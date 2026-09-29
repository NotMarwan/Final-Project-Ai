"""Deterministic tensor/coordinate contracts; these are not accuracy evaluations."""
from types import SimpleNamespace

import numpy as np
import pytest

from yolo_onnx import (LetterboxTransform, decode_detections, model_names,
                       model_output_format, prepare_input, session_options)
from person_detector import PersonDetector
from weapon import _ONNXBackend


def raw_output(nc, proposals, count=8400):
    tensor = np.zeros((1, 4 + nc, count), dtype=np.float32)
    for i, (box, class_id, score) in enumerate(proposals):
        tensor[0, :4, i] = box
        tensor[0, 4 + class_id, i] = score
    return tensor


def test_person_raw_84_by_8400_and_letterbox_inverse_scale():
    frame = np.zeros((360, 480, 3), dtype=np.uint8)
    tensor, transform = prepare_input(frame, (640, 640))
    assert tensor.shape == (1, 3, 640, 640)
    assert transform.top == 80
    rows = decode_detections(raw_output(80, [([320, 320, 320, 240], 0, .9)]),
                             num_classes=80, transform=transform, confidence=.45, classes={0})
    assert rows.shape == (1, 6)
    np.testing.assert_allclose(rows[0, :4], [120, 90, 360, 270], atol=1e-5)
    assert rows[0, 4] == pytest.approx(.9)


def test_preprocessing_rgb_float_and_padding():
    frame = np.zeros((2, 4, 3), dtype=np.uint8)
    frame[:] = [0, 128, 255]
    tensor, transform = prepare_input(frame, (8, 8))
    assert tensor.dtype == np.float32 and tensor.flags.c_contiguous
    np.testing.assert_allclose(tensor[0, :, 0, 0], 114 / 255)
    np.testing.assert_allclose(tensor[0, :, 3, 0], [1, 128 / 255, 0])
    assert transform.top == 2


def test_class_aware_nms_keeps_different_class_and_highest_score():
    output = raw_output(6, [([320, 320, 100, 100], 0, .7),
                            ([321, 321, 100, 100], 0, .9),
                            ([320, 320, 100, 100], 3, .8)])
    rows = decode_detections(output, num_classes=6,
                             transform=LetterboxTransform(640, 640, 1, 0, 0), confidence=.2)
    assert len(rows) == 2
    np.testing.assert_allclose(rows[:, 4], [.9, .8])
    assert list(rows[:, 5]) == [0, 3]


def test_raw_rows_transposed_supported():
    output = raw_output(80, [([320, 320, 100, 100], 0, .9)])
    kwargs = dict(num_classes=80, transform=LetterboxTransform(640, 640, 1, 0, 0), confidence=.2)
    np.testing.assert_array_equal(decode_detections(output, **kwargs),
                                  decode_detections(output.transpose(0, 2, 1), **kwargs))


def test_two_class_raw_is_not_misread_as_post_nms():
    output = raw_output(2, [([100, 100, 40, 20], 1, .8)], count=9)
    rows = decode_detections(output, num_classes=2,
                             transform=LetterboxTransform(640, 640, 1, 0, 0), confidence=.2)
    np.testing.assert_allclose(rows[0], [80, 90, 120, 110, .8, 1])


def test_explicit_post_nms_and_invalid_rows_filtered():
    output = np.array([[[0, 0, 800, 800, .9, 0], [0, 0, 10, 10, .8, .5],
                        [0, 0, 10, 10, 1.5, 0], [0, 0, np.nan, 1, .9, 0],
                        [10, 10, 0, 0, .9, 0], [0, 0, 10, 10, .9, 2]]])
    rows = decode_detections(output, num_classes=2,
                             transform=LetterboxTransform(640, 640, 1, 0, 0),
                             confidence=.2, output_format='post_nms')
    assert rows.shape == (1, 6)
    np.testing.assert_allclose(rows[0], [0, 0, 640, 640, .9, 0])


def test_raw_invalid_confidence_nonfinite_degenerate_and_other_class_filtered():
    output = raw_output(80, [([100, 100, -1, 2], 0, .9), ([100, 100, 20, 20], 0, 2),
                             ([100, 100, 20, 20], 1, .9), ([100, 100, 20, 20], 0, .1)])
    output[0, 0, 10] = np.inf
    rows = decode_detections(output, num_classes=80,
                             transform=LetterboxTransform(640, 640, 1, 0, 0),
                             confidence=.2, classes={0})
    assert rows.shape == (0, 6)


def test_nms_precedes_border_clipping():
    rows = decode_detections(np.array([[[-1000, -1000, 20, 20, .9, 0],
                                        [0, 0, 20, 20, .8, 0]]]),
                             num_classes=1, transform=LetterboxTransform(640, 640, 1, 0, 0),
                             confidence=.2, output_format='post_nms')
    assert len(rows) == 2  # Clipping first makes these identical and wrongly suppresses one.
    np.testing.assert_allclose(rows[:, :4], [[0, 0, 20, 20], [0, 0, 20, 20]])


@pytest.mark.parametrize('shape', [(2, 84, 8400), (1, 85, 8400), (84,), (1, 1, 84, 8400)])
def test_unsupported_tensor_layout_rejected(shape):
    with pytest.raises(ValueError):
        decode_detections(np.zeros(shape), num_classes=80,
                          transform=LetterboxTransform(640, 640, 1, 0, 0), confidence=.2)


def test_metadata_is_parsed_without_execution_and_requires_class_order():
    assert model_names({'names': "{0: 'pistol', 1: 'knife'}"}) == {0: 'pistol', 1: 'knife'}
    assert model_names({'names': '["pistol", "knife"]'}) == {0: 'pistol', 1: 'knife'}
    for raw in ('__import__("os").getcwd()', '{1: "knife"}', '{}'):
        with pytest.raises((ValueError, SyntaxError)):
            model_names({'names': raw})
    assert model_output_format({'args': "{'nms': False}"}) == 'raw'
    assert model_output_format({'args': "{'nms': True}"}) == 'post_nms'


def test_ort_thread_override_is_bounded_and_keeps_spinning_disabled(monkeypatch):
    class SessionOptions:
        def __init__(self):
            self.entries = {}

        def add_session_config_entry(self, key, value):
            self.entries[key] = value

    ort = SimpleNamespace(SessionOptions=SessionOptions)
    monkeypatch.setenv('AI_SENTINEL_ORT_INTRA_OP_THREADS', '1')
    options = session_options(ort)
    assert options.intra_op_num_threads == 1
    assert options.inter_op_num_threads == 1
    assert options.entries['session.intra_op.allow_spinning'] == '0'
    with pytest.raises(ValueError, match='between 1 and 4'):
        session_options(ort, intra_op_threads=0)


class FakeSession:
    def __init__(self, output):
        self.output = output
    def run(self, _names, inputs):
        assert next(iter(inputs.values())).shape == (1, 3, 640, 640)
        return [self.output]


def test_person_adapter_tracks_valid_raw_detection_across_observations():
    detector = PersonDetector(min_track_frames=2, infer_every_n=1)
    detector._use_onnx = True
    detector._onnx_session = FakeSession(raw_output(80, [([320, 320, 320, 240], 0, .9)]))
    detector._onnx_input = 'images'
    frame = np.zeros((360, 480, 3), dtype=np.uint8)
    assert detector.detect(frame, timestamp=1.0) == []
    tracks = detector.detect(frame, timestamp=2.0)
    assert len(tracks) == 1
    assert tracks[0]['track_id'] == 1
    np.testing.assert_allclose(tracks[0]['bbox'], [120, 90, 360, 270])
    detector._onnx_session.output[:] = 0
    assert detector.detect(frame, timestamp=3.0) == []


def test_track_id_is_used_once_per_observation():
    detector = PersonDetector(min_track_frames=1)
    detector._update_tracks(np.array([[0, 0, 100, 100, .9]]), timestamp=1.0)
    first_id = detector._get_active_tracks()[0]['track_id']
    detector._update_tracks(np.array([[0, 0, 100, 100, .9], [5, 0, 105, 100, .8]]), timestamp=2.0)
    ids = [track['track_id'] for track in detector._get_active_tracks()]
    assert len(ids) == len(set(ids)) == 2
    assert first_id in ids


def test_weapon_adapter_uses_export_class3_knife_not_config_index2():
    backend = _ONNXBackend.__new__(_ONNXBackend)
    backend.min_confidence = .2
    backend.labels = ('pistol', 'rifle', 'knife')
    backend._categories = {0:'pistol', 1:'rifle', 2:'shotgun', 3:'knife', 4:'sword', 5:'revolver'}
    backend._selected_classes = {0, 1, 3}
    backend.input_name = 'images'
    backend.input_size = (640, 640)
    backend.output_format = 'raw'
    backend.session = FakeSession(raw_output(6, [([320, 320, 320, 240], 3, .8),
                                                 ([100, 100, 30, 30], 2, .95)]))
    hits = backend.predict(np.zeros((360, 480, 3), dtype=np.uint8))
    assert len(hits) == 1
    assert hits[0][1] == 'knife'
    np.testing.assert_allclose(hits[0][2], [.25, .25, .75, .75])


def test_person_ultralytics_tracking_fallback_contract():
    detector = PersonDetector(min_track_frames=1)
    calls = []
    detector._model = SimpleNamespace(predict=lambda **kwargs: (calls.append(kwargs) or [SimpleNamespace(boxes=None)]))
    detections = detector._detect_yolo(np.zeros((20, 20, 3), dtype=np.uint8))
    assert detections.shape == (0, 5)
    assert calls[0]['classes'] == [0]
    # Both ONNX and Ultralytics feed the same geometry tracker; no second tracker.
    assert 'persist' not in calls[0]


# ──────────────────────────────────────────────────────────────────────────────
# WT-18 additions: person-crop (SAHI-style) region pass on the weapon ONNX
# backend. Coordinates MUST map back to source pixels (SC-2: source-pixel
# coordinates are authoritative); these are deterministic tensor/coordinate
# contracts, not accuracy evaluations.
# ──────────────────────────────────────────────────────────────────────────────


class CountingSession(FakeSession):
    def __init__(self, output):
        super().__init__(output)
        self.calls = 0

    def run(self, names, inputs):
        self.calls += 1
        return super().run(names, inputs)


def weapon_backend(output):
    backend = _ONNXBackend.__new__(_ONNXBackend)
    backend.min_confidence = .2
    backend.labels = ('pistol', 'rifle', 'knife')
    backend._categories = {0: 'pistol', 1: 'rifle', 2: 'shotgun', 3: 'knife',
                           4: 'sword', 5: 'revolver'}
    backend._selected_classes = {0, 1, 3, 4, 5}
    backend.input_name = 'images'
    backend.input_size = (640, 640)
    backend.output_format = 'raw'
    backend.session = output
    return backend


def test_region_pass_maps_crop_hits_back_to_source_pixels():
    backend = weapon_backend(CountingSession(raw_output(6, [([320, 320, 320, 320], 0, .8)])))
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    hits = backend.predict_regions(frame, [[0, 0, 320, 320]], padding=0.0)
    assert len(hits) == 1
    score, label, bbox = hits[0]
    assert label == 'pistol' and score == pytest.approx(.8)
    np.testing.assert_allclose(bbox, [.125, .125, .375, .375], atol=1e-5)


def test_region_pass_applies_crop_offset_and_letterbox_inverse():
    backend = weapon_backend(CountingSession(raw_output(6, [([320, 320, 320, 320], 3, .7)])))
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    hits = backend.predict_regions(frame, [[160, 160, 480, 480]], padding=0.0)
    assert hits[0][1] == 'knife'
    np.testing.assert_allclose(hits[0][2], [.375, .375, .625, .625], atol=1e-5)


def test_region_pass_inverse_handles_non_square_crop_padding():
    backend = weapon_backend(CountingSession(raw_output(6, [([320, 320, 320, 320], 0, .6)])))
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    # 160x320 crop -> vertical letterbox (left pad 160 at scale 2).
    hits = backend.predict_regions(frame, [[0, 0, 160, 320]], padding=0.0)
    np.testing.assert_allclose(hits[0][2], [0.0, .125, .25, .375], atol=1e-5)
    # An asymmetric box before a non-zero origin: padding stays clamped in frame.
    padded = weapon_backend(CountingSession(raw_output(6, [([320, 320, 320, 320], 0, .6)])))
    hits = padded.predict_regions(frame, [[100, 200, 260, 520]], padding=0.12)
    assert len(hits) == 1
    assert 0 <= hits[0][2][0] < hits[0][2][2] <= 640
    assert 0 <= hits[0][2][1] < hits[0][2][3] <= 640


def test_region_pass_is_bounded_and_validates_padding():
    session = CountingSession(raw_output(6, [([320, 320, 320, 320], 0, .8)]))
    backend = weapon_backend(session)
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    boxes = [[0, 0, 320, 320], [160, 160, 480, 480], [320, 320, 640, 640]]
    hits = backend.predict_regions(frame, boxes, padding=0.0, max_regions=2)
    assert session.calls == 2 and len(hits) == 2
    with pytest.raises(ValueError, match='padding'):
        backend.predict_regions(frame, boxes, padding=1.0)
