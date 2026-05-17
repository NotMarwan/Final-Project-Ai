from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

import cv2
import numpy as np
import torch


def _as_bool(raw: Any, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _as_float(raw: Any, default: float, low: float = 0.0, high: float = 1.0) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _as_int(raw: Any, default: int, low: int = 1, high: int = 300) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


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
    enabled: bool = True
    backend: str = "yolo"
    weight_path: str = "./weapon_yolo.pt"
    interval: int = 8
    min_confidence: float = 0.20
    ema_alpha: float = 0.45
    input_size: int = 640
    labels: tuple[str, ...] = ("pistol", "rifle", "knife")
    preload_on_startup: bool = False
    min_interval_ms: int = 2500
    realtime_threshold_ms: int = 500
    independent_alert_threshold: float = 0.65

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None, env: Mapping[str, str] | None = None) -> "WeaponConfig":
        weapon_settings = settings.get("weapon", {}) if settings else {}
        env = env or {}
        
        default_labels = ("pistol", "rifle", "knife")
        labels_from_settings = _parse_labels(weapon_settings.get("labels"), default_labels)
        labels = _parse_labels(env.get("WEAPON_LABELS"), labels_from_settings)

        return cls(
            enabled=_as_bool(env.get("WEAPON_DETECTION_ENABLED"), _as_bool(weapon_settings.get("enabled"), True)),
            backend=str(env.get("WEAPON_BACKEND", weapon_settings.get("backend", "yolo"))).strip().lower(),
            weight_path=_parse_str(env.get("WEAPON_WEIGHT_PATH"), weapon_settings.get("weight_path", "./weapon_yolo.pt")),
            interval=_as_int(env.get("WEAPON_INFER_INTERVAL", weapon_settings.get("interval", 8)), 8, 1, 300),
            min_confidence=_as_float(env.get("WEAPON_MIN_CONFIDENCE", weapon_settings.get("min_confidence", 0.20)), 0.20, 0.01, 0.99),
            ema_alpha=_as_float(env.get("WEAPON_SCORE_EMA_ALPHA", weapon_settings.get("ema_alpha", 0.45)), 0.45, 0.05, 0.95),
            input_size=_as_int(env.get("WEAPON_INPUT_SIZE", weapon_settings.get("input_size", 640)), 640, 224, 1920),
            labels=labels,
            preload_on_startup=_as_bool(env.get("WEAPON_PRELOAD_ON_STARTUP"), _as_bool(weapon_settings.get("preload_on_startup"), False)),
            min_interval_ms=_as_int(env.get("WEAPON_MIN_INTERVAL_MS", weapon_settings.get("min_interval_ms", 2500)), 2500, 0, 10000),
            realtime_threshold_ms=_as_int(env.get("WEAPON_REALTIME_THRESHOLD_MS", weapon_settings.get("realtime_threshold_ms", 500)), 500, 10, 5000),
            independent_alert_threshold=_as_float(env.get("WEAPON_INDEPENDENT_ALERT_THRESHOLD", weapon_settings.get("independent_alert_threshold", 0.65)), 0.65, 0.01, 0.99),
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
        except Exception:
            return []

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
        self.session = None
        self.input_name = None
        try:
            import onnxruntime as ort
            from device_utils import get_onnx_providers
            self.session = ort.InferenceSession(model_path, providers=get_onnx_providers())
            self.input_name = self.session.get_inputs()[0].name
        except Exception as exc:
            raise RuntimeError(f"Failed to load ONNX model from {model_path}: {exc}") from exc

    @property
    def categories(self) -> tuple[str, ...]:
        return self.labels

    def predict(self, frame: np.ndarray) -> list[tuple[float, str]]:
        """Run ONNX inference on a single frame. Handles YOLOv8 output format."""
        try:
            import numpy as np
            img = cv2.resize(frame, (640, 640))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = img.astype(np.float32) / 255.0
            img = img.transpose(2, 0, 1)  # HWC to CHW
            img = np.expand_dims(img, 0)  # Add batch dim

            outputs = self.session.run(None, {self.input_name: img})
            output = outputs[0]  # YOLOv8: [1, 4+nc, num_detections] = [1, 10, 8400]

            # Transpose to [num_detections, 4+nc] = [8400, 10]
            if output.ndim == 3:
                output = output[0].T  # [10, 8400] -> [8400, 10]

            num_classes = len(self.labels)
            hits = []

            for det in output:
                # First 4 values are bbox (x1, y1, x2, y2) in normalized coords
                bbox = [float(det[0]), float(det[1]), float(det[2]), float(det[3])]
                # Next num_classes values are class scores
                class_scores = det[4:4 + num_classes]
                max_score = float(np.max(class_scores))
                cls_id = int(np.argmax(class_scores))

                if max_score < self.min_confidence:
                    continue

                label = self.labels[cls_id] if cls_id < len(self.labels) else f"class_{cls_id}"
                if self._is_weapon_label(label):
                    hits.append((max_score, label, bbox))
            return hits
        except Exception:
            return []

    def _is_weapon_label(self, label: str) -> bool:
        normalized = str(label).strip().lower()
        return any(token in normalized for token in self.labels)


# ──────────────────────────────────────────────────────────────────────────────
# Weapon Signal Engine
# ──────────────────────────────────────────────────────────────────────────────

class WeaponSignalEngine:
    def __init__(self, config: WeaponConfig, device: torch.device | None = None):
        self.config = config
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.enabled = bool(config.enabled)
        self._status_reason = ""
        self._load_attempted = False
        self._loading = False
        self._failed = False
        self._frame_counter = 0
        self._inference_running = False
        self._lock = threading.Lock()
        self._backend: _YOLOBackend | _TorchvisionBackend | _ONNXBackend | None = None
        self._last_score = 0.0
        self._last_labels: list[str] = []
        self._last_bbox: list[float] | None = None
        self._last_latency_ms = 0.0
        self._last_inference_latency_ms = 0.0
        self._last_load_latency_ms = 0.0
        self._last_inference_at = 0.0
        self._skipped_frames = 0

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
    ) -> "WeaponSignalEngine":
        return cls(WeaponConfig.from_settings(settings, env), device=device)

    def reset(self) -> None:
        with self._lock:
            self._frame_counter = 0
            self._inference_running = False
            self._last_score = 0.0
            self._last_labels = []
            self._last_bbox = None

    def latest_signal(self) -> dict[str, Any]:
        with self._lock:
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
            }
        )
        return signal

    def process_frame(self, frame: np.ndarray) -> dict[str, Any]:
        if not self.enabled:
            return self.latest_signal()

        self._frame_counter += 1
        if self._frame_counter % self.config.interval != 0:
            return self.latest_signal()

        now = time.time()
        should_skip = False
        should_start = False

        with self._lock:
            if self._inference_running:
                self._skipped_frames += 1
                should_skip = True
            else:
                elapsed_ms = (now - self._last_inference_at) * 1000
                if self._last_inference_at > 0 and elapsed_ms < self.config.min_interval_ms:
                    self._skipped_frames += 1
                    should_skip = True
                else:
                    self._inference_running = True
                    self._last_inference_at = now
                    should_start = True

        if should_skip:
            return self.latest_signal()

        if should_start:
            frame_copy = frame.copy()
            threading.Thread(target=self._infer_async, args=(frame_copy,), daemon=True).start()

        return self.latest_signal()

    def _infer_async(self, frame: np.ndarray) -> None:
        start_total = time.perf_counter()
        try:
            if not self._ensure_model_loaded():
                return

            start_infer = time.perf_counter()
            weapon_hits = self._backend.predict(frame)

            if weapon_hits:
                best_hit = max(weapon_hits, key=lambda row: row[0])
                best_score = best_hit[0]
                top_labels = [item[1] for item in sorted(weapon_hits, key=lambda row: row[0], reverse=True)[:3]]
                best_bbox = best_hit[2] if len(best_hit) > 2 else None
                self._update_score(best=best_score, labels=top_labels, bbox=best_bbox)
            else:
                self._update_score(best=0.0, labels=[])

            with self._lock:
                self._last_inference_latency_ms = (time.perf_counter() - start_infer) * 1000
        except Exception as exc:
            self._status_reason = f"inference-error:{type(exc).__name__}"
        finally:
            with self._lock:
                self._last_latency_ms = (time.perf_counter() - start_total) * 1000
                self._inference_running = False

    def preload(self) -> bool:
        """Preload the model into memory."""
        return self._ensure_model_loaded()

    def _update_score(self, *, best: float, labels: list[str], bbox: list[float] | None = None) -> None:
        best = max(0.0, min(1.0, float(best)))
        with self._lock:
            prev = float(self._last_score)
            if best > 0.0:
                blended = (self.config.ema_alpha * best) + ((1.0 - self.config.ema_alpha) * prev)
            else:
                blended = prev * 0.85
            self._last_score = max(0.0, min(1.0, blended))
            self._last_labels = labels
            if bbox is not None:
                self._last_bbox = list(bbox)
            elif best == 0.0:
                self._last_bbox = None

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
                self._backend = _ONNXBackend(
                    model_path=str(onnx_path),
                    min_confidence=self.config.min_confidence,
                    labels=self.config.labels,
                )
                print(f"[Weapon] ONNX detector ready ({(time.perf_counter() - start_load) * 1000:.1f}ms).")
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
