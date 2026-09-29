from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class EvidenceIntegrityError(ValueError):
    """A damaged ledger must be reviewed before additional evidence is linked."""


class EvidenceStorageError(OSError):
    """An append could not be persisted; the ledger was rolled back unchanged."""


# Record types in the evidence chain. The alert receipt is the primary record
# returned by ``get()`` / ``GET /evidence_chain/{alertId}``; the other types are
# additive follow-up records linked to the same alertId (SC-8 additive-only).
ALERT_RECEIPT_TYPE = "alert-receipt"
REPORT_RECEIPT_TYPE = "report-receipt"
# Imported one-way by backend/enhance.py (WT-23 derivative records).
DERIVATIVE_RECORD_TYPE = "enhancement-derivative"
_NON_PRIMARY_RECORD_TYPES = frozenset({REPORT_RECEIPT_TYPE, DERIVATIVE_RECORD_TYPE})


def _reject_json_constant(value: str) -> None:
    raise ValueError("Non-finite ledger value")


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else base_dir / path


def sha256_file(path: Path | None) -> str | None:
    """Hash a published artifact, or record its explicit absence.

    Every published artifact must carry a real SHA-256 in the chain: a
    provided path that cannot be read is an explicit integrity failure
    (R-4 previously substituted the placeholder string ``"N/A"`` here).
    Only a genuinely absent artifact (``path is None``) is recorded as
    ``None`` — an explicit absence, never a fake hash.
    """
    if path is None:
        return None
    path = Path(path)
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise EvidenceIntegrityError(
            f"Evidence artifact is missing or unreadable: {path.name}"
        ) from exc
    return digest.hexdigest()


def hash_asset(path: Path | None) -> tuple[str | None, str]:
    """Hash an artifact, classifying the outcome instead of substituting.

    Returns ``(sha256 | None, status)`` with status ``"hashed"``, ``"absent"``
    (``path is None`` — a declared absence) or ``"unreadable"`` (a declared
    artifact that cannot be read — an explicit failure recorded as data, so
    chain consumers can tell absence from breakage).
    """
    if path is None:
        return None, "absent"
    try:
        return sha256_file(path), "hashed"
    except EvidenceIntegrityError:
        return None, "unreadable"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceLedgerConfig:
    path: Path

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None,
        base_dir: Path,
    ) -> "EvidenceLedgerConfig":
        storage_settings: Mapping[str, Any] = {}
        if settings and isinstance(settings.get("storage"), Mapping):
            storage_settings = settings["storage"]  # type: ignore[index]

        raw_path = str(storage_settings.get("evidence_ledger_path", "./evidence_ledger.jsonl")).strip()
        if not raw_path:
            raw_path = "./evidence_ledger.jsonl"
        return cls(path=_resolve_path(base_dir, raw_path))


class EvidenceLedger:
    # All camera writers run in the API process. Share locks even if callers
    # construct separate ledger objects for the same canonical file path.
    _path_locks: dict[str, Any] = {}
    _path_locks_guard = threading.Lock()

    def __init__(self, config: EvidenceLedgerConfig):
        self.config = config
        key = os.path.normcase(str(config.path.resolve()))
        with self._path_locks_guard:
            self._lock = self._path_locks.setdefault(key, threading.RLock())
        self.config.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None,
        base_dir: Path,
    ) -> "EvidenceLedger":
        return cls(EvidenceLedgerConfig.from_settings(settings, base_dir))

    def _read_records(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self.config.path.exists():
                return []
            lines = self.config.path.read_text(encoding="utf-8").splitlines()
            records: list[dict[str, Any]] = []
            previous_hash = "GENESIS"
            for line_number, line in enumerate(lines, 1):
                try:
                    record = json.loads(line, parse_constant=_reject_json_constant)
                    if not isinstance(record, dict) or not record.get("alertId"):
                        raise ValueError("Invalid ledger record")
                    body = {key: value for key, value in record.items() if key != "currentHash"}
                    expected_hash = sha256_text(json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False))
                    if record.get("prevHash") != previous_hash or record.get("currentHash") != expected_hash:
                        raise ValueError("Broken ledger hash chain")
                except (ValueError, TypeError) as exc:
                    raise EvidenceIntegrityError(f"Evidence ledger integrity failed at record {line_number}") from exc
                records.append(record)
                previous_hash = record["currentHash"]
            return records

    def get(self, alert_id: str) -> dict[str, Any] | None:
        """Return the alert's primary receipt (never follow-up records)."""
        for record in reversed(self._read_records()):
            if record.get("alertId") == alert_id and record.get("recordType") not in _NON_PRIMARY_RECORD_TYPES:
                return record
        return None

    def records_for(self, alert_id: str) -> list[dict[str, Any]]:
        """All chain records for one alert, oldest first (receipts + follow-ups)."""
        return [record for record in self._read_records() if record.get("alertId") == alert_id]

    def append_entry(
        self,
        *,
        alert: Mapping[str, Any],
        clip_path: Path | None,
        snapshot_path: Path | None,
        report_path: Path | None,
        report_text: str,
        record_type: str = ALERT_RECEIPT_TYPE,
        clip_meta: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        alert_id = str(alert.get("id") or "")
        if not alert_id:
            raise ValueError("Evidence requires an alert ID")
        # Hash finalized assets before taking the ledger transaction lock.
        # The caller must not mutate assets after finalization.
        #
        # R-4 hardening: no silent substitution. The hash fields keep the
        # SC-8/C-4a wire sentinel ("N/A" = no hash recorded; the UI parser
        # lib/local-report.ts normalizes it to null) but every new record
        # carries an explicit per-asset status — "hashed" (real SHA-256),
        # "absent" (artifact was never created) or "unreadable" (declared
        # artifact that cannot be read: an explicit failure recorded as
        # data). A published artifact therefore always has either a real
        # SHA-256 chain entry or an explicit failure marker.
        clip_sha, clip_status = hash_asset(clip_path)
        snapshot_sha, snapshot_status = hash_asset(snapshot_path)
        report_sha, report_status = hash_asset(report_path)
        asset_hashes = {
            "clipSha256": clip_sha if clip_sha is not None else "N/A",
            "snapshotSha256": snapshot_sha if snapshot_sha is not None else "N/A",
            "reportSha256": report_sha if report_sha is not None else "N/A",
            "reportTextSha256": sha256_text(report_text or ""),
            "clipHashStatus": clip_status,
            "snapshotHashStatus": snapshot_status,
            "reportHashStatus": report_status,
        }
        face_data = alert.get("faceSummary")
        if not isinstance(face_data, Mapping):
            face_data = {}

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # SC-6: label the clock domain of `timestamp` explicitly.
            "timestampClockDomain": "utc-wall",
            "recordType": record_type,
            "alertId": alert_id,
            "cameraId": alert.get("cameraId"),
            "severity": alert.get("severity"),
            "confidence": alert.get("confidence"),
            "fusionScore": alert.get("fusionScore"),
            "motionScore": alert.get("motionScore"),
            "weaponScore": alert.get("weaponScore"),
            "faceRecognizedCount": face_data.get("recognizedCount"),
            "faceUnknownCount": face_data.get("unknownCount"),
            "faceUnknownIds": face_data.get("unknownIds", []),
            **asset_hashes,
        }
        if clip_meta:
            payload.update(clip_meta)

        with self._lock:
            # One transaction covers duplicate detection, previous-hash choice
            # and append. _read_records uses the same reentrant lock.
            records = self._read_records()
            if record_type == REPORT_RECEIPT_TYPE:
                # Idempotent report downloads: one receipt per distinct PDF.
                existing = next(
                    (
                        record
                        for record in reversed(records)
                        if record.get("alertId") == alert_id
                        and record.get("recordType") == REPORT_RECEIPT_TYPE
                        and record.get("reportSha256") == asset_hashes["reportSha256"]
                    ),
                    None,
                )
            else:
                existing = next(
                    (
                        record
                        for record in reversed(records)
                        if record.get("alertId") == alert_id
                        and record.get("recordType", ALERT_RECEIPT_TYPE) == record_type
                    ),
                    None,
                )
            if existing is not None:
                return existing
            return self._append_locked(payload, records)

    def append_record(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Append a caller-built chain record (e.g. WT-23 derivative records).

        The body MUST carry ``alertId`` and its own ``recordType``. No
        deduplication is applied: follow-up writers own their idempotency.
        """
        alert_id = str(body.get("alertId") or "")
        if not alert_id:
            raise ValueError("Evidence records require an alert ID")
        if not body.get("recordType"):
            raise ValueError("Evidence records require a recordType")
        with self._lock:
            # Validate the existing chain before extending it.
            return self._append_locked(dict(body), self._read_records())

    def _append_locked(self, payload: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
        # Serialize before opening the file so non-finite metadata can never
        # write a partial record. allow_nan=False raises ValueError first.
        payload["prevHash"] = records[-1]["currentHash"] if records else "GENESIS"
        payload["currentHash"] = sha256_text(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        )
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
        with self.config.path.open("ab+") as fh:
            # Accept a valid final JSON record without a terminal newline,
            # but never concatenate the next object onto the same line.
            fh.seek(0, os.SEEK_END)
            start = fh.tell()
            prefix = b""
            if fh.tell():
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    prefix = b"\n"
            try:
                fh.write(prefix + serialized.encode("utf-8"))
                fh.flush()
                os.fsync(fh.fileno())
            except OSError as exc:
                # Storage failure (e.g. disk full): roll back the partial
                # append so the chain file stays exactly as it was.
                try:
                    os.truncate(self.config.path, start)
                except OSError:
                    pass
                raise EvidenceStorageError(
                    "Evidence ledger append failed; chain left unchanged"
                ) from exc
        return payload

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "path": str(self.config.path),
            "exists": self.config.path.exists(),
        }


@dataclass(frozen=True)
class RetentionVerdict:
    """Dry-run retention decision for one published artifact."""

    alert_id: str
    artifact: str  # "clip" | "snapshot" | "report"
    path: str
    age_days: float
    action: str  # "keep" | "prune"
    reason: str  # "retention-disabled" | "within-retention" | "legal-hold" | "older-than-retention"


class EvidenceRetentionPolicy:
    """Dry-run retention planner over published evidence artifacts.

    This campaign NEVER deletes evidence: the policy only reports which
    artifacts are older than ``clips.clip_retention_days`` and therefore
    *would be* prunable once deletion is deliberately implemented and
    reviewed. A legal hold always wins over age.
    """

    def __init__(self, retention_days: float | None, holds: frozenset[str] | set[str]):
        if retention_days is not None:
            retention_days = float(retention_days)
            if retention_days <= 0:
                retention_days = None
        self.retention_days = retention_days
        self.holds = frozenset(holds)

    @property
    def enabled(self) -> bool:
        return self.retention_days is not None

    def evaluate(self, alert_id: str, artifact: str, path: Path, age_days: float) -> RetentionVerdict:
        if not self.enabled:
            action, reason = "keep", "retention-disabled"
        elif alert_id in self.holds:
            action, reason = "keep", "legal-hold"
        elif age_days > float(self.retention_days):
            action, reason = "prune", "older-than-retention"
        else:
            action, reason = "keep", "within-retention"
        return RetentionVerdict(
            alert_id=alert_id,
            artifact=artifact,
            path=str(path),
            age_days=float(age_days),
            action=action,
            reason=reason,
        )


class EvidenceHoldStore:
    """Persists per-alert legal holds beside the evidence ledger (atomic writes)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def load(self) -> set[str]:
        with self._lock:
            if not self.path.exists():
                return set()
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise EvidenceIntegrityError("Evidence hold store is damaged") from exc
            holds = data.get("holds") if isinstance(data, Mapping) else None
            if not isinstance(holds, list) or not all(isinstance(item, str) for item in holds):
                raise EvidenceIntegrityError("Evidence hold store is damaged")
            return set(holds)

    def set_hold(self, alert_id: str, held: bool) -> set[str]:
        if not alert_id:
            raise ValueError("A hold requires an alert ID")
        with self._lock:
            holds = self.load()
            if held:
                holds.add(alert_id)
            else:
                holds.discard(alert_id)
            payload = json.dumps({"holds": sorted(holds)}, ensure_ascii=False, sort_keys=True)
            temporary = self.path.with_suffix(self.path.suffix + ".part")
            with temporary.open("w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temporary, self.path)
            return holds
