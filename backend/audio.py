from __future__ import annotations

import base64
import io
import wave
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AudioConfig:
    enabled: bool = False
    scream_threshold: float = 0.55
    loudness_threshold: float = 0.40

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None) -> "AudioConfig":
        audio_settings: Mapping[str, Any] = {}
        if settings and isinstance(settings.get("audio"), Mapping):
            audio_settings = settings["audio"]  # type: ignore[index]

        return cls(
            enabled=_coerce_bool(audio_settings.get("enabled"), False),
            scream_threshold=_coerce_float(audio_settings.get("scream_threshold"), 0.55),
            loudness_threshold=_coerce_float(audio_settings.get("loudness_threshold"), 0.40),
        )


class AudioRiskAnalyzer:
    def __init__(self, config: AudioConfig):
        self.config = config

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None) -> "AudioRiskAnalyzer":
        return cls(AudioConfig.from_settings(settings))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "supported": True,
            "screamThreshold": self.config.scream_threshold,
            "loudnessThreshold": self.config.loudness_threshold,
        }

    def analyze_base64_wav(self, audio_base64: str) -> dict[str, Any]:
        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as exc:
            return {
                "enabled": self.config.enabled,
                "detected": False,
                "score": 0.0,
                "error": f"Invalid base64 payload: {exc}",
            }

        return self.analyze_wav_bytes(audio_bytes)

    def analyze_wav_bytes(self, audio_bytes: bytes) -> dict[str, Any]:
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                frame_rate = wav.getframerate()
                frame_count = wav.getnframes()
                frames = wav.readframes(frame_count)
        except Exception as exc:
            return {
                "enabled": self.config.enabled,
                "detected": False,
                "score": 0.0,
                "error": f"Unsupported audio payload: {exc}",
            }

        if sample_width == 1:
            samples = np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0
            peak_divisor = 128.0
        elif sample_width == 2:
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            peak_divisor = float(np.iinfo(np.int16).max)
        elif sample_width == 4:
            samples = np.frombuffer(frames, dtype=np.int32).astype(np.float32)
            peak_divisor = float(np.iinfo(np.int32).max)
        else:
            return {
                "enabled": self.config.enabled,
                "detected": False,
                "score": 0.0,
                "error": f"Unsupported sample width: {sample_width}",
            }

        if channels > 1 and samples.size:
            samples = samples.reshape(-1, channels).mean(axis=1)

        if samples.size == 0:
            return {
                "enabled": self.config.enabled,
                "detected": False,
                "score": 0.0,
                "error": "Audio payload contains no samples",
            }

        normalized = np.clip(samples / peak_divisor, -1.0, 1.0)
        rms = float(np.sqrt(np.mean(np.square(normalized))))
        peak = float(np.max(np.abs(normalized)))
        sign_changes = np.mean(np.abs(np.diff(np.sign(normalized))) > 0) if normalized.size > 1 else 0.0
        duration = frame_count / float(frame_rate or 1)

        scream_score = min(1.0, (rms * 0.45) + (peak * 0.35) + (sign_changes * 0.20))
        if scream_score >= self.config.scream_threshold:
            severity = "critical"
            detected = True
            reason = "Audio intensity and transients indicate a scream or sharp distress."
        elif scream_score >= self.config.loudness_threshold:
            severity = "high"
            detected = True
            reason = "Audio is loud and unstable enough to validate a security concern."
        else:
            severity = "medium"
            detected = False
            reason = "Audio remains below the validation threshold."

        return {
            "enabled": self.config.enabled,
            "detected": detected,
            "score": round(scream_score * 100, 1),
            "severity": severity,
            "sampleRate": frame_rate,
            "channels": channels,
            "durationSeconds": round(duration, 2),
            "rms": round(rms * 100, 1),
            "peak": round(peak * 100, 1),
            "zeroCrossing": round(sign_changes * 100, 1),
            "reason": reason,
        }
