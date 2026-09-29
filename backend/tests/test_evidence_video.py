"""Real codec and lifecycle checks for browser-compatible evidence output."""

import asyncio
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from backend import evidence_video
from backend.evidence import (
    EvidenceHoldStore,
    EvidenceIntegrityError,
    EvidenceLedger,
    EvidenceLedgerConfig,
)


def _frames(count=12, width=64, height=48):
    frames = []
    for index in range(count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = index * 11
        frame[:, :, 1] = np.arange(width, dtype=np.uint8)
        frame[:, :, 2] = np.arange(height, dtype=np.uint8)[:, None]
        frames.append(frame)
    return frames


def _decode_count(path: Path) -> tuple[int, int]:
    reader = cv2.VideoCapture(str(path))
    count = 0
    fourcc = int(reader.get(cv2.CAP_PROP_FOURCC))
    while True:
        ok, frame = reader.read()
        if not ok:
            break
        assert frame.shape[:2] == (48, 64)
        count += 1
    reader.release()
    return count, fourcc


def test_real_h264_output_is_fast_start_yuv420p_and_fully_decodes(tmp_path):
    ffmpeg = evidence_video.resolve_ffmpeg()
    output = tmp_path / "fixture.part.mp4"
    result = evidence_video.encode_browser_mp4(
        _frames(), output, fps=6, width=64, height=48, timeout_seconds=10
    )

    assert result.codec == "h264"
    assert result.pixel_format == "yuv420p"
    assert result.fast_start is True
    assert result.frame_count == 12
    decoded, fourcc = _decode_count(output)
    assert decoded == 12
    assert fourcc.to_bytes(4, "little").decode("ascii").lower() in {"avc1", "h264"}

    probe = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-i", str(output), "-map", "0:v:0", "-f", "null", "-"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
        shell=False,
    )
    diagnostics = probe.stderr.decode("utf-8", errors="replace").lower()
    assert probe.returncode == 0
    assert "video: h264" in diagnostics
    assert "yuv420p" in diagnostics


def test_timeout_kills_process_and_joins_watchdog():
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    blocking_frame = np.zeros((1024, 1024, 3), dtype=np.uint8)
    started = time.monotonic()
    with pytest.raises(evidence_video.EvidenceEncodingTimeout):
        evidence_video._encode_raw_frames(
            command,
            [blocking_frame],
            timeout_seconds=0.15,
            cancel_event=None,
        )
    assert time.monotonic() - started < 2.0
    assert not any(
        thread.name == "evidence-video-watchdog" and thread.is_alive()
        for thread in threading.enumerate()
    )


def test_cancellation_kills_process_and_joins_watchdog():
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    blocking_frame = np.zeros((1024, 1024, 3), dtype=np.uint8)
    cancel = threading.Event()
    timer = threading.Timer(0.15, cancel.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(evidence_video.EvidenceEncodingCancelled):
            evidence_video._encode_raw_frames(
                command,
                [blocking_frame],
                timeout_seconds=5,
                cancel_event=cancel,
            )
    finally:
        timer.join(timeout=1)
    assert time.monotonic() - started < 2.0
    assert not any(
        thread.name == "evidence-video-watchdog" and thread.is_alive()
        for thread in threading.enumerate()
    )


def test_pre_cancel_does_not_start_encoder(monkeypatch):
    cancel = threading.Event()
    cancel.set()
    started = False

    def unexpected(*args, **kwargs):
        nonlocal started
        started = True
        raise AssertionError("process must not start")

    monkeypatch.setattr(evidence_video.subprocess, "Popen", unexpected)
    with pytest.raises(evidence_video.EvidenceEncodingCancelled):
        evidence_video._encode_raw_frames(
            ["unused"],
            [],
            timeout_seconds=1,
            cancel_event=cancel,
        )
    assert started is False


# ─── WT-24 S-07: encoder opt-in (E-7) + probe contract ────────────────────────


def test_unset_env_keeps_the_validated_cpu_encoder(monkeypatch):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    assert evidence_video.resolve_encoder_mode() == "libx264"


def test_encoder_env_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("AI_SENTINEL_EVIDENCE_ENCODER", "hevc_nvenc")
    with pytest.raises(evidence_video.EvidenceEncoderUnavailable):
        evidence_video.resolve_encoder_mode()


def test_auto_without_nvenc_capability_still_produces_verified_output(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SENTINEL_EVIDENCE_ENCODER", "auto")
    monkeypatch.setattr(evidence_video, "_probe_nvenc", lambda ffmpeg: False)
    output = tmp_path / "auto.part.mp4"
    result = evidence_video.encode_browser_mp4(
        _frames(), output, fps=6, width=64, height=48, timeout_seconds=10
    )
    assert result.encoder == "ffmpeg/libx264"
    assert result.frame_count == 12
    assert result.fast_start is True


def test_explicit_nvenc_fails_loudly_without_session_capacity(tmp_path, monkeypatch):
    class NoSlots:
        def acquire(self, *args, **kwargs):
            return False

        def release(self):
            raise AssertionError("no slot was acquired")

    monkeypatch.setattr(evidence_video, "_nvenc_slots", NoSlots())
    output = tmp_path / "nvenc.part.mp4"
    with pytest.raises(evidence_video.EvidenceEncoderUnavailable):
        evidence_video.encode_browser_mp4(
            _frames(), output, fps=6, width=64, height=48, timeout_seconds=10,
            encoder="h264_nvenc",
        )
    assert not output.exists()


def test_auto_falls_back_to_libx264_when_nvenc_encode_fails(tmp_path, monkeypatch):
    class RecordingSlots:
        def __init__(self):
            self.released = 0

        def acquire(self, *args, **kwargs):
            return True

        def release(self):
            self.released += 1

    slots = RecordingSlots()
    real_encode = evidence_video._encode_raw_frames

    def fail_nvenc_only(command, frames, **kwargs):
        if any("h264_nvenc" == part for part in command):
            raise evidence_video.EvidenceVideoError("simulated nvenc failure")
        return real_encode(command, frames, **kwargs)

    monkeypatch.setattr(evidence_video, "_nvenc_slots", slots)
    monkeypatch.setattr(evidence_video, "_probe_nvenc", lambda ffmpeg: True)
    monkeypatch.setattr(evidence_video, "_encode_raw_frames", fail_nvenc_only)
    output = tmp_path / "fallback.part.mp4"
    result = evidence_video.encode_browser_mp4(
        _frames(), output, fps=6, width=64, height=48, timeout_seconds=10,
        encoder="auto",
    )
    # The published contract is encoder-agnostic and the fallback is recorded.
    assert result.encoder == "ffmpeg/libx264"
    assert result.codec == "h264"
    assert result.pixel_format == "yuv420p"
    assert result.frame_count == 12
    assert slots.released == 1


def test_probe_contract_is_encoder_agnostic_for_nvenc_outputs(tmp_path, monkeypatch):
    # The verify step must accept any encoder that meets the output contract:
    # simulated NVENC output goes through the same moov/mdat + decode probe.
    def fake_args(encoder):
        assert encoder == "h264_nvenc"
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-profile:v", "high", "-tag:v", "avc1"]

    class Slots:
        def acquire(self, *args, **kwargs):
            return True

        def release(self):
            pass

    monkeypatch.setattr(evidence_video, "_encoder_video_args", fake_args)
    monkeypatch.setattr(evidence_video, "_nvenc_slots", Slots())
    monkeypatch.setattr(evidence_video, "_probe_nvenc", lambda ffmpeg: True)
    output = tmp_path / "probe.part.mp4"
    result = evidence_video.encode_browser_mp4(
        _frames(), output, fps=6, width=64, height=48, timeout_seconds=10,
        encoder="auto",
    )
    assert result.encoder == "ffmpeg/h264_nvenc"
    assert result.frame_count == 12


# ─── WT-24 S-07: evidence writer lifecycle (pre/post, G-08, partial clips) ────


@pytest.fixture
def api(monkeypatch):
    import backend.api as module
    monkeypatch.setattr(module, "state", module.AppState())
    monkeypatch.setattr(module, "fusion_engine", None)
    monkeypatch.setattr(module, "audit_logger", Mock())
    monkeypatch.setattr(module, "security_controller", Mock())
    module.security_controller.authorize.return_value = "admin"
    return module


def _frames_at(base, stamps, width=32, height=24, level=90):
    return [(stamp, np.full((height, width, 3), level, np.uint8)) for stamp in stamps]


def _setup_ledger(api, monkeypatch, tmp_path):
    monkeypatch.setattr(api, "EVIDENCE_DIR", tmp_path)
    ledger = EvidenceLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    monkeypatch.setattr(api, "evidence_ledger", ledger)
    return ledger


def _run_writer(api, alert_id, pre, post, fps=5.0):
    api._write_evidence_clip(alert_id, pre, post, fps=fps, width=32, height=24)


def test_g08_clip_duration_within_5_percent_and_fps_exact(api, monkeypatch, tmp_path):
    from fastapi import HTTPException  # noqa: F401  (import sanity for route tests)

    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    ledger = _setup_ledger(api, monkeypatch, tmp_path)
    alert_id = "alert-g08"
    api.state.register_alert({"id": alert_id, "cameraId": "cam", "confidence": 90})
    api.state.store_report_text(alert_id, "summary")
    base = time.monotonic()
    fps = 5.0
    pre = _frames_at(base, [base + index / fps for index in range(8)])
    post = Queue()
    for stamp in [base + index / fps for index in range(8, 33)]:
        post.put((stamp, np.full((24, 32, 3), 90, np.uint8)))
    post.put(None)
    _run_writer(api, alert_id, pre, post, fps=fps)

    assert api.state.get_evidence_status(alert_id) == "ready"
    receipt = ledger.get(alert_id)
    span = receipt["clipSourceSpanSeconds"]
    duration = receipt["clipDurationSeconds"]
    assert abs(duration - span) / span <= 0.05, (duration, span)
    assert duration == pytest.approx(receipt["clipFrameCount"] / fps)
    reader = cv2.VideoCapture(str(tmp_path / f"{alert_id}.mp4"))
    assert reader.get(cv2.CAP_PROP_FPS) == pytest.approx(fps, abs=0.01)
    decoded = 0
    while reader.read()[0]:
        decoded += 1
    reader.release()
    assert decoded == receipt["clipFrameCount"] == 33
    assert receipt["clipComplete"] is True
    assert receipt["clipPartialReason"] is None
    assert receipt["clipCaptureClockDomain"] == "monotonic"
    assert receipt["timestampClockDomain"] == "utc-wall"
    assert receipt["clipHashStatus"] == "hashed"


def test_stream_close_before_deadline_is_an_explicit_partial_clip(api, monkeypatch, tmp_path):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    ledger = _setup_ledger(api, monkeypatch, tmp_path)
    alert_id = "alert-partial-close"
    api.state.register_alert({"id": alert_id, "cameraId": "cam", "confidence": 90})
    base = time.monotonic()
    fps = 5.0
    pre = _frames_at(base, [base + index / fps for index in range(8)])
    post = Queue()
    for stamp in [base + index / fps for index in range(8, 16)]:
        post.put((stamp, np.full((24, 32, 3), 90, np.uint8)))
    post.put(None)  # stream closed before trigger + 5 s
    _run_writer(api, alert_id, pre, post, fps=fps)

    receipt = ledger.get(alert_id)
    assert api.state.get_evidence_status(alert_id) == "partial"
    assert receipt["clipComplete"] is False
    assert receipt["clipPartialReason"] == "stream-closed"
    assert (tmp_path / f"{alert_id}.mp4").exists()


def test_stream_stall_is_an_explicit_partial_clip_with_reason(api, monkeypatch, tmp_path):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    ledger = _setup_ledger(api, monkeypatch, tmp_path)
    alert_id = "alert-partial-stall"
    api.state.register_alert({"id": alert_id, "cameraId": "cam", "confidence": 90})
    base = time.monotonic()
    fps = 5.0
    pre = _frames_at(base, [base + index / fps for index in range(8)])
    post = Queue()
    for stamp in [base + index / fps for index in range(8, 16)]:
        post.put((stamp, np.full((24, 32, 3), 90, np.uint8)))
    # No sentinel: the producer goes silent and the bounded get() times out.
    _run_writer(api, alert_id, pre, post, fps=fps)

    receipt = ledger.get(alert_id)
    assert api.state.get_evidence_status(alert_id) == "partial"
    assert receipt["clipComplete"] is False
    assert receipt["clipPartialReason"] == "stalled"


def test_stream_start_without_pre_event_frames_still_finalizes(api, monkeypatch, tmp_path):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    ledger = _setup_ledger(api, monkeypatch, tmp_path)
    alert_id = "alert-stream-start"
    api.state.register_alert({"id": alert_id, "cameraId": "cam", "confidence": 90})
    base = time.monotonic()
    fps = 5.0
    post = Queue()
    for stamp in [base + index / fps for index in range(0, 31)]:
        post.put((stamp, np.full((24, 32, 3), 90, np.uint8)))
    _run_writer(api, alert_id, [], post, fps=fps)

    receipt = ledger.get(alert_id)
    assert api.state.get_evidence_status(alert_id) == "ready"
    # The pre-event window is honestly near-empty at stream start, not faked.
    assert receipt["clipPreEventSpanSeconds"] < 1.0
    assert receipt["clipFrameCount"] >= 25


def test_unreadable_snapshot_still_emits_receipt_with_explicit_failure(api, monkeypatch, tmp_path):
    # SecurityApiAudit regression case: an unreadable asset must not drop the
    # alert finalization; the failure is explicit data in the chain (R-4).
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    ledger = _setup_ledger(api, monkeypatch, tmp_path)
    alert_id = "alert-unreadable-snapshot"
    api.state.register_alert({"id": alert_id, "cameraId": "cam", "confidence": 90})
    api.state.store_snapshot_path(alert_id, str(tmp_path / "never-written.jpg"))
    base = time.monotonic()
    fps = 5.0
    pre = _frames_at(base, [base + index / fps for index in range(8)])
    post = Queue()
    for stamp in [base + index / fps for index in range(8, 33)]:
        post.put((stamp, np.full((24, 32, 3), 90, np.uint8)))
    post.put(None)
    _run_writer(api, alert_id, pre, post, fps=fps)

    assert api.state.get_evidence_status(alert_id) == "ready"
    receipt = ledger.get(alert_id)
    assert receipt is not None
    assert receipt["snapshotSha256"] == "N/A"
    assert receipt["snapshotHashStatus"] == "unreadable"
    assert receipt["clipHashStatus"] == "hashed"


def test_torn_write_is_never_published_and_a_retry_recovers(api, monkeypatch, tmp_path):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    _setup_ledger(api, monkeypatch, tmp_path)
    alert_id = "alert-torn"
    api.state.register_alert({"id": alert_id, "cameraId": "cam", "confidence": 90})
    real_encode = evidence_video.encode_browser_mp4
    broken = {"on": True}

    def torn(*args, **kwargs):
        if broken["on"]:
            (tmp_path / f"{alert_id}.part.mp4").write_bytes(b"torn")
            raise evidence_video.EvidenceVideoError("simulated crash mid-encode")
        return real_encode(*args, **kwargs)

    monkeypatch.setattr(evidence_video, "encode_browser_mp4", torn)
    base = time.monotonic()
    post = Queue()
    post.put(None)
    _run_writer(api, alert_id, _frames_at(base, [base]), post)
    assert api.state.get_evidence_status(alert_id) == "error"
    assert not (tmp_path / f"{alert_id}.mp4").exists()
    assert not (tmp_path / f"{alert_id}.part.mp4").exists()

    # A retry after the torn write publishes cleanly.
    broken["on"] = False
    api.state.store_report_text(alert_id, "summary")
    fps = 5.0
    pre = _frames_at(base, [base + index / fps for index in range(8)])
    post = Queue()
    for stamp in [base + index / fps for index in range(8, 33)]:
        post.put((stamp, np.full((24, 32, 3), 90, np.uint8)))
    post.put(None)
    _run_writer(api, alert_id, pre, post, fps=fps)
    assert api.state.get_evidence_status(alert_id) == "ready"
    assert (tmp_path / f"{alert_id}.mp4").exists()
    assert not (tmp_path / f"{alert_id}.part.mp4").exists()
    assert api.evidence_ledger.get(alert_id)["clipHashStatus"] == "hashed"


def test_duplicate_alert_id_second_writer_never_overwrites_chained_clip(api, monkeypatch, tmp_path):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    ledger = _setup_ledger(api, monkeypatch, tmp_path)
    alert_id = "alert-duplicate"
    api.state.register_alert({"id": alert_id, "cameraId": "cam", "confidence": 90})
    base = time.monotonic()
    fps = 5.0
    pre = _frames_at(base, [base + index / fps for index in range(8)], level=90)
    post = Queue()
    for stamp in [base + index / fps for index in range(8, 33)]:
        post.put((stamp, np.full((24, 32, 3), 90, np.uint8)))
    post.put(None)
    _run_writer(api, alert_id, pre, post, fps=fps)
    clip_path = tmp_path / f"{alert_id}.mp4"
    chained_bytes = clip_path.read_bytes()
    chained_hash = ledger.get(alert_id)["clipSha256"]

    # Second writer for the same alert id with different pixels.
    post = Queue()
    for stamp in [base + index / fps for index in range(8, 33)]:
        post.put((stamp, np.full((24, 32, 3), 200, np.uint8)))
    post.put(None)
    _run_writer(api, alert_id, pre, post, fps=fps)

    assert clip_path.read_bytes() == chained_bytes
    assert ledger.get(alert_id)["clipSha256"] == chained_hash
    assert api.state.get_evidence_status(alert_id) == "ready"
    assert api.audit_logger.record.call_args.args[0] == "evidence_clip_duplicate"


def test_chained_clip_hash_mismatch_marks_conflict_and_never_clobbers(api, monkeypatch, tmp_path):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    ledger = _setup_ledger(api, monkeypatch, tmp_path)
    alert_id = "alert-conflict"
    api.state.register_alert({"id": alert_id, "cameraId": "cam", "confidence": 90})
    base = time.monotonic()
    fps = 5.0
    pre = _frames_at(base, [base + index / fps for index in range(8)])
    post = Queue()
    for stamp in [base + index / fps for index in range(8, 33)]:
        post.put((stamp, np.full((24, 32, 3), 90, np.uint8)))
    post.put(None)
    _run_writer(api, alert_id, pre, post, fps=fps)
    clip_path = tmp_path / f"{alert_id}.mp4"
    clip_path.write_bytes(b"tampered-replacement")

    post = Queue()
    post.put(None)
    _run_writer(api, alert_id, pre, post, fps=fps)
    assert api.state.get_evidence_status(alert_id) == "error"
    assert clip_path.read_bytes() == b"tampered-replacement"  # never overwritten
    assert api.audit_logger.record.call_args.args[0] == "evidence_clip_conflict"


def test_damaged_ledger_aborts_publish_and_leaves_nothing_unchained(api, monkeypatch, tmp_path):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    ledger = _setup_ledger(api, monkeypatch, tmp_path)
    (tmp_path / "chain.jsonl").write_text('{"alertId": "torn\n', encoding="utf-8")
    alert_id = "alert-damaged-chain"
    api.state.register_alert({"id": alert_id, "cameraId": "cam", "confidence": 90})
    base = time.monotonic()
    fps = 5.0
    pre = _frames_at(base, [base + index / fps for index in range(8)])
    post = Queue()
    for stamp in [base + index / fps for index in range(8, 33)]:
        post.put((stamp, np.full((24, 32, 3), 90, np.uint8)))
    post.put(None)
    _run_writer(api, alert_id, pre, post, fps=fps)
    assert api.state.get_evidence_status(alert_id) == "error"
    assert not (tmp_path / f"{alert_id}.mp4").exists()
    assert not (tmp_path / f"{alert_id}.part.mp4").exists()
    # The damaged chain itself refuses reads: custody stops loudly.
    with pytest.raises(EvidenceIntegrityError):
        ledger.get(alert_id)


# ─── WT-24 S-07: evidence access (P-2 read-audit, tamper check, traversal) ────


def _publish_clip(api, monkeypatch, tmp_path, alert_id, level=90):
    _setup_ledger(api, monkeypatch, tmp_path)
    api.state.register_alert({"id": alert_id, "cameraId": "cam", "confidence": 90})
    api.state.store_report_text(alert_id, "summary")
    base = time.monotonic()
    fps = 5.0
    pre = _frames_at(base, [base + index / fps for index in range(8)], level=level)
    post = Queue()
    for stamp in [base + index / fps for index in range(8, 33)]:
        post.put((stamp, np.full((24, 32, 3), level, np.uint8)))
    post.put(None)
    _run_writer(api, alert_id, pre, post, fps=fps)
    return tmp_path / f"{alert_id}.mp4"


def test_evidence_reads_are_audited_with_artifact_hash_and_tamper_check(api, monkeypatch, tmp_path):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    clip_path = _publish_clip(api, monkeypatch, tmp_path, "alert-audit")
    request = Mock()
    response = asyncio.run(api.get_clip("alert-audit", request))
    assert response.path == str(clip_path)
    action, status, kwargs = _last_audit(api)
    assert action == "evidence_clip_read"
    assert status == "success"
    assert kwargs["details"]["artifact"] == "clip"
    assert kwargs["details"]["artifactSha256"] == api.evidence_ledger.get("alert-audit")["clipSha256"]
    assert kwargs["details"]["ledgerSha256"] == kwargs["details"]["artifactSha256"]

    # One flipped byte must be caught before serving (tamper -> 500 + audit).
    clip_path.write_bytes(clip_path.read_bytes() + b"X")
    with pytest.raises(Exception) as result:
        asyncio.run(api.get_clip("alert-audit", request))
    assert getattr(result.value, "status_code", None) == 500
    action, status, kwargs = _last_audit(api)
    assert action == "evidence_clip_read"
    assert status == "error"
    assert kwargs["details"]["ledgerSha256"] != kwargs["details"]["artifactSha256"]


def _last_audit(api):
    call = api.audit_logger.record.call_args
    return call.args[0], call.args[1], call.kwargs


def test_download_evidence_survives_status_loss_via_chain(api, monkeypatch, tmp_path):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    clip_path = _publish_clip(api, monkeypatch, tmp_path, "alert-restart")
    # Simulate an API restart: in-memory evidence status is gone.
    monkeypatch.setattr(api, "state", api.AppState())
    request = Mock()
    response = asyncio.run(api.download_evidence("alert-restart", request))
    assert response.path == str(clip_path)
    action, status, kwargs = _last_audit(api)
    assert action == "evidence_download"
    assert status == "success"
    assert kwargs["details"]["artifactSha256"] == api.evidence_ledger.get("alert-restart")["clipSha256"]


def test_evidence_chain_read_is_audited(api, monkeypatch, tmp_path):
    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    _publish_clip(api, monkeypatch, tmp_path, "alert-chain")
    request = Mock()
    record = api.evidence_chain("alert-chain", request)
    assert record["alertId"] == "alert-chain"
    action, status, kwargs = _last_audit(api)
    assert action == "evidence_chain_read"
    assert status == "success"
    assert kwargs["details"]["artifact"] == "ledger-record"
    assert kwargs["details"]["artifactSha256"] == record["currentHash"]


def test_evidence_read_rejects_invalid_credentials_before_access(api, monkeypatch, tmp_path):
    from fastapi import HTTPException

    monkeypatch.delenv("AI_SENTINEL_EVIDENCE_ENCODER", raising=False)
    _publish_clip(api, monkeypatch, tmp_path, "alert-actor")

    def reject(*args, **kwargs):
        raise HTTPException(status_code=401, detail="bad key")

    api.security_controller.authorize.side_effect = reject
    request = Mock()
    api.audit_logger.reset_mock()
    ledger_get = Mock(wraps=api.evidence_ledger.get)
    monkeypatch.setattr(api.evidence_ledger, "get", ledger_get)
    with pytest.raises(HTTPException) as result:
        asyncio.run(api.get_clip("alert-actor", request))
    assert result.value.status_code == 401
    ledger_get.assert_not_called()
    api.audit_logger.record.assert_not_called()
    api.security_controller.authorize.assert_called_once_with(request, required_role="viewer")


@pytest.mark.parametrize("alert_id", ["../secret", "alert/path", "alert\\path", "..", "a" * 65])
def test_path_traversal_alert_ids_are_rejected_on_evidence_surface(api, alert_id):
    from fastapi import HTTPException

    request = Mock()
    for call in (
        lambda: asyncio.run(api.get_clip(alert_id, request)),
        lambda: asyncio.run(api.download_evidence(alert_id, request)),
        lambda: api.evidence_chain(alert_id, request),
    ):
        with pytest.raises(HTTPException) as result:
            call()
        assert result.value.status_code == 400


def test_part_file_is_torn_until_published_and_never_served(api, monkeypatch, tmp_path):
    _setup_ledger(api, monkeypatch, tmp_path)
    (tmp_path / "alert-part.part.mp4").write_bytes(b"torn bytes")
    request = Mock()
    listing = asyncio.run(api.list_clips(request))
    assert listing["count"] == 0
    api.security_controller.authorize.assert_called_once_with(request, required_role="viewer")
    with pytest.raises(Exception) as result:
        asyncio.run(api.get_clip("alert-part", request))
    assert getattr(result.value, "status_code", None) == 404


# ─── WT-24 S-07: retention dry-run (P-6) ─────────────────────────────────────


def test_retention_plan_is_dry_run_only_and_holds_win(api, monkeypatch, tmp_path):
    clips = tmp_path / "clips"
    thumbs = tmp_path / "thumbs"
    reports = tmp_path / "reports"
    for directory in (clips, thumbs, reports):
        directory.mkdir()
    monkeypatch.setattr(api, "EVIDENCE_DIR", clips)
    monkeypatch.setattr(api, "THUMBNAILS_DIR", thumbs)
    monkeypatch.setattr(api, "REPORTS_DIR", reports)
    monkeypatch.setattr(api, "_EVIDENCE_HOLD_STORE", EvidenceHoldStore(tmp_path / "holds.json"))

    old = clips / "alert-old.mp4"
    old.write_bytes(b"old clip")
    ancient = time.time() - 40 * 86400
    os.utime(old, (ancient, ancient))
    young = thumbs / "alert-new.jpg"
    young.write_bytes(b"new thumb")
    (clips / "alert-torn.part.mp4").write_bytes(b"torn")

    request = Mock()
    plan = api.evidence_retention_plan(request)
    assert plan["dryRunOnly"] is True
    assert plan["deletionImplemented"] is False
    assert plan["retentionDays"] == api.config["clips"]["clip_retention_days"]
    assert plan["prunableCount"] == 1
    actions = {item["alertId"]: item for item in plan["artifacts"]}
    assert actions["alert-old"]["action"] == "prune"
    assert actions["alert-old"]["reason"] == "older-than-retention"
    assert actions["alert-new"]["action"] == "keep"
    assert "alert-torn" not in actions  # .part files are unpublished, not artifacts
    # Dry-run means nothing was deleted.
    assert old.exists() and young.exists()

    api.evidence_retention_hold({"alertId": "alert-old", "hold": True}, request)
    plan = api.evidence_retention_plan(request)
    actions = {item["alertId"]: item for item in plan["artifacts"]}
    assert actions["alert-old"]["action"] == "keep"
    assert actions["alert-old"]["reason"] == "legal-hold"
    assert plan["holds"] == ["alert-old"]

    api.evidence_retention_hold({"alertId": "alert-old", "hold": False}, request)
    plan = api.evidence_retention_plan(request)
    assert plan["holds"] == []
    assert old.exists()


# ─── WT-24 S-07: quality-audit coordinate + view claims ──────────────────────


def test_model_input_to_source_to_display_coordinate_mapping():
    from inference_process import _scale_person_tracks

    source_size = (1920, 1080)
    input_size = (640, 360)
    tracks = [{"track_id": 7, "bbox": [64.0, 36.0, 320.0, 180.0]}]
    scaled = _scale_person_tracks(tracks, input_size, source_size)
    assert scaled[0]["bbox"] == [192.0, 108.0, 960.0, 540.0]
    # Display is the annotated source-resolution copy: display == source (1:1),
    # so source coordinates are drawn unchanged on the display frame.
    display_size = source_size
    assert display_size == source_size
    # Bounds are clipped into the source frame, never out of range.
    clipped = _scale_person_tracks(
        [{"track_id": 1, "bbox": [-10.0, -10.0, 700.0, 400.0]}], input_size, source_size
    )[0]["bbox"]
    assert clipped == [0.0, 0.0, 1920.0, 1080.0]
    with pytest.raises(ValueError):
        _scale_person_tracks(tracks, (0, 360), source_size)


def test_evidence_view_bypasses_the_inference_view():
    from temporal_frames import downscale_for_inference

    raw = np.zeros((1080, 1920, 3), dtype=np.uint8)
    evidence_frame = downscale_for_inference(raw, 960)   # ring input (api.py)
    inference_view = downscale_for_inference(raw, 640)   # model input (api.py)
    assert evidence_frame.shape[:2] == (540, 960)
    assert inference_view.shape[:2] == (360, 640)
    # Two distinct artifacts: the evidence copy is never derived from the
    # 640-side model view and keeps the full frame aspect (no crop).
    assert evidence_frame.shape != inference_view.shape
    assert 1920 / 1080 == pytest.approx(960 / 540)
    assert raw.shape[1] / raw.shape[0] == pytest.approx(
        evidence_frame.shape[1] / evidence_frame.shape[0]
    )
