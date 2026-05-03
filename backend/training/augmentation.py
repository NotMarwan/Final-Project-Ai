"""
Advanced augmentation for multi-angle and robust training.
Critical for 170cm eye-level camera angle performance.
"""

import torch
import numpy as np
import cv2
from torchvision import transforms


class AngleAugmentation:
    """Augmentation to simulate different camera angles."""
    
    def __init__(self, angles: list = [-30, -15, 0, 15, 30], p: float = 0.5):
        self.angles = angles
        self.p = p
    
    def __call__(self, clip: torch.Tensor) -> torch.Tensor:
        """
        Apply random angle augmentation to clip.
        clip shape: (C, T, H, W)
        """
        if np.random.rand() > self.p:
            return clip
        
        angle = np.random.choice(self.angles)
        
        # Apply rotation to each frame
        C, T, H, W = clip.shape
        rotated = []
        
        for t in range(T):
            frame = clip[:, t, :, :].numpy().transpose(1, 2, 0)  # (H, W, C)
            frame = (frame * 255).astype(np.uint8)
            
            # Rotate
            center = (W // 2, H // 2)
            rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated_frame = cv2.warpAffine(frame, rot_mat, (W, H))
            
            rotated_frame = rotated_frame.astype(np.float32) / 255.0
            rotated.append(torch.from_numpy(rotated_frame.transpose(2, 0, 1)))
        
        return torch.stack(rotated, dim=1)  # (C, T, H, W)


class LightingAugmentation:
    """Simulate different lighting conditions."""
    
    def __init__(self, brightness: float = 0.3, contrast: float = 0.3, p: float = 0.5):
        self.brightness = brightness
        self.contrast = contrast
        self.p = p
    
    def __call__(self, clip: torch.Tensor) -> torch.Tensor:
        if np.random.rand() > self.p:
            return clip
        
        # Random brightness/contrast adjustment
        brightness_factor = 1.0 + np.random.uniform(-self.brightness, self.brightness)
        contrast_factor = 1.0 + np.random.uniform(-self.contrast, self.contrast)
        
        clip = clip * brightness_factor
        clip = (clip - 0.5) * contrast_factor + 0.5
        clip = torch.clamp(clip, 0.0, 1.0)
        
        return clip


class VideoAugmentationPipeline:
    """Complete augmentation pipeline for video clips."""
    
    def __init__(self, config: dict = None):
        config = config or {}
        
        self.angle_aug = AngleAugmentation(
            angles=config.get("angles", [-30, -15, 0, 15, 30]),
            p=config.get("angle_prob", 0.5),
        )
        
        self.lighting_aug = LightingAugmentation(
            brightness=config.get("brightness", 0.3),
            contrast=config.get("contrast", 0.3),
            p=config.get("lighting_prob", 0.5),
        )
    
    def __call__(self, clip: torch.Tensor) -> torch.Tensor:
        clip = self.angle_aug(clip)
        clip = self.lighting_aug(clip)
        return clip
