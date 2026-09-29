"""Tracking/counting evaluation harness (S-04 / WT-22).

Implements the metrics the campaign requires for the tracking slice:

* **HOTA** (Luiten et al., arXiv:2009.07736) — DetA / AssA / LocA integrated
  over IoU thresholds, TrackEval-compatible definition (association accuracy is
  localisation-weighted).
* **IDF1** (Ristani et al.) — global identity F1 via sequence-level identity
  matching at the standard ID threshold 0.5.
* **Counting metrics** — per-frame count error against ground truth with
  explicit slices (normal / occlusion / exit / re-entry) and track-switch
  counts, always reported with sample counts and denominators.

Input format (fixture JSON, one sequence per file):

```
{
  "name": "crossing",
  "fps": 30.0,
  "frames": [
    {"index": 0, "slice": "normal",
     "gt":   [[gt_id, x1, y1, x2, y2], ...],
     "detections": [[x1, y1, x2, y2, score], ...]}
  ]
}
```

The harness runs a tracker over ``detections`` and compares its output tracks
with ``gt`` — the tracker never sees the ground truth. MOTA alone is not used
anywhere: it is inadequate for identity-critical counting, as the campaign
brief states.

WT-12 fixtures are not yet available on any branch; running this harness against
real fixtures is blocked on them. Until then the harness is exercised on
generated labelled sequences (``--synth``), which are deterministic.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from tracking import create_tracker, iou_matrix

TRACKER_NAMES = ("bytetrack", "ocsort", "iou_legacy")
HOTA_ALPHAS = tuple(round(0.05 + 0.05 * index, 2) for index in range(19))  # 0.05..0.95


def _box_iou_matrix(gt: np.ndarray, pred: np.ndarray) -> np.ndarray:
    if len(gt) == 0 or len(pred) == 0:
        return np.zeros((len(gt), len(pred)), dtype=np.float64)
    g = gt.reshape(-1, 4).astype(np.float64)
    p = pred.reshape(-1, 4).astype(np.float64)
    ix1 = np.maximum(g[:, None, 0], p[None, :, 0])
    iy1 = np.maximum(g[:, None, 1], p[None, :, 1])
    ix2 = np.minimum(g[:, None, 2], p[None, :, 2])
    iy2 = np.minimum(g[:, None, 3], p[None, :, 3])
    inter = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
    area_g = np.clip(g[:, 2] - g[:, 0], 0, None) * np.clip(g[:, 3] - g[:, 1], 0, None)
    area_p = np.clip(p[:, 2] - p[:, 0], 0, None) * np.clip(p[:, 3] - p[:, 1], 0, None)
    union = area_g[:, None] + area_p[None, :] - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(union > 0, inter / union, 0.0)
    return np.nan_to_num(out, nan=0.0)


def _frame_match(gt_boxes: np.ndarray, pred_boxes: np.ndarray, alpha: float) -> list[tuple[int, int]]:
    """Per-frame matching maximising TP at IoU >= alpha (HOTA convention)."""
    if len(gt_boxes) == 0 or len(pred_boxes) == 0:
        return []
    ious = _box_iou_matrix(gt_boxes, pred_boxes)
    cost = np.where(ious >= alpha, 1.0 - ious, 1.0)
    rows, cols = linear_sum_assignment(cost)
    return [(int(row), int(col)) for row, col in zip(rows, cols) if ious[row, col] >= alpha]


def load_fixture(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if "frames" not in payload:
        raise ValueError(f"fixture {path} has no frames")
    return payload


# ---------------------------------------------------------------------------
# No-GT tracking health (WT-12 fixture outputs)
#
# The WT-12 suite carries action labels only — identity ground truth is absent,
# so HOTA/IDF1/count-accuracy are UNMEASURABLE there (unavailable by annotation
# type). What CAN be measured from a run's `tracks[]` rows is tracking HEALTH:
# geometry-and-time signals that need no ground truth. They are reported as
# health signals and must never be presented as tracking accuracy.
#
# Fixed thresholds (declared BEFORE inspecting any run, per WT-12 discipline;
# recorded in every report so a reader can see they were not tuned):
#   DROPOUT_GAP_SECONDS  = 0.5   a track missing longer than this has dropped out
#   REENTRY_GAP_SECONDS  = 2.0   a track returning after this counts as re-entry
#   MERGE_IOU            = 0.8   two tracks this overlapped are merge suspects
#   AREA_JUMP_RATIO      = 1.8   box area change this large is a scale suspicion
# ---------------------------------------------------------------------------
HEALTH_SCHEMA = "wt12-tracking-health/1"
DROPOUT_GAP_SECONDS = 0.5
REENTRY_GAP_SECONDS = 2.0
MERGE_IOU = 0.8
AREA_JUMP_RATIO = 1.8
HEALTH_LABEL = ("no-GT tracking health (id churn, dropout/recovery, merge/split suspicion) — "
                "health signals, never tracking accuracy")
UNAVAILABLE_METRICS = {
    "HOTA": "unavailable: no identity ground truth in the suite (annotation type, not downloads)",
    "IDF1": "unavailable: no identity ground truth in the suite (annotation type, not downloads)",
    "count_accuracy": "unavailable: no per-frame person-count ground truth in the suite",
    "time_to_detection": "unavailable: no independently labeled onset in the suite",
}


def load_run_outputs(path: str | Path) -> dict[str, Any]:
    """Load one fixture output file and reject anything the health pass cannot trust."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [key for key in ("fixture_id", "source_sha256", "run_id", "source_mode", "tracks")
               if key not in payload]
    if missing:
        raise ValueError(f"{path}: missing required output keys {missing}")
    if payload["source_mode"] != "file-media":
        raise ValueError(f"{path}: refusing source_mode {payload['source_mode']!r} — "
                         "tracking health is reported for file-media runs only")
    if not str(payload.get("source_sha256") or ""):
        raise ValueError(f"{path}: source_sha256 is required (no unverifiable runs)")
    for index, row in enumerate(payload.get("tracks") or []):
        if not isinstance(row, dict) or "track_id" not in row or "bbox" not in row or "time_s" not in row:
            raise ValueError(f"{path}: malformed track row {index}")
        if not isinstance(row["track_id"], int) or len(row["bbox"]) != 4:
            raise ValueError(f"{path}: malformed track row {index}")
    payload["_path"] = str(path)
    return payload


def tracking_health(outputs: dict[str, Any]) -> dict[str, Any]:
    """Per-fixture tracking-health metrics computed from `tracks[]` alone."""
    rows = sorted(outputs.get("tracks") or [], key=lambda row: float(row["time_s"]))
    by_id: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_id.setdefault(int(row["track_id"]), []).append(row)
    timestamps = sorted({round(float(row["time_s"]), 6) for row in rows})
    per_time: dict[float, list[list[float]]] = {}
    for row in rows:
        per_time.setdefault(round(float(row["time_s"]), 6), []).append([float(value) for value in row["bbox"]])

    gap_events = 0
    reentry_events = 0
    area_jump_events = 0
    for track_rows in by_id.values():
        times = [round(float(row["time_s"]), 6) for row in track_rows]
        for previous, current in zip(times, times[1:]):
            delta = current - previous
            if delta > DROPOUT_GAP_SECONDS:
                gap_events += 1
                if delta > REENTRY_GAP_SECONDS:
                    reentry_events += 1
        for previous, current in zip(track_rows, track_rows[1:]):
            previous_area = _bbox_area(previous["bbox"])
            current_area = _bbox_area(current["bbox"])
            if previous_area > 0 and current_area > 0:
                ratio = max(current_area / previous_area, previous_area / current_area)
                if ratio >= AREA_JUMP_RATIO:
                    area_jump_events += 1

    merge_frames = 0
    for boxes in per_time.values():
        if len(boxes) < 2:
            continue
        overlaps = iou_matrix(np.asarray(boxes, dtype=np.float64), np.asarray(boxes, dtype=np.float64))
        for left in range(len(boxes)):
            for right in range(left + 1, len(boxes)):
                if overlaps[left, right] >= MERGE_IOU:
                    merge_frames += 1
                    break

    unique_ids = len(by_id)
    transient_ids = sum(1 for track_rows in by_id.values() if len(track_rows) == 1)
    counts = [len(boxes) for boxes in per_time.values()]
    duration = (timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else 0.0
    return {
        "fixture_id": outputs.get("fixture_id"),
        "run_id": outputs.get("run_id"),
        "source_sha256": outputs.get("source_sha256"),
        "output_path": outputs.get("_path"),
        "denominators": {
            "rows": len(rows),
            "unique_track_ids": unique_ids,
            "timestamps": len(timestamps),
            "windows": len(outputs.get("windows") or []),
            "duration_s": round(duration, 3),
        },
        "metrics": {
            "transient_id_rate": round(transient_ids / unique_ids, 6) if unique_ids else None,
            "dropout_events_per_track": round(gap_events / unique_ids, 6) if unique_ids else None,
            "reentry_events_per_track": round(reentry_events / unique_ids, 6) if unique_ids else None,
            "id_churn_proxy_per_track": round((reentry_events + transient_ids) / unique_ids, 6) if unique_ids else None,
            "merge_suspicion_frame_rate": round(merge_frames / len(timestamps), 6) if timestamps else None,
            "area_jump_events_per_track": round(area_jump_events / unique_ids, 6) if unique_ids else None,
            "active_track_count_min": min(counts) if counts else None,
            "active_track_count_median": float(np.median(counts)) if counts else None,
            "active_track_count_max": max(counts) if counts else None,
        },
        "thresholds": {"dropout_gap_s": DROPOUT_GAP_SECONDS, "reentry_gap_s": REENTRY_GAP_SECONDS,
                       "merge_iou": MERGE_IOU, "area_jump_ratio": AREA_JUMP_RATIO},
    }


def _bbox_area(bbox: Sequence[float]) -> float:
    x1, y1, x2, y2 = (float(value) for value in bbox[:4])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def tracking_health_report(paths: Sequence[str | Path], run_id: str | None = None,
                           seed: int = 20260929, bootstrap_resamples: int = 2000) -> dict[str, Any]:
    """Aggregate per-fixture health into the WT-12 report shape (slices + denominators).

    ``bootstrap_unit`` is the fixture (session): with fewer than three fixtures the
    interval is flagged as indicative only rather than presented as a tight bound.
    """
    fixtures = [tracking_health(load_run_outputs(path)) for path in paths]
    metrics = list(fixtures[0]["metrics"]) if fixtures else []
    slices: dict[str, Any] = {}
    for metric in metrics:
        values = [fixture["metrics"][metric] for fixture in fixtures if fixture["metrics"][metric] is not None]
        if not values:
            continue
        boot = _bootstrap_ci(values, seed=seed, resamples=bootstrap_resamples)
        slices[metric] = {
            "value": round(float(np.mean(values)), 6),
            "per_fixture": {fixture["fixture_id"]: fixture["metrics"][metric] for fixture in fixtures},
            "denominator": {"sessions": len(values),
                            "rows": sum(fixture["denominators"]["rows"] for fixture in fixtures),
                            "unique_track_ids": sum(fixture["denominators"]["unique_track_ids"] for fixture in fixtures),
                            "timestamps": sum(fixture["denominators"]["timestamps"] for fixture in fixtures)},
            "bootstrap_unit": "session",
            "bootstrap": boot,
            "bootstrap_is_indicative_only": len(values) < 3,
        }
    return {
        "schema": HEALTH_SCHEMA,
        "run_id": run_id or (fixtures[0]["run_id"] if fixtures else None),
        "source_mode": "file-media",
        "labels": HEALTH_LABEL,
        "thresholds": {"dropout_gap_s": DROPOUT_GAP_SECONDS, "reentry_gap_s": REENTRY_GAP_SECONDS,
                       "merge_iou": MERGE_IOU, "area_jump_ratio": AREA_JUMP_RATIO},
        "fixtures": fixtures,
        "slices": slices,
        "unavailable_metrics": dict(UNAVAILABLE_METRICS),
        "limitations": [
            "health signals are computed from predicted tracks only; they are not accuracy",
            "id churn is a proxy derived from gaps and single-observation ids, not a measured switch count",
            "thresholds were fixed before inspection and are recorded above",
        ],
    }


def _bootstrap_ci(values: Sequence[float], seed: int, resamples: int = 2000) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0:
        return {"low": 0.0, "high": 0.0}
    draws = rng.choice(array, size=(max(1, int(resamples)), array.size), replace=True).mean(axis=1)
    return {"low": round(float(np.percentile(draws, 2.5)), 6),
            "high": round(float(np.percentile(draws, 97.5)), 6)}


def health_cli_outputs_dir(directory: str | Path) -> list[str]:
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"outputs directory not found: {root}")
    return [str(path) for path in sorted(root.glob("*.json"))]


def run_tracker(fixture: dict[str, Any], tracker_name: str) -> tuple[list[dict[str, Any]], Any]:
    """Feed the fixture's detections through a tracker.

    Returns ``(per_frame_output, tracker)`` — the tracker instance is returned so
    callers read telemetry from the instance that actually ran the sequence.
    """
    tracker = create_tracker(tracker_name)
    outputs: list[dict[str, Any]] = []
    for frame in fixture["frames"]:
        detections = np.asarray(frame.get("detections", []), dtype=np.float64).reshape(-1, 5)
        tracks = tracker.update(detections)
        outputs.append({"index": int(frame["index"]), "slice": frame.get("slice", "normal"),
                        "gt": list(frame.get("gt", [])),
                        "tracks": [[track["track_id"], *track["bbox"]] for track in tracks]})
    return outputs, tracker


def hota(frames: Sequence[dict[str, Any]], alphas: Iterable[float] = HOTA_ALPHAS) -> dict[str, Any]:
    per_alpha: dict[str, dict[str, float]] = {}
    for alpha in alphas:
        tp = fp = fn = 0
        iou_sum = 0.0
        matches: dict[tuple[int, int], int] = {}
        match_iou: dict[tuple[int, int], float] = {}
        gt_count: dict[int, int] = {}
        pred_count: dict[int, int] = {}
        for frame in frames:
            gt_ids = [int(row[0]) for row in frame["gt"]]
            gt_boxes = np.asarray([row[1:5] for row in frame["gt"]], dtype=np.float64)
            pred_ids = [int(row[0]) for row in frame["tracks"]]
            pred_boxes = np.asarray([row[1:5] for row in frame["tracks"]], dtype=np.float64)
            for gt_id in gt_ids:
                gt_count[gt_id] = gt_count.get(gt_id, 0) + 1
            for pred_id in pred_ids:
                pred_count[pred_id] = pred_count.get(pred_id, 0) + 1
            pairs = _frame_match(gt_boxes, pred_boxes, alpha)
            ious = _box_iou_matrix(gt_boxes, pred_boxes)
            for row, col in pairs:
                key = (gt_ids[row], pred_ids[col])
                matches[key] = matches.get(key, 0) + 1
                match_iou[key] = match_iou.get(key, 0.0) + float(ious[row, col])
            tp += len(pairs)
            fn += len(gt_boxes) - len(pairs)
            fp += len(pred_boxes) - len(pairs)
            iou_sum += sum(float(ious[row, col]) for row, col in pairs)
        det_a = tp / (tp + fn + fp) if (tp + fn + fp) else 0.0
        ass_a = 0.0
        if tp:
            # AssA_alpha = (1/TP) * sum_c TP(c) * A(c), A(c) = matched_iou(c) / (gt(c)+pred(c)-TP(c))
            # (Luiten et al. 2020; localisation-weighted through matched_iou).
            for key, matched in matches.items():
                gt_total = gt_count[key[0]]
                pred_total = pred_count[key[1]]
                denominator = gt_total + pred_total - matched
                if denominator > 0:
                    ass_a += matched * match_iou[key] / denominator
            ass_a /= tp
        loc_a = (iou_sum / tp) if tp else 0.0
        hota_alpha = float(np.sqrt(det_a * ass_a)) if det_a > 0 and ass_a > 0 else 0.0
        per_alpha[f"{alpha:.2f}"] = {"DetA": round(det_a, 6), "AssA": round(ass_a, 6),
                                     "LocA": round(loc_a, 6), "HOTA": round(hota_alpha, 6),
                                     "TP": tp, "FN": fn, "FP": fp}
    values = [entry["HOTA"] for entry in per_alpha.values()]
    det = [entry["DetA"] for entry in per_alpha.values()]
    ass = [entry["AssA"] for entry in per_alpha.values()]
    loc = [entry["LocA"] for entry in per_alpha.values()]
    return {
        "HOTA": round(float(np.mean(values)), 6),
        "DetA": round(float(np.mean(det)), 6),
        "AssA": round(float(np.mean(ass)), 6),
        "LocA": round(float(np.mean(loc)), 6),
        "alphas": len(per_alpha),
        "per_alpha": per_alpha,
    }


def idf1(frames: Sequence[dict[str, Any]], threshold: float = 0.5) -> dict[str, Any]:
    matches: dict[tuple[int, int], int] = {}
    gt_total = pred_total = 0
    for frame in frames:
        gt_ids = [int(row[0]) for row in frame["gt"]]
        gt_boxes = np.asarray([row[1:5] for row in frame["gt"]], dtype=np.float64)
        pred_ids = [int(row[0]) for row in frame["tracks"]]
        pred_boxes = np.asarray([row[1:5] for row in frame["tracks"]], dtype=np.float64)
        gt_total += len(gt_ids)
        pred_total += len(pred_ids)
        for row, col in _frame_match(gt_boxes, pred_boxes, threshold):
            key = (gt_ids[row], pred_ids[col])
            matches[key] = matches.get(key, 0) + 1
    idtp = 0
    if matches:
        gt_ids = sorted({key[0] for key in matches})
        pred_ids = sorted({key[1] for key in matches})
        gt_count = {gt_id: sum(1 for frame in frames for row in frame["gt"] if int(row[0]) == gt_id)
                    for gt_id in gt_ids}
        pred_count = {pred_id: sum(1 for frame in frames for row in frame["tracks"] if int(row[0]) == pred_id)
                      for pred_id in pred_ids}
        cost = np.zeros((len(gt_ids), len(pred_ids)), dtype=np.float64)
        for row, gt_id in enumerate(gt_ids):
            for col, pred_id in enumerate(pred_ids):
                cost[row, col] = -(matches.get((gt_id, pred_id), 0) * 2
                                   - gt_count[gt_id] - pred_count[pred_id])
        rows, cols = linear_sum_assignment(cost)
        for row, col in zip(rows, cols):
            idtp += matches.get((gt_ids[row], pred_ids[col]), 0)
    idfn = gt_total - idtp
    idfp = pred_total - idtp
    idp = idtp / (idtp + idfp) if (idtp + idfp) else 0.0
    idr = idtp / (idtp + idfn) if (idtp + idfn) else 0.0
    value = (2 * idp * idr / (idp + idr)) if (idp + idr) else 0.0
    return {"IDF1": round(float(value), 6), "IDP": round(float(idp), 6), "IDR": round(float(idr), 6),
            "IDTP": idtp, "IDFN": idfn, "IDFP": idfp, "threshold": threshold,
            "gt_detections": gt_total, "pred_detections": pred_total}


def counting_metrics(frames: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Frame-level counting accuracy with slices and identity-continuity checks."""
    slice_values: dict[str, list[int]] = {}
    errors: list[int] = []
    missed = duplicate = 0
    switches = 0
    # gt id -> last matched pred id, to count identity switches over GT tracks.
    last_match: dict[int, int] = {}
    gt_presence: dict[int, int] = {}
    slices_seen: dict[str, int] = {}
    for frame in frames:
        gt_count = len(frame["gt"])
        pred_count = len(frame["tracks"])
        error = pred_count - gt_count
        errors.append(error)
        if error < 0:
            missed += 1
        elif error > 0:
            duplicate += 1
        label = str(frame.get("slice", "normal"))
        slice_values.setdefault(label, []).append(error)
        slices_seen[label] = slices_seen.get(label, 0) + 1
        for row in frame["gt"]:
            gt_presence[int(row[0])] = gt_presence.get(int(row[0]), 0) + 1
        gt_boxes = np.asarray([row[1:5] for row in frame["gt"]], dtype=np.float64)
        pred_boxes = np.asarray([row[1:5] for row in frame["tracks"]], dtype=np.float64)
        pred_ids = [int(row[0]) for row in frame["tracks"]]
        for row, col in _frame_match(gt_boxes, pred_boxes, 0.5):
            gt_id = int(frame["gt"][row][0])
            pred_id = pred_ids[col]
            if gt_id in last_match and last_match[gt_id] != pred_id:
                switches += 1
            last_match[gt_id] = pred_id
    total = len(errors)
    return {
        "frames": total,
        "count_mae": round(float(np.mean(np.abs(errors))) if total else 0.0, 6),
        "count_bias": round(float(np.mean(errors)) if total else 0.0, 6),
        "frames_undercounted": missed,
        "frames_overcounted": duplicate,
        "frames_exact": total - missed - duplicate,
        "track_switches": switches,
        "gt_tracks": len(gt_presence),
        "slices": {label: {"frames": slices_seen[label],
                           "count_mae": round(float(np.mean(np.abs(values))), 6),
                           "count_bias": round(float(np.mean(values)), 6)}
                   for label, values in slice_values.items()},
    }


def evaluate_fixture(path: str | Path, tracker_names: Sequence[str] = TRACKER_NAMES) -> dict[str, Any]:
    fixture = load_fixture(path)
    report: dict[str, Any] = {"fixture": str(path), "name": fixture.get("name"),
                              "frames": len(fixture["frames"]), "trackers": {}}
    for name in tracker_names:
        frames, tracker = run_tracker(fixture, name)
        report["trackers"][name] = {
            "HOTA": hota(frames),
            "IDF1": idf1(frames),
            "counting": counting_metrics(frames),
            "failure_flags": tracker.telemetry.snapshot(),
            "failure_events": list(tracker.telemetry.events),
        }
    return report


def evaluate_cli(fixture_dir: Optional[str], synth: bool, tracker_names: Sequence[str]) -> dict[str, Any]:
    paths: list[Path] = []
    if synth:
        paths = [Path(path) for path in write_synth_fixtures()]
    if fixture_dir:
        paths += sorted(Path(fixture_dir).glob("*.json"))
    return {"fixtures": [evaluate_fixture(path, tracker_names) for path in paths]}


# ---------------------------------------------------------------------------
# Deterministic labelled sequences (used until WT-12 fixtures land).
# ---------------------------------------------------------------------------

def _person(x: float, y: float, width: float = 24.0, height: float = 60.0) -> list[float]:
    return [x, y, x + width, y + height]


def synth_sequences() -> dict[str, dict[str, Any]]:
    sequences: dict[str, dict[str, Any]] = {}

    def blank(name: str) -> dict[str, Any]:
        return {"name": name, "fps": 10.0, "frames": []}

    # 1. Two people crossing: the classic identity-switch trap. They converge to
    #    (nearly) the same boxes mid-sequence, so a geometry-only tracker can
    #    swap identities there.
    crossing = blank("crossing")
    for index in range(30):
        progress = index / 29.0
        left_x = 20 + progress * 60.0
        right_x = 140 - progress * 60.0
        gt = [[1, *_person(left_x, 40)], [2, *_person(right_x, 44)]]
        detections = [[*_person(left_x, 40), 0.9], [*_person(right_x, 44), 0.9]]
        crossing["frames"].append({"index": index, "slice": "normal", "gt": gt, "detections": detections})
    sequences["crossing"] = crossing

    # 2. Occlusion: person 1 disappears for 6 frames, padded by crowding.
    occlusion = blank("occlusion")
    for index in range(30):
        gt = [[1, *_person(30 + index * 1.0, 40)], [2, *_person(120, 40)]]
        detections: list[list[float]] = []
        if not 10 <= index < 16:  # detection dropout = occlusion for the detector
            detections.append([*_person(30 + index * 1.0, 40), 0.85])
        detections.append([*_person(120, 40), 0.9])
        occlusion["frames"].append({
            "index": index,
            "slice": "occlusion" if 10 <= index < 16 else "normal",
            "gt": gt, "detections": detections,
        })
    sequences["occlusion"] = occlusion

    # 3. Exit and re-entry: person 2 leaves the scene and comes back later.
    reentry = blank("exit_reentry")
    for index in range(40):
        gt = [[1, *_person(20 + index * 0.5, 40)]]
        detections = [[*_person(20 + index * 0.5, 40), 0.9]]
        present = index < 12 or index >= 24
        if present:
            gt.append([2, *_person(150, 40)])
            detections.append([*_person(150, 40), 0.88])
        label = "exit" if 12 <= index < 24 else ("reentry" if index >= 24 else "normal")
        reentry["frames"].append({"index": index, "slice": label, "gt": gt, "detections": detections})
    sequences["exit_reentry"] = reentry

    # 4. Duplicated detections: one person reported twice (count inflation trap).
    duplicate = blank("duplicate_detections")
    for index in range(20):
        box = _person(40 + index * 0.5, 40)
        gt = [[1, *box]]
        detections = [[*box, 0.9], [box[0] + 2, box[1] + 2, box[2] + 2, box[3] + 2, 0.6]]
        duplicate["frames"].append({
            "index": index,
            "slice": "duplicate" if index >= 5 else "normal",
            "gt": gt, "detections": detections,
        })
    sequences["duplicate_detections"] = duplicate

    # 5. Missed person: a second person is only detected in half the frames.
    missed = blank("missed_person")
    for index in range(24):
        gt = [[1, *_person(20, 40)], [2, *_person(90, 40)]]
        detections = [[*_person(20, 40), 0.9]]
        if index % 2 == 0:
            detections.append([*_person(90, 40), 0.5])
        missed["frames"].append({
            "index": index,
            "slice": "low_recall" if index % 2 else "normal",
            "gt": gt, "detections": detections,
        })
    sequences["missed_person"] = missed
    # 6. Fast motion: 26 px/frame on a 40 px-wide box keeps IoU in the
    #    association floor region, which is where the drift suspicion fires.
    fast = blank("fast_motion")
    for index in range(16):
        box = _person(10 + index * 26.0, 20, width=40.0, height=80.0)
        fast["frames"].append({
            "index": index, "slice": "fast_motion",
            "gt": [[1, *box]], "detections": [[*box, 0.9]],
        })
    sequences["fast_motion"] = fast
    return sequences


def write_synth_fixtures(directory: Optional[str | Path] = None) -> list[str]:
    target = Path(directory) if directory is not None else Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "tracking"
    target.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, payload in synth_sequences().items():
        path = target / f"{name}.json"
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        written.append(str(path))
    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Tracking/counting evaluation (HOTA + IDF1 + counting)")
    parser.add_argument("--fixtures", help="directory of fixture JSON files (e.g. WT-12 fixtures)")
    parser.add_argument("--synth", action="store_true", help="run the generated labelled sequences")
    parser.add_argument("--write-synth", action="store_true", help="write generated sequences to tests/fixtures/tracking")
    parser.add_argument("--trackers", default=",".join(TRACKER_NAMES))
    parser.add_argument("--json", help="optional path to write the full report")
    parser.add_argument("--outputs-dir", help="WT-12 run outputs dir (bench/results/<run-id>/outputs) for no-GT tracking health")
    parser.add_argument("--health-report", help="optional path to write the no-GT tracking-health report (WT-12 shape)")
    args = parser.parse_args(argv)
    tracker_names = [name.strip() for name in args.trackers.split(",") if name.strip()]
    if args.write_synth:
        for path in write_synth_fixtures():
            print(f"wrote {path}")
    if args.health_report:
        if not args.outputs_dir:
            parser.error("--health-report requires --outputs-dir")
        outputs = health_cli_outputs_dir(args.outputs_dir)
        health = tracking_health_report(outputs)
        Path(args.health_report).write_text(json.dumps(health, indent=2), encoding="utf-8")
        print(f"\n== no-GT tracking health ({len(outputs)} fixture outputs) ==")
        for metric, entry in health["slices"].items():
            print(f"  {metric:32s} {entry['value']:.4f} "
                  f"[{entry['bootstrap']['low']:.4f}, {entry['bootstrap']['high']:.4f}] "
                  f"sessions={entry['denominator']['sessions']} rows={entry['denominator']['rows']}")
        for metric, reason in health["unavailable_metrics"].items():
            print(f"  {metric:32s} UNAVAILABLE — {reason}")
        print(f"health report written to {args.health_report}")
    report = evaluate_cli(args.fixtures, args.synth or args.write_synth, tracker_names)
    for fixture in report["fixtures"]:
        print(f"\n== {fixture['name']} ({fixture['frames']} frames) ==")
        for name, metrics in fixture["trackers"].items():
            print(f"  {name:10s} HOTA={metrics['HOTA']['HOTA']:.4f} DetA={metrics['HOTA']['DetA']:.4f} "
                  f"AssA={metrics['HOTA']['AssA']:.4f} IDF1={metrics['IDF1']['IDF1']:.4f} "
                  f"countMAE={metrics['counting']['count_mae']:.3f} switches={metrics['counting']['track_switches']} "
                  f"flags={metrics['failure_flags']}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nreport written to {args.json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
