import cv2
import torch
import numpy as np
from pathlib import Path
from typing import Tuple

from .video_contract import (
    DEFAULT_NUM_FRAMES,
    DEFAULT_SIZE,
    RESIZE_BEFORE_CROP,
    NORMALIZE_MEAN,
    NORMALIZE_STD,
)

# ── Contract-aligned constants ───────────────────────────────────────────────
# These must remain consistent with inference.py and video_contract.py.
# STRICT: 32 frames, 160×160, ImageNet-style normalization (mean/std from preprocess_window).
_MEAN = np.array(NORMALIZE_MEAN, dtype=np.float32)
_STD  = np.array(NORMALIZE_STD,  dtype=np.float32)


def load_video_clip(
    path: str,
    num_frames: int = DEFAULT_NUM_FRAMES,
    size: Tuple[int, int] = DEFAULT_SIZE,
) -> torch.Tensor:
    """
    Loads a video clip using OpenCV.

    Mirrors the preprocessing in inference.py preprocess_window():
      1. Uniformly sample `num_frames` frames from the video.
      2. For each frame: BGR → RGB, resize to RESIZE_BEFORE_CROP×RESIZE_BEFORE_CROP,
         center-crop to size×size, normalize with ImageNet-style mean/std.
      3. Return tensor of shape (C, T, H, W) = (3, num_frames, H, W) as float32.

    Defaults match production inference contract:
        num_frames = 32   (WINDOW_SIZE in inference.py)
        size       = (160, 160)  (FRAME_SIZE in inference.py)

    Normalization: (pixel/255.0 - mean) / std
        mean = [0.45, 0.45, 0.45]
        std  = [0.225, 0.225, 0.225]

    Output shape (no batch): (3, 32, 160, 160)
    Batched (after DataLoader): (B, 3, 32, 160, 160)
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"Video file not found: {path}")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video file: {path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        raise RuntimeError(f"Video {path} has 0 frames or is corrupt.")

    # Uniform sampling indices across the full video duration
    indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)

    frames = []
    current_idx = 0

    for target_idx in indices:
        # Fast-forward to the target frame
        while current_idx < target_idx:
            ret = cap.grab()
            if not ret:
                break
            current_idx += 1

        ret, frame = cap.read()
        if not ret:
            # Duplicate the last valid frame on read failure (end-of-file corruption)
            if frames:
                frames.append(frames[-1])
            else:
                cap.release()
                raise RuntimeError(f"Failed to read any frames from {path}")
        else:
            # ── Mirror inference.py preprocess_window() ──────────────────────
            # 1. Resize to RESIZE_BEFORE_CROP × RESIZE_BEFORE_CROP
            img = cv2.resize(frame, (RESIZE_BEFORE_CROP, RESIZE_BEFORE_CROP),
                             interpolation=cv2.INTER_LINEAR)
            # 2. BGR → RGB
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            # 3. Center-crop to target size
            h, w = size
            start_y = (RESIZE_BEFORE_CROP - h) // 2
            start_x = (RESIZE_BEFORE_CROP - w) // 2
            img = img[start_y:start_y + h, start_x:start_x + w]
            # 4. Normalize: float32 → [0,1] → (x - mean) / std
            img = img.astype(np.float32) / 255.0
            img = (img - _MEAN) / _STD
            frames.append(img)
        current_idx += 1

    cap.release()

    # Pad short videos by repeating the last frame
    while len(frames) < num_frames:
        frames.append(frames[-1])

    # Stack: (T, H, W, C) → permute → (C, T, H, W)
    video_array = np.stack(frames, axis=0)          # (T, H, W, C)
    tensor = torch.from_numpy(video_array).float()  # (T, H, W, C)
    tensor = tensor.permute(3, 0, 1, 2)             # (C, T, H, W)

    return tensor
