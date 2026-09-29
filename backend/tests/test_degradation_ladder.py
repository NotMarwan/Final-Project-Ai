"""WT-14 multi-camera degradation ladder: config-driven, never silent.

Canonical step order: jpeg quality -> ring fps -> ring max-side -> pause
annotation.  Ring-fps decimation decisions are COUNTED by the capture loop
(evidenceFramesDecimated); transitions are logged.
"""
from pipeline_capture import (
    DegradationConfig,
    DegradationLadder,
    DegradationStep,
    RingConfig,
)


CFG = DegradationConfig(
    enabled=True,
    degrade_after_s=5.0,
    recover_after_s=30.0,
    steps=(
        DegradationStep(jpeg_quality=75),
        DegradationStep(jpeg_quality=50),
        DegradationStep(ring_fps=15),
        DegradationStep(ring_max_side=640),
        DegradationStep(pause_annotation=True),
    ),
)


def test_disabled_ladder_never_degrades():
    ladder = DegradationLadder(DegradationConfig(enabled=False, steps=CFG.steps))
    for now in range(0, 100):
        ladder.observe(healthy=False, now=float(now))
    assert ladder.level == 0


def test_pressure_steps_down_in_canonical_order_and_recovers():
    ladder = DegradationLadder(CFG)
    now = 0.0
    assert ladder.observe(healthy=False, now=now) == 0
    for expected in range(1, 6):
        now += 5.0
        assert ladder.observe(healthy=False, now=now) == expected
    base = RingConfig(format="jpeg90")
    applied = ladder.ring_config(base)
    assert applied.jpeg_quality == 50          # last jpeg step wins
    assert applied.max_side == 640
    assert ladder.ring_fps_cap() == 15
    assert ladder.pause_annotation is True
    for _ in range(6):
        now += 30.0
        ladder.observe(healthy=True, now=now)
    assert ladder.level == 0
    assert ladder.ring_config(base).jpeg_quality == 90


def test_ring_fps_decimation_stride_counts_every_other_frame():
    ladder = DegradationLadder(CFG)
    now = 0.0
    for _ in range(4):
        now += 5.0
        ladder.observe(healthy=False, now=now)
    assert ladder.level == 3
    assert ladder.ring_fps_cap() == 15
    kept = [seq for seq in range(1, 11) if ladder.should_append(seq, nominal_fps=30.0)]
    assert kept == [2, 4, 6, 8, 10]


def test_transitions_are_recorded_with_reason():
    ladder = DegradationLadder(CFG)
    ladder.observe(healthy=False, now=0.0)
    ladder.observe(healthy=False, now=6.0)
    assert ladder.transitions and ladder.transitions[0][1:] == (0, 1, "pressure")
    snap = ladder.snapshot()
    assert snap["degradationLevel"] == 1
    assert snap["degradationEnabled"] is True
    assert snap["degradationSteps"].get("jpeg_quality:75") == 1
