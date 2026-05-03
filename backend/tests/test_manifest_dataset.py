import json
import pytest
import torch
import tempfile
from pathlib import Path
from backend.datasets.manifest_dataset import ManifestDataset

def fake_video_loader(path: str) -> torch.Tensor:
    if path.endswith("missing.mp4"):
        raise FileNotFoundError(f"Missing {path}")
    return torch.zeros(3, 16, 224, 224)

@pytest.fixture
def fake_manifest():
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "test_manifest.jsonl"
        entries = [
            {"video_path": "fake1.mp4", "label": "violence", "split": "train"},
            {"video_path": "fake2.mp4", "label": "normal", "split": "train"},
            {"video_path": "fake3.mp4", "label": "Violence", "split": "val"},
            {"video_path": "missing.mp4", "label": "normal", "split": "val"},
            {"video_path": "fake_unknown.mp4", "label": "unknown", "split": "test"},
        ]
        with open(manifest_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        yield manifest_path

def test_manifest_dataset_loads_all(fake_manifest):
    # Load all valid labels regardless of split
    dataset = ManifestDataset(manifest_path=fake_manifest, video_loader=fake_video_loader)
    # fake_unknown is skipped because label 'unknown' is not in LABEL_MAP
    assert len(dataset) == 4

def test_manifest_dataset_filters_by_split(fake_manifest):
    dataset = ManifestDataset(manifest_path=fake_manifest, split="train", video_loader=fake_video_loader)
    assert len(dataset) == 2
    assert dataset[0]["video_path"] == "fake1.mp4"
    assert dataset[1]["video_path"] == "fake2.mp4"

def test_manifest_dataset_label_mapping(fake_manifest):
    dataset = ManifestDataset(manifest_path=fake_manifest, split="val", video_loader=fake_video_loader)
    # violence -> 1
    assert dataset[0]["label"] == 1
    assert dataset[0]["label_name"] == "violence"
    # missing -> 0
    assert dataset[1]["label"] == 0
    assert dataset[1]["label_name"] == "normal"

def test_manifest_dataset_video_loader_called(fake_manifest):
    dataset = ManifestDataset(manifest_path=fake_manifest, split="train", video_loader=fake_video_loader)
    item = dataset[0]
    assert "video" in item
    assert item["video"].shape == (3, 16, 224, 224)

def test_manifest_dataset_missing_file_raises(fake_manifest):
    dataset = ManifestDataset(manifest_path=fake_manifest, split="val", video_loader=fake_video_loader)
    with pytest.raises(RuntimeError) as excinfo:
        _ = dataset[1] # missing.mp4
    assert "Failed to load video missing.mp4" in str(excinfo.value)
