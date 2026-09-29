"""Incident triage state machine (WT-25).

An operator workflow for a received alert: acknowledge it, hold it, resume it
and close it, recording the acting role and a timestamp for every transition
(research WT-11 T25-1; vendor lifecycles: Milestone New -> In progress ->
On hold -> Closed, Avigilon Active / Acknowledged / Assigned).

The helpers are pure functions in their own module rather than in ``api.py`` so
the transitions stay unit-testable without importing the API module (the
committed API layer cannot be imported at the baseline, see B-1 / SC-10).

State is process-scoped: it lives in the in-memory alert registry
(``AppState.update_alert``) and is broadcast to connected clients. It is not
written to the evidence ledger, so a backend restart loses it; the UI says so.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

TRIAGE_STATES = ("new", "in_progress", "on_hold", "resolved")
TRIAGE_ACTIONS = ("acknowledge", "hold", "resume", "resolve", "reopen")

#: Allowed transitions per state. Acknowledging is the ``new -> in_progress``
#: transition; the action verb is kept in the record so the acknowledgement
#: itself remains visible in the activity log.
TRIAGE_ALLOWED: dict[str, tuple[str, ...]] = {
    "new": ("acknowledge", "resolve"),
    "in_progress": ("hold", "resolve"),
    "on_hold": ("resume", "resolve"),
    "resolved": ("reopen",),
}

_TRIAGE_NEXT: dict[tuple[str, str], str] = {
    ("new", "acknowledge"): "in_progress",
    ("new", "resolve"): "resolved",
    ("in_progress", "hold"): "on_hold",
    ("in_progress", "resolve"): "resolved",
    ("on_hold", "resume"): "in_progress",
    ("on_hold", "resolve"): "resolved",
    ("resolved", "reopen"): "in_progress",
}

MAX_ACTOR_CHARS = 64
MAX_HISTORY_ENTRIES = 20
UNKNOWN_ACTOR = "unknown"


def normalize_actor(value: Any) -> str:
    """Actor identity: the role reported by the security controller, never a
    client-supplied string (no per-user identity exists at this revision)."""
    if isinstance(value, str):
        actor = value.strip()[:MAX_ACTOR_CHARS]
        if actor:
            return actor
    return UNKNOWN_ACTOR


def reduce_triage(state: str, action: str) -> Optional[str]:
    """Return the next state, or ``None`` when the transition is not allowed."""
    return _TRIAGE_NEXT.get((state, action))


def build_record(
    state: str,
    action: str,
    actor: Any,
    at: Optional[str] = None,
    previous: Optional[Mapping[str, Any]] = None,
) -> dict:
    """Builds the triage record stored on the alert and returned by the API."""
    timestamp = at or datetime.now(timezone.utc).isoformat()
    history: list[dict] = []
    if isinstance(previous, Mapping):
        raw_history = previous.get("history")
        if isinstance(raw_history, list):
            history = [entry for entry in raw_history if isinstance(entry, dict)][-MAX_HISTORY_ENTRIES:]
    history.append({"action": action, "actor": normalize_actor(actor), "at": timestamp})
    return {
        "state": state,
        "action": action,
        "actor": normalize_actor(actor),
        "at": timestamp,
        "history": history[-MAX_HISTORY_ENTRIES:],
    }


def normalize_record(raw: Any) -> Optional[dict]:
    """Validates a record read back from the alert registry.

    The PUT path would otherwise accept any stored value; this keeps the read
    path fail-closed against a corrupted or stale registry entry.
    """
    if not isinstance(raw, Mapping):
        return None
    state = raw.get("state")
    action = raw.get("action")
    if state not in TRIAGE_STATES or action not in TRIAGE_ACTIONS:
        return None
    at = raw.get("at")
    if not isinstance(at, str) or not at:
        return None
    history = raw.get("history")
    return {
        "state": state,
        "action": action,
        "actor": normalize_actor(raw.get("actor")),
        "at": at,
        "history": [entry for entry in history if isinstance(entry, dict)][-MAX_HISTORY_ENTRIES:]
        if isinstance(history, list) else [],
    }


def apply_transition(existing: Any, action: str, actor: Any) -> tuple[Optional[dict], str]:
    """Applies ``action`` to the stored record.

    Returns ``(record, "ok")`` on success or ``(None, reason)`` with one of
    ``invalid_action`` / ``invalid_state`` / ``conflict``.
    """
    if action not in TRIAGE_ACTIONS:
        return None, "invalid_action"
    previous = normalize_record(existing) if existing is not None else None
    state = previous["state"] if previous else "new"
    if state not in TRIAGE_STATES:
        return None, "invalid_state"
    next_state = reduce_triage(state, action)
    if next_state is None:
        return None, "conflict"
    return build_record(next_state, action, actor, previous=previous), "ok"
