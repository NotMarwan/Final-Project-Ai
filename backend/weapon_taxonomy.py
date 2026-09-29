"""Taxonomy mapping layer at the F-09 weapon output boundary.

Canonical groups (firearm / edged) plus a foreign-class fallback. Alert-level
labels and severity keys derive from the coarse group only, so a subtype
mapping error (pistol vs revolver, knife vs sword) can never change the
severity of an alert. Raw subtypes are preserved as detail.

The mapping itself is config-driven (SC-5 `config/thresholds.toml` ->
`decision_config.load_weapon_taxonomy()`); this module only applies it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# Group names are a cross-module contract (WT-20 maps them verbatim:
# firearm->gun, edged->knife, other-weapon->unknown in fusion box typing).
GROUP_FIREARM = "firearm"
GROUP_EDGED = "edged"
GROUP_FALLBACK = "other-weapon"

# Alert-label alias pairs: the alert layer accepts either subtype of an
# unresolvable pair (WT-07 rec #3). Config may override via "alias_pairs".
DEFAULT_ALIAS_PAIRS: tuple[tuple[str, ...], ...] = (
    ("pistol", "revolver"),
    ("knife", "sword"),
)


class TaxonomyConfigError(ValueError):
    """Invalid taxonomy mapping configuration."""


def _normalize(label: Any) -> str:
    return str(label).strip().lower()


def _as_str_tuple(raw: Any, name: str) -> tuple[str, ...]:
    if isinstance(raw, str):
        items = tuple(_normalize(part) for part in raw.split(",") if part.strip())
    elif isinstance(raw, Sequence):
        items = tuple(_normalize(item) for item in raw if str(item).strip())
    else:
        raise TaxonomyConfigError(f"{name} must be a list of labels")
    if not items or any(not item for item in items):
        raise TaxonomyConfigError(f"{name} must contain nonempty labels")
    return items


@dataclass(frozen=True)
class WeaponTaxonomy:
    """Config-driven subtype -> group -> canonical alert label mapping."""

    firearm: tuple[str, ...]
    edged: tuple[str, ...]
    fallback_group: str = GROUP_FALLBACK
    alias_pairs: tuple[tuple[str, ...], ...] = DEFAULT_ALIAS_PAIRS
    # Detector label filter (SC-5 `taxonomy_weapon.filter_labels`): which head
    # classes the runtime keeps. Defaults to every head class so no subtype is
    # silently dropped (runtime-map §3.3).
    filter_labels: tuple[str, ...] | None = None
    _alias_of: dict[str, str] = field(default_factory=dict, init=False, compare=False)

    def __post_init__(self) -> None:
        if not self.firearm or not self.edged:
            raise TaxonomyConfigError("firearm and edged groups must be nonempty")
        if not str(self.fallback_group).strip():
            raise TaxonomyConfigError("fallback_group must be nonempty")
        overlap = set(self.firearm) & set(self.edged)
        if overlap:
            raise TaxonomyConfigError(f"groups must be disjoint; overlap: {sorted(overlap)}")
        if self.filter_labels is not None and set(self.filter_labels) < set(self.firearm) | set(self.edged):
            raise TaxonomyConfigError("filter_labels must cover the firearm and edged subtypes")
        alias_of: dict[str, str] = {}
        for pair in self.alias_pairs:
            if len(pair) < 2 or any(not str(name).strip() for name in pair):
                raise TaxonomyConfigError("alias pairs need at least two nonempty labels")
            members = tuple(_normalize(name) for name in pair)
            canonical = members[0]
            for member in members:
                previous = alias_of.get(member)
                if previous is not None and previous != canonical:
                    raise TaxonomyConfigError(f"label {member!r} appears in two alias pairs")
                alias_of[member] = canonical
        object.__setattr__(self, "_alias_of", alias_of)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "WeaponTaxonomy":
        """Build from the SC-5 `[taxonomy_weapon]` table contents
        (`decision_config.load_weapon_taxonomy()` output)."""
        if not isinstance(values, Mapping):
            raise TaxonomyConfigError("taxonomy mapping must be a table")
        unknown = set(values) - {"firearm", "edged", "fallback_group",
                                 "alias_pairs", "filter_labels"}
        if unknown:
            raise TaxonomyConfigError(f"unknown taxonomy keys: {sorted(unknown)}")
        raw_pairs = values.get("alias_pairs")
        if raw_pairs is None:
            alias_pairs = DEFAULT_ALIAS_PAIRS
        elif isinstance(raw_pairs, Sequence) and not isinstance(raw_pairs, str):
            alias_pairs = tuple(_as_str_tuple(pair, "alias_pairs") for pair in raw_pairs)
        else:
            raise TaxonomyConfigError("alias_pairs must be a list of label lists")
        raw_filter = values.get("filter_labels")
        return cls(
            firearm=_as_str_tuple(values.get("firearm"), "firearm"),
            edged=_as_str_tuple(values.get("edged"), "edged"),
            fallback_group=_normalize(values.get("fallback_group") or GROUP_FALLBACK),
            alias_pairs=alias_pairs,
            filter_labels=(None if raw_filter is None else _as_str_tuple(raw_filter, "filter_labels")),
        )

    def label_filter(self) -> tuple[str, ...]:
        """Detector label filter: SC-5 filter_labels, else every subtype."""
        if self.filter_labels is not None:
            return tuple(self.filter_labels)
        return tuple(self.firearm) + tuple(self.edged)

    @property
    def group_names(self) -> tuple[str, ...]:
        return (GROUP_FIREARM, GROUP_EDGED, self.fallback_group)

    def subtype(self, label: Any) -> str:
        """Raw normalized detector label (detail only, never a severity key)."""
        return _normalize(label)

    def group_for(self, label: Any) -> str:
        """Coarse group for a detector label; unknown labels fall back."""
        name = _normalize(label)
        if name in self.firearm:
            return GROUP_FIREARM
        if name in self.edged:
            return GROUP_EDGED
        return self.fallback_group

    def canonical_label(self, label: Any) -> str:
        """Alert-level label: alias pairs collapse to their first member."""
        name = _normalize(label)
        return self._alias_of.get(name, name)

    def severity_key(self, label: Any) -> str:
        """Severity is keyed on the coarse group, never on the subtype."""
        return self.group_for(label)


def default_taxonomy() -> WeaponTaxonomy:
    """Six-class weapon head defaults (ONNX `names`): pistol, rifle, shotgun,
    knife, sword, revolver. Used only where SC-5 config is not yet wired."""
    return WeaponTaxonomy(
        firearm=("pistol", "revolver", "rifle", "shotgun"),
        edged=("knife", "sword"),
    )
