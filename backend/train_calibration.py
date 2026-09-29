from __future__ import annotations

import argparse
import json
import math
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import torch
import torch.nn.functional as F

try:
    from .calibration_utils import resolve_calibration_path
    from .inference import (
        ViolenceInferencePipeline,
        WINDOW_SIZE,
        ensure_bgr,
        preprocess_window,
    )
except ImportError:
    from calibration_utils import resolve_calibration_path
    from inference import (
        ViolenceInferencePipeline,
        WINDOW_SIZE,
        ensure_bgr,
        preprocess_window,
    )


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_ZIP = ROOT_DIR / "val-20260418T185437Z-3-001.zip"
DEFAULT_WEIGHTS = BACKEND_DIR / "best_model.pt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train confidence calibration for the violence model.")
    parser.add_argument("--dataset-zip", default=str(DEFAULT_DATASET_ZIP))
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS))
    parser.add_argument("--output", default=str(resolve_calibration_path(base_dir=BACKEND_DIR)))
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--max-videos", type=int, default=0)
    parser.add_argument("--steps", type=int, default=250)
    parser.add_argument("--lr", type=float, default=0.05)
    return parser.parse_args()


def load_pipeline(weights_path: Path, device: torch.device) -> ViolenceInferencePipeline:
    pipeline = ViolenceInferencePipeline(str(weights_path), device, threshold=0.5, stride=16)
    if not pipeline.enabled or pipeline.model is None:
        raise RuntimeError(f"Unable to load training pipeline from {weights_path}")
    pipeline.model.eval()
    return pipeline


def iter_zip_examples(zip_path: Path, max_videos: int = 0) -> Iterable[tuple[str, int, bytes]]:
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".avi")]
        yielded = 0
        for name in names:
            label = 1 if "/violence/" in name.replace("\\", "/").lower() else 0
            with archive.open(name, "r") as handle:
                yield name, label, handle.read()
            yielded += 1
            if max_videos > 0 and yielded >= max_videos:
                return


def iter_test_positives(test_dir: Path, seen_names: set[str]) -> Iterable[tuple[str, int, bytes]]:
    if not test_dir.exists():
        return
    for path in sorted(test_dir.glob("*.avi")):
        basename = path.name.lower()
        if basename in seen_names:
            continue
        yield f"test/violence/{path.name}", 1, path.read_bytes()


def sample_frames(video_bytes: bytes, suffix: str = ".avi") -> list[np.ndarray] | None:
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(video_bytes)
            tmp_path = Path(tmp.name)

        cap = cv2.VideoCapture(str(tmp_path))
        if not cap.isOpened():
            return None

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total_frames <= 0:
            cap.release()
            return None

        indices = np.linspace(0, max(0, total_frames - 1), WINDOW_SIZE).astype(np.int32)
        frames: list[np.ndarray] = []
        for index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frames.append(ensure_bgr(frame))

        cap.release()
        if len(frames) < WINDOW_SIZE:
            return None
        return frames[:WINDOW_SIZE]
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def infer_logits(pipeline: ViolenceInferencePipeline, frames: list[np.ndarray]) -> torch.Tensor:
    with torch.inference_mode():
        if pipeline.is_x3d:
            inputs = preprocess_window(frames).to(pipeline.device)
            return pipeline.model(inputs).cpu()[0]

        processed = []
        for frame in frames:
            image = cv2.resize(frame, (224, 224))
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            processed.append((image - np.array([0.45, 0.45, 0.45], dtype=np.float32)) / np.array([0.225, 0.225, 0.225], dtype=np.float32))
        fast = torch.from_numpy(np.stack(processed).transpose(0, 3, 1, 2)).unsqueeze(0).to(pipeline.device)
        slow = fast[:, ::4, :, :, :]
        return pipeline.model(slow, fast).cpu()[0]


def build_dataset(zip_path: Path, pipeline: ViolenceInferencePipeline, max_videos: int = 0) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    seen_names: set[str] = set()
    logits_rows: list[np.ndarray] = []
    labels: list[int] = []
    counts: Counter[str] = Counter()

    for name, label, video_bytes in iter_zip_examples(zip_path, max_videos=max_videos):
        frames = sample_frames(video_bytes)
        if frames is None:
            continue
        logits = infer_logits(pipeline, frames).numpy()
        logits_rows.append(logits.astype(np.float32))
        labels.append(label)
        counts["zip_total"] += 1
        counts["zip_violence" if label == 1 else "zip_non_violence"] += 1
        seen_names.add(Path(name).name.lower())

    for name, label, video_bytes in iter_test_positives(ROOT_DIR / "test", seen_names):
        frames = sample_frames(video_bytes)
        if frames is None:
            continue
        logits = infer_logits(pipeline, frames).numpy()
        logits_rows.append(logits.astype(np.float32))
        labels.append(label)
        counts["test_total"] += 1
        counts["test_violence"] += 1

    if not logits_rows:
        raise RuntimeError("No usable video samples were found for calibration.")

    counts["samples"] = len(labels)
    counts["violence"] = int(sum(labels))
    counts["non_violence"] = int(len(labels) - sum(labels))
    return np.stack(logits_rows), np.asarray(labels, dtype=np.float32), dict(counts)


def optimize_calibration(margins: torch.Tensor, labels: torch.Tensor, steps: int, lr: float) -> tuple[float, float]:
    log_temp = torch.nn.Parameter(torch.tensor(math.log(math.exp(1.0) - 1.0), dtype=torch.float32))
    bias = torch.nn.Parameter(torch.tensor(0.0, dtype=torch.float32))
    optimizer = torch.optim.Adam([log_temp, bias], lr=lr)

    for _ in range(steps):
        temp = F.softplus(log_temp) + 1e-4
        calibrated_logits = (margins + bias) / temp
        loss = F.binary_cross_entropy_with_logits(calibrated_logits, labels)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

    final_temp = float((F.softplus(log_temp) + 1e-4).item())
    final_bias = float(bias.item())
    return final_temp, final_bias


def compute_metrics(probabilities: np.ndarray, labels: np.ndarray, threshold: float) -> dict[str, float]:
    predictions = (probabilities >= threshold).astype(np.int32)
    truth = labels.astype(np.int32)

    tp = int(np.sum((predictions == 1) & (truth == 1)))
    tn = int(np.sum((predictions == 0) & (truth == 0)))
    fp = int(np.sum((predictions == 1) & (truth == 0)))
    fn = int(np.sum((predictions == 0) & (truth == 1)))

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    specificity = tn / max(1, tn + fp)
    accuracy = (tp + tn) / max(1, len(truth))
    f1 = (2 * precision * recall) / max(1e-8, precision + recall)
    balanced_accuracy = (recall + specificity) / 2.0

    return {
        "threshold": round(float(threshold), 4),
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "specificity": round(float(specificity), 4),
        "f1": round(float(f1), 4),
        "balancedAccuracy": round(float(balanced_accuracy), 4),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def select_threshold(probabilities: np.ndarray, labels: np.ndarray) -> tuple[float, dict[str, float]]:
    best_threshold = 0.5
    best_metrics = compute_metrics(probabilities, labels, best_threshold)
    best_score = float(best_metrics["f1"]) + float(best_metrics["balancedAccuracy"])

    for threshold in np.linspace(0.15, 0.85, 71):
        metrics = compute_metrics(probabilities, labels, float(threshold))
        score = float(metrics["f1"]) + float(metrics["balancedAccuracy"])
        if score > best_score:
            best_score = score
            best_threshold = float(threshold)
            best_metrics = metrics

    return best_threshold, best_metrics


def evaluate_candidate(logits: np.ndarray, labels: np.ndarray, class_index: int, steps: int, lr: float) -> dict[str, float | int]:
    logits_tensor = torch.from_numpy(logits)
    labels_tensor = torch.from_numpy(labels)
    other_index = 1 - class_index
    margins = logits_tensor[:, class_index] - logits_tensor[:, other_index]

    base_probs = torch.sigmoid(margins).numpy()
    _, base_metrics = select_threshold(base_probs, labels)

    temp, bias = optimize_calibration(margins, labels_tensor, steps=steps, lr=lr)
    calibrated_probs = torch.sigmoid((margins + bias) / temp).numpy()
    threshold, metrics = select_threshold(calibrated_probs, labels)

    return {
        "classIndex": class_index,
        "logitTemperature": round(temp, 6),
        "logitBias": round(bias, 6),
        "threshold": round(threshold, 6),
        "baselineF1": float(base_metrics["f1"]),
        "baselineBalancedAccuracy": float(base_metrics["balancedAccuracy"]),
        "f1": float(metrics["f1"]),
        "balancedAccuracy": float(metrics["balancedAccuracy"]),
        "accuracy": float(metrics["accuracy"]),
        "precision": float(metrics["precision"]),
        "recall": float(metrics["recall"]),
        "specificity": float(metrics["specificity"]),
        "tp": int(metrics["tp"]),
        "tn": int(metrics["tn"]),
        "fp": int(metrics["fp"]),
        "fn": int(metrics["fn"]),
    }


def main() -> None:
    args = parse_args()
    dataset_zip = Path(args.dataset_zip).resolve()
    weights_path = Path(args.weights).resolve()
    output_path = Path(args.output).resolve()
    device = torch.device(args.device)

    if not dataset_zip.exists():
        raise FileNotFoundError(f"Dataset zip not found: {dataset_zip}")
    if not weights_path.exists():
        raise FileNotFoundError(f"Weights file not found: {weights_path}")

    print(f"[Calibration] Loading model from {weights_path}")
    pipeline = load_pipeline(weights_path=weights_path, device=device)

    print(f"[Calibration] Building dataset from {dataset_zip}")
    logits, labels, counts = build_dataset(dataset_zip, pipeline, max_videos=args.max_videos)
    print(f"[Calibration] Samples: {counts}")

    candidates = [
        evaluate_candidate(logits, labels, class_index=0, steps=args.steps, lr=args.lr),
        evaluate_candidate(logits, labels, class_index=1, steps=args.steps, lr=args.lr),
    ]
    best = max(candidates, key=lambda item: (float(item["f1"]) + float(item["balancedAccuracy"]), float(item["accuracy"])))

    payload = {
        "trainedAt": datetime.now(timezone.utc).isoformat(),
        "datasetZip": str(dataset_zip),
        "weightsPath": str(weights_path),
        "samples": counts,
        "classIndex": int(best["classIndex"]),
        "logitTemperature": float(best["logitTemperature"]),
        "logitBias": float(best["logitBias"]),
        "threshold": float(best["threshold"]),
        "emaAlpha": 0.45,
        "hysteresisMargin": 0.08,
        "metrics": {
            "f1": float(best["f1"]),
            "balancedAccuracy": float(best["balancedAccuracy"]),
            "accuracy": float(best["accuracy"]),
            "precision": float(best["precision"]),
            "recall": float(best["recall"]),
            "specificity": float(best["specificity"]),
            "tp": int(best["tp"]),
            "tn": int(best["tn"]),
            "fp": int(best["fp"]),
            "fn": int(best["fn"]),
            "baselineF1": float(best["baselineF1"]),
            "baselineBalancedAccuracy": float(best["baselineBalancedAccuracy"]),
        },
        "candidates": candidates,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    print(f"[Calibration] Best candidate: {json.dumps(best, indent=2)}")
    print(f"[Calibration] Saved calibration to {output_path}")


if __name__ == "__main__":
    main()
