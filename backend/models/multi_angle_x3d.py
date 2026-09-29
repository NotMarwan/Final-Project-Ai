"""
Multi-angle violence backbone (legacy module name `multi_angle_x3d`).

IDENTITY (verified 2026-09-29, WT-19 / S-02):
  This module is NOT X3D. The backbone is torchvision's ``r2plus1d_18``
  ("R(2+1)D-18"). The historical names ``MultiAngleX3D`` / ``X3DViolenceModel``
  are retained only because they are string contracts in other slices
  (dataset profile ``model_class`` values in `backend/datasets/`,
  `backend/tools/inspect_model_checkpoint.py`, `backend/train_calibration.py`).
  Do not describe this model as X3D in labels or APIs; use
  ``ARCHITECTURE_ID`` / ``ARCHITECTURE_LABEL`` below (see F-29 wording fix).
  True X3D (arXiv 2004.04730) was never present in this repository.

The former ``SpatialTransformer`` submodule was removed: its forward pass
computed an affine theta and discarded it (a 512000x32 dead matmul per window,
~16.4M unused parameters). Outputs are bit-identical without it. Checkpoints
that still carry ``spatial_transformer.*`` keys are tolerated by the loader in
`backend/inference.py`, which strips those keys with a printed notice.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional


# Truthful architecture identity for labels/APIs (R8 identity reconciliation).
ARCHITECTURE_ID = "torchvision_r2plus1d_18_multiangle"
ARCHITECTURE_LABEL = "R(2+1)D-18 (torchvision) with multi-angle head (legacy class name MultiAngleX3D; not X3D)"
LEGACY_CLASS_NAME = "MultiAngleX3D"


class MultiAngleX3D(nn.Module):
    """
    Binary violence head over torchvision R(2+1)D-18.

    Legacy name: this is NOT an X3D model (see module docstring). Kept for
    state-dict and string-contract compatibility across slices S-21/S-05.
    """

    ARCHITECTURE_ID = ARCHITECTURE_ID
    ARCHITECTURE_LABEL = ARCHITECTURE_LABEL

    def __init__(
        self,
        num_classes: int = 2,
        use_angle_augmentation: bool = True,
        dropout_rate: float = 0.3,
    ):
        super().__init__()
        self.use_angle_augmentation = use_angle_augmentation

        # This project was trained against torchvision's local R(2+1)D fallback;
        # torchvision does not provide x3d_m. Construct that exact architecture
        # directly so startup never depends on an optional import or network path.
        from torchvision.models.video import r2plus1d_18
        self.backbone = r2plus1d_18(weights=None)
        in_features = self.backbone.fc.in_features
        self.backbone.fc = nn.Linear(in_features, num_classes)

        # Dropout for regularization
        self.dropout = nn.Dropout(dropout_rate)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Angle augmentation during training: random horizontal flip
        # (simulates different camera positions).
        if self.training and self.use_angle_augmentation:
            if torch.rand(1).item() > 0.5:
                x = torch.flip(x, dims=[4])  # Flip width dimension

        x = self.backbone(x)
        x = self.dropout(x)
        return x
