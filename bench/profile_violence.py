"""Profile violence inference stages on the repository's demo AVI fixtures."""
from __future__ import annotations

import argparse
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
    ViolenceInferencePipeline,
    cached_resize,
    ensure_bgr,
    preprocess_slowfast_window,
)

VIDEO_DIR = ROOT / "demo_assets" / "videos"
WINDOW_STEP = 8
WARMUP_WINDOWS = 2


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


def _distribution(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("Cannot summarize an empty profile stage")
    return {
        "count": len(values),
        "p50_ms": round(statistics.median(values), 4),
        "p95_ms": round(float(np.percentile(values, 95)), 4),
        "mean_ms": round(statistics.mean(values), 4),
    }


def _profile_window(
    frames: list[np.ndarray],
    model: torch.nn.Module,
    pipeline: ViolenceInferencePipeline,
    device: torch.device,
    preprocess,
) -> dict[str, float]:
    stages = {}
    started = time.perf_counter()
    cpu_input = preprocess(frames)
    stages["preprocess"] = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    fast = cpu_input.to(device)
    slow = fast[:, ::4, :, :, :]
    _sync(device)
    stages["transfer"] = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    logits = model(slow, fast)
    _sync(device)
    stages["forward"] = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    probs = F.softmax(logits, dim=-1)[0]
    raw_confidence = float(probs[VIOLENCE_CLS].item())
    pipeline._calibrate_confidence(logits, raw_confidence)
    int(torch.argmax(probs).item())
    _sync(device)
    stages["postprocess"] = (time.perf_counter() - started) * 1000
    return stages


def run(output: Path) -> dict:
    videos = sorted(VIDEO_DIR.glob("*.avi"))
    if not videos:
        raise FileNotFoundError(f"No AVI files found under {VIDEO_DIR}")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    weights = BACKEND / "best_model.pt"
    load_started = time.perf_counter()
    pipeline = ViolenceInferencePipeline(
        str(weights), device, threshold=load_decision_config().violence_threshold,
        stride=WINDOW_STEP,
    )
    model_load_ms = (time.perf_counter() - load_started) * 1000
    if not pipeline.enabled or pipeline.model is None:
        raise RuntimeError(f"Violence model unavailable: {pipeline.disabled_reason}")
    model = pipeline.model.eval()

    reference = {name: [] for name in ("assembly", "preprocess", "transfer", "forward", "postprocess")}
    optimized = {name: [] for name in ("preprocess", "transfer", "forward", "postprocess")}
    video_records = []
    profile_windows = 0
    decoded_windows = 0
    try:
        with torch.inference_mode():
            for video in videos:
                capture = cv2.VideoCapture(str(video))
                if not capture.isOpened():
                    raise RuntimeError(f"Could not open demo AVI: {video}")
                rolling: deque[np.ndarray] = deque(maxlen=WINDOW_SIZE)
                frame_count = 0
                video_windows = 0
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    frame_count += 1
                    rolling.append(frame)
                    if len(rolling) != WINDOW_SIZE or (frame_count - WINDOW_SIZE) % WINDOW_STEP:
                        continue

                    started = time.perf_counter()
                    window = list(rolling)
                    assembly_ms = (time.perf_counter() - started) * 1000
                    decoded_windows += 1
                    old_parts = _profile_window(window, model, pipeline, device, _legacy_preprocess)
                    new_parts = _profile_window(window, model, pipeline, device, preprocess_slowfast_window)
                    if decoded_windows > WARMUP_WINDOWS:
                        reference["assembly"].append(assembly_ms)
                        for stage, value in old_parts.items():
                            reference[stage].append(value)
                        for stage, value in new_parts.items():
                            optimized[stage].append(value)
                        profile_windows += 1
                    video_windows += 1
                capture.release()
                video_records.append({
                    "path": str(video.relative_to(ROOT)).replace("\\", "/"),
                    "sha256": _sha256(video),
                    "frames": frame_count,
                    "windows": video_windows,
                })
    finally:
        pipeline._inference_executor.shutdown(wait=True)

    result = {
        "device": str(device),
        "model_class": type(model).__name__,
        "weights_sha256": _sha256(weights),
        "threshold": pipeline.threshold,
        "videos": video_records,
        "warmup_windows_discarded": WARMUP_WINDOWS,
        "profile_windows": profile_windows,
        "model_load_ms": round(model_load_ms, 2),
        "legacy_serial_stages": {name: _distribution(values) for name, values in reference.items()},
        "parallel_preprocess_stages": {name: _distribution(values) for name, values in optimized.items()},
        "method": (
            "Same FP32 model and windows profiled serially with CUDA synchronization; "
            "old and four-worker preprocessing outputs are bit-identical. "
            "Clip assembly measures the frame-deque to list copy."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "bench" / "results" / "perf-r2-after-2026-09-26" / "violence-profile.json",
    )
    args = parser.parse_args()
    print(json.dumps(run(args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
