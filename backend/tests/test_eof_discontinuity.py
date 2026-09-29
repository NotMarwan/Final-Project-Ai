"""Regression tests for prerecorded-media loop boundaries.

These tests replace all model constructors with deterministic fakes; they do
not load checkpoints or require a GPU.
"""
from collections import deque
import queue
import threading
import time
from types import SimpleNamespace

import numpy as np


def test_file_loop_boundary_drops_capture_render_decision_and_evidence_state(monkeypatch):
    import api

    isolated_state = api.AppState()
    monkeypatch.setattr(api, "state", isolated_state)

    camera_id = "boundary-camera"
    decision = isolated_state.decision_for_camera(camera_id)
    decision.update(0.99, sample_time=1.0, sample_id=1, current_time=1.0)
    isolated_state.set_detection_meta(camera_id, {"inference_sequence": 7})

    render_queue = deque(["old-render"])
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    ring_buffer = deque([(10.0, frame)])
    evidence_lock = threading.Lock()
    post = queue.Queue(maxsize=2)
    post.put((10.0, frame))
    active_post_queues = [post]
    renderer = SimpleNamespace(
        _last_result={"inference_sequence": 7},
        _legacy_sequence=7,
        _health={"violence": {"status": "OK"}},
    )

    class Cache:
        def __init__(self):
            self.updates = []

        def update(self, **kwargs):
            self.updates.append(kwargs)

    cache = Cache()

    api._reset_file_loop_boundary(
        camera_id,
        render_queue,
        ring_buffer,
        evidence_lock,
        active_post_queues,
        renderer=renderer,
        cache=cache,
    )

    assert not render_queue
    assert not ring_buffer
    assert not active_post_queues
    assert post.get_nowait()[0] == 10.0
    assert post.get_nowait() is None
    assert isolated_state.get_detection_meta(camera_id) == {}
    assert decision.status()["history_count"] == 0
    assert renderer._last_result == {}
    assert renderer._legacy_sequence == 0
    assert renderer._health == {}
    assert cache.updates[-1]["tracks"] == []
    assert cache.updates[-1]["violence_conf"] == 0.0
    assert cache.updates[-1]["weapon_score"] == 0.0


def test_inference_reset_handshake_drops_tail_and_restarts_model_state(monkeypatch):
    import inference
    import inference_process
    import weapon
    from temporal_frames import FramePacket

    violence_engines = []
    weapon_engines = []

    class FakeViolence:
        enabled = True
        disabled_reason = ""
        last_error = ""

        def __init__(self, *args, **kwargs):
            self._state_lock = threading.Lock()
            self._last_conf = 0.9
            self._last_calibrated_conf = 0.9
            self._observation_id = 0
            self._completed_at = 0.0
            self.window_status = {}
            self.reset_count = 0
            self.processed_values = []
            violence_engines.append(self)

        def process_frame(self, frame, captured_at, nominal_fps):
            value = int(frame[0, 0, 0])
            self.processed_values.append(value)
            with self._state_lock:
                self._observation_id += 1
                self._completed_at = time.monotonic()
                self.window_status = {
                    "frames_collected": 32,
                    "frames_required": 32,
                    "span_seconds": 1.0,
                    "valid": True,
                }

        def reset(self):
            self.reset_count += 1
            with self._state_lock:
                self._observation_id = 0
                self._completed_at = 0.0
                self.window_status = {}

    class FakeWeapon:
        enabled = True

        def __init__(self, *args, **kwargs):
            self.observation_id = 0
            self.reset_count = 0
            self.processed_values = []
            weapon_engines.append(self)

        def preload(self):
            return True

        def status(self):
            return {"ready": True, "failed": False, "reason": "ok"}

        def process_frame(self, frame, observed_at=None):
            self.processed_values.append(int(frame[0, 0, 0]))
            self.observation_id += 1

        def latest_signal(self):
            return {
                "score": 0.1,
                "labels": [],
                "bbox": None,
                "observation_score": 0.1,
                "observation_valid": True,
                "observation_id": self.observation_id,
                "completed_at": time.monotonic(),
                "reason": "ok",
            }

        def reset(self):
            self.reset_count += 1
            self.observation_id = 0

        def close(self):
            pass

    monkeypatch.setattr(inference, "ViolenceInferencePipeline", FakeViolence)
    monkeypatch.setattr(weapon, "WeaponSignalEngine", FakeWeapon)

    stop_event = threading.Event()
    reset_event = threading.Event()
    results = []

    class BoundaryQueue:
        def __init__(self, items):
            self.items = deque(items)

        def get(self, timeout=None):
            deadline = time.monotonic() + (timeout or 0.1)
            while not self.items:
                if time.monotonic() >= deadline:
                    raise queue.Empty
                time.sleep(0.001)
            return self.items.popleft()

        def get_nowait(self):
            if not self.items:
                raise queue.Empty
            return self.items.popleft()

    def packet(value, sequence):
        captured_at = time.monotonic()
        return FramePacket(
            np.full((8, 8, 3), value, dtype=np.uint8),
            sequence,
            captured_at,
            8,
            8,
            30.0,
            {},
            sample_timestamp=100.0 + value,
        )

    frame_queue = BoundaryQueue([packet(1, 1), packet(2, 2)])

    class ResultQueue:
        def __init__(self):
            self.pending = deque()

        def put(self, result, timeout=None):
            results.append(result)
            self.pending.append(result)
            if len(results) == 1:
                reset_event.set()
            elif len(results) == 2:
                stop_event.set()

        def get_nowait(self):
            if not self.pending:
                raise queue.Empty
            return self.pending.popleft()

    result_queue = ResultQueue()

    class ResetAck:
        def __init__(self):
            self.count = 0

        def set(self):
            self.count += 1
            # This represents the next epoch arriving after the child has
            # drained the stale tail and acknowledged the reset.
            frame_queue.items.append(packet(3, 3))

    reset_ack = ResetAck()
    inference_process.inference_worker(
        frame_queue,
        result_queue,
        stop_event,
        {
            "device": "cpu",
            "person_overlay_enabled": False,
            "reset_event": reset_event,
            "reset_ack": reset_ack,
        },
    )

    assert violence_engines[0].processed_values == [1, 3]
    assert weapon_engines[0].processed_values == [1, 3]
    assert violence_engines[0].reset_count == 1
    assert weapon_engines[0].reset_count == 1
    assert reset_ack.count == 1
    assert len(results) == 2
    assert results[0]["observation_valid"]
    assert results[1]["observation_valid"]
    assert results[1]["violence_observation_id"] == 1
    assert results[1]["weapon_observation_id"] == 1


# --- G-07 window contract under queue policy (WT-15) -------------------------

def test_temporal_window_rejects_gaps_without_fabricating_samples():
    from temporal_frames import TemporalWindow

    fps = 30.0
    # Uninterrupted 32-frame window at 30 fps is valid.
    window = TemporalWindow(frames=32, nominal_fps=fps)
    stamps = [i / fps for i in range(32)]
    for stamp in stamps:
        assert window.push(stamp, stamp)
    status = window.status()
    assert status["valid"] is True
    assert status["frames_collected"] == 32

    # A single dropped frame (one gap of 2/fps) stays inside BOTH bounds:
    # gap <= 2.1/fps and span within 10% of nominal (32/30 vs 31/30).
    window = TemporalWindow(frames=32, nominal_fps=fps)
    stamp = 0.0
    window.push(stamp, stamp)
    for i in range(31):
        stamp += 2.0 / fps if i == 15 else 1.0 / fps
        window.push(stamp, stamp)
    status = window.status()
    assert status["frames_collected"] == 32
    assert status["valid"] is True

    # Two or more consecutive dropped frames (gap 3/fps) invalidates the
    # window — a latest-wins drain that skips 2+ frames can NEVER produce a
    # fake-valid window (missing frames are not replaced by fake samples).
    window = TemporalWindow(frames=32, nominal_fps=fps)
    stamp = 0.0
    window.push(stamp, stamp)
    for i in range(31):
        stamp += 3.0 / fps
        window.push(stamp, stamp)
    status = window.status()
    assert status["valid"] is False
    assert status["frames_collected"] == 32  # no fabrication: only real samples

    # Non-monotonic stamps are rejected outright.
    window = TemporalWindow(frames=4, nominal_fps=fps)
    assert window.push(1.0, 1.0) is True
    assert window.push(1.0, 2.0) is False
    assert window.push(0.5, 3.0) is False
    assert window.status()["frames_collected"] == 1


def test_worker_propagates_invalid_window_as_degraded_health(monkeypatch):
    """G-07 at the worker boundary: invalid windows are surfaced, never smoothed."""
    import threading
    import time

    import numpy as np

    import inference
    import inference_process
    import weapon
    from temporal_frames import FramePacket

    class InvalidWindowViolence:
        enabled = True
        disabled_reason = ""
        last_error = ""

        def __init__(self, *args, **kwargs):
            self._state_lock = threading.Lock()
            self._last_conf = 0.0
            self._last_calibrated_conf = 0.0
            self._observation_id = 0
            self._completed_at = 0.0
            self.window_status = {}

        def process_frame(self, frame, captured_at=None, nominal_fps=30.0, source_captured_at=None):
            with self._state_lock:
                self.window_status = {
                    "frames_collected": 32,
                    "frames_required": 32,
                    "span_seconds": 1.2,
                    "nominal_span_seconds": 1.0,
                    "valid": False,
                }

        def reset(self):
            pass

    class NoWeapon:
        enabled = False

        def __init__(self, *args, **kwargs):
            pass

        def status(self):
            return {"ready": False, "failed": False, "reason": "disabled"}

        def close(self):
            pass

    monkeypatch.setattr(inference, "ViolenceInferencePipeline", InvalidWindowViolence)
    monkeypatch.setattr(weapon, "WeaponSignalEngine", NoWeapon)

    stop_event = threading.Event()
    results = []

    class OneShotQueue:
        def __init__(self):
            self.items = [
                FramePacket(
                    np.zeros((8, 8, 3), dtype=np.uint8),
                    1,
                    time.monotonic(),
                    8,
                    8,
                    30.0,
                    {},
                    sample_timestamp=100.0,
                )
            ]

        def get(self, timeout=None):
            if self.items:
                return self.items.pop(0)
            raise queue.Empty

        def get_nowait(self):
            if not self.items:
                raise queue.Empty
            return self.items.pop(0)

    class ResultQueue:
        def put(self, result, timeout=None):
            results.append(result)
            stop_event.set()

    inference_process.inference_worker(
        OneShotQueue(),
        ResultQueue(),
        stop_event,
        {"device": "cpu", "person_overlay_enabled": False},
    )

    assert len(results) == 1
    result = results[0]
    assert result["window_valid"] is False
    assert result["window_clock_source"] == "file-media"
    violence_health = result["pipeline_health"]["violence"]
    assert violence_health["status"] == "DEGRADED"
    assert "Invalid temporal window" in violence_health["reason"]
