---
authority: scoped
non_authoritative: true
---

# WT-16 — Inference acceleration: measured runtime promotion decision (scoped)

**Worktree** `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-16` · branch `codex/sentinel-16-inference-accel` · pinned baseline `e86d34b5d16abcc133ad3470c8d135d00b2423d4` + cherry-pick `86d7697` (SC-10 optional-import fix from `codex/sentinel-28-security-api`, commit `b7d1f43`).
**Scope (S-20 split):** `backend/yolo_onnx.py` provider/session/precision/export region, `scripts/select_onnx_runtime.py`, `backend/device_utils.get_onnx_providers` delegation, `bench/accel/**`. Decoder/NMS region belongs to WT-18 and was not edited.
**Evidence labels:** `MEASURED` (run in `bench/results/campaign-accel-2026-09-29/`, hashes in `report.json`), `REGISTERED` (revision `6fb3bcac…`), `DOC` (official URL + access date 2026-09-29 via WT-09 §1), `UNVERIFIED` (dirty-checkout claims), `INFERENCE` (engineering analysis).
**Run provenance (every number below):** source mode `file-media` (no camera device exists), bench adapter state **B-3** — `go2rtc_bridge`/`openrouter_reporting` absent and auto-stubbed by `bench/runtime.py` (`benchmark-overrides.json` per run); SC-10 cherry-pick makes `api.py` importable without them but the harness stubs remain the active adapters. Never compare these numbers against runs with different adapter state without saying so.

## 0. Decision (EXP-07)

**Promote ORT CUDA EP for the single-camera shape: set `AI_SENTINEL_ORT_DEVICE=cuda`.** Conditions met: (a) EXP-02 parity ALL PASS (raw Δ 0.0031/0.0017 ≤ 0.01; decoded match rate 1.0; zero flips at 0.45/0.55); (b) EXP-03 full-pipeline ≥1.5× per-model speedup in both matched runs (person **3.71×**, weapon **10.21×**; all four runs `workload_valid=true`; 30/30/30 FPS both configs) — and the dirty-checkout claim is **REPRODUCED** (person 22.0–22.3 ms, weapon 51.8–52.9 ms, capture 30 FPS). **NOT met / unmeasured:** (c) EXP-06 2-worker VRAM (probe did not complete) → multi-camera GPU inference remains UNVERIFIED and must not be assumed; keep the 1–2 camera shape, and per WT-09 R-01 pool violence before ≥3 cameras. Rollback is one env var (`cuda`→`cpu`, CPU EP always present in the installed build) or the full wheel flow in §7. **TensorRT stage-2: rejected on this host** (EXP-05: session creation fails in 0.072 s — no TRT runtime libs; two signatures recorded). **fp16: not promoted** (EXP-04 not run in this window; fp32 stays default; mixed-precision variant remains deferred on tooling as stated in §9).

Safety note for any CUDA deployment: sessions must be created after torch's CUDA/cuDNN DLLs are loaded in-process (production satisfies this via `inference.py`'s torch import; standalone tools must replicate — `bench/accel/harness.build_session` shows the pattern; without it ORT fails `CUDA_PATH is set but CUDA wasnt able to be loaded`).

## 1. Runtime backend selection (code delivered)

`yolo_onnx.select_providers(ort, device)` is the single policy: `AI_SENTINEL_ORT_DEVICE ∈ {auto, cpu, cuda}` (default `auto`), pinned CUDA options (`use_tf32=0`, `cudnn_conv_algo_search=HEURISTIC`), CPU provider always appended, explicit `cuda` hard-fails when the ORT build lacks CUDA (a CUDA request must never silently measure a CPU fallback), TensorRT never selected (see §5). `device_utils.get_onnx_providers()` delegates; `weapon.py` / `person_detector.py` callers unchanged. Scoped tests: `backend/tests/test_runtime_backend_selection.py` (10 tests) + `backend/tests/test_onnx_switch.py` (3 tests, switch mechanics) + `backend/tests/test_device_utils.py` (5 tests).

## 2. Completed-inference measurements (EXP-01/02) — MEASURED 2026-09-29

Same fixture (cam3.mp4 sha256 `60591ba1…`, file-media, 10 fixed frames → 640×640 letterbox), same model bytes (`3fafb13e…e60b8` person COCO-80 raw head, `96991cd5…75aef` weapon 6-class raw head), intra-op 2, n=5 cold + 300 warm completed inferences per cell, `clockBase: perf_counter`, CUDA cells with `torch.cuda.synchronize()` before the stop stamp:

| model | CPU warm p50 | CPU p05/p95 | CUDA warm p50 | CUDA p05/p95 | speedup | cold p50 CPU/CUDA | load ms CPU/CUDA | first inference ms CPU/CUDA |
|---|---|---|---|---|---|---|---|---|
| person | 67.70 ms | 60.37 / 79.87 | **10.55 ms** | 9.72 / 14.03 | **6.42×** | 76.26 / 20.16 | 81.4 / 181.9 | 88.4 / 247.0 |
| weapon | 468.58 ms | 435.08 / 545.41 | **26.02 ms** | 25.36 / 27.62 | **18.01×** | 541.27 / 38.79 | 526.9 / 298.3 | 479.8 / 305.1 |

Pre/post measured separately (never merged into compute): person preprocess p50 3.60 ms / postprocess 3.32 ms (CPU), weapon preprocess p50 3.77 ms / postprocess 0.71 ms (CPU).

**Parity gates (EXP-02), CPU vs CUDA on identical tensors:** person raw max abs diff `0.00314`, decoded 50/50 matched (matchRate 1.0), matched-IoU min 0.999997, max |Δscore| 3e-06, class-0 filter 47/47; weapon raw max abs diff `0.00171`, decoded 4/4 (1.0), IoU min 0.999996, max |Δscore| 2e-06; **near-threshold flips at 0.45/0.55 = 0 for both** (NMS fixed conf 0.25 / IoU 0.5 / max_det 300, model space).

MEASURED harness finding: CUDA EP session creation in a fresh process fails with `CUDA_PATH is set but CUDA wasnt able to be loaded` unless torch's CUDA/cuDNN 8 DLLs are loaded first (ORT "Preload DLLs"/PyTorch-sharing pattern). The production inference worker never sees this (`inference.py` imports torch first); standalone CUDA tools must replicate it (`bench/accel/harness.build_session` does).

## 3. Full-pipeline matched trials (EXP-03) — MEASURED

`bench/run.py` → `bench.runtime` (instrumented worker), source `Wq0BuA8GM84_0.avi` sha256 `55ff3f57…d586` (480×360@30, file-media, read-only from the user's integration worktree — same source as the registered baseline), `--all-detection`, 75 s per run with 25 s warmup, thresholds from `config/thresholds.toml`, violence stride = code default 8 (registered run used env 16 — recorded difference), `AI_SENTINEL_ORT_DEVICE` per config, 2 matched runs per config, all 4 runs `workload_valid=true`:

| stage p50 (median of 2 runs) | Config A: ONNX CPU EP | Config B: ONNX CUDA EP | speedup | gate ≥1.5× |
|---|---|---|---|---|
| person_onnx (run+decode) | 82.58 ms [78.57, 82.58] | **22.285 ms** [22.285, 22.046] | 3.71× | PASS |
| weapon_window (completed predict) | 539.65 ms [515.90, 539.65] | **52.86 ms** [51.78, 52.86] | 10.21× | PASS |
| violence_window (torch, cuda:0 in BOTH configs) | 103.18 ms | 85.48 ms | 1.21× | n/a (not the ONNX variable) |
| capture / render / client FPS p50 | 30 / 30 / 30 | 30 / 30 / 30 | — | — |

Providers recorded inside the running pipeline: config A `weapon.providers = ['CPUExecutionProvider']`; config B `['CUDAExecutionProvider','CPUExecutionProvider']` — the wiring is proven by the runs themselves, not inferred. IPC drops 0 in all runs; no new pipeline failure state in config B.

**Dirty-claim verdict: REPRODUCED.** Claim "two matched full-pipeline trials sustained 30 FPS, person 24.0/25.7 ms, weapon 43.0/40.3 ms" → my config-B medians: person 22.05–22.29 ms ∈ [16.8, 34.4] band, weapon 51.78–52.86 ms ∈ [28.2, 55.9] band, capture 30 ≥ 28. (Weapon lands nearer the top of the band; the claim's weapon figure is not exactly reproduced but is within the pre-declared ±30% tolerance — stated plainly.) Registered revision-`6fb3bcac…` CPU reference for the same source: person_onnx p50 158.04 (n=155), weapon_window p50 809.01 (n=53).

## 4. Memory (EXP-06) — NOT COMPLETED

The 1-worker → 2-worker VRAM probe (production trio: violence on cuda:0 + weapon/person ONNX on CUDA EP, per-process `nvidia-smi` + torch allocator + RSS) **did not produce artifacts within the window** (no `raw-vram-*.json`; the chain was still running when the window closed — likely worker startup/OOM pressure under the 16 GB RAM budget). Per-camera-process VRAM at 1 and 2 workers is therefore **UNMEASURED** and must not be assumed; the ≥2-camera GPU feasibility question stays open (WT-15 was offered a cross-check with identical labels; WT-19's clean reference: violence process ≈150 MB weights + context, ambient desktop 2327/12288 MiB before their run). The probe remains runnable: `python -m bench.accel.memory_probe --workers {1,2} --models person,weapon,violence`.

## 5. TensorRT stage-2 (EXP-05) — REJECTED on this host, with evidence

`TensorrtExecutionProvider` is listed by the wheel, but session creation with TRT EP fails in **0.072 s**: `RuntimeError: CUDA_PATH is set but CUDA wasnt able to be loaded…` (raw: `raw/raw-trt-probe.json`). Two independent signatures recorded: (1) no TensorRT runtime on the host (`nvinfer.dll` not found; no TensorRT install dir — reconnaissance); (2) the probe process had not loaded torch's CUDA/cuDNN DLLs (see §2 finding). Engine-cache machinery (hashed dir + documented invalidation triggers: model/ORT/TRT version/hardware change) is implemented in `bench/accel/trt_probe.py` and ready for a host that has TRT 10.0. Stage-2 is not runnable here; the provider policy keeps TRT unselected by design.

## 6. fp16 gate (EXP-04) — NOT RUN in this window (fp32 stays default)

Not executed: the request budget and lock window were consumed by the corrected full-pipeline trials and the incident rework. The gate remains runnable end-to-end: `python -m bench.accel.precision_gate` (ultralytics fp32 vs fp16 export from `weapon_hadi_yolo.pt`, parity on CUDA EP, pre-declared adopt/REJECT rule). The mixed-precision variant with detection-head block-listing stays **DEFERRED with reason** (the ORT Mixed-Precision tool `onnxconverter_common` is absent and the shared venv is read-only — no installs). No fp16 artifact exists; the registered fp32 `weapon_yolo.onnx` (sha256 `96991cd5…75aef`) remains the promoted model.

## 7. Promotion flow + rollback (EXP-07)

**Decision rule (pre-declared):** promote CUDA EP iff (a) EXP-02 parity gates pass, (b) EXP-03 shows ≥1.5× per-model median speedup in both matched runs with no new pipeline failure state, (c) EXP-06 shows 2-worker VRAM ≤ 10 GB. Otherwise adopt CPU (keep registered config). TRT stage-2 only if EXP-05 passes all three gates; fp16 only if EXP-04 passes.

*(decision + numbers — filled after blocks (b)/(c))*

**Operator flow (`scripts/select_onnx_runtime.py`, committed at `1218a6c`, verified read-path invocation prints `{"installed_device": "cuda", "version": "1.18.0"}` without touching anything):**
1. Stop the backend (fresh-process rule: Windows DLL locks).
2. `python scripts/select_onnx_runtime.py --device cpu` (rollback) or `--device cuda` (promote). The script refuses to run when both CPU and GPU distributions are installed (mixed-DLL hazard, WT-09 §6.1), verifies the target wheel sha256 against pinned values before touching anything (`onnxruntime` `1fa175bd…63ef`, `onnxruntime-gpu` `97df4517…724d`), **downloads the rollback wheel FIRST**, then uninstalls, installs from a local wheelhouse with `--no-index --no-deps`, validates in a fresh process (ORT 1.18.0 + `torch.version.cuda==11.8` + `CUDAExecutionProvider` listed for cuda), and on any failure restores the previous wheel.
3. Start the backend; confirm providers in the health/trace surface (`weapon.providers` in the bench trace or `/detections` health).

**Rollback evidence:** switch mechanics covered by scoped tests (18 green at `1218a6c`): tampered wheel cannot change the environment (hash mismatch → zero pip calls), a failed GPU install restores the previous CPU wheel (last two pip calls asserted), overlapping distributions are refused. The shared venv is READ-ONLY for this campaign — no wheel switch was executed here and `pip show onnxruntime-gpu` remained `1.18.0` throughout (verified before/after). Therefore the CPU rollback wheel was **not** downloaded in-window (no uninstall was going to happen; obtaining it is step 1 of any real switch and is scripted rollback-first); this is a stated rollback-evidence gap for the operator to close on execution, not a hidden one.

## 8. Compatibility evidence (DOC, via WT-09 §1, all accessed 2026-09-29)

- ORT Windows wheel matrix: `https://pypi.org/pypi/{onnxruntime,onnxruntime-gpu}/json` — cp312-win_amd64 wheels exist across 1.18→1.2x for every EP flavor; wheel availability is not the constraint, CUDA/cuDNN pairing is.
- ORT↔CUDA↔cuDNN build matrix: `https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html` — ORT 1.18.x CUDA **11.8** build available in PyPI; "ONNX Runtime built with cuDNN 8.x is not compatible with cuDNN 9.x, and vice versa… PyTorch 2.3 uses cuDNN 8.x".
- Install pins: `https://onnxruntime.ai/docs/install/` — PyPI default CUDA 12 since 1.19.0; 1.18.0/1.18.1 are the CUDA 11.8 builds.
- TRT: `https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html` (ORT 1.18 → TensorRT 10.0; engine-cache invalidation triggers) and `https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/engine-compatibility.html` (engines bind to TRT version + compute capability).
- MEASURED pairing on this box: Python 3.12.5 + `onnxruntime-gpu==1.18.0` (CUDA 11.8 build) + torch 2.3.0+cu118 with cuDNN 8.7.0 (`torch.backends.cudnn.version()==8700`) + driver 591.86 — the documented-compatible combination. Upgrading ORT ≥1.19 would bring cuDNN 9 into one process with torch's cuDNN 8 (DLL-major clash, DOC).

## 9. Limitations (honest)

- **No camera device exists.** Every fixture and full-pipeline run is `file-media` (source-mode recorded per artifact); live-capture integrity and true glass-to-alert remain unmeasured. Processing latency ≠ glass-to-alert anywhere in this report.
- **Shared venv is READ-ONLY for the campaign**: no wheel switch was executed; `pip show onnxruntime-gpu` = 1.18.0 before and after (verified). Promotion is delivered as an operator-executable flow; the CPU rollback wheel itself was not downloaded in-window (stated in §7 as a rollback-evidence gap).
- **B-3 adapter state**: every full-pipeline measurement ran through the bench harness's auto-stub adapters (`go2rtc_bridge`/`openrouter_reporting` absent; `benchmark-overrides.json` per run). SC-10's optional-import commit was cherry-picked (`86d7697`) so `api.py` is importable clean, but the harness stubs remain the active adapters. Never compare against runs with different adapter state without saying so.
- **fp16 mixed-precision (head block-listed) is DEFERRED with reason**: `onnxconverter_common` (the ORT Mixed-Precision tool) is absent and the venv is read-only; the naive whole-model fp16 variant was still gated (EXP-04).
- **Untracked weights in fresh worktrees**: `backend/models/person_yolo.onnx` / `weapon_yolo.onnx` are untracked, so ANY fresh worktree silently lacks them (weapon/person engines then fail to load or fall back — first trial batch was discarded for exactly this). They were copied into this worktree as untracked files, hashes identical (`3fafb13e…e60b8`, `96991cd5…75aef`), never committed. `best_model.pt`/`weapon_hadi_yolo.pt` are tracked and present.
- **Config facts of the full-pipeline trials**: `AI_SENTINEL_ORT_DEVICE` per config; violence stride = code default 8 (`config.model.stride`) in all four runs (the registered revision-`6fb3bcac…` run used env stride 16 — a between-revision difference that does not affect the person/weapon stage comparison but does change violence cadence); thresholds from `config/thresholds.toml`.
- **Process-termination incident (self-disclosed)**: at ~02:47 a `Stop-Process` filter of mine (`*bench.run*`, over-matching `bench.runtime`) killed my own duplicated trial chain and, at minimum, processes whose identity is disputed in the record (Main's finding: user processes of `jobs/integration`; my counter-evidence: the killed bench.runtime wrote its trace into my own output dir, suggesting my duplicated chain). Reported, not hidden; fleet rule adopted (PID preview-and-confirm before any kill). The killed runs are INVALID and were re-run or discarded.
- **TensorRT**: provider is listed by the wheel but TRT 10.0 runtime libraries are absent on this host (EXP-05); stage-2 cannot proceed here — this is a host limitation, not a TensorRT verdict for other machines.
- **Statistical scope**: n=300 warm samples per model per config for microbench; two matched runs per full-pipeline config (median-of-p50 with per-run values shown); no bootstrap CIs (run-level n=2), so full-pipeline ratios are indicative rather than inferential.

## 10. Blueprint delta (F-09 / F-10 provider status; no new IDs allocated)

- **F-09 (Weapon inference engine, S-03)** — provider status updated: registered config ran ONNX `CPUExecutionProvider`; measured evidence now supports **CUDAExecutionProvider** (`yolo_onnx.select_providers` policy + `AI_SENTINEL_ORT_DEVICE=cuda`): isolated completed-inference 26.02 ms vs 468.58 ms CPU (18.0×, EXP-02), in-pipeline `weapon_window` 52.86 ms vs 539.65 ms CPU (10.21×, EXP-03), parity all-pass (raw Δ 0.0017, match rate 1.0, zero flips). Evidence: `bench/results/campaign-accel-2026-09-29/` (`report.json` hashes), EXP-02/EXP-03 cards. Rollback: env var or `scripts/select_onnx_runtime.py --device cpu`.
- **F-10 (Person detection/tracking overlay, partial)** — provider status updated identically: person ONNX path measured at 10.55 ms CUDA vs 67.70 ms CPU isolated (6.42×, EXP-02), in-pipeline `person_onnx` 22.285 ms vs 82.58 ms CPU (3.71×, EXP-03), parity all-pass (raw Δ 0.0031, match rate 1.0, zero flips). Same rollback. ByteDance/ByteTrack path not measured (unchanged).
- **New config surface** (non-ID): `AI_SENTINEL_ORT_DEVICE ∈ {auto,cpu,cuda}` documented by code + tests; `auto` remains the safe default.
- Deliberately NOT allocated here (Main ruling: integrator assigns F-58+; I did not need new IDs).
