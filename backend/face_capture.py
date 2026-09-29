"""Incident face capture: detection consumption, association-with-uncertainty,
clear capture, and derivative records. NEVER identity.

Campaign scope boundary (binding): face work = DETECTION + ASSOCIATION WITH
UNCERTAINTY + CLEAR CAPTURE ONLY. This module never identifies people and
never labels perpetrators. ``backend/face_intel.py`` (recognition engine,
F-30) stays unwired; nothing here imports it.

Discipline carried into code (WT-08 §3):
- Association confidence is a HEURISTIC score, UNCALIBRATED, never a
  probability and never evidence of identity.
- Proximity never implies causation: a face near a person track means only
  that the boxes overlap in one camera's frames — it does not establish who
  acted, who is a perpetrator, or any causal role.
- Tracks and faces are namespaced per camera. Cross-camera association is
  impossible by construction (the engine only ever sees one camera's tracks
  per call; emitted ``track_id`` values embed the camera namespace).
- When a track is lost and re-acquired it gets a NEW id; crops from old and
  new tracks are never merged into one "person".
- No usable face frame -> explicit ``absent`` status with reasons. We never
  substitute generated detail for a missing capture.

Frames are consumed from the evidence pre/post fan-out (the same collections
``_write_evidence_clip`` reads) and, when available, WT-22's best-frame
provider. Nothing here duplicates the capture ring.

Coordinate contract (SC mapping, tested in ``tests/test_face_capture.py``):
face boxes are detected in the pixels of the frame handed over; a
``bbox_xyxy`` copy in ORIGINAL SOURCE pixels (``bbox_xyxy_source``) is always
carried alongside via :func:`scale_box_to_source` (uniform-ratio mapping —
the same contract as ``inference_process._scale_person_tracks``; valid for
uniform resize only). Which space a box lives in is recorded in
``bbox_space``; which pixels were hashed is recorded in ``hash_format``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

import cv2
import numpy as np

try:
    from .face_detect import YuNetFaceDetector, reporting_gate, sha256_file
except ImportError:  # plain backend/ imports
    from face_detect import YuNetFaceDetector, reporting_gate, sha256_file

logger = logging.getLogger(__name__)

# --- additive SC-2 / reference schema tags (WT-22 frame_reference.py v1) ---
FRAME_REF_SCHEMA = "sentinel.frame_ref/v1"
CROP_REF_SCHEMA = "sentinel.crop_ref/v1"

# --- association payload semantics (WT-08 §3.2) ---
FACE_ASSOC_META = {
    "confidence_semantics": "heuristic_uncalibrated_not_a_probability",
    "identity": "none — detection and association only; no recognition is performed",
    "causal": False,
    "causal_note": "box proximity never implies causation or perpetrator role",
    "multi_camera": "non_associated — tracks and faces are namespaced per camera",
}


# --------------------------------------------------------------------------
# Coordinate mapping (SC mapping)
# --------------------------------------------------------------------------
def scale_box_to_source(
    box_xyxy: Iterable[float],
    frame_size: tuple[int, int],
    source_size: tuple[int, int],
) -> list[float]:
    """Uniform-ratio mapping of a box from analysis-frame pixels to ORIGINAL
    SOURCE pixels. Mirrors ``inference_process._scale_person_tracks``.

    Valid for uniform resize only — crop/letterbox chains need the full
    transform and are rejected by contract (see module docstring).
    """
    frame_w, frame_h = frame_size
    source_w, source_h = source_size
    if min(frame_w, frame_h, source_w, source_h) <= 0:
        raise ValueError("Invalid coordinate dimensions")
    x1, y1, x2, y2 = (float(v) for v in box_xyxy)
    sx, sy = source_w / frame_w, source_h / frame_h
    out = [
        min(max(x1 * sx, 0.0), float(source_w)),
        min(max(y1 * sy, 0.0), float(source_h)),
        min(max(x2 * sx, 0.0), float(source_w)),
        min(max(y2 * sy, 0.0), float(source_h)),
    ]
    if out[2] <= out[0] or out[3] <= out[1]:
        raise ValueError("Degenerate box after mapping")
    return out


def roundtrip_ok(
    box_xyxy: Iterable[float],
    frame_size: tuple[int, int],
    source_size: tuple[int, int],
    tolerance: float = 1.0,
) -> bool:
    """True when source -> frame -> source stays within ``tolerance`` px."""
    frame_w, frame_h = frame_size
    source_w, source_h = source_size
    sx, sy = frame_w / source_w, frame_h / source_h
    x1, y1, x2, y2 = (float(v) for v in box_xyxy)
    framed = [x1 * sx, y1 * sy, x2 * sx, y2 * sy]
    back = scale_box_to_source(framed, frame_size, source_size)
    return all(abs(a - b) <= tolerance for a, b in zip(back, [x1, y1, x2, y2]))


# --------------------------------------------------------------------------
# Frame / crop references (WT-22 schema v1, dicts; integrate
# backend/frame_reference.py dataclasses at merge time — same fields)
# --------------------------------------------------------------------------
def build_frame_ref(
    *,
    camera_id: str,
    frame_sequence: int,
    captured_at: float,
    sample_timestamp: Optional[float],
    width: int,
    height: int,
    source_width: Optional[int],
    source_height: Optional[int],
    bbox_space: str,
    frame_sha256: str,
    hash_format: str,
) -> dict:
    return {
        "schema": FRAME_REF_SCHEMA,
        "frame_id": f"{camera_id}:{int(frame_sequence)}",
        "camera_id": camera_id,
        "frame_sequence": int(frame_sequence),
        "captured_at": float(captured_at),
        "sample_timestamp": None if sample_timestamp is None else float(sample_timestamp),
        "iso_time": datetime.now(timezone.utc).isoformat(),
        "width": int(width),
        "height": int(height),
        "source_width": None if source_width is None else int(source_width),
        "source_height": None if source_height is None else int(source_height),
        "bbox_space": bbox_space,
        "frame_sha256": frame_sha256,
        "hash_format": hash_format,
    }


def build_crop_ref(
    frame_ref: dict,
    *,
    alert_id: str,
    camera_id: str,
    subject_kind: str,
    track_id: Optional[str],
    track_id_raw: Optional[int],
    face_index: Optional[int],
    bbox_xyxy: Iterable[float],
    bbox_xyxy_source: Iterable[float],
    crop_id: str,
) -> dict:
    ref = {
        "schema": CROP_REF_SCHEMA,
        "crop_id": crop_id,
        "alert_id": alert_id,
        "subject_kind": subject_kind,
        "track_id": track_id,
        "track_id_raw": track_id_raw,
        "face_index": face_index,
        "bbox_xyxy": [float(v) for v in bbox_xyxy],
        "bbox_xyxy_source": [float(v) for v in bbox_xyxy_source],
        "is_derivative": False,
        "derivative_of": None,
    }
    for key in ("frame_id", "camera_id", "frame_sequence", "captured_at",
                "sample_timestamp", "iso_time", "width", "height",
                "source_width", "source_height", "bbox_space",
                "frame_sha256", "hash_format"):
        ref[key] = frame_ref[key]
    return ref


# --------------------------------------------------------------------------
# Face <-> track association with uncertainty (pure; WT-08 §3.2)
# --------------------------------------------------------------------------
UPPER_REGION_FRACTION = 0.45  # face center must sit in the top 45% of the person box
CONTAINMENT_PASS = 0.6       # >=60% of the face box area inside the person box
MOTION_TOLERANCE_FRACTION = 0.2  # face/track center displacement agreement
CO_OCCURRENCE_MIN_FRAMES = 2


class FaceAssocEngine:
    """Heuristic face-to-track association per camera, with explicit ambiguity.

    Rules (WT-08 §3.2): containment, upper-region, temporal co-occurrence;
    >=2 surviving candidates -> ``ambiguous`` with candidate ids and NO silent
    pick; zero candidates -> ``track_id: None``. Emitted track ids are
    namespaced ``<camera_id>::<n>`` so cross-camera association is impossible
    by type. Confidence is a heuristic in [0,1], UNCALIBRATED — never a
    probability (F-40: nothing here is calibrated).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # camera_id -> per-face-tracklet co-occurrence bookkeeping
        self._tracklets: dict[str, dict] = {}
        self._next_tracklet: dict[str, int] = {}
        # camera_id -> raw track id -> last center (for motion consistency)
        self._track_history: dict[str, dict] = {}

    @staticmethod
    def _iou(a: Iterable[float], b: Iterable[float]) -> float:
        ax1, ay1, ax2, ay2 = (float(v) for v in a)
        bx1, by1, bx2, by2 = (float(v) for v in b)
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _center(box: Iterable[float]) -> tuple[float, float]:
        x1, y1, x2, y2 = (float(v) for v in box)
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0

    def _tracklet_for(self, camera_id: str, face_box: Iterable[float]) -> tuple[int, Optional[tuple[float, float]]]:
        """Match a face to the previous frame's face tracklets by IoU.

        Returns the tracklet id and the PREVIOUS center of that tracklet
        (None when the tracklet is new). A lost face that reappears after
        IoU matching fails gets a NEW tracklet — old and new observations are
        never merged into one "person" (WT-08 §3.2 re-entry rule).
        """
        state = self._tracklets.setdefault(camera_id, {})
        best_id, best_iou = None, 0.0
        for tid, tracklet in state.items():
            iou = self._iou(face_box, tracklet["bbox"])
            if iou > best_iou:
                best_id, best_iou = tid, iou
        previous_center = None
        if best_id is None or best_iou < 0.4:
            best_id = self._next_tracklet.get(camera_id, 1)
            self._next_tracklet[camera_id] = best_id + 1
        else:
            previous_center = self._center(state[best_id]["bbox"])
        state[best_id] = {"bbox": list(map(float, face_box)),
                          "cooccur": state.get(best_id, {}).get("cooccur", {})}
        return best_id, previous_center

    def associate_frame(
        self,
        *,
        camera_id: str,
        faces: list[dict],
        tracks: list[dict],
        captured_at: float,
    ) -> list[dict]:
        """Associate one frame's faces with that frame's person tracks.

        ``faces``: dicts with ``bbox_xyxy_source`` (SOURCE pixels) + face_index.
        ``tracks``: dicts with ``bbox`` (SOURCE pixels) + integer ``track_id``
        from the inference observation (already scaled by
        ``_scale_person_tracks``). One camera per call — multi-camera
        NON-association is enforced by construction.
        """
        candidates_out = []
        with self._lock:
            history = self._track_history.setdefault(camera_id, {})
            for face in faces:
                face_box = face.get("bbox_xyxy_source") or face.get("bbox_xyxy")
                if not face_box:
                    continue
                tracklet_id, previous_face_center = self._tracklet_for(camera_id, face_box)
                tracklet = self._tracklets[camera_id][tracklet_id]
                face_center = self._center(face_box)
                scored = []
                for track in tracks:
                    track_box = track.get("bbox")
                    if not track_box:
                        continue
                    raw_id = track.get("track_id")
                    reasons = []
                    # 1) containment: face box inside person box
                    face_area = max(1e-6, (face_box[2] - face_box[0]) * (face_box[3] - face_box[1]))
                    ix1 = max(face_box[0], track_box[0]); iy1 = max(face_box[1], track_box[1])
                    ix2 = min(face_box[2], track_box[2]); iy2 = min(face_box[3], track_box[3])
                    inside = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1) / face_area
                    if inside >= CONTAINMENT_PASS:
                        reasons.append("face_box_contained_in_person_box")
                    # 2) upper region: face center in the top of the person box
                    person_h = max(1e-6, track_box[3] - track_box[1])
                    in_upper = face_center[1] <= track_box[1] + UPPER_REGION_FRACTION * person_h
                    if in_upper:
                        reasons.append("face_in_upper_person_region")
                    # 3) temporal co-occurrence (>=2 frames) + motion consistency:
                    #    the same face-tracklet and the same person track must have
                    #    co-occurred before, and their frame-to-frame displacements
                    #    must agree within tolerance.
                    cooccur = tracklet["cooccur"]
                    count = cooccur.get(raw_id, {}).get("frames", 0) + 1
                    track_center = self._center(track_box)
                    previous_track_center = history.get(raw_id)
                    moved_consistently = True
                    if previous_face_center is not None and previous_track_center is not None:
                        face_disp = (face_center[0] - previous_face_center[0],
                                     face_center[1] - previous_face_center[1])
                        track_disp = (track_center[0] - previous_track_center[0],
                                      track_center[1] - previous_track_center[1])
                        tolerance = MOTION_TOLERANCE_FRACTION * person_h
                        moved_consistently = (
                            abs(face_disp[0] - track_disp[0]) <= tolerance
                            and abs(face_disp[1] - track_disp[1]) <= tolerance
                        )
                    cooccur[raw_id] = {"frames": count}
                    if count >= CO_OCCURRENCE_MIN_FRAMES and moved_consistently:
                        reasons.append("temporal_co_occurrence")
                    if reasons:
                        score = 0.0
                        if "face_box_contained_in_person_box" in reasons:
                            score += 0.25 + 0.25 * min(1.0, inside)
                        if "face_in_upper_person_region" in reasons:
                            score += 0.2
                        if "temporal_co_occurrence" in reasons:
                            score += 0.3
                        scored.append((min(1.0, score), raw_id, reasons))
                namespaced = lambda raw: f"{camera_id}::{raw}"
                if len(scored) == 1:
                    conf, raw_id, reasons = scored[0]
                    candidates_out.append({
                        "track_id": namespaced(raw_id),
                        "track_id_raw": raw_id,
                        "confidence": round(conf, 4),
                        "confidence_semantics": "heuristic_uncalibrated",
                        "ambiguous": False,
                        "reasons": reasons + ["namespaced_per_camera", "proximity_not_causation"],
                        "candidate_track_ids": [namespaced(raw_id)],
                    })
                elif len(scored) > 1:
                    scored.sort(key=lambda item: -item[0])
                    candidates_out.append({
                        "track_id": None,
                        "track_id_raw": None,
                        "confidence": round(scored[0][0], 4),
                        "confidence_semantics": "heuristic_uncalibrated",
                        "ambiguous": True,
                        "reasons": ["multiple_candidate_tracks", "namespaced_per_camera",
                                    "proximity_not_causation"],
                        "candidate_track_ids": [namespaced(raw) for _, raw, _ in scored],
                    })
                else:
                    candidates_out.append({
                        "track_id": None,
                        "track_id_raw": None,
                        "confidence": 0.0,
                        "confidence_semantics": "heuristic_uncalibrated",
                        "ambiguous": False,
                        "reasons": ["no_candidate_track", "namespaced_per_camera",
                                    "proximity_not_causation"],
                        "candidate_track_ids": [],
                    })
            # record this frame's track centers once, for the next frame's
            # motion-consistency check
            for track in tracks:
                if track.get("bbox") and track.get("track_id") is not None:
                    history[track["track_id"]] = self._center(track["bbox"])
        return candidates_out


# --------------------------------------------------------------------------
# Derivative records (WT-23 schema, exact required keys)
# --------------------------------------------------------------------------
# Integration seam: at merge time replace the builder below with
# ``backend.enhance.build_derivative_record`` + ``DerivativeLedger`` (same
# shape, agreed with WT-23 2026-09-29). The local builder exists because
# backend/enhance.py is not in this worktree's baseline.
DERIVATIVE_RECORD_TYPE = "enhancement-derivative"


def build_derivative_record(
    *,
    derivative_id: str,
    alert_id: str,
    parent_path: str,
    parent_sha256: str,
    derivative_path: str,
    derivative_sha256: str,
    operations: list[dict],
    library_versions: dict,
    operator: dict,
    is_enhanced: bool,
    camera_id: Optional[str] = None,
    parent_hash_format: str = "file-bytes",
    parent_hash_basis: str = "file-bytes",
    parent_captured_at: Optional[float] = None,
    parent_sample_timestamp: Optional[float] = None,
    subject_ref: Optional[dict] = None,
    harness: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> dict:
    if not parent_sha256 or parent_sha256 == "N/A":
        raise ValueError("Derivative record requires the parent asset SHA-256 (never 'N/A')")
    label = "ENHANCED DERIVATIVE" if is_enhanced else "CROP DERIVATIVE"
    label_text = ("ENHANCED DERIVATIVE — synthesized detail may be present; not an observation"
                  if is_enhanced else
                  "CROP DERIVATIVE — unmodified pixels from the original")
    record = {
        "recordType": DERIVATIVE_RECORD_TYPE,
        "derivativeId": derivative_id,
        "alertId": alert_id,
        "cameraId": camera_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "producedAt": datetime.now(timezone.utc).isoformat(),
        "parentKind": "frame",
        "parentPath": parent_path,
        "parentSha256": parent_sha256,
        "parentHashFormat": parent_hash_format,
        "parentHashBasis": parent_hash_basis,
        "parentCapturedAt": parent_captured_at,
        "parentSampleTimestamp": parent_sample_timestamp,
        "subjectRef": subject_ref or {},
        "derivativePath": derivative_path,
        "derivativeSha256": derivative_sha256,
        "derivativeFormat": "png",
        "tier": 0,
        "derivationBasis": "deterministic",
        "operations": operations,
        "model": {"name": None, "version": None, "weightsSha256": None, "license": None},
        "libraryVersions": library_versions,
        "operator": operator,
        "isEnhanced": is_enhanced,
        "label": label,
        "labelText": label_text,
        "labelLocations": ["image_metadata", "ledger_record", "ui_contract"],
        "uiContract": {
            "originalFirst": True,
            "originalRequired": True,
            "badge": label,
            "disclaimer": ("enhanced derivative — detail may be reconstructed" if is_enhanced
                           else "crop derivative — unmodified pixels from the original"),
        },
        "harness": harness or {
            "status": "not_measured", "passed": None, "psnrDb": None, "ssim": None,
            "lpips": None, "identitySimilarity": None,
            "utility": {"faceDetectScoreBefore": None, "faceDetectScoreAfter": None,
                        "iedBeforePx": None, "iedAfterPx": None},
            "failedBounds": [],
        },
    }
    if extra:
        record.update(extra)
    return record


class FaceDerivativeLedger:
    """Append-only, hash-chained derivative records on the SC-8 ledger file.

    Chain format matches ``EvidenceLedger`` exactly (prevHash/currentHash over
    the sorted-key JSON body minus currentHash; shared per-path RLock; fsync).
    Multiple records per alertId are expected and allowed; dedupe is on
    ``derivativeId`` (idempotent replay), never on alertId. A derivative is
    refused when no alert receipt exists yet for that alertId — derivatives
    always sit AFTER the receipt in the chain (WT-23 ordering guard).
    """

    _path_locks: dict[str, threading.RLock] = {}
    _path_locks_guard = threading.Lock()

    def __init__(self, path: Path):
        self.path = Path(path)
        key = os.path.normcase(str(self.path.resolve()))
        with self._path_locks_guard:
            self._lock = self._path_locks.setdefault(key, threading.RLock())
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _read_chain(self) -> list[dict]:
        if not self.path.exists():
            return []
        records = []
        previous_hash = "GENESIS"
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            record = json.loads(line)
            if not isinstance(record, dict) or not record.get("alertId"):
                raise ValueError(f"Invalid ledger record at line {line_number}")
            body = {k: v for k, v in record.items() if k != "currentHash"}
            expected = self._sha256_text(json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False))
            if record.get("prevHash") != previous_hash or record.get("currentHash") != expected:
                raise ValueError(f"Broken ledger hash chain at line {line_number}")
            records.append(record)
            previous_hash = record["currentHash"]
        return records

    def append_derivative(self, record: dict) -> dict:
        with self._lock:
            records = self._read_chain()
            derivative_id = record.get("derivativeId")
            existing = next((r for r in records if r.get("derivativeId") == derivative_id), None)
            if existing is not None:
                return existing
            alert_id = record.get("alertId")
            has_receipt = any(
                r.get("alertId") == alert_id and r.get("recordType") in (None, "alert-receipt")
                for r in records
            )
            if not has_receipt:
                raise ValueError(
                    "Refusing derivative record before its alert receipt (ordering guard)"
                )
            payload = dict(record)
            payload["prevHash"] = records[-1]["currentHash"] if records else "GENESIS"
            payload["currentHash"] = self._sha256_text(
                json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False))
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
            with self.path.open("ab+") as fh:
                fh.seek(0, os.SEEK_END)
                prefix = b""
                if fh.tell():
                    fh.seek(-1, os.SEEK_END)
                    if fh.read(1) != b"\n":
                        prefix = b"\n"
                fh.write(prefix + serialized.encode("utf-8"))
                fh.flush()
                os.fsync(fh.fileno())
            return payload


# --------------------------------------------------------------------------
# Frame entry adapter (baseline tuples, WT-14/WT-22 record shapes)
# --------------------------------------------------------------------------
def _entry_to_sample(entry, fallback_index: int) -> tuple[int, float, Optional[float], np.ndarray]:
    """Return (sequence, captured_at, sample_timestamp, frame) for one entry."""
    if isinstance(entry, tuple) and len(entry) == 2 and isinstance(entry[1], np.ndarray):
        captured_at, frame = entry
        return fallback_index, float(captured_at), None, frame
    if isinstance(entry, dict):
        frame = entry.get("frame")
        captured_at = entry.get("captured_at", 0.0)
        sequence = entry.get("sequence", fallback_index)
        sample = entry.get("sample_timestamp")
        if isinstance(frame, np.ndarray):
            return int(sequence), float(captured_at), sample, frame
    frame = getattr(entry, "frame", None)
    if isinstance(frame, np.ndarray):
        captured_at = float(getattr(entry, "captured_at", 0.0))
        sequence = int(getattr(entry, "sequence", fallback_index))
        sample = getattr(entry, "sample_timestamp", None)
        return sequence, captured_at, sample, frame
    raise TypeError(f"Unsupported frame entry type: {type(entry)!r}")


# --------------------------------------------------------------------------
# Incident face capture service (bounded async work, zero face work on the
# alert dispatch path)
# --------------------------------------------------------------------------
class FaceCaptureService:
    """Consumes evidence pre/post frames; runs detection OFF the alert path.

    Threading contract (tested in ``tests/test_face_capture.py``):
    ``note_incident_blocking`` and ``start_capture`` are O(1) bounded-queue
    enqueues. They never call cv2/numpy, never touch the detector, and never
    write files — the single worker thread does all face work. Job queue is
    bounded with drop-oldest so a stalled camera cannot grow memory.
    """

    def __init__(
        self,
        detector,
        faces_root: Path,
        ledger: Optional[FaceDerivativeLedger] = None,
        best_frame_provider=None,
        sample_every: int = 3,
        post_window_sec: float = 5.0,
        max_crops_per_incident: int = 8,
        min_face_size_px: float = 36.0,
        min_ied_px: float = 12.0,
        assoc: Optional[FaceAssocEngine] = None,
        on_result: Optional[Callable[[str, dict], None]] = None,
        max_queue: int = 8,
    ):
        self.detector = detector
        self.faces_root = Path(faces_root)
        self.ledger = ledger
        self.best_frame_provider = best_frame_provider
        self.sample_every = max(1, int(sample_every))
        self.post_window_sec = float(post_window_sec)
        self.max_crops_per_incident = max(1, int(max_crops_per_incident))
        self.min_face_size_px = float(min_face_size_px)
        self.min_ied_px = float(min_ied_px)
        self.assoc = assoc or FaceAssocEngine()
        self.on_result = on_result
        self._results: dict[str, dict] = {}
        self._results_lock = threading.Lock()
        self._incidents: dict[str, dict] = {}
        self._jobs: queue.Queue = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, name="face-capture", daemon=True)
        self._worker.start()
        self._processed = 0
        self._dropped_jobs = 0

    # -- dispatch-path API (O(1), zero face work) --------------------------
    def note_incident_blocking(self, alert_id: str, camera_id: str) -> None:
        """Dispatch-path marker only: bounded enqueue, no cv2/numpy/IO."""
        if not alert_id:
            return
        try:
            self._jobs.put_nowait(("note", alert_id, camera_id, None))
        except queue.Full:
            self._drop_oldest_then_put(("note", alert_id, camera_id, None))

    def start_capture(self, alert_id: str, camera_id: str,
                      pre_entries: list, post_source, track_provider=None,
                      source_size: Optional[tuple[int, int]] = None,
                      on_post_done: Optional[Callable[[], None]] = None) -> None:
        """Enqueue an incident capture job. O(1); frames are consumed later by
        the worker thread (pre list is referenced, never copied).

        ``on_post_done`` runs after the worker finishes consuming ``post_source``
        so callers can deregister their fan-out queue (bounded memory).
        """
        if not alert_id:
            return
        with self._results_lock:
            # pending state is visible immediately; the worker replaces it
            self._incidents[alert_id] = {"camera_id": camera_id,
                                         "noted_at": time.monotonic()}
            if alert_id not in self._results:
                self._results[alert_id] = {
                    "alert_id": alert_id, "camera_id": camera_id,
                    "status": "pending", "reasons": ["capture_queued"],
                    "face_assoc": [],
                }
        job = ("capture", alert_id, camera_id,
               {"pre": list(pre_entries), "post": post_source,
                "track_provider": track_provider, "source_size": source_size,
                "on_post_done": on_post_done})
        try:
            self._jobs.put_nowait(job)
        except queue.Full:
            self._drop_oldest_then_put(job)

    def _drop_oldest_then_put(self, job) -> None:
        try:
            self._jobs.get_nowait()
            self._dropped_jobs += 1
        except queue.Empty:
            pass
        try:
            self._jobs.put_nowait(job)
        except queue.Full:
            self._dropped_jobs += 1

    # -- query API ---------------------------------------------------------
    def get_result(self, alert_id: str) -> dict:
        with self._results_lock:
            stored = self._results.get(alert_id)
            if stored is not None:
                return dict(stored)
            noted = alert_id in self._incidents
        if noted:
            return {"alert_id": alert_id, "status": "pending",
                    "reasons": ["capture_queued"], "face_assoc": []}
        return {"alert_id": alert_id, "status": "absent",
                "reasons": ["no_face_capture_record_for_alert"], "face_assoc": []}

    def health(self) -> dict:
        detector_health = (self.detector.health() if hasattr(self.detector, "health")
                           else {"status": "unknown"})
        return {
            "detector": detector_health,
            "queue_depth": self._jobs.qsize(),
            "processed_jobs": self._processed,
            "dropped_jobs": self._dropped_jobs,
            "worker_alive": self._worker.is_alive(),
        }

    def shutdown(self, wait: bool = True) -> None:
        self._stop.set()
        try:
            self._jobs.put_nowait(("stop", None, None, None))
        except queue.Full:
            pass
        if wait:
            self._worker.join(timeout=10.0)

    # -- worker ------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                kind, alert_id, camera_id, payload = self._jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            if kind == "stop":
                return
            try:
                if kind == "note":
                    with self._results_lock:
                        self._incidents[alert_id] = {"camera_id": camera_id,
                                                     "noted_at": time.monotonic()}
                        if alert_id not in self._results:
                            self._results[alert_id] = {
                                "alert_id": alert_id, "camera_id": camera_id,
                                "status": "pending", "reasons": ["capture_queued"],
                                "face_assoc": [],
                            }
                elif kind == "capture":
                    try:
                        self._process_capture(alert_id, camera_id, payload)
                    finally:
                        done = payload.get("on_post_done")
                        if done is not None:
                            try:
                                done()
                            except Exception:
                                logger.warning("[FaceCaptureService] on_post_done failed", exc_info=False)
                    self._processed += 1
            except Exception:
                logger.exception("[FaceCaptureService] job failed for %s", alert_id)
                self._store_result(alert_id, {
                    "alert_id": alert_id, "camera_id": camera_id,
                    "status": "failed", "reasons": ["capture_job_error"],
                    "face_assoc": [], "face_assoc_meta": dict(FACE_ASSOC_META),
                })

    def _store_result(self, alert_id: str, result: dict) -> None:
        with self._results_lock:
            self._results[alert_id] = result
        if self.on_result is not None:
            try:
                self.on_result(alert_id, result)
            except Exception:
                logger.exception("[FaceCaptureService] on_result callback failed")

    def _iter_samples(self, payload: dict):
        """Yield (sequence, captured_at, sample_timestamp, frame) sampled every
        Nth entry over pre + post within the bounded post window."""
        index = 0
        for entry in payload["pre"]:
            if index % self.sample_every == 0:
                yield _entry_to_sample(entry, index)
            index += 1
        post = payload.get("post")
        if post is None:
            return
        trigger = time.monotonic()
        deadline = trigger + self.post_window_sec
        while time.monotonic() <= deadline and not self._stop.is_set():
            try:
                entry = post.get(timeout=0.5)
            except queue.Empty:
                break
            if entry is None:
                break
            if index % self.sample_every == 0:
                yield _entry_to_sample(entry, index)
            index += 1

    def _process_capture(self, alert_id: str, camera_id: str, payload: dict) -> None:
        detector_health = (self.detector.health() if hasattr(self.detector, "health")
                           else {"status": "unknown"})
        if detector_health.get("status") != "loaded":
            self._store_result(alert_id, {
                "alert_id": alert_id, "camera_id": camera_id,
                "status": "failed" if detector_health.get("status") == "failed" else "absent",
                "reasons": [f"face_detector_{detector_health.get('status', 'unknown')}",
                            str(detector_health.get("reason", ""))],
                "face_assoc": [], "face_assoc_meta": dict(FACE_ASSOC_META),
                "detector_health": detector_health,
            })
            return

        frames_sampled = 0
        frames_with_faces = 0
        faces_detected = 0
        faces_suppressed = 0
        crops = []
        face_assoc = []
        source_size = payload.get("source_size")

        for sequence, captured_at, sample_timestamp, frame in self._iter_samples(payload):
            frames_sampled += 1
            frame_h, frame_w = frame.shape[:2]
            effective_source = source_size or (frame_w, frame_h)
            bbox_space = "source" if effective_source == (frame_w, frame_h) else "model_input"
            try:
                detections = self.detector.detect(frame)
            except Exception as exc:
                logger.warning("[FaceCaptureService] detection error: %s", exc)
                continue
            if not detections:
                continue
            frames_with_faces += 1
            faces_detected += len(detections)
            gated = reporting_gate(detections, self.min_face_size_px, self.min_ied_px)
            reportable = [d for d, g in zip(detections, gated) if g["reportable"]]
            faces_suppressed += len(detections) - len(reportable)
            if not reportable or len(crops) >= self.max_crops_per_incident:
                continue

            tracks = []
            track_provider = payload.get("track_provider")
            if track_provider is not None:
                try:
                    tracks = track_provider() or []
                except Exception:
                    tracks = []

            assoc_inputs = []
            for detection in reportable:
                if len(crops) >= self.max_crops_per_incident:
                    break
                frame_box = list(detection.bbox_xyxy)
                source_box = (scale_box_to_source(frame_box, (frame_w, frame_h), effective_source)
                              if bbox_space != "source" else list(frame_box))
                crop_id = f"{camera_id}:{sequence}:face:{detection.face_index}"
                assoc_inputs.append({
                    "bbox_xyxy": frame_box,
                    "bbox_xyxy_source": source_box,
                    "face_index": detection.face_index,
                    "crop_id": crop_id,
                    "detection": detection,
                })

            assoc_results = self.assoc.associate_frame(
                camera_id=camera_id,
                faces=assoc_inputs,
                tracks=tracks,
                captured_at=captured_at,
            )

            # Persist crop + source frame (PNG, hashed bytes = stored bytes).
            frame_png = None
            frame_sha = None
            for item, assoc_entry in zip(assoc_inputs, assoc_results):
                if len(crops) >= self.max_crops_per_incident:
                    break
                if frame_png is None:
                    ok, encoded = cv2.imencode(".png", frame)
                    if not ok:
                        break
                    frame_png = encoded.tobytes()
                    frame_sha = hashlib.sha256(frame_png).hexdigest()
                detection = item["detection"]
                x1, y1, x2, y2 = (int(round(v)) for v in item["bbox_xyxy"])
                margin_x = int(0.2 * (x2 - x1)); margin_y = int(0.2 * (y2 - y1))
                cx1 = max(0, x1 - margin_x); cy1 = max(0, y1 - margin_y)
                cx2 = min(frame_w, x2 + margin_x); cy2 = min(frame_h, y2 + margin_y)
                crop = frame[cy1:cy2, cx1:cx2]
                if crop.size == 0:
                    continue
                safe_name = item["crop_id"].replace(":", "_")
                incident_dir = self.faces_root / f"{alert_id}_faces"
                incident_dir.mkdir(parents=True, exist_ok=True)
                frame_path = incident_dir / f"{safe_name}.frame.png"
                crop_path = incident_dir / f"{safe_name}.face.png"
                frame_path.write_bytes(frame_png)
                ok, crop_encoded = cv2.imencode(".png", crop)
                if not ok:
                    continue
                crop_bytes = crop_encoded.tobytes()
                crop_path.write_bytes(crop_bytes)
                crop_sha = hashlib.sha256(crop_bytes).hexdigest()

                frame_ref = build_frame_ref(
                    camera_id=camera_id, frame_sequence=sequence,
                    captured_at=captured_at, sample_timestamp=sample_timestamp,
                    width=frame_w, height=frame_h,
                    source_width=effective_source[0], source_height=effective_source[1],
                    bbox_space=bbox_space, frame_sha256=frame_sha, hash_format="png",
                )
                crop_ref = build_crop_ref(
                    frame_ref, alert_id=alert_id, camera_id=camera_id,
                    subject_kind="face",
                    track_id=assoc_entry.get("track_id"),
                    track_id_raw=assoc_entry.get("track_id_raw"),
                    face_index=detection.face_index,
                    bbox_xyxy=item["bbox_xyxy"], bbox_xyxy_source=item["bbox_xyxy_source"],
                    crop_id=item["crop_id"],
                )
                derivative_id = f"deriv-{alert_id}-{len(crops):03d}"
                record = build_derivative_record(
                    derivative_id=derivative_id, alert_id=alert_id, camera_id=camera_id,
                    parent_path=str(frame_path.relative_to(self.faces_root.parent))
                    if self.faces_root.parent in frame_path.parents else str(frame_path),
                    parent_sha256=frame_sha,
                    parent_captured_at=captured_at,
                    parent_sample_timestamp=sample_timestamp,
                    subject_ref={
                        "kind": "face",
                        "cropId": item["crop_id"],
                        "faceIndex": detection.face_index,
                        "trackId": assoc_entry.get("track_id"),
                        "trackIdRaw": assoc_entry.get("track_id_raw"),
                        "bboxXyxy": [int(round(v)) for v in item["bbox_xyxy"]],
                        "bboxXyxySource": [round(v, 2) for v in item["bbox_xyxy_source"]],
                        "bboxSpace": bbox_space,
                        "frameSequence": sequence,
                        "frameId": frame_ref["frame_id"],
                        "isoTime": frame_ref["iso_time"],
                        "isDerivative": False,
                        "derivativeOf": None,
                        "hashFormat": "png",
                    },
                    derivative_path=str(crop_path),
                    derivative_sha256=crop_sha,
                    operations=[{"name": "crop",
                                 "params": {"bboxXyxy": [int(round(v)) for v in item["bbox_xyxy"]],
                                            "marginFraction": 0.2}}],
                    library_versions={
                        "python": os.sys.version.split()[0],
                        "opencv": cv2.__version__,
                        "numpy": np.__version__,
                    },
                    operator={"id": "system:backend.face_capture", "kind": "system",
                              "module": "backend.face_capture", "moduleVersion": "1.0.0"},
                    is_enhanced=False,
                    extra={"faceAssoc": {k: assoc_entry[k] for k in
                                         ("track_id", "confidence", "ambiguous", "reasons")}},
                )
                ledger_error = None
                if self.ledger is not None:
                    try:
                        self.ledger.append_derivative(record)
                    except Exception as exc:
                        # Ordering guard etc.: keep the crop, surface the gap.
                        ledger_error = f"{type(exc).__name__}: {exc}"
                        logger.warning("[FaceCaptureService] derivative append failed: %s", ledger_error)
                crops.append({
                    "crop_id": item["crop_id"],
                    "crop_path": str(crop_path),
                    "frame_path": str(frame_path),
                    "crop_sha256": crop_sha,
                    "frame_sha256": frame_sha,
                    "derivative_id": derivative_id,
                    "derivative_record_error": ledger_error,
                    "crop_ref": crop_ref,
                })
                face_assoc.append({
                    "crop_ref": crop_ref,
                    "track_id": assoc_entry.get("track_id"),
                    "confidence": assoc_entry.get("confidence"),
                    "confidence_semantics": "heuristic_uncalibrated_not_a_probability",
                    "ambiguous": assoc_entry.get("ambiguous"),
                    "reasons": assoc_entry.get("reasons"),
                    "candidate_track_ids": assoc_entry.get("candidate_track_ids"),
                })

        # Best-frame reference from WT-22's provider when configured.
        best_frame = {"status": "unavailable",
                      "reason": "best_frame_provider_not_configured"}
        if self.best_frame_provider is not None:
            try:
                best_frame = {"status": "available",
                              "ref": self.best_frame_provider(alert_id, camera_id)}
            except Exception as exc:
                best_frame = {"status": "unavailable",
                              "reason": f"best_frame_provider_error:{type(exc).__name__}"}

        if crops:
            status, reasons = "captured", []
        elif faces_detected and faces_suppressed == faces_detected:
            status = "absent"
            reasons = ["no_reportable_face", "all_faces_below_reporting_gate",
                       f"faces_detected:{faces_detected}",
                       f"faces_suppressed:{faces_suppressed}"]
        elif faces_detected:
            status = "absent"
            reasons = [f"faces_detected:{faces_detected}", "crop_budget_exhausted_or_persist_failed"]
        elif frames_sampled == 0:
            status = "absent"
            reasons = ["no_frames_in_window"]
        else:
            status = "absent"
            reasons = ["no_face_detected_in_window"]

        self._store_result(alert_id, {
            "alert_id": alert_id, "camera_id": camera_id,
            "status": status, "reasons": reasons,
            "face_assoc": face_assoc,
            "face_assoc_meta": dict(FACE_ASSOC_META),
            "crops": crops,
            "frames_sampled": frames_sampled,
            "frames_with_faces": frames_with_faces,
            "faces_detected": faces_detected,
            "faces_suppressed_reporting_gate": faces_suppressed,
            "detector_health": self.detector.health() if hasattr(self.detector, "health") else {},
            "best_frame": best_frame,
            "capture_window": {
                "pre_frames": len(payload["pre"]),
                "post_window_sec": self.post_window_sec,
                "sample_every": self.sample_every,
            },
            "association_semantics": {
                "note": "association is heuristic and uncalibrated; box proximity "
                        "never implies causation or perpetrator role; no identity "
                        "recognition is performed",
            },
        })


# --------------------------------------------------------------------------
# Module-level default service (used by the api.py on_threat hook)
# --------------------------------------------------------------------------
_default_service: Optional[FaceCaptureService] = None


def configure_service(service: Optional[FaceCaptureService]) -> None:
    global _default_service
    _default_service = service


def note_incident_blocking(alert_id: str, camera_id: str) -> None:
    """O(1) dispatch-path hook. Zero face work; never raises."""
    service = _default_service
    if service is None:
        return
    try:
        service.note_incident_blocking(alert_id, camera_id)
    except Exception:
        logger.warning("[face_capture] note_incident hook failed", exc_info=False)
