---
authority: scoped
non_authoritative: true
---

# WT-10 · Camera configuration and capture / transport / recording / delivery research

- **Worktree** `jobs/sentinel-campaign/wt-10`, branch `codex/sentinel-10-camera-research`, pinned baseline `e86d34b5d16abcc133ad3470c8d135d00b2423d4`.
- **Date** 2026-09-29. **Scope** research only; no runtime code changed. Consumers: the capture-quality workstream (**WT-14**), the transport/streaming workstream (**WT-17**), the recording/evidence workstream (**WT-24**).
- **Evidence labels** used throughout:
  - `[MEASURED]` — executed on this machine on 2026-09-29; command and output included.
  - `[DOCUMENTED]` — from a primary source cited in §12 (URL + document date).
  - `[INFERRED]` — reasoned from code/docs, not executed.
  - `[UNMEASURED]` — cannot be established without hardware absent here (see §9).
- **ID mapping note.** The assignment names "F-13/F-14 transport"; in wt-01 `docs/blueprint/runtime-map.md` (authoritative feature table) **F-13 = display/render + MJPEG encode**, **F-14 = per-camera decision layer**, and the transport surface is **F-19 (MJPEG stream)** + **F-37 (WebRTC transport)**. This document maps onto the runtime-map IDs: **F-03** (camera source resolution), **F-04** (capture thread), **F-05** (downscale + IPC), **F-13** (render/MJPEG encode), **F-19** (MJPEG stream), **F-37** (WebRTC), **F-21/F-22** (evidence clip + ledger), **F-38** (camera health), **SC-6** (timestamp semantics), **SC-8** (evidence layout). Any WT-14/17/24 ticket text that says F-13/F-14 for "transport" should be read against this mapping.
- **Blueprint seed status.** wt-01 `runtime-map.md` / `ownership-map.md` / `runtime-map-verification.md` and wt-02 `design-map.md` / `ui-contract.md` were read before finalizing. The **reconciled seed landed in wt-03 `docs/blueprint/`** (checked 2026-09-29 at commit time): `index.json` (`living-blueprint-index`, `schema_version: 1`, `non_authoritative: true`, baseline `e86d34b…`), plus `runtime-map.md`, `runtime-map-verification.md`, `ownership-map.md`, `design-map.md`, `ui-contract.md`. Its INDEX (`index.json`) was read; its ID namespaces (F-01..F-49, U-01..U-10, SC-1..SC-10, S-01..S-22, B-1..B-10, N-1..N-16, R-1..R-8) **match the mapping used in this document**, and its U-02 (Live Monitor) entry links F-17/F-18/F-19/F-37/F-42/F-43 with the same baseline facts ("WebRTC path disabled/unavailable at baseline (F-37 disconnected); MJPEG fallback retained"). Nothing in the reconciled seed contradicts §0-§12 below.
- **Assignment-text gap.** The WT-14/17/24 assignment texts are not present anywhere under `jobs/sentinel-campaign/**` (searched `WT-14|WT-17|WT-24` in all `*/docs` trees and the jobs root — zero hits). The handoff in §11 is therefore organized by capability area (capture / transport / recording) so any of those tickets can consume it.

---

## 1. The pipeline as it exists today (anchored, verified in source)

Capture → IPC → MJPEG/SSE path at the pinned commit (all anchors verified by reading the code in this worktree; boundary table re-derived from wt-01 runtime-map §1.2):

| Stage | What happens | Anchor |
|---|---|---|
| Source open | RTSP: `OPENCV_FFMPEG_CAPTURE_OPTIONS` (`rtsp_transport;tcp, fflags;nobuffer, flags;low_delay, max_delay;0, analyzeduration;100000, probesize;50000`) + `CAP_PROP_BUFFERSIZE=1`. USB int index: `BUFFERSIZE=1`, **request** 1280×720@30. File: plain open. | `backend/pipeline_capture.py:40-70` (F-03/F-04) |
| Read + timestamp | `read_frame()` then `captured_at = time.monotonic()` — the stamp is **read-complete time**, not sensor time (SC-6). | `backend/api.py:1290-1292` |
| Three per-frame consumers | ① render queue `deque(maxlen=3)` gets `raw.copy()`; ② evidence ring `deque(maxlen=600)` of `(captured_at, downscale(raw,960))`, trimmed to a 5 s monotonic window; ③ IPC `FramePacket(downscale(raw,640), sequence, captured_at, src_w, src_h, src_fps, config, sample_timestamp)` into `mp.Queue(maxsize=3)` (drop-on-full, no counter — runtime-map R-2). | `backend/api.py:1270-1300` (F-05) |
| Inference | Per-camera `mp.Process` (`spawn`) owns SlowFast/X3D + YOLO-ONNX weapon + person; results back via `mp.Queue(maxsize=30)`. | `inference_process.py`, api.py camera_worker (F-06) |
| Render + MJPEG | `RenderThread` pops latest frame (latest-wins), draws server-side overlay (`annotate_fn`), downscales to **854 wide**, `cv2.imencode(".jpg", quality=JPEG_QUALITY)` (`STREAM_QUALITY` 50/75/90), publishes `(sequence, jpeg)` via `state.set_frame`; `_mjpeg_generator` emits `multipart/x-mixed-replace` only for **new** sequences. | `backend/pipeline_render.py:121-184`, `api.py:1492-1498,1553-1558` (F-13/F-19) |
| Detection SSE | `set_detection_meta` snapshot polled at 0.1 s, emitted on change; `updatedAt = time.time()`; `window.clockSource ∈ {file-media, monotonic-capture}`. | `api.py:1594-1643` (F-18, SC-3) |
| Frontend | `<img src="/video_feed?camera_id=…&k=streamKey">` (multipart MJPEG in an `<img>`), optional `WebRTCPlayer` on top, `CanvasOverlay` from detection SSE. | `components/video-player.tsx:164-177` |
| Evidence | On alert: pre-window list copy of ring + post `queue.Queue(maxsize=360)` (deadline trigger + 5 s) → `encode_browser_mp4` (ffmpeg `libx264 veryfast CRF 23 yuv420p high avc1 +faststart`, full decode probe, moov-before-mdat box check) → `{alert_id}.part.mp4` → atomic `Path.replace` → hash-chained ledger. | `api.py:703-822`, `backend/evidence_video.py:287-400` (F-21/F-22, SC-8) |

---

## 2. Capture quality controls

### 2.1 Windows backends: DirectShow vs Media Foundation; AVFoundation caveat

- OpenCV is a two-layer interface over OS capture APIs; **each backend supports device properties differently, or not at all** (quote from OpenCV Video I/O Overview `[DOCUMENTED]`). Windows backends: `CAP_DSHOW` (DirectShow) and `CAP_MSMF` (Media Foundation via videoInput); `CAP_ANY` auto-picks the first available. Cross-platform code must not assume the same property support everywhere.
- **AVFoundation is macOS-only** (`avfoundation` FFmpeg input; Apple-recommended for OS X ≥ 10.7) `[DOCUMENTED]` — any capture abstraction written for AVFoundation property semantics (e.g. `AVCaptureDevice` exposure/focus point-of-interest) has **no** Windows equivalent API; the Windows equivalents are the KS/DirectShow property families in §2.3. Portability caveat: keep a per-backend capability table, don't translate property IDs blindly.
- This machine's OpenCV build `[MEASURED]` (`cv2 4.10.0`, `getBuildInformation()`): **DirectShow: YES, Media Foundation: YES (DXVA: YES), GStreamer: NO**, FFmpeg: YES (prebuilt, libav* 58.x). So both native Windows backends are usable here.
- Practical difference (Windows): MSMF tends to have lower-latency pipelines and handles modern UVC/MJPEG autodecode (§2.2), but historically had format-negotiation quirks in OpenCV; DSHOW gives the most explicit format control via pin media types and is what FFmpeg's `dshow` device mirrors. `[INFERRED from docs + wiki]` Recommendation: pin the backend explicitly (`cv2.VideoCapture(src, cv2.CAP_DSHOW)` or `CAP_MSMF`) instead of `CAP_ANY`, and treat backend choice as camera-profile config. Current code opens live indices with `CAP_ANY` defaults (`pipeline_capture.py:54`).

### 2.2 Format negotiation: MJPEG vs YUY2 vs H.264, and verifying the ACTUAL mode

- UVC cameras usually expose both a raw mode (`yuyv422` = YUV 4:2:2 uncompressed) and a compressed `vcodec=mjpeg` mode; the FFmpeg DirectShow wiki's worked example shows a camera where **720p raw tops out at 7.5 fps while 720p MJPEG reaches 15-30 fps** — compressed modes win at high resolution over USB2 `[DOCUMENTED]`.
- FFmpeg `dshow` negotiates explicitly: `ffmpeg -list_options true -f dshow -i video="Camera"` enumerates every supported `pixel_format`/`vcodec` mode with `min s=WxH fps=f1 max s=WxH fps=f2`; request with `-video_size WxH -framerate N -pixel_format …` or `-vcodec mjpeg`; "If the device does not support the requested options, it will **fail to open**" (dshow device docs) `[DOCUMENTED]`. Footnote: `vcodec=mjpeg` appears in the wiki output and as a pin option; the current ffmpeg-devices dshow options list has no `vcodec` bullet (docs drift) — treat the wiki as the working reference and verify with `-list_options` output on the target device.
- OpenCV side: `CAP_PROP_FRAME_WIDTH/HEIGHT/FPS/FOURCC` `set()` is best-effort per backend; **the only trustworthy verification is reading the properties back after open** and asserting. Current code requests 1280×720@30 then stores `cap.get(...)` values (`pipeline_capture.py:55-70`) but never asserts the result against the request. `[MEASURED]` mode enumeration works without capturing frames: on this machine `ffmpeg -list_devices true -f dshow -i dummy` lists virtual devices `DroidCam Video`, `Marwan204's S23 (Windows Virtual Camera)`, `Camera (NVIDIA Broadcast)`, `OBS Virtual Camera` (filter), and `-list_options true -f dshow -i video="DroidCam Video"` returns real mode rows, e.g. `pixel_format=yuyv422 min s=1280x720 fps=1 max s=1280x720 fps=30`, `…1920x1080… max fps=60.0002`, `…2560x1440…`. **No physical UVC camera exists here** (campaign baseline), so negotiation experiments can run against virtual drivers only (§8 E-1).
- **The OS can hand you a different pixel format than you negotiated**: Windows can opt into "MJPEG at source autodecode" for UVC, where MJPEG media types are *hidden* and replaced with equivalent **NV12 or YUY2** uncompressed types after an OS-inserted decode MFT; this is driver/INF/firmware opt-in and unavailable on older Windows, where MJPEG remains visible `[DOCUMENTED]`. Consequence: **always verify `CAP_PROP_FOURCC`/probe codec after open**; CPU cost and color conversion differ between getting MJPEG (decode cost) and YUY2/NV12 (conversion + larger buffers).
- H.264 at the capture pin (`vcodec=h264`) exists on some IPC/USB devices; on Windows webcams it is rare; for IP cameras H.264 arrives over RTSP anyway (current RTSP path already streams compressed and decodes in FFmpeg inside OpenCV). `[DOCUMENTED/INFERRED]`

### 2.3 Camera controls: exposure, focus, WDR, low-light

| Control family | API surface | Windows mechanism | Availability |
|---|---|---|---|
| Exposure | `CameraControl_Exposure` (log-2 seconds, e.g. −3 = 1/8 s) / `KSPROPERTY_CAMERACONTROL_EXPOSURE` (LONG, log-2 seconds, per-driver range) | DirectShow `IAMCameraControl`, KS `PROPSETID_VIDCAP_CAMERACONTROL` | Optional per driver `[DOCUMENTED]` |
| Focus | `CameraControl_Focus` (mm to optimal target, device range) + extended `…EXTENDED_FOCUSMODE`, focus state `KSCAMERA_EXTENDEDPROP_FOCUSSTATE_*` | `IAMCameraControl` / `KSPROPERTYSETID_ExtendedCameraControl` | Extended controls standardized by Media Foundation `[DOCUMENTED]` |
| Brightness/contrast/white balance | `VideoProcAmp_*` properties | DirectShow `IAMVideoProcAmp` | Common `[DOCUMENTED]` |
| WDR, low-light compensation | **Not in Microsoft's standardized extended-control list** (which covers metadata, focus priority/state, ROI, photo confirmation/mode, EXIF/HW-JPEG, integer ISO, advanced focus, flash, zoom, scene mode) | Vendor/OEM extension KS properties or scene-mode presets | **Device-specific; must be verified per device** `[DOCUMENTED list + INFERRED gap]` |
| Stabilization (closest standardized "quality" control) | `KSPROPERTY_CAMERACONTROL_EXTENDED_VIDEOSTABILIZATION` (OFF/ON/AUTO; rejected while pin runs) | KS extended property | Optional per driver `[DOCUMENTED]` |

- OpenCV can set only the generic `CAP_PROP_*` (brightness/contrast/exposure/focus/…) and support varies per backend; anything beyond that needs COM (`IAMCameraControl`/`IAMVideoProcAmp` via e.g. `pygrabber`) or a vendor SDK. `[DOCUMENTED/INFERRED]`
- Per-frame *read-back* of what the sensor actually applied is available as MF capture metadata (`MF_CAPTURE_METADATA_EXPOSURE_TIME` in 100 ns, `MF_CAPTURE_METADATA_ISO_SPEED`, `MF_CAPTURE_METADATA_SENSORFRAMERATE` = measured sensor readout rate, `MF_CAPTURE_METADATA_WHITEBALANCE`, …) `[DOCUMENTED]` — but only through Media Foundation pipelines, not through OpenCV's `VideoCapture`.
- **Rule for WT-14: never claim exposure/WDR/low-light behaviour without a per-device read-back proof** (§8 E-4). On this machine none of it is verifiable (§9).

### 2.4 fps vs resolution tradeoffs

- USB bandwidth: uncompressed YUY2 1280×720@30 ≈ 55 MB/s (> USB2 effective ~35-40 MB/s) → typical UVC cameras offer 720p30 only in MJPEG; raw 720p collapses to 5-7.5 fps `[DOCUMENTED example + INFERRED arithmetic]`.
- Decode cost at the back end `[MEASURED here]`: one 720p H.264 reader sustains **~474 fps** (≈2.1 ms/frame) of synthetic content on this CPU; MJPEG decode is comparable per frame; YUY2→BGR conversion is cheaper but the 2× frame bytes move through memory.
- Downstream fixed points: inference IPC is always max-side 640 (`temporal_frames.py:53-59`), YOLO-ONNX letterboxes internally; violence window is 32 frames at `source_fps` (window validity ±10 % span) — so **camera fps changes temporal semantics** (`inference.py:517-524`, runtime-map §3.5). 720p30 is the sweet spot this pipeline is tuned for (IPC 640×360 ≈ cheap; ring 960×540).

### 2.5 Dropped-frame detection

Current code has **no drop detection**: `frame_queue_mp.put_nowait` on full → `except queue.Full: pass` (R-2), and the fps counter (`api.py` loop) measures loop throughput, not source delivery. Sources of truth available:

| Source type | Drop signal | Mechanism | Label |
|---|---|---|---|
| RTSP/RTP | sequence-number gaps in RTP (RFC 3550) | proxy/bridge or FFmpeg-level log; OpenCV hides RTP headers | `[DOCUMENTED]` |
| DirectShow/MSMF | frame timestamp gaps; `use_video_device_timestamps`-style device timestamps vs wallclock (ffmpeg dshow option exists exactly for "devices that provide unreliable timestamps") | FFmpeg option; OpenCV has no per-frame device timestamp API | `[DOCUMENTED]` |
| Any | inter-arrival gap histogram on `captured_at`; nominal-vs-measured fps delta; identical-frame detection (cheap hash) | implementable in `camera_worker` today | `[INFERRED]` |

Recommendation (WT-14): add per-camera counters `frames_read`, `frames_dropped_ipc`, `read_gap_p95_ms`, `duplicate_frames` into the existing health surface (F-38 / `/system/status`), closing runtime-map R-2's invisibility.

### 2.6 Timestamp sources and clock domains (SC-6)

| Clock | Source | Where | Domain |
|---|---|---|---|
| `captured_at` | `time.monotonic()` **after `read_frame()` returns** | `api.py:1290` | host monotonic; = read-complete time incl. driver buffering + transport + decode |
| `sample_timestamp` | `source_epoch + file_frame_index/source_fps` **files only**; `None` for live | `api.py:1296`, `temporal_frames.py:22` ("Prerecorded media timeline only; captured_at remains the actual read clock") | synthetic media clock |
| Decision time | `LiveAlertDecisionLayer.update(..., current_time=now)` monotonic | `pipeline_render.py:101-120` | host monotonic |
| `isoTime` | UTC wall at alert | `pipeline_render.py:215-233` | wall clock |
| `updatedAt` | `time.time()` at detection snapshot | `api.py:1594-1622` | wall clock (epoch seconds, 0.1 s granularity from the poll) |
| Media/driver time | MF `MetadataTimeStamps {Device: QPC 100 ns, Presentation: PTS}`; dshow device timestamps (`use_video_device_timestamps`); network cameras may expose NTP (`KSPROPERTYSETID_NetworkCameraControl` NTP property) | driver pipeline | QPC / media PTS / NTP |

Consequences for WT-14/17:

1. `captured_at` **includes read latency** — for USB/RTSP the sensor-to-stamp offset is unknown `[UNMEASURED]`. Document the semantic (SC-6 forbids renaming without three-layer change); optionally add an additive `device_timestamp`/`capture_latency_estimate_ms` field rather than redefining `captured_at`.
2. Two clocks already coexist correctly for files (media clock for windows, monotonic for everything else) — do not collapse them; `window.clockSource` exposes which one is active (`inference_process.py:326-333`).
3. Overlay/frame alignment across transports needs one shared identity: the display frame sequence (`AppState._frame_sequences`) is currently **not exposed** to the client, while the overlay data carries `inferenceSequence`/`updatedAt` (SC-3). See §4.3.

---

## 3. Evidence preservation (the quality ring)

### 3.1 Current design and why it does not slow inference

The pipeline already decouples the three resolutions: inference IPC gets max-side **640** (`INTER_AREA`), the evidence ring max-side **960**, display 854-wide JPEG. Ring writes are a resize + append on the capture thread (cheap) and never block on AI (`pipeline_capture.py` docstring contract, F-04). `[MEASURED]` one 960×540 resize + append is sub-millisecond-scale; the render-side JPEG encode measured at **8.15 ms/frame** (§5 M2) is the largest per-frame software cost in the process and lives on the render thread, not the capture path.

### 3.2 Buffer sizing math

Raw BGR frame bytes = `W × H × 3`. Ring bytes ≈ `min(window_s, maxlen/fps) × fps × W × H × 3`. Post-event queue worst case = `360 × W × H × 3` (size-fixed `queue.Queue(maxsize=360)`, `api.py` on_evidence).

| Ring content | Frame bytes | fps | Window | RAM / camera | Post-queue cap |
|---|---|---|---|---|---|
| 960×540 BGR **(current)** | 1.48 MiB | 30 | 5 s | **222 MiB** | 534 MiB (360 frames) |
| 960×540 BGR | 1.48 MiB | 60 | 5 s | 445 MiB | 534 MiB |
| 1920×1080 BGR | 5.93 MiB | 30 | 5 s | 890 MiB | 2.1 GiB |
| 960×540 NV12 | 0.74 MiB | 30 | 5 s | 111 MiB | 267 MiB |
| 960×540 JPEG q≈90 | ~0.15 MiB | 30 | 5 s | ~22 MiB | ~54 MiB |

An alert clip (5 s pre + 5 s post @30 fps = 300 frames) transiently holds pre-copy + post-queue ≈ **445 MiB** at the current format, on a machine with **~2.6 GB free RAM** (campaign environment note) — two concurrent alerts at 60 fps are a genuine OOM risk. `[MEASURED]` the actual encode of 150 synthetic 960×540 frames took **0.515 s wall (3.44 ms/frame)** and the bounded `encode_browser_mp4` accepts up to **2000 frames** (`evidence_video.py` hard limit), i.e. ≥66 s @30 fps — encoding is not the bottleneck; **RAM is**.

Recommendation (WT-24/WT-14): make the ring content configurable — keep raw BGR 960 as the evidence-quality default, add a JPEG-q90 (or NV12) compressed ring mode as the memory-safe default for multi-camera deployments; decode at clip-assembly time (~2-4 ms/frame `[INFERRED]`, cheap vs 0.5 s encode). If quality policy forbids a lossy ring, cap the ring at 3 s (134 MiB @30 fps) instead of 5 s.

### 3.3 ROI / crop derived views

- Source of record stays the untouched 960 ring frames; ROI/zoom views MUST be derived on copies (`frame[y0:y1, x0:x2].copy()`), never stored back into the ring, and the clip writer MUST keep assembling from ring originals (current behavior — `pre=list(ring_buffer)` shares the frame objects but nothing mutates them `[MEASURED by code-reading]`).
- Note one aliasing subtlety: `downscale_for_inference` returns the *same array* when no scaling is needed (e.g. a 640-wide source) — `temporal_frames.py:53-59`. Harmless today because `cv2.VideoCapture.read()` allocates a fresh array per frame, but any future buffer-reuse optimization must add a `.copy()` there or the ring can be corrupted. Worth a regression test in WT-14 (E-6).
- Store ROI metadata (rect in **source** coordinates + `captured_at` + `inference_sequence`) as *additive* fields (SC-2 additive rule) so crops remain re-derivable from the originals.

---

## 4. Streaming to the browser

### 4.1 Comparison — transport options

| Option | Latency (LAN) | Browser path | Windows/server feasibility | Fit to current code | Evidence |
|---|---|---|---|---|---|
| **MJPEG over HTTP** (`multipart/x-mixed-replace`) | ~100-300 ms practical `[INFERRED]` | `<img src>` — zero JS, works everywhere | Trivial (FastAPI StreamingResponse, exists) | **F-19 is this**; keep as baseline | `[MEASURED]` encode 8.15 ms/frame; `[DOCUMENTED]` go2rtc `mpjpeg` in/out |
| **MSE / fMP4** (fragmented MP4 appended to `SourceBuffer`) | ~0.5-2 s typical (fragment-size bound) `[DOCUMENTED/INFERRED]` | `<video>` + MSE JS; H.264 needs platform decoder (Chrome has it) | go2rtc `mp4` output ships MSE-compatible streams `[DOCUMENTED]`; or FFmpeg `-f mp4 -movflags frag_keyframe+empty_moov` piped | medium work; good for "record-quality" view | `[DOCUMENTED]` W3C MSE; go2rtc README |
| **WebRTC (WHEP)** | ~100-300 ms typical `[INFERRED]` | `<video>` + RTCPeerConnection; no plugins | go2rtc: **Windows 10+ 64-bit zero-dependency binary** (`go2rtc_win64.zip`), WHEP client/server support `[DOCUMENTED]`; aiortc: Python/asyncio, pure-Python (PyAV wheels) `[DOCUMENTED]`; mediasoup: Node SFU, native worker build (meson/VS) — heaviest, Windows possible but build-costly `[DOCUMENTED/INFERRED]` | **F-37 route surface already exists** (WHEP proxy + `/webrtc/offer`), `go2rtc_bridge` missing (SC-10) | `[DOCUMENTED]` go2rtc README; WHEP draft-04 (2026-06-22); WHIP = RFC 9725 |
| **LL-HLS / DASH** | 2-4 s typical; LL variants ~2 s | `<video>` + hls.js (LL-HLS needs newer hls.js/Safari) | FFmpeg `hls`/`segment` muxers `[DOCUMENTED]`; go2rtc `hls` output `[DOCUMENTED]` | low priority — worse latency than MJPEG here; keep only if scrubbing/timeshift is required | RFC 8216 `[DOCUMENTED]`; ISO/IEC 23009-1 `[DOCUMENTED]` |

**Recommendation (WT-17):** keep MJPEG as the always-available baseline; implement the WebRTC path via a **go2rtc sidecar** (matches the existing `go2rtc_bridge` seam and F-37 WHEP proxy routes) rather than aiortc/mediasoup — go2rtc is the only option with a zero-dependency Windows binary and both MJPEG/MSE/WebRTC outputs from one process, so it can later serve the MSE view too. Keep `webrtc.enabled: false` (current `backend/config.yml`) until a measured latency row exists. aiortc remains the fallback for "no external binary" environments (it is already half-wired in `backend/webrtc_streamer.py`).

### 4.2 Latency budgets and freshness semantics

Budget for "operator sees it ≤ 0.5 s after capture" on LAN (MJPEG baseline) `[INFERRED]`: capture+decode ≤ 50 ms, render/JPEG ≤ 15 ms (measured 8.1), network ≤ 20 ms, browser decode/paint ≤ 100 ms, slack for scheduling. **Frame age vs throughput:** `_mjpeg_generator` waits for a strictly newer sequence (`wait_for_frame(after_sequence)`) — freshness is correct (latest-frame-wins, never serves stale), but the wire carries **no frame age**; a stalled camera looks identical to a slow network. Add `frame_age_ms`/`captured_at` (SC-3 additive) to detection metadata and a per-part sequence header for non-`<img>` consumers; the 5 s frontend staleness rule (F-43, `MODALITY_STALE_AFTER_SECONDS = 5.0`) is the current staleness authority.

### 4.3 Overlay / frame alignment

- The streamed JPEG is **annotated server-side** (`annotate_fn` before encode) so boxes drawn by the backend are always frame-accurate `[MEASURED by code-reading]`.
- The client `CanvasOverlay` draws from **detection SSE** (0.1 s poll) over the MJPEG `<img>` — these are two unsynchronized channels with no shared per-frame identity (`AppState._frame_sequences` exists but is never sent). Practical drift = detection poll interval + network jitter (≤ ~150 ms `[INFERRED]`).
- WT-17 fix options (pick one, in preference order): (a) draw all overlay server-side and drop the canvas layer for live view; (b) expose `frameSequence` in the detection payload and match against a per-part `X-Frame-Sequence` MJPEG header (needs a fetch-based MJPEG reader instead of `<img>`); (c) accept drift and render overlay with a timestamp-slop indicator. Option (a) is the only zero-contract-change path (annotate_fn already exists).

### 4.4 Reconnect / backoff / stale-state signaling

| Layer | Current | Gap | Recommendation |
|---|---|---|---|
| Capture (`CaptureThread.reconnect`) | fixed 2.0 s wait, retry forever | no backoff, no jitter, no max-retry escalation | exponential backoff 1→2→4→…→30 s + jitter; escalate `OK→DEGRADED→FAILED` on the existing F-38 health surface |
| MJPEG `<img>` | `onError` → `streamError` state; restart via `streamKey` cache-buster (`video-player.tsx:164-176`) | no auto-retry backoff; silent stall ≠ error | timer-based restart with backoff; heartbeat: if no `onLoad` within 3 s, treat as stale and show the stale banner |
| Detection SSE | `EventSource` auto-reconnect (browser-built-in), 5 s staleness in UI | transport death not surfaced server-side | keep; add stream-state event (`stream: {state: degraded, reason}`) |
| WebRTC (future) | `onError`/`onConnected` hooks exist (`WebRTCPlayer`) | ICE restart policy undefined | WHEP `PATCH` trickle-ICE + ICE restart per draft-04 §4.5 `[DOCUMENTED]` |

---

## 5. Recording / encoding

- **Current flow** (keep): raw BGR frames → pipe → ffmpeg `libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -profile:v high -tag:v avc1 -movflags +faststart` → box-order check (moov < mdat) → full decode probe (`frame=` count must equal input, diagnostics must show `video: h264` + `yuv420p`) → `.part.mp4` → atomic `Path.replace` → SHA-256 + hash-chained ledger (`evidence_video.py:287-400`, `evidence.py`, SC-8). This is a genuinely strong evidence contract — do not weaken it.
- **NVENC feasibility** `[MEASURED]`: the bundled `imageio-ffmpeg` binary (ffmpeg-win-x86_64-**v7.1**) lists `h264_nvenc`, `hevc_nvenc`, `av1_nvenc`, `h264_mf`, `h264_qsv`, `h264_amf` and hwaccels `cuda/d3d11va/d3d12va/dxva2/qsv`; a 150-frame 720p re-encode with `-c:v h264_nvenc -preset p4 -cq 23` succeeded in **0.53 s wall** on the RTX 3060 (driver 591.86). So NVENC is a working option *today* for evidence encoding. Caveats: (a) GeForce NVENC concurrent-session limits have historically existed — verify with a 2-camera parallel encode before relying on it (E-7); (b) the GPU also runs CUDA inference (torch 2.3.0+cu118) — NVENC uses a separate engine, but measure evidence-encode interference (E-7); (c) `_probe_output` is encoder-agnostic so the verification contract survives the switch. Recommendation: `AI_SENTINEL_EVIDENCE_ENCODER=auto|libx264|h264_nvenc` with automatic libx264 fallback on any NVENC failure; keep libx264 the default until E-7 lands.
- **Segmenting** (if continuous recording is added): FFmpeg `segment` muxer or fMP4 fragments, 2-6 s segments, per-segment SHA-256 manifest + atomic `.part` publish per segment (reuse the SC-8 pattern); playback via `<video>` seek (fast-start segments) or MSE. `[DOCUMENTED]`
- **Chrome playback**: the compatibility contract is exactly what the encoder asserts — H.264 High + yuv420p + `avc1` tag + moov-first; baseline evidence: a synthetic 2 s fixture played to completion in Chromium (runtime-map G-08 row). `[DOCUMENTED + prior measured]` New clips must be regression-played in Chrome after any encoder change (E-8).

---

## 6. Multi-camera

- **Decode scaling** `[MEASURED, synthetic 720p H.264, this CPU]`: 1 decoder 474 fps aggregate (2.1 ms/frame); 2 decoders 579 fps aggregate (290 each); 4 decoders 561 fps aggregate (140 each). Per-camera demand at 30 fps is ~6 % of one decoder's throughput; this machine's decode ceiling is roughly **15-18 simultaneous 720p30 H.264 streams** for easy content (synthetic `testsrc2`; real high-bitrate IPC streams cost more `[INFERRED]`). JPEG encode is the tighter budget: 8.15 ms/frame ≈ 3.4 CPU-seconds per camera-minute at 30 fps (≈24 % of one core per camera just for MJPEG).
- **Process isolation**: inference is already one `mp.Process` per camera (F-06, `spawn`) — keep. Capture + render are threads in the API process; a wedged DirectShow driver call blocks the whole process `[INFERRED]`. If multi-camera reliability matters on Windows, move capture into the per-camera process or a small capture helper process (WT-14 decision; measure GIL/driver behavior first — E-9).
- **Prioritization under load**: current policy is implicit (frame-queue drop on full, render latest-wins). Add: per-camera `priority` in `camera_profiles.yml`, drop counters (R-2), and a degradation ladder — MJPEG quality 90→75→50 → ring fps 30→15 → ring max-side 960→640 → pause overlay annotation for low-priority cameras. `[INFERRED design]`

---

## 7. Concrete recommended settings

**Capture profile (USB webcam, Windows) — WT-14**

```yaml
# camera_profiles.yml (proposed shape; additive to existing loader)
cameras:
  CAM-01:
    source: 0                    # or rtsp://…
    backend: dshow               # pin explicitly: dshow | msmf | ffmpeg (RTSP)
    request: { width: 1280, height: 720, fps: 30, fourcc: MJPG }  # fallback YUY2
    verify_mode: true            # read back W/H/FOURCC/FPS; DEGRADED on mismatch
    ring: { max_side: 960, seconds: 5, format: jpeg90 }   # jpeg90 | bgr | nv12
    priority: 1
```

- Request 1280×720@30; **read back and assert** `CAP_PROP_FRAME_WIDTH/HEIGHT/FOURCC/FPS`; mismatch → `DEGRADED` on F-38 health with the actual mode in `reason`.
- Prefer MJPEG pin modes at 720p+ (USB2 reality); accept YUY2 on virtual drivers/USB3.
- Keep `CAP_PROP_BUFFERSIZE=1` (present); wire the unused `_drain_to_latest` (`pipeline_capture.py:100-110`) for RTSP freshness (it exists, has no caller).
- Exposure/focus: leave camera auto unless a device-specific read-back (MF metadata / `IAMCameraControl`) is demonstrated; WDR/low-light: device-specific, verify per device or don't claim.

**Evidence (WT-24)** — keep SC-8 flow; add ring format option (§3.2), keep 5 s pre + 5 s post (post deadline in `api.py` evidence writer), add NVENC opt-in (§5), keep probe + atomic replace + ledger unchanged.

**Streaming (WT-17)** — MJPEG baseline stays (`STREAM_QUALITY=medium` → Q75 at 854-wide is fine for ops display; use `high`/Q90 at 854 for evidence review views); add `frame_age_ms` + `frameSequence` to detection metadata (SC-3 additive); go2rtc sidecar behind the existing `go2rtc_bridge` seam (SC-10: optional import + explicit disabled health state); backoff table from §4.4.

**Timestamps (all)** — document `captured_at` = read-complete monotonic; keep `sample_timestamp` file-only; additive `device_timestamp` only when the backend actually exposes one.

---

## 8. Verification experiments for WT-14 / WT-17 / WT-24 (no physical camera required)

Fixtures: generate with the bundled ffmpeg (`venv/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe`) — **do not use `backend/cam*.mp4`** (untracked user files). Pilots marked `[PILOT]` were executed during this research (§8.0).

### 8.0 Pilots already run (2026-09-29, outputs in §5/§6 and below)

| ID | What | Result |
|---|---|---|
| P-1 | `testsrc2=size=1280x720:rate=30:duration=5` fixture generation | 0.56 s; 1.73 MB `[MEASURED]` |
| P-2 | NVENC re-encode 150 frames 720p | 0.53 s wall, output 2.9 MB `[MEASURED]` |
| P-3 | Real `encode_browser_mp4` on 150 synthetic 960×540 frames | 0.515 s (3.44 ms/frame), probe pass (150/150, h264+yuv420p, faststart) `[MEASURED]` — note: frames were identical (static); motion content not covered |
| P-4 | MJPEG encode 854×478 Q75 | 8.15 ms/frame, ~123 fps capacity `[MEASURED]` |
| P-5 | N parallel 720p H.264 decoders (separate processes) | 1→474 fps, 2→579, 4→561 aggregate `[MEASURED]` |
| P-6 | dshow device/mode enumeration (metadata only, zero frames) | virtual devices present (DroidCam, Windows Virtual Camera, NVIDIA Broadcast, OBS Virtual Camera); DroidCam yuyv422 modes listed up to 2560×1440@60 `[MEASURED]` |

### E-1 Mode negotiation proof (WT-14)

Synthetic webcam: OBS Virtual Camera fed by an OBS scene showing `testsrc2` (or Unity Capture loopback). Steps: `ffmpeg -list_options true -f dshow -i video="OBS Virtual Camera"` → record every `pixel_format`/`vcodec` row; open with OpenCV requesting 1280×720@30 MJPG via `CAP_DSHOW`; read back `CAP_PROP_FOURCC/FRAME_WIDTH/FRAME_HEIGHT/FPS`; repeat via `CAP_MSMF`. **Accept:** read-back equals request or the mismatch is surfaced as `DEGRADED` with actual values. Also `ffmpeg -f dshow -video_size 1280x720 -framerate 30 -vcodec mjpeg -i video=… -t 1 out.mp4` + `ffprobe` of `out.mp4` proves the *actual* negotiated codec (autodecode trap, §2.2).

### E-2 File-clock vs read-clock (WT-14, SC-6)

30 fps fixture with burned-in frame counter (`testsrc2` already varies per frame; or `drawtext` frame number). Run the worker on the file; assert `sample_timestamp` spacing = 1/30 ±10 % and `window.valid` true; then re-run with `AI_SENTINEL_FILE_SKIP=2` and assert window invalidation + counter evidence. **Accept:** window validity flips exactly with the sampling contract; `clockSource=file-media`.

### E-3 Drop detection harness (WT-14)

Feed a 120 fps fixture while artificially slowing the consumer (e.g. `AI_SENTINEL_FILE_SKIP` negative / sleep injection in a test build or a second CPU burner); assert counters (`frames_dropped_ipc`, `read_gap_p95_ms`) move; regression-test that `except queue.Full: pass` paths are counted (closes R-2).

### E-4 Camera-control read-back (WT-14; device-gated)

Against the synthetic webcam: attempt `CAP_PROP_EXPOSURE/FOCUS` set + read-back; `ffmpeg -list_options true` for vendor modes. **Accept:** either a demonstrated read-back or an explicit "unsupported on this device" health note. WDR/low-light cannot be proven without a device that implements them — record as `UNMEASURED` per device.

### E-5 Transport latency (WT-17)

Burn-in a millisecond timer (`drawtext=%{eif\:t*1000\:d}`) in a fixture; serve via (a) MJPEG `/video_feed`, (b) go2rtc MSE/WebRTC; screenshot the browser at ≥30 samples (Playwright/Chrome DevTools MCP) and diff burned-in timer vs `Date.now()`. **Accept:** per-transport median/p95 rows in the report; MJPEG baseline < 300 ms LAN.

### E-6 Ring aliasing regression (WT-14)

640-wide source through `downscale_for_inference(raw, 960)` → assert ring frame is not the same buffer object as the next read's frame after a hypothetical buffer-reuse change; and that ROI crop copies don't mutate ring originals.

### E-7 NVENC concurrency + interference (WT-24)

2 parallel `h264_nvenc` encodes (session limit probe) + simultaneous torch CUDA inference; record encode wall time vs P-3 baseline and inference latency delta. **Accept:** fallback to libx264 triggers when NVENC fails; no >10 % inference slowdown.

### E-8 Chrome playback regression (WT-24)

Play a fresh clip (both encoders) in Chromium to completion; assert duration/frames via `HTMLVideoElement` events. Reuses the G-08 methodology.

### E-9 Capture-thread isolation stress (WT-14)

4 virtual-camera readers (E-1 fixture) + 4 decoders at 720p30 in-process vs separate processes; measure p95 read latency and GIL contention (`py-spy` or timestamps). Informs the §6 isolation decision.

---

## 9. What remains unmeasurable without a physical camera

Explicitly out of scope of every experiment above and **must not be claimed** by WT-14/17/24:

1. **Exposure / WDR / low-light negotiation and effect** — vendor KS extensions and 3A behavior need a real sensor; virtual drivers implement none of it (E-4 can only prove the API returns "unsupported").
2. **True glass-to-alert / glass-to-display latency** — includes sensor readout, 3A settling, USB/ISP pipeline, and driver buffering; `captured_at` is read-complete time (§2.6), so the glass-to-`captured_at` segment is structurally invisible here (runtime-map `glass_to_alert_ms: null`, `unmeasured_reasons.glass_latency`).
3. **Sensor/driver-level dropped frames and timestamp quality** (device QPC availability, `use_video_device_timestamps` behavior on real UVC firmware).
4. **Real-mode fps at native resolution under real USB load** (bandwidth fallbacks, hub contention) and autofocus hunting effects on detection scores.
5. **Low-light noise → model score drift** (calibration artifact absent anyway, F-40: scores stay `calibrationStatus: "unverified"`).
6. **Two-way audio / intercom paths** (go2rtc advertises them; no microphone-in-the-loop test performed).

The virtual-camera experiments (E-1/E-3/E-5/E-9) are valid for *software* claims only.

---

## 10. Candidate list (options worth an engineering decision)

1. **Pin capture backend + negotiated-mode read-back assertion** (dshow/msmf explicit; `DEGRADED` on mismatch) — cheap, closes a silent-failure hole. (WT-14)
2. **JPEG-q90 (or NV12) evidence-ring mode** with raw-BGR default retained — 222 MiB → ~22 MiB per camera; RAM is the real constraint (§3.2). (WT-14/24)
3. **go2rtc sidecar for WebRTC/MSE** through the existing `go2rtc_bridge` seam (SC-10 optional-import decision), `webrtc.enabled` stays false until E-5 lands. (WT-17)
4. **NVENC evidence encoder opt-in** (`AI_SENTINEL_EVIDENCE_ENCODER`) with libx264 fallback — measured working (P-2). (WT-24)
5. **Per-frame identity on the wire** (`frameSequence` + `frame_age_ms`, SC-3 additive) for overlay alignment and freshness. (WT-17)
6. **Drop/throughput counters on the health surface** (R-1/R-2 closure). (WT-14)
7. **Exponential reconnect backoff + stale-state signaling** across capture, `<img>`, SSE. (WT-17)
8. **Virtual-camera test harness** (OBS `testsrc2` scene) as the CI-able stand-in for capture tests. (WT-14)
9. **Segment-based continuous recording** with per-segment hashes + atomic publish (only if timeshift is required; otherwise clips-only is fine). (WT-24)
10. **Wire `_drain_to_latest`** for RTSP latest-frame-wins reads (code exists, unused). (WT-14)
11. **Per-camera priority + degradation ladder** for multi-camera load. (WT-14/17)
12. **Device timestamps (`device_timestamp` additive)** where the backend exposes them. (WT-14, SC-6-respecting)

---

## 11. Engineer handoff

### 11.1 WT-14 (capture quality)

- Change only `backend/pipeline_capture.py`, `backend/api.py` capture loop region, `camera_profiles.yml` shape (S-01/S-09 boundaries — coordinate before touching `api.py`, SC-1).
- Implement §7 capture profile + read-back assertion (Candidate 1); counters (6); `_drain_to_latest` (10); ring format option (2) with the §3.3 copy rules and the aliasing regression (E-6).
- Acceptance: E-1/E-2/E-3/E-6 green on synthetic webcam + fixtures; health surface shows actual negotiated mode; no SC-6 renames (additive fields only).

### 11.2 WT-17 (transport / delivery)

- Change `backend/webrtc_streamer.py`, `components/webrtc-player.tsx`, `components/video-player.tsx` (S-09); detection-payload additions are SC-3 → single commit across `backend/api.py` + `lib/` (ownership-map rule).
- Baseline: keep `/video_feed` MJPEG (`F-19`) untouched in behavior; add freshness/identity fields (5), backoff/stale signaling (7), overlay decision from §4.3 (prefer server-side annotation), then the go2rtc sidecar (3) behind SC-10 semantics.
- Acceptance: E-5 latency rows for MJPEG (and go2rtc paths if the binary is provisioned); reconnect storm test (kill/restart source) leaves no zombie streams; frontend staleness banner fires at 5 s.

### 11.3 WT-24 (recording / evidence)

- Change `backend/evidence_video.py`, evidence writer region of `backend/api.py` (S-07 boundary: `api.py` writes need SC-1 coordination).
- Keep the SC-8 contract byte-identical (`.part.mp4` → atomic replace → ledger hashes → probe). Add encoder option (4) only behind E-7 evidence; segmenting (9) only if timeshift is in scope.
- Acceptance: E-7/E-8 green; every published clip still passes the full decode probe + box-order check; ledger chain verifies on read.

### 11.4 Cross-cutting notes for the orchestrator

- **wt-03 reconciled blueprint seed**: present at finalize time (`docs/blueprint/index.json` read; namespaces/IDs consistent with §0 — no delta required from this research).
- SC-10 (`go2rtc_bridge` missing) is the transport workstream's prerequisite decision.
- This document is `authority: scoped / non_authoritative: true` and must never become status/design authority (DocsSeed SC-9 policy). The checker in this pinned branch predates DocsSeed's `scoped_artifacts` allowlist: `node scripts/docs-contract.mjs --check` exits **1** with `Unregistered active document: docs/campaign/research/10-camera-transport.md` plus the two pre-existing baseline-red lines (`Stale generated document: docs/SOURCE-MANIFEST.json`, `Stale generated document: docs/CURRENT.md`, runtime-map B-6). Exact failure text reported as required; no check rule or registry was modified to force green.

---

## 12. Primary sources (all accessed 2026-09-29)

| # | Source | URL | Doc date |
|---|---|---|---|
| S1 | OpenCV — Video I/O with OpenCV Overview | https://docs.opencv.org/4.x/d0/da7/videoio_overview.html | page generated for OpenCV 4.13.0, 2025-12-31 |
| S2 | FFmpeg — dshow input device (ffmpeg-devices) | https://ffmpeg.org/ffmpeg-devices.html#dshow | current docs (local binary n7.1) |
| S3 | FFmpeg wiki — DirectShow | https://trac.ffmpeg.org/wiki/DirectShow | last modified 2024-07-22 |
| S4 | FFmpeg wiki — Capture/Webcam | https://trac.ffmpeg.org/wiki/Capture/Webcam | last modified 2014-06-03 |
| S5 | Microsoft — CameraControlProperty (strmif.h) | https://learn.microsoft.com/en-us/windows/win32/api/strmif/ne-strmif-cameracontrolproperty | ms.date 2023-04-26 |
| S6 | Microsoft — KSPROPERTY_CAMERACONTROL_EXPOSURE | https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-cameracontrol-exposure | ms.date 2021-10-14 |
| S7 | Microsoft — Extended Camera Controls | https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/standardized-extended-controls- | ms.date 2020-06-19, updated 2025-07-18 |
| S8 | Microsoft — KSPROPERTY_CAMERACONTROL_EXTENDED_VIDEOSTABILIZATION | https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-cameracontrol-extended-videostabilization | ms.date 2018-09-11 |
| S9 | Microsoft — MJPEG At Source Autodecode for UVC | https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/mjpeg-at-source-autodecode-for-uvc | ms.date 2026-01-29, updated 2026-02-04 |
| S10 | Microsoft — Capture Stats Metadata Attributes (MF_CAPTURE_METADATA_*) | https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/mf-capture-metadata | ms.date 2019-08-16, updated 2025-03-25 |
| S11 | go2rtc (AlexxIT) README | https://github.com/AlexxIT/go2rtc | master, fetched 2026-09-29 |
| S12 | IETF — WebRTC-HTTP Egress Protocol (WHEP) | https://datatracker.ietf.org/doc/draft-ietf-wish-whep/ | draft-ietf-wish-whep-04, 2026-06-22 (expires 2026-12-24) |
| S13 | IETF — WHIP (referenced as RFC 9725 within S12) | https://datatracker.ietf.org/doc/rfc9725/ | RFC 9725 |
| S14 | aiortc documentation | https://aiortc.readthedocs.io/en/latest/ | fetched 2026-09-29 |
| S15 | W3C — Media Source Extensions | https://www.w3.org/TR/media-source/ | cited, not re-fetched |
| S16 | W3C — WebRTC Statistics API | https://www.w3.org/TR/webrtc-stats/ | cited, not re-fetched |
| S17 | RFC 8216 — HTTP Live Streaming | https://www.rfc-editor.org/rfc/rfc8216 | cited, not re-fetched |
| S18 | FFmpeg — ffmpeg-formats (mov `+faststart`, `segment`/`hls` muxers) | https://ffmpeg.org/ffmpeg-formats.html | cited, not re-fetched |
| S19 | Repo-internal: wt-01 `docs/blueprint/runtime-map.md` (+verification), wt-02 `docs/blueprint/ui-contract.md` | campaign worktrees | 2026-09-28/29 |
