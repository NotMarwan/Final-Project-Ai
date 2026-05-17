"""Dedicated render thread — annotates frames and streams to clients.

This thread pops frames from the capture queue, applies the latest AI
results from the cache, annotates the frame, encodes to JPEG, and
stores for MJPEG streaming.
"""
from __future__ import annotations

import time
import threading
from collections import deque
from typing import Optional, Callable

import cv2
import numpy as np


class RenderThread:
    """Consumer thread: annotates frames and encodes for streaming."""

    def __init__(
        self,
        frame_queue: deque,
        result_cache,  # OverlayCache instance
        camera_id: str,
        stop_event: threading.Event,
        set_frame_fn: Callable[[str, bytes], None],  # state.set_frame
        annotate_fn: Callable,  # visual_annotator.annotate
        set_detection_meta_fn: Optional[Callable] = None,  # state.set_detection_meta
        on_threat_fn: Optional[Callable] = None,  # callback(alert_payload, snapshot_jpeg, clip_path)
        on_evidence_trigger_fn: Optional[Callable] = None,  # callback(alert_id, width, height, fps)
        decision_layer = None,  # LiveAlertDecisionLayer instance
        target_fps: int = 20,
        jpeg_quality: int = 75,
    ):
        self.frame_queue = frame_queue
        self.result_cache = result_cache
        self.camera_id = camera_id
        self.stop_event = stop_event
        self.set_frame_fn = set_frame_fn
        self.annotate_fn = annotate_fn
        self.set_detection_meta_fn = set_detection_meta_fn
        self.on_threat_fn = on_threat_fn
        self.on_evidence_trigger_fn = on_evidence_trigger_fn
        self._decision_layer = decision_layer
        self.target_fps = target_fps
        self.jpeg_quality = jpeg_quality
        self.frame_count: int = 0
        self.encode_latency_ms: float = 0.0
        self._meta_push_counter: int = 0
        self._skip_counter: int = 0
        self._last_threat_state: bool = False
        self._last_alert_time: float = 0.0

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

            # Maintain target FPS
            elapsed = time.perf_counter() - t0
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _render_frame(self, frame: np.ndarray):
        """Annotate frame with AI results and encode to JPEG."""
        self.frame_count += 1

        # Get latest AI results from cache
        snap = self.result_cache.snapshot()

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

        # Push detection metadata to SSE every 5 frames (throttled)
        if self.set_detection_meta_fn is not None:
            self._meta_push_counter += 1
            if self._meta_push_counter % 5 == 0:
                try:
                    self.set_detection_meta_fn(self.camera_id, snap)
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
                    _, snapshot_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    snapshot_jpeg = snapshot_buf.tobytes() if snapshot_buf is not None else None
                except Exception:
                    snapshot_jpeg = None

                from datetime import datetime, timezone
                import uuid
                alert_id = f"alert-{int(now * 1000)}-{uuid.uuid4().hex[:6]}"
                severity = "critical" if snap.get("threat_confidence", 0) >= 85 else "high" if snap.get("threat_confidence", 0) >= 65 else "medium"
                alert_payload = {
                    "id": alert_id,
                    "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                    "isoTime": datetime.now(timezone.utc).isoformat(),
                    "confidence": round(snap.get("threat_confidence", 0), 1),
                    "modelConfidence": round(snap.get("threat_confidence", 0), 1),
                    "threatConfidence": round(snap.get("threat_confidence", 0), 1),
                    "type": "Violence",
                    "severity": severity,
                    "cameraId": self.camera_id,
                    "location": self.camera_id,
                    "fusionScore": round(snap.get("threat_confidence", 0) / 100.0, 2),
                    "motionScore": round(snap.get("motion_score", 0), 2),
                    "weaponScore": round(snap.get("weapon_score", 0), 2),
                    "personCount": snap.get("person_count", 0),
                    "weaponLabels": snap.get("weapon_labels", []),
                }
                if self.on_threat_fn is not None:
                    self.on_threat_fn(alert_payload, snapshot_jpeg, None)
                print(f"[Render] Alert triggered: {alert_id} (threat={snap.get('threat_confidence', 0):.1f}%, state={decision['alert_state']})")

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
                _, snapshot_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                snapshot_jpeg = snapshot_buf.tobytes() if snapshot_buf is not None else None
            except Exception:
                snapshot_jpeg = None

            from datetime import datetime, timezone
            import uuid
            alert_id = f"alert-{int(now * 1000)}-{uuid.uuid4().hex[:6]}"
            severity = "critical" if snap.get("threat_confidence", 0) >= 85 else "high" if snap.get("threat_confidence", 0) >= 65 else "medium"
            alert_payload = {
                "id": alert_id,
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "isoTime": datetime.now(timezone.utc).isoformat(),
                "confidence": round(snap.get("threat_confidence", 0), 1),
                "modelConfidence": round(snap.get("threat_confidence", 0), 1),
                "threatConfidence": round(snap.get("threat_confidence", 0), 1),
                "type": "Violence",
                "severity": severity,
                "cameraId": self.camera_id,
                "location": self.camera_id,
                "fusionScore": round(snap.get("threat_confidence", 0) / 100.0, 2),
                "motionScore": round(snap.get("motion_score", 0), 2),
                "weaponScore": round(snap.get("weapon_score", 0), 2),
                "personCount": snap.get("person_count", 0),
                "weaponLabels": snap.get("weapon_labels", []),
            }
            if self.on_threat_fn is not None:
                self.on_threat_fn(alert_payload, snapshot_jpeg, None)
            print(f"[Render] Telegram alert triggered for {alert_id} (threat={snap.get('threat_confidence', 0):.1f}%)")

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
