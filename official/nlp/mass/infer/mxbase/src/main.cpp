/**
 * Copyright 2021 Huawei Technologies Co., Ltd
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <dirent.h>
#include <unistd.h>

#include <algorithm>
#include <fstream>
#include <iostream>
#include <vector>

#include "MassNerBase.h"
#include "MxBase/Log/Log.h"

std::vector<double> g_inferCost;
uint32_t FEATURES = 64;

void InitMassParam(InitParam* initParam) {
  initParam->deviceId = 0;
  initParam->modelPath = "../data/model/mass.om";
}

int main(int argc, char* argv[]) {
  if (argc < 3) {
    LogWarn << "Please input data path, model path, node num, feature num, "
               "class num.";
    return APP_ERR_OK;
  }

  InitParam initParam;
  InitMassParam(&initParam);
  initParam.modelPath = argv[2];
  FEATURES = atoi(argv[3]);
  auto massBase = std::make_shared<MassNerBase>();
  APP_ERROR ret = massBase->Init(initParam);
  if (ret != APP_ERR_OK) {
    LogError << "Massbase init failed, ret=" << ret << ".";
    return ret;
  }

  std::string inferPath = argv[1];
  std::vector<std::string> files;
  files.push_back(argv[1]);

  for (uint32_t i = 0; i < files.size(); i++) {
    LogInfo << "read file name: " << files[i];
    ret = massBase->Process(inferPath, files[i]);
    if (ret != APP_ERR_OK) {
      LogError << "Massbase process failed, ret=" << ret << ".";
      massBase->DeInit();
      return ret;
    }
  }

  massBase->DeInit();
  double costSum = 0;
  for (uint32_t i = 0; i < g_inferCost.size(); i++) {
    costSum += g_inferCost[i];
  }
  LogInfo << "Infer texts sum " << g_inferCost.size()
          << ", cost total time: " << costSum << " ms.";
  LogInfo << "The throughput: " << g_inferCost.size() * 1000 / costSum
          << " bin/sec.";
  return APP_ERR_OK;
}
