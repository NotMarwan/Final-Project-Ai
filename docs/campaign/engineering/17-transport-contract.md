---
authority: scoped
non_authoritative: true
---

# WT-17 transport contract (S-09 / F-13 / F-14 / F-37 / SC-3)

Branch `codex/sentinel-17-transport`, worktree `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-17`.
Scoped engineering artifact; docs/CURRENT.md, docs/DESIGN.md and docs/PLAN.md remain the
status/design authorities. Reviewed against the wt-03 blueprint seed (`index.json`, IDs used
exactly as registered).

## 1. Wire contract additions (SC-3 additive, coordinated with WT-13)

`/detections` (one event payload) gains four keys; nothing renamed or removed:

| Key | Type | Semantics |
|---|---|---|
| `frameSequence` | int > 0 \| null | **Display-frame** identity (`AppState._frame_sequences`) of the frame the overlay snapshot was rendered on. Distinct from `inferenceSequence`. Same counter the MJPEG stream serves per part. |
| `frameAgeAtDetectionEmitMs` | number ≥ 0 \| null | Duration (detection-SSE emission stamp − frame `captured_at`) in ms. One clock domain per subtraction (SC-6); never a cross-clock difference. |
| `frameAgeAtDetectionEmitClockBase` | `"monotonic-gettickcount64"` \| `"perf-qpc"` \| null | Clock base of the two stamps above (WT-15 vocabulary). Emission stamp function follows the capture stamp's base. |
| `renderBacklogDroppedCount` | int ≥ 0 \| null | Display frames dropped by the render thread's latest-wins pop at the render step that produced the stamped frame. Not `backlogFrames` (inference queue) and not `frameQueueDropped`. |

Unmeasured ⇒ `null`, never `0` (WT-13's rule). Rename note: the assignment's working name
`frame_age_ms` was renamed to `frameAgeAtDetectionEmitMs` per WT-13 to avoid silent
conflation with WT-15's `frameAgeMs` (inference-start − captured_at) — different boundary.

MJPEG `/video_feed` multipart parts gain headers (ignored by `<img>`, available to
identity-aware readers):

```
--frame
Content-Type: image/jpeg
X-Frame-Sequence: <n>
X-Frame-Age-Ms: <age at publication>          # omitted when no capture stamp
X-Frame-Age-Clock-Base: <base>
```

## 2. Overlay alignment (known defect fixed)

- **Decision overlays are drawn server-side** (`visual_annotator.annotate` → new additive
  kwargs `threat_boxes`, `decision_state`; `RenderThread._render_frame` now runs fusion
  *before* annotation). Threat boxes and the decision badge are burned into the exact frame
  they describe; `frameSequence` identifies that same frame on the wire.
- **The client canvas overlay self-hides unless correlation is proven**:
  `isOverlayFrameCorrelated(payloadFrameSequence, displayFrameSequence)` — equal, positive,
  safe-integer values only. `<img>` MJPEG exposes no display-side identity, so
  `video-player.tsx` passes `displayFrameSequence={null}` and the overlay renders nothing;
  a hidden overlay is never misaligned. Any identity-capable transport must pass the real
  displayed sequence.
- Consequence: the operator still sees tracks/labels/threat boxes — now from the
  frame-accurate server-side annotation instead of an uncorrelated canvas layer.

## 3. Freshness / staleness ladder (preserved, extended)

- Unchanged authority: `telemetryIsStale` / `inferenceIsStale` (5 s) in
  `lib/pipeline-telemetry.ts`; `sourceVisualState` ladder keeps file/replay sources out of
  `live` (file playback is never labelled live).
- New: MJPEG heartbeat watchdog in `video-player.tsx` — a silent stall must not look
  healthy. After a (re)start, no frame within 3 s → stalled (stale banner + backoff
  restart). Once >2 `load` events prove per-frame cadence, a 3 s gap mid-stream is also
  stalled. If a browser fires `load` only once per multipart stream, mid-stream freezes rely
  on `onError` — documented limitation, cadence to be recorded during E-5.
- `frameAgeAtDetectionEmitMs` + `renderBacklogDroppedCount` + WT-13's `frameAgeAtDisplayMs`
  are surfaced by WT-13's telemetry panel (fourth frame-age cell with its clock-base label,
  plus a render-drop cell).

## 4. Reconnect policy (step 3)

`lib/reconnect-backoff.ts` → `reconnectDelayMs(attempt, {baseMs, maxMs, jitterRatio, random})`
= `min(max, base·2^(n−1))` ±30 % jitter, floor `base/2`.

| Layer | Before | Now |
|---|---|---|
| MJPEG `<img>` (`video-player.tsx`) | manual retry button; `onError` → offline | shared backoff + jitter auto-restart (streamKey bump), heartbeat watchdog, attempts reset on every painted frame |
| `/detections` SSE (`use-detection-stream.ts`, WT-17-flagged hunk approved by WT-13) | fixed 2 000 ms | exponential backoff + jitter; guards/cleanup/parse pipeline untouched |
| `/alerts` SSE (`lib/sentinel-store.tsx`; no visible campaign owner — flagged hunk) | fixed 3 000 ms | exponential backoff + jitter; 2 s grace→offline semantics and guards preserved |
| WHEP client (`webrtc-player.tsx`) | linear `1000·n` | exponential backoff + jitter, 3-attempt cap unchanged |

Verification: `backend/tests/test_transport_identity.py::test_reconnect_storm_leaves_no_zombie_streams`
(12 MJPEG + 12 SSE connect/read/close cycles; no suspended async generator for the camera
afterwards; a fresh stream still receives new frames).

## 5. go2rtc sidecar (F-37 recommended path, SC-10 pattern)

`backend/webrtc_streamer.py` → `Go2RTCSidecar` (wired in `api.py` lifespan; health exposed as
`features.go2rtcSidecar` in `/system/status`).

States: `DISABLED` (webrtc.enabled false — the default; or binary absent with a
provisioning hint), `READY` (binary present; optional pinned SHA-256 verified), `RUNNING`
(launched), `ERROR` (hash mismatch or immediate exit). Absent is explicit, never silent.

Provenance recorded in code: upstream `https://github.com/AlexxIT/go2rtc`, artifact
`go2rtc_win64.zip`, license MIT; the binary is never committed (`.gitignore`). `webrtc.enabled`
stays `false` until a measured WebRTC latency row exists (E-5); the MJPEG baseline is always
retained.

## 6. Ownership / hunk flags for the integrator

- SC-3 commit: `backend/api.py` (`AppState.set_frame`/`wait_for_frame`, `_mjpeg_generator`,
  `_build_detection_payload`, capture-loop `render_queue.append`), `backend/pipeline_render.py`
  (`_render_frame`), `backend/visual_annotator.py`, `lib/detection-envelope.ts`.
- Shared hunks (coordinate at merge): `api.py` capture-loop `render_queue.append` (agreed dict
  shape with WT-14/CaptureQuality — `{"frame", "captured_at", "clock_base"}`); `api.py`
  `_build_detection_payload` dict literal alongside WT-13's `pipeline` key (additive);
  `_render_frame` fusion move (disjoint from WT-20's `_emit_alert`); `lib/pipeline-telemetry.ts`
  parser additions are WT-13's (cherry-picked), not mine.
- Sidecar wiring hunks: `api.py` declaration + lifespan + `feature_health()` `go2rtcSidecar` key.
- `lib/sentinel-store.tsx` backoff hunk: no visible owner; flagged for integrator review.
- Optional: WT-20 SC-4 score-semantics fields added additively to the `LiveAlert` interface in
  `components/video-player.tsx`.

## 7. Blueprint delta (proposed, ID-registry exact)

| ID | Proposed status | Delta |
|---|---|---|
| F-13 display/render + MJPEG encode | implemented-active (unchanged) | Source refs add `backend/visual_annotator.py` (decision overlays) and the per-part identity headers in `_mjpeg_generator`; limitation: MJPEG-only delivery measured. |
| F-14 per-camera decision layer | implemented-active (unchanged) | Evidence: decision overlays now frame-accurate (fusion before annotation). |
| F-37 WebRTC transport | disconnected → **partial** | `Go2RTCSidecar` wrapper + explicit `DISABLED` health (SC-10 pattern) wired and tested; WebRTC delivery still disabled/unmeasured (`webrtc.enabled=false` until an E-5 WebRTC row). Limitations: no measured WebRTC latency row; binary not provisioned. |
| S-09 Transport | unverified → **partial** | Owns the identity/freshness contract, correlation gate, backoff policy and sidecar; MJPEG latency row measured in EXP-17 (E-5); WebRTC remains disabled. |
| SC-3 Detection SSE payload | partial (unchanged) | Additive keys `frameSequence`, `frameAgeAtDetectionEmitMs`, `frameAgeAtDetectionEmitClockBase`, `renderBacklogDroppedCount`; coordinated with WT-13; MJPEG part headers added. |
| SC-10 missing-module policy | proposed → **partial** | `go2rtc_bridge` optional import landed (WT-28 cherry-pick) + `go2rtc_sidecar` explicit-health implementation. |

## 8. Limitations and open items

- No camera device: every claim is software-fixture (or file-media) only; glass-to-alert
  stays `null` and is never claimed.
- `<img>` MJPEG exposes no display-side frame identity ⇒ the client canvas overlay is hidden
  by design today (server-side annotation covers it). Identity-aware readers are the intended
  consumers of the new part headers.
- WebRTC: wrapper + health only; no measured WebRTC latency row (E-5 covers MJPEG).
- E-5 measurement is queued behind the campaign RESOURCE-LOCK (slot after WT-24).
