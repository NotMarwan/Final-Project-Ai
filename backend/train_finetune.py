from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, Dataset

try:
    from .datasets.manifest_dataset import ManifestDataset
    from .inference import ViolenceDetector, ensure_bgr
except ImportError:
    from datasets.manifest_dataset import ManifestDataset
    from inference import ViolenceDetector, ensure_bgr


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = BACKEND_DIR / "best_model.pt"
DEFAULT_CACHE_DIR = ROOT_DIR / ".runlogs" / "training" / "cache"
LOCAL_OUTPUT_ROOT = ROOT_DIR / ".runlogs" / "training"
COLAB_OUTPUT_ROOT = "/content/drive/MyDrive/AI-Sentinel/checkpoints/full_finetune"
WINDOW_SIZE = 32
FRAME_SIZE = 224
MEAN = np.array([0.45, 0.45, 0.45], dtype=np.float32)
STD = np.array([0.225, 0.225, 0.225], dtype=np.float32)


@dataclass(frozen=True)
class VideoSample:
    path: Path
    label: int
    source: str


class ManifestSlowFastDataset(Dataset):
    def __init__(self, manifest_path: Path, split: str, max_samples: int):
        self.dataset = ManifestDataset(str(manifest_path), split=split)
        if max_samples > 0:
            self.dataset.samples = self.dataset.samples[:max_samples]

    def __len__(self) -> int:
        return len(self.dataset)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        video, label = self.dataset[index]
        fast = video.permute(1, 0, 2, 3).contiguous()
        slow = fast[::4]
        return slow, fast, torch.tensor(label, dtype=torch.long)

    @property
    def labels(self) -> list[int]:
        label_map = {"normal": 0, "violence": 1}
        return [label_map.get(sample.get("label"), 0) for sample in self.dataset.samples]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune the violence detector with guarded Colab-safe outputs.")
    parser.add_argument("--manifest", help="Path to a JSONL manifest with explicit train/val splits.")
    parser.add_argument("--sources", nargs="+", help="Zip files or directories containing violence/non-violence videos.")
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="Initial checkpoint path.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Checkpoint directory. Allowed roots: .runlogs/training/ or /content/drive/MyDrive/AI-Sentinel/checkpoints/full_finetune/.",
    )
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR), help="Where zip inputs are extracted.")
    parser.add_argument("--device", default="auto", help="Device to run on: auto, cuda, or cpu.")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--max-train-samples", type=int, default=0)
    parser.add_argument("--max-val-samples", type=int, default=0)
    parser.add_argument("--max-samples", type=int, default=None, help="Deprecated. Use --max-train-samples and --max-val-samples.")
    parser.add_argument("--include-test-positives", action="store_true")
    parser.add_argument("--unfreeze-backbone", action="store_true")
    parser.add_argument("--allow-cpu-full-training", action="store_true")
    args = parser.parse_args()

    if bool(args.manifest) == bool(args.sources):
        parser.error("Provide exactly one of --manifest or --sources.")
    if args.max_samples is not None:
        parser.error("Use --max-train-samples and --max-val-samples instead of --max-samples.")
    if args.epochs < 1:
        parser.error("--epochs must be >= 1.")
    if args.max_train_samples < 0 or args.max_val_samples < 0:
        parser.error("Sample caps must be >= 0.")
    if args.device not in {"auto", "cpu", "cuda"}:
        parser.error("--device must be one of: auto, cpu, cuda.")
    return args


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def path_is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def validate_output_dir(raw_output_dir: str) -> Path:
    output_dir = Path(raw_output_dir).expanduser()
    resolved_output_dir = output_dir.resolve()
    backend_root = BACKEND_DIR.resolve()
    local_output_root = LOCAL_OUTPUT_ROOT.resolve()
    raw_normalized = normalize_path(raw_output_dir)

    if path_is_within(resolved_output_dir, backend_root):
        raise ValueError("output_dir must not live inside backend/.")
    if path_is_within(resolved_output_dir, local_output_root):
        return resolved_output_dir
    if raw_normalized.startswith(f"{COLAB_OUTPUT_ROOT}/"):
        return output_dir

    raise ValueError(
        "output_dir must be under .runlogs/training/ or "
        "/content/drive/MyDrive/AI-Sentinel/checkpoints/full_finetune/."
    )


def get_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def resolve_device(requested_device: str) -> tuple[torch.device, dict[str, object]]:
    if requested_device == "auto":
        requested_device = "cuda" if torch.cuda.is_available() else "cpu"
    if requested_device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available in this runtime.")

    device = torch.device(requested_device)
    info: dict[str, object] = {"device": device.type}
    if device.type == "cuda":
        properties = torch.cuda.get_device_properties(0)
        info["gpu_name"] = torch.cuda.get_device_name(0)
        info["gpu_total_memory_gb"] = round(properties.total_memory / (1024 ** 3), 2)
    else:
        info["gpu_name"] = None
        info["gpu_total_memory_gb"] = 0.0
    return device, info


def enforce_cpu_training_guard(
    device: torch.device,
    train_size: int,
    val_size: int,
    epochs: int,
    allow_cpu_full_training: bool,
) -> None:
    if device.type != "cpu" or allow_cpu_full_training:
        return
    if epochs > 1 or train_size > 32 or val_size > 32:
        raise RuntimeError(
            "Refusing long CPU fine-tuning without --allow-cpu-full-training. "
            "Use CUDA, or keep CPU runs to <=32 train, <=32 val, and 1 epoch."
        )


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

        root = extract_zip(source, cache_dir) if source.is_file() and source.suffix.lower() == ".zip" else source
        for sample in discover_videos(root):
            key = normalize_path(sample.path.resolve()).lower()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            samples.append(sample)

    if include_test_positives:
        for path in sorted((ROOT_DIR / "test").glob("*.avi")):
            key = normalize_path(path.resolve()).lower()
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
        fast = torch.from_numpy(clip).permute(0, 3, 1, 2).contiguous()
        slow = fast[::4]
        label = torch.tensor(sample.label, dtype=torch.long)
        return slow, fast, label


def collate_batch(batch: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    slow = torch.stack([item[0] for item in batch], dim=0)
    fast = torch.stack([item[1] for item in batch], dim=0)
    labels = torch.stack([item[2] for item in batch], dim=0)
    return slow, fast, labels


def build_datasets(args: argparse.Namespace, cache_dir: Path) -> tuple[Dataset, Dataset, dict[str, object]]:
    if args.manifest:
        manifest_path = Path(args.manifest).resolve()
        train_dataset = ManifestSlowFastDataset(manifest_path, split="train", max_samples=args.max_train_samples)
        val_dataset = ManifestSlowFastDataset(manifest_path, split="val", max_samples=args.max_val_samples)
        summary = {
            "manifest_path": str(manifest_path),
            "sources": None,
            "train_samples": len(train_dataset),
            "val_samples": len(val_dataset),
            "train_label_counts": dict(Counter(train_dataset.labels)),
            "val_label_counts": dict(Counter(val_dataset.labels)),
        }
        return train_dataset, val_dataset, summary

    samples = load_sources(args.sources, cache_dir=cache_dir, include_test_positives=args.include_test_positives)
    if len(samples) < 8:
        raise RuntimeError("Not enough samples found for fine-tuning.")

    train_samples, val_samples = stratified_split(samples, val_ratio=args.val_ratio, seed=args.seed)
    if args.max_train_samples > 0:
        train_samples = train_samples[: args.max_train_samples]
    if args.max_val_samples > 0:
        val_samples = val_samples[: args.max_val_samples]

    summary = {
        "manifest_path": None,
        "sources": list(args.sources),
        "train_samples": len(train_samples),
        "val_samples": len(val_samples),
        "train_label_counts": dict(Counter(sample.label for sample in train_samples)),
        "val_label_counts": dict(Counter(sample.label for sample in val_samples)),
    }
    return (
        ViolenceVideoDataset(train_samples, training=True),
        ViolenceVideoDataset(val_samples, training=False),
        summary,
    )


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


def compute_metrics(logits: torch.Tensor, labels: torch.Tensor) -> dict[str, object]:
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
        "balanced_accuracy": round(float(balanced_accuracy), 4),
        "balancedAccuracy": round(float(balanced_accuracy), 4),
        "false_positives": fp,
        "false_negatives": fn,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "confusion_matrix": {
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "tp": tp,
        },
    }


def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None = None,
) -> tuple[float, dict[str, object]]:
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

    if not collected_logits:
        raise RuntimeError("No batches were produced for this epoch.")

    merged_logits = torch.cat(collected_logits, dim=0)
    merged_labels = torch.cat(collected_labels, dim=0)
    metrics = compute_metrics(merged_logits, merged_labels)
    avg_loss = total_loss / max(1, total_items)
    return avg_loss, metrics


def write_json(path: Path, payload: dict[str, object] | list[dict[str, object]]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_history(path: Path, history: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in history:
            handle.write(json.dumps(row) + "\n")


def main() -> None:
    args = parse_args()
    seed_everything(args.seed)

    output_dir = validate_output_dir(args.output_dir)
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    device, device_info = resolve_device(args.device)
    weights_path = Path(args.weights).resolve()
    git_commit = get_git_commit()

    train_dataset, val_dataset, dataset_summary = build_datasets(args, cache_dir=cache_dir)
    if len(train_dataset) == 0 or len(val_dataset) == 0:
        raise RuntimeError("Training requires at least one train sample and one validation sample.")

    enforce_cpu_training_guard(
        device=device,
        train_size=len(train_dataset),
        val_size=len(val_dataset),
        epochs=args.epochs,
        allow_cpu_full_training=args.allow_cpu_full_training,
    )

    print(f"[Train] Device: {device_info['device']}")
    if device_info["gpu_name"]:
        print(f"[Train] GPU: {device_info['gpu_name']} ({device_info['gpu_total_memory_gb']} GB)")
    else:
        print("[Train] GPU: unavailable; CPU fallback is active.")
    print(f"[Train] Output dir: {output_dir}")
    print(f"[Train] Source weights: {weights_path}")
    if dataset_summary["manifest_path"]:
        print(f"[Train] Manifest: {dataset_summary['manifest_path']}")
    else:
        print(f"[Train] Sources: {dataset_summary['sources']}")
    print(
        f"[Train] Train/Val samples: "
        f"{dataset_summary['train_samples']}/{dataset_summary['val_samples']}"
    )
    print(f"[Train] Train label counts: {dataset_summary['train_label_counts']}")
    print(f"[Train] Val label counts: {dataset_summary['val_label_counts']}")

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=device.type == "cuda",
        collate_fn=collate_batch,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=max(1, args.num_workers // 2),
        pin_memory=device.type == "cuda",
        collate_fn=collate_batch,
    )

    model = load_model(weights_path=weights_path, device=device, unfreeze_backbone=args.unfreeze_backbone)
    trainable_parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    if not trainable_parameters:
        raise RuntimeError("No trainable parameters remain after applying the backbone freeze policy.")
    optimizer = torch.optim.AdamW(trainable_parameters, lr=args.lr, weight_decay=args.weight_decay)

    best_score = -1.0
    history: list[dict[str, object]] = []
    best_snapshot: dict[str, object] | None = None
    best_checkpoint_path = output_dir / "best_candidate.pt"
    last_checkpoint_path = output_dir / "last_checkpoint.pt"
    history_path = output_dir / "metrics_history.jsonl"

    config = {
        "manifest_path": dataset_summary["manifest_path"],
        "sources": dataset_summary["sources"],
        "weights_path": str(weights_path),
        "output_dir": str(output_dir),
        "cache_dir": str(cache_dir),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "val_ratio": args.val_ratio,
        "seed": args.seed,
        "num_workers": args.num_workers,
        "max_train_samples": args.max_train_samples,
        "max_val_samples": args.max_val_samples,
        "include_test_positives": args.include_test_positives,
        "unfreeze_backbone": args.unfreeze_backbone,
        "device_request": args.device,
        "device_info": device_info,
        "git_commit": git_commit,
        "run_started_at": datetime.now(timezone.utc).isoformat(),
    }

    for epoch in range(1, args.epochs + 1):
        train_loss, train_metrics = run_epoch(model, train_loader, device, optimizer=optimizer)
        val_loss, val_metrics = run_epoch(model, val_loader, device, optimizer=None)
        score = float(val_metrics["f1"]) + float(val_metrics["balanced_accuracy"])

        summary = {
            "epoch": epoch,
            "train_loss": round(train_loss, 4),
            "val_loss": round(val_loss, 4),
            "train_f1": train_metrics["f1"],
            "val_f1": val_metrics["f1"],
            "val_balanced_accuracy": val_metrics["balanced_accuracy"],
            "val_accuracy": val_metrics["accuracy"],
            "val_precision": val_metrics["precision"],
            "val_recall": val_metrics["recall"],
            "val_specificity": val_metrics["specificity"],
            "val_false_positives": val_metrics["false_positives"],
            "val_false_negatives": val_metrics["false_negatives"],
            "val_confusion_matrix": val_metrics["confusion_matrix"],
        }
        history.append(summary)
        write_history(history_path, history)
        print(f"[Train] {json.dumps(summary)}")

        checkpoint_payload = {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "metrics": val_metrics,
            "history": history,
            "config": config,
            "trainArgs": vars(args),
            "source_weights_path": str(weights_path),
            "manifest_path": dataset_summary["manifest_path"],
            "git_commit": git_commit,
        }
        torch.save(checkpoint_payload, last_checkpoint_path)

        if score > best_score:
            best_score = score
            best_snapshot = checkpoint_payload | {
                "best_loss": float(val_loss),
                "best_f1": float(val_metrics["f1"]),
                "best_balanced_accuracy": float(val_metrics["balanced_accuracy"]),
            }
            torch.save(best_snapshot, best_checkpoint_path)
            print(f"[Train] Saved improved checkpoint to {best_checkpoint_path}")

    if best_snapshot is None:
        raise RuntimeError("Training did not produce a checkpoint.")

    write_json(output_dir / "eval_summary.json", best_snapshot["metrics"])
    write_json(output_dir / "confusion_matrix.json", best_snapshot["metrics"]["confusion_matrix"])
    write_json(
        output_dir / "training_summary.json",
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit,
            "manifest_path": dataset_summary["manifest_path"],
            "source_weights_path": str(weights_path),
            "output_dir": str(output_dir),
            "train_samples": dataset_summary["train_samples"],
            "val_samples": dataset_summary["val_samples"],
            "epochs_completed": args.epochs,
            "best_checkpoint": str(best_checkpoint_path),
            "last_checkpoint": str(last_checkpoint_path),
            "best_metrics": best_snapshot["metrics"],
            "config": config,
        },
    )

    print("[Train] Final best metrics:")
    print(json.dumps(best_snapshot["metrics"], indent=2))


if __name__ == "__main__":
    main()
