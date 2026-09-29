"""EXP-20 sweep tool contract: dev-only selection, and the negatives-only G-02 screen.

Fixtures are SYNTHETIC MECHANICS only (never evidence, never test truth).
"""
from __future__ import annotations

import pytest

from bench.calibrate import select_policy
from backend.decision_config import load_decision_config

MODEL = "2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01"


def sequence(clip_id, digest_char, split, label, scores):
    return {"clip_id": clip_id, "source_sha256": digest_char * 64, "split": split, "label": label,
            "label_source": "publisher", "scores": scores,
            "valid": [True] * len(scores), "start_s": [float(i) for i in range(len(scores))]}


def payload(rows):
    return {"model_sha256": MODEL, "aggregation": "per-window sequences", "sequences": rows}


def test_selection_requires_both_classes_in_dev():
    with pytest.raises(ValueError):
        select_policy(payload([sequence("n", "a", "dev", 0, [0.5, 0.5])]))


def test_selection_picks_a_policy_meeting_the_frozen_criteria():
    rows = [sequence("pos", "a", "dev", 1, [0.5, 0.72, 0.8]),
            sequence("neg-hard", "b", "dev", 0, [0.66, 0.68, 0.66, 0.67]),
            sequence("pos-test", "c", "test", 1, [0.6, 0.82]),
            sequence("neg-test", "d", "test", 0, [0.3, 0.2])]
    report = select_policy(payload(rows))
    assert report["mode"] == "selection"
    assert report["meets_criteria"] is True
    assert report["selected"]["false_positives"] == 0
    assert report["selected"]["tp_rate"] == 1.0
    # The shipped defaults must be the row that fails G-02 on this hard negative.
    defaults = [row for row in report["dev"]
                if row["policy"]["cascade_gate_threshold"] == 0.0
                and row["policy"]["confirm_weight_gain"] == 0.0
                and row["policy"]["confirm_weight_sum"] == 2.0
                and row["policy"]["confirm_n"] == 2 and row["policy"]["confirm_m"] == 3]
    assert defaults and all(row["false_positives"] == 1 for row in defaults)
    assert report["test"]["negatives"] == 1


def test_negatives_only_screen_ranks_candidates_and_defers_selection():
    rows = [sequence("neg1", "a", "dev", 0, [0.66, 0.68, 0.66, 0.67]),
            sequence("neg2", "b", "dev", 0, [0.2, 0.1, 0.3])]
    report = select_policy(payload(rows), negatives_only=True)
    assert report["mode"] == "false-positive-screen"
    assert report["selected"] is None
    assert report["meets_criteria"] is None
    assert report["criteria"]["deferred"]
    headline = report["lowest_false_positive_policy"]
    assert headline["false_positives"] == 0
    assert headline["policy"]["cascade_gate_threshold"] > 0
    assert len(report["dev"]) > 1


def test_train_and_calibration_rows_are_validated_but_excluded_from_selection():
    rows = [sequence("pos", "a", "dev", 1, [0.6, 0.8]),
            sequence("neg", "b", "dev", 0, [0.66, 0.66, 0.66]),
            sequence("train-hard-neg", "c", "train", 0, [0.9, 0.9, 0.9]),
            sequence("calib-neg", "d", "calibration", 0, [0.9, 0.9, 0.9])]
    report = select_policy(payload(rows))
    assert report["excluded_rows"] == {"train": 1, "calibration": 1}
    assert all(row["policy"]["confirm_m"] >= 1 for row in report["dev"])


def test_infeasible_weight_sums_are_excluded_from_screening_and_selection():
    rows = [sequence("neg", "a", "dev", 0, [0.7, 0.7, 0.7]),
            sequence("neg2", "b", "dev", 0, [0.2, 0.1])]
    base = load_decision_config().to_dict()
    grid = [{**base, "confirm_n": 2, "confirm_m": 3, "confirm_weight_sum": 3.5,
             "confirm_weight_gain": 0.0, "cascade_gate_threshold": 0.0},
            {**base, "confirm_n": 2, "confirm_m": 3, "confirm_weight_sum": 2.0,
             "confirm_weight_gain": 0.0, "cascade_gate_threshold": 0.8}]
    payload_rows = [dict(row) for row in rows]
    payload_rows[0]["label"] = 1  # make the tuning split whole for selection mode
    report = select_policy(payload(payload_rows), grid=grid)
    dead = [row for row in report["dev"] if row["policy"]["confirm_weight_sum"] == 3.5][0]
    assert dead["feasible"] is False and dead["max_achievable_weight_sum"] == 3.0
    assert report["infeasible_policies"] == 1
    assert report["selected"]["policy"]["confirm_weight_sum"] == 2.0
    with pytest.raises(ValueError):
        select_policy(payload([sequence("pos", "a", "dev", 1, [0.6, 0.8]),
                               sequence("neg", "b", "dev", 0, [0.66, 0.66]),
                               sequence("weird", "c", "holdout", 0, [0.9, 0.9])]))
