# Frontend Overlay Rendering — Implementation Plan

> **For agentic workers (cheaper models):** This is a detailed step-by-step plan. Execute tasks in order. Do NOT skip steps. Test after each task.

**Goal:** Move all visual overlays (bounding boxes, person labels, HUD, threat banner) from the backend to the frontend. The backend sends clean video + JSON metadata. The frontend renders overlays using Canvas 2D and CSS. This makes overlays crisp regardless of input video quality.

**Architecture:**
- Backend: camera_worker emits **clean frames** (no OpenCV drawing) + **detection metadata** via SSE
- Frontend: `<img>` shows clean MJPEG + `<canvas>` draws bounding boxes + React/CSS draws HUD text
- Metadata is tiny JSON (~500 bytes) vs JPEG frames (~30KB) — lower bandwidth too

**Tech Stack:** React 19, TypeScript, HTML5 Canvas 2D, Server-Sent Events (SSE), Tailwind CSS

---

## New Architecture Overview

```
Before (quality tied to input video):
  Camera → OpenCV annotate → JPEG encode → <img src="/video_feed">
  (boxes baked into low-quality JPEG = blurry boxes)

After (overlays separate from video):
  Camera → JPEG encode (clean) → <img src="/video_feed?raw=1">
  AI → JSON metadata ──────→ SSE /detections → Canvas draws boxes
  (clean video + crisp vector overlays)
```

---

## Task 1: Backend — Add `?raw=1` Query Param to Video Feed

**Files:**
- Modify: `backend/api.py`

**What:** When `raw=1` is passed to `/video_feed`, the backend should skip `annotate_frame()` and send clean frames.

**Why:** We need the existing MJPEG endpoint to optionally serve clean frames.

**Current code location:** Lines around 1262-1281 (inside camera_worker while loop)

```python
# Current (annotates every frame):
annotated = annotate_frame(frame=raw, tracks=tracks, ...)
ok, jpg_buf = cv2.imencode(".jpg", annotated, ...)
```

- [ ] **Step 1: Add `raw_mode` flag to camera_worker signature**

In `backend/api.py`, find `def camera_worker(` at line ~1198. Add a `raw_mode` parameter:

```python
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
```

- [ ] **Step 2: Skip annotation when raw_mode=True**

Find the annotation block (around line 1453 in current version). Change:

```python
        # ── Annotate frame with visual overlays ──
        try:
            annotated = annotate_frame(
                frame=raw,
                tracks=tracks,
                person_count=person_count,
                is_threat=is_threat_now,
                threat_confidence=threat_conf,
                camera_id=camera_id,
                fps=_current_fps,
            )
        except Exception as exc:
            print(f"[System] Annotation error: {exc}")
            annotated = raw  # fall back to raw frame
```

To:

```python
        # ── Annotate frame with visual overlays ──
        if raw_mode:
            annotated = raw  # Clean frame — overlays rendered by frontend
        else:
            try:
                annotated = annotate_frame(
                    frame=raw,
                    tracks=tracks,
                    person_count=person_count,
                    is_threat=is_threat_now,
                    threat_confidence=threat_conf,
                    camera_id=camera_id,
                    fps=_current_fps,
                )
            except Exception as exc:
                print(f"[System] Annotation error: {exc}")
                annotated = raw  # fall back to raw frame
```

- [ ] **Step 3: Pass raw_mode when spawning camera_worker**

Find the camera_worker spawn location (around line 1597). Change:

```python
            t = threading.Thread(
                target=camera_worker,
                args=(cam_id, source, device, WEIGHTS_PATH, THRESHOLD, STRIDE),
                daemon=True
            )
```

To:

```python
            _raw_mode = _env_flag("AI_SENTINEL_RAW_STREAM", default=False)
            t = threading.Thread(
                target=camera_worker,
                args=(cam_id, source, device, WEIGHTS_PATH, THRESHOLD, STRIDE),
                kwargs={"raw_mode": _raw_mode},
                daemon=True
            )
```

Also add the same for `demo_start` endpoint (around line 1706):

```python
    t = threading.Thread(
        target=camera_worker,
        args=(clip_id, clip_path, device, WEIGHTS_PATH, state.get_threshold(), STRIDE),
        kwargs={"stop_event": stop_event, "raw_mode": _env_flag("AI_SENTINEL_RAW_STREAM", default=False)},
        daemon=True,
        name=f"demo-worker-{clip_id}",
    )
```

- [ ] **Step 4: Commit**

```bash
git add backend/api.py
git commit -m "feat(backend): add raw_mode to camera_worker for clean video stream"
```

---

## Task 2: Backend — Create Detection Metadata SSE Endpoint

**Files:**
- Create: `backend/detection_sse.py`
- Modify: `backend/api.py`

**What:** Create a new SSE endpoint `/detections` that streams JSON metadata (tracks, person count, threat status) in real-time.

- [ ] **Step 1: Create detection metadata emitter**

Create `backend/detection_sse.py`:

```python
"""SSE endpoint for real-time detection metadata.

The frontend connects to /detections and receives JSON events containing
bounding boxes, person counts, threat status, etc.
"""
from __future__ import annotations

import json
import queue
import time
import asyncio
from typing import AsyncGenerator


def _serialize_tracks(tracks: list) -> list[dict]:
    """Convert track objects to JSON-serializable dicts."""
    out = []
    for t in tracks:
        out.append({
            "id": getattr(t, "label", "?"),
            "bbox": list(getattr(t, "bbox", [0, 0, 0, 0])),
            "confidence": round(float(getattr(t, "confidence", 0.0)), 3),
            "color": getattr(t, "color", [0, 255, 255]),
        })
    return out


def _build_detection_payload(
    camera_id: str,
    tracks: list,
    person_count: int,
    is_threat: bool,
    threat_confidence: float,
    weapon_score: float,
    fps: float,
) -> dict:
    return {
        "cameraId": camera_id,
        "timestamp": time.time(),
        "tracks": _serialize_tracks(tracks),
        "personCount": person_count,
        "isThreat": is_threat,
        "threatConfidence": round(threat_confidence, 1),
        "weaponScore": round(weapon_score, 3),
        "fps": round(fps, 1),
    }


async def _detection_generator(camera_id: str, state_getter) -> AsyncGenerator[str, None]:
    """SSE generator that yields detection metadata every 100ms."""
    q: queue.Queue = queue.Queue(maxsize=4)
    
    # Subscribe to person detection broadcasts
    # We'll poll the state for latest metadata instead of using SSE queue
    # to avoid coupling with the existing alert SSE system
    
    while True:
        try:
            # Get latest metadata from the state's per-camera cache
            # The state stores the latest frame metadata
            metadata = state_getter(camera_id)
            if metadata:
                yield f"data: {json.dumps(metadata)}\n\n"
            await asyncio.sleep(0.1)  # 10 updates per second
        except Exception:
            await asyncio.sleep(0.5)
```

- [ ] **Step 2: Add metadata storage to AppState**

In `backend/api.py`, find the `AppState` class. Add a method to store and retrieve detection metadata per camera:

Find the `class AppState:` definition (around line 300). After the existing `__init__`, add:

```python
        # Per-camera detection metadata (for frontend overlay rendering)
        self._detection_meta: Dict[str, dict] = {}
        self._detection_meta_lock = threading.Lock()
```

Then add methods inside the AppState class (after existing methods, find a good spot around line 600):

```python
    def set_detection_meta(self, camera_id: str, meta: dict):
        with self._detection_meta_lock:
            self._detection_meta[camera_id] = dict(meta)

    def get_detection_meta(self, camera_id: str) -> Optional[dict]:
        with self._detection_meta_lock:
            return dict(self._detection_meta.get(camera_id, {}))
```

- [ ] **Step 3: Emit metadata in camera_worker**

In `backend/api.py`, find the main loop in `camera_worker` where `state.set_frame()` is called (around line 1481). After setting the frame, add:

```python
        # MJPEG streaming: encode the annotated frame
        _enc_t0 = time.perf_counter()
        ok, jpg_buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok:
            _pm.record_encode((time.perf_counter() - _enc_t0) * 1000)
            state.set_frame(camera_id, jpg_buf.tobytes())
        
        # Emit detection metadata for frontend overlay rendering
        state.set_detection_meta(camera_id, {
            "cameraId": camera_id,
            "timestamp": time.time(),
            "tracks": [
                {
                    "id": getattr(t, "label", f"P-{i}"),
                    "bbox": list(getattr(t, "bbox", [0, 0, 0, 0])),
                    "confidence": round(float(getattr(t, "confidence", 0.0)), 3),
                    "color": list(getattr(t, "color", [0, 255, 255])),
                }
                for i, t in enumerate(tracks)
            ],
            "personCount": person_count,
            "isThreat": is_threat_now,
            "threatConfidence": round(threat_conf, 1),
            "weaponScore": round(weapon_score, 3),
            "fps": round(_current_fps, 1),
        })
```

Note: `weapon_score` is available earlier in the loop (around line 1314). If it's not in scope, declare it at the top of the function or read from the overlay cache.

- [ ] **Step 4: Add the SSE endpoint**

In `backend/api.py`, add the endpoint. Find a good spot near the `/alerts` endpoint (around line 1670):

```python
async def _detection_sse_generator(camera_id: str) -> AsyncGenerator[bytes, None]:
    from detection_sse import _build_detection_payload
    while True:
        meta = state.get_detection_meta(camera_id)
        if meta:
            import json
            yield f"data: {json.dumps(meta)}\n\n".encode()
        await asyncio.sleep(0.1)

@app.get("/detections", summary="SSE Detection Metadata Stream")
async def detections(camera_id: str = DEFAULT_CAMERA_ID):
    if camera_id not in CAMERA_SOURCES and camera_id not in EXAMPLE_SOURCES:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} not configured")
    return StreamingResponse(
        _detection_sse_generator(camera_id),
        media_type="text/event-stream",
    )
```

- [ ] **Step 5: Commit**

```bash
git add backend/detection_sse.py backend/api.py
git commit -m "feat(backend): add /detections SSE endpoint for frontend overlay metadata"
```

---

## Task 3: Frontend — Create Canvas Overlay Component

**Files:**
- Create: `components/canvas-overlay.tsx`

**What:** A React component that receives detection metadata and draws bounding boxes, labels, and tracks on a transparent `<canvas>` overlaid on the video.

- [ ] **Step 1: Create the Canvas overlay component**

Create `components/canvas-overlay.tsx`:

```typescript
"use client"

import { useRef, useEffect, useCallback } from "react"

export interface TrackOverlay {
  id: string
  bbox: [number, number, number, number]  // [x1, y1, x2, y2]
  confidence: number
  color: [number, number, number]  // RGB
}

export interface DetectionOverlayData {
  tracks: TrackOverlay[]
  personCount: number
  isThreat: boolean
  threatConfidence: number
  fps: number
}

interface CanvasOverlayProps {
  data: DetectionOverlayData | null
  videoWidth: number
  videoHeight: number
  containerWidth: number
  containerHeight: number
  showBoxes?: boolean
  showLabels?: boolean
}

export function CanvasOverlay({
  data,
  videoWidth,
  videoHeight,
  containerWidth,
  containerHeight,
  showBoxes = true,
  showLabels = true,
}: CanvasOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  // Scale factor to map video coordinates to canvas coordinates
  const scaleX = containerWidth / videoWidth
  const scaleY = containerHeight / videoHeight

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    if (!data || !showBoxes) return

    ctx.lineWidth = 2
    ctx.font = 'bold 13px "Segoe UI", Roboto, sans-serif'
    ctx.textBaseline = "top"

    data.tracks.forEach((track) => {
      const [x1, y1, x2, y2] = track.bbox
      const sx1 = x1 * scaleX
      const sy1 = y1 * scaleY
      const sx2 = x2 * scaleX
      const sy2 = y2 * scaleY
      const w = sx2 - sx1
      const h = sy2 - sy1
      const [r, g, b] = track.color
      const colorStr = `rgb(${r}, ${g}, ${b})`

      // Glow effect for threat
      if (data.isThreat) {
        ctx.shadowColor = "rgba(255, 0, 0, 0.5)"
        ctx.shadowBlur = 15
      } else {
        ctx.shadowColor = "transparent"
        ctx.shadowBlur = 0
      }

      // Box
      ctx.strokeStyle = colorStr
      ctx.strokeRect(sx1, sy1, w, h)

      // Corner brackets (tactical look)
      const bracketLen = Math.min(15, w * 0.15, h * 0.15)
      ctx.beginPath()
      ctx.moveTo(sx1, sy1 + bracketLen); ctx.lineTo(sx1, sy1); ctx.lineTo(sx1 + bracketLen, sy1)
      ctx.moveTo(sx2, sy1 + bracketLen); ctx.lineTo(sx2, sy1); ctx.lineTo(sx2 - bracketLen, sy1)
      ctx.moveTo(sx1, sy2 - bracketLen); ctx.lineTo(sx1, sy2); ctx.lineTo(sx1 + bracketLen, sy2)
      ctx.moveTo(sx2, sy2 - bracketLen); ctx.lineTo(sx2, sy2); ctx.lineTo(sx2 - bracketLen, sy2)
      ctx.stroke()

      ctx.shadowBlur = 0

      // Label badge
      if (showLabels) {
        const labelText = `${track.id} ${(track.confidence * 100).toFixed(0)}%`
        const textMetrics = ctx.measureText(labelText)
        const textW = textMetrics.width + 10
        const textH = 18
        const badgeY = Math.max(0, sy1 - textH - 4)

        // Badge background
        ctx.fillStyle = colorStr
        ctx.fillRect(sx1, badgeY, textW, textH)

        // Badge text
        ctx.fillStyle = "#000"
        ctx.fillText(labelText, sx1 + 5, badgeY + 3)
      }
    })

    // Threat pulsing border (canvas version)
    if (data.isThreat) {
      const pulse = 0.3 + 0.2 * Math.sin(Date.now() / 250)
      ctx.strokeStyle = `rgba(255, 0, 0, ${pulse})`
      ctx.lineWidth = 4
      ctx.strokeRect(2, 2, canvas.width - 4, canvas.height - 4)
    }
  }, [data, scaleX, scaleY, showBoxes, showLabels])

  useEffect(() => {
    draw()
  }, [draw])

  // Also animate on frame
  useEffect(() => {
    let animId: number
    const animate = () => {
      draw()
      animId = requestAnimationFrame(animate)
    }
    animId = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animId)
  }, [draw])

  return (
    <canvas
      ref={canvasRef}
      width={containerWidth}
      height={containerHeight}
      className="absolute inset-0 z-10 pointer-events-none"
      style={{ imageRendering: "crisp-edges" }}
    />
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add components/canvas-overlay.tsx
git commit -m "feat(frontend): create CanvasOverlay component for crisp bounding boxes"
```

---

## Task 4: Frontend — Create SSE Hook for Detection Metadata

**Files:**
- Create: `hooks/use-detection-stream.ts`

**What:** A React hook that connects to the `/detections` SSE endpoint and provides real-time detection metadata.

- [ ] **Step 1: Create the hook**

Create `hooks/use-detection-stream.ts`:

```typescript
"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import type { DetectionOverlayData } from "@/components/canvas-overlay"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

export function useDetectionStream(cameraId: string) {
  const [data, setData] = useState<DetectionOverlayData | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const url = `${API_BASE}/detections?camera_id=${encodeURIComponent(cameraId)}`
    const es = new EventSource(url)
    eventSourceRef.current = es

    es.onopen = () => {
      setConnected(true)
      setError(null)
    }

    es.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data)
        const mapped: DetectionOverlayData = {
          tracks: (parsed.tracks || []).map((t: any) => ({
            id: t.id ?? "?",
            bbox: t.bbox ?? [0, 0, 0, 0],
            confidence: t.confidence ?? 0,
            color: t.color ?? [0, 255, 255],
          })),
          personCount: parsed.personCount ?? 0,
          isThreat: parsed.isThreat ?? false,
          threatConfidence: parsed.threatConfidence ?? 0,
          fps: parsed.fps ?? 0,
        }
        setData(mapped)
      } catch (err) {
        console.warn("[DetectionStream] Failed to parse SSE data:", err)
      }
    }

    es.onerror = () => {
      setConnected(false)
      setError("Connection lost")
      es.close()
      // Auto-reconnect after 2 seconds
      reconnectTimerRef.current = setTimeout(() => {
        connect()
      }, 2000)
    }
  }, [cameraId])

  useEffect(() => {
    connect()
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
    }
  }, [connect])

  return { data, connected, error }
}
```

- [ ] **Step 2: Commit**

```bash
git add hooks/use-detection-stream.ts
git commit -m "feat(frontend): add useDetectionStream hook for SSE metadata"
```

---

## Task 5: Frontend — Integrate Canvas + Clean Stream into VideoPlayer

**Files:**
- Modify: `components/video-player.tsx`

**What:** Modify the existing VideoPlayer to:
1. Use the clean MJPEG stream (with `?raw=1` if env flag is set)
2. Overlay the Canvas component for bounding boxes
3. Use React/CSS for HUD (person count, FPS, camera ID, threat banner) — already partially done

- [ ] **Step 1: Import new components and hook**

At the top of `components/video-player.tsx`, add:

```typescript
import { CanvasOverlay } from "@/components/canvas-overlay"
import { useDetectionStream } from "@/hooks/use-detection-stream"
```

- [ ] **Step 2: Use the detection stream hook**

Inside the `VideoPlayer` component (after state declarations, around line 101), add:

```typescript
  const { data: detectionData } = useDetectionStream(propCameraId)
  const [showOverlays, setShowOverlays] = useState(true)
  const videoContainerRef = useRef<HTMLDivElement>(null)
  const [containerSize, setContainerSize] = useState({ width: 1280, height: 720 })
```

- [ ] **Step 3: Measure container size for canvas scaling**

Add a resize observer to measure the video container:

```typescript
  useEffect(() => {
    const el = videoContainerRef.current
    if (!el) return
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setContainerSize({ width, height })
      }
    })
    resizeObserver.observe(el)
    return () => resizeObserver.disconnect()
  }, [])
```

- [ ] **Step 4: Modify video stream URL to use raw mode**

Change the streamSrc to include `raw=1` when in overlay mode:

```typescript
  // Use raw stream when overlays are rendered by frontend
  const _rawMode = true  // Or read from env: process.env.NEXT_PUBLIC_RAW_STREAM === "true"
  const streamSrc = isPlaying
    ? `${API_BASE}/video_feed?camera_id=${propCameraId}${_rawMode ? "&raw=1" : ""}&k=${streamKey}`
    : undefined
  const demoMjpegSrc = isDemo && !demoLoading
    ? `${API_BASE}/video_feed?camera_id=${propCameraId}${_rawMode ? "&raw=1" : ""}&k=${streamKey}`
    : undefined
```

Wait — we didn't add `?raw=1` query param handling to the backend `/video_feed` endpoint. We added `raw_mode` as an env var to the worker. For simplicity, we can either:

A. Make `raw_mode` the default (set `AI_SENTINEL_RAW_STREAM=true` in env)
B. Add query param parsing to the endpoint

For this plan, let me use approach A — make raw mode the default by adding to `.env`:

```
AI_SENTINEL_RAW_STREAM=true
```

This way the existing `/video_feed` endpoint serves clean frames by default.

Actually, looking at the code again, `raw_mode` is passed to `camera_worker` via kwargs. The env var `AI_SENTINEL_RAW_STREAM` controls it. So if we set that env var, ALL camera workers run in raw mode.

For the plan, let's say: Set `AI_SENTINEL_RAW_STREAM=true` in `backend/.env` to enable clean streams globally.

- [ ] **Step 5: Add Canvas overlay to the video container**

Find the video container div (around line 244):

```jsx
      <div className={cn("relative flex-1 overflow-hidden bg-black transition-all duration-500", showViolence ? "animate-shake" : "")}>
```

Inside this div, after the `<img>` or video element, add the CanvasOverlay:

```jsx
        {/* Bounding boxes rendered by frontend Canvas */}
        <CanvasOverlay
          data={detectionData}
          videoWidth={1280}
          videoHeight={720}
          containerWidth={containerSize.width}
          containerHeight={containerSize.height}
          showBoxes={showOverlays}
          showLabels={showOverlays}
        />
```

Note: `videoWidth` and `videoHeight` should ideally come from the actual video source. For now, use 1280x720 as default. A future improvement would be to read actual dimensions from the video element.

- [ ] **Step 6: Add overlay toggle button to controls**

In the controls bar (around line 408), add a toggle:

```jsx
      <div className="flex items-center justify-between border-t border-border bg-card px-4 py-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setIsPlaying((p) => !p)}>
            {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </Button>
          <Button
            variant={showOverlays ? "default" : "outline"}
            size="sm"
            className="h-7 text-xs"
            onClick={() => setShowOverlays((v) => !v)}
          >
            {showOverlays ? "Boxes On" : "Boxes Off"}
          </Button>
        </div>
        {/* ... rest of controls ... */}
      </div>
```

- [ ] **Step 7: Use detectionData for person count in HUD**

In the status banner, replace the prop-based `personCount` with the streamed one:

Find this code (around line 225):
```jsx
              {(personCount ?? 0) > 0 && (
                <span className="flex items-center gap-1 text-cyan-400 font-semibold">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  PERSONS: {personCount}
                </span>
              )}
```

Change to:
```jsx
              {(detectionData?.personCount ?? 0) > 0 && (
                <span className="flex items-center gap-1 text-cyan-400 font-semibold">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  PERSONS: {detectionData.personCount}
                </span>
              )}
```

- [ ] **Step 8: Commit**

```bash
git add components/video-player.tsx hooks/use-detection-stream.ts components/canvas-overlay.tsx
git commit -m "feat(frontend): integrate Canvas overlay and clean video stream"
```

---

## Task 6: Frontend — Add CSS HUD Overlay (Person Count, FPS, Camera ID)

**Files:**
- Modify: `components/video-player.tsx`

**What:** Add React/CSS-based HUD elements that were previously baked into the video frames. These are now rendered by the browser as crisp HTML/CSS.

- [ ] **Step 1: Add HUD overlay elements inside the video container**

Inside the video container div, add these HUD elements (after the CanvasOverlay):

```jsx
        {/* ── CSS HUD Overlays (crisp, not baked into video) ── */}
        
        {/* Top-left: Person count + FPS */}
        <div className="pointer-events-none absolute top-3 left-3 z-20 flex flex-col gap-1">
          <div className="flex items-center gap-2 backdrop-blur-sm bg-black/50 rounded px-2 py-1">
            <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
            <span className="font-mono text-xs text-cyan-400 font-bold">
              PERSONS: {detectionData?.personCount ?? 0}
            </span>
          </div>
          <div className="font-mono text-[10px] text-white/50 backdrop-blur-sm bg-black/30 rounded px-2 py-0.5">
            {detectionData?.fps?.toFixed(0) ?? "--"} FPS
          </div>
        </div>

        {/* Bottom-left: Camera ID + Timestamp */}
        <div className="pointer-events-none absolute bottom-12 left-3 z-20 flex items-center gap-2">
          <span className="font-mono text-[10px] text-primary/80 backdrop-blur-sm bg-black/50 rounded px-1.5 py-0.5">
            {propCameraId}
          </span>
          <span className="font-mono text-[10px] text-white/40">
            {new Date().toLocaleTimeString()}
          </span>
        </div>

        {/* Bottom-right: Status badge */}
        <div className="pointer-events-none absolute bottom-12 right-3 z-20">
          {detectionData?.isThreat ? (
            <div className="backdrop-blur-sm bg-black/70 rounded border border-danger/50 px-3 py-1.5 animate-pulse">
              <span className="font-mono text-xs font-bold text-danger">
                THREAT {detectionData.threatConfidence.toFixed(0)}%
              </span>
            </div>
          ) : (
            <div className="backdrop-blur-sm bg-black/30 rounded px-2 py-1">
              <span className="font-mono text-[10px] text-success font-semibold">● NORMAL</span>
            </div>
          )}
        </div>
```

These replace the existing HUD elements that were baked into frames by `visual_annotator.py`. The existing CSS-based elements (threat banner, scan lines, REC indicator, corners) can stay since they're already frontend-rendered.

- [ ] **Step 2: Commit**

```bash
git add components/video-player.tsx
git commit -m "feat(frontend): add CSS HUD overlays (person count, FPS, camera ID, status)"
```

---

## Task 7: Environment Setup — Enable Raw Stream Mode

**Files:**
- Modify: `backend/.env.example` (or create instructions)

**What:** Document how to enable the new frontend overlay mode.

- [ ] **Step 1: Add env var to .env.example**

In `backend/.env.example`, add:

```bash
# Frontend overlay rendering mode
# When true: backend sends clean video, frontend renders overlays
# When false: backend bakes overlays into video (legacy mode)
AI_SENTINEL_RAW_STREAM=true
```

- [ ] **Step 2: Add frontend env var**

If there's a frontend env file (`.env.local` or similar), add:

```bash
# Use clean video stream with frontend-rendered overlays
NEXT_PUBLIC_RAW_STREAM=true
```

- [ ] **Step 3: Commit**

```bash
git add backend/.env.example
git commit -m "docs: add AI_SENTINEL_RAW_STREAM env var documentation"
```

---

## Task 8: Testing — Verify End-to-End

**Files:**
- None (testing only)

**What:** Test the complete flow to ensure it works.

- [ ] **Step 1: Start backend with raw mode**

```bash
cd backend
export AI_SENTINEL_RAW_STREAM=true
export STREAM_QUALITY=high
python api.py
```

- [ ] **Step 2: Start frontend**

```bash
npm run dev
```

- [ ] **Step 3: Open browser and inspect**

1. Open `http://localhost:3000`
2. Select a camera feed
3. Open browser DevTools → Network tab
4. Verify:
   - `/video_feed` returns clean frames (no boxes baked in)
   - `/detections` SSE connection is active
   - SSE messages contain JSON with `tracks`, `personCount`, etc.
5. Open DevTools → Elements tab
6. Verify:
   - `<img>` shows clean video
   - `<canvas>` is overlaid on top
   - CSS HUD elements are visible
   - Bounding boxes drawn on canvas match persons in video

- [ ] **Step 4: Toggle overlay button**

Click the "Boxes On/Off" button and verify:
- Boxes disappear when toggled off
- Boxes reappear when toggled on
- Video stays clean throughout

- [ ] **Step 5: Check quality comparison**

Compare the new mode with legacy mode:

```bash
# Legacy mode (backend draws overlays)
export AI_SENTINEL_RAW_STREAM=false
python backend/api.py
```

Verify that:
- Legacy mode: boxes are baked into JPEG, look blocky
- New mode: boxes are Canvas-rendered, look crisp
- New mode: video quality is better (no double JPEG compression)

- [ ] **Step 6: Commit test results**

```bash
# If all tests pass
git commit -m "test: verify frontend overlay rendering end-to-end"
```

---

## Task 9: Cleanup — Optional Legacy Mode Removal

**Files:**
- Modify: `backend/api.py`
- Modify: `backend/visual_annotator.py`

**What:** Once frontend overlay mode is confirmed working, you can optionally remove the legacy backend annotation path entirely. This simplifies the code and removes the slow OpenCV drawing path.

**Note:** This is OPTIONAL. Do this only after the frontend mode has been running stable for a while.

- [ ] **Step 1: Remove raw_mode conditional, always use clean frames**

In `camera_worker`, remove the `raw_mode` parameter and always skip annotation:

```python
        # Encode clean frame (overlays rendered by frontend)
        annotated = raw
```

- [ ] **Step 2: Remove annotate_frame import and usage**

In `backend/api.py`, remove the `annotate_frame` import if it's no longer used anywhere else.

- [ ] **Step 3: Commit (when ready)**

```bash
git add backend/api.py
git commit -m "refactor(backend): remove legacy backend overlay rendering"
```

---

## Summary of Changes

| Task | File(s) | What |
|------|---------|------|
| 1 | `backend/api.py` | Add `raw_mode` to camera_worker |
| 2 | `backend/detection_sse.py`, `backend/api.py` | Create `/detections` SSE endpoint |
| 3 | `components/canvas-overlay.tsx` | Canvas component for bounding boxes |
| 4 | `hooks/use-detection-stream.ts` | SSE hook for metadata |
| 5 | `components/video-player.tsx` | Integrate canvas + clean stream |
| 6 | `components/video-player.tsx` | CSS HUD overlays |
| 7 | `backend/.env.example` | Env var documentation |
| 8 | — | Testing steps |
| 9 | `backend/api.py` | (Optional) Remove legacy path |

## Key Benefits After Implementation

1. **Crisp overlays**: Canvas 2D + CSS text is vector-sharp, not JPEG-blocky
2. **Better video quality**: No double compression (video → annotate → re-encode)
3. **Toggleable overlays**: Users can show/hide boxes without restarting stream
4. **Lower backend CPU**: No OpenCV drawing, no alpha blending
5. **Lower bandwidth**: Metadata is ~500 bytes vs annotated JPEG ~30KB
6. **Input quality independence**: Bad input video ≠ bad overlays

## Troubleshooting for Cheaper Model

| Problem | Solution |
|---------|----------|
| Canvas not drawing | Check `detectionData` is not null. Check `containerSize` is not 0. |
| Boxes in wrong position | Check `scaleX` and `scaleY` calculations. Video dimensions may differ from container. |
| SSE not connecting | Verify `/detections` endpoint exists. Check CORS headers. |
| Boxes flicker | `requestAnimationFrame` loop should be smooth. Check `data` updates are not causing re-renders. |
| No person count | Check `state.set_detection_meta()` is called in `camera_worker`. |
