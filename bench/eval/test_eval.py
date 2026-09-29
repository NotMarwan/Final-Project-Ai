"""Self-tests for the WT-12 evaluation tooling: synthetic outputs -> known metrics.

Every expected number below is hand-computed from the synthetic fixtures defined
in this file (see comments), not re-derived through the implementation under test.
"""
from __future__ import annotations

import copy
import json

import pytest

from bench.eval import metrics
from bench.eval.contracts import ContractError, load_manifest, load_outputs


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------

def make_fixture(fixture_id, *, category, subcategory, duration_s, sha256,
                 session_id, split="test", labels_extra=None, counts=None,
                 tags=None, fps=1.0, frames=None):
    labels = {
        "class": "benign" if category == "negative" else "violence_like",
        "label_source": "publisher",
        "annotation_ref": "synthetic self-test annotation (NOT evaluation truth)",
        "onset_s": None,
        "onset_available": False,
        "frames": frames,
        "counts": counts,
    }
    labels.update(labels_extra or {})
    return {
        "fixture_id": fixture_id,
        "category": category,
        "subcategory": subcategory,
        "split": split,
        "session_id": session_id,
        "media": {"path": f"synthetic/{fixture_id}.avi", "sha256": sha256, "bytes": 1024,
                  "duration_s": duration_s, "fps": fps, "width": 160, "height": 120,
                  "frame_count": int(duration_s * fps)},
        "source": {"dataset": "WT-12 self-test", "url": "https://example.invalid/selftest",
                   "retrieved": "2026-09-29"},
        "license": {"name": "n/a self-test", "spdx": "LicenseRef-SELFTEST",
                    "rights_basis": "synthetic record; no media, no rights",
                    "commercial_use": False, "redistribution": "none",
                    "verified_on": "2026-09-29"},
        "labels": labels,
        "difficulty_tags": tags or [],
        "notes": "self-test fixture",
    }


def make_manifest(fixtures):
    return {
        "schema_version": "wt12-fixture-manifest/1",
        "generated": "2026-09-29",
        "media_root": "C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12-fixtures",
        "policy": {
            "label_provenance_allowed": ["independent-human", "publisher"],
            "label_provenance_forbidden": ["auto", "model", "pseudo", "synthetic"],
            "note": "self-test manifest",
        },
        "fixtures": fixtures,
        "unavailable_categories": [],
    }


def make_output(fixture_id, sha256, *, windows=(), alerts=(), detections=(), tracks=()):
    return {"fixture_id": fixture_id, "source_sha256": sha256, "run_id": "selftest",
            "source_mode": "file-media",
            "windows": list(windows), "alerts": list(alerts),
            "detections": list(detections), "tracks": list(tracks)}


def window(start, end, score, valid=True):
    return {"window_id": f"w{int(start * 1000):06d}", "start_s": start, "end_s": end,
            "violence_conf": score, "weapon_score": 0.0, "observation_score": score,
            "valid": valid, "frames_collected": 32, "frames_required": 32}


# Scenario A/C: two 4 s clips at 1 fps; 4 windows per clip, one per second.
# pos-1 (clip-level positive -> every window/frame positive): scores 0.9 0.6 0.4 0.2
# neg-1 (benign): scores 0.7 0.3 0.1 0.1
# threshold 0.5 -> tp=2 fp=1 tn=3 fn=2 (hand-enumerated).
POS_SHA = "a" * 64
NEG_SHA = "b" * 64
SCENARIO_A_FIXTURES = [
    make_fixture("pos-1", category="positive", subcategory="violence_staged", duration_s=4.0,
                 sha256=POS_SHA, session_id="sess-1"),
    make_fixture("neg-1", category="negative", subcategory="walking", duration_s=4.0,
                 sha256=NEG_SHA, session_id="sess-2"),
]
SCENARIO_A_OUTPUTS = [
    make_output("pos-1", POS_SHA, windows=[window(0, 1, 0.9), window(1, 2, 0.6),
                                           window(2, 3, 0.4), window(3, 4, 0.2)]),
    make_output("neg-1", NEG_SHA, windows=[window(0, 1, 0.7), window(1, 2, 0.3),
                                           window(2, 3, 0.1), window(3, 4, 0.1)]),
]


def test_window_level_confusion_precision_recall_match_hand_computation():
    intervals = metrics.positive_intervals(SCENARIO_A_FIXTURES[0]["labels"], 4.0)
    result = metrics.window_level_metrics(SCENARIO_A_OUTPUTS[0]["windows"] + SCENARIO_A_OUTPUTS[1]["windows"],
                                          [], 0.5)  # wrong-label control first
    assert (result["tp"], result["fp"], result["tn"], result["fn"]) == (0, 3, 5, 0)  # all negative labels
    items = ([(float(w["violence_conf"]), 1) for w in SCENARIO_A_OUTPUTS[0]["windows"]] +
             [(float(w["violence_conf"]), 0) for w in SCENARIO_A_OUTPUTS[1]["windows"]])
    counts = metrics.confusion_at_threshold(items, 0.5)
    assert (counts["tp"], counts["fp"], counts["tn"], counts["fn"]) == (2, 1, 3, 2)
    pr = metrics.precision_recall(counts)
    assert pr["precision"] == pytest.approx(2 / 3)
    assert pr["recall"] == pytest.approx(0.5)
    assert pr["f1"] == pytest.approx(4 / 7)
    assert intervals == [(0.0, 4.0)]


def test_average_precision_matches_hand_computation():
    items = [(0.9, 1), (0.6, 1), (0.4, 1), (0.2, 1), (0.7, 0), (0.3, 0), (0.1, 0), (0.1, 0)]
    # Ranks by score desc: 0.9+ 0.7- 0.6+ 0.4+ 0.3- 0.2+ 0.1- 0.1-
    # AP = .25*1 + .25*(2/3) + .25*(3/4) + .25*(4/6) = 0.25 + 0.166667 + 0.1875 + 0.166667
    assert metrics.average_precision(items) == pytest.approx(0.770833, abs=1e-6)
    assert metrics.average_precision([(0.5, 1)]) is None  # single class -> unavailable, not 0


def test_frame_level_grid_uses_covering_window_and_counts_unevaluated():
    intervals = metrics.positive_intervals(SCENARIO_A_FIXTURES[0]["labels"], 4.0)
    result = metrics.frame_level_metrics(SCENARIO_A_OUTPUTS[0]["windows"], intervals, 4.0, 1.0, 0.5)
    assert result["grid_frames"] == 4
    assert result["unevaluated_frames"] == 0
    assert (result["tp"], result["fp"], result["tn"], result["fn"]) == (2, 0, 0, 2)
    # A window covering only the first 2 s leaves the rest of the grid unevaluated.
    partial = metrics.frame_level_metrics([window(0, 2, 0.9)], intervals, 4.0, 1.0, 0.5)
    assert partial["unevaluated_frames"] == 2
    assert partial["n"] == 2


def test_event_level_ttd_false_alerts_and_per_camera_hour():
    # pos-2: 30 s, positive interval [10,15], onset 10.0. Alerts 11.2 (TTD=1.2),
    # 12.5 (event already matched -> false), 25.0 (false, not pre-onset).
    # neg-2: 60 s benign. Alert 30.0 (false).
    # negative observation = (30-5) + 60 = 85 s; false=3 -> 3/(85/3600)=127.058824/h
    pos2 = make_fixture("pos-2", category="positive", subcategory="violence_staged", duration_s=30.0,
                        sha256="c" * 64, session_id="sess-3",
                        labels_extra={"onset_s": 10.0, "onset_available": True,
                                      "frames": [{"start_s": 10.0, "end_s": 15.0, "label": "violence_like"}]})
    neg2 = make_fixture("neg-2", category="negative", subcategory="walking", duration_s=60.0,
                        sha256="d" * 64, session_id="sess-4")
    out_pos = make_output("pos-2", "c" * 64, alerts=[
        {"alert_id": "a1", "time_s": 11.2, "score": 0.8},
        {"alert_id": "a2", "time_s": 12.5, "score": 0.7},
        {"alert_id": "a3", "time_s": 25.0, "score": 0.6}])
    out_neg = make_output("neg-2", "d" * 64, alerts=[{"alert_id": "b1", "time_s": 30.0, "score": 0.55}])
    result = metrics.event_level_metrics([(pos2, out_pos), (neg2, out_neg)], 0.0, 5.0)
    assert result["events_total"] == 1 and result["events_matched"] == 1
    assert result["event_recall"] == 1.0
    assert result["alerts_total"] == 4 and result["false_alerts"] == 3
    assert result["alert_precision"] == pytest.approx(0.25)
    assert result["time_to_detection_s"]["count"] == 1
    assert result["time_to_detection_s"]["p50"] == pytest.approx(1.2)
    assert result["negative_observation_seconds"] == pytest.approx(85.0)
    assert result["false_alerts_per_camera_hour"] == pytest.approx(3 * 3600 / 85)
    assert result["pre_onset_false_alerts"] == 0


def test_pre_onset_alerts_are_flagged_and_do_not_count_as_detection():
    # pos-3: 20 s, interval [8,12], onset 8.0; alerts at 5.0 (pre-onset false) and
    # 9.0 (TTD=1.0). negative obs = 20-4 = 16 s; false=1 -> 1/(16/3600) = 225/h
    pos3 = make_fixture("pos-3", category="positive", subcategory="violence_staged", duration_s=20.0,
                        sha256="e" * 64, session_id="sess-5",
                        labels_extra={"onset_s": 8.0, "onset_available": True,
                                      "frames": [{"start_s": 8.0, "end_s": 12.0, "label": "violence_like"}]})
    out = make_output("pos-3", "e" * 64, alerts=[
        {"alert_id": "x1", "time_s": 5.0, "score": 0.9},
        {"alert_id": "x2", "time_s": 9.0, "score": 0.9}])
    result = metrics.event_level_metrics([(pos3, out)], 0.0, 5.0)
    assert result["events_matched"] == 1 and result["event_recall"] == 1.0
    assert result["false_alerts"] == 1 and result["pre_onset_false_alerts"] == 1
    assert result["time_to_detection_s"]["p50"] == pytest.approx(1.0)
    assert result["false_alerts_per_camera_hour"] == pytest.approx(225.0)


def test_time_to_detection_unavailable_without_onset():
    pos = make_fixture("pos-4", category="positive", subcategory="violence_staged", duration_s=10.0,
                       sha256="f" * 64, session_id="sess-6")  # clip-level label, no onset
    out = make_output("pos-4", "f" * 64, alerts=[{"alert_id": "y1", "time_s": 4.0, "score": 0.9}])
    result = metrics.event_level_metrics([(pos, out)], 0.0, 5.0)
    assert result["events_matched"] == 1  # clip-level events still detectable
    assert result["time_to_detection_s"]["count"] == 0  # but TTD is unmeasured, not zero
    assert result["time_to_detection_s"]["p50"] is None


def test_counting_metrics_visible_unique_event_and_taxonomy():
    counts = {"visible_persons": [1, 2], "sample_times_s": [0.5, 2.5], "unique_persons": 2,
              "events": 1, "failure_modes": {"occlusion": 1, "reentry": 1}}
    fixture = make_fixture("cnt-1", category="negative", subcategory="walking", duration_s=4.0,
                           sha256="1" * 64, session_id="sess-7", counts=counts)
    tracks = [{"time_s": 0.5, "track_id": "a", "bbox": [0, 0, 1, 1]},
              {"time_s": 2.4, "track_id": "a", "bbox": [0, 0, 1, 1]},
              {"time_s": 3.0, "track_id": "a", "bbox": [0, 0, 1, 1]}]
    out = make_output("cnt-1", "1" * 64, tracks=tracks)
    result = metrics.counting_metrics([(fixture, out)])
    assert result["available"] and result["visible_samples"] == 2
    # sample 0.5: |{a}|=1 vs 1 -> error 0; sample 2.5: ids within 0.25 s = {a} -> 1 vs 2 -> error -1
    assert result["visible_mae"] == pytest.approx(0.5)
    assert result["visible_rmse"] == pytest.approx((0.5) ** 0.5)
    assert result["visible_bias"] == pytest.approx(-0.5)
    assert result["visible_exact_rate"] == pytest.approx(0.5)
    assert result["unique_abs_error"]["values"] == [["cnt-1", -1]]  # 1 distinct id vs labeled 2
    assert result["event_abs_error"]["values"] == [["cnt-1", 0]]    # 1 track birth vs labeled 1
    assert result["failure_taxonomy"]["occlusion"]["labeled_occurrences"] == 1
    assert result["failure_taxonomy"]["occlusion"]["visible_mae_on_tagged_fixtures"] == pytest.approx(0.5)


def test_counting_unavailable_without_labels():
    fixture = make_fixture("cnt-2", category="negative", subcategory="walking", duration_s=2.0,
                           sha256="2" * 64, session_id="sess-8")
    result = metrics.counting_metrics([(fixture, make_output("cnt-2", "2" * 64))])
    assert result["available"] is False and result["reason"]


def test_bootstrap_is_deterministic_and_respects_independent_units():
    per_fixture = [(f, o) for f, o in zip(SCENARIO_A_FIXTURES, SCENARIO_A_OUTPUTS)]
    first = metrics.bootstrap_intervals(per_fixture, 0.5, 0.0, 5.0, "session", 200, 20260929)
    second = metrics.bootstrap_intervals(per_fixture, 0.5, 0.0, 5.0, "session", 200, 20260929)
    assert first == second  # identical seed -> byte-identical result
    assert first["units"] == 2 and first["unit_ids"] == ["sess-1", "sess-2"]
    recall = first["intervals"]["frame_recall"]
    assert recall["estimate"] == pytest.approx(0.5)
    assert recall["resamples_with_value"] > 0
    assert recall["ci95_low"] <= recall["ci95_high"]


def test_negative_control_threshold_one_yields_zero_predicted_positives():
    items = [(float(w["violence_conf"]), 1) for w in SCENARIO_A_OUTPUTS[0]["windows"]]
    counts = metrics.confusion_at_threshold(items, 1.0)
    assert counts["predicted_positive"] == 0 and counts["fn"] == 4


# --------------------------------------------------------------------------
# Contract enforcement
# --------------------------------------------------------------------------

def _manifest_document(fixtures):
    return make_manifest(fixtures)


def test_contract_rejects_model_labels():
    fixture = make_fixture("bad-1", category="negative", subcategory="walking", duration_s=2.0,
                           sha256="3" * 64, session_id="sess-9")
    fixture["labels"]["label_source"] = "model"
    with pytest.raises(ContractError, match="label_source"):
        load_manifest_json(_manifest_document([fixture]))


def test_contract_rejects_duplicate_media_hashes():
    fixtures = [
        make_fixture("dup-1", category="negative", subcategory="walking", duration_s=2.0,
                     sha256="4" * 64, session_id="sess-10"),
        make_fixture("dup-2", category="negative", subcategory="waving", duration_s=2.0,
                     sha256="4" * 64, session_id="sess-11"),
    ]
    with pytest.raises(ContractError, match="duplicates"):
        load_manifest_json(_manifest_document(fixtures))


def test_contract_rejects_session_straddling_splits():
    fixtures = [
        make_fixture("strad-1", category="negative", subcategory="walking", duration_s=2.0,
                     sha256="5" * 64, session_id="sess-12", split="val"),
        make_fixture("strad-2", category="negative", subcategory="waving", duration_s=2.0,
                     sha256="6" * 64, session_id="sess-12", split="test"),
    ]
    with pytest.raises(ContractError, match="straddles"):
        load_manifest_json(_manifest_document(fixtures))


def test_contract_rejects_missing_rights_block():
    fixture = make_fixture("rights-1", category="negative", subcategory="walking", duration_s=2.0,
                           sha256="7" * 64, session_id="sess-13")
    fixture["license"].pop("rights_basis")
    with pytest.raises(ContractError, match="rights_basis"):
        load_manifest_json(_manifest_document([fixture]))


def test_outputs_must_match_manifest_sha_and_declare_source_mode(tmp_path):
    fixture = make_fixture("out-1", category="negative", subcategory="walking", duration_s=2.0,
                           sha256="8" * 64, session_id="sess-14")
    manifest = load_manifest_json(_manifest_document([fixture]))
    good = make_output("out-1", "8" * 64)
    assert load_outputs(manifest, _write_outputs(tmp_path, [good]))[0]["fixture_id"] == "out-1"
    wrong_sha = make_output("out-1", "9" * 64)
    with pytest.raises(ContractError, match="source_sha256"):
        load_outputs(manifest, _write_outputs(tmp_path, [wrong_sha]))
    live = make_output("out-1", "8" * 64)
    live["source_mode"] = "live"
    with pytest.raises(ContractError, match="live"):
        load_outputs(manifest, _write_outputs(tmp_path, [live]))


def load_manifest_json(document):
    """Validate an in-memory manifest document through the same code path."""
    import json as _json
    import tempfile
    from pathlib import Path as _Path
    with tempfile.TemporaryDirectory() as tmp:
        path = _Path(tmp) / "manifest.json"
        path.write_text(_json.dumps(document), encoding="utf-8")
        return load_manifest(path)


def _write_outputs(tmp_path, records):
    target = tmp_path / "outputs.json"
    target.write_text(json.dumps(records), encoding="utf-8")
    return target


def test_evaluate_end_to_end_report_has_slices_denominators_and_gaps(tmp_path):
    from bench.eval.evaluate import build_report
    manifest = load_manifest_json(_manifest_document(SCENARIO_A_FIXTURES))
    report = build_report(manifest, SCENARIO_A_OUTPUTS, 0.5, 0.0, 5.0, "session", 50, 7)
    assert report["fixtures_evaluated"] == ["neg-1", "pos-1"]
    all_slice = report["slices"]["all"]
    counts = all_slice["window_level"]
    assert (counts["tp"], counts["fp"], counts["tn"], counts["fn"]) == (2, 1, 3, 2)
    assert counts["n"] == 8
    gap_names = {gap["metric"] for gap in report["unavailable_metrics"]}
    assert "time_to_detection_s" in gap_names  # scenario A has no onset labels
    assert "counting" in gap_names             # scenario A has no counts
    first = json.dumps(report, sort_keys=True)
    second = json.dumps(build_report(manifest, SCENARIO_A_OUTPUTS, 0.5, 0.0, 5.0, "session", 50, 7),
                        sort_keys=True)
    # Timestamps differ by construction; compare everything else deterministically.
    strip = lambda text: text.split('"generated_utc"')[1][text.split('"generated_utc"')[1].index(","):]
    assert strip(first) == strip(second)


def test_difficulty_slices_break_down_by_tag():
    from bench.eval.evaluate import build_report
    fixtures = copy.deepcopy(SCENARIO_A_FIXTURES)
    fixtures[0]["difficulty_tags"] = ["low_light"]
    fixtures[1]["difficulty_tags"] = ["low_light", "motion_blur"]
    manifest = load_manifest_json(_manifest_document(fixtures))
    report = build_report(manifest, SCENARIO_A_OUTPUTS, 0.5, 0.0, 5.0, "session", 10, 7)
    assert set(report["slices"]) == {"all", "low_light", "motion_blur"}
    assert report["slices"]["low_light"]["fixtures_n"] == 2
    assert report["slices"]["motion_blur"]["fixtures"] == ["neg-1"]


def test_detection_level_metrics_use_max_score_and_clip_labels():
    fixtures = [
        make_fixture("wp-1", category="positive", subcategory="weapon_visible", duration_s=2.0,
                     sha256="a1" + "0" * 62, session_id="sess-w1",
                     labels_extra={"class": "weapon"}),
        make_fixture("wn-1", category="negative", subcategory="walking", duration_s=2.0,
                     sha256="b1" + "0" * 62, session_id="sess-w2"),
    ]
    outputs = [
        make_output("wp-1", "a1" + "0" * 62, detections=[
            {"time_s": 0.5, "class": "weapon", "score": 0.4, "bbox": [0, 0, 2, 2]},
            {"time_s": 1.5, "class": "weapon", "score": 0.8, "bbox": [0, 0, 2, 2]}]),
        make_output("wn-1", "b1" + "0" * 62, detections=[
            {"time_s": 1.0, "class": "weapon", "score": 0.6, "bbox": [0, 0, 2, 2]}]),
    ]
    per_fixture = list(zip(fixtures, outputs))
    result = metrics.detection_level_metrics(per_fixture, "weapon", 0.5, {"weapon"})
    # wp-1 max score 0.8 -> tp at 0.5; wn-1 max 0.6 -> fp
    assert (result["tp"], result["fp"], result["tn"], result["fn"]) == (1, 1, 0, 0)
    assert result["precision"] == pytest.approx(0.5) and result["recall"] == pytest.approx(1.0)
    # AP over [(0.8,1),(0.6,0)] = 1.0 (the positive ranks first)
    assert result["average_precision"] == pytest.approx(1.0)


def test_box_level_ap50_requires_ground_truth_and_matches_iou():
    fixture = make_fixture("box-1", category="positive", subcategory="weapon_visible", duration_s=2.0,
                           sha256="c1" + "0" * 62, session_id="sess-b1",
                           labels_extra={"class": "weapon",
                                         "boxes": [{"frame_time_s": 1.0, "class": "weapon",
                                                    "bbox": [0.0, 0.0, 10.0, 10.0]}]})
    out_with = make_output("box-1", "c1" + "0" * 62, detections=[
        {"time_s": 1.05, "class": "weapon", "score": 0.9, "bbox": [0.0, 0.0, 10.0, 10.0]}])
    out_without_boxes = make_fixture("box-2", category="positive", subcategory="weapon_visible",
                                     duration_s=2.0, sha256="d1" + "0" * 62, session_id="sess-b2",
                                     labels_extra={"class": "weapon"})
    result = metrics.box_level_metrics([(fixture, out_with)], "weapon")
    assert result["ap50"] == pytest.approx(1.0) and result["gt_boxes"] == 1
    # IoU below 0.5 -> no match -> AP 0
    out_low_iou = make_output("box-1", "c1" + "0" * 62, detections=[
        {"time_s": 1.05, "class": "weapon", "score": 0.9, "bbox": [8.0, 8.0, 18.0, 18.0]}])
    assert metrics.box_level_metrics([(fixture, out_low_iou)], "weapon")["ap50"] == 0.0
    # Without boxes: unavailable with the exact reason, never an estimate
    unavailable = metrics.box_level_metrics(
        [(out_without_boxes, make_output("box-2", "d1" + "0" * 62))], "weapon")
    assert unavailable["ap50"] is None
    assert unavailable["reason"] == "no box-level ground truth in fixtures"


def test_contract_validates_box_labels():
    fixture = make_fixture("boxv-1", category="positive", subcategory="weapon_visible", duration_s=2.0,
                           sha256="e1" + "0" * 62, session_id="sess-bv1",
                           labels_extra={"class": "weapon",
                                         "boxes": [{"frame_time_s": 3.0, "class": "weapon",
                                                    "bbox": [0.0, 0.0, 1.0, 1.0]}]})
    with pytest.raises(ContractError, match="frame_time_s"):
        load_manifest_json(_manifest_document([fixture]))


def test_outputs_from_two_passes_merge_per_fixture(tmp_path):
    fixture = make_fixture("mrg-1", category="negative", subcategory="walking", duration_s=2.0,
                           sha256="a4" + "0" * 62, session_id="sess-mrg")
    manifest = load_manifest_json(_manifest_document([fixture]))
    pass1 = make_output("mrg-1", "a4" + "0" * 62, windows=[window(0, 1, 0.2)])
    pass1["run_id"] = "anchor-pass1"
    pass2 = make_output("mrg-1", "a4" + "0" * 62,
                        tracks=[{"time_s": 0.5, "track_id": 3, "bbox": [0, 0, 2, 2]}])
    pass2["run_id"] = "anchor-pass2"
    pass2["producer"] = {"pass": 2}
    dir1, dir2 = tmp_path / "p1", tmp_path / "p2"
    dir1.mkdir(), dir2.mkdir()
    (dir1 / "mrg-1.json").write_text(json.dumps(pass1), encoding="utf-8")
    (dir2 / "mrg-1.json").write_text(json.dumps(pass2), encoding="utf-8")
    rows = load_outputs(manifest, f"{dir1},{dir2}")
    assert len(rows) == 1
    assert rows[0]["windows"] and rows[0]["tracks"]
    assert rows[0]["run_ids"] == ["anchor-pass1", "anchor-pass2"]
    # scalar disagreement on a field both passes carry is rejected, never silently kept
    pass1_bad = dict(pass1, producer={"pass": 1})
    pass2_bad = dict(pass2, producer={"pass": 99})
    (dir1 / "mrg-1.json").write_text(json.dumps(pass1_bad), encoding="utf-8")
    (dir2 / "mrg-1.json").write_text(json.dumps(pass2_bad), encoding="utf-8")
    with pytest.raises(ContractError, match="conflicting"):
        load_outputs(manifest, f"{dir1},{dir2}")
