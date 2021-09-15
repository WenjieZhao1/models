#!/bin/bash
# Copyright 2020 Huawei Technologies Co., Ltd
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
if [ $# != 2 ] && [ $# != 1 ]; then
  echo "Usage: sh run_eval.sh [CKPT_PATH] [DEVICE_ID]"
  exit 1
fi

if [ $# == 2 ]; then
  export DEVICE_ID=$2
else
  export DEVICE_ID=0
fi

ulimit -u unlimited

BASEPATH=$(cd "`dirname $0`" || exit; pwd)
export PYTHONPATH=${BASEPATH}:$PYTHONPATH
python ${BASEPATH}/../eval.py --ckpt_path $1 > ./eval.log 2>&1 &
