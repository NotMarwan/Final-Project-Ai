from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

import torch

from backend import inference


class ViolenceAutocastTests(unittest.TestCase):
    def test_fp16_autocast_is_used_for_cuda_when_enabled(self):
        model = Mock(return_value=torch.tensor([1.0]))
        pipeline = SimpleNamespace(device=torch.device("cuda"), model=model)
        autocast_context = nullcontext()

        with patch.object(inference, "VIOLENCE_FP16_AUTOCAST", True), patch.object(
            inference.torch, "autocast", return_value=autocast_context
        ) as autocast:
            result = inference.ViolenceInferencePipeline._forward_with_optional_autocast(
                pipeline, torch.tensor([0.5])
            )

        autocast.assert_called_once_with("cuda", dtype=torch.float16)
        model.assert_called_once()
        self.assertEqual(result.tolist(), [1.0])

    def test_fp16_autocast_is_skipped_when_disabled_or_on_cpu(self):
        model = Mock(return_value=torch.tensor([1.0]))
        pipeline = SimpleNamespace(device=torch.device("cpu"), model=model)

        with patch.object(inference, "VIOLENCE_FP16_AUTOCAST", True), patch.object(
            inference.torch, "autocast"
        ) as autocast:
            result = inference.ViolenceInferencePipeline._forward_with_optional_autocast(
                pipeline, torch.tensor([0.5])
            )

        autocast.assert_not_called()
        model.assert_called_once()
        self.assertEqual(result.tolist(), [1.0])

        pipeline.device = torch.device("cuda")
        with patch.object(inference, "VIOLENCE_FP16_AUTOCAST", False), patch.object(
            inference.torch, "autocast"
        ) as autocast:
            inference.ViolenceInferencePipeline._forward_with_optional_autocast(
                pipeline, torch.tensor([0.5])
            )

        autocast.assert_not_called()


class ViolenceOptimizationDefaultsTests(unittest.TestCase):
    """Full-pipeline replay (bench/results/perf-r3-final-*) showed worse p95 with these on."""

    def test_cuda_experiments_are_off_unless_explicitly_enabled(self):
        import os

        flags = {
            "AI_SENTINEL_VIOLENCE_CUDNN_BENCHMARK": inference.VIOLENCE_CUDNN_BENCHMARK,
            "AI_SENTINEL_VIOLENCE_CHANNELS_LAST_3D": inference.VIOLENCE_CHANNELS_LAST_3D,
            "AI_SENTINEL_VIOLENCE_PINNED_HOST_TENSOR": inference.VIOLENCE_PINNED_HOST_TENSOR,
            "AI_SENTINEL_VIOLENCE_FP16_AUTOCAST": inference.VIOLENCE_FP16_AUTOCAST,
            "AI_SENTINEL_VIOLENCE_WARMUP_AT_LOAD": inference.VIOLENCE_WARMUP_AT_LOAD,
        }
        for name, enabled in flags.items():
            if name not in os.environ:
                self.assertFalse(enabled, name)


# ---------------------------------------------------------------------------
# Worker/resource architecture (S-01, WT-15): telemetry contract, queue policy,
# drop accounting, allocation rule. Model constructors are deterministic fakes;
# no checkpoints or GPU are required.
# ---------------------------------------------------------------------------
import threading
import time
from collections import deque

import numpy as np


class FakeViolence:
    enabled = True
    disabled_reason = ""
    last_error = ""

    def __init__(self, *args, window_valid=True, **kwargs):
        self._state_lock = threading.Lock()
        self._last_conf = 0.0
        self._last_calibrated_conf = 0.0
        self._observation_id = 0
        self._completed_at = 0.0
        self.window_status = {}
        self.window_valid = window_valid
        self.processed_values = []

    def process_frame(self, frame, captured_at=None, nominal_fps=30.0, source_captured_at=None):
        self.processed_values.append(int(frame[0, 0, 0]))
        with self._state_lock:
            self._observation_id += 1
            self._completed_at = time.monotonic()
            self.window_status = {
                "frames_collected": 32,
                "frames_required": 32,
                "span_seconds": 1.0,
                "nominal_span_seconds": 1.0,
                "valid": self.window_valid,
            }

    def reset(self):
        with self._state_lock:
            self._observation_id = 0
            self._completed_at = 0.0
            self.window_status = {}


class FakeWeapon:
    enabled = True

    def __init__(self, *args, **kwargs):
        self.observation_id = 0
        self.processed_values = []

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
        self.observation_id = 0

    def close(self):
        pass


import queue as _queue_mod


class FakeQueue:
    """mp.Queue-shaped fake exposing get/put/get_nowait/qsize (qsize optional)."""

    def __init__(self, items=(), with_qsize=True):
        self.items = deque(items)
        if with_qsize:
            self.qsize = lambda: len(self.items)

    def get(self, timeout=None):
        deadline = time.monotonic() + (timeout or 0.1)
        while not self.items:
            if time.monotonic() >= deadline:
                raise _queue_mod.Empty
            time.sleep(0.001)
        return self.items.popleft()

    def get_nowait(self):
        if not self.items:
            raise _queue_mod.Empty
        return self.items.popleft()

    def put(self, item, timeout=None):
        self.items.append(item)


def _packet(value, sequence, *, fps=30.0):
    from temporal_frames import FramePacket

    captured_at = time.monotonic()
    return FramePacket(
        np.full((8, 8, 3), value, dtype=np.uint8),
        sequence,
        captured_at,
        8,
        8,
        fps,
        {},
        sample_timestamp=100.0 + value,
    )


def _run_worker(monkeypatch, packets, *, queue_policy="drop-newest", expected_results=None,
                window_valid=True, extra_config=None, with_qsize=True):
    import inference
    import inference_process
    import weapon

    monkeypatch.setattr(inference, "ViolenceInferencePipeline", FakeViolence)
    monkeypatch.setattr(weapon, "WeaponSignalEngine", FakeWeapon)

    stop_event = threading.Event()
    results = []
    expected = expected_results if expected_results is not None else len(packets)

    frame_queue = FakeQueue(packets, with_qsize=with_qsize)

    class ResultQueue(FakeQueue):
        def put(self, item, timeout=None):
            results.append(item)
            if len(results) >= expected:
                stop_event.set()

    result_queue = ResultQueue()
    config = {
        "device": "cpu",
        "person_overlay_enabled": False,
        "queue_policy": queue_policy,
    }
    if extra_config:
        config.update(extra_config)
    inference_process.inference_worker(frame_queue, result_queue, stop_event, config)
    return results


LOCKED_TELEMETRY_FIELDS = (
    "processRunId", "workerPid", "captureClockBase", "queuePolicy",
    "personCompletedCount", "violenceCompletedCount", "weaponCompletedCount",
    "active_track_count", "frameQueueDroppedDerived", "frameQueueDiscardedByPolicy",
    "frameQueueDiscardedAtReset", "resultQueueDropped",
    "capturedAtMonoMs", "inferenceStartedAtMonoMs", "dequeuedAtMonoMs",
    "frameAgeMs", "frameAgeClockSource", "stagePreprocessMs", "stageInferenceWaitMs",
    "stageSerializeMs", "startupModelLoadMs", "startupFirstFrameMs",
    "startupFirstResultMs", "startupFirstObservationMs",
)


def test_result_carries_locked_telemetry_fields(monkeypatch):
    results = _run_worker(monkeypatch, [_packet(1, 1), _packet(2, 2)], expected_results=2)
    assert len(results) == 2
    for field in LOCKED_TELEMETRY_FIELDS:
        assert field in results[-1], field
    assert results[-1]["frameAgeClockSource"] == "monotonic-capture"
    assert results[-1]["captureClockBase"] in ("monotonic-gettickcount64", "perf-qpc")
    assert results[-1]["workerPid"] > 0
    assert results[-1]["violenceCompletedCount"] == 2
    assert results[-1]["weaponCompletedCount"] == 2
    assert results[-1]["active_track_count"] == results[-1]["person_count"]


def test_frame_age_is_same_clock_domain_difference(monkeypatch):
    results = _run_worker(monkeypatch, [_packet(1, 1)], expected_results=1)
    result = results[0]
    recomputed = result["inferenceStartedAtMonoMs"] - result["capturedAtMonoMs"]
    assert abs(result["frameAgeMs"] - recomputed) < 1e-6
    assert result["frameAgeMs"] >= 0.0


def test_frame_queue_dropped_derived_counts_producer_gaps(monkeypatch):
    # Capture-loop sequence 1,2,5,6: frames 3 and 4 never arrived (R-2 drops).
    results = _run_worker(
        monkeypatch, [_packet(1, 1), _packet(2, 2), _packet(3, 5), _packet(4, 6)],
        expected_results=4,
    )
    assert results[-1]["frameQueueDroppedDerived"] == 2
    assert results[-1]["frameQueueDiscardedByPolicy"] == 0


def test_latest_wins_policy_discards_stale_packets_without_drop_credit(monkeypatch):
    results = _run_worker(
        monkeypatch,
        [_packet(1, 1), _packet(2, 2), _packet(3, 3)],
        queue_policy="latest-wins",
        expected_results=1,
    )
    assert len(results) == 1
    # Only the freshest packet is processed; the two stale ones are policy
    # discards, never counted as producer drops.
    assert results[0]["frame_idx"] == 1
    assert results[0]["frameQueueDiscardedByPolicy"] == 2
    assert results[0]["frameQueueDroppedDerived"] == 0
    assert results[0]["queuePolicy"] == "latest-wins"


def test_unknown_queue_policy_is_visible_not_silent(monkeypatch):
    results = _run_worker(
        monkeypatch, [_packet(1, 1)], queue_policy="bogus-policy", expected_results=1
    )
    result = results[0]
    assert result["queuePolicy"] == "drop-newest"
    delivery = result["pipeline_health"].get("delivery", {})
    assert delivery.get("status") == "DEGRADED"
    assert "bogus-policy" in delivery.get("reason", "")


def test_result_queue_full_counts_drop_and_marks_health(monkeypatch):
    import inference
    import inference_process
    import weapon
    from queue import Full

    monkeypatch.setattr(inference, "ViolenceInferencePipeline", FakeViolence)
    monkeypatch.setattr(weapon, "WeaponSignalEngine", FakeWeapon)

    results = []

    class FlakyResultQueue:
        """Rejects the first put (queue full), accepts afterwards."""

        def __init__(self):
            self.rejected = False

        def put(self, item, timeout=None):
            if not self.rejected:
                self.rejected = True
                raise Full
            results.append(item)
            if len(results) >= 1:
                stop_event.set()

        def get_nowait(self):
            raise _queue_mod.Empty

    stop_event = threading.Event()
    frame_queue = FakeQueue([_packet(1, 1), _packet(2, 2)])
    inference_process.inference_worker(
        frame_queue,
        FlakyResultQueue(),
        stop_event,
        {"device": "cpu", "person_overlay_enabled": False},
    )
    # The dropped result is observed as a cumulative counter on the next
    # result (counters ride the following payload), with a visible health mark.
    assert len(results) == 1
    assert results[0]["frame_idx"] == 2
    assert results[0]["resultQueueDropped"] == 1
    assert results[0]["pipeline_health"]["delivery"]["status"] == "DEGRADED"
    assert "full" in results[0]["pipeline_health"]["delivery"]["reason"].lower()


def test_allocation_rule_dedicates_then_pools_at_trigger(monkeypatch):
    from frame_pipeline import plan_inference_allocation, POOLING_TRIGGER_CAMERAS

    assert POOLING_TRIGGER_CAMERAS == 3
    for n in (1, 2):
        plan = plan_inference_allocation(n)
        assert plan["mode"] == "dedicated-per-camera"
        assert plan["inference_processes"] == n
        assert plan["violence_pool_size"] == n
    for n in (3, 4, 8):
        plan = plan_inference_allocation(n)
        assert plan["mode"] == "pooled-violence"
        assert plan["violence_pool_size"] == 1
        assert plan["inference_processes"] == n + 1
        assert plan["weapon_person_workers"] == n


def test_allocation_rule_never_guesses_unmeasured_vram(monkeypatch):
    from frame_pipeline import plan_inference_allocation

    plan = plan_inference_allocation(2)
    assert plan["estimated_vram_gb"] is None
    assert "per_camera_process_vram_gb" in plan["unmeasured"]
    assert "fits_budget" not in plan
    plan = plan_inference_allocation(2, per_camera_process_vram_gb=1.0)
    assert plan["estimated_vram_gb"] == 2.0
    assert plan["headroom_gb"] == 10.0
    assert plan["fits_budget"] is True
    plan = plan_inference_allocation(3, per_camera_pooled_vram_gb=2.0)
    assert plan["estimated_vram_gb"] == 8.0  # 3 camera workers + 1 violence pool worker


def test_allocation_rule_rejects_invalid_inputs(monkeypatch):
    from frame_pipeline import plan_inference_allocation
    import pytest

    with pytest.raises(ValueError):
        plan_inference_allocation(0)
    with pytest.raises(ValueError):
        plan_inference_allocation(2, vram_budget_gb=0.0)
