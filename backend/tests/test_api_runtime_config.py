"""Runtime configuration regression tests for backend.api."""

from __future__ import annotations

import importlib


def test_finalize_config_uses_validated_runtime_policy_over_legacy_sources(monkeypatch):
    api = importlib.import_module("backend.api")

    monkeypatch.setenv("THRESHOLD", "0.51")
    monkeypatch.setattr(api, "CALIBRATION_PROFILE", {"threshold": 0.45}, raising=False)
    monkeypatch.setattr(api, "THRESHOLD", 0.0, raising=False)
    monkeypatch.setattr(api, "state", api.AppState())

    api._finalize_config()
    assert api.THRESHOLD == api.load_decision_config().violence_threshold
    assert api.state.get_threshold() == api.THRESHOLD

    # An explicitly validated runtime update remains authoritative when other
    # startup settings are refreshed. Environment/calibration cannot replace it.
    api.state.set_threshold(0.6)
    api._finalize_config()
    assert api.THRESHOLD == 0.6
    assert api.state.get_threshold() == 0.6
