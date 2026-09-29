import pytest
import torch


def test_get_device_returns_torch_device():
    from device_utils import get_device
    device = get_device()
    assert isinstance(device, torch.device)


def test_get_device_returns_valid_type():
    from device_utils import get_device
    device = get_device()
    assert device.type in ("cuda", "mps", "cpu")


def test_device_name_returns_string():
    from device_utils import get_device_name
    name = get_device_name()
    assert isinstance(name, str)
    assert len(name) > 0


def test_is_gpu_returns_bool():
    from device_utils import is_gpu_available
    result = is_gpu_available()
    assert isinstance(result, bool)


def test_get_onnx_providers_returns_list():
    from device_utils import get_onnx_providers
    providers = get_onnx_providers()
    assert isinstance(providers, list)
    assert len(providers) > 0
    assert "CPUExecutionProvider" in providers
