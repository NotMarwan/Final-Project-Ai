"""Frame and crop reference schema (v1) for the Sentinel capture path.

This is the shared contract between the tracking/counting slice (S-04, WT-22),
face detection/association (WT-21) and image enhancement (WT-23). It is
deliberately dependency-free (no numpy import required for the record layer) so
every producer can emit and every consumer can validate the same wire dicts.

Contracts honoured:
- SC-6  ``captured_at`` is the monotonic capture clock, ``sample_timestamp`` is
  the media clock (file sources only, else ``None``), ``iso_time`` is UTC.
- SC-7  observation identity is monotone and unique per producer
  (``frame_id``/``crop_id`` embed the camera namespace and capture sequence).
- SC-8  every derivative carries a parent reference (``derivative_of``) and an
  explicit hash of the exact bytes handed over (``*_sha256`` + ``hash_format``).

Policy: crop references carry camera-scoped track ids only. There is no
identity claim anywhere in this schema; enhanced outputs are marked
``is_derivative`` so an operator can never mistake an enhancement for a
camera-observed frame.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping, Optional, Sequence

FRAME_REF_SCHEMA = "sentinel.frame_ref/v1"
CROP_REF_SCHEMA = "sentinel.crop_ref/v1"

BBoxSpace = Literal["source", "model_input"]
SubjectKind = Literal["person", "face", "frame"]

_BBOX_SPACES = ("source", "model_input")
_SUBJECT_KINDS = ("person", "face", "frame")


class FrameReferenceError(ValueError):
    """A malformed frame/crop reference must never be silently accepted."""


def make_frame_id(camera_id: str, frame_sequence: int) -> str:
    """SC-7 monotone identity: ``<camera_id>:<frame_sequence>``."""
    camera = str(camera_id or "").strip()
    if not camera:
        raise FrameReferenceError("frame_id requires a camera_id namespace")
    if int(frame_sequence) < 0:
        raise FrameReferenceError("frame_sequence must be >= 0")
    return f"{camera}:{int(frame_sequence)}"


def make_crop_id(camera_id: str, frame_sequence: int, subject_kind: str,
                 face_index: Optional[int] = None) -> str:
    if subject_kind not in _SUBJECT_KINDS:
        raise FrameReferenceError(f"unknown subject_kind: {subject_kind!r}")
    base = f"{make_frame_id(camera_id, frame_sequence)}:{subject_kind}"
    return f"{base}:{int(face_index)}" if face_index is not None else base


def make_track_ref(camera_id: str, track_id: int) -> str:
    """Camera-scoped track namespace: ``<camera_id>::<track_id>``.

    Multi-camera non-association is structural: two cameras can never produce
    the same track reference, so a cross-camera association is impossible by
    type/value, not by convention.
    """
    camera = str(camera_id or "").strip()
    if not camera:
        raise FrameReferenceError("track_ref requires a camera_id namespace")
    return f"{camera}::{int(track_id)}"


def parse_track_ref(track_ref: str) -> tuple[str, int]:
    camera, _, raw = str(track_ref).partition("::")
    if not camera or not raw:
        raise FrameReferenceError(f"malformed track_ref: {track_ref!r}")
    try:
        return camera, int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise FrameReferenceError(f"malformed track_ref: {track_ref!r}") from exc


def hash_array_raw(frame: Any) -> tuple[str, str]:
    """SHA-256 over the exact C-contiguous raw bytes of an ndarray.

    Returns ``(hex_digest, hash_format)`` where hash_format records shape and
    dtype so a consumer can never mistake two different pixel orders for the
    same asset. The frame is coerced to C-contiguous bytes without a silent
    dtype/colour conversion.
    """
    import numpy as np  # local import keeps the record layer importable without numpy

    array = np.ascontiguousarray(frame)
    if array.dtype != np.uint8 and array.dtype != np.float32:
        array = array.astype(np.uint8, copy=False)
    digest = hashlib.sha256(array.tobytes(order="C")).hexdigest()
    if array.ndim == 3:
        height, width, channels = array.shape
        fmt = f"raw-{array.dtype.name}-{height}x{width}x{channels}"
    else:
        height, width = array.shape[:2]
        fmt = f"raw-{array.dtype.name}-{height}x{width}"
    return digest, fmt


def hash_png_bytes(encoded: bytes) -> tuple[str, str]:
    return hashlib.sha256(bytes(encoded)).hexdigest(), "png"


def _validate_bbox(bbox: Sequence[int] | Sequence[float] | None, name: str) -> tuple[int, int, int, int] | None:
    if bbox is None:
        return None
    if len(bbox) != 4:
        raise FrameReferenceError(f"{name} must have four values")
    values = tuple(int(round(float(value))) for value in bbox)
    if values[2] <= values[0] or values[3] <= values[1]:
        raise FrameReferenceError(f"{name} must be a non-empty xyxy box")
    return values


@dataclass(frozen=True)
class FrameRef:
    """Reference to one stored frame of the capture ring."""

    camera_id: str
    frame_sequence: int
    captured_at: float
    iso_time: str
    width: int
    height: int
    frame_sha256: str
    hash_format: str
    sample_timestamp: Optional[float] = None
    source_width: Optional[int] = None
    source_height: Optional[int] = None
    bbox_space: BBoxSpace = "model_input"
    schema: str = field(default=FRAME_REF_SCHEMA, init=False)

    @property
    def frame_id(self) -> str:
        return make_frame_id(self.camera_id, self.frame_sequence)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "frame_id": self.frame_id, **asdict(self)}

    def to_dict_minimal(self) -> dict[str, Any]:
        """SC-8 parent reference: identity + hash only, no redundant metrics."""
        return {
            "schema": self.schema,
            "frame_id": self.frame_id,
            "camera_id": self.camera_id,
            "frame_sequence": self.frame_sequence,
            "captured_at": self.captured_at,
            "sample_timestamp": self.sample_timestamp,
            "iso_time": self.iso_time,
            "frame_sha256": self.frame_sha256,
            "hash_format": self.hash_format,
        }


@dataclass(frozen=True)
class CropRef:
    """Reference to a named region of a stored frame (or of another crop)."""

    camera_id: str
    frame_sequence: int
    captured_at: float
    iso_time: str
    subject_kind: SubjectKind
    bbox_xyxy: tuple[int, int, int, int]
    bbox_space: BBoxSpace
    source_frame_sha256: str
    hash_format: str
    bbox_xyxy_source: Optional[tuple[int, int, int, int]] = None
    track_ref: Optional[str] = None
    face_index: Optional[int] = None
    alert_id: Optional[str] = None
    sample_timestamp: Optional[float] = None
    score_vector: Optional[dict[str, float]] = None
    is_derivative: bool = False
    derivative_of: Optional[str] = None
    schema: str = field(default=CROP_REF_SCHEMA, init=False)

    @property
    def crop_id(self) -> str:
        return make_crop_id(self.camera_id, self.frame_sequence, self.subject_kind, self.face_index)

    @property
    def frame_id(self) -> str:
        return make_frame_id(self.camera_id, self.frame_sequence)

    def to_dict(self) -> dict[str, Any]:
        payload = {"schema": self.schema, "crop_id": self.crop_id, "frame_id": self.frame_id, **asdict(self)}
        return payload

    def to_dict_minimal(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "crop_id": self.crop_id,
            "frame_id": self.frame_id,
            "camera_id": self.camera_id,
            "subject_kind": self.subject_kind,
            "bbox_xyxy": list(self.bbox_xyxy),
            "bbox_space": self.bbox_space,
            "source_frame_sha256": self.source_frame_sha256,
            "hash_format": self.hash_format,
            "is_derivative": self.is_derivative,
            "derivative_of": self.derivative_of,
        }


def frame_ref_from_dict(payload: Mapping[str, Any]) -> FrameRef:
    data = dict(payload)
    if data.get("schema") != FRAME_REF_SCHEMA:
        raise FrameReferenceError(f"unexpected frame schema: {data.get('schema')!r}")
    if data.get("bbox_space", "model_input") not in _BBOX_SPACES:
        raise FrameReferenceError(f"unknown bbox_space: {data.get('bbox_space')!r}")
    digest = str(data.get("frame_sha256") or "")
    if len(digest) != 64:
        raise FrameReferenceError("frame_sha256 must be a 64-char hex digest")
    return FrameRef(
        camera_id=str(data["camera_id"]),
        frame_sequence=int(data["frame_sequence"]),
        captured_at=float(data["captured_at"]),
        iso_time=str(data["iso_time"]),
        width=int(data["width"]),
        height=int(data["height"]),
        frame_sha256=digest,
        hash_format=str(data["hash_format"]),
        sample_timestamp=(None if data.get("sample_timestamp") is None else float(data["sample_timestamp"])),
        source_width=(None if data.get("source_width") is None else int(data["source_width"])),
        source_height=(None if data.get("source_height") is None else int(data["source_height"])),
        bbox_space=data.get("bbox_space", "model_input"),
    )


def crop_ref_from_dict(payload: Mapping[str, Any]) -> CropRef:
    data = dict(payload)
    if data.get("schema") != CROP_REF_SCHEMA:
        raise FrameReferenceError(f"unexpected crop schema: {data.get('schema')!r}")
    if data.get("subject_kind") not in _SUBJECT_KINDS:
        raise FrameReferenceError(f"unknown subject_kind: {data.get('subject_kind')!r}")
    if data.get("bbox_space") not in _BBOX_SPACES:
        raise FrameReferenceError(f"unknown bbox_space: {data.get('bbox_space')!r}")
    digest = str(data.get("source_frame_sha256") or "")
    if len(digest) != 64:
        raise FrameReferenceError("source_frame_sha256 must be a 64-char hex digest")
    track_ref = data.get("track_ref")
    if track_ref is not None:
        parse_track_ref(str(track_ref))
    return CropRef(
        camera_id=str(data["camera_id"]),
        frame_sequence=int(data["frame_sequence"]),
        captured_at=float(data["captured_at"]),
        iso_time=str(data["iso_time"]),
        subject_kind=data["subject_kind"],
        bbox_xyxy=_validate_bbox(data["bbox_xyxy"], "bbox_xyxy"),
        bbox_space=data["bbox_space"],
        source_frame_sha256=digest,
        hash_format=str(data["hash_format"]),
        bbox_xyxy_source=_validate_bbox(data.get("bbox_xyxy_source"), "bbox_xyxy_source"),
        track_ref=(None if track_ref is None else str(track_ref)),
        face_index=(None if data.get("face_index") is None else int(data["face_index"])),
        alert_id=(None if data.get("alert_id") is None else str(data["alert_id"])),
        sample_timestamp=(None if data.get("sample_timestamp") is None else float(data["sample_timestamp"])),
        score_vector=(None if data.get("score_vector") is None else dict(data["score_vector"])),
        is_derivative=bool(data.get("is_derivative", False)),
        derivative_of=(None if data.get("derivative_of") is None else str(data["derivative_of"])),
    )
