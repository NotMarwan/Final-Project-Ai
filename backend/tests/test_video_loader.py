import pytest
import cv2
import numpy as np
import tempfile
from pathlib import Path
from datasets.video_contract import LEGACY_SLOWFAST_PROFILE, X3D_PROFILE

@pytest.fixture
def fake_video_file():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        path = tmp.name
    
    # Create a 5-frame video with 256x256 frames
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(path, fourcc, 1.0, (256, 256))
    for i in range(5):
        frame = np.full((256, 256, 3), i * 50, dtype=np.uint8)
        out.write(frame)
    out.release()
    yield path
    if Path(path).exists():
        Path(path).unlink()

def test_load_video_clip_legacy_profile(fake_video_file):
    from datasets.video_loader import load_video_clip
    import torch
    # Legacy profile: 32 frames, 224x224
    tensor = load_video_clip(fake_video_file, profile="legacy_slowfast")
    assert tensor.shape == (3, 32, 224, 224)
    assert tensor.dtype == torch.float32

def test_load_video_clip_x3d_profile(fake_video_file):
    from datasets.video_loader import load_video_clip
    import torch
    # X3D profile: 32 frames, 160x160
    tensor = load_video_clip(fake_video_file, profile="x3d")
    assert tensor.shape == (3, 32, 160, 160)
    assert tensor.dtype == torch.float32

def test_load_video_clip_missing_file():
    from datasets.video_loader import load_video_clip
    with pytest.raises(FileNotFoundError):
        load_video_clip("non_existent.mp4")

def test_load_video_clip_corrupt_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        corrupt_path = str(Path(tmpdir) / "corrupt.mp4")
        with open(corrupt_path, "wb") as f:
            f.write(b"this is not a video file")
        from datasets.video_loader import load_video_clip
        with pytest.raises(RuntimeError) as excinfo:
            load_video_clip(corrupt_path)
        err_msg = str(excinfo.value)
        assert "Failed to open" in err_msg or "0 frames or is corrupt" in err_msg

def test_load_video_clip_padding(fake_video_file):
    from datasets.video_loader import load_video_clip
    import torch
    # The fake video has only 5 frames, but we request 32.
    tensor = load_video_clip(fake_video_file, profile=LEGACY_SLOWFAST_PROFILE)
    assert tensor.shape[1] == 32
    # The padding should repeat the last frame
    frame_last_sampled = tensor[:, 4, :, :] 
    frame_padded = tensor[:, 31, :, :]
    assert torch.allclose(frame_last_sampled, frame_padded)
