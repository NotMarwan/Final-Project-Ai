"""WT-26 scoped tests: /stats/overview counts evidence records, never alerts.

Semantics under test (docs/campaign/engineering/26-stats-semantics.md §2.2):
closed window on evidence-write time, exact camera scope, explicit unavailable
quantities (type/latency), previous-window comparison, and explicit failure
states for the route.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.stats_service import (
    aggregate_evidence_records,
    build_overview_stats,
    build_stats_router,
    parse_iso,
)


BASE = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def record(offset_minutes, camera_id="CAM-01", severity="high", clip="abc123", stamp=None):
    return {
        "timestamp": (stamp or (BASE - timedelta(minutes=offset_minutes))).isoformat(),
        "alertId": f"alert-{offset_minutes}-{camera_id}",
        "cameraId": camera_id,
        "severity": severity,
        "confidence": 88.5,
        "clipSha256": clip,
        "snapshotSha256": "N/A",
        "reportSha256": "N/A",
    }


# ── parse_iso ────────────────────────────────────────────────────────────────

def test_parse_iso_requires_timezone_and_normalises_to_utc():
    assert parse_iso("2026-09-26T12:00:00+02:00") == datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
    assert parse_iso("2026-09-26T12:00:00Z") == BASE
    with pytest.raises(ValueError):
        parse_iso("2026-09-26T12:00:00")  # naive
    with pytest.raises(ValueError):
        parse_iso("not-a-time")


# ── aggregation ──────────────────────────────────────────────────────────────

def test_window_is_closed_and_uses_evidence_write_time():
    records = [record(30), record(60), record(90)]
    window_from = BASE - timedelta(minutes=60)
    window_to = BASE - timedelta(minutes=30)
    result = aggregate_evidence_records(records, window_from, window_to)
    # Both boundaries included (closed interval): 30 and 60 minutes ago.
    assert result["recordCount"] == 2
    assert result["firstRecordAt"] is not None and result["lastRecordAt"] is not None


def test_camera_scope_is_exact_and_severity_buckets_keep_unclassified_records():
    records = [
        record(10, camera_id="CAM-01", severity="critical"),
        record(10, camera_id="CAM-02", severity="high"),
        record(10, camera_id="CAM-01", severity="low"),  # unclassified severity
    ]
    scoped = aggregate_evidence_records(records, BASE - timedelta(minutes=30), BASE, "CAM-01")
    assert scoped["recordCount"] == 2
    assert scoped["bySeverity"] == {"critical": 1, "high": 0, "medium": 0, "other": 1}
    assert scoped["byCamera"] == {"CAM-01": 2}


def test_asset_coverage_counts_only_real_hashes():
    records = [record(5, clip="deadbeef"), record(6, clip="N/A"), record(7, clip=None)]
    result = aggregate_evidence_records(records, BASE - timedelta(minutes=30), BASE)
    assert result["recordCount"] == 3
    assert result["assets"] == {"withClip": 1, "withSnapshot": 0, "withReport": 0}


def test_records_with_invalid_timestamps_are_counted_as_skipped_not_dropped_silently():
    records = [record(5), {"timestamp": "garbage", "alertId": "x"}, {"alertId": "no-stamp"}]
    result = aggregate_evidence_records(records, BASE - timedelta(minutes=30), BASE)
    assert result["recordCount"] == 1
    assert result["skippedRecords"] == 2


def test_payload_states_unavailable_quantities_instead_of_inventing_them():
    payload = build_overview_stats([record(5)], BASE - timedelta(minutes=60), BASE, "CAM-01")
    assert payload["scope"] == "evidence-ledger"
    assert payload["timeField"] == "evidenceWriteTimeUtc"
    assert payload["typeBreakdown"] is None
    assert payload["latency"] is None
    assert payload["recordCount"] == 1
    assert payload["cameraId"] == "CAM-01"
    payload_with_path = build_overview_stats(
        [record(5)], BASE - timedelta(minutes=60), BASE,
        ledger={"path": "C:\\private\\evidence_ledger.jsonl", "exists": True, "totalRecords": 1},
    )
    assert payload_with_path["ledger"]["path"] == ""


def test_previous_window_is_the_same_span_shifted_back():
    records = [record(5), record(65), record(200)]
    payload = build_overview_stats(records, BASE - timedelta(minutes=60), BASE)
    assert payload["recordCount"] == 1  # only 5 minutes ago is inside [BASE-60min, BASE]
    previous = payload["previousWindow"]
    assert previous["recordCount"] == 1  # 65 minutes ago sits 5 minutes into the previous hour
    assert previous["to"] == (BASE - timedelta(minutes=60)).isoformat()


def test_previous_window_excludes_shared_boundary_record():
    boundary = record(60)
    payload = build_overview_stats([boundary], BASE - timedelta(minutes=60), BASE)
    assert payload["recordCount"] == 1  # current interval includes its lower bound
    assert payload["previousWindow"]["recordCount"] == 0  # previous interval excludes its upper bound


def test_reversed_window_is_rejected():
    with pytest.raises(ValueError):
        build_overview_stats([], BASE, BASE - timedelta(minutes=1))


# ── route wiring ─────────────────────────────────────────────────────────────

class StubSecurity:
    def __init__(self):
        self.calls = []

    def authorize(self, request, required_role):
        self.calls.append(required_role)
        return "viewer"


class StubLedger:
    def __init__(self, records, path, broken=False):
        self._records = records
        self._broken = broken
        self.config = type("Config", (), {"path": path})()

    def _read_records(self):
        if self._broken:
            raise RuntimeError("Evidence ledger integrity failed at record 1")
        return self._records


def client_for(records=None, broken=False, path="evidence_ledger.jsonl", no_security=False):
    security = None if no_security else StubSecurity()
    ledger = StubLedger(records or [], path, broken=broken)
    app = FastAPI()
    app.include_router(build_stats_router(lambda: ledger, lambda: security))
    return TestClient(app), security


def test_route_returns_payload_and_requires_viewer_role(tmp_path):
    ledger_file = tmp_path / "evidence_ledger.jsonl"
    ledger_file.write_text("{}\n", encoding="utf-8")
    client, security = client_for([record(5)], path=ledger_file)
    response = client.get("/stats/overview", params={"from": (BASE - timedelta(hours=1)).isoformat(), "to": BASE.isoformat()})
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "evidence-ledger"
    assert body["recordCount"] == 1
    assert body["ledger"]["exists"] is True
    assert body["ledger"]["totalRecords"] == 1
    assert body["ledger"]["path"] == ""
    assert security.calls == ["viewer"]


def test_route_fails_closed_when_security_controller_is_missing():
    client, _ = client_for([record(5)], no_security=True)
    response = client.get("/stats/overview", params={
        "from": (BASE - timedelta(hours=1)).isoformat(), "to": BASE.isoformat(),
    })
    assert response.status_code == 503
    assert response.json()["detail"] == "access control is not initialized"


def test_route_rejects_missing_or_invalid_windows():
    client, _ = client_for([])
    assert client.get("/stats/overview").status_code == 422  # missing from/to
    assert client.get("/stats/overview", params={"from": "bad", "to": BASE.isoformat()}).status_code == 400
    assert client.get("/stats/overview", params={"from": BASE.isoformat(), "to": BASE.isoformat()}).status_code == 400
    wide = {"from": (BASE - timedelta(days=400)).isoformat(), "to": BASE.isoformat()}
    assert client.get("/stats/overview", params=wide).status_code == 400


def test_route_reports_ledger_integrity_failure_as_explicit_state():
    client, _ = client_for(broken=True)
    response = client.get("/stats/overview", params={"from": (BASE - timedelta(hours=1)).isoformat(), "to": BASE.isoformat()})
    assert response.status_code == 503
    assert "integrity" in response.json()["detail"]


def test_route_scopes_to_camera_query():
    records = [record(5, camera_id="CAM-01"), record(5, camera_id="CAM-02")]
    client, _ = client_for(records)
    response = client.get("/stats/overview", params={
        "from": (BASE - timedelta(hours=1)).isoformat(), "to": BASE.isoformat(), "cameraId": "CAM-02",
    })
    assert response.status_code == 200
    assert response.json()["recordCount"] == 1
    assert response.json()["byCamera"] == {"CAM-02": 1}
