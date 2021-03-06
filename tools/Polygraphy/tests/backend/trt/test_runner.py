#
# Copyright (c) 2021, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import threading

import pytest
import tensorrt as trt
from polygraphy.backend.trt import (CreateConfig, EngineFromNetwork,
                                    NetworkFromOnnxBytes, Profile, TrtRunner)
from polygraphy.common import func
from polygraphy.logger import G_LOGGER
from polygraphy.util import misc
from tests.common import version
from tests.models.meta import ONNX_MODELS


class TestLoggerCallbacks(object):
    @pytest.mark.parametrize("sev", G_LOGGER.SEVERITY_LETTER_MAPPING.keys())
    def test_set_severity(self, sev):
        G_LOGGER.severity = sev


class TestTrtRunner(object):
    def test_can_name_runner(self):
        NAME = "runner"
        runner = TrtRunner(None, name=NAME)
        assert runner.name == NAME


    def test_basic(self):
        model = ONNX_MODELS["identity"]
        network_loader = NetworkFromOnnxBytes(model.loader)
        with TrtRunner(EngineFromNetwork(network_loader)) as runner:
            assert runner.is_active
            model.check_runner(runner)
        assert not runner.is_active


    def test_context(self):
        model = ONNX_MODELS["identity"]
        engine = func.invoke(EngineFromNetwork(NetworkFromOnnxBytes(model.loader)))
        with engine, TrtRunner(engine.create_execution_context) as runner:
            model.check_runner(runner)


    @pytest.mark.skipif(version(trt.__version__) < version("7.0"), reason="Unsupported for TRT 6")
    def test_shape_output(self):
        model = ONNX_MODELS["reshape"]
        engine = func.invoke(EngineFromNetwork(NetworkFromOnnxBytes(model.loader)))
        with engine, TrtRunner(engine.create_execution_context) as runner:
            model.check_runner(runner)


    def test_multithreaded_runners_from_engine(self):
        model = ONNX_MODELS["identity"]
        engine = func.invoke(EngineFromNetwork(NetworkFromOnnxBytes(model.loader)))

        with engine, TrtRunner(engine) as runner0, TrtRunner(engine) as runner1:
            t1 = threading.Thread(target=model.check_runner, args=(runner0, ))
            t2 = threading.Thread(target=model.check_runner, args=(runner1, ))
            t1.start()
            t2.start()
            t2.join()
            t2.join()


    @pytest.mark.skipif(version(trt.__version__) < version("7.0"), reason="Unsupported for TRT 6")
    def test_multiple_profiles(self):
        model = ONNX_MODELS["dynamic_identity"]
        shapes = [(1, 2, 4, 4), (1, 2, 8, 8), (1, 2, 16, 16)]
        network_loader = NetworkFromOnnxBytes(model.loader)
        profiles = [
            Profile().add("X", (1, 2, 1, 1), (1, 2, 2, 2), (1, 2, 4, 4)),
            Profile().add("X", *shapes),
        ]
        config_loader = CreateConfig(profiles=profiles)
        with TrtRunner(EngineFromNetwork(network_loader, config_loader)) as runner:
            if misc.version(trt.__version__) < misc.version("7.3"):
                runner.context.active_optimization_profile = 1
            else:
                runner.context.set_optimization_profile_async(1, runner.stream.address())
            for shape in shapes:
                model.check_runner(runner, {"X": shape})


    @pytest.mark.skipif(version(trt.__version__) < version("7.0"), reason="Unsupported for TRT 6")
    def test_empty_tensor_with_dynamic_input_shape_tensor(self):
        model = ONNX_MODELS["empty_tensor_expand"]
        shapes = [(1, 2, 0, 3, 0), (2, 2, 0, 3, 0), (4, 2, 0, 3, 0)]
        network_loader = NetworkFromOnnxBytes(model.loader)
        profiles = [Profile().add("new_shape", *shapes)]
        config_loader = CreateConfig(profiles=profiles)

        with TrtRunner(EngineFromNetwork(network_loader, config_loader)) as runner:
            for shape in shapes:
                model.check_runner(runner, {"new_shape": shape})
