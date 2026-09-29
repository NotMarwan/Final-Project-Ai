---
authority: scoped
non_authoritative: true
---

# WT-22 — Tracking, counting, incident capture (S-04) — canonical definitions and handoff

Branch: `codex/sentinel-22-tracking-counting`. Baseline: `e86d34b5`. This document is
scoped evidence for the campaign; it is not a status or design authority.

## 1. Canonical counting semantics (these definitions are normative for the payloads)

Three distinct quantities. They were previously conflated into the single
`person_count = len(tracks)` key.

| field | definition | where computed |
|---|---|---|
| `visiblePersonCount` | person **detections** accepted in the current processed frame (before any tracking filter) | `person_detector._update_tracks` → `counting.observe` |
| `activeTrackCount` | **confirmed** tracks matched in the current processed frame (overlay confirmation gate `min_track_frames`) | `counting.observe` |
| `personCount` | **documented alias of `activeTrackCount`** (legacy consumers unchanged) | inference worker (`len(tracks)`) |
| `uniquePersonEstimateWindow` | distinct confirmed track identities observed in a trailing window, with an explicit period and a ± band | `counting.CountingSemantics` |

`uniquePersonEstimateWindow` fields: `windowSeconds`, `uniqueTrackIds`, `estimate`,
`bandLabel` (`±k`), `bandAbs`, `estimateLower`, `estimateUpper`, `bandIsCalibrated`
(**always false**), `bandSource = tracker_failure_suspicion_events_in_window`,
`windowFlags`, `definition`. The band is derived from the tracker's own geometry-derived
suspicion events inside the same window (id-switch / re-entry / merge-split / dropout) —
it is a suspicion band, never a calibrated confidence interval, and it is labelled so in
every payload.

Counting never claims identity. Track ids are **camera-namespaced**
(`"<cameraId>::<n>"`, SC-7); multi-camera non-association is structural (no cross-camera
comparison exists in the Python producers, and `assertSameTrackNamespace` in
`lib/detection-types.ts` refuses it at the type layer).

## 2. Tracking path (S-04 / F-10)

`backend/person_detector.py` no longer contains its own IoU tracker. Detection backends
(ONNX `person_yolo.onnx`, sha256 `3fafb13e…e60b8`; YOLO fallback) now only produce
boxes+scores; `backend/tracking.py` owns association:

- `ByteTracker` — ByteTrack, arXiv:2110.06864 (MIT). Stage 1: high-score detections vs
  tracked+lost pool; stage 2: low-score detections vs unmatched tracked tracks; new tracks
  from unmatched high-score detections (`new_track_thresh = track_thresh`, per the paper —
  a detection above the tracking threshold can always start a track).
- `OCSortTracker` — compact observation-centric variant, arXiv:2203.14360 (MIT):
  direction/momentum cost + observation-centric recovery after a gap.
- `LegacyIouTracker` — the previous behaviour, kept **only** as the labelled A/B baseline.
- Tracker thresholds are derived from the detector confidence
  (`track_thresh = new_track_thresh = PERSON_OVERLAY_CONF`, `low_thresh = conf/2`),
  so a detection that passed the detector gate can always start/continue a track.
- **No ReID / appearance features anywhere** (policy): the update surface is boxes+scores
  only, asserted by a test that inspects the tracker API signature.
- `PERSON_TRACKER=bytetrack|ocsort` selects the tracker; unknown names raise.

Track-failure taxonomy (heuristic suspicion counters, surfaced as telemetry and never
silently absorbed): `id_switch`, `re_entry`, `merge_split`, `dropout`, `drift`.
Cross-validation on the fixtures: for `iou_legacy` on `missed_person` the counters report
11 `id_switch` while the independent counting metric reports 11 measured switches; on
`occlusion`/`exit_reentry` it reports 1 `re_entry` against 1 measured switch. The counters
are geometry-derived suspicions, not ground-truth labels.

## 3. Frame / crop reference schema (consumed by WT-21 and WT-23)

`backend/frame_reference.py`, wire schemas `sentinel.frame_ref/v1` and
`sentinel.crop_ref/v1`, agreed with WT-21 (faces) and WT-23 (enhancement):

- identity: `frame_id = "<cameraId>:<frameSequence>"`, `crop_id =
  "<cameraId>:<frameSequence>:<subjectKind>[:<faceIndex>]"` (SC-7, monotone per producer);
- time: `captured_at` (SC-6 monotonic capture clock, verbatim), `sample_timestamp`
  (media clock, file sources only, else `null`), `iso_time` (UTC);
- hashing: `frame_sha256`/`source_frame_sha256` are **required** (64-char hex) with
  `hash_format` (`raw-<dtype>-<h>x<w>x<c>` or `png`); placeholders are rejected;
- geometry: `bbox_xyxy`, `bbox_space ∈ {source, model_input}`, plus `bbox_xyxy_source`;
- lineage (SC-8): `is_derivative` (false for camera-observed crops), `derivative_of`;
- tracks: `track_ref` is the camera-namespaced id.

Ring frames are downscaled max-side 640 (model-input space) sampled at a bounded cadence,
with a **sparse native-resolution ring** (`native_fps`, `native_max_frames`) so native
crops remain possible; WT-21's measured finding (YuNet loses faces at 640 on repo
footage) is why the native ring exists. Records always state which pixels were hashed.

## 4. Incident capture queue + best frames

- `backend/best_frame.py` — deterministic defect-axis scorer
  (sharpness = variance of Laplacian; exposure clipping; yaw proxy from landmarks;
  face size px; IED px; occlusion). Weights live in ONE TOML block,
  `config/best_frame.toml` `[best_frame]`, validated to sum to 1.0. Provided
  `ied_px`/`yaw_proxy_deg` from face landmarks are used verbatim and labelled
  `*_source: "provided"`; otherwise the yaw axis is labelled
  `proxy_from_landmarks` with `yaw_is_proxy: true`. Selection is input-order independent
  (total order: total score, sharpness, frame id).
- `backend/capture_queue.py` — `PreEventRing` (T-10 s..T+5 s sweep, cadence-sampled,
  sparse native samples) + `IncidentCapture` (bounded drop-oldest job queue with
  `dropped_jobs`/`dropped_frames` telemetry). `trigger()` is O(1): it snapshots ring
  references and enqueues; **no scoring, crop, face or recording work runs on the alert
  path** (EXP-2203). Alert timestamp resolution is capture-clock first
  (caller value → newest fed timestamp) and the worker measures readiness relatively, so
  no diff mixes clock bases.
- Selection records: `EVIDENCE_DIR/best_frames/<alert_id>.json`, schema
  `sentinel.best_frame_record/v1`, containing the score vector, SC-6 timestamps, SC-8
  parent refs for every candidate frame, emitted `crop_refs`, and the thread that scored.
- Incident-view contract (for WT-25): `IncidentCapture.status()` →
  `{state: "pending"|"idle", pending, ready, failed, dropped_jobs, dropped_frames, ring, last_selection}`;
  alerts also carry `capture: {state, preCandidates, alertId}`.

## 5. F-17 wiring (dead code removed)

`AppState.broadcast_person_data` previously had **no caller** (N-2), so person counts never
reached the UI. It now has a caller: `api._broadcast_person_counts`, invoked from the
detection-metadata hook in `camera_worker`. The broadcast is change-detected and rate
limited (0.25 s per camera) so a 30 fps render loop cannot flood the SSE alert queues, and
it carries the new counting fields. `_build_detection_payload` and the alert payload carry
the same additive fields. **UI display may lag**: the payload fields exist and parse
(`parsePersonDetectionEvent`), but richer UI presentation of the window estimate/band is
not part of this ticket.

## 6. Blueprint delta

| ID | status before → after | evidence |
|---|---|---|
| S-04 tracking/counting | partial → implemented-active (default path now ByteTrack, thresholds derived from detector conf, counting semantics canonical) | EXP-2201, EXP-2202, `tests/test_tracking_counting.py` |
| F-10 person detection/tracking overlay | partial ("ByteTrack path unmeasured") → implemented-active with measured A/B and failure taxonomy | EXP-2201/2202, eval report sha256 `1c5c76d2…7f45ee` |
| F-17 alert SSE + person-count event | implemented-active (**no caller**) → implemented-active with a throttled caller; counts reach the UI | `tests/test_alert_path_capture.py` |
| N-2 ("`broadcast_person_data` has no caller") | open → resolved | same test |

**New surfaces — IDs ratified by the orchestrator (binding reallocation table, applied
doc-side only; no code references IDs):**
- `F-50` — incident capture queue + pre-event ring sweep (WT-22) — **ratified**
- `F-51` — deterministic best-frame selection with TOML weights (WT-22) — **ratified**
- The frame/crop reference schema (`sentinel.frame_ref/v1`, `sentinel.crop_ref/v1`) was
  proposed by WT-22 as `SC-11`, which is **not** in the ratified table: it stays
  unallocated and is handed to the integrator, who assigns all further IDs (F-58+ upward
  per the orchestrator's ruling). WT-22 allocates no further IDs.

## 7. Limitations (honest)

- HOTA/IDF1 numbers are measured **only** on generated labelled sequences. The WT-12
  harness has now landed (`codex/sentinel-12-eval-data`, `a9cb03d`), but its fixture suite
  does not close this gap **structurally, not just temporally**: its labels are
  action/alert-level (KTH aux domain) and its declared gaps include "AP50 unavailable
  without box labels"; HOTA and IDF1 require per-frame **identity** ground truth, which no
  available fixture provides. So real-footage HOTA/IDF1 stays unmeasurable until an
  identity-labelled suite exists (or WT-12 confirms per-person id labels in some planned
  fixture). The harness (`backend/eval_tracking.py`) is ready for the 3-key JSON shape
  `{gt: [[id, x1, y1, x2, y2]], detections: [[x1, y1, x2, y2, score]]}` per frame and can
  additionally read WT-12's `tracks[]` output to compute **no-GT self-consistency**
  diagnostics (id churn, dropout/recovery counts, failure-flag rates) on real footage —
  offered, not built (WT-22 is frozen).
- The `crossing` sequence is not discriminating (both trackers perfect) and is reported as
  such rather than as evidence.
- **RESOURCE-LOCK: the evaluation run is marked CONTENDED** per the orchestrator's binding
  protocol correction (rule 4). WT-22 never acquired the lock — the atomic `mkdir` failed on
  two attempts (holders then: WT-23, WT-19, later WT-21) and this workstream never wrote an
  owner.txt into an existing dir nor removed it. A re-run under clean acquisition is queued
  and requested; the harness is CPU-only, model-free, camera-free and deterministic
  (byte-identical report JSON across two runs, sha256 `1c5c76d2…7f45ee`), so the clean window
  buys the protocol-clean label rather than different numbers.
- Ring frames handed to consumers are 640-max-side (model-input space) unless a sparse
  native sample covers the selected timestamp; native-resolution crops for *every*
  candidate would need an unbounded ring and are not attempted.
- The alert-path timing proof is a method-level microbenchmark (5 calls per arm, 5 ms
  budget), not a full-pipeline measurement.
- `track_failure_flags` are geometry heuristics: they can miss real identity failures that
  leave no geometric trace and can fire on legitimate fast motion (labelled as suspicion
  in every payload).
- No camera device exists; nothing here was validated against live capture, and no face
  data was processed by this workstream.
