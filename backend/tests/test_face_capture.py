"""Scoped contracts for incident face capture: association ambiguity cases,
multi-camera non-association, SC-8 derivative records, health/absent states,
and the async non-blocking dispatch-path proof. No identity assertions exist
in this module or in the code under test — by campaign policy."""
import queue
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from face_capture import (FACE_ASSOC_META, FaceAssocEngine, FaceCaptureService,
                          FaceDerivativeLedger, build_derivative_record,
                          note_incident_blocking, roundtrip_ok, scale_box_to_source)
from face_detect import FaceDetection

# exact WT-23 derivative record contract (agreed with ImageEnhancement 2026-09-29)
REQUIRED_DERIVATIVE_KEYS = {
    "recordType", "derivativeId", "alertId", "cameraId", "timestamp", "producedAt",
    "parentKind", "parentPath", "parentSha256", "parentCapturedAt",
    "parentSampleTimestamp", "subjectRef", "derivativePath", "derivativeSha256",
    "derivativeFormat", "tier", "derivationBasis", "operations", "model",
    "libraryVersions", "operator", "isEnhanced", "label", "labelText",
    "labelLocations", "uiContract", "harness",
}


def make_face(box, index=0):
    return FaceDetection(bbox_xyxy=tuple(box), score=0.9,
                         landmarks_5pt=tuple((0.0, 0.0) for _ in range(5)),
                         ied_px=25.0, yaw_proxy_deg=0.0, face_index=index)


class StubDetector:
    """Configurable detector stub with an explicit health surface."""

    def __init__(self, faces=None, status="loaded", delay=0.0):
        self.faces = faces or []
        self.status = status
        self.delay = delay
        self.calls = []
        self.lock = threading.Lock()

    def health(self):
        return {"status": self.status, "reason": "" if self.status == "loaded" else "stub",
                "model_path": None, "model_sha256": None, "input_size": None}

    def detect(self, frame):
        with self.lock:
            self.calls.append(threading.current_thread().name)
        if self.delay:
            time.sleep(self.delay)
        return list(self.faces)


def frame_entry(ts, size=(120, 160)):
    return (ts, np.zeros((size[0], size[1], 3), dtype=np.uint8))


# ---------------------------------------------------------------- association
def test_association_single_contained_track():
    engine = FaceAssocEngine()
    face = {"bbox_xyxy_source": [45.0, 10.0, 55.0, 25.0], "face_index": 0}
    track = {"track_id": 7, "bbox": [30.0, 0.0, 70.0, 100.0]}
    out = engine.associate_frame(camera_id="camA", faces=[face], tracks=[track], captured_at=1.0)
    assert len(out) == 1
    entry = out[0]
    assert entry["track_id"] == "camA::7"          # namespaced per camera
    assert entry["ambiguous"] is False
    assert "face_box_contained_in_person_box" in entry["reasons"]
    assert "face_in_upper_person_region" in entry["reasons"]
    assert "proximity_not_causation" in entry["reasons"]
    assert 0.0 <= entry["confidence"] <= 1.0
    assert entry["confidence_semantics"] == "heuristic_uncalibrated"


def test_association_two_candidate_tracks_is_ambiguous_never_silent():
    engine = FaceAssocEngine()
    face = {"bbox_xyxy_source": [45.0, 10.0, 55.0, 25.0], "face_index": 0}
    tracks = [{"track_id": 1, "bbox": [30.0, 0.0, 70.0, 100.0]},
              {"track_id": 2, "bbox": [35.0, 0.0, 75.0, 100.0]}]
    out = engine.associate_frame(camera_id="camA", faces=[face], tracks=tracks, captured_at=1.0)
    entry = out[0]
    assert entry["ambiguous"] is True
    assert entry["track_id"] is None               # NEVER pick one silently
    assert sorted(entry["candidate_track_ids"]) == ["camA::1", "camA::2"]
    assert "multiple_candidate_tracks" in entry["reasons"]


def test_association_no_candidate_track():
    engine = FaceAssocEngine()
    face = {"bbox_xyxy_source": [500.0, 500.0, 520.0, 530.0], "face_index": 0}
    out = engine.associate_frame(camera_id="camA", faces=[face], tracks=[], captured_at=1.0)
    entry = out[0]
    assert entry["track_id"] is None
    assert entry["ambiguous"] is False
    assert "no_candidate_track" in entry["reasons"]


def test_association_temporal_co_occurrence_across_frames_with_motion():
    engine = FaceAssocEngine()
    # frame 1: face+track co-present, but co-occurrence needs >=2 frames
    face1 = {"bbox_xyxy_source": [45.0, 10.0, 105.0, 80.0], "face_index": 0}
    track1 = {"track_id": 3, "bbox": [30.0, 0.0, 150.0, 120.0]}
    out1 = engine.associate_frame(camera_id="camA", faces=[face1], tracks=[track1], captured_at=1.0)
    assert "temporal_co_occurrence" not in out1[0]["reasons"]
    # frame 2: face and track move together (20 px right; the 60 px face box
    # still IoU-matches its tracklet at 0.5)
    face2 = {"bbox_xyxy_source": [65.0, 10.0, 125.0, 80.0], "face_index": 0}
    track2 = {"track_id": 3, "bbox": [50.0, 0.0, 170.0, 120.0]}
    out2 = engine.associate_frame(camera_id="camA", faces=[face2], tracks=[track2], captured_at=2.0)
    assert "temporal_co_occurrence" in out2[0]["reasons"]


def test_association_motion_inconsistent_blocks_temporal_reason():
    engine = FaceAssocEngine()
    face1 = {"bbox_xyxy_source": [45.0, 10.0, 145.0, 110.0], "face_index": 0}
    track1 = {"track_id": 3, "bbox": [30.0, 0.0, 170.0, 120.0]}
    engine.associate_frame(camera_id="camA", faces=[face1], tracks=[track1], captured_at=1.0)
    # face moves +30 px while the track stands still -> within tracklet IoU
    # matching range but inconsistent motion (tolerance 0.2*120 = 24 px)
    face2 = {"bbox_xyxy_source": [75.0, 10.0, 175.0, 110.0], "face_index": 0}
    track2 = {"track_id": 3, "bbox": [30.0, 0.0, 170.0, 120.0]}
    out2 = engine.associate_frame(camera_id="camA", faces=[face2], tracks=[track2], captured_at=2.0)
    assert "temporal_co_occurrence" not in out2[0]["reasons"]


def test_multi_camera_non_association_is_structural():
    engine = FaceAssocEngine()
    face = {"bbox_xyxy_source": [45.0, 10.0, 55.0, 25.0], "face_index": 0}
    track = {"track_id": 1, "bbox": [30.0, 0.0, 70.0, 100.0]}
    out_a = engine.associate_frame(camera_id="camA", faces=[face], tracks=[track], captured_at=1.0)
    out_b = engine.associate_frame(camera_id="camB", faces=[face], tracks=[track], captured_at=1.0)
    assert out_a[0]["track_id"] == "camA::1"
    assert out_b[0]["track_id"] == "camB::1"       # same raw id, different namespace
    assert out_a[0]["track_id"] != out_b[0]["track_id"]
    # camB's face never inherits camA's temporal bookkeeping
    assert "temporal_co_occurrence" not in out_b[0]["reasons"]


def test_face_assoc_payload_shape_and_uncalibrated_label():
    engine = FaceAssocEngine()
    face = {"bbox_xyxy_source": [45.0, 10.0, 55.0, 25.0], "face_index": 0}
    track = {"track_id": 7, "bbox": [30.0, 0.0, 70.0, 100.0]}
    entry = engine.associate_frame(camera_id="camA", faces=[face], tracks=[track],
                                   captured_at=1.0)[0]
    # WT-08 contract keys are all present
    for key in ("track_id", "confidence", "ambiguous", "reasons"):
        assert key in entry
    assert "UNCALIBRATED" in entry["confidence_semantics"].upper() or \
           entry["confidence_semantics"] == "heuristic_uncalibrated"
    assert FACE_ASSOC_META["causal"] is False
    assert "not_a_probability" in FACE_ASSOC_META["confidence_semantics"]


# ------------------------------------------------------------- SC-8 records
def test_derivative_record_contract_keys():
    record = build_derivative_record(
        derivative_id="deriv-alert-x-000", alert_id="alert-x", camera_id="camA",
        parent_path="evidence_clips/alert-x_faces/a.frame.png", parent_sha256="ab" * 32,
        parent_captured_at=1.0, parent_sample_timestamp=None,
        subject_ref={"kind": "face", "faceIndex": 0, "trackId": 7,
                     "bboxXyxy": [1, 2, 3, 4], "frameSequence": 3},
        derivative_path="evidence_clips/alert-x_faces/a.face.png",
        derivative_sha256="cd" * 32,
        operations=[{"name": "crop", "params": {"bboxXyxy": [1, 2, 3, 4]}}],
        library_versions={"python": "3", "opencv": "4", "numpy": "2"},
        operator={"id": "system:backend.face_capture", "kind": "system",
                  "module": "backend.face_capture", "moduleVersion": "1.0.0"},
        is_enhanced=False,
    )
    assert REQUIRED_DERIVATIVE_KEYS <= set(record)
    assert record["recordType"] == "enhancement-derivative"
    assert record["isEnhanced"] is False
    assert record["label"] == "CROP DERIVATIVE"
    assert record["tier"] == 0 and record["derivationBasis"] == "deterministic"
    with pytest.raises(ValueError):
        build_derivative_record(
            derivative_id="d", alert_id="a", camera_id=None, parent_path="p",
            parent_sha256="N/A", parent_captured_at=None, parent_sample_timestamp=None,
            subject_ref={}, derivative_path="d", derivative_sha256="ab" * 32,
            operations=[], library_versions={}, operator={}, is_enhanced=False)


def test_derivative_ledger_ordering_guard_and_chain(tmp_path):
    ledger_path = tmp_path / "evidence_ledger.jsonl"
    record = build_derivative_record(
        derivative_id="deriv-alert-y-000", alert_id="alert-y", camera_id="camA",
        parent_path="f.png", parent_sha256="ab" * 32,
        parent_captured_at=1.0, parent_sample_timestamp=2.0,
        subject_ref={"kind": "face", "faceIndex": 0, "trackId": 1,
                     "bboxXyxy": [1, 2, 3, 4], "frameSequence": 0},
        derivative_path="c.png", derivative_sha256="cd" * 32,
        operations=[{"name": "crop", "params": {}}],
        library_versions={"python": "3", "opencv": "4", "numpy": "2"},
        operator={"id": "system:backend.face_capture", "kind": "system",
                  "module": "backend.face_capture", "moduleVersion": "1.0.0"},
        is_enhanced=False)
    ledger = FaceDerivativeLedger(ledger_path)
    # ordering guard: no alert receipt yet -> refused
    with pytest.raises(ValueError):
        ledger.append_derivative(record)
    # append a normal alert receipt (EvidenceLedger-compatible chain record)
    receipt = {"alertId": "alert-y", "cameraId": "camA", "severity": "low",
               "confidence": 1.0, "timestamp": "2026-09-29T00:00:00+00:00"}
    chain_ledger = FaceDerivativeLedger(ledger_path)
    body = dict(receipt)
    import hashlib, json as _json
    body["prevHash"] = "GENESIS"
    body["currentHash"] = hashlib.sha256(
        _json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    with ledger_path.open("w", encoding="utf-8") as fh:
        fh.write(_json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
    appended = ledger.append_derivative(record)
    assert appended["currentHash"]
    # idempotent replay: same derivativeId returns the existing record
    again = ledger.append_derivative(record)
    assert again["currentHash"] == appended["currentHash"]
    records = chain_ledger._read_chain()
    assert [r.get("recordType") for r in records] == [None, "enhancement-derivative"]


# ------------------------------------------------------------------- service
def test_service_capture_persists_crop_frame_and_assoc(tmp_path):
    detector = StubDetector(faces=[make_face((40, 10, 100, 80))])
    service = FaceCaptureService(detector, tmp_path / "evidence", sample_every=1)
    try:
        service.start_capture(
            "alert-1", "camA", [frame_entry(1.0)], post_source=None,
            track_provider=lambda: [{"track_id": 5, "bbox": [30.0, 0.0, 80.0, 110.0]}])
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            result = service.get_result("alert-1")
            if result.get("status") in {"captured", "absent", "failed"}:
                break
            time.sleep(0.02)
        assert result["status"] == "captured"
        assert result["faces_detected"] == 1
        assert len(result["crops"]) == 1
        crop = result["crops"][0]
        assert Path(crop["crop_path"]).exists() and Path(crop["frame_path"]).exists()
        assert crop["crop_sha256"] and crop["frame_sha256"]
        ref = crop["crop_ref"]
        assert ref["schema"] == "sentinel.crop_ref/v1"
        assert ref["subject_kind"] == "face"
        assert ref["track_id"] == "camA::5"
        assert ref["frame_sha256"] != "N/A" and ref["hash_format"] == "png"
        assert ref["bbox_space"] in {"source", "model_input"}
        assert ref["is_derivative"] is False
        assoc = result["face_assoc"][0]
        for key in ("crop_ref", "track_id", "confidence", "ambiguous", "reasons"):
            assert key in assoc
        assert assoc["track_id"] == "camA::5"
        assert result["best_frame"]["status"] == "unavailable"
        assert "provider" in result["best_frame"]["reason"]
    finally:
        service.shutdown()


def test_service_absent_states(tmp_path):
    # detector absent -> explicit absent with reason
    service = FaceCaptureService(StubDetector(status="absent"), tmp_path / "e", sample_every=1)
    try:
        service.start_capture("alert-a", "camA", [frame_entry(1.0)], post_source=None)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and service.get_result("alert-a").get("status") == "pending":
            time.sleep(0.02)
        result = service.get_result("alert-a")
        assert result["status"] == "absent"
        assert any("face_detector_absent" in r for r in result["reasons"])
    finally:
        service.shutdown()

    # loaded detector, no faces -> absent with explicit reason
    service = FaceCaptureService(StubDetector(faces=[]), tmp_path / "e", sample_every=1)
    try:
        service.start_capture("alert-b", "camA", [frame_entry(1.0)], post_source=None)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and service.get_result("alert-b").get("status") == "pending":
            time.sleep(0.02)
        result = service.get_result("alert-b")
        assert result["status"] == "absent"
        assert "no_face_detected_in_window" in result["reasons"]
    finally:
        service.shutdown()

    # faces detected but all below the reporting gate -> absent, counts preserved
    tiny = make_face((0, 0, 10, 10))
    service = FaceCaptureService(StubDetector(faces=[tiny]), tmp_path / "e", sample_every=1)
    try:
        service.start_capture("alert-c", "camA", [frame_entry(1.0)], post_source=None)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and service.get_result("alert-c").get("status") == "pending":
            time.sleep(0.02)
        result = service.get_result("alert-c")
        assert result["status"] == "absent"
        assert "no_reportable_face" in result["reasons"]
        assert result["faces_detected"] == 1
        assert result["faces_suppressed_reporting_gate"] == 1
    finally:
        service.shutdown()


def test_service_no_frames_in_window_absent(tmp_path):
    service = FaceCaptureService(StubDetector(faces=[]), tmp_path / "e", sample_every=1)
    try:
        service.start_capture("alert-d", "camA", [], post_source=None)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and service.get_result("alert-d").get("status") == "pending":
            time.sleep(0.02)
        result = service.get_result("alert-d")
        assert result["status"] == "absent"
        assert "no_frames_in_window" in result["reasons"]
    finally:
        service.shutdown()


def test_service_async_dispatch_is_non_blocking(tmp_path):
    """Dispatch-path proof: note/start calls never run face work on the caller
    thread and return while detection is still in flight."""
    release = threading.Event()
    started = threading.Event()

    class BlockingDetector(StubDetector):
        def detect(self, frame):
            started.set()
            release.wait(timeout=5.0)
            return super().detect(frame)

    detector = BlockingDetector(faces=[make_face((40, 10, 100, 80))])
    service = FaceCaptureService(detector, tmp_path / "e", sample_every=1)
    try:
        t0 = time.perf_counter()
        note_incident_blocking("alert-async", "camA")   # module-level: no service configured -> no-op
        service.note_incident_blocking("alert-async", "camA")
        service.start_capture("alert-async", "camA", [frame_entry(1.0)], post_source=None)
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.2, f"dispatch-path calls took {elapsed:.3f}s"
        assert started.wait(timeout=5.0)
        # detection is in flight on the worker thread; the caller already returned
        assert service.get_result("alert-async")["status"] == "pending"
        release.set()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and service.get_result("alert-async").get("status") == "pending":
            time.sleep(0.02)
        assert service.get_result("alert-async")["status"] == "captured"
        assert all(name == "face-capture" for name in detector.calls), detector.calls
    finally:
        release.set()
        service.shutdown()


def test_service_bounded_queue_drop_oldest(tmp_path):
    release = threading.Event()

    class BlockingDetector(StubDetector):
        def detect(self, frame):
            release.wait(timeout=10.0)
            return []

    service = FaceCaptureService(BlockingDetector(), tmp_path / "e", sample_every=1, max_queue=2)
    try:
        service.start_capture("alert-1", "camA", [frame_entry(1.0)], post_source=None)
        for i in range(6):
            service.start_capture(f"alert-{i + 2}", "camA", [frame_entry(1.0)], post_source=None)
        assert service.health()["dropped_jobs"] >= 1   # bounded, drop-oldest, no exception
    finally:
        release.set()
        service.shutdown()


def test_note_incident_without_service_is_safe_noop():
    # module default not configured: the hook must be inert, never raise
    note_incident_blocking("alert-x", "camA")


def test_service_on_result_callback_receives_payload(tmp_path):
    seen = {}
    detector = StubDetector(faces=[make_face((40, 10, 100, 80))])
    service = FaceCaptureService(detector, tmp_path / "e", sample_every=1,
                                 on_result=lambda aid, res: seen.update({aid: res}))
    try:
        service.start_capture("alert-cb", "camA", [frame_entry(1.0)], post_source=None)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not seen:
            time.sleep(0.02)
        assert "alert-cb" in seen
        assert seen["alert-cb"]["status"] == "captured"
    finally:
        service.shutdown()
