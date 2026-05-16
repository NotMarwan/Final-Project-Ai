# AI Sentinel Video Performance Overhaul — Implementation Plan

> See also: [Design Doc](VIDEO_PERFORMANCE_OVERHAUL_DESIGN.md) | [README](../README.md) | [WebRTC Streaming Plan](superpowers/plans/2026-05-16-phase1-webrtc-streaming.md)
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix choppy video, detection lag, and frame dropping by decoupling capture from AI inference, optimizing inference paths, and replacing MJPEG with modern streaming.

**Architecture:** Producer-consumer frame pipeline with ring buffer. AI workers run asynchronously on every Nth frame. Stream renderer always shows the latest captured frame with most recent (possibly interpolated) overlay metadata. WebRTC replaces MJPEG for sub-100ms latency.

**Tech Stack:** Python 3.11, FastAPI, OpenCV, PyTorch/ONNX, aiortc (WebRTC), Ultralytics YOLO

---

## Task 1: Remove Destructive Frame Skipping

**Files:**
- Modify: `backend/api.py:1240-1246`

**Problem:** File-based sources intentionally discard 75% of frames.

- [ ] **Step 1: Remove frame skip loop**

Find this code in `backend/api.py` around line 1240:

```python
        if _is_rtsp(current_source) or _is_live_source(current_source):
            ret, raw = _drain_to_latest(cap)
        else:
            ret, raw = cap.read()
            # For file-based sources (demo clips), skip frames to keep stream responsive
            if ret:
                for _ in range(3):
                    skip_ret, _ = cap.read()
                    if not skip_ret:
                        break
```

Replace with:

```python
        if _is_rtsp(current_source) or _is_live_source(current_source):
            ret, raw = _drain_to_latest(cap)
        else:
            ret, raw = cap.read()
```

- [ ] **Step 2: Add frame skip configuration (optional, for very slow machines)**

Instead of hardcoded skip, add an env-controlled skip with default 0:

```python
_FILE_SKIP_FRAMES = int(os.getenv("AI_SENTINEL_FILE_SKIP", "0"))
```

Then:

```python
        if _is_rtsp(current_source) or _is_live_source(current_source):
            ret, raw = _drain_to_latest(cap)
        else:
            ret, raw = cap.read()
            if ret and _FILE_SKIP_FRAMES > 0:
                for _ in range(_FILE_SKIP_FRAMES):
                    skip_ret, _ = cap.read()
                    if not skip_ret:
                        break
```

- [ ] **Step 3: Verify with a test video**

Run the backend with a demo clip and visually confirm smoother motion.

```bash
cd backend
python api.py
```

Open the dashboard and check `/video_feed`. Movement should immediately feel less jerky.

- [ ] **Step 4: Commit**

```bash
git add backend/api.py
git commit -m "fix(pipeline): remove hardcoded 75% frame discard for file sources"
```

---

## Task 2: Create Async Frame Producer-Consumer Pipeline

**Files:**
- Create: `backend/frame_pipeline.py`
- Modify: `backend/api.py` (integrate new pipeline)

**Problem:** Everything runs in one thread. AI blocks video.

- [ ] **Step 1: Create frame ring buffer and producer thread**

Create `backend/frame_pipeline.py`:

```python
"""Async frame pipeline: decouple capture, AI, and streaming."""
from __future__ import annotations

import threading
import queue
import time
from collections import deque
from typing import Optional, Callable
from dataclasses import dataclass
import numpy as np


@dataclass
class FramePacket:
    """A captured frame with metadata."""
    frame: np.ndarray
    timestamp: float
    frame_number: int
    source_id: str


@dataclass
class OverlayMetadata:
    """AI-derived overlays for a frame (can be from a recent frame)."""
    tracks: list
    person_count: int
    is_threat: bool
    threat_confidence: float
    weapon_score: float
    latency_ms: float
    ai_timestamp: float


class FrameRingBuffer:
    """Thread-safe ring buffer for recent frames."""
    def __init__(self, maxlen: int = 30):
        self._buffer: deque[FramePacket] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._latest: Optional[FramePacket] = None

    def push(self, packet: FramePacket):
        with self._lock:
            self._buffer.append(packet)
            self._latest = packet

    def latest(self) -> Optional[FramePacket]:
        with self._lock:
            return self._latest

    def get_since(self, timestamp: float) -> list[FramePacket]:
        with self._lock:
            return [p for p in self._buffer if p.timestamp >= timestamp]


class AsyncFramePipeline:
    """
    Decouples video capture from AI inference and streaming.

    - Producer thread: captures frames at source FPS, pushes to ring buffer
    - AI worker threads: pull frames from ring buffer, run inference, push metadata
    - Stream thread: always reads latest frame + latest metadata, renders, encodes
    """

    def __init__(
        self,
        source: str | int,
        camera_id: str,
        ai_callback: Callable[[np.ndarray], OverlayMetadata],
        ai_interval_frames: int = 5,
        ring_buffer_size: int = 30,
    ):
        self.source = source
        self.camera_id = camera_id
        self.ai_callback = ai_callback
        self.ai_interval_frames = max(1, ai_interval_frames)
        self.ring = FrameRingBuffer(maxlen=ring_buffer_size)
        self._overlay_metadata: Optional[OverlayMetadata] = None
        self._overlay_lock = threading.Lock()

        self._running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._ai_thread: Optional[threading.Thread] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._frame_counter = 0

    @property
    def latest_overlay(self) -> Optional[OverlayMetadata]:
        with self._overlay_lock:
            return self._overlay_metadata

    def start(self):
        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, name=f"capture-{self.camera_id}")
        self._ai_thread = threading.Thread(target=self._ai_loop, name=f"ai-{self.camera_id}")
        self._capture_thread.start()
        self._ai_thread.start()

    def stop(self):
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
        if self._ai_thread:
            self._ai_thread.join(timeout=2.0)

    def _capture_loop(self):
        """Continuously capture frames and push to ring buffer."""
        import cv2
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            print(f"[FramePipeline] Failed to open source: {self.source}")
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_delay = 1.0 / fps
        frame_num = 0

        while self._running:
            t0 = time.perf_counter()
            ret, frame = cap.read()
            if not ret:
                if isinstance(self.source, int) or str(self.source).startswith("rtsp"):
                    time.sleep(0.1)
                    continue
                # File ended — loop
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            frame_num += 1
            packet = FramePacket(
                frame=frame,
                timestamp=time.time(),
                frame_number=frame_num,
                source_id=self.camera_id,
            )
            self.ring.push(packet)

            elapsed = time.perf_counter() - t0
            sleep_time = max(0, frame_delay - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        cap.release()

    def _ai_loop(self):
        """Run AI inference on selected frames, never block capture."""
        while self._running:
            latest = self.ring.latest()
            if latest is None:
                time.sleep(0.01)
                continue

            # Only run AI every N frames to reduce load
            if latest.frame_number % self.ai_interval_frames != 0:
                time.sleep(0.01)
                continue

            t0 = time.perf_counter()
            try:
                metadata = self.ai_callback(latest.frame)
                metadata.ai_timestamp = latest.timestamp
                metadata.latency_ms = (time.perf_counter() - t0) * 1000
                with self._overlay_lock:
                    self._overlay_metadata = metadata
            except Exception as exc:
                print(f"[FramePipeline] AI error: {exc}")

            # Brief sleep to prevent CPU spin when AI is faster than interval
            time.sleep(0.005)
```

- [ ] **Step 2: Integrate into camera_worker**

In `backend/api.py`, replace the main camera_worker loop body. Instead of the synchronous loop, use `AsyncFramePipeline`. This is a significant refactor — create a helper function inside `camera_worker`:

```python
# Inside camera_worker, replace the while loop starting at line 1233

from frame_pipeline import AsyncFramePipeline, OverlayMetadata

def _run_ai_on_frame(frame):
    """Callback for the async pipeline. Runs all AI models on one frame."""
    # Weapon detection
    weapon_signal = weapon_engine.process_frame(frame)
    weapon_score = float(weapon_signal.get("score", 0.0))

    # Person detection
    detections = person_detector.detect(frame) if person_detector else []
    tracks = centroid_tracker.update(detections) if centroid_tracker else []
    person_count = len(tracks)

    # Violence inference (this is the expensive one — consider running less frequently)
    # Note: For now, we skip violence in the per-frame callback and run it separately
    # via the existing ai_executor if needed. The overlay can use cached violence state.

    is_threat = bool(
        getattr(pipeline, "_last_label", None) == VIOLENCE_CLS
        and getattr(pipeline, "_last_conf", 0) > 0.3
    )

    return OverlayMetadata(
        tracks=tracks,
        person_count=person_count,
        is_threat=is_threat,
        threat_confidence=getattr(pipeline, "_last_conf", 0.0) * 100,
        weapon_score=weapon_score,
        latency_ms=0.0,
        ai_timestamp=time.time(),
    )

pipeline_obj = AsyncFramePipeline(
    source=source,
    camera_id=camera_id,
    ai_callback=_run_ai_on_frame,
    ai_interval_frames=3,  # Run AI every 3rd captured frame
    ring_buffer_size=30,
)
pipeline_obj.start()

# Stream rendering loop (runs independently at TARGET_FPS)
while state.running and not (stop_event and stop_event.is_set()):
    t0 = time.perf_counter()

    packet = pipeline_obj.ring.latest()
    if packet is None:
        time.sleep(0.01)
        continue

    overlay = pipeline_obj.latest_overlay
    tracks = overlay.tracks if overlay else []
    person_count = overlay.person_count if overlay else 0
    is_threat = overlay.is_threat if overlay else False
    threat_confidence = overlay.threat_confidence if overlay else 0.0

    # Always annotate the LATEST frame with the LATEST metadata
    annotated = annotate_frame(
        frame=packet.frame,
        tracks=tracks,
        person_count=person_count,
        is_threat=is_threat,
        threat_confidence=threat_confidence,
        camera_id=camera_id,
        fps=_current_fps,
    )

    ok, jpg_buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if ok:
        state.set_frame(camera_id, jpg_buf.tobytes())

    # Update FPS counter
    _fps_counter += 1
    now_time = time.perf_counter()
    if now_time - _fps_timer >= 1.0:
        _current_fps = _fps_counter / (now_time - _fps_timer)
        _fps_counter = 0
        _fps_timer = now_time

    # Maintain target stream FPS (20 FPS for the output stream)
    elapsed = time.perf_counter() - t0
    sleep_time = max(0, (1.0 / TARGET_FPS) - elapsed)
    if sleep_time > 0:
        time.sleep(sleep_time)

pipeline_obj.stop()
```

- [ ] **Step 3: Test the decoupled pipeline**

```bash
cd backend
python -c "from frame_pipeline import FrameRingBuffer, AsyncFramePipeline; print('Import OK')"
python api.py
```

Open the dashboard. Video should now be smooth even if AI boxes lag slightly.

- [ ] **Step 4: Commit**

```bash
git add backend/frame_pipeline.py backend/api.py
git commit -m "feat(pipeline): async producer-consumer frame pipeline decouples capture from AI"
```

---

## Task 3: Export YOLO Models to ONNX for 2-3x CPU Speedup

**Files:**
- Create: `backend/export_models.py`
- Modify: `backend/weapon.py` — Add ONNX backend path
- Modify: `backend/person_detector.py` — Add ONNX path

**Problem:** PyTorch `.pt` models are not optimized for inference. ONNX Runtime uses graph optimizations and can run on CPU much faster.

- [ ] **Step 1: Create model export script**

Create `backend/export_models.py`:

```python
"""Export PyTorch YOLO models to ONNX for faster inference."""
import os
import sys
from pathlib import Path

def export_yolo_to_onnx(pt_path: str, onnx_path: str, imgsz: int = 640):
    """Export Ultralytics YOLO model to ONNX format."""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ERROR: ultralytics not installed. pip install ultralytics")
        sys.exit(1)

    if not Path(pt_path).exists():
        print(f"ERROR: Model not found: {pt_path}")
        sys.exit(1)

    print(f"Loading {pt_path}...")
    model = YOLO(pt_path)

    print(f"Exporting to ONNX (imgsz={imgsz})...")
    # Export to ONNX with optimizations
    model.export(
        format="onnx",
        imgsz=imgsz,
        dynamic=True,  # Allow variable batch sizes
        simplify=True,  # Use onnx-simplifier for graph cleanup
        opset=12,
    )

    # Ultralytics saves to same directory with .onnx extension
    expected = Path(pt_path).with_suffix(".onnx")
    if expected.exists():
        print(f"ONNX model saved: {expected}")
        # Optionally move to specified path
        if str(expected) != onnx_path:
            import shutil
            shutil.copy(str(expected), onnx_path)
            print(f"Copied to: {onnx_path}")
    else:
        print(f"Export may have failed. Expected: {expected}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export YOLO to ONNX")
    parser.add_argument("--pt", default="backend/weapon_yolo.pt", help="Input .pt path")
    parser.add_argument("--onnx", default="backend/weapon_yolo.onnx", help="Output .onnx path")
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()
    export_yolo_to_onnx(args.pt, args.onnx, args.imgsz)
```

- [ ] **Step 2: Install ONNX Runtime**

```bash
cd backend
pip install onnxruntime-gpu  # Use onnxruntime (CPU) if no NVIDIA GPU
# Or for CPU only:
# pip install onnxruntime
```

- [ ] **Step 3: Add ONNX inference path to weapon.py**

In `backend/weapon.py`, add an ONNX backend option:

```python
class _ONNXBackend:
    """ONNX Runtime backend for YOLO inference."""

    def __init__(self, onnx_path: str, min_confidence: float, labels: tuple[str, ...]):
        self.min_confidence = min_confidence
        self.labels = labels
        import onnxruntime as ort

        # Use GPU if available, else CPU
        providers = ort.get_available_providers()
        preferred = ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"]
        session_providers = [p for p in preferred if p in providers]
        if not session_providers:
            session_providers = providers  # fallback

        print(f"[ONNXBackend] Using providers: {session_providers}")
        self.session = ort.InferenceSession(onnx_path, providers=session_providers)
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape  # [batch, 3, h, w]
        self.img_size = self.input_shape[-1] if self.input_shape[-1] else 640

        # Parse class names from ONNX metadata if available
        meta = self.session.get_modelmeta().custom_metadata_map
        names_str = meta.get("names", "")
        if names_str:
            import json
            self._categories = {int(k): str(v).lower() for k, v in json.loads(names_str).items()}
        else:
            self._categories = {}

    def predict(self, frame: np.ndarray) -> list[tuple[float, str]]:
        import cv2
        # Preprocess: resize, normalize, BGR->RGB, CHW
        h, w = frame.shape[:2]
        img = cv2.resize(frame, (self.img_size, self.img_size), interpolation=cv2.INTER_LINEAR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
        img = np.expand_dims(img, axis=0)   # Add batch dim

        outputs = self.session.run(None, {self.input_name: img})
        # YOLOv8 ONNX output shape: [1, 84, 8400] — parse as needed
        # For simplicity, fall back to Ultralytics postprocessing if available,
        # or implement NMS here.
        # As a shortcut, we can wrap the ONNX model in a minimal YOLO predictor:
        return []
```

**Alternative (Recommended):** Use Ultralytics built-in ONNX support. When you export YOLO to ONNX, Ultralytics handles the model loading transparently:

```python
# In _YOLOBackend.__init__, change loading:
if weight_path.endswith(".onnx"):
    self._model = YOLO(weight_path)  # Ultralytics auto-detects ONNX
else:
    self._model = YOLO(weight_path)
```

Ultralytics YOLO class automatically uses ONNX Runtime when given an `.onnx` file. So the simplest fix is:

- Export the model
- Change the config/env to point to `.onnx` instead of `.pt`

- [ ] **Step 4: Export your weapon model**

```bash
cd "Final Project AI Sentinel"
python backend/export_models.py --pt backend/weapon_yolo.pt --onnx backend/weapon_yolo.onnx
python backend/export_models.py --pt backend/yolov8n.pt --onnx backend/yolov8n.onnx
```

- [ ] **Step 5: Update config or env to use ONNX**

In `backend/.env` or environment:

```bash
WEAPON_WEIGHT_PATH=backend/weapon_yolo.onnx
```

Or in `backend/config.yml` under weapon section, change `weight_path`.

- [ ] **Step 6: Verify faster inference**

```bash
cd backend
python -c "
from weapon import WeaponConfig, WeaponSignalEngine
import torch, time
config = WeaponConfig(backend='yolo', weight_path='weapon_yolo.onnx')
engine = WeaponSignalEngine(config)
engine.preload()
print('Loaded:', engine.status())
"
```

- [ ] **Step 7: Commit**

```bash
git add backend/export_models.py backend/.env.example
git commit -m "perf(models): add ONNX export and inference path for 2-3x CPU speedup"
```

---

## Task 4: Add GPU / CUDA Auto-Detection & Half-Precision

**Files:**
- Modify: `backend/api.py` (device selection)
- Modify: `backend/weapon.py` (half precision option)
- Modify: `backend/person_detector.py` (device passthrough)

**Problem:** Code defaults to CPU even when GPU is available. No half-precision support.

- [ ] **Step 1: Create device utility**

Create `backend/device_config.py`:

```python
"""Centralized device configuration with GPU auto-detection."""
import os
import torch


def get_optimal_device(prefer_gpu: bool = True) -> torch.device:
    """Select the best available device: CUDA > MPS (Apple) > CPU."""
    if not prefer_gpu:
        return torch.device("cpu")

    if torch.cuda.is_available():
        device = torch.device("cuda:0")
        props = torch.cuda.get_device_properties(0)
        print(f"[Device] CUDA GPU detected: {props.name}, {props.total_memory / 1e9:.1f} GB VRAM")
        return device

    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        print("[Device] Apple MPS (Metal) detected")
        return torch.device("mps")

    print("[Device] No GPU detected, using CPU")
    return torch.device("cpu")


def is_cuda(device: torch.device) -> bool:
    return device.type == "cuda"


def enable_half_precision(device: torch.device) -> bool:
    """Enable FP16 half-precision on supported GPUs."""
    if not is_cuda(device):
        return False
    # RTX 20 series and above support FP16 well
    capability = torch.cuda.get_device_capability(device.index or 0)
    if capability[0] >= 7:  # Turing and newer
        print("[Device] FP16 half-precision enabled")
        return True
    return False
```

- [ ] **Step 2: Use device utility everywhere**

In `backend/api.py`, replace all instances of:

```python
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
```

With:

```python
from device_config import get_optimal_device, enable_half_precision

device = get_optimal_device(prefer_gpu=True)
use_fp16 = enable_half_precision(device)
```

- [ ] **Step 3: Pass FP16 to YOLO inference**

In `backend/weapon.py`, modify `_YOLOBackend.predict`:

```python
    def predict(self, frame: np.ndarray, half: bool = False) -> list[tuple[float, str]]:
        try:
            results = self._model.predict(
                frame,
                verbose=False,
                conf=self.min_confidence,
                device=str(self.device),
                half=half,  # FP16 inference
            )
            ...
```

In `WeaponSignalEngine`, pass the `half` flag through from config.

- [ ] **Step 4: Verify GPU is being used**

```bash
cd backend
python -c "
from device_config import get_optimal_device, enable_half_precision
d = get_optimal_device()
print('Device:', d)
print('FP16:', enable_half_precision(d))
"
```

If you have an NVIDIA GPU, you should see CUDA detected. If not, it falls back to CPU gracefully.

- [ ] **Step 5: Commit**

```bash
git add backend/device_config.py backend/api.py backend/weapon.py backend/person_detector.py
git commit -m "perf(gpu): auto-detect CUDA/MPS, add FP16 half-precision support"
```

---

## Task 5: Optimize Visual Annotator & JPEG Encoding

**Files:**
- Modify: `backend/visual_annotator.py`
- Modify: `backend/api.py` (JPEG quality settings)

**Problem:** OpenCV drawing is CPU-heavy. Low JPEG quality causes artifacts.

- [ ] **Step 1: Add quality presets**

In `backend/api.py`, change `JPEG_QUALITY = 60` to a configurable preset:

```python
# Quality presets: low (bandwidth), medium (balanced), high (quality)
JPEG_QUALITY_PRESETS = {
    "low": 50,
    "medium": 75,
    "high": 90,
}
JPEG_QUALITY = JPEG_QUALITY_PRESETS.get(os.getenv("STREAM_QUALITY", "medium").lower(), 75)
```

- [ ] **Step 2: Optimize annotation drawing**

In `backend/visual_annotator.py`, add fast mode that skips expensive effects:

```python
_FAST_MODE = os.getenv("AI_SENTINEL_FAST_ANNOTATE", "true").lower() == "true"

def annotate(
    frame: np.ndarray,
    tracks: list,
    person_count: int = 0,
    is_threat: bool = False,
    threat_confidence: float = 0.0,
    camera_id: str = "",
    fps: float = 0.0,
    threat_person_box: Optional[list[float]] = None,
    fast: bool = _FAST_MODE,
) -> np.ndarray:
    img = frame.copy()
    h, w = img.shape[:2]

    if fast:
        # Fast path: skip trails, glows, and pulsing borders
        for track in tracks:
            x1, y1, x2, y2 = map(int, getattr(track, "bbox", [0, 0, 0, 0]))
            color = getattr(track, "color", (0, 255, 255))
            lw = _BOX_LW_THREAT if is_threat else _BOX_LW_NORMAL
            cv2.rectangle(img, (x1, y1), (x2, y2), color, lw, _LINE_AA)
            badge_text = f"{getattr(track, 'label', '?')} {getattr(track, 'confidence', 0.0):.0%}"
            (tw, th), _ = cv2.getTextSize(badge_text, _FONT, _FONT_SCALE, 1)
            cv2.rectangle(img, (x1, max(0, y1 - th - 6)), (x1 + tw + 10, y1), color, -1, _LINE_AA)
            cv2.putText(img, badge_text, (x1 + 5, max(0, y1 - 5) + th), _FONT, _FONT_SCALE, (0, 0, 0), 1, _LINE_AA)
    else:
        # Original slow path with trails, glows, etc.
        ...  # keep existing implementation
    ...
```

This gives users a choice: turn off expensive visual effects when they need maximum FPS.

- [ ] **Step 3: Test with fast mode**

```bash
AI_SENTINEL_FAST_ANNOTATE=true STREAM_QUALITY=high python backend/api.py
```

- [ ] **Step 4: Commit**

```bash
git add backend/visual_annotator.py backend/api.py
git commit -m "perf(annotate): add fast annotation mode and configurable JPEG quality presets"
```

---

## Task 6: Fix Demo Scripts to Use GPU/Optimized Settings

**Files:**
- Modify: `scripts/weapon_video_demo.py`
- Modify: `scripts/weapon_visual_demo.py`

**Problem:** Demo scripts hardcode `device="cpu"`, producing poor-quality example videos.

- [ ] **Step 1: Update weapon_video_demo.py**

Change:

```python
results = model(frame, verbose=False, conf=args.conf, device="cpu")
```

To:

```python
import torch
from backend.device_config import get_optimal_device
device = get_optimal_device()
results = model(frame, verbose=False, conf=args.conf, device=str(device))
```

Also add `--quality` and `--fast` flags:

```python
parser.add_argument("--quality", choices=["low", "medium", "high"], default="high")
parser.add_argument("--fast", action="store_true", help="Fast annotation mode")
parser.add_argument("--onnx", action="store_true", help="Use ONNX model if available")
```

- [ ] **Step 2: Update weapon_visual_demo.py**

Same changes — remove hardcoded CPU, auto-detect GPU, allow ONNX.

- [ ] **Step 3: Regenerate demo outputs with optimized settings**

```bash
cd "Final Project AI Sentinel"
python scripts/weapon_video_demo.py --quality high --fast --onnx
```

- [ ] **Step 4: Commit**

```bash
git add scripts/weapon_video_demo.py scripts/weapon_visual_demo.py
git commit -m "perf(demos): auto-detect GPU, add quality/fast flags to demo scripts"
```

---

## Task 7: Add WebRTC Streaming as MJPEG Replacement

**Files:**
- Create: `backend/webrtc_streamer.py`
- Modify: `backend/api.py` — Add WebRTC endpoints
- Modify: `components/video-player.tsx` — Add WebRTC player

**Problem:** MJPEG is high-bandwidth, high-latency, and unreliable over networks.

- [ ] **Step 1: Install aiortc**

```bash
cd backend
pip install aiortc av
```

- [ ] **Step 2: Create WebRTC streamer**

Create `backend/webrtc_streamer.py`:

```python
"""WebRTC video streaming for sub-100ms latency."""
import asyncio
import numpy as np
from aiortc import RTCPeerConnection, VideoStreamTrack
from aiortc.contrib.media import MediaBlackhole
from av import VideoFrame
import cv2


class CameraVideoStreamTrack(VideoStreamTrack):
    """A video track that reads from the frame pipeline."""
    kind = "video"

    def __init__(self, frame_getter):
        super().__init__()
        self.frame_getter = frame_getter  # callable that returns latest JPEG bytes or numpy frame

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        frame_data = self.frame_getter()

        if frame_data is None:
            # Return black frame if no data
            img = np.zeros((720, 1280, 3), dtype=np.uint8)
        elif isinstance(frame_data, bytes):
            img = cv2.imdecode(np.frombuffer(frame_data, np.uint8), cv2.IMREAD_COLOR)
        else:
            img = frame_data

        # Ensure RGB for WebRTC
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        frame = VideoFrame.from_ndarray(img, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame


class WebRTCManager:
    """Manages peer connections per camera."""
    def __init__(self):
        self.pcs: dict[str, RTCPeerConnection] = {}

    async def offer(self, camera_id: str, frame_getter, sdp: str, type_: str):
        pc = RTCPeerConnection()
        self.pcs[camera_id] = pc

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if pc.connectionState == "failed":
                await pc.close()
                self.pcs.pop(camera_id, None)

        video_track = CameraVideoStreamTrack(frame_getter)
        pc.addTrack(video_track)

        await pc.setRemoteDescription({"sdp": sdp, "type": type_})
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

    async def close(self, camera_id: str):
        pc = self.pcs.pop(camera_id, None)
        if pc:
            await pc.close()
```

- [ ] **Step 3: Add WebRTC endpoints to api.py**

```python
from webrtc_streamer import WebRTCManager
webrtc_manager = WebRTCManager()

@app.post("/webrtc/offer/{camera_id}")
async def webrtc_offer(camera_id: str, request: Request):
    """Accept SDP offer and return SDP answer for WebRTC connection."""
    if camera_id not in CAMERA_SOURCES:
        raise HTTPException(status_code=404, detail="Camera not found")
    data = await request.json()
    sdp = data.get("sdp")
    type_ = data.get("type")
    if not sdp or not type_:
        raise HTTPException(status_code=400, detail="Missing sdp or type")

    def frame_getter():
        return state.get_frame(camera_id)

    answer = await webrtc_manager.offer(camera_id, frame_getter, sdp, type_)
    return answer
```

- [ ] **Step 4: Add WebRTC player to frontend**

In `components/video-player.tsx`, add a WebRTC mode:

```typescript
// Add to video-player.tsx
const useWebRTC = (cameraId: string, enabled: boolean) => {
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const pc = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
    });
    pcRef.current = pc;

    pc.ontrack = (event) => {
      if (event.streams && event.streams[0]) {
        setRemoteStream(event.streams[0]);
      }
    };

    fetch(`${API_BASE}/webrtc/offer/${cameraId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sdp: "", type: "offer" }) // Actually need proper SDP flow
    }).then(...); // Full SDP exchange needed

    return () => {
      pc.close();
    };
  }, [cameraId, enabled]);

  return remoteStream;
};
```

**Note:** The full WebRTC SDP exchange requires a proper signaling implementation. The above is the skeleton. For a production-grade setup, use a library like `simple-peer` or implement a proper signaling server over WebSocket.

- [ ] **Step 5: Commit**

```bash
git add backend/webrtc_streamer.py backend/api.py components/video-player.tsx
git commit -m "feat(streaming): add WebRTC support for sub-100ms latency video"
```

---

## Task 8: Dockerize for Consistent Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

**Problem:** Environment differences cause "works on my machine" issues. Docker ensures consistent runtime with all dependencies.

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    libgl1-mesa-glx libglib2.0-0 \
    libsm6 libxext6 libxrender-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy project
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY public/ ./public/

# Expose API port
EXPOSE 8000

# Default to CPU if no GPU, but CUDA runtime supports GPU if available
ENV PYTHONUNBUFFERED=1
ENV AI_SENTINEL_ENABLE_CAPTURE_LOOP=true

CMD ["python3", "backend/api.py"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
version: "3.8"
services:
  ai-sentinel:
    build: .
    ports:
      - "8000:8000"
    environment:
      - AI_SENTINEL_ENABLE_CAPTURE_LOOP=true
      - STREAM_QUALITY=high
      - AI_SENTINEL_FAST_ANNOTATE=true
    volumes:
      - ./backend:/app/backend:ro
      - ./public:/app/public:ro
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

- [ ] **Step 3: Create .dockerignore**

```
__pycache__/
*.pyc
*.pt
*.onnx
.env
node_modules/
.next/
desktop/
reports/
evidence/
.git/
```

- [ ] **Step 4: Build and test**

```bash
docker-compose build
docker-compose up
```

If you have an NVIDIA GPU with Docker runtime installed, it will use GPU. Otherwise it falls back to CPU.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat(infra): add Docker support for consistent GPU/CPU deployment"
```

---

## Task 9: Add Performance Metrics & Monitoring

**Files:**
- Create: `backend/metrics.py`
- Modify: `backend/api.py` — Add metrics endpoint

**Problem:** You can't optimize what you don't measure.

- [ ] **Step 1: Create metrics collector**

Create `backend/metrics.py`:

```python
"""Real-time performance metrics for the video pipeline."""
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque


@dataclass
class PipelineMetrics:
    capture_fps: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    inference_latency_ms: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    encode_latency_ms: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    stream_fps: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    ai_queue_depth: int = 0
    dropped_frames: int = 0

    def record_capture(self, fps: float):
        self.capture_fps.append(fps)

    def record_inference(self, latency_ms: float):
        self.inference_latency_ms.append(latency_ms)

    def record_encode(self, latency_ms: float):
        self.encode_latency_ms.append(latency_ms)

    def record_stream(self, fps: float):
        self.stream_fps.append(fps)

    def summary(self) -> dict:
        def avg(d: Deque[float]) -> float:
            return sum(d) / len(d) if d else 0.0

        return {
            "captureFps": round(avg(self.capture_fps), 1),
            "inferenceLatencyMs": round(avg(self.inference_latency_ms), 1),
            "encodeLatencyMs": round(avg(self.encode_latency_ms), 1),
            "streamFps": round(avg(self.stream_fps), 1),
            "aiQueueDepth": self.ai_queue_depth,
            "droppedFrames": self.dropped_frames,
        }
```

- [ ] **Step 2: Add /system/metrics endpoint**

In `backend/api.py`:

```python
metrics = PipelineMetrics()

@app.get("/system/metrics")
async def system_metrics():
    return {
        "pipeline": metrics.summary(),
        "decisionLayer": state.get_decision_layer_status(),
        "device": str(device) if 'device' in globals() else "unknown",
    }
```

- [ ] **Step 3: Instrument the pipeline**

In `camera_worker` or `AsyncFramePipeline`, call:

```python
metrics.record_capture(capture_fps)
metrics.record_inference(inference_ms)
metrics.record_encode(encode_ms)
metrics.record_stream(stream_fps)
```

- [ ] **Step 4: Commit**

```bash
git add backend/metrics.py backend/api.py
git commit -m "feat(monitoring): add real-time pipeline performance metrics endpoint"
```

---

## Task 10: Create Cloud Deployment Guide (AWS/GCP)

**Files:**
- Create: `docs/CLOUD_DEPLOYMENT.md`
- Create: `infra/terraform/main.tf` (optional)

**Problem:** If you want to deploy to the cloud for better uptime or remote access.

- [ ] **Step 1: Write AWS deployment guide**

Create `docs/CLOUD_DEPLOYMENT.md`:

```markdown
# Cloud Deployment Guide

## AWS (Recommended for GPU)

### Instance Type
- **g4dn.xlarge** — NVIDIA T4 GPU, 4 vCPU, 16GB RAM (~$0.50/hour spot)
- **g4dn.2xlarge** — For 4+ camera streams

### Steps
1. Launch EC2 instance with NVIDIA GPU AMI
2. Install NVIDIA drivers and Docker runtime:
   ```bash
   sudo apt update
   sudo apt install -y nvidia-driver-535
   sudo reboot
   ```
3. Install NVIDIA Container Toolkit:
   ```bash
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
   curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
   sudo apt update && sudo apt install -y nvidia-container-toolkit
   sudo systemctl restart docker
   ```
4. Clone and run:
   ```bash
   git clone <your-repo>
   cd ai-sentinel
   docker-compose up -d
   ```
5. Open security group port 8000
6. Access at `http://<ec2-ip>:8000`

### Auto-scaling (Optional)
- Use AWS ECS with GPU task definitions
- ALB for load balancing across instances
- S3 for evidence clip storage

## GCP
- Use **n1-standard-4** with NVIDIA T4 attached
- Container-Optimized OS + NVIDIA drivers
- Deploy via Cloud Run (GPU limited preview) or GKE
```

- [ ] **Step 2: Commit**

```bash
git add docs/CLOUD_DEPLOYMENT.md
git commit -m "docs(infra): add AWS/GCP cloud deployment guide"
```

---

## Summary Checklist

| Task | Impact | Effort | Hardware Needed |
|------|--------|--------|----------------|
| 1. Remove frame skip | **Immediate smoothness** | 10 min | None |
| 2. Async pipeline | **3-5x throughput** | 2-3 hours | None |
| 3. ONNX export | **2-3x inference speed** | 1 hour | None |
| 4. GPU auto-detect | **10-50x if you have GPU** | 30 min | NVIDIA GPU |
| 5. Fast annotate + JPEG | **20% lighter CPU** | 30 min | None |
| 6. Fix demo scripts | **Better examples** | 30 min | None |
| 7. WebRTC | **Sub-100ms latency** | 3-4 hours | None |
| 8. Docker | **Consistent deploy** | 1 hour | None |
| 9. Metrics | **Visibility** | 1 hour | None |
| 10. Cloud guide | **Remote hosting** | 30 min | Cloud $ |

## Recommended Execution Order

**Day 1 (Free improvements, do these NOW):**
1. Task 1 — Remove frame skip (immediate visible improvement)
2. Task 2 — Async pipeline (fixes the core architecture problem)
3. Task 5 — Fast annotate + JPEG quality (minor but visible)

**Day 2 (Optimization):**
4. Task 3 — ONNX export (2-3x speedup on same hardware)
5. Task 4 — GPU auto-detect (massive if you have GPU)
6. Task 6 — Fix demo scripts

**Day 3-4 (Infrastructure):**
7. Task 7 — WebRTC (replace MJPEG for professional streaming)
8. Task 8 — Docker (deployment consistency)
9. Task 9 — Metrics (know your numbers)
10. Task 10 — Cloud guide (if you need remote access)

## How to Test Each Phase

After each task:
1. Start backend: `python backend/api.py`
2. Open dashboard and video feed
3. Run: `curl http://localhost:8000/system/metrics`
4. Check: capture FPS should be close to source FPS (25-30)
5. Check: stream FPS should be stable at 15-20
6. Check: inference latency should decrease with each optimization
7. Visual check: people movement should look smooth, boxes should not lag wildly behind

## Success Criteria

- [ ] Video motion is smooth (no jerky skipping)
- [ ] Detection boxes stay close to people (lag < 200ms)
- [ ] Stream FPS is stable (>15 FPS)
- [ ] CPU usage is reasonable (<80% on target hardware)
- [ ] Demo videos look professional (high quality, smooth)
- [ ] Metrics endpoint shows healthy numbers

---

Plan saved to: `docs/VIDEO_PERFORMANCE_OVERHAUL_PLAN.md`
