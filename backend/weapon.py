from __future__ import annotations

import logging
import math
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

import cv2
import numpy as np
import torch

from yolo_onnx import (decode_detections, model_input_size, model_names,
                       model_output_format, prepare_input, session_options)
from weapon_calibration import WeaponScoreCalibration
from weapon_taxonomy import WeaponTaxonomy

logger = logging.getLogger(__name__)

# Operational knobs come from the SC-5 threshold authority (G-05):
# config/thresholds.toml -> decision_config.DecisionConfig weapon_* fields.
# This module holds no numeric threshold defaults (see
# test_weapon_observation_contract.test_weapon_path_holds_no_threshold_literals).
_POLICY_FIELDS = {
    "interval": "weapon_infer_interval",
    "min_confidence": "weapon_min_confidence",
    "ema_alpha": "weapon_score_ema_alpha",
    "input_size": "weapon_input_size",
    "min_interval_ms": "weapon_min_interval_ms",
    "realtime_threshold_ms": "weapon_realtime_threshold_ms",
    "independent_alert_threshold": "weapon_independent_alert_threshold",
    "score_decay_half_life_ms": "weapon_score_decay_half_life_ms",
    "signal_ttl_ms": "weapon_signal_ttl_ms",
}


class WeaponPolicyUnavailable(RuntimeError):
    """The SC-5 decision policy cannot supply the weapon operating knobs."""


def load_decision_policy() -> Any:
    """The single threshold authority (SC-5). No ad-hoc TOML reads here."""
    from decision_config import load_decision_config
    policy = load_decision_config()
    missing = [key for key in _POLICY_FIELDS.values() if not hasattr(policy, key)]
    if missing:
        raise WeaponPolicyUnavailable(
            "config/thresholds.toml is missing SC-5 weapon keys "
            f"{missing}; they land with the DecisionCalibration (WT-20) commit"
        )
    return policy


def _policy_value(name: str) -> Any:
    return getattr(load_decision_policy(), _POLICY_FIELDS[name])


def _policy_default(name: str):
    return lambda: _policy_value(name)


def _merge_hits(hits: list[tuple[float, str, list[float]]]) -> list[tuple[float, str, list[float]]]:
    """Dedupe full-frame and person-crop passes: when two detections of the
    same canonical label overlap in source pixels, keep the higher score."""
    ordered = sorted(hits, key=lambda row: row[0], reverse=True)
    kept: list[tuple[float, str, list[float]]] = []
    for candidate in ordered:
        score, label, box = candidate
        duplicate = False
        for _, kept_label, kept_box in kept:
            if kept_label != label:
                continue
            left = max(box[0], kept_box[0])
            top = max(box[1], kept_box[1])
            right = min(box[2], kept_box[2])
            bottom = min(box[3], kept_box[3])
            if right > left and bottom > top:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


def load_weapon_taxonomy_table() -> Mapping[str, Any]:
    """SC-5 weapon taxonomy table via its single validated reader."""
    from decision_config import load_weapon_taxonomy
    return load_weapon_taxonomy()


def _load_taxonomy() -> WeaponTaxonomy:
    """Taxonomy mapping layer built from the SC-5 table (single reader)."""
    return WeaponTaxonomy.from_mapping(load_weapon_taxonomy_table())


def _as_bool(raw: Any, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _as_float(raw: Any, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _as_int(raw: Any, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _parse_labels(raw: Any, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(raw, str):
        labels = [part.strip().lower() for part in raw.split(",") if part.strip()]
        return tuple(labels) if labels else fallback
    if isinstance(raw, (list, tuple)):
        labels = [str(item).strip().lower() for item in raw if str(item).strip()]
        return tuple(labels) if labels else fallback
    return fallback


def _parse_str(raw: Any, default: str) -> str:
    if raw is None:
        return default
    return str(raw).strip()


@dataclass(frozen=True)
class WeaponConfig:
    # Non-threshold structural settings (G-05 covers numeric thresholds only).
    enabled: bool = True
    backend: str = "yolo"
    weight_path: str = "./weapon_yolo.pt"
    labels: tuple[str, ...] = ("pistol", "rifle", "knife")
    preload_on_startup: bool = False
    # F-40 calibration artifact (bound to the ONNX sha256); empty = absent.
    calibration_path: str = ""
    # Person-crop small-object pass (WT-07 rec #5). Disabled unless a crop
    # padding fraction is configured; padding has no code default (G-05).
    person_crop_enabled: bool = False
    person_crop_padding: float | None = None
    person_crop_max_regions: int | None = None
    # Env/settings overrides actually applied, surfaced in status (SC-5
    # requires explicit + logged + surfaced, never silent).
    threshold_overrides: tuple[str, ...] = ()

    # Operating knobs: the SC-5 threshold authority supplies every default.
    interval: int = field(default_factory=_policy_default("interval"))
    min_confidence: float = field(default_factory=_policy_default("min_confidence"))
    ema_alpha: float = field(default_factory=_policy_default("ema_alpha"))
    input_size: int = field(default_factory=_policy_default("input_size"))
    min_interval_ms: int = field(default_factory=_policy_default("min_interval_ms"))
    realtime_threshold_ms: int = field(default_factory=_policy_default("realtime_threshold_ms"))
    independent_alert_threshold: float = field(default_factory=_policy_default("independent_alert_threshold"))
    # Operational expiry controls, not calibrated accuracy/confidence settings.
    score_decay_half_life_ms: int = field(default_factory=_policy_default("score_decay_half_life_ms"))
    signal_ttl_ms: int = field(default_factory=_policy_default("signal_ttl_ms"))

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None,
                      env: Mapping[str, str] | None = None,
                      policy: Any = None) -> "WeaponConfig":
        """env > settings > SC-5 policy. Env wins are tracked and surfaced."""
        weapon_settings = settings.get("weapon", {}) if settings else {}
        env = env or {}
        overrides: list[str] = []
        policy = policy if policy is not None else load_decision_policy()
        missing = [key for key in _POLICY_FIELDS.values() if not hasattr(policy, key)]
        if missing:
            raise WeaponPolicyUnavailable(
                f"decision policy is missing SC-5 weapon keys: {missing}"
            )

        def knob(field_name: str, env_key: str, cast):
            policy_value = getattr(policy, _POLICY_FIELDS[field_name])
            if env.get(env_key) is not None:
                overrides.append(env_key)
                return cast(env[env_key], policy_value)
            if weapon_settings.get(field_name) is not None:
                return cast(weapon_settings[field_name], policy_value)
            return policy_value

        default_labels = WeaponTaxonomy.from_mapping(load_weapon_taxonomy_table()).label_filter()
        labels_from_settings = _parse_labels(weapon_settings.get("labels"), default_labels)
        if env.get("WEAPON_LABELS") is not None:
            overrides.append("WEAPON_LABELS")
        labels = _parse_labels(env.get("WEAPON_LABELS"), labels_from_settings)
        if env.get("WEAPON_DETECTION_ENABLED") is not None:
            overrides.append("WEAPON_DETECTION_ENABLED")
        if env.get("WEAPON_PRELOAD_ON_STARTUP") is not None:
            overrides.append("WEAPON_PRELOAD_ON_STARTUP")

        # Resolve knobs before construction so threshold_overrides is complete.
        resolved = {
            "interval": knob("interval", "WEAPON_INFER_INTERVAL", _as_int),
            "min_confidence": knob("min_confidence", "WEAPON_MIN_CONFIDENCE", _as_float),
            "ema_alpha": knob("ema_alpha", "WEAPON_SCORE_EMA_ALPHA", _as_float),
            "input_size": knob("input_size", "WEAPON_INPUT_SIZE", _as_int),
            "min_interval_ms": knob("min_interval_ms", "WEAPON_MIN_INTERVAL_MS", _as_int),
            "realtime_threshold_ms": knob("realtime_threshold_ms",
                                          "WEAPON_REALTIME_THRESHOLD_MS", _as_int),
            "independent_alert_threshold": knob("independent_alert_threshold",
                                                "WEAPON_INDEPENDENT_ALERT_THRESHOLD", _as_float),
            "score_decay_half_life_ms": knob("score_decay_half_life_ms",
                                             "WEAPON_SCORE_DECAY_HALF_LIFE_MS", _as_int),
            "signal_ttl_ms": knob("signal_ttl_ms", "WEAPON_SIGNAL_TTL_MS", _as_int),
        }

        return cls(
            enabled=_as_bool(env.get("WEAPON_DETECTION_ENABLED"),
                            _as_bool(weapon_settings.get("enabled"), True)),
            backend=str(env.get("WEAPON_BACKEND", weapon_settings.get("backend", "yolo"))).strip().lower(),
            weight_path=_parse_str(env.get("WEAPON_WEIGHT_PATH"),
                                   weapon_settings.get("weight_path", "./weapon_yolo.pt")),
            labels=labels,
            preload_on_startup=_as_bool(env.get("WEAPON_PRELOAD_ON_STARTUP"),
                                        _as_bool(weapon_settings.get("preload_on_startup"), False)),
            calibration_path=_parse_str(env.get("WEAPON_CALIBRATION_ARTIFACT"),
                                        weapon_settings.get("calibration_path", "")),
            person_crop_enabled=_as_bool(env.get("WEAPON_PERSON_CROP_ENABLED"),
                                         _as_bool(weapon_settings.get("person_crop_enabled"), False)),
            person_crop_padding=(None if _parse_str(env.get("WEAPON_PERSON_CROP_PADDING"),
                                                    str(weapon_settings.get("person_crop_padding", ""))) == ""
                                 else _as_float(env.get("WEAPON_PERSON_CROP_PADDING"),
                                                weapon_settings.get("person_crop_padding"))),
            person_crop_max_regions=(None if _parse_str(env.get("WEAPON_PERSON_CROP_MAX_REGIONS"),
                                                        str(weapon_settings.get("person_crop_max_regions", ""))) == ""
                                     else _as_int(env.get("WEAPON_PERSON_CROP_MAX_REGIONS"),
                                                  weapon_settings.get("person_crop_max_regions"))),
            threshold_overrides=tuple(overrides),
            **resolved,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Backend: YOLO (Ultralytics)
# ──────────────────────────────────────────────────────────────────────────────

class _YOLOBackend:
    """Wrapper around Ultralytics YOLO for thread-safe inference."""

    def __init__(self, weight_path: str, device: torch.device, min_confidence: float, labels: tuple[str, ...]):
        self.device = device
        self.min_confidence = min_confidence
        self.labels = labels
        self._model = None
        self._categories: dict[int, str] = {}

        try:
            from ultralytics import YOLO
            self._model = YOLO(weight_path)
            # YOLO automatically handles device placement during predict()
            self._categories = {int(k): str(v).lower() for k, v in self._model.names.items()}
        except Exception as exc:
            raise RuntimeError(f"Failed to load YOLO model from {weight_path}: {exc}") from exc

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(self._categories.values())

    def predict(self, frame: np.ndarray) -> list[tuple[float, str, list[float]]]:
        """Run inference on a single frame. Returns list of (confidence, label, bbox)."""
        try:
            results = self._model.predict(
                frame,
                verbose=False,
                conf=self.min_confidence,
                device=str(self.device),
            )
            result = results[0]
            hits: list[tuple[float, str, list[float]]] = []

            if result.boxes is None:
                return hits

            h, w = frame.shape[:2]
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                label = self._categories.get(cls_id, f"class_{cls_id}")
                # Extract bbox in [x1, y1, x2, y2] normalized to 0-1
                xyxy = box.xyxy[0].cpu().tolist()
                bbox = [xyxy[0] / w, xyxy[1] / h, xyxy[2] / w, xyxy[3] / h]
                if self._is_weapon_label(label):
                    hits.append((conf, label, bbox))

            return hits
        except Exception as exc:
            # An unavailable backend is not evidence that a frame is weapon-free.
            raise RuntimeError("Ultralytics weapon inference failed") from exc

    def _is_weapon_label(self, label: str) -> bool:
        normalized = str(label).strip().lower()
        if not normalized:
            return False
        return any(token in normalized for token in self.labels)


# ──────────────────────────────────────────────────────────────────────────────
# Backend: torchvision COCO (legacy)
# ──────────────────────────────────────────────────────────────────────────────

class _TorchvisionBackend:
    """Legacy Faster R-CNN COCO backend."""

    def __init__(self, device: torch.device, min_confidence: float, labels: tuple[str, ...]):
        self.device = device
        self.min_confidence = min_confidence
        self.labels = labels
        self._model = None
        self._categories: tuple[str, ...] = ()

        try:
            from torchvision.models.detection import (
                FasterRCNN_ResNet50_FPN_V2_Weights,
                fasterrcnn_resnet50_fpn_v2,
            )
            weights = FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT
            self._categories = tuple(str(cat).lower() for cat in weights.meta.get("categories", []))
            self._model = fasterrcnn_resnet50_fpn_v2(weights=weights, box_score_thresh=min_confidence)
            self._model.to(device)
            self._model.eval()
        except Exception as exc:
            raise RuntimeError(f"Failed to load torchvision model: {exc}") from exc

    @property
    def categories(self) -> tuple[str, ...]:
        return self._categories

    def predict(self, frame: np.ndarray) -> list[tuple[float, str, list[float]]]:
        """Run inference on a single BGR frame. Returns list of (confidence, label, bbox)."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        max_side = max(h, w)
        scale = 1.0
        if max_side > 640:
            scale = 640 / float(max_side)
            rgb = cv2.resize(rgb, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)

        tensor = torch.from_numpy(rgb).permute(2, 0, 1).float().div(255.0).to(self.device)

        with torch.inference_mode():
            output = self._model([tensor])[0]

        scores = output.get("scores")
        labels = output.get("labels")
        boxes = output.get("boxes")
        if scores is None or labels is None:
            return []

        hits: list[tuple[float, str, list[float]]] = []
        scores_list = scores.detach().cpu().tolist()
        labels_list = labels.detach().cpu().tolist()

        for i, (score, label_idx) in enumerate(zip(scores_list, labels_list)):
            if float(score) < self.min_confidence:
                continue
            label = self._label_for_index(int(label_idx))
            if self._is_weapon_label(label):
                if boxes is not None:
                    box = boxes[i].detach().cpu().tolist()
                    bbox = [
                        max(0, min(1, (box[0] / scale) / w)),
                        max(0, min(1, (box[1] / scale) / h)),
                        max(0, min(1, (box[2] / scale) / w)),
                        max(0, min(1, (box[3] / scale) / h)),
                    ]
                else:
                    bbox = [0.0, 0.0, 1.0, 1.0]
                hits.append((float(score), label, bbox))

        return hits

    def _label_for_index(self, index: int) -> str:
        if 0 <= index < len(self._categories):
            return str(self._categories[index]).strip().lower()
        return f"class_{index}"

    def _is_weapon_label(self, label: str) -> bool:
        normalized = str(label).strip().lower()
        if not normalized:
            return False
        return any(token in normalized for token in self.labels)


# ──────────────────────────────────────────────────────────────────────────────
# Backend: ONNX Runtime (fast inference)
# ──────────────────────────────────────────────────────────────────────────────

class _ONNXBackend:
    """ONNX Runtime backend for faster inference."""

    def __init__(self, model_path: str, min_confidence: float, labels: tuple[str, ...]):
        self.min_confidence = min_confidence
        self.labels = labels
        try:
            import hashlib
            import onnxruntime as ort
            from device_utils import get_onnx_providers
            self.model_path = model_path
            self.session = ort.InferenceSession(model_path, sess_options=session_options(ort),
                                                providers=get_onnx_providers())
            # F-40: calibration artifacts bind to this hash; evidence and FP
            # logs record it so every score is attributable to a model build.
            with open(model_path, "rb") as stream:
                self.model_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
            self.execution_provider = str(self.session.get_providers()[0])
            input_info = self.session.get_inputs()[0]
            self.input_name = input_info.name
            self.input_size = model_input_size(input_info.shape)
            metadata = self.session.get_modelmeta().custom_metadata_map
            self._categories = model_names(metadata)
            self.output_format = model_output_format(metadata)
            self._selected_classes = {index for index, name in self._categories.items()
                                      if self._is_weapon_label(name)}
        except Exception as exc:
            raise RuntimeError("Failed to initialize ONNX weapon model") from exc

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(self._categories.values())

    def predict(self, frame: np.ndarray) -> list[tuple[float, str, list[float]]]:
        """Decode export class IDs and return normalized source-frame xyxy."""
        img, transform = prepare_input(frame, self.input_size)
        output = self.session.run(None, {self.input_name: img})[0]
        rows = decode_detections(
            output, num_classes=len(self._categories), transform=transform,
            confidence=self.min_confidence, classes=self._selected_classes,
            output_format=self.output_format,
        )
        h, w = frame.shape[:2]
        return [(float(conf), self._categories[int(class_id)],
                 [float(x1 / w), float(y1 / h), float(x2 / w), float(y2 / h)])
                for x1, y1, x2, y2, conf, class_id in rows]

    def predict_regions(self, frame: np.ndarray, boxes_xyxy: list[list[float]],
                        padding: float, max_regions: int | None = None) -> list[tuple[float, str, list[float]]]:
        """SAHI-style pass restricted to person-crop regions (WT-07 rec #5).

        Each region is cropped with `padding` relative margin and letterboxed
        to the model input, so a small held weapon gains pixels. One forward
        per region; coordinates map back to source pixels (SC-2: source-pixel
        coordinates are authoritative). Returns normalized frame xyxy hits.
        """
        if not 0 <= padding < 1:
            raise ValueError("region padding must be a fraction in [0,1)")
        regions = list(boxes_xyxy)[:max_regions]
        h, w = frame.shape[:2]
        hits: list[tuple[float, str, list[float]]] = []
        for box in regions:
            x1, y1, x2, y2 = (float(value) for value in box)
            pad_x, pad_y = (x2 - x1) * padding, (y2 - y1) * padding
            left, top = max(0, int(x1 - pad_x)), max(0, int(y1 - pad_y))
            right, bottom = min(w, int(x2 + pad_x)), min(h, int(y2 + pad_y))
            if right - left <= 0 or bottom - top <= 0:
                continue
            crop = frame[top:bottom, left:right]
            img, transform = prepare_input(crop, self.input_size)
            output = self.session.run(None, {self.input_name: img})[0]
            rows = decode_detections(
                output, num_classes=len(self._categories), transform=transform,
                confidence=self.min_confidence, classes=self._selected_classes,
                output_format=self.output_format,
            )
            for x1c, y1c, x2c, y2c, conf, class_id in rows:
                hits.append((float(conf), self._categories[int(class_id)],
                             [float((x1c + left) / w), float((y1c + top) / h),
                              float((x2c + left) / w), float((y2c + top) / h)]))
        return hits

    def _is_weapon_label(self, label: str) -> bool:
        normalized = str(label).strip().lower()
        return bool(normalized) and any(token in normalized for token in self.labels)


# ──────────────────────────────────────────────────────────────────────────────
# Weapon Signal Engine
# ──────────────────────────────────────────────────────────────────────────────

class WeaponSignalEngine:
    def __init__(self, config: WeaponConfig, device: torch.device | None = None,
                 taxonomy: WeaponTaxonomy | None = None,
                 calibration: WeaponScoreCalibration | None = None,
                 fp_logger: Any = None):
        self.config = config
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.enabled = bool(config.enabled)
        self.taxonomy = taxonomy if taxonomy is not None else _load_taxonomy()
        self._calibration = calibration
        self._fp_logger = fp_logger
        self._status_reason = ""
        self._load_attempted = False
        self._loading = False
        self._failed = False
        self._frame_counter = 0
        self._inference_running = False
        self._lock = threading.Lock()
        self._backend: _YOLOBackend | _TorchvisionBackend | _ONNXBackend | None = None
        self._last_score = 0.0
        self._observation_score = 0.0
        self._last_labels: list[str] = []
        self._last_bbox: list[float] | None = None
        self._last_group: str | None = None
        self._last_subtype: str | None = None
        self._last_latency_ms = 0.0
        self._last_inference_latency_ms = 0.0
        self._last_load_latency_ms = 0.0
        self._last_inference_at = 0.0
        self._skipped_frames = 0
        self._last_start_monotonic: float | None = None
        self._score_updated_at: float | None = None
        self._observed_at: float | None = None
        self._completed_at: float | None = None
        self._observation_sequence = 0
        self._observation_id = 0
        self._generation = 0
        self._closed = False
        self._jobs: queue.Queue = queue.Queue(maxsize=1)
        self._worker: threading.Thread | None = None

        if not self.enabled:
            self._status_reason = "disabled-by-config"
        elif self.config.preload_on_startup:
            threading.Thread(target=self.preload, daemon=True).start()

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None,
        env: Mapping[str, str] | None = None,
        device: torch.device | None = None,
        policy: Any = None,
        taxonomy: WeaponTaxonomy | None = None,
        fp_logger: Any = None,
    ) -> "WeaponSignalEngine":
        config = WeaponConfig.from_settings(settings, env, policy=policy)
        calibration = None
        if config.calibration_path:
            calibration = WeaponScoreCalibration.from_path(config.calibration_path)
        return cls(config, device=device, taxonomy=taxonomy,
                   calibration=calibration, fp_logger=fp_logger)

    def reset(self) -> None:
        with self._lock:
            self._generation += 1
            self._frame_counter = 0
            # Keep a running job marked busy until it exits; its generation is stale.
            self._last_score = 0.0
            self._observation_score = 0.0
            self._last_labels = []
            self._last_bbox = None
            self._last_group = None
            self._last_subtype = None
            self._score_updated_at = None
            self._observed_at = None
            self._completed_at = None
            self._observation_id = 0
            self._last_start_monotonic = None

    def close(self) -> None:
        """Invalidate pending work and wake the bounded daemon worker for shutdown."""
        with self._lock:
            self._closed = True
            self._generation += 1
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            pass  # The worker checks _closed before consuming its queued job.

    def _decay_score_locked(self, now: float) -> None:
        if self._score_updated_at is not None:
            elapsed = max(0.0, now - self._score_updated_at)
            self._last_score *= 2 ** -(elapsed * 1000 / self.config.score_decay_half_life_ms)
        self._score_updated_at = now
        if self._observed_at is not None and (now - self._observed_at) * 1000 >= self.config.signal_ttl_ms:
            self._last_score = 0.0
            self._last_labels = []
            self._last_bbox = None
            self._last_group = None
            self._last_subtype = None

    def latest_signal(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            self._decay_score_locked(now)
            is_realtime = (
                self._backend is not None
                and self._last_inference_latency_ms > 0
                and self._last_inference_latency_ms < self.config.realtime_threshold_ms
            )

            return {
                "enabled": self.enabled,
                "backend": self.config.backend,
                "ready": self._backend is not None,
                "loading": self._loading,
                "failed": self._failed,
                "isRealtime": is_realtime,
                "score": round(float(self._last_score), 4),
                "labels": list(self._last_labels),
                "bbox": list(self._last_bbox) if self._last_bbox else None,
                "latencyMs": round(float(self._last_latency_ms), 1),
                "inferenceLatencyMs": round(float(self._last_inference_latency_ms), 1),
                "loadLatencyMs": round(float(self._last_load_latency_ms), 1),
                "skippedFrames": self._skipped_frames,
                "lastInferenceAt": self._last_inference_at,
                "minIntervalMs": self.config.min_interval_ms,
                "inferenceRunning": self._inference_running,
                "reason": self._status_reason,
                "observation_id": self._observation_id,
                "observation_score": self._observation_score,
                "observation_valid": (self._observation_id > 0 and self._observed_at is not None
                                      and (now-self._observed_at)*1000 < self.config.signal_ttl_ms),
                "observed_at": self._observed_at,
                "completed_at": self._completed_at,
                "observation_age_ms": (max(0.0, now - self._observed_at) * 1000
                                       if self._observed_at is not None else None),
                # F-09 output boundary (taxonomy + calibration, additive).
                "weaponGroup": self._last_group,
                "weaponSubtype": self._last_subtype,
                "rawModelScore": self._observation_score,
                "calibratedProbability": (None if self._calibration is None
                                          else self._calibration.apply(self._observation_score)),
                "calibrationStatus": (self._calibration.status if self._calibration is not None
                                      else "absent"),
            }

    def status(self) -> dict[str, Any]:
        signal = self.latest_signal()
        signal.update(
            {
                "device": str(self.device),
                "interval": self.config.interval,
                "minConfidence": self.config.min_confidence,
                "emaAlpha": self.config.ema_alpha,
                "trackedLabels": list(self.config.labels),
                "scoreDecayHalfLifeMs": self.config.score_decay_half_life_ms,
                "signalTtlMs": self.config.signal_ttl_ms,
                # SC-5: env/settings threshold overrides are explicit and
                # surfaced here, never silent.
                "thresholdOverrides": list(self.config.threshold_overrides),
                "executionProvider": self._execution_provider(),
                "modelSha256": getattr(self._backend, "model_sha256", None),
                "health": self._health(signal),
            }
        )
        return signal

    def _execution_provider(self) -> str:
        provider = getattr(self._backend, "execution_provider", None)
        if provider:
            return str(provider)
        return "cpu-torch" if self.device.type == "cpu" else str(self.device)

    def _health(self, signal: Mapping[str, Any]) -> str:
        """Explicit health state (SC-10 honesty): the registered CPU-EP
        weapon path is a degraded mode (WT-07 §5: ~290-310 ms measured
        CPU forward vs the realtime budget), not the accuracy reference."""
        if not self.enabled:
            return "disabled"
        if self._failed:
            return "failed"
        if signal.get("loading"):
            return "loading"
        if self._backend is None:
            return "not-ready"
        provider = self._execution_provider()
        if provider.startswith("CPU") or provider == "cpu-torch":
            return "degraded-cpu"
        return "ok"

    def process_frame(self, frame: np.ndarray, observed_at: float | None = None,
                      person_boxes: list[list[float]] | None = None) -> dict[str, Any]:
        if not self.enabled:
            return self.latest_signal()
        now = time.monotonic()
        if observed_at is None:
            observed_at = now
        if not math.isfinite(observed_at) or observed_at > now:
            raise ValueError("observed_at must be a finite monotonic capture timestamp")
        with self._lock:
            self._frame_counter += 1
            eligible = self._frame_counter % self.config.interval == 0
            interval_due = (self._last_start_monotonic is None or
                            (now - self._last_start_monotonic) * 1000 >= self.config.min_interval_ms)
            should_start = eligible and interval_due and not self._inference_running and not self._closed
            if eligible and not should_start:
                self._skipped_frames += 1
            if should_start:
                self._inference_running = True
                self._last_start_monotonic = now
                self._last_inference_at = time.time()  # Preserve existing wall-clock status field.
                generation = self._generation
                if self._worker is None:
                    self._worker = threading.Thread(target=self._worker_loop, name="weapon-inference", daemon=True)
                    self._worker.start()
        if should_start:
            try:
                self._jobs.put_nowait((frame.copy(), observed_at, generation, person_boxes))
            except Exception:
                with self._lock:
                    self._inference_running = False
                raise
        return self.latest_signal()

    def _worker_loop(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            with self._lock:
                if self._closed:
                    self._inference_running = False
                    return
            self._infer_async(*job)
            with self._lock:
                if self._closed:
                    return

    def predict_hits(self, frame: np.ndarray, person_boxes: list[list[float]] | None = None,
                     *, frame_index: int = 0, time_s: float = 0.0) -> list[dict[str, Any]]:
        """Run the weapon backend and map hits through the taxonomy boundary.

        Every returned hit carries canonical label, raw subtype and coarse
        group; severity consumers key on `group` only. When an FP logger is
        attached, every detection is logged (the run declares the source
        benign, so detections are false positives by construction).
        """
        hits = list(self._backend.predict(frame))
        padding = self.config.person_crop_padding
        if (person_boxes and self.config.person_crop_enabled and padding is not None
                and hasattr(self._backend, "predict_regions")):
            hits += self._backend.predict_regions(
                frame, person_boxes, padding,
                self.config.person_crop_max_regions,
            )
        hits = _merge_hits(hits)
        mapped: list[dict[str, Any]] = []
        for score, label, bbox in hits:
            subtype = self.taxonomy.subtype(label)
            mapped.append({
                "score": float(score),
                "label": self.taxonomy.canonical_label(label),
                "subtype": subtype,
                "group": self.taxonomy.group_for(label),
                "bbox": list(bbox),
            })
        if self._fp_logger is not None:
            for hit in mapped:
                self._fp_logger.log_detection(
                    frame_index=frame_index, time_s=time_s, frame=frame,
                    class_label=hit["subtype"], canonical_label=hit["label"],
                    group=hit["group"], score=hit["score"], bbox_norm=hit["bbox"],
                )
        return mapped

    def _infer_async(self, frame: np.ndarray, observed_at: float | None = None,
                     generation: int | None = None,
                     person_boxes: list[list[float]] | None = None) -> None:
        start_total = time.perf_counter()
        if observed_at is None:
            observed_at = time.monotonic()
        if generation is None:
            generation = self._generation
        try:
            if not self._ensure_model_loaded():
                return
            start_infer = time.perf_counter()
            weapon_hits = self.predict_hits(frame, person_boxes)
            best_hit = max(weapon_hits, key=lambda row: row["score"]) if weapon_hits else None
            labels = [item["label"] for item in
                      sorted(weapon_hits, key=lambda row: row["score"], reverse=True)[:3]]
            self._update_score(best=best_hit["score"] if best_hit else 0.0, labels=labels,
                               bbox=best_hit["bbox"] if best_hit else None,
                               observed_at=observed_at, generation=generation,
                               group=best_hit["group"] if best_hit else None,
                               subtype=best_hit["subtype"] if best_hit else None)
            with self._lock:
                if generation == self._generation and not self._closed:
                    self._last_inference_latency_ms = (time.perf_counter() - start_infer) * 1000
                    self._status_reason = "ok"
        except Exception as exc:
            with self._lock:
                if generation == self._generation:
                    self._status_reason = f"inference-error:{type(exc).__name__}"
            logger.warning("[Weapon] Inference failed (%s)", type(exc).__name__)
        finally:
            with self._lock:
                self._last_latency_ms = (time.perf_counter() - start_total) * 1000
                self._inference_running = False

    def preload(self) -> bool:
        """Preload the model into memory."""
        return self._ensure_model_loaded()

    def _update_score(self, *, best: float, labels: list[str], bbox: list[float] | None = None,
                      observed_at: float | None = None, generation: int | None = None,
                      group: str | None = None, subtype: str | None = None) -> None:
        best = float(best)
        if not math.isfinite(best):
            raise ValueError("Weapon confidence must be finite")
        best = max(0.0, min(1.0, best))
        now = time.monotonic()
        with self._lock:
            if self._closed or (generation is not None and generation != self._generation):
                return
            self._decay_score_locked(now)
            if best > 0.0:
                self._last_score = self.config.ema_alpha * best + (1.0 - self.config.ema_alpha) * self._last_score
            # Negative observations decay only by elapsed time, never by frame/tick count.
            self._last_labels = list(labels)
            self._last_bbox = list(bbox) if bbox is not None else None
            self._last_group = group
            self._last_subtype = subtype
            self._observed_at = now if observed_at is None else observed_at
            self._decay_score_locked(now)  # An already-expired queued observation is not current.
            if generation is not None:
                self._observation_score = best
                self._observation_sequence += 1
                self._observation_id = self._observation_sequence
                self._completed_at = now

    def _ensure_model_loaded(self) -> bool:
        if self._backend is not None:
            return True
        if self._load_attempted:
            return False

        with self._lock:
            if self._loading:
                return False
            self._loading = True

        self._load_attempted = True
        start_load = time.perf_counter()

        try:
            # Try ONNX first (faster)
            from pathlib import Path
            onnx_path = Path(__file__).parent / "models" / "weapon_yolo.onnx"
            if onnx_path.exists() and self.config.backend == "yolo":
                try:
                    self._backend = _ONNXBackend(
                        model_path=str(onnx_path),
                        min_confidence=self.config.min_confidence,
                        labels=self.config.labels,
                    )
                    logger.info("[Weapon] ONNX detector ready")
                except Exception as exc:
                    logger.warning("[Weapon] ONNX initialization failed (%s); trying YOLO", type(exc).__name__)
                    self._backend = _YOLOBackend(
                        weight_path=self.config.weight_path, device=self.device,
                        min_confidence=self.config.min_confidence, labels=self.config.labels,
                    )
            elif self.config.backend == "yolo":
                self._backend = _YOLOBackend(
                    weight_path=self.config.weight_path,
                    device=self.device,
                    min_confidence=self.config.min_confidence,
                    labels=self.config.labels,
                )
                print(f"[Weapon] YOLO detector ready on {self.device.type.upper()} ({(time.perf_counter() - start_load) * 1000:.1f}ms).")
            elif self.config.backend == "torchvision_coco":
                self._backend = _TorchvisionBackend(
                    device=self.device,
                    min_confidence=self.config.min_confidence,
                    labels=self.config.labels,
                )
                print(f"[Weapon] torchvision detector ready on {self.device.type.upper()} ({(time.perf_counter() - start_load) * 1000:.1f}ms).")
            else:
                raise ValueError(f"Unsupported backend: {self.config.backend}")

            with self._lock:
                self._last_load_latency_ms = (time.perf_counter() - start_load) * 1000
                self._loading = False
                self._status_reason = "ok"
            return True

        except Exception as exc:
            with self._lock:
                self.enabled = False
                self._failed = True
                self._loading = False
                self._status_reason = f"model-load-failed:{type(exc).__name__}"
            print(f"[Weapon] Detector disabled: {exc}")
            return False


def observation_payload(signal: Mapping[str, Any]) -> dict[str, Any]:
    """SC-2 observation identity contract at the F-09 boundary.

    `weapon_score`/`weapon_labels` are null WITHOUT a producer observation
    id; consumers must handle the null state explicitly. A completed
    observation yields values even when it is a genuine negative (score 0.0,
    empty labels) — an absent producer is not a negative observation.
    """
    has_producer = bool(signal.get("observation_id"))
    return {
        "observation_id": signal.get("observation_id", 0),
        "observation_age_ms": signal.get("observation_age_ms"),
        "observation_valid": bool(signal.get("observation_valid")),
        "weapon_score": signal.get("observation_score") if has_producer else None,
        "weapon_labels": list(signal.get("labels") or []) if has_producer else None,
        "weapon_group": signal.get("weaponGroup") if has_producer else None,
        "weapon_subtype": signal.get("weaponSubtype") if has_producer else None,
    }
