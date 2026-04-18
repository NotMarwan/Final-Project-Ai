from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SEVERITY_ORDER = {"medium": 0, "high": 1, "critical": 2}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_severity(value: Any, default: str = "high") -> str:
    text = str(value or default).strip().lower()
    return text if text in SEVERITY_ORDER else default


@dataclass(frozen=True)
class FusionConfig:
    enabled: bool = True
    violence_weight: float = 0.65
    motion_weight: float = 0.20
    weapon_weight: float = 0.15
    weapon_threshold: float = 0.55
    weapon_boost: float = 0.12

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None) -> "FusionConfig":
        fusion_settings: Mapping[str, Any] = {}
        if settings and isinstance(settings.get("fusion"), Mapping):
            fusion_settings = settings["fusion"]  # type: ignore[index]

        return cls(
            enabled=bool(fusion_settings.get("enabled", True)),
            violence_weight=_coerce_float(fusion_settings.get("violence_weight"), 0.65),
            motion_weight=_coerce_float(fusion_settings.get("motion_weight"), 0.20),
            weapon_weight=_coerce_float(fusion_settings.get("weapon_weight"), 0.15),
            weapon_threshold=_coerce_float(fusion_settings.get("weapon_threshold"), 0.55),
            weapon_boost=_coerce_float(fusion_settings.get("weapon_boost"), 0.12),
        )


class ThreatFusionEngine:
    def __init__(self, config: FusionConfig):
        self.config = config

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None) -> "ThreatFusionEngine":
        return cls(FusionConfig.from_settings(settings))

    def assess(
        self,
        *,
        violence_confidence: float,
        motion_score: float = 0.0,
        weapon_score: float = 0.0,
        base_severity: str = "high",
    ) -> dict[str, Any]:
        violence = _clamp(violence_confidence)
        motion = _clamp(motion_score)
        weapon = _clamp(weapon_score)
        base_severity = _normalize_severity(base_severity)

        if not self.config.enabled:
            final_severity = base_severity
            fused_score = violence
        else:
            fused_score = (
                violence * self.config.violence_weight
                + motion * self.config.motion_weight
                + weapon * self.config.weapon_weight
            )

            if weapon >= self.config.weapon_threshold:
                fused_score = _clamp(fused_score + self.config.weapon_boost)

            if weapon >= 0.75:
                fused_score = max(fused_score, 0.92)
            elif violence >= 0.85:
                fused_score = max(fused_score, 0.88)

            if fused_score >= 0.85:
                fused_severity = "critical"
            elif fused_score >= 0.62:
                fused_severity = "high"
            elif fused_score >= 0.40:
                fused_severity = "medium"
            else:
                fused_severity = "medium"

            final_severity = fused_severity if SEVERITY_ORDER[fused_severity] >= SEVERITY_ORDER[base_severity] else base_severity

        if weapon >= self.config.weapon_threshold:
            reason = "Weapon signal increased the threat score."
        elif motion >= 0.55:
            reason = "Sustained motion raised operational risk."
        elif violence >= 0.85:
            reason = "High violence confidence dominated the decision."
        else:
            reason = "Fusion score combined violence and motion cues."

        return {
            "enabled": self.config.enabled,
            "model": "fusion-v1",
            "score": round(_clamp(fused_score) * 100, 1),
            "severity": final_severity,
            "violenceScore": round(violence * 100, 1),
            "motionScore": round(motion * 100, 1),
            "weaponScore": round(weapon * 100, 1),
            "weaponEnabled": self.config.enabled,
            "reason": reason,
        }
