"""
inference.py — Violence Detection Inference Script
====================================================
Senior Computer Vision Engineer — Production-Ready
"""

import os
import time
import threading
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    from .calibration_utils import load_calibration_profile
except ImportError:
    from calibration_utils import load_calibration_profile

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
CALIBRATION_PROFILE = load_calibration_profile(base_dir=Path(__file__).resolve().parent)
VIOLENCE_CLS = int(os.getenv("VIOLENCE_CLASS_INDEX", str(CALIBRATION_PROFILE.get("classIndex", 0))))
VIOLENCE_TEMP = max(0.05, float(os.getenv("VIOLENCE_LOGIT_TEMPERATURE", str(CALIBRATION_PROFILE.get("logitTemperature", 1.0)))))
VIOLENCE_LOGIT_BIAS = float(os.getenv("VIOLENCE_LOGIT_BIAS", str(CALIBRATION_PROFILE.get("logitBias", 0.0))))
CONF_EMA_ALPHA = float(os.getenv("VIOLENCE_CONFIDENCE_EMA_ALPHA", str(CALIBRATION_PROFILE.get("emaAlpha", 0.45))))
HYSTERESIS_MARGIN = float(os.getenv("VIOLENCE_HYSTERESIS_MARGIN", str(CALIBRATION_PROFILE.get("hysteresisMargin", 0.08))))

def ensure_bgr(frame: np.ndarray) -> np.ndarray:
    if frame is None:
        return frame
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if frame.ndim == 3 and frame.shape[2] == 1:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if frame.ndim == 3 and frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return frame

def preprocess_window(frames: list[np.ndarray]) -> torch.Tensor:
    processed = []
    for frame in frames:
        frame = ensure_bgr(frame)
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
        self.enabled   = True
        self.disabled_reason = ""
        self._inference_running = False
        self._inference_lock = threading.Lock()

        print(f"[AI] Initializing X3D-M on {device}...")
        try:
            self.model = X3DViolenceModel(num_classes=2).to(device)
            if os.path.exists(weights_path):
                state = torch.load(weights_path, map_location=device)
                state_dict = self._extract_state_dict(state)
                self.model.load_state_dict(state_dict)
                self.is_x3d = True
                print("[AI] X3D model loaded successfully.")
            else:
                print(f"[WARN] {weights_path} not found. Fallback to Legacy.")
                raise FileNotFoundError()
        except Exception as x3d_exc:
            print("[AI] Falling back to Legacy SlowFast model.")
            self.model = ViolenceDetector(num_classes=2).to(device)
            try:
                state = torch.load(weights_path, map_location=device)
                state_dict = self._extract_state_dict(state)
                self.model.load_state_dict(state_dict)
            except Exception as e:
                print(f"[AI] Critical: Fallback failed: {e}")
                self.enabled = False
                self.model = None
                self.disabled_reason = f"x3d={type(x3d_exc).__name__}; legacy={type(e).__name__}"
                print(f"[AI] Stream-only mode enabled (reason: {self.disabled_reason}).")
        
        if self.model is not None:
            self.model.eval()
        self._buffer = deque(maxlen=WINDOW_SIZE)
        self._last_label = 0
        self._last_conf  = 0.0
        self._last_raw_conf = 0.0
        self._last_calibrated_conf = 0.0
        self._is_violent = False
        self._counter    = 0
        self._ema_alpha = max(0.05, min(0.95, CONF_EMA_ALPHA))
        self._hysteresis_margin = max(0.0, min(0.30, HYSTERESIS_MARGIN))
        self._logit_temp = VIOLENCE_TEMP
        self._logit_bias = VIOLENCE_LOGIT_BIAS

    def reset(self):
        self._buffer.clear()
        self._last_label = 0
        self._last_conf = 0.0
        self._last_raw_conf = 0.0
        self._last_calibrated_conf = 0.0
        self._is_violent = False
        self._counter = 0
        with self._inference_lock:
            self._inference_running = False

    @staticmethod
    def _extract_state_dict(state):
        if isinstance(state, dict):
            if "model_state_dict" in state and isinstance(state["model_state_dict"], dict):
                return state["model_state_dict"]
            if "state_dict" in state and isinstance(state["state_dict"], dict):
                return state["state_dict"]
        return state

    @torch.inference_mode()
    def _infer_window(self, window_frames: list[np.ndarray]) -> None:
        start_time = time.perf_counter()
        try:
            if self.is_x3d:
                input_tensor = preprocess_window(window_frames).to(self.device)
                logits = self.model(input_tensor)
            else:
                processed = []
                for f in window_frames:
                    f = ensure_bgr(f)
                    img = cv2.resize(f, (224, 224))
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
                    processed.append((img - MEAN) / STD)
                fast = torch.from_numpy(np.stack(processed).transpose(0, 3, 1, 2)).unsqueeze(0).to(self.device)
                slow = fast[:, ::4, :, :, :]
                logits = self.model(slow, fast)

            probs = F.softmax(logits, dim=-1)[0]
            raw_conf = probs[VIOLENCE_CLS].item()
            calibrated_conf = self._calibrate_confidence(logits, raw_conf)
            self._last_raw_conf = raw_conf
            self._last_calibrated_conf = calibrated_conf
            if self._counter <= WINDOW_SIZE:
                smoothed_conf = calibrated_conf
            else:
                smoothed_conf = (self._ema_alpha * calibrated_conf) + ((1.0 - self._ema_alpha) * self._last_conf)
            self._last_conf = float(max(0.0, min(1.0, smoothed_conf)))
            self._last_label = int(torch.argmax(probs).item())
            if self._is_violent:
                self._is_violent = bool(self._last_conf >= self._release_threshold())
            else:
                self._is_violent = bool(self._last_conf >= self.threshold)

            latency = (time.perf_counter() - start_time) * 1000
            print(
                "[AI] Latency: "
                f"{latency:.1f}ms | Raw: {self._last_raw_conf:.2f} | "
                f"Cal: {self._last_calibrated_conf:.2f} | Smooth: {self._last_conf:.2f}"
            )
        except Exception as exc:
            print(f"[AI] Inference error: {exc}")
        finally:
            with self._inference_lock:
                self._inference_running = False

    def _release_threshold(self) -> float:
        return max(0.05, min(self.threshold, self.threshold - self._hysteresis_margin))

    def _calibrate_confidence(self, logits: torch.Tensor, raw_conf: float) -> float:
        try:
            if logits.ndim != 2 or logits.shape[1] < 2:
                return float(raw_conf)

            row = logits[0]
            violence_logit = float(row[VIOLENCE_CLS].item())
            other_indices = [idx for idx in range(row.shape[0]) if idx != VIOLENCE_CLS]
            if not other_indices:
                return float(raw_conf)

            other_logits = row[other_indices]
            other_max = float(torch.max(other_logits).item())
            margin = ((violence_logit - other_max) + self._logit_bias) / max(0.05, self._logit_temp)
            margin = float(np.clip(margin, -20.0, 20.0))
            calibrated = 1.0 / (1.0 + np.exp(-margin))
            return float(max(0.0, min(1.0, calibrated)))
        except Exception:
            return float(raw_conf)

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        if not self.enabled:
            return frame.copy()

        self._buffer.append(frame)
        self._counter += 1

        if len(self._buffer) == WINDOW_SIZE and self._counter % self.stride == 0:
            should_start = False
            with self._inference_lock:
                if not self._inference_running:
                    self._inference_running = True
                    should_start = True
            if should_start:
                window = list(self._buffer)
                threading.Thread(target=self._infer_window, args=(window,), daemon=True).start()

        return frame.copy()
