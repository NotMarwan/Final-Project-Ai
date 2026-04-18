from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping
from urllib import error, parse, request

SEVERITY_ORDER = {"medium": 0, "high": 1, "critical": 2}


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", ""}:
        return False
    return default


def _coerce_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _normalize_severity(value: Any, default: str = "high") -> str:
    severity = _coerce_str(value, default).lower()
    return severity if severity in SEVERITY_ORDER else default


@dataclass(frozen=True)
class TelegramNotificationConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    min_severity: str = "high"
    request_timeout: float = 8.0
    retries: int = 3
    retry_delay_seconds: float = 1.5

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.bot_token and self.chat_id)

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None,
        env: Mapping[str, str] | None = None,
    ) -> "TelegramNotificationConfig":
        env = env or os.environ
        telegram_settings: Mapping[str, Any] = {}
        if settings:
            notifications = settings.get("notifications", {})
            if isinstance(notifications, Mapping):
                telegram_settings = notifications.get("telegram", {}) or {}

        token = _coerce_str(env.get("TELEGRAM_BOT_TOKEN")) or _coerce_str(
            telegram_settings.get("bot_token")
        )
        chat_id = _coerce_str(env.get("TELEGRAM_CHAT_ID")) or _coerce_str(
            telegram_settings.get("chat_id")
        )

        enabled_env = env.get("TELEGRAM_ENABLED")
        if enabled_env is None:
            enabled = _coerce_bool(
                telegram_settings.get("enabled"),
                default=bool(token and chat_id),
            )
        else:
            enabled = _coerce_bool(enabled_env)

        min_severity = _normalize_severity(
            env.get("TELEGRAM_MIN_SEVERITY")
            or telegram_settings.get("min_severity"),
            default="high",
        )

        return cls(
            enabled=enabled,
            bot_token=token,
            chat_id=chat_id,
            min_severity=min_severity,
        )


class TelegramNotifier:
    def __init__(self, config: TelegramNotificationConfig):
        self.config = config
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=128)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._sent_lock = threading.Lock()
        self._sent_alert_ids: set[str] = set()

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None,
        env: Mapping[str, str] | None = None,
    ) -> "TelegramNotifier":
        return cls(TelegramNotificationConfig.from_settings(settings, env))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "ready": self.config.ready,
            "running": bool(self._thread and self._thread.is_alive()),
            "min_severity": self.config.min_severity,
        }

    def start(self) -> None:
        if not self.config.ready:
            print("[Telegram] Disabled or not configured.")
            return
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        print("[Telegram] Notification worker started.")

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def should_notify(self, alert: Mapping[str, Any]) -> bool:
        if not self.config.ready:
            return False

        severity = _normalize_severity(alert.get("severity"), default="high")
        return SEVERITY_ORDER[severity] >= SEVERITY_ORDER[self.config.min_severity]

    def enqueue_alert(self, alert: Mapping[str, Any], snapshot_jpeg: bytes | None = None) -> bool:
        if not self.should_notify(alert):
            return False

        alert_id = _coerce_str(alert.get("id"))
        if not alert_id:
            return False

        with self._sent_lock:
            if alert_id in self._sent_alert_ids:
                return False

        payload = {
            "kind": "alert",
            "alert": dict(alert),
            "snapshot_jpeg": snapshot_jpeg,
        }

        try:
            self._queue.put_nowait(payload)
            return True
        except queue.Full:
            print(f"[Telegram] Queue full, dropping alert {alert_id}.")
            return False

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if item is None:
                break

            if item.get("kind") == "alert":
                self._deliver_alert(item["alert"], item.get("snapshot_jpeg"))

    def _deliver_alert(self, alert: Mapping[str, Any], snapshot_jpeg: bytes | None) -> bool:
        alert_id = _coerce_str(alert.get("id"))
        if not alert_id:
            return False

        caption = self._format_caption(alert)
        last_error: Exception | None = None

        for attempt in range(1, self.config.retries + 1):
            try:
                if snapshot_jpeg:
                    try:
                        self._send_photo(snapshot_jpeg, caption)
                    except Exception as photo_error:
                        last_error = photo_error
                        print(
                            f"[Telegram] Photo send failed for {alert_id}: {photo_error}. "
                            "Falling back to text message."
                        )
                        self._send_message(caption)
                else:
                    self._send_message(caption)

                with self._sent_lock:
                    self._sent_alert_ids.add(alert_id)

                print(f"[Telegram] Alert sent: {alert_id}")
                return True
            except Exception as exc:
                last_error = exc
                if attempt < self.config.retries:
                    time.sleep(self.config.retry_delay_seconds)

        print(f"[Telegram] Failed to send {alert_id}: {last_error}")
        return False

    def _format_caption(self, alert: Mapping[str, Any]) -> str:
        lines = [
            "AI Sentinel Alert",
            f"Type: {_coerce_str(alert.get('type'), 'Incident')}",
            f"Severity: {_coerce_str(alert.get('severity'), 'high').upper()}",
            f"Camera: {_coerce_str(alert.get('cameraId'), 'unknown')}",
            f"Confidence: {_coerce_str(alert.get('confidence'), '0')}%",
            f"Time: {_coerce_str(alert.get('timestamp'), '--:--:-- UTC')}",
            f"Alert ID: {_coerce_str(alert.get('id'))}",
        ]

        location = _coerce_str(alert.get("location"))
        if location:
            lines.append(f"Location: {location}")

        return "\n".join(lines)

    def _request_json(self, method: str, fields: Mapping[str, Any]) -> dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.config.bot_token}/{method}"
        data = parse.urlencode({k: str(v) for k, v in fields.items()}).encode("utf-8")
        req = request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        )

        try:
            with request.urlopen(req, timeout=self.config.request_timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            raise RuntimeError(f"Telegram request failed: {exc}") from exc

        if not body.get("ok"):
            raise RuntimeError(body.get("description", "Telegram API returned an error"))

        return body["result"]

    def _request_multipart(
        self,
        method: str,
        fields: Mapping[str, Any],
        files: Mapping[str, tuple[str, bytes, str]],
    ) -> dict[str, Any]:
        boundary = f"----AI-Sentinel-{uuid.uuid4().hex}"
        chunks: list[bytes] = []

        for name, value in fields.items():
            chunks.append(f"--{boundary}\r\n".encode("utf-8"))
            chunks.append(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
            )
            chunks.append(str(value).encode("utf-8"))
            chunks.append(b"\r\n")

        for name, (filename, content, content_type) in files.items():
            chunks.append(f"--{boundary}\r\n".encode("utf-8"))
            chunks.append(
                (
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode("utf-8")
            )
            chunks.append(content)
            chunks.append(b"\r\n")

        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

        req = request.Request(
            f"https://api.telegram.org/bot{self.config.bot_token}/{method}",
            data=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

        try:
            with request.urlopen(req, timeout=self.config.request_timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            raise RuntimeError(f"Telegram request failed: {exc}") from exc

        if not body.get("ok"):
            raise RuntimeError(body.get("description", "Telegram API returned an error"))

        return body["result"]

    def _send_message(self, text: str) -> dict[str, Any]:
        return self._request_json(
            "sendMessage",
            {
                "chat_id": self.config.chat_id,
                "text": text,
                "disable_notification": "false",
            },
        )

    def _send_photo(self, photo_bytes: bytes, caption: str) -> dict[str, Any]:
        return self._request_multipart(
            "sendPhoto",
            {
                "chat_id": self.config.chat_id,
                "caption": caption,
                "disable_notification": "false",
            },
            {"photo": ("alert.jpg", photo_bytes, "image/jpeg")},
        )
