"""Shared contracts for Ultralytics detection ONNX exports (batch one).

Raw YOLOv8 tensors contain pixel cxcywh and class probabilities, without an
objectness column. Post-NMS tensors require an explicit format declaration.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from typing import Mapping

import cv2
import numpy as np


def session_options(ort, intra_op_threads: int | None = None):
    """Bound each model's CPU pool; idle sessions must not spin against capture."""
    options = ort.SessionOptions()
    if intra_op_threads is None:
        raw_threads = os.getenv("AI_SENTINEL_ORT_INTRA_OP_THREADS", "2")
        try:
            intra_op_threads = int(raw_threads)
        except ValueError as exc:
            raise ValueError("AI_SENTINEL_ORT_INTRA_OP_THREADS must be an integer") from exc
    if not 1 <= intra_op_threads <= 4:
        raise ValueError("ORT intra-op threads must be between 1 and 4")
    options.intra_op_num_threads = intra_op_threads
    options.inter_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return options


# --- Runtime backend selection (provider/session region) ----------------------
# TensorRT is deliberately absent from the policy: the wheel lists
# TensorrtExecutionProvider but the TRT runtime libraries are not installed on
# this deployment target, and TRT engines bind to ORT/TRT/GPU versions.
PROVIDER_DEVICE_ENV = "AI_SENTINEL_ORT_DEVICE"
CUDA_PROVIDER_OPTIONS = {"use_tf32": "0", "cudnn_conv_algo_search": "HEURISTIC"}
PROVIDER_DEVICES = ("auto", "cpu", "cuda")


def select_providers(ort=None, device: str | None = None) -> list:
    """Return ONNX Runtime providers in priority order (runtime backend selection).

    ``device`` is "auto" | "cpu" | "cuda"; when omitted it is read from the
    ``AI_SENTINEL_ORT_DEVICE`` environment variable and defaults to "auto".

    - "auto": CUDA when the loaded ORT build lists CUDAExecutionProvider, else
      CPU. Deployment stays functional on a CPU-only host without config edits.
    - "cpu": CPU only, even when CUDA is available. This is the verified
      rollback mode and the matched-measurement baseline mode.
    - "cuda": CUDA required. Missing CUDA support is a hard error: a run that
      requested CUDA must never silently measure (or ship) a CPU fallback.

    CUDA runs with the pinned option set (tf32 off for output parity with CPU
    fp32; HEURISTIC conv search to avoid EXHAUSTIVE first-run stalls). A CPU
    provider is always appended so unsupported nodes fall back per node instead
    of failing session creation.
    """
    if device is None:
        device = os.getenv(PROVIDER_DEVICE_ENV, "auto")
    device = str(device).strip().lower() or "auto"
    if device not in PROVIDER_DEVICES:
        raise ValueError(f"{PROVIDER_DEVICE_ENV} must be one of {PROVIDER_DEVICES}, got {device!r}")
    if ort is None:
        try:
            import onnxruntime as ort
        except ImportError:
            return ["CPUExecutionProvider"]
    available = list(ort.get_available_providers())
    if device == "cpu":
        return ["CPUExecutionProvider"]
    cuda_available = "CUDAExecutionProvider" in available
    if device == "cuda" and not cuda_available:
        raise RuntimeError(
            "AI_SENTINEL_ORT_DEVICE=cuda but the loaded ONNX Runtime build does not "
            f"list CUDAExecutionProvider (available: {available})"
        )
    if cuda_available:
        return [("CUDAExecutionProvider", dict(CUDA_PROVIDER_OPTIONS)), "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


@dataclass(frozen=True)
class LetterboxTransform:
    width: int
    height: int
    scale: float
    left: int
    top: int


def model_names(metadata: Mapping[str, str]) -> dict[int, str]:
    """Parse export metadata as data, never executable Python."""
    raw = metadata.get("names", "")
    if not raw or len(raw) > 65536:
        raise ValueError("ONNX class-name metadata missing or too large")
    names = ast.literal_eval(raw)
    if isinstance(names, (list, tuple)):
        names = dict(enumerate(names))
    if not isinstance(names, dict) or not names or len(names) > 10000:
        raise ValueError("Invalid ONNX class-name metadata")
    result = {int(k): str(v).strip().lower() for k, v in names.items()}
    if set(result) != set(range(len(result))) or any(not v for v in result.values()):
        raise ValueError("ONNX class IDs must be contiguous from zero")
    return result


def model_output_format(metadata: Mapping[str, str]) -> str:
    raw_args = metadata.get("args", "{}")
    if len(raw_args) > 65536:
        raise ValueError("ONNX arguments metadata too large")
    args = ast.literal_eval(raw_args)
    if not isinstance(args, dict):
        raise ValueError("Invalid ONNX arguments metadata")
    end2end = str(metadata.get("end2end", "false")).lower() == "true"
    return "post_nms" if args.get("nms") is True or end2end else "raw"


def model_input_size(shape: list) -> tuple[int, int]:
    if len(shape) != 4 or shape[0] not in (1, "batch") or shape[1] != 3:
        raise ValueError("Expected batch-one NCHW RGB ONNX input")
    h, w = shape[2:]
    if not isinstance(h, int) or not isinstance(w, int) or min(h, w) <= 0:
        raise ValueError("A fixed ONNX input size is required")
    return w, h


def prepare_input(frame: np.ndarray, size: tuple[int, int]) -> tuple[np.ndarray, LetterboxTransform]:
    if frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) <= 0:
        raise ValueError("Expected a nonempty BGR frame")
    h, w = frame.shape[:2]
    target_w, target_h = size
    scale = min(target_w / w, target_h / h)
    resized_w, resized_h = round(w * scale), round(h * scale)
    left = (target_w - resized_w) // 2
    top = (target_h - resized_h) // 2
    resized = cv2.resize(frame, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
    padded = cv2.copyMakeBorder(resized, top, target_h - resized_h - top,
                               left, target_w - resized_w - left,
                               cv2.BORDER_CONSTANT, value=(114, 114, 114))
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    tensor = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
    return tensor, LetterboxTransform(w, h, scale, left, top)


def decode_detections(output: np.ndarray, *, num_classes: int,
                      transform: LetterboxTransform, confidence: float,
                      classes: set[int] | None = None, iou_threshold: float = 0.5,
                      output_format: str = "raw", max_detections: int = 300) -> np.ndarray:
    """Return finite clipped source-pixel [x1,y1,x2,y2,score,class] rows.

    Class-aware NMS uses the highest scoring class per raw proposal, matching
    Ultralytics' default single-label behavior. Never infer raw vs post-NMS
    solely from six columns: two-class raw exports also have six channels.
    """
    data = np.asarray(output)
    if data.ndim == 3 and data.shape[0] == 1:
        data = data[0]
    if data.ndim != 2 or num_classes < 1:
        raise ValueError("Expected a batch-one detection tensor")
    if output_format == "raw":
        channels = 4 + num_classes
        if data.shape[0] == channels:
            data = data.T
        elif data.shape[1] != channels:
            raise ValueError("Raw ONNX class count does not match metadata")
        data = data[np.isfinite(data).all(axis=1)]
        scores = data[:, 4:]
        class_ids = scores.argmax(axis=1)
        best = scores[np.arange(len(scores)), class_ids]
        valid = (best >= confidence) & (best <= 1) & (best >= 0)
        valid &= (data[:, 2:4] > 0).all(axis=1)
        data, best, class_ids = data[valid], best[valid], class_ids[valid]
        boxes = np.empty((len(data), 4), dtype=np.float32)
        boxes[:, :2] = data[:, :2] - data[:, 2:4] / 2
        boxes[:, 2:4] = data[:, :2] + data[:, 2:4] / 2
        rows = np.column_stack((boxes, best, class_ids)).astype(np.float32)
    elif output_format == "post_nms":
        if data.shape[1] != 6:
            raise ValueError("Expected post-NMS [N,6] xyxy/score/class rows")
        rows = data.astype(np.float32, copy=True)
    else:
        raise ValueError("Unsupported ONNX output format")
    valid = np.isfinite(rows).all(axis=1)
    valid &= (rows[:, 4] >= confidence) & (rows[:, 4] <= 1) & (rows[:, 4] >= 0)
    valid &= (rows[:, 5] >= 0) & (rows[:, 5] < num_classes) & (rows[:, 5] == np.floor(rows[:, 5]))
    if classes is not None:
        valid &= np.isin(rows[:, 5], list(classes))
    rows = rows[valid]
    rows = rows[(rows[:, 2] > rows[:, 0]) & (rows[:, 3] > rows[:, 1])]
    order = np.argsort(-rows[:, 4], kind="stable")[:30000]
    keep = []
    while order.size and len(keep) < max_detections:
        index = int(order[0])
        keep.append(index)
        rest = order[1:]
        a, b = rows[index], rows[rest]
        inter = np.maximum(0, np.minimum(a[2:4], b[:, 2:4]) - np.maximum(a[:2], b[:, :2])).prod(axis=1)
        union = (a[2] - a[0]) * (a[3] - a[1]) + (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) - inter
        iou = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
        order = rest[(b[:, 5] != a[5]) | (iou <= iou_threshold)]
    # Suppress in model coordinates before clipping: border clipping changes IoU.
    rows = rows[keep]
    rows[:, [0, 2]] = np.clip((rows[:, [0, 2]] - transform.left) / transform.scale, 0, transform.width)
    rows[:, [1, 3]] = np.clip((rows[:, [1, 3]] - transform.top) / transform.scale, 0, transform.height)
    return rows[(rows[:, 2] > rows[:, 0]) & (rows[:, 3] > rows[:, 1])]
