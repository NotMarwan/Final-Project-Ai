from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else base_dir / path


def sha256_file(path: Path | None) -> str:
    if not path or not path.exists():
        return "N/A"

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    def __init__(self, config: EvidenceLedgerConfig):
        self.config = config
        self._lock = threading.Lock()
        self.config.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None,
        base_dir: Path,
    ) -> "EvidenceLedger":
        return cls(EvidenceLedgerConfig.from_settings(settings, base_dir))

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.config.path.exists():
            return []

        with self._lock:
            lines = self.config.path.read_text(encoding="utf-8").splitlines()

        records: list[dict[str, Any]] = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def get(self, alert_id: str) -> dict[str, Any] | None:
        for record in reversed(self._read_records()):
            if record.get("alertId") == alert_id:
                return record
        return None

    def append_entry(
        self,
        *,
        alert: Mapping[str, Any],
        clip_path: Path | None,
        snapshot_path: Path | None,
        report_path: Path | None,
        report_text: str,
    ) -> dict[str, Any]:
        alert_id = str(alert.get("id") or "")
        existing = self.get(alert_id)
        if existing:
            return existing

        records = self._read_records()
        previous_hash = records[-1]["currentHash"] if records else "GENESIS"
        face_data = alert.get("faceSummary")
        if not isinstance(face_data, Mapping):
            face_data = {}

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            "clipSha256": sha256_file(clip_path),
            "snapshotSha256": sha256_file(snapshot_path),
            "reportSha256": sha256_file(report_path),
            "reportTextSha256": sha256_text(report_text or ""),
            "prevHash": previous_hash,
        }
        payload["currentHash"] = sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))

        with self._lock:
            with self.config.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return payload

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "path": str(self.config.path),
            "exists": self.config.path.exists(),
        }
