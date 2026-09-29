"""WT-19 → WT-12 recorded-outputs adapter tests (S-02 scoped).

Pins the mapping onto WT-12's `bench/eval/contracts.py::load_outputs` contract
without depending on the other worktree: fixture_id/source_sha256/source_mode
plus windows[].start_s/end_s/violence_conf, and the runtime_contract's
window_integrity_fields carried additively.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wt19_sweep_harness as harness  # noqa: E402

SHA_A = "a" * 64
SHA_B = "b" * 64


def _fixture(fixture_id, path, sha):
    return {
        "fixture_id": fixture_id,
        "category": "negative",
        "subcategory": "walking",
        "split": "test",
        "session_id": f"session-{fixture_id}",
        "media": {"path": path, "sha256": sha, "bytes": 1024, "duration_s": 1.0,
                  "fps": 25.0, "width": 160, "height": 120, "frame_count": 25},
        "source": {"publisher": "KTH", "licence": "non-commercial"},
    }


def _manifest():
    return {
        "schema_version": "wt12-fixture-manifest/1",
        "media_root": "X:/fixtures",
        "policy": {"label_provenance_allowed": ["independent-human", "publisher"],
                   "label_provenance_forbidden": ["auto", "model", "pseudo", "synthetic"]},
        "fixtures": [
            _fixture("kth-walking-01", "walking/person01_walking_d1.avi", SHA_A),
            _fixture("kth-handwaving-02", "handwaving/person02_handwaving.avi", SHA_B),
        ],
        "unavailable_categories": [
            {"category": "negative/hugging", "attempted_sources": ["KTH Actions"],
             "why_excluded": "no lawful corpus"},
        ],
    }


def _row(clip, window_id, start, end, conf, **overrides):
    row = {
        "clip_id": clip,
        "window_id": window_id,
        "window_start_timestamp": start,
        "window_end_timestamp": end,
        "raw_conf": conf,
        "calibrated_conf": conf,
        "smoothed_conf": conf,
        "logit_margin": 0.5,
        "ensemble_k": 3,
        "ensemble_score": conf,
        "ensemble_spread": 0.1,
        "motion_energy": 2.0,
        "motion_gated": False,
        "window_valid": True,
        "window_frames_collected": 32,
        "window_frames_required": 32,
        "window_span_seconds": end - start,
    }
    row.update(overrides)
    return row


def _scores(rows):
    return {
        "code_sha": "deadbeef", "weights_sha256": "c" * 64,
        "window": 32, "stride": 16, "ensemble_k": 3, "ensemble_agg": "max",
        "motion_gate": "off", "motion_floor": 1.0, "threshold": 0.45,
        "source_mode": "file-media (demo AVIs, UNLABELLED — no accuracy/FP claims)",
        "window_scores": rows,
    }


def test_maps_rows_onto_contract_fields_and_sorts_windows():
    rows = [
        _row("person02_handwaving.avi", 8, 1.28, 2.56, 0.9),
        _row("person01_walking_d1.avi", 1, 0.0, 1.28, 0.1),
        _row("person01_walking_d1.avi", 2, 0.64, 1.92, 0.2),
    ]
    payloads, unmatched = harness.build_fixture_outputs(_manifest(), _scores(rows), "run-42")
    assert unmatched == []
    assert [p["fixture_id"] for p in payloads] == ["kth-handwaving-02", "kth-walking-01"]
    by_id = {p["fixture_id"]: p for p in payloads}
    walk = by_id["kth-walking-01"]
    assert walk["source_sha256"] == SHA_A
    assert walk["source_mode"] == "file-media"
    assert walk["run_id"] == "run-42"
    assert walk["detections"] == [] and walk["alerts"] == [] and walk["tracks"] == []
    windows = walk["windows"]
    assert [w["start_s"] for w in windows] == [0.0, 0.64], "windows must be sorted by start_s"
    for w in windows:
        assert w["end_s"] > w["start_s"] >= 0.0
        assert 0.0 <= w["violence_conf"] <= 1.0
        # runtime_contract window_integrity_fields carried additively
        assert w["valid"] is True and w["frames_collected"] == 32 and w["frames_required"] == 32
        assert w["span_s"] == pytest.approx(w["end_s"] - w["start_s"])
        assert w["ensemble_k"] == 3 and w["ensemble_spread"] == pytest.approx(0.1)
    assert by_id["kth-handwaving-02"]["source_sha256"] == SHA_B
    assert walk["producer"]["score_semantics"].startswith("violence_conf = EMA-smoothed")


def test_unmatched_clips_are_reported_not_silently_dropped():
    rows = [_row("unknown_clip.avi", 1, 0.0, 1.0, 0.5)]
    payloads, unmatched = harness.build_fixture_outputs(_manifest(), _scores(rows), "run-1")
    assert payloads == []
    assert unmatched == ["unknown_clip.avi"]


def test_full_path_clip_id_also_matches():
    rows = [_row("walking/person01_walking_d1.avi", 1, 0.0, 1.28, 0.3)]
    payloads, unmatched = harness.build_fixture_outputs(_manifest(), _scores(rows), "run-1")
    assert unmatched == [] and payloads[0]["fixture_id"] == "kth-walking-01"


def test_degenerate_or_unscored_windows_are_dropped():
    rows = [
        _row("person01_walking_d1.avi", 1, 0.0, 1.28, 0.3),
        _row("person01_walking_d1.avi", 2, 1.5, 1.5, 0.3),          # empty interval
        _row("person01_walking_d1.avi", 3, 2.5, 1.5, 0.3),          # inverted interval
        {"clip_id": "person01_walking_d1.avi", "window_id": 4,
         "window_start_timestamp": 2.0, "window_end_timestamp": 3.0},  # no score at all
    ]
    payloads, _ = harness.build_fixture_outputs(_manifest(), _scores(rows), "run-1")
    assert [w["window_id"] for w in payloads[0]["windows"]] == [1]


def test_scores_are_clipped_and_fall_back_to_ensemble_score():
    rows = [
        _row("person01_walking_d1.avi", 1, 0.0, 1.0, 1.4, smoothed_conf=None, ensemble_score=0.75),
        _row("person01_walking_d1.avi", 2, 1.0, 2.0, -0.2),
    ]
    payloads, _ = harness.build_fixture_outputs(_manifest(), _scores(rows), "run-1")
    got = {w["window_id"]: w["violence_conf"] for w in payloads[0]["windows"]}
    assert got[1] == pytest.approx(0.75)   # falls back to ensemble_score, clipped to <= 1
    assert got[2] == pytest.approx(0.0)


def test_cli_fails_strict_on_unmatched_and_writes_files(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"
    scores_path = tmp_path / "scores.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    scores_path.write_text(json.dumps(_scores([
        _row("person01_walking_d1.avi", 1, 0.0, 1.28, 0.2),
        _row("stray.avi", 2, 0.0, 1.28, 0.2),
    ])), encoding="utf-8")
    out_dir = tmp_path / "outputs"

    monkeypatch.setattr(sys, "argv", [
        "wt19_sweep_harness.py", "--out", str(tmp_path / "report.json"), "to-fixture-outputs",
        "--manifest", str(manifest_path), "--scores", str(scores_path),
        "--out-dir", str(out_dir), "--run-id", "run-strict",
    ])
    with pytest.raises(SystemExit):
        harness.main()
    assert (out_dir / "kth-walking-01.json").is_file(), "matched fixture is written before the strict failure"

    monkeypatch.setattr(sys, "argv", [
        "wt19_sweep_harness.py", "--out", str(tmp_path / "report.json"), "to-fixture-outputs",
        "--manifest", str(manifest_path), "--scores", str(scores_path),
        "--out-dir", str(out_dir), "--run-id", "run-lenient", "--no-strict",
    ])
    assert harness.main() == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["strict_ok"] is False
    assert report["strict_enforced"] is False
    assert report["unmatched_clips"] == ["stray.avi"]
    assert report["n_fixtures_written"] == 1
