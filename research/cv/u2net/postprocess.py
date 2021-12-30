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
"""postprocess"""
import argparse
import os

import cv2
import imageio
import numpy as np
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("--bin_path", type=str, help='bin_path, path to binary files generated by 310 model, default: None')
parser.add_argument("--content_path", type=str, help='content_path, default: None')
parser.add_argument("--output_dir", type=str, default='output_dir',
                    help='output_path, path to store output, default: None')
args = parser.parse_args()

if __name__ == "__main__":
    bin_path = args.bin_path
    original_dir = args.content_path
    content_list = os.listdir(args.bin_path)


    def normPRED(d):
        """rescale the value of tensor to between 0 and 1"""
        ma = d.max()
        mi = d.min()
        dn = (d - mi) / (ma - mi)
        return dn


    for i in range(0, len(content_list)):
        pic_path = os.path.join(args.bin_path, content_list[i])
        b = np.fromfile(pic_path, dtype=np.float32, count=320 * 320)
        b = np.reshape(b, (320, 320))
        file_path = os.path.join(original_dir, content_list[i]).replace("_0.bin", ".jpg")
        original = np.array(Image.open(file_path), dtype='float32')
        shape = original.shape
        b = normPRED(b)
        image = b
        content_name = content_list[i].replace("_0.bin", "")
        image = cv2.resize(image, dsize=(0, 0), fx=shape[1] / image.shape[1], fy=shape[0] / image.shape[0])
        image_path = os.path.join(args.output_dir, content_name) + ".png"
        imageio.imsave(image_path, image)
        print("%d / %d , %s \n" % (i, len(content_list), content_name))
