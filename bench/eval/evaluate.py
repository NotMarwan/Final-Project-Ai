"""WT-12 evaluation CLI: recorded model outputs + fixture manifest -> protocol report.

Usage (from the repository root, with the campaign environment active):

    python -m bench.eval.evaluate ^
        --manifest docs/campaign/eval/12-fixture-manifest.json ^
        --outputs bench/results/<run>/outputs ^
        --report bench/results/<run>/eval-report.json ^
        --threshold 0.45 --bootstrap-unit session --bootstrap-resamples 2000 --seed 20260929

The operating threshold must be fixed BEFORE results are inspected; threshold
retuning is a separate declared experiment (see the protocol document).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from bench.eval import metrics
from bench.eval.contracts import ContractError, load_manifest, load_outputs


def _slice_metrics(per_fixture, threshold, match_before_s, match_after_s):
    frames = windows = None
    for fixture, output in per_fixture:
        duration = float(fixture["media"]["duration_s"])
        intervals = metrics.positive_intervals(fixture["labels"], duration)
        window_items = [(float(w["violence_conf"]), metrics.window_label(w, intervals))
                        for w in output.get("windows", [])]
        frame = metrics.frame_level_metrics(output.get("windows", []), intervals, duration,
                                            float(fixture["media"]["fps"]), threshold)
        window = metrics.window_level_metrics(output.get("windows", []), intervals, threshold)
        frames = _accumulate(frames, frame)
        windows = _accumulate(windows, window)
        windows["scores"].extend(window_items)
    event = metrics.event_level_metrics(per_fixture, match_before_s, match_after_s)
    counting = metrics.counting_metrics(per_fixture)
    return {
        "fixtures": sorted(fixture["fixture_id"] for fixture, _ in per_fixture),
        "fixtures_n": len(per_fixture),
        "frame_level": _finalize(frames, threshold, "frame"),
        "window_level": _finalize(windows, threshold, "window"),
        "frame_level_by_class": _by_class(per_fixture, threshold),
        "event_level": event,
        "counting": counting,
    }


DETECTION_POSITIVE_LABELS = {
    "weapon": {"weapon"},
    "violence": {"violence", "violence_like"},
    "person": {"person"},
}


def _by_class(per_fixture, threshold):
    classes = sorted({d.get("class") for _, output in per_fixture
                      for d in output.get("detections", []) if d.get("class")})
    if not classes:
        return {"available": False, "reason": "no detections recorded in outputs"}
    result = {"available": True, "classes": {}}
    for name in classes:
        positives = DETECTION_POSITIVE_LABELS.get(name, {name})
        entry = metrics.detection_level_metrics(per_fixture, name, threshold, positives)
        entry["box_level"] = metrics.box_level_metrics(per_fixture, name)
        result["classes"][name] = entry
    return result


def _accumulate(total, counts):
    total = total or {"tp": 0, "fp": 0, "tn": 0, "fn": 0,
                      "grid_frames": 0, "unevaluated_frames": 0, "scores": []}
    for name in ("tp", "fp", "tn", "fn"):
        total[name] += counts[name]
    total["grid_frames"] += counts.get("grid_frames", 0)
    total["unevaluated_frames"] += counts.get("unevaluated_frames", 0)
    return total


def _finalize(total, threshold, level):
    if total is None:
        return {"level": level, "available": False, "reason": "no fixtures in slice"}
    counts = {name: total[name] for name in ("tp", "fp", "tn", "fn")}
    counts.update({"predicted_positive": counts["tp"] + counts["fp"],
                   "actual_positive": counts["tp"] + counts["fn"],
                   "predicted_negative": counts["tn"] + counts["fn"],
                   "actual_negative": counts["tn"] + counts["fp"],
                   "n": sum(counts[name] for name in ("tp", "fp", "tn", "fn"))})
    result = {"level": level, "threshold": threshold, **counts, **metrics.precision_recall(counts)}
    if level == "window":
        result["average_precision"] = metrics._round(metrics.average_precision(total.get("scores", [])))
    if level == "frame":
        result["grid_frames"] = total["grid_frames"]
        result["unevaluated_frames"] = total["unevaluated_frames"]
    return result


def build_report(manifest, outputs, threshold, match_before_s, match_after_s,
                 bootstrap_unit, bootstrap_resamples, seed):
    per_fixture = [(manifest["_by_id"][record["fixture_id"]], record) for record in outputs]
    splits = {}
    for fixture, _ in per_fixture:
        splits.setdefault(fixture["split"], []).append((fixture, _))
    evaluated = {name: rows for name, rows in sorted(splits.items())
                 if name in {"val", "calibration", "test", "regression-only"}}
    unavailable = []
    onset_known = any(f["labels"].get("onset_s") is not None for f, _ in per_fixture)
    counts_labeled = any(f["labels"].get("counts") for f, _ in per_fixture)
    if not onset_known:
        unavailable.append({"metric": "time_to_detection_s",
                            "reason": "no evaluated fixture carries an independently labeled onset; "
                                      "clip-level publisher labels cannot time the alert"})
    if not counts_labeled:
        unavailable.append({"metric": "counting",
                            "reason": "no evaluated fixture carries labels.counts"})
    has_boxes = any(fixture["labels"].get("boxes") for fixture, _ in per_fixture)
    if not has_boxes:
        unavailable.append({"metric": "ap50_by_class",
                            "reason": "no box-level ground truth in fixtures"})
    slices = {"all": _slice_metrics(per_fixture, threshold, match_before_s, match_after_s)}
    tag_index = {}
    for fixture, record in per_fixture:
        for tag in fixture["difficulty_tags"]:
            tag_index.setdefault(tag, []).append((fixture, record))
    for tag, rows in sorted(tag_index.items()):
        slices[tag] = _slice_metrics(rows, threshold, match_before_s, match_after_s)
    report = {
        "schema_version": "wt12-eval-report/1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol": "docs/campaign/eval/12-eval-protocol.md",
        "manifest": manifest["_path"],
        "operating_point": {"violence_threshold": threshold, "match_before_s": match_before_s,
                            "match_after_s": match_after_s,
                            "rule": "threshold fixed before inspecting results; retuning is a separate declared step"},
        "splits_evaluated": sorted(evaluated),
        "fixtures_evaluated": sorted(fixture["fixture_id"] for fixture, _ in per_fixture),
        "source_modes": sorted({record["source_mode"] for record in outputs}),
        "slices": slices,
        "bootstrap": metrics.bootstrap_intervals(per_fixture, threshold, match_before_s, match_after_s,
                                                 bootstrap_unit, bootstrap_resamples, seed),
        "unavailable_metrics": unavailable,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Compute WT-12 protocol metrics")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--outputs", required=True,
                        help="directory of <fixture_id>.json, one JSON file, or a comma-separated "
                             "list of them (anchor passes merge per fixture)")
    parser.add_argument("--report", required=True)
    parser.add_argument("--threshold", type=float, required=True,
                        help="violence operating threshold fixed before inspecting results")
    parser.add_argument("--match-before-s", type=float, default=0.0)
    parser.add_argument("--match-after-s", type=float, default=5.0)
    parser.add_argument("--bootstrap-unit", choices=("session", "clip"), default="session")
    parser.add_argument("--bootstrap-resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260929)
    args = parser.parse_args()
    if not 0.0 <= args.threshold <= 1.0:
        raise SystemExit("--threshold must be in [0,1]")
    manifest = load_manifest(args.manifest)
    outputs = load_outputs(manifest, args.outputs)
    report = build_report(manifest, outputs, args.threshold, args.match_before_s, args.match_after_s,
                          args.bootstrap_unit, args.bootstrap_resamples, args.seed)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({"report": str(report_path), "fixtures": len(outputs),
                      "slices": sorted(report["slices"]),
                      "unavailable_metrics": report["unavailable_metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
