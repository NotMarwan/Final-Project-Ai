# Local operation

Current implementation entry points are root app/ (web) and backend/api.py (API). No service is claimed running by this document.

For this existing Windows installation, from the project root in separate terminals:

```powershell
& ./venv/Scripts/python.exe -m uvicorn api:app --host 127.0.0.1 --port 8002 --app-dir backend
npm run dev
```

The API reads local configuration and may activate configured cameras/notifications. The operator controls those settings. Never paste credentials into documentation or command-line URLs. These commands are source-derived, not a fresh live-camera verification. The bench harness is the isolated alternative for experiments; see bench/README.md.

No validated calibration artifact is currently registered. Normal startup refuses without one. For local development only, the exact fail-loud override is:

```powershell
$env:AI_SENTINEL_CALIBRATION_UNVERIFIED_OVERRIDE = "I-UNDERSTAND-SCORES-ARE-UNVERIFIED"
./venv/Scripts/python.exe -m uvicorn api:app --host 127.0.0.1 --port 8002 --app-dir backend
```

The application prints a warning and marks the override active; it must not be used for production or represented as calibration evidence. The guard rejects this override in production mode. Remove the variable from the shell after stopping the process with `Remove-Item Env:AI_SENTINEL_CALIBRATION_UNVERIFIED_OVERRIDE`.

Use existing lockfiles/environment; an upgrade is a separate measured change. Current camera availability and readiness evidence are in CURRENT.md. Source/configuration changes require relevant remeasurement. Do not infer that stale status endpoints, model initialization or successful HTTP requests demonstrate accurate detection.

## Runtime controls and local reports

Configure administrator authentication on the server before using protected controls. Missing server credentials now disable protected mutations. The local report is read from /reports/local/{alert_id}; it is a recorded-facts summary in Arabic, with no image-language interpretation. Online DeepSeek remains optional and sends incident metadata externally only when the operator explicitly requests generation.

## Reproducible calibration candidate

Run `./venv/Scripts/python.exe -m bench.calibrate scores.json --output candidate-calibration.json` with a new output path. The input contains model_sha256 and observations with clip_id, unique source_sha256, split (calibration/test), binary label, score in[0,1], and label_source (publisher/independent-human). Both splits require both classes. The tool rejects duplicated clips, nonfinite scores and model-generated labels. Never fabricate a scores file or copy synthetic unit-test labels into evaluation evidence. The candidate does not activate runtime calibration.


## Evidence encoding dependency

The active environment includes imageio-ffmpeg0.6.0. New installs must install backend/requirements-evidence.txt (also included by the backend dependency declaration). Runtime resolves AI_SENTINEL_FFMPEG, a system ffmpeg, or the installed bundle. Clips are published only after H.264/yuv420p encoding and complete decode verification. A missing or failed encoder produces an explicit evidence error.

## Current accelerator decision

The measured project venv uses `onnxruntime-gpu` 1.18.0 with Torch 2.3.0+cu118 on Windows/Python 3.12. The base `backend/requirements.txt` still installs CPU ONNX Runtime, so a fresh install is not a GPU-default environment. CPU and GPU ONNX Runtime wheels share a package namespace; install only one. `scripts/select_onnx_runtime.py` can report the installed profile or switch it after the backend is stopped. Its package/provider validation is only a preflight; rerun the full matched workload before treating a switched profile as measured.

The latest registered CUDA file-replay report is `bench/results/integration-review-2026-09-29/report.json`. It records all three model paths active, render FPS p05/p50/p95 of 25/30/30.55, and all 62 backend source hashes matching reviewed source `e1a5636`. This is replay throughput evidence, not model accuracy, live-camera acceptance or end-to-end event timing. Historical matched CPU/CUDA reports are retained for their original source. Provider enumeration alone does not establish usable TensorRT.

To reproduce a matched file-replay run after source changes, first confirm the selected runtime with `./venv/Scripts/python.exe scripts/select_onnx_runtime.py`, then stop other backend runs and use a new output directory:

```powershell
$env:AI_SENTINEL_CALIBRATION_UNVERIFIED_OVERRIDE = "I-UNDERSTAND-SCORES-ARE-UNVERIFIED"
$env:AI_SENTINEL_ORT_DEVICE = "cuda"
./venv/Scripts/python.exe -m bench.run --seconds 75 --warmup 25 --all-detection --extended-controls --output bench/results/new-run
```

The harness must record completed requested model calls and active post-warmup rendering. Use separate CPU and CUDA output directories with the same source, fixtures, settings and environment except provider selection. Preserve reports and hashes; do not use this replay as proof of live capture, model accuracy or glass-to-alert latency.

For the web development server, open `http://localhost:3000`; the patched Next.js development-origin protection expects localhost. Production build, typecheck and lint pass with the committed lockfile. Main integration preserves original local files under `.runlogs/integration-primary-backup-20260929/`; its manifest records hashes. Unreviewed optional source copies are preserved there instead of being implicitly imported by the reviewed runtime. Model weights remain in place.
