"""Deterministic best-frame selection for incident capture (S-04 / WT-22).

Scores candidate frames on six defect axes and picks the best frame for
evidence/face capture. The scorer is fully deterministic — the same frames in
any input order produce the same selection (the tie-break is a total order over
content, not over arrival order).

Axes (weights live in ONE TOML block: ``config/best_frame.toml`` ``[best_frame]``):

* ``sharpness``      variance of Laplacian (higher is better)
* ``exposure``       clipping fraction at both ends of the histogram
* ``yaw``            face yaw proxy from landmarks when a face is present
* ``face_size``      face min-side in pixels
* ``ied``            inter-eye distance in pixels
* ``occlusion``      fraction of the subject region occluded / clipped by frame

Honesty rules baked into the output: a yaw value derived from landmarks is
labelled ``yaw_source = "proxy_from_landmarks"`` with ``yaw_is_proxy = true`` —
never reported as a measured head rotation. Absent faces leave the face axes at
a neutral score with ``*_source = "unavailable"`` rather than being invented.
Selection records carry SC-6 timestamps and SC-8 parent references.
"""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "best_frame.toml"

AXIS_NAMES = ("sharpness", "exposure", "yaw", "face_size", "ied", "occlusion")


@dataclass(frozen=True)
class BestFrameConfig:
    weights: dict[str, float]
    sharpness_ref: float = 500.0
    exposure_clip_lo: int = 5
    exposure_clip_hi: int = 250
    clipping_bad: float = 0.25
    yaw_ratio_bad: float = 0.35
    face_min_px: float = 60.0
    face_good_px: float = 140.0
    ied_min_px: float = 24.0
    ied_good_px: float = 60.0
    pre_seconds: float = 10.0
    post_seconds: float = 5.0
    source: str = str(DEFAULT_CONFIG_PATH)

    @classmethod
    def from_dict(cls, payload: dict[str, Any], source: str = "<dict>") -> "BestFrameConfig":
        block = payload.get("best_frame")
        if not isinstance(block, dict):
            raise ValueError("best_frame config requires a [best_frame] table")
        weights = {axis: float(block.get(f"w_{axis}", 0.0)) for axis in AXIS_NAMES}
        if any(value < 0 for value in weights.values()):
            raise ValueError("best_frame weights must be non-negative")
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"best_frame weights must sum to 1.0 (got {total!r})")
        window = block.get("window", {}) if isinstance(block.get("window"), dict) else {}
        scalar = {key: float(block[key]) for key in
                  ("sharpness_ref", "clipping_bad", "yaw_ratio_bad", "face_min_px",
                   "face_good_px", "ied_min_px", "ied_good_px") if key in block}
        ints = {key: int(block[key]) for key in ("exposure_clip_lo", "exposure_clip_hi") if key in block}
        return cls(weights=weights, source=source,
                   pre_seconds=float(window.get("pre_seconds", 10.0)),
                   post_seconds=float(window.get("post_seconds", 5.0)),
                   **scalar, **ints)


def load_config(path: str | Path | None = None) -> BestFrameConfig:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"best_frame config not found: {config_path}")
    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)
    return BestFrameConfig.from_dict(payload, source=str(config_path))


DEFAULT_CONFIG: Optional[BestFrameConfig] = None


def _config(config: Optional[BestFrameConfig]) -> BestFrameConfig:
    global DEFAULT_CONFIG
    if config is not None:
        return config
    if DEFAULT_CONFIG is None:
        DEFAULT_CONFIG = load_config()
    return DEFAULT_CONFIG


def _clamp01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _face_value(face: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = face.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _face_bbox(face: dict[str, Any]) -> Optional[tuple[float, float, float, float]]:
    for key in ("bbox_xyxy_source", "bbox_xyxy", "bbox"):
        value = face.get(key)
        if value is None:
            continue
        if len(value) != 4:
            continue
        try:
            return tuple(float(item) for item in value)  # type: ignore[return-value]
        except (TypeError, ValueError):
            continue
    return None


def _face_landmarks(face: dict[str, Any]) -> Optional[np.ndarray]:
    for key in ("landmarks_5pt", "landmarks", "kps"):
        value = face.get(key)
        if value is None:
            continue
        array = np.asarray(value, dtype=np.float64)
        if array.shape == (5, 2):
            return array
    return None


def _sharpness_score(gray: np.ndarray, config: BestFrameConfig) -> tuple[float, float]:
    raw = float(np.var(np.asarray(_laplacian(gray), dtype=np.float64)))
    return raw, _clamp01(raw / max(1e-6, config.sharpness_ref))


def _laplacian(gray: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.Laplacian(gray, cv2.CV_64F)


def _exposure_score(gray: np.ndarray, config: BestFrameConfig) -> tuple[float, float]:
    clipped = float(np.mean((gray <= config.exposure_clip_lo) | (gray >= config.exposure_clip_hi)))
    return clipped, _clamp01(1.0 - clipped / max(1e-6, config.clipping_bad))


def _occlusion_score(face: dict[str, Any] | None, bbox: Optional[Sequence[float]],
                     frame_shape: Sequence[int], config: BestFrameConfig) -> tuple[float, str]:
    """Returns (score, source). Never invents occlusion knowledge."""
    if face is not None:
        provided = _face_value(face, "occluded_fraction", "occlusion")
        if provided is not None:
            return _clamp01(1.0 - provided), "provided"
    if bbox is not None:
        height, width = float(frame_shape[0]), float(frame_shape[1])
        x1, y1, x2, y2 = (float(value) for value in bbox[:4])
        area = max(1e-6, (x2 - x1) * (y2 - y1))
        inside = max(0.0, min(x2, width) - max(x1, 0.0)) * max(0.0, min(y2, height) - max(y1, 0.0))
        return _clamp01(inside / area), "bbox_frame_clip_fraction"
    return 0.5, "unavailable"


def score_frame(frame: np.ndarray, faces: Optional[Sequence[dict[str, Any]]] = None,
                config: Optional[BestFrameConfig] = None,
                subject_bbox: Optional[Sequence[float]] = None) -> dict[str, Any]:
    """Score one candidate frame. Pure function of the pixels and face records."""
    config = _config(config)
    array = np.asarray(frame)
    if array.ndim == 3:
        gray = array.mean(axis=2).astype(np.uint8) if array.dtype == np.uint8 else array.mean(axis=2)
    else:
        gray = array
    sharpness_raw, sharpness = _sharpness_score(gray, config)
    clipping, exposure = _exposure_score(gray.astype(np.float64), config)

    faces = list(faces or [])
    best_face_index: Optional[int] = None
    best_face_score = -1.0
    per_face: list[dict[str, Any]] = []
    for index, face in enumerate(faces):
        bbox = _face_bbox(face)
        landmarks = _face_landmarks(face)
        size_px = None
        if bbox is not None:
            size_px = min(bbox[2] - bbox[0], bbox[3] - bbox[1])
        provided_size = _face_value(face, "face_size_px", "size_px")
        if provided_size is not None:
            size_px = provided_size
        ied_px = _face_value(face, "ied_px")
        ied_source = "provided" if ied_px is not None else "unavailable"
        if ied_px is None and landmarks is not None:
            ied_px = float(np.linalg.norm(landmarks[0] - landmarks[1]))
            ied_source = "landmarks"
        yaw_ratio = _face_value(face, "yaw_ratio")
        yaw_deg = _face_value(face, "yaw_proxy_deg")
        yaw_source = "provided" if (yaw_ratio is not None or yaw_deg is not None) else "unavailable"
        if yaw_ratio is None and yaw_deg is not None:
            yaw_ratio = abs(math.sin(math.radians(yaw_deg)))
            yaw_source = "provided"
        if yaw_ratio is None and landmarks is not None and ied_px:
            eye_mid_x = (landmarks[0][0] + landmarks[1][0]) / 2.0
            yaw_ratio = abs(landmarks[2][0] - eye_mid_x) / max(1e-6, ied_px)
            yaw_source = "proxy_from_landmarks"

        yaw_score = 0.5 if yaw_ratio is None else _clamp01(1.0 - yaw_ratio / max(1e-6, config.yaw_ratio_bad))
        size_score = 0.5 if size_px is None else _clamp01(
            (size_px - config.face_min_px) / max(1e-6, config.face_good_px - config.face_min_px))
        ied_score = 0.5 if ied_px is None else _clamp01(
            (ied_px - config.ied_min_px) / max(1e-6, config.ied_good_px - config.ied_min_px))
        occlusion_value, occlusion_source = _occlusion_score(face, bbox, array.shape[:2], config)
        face_total = (config.weights["yaw"] * yaw_score + config.weights["face_size"] * size_score
                      + config.weights["ied"] * ied_score + config.weights["occlusion"] * occlusion_value)
        per_face.append({
            "face_index": index,
            "bbox_xyxy": None if bbox is None else [int(round(value)) for value in bbox],
            "track_ref": face.get("track_ref"),
            "face_size_px": None if size_px is None else round(float(size_px), 2),
            "ied_px": None if ied_px is None else round(float(ied_px), 2),
            "ied_source": ied_source,
            "yaw_ratio": None if yaw_ratio is None else round(float(yaw_ratio), 4),
            "yaw_source": yaw_source,
            "yaw_is_proxy": yaw_source == "proxy_from_landmarks",
            "occlusion_source": occlusion_source,
            "occluded_fraction": round(float(1.0 - occlusion_value), 4),
            "yaw_score": round(float(yaw_score), 6),
            "face_size_score": round(float(size_score), 6),
            "ied_score": round(float(ied_score), 6),
            "face_score": round(float(face_total), 4),
        })
        if face_total > best_face_score:
            best_face_score = face_total
            best_face_index = index

    if best_face_index is None:
        occlusion_value, occlusion_source = _occlusion_score(None, subject_bbox, array.shape[:2], config)
        selected = None
    else:
        selected = per_face[best_face_index]
        occlusion_value = 1.0 - float(selected["occluded_fraction"])
        occlusion_source = str(selected["occlusion_source"])

    axes = {
        "sharpness": round(sharpness, 6),
        "exposure": round(exposure, 6),
        "yaw": 0.5 if selected is None else float(selected["yaw_score"]),
        "face_size": 0.5 if selected is None else float(selected["face_size_score"]),
        "ied": 0.5 if selected is None else float(selected["ied_score"]),
        "occlusion": round(_clamp01(occlusion_value), 6),
    }
    total = sum(config.weights[axis] * axes[axis] for axis in AXIS_NAMES)
    return {
        "total": round(float(total), 6),
        "axes": axes,
        "raw": {
            "sharpness_variance_of_laplacian": round(sharpness_raw, 4),
            "exposure_clipped_fraction": round(clipping, 6),
        },
        "selected_face_index": best_face_index,
        "faces": per_face,
        "occlusion_source": occlusion_source,
        "weights": dict(config.weights),
        "weights_source": config.source,
    }


def select_best(candidates: Sequence[dict[str, Any]],
                config: Optional[BestFrameConfig] = None) -> Optional[dict[str, Any]]:
    """Pick the best candidate. Input order never affects the winner.

    Each candidate is ``{"frame": ndarray, "frame_ref": dict, "faces": [...],
    "subject_bbox": [...] }`` (faces/subject_bbox optional). Returns the best
    candidate dict augmented with ``score`` and a full ``ranked`` list, or
    ``None`` for an empty candidate set.
    """
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        frame = candidate.get("frame")
        if frame is None:
            continue
        score = score_frame(frame, candidate.get("faces"), config, candidate.get("subject_bbox"))
        scored.append({**candidate, "score": score})
    if not scored:
        return None
    # Total order over content: score desc, sharpness desc, frame_id asc.
    def sort_key(entry: dict[str, Any]) -> tuple[float, float, str]:
        ref = entry.get("frame_ref") or {}
        return (-float(entry["score"]["total"]),
                -float(entry["score"]["axes"]["sharpness"]),
                str(ref.get("frame_id") or ""))

    scored.sort(key=sort_key)
    best = dict(scored[0])
    best["ranked"] = [
        {
            "frame_id": (entry.get("frame_ref") or {}).get("frame_id"),
            "total": entry["score"]["total"],
            "axes": entry["score"]["axes"],
        }
        for entry in scored
    ]
    best["candidate_count"] = len(scored)
    return best
