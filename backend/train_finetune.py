from __future__ import annotations

import argparse
import json
import random
import shutil
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, Dataset

try:
    from .inference import ViolenceDetector, ensure_bgr
except ImportError:
    from inference import ViolenceDetector, ensure_bgr


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_ZIP = ROOT_DIR / "val-20260418T185437Z-3-001.zip"
DEFAULT_WEIGHTS = BACKEND_DIR / "best_model.pt"
MEAN = np.array([0.45, 0.45, 0.45], dtype=np.float32)
STD = np.array([0.225, 0.225, 0.225], dtype=np.float32)
WINDOW_SIZE = 32
FRAME_SIZE = 224


@dataclass(frozen=True)
class VideoSample:
    path: Path
    label: int
    source: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune the violence detection head on Colab/GPU.")
    parser.add_argument("--sources", nargs="+", default=[str(DEFAULT_DATASET_ZIP)], help="Zip files or directories containing violence/non-violence videos.")
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="Initial checkpoint path.")
    parser.add_argument("--output", default=str(BACKEND_DIR / "best_model_finetuned.pt"), help="Where to save the best checkpoint.")
    parser.add_argument("--cache-dir", default=str(BACKEND_DIR / "training_cache"), help="Where zip inputs are extracted.")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--include-test-positives", action="store_true")
    parser.add_argument("--unfreeze-backbone", action="store_true")
    return parser.parse_args()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def extract_zip(source: Path, cache_dir: Path) -> Path:
    target = cache_dir / source.stem
    marker = target / ".complete"
    if marker.exists():
        return target

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source) as archive:
        archive.extractall(target)

    marker.write_text("ok", encoding="utf-8")
    return target


def discover_videos(root: Path) -> list[VideoSample]:
    samples: list[VideoSample] = []
    for video_path in root.rglob("*.avi"):
        normalized = video_path.as_posix().lower()
        if "/violence/" in normalized:
            samples.append(VideoSample(path=video_path, label=1, source=str(root)))
        elif "/non-violence/" in normalized or "/non_violence/" in normalized:
            samples.append(VideoSample(path=video_path, label=0, source=str(root)))
    return samples


def load_sources(raw_sources: list[str], cache_dir: Path, include_test_positives: bool) -> list[VideoSample]:
    samples: list[VideoSample] = []
    seen_paths: set[str] = set()

    for raw_source in raw_sources:
        source = Path(raw_source).resolve()
        if not source.exists():
            raise FileNotFoundError(f"Training source not found: {source}")

        if source.is_file() and source.suffix.lower() == ".zip":
            root = extract_zip(source, cache_dir)
        else:
            root = source

        for sample in discover_videos(root):
            key = str(sample.path.resolve()).lower()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            samples.append(sample)

    if include_test_positives:
        for path in sorted((ROOT_DIR / "test").glob("*.avi")):
            key = str(path.resolve()).lower()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            samples.append(VideoSample(path=path.resolve(), label=1, source="test"))

    return samples


def stratified_split(samples: list[VideoSample], val_ratio: float, seed: int) -> tuple[list[VideoSample], list[VideoSample]]:
    positives = [sample for sample in samples if sample.label == 1]
    negatives = [sample for sample in samples if sample.label == 0]
    rng = random.Random(seed)
    rng.shuffle(positives)
    rng.shuffle(negatives)

    def split_class(items: list[VideoSample]) -> tuple[list[VideoSample], list[VideoSample]]:
        if not items:
            return [], []
        val_count = max(1, int(round(len(items) * val_ratio))) if len(items) > 2 else 1
        val_count = min(val_count, max(1, len(items) - 1))
        return items[val_count:], items[:val_count]

    train_pos, val_pos = split_class(positives)
    train_neg, val_neg = split_class(negatives)
    train = train_pos + train_neg
    val = val_pos + val_neg
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def load_frames(video_path: Path, training: bool) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total_frames <= 0:
        cap.release()
        raise RuntimeError(f"Video has no frames: {video_path}")

    if training and total_frames > WINDOW_SIZE:
        max_start = max(0, total_frames - WINDOW_SIZE)
        start = random.randint(0, max_start)
        indices = np.linspace(start, start + WINDOW_SIZE - 1, WINDOW_SIZE).astype(np.int32)
    else:
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
        raise RuntimeError(f"Insufficient frames in video: {video_path}")
    return frames[:WINDOW_SIZE]


def preprocess_frames(frames: list[np.ndarray], training: bool) -> np.ndarray:
    processed: list[np.ndarray] = []
    flip = training and random.random() < 0.5
    crop_shift = random.randint(0, 10) if training else 5
    brightness = random.uniform(0.92, 1.08) if training else 1.0

    for frame in frames:
        image = cv2.resize(frame, (234, 234), interpolation=cv2.INTER_LINEAR)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = image[crop_shift:crop_shift + FRAME_SIZE, crop_shift:crop_shift + FRAME_SIZE]
        if flip:
            image = np.ascontiguousarray(image[:, ::-1, :])
        image = np.clip(image.astype(np.float32) * brightness, 0.0, 255.0) / 255.0
        image = (image - MEAN) / STD
        processed.append(image)

    return np.stack(processed, axis=0).astype(np.float32)


class ViolenceVideoDataset(Dataset):
    def __init__(self, samples: list[VideoSample], training: bool):
        self.samples = samples
        self.training = training

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        sample = self.samples[index]
        frames = load_frames(sample.path, training=self.training)
        clip = preprocess_frames(frames, training=self.training)
        # Keep the clip in (time, channel, height, width) so the SlowFast
        # backbone receives the expected channel-first layout after batching.
        fast = torch.from_numpy(clip).permute(0, 3, 1, 2).contiguous()
        slow = fast[::4]
        label = torch.tensor(sample.label, dtype=torch.long)
        return slow, fast, label


def collate_batch(batch: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    slow = torch.stack([item[0] for item in batch], dim=0)
    fast = torch.stack([item[1] for item in batch], dim=0)
    labels = torch.stack([item[2] for item in batch], dim=0)
    return slow, fast, labels


def load_model(weights_path: Path, device: torch.device, unfreeze_backbone: bool) -> nn.Module:
    model = ViolenceDetector(num_classes=2).to(device)
    checkpoint = torch.load(weights_path, map_location=device)
    state_dict = checkpoint["model_state_dict"] if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint else checkpoint
    model.load_state_dict(state_dict)

    if not unfreeze_backbone:
        for parameter in model.sf.parameters():
            parameter.requires_grad = False

    model.train()
    return model


def compute_metrics(logits: torch.Tensor, labels: torch.Tensor) -> dict[str, float]:
    predictions = torch.argmax(logits, dim=1)
    truth = labels
    tp = int(((predictions == 1) & (truth == 1)).sum().item())
    tn = int(((predictions == 0) & (truth == 0)).sum().item())
    fp = int(((predictions == 1) & (truth == 0)).sum().item())
    fn = int(((predictions == 0) & (truth == 1)).sum().item())

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    specificity = tn / max(1, tn + fp)
    accuracy = (tp + tn) / max(1, tp + tn + fp + fn)
    f1 = (2 * precision * recall) / max(1e-8, precision + recall)
    balanced_accuracy = (recall + specificity) / 2.0

    return {
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


def run_epoch(model: nn.Module, loader: DataLoader, device: torch.device, optimizer: torch.optim.Optimizer | None = None) -> tuple[float, dict[str, float]]:
    training = optimizer is not None
    total_loss = 0.0
    total_items = 0
    collected_logits: list[torch.Tensor] = []
    collected_labels: list[torch.Tensor] = []

    model.train(training)
    context = torch.enable_grad() if training else torch.inference_mode()
    with context:
        for slow, fast, labels in loader:
            slow = slow.to(device)
            fast = fast.to(device)
            labels = labels.to(device)
            logits = model(slow, fast)
            loss = F.cross_entropy(logits, labels)

            if training:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            batch_size = labels.shape[0]
            total_loss += float(loss.item()) * batch_size
            total_items += batch_size
            collected_logits.append(logits.detach().cpu())
            collected_labels.append(labels.detach().cpu())

    merged_logits = torch.cat(collected_logits, dim=0)
    merged_labels = torch.cat(collected_labels, dim=0)
    metrics = compute_metrics(merged_logits, merged_labels)
    avg_loss = total_loss / max(1, total_items)
    return avg_loss, metrics


def main() -> None:
    args = parse_args()
    seed_everything(args.seed)

    cache_dir = Path(args.cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    samples = load_sources(args.sources, cache_dir=cache_dir, include_test_positives=args.include_test_positives)
    if args.max_samples > 0:
        samples = samples[: args.max_samples]
    if len(samples) < 8:
        raise RuntimeError("Not enough samples found for fine-tuning.")

    train_samples, val_samples = stratified_split(samples, val_ratio=args.val_ratio, seed=args.seed)
    print(f"[Train] Total samples: {len(samples)}")
    print(f"[Train] Train/Val: {len(train_samples)}/{len(val_samples)}")
    print(f"[Train] Class distribution: {Counter(sample.label for sample in samples)}")

    train_loader = DataLoader(
        ViolenceVideoDataset(train_samples, training=True),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=torch.cuda.is_available(),
        collate_fn=collate_batch,
    )
    val_loader = DataLoader(
        ViolenceVideoDataset(val_samples, training=False),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=max(1, args.num_workers // 2),
        pin_memory=torch.cuda.is_available(),
        collate_fn=collate_batch,
    )

    device = torch.device(args.device)
    weights_path = Path(args.weights).resolve()
    output_path = Path(args.output).resolve()

    model = load_model(weights_path=weights_path, device=device, unfreeze_backbone=args.unfreeze_backbone)
    trainable_parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable_parameters, lr=args.lr, weight_decay=args.weight_decay)

    best_score = -1.0
    history: list[dict[str, float | int]] = []
    best_snapshot: dict[str, object] | None = None

    for epoch in range(1, args.epochs + 1):
        train_loss, train_metrics = run_epoch(model, train_loader, device, optimizer=optimizer)
        val_loss, val_metrics = run_epoch(model, val_loader, device, optimizer=None)
        score = float(val_metrics["f1"]) + float(val_metrics["balancedAccuracy"])

        summary = {
            "epoch": epoch,
            "trainLoss": round(train_loss, 4),
            "valLoss": round(val_loss, 4),
            "trainF1": train_metrics["f1"],
            "valF1": val_metrics["f1"],
            "valBalancedAccuracy": val_metrics["balancedAccuracy"],
            "valAccuracy": val_metrics["accuracy"],
        }
        history.append(summary)
        print(f"[Train] {json.dumps(summary)}")

        if score > best_score:
            best_score = score
            best_snapshot = {
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "best_loss": float(val_loss),
                "best_f1": float(val_metrics["f1"]),
                "best_balanced_accuracy": float(val_metrics["balancedAccuracy"]),
                "metrics": val_metrics,
                "history": history,
                "trainArgs": vars(args),
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(best_snapshot, output_path)
            print(f"[Train] Saved improved checkpoint to {output_path}")

    if best_snapshot is None:
        raise RuntimeError("Training did not produce a checkpoint.")

    print("[Train] Final best metrics:")
    print(json.dumps(best_snapshot["metrics"], indent=2))


if __name__ == "__main__":
    main()
