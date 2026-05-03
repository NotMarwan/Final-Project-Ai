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


@dataclass(frozen=True)
class WeaponConfig:
    enabled: bool = True
    backend: str = "torchvision_coco"
    interval: int = 8
    min_confidence: float = 0.20
    ema_alpha: float = 0.45
    input_size: int = 640
    labels: tuple[str, ...] = ("firearm", "handgun", "rifle", "knife")
    preload_on_startup: bool = False
    min_interval_ms: int = 2500
    realtime_threshold_ms: int = 500

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None, env: Mapping[str, str] | None = None) -> "WeaponConfig":
        weapon_settings = settings.get("weapon", {}) if settings else {}
        env = env or {}
        
        default_labels = ("firearm", "handgun", "rifle", "knife")
        labels_from_settings = _parse_labels(weapon_settings.get("labels"), default_labels)
        labels = _parse_labels(env.get("WEAPON_LABELS"), labels_from_settings)

        return cls(
            enabled=_as_bool(env.get("WEAPON_DETECTION_ENABLED"), _as_bool(weapon_settings.get("enabled"), True)),
            backend=str(env.get("WEAPON_BACKEND", weapon_settings.get("backend", "torchvision_coco"))).strip().lower(),
            interval=_as_int(env.get("WEAPON_INFER_INTERVAL", weapon_settings.get("interval", 8)), 8, 1, 300),
            min_confidence=_as_float(env.get("WEAPON_MIN_CONFIDENCE", weapon_settings.get("min_confidence", 0.20)), 0.20, 0.01, 0.99),
            ema_alpha=_as_float(env.get("WEAPON_SCORE_EMA_ALPHA", weapon_settings.get("ema_alpha", 0.45)), 0.45, 0.05, 0.95),
            input_size=_as_int(env.get("WEAPON_INPUT_SIZE", weapon_settings.get("input_size", 640)), 640, 224, 1920),
            labels=labels,
            preload_on_startup=_as_bool(env.get("WEAPON_PRELOAD_ON_STARTUP"), _as_bool(weapon_settings.get("preload_on_startup"), False)),
            min_interval_ms=_as_int(env.get("WEAPON_MIN_INTERVAL_MS", weapon_settings.get("min_interval_ms", 2500)), 2500, 0, 10000),
            realtime_threshold_ms=_as_int(env.get("WEAPON_REALTIME_THRESHOLD_MS", weapon_settings.get("realtime_threshold_ms", 500)), 500, 10, 5000),
        )


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
        self._model = None
        self._categories: tuple[str, ...] = ()
        self._last_score = 0.0
        self._last_labels: list[str] = []
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

    def latest_signal(self) -> dict[str, Any]:
        with self._lock:
            # We consider it real-time if warm inference latency is below threshold
            # and it's actually running on a device (model loaded)
            is_realtime = (
                self._model is not None 
                and self._last_inference_latency_ms > 0 
                and self._last_inference_latency_ms < self.config.realtime_threshold_ms
            )
            
            return {
                "enabled": self.enabled,
                "backend": self.config.backend,
                "ready": self._model is not None,
                "loading": self._loading,
                "failed": self._failed,
                "isRealtime": is_realtime,
                "score": round(float(self._last_score), 4),
                "labels": list(self._last_labels),
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
        with self._lock:
            # 1. Single-flight check
            if self._inference_running:
                self._skipped_frames += 1
                return self.latest_signal()
            
            # 2. Cooldown check (min_interval_ms)
            elapsed_ms = (now - self._last_inference_at) * 1000
            if self._last_inference_at > 0 and elapsed_ms < self.config.min_interval_ms:
                self._skipped_frames += 1
                return self.latest_signal()

            self._inference_running = True
            self._last_inference_at = now

        frame_copy = frame.copy()
        threading.Thread(target=self._infer_async, args=(frame_copy,), daemon=True).start()
        return self.latest_signal()

    def _infer_async(self, frame: np.ndarray) -> None:
        start_total = time.perf_counter()
        try:
            if not self._ensure_model_loaded():
                return
            
            start_infer = time.perf_counter()
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            max_side = max(h, w)
            if max_side > self.config.input_size:
                scale = self.config.input_size / float(max_side)
                rgb = cv2.resize(rgb, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)

            tensor = torch.from_numpy(rgb).permute(2, 0, 1).float().div(255.0).to(self.device)

            with torch.inference_mode():
                output = self._model([tensor])[0]

            scores = output.get("scores")
            labels = output.get("labels")
            if scores is None or labels is None:
                self._update_score(best=0.0, labels=[])
                return

            scores_list = scores.detach().cpu().tolist()
            labels_list = labels.detach().cpu().tolist()
            weapon_hits: list[tuple[float, str]] = []

            for score, label_idx in zip(scores_list, labels_list):
                if float(score) < self.config.min_confidence:
                    continue
                label = self._label_for_index(int(label_idx))
                if self._is_weapon_label(label):
                    weapon_hits.append((float(score), label))

            if weapon_hits:
                best_score = max(item[0] for item in weapon_hits)
                top_labels = [item[1] for item in sorted(weapon_hits, key=lambda row: row[0], reverse=True)[:3]]
                self._update_score(best=best_score, labels=top_labels)
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

    def _update_score(self, *, best: float, labels: list[str]) -> None:
        best = max(0.0, min(1.0, float(best)))
        with self._lock:
            prev = float(self._last_score)
            if best > 0.0:
                blended = (self.config.ema_alpha * best) + ((1.0 - self.config.ema_alpha) * prev)
            else:
                blended = prev * 0.85
            self._last_score = max(0.0, min(1.0, blended))
            self._last_labels = labels

    def _label_for_index(self, index: int) -> str:
        if 0 <= index < len(self._categories):
            return str(self._categories[index]).strip().lower()
        return f"class_{index}"

    def _is_weapon_label(self, label: str) -> bool:
        normalized = str(label).strip().lower()
        if not normalized:
            return False
        return any(token in normalized for token in self.config.labels)

    def _ensure_model_loaded(self) -> bool:
        if self._model is not None:
            return True
        if self._load_attempted:
            return False
        
        with self._lock:
            if self._loading:
                return False
            self._loading = True
            
        self._load_attempted = True
        start_load = time.perf_counter()

        if self.config.backend != "torchvision_coco":
            with self._lock:
                self.enabled = False
                self._failed = True
                self._loading = False
                self._status_reason = f"unsupported-backend:{self.config.backend}"
            return False

        try:
            from torchvision.models.detection import (
                FasterRCNN_ResNet50_FPN_V2_Weights,
                fasterrcnn_resnet50_fpn_v2,
            )

            weights = FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT
            self._categories = tuple(str(cat).lower() for cat in weights.meta.get("categories", []))
            model = fasterrcnn_resnet50_fpn_v2(weights=weights, box_score_thresh=self.config.min_confidence)
            model.to(self.device)
            model.eval()
            
            with self._lock:
                self._model = model
                self._last_load_latency_ms = (time.perf_counter() - start_load) * 1000
                self._loading = False
                self._status_reason = "ok"
            print(f"[Weapon] torchvision detector ready on {self.device.type.upper()} ({self._last_load_latency_ms:.1f}ms).")
            return True
        except Exception as exc:
            with self._lock:
                self.enabled = False
                self._failed = True
                self._loading = False
                self._status_reason = f"model-load-failed:{type(exc).__name__}"
            print(f"[Weapon] Detector disabled: {exc}")
            return False
