"""Scoped tests for the ONNX runtime backend selection policy (WT-16).

Covers yolo_onnx.select_providers and the device_utils delegation contract:
device override via AI_SENTINEL_ORT_DEVICE, pinned CUDA options, CPU fallback,
and the hard failure when CUDA is explicitly requested but unavailable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yolo_onnx  # noqa: E402


class FakeOrt:
    def __init__(self, available):
        self._available = list(available)

    def get_available_providers(self):
        return list(self._available)


ALL_PROVIDERS = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]


def test_auto_prefers_cuda_with_pinned_options():
    providers = yolo_onnx.select_providers(FakeOrt(ALL_PROVIDERS), device="auto")
    assert providers[0] == ("CUDAExecutionProvider", dict(yolo_onnx.CUDA_PROVIDER_OPTIONS))
    assert providers[-1] == "CPUExecutionProvider"


def test_auto_falls_back_to_cpu_without_cuda():
    providers = yolo_onnx.select_providers(FakeOrt(["CPUExecutionProvider"]), device="auto")
    assert providers == ["CPUExecutionProvider"]


def test_cpu_override_wins_even_with_cuda_available(monkeypatch):
    monkeypatch.setenv("AI_SENTINEL_ORT_DEVICE", "cpu")
    providers = yolo_onnx.select_providers(FakeOrt(ALL_PROVIDERS))
    assert providers == ["CPUExecutionProvider"]


def test_cuda_override_without_cuda_support_is_a_hard_error():
    with pytest.raises(RuntimeError, match="does not list CUDAExecutionProvider"):
        yolo_onnx.select_providers(FakeOrt(["CPUExecutionProvider"]), device="cuda")


def test_cuda_override_uses_pinned_options():
    providers = yolo_onnx.select_providers(FakeOrt(ALL_PROVIDERS), device="cuda")
    assert providers[0][1] == {"use_tf32": "0", "cudnn_conv_algo_search": "HEURISTIC"}


def test_invalid_device_value_is_rejected():
    with pytest.raises(ValueError, match="must be one of"):
        yolo_onnx.select_providers(FakeOrt(ALL_PROVIDERS), device="tensorrt")


def test_empty_env_value_defaults_to_auto(monkeypatch):
    monkeypatch.setenv("AI_SENTINEL_ORT_DEVICE", "")
    providers = yolo_onnx.select_providers(FakeOrt(ALL_PROVIDERS))
    assert providers[0][0] == "CUDAExecutionProvider"


def test_env_invalid_value_is_rejected(monkeypatch):
    monkeypatch.setenv("AI_SENTINEL_ORT_DEVICE", "gpu")
    with pytest.raises(ValueError, match="AI_SENTINEL_ORT_DEVICE"):
        yolo_onnx.select_providers(FakeOrt(ALL_PROVIDERS))


def test_tensorrt_provider_is_never_selected():
    # The policy must not advertise TRT while TRT runtime libs are absent.
    providers = yolo_onnx.select_providers(FakeOrt(ALL_PROVIDERS), device="auto")
    assert all("Tensorrt" not in str(entry) for entry in providers)


def test_device_utils_delegates_to_the_same_policy(monkeypatch):
    import device_utils
    monkeypatch.setenv("AI_SENTINEL_ORT_DEVICE", "cpu")
    assert device_utils.get_onnx_providers() == ["CPUExecutionProvider"]
    monkeypatch.setenv("AI_SENTINEL_ORT_DEVICE", "auto")
    providers = device_utils.get_onnx_providers()
    # Real ORT on this box lists CUDA: same shape as the policy contract.
    assert providers[-1] == "CPUExecutionProvider"
    assert providers == yolo_onnx.select_providers()
