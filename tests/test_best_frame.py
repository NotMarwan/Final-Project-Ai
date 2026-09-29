"""S-04 / WT-22 scoped tests: deterministic best-frame selection and the
frame/crop reference schema consumed by WT-21 (faces) and WT-23 (enhancement)."""
from __future__ import annotations

import numpy as np
import pytest

import best_frame as bf
from frame_reference import (CropRef, FrameRef, FrameReferenceError,
                             crop_ref_from_dict, frame_ref_from_dict, hash_array_raw,
                             make_crop_id, make_frame_id, make_track_ref, parse_track_ref)


def flat(value: int = 40) -> np.ndarray:
    return np.full((48, 64, 3), value, dtype=np.uint8)


def sharp(amplitude: int = 120) -> np.ndarray:
    array = flat(128)
    checker = np.indices((32, 48)).sum(axis=0) % 2
    array[8:40, 8:56] = np.clip(128 + (checker * amplitude - amplitude // 2)[..., None], 0, 255).astype(np.uint8)
    return array


def ref(frame_id: str) -> dict:
    return {"frame_id": frame_id, "camera_id": "CAM-1", "frame_sequence": int(frame_id.split(":")[-1])}


def test_scorer_axes_are_ordered_as_expected():
    config = bf.load_config()
    sharp_score = bf.score_frame(sharp(), config=config)["axes"]["sharpness"]
    flat_score = bf.score_frame(flat(), config=config)["axes"]["sharpness"]
    assert sharp_score > 0.9 > flat_score
    blown = bf.score_frame(np.full((48, 64, 3), 255, dtype=np.uint8), config=config)
    assert blown["axes"]["exposure"] < 0.1
    assert blown["raw"]["exposure_clipped_fraction"] == pytest.approx(1.0)


def test_selection_is_deterministic_and_input_order_independent():
    config = bf.load_config()
    candidates = [
        {"frame": flat(), "frame_ref": ref("CAM-1:1")},
        {"frame": sharp(), "frame_ref": ref("CAM-1:2")},
        {"frame": flat(60), "frame_ref": ref("CAM-1:3")},
    ]
    forward = bf.select_best(candidates, config)
    reverse = bf.select_best(list(reversed(candidates)), config)
    assert forward["frame_ref"]["frame_id"] == reverse["frame_ref"]["frame_id"] == "CAM-1:2"
    assert forward["ranked"] == reverse["ranked"]
    assert forward["candidate_count"] == 3
    assert bf.select_best([], config) is None
    assert bf.select_best([{"frame_ref": ref("CAM-1:9")}], config) is None  # no pixels, no candidate


def test_ties_break_on_content_not_arrival_order():
    config = bf.load_config()
    candidates = [{"frame": flat(70), "frame_ref": ref("CAM-1:20")},
                  {"frame": flat(70), "frame_ref": ref("CAM-1:10")}]
    assert bf.select_best(candidates, config)["frame_ref"]["frame_id"] == "CAM-1:10"


def test_face_axes_use_provided_measurements_and_label_proxies():
    config = bf.load_config()
    landmarks = [[20.0, 20.0], [60.0, 20.0], [44.0, 34.0], [26.0, 44.0], [58.0, 44.0]]
    face = {"bbox_xyxy_source": [10, 10, 90, 90], "landmarks_5pt": landmarks, "occlusion": 0.0}
    score = bf.score_frame(sharp(), [face], config)
    assert score["selected_face_index"] == 0
    selected = score["faces"][0]
    assert selected["ied_px"] == pytest.approx(40.0)
    assert selected["ied_source"] == "landmarks"
    assert selected["yaw_source"] == "proxy_from_landmarks"
    assert selected["yaw_is_proxy"] is True
    assert selected["face_size_px"] == pytest.approx(80.0)

    provided = {"bbox_xyxy": [10, 10, 90, 90], "ied_px": 55.0, "yaw_proxy_deg": 10.0, "occluded_fraction": 0.25}
    score = bf.score_frame(sharp(), [provided], config)
    assert score["faces"][0]["ied_source"] == "provided"
    assert score["faces"][0]["yaw_source"] == "provided"
    assert score["faces"][0]["occluded_fraction"] == pytest.approx(0.25)
    assert score["faces"][0]["occlusion_source"] == "provided"


def test_faces_narrow_the_choice_between_two_similar_frames():
    config = bf.load_config()
    big = {"bbox_xyxy": [8, 8, 56, 40], "ied_px": 60.0, "yaw_proxy_deg": 0.0, "occluded_fraction": 0.0}
    small = {"bbox_xyxy": [12, 12, 32, 28], "ied_px": 20.0, "yaw_proxy_deg": 40.0, "occluded_fraction": 0.6}
    big_score = bf.score_frame(sharp(), [big], config)["total"]
    small_score = bf.score_frame(sharp(), [small], config)["total"]
    assert big_score > small_score


def test_no_face_means_neutral_axes_and_an_honest_source():
    config = bf.load_config()
    score = bf.score_frame(sharp(), [], config)
    assert score["selected_face_index"] is None
    assert score["faces"] == []
    assert score["axes"]["yaw"] == 0.5 and score["axes"]["ied"] == 0.5
    assert score["occlusion_source"] in {"unavailable", "bbox_frame_clip_fraction"}


def test_weights_must_sum_to_one_and_be_non_negative():
    with pytest.raises(ValueError, match="sum to 1.0"):
        bf.BestFrameConfig.from_dict({"best_frame": {"w_sharpness": 0.9, "w_exposure": 0.9}})
    with pytest.raises(ValueError, match="non-negative"):
        bf.BestFrameConfig.from_dict({"best_frame": {"w_sharpness": 1.5, "w_exposure": -0.5}})


def test_shipped_config_is_valid_and_has_a_single_weight_block():
    import tomllib
    from pathlib import Path

    payload = tomllib.loads((Path(__file__).resolve().parent.parent / "config" / "best_frame.toml")
                            .read_text(encoding="utf-8"))
    weight_keys = [key for key in payload["best_frame"] if key.startswith("w_")]
    assert len(weight_keys) == 6
    config = bf.BestFrameConfig.from_dict(payload)
    assert abs(sum(config.weights.values()) - 1.0) < 1e-9
    assert config.pre_seconds == 10.0 and config.post_seconds == 5.0


def test_frame_ref_round_trip_and_validation():
    digest, fmt = hash_array_raw(flat())
    frame = FrameRef(camera_id="CAM-1", frame_sequence=3, captured_at=100.5, iso_time="2026-01-01T00:00:00Z",
                     width=64, height=48, frame_sha256=digest, hash_format=fmt, source_width=1280, source_height=720)
    payload = frame.to_dict()
    assert payload["frame_id"] == "CAM-1:3"
    assert frame_ref_from_dict(payload) == frame
    minimal = frame.to_dict_minimal()
    assert "width" not in minimal and minimal["frame_sha256"] == digest

    with pytest.raises(FrameReferenceError, match="64-char hex"):
        frame_ref_from_dict({**payload, "frame_sha256": "short"})
    with pytest.raises(FrameReferenceError, match="unexpected frame schema"):
        frame_ref_from_dict({**payload, "schema": "sentinel.frame_ref/v2"})
    with pytest.raises(FrameReferenceError, match="camera_id namespace"):
        FrameRef(camera_id="", frame_sequence=1, captured_at=1.0, iso_time="t", width=1, height=1,
                 frame_sha256=digest, hash_format=fmt).frame_id


def test_crop_ref_round_trip_enforces_namespacing_and_derivative_lineage():
    digest, fmt = hash_array_raw(flat())
    crop = CropRef(camera_id="CAM-1", frame_sequence=7, captured_at=101.0, iso_time="2026-01-01T00:00:00Z",
                   subject_kind="face", bbox_xyxy=(10, 10, 40, 40), bbox_space="model_input",
                   source_frame_sha256=digest, hash_format=fmt, track_ref=make_track_ref("CAM-1", 4),
                   face_index=0, alert_id="alert-1")
    payload = crop.to_dict()
    assert payload["crop_id"] == "CAM-1:7:face:0"
    assert crop_ref_from_dict(payload) == crop

    derived = CropRef(camera_id="CAM-1", frame_sequence=7, captured_at=101.0, iso_time="t", subject_kind="face",
                      bbox_xyxy=(10, 10, 40, 40), bbox_space="model_input", source_frame_sha256=digest,
                      hash_format=fmt, is_derivative=True, derivative_of="CAM-1:7:face:0")
    restored = crop_ref_from_dict(derived.to_dict())
    assert restored.is_derivative is True
    assert restored.derivative_of == "CAM-1:7:face:0"
    assert restored == derived

    with pytest.raises(FrameReferenceError, match="malformed track_ref"):
        crop_ref_from_dict({**payload, "track_ref": "CAM-1-4"})
    with pytest.raises(FrameReferenceError, match="unknown bbox_space"):
        crop_ref_from_dict({**payload, "bbox_space": "screen"})
    with pytest.raises(FrameReferenceError, match="non-empty xyxy"):
        crop_ref_from_dict({**payload, "bbox_xyxy": [10, 10, 10, 40]})


def test_identity_ids_are_camera_scoped_and_monotone_by_sequence():
    assert make_frame_id("CAM-2", 11) == "CAM-2:11"
    assert make_crop_id("CAM-2", 11, "person") == "CAM-2:11:person"
    assert make_crop_id("CAM-2", 11, "face", 2) == "CAM-2:11:face:2"
    assert make_track_ref("CAM-2", 5) == "CAM-2::5"
    assert parse_track_ref("CAM-2::5") == ("CAM-2", 5)
    with pytest.raises(FrameReferenceError):
        parse_track_ref("CAM-2:5")
    with pytest.raises(FrameReferenceError):
        make_crop_id("CAM-2", 11, "identity")


def test_hash_formats_distinguish_layouts_and_are_stable():
    digest, fmt = hash_array_raw(flat())
    assert fmt == "raw-uint8-48x64x3"
    assert (digest, fmt) == hash_array_raw(flat())
    other, other_fmt = hash_array_raw(np.zeros((48, 64), dtype=np.uint8))
    assert other_fmt == "raw-uint8-48x64" and other != digest
