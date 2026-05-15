# Design: Live Monitor 4-Source Switcher

**Date**: 2026-05-13  
**Branch**: hardening/ai-sentinel-real-implementation  
**Approach**: Option A — on-demand demo workers

---

## Summary

Add a 4-source selector to the Live Monitor tab:
- **CAM-01** and **CAM-02** — always-on live sources; analyzed in parallel background workers at startup
- **EXAMPLE-01** and **EXAMPLE-02** — demo clips; analyzed on-demand only when user selects them

Switching the visible source between CAM-01 and CAM-02 only changes what is displayed — background analysis continues for both. Selecting an EXAMPLE clip starts a temporary AI worker for that clip; deselecting it stops the worker.

---

## Architecture

### Backend

**New: `EXAMPLE_SOURCES` dict** (separate from `CAMERA_SOURCES`)
```
EXAMPLE_SOURCES = {
  "EXAMPLE-01": "<project_root>/Wq0BuA8GM84_0.avi",
  "EXAMPLE-02": "<project_root>/YDOJvzChqSg_0 (1).avi",
}
```
Not auto-started. Not in `CAMERA_SOURCES`.

**New: Per-worker stop events in `AppState`**
```
_worker_stop_events: Dict[str, threading.Event]
```
`should_run(cam_id)` returns False when that event is set.
Permanent workers (CAM-01, CAM-02) never have their event set.

**Modified: `camera_worker` signature**
```python
def camera_worker(camera_id, source, device, weights, threshold, stride, stop_event=None)
```
Inner loop: `while state.running and not (stop_event and stop_event.is_set()):`

**New endpoints**
- `POST /demo_start/{clip_id}` — validates clip_id is in EXAMPLE_SOURCES, starts a daemon thread running camera_worker with a new stop_event stored in AppState
- `DELETE /demo_stop/{clip_id}` — sets the stop_event for that clip; no-op if not running

**Startup (lifespan)**
Only starts workers for `CAMERA_SOURCES` (CAM-01, CAM-02) — no change needed if EXAMPLE_SOURCES is separate.

### Frontend

**`app/page.tsx`**
- Add `selectedSource` state, default `"CAM-01"`
- Pass `cameraId={selectedSource as CameraId}` to `VideoPlayer`
- Add source switcher bar above VideoPlayer (inside the `monitor` tab's `<main>`)
- On source change: if switching to EXAMPLE → `POST /demo_start/{id}`; if switching away from EXAMPLE → `DELETE /demo_stop/{id}`
- Use `useEffect` cleanup to stop any running EXAMPLE worker on tab change or unmount

**`components/video-player.tsx`**
- Update `CAMERAS` array:
  ```ts
  { id: "CAM-01",      label: "VIGI C340",   isLive: true,  isDemo: false },
  { id: "CAM-02",      label: "VIGI C340-2", isLive: true,  isDemo: false },
  { id: "EXAMPLE-01",  label: "Fight Clip 1", isLive: false, isDemo: true  },
  { id: "EXAMPLE-02",  label: "Fight Clip 2", isLive: false, isDemo: true  },
  ```
- Update `CameraId` type to include new IDs
- Add LIVE badge (red) for live sources, DEMO badge (amber) for examples
- Status banner: when source is live → show `LIVE`; when demo → show `DEMO`

**Source Switcher UI** (rendered in `page.tsx` inside Live Monitor main area, above VideoPlayer)
- Pill buttons: CAM-01 | CAM-02 | EXAMPLE-01 | EXAMPLE-02
- Active pill: highlighted with primary color
- LIVE badge next to CAM-01 and CAM-02
- DEMO badge next to EXAMPLE-01 and EXAMPLE-02
- Status summary card: "Background analysis: CAM-01 + CAM-02 active | Demo clips: on-demand only"

---

## Data Flow

```
Startup:
  camera_worker(CAM-01) ──┐
  camera_worker(CAM-02) ──┼── state._frame_jpgs[cam_id] ──► /video_feed?camera_id=X
                          └── state.broadcast_alert(payload with cameraId)

User selects EXAMPLE-01:
  POST /demo_start/EXAMPLE-01
  → new daemon thread: camera_worker(EXAMPLE-01, avi_path, stop_event)
  → frames stored in state._frame_jpgs["EXAMPLE-01"]
  → alerts tagged cameraId="EXAMPLE-01" → SSE → main feed

User deselects EXAMPLE-01:
  DELETE /demo_stop/EXAMPLE-01
  → stop_event.set() → worker exits after current frame
```

---

## Files to Edit

| File | Change |
|---|---|
| `backend/api.py` | Add EXAMPLE_SOURCES, per-worker stop events in AppState, modify camera_worker signature, add demo_start/demo_stop endpoints |
| `app/page.tsx` | Add selectedSource state, source switcher UI, demo start/stop API calls |
| `components/video-player.tsx` | Expand CAMERAS array + CameraId type, add LIVE/DEMO badges |

---

## Constraints Honored

- No Telegram config changes
- No SSE changes
- No incident feed changes
- No broad refactoring
- Existing tabs preserved
- ACTIVE_CAMERAS env var still works for permanent workers
- `/switch_camera` deprecated endpoint untouched

---

## Validation Plan

1. `npm run build` — no TypeScript errors
2. Backend starts → CAM-01 and CAM-02 workers running
3. Live Monitor shows 4 source pills
4. CAM-01 ↔ CAM-02 switch changes video display only
5. Selecting EXAMPLE-01 → worker starts → video appears → alerts flow to feed
6. Deselecting EXAMPLE-01 → worker stops → feed stops receiving EXAMPLE alerts
7. All existing tabs work
8. SSE reconnects normally
