"""
inference.py — Violence Detection Inference Script
====================================================
Senior Computer Vision Engineer — Production-Ready
"""

import os
import time
import sys
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ──────────────────────────────────────────────────────────────────────────────
# 1. Model Architecture
# ──────────────────────────────────────────────────────────────────────────────

class X3DViolenceModel(nn.Module):
    def __init__(self, num_classes: int = 2):
        super().__init__()
        # Prefer X3D-M when torchvision exposes it, otherwise fall back to a
        # supported video backbone that keeps the same single-tensor interface.
        self.model = self._build_backbone(num_classes)

    @staticmethod
    def _build_backbone(num_classes: int) -> nn.Module:
        try:
            from torchvision.models.video import x3d_m

            model = x3d_m(weights=None)
            if hasattr(model, "blocks") and len(model.blocks) > 5 and hasattr(model.blocks[5], "proj"):
                in_features = model.blocks[5].proj.in_features
                model.blocks[5].proj = nn.Linear(in_features, num_classes)
                return model
        except Exception:
            pass

        try:
            from torchvision.models.video import r2plus1d_18

            model = r2plus1d_18(weights=None)
            if hasattr(model, "fc"):
                in_features = model.fc.in_features
                model.fc = nn.Linear(in_features, num_classes)
                return model
        except Exception as exc:
            raise RuntimeError(f"Unable to initialize a supported video backbone: {exc}") from exc

        raise RuntimeError("No supported video backbone available for violence model.")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Expected input shape: (batch, 3, 32, 160, 160)
        return self.model(x)

# Legacy architecture fallback (SlowFast)
class SlowFastBackbone(nn.Module):
    def __init__(self, pretrained: bool = False):
        super().__init__()
        try:
            from einops import rearrange
            self.backbone = torch.hub.load("facebookresearch/pytorchvideo", "slowfast_r50", pretrained=pretrained)
            self.backbone.blocks[-1] = nn.Identity()
            self.out_dim = 2304
        except Exception:
            import torchvision.models.video as vm
            m = vm.r3d_18(pretrained=pretrained)
            self.backbone = nn.Sequential(*list(m.children())[:-2])
            self.pool = nn.AdaptiveAvgPool3d((1, 1, 1))
            self.out_dim = 512

    def forward(self, slow: torch.Tensor, fast: torch.Tensor) -> torch.Tensor:
        from einops import rearrange
        if hasattr(self, "pool"):
            return self.pool(self.backbone(rearrange(fast, "b t c h w -> b c t h w"))).flatten(1)
        return self.backbone([
            rearrange(slow, "b t c h w -> b c t h w"),
            rearrange(fast, "b t c h w -> b c t h w"),
        ]).flatten(1)

class ViolenceDetector(nn.Module):
    def __init__(self, num_classes: int = 2):
        super().__init__()
        self.sf = SlowFastBackbone(pretrained=False)
        dim = self.sf.out_dim
        self.head = nn.Sequential(
            nn.LayerNorm(dim),
            nn.Linear(dim, 512),
            nn.GELU(),
            nn.Dropout(0.4),
            nn.Linear(512, num_classes),
        )

    def forward(self, slow: torch.Tensor, fast: torch.Tensor) -> torch.Tensor:
        return self.head(self.sf(slow, fast))

# ──────────────────────────────────────────────────────────────────────────────
# 2. Preprocessing & Constants
# ──────────────────────────────────────────────────────────────────────────────

MEAN = np.array([0.45, 0.45, 0.45], dtype=np.float32)
STD  = np.array([0.225, 0.225, 0.225], dtype=np.float32)
FRAME_SIZE   = 160   # X3D target
WINDOW_SIZE  = 32    # STRICT 32-frame window
VIOLENCE_CLS = 1

def preprocess_window(frames: list[np.ndarray]) -> torch.Tensor:
    processed = []
    for frame in frames:
        # resize each frame → (182×182) → center-crop → (160×160)
        img = cv2.resize(frame, (182, 182), interpolation=cv2.INTER_LINEAR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        start = (182 - 160) // 2
        img = img[start:start+160, start:start+160].astype(np.float32) / 255.0
        img = (img - MEAN) / STD
        processed.append(img)
    
    # stack to tensor (1, 3, 32, 160, 160)
    tensor = np.stack(processed, axis=0).transpose(3, 0, 1, 2)
    return torch.from_numpy(tensor).unsqueeze(0)

# ──────────────────────────────────────────────────────────────────────────────
# 3. Inference Pipeline
# ──────────────────────────────────────────────────────────────────────────────

class ViolenceInferencePipeline:
    def __init__(self, weights_path: str, device: torch.device, threshold: float = 0.75, stride: int = 16):
        self.device    = device
        self.threshold = threshold
        self.stride    = stride
        self.is_x3d    = False

        print(f"[AI] Initializing X3D-M on {device}...")
        try:
            self.model = X3DViolenceModel(num_classes=2).to(device)
            if os.path.exists(weights_path):
                state = torch.load(weights_path, map_location=device)
                self.model.load_state_dict(state)
                self.is_x3d = True
                print("[AI] X3D model loaded successfully.")
            else:
                print(f"[WARN] {weights_path} not found. Fallback to Legacy.")
                raise FileNotFoundError()
        except Exception:
            print("[AI] Falling back to Legacy SlowFast model.")
            self.model = ViolenceDetector(num_classes=2).to(device)
            try:
                state = torch.load("best_model.pt", map_location=device)
                # Unwrap the model state dict if it's a full checkpoint
                if "model_state_dict" in state:
                    state = state["model_state_dict"]
                self.model.load_state_dict(state)
                print("[AI] Legacy SlowFast model weights loaded successfully.")
            except Exception as e:
                print(f"[AI] Critical: Fallback failed: {e}")
        
        self.model.eval()
        self._buffer = deque(maxlen=WINDOW_SIZE)
        self._last_label = 0
        self._last_conf  = 0.0
        self._counter    = 0

    def reset(self):
        self._buffer.clear()
        self._last_label = 0
        self._last_conf = 0.0
        self._counter = 0

    @torch.inference_mode()
    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        self._buffer.append(frame)
        self._counter += 1

        if len(self._buffer) == WINDOW_SIZE and self._counter % self.stride == 0:
            start_time = time.perf_counter()
            
            if self.is_x3d:
                input_tensor = preprocess_window(list(self._buffer)).to(self.device)
                logits = self.model(input_tensor)
            else:
                # Legacy SlowFast Logic (Simulated for compatibility)
                processed = []
                for f in list(self._buffer):
                    img = cv2.resize(f, (224, 224))
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)/255.0
                    processed.append((img-MEAN)/STD)
                fast = torch.from_numpy(np.stack(processed).transpose(0,3,1,2)).unsqueeze(0).to(self.device)
                slow = fast[:, ::4, :, :, :]
                logits = self.model(slow, fast)

            probs = F.softmax(logits, dim=-1)[0]
            self._last_conf = probs[VIOLENCE_CLS].item()
            self._last_label = int(self._last_conf >= self.threshold)
            
            latency = (time.perf_counter() - start_time) * 1000
            print(f"[AI] Latency: {latency:.1f}ms | Conf: {self._last_conf:.2f}")

        return frame.copy()
