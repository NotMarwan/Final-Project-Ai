from __future__ import annotations

import asyncio
import json
import os
import time
import threading
import queue
import multiprocessing as mp
import base64
import re
import yaml
from dotenv import load_dotenv
from collections import deque
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Dict, Optional, Tuple, Union

import cv2
import numpy as np
# import torch deferred to functions
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent

try:
    from .live_alert_decision import LiveAlertDecisionLayer
except ImportError:
    from live_alert_decision import LiveAlertDecisionLayer

try:
    from .person_detector import PersonDetector
    from .visual_annotator import annotate as annotate_frame
except ImportError:
    from person_detector import PersonDetector
    from visual_annotator import annotate as annotate_frame

try:
    from .go2rtc_bridge import Go2RTCBridge
except ImportError:
    from go2rtc_bridge import Go2RTCBridge

def _is_torch_cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False

# Heavy imports moved inside functions
def _get_imports():
    try:
        from .inference import ViolenceInferencePipeline, VIOLENCE_CLS
        from .fusion import ThreatFusionEngine
        from .weapon import WeaponSignalEngine
        from .calibration_utils import load_calibration_profile
        from .security import AccessController, AuditLogger
        from .evidence import EvidenceLedger
        from .audio import AudioRiskAnalyzer
        from .notifications import TelegramNotifier
        from .reporting import build_incident_pdf
        from .live_alert_decision import LiveAlertDecisionLayer
    except ImportError:
        from inference import ViolenceInferencePipeline, VIOLENCE_CLS
        from fusion import ThreatFusionEngine
        from weapon import WeaponSignalEngine
        from calibration_utils import load_calibration_profile
        from security import AccessController, AuditLogger
        from evidence import EvidenceLedger
        from audio import AudioRiskAnalyzer
        from notifications import TelegramNotifier
        from reporting import build_incident_pdf
        from live_alert_decision import LiveAlertDecisionLayer
    return locals()

try:
    from .detection_categories import (
        CategoryDetector, 
        DetectionCategory, 
        CategoryConfig, 
        DetectionContext,
        parse_detection_context
    )
except ImportError:
    from detection_categories import (
        CategoryDetector, 
        DetectionCategory, 
        CategoryConfig, 
        DetectionContext,
        parse_detection_context
    )

# Initialize category detector
category_detector = None
def _init_category_detector():
    global category_detector
    if category_detector is not None:
        return
    cat_config = CategoryConfig.from_settings(config)
    category_detector = CategoryDetector(cat_config, weapon_engine=weapon_engine)
    print(f"[System] Category detector initialized with: {[c.value for c in category_detector.enabled_categories]}")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Configuration & Environment Setup
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv(override=True)

with open(BASE_DIR / "config.yml", "r") as f:
    config = yaml.safe_load(f)

CALIBRATION_PROFILE = None
VIOLENCE_CLS = None

def _init_config_and_profiles():
    global CALIBRATION_PROFILE, VIOLENCE_CLS
    if CALIBRATION_PROFILE is not None:
        return
    imports = _get_imports()
    CALIBRATION_PROFILE = imports['load_calibration_profile'](base_dir=BASE_DIR)
    VIOLENCE_CLS = imports['VIOLENCE_CLS']

def _parse_source(raw: str) -> Union[str, int]:
    try:
        return int(raw)
    except ValueError:
        return raw


def _looks_like_stream_url(raw: str) -> bool:
    text = raw.strip().lower()
    return text.startswith(("rtsp://", "http://", "https://", "rtmp://", "udp://", "tcp://"))


def _normalize_camera_source(source: Union[str, int], base_dir: Path) -> Union[str, int]:
    if isinstance(source, int):
        return source

    text = str(source).strip()
    parsed = _parse_source(text)
    if isinstance(parsed, int):
        return parsed
    if _looks_like_stream_url(text):
        return text

    path = Path(text)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return str(path)

def _resolve_profiles_path() -> Path:
    raw = os.getenv("CAMERA_PROFILES_PATH", "camera_profiles.yml")
    path = Path(raw)
    return path if path.is_absolute() else BASE_DIR / path


def _resolve_backend_path(raw_path: str) -> str:
    path = Path(raw_path)
    return str(path if path.is_absolute() else BASE_DIR / path)


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
            loaded[camera_id] = _normalize_camera_source(source, path.parent)
    return loaded


def _default_camera_sources() -> Dict[str, Union[str, int]]:
    return {
        "CAM-01": _normalize_camera_source(os.getenv("CAM1_SOURCE", "cam1.mp4"), BASE_DIR),
        "CAM-02": _normalize_camera_source(os.getenv("CAM2_SOURCE", "cam2.mp4"), BASE_DIR),
    }


def _load_camera_sources() -> Dict[str, Union[str, int]]:
    profile_path = _resolve_profiles_path()
    if profile_path.exists():
        profile_sources = _load_profile_camera_sources(profile_path)
        print(f"[System] Profile found at {profile_path}. Active cameras: {len(profile_sources)}")
        if profile_sources:
            return profile_sources
        print("[System] Profile has no active cameras. Falling back to environment/default sources.")
    print("[System] No camera_profiles.yml found. Using environment/default sources.")
    return _default_camera_sources()


CAMERA_SOURCES: Dict[str, Union[str, int]] = _load_camera_sources()
DEFAULT_CAMERA_ID = os.getenv("DEFAULT_CAMERA_ID", next(iter(CAMERA_SOURCES), "CAM-01"))
if DEFAULT_CAMERA_ID not in CAMERA_SOURCES and CAMERA_SOURCES:
    DEFAULT_CAMERA_ID = next(iter(CAMERA_SOURCES))

# Demo/example clips — NOT auto-started at boot; only analyzed when user selects them
def _load_example_sources() -> Dict[str, str]:
    _project_root = BASE_DIR.parent
    return {
        "EXAMPLE-01": str(_project_root / "test" / "Wq0BuA8GM84_0.avi"),
        "EXAMPLE-02": str(_project_root / "test" / "YDOJvzChqSg_0 (1).avi"),
        "EXAMPLE-03": str(_project_root / "unrelated" / "archived-projects" / "violence" / "FXC43fACfPc_0.avi"),
    }

EXAMPLE_SOURCES: Dict[str, str] = _load_example_sources()

# Initialize these lazily too
WEIGHTS_PATH = _resolve_backend_path(os.getenv("WEIGHTS_PATH", "best_model.pt"))
THRESHOLD = 0.0
STRIDE = 0

def _finalize_config():
    global THRESHOLD, STRIDE
    if THRESHOLD != 0.0:
        return
    THRESHOLD = float(os.getenv("THRESHOLD", str(CALIBRATION_PROFILE.get("threshold", config['model']['confidence_threshold']))))
    STRIDE = int(os.getenv("STRIDE", str(config['model']['stride'])))

JPEG_QUALITY_PRESETS = {"low": 50, "medium": 75, "high": 90}
JPEG_QUALITY = JPEG_QUALITY_PRESETS.get(os.getenv("STREAM_QUALITY", "medium").lower(), 75)
TARGET_FPS     = 25
RING_BUFFER_LEN = 140   # ~7s pre-alert buffer at 20fps target
POST_ALERT_LEN  = 160   # ~8s post-alert capture at 20fps (20s at 8fps real)
_FILE_SKIP_FRAMES = int(os.getenv("AI_SENTINEL_FILE_SKIP", "0"))


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

try:
    from .openrouter_reporting import DeepSeekReportService
except ImportError:
    from openrouter_reporting import DeepSeekReportService

deepseek_service = DeepSeekReportService(cache_dir=REPORTS_DIR)

# ── Groq Vision-Language Model Setup ──
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ENABLED = bool(GROQ_API_KEY)
_groq_client = None
telegram_notifier = None
fusion_engine = None
weapon_engine = None
security_controller = None
audit_logger = None
evidence_ledger = None
audio_analyzer = None
go2rtc_bridge: Go2RTCBridge | None = None
_webrtc_manager = None

def _init_engines():
    global telegram_notifier, fusion_engine, weapon_engine, security_controller
    global audit_logger, evidence_ledger, audio_analyzer
    
    if telegram_notifier is not None:
        print("[Engines] Already initialized.")
        return
        
    print("[Engines] Importing dependencies...")
    imports = _get_imports()
    print("[Engines] Dependencies imported.")
    
    telegram_notifier = imports['TelegramNotifier'].from_settings(config, os.environ)
    fusion_engine = imports['ThreatFusionEngine'].from_settings(config)
    weapon_engine = imports['WeaponSignalEngine'].from_settings(config, os.environ)
    security_controller = imports['AccessController'].from_settings(config, os.environ)
    audit_logger = imports['AuditLogger'].from_settings(config, BASE_DIR)
    evidence_ledger = imports['EvidenceLedger'].from_settings(config, BASE_DIR)
    audio_analyzer = imports['AudioRiskAnalyzer'].from_settings(config)
    global go2rtc_bridge
    go2rtc_bridge = Go2RTCBridge(config, os.environ)
    go2rtc_bridge.start()
CAPTURE_LOOP_ENABLED = _env_flag("AI_SENTINEL_ENABLE_CAPTURE_LOOP", default=True)

if GROQ_ENABLED:
    try:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
        print("[System] Groq initialized successfully.")
    except Exception as exc:
        print(f"[System] Failed to initialize Groq VLM: {exc}")
        GROQ_ENABLED = False

_VLM_PROMPT = (
    "تصرف كخبير أمني. قم بوصف حادثة العنف في هذا الإطار من كاميرا المراقبة "
    "بفقرة واحدة قصيرة واحترافية باللغة العربية. ركز على عدد الأشخاص، "
    "الأفعال الجسدية، والأسلحة المحتملة إن وجدت."
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


class AnalyzeRequest(BaseModel):
    category: str
    context: dict

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

        # Camera statistics
        self._cam_stats_lock = threading.Lock()
        self._camera_heartbeats: Dict[str, float] = {}
        self._camera_alert_counts: Dict[str, int] = {}

        # Per-camera detection metadata for frontend overlay rendering
        self._detection_meta_lock = threading.Lock()
        self._detection_meta: Dict[str, dict] = {}
        
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

        self._decision_lock = threading.Lock()
        self._decision_layer = LiveAlertDecisionLayer()

        # Per-worker stop events for on-demand (example/demo) camera workers
        self._worker_stop_lock = threading.Lock()
        self._worker_stop_events: Dict[str, threading.Event] = {}

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

    def broadcast_person_data(self, camera_id: str, person_count: int, track_ids: list[str], is_threat: bool, video_width: int = 0, video_height: int = 0):
        payload = {
            "type": "person_detection",
            "cameraId": camera_id,
            "personCount": person_count,
            "trackIds": track_ids,
            "isThreat": is_threat,
            "videoWidth": video_width,
            "videoHeight": video_height,
        }
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

    def get_all_alerts(self) -> list:
        with self._alert_lock:
            return [dict(a) for a in self._alerts.values()]

    def update_alert(self, alert_id: str, updates: Dict[str, object]) -> Optional[dict]:
        if not alert_id:
            return None
        with self._alert_lock:
            existing = self._alerts.get(alert_id)
            if not existing:
                return None
            merged = dict(existing)
            merged.update(updates)
            self._alerts[alert_id] = merged
            return dict(merged)

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

    def update_decision_layer(
        self,
        calibrated_probability: float,
        sample_time: Optional[float] = None,
    ) -> Dict[str, object]:
        with self._decision_lock:
            return dict(self._decision_layer.update(calibrated_probability, sample_time=sample_time))

    def reset_decision_layer(self) -> Dict[str, object]:
        with self._decision_lock:
            self._decision_layer.reset()
            return self._decision_layer_status_locked()

    def get_decision_layer_status(self) -> Dict[str, object]:
        with self._decision_lock:
            return self._decision_layer_status_locked()

    def _decision_layer_status_locked(self) -> Dict[str, object]:
        return dict(self._decision_layer.status())

    def create_worker_stop_event(self, camera_id: str) -> threading.Event:
        ev = threading.Event()
        with self._worker_stop_lock:
            # Stop any existing event for this camera_id before replacing
            old = self._worker_stop_events.get(camera_id)
            if old:
                old.set()
            self._worker_stop_events[camera_id] = ev
        return ev

    def stop_worker(self, camera_id: str) -> bool:
        with self._worker_stop_lock:
            ev = self._worker_stop_events.pop(camera_id, None)
        if ev:
            ev.set()
            return True
        return False

    def is_demo_worker_running(self, camera_id: str) -> bool:
        with self._worker_stop_lock:
            ev = self._worker_stop_events.get(camera_id)
        return ev is not None and not ev.is_set()

    def set_detection_meta(self, camera_id: str, meta: dict):
        with self._detection_meta_lock:
            self._detection_meta[camera_id] = dict(meta)

    def get_detection_meta(self, camera_id: str) -> Optional[dict]:
        with self._detection_meta_lock:
            return dict(self._detection_meta.get(camera_id, {}))

state = AppState()

# ─────────────────────────────────────────────────────────────────────────────
# 4. Background Workers (DVR & VLM)
# ─────────────────────────────────────────────────────────────────────────────

def _write_evidence_clip(alert_id: str, pre_frames: list, post_queue: queue.Queue, fps: float, width: int, height: int):
    out_path = EVIDENCE_DIR / f"{alert_id}.mp4"
    state.mark_evidence(alert_id, "writing")
    try:
        # Try H.264 (browser-compatible) first, fall back to MPEG-4 Part 2
        writer = None
        for _codec in ("avc1", "mp4v"):
            _fourcc = cv2.VideoWriter_fourcc(*_codec)
            _w = cv2.VideoWriter(str(out_path), _fourcc, fps, (width, height))
            if _w.isOpened():
                writer = _w
                print(f"[Evidence] Using codec '{_codec}' for {alert_id}")
                break
            _w.release()
        if writer is None:
            raise RuntimeError("No working video codec found (tried avc1, mp4v)")

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
    Forensic reporting function using Groq AI (Llama-4 Scout).
    Generates Arabic incident description for the given frame.
    """
    global _groq_client
    report_text = None
    last_error = ""

    if not GROQ_ENABLED or not _groq_client:
        report_text = "[Forensic module offline. Ensure API key is configured and Groq is installed.]"
    else:
        try:
            ok, jpg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                raise ValueError("JPEG encoding failed")
            base64_image = base64.b64encode(jpg_buf).decode("utf-8")

            response = _groq_client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": _VLM_PROMPT
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=256,
                temperature=0.5,
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
        "report": report_text
    })
    state.store_report_text(alert_id, report_text)
    audit_logger.record(
        "vlm_report_generated",
        "success" if not report_text.startswith("[Forensic analysis failed") else "error",
        role="system",
        alert_id=alert_id,
        details={"chars": len(report_text)},
    )

def _generate_alert_payload(
    alert_id: str,
    pipeline: ViolenceInferencePipeline,
    weapon_score: float,
    weapon_signal: dict,
    motion_score: float,
    cam_id: str,
    now: float,
    t0: float,
    decision_result: Optional[dict] = None,
) -> dict:
    conf = pipeline._last_conf
    model_conf = round(conf * 100, 1)
    raw_model_conf = round(float(getattr(pipeline, "_last_raw_conf", conf)) * 100, 1)
    calibrated_conf = round(float(getattr(pipeline, "_last_calibrated_conf", conf)) * 100, 1)
    raw_probability = round(float(getattr(pipeline, "_last_raw_conf", conf)), 4)
    calibrated_probability = round(float(getattr(pipeline, "_last_calibrated_conf", conf)), 4)
    model_prediction = bool(pipeline._is_violent)
    decision_data = dict(decision_result or state.get_decision_layer_status())
    confirmed_alert = bool(decision_data.get("confirmed_alert", False))
    alert_state = str(decision_data.get("alert_state", "NORMAL"))
    confirm_rule = str(decision_data.get("confirm_rule", ""))
    rolling_history = decision_data.get("rolling_history", [])
    rolling_window_count = int(decision_data.get("rolling_window_count", 0))
    cooldown_remaining_seconds = float(decision_data.get("cooldown_remaining_seconds", 0.0))
    decision_sample_accepted = bool(decision_data.get("decision_sample_accepted", True))
    ignored_reason = decision_data.get("ignored_reason")
    last_decision_sample_time = decision_data.get("last_decision_sample_time")
    min_decision_interval_seconds = float(decision_data.get("min_decision_interval_seconds", 0.5))

    severity = "critical" if conf >= 0.85 else "high" if conf >= 0.65 else "medium"
    fusion = fusion_engine.assess(
        violence_confidence=conf,
        motion_score=motion_score,
        weapon_score=weapon_score,
        base_severity=severity,
    )
    severity = fusion["severity"]
    threat_conf = round(max(model_conf, float(fusion["score"])), 1)
    is_weapon_threat = weapon_score >= weapon_engine.config.independent_alert_threshold
    visible_violence_alert = confirmed_alert
    alert_type = "violence" if visible_violence_alert else "weapon"
    alert_label = "Violence" if visible_violence_alert else "Weapon Detection"
    
    # Base payload
    payload = {
        "id": alert_id,
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "isoTime": datetime.now(timezone.utc).isoformat(),
        "confidence": threat_conf,
        "modelConfidence": model_conf,
        "rawModelConfidence": raw_model_conf,
        "calibratedConfidence": calibrated_conf,
        "threatConfidence": threat_conf,
        "threatType": alert_type,
        "type": alert_label,
        "severity": severity,
        "cameraId": cam_id,
        "location": str(CAMERA_SOURCES.get(cam_id, cam_id)),
        "fusionScore": fusion["score"],
        "fusionModel": fusion["model"],
        "motionScore": fusion["motionScore"],
        "weaponScore": fusion["weaponScore"],
        "weaponLabels": weapon_signal.get("labels", []),
        "weaponDetectorReady": bool(weapon_signal.get("ready", False)),
        "fusionReason": fusion["reason"],
        "alertLatencyMs": round((time.perf_counter() - t0) * 1000, 1),
        "raw_probability": raw_probability,
        "calibrated_probability": calibrated_probability,
        "model_prediction": model_prediction,
        "alert_state": alert_state,
        "confirmed_alert": confirmed_alert,
        "confirm_rule": confirm_rule,
        "rolling_history": rolling_history,
        "rolling_window_count": rolling_window_count,
        "cooldown_remaining_seconds": cooldown_remaining_seconds,
        "decision_sample_accepted": decision_sample_accepted,
        "ignored_reason": ignored_reason,
        "last_decision_sample_time": last_decision_sample_time,
        "min_decision_interval_seconds": min_decision_interval_seconds,
        "visible_alert_source": "confirmed_violence" if visible_violence_alert else "weapon",
        "weapon_alert": bool(is_weapon_threat),
    }
    
    payload["alertState"] = alert_state
    payload["confirmedAlert"] = confirmed_alert
    payload["confirmRule"] = confirm_rule
    payload["rollingHistory"] = rolling_history
    payload["rollingWindowCount"] = rolling_window_count
    payload["cooldownRemainingSeconds"] = cooldown_remaining_seconds
    payload["decisionSampleAccepted"] = decision_sample_accepted
    payload["ignoredReason"] = ignored_reason
    payload["lastDecisionSampleTime"] = last_decision_sample_time
    payload["minDecisionIntervalSeconds"] = min_decision_interval_seconds
    payload["rawProbability"] = raw_probability
    payload["calibratedProbability"] = calibrated_probability
    payload["modelPrediction"] = model_prediction
    
    return payload

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


_WEAPON_TEXT_HINTS: Dict[str, float] = {
    "weapon": 0.80,
    "firearm": 0.95,
    "gun": 0.95,
    "pistol": 0.95,
    "rifle": 0.95,
    "shotgun": 0.95,
    "knife": 0.86,
    "sword": 0.80,
    "سلاح": 0.90,
    "مسدس": 0.95,
    "بندقية": 0.95,
    "رشاش": 0.95,
    "سكين": 0.86,
}


def _weapon_signal_from_report(report_text: str) -> Tuple[float, list[str]]:
    if not report_text:
        return 0.0, []
    lowered = str(report_text).lower()
    matched: list[str] = []
    best = 0.0
    for token, score in _WEAPON_TEXT_HINTS.items():
        if token in lowered:
            matched.append(token)
            if score > best:
                best = score
    return best, matched


def _decision_layer_status_payload() -> Dict[str, object]:
    status = state.get_decision_layer_status()
    payload = dict(status)
    payload["watchThreshold"] = status["watch_threshold"]
    payload["confirmThreshold"] = status["confirm_threshold"]
    payload["confirmN"] = status["confirm_n"]
    payload["confirmM"] = status["confirm_m"]
    payload["cooldownSeconds"] = status["cooldown_seconds"]
    payload["alertState"] = status["alert_state"]
    payload["confirmedAlert"] = status["confirmed_alert"]
    payload["confirmRule"] = status["confirm_rule"]
    payload["rollingHistory"] = status["rolling_history"]
    payload["rollingWindowCount"] = status["rolling_window_count"]
    payload["cooldownRemainingSeconds"] = status["cooldown_remaining_seconds"]
    payload["decisionSampleAccepted"] = status["decision_sample_accepted"]
    payload["ignoredReason"] = status["ignored_reason"]
    payload["lastDecisionSampleTime"] = status["last_decision_sample_time"]
    payload["minDecisionIntervalSeconds"] = status["min_decision_interval_seconds"]
    payload["baseModelThreshold"] = status.get("base_model_threshold", 0.45)
    return payload



def _is_live_source(source: Union[str, int]) -> bool:
    """Returns True if source is a live webcam (integer index), False if it's a file."""
    return isinstance(source, int)

def _is_rtsp_source(source: Union[str, int]) -> bool:
    """Returns True if source is an RTSP URL."""
    return isinstance(source, str) and source.lower().startswith("rtsp://")

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

def _read_cap_props(cap: cv2.VideoCapture) -> Tuple[float, int, int]:
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return fps, w, h

def _drain_to_latest(cap: cv2.VideoCapture, max_drain: int = 30) -> Tuple[bool, Optional[np.ndarray]]:
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
    device,
    model_weights: str,
    threshold: float,
    stride: int,
    stop_event: Optional[threading.Event] = None,
    raw_mode: bool = False,
):
    import torch
    try:
        from .pipeline_capture import CaptureThread
        from .pipeline_render import RenderThread
        from .inference_process import inference_worker
    except ImportError:
        from pipeline_capture import CaptureThread
        from pipeline_render import RenderThread
        from inference_process import inference_worker

    print(f"[{camera_id}] Pipeline worker starting...")

    render_queue = deque(maxlen=12)
    ring_buffer = deque(maxlen=RING_BUFFER_LEN)
    effective_stop = stop_event or threading.Event()

    # ── Multiprocessing queues for inference subprocess ──
    frame_queue_mp = mp.Queue(maxsize=3)
    result_queue_mp = mp.Queue(maxsize=30)
    mp_stop_event = mp.Event()

    # ── Build config dict for inference subprocess ──
    weapon_config_dict = {}
    try:
        if isinstance(config, dict) and "weapon" in config:
            weapon_config_dict = config
        elif hasattr(config, "__getitem__") and "weapon" in dict(config):
            weapon_config_dict = dict(config)
    except Exception:
        pass

    inf_config = {
        "device": str(device),
        "weights_path": str(model_weights),
        "weapon_path": os.getenv("WEAPON_WEIGHT_PATH", config.get("weapon", {}).get("weight_path", "./weapon_yolo.pt")) if isinstance(config, dict) else "./weapon_yolo.pt",
        "threshold": threshold,
        "violence_stride": stride,
        "weapon_interval": int(os.getenv("WEAPON_INFER_INTERVAL", "4")),
        "person_interval": int(os.getenv("PERSON_INFER_INTERVAL", "3")),
        "weapon_config": weapon_config_dict,
        "person_conf_threshold": float(os.getenv("PERSON_OVERLAY_CONF", "0.45")),
        "weapon_min_confidence": float(os.getenv("WEAPON_MIN_CONFIDENCE", "0.20")),
    }

    # ── Spawn inference subprocess ──
    inf_process = mp.Process(
        target=inference_worker,
        args=(frame_queue_mp, result_queue_mp, mp_stop_event, inf_config),
        daemon=True,
        name=f"inference-{camera_id}",
    )
    inf_process.start()
    print(f"[{camera_id}] Inference subprocess started (pid={inf_process.pid}).")

    # ── Open capture ──
    capture = CaptureThread(
        source=source, queue=deque(maxlen=5), ring_buffer=ring_buffer,
        stop_event=effective_stop,
    )
    if not capture.open():
        print(f"[{camera_id}] Failed to open source: {source}")
        mp_stop_event.set()
        inf_process.join(timeout=5)
        return

    width, height = capture.width, capture.height
    print(f"[{camera_id}] Source: {width}x{height} @ {capture.fps:.0f}fps")

    # Throttle file source reads to native FPS (live cameras self-rate via hardware)
    _is_file_source = not (isinstance(source, int) or
                           (isinstance(source, str) and
                            source.lower().startswith(("rtsp://", "rtmp://"))))
    _frame_delay = (1.0 / max(1.0, capture.fps)) if _is_file_source else 0.0

    try:
        from .frame_pipeline import OverlayCache
    except ImportError:
        from frame_pipeline import OverlayCache
    overlay_cache = OverlayCache()
    overlay_cache.update(video_width=int(width), video_height=int(height))

    # ── Start render thread ──
    def _on_threat_callback(alert_payload, snapshot_jpeg, clip_path):
        state.register_alert(alert_payload)
        if snapshot_jpeg:
            thumb_path = THUMBNAILS_DIR / f"{alert_payload.get('id', 'unknown')}.jpg"
            try:
                thumb_path.write_bytes(snapshot_jpeg)
                alert_payload["thumbnailPath"] = str(thumb_path)
            except Exception:
                pass
        state.broadcast_alert(alert_payload)
        if telegram_notifier is not None:
            telegram_notifier.enqueue_alert(alert_payload, snapshot_jpeg, clip_path)

    active_post_queues: list = []

    def _on_evidence_trigger(alert_id: str, width: int, height: int, fps: float):
        # Use source native FPS for accurate clip timing; fall back to render-measured
        effective_fps = capture.fps if capture.fps > 0 else fps
        pre_frames = list(ring_buffer)
        post_q: queue.Queue = queue.Queue(maxsize=POST_ALERT_LEN + 20)
        active_post_queues.append(post_q)
        def _writer():
            try:
                _write_evidence_clip(alert_id, pre_frames, post_q, effective_fps, int(width), int(height))
            finally:
                try:
                    active_post_queues.remove(post_q)
                except ValueError:
                    pass
        threading.Thread(target=_writer, daemon=True, name=f"clip-{alert_id}").start()

    render_thread = RenderThread(
        frame_queue=render_queue,
        result_cache=overlay_cache,
        result_queue_mp=result_queue_mp,
        camera_id=camera_id,
        stop_event=effective_stop,
        set_frame_fn=state.set_frame,
        annotate_fn=annotate_frame,
        set_detection_meta_fn=state.set_detection_meta,
        on_threat_fn=_on_threat_callback,
        on_evidence_trigger_fn=_on_evidence_trigger,
        decision_layer=state._decision_layer,
        fusion_engine=fusion_engine,
        target_fps=TARGET_FPS,
        jpeg_quality=JPEG_QUALITY,
    )
    render_t = threading.Thread(target=render_thread.run, daemon=True, name=f"render-{camera_id}")
    render_t.start()

    # ── Main capture loop ──
    print(f"[{camera_id}] Pipeline running (multiprocessing mode).")
    state.running = True
    fps_counter = 0
    fps_timer = time.perf_counter()

    while state.running and not effective_stop.is_set():
        # Health check: restart inference subprocess if it died
        if not inf_process.is_alive():
            print(f"[{camera_id}] Inference subprocess died! Restarting...")
            mp_stop_event.clear()
            result_queue_mp = mp.Queue(maxsize=30)
            frame_queue_mp = mp.Queue(maxsize=3)
            inf_process = mp.Process(
                target=inference_worker,
                args=(frame_queue_mp, result_queue_mp, mp_stop_event, dict(inf_config)),
                daemon=True,
                name=f"inference-{camera_id}",
            )
            inf_process.start()
            render_thread.result_queue_mp = result_queue_mp
            print(f"[{camera_id}] Inference subprocess restarted (pid={inf_process.pid}).")

        ret, raw = capture.read_frame()

        if not ret:
            is_live = isinstance(source, int) or (
                isinstance(source, str) and source.lower().startswith(("rtsp://", "rtmp://"))
            )
            if is_live:
                print(f"[{camera_id}] Connection lost. Reconnecting...")
                if not capture.reconnect():
                    time.sleep(5.0)
                continue
            else:
                capture.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

        # Push frame to render queue (for display)
        render_queue.append(raw.copy())

        # Populate pre-alert ring buffer for evidence clips
        ring_buffer.append(raw)

        # Feed any active evidence clip writers
        if active_post_queues:
            frame_copy = raw.copy()
            for pq in list(active_post_queues):
                try:
                    pq.put_nowait(frame_copy)
                except queue.Full:
                    pass

        # Push frame to inference subprocess queue (non-blocking, drop if full)
        try:
            frame_queue_mp.put_nowait(raw.copy())
        except queue.Full:
            pass  # Drop frame — inference is behind, keep display responsive

        # Update FPS
        fps_counter += 1
        now = time.perf_counter()
        if now - fps_timer >= 1.0:
            current_fps = fps_counter / (now - fps_timer)
            overlay_cache.update(fps=current_fps)
            fps_counter = 0
            fps_timer = now

            snap = overlay_cache.snapshot()
            track_ids = [t.get("label", f"P-{i}") if isinstance(t, dict) else getattr(t, "label", f"P-{i}") for i, t in enumerate(snap["tracks"])]
            state.broadcast_person_data(
                camera_id=camera_id, person_count=snap["person_count"],
                track_ids=track_ids, is_threat=snap["is_threat"],
                video_width=snap.get("video_width", 0),
                video_height=snap.get("video_height", 0),
            )

        # Throttle file sources to native FPS so video plays at real speed
        if _frame_delay > 0:
            time.sleep(_frame_delay)

    # ── Cleanup ──
    mp_stop_event.set()
    effective_stop.set()
    capture.release()
    inf_process.join(timeout=5)
    print(f"[{camera_id}] Pipeline stopped.")



# ─────────────────────────────────────────────────────────────────────────────
# 6. Input Validation Helpers
# ─────────────────────────────────────────────────────────────────────────────

# alert_id must be alphanumeric with dashes or underscores only (e.g. "alert-1715441234567").
# This blocks path traversal sequences like "../secret" before they reach the filesystem.
_ALERT_ID_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')

def _validate_alert_id(alert_id: str) -> None:
    """Reject alert_id that could escape intended storage directories.

    Raises HTTPException 400 if the format is invalid.
    The regex whitelist is the primary guard; the explicit substring check
    is a secondary defense-in-depth layer.
    """
    if not _ALERT_ID_RE.match(alert_id):
        raise HTTPException(status_code=400, detail="Invalid alert_id format")
    # Redundant but explicit: these characters cannot appear after the regex passes,
    # kept to document the intent.
    if any(c in alert_id for c in ("..", "/", "\\", "\x00")):
        raise HTTPException(status_code=400, detail="Invalid alert_id format")


# ─────────────────────────────────────────────────────────────────────────────
# 7. FastAPI Setup & Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # System initialization
    _init_config_and_profiles()
    _finalize_config()
    _init_engines()
    if not security_controller.config.api_key:
        print(
            "\n[SECURITY WARNING] ADMIN_API_KEY is empty — all admin-only API routes "
            "(set_threshold, set_cooldown, telegram/test, category/toggle) "
            "are accessible without authentication. "
            "Set ADMIN_API_KEY in backend/.env before public demo or production use.\n"
        )
    _init_category_detector()

    global _webrtc_manager
    try:
        from webrtc_streamer import WebRTCManager
        _webrtc_manager = WebRTCManager()
        print(f"[System] WebRTC manager ready (available={_webrtc_manager.available})")
    except Exception as exc:
        print(f"[System] WebRTC init skipped: {exc}")

    telegram_notifier.start()
    threads = []
    inf_processes = []
    state.running = True
    # Set multiprocessing start method to 'spawn' for CUDA compatibility
    try:
        mp.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # Already set
    if CAPTURE_LOOP_ENABLED:
        import torch
        # Determine active cameras
        active_ids = []
        env_active = os.getenv("ACTIVE_CAMERAS")
        if env_active:
            active_ids = [cid.strip() for cid in env_active.split(",") if cid.strip()]
        else:
            active_ids = list(CAMERA_SOURCES.keys())
        try:
            from .device_config import get_optimal_device
        except ImportError:
            from device_config import get_optimal_device
        device = get_optimal_device(prefer_gpu=True)
        _raw_mode = _env_flag("AI_SENTINEL_RAW_STREAM", default=False)
        for cam_id in active_ids:
            if cam_id not in CAMERA_SOURCES:
                print(f"[System] Warning: camera '{cam_id}' not in CAMERA_SOURCES, skipping.")
                continue
            source = CAMERA_SOURCES[cam_id]
            t = threading.Thread(
                target=camera_worker,
                args=(cam_id, source, device, WEIGHTS_PATH, THRESHOLD, STRIDE),
                kwargs={"raw_mode": _raw_mode},
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
    for p in inf_processes:
        p.join(timeout=5)
    if telegram_notifier:
        telegram_notifier.stop()
    if go2rtc_bridge:
        go2rtc_bridge.stop()
    if _webrtc_manager is not None:
        try:
            await _webrtc_manager.close_all()
        except Exception:
            pass

app = FastAPI(lifespan=lifespan, title="AI Sentinel Advanced Backend")
app.add_middleware(
    CORSMiddleware, 
    allow_origins=config['server']['cors_origins'], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

async def _mjpeg_generator(camera_id: str) -> AsyncGenerator[bytes, None]:
    boundary = b"--frame\r\n"
    last_id: int = 0
    while True:
        jpg = state.get_frame(camera_id)
        if jpg and id(jpg) != last_id:
            last_id = id(jpg)
            yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(0)      # yield event loop control immediately after send
        else:
            await asyncio.sleep(0.005)  # 5ms poll — below Windows timer coarseness cap

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

# ── WebRTC / go2rtc Proxy Endpoints ──────────────────────────────────────────

@app.get("/api/webrtc/{cam_id}", summary="Get WebRTC stream metadata for camera")
async def webrtc_stream(cam_id: str):
    if not go2rtc_bridge or not go2rtc_bridge.is_running:
        raise HTTPException(status_code=503, detail="WebRTC not available")
    whep_url = go2rtc_bridge.get_whep_url(cam_id)
    if not whep_url:
        raise HTTPException(status_code=404, detail="Stream not found")
    return {"cam_id": cam_id, "url": whep_url, "protocol": "webrtc"}

@app.post("/api/webrtc/{cam_id}/whep", summary="Proxy WHEP SDP offer to go2rtc")
async def webrtc_whep_offer(cam_id: str, request: Request):
    if not go2rtc_bridge or not go2rtc_bridge.is_running:
        raise HTTPException(status_code=503, detail="WebRTC not available")
    body = await request.body()
    status, response_body = go2rtc_bridge.proxy_whep(
        cam_id, "POST", body.decode() if body else None, "application/sdp"
    )
    if status != 200:
        raise HTTPException(status_code=status, detail="WHEP negotiation failed")
    return Response(content=response_body, media_type="application/sdp")

@app.patch("/api/webrtc/{cam_id}/whep", summary="Proxy ICE trickle to go2rtc")
async def webrtc_whep_ice(cam_id: str, request: Request):
    if not go2rtc_bridge or not go2rtc_bridge.is_running:
        raise HTTPException(status_code=503, detail="WebRTC not available")
    body = await request.body()
    status, response_body = go2rtc_bridge.proxy_ice(cam_id, body.decode() if body else None)
    if status not in (200, 204):
        raise HTTPException(status_code=status, detail="ICE trickle failed")
    return Response(content=response_body, media_type="application/trickle-ice-sdpfrag")

# ── MJPEG / Standard Endpoints ───────────────────────────────────────────────

@app.get("/video_feed", summary="MJPEG Video Stream")
async def video_feed(camera_id: str = DEFAULT_CAMERA_ID):
    is_example = camera_id in EXAMPLE_SOURCES
    if not is_example and camera_id not in CAMERA_SOURCES:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} is not configured or offline")
    return StreamingResponse(_mjpeg_generator(camera_id), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/webrtc/offer/{camera_id}", summary="WebRTC SDP offer/answer exchange")
async def webrtc_offer(camera_id: str, request: Request):
    if _webrtc_manager is None:
        raise HTTPException(status_code=501, detail="WebRTC not initialized")
    if not _webrtc_manager.available:
        raise HTTPException(status_code=501, detail="WebRTC not available. Install: pip install aiortc av")
    data = await request.json()
    try:
        result = await _webrtc_manager.handle_offer(
            camera_id,
            lambda cid=camera_id: state.get_frame(cid),
            data["sdp"], data["type"]
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"WebRTC offer failed: {exc}")

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


def _build_detection_payload(snap: dict) -> dict:
    return {
        "tracks": snap.get("tracks", []),
        "personCount": snap.get("person_count", 0),
        "isThreat": snap.get("is_threat", False),
        "threatConfidence": snap.get("threat_confidence", 0),
        "fps": snap.get("fps", 0),
        "weaponScore": snap.get("weapon_score", 0),
        "videoWidth": snap.get("video_width", 0),
        "videoHeight": snap.get("video_height", 0),
        "multiThreat": snap.get("multiThreat"),
    }


async def _detection_sse_generator(camera_id: str) -> AsyncGenerator[bytes, None]:
    import json
    last_tracks_hash = ""
    while True:
        snap = state.get_detection_meta(camera_id)
        if snap and snap.get("tracks") is not None:
            payload = _build_detection_payload(snap)
            data_str = json.dumps(payload)
            current_hash = hash(data_str)
            if current_hash != last_tracks_hash:
                last_tracks_hash = current_hash
                yield f"data: {data_str}\n\n".encode()
        await asyncio.sleep(0.1)


@app.get("/detections", summary="SSE Detection Metadata Stream")
async def detections(camera_id: str = DEFAULT_CAMERA_ID):
    """Stream real-time detection metadata (tracks, person count, threat) for frontend overlay rendering."""
    if camera_id not in CAMERA_SOURCES and camera_id not in EXAMPLE_SOURCES:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} not configured")
    return StreamingResponse(
        _detection_sse_generator(camera_id),
        media_type="text/event-stream",
    )


@app.post("/demo_start/{clip_id}", summary="Start on-demand analysis of a demo/example clip")
async def demo_start(clip_id: str):
    """Start a temporary AI analysis worker for a demo clip. No-op if already running."""
    if clip_id not in EXAMPLE_SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown demo clip: {clip_id}")
    clip_path = EXAMPLE_SOURCES[clip_id]
    if not Path(clip_path).exists():
        raise HTTPException(status_code=404, detail=f"Demo clip file not found: {clip_path}")
    if state.is_demo_worker_running(clip_id):
        return {"status": "already_running", "clip_id": clip_id}
    from device_config import get_optimal_device
    device = get_optimal_device(prefer_gpu=True)
    stop_event = state.create_worker_stop_event(clip_id)
    t = threading.Thread(
        target=camera_worker,
        args=(clip_id, clip_path, device, WEIGHTS_PATH, state.get_threshold(), STRIDE),
        kwargs={"stop_event": stop_event, "raw_mode": _env_flag("AI_SENTINEL_RAW_STREAM", default=False)},
        daemon=True,
        name=f"demo-worker-{clip_id}",
    )
    t.start()
    print(f"[Demo] Started on-demand worker for {clip_id}: {clip_path}")
    return {"status": "started", "clip_id": clip_id}


@app.delete("/demo_stop/{clip_id}", summary="Stop on-demand demo clip analysis")
async def demo_stop(clip_id: str):
    """Stop the temporary analysis worker for a demo clip."""
    if clip_id not in EXAMPLE_SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown demo clip: {clip_id}")
    stopped = state.stop_worker(clip_id)
    print(f"[Demo] {'Stopped' if stopped else 'No active worker for'} {clip_id}")
    return {"status": "stopped" if stopped else "not_running", "clip_id": clip_id}


@app.get("/demo_video/{clip_id}", summary="Serve demo clip video file for browser playback")
async def demo_video(clip_id: str):
    """Return the raw demo clip file so the browser can play it natively in a <video> element."""
    if clip_id not in EXAMPLE_SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown demo clip: {clip_id}")
    clip_path = Path(EXAMPLE_SOURCES[clip_id])
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail=f"Demo clip file not found: {clip_id}")
    suffix = clip_path.suffix.lower()
    media_type = "video/mp4" if suffix == ".mp4" else "video/x-msvideo"
    return FileResponse(str(clip_path), media_type=media_type)


@app.get("/clips/{alert_id}", summary="Stream recorded incident clip")
async def get_clip(alert_id: str):
    """Stream a recorded incident clip."""
    _validate_alert_id(alert_id)
    from pathlib import Path

    # Check evidence directory
    clip_path = EVIDENCE_DIR / f"{alert_id}.mp4"
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Clip not found")
    
    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
    )


@app.get("/api/clips/list", summary="List available incident clips")
async def list_clips():
    """List all evidence clips in EVIDENCE_DIR, newest first."""
    clips = []

    if EVIDENCE_DIR.exists():
        paths = sorted(EVIDENCE_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        for clip_path in paths:
            alert_id = clip_path.stem
            alert = state.get_alert(alert_id)
            clips.append({
                "alertId": alert_id,
                "clipUrl": f"/clips/{alert_id}",
                "timestamp": alert.get("timestamp") if alert else None,
                "cameraId": alert.get("cameraId") if alert else None,
                "type": alert.get("type") if alert else "unknown",
                "confidence": alert.get("confidence") if alert else None,
                "severity": alert.get("severity") if alert else None,
                "size": clip_path.stat().st_size,
                "mtime": clip_path.stat().st_mtime,
            })

    return {"clips": clips, "count": len(clips)}


@app.get("/api/categories", summary="Get all available detection categories")
async def get_categories():
    """Get all available detection categories and their status."""
    if not category_detector:
        raise HTTPException(status_code=503, detail="Category detector not initialized")
    
    return {
        "categories": [
            category_detector.get_capability(cat)
            for cat in DetectionCategory
        ]
    }


@app.post("/api/analyze", summary="Analyze a frame or context for a specific category")
async def analyze_category(body: AnalyzeRequest, request: Request):
    """Analyze context data for a specific detection category."""
    if not category_detector:
        raise HTTPException(status_code=503, detail="Category detector not initialized")
    
    try:
        cat = DetectionCategory(body.category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: {body.category}")
    
    try:
        context = parse_detection_context(body.context)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        # Unexpected parsing error
        raise HTTPException(status_code=400, detail=f"Malformed context: {exc}")
        
    scores = category_detector.analyze_context(context, cat)
    score = scores.get(cat, 0.0)
    
    return {
        "category": cat.value,
        "score": float(score),
        "threshold": getattr(category_detector.config, f"{cat.value}_threshold", 0.0),
        "triggered": score >= getattr(category_detector.config, f"{cat.value}_threshold", 0.0),
        "severity": category_detector.get_category_severity(cat)
    }


@app.post("/api/categories/{category_id}/toggle", summary="Toggle a detection category")
async def toggle_category(category_id: str, enabled: bool, request: Request):
    """Enable or disable a detection category."""
    global category_detector
    role = security_controller.authorize(request, required_role="admin")
    if not category_detector:
        raise HTTPException(status_code=503, detail="Category detector not initialized")
    
    try:
        cat = DetectionCategory(category_id)
        
        cap = category_detector.get_capability(cat)
        
        if enabled and cap["status"] == "unsupported":
            raise HTTPException(status_code=400, detail=f"Cannot enable {category_id}: {cap['reason']}")
            
        # Update config (in production, would persist to config file)
        import dataclasses
        new_config = dataclasses.replace(
            category_detector.config, 
            **{f"{cat.value}_enabled": enabled}
        )
        category_detector = CategoryDetector(new_config)
        
        audit_logger.record("category_toggle", "success", role=role, details={"category": category_id, "enabled": enabled})
        return {"category": category_id, "enabled": enabled, "status": cap["status"]}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category_id}")


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


@app.post("/notifications/telegram/test_video", summary="Send a Telegram test video alert using a demo clip")
async def test_telegram_video(request: Request, clip_id: str = "EXAMPLE-02"):
    role = security_controller.authorize(request, required_role="admin")
    if not telegram_notifier.config.ready:
        raise HTTPException(status_code=503, detail="Telegram notifications are not configured")
    if clip_id not in EXAMPLE_SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown demo clip: {clip_id}")
    clip_path = EXAMPLE_SOURCES[clip_id]
    if not Path(clip_path).exists():
        raise HTTPException(status_code=404, detail=f"Demo clip file not found: {clip_id}")

    test_alert = {
        "id": f"test-video-{int(time.time() * 1000)}",
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "isoTime": datetime.now(timezone.utc).isoformat(),
        "confidence": 100.0,
        "type": "Telegram Video Test",
        "severity": "high",
        "cameraId": clip_id,
        "location": "Test channel",
    }
    snapshot = state.get_frame(clip_id)
    telegram_notifier.enqueue_alert(test_alert, snapshot, clip_path=clip_path, is_demo_clip=True)
    audit_logger.record(
        "telegram_test_video",
        "queued",
        role=role,
        alert_id=test_alert["id"],
        details={"clipId": clip_id},
    )
    return {"status": "queued", "clip_id": clip_id, "telegram": telegram_notifier.status()}


# ─────────────────────────────────────────────────────────────────────────────
# DeepSeek / OpenRouter Reporting
# ─────────────────────────────────────────────────────────────────────────────

_DEMO_SOURCE_NAMES: dict[str, str] = {
    "EXAMPLE-01": "Fight Sample 1",
    "EXAMPLE-02": "Fight Sample 2",
    "EXAMPLE-03": "Violence Sample 3",
}

_LIVE_SOURCE_NAMES: dict[str, str] = {
    "CAM-01": "Live Camera Slot 1",
    "CAM-02": "Live Camera Slot 2",
}


def _enrich_alert_for_report(alert: dict) -> dict:
    """Add evidence availability and demo context fields before sending to DeepSeek."""
    cam_id = str(alert.get("cameraId", ""))
    alert_id = str(alert.get("id", "x"))
    is_demo = cam_id in EXAMPLE_SOURCES

    if is_demo:
        evidence_video_available = True
        evidence_video_type = "demo_source_video"
        source_type = "demo_clip"
        demo_mode = True
        clip_review_available = True
        visual_review_note = (
            "Demo source video is available for review in the Demo Clips / Clip Review workflow."
        )
    else:
        evidence_clip_exists = (EVIDENCE_DIR / f"{alert_id}.mp4").exists()
        evidence_video_available = evidence_clip_exists
        evidence_video_type = "recorded_evidence_clip" if evidence_clip_exists else "none"
        source_type = "live_camera"
        demo_mode = False
        clip_review_available = evidence_clip_exists
        visual_review_note = (
            "Recorded incident clip is available for review."
            if evidence_clip_exists
            else "No saved clip is currently available."
        )

    source_name = (
        _DEMO_SOURCE_NAMES.get(cam_id)
        or _LIVE_SOURCE_NAMES.get(cam_id)
        or cam_id
    )

    # Confidence percentages — alert may have separate threat vs model fields
    raw_conf = float(alert.get("confidence") or 0)
    threat_confidence_percent = float(
        alert.get("threatConfidence") or alert.get("fusionScore") or raw_conf
    )
    model_confidence_percent = float(
        alert.get("modelConfidence") or alert.get("calibratedConfidence") or raw_conf
    )
    motion_raw = float(alert.get("motionScore") or 0)
    # motionScore from fusion is 0-1 scale; convert to percent
    motion_score_percent = round(motion_raw * 100, 1) if motion_raw <= 1.0 else round(motion_raw, 1)

    return {
        **alert,
        "demoMode": demo_mode,
        "demo_mode": demo_mode,
        "source_type": source_type,
        "source_name": source_name,
        "evidence_video_available": evidence_video_available,
        "evidence_video_type": evidence_video_type,
        "clip_review_available": clip_review_available,
        "visual_review_note": visual_review_note,
        "threat_confidence_percent": round(threat_confidence_percent, 1),
        "model_confidence_percent": round(model_confidence_percent, 1),
        "motion_score_percent": motion_score_percent,
        "report_context": (
            "This is an AI Sentinel surveillance alert. The report is generated from alert metadata "
            "and available system evidence. Do not claim that no video exists if evidence_video_available is true."
        ),
    }


@app.get("/reports/deepseek/status", summary="DeepSeek report service status")
async def deepseek_status():
    return deepseek_service.status()


@app.post("/reports/deepseek/test", summary="Generate test DeepSeek report (no alert required)")
async def deepseek_test(request: Request):
    security_controller.authorize(request, required_role="viewer")
    demo = deepseek_service.demo_alert()
    all_alerts = state.get_all_alerts()
    if all_alerts:
        latest = sorted(all_alerts, key=lambda a: a.get("isoTime", ""), reverse=True)[0]
        demo = {**latest, "id": "test-demo-report"}
    demo = _enrich_alert_for_report(demo)

    try:
        result = deepseek_service.generate(demo, force=True)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/reports/deepseek/{alert_id}", summary="Generate DeepSeek report for an alert")
async def deepseek_generate(alert_id: str, request: Request, force: bool = False):
    _validate_alert_id(alert_id)
    security_controller.authorize(request, required_role="viewer")
    alert = state.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Incident not found")
    alert_payload = _enrich_alert_for_report(alert)
    try:
        result = deepseek_service.generate(alert_payload, force=force)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/reports/deepseek/{alert_id}", summary="Fetch cached DeepSeek report")
async def deepseek_get(alert_id: str, request: Request):
    _validate_alert_id(alert_id)
    security_controller.authorize(request, required_role="viewer")
    cached = deepseek_service.get_cached(alert_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="Report not generated yet")
    return cached


@app.get("/download_report/{alert_id}", summary="Fetch forensic PDF report")
async def download_report(alert_id: str, request: Request):
    _validate_alert_id(alert_id)
    role = security_controller.authorize(request, required_role="viewer")
    alert = state.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Prefer DeepSeek report if cached; fall back to Groq/VLM text
    _ds_cache = deepseek_service.get_cached(alert_id)
    if _ds_cache and isinstance(_ds_cache.get("report"), dict):
        _r = _ds_cache["report"]
        _parts = []
        if _r.get("executive_summary"):
            _parts.append(f"Summary: {_r['executive_summary']}")
        if _r.get("severity_assessment"):
            _parts.append(f"Severity: {_r['severity_assessment']}")
        if _r.get("recommended_actions"):
            _actions = _r["recommended_actions"]
            _joined = "; ".join(str(a) for a in _actions[:3]) if isinstance(_actions, list) else str(_actions)
            _parts.append(f"Actions: {_joined}")
        if _r.get("final_verdict"):
            _parts.append(f"Verdict: {_r['final_verdict']}")
        report_text = "\n".join(_parts) if _parts else "DeepSeek report available."
    else:
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
    _validate_alert_id(alert_id)
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
    _validate_alert_id(alert_id)
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


@app.get("/system/status", summary="Combined system status")
async def system_status():
    return {
        "health": "ok",
        "model": {
            "threshold": state.get_threshold(),
            "cooldown": state.get_cooldown(),
            "device": "cuda" if _is_torch_cuda_available() else "cpu",
            "violenceClassIndex": VIOLENCE_CLS,
        },
        "decisionLayer": _decision_layer_status_payload(),
        "notifications": telegram_notifier.status(),
        "fusion": {
            "enabled": fusion_engine.config.enabled,
            "weights": {
                "violence": fusion_engine.config.violence_weight,
                "motion": fusion_engine.config.motion_weight,
                "weapon": fusion_engine.config.weapon_weight,
            },
        },
        "weapon": weapon_engine.status(),
        "security": security_controller.status(),
        "audit": audit_logger.status(),
        "audio": audio_analyzer.status(),
        "storage": {
            "evidence": str(EVIDENCE_DIR),
            "thumbnails": str(THUMBNAILS_DIR),
            "reports": str(REPORTS_DIR),
        },
    }


@app.get("/system/metrics", summary="Real-time pipeline performance metrics")
async def system_metrics():
    try:
        from metrics import pipeline_metrics as pm
        m = pm.summary()
        m["webrtcAvailable"] = False
        try:
            from webrtc_streamer import WebRTCManager
            m["webrtcAvailable"] = WebRTCManager().available
        except Exception:
            pass
        return m
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/decision_layer/reset", summary="Reset live alert decision layer state")
async def reset_decision_layer(request: Request):
    role = security_controller.authorize(request, required_role="admin")
    decision_status = state.reset_decision_layer()
    audit_logger.record(
        "decision_layer_reset",
        "success",
        role=role,
    )
    payload = dict(decision_status)
    payload["watchThreshold"] = decision_status["watch_threshold"]
    payload["confirmThreshold"] = decision_status["confirm_threshold"]
    payload["confirmN"] = decision_status["confirm_n"]
    payload["confirmM"] = decision_status["confirm_m"]
    payload["cooldownSeconds"] = decision_status["cooldown_seconds"]
    payload["alertState"] = decision_status["alert_state"]
    payload["confirmedAlert"] = decision_status["confirmed_alert"]
    payload["confirmRule"] = decision_status["confirm_rule"]
    payload["rollingHistory"] = decision_status["rolling_history"]
    payload["rollingWindowCount"] = decision_status["rolling_window_count"]
    payload["cooldownRemainingSeconds"] = decision_status["cooldown_remaining_seconds"]
    payload["decisionSampleAccepted"] = decision_status["decision_sample_accepted"]
    payload["ignoredReason"] = decision_status["ignored_reason"]
    payload["lastDecisionSampleTime"] = decision_status["last_decision_sample_time"]
    payload["minDecisionIntervalSeconds"] = decision_status["min_decision_interval_seconds"]
    payload["baseModelThreshold"] = decision_status.get("base_model_threshold", 0.45)
    return {
        "status": "success",
        "decisionLayer": payload,
    }


@app.get("/health", summary="Health check")
async def health():
    return await system_status()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Application Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", config.get("server", {}).get("host", "0.0.0.0"))
    port = int(os.getenv("PORT", config.get("server", {}).get("port", 8002)))
    print(f"[System] Starting AI Sentinel on {host}:{port}...")
    uvicorn.run(app, host=host, port=port)
