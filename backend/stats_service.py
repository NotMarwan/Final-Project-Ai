"""Additive statistics route over the evidence ledger (WT-26, slice S-13).

Counting semantics — see docs/campaign/engineering/26-stats-semantics.md §2.2:

* This route aggregates EVIDENCE RECORDS from `evidence_ledger.jsonl`, never raw
  alert occurrences. A record exists only for alerts that received evidence
  artifacts (clip ready or report generated), so the honest denominator is
  "alerts with generated evidence".
* The record ``timestamp`` is the evidence-write time (UTC), not the alert
  occurrence time. The payload states this as ``timeField`` and the window is
  applied to it. No other time basis is available from the ledger.
* The ledger stores no alert type and no latency, so ``typeBreakdown`` and
  ``latency`` are explicitly ``None`` in the payload — quantities the persisted
  source cannot supply are labelled unavailable, never invented.

The route is registered by ``backend/api.py`` via ``build_stats_router`` so the
shared FastAPI route table (SC-1) gains exactly one additive endpoint.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from fastapi import APIRouter, HTTPException, Query, Request

SEVERITY_KEYS = ("critical", "high", "medium")
MAX_WINDOW_DAYS = 366


def parse_iso(value: str) -> datetime:
    """Parse a timezone-aware ISO-8601 timestamp; naive input is rejected."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _record_time(record: Mapping[str, Any]) -> datetime | None:
    raw = record.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return parse_iso(raw)
    except ValueError:
        return None


def aggregate_evidence_records(
    records: Sequence[Mapping[str, Any]],
    window_from: datetime,
    window_to: datetime,
    camera_id: str | None = None,
    *,
    end_inclusive: bool = True,
) -> dict[str, Any]:
    """Aggregate evidence records in [from, to] or [from, to) when requested."""
    by_severity = {"critical": 0, "high": 0, "medium": 0, "other": 0}
    by_camera: dict[str, int] = {}
    assets = {"withClip": 0, "withSnapshot": 0, "withReport": 0}
    matched = 0
    skipped = 0
    first_at: str | None = None
    last_at: str | None = None
    for record in records:
        stamp = _record_time(record)
        if stamp is None:
            skipped += 1
            continue
        if stamp < window_from or (stamp > window_to if end_inclusive else stamp >= window_to):
            continue
        record_camera = record.get("cameraId")
        if camera_id is not None and record_camera != camera_id:
            continue
        matched += 1
        severity = record.get("severity")
        if severity in SEVERITY_KEYS:
            by_severity[str(severity)] += 1
        else:
            by_severity["other"] += 1
        if isinstance(record_camera, str) and record_camera:
            by_camera[record_camera] = by_camera.get(record_camera, 0) + 1
        if record.get("clipSha256") not in (None, "", "N/A"):
            assets["withClip"] += 1
        if record.get("snapshotSha256") not in (None, "", "N/A"):
            assets["withSnapshot"] += 1
        if record.get("reportSha256") not in (None, "", "N/A"):
            assets["withReport"] += 1
        iso = stamp.isoformat()
        if first_at is None or iso < first_at:
            first_at = iso
        if last_at is None or iso > last_at:
            last_at = iso
    return {
        "recordCount": matched,
        "bySeverity": by_severity,
        "byCamera": by_camera,
        "assets": assets,
        "firstRecordAt": first_at,
        "lastRecordAt": last_at,
        "skippedRecords": skipped,
    }


def build_overview_stats(
    records: Sequence[Mapping[str, Any]],
    window_from: datetime,
    window_to: datetime,
    camera_id: str | None = None,
    ledger: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the /stats/overview payload for one explicit window + camera scope."""
    if window_to <= window_from:
        raise ValueError("window end must be after window start")
    span = window_to - window_from
    previous_from = window_from - span
    previous_to = window_to - span
    current = aggregate_evidence_records(records, window_from, window_to, camera_id)
    previous = aggregate_evidence_records(
        records, previous_from, previous_to, camera_id, end_inclusive=False,
    )
    return {
        "scope": "evidence-ledger",
        "timeField": "evidenceWriteTimeUtc",
        "window": {"from": window_from.isoformat(), "to": window_to.isoformat()},
        "cameraId": camera_id,
        "recordCount": current["recordCount"],
        "bySeverity": current["bySeverity"],
        "byCamera": current["byCamera"],
        "assets": current["assets"],
        "firstRecordAt": current["firstRecordAt"],
        "lastRecordAt": current["lastRecordAt"],
        "skippedRecords": current["skippedRecords"],
        # The ledger stores neither the alert type nor any latency: unavailable.
        "typeBreakdown": None,
        "latency": None,
        "previousWindow": {
            "from": previous_from.isoformat(),
            "to": previous_to.isoformat(),
            "recordCount": previous["recordCount"],
        },
        "ledger": {**dict(ledger or {"path": "", "exists": False, "totalRecords": 0}), "path": ""},
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def build_stats_router(
    get_ledger: Callable[[], Any],
    get_security: Callable[[], Any],
) -> APIRouter:
    """Wire the route to the api.py singletons (evidence_ledger, security_controller)."""
    router = APIRouter()

    @router.get("/stats/overview", summary="Evidence-ledger statistics for the overview")
    def stats_overview(
        request: Request,
        from_: str = Query(..., alias="from", description="Window start, ISO-8601 with timezone"),
        to: str = Query(..., description="Window end, ISO-8601 with timezone"),
        cameraId: str | None = Query(None, max_length=128, description="Exact camera scope; omitted = all cameras"),
    ) -> dict[str, Any]:
        security = get_security()
        if security is None:
            raise HTTPException(status_code=503, detail="access control is not initialized")
        security.authorize(request, required_role="viewer")
        try:
            window_from = parse_iso(from_)
            window_to = parse_iso(to)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if window_to <= window_from:
            raise HTTPException(status_code=400, detail="window end must be after window start")
        if window_to - window_from > timedelta(days=MAX_WINDOW_DAYS):
            raise HTTPException(status_code=400, detail=f"window span exceeds {MAX_WINDOW_DAYS} days")
        ledger = get_ledger()
        if ledger is None:
            raise HTTPException(status_code=503, detail="evidence ledger is not initialized")
        read_records = getattr(ledger, "_read_records", None)
        if not callable(read_records):
            raise HTTPException(status_code=503, detail="evidence ledger cannot be read")
        try:
            records = read_records()
        except Exception as exc:  # EvidenceIntegrityError and OS errors are one explicit failure state.
            raise HTTPException(status_code=503, detail="evidence ledger integrity check failed") from exc
        config = getattr(ledger, "config", None)
        raw_path = getattr(config, "path", "")
        try:
            path_exists = Path(str(raw_path)).exists() if raw_path else False
        except OSError:
            path_exists = False
        ledger_meta = {
            "path": "",
            "exists": path_exists,
            "totalRecords": len(records),
        }
        return build_overview_stats(records, window_from, window_to, cameraId, ledger_meta)

    return router
