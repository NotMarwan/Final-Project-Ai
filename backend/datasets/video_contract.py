"""
video_contract.py — Single source of truth for video input contract.

These values MUST match inference.py:
    FRAME_SIZE  = 160   (X3D target)
    WINDOW_SIZE = 32    (STRICT 32-frame window, never change)
    MEAN        = [0.45, 0.45, 0.45]
    STD         = [0.225, 0.225, 0.225]

Tensor shape convention:
    Per-clip (no batch): (C, T, H, W)  -> (3, 32, 160, 160)
    Batched:             (B, C, T, H, W) -> (B, 3, 32, 160, 160)
"""

# ── Authoritative constants (mirrors inference.py) ──────────────────────────
# STRICT: never change without updating inference.py
DEFAULT_NUM_FRAMES: int = 32            # WINDOW_SIZE from inference.py
DEFAULT_SIZE: tuple[int, int] = (160, 160)  # FRAME_SIZE from inference.py
RESIZE_BEFORE_CROP: int = 182           # resize-then-center-crop (inference.py convention)
NORMALIZE_MEAN: tuple[float, float, float] = (0.45, 0.45, 0.45)
NORMALIZE_STD: tuple[float, float, float] = (0.225, 0.225, 0.225)

# Shape descriptors (for documentation/assertion use)
EXPECTED_CLIP_SHAPE: str = "(3, T, H, W) = (3, 32, 160, 160)"
EXPECTED_BATCH_SHAPE: str = "(B, C, T, H, W) = (B, 3, 32, 160, 160)"
