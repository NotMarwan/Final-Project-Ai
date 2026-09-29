"""Evidence fusion; motion describes context and never creates a threat.

Modality independence is a hard rule: weapon evidence never inflates the
violence score (or vice versa), person counts never enter the fused score, and
severity keys on the coarse weapon group, never on raw subtypes.
G-05: every numeric literal below is display/unit/ordering structure and is
annotated ``# g05-allow:``; fusion weights come from `config/thresholds.toml`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping

try:
    from .decision_config import DecisionConfig, load_decision_config
    from .calibration_utils import calibration_state
except ImportError:
    from decision_config import DecisionConfig, load_decision_config
    from calibration_utils import calibration_state

SEVERITY_ORDER = {"none": -1, "medium": 0, "high": 1, "critical": 2}  # g05-allow: band ordering
WEAPON_TYPE_KEYWORDS = {
    "knife": ("knife", "blade", "sword", "dagger"),
    "gun": ("gun", "pistol", "rifle", "revolver", "shotgun"),
    "explosive": ("bomb", "grenade", "explosive", "dynamite"),
}
# Coarse-group boundary (F-09): group -> alert weapon type; subtypes never key severity.
WEAPON_GROUP_TYPES = {"firearm": "gun", "edged": "knife", "other-weapon": "unknown"}
_PERCENT = 100.0  # g05-allow: percent display scaling
_BOX_ROUNDING = 3  # g05-allow: display rounding
_SCORE_ROUNDING = 1  # g05-allow: display rounding
_WEAPON_BOX_COLORS = {"gun": [220, 38, 38], "knife": [245, 158, 11]}  # g05-allow: display colours
_DEFAULT_BOX_COLOR = [234, 179, 8]  # g05-allow: display colour
_VIOLENCE_BOX_COLOR = [239, 68, 68]  # g05-allow: display colour


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0  # g05-allow: clamp lower bound
    return max(0.0, min(1.0, number)) if math.isfinite(number) else 0.0  # g05-allow: score domain


def _classify_weapon_type(labels: list | None, group: str | None = None) -> str:
    if group:
        return WEAPON_GROUP_TYPES.get(str(group).strip().lower(), "unknown")
    for raw_label in labels or []:
        normalized = str(raw_label or "").strip().lower()
        for weapon_type, keywords in WEAPON_TYPE_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                return weapon_type
    return "unknown"


def _calibration_status() -> str:
    try:
        return str(calibration_state(use_cache=True).get("status", "unverified"))
    except Exception:  # never let status reporting break a decision path
        return "unverified"


@dataclass(frozen=True)
class FusionConfig:
    enabled: bool = True
    policy: DecisionConfig = field(default_factory=load_decision_config)

    @property
    def weapon_threshold(self) -> float:
        return self.policy.weapon_threshold

    @property
    def violence_weight(self) -> float:
        return self.policy.fusion_violence_weight

    @property
    def weapon_weight(self) -> float:
        return self.policy.fusion_weapon_weight

    @property
    def motion_weight(self) -> float:
        # Kept for the status endpoint; motion cannot contribute to threat score.
        return 0.0  # g05-allow: motion is context-only by construction

    @property
    def weapon_boost(self) -> float:
        return self.policy.fusion_weapon_boost

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None) -> "FusionConfig":
        # Legacy YAML controls enablement only; thresholds have one authority.
        values = settings.get("fusion", {}) if settings else {}
        values = values if isinstance(values, Mapping) else {}
        policy_values = settings.get("decision_config") if settings else None
        policy = DecisionConfig.from_mapping(policy_values) if isinstance(policy_values, Mapping) else load_decision_config()
        return cls(enabled=bool(values.get("enabled", True)), policy=policy)


class ThreatFusionEngine:
    def __init__(self, config: FusionConfig):
        self.config = config

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None) -> "ThreatFusionEngine":
        return cls(FusionConfig.from_settings(settings))

    def apply_config(self, policy: DecisionConfig) -> None:
        self.config = FusionConfig(enabled=self.config.enabled, policy=policy)

    def assess(self, *, violence_confidence: float, motion_score: float = 0.0,  # g05-allow: context default
               weapon_score: float = 0.0, base_severity: str = "none") -> dict[str, Any]:  # g05-allow: no-evidence default
        violence, motion, weapon = map(_clamp, (violence_confidence, motion_score, weapon_score))
        policy = self.config.policy
        supported = violence >= policy.violence_threshold or weapon >= policy.weapon_threshold
        if not supported:
            fused_score, severity = 0.0, "none"  # g05-allow: no-evidence baseline, not a threshold
            reason = "No qualifying violence or weapon evidence. Motion is context only."
        elif not self.config.enabled:
            fused_score = max(violence, weapon)
            severity = policy.severity_for(fused_score)
            reason = "Model evidence without score fusion."
        else:
            fused_score = violence * policy.fusion_violence_weight + weapon * policy.fusion_weapon_weight
            if weapon >= policy.weapon_threshold:
                fused_score = _clamp(fused_score + policy.fusion_weapon_boost)
            if weapon >= policy.fusion_strong_weapon_threshold:
                fused_score = max(fused_score, policy.fusion_strong_weapon_floor)
            elif violence >= policy.fusion_strong_violence_threshold:
                fused_score = max(fused_score, policy.fusion_strong_violence_floor)
            severity = policy.severity_for(fused_score)
            reason = "Violence and weapon model evidence; motion is context only."
        return {
            "enabled": self.config.enabled,
            "model": "fusion-v2",
            "score": round(_clamp(fused_score) * _PERCENT, _SCORE_ROUNDING),
            "severity": severity,
            "violenceScore": round(violence * _PERCENT, _SCORE_ROUNDING),
            "motionScore": round(motion * _PERCENT, _SCORE_ROUNDING),
            "weaponScore": round(weapon * _PERCENT, _SCORE_ROUNDING),
            "weaponEnabled": self.config.enabled,
            "reason": reason,
            "calibrationStatus": _calibration_status(),
            "scoreSemantics": {
                "score": "rule-based fused score (percent of the 0-1 fused value); not a calibrated probability",
                "violenceScore": "violence model evidence only",
                "weaponScore": "weapon model evidence only",
                "motionScore": "context only; never contributes to the fused score",
                "severity": "rule-based band of the fused score",
            },
        }

    def assess_multi_threat(self, *, violence_confidence: float, motion_score: float = 0.0,  # g05-allow: context default
                            weapon_score: float = 0.0, violence_bbox: list | None = None,  # g05-allow: no-evidence default
                            weapon_bbox: list | None = None, weapon_labels: list | None = None,
                            weapon_group: str | None = None,
                            base_severity: str = "none") -> dict[str, Any]:
        base_result = self.assess(violence_confidence=violence_confidence, motion_score=motion_score,
                                  weapon_score=weapon_score, base_severity=base_severity)
        violence, weapon = _clamp(violence_confidence), _clamp(weapon_score)
        has_violence = violence >= self.config.policy.violence_threshold
        has_weapon = weapon >= self.config.policy.weapon_display_threshold
        boxes = []
        if has_violence and violence_bbox:
            boxes.append({"id": "violence-01", "type": "violence", "bbox": violence_bbox,
                          "confidence": round(violence, _BOX_ROUNDING), "color": _VIOLENCE_BOX_COLOR,
                          "label": "VIOLENCE"})
        if has_weapon and weapon_bbox:
            weapon_type = _classify_weapon_type(weapon_labels, weapon_group)
            color = _WEAPON_BOX_COLORS.get(weapon_type, _DEFAULT_BOX_COLOR)
            boxes.append({"id": "weapon-" + weapon_type, "type": "weapon", "weaponType": weapon_type,
                          "bbox": weapon_bbox, "confidence": round(weapon, _BOX_ROUNDING), "color": color,
                          "label": weapon_type.upper() if weapon_type != "unknown" else "WEAPON"})
        return {**base_result, "multiThreat": {
            "hasViolence": has_violence, "hasWeapon": has_weapon,
            "isMultiThreat": has_violence and has_weapon,
            "violenceScore": round(violence * _PERCENT, _SCORE_ROUNDING),
            "weaponScore": round(weapon * _PERCENT, _SCORE_ROUNDING),
            "fusedScore": base_result["score"], "severity": base_result["severity"],
            "threatBoxes": boxes, "reason": base_result["reason"],
        }}
