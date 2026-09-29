"""Gate violence inference candidates against legacy FP32 outputs on demo AVIs."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import statistics
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import cv2
import numpy as np
import torch
import torch.nn.functional as F

cv2.setNumThreads(1)
torch.set_num_threads(2)
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass

from decision_config import load_decision_config
from inference import (
    MEAN,
    STD,
    VIOLENCE_CLS,
    WINDOW_SIZE,
    SLOWFAST_PREPROCESS_WORKERS,
    ViolenceInferencePipeline,
    cached_resize,
    ensure_bgr,
    preprocess_slowfast_window,
)

VIDEO_DIR = ROOT / "demo_assets" / "videos"
WINDOW_STEP = 8
PROBABILITY_TOLERANCE = 0.01
CANDIDATES = (
    "baseline",
    "inference_mode",
    "cudnn_benchmark",
    "channels_last_3d",
    "pinned_non_blocking",
    "fp16_autocast",
    "warmup",
    "combined_fp32",
    "combined_fp16",
    "combined_fp16_warmup",
    "fp16_channels_last",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _legacy_preprocess(frames: list[np.ndarray]) -> torch.Tensor:
    processed = []
    for frame in frames:
        frame = ensure_bgr(frame)
        image = cached_resize(frame, 224)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        processed.append((image - MEAN) / STD)
    tensor = np.stack(processed).transpose(0, 3, 1, 2)
    return torch.from_numpy(tensor).unsqueeze(0)


def _sync(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def _channels_last_3d_input(tensor: torch.Tensor) -> torch.Tensor:
    """Keep the model's N,T,C,H,W API while laying out its N,C,T,H,W view."""
    return tensor.permute(0, 2, 1, 3, 4).contiguous(
        memory_format=torch.channels_last_3d
    ).permute(0, 2, 1, 3, 4)


def _candidate_flags(candidate: str) -> dict[str, bool]:
    combined = candidate in {"combined_fp32", "combined_fp16", "combined_fp16_warmup"}
    return {
        "cudnn_benchmark": candidate == "cudnn_benchmark" or combined,
        "channels_last_3d": candidate == "channels_last_3d" or combined or candidate == "fp16_channels_last",
        "pinned_non_blocking": candidate == "pinned_non_blocking" or combined,
        "fp16_autocast": candidate == "fp16_autocast" or candidate in {
            "combined_fp16", "combined_fp16_warmup", "fp16_channels_last"
        },
    }


def _probability(
    model: torch.nn.Module,
    tensor: torch.Tensor,
    device: torch.device,
    candidate: str,
) -> tuple[float, float]:
    use_cuda = device.type == "cuda"
    flags = _candidate_flags(candidate)
    cudnn_benchmark = torch.backends.cudnn.benchmark
    if use_cuda and flags["cudnn_benchmark"]:
        torch.backends.cudnn.benchmark = True
    try:
        started = time.perf_counter()
        source = tensor
        non_blocking = use_cuda and flags["pinned_non_blocking"]
        if non_blocking:
            source = source.pin_memory()
        fast = source.to(device, non_blocking=non_blocking)
        if use_cuda and flags["channels_last_3d"]:
            fast = _channels_last_3d_input(fast)
        slow = fast[:, ::4, :, :, :]
        if use_cuda and flags["channels_last_3d"]:
            slow = _channels_last_3d_input(slow)

        inference_context = torch.no_grad if candidate == "baseline" else torch.inference_mode
        with inference_context():
            if use_cuda and flags["fp16_autocast"]:
                with torch.autocast("cuda", dtype=torch.float16):
                    logits = model(slow, fast)
            else:
                logits = model(slow, fast)
            probability = float(F.softmax(logits.float(), dim=-1)[0, VIOLENCE_CLS].item())
        _sync(device)
        return probability, (time.perf_counter() - started) * 1000
    finally:
        if use_cuda and flags["cudnn_benchmark"]:
            torch.backends.cudnn.benchmark = cudnn_benchmark


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "p50_ms": None, "p95_ms": None}
    return {
        "count": len(values),
        "p50_ms": round(statistics.median(values), 4),
        "p95_ms": round(float(np.percentile(values, 95)), 4),
    }


def run(output: Path, candidate: str = "baseline") -> dict:
    if candidate not in CANDIDATES:
        raise ValueError(f"Unknown candidate: {candidate}")
    videos = sorted(VIDEO_DIR.glob("*.avi"))
    if not videos:
        raise FileNotFoundError(f"No AVI files found under {VIDEO_DIR}")

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    weights = BACKEND / "best_model.pt"
    threshold = load_decision_config().violence_threshold
    load_started = time.perf_counter()
    pipeline = ViolenceInferencePipeline(
        str(weights), device, threshold=threshold, stride=WINDOW_STEP
    )
    load_ms = (time.perf_counter() - load_started) * 1000
    if not pipeline.enabled or pipeline.model is None:
        raise RuntimeError(f"Violence model unavailable: {pipeline.disabled_reason}")

    reference_model = pipeline.model.eval()
    candidate_model = copy.deepcopy(reference_model).eval()
    flags = _candidate_flags(candidate)
    if device.type == "cuda" and flags["channels_last_3d"]:
        candidate_model.to(memory_format=torch.channels_last_3d)

    candidate_warmup_ms = None
    if candidate in {"warmup", "combined_fp16_warmup"}:
        warmup_fast = torch.zeros((1, WINDOW_SIZE, 3, 224, 224), dtype=torch.float32)
        _, candidate_warmup_ms = _probability(candidate_model, warmup_fast, device, candidate)

    reference_inference_ms: list[float] = []
    candidate_inference_ms: list[float] = []
    reference_preprocess_ms: list[float] = []
    parallel_preprocess_ms: list[float] = []
    all_deltas: list[float] = []
    comparisons: list[tuple[float, float]] = []
    max_input_delta = 0.0
    video_records = []

    try:
        for video in videos:
            capture = cv2.VideoCapture(str(video))
            if not capture.isOpened():
                raise RuntimeError(f"Could not open demo AVI: {video}")
            rolling: deque[np.ndarray] = deque(maxlen=WINDOW_SIZE)
            frame_count = 0
            video_comparisons: list[tuple[float, float]] = []
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                frame_count += 1
                rolling.append(frame)
                if len(rolling) != WINDOW_SIZE or (frame_count - WINDOW_SIZE) % WINDOW_STEP:
                    continue

                frames = list(rolling)
                started = time.perf_counter()
                reference = _legacy_preprocess(frames)
                reference_preprocess_ms.append((time.perf_counter() - started) * 1000)
                started = time.perf_counter()
                parallel = preprocess_slowfast_window(frames)
                parallel_preprocess_ms.append((time.perf_counter() - started) * 1000)
                max_input_delta = max(
                    max_input_delta,
                    float(np.max(np.abs(reference.numpy() - parallel.numpy()))),
                )

                reference_prob, reference_ms = _probability(
                    reference_model, reference, device, "baseline"
                )
                candidate_prob, candidate_ms = _probability(
                    candidate_model, parallel, device, candidate
                )
                reference_inference_ms.append(reference_ms)
                candidate_inference_ms.append(candidate_ms)
                comparisons.append((reference_prob, candidate_prob))
                video_comparisons.append((reference_prob, candidate_prob))

            capture.release()
            deltas = [abs(ref - cand) for ref, cand in video_comparisons]
            mismatches = sum(
                (ref >= threshold) != (cand >= threshold)
                for ref, cand in video_comparisons
            )
            video_records.append({
                "path": str(video.relative_to(ROOT)).replace("\\", "/"),
                "sha256": _sha256(video),
                "frames": frame_count,
                "windows": len(video_comparisons),
                "max_probability_absolute_delta": max(deltas, default=0.0),
                "threshold_decision_mismatches": mismatches,
            })
    finally:
        pipeline._inference_executor.shutdown(wait=True)

    if not comparisons:
        raise RuntimeError("No full violence windows were decoded from the demo AVIs")
    deltas = [abs(reference - candidate_prob) for reference, candidate_prob in comparisons]
    decisions_differ = [
        index for index, (reference, candidate_prob) in enumerate(comparisons)
        if (reference >= threshold) != (candidate_prob >= threshold)
    ]
    result = {
        "passed": max(deltas, default=0.0) <= PROBABILITY_TOLERANCE and not decisions_differ,
        "candidate": candidate,
        "device": str(device),
        "model_class": type(reference_model).__name__,
        "weights_sha256": _sha256(weights),
        "threshold": threshold,
        "violence_class_index": VIOLENCE_CLS,
        "probability_tolerance": PROBABILITY_TOLERANCE,
        "videos": video_records,
        "windows_compared": len(comparisons),
        "max_input_absolute_delta": max_input_delta,
        "max_probability_absolute_delta": max(deltas, default=0.0),
        "p95_probability_absolute_delta": round(float(np.percentile(deltas, 95)), 8),
        "threshold_decision_mismatches": len(decisions_differ),
        "preprocess_latency_ms": {
            "legacy": _distribution(reference_preprocess_ms),
            f"parallel_{SLOWFAST_PREPROCESS_WORKERS}_worker": _distribution(parallel_preprocess_ms),
        },
        "inference_latency_ms": {
            "reference_fp32": _distribution(reference_inference_ms),
            "candidate": _distribution(candidate_inference_ms),
        },
        "candidate_warmup_ms": round(candidate_warmup_ms, 4) if candidate_warmup_ms is not None else None,
        "model_load_ms": round(load_ms, 2),
        "method": (
            "All full 32-frame windows sampled every 8 frames from every AVI in "
            "demo_assets/videos. Candidate outputs are compared with separate "
            "legacy FP32 model outputs; every AVI reports its own max probability "
            "delta and threshold-decision mismatch count."
        ),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if not result["passed"]:
        raise AssertionError("Violence probability or threshold decision parity failed")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", choices=CANDIDATES, default="baseline")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "bench" / "results" / "perf-violence-parity-2026-09-26",
    )
    args = parser.parse_args()
    print(json.dumps(run(args.output.resolve(), candidate=args.candidate), indent=2))


if __name__ == "__main__":
    main()
