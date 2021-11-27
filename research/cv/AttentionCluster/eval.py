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
"""Eval Attention Cluster"""
import mindspore.dataset as ds
import mindspore.nn as nn
import mindspore.context as context
import mindspore.common as common
from mindspore.train.model import Model
from mindspore.train.serialization import load_checkpoint, load_param_into_net
from src.models.attention_cluster import AttentionCluster
from src.datasets.mnist_feature import MNISTFeature
from src.utils.config import parse_opts


if __name__ == '__main__':
    # Test settings
    args = parse_opts()

    # init context
    common.set_seed(args.seed)
    context.set_context(mode=context.GRAPH_MODE, device_target='Ascend', device_id=args.device_id)

    #define net
    fdim = [50]
    natt = [args.natt]
    nclass = 1024
    net = AttentionCluster(fdims=fdim, natts=natt, nclass=nclass, fc=args.fc)

    # define loss
    loss = nn.SoftmaxCrossEntropyWithLogits(sparse=True)

    # create dataset
    dataset_generator = MNISTFeature(root=args.data_dir, train=False, transform=None)
    dataset = ds.GeneratorDataset(dataset_generator, ["feature", "target"], shuffle=False)
    dataset = dataset.batch(args.batch_size, drop_remainder=True)

    # define model
    model = Model(network=net, loss_fn=loss,
                  metrics={'top_1_accuracy': nn.Top1CategoricalAccuracy(),
                           'top_5_accuracy': nn.Top5CategoricalAccuracy()}
                  )

    # load checkpoint
    param_dict = load_checkpoint(ckpt_file_name=args.ckpt)
    load_param_into_net(net, param_dict)
    net.set_train(False)

    # eval model
    res = model.eval(valid_dataset=dataset)
    print("result:", res, "ckpt:", args.ckpt)
