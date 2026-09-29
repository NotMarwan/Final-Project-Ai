"""G-05: exactly one threshold source (config/thresholds.toml).

This checker greps the decision-path modules for inline numeric literals and
fails on any literal that is not explicitly annotated with ``# g05-allow:`` on
its own line. Policy values (thresholds, weights, gains, gates, windows) must
come from ``config/thresholds.toml`` via ``load_decision_config``; structural
constants (unit conversions, rounding digits, display colours) are permitted
only with a written reason.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.decision_config import DecisionConfig, load_decision_config, load_weapon_taxonomy

BACKEND = Path(__file__).resolve().parents[1]
DECISION_MODULES = [
    BACKEND / "live_alert_decision.py",
    BACKEND / "decision_config.py",
    BACKEND / "fusion.py",
    BACKEND / "calibration_utils.py",
]
ALLOW_MARKER = "g05-allow:"


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = path.read_text(encoding="utf-8").splitlines()
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or isinstance(node.value, (bool, str, bytes, type(None))):
            continue
        if not isinstance(node.value, (int, float)):
            continue
        line = lines[node.lineno - 1]
        if ALLOW_MARKER not in line:
            bad.append(f"{path.name}:{node.lineno}:{node.col_offset} unannotated numeric literal {node.value!r}")
    return bad


def test_decision_path_has_zero_unannotated_numeric_literals():
    report = []
    for module in DECISION_MODULES:
        assert module.exists(), f"missing decision module {module}"
        report.extend(_violations(module))
    if report:
        pytest.fail("G-05 threshold-literal checker violations:\n" + "\n".join(report))


def test_every_policy_value_lives_in_thresholds_toml():
    policy = load_decision_config()
    # Every numeric policy field must round-trip from the TOML mapping only.
    assert DecisionConfig.from_mapping(policy.to_dict()) == policy
    assert load_decision_config().to_dict() == policy.to_dict()


def test_weapon_taxonomy_is_read_from_the_same_single_source():
    taxonomy = load_weapon_taxonomy()
    assert set(taxonomy) == {"firearm", "edged", "fallback_group", "filter_labels"}
    assert not set(taxonomy["firearm"]) & set(taxonomy["edged"])
    assert taxonomy["fallback_group"]
    assert set(taxonomy["filter_labels"]) >= set(taxonomy["firearm"]) | set(taxonomy["edged"])
