---
authority: scoped
non_authoritative: true
---

# WT-13 / S-08 — telemetry audit and instrumentation contract

Workstream: WT-13 (Measurement & telemetry). Slice: S-08 (`backend/metrics.py`,
`lib/pipeline-telemetry.ts`, `components/pipeline-telemetry.tsx`,
`hooks/use-detection-stream.ts`, `tests/pipeline-telemetry.test.mjs`,
`tests/visual-state.test.mjs`, `tests/detection-envelope.test.mjs`).
Pinned baseline: `e86d34b5d16abcc133ad3470c8d135d00b2423d4` (`final-demo-transfer`).
This document is a scoped campaign artifact; `docs/CURRENT.md` / `docs/DESIGN.md` /
`docs/SOURCE-MANIFEST.json` remain the only status/design authorities.

## 1. What existed at baseline

| Surface | Baseline state | Evidence |
|---|---|---|
| `GET /system/status` | Combined health: model thresholds, decision layer, Telegram, fusion, weapon, security, audit, audio, storage. No telemetry, no queue/drop counters, no per-subsystem telemetry health. | `backend/api.py:2186-2216` (baseline numbering) |
| `GET /system/metrics` | Called `pipeline_metrics.summary()` and returned six averages. The singleton was **never written** by any runtime path, so every field was always `0.0`/`0.0`/`0`; wrapped in `except Exception: return {"error": str(exc)}`. Inert (runtime-map N-3, R-7). | `backend/api.py:2218-2230`; `backend/metrics.py:1-49`; runtime-map §1.6 ("read-only consumer; **never written**") |
| `GET /detections` (SSE) | `cameraId`, `sourceKind`, `updatedAt`, `inferenceSequence`, modality sequences/scores, `tracks`, `personCount`, `isThreat`, `threatConfidence`, `fps`, `videoWidth/Height`, `multiThreat`, `health{capture,violence,weapon,person,decision,render}`, `latencyMs`, `window{...}`, `decision{...}`, `calibrationStatus`. `latencyMs` = `processing_latency_ms` = capture→**result build** inside the worker, i.e. processing latency, never glass-to-alert. | `backend/api.py:1594-1622` (baseline); `backend/inference_process.py:442` |
| Frontend freshness | `telemetryIsStale` / `inferenceIsStale` (>5 s), per-modality freshness with independent completion IDs, trace-restart reset on sequence regression, 60 s / 120-point trace window. | `lib/pipeline-telemetry.ts:114-186` (baseline) |
| Queue health | Frame queue full → `except queue.Full: pass` (`api.py:1351`) and alert broadcast full → silent drop (`api.py:465-495`): no counter anywhere (R-1/R-2). | runtime-map §6.1 R-1, R-2 |
| Timestamp semantics | `captured_at = time.monotonic()`; `sample_timestamp` = media clock for files only; `isoTime` = UTC wall clock; `window.clockSource ∈ {file-media, monotonic-capture}`. No explicit clock-domain labelling of latency fields. | runtime-map §3.5, §1.2 D-4/D-5 |

## 2. Stage timings at baseline: captured vs missing

| Stage | Baseline | Now produced by |
|---|---|---|
| source → capture (frame read/decode) | not measured | WT-14 `stageFrameReadMs` (capture-monotonic) |
| capture → downscale/IPC queue put | not measured | WT-15 `stageCaptureToQueueMs` (capture-monotonic) |
| queue wait + pickle transfer (enqueue→dequeue) | not measured | WT-15 `stageEnqueueToDequeueMs` (honest composition; queue maxsize 3 dominates) |
| worker preprocess | not measured | WT-15 `stagePreprocessMs` |
| inference wait (submit → completed read) | not measured | WT-15 `stageInferenceWaitMs` |
| inference compute (completed) | only a blended `processing_latency_ms` | WT-16 `stageInferenceComputeMs` + `inferenceComputeSynced` |
| capture → result build (processing latency) | measured (worker monotonic) | unchanged `processing_latency_ms`, relabelled in the export as processing latency ≠ glass-to-alert |
| capture → publication age | not measured | derived at ingest from `capturedAtMonoMs`/`capture_timestamp` (see §3) |
| publication → display age | not measured and not measurable server-side | browser wall-epoch difference, explicitly labelled cross-clock |
| decision confirmation | `alertLatencyMs: null` in the live alert path | WT-20 (`decisionConfirmLatencyMs`), plus observed `alert_state` transitions recorded here |
| cold start (spawn→load→first inference) | unmeasured (G-13) | WT-15 `startupModelLoadMs`/`startupFirstResultMs`, WT-16 `stageModelLoadMs`/`stageFirstInferenceMs`/`inferenceColdStartMs` |

## 3. Instrumentation contract (additive, SC-2/SC-3/SC-6/SC-7)

Producer → surface names are frozen with WT-14/WT-15/WT-16; the ingest accepts both
canonical camelCase and snake_case aliases so producers can land incrementally.

| Field | Type | Clock domain / unit | Producer |
|---|---|---|---|
| `processRunId`, `workerPid` | string, int | identity (no clock) | WT-15/WT-16 worker |
| `inferenceGeneration` | int | identity; bumps on media-loop reset **without** resetting counters | WT-15 |
| `personCompletedCount` / `violenceCompletedCount` / `weaponCompletedCount` | int, cumulative | completed-inference counts, monotone per `processRunId` | WT-15/WT-16 |
| `framesReadCount`, `duplicateFrameCount`, `reconnectCount` | int, cumulative | counts | WT-14 |
| `capturedAtMonoMs`, `enqueuedAtMonoMs`, `dequeuedAtMonoMs`, `inferenceStartedAtMonoMs` | float | `time.monotonic()*1000`, producer process | WT-15 |
| `frameAgeMs`, `frameAgeClockSource` | float, string | `inferenceStartedAtMonoMs − capturedAtMonoMs`, same monotonic domain | WT-15 |
| `stageFrameReadMs` | float ms | capture-monotonic (pre-read → decode complete) | WT-14 |
| `stageCaptureToQueueMs`, `stagePreprocessMs`, `stageEnqueueToDequeueMs`, `stageInferenceWaitMs` | float ms | worker-monotonic, single-clock diffs | WT-15 |
| `stageInferenceComputeMs`, `inferenceComputeSynced` | float ms, bool | worker-monotonic; `synced=true` only for CUDA-synced completed-inference timing | WT-16 |
| `stageModelLoadMs`, `stageFirstInferenceMs`, `stageEngineBuildMs`, `inferenceColdStartMs` | float ms | worker-monotonic cold-start stages (G-13) | WT-15/WT-16 |
| `frameQueueDepth`, `frameQueueDropped`, `frameQueueDroppedDerived` | int, cumulative for drops | counts; derived = gaps in `FramePacket.sequence` (independent R-2 measure) | WT-14/WT-15 |
| `resultQueueDepth`, `resultQueueDropped`, `backlogFrames` | int | counts; `backlogFrames = frame_queue.qsize()` at `get()` | WT-15 |
| `readGapP50Ms`/`P95Ms`/`MaxMs` + `readGapSampleCount`, negotiated/requested stream mode | float/int | capture cadence; denominators mandatory | WT-14 |
| `decisionConfirmLatencyMs` (alert payload) / `decision_confirm_latency_ms` + `decision_confirm_latency_clock` (inside `decision_layer`) | float ms, string | window-open → CONFIRMED on the decision sample clock (published verbatim as `decision.confirmLatencyClock`); `None` until a confirmation and after reset | WT-20 (landed `c4f6bf9`; ingested from both payload shapes) |
| `frameSequence` | int ≥ 0 | display-frame identity (render/MJPEG counter), NOT the inference sequence | WT-17 (S-09) |
| `frameAgeAtDetectionEmitMs` + `frameAgeAtDetectionEmitClockBase` | float ms, enum | SSE-emission stamp − that frame's `captured_at`, computed only inside the producer-declared base (`monotonic-gettickcount64` \| `perf-qpc`) | WT-17 (S-09) |
| `renderBacklogDroppedCount` | int ≥ 0 | render-thread latest-wins drops (distinct from `backlogFrames` and `frameQueueDropped`) | WT-17 (S-09) |
| `gpuMemoryUsedBytes` per `processRunId` | int | VRAM (nvidia-smi/pynvml) | WT-16 |

Emitted surfaces:

* `GET /detections` → additive `pipeline` block (`metrics.detection_telemetry_payload`):
  per-frame `stageMs`, `queues`, `counters`, `frameAgeMs{atInferenceStart, atPublication,
  atDisplay:null, clockSource}`, `inferenceComputeSynced`, `processingLatencyMs`
  (+ `processingLatencyClockDomain`), and an explicit `unavailable[]` list of field paths
  that were not measured. Consumers must render `null` as "unavailable", never as `0`.
* `GET /system/status` → additive `metrics` (full `summary()` incl. `metricsExport`) and
  `subsystems` (G-10 health per telemetry subsystem). The handler also ingests every
  configured camera snapshot, so polling status/metrics keeps the registry fresh.
* `GET /system/metrics` (handler unchanged) → legacy six keys + `telemetry` + `metricsExport`
  (schema `sentinel-metrics-export/1`). This is the machine-readable export for `bench/`:
  `rates.{captureFps, renderFps, publicationFps, completedInferenceFps.{person,violence,weapon}}`
  computed **separately**, `frameAgeMs.{atInferenceStart,atPublication,atDisplay}`,
  `stageLatencyMs.{stage}.{p05,median,p95,min,max,n,unit,clockDomain[,synced][,model/byModel]}`,
  `queues.{frame,result}.{depthNow,depthDist,droppedTotal,droppedDerivedTotal,divergence,dropRatePerSec}`,
  `counters`, `models`, `decision`, `resources`, `faults`, `faultLog`, `subsystems`,
  `clockDomains`, `fieldNaming`, `rules`, `runProvenance`, `ingest`, `observation`.

## 4. Clock-domain rules (enforced in the export, published in `export.rules`)

1. Durations are single-clock differences only (`...Ms`); absolute stamps encode domain and
   unit (`...AtMonoMs` = `time.monotonic()*1000`, `...AtEpochMs` = `time.time()*1000`).
2. `time.monotonic()` is machine-wide, so same-machine monotonic differences across the
   capture thread, worker process and API process are comparable — and are still labelled
   with their producing domain (`monotonic-same-machine` for derived publication age).
3. Media clock (`sample_timestamp`, file sources) is never mixed with monotonic or wall clocks.
4. Processing latency (capture→result build) ≠ glass-to-alert. Frame age at display is a
   browser-wall-minus-server-wall estimate and is labelled cross-clock, not monotonic.
5. Unmeasured = `null` + reason; never `0`.
6. Counters are monotone per `processRunId`; a regression without a new run id is logged as
   `counterRegressionDetected` and rate windows never cross a run boundary.

## 5. Bench consumption notes

* Poll `GET /system/status` (or keep a `/detections` subscription) so ingest runs; the export
  reports `ingest.lastIngestAtMonoMs` and `observation.*` so a consumer can prove staleness.
* `rates.completedInferenceFps` is computed from completed counters over the measured window
  and carries `numerator`, `denominatorSeconds`, `samples`, `processRunId`, `stationary`.
  `stationary: true` means the counter was present and did not advance — a measured zero,
  distinct from `null` (unmeasured).
* GPU sampling is passive (`nvidia-smi` here; `pynvml` if present) and needs no GPU lock;
  no benchmark was run by this workstream. `AI_SENTINEL_DISABLE_GPU_SAMPLER=1` disables it
  and the reason is published as `resourceSamplerSource: "disabled"`.
* `resources.gpu*` is **device-wide** (`gpuScope`: nvidia-smi/pynvml device totals), never
  per-process VRAM — `gpuPerProcess` says so explicitly and per-process numbers come from
  WT-16 per `processRunId`. `contentionNote` encodes the RESOURCE-LOCK protocol: acquisition
  is the atomic `mkdir` only, and a measured run taken while another workload held the lock is
  CONTENDED/INVALID and must be re-run, never silently kept.
* `runProvenance` is first-class: unlabelled runs export `{"label":"unlabeled"}` and must not
  be treated as clean adapter state (B-3).
* `decision.confirmLatencyMs` is a **producer-supplied** measurement (WT-20, pinned by their
  contract test `8ac3994`: `decision_confirm_latency_ms` + `decision_confirm_latency_clock`
  present in every decision response). Known artifact source: synthetic sample clocks in unit
  fixtures can yield implausible values (WT-20 observed a 9.0 s fixture figure from a
  votes-at-101/102 vs decision-clock-110 mismatch) — consumers MUST gate on `runProvenance`
  and never quote a latency from a fixture-driven run.

## 6. Validation performed (see handoff for raw output)

* `node --test tests/pipeline-telemetry.test.mjs tests/visual-state.test.mjs tests/detection-envelope.test.mjs`
  → 32 passed (14 original telemetry regressions + 5 new pipeline cases + the untouched
  visual-state/envelope suites).
* `backend/tests/test_metrics_telemetry.py` (project venv, torch/onnxruntime) → `15 passed`,
  including two real-app cases: `_build_detection_payload` attaching the `pipeline` block and
  `GET /system/status` + `GET /system/metrics` through `TestClient`.
* `npm run typecheck` (`tsc --noEmit`) after `npm ci` → clean; `npm run lint` → clean.
* `api.py` compiles (`py -3 -m py_compile`) with and without the SC-10 cherry-pick.
* Module-level replay smoke (`docs/campaign/engineering/13-metrics-replay-smoke.py`, the
  reproducible script; artifact `13-metrics-export-sample.json`, 14 697 bytes,
  sha256 `a6f66238416a7ecc9a6f6deeccc43f5368e45b133de237c308b86052e60c6096`) produced with the
  **venv interpreter** so its `clockQuantization` block reports the deployed runtime values.

## 8. Clock quantization finding (measured, 2026-09-29)

Blueprint IDs: per the orchestrator reallocation ruling this workstream allocates **no** new
registry IDs. The finding below is submitted for **integrator assignment** in the `N`
namespace (it was briefly proposed as "N-17"; the integrator assigns the final number, the
same policy as `F-58+`). Registry-only label — no code references any ID.

Measured on the project venv interpreter (`./venv/Scripts/python.exe`, **CPython 3.12.5**, Windows):

| clock | resolution | implementation |
|---|---|---|
| `time.monotonic()` | **15.625 ms** | `GetTickCount64()` |
| `time.time()` | **15.625 ms** | `GetSystemTimeAsFileTime()` |
| `time.perf_counter()` | **0.0001 ms** | `QueryPerformanceCounter()` |

Consequence: every sub-15.6 ms duration computed with `time.monotonic()` on the deployed
interpreter collapses to 0 or a 15.625 ms multiple, so stage distributions (preprocess ≈3 ms,
IPC ≈9 ms) and `frameAgeMs` would be quantization artifacts rather than measurements. The
system interpreter (`py -3` = CPython 3.14) uses QPC for `time.monotonic()`, so this is
interpreter-dependent and easy to miss.

Mitigation implemented here: all rate windows, queue delta stamps and resource TTLs use
`time.perf_counter()`; the export publishes `clockQuantization` for the *producing*
interpreter, requires `captureClockBase` (`perf-qpc` | `monotonic-gettickcount64`) before any
cross-boundary age is derived, and never subtracts stamps from different bases. WT-15 and
WT-16 were notified with the measurements; both adopted `time.perf_counter` for durations
(WT-15 additionally emits `captureClockBase` + `cudaSyncApplied`).

## 9. Limitations (honest, not measured)

* No camera device: nothing here is measured on live capture; all stage fields render
  "unavailable" until the WT-14/WT-15/WT-16 producers land in the same integration.
* `frameAgeMs.atDisplay` is a cross-clock estimate; true glass-to-alert remains unmeasured
  (requires independent onset labelling).
* `latencyMs`/`processingLatencyMs` remain capture→result-build; do not relabel as alert or
  display latency.
* `GET /system/metrics` freshness depends on ingest: with no `/detections` subscriber and no
  `/system/status` poll, counters stay unmeasured (the export says so via `observation`).
* `npm run docs:check` is **red/expected** on this branch, per the SC-9 ruling: it reports
  `Unregistered active document: docs/campaign/engineering/13-telemetry-audit.md` (plus any
  other scoped docs on the branch) until the `scoped_artifacts` allowlist on
  `codex/sentinel-03-docs-gen` merges at integration. At the pinned baseline it additionally
  reported `Stale generated document: docs/SOURCE-MANIFEST.json` and `docs/CURRENT.md`
  (pre-existing B-6); those clear with the committed `docs:sync` regeneration.
* `npm run docs:sync` regeneration is committed per the SC-9 ruling (generated fields follow
  implementation; the integrator re-generates snapshots from the assembled candidate). Note
  for the reviewer: in this worktree the regenerated `docs/SOURCE-MANIFEST.json` also **drops**
  entries for paths that are absent here (untracked user modules such as `go2rtc_bridge.py`,
  `_pipeline_ai_deprecated.py`, `dataset_manager.py`), so the manifest must be re-generated in
  the full checkout after integration — that is exactly why the ruling has the integrator
  re-run it.
* Text of this document is Arabic-free by design (scoped engineering artifact, not a UI string).
