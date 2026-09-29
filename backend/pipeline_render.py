"""Render each frame with stable overlays and consume every AI observation."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import logging
from queue import Empty
import threading
import time
from typing import Optional, Callable
import uuid

import cv2
import numpy as np

try:
    from .live_alert_decision import LiveAlertDecisionLayer
except ImportError:
    from live_alert_decision import LiveAlertDecisionLayer

try:
    from .counting import estimate_window_to_wire
except ImportError:
    from counting import estimate_window_to_wire

logger = logging.getLogger(__name__)


class RenderThread:
    def __init__(self, frame_queue: deque, result_cache, result_queue_mp=None,
                 camera_id: str = "", stop_event: Optional[threading.Event] = None,
                 set_frame_fn: Optional[Callable] = None, annotate_fn: Optional[Callable] = None,
                 set_detection_meta_fn: Optional[Callable] = None, on_threat_fn: Optional[Callable] = None,
                 on_evidence_trigger_fn: Optional[Callable] = None, decision_layer=None,
                 fusion_engine=None, target_fps: int = 20, jpeg_quality: int = 75,
                 frame_available: Optional[threading.Event] = None, incident_capture=None):
        self.frame_queue, self.result_cache, self.result_queue_mp = frame_queue, result_cache, result_queue_mp
        self.camera_id = camera_id
        self.stop_event = stop_event or threading.Event()
        self.frame_available = frame_available
        self.set_frame_fn, self.annotate_fn = set_frame_fn, annotate_fn
        self.set_detection_meta_fn, self.on_threat_fn = set_detection_meta_fn, on_threat_fn
        self.on_evidence_trigger_fn = on_evidence_trigger_fn
        # Incident capture (WT-22): trigger() is an O(1) enqueue — all scoring
        # and crop work happens on the capture worker thread, never here.
        self.incident_capture = incident_capture
        self._decision_layer = decision_layer if decision_layer is not None else LiveAlertDecisionLayer()
        self._fusion_engine = fusion_engine
        self.target_fps, self.jpeg_quality = target_fps, jpeg_quality
        self.frame_count = 0
        self.encode_latency_ms = 0.0
        self._last_result: dict = {}
        self._legacy_sequence = 0
        self._health: dict[str, str] = {}
        # WT-17 (S-09): display frames dropped by the latest-wins pop at the last
        # render step; stamped into the detection snapshot as renderBacklogDroppedCount.
        self._render_dropped = 0

    def _failure(self, subsystem: str, exc: Exception) -> None:
        # Expose sanitized health, with detail retained only in server logs.
        self._health[subsystem] = "degraded"
        logger.warning("Render %s failed for camera %s (%s)", subsystem, self.camera_id, type(exc).__name__)

    def run(self):
        # Source capture supplies cadence. Sleeping a frame interval after each
        # encode adds timer rounding and processing time to every source frame.
        while not self.stop_event.is_set():
            started = time.monotonic()
            if not self.frame_queue:
                self._decision_layer.status(current_time=started)
                if self.frame_available is not None:
                    self.frame_available.clear()
                    # Producer may have appended between empty-check and clear.
                    if not self.frame_queue:
                        self.frame_available.wait(0.1)
                else:
                    self.stop_event.wait(0.005)
                continue
            try:
                frame = self.frame_queue.pop()
                self._render_dropped = len(self.frame_queue)
                self.frame_queue.clear()
            except IndexError:
                continue
            try:
                self._render_frame(frame)
            except Exception as exc:
                self._failure("render", exc)

    def _pull_mp_results(self) -> list[dict]:
        results = []
        if self.result_queue_mp is None:
            return results
        for _ in range(30):
            try:
                result = self.result_queue_mp.get_nowait()
            except Empty:
                break
            if not isinstance(result, dict):
                self._health["inference_result"] = "degraded"
                continue
            # Legacy producers get a queue-event identity, never a render identity.
            if result.get("inference_sequence") is None:
                self._legacy_sequence += 1
                result = {**result, "inference_sequence": self._legacy_sequence,
                          "inference_sample_time": time.monotonic()}
            results.append(result)
            self._last_result = result
            if self.result_cache is not None:
                self.result_cache.update_from_result(result)
        return results

    def _observe(self, snap: dict, now: float) -> dict:
        if snap.get("observation_valid", snap.get("window_valid", True)) is False:
            self._health["decision_window"] = "degraded"
            result = self._decision_layer.status(current_time=now)
            return {**result, "decision_sample_accepted": False, "ignored_reason": "invalid_window"}
        sequence = snap.get("inference_sequence")
        timestamp = snap.get("inference_sample_time")
        if sequence is None or timestamp is None:
            result = self._decision_layer.status(current_time=now)
            return {**result, "decision_sample_accepted": False, "ignored_reason": "awaiting_observation"}
        try:
            score = snap.get("observation_score", float(snap.get("threat_confidence", 0)) / 100.0)
            result = self._decision_layer.update(
                score,
                sample_time=timestamp,
                sample_id=sequence,
                current_time=now,
                calibrated_value=snap.get("observation_calibrated_probability"),
                raw_model_score=snap.get("observation_raw_model_score"),
                score_source=snap.get("observation_score_source", "unknown"),
                score_calibration_status=snap.get("observation_calibration_status", "unverified"),
            )
            self._health["decision_window"] = "ok"
            return result
        except (ValueError, TypeError) as exc:
            self._failure("decision", exc)
            result = self._decision_layer.status(current_time=now)
            return {**result, "decision_sample_accepted": False, "ignored_reason": "invalid_observation"}

    def _render_frame(self, frame: np.ndarray):
        self.frame_count += 1
        # WT-17 (S-09): capture stamps travel with the display frame (dict form);
        # ndarray frames and legacy stubs keep working without stamps.
        captured_at = None
        frame_clock_base = "monotonic-gettickcount64"
        if isinstance(frame, dict):
            captured_at = frame.get("captured_at")
            frame_clock_base = frame.get("clock_base") or "monotonic-gettickcount64"
            frame = frame["frame"]
        observations = self._pull_mp_results()
        cache = self.result_cache.snapshot() if self.result_cache is not None else {}
        snap = {"is_threat": False, "threat_confidence": 0.0, "fps": 0.0,
                "tracks": [], "person_count": 0, "weapon_score": 0.0,
                "weapon_labels": [], "motion_score": 0.0, **cache, **self._last_result}
        if cache.get("fps"):
            snap["fps"] = cache["fps"]
        pending_alerts = []
        decision = None
        # Consume ALL queued observations, not just the final positive overlay.
        for observation in observations or [snap]:
            decision = self._observe(observation, time.monotonic())
            if decision["confirmed_alert"] and decision["decision_sample_accepted"]:
                pending_alerts.append((dict(observation), decision))
        snap["decision_layer"] = decision
        snap["severity"] = (self._decision_layer.config.severity_for(float(snap.get("threat_confidence", 0)) / 100.0)
                            if snap.get("is_threat") else "none")

        # WT-17 (S-09): run fusion before annotation so decision overlays are burned
        # into the exact frame they describe (frame-accurate server-side overlay).
        if self._fusion_engine is not None:
            try:
                fused = self._fusion_engine.assess_multi_threat(
                    violence_confidence=snap.get("violence_conf", 0), motion_score=snap.get("motion_score", 0),
                    weapon_score=snap.get("weapon_score", 0), violence_bbox=snap.get("violence_bbox"),
                    weapon_bbox=snap.get("weapon_bbox"), weapon_labels=snap.get("weapon_labels", []),
                    base_severity=snap["severity"])
                snap["multiThreat"] = fused["multiThreat"]
            except Exception as exc:
                self._failure("fusion", exc)

        annotated = frame
        if self.annotate_fn is not None:
            try:
                annotated = self.annotate_fn(frame=frame, tracks=snap["tracks"],
                    person_count=snap["person_count"], is_threat=snap["is_threat"],
                    threat_confidence=snap["threat_confidence"], camera_id=self.camera_id, fps=snap.get("fps", 0.0),
                    threat_boxes=(snap.get("multiThreat") or {}).get("threatBoxes") or None,
                    decision_state=(decision or {}).get("alert_state"))
                self._health["annotation"] = "ok"
            except Exception as exc:
                self._failure("annotation", exc)
                annotated = frame

        stream_frame = annotated
        height, width = annotated.shape[:2]
        if width > 854:
            stream_frame = cv2.resize(annotated, (854, int(height * 854 / width)), interpolation=cv2.INTER_LINEAR)
        started = time.perf_counter()
        ok, jpg = cv2.imencode(".jpg", stream_frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        self.encode_latency_ms = (time.perf_counter() - started) * 1000
        frame_sequence = None
        if ok and self.set_frame_fn is not None:
            # WT-17 (S-09): set_frame returns the assigned display sequence — the SAME
            # identity the MJPEG stream serves; legacy 2-arg stubs keep working.
            try:
                frame_sequence = self.set_frame_fn(self.camera_id, jpg.tobytes(), captured_at, frame_clock_base)
            except TypeError:
                frame_sequence = self.set_frame_fn(self.camera_id, jpg.tobytes())
        elif not ok:
            self._health["jpeg_encode"] = "degraded"

        if self._fusion_engine is not None:
            try:
                fused = self._fusion_engine.assess_multi_threat(
                    violence_confidence=snap.get("violence_conf", 0), motion_score=snap.get("motion_score", 0),
                    weapon_score=snap.get("weapon_score", 0), violence_bbox=snap.get("violence_bbox"),
                    weapon_bbox=snap.get("weapon_bbox"), weapon_labels=snap.get("weapon_labels", []),
                    weapon_group=snap.get("weapon_group"),
                    base_severity=snap["severity"])
                snap["multiThreat"] = fused["multiThreat"]
            except Exception as exc:
                self._failure("fusion", exc)
        snap["pipeline_health"] = {**snap.get("pipeline_health", {}), **self._health}
        # WT-17 (S-09) SC-3: stamp frame identity + freshness onto the snapshot so the
        # /detections payload correlates overlays with the exact published frame. Raw
        # stamps stay process-internal; the wire carries durations only (SC-6).
        if isinstance(frame_sequence, int) and not isinstance(frame_sequence, bool):
            snap["frameSequence"] = frame_sequence
        snap["frame_captured_at"] = captured_at
        snap["frame_clock_base"] = frame_clock_base
        snap["renderBacklogDroppedCount"] = self._render_dropped
        if self.set_detection_meta_fn is not None:
            try:
                self.set_detection_meta_fn(self.camera_id, snap)
            except Exception as exc:
                self._failure("metadata", exc)

        for alert_snap, alert_decision in pending_alerts:
            self._emit_alert(alert_snap, alert_decision, annotated)

    def _emit_alert(self, snap: dict, decision: dict, annotated: np.ndarray) -> None:
        snapshot_jpeg = None
        try:
            snapshot = annotated.copy()
            weapon_box = snap.get("weapon_bbox")
            if weapon_box and snap.get("weapon_score", 0) >= self._decision_layer.config.weapon_display_threshold:
                coords = np.asarray(weapon_box, dtype=float)
                if coords.shape == (4,) and np.isfinite(coords).all():
                    height, width = snapshot.shape[:2]
                    if (coords >= 0).all() and (coords <= 1).all():
                        coords *= np.array([width, height, width, height])
                    coords = np.clip(coords, 0, [width - 1, height - 1, width - 1, height - 1]).astype(int)
                    x1, y1, x2, y2 = coords
                    if x2 > x1 and y2 > y1:
                        cv2.rectangle(snapshot, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        label = str((snap.get("weapon_labels") or ["WEAPON"])[0]).upper()[:32]
                        cv2.putText(snapshot, label, (x1, max(10, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.55, (0, 0, 255), 2)
            ok, image = cv2.imencode(".jpg", snapshot, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                snapshot_jpeg = image.tobytes()
        except Exception as exc:
            self._failure("alert_snapshot", exc)
        now = datetime.now(timezone.utc)
        alert_id = f"alert-{int(now.timestamp() * 1000)}-{uuid.uuid4().hex[:6]}"
        score = float(snap.get("observation_score", float(snap.get("threat_confidence", 0)) / 100.0))
        weapon = float(snap.get("weapon_score", 0))
        violence = float(snap.get("violence_conf", 0))
        score_source = str(snap.get("observation_score_source") or "unknown")
        if score_source == "weapon":
            is_weapon = True
        elif score_source == "violence":
            is_weapon = False
        else:
            is_weapon = weapon >= self._decision_layer.config.weapon_threshold and weapon >= violence
            score_source = "weapon" if is_weapon else "violence"
        raw_model_score = snap.get("observation_raw_model_score")
        if raw_model_score is None:
            raw_model_score = snap.get("weapon_raw_model_score" if is_weapon else "violence_raw_model_score")
        try:
            raw_model_score = (None if raw_model_score is None else float(raw_model_score))
            if (raw_model_score is not None and
                    (not np.isfinite(raw_model_score) or not 0 <= raw_model_score <= 1)):
                raw_model_score = None
        except (TypeError, ValueError):
            raw_model_score = None
        calibrated_probability = snap.get("observation_calibrated_probability")
        calibration_status = str(snap.get("observation_calibration_status", "unverified"))
        try:
            calibrated_probability = (None if calibrated_probability is None
                                      else float(calibrated_probability))
            if (calibrated_probability is not None and
                    (not np.isfinite(calibrated_probability) or not 0 <= calibrated_probability <= 1 or
                     calibration_status not in {"calibrated", "calibrated-candidate"})):
                calibrated_probability = None
                calibration_status = "unverified"
        except (TypeError, ValueError):
            calibrated_probability = None
            calibration_status = "unverified"
        if calibrated_probability is None and calibration_status in {"calibrated", "calibrated-candidate"}:
            calibration_status = "unverified"
        raw_violence_score = snap.get("violence_raw_model_score")
        try:
            raw_violence_score = (None if raw_violence_score is None
                                  else float(raw_violence_score))
            if (raw_violence_score is not None and
                    (not np.isfinite(raw_violence_score) or not 0 <= raw_violence_score <= 1)):
                raw_violence_score = None
        except (TypeError, ValueError):
            raw_violence_score = None
        payload = {
            "id": alert_id, "timestamp": now.strftime("%H:%M:%S UTC"), "isoTime": now.isoformat(),
            "confidence": round(score * 100, 1), "modelConfidence": round(score * 100, 1),
            "threatConfidence": round(score * 100, 1),
            "rawModelConfidence": (None if raw_violence_score is None else round(raw_violence_score, 4)),
            "calibratedConfidence": (round(calibrated_probability, 4) if calibrated_probability is not None else None),
            "calibrationStatus": calibration_status,
            "rawModelScore": (None if raw_model_score is None else round(raw_model_score, 4)),
            "calibratedProbability": (round(calibrated_probability, 4) if calibrated_probability is not None else None),
            "scoreSemantics": {
                "confidence": "decision score percent; source-specific and not necessarily a probability",
                "modelConfidence": "alias of confidence",
                "threatConfidence": "alias of confidence",
                "rawModelConfidence": "untransformed violence model score (0-1), when supplied",
                "rawModelScore": "untransformed score from the selected producer named by scoreSource, or null when unavailable",
                "calibratedConfidence": "temperature-scaled calibrated probability from a validated artifact; null while unverified",
                "calibratedProbability": "temperature-scaled calibrated probability from a validated artifact; null while unverified",
                "severity": "rule-based severity band of the confirmed alert score (never below medium)",
            },
            "scoreSource": score_source,
            "severitySource": "rule-based-band-of-fused-score-min-medium",
            "decisionConfirmLatencyMs": decision.get("decision_confirm_latency_ms"),
            # Onset/window identity mirror (R7, SC-4; additive, fed from SC-2 result fields).
            "onsetCandidateAt": snap.get("violence_onset_candidate_timestamp"),
            "onsetCandidateWindowId": snap.get("violence_onset_candidate_window_id"),
            "violenceWindowId": snap.get("violence_window_id"),
            "violenceWindowStartTimestamp": snap.get("violence_window_start_timestamp"),
            "violenceWindowEndTimestamp": snap.get("violence_window_end_timestamp"),
            "threatType": "weapon" if is_weapon else "violence", "type": "Weapon" if is_weapon else "Violence",
            "severity": self._decision_layer.config.alert_severity_for(score),
            "cameraId": self.camera_id, "location": self.camera_id,
            "fusionScore": round(score, 4), "fusionModel": "rule_based",
            "weaponDetectorReady": snap.get("weapon_detector_ready", False),
            "fusionReason": "weapon" if is_weapon else "violence",
            "motionScore": round(snap.get("motion_score", 0), 2), "weaponScore": round(weapon * 100, 1),
            "personCount": snap.get("person_count", 0), "weaponLabels": snap.get("weapon_labels", []),
            "alertLatencyMs": None, "alertState": decision["alert_state"], "confirmedAlert": True,
            "confirmRule": decision["confirm_rule"], "decisionLayer": decision,
            "weaponBbox": list(snap["weapon_bbox"]) if snap.get("weapon_bbox") else None,
            "violenceBbox": list(snap["violence_bbox"]) if snap.get("violence_bbox") else None,
            "alertVideoWidth": int(snap.get("video_width", annotated.shape[1])),
            "alertVideoHeight": int(snap.get("video_height", annotated.shape[0])),
            # --- canonical counting semantics (S-04/WT-22, additive to SC-2/SC-3) ---
            "visiblePersonCount": int(snap.get("visible_person_count", 0) or 0),
            "activeTrackCount": int(snap.get("active_track_count", snap.get("person_count", 0)) or 0),
            "uniquePersonEstimateWindow": estimate_window_to_wire(snap.get("unique_person_estimate_window")),
            "trackFailureFlags": dict(snap.get("track_failure_flags") or {}),
            "personTracker": str(snap.get("person_tracker") or ""),
            "trackNamespace": self.camera_id,
        }
        # Incident capture: enqueue only, before delivery so the delivered alert
        # carries its capture state. trigger() copies ring references and
        # returns; scoring/crops/records run on the capture worker thread. A
        # failure here degrades the capture subsystem, never the alert path.
        if self.incident_capture is not None:
            try:
                status = self.incident_capture.trigger(alert_id=alert_id, camera_id=self.camera_id)
                payload["capture"] = {"state": status.get("state", "pending"),
                                      "preCandidates": status.get("pre_candidates", 0),
                                      "alertId": alert_id}
                self._health["incident_capture"] = "ok"
            except Exception as exc:
                self._failure("incident_capture", exc)
        if self.on_threat_fn is not None:
            try:
                self.on_threat_fn(payload, snapshot_jpeg, None)
                self._health["alert_delivery"] = "ok"
            except Exception as exc:
                self._failure("alert_delivery", exc)
        # Preserve decision history and cooldown after delivery, including failures.
        if self.on_evidence_trigger_fn is not None:
            try:
                self.on_evidence_trigger_fn(alert_id=alert_id, width=payload["alertVideoWidth"],
                    height=payload["alertVideoHeight"], fps=snap.get("fps", 20.0))
            except Exception as exc:
                self._failure("evidence_trigger", exc)

    def get_stats(self) -> dict:
        return {"frame_count": self.frame_count, "encode_latency_ms": round(self.encode_latency_ms, 1),
                "health": dict(self._health)}
