"""Validated operating policy shared by API, inference workers and live decisions.

The TOML file is the only default source. Runtime changes are validated copies
of this policy and must be propagated explicitly to workers. No environment or
model calibration file silently overrides these values.

G-05: zero inline policy numbers live outside ``config/thresholds.toml``; the
structural constants below are bounds/ordering only and every numeric literal
carries a ``# g05-allow:`` justification (enforced by
``backend/tests/test_threshold_literals.py``).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
import math
from pathlib import Path
from typing import Any, Mapping
import tomllib

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "thresholds.toml"  # g05-allow: path traversal index

# Structural (non-policy) bounds; values themselves come from the TOML source.
_COUNT_UPPER = 1000  # g05-allow: structural cap on count-like fields
_INTERVAL_UPPER = 65536  # g05-allow: structural cap on interval/size fields
SEVERITY_ORDER = {"none": -1, "medium": 0, "high": 1, "critical": 2}  # g05-allow: band ordering, not thresholds
_COUNT_LIKE = frozenset({"weapon_infer_interval", "weapon_input_size"})
_UNBOUNDED_SECONDS = frozenset({"min_decision_interval_seconds", "cooldown_seconds", "history_max_age_seconds"})
_UNBOUNDED_MS = frozenset({
    "weapon_min_interval_ms", "weapon_realtime_threshold_ms",
    "weapon_score_decay_half_life_ms", "weapon_signal_ttl_ms",
})


@dataclass(frozen=True)
class DecisionConfig:
    schema_version: int
    violence_threshold: float
    weapon_threshold: float
    weapon_display_threshold: float
    watch_threshold: float
    confirm_threshold: float
    confirm_n: int
    confirm_m: int
    min_decision_interval_seconds: float
    cooldown_seconds: float
    history_max_age_seconds: float
    severity_medium_threshold: float
    severity_high_threshold: float
    severity_critical_threshold: float
    fusion_violence_weight: float
    fusion_weapon_weight: float
    fusion_weapon_boost: float
    fusion_strong_weapon_threshold: float
    fusion_strong_weapon_floor: float
    fusion_strong_violence_threshold: float
    fusion_strong_violence_floor: float
    confirm_weight_sum: float
    confirm_weight_gain: float
    cascade_gate_threshold: float
    weapon_min_confidence: float
    weapon_independent_alert_threshold: float
    weapon_score_ema_alpha: float
    weapon_infer_interval: int
    weapon_min_interval_ms: float
    weapon_realtime_threshold_ms: float
    weapon_score_decay_half_life_ms: float
    weapon_signal_ttl_ms: float
    weapon_input_size: int

    def __post_init__(self) -> None:
        for name in ("schema_version", "confirm_n", "confirm_m"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:  # g05-allow: positivity bound
                raise ValueError(f"{name} must be a positive integer")
        if self.schema_version != 1:  # g05-allow: schema gate, not a policy value
            raise ValueError("Unsupported decision policy schema version")
        if not self.confirm_n <= self.confirm_m <= _COUNT_UPPER:
            raise ValueError("Confirmation counts must satisfy 1 <= n <= m <= 1000")
        for field in fields(self):
            if field.name in ("schema_version", "confirm_n", "confirm_m"):
                continue
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError(f"{field.name} must be finite numeric data")
            if field.name in _COUNT_LIKE:
                if not 1 <= value <= _INTERVAL_UPPER:  # g05-allow: structural interval/size bound
                    raise ValueError(f"{field.name} is outside its permitted range")
                continue
            if field.name in _UNBOUNDED_SECONDS or field.name in _UNBOUNDED_MS:
                if not 0 <= value:  # g05-allow: durations are non-negative
                    raise ValueError(f"{field.name} is outside its permitted range")
                continue
            if field.name == "confirm_weight_sum":
                if not self.confirm_n <= value <= _COUNT_UPPER:
                    raise ValueError("confirm_weight_sum must satisfy confirm_n <= value <= 1000")
                continue
            if not 0 <= value <= 1:  # g05-allow: probabilities/weights live in [0,1]
                raise ValueError(f"{field.name} is outside its permitted range")
        if self.history_max_age_seconds <= 0:  # g05-allow: age bound must be positive
            raise ValueError("history_max_age_seconds must be positive")
        if self.watch_threshold > self.confirm_threshold:
            raise ValueError("watch_threshold must not exceed confirm_threshold")
        if self.weapon_display_threshold > self.weapon_threshold:
            raise ValueError("Weapon display threshold must not exceed alert threshold")
        if not self.severity_medium_threshold <= self.severity_high_threshold <= self.severity_critical_threshold:
            raise ValueError("Severity thresholds must be ordered")

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "DecisionConfig":
        expected = {field.name for field in fields(cls)}
        if set(values) != expected:
            raise ValueError("Decision policy has missing or unknown fields")
        return cls(**dict(values))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_updates(self, **changes: Any) -> "DecisionConfig":
        return replace(self, **changes)

    def severity_for(self, score: float) -> str:
        if not math.isfinite(score) or score < self.severity_medium_threshold:
            return "none"
        if score >= self.severity_critical_threshold:
            return "critical"
        if score >= self.severity_high_threshold:
            return "high"
        return "medium"

    def alert_severity_for(self, score: float) -> str:
        """Severity for a CONFIRMED alert: never below ``medium`` (R-3).

        The frontend alert envelope validator rejects ``severity: "none"``
        (runtime-map R-3), and a confirmed alert is by definition at least a
        medium-severity event.
        """
        severity = self.severity_for(score)
        return severity if SEVERITY_ORDER[severity] >= SEVERITY_ORDER["medium"] else "medium"


def _load_source(path: str | Path | None) -> dict[str, Any]:
    with Path(path or DEFAULT_CONFIG_PATH).open("rb") as source:
        values = tomllib.load(source)
    unknown_tables = {key for key, value in values.items() if isinstance(value, dict) and key != "taxonomy_weapon"}
    if unknown_tables:
        raise ValueError(f"Decision policy has unknown tables: {sorted(unknown_tables)}")
    return values


def load_decision_config(path: str | Path | None = None) -> DecisionConfig:
    values = {key: value for key, value in _load_source(path).items() if not isinstance(value, dict)}
    return DecisionConfig.from_mapping(values)


def load_weapon_taxonomy(path: str | Path | None = None) -> dict[str, Any]:
    """Single validated reader for the coarse weapon taxonomy (SC-5 table)."""
    table = _load_source(path).get("taxonomy_weapon")
    if not isinstance(table, Mapping):
        raise ValueError("Decision policy is missing the taxonomy_weapon table")
    if set(table) != {"firearm", "edged", "fallback_group", "filter_labels"}:
        raise ValueError("taxonomy_weapon has missing or unknown fields")
    firearm, edged = table["firearm"], table["edged"]
    for name, group in (("firearm", firearm), ("edged", edged), ("filter_labels", table["filter_labels"])):
        if not isinstance(group, list) or not group or not all(isinstance(item, str) and item for item in group):
            raise ValueError(f"taxonomy_weapon.{name} must be a nonempty list of names")
        if len(set(group)) != len(group):
            raise ValueError(f"taxonomy_weapon.{name} must not contain duplicates")
    if set(firearm) & set(edged):
        raise ValueError("A weapon subtype cannot belong to both firearm and edged")
    fallback = table["fallback_group"]
    if not isinstance(fallback, str) or not fallback:
        raise ValueError("taxonomy_weapon.fallback_group must be a nonempty group name")
    if set(table["filter_labels"]) < set(firearm) | set(edged):
        raise ValueError("filter_labels must cover the firearm and edged subtypes")
    return {"firearm": list(firearm), "edged": list(edged),
            "fallback_group": fallback, "filter_labels": list(table["filter_labels"])}
