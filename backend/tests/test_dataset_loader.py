import pytest
from pathlib import Path

def test_dataset_config_loading():
    """Test that dataset configuration loads correctly."""
    # Use the absolute path or relative to project root
    config_path = Path("backend/training/datasets_config.yaml")
    
    # We'll create a dummy config for testing if it doesn't exist yet in the test environment
    if not config_path.parent.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not config_path.exists():
        with open(config_path, "w") as f:
            f.write("datasets:\n  test:\n    enabled: true\n    weight: 1.0\n")

    from training.dataset_loader import MultiDatasetLoader
    loader = MultiDatasetLoader.from_config(config_path)
    assert len(loader.datasets) > 0, "No datasets loaded"

def test_rwc2000_dataset():
    """Test RWC-2000 dataset loading."""
    from training.dataset_loader import RWCDataset
    
    # Mock path - in real test would point to actual data
    dataset = RWCDataset(root_path="dummy/path", split="train")
    
    # Check dataset structure
    assert hasattr(dataset, "__len__"), "Dataset should have __len__"
    assert hasattr(dataset, "__getitem__"), "Dataset should have __getitem__"

def test_ufc_dataset():
    """Test UFC dataset loading."""
    from training.dataset_loader import UFCDataset
    
    dataset = UFCDataset(root_path="dummy/path", split="train")
    
    assert hasattr(dataset, "__len__"), "Dataset should have __len__"
    assert hasattr(dataset, "__getitem__"), "Dataset should have __getitem__"

def test_multi_dataset_sampling():
    """Test that multi-dataset loader samples correctly."""
    config = {
        "datasets": {
            "rwc2000": {"weight": 0.3, "enabled": True},
            "ufc": {"weight": 0.3, "enabled": True},
            "hockey": {"weight": 0.2, "enabled": True},
            "movies": {"weight": 0.2, "enabled": True},
        }
    }
    
    from training.dataset_loader import MultiDatasetLoader
    loader = MultiDatasetLoader(config)
    
    # Check sampling weights sum to 1
    total_weight = sum(d['weight'] for d in loader.datasets.values())
    assert abs(total_weight - 1.0) < 0.01, "Dataset weights should sum to 1"

def test_video_clip_generation():
    """Test that videos are correctly split into clips."""
    from training.dataset_loader import VideoClipDataset
    import numpy as np
    import torch
    
    # Create dummy video frames
    dummy_video = [np.random.randint(0, 255, (160, 160, 3), dtype=np.uint8) for _ in range(100)]
    
    dataset = VideoClipDataset(
        frames=dummy_video,
        clip_length=32,
        stride=16,
        label=1,
    )
    
    assert len(dataset) > 0, "Should generate at least one clip"
    clip, label = dataset[0]
    assert isinstance(clip, torch.Tensor), "Clip should be a torch.Tensor"
    # Expected shape (C, T, H, W)
    assert clip.shape[0] == 3, "Channels should be 3"
    assert clip.shape[1] == 32, "Time steps should be 32"
    assert label in [0, 1], "Label should be 0 or 1"
