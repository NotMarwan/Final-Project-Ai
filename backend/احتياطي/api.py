"""
api.py — SentinelEye FastAPI Backend  (Final / DVR Edition)
=============================================================
Endpoints:
  GET  /video_feed                   →  MJPEG live annotated stream
  GET  /alerts                       →  SSE violence alert feed
  GET  /download_evidence/{alert_id} →  Download compiled evidence .mp4
  GET  /health                       →  System status

Run:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload

Env vars (override via shell export or a .env file):
    VIDEO_SOURCE   Path to .mp4 OR integer webcam index  (default "0")
    WEIGHTS_PATH   Path to best_model.pt                 (default "best_model.pt")
    THRESHOLD      Confidence threshold 0–1              (default "0.5")
    STRIDE         Frames between model predictions      (default "16")
"""

import asyncio
import json
import os
import time
import threading
import queue
from collections import deque
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import cv2
import numpy as np
import torch

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse

from inference import ViolenceInferencePipeline, VIOLENCE_CLS

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

VIDEO_SOURCE: str | int = os.getenv("VIDEO_SOURCE", "0")
try:
    VIDEO_SOURCE = int(VIDEO_SOURCE)
except ValueError:
    pass  # keep as string path

WEIGHTS_PATH: str   = os.getenv("WEIGHTS_PATH", "best_model.pt")
THRESHOLD:    float = float(os.getenv("THRESHOLD", "0.5"))
STRIDE:       int   = int(os.getenv("STRIDE", "16"))

JPEG_QUALITY   = 80    # MJPEG stream encode quality (0–100)
TARGET_FPS     = 25    # Max stream frame-rate cap
ALERT_COOLDOWN = 3.0   # Seconds between consecutive SSE broadcasts

# DVR / evidence clip settings
RING_BUFFER_LEN = 150  # Pre-alert raw frames kept in memory  (~5 s @ 30 fps)
POST_ALERT_LEN  = 150  # Post-alert raw frames captured after a trigger

EVIDENCE_DIR = Path("evidence_clips")
EVIDENCE_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Shared application state
# ─────────────────────────────────────────────────────────────────────────────

class AppState:
    """
    Thread-safe container shared between the capture thread and HTTP handlers.

    Responsibilities
    ────────────────
    • Hold the latest JPEG-encoded annotated frame for MJPEG delivery.
    • Fan-out SSE alert payloads to all connected browser clients.
    • Track evidence clip status so the download endpoint can give precise
      responses (202 still-writing / 200 ready / 500 error).
    """

    def __init__(self) -> None:
        # Latest MJPEG frame
        self._frame_lock: threading.Lock = threading.Lock()
        self._frame_jpg:  bytes | None   = None

        # SSE subscriber queues — one per connected client
        self._aq_lock:      threading.Lock       = threading.Lock()
        self._alert_queues: list[queue.Queue]    = []

        # Evidence clip registry  alert_id → "writing" | "ready" | "error"
        self._evidence_lock:   threading.Lock    = threading.Lock()
        self._evidence_status: dict[str, str]    = {}

        self.running: bool = False

    # ── Frame ─────────────────────────────────────────────────────────────

    def set_frame(self, jpg: bytes) -> None:
        with self._frame_lock:
            self._frame_jpg = jpg

    def get_frame(self) -> bytes | None:
        with self._frame_lock:
            return self._frame_jpg

    # ── SSE pub/sub ───────────────────────────────────────────────────────

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=64)
        with self._aq_lock:
            self._alert_queues.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._aq_lock:
            try:
                self._alert_queues.remove(q)
            except ValueError:
                pass

    def broadcast_alert(self, payload: dict) -> None:
        data = json.dumps(payload)
        with self._aq_lock:
            for q in list(self._alert_queues):
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass  # slow client — skip rather than block

    # ── Evidence registry ─────────────────────────────────────────────────

    def mark_evidence_writing(self, alert_id: str) -> None:
        with self._evidence_lock:
            self._evidence_status[alert_id] = "writing"

    def mark_evidence_ready(self, alert_id: str) -> None:
        with self._evidence_lock:
            self._evidence_status[alert_id] = "ready"

    def mark_evidence_error(self, alert_id: str) -> None:
        with self._evidence_lock:
            self._evidence_status[alert_id] = "error"

    def get_evidence_status(self, alert_id: str) -> str | None:
        with self._evidence_lock:
            return self._evidence_status.get(alert_id)

    def evidence_stats(self) -> dict:
        with self._evidence_lock:
            statuses = list(self._evidence_status.values())
        return {
            "ready":   statuses.count("ready"),
            "writing": statuses.count("writing"),
            "error":   statuses.count("error"),
        }


state = AppState()


# ─────────────────────────────────────────────────────────────────────────────
# Evidence writer  (one daemon thread per alert, zero impact on stream)
# ─────────────────────────────────────────────────────────────────────────────

def _write_evidence_clip(
    alert_id:   str,
    pre_frames: list[np.ndarray],
    post_queue: queue.Queue,
    fps:        float,
    width:      int,
    height:     int,
) -> None:
    """
    Background thread target — never called from the async event loop.

    Combines `pre_frames` (ring buffer snapshot taken at the moment the alert
    fired) with raw frames consumed from `post_queue` (fed by capture_loop
    for the next POST_ALERT_LEN frames), then writes everything to:

        evidence_clips/<alert_id>.mp4

    The function blocks inside the thread until all post-alert frames arrive
    OR a 2-second timeout with no new frames triggers early termination.
    """
    out_path = EVIDENCE_DIR / f"{alert_id}.mp4"
    state.mark_evidence_writing(alert_id)

    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
        if not writer.isOpened():
            raise IOError(f"VideoWriter could not open: {out_path}")

        # 1. Write pre-alert frames (already captured in ring buffer)
        for frame in pre_frames:
            writer.write(frame)

        # 2. Collect and write post-alert frames
        collected = 0
        while collected < POST_ALERT_LEN:
            try:
                frame = post_queue.get(timeout=2.0)
                if frame is None:
                    # Sentinel sent by capture_loop on shutdown
                    break
                writer.write(frame)
                collected += 1
            except queue.Empty:
                # No frame within 2 s — treat as end-of-stream
                break

        writer.release()
        state.mark_evidence_ready(alert_id)

        total = len(pre_frames) + collected
        print(
            f"[evidence] ✓ {alert_id}  "
            f"{total} frames ({len(pre_frames)} pre + {collected} post) "
            f"→ {out_path}"
        )

    except Exception as exc:
        state.mark_evidence_error(alert_id)
        print(f"[evidence][ERROR] Failed to write {alert_id}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Capture + inference thread
# ─────────────────────────────────────────────────────────────────────────────

def capture_loop() -> None:
    """
    Single long-lived daemon thread.

    Each iteration:
      1.  Read one raw BGR frame from VIDEO_SOURCE.
      2.  Feed raw frame into all active post-alert queues (evidence writers).
      3.  Run ViolenceInferencePipeline.process_frame() for annotation.
      4.  Push the raw frame into the ring buffer.
      5.  JPEG-encode the annotated frame → AppState for MJPEG delivery.
      6.  On violence detection (gated by ALERT_COOLDOWN):
            a. Broadcast SSE alert payload to all subscribers.
            b. Snapshot ring buffer → pre_frames list.
            c. Spin up _write_evidence_clip in a fresh daemon thread.
      7.  Sleep to honour TARGET_FPS cap.
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(
        f"[capture_loop] device={device}  source={VIDEO_SOURCE}  "
        f"weights={WEIGHTS_PATH}  threshold={THRESHOLD}"
    )

    pipeline = ViolenceInferencePipeline(
        weights_path=WEIGHTS_PATH,
        device=device,
        threshold=THRESHOLD,
        stride=STRIDE,
    )

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open video source: {VIDEO_SOURCE}")
        state.running = False
        return

    src_fps   = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_dur = 1.0 / TARGET_FPS

    # Ring buffer of raw (unannotated) frames for pre-alert capture
    ring: deque[np.ndarray] = deque(maxlen=RING_BUFFER_LEN)

    # Active post-alert queues: each entry is [queue.Queue, frames_remaining]
    active_post_queues: list[list] = []

    last_alert_time = 0.0
    state.running   = True
    print("[capture_loop] Frame loop started.")

    while state.running:
        t0 = time.perf_counter()

        ret, raw = cap.read()
        if not ret:
            # Loop the video file from the beginning
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            pipeline.reset()
            continue

        # ── Step 2: feed post-alert queues BEFORE inference ───────────────
        # Feeding first ensures post-alert frames reflect real wall-clock order.
        still_active: list[list] = []
        for entry in active_post_queues:
            post_q, remaining = entry
            if remaining > 0:
                try:
                    post_q.put_nowait(raw.copy())
                except queue.Full:
                    pass  # writer can't keep up — skip this frame
                entry[1] -= 1
                still_active.append(entry)
            # remaining == 0 → writer has enough frames; drop the entry
        active_post_queues = still_active

        # ── Step 3: annotate via inference pipeline ───────────────────────
        annotated = pipeline.process_frame(raw)

        # ── Step 4: update ring buffer with raw frame ─────────────────────
        ring.append(raw.copy())

        # ── Step 5: JPEG-encode annotated frame for MJPEG stream ──────────
        ok, jpg_buf = cv2.imencode(
            ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        )
        if ok:
            state.set_frame(jpg_buf.tobytes())

        # ── Step 6: check for violence trigger ────────────────────────────
        now = time.time()
        if (
            pipeline._last_label == VIOLENCE_CLS
            and now - last_alert_time > ALERT_COOLDOWN
        ):
            last_alert_time = now
            alert_id = f"alert-{int(now * 1000)}"

            payload: dict = {
                "id":         alert_id,
                "timestamp":  datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "isoTime":    datetime.now(timezone.utc).isoformat(),
                "confidence": round(pipeline._last_conf * 100, 1),
                "type":       "Violence",
                "severity":   _severity(pipeline._last_conf),
                "cameraId":   "CAM-01",
                "location":   (
                    str(VIDEO_SOURCE)
                    if isinstance(VIDEO_SOURCE, str)
                    else "Webcam"
                ),
            }
            state.broadcast_alert(payload)

            # Snapshot current ring buffer (copy so it keeps rotating freely)
            pre_frames: list[np.ndarray] = list(ring)

            # Create a dedicated queue for this clip's post-alert frames
            post_q: queue.Queue = queue.Queue(maxsize=POST_ALERT_LEN + 32)
            active_post_queues.append([post_q, POST_ALERT_LEN])

            # Launch evidence writer — completely non-blocking for the stream
            threading.Thread(
                target=_write_evidence_clip,
                args=(alert_id, pre_frames, post_q, src_fps, width, height),
                daemon=True,
                name=f"evidence-{alert_id}",
            ).start()

            print(
                f"[capture_loop] ⚡ Alert {alert_id}  "
                f"conf={pipeline._last_conf:.1%}  "
                f"pre_buf={len(pre_frames)}"
            )

        # ── Step 7: frame-rate cap ────────────────────────────────────────
        elapsed = time.perf_counter() - t0
        wait    = frame_dur - elapsed
        if wait > 0:
            time.sleep(wait)

    # Shutdown: send sentinel to any still-running writers
    for entry in active_post_queues:
        try:
            entry[0].put_nowait(None)
        except queue.Full:
            pass

    cap.release()
    print("[capture_loop] Thread exited cleanly.")


def _severity(conf: float) -> str:
    if conf >= 0.85:
        return "critical"
    if conf >= 0.65:
        return "high"
    return "medium"


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI application
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    t = threading.Thread(target=capture_loop, daemon=True, name="capture")
    t.start()
    yield
    state.running = False
    t.join(timeout=5)


app = FastAPI(
    title="SentinelEye API",
    description="Violence Detection — MJPEG stream · SSE alerts · Evidence DVR",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 1 — MJPEG live stream
# ─────────────────────────────────────────────────────────────────────────────

async def _mjpeg_generator() -> AsyncGenerator[bytes, None]:
    boundary = b"--frame\r\n"
    while True:
        jpg = state.get_frame()
        if jpg is not None:
            yield (
                boundary
                + b"Content-Type: image/jpeg\r\n"
                + b"Content-Length: " + str(len(jpg)).encode() + b"\r\n"
                + b"\r\n"
                + jpg
                + b"\r\n"
            )
        await asyncio.sleep(1 / TARGET_FPS)


@app.get("/video_feed", summary="Live annotated MJPEG stream", tags=["Stream"])
async def video_feed():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control":     "no-cache, no-store, must-revalidate",
            "Pragma":            "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 2 — SSE alert feed
# ─────────────────────────────────────────────────────────────────────────────

async def _sse_generator(q: queue.Queue) -> AsyncGenerator[bytes, None]:
    try:
        last_ping = time.time()
        while True:
            # Drain all queued alerts without blocking the event loop
            while True:
                try:
                    data = q.get_nowait()
                    yield f"data: {data}\n\n".encode()
                except queue.Empty:
                    break
            # Keep-alive comment every 15 s
            if time.time() - last_ping > 15:
                yield b": ping\n\n"
                last_ping = time.time()
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass
    finally:
        state.unsubscribe(q)


@app.get("/alerts", summary="SSE violence alert feed", tags=["Stream"])
async def alerts():
    q = state.subscribe()
    return StreamingResponse(
        _sse_generator(q),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 3 — Evidence download
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/download_evidence/{alert_id}",
    summary="Download compiled evidence clip",
    tags=["Evidence"],
    responses={
        200: {"description": "Evidence .mp4 file ready for download"},
        202: {"description": "Clip is still being compiled — retry in a few seconds"},
        404: {"description": "No evidence record for this alert ID"},
        422: {"description": "Malformed alert_id"},
        500: {"description": "Evidence write failed on server"},
    },
)
async def download_evidence(alert_id: str):
    """
    Returns the DVR evidence clip for *alert_id* as a downloadable .mp4.

    The clip contains up to RING_BUFFER_LEN pre-alert frames followed by
    POST_ALERT_LEN post-alert frames at the source video's native frame-rate.

    HTTP 202 is returned while the background writer is still collecting
    post-alert frames.  The frontend should poll / retry on 202.
    """
    # Sanitise: only accept "alert-<digits>"
    if not alert_id.startswith("alert-") or not alert_id[6:].isdigit():
        raise HTTPException(status_code=422, detail="Invalid alert_id format.")

    status = state.get_evidence_status(alert_id)

    if status is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No evidence record found for '{alert_id}'. "
                "The alert may have occurred before this server session."
            ),
        )

    if status == "writing":
        raise HTTPException(
            status_code=202,
            detail="Evidence clip is still being compiled. Please retry in a few seconds.",
        )

    if status == "error":
        raise HTTPException(
            status_code=500,
            detail="Evidence clip write failed on the server.",
        )

    # status == "ready"
    clip_path = EVIDENCE_DIR / f"{alert_id}.mp4"
    if not clip_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Evidence file was registered as ready but is missing on disk.",
        )

    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
        filename=f"{alert_id}.mp4",
        headers={
            # Force browser "Save As" dialogue instead of inline playback
            "Content-Disposition": f'attachment; filename="{alert_id}.mp4"',
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 4 — Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", summary="System status", tags=["System"])
async def health():
    stats = state.evidence_stats()
    return {
        "status":        "ok" if state.running else "starting",
        "source":        str(VIDEO_SOURCE),
        "threshold":     THRESHOLD,
        "device":        "cuda" if torch.cuda.is_available() else "cpu",
        "clips_ready":   stats["ready"],
        "clips_writing": stats["writing"],
        "clips_error":   stats["error"],
        "evidence_dir":  str(EVIDENCE_DIR.resolve()),
    }
