"""S-04 / WT-22 scoped tests: async incident capture queue (the alert-path proof)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest

import capture_queue
from capture_queue import IncidentCapture, PreEventRing
from frame_reference import hash_array_raw


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def frame(value: int = 40, *, sharp: bool = False) -> np.ndarray:
    """A small BGR frame; `sharp` gives a high-variance pattern for the scorer."""
    array = np.full((48, 64, 3), value, dtype=np.uint8)
    if sharp:
        checker = np.indices((32, 48)).sum(axis=0) % 2
        array[8:40, 8:56] = np.clip(128 + (checker * 120 - 60)[..., None], 0, 255).astype(np.uint8)
    return array


def test_ring_samples_at_the_configured_cadence_and_prunes_by_time():
    ring = PreEventRing(max_seconds=5.0, sample_fps=4.0, native_fps=0.0, native_max_frames=0)
    stored = [ring.add(1000.0 + index * 0.05, frame(index)) is not None for index in range(40)]
    # 40 frames span 2 s of input; a 4 fps ring keeps one frame per 0.25 s.
    assert sum(stored) == 8
    assert ring.stats()["entries"] <= 21
    window = ring.snapshot(1000.0, 1002.0)
    assert window and window[0].captured_at >= 1000.0
    assert all(entry.frame is not None for entry in window)


def test_ring_keeps_a_bounded_native_sample():
    ring = PreEventRing(max_seconds=10.0, sample_fps=10.0, native_fps=1.0, native_max_frames=3)
    for index in range(50):
        ring.add(1000.0 + index * 0.1, frame(index), native_frame=frame(index, sharp=True))
    stats = ring.stats()
    assert stats["native_entries"] <= 3
    assert stats["native_entries"] >= 1


def test_record_hash_and_dimensions_refer_to_the_same_sampled_pixels():
    clock = FakeClock()
    sampled = frame(30)
    native = np.full((96, 128, 3), 90, dtype=np.uint8)
    capture = IncidentCapture(pre_seconds=1.0, post_seconds=0.0, clock=clock,
                              camera_id="CAM-1", start_worker=False)
    capture.feed(clock.now, sampled, frame_sequence=7, native_frame=native)
    capture.trigger("alert-native", alert_time=clock.now)
    record = capture._build_record(capture._jobs[0])
    capture.stop()

    best = record["best"]
    assert best["width"] == sampled.shape[1]
    assert best["height"] == sampled.shape[0]
    assert best["hash_format"] == "raw-uint8-48x64x3"
    assert best["frame_sha256"] == hash_array_raw(sampled)[0]
    assert best["native_frame"]["width"] == native.shape[1]
    assert best["native_frame"]["height"] == native.shape[0]
    assert best["native_frame"]["sha256"] == hash_array_raw(native)[0]


def test_record_declares_post_window_truncated_when_capture_stalls():
    clock = FakeClock()
    capture = IncidentCapture(pre_seconds=1.0, post_seconds=5.0, clock=clock,
                              camera_id="CAM-1", start_worker=False)
    capture.feed(clock.now, frame(30))
    capture.trigger("alert-stalled", alert_time=clock.now)
    clock.now += 5.0
    record = capture._build_record(capture._jobs[0])

    assert record["capture_status"] == "partial"
    assert record["window"]["post_window_status"] == "truncated"
    assert record["window"]["post_window_truncated"] is True
    assert record["window"]["post_window_endpoint_reached"] is False
    assert record["window"]["post_window_truncation_reason"] == "capture-ended-before-post-deadline"
    capture.stop()


def test_media_epoch_end_finalizes_pending_records_and_clears_old_pre_event_frames():
    clock = FakeClock()
    capture = IncidentCapture(pre_seconds=2.0, post_seconds=5.0, clock=clock,
                              camera_id="CAM-1", start_worker=False)
    capture.feed(clock.now, frame(30), frame_sequence=1)
    clock.now += 1.0
    capture.feed(clock.now, frame(31), frame_sequence=2)
    capture.trigger("alert-loop-end", alert_time=clock.now)

    assert capture.end_epoch("media-loop-boundary") == 1
    assert capture.ring.stats()["entries"] == 0
    job = capture._jobs[0]
    assert job.state == "pending"
    assert job.force_finalize is True
    record = capture._build_record(capture._jobs[0])
    assert record["capture_status"] == "partial"
    assert record["window"]["post_window_truncated"] is True
    assert record["window"]["post_window_truncation_reason"] == "media-loop-boundary"
    assert record["window"]["last_capture_at"] == clock.now

    clock.now += 1.0
    capture.feed(clock.now, frame(32), frame_sequence=1)
    assert job.post_entries == []
    assert capture.ring.stats()["entries"] == 1
    capture.stop()


def test_media_epoch_end_delivers_a_partial_record_for_pending_incident():
    clock = FakeClock()
    completed = []
    done = threading.Event()

    def on_complete(record):
        completed.append(record)
        done.set()

    capture = IncidentCapture(pre_seconds=1.0, post_seconds=5.0, clock=clock,
                              camera_id="CAM-1", on_complete=on_complete)
    capture.feed(clock.now, frame(30), frame_sequence=1)
    capture.trigger("alert-loop-pending", alert_time=clock.now)
    assert capture.end_epoch("media-loop-boundary") == 1

    assert done.wait(1.0)
    assert completed[0]["capture_status"] == "partial"
    assert completed[0]["window"]["post_window_truncation_reason"] == "media-loop-boundary"
    assert capture.status()["last_selection"]["capture_status"] == "partial"
    capture.stop()


def test_trigger_enqueues_without_running_any_scoring(tmp_path, monkeypatch):
    """The alert path must not do capture work: sabotage the scorer and prove
    trigger() still succeeds, then prove the failure stayed inside the worker."""
    calls = {"count": 0}

    def exploding_scorer(*args, **kwargs):
        calls["count"] += 1
        raise RuntimeError("scorer must never run on the alert path")

    monkeypatch.setattr(capture_queue.best_frame, "select_best", exploding_scorer)
    clock = FakeClock()
    capture = IncidentCapture(pre_seconds=10.0, post_seconds=5.0, clock=clock, camera_id="CAM-1")
    for index in range(20):
        capture.feed(clock.now + index * 0.25, frame(index))
    started = time.perf_counter()
    status = capture.trigger("alert-1", alert_time=clock.now + 4.0)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert status["state"] == "pending"
    assert calls["count"] == 0, "scoring ran on the alert path"
    assert elapsed_ms < 100.0, f"trigger took {elapsed_ms:.1f} ms"

    clock.now += 6.0
    assert capture.wait_for_idle(5.0) is True
    assert calls["count"] == 1, "the worker should have attempted the selection"
    assert capture.status()["failed"] == 1, "worker failure must be recorded, not swallowed"
    assert capture.status()["state"] == "idle"
    capture.stop()


def test_queue_is_bounded_and_drops_oldest_with_telemetry():
    clock = FakeClock()
    capture = IncidentCapture(pre_seconds=1.0, post_seconds=5.0, queue_capacity=3,
                              clock=clock, camera_id="CAM-1", start_worker=False)
    for index in range(12):
        clock.now = 1000.0 + index
        capture.trigger(f"alert-{index}", alert_time=clock.now)
    status = capture.status()
    assert status["pending"] == 3
    assert status["dropped_jobs"] == 9
    assert status["state"] == "pending"
    capture.stop(timeout=0.1)


def test_post_window_collection_is_bounded_and_reports_drops():
    clock = FakeClock()
    capture = IncidentCapture(pre_seconds=1.0, post_seconds=5.0, clock=clock,
                              camera_id="CAM-1", start_worker=False,
                              max_post_frames_per_job=4)
    capture.feed(clock.now, frame(0))
    capture.trigger("alert-1", alert_time=clock.now)
    for index in range(10):
        clock.now += 0.25
        capture.feed(clock.now, frame(index + 1))
    job = capture._jobs[0]
    assert len(job.post_entries) == 4
    assert job.dropped_post_frames == 6
    assert capture.status()["dropped_frames"] == 6
    capture.stop(timeout=0.1)


def test_capture_pending_status_contract_for_the_incident_view():
    clock = FakeClock()
    capture = IncidentCapture(pre_seconds=1.0, post_seconds=2.0, clock=clock,
                              camera_id="CAM-1", start_worker=False)
    assert capture.status()["state"] == "idle"
    capture.feed(clock.now, frame(0))
    pending = capture.trigger("alert-9", alert_time=clock.now)
    assert pending["state"] == "pending" and pending["pre_candidates"] == 1
    assert capture.status()["state"] == "pending"
    capture.stop(timeout=0.1)


def test_selection_record_carries_sc6_timestamps_sc8_parents_and_the_worker_thread(tmp_path):
    clock = FakeClock()
    completed = []
    capture = IncidentCapture(pre_seconds=10.0, post_seconds=1.0, clock=clock, camera_id="CAM-1",
                              record_dir=tmp_path, on_complete=completed.append)
    for index in range(40):
        capture.feed(clock.now + index * 0.25, frame(index, sharp=(index == 20)))
    alert_time = clock.now + 10.0
    capture.trigger("alert-42", alert_time=alert_time)
    for index in range(5):
        capture.feed(alert_time + 0.2 * (index + 1), frame(100 + index))
    clock.now += 2.0
    assert capture.wait_for_idle(5.0)
    capture.stop()

    assert len(completed) == 1
    record = completed[0]
    assert record["schema"] == "sentinel.best_frame_record/v1"
    assert record["alert_id"] == "alert-42"
    assert record["scoring"]["scoring_thread"].startswith("capture-")
    assert record["scoring"]["trigger_thread"] != record["scoring"]["scoring_thread"]
    assert record["best"]["captured_at"] is not None
    assert record["best"]["iso_time"] and record["best"]["frame_sha256"]
    assert len(record["parents"]) == record["window"]["candidates"]
    assert record["window"]["pre_candidates"] >= 1 and record["window"]["post_candidates"] >= 1
    assert record["policy"]["identity_recognition"] is False
    assert record["score_vector"]["total"] > 0
    written = json.loads((tmp_path / "alert-42.json").read_text(encoding="utf-8"))
    assert written["best"]["frame_id"] == record["best"]["frame_id"]
    assert not (tmp_path / "alert-42.json.part").exists()


def test_selection_prefers_the_clearest_frame_in_the_pre_event_window():
    clock = FakeClock()
    completed = []
    capture = IncidentCapture(pre_seconds=10.0, post_seconds=1.0, clock=clock, camera_id="CAM-1",
                              on_complete=completed.append)
    sharp_at = clock.now + 30 * 0.25
    for index in range(40):
        capture.feed(clock.now + index * 0.25, frame(0 if index != 30 else 60, sharp=(index == 30)))
    assert capture.trigger("alert-sharp", alert_time=clock.now + 10.0)["pre_candidates"] > 0
    clock.now += 2.0
    assert capture.wait_for_idle(5.0)
    capture.stop()
    record = completed[0]
    assert record["score_vector"]["axes"]["sharpness"] > 0.9
    assert record["best"]["captured_at"] == pytest.approx(sharp_at)
    assert record["best"]["frame_id"] == f"CAM-1:{record['best']['frame_sequence']}"


def test_face_crops_are_emitted_as_camerascoped_crop_refs_without_identity_claims():
    clock = FakeClock()
    completed = []
    capture = IncidentCapture(pre_seconds=5.0, post_seconds=0.0, clock=clock, camera_id="CAM-1",
                              on_complete=completed.append)
    capture.feed(clock.now, frame(0, sharp=True))
    capture.trigger("alert-face", alert_time=clock.now)
    clock.now += 1.0
    assert capture.wait_for_idle(5.0)
    capture.stop()
    # The scorer emits crop refs only for faces it was given; with no face input
    # the record must say so rather than inventing subjects.
    assert completed[0]["crop_refs"] == []
    assert completed[0]["score_vector"]["selected_face_index"] is None
    assert completed[0]["score_vector"]["occlusion_source"] in {"unavailable", "bbox_frame_clip_fraction"}


def test_crop_refs_from_a_supplied_face_carry_namespaced_track_and_parent_hash():
    clock = FakeClock()
    completed = []
    capture = IncidentCapture(pre_seconds=5.0, post_seconds=0.0, clock=clock, camera_id="CAM-1",
                              on_complete=completed.append)
    entry = capture.ring.add(clock.now, frame(0, sharp=True))
    face = {"bbox_xyxy": [10, 10, 30, 30], "ied_px": 40.0, "yaw_proxy_deg": 5.0, "occluded_fraction": 0.0}
    capture.trigger("alert-crops", alert_time=clock.now)
    job = capture._jobs[0]
    job.pre_entries[0].frame_sha256 = None  # force hashing through ensure_hash
    reference = {
        "camera_id": "CAM-1", "frame_sequence": 5, "captured_at": clock.now,
        "iso_time": "2026-01-01T00:00:00Z", "frame_sha256": "a" * 64,
        "hash_format": "raw-uint8-48x64x3", "sample_timestamp": None,
    }
    refs = capture._crop_refs(job, reference, capture_queue.best_frame.score_frame(entry.frame, [face]))
    assert len(refs) == 1
    assert refs[0]["schema"] == "sentinel.crop_ref/v1"
    assert refs[0]["crop_id"] == "CAM-1:5:face:0"
    assert refs[0]["bbox_space"] == "model_input"
    assert refs[0]["source_frame_sha256"] == "a" * 64
    assert refs[0]["is_derivative"] is False
    capture.stop(timeout=0.1)


def test_feed_reports_whether_a_frame_was_stored():
    ring = PreEventRing(max_seconds=5.0, sample_fps=2.0, native_fps=0.0, native_max_frames=0)
    assert ring.add(1000.0, frame(0)) is not None
    assert ring.add(1000.1, frame(1)) is None  # inside the sample interval
    assert ring.add(1000.6, frame(2)) is not None


def test_capture_never_blocks_the_caller_while_the_worker_is_busy():
    """A stalled worker must not slow the capture loop or the alert path."""
    clock = FakeClock()
    gate = threading.Event()

    def slow_complete(record):
        gate.wait(2.0)

    capture = IncidentCapture(pre_seconds=1.0, post_seconds=0.0, clock=clock, camera_id="CAM-1",
                              on_complete=slow_complete)
    capture.feed(clock.now, frame(0))
    capture.trigger("alert-slow", alert_time=clock.now)
    clock.now += 0.5
    durations = []
    for index in range(20):
        started = time.perf_counter()
        capture.feed(clock.now + index * 0.05, frame(index))
        durations.append((time.perf_counter() - started) * 1000)
    assert max(durations) < 50.0, f"feed blocked for {max(durations):.1f} ms"
    gate.set()
    capture.wait_for_idle(5.0)
    capture.stop()


def test_missing_config_file_falls_back_to_documented_defaults(tmp_path):
    config = capture_queue.best_frame.load_config(Path("config/best_frame.toml"))
    assert abs(sum(config.weights.values()) - 1.0) < 1e-9
    assert config.pre_seconds == 10.0 and config.post_seconds == 5.0


def test_a_malformed_weight_block_is_rejected():
    with pytest.raises(ValueError, match="sum to 1.0"):
        capture_queue.best_frame.BestFrameConfig.from_dict({"best_frame": {"w_sharpness": 0.5}})
    with pytest.raises(ValueError, match="\\[best_frame\\] table"):
        capture_queue.best_frame.BestFrameConfig.from_dict({})
