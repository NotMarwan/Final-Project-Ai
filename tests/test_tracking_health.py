"""S-04 / WT-22 scoped tests: no-GT tracking health from WT-12 fixture outputs.

Identity ground truth is absent in the WT-12 suite, so HOTA/IDF1 are unmeasurable
there; these tests lock the health-only contract (id churn, dropout/recovery,
merge/area suspicion), the loud validation of untrustworthy outputs, and the
report shape (slices + denominators + unavailable_metrics).
"""
from __future__ import annotations

import json

import pytest

import eval_tracking as ev


def outputs(fixture_id: str = "kth-walking-01", tracks: list | None = None,
            source_mode: str = "file-media") -> dict:
    return {
        "fixture_id": fixture_id,
        "source_sha256": "a" * 64,
        "run_id": "campaign-baseline-2026-09-29",
        "source_mode": source_mode,
        "windows": [{"start_s": 0.0, "end_s": 1.0}],
        "detections": [],
        "alerts": [],
        "tracks": tracks if tracks is not None else [
            {"time_s": 0.0, "track_id": 1, "bbox": [0, 0, 10, 20]},
            {"time_s": 0.1, "track_id": 1, "bbox": [1, 0, 11, 20]},
            {"time_s": 0.2, "track_id": 1, "bbox": [2, 0, 12, 20]},
        ],
    }


def write(tmp_path, name: str, payload: dict) -> str:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_clean_tracks_have_no_health_suspicion(tmp_path):
    path = write(tmp_path, "clean", outputs())
    health = ev.tracking_health(ev.load_run_outputs(path))
    assert health["denominators"] == {"rows": 3, "unique_track_ids": 1, "timestamps": 3,
                                      "windows": 1, "duration_s": 0.2}
    assert health["metrics"]["transient_id_rate"] == 0.0
    assert health["metrics"]["dropout_events_per_track"] == 0.0
    assert health["metrics"]["reentry_events_per_track"] == 0.0
    assert health["metrics"]["merge_suspicion_frame_rate"] == 0.0
    assert health["metrics"]["area_jump_events_per_track"] == 0.0
    assert health["metrics"]["active_track_count_median"] == 1.0


def test_dropout_reentry_transient_and_merge_are_counted(tmp_path):
    tracks = [
        # id 1 drops out for 1 s (3 rows then a 1 s gap) -> dropout + re-entry
        {"time_s": 0.0, "track_id": 1, "bbox": [0, 0, 10, 20]},
        {"time_s": 0.1, "track_id": 1, "bbox": [0, 0, 10, 20]},
        {"time_s": 1.2, "track_id": 1, "bbox": [0, 0, 10, 20]},
        # id 2 appears once -> transient
        {"time_s": 0.1, "track_id": 2, "bbox": [50, 0, 60, 20]},
        # id 3 changes scale by > 1.8x between rows -> area jump
        {"time_s": 0.1, "track_id": 3, "bbox": [100, 0, 110, 20]},
        {"time_s": 0.2, "track_id": 3, "bbox": [100, 0, 140, 20]},
        # ids 4 and 5 overlap at t=0.2 -> merge suspicion frame
        {"time_s": 0.2, "track_id": 4, "bbox": [200, 0, 230, 40]},
        {"time_s": 0.2, "track_id": 5, "bbox": [201, 1, 231, 41]},
    ]
    health = ev.tracking_health(ev.load_run_outputs(write(tmp_path, "messy", outputs(tracks=tracks))))
    metrics = health["metrics"]
    assert metrics["dropout_events_per_track"] == pytest.approx(1 / 5)
    assert metrics["reentry_events_per_track"] == 0.0  # 1.1 s gap < the 2 s re-entry bar
    # ids 2, 4 and 5 appear in a single row each
    assert metrics["transient_id_rate"] == pytest.approx(3 / 5)
    assert metrics["id_churn_proxy_per_track"] == pytest.approx(3 / 5)
    assert metrics["area_jump_events_per_track"] == pytest.approx(1 / 5)
    assert metrics["merge_suspicion_frame_rate"] == pytest.approx(1 / 4)
    assert metrics["active_track_count_max"] == 3  # t=0.2 holds ids 3, 4 and 5


def test_reentry_threshold_is_applied(tmp_path):
    tracks = [
        {"time_s": 0.0, "track_id": 7, "bbox": [0, 0, 10, 20]},
        {"time_s": 3.5, "track_id": 7, "bbox": [0, 0, 10, 20]},
    ]
    health = ev.tracking_health(ev.load_run_outputs(write(tmp_path, "reenter", outputs(tracks=tracks))))
    assert health["metrics"]["reentry_events_per_track"] == 1.0
    assert health["thresholds"]["reentry_gap_s"] == ev.REENTRY_GAP_SECONDS


def test_outputs_that_cannot_be_trusted_are_rejected_loudly(tmp_path):
    with pytest.raises(ValueError, match="missing required output keys"):
        ev.load_run_outputs(write(tmp_path, "missing", {"fixture_id": "x"}))
    with pytest.raises(ValueError, match="refusing source_mode"):
        ev.load_run_outputs(write(tmp_path, "live", outputs(source_mode="live")))
    with pytest.raises(ValueError, match="source_sha256 is required"):
        ev.load_run_outputs(write(tmp_path, "nohash", {**outputs(), "source_sha256": ""}))
    with pytest.raises(ValueError, match="malformed track row"):
        ev.load_run_outputs(write(tmp_path, "badrow", outputs(tracks=[{"time_s": 0.0, "track_id": 1}])))
    with pytest.raises(ValueError, match="malformed track row"):
        ev.load_run_outputs(write(tmp_path, "badid",
                                  outputs(tracks=[{"time_s": 0.0, "track_id": "1", "bbox": [0, 0, 1, 1]}])))


def test_report_shape_matches_the_wt12_contract(tmp_path):
    paths = [write(tmp_path, "a", outputs("kth-walking-01")),
             write(tmp_path, "b", outputs("kth-boxing-01", tracks=[
                 {"time_s": 0.0, "track_id": 1, "bbox": [0, 0, 10, 20]},
                 {"time_s": 1.5, "track_id": 1, "bbox": [0, 0, 10, 20]},
                 {"time_s": 1.6, "track_id": 2, "bbox": [40, 0, 50, 20]},
             ]))]
    report = ev.tracking_health_report(paths, run_id="campaign-baseline-2026-09-29")
    assert report["schema"] == ev.HEALTH_SCHEMA
    assert report["source_mode"] == "file-media"
    assert report["run_id"] == "campaign-baseline-2026-09-29"
    assert len(report["fixtures"]) == 2
    slice_entry = report["slices"]["dropout_events_per_track"]
    assert slice_entry["denominator"]["sessions"] == 2
    assert slice_entry["denominator"]["rows"] == 6
    assert slice_entry["bootstrap_unit"] == "session"
    assert slice_entry["bootstrap_is_indicative_only"] is True  # < 3 sessions
    assert set(slice_entry["per_fixture"]) == {"kth-walking-01", "kth-boxing-01"}
    assert "HOTA" in report["unavailable_metrics"] and "IDF1" in report["unavailable_metrics"]
    assert "never tracking accuracy" in report["labels"]


def test_bootstrap_is_seeded_and_deterministic(tmp_path):
    paths = [write(tmp_path, f"f{index}", outputs(f"fixture-{index}")) for index in range(3)]
    first = ev.tracking_health_report(paths, seed=20260929)
    second = ev.tracking_health_report(paths, seed=20260929)
    assert first["slices"]["merge_suspicion_frame_rate"]["bootstrap"] == \
           second["slices"]["merge_suspicion_frame_rate"]["bootstrap"]


def test_health_cli_reads_the_wt12_outputs_layout(tmp_path):
    outputs_dir = tmp_path / "bench" / "results" / "campaign-baseline-2026-09-29" / "outputs"
    outputs_dir.mkdir(parents=True)
    (outputs_dir / "kth-walking-01.json").write_text(json.dumps(outputs()), encoding="utf-8")
    (outputs_dir / "notes.txt").write_text("ignored", encoding="utf-8")
    paths = ev.health_cli_outputs_dir(outputs_dir)
    assert len(paths) == 1 and paths[0].endswith("kth-walking-01.json")
    report_path = tmp_path / "health.json"
    assert ev.main(["--outputs-dir", str(outputs_dir), "--health-report", str(report_path)]) == 0
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written["slices"]["transient_id_rate"]["value"] == 0.0
    with pytest.raises(FileNotFoundError, match="outputs directory not found"):
        ev.health_cli_outputs_dir(tmp_path / "missing")


def test_health_report_requires_the_outputs_directory():
    with pytest.raises(SystemExit):
        ev.main(["--health-report", "whatever.json"])
