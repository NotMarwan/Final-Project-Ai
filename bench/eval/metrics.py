"""Metric computation for WT-12 evaluation protocol.

All functions are deterministic: sorted iteration everywhere, explicit tie-breaks,
bootstrap seeded from a caller-provided integer. Every metric carries its sample
count and denominators. Metrics whose preconditions are not met are returned as
None with an explicit reason, never as zero.
"""
from __future__ import annotations

import math
import random


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _percentile(sorted_values, q):
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * q
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def _round(value, digits=6):
    return None if value is None else round(float(value), digits)


def positive_intervals(labels, duration_s):
    """Labeled positive time intervals for one fixture.

    Frame-level intervals win when present. Clip-level labels (the common case for
    publisher annotations) yield one full-clip interval for positives and none for
    negatives; the coarser granularity is reported by the caller, not hidden here.
    """
    frames = labels.get("frames") or []
    intervals = []
    if frames:
        for row in frames:
            if row.get("label") == labels.get("class"):
                intervals.append((float(row["start_s"]), float(row["end_s"])))
        intervals.sort()
        merged = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged
    if labels.get("class") != "benign":
        return [(0.0, float(duration_s))]
    return []


def covered_seconds(intervals):
    return sum(end - start for start, end in intervals)


def label_at(intervals, t):
    return any(start <= t < end for start, end in intervals)


def window_label(window, intervals):
    """A window is positive iff >=50% of its span overlaps labeled positive time."""
    start, end = float(window["start_s"]), float(window["end_s"])
    span = end - start
    if span <= 0:
        raise ValueError("window span must be positive")
    overlap = 0.0
    for i_start, i_end in intervals:
        overlap += max(0.0, min(end, i_end) - max(start, i_start))
    return 1 if overlap / span >= 0.5 else 0


def confusion_at_threshold(items, threshold):
    """items: iterable of (score, label). Returns tp/fp/tn/fn counts."""
    tp = fp = tn = fn = 0
    for score, label in items:
        predicted = 1 if score >= threshold else 0
        if predicted and label:
            tp += 1
        elif predicted:
            fp += 1
        elif label:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "predicted_positive": tp + fp, "actual_positive": tp + fn,
            "predicted_negative": tn + fn, "actual_negative": tn + fp,
            "n": tp + fp + tn + fn}


def precision_recall(counts):
    return {
        "precision": _ratio(counts["tp"], counts["tp"] + counts["fp"]),
        "recall": _ratio(counts["tp"], counts["tp"] + counts["fn"]),
        "f1": _ratio(2 * counts["tp"], 2 * counts["tp"] + counts["fp"] + counts["fn"]),
    }


def average_precision(items):
    """All-point interpolated AP over (score, label) pairs; needs both classes."""
    labels = {label for _, label in items}
    if labels != {0, 1} or not items:
        return None
    ordered = sorted(items, key=lambda pair: (-pair[0], pair[1]))
    positives = sum(label for _, label in items)
    hits = 0
    previous_recall = 0.0
    ap = 0.0
    for index, (score, label) in enumerate(ordered, start=1):
        if not label:
            continue
        hits += 1
        recall = hits / positives
        precision = hits / index
        ap += (recall - previous_recall) * precision
        previous_recall = recall
    return ap


def frame_level_metrics(windows, intervals, duration_s, fps, threshold):
    """Frame-grid metrics from window scores.

    Each frame sample takes the score of the window with the greatest start_s
    covering it (latest completed window); frames without a covering window are
    unevaluated and excluded from every denominator.
    """
    frame_count = max(1, int(round(duration_s * fps)))
    period = 1.0 / fps
    ordered = sorted(windows, key=lambda w: (float(w["start_s"]), float(w["end_s"])))
    items = []
    unevaluated = 0
    for index in range(frame_count):
        t = index * period
        covering = [w for w in ordered if float(w["start_s"]) <= t < float(w["end_s"])]
        if not covering:
            unevaluated += 1
            continue
        window = max(covering, key=lambda w: (float(w["start_s"]), float(w["end_s"])))
        items.append((float(window["violence_conf"]), label_at(intervals, t)))
    counts = confusion_at_threshold(items, threshold)
    return {"level": "frame", "threshold": threshold, "fps": fps, "frame_period_s": period,
            "grid_frames": frame_count, "unevaluated_frames": unevaluated,
            **counts, **precision_recall(counts), "average_precision": _round(average_precision(items))}


def window_level_metrics(windows, intervals, threshold):
    items = [(float(w["violence_conf"]), window_label(w, intervals)) for w in windows]
    counts = confusion_at_threshold(items, threshold)
    return {"level": "window", "threshold": threshold, **counts,
            **precision_recall(counts), "average_precision": _round(average_precision(items))}


def build_events(labels, duration_s):
    """Ground-truth events for one fixture. onset_known gates time-to-detection."""
    intervals = positive_intervals(labels, duration_s)
    if not intervals:
        return []
    onset_known = labels.get("onset_s") is not None
    events = []
    for index, (start, end) in enumerate(intervals):
        onset = float(labels["onset_s"]) if onset_known else start
        events.append({"event_id": f"{index:04d}", "onset_s": onset, "offset_s": end,
                       "onset_known": onset_known})
    return events


def match_alerts_to_events(alerts, events, match_before_s, match_after_s):
    """Greedy earliest-alert matching; each alert and event matches at most once."""
    ordered_alerts = sorted(alerts, key=lambda a: (float(a["time_s"]), a["alert_id"]))
    used = set()
    matches = []
    for event in sorted(events, key=lambda e: (e["onset_s"], e["event_id"])):
        for alert in ordered_alerts:
            if alert["alert_id"] in used:
                continue
            time_s = float(alert["time_s"])
            if event["onset_s"] - match_before_s <= time_s <= event["offset_s"] + match_after_s:
                used.add(alert["alert_id"])
                matches.append({"event_id": event["event_id"], "alert_id": alert["alert_id"],
                                "alert_time_s": time_s, "onset_s": event["onset_s"],
                                "onset_known": event["onset_known"],
                                "time_to_detection_s": _round(time_s - event["onset_s"])
                                if event["onset_known"] else None})
                break
    unmatched_alerts = [a for a in ordered_alerts if a["alert_id"] not in used]
    return matches, unmatched_alerts


def event_level_metrics(per_fixture, match_before_s, match_after_s):
    """Event/alert metrics across fixtures.

    per_fixture: list of (fixture_dict, output_dict). False alerts per camera-hour
    divides unmatched alerts by the labeled-negative observation time of the same
    fixtures (total duration minus labeled positive intervals).
    """
    total_events = matched_events = 0
    total_alerts = 0
    false_alerts = []
    pre_onset_alerts = 0
    ttd_values = []
    missed_events = []
    negative_seconds = 0.0
    for fixture, output in per_fixture:
        duration = float(fixture["media"]["duration_s"])
        intervals = positive_intervals(fixture["labels"], duration)
        negative_seconds += duration - covered_seconds(intervals)
        events = build_events(fixture["labels"], duration)
        total_events += len(events)
        alerts = output.get("alerts", [])
        total_alerts += len(alerts)
        matches, unmatched = match_alerts_to_events(alerts, events, match_before_s, match_after_s)
        matched_events += len(matches)
        matched_event_ids = {m["event_id"] for m in matches}
        for event in events:
            if event["event_id"] not in matched_event_ids:
                missed_events.append({"fixture_id": fixture["fixture_id"], "event_id": event["event_id"],
                                      "onset_s": event["onset_s"], "onset_known": event["onset_known"]})
        for match in matches:
            if match["time_to_detection_s"] is not None:
                ttd_values.append(match["time_to_detection_s"])
        for alert in unmatched:
            time_s = float(alert["time_s"])
            later_onsets = [e["onset_s"] for e in events if e["onset_s"] > time_s]
            is_pre_onset = bool(later_onsets) and time_s < min(later_onsets)
            if is_pre_onset:
                pre_onset_alerts += 1
            false_alerts.append({"fixture_id": fixture["fixture_id"], "alert_id": alert["alert_id"],
                                 "time_s": time_s, "pre_onset": is_pre_onset})
    negative_hours = negative_seconds / 3600.0
    ttd_sorted = sorted(ttd_values)
    return {
        "level": "event",
        "match_before_s": match_before_s, "match_after_s": match_after_s,
        "events_total": total_events, "events_matched": matched_events,
        "events_missed": total_events - matched_events,
        "event_recall": _ratio(matched_events, total_events),
        "alerts_total": total_alerts,
        "alerts_matched": total_alerts - len(false_alerts),
        "alert_precision": _ratio(total_alerts - len(false_alerts), total_alerts),
        "false_alerts": len(false_alerts),
        "false_alerts_detail": sorted(false_alerts, key=lambda row: (row["fixture_id"], row["alert_id"])),
        "pre_onset_false_alerts": pre_onset_alerts,
        "negative_observation_seconds": _round(negative_seconds),
        "negative_observation_hours": _round(negative_hours, 9),
        "false_alerts_per_camera_hour": _ratio(len(false_alerts), negative_hours) if negative_hours else None,
        "missed_events_detail": missed_events,
        "time_to_detection_s": {
            "count": len(ttd_values),
            "p50": _round(_percentile(ttd_sorted, 0.5)),
            "p95": _round(_percentile(ttd_sorted, 0.95)),
            "min": _round(ttd_sorted[0]) if ttd_sorted else None,
            "max": _round(ttd_sorted[-1]) if ttd_sorted else None,
            "onset_known_only": True,
        },
    }


def counting_metrics(per_fixture, presence_tol_s=0.25):
    """Visible/unique/event counting evaluation for WT-22 track outputs.

    visible counts: |track ids with a row within presence_tol_s of each labeled
    sample time| vs labeled visible_persons.
    unique counts: distinct track ids over the clip vs labeled unique_persons.
    event counts: track births (first appearance of an id) vs labeled events.
    Failure taxonomy: per-tag aggregation of labeled failure modes with the mean
    absolute visible-count error of the fixtures carrying that tag.
    """
    rows = []
    taxonomy = {}
    for fixture, output in per_fixture:
        counts = fixture["labels"].get("counts")
        if not counts:
            continue
        tracks = output.get("tracks", [])
        ids_at = lambda t: {str(r["track_id"]) for r in tracks if abs(float(r["time_s"]) - t) <= presence_tol_s}
        visible_errors, exact = [], 0
        for sample_time, labeled in zip(counts["sample_times_s"], counts["visible_persons"]):
            estimated = len(ids_at(float(sample_time)))
            error = estimated - labeled
            visible_errors.append(error)
            exact += 1 if error == 0 else 0
        distinct_ids = {str(r["track_id"]) for r in tracks}
        first_seen = {}
        for row in sorted(tracks, key=lambda r: float(r["time_s"])):
            first_seen.setdefault(str(row["track_id"]), float(row["time_s"]))
        unique_error = len(distinct_ids) - counts["unique_persons"]
        event_error = len(first_seen) - counts["events"]
        rows.append({"fixture_id": fixture["fixture_id"], "samples": len(visible_errors),
                     "visible_errors": visible_errors, "visible_exact": exact,
                     "unique_error": unique_error, "event_error": event_error,
                     "failure_modes": counts.get("failure_modes") or {}})
        for tag, count in (counts.get("failure_modes") or {}).items():
            taxonomy.setdefault(tag, {"fixtures": 0, "labeled_occurrences": 0, "visible_abs_errors": []})
            taxonomy[tag]["fixtures"] += 1
            taxonomy[tag]["labeled_occurrences"] += count
            taxonomy[tag]["visible_abs_errors"].extend(abs(e) for e in visible_errors)
    if not rows:
        return {"level": "counting", "available": False,
                "reason": "no fixture carries labels.counts; counting metrics unmeasured"}
    all_errors = [e for row in rows for e in row["visible_errors"]]
    abs_errors = [abs(e) for e in all_errors]
    n = len(all_errors)
    return {
        "level": "counting", "available": True,
        "fixtures_evaluated": len(rows), "visible_samples": n,
        "visible_mae": _round(sum(abs_errors) / n) if n else None,
        "visible_rmse": _round(math.sqrt(sum(e * e for e in all_errors) / n)) if n else None,
        "visible_bias": _round(sum(all_errors) / n) if n else None,
        "visible_exact_rate": _ratio(sum(row["visible_exact"] for row in rows), n),
        "unique_abs_error": {"count": len(rows), "mean": _round(sum(abs(r["unique_error"]) for r in rows) / len(rows)),
                             "values": [[r["fixture_id"], r["unique_error"]] for r in sorted(rows, key=lambda r: r["fixture_id"])]},
        "event_abs_error": {"count": len(rows), "mean": _round(sum(abs(r["event_error"]) for r in rows) / len(rows)),
                            "values": [[r["fixture_id"], r["event_error"]] for r in sorted(rows, key=lambda r: r["fixture_id"])]},
        "failure_taxonomy": {
            tag: {"fixtures": data["fixtures"], "labeled_occurrences": data["labeled_occurrences"],
                  "visible_mae_on_tagged_fixtures": _round(sum(data["visible_abs_errors"]) / len(data["visible_abs_errors"]))
                  if data["visible_abs_errors"] else None}
            for tag, data in sorted(taxonomy.items())
        },
    }


def _iou(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = inter_w * inter_h
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def detection_level_metrics(per_fixture, class_name, threshold, positive_label_classes):
    """Clip-level metrics from detections of one class.

    Per fixture the score is the MAX score of that class (0.0 when the detector
    never fired); the label is 1 iff the fixture's labels.class is in
    positive_label_classes. Clip-level only: it cannot express per-frame AP50.
    """
    items = []
    for fixture, output in per_fixture:
        scores = [float(d["score"]) for d in output.get("detections", []) if d.get("class") == class_name]
        items.append((max(scores) if scores else 0.0,
                      1 if fixture["labels"].get("class") in positive_label_classes else 0))
    counts = confusion_at_threshold(items, threshold)
    return {"level": "clip(detection)", "class": class_name, "threshold": threshold,
            **counts, **precision_recall(counts),
            "average_precision": _round(average_precision(items))}


def box_level_metrics(per_fixture, class_name, iou_threshold=0.5, frame_match_tol_s=0.25):
    """AP50-style detection quality against BOX-level ground truth.

    Only labeled frames participate (labels.boxes); detections outside the
    labeled frames cannot be judged and are excluded from the denominators —
    the report must say so via the caller's caveats. Without box labels this
    returns unavailable, never an estimate from clip labels.
    """
    gt_boxes = []
    for fixture, output in per_fixture:
        for box in fixture["labels"].get("boxes") or []:
            if box.get("class") == class_name:
                gt_boxes.append({"fixture_id": fixture["fixture_id"],
                                 "frame_time_s": float(box["frame_time_s"]),
                                 "bbox": box["bbox"]})
    if not gt_boxes:
        return {"ap50": None, "class": class_name, "reason": "no box-level ground truth in fixtures"}
    scored = []
    for fixture, output in per_fixture:
        labeled_times = [b["frame_time_s"] for b in gt_boxes if b["fixture_id"] == fixture["fixture_id"]]
        for det in output.get("detections", []):
            if det.get("class") != class_name:
                continue
            if not any(abs(float(det["time_s"]) - t) <= frame_match_tol_s for t in labeled_times):
                continue
            scored.append((float(det["score"]), fixture["fixture_id"], float(det["time_s"]), det["bbox"]))
    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    matched = set()
    hits = 0
    previous_recall = 0.0
    ap = 0.0
    positives = len(gt_boxes)
    for rank, (score, fixture_id, time_s, bbox) in enumerate(scored, start=1):
        best, best_iou = None, 0.0
        for index, gt in enumerate(gt_boxes):
            if index in matched or gt["fixture_id"] != fixture_id:
                continue
            if abs(gt["frame_time_s"] - time_s) > frame_match_tol_s:
                continue
            overlap = _iou(bbox, gt["bbox"])
            if overlap > best_iou:
                best, best_iou = index, overlap
        if best is not None and best_iou >= iou_threshold:
            matched.add(best)
            hits += 1
            recall = hits / positives
            precision = hits / rank
            ap += (recall - previous_recall) * precision
            previous_recall = recall
    return {"ap50": _round(ap), "class": class_name, "iou_threshold": iou_threshold,
            "frame_match_tol_s": frame_match_tol_s,
            "gt_boxes": positives, "detections_scored": len(scored),
            "detections_matched": hits,
            "caveat": "detections outside labeled frames are excluded from the denominators"}


def _unit_key(fixture, bootstrap_unit):
    return fixture["session_id"] if bootstrap_unit == "session" else fixture["fixture_id"]


def _unit_statistics(per_fixture, threshold, match_before_s, match_after_s, bootstrap_unit):
    """Per-independent-unit sufficient statistics for cluster bootstrap."""
    units = {}
    for fixture, output in per_fixture:
        key = _unit_key(fixture, bootstrap_unit)
        duration = float(fixture["media"]["duration_s"])
        intervals = positive_intervals(fixture["labels"], duration)
        frame = frame_level_metrics(output.get("windows", []), intervals, duration,
                                    float(fixture["media"]["fps"]), threshold)
        events = event_level_metrics([(fixture, output)], match_before_s, match_after_s)
        stat = units.setdefault(key, {"frames": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
                                      "windows": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
                                      "false_alerts": 0, "negative_seconds": 0.0,
                                      "events_matched": 0, "events_total": 0,
                                      "alerts_matched": 0, "alerts_total": 0,
                                      "ttd": []})
        for bucket in ("frames", "windows"):
            for name in ("tp", "fp", "tn", "fn"):
                stat[bucket][name] += frame[name] if bucket == "frames" else 0
        window = window_level_metrics(output.get("windows", []), intervals, threshold)
        for name in ("tp", "fp", "tn", "fn"):
            stat["windows"][name] += window[name]
        stat["false_alerts"] += events["false_alerts"]
        stat["negative_seconds"] += events["negative_observation_seconds"]
        stat["events_matched"] += events["events_matched"]
        stat["events_total"] += events["events_total"]
        stat["alerts_matched"] += events["alerts_matched"]
        stat["alerts_total"] += events["alerts_total"]
        stat["ttd"].extend(
            row["time_to_detection_s"] for row in
            [m for m in match_alerts_to_events(output.get("alerts", []),
                                               build_events(fixture["labels"], duration),
                                               match_before_s, match_after_s)[0]]
            if row["time_to_detection_s"] is not None)
    return units


def _statistic_from_units(unit_rows):
    frames = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    windows = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    false_alerts = negative_seconds = 0.0
    events_matched = events_total = alerts_matched = alerts_total = 0
    ttd = []
    for row in unit_rows:
        for name in frames:
            frames[name] += row["frames"][name]
            windows[name] += row["windows"][name]
        false_alerts += row["false_alerts"]
        negative_seconds += row["negative_seconds"]
        events_matched += row["events_matched"]
        events_total += row["events_total"]
        alerts_matched += row["alerts_matched"]
        alerts_total += row["alerts_total"]
        ttd.extend(row["ttd"])
    precision = _ratio(frames["tp"], frames["tp"] + frames["fp"])
    recall = _ratio(frames["tp"], frames["tp"] + frames["fn"])
    window_precision = _ratio(windows["tp"], windows["tp"] + windows["fp"])
    window_recall = _ratio(windows["tp"], windows["tp"] + windows["fn"])
    fa_per_hour = _ratio(false_alerts, negative_seconds / 3600.0) if negative_seconds else None
    return {"frame_precision": precision, "frame_recall": recall,
            "window_precision": window_precision, "window_recall": window_recall,
            "event_recall": _ratio(events_matched, events_total),
            "alert_precision": _ratio(alerts_matched, alerts_total),
            "false_alerts_per_camera_hour": fa_per_hour,
            "ttd_p50": _percentile(sorted(ttd), 0.5) if ttd else None}


def bootstrap_intervals(per_fixture, threshold, match_before_s, match_after_s,
                        bootstrap_unit, resamples, seed):
    """Cluster bootstrap over independent units (session or clip). Deterministic."""
    units = _unit_statistics(per_fixture, threshold, match_before_s, match_after_s, bootstrap_unit)
    keys = sorted(units)
    point = _statistic_from_units([units[key] for key in keys])
    rng = random.Random(seed)
    distributions = {name: [] for name in point}
    if len(keys) >= 2 and resamples > 0:
        for _ in range(resamples):
            sample = [units[keys[rng.randrange(len(keys))]] for _ in keys]
            stat = _statistic_from_units(sample)
            for name, value in stat.items():
                if value is not None and not (isinstance(value, float) and math.isnan(value)):
                    distributions[name].append(value)
    intervals = {}
    for name, values in distributions.items():
        ordered = sorted(values)
        intervals[name] = {
            "estimate": _round(point[name]),
            "ci95_low": _round(_percentile(ordered, 0.025)) if ordered else None,
            "ci95_high": _round(_percentile(ordered, 0.975)) if ordered else None,
            "resamples_with_value": len(ordered),
        }
    return {
        "unit": bootstrap_unit, "units": len(keys), "unit_ids": keys,
        "resamples": resamples, "seed": seed,
        "method": "cluster bootstrap over independent units; percentile 95% CI; "
                  "adjacent frames/windows never resampled independently",
        "intervals": intervals,
    }
