import pytest
import json
import torch
import tempfile
from pathlib import Path
from datasets.manifest_dataset import ManifestDataset
from datasets.video_contract import LEGACY_SLOWFAST_PROFILE, X3D_PROFILE

@pytest.fixture
def mock_manifest():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as tmp:
        tmp.write(json.dumps({"video_path": "v1.mp4", "label": "violence", "split": "train"}) + "\n")
        tmp.write(json.dumps({"video_path": "v2.mp4", "label": "normal", "split": "train"}) + "\n")
        tmp.write(json.dumps({"video_path": "v3.mp4", "label": "normal", "split": "val"}) + "\n")
        path = tmp.name
    yield path
    if Path(path).exists():
        Path(path).unlink()

def test_manifest_dataset_basic(mock_manifest):
    def mock_loader(path, profile):
        return torch.randn(3, profile.num_frames, profile.resolution, profile.resolution)
        
    ds = ManifestDataset(mock_manifest, loader_fn=mock_loader)
    assert len(ds) == 3
    video, label = ds[0]
    assert video.shape == (3, 32, 224, 224) # Default profile
    assert label == 1 # violence

def test_manifest_dataset_split(mock_manifest):
    def mock_loader(path, profile):
        return torch.randn(3, profile.num_frames, profile.resolution, profile.resolution)
        
    ds = ManifestDataset(mock_manifest, split="val", loader_fn=mock_loader)
    assert len(ds) == 1
    assert ds.samples[0]["video_path"] == "v3.mp4"

def test_manifest_dataset_x3d_profile(mock_manifest):
    def mock_loader(path, profile):
        return torch.randn(3, profile.num_frames, profile.resolution, profile.resolution)
        
    ds = ManifestDataset(mock_manifest, profile="x3d", loader_fn=mock_loader)
    video, label = ds[0]
    assert video.shape == (3, 32, 160, 160)
