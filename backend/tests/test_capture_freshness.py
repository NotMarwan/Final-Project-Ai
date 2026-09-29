"""WT-14 capture freshness: drop counters, read-gap stats, backoff reconnect.

Covers E-3 (drop detection harness) and the reconnect-storm contract:
exponential backoff with jitter replaces the fixed 2s sleep; drop-NEWEST on
the bounded inference queue is counted (runtime-map R-2 closure).  All timing
assertions use scripted clocks — the suite is timing-independent.
"""
import queue
import threading
from collections import deque

import numpy as np
import pytest

from pipeline_capture import (
    CaptureProfile,
    CaptureStats,
    CaptureThread,
    ReconnectConfig,
    bounded_put_drop_newest,
    fourcc_code,
    next_backoff_delay,
)


class ScriptedClock:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.values.pop(0) if self.values else float(self.calls)


class FakeFrameCapture:
    """cv2.VideoCapture stand-in with REAL grab/retrieve semantics:

    grab() advances to the next buffered frame (blocking readers return False
    at end of stream); retrieve() decodes the frame grabbed last.
    """

    def __init__(self, frames):
        self.frames = list(frames)
        self._grabbed = None
        self.opened = True
        self.grabs = 0
        self.props = {
            "FRAME_WIDTH": 1280.0,
            "FRAME_HEIGHT": 720.0,
            "FPS": 30.0,
            "FOURCC": float(fourcc_code("MJPG")),
            "BUFFERSIZE": 0.0,
        }

    def isOpened(self):
        return self.opened

    def set(self, prop, value):
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
        return self.props.get(mapping.get(prop, ""), 0.0)

    def read(self):
        if self.frames:
            self._grabbed = self.frames.pop(0)
            return True, self._grabbed
        return False, None

    def grab(self):
        self.grabs += 1
        if self.frames:
            self._grabbed = self.frames.pop(0)
            return True
        return False

    def retrieve(self):
        if self._grabbed is None:
            return False, None
        return True, self._grabbed

    def release(self):
        self.opened = False


class FlakySourceThread(CaptureThread):
    """open() fails `failures` times, then succeeds."""

    def __init__(self, failures, **kwargs):
        kwargs.setdefault("source", 0)
        kwargs.setdefault("queue", deque(maxlen=3))
        kwargs.setdefault("ring_buffer", deque(maxlen=8))
        kwargs.setdefault("stop_event", threading.Event())
        super().__init__(**kwargs)
        self.failures = failures
        self.open_attempts = 0

    def _create_capture(self, api, params=()):
        self.open_attempts += 1
        fake = FakeFrameCapture([np.zeros((8, 8, 3), dtype=np.uint8)])
        if self.open_attempts <= self.failures:
            fake.opened = False
        return fake


class RecordingEvent:
    def __init__(self, fired=False):
        self.delays = []
        self.fired = fired

    def wait(self, timeout=None):
        self.delays.append(timeout)
        return self.fired

    def is_set(self):
        return self.fired

    def set(self):
        self.fired = True


def test_backoff_schedule_grows_and_caps():
    cfg = ReconnectConfig(initial_delay_s=1.0, max_delay_s=30.0, multiplier=2.0, jitter=0.0)
    delays = [next_backoff_delay(n, cfg) for n in range(1, 9)]
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]


def test_backoff_jitter_stays_within_bounds():
    cfg = ReconnectConfig(initial_delay_s=1.0, max_delay_s=30.0, multiplier=2.0, jitter=0.2)
    import random
    rng = random.Random(1234)
    for attempt in range(1, 12):
        base = min(30.0, 1.0 * (2.0 ** (attempt - 1)))
        for _ in range(20):
            delay = next_backoff_delay(attempt, cfg, rng=rng)
            assert base * 0.8 - 1e-9 <= delay <= base * 1.2 + 1e-9


def test_reconnect_storm_backs_off_counts_and_recovers():
    profile = CaptureProfile(
        camera_id="CAM-01",
        reconnect=ReconnectConfig(initial_delay_s=0.01, max_delay_s=0.05, multiplier=2.0, jitter=0.0),
    )
    thread = FlakySourceThread(failures=5, profile=profile)
    thread.stop_event = RecordingEvent()
    assert thread.open() is False  # initial open fails (attempt 1)
    recovered = False
    for _ in range(6):
        if thread.reconnect():
            recovered = True
            break
    assert recovered
    assert thread.stats.reconnects == 1
    assert thread.stop_event.delays[:5] == [0.01, 0.02, 0.04, 0.05, 0.05]
    assert thread.capture_state == "ok"
    assert thread.negotiated is not None and not thread.negotiated.mismatch


def test_reconnect_failure_state_is_interrupted():
    profile = CaptureProfile(
        camera_id="CAM-01",
        reconnect=ReconnectConfig(initial_delay_s=0.001, max_delay_s=0.002, jitter=0.0),
    )
    thread = FlakySourceThread(failures=3, profile=profile)
    thread.stop_event = RecordingEvent()
    assert thread.open() is False
    assert thread.reconnect() is False
    assert thread.capture_state == "interrupted"


def test_stop_interrupts_backoff_wait():
    profile = CaptureProfile(
        camera_id="CAM-01",
        reconnect=ReconnectConfig(initial_delay_s=5.0, max_delay_s=30.0, jitter=0.0),
    )
    thread = FlakySourceThread(failures=1, profile=profile)
    thread.stop_event = RecordingEvent(fired=True)
    assert thread.open() is False
    assert thread.reconnect() is False  # stop wins; no open retry


def test_bounded_put_counts_drops_not_silently():
    stats = CaptureStats()
    frame_queue = queue.Queue(maxsize=2)
    assert bounded_put_drop_newest(frame_queue, "p1", stats) is True
    assert bounded_put_drop_newest(frame_queue, "p2", stats) is True
    assert bounded_put_drop_newest(frame_queue, "p3", stats) is False
    assert stats.frame_queue_dropped == 1
    assert stats.snapshot()["frameQueueDropped"] == 1
    assert stats.snapshot()["frameQueueDepth"] == 2


def test_read_gap_stats_stage_read_and_duplicates():
    frames = [
        np.full((8, 8, 3), 10, dtype=np.uint8),
        np.full((8, 8, 3), 10, dtype=np.uint8),  # duplicate
        np.full((8, 8, 3), 200, dtype=np.uint8),
    ]
    fake = FakeFrameCapture(frames)
    # read() consumes two clock ticks (started, finished): gaps are measured
    # between read-complete stamps -> 1.043-1.004 and 1.082-1.043 = 39ms.
    clock = ScriptedClock([1.000, 1.004, 1.040, 1.043, 1.080, 1.082])
    thread = CaptureThread(
        "rtsp://cam", deque(maxlen=3), deque(maxlen=8), threading.Event(),
        profile=CaptureProfile(camera_id="CAM-01", drain_to_latest=False),
        clock=clock,
    )
    thread.cap = fake
    for _ in range(3):
        ok, frame = thread.read_frame()
        assert ok
    snap = thread.stats.snapshot()
    assert snap["framesReadCount"] == 3
    assert snap["duplicateFrameCount"] == 1
    assert snap["readGapSampleCount"] == 2
    assert snap["stageFrameReadSampleCount"] == 3
    assert snap["readGapP50Ms"] == pytest.approx(39.0, abs=0.5)
    assert snap["readGapMaxMs"] == pytest.approx(39.0, abs=0.5)
    assert snap["stageFrameReadP50Ms"] == pytest.approx(3.0, abs=0.5)


def test_file_media_index_counts_skipped_frames_and_invalidates_window():
    """E-2 acceptance (deterministic): skip runs must NOT look like 32@fps."""
    from temporal_frames import TemporalWindow

    def collect(skip, n=4):
        frames = [np.full((4, 4, 3), i, dtype=np.uint8) for i in range(30)]
        th = CaptureThread("clip.mp4", deque(maxlen=3), deque(maxlen=8), threading.Event(),
                           file_skip_frames=skip)
        th.cap = FakeFrameCapture(frames)
        stamps = []
        for _ in range(n):
            ok, _ = th.read_frame()
            assert ok
            stamps.append(th.last_media_index / 30.0)
        window = TemporalWindow(frames=n, nominal_fps=30.0)
        for stamp in stamps:
            assert window.push(stamp, None)
        return stamps, window.status()

    stamps, status = collect(skip=2)
    assert stamps == [0.0, 0.1, 0.2, 0.3]  # media frames 0,3,6,9 (3 consumed/read)
    assert status["valid"] is False
    stamps, status = collect(skip=0)
    assert stamps == [0.0, 1 / 30, 2 / 30, 3 / 30]
    assert status["valid"] is True


def test_drain_to_latest_returns_newest_and_respects_budget():
    frames = [np.full((4, 4, 3), i, dtype=np.uint8) for i in range(5)]
    fake = FakeFrameCapture(frames)
    thread = CaptureThread(
        "rtsp://cam", deque(maxlen=3), deque(maxlen=8), threading.Event(),
        profile=CaptureProfile(camera_id="CAM-01", drain_to_latest=True,
                               drain_budget_s=1.0, max_drain=30),
    )
    thread.cap = fake
    ok, frame = thread.read_frame()
    assert ok
    assert fake.grabs == 6  # 5 successful grabs drained the backlog + 1 EOS probe
    assert int(frame[0, 0, 0]) == 4  # newest frame won

    fake2 = FakeFrameCapture([np.full((4, 4, 3), i, dtype=np.uint8) for i in range(5)])
    thread2 = CaptureThread(
        "rtsp://cam", deque(maxlen=3), deque(maxlen=8), threading.Event(),
        profile=CaptureProfile(camera_id="CAM-01", drain_to_latest=True,
                               drain_budget_s=0.0, max_drain=30),
    )
    thread2.cap = fake2
    ok, frame = thread2.read_frame()
    assert ok
    assert fake2.grabs == 1  # zero budget: one grab, no runaway drain
    assert int(frame[0, 0, 0]) == 0
