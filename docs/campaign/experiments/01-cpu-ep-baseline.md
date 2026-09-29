---
authority: scoped
non_authoritative: true
---

# EXP-01 CPU-EP baseline completed-inference timings

- Hypothesis: With the registered preprocessing (letterbox 640×640, pad 114, BGR→RGB, /255), fp32 ONNX models and `AI_SENTINEL_ORT_INTRA_OP_THREADS=2`, CPU-EP completed-inference medians on this revision and fixture set will be the same order as the registered revision-`6fb3bcac…` figures (person 135.6 ms, weapon 696.5 ms medians). This run establishes the WT-16 CPU reference; any deviation is reported, not tuned away.
- Requirement link: F-09 (weapon engine provider status), F-10 (person detector provider status); WT-09 §9 protocol items 1; G-13 cold-start stages.
- Baseline: commit `e86d34b5` + cherry-pick `86d7697` (SC-10) on `codex/sentinel-16-inference-accel`; models `person_yolo.onnx` sha256 `3fafb13e…e60b8`, `weapon_yolo.onnx` sha256 `96991cd5…75aef`; preprocessing per `yolo_onnx.prepare_input`; decision config untouched (`config/thresholds.toml` defaults); env: Python 3.12.5, `onnxruntime-gpu==1.18.0`, torch 2.3.0+cu118, driver 591.86; source mode `file-media` (cam3.mp4 sha256 recorded at run time, fixed frame indices 0,15,…,135); resolution 1280×720 source → 640×640 model input; workload = n=5 cold + 300 warm completed inferences per model.
- Candidate: (none — this is the baseline measurement for the CPU configuration.)
- Success criteria (defined BEFORE inspecting results): run completes with ≥300 warm samples per model, all timings finite, cold/warm separated, pre/post-processing distributions separate from compute, report carries `clockBase: perf_counter` and `inferenceComputeSynced`.
- Failure criteria / rollback: any harness error, non-finite timing, or <300 warm samples invalidates the run (fix harness, re-run; no environment mutation to recover). No code rollback needed (measurement only).
- Result: **MEASURED** (2026-09-29, clean RESOURCE-LOCK acquisition, `bench/results/campaign-accel-2026-09-29/raw/raw-person-cpu.json` + `raw-weapon-cpu.json`, code `1218a6c`, fixture cam3.mp4 sha256 `60591ba1…`, file-media, fixed indices 0,15,…,135):
  - person (COCO-80, raw head): warm p50 **67.70 ms** (p05 60.37 / p95 79.87 / max 92.60, n=300); cold p50 76.26 ms (n=5); stageModelLoadMs 81.4; stageFirstInferenceMs 88.4; preprocess p50 3.60 ms; postprocess p50 3.32 ms.
  - weapon (6-class, raw head): warm p50 **468.58 ms** (p05 435.08 / p95 545.41 / max 818.83, n=300); cold p50 541.27 ms (n=5); stageModelLoadMs 526.9; stageFirstInferenceMs 479.8; inferenceColdStartMs 1006.7; preprocess p50 3.77 ms; postprocess p50 0.71 ms.
  - Providers active: `['CPUExecutionProvider']` both models; intra-op 2; `cudaSyncApplied: false`.
  - Deviation note: these isolated completed-inference medians are BELOW both the dirty-claim CPU figures (person 135.6 / weapon 696.5 ms, UNVERIFIED scope) and the registered in-pipeline stage medians (person_onnx p50 158.0 / weapon_window p50 809.0 ms, revision `6fb3bcac…`) — different measurement scope (isolated run+decode vs in-pipeline stage incl. engine bookkeeping), different revision and machine state. All are reported as measured; none folded into another.
  - One earlier person-CPU run (01:38) overlapped the mkdir-race incident and is marked CONTENDED/INVALID (`invalid/raw-person-cpu.CONTENDED-no-valid-lock.json`, warm p50 126.4 ms — contention signature visible); re-run above supersedes it.
- Verdict: adopt (baseline established; protocol criteria met: n≥300 warm, finite, cold/warm separated, pre/post separate)
- Cold vs warm: separated. Completed-inference timing (ORT run returns host outputs), not launch timing. CPU: no CUDA sync applicable (`cudaSyncApplied: false`).
