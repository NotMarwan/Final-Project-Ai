"""Operating-point summaries for the weapon path (WT-07 §5.3).

Consumes `weapon-fp-log/1` rows produced on a KNOWN-BENIGN source, where
every logged detection is a false positive by construction, and reports the
operator-facing framing: false alerts per clip/frame with explicit
denominators, per-class and per-group breakdowns, and score distributions.

This module never fabricates ground truth: rows carry their own split and
source hash (WT-12 manifest), and only "unregistered" auxiliary media may be
summarized as an auxiliary-domain figure — never as a gate result.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize_negative_run(rows: Iterable[Mapping[str, Any]], *, alert_threshold: float) -> dict[str, Any]:
    """False-positive summary for a known-benign run at a fixed alert point.

    `alert_threshold` is supplied by the caller (SC-5 policy / explicit CLI
    input) so this module holds no operating values of its own.
    """
    rows = list(rows)
    per_class: dict[str, dict[str, Any]] = {}
    per_group: dict[str, dict[str, Any]] = {}
    clips: set[str] = set()
    frames: set[tuple[str, int]] = set()
    alert_frames: set[tuple[str, int]] = set()
    splits: set[str] = set()
    for row in rows:
        clips.add(str(row["clip_id"]))
        frames.add((str(row["clip_id"]), int(row["frame_index"])))
        splits.add(str(row.get("split", "unregistered")))
        if float(row["score"]) >= alert_threshold:
            alert_frames.add((str(row["clip_id"]), int(row["frame_index"])))
        for bucket, key in ((per_class, str(row["class"])), (per_group, str(row["group"]))):
            entry = bucket.setdefault(key, {"detections": 0, "at_or_above_alert": 0, "scores": []})
            entry["detections"] += 1
            entry["scores"].append(float(row["score"]))
            if float(row["score"]) >= alert_threshold:
                entry["at_or_above_alert"] += 1
    for bucket in (per_class, per_group):
        for entry in bucket.values():
            entry["max_score"] = max(entry["scores"]) if entry["scores"] else None
            entry["p95_score"] = _percentile(entry["scores"], 0.95)
            del entry["scores"]
    return {
        "schema_version": "weapon-negative-run-summary/1",
        "alert_threshold": float(alert_threshold),
        "denominators": {
            "clips": len(clips),
            "frames_with_detections": len(frames),
            "detections_logged": len(rows),
        },
        "false_alert_frames": len(alert_frames),
        "detections_at_or_above_alert": sum(
            1 for row in rows if float(row["score"]) >= alert_threshold),
        "per_class": per_class,
        "per_group": per_group,
        "splits": sorted(splits),
        "interpretation": (
            "Detections on a known-benign source are false positives by "
            "construction. Split provenance decides whether this figure may "
            "enter a gate claim; 'unregistered' rows are auxiliary-domain only."
        ),
    }
