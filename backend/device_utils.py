"""GPU/CPU auto-detection and device helper for AI Sentinel."""
from __future__ import annotations

import torch


def get_device() -> torch.device:
    """Detect best available device: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def get_device_name() -> str:
    """Return human-readable device name."""
    device = get_device()
    if device.type == "cuda":
        return torch.cuda.get_device_name(0)
    if device.type == "mps":
        return "Apple Silicon (MPS)"
    return "CPU"


def is_gpu_available() -> bool:
    """Check if GPU is available."""
    return get_device().type in ("cuda", "mps")


def get_onnx_providers() -> list:
    """Return ONNX Runtime providers in priority order.

    Policy lives in ``yolo_onnx.select_providers`` (runtime backend selection
    region, WT-16): auto/cpu/cuda via AI_SENTINEL_ORT_DEVICE, pinned CUDA
    options, CPU fallback appended. Kept as a thin delegate so existing
    callers (weapon.py, person_detector.py) keep their import contract.
    """
    from yolo_onnx import select_providers
    return select_providers()


def get_half_precision_dtype() -> torch.dtype | None:
    """Return half-precision dtype if supported, else None."""
    device = get_device()
    if device.type == "cuda":
        return torch.float16
    return None
