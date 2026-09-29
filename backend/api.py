from __future__ import annotations

import asyncio
import logging
import json
import os
import time
import threading
import queue
import multiprocessing as mp
import base64
import re
import sys
import yaml
from dotenv import load_dotenv
from collections import deque
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional, Tuple, Union

import cv2
cv2.setNumThreads(1)
import numpy as np
# import torch deferred to functions
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent

# Sibling modules import their collaborators by top-level name (e.g.
# ``person_detector`` does ``from yolo_onnx import ...``). Make the backend
# directory importable when this module is imported as a package
# (``import backend.api``) as well as via ``uvicorn api:app --app-dir backend``
# so the API can start from committed code alone (SC-10).
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from .live_alert_decision import LiveAlertDecisionLayer
    from .decision_config import load_decision_config, DecisionConfig
except ImportError:
    from live_alert_decision import LiveAlertDecisionLayer
    from decision_config import load_decision_config, DecisionConfig

try:
    from .person_detector import PersonDetector
    from .visual_annotator import annotate as annotate_frame
    from .counting import estimate_window_to_wire
except ImportError:
    from person_detector import PersonDetector
    from visual_annotator import annotate as annotate_frame
    from counting import estimate_window_to_wire

# SC-10: ``go2rtc_bridge`` is an optional integration module that is not part of
# the committed tree. When it is unavailable the WebRTC/WHEP routes stay
# registered and report an explicit DISABLED state instead of taking the whole
# API down (a missing integration must never be silent).
Go2RTCBridge = None  # type: ignore[assignment,misc]
_GO2RTC_IMPORT_ERROR: str | None = None
try:
    try:
        from .go2rtc_bridge import Go2RTCBridge  # type: ignore[no-redef]
    except ImportError:
        from go2rtc_bridge import Go2RTCBridge  # type: ignore[no-redef]
except ImportError as _exc:
    _GO2RTC_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"

# `download_report` calls `build_incident_pdf` as a module global, but
# `_get_imports()` only binds it in its own locals() — bind it here (same
# tracked-module convention as the imports above). Pre-existing defect at the
# baseline: the PDF route answered HTTP 500 NameError (reported by WT-27).
try:
    from .reporting import build_incident_pdf
except ImportError:
    from reporting import build_incident_pdf
try:
    from .alert_triage import apply_transition, normalize_record as normalize_triage_record
except ImportError:
    from alert_triage import apply_transition, normalize_record as normalize_triage_record

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
        from .calibration_utils import load_calibration_profile, enforce_startup_calibration
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
        from calibration_utils import load_calibration_profile, enforce_startup_calibration
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
    # [WT-14] camera_profiles.yml discovery (first EXISTING wins): env override,
    # then legacy backend/camera_profiles.yml (user-owned), then the shipped
    # config/camera_profiles.yml. A user file is never shadowed by the default.
    env_raw = os.getenv("CAMERA_PROFILES_PATH")
    if env_raw:
        path = Path(env_raw)
        return path if path.is_absolute() else BASE_DIR / path
    for candidate in (BASE_DIR / "camera_profiles.yml",
                      BASE_DIR.parent / "config" / "camera_profiles.yml"):
        if candidate.exists():
            return candidate
    return BASE_DIR / "camera_profiles.yml"


def _load_capture_profile(camera_id: str):
    # [WT-14] capture-quality tuning (additive schema keys; defaults if absent)
    from pipeline_capture import default_profile, load_capture_profiles
    path = _resolve_profiles_path()
    if not path.exists():
        return default_profile(camera_id)
    try:
        profiles = load_capture_profiles(path)
    except Exception:
        logging.exception("camera_profiles.yml capture tuning invalid; using defaults")
        return default_profile(camera_id)
    return profiles.get(camera_id) or default_profile(camera_id)


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
        "EXAMPLE-01": str(_project_root / "demo_assets" / "videos" / "Wq0BuA8GM84_0.avi"),
        "EXAMPLE-02": str(_project_root / "demo_assets" / "videos" / "YDOJvzChqSg_0 (1).avi"),
        "EXAMPLE-03": str(_project_root / "demo_assets" / "videos" / "FXC43fACfPc_0.avi"),
    }

EXAMPLE_SOURCES: Dict[str, str] = _load_example_sources()

# Initialize these lazily too
WEIGHTS_PATH = _resolve_backend_path(os.getenv("WEIGHTS_PATH", "best_model.pt"))
THRESHOLD = 0.0
STRIDE = 0

def _finalize_config():
    global THRESHOLD, STRIDE
    THRESHOLD = state.get_decision_config().violence_threshold
    STRIDE = int(os.getenv("STRIDE", str(config['model']['stride'])))

JPEG_QUALITY_PRESETS = {"low": 50, "medium": 75, "high": 90}
JPEG_QUALITY = JPEG_QUALITY_PRESETS.get(os.getenv("STREAM_QUALITY", "medium").lower(), 75)
TARGET_FPS     = 30
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

# WT-21 (S-15): incident face capture — DETECTION + ASSOCIATION WITH
# UNCERTAINTY + CLEAR CAPTURE ONLY; no identity recognition (F-30 face_intel
# stays unwired by campaign policy). Optional import (SC-10 style): when the
# modules are unavailable the /api/faces/* routes report an explicit DISABLED
# state instead of failing at import time.
_FACE_CAPTURE_IMPORT_ERROR: str | None = None
try:
    try:
        from .face_capture import (FaceCaptureService, FaceDerivativeLedger,
                                   configure_service as _configure_face_service)
        from .face_detect import YuNetFaceDetector
    except ImportError:
        from face_capture import (FaceCaptureService, FaceDerivativeLedger,
                                  configure_service as _configure_face_service)
        from face_detect import YuNetFaceDetector
except ImportError as _face_exc:  # pragma: no cover - exercised only when backend files are absent
    _FACE_CAPTURE_IMPORT_ERROR = f"{type(_face_exc).__name__}: {_face_exc}"
    FaceCaptureService = None  # type: ignore[assignment,misc]
    FaceDerivativeLedger = None  # type: ignore[assignment,misc]
    YuNetFaceDetector = None  # type: ignore[assignment,misc]
    _configure_face_service = None  # type: ignore[assignment]

_face_service = None
_face_service_lock = threading.Lock()
_face_build_error: str | None = None
_CROP_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]+$")


def _build_face_service():
    """Construct the incident face capture service (evidence dir per SC-8)."""
    if FaceCaptureService is None:
        return None
    detector = YuNetFaceDetector(
        score_threshold=float(os.getenv("FACE_DETECT_SCORE", "0.6")),
    )
    ledger_path = _resolve_storage_path(
        config['storage'].get('evidence_ledger_path', "./evidence_ledger.jsonl"))
    service = FaceCaptureService(
        detector=detector,
        faces_root=EVIDENCE_DIR,
        ledger=FaceDerivativeLedger(ledger_path),
        sample_every=int(os.getenv("FACE_CAPTURE_SAMPLE_EVERY", "3")),
        post_window_sec=float(os.getenv("FACE_CAPTURE_POST_WINDOW_SEC", "5")),
    )

    def _on_result(alert_id: str, result: dict) -> None:
        # Additive keys only (WT-20 owns other alert payload keys).
        try:
            state.update_alert(alert_id, {
                "faceAssoc": result.get("face_assoc", []),
                "faceCaptureStatus": result.get("status"),
            })
        except Exception:
            logging.getLogger(__name__).warning("face result store failed", exc_info=False)

    service.on_result = _on_result
    if _configure_face_service is not None:
        _configure_face_service(service)
    return service


def _get_face_service():
    global _face_service, _face_build_error
    with _face_service_lock:
        if _face_service is None and _face_build_error is None:
            try:
                _face_service = _build_face_service()
            except Exception as _build_exc:
                # Never 500 on a health check: surface an explicit build error.
                _face_build_error = f"{type(_build_exc).__name__}: {_build_exc}"
                logging.getLogger(__name__).warning(
                    "face capture service build failed: %s", _face_build_error)
        return _face_service

# Best-frame selection records (SC-8 layout: EVIDENCE_DIR sibling directory).
BEST_FRAMES_DIR = EVIDENCE_DIR / "best_frames"
BEST_FRAMES_DIR.mkdir(exist_ok=True)


def _capture_config() -> dict:
    """Incident-capture tuning from config/best_frame.toml ([best_frame.window],
    [capture_ring]); falls back to documented defaults when the file is absent."""
    defaults = {'pre_seconds': 10.0, 'post_seconds': 5.0, 'queue_capacity': 8}
    path = BASE_DIR.parent / 'config' / 'best_frame.toml'
    try:
        import tomllib
        with path.open('rb') as handle:
            payload = tomllib.load(handle)
        window = payload.get('best_frame', {}).get('window', {}) or {}
        ring = payload.get('capture_ring', {}) or {}
        defaults['pre_seconds'] = float(window.get('pre_seconds', defaults['pre_seconds']))
        defaults['post_seconds'] = float(window.get('post_seconds', defaults['post_seconds']))
        defaults['queue_capacity'] = int(ring.get('queue_capacity', defaults['queue_capacity']))
    except (OSError, ValueError, ImportError):
        logging.warning('best_frame.toml unavailable; using built-in capture defaults')
    return defaults


# Person-count SSE broadcast throttling: change-detected, rate-limited per camera.
_PERSON_BROADCAST_MIN_INTERVAL = 0.25
_person_broadcast_state: dict = {}
_person_broadcast_lock = threading.Lock()


def _broadcast_person_counts(camera_id: str, snap: dict) -> None:
    """F-17: give `broadcast_person_data` its first caller.

    Emits only when the counting block changes and at most every
    ``_PERSON_BROADCAST_MIN_INTERVAL`` seconds, so a 30 fps render loop cannot
    flood the SSE alert queues. Counts reach the UI now; richer UI display may
    lag (documented in the campaign blueprint delta).
    """
    tracks = snap.get('tracks') or []
    track_ids = [str(track.get('track_ref') or track.get('track_id')) for track in tracks if isinstance(track, dict)]
    estimate = snap.get('unique_person_estimate_window') or {}
    signature = (
        int(snap.get('visible_person_count', 0) or 0),
        int(snap.get('active_track_count', snap.get('person_count', 0)) or 0),
        tuple(track_ids),
        estimate.get('estimate'), estimate.get('band_label'),
    )
    now = time.monotonic()
    with _person_broadcast_lock:
        previous = _person_broadcast_state.get(camera_id)
        if previous is not None:
            if previous['signature'] == signature:
                return
            if now - previous['at'] < _PERSON_BROADCAST_MIN_INTERVAL:
                return
        _person_broadcast_state[camera_id] = {'signature': signature, 'at': now}
    state.broadcast_person_data(
        camera_id=camera_id,
        person_count=int(snap.get('person_count', 0) or 0),
        track_ids=track_ids,
        is_threat=bool(snap.get('is_threat', False)),
        video_width=int(snap.get('video_width', 0) or 0),
        video_height=int(snap.get('video_height', 0) or 0),
        visible_person_count=int(snap.get('visible_person_count', 0) or 0),
        active_track_count=int(snap.get('active_track_count', snap.get('person_count', 0)) or 0),
        unique_person_estimate_window=estimate or None,
        track_failure_flags=dict(snap.get('track_failure_flags') or {}),
        person_tracker=str(snap.get('person_tracker') or ''),
    )

# WT-23 (F-52/F-53) enhancement seam: optional module (SC-10 style). The
# scheduler runs strictly AFTER evidence finalization (the trigger is evidence
# finalization); when the module is unavailable the
# GET /evidence_derivatives/{alert_id} route reports an explicit DISABLED state
# instead of failing at import time. Tier-0 (CPU pixel ops) only: tier-1 stays
# gated behind the harness and the untracked Real-ESRGAN weights.
_ENHANCE_IMPORT_ERROR: str | None = None
try:
    try:
        from .enhance import (CropRef, DerivativeLedger, EnhancementScheduler,
                              EnhancementService, HASH_BASIS_FILE,
                              enqueue_alert_enhancement)
    except ImportError:
        from enhance import (CropRef, DerivativeLedger, EnhancementScheduler,
                             EnhancementService, HASH_BASIS_FILE,
                             enqueue_alert_enhancement)
except ImportError as _enh_exc:  # pragma: no cover - exercised only when backend files are absent
    _ENHANCE_IMPORT_ERROR = f"{type(_enh_exc).__name__}: {_enh_exc}"
    CropRef = DerivativeLedger = EnhancementScheduler = None  # type: ignore[assignment,misc]
    EnhancementService = HASH_BASIS_FILE = None  # type: ignore[assignment,misc]
    enqueue_alert_enhancement = None  # type: ignore[assignment]

_enhancement_service = None
_enhancement_scheduler = None
_enhancement_build_error: str | None = None
_enhancement_lock = threading.Lock()


def _run_enhancement_job(job) -> None:
    """Tier-0 enhancement handler (worker thread; zero work on the alert path)."""
    service, _scheduler = _get_enhancement()
    if service is None:
        return
    try:
        service.enhance(
            job.crop, job.parent_frame,
            ops=job.ops,
            parent_path=job.parent_path,
            parent_sha256=job.parent_sha256,
            parent_hash_basis=job.parent_hash_basis,
            parent_hash_format=job.parent_hash_format,
            parent_source=job.parent_source,
            tier=job.tier,
        )
    except Exception:
        logging.getLogger(__name__).warning(
            "enhancement job failed for %s", job.alert_id, exc_info=True)


def _get_enhancement():
    """Build the enhancement service + scheduler once; never 500 on lookup."""
    global _enhancement_service, _enhancement_scheduler, _enhancement_build_error
    with _enhancement_lock:
        if _enhancement_service is None and _enhancement_build_error is None:
            if EnhancementService is None:
                return None, None
            try:
                ledger = DerivativeLedger.from_settings(config, BASE_DIR)
                _enhancement_service = EnhancementService(ledger, evidence_dir=EVIDENCE_DIR)
                _enhancement_scheduler = EnhancementScheduler(_run_enhancement_job)
            except Exception as _build_exc:
                _enhancement_build_error = f"{type(_build_exc).__name__}: {_build_exc}"
                logging.getLogger(__name__).warning(
                    "enhancement service build failed: %s", _enhancement_build_error)
        return _enhancement_service, _enhancement_scheduler


def _start_enhancement_scheduler() -> None:
    """Start the scheduler; safe across API restarts (WT-23 seam).

    The WT-23 scheduler owns a one-shot worker thread: a second ``start()`` on
    the same object raises ``RuntimeError: threads can only be started once``.
    A restarted lifespan (repeated TestClient contexts, service restart) swaps
    in a fresh scheduler for the same handler instead of double-starting the
    old thread.
    """
    global _enhancement_scheduler
    _service, scheduler = _get_enhancement()
    if scheduler is None:
        return
    try:
        scheduler.start()
    except RuntimeError:
        _enhancement_scheduler = EnhancementScheduler(_run_enhancement_job)
        _enhancement_scheduler.start()


def _schedule_alert_enhancement(alert_id, record, out_path, samples, trigger) -> None:
    """WT-23 trigger: evidence finalization enqueues one frame crop (lock-only).

    Enhancement never runs for alerts that never finalize evidence; anything
    that fails here is logged, never raised into the evidence path.
    """
    _service, scheduler = _get_enhancement()
    if _service is None or scheduler is None or not samples:
        return
    try:
        clip_sha = (record or {}).get("clipSha256")
        if not isinstance(clip_sha, str) or clip_sha in ("", "N/A"):
            return
        _stamp, frame = min(samples, key=lambda item: abs(item[0] - trigger))
        height, width = frame.shape[:2]
        alert = state.get_alert(alert_id) or {"id": alert_id}
        camera_id = alert.get("cameraId") or alert.get("camera_id")
        crop = CropRef(
            alert_id=alert_id,
            camera_id=camera_id,
            subject_kind="frame",
            bbox_xyxy=(0, 0, width - 1, height - 1),
        )
        enqueue_alert_enhancement(
            scheduler,
            alert_id=alert_id,
            camera_id=camera_id,
            crops=[(crop, frame)],
            parent_path=str(out_path),
            parent_sha256=clip_sha,
            parent_hash_basis=HASH_BASIS_FILE,
        )
    except Exception:
        logging.getLogger(__name__).warning(
            "enhancement enqueue failed for %s", alert_id, exc_info=False)

# SC-10: ``openrouter_reporting`` is an optional integration module that is not
# part of the committed tree. When it is unavailable the reporting endpoints
# stay registered and report an explicit DISABLED state; the offline/local
# report path keeps working unchanged.
DeepSeekReportService = None  # type: ignore[assignment,misc]
_OPENROUTER_IMPORT_ERROR: str | None = None
try:
    try:
        from .openrouter_reporting import DeepSeekReportService  # type: ignore[no-redef]
    except ImportError:
        from openrouter_reporting import DeepSeekReportService  # type: ignore[no-redef]
except ImportError as _exc:
    _OPENROUTER_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"


class _DisabledDeepSeekReportService:
    """Explicit DISABLED stand-in for the optional DeepSeek/OpenRouter service.

    Never silently pretends to work: ``status()`` reports the DISABLED state and
    generation raises a clear message that the API maps to HTTP 503.
    """

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def status(self) -> dict[str, Any]:
        return {
            "available": False,
            "state": "DISABLED",
            "apiKeyPresent": False,
            "reason": self._reason,
        }

    def demo_alert(self) -> dict[str, Any]:
        # Fed into ``generate``, which refuses with the DISABLED reason; kept as a
        # dict so callers cannot crash before reaching that refusal.
        return {}

    def generate(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ValueError(self._reason)

    def get_cached(self, _alert_id: str) -> None:
        return None


if DeepSeekReportService is None:
    deepseek_service = _DisabledDeepSeekReportService(
        "DeepSeek/OpenRouter reporting is DISABLED: module 'openrouter_reporting' "
        f"is not installed ({_OPENROUTER_IMPORT_ERROR})"
    )
else:
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
_REPORT_GENERATION_LOCK = threading.Lock()
audio_analyzer = None
go2rtc_bridge: Go2RTCBridge | None = None
# WT-17 (S-09/F-37): optional go2rtc sidecar wrapper (SC-10 explicit-health pattern).
go2rtc_sidecar = None
_webrtc_manager = None


def _authorize_request(request: Request, required_role: str = "viewer") -> str:
    controller = security_controller
    if controller is None:
        raise HTTPException(status_code=503, detail="Access control is not initialized")
    return controller.authorize(request, required_role=required_role)


def _init_engines():
    global telegram_notifier, fusion_engine, weapon_engine, security_controller
    global audit_logger, evidence_ledger, audio_analyzer

    if telegram_notifier is not None:
        print("[Engines] Already initialized.")
        return

    print("[Engines] Importing dependencies...")
    imports = _get_imports()
    # G-06: refuse to start without a calibration artifact (loud dev override only).
    imports['enforce_startup_calibration'](base_dir=BASE_DIR)
    print("[Engines] Dependencies imported.")

    telegram_notifier = imports['TelegramNotifier'].from_settings(config, os.environ)
    fusion_engine = imports['ThreatFusionEngine'].from_settings(config)
    weapon_engine = imports['WeaponSignalEngine'].from_settings(config, os.environ)
    security_controller = imports['AccessController'].from_settings(config, os.environ)
    audit_logger = imports['AuditLogger'].from_settings(config, BASE_DIR)
    evidence_ledger = imports['EvidenceLedger'].from_settings(config, BASE_DIR)
    # WT-23 seam: build the enhancement service + scheduler right after the
    # evidence ledger exists (F-52/F-53); the scheduler thread itself starts
    # and stops in lifespan.
    _get_enhancement()
    audio_analyzer = imports['AudioRiskAnalyzer'].from_settings(config)
    global go2rtc_bridge
    if Go2RTCBridge is None:
        print(f"[Engines] go2rtc_bridge DISABLED: {_GO2RTC_IMPORT_ERROR or 'module unavailable'}")
    else:
        go2rtc_bridge = Go2RTCBridge(config, os.environ)
        go2rtc_bridge.start()


def feature_health() -> dict[str, Any]:
    """Explicit availability state for optional integration modules (SC-10).

    A missing optional module must never be silent: each entry reports
    ``state`` (READY/DISABLED) plus the captured import error as ``reason``.
    """
    bridge_available = Go2RTCBridge is not None
    reporting_available = DeepSeekReportService is not None
    return {
        "go2rtcBridge": {
            "module": "go2rtc_bridge",
            "state": "READY" if bridge_available else "DISABLED",
            "running": bool(go2rtc_bridge is not None and getattr(go2rtc_bridge, "is_running", False)),
            "reason": None if bridge_available else (_GO2RTC_IMPORT_ERROR or "module unavailable"),
        },
        "openrouterReporting": {
            "module": "openrouter_reporting",
            "state": "READY" if reporting_available else "DISABLED",
            "reason": None if reporting_available else (_OPENROUTER_IMPORT_ERROR or "module unavailable"),
        },
        # WT-17 (S-09/F-37) additive: go2rtc sidecar health (F-37 recommended path).
        "go2rtcSidecar": (go2rtc_sidecar.health() if go2rtc_sidecar is not None else {
            "module": "go2rtc_sidecar",
            "state": "DISABLED",
            "running": False,
            "reason": "sidecar not initialized (webrtc.enabled is false by default: no measured WebRTC latency row yet)",
        }),
    }


def _webrtc_bridge_unavailable_detail() -> str:
    """Stable error detail for WebRTC routes when the bridge is unavailable."""
    if _GO2RTC_IMPORT_ERROR:
        return "WebRTC bridge DISABLED: go2rtc_bridge module is not installed"
    return "WebRTC not available"
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
    cooldown: float = Field(..., ge=0.0, le=120.0)

class TriageRequest(BaseModel):
    """WT-25: the action verb only; the acting role is taken from the
    authenticated session, never from the request body."""
    action: str = Field(..., min_length=1, max_length=32)

class AudioAnalysisRequest(BaseModel):
    # Bounded (≈6 MB decoded WAV) so a caller cannot force an arbitrary base64
    # decode; see the WT-28 security audit mutation inventory.
    audio_base64: str = Field(..., max_length=8_000_000)
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
        self._frame_condition = threading.Condition(self._frames_lock)
        self._frame_sequences = {}
        # WT-17 (S-09): per-frame capture stamps for freshness metadata; kept
        # process-internal (only durations leave the wire, never raw stamps).
        self._frame_captured_at = {}
        self._frame_clock_base = {}
        self._camera_health_lock = threading.Lock()
        self._camera_health = {}

        self._aq_lock = threading.Lock()
        self._alert_queues: list[queue.Queue] = []

        self._evidence_lock = threading.Lock()
        self._evidence_status: Dict[str, str] = {}

        self._alert_lock = threading.Lock()
        self._alerts: Dict[str, dict] = {}

        self._report_lock = threading.Lock()
        self._report_texts: Dict[str, str] = {}
        self._report_sources: Dict[str, str] = {}

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
        self._current_threshold = load_decision_config().violence_threshold
        self._pipelines_lock = threading.Lock()
        self._pipelines: set[ViolenceInferencePipeline] = set()

        self._camera_lock = threading.Lock()
        self._pending_switch: Optional[Tuple[Union[str, int], str]] = None
        self._current_cam_id = DEFAULT_CAMERA_ID

        self._cooldown_lock = threading.Lock()
        self._cooldown = load_decision_config().cooldown_seconds

        self._decision_lock = threading.RLock()
        self._decision_config = load_decision_config()
        self._confirmation_margin = self._decision_config.confirm_threshold - self._decision_config.watch_threshold
        self._decision_layer = LiveAlertDecisionLayer(config=self._decision_config)
        self._decision_layers = {DEFAULT_CAMERA_ID: self._decision_layer}

        # Per-worker stop events for on-demand (example/demo) camera workers
        self._worker_stop_lock = threading.Lock()
        self._worker_stop_events: Dict[str, threading.Event] = {}

        self.running = False

    def set_frame(self, camera_id: str, jpg: bytes, captured_at: float | None = None,
                  clock_base: str = "monotonic-gettickcount64") -> int:
        with self._frames_lock:
            self._frame_jpgs[camera_id] = jpg
            self._frame_captured_at[camera_id] = captured_at
            self._frame_clock_base[camera_id] = clock_base
            self._frame_sequences[camera_id] = self._frame_sequences.get(camera_id, 0) + 1
            sequence = self._frame_sequences[camera_id]
            self._frame_condition.notify_all()
        # Update heartbeat
        with self._cam_stats_lock:
            self._camera_heartbeats[camera_id] = time.time()
        return sequence

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

    def broadcast_person_data(self, camera_id: str, person_count: int, track_ids: list[str], is_threat: bool, video_width: int = 0, video_height: int = 0,
                              visible_person_count: int = 0, active_track_count: int = 0,
                              unique_person_estimate_window: dict | None = None,
                              track_failure_flags: dict | None = None, person_tracker: str = ""):
        # `personCount` remains for existing consumers and is documented as the
        # alias of `activeTrackCount` (SC-2 additive change).
        payload = {
            "type": "person_detection",
            "cameraId": camera_id,
            "personCount": person_count,
            "trackIds": track_ids,
            "isThreat": is_threat,
            "videoWidth": video_width,
            "videoHeight": video_height,
            "visiblePersonCount": visible_person_count,
            "activeTrackCount": active_track_count,
            "uniquePersonEstimateWindow": estimate_window_to_wire(unique_person_estimate_window),
            "trackFailureFlags": dict(track_failure_flags or {}),
            "personTracker": person_tracker,
            "trackNamespace": camera_id,
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

    def get_decision_config(self):
        with self._decision_lock:
            return self._decision_config

    def decision_for_camera(self, camera_id):
        with self._decision_lock:
            if camera_id not in self._decision_layers:
                self._decision_layers[camera_id] = LiveAlertDecisionLayer(config=self._decision_config)
            return self._decision_layers[camera_id]

    def apply_decision_config(self, policy):
        if not isinstance(policy, DecisionConfig):
            raise TypeError("Expected validated DecisionConfig")
        # Runtime policy, camera decisions and public aliases form one update.
        # Setters also use this reentrant lock, preventing lost concurrent edits.
        with self._decision_lock:
            self._decision_config = policy
            for layer in self._decision_layers.values():
                layer.apply_config(policy)
            with self._threshold_lock:
                self._current_threshold = policy.violence_threshold
            with self._cooldown_lock:
                self._cooldown = policy.cooldown_seconds
            with self._pipelines_lock:
                for pipeline in self._pipelines:
                    pipeline.threshold = policy.violence_threshold
            engine = globals().get('fusion_engine')
            if engine is not None:
                engine.apply_config(policy)

    def set_threshold(self, value: float) -> float:
        with self._decision_lock:
            current = self._decision_config
            self.apply_decision_config(current.with_updates(violence_threshold=value,
                watch_threshold=value, confirm_threshold=min(1.0, value + self._confirmation_margin)))
        return value

    def wait_for_frame(self, camera_id, after_sequence, timeout=1.0):
        with self._frame_condition:
            self._frame_condition.wait_for(lambda: self._frame_sequences.get(camera_id, 0) > after_sequence, timeout)
            return (self._frame_sequences.get(camera_id, 0), self._frame_jpgs.get(camera_id),
                    self._frame_captured_at.get(camera_id), self._frame_clock_base.get(camera_id))

    def set_camera_health(self, camera_id, status, reason, details=None):
        # [WT-14] additive F-38 detail block (negotiated mode + capture
        # counters) merges into the stored entry; call sites without details
        # keep the historical {'status','reason'} surface plus prior details.
        with self._camera_health_lock:
            entry = self._camera_health.setdefault(camera_id, {})
            entry['status'] = status
            entry['reason'] = reason
            if details:
                entry.update(details)

    def get_camera_health(self, camera_id):
        with self._camera_health_lock:
            return dict(self._camera_health.get(camera_id, {'status': 'UNAVAILABLE', 'reason': 'Source has not started'}))

    def get_threshold(self) -> float:
        with self._threshold_lock:
            return self._current_threshold

    def set_cooldown(self, value: float) -> float:
        with self._decision_lock:
            self.apply_decision_config(self._decision_config.with_updates(cooldown_seconds=value))
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

    def store_report_text(self, alert_id: str, report_text: str, source: str = "model"):
        normalized_source = "local_facts" if source == "local_facts" else "model"
        with self._report_lock:
            self._report_texts[alert_id] = report_text
            self._report_sources[alert_id] = normalized_source

    def get_report_text(self, alert_id: str) -> Optional[str]:
        with self._report_lock:
            return self._report_texts.get(alert_id)

    def get_report_source(self, alert_id: str) -> Optional[str]:
        with self._report_lock:
            return self._report_sources.get(alert_id)

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
            for layer in self._decision_layers.values():
                layer.reset()
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

# WT-24 S-07 [additive]: serializes publish + chain-append so a duplicate
# alert id can never overwrite a chained artifact or fork the hash chain.
_evidence_publish_lock = threading.Lock()


def _write_evidence_clip(
    alert_id,
    pre_frames,
    post_queue,
    fps,
    width,
    height,
    cancel_event=None,
    clock_domain="monotonic",
):
    """Resample timestamps, encode a verified browser MP4, then publish atomically."""
    try:
        from .evidence_video import (
            EvidenceEncodingCancelled,
            EvidenceVideoError,
            encode_browser_mp4,
        )
        from .evidence import EvidenceIntegrityError, sha256_file
    except ImportError:
        from evidence_video import (
            EvidenceEncodingCancelled,
            EvidenceVideoError,
            encode_browser_mp4,
        )
        from evidence import EvidenceIntegrityError, sha256_file

    _validate_alert_id(alert_id)
    out_path = EVIDENCE_DIR / f"{alert_id}.mp4"
    temporary = EVIDENCE_DIR / f"{alert_id}.part.mp4"
    state.mark_evidence(alert_id, "writing")
    samples = []
    try:
        fps = float(fps)
        if not np.isfinite(fps):
            raise ValueError("Evidence FPS must be finite")
        fps = max(1.0, min(120.0, fps))
        for index, item in enumerate(pre_frames):
            samples.append(item if isinstance(item, tuple) else (index / fps, item))
        trigger = samples[-1][0] if samples else time.monotonic()
        deadline = trigger + 5.0
        end_reason = "stalled"
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise EvidenceEncodingCancelled("Evidence collection cancelled")
            try:
                item = post_queue.get(timeout=1.0)
            except queue.Empty:
                # The producer went silent before the post window closed.
                end_reason = "stalled"
                break
            if item is None:
                # Explicit stream close (shutdown or media-loop boundary).
                end_reason = "stream-closed"
                break
            stamp, frame = item if isinstance(item, tuple) else (
                (samples[-1][0] + 1 / fps) if samples else trigger,
                item,
            )
            if not samples or stamp > samples[-1][0]:
                samples.append((stamp, frame))
            if stamp >= deadline:
                end_reason = "deadline"
                break
        if not samples:
            raise ValueError("No evidence frames")
        height, width = samples[0][1].shape[:2]
        start, end = samples[0][0], samples[-1][0]
        if not np.isfinite(start) or not np.isfinite(end) or end < start:
            raise ValueError("Evidence timestamps must be finite and ordered")
        count = max(1, round((end - start) * fps) + 1)
        selected = 0
        output_frames = []
        for index in range(count):
            stamp = start + index / fps
            while (
                selected + 1 < len(samples)
                and abs(samples[selected + 1][0] - stamp)
                <= abs(samples[selected][0] - stamp)
            ):
                selected += 1
            output_frames.append(samples[selected][1])

        encoded = encode_browser_mp4(
            output_frames,
            temporary,
            fps=fps,
            width=width,
            height=height,
            timeout_seconds=12.0,
            cancel_event=cancel_event,
        )
        # The post window is complete only if collection reached the planned
        # deadline; anything shorter is published as an explicit partial clip,
        # never as a silently short "ready" one (G-08).
        post_complete = bool(end >= deadline)
        clip_meta = {
            "clipFrameCount": encoded.frame_count,
            "clipFps": fps,
            "clipWidth": encoded.width,
            "clipHeight": encoded.height,
            "clipDurationSeconds": round(encoded.frame_count / fps, 6),
            "clipSourceSpanSeconds": round(end - start, 6),
            "clipPreEventSpanSeconds": round(max(0.0, trigger - start), 6),
            "clipPostEventSpanSeconds": round(max(0.0, end - trigger), 6),
            "clipCodec": encoded.codec,
            "clipPixelFormat": encoded.pixel_format,
            "clipFastStart": encoded.fast_start,
            "clipEncoder": encoded.encoder,
            "clipFrameMaxSide": max(encoded.width, encoded.height),
            "clipCaptureClockDomain": str(clock_domain or "monotonic"),
            "clipComplete": post_complete,
            "clipPartialReason": None if post_complete else end_reason,
            "snapshotEncoding": "jpeg" if state.get_snapshot_path(alert_id) else None,
        }
        with _evidence_publish_lock:
            existing = evidence_ledger.get(alert_id)
            if existing is not None:
                # Duplicate alert id: a chained artifact is never overwritten.
                temporary.unlink(missing_ok=True)
                chained = existing.get("clipSha256")
                intact = (
                    existing.get("clipHashStatus", "hashed") == "hashed"
                    and isinstance(chained, str)
                    and chained != "N/A"
                    and out_path.exists()
                    and sha256_file(out_path) == chained
                )
                if intact:
                    state.mark_evidence(
                        alert_id,
                        "ready" if existing.get("clipComplete", True) else "partial",
                    )
                    audit_logger.record(
                        "evidence_clip_duplicate",
                        "warning",
                        role="system",
                        alert_id=alert_id,
                        details={"kept": "chained-artifact", "discarded": "second-writer-clip"},
                    )
                else:
                    state.mark_evidence(alert_id, "error")
                    audit_logger.record(
                        "evidence_clip_conflict",
                        "error",
                        role="system",
                        alert_id=alert_id,
                        details={
                            "errorType": "EvidenceConflict",
                            "errorCode": "duplicate_alert_id_conflict",
                        },
                    )
                return
            # Publish atomically: fsync the verified temp file, then rename.
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())
            temporary.replace(out_path)
            alert = state.get_alert(alert_id) or {"id": alert_id}
            report = state.get_report_text(alert_id) or ""
            record = evidence_ledger.append_entry(
                alert=alert,
                clip_path=out_path,
                snapshot_path=state.get_snapshot_path(alert_id),
                report_path=None,
                report_text=report,
                clip_meta=clip_meta,
            )
            if record.get("clipHashStatus") != "hashed":
                # The primary artifact must be chained with a real SHA-256;
                # withdraw the publication instead of leaving it unchained.
                out_path.unlink(missing_ok=True)
                raise EvidenceIntegrityError("published clip could not be hashed into the chain")
        state.mark_evidence(alert_id, "ready" if post_complete else "partial")
        audit_logger.record(
            "evidence_clip_ready",
            "success",
            role="system",
            alert_id=alert_id,
            details={
                "durationSeconds": encoded.frame_count / fps,
                "sourceSpanSeconds": end - start,
                "frames": encoded.frame_count,
                "fps": fps,
                "width": encoded.width,
                "height": encoded.height,
                "codec": encoded.codec,
                "pixelFormat": encoded.pixel_format,
                "fastStart": encoded.fast_start,
                "encoder": encoded.encoder,
                "postWindowComplete": post_complete,
                "clipPartialReason": None if post_complete else end_reason,
                "browserVerified": False,
            },
        )
        # WT-23: the trigger is evidence finalization (lock-only enqueue).
        _schedule_alert_enhancement(alert_id, record, out_path, samples, trigger)
    except Exception as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            logging.warning("Could not remove incomplete evidence for %s", alert_id)
        state.mark_evidence(alert_id, "error")
        error_code = (
            exc.code if isinstance(exc, EvidenceVideoError) else "evidence_finalization_error"
        )
        logging.error("Evidence finalization failed for %s (%s)", alert_id, error_code)
        audit_logger.record(
            "evidence_clip_failed",
            "error",
            role="system",
            alert_id=alert_id,
            details={"errorType": type(exc).__name__, "errorCode": error_code},
        )


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
    face_summary: Optional[dict] = None,
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

    if face_summary:
        # SC-2 additive: optional face context travels with the threat payload.
        # Empty/absent input adds no key (payload shape unchanged for callers
        # that do not supply it).
        payload["faceSummary"] = face_summary

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
    """Configured camera indices and network streams use capture-time semantics."""
    return isinstance(source, int) or (isinstance(source, str) and source.lower().startswith(("rtsp://", "rtmp://", "http://", "https://")))

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

# [WT-14] The stale-frame drain helper that lived here is superseded by
# pipeline_capture.CaptureThread._drain_to_latest (wired for live network
# sources, budget-bounded, keeps the freshest grabbed frame).

INFERENCE_MAX_RESTARTS = 3
INFERENCE_RESTART_WINDOW_SECONDS = 60.0
INFERENCE_RESTART_BACKOFF_SECONDS = (0.25, 0.5, 1.0)


def _drain_ipc_queue(channel, max_items: int = 1024) -> int:
    """Drain a bounded IPC queue, including benchmark probe wrappers."""
    drain_channel = getattr(channel, "wrapped", channel)
    getter = getattr(drain_channel, "get_nowait", None)
    if getter is None:
        return 0
    drained = 0
    while drained < max_items:
        try:
            getter()
        except queue.Empty:
            break
        except (EOFError, OSError):
            break
        drained += 1
    return drained


class _GenerationResultQueue:
    """Render-side view that rejects results from a retired child process."""

    def __init__(self, channel, generation_ref):
        self._channel = channel
        self._generation_ref = generation_ref

    def get_nowait(self):
        # The underlying result queue is bounded, so this filter is bounded too.
        for _ in range(32):
            result = self._channel.get_nowait()
            if not isinstance(result, dict):
                return result
            generation = result.get("inference_generation")
            current = self._generation_ref["value"]
            if generation == current or (generation is None and current == 0):
                return result
        raise queue.Empty


def _request_media_epoch_reset(*, ready_event, reset_event, reset_ack, generation_ref) -> bool:
    """Advance the parent generation before asking a ready child to reset."""
    if ready_event is None or not ready_event.is_set():
        return False
    reset_ack.clear()
    generation_ref["value"] += 1
    reset_event.set()
    return True


def _restart_inference_child(*, camera_id, old_process, old_stop_event,
                             frame_queue, result_queue, inference_worker,
                             base_config, outer_stop_event, restart_times,
                             reset_parent_state, process_factory=None,
                             event_factory=None, reset_lock=None,
                             generation_ref=None):
    """Replace a failed child after reaping it and retiring its IPC generation."""
    if outer_stop_event.is_set():
        return None

    now = time.monotonic()
    while restart_times and now - restart_times[0] >= INFERENCE_RESTART_WINDOW_SECONDS:
        restart_times.popleft()
    if len(restart_times) >= INFERENCE_MAX_RESTARTS:
        logging.error("Inference restart budget exhausted for %s", camera_id)
        return None

    if old_stop_event is not None:
        old_stop_event.set()
    try:
        old_process.join(timeout=1.0)
        if old_process.is_alive():
            old_process.terminate()
            old_process.join(timeout=1.0)
        if old_process.is_alive():
            logging.error("Inference child would overlap restart for %s", camera_id)
            return None
        if hasattr(old_process, "close"):
            old_process.close()
    except (OSError, ValueError):
        logging.exception("Inference child reap failed for %s", camera_id)
        return None

    next_generation = None

    def reset_retired_generation():
        nonlocal next_generation
        _drain_ipc_queue(frame_queue)
        _drain_ipc_queue(result_queue)
        reset_parent_state()
        if generation_ref is not None:
            generation_ref["value"] += 1
            next_generation = generation_ref["value"]

    try:
        if reset_lock is None:
            reset_retired_generation()
        else:
            with reset_lock:
                reset_retired_generation()
    except Exception:
        logging.exception("Inference restart state reset failed for %s", camera_id)
        return None

    attempt = len(restart_times)
    restart_times.append(now)
    delay = INFERENCE_RESTART_BACKOFF_SECONDS[min(attempt, len(INFERENCE_RESTART_BACKOFF_SECONDS) - 1)]
    if outer_stop_event.wait(delay):
        return None

    if process_factory is None:
        process_factory = mp.Process
    if event_factory is None:
        event_factory = mp.Event
    replacement = None
    try:
        replacement_stop = event_factory()
        replacement_ready = event_factory()
        replacement_reset = event_factory()
        replacement_reset_ack = event_factory()
        replacement_config = dict(base_config)
        replacement_config.update({
            "ready_event": replacement_ready,
            "reset_event": replacement_reset,
            "reset_ack": replacement_reset_ack,
        })
        if generation_ref is not None:
            replacement_config["inference_generation"] = next_generation
        replacement = process_factory(
            target=inference_worker,
            args=(frame_queue, result_queue, replacement_stop, replacement_config),
            daemon=True,
            name=f"inference-{camera_id}-restart-{attempt + 1}",
        )
        replacement.start()
        return (replacement, replacement_stop, replacement_ready,
                replacement_reset, replacement_reset_ack)
    except Exception:
        logging.exception("Inference child restart failed for %s", camera_id)
        try:
            if replacement is not None and replacement.is_alive():
                replacement.terminate()
                replacement.join(timeout=1.0)
        except (OSError, ValueError):
            pass
        return None


def _reset_inference_parent_state(camera_id, render_queue, renderer=None, cache=None):
    """Drop cached decisions/overlays while leaving camera evidence capture intact."""
    render_queue.clear()
    state.decision_for_camera(camera_id).reset()
    state.set_detection_meta(camera_id, {})
    if renderer is not None:
        renderer._last_result = {}
        renderer._legacy_sequence = 0
        renderer._health = {}
    if cache is not None:
        cache.update(
            tracks=[], person_count=0, is_threat=False, threat_confidence=0.0,
            weapon_score=0.0, weapon_labels=[], fps=0.0,
            violence_conf=0.0, motion_score=0.0,
        )


def _reset_file_loop_boundary(camera_id, render_queue, ring_buffer, evidence_lock,
                              active_post_queues, renderer=None, cache=None,
                              incident_capture=None):
    """Drop state that must not cross a prerecorded-media loop boundary."""
    if incident_capture is not None:
        incident_capture.end_epoch("media-loop-boundary")
    with evidence_lock:
        ring_buffer.clear()
        posts = list(active_post_queues)
        active_post_queues.clear()

    # An evidence post-window cannot span two independent loops. Close each
    # writer with the frames it already received, then let the next loop start
    # with an empty post queue.
    for post in posts:
        try:
            post.put_nowait(None)
        except queue.Full:
            try:
                post.get_nowait()
            except queue.Empty:
                pass
            try:
                post.put_nowait(None)
            except queue.Full:
                logging.warning('Evidence boundary sentinel could not be queued for %s', camera_id)

    _reset_inference_parent_state(camera_id, render_queue, renderer=renderer, cache=cache)


def camera_worker(camera_id, source, device, model_weights, threshold, stride, stop_event=None, raw_mode=False):
    """Bounded capture, timestamped IPC, per-camera decisions and joined evidence."""
    from pipeline_capture import (CaptureThread, DegradationLadder, DecodedPostQueue,
                                  bounded_put_drop_newest, capture_now, copy_if_aliased,
                                  get_capture_clock_base, make_evidence_frame,
                                  materialize_evidence_samples)
    from pipeline_render import RenderThread
    from inference_process import inference_worker
    from frame_pipeline import OverlayCache
    from temporal_frames import FramePacket, downscale_for_inference
    import inspect
    effective_stop=stop_event or state.create_worker_stop_event(camera_id)
    render_queue=deque(maxlen=3)
    frame_available=threading.Event()
    capture_profile = _load_capture_profile(camera_id)  # [WT-14] ring/reconnect/ladder tuning
    capture_clock_base = get_capture_clock_base()       # [WT-15 ASK C] published stamp base
    ring_buffer=deque(maxlen=capture_profile.ring.max_entries)
    evidence_lock=threading.Lock()
    active_post_queues=[]
    evidence_threads=[]
    frame_queue_mp=mp.Queue(maxsize=3)
    result_queue_mp=mp.Queue(maxsize=30)
    mp_stop_event=mp.Event()
    mp_ready_event=mp.Event()
    mp_reset_event=mp.Event()
    mp_reset_ack=mp.Event()
    inf_process=None
    inference_restart_times=deque()
    inference_generation={"value":0}
    render_t=None
    capture=CaptureThread(source,deque(maxlen=3),ring_buffer,effective_stop,profile=capture_profile)
    ladder=DegradationLadder(capture_profile.degradation)  # [WT-14] multi-camera ladder
    # [WT-22] incident capture: None pre-init before try so the early-return
    # path cannot NameError in finally (WT-22 integration note). The service
    # itself is wired once, inside try, from capture_queue.IncidentCapture.
    incident_capture=None
    state.set_camera_health(camera_id,'STARTING','Opening configured source')
    try:
        if not capture.open():
            state.set_camera_health(camera_id,'FAILED','Configured source could not be opened')
            return
        # [WT-14] F-38: mode mismatch is DEGRADED + exact requested-vs-actual,
        # never silent (OpenCV/OS may swap MJPG for decoded NV12/YUY2).
        if capture.negotiated is not None and capture.negotiated.mismatch:
            state.set_camera_health(
                camera_id,'DEGRADED',
                'Capture mode mismatch: '+capture.negotiated.describe()
                +' mismatched='+','.join(capture.negotiated.mismatched_fields),
                details=capture.health_details())
        else:
            state.set_camera_health(camera_id,'OK','',details=capture.health_details())
        state.decision_for_camera(camera_id).reset()
        is_file=not _is_live_source(source)
        source_fps=max(1.0,min(120.0,float(capture.fps or 30.0)))
        policy=state.get_decision_config()
        inf_config={'device':str(device),'weights_path':str(model_weights),'threshold':policy.violence_threshold,
                    'violence_stride':stride,'person_interval':int(os.getenv('PERSON_INFER_INTERVAL','3')),
                    'weapon_config':config,'person_conf_threshold':float(os.getenv('PERSON_OVERLAY_CONF','0.45')),
                    'person_overlay_enabled':_env_flag('PERSON_OVERLAY_ENABLED',True),'source_fps':source_fps,
                    'decision_config':policy.to_dict(),'capture_clock_base':capture_clock_base,'ready_event':mp_ready_event,
                    'reset_event':mp_reset_event,'inference_generation':inference_generation['value'],
                    'reset_ack':mp_reset_ack,'camera_id':camera_id}
        inf_process=mp.Process(target=inference_worker,args=(frame_queue_mp,result_queue_mp,mp_stop_event,inf_config),daemon=True,name=f'inference-{camera_id}')
        inf_process.start()
        cache=OverlayCache()
        cache.update(video_width=capture.width,video_height=capture.height)
        # Incident capture (WT-22): bounded drop-oldest queue + pre/post ring
        # sweep. All capture work runs on its own worker thread; the alert path
        # only enqueues (see RenderThread._emit_alert).
        from capture_queue import IncidentCapture
        incident_capture=IncidentCapture(
            pre_seconds=_capture_config()['pre_seconds'],post_seconds=_capture_config()['post_seconds'],
            queue_capacity=_capture_config()['queue_capacity'],camera_id=camera_id,
            record_dir=BEST_FRAMES_DIR)
        def on_detection_meta(cam_id,snap):
            state.set_detection_meta(cam_id,snap)
            _broadcast_person_counts(cam_id,snap)
        def on_threat(payload,jpeg,clip_path):
            state.register_alert(payload)
            if jpeg:
                try:
                    thumb=THUMBNAILS_DIR/f"{payload['id']}.jpg"
                    thumb.write_bytes(jpeg)
                    state.store_snapshot_path(payload['id'],str(thumb))
                    payload['thumbnailPath']=str(thumb)
                except OSError:logging.exception('Snapshot persistence failed')
            from local_forensics import build_local_report
            state.store_report_text(payload["id"], build_local_report(payload), source="local_facts")
            state.broadcast_alert(payload)
            if telegram_notifier is not None:telegram_notifier.enqueue_alert(payload,jpeg,clip_path)
        def on_evidence(alert_id,width,height,fps):
            with evidence_lock:
                pre=list(ring_buffer)
                post=queue.Queue(maxsize=360)
                active_post_queues.append(post)
                # WT-21: face capture consumes the SAME pre/post frame fan-out
                # as the evidence clip writer (consume, never duplicate the
                # ring). All face work runs on the face-capture worker thread;
                # this dispatch-path hook only enqueues (zero face work).
                face_post=queue.Queue(maxsize=360)
                active_post_queues.append(face_post)
            if pre:
                height,width=pre[-1].height,pre[-1].width  # [WT-14] EvidenceFrame record
            def writer():
                try:
                    # [WT-14] decode-at-assembly on THIS thread (~3.4 ms/frame,
                    # WT-10 P-3); _write_evidence_clip keeps its (stamp, frame)
                    # tuple contract via materialized samples + queue view.
                    samples,pre_adjusted=materialize_evidence_samples(pre)
                    canvas=(samples[0][1].shape[1],samples[0][1].shape[0]) if samples else None
                    post_view=DecodedPostQueue(post,canvas=canvas)
                    call_kwargs={}
                    if 'clock_domain' in inspect.signature(_write_evidence_clip).parameters:
                        call_kwargs['clock_domain']=get_capture_clock_base()
                    _write_evidence_clip(alert_id,samples,post_view,source_fps,width,height,**call_kwargs)
                    adjusted=pre_adjusted+post_view.adjusted
                    if adjusted:
                        capture.stats.evidence_frames_adjusted+=adjusted
                        logging.warning('Evidence window mixed sizes for %s: %d frames fitted to canvas (no upscaling)',alert_id,adjusted)
                finally:
                    with evidence_lock:
                        if post in active_post_queues:active_post_queues.remove(post)
            thread=threading.Thread(target=writer,daemon=False,name=f'evidence-{alert_id}')
            evidence_threads.append(thread)
            thread.start()
            face_svc=_get_face_service()
            if face_svc is not None:
                def _release_face_post():
                    with evidence_lock:
                        if face_post in active_post_queues:active_post_queues.remove(face_post)
                try:
                    face_svc.start_capture(
                        alert_id,camera_id,pre,face_post,
                        track_provider=lambda cam=camera_id:(state.get_detection_meta(cam) or {}).get('tracks') or [],
                        on_post_done=_release_face_post)
                except Exception:
                    logging.getLogger(__name__).warning('face capture enqueue failed',exc_info=False)
                    _release_face_post()
            else:
                with evidence_lock:
                    if face_post in active_post_queues:active_post_queues.remove(face_post)
        def _annotate_guard(frame,*args,**kwargs):
            # [WT-14] ladder step "pause_annotation" skips display overlay only;
            # the evidence ring path is never touched by this gate.
            return frame if ladder.pause_annotation else annotate_frame(frame,*args,**kwargs)
        result_queue_for_render=_GenerationResultQueue(result_queue_mp,inference_generation)
        options={'frame_queue':render_queue,'result_cache':cache,'result_queue_mp':result_queue_for_render,
                 'camera_id':camera_id,'stop_event':effective_stop,'set_frame_fn':state.set_frame,
                 'annotate_fn':_annotate_guard,'set_detection_meta_fn':on_detection_meta,
                 'on_threat_fn':on_threat,'on_evidence_trigger_fn':on_evidence,
                 'decision_layer':state.decision_for_camera(camera_id),'fusion_engine':fusion_engine,
                 'target_fps':TARGET_FPS,'jpeg_quality':JPEG_QUALITY}
        if 'frame_available' in inspect.signature(RenderThread).parameters:options['frame_available']=frame_available
        if incident_capture is not None and 'incident_capture' in inspect.signature(RenderThread).parameters:options['incident_capture']=incident_capture
        renderer=RenderThread(**options)
        render_reset_lock=threading.Lock()
        render_frame=renderer._render_frame
        def locked_render_frame(frame):
            with render_reset_lock:
                return render_frame(frame)
        renderer._render_frame=locked_render_frame
        render_t=threading.Thread(target=renderer.run,daemon=True,name=f'render-{camera_id}')
        render_t.start()
        frame_sequence=0
        source_epoch=capture_now()  # [WT-14] same published base as captured_at
        next_frame=time.perf_counter()
        fps_start=next_frame
        fps_count=0
        state.running=True
        while state.running and not effective_stop.is_set():
            if not inf_process.is_alive():
                if effective_stop.is_set():
                    break
                replacement=_restart_inference_child(
                    camera_id=camera_id,
                    old_process=inf_process,
                    old_stop_event=mp_stop_event,
                    frame_queue=frame_queue_mp,
                    result_queue=result_queue_mp,
                    inference_worker=inference_worker,
                    base_config=inf_config,
                    outer_stop_event=effective_stop,
                    restart_times=inference_restart_times,
                    reset_parent_state=lambda: _reset_inference_parent_state(
                        camera_id, render_queue, renderer=renderer, cache=cache),
                    reset_lock=render_reset_lock,
                    generation_ref=inference_generation,
                )
                if replacement is None:
                    state.set_camera_health(camera_id,'FAILED','Inference process failed after bounded restarts')
                    break
                inf_process,mp_stop_event,mp_ready_event,mp_reset_event,mp_reset_ack=replacement
                state.set_camera_health(camera_id,'DEGRADED','Inference process restarted; awaiting readiness')
                continue
            ok,raw=capture.read_frame()
            captured_at=capture_now()  # [WT-15 ASK C] published base; read-complete semantics (SC-6)
            if not ok:
                if is_file:
                    capture.cap.set(cv2.CAP_PROP_POS_FRAMES,0)
                    with render_reset_lock:
                        _reset_file_loop_boundary(
                            camera_id, render_queue, ring_buffer, evidence_lock,
                            active_post_queues, renderer=renderer, cache=cache,
                            incident_capture=incident_capture,
                        )
                        # The child increments its own generation in response
                        # to this reset; advance the render filter atomically
                        # before waking it so new-epoch results are accepted.
                        reset_requested = (
                            inf_process is not None and inf_process.is_alive() and
                            _request_media_epoch_reset(
                                ready_event=mp_ready_event,
                                reset_event=mp_reset_event,
                                reset_ack=mp_reset_ack,
                                generation_ref=inference_generation,
                            )
                        )
                    # A short replay may reach EOF before the child is ready.
                    # In that case no child reset is needed; a ready child must
                    # acknowledge before capture admits the next media epoch.
                    if reset_requested:
                        if not mp_reset_ack.wait(timeout=2.0):
                            state.set_camera_health(
                                camera_id, 'DEGRADED',
                                'Inference reset did not complete at media boundary',
                            )
                            break
                        with render_reset_lock:
                            state.decision_for_camera(camera_id).reset()
                            renderer._last_result = {}
                    next_frame=time.perf_counter()
                    source_epoch=capture_now()  # [WT-14] same published base as captured_at
                    capture.reset_media_timeline()  # [WT-14] media clock restarts with the media
                    continue
                # [WT-14] explicit interrupted state; reconnect() now backs off
                # exponentially with jitter (1..30s) instead of a fixed 2s sleep.
                state.set_camera_health(camera_id,'DEGRADED','Capture interrupted; reconnecting with backoff',
                                        details=capture.health_details())
                capture.reconnect()
                continue
            if capture.capture_state=='ok':
                if mp_ready_event.is_set():
                    state.set_camera_health(camera_id,'OK','')
                else:
                    state.set_camera_health(camera_id,'DEGRADED','Capture active; inference child is starting')
            frame_sequence+=1
            # [WT-14] sample_timestamp rides the MEDIA frame index (skipped
            # frames count): a file-skip run can never masquerade as N frames
            # at source_fps (EXP-1402 defect fix; SC-6 media-clock semantics).
            sample_timestamp=source_epoch+capture.last_media_index/source_fps if is_file else None
            # Display is annotated on a separate copy; perception/evidence stay raw.
            render_queue.append({"frame": raw.copy(), "captured_at": captured_at, "clock_base": capture_clock_base})
            frame_available.set()
            # [WT-14] evidence ring: format-tagged records (bgr|jpeg90|nv12);
            # ladder decimation is COUNTED — evidence frames never vanish silently.
            ring_cfg=ladder.ring_config(capture_profile.ring)
            if ladder.should_append(frame_sequence,source_fps):
                evidence_view=downscale_for_inference(raw,ring_cfg.max_side)
                evidence_frame=make_evidence_frame(evidence_view,raw,ring_cfg.format,captured_at,frame_sequence,jpeg_quality=ring_cfg.jpeg_quality)
                with evidence_lock:
                    ring_buffer.append(evidence_frame)
                    while ring_buffer and captured_at-ring_buffer[0].captured_at>ring_cfg.seconds:ring_buffer.popleft()
                    posts=list(active_post_queues)
                for post in posts:
                    try:post.put_nowait(evidence_frame)
                    except queue.Full:logging.warning('Evidence frame queue full for %s',camera_id)
            else:
                capture.stats.evidence_frames_decimated+=1
            # [WT-14] E-6: the inference view owns its buffer (passthrough alias
            # copied; resize output stays single-produce) — evidence never
            # aliases it. [WT-22] incident capture samples this view (None-guarded).
            small=copy_if_aliased(downscale_for_inference(raw,640),raw)
            if incident_capture is not None:
                try:
                    incident_capture.feed(captured_at,small,frame_sequence=frame_sequence,sample_timestamp=sample_timestamp,native_frame=raw)
                except TypeError:
                    incident_capture.feed(captured_at,small)
            packet=FramePacket(small,frame_sequence,captured_at,raw.shape[1],raw.shape[0],source_fps,state.get_decision_config().to_dict(),sample_timestamp=sample_timestamp)
            # [WT-14] R-2 closure: drop-NEWEST on full queue is counted and
            # surfaced (frameQueueDropped); sequence increments regardless.
            bounded_put_drop_newest(frame_queue_mp,packet,capture.stats)
            fps_count+=1
            now=time.perf_counter()
            if now-fps_start>=1:
                cache.update(fps=fps_count/(now-fps_start))
                # [WT-14] 1 Hz: ladder pressure probe + F-38 detail refresh.
                # Pressure = last read gap beyond 2.5x the nominal frame period
                # (cadence shortfall under multi-camera load) -> 'partial'.
                nominal_ms=1000.0/source_fps
                gaps=capture.stats.read_gaps_ms
                healthy=(not gaps) or gaps[-1]<=max(100.0,2.5*nominal_ms)
                if not healthy and capture.capture_state=='ok':
                    capture.capture_state='partial'
                elif healthy and capture.capture_state=='partial':
                    capture.capture_state='ok'
                ladder.observe(healthy)
                inference_ready=mp_ready_event.is_set()
                status='OK' if capture.capture_state=='ok' and inference_ready else 'DEGRADED'
                reason=("" if status=='OK' else
                        'Capture '+capture.capture_state if capture.capture_state!='ok' else
                        'Capture active; inference child is starting')
                state.set_camera_health(
                    camera_id,status,reason,
                    details={**capture.health_details(),**ladder.snapshot()})
                fps_count=0
                fps_start=now
            if is_file:
                next_frame+=1/source_fps
                if now-next_frame>1/source_fps:next_frame=now
                effective_stop.wait(max(0,next_frame-time.perf_counter()))
    except Exception:
        logging.exception('Camera pipeline failed: %s',camera_id)
        state.set_camera_health(camera_id,'FAILED','Camera pipeline raised an exception')
    finally:
        effective_stop.set()
        frame_available.set()
        mp_stop_event.set()
        capture.release()
        with evidence_lock:posts=list(active_post_queues)
        for post in posts:
            try:post.put(None,timeout=.2)
            except queue.Full:logging.warning('Evidence queue full during shutdown: %s',camera_id)
        if render_t is not None:render_t.join(timeout=2)
        if incident_capture is not None:
            try:incident_capture.stop(timeout=2)
            except Exception:logging.exception('Incident capture shutdown failed: %s',camera_id)
        for thread in evidence_threads:thread.join(timeout=4)
        if inf_process is not None:
            inf_process.join(timeout=4)
            if inf_process.is_alive():
                inf_process.terminate()
                inf_process.join(timeout=2)
        for channel in (frame_queue_mp,result_queue_mp):
            if hasattr(channel,'cancel_join_thread'):channel.cancel_join_thread()
            if hasattr(channel,'close'):channel.close()
        if state.get_camera_health(camera_id)['status'] not in {'FAILED', 'DEGRADED'}:
            state.set_camera_health(camera_id,'STOPPED','Source stopped')


_ALERT_ID_RE = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}')

def _validate_alert_id(alert_id: str) -> None:
    """Reject alert_id that could escape intended storage directories.

    Raises HTTPException 400 if the format is invalid.
    The regex whitelist is the primary guard; the explicit substring check
    is a secondary defense-in-depth layer.
    """
    if not _ALERT_ID_RE.fullmatch(alert_id):
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
    # WT-23 seam: lifespan start — the post-alert enhancement scheduler (F-52).
    _enh_service, _enh_scheduler = _get_enhancement()
    if _enh_scheduler is not None:
        _start_enhancement_scheduler()
        print("[System] enhancement scheduler started (WT-23, tier-0 only)")
    else:
        print(f"[System] enhancement DISABLED: {_ENHANCE_IMPORT_ERROR or _enhancement_build_error or 'module unavailable'}")
    if not security_controller.config.api_key:
        print(
            "ADMIN_API_KEY is empty; protected mutation routes are disabled. Configure server authentication to enable controls."
        )
    _init_category_detector()

    global _webrtc_manager, go2rtc_sidecar
    try:
        from webrtc_streamer import WebRTCManager, Go2RTCSidecar
        _webrtc_manager = WebRTCManager()
        print(f"[System] WebRTC manager ready (available={_webrtc_manager.available})")
        # WT-17 (S-09/F-37): optional go2rtc sidecar. Absent/disabled is explicit,
        # never silent (SC-10); default webrtc.enabled=false keeps this DISABLED.
        go2rtc_sidecar = Go2RTCSidecar(config, os.environ)
        sidecar_health = go2rtc_sidecar.start()
        print(f"[System] go2rtc sidecar {sidecar_health['state']}"
              + (f": {sidecar_health['reason']}" if sidecar_health.get("reason") else ""))
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
    # WT-23 seam: lifespan stop — drain/stop the enhancement scheduler.
    _enh_service, _enh_scheduler = _get_enhancement()
    if _enh_scheduler is not None:
        _enh_scheduler.stop(timeout=2)
    if go2rtc_bridge:
        go2rtc_bridge.stop()
    if _webrtc_manager is not None:
        try:
            await _webrtc_manager.close_all()
        except Exception:
            pass

# ── WT-26 additive (flagged SC-1 hunk) ───────────────────────────────────────
# Evidence-ledger statistics for the overview; counting semantics in
# docs/campaign/engineering/26-stats-semantics.md §2.2. One GET /stats/overview.
try:
    from .stats_service import build_stats_router
except ImportError:
    from stats_service import build_stats_router

app = FastAPI(lifespan=lifespan, title="AI Sentinel Advanced Backend")
app.include_router(build_stats_router(lambda: evidence_ledger, lambda: security_controller))
app.add_middleware(
    CORSMiddleware,
    allow_origins=config['server']['cors_origins'],
    allow_methods=["*"],
    allow_headers=["*"]
)

async def _mjpeg_generator(camera_id: str) -> AsyncGenerator[bytes, None]:
    try:
        sequence = 0
        while True:
            latest, jpg, captured_at, clock_base = await asyncio.to_thread(state.wait_for_frame, camera_id, sequence, 1.0)
            if latest > sequence and jpg:
                sequence = latest
                # WT-17 (S-09): per-part frame identity + freshness. Additive headers:
                # <img> consumers ignore them; identity-aware readers correlate with the
                # /detections frameSequence and compute display-side age.
                headers = f"X-Frame-Sequence: {latest}\r\n".encode()
                if isinstance(captured_at, (int, float)):
                    base = "perf-qpc" if clock_base == "perf-qpc" else "monotonic-gettickcount64"
                    age_stamp = time.perf_counter() if clock_base == "perf-qpc" else time.monotonic()
                    age_ms = max(0.0, (age_stamp - captured_at) * 1000.0)
                    headers += f"X-Frame-Age-Ms: {age_ms:.1f}\r\nX-Frame-Age-Clock-Base: {base}\r\n".encode()
                yield b"--frame\r\nContent-Type: image/jpeg\r\n" + headers + b"\r\n" + jpg + b"\r\n"
    finally:
        _release_stream_slot()

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
        _release_stream_slot()

# ── Unauthenticated read streams: documented public-read policy with limits ──
# EventSource cannot carry X-API-Key, so /alerts and /detections (and the MJPEG
# fallback) are documented public reads (wt-28 audit P2). They are bounded by a
# global concurrent-stream cap plus a per-client connection rate limit, both
# answering HTTP 429 with Retry-After. All mutations remain credential-gated.
_STREAM_LIMITS = {
    "sse": {"max_subscribers": 32, "per_client_per_minute": 60},
    "mjpeg": {"max_subscribers": 64, "per_client_per_minute": 120},
}
_stream_lock = threading.Lock()
_stream_subscribers = 0
_stream_attempts: dict[str, list[float]] = {}
_STREAM_RATE_WINDOW_SECONDS = 60.0


def _acquire_stream_slot(request: Request, kind: str = "sse") -> None:
    """Bound public read streams (concurrency cap + per-client connection rate)."""
    global _stream_subscribers
    limits = _STREAM_LIMITS.get(kind, _STREAM_LIMITS["sse"])
    client_key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _stream_lock:
        if _stream_subscribers >= limits["max_subscribers"]:
            raise HTTPException(
                status_code=429,
                detail="Too many concurrent streams",
                headers={"Retry-After": "5"},
            )
        recent = [t for t in _stream_attempts.get(client_key, []) if now - t < _STREAM_RATE_WINDOW_SECONDS]
        if len(recent) >= limits["per_client_per_minute"]:
            raise HTTPException(
                status_code=429,
                detail="Stream connection rate exceeded",
                headers={"Retry-After": "30"},
            )
        recent.append(now)
        _stream_attempts[client_key] = recent
        _stream_subscribers += 1


def _release_stream_slot() -> None:
    global _stream_subscribers
    with _stream_lock:
        _stream_subscribers = max(0, _stream_subscribers - 1)

# ── WebRTC / go2rtc Proxy Endpoints ──────────────────────────────────────────

@app.get("/api/webrtc/{cam_id}", summary="Get WebRTC stream metadata for camera")
async def webrtc_stream(cam_id: str, request: Request):
    _authorize_request(request, required_role="viewer")
    if not go2rtc_bridge or not go2rtc_bridge.is_running:
        raise HTTPException(status_code=503, detail=_webrtc_bridge_unavailable_detail())
    whep_url = go2rtc_bridge.get_whep_url(cam_id)
    if not whep_url:
        raise HTTPException(status_code=404, detail="Stream not found")
    # Keep negotiation on this authenticated API origin; do not disclose the
    # sidecar's unauthenticated WHEP endpoint to the browser.
    return {"cam_id": cam_id, "url": str(request.url_for("webrtc_whep_offer", cam_id=cam_id)), "protocol": "webrtc"}

@app.post("/api/webrtc/{cam_id}/whep", summary="Proxy WHEP SDP offer to go2rtc")
async def webrtc_whep_offer(cam_id: str, request: Request):
    _authorize_request(request, required_role="admin")
    if not go2rtc_bridge or not go2rtc_bridge.is_running:
        raise HTTPException(status_code=503, detail=_webrtc_bridge_unavailable_detail())
    body = await request.body()
    status, response_body = go2rtc_bridge.proxy_whep(
        cam_id, "POST", body.decode() if body else None, "application/sdp"
    )
    if status != 200:
        raise HTTPException(status_code=status, detail="WHEP negotiation failed")
    return Response(content=response_body, media_type="application/sdp")

@app.patch("/api/webrtc/{cam_id}/whep", summary="Proxy ICE trickle to go2rtc")
async def webrtc_whep_ice(cam_id: str, request: Request):
    _authorize_request(request, required_role="admin")
    if not go2rtc_bridge or not go2rtc_bridge.is_running:
        raise HTTPException(status_code=503, detail=_webrtc_bridge_unavailable_detail())
    body = await request.body()
    status, response_body = go2rtc_bridge.proxy_ice(cam_id, body.decode() if body else None)
    if status not in (200, 204):
        raise HTTPException(status_code=status, detail="ICE trickle failed")
    return Response(content=response_body, media_type="application/trickle-ice-sdpfrag")

# ── MJPEG / Standard Endpoints ───────────────────────────────────────────────

@app.get("/video_feed", summary="MJPEG Video Stream")
async def video_feed(request: Request, camera_id: str = DEFAULT_CAMERA_ID):
    is_example = camera_id in EXAMPLE_SOURCES
    if not is_example and camera_id not in CAMERA_SOURCES:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} is not configured or offline")
    _acquire_stream_slot(request, "mjpeg")
    return StreamingResponse(_mjpeg_generator(camera_id), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/webrtc/offer/{camera_id}", summary="WebRTC SDP offer/answer exchange")
async def webrtc_offer(camera_id: str, request: Request):
    _authorize_request(request, required_role="admin")
    if camera_id not in CAMERA_SOURCES and camera_id not in EXAMPLE_SOURCES:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not configured")
    if _webrtc_manager is None:
        raise HTTPException(status_code=501, detail="WebRTC not initialized")
    if not _webrtc_manager.available:
        raise HTTPException(status_code=501, detail="WebRTC not available. Install: pip install aiortc av")
    try:
        data = await request.json()
        result = await _webrtc_manager.handle_offer(
            camera_id,
            lambda cid=camera_id: state.get_frame(cid),
            data["sdp"], data["type"]
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        # Internal failure detail stays server-side; the client contract is stable.
        print(f"[WebRTC] offer failed for {camera_id}: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail="WebRTC offer failed")

@app.get("/cameras/status", summary="Camera status list")
async def cameras_status(request: Request):
    """Return operational status without exposing camera URLs or credentials."""
    _authorize_request(request, required_role="viewer")
    statuses = []
    for cam_id, source in CAMERA_SOURCES.items():
        cam_status = state.get_camera_status(cam_id)
        cam_status["sourceKind"] = "file" if cam_id in EXAMPLE_SOURCES or not _is_live_source(source) else "live"
        last_ts = cam_status.get("lastFrameTimestamp")
        cam_status["running"] = (time.time() - last_ts) < 5.0 if last_ts is not None else False
        statuses.append(cam_status)
    return {"cameras": statuses}

@app.get("/alerts", summary="SSE Event Stream")
async def alerts(request: Request):
    _acquire_stream_slot(request, "sse")
    return StreamingResponse(_sse_generator(state.subscribe()), media_type="text/event-stream")


@app.get("/alerts/{alert_id}/triage", summary="Read the incident triage state (WT-25)")
def get_alert_triage(alert_id: str, request: Request):
    """Process-scoped triage state for one alert (`null` when never triaged).

    Actor identity is the authenticated role; no per-user identity exists at
    this revision, so the record documents the role that changed the state.
    """
    _validate_alert_id(alert_id)
    _authorize_request(request, required_role="viewer")
    alert = state.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"alertId": alert_id, "triage": normalize_triage_record(alert.get("triage"))}


@app.post("/alerts/{alert_id}/triage", summary="Advance the incident triage state (WT-25)")
def post_alert_triage(alert_id: str, body: TriageRequest, request: Request):
    """Applies one transition of the incident workflow.

    new -> in_progress (acknowledge) | on_hold | resolved, and reopen from
    resolved. Every transition records the acting role and an ISO timestamp.
    """
    role = _authorize_request(request, required_role="admin")
    _validate_alert_id(alert_id)
    alert = state.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    record, reason = apply_transition(alert.get("triage"), body.action, role)
    if record is None:
        audit_logger.record("alert_triage", "error", role=role, alert_id=alert_id,
                            details={"action": body.action, "reason": reason})
        status = 409 if reason == "conflict" else 400
        raise HTTPException(status_code=status, detail=f"Triage transition rejected: {reason}")
    state.update_alert(alert_id, {"triage": record})
    state.broadcast_alert({"type": "alert_triage", "alertId": alert_id, "triage": record})
    audit_logger.record("alert_triage", "success", role=role, alert_id=alert_id,
                        details={"state": record["state"], "action": record["action"]})
    return record


def _build_detection_payload(snap: dict, camera_id: str = DEFAULT_CAMERA_ID) -> dict:
    # ── WT-13 (S-08) additive telemetry ingest — flag hunk, safe to drop ────
    try:
        from metrics import pipeline_metrics as _pipeline_metrics
        _pipeline_metrics.observe_detection_snapshot(snap, camera_id=camera_id)
        _pipeline_telemetry_block = _pipeline_metrics.detection_telemetry_payload(snap, camera_id=camera_id)
    except Exception as _telemetry_exc:  # surfaced in the payload, never silent
        _pipeline_telemetry_block = {"available": False, "reason": f"telemetry unavailable: {_telemetry_exc}"}
    # ── end WT-13 hunk ──────────────────────────────────────────────────────
    policy = state.get_decision_config()
    decision = snap.get('decision_layer') or state.decision_for_camera(camera_id).status()
    sequence = snap.get('inference_sequence', 0)
    # ── WT-17 (S-09) frame identity + freshness (SC-3 additive) — flag hunk ─
    frame_sequence = snap.get('frameSequence')
    frame_sequence = frame_sequence if isinstance(frame_sequence, int) and not isinstance(frame_sequence, bool) and frame_sequence > 0 else None
    frame_captured_at = snap.get('frame_captured_at')
    frame_clock_base = snap.get('frame_clock_base') or 'monotonic-gettickcount64'
    frame_age_ms = None
    frame_age_clock_base = None
    if isinstance(frame_captured_at, (int, float)) and not isinstance(frame_captured_at, bool) and frame_captured_at > 0:
        # One subtraction inside a single clock domain (SC-6): the emission stamp
        # uses the same base the capture stamp was taken with.
        age_stamp = time.perf_counter() if frame_clock_base == 'perf-qpc' else time.monotonic()
        frame_age_ms = round(max(0.0, (age_stamp - float(frame_captured_at)) * 1000.0), 1)
        frame_age_clock_base = 'perf-qpc' if frame_clock_base == 'perf-qpc' else 'monotonic-gettickcount64'
    render_backlog = snap.get('renderBacklogDroppedCount')
    render_backlog = render_backlog if isinstance(render_backlog, int) and not isinstance(render_backlog, bool) and render_backlog >= 0 else None
    # ── end WT-17 hunk ──────────────────────────────────────────────────────
    health = dict(snap.get('pipeline_health') or {})
    health['capture'] = state.get_camera_health(camera_id)
    alert_state = decision.get('alert_state', 'NORMAL')
    if alert_state == 'CONFIRMED_VIOLENCE': alert_state = 'CONFIRMED'
    return {
        "cameraId": camera_id, "sourceKind": "file" if camera_id in EXAMPLE_SOURCES or not _is_live_source(CAMERA_SOURCES.get(camera_id, 0)) else "live",
        "updatedAt": snap.get('timestamp'), "inferenceSequence": sequence,
        "violenceSequence": snap.get("violence_observation_id", 0), "weaponSequence": snap.get("weapon_observation_id", 0),
        "tracks": snap.get("tracks", []), "personCount": snap.get("person_count", 0),
        # Canonical counting semantics (S-04/WT-22): personCount is the documented
        # alias of activeTrackCount; the window estimate carries its own band.
        "visiblePersonCount": int(snap.get("visible_person_count", 0) or 0),
        "activeTrackCount": int(snap.get("active_track_count", snap.get("person_count", 0)) or 0),
        "uniquePersonEstimateWindow": estimate_window_to_wire(snap.get("unique_person_estimate_window")),
        "trackFailureFlags": dict(snap.get("track_failure_flags") or {}),
        "personTracker": str(snap.get("person_tracker") or ""),
        "trackNamespace": camera_id,
        "isThreat": snap.get("is_threat", False), "threatConfidence": snap.get("threat_confidence", 0),
        "fps": snap.get("fps", 0), "violenceScore": snap.get('violence_conf') if snap.get('violence_observation_id', 0) else None,
        "weaponScore": snap.get("weapon_score") if snap.get("weapon_observation_id", 0) else None,
        "videoWidth": snap.get("video_width", 0), "videoHeight": snap.get("video_height", 0),
        "multiThreat": snap.get("multiThreat"), "health": health,
        "latencyMs": snap.get('processing_latency_ms'),
        "window": {"framesCollected": snap.get('frames_collected', 0), "framesRequired": snap.get('frames_required', 32),
                   "spanSeconds": snap.get('window_span_seconds'), "valid": snap.get('window_valid', False), "clockSource": snap.get("window_clock_source", "unavailable")},
        "decision": {"alertState": alert_state, "confirmedAlert": decision.get('confirmed_alert', False),
                     "watchThreshold": policy.watch_threshold, "confirmThreshold": policy.confirm_threshold,
                     "weaponThreshold": policy.weapon_threshold, "rollingWindowCount": decision.get('rolling_window_count', 0),
                     "confirmN": policy.confirm_n, "confirmM": policy.confirm_m,
                     "cooldownRemainingSeconds": decision.get('cooldown_remaining_seconds', 0)},
        "calibrationStatus": "unverified",
        "pipeline": _pipeline_telemetry_block,  # WT-13 (S-08) additive
        # WT-17 (S-09) SC-3 additive frame identity + freshness; null when unmeasured.
        "frameSequence": frame_sequence,
        "frameAgeAtDetectionEmitMs": frame_age_ms,
        "frameAgeAtDetectionEmitClockBase": frame_age_clock_base,
        "renderBacklogDroppedCount": render_backlog,
    }


async def _detection_sse_generator(camera_id: str) -> AsyncGenerator[bytes, None]:
    try:
        last_data = None
        while True:
            payload = _build_detection_payload(state.get_detection_meta(camera_id) or {}, camera_id)
            data = json.dumps(payload, allow_nan=False)
            if data != last_data:
                last_data = data
                yield f"data: {data}\n\n".encode()
            await asyncio.sleep(0.1)
    finally:
        _release_stream_slot()


@app.get("/detections", summary="SSE Detection Metadata Stream")
async def detections(request: Request, camera_id: str = DEFAULT_CAMERA_ID):
    """Stream real-time detection metadata (tracks, person count, threat) for frontend overlay rendering."""
    if camera_id not in CAMERA_SOURCES and camera_id not in EXAMPLE_SOURCES:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} not configured")
    _acquire_stream_slot(request, "sse")
    return StreamingResponse(
        _detection_sse_generator(camera_id),
        media_type="text/event-stream",
    )


@app.post("/demo_start/{clip_id}", summary="Start on-demand analysis of a demo/example clip")
async def demo_start(clip_id: str, request: Request):
    """Start a worker for a bundled sample clip (admin-only resource mutation)."""
    _authorize_request(request, required_role="admin")
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
async def demo_stop(clip_id: str, request: Request):
    """Stop the temporary analysis worker for a demo clip."""
    _authorize_request(request, required_role="admin")
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


# ─── WT-24 S-07 [additive]: evidence read-audit (P-2) ─────────────────────────
# Evidence reads require the viewer tier and record the authenticated role,
# action, artifact hash, and timestamp through AuditLogger.
def _evidence_reader_role(request: Request) -> str:
    return _authorize_request(request, required_role="viewer")


def _evidence_file_sha(path) -> str | None:
    try:
        from .evidence import sha256_file as _sha
    except ImportError:
        from evidence import sha256_file as _sha
    try:
        return _sha(Path(path))
    except Exception:
        return None


def _audit_evidence_access(action, request, alert_id, artifact, served_sha, ledger_sha, role=None):
    recorded = ledger_sha if isinstance(ledger_sha, str) and re.fullmatch(r"[a-fA-F0-9]{64}", ledger_sha) else None
    mismatch = recorded is not None and served_sha is not None and recorded.lower() != served_sha.lower()
    audit_logger.record(
        action,
        "error" if mismatch else "success",
        role=role or _evidence_reader_role(request),
        alert_id=alert_id,
        details={
            "artifact": artifact,
            "artifactSha256": served_sha,
            "ledgerSha256": recorded,
        },
    )
    if mismatch:
        # Tampered or replaced artifact: never serve bytes that fail the chain.
        raise HTTPException(status_code=500, detail="Evidence integrity check failed")


@app.get("/clips/{alert_id}", summary="Stream recorded incident clip")
async def get_clip(alert_id: str, request: Request):
    """Stream a recorded incident clip."""
    role = _authorize_request(request, required_role="viewer")
    _validate_alert_id(alert_id)
    from pathlib import Path

    # Check evidence directory
    clip_path = EVIDENCE_DIR / f"{alert_id}.mp4"
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Clip not found")

    record = evidence_ledger.get(alert_id) if evidence_ledger else None
    _audit_evidence_access(
        "evidence_clip_read",
        request,
        alert_id,
        "clip",
        _evidence_file_sha(clip_path),
        (record or {}).get("clipSha256"),
        role=role,
    )
    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
    )


@app.get("/api/clips/list", summary="List available incident clips")
async def list_clips(request: Request):
    """List all evidence clips in EVIDENCE_DIR, newest first."""
    _authorize_request(request, required_role="viewer")
    clips = []

    if EVIDENCE_DIR.exists():
        paths = sorted(EVIDENCE_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        for clip_path in paths:
            if clip_path.name.endswith(".part.mp4"):
                continue
            alert_id = clip_path.stem
            alert = state.get_alert(alert_id)
            # WT-24 S-07 [additive]: surface explicit evidence state so a
            # partial clip is never presented as a complete one.
            record = evidence_ledger.get(alert_id) if evidence_ledger else None
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
                "evidenceStatus": state.get_evidence_status(alert_id),
                "clipComplete": (record or {}).get("clipComplete"),
                "clipPartialReason": (record or {}).get("clipPartialReason"),
            })

    return {"clips": clips, "count": len(clips)}


@app.get("/api/categories", summary="Get all available detection categories")
async def get_categories(request: Request):
    """Get all available detection categories and their status."""
    _authorize_request(request, required_role="viewer")
    if not category_detector:
        raise HTTPException(status_code=503, detail="Category detector not initialized")

    return {
        "categories": [
            category_detector.get_capability(cat)
            for cat in DetectionCategory
        ]
    }


@app.post("/api/analyze", summary="Analyze a frame or context for a specific category")
def analyze_category(body: AnalyzeRequest, request: Request):
    """Analyze context data for a specific detection category."""
    _authorize_request(request, required_role="admin")
    if not category_detector:
        raise HTTPException(status_code=503, detail="Category detector not initialized")

    try:
        cat = DetectionCategory(body.category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: {body.category}")

    try:
        context = parse_detection_context(body.context)
    except ValueError as exc:
        # Parser messages are the documented client-facing validation contract.
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print(f"[Categories] context parse failed: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=400, detail="Malformed context")

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
def toggle_category(category_id: str, enabled: bool, request: Request):
    """Enable or disable a detection category."""
    global category_detector
    role = _authorize_request(request, required_role="admin")
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
async def notifications_status(request: Request):
    _authorize_request(request, required_role="viewer")
    return {
        "telegram": telegram_notifier.status(),
    }


@app.post("/notifications/telegram/test", summary="Send a Telegram test alert")
def test_telegram_notification(request: Request):
    role = _authorize_request(request, required_role="admin")
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
def test_telegram_video(request: Request, clip_id: str = "EXAMPLE-02"):
    role = _authorize_request(request, required_role="admin")
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
async def deepseek_status(request: Request):
    _authorize_request(request, required_role="viewer")
    return deepseek_service.status()


@app.post("/reports/deepseek/test", summary="Generate test DeepSeek report (no alert required)")
def deepseek_test(request: Request):
    # ui-contract C-5: server-side generation is admin-gated (external LLM spend).
    _authorize_request(request, required_role="admin")
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
    except TimeoutError:
        print("[Reporting] DeepSeek generation timed out")
        raise HTTPException(status_code=504, detail="Report generation timed out")
    except RuntimeError as exc:
        print(f"[Reporting] DeepSeek generation failed: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail="Report service unavailable")


@app.post("/reports/deepseek/{alert_id}", summary="Generate DeepSeek report for an alert")
def deepseek_generate(alert_id: str, request: Request, force: bool = False):
    _validate_alert_id(alert_id)
    # ui-contract C-5: regeneration is admin-gated server-side (external LLM spend).
    _authorize_request(request, required_role="admin")
    alert = state.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Incident not found")
    alert_payload = _enrich_alert_for_report(alert)
    try:
        result = deepseek_service.generate(alert_payload, force=force)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TimeoutError:
        print("[Reporting] DeepSeek generation timed out")
        raise HTTPException(status_code=504, detail="Report generation timed out")
    except RuntimeError as exc:
        print(f"[Reporting] DeepSeek generation failed: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail="Report service unavailable")


@app.get("/reports/deepseek/{alert_id}", summary="Fetch cached DeepSeek report")
async def deepseek_get(alert_id: str, request: Request):
    _validate_alert_id(alert_id)
    _authorize_request(request, required_role="viewer")
    cached = deepseek_service.get_cached(alert_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="Report not generated yet")
    return cached


def _report_text_for_pdf(alert_id: str) -> tuple[str, str]:
    cached = deepseek_service.get_cached(alert_id)
    if cached and isinstance(cached.get("report"), dict):
        report = cached["report"]
        parts = []
        if report.get("executive_summary"):
            parts.append(f"Summary: {report['executive_summary']}")
        if report.get("severity_assessment"):
            parts.append(f"Severity: {report['severity_assessment']}")
        if report.get("recommended_actions"):
            actions = report["recommended_actions"]
            joined = "; ".join(str(action) for action in actions[:3]) if isinstance(actions, list) else str(actions)
            parts.append(f"Actions: {joined}")
        if report.get("final_verdict"):
            parts.append(f"Verdict: {report['final_verdict']}")
        return ("\n".join(parts) if parts else "DeepSeek report available.", "model")
    return (
        state.get_report_text(alert_id) or "Visual analysis is still pending.",
        state.get_report_source(alert_id) or "model",
    )


def _report_receipt_type() -> str:
    try:
        from .evidence import REPORT_RECEIPT_TYPE
    except ImportError:
        from evidence import REPORT_RECEIPT_TYPE
    return REPORT_RECEIPT_TYPE


def _report_pdf_response(alert_id: str, alert: dict, role: str) -> FileResponse:
    # Serialize check/build/receipt publication/cleanup so a losing concurrent
    # request cannot remove the winner's successfully chained PDF.
    with _REPORT_GENERATION_LOCK:
        return _report_pdf_response_locked(alert_id, alert, role)


def _report_pdf_response_locked(alert_id: str, alert: dict, role: str) -> FileResponse:
    if evidence_ledger is None:
        raise HTTPException(status_code=503, detail="Evidence ledger is not initialized")
    report_text, report_source = _report_text_for_pdf(alert_id)
    snapshot_path = state.get_snapshot_path(alert_id)
    evidence_path = EVIDENCE_DIR / f"{alert_id}.mp4"
    output_path = REPORTS_DIR / f"{alert_id}.pdf"
    if output_path.exists():
        raise HTTPException(status_code=409, detail="A PDF already exists; use the verified cached download")
    try:
        build_incident_pdf(
            alert=alert,
            report_text=report_text,
            report_source=report_source,
            snapshot_path=snapshot_path,
            evidence_path=evidence_path if evidence_path.exists() else None,
            output_path=output_path,
        )
        receipt = evidence_ledger.append_entry(
            alert=alert,
            clip_path=evidence_path if evidence_path.exists() else None,
            snapshot_path=snapshot_path,
            report_path=output_path,
            report_text=report_text,
            record_type=_report_receipt_type(),
        )
        report_sha = _evidence_file_sha(output_path)
        if not report_sha or not re.fullmatch(r"[a-fA-F0-9]{64}", report_sha):
            raise RuntimeError("Report PDF could not be hashed")
        if not isinstance(receipt, dict) or receipt.get("reportSha256") != report_sha:
            raise RuntimeError("Report receipt did not match the published PDF")
    except Exception as exc:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        logging.exception("Report receipt could not be chained for %s", alert_id)
        raise HTTPException(status_code=500, detail="Evidence chain could not record the published report") from exc

    audit_logger.record(
        "report_pdf_generate",
        "success",
        role=role,
        alert_id=alert_id,
        details={"reportSha256": report_sha},
    )
    return FileResponse(
        str(output_path),
        media_type="application/pdf",
        filename=f"{alert_id}.pdf",
    )


@app.post("/reports/pdf/{alert_id}", summary="Generate and publish a forensic PDF report")
def generate_report_pdf(alert_id: str, request: Request):
    role = _authorize_request(request, required_role="admin")
    _validate_alert_id(alert_id)
    alert = state.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _report_pdf_response(alert_id, alert, role)


@app.get("/download_report/{alert_id}", summary="Fetch a chained forensic PDF report")
def download_report(alert_id: str, request: Request):
    role = _authorize_request(request, required_role="viewer")
    _validate_alert_id(alert_id)
    if evidence_ledger is None:
        raise HTTPException(status_code=503, detail="Evidence ledger is not initialized")

    output_path = REPORTS_DIR / f"{alert_id}.pdf"
    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="Report PDF has not been generated")
    try:
        records = evidence_ledger.records_for(alert_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Evidence ledger integrity check failed") from exc
    receipts = [
        record for record in records
        if record.get("recordType") == _report_receipt_type()
    ]
    if not receipts:
        raise HTTPException(status_code=404, detail="Report PDF has not been generated")
    report_sha = _evidence_file_sha(output_path)
    if not report_sha:
        raise HTTPException(status_code=500, detail="Report integrity check failed")
    latest_receipt = receipts[-1]
    recorded_sha = latest_receipt.get("reportSha256")
    if not isinstance(recorded_sha, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", recorded_sha):
        raise HTTPException(status_code=500, detail="Report integrity check failed")
    _audit_evidence_access(
        "report_pdf_read",
        request,
        alert_id,
        "report-pdf",
        report_sha,
        recorded_sha,
        role=role,
    )
    return FileResponse(
        str(output_path),
        media_type="application/pdf",
        filename=f"{alert_id}.pdf",
    )

@app.post("/switch_camera", summary="Change active camera stream (deprecated)")
async def switch_camera(body: CameraRequest, request: Request):
    raise HTTPException(status_code=410, detail="This endpoint is deprecated in multi-camera mode. Configure ACTIVE_CAMERAS environment variable to select cameras.")

@app.get("/decision/config", summary="Read the active validated decision policy")
def decision_config_status(request: Request):
    _authorize_request(request, required_role="viewer")
    return {"policy": state.get_decision_config().to_dict(), "persistence": "runtime"}

@app.post("/decision/config", summary="Update validated runtime decision policy")
def update_decision_config(body: dict, request: Request):
    role = _authorize_request(request, required_role="admin")
    try:
        policy = DecisionConfig.from_mapping(body)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    state.apply_decision_config(policy)
    audit_logger.record('decision_config', 'success', role=role)
    return {'status': 'success', 'policy': policy.to_dict()}

@app.get("/reports/local/{alert_id}", summary="Read stored offline factual summary")
def get_local_incident_report(alert_id: str, request: Request):
    _authorize_request(request, required_role="viewer")
    _validate_alert_id(alert_id)
    report = state.get_report_text(alert_id)
    if report is None or state.get_report_source(alert_id) != "local_facts":
        raise HTTPException(status_code=404, detail="Local summary not available")
    return {'alertId': alert_id, 'mode': 'local-evidence-summary', 'report': report}

@app.post("/reports/local/{alert_id}", summary="Generate offline factual incident summary")
def local_incident_report(alert_id: str, request: Request):
    role = _authorize_request(request, required_role="admin")
    _validate_alert_id(alert_id)
    alert = state.get_alert(alert_id)
    if not alert: raise HTTPException(status_code=404, detail="Alert not found")
    from local_forensics import build_local_report
    report = build_local_report(alert)
    state.store_report_text(alert_id, report, source="local_facts")
    audit_logger.record("local_report", "success", role=role, alert_id=alert_id)
    return {'alertId': alert_id, 'mode': 'local-evidence-summary', 'report': report}

@app.post("/set_threshold", summary="Update model confidence threshold")
def set_threshold(body: ThresholdRequest, request: Request):
    role = _authorize_request(request, required_role="admin")
    new_thresh = state.set_threshold(body.threshold)
    audit_logger.record("set_threshold", "success", role=role, details={"threshold": new_thresh})
    return {"status": "success", "threshold": new_thresh}

@app.post("/set_cooldown", summary="Update time between consecutive alerts")
def set_cooldown(body: CooldownRequest, request: Request):
    role = _authorize_request(request, required_role="admin")
    new_cooldown = state.set_cooldown(body.cooldown)
    audit_logger.record("set_cooldown", "success", role=role, details={"cooldown": new_cooldown})
    return {"status": "success", "cooldown": new_cooldown}

@app.get("/download_evidence/{alert_id}", summary="Fetch recorded DVR clip")
async def download_evidence(alert_id: str, request: Request):
    _validate_alert_id(alert_id)
    role = _authorize_request(request, required_role="viewer")
    record = evidence_ledger.get(alert_id) if evidence_ledger else None
    status = state.get_evidence_status(alert_id)
    if not status and record is not None and (EVIDENCE_DIR / f"{alert_id}.mp4").exists():
        # SC-8 consistency: a chained, published clip stays downloadable even
        # when in-memory status was lost (e.g. across an API restart).
        status = "ready" if record.get("clipComplete", True) else "partial"
    if not status:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if status == "writing":
        raise HTTPException(status_code=202, detail="Compiling video, try again shortly")
    if status == "error":
        raise HTTPException(status_code=500, detail="Server failed to compile evidence")
    clip_path = EVIDENCE_DIR / f"{alert_id}.mp4"
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Evidence not found")
    # WT-24 S-07 [additive]: P-2 read-audit with the served artifact hash.
    _audit_evidence_access(
        "evidence_download",
        request,
        alert_id,
        "clip",
        _evidence_file_sha(clip_path),
        (record or {}).get("clipSha256"),
        role=role,
    )

    return FileResponse(
        str(clip_path),
        media_type="video/mp4",
        filename=f"{alert_id}.mp4"
    )


# --- WT-21 (S-15): incident face capture API (additive). UI display of face
# --- capture is WT-25's; these endpoints deliver the data contract only.
@app.get("/evidence_derivatives/{alert_id}", summary="SC-8 enhancement derivative records for an alert (WT-23)")
def get_evidence_derivatives(alert_id: str, request: Request):
    _authorize_request(request, required_role="viewer")
    _validate_alert_id(alert_id)
    if EnhancementService is None:
        raise HTTPException(
            status_code=503,
            detail=f"Enhancement derivatives DISABLED: {_ENHANCE_IMPORT_ERROR or 'enhance module is not available'}")
    service, _scheduler = _get_enhancement()
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=f"Enhancement derivatives DISABLED: {_enhancement_build_error or 'enhancement service unavailable'}")
    return {
        "alertId": alert_id,
        "state": "READY",
        "derivatives": service.ledger.derivatives_for_alert(alert_id),
    }


@app.get("/api/faces/health", summary="Incident face capture subsystem health")
async def faces_health(request: Request):
    _authorize_request(request, required_role="viewer")
    service = _get_face_service()
    if service is None:
        return {"status": "DISABLED",
                "reason": _face_build_error or _FACE_CAPTURE_IMPORT_ERROR or "face capture modules unavailable",
                "detector": {"status": "disabled"}}
    health = service.health()
    detector_status = health.get("detector", {}).get("status", "unknown")
    return {"status": "OK" if detector_status == "loaded" else "DEGRADED",
            "reason": health.get("detector", {}).get("reason", ""),
            **health}


@app.get("/api/faces/incidents/{alert_id}", summary="Face capture result for an incident")
async def faces_incident(alert_id: str, request: Request):
    """Face capture result for one incident: ``face_assoc`` payload
    (crop_ref, track_id, UNCALIBRATED heuristic confidence, ambiguous, reasons),
    persisted crops, and explicit absent/pending states. No identity data."""
    _validate_alert_id(alert_id)
    _authorize_request(request, required_role="viewer")
    service = _get_face_service()
    if service is None:
        raise HTTPException(status_code=503,
                            detail="Face capture unavailable: " +
                                   (_face_build_error or _FACE_CAPTURE_IMPORT_ERROR or "modules missing"))
    return service.get_result(alert_id)


@app.get("/api/faces/incidents/{alert_id}/crops/{crop_id}", summary="Serve one persisted face crop")
async def faces_crop(alert_id: str, crop_id: str, request: Request):
    _validate_alert_id(alert_id)
    if not _CROP_ID_RE.fullmatch(crop_id) or ".." in crop_id:
        raise HTTPException(status_code=400, detail="Invalid crop_id format")
    _authorize_request(request, required_role="viewer")
    safe_name = crop_id.replace(":", "_")
    crop_path = EVIDENCE_DIR / f"{alert_id}_faces" / f"{safe_name}.face.png"
    if not crop_path.exists():
        raise HTTPException(status_code=404, detail="Face crop not found")
    audit_logger.record("face_crop_download", "success", role="viewer",
                        alert_id=alert_id, details={"cropId": crop_id})
    return FileResponse(str(crop_path), media_type="image/png",
                        filename=f"{safe_name}.face.png")


@app.get("/security/status", summary="Access control status")
async def security_status():
    if security_controller is None:
        raise HTTPException(status_code=503, detail="Access control is not initialized")
    return security_controller.status()


@app.get("/security/session", summary="Validate the presented operator credential")
def security_session(request: Request):
    """Report the server-assigned role for the presented credential.

    Frontend contract (wt-02 ui-contract C-6 / hooks/use-api-access.ts): response
    is exactly ``{"role": "admin" | "viewer"}``; a non-2xx response means the
    stored credential must be cleared (401 when a configured key does not match).
    With no key configured a read-only viewer session is reported, matching the
    controller's demo-mode semantics.
    """
    role = _authorize_request(request, required_role="viewer")
    return {"role": role}


@app.get("/audit/status", summary="Audit log status")
async def audit_status(request: Request):
    _authorize_request(request, required_role="admin")
    return audit_logger.status()


@app.get("/audit/recent", summary="Recent audit events")
def audit_recent(request: Request, limit: int = 20):
    _authorize_request(request, required_role="admin")
    return {"items": audit_logger.recent(limit=max(1, min(limit, 100)))}


@app.get("/evidence_chain/{alert_id}", summary="Evidence ledger entry")
def evidence_chain(alert_id: str, request: Request):
    _validate_alert_id(alert_id)
    role = _authorize_request(request, required_role="viewer")
    record = evidence_ledger.get(alert_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evidence chain entry not found")
    # WT-24 S-07 [additive]: P-2 read-audit for chain reads (artifact = the
    # chain record itself; its chain hash is the artifact hash).
    _audit_evidence_access(
        "evidence_chain_read",
        request,
        alert_id,
        "ledger-record",
        record.get("currentHash"),
        record.get("currentHash"),
        role=role,
    )
    return record


# ─── WT-24 S-07 [additive]: evidence retention (P-6) ──────────────────────────
# Dry-run only by design: this campaign NEVER deletes evidence. The planner
# reports what would become prunable after `clips.clip_retention_days`; a legal
# hold always wins over age. No deletion code path exists here on purpose.
_EVIDENCE_HOLD_STORE = None


def _evidence_hold_store():
    global _EVIDENCE_HOLD_STORE
    if _EVIDENCE_HOLD_STORE is None:
        try:
            from .evidence import EvidenceHoldStore
        except ImportError:
            from evidence import EvidenceHoldStore
        holds_path = _resolve_storage_path(
            str(config.get("storage", {}).get("evidence_holds_path", "./evidence_holds.json"))
        )
        _EVIDENCE_HOLD_STORE = EvidenceHoldStore(holds_path)
    return _EVIDENCE_HOLD_STORE


@app.get("/api/evidence/retention", summary="Dry-run evidence retention plan (never deletes)")
def evidence_retention_plan(request: Request):
    _authorize_request(request, required_role="viewer")
    try:
        from .evidence import EvidenceRetentionPolicy
    except ImportError:
        from evidence import EvidenceRetentionPolicy

    retention_days = config.get("clips", {}).get("clip_retention_days")
    holds = _evidence_hold_store().load()
    policy = EvidenceRetentionPolicy(retention_days, holds)
    now = time.time()
    artifacts = []
    prunable_bytes = 0
    for kind, directory, pattern in (
        ("clip", EVIDENCE_DIR, "*.mp4"),
        ("snapshot", THUMBNAILS_DIR, "*.jpg"),
        ("report", REPORTS_DIR, "*.pdf"),
    ):
        if not directory.exists():
            continue
        for path in sorted(directory.glob(pattern)):
            if path.name.endswith(".part.mp4"):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            age_days = max(0.0, (now - stat.st_mtime) / 86400.0)
            verdict = policy.evaluate(path.stem, kind, path, age_days)
            if verdict.action == "prune":
                prunable_bytes += stat.st_size
            artifacts.append({
                "alertId": verdict.alert_id,
                "artifact": verdict.artifact,
                "name": path.name,
                "ageDays": round(age_days, 3),
                "size": stat.st_size,
                "action": verdict.action,
                "reason": verdict.reason,
            })
    return {
        "retentionDays": retention_days,
        "enabled": policy.enabled,
        "dryRunOnly": True,
        "deletionImplemented": False,
        "note": "Retention is dry-run only in this campaign; no evidence is deleted.",
        "holds": sorted(holds),
        "artifacts": artifacts,
        "prunableCount": sum(1 for item in artifacts if item["action"] == "prune"),
        "prunableBytes": prunable_bytes,
    }


@app.post("/api/evidence/retention/hold", summary="Set or clear a per-alert legal hold")
def evidence_retention_hold(body: dict, request: Request):
    role = _authorize_request(request, required_role="admin")
    alert_id = str((body or {}).get("alertId") or "")
    _validate_alert_id(alert_id)
    held = bool((body or {}).get("hold", True))
    holds = _evidence_hold_store().set_hold(alert_id, held)
    audit_logger.record(
        "evidence_retention_hold",
        "success",
        role=role,
        alert_id=alert_id,
        details={"hold": held},
    )
    return {"alertId": alert_id, "hold": held, "holds": sorted(holds)}


@app.post("/audio/analyze", summary="Analyze audio clip for distress cues")
def analyze_audio(body: AudioAnalysisRequest, request: Request):
    role = _authorize_request(request, required_role="admin")
    result = audio_analyzer.analyze_base64_wav(body.audio_base64)
    audit_logger.record(
        "audio_analyze",
        "success" if result.get("detected") else "ok",
        role=role,
        details={"filename": body.filename, "score": result.get("score", 0.0)},
    )
    return result


@app.get("/audio/status", summary="Audio analysis status")
async def audio_status(request: Request):
    _authorize_request(request, required_role="viewer")
    return audio_analyzer.status()


@app.get("/system/status", summary="Combined system status")
async def system_status():
    # ── WT-13 (S-08) additive telemetry ingest — flag hunk, safe to drop ────
    try:
        from metrics import pipeline_metrics as _pipeline_metrics
        for _telemetry_camera in list(CAMERA_SOURCES) + [c for c in EXAMPLE_SOURCES if c not in CAMERA_SOURCES]:
            _pipeline_metrics.observe_detection_snapshot(
                state.get_detection_meta(_telemetry_camera) or {}, camera_id=_telemetry_camera)
        _telemetry_metrics = _pipeline_metrics.summary()
        _telemetry_subsystems = _pipeline_metrics.subsystems()
    except Exception as _telemetry_exc:  # surfaced, never silent
        _telemetry_metrics = {"error": f"telemetry unavailable: {_telemetry_exc}"}
        _telemetry_subsystems = {"telemetry-status": {"status": "FAILED", "reason": str(_telemetry_exc)[:300]}}
    # ── end WT-13 hunk ──────────────────────────────────────────────────────
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
        "features": feature_health(),
        "storage": {
            "evidence": str(EVIDENCE_DIR),
            "thumbnails": str(THUMBNAILS_DIR),
            "reports": str(REPORTS_DIR),
        },
        "metrics": _telemetry_metrics,        # WT-13 (S-08) additive
        "subsystems": _telemetry_subsystems,  # WT-13 (S-08) additive: G-10 health
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
        # Keep the 200 + JSON shape monitoring consumers expect; never echo internals.
        print(f"[Metrics] summary failed: {type(exc).__name__}: {exc}")
        return {"error": "metrics unavailable", "features": feature_health()}


@app.post("/decision_layer/reset", summary="Reset live alert decision layer state")
def reset_decision_layer(request: Request):
    role = _authorize_request(request, required_role="admin")
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
