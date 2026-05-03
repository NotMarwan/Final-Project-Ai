import cv2
import torch
import numpy as np
from pathlib import Path
from typing import Tuple

def load_video_clip(
    path: str,
    num_frames: int = 16,
    size: Tuple[int, int] = (256, 256)
) -> torch.Tensor:
    """
    Loads a video clip using OpenCV, samples a fixed number of frames uniformly,
    resizes them, converts BGR to RGB, and returns a PyTorch tensor.
    
    Expected output shape: (C, T, H, W) -> (3, num_frames, size[0], size[1])
    Values are normalized to [0, 1] range as torch.float32.
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"Video file not found: {path}")

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video file: {path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Handle extremely short or unreadable videos
    if total_frames <= 0:
        cap.release()
        raise RuntimeError(f"Video {path} has 0 frames or is corrupt.")

    # Uniform sampling indices
    indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
    
    frames = []
    current_idx = 0
    
    for target_idx in indices:
        # Fast-forward to the target frame if needed
        while current_idx < target_idx:
            ret = cap.grab()
            if not ret:
                break
            current_idx += 1
            
        ret, frame = cap.read()
        if not ret:
            # If we fail to read a frame (corrupt at end), duplicate the last valid frame
            if len(frames) > 0:
                frames.append(frames[-1])
            else:
                # If even the first frame fails, we must abort
                cap.release()
                raise RuntimeError(f"Failed to read any frames from {path}")
        else:
            # Convert BGR to RGB and resize
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, size)
            frames.append(frame)
        current_idx += 1

    cap.release()

    # In case we didn't get enough frames (due to extreme corruption), pad by repeating the last frame
    while len(frames) < num_frames:
        frames.append(frames[-1])
        
    # Stack frames into a numpy array: shape (T, H, W, C)
    video_array = np.stack(frames, axis=0)
    
    # Convert to PyTorch tensor
    tensor = torch.from_numpy(video_array).float()
    
    # Normalize to [0, 1]
    tensor = tensor / 255.0
    
    # Transpose to (C, T, H, W)
    # Original is (T, H, W, C) -> permute(3, 0, 1, 2)
    tensor = tensor.permute(3, 0, 1, 2)
    
    return tensor
