"""WT-25 API tests — incident triage routes over the real ASGI stack.

The FastAPI lifespan (model engines, camera workers) is intentionally NOT
started: these tests exercise routing, request validation, the state machine,
the response shape and the SSE fan-out, which is everything the routes own.

Scoped command:

    py -3.14 -m pytest backend/tests/test_alert_triage.py \
        backend/tests/test_alert_triage_api.py -q
"""
from __future__ import annotations

import os
import sys
import types

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _alert(alert_id: str) -> dict:
    return {
        "id": alert_id,
        "cameraId": "CAM-01",
        "severity": "high",
        "type": "Violence",
        "confidence": 71.5,
        "timestamp": "00:00:00 UTC",
        "isoTime": "2026-09-29T00:00:00+00:00",
        "location": "Test location",
    }


@pytest.fixture
def api_env(monkeypatch):
    import api

    class _AllowAll:
        role = "admin"

        def authorize(self, request, required_role="viewer"):
            if required_role == "admin" and self.role != "admin":
                raise HTTPException(status_code=403, detail="admin required")
            return self.role

    controller = _AllowAll()
    broadcasts: list[dict] = []
    monkeypatch.setattr(api, "security_controller", controller)
    monkeypatch.setattr(api, "audit_logger", types.SimpleNamespace(record=lambda *args, **kwargs: None))
    monkeypatch.setattr(api.state, "broadcast_alert", lambda payload: broadcasts.append(payload))
    client = TestClient(api.app)
    try:
        yield types.SimpleNamespace(api=api, client=client, controller=controller, broadcasts=broadcasts)
    finally:
        client.close()


@pytest.fixture()
def alert_id(api_env):
    identifier = "alert-triage-test-1"
    api_env.api.state.register_alert(_alert(identifier))
    api_env.api.state.update_alert(identifier, {"triage": None})
    api_env.broadcasts.clear()
    return identifier


def test_untriaged_alert_reads_null(api_env, alert_id):
    response = api_env.client.get(f"/alerts/{alert_id}/triage")
    assert response.status_code == 200
    assert response.json() == {"alertId": alert_id, "triage": None}


def test_viewer_cannot_mutate_triage(api_env, alert_id):
    api_env.controller.role = "viewer"
    response = api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "acknowledge"})
    assert response.status_code == 403
    assert api_env.api.state.get_alert(alert_id)["triage"] is None
    assert api_env.broadcasts == []


def test_workflow_transitions_and_actor(api_env, alert_id):
    api_env.controller.role = "admin"
    try:
        acknowledged = api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "acknowledge"})
        assert acknowledged.status_code == 200
        body = acknowledged.json()
        assert body["state"] == "in_progress"
        assert body["action"] == "acknowledge"
        assert body["actor"] == "admin"
        assert len(body["history"]) == 1

        held = api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "hold"})
        assert held.json()["state"] == "on_hold"
        resumed = api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "resume"})
        assert resumed.json()["state"] == "in_progress"
        resolved = api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "resolve"})
        assert resolved.json()["state"] == "resolved"
        assert [entry["action"] for entry in resolved.json()["history"]] == [
            "acknowledge", "hold", "resume", "resolve",
        ]
        reopened = api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "reopen"})
        assert reopened.json()["state"] == "in_progress"
    finally:
        api_env.controller.role = "viewer"


def test_state_survives_a_reread(api_env, alert_id):
    api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "acknowledge"})
    reread = api_env.client.get(f"/alerts/{alert_id}/triage")
    assert reread.json()["triage"]["state"] == "in_progress"


def test_each_transition_is_broadcast_once(api_env, alert_id):
    api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "acknowledge"})
    api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "hold"})
    assert [frame["type"] for frame in api_env.broadcasts] == ["alert_triage", "alert_triage"]
    assert [frame["triage"]["state"] for frame in api_env.broadcasts] == ["in_progress", "on_hold"]
    assert {frame["alertId"] for frame in api_env.broadcasts} == {alert_id}


def test_disallowed_transition_conflicts(api_env, alert_id):
    api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "resolve"})
    broadcasts_before_conflict = len(api_env.broadcasts)
    conflict = api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "hold"})
    assert conflict.status_code == 409
    assert "conflict" in conflict.json()["detail"]
    assert len(api_env.broadcasts) == broadcasts_before_conflict


def test_unknown_action_is_rejected(api_env, alert_id):
    response = api_env.client.post(f"/alerts/{alert_id}/triage", json={"action": "delete"})
    assert response.status_code == 400
    assert "invalid_action" in response.json()["detail"]


def test_unknown_alert_is_404(api_env):
    response = api_env.client.post("/alerts/alert-triage-absent/triage", json={"action": "acknowledge"})
    assert response.status_code == 404


def test_invalid_alert_id_is_400(api_env):
    response = api_env.client.post("/alerts/..%2Fescape/triage", json={"action": "acknowledge"})
    assert response.status_code in (400, 404)


def test_routes_are_registered_with_expected_methods(api_env):
    triage_routes = [route for route in api_env.api.app.routes if "triage" in getattr(route, "path", "")]
    assert sorted({method for route in triage_routes for method in route.methods}) == ["GET", "POST"]
