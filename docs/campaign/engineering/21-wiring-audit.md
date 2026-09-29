---
authority: scoped
non_authoritative: true
---

# WT-21 wiring audit — person/face detection reachability + SC coordinate mapping

Workstream WT-21 (S-15 Faces) · branch `codex/sentinel-21-face-detect` · baseline `e86d34b5d16abcc133ad3470c8d135d00b2423d4` (+ cherry-picked `b7d1f43` SC-10 optional-import fix, re-landed as `e023b59`) · 2026-09-29.

Scoped campaign artifact. `docs/CURRENT.md` / `docs/DESIGN.md` remain the only status/design authorities. Blueprint IDs referenced: F-10, F-30, S-15, SC-2, SC-6, SC-7, SC-8.

## 1. What person detection exists and is reachable

| Item | Finding (source refs at baseline) | Status |
|---|---|---|
| Person detector | `backend/person_detector.py:20-253` (`PersonDetector`) — ONNX `backend/models/person_yolo.onnx` primary, Ultralytics `yolov8n.pt` fallback. Load asserts class 0 is `person` (`person_detector.py:88`). | reachable (F-10 partial) |
| Runtime caller | `backend/inference_process.py:213-215` constructs it inside the inference worker; `inference_process.py:398-400` submits `person_detector.detect` to a 1-thread `ThreadPoolExecutor` every `person_interval` frames (default 3). | reachable, OFF the alert path |
| Observation output | `inference_process.py` result dict: `tracks` (per-track `id`, `bbox`, `confidence`, `track_id`), `person_count = len(tracks)`. | reachable via observation IPC |
| ByteTrack path | Only in the Ultralytics fallback (`tracker_config="bytetrack.yaml"`); ONNX path uses simple IoU track assignment (`person_detector.py:_assign_track_id`). | unmeasured (as F-10 says) |
| `broadcast_person_data` (F-17) | `api.py:473` exists, has NO caller at baseline — counts reach SSE/detections but not that broadcast. WT-22 owns the counting-semantics fix; not touched here. | disconnected at baseline |

## 2. Face detection/identification wiring

| Item | Finding | Status |
|---|---|---|
| `backend/face_intel.py:39-926` | Identity-recognition engine (`FaceIntelEngine`, known-faces registry, embedding matching). Zero runtime imports; only `backend/tests/test_face_policy_persistence.py` imports it. `bench/runtime.py` force-disables it. | **disconnected — and MUST stay so** (campaign scope: no identity recognition; F-30 remains disconnected) |
| Face DETECTION for incidents | **New in this workstream**: `backend/face_detect.py` (YuNet wrapper) + `backend/face_capture.py` (association + capture + derivative records). | wired (F-56/F-57, see §7) |
| Reachability of new path | `api.py` `camera_worker.on_evidence` (api.py:1426-1462) enqueues an incident capture job; worker thread runs detection; results exposed at `/api/faces/*` (api.py:2329-2368) and as additive alert keys `faceAssoc`/`faceCaptureStatus` via `state.update_alert`. | reachable |

## 3. Exact coordinate transforms (SC mapping) — TESTED

Chain (three spaces; every hop has a single owner and a test):

1. **model input ↔ detector input**: person path uses letterbox `prepare_input` (`yolo_onnx.py:84-101`, `LetterboxTransform(w,h,scale,left,top)`) and un-letterboxes inside `decode_detections` (`yolo_onnx.py:143-145`: `(x - left)/scale`, clipped). Face path: YuNet takes the frame at native size via `cv2.FaceDetectorYN.setInputSize`; the library rescales internally to its fixed `1x3x640x640` input and returns coordinates already in detector-input pixels — no manual letterbox, no inverse map to get wrong.
2. **detector input ↔ ORIGINAL SOURCE pixels**: uniform-ratio mapping `bbox × source/detection-frame` — person: `inference_process._scale_person_tracks` (`inference_process.py:145-165`, clipping + degenerate rejection); face: `face_capture.scale_box_to_source` (same contract). Valid for uniform resize only; crop/letterbox chains are out of contract by documentation.
3. **ORIGINAL SOURCE ↔ displayed frame**: the render/annotated frame is the capture frame (same dims); overlay drawing happens in annotated-frame pixels; the alert payload carries `alertVideoWidth/alertVideoHeight` (pipeline_render.py `_emit_alert`) so clients can scale. Face crops carry BOTH `bbox_xyxy` (frame pixels) and `bbox_xyxy_source` (source pixels) plus a `bbox_space` tag — the displayed coordinate is `bbox_xyxy_source` scaled by the client's source→display factor, identical to what `tracks[].bbox` consumers already do.

Tests covering the mapping (all green, §5):
- `backend/tests/test_face_detect.py::test_scale_box_to_source_uniform_ratio_and_roundtrip` — ratio mapping, source→frame→source round-trip ≤1 px, identity when frame==source, degenerate rejection.
- `test_real_detector_smoke_and_coordinate_mapping_on_fixture` — real YuNet output boxes verified in-frame bounds + round-trip at halved resolution (skips without untracked weights).
- `backend/tests/test_face_capture.py::test_service_capture_persists_crop_frame_and_assoc` — the persisted crop's `crop_ref` records `bbox_space` + both box copies and `frame_sha256 != "N/A"`.

## 4. Alert dispatch path — zero face work

`pipeline_render.py:197` `_emit_alert` → `on_threat_fn` (`api.py:1346`) and `on_evidence_trigger_fn` (`api.py:1426`). The face hook inside `on_evidence` only creates two bounded queues, copies the ring list reference and enqueues one job (`FaceCaptureService.start_capture`, O(1)); detection, encoding and ledger writes run on the dedicated `face-capture` thread. Proven by `test_service_async_dispatch_is_non_blocking` (dispatch calls return <0.2 s while the detector blocks; detector runs only on the `face-capture` thread).

## 5. Health surfaces (never silent)

| Surface | States | Where |
|---|---|---|
| `YuNetFaceDetector.health()` | `loaded` / `absent` (weights missing vs lazy-unloaded distinguished in `reason`) / `failed` (corrupt weights or inference error) / `disabled` | `face_detect.py` |
| `FaceCaptureService.health()` | detector block + `queue_depth` / `processed_jobs` / `dropped_jobs` / `worker_alive` | `face_capture.py` |
| `GET /api/faces/health` | `OK` / `DEGRADED` + explicit `reason` (or `DISABLED` when modules absent — SC-10 style) | `api.py:2333` |
| Capture result | `captured` / `absent` (with reasons: `no_face_detected_in_window`, `no_reportable_face`, `no_frames_in_window`, `face_detector_absent`) / `failed` / `pending` | `face_capture.py:_process_capture` |

## 6. Assets + provenance

| Asset | Source | SHA-256 | License (text fetched and stored) |
|---|---|---|---|
| `assets/yunet/face_detection_yunet_2023mar.onnx` (232,589 B, untracked) | OpenCV Zoo `models/face_detection_yunet/` (raw GitHub, 2026-09-29) | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` (matches WT-08 reference `8f2383e4…52fa4`) | MIT, author Shiqi Yu; `assets/yunet/LICENSE` sha256 `c83b8120c50ccbd4c4f96edf53141bdd566ebb8f8e9227e415326aa1b1aba958` |
| `assets/fixtures/*.jpg` (27 frames, untracked) | frames extracted from `demo_assets/videos/*.avi` (3 clips, 150 frames each) with OpenCV | per-file hashes not stored (regenerable; extraction is deterministic modulo JPEG encode) | repo demo media, file-media source mode — NOT live capture |

Loader search order (`face_detect.resolve_model_path`): explicit arg → `FACE_YUNET_MODEL` env → `backend/models/face_detection_yunet_2023mar.onnx` → `assets/yunet/…`. Weights are never committed.

## 7. New runtime IDs proposed (blueprint delta)

Per the orchestrator's BINDING ID reallocation (three-way collision resolved; registry-only labels, no code references IDs):

- **F-56** Incident face detection + capture (YuNet, off-alert-path, reporting gate, explicit health) — status `implemented-active` at this branch.
- **F-57** Face↔track/incident association with uncertainty (`face_assoc`, ambiguity + per-camera namespacing) — status `implemented-active` at this branch.

(An earlier draft of this document proposed F-50/F-51 for these two; WT-22 allocated F-50/F-51 first and those assignments are kept. F-52..F-55 are WT-23's; further IDs are assigned by the integrator from F-58 upward.)

F-10 status: `partial` → `partial` (no behavior change; ONNX person path untouched — coordinate contract documented + round-trip tests added). F-30 status: `disconnected` → `disconnected` (unchanged BY POLICY). S-15: `disconnected` → `implemented-active` (detection + capture + association only).

## 8. Known gaps recorded at audit time

- `face_intel.py` route surface from the untracked `.runlogs/` snapshot (`/face/policy` etc.) remains absent; not implemented here (recognition stays out of scope).
- Best-frame references in capture results report `unavailable: best_frame_provider_not_configured` until WT-22's `backend/best_frame.py` lands; the provider seam is `FaceCaptureService.best_frame_provider`.
- 1080p native detection costs ~134 ms/frame CPU median (EXP-21-01 clean confirm; contended upper bound was ~155 ms) — capture sampling must stay sparse (`FACE_CAPTURE_SAMPLE_EVERY`, default 3; recommended ≥10 for 1080p CPU deployments).
