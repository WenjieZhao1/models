/*
 * Copyright 2021 Huawei Technologies Co., Ltd.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "Dscnn.h"
#include <unistd.h>
#include <sys/stat.h>
#include <memory>
#include <string>
#include <fstream>
#include <algorithm>
#include <vector>
#include "MxBase/DeviceManager/DeviceManager.h"
#include "MxBase/Log/Log.h"

APP_ERROR DSCNN::Init(const InitParam &initParam) {
    deviceId_ = initParam.deviceId;
    APP_ERROR ret = MxBase::DeviceManager::GetInstance()->InitDevices();
    if (ret != APP_ERR_OK) {
        LogError << "Init devices failed, ret=" << ret << ".";
        return ret;
    }
    ret = MxBase::TensorContext::GetInstance()->SetContext(initParam.deviceId);
    if (ret != APP_ERR_OK) {
        LogError << "Set context failed, ret=" << ret << ".";
        return ret;
    }
    model_ = std::make_shared<MxBase::ModelInferenceProcessor>();
    ret = model_->Init(initParam.modelPath, modelDesc_);
    if (ret != APP_ERR_OK) {
        LogError << "ModelInferenceProcessor init failed, ret=" << ret << ".";
        return ret;
    }
    return APP_ERR_OK;
}

APP_ERROR DSCNN::DeInit() {
    dvppWrapper_->DeInit();
    model_->DeInit();
    MxBase::DeviceManager::GetInstance()->DestroyDevices();
    return APP_ERR_OK;
}

APP_ERROR DSCNN::VectorToTensorBase(const std::vector<std::vector<float>> &input_x, MxBase::TensorBase *tensorBase) {
    uint32_t dataSize = 1;
    for (size_t i = 0; i < modelDesc_.inputTensors.size(); i++) {
        std::vector<uint32_t> shape = {};
        for (size_t j = 0; j < modelDesc_.inputTensors[i].tensorDims.size(); j++) {
            shape.push_back((uint32_t)modelDesc_.inputTensors[i].tensorDims[j]);
        }
        for (uint32_t s = 0; s < shape.size(); ++s) {
            dataSize *= shape[s];
        }
    }
    float *metaFeatureData = new float[dataSize];
    uint32_t idx = 0;
    for (size_t bs = 0; bs < input_x.size(); bs++) {
        for (size_t c = 0; c < input_x[bs].size(); c++) {
            metaFeatureData[idx++] = input_x[bs][c];
        }
    }
    MxBase::MemoryData memoryDataDst(dataSize * 4, MxBase::MemoryData::MEMORY_DEVICE, deviceId_);
    MxBase::MemoryData memoryDataSrc(reinterpret_cast<void *>(metaFeatureData),
                                     dataSize * 4, MxBase::MemoryData::MEMORY_HOST_MALLOC);

    APP_ERROR ret = MxBase::MemoryHelper::MxbsMallocAndCopy(memoryDataDst, memoryDataSrc);
    if (ret != APP_ERR_OK) {
        LogError << GetError(ret) << "Memory malloc failed.";
        return ret;
    }

    std::vector<uint32_t> shape = {100, 1, 49, 20};
    *tensorBase = MxBase::TensorBase(memoryDataDst, false, shape, MxBase::TENSOR_DTYPE_FLOAT32);
    return APP_ERR_OK;
}

APP_ERROR DSCNN::Inference(const std::vector<MxBase::TensorBase> &inputs,
                                      std::vector<MxBase::TensorBase> *outputs) {
    auto dtypes = model_->GetOutputDataType();
    for (size_t i = 0; i < modelDesc_.outputTensors.size(); i++) {
        std::vector<uint32_t> shape = {};
        for (size_t j = 0; j < modelDesc_.outputTensors[i].tensorDims.size(); j++) {
            shape.push_back((uint32_t)modelDesc_.outputTensors[i].tensorDims[j]);
        }
        MxBase::TensorBase tensor(shape, dtypes[i],  MxBase::MemoryData::MemoryType::MEMORY_DEVICE, deviceId_);
        APP_ERROR ret = MxBase::TensorBase::TensorBaseMalloc(tensor);
        if (ret != APP_ERR_OK) {
            LogError << "TensorBaseMalloc failed, ret=" << ret << ".";
            return ret;
        }
        (*outputs).push_back(tensor);
    }
    MxBase::DynamicInfo dynamicInfo = {};
    dynamicInfo.dynamicType = MxBase::DynamicType::STATIC_BATCH;
    auto startTime = std::chrono::high_resolution_clock::now();
    APP_ERROR ret = model_->ModelInference(inputs, *outputs, dynamicInfo);
    auto endTime = std::chrono::high_resolution_clock::now();
    double costMs = std::chrono::duration<double, std::milli>(endTime - startTime).count();
    inferCostTimeMilliSec += costMs;
    if (ret != APP_ERR_OK) {
        LogError << "ModelInference failed, ret=" << ret << ".";
        return ret;
    }
    return APP_ERR_OK;
}

APP_ERROR DSCNN::SaveInferResult(std::vector<float> *batchFeaturePaths, const std::vector<MxBase::TensorBase> &inputs) {
    for (auto retTensor : inputs) {
        std::vector<uint32_t> shape = retTensor.GetShape();
        uint32_t N = shape[0];
        uint32_t C = shape[1];
        if (!retTensor.IsHost()) {
            retTensor.ToHost();
        }
        void* data = retTensor.GetBuffer();

        for (uint32_t i = 0; i < N; i++) {
            for (uint32_t j = 0; j < C; j++) {
                float value = *(reinterpret_cast<float*>(data) + i * C + j);
                batchFeaturePaths->emplace_back(value);
            }
        }
    }
    return APP_ERR_OK;
}

int DSCNN::arg_max(const std::vector<float> & vec) {
  return static_cast<int>(std::distance(vec.begin(), std::max_element(vec.begin(), vec.end())));
}

std::vector<int> DSCNN::argsort(const std::vector<float>& array) {
    const int array_len(array.size());
    std::vector<int> array_index(array_len, 0);
    for (int i = 0; i < array_len; ++i)
        array_index[i] = i;

    std::sort(array_index.begin(), array_index.end(),
              [&array](int pos1, int pos2) {return (array[pos1] < array[pos2]);});
    return array_index;
}


APP_ERROR DSCNN::WriteResult(const std::vector<int> &outputs) {
    std::string resultPathName = "./result.txt";
    std::ofstream outfile(resultPathName, std::ios::app);
    if (outfile.fail()) {
        LogError << "Failed to open result file: ";
        return APP_ERR_COMM_FAILURE;
    }
    std::string tmp;
    for (auto x : outputs) {
        tmp += std::to_string(x) + " ";
    }
    tmp = tmp.substr(0, tmp.size()-1);
    outfile << tmp << std::endl;
    outfile.close();
    return APP_ERR_OK;
}

APP_ERROR DSCNN::Process(const std::vector<std::vector<float>> &input_x, const InitParam &initParam,
                         std::vector<int> *output1, std::vector<std::vector<int>> *output5) {
    std::vector<MxBase::TensorBase> inputs = {};
    std::vector<MxBase::TensorBase> outputs;
    std::vector<float> batchFeaturePaths;
    std::vector<int> toWrite;
    MxBase::TensorBase tensorBase;
    auto ret = VectorToTensorBase(input_x, &tensorBase);
    if (ret != APP_ERR_OK) {
        LogError << "ToTensorBase failed, ret=" << ret << ".";
        return ret;
    }
    inputs.push_back(tensorBase);
    auto startTime = std::chrono::high_resolution_clock::now();
    ret = Inference(inputs, &outputs);

    auto endTime = std::chrono::high_resolution_clock::now();
    double costMs = std::chrono::duration<double, std::milli>(endTime - startTime).count();
    inferCostTimeMilliSec += costMs;
    if (ret != APP_ERR_OK) {
        LogError << "Inference failed, ret=" << ret << ".";
        return ret;
    }

    ret = SaveInferResult(&batchFeaturePaths, outputs);
    if (ret != APP_ERR_OK) {
        LogError << "Save model infer results into file failed. ret = " << ret << ".";
        return ret;
    }
    int res = arg_max(batchFeaturePaths);
    (*output1).emplace_back(res);
    toWrite.push_back(res);
    std::vector<int> out5;
    std::vector<int> index = argsort(batchFeaturePaths);
    std::reverse(index.begin(), index.end());
    for (int i =0; i < 5; i ++) {
        out5.push_back(index[i]);
    }
    output5->push_back(out5);

    ret = WriteResult(toWrite);
    if (ret != APP_ERR_OK) {
        LogError << "WriteResult failed, ret=" << ret << ".";
        return ret;
    }
    return APP_ERR_OK;
}
