"""
inference.py — Violence Detection Inference Script
====================================================
Senior Computer Vision Engineer — Production-Ready

ARCHITECTURE IDENTITY (R8 reconciliation, WT-19 / S-02, verified 2026-09-29):
  The shipped checkpoint `backend/best_model.pt` is a pytorchvideo SlowFast R-50
  (`slowfast_r50`) backbone + 2304-d head ("ViolenceDetector"). The legacy
  single-path fallback is torchvision R(2+1)D-18 (class name `X3DViolenceModel`
  is a historical misnomer; it is NOT X3D). Runtime labels come from
  `identify_checkpoint()` / each class's `ARCHITECTURE_ID`; never label a loaded
  engine "X3D" (F-29 wording drift).
"""

import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
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
    """Legacy single-path fallback. NOT X3D: torchvision R(2+1)D-18.

    The class name is a string contract in S-21/S-05 tooling
    (`model_class == "X3DViolenceModel"`); the identity fields below are the
    truthful ones and must be used for any label or API text (F-29).
    """

    ARCHITECTURE_ID = "torchvision_r2plus1d_18_multiangle"
    ARCHITECTURE_LABEL = "R(2+1)D-18 (torchvision) single-path fallback (legacy class name X3DViolenceModel; not X3D)"

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
    """Two-pathway ResNet backbone: pytorchvideo `slowfast_r50` when the local
    hub cache is present, else torchvision `r3d_18` (single pathway). The
    built variant is recorded in `self.architecture_id` (R8 identity)."""

    ARCHITECTURE_ID_HUB = "pytorchvideo_slowfast_r50"
    ARCHITECTURE_ID_FALLBACK = "torchvision_r3d_18_fallback"

    def __init__(self, pretrained: bool = False):
        super().__init__()
        try:
            from einops import rearrange
            hub_path = Path(torch.hub.get_dir()) / "facebookresearch_pytorchvideo_main"
            if not (hub_path / "hubconf.py").is_file():
                raise FileNotFoundError("cached pytorchvideo architecture is unavailable")
            self.backbone = torch.hub.load(
                str(hub_path),
                "slowfast_r50",
                source="local",
                pretrained=False,
            )
            self.backbone.blocks[-1] = nn.Identity()
            self.out_dim = 2304
            self.architecture_id = self.ARCHITECTURE_ID_HUB
        except Exception:
            import torchvision.models.video as vm
            m = vm.r3d_18(weights=None)
            self.backbone = nn.Sequential(*list(m.children())[:-2])
            self.pool = nn.AdaptiveAvgPool3d((1, 1, 1))
            self.out_dim = 512
            self.architecture_id = self.ARCHITECTURE_ID_FALLBACK

    def forward(self, slow: torch.Tensor, fast: torch.Tensor) -> torch.Tensor:
        from einops import rearrange
        if hasattr(self, "pool"):
            return self.pool(self.backbone(rearrange(fast, "b t c h w -> b c t h w"))).flatten(1)
        return self.backbone([
            rearrange(slow, "b t c h w -> b c t h w"),
            rearrange(fast, "b t c h w -> b c t h w"),
        ]).flatten(1)

class ViolenceDetector(nn.Module):
    """Two-pathway violence classifier (shipped checkpoint architecture).

    Identity is the built backbone's `architecture_id`
    (`pytorchvideo_slowfast_r50` for `backend/best_model.pt`)."""

    def __init__(self, num_classes: int = 6):

        super().__init__()
        self.sf = SlowFastBackbone(pretrained=False)
        dim = self.sf.out_dim
        self.architecture_id = self.sf.architecture_id
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
FRAME_SIZE   = 160   # single-path (R(2+1)D) target resolution
DEFAULT_WINDOW_SIZE = 32
SLOWFAST_FRAME_SIZE = 224
SLOWFAST_PREPROCESS_WORKERS = int(
    os.getenv("AI_SENTINEL_VIOLENCE_PREPROCESS_WORKERS", "4")
)
if not 1 <= SLOWFAST_PREPROCESS_WORKERS <= 4:
    raise ValueError("AI_SENTINEL_VIOLENCE_PREPROCESS_WORKERS must be between 1 and 4")

def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not lo <= value <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi} (got {value})")
    return value

# Temporal sampling (R3 window/stride re-derivation). Window is configurable so
# the sweep {16,32} x stride {4,8,16} (+ 50% overlap variant) can run without
# code changes; G-07 window-integrity accounting is enforced per window either
# way (see assess_window_integrity). Stride is passed per pipeline instance
# (constructor `stride`, or `STRIDE` env / config.model.stride via api.py).
WINDOW_SIZE = _env_int("AI_SENTINEL_VIOLENCE_WINDOW_SIZE", DEFAULT_WINDOW_SIZE, 8, 64)
# Constructor default only; every in-tree caller passes `stride` explicitly
# (api.py from `STRIDE` env / config.model.stride). Legacy default is 16.
STRIDE_DEFAULT = _env_int("AI_SENTINEL_VIOLENCE_STRIDE", 16, 1, 256)

# Temporal ensemble over stride-offset windows (R4). K=1 keeps the legacy
# single-window behaviour exactly (one producer observation, one decision vote
# per completion — never K votes; see SC-7 notes in the handoff).
ENSEMBLE_K = _env_int("AI_SENTINEL_VIOLENCE_ENSEMBLE_K", 1, 1, 8)
ENSEMBLE_AGG = os.getenv("AI_SENTINEL_VIOLENCE_ENSEMBLE_AGG", "max").strip().lower()
if ENSEMBLE_AGG not in ("max", "mean"):
    raise ValueError("AI_SENTINEL_VIOLENCE_ENSEMBLE_AGG must be 'max' or 'mean'")

# Perception-level benign-motion rejection (item 5). Default OFF: no behaviour
# change unless enabled. `block` forces score 0 below the motion floor; `damp`
# scales the score by motion/floor. The floor is a perception constant in mean
# absolute gray-level frame difference (0..255); decision thresholds stay in
# config/thresholds.toml (SC-5, single authority).
MOTION_GATE_MODE = os.getenv("AI_SENTINEL_VIOLENCE_MOTION_GATE", "off").strip().lower()
if MOTION_GATE_MODE not in ("off", "damp", "block"):
    raise ValueError("AI_SENTINEL_VIOLENCE_MOTION_GATE must be 'off', 'damp' or 'block'")
MOTION_GATE_FLOOR = float(os.getenv("AI_SENTINEL_VIOLENCE_MOTION_FLOOR", "1.0"))
if MOTION_GATE_FLOOR < 0:
    raise ValueError("AI_SENTINEL_VIOLENCE_MOTION_FLOOR must be >= 0")
# CUDA experiments stay opt-in: isolated parity runs were faster, but the full replay
# pipeline (bench/results/perf-r3-final-2026-09-26) had worse p95 on every model.
VIOLENCE_CUDNN_BENCHMARK = os.getenv("AI_SENTINEL_VIOLENCE_CUDNN_BENCHMARK", "0") == "1"
VIOLENCE_CHANNELS_LAST_3D = os.getenv("AI_SENTINEL_VIOLENCE_CHANNELS_LAST_3D", "0") == "1"
VIOLENCE_PINNED_HOST_TENSOR = os.getenv("AI_SENTINEL_VIOLENCE_PINNED_HOST_TENSOR", "0") == "1"
VIOLENCE_FP16_AUTOCAST = os.getenv("AI_SENTINEL_VIOLENCE_FP16_AUTOCAST", "0") == "1"
VIOLENCE_WARMUP_AT_LOAD = os.getenv("AI_SENTINEL_VIOLENCE_WARMUP_AT_LOAD", "0") == "1"
_SLOWFAST_PREPROCESS_EXECUTOR = ThreadPoolExecutor(
    max_workers=SLOWFAST_PREPROCESS_WORKERS,
    thread_name_prefix="violence-preprocess",
)

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
    """Resize current pixels; capture buffers and caller output are mutable.

    Do not cache by object identity: camera-buffer reuse and Python ID recycling
    otherwise return old pixels. The retained function name preserves callers.
    """
    return cv2.resize(frame, (size, size), interpolation=cv2.INTER_LINEAR)


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


def _preprocess_slowfast_frame(frame: np.ndarray) -> np.ndarray:
    frame = ensure_bgr(frame)
    image = cached_resize(frame, SLOWFAST_FRAME_SIZE)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return (image - MEAN) / STD


def preprocess_slowfast_window(frames: list[np.ndarray]) -> torch.Tensor:
    """Preserve legacy FP32 preprocessing while parallelizing independent frames."""
    processed = list(_SLOWFAST_PREPROCESS_EXECUTOR.map(_preprocess_slowfast_frame, frames))
    tensor = np.stack(processed).transpose(0, 3, 1, 2)
    return torch.from_numpy(tensor).unsqueeze(0)


def _slowfast_channels_last_3d(tensor: torch.Tensor) -> torch.Tensor:
    """Lay out the N,C,T,H,W view while preserving the N,T,C,H,W API."""
    return tensor.permute(0, 2, 1, 3, 4).contiguous(
        memory_format=torch.channels_last_3d
    ).permute(0, 2, 1, 3, 4)

# ──────────────────────────────────────────────────────────────────────────────
# 2b. Temporal-window integrity (G-07) and checkpoint identity (R8)
# ──────────────────────────────────────────────────────────────────────────────

def assess_window_integrity(
    sample_stamps: list[float],
    window_size: int,
    nominal_fps: float,
    has_clock: bool = True,
) -> dict:
    """G-07 temporal-window integrity for one candidate window.

    A window is valid iff exactly `window_size` samples exist and, when a
    source clock is available, its wall-clock span is within ±10 % of the
    nominal span (window_size-1)/fps with every inter-frame gap > 0 and
    <= 2.1/fps. The returned dict is additive-safe for `window_status`.
    """
    fps = max(float(nominal_fps), 1.0)
    nominal = (window_size - 1) / fps
    gap_bound = 2.1 / fps
    span = (
        float(sample_stamps[-1] - sample_stamps[0])
        if len(sample_stamps) > 1
        else 0.0
    )
    gaps = [float(b - a) for a, b in zip(sample_stamps, list(sample_stamps)[1:])]
    reasons: list[str] = []
    if len(sample_stamps) != window_size:
        reasons.append("incomplete")
    if has_clock and len(sample_stamps) == window_size:
        if abs(span - nominal) > nominal * 0.10:
            reasons.append("span-out-of-tolerance")
        if gaps and min(gaps) <= 0:
            reasons.append("non-increasing-stamp")
        if gaps and max(gaps) > gap_bound:
            reasons.append("gap-over-bound")
    return {
        "valid": not reasons,
        "span_seconds": span,
        "nominal_span_seconds": nominal,
        "span_tolerance_seconds": nominal * 0.10,
        "max_gap_seconds": max(gaps) if gaps else 0.0,
        "gap_bound_seconds": gap_bound,
        "integrity_reason": ",".join(reasons) if reasons else "ok",
    }


def identify_checkpoint(state_dict: dict) -> dict:
    """Truthful architecture identification from checkpoint keys/shapes (R8).

    Returns {family, variant, num_classes, head_dim, confidence} where family is
    one of "slowfast" | "r2plus1d-multiangle" | "unknown". Detection is purely
    structural (state-dict keys / tensor shapes), never filename-based.
    """
    if not isinstance(state_dict, dict) or not state_dict:
        return {"family": "unknown", "variant": "unknown", "num_classes": None,
                "head_dim": None, "confidence": "empty-state-dict"}
    keys = list(state_dict.keys())

    def _shape(key):
        value = state_dict.get(key)
        shape = getattr(value, "shape", None)
        return tuple(shape) if shape is not None else None

    # Shipped checkpoints wrap keys under sf.* (ViolenceDetector).
    if any(k.startswith("sf.backbone.blocks.") and "multipathway" in k for k in keys):
        head = _shape("head.1.weight")
        stem = _shape("sf.backbone.blocks.0.multipathway_blocks.0.conv.weight")
        variant = "pytorchvideo_slowfast_r50"
        if stem and len(stem) == 5 and stem[2] == 1:
            variant = "pytorchvideo_slowfast_r50"  # fast-pathway stem (1,7,7)
        return {
            "family": "slowfast",
            "variant": variant,
            "num_classes": _shape("head.4.weight")[0] if _shape("head.4.weight") else None,
            "head_dim": head[1] if head else None,
            "confidence": "structural-keys",
        }
    if any(k.startswith("sf.backbone.") for k in keys):
        head = _shape("head.1.weight")
        return {
            "family": "slowfast",
            "variant": "torchvision_r3d_18_fallback",
            "num_classes": _shape("head.4.weight")[0] if _shape("head.4.weight") else None,
            "head_dim": head[1] if head else None,
            "confidence": "structural-keys",
        }
    if any(k.startswith("backbone.") for k in keys):
        head = _shape("backbone.fc.weight")
        has_stn = any(k.startswith("spatial_transformer.") for k in keys)
        return {
            "family": "r2plus1d-multiangle",
            "variant": "torchvision_r2plus1d_18_multiangle"
                       + ("-with-legacy-spatial-transformer" if has_stn else ""),
            "num_classes": head[0] if head else None,
            "head_dim": None,
            "confidence": "structural-keys",
        }
    return {"family": "unknown", "variant": "unknown", "num_classes": None,
            "head_dim": None, "confidence": "no-known-key-families"}


# ──────────────────────────────────────────────────────────────────────────────
# 3. Inference Pipeline
# ──────────────────────────────────────────────────────────────────────────────

class ViolenceInferencePipeline:
    _class_index = VIOLENCE_CLS

    def __init__(self, weights_path: str, device: torch.device, threshold: float = 0.75,
                 stride: int = STRIDE_DEFAULT, window_size: int | None = None,
                 ensemble_k: int | None = None, ensemble_agg: str | None = None):
        self.device    = device
        self.threshold = threshold
        self.stride    = stride
        self.window_size = int(window_size) if window_size is not None else WINDOW_SIZE
        if not 8 <= self.window_size <= 64:
            raise ValueError(f"window_size must be in [8, 64] (got {self.window_size})")
        self._ensemble_k = int(ensemble_k) if ensemble_k is not None else ENSEMBLE_K
        if not 1 <= self._ensemble_k <= 8:
            raise ValueError(f"ensemble_k must be in [1, 8] (got {self._ensemble_k})")
        self._ensemble_agg = (ensemble_agg or ENSEMBLE_AGG).strip().lower()
        if self._ensemble_agg not in ("max", "mean"):
            raise ValueError("ensemble_agg must be 'max' or 'mean'")
        self._motion_gate_mode = MOTION_GATE_MODE
        self._motion_gate_floor = MOTION_GATE_FLOOR
        # Legacy flag, retained for S-05/train_calibration.py consumers: True iff
        # the single-path R(2+1)D model is loaded. NOT an X3D claim — see
        # `architecture_id` / `architecture_label` for the truthful identity.
        self.is_x3d    = False
        self.architecture_id = "unloaded"
        self.architecture_label = "unloaded"
        self.checkpoint_identity = {}
        self.enabled   = True
        self.disabled_reason = ""
        self._inference_running = False
        self._generation = 0
        self._observation_id = 0
        self._window_id = 0
        self._last_observed_at = 0.0
        self._last_source_capture_at = 0.0
        self._completed_at = 0.0
        self.last_error = ""
        self.window_status = {"frames_collected": 0, "frames_required": self.window_size, "valid": False, "span_seconds": 0.0}
        self._completed_window_fields: dict = {}
        self._sample_times = deque(maxlen=self.window_size)
        self._buffer = deque(maxlen=self.window_size)
        self._window_scores = deque(maxlen=max(1, self._ensemble_k))
        self._window_score_history = deque(maxlen=512)
        self._onset_candidate_timestamp = None
        self._onset_candidate_window_id = None
        self._last_logit_margin = 0.0
        self._last_logits = ()
        self._inference_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="violence")
        self._inference_lock = threading.Lock()
        self._state_lock = threading.Lock()  # Protects _last_conf, _is_violent etc.

        print(f"[AI] Inspecting local violence checkpoint for {device}...")
        checkpoint_state = None
        checkpoint_is_slowfast = False
        try:
            if not os.path.exists(weights_path):
                raise FileNotFoundError(weights_path)
            checkpoint = torch.load(weights_path, map_location="cpu", weights_only=True)
            checkpoint_state = self._extract_state_dict(checkpoint)
            self.checkpoint_identity = identify_checkpoint(checkpoint_state)
            checkpoint_is_slowfast = self._is_slowfast_state_dict(checkpoint_state)
            architecture = (
                "SlowFast R-50 two-pathway (pytorchvideo slowfast_r50)"
                if checkpoint_is_slowfast
                else "R(2+1)D-18 single-path (legacy class name X3DViolenceModel; not X3D)"
            )
            print(f"[AI] Checkpoint identity: {self.checkpoint_identity}")
            print(f"[AI] Building local {architecture} architecture (pretrained=False)...")
            candidate = (
                ViolenceDetector(num_classes=2)
                if checkpoint_is_slowfast
                else X3DViolenceModel(num_classes=2)
            )
            self._load_compatible(candidate, checkpoint_state)
            print(f"[AI] {architecture} weights matched; transferring model to {device}...")
            self.model = candidate.to(device)
            self.is_x3d = not checkpoint_is_slowfast
            self.architecture_id = getattr(candidate, "architecture_id", "unknown")
            self.architecture_label = architecture
            print(f"[AI] {architecture} model loaded successfully (architecture_id={self.architecture_id}).")
        except Exception as x3d_exc:
            self.model = None
            if checkpoint_is_slowfast:
                fallback_exc = x3d_exc
            else:
                print("[AI] Falling back to local Legacy SlowFast model.")
                fallback_exc = None
            try:
                if fallback_exc is not None:
                    raise fallback_exc
                if checkpoint_state is None:
                    checkpoint = torch.load(weights_path, map_location="cpu", weights_only=True)
                    checkpoint_state = self._extract_state_dict(checkpoint)
                    self.checkpoint_identity = identify_checkpoint(checkpoint_state)
                candidate = ViolenceDetector(num_classes=2)
                self._load_compatible(candidate, checkpoint_state)
                self.model = candidate.to(device)
                self.architecture_id = getattr(candidate, "architecture_id", "unknown")
                self.architecture_label = "SlowFast two-pathway (fallback load path)"
                print(f"[AI] Local Legacy SlowFast model loaded successfully (architecture_id={self.architecture_id}).")
            except Exception as e:
                print(f"[AI] Critical: Fallback failed: {e}")
                self.enabled = False
                self.model = None
                self.disabled_reason = f"r2plus1d={type(x3d_exc).__name__}; legacy={type(e).__name__}"
                print(f"[AI] Stream-only mode enabled (reason: {self.disabled_reason}).")
        
        if self.model is not None:
            self.model.eval()
        self._last_label = 0
        self._last_conf  = 0.0
        self._last_raw_conf = 0.0
        self._last_calibrated_conf = 0.0
        self._is_violent = False
        self._counter    = 0
        self._ema_alpha = max(0.05, min(0.95, CONF_EMA_ALPHA))
        self._hysteresis_margin = max(0.0, min(0.30, HYSTERESIS_MARGIN))
        self._configure_score_profile(weights_path)
        self.warmup_ms = 0.0
        if self.model is not None:
            self._configure_cuda_inference()

    def architecture_identity(self) -> dict:
        """Truthful loaded-architecture identity for labels/telemetry (R8)."""
        return {
            "architectureId": self.architecture_id,
            "architectureLabel": self.architecture_label,
            "legacyIsX3dFlag": self.is_x3d,
            "checkpointIdentity": dict(self.checkpoint_identity),
            "windowSize": self.window_size,
            "stride": self.stride,
            "ensembleK": self._ensemble_k,
            "ensembleAgg": self._ensemble_agg,
        }

    @staticmethod
    def _drop_legacy_dead_keys(state_dict: dict) -> dict:
        """Strip legacy `spatial_transformer.*` keys (removed dead STN module).

        Those keys belonged to a no-op spatial transformer whose forward pass
        discarded its output; keeping load compatibility for old checkpoints
        without keeping the 16.4M dead parameters.
        """
        legacy = [k for k in state_dict if k.startswith("spatial_transformer.")]
        if legacy:
            print(f"[AI] Dropping {len(legacy)} legacy spatial_transformer.* keys (module removed; outputs unchanged).")
            state_dict = {k: v for k, v in state_dict.items() if k not in set(legacy)}
        return state_dict

    def _configure_cuda_inference(self) -> None:
        if self.device.type != "cuda":
            return
        if VIOLENCE_CUDNN_BENCHMARK:
            torch.backends.cudnn.benchmark = True
        if VIOLENCE_CHANNELS_LAST_3D:
            self.model.to(memory_format=torch.channels_last_3d)
        if VIOLENCE_WARMUP_AT_LOAD:
            started = time.perf_counter()
            try:
                with torch.inference_mode():
                    if self.is_x3d:
                        sample = torch.zeros(
                            (1, 3, self.window_size, FRAME_SIZE, FRAME_SIZE),
                            device=self.device,
                        )
                        if VIOLENCE_CHANNELS_LAST_3D:
                            sample = sample.contiguous(memory_format=torch.channels_last_3d)
                        self._forward_with_optional_autocast(sample)
                    else:
                        fast_cpu = torch.zeros(
                            (1, self.window_size, 3, SLOWFAST_FRAME_SIZE, SLOWFAST_FRAME_SIZE),
                            dtype=torch.float32,
                        )
                        if VIOLENCE_PINNED_HOST_TENSOR:
                            fast_cpu = fast_cpu.pin_memory()
                        fast = fast_cpu.to(self.device, non_blocking=VIOLENCE_PINNED_HOST_TENSOR)
                        if VIOLENCE_CHANNELS_LAST_3D:
                            fast = _slowfast_channels_last_3d(fast)
                        slow = fast[:, ::4, :, :, :]
                        if VIOLENCE_CHANNELS_LAST_3D:
                            slow = _slowfast_channels_last_3d(slow)
                        self._forward_with_optional_autocast(slow, fast)
                torch.cuda.synchronize(self.device)
                self.warmup_ms = (time.perf_counter() - started) * 1000
            except Exception as exc:
                self.warmup_ms = (time.perf_counter() - started) * 1000
                print(f"[AI] CUDA warmup skipped: {type(exc).__name__}")

    def _forward_with_optional_autocast(self, *inputs: torch.Tensor) -> torch.Tensor:
        if self.device.type == "cuda" and VIOLENCE_FP16_AUTOCAST:
            with torch.autocast("cuda", dtype=torch.float16):
                return self.model(*inputs)
        return self.model(*inputs)

    def reset(self):
        self._generation += 1
        self._sample_times.clear()
        self._buffer.clear()
        self._window_scores.clear()
        self._last_label = 0
        self._last_conf = 0.0
        self._last_raw_conf = 0.0
        self._last_calibrated_conf = 0.0
        self._last_logit_margin = 0.0
        self._last_logits = ()
        self._last_source_capture_at = 0.0
        self._is_violent = False
        self._counter = 0
        self._onset_candidate_timestamp = None
        self._onset_candidate_window_id = None
        self._completed_window_fields = {}
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

    @staticmethod
    def _is_slowfast_state_dict(state_dict) -> bool:
        """True for any two-pathway (ViolenceDetector) checkpoint.

        Accepts both the pytorchvideo `slowfast_r50` key layout
        (`sf.backbone.blocks.*.multipathway*`) and the r3d_18 fallback layout
        (`sf.backbone.<idx>.*`), so variant is reported by `identify_checkpoint`
        while routing stays correct.
        """
        if not isinstance(state_dict, dict):
            return False
        return any(key.startswith("sf.") for key in state_dict)

    @classmethod
    def _load_compatible(cls, candidate: nn.Module, state_dict: dict) -> None:
        """Strict state-dict load with two documented legacy tolerances.

        1. `spatial_transformer.*` keys (removed no-op module) are dropped.
        2. Checkpoints saved from bare `MultiAngleX3D` (keys `backbone.*`) load
           into `X3DViolenceModel.model` instead of the wrapper (`model.*`).
        Anything else stays strict: silent shape/key drift is not tolerated.
        """
        state_dict = cls._drop_legacy_dead_keys(state_dict)
        try:
            candidate.load_state_dict(state_dict)
            return
        except RuntimeError:
            inner = getattr(candidate, "model", None)
            native_keys = ("backbone.", "fc.")
            if inner is None or not any(k.startswith(native_keys) for k in state_dict):
                raise
            print("[AI] Checkpoint carries bare MultiAngleX3D keys; loading into wrapper.model.")
            inner.load_state_dict(state_dict)

    @torch.inference_mode()
    def _infer_window_async(
        self,
        window_frames: list[np.ndarray],
        observed_at: float = 0.0,
        generation=None,
        source_captured_at: float | None = None,
        window_id: int = 0,
        window_start_timestamp: float | None = None,
        window_end_timestamp: float | None = None,
        window_integrity: dict | None = None,
    ) -> None:
        """Async inference that doesn't block frame capture.

        One completed evaluation produces exactly one producer observation
        (one `violence_observation_id` bump => one decision vote): the temporal
        ensemble aggregates scores over the last K stride-offset windows and
        never emits per-member votes (R4, SC-7).
        """
        try:
            start_time = time.perf_counter()
            
            if self.is_x3d:
                input_cpu = preprocess_window(window_frames)
                if self.device.type == "cuda" and VIOLENCE_PINNED_HOST_TENSOR:
                    input_cpu = input_cpu.pin_memory()
                input_tensor = input_cpu.to(
                    self.device,
                    non_blocking=self.device.type == "cuda" and VIOLENCE_PINNED_HOST_TENSOR,
                )
                if self.device.type == "cuda" and VIOLENCE_CHANNELS_LAST_3D:
                    input_tensor = input_tensor.contiguous(memory_format=torch.channels_last_3d)
                logits = self._forward_with_optional_autocast(input_tensor)
            else:
                fast_cpu = preprocess_slowfast_window(window_frames)
                if self.device.type == "cuda" and VIOLENCE_PINNED_HOST_TENSOR:
                    fast_cpu = fast_cpu.pin_memory()
                fast = fast_cpu.to(
                    self.device,
                    non_blocking=self.device.type == "cuda" and VIOLENCE_PINNED_HOST_TENSOR,
                )
                if self.device.type == "cuda" and VIOLENCE_CHANNELS_LAST_3D:
                    fast = _slowfast_channels_last_3d(fast)
                slow = fast[:, ::4, :, :, :]
                if self.device.type == "cuda" and VIOLENCE_CHANNELS_LAST_3D:
                    slow = _slowfast_channels_last_3d(slow)
                logits = self._forward_with_optional_autocast(slow, fast)

            logits = logits.float()
            probs = F.softmax(logits, dim=-1)[0]
            raw_conf = probs[self._class_index].item()
            calibrated_conf = self._calibrate_confidence(logits, raw_conf)
            logits_list = [float(v) for v in logits[0].tolist()]
            logit_margin = self._logit_margin_of(logits, self._class_index)
            motion_energy = self._window_motion_energy(window_frames)
            gated_conf, motion_gated = self._apply_motion_gate(calibrated_conf, motion_energy)

            with self._state_lock:
                if generation is not None and generation != self._generation:
                    return
                self._observation_id += 1
                self._last_observed_at = observed_at or time.monotonic()
                self._last_source_capture_at = (
                    float(source_captured_at)
                    if source_captured_at is not None
                    else self._last_observed_at
                )
                self._completed_at = time.monotonic()
                self.last_error = ""
                self._last_raw_conf = raw_conf
                self._last_calibrated_conf = calibrated_conf
                self._last_logit_margin = logit_margin
                self._last_logits = tuple(logits_list)
                self._last_motion_energy = motion_energy
                self._last_motion_gated = motion_gated

                # Temporal ensemble over the last K stride-offset window
                # scores (R4). K=1 => identical to legacy single-window score.
                self._window_scores.append(float(gated_conf))
                members = list(self._window_scores)
                if self._ensemble_agg == "mean":
                    ensemble_score = sum(members) / len(members)
                else:
                    ensemble_score = max(members)
                ensemble_spread = float(np.std(members)) if len(members) > 1 else 0.0
                self._last_ensemble_score = float(ensemble_score)
                self._last_ensemble_spread = ensemble_spread

                # EMA smoothing after warmup
                if self._counter > self.window_size:
                    smoothed_conf = (self._ema_alpha * ensemble_score) + ((1.0 - self._ema_alpha) * self._last_conf)
                else:
                    smoothed_conf = ensemble_score
                    
                self._last_conf = float(max(0.0, min(1.0, smoothed_conf)))
                self._last_label = int(torch.argmax(probs).item())
                self._last_threat_type = THREAT_CATEGORIES.get(self._last_label, "unknown")
                
                # Hysteresis for state change
                was_violent = self._is_violent
                if self._is_violent:
                    self._is_violent = bool(self._last_conf >= self._release_threshold())
                else:
                    self._is_violent = bool(self._last_conf >= self.threshold)

                # Onset-candidate identity (R7): first window of the current
                # candidate-positive run; cleared when the run releases.
                if self._is_violent and not was_violent:
                    self._onset_candidate_timestamp = (
                        float(window_start_timestamp)
                        if window_start_timestamp is not None
                        else self._last_observed_at
                    )
                    self._onset_candidate_window_id = int(window_id)
                elif not self._is_violent:
                    self._onset_candidate_timestamp = None
                    self._onset_candidate_window_id = None

                completed = {
                    "window_id": int(window_id),
                    "window_start_timestamp": (
                        float(window_start_timestamp)
                        if window_start_timestamp is not None else None
                    ),
                    "window_end_timestamp": (
                        float(window_end_timestamp)
                        if window_end_timestamp is not None else None
                    ),
                    "onset_candidate_timestamp": self._onset_candidate_timestamp,
                    "onset_candidate_window_id": self._onset_candidate_window_id,
                    # G-07 integrity of the submitted window (WT-12 runtime_contract
                    # window_integrity_fields: valid/frames_collected/frames_required/span_s).
                    "window_valid": (window_integrity or {}).get("valid"),
                    "window_frames_collected": (window_integrity or {}).get("frames_collected"),
                    "window_frames_required": (window_integrity or {}).get("frames_required"),
                    "window_span_seconds": (window_integrity or {}).get("span_seconds"),
                    "raw_conf": float(raw_conf),
                    "calibrated_conf": float(calibrated_conf),
                    "smoothed_conf": self._last_conf,
                    "ensemble_k": self._ensemble_k,
                    "ensemble_score": float(ensemble_score),
                    "ensemble_spread": ensemble_spread,
                    "motion_energy": motion_energy,
                    "motion_gated": bool(motion_gated),
                    "logit_margin": logit_margin,
                    "logits": list(logits_list),
                }
                self._completed_window_fields = completed
                self._window_score_history.append({
                    **completed,
                    "is_violent": bool(self._is_violent),
                    "threshold": float(self.threshold),
                })

            
            latency = (time.perf_counter() - start_time) * 1000
            print(f"[AI] Latency: {latency:.1f}ms | Conf: {self._last_conf:.2f}")
            
        except Exception as exc:
            self.last_error = type(exc).__name__
            print(f"[AI] Inference error: {type(exc).__name__}")
        finally:
            with self._inference_lock:
                self._inference_running = False

    def _release_threshold(self) -> float:

        return max(0.05, min(self.threshold, self.threshold - self._hysteresis_margin))

    @staticmethod
    def _logit_margin_of(logits: torch.Tensor, class_index: int | None = None) -> float:
        """Raw pre-temperature margin (violence logit - max other logit)."""
        if logits.ndim != 2 or logits.shape[1] < 2:
            return 0.0
        row = logits[0]
        class_index = VIOLENCE_CLS if class_index is None else class_index
        if not 0 <= class_index < row.shape[0]:
            return 0.0
        violence_logit = float(row[class_index].item())
        other_indices = [idx for idx in range(row.shape[0]) if idx != class_index]
        if not other_indices:
            return 0.0
        return violence_logit - float(torch.max(row[other_indices]).item())

    @staticmethod
    def _window_motion_energy(frames: list[np.ndarray]) -> float:
        """Mean absolute gray-level frame difference (0..255) over the window."""
        if len(frames) < 2:
            return 0.0
        prev = None
        total = 0.0
        for frame in frames:
            gray = ensure_bgr(frame)
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
            if prev is not None:
                total += float(np.abs(small - prev).mean())
            prev = small
        return total / (len(frames) - 1)

    def _apply_motion_gate(self, score: float, motion_energy: float) -> tuple[float, bool]:
        """Perception-level benign-motion rejection (item 5). Default off.

        `block`: score forced to 0 below the motion floor. `damp`: score scaled
        by motion/floor. The floor is a perception constant, not a decision
        threshold — decision thresholds remain in config/thresholds.toml.
        """
        if self._motion_gate_mode == "off" or self._motion_gate_floor <= 0:
            return score, False
        if motion_energy >= self._motion_gate_floor:
            return score, False
        if self._motion_gate_mode == "block":
            return 0.0, True
        ratio = max(0.0, min(1.0, motion_energy / self._motion_gate_floor))
        return score * ratio, True

    def _configure_score_profile(self, weights_path: str) -> None:
        # Class selection and score transforms must use the same model-bound
        # profile, including explicit checkpoints different from WEIGHTS_PATH.
        profile = load_calibration_profile(base_dir=Path(__file__).resolve().parent, model_path=weights_path)
        self._class_index = int(os.getenv("VIOLENCE_CLASS_INDEX", str(profile.get("classIndex", 1))))
        self._logit_temp = max(0.05, float(os.getenv("VIOLENCE_LOGIT_TEMPERATURE", str(profile.get("logitTemperature", 1.0)))))
        self._logit_bias = float(os.getenv("VIOLENCE_LOGIT_BIAS", str(profile.get("logitBias", 0.0))))

    def _calibrate_confidence(self, logits: torch.Tensor, raw_conf: float) -> float:
        try:
            if logits.ndim != 2 or logits.shape[1] < 2:
                return float(raw_conf)

            row = logits[0]
            violence_logit = float(row[self._class_index].item())
            other_indices = [idx for idx in range(row.shape[0]) if idx != self._class_index]
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

    def process_frame(
        self,
        frame: np.ndarray,
        captured_at=None,
        nominal_fps=30.0,
        source_captured_at=None,
    ) -> np.ndarray:
        if not self.enabled:
            return frame.copy()

        self._counter += 1
        self._buffer.append(frame)
        stamp = float(captured_at) if captured_at is not None else time.monotonic()
        self._sample_times.append(stamp)
        integrity = assess_window_integrity(
            list(self._sample_times),
            self.window_size,
            nominal_fps,
            has_clock=captured_at is not None,
        )
        # Legacy direct calls have no source clock contract (has_clock=False
        # above): only completeness is validated for them.
        valid = integrity["valid"]
        self.window_status = {
            **self._completed_window_fields,
            "frames_collected": len(self._buffer),
            "frames_required": self.window_size,
            "span_seconds": integrity["span_seconds"],
            "nominal_span_seconds": integrity["nominal_span_seconds"],
            "valid": valid,
            "span_tolerance_seconds": integrity["span_tolerance_seconds"],
            "max_gap_seconds": integrity["max_gap_seconds"],
            "gap_bound_seconds": integrity["gap_bound_seconds"],
            "integrity_reason": integrity["integrity_reason"],
        }

        # Only run inference on stride intervals and when not already running
        if valid and self._counter % self.stride == 0:
            should_start = False
            with self._inference_lock:
                if not self._inference_running:
                    self._inference_running = True
                    should_start = True
            
            if should_start:
                # Use the latest complete window
                window = list(self._buffer)
                stamps = list(self._sample_times)
                self._window_id += 1
                window_id = self._window_id
                # Run inference in background thread
                source_stamp = float(source_captured_at) if source_captured_at is not None else stamp
                self._inference_executor.submit(
                    self._infer_window_async,
                    window,
                    stamp,
                    self._generation,
                    source_stamp,
                    window_id,
                    stamps[0] if stamps else None,
                    stamps[-1] if stamps else None,
                    {
                        "valid": valid,
                        "frames_collected": len(self._buffer),
                        "frames_required": self.window_size,
                        "span_seconds": integrity["span_seconds"],
                    },
                )

        # Return frame immediately - don't wait for inference
        return frame.copy()
