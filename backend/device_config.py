"""Centralized device configuration with GPU auto-detection."""
import os
import torch


def get_optimal_device(prefer_gpu: bool = True) -> torch.device:
    if not prefer_gpu:
        return torch.device("cpu")
    if torch.cuda.is_available():
        device = torch.device("cuda:0")
        props = torch.cuda.get_device_properties(0)
        print(f"[Device] CUDA GPU: {props.name}, {props.total_memory / 1e9:.1f} GB VRAM")
        return device
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        print("[Device] Apple MPS (Metal) detected")
        return torch.device("mps")
    print("[Device] No GPU detected, using CPU")
    return torch.device("cpu")


def enable_half_precision(device: torch.device) -> bool:
    if device.type != "cuda":
        return False
    capability = torch.cuda.get_device_capability(device.index or 0)
    if capability[0] >= 7:
        print("[Device] FP16 half-precision supported")
        return True
    return False


__all__ = ["get_optimal_device", "enable_half_precision"]
