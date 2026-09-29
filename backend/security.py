from __future__ import annotations

import json
import hmac
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from fastapi import HTTPException, Request


def _coerce_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else base_dir / path


@dataclass(frozen=True)
class AccessConfig:
    api_key: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None, env: Mapping[str, str] | None = None) -> "AccessConfig":
        env = env or {}
        security_settings: Mapping[str, Any] = {}
        if settings and isinstance(settings.get("security"), Mapping):
            security_settings = settings["security"]  # type: ignore[index]

        api_key = _coerce_str(env.get("ADMIN_API_KEY")) or _coerce_str(security_settings.get("api_key"))
        return cls(api_key=api_key)


class AccessController:
    def __init__(self, config: AccessConfig):
        self.config = config

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None, env: Mapping[str, str] | None = None) -> "AccessController":
        return cls(AccessConfig.from_settings(settings, env))

    def authorize(self, request: Request, required_role: str = "viewer") -> str:
        if required_role not in {"viewer", "operator", "admin"}:
            raise HTTPException(status_code=403, detail="Unknown permission")
        provided_key = _coerce_str(request.headers.get("x-api-key"))
        if self.config.enabled:
            if not hmac.compare_digest(provided_key.encode(), self.config.api_key.encode()):
                raise HTTPException(status_code=401, detail="Invalid API key")
            # This is an administrator credential. Client role headers confer no authority.
            return "admin"
        if required_role != "viewer":
            raise HTTPException(status_code=503, detail="Administrator authentication is not configured")
        return "viewer"

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "apiKeyConfigured": bool(self.config.api_key),
        }


@dataclass(frozen=True)
class AuditConfig:
    path: Path

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None,
        base_dir: Path,
    ) -> "AuditConfig":
        audit_settings: Mapping[str, Any] = {}
        if settings and isinstance(settings.get("security"), Mapping):
            audit_settings = settings["security"]  # type: ignore[index]

        raw_path = _coerce_str(audit_settings.get("audit_log_path"), "./audit_logs.jsonl")
        return cls(path=_resolve_path(base_dir, raw_path))


class AuditLogger:
    def __init__(self, config: AuditConfig):
        self.config = config
        self._lock = threading.Lock()
        self.config.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None,
        base_dir: Path,
    ) -> "AuditLogger":
        return cls(AuditConfig.from_settings(settings, base_dir))

    def record(
        self,
        action: str,
        status: str,
        *,
        role: str = "system",
        alert_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "status": status,
            "role": role,
            "alertId": alert_id,
            "details": dict(details or {}),
        }
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with self.config.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return entry

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.config.path.exists():
            return []

        with self._lock:
            lines = self.config.path.read_text(encoding="utf-8").splitlines()

        records: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def status(self) -> dict[str, Any]:
        size = self.config.path.stat().st_size if self.config.path.exists() else 0
        return {
            "enabled": True,
            "path": str(self.config.path),
            "exists": self.config.path.exists(),
            "sizeBytes": size,
        }
