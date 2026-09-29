"""Runtime API contracts for camera isolation, honest scores and finalized evidence."""
import asyncio
import hashlib
import json
from queue import Queue
import threading
from unittest.mock import Mock

import cv2
import httpx
import numpy as np
import pytest

from backend.evidence import EvidenceLedger, EvidenceLedgerConfig


@pytest.fixture
def api(monkeypatch):
    import backend.api as module
    monkeypatch.setattr(module, "state", module.AppState())
    monkeypatch.setattr(module, "fusion_engine", None)
    monkeypatch.setattr(module, "audit_logger", Mock())
    monkeypatch.setattr(module, "security_controller", Mock())
    module.security_controller.authorize.return_value = "admin"
    return module


def test_runtime_camera_decisions_are_isolated_and_configuration_propagates(api):
    left = api.state.decision_for_camera("left")
    right = api.state.decision_for_camera("right")
    left.update(0.9, sample_time=10, sample_id=1)
    assert not right.update(0.9, sample_time=11, sample_id=1)["confirmed_alert"]
    api.state.set_cooldown(7)
    assert left.cooldown_seconds == right.cooldown_seconds == 7
    assert left.status()["history_count"] == right.status()["history_count"] == 0
    assert api.state.decision_for_camera("new-camera").cooldown_seconds == 7


def test_threshold_round_trip_does_not_shrink_confirmation_margin(api):
    original = api.state.get_decision_config()
    api.state.set_threshold(0.95)
    api.state.set_threshold(original.violence_threshold)
    current = api.state.get_decision_config()
    assert current.watch_threshold == original.watch_threshold
    assert current.confirm_threshold == original.confirm_threshold


def test_sse_initial_observation_is_unknown_and_json_is_finite(api):
    async def read():
        generator = api._detection_sse_generator("not-started")
        try:
            raw = await anext(generator)
        finally:
            await generator.aclose()
        assert raw.startswith(b"data: ") and raw.endswith(b"\n\n")
        payload = json.loads(raw[6:])
        assert payload["violenceScore"] is None
        assert payload["weaponScore"] is None
        assert payload["calibrationStatus"] == "unverified"
        assert payload["health"]["capture"]["status"] == "UNAVAILABLE"
    asyncio.run(read())


def test_a_completed_weapon_does_not_invent_a_completed_violence_score(api):
    payload = api._build_detection_payload({"inference_sequence": 5, "weapon_observation_id": 1,
        "violence_observation_id": 0, "weapon_score": 0.7, "violence_conf": 0.0}, "camera")
    assert payload["weaponScore"] == 0.7
    assert payload["violenceScore"] is None


def test_mjpeg_sequence_advances_even_when_jpeg_bytes_are_same_object(api):
    async def read():
        jpg = b"same-bytes-object"
        api.state.set_frame("camera", jpg)
        generator = api._mjpeg_generator("camera")
        try:
            first = await asyncio.wait_for(anext(generator), timeout=2)
            api.state.set_frame("camera", jpg)
            second = await asyncio.wait_for(anext(generator), timeout=2)
            # WT-17 (S-09): the wire carries per-part frame identity. Identical JPEG
            # bytes still advance the sequence; the former byte-identity assertion is
            # superseded by X-Frame-Sequence and removed, not re-pinned.
            assert jpg in first and jpg in second
            assert b"X-Frame-Sequence: 1\r\n" in first
            assert b"X-Frame-Sequence: 2\r\n" in second
        finally:
            await generator.aclose()
    asyncio.run(read())


def test_threshold_route_releases_event_loop_while_mutation_runs(api, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    released_while_running = []
    original = api.state.set_threshold

    def mutation(value):
        entered.set()
        released_while_running.append(release.wait(timeout=2))
        return original(value)

    monkeypatch.setattr(api.state, "set_threshold", mutation)

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            pending = asyncio.create_task(client.post("/set_threshold", json={"threshold": 0.6}))
            assert await asyncio.to_thread(entered.wait, 3)
            release.set()
            response = await pending
            assert response.status_code == 200
    asyncio.run(request())
    assert released_while_running == [True]


def test_threshold_route_checks_authorization_before_mutation(api, monkeypatch):
    from fastapi import HTTPException
    api.security_controller.authorize.side_effect = HTTPException(status_code=403, detail="Denied")
    mutation = Mock()
    monkeypatch.setattr(api.state, "set_threshold", mutation)

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
            response = await client.post("/set_threshold", json={"threshold": 0.6})
            assert response.status_code == 403
    asyncio.run(request())
    mutation.assert_not_called()


@pytest.mark.parametrize("alert_id", ["../secret", "alert/path", "alert\\path", "alert\x00bad", "alert\n", "", "a" * 65])
def test_actual_alert_id_validator_rejects_unsafe_paths(api, alert_id):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as result:
        api._validate_alert_id(alert_id)
    assert result.value.status_code == 400


@pytest.mark.parametrize("alert_id", ["alert-finalize-test", "a", "alert_123", "a" * 64])
def test_actual_alert_id_validator_accepts_supported_ids(api, alert_id):
    assert api._validate_alert_id(alert_id) is None


def test_evidence_writer_closes_readable_clip_before_ledger_receipt(api, monkeypatch, tmp_path):
    monkeypatch.setattr(api, "EVIDENCE_DIR", tmp_path)
    ledger = EvidenceLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    monkeypatch.setattr(api, "evidence_ledger", ledger)
    alert_id = "alert-finalize-test"
    api.state.register_alert({"id": alert_id, "cameraId": "test-camera", "confidence": 90})
    api.state.store_report_text(alert_id, "Local factual summary")
    frame = np.full((24, 32, 3), 90, np.uint8)
    pre = [(100 + index / 5, frame.copy()) for index in range(8)]
    post = Queue()
    for index in range(8, 33):
        post.put((100 + index / 5, frame.copy()))
    post.put(None)
    api._write_evidence_clip(alert_id, pre, post, fps=5, width=32, height=24)
    assert api.state.get_evidence_status(alert_id) == "ready"
    clip = tmp_path / (alert_id + ".mp4")
    assert clip.exists()
    assert not (tmp_path / (alert_id + ".part.mp4")).exists()
    reader = cv2.VideoCapture(str(clip))
    decoded = 0
    while True:
        ok, actual = reader.read()
        if not ok:
            break
        assert actual.shape[:2] == (24, 32)
        decoded += 1
    reader.release()
    assert decoded == 33
    receipt = ledger.get(alert_id)
    assert receipt["clipSha256"] == hashlib.sha256(clip.read_bytes()).hexdigest()
    audit = api.audit_logger.record.call_args.kwargs["details"]
    assert audit["postWindowComplete"]
    assert audit["codec"] == "h264"
    assert audit["pixelFormat"] == "yuv420p"
    assert audit["fastStart"] is True
    assert audit["browserVerified"] is False


def test_evidence_encoder_failure_publishes_no_clip_or_receipt(api, monkeypatch, tmp_path):
    import backend.evidence_video as evidence_video

    monkeypatch.setattr(api, "EVIDENCE_DIR", tmp_path)
    ledger = EvidenceLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    monkeypatch.setattr(api, "evidence_ledger", ledger)
    alert_id = "alert-no-encoder"
    api.state.register_alert({"id": alert_id, "cameraId": "test-camera", "confidence": 90})

    def unavailable(*args, **kwargs):
        raise evidence_video.EvidenceEncoderUnavailable("ffmpeg unavailable")

    monkeypatch.setattr(evidence_video, "encode_browser_mp4", unavailable)
    frame = np.zeros((24, 32, 3), np.uint8)
    post = Queue()
    post.put(None)
    api._write_evidence_clip(alert_id, [(100.0, frame)], post, 5, 32, 24)

    assert api.state.get_evidence_status(alert_id) == "error"
    assert not (tmp_path / f"{alert_id}.mp4").exists()
    assert not (tmp_path / f"{alert_id}.part.mp4").exists()
    assert ledger.get(alert_id) is None
    audit = api.audit_logger.record.call_args.kwargs["details"]
    assert audit == {
        "errorType": "EvidenceEncoderUnavailable",
        "errorCode": "ffmpeg_unavailable",
    }
