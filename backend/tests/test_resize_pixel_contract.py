"""A reused capture buffer and mutable output must never return stale pixels."""
import numpy as np
import pytest

import inference
import optimization


@pytest.mark.parametrize('resize', [inference.cached_resize, optimization.cached_resize])
def test_resize_observes_inplace_input_mutation(resize):
    frame = np.zeros((12, 12, 3), dtype=np.uint8)
    first = resize(frame, 24)
    frame[:] = 37
    second = resize(frame, 24)
    assert np.all(first == 0)
    assert np.all(second == 37)


@pytest.mark.parametrize('resize', [inference.cached_resize, optimization.cached_resize])
def test_resize_output_mutation_does_not_poison_next_call(resize):
    frame = np.full((12, 12, 3), 21, dtype=np.uint8)
    resize(frame, 24)[:] = 99
    assert np.all(resize(frame, 24) == 21)


@pytest.mark.parametrize('resize', [inference.cached_resize, optimization.cached_resize])
def test_ephemeral_frames_and_sizes_remain_correct(resize):
    for value in range(60):
        frame = np.full((12, 12, 3), value, dtype=np.uint8)
        assert np.all(resize(frame, 24) == value)
        assert resize(frame, 16).shape == (16, 16, 3)


# --- Quality preservation + coordinate mapping (WT-15) ----------------------

def test_downscale_for_inference_never_mutates_the_original():
    """The inference view derives; the source frame (evidence/display) is untouched."""
    from temporal_frames import downscale_for_inference

    rng = np.random.default_rng(7)
    raw = rng.integers(0, 256, size=(720, 1280, 3), dtype=np.uint8)
    before = raw.copy()
    small = downscale_for_inference(raw, 640)
    assert small.shape == (360, 640, 3)
    assert np.array_equal(raw, before)
    assert small is not raw


def test_downscale_for_inference_passthrough_edge_is_pinned():
    """No-scaling case returns the SAME buffer (callers must copy — WT-14 boundary contract)."""
    from temporal_frames import downscale_for_inference

    raw = np.zeros((480, 640, 3), dtype=np.uint8)
    same = downscale_for_inference(raw, 640)
    assert same is raw


def test_downscale_resolution_contract_exact_shapes():
    """Evidence ring (960) and inference view (640) derive at exact fixed shapes."""
    from temporal_frames import downscale_for_inference

    raw = np.full((720, 1280, 3), 33, dtype=np.uint8)
    assert downscale_for_inference(raw, 640).shape == (360, 640, 3)
    assert downscale_for_inference(raw, 960).shape == (540, 960, 3)
    assert downscale_for_inference(raw, 256).shape == (144, 256, 3)
    uniform = downscale_for_inference(raw, 640)
    assert np.all(uniform == 33)  # INTER_AREA preserves uniform pixels exactly


def test_scale_person_tracks_maps_model_input_to_source_pixels():
    from inference_process import _scale_person_tracks

    tracks = [
        {"id": 1, "bbox": [160.0, 90.0, 320.0, 180.0], "confidence": 0.9},
        {"id": 2, "bbox": [-5.0, -5.0, 5.0, 5.0], "confidence": 0.5},   # clipped
        {"id": 3, "bbox": [10.0, 10.0, 5.0, 5.0], "confidence": 0.5},   # inverted -> dropped
        {"id": 4, "bbox": [float("nan")] * 4, "confidence": 0.5},        # invalid -> dropped
    ]
    scaled = _scale_person_tracks(tracks, (640, 360), (1280, 720))
    by_id = {track["id"]: track for track in scaled}
    assert set(by_id) == {1, 2}
    assert by_id[1]["bbox"] == [320.0, 180.0, 640.0, 360.0]
    assert by_id[2]["bbox"] == [0.0, 0.0, 10.0, 10.0]
    assert by_id[1]["confidence"] == 0.9  # non-geometry fields preserved


def test_track_bbox_display_mapping_stays_proportional():
    """Model-input -> original -> display (MJPEG width 854) is pure scaling."""
    from inference_process import _scale_person_tracks

    source_width, source_height, display_width = 1280, 720, 854
    scaled = _scale_person_tracks(
        [{"id": 1, "bbox": [160.0, 90.0, 320.0, 180.0], "confidence": 1.0}],
        (640, 360),
        (source_width, source_height),
    )
    assert scaled[0]["bbox"] == [320.0, 180.0, 640.0, 360.0]  # model-input -> original
    x1, y1, x2, y2 = scaled[0]["bbox"]
    display = [coord * display_width / source_width for coord in (x1, y1, x2, y2)]
    assert display == [213.5, 120.09375, 427.0, 240.1875]  # original -> display (aspect preserved)


def test_scale_person_tracks_rejects_invalid_dimensions():
    from inference_process import _scale_person_tracks
    import pytest

    with pytest.raises(ValueError):
        _scale_person_tracks([{"id": 1, "bbox": [1, 2, 3, 4]}], (0, 360), (1280, 720))
