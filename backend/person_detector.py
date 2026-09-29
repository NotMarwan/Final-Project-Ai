from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from counting import CountingSemantics
from tracking import create_tracker
from yolo_onnx import (decode_detections, model_input_size, model_names,
                       model_output_format, prepare_input, session_options)

logger = logging.getLogger(__name__)

_PERSON_OVERLAY_ENABLED = os.getenv("PERSON_OVERLAY_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
_PERSON_TRACKER = os.getenv("PERSON_TRACKER", "bytetrack").strip().lower() or "bytetrack"


class PersonDetector:
    """Person detection with geometry-only tracking (ByteTrack by default).

    Detection: ``backend/models/person_yolo.onnx`` (ONNX, measured path) or
    ``yolov8n.pt`` (fallback). Tracking: ``backend/tracking.py`` — ByteTrack
    (MIT, arXiv:2110.06864) by default, OC-SORT selectable via
    ``PERSON_TRACKER=ocsort``. No ReID / appearance features are used anywhere;
    association is box geometry only.

    Counting semantics (canonical, see ``backend/counting.py``):
    ``visible_person_count`` = detections in the current processed frame,
    ``active_track_count`` = confirmed tracks in the current processed frame,
    ``unique_person_estimate_window`` = distinct track identities in a trailing
    window with an explicit ± suspicion band.

    Track-failure taxonomy (heuristic, never silently absorbed) is exposed via
    ``latest_counting_stats()['track_failure_flags']`` and per-track state.
    """

    def __init__(
        self,
        conf_threshold: float = 0.45,
        infer_every_n: int = 2,
        device: str = "cpu",
        min_track_frames: int = 3,
        tracker_config: str = "bytetrack.yaml",
        tracker: str = _PERSON_TRACKER,
        camera_id: str = "",
        counting_window_seconds: float = 60.0,
        tracker_params: Optional[dict[str, Any]] = None,
    ):
        self.conf_threshold = conf_threshold
        self.infer_every_n = infer_every_n
        self.device = device
        self.min_track_frames = min_track_frames
        self.tracker_config = tracker_config
        self.camera_id = str(camera_id or "")
        self._model: Optional[object] = None
        self._frame_counter = 0
        self._enabled = _PERSON_OVERLAY_ENABLED
        self._load_error: Optional[str] = None
        self._use_onnx: bool = False
        self._onnx_session = None
        self._onnx_input: str = ""
        self._onnx_size = (640, 640)
        self._onnx_num_classes = 80
        self._onnx_output_format = "raw"

        # The tracker thresholds are derived from the detector confidence so a
        # detection that passed the detector gate can always start/continue a
        # track — otherwise people detected between the two thresholds would be
        # counted as visible but never tracked (a silent recall loss).
        params: dict[str, Any] = dict(tracker_params or {})
        params.setdefault("track_thresh", float(conf_threshold))
        params.setdefault("new_track_thresh", float(conf_threshold))
        params.setdefault("low_thresh", max(0.05, float(conf_threshold) * 0.5))
        self.tracker = create_tracker(tracker, **params)
        self.counting = CountingSemantics(window_seconds=counting_window_seconds)
        self._visible_person_count: int = 0
        self._last_counting_stats: dict[str, Any] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    # -- bring-up ---------------------------------------------------------
    def _load_model(self) -> bool:
        if self._model is not None or self._onnx_session is not None:
            return True
        if self._load_error:
            return False

        # Try ONNX first
        onnx_path = Path(__file__).parent / "models" / "person_yolo.onnx"
        if onnx_path.exists():
            try:
                import onnxruntime as ort
                from device_utils import get_onnx_providers
                self._onnx_session = ort.InferenceSession(
                    str(onnx_path), sess_options=session_options(ort), providers=get_onnx_providers()
                )
                input_info = self._onnx_session.get_inputs()[0]
                self._onnx_input = input_info.name
                self._onnx_size = model_input_size(input_info.shape)
                metadata = self._onnx_session.get_modelmeta().custom_metadata_map
                names = model_names(metadata)
                if names.get(0) != "person":
                    raise ValueError("Person model must declare class zero as person")
                self._onnx_num_classes = len(names)
                self._onnx_output_format = model_output_format(metadata)
                self._use_onnx = True
                logger.info("[PersonDetector] ONNX model loaded from %s", onnx_path)
                return True
            except Exception as exc:
                self._onnx_session = None
                logger.warning("[PersonDetector] ONNX load failed: %s, falling back to YOLO", exc)

        # Fallback to YOLO
        try:
            from ultralytics import YOLO
            self._model = YOLO("yolov8n.pt")
            if hasattr(self._model, "to"):
                self._model.to(self.device)
            self._use_onnx = False
            logger.info("[PersonDetector] yolov8n.pt loaded on %s", self.device)
            return True
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("[PersonDetector] Failed to load yolov8n.pt: %s. Person overlay disabled.", exc)
            self._enabled = False
            return False

    # -- public API -------------------------------------------------------
    def detect(self, frame: np.ndarray, timestamp: Optional[float] = None) -> list[dict]:
        """Detect and track persons in ``frame``. Returns confirmed track dicts.

        ``timestamp`` is the monotonic capture time used by the counting window;
        it defaults to ``time.monotonic()`` so existing callers are unaffected.
        """
        if not self._enabled:
            return []
        self._frame_counter += 1
        if self._frame_counter % self.infer_every_n != 0:
            return self._get_active_tracks()

        if not self._load_model():
            return []

        try:
            detections = self._detect_onnx(frame) if self._use_onnx else self._detect_yolo(frame)
        except Exception as exc:
            logger.warning("[PersonDetector] Inference error: %s", exc)
            return self._get_active_tracks()

        self._update_tracks(detections, timestamp if timestamp is not None else time.monotonic())
        return self._get_active_tracks()

    def latest_counting_stats(self) -> dict[str, Any]:
        """Counting/telemetry block for the inference result dict (SC-2 additive).

        Only keys with measured values are present: before the first tracker
        update this returns ``{"person_tracker": <name>}`` and the caller omits
        the rest rather than inventing zeros.
        """
        stats: dict[str, Any] = {"person_tracker": self.tracker.name}
        stats.update(self._last_counting_stats)
        return stats

    def get_person_count(self) -> int:
        """Confirmed tracked persons in the last processed frame."""
        return len(self._get_active_tracks())

    @property
    def visible_person_count(self) -> int:
        return self._visible_person_count

    # -- detection backends (detections only; tracking is shared) ---------
    def _detect_onnx(self, frame: np.ndarray) -> np.ndarray:
        img, transform = prepare_input(frame, self._onnx_size)
        outputs = self._onnx_session.run(None, {self._onnx_input: img})
        detections = decode_detections(
            outputs[0], num_classes=self._onnx_num_classes, transform=transform,
            confidence=self.conf_threshold, classes={0},
            output_format=self._onnx_output_format,
        )
        rows = [[float(x1), float(y1), float(x2), float(y2), float(conf)]
                for x1, y1, x2, y2, conf, _label in detections]
        return np.asarray(rows, dtype=np.float64).reshape(-1, 5)

    def _detect_yolo(self, frame: np.ndarray) -> np.ndarray:
        results = self._model.predict(
            source=frame,
            conf=self.conf_threshold,
            iou=0.5,
            classes=[0],
            verbose=False,
        )[0]
        rows: list[list[float]] = []
        boxes = getattr(results, "boxes", None)
        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().tolist()
            for bbox, conf in zip(xyxy, confs):
                rows.append([float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]), float(conf)])
        return np.asarray(rows, dtype=np.float64).reshape(-1, 5)

    # -- tracking + counting ---------------------------------------------
    def _update_tracks(self, detections: np.ndarray, timestamp: float) -> None:
        tracked = self.tracker.update(detections)
        confirmed = [track for track in tracked if track["hits"] >= self.min_track_frames]
        flags = self.tracker.telemetry.drain_deltas()
        snapshot = self.counting.observe(
            timestamp,
            visible_person_count=int(len(detections)),
            track_refs=[self._track_ref(track["track_id"]) for track in confirmed],
            failure_deltas=flags,
        )
        self._visible_person_count = int(snapshot["visible_person_count"])
        self._last_counting_stats = {
            "visible_person_count": int(snapshot["visible_person_count"]),
            "unique_person_estimate_window": dict(snapshot["unique_person_estimate_window"]),
            "track_failure_flags": self.tracker.telemetry.snapshot(),
        }

    def _track_ref(self, track_id: int) -> str:
        camera = self.camera_id or "unscoped"
        return f"{camera}::{int(track_id)}"

    def _get_active_tracks(self) -> list[dict]:
        """Confirmed tracks (hits >= min_track_frames) from the last update."""
        confirmed = [track for track in self.tracker.output() if track["hits"] >= self.min_track_frames]
        result: list[dict] = []
        for track in confirmed:
            track_id = int(track["track_id"])
            result.append({
                "id": f"Person {track_id}",
                "bbox": [float(value) for value in track["bbox"]],
                "confidence": float(track["confidence"]),
                "color": self._id_to_color(track_id),
                "label": f"P{track_id}",
                "track_id": track_id,
                "track_ref": self._track_ref(track_id),
                "camera_id": self.camera_id,
            })
        return result

    @staticmethod
    def _id_to_color(track_id: int) -> tuple[int, int, int]:
        """Generate a consistent color for each track ID."""
        colors = [
            (0, 255, 255), (255, 0, 255), (255, 255, 0),
            (0, 255, 0), (255, 128, 0), (128, 0, 255),
            (0, 128, 255), (255, 0, 128), (128, 255, 0),
            (0, 128, 128),
        ]
        return colors[track_id % len(colors)]
