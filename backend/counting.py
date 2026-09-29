"""Canonical person-counting semantics for Sentinel (S-04 / WT-22).

Three distinct quantities, never conflated (they were previously all implied by
the single ``person_count`` key):

``visible_person_count``
    Number of person *detections* accepted in the current processed frame,
    before any tracking filter. Answers "how many people are visible right now".

``active_track_count``
    Number of confirmed tracks matched in the current processed frame — the
    documented replacement for the old ``person_count = len(tracks)``.
    Answers "how many tracked people are being followed right now".

``unique_person_estimate_window``
    Number of distinct track identities observed in a trailing time window,
    with an explicit period and an uncertainty band expressed only as a
    >= / +/- style interval. Answers "how many different people have been here".
    The band counts the tracker's own failure-suspicion *events* that fall
    inside the same window (id-switch / re-entry / merge-split / dropout);
    it is a suspicion band, NOT a calibrated confidence interval, and is
    labelled as such in every payload.

Counting never claims identity: the window estimate counts identities the
tracker *believes* it observed, and reports the suspicion band alongside.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

DEFAULT_WINDOW_SECONDS = 60.0
BAND_SOURCE_FLAGS = ("id_switch", "re_entry", "merge_split", "dropout")

# Wire (JSON) key names are camelCase everywhere the UI reads them; the internal
# result dict stays snake_case. One mapper keeps that translation in one place.
_WIRE_KEY_MAP = {
    "window_seconds": "windowSeconds",
    "unique_track_ids": "uniqueTrackIds",
    "band_label": "bandLabel",
    "band_abs": "bandAbs",
    "estimate_lower": "estimateLower",
    "estimate_upper": "estimateUpper",
    "band_source": "bandSource",
    "band_is_calibrated": "bandIsCalibrated",
    "window_flags": "windowFlags",
}


def estimate_window_to_wire(window: Any) -> Optional[dict[str, Any]]:
    """Translate the internal estimate window into the camelCase wire form."""
    if not isinstance(window, Mapping):
        return None
    return {_WIRE_KEY_MAP.get(key, key): value for key, value in window.items()}


class CountingSemantics:
    """Trailing-window identity accounting with an explicit suspicion band."""

    def __init__(self, window_seconds: float = DEFAULT_WINDOW_SECONDS,
                 clock: Optional[Callable[[], float]] = None):
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.window_seconds = float(window_seconds)
        self._clock = clock or time.monotonic
        self._last_seen: dict[str, float] = {}
        self._flag_events: deque[tuple[float, str]] = deque(maxlen=4096)
        self._last_snapshot: dict[str, Any] = {}
        self._updates = 0

    def note_failure_events(self, timestamp: float, deltas: Mapping[str, int]) -> int:
        """Append suspicion events (counts since the previous tracker read)."""
        recorded = 0
        for name in BAND_SOURCE_FLAGS:
            count = int(deltas.get(name, 0) or 0)
            if count <= 0:
                continue
            for _ in range(min(count, 512)):
                self._flag_events.append((float(timestamp), name))
            recorded += count
        return recorded

    def observe(self, timestamp: float, visible_person_count: int,
                track_refs: Sequence[str],
                failure_deltas: Optional[Mapping[str, int]] = None) -> dict[str, Any]:
        """Fold one processed frame into the window and return the counting block."""
        timestamp = float(timestamp)
        if failure_deltas:
            self.note_failure_events(timestamp, failure_deltas)
        for ref in track_refs:
            self._last_seen[str(ref)] = timestamp
        self._prune(timestamp)
        window_flags = self._window_flag_counts()
        unique_tracks = len(self._last_seen)
        suspicion = sum(window_flags.values())
        self._last_snapshot = {
            "visible_person_count": int(max(0, visible_person_count)),
            "active_track_count": int(len(track_refs)),
            "unique_person_estimate_window": {
                "window_seconds": self.window_seconds,
                "unique_track_ids": int(unique_tracks),
                "estimate": int(unique_tracks),
                "band_label": f"\u00b1{suspicion}",
                "band_abs": int(suspicion),
                "estimate_lower": int(max(0, unique_tracks - suspicion)),
                "estimate_upper": int(unique_tracks + suspicion),
                "band_source": "tracker_failure_suspicion_events_in_window",
                "band_is_calibrated": False,
                "definition": (
                    "distinct confirmed track identities observed in the trailing "
                    f"{self.window_seconds:.0f}s window; band counts id_switch/re_entry/"
                    "merge_split/dropout suspicion events recorded in the same window "
                    "(heuristic geometry-derived counters, uncalibrated)"
                ),
                "window_flags": dict(window_flags),
            },
        }
        self._updates += 1
        return self._last_snapshot

    def last_snapshot(self) -> dict[str, Any]:
        return {**self._last_snapshot}

    def reset(self) -> None:
        self._last_seen.clear()
        self._flag_events.clear()
        self._last_snapshot = {}
        self._updates = 0

    # -- internals ---------------------------------------------------------
    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        for key in [key for key, seen in self._last_seen.items() if seen < cutoff]:
            self._last_seen.pop(key, None)
        while self._flag_events and self._flag_events[0][0] < cutoff:
            self._flag_events.popleft()

    def _window_flag_counts(self) -> dict[str, int]:
        counts = {name: 0 for name in BAND_SOURCE_FLAGS}
        for _timestamp, name in self._flag_events:
            counts[name] = counts.get(name, 0) + 1
        return counts
