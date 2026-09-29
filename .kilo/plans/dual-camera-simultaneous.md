# Dual-Camera Simultaneous Processing — Implementation Plan

## Problem Statement

**Current:** Single `capture_loop()` processes one active camera at a time. `state._frame_jpg` holds only one MJPEG stream. `/video_feed` serves one camera. Frontend VideoPlayer can switch cameras but cannot display two simultaneously.

**Goal:** Run both CAM-01 and CAM-02 **in parallel** with independent processing, two MJPEG streams on localhost:3000, alerts tagged with `cameraId` to identify source.

---

## Architecture Changes

### Backend — Multi-Capture Engine

**File:** `backend/api.py`

#### 1. State Expansion
```python
class AppState:
    _frames_lock = threading.Lock()
    _frame_jpgs: Dict[str, bytes] = {}   # cameraId → latest JPEG
    
    def set_frame(self, camera_id: str, jpg: bytes):
        with self._frames_lock:
            self._frame_jpgs[camera_id] = jpg
    
    def get_frame(self, camera_id: str) -> Optional[bytes]:
        with self._frames_lock:
            return self._frame_jpgs.get(camera_id)
```

#### 2. Per-Camera Worker
Replace single `capture_loop()` with `create_camera_worker(camera_id: str, source: Union[str,int])`:

```python
def camera_worker(camera_id: str, source: Union[str, int], device: torch.device, 
                  model_weights: str, threshold: float, stride: int):
    # Each worker has:
    # - its own VideoCapture
    # - its own ViolenceInferencePipeline instance (same weights, separate 32-frame buffer)
    # - its own FaceIntelEngine session (or share? see design choice below)
    # - its own ring buffer, post-queues, reconnect state
    # - calls state.set_frame(camera_id, jpg) for MJPEG
    # - alerts include cameraId; broadcast via state.broadcast_alert()
```

**Threading model:**
- Main thread: FastAPI + SSE
- Worker threads: one per camera (daemon)
- Shared objects (thread-safe): `state`, `fusion_engine` (stateless), `telegram_notifier` (thread-safe queue), `evidence_ledger` (file append), `audit_logger` (file append)
- Separate objects: `ViolenceInferencePipeline` per camera (own buffer), `FaceIntelEngine` per camera (session isolation) OR share with lock

#### 3. Startup
```python
def lifespan(app: FastAPI):
    telegram_notifier.start()
    state.running = True
    if CAPTURE_LOOP_ENABLED:
        active_cameras = CAMERA_SOURCES  # or subset from env: ACTIVE_CAMERAS="CAM-01,CAM-02"
        for cam_id, source in active_cameras.items():
            t = threading.Thread(
                target=camera_worker,
                args=(cam_id, source, device, WEIGHTS_PATH, THRESHOLD, STRIDE),
                daemon=True
            )
            t.start()
    yield
    state.running = False
    # threads auto-die as daemon
```

**Design choice — Shared vs Per-Camera Face Engine:**
- **Separate per camera:** `face_engine = FaceIntelEngine(...)` created inside each worker. Pros: no lock contention, independent tracking of unknown IDs across cameras. Cons: duplicate model (GPU memory). Acceptable if face model small.
- **Shared with lock:** One global `face_engine` protected by lock. Pros: single face registry state (known persons tracked across cameras). Cons: lock contention, session mixing (unknown IDs may bleed between cameras in same frame buffer). 
**Recommendation:** Separate face engine per camera *except* known registry is file-based so can be shared; unknown tracking isolated per camera.

#### 4. Video Endpoint Parameterization
```python
@app.get("/video_feed")
async def video_feed(camera_id: str = DEFAULT_CAMERA_ID):
    async def gen():
        while True:
            jpg = state.get_frame(camera_id)
            if jpg:
                yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(1/TARGET_FPS)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")
```
Frontend: `<img src="/video_feed?camera_id=CAM-01" />` and `<img src="/video_feed?camera_id=CAM-02" />`

#### 5. Alert Payload
Already contains `cameraId`. No change needed. However frontend needs per-camera alert filtering.

---

### Frontend — Dual Video Layout

**File:** `app/page.tsx`

#### 1. Two VideoPlayer Components
Replace single `VideoPlayer` with two instances, each bound to a different `activeCamId`:

```tsx
const [activeCamIds, setActiveCamIds] = useState<[CameraId, CameraId]>(["CAM-01", "CAM-02"])

// Left panel: alerts + report (same)
// Main area: split vertically or horizontally?
// Option A (horizontal split): <div className="flex flex-1"><VideoPlayer camId="CAM-01" .../><VideoPlayer camId="CAM-02" .../></div>
```

#### 2. VideoPlayer Props
Extend `VideoPlayer` to accept `cameraId` prop:

```tsx
interface VideoPlayerProps {
  cameraId: CameraId          // NEW — which stream to show
  activeAlert: LiveAlert | null  // only alerts for THIS camera
  privacyMode: boolean
}
```

Filter alerts in parent:
```tsx
const cam1Alerts = alerts.filter(a => a.cameraId === "CAM-01")
const cam2Alerts = alerts.filter(a => a.cameraId === "CAM-02")

<VideoPlayer cameraId="CAM-01" activeAlert={cam1Alerts[0]} ... />
<VideoPlayer cameraId="CAM-02" activeAlert={cam2Alerts[0]} ... />
```

#### 3. Stream URL per Camera
Inside `VideoPlayer`:
```tsx
const streamSrc = isPlaying ? `${API_BASE}/video_feed?camera_id=${cameraId}&k=${streamKey}` : ...
```
Remove camera-switching logic (split-screen shows both always). Keep play/pause.

#### 4. Alert Overlay per Camera
Each player shows violence overlay independently. Pulsing red border when its own `activeAlert` is non-null.

#### 5. AlertFeed Unchanged
Still shows all alerts (both cameras). Selected alert shows details for whichever camera. No change needed.

---

### Configuration

**Config file:** `backend/config.yml` or environment

#### New Option: Active Cameras
```yaml
cameras:
  active: ["CAM-01", "CAM-02"]     # which cameras to run in parallel
  # CAMERA_SOURCES still defines all sources; workers only start for active list
```

Or simpler: start all cameras defined in `CAMERA_SOURCES` (currently 3). To limit to 2, set env:
```bash
ACTIVE_CAMERAS=CAM-01,CAM-02
```

#### GPU Memory
Running two parallel inference pipelines on one GPU:
- X3D-M model size ~ 40MB (parameters) + activations ~ 1–2 GB? Actual: X3D-M ~ 4.7M params, ~19MB FP32. Two copies = ~40MB, negligible.
- Face engine (if using deep face model) may be larger (~100–200MB). Two copies = 200–400MB, still acceptable on 4GB+ GPU.
- Total GPU memory: model weights + frame buffers. Two pipelines double the per-camera buffer (2 × 32 frames). Acceptable.

**Recommendation:** Per-camera pipeline + per-camera face engine is viable on mid-range GPU (GTX 1660+ / RTX 3060+). If memory constrained, share face engine with lock.

---

### API Routing & Management

**New Endpoint:**
- `GET /cameras/status` — list all cameras with `{cameraId, source, running, lastFrameTime, alertCount}`

**Modified Endpoints:**
- `/switch_camera` — **deprecate** (not needed for fixed dual-display)
- `/video_feed?camera_id=` — new param; default to `DEFAULT_CAMERA_ID` for backward compatibility

**State Trackers (add to AppState):**
```python
self._camera_frames: Dict[str, float] = {}   # last frame timestamp per cam
def update_camera_heartbeat(self, camera_id: str):
    self._camera_frames[camera_id] = time.time()
```

---

### Evidence & Alerts

**Evidence clip path:** Already `alert_id` unique; no conflict. Evidence thread already knows `camera_id` from `state.get_current_camera_id()`. Modify to pass `camera_id` to `_write_evidence_clip`:
```python
threading.Thread(target=_write_evidence_clip, args=(alert_id, camera_id, pre_frames, ...))
```
Clip saved as `evidence_clips/{alert_id}.mp4` (no camera subfolder needed; alert_id unique).

**Telegram notification:** Already includes `cameraId` in payload.

**Face audit events:** Already include `cameraId`. Ensure per-camera dedupe cache is separate (already local variable in `camera_worker`, not shared).

---

### Implementation Tasks Per Subagent

#### 1. video-capture-agent
- Refactor `capture_loop()` → `camera_worker(camera_id, source, ...)`
- Set `state.set_frame(camera_id, jpg)` not global setter
- Maintain per-camera ring buffer, post-queues, reconnect logic
- Remove `state.request_camera_switch()` path (not needed for fixed split)

#### 2. inference-agent
- No change to `ViolenceInferencePipeline` class itself
- Ensure each camera instantiates its own pipeline: `ViolenceInferencePipeline(WEIGHTS_PATH, device, threshold, stride)`
- Model weights file shared; multiple copies in GPU memory OK

#### 3. face-intel-agent
- Decision: **per-camera face engine** (simpler). Implement: each worker calls `FaceIntelEngine.from_settings()` at start.
- `state.store_face_summary()` may become per-camera? Design: keep **latest per-camera summary**:
```python
_face_summaries: Dict[str, Dict] = {}
def store_face_summary(self, camera_id: str, summary: dict): ...
def get_face_summary(self, camera_id: str) -> dict: ...
```
Frontend `VideoPlayer` asks for faceSummary of its camera via new endpoint `GET /face/summary?camera_id=...` or embed in alert (`faceSummary` already in alert payload). Since alerts already carry `faceSummary`, per-camera latest not needed separately.

#### 4. api-endpoints-agent
- Add `camera_id` query param to `/video_feed`
- Add `GET /cameras/status`
- Ensure `/alerts` SSE broadcasts from all cameras (already broadcasts all alerts)
- Possibly add `camera_id` field to SSE payload (already present: `alert_payload["cameraId"]`)
- Deprecate `/switch_camera` (or keep for fallback to single-camera mode)

#### 5. frontend-agent
- Split main area: two VideoPlayer components side-by-side (50% width each)
- Pass `cameraId` prop and filter `alerts` array per camera
- Update `VideoPlayer` component: accept `cameraId`, build stream URL with query, remove camera-switching UI (or keep to allow swapping one pane to other camera if desired)
- AlertFeed unchanged
- GeoDashboard: may need to show active camera context; keep as-is (uses selected alert's cameraId)

#### 6. evidence-agent
- No changes needed (evidence per alert already isolated)
- Optionally include cameraId in evidence ledger entry (already present via alert.cameraId)

#### 7. security-audit-agent, notifications-agent, fusion-agent, vlm-agent, audio-agent
- No changes needed (already camera-agnostic via `camera_id`)

---

### Camera Profiles

**File:** `camera_profiles.yml`

```yaml
cameras:
  CAM-01:
    enabled: true
    rtsp:
      high: "rtsp://admin:password@192.168.1.10:554/stream1"
      low:  "rtsp://admin:password@192.168.1.10:554/stream2"
    location: "Entrance"
  CAM-02:
    enabled: true
    source: 1                    # USB webcam index 1
    location: "Lobby"
  CAM-03:
    enabled: false               # keep disabled
    source: "sample3.mp4"
```

`_load_camera_sources()` already returns dict of all cameras. Worker startup will iterate and spawn only those with `enabled: true` (if using that flag) or use env `ACTIVE_CAMERAS`.

---

### Error Handling

- If a camera fails to open, worker logs error and retries with backoff (same as current reconnect logic)
- Global `state.running = False` shuts down all workers
- Evidence clip errors per-camera isolated
- Face engine errors per-camera isolated

---

### Testing Checklist

1. Backend startup logs: `[System] Starting worker for CAM-01: rtsp://...` and same for CAM-02
2. MJPEG streams: `http://localhost:8000/video_feed?camera_id=CAM-01` and `CAM-02` both return multipart images
3. Frontend: both video panes show live feeds
4. Trigger violence on CAM-01: alert appears with `cameraId="CAM-01"`, red border around left pane only
5. Trigger violence on CAM-02: alert appears with `cameraId="CAM-02"`, red border around right pane only
6. AlertFeed shows both alerts interleaved; selecting one updates report panel correctly
7. Evidence clips downloaded for each alert
8. Telegram notification (if enabled) includes correct cameraId

---

### Performance Targets

- Each camera runs at ~25 FPS capture + inference (if GPU can handle two parallel inferences)
- Latency: < 1 second from event to alert (same as single-camera)
- Memory: +200–400MB GPU (two face engines) acceptable
- CPU: two decode threads + two inference threads (ThreadPoolExecutor max_workers=1 per camera? Use one global executor with 2 workers?)

**Executor design:**
Current per-camera worker: uses `concurrent.futures.ThreadPoolExecutor(max_workers=1)` inside each worker → two separate threadpools, each with 1 worker. Acceptable. Or share a global pool with 2 workers; simpler to keep per-camera for isolation.

---

### Future Extensions

- N-camera scalability: refactor workers to asyncio or process pool if >4 cameras
- Camera matrix view (2×2 grid) by adding CAM-03, CAM-04
- Recording all cameras to disk continuously (DVR) with circular buffer per cam
- Cross-camera tracking: link same person/unknown across cameras (shared face registry + ID)

---

## Master Prompt for Kilo

Copy-paste this to Kilo to execute:

```
@video-capture-agent: Refactor capture_loop() into camera_worker(camera_id, source, device, weights, threshold, stride). This worker runs per camera in its own daemon thread. Replace global state._frame_jpg with state._frame_jpgs: Dict[str, bytes]. Call state.set_frame(camera_id, jpg) each iteration. Remove camera switching logic; keep ring buffer, post-alert queuing, reconnect per camera. Keep same inference/face engine init.

@inference-agent: No changes to ViolenceInferencePipeline class needed. Confirm it's re-entrant (no shared module-level state). Each camera will instantiate its own pipeline instance.

@face-intel-agent: Modify FaceIntelEngine if needed to support per-camera sessions without cross-contamination. Prefer creating separate FaceIntelEngine instance per camera worker (same config). Update state to not store single global face_summary; instead include faceSummary inside alert payload (already done). Ensure face audit dedupe cache is per-camera (declare inside worker, not global).

@api-endpoints-agent:
1) Change /video_feed to accept query param camera_id (default DEFAULT_CAMERA_ID). Use state.get_frame(camera_id).
2) In lifespan(), load all cameras from CAMERA_SOURCES (or filter by ACTIVE_CAMERAS env). For each, spawn threading.Thread(target=camera_worker, daemon=True).start().
3) Remove switch_camera endpoint? Keep it but mark as deprecated; it can switch a SINGLE camera in a single-camera fallback mode. For dual-camera mode, ignore.
4) Add GET /cameras/status returning array of {cameraId, source, lastFrameTimestamp iso, alertCount (from state._alerts filtered)}.

@frontend-agent:
1) In app/page.tsx, change layout: main area split into two <VideoPlayer> components side-by-side (flex-1 each).
2) Add state for two camera IDs: const [camA, setCamA] = useState("CAM-01"); const [camB, setCamB] = useState("CAM-02");
3) Compute cam1Alerts = alerts.filter(a => a.cameraId === camA), cam2Alerts = alerts.filter(a => a.cameraId === camB)
4) Pass cameraId prop to each VideoPlayer: <VideoPlayer cameraId={camA} activeAlert={cam1Alerts[0]||null} ... /> and similarly for CAM-02.
5) In VideoPlayer (components/video-player.tsx): accept new prop cameraId: CameraId; build streamSrc = `${API_BASE}/video_feed?camera_id=${cameraId}&k=${streamKey}`. Remove camera-switching UI (the CAMERAS buttons bar) or keep but make it change which camera is shown in that pane only (optional for now).
6) Keep alert overlay logic but compare activeAlert?.cameraId === cameraId to show overlay only for its own alerts.

@evidence-agent: No changes needed. Evidence clips tied to alert_id already camera-specific.

Run uvicorn backend/api.py and confirm dual streams on http://localhost:3000 (Next.js) showing both cameras simultaneously.

---

## Configuration Summary

- `ACTIVE_CAMERAS=CAM-01,CAM-02` (optional; if unset, use all enabled in profiles)
- Each camera gets its own pipeline + face engine
- `/video_feed?camera_id=` parameterized
- Frontend: two panes

---

## Rollout Plan

Phase 1 (Backend only): Implement camera_worker, parameterized /video_feed. Test with curl:
```
curl http://localhost:8000/video_feed?camera_id=CAM-01 > cam1.mjpeg
curl http://localhost:8000/video_feed?camera_id=CAM-02 > cam2.mjpeg
```

Phase 2 (Frontend split): Two VideoPlayer components working.

Phase 3 (Polish): Handle camera failure (one pane shows error, other continues). Add camera health status endpoint.

---

## Risks & Mitigations

| Risk                              | Impact | Mitigation |
|-----------------------------------|--------|------------|
| GPU memory OOM                    | High   | Use smaller model (STRIDE=32 reduces throughput but memory similar), or share face engine |
| Race condition in state updates   | Medium | Ensure per-camera state isolated; only shared broadcast_alert uses lock |
| One camera blocks the other       | Low    | Each worker independent; no cross-wait |
| Evidence clip mixing frames       | Low    | Alert ID global unique; ring buffers per-camera, no mixing |

---

## Done Criteria

- [ ] Backend: two daemon threads, each producing MJPEG for its camera
- [ ] /video_feed?camera_id=CAM-01 and CAM-02 both work
- [ ] Alerts emitted with correct cameraId for each source
- [ ] Frontend: split view shows both feeds simultaneously
- [ ] Alert overlay only flashes on corresponding pane
- [ ] Evidence clips and VLM reports per alert intact