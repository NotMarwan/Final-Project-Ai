"""Evidence-safe image enhancement (WT-23) with SC-8 derivative records.

Design constraints (binding, from the WT-08 research catalog §5.2–§5.3):

* Originals are immutable. Every enhancement output is a *derivative* with its
  own file, its own hash, and a chained transformation record appended to
  ``evidence_ledger.jsonl`` (SC-8). Records are append-only; nothing rewrites
  an existing line.
* Tier 0 (this module's default) is deterministic pixel work only — crop,
  CLAHE, gamma, classical denoise. No learned model, no invented texture. The
  same input and parameters must produce byte-identical output.
* Every derivative carries the ``ENHANCED DERIVATIVE`` label (or
  ``CROP DERIVATIVE`` when no pixel-altering operation ran) in three places:
  the image's own PNG metadata, the ledger record, and the UI contract fields.
* Enhancement is strictly post-alert. Nothing here may run on the alert path;
  the scheduler's ``enqueue`` is O(1) under a short lock and performs no I/O and
  no model work.
* Missing parents fail loudly. This module never substitutes a placeholder hash
  such as ``"N/A"`` (runtime-map R-4): a derivative record requires the real
  SHA-256 of the exact parent asset.

The module is self-contained apart from ``backend/evidence.py`` (chain
primitive) and cv2/numpy.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import os
import platform
import struct
import threading
import time
import zlib
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

import cv2
import numpy as np

from evidence import (
    DERIVATIVE_RECORD_TYPE,
    EvidenceLedger,
    EvidenceLedgerConfig,
)

ENHANCE_MODULE_VERSION = "1.0.0"

DERIVATIVE_LABEL_ENHANCED = "ENHANCED DERIVATIVE"
DERIVATIVE_LABEL_CROP = "CROP DERIVATIVE"
LABEL_TEXT_ENHANCED = "ENHANCED DERIVATIVE — synthesized detail may be present; not an observation"
LABEL_TEXT_CROP = "CROP DERIVATIVE — unmodified pixels from the original"
DERIVATIVE_DISCLAIMER = "enhanced derivative — detail may be reconstructed"

PARENT_KINDS = ("face_crop", "person_crop", "frame", "snapshot")
SUBJECT_KINDS = ("face", "person", "frame")
HASH_BASIS_FILE = "file-bytes"
HASH_BASIS_PIXELS = "raw-pixels-bgr"

# Tier-0 operations that alter pixels. Anything here makes a derivative
# "enhanced"; a crop-only derivation stays a plain (unmodified-pixel) crop.
PIXEL_ALTERING_OPS = frozenset({"clahe", "gamma", "denoise_lite", "contrast_stretch"})
# Learned (tier-1) operations are always pixel-altering and always generative-risk.
LEARNED_OPERATION_NAMES = frozenset({"real_esrgan_x4"})


class EnhancementError(RuntimeError):
    """Base class for errors safe to classify in audit/telemetry records."""

    code = "enhancement_error"


class DerivativeParentMissing(EnhancementError):
    code = "derivative_parent_missing"


class DerivativeParentUnhashed(EnhancementError):
    code = "derivative_parent_hash_unavailable"


class DerivativeOrderingError(EnhancementError):
    code = "derivative_without_alert_receipt"


class DerivativeRecordInvalid(EnhancementError):
    code = "derivative_record_invalid"


class DerivativeOutputMissing(EnhancementError):
    code = "derivative_output_missing"


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------


def sha256_file_bytes(path: Path | str) -> str:
    """SHA-256 of a file's raw bytes. Never substitutes a placeholder."""
    p = Path(path)
    if not p.exists():
        raise DerivativeParentMissing(f"Parent asset does not exist: {p}")
    if not p.is_file():
        raise DerivativeParentMissing(f"Parent asset is not a file: {p}")
    digest = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raw_pixel_hash_format(bgr: np.ndarray) -> str:
    """Canonical layout string for the raw-pixel hash (shared wire contract).

    Format: ``raw-bgr-{height}x{width}x{channels}-{dtype}`` — e.g.
    ``raw-bgr-720x1280x3-uint8``. WT-22 records the same string in
    ``hash_format`` for handed-over frames, so a hash can always be
    recomputed from the bytes it describes.
    """
    if not isinstance(bgr, np.ndarray) or bgr.ndim != 3:
        raise DerivativeParentUnhashed("Parent pixels must be a 3-channel ndarray")
    return f"raw-bgr-{bgr.shape[0]}x{bgr.shape[1]}x{bgr.shape[2]}-{np.dtype(bgr.dtype).name}"


def sha256_pixels(bgr: np.ndarray) -> str:
    """Canonical SHA-256 of an in-memory BGR image (layout in ``raw_pixel_hash_format``).

    The digest covers exactly the C-contiguous byte buffer of the handed-over
    pixels, so a peer holding the same buffer can verify it byte-for-byte.
    """
    if not isinstance(bgr, np.ndarray) or bgr.ndim != 3:
        raise DerivativeParentUnhashed("Parent pixels must be a 3-channel ndarray")
    contiguous = np.ascontiguousarray(bgr)
    return hashlib.sha256(contiguous.tobytes()).hexdigest()


def pixel_hash(bgr: np.ndarray) -> tuple[str, str]:
    """(sha256, layout) for an in-memory frame."""
    return sha256_pixels(bgr), raw_pixel_hash_format(bgr)


def is_placeholder_hash(value: Any) -> bool:
    """True for the ledger's legacy 'N/A'/'unknown' placeholder substitutions."""
    if not isinstance(value, str):
        return True
    text = value.strip().lower()
    if text in {"n/a", "na", "none", "null", "unknown", "", "0"}:
        return True
    return len(text) != 64 or any(character not in "0123456789abcdef" for character in text)


# ---------------------------------------------------------------------------
# Tier-0 deterministic operations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tier0Ops:
    """Deterministic tier-0 enhancement parameters (all recorded per output)."""

    crop: bool = True
    clahe: bool = False
    clahe_clip_limit: float = 2.0
    clahe_tile_grid: tuple[int, int] = (8, 8)
    gamma: float | None = None
    denoise_lite: bool = False
    denoise_h: float = 3.0
    denoise_template_window: int = 7
    denoise_search_window: int = 21
    contrast_stretch: bool = False

    def is_identity(self) -> bool:
        """True when no pixel-altering operation is enabled."""
        return not (self.clahe or self.gamma or self.denoise_lite or self.contrast_stretch)


def default_tier0_ops() -> Tier0Ops:
    """Shipped default tier-0 op set, chosen from measurement (EXP-23-01).

    ``gamma 1.2`` measured PSNR 25.96 dB / SSIM 0.977 / LPIPS 0.0101 / identity
    0.9935 — the least distorted op that still lifts an under-exposed crop.
    CLAHE is opt-in (identity 0.913–0.916, near the 0.90 bound) and denoise-lite
    is never combined by default (measured 0.8960, refused by the tier-0 bounds).
    """
    return Tier0Ops(gamma=1.2)


def clamp_bbox(bbox: Sequence[int], width: int, height: int) -> tuple[int, int, int, int]:
    """Clamp an xyxy box to the image; raise when it is degenerate."""
    if len(bbox) != 4:
        raise EnhancementError("Bounding box must have four values")
    x1, y1, x2, y2 = (int(round(float(value))) for value in bbox)
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    if x2 - x1 < 2 or y2 - y1 < 2:
        raise EnhancementError(f"Degenerate crop box after clamping: {(x1, y1, x2, y2)}")
    return (x1, y1, x2, y2)


def crop_frame(bgr: np.ndarray, bbox: Sequence[int]) -> tuple[np.ndarray, dict[str, Any]]:
    x1, y1, x2, y2 = clamp_bbox(bbox, bgr.shape[1], bgr.shape[0])
    crop = bgr[y1:y2, x1:x2]
    if crop.size == 0:
        raise EnhancementError("Crop produced an empty image")
    return crop, {"name": "crop", "params": {"bboxXyxy": [x1, y1, x2, y2], "outputSize": [int(crop.shape[1]), int(crop.shape[0])]}}


def apply_clahe(bgr: np.ndarray, clip_limit: float, tile_grid: tuple[int, int]) -> tuple[np.ndarray, dict[str, Any]]:
    """CLAHE on the LAB luminance channel (deterministic, pointwise-ish)."""
    if clip_limit <= 0:
        raise EnhancementError("CLAHE clip limit must be positive")
    tile_x, tile_y = (int(tile_grid[0]), int(tile_grid[1]))
    if tile_x < 1 or tile_y < 1:
        raise EnhancementError("CLAHE tile grid must be positive")
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=float(clip_limit), tileGridSize=(tile_x, tile_y))
    lightness = clahe.apply(lightness)
    merged = cv2.merge((lightness, channel_a, channel_b))
    out = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    return out, {"name": "clahe", "params": {"space": "LAB-L", "clipLimit": float(clip_limit), "tileGridSize": [tile_x, tile_y]}}


def apply_gamma(bgr: np.ndarray, gamma: float) -> tuple[np.ndarray, dict[str, Any]]:
    """Pointwise gamma via a 256-entry LUT (deterministic, invertible-ish)."""
    if gamma <= 0:
        raise EnhancementError("Gamma must be positive")
    inverse = 1.0 / float(gamma)
    table = np.array([((index / 255.0) ** inverse) * 255.0 for index in range(256)], dtype=np.uint8)
    out = cv2.LUT(bgr, table)
    return out, {"name": "gamma", "params": {"gamma": float(gamma), "lutEntries": 256}}


def apply_denoise_lite(
    bgr: np.ndarray,
    h: float,
    template_window: int,
    search_window: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Classical non-local-means denoise: averages existing pixels only."""
    if h < 0:
        raise EnhancementError("Denoise strength must be non-negative")
    out = cv2.fastNlMeansDenoisingColored(
        bgr,
        None,
        float(h),
        float(h),
        int(template_window),
        int(search_window),
    )
    return out, {
        "name": "denoise_lite",
        "params": {
            "algorithm": "fastNlMeansDenoisingColored",
            "h": float(h),
            "templateWindowSize": int(template_window),
            "searchWindowSize": int(search_window),
        },
    }


def apply_contrast_stretch(bgr: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """Per-channel min/max stretch over the observed pixels (deterministic)."""
    out = bgr.copy()
    low, high = np.percentile(bgr, 1.0), np.percentile(bgr, 99.0)
    if high <= low:
        return out, {"name": "contrast_stretch", "params": {"lowPercentile": 1.0, "highPercentile": 99.0, "applied": False}}
    scaled = (bgr.astype(np.float32) - float(low)) * (255.0 / float(high - low))
    out = np.clip(scaled, 0, 255).astype(np.uint8)
    return out, {
        "name": "contrast_stretch",
        "params": {"lowPercentile": 1.0, "highPercentile": 99.0, "lowValue": float(low), "highValue": float(high), "applied": True},
    }


def apply_tier0(bgr: np.ndarray, ops: Tier0Ops, bbox: Sequence[int] | None = None) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Apply tier-0 operations in a fixed order and return (image, operations)."""
    if not isinstance(bgr, np.ndarray) or bgr.ndim != 3 or bgr.shape[2] != 3:
        raise EnhancementError("Tier-0 input must be a 3-channel BGR ndarray")
    operations: list[dict[str, Any]] = []
    out = bgr
    if ops.crop:
        if bbox is None:
            raise EnhancementError("Crop requested without a bounding box")
        out, record = crop_frame(out, bbox)
        operations.append(record)
    if ops.clahe:
        out, record = apply_clahe(out, ops.clahe_clip_limit, ops.clahe_tile_grid)
        operations.append(record)
    if ops.gamma is not None:
        out, record = apply_gamma(out, float(ops.gamma))
        operations.append(record)
    if ops.contrast_stretch:
        out, record = apply_contrast_stretch(out)
        operations.append(record)
    if ops.denoise_lite:
        out, record = apply_denoise_lite(out, ops.denoise_h, ops.denoise_template_window, ops.denoise_search_window)
        operations.append(record)
    return np.ascontiguousarray(out), operations


def operations_are_enhancing(operations: Iterable[Mapping[str, Any]]) -> bool:
    """True when any recorded operation altered pixels beyond cropping."""
    return any(
        entry.get("name") in PIXEL_ALTERING_OPS or entry.get("name") in LEARNED_OPERATION_NAMES
        for entry in operations
    )


# ---------------------------------------------------------------------------
# On-image labeling (PNG tEXt metadata)
# ---------------------------------------------------------------------------


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _png_text_chunks(labels: Mapping[str, str]) -> bytes:
    """tEXt (Latin-1) when possible, iTXt (UTF-8) otherwise — never lossy."""
    payload = b""
    for key, value in labels.items():
        text = str(value)
        keyword = str(key).encode("latin-1", "replace")[:79]
        try:
            encoded = text.encode("latin-1")
        except UnicodeEncodeError:
            # iTXt: keyword\0 flag(0=uncompressed) method(0) language\0 translated\0 text(UTF-8)
            body = keyword + b"\x00" + b"\x00" + b"\x00" + b"\x00" + b"\x00" + text.encode("utf-8")
            payload += _png_chunk(b"iTXt", body)
        else:
            payload += _png_chunk(b"tEXt", keyword + b"\x00" + encoded)
    return payload


def encode_png_with_labels(bgr: np.ndarray, labels: Mapping[str, str]) -> bytes:
    """Encode BGR to PNG and insert label chunks before IEND.

    The labels are part of the file itself, so a derivative cannot be separated
    from its provenance by copying the file.
    """
    success, buffer = cv2.imencode(".png", bgr, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
    if not success:
        raise EnhancementError("PNG encoding failed")
    raw = buffer.tobytes()
    signature = raw[:8]
    if signature != b"\x89PNG\r\n\x1a\n":
        raise EnhancementError("Unexpected PNG signature from encoder")
    chunks = bytearray(signature)
    offset = 8
    inserted = False
    text_chunks = _png_text_chunks(labels)
    while offset < len(raw):
        length = struct.unpack(">I", raw[offset : offset + 4])[0]
        kind = raw[offset + 4 : offset + 8]
        end = offset + 12 + length
        if kind == b"IEND":
            chunks += text_chunks
            chunks += raw[offset:end]
            inserted = True
            break
        chunks += raw[offset:end]
        offset = end
    if not inserted:
        raise EnhancementError("PNG stream had no IEND chunk")
    return bytes(chunks)


def read_png_text_labels(png_bytes: bytes) -> dict[str, str]:
    """Parse tEXt and iTXt chunks back out (used to verify on-image labeling)."""
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise EnhancementError("Not a PNG stream")
    labels: dict[str, str] = {}
    offset = 8
    while offset < len(png_bytes):
        length = struct.unpack(">I", png_bytes[offset : offset + 4])[0]
        kind = png_bytes[offset + 4 : offset + 8]
        data = png_bytes[offset + 8 : offset + 8 + length]
        if kind == b"tEXt" and b"\x00" in data:
            keyword, _, text = data.partition(b"\x00")
            labels[keyword.decode("latin-1")] = text.decode("latin-1")
        elif kind == b"iTXt":
            keyword, _, rest = data.partition(b"\x00")
            if len(rest) >= 2:
                remainder = rest[2:]
                if b"\x00" in remainder:
                    _, _, translated = remainder.partition(b"\x00")
                    if b"\x00" in translated:
                        _, _, text = translated.partition(b"\x00")
                        labels[keyword.decode("latin-1")] = text.decode("utf-8")
        offset += 12 + length
        if kind == b"IEND":
            break
    return labels


def write_derivative_png(
    path: Path | str,
    bgr: np.ndarray,
    *,
    labels: Mapping[str, str],
    fsync: bool = True,
) -> str:
    """Write a labeled derivative PNG atomically (``.part`` then replace).

    Returns the SHA-256 of the published file bytes.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = encode_png_with_labels(bgr, labels)
    temporary = target.with_suffix(target.suffix + ".part")
    with temporary.open("wb") as fh:
        fh.write(payload)
        fh.flush()
        if fsync:
            os.fsync(fh.fileno())
    temporary.replace(target)
    if not target.exists():
        raise DerivativeOutputMissing(f"Derivative was not published: {target}")
    return hashlib.sha256(target.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Timestamps (SC-6)
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_timestamp(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DerivativeRecordInvalid(f"{field_name} must be numeric or null") from exc
    if not np.isfinite(number):
        raise DerivativeRecordInvalid(f"{field_name} must be finite")
    return number


# ---------------------------------------------------------------------------
# Derivative records (SC-8 extension)
# ---------------------------------------------------------------------------

REQUIRED_DERIVATIVE_KEYS = (
    "recordType",
    "derivativeId",
    "alertId",
    "cameraId",
    "timestamp",
    "producedAt",
    "parentKind",
    "parentPath",
    "parentSha256",
    "parentCapturedAt",
    "parentSampleTimestamp",
    "subjectRef",
    "derivativePath",
    "derivativeSha256",
    "derivativeFormat",
    "tier",
    "derivationBasis",
    "operations",
    "model",
    "libraryVersions",
    "operator",
    "isEnhanced",
    "label",
    "labelText",
    "labelLocations",
    "uiContract",
    "harness",
)


def library_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "numpy": np.__version__,
    }


def ui_contract_fields(is_enhanced: bool) -> dict[str, Any]:
    """The fields the UI contract (WT-25) must render for any derivative."""
    return {
        "originalFirst": True,
        "originalRequired": True,
        "badge": DERIVATIVE_LABEL_ENHANCED if is_enhanced else DERIVATIVE_LABEL_CROP,
        "disclaimer": DERIVATIVE_DISCLAIMER if is_enhanced else "crop derivative — unmodified pixels from the original",
    }


def derivative_labels(is_enhanced: bool) -> dict[str, str]:
    return {
        "Label": DERIVATIVE_LABEL_ENHANCED if is_enhanced else DERIVATIVE_LABEL_CROP,
        "Disclaimer": LABEL_TEXT_ENHANCED if is_enhanced else LABEL_TEXT_CROP,
    }


def build_derivative_record(
    *,
    derivative_id: str,
    alert_id: str,
    camera_id: str | None,
    parent_kind: str,
    parent_path: str,
    parent_sha256: str,
    parent_hash_basis: str,
    parent_hash_format: str | None = None,
    parent_captured_at: Any = None,
    parent_sample_timestamp: Any = None,
    subject_ref: Mapping[str, Any],
    derivative_path: str,
    derivative_sha256: str,
    operations: Sequence[Mapping[str, Any]],
    tier: int = 0,
    model: Mapping[str, Any] | None = None,
    harness: Mapping[str, Any] | None = None,
    operator: Mapping[str, Any] | None = None,
    parent_source: Mapping[str, Any] | None = None,
    produced_at: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a fully labeled derivative record, validating hard requirements."""
    if not derivative_id:
        raise DerivativeRecordInvalid("derivativeId is required")
    if not alert_id:
        raise DerivativeRecordInvalid("alertId is required")
    if parent_kind not in PARENT_KINDS:
        raise DerivativeRecordInvalid(f"parentKind must be one of {PARENT_KINDS}")
    if tier not in (0, 1):
        raise DerivativeRecordInvalid("tier must be 0 or 1")
    if is_placeholder_hash(parent_sha256):
        raise DerivativeParentUnhashed(
            f"parentSha256 must be a real SHA-256 hash (got {parent_sha256!r}); placeholders such as 'N/A' are refused"
        )
    if is_placeholder_hash(derivative_sha256):
        raise DerivativeOutputMissing(f"derivativeSha256 must be a real SHA-256 hash (got {derivative_sha256!r})")
    if parent_hash_basis not in (HASH_BASIS_FILE, HASH_BASIS_PIXELS):
        raise DerivativeRecordInvalid(f"parentHashBasis must be one of {(HASH_BASIS_FILE, HASH_BASIS_PIXELS)}")

    subject = dict(subject_ref)
    if subject.get("kind") not in SUBJECT_KINDS:
        raise DerivativeRecordInvalid(f"subjectRef.kind must be one of {SUBJECT_KINDS}")

    operation_list = [dict(entry) for entry in operations]
    enhanced = operations_are_enhancing(operation_list)
    label = DERIVATIVE_LABEL_ENHANCED if enhanced else DERIVATIVE_LABEL_CROP
    label_text = LABEL_TEXT_ENHANCED if enhanced else LABEL_TEXT_CROP
    if tier == 1 and not enhanced:
        raise DerivativeRecordInvalid("tier 1 requires at least one pixel-altering operation")
    model_block = dict(model) if model is not None else {"name": None, "version": None, "weightsSha256": None, "license": None}
    if tier == 1:
        if not model_block.get("name") or is_placeholder_hash(model_block.get("weightsSha256")):
            raise DerivativeRecordInvalid("tier 1 requires a model name and a real weights hash")

    record: dict[str, Any] = {
        "recordType": DERIVATIVE_RECORD_TYPE,
        "derivativeId": str(derivative_id),
        "alertId": str(alert_id),
        "cameraId": camera_id,
        "timestamp": timestamp or utc_now_iso(),
        "producedAt": produced_at or utc_now_iso(),
        "parentKind": parent_kind,
        "parentPath": str(parent_path),
        "parentSha256": str(parent_sha256),
        "parentHashBasis": parent_hash_basis,
        "parentHashFormat": parent_hash_format if parent_hash_format is not None else parent_hash_basis,
        "parentCapturedAt": _normalize_timestamp(parent_captured_at, "parentCapturedAt"),
        "parentSampleTimestamp": _normalize_timestamp(parent_sample_timestamp, "parentSampleTimestamp"),
        "subjectRef": subject,
        "derivativePath": str(derivative_path),
        "derivativeSha256": str(derivative_sha256),
        "derivativeFormat": "png",
        "tier": int(tier),
        "derivationBasis": "deterministic" if tier == 0 else "learned",
        "operations": operation_list,
        "model": model_block,
        "libraryVersions": library_versions(),
        "operator": dict(operator)
        if operator is not None
        else {
            "id": "system:backend.enhance",
            "kind": "system",
            "module": "backend.enhance",
            "moduleVersion": ENHANCE_MODULE_VERSION,
        },
        "isEnhanced": bool(enhanced),
        "label": label,
        "labelText": label_text,
        "labelLocations": ["image_metadata", "ledger_record", "ui_contract"],
        "uiContract": ui_contract_fields(enhanced),
        "harness": dict(harness) if harness is not None else {"status": "not_measured", "passed": None},
    }
    if parent_source is not None:
        record["parentSource"] = dict(parent_source)
    validate_derivative_record(record)
    return record


def validate_derivative_record(record: Mapping[str, Any]) -> None:
    """Fail loudly on a derivative record that breaks the frozen schema."""
    missing = [key for key in REQUIRED_DERIVATIVE_KEYS if key not in record]
    if missing:
        raise DerivativeRecordInvalid(f"Derivative record missing required keys: {missing}")
    if record.get("recordType") != DERIVATIVE_RECORD_TYPE:
        raise DerivativeRecordInvalid(f"recordType must be {DERIVATIVE_RECORD_TYPE!r}")
    if is_placeholder_hash(record.get("parentSha256")):
        raise DerivativeParentUnhashed("Derivative record carries a placeholder parent hash")
    if is_placeholder_hash(record.get("derivativeSha256")):
        raise DerivativeOutputMissing("Derivative record carries a placeholder output hash")
    if record.get("tier") == 1 and record.get("derivationBasis") != "learned":
        raise DerivativeRecordInvalid("tier 1 records must declare derivationBasis='learned'")
    if record.get("tier") == 0 and record.get("derivationBasis") != "deterministic":
        raise DerivativeRecordInvalid("tier 0 records must declare derivationBasis='deterministic'")
    ui = record.get("uiContract")
    if not isinstance(ui, Mapping) or ui.get("originalFirst") is not True or ui.get("originalRequired") is not True:
        raise DerivativeRecordInvalid("Derivative records must require original-first display")
    if not record.get("label") or not record.get("labelText"):
        raise DerivativeRecordInvalid("Derivative records must carry label and labelText")
    if "image_metadata" not in (record.get("labelLocations") or []):
        raise DerivativeRecordInvalid("Derivative records must declare image_metadata labeling")


def record_is_derivative(record: Mapping[str, Any]) -> bool:
    return record.get("recordType") == DERIVATIVE_RECORD_TYPE


class DerivativeLedger(EvidenceLedger):
    """Append-only derivative records on the same SC-8 chain as alert receipts.

    Reuses ``EvidenceLedger``'s chain validation, per-path lock registry and
    fsync discipline. Two rules are enforced here beyond the parent class:

    * a derivative may only be appended after the alert's receipt record, so
      the receipt lookups (``EvidenceLedger.get``/``append_entry``) can never be
      shadowed by a derivative; and
    * records are de-duplicated on ``derivativeId`` (idempotent replay), never
      on ``alertId``.
    """

    def __init__(self, config: EvidenceLedgerConfig):
        super().__init__(config)

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None, base_dir: Path) -> "DerivativeLedger":
        return cls(EvidenceLedgerConfig.from_settings(settings, base_dir))

    def has_alert_receipt(self, alert_id: str) -> bool:
        for record in self._read_records():
            if record.get("alertId") == alert_id and not record_is_derivative(record):
                return True
        return False

    def get_derivative(self, derivative_id: str) -> dict[str, Any] | None:
        for record in reversed(self._read_records()):
            if record.get("derivativeId") == derivative_id:
                return record
        return None

    def derivatives_for_alert(self, alert_id: str) -> list[dict[str, Any]]:
        return [record for record in self._read_records() if record_is_derivative(record) and record.get("alertId") == alert_id]

    def append_derivative(self, record: Mapping[str, Any]) -> dict[str, Any]:
        validate_derivative_record(record)
        derivative_id = str(record["derivativeId"])
        alert_id = str(record["alertId"])
        with self._lock:
            existing = self.get_derivative(derivative_id)
            if existing is not None:
                return existing
            if not self.has_alert_receipt(alert_id):
                raise DerivativeOrderingError(
                    f"Refusing to append derivative {derivative_id!r}: no alert receipt for {alert_id!r} exists yet"
                )
            # Chain mechanics (prevHash/currentHash, fsync, rollback on storage
            # failure) live in the shared S-07 primitive; idempotency and the
            # receipt-ordering guard are derivative-specific and stay here.
            return self.append_record(dict(record))


def verify_derivative_chain(path: Path | str) -> list[dict[str, Any]]:
    """Verify the chain and schema of every derivative record in a ledger."""
    ledger = DerivativeLedger(EvidenceLedgerConfig(Path(path)))
    records = ledger._read_records()
    for record in records:
        if record_is_derivative(record):
            validate_derivative_record(record)
    return records


# ---------------------------------------------------------------------------
# Derivative identity (SC-7-style monotone ids)
# ---------------------------------------------------------------------------


class DerivativeIdAllocator:
    """Monotone, unique derivative ids within one ledger for one alert."""

    def __init__(self, ledger: DerivativeLedger):
        self._ledger = ledger
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}

    def next_id(self, alert_id: str) -> str:
        with self._lock:
            existing = self._ledger.derivatives_for_alert(alert_id)
            current = self._counters.get(alert_id, 0)
            highest = 0
            for record in existing:
                raw = str(record.get("derivativeId", ""))
                tail = raw.rsplit("-", 1)[-1]
                if tail.isdigit():
                    highest = max(highest, int(tail))
            counter = max(current, highest) + 1
            self._counters[alert_id] = counter
            return f"deriv-{alert_id}-{counter:03d}"


# ---------------------------------------------------------------------------
# Async scheduler and GPU budget policy
# ---------------------------------------------------------------------------


@dataclass
class CropRef:
    """A subject crop request (WT-21/WT-22 supply these).

    Field names follow the shared ``sentinel.crop_ref/v1`` wire contract; the
    extra fields below (``crop_id``, ``track_id_raw``, ``bbox_xyxy_source``,
    ``frame_id``, ``iso_time``, ``is_derivative``, ``derivative_of``) are carried
    verbatim into the derivative record's ``subjectRef``.
    """

    alert_id: str
    camera_id: str | None
    subject_kind: Literal["face", "person", "frame"]
    bbox_xyxy: tuple[int, int, int, int]
    bbox_space: Literal["source", "model_input"] = "source"
    track_id: str | None = None
    track_id_raw: int | None = None
    face_index: int | None = None
    frame_sequence: int | None = None
    captured_at: float | None = None
    sample_timestamp: float | None = None
    iso_time: str | None = None
    parent_kind: str = "frame"
    parent_label: str = "parent"
    crop_id: str | None = None
    frame_id: str | None = None
    bbox_xyxy_source: tuple[int, int, int, int] | None = None
    is_derivative: bool = False
    derivative_of: str | None = None
    hash_format: str | None = None


@dataclass
class EnhancementJob:
    """A post-alert enhancement unit of work."""

    job_id: str
    alert_id: str
    camera_id: str | None
    tier: int
    crop: CropRef
    parent_sha256: str
    parent_path: str
    parent_hash_basis: str
    parent_hash_format: str | None = None
    ops: Tier0Ops = field(default_factory=default_tier0_ops)
    parent_frame: np.ndarray | None = None
    parent_source: dict[str, Any] | None = None
    attempts: int = 0
    not_before: float = 0.0

    def is_ready(self, now: float | None = None) -> bool:
        return self.not_before <= (time.monotonic() if now is None else now)


@dataclass
class GpuBudget:
    """Cooperative GPU budget shared with detection.

    Tier-1 (learned) work may only start while detection is idle. Tier-0 work is
    CPU-only pixel arithmetic and is always allowed, which is also the fallback
    the assignment requires when detection is active.
    """

    detection_active: Callable[[], bool] | None = None
    defer_seconds: float = 0.5
    max_deferrals: int = 3
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _deferrals: int = 0

    def detection_busy(self) -> bool:
        if self.detection_active is None:
            return False
        try:
            return bool(self.detection_active())
        except Exception:  # a broken probe must not enable GPU work
            return True

    def permits(self, tier: int) -> bool:
        if tier <= 0:
            return True
        return not self.detection_busy()

    def note_deferral(self) -> bool:
        """Record a deferral; returns False once the budget is exhausted."""
        with self._lock:
            self._deferrals += 1
            return self._deferrals <= self.max_deferrals

    def reset_deferrals(self) -> None:
        with self._lock:
            self._deferrals = 0

    @property
    def deferrals(self) -> int:
        with self._lock:
            return self._deferrals


@dataclass
class SchedulerStats:
    enqueued: int = 0
    completed: int = 0
    failed: int = 0
    evicted_oldest: int = 0
    deferred_detection_busy: int = 0
    dropped_detection_busy: int = 0
    queue_depth: int = 0
    last_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "enqueued": self.enqueued,
            "completed": self.completed,
            "failed": self.failed,
            "evictedOldest": self.evicted_oldest,
            "deferredDetectionBusy": self.deferred_detection_busy,
            "droppedDetectionBusy": self.dropped_detection_busy,
            "queueDepth": self.queue_depth,
            "lastError": self.last_error,
        }


class EnhancementScheduler:
    """Bounded, drop-oldest, post-alert enhancement worker.

    ``enqueue`` never performs I/O or model work and never waits on the GPU
    budget, so it can be called from the alert/evidence finalization path
    without adding latency there. Jobs that fail are counted and reported, never
    silently retried into the alert path.
    """

    def __init__(
        self,
        handler: Callable[[EnhancementJob], Any],
        *,
        queue_size: int = 8,
        budget: GpuBudget | None = None,
        poll_interval: float = 0.02,
        clock: Callable[[], float] = time.monotonic,
        clock_sleep: Callable[[float], None] = time.sleep,
        name: str = "enhancement-worker",
    ):
        if queue_size < 1:
            raise EnhancementError("queue_size must be at least 1")
        self._handler = handler
        self._queue_size = int(queue_size)
        self._pending: deque[EnhancementJob] = deque()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._budget = budget or GpuBudget()
        self._poll_interval = float(poll_interval)
        self._clock = clock
        self._sleep = clock_sleep
        self.stats = SchedulerStats()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def enqueue(self, job: EnhancementJob) -> bool:
        """O(1), lock-only enqueue with drop-oldest overflow semantics."""
        with self._lock:
            if len(self._pending) >= self._queue_size:
                evicted = self._pending.popleft()
                self.stats.evicted_oldest += 1
                self.stats.last_error = f"evicted {evicted.job_id} (queue full)"
            self._pending.append(job)
            self.stats.enqueued += 1
            self.stats.queue_depth = len(self._pending)
        self._wake.set()
        return True

    def queue_depth(self) -> int:
        with self._lock:
            return len(self._pending)

    def _pop(self) -> EnhancementJob | None:
        with self._lock:
            if not self._pending:
                self.stats.queue_depth = 0
                return None
            job = self._pending.popleft()
            self.stats.queue_depth = len(self._pending)
            return job

    def _requeue(self, job: EnhancementJob) -> None:
        with self._lock:
            if len(self._pending) >= self._queue_size:
                self.stats.evicted_oldest += 1
                self._pending.popleft()
            self._pending.append(job)
            self.stats.queue_depth = len(self._pending)

    def _run(self) -> None:
        while not self._stop.is_set():
            job = self._pop()
            if job is None:
                self._wake.wait(self._poll_interval)
                self._wake.clear()
                continue
            if not job.is_ready(self._clock()):
                self._requeue(job)
                self._wake.wait(self._poll_interval)
                self._wake.clear()
                continue
            if job.tier >= 1 and not self._budget.permits(job.tier):
                self.stats.deferred_detection_busy += 1
                job.attempts += 1
                if not self._budget.note_deferral():
                    self.stats.dropped_detection_busy += 1
                    self.stats.last_error = f"dropped {job.job_id}: detection active, GPU budget exhausted"
                    continue
                job.not_before = self._clock() + self._budget.defer_seconds
                self._requeue(job)
                continue
            if job.tier >= 1:
                self._budget.reset_deferrals()
            try:
                self._handler(job)
            except Exception as exc:  # failures are counted, never propagated
                self.stats.failed += 1
                self.stats.last_error = f"{getattr(exc, 'code', type(exc).__name__)}: {exc}"
            else:
                self.stats.completed += 1

    def drain(self, timeout: float = 5.0) -> bool:
        """Block until the queue is empty (test helper; not used on the alert path)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.queue_depth() == 0:
                return True
            time.sleep(0.005)
        return self.queue_depth() == 0


# ---------------------------------------------------------------------------
# Post-alert orchestration
# ---------------------------------------------------------------------------


def resolve_derivative_path(evidence_dir: Path, alert_id: str, subject_tag: str, frame_tag: str) -> Path:
    """SC-8 derivative layout: EVIDENCE_DIR/derivatives/{alert}.{subject}.enhanced.png."""
    return Path(evidence_dir) / "derivatives" / f"{alert_id}.{subject_tag}.{frame_tag}.enhanced.png"


def subject_tag(crop: CropRef) -> str:
    if crop.subject_kind == "face":
        index = crop.face_index if crop.face_index is not None else 0
        return f"face{index}"
    if crop.subject_kind == "person":
        raw = crop.track_id_raw if crop.track_id_raw is not None else crop.track_id
        text = "0" if raw is None else str(raw)
        safe = "".join(character if character.isalnum() else "_" for character in text)
        return f"person{safe}"
    return "frame"


def frame_tag(crop: CropRef) -> str:
    if crop.sample_timestamp is not None:
        return f"t{int(round(float(crop.sample_timestamp) * 1000))}"
    if crop.frame_sequence is not None:
        return f"f{crop.frame_sequence}"
    if crop.captured_at is not None:
        return f"m{int(round(float(crop.captured_at) * 1000))}"
    return "f0"


class EnhancementService:
    """Ties together ops, on-image labeling, the derivative ledger and the file layout."""

    def __init__(
        self,
        ledger: DerivativeLedger,
        *,
        evidence_dir: Path,
        harness: Any = None,
        ids: DerivativeIdAllocator | None = None,
        operator: Mapping[str, Any] | None = None,
    ):
        self.ledger = ledger
        self.evidence_dir = Path(evidence_dir)
        self.harness = harness
        self.ids = ids or DerivativeIdAllocator(ledger)
        self.operator = dict(operator) if operator is not None else None
        self._parents: dict[str, dict[str, Any]] = {}
        self._parent_lock = threading.Lock()

    def register_parent(
        self,
        *,
        alert_id: str,
        camera_id: str | None,
        parent_path: str,
        parent_sha256: str,
        parent_hash_basis: str,
        parent_hash_format: str | None = None,
        parent_captured_at: float | None = None,
        parent_sample_timestamp: float | None = None,
        parent_source: Mapping[str, Any] | None = None,
    ) -> None:
        """Record the identity of an original so derivatives can reference it."""
        with self._parent_lock:
            self._parents[alert_id] = {
                "cameraId": camera_id,
                "parentPath": str(parent_path),
                "parentSha256": str(parent_sha256),
                "parentHashBasis": parent_hash_basis,
                "parentHashFormat": parent_hash_format if parent_hash_format is not None else parent_hash_basis,
                "parentCapturedAt": parent_captured_at,
                "parentSampleTimestamp": parent_sample_timestamp,
                "parentSource": dict(parent_source) if parent_source is not None else None,
            }

    def known_parent(self, alert_id: str) -> dict[str, Any] | None:
        with self._parent_lock:
            parent = self._parents.get(alert_id)
            return dict(parent) if parent is not None else None

    def enhance(
        self,
        crop: CropRef,
        frame: np.ndarray,
        *,
        ops: Tier0Ops,
        parent_path: str | None = None,
        parent_sha256: str | None = None,
        parent_hash_basis: str | None = None,
        parent_hash_format: str | None = None,
        parent_source: Mapping[str, Any] | None = None,
        tier: int = 0,
        model: Mapping[str, Any] | None = None,
        harness_report: Mapping[str, Any] | None = None,
        operations_override: Sequence[Mapping[str, Any]] | None = None,
        write_image: bool = True,
    ) -> dict[str, Any]:
        """Enhance one crop, publish a labeled PNG and append the SC-8 record.

        ``operations_override`` is how a learned (tier-1) artifact enters the
        ledger: the caller already produced final pixels, so no tier-0 op runs
        and the recorded operation list is the learned one.
        """
        parent = self.known_parent(crop.alert_id) or {}
        parent_path = parent_path if parent_path is not None else parent.get("parentPath")
        parent_sha256 = parent_sha256 if parent_sha256 is not None else parent.get("parentSha256")
        parent_hash_basis = parent_hash_basis if parent_hash_basis is not None else parent.get("parentHashBasis")
        parent_hash_format = parent_hash_format if parent_hash_format is not None else parent.get("parentHashFormat")
        if parent_hash_format is None:
            parent_hash_format = crop.hash_format
        parent_source = parent_source if parent_source is not None else parent.get("parentSource")
        if parent_path is None:
            raise DerivativeParentMissing(f"No parent registered for alert {crop.alert_id!r}")
        if parent_sha256 is None:
            raise DerivativeParentUnhashed(
                f"No parent hash for alert {crop.alert_id!r}; refusing to write an unverifiable derivative"
            )

        if operations_override is not None:
            enhanced = np.ascontiguousarray(frame)
            operations = [dict(entry) for entry in operations_override]
        else:
            enhanced, operations = apply_tier0(frame, ops, crop.bbox_xyxy)
        is_enhanced = operations_are_enhancing(operations)
        derivative_id = self.ids.next_id(crop.alert_id)
        target = resolve_derivative_path(self.evidence_dir, crop.alert_id, subject_tag(crop), frame_tag(crop))
        relative_target = f"{self.evidence_dir.name}/{target.relative_to(self.evidence_dir).as_posix()}"
        labels = derivative_labels(is_enhanced)
        labels["DerivativeId"] = derivative_id
        labels["ParentSha256"] = str(parent_sha256)

        if write_image:
            derivative_sha = write_derivative_png(target, enhanced, labels=labels)
        else:
            derivative_sha = hashlib.sha256(encode_png_with_labels(enhanced, labels)).hexdigest()

        report = dict(harness_report) if harness_report is not None else {"status": "not_measured", "passed": None}
        record = build_derivative_record(
            derivative_id=derivative_id,
            alert_id=crop.alert_id,
            camera_id=crop.camera_id,
            parent_kind=crop.parent_kind,
            parent_path=str(parent_path),
            parent_sha256=str(parent_sha256),
            parent_hash_basis=str(parent_hash_basis or HASH_BASIS_FILE),
            parent_hash_format=str(parent_hash_format) if parent_hash_format is not None else None,
            parent_captured_at=crop.captured_at if crop.captured_at is not None else parent.get("parentCapturedAt"),
            parent_sample_timestamp=crop.sample_timestamp
            if crop.sample_timestamp is not None
            else parent.get("parentSampleTimestamp"),
            subject_ref={
                "kind": crop.subject_kind,
                "cropId": crop.crop_id,
                "faceIndex": crop.face_index,
                "trackId": crop.track_id,
                "trackIdRaw": crop.track_id_raw,
                "bboxXyxy": list(crop.bbox_xyxy),
                "bboxXyxySource": list(crop.bbox_xyxy_source) if crop.bbox_xyxy_source is not None else None,
                "bboxSpace": crop.bbox_space,
                "frameSequence": crop.frame_sequence,
                "frameId": crop.frame_id,
                "isoTime": crop.iso_time,
                "isDerivative": bool(crop.is_derivative),
                "derivativeOf": crop.derivative_of,
                "hashFormat": crop.hash_format,
            },
            derivative_path=relative_target,
            derivative_sha256=derivative_sha,
            operations=operations,
            tier=tier,
            model=model,
            harness=report,
            operator=self.operator,
            parent_source=parent_source,
        )
        written = self.ledger.append_derivative(record)
        return written

    def scheduled_handler(self, job: EnhancementJob) -> dict[str, Any]:
        if job.parent_frame is None:
            raise DerivativeParentMissing(f"Job {job.job_id} has no in-memory parent frame")
        return self.enhance(
            job.crop,
            job.parent_frame,
            ops=job.ops,
            parent_path=job.parent_path,
            parent_sha256=job.parent_sha256,
            parent_hash_basis=job.parent_hash_basis,
            parent_hash_format=job.parent_hash_format,
            parent_source=job.parent_source,
            tier=job.tier,
        )


def enqueue_alert_enhancement(
    scheduler: EnhancementScheduler,
    *,
    alert_id: str,
    camera_id: str | None,
    crops: Sequence[tuple[CropRef, np.ndarray]],
    parent_path: str,
    parent_sha256: str,
    parent_hash_basis: str,
    parent_hash_format: str | None = None,
    parent_source: Mapping[str, Any] | None = None,
    ops: Tier0Ops | None = None,
    tier: int = 0,
) -> int:
    """Publish post-alert enhancement jobs. Safe to call from the alert path."""
    operations = ops or default_tier0_ops()
    count = 0
    for index, (crop, frame) in enumerate(crops):
        job = EnhancementJob(
            job_id=f"{alert_id}:{subject_tag(crop)}:{index}",
            alert_id=alert_id,
            camera_id=camera_id,
            tier=tier,
            crop=replace(crop, alert_id=alert_id, camera_id=camera_id if crop.camera_id is None else crop.camera_id),
            parent_sha256=parent_sha256,
            parent_path=parent_path,
            parent_hash_basis=parent_hash_basis,
            parent_hash_format=parent_hash_format if parent_hash_format is not None else crop.hash_format,
            parent_frame=frame,
            parent_source=dict(parent_source) if parent_source is not None else None,
            ops=operations,
        )
        scheduler.enqueue(job)
        count += 1
    return count
