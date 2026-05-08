from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping
from urllib import error, parse, request

_logger = logging.getLogger(__name__)

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
    min_alert_interval_seconds: float = 60.0
    send_test_on_startup: bool = False
    retries: int = 3
    retry_delay_seconds: float = 1.5

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.bot_token and self.chat_id)

    @property
    def token_configured(self) -> str:
        """Return 'configured' if both token and chat_id are present, 'missing' otherwise."""
        return "configured" if (self.bot_token and self.chat_id) else "missing"

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

        # Prioritize environment variables over config.yml for ALL fields
        token = _coerce_str(env.get("TELEGRAM_BOT_TOKEN", "")) or _coerce_str(
            telegram_settings.get("bot_token", "")
        )
        chat_id = _coerce_str(env.get("TELEGRAM_CHAT_ID", "")) or _coerce_str(
            telegram_settings.get("chat_id", "")
        )

        # If TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID are missing, set enabled = false
        token_present = bool(token)
        chat_id_present = bool(chat_id)
        if not (token_present and chat_id_present):
            enabled = False
        else:
            enabled_env = env.get("TELEGRAM_ENABLED")
            if enabled_env is None:
                enabled = _coerce_bool(
                    telegram_settings.get("enabled"),
                    default=True,
                )
            else:
                enabled = _coerce_bool(enabled_env, default=False)

        min_severity = _normalize_severity(
            env.get("TELEGRAM_MIN_SEVERITY")
            or telegram_settings.get("min_severity"),
            default="high",
        )

        timeout_str = env.get("TELEGRAM_TIMEOUT_SECONDS")
        if timeout_str is not None:
            try:
                request_timeout = float(timeout_str)
            except (ValueError, TypeError):
                request_timeout = 8.0
        else:
            request_timeout = float(telegram_settings.get("request_timeout", 8.0))

        interval_str = env.get("TELEGRAM_MIN_ALERT_INTERVAL_SECONDS")
        if interval_str is not None:
            try:
                min_alert_interval_seconds = float(interval_str)
            except (ValueError, TypeError):
                min_alert_interval_seconds = 60.0
        else:
            min_alert_interval_seconds = float(telegram_settings.get("min_alert_interval_seconds", 60.0))

        send_test_env = env.get("TELEGRAM_SEND_TEST_ON_STARTUP")
        if send_test_env is not None:
            send_test_on_startup = _coerce_bool(send_test_env, default=False)
        else:
            send_test_on_startup = _coerce_bool(
                telegram_settings.get("send_test_on_startup"), default=False
            )

        return cls(
            enabled=enabled,
            bot_token=token,
            chat_id=chat_id,
            min_severity=min_severity,
            request_timeout=request_timeout,
            min_alert_interval_seconds=min_alert_interval_seconds,
            send_test_on_startup=send_test_on_startup,
        )


class TelegramNotifier:
    def __init__(self, config: TelegramNotificationConfig):
        self.config = config
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=128)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._sent_lock = threading.Lock()
        self._sent_alert_ids: set[str] = set()
        self._last_send_time: float = 0.0  # For cooldown tracking
        # Status tracking fields for Phase 6
        self._last_send_status: str | None = None
        self._last_error: str | None = None
        self._last_sent_at: str | None = None
        # Worker health monitoring
        self._worker_start_time: float = 0.0
        self._worker_restart_count: int = 0
        self._max_restarts: int = 5

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None,
        env: Mapping[str, str] | None = None,
    ) -> "TelegramNotifier":
        return cls(TelegramNotificationConfig.from_settings(settings, env))

    def status(self) -> dict[str, Any]:
        worker_alive = bool(self._thread and self._thread.is_alive())
        return {
            "enabled": self.config.enabled,
            "configured": self.config.token_configured == "configured",
            "lastSendStatus": self._last_send_status,
            "lastError": self._last_error,
            "lastSentAt": self._last_sent_at,
            "minAlertIntervalSeconds": self.config.min_alert_interval_seconds,
            "provider": "telegram",
            "running": worker_alive,
            "min_severity": self.config.min_severity,
            "workerRestartCount": self._worker_restart_count,
            "workerHealthy": worker_alive,
        }

    def start(self) -> None:
        if not self.config.ready:
            _logger.info("[Telegram] Disabled or not configured.")
            return
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_start_time = time.time()
        self._thread.start()
        _logger.info("[Telegram] Notification worker started.")

    def ensure_worker_alive(self) -> bool:
        """Check if worker is alive; restart if dead (within restart limits). Returns True if worker is alive after call."""
        if self._thread and self._thread.is_alive():
            return True
        if not self.config.ready:
            return False
        if self._worker_restart_count >= self._max_restarts:
            _logger.error(
                "[Telegram] Worker died and max restarts (%s) reached; not restarting.",
                self._max_restarts
            )
            return False
        _logger.warning("[Telegram] Worker thread died; attempting restart.")
        self._worker_restart_count += 1
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_start_time = time.time()
        self._thread.start()
        return True

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
            _logger.debug("[Telegram] Not ready, skipping notification")
            return False
        
        # Check for WATCH-only mode - do NOT send Telegram alerts
        alert_state = str(alert.get("alert_state", "")).upper()
        if alert_state == "WATCH":
            _logger.info("[Telegram] WATCH-only mode detected, skipping alert")
            return False
        
        # Check severity
        severity = _normalize_severity(alert.get("severity"), default="high")
        if SEVERITY_ORDER[severity] < SEVERITY_ORDER[self.config.min_severity]:
            _logger.debug(
                "[Telegram] Severity %s below threshold %s",
                severity, self.config.min_severity
            )
            return False
        
        # Check alert type and required fields
        alert_type = str(alert.get("type", "")).lower()
        threat_type = str(alert.get("threatType", "")).lower()
        
        # Violence alerts require confirmed_alert=True
        is_violence = "violence" in alert_type or "violence" in threat_type
        if is_violence:
            confirmed = alert.get("confirmed_alert")
            if isinstance(confirmed, str):
                confirmed = _coerce_bool(confirmed, default=False)
            if not confirmed:
                _logger.info("[Telegram] Violence alert without confirmed_alert=True, skipping")
                return False
        
        # Weapon alerts require weapon_alert=True (if field exists)
        is_weapon = "weapon" in alert_type or "weapon" in threat_type
        if is_weapon:
            weapon_alert = alert.get("weapon_alert")
            if weapon_alert is not None:
                if isinstance(weapon_alert, str):
                    weapon_alert = _coerce_bool(weapon_alert, default=False)
                if not weapon_alert:
                    _logger.info("[Telegram] Weapon alert without weapon_alert=True, skipping")
                    return False
        
        # Danger alerts require danger_alert=True (if field exists)
        is_danger = "danger" in alert_type or "danger" in threat_type
        if is_danger:
            danger_alert = alert.get("danger_alert")
            if danger_alert is not None:
                if isinstance(danger_alert, str):
                    danger_alert = _coerce_bool(danger_alert, default=False)
                if not danger_alert:
                    _logger.info("[Telegram] Danger alert without danger_alert=True, skipping")
                    return False
        
        return True

    def enqueue_alert(self, alert: Mapping[str, Any], snapshot_jpeg: bytes | None = None) -> bool:
        if not self.should_notify(alert):
            return False
        
        # Ensure worker is alive before enqueueing
        if not self.ensure_worker_alive():
            _logger.warning("[Telegram] Worker not available; dropping alert")
            return False
        
        # Check cooldown
        now = time.time()
        with self._sent_lock:
            if now - self._last_send_time < self.config.min_alert_interval_seconds:
                _logger.info("[Telegram] Cooldown active, skipping alert")
                self._last_send_status = "cooldown"
                return False
        
        alert_id = _coerce_str(alert.get("id"))
        if not alert_id:
            return False

        with self._sent_lock:
            if alert_id in self._sent_alert_ids:
                _logger.info("[Telegram] Duplicate alert %s, skipping", alert_id)
                return False
            # Update cooldown timer and mark as sent to prevent duplicates
            self._last_send_time = now
            self._sent_alert_ids.add(alert_id)

        payload = {
            "kind": "alert",
            "alert": dict(alert),
            "snapshot_jpeg": snapshot_jpeg,
        }

        try:
            self._queue.put_nowait(payload)
            return True
        except queue.Full:
            # Remove from sent set if we couldn't queue it
            with self._sent_lock:
                self._sent_alert_ids.discard(alert_id)
            _logger.warning("[Telegram] Queue full, dropping alert %s", alert_id)
            return False

    def send_test_message(self) -> dict[str, Any]:
        """Send a simple test message and return delivery status."""
        if not self.config.ready:
            self._last_send_status = "not_configured"
            return {
                "success": False,
                "error": "not_configured",
            }
        try:
            result = self._send_message("AI-Sentinel Telegram test message")
            # Update status tracking on success
            self._last_send_status = "success"
            self._last_error = None
            self._last_sent_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            return {
                "success": True,
                "telegram_result": result,
            }
        except Exception as exc:
            # Update status tracking on failure
            self._last_send_status = "failed"
            self._last_error = str(exc)
            return {
                "success": False,
                "error": str(exc),
            }

    def _worker(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    item = self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if item is None:
                    break

                if item.get("kind") == "alert":
                    self._deliver_alert(item["alert"], item.get("snapshot_jpeg"))
        except Exception as exc:
            _logger.error("[Telegram] Worker thread crashed: %s", exc)
            # Worker is now dead; status() will reflect this

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
                        _logger.warning(
                            "[Telegram] Photo send failed for %s: %s. "
                            "Falling back to text message.",
                            alert_id, photo_error
                        )
                        self._send_message(caption)
                else:
                    self._send_message(caption)

                _logger.info("[Telegram] Alert sent: %s", alert_id)
                # Update status tracking on success
                self._last_send_status = "success"
                self._last_error = None
                self._last_sent_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                return True
            except Exception as exc:
                last_error = exc
                # Don't retry on 400 Bad Request (invalid chat_id, bot blocked, etc.)
                error_str = str(exc)
                if "400" in error_str or "Bad Request" in error_str:
                    _logger.error(
                        "[Telegram] Not retrying %s due to client error: %s",
                        alert_id, exc
                    )
                    break
                if attempt < self.config.retries:
                    time.sleep(self.config.retry_delay_seconds)

        _logger.error("[Telegram] Failed to send %s: %s", alert_id, last_error)
        # Update status tracking on failure
        self._last_send_status = "failed"
        self._last_error = str(last_error) if last_error else "Unknown error"
        # Remove from sent set so it can be retried later if needed
        with self._sent_lock:
            self._sent_alert_ids.discard(alert_id)
        return False

    def _format_caption(self, alert: Mapping[str, Any]) -> str:
        lines = [
            "AI-Sentinel Alert",
            f"Type: {_coerce_str(alert.get('type'), 'Incident')}",
            f"Camera: {_coerce_str(alert.get('cameraId'), 'unknown')}",
            f"Time: {_coerce_str(alert.get('timestamp'), '--:--:-- UTC')}",
            f"Severity: {_coerce_str(alert.get('severity'), 'high').upper()}",
            f"Confidence: {_coerce_str(alert.get('confidence'), '0')}%",
            f"Alert State: {_coerce_str(alert.get('alert_state'), 'NORMAL')}",
            f"Confirmed: {_coerce_bool(alert.get('confirmed_alert'), default=False)}",
            f"Alert ID: {_coerce_str(alert.get('id'))}",
        ]

        location = _coerce_str(alert.get("location"))
        if location:
            lines.append(f"Location: {location}")

        return "\n".join(lines)

    def _request_json(self, method: str, fields: Mapping[str, Any]) -> dict[str, Any]:
        # Build URL without embedding token in error messages
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
            # Sanitize error: do NOT include URL (which contains token) in error message
            reason = getattr(exc, "reason", str(exc))
            if hasattr(exc, "url"):
                # URLError may contain the URL; strip it
                reason = str(reason).replace(self.config.bot_token, "***")
            raise RuntimeError(f"Telegram request failed: {reason}") from exc

        if not body.get("ok"):
            # Telegram API error description should not contain the token, but sanitize just in case
            description = body.get("description", "Telegram API returned an error")
            if self.config.bot_token in description:
                description = description.replace(self.config.bot_token, "***")
            raise RuntimeError(description)

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
            # Sanitize error: do NOT include URL (which contains token) in error message
            reason = getattr(exc, "reason", str(exc))
            if hasattr(exc, "url"):
                reason = str(reason).replace(self.config.bot_token, "***")
            raise RuntimeError(f"Telegram request failed: {reason}") from exc

        if not body.get("ok"):
            # Telegram API error description should not contain the token, but sanitize just in case
            description = body.get("description", "Telegram API returned an error")
            if self.config.bot_token in description:
                description = description.replace(self.config.bot_token, "***")
            raise RuntimeError(description)

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
