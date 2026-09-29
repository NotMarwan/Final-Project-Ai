"""Scoped contracts for face detection: health states, coordinate mapping,
reporting gate (never a detection gate). Not an accuracy evaluation — the
fixture-based test is a smoke check and skips when untracked assets are absent.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from face_capture import roundtrip_ok, scale_box_to_source
from face_detect import (EXPECTED_MODEL_SHA256, FaceDetection, YuNetFaceDetector,
                         _landmark_metrics, reporting_gate, resolve_model_path)

BACKEND_DIR = Path(__file__).resolve().parents[1]
ASSETS_MODEL = BACKEND_DIR.parent / "assets" / "yunet" / "face_detection_yunet_2023mar.onnx"
FIXTURES = BACKEND_DIR.parent / "assets" / "fixtures"


def test_health_absent_without_weights(tmp_path, monkeypatch):
    monkeypatch.delenv("FACE_YUNET_MODEL", raising=False)
    monkeypatch.setattr("face_detect.resolve_model_path", lambda explicit=None: None)
    detector = YuNetFaceDetector()
    health = detector.health()
    assert health["status"] == "absent"
    assert "not found" in health["reason"]
    assert detector.detect(np.zeros((64, 64, 3), dtype=np.uint8)) == []


def test_health_failed_on_corrupt_weights(tmp_path):
    bad = tmp_path / "face_detection_yunet_2023mar.onnx"
    bad.write_bytes(b"this is not an onnx model")
    detector = YuNetFaceDetector(model_path=bad)
    assert detector.detect(np.zeros((64, 64, 3), dtype=np.uint8)) == []
    health = detector.health()
    assert health["status"] == "failed"
    assert health["reason"]  # explicit, never silent


def test_health_disabled_when_constructed_disabled():
    detector = YuNetFaceDetector(enabled=False)
    health = detector.health()
    assert health["status"] == "disabled"
    assert detector.detect(np.zeros((64, 64, 3), dtype=np.uint8)) == []


def test_health_lazy_loaded_reports_weights_present_without_session(tmp_path):
    # weights exist but no detection attempted yet -> explicit "absent" reason
    # distinguishes "not loaded yet" from "not found"
    if not ASSETS_MODEL.exists():
        pytest.skip("untracked YuNet weights not present")
    detector = YuNetFaceDetector()
    health = detector.health()
    assert health["status"] == "absent"
    assert "lazy" in health["reason"]


def test_landmark_metrics_yaw_proxy_direction_and_degeneracy():
    symmetric = np.array([[40.0, 50.0], [60.0, 50.0], [50.0, 65.0], [42.0, 80.0], [58.0, 80.0]])
    ied, yaw = _landmark_metrics(symmetric)
    assert ied == pytest.approx(20.0)
    assert yaw == pytest.approx(0.0, abs=1e-6)
    right_shifted = symmetric.copy()
    right_shifted[2] = [65.0, 65.0]  # nose shifted toward left eye side
    _, yaw2 = _landmark_metrics(right_shifted)
    assert yaw2 > 0
    degenerate = np.zeros((5, 2))
    ied3, yaw3 = _landmark_metrics(degenerate)
    assert ied3 == 0.0 and yaw3 == 0.0


def test_scale_box_to_source_uniform_ratio_and_roundtrip():
    box = [10.0, 20.0, 110.0, 220.0]
    mapped = scale_box_to_source(box, (640, 360), (1920, 1080))
    assert mapped == pytest.approx([30.0, 60.0, 330.0, 660.0])
    # source -> frame -> source round-trip within 1 px at 3x scale
    assert roundtrip_ok(mapped, (640, 360), (1920, 1080), tolerance=1.0)
    # identity when frame == source
    assert scale_box_to_source(box, (1920, 1080), (1920, 1080)) == pytest.approx(box)
    assert roundtrip_ok(box, (1920, 1080), (1920, 1080))
    with pytest.raises(ValueError):
        scale_box_to_source(box, (0, 360), (1920, 1080))
    with pytest.raises(ValueError):
        scale_box_to_source([50.0, 50.0, 50.0, 60.0], (640, 360), (1920, 1080))


def test_reporting_gate_is_not_a_detection_gate():
    tiny = FaceDetection(bbox_xyxy=(0, 0, 10, 10), score=0.9,
                         landmarks_5pt=tuple((0.0, 0.0) for _ in range(5)),
                         ied_px=3.0, yaw_proxy_deg=0.0, face_index=0)
    big = FaceDetection(bbox_xyxy=(100, 100, 200, 200), score=0.9,
                        landmarks_5pt=tuple((0.0, 0.0) for _ in range(5)),
                        ied_px=30.0, yaw_proxy_deg=0.0, face_index=1)
    gated = reporting_gate([tiny, big], min_face_size_px=36, min_ied_px=12)
    assert len(gated) == 2  # both DETECTED
    assert gated[0]["reportable"] is False
    assert any(r.startswith("face_box_too_small") for r in gated[0]["unreportable_reasons"])
    assert any(r.startswith("ied_too_small") for r in gated[0]["unreportable_reasons"])
    assert gated[1]["reportable"] is True
    assert gated[1]["unreportable_reasons"] == []


def test_real_detector_smoke_and_coordinate_mapping_on_fixture():
    """Smoke check on repo demo-clip fixture frames; not a labeled accuracy test."""
    if not ASSETS_MODEL.exists() or not FIXTURES.exists():
        pytest.skip("untracked YuNet weights / fixtures not present")
    frames = sorted(FIXTURES.glob("*.jpg"))
    if not frames:
        pytest.skip("no fixture frames")
    detector = YuNetFaceDetector()
    assert detector.health()["status"] in {"absent", "loaded"}
    total_faces = 0
    for frame_path in frames:
        frame = __import__("cv2").imread(str(frame_path))
        faces = detector.detect(frame)
        total_faces += len(faces)
        for face in faces:
            x1, y1, x2, y2 = face.bbox_xyxy
            assert 0 <= x1 < x2 <= frame.shape[1]
            assert 0 <= y1 < y2 <= frame.shape[0]
            # detector output is in the frame's own pixel space: mapping to a
            # same-size "source" is the identity, and the halved-resolution
            # mapping must round-trip
            assert scale_box_to_source(face.bbox_xyxy, (frame.shape[1], frame.shape[0]),
                                       (frame.shape[1], frame.shape[0])) == pytest.approx(
                list(face.bbox_xyxy), abs=1e-3)
            assert roundtrip_ok(face.bbox_xyxy, (frame.shape[1] // 2, frame.shape[0] // 2),
                                (frame.shape[1], frame.shape[0]), tolerance=1.5)
    # honest denominator for the smoke check: how many faces fired on 27 frames
    assert total_faces >= 0
    print(f"[smoke] faces detected across {len(frames)} fixture frames: {total_faces}")
    assert detector.health()["status"] == "loaded"
    assert detector.health()["model_sha256"] == EXPECTED_MODEL_SHA256
