import cv2
import torch
import numpy as np
from pathlib import Path
from typing import Optional, Union, Tuple
from .video_contract import ModelProfile, DEFAULT_PROFILE, get_profile

def load_video_clip(
    path: str,
    profile: Union[str, ModelProfile] = DEFAULT_PROFILE,
) -> torch.Tensor:
    """
    Loads and preprocesses a video clip according to the specified model profile.
    
    Args:
        path: Path to video file.
        profile: Profile name ("legacy_slowfast", "x3d") or ModelProfile object.
        
    Returns:
        Tensor of shape (3, T, H, W)
    """
    if isinstance(profile, str):
        profile = get_profile(profile)
        
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
    indices = np.linspace(0, total_frames - 1, profile.num_frames, dtype=int)

    frames = []
    current_idx = 0
    
    _MEAN = np.array(profile.mean, dtype=np.float32)
    _STD  = np.array(profile.std,  dtype=np.float32)

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
            # 1. BGR -> RGB
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 2. Resize to profile.resize_size
            img = cv2.resize(img, (profile.resize_size, profile.resize_size), interpolation=cv2.INTER_LINEAR)
            
            # 3. Center crop if resolution < resize_size
            if profile.resolution < profile.resize_size:
                h, w = profile.resolution, profile.resolution
                start_y = (profile.resize_size - h) // 2
                start_x = (profile.resize_size - w) // 2
                img = img[start_y:start_y+h, start_x:start_x+w]
            
            # 4. Normalize: float32 -> [0,1] -> (x - mean) / std
            img = img.astype(np.float32) / 255.0
            img = (img - _MEAN) / _STD
            
            # 5. Transpose to (C, H, W)
            frames.append(img.transpose(2, 0, 1))
            current_idx += 1

    cap.release()
    
    # Final check: if we somehow have fewer frames than requested, repeat padding
    while len(frames) < profile.num_frames:
        if not frames:
            raise RuntimeError(f"Critical failure: no frames loaded from {path}")
        frames.append(frames[-1])

    # Stack to (T, C, H, W) then transpose to (C, T, H, W)
    # Output should be (3, 32, H, W)
    video_tensor = torch.from_numpy(np.stack(frames)).permute(1, 0, 2, 3).float()
    return video_tensor
