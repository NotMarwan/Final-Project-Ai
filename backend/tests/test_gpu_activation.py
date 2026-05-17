"""Tests to verify GPU activation for AI Sentinel."""
import pytest
import torch


def test_pytorch_is_cuda_version():
    """Ensure PyTorch is built with CUDA support."""
    assert torch.cuda.is_available(), "PyTorch CUDA is not available"
    assert "cu" in torch.__version__, f"Expected CUDA PyTorch, got: {torch.__version__}"


def test_rtx_3060_detected():
    """Verify RTX 3060 is detected and accessible."""
    assert torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0)
    assert "RTX 3060" in device_name, f"Expected RTX 3060, got: {device_name}"


def test_device_utils_returns_cuda():
    """Verify device_utils selects CUDA over CPU."""
    from device_utils import get_device, is_gpu_available, get_device_name
    
    device = get_device()
    assert device.type == "cuda", f"Expected cuda device, got: {device.type}"
    assert is_gpu_available() is True
    assert "RTX 3060" in get_device_name()


def test_device_config_returns_cuda():
    """Verify device_config selects optimal GPU."""
    from device_config import get_optimal_device
    
    device = get_optimal_device(prefer_gpu=True)
    assert device.type == "cuda", f"Expected cuda, got: {device.type}"
    assert device.index == 0


def test_vram_sufficient():
    """Verify GPU has enough VRAM for AI Sentinel models."""
    assert torch.cuda.is_available()
    total_vram = torch.cuda.get_device_properties(0).total_memory
    min_required = 4 * 1024**3  # 4GB minimum
    assert total_vram >= min_required, f"VRAM {total_vram / 1e9:.1f}GB < required 4GB"


def test_cuda_tensor_operations():
    """Verify basic CUDA tensor operations work."""
    device = torch.device("cuda:0")
    tensor = torch.randn(1000, 1000, device=device)
    result = tensor @ tensor.T
    assert result.device.type == "cuda"
