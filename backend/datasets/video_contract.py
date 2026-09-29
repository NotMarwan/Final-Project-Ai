"""
video_contract.py — Single source of truth for video input profiles.

This file defines the expected input contracts for different model architectures
used in the AI Sentinel project.
"""

from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class ModelProfile:
    name: str
    num_frames: int
    resolution: int
    resize_size: int
    mean: Tuple[float, float, float]
    std: Tuple[float, float, float]
    model_class: str

# ── LEGACY SLOWFAST PROFILE (Current Production) ──────────────────────────
# Mirroring inference.py legacy path:
# - resolution 224
# - no center-crop (just direct resize to 224)
# - 32 frames
LEGACY_SLOWFAST_PROFILE = ModelProfile(
    name="legacy_slowfast",
    num_frames=32,
    resolution=224,
    resize_size=224,
    mean=(0.45, 0.45, 0.45),
    std=(0.225, 0.225, 0.225),
    model_class="ViolenceDetector"
)

# ── X3D PROFILE (Future / Experimental) ──────────────────────────────────
# Mirroring inference.py X3D path:
# - resolution 160
# - resize 182 then center-crop 160
# - 32 frames
X3D_PROFILE = ModelProfile(
    name="x3d",
    num_frames=32,
    resolution=160,
    resize_size=182,
    mean=(0.45, 0.45, 0.45),
    std=(0.225, 0.225, 0.225),
    model_class="X3DViolenceModel"
)

# ── DEFAULT PROFILE ──────────────────────────────────────────────────────
# Production defaults to legacy SlowFast as proven by best_model.pt audit.
DEFAULT_PROFILE = LEGACY_SLOWFAST_PROFILE

def get_profile(name: str) -> ModelProfile:
    if name == "legacy_slowfast":
        return LEGACY_SLOWFAST_PROFILE
    if name == "x3d":
        return X3D_PROFILE
    raise ValueError(f"Unknown model profile: {name}")
