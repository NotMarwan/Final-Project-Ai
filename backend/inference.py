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
        try:
            from models.multi_angle_x3d import MultiAngleX3D
            self.model = MultiAngleX3D(
                num_classes=num_classes,
                use_angle_augmentation=True,
                dropout_rate=0.3,
            )
        except ImportError:
            # Fallback if multi_angle module not available
            self._build_fallback(num_classes)
    
    def _build_fallback(self, num_classes: int):
        try:
            from torchvision.models.video import x3d_m
            self.model = x3d_m(weights=None)
            if hasattr(self.model, "blocks") and len(self.model.blocks) > 5:
                if hasattr(self.model.blocks[5], "proj"):
                    in_features = self.model.blocks[5].proj.in_features
                    self.model.blocks[5].proj = nn.Linear(in_features, num_classes)
        except Exception:
            from torchvision.models.video import r2plus1d_18
            self.model = r2plus1d_18(weights=None)
            if hasattr(self.model, "fc"):
                in_features = self.model.fc.in_features
                self.model.fc = nn.Linear(in_features, num_classes)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
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
    def __init__(self, num_classes: int = 6):

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

# Threat Category Mapping
THREAT_CATEGORIES = {
    0: "violence",
    1: "weapon",
    2: "crowd_surge",
    3: "fall",
    4: "intrusion",
    5: "loitering"
}

CALIBRATION_PROFILE = load_calibration_profile(base_dir=Path(__file__).resolve().parent)
VIOLENCE_CLS = int(os.getenv("VIOLENCE_CLASS_INDEX", str(CALIBRATION_PROFILE.get("classIndex", 1))))
VIOLENCE_TEMP = max(0.05, float(os.getenv("VIOLENCE_LOGIT_TEMPERATURE", str(CALIBRATION_PROFILE.get("logitTemperature", 1.0)))))
VIOLENCE_LOGIT_BIAS = float(os.getenv("VIOLENCE_LOGIT_BIAS", str(CALIBRATION_PROFILE.get("logitBias", 0.0))))
CONF_EMA_ALPHA = float(os.getenv("VIOLENCE_CONFIDENCE_EMA_ALPHA", str(CALIBRATION_PROFILE.get("emaAlpha", 0.45))))
HYSTERESIS_MARGIN = float(os.getenv("VIOLENCE_HYSTERESIS_MARGIN", str(CALIBRATION_PROFILE.get("hysteresisMargin", 0.08))))

# Cache for resized frames — keyed by (frame_id, size) for O(1) lookup
_FRAME_CACHE_LIMIT = 50
_frame_cache_keys: deque = deque()
_frame_cache: dict = {}


def cached_resize(frame: np.ndarray, size: int) -> np.ndarray:
    """Resize frame with lightweight caching using frame object identity."""
    cache_key = (id(frame), size)
    cached = _frame_cache.get(cache_key)
    if cached is not None:
        return cached
    resized = cv2.resize(frame, (size, size), interpolation=cv2.INTER_LINEAR)
    _frame_cache[cache_key] = resized
    _frame_cache_keys.append(cache_key)
    if len(_frame_cache_keys) > _FRAME_CACHE_LIMIT:
        old_key = _frame_cache_keys.popleft()
        _frame_cache.pop(old_key, None)
    return resized

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
        img = cached_resize(frame, 182)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        start = (182 - 160) // 2
        img = img[start:start+160, start:start+160].astype(np.float32) / 255.0
        img = (img - MEAN) / STD
        processed.append(img)
    
    # stack to tensor (1, 3, 32, 160, 160)
    tensor = np.stack(processed, axis=0).transpose(3, 0, 1, 2)
    return torch.from_numpy(tensor).unsqueeze(0)

def preprocess_window_multi_angle(frames: list[np.ndarray], target_angle: str = "eye_level") -> torch.Tensor:
    """
    Preprocess with angle-specific augmentations.
    target_angle: "eye_level" (170cm), "high" (>170cm), "low" (<170cm)
    """
    processed = []
    for frame in frames:
        frame = ensure_bgr(frame)
        # Resize to 182x182 then center crop to 160x160
        img = cached_resize(frame, 182)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        start = (182 - 160) // 2
        img = img[start:start+160, start:start+160].astype(np.float32) / 255.0
        img = (img - MEAN) / STD
        processed.append(img)
    
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
        self._state_lock = threading.Lock()  # Protects _last_conf, _is_violent etc.

        print(f"[AI] Initializing X3D-M on {device}...")
        try:
            self.model = X3DViolenceModel(num_classes=2).to(device)
            print(f"[AI] Model architecture created.")
            if os.path.exists(weights_path):
                print(f"[AI] Loading weights from {weights_path}...")
                state = torch.load(weights_path, map_location=device, weights_only=True)
                print(f"[AI] Weights loaded into memory.")
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
                print(f"[AI] Loading legacy weights from {weights_path}...")
                state = torch.load(weights_path, map_location=device, weights_only=True)
                print("[AI] Legacy weights loaded into memory.")
                # Unwrap the model state dict if it's a full checkpoint
                if "model_state_dict" in state:
                    state = state["model_state_dict"]
                self.model.load_state_dict(state)
                print("[AI] Legacy SlowFast model weights loaded successfully.")
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
    def _infer_window_async(self, window_frames: list[np.ndarray]) -> None:
        """Async inference that doesn't block frame capture."""
        try:
            start_time = time.perf_counter()
            
            if self.is_x3d:
                input_tensor = preprocess_window(window_frames).to(self.device)
                logits = self.model(input_tensor)
            else:
                # Legacy path
                processed = []
                for f in window_frames:
                    f = ensure_bgr(f)
                    img = cached_resize(f, 224)
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
                    processed.append((img - MEAN) / STD)
                fast = torch.from_numpy(np.stack(processed).transpose(0, 3, 1, 2)).unsqueeze(0).to(self.device)
                slow = fast[:, ::4, :, :, :]
                logits = self.model(slow, fast)

            probs = F.softmax(logits, dim=-1)[0]
            raw_conf = probs[VIOLENCE_CLS].item()
            calibrated_conf = self._calibrate_confidence(logits, raw_conf)
            
            with self._state_lock:
                self._last_raw_conf = raw_conf
                self._last_calibrated_conf = calibrated_conf
                
                # EMA smoothing after warmup
                if self._counter > WINDOW_SIZE:
                    smoothed_conf = (self._ema_alpha * calibrated_conf) + ((1.0 - self._ema_alpha) * self._last_conf)
                else:
                    smoothed_conf = calibrated_conf
                    
                self._last_conf = float(max(0.0, min(1.0, smoothed_conf)))
                self._last_label = int(torch.argmax(probs).item())
                self._last_threat_type = THREAT_CATEGORIES.get(self._last_label, "unknown")
                
                # Hysteresis for state change
                if self._is_violent:
                    self._is_violent = bool(self._last_conf >= self._release_threshold())
                else:
                    self._is_violent = bool(self._last_conf >= self.threshold)

            
            latency = (time.perf_counter() - start_time) * 1000
            print(f"[AI] Latency: {latency:.1f}ms | Conf: {self._last_conf:.2f}")
            
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

        self._counter += 1
        self._buffer.append(frame)

        # Only run inference on stride intervals and when not already running
        if len(self._buffer) == WINDOW_SIZE and self._counter % self.stride == 0:
            should_start = False
            with self._inference_lock:
                if not self._inference_running:
                    self._inference_running = True
                    should_start = True
            
            if should_start:
                # Use the latest complete window
                window = list(self._buffer)
                # Run inference in background thread
                threading.Thread(
                    target=self._infer_window_async, 
                    args=(window,), 
                    daemon=True
                ).start()

        # Return frame immediately - don't wait for inference
        return frame.copy()

