import asyncio
import json
import os
import time
import threading
import queue
import base64
import yaml
from dotenv import load_dotenv
from collections import deque
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Dict, Optional, Tuple, Union

import cv2
import numpy as np
import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent

try:
    from .inference import ViolenceInferencePipeline, VIOLENCE_CLS
    from .fusion import ThreatFusionEngine
    from .security import AccessController, AuditLogger
    from .evidence import EvidenceLedger
    from .audio import AudioRiskAnalyzer
    from .face_intel import FaceIntelEngine
    from .notifications import TelegramNotifier
    from .reporting import build_incident_pdf
except ImportError:
    from inference import ViolenceInferencePipeline, VIOLENCE_CLS
    from fusion import ThreatFusionEngine
    from security import AccessController, AuditLogger
    from evidence import EvidenceLedger
    from audio import AudioRiskAnalyzer
    from face_intel import FaceIntelEngine
    from notifications import TelegramNotifier
    from reporting import build_incident_pdf

# ─────────────────────────────────────────────────────────────────────────────
# 1. Configuration & Environment Setup
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv()

with open(BASE_DIR / "config.yml", "r") as f:
    config = yaml.safe_load(f)

def _parse_source(raw: str) -> Union[str, int]:
    try:
        return int(raw)
    except ValueError:
        return raw

def _resolve_profiles_path() -> Path:
    raw = os.getenv("CAMERA_PROFILES_PATH", "camera_profiles.yml")
    path = Path(raw)
    return path if path.is_absolute() else BASE_DIR / path


def _camera_source_from_profile(payload: dict) -> Optional[Union[str, int]]:
    if not isinstance(payload, dict):
        return None
    if payload.get("enabled") is False:
        return None

    rtsp = payload.get("rtsp")
    if isinstance(rtsp, dict):
        high = rtsp.get("high")
        low  = rtsp.get("low")
        # Prefer low-quality (stream2/720p) for live inference — 4× fewer
        # pixels means dramatically lower decode + AI latency.  Fall back
        # to high only if low is absent.
        for candidate in (low, high):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

    source = payload.get("source")
    if isinstance(source, int):
        return source
    if isinstance(source, str) and source.strip():
        return _parse_source(source.strip())

    return None


def _load_profile_camera_sources(path: Path) -> Dict[str, Union[str, int]]:
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            profile_doc = yaml.safe_load(f) or {}
    except Exception as exc:
        print(f"[System] Failed to read camera profile file: {exc}")
        return {}

    cameras = profile_doc.get("cameras")
    if not isinstance(cameras, dict):
        return {}

    loaded: Dict[str, Union[str, int]] = {}
    for camera_id, payload in cameras.items():
        if not isinstance(camera_id, str):
            continue
        source = _camera_source_from_profile(payload)
        if source is not None:
            loaded[camera_id] = source
    return loaded


def _default_camera_sources() -> Dict[str, Union[str, int]]:
    return {
        "CAM-01": _parse_source(os.getenv("CAM1_SOURCE", "cam1.mp4")),
        "CAM-02": _parse_source(os.getenv("CAM2_SOURCE", "cam2.mp4")),
        "CAM-03": _parse_source(os.getenv("CAM3_SOURCE", "cam3.mp4")),
    }


def _load_camera_sources() -> Dict[str, Union[str, int]]:
    profile_path = _resolve_profiles_path()
    profile_sources = _load_profile_camera_sources(profile_path)
    if profile_sources:
        print(f"[System] Loaded {len(profile_sources)} camera(s) from {profile_path}")
        return profile_sources
    print("[System] Using CAMERA_SOURCES from environment/default values.")
    return _default_camera_sources()


CAMERA_SOURCES: Dict[str, Union[str, int]] = _load_camera_sources()
DEFAULT_CAMERA_ID = os.getenv("DEFAULT_CAMERA_ID", next(iter(CAMERA_SOURCES), "CAM-01"))
if DEFAULT_CAMERA_ID not in CAMERA_SOURCES and CAMERA_SOURCES:
    DEFAULT_CAMERA_ID = next(iter(CAMERA_SOURCES))

WEIGHTS_PATH = os.getenv("WEIGHTS_PATH", "best_model.pt")
THRESHOLD    = float(os.getenv("THRESHOLD", str(config['model']['confidence_threshold'])))
STRIDE       = int(os.getenv("STRIDE", str(config['model']['stride'])))

JPEG_QUALITY   = 80
TARGET_FPS     = 25
RING_BUFFER_LEN = 150  
POST_ALERT_LEN  = 150  


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}

def _resolve_storage_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else BASE_DIR / path


EVIDENCE_DIR = _resolve_storage_path(config['storage']['evidence_dir'])
EVIDENCE_DIR.mkdir(exist_ok=True)

THUMBNAILS_DIR = _resolve_storage_path(config['storage']['thumbnails_dir'])
THUMBNAILS_DIR.mkdir(exist_ok=True)

REPORTS_DIR = _resolve_storage_path(config['storage'].get('reports_dir', "./reports"))
REPORTS_DIR.mkdir(exist_ok=True)

# ── Engine Initializations ──
telegram_notifier = TelegramNotifier.from_settings(config, os.environ)
fusion_engine = ThreatFusionEngine.from_settings(config)
security_controller = AccessController.from_settings(config, os.environ)
audit_logger = AuditLogger.from_settings(config, BASE_DIR)
evidence_ledger = EvidenceLedger.from_settings(config, BASE_DIR)
audio_analyzer = AudioRiskAnalyzer.from_settings(config)
face_engine = FaceIntelEngine.from_settings(config, os.environ, BASE_DIR)
CAPTURE_LOOP_ENABLED = _env_flag("AI_SENTINEL_ENABLE_CAPTURE_LOOP", default=True)

# ── Groq VLM Setup ──
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ENABLED = bool(GROQ_API_KEY)
_groq_client = None

if GROQ_ENABLED:
    try:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
        print("[System] Groq initialized successfully.")
    except Exception as exc:
        print(f"[System] Failed to initialize Groq: {exc}")
        GROQ_ENABLED = False

_VLM_PROMPT = (
    "Act as a professional security expert. Describe the security incident or potential violence in this surveillance frame "
    "in one short, professional paragraph in English. Focus on the number of individuals, physical actions, "
    "and potential weapons if visible."
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Pydantic Models (Request Validation)
# ─────────────────────────────────────────────────────────────────────────────

class ThresholdRequest(BaseModel):
    threshold: float = Field(..., ge=0.10, le=0.95)

class CameraRequest(BaseModel):
    camera_id: str = Field(...)

class CooldownRequest(BaseModel):
    cooldown: float = Field(..., ge=15.0, le=120.0)

class AudioAnalysisRequest(BaseModel):
    audio_base64: str
    filename: Optional[str] = None


class FacePersonUpdateRequest(BaseModel):
    display_name: str
    role: Optional[str] = None


class FaceEnrollRequest(BaseModel):
    image_base64: str
    display_name: Optional[str] = None
    role: Optional[str] = None


class FacePolicyRequest(BaseModel):
    identity_labeling_enabled: Optional[bool] = None
    recognition_audit_enabled: Optional[bool] = None
    recognition_audit_cooldown_sec: Optional[int] = Field(default=None, ge=1, le=3600)

# ─────────────────────────────────────────────────────────────────────────────
# 3. Application State Management
# ─────────────────────────────────────────────────────────────────────────────

class AppState:
    def __init__(self):
        # Per-camera frame storage
        self._frames_lock = threading.Lock()
        self._frame_jpgs: Dict[str, bytes] = {}
        
        self._aq_lock = threading.Lock()
        self._alert_queues: list[queue.Queue] = []
        
        self._evidence_lock = threading.Lock()
        self._evidence_status: Dict[str, str] = {}
        
        self._alert_lock = threading.Lock()
        self._alerts: Dict[str, dict] = {}
        
        self._report_lock = threading.Lock()
        self._report_texts: Dict[str, str] = {}
        
        self._snapshot_lock = threading.Lock()
        self._snapshot_paths: Dict[str, str] = {}
        
        self._face_lock = threading.Lock()
        self._face_summary: Dict[str, object] = {}

        # Camera statistics
        self._cam_stats_lock = threading.Lock()
        self._camera_heartbeats: Dict[str, float] = {}
        self._camera_alert_counts: Dict[str, int] = {}
        
        # Threshold management and pipeline registry
        self._threshold_lock = threading.Lock()
        self._current_threshold = THRESHOLD
        self._pipelines_lock = threading.Lock()
        self._pipelines: set[ViolenceInferencePipeline] = set()
        
        self._camera_lock = threading.Lock()
        self._pending_switch: Optional[Tuple[Union[str, int], str]] = None
        self._current_cam_id = DEFAULT_CAMERA_ID
        
        self._cooldown_lock = threading.Lock()
        self._cooldown = 60.0  
        
        self.running = False

    def set_frame(self, camera_id: str, jpg: bytes):
        with self._frames_lock:
            self._frame_jpgs[camera_id] = jpg
        # Update heartbeat
        with self._cam_stats_lock:
            self._camera_heartbeats[camera_id] = time.time()

    def get_frame(self, camera_id: str) -> Optional[bytes]:
        with self._frames_lock:
            return self._frame_jpgs.get(camera_id)

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=128)
        with self._aq_lock:
            self._alert_queues.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._aq_lock:
            if q in self._alert_queues:
                self._alert_queues.remove(q)

    def broadcast_alert(self, payload: dict):
        data = json.dumps(payload)
        with self._aq_lock:
            for q in list(self._alert_queues):
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass

    def register_pipeline(self, pipeline: ViolenceInferencePipeline):
        # Set pipeline threshold to current global threshold
        with self._threshold_lock:
            current = self._current_threshold
        pipeline.threshold = current
        with self._pipelines_lock:
            self._pipelines.add(pipeline)

    def set_threshold(self, value: float) -> float:
        with self._threshold_lock:
            self._current_threshold = value
        with self._pipelines_lock:
            for p in self._pipelines:
                p.threshold = value
        return value

    def get_threshold(self) -> float:
        with self._threshold_lock:
            return self._current_threshold

    def set_cooldown(self, value: float) -> float:
        with self._cooldown_lock:
            self._cooldown = value
            return value

    def get_cooldown(self) -> float:
        with self._cooldown_lock:
            return self._cooldown

    def request_camera_switch(self, source: Union[str, int], camera_id: str):
        with self._camera_lock:
            self._pending_switch = (source, camera_id)

    def consume_pending_switch(self) -> Optional[Tuple[Union[str, int], str]]:
        with self._camera_lock:
            pending = self._pending_switch
            if pending:
                self._pending_switch = None
                self._current_cam_id = pending[1]
            return pending

    def get_current_camera_id(self) -> str:
        with self._camera_lock:
            return self._current_cam_id

    def mark_evidence(self, alert_id: str, status: str):
        with self._evidence_lock:
            self._evidence_status[alert_id] = status

    def get_evidence_status(self, alert_id: str) -> Optional[str]:
        with self._evidence_lock:
            return self._evidence_status.get(alert_id)

    def get_camera_status(self, camera_id: str) -> dict:
        """Return per-camera status info."""
        with self._cam_stats_lock:
            return {
                "cameraId": camera_id,
                "lastFrameTimestamp": self._camera_heartbeats.get(camera_id),
                "alertCount": self._camera_alert_counts.get(camera_id, 0)
            }

    def register_alert(self, payload: dict):
        alert_id = payload.get("id")
        if not alert_id:
            return
        with self._alert_lock:
            self._alerts[alert_id] = dict(payload)
        # Increment per-camera alert count
        camera_id = payload.get("cameraId")
        if camera_id:
            with self._cam_stats_lock:
                self._camera_alert_counts[camera_id] = self._camera_alert_counts.get(camera_id, 0) + 1

    def get_alert(self, alert_id: str) -> Optional[dict]:
        with self._alert_lock:
            alert = self._alerts.get(alert_id)
            return dict(alert) if alert else None

    def store_report_text(self, alert_id: str, report_text: str):
        with self._report_lock:
            self._report_texts[alert_id] = report_text

    def get_report_text(self, alert_id: str) -> Optional[str]:
        with self._report_lock:
            return self._report_texts.get(alert_id)

    def store_snapshot_path(self, alert_id: str, snapshot_path: str):
        with self._snapshot_lock:
            self._snapshot_paths[alert_id] = snapshot_path

    def get_snapshot_path(self, alert_id: str) -> Optional[Path]:
        with self._snapshot_lock:
            raw = self._snapshot_paths.get(alert_id)
        return Path(raw) if raw else None

    def store_face_summary(self, summary: Dict[str, object]):
        with self._face_lock:
            self._face_summary = dict(summary)

    def get_face_summary(self) -> Dict[str, object]:
        with self._face_lock:
            return dict(self._face_summary)

state = AppState()

# ─────────────────────────────────────────────────────────────────────────────
# 4. Background Workers (DVR & VLM)
# ─────────────────────────────────────────────────────────────────────────────

def _write_evidence_clip(alert_id: str, pre_frames: list, post_queue: queue.Queue, fps: float, width: int, height: int):
    out_path = EVIDENCE_DIR / f"{alert_id}.mp4"
    state.mark_evidence(alert_id, "writing")
    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
        
        for frame in pre_frames:
            writer.write(frame)
            
        collected = 0
        while collected < POST_ALERT_LEN:
            try:
                frame = post_queue.get(timeout=2.0)
                if frame is None:
                    break
                writer.write(frame)
                collected += 1
            except queue.Empty:
                break
                
        writer.release()
        state.mark_evidence(alert_id, "ready")
        audit_logger.record(
            "evidence_clip_ready",
            "success",
            role="system",
            alert_id=alert_id,
            details={"path": str(out_path)},
        )
        print(f"[Evidence] Clip compiled successfully: {alert_id}.mp4")
    except Exception as exc:
        state.mark_evidence(alert_id, "error")
        audit_logger.record(
            "evidence_clip_failed",
            "error",
            role="system",
            alert_id=alert_id,
            details={"error": str(exc)},
        )
        print(f"[Evidence] Error writing clip {alert_id}: {exc}")

def _call_vlm_forensics(alert_id: str, frame: np.ndarray):
    """
    Forensic reporting function using Groq AI (Llama-3.2-Vision).
    """
    global _groq_client
    report_text = None
    last_error = ""

    if GROQ_ENABLED and _groq_client:
        try:
            ok, jpg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                raise ValueError("Failed to encode image to JPG for Groq")
            
            base64_image = base64.b64encode(jpg_buf.tobytes()).decode("utf-8")
            
            response = _groq_client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _VLM_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ],
                    }
                ],
                max_tokens=300,
            )
            report_text = response.choices[0].message.content.strip()
            print(f"[VLM] Forensic report generated for {alert_id} using Groq")
        except Exception as groq_exc:
            last_error = str(groq_exc)
            print(f"[VLM] Groq engine failed: {last_error}")

    if report_text is None:
        report_text = f"[Forensic analysis failed: {last_error}]"

    state.broadcast_alert({
        "type": "VLM_Report", 
        "id": alert_id, 
        "text": report_text
    })
    state.store_report_text(alert_id, report_text)
    audit_logger.record(
        "vlm_report_generated",
        "success" if not report_text.startswith("[فشل") else "error",
        role="system",
        alert_id=alert_id,
        details={"chars": len(report_text)},
    )

# ─────────────────────────────────────────────────────────────────────────────
# 5. Core Video Capture & Inference Engine
# ─────────────────────────────────────────────────────────────────────────────

def _encode_snapshot(frame: np.ndarray) -> Optional[bytes]:
    try:
        ok, jpg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return None
        return jpg_buf.tobytes()
    except Exception as exc:
        print(f"[Telegram] Snapshot encoding failed: {exc}")
        return None


def _estimate_motion_score(previous_frame: Optional[np.ndarray], current_frame: np.ndarray) -> float:
    if previous_frame is None:
        return 0.0

    try:
        prev_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
        prev_small = cv2.resize(prev_gray, (64, 64), interpolation=cv2.INTER_AREA)
        curr_small = cv2.resize(curr_gray, (64, 64), interpolation=cv2.INTER_AREA)
        diff = cv2.absdiff(prev_small, curr_small)
        return float(diff.mean() / 255.0)
    except Exception:
        return 0.0


def _public_face_summary(face_summary: Dict[str, object]) -> Dict[str, object]:
    identity_enabled = bool(face_summary.get("identityLabelingEnabled", True))
    recognized_raw = face_summary.get("recognized", [])
    observations_raw = face_summary.get("observations", [])

    alias_map: Dict[str, str] = {}

    def _alias_for(person_key: str) -> str:
        existing = alias_map.get(person_key)
        if existing:
            return existing
        alias = f"K-{len(alias_map) + 1:03d}"
        alias_map[person_key] = alias
        return alias

    recognized_public = []
    if isinstance(recognized_raw, list):
        for idx, item in enumerate(recognized_raw):
            if not isinstance(item, dict):
                continue
            entry = dict(item)
            if not identity_enabled:
                person_key = str(item.get("personId", "")).strip() or f"KNOWN-{idx + 1}"
                alias = _alias_for(person_key)
                entry["personId"] = alias
                entry["label"] = alias
                entry["masked"] = True
            recognized_public.append(entry)

    observations_public = []
    if isinstance(observations_raw, list):
        for idx, obs in enumerate(observations_raw):
            if not isinstance(obs, dict):
                continue
            entry = dict(obs)
            if not identity_enabled and str(obs.get("kind", "")).strip().lower() == "known":
                person_key = str(obs.get("id", "")).strip() or f"KNOWN-{idx + 1}"
                alias = _alias_for(person_key)
                entry["id"] = alias
                entry["label"] = alias
            observations_public.append(entry)

    return {
        "enabled": bool(face_summary.get("enabled", False)),
        "identityLabelingEnabled": identity_enabled,
        "frameIndex": int(face_summary.get("frameIndex", 0)),
        "totalFaces": int(face_summary.get("totalFaces", 0)),
        "recognized": recognized_public,
        "recognizedCount": int(face_summary.get("recognizedCount", len(recognized_public))),
        "unknownIds": face_summary.get("unknownIds", []),
        "unknownCount": int(face_summary.get("unknownCount", 0)),
        "unknownDetails": face_summary.get("unknownDetails", []),
        "observations": observations_public,
    }


def _emit_face_audit_events(
    *,
    face_summary: Dict[str, object],
    camera_id: str,
    dedupe_cache: Dict[str, float],
    alert_id: Optional[str] = None,
) -> None:
    if not face_engine.config.recognition_audit_enabled:
        return

    now = time.time()
    cooldown = max(1, int(face_engine.config.recognition_audit_cooldown_sec))
    identity_enabled = bool(face_summary.get("identityLabelingEnabled", True))
    frame_index = int(face_summary.get("frameIndex", 0))

    recognized = face_summary.get("recognized", [])
    if isinstance(recognized, list):
        for idx, person in enumerate(recognized):
            if not isinstance(person, dict):
                continue
            person_key = str(person.get("personId", "")).strip() or f"known-{idx + 1}"
            dedupe_key = f"known:{person_key}"
            last_seen_at = dedupe_cache.get(dedupe_key, 0.0)
            if now - last_seen_at < cooldown:
                continue
            dedupe_cache[dedupe_key] = now

            details = {
                "cameraId": camera_id,
                "frameIndex": frame_index,
                "confidence": float(person.get("confidence", 0.0)),
                "identityLabelingEnabled": identity_enabled,
            }
            if identity_enabled:
                details["personId"] = person_key
                details["label"] = str(person.get("label", "")).strip()
            else:
                details["masked"] = True

            audit_logger.record(
                "face_known_seen",
                "success",
                role="system",
                alert_id=alert_id,
                details=details,
            )

    unknown_ids = face_summary.get("unknownIds", [])
    if isinstance(unknown_ids, list):
        for raw_unknown_id in unknown_ids:
            unknown_id = str(raw_unknown_id).strip()
            if not unknown_id:
                continue
            dedupe_key = f"unknown:{unknown_id}"
            last_seen_at = dedupe_cache.get(dedupe_key, 0.0)
            if now - last_seen_at < cooldown:
                continue
            dedupe_cache[dedupe_key] = now
            audit_logger.record(
                "face_unknown_seen",
                "success",
                role="system",
                alert_id=alert_id,
                details={
                    "cameraId": camera_id,
                    "frameIndex": frame_index,
                    "unknownId": unknown_id,
                },
            )

    prune_before = now - (cooldown * 4.0)
    stale_keys = [k for k, ts in dedupe_cache.items() if ts < prune_before]
    for key in stale_keys:
        dedupe_cache.pop(key, None)


import concurrent.futures

def _run_ai_task(pipeline, face_engine, frame, previous_raw_frame):
    clean_frame = pipeline.process_frame(frame)
    face_summary = face_engine.analyze_frame(frame)
    motion_score = _estimate_motion_score(previous_raw_frame, frame)
    return face_summary, motion_score

def _is_live_source(source: Union[str, int]) -> bool:
    """Returns True if source is a live webcam (integer index), False if it's a file."""
    return isinstance(source, int)


def _open_capture(source: Union[str, int]) -> cv2.VideoCapture:
    """Open a VideoCapture with optimal settings based on source type.

    - Integer source  → USB/webcam device (low-latency buffer settings)
    - rtsp:// string  → IP camera over RTSP (uses FFMPEG backend, zero-latency flags)
    - Other string    → local video file (no special settings needed)
    """
    is_rtsp = isinstance(source, str) and source.lower().startswith("rtsp://")

    if is_rtsp:
        # Set FFMPEG capture options for minimum latency BEFORE opening.
        # nobuffer       – skip internal FFMPEG demuxer buffer
        # rtsp_transport – use TCP (more reliable, avoids UDP reordering/drops)
        # max_delay=0    – no extra decode delay
        # analyzeduration/probesize – skip long stream probing on open
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;tcp|"
            "fflags;nobuffer|"
            "flags;low_delay|"
            "max_delay;0|"
            "analyzeduration;100000|"
            "probesize;50000"
        )
        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
            print(f"[System] RTSP camera opened (low-latency): {source} @ {w}x{h} {fps:.0f}fps")
        else:
            print(f"[System] WARNING: Could not open RTSP stream: {source}")
    elif _is_live_source(source):
        cap = cv2.VideoCapture(source)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)
            print(f"[System] USB camera opened: device {source} @ "
                  f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
                  f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} "
                  f"{cap.get(cv2.CAP_PROP_FPS):.0f}fps")
    else:
        cap = cv2.VideoCapture(source)

    return cap


def _drain_to_latest(cap: cv2.VideoCapture, max_drain: int = 8) -> Tuple[bool, Optional[np.ndarray]]:
    """Drain stale RTSP frames and return only the newest one.

    For live cameras the decoder buffer fills up between AI inference calls.
    Calling cap.grab() (no decode) in a tight loop drops all queued frames,
    then cap.retrieve() decodes just the freshest one.  This keeps latency
    near zero without a background thread (and avoids libavcodec thread-safety
    issues on Windows).
    """
    ret = False
    for _ in range(max_drain):
        ret = cap.grab()
        if not ret:
            break
    if not ret:
        return False, None
    ret, frame = cap.retrieve()
    return ret, frame


def camera_worker(
    camera_id: str,
    source: Union[str, int],
    device: torch.device,
    model_weights: str,
    threshold: float,
    stride: int
):

    print(f"[{camera_id}] AI Engine initializing on {device.type.upper()}...")
    
    pipeline = ViolenceInferencePipeline(model_weights, device, threshold, stride)
    state.register_pipeline(pipeline)
    local_face_engine = FaceIntelEngine.from_settings(config, os.environ, BASE_DIR)
    state.running = True
    
    ai_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    ai_future = None
    _live_reconnect_attempts = 0
    _MAX_RECONNECT = 10

    while state.running:
        t0 = time.perf_counter()

        # --- Frame acquisition -------------------------------------------------
        # For live/RTSP sources drain stale buffered frames first so the AI
        # always processes the newest frame (eliminates buffer-buildup latency).
        # For video files use sequential cap.read() to preserve playback order.
        if _is_rtsp_source(current_source) or _is_live_source(current_source):
            ret, raw = _drain_to_latest(cap)
        else:
            ret, raw = cap.read()
        # -----------------------------------------------------------------------

        if not ret:
            is_rtsp = isinstance(current_source, str) and current_source.lower().startswith("rtsp://")
            if _is_live_source(current_source) or _is_rtsp_source(current_source):
                # Live source (USB webcam or RTSP IP camera) — attempt reconnect
                _live_reconnect_attempts += 1
                print(f"[System] Live camera lost. Reconnect attempt {_live_reconnect_attempts}/{_MAX_RECONNECT}...")
                cap.release()
                time.sleep(2.0)
                cap = _open_capture(current_source)
                if cap.isOpened():
                    src_fps, width, height = _read_cap_props(cap)
                    _live_reconnect_attempts = 0
                    print("[System] Live camera reconnected.")
                elif _live_reconnect_attempts >= _MAX_RECONNECT:
                    print("[System] Live camera unavailable. Waiting...")
                    time.sleep(5.0)
                    _live_reconnect_attempts = 0
            else:
                # Video file — loop back to beginning
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                pipeline.reset()
            continue
        
        _live_reconnect_attempts = 0

        still_active = []
        for entry in active_post_queues:
            if entry[1] > 0:
                try: 
                    entry[0].put_nowait(raw.copy())
                except queue.Full: 
                    pass
                entry[1] -= 1
                still_active.append(entry)
        active_post_queues = still_active

        ring.append(raw.copy())

        if ai_future is None or ai_future.done():
            if ai_future is not None:
                try:
                    face_summary, motion_score = ai_future.result()
                    state.store_face_summary(face_summary)
                    cam_id = camera_id
                    _emit_face_audit_events(
                        face_summary=face_summary,
                        camera_id=cam_id,
                        dedupe_cache=face_audit_dedupe,
                    )
                    client_face_summary = _public_face_summary(face_summary)

                    now = time.time()
                    current_cooldown = state.get_cooldown()
                    
                    if pipeline._last_label == VIOLENCE_CLS and (now - last_alert_time > current_cooldown):
                        last_alert_time = now
                        alert_id = f"alert-{int(now * 1000)}"
                        conf = pipeline._last_conf

                        severity = "critical" if conf >= 0.85 else "high" if conf >= 0.65 else "medium"
                        fusion = fusion_engine.assess(
                            violence_confidence=conf,
                            motion_score=motion_score,
                            weapon_score=0.0,
                            base_severity=severity,
                        )
                        severity = fusion["severity"]

                        alert_payload = {
                            "id": alert_id, 
                            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                            "isoTime": datetime.now(timezone.utc).isoformat(), 
                            "confidence": round(conf * 100, 1),
                            "type": "Violence", 
                            "severity": severity,
                            "cameraId": cam_id, 
                            "location": str(CAMERA_SOURCES.get(cam_id, cam_id)),
                            "fusionScore": fusion["score"],
                            "fusionModel": fusion["model"],
                            "motionScore": fusion["motionScore"],
                            "weaponScore": fusion["weaponScore"],
                            "fusionReason": fusion["reason"],
                            "faceSummary": client_face_summary,
                        }

                        state.register_alert(alert_payload)
                        state.broadcast_alert(alert_payload)
                        audit_logger.record(
                            "alert_detected",
                            "success",
                            role="system",
                            alert_id=alert_id,
                            details={
                                "cameraId": cam_id,
                                "severity": severity,
                                "confidence": round(conf * 100, 1),
                                "fusionScore": fusion["score"],
                                "faceTotal": int(face_summary.get("totalFaces", 0)),
                                "faceKnown": int(face_summary.get("recognizedCount", 0)),
                                "faceUnknown": int(face_summary.get("unknownCount", 0)),
                                "identityLabelingEnabled": bool(face_summary.get("identityLabelingEnabled", True)),
                            },
                        )
                        _emit_face_audit_events(
                            face_summary=face_summary,
                            camera_id=cam_id,
                            dedupe_cache=face_audit_dedupe,
                            alert_id=alert_id,
                        )

                        pre_frames = list(ring)
                        post_q = queue.Queue(maxsize=POST_ALERT_LEN + 32)
                        active_post_queues.append([post_q, POST_ALERT_LEN])
                        threading.Thread(
                            target=_write_evidence_clip, 
                            args=(alert_id, pre_frames, post_q, src_fps, width, height), 
                            daemon=True
                        ).start()

                        if GROQ_ENABLED and pre_frames:
                            threading.Thread(
                                target=_call_vlm_forensics, 
                                args=(alert_id, pre_frames[-1].copy()), 
                                daemon=True
                            ).start()

                        if pre_frames:
                            snapshot_bytes = _encode_snapshot(pre_frames[-1].copy())
                            if snapshot_bytes:
                                snapshot_path = THUMBNAILS_DIR / f"{alert_id}.jpg"
                                snapshot_path.write_bytes(snapshot_bytes)
                                state.store_snapshot_path(alert_id, str(snapshot_path))
                            telegram_notifier.enqueue_alert(alert_payload, snapshot_bytes)
                except Exception as exc:
                    print(f"[System] AI worker encountered an error: {exc}")

            ai_future = ai_executor.submit(_run_ai_task, pipeline, local_face_engine, raw.copy(), previous_raw_frame)
            previous_raw_frame = raw.copy()

        # MJPEG stream uses the raw frame to prevent blocking
        ok, jpg_buf = cv2.imencode(".jpg", raw, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok: 
            state.set_frame(camera_id, jpg_buf.tobytes())



        time.sleep(max(0, (1.0 / TARGET_FPS) - (time.perf_counter() - t0)))

    ai_executor.shutdown(wait=False)
    cap.release()

# ─────────────────────────────────────────────────────────────────────────────
# 6. FastAPI Setup & Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    telegram_notifier.start()
    threads = []
    state.running = True
    if CAPTURE_LOOP_ENABLED:
        # Determine active cameras
        active_ids = []
        env_active = os.getenv("ACTIVE_CAMERAS")
        if env_active:
            active_ids = [cid.strip() for cid in env_active.split(",") if cid.strip()]
        else:
            active_ids = list(CAMERA_SOURCES.keys())
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        for cam_id in active_ids:
            if cam_id not in CAMERA_SOURCES:
                print(f"[System] Warning: camera '{cam_id}' not in CAMERA_SOURCES, skipping.")
                continue
            source = CAMERA_SOURCES[cam_id]
            t = threading.Thread(
                target=camera_worker,
                args=(cam_id, source, device, WEIGHTS_PATH, THRESHOLD, STRIDE),
                daemon=True
            )
            t.start()
            threads.append(t)
    else:
        print("[System] Capture loop disabled via AI_SENTINEL_ENABLE_CAPTURE_LOOP.")
    yield
    state.running = False
    for t in threads:
        t.join(timeout=5)
    telegram_notifier.stop()

app = FastAPI(lifespan=lifespan, title="AI Sentinel Advanced Backend")
app.add_middleware(
    CORSMiddleware, 
    allow_origins=config['server']['cors_origins'], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

async def _mjpeg_generator(camera_id: str) -> AsyncGenerator[bytes, None]:
    boundary = b"--frame\r\n"
    while True:
        jpg = state.get_frame(camera_id)
        if jpg:
            yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
        await asyncio.sleep(1 / TARGET_FPS)

async def _sse_generator(q: queue.Queue) -> AsyncGenerator[bytes, None]:
    try:
        last_ping = time.time()
        while True:
            while True:
                try: 
                    yield f"data: {q.get_nowait()}\n\n".encode()
                except queue.Empty: 
                    break
            if time.time() - last_ping > 15: 
                yield b": ping\n\n"
                last_ping = time.time()
            await asyncio.sleep(0.1)
    except asyncio.CancelledError: 
        pass
    finally: 
        state.unsubscribe(q)

@app.get("/video_feed", summary="MJPEG Video Stream")
async def video_feed(camera_id: str = DEFAULT_CAMERA_ID):
    return StreamingResponse(_mjpeg_generator(camera_id), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/cameras/status", summary="Camera status list")
async def cameras_status():
    """Return status for all configured cameras."""
    statuses = []
    for cam_id, source in CAMERA_SOURCES.items():
        cam_status = state.get_camera_status(cam_id)
        cam_status["source"] = str(source)
        last_ts = cam_status.get("lastFrameTimestamp")
        cam_status["running"] = (time.time() - last_ts) < 5.0 if last_ts is not None else False
        statuses.append(cam_status)
    return {"cameras": statuses}

@app.get("/alerts", summary="SSE Event Stream")
async def alerts():
    return StreamingResponse(_sse_generator(state.subscribe()), media_type="text/event-stream")


@app.get("/notifications/status", summary="Notification subsystem status")
async def notifications_status():
    return {
        "telegram": telegram_notifier.status(),
    }


@app.post("/notifications/telegram/test", summary="Send a Telegram test alert")
async def test_telegram_notification(request: Request):
    role = security_controller.authorize(request, required_role="admin")
    if not telegram_notifier.config.ready:
        raise HTTPException(status_code=503, detail="Telegram notifications are not configured")

    test_alert = {
        "id": f"test-{int(time.time() * 1000)}",
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "isoTime": datetime.now(timezone.utc).isoformat(),
        "confidence": 100.0,
        "type": "Telegram Test",
        "severity": "high",
        "cameraId": DEFAULT_CAMERA_ID,
        "location": "Test channel",
    }
    snapshot = state.get_frame(DEFAULT_CAMERA_ID)
    telegram_notifier.enqueue_alert(test_alert, snapshot)
    audit_logger.record("telegram_test", "queued", role=role, alert_id=test_alert["id"], details={"cameraId": test_alert["cameraId"]})
    return {"status": "queued", "telegram": telegram_notifier.status()}


@app.get("/get_report/{alert_id}", summary="Get VLM forensic report text for an alert")
async def get_report(alert_id: str):
    """Returns the Groq-generated report text for a given alert. Returns status=pending if not ready yet."""
    report_text = state.get_report_text(alert_id)
    if report_text is None:
        return {"status": "pending", "report": None}
    return {"status": "ready", "report": report_text}


@app.get("/download_report/{alert_id}", summary="Fetch forensic PDF report")
async def download_report(alert_id: str, request: Request):
    role = security_controller.authorize(request, required_role="viewer")
    alert = state.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Incident not found")

    report_text = state.get_report_text(alert_id) or "Visual analysis is still pending."
    snapshot_path = state.get_snapshot_path(alert_id)
    evidence_path = EVIDENCE_DIR / f"{alert_id}.mp4"
    output_path = REPORTS_DIR / f"{alert_id}.pdf"

    build_incident_pdf(
        alert=alert,
        report_text=report_text,
        snapshot_path=snapshot_path,
        evidence_path=evidence_path if evidence_path.exists() else None,
        output_path=output_path,
    )
    evidence_ledger.append_entry(
        alert=alert,
        clip_path=evidence_path if evidence_path.exists() else None,
        snapshot_path=snapshot_path,
        report_path=output_path,
        report_text=report_text,
    )
    audit_logger.record(
        "report_download",
        "success",
        role=role,
        alert_id=alert_id,
        details={"path": str(output_path)},
    )

    return FileResponse(
        str(output_path),
        media_type="application/pdf",
        filename=f"{alert_id}.pdf",
    )

@app.post("/switch_camera", summary="Change active camera stream (deprecated)")
async def switch_camera(body: CameraRequest, request: Request):
    raise HTTPException(status_code=410, detail="This endpoint is deprecated in multi-camera mode. Configure ACTIVE_CAMERAS environment variable to select cameras.")

@app.post("/set_threshold", summary="Update model confidence threshold")
async def set_threshold(body: ThresholdRequest, request: Request):
    role = security_controller.authorize(request, required_role="admin")
    new_thresh = state.set_threshold(body.threshold)
    audit_logger.record("set_threshold", "success", role=role, details={"threshold": new_thresh})
    return {"status": "success", "threshold": new_thresh}

@app.post("/set_cooldown", summary="Update time between consecutive alerts")
async def set_cooldown(body: CooldownRequest, request: Request):
    role = security_controller.authorize(request, required_role="admin")
    new_cooldown = state.set_cooldown(body.cooldown)
    audit_logger.record("set_cooldown", "success", role=role, details={"cooldown": new_cooldown})
    return {"status": "success", "cooldown": new_cooldown}

@app.get("/download_evidence/{alert_id}", summary="Fetch recorded DVR clip")
async def download_evidence(alert_id: str, request: Request):
    role = security_controller.authorize(request, required_role="viewer")
    status = state.get_evidence_status(alert_id)
    if not status:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if status == "writing":
        raise HTTPException(status_code=202, detail="Compiling video, try again shortly")
    if status == "error":
        raise HTTPException(status_code=500, detail="Server failed to compile evidence")
    audit_logger.record("evidence_download", "success", role=role, alert_id=alert_id)

    return FileResponse(
        str(EVIDENCE_DIR / f"{alert_id}.mp4"), 
        media_type="video/mp4", 
        filename=f"{alert_id}.mp4"
    )


@app.get("/security/status", summary="Access control status")
async def security_status():
    return security_controller.status()


@app.get("/audit/status", summary="Audit log status")
async def audit_status():
    return audit_logger.status()


@app.get("/audit/recent", summary="Recent audit events")
async def audit_recent(limit: int = 20):
    return {"items": audit_logger.recent(limit=max(1, min(limit, 100)))}


@app.get("/evidence_chain/{alert_id}", summary="Evidence ledger entry")
async def evidence_chain(alert_id: str, request: Request):
    security_controller.authorize(request, required_role="viewer")
    record = evidence_ledger.get(alert_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evidence chain entry not found")
    return record


@app.post("/audio/analyze", summary="Analyze audio clip for distress cues")
async def analyze_audio(body: AudioAnalysisRequest, request: Request):
    role = security_controller.authorize(request, required_role="viewer")
    result = audio_analyzer.analyze_base64_wav(body.audio_base64)
    audit_logger.record(
        "audio_analyze",
        "success" if result.get("detected") else "ok",
        role=role,
        details={"filename": body.filename, "score": result.get("score", 0.0)},
    )
    return result


@app.get("/audio/status", summary="Audio analysis status")
async def audio_status():
    return audio_analyzer.status()


@app.get("/face/status", summary="Face intelligence status")
async def face_status():
    return face_engine.status()


@app.get("/face/policy", summary="Get face identity/audit policy")
async def face_policy_get(request: Request):
    security_controller.authorize(request, required_role="viewer")
    status = face_engine.status()
    policy = status.get("policy", {})
    policy_fetched_at = datetime.now(timezone.utc).isoformat()
    return {
        "status": "success",
        "policy": policy,
        "policyFetchedAt": policy_fetched_at,
    }


@app.post("/face/policy", summary="Update face identity/audit policy")
async def face_policy_update(body: FacePolicyRequest, request: Request):
    role = security_controller.authorize(request, required_role="admin")
    updates = {}

    if body.identity_labeling_enabled is not None:
        updates["identityLabelingEnabled"] = face_engine.set_identity_labeling_enabled(body.identity_labeling_enabled)
    if body.recognition_audit_enabled is not None:
        updates["recognitionAuditEnabled"] = face_engine.set_recognition_audit_enabled(body.recognition_audit_enabled)
    if body.recognition_audit_cooldown_sec is not None:
        updates["recognitionAuditCooldownSec"] = face_engine.set_recognition_audit_cooldown_sec(body.recognition_audit_cooldown_sec)

    if not updates:
        raise HTTPException(status_code=400, detail="No policy field provided")

    audit_logger.record(
        "face_policy_update",
        "success",
        role=role,
        details=updates,
    )
    return {
        "status": "success",
        "updates": updates,
        "face": face_engine.status(),
    }


@app.post("/face/policy/reload", summary="Reload face policy overrides from disk")
async def face_policy_reload(request: Request):
    role = security_controller.authorize(request, required_role="admin")
    status = face_engine.reload_policy_overrides()
    policy = status.get("policy", {})
    audit_logger.record(
        "face_policy_reload",
        "success",
        role=role,
        details={
            "identityLabelingEnabled": policy.get("identityLabelingEnabled"),
            "recognitionAuditEnabled": policy.get("recognitionAuditEnabled"),
            "recognitionAuditCooldownSec": policy.get("recognitionAuditCooldownSec"),
        },
    )
    return {
        "status": "success",
        "policy": policy,
        "face": status,
    }


@app.get("/face/registry", summary="List known people registry")
async def face_registry(request: Request, include_embeddings: bool = False):
    security_controller.authorize(request, required_role="viewer")
    return {"items": face_engine.list_known_people(include_embeddings=include_embeddings)}


@app.get("/face/registry/{person_id}", summary="Get known person profile")
async def face_registry_get(person_id: str, request: Request, include_embeddings: bool = False):
    security_controller.authorize(request, required_role="viewer")
    person = face_engine.get_known_person(person_id, include_embeddings=include_embeddings)
    if not person:
        raise HTTPException(status_code=404, detail="Known person not found")
    return person


@app.put("/face/registry/{person_id}", summary="Create or update known person")
async def face_registry_upsert(person_id: str, body: FacePersonUpdateRequest, request: Request):
    role = security_controller.authorize(request, required_role="admin")
    try:
        person = face_engine.upsert_known_person(
            person_id=person_id,
            display_name=body.display_name,
            role=body.role or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audit_logger.record(
        "face_registry_upsert",
        "success",
        role=role,
        details={"personId": person.get("personId")},
    )
    return {"status": "success", "person": person}


@app.delete("/face/registry/{person_id}", summary="Delete known person")
async def face_registry_delete(person_id: str, request: Request):
    role = security_controller.authorize(request, required_role="admin")
    deleted = face_engine.delete_known_person(person_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Known person not found")
    audit_logger.record("face_registry_delete", "success", role=role, details={"personId": person_id})
    return {"status": "success", "personId": person_id}


@app.delete("/face/registry/{person_id}/embeddings", summary="Clear known person embeddings")
async def face_registry_clear_embeddings(person_id: str, request: Request):
    role = security_controller.authorize(request, required_role="admin")
    cleared = face_engine.clear_person_embeddings(person_id)
    if not cleared:
        raise HTTPException(status_code=404, detail="Known person not found")
    audit_logger.record(
        "face_registry_clear_embeddings",
        "success",
        role=role,
        details={"personId": person_id},
    )
    return {"status": "success", "personId": person_id}


@app.post("/face/registry/{person_id}/enroll", summary="Enroll known person from image base64")
async def face_registry_enroll(person_id: str, body: FaceEnrollRequest, request: Request):
    role = security_controller.authorize(request, required_role="admin")
    try:
        person = face_engine.enroll_person_from_base64(
            person_id=person_id,
            image_base64=body.image_base64,
            display_name=body.display_name or "",
            role=body.role or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Enrollment failed: {exc}")

    audit_logger.record(
        "face_registry_enroll",
        "success",
        role=role,
        details={
            "personId": person.get("personId"),
            "embeddingCount": person.get("embeddingCount", 0),
        },
    )
    return {"status": "success", "person": person}


@app.post("/face/session/reset", summary="Reset face unknown-id session")
async def face_session_reset(request: Request):
    role = security_controller.authorize(request, required_role="admin")
    face_engine.reset_session(reason=f"manual-reset-by-{role}")
    audit_logger.record("face_session_reset", "success", role=role)
    return {"status": "success", "face": face_engine.status()}


@app.get("/system/status", summary="Combined system status")
async def system_status():
    return {
        "health": "ok",
        "model": {
            "threshold": state.get_threshold(),
            "cooldown": state.get_cooldown(),
            "device": "cuda" if torch.cuda.is_available() else "cpu",
        },
        "notifications": telegram_notifier.status(),
        "fusion": {
            "enabled": fusion_engine.config.enabled,
            "weights": {
                "violence": fusion_engine.config.violence_weight,
                "motion": fusion_engine.config.motion_weight,
                "weapon": fusion_engine.config.weapon_weight,
            },
        },
        "security": security_controller.status(),
        "audit": audit_logger.status(),
        "audio": audio_analyzer.status(),
        "face": face_engine.status(),
        "storage": {
            "evidence": str(EVIDENCE_DIR),
            "thumbnails": str(THUMBNAILS_DIR),
            "reports": str(REPORTS_DIR),
        },
    }


@app.get("/health", summary="Health check")
async def health():
    return await system_status()
