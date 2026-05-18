"""Dedicated render thread — annotates frames and streams to clients.

This thread pops frames from the render queue, merges the latest AI results
from the inference subprocess (via result_queue), annotates the frame, encodes
to JPEG, and stores for MJPEG streaming.
"""
from __future__ import annotations

import time
import threading
from collections import deque
from queue import Empty
from typing import Optional, Callable

import cv2
import numpy as np


class RenderThread:
    """Consumer thread: annotates frames and encodes for streaming."""

    def __init__(
        self,
        frame_queue: deque,
        result_cache,  # OverlayCache instance (for FPS, video dims)
        result_queue_mp=None,  # multiprocessing.Queue from inference subprocess
        camera_id: str = "",
        stop_event: Optional[threading.Event] = None,
        set_frame_fn: Optional[Callable] = None,
        annotate_fn: Optional[Callable] = None,
        set_detection_meta_fn: Optional[Callable] = None,
        on_threat_fn: Optional[Callable] = None,
        on_evidence_trigger_fn: Optional[Callable] = None,
        decision_layer=None,
        fusion_engine=None,
        target_fps: int = 20,
        jpeg_quality: int = 75,
    ):
        self.frame_queue = frame_queue
        self.result_cache = result_cache
        self.result_queue_mp = result_queue_mp
        self.camera_id = camera_id
        self.stop_event = stop_event or threading.Event()
        self.set_frame_fn = set_frame_fn
        self.annotate_fn = annotate_fn
        self.set_detection_meta_fn = set_detection_meta_fn
        self.on_threat_fn = on_threat_fn
        self.on_evidence_trigger_fn = on_evidence_trigger_fn
        self._decision_layer = decision_layer
        self._fusion_engine = fusion_engine
        self.target_fps = target_fps
        self.jpeg_quality = jpeg_quality
        self.frame_count: int = 0
        self.encode_latency_ms: float = 0.0
        self._meta_push_counter: int = 0
        self._skip_counter: int = 0
        self._last_threat_state: bool = False
        self._last_alert_time: float = 0.0
        self._last_result: dict = {}

    def run(self):
        """Main loop — runs until stop_event is set."""
        frame_interval = 1.0 / self.target_fps

        while not self.stop_event.is_set():
            t0 = time.perf_counter()

            if not self.frame_queue:
                time.sleep(0.005)
                continue

            try:
                frame = self.frame_queue.popleft()
            except IndexError:
                time.sleep(0.005)
                continue

            self._render_frame(frame)

            elapsed = time.perf_counter() - t0
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _pull_mp_results(self):
        """Drain all available results from the multiprocessing queue."""
        if self.result_queue_mp is None:
            return
        pulled = 0
        for _ in range(30):  # drain up to 30 results per frame
            try:
                result = self.result_queue_mp.get_nowait()
                self._last_result = result
                pulled += 1
                # Merge into OverlayCache for FPS/video dims
                if self.result_cache is not None:
                    self.result_cache.update_from_result(result)
            except Empty:
                break

    def _render_frame(self, frame: np.ndarray):
        """Annotate frame with AI results and encode to JPEG."""
        self.frame_count += 1

        # Pull latest results from inference subprocess
        self._pull_mp_results()

        # Get overlay data — prefer subprocess result, fall back to OverlayCache
        if self._last_result:
            snap = dict(self._last_result)
            # Merge FPS from OverlayCache if available
            if self.result_cache is not None:
                cache_snap = self.result_cache.snapshot()
                snap["fps"] = cache_snap.get("fps", 0.0)
                if not snap.get("video_width"):
                    snap["video_width"] = cache_snap.get("video_width", 0)
                if not snap.get("video_height"):
                    snap["video_height"] = cache_snap.get("video_height", 0)
        elif self.result_cache is not None:
            snap = self.result_cache.snapshot()
        else:
            snap = {"is_threat": False, "threat_confidence": 0.0, "fps": 0.0,
                    "tracks": [], "person_count": 0, "weapon_score": 0.0,
                    "weapon_labels": [], "motion_score": 0.0,
                    "video_width": 0, "video_height": 0}

        # Annotate frame — skip on alternating frames when no threat
        self._skip_counter += 1
        is_threat = snap["is_threat"]
        do_annotate = is_threat or (self._skip_counter % 2 == 1)

        if do_annotate:
            try:
                annotated = self.annotate_fn(
                    frame=frame,
                    tracks=snap["tracks"],
                    person_count=snap["person_count"],
                    is_threat=is_threat,
                    threat_confidence=snap["threat_confidence"],
                    camera_id=self.camera_id,
                    fps=snap.get("fps", 0.0),
                )
            except Exception as exc:
                print(f"[Render] Annotation error: {exc}")
                annotated = frame
        else:
            annotated = frame

        # JPEG encode
        t_enc = time.perf_counter()
        ok, jpg_buf = cv2.imencode(
            ".jpg", annotated,
            [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
        )
        self.encode_latency_ms = (time.perf_counter() - t_enc) * 1000

        if ok:
            self.set_frame_fn(self.camera_id, jpg_buf.tobytes())

        # Push detection metadata frequently enough for responsive browser overlays.
        if self.set_detection_meta_fn is not None:
            self._meta_push_counter += 1
            if self._meta_push_counter % 2 == 0:
                try:
                    meta = dict(snap)
                    # Build multi-threat data whenever live signals are present so
                    # the frontend can render watch-state framing before an alert.
                    if self._fusion_engine is not None:
                        try:
                            fusion_result = self._fusion_engine.assess_multi_threat(
                                violence_confidence=snap.get("violence_conf", 0) / 100.0 if snap.get("violence_conf", 0) > 1 else snap.get("violence_conf", 0),
                                motion_score=snap.get("motion_score", 0),
                                weapon_score=snap.get("weapon_score", 0) / 100.0 if snap.get("weapon_score", 0) > 1 else snap.get("weapon_score", 0),
                                violence_bbox=snap.get("violence_bbox"),
                                weapon_bbox=snap.get("weapon_bbox"),
                                weapon_labels=snap.get("weapon_labels", []),
                                base_severity=snap.get("severity", "high"),
                            )
                            meta["multiThreat"] = fusion_result.get("multiThreat")
                        except Exception:
                            pass
                    self.set_detection_meta_fn(self.camera_id, meta)
                except Exception:
                    pass

        # Trigger alert via decision layer on threat state transition
        current_threat = snap.get("is_threat", False)
        now = time.time()

        if self._decision_layer is not None and current_threat:
            threat_conf = snap.get("threat_confidence", 0) / 100.0
            decision = self._decision_layer.update(max(0.0, min(1.0, threat_conf)))
            if decision["confirmed_alert"] and now - self._last_alert_time > self._decision_layer.cooldown_seconds:
                self._last_alert_time = now
                try:
                    _snap_frame = annotated.copy()
                    _weapon_bbox = snap.get("weapon_bbox")
                    if _weapon_bbox:
                        try:
                            _x1, _y1, _x2, _y2 = [int(c) for c in _weapon_bbox]
                            cv2.rectangle(_snap_frame, (_x1, _y1), (_x2, _y2), (0, 0, 255), 2)
                            _wlabel = (snap.get("weapon_labels") or ["WEAPON"])[0].upper()
                            cv2.putText(_snap_frame, _wlabel, (_x1, max(10, _y1 - 6)),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
                        except Exception:
                            pass
                    _, snapshot_buf = cv2.imencode(".jpg", _snap_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    snapshot_jpeg = snapshot_buf.tobytes() if snapshot_buf is not None else None
                except Exception:
                    snapshot_jpeg = None

                from datetime import datetime, timezone
                import uuid
                alert_id = f"alert-{int(now * 1000)}-{uuid.uuid4().hex[:6]}"
                severity = "critical" if snap.get("threat_confidence", 0) >= 85 else "high" if snap.get("threat_confidence", 0) >= 65 else "medium"
                is_weapon_threat = snap.get("weapon_score", 0) >= 0.30 and snap.get("weapon_score", 0) >= snap.get("violence_conf", 0)
                alert_type = "weapon" if is_weapon_threat else "violence"
                alert_label = "Weapon" if is_weapon_threat else "Violence"
                alert_payload = {
                    "id": alert_id,
                    "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                    "isoTime": datetime.now(timezone.utc).isoformat(),
                    "confidence": round(snap.get("threat_confidence", 0), 1),
                    "modelConfidence": round(snap.get("threat_confidence", 0), 1),
                    "threatConfidence": round(snap.get("threat_confidence", 0), 1),
                    "rawModelConfidence": round(snap.get("violence_conf", 0), 4),
                    "calibratedConfidence": round(snap.get("threat_confidence", 0) / 100.0, 4),
                    "threatType": alert_type,
                    "type": alert_label,
                    "severity": severity,
                    "cameraId": self.camera_id,
                    "location": self.camera_id,
                    "fusionScore": round(snap.get("threat_confidence", 0) / 100.0, 2),
                    "fusionModel": "rule_based",
                    "weaponDetectorReady": True,
                    "fusionReason": "violence" if snap.get("violence_conf", 0) > snap.get("weapon_score", 0) else "weapon" if snap.get("weapon_score", 0) > 0.3 else "none",
                    "motionScore": round(snap.get("motion_score", 0), 2),
                    "weaponScore": round(snap.get("weapon_score", 0) * 100, 1),
                    "personCount": snap.get("person_count", 0),
                    "weaponLabels": snap.get("weapon_labels", []),
                    "alertLatencyMs": 0,
                    "alertState": decision.get("alert_state", "CONFIRMED_VIOLENCE"),
                    "confirmedAlert": decision.get("confirmed_alert", True),
                    "confirmRule": decision.get("confirm_rule", ""),
                    "weaponBbox": list(snap["weapon_bbox"]) if snap.get("weapon_bbox") else None,
                    "violenceBbox": list(snap["violence_bbox"]) if snap.get("violence_bbox") else None,
                    "alertVideoWidth": int(snap.get("video_width", 640)),
                    "alertVideoHeight": int(snap.get("video_height", 480)),
                }
                if self.on_threat_fn is not None:
                    self.on_threat_fn(alert_payload, snapshot_jpeg, None)
                print(f"[Render] Alert triggered: {alert_id} (threat={snap.get('threat_confidence', 0):.1f}%, state={decision['alert_state']})")

                # Reset decision layer to prevent immediate re-confirmation
                if self._decision_layer is not None:
                    self._decision_layer.reset()

                if self.on_evidence_trigger_fn is not None:
                    try:
                        self.on_evidence_trigger_fn(
                            alert_id=alert_id,
                            width=snap.get("video_width", 1280),
                            height=snap.get("video_height", 720),
                            fps=snap.get("fps", 20.0),
                        )
                    except Exception as exc:
                        print(f"[Render] Evidence trigger error: {exc}")
        elif self._decision_layer is None and current_threat and not self._last_threat_state:
            # Fallback: no decision layer, use simple edge detection
            try:
                _snap_frame = annotated.copy()
                _weapon_bbox = snap.get("weapon_bbox")
                if _weapon_bbox:
                    try:
                        _x1, _y1, _x2, _y2 = [int(c) for c in _weapon_bbox]
                        cv2.rectangle(_snap_frame, (_x1, _y1), (_x2, _y2), (0, 0, 255), 2)
                        _wlabel = (snap.get("weapon_labels") or ["WEAPON"])[0].upper()
                        cv2.putText(_snap_frame, _wlabel, (_x1, max(10, _y1 - 6)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
                    except Exception:
                        pass
                _, snapshot_buf = cv2.imencode(".jpg", _snap_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                snapshot_jpeg = snapshot_buf.tobytes() if snapshot_buf is not None else None
            except Exception:
                snapshot_jpeg = None

            from datetime import datetime, timezone
            import uuid
            alert_id = f"alert-{int(now * 1000)}-{uuid.uuid4().hex[:6]}"
            severity = "critical" if snap.get("threat_confidence", 0) >= 85 else "high" if snap.get("threat_confidence", 0) >= 65 else "medium"
            is_weapon_threat = snap.get("weapon_score", 0) >= 0.30 and snap.get("weapon_score", 0) >= snap.get("violence_conf", 0)
            alert_type = "weapon" if is_weapon_threat else "violence"
            alert_label = "Weapon" if is_weapon_threat else "Violence"
            alert_payload = {
                "id": alert_id,
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "isoTime": datetime.now(timezone.utc).isoformat(),
                "confidence": round(snap.get("threat_confidence", 0), 1),
                "modelConfidence": round(snap.get("threat_confidence", 0), 1),
                "threatConfidence": round(snap.get("threat_confidence", 0), 1),
                "rawModelConfidence": round(snap.get("violence_conf", 0), 4),
                "calibratedConfidence": round(snap.get("threat_confidence", 0) / 100.0, 4),
                "threatType": alert_type,
                "type": alert_label,
                "severity": severity,
                "cameraId": self.camera_id,
                "location": self.camera_id,
                "fusionScore": round(snap.get("threat_confidence", 0) / 100.0, 2),
                "fusionModel": "rule_based",
                "weaponDetectorReady": True,
                "fusionReason": "violence" if snap.get("violence_conf", 0) > snap.get("weapon_score", 0) else "weapon" if snap.get("weapon_score", 0) > 0.3 else "none",
                "motionScore": round(snap.get("motion_score", 0), 2),
                "weaponScore": round(snap.get("weapon_score", 0) * 100, 1),
                "personCount": snap.get("person_count", 0),
                "weaponLabels": snap.get("weapon_labels", []),
                "alertLatencyMs": 0,
                "alertState": "CONFIRMED_VIOLENCE",
                "confirmedAlert": True,
                "confirmRule": "fallback_edge",
                "weaponBbox": list(snap["weapon_bbox"]) if snap.get("weapon_bbox") else None,
                "violenceBbox": list(snap["violence_bbox"]) if snap.get("violence_bbox") else None,
                "alertVideoWidth": int(snap.get("video_width", 640)),
                "alertVideoHeight": int(snap.get("video_height", 480)),
            }
            if self.on_threat_fn is not None:
                self.on_threat_fn(alert_payload, snapshot_jpeg, None)
            print(f"[Render] Telegram alert triggered for {alert_id} (threat={snap.get('threat_confidence', 0):.1f}%)")

            # Reset decision layer to prevent immediate re-confirmation
            if self._decision_layer is not None:
                self._decision_layer.reset()

            if self.on_evidence_trigger_fn is not None:
                try:
                    self.on_evidence_trigger_fn(
                        alert_id=alert_id,
                        width=snap.get("video_width", 1280),
                        height=snap.get("video_height", 720),
                        fps=snap.get("fps", 20.0),
                    )
                except Exception as exc:
                    print(f"[Render] Evidence trigger error: {exc}")

        self._last_threat_state = current_threat

    def get_stats(self) -> dict:
        """Return thread statistics."""
        return {
            "frame_count": self.frame_count,
            "encode_latency_ms": round(self.encode_latency_ms, 1),
        }
