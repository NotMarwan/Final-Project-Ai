"""G-07 temporal-window integrity assertions (WT-19 / S-02).

Every valid window MUST span (window_size-1)/nominal_fps ± 10 %. Asserted here
across the R3 sweep grid {window 16, 32} x fps {25, 30} and at the tolerance
boundaries, plus the pipeline-level window identity bookkeeping (R7).
"""
import threading

import numpy as np
import pytest
import torch

import inference
from inference import ViolenceInferencePipeline, assess_window_integrity


WINDOW_GRID = [16, 32]
FPS_GRID = [25.0, 30.0]


def stamps_for(window_size, fps, jitter=0.0, gap_scale=1.0):
    """Timestamps with a uniform span stretch (jitter, in fraction of nominal)."""
    nominal = (window_size - 1) / fps
    span = nominal * (1.0 + jitter)
    if window_size == 1:
        return [0.0]
    step = span * gap_scale / (window_size - 1)
    return [i * step for i in range(window_size)]


@pytest.mark.parametrize("window_size", WINDOW_GRID)
@pytest.mark.parametrize("fps", FPS_GRID)
def test_g07_valid_windows_within_ten_percent(window_size, fps):
    for jitter in (0.0, 0.05, -0.05, 0.09, -0.09):
        result = assess_window_integrity(stamps_for(window_size, fps, jitter), window_size, fps)
        assert result["valid"], (window_size, fps, jitter, result["integrity_reason"])
        nominal = (window_size - 1) / fps
        # G-07: every valid window's wall-clock span within ±10 % of nominal.
        assert abs(result["span_seconds"] - nominal) <= nominal * 0.10 + 1e-12


@pytest.mark.parametrize("window_size", WINDOW_GRID)
@pytest.mark.parametrize("fps", FPS_GRID)
@pytest.mark.parametrize("jitter", [0.11, -0.11, 0.25])
def test_g07_span_outside_tolerance_invalid(window_size, fps, jitter):
    result = assess_window_integrity(stamps_for(window_size, fps, jitter), window_size, fps)
    assert not result["valid"]
    assert "span-out-of-tolerance" in result["integrity_reason"]


@pytest.mark.parametrize("window_size", WINDOW_GRID)
def test_gap_bound_is_enforced(window_size):
    fps = 30.0
    bound = 2.1 / fps
    # One stretched gap just under the bound (valid) and one just over (invalid).
    # Exact-boundary equality is float-fragile in both legacy and current code
    # (`max(gaps) <= 2.1/fps`), so enforcement is asserted at 0.99x/1.01x.
    base = stamps_for(window_size - 1, fps)
    under = base + [base[-1] + bound * 0.99]
    result = assess_window_integrity(under, window_size, fps)
    assert result["valid"], result["integrity_reason"]
    over = base + [base[-1] + bound * 1.01]
    result = assess_window_integrity(over, window_size, fps)
    assert not result["valid"]
    assert "gap-over-bound" in result["integrity_reason"]


def test_non_increasing_stamp_invalid():
    stamps = [i / 30 for i in range(16)]
    stamps[5] = stamps[4]
    stamps[7] = stamps[8]
    result = assess_window_integrity(stamps, 16, 30.0)
    assert not result["valid"]
    assert "non-increasing-stamp" in result["integrity_reason"]


def test_incomplete_window_invalid():
    result = assess_window_integrity([i / 30 for i in range(10)], 16, 30.0)
    assert not result["valid"]
    assert "incomplete" in result["integrity_reason"]


def test_no_clock_only_checks_completeness():
    # Legacy direct calls have no source clock contract.
    result = assess_window_integrity([0.0] * 16, 16, 30.0, has_clock=False)
    assert result["valid"]
    result = assess_window_integrity([0.0] * 5, 16, 30.0, has_clock=False)
    assert not result["valid"]


class _FakeModel:
    logits = torch.tensor([[0.0, 0.0]])

    def __init__(self, *args, **kwargs):
        self.architecture_id = "fake"

    def load_state_dict(self, state_dict, strict=True):
        return None

    def to(self, device):
        return self

    def eval(self):
        return self

    def __call__(self, slow, fast):
        return _FakeModel.logits


def make_pipeline(monkeypatch, tmp_path, **kwargs):
    weights = tmp_path / "w.pt"
    weights.write_bytes(b"x")
    monkeypatch.setattr(inference, "ViolenceDetector", _FakeModel)
    monkeypatch.setattr(inference, "X3DViolenceModel", _FakeModel)
    monkeypatch.setattr(inference.torch, "load", lambda *a, **k: {
        "sf.backbone.blocks.0.multipathway_blocks.0.conv.weight": torch.zeros(1),
        "head.1.weight": torch.zeros(2, 4),
    })
    return ViolenceInferencePipeline(str(weights), torch.device("cpu"), **kwargs)


def test_window_status_reports_integrity_fields_and_configured_size(monkeypatch, tmp_path):
    pipe = make_pipeline(monkeypatch, tmp_path, window_size=16, stride=8)
    assert pipe.window_size == 16
    submissions = []
    monkeypatch.setattr(pipe, "_infer_window_async",
                        lambda *a, **k: submissions.append((a, k)))
    for i in range(16):
        pipe.process_frame(np.zeros((8, 8, 3), np.uint8), captured_at=100.0 + i / 30, nominal_fps=30.0)
    status = pipe.window_status
    assert status["frames_required"] == 16
    assert status["frames_collected"] == 16
    assert status["valid"]
    assert status["integrity_reason"] == "ok"
    assert abs(status["span_seconds"] - status["nominal_span_seconds"]) <= status["span_tolerance_seconds"]
    assert submissions, "stride tick must submit one window"


def test_window_ids_and_window_stamps_are_monotone_per_submission(monkeypatch, tmp_path):
    pipe = make_pipeline(monkeypatch, tmp_path, window_size=16, stride=4)
    seen = []
    def record(window, observed_at, generation, source_stamp, window_id, start, end, window_integrity):
        seen.append((window_id, start, end, window_integrity))
    monkeypatch.setattr(pipe, "_infer_window_async", record)
    start = 500.0
    for i in range(16 * 3):
        pipe.process_frame(np.zeros((8, 8, 3), np.uint8), captured_at=start + i / 30, nominal_fps=30.0)
        pipe._inference_running = False  # let the next stride tick submit (async sim)
    pipe._inference_executor.shutdown(wait=True)  # drain the async worker
    assert len(seen) >= 2
    ids = [s[0] for s in seen]
    assert ids == sorted(ids) and len(set(ids)) == len(ids), "window ids must be monotone and unique"
    for window_id, w_start, w_end, w_integrity in seen:
        assert w_end > w_start
        assert abs((w_end - w_start) - 15 / 30) <= (15 / 30) * 0.10, "G-07 span for submitted window"
        assert w_integrity["valid"] is True
        assert w_integrity["frames_collected"] == 16 and w_integrity["frames_required"] == 16
        assert abs(w_integrity["span_seconds"] - 15 / 30) <= (15 / 30) * 0.10
