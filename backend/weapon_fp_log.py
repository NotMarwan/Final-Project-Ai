"""Structured false-positive logging for the weapon path (WT-07 rec #1).

Every weapon-path detection recorded on a known-benign source becomes one
JSONL row plus a crop image, so hard-negative mining can consume the log as
a training set and gate reviews can count FPs with explicit denominators.

Schema (`weapon-fp-log/1`) — one row per detection, self-describing and
joinable with the WT-12 fixture manifest (`wt12-fixture-manifest/1`):
  schema_version, event, log_id, run_id, fixture_id, source_sha256, split,
  clip_id, frame_index, time_s, source (camera id / file path label),
  source_mode ("file-media"|"live"), class (raw subtype), canonical_label,
  group, score, bbox_norm [x1,y1,x2,y2], bbox_px [x1,y1,x2,y2],
  crop_ref (path relative to the log root), resolution [w, h],
  context {backend, provider, input_size, nms_iou_threshold, max_detections,
  min_confidence, thresholds {...}, model_sha256, taxonomy {...}}
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

SCHEMA_VERSION = "weapon-fp-log/1"
FP_LOG_NAME = "fp_detections.jsonl"

_REQUIRED_KEYS = {
    "schema_version", "event", "log_id", "run_id", "fixture_id", "source_sha256",
    "split", "clip_id", "frame_index", "time_s",
    "source", "source_mode", "class", "canonical_label", "group", "score",
    "bbox_norm", "bbox_px", "crop_ref", "resolution", "context",
}
_SOURCE_MODES = {"file-media", "live"}
# Manifest splits (wt12-fixture-manifest/1); "unregistered" marks auxiliary
# media that is NOT part of the fixture set and must never mix into metrics.
_SPLITS = {"train", "val", "calibration", "test", "regression-only", "unregistered"}


class FPLogError(ValueError):
    """FP log record violates the schema."""


def padded_crop_rect(bbox_px: tuple[float, float, float, float],
                     frame_shape: tuple[int, ...], padding: float) -> tuple[int, int, int, int]:
    """Evidence crop rect with a relative padding margin, clamped to the frame.

    Boxes mapped out of a 640 detection view are quantization-noisy in a
    higher-resolution evidence ring (WT-07 §6); padding keeps operator
    context. `padding` is a fraction of box size (e.g. 0.10-0.15) and MUST be
    supplied by configuration — it is not defaulted here (G-05).
    """
    if not 0 <= padding < 1:
        raise FPLogError("crop padding must be a fraction in [0,1)")
    height, width = frame_shape[:2]
    x1, y1, x2, y2 = (float(value) for value in bbox_px)
    if not (x2 > x1 and y2 > y1):
        raise FPLogError("crop bbox must have positive area")
    pad_x = (x2 - x1) * padding
    pad_y = (y2 - y1) * padding
    left = max(0, int(np.floor(x1 - pad_x)))
    top = max(0, int(np.floor(y1 - pad_y)))
    right = min(width, int(np.ceil(x2 + pad_x)))
    bottom = min(height, int(np.ceil(y2 + pad_y)))
    return left, top, right, bottom


def validate_fp_record(record: Mapping[str, Any]) -> None:
    """Raise FPLogError on any schema violation; used by tests and tooling."""
    if not isinstance(record, Mapping):
        raise FPLogError("FP record must be a mapping")
    missing = _REQUIRED_KEYS - set(record)
    if missing:
        raise FPLogError(f"FP record missing keys: {sorted(missing)}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise FPLogError("unknown FP record schema version")
    if record["event"] != "weapon_fp":
        raise FPLogError("FP record event must be 'weapon_fp'")
    if record["source_mode"] not in _SOURCE_MODES:
        raise FPLogError("source_mode must be 'file-media' or 'live'")
    if record["split"] not in _SPLITS:
        raise FPLogError("split must be a manifest split or 'unregistered'")
    if not str(record["run_id"]) or not str(record["fixture_id"]):
        raise FPLogError("run_id and fixture_id must be nonempty")
    source_sha256 = str(record["source_sha256"])
    if len(source_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in source_sha256):
        raise FPLogError("source_sha256 must be a lowercase sha256 hex digest")
    if not str(record["clip_id"]) or not str(record["source"]):
        raise FPLogError("clip_id and source must be nonempty")
    if isinstance(record["frame_index"], bool) or not isinstance(record["frame_index"], int) \
            or record["frame_index"] < 0:
        raise FPLogError("frame_index must be a nonnegative integer")
    score = record["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        raise FPLogError("score must be a probability in [0,1]")
    for key in ("bbox_norm", "bbox_px", "resolution"):
        value = record[key]
        if not isinstance(value, (list, tuple)) or len(value) != (2 if key == "resolution" else 4):
            raise FPLogError(f"{key} has the wrong shape")
    if record["resolution"][0] <= 0 or record["resolution"][1] <= 0:
        raise FPLogError("resolution must be positive")
    if not isinstance(record["context"], Mapping):
        raise FPLogError("context must be a mapping")
    json.dumps(record, allow_nan=False)  # All rows must serialize cleanly.


@dataclass
class WeaponFPLogger:
    """Appends validated FP rows and writes crop references.

    One logger per clip/source run. `context` carries the run's thresholds,
    NMS parameters, model hash and taxonomy so the log is reproducible.
    """

    root: Path
    clip_id: str
    source: str
    source_mode: str
    resolution: tuple[int, int]
    context: Mapping[str, Any]
    crop_padding: float
    run_id: str
    fixture_id: str
    source_sha256: str
    split: str = "unregistered"

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.crops_dir = self.root / "crops" / self.clip_id
        self.crops_dir.mkdir(parents=True, exist_ok=True)
        self._rows_path = self.root / FP_LOG_NAME
        self._counter = 0
        self._rows: list[dict[str, Any]] = []

    def log_detection(self, *, frame_index: int, time_s: float, frame: np.ndarray,
                      class_label: str, canonical_label: str, group: str,
                      score: float, bbox_norm: list[float],
                      crop_padding: float | None = None) -> dict[str, Any]:
        """Log one weapon-path detection (FP on a known-benign source)."""
        height, width = frame.shape[:2]
        bbox_px = [
            float(bbox_norm[0] * width), float(bbox_norm[1] * height),
            float(bbox_norm[2] * width), float(bbox_norm[3] * height),
        ]
        padding = self.crop_padding if crop_padding is None else crop_padding
        left, top, right, bottom = padded_crop_rect(
            (bbox_px[0], bbox_px[1], bbox_px[2], bbox_px[3]), frame.shape, padding
        )
        crop_name = f"{self.clip_id}_{frame_index:06d}_{self._counter:04d}.png"
        crop_path = self.crops_dir / crop_name
        if not cv2.imwrite(str(crop_path), frame[top:bottom, left:right]):
            raise FPLogError(f"failed to write FP crop {crop_path}")
        record = {
            "schema_version": SCHEMA_VERSION,
            "event": "weapon_fp",
            "log_id": f"{self.clip_id}:{frame_index}:{self._counter}",
            "run_id": self.run_id,
            "fixture_id": self.fixture_id,
            "source_sha256": self.source_sha256,
            "split": self.split,
            "clip_id": self.clip_id,
            "frame_index": int(frame_index),
            "time_s": float(time_s),
            "source": self.source,
            "source_mode": self.source_mode,
            "class": class_label,
            "canonical_label": canonical_label,
            "group": group,
            "score": float(score),
            "bbox_norm": [float(value) for value in bbox_norm],
            "bbox_px": bbox_px,
            "crop_ref": str(crop_path.relative_to(self.root)).replace("\\", "/"),
            "resolution": [int(width), int(height)],
            "context": dict(self.context),
        }
        validate_fp_record(record)
        with self._rows_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, allow_nan=False) + "\n")
        self._counter += 1
        self._rows.append(record)
        return record

    @property
    def rows(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def summary(self) -> dict[str, Any]:
        """Denominators for the run: frames seen vs detections logged."""
        per_class: dict[str, int] = {}
        per_group: dict[str, int] = {}
        for row in self._rows:
            per_class[row["class"]] = per_class.get(row["class"], 0) + 1
            per_group[row["group"]] = per_group.get(row["group"], 0) + 1
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "fixture_id": self.fixture_id,
            "source_sha256": self.source_sha256,
            "split": self.split,
            "clip_id": self.clip_id,
            "source": self.source,
            "source_mode": self.source_mode,
            "detections_logged": len(self._rows),
            "per_class": per_class,
            "per_group": per_group,
            "log_path": str(self._rows_path),
        }
