"""R4 ensemble single-vote semantics, R7 onset identity, item-5 motion gate,
and R8 checkpoint identity (WT-19 / S-02).

Contract under test: one completed window evaluation produces exactly ONE
producer observation (violence_observation_id bump) — the temporal ensemble
aggregates scores and never double-counts decision votes (WT-20 confirmed
decision-layer semantics 2026-09-29).
"""
import numpy as np
import pytest
import torch

import inference
from inference import ViolenceInferencePipeline, identify_checkpoint

CLS = inference.VIOLENCE_CLS


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
    monkeypatch.setattr(inference, "preprocess_slowfast_window",
                        lambda frames: torch.zeros(1, len(frames), 3, 4, 4))
    return ViolenceInferencePipeline(str(weights), torch.device("cpu"), **kwargs)


def logits_for(score):
    """Logits whose margin sigmoid equals `score` (temp=1, bias=0)."""
    margin = np.log(score / (1.0 - score))
    row = [-margin / 2.0] * 2
    row[CLS] = margin / 2.0
    return torch.tensor([row], dtype=torch.float32)


def complete(pipe, score, window_id, start):
    _FakeModel.logits = logits_for(score)
    pipe._infer_window_async(
        window_frames=[np.zeros((8, 8, 3), np.uint8) for _ in range(4)],
        observed_at=start + 1.0,
        generation=None,
        source_captured_at=start,
        window_id=window_id,
        window_start_timestamp=start,
        window_end_timestamp=start + 1.0,
    )


def test_one_observation_per_ensemble_completion(monkeypatch, tmp_path):
    pipe = make_pipeline(monkeypatch, tmp_path, ensemble_k=3, ensemble_agg="max", threshold=0.5)
    for i in range(3):
        complete(pipe, 0.6 + 0.1 * i, window_id=i + 1, start=10.0 + i)
    assert pipe._observation_id == 3, "exactly one producer observation per completion (SC-7)"
    scores = [0.6, 0.7, 0.8]
    assert pipe._completed_window_fields["ensemble_score"] == pytest.approx(max(scores), abs=1e-3)
    assert pipe._completed_window_fields["ensemble_k"] == 3
    assert pipe._completed_window_fields["ensemble_spread"] >= 0.0


def test_ensemble_mean_variant(monkeypatch, tmp_path):
    pipe = make_pipeline(monkeypatch, tmp_path, ensemble_k=3, ensemble_agg="mean", threshold=0.5)
    for i in range(3):
        complete(pipe, 0.4 + 0.2 * i, window_id=i + 1, start=10.0 + i)
    assert pipe._completed_window_fields["ensemble_score"] == pytest.approx(0.6, abs=1e-3)


def test_k1_gate_off_matches_legacy_score_formula(monkeypatch, tmp_path):
    pipe = make_pipeline(monkeypatch, tmp_path, threshold=0.5)
    assert pipe._ensemble_k == 1 and pipe._motion_gate_mode == "off"
    complete(pipe, 0.7, window_id=1, start=10.0)
    expected = pipe._calibrate_confidence(logits_for(0.7), 0.7)
    assert pipe._last_calibrated_conf == pytest.approx(expected, abs=1e-6)
    # _counter stays 0 in direct calls -> pre-warmup path: smoothed == calibrated.
    assert pipe._last_conf == pytest.approx(expected, abs=1e-6)
    assert pipe._completed_window_fields["ensemble_spread"] == 0.0


def test_onset_candidate_tracks_positive_run(monkeypatch, tmp_path):
    pipe = make_pipeline(monkeypatch, tmp_path, threshold=0.5)
    complete(pipe, 0.95, window_id=1, start=10.0)
    assert pipe._is_violent
    assert pipe._onset_candidate_timestamp == pytest.approx(10.0)
    assert pipe._onset_candidate_window_id == 1
    complete(pipe, 0.95, window_id=2, start=11.0)
    assert pipe._onset_candidate_window_id == 1, "run start must not move within a run"
    complete(pipe, 0.10, window_id=3, start=12.0)
    assert not pipe._is_violent
    assert pipe._onset_candidate_timestamp is None
    assert pipe._onset_candidate_window_id is None
    complete(pipe, 0.95, window_id=4, start=13.0)
    assert pipe._is_violent
    assert pipe._onset_candidate_window_id == 4
    fields = pipe._completed_window_fields
    assert fields["window_id"] == 4
    assert fields["window_start_timestamp"] == pytest.approx(13.0)
    assert fields["window_end_timestamp"] == pytest.approx(14.0)
    assert fields["onset_candidate_window_id"] == 4
    # History keeps every window for the WT-20 score-sequence schema.
    assert [row["window_id"] for row in pipe._window_score_history] == [1, 2, 3, 4]


def test_reset_clears_onset_and_ensemble_state(monkeypatch, tmp_path):
    pipe = make_pipeline(monkeypatch, tmp_path, ensemble_k=3, threshold=0.5)
    complete(pipe, 0.95, window_id=1, start=10.0)
    pipe.reset()
    assert pipe._onset_candidate_window_id is None
    assert len(pipe._window_scores) == 0
    assert pipe._completed_window_fields == {}


def test_motion_gate_block_and_damp(monkeypatch, tmp_path):
    pipe = make_pipeline(monkeypatch, tmp_path, threshold=0.5)
    static = [np.full((16, 16, 3), 7, np.uint8) for _ in range(4)]
    energy = pipe._window_motion_energy(static)
    assert energy == pytest.approx(0.0, abs=1e-6)
    pipe._motion_gate_mode = "block"
    pipe._motion_gate_floor = 1.0
    assert pipe._apply_motion_gate(0.9, energy) == (0.0, True)
    pipe._motion_gate_mode = "damp"
    assert pipe._apply_motion_gate(0.9, 0.5) == (pytest.approx(0.45), True)
    pipe._motion_gate_mode = "off"
    assert pipe._apply_motion_gate(0.9, energy) == (0.9, False)
    # Moving window passes the gate untouched.
    moving = [np.full((16, 16, 3), i * 40 % 255, np.uint8) for i in range(4)]
    assert pipe._window_motion_energy(moving) > 1.0
    pipe._motion_gate_mode = "block"
    score, gated = pipe._apply_motion_gate(0.9, pipe._window_motion_energy(moving))
    assert (score, gated) == (0.9, False)


def test_motion_gate_marks_completed_fields(monkeypatch, tmp_path):
    pipe = make_pipeline(monkeypatch, tmp_path, threshold=0.5)
    pipe._motion_gate_mode = "block"
    pipe._motion_gate_floor = 1.0
    _FakeModel.logits = logits_for(0.95)
    pipe._infer_window_async(
        window_frames=[np.full((16, 16, 3), 7, np.uint8) for _ in range(4)],
        observed_at=1.0, generation=None, source_captured_at=0.0,
        window_id=1, window_start_timestamp=0.0, window_end_timestamp=1.0,
    )
    fields = pipe._completed_window_fields
    assert fields["motion_gated"] is True
    assert fields["motion_energy"] == pytest.approx(0.0, abs=1e-6)
    assert fields["ensemble_score"] == pytest.approx(0.0, abs=1e-6)
    assert not pipe._is_violent, "gated static window must not start a positive run"


def test_identify_checkpoint_families():
    slowfast = identify_checkpoint({
        "sf.backbone.blocks.0.multipathway_blocks.0.conv.weight": torch.zeros(64, 3, 1, 7, 7),
        "sf.backbone.blocks.0.multipathway_fusion.conv_fast_to_slow.weight": torch.zeros(1),
        "head.1.weight": torch.zeros(512, 2304),
        "head.4.weight": torch.zeros(2, 512),
    })
    assert slowfast["family"] == "slowfast"
    assert slowfast["variant"] == "pytorchvideo_slowfast_r50"
    assert slowfast["num_classes"] == 2 and slowfast["head_dim"] == 2304
    r3d = identify_checkpoint({"sf.backbone.0.weight": torch.zeros(1), "head.4.weight": torch.zeros(2, 512)})
    assert r3d["family"] == "slowfast" and r3d["variant"] == "torchvision_r3d_18_fallback"
    r2p1 = identify_checkpoint({
        "backbone.conv1.weight": torch.zeros(1),
        "spatial_transformer.fc_loc.0.weight": torch.zeros(1),
    })
    assert r2p1["family"] == "r2plus1d-multiangle"
    assert "legacy-spatial-transformer" in r2p1["variant"]
    assert identify_checkpoint({"weird.key": torch.zeros(1)})["family"] == "unknown"
    assert identify_checkpoint({})["family"] == "unknown"


def test_legacy_spatial_transformer_keys_are_dropped():
    state = {"backbone.fc.weight": torch.zeros(2, 4),
             "spatial_transformer.fc_loc.0.weight": torch.zeros(1)}
    cleaned = ViolenceInferencePipeline._drop_legacy_dead_keys(state)
    assert "spatial_transformer.fc_loc.0.weight" not in cleaned
    assert "backbone.fc.weight" in cleaned
    assert "spatial_transformer.fc_loc.0.weight" in state, "input untouched"


def test_bare_multiangle_keys_load_into_wrapper_model():
    class Inner:
        def __init__(self):
            self.loaded = None
        def load_state_dict(self, sd, strict=True):
            self.loaded = list(sd)

    class Wrapper:
        def __init__(self):
            self.model = Inner()
        def load_state_dict(self, sd, strict=True):
            raise RuntimeError("missing keys: model.backbone.fc.weight")

    wrapper = Wrapper()
    ViolenceInferencePipeline._load_compatible(wrapper, {"backbone.fc.weight": torch.zeros(1)})
    assert wrapper.model.loaded == ["backbone.fc.weight"]


def test_architecture_identity_is_truthful(monkeypatch, tmp_path):
    pipe = make_pipeline(monkeypatch, tmp_path)
    identity = pipe.architecture_identity()
    assert identity["architectureId"] == "fake"
    assert identity["checkpointIdentity"]["family"] == "slowfast"
    assert identity["legacyIsX3dFlag"] is False
    assert identity["ensembleK"] == 1
