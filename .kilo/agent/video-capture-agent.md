---
name: video-capture-agent
mode: subagent
description: Camera management & frame ingestion specialist
model: stepfun/step-3.5-flash:free
temperature: 0.1
permission:
  edit: allow
  bash: allow
---
# Video Capture Agent — Camera Management & Frame Ingestion Specialist

**Scope:** Multi-source video capture (RTSP, USB webcam, video file), frame acquisition, ring buffer, live reconnect logic, MJPEG streaming.

## Responsibilities

- Open and maintain `cv2.VideoCapture` for active camera
- Drain stale frames from live/RTSP sources to maintain sub-second latency
- Maintain a circular ring buffer of pre-alert frames (150-frame default)
- Post-alert frame collection queue per alert (150 frames after detection)
- Stream latest frame as MJPEG (`/video_feed`) and SSE alerts (`/alerts`)
- Camera switch requests from admin API
- Graceful reconnect for USB/RTSP sources
- FPS throttling to target ~25 FPS output

## Technical Context

**File:** `backend/api.py` — `capture_loop()` function (lines 734–953)

**Source Resolution Order:**

1. **camera_profiles.yml** (preferred) — if exists and has cameras
2. Environment variables: `CAM1_SOURCE`, `CAM2_SOURCE`, `CAM3_SOURCE`
3. Defaults: `"cam1.mp4"`, `"cam2.mp4"`, `"cam3.mp4"` (sample video files)

**Source Types Handled:**

| Type             | Syntax                          | Latency Strategy                    |
|------------------|---------------------------------|-------------------------------------|
| USB webcam       | integer device index: 0, 1, 2   | `CAP_PROP_BUFFERSIZE=1`, set 720p   |
| RTSP IP camera   | `"rtsp://user:pass@ip:port/path"` | FFMPEG zero-buffer flags, drain loop |
| Video file       | `"recording.mp4"`               | Sequential read; loop on EOF        |

**RTSP Low-Latency Flags (set before `VideoCapture`):**
```
OPENCV_FFMPEG_CAPTURE_OPTIONS = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0|analyzeduration;100000|probesize;50000"
```

**Frame Drain (live sources):**
- `_drain_to_latest(cap)` calls `cap.grab()` up to 8 times (no decode), then `cap.retrieve()` gets freshest frame
- Eliminates decoder backlog; keeps latency < 1 second

**Ring Buffer:**
- `deque(maxlen=RING_BUFFER_LEN=150)` — holds ~6 seconds at 25 FPS
- Pre-alert footage used to compile evidence clip + snapshot

**Post-Alert Queue:**
- After alert, spawns `_write_evidence_clip` thread
- Feed post-alert frames via `queue.Queue` for 150 additional frames (~6 sec post-event)
- Evidence MP4 compiled via `cv2.VideoWriter`

**MJPG Stream:**
- `GET /video_feed` → `StreamingResponse` with multipart boundary
- Encodes latest raw frame with `cv2.imencode(".jpg", ..., [QUALITY=80])`
- ~25 FPS target; `time.sleep(max(0, 1/TARGET_FPS - delta))`

**SSE Alerts:**
- `GET /alerts` → queue-based `EventSource` broadcast via `state.broadcast_alert()`
- Each alert JSON: `{ id, timestamp, confidence, type, severity, cameraId, location, fusionScore, faceSummary, ... }`

**Camera Switch:**
- `POST /switch_camera` → `state.request_camera_switch(source, camera_id)`
- Capture loop drains ring buffer, releases old `VideoCapture`, opens new, resets AI pipeline + face engine
- Clears face audit dedupe cache
- Empties GPU cache on CUDA

**Reconnect Logic:**

| Source   | Behavior                     |
|----------|-----------------------------|
| USB      | Retry up to 10×, 2s pause   |
| RTSP     | Retry up to 10×, 2s pause   |
| File     | Seek to frame 0, reset AI   |

**Config Knobs:**
- `RING_BUFFER_LEN = 150` (sec 147 api.py)
- `POST_ALERT_LEN = 150` (sec 148)
- `TARGET_FPS = 25` (sec 146)
- `JPEG_QUALITY = 80` (sec 145)

## Common Pitfalls

- **RTSP stalls**: ensure `OPENCV_FFMPEG_CAPTURE_OPTIONS` set before opening; verify network reachability
- **USB camera index collision**: `ls /dev/video*` (Linux) or check Device Manager (Windows); set `CAMx_SOURCE=1` etc.
- **High latency**: if GPU inference > (1/TARGET_FPS), MJPEG lags; reduce `STRIDE` or use smaller model
- **Out-of-sync video/SSE**: SSE alerts fire on detection; MJPEG shows ~1-3 frames behind due to buffer drain + encode
- **Low disk space**: evidence clips accumulate (`./evidence_clips/`); cleanup old alerts

## Observability

- Console logs: camera open/close, reconnect attempts, frame drops
- `state.running` flag; `state.get_current_camera_id()` for active cam
- Alert queue depth: each SSE client gets its own `queue.Queue(maxsize=128)`

## Example Queries This Agent Answers

- "Camera feed is black/blank — is capture working?"
- "Why is there a 3-second delay in the video?"
- "RTSP reconnects repeatedly — check credentials?"
- "How to add a new camera source?"
- "Evidence clip is missing frames — adjust buffer sizes?"

---
**Created:** 2026-05-12 — Permanent AI Sentinel subagent