# AI Sentinel Video Performance & Streaming Overhaul

## Problem Statement

The current video pipeline suffers from severe performance degradation causing:

1. **People outrunning frames** — choppy, non-smooth movement tracking
2. **Frame quality tied to input quality** — no enhancement, just passthrough with overlays
3. **High latency** — detection boxes lag behind actual person positions
4. **Low effective FPS** — output feels like a slideshow, not real-time video
5. **Poor demo video quality** — weapon_video_demo.py produces stuttering outputs

## Root Cause Analysis

### 1. CPU-Bound Synchronous Pipeline (CRITICAL)

The `camera_worker` in `backend/api.py` runs everything in a **single thread**:

```python
while state.running:
    ret, raw = cap.read()              # Frame capture
    weapon_engine.process_frame(raw)   # YOLO inference (blocking, 50-300ms on CPU)
    ai_future = ai_executor.submit(...) # Violence detection (another 100-500ms)
    person_detector.detect(raw)        # YOLOv8 person detect (another 50-200ms)
    annotate_frame(raw, ...)           # OpenCV drawing (CPU intensive)
    cv2.imencode(".jpg", ...)          # JPEG encoding
    state.set_frame(camera_id, ...)    # Store for streaming
    time.sleep(max(0, (1.0 / 20) - elapsed))  # Target 20 FPS (rarely achieved)
```

**On a CPU without CUDA GPU:**
- YOLO weapon detection: ~80-150ms/frame
- YOLOv8 person detection: ~40-80ms/frame  
- Violence X3D inference: ~150-400ms/frame
- OpenCV annotation: ~10-30ms/frame
- JPEG encoding: ~5-15ms/frame
- **Total per frame: 285-675ms = 1.4-3.5 FPS actual**

This is why people "outrun the frames" — the pipeline processes 1 frame every 300-700ms while the video source runs at 25-30 FPS.

### 2. Destructive Frame Skipping (CRITICAL)

For file-based sources (demo clips), the code intentionally **destroys 75% of frames**:

```python
ret, raw = cap.read()
for _ in range(3):  # Skip 3 frames after every captured frame
    skip_ret, _ = cap.read()
```

This was meant to "keep stream responsive" but it actually **causes the choppy motion**. You're throwing away the intermediate frames that would make movement smooth.

### 3. Single-Threaded AI Inference

The background AI executor has `max_workers=1`. Even though face+motion is submitted to a thread pool, weapon detection and person detection run **synchronously in the main loop**. Three AI models compete for the same CPU cores.

### 4. No Frame Buffer / Producer-Consumer Architecture

There is no decoupling between:
- **Frame producer** (video capture at source FPS)
- **Frame consumer** (AI processing at whatever speed it can manage)
- **Frame renderer** (annotation overlays)
- **Frame broadcaster** (MJPEG streaming)

They are all locked together. When AI is slow, the whole stream stalls.

### 5. Low JPEG Quality & Software Encoding

```python
JPEG_QUALITY = 60  # Visible artifacts, blocky compression
```

MJPEG streaming uses software JPEG encoding. No hardware acceleration.

### 6. MJPEG is the Wrong Protocol for Real-Time Video

The frontend receives:
```html
<img src="/video_feed?camera_id=CAM-01" />
```

MJPEG over HTTP:
- No buffering
- No adaptive quality
- Each frame is a separate HTTP chunk
- Browser `<img>` tag has no frame interpolation
- Latency stacks: capture + inference + encode + network + decode + render

### 7. No Hardware Acceleration Options

The codebase has **no support** for:
- ONNX Runtime (CPU/GPU optimized inference)
- TensorRT (NVIDIA GPU acceleration)
- OpenVINO (Intel acceleration)
- CUDA optimizations (half-precision, batch inference)
- Hardware video encoding (NVENC, QuickSync)

### 8. Demo Scripts Use CPU Explicitly

```python
# scripts/weapon_video_demo.py
model = YOLO(args.weights)
results = model(frame, verbose=False, conf=args.conf, device="cpu")  # Hardcoded CPU
```

The demo scripts that generate "example videos" also run on CPU, producing stuttery output files that become the "evidence" of poor quality.

## Why Your PC / Current Setup is Struggling

| Component | Current State | Impact |
|-----------|--------------|--------|
| **Inference Device** | CPU only (no GPU detection/utilization) | 10-50x slower than GPU |
| **Frame Pipeline** | Single-threaded, synchronous | Everything blocks everything |
| **Frame Strategy** | Skip 75% of input frames | Choppy motion, missed action |
| **Video Protocol** | MJPEG over HTTP | High overhead, no buffering |
| **Encoding** | Software JPEG (OpenCV) | Slow, CPU intensive |
| **Model Format** | PyTorch .pt files | Not optimized for inference |
| **Architecture** | Monolithic worker thread | No separation of concerns |

## Solution Architecture

### Phase 1: Emergency Pipeline Fix (Immediate — No New Hardware)

These changes can be done TODAY on your existing PC and will give you 3-5x improvement:

1. **Remove frame skipping** — capture ALL frames, smooth motion immediately
2. **Decouple capture from processing** — separate threads with a frame queue
3. **Make AI truly async** — don't block the stream on inference results
4. **Reduce inference frequency** — run AI on every Nth frame, interpolate overlays
5. **Optimize OpenCV settings** — faster JPEG, buffered capture

### Phase 2: Inference Optimization (1-2 days, depends on hardware)

1. **GPU Utilization** — if you have an NVIDIA GPU, use CUDA + half precision
2. **ONNX Export** — convert YOLO models to ONNX for 2-3x CPU speedup
3. **Model quantization** — INT8 for even faster inference
4. **Batch inference** — process multiple frames together

### Phase 3: Streaming Infrastructure (2-3 days)

1. **Replace MJPEG with WebRTC** — sub-second latency, adaptive bitrate
2. **Add HLS/WebSocket fallback** — for broader compatibility
3. **Hardware encoding** — NVENC/QuickSync for zero-CPU encoding
4. **CDN/edge distribution** — if deploying to AWS/cloud

### Phase 4: Cloud Deployment (Optional, 1-2 days)

1. **Docker containerization** — reproducible deployment
2. **AWS/GCP deployment** — GPU instances for inference
3. **Load balancing** — multiple camera workers across instances
4. **Auto-scaling** — scale inference workers based on load

## Expected Results

| Metric | Current | After Phase 1 | After Phase 2 | After Phase 3 |
|--------|---------|--------------|---------------|---------------|
| Effective FPS | 1-3 FPS | 15-20 FPS | 25-30 FPS | 30 FPS |
| Stream Latency | 500-1000ms | 100-200ms | 50-100ms | <50ms |
| Motion Smoothness | Jerky, skipping | Smooth, all frames | Smooth + real-time | Broadcast quality |
| CPU Usage | 100% (bottlenecked) | 60-80% | 30-50% | 20-30% |
| Detection Lag | 300-500ms behind | 50-100ms behind | Real-time | Real-time |

## Key Design Principles

1. **Never drop frames for "responsiveness"** — dropping frames makes video worse, not better
2. **Capture and inference are separate concerns** — the camera thread should NEVER wait for AI
3. **Display the freshest frame always** — even if AI overlays are 100ms old, show the current video
4. **AI results are metadata, not frame gates** — boxes can lag slightly; video cannot
5. **Measure everything** — log actual FPS, inference latency, queue depths, encode times

## Files to Modify

- `backend/api.py` — Core pipeline rewrite (frame queue, async workers)
- `backend/person_detector.py` — Add frame decimation, batch support
- `backend/weapon.py` — Async inference, result caching
- `backend/visual_annotator.py` — Optimize drawing (reduce overlays, cached fonts)
- `backend/inference.py` — Add ONNX export path, half-precision support
- `scripts/weapon_video_demo.py` — Remove CPU hardcoding, add GPU support
- `components/video-player.tsx` — Add WebRTC support, buffering
- `backend/config.yml` — Add streaming quality settings

## Hardware Recommendations

If you want the BEST results:

| Budget | Recommendation | Expected Gain |
|--------|---------------|---------------|
| $0 (existing PC) | Phase 1 + Phase 2 (ONNX) | 5-10x faster |
| $300-500 | NVIDIA RTX 3060/4060 | 20-50x faster |
| $500-1000 | NVIDIA RTX 4070 + NVENC | 50-100x faster |
| Cloud | AWS g4dn.xlarge (Tesla T4) | 30-50x faster, scalable |

## Risk Assessment

- **Low Risk**: Phase 1 changes (threading, queues, no frame skip) — pure software optimization
- **Medium Risk**: Phase 2 (ONNX export) — model accuracy may shift slightly, requires validation
- **Medium Risk**: Phase 3 (WebRTC) — adds complexity, requires STUN/TURN server config
- **Low Risk**: Phase 4 (Docker/AWS) — infrastructure, doesn't affect core algorithm

## Conclusion

The problem is **NOT** that you need AWS or a server. The problem is that your **single-threaded CPU-bound pipeline drops frames and blocks the video stream on AI inference**. 

You can fix 80% of the issues TODAY with software changes only. A $400 GPU would fix the remaining 20% and make it broadcast-quality.

**Priority order:**
1. Phase 1 (immediate, free, 3-5x improvement)
2. Phase 2 (check if you have a GPU, export ONNX, another 2-3x)
3. Phase 3 (if you need sub-100ms latency for live demos)
4. Phase 4 (only if you need remote/cloud deployment)
