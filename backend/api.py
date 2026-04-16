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
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from inference import ViolenceInferencePipeline, VIOLENCE_CLS

# ─────────────────────────────────────────────────────────────────────────────
# 1. Configuration & Environment Setup
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv()

with open("config.yml", "r") as f:
    config = yaml.safe_load(f)

def _parse_source(raw: str) -> Union[str, int]:
    try:
        return int(raw)
    except ValueError:
        return raw

CAMERA_SOURCES: Dict[str, Union[str, int]] = {
    "CAM-01": _parse_source(os.getenv("CAM1_SOURCE", "cam1.mp4")),
    "CAM-02": _parse_source(os.getenv("CAM2_SOURCE", "cam2.mp4")),
    "CAM-03": _parse_source(os.getenv("CAM3_SOURCE", "cam3.mp4")),
}
DEFAULT_CAMERA_ID = "CAM-01"

WEIGHTS_PATH = os.getenv("WEIGHTS_PATH", "best_model.pt")
THRESHOLD    = float(os.getenv("THRESHOLD", str(config['model']['confidence_threshold'])))
STRIDE       = int(os.getenv("STRIDE", str(config['model']['stride'])))

JPEG_QUALITY   = 80
TARGET_FPS     = 25
RING_BUFFER_LEN = 150  
POST_ALERT_LEN  = 150  

EVIDENCE_DIR = Path(config['storage']['evidence_dir'])
EVIDENCE_DIR.mkdir(exist_ok=True)

THUMBNAILS_DIR = Path(config['storage']['thumbnails_dir'])
THUMBNAILS_DIR.mkdir(exist_ok=True)

# ── Groq Vision-Language Model Setup ──
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ENABLED = bool(GROQ_API_KEY)
_groq_client = None

if GROQ_ENABLED:
    try:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
        print("[System] ✓ Groq initialized successfully.")
    except Exception as exc:
        print(f"[System] ✗ Failed to initialize Groq VLM: {exc}")
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

# ─────────────────────────────────────────────────────────────────────────────
# 3. Application State Management
# ─────────────────────────────────────────────────────────────────────────────

class AppState:
    def __init__(self):
        self._frame_lock = threading.Lock()
        self._frame_jpg: Optional[bytes] = None
        
        self._aq_lock = threading.Lock()
        self._alert_queues: list[queue.Queue] = []
        
        self._evidence_lock = threading.Lock()
        self._evidence_status: Dict[str, str] = {}
        
        self._pipeline_lock = threading.Lock()
        self._pipeline: Optional[ViolenceInferencePipeline] = None
        
        self._camera_lock = threading.Lock()
        self._pending_switch: Optional[Tuple[Union[str, int], str]] = None
        self._current_cam_id = DEFAULT_CAMERA_ID
        
        self._cooldown_lock = threading.Lock()
        self._cooldown = 60.0  
        
        self.running = False

    def set_frame(self, jpg: bytes):
        with self._frame_lock:
            self._frame_jpg = jpg

    def get_frame(self) -> Optional[bytes]:
        with self._frame_lock:
            return self._frame_jpg

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
        with self._pipeline_lock:
            self._pipeline = pipeline

    def set_threshold(self, value: float) -> float:
        with self._pipeline_lock:
            if not self._pipeline:
                raise RuntimeError("Pipeline is not initialized yet.")
            self._pipeline.threshold = value
            return value

    def get_threshold(self) -> float:
        with self._pipeline_lock:
            return self._pipeline.threshold if self._pipeline else THRESHOLD

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
        print(f"[Evidence] ✓ Clip compiled successfully: {alert_id}.mp4")
    except Exception as exc:
        state.mark_evidence(alert_id, "error")
        print(f"[Evidence] ✗ Error writing clip {alert_id}: {exc}")

def _call_groq_vlm(alert_id: str, frame: np.ndarray):
    global _groq_client
    if not GROQ_ENABLED or not _groq_client:
        report_text = "[Forensic module offline. Ensure API key is configured and Groq is installed.]"
    else:
        try:
            ok, jpg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            base64_image = base64.b64encode(jpg_buf).decode('utf-8')
            
            completion = _groq_client.chat.completions.create(
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
            report_text = completion.choices[0].message.content.strip()
            print(f"[VLM] ✓ Forensic report generated for {alert_id}")
        except Exception as exc:
            report_text = f"[Forensic analysis failed due to network or API error: {exc}]"
            print(f"[VLM] ✗ {report_text}")
            
    state.broadcast_alert({
        "type": "VLM_Report", 
        "id": alert_id, 
        "report": report_text
    })

# ─────────────────────────────────────────────────────────────────────────────
# 5. Core Video Capture & Inference Engine
# ─────────────────────────────────────────────────────────────────────────────

def capture_loop():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[System] AI Engine initializing on {device.type.upper()}...")
    
    pipeline = ViolenceInferencePipeline(WEIGHTS_PATH, device, THRESHOLD, STRIDE)
    state.register_pipeline(pipeline)
    
    cap = cv2.VideoCapture(CAMERA_SOURCES[DEFAULT_CAMERA_ID])
    
    def _read_cap_props(c):
        return c.get(cv2.CAP_PROP_FPS) or 25.0, int(c.get(cv2.CAP_PROP_FRAME_WIDTH)), int(c.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
    src_fps, width, height = _read_cap_props(cap)
    ring = deque(maxlen=RING_BUFFER_LEN)
    active_post_queues = []
    last_alert_time = 0.0
    state.running = True

    while state.running:
        t0 = time.perf_counter()
        
        ret, raw = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            pipeline.reset()
            continue

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

        clean_frame = pipeline.process_frame(raw)
        ring.append(raw.copy())

        ok, jpg_buf = cv2.imencode(".jpg", clean_frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok: 
            state.set_frame(jpg_buf.tobytes())

        now = time.time()
        current_cooldown = state.get_cooldown()
        
        if pipeline._last_label == VIOLENCE_CLS and (now - last_alert_time > current_cooldown):
            last_alert_time = now
            alert_id = f"alert-{int(now * 1000)}"
            cam_id = state.get_current_camera_id()
            conf = pipeline._last_conf

            severity = "critical" if conf >= 0.85 else "high" if conf >= 0.65 else "medium"

            state.broadcast_alert({
                "id": alert_id, 
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "isoTime": datetime.now(timezone.utc).isoformat(), 
                "confidence": round(conf * 100, 1),
                "type": "Violence", 
                "severity": severity,
                "cameraId": cam_id, 
                "location": str(CAMERA_SOURCES.get(cam_id, cam_id)),
            })

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
                    target=_call_groq_vlm, 
                    args=(alert_id, pre_frames[-1].copy()), 
                    daemon=True
                ).start()

        pending = state.consume_pending_switch()
        if pending:
            new_source, new_cam_id = pending
            cap.release()
            ring.clear()
            active_post_queues.clear()
            pipeline.reset()
            if device.type == "cuda":
                torch.cuda.empty_cache()
            
            cap = cv2.VideoCapture(new_source)
            if cap.isOpened(): 
                src_fps, width, height = _read_cap_props(cap)
                print(f"[System] Stream focused on {new_cam_id}")
            else:
                print(f"[System] Warning: Failed to open {new_source}. Reverting to default.")
                cap = cv2.VideoCapture(CAMERA_SOURCES[DEFAULT_CAMERA_ID])
                src_fps, width, height = _read_cap_props(cap)
                state.request_camera_switch(CAMERA_SOURCES[DEFAULT_CAMERA_ID], DEFAULT_CAMERA_ID)
                state.consume_pending_switch()

        time.sleep(max(0, (1.0 / TARGET_FPS) - (time.perf_counter() - t0)))
        
    cap.release()

# ─────────────────────────────────────────────────────────────────────────────
# 6. FastAPI Setup & Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    t = threading.Thread(target=capture_loop, daemon=True)
    t.start()
    yield
    state.running = False
    t.join(timeout=5)

app = FastAPI(lifespan=lifespan, title="AI Sentinel Advanced Backend")
app.add_middleware(
    CORSMiddleware, 
    allow_origins=config['server']['cors_origins'], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

async def _mjpeg_generator() -> AsyncGenerator[bytes, None]:
    boundary = b"--frame\r\n"
    while True:
        jpg = state.get_frame()
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
async def video_feed():
    return StreamingResponse(_mjpeg_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/alerts", summary="SSE Event Stream")
async def alerts():
    return StreamingResponse(_sse_generator(state.subscribe()), media_type="text/event-stream")

@app.post("/switch_camera", summary="Change active camera stream")
async def switch_camera(body: CameraRequest):
    if body.camera_id not in CAMERA_SOURCES:
        raise HTTPException(status_code=400, detail="Unknown camera_id")
    state.request_camera_switch(CAMERA_SOURCES[body.camera_id], body.camera_id)
    return {"status": "success", "camera_id": body.camera_id}

@app.post("/set_threshold", summary="Update model confidence threshold")
async def set_threshold(body: ThresholdRequest):
    new_thresh = state.set_threshold(body.threshold)
    return {"status": "success", "threshold": new_thresh}

@app.post("/set_cooldown", summary="Update time between consecutive alerts")
async def set_cooldown(body: CooldownRequest):
    new_cooldown = state.set_cooldown(body.cooldown)
    return {"status": "success", "cooldown": new_cooldown}

@app.get("/download_evidence/{alert_id}", summary="Fetch recorded DVR clip")
async def download_evidence(alert_id: str):
    status = state.get_evidence_status(alert_id)
    if not status:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if status == "writing":
        raise HTTPException(status_code=202, detail="Compiling video, try again shortly")
    if status == "error":
        raise HTTPException(status_code=500, detail="Server failed to compile evidence")
        
    return FileResponse(
        str(EVIDENCE_DIR / f"{alert_id}.mp4"), 
        media_type="video/mp4", 
        filename=f"{alert_id}.mp4"
    )