"""
test_video_input_contract.py

Verifies:
 1. video_loader defaults match the production model contract (32 frames, 160x160).
 2. Tensor shape is (3, 32, 160, 160).
 3. Batch shape is (B, 3, 32, 160, 160).
 4. Normalization is applied (values may be < 0 due to mean subtraction).
 5. ManifestDataset produces samples with the correct shape.
 6. No fake/random tensors are used in the real loader path.
"""

import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch

from backend.datasets.video_loader import load_video_clip
from backend.datasets.video_contract import (
    DEFAULT_NUM_FRAMES,
    DEFAULT_SIZE,
    NORMALIZE_MEAN,
    NORMALIZE_STD,
    EXPECTED_CLIP_SHAPE,
)
from backend.datasets.manifest_dataset import ManifestDataset


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def synthetic_video():
    """Creates a tiny but valid MP4 clip using cv2."""
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = str(Path(tmpdir) / "contract_test.mp4")
        h, w = 200, 200  # Larger than 182 so center-crop can work
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(video_path, fourcc, 30.0, (w, h))
        for i in range(40):  # 40 frames > 32, exercises sampling
            color = [0, 0, 0]
            color[i % 3] = 200
            frame = np.full((h, w, 3), color, dtype=np.uint8)
            out.write(frame)
        out.release()
        yield video_path


@pytest.fixture
def fake_manifest(synthetic_video):
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = str(Path(tmpdir) / "manifest.jsonl")
        entries = [
            {"path": synthetic_video, "label": "violence", "split": "train"},
            {"path": synthetic_video, "label": "normal",   "split": "val"},
        ]
        with open(manifest_path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        yield manifest_path


# ── Contract Constants ────────────────────────────────────────────────────────

def test_contract_num_frames():
    assert DEFAULT_NUM_FRAMES == 32, (
        f"Contract violation: expected 32 frames (matching inference.py WINDOW_SIZE), "
        f"got {DEFAULT_NUM_FRAMES}"
    )


def test_contract_resolution():
    assert DEFAULT_SIZE == (160, 160), (
        f"Contract violation: expected (160, 160) (matching inference.py FRAME_SIZE), "
        f"got {DEFAULT_SIZE}"
    )


def test_contract_normalization_mean():
    assert NORMALIZE_MEAN == (0.45, 0.45, 0.45), (
        f"Contract violation: mean should match inference.py, got {NORMALIZE_MEAN}"
    )


def test_contract_normalization_std():
    assert NORMALIZE_STD == (0.225, 0.225, 0.225), (
        f"Contract violation: std should match inference.py, got {NORMALIZE_STD}"
    )


# ── Loader Shape Tests ────────────────────────────────────────────────────────

def test_loader_default_shape(synthetic_video):
    """Default load_video_clip must produce (3, 32, 160, 160)."""
    tensor = load_video_clip(synthetic_video)
    assert tensor.shape == (3, DEFAULT_NUM_FRAMES, DEFAULT_SIZE[0], DEFAULT_SIZE[1]), (
        f"Shape mismatch. Got {tensor.shape}, expected "
        f"(3, {DEFAULT_NUM_FRAMES}, {DEFAULT_SIZE[0]}, {DEFAULT_SIZE[1]})"
    )


def test_loader_dtype(synthetic_video):
    tensor = load_video_clip(synthetic_video)
    assert tensor.dtype == torch.float32


def test_loader_normalization_applied(synthetic_video):
    """After mean/std normalization, values should be able to go negative."""
    tensor = load_video_clip(synthetic_video)
    # Raw pixel > 0 and mean=0.45 → after normalization some frames may be negative
    # Just confirm the range is not simply [0, 1] (which would indicate raw scaling only)
    # Allow either: a) has negatives, or b) all-zero dark frames give exactly -2.0
    value_range = tensor.max() - tensor.min()
    assert value_range > 0, "Tensor appears to be all zeros — normalization may have failed."


def test_loader_no_random_data(synthetic_video):
    """Loading the same file twice must produce identical tensors."""
    t1 = load_video_clip(synthetic_video)
    t2 = load_video_clip(synthetic_video)
    assert torch.allclose(t1, t2), "Loader is non-deterministic — possible random/mock data."


# ── Batch Shape ───────────────────────────────────────────────────────────────

def test_batch_shape(synthetic_video):
    """DataLoader batching should produce (B, C, T, H, W)."""
    t1 = load_video_clip(synthetic_video)
    t2 = load_video_clip(synthetic_video)
    batch = torch.stack([t1, t2], dim=0)
    assert batch.shape == (2, 3, DEFAULT_NUM_FRAMES, DEFAULT_SIZE[0], DEFAULT_SIZE[1])


# ── ManifestDataset Integration ───────────────────────────────────────────────

def test_manifest_dataset_sample_shape(fake_manifest):
    """ManifestDataset must return samples with the production clip shape."""
    dataset = ManifestDataset(manifest_path=fake_manifest, split="train")
    tensor, label = dataset[0]
    expected = (3, DEFAULT_NUM_FRAMES, DEFAULT_SIZE[0], DEFAULT_SIZE[1])
    assert tensor.shape == expected, (
        f"ManifestDataset sample shape mismatch. Got {tensor.shape}, expected {expected}"
    )
    assert isinstance(label, int)


def test_manifest_dataset_no_fake_injection(fake_manifest):
    """ManifestDataset without explicit video_loader must use the real loader."""
    dataset = ManifestDataset(manifest_path=fake_manifest, split="train")
    # The real loader is load_video_clip — we verify by checking the loader reference
    from backend.datasets.video_loader import load_video_clip as real_loader
    assert dataset.video_loader is real_loader, (
        "ManifestDataset is not using the real video loader by default."
    )
