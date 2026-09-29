"""YuNet face detection for incident face capture (detection only, never identity).

Scope boundary (campaign binding): face work = DETECTION + ASSOCIATION WITH
UNCERTAINTY + CLEAR CAPTURE ONLY. Nothing in this module identifies people.
``backend/face_intel.py`` is an identity-recognition engine and MUST stay
unwired; no code here imports it.

Model: OpenCV Zoo ``face_detection_yunet_2023mar.onnx`` (MIT, author Shiqi Yu;
LICENSE file recorded next to the weights in ``assets/yunet/LICENSE``). Fixed
network input 1x3x640x640, 5-point landmarks. ``cv2.FaceDetectorYN`` accepts
frames of any size via ``setInputSize``: it rescales internally and maps
detections back into the *detector input* (i.e. the frame we passed) pixel
space. We therefore run detection at the full decoded frame resolution —
WT-08 measured that letterboxing 1080p down to 640x640 loses small CCTV faces.

Coordinate contract (SC mapping — tested in ``tests/test_face_detect.py``):

    model input (1x3x640x640, internal)
      -> detector input space (= the pixels of the frame passed to detect())
      -> ORIGINAL SOURCE pixels (uniform-ratio mapping, same contract as
         ``inference_process._scale_person_tracks``: bbox * source/frame;
         valid for uniform resize only — never for crop/letterbox chains)

Every box/landmark returned by :meth:`YuNetFaceDetector.detect` is already in
the pixel space of the frame that was passed in. Callers that hold frames
downscaled from the original source MUST map to source pixels with
:func:`face_capture.scale_box_to_source` before cropping or associating, and
must record which space a box lives in (``bbox_space``) in its references.

Reporting gate policy (WT-08): min face size is a REPORTING gate (IED px /
face box px), never a detection gate. ``detect()`` returns every face the
model fires on; :func:`reporting_gate` marks each face reportable or not with
explicit reasons.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

MODEL_FILENAME = "face_detection_yunet_2023mar.onnx"
# sha256 of the OpenCV Zoo 2023mar artifact downloaded for this workstream
# (verified against the WT-08 research reference 8f2383e4...52fa4).
EXPECTED_MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_model_path(explicit: str | os.PathLike | None = None) -> Optional[Path]:
    """Search order: explicit arg, FACE_YUNET_MODEL env, models/ dir, assets/."""
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None
    env = os.getenv("FACE_YUNET_MODEL", "").strip()
    if env and Path(env).exists():
        return Path(env)
    backend_dir = Path(__file__).resolve().parent
    candidates = [
        backend_dir / "models" / MODEL_FILENAME,
        backend_dir.parent / "assets" / "yunet" / MODEL_FILENAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@dataclass(frozen=True)
class FaceDetection:
    """One detected face, all geometry in the detector-input (frame) pixel space."""
    bbox_xyxy: tuple[float, float, float, float]
    score: float
    landmarks_5pt: tuple[tuple[float, float], ...]  # right eye, left eye, nose, right mouth, left mouth
    ied_px: float
    yaw_proxy_deg: float
    face_index: int

    def to_dict(self) -> dict:
        return {
            "bbox_xyxy": list(self.bbox_xyxy),
            "score": round(float(self.score), 4),
            "landmarks_5pt": [list(p) for p in self.landmarks_5pt],
            "ied_px": round(float(self.ied_px), 2),
            "yaw_proxy_deg": round(float(self.yaw_proxy_deg), 1),
            "face_index": int(self.face_index),
        }


def _landmark_metrics(landmarks: np.ndarray) -> tuple[float, float]:
    """IED (inter-eye distance, px) and a landmark-based yaw proxy in degrees.

    Yaw proxy: horizontal offset of the nose tip from the eye midpoint,
    normalized by IED -> sin(yaw) approximation. This is a geometric PROXY
    (WT-08 §4), not a calibrated pose estimate.
    """
    right_eye, left_eye, nose = landmarks[0], landmarks[1], landmarks[2]
    eye_mid = (right_eye + left_eye) / 2.0
    ied = float(np.linalg.norm(left_eye - right_eye))
    if ied <= 1e-6:
        return 0.0, 0.0
    offset = float(nose[0] - eye_mid[0]) / ied
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, offset))))
    return ied, yaw


class YuNetFaceDetector:
    """Lazy-loading YuNet wrapper with an explicit, never-silent health surface.

    Health statuses: ``loaded`` (weights on disk and session created),
    ``absent`` (no weights file found), ``failed`` (weights found but load or
    first inference failed), ``disabled`` (constructed with enabled=False).
    """

    def __init__(
        self,
        model_path: str | os.PathLike | None = None,
        score_threshold: float = 0.6,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
        enabled: bool = True,
    ):
        self._explicit_path = model_path
        self.score_threshold = float(score_threshold)
        self.nms_threshold = float(nms_threshold)
        self.top_k = int(top_k)
        self._enabled = bool(enabled)
        self._detector = None
        self._load_error: Optional[str] = None
        self._model_path: Optional[Path] = None
        self._model_sha256: Optional[str] = None
        self._input_size: tuple[int, int] = (0, 0)
        self._failed_after_load = False

    # -- health ------------------------------------------------------------
    def health(self) -> dict:
        if not self._enabled:
            return {"status": "disabled", "reason": "disabled by configuration",
                    "model_path": None, "model_sha256": None, "input_size": None}
        if self._detector is not None and not self._failed_after_load:
            return {"status": "loaded", "reason": "",
                    "model_path": str(self._model_path), "model_sha256": self._model_sha256,
                    "input_size": list(self._input_size)}
        if self._load_error:
            status = "failed" if self._model_path else "absent"
            return {"status": status, "reason": self._load_error,
                    "model_path": str(self._model_path) if self._model_path else None,
                    "model_sha256": self._model_sha256, "input_size": None}
        # Not attempted yet: report absent/loaded based on weights presence
        # without creating the session, so health checks stay cheap.
        path = resolve_model_path(self._explicit_path)
        if path is None:
            return {"status": "absent", "reason": f"{MODEL_FILENAME} not found in models/ or assets/yunet/",
                    "model_path": None, "model_sha256": None, "input_size": None}
        return {"status": "absent", "reason": "weights present but detector not loaded yet (lazy)",
                "model_path": str(path), "model_sha256": None, "input_size": None}

    @property
    def enabled(self) -> bool:
        return self._enabled

    # -- loading -----------------------------------------------------------
    def _load(self) -> bool:
        if self._detector is not None:
            return not self._failed_after_load
        if self._load_error:
            return False
        path = resolve_model_path(self._explicit_path)
        if path is None:
            self._load_error = f"{MODEL_FILENAME} not found in models/ or assets/yunet/"
            logger.warning("[YuNetFaceDetector] %s", self._load_error)
            return False
        self._model_path = path
        try:
            self._model_sha256 = sha256_file(path)
            self._detector = cv2.FaceDetectorYN.create(
                str(path), "", (640, 640),
                score_threshold=self.score_threshold,
                nms_threshold=self.nms_threshold,
                top_k=self.top_k,
            )
            logger.info("[YuNetFaceDetector] loaded %s sha256=%s", path, self._model_sha256)
            return True
        except Exception as exc:
            self._detector = None
            self._load_error = f"{type(exc).__name__}: {exc}"
            logger.warning("[YuNetFaceDetector] load failed: %s", self._load_error)
            return False

    # -- detection ---------------------------------------------------------
    def detect(self, frame: np.ndarray) -> list[FaceDetection]:
        """Detect faces at the frame's native resolution.

        Never raises on inference problems: on failure the health surface
        flips to ``failed`` and an empty list is returned so callers surface
        an explicit absent/failed state instead of a silent zero.
        """
        if not self._enabled:
            return []
        if frame is None or getattr(frame, "ndim", 0) != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) <= 0:
            return []
        if not self._load():
            return []
        height, width = frame.shape[:2]
        try:
            self._detector.setInputSize((width, height))
            _, faces = self._detector.detect(frame)
        except Exception as exc:
            self._failed_after_load = True
            self._load_error = f"inference-error: {type(exc).__name__}: {exc}"
            logger.warning("[YuNetFaceDetector] inference failed: %s", self._load_error)
            return []
        if faces is None:
            return []
        results: list[FaceDetection] = []
        for index, row in enumerate(np.asarray(faces)):
            x, y, w, h = (float(v) for v in row[:4])
            score = float(row[14]) if row.shape[0] > 14 else float(row[-1])
            landmarks = np.asarray(row[4:14], dtype=np.float64).reshape(5, 2)
            ied, yaw = _landmark_metrics(landmarks)
            results.append(FaceDetection(
                bbox_xyxy=(x, y, x + w, y + h),
                score=score,
                landmarks_5pt=tuple((float(px), float(py)) for px, py in landmarks),
                ied_px=ied,
                yaw_proxy_deg=yaw,
                face_index=index,
            ))
        return results


def reporting_gate(
    faces: list[FaceDetection],
    min_face_size_px: float = 36.0,
    min_ied_px: float = 12.0,
) -> list[dict]:
    """REPORTING gate (WT-08): decides what is captured/reported, not detected.

    Returns per-face dicts with ``reportable`` plus explicit
    ``unreportable_reasons``. Small or degenerate faces stay visible in the
    counts — they are suppressed from capture, never hidden.
    """
    gated = []
    for face in faces:
        x1, y1, x2, y2 = face.bbox_xyxy
        box_size = min(x2 - x1, y2 - y1)
        reasons = []
        if box_size < min_face_size_px:
            reasons.append(f"face_box_too_small:{box_size:.1f}px<{min_face_size_px:g}px")
        if face.ied_px < min_ied_px:
            reasons.append(f"ied_too_small:{face.ied_px:.1f}px<{min_ied_px:g}px")
        entry = face.to_dict()
        entry["reportable"] = not reasons
        entry["unreportable_reasons"] = reasons
        gated.append(entry)
    return gated
