from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SEVERITY_ORDER = {"medium": 0, "high": 1, "critical": 2}
WEAPON_TYPE_KEYWORDS = {
    "knife": ("knife", "blade", "sword", "dagger"),
    "gun": ("gun", "pistol", "rifle", "revolver", "shotgun"),
    "explosive": ("bomb", "grenade", "explosive", "dynamite"),
}


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


def _classify_weapon_type(labels: list | None) -> str:
    if not labels:
        return "unknown"

    for raw_label in labels:
        normalized = str(raw_label or "").strip().lower()
        if not normalized:
            continue
        for weapon_type, keywords in WEAPON_TYPE_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                return weapon_type
    return "unknown"


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

    def assess_multi_threat(
        self,
        *,
        violence_confidence: float,
        motion_score: float = 0.0,
        weapon_score: float = 0.0,
        violence_bbox: list | None = None,
        weapon_bbox: list | None = None,
        weapon_labels: list | None = None,
        base_severity: str = "high",
    ) -> dict:
        base_result = self.assess(
            violence_confidence=violence_confidence,
            motion_score=motion_score,
            weapon_score=weapon_score,
            base_severity=base_severity,
        )

        violence = _clamp(violence_confidence)
        weapon = _clamp(weapon_score)
        weapon_threshold = self.config.weapon_threshold
        visual_weapon_threshold = min(weapon_threshold, 0.45)

        threat_boxes = []

        if violence >= 0.5 and violence_bbox:
            threat_boxes.append({
                "id": "violence-01",
                "type": "violence",
                "bbox": violence_bbox,
                "confidence": round(violence, 3),
                "color": [239, 68, 68],
                "label": "VIOLENCE",
            })

        if weapon >= visual_weapon_threshold and weapon_bbox:
            w_type = _classify_weapon_type(weapon_labels)

            color_map = {
                "gun": [220, 38, 38],
                "knife": [245, 158, 11],
                "unknown": [234, 179, 8],
            }

            threat_boxes.append({
                "id": "weapon-" + w_type,
                "type": "weapon",
                "weaponType": w_type,
                "bbox": weapon_bbox,
                "confidence": round(weapon, 3),
                "color": color_map.get(w_type, [234, 179, 8]),
                "label": w_type.upper() if w_type != "unknown" else "WEAPON",
            })

        has_violence = violence >= 0.5
        has_weapon = weapon >= visual_weapon_threshold
        is_multi_threat = has_violence and has_weapon

        return {
            **base_result,
            "multiThreat": {
                "hasViolence": has_violence,
                "hasWeapon": has_weapon,
                "isMultiThreat": is_multi_threat,
                "violenceScore": round(violence * 100, 1),
                "weaponScore": round(weapon * 100, 1),
                "fusedScore": base_result["score"],
                "severity": base_result["severity"],
                "threatBoxes": threat_boxes,
                "reason": base_result["reason"],
            },
        }
