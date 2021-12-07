# Copyright 2021 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""train imagenet."""
import argparse
import ast
import os
import time
from collections import OrderedDict
import numpy as np

from mindspore import Tensor
from mindspore import context
from mindspore.context import ParallelMode
from mindspore.communication.management import init, get_rank, get_group_size
from mindspore.nn.optim.rmsprop import RMSProp
from mindspore.train.callback import ModelCheckpoint, CheckpointConfig, LossMonitor, TimeMonitor
from mindspore.train.model import Model
from mindspore.train.serialization import load_checkpoint, load_param_into_net
from mindspore.common import set_seed
from mindspore.common import dtype as mstype
from mindspore import export

from src.config import nasnet_a_mobile_config_gpu, nasnet_a_mobile_config_ascend
from src.dataset import create_dataset
from src.nasnet_a_mobile import NASNetAMobileWithLoss, NASNetAMobile
from src.lr_generator import get_lr

def export_models(checkpoint_path):
    net = NASNetAMobile(num_classes=config.num_classes, is_training=False)

    file_list = []
    for root, _, files in os.walk(checkpoint_path):
        for file in files:
            if os.path.splitext(file)[1] == '.ckpt':
                file_list.append(os.path.join(root, file))

    file_list.sort(key=os.path.getmtime, reverse=True)
    exported_count = 0

    for checkpoint in file_list:
        ckpt_dict = load_checkpoint(checkpoint)

        parameter_dict = OrderedDict()
        for name in ckpt_dict:
            new_name = name
            if new_name.startswith("network."):
                new_name = new_name.replace("network.", "")
            parameter_dict[new_name] = ckpt_dict[name]
        load_param_into_net(net, parameter_dict)

        output_file = checkpoint.replace('.ckpt', '')
        input_data = Tensor(np.zeros([1, 3, 224, 224]), mstype.float32)

        if args_opt.export_mindir_model:
            export(net, input_data, file_name=output_file, file_format="MINDIR")
        if args_opt.export_air_model and context.get_context("device_target") == "Ascend":
            export(net, input_data, file_name=output_file, file_format="AIR")
        if args_opt.export_onnx_model:
            export(net, input_data, file_name=output_file, file_format="ONNX")

        print(checkpoint, 'is exported')

        exported_count += 1
        if exported_count >= args_opt.export_checkpoint_count:
            print('exported checkpoint count =', exported_count)
            break

def filter_checkpoint_parameter_by_list(origin_dict, param_filter):
    for key in list(origin_dict.keys()):
        for name in param_filter:
            if name in key:
                print("Delete parameter from checkpoint: ", key)
                del origin_dict[key]
                break

if __name__ == '__main__':
    start_time = time.time()

    parser = argparse.ArgumentParser(description='image classification training')
    parser.add_argument('--dataset_path', type=str, default='../imagenet', help='Dataset path')
    parser.add_argument('--resume', type=str, default='',
                        help='resume training with existed checkpoint')
    parser.add_argument('--resume_epoch', type=int, default=1, help='Resume from which epoch')
    parser.add_argument('--is_distributed', type=ast.literal_eval, default=False,
                        help='distributed training')
    parser.add_argument('--platform', type=str, default='Ascend', choices=('Ascend', 'GPU'),
                        help='run platform')

    parser.add_argument('--device_id', type=int, default=0, help='device id(Default:0)')

    parser.add_argument('--is_modelarts', type=ast.literal_eval, default=False)
    parser.add_argument('--data_url', type=str, default=None, help='Dataset path for modelarts')
    parser.add_argument('--train_url', type=str, default=None, help='Output path for modelarts')

    parser.add_argument('--use_pynative_mode', type=ast.literal_eval, default=False,
                        help='whether to use pynative mode for device(Default: False)')

    parser.add_argument('--amp_level', type=str, default='O0', help='level for mixed precision training')

    parser.add_argument('--remove_classifier_parameter', type=ast.literal_eval, default=False,
                        help='whether to filter the classifier parameter in the checkpoint (Default: False)')

    parser.add_argument('--export_mindir_model', type=ast.literal_eval, default=True,
                        help='whether to export MINDIR model (Default: True)')

    parser.add_argument('--export_air_model', type=ast.literal_eval, default=True,
                        help='whether to export AIR model on Ascend 910 (Default: True)')

    parser.add_argument('--export_onnx_model', type=ast.literal_eval, default=False,
                        help='whether to export ONNX model (Default: False)')

    parser.add_argument('--export_checkpoint_count', type=int, default=1,
                        help='export how many checkpoints reversed from the last epoch (Default: 1)')

    parser.add_argument('--overwrite_config', type=ast.literal_eval, default=False,
                        help='whether to overwrite the config according to the arguments')
    #when the overwrite_config == True , the following argument will be written to config
    parser.add_argument('--epoch_size', type=int, default=600,
                        help='Epoches for trainning(default:600)')
    parser.add_argument('--num_classes', type=int, default=1000, help='number of classes')
    parser.add_argument('--cutout', type=ast.literal_eval, default=False,
                        help='whether to cutout the data for trainning(Default: False)')
    parser.add_argument('--train_batch_size', type=int, default=32, help='batch size for training')
    parser.add_argument('--lr_init', type=float, default=0.32, help='learning rate for training')

    args_opt = parser.parse_args()

    is_modelarts = args_opt.is_modelarts

    if args_opt.platform == 'GPU':
        config = nasnet_a_mobile_config_gpu
        drop_remainder = True
    else:
        config = nasnet_a_mobile_config_ascend
        drop_remainder = False

    if args_opt.overwrite_config:
        config.epoch_size = args_opt.epoch_size
        config.num_classes = args_opt.num_classes
        config.cutout = args_opt.cutout
        config.train_batch_size = args_opt.train_batch_size
        config.lr_init = args_opt.lr_init

    print('epoch_size = ', config.epoch_size, ' num_classes = ', config.num_classes)
    print('train_batch_size = ', config.train_batch_size, ' lr_init = ', config.lr_init)
    print('cutout = ', config.cutout, ' cutout_length =', config.cutout_length)

    set_seed(config.random_seed)

    if args_opt.use_pynative_mode:
        context.set_context(mode=context.PYNATIVE_MODE, device_target=args_opt.platform)
    else:
        context.set_context(mode=context.GRAPH_MODE, device_target=args_opt.platform, save_graphs=False)

    # init distributed
    if args_opt.is_distributed:
        init()

        if args_opt.is_modelarts:
            device_id = get_rank()
            config.group_size = get_group_size()
        else:
            if args_opt.platform == 'Ascend':
                device_id = int(os.getenv('DEVICE_ID', default='0'))
                config.group_size = int(os.getenv('DEVICE_NUM', default='1'))
            else:
                device_id = get_rank()
                config.group_size = get_group_size()

        context.set_auto_parallel_context(parallel_mode=ParallelMode.DATA_PARALLEL,
                                          device_num=config.group_size,
                                          gradients_mean=True)
    else:
        device_id = args_opt.device_id
        config.group_size = 1
        context.set_context(device_id=device_id)
    rank_id = device_id
    config.rank = rank_id
    print('rank_id = ', rank_id, ' group_size = ', config.group_size)

    resume = args_opt.resume
    if args_opt.is_modelarts:
        # download dataset from obs to cache
        import moxing
        dataset_path = '/cache/dataset'
        if args_opt.data_url.find('/train/') > 0:
            dataset_path += '/train/'
        moxing.file.copy_parallel(src_url=args_opt.data_url, dst_url=dataset_path)

        # download the checkpoint from obs to cache
        if resume != '':
            base_name = os.path.basename(resume)
            dst_url = '/cache/checkpoint/' + base_name
            moxing.file.copy_parallel(src_url=resume, dst_url=dst_url)
            resume = dst_url

        # the path for the output of training
        save_checkpoint_path = '/cache/train_output/' + str(device_id) + '/'
    else:
        dataset_path = args_opt.dataset_path
        save_checkpoint_path = os.path.join(config.ckpt_path, 'ckpt_' + str(config.rank) + '/')

    log_filename = os.path.join(save_checkpoint_path, 'log_' + str(device_id) + '.txt')

    # dataloader
    if dataset_path.find('/train') > 0:
        dataset_train_path = dataset_path
    else:
        dataset_train_path = os.path.join(dataset_path, 'train')
        if not os.path.exists(dataset_train_path):
            dataset_train_path = dataset_path

    train_dataset = create_dataset(dataset_train_path, True, config.rank, config.group_size,
                                   num_parallel_workers=config.work_nums,
                                   batch_size=config.train_batch_size,
                                   drop_remainder=drop_remainder, shuffle=True,
                                   cutout=config.cutout, cutout_length=config.cutout_length,
                                   image_size=config.image_size)
    batches_per_epoch = train_dataset.get_dataset_size()
    # network
    net_with_loss = NASNetAMobileWithLoss(config)
    if resume != '':
        ckpt = load_checkpoint(resume)

        print('remove_classifier_parameter = ', args_opt.remove_classifier_parameter)

        if args_opt.remove_classifier_parameter:
            filter_list = [x.name for x in net_with_loss.network.classifier.get_parameters()]
            filter_checkpoint_parameter_by_list(ckpt, filter_list)

            filter_list = [x.name for x in net_with_loss.network.aux_logits.fc.get_parameters()]
            filter_checkpoint_parameter_by_list(ckpt, filter_list)

        load_param_into_net(net_with_loss, ckpt)
        print(resume, ' is loaded')

    # learning rate schedule
    lr = get_lr(lr_init=config.lr_init, lr_decay_rate=config.lr_decay_rate,
                num_epoch_per_decay=config.num_epoch_per_decay, total_epochs=config.epoch_size,
                steps_per_epoch=batches_per_epoch, is_stair=True)
    if resume:
        resume_epoch = args_opt.resume_epoch
        step_num_in_epoch = train_dataset.get_dataset_size()
        lr = lr[step_num_in_epoch * resume_epoch:]
        # adjust the epoch_size in config so that the source code for model.train will be simplified.
        config.epoch_size = config.epoch_size - resume_epoch
        print('Effective epoch_size = ', config.epoch_size)
    lr = Tensor(lr, mstype.float32)

    # optimizer
    decayed_params = []
    no_decayed_params = []
    for param in net_with_loss.trainable_params():
        if 'beta' not in param.name and 'gamma' not in param.name and 'bias' not in param.name:
            decayed_params.append(param)
        else:
            no_decayed_params.append(param)
    group_params = [{'params': decayed_params, 'weight_decay': config.weight_decay},
                    {'params': no_decayed_params},
                    {'order_params': net_with_loss.trainable_params()}]
    optimizer = RMSProp(group_params, lr, decay=config.rmsprop_decay, weight_decay=config.weight_decay,
                        momentum=config.momentum, epsilon=config.opt_eps, loss_scale=config.loss_scale)

    # high performance
    net_with_loss.set_train()

    print('amp_level = ', args_opt.amp_level)

    model = Model(net_with_loss, optimizer=optimizer, amp_level=args_opt.amp_level)

    print("============== Starting Training ==============")
    loss_cb = LossMonitor(per_print_times=batches_per_epoch)
    time_cb = TimeMonitor(data_size=batches_per_epoch)

    callbacks = [loss_cb, time_cb]

    config_ck = CheckpointConfig(save_checkpoint_steps=batches_per_epoch,
                                 keep_checkpoint_max=config.keep_checkpoint_max)
    ckpoint_cb = ModelCheckpoint(prefix=f"nasnet-a-mobile-rank{config.rank}",
                                 directory=save_checkpoint_path, config=config_ck)
    if args_opt.is_distributed and config.is_save_on_master == 1:
        if config.rank == 0:
            callbacks.append(ckpoint_cb)
    else:
        callbacks.append(ckpoint_cb)

    try:
        model.train(config.epoch_size, train_dataset, callbacks=callbacks, dataset_sink_mode=True)
    except KeyboardInterrupt:
        print("!!!!!!!!!!!!!! Train Failed !!!!!!!!!!!!!!!!!!!")
    else:
        print("============== Train Success ==================")

    export_models(save_checkpoint_path)

    print("data_url   = ", args_opt.data_url)
    print("cutout = ", config.cutout, " cutout_length = ", config.cutout_length)
    print("epoch_size = ", config.epoch_size, " train_batch_size = ", config.train_batch_size,
          " lr_init = ", config.lr_init, " weight_decay = ", config.weight_decay)

    print("time: ", (time.time() - start_time) / 3600, " hours")

    fp = open(log_filename, 'at+')

    print("data_url   = ", args_opt.data_url, file=fp)
    print("cutout = ", config.cutout, " cutout_length = ", config.cutout_length, file=fp)
    print("epoch_size = ", config.epoch_size, " train_batch_size = ", config.train_batch_size,
          " lr_init = ", config.lr_init, " weight_decay = ", config.weight_decay, file=fp)

    print("time: ", (time.time() - start_time) / 3600, file=fp)
    fp.close()

    if args_opt.is_modelarts:
        if os.path.exists('/cache/train_output'):
            moxing.file.copy_parallel(src_url='/cache/train_output', dst_url=args_opt.train_url)
