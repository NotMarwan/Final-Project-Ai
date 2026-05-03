import pytest
import cv2
import numpy as np
import torch
import tempfile
from pathlib import Path
from backend.datasets.video_loader import load_video_clip

@pytest.fixture
def fake_video_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = str(Path(tmpdir) / "test_video.mp4")
        # Frame size must be > 182 so the resize-then-center-crop pipeline can work.
        height, width = 200, 200
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(video_path, fourcc, 30.0, (width, height))

        for i in range(5):
            # Blue, Green, Red cycle
            color = [0, 0, 0]
            color[i % 3] = 200
            frame = np.full((height, width, 3), color, dtype=np.uint8)
            out.write(frame)

        out.release()
        yield video_path

def test_load_video_clip_basic(fake_video_file):
    tensor = load_video_clip(fake_video_file, num_frames=16, size=(160, 160))
    # Shape should be (C, T, H, W)
    assert tensor.shape == (3, 16, 160, 160)
    assert tensor.dtype == torch.float32
    # After mean/std normalization, values can be negative — do NOT assert [0,1].
    # Assert the tensor has non-trivial variance (not all zeros / random noise).
    assert tensor.std() > 0.0

def test_load_video_clip_missing_file():
    with pytest.raises(FileNotFoundError):
        load_video_clip("missing_video.mp4")

def test_load_video_clip_corrupt_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        corrupt_path = str(Path(tmpdir) / "corrupt.mp4")
        with open(corrupt_path, "wb") as f:
            f.write(b"this is not a video file")
        
        with pytest.raises(RuntimeError) as excinfo:
            load_video_clip(corrupt_path)
        assert "0 frames or is corrupt" in str(excinfo.value)

def test_load_video_clip_padding(fake_video_file):
    # The fake video has only 5 frames, but we request 16.
    # The loader should repeat the last frame up to 16 via padding.
    tensor = load_video_clip(fake_video_file, num_frames=16, size=(160, 160))
    assert tensor.shape[1] == 16, "Tensor does not have the requested number of frames."
    # The last sampled frame and the last padded frame must be identical.
    frame_last_sampled = tensor[:, 4, :, :]  # index 4 is the last real sample in a 5-frame video
    frame_padded = tensor[:, 15, :, :]
    assert torch.allclose(frame_last_sampled, frame_padded), "Padding did not repeat the last frame."
