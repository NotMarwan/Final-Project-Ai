"""WT-14 capture quality: profile schema + negotiated-mode read-back (F-03/F-38).

Covers the silent mode-swap trap (OS substitutes decoded NV12/YUY2 for the
requested MJPG pin mode) and asserts the mismatch is surfaced as DEGRADED with
exact requested-vs-actual values and an exact log line — never silent.
"""
import logging
import threading
from collections import deque

import numpy as np
import pytest

from pipeline_capture import (
    CaptureRequest,
    CaptureThread,
    default_profile,
    fourcc_code,
    fourcc_str,
    load_capture_profiles,
    verify_negotiated_mode,
    CaptureProfile,
)


class FakeCapture:
    """Scriptable stand-in for cv2.VideoCapture with set/get mode behavior."""

    def __init__(self, actual=None, refuse_fourcc=None):
        self.props = {
            "FRAME_WIDTH": 1280.0,
            "FRAME_HEIGHT": 720.0,
            "FPS": 30.0,
            "FOURCC": float(fourcc_code("MJPG")),
            "BUFFERSIZE": 0.0,
        }
        self.actual = dict(actual or {})
        self.refuse_fourcc = refuse_fourcc or set()
        self.opened = True
        self.set_calls = []

    def isOpened(self):
        return self.opened

    def set(self, prop, value):
        self.set_calls.append((prop, value))
        return True

    def get(self, prop):
        import cv2
        mapping = {
            cv2.CAP_PROP_FRAME_WIDTH: "FRAME_WIDTH",
            cv2.CAP_PROP_FRAME_HEIGHT: "FRAME_HEIGHT",
            cv2.CAP_PROP_FPS: "FPS",
            cv2.CAP_PROP_FOURCC: "FOURCC",
            cv2.CAP_PROP_BUFFERSIZE: "BUFFERSIZE",
        }
        key = mapping.get(prop)
        if key is None:
            return 0.0
        return self.props.get(key, 0.0)

    def read(self):
        return False, None

    def grab(self):
        return False

    def retrieve(self):
        return False, None

    def release(self):
        self.opened = False


class FakeNegotiatingCapture(FakeCapture):
    """Applies width/height/fps sets, but FOURCC handling is scriptable.

    `fourcc_policy`:
      "honor"   — read-back equals the requested fourcc
      "swap"    — silently reports NV12 (the Windows UVC autodecode trap)
      "fallback"— accepts only YUY2 (refuses MJPG), reports YUY2
    """

    def __init__(self, fourcc_policy="honor", **kwargs):
        super().__init__(**kwargs)
        self.fourcc_policy = fourcc_policy
        if fourcc_policy == "fallback":
            # device refuses MJPG; its native mode is YUY2
            self.props["FOURCC"] = float(fourcc_code("YUY2"))

    def set(self, prop, value):
        import cv2
        self.set_calls.append((prop, value))
        if self.fourcc_policy == "ignore":
            # device silently ignores ALL mode sets and keeps its native mode
            return True
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            self.props["FRAME_WIDTH"] = float(value)
        elif prop == cv2.CAP_PROP_FRAME_HEIGHT:
            self.props["FRAME_HEIGHT"] = float(value)
        elif prop == cv2.CAP_PROP_FPS:
            self.props["FPS"] = float(value)
        elif prop == cv2.CAP_PROP_FOURCC:
            requested = fourcc_str(float(value))
            if self.fourcc_policy == "honor":
                self.props["FOURCC"] = float(value)
            elif self.fourcc_policy == "swap":
                self.props["FOURCC"] = float(fourcc_code("NV12"))
            elif self.fourcc_policy == "fallback":
                if requested == "YUY2":
                    self.props["FOURCC"] = float(value)
        return True


class FakeThread(CaptureThread):
    def __init__(self, fake, **kwargs):
        kwargs.setdefault("source", 0)
        kwargs.setdefault("queue", deque(maxlen=3))
        kwargs.setdefault("ring_buffer", deque(maxlen=8))
        kwargs.setdefault("stop_event", threading.Event())
        kwargs.setdefault("profile", default_profile("CAM-01"))
        super().__init__(**kwargs)
        self._fake = fake

    def _create_capture(self, api, params=()):
        return self._fake


def test_profile_schema_parses_and_tolerates_legacy_keys(tmp_path):
    path = tmp_path / "camera_profiles.yml"
    path.write_text(
        """
version: 1
cameras:
  CAM-01:
    enabled: false
    source: 0
    rtsp: {high: rtsp://h, low: rtsp://l}
    backend: msmf
    request: {width: 1280, height: 720, fps: 30, fourcc: MJPG, fallback_fourcc: YUY2}
    verify_mode: true
    drain_to_latest: true
    ring: {max_side: 960, seconds: 5.0, format: jpeg90, jpeg_quality: 90}
    reconnect: {initial_delay_s: 1.0, max_delay_s: 30.0, multiplier: 2.0, jitter: 0.2}
    priority: 3
    degradation:
      enabled: true
      steps:
        - {jpeg_quality: 75}
        - {ring_fps: 15}
        - {ring_max_side: 640}
        - {pause_annotation: true}
""",
        encoding="utf-8",
    )
    profiles = load_capture_profiles(path)
    profile = profiles["CAM-01"]
    assert profile.backend == "msmf"
    assert profile.request.fourcc == "MJPG"
    assert profile.acceptable_fourccs == ("MJPG", "YUY2")
    assert profile.ring.format == "jpeg90"
    assert profile.priority == 3
    assert [s.jpeg_quality for s in profile.degradation.steps] == [75, None, None, None]


def test_profile_rejects_unknown_ring_format(tmp_path):
    path = tmp_path / "camera_profiles.yml"
    path.write_text(
        "cameras:\n  CAM-01:\n    ring: {format: webp}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ring format"):
        load_capture_profiles(path)


def test_negotiated_mode_exact_match_is_not_mismatch():
    profile = default_profile("CAM-01")
    mode = verify_negotiated_mode(
        profile,
        {"width": 1280, "height": 720, "fps": 30.0, "fourcc": "MJPG"},
        "dshow",
    )
    assert not mode.mismatch
    assert mode.fallback_used is False


def test_yuy2_fallback_is_accepted_not_mismatch():
    profile = default_profile("CAM-01")
    mode = verify_negotiated_mode(
        profile,
        {"width": 1280, "height": 720, "fps": 30.0, "fourcc": "YUY2"},
        "dshow",
    )
    assert not mode.mismatch
    assert mode.fallback_used is True


def test_silent_mjpeg_swap_is_degraded_with_exact_log(caplog):
    fake = FakeNegotiatingCapture(fourcc_policy="swap")
    thread = FakeThread(fake)
    with caplog.at_level(logging.WARNING, logger="pipeline_capture"):
        assert thread.open() is True
    assert thread.negotiated is not None and thread.negotiated.mismatch
    assert thread.negotiated.mismatched_fields == ("fourcc",)
    assert thread.capture_state == "mode-mismatch"
    assert "Capture mode negotiation mismatch for CAM-01: requested=1280x720@30.0 MJPG actual=1280x720@30.0 NV12 mismatched=fourcc" in caplog.text
    details = thread.health_details()
    assert details["modeMismatch"] is True
    assert details["negotiatedFourcc"] == "NV12"
    assert details["requestedFourcc"] == "MJPG"


def test_resolution_and_fps_drift_is_degraded():
    fake = FakeNegotiatingCapture(fourcc_policy="ignore")
    fake.props["FRAME_WIDTH"] = 640.0
    fake.props["FRAME_HEIGHT"] = 480.0
    fake.props["FPS"] = 15.0
    thread = FakeThread(fake)
    assert thread.open() is True
    assert thread.negotiated.mismatched_fields == ("width", "height", "fps")
    assert thread.capture_state == "mode-mismatch"


def test_fallback_used_when_mjpg_refused():
    fake = FakeNegotiatingCapture(fourcc_policy="fallback")
    thread = FakeThread(fake)
    assert thread.open() is True
    assert thread.negotiated.fallback_used is True
    assert not thread.negotiated.mismatch
    assert thread.capture_state == "ok"


def test_verify_mode_false_skips_assertion_but_reports_actual():
    fake = FakeNegotiatingCapture(fourcc_policy="swap")
    profile = CaptureProfile(camera_id="CAM-01", verify_mode=False)
    thread = FakeThread(fake, profile=profile)
    assert thread.open() is True
    assert thread.negotiated is None
    assert thread.capture_state == "ok"


def test_usb_open_pins_backend_and_requests_720p30_mjpg():
    fake = FakeNegotiatingCapture(fourcc_policy="honor")
    thread = FakeThread(fake)
    assert thread.open() is True
    import cv2
    width_sets = [v for p, v in fake.set_calls if p == cv2.CAP_PROP_FRAME_WIDTH]
    fourcc_sets = [fourcc_str(float(v)) for p, v in fake.set_calls if p == cv2.CAP_PROP_FOURCC]
    assert width_sets and width_sets[0] == 1280
    assert fourcc_sets and fourcc_sets[0] == "MJPG"


def test_fourcc_codec_roundtrip():
    for tag in ("MJPG", "YUY2", "NV12"):
        assert fourcc_str(fourcc_code(tag)) == tag
    assert fourcc_str(0) == "NONE"
