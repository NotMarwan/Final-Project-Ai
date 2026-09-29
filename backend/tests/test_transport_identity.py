"""WT-17 (S-09) transport identity, overlay correlation and reconnect-storm tests.

Contract under test (SC-3 additive):
- ``frameSequence`` identifies the DISPLAY frame the overlay snapshot was rendered
  on — the same identity the MJPEG stream serves per part (``X-Frame-Sequence``).
- Decision overlays are burned into that exact frame server-side (annotate_fn).
- ``frameAgeAtDetectionEmitMs`` / ``frameAgeAtDetectionEmitClockBase`` are durations
  computed inside a single clock domain; unmeasured values stay null, never zero.
"""
from __future__ import annotations

import asyncio
import gc
import inspect
import time

import cv2
import numpy as np
import pytest

import api
from pipeline_render import RenderThread


class _StubDecision:
    """Decision layer that confirms only after N accepted samples (decision delay)."""

    class _Cfg:
        weapon_threshold = 0.55

        @staticmethod
        def severity_for(score):
            return "high" if score > 0.5 else "none"

        alert_severity_for = severity_for

    config = _Cfg()

    def __init__(self, confirm_after: int):
        self.confirm_after = confirm_after
        self.calls = 0

    def update(self, score, sample_time=None, sample_id=None, current_time=None, **score_metadata):
        self.calls += 1
        confirmed = self.calls >= self.confirm_after
        return {
            "alert_state": "CONFIRMED" if confirmed else "WATCH",
            "confirmed_alert": confirmed,
            "decision_sample_accepted": True,
            "confirm_rule": f"{self.calls}/3",
            "rolling_window_count": self.calls,
            "cooldown_remaining_seconds": 0,
        }

    def status(self, current_time=None):
        return {
            "alert_state": "NORMAL",
            "confirmed_alert": False,
            "decision_sample_accepted": True,
            "confirm_rule": "0/0",
            "rolling_window_count": 0,
            "cooldown_remaining_seconds": 0,
        }


class _FrameStore:
    """Stands in for AppState.set_frame; records every published display frame."""

    def __init__(self):
        self.seq = 0
        self.published = []

    def __call__(self, camera_id, jpg, captured_at=None, clock_base=None):
        self.seq += 1
        self.published.append({
            "sequence": self.seq, "jpg": jpg,
            "captured_at": captured_at, "clock_base": clock_base,
        })
        return self.seq


def _feed_frame(worker, sequence, captured_at=None, clock_base=None):
    worker._last_result = {
        "inference_sequence": sequence,
        "inference_sample_time": time.monotonic(),
        "observation_score": 0.9,
        "threat_confidence": 90.0,
        "is_threat": True,
        "tracks": [],
        "person_count": 1,
    }
    payload = {"frame": np.zeros((120, 160, 3), dtype=np.uint8)}
    if captured_at is not None:
        payload["captured_at"] = captured_at
    if clock_base is not None:
        payload["clock_base"] = clock_base
    worker._render_frame(payload)


def test_overlay_labels_match_the_underlying_frame_after_a_decision_delay():
    store = _FrameStore()
    snaps = []
    annotated_states = []
    worker = RenderThread(
        [], None, camera_id="cam-correlate", decision_layer=_StubDecision(confirm_after=3),
        set_frame_fn=store,
        annotate_fn=lambda **kwargs: annotated_states.append(kwargs.get("decision_state")) or kwargs["frame"],
        set_detection_meta_fn=lambda _camera, snap: snaps.append(snap),
        on_threat_fn=lambda payload, *args: None,
        on_evidence_trigger_fn=lambda *args: None,
    )

    for index in range(1, 6):
        worker._render_dropped = index % 2  # exercise backlog stamping too
        _feed_frame(worker, index, captured_at=time.monotonic() - 0.1, clock_base="monotonic-gettickcount64")

    assert len(store.published) == 5 and len(snaps) == 5
    for index, (published, snap, state) in enumerate(zip(store.published, snaps, annotated_states), start=1):
        # The label decision drawn on this frame and the identity stamped for this
        # frame come from the same render pass: no cross-frame overlay drift possible.
        assert snap["frameSequence"] == published["sequence"] == index
        assert snap["decision_layer"]["alert_state"] == state
        assert snap["renderBacklogDroppedCount"] == index % 2
        assert snap["frame_captured_at"] == published["captured_at"]

    # Decision delay: frames 1-2 are WATCH, frames 3+ are CONFIRMED.
    assert annotated_states[:2] == ["WATCH", "WATCH"]
    assert annotated_states[2:] == ["CONFIRMED"] * 3


def test_detection_payload_frame_identity_fields_are_null_when_unmeasured():
    stamped = {
        "frameSequence": 7,
        "frame_captured_at": time.monotonic() - 0.25,
        "frame_clock_base": "monotonic-gettickcount64",
        "renderBacklogDroppedCount": 2,
        "inference_sequence": 5,
    }
    payload = api._build_detection_payload(stamped, "CAM-01")
    assert payload["frameSequence"] == 7
    assert payload["renderBacklogDroppedCount"] == 2
    assert payload["frameAgeAtDetectionEmitClockBase"] == "monotonic-gettickcount64"
    assert isinstance(payload["frameAgeAtDetectionEmitMs"], (int, float))
    assert 200.0 <= payload["frameAgeAtDetectionEmitMs"] < 2000.0

    qpc = dict(stamped, frame_captured_at=time.perf_counter() - 0.1, frame_clock_base="perf-qpc")
    payload_qpc = api._build_detection_payload(qpc, "CAM-01")
    assert payload_qpc["frameAgeAtDetectionEmitClockBase"] == "perf-qpc"

    empty = api._build_detection_payload({}, "CAM-01")
    assert empty["frameSequence"] is None
    assert empty["frameAgeAtDetectionEmitMs"] is None
    assert empty["frameAgeAtDetectionEmitClockBase"] is None
    assert empty["renderBacklogDroppedCount"] is None


def test_mjpeg_parts_carry_frame_identity_and_age_headers():
    async def read():
        generator = api._mjpeg_generator("cam-headers")
        try:
            api.state.set_frame("cam-headers", b"frame-a", time.monotonic() - 0.2)
            first = await asyncio.wait_for(anext(generator), timeout=2)
            api.state.set_frame("cam-headers", b"frame-b")  # no capture stamp
            second = await asyncio.wait_for(anext(generator), timeout=2)
            assert b"X-Frame-Sequence: 1\r\n" in first and b"frame-a" in first
            assert b"X-Frame-Age-Ms: " in first
            assert b"X-Frame-Age-Clock-Base: monotonic-gettickcount64\r\n" in first
            assert b"X-Frame-Sequence: 2\r\n" in second and b"frame-b" in second
            # Unmeasured age: header absent, never a fake zero.
            assert b"X-Frame-Age-Ms: " not in second
        finally:
            await generator.aclose()
    asyncio.run(read())


def test_go2rtc_sidecar_health_is_explicit_and_never_silent(tmp_path):
    import sys

    from webrtc_streamer import Go2RTCSidecar

    # Default deployment: webrtc.enabled false → DISABLED with a stated reason.
    disabled = Go2RTCSidecar({"webrtc": {"enabled": False, "go2rtc_binary": "./go2rtc"}}, {})
    disabled_health = disabled.start()
    assert disabled_health["state"] == "DISABLED"
    assert disabled_health["running"] is False
    assert "webrtc.enabled" in disabled_health["reason"]
    assert disabled_health["license"].startswith("MIT") and "go2rtc" in disabled_health["upstream"]

    # Enabled but binary absent → DISABLED (SC-10) with a provisioning hint.
    missing = Go2RTCSidecar({"webrtc": {"enabled": True, "go2rtc_binary": str(tmp_path / "absent.exe")}}, {})
    missing_health = missing.start()
    assert missing_health["state"] == "DISABLED"
    assert "not found" in missing_health["reason"] and missing_health["reason"].endswith("")

    # Present + pinned hash mismatch → ERROR, never silently accepted.
    fake = tmp_path / "go2rtc.exe"
    fake.write_bytes(b"not-the-real-binary")
    mismatch = Go2RTCSidecar(
        {"webrtc": {"enabled": True, "go2rtc_binary": str(fake), "go2rtc_sha256": "0" * 64}}, {})
    mismatch_health = mismatch.start()
    assert mismatch_health["state"] == "ERROR" and "hash mismatch" in mismatch_health["reason"]

    # Present without a pin → READY resolution records the observed sha256.
    resolved = Go2RTCSidecar({"webrtc": {"enabled": True, "go2rtc_binary": str(fake)}}, {})
    assert resolved.check() == "READY"
    assert resolved.health()["sha256"] and resolved.health()["sha256"] != "0" * 64

    # A launch that dies immediately is reported as ERROR, not RUNNING.
    failing = Go2RTCSidecar(
        {"webrtc": {"enabled": True, "go2rtc_binary": sys.executable,
                    "go2rtc_config": str(tmp_path / "bogus.yml")}}, {})
    failing_health = failing.start()
    assert failing_health["state"] == "ERROR" and "exited immediately" in failing_health["reason"]
    assert failing_health["running"] is False


def test_reconnect_storm_leaves_no_zombie_streams(monkeypatch):
    # ASGITransport buffers the entire body and cannot consume an infinite
    # response. Drive a real ASGI disconnect after the first payload instead.
    monkeypatch.setattr(api, "_stream_subscribers", 0)
    monkeypatch.setattr(api, "_stream_attempts", {})

    async def connect_then_disconnect(path):
        messages = asyncio.Queue()
        await messages.put({"type": "http.request", "body": b"", "more_body": False})
        status = None
        first_body = None

        async def send(message):
            nonlocal status, first_body
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body" and message.get("body") and first_body is None:
                first_body = message["body"]
                await messages.put({"type": "http.disconnect"})

        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1", "method": "GET", "scheme": "http",
            "path": path, "raw_path": path.encode(),
            "query_string": b"camera_id=EXAMPLE-01", "root_path": "",
            "headers": [(b"host", b"test")],
            "client": ("reconnect-test", 1234), "server": ("test", 80),
        }
        await asyncio.wait_for(api.app(scope, messages.get, send), timeout=2)
        assert status == 200
        assert first_body
        assert api._stream_subscribers == 0
        return first_body

    async def storm():
        for index in range(12):
            frame = f"frame-{index}".encode()
            api.state.set_frame("EXAMPLE-01", frame, time.monotonic())
            chunk = await connect_then_disconnect("/video_feed")
            assert b"--frame" in chunk and frame in chunk
            detection = await connect_then_disconnect("/detections")
            assert detection.startswith(b"data: ")

        gc.collect()
        zombies = [
            obj for obj in gc.get_objects()
            if inspect.isasyncgen(obj) and getattr(obj, "ag_frame", None) is not None
            and obj.ag_frame.f_locals.get("camera_id") == "EXAMPLE-01"
        ]
        assert zombies == [], f"zombie streams still suspended after storm: {zombies}"
        api.state.set_frame("EXAMPLE-01", b"frame-after", time.monotonic())
        assert b"frame-after" in await connect_then_disconnect("/video_feed")

    asyncio.run(storm())
