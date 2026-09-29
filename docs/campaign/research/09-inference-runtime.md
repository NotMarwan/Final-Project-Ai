---
authority: scoped
non_authoritative: true
---

# WT-09 — Inference & runtime options research (scoped campaign catalog)

**Worktree** `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-09` · branch `codex/sentinel-09-inference-research` · pinned baseline `e86d34b5d16abcc133ad3470c8d135d00b2423d4`.
**Status:** scoped research catalog for R-01/R-02 decisions and WT-15/WT-16 measurement design. Not a status or design authority (`docs/CURRENT.md` / `docs/DESIGN.md` remain the only authorities).
**Evidence labels:** `MEASURED` = probe run on this machine in the shared venv (command recorded); `DOC` = verbatim/near-verbatim official documentation with URL + access date (all web sources accessed **2026-09-29**); `REGISTERED` = from `bench/results/**` or the wt-01 runtime map (revision `6fb3bcac…`, not the pinned commit); `INFERENCE` = engineering analysis, not measured.
**Blueprint seeds read before finalizing:** wt-01 `docs/blueprint/{runtime-map.md,ownership-map.md,runtime-map-verification.md}`, wt-02 `docs/blueprint/{design-map.md,ui-contract.md}`. The reconciled seed in `wt-03/docs/blueprint/` was **absent** at the time of writing (checked 2026-09-29) — this document could not consume it.

---

## 0. Verified local environment (all MEASURED, 2026-09-29, shared project venv)

| Fact | Value | Probe |
|---|---|---|
| Python | 3.12.5 | `venv/Scripts/python.exe -c "import sys…"` |
| ONNX Runtime | **`onnxruntime-gpu 1.18.0` active** (`onnxruntime` and `onnxruntime-directml` NOT installed) | `importlib.metadata` |
| ORT providers listed | `['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']` | `ort.get_available_providers()` |
| ORT capi DLLs | `onnxruntime_providers_cuda.dll`, `onnxruntime_providers_shared.dll`, `onnxruntime_providers_tensorrt.dll` | glob `onnxruntime/capi/*.dll` |
| Torch | 2.3.0+cu118, `torch.cuda.is_available() == True`, `torch.version.cuda == 11.8` | import probe |
| cuDNN in torch | `torch.backends.cudnn.version() == 8700` (8.7.0) | import probe |
| Triton | **not installed** (`find_spec('triton') is None`) | import probe |
| GPU / driver | NVIDIA GeForce RTX 3060, 12288 MiB, driver 591.86 | `nvidia-smi --query-gpu=name,driver_version,memory.total` |
| Model files (untracked) | `person_yolo.onnx` 12.85 MB (sha256 3fafb13e…e60b8), `weapon_yolo.onnx` 103.6 MB (sha256 96991cd5…75aef) | wt-01 runtime-map §3.1 |
| Registered model loads | violence = SlowFast `ViolenceDetector` on `cuda:0`, stride 16, **load_ms 3020.17**; weapon + person ONNX on `CPUExecutionProvider` | `bench/results/sprint2-verified-480p/report.json` via wt-01 §3.2 / V-09 (revision `6fb3bcac…`) |

**Important:** the shared venv currently carries the **GPU** distribution. The registered measurements were taken on CPU EP after a documented GPU rollback (wt-01 PLAN R-02/R-05). The GPU/CPU wheel pair is mutually exclusive (see §6.1).

---

## 1. Compatibility evidence (official, URL + access date 2026-09-29)

### 1.1 ORT Windows wheel matrix (verified against the PyPI JSON API)

Source: `https://pypi.org/pypi/{onnxruntime,onnxruntime-gpu,onnxruntime-directml}/json` (queried 2026-09-29; latest ORT is 1.30.0). All three distributions publish `cp312-cp312-win_amd64` wheels for **1.18.0 through 1.29.0** (each minor/patch that exists; e.g. onnxruntime-gpu 1.18.0/1.18.1/1.19.0/1.19.2/1.20.0/1.20.2/1.21.0/1.21.1/1.22.0/1.23.0/1.23.2/1.24.1/1.24.4/1.25.0/1.25.1/1.26.0/1.27.0/1.28.0/1.29.0/1.30.0). `onnxruntime-directml` wheels exist cp312-win_amd64 up to **1.24.4** (its last release). **Conclusion: Python 3.12 Windows wheels exist across the whole 1.18→1.2x range for every EP-flavor package; wheel availability is not the constraint — CUDA/cuDNN pairing is.**

### 1.2 ORT ↔ CUDA ↔ cuDNN build matrix

Source: `https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html` (accessed 2026-09-29). Key rows:

| ORT | PyPI GPU build | CUDA | cuDNN | Note (doc text) |
|---|---|---|---|---|
| 1.18.x | CUDA **11.8** build **available in PyPI** | 11.8 | 8.x | ← matches installed torch 2.3.0+cu118 (cuDNN 8.7.0) |
| 1.18.0 (CUDA 12 flavor) | 12.x | 12.x | 8.x | separate build; cuDNN 8 |
| 1.18.1 (CUDA 12 flavor) | 12.x | 12.x | 9.x | "cuDNN 9 is required" |
| 1.19.x / 1.20.x | CUDA **12** default on PyPI; **CUDA 11.8 builds not on PyPI** | 12.x | 9.x | "Compatible with PyTorch >= 2.4.0 for CUDA 12.x"; the 11.8 rows say "Not available in PyPI. Compatible with PyTorch <= 2.3.1 for CUDA 11.8" |
| 1.21–1.26 | 12.8 | 9.x | "Default GPU package build before 1.27" |
| 1.27+ | **CUDA 13.0 default** on PyPI (12.8 variants separate) | 13.0 | 9.x | "Starting with version 1.27, GPU packages published to PyPI … are built with CUDA 13.0 by default" |

Also DOC from the same page: "Because of Nvidia CUDA Minor Version Compatibility, ONNX Runtime built with CUDA 11.8 are compatible with any CUDA 11.x version; ONNX Runtime built with CUDA 12.8 require CUDA 12.8 or newer… ONNX Runtime built with cuDNN 8.x is not compatible with cuDNN 9.x, and vice versa. You can choose the package based on CUDA and cuDNN major versions that match your runtime environment (e.g., PyTorch 2.3 uses cuDNN 8.x, while PyTorch 2.4 or later uses cuDNN 9.x)." Install page (`https://onnxruntime.ai/docs/install/`, accessed 2026-09-29): "The default CUDA version for onnxruntime-gpu in pypi is 12.x since 1.19.0. For previous versions, you can download here: 1.18.1, 1.18.0."

**Consequence:** staying on `onnxruntime-gpu==1.18.0` (CUDA 11.8 / cuDNN 8) is the only zero-friction pairing with torch 2.3.0+cu118 (cuDNN 8.7.0, MEASURED). Upgrading ORT to ≥1.19 PyPI default means CUDA 12 + cuDNN 9 while torch still links cuDNN 8 in the same process → DLL-major clash risk in one interpreter (DOC: cuDNN 8/9 mutually incompatible; ORT CUDA EP doc "Compatibility with PyTorch"/"Preload DLLs" sections exist precisely for sharing torch's CUDA/cuDNN DLLs).

### 1.3 torch CUDA wheels (Windows, cp312)

Source: `https://download.pytorch.org/whl/cu118/torch/` index (accessed 2026-09-29): `cp312-cp312-win_amd64` wheels exist for `torch 2.2.0+cu118 … 2.7.1+cu118` (2.7.1 is the last cu118 build listed). **2.3.0+cu118 is on the official index** (consistent with the installed venv). Newer torch on cu118 therefore exists (2.4.1/2.5.1/2.6.0/2.7.1) if a torch upgrade is ever needed without moving to CUDA 12.

### 1.4 torch.compile / inductor on Windows — locally disproved for this stack (MEASURED)

Probe (shared venv, 2026-09-29): `torch.compile(nn.Conv2d(...), backend='inductor')` on a trivial model fails with
`RuntimeError: Dynamo is not supported on Python 3.12+` (torch 2.3.0+cu118); `find_spec('triton')` is `None`.
**torch.compile/inductor is not usable on Python 3.12 + torch 2.3.0 at all** (not a Windows-specific gap — dynamo rejects the interpreter). Making compile usable requires torch ≥ 2.4 (which raises the cuDNN-9 question for CUDA 12 builds) plus triton on Windows. **Recommendation: exclude `torch.compile` from the option space until the torch/CUDA pairing is deliberately re-decided.**

### 1.5 DirectML

Source: `https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html` (accessed 2026-09-29): "Note: DirectML is in sustained engineering. DirectML continues to be supported, but new feature development has moved to WinML for Windows-based ONNX Runtime deployments." DML needs Windows 10 1903+, works across GPU vendors (page lists Intel Haswell+ iGPU, NVIDIA, Qualcomm Adreno 600+). The page documents no INT8/quantized-model configuration and no fp16 switch; PyPI `onnxruntime-directml` cp312-win_amd64 wheels stop at 1.24.4 (§1.1). **Role here: portability fallback only. On the RTX 3060 it would be strictly slower than CUDA EP and is in maintenance mode upstream.**

### 1.6 TensorRT

Sources: `https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html` and `https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/engine-compatibility.html` (accessed 2026-09-29).

- ORT↔TRT matrix (ORT TRT EP page): **ORT 1.18 → TensorRT 10.0, CUDA 11.8 or 12.0–12.6**; ORT 1.19 → TRT 10.2; 1.20 → 10.4; 1.21 → 10.8; 1.22 → 10.9 (CUDA 12 only from 1.22).
- Engine cache invalidation (ORT TRT EP page, verbatim triggers): "model changes … ORT version changes … TensorRT version changes … Hardware changes. (Engine and profile files are not portable and optimized for specific Nvidia hardware)". Caching "can help reduce session creation time from minutes to seconds"; `trt_engine_cache_enable/path`, `trt_timing_cache_enable/path`, `trt_engine_hw_compatible` ("Maximize engine compatibility across Ampere+ GPUs"), `trt_builder_optimization_level` (default 3; "levels below 3 do not guarantee good engine performance, but greatly improve build time"), `trt_fp16_enable`, `trt_int8_enable`, `trt_int8_calibration_table_name` (for non-QDQ models) are the documented knobs.
- NVIDIA Engine Compatibility page: "By default, TensorRT engines are compatible only with the version of TensorRT used to build them" (opt-in `VERSION_COMPATIBLE` for forward-compat within a major, "version-compatible engines can be slower"); "TensorRT also records the compute capability (major and minor versions) in the plan and checks it against the GPU on which the plan is being loaded. If they do not match, the plan will fail to deserialize"; `HardwareCompatibilityLevel::kAMPERE_PLUS` relaxes the check at some throughput/latency cost; "Engine files are executable artifacts that contain compiled CUDA tactics. Deserialize only engines you built yourself…".
- **Driver-change note (pitfall correction):** neither source lists a driver update as a documented engine-invalidation trigger — the documented triggers are model, ORT-TRT, TensorRT version, and hardware changes. "Driver change invalidates engines" is **not supported by these official sources**; the real operational hazards are ORT/TRT upgrades and GPU swaps. [INFERENCE] a driver update can still change tactic availability in *new* builds and is worth re-measuring after any driver bump, but cached engines are not documented to break on it.

### 1.7 Quantization / precision docs

Source: `https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html` (accessed 2026-09-29):
- Two representations: **QOperator** (operator-oriented: `QLinearConv`, `MatMulInteger`, …) and **QDQ** (tensor-oriented: `DeQuantizeLinear(QuantizeLinear(t))` between original ops; static QDQ nodes carry scales/zero-points).
- "In general, it is recommended to use dynamic quantization for RNNs and transformer-based models, and static quantization for CNN models." "Quantization is not a loss-less transformation. It may negatively affect a model's accuracy." Calibration methods: MinMax / Entropy / Percentile. "it is best to perform model optimization during pre-processing instead of during quantization".
- QDQ is the format TRT consumes for INT8 (ORT TRT page: `trt_int8_calibration_table_name` exists "for non-QDQ models", i.e. QDQ models carry their own params).

Source: `https://onnxruntime.ai/docs/performance/model-optimizations/float16.html` (accessed 2026-09-29): fp16 conversion halves model size and "can … improve performance on some GPUs. There may be some accuracy loss…"; a **Mixed Precision** tool exists to keep selected ops in float32 (the standard remedy when detection heads degrade).

### 1.8 Ultralytics export

Source: `https://docs.ultralytics.com/modes/export/` (accessed 2026-09-29): `dynamic=True` supported "for TorchScript, ONNX, OpenVINO, TensorRT, CoreML, and MNN exports"; `simplify=True` (onnxslim) default; `opset` pinning supported; `workspace` (GiB) for TensorRT; `nms`: `None` exports **raw predictions for external NMS**, `True` embeds NMS where supported (export-time `conf` default 0.25, `iou` 0.7, `max_det` 300 freeze into the graph), `False` selects the NMS-free head where available; `half`/`int8` flags are deprecated in favour of a `precision` argument (`16`, `8`; mixed precisions only for some formats). Vendor claim on that page ("up to 5x GPU speedup with TensorRT and 3x CPU speedup with ONNX or OpenVINO") is marketing, not our measurement.

### 1.9 Paddle / TFLite relevance on Windows (PyPI JSON, accessed 2026-09-29)

- `paddlepaddle` (CPU) latest 3.3.1; Windows cp312 wheels only up to `3.0.0rc1`. `paddlepaddle-gpu` latest 2.6.2; Windows wheels stop at 2.5.0 and **cp310 or older** — no Python 3.12 Windows GPU wheel. 
- `tflite-runtime` latest 2.14.0; Windows wheels only up to 2.5.0 (cp38 max). `ai-edge-litert` (LiteRT) has Windows cp312 wheels at 2.1.2.
- **Assessment:** irrelevant for this stack — the models are YOLO ONNX + a torch SlowFast checkpoint; ORT and torch cover them. Paddle/TFLite would add a third inference runtime with no Python 3.12 Windows GPU story. Do not adopt.

---

## 2. Option comparison table (feeds R-02; "expected speed/memory" are expectations, not measurements)

| Option | Expected speed / memory | Parity & accuracy risk | Compatibility evidence (URL + 2026-09-29) | Install / rollback complexity | What WT-16 must measure |
|---|---|---|---|---|---|
| **A. Status quo: ORT CPU EP 1.18.0** (registered baseline) | Person median 135.6 ms, weapon 696.5 ms per dirty-checkout claim; CPU RAM only; intra_op=2 per session (`yolo_onnx.py:18-37`) | None (fp32 reference) | PyPI `onnxruntime` cp312-win_amd64 1.18.0 exists (§1.1) | Trivial: `select_onnx_runtime.py --device cpu`; wheel sha256 pinned in script | Baseline full-pipeline medians incl. CUDA-free completed inference, cold vs warm |
| **B. ORT CUDA EP 1.18.0** (currently installed) | Dirty-claim: person 24.0/25.7 ms, weapon 43.0/40.3 ms at 30 fps full-pipeline (UNVERIFIED, §7); isolated speedups 4.94×/27.18× are REGISTERED but not full-pipeline | fp32 → raw/decoded parity passed in the earlier isolated experiment (REGISTERED); full-pipeline parity unproven | CUDA EP doc 1.18.x↔CUDA 11.8/cuDNN 8.x "Available in PyPI" (§1.2); matches torch cu118/cuDNN 8.7.0 (MEASURED) | `select_onnx_runtime.py --device cuda` — hash-pinned wheel, automatic rollback wheel obtained **before** uninstall, fresh-process provider check; guard refuses mixed CPU+GPU dists (§6.1) | Completed inference **with CUDA sync** (torch.cuda.synchronize / ORT run is sync at fetch), cold vs warm, CPU-vs-GPU parity on identical fixtures + checkpoints, VRAM per camera process, G-13 cold-start |
| **C. ORT TensorRT EP (1.18 ↔ TRT 10.0)** | Typically ≥ CUDA EP on detection nets; engine cache turns "minutes to seconds" session creation (DOC) | fp16/INT8 engine modes add parity risk; subgraph partitioning (TRT fallback to CUDA/CPU per node) makes latency bimodal | TRT EP matrix: ORT 1.18→TRT 10.0, CUDA 11.8/12.0-12.6 (§1.6); `TensorrtExecutionProvider` is already listed by the installed wheel (MEASURED) but the TRT **runtime libs** must exist on the box — listing ≠ working | No wheel change (same `onnxruntime-gpu`); needs TRT 10.0 install + engine cache dir; rollback = provider list without TRT. Engines non-portable across ORT/TRT/hardware (DOC) → cache must be cleared on those changes | First-session engine build time, cached-session time, engine file sizes, per-inference CUDA-synced latency, CPU/CUDA-EP parity of outputs, behavior on `trt_engine_cache_enable` |
| **D. ORT DirectML (onnxruntime-directml)** | Slower than CUDA EP on NVIDIA; runs on any DX12 GPU | Float-path only per docs; operator coverage gaps can silently fall back | DirectML EP doc "sustained engineering / new feature development has moved to WinML" (§1.5); wheels cp312-win_amd64 ≤ 1.24.4 (§1.1) | Different distribution (mutually exclusive wheel family) — same switch-script pattern would apply; rollback = reinstall chosen ORT dist | Only if CUDA path becomes untenable; then latency + parity vs CPU |
| **E. fp16 (ORT fp16 conversion or `trt_fp16_enable`)** | ~2× memory for weights; some GPU speedup (DOC is deliberately vague: "some GPUs") | Real accuracy risk on detection heads (decode/exp/sigmoid paths; small-object scores); NaN/Inf in fp16 exp ranges; ORT fp16 doc admits "accuracy loss" and ships a Mixed-Precision block-list tool | §1.7 | Offline model transform (new .onnx artifact); rollback = keep fp32 model + hash switch | Box/score parity vs fp32 on a labelled fixture set: per-class AP delta, score distribution drift, near-threshold flip rate (0.45/0.55 thresholds), NaN scan |
| **F. int8 (ORT quantization QDQ static)** | Largest speed/memory win on conv nets; QOperator recommended away from TRT | "not a loss-less transformation" (DOC); needs calibration data (we have **no** domain calibration set — F-40 artifact absent); small-object recall is the classic casualty | §1.7 (QDQ vs QOperator; static for CNNs) | Offline quantize + calibration pipeline (new tooling); rollback = fp32 artifact | Only after E passes: same parity suite + ECE/NLL on held-out; must not proceed on synthetic calibration data (R-03/R-04 policy) |
| **G. torch.compile / inductor (violence model)** | Would help SlowFast conv3d if it ran | n/a | **Blocked**: `RuntimeError: Dynamo is not supported on Python 3.12+` (MEASURED on torch 2.3.0+cu118); no triton installed | n/a until torch ≥ 2.4 + triton-on-Windows decision (cuDNN-9 implications, §1.2) | Not in scope for WT-16 |
| **H. Ultralytics export rework (weapon ONNX)** | Minor; current raw-head + external NMS is the lean variant | Re-export changes tensors; must re-pin class order (6 classes) and NMS contract (runtime-map §3.3) | §1.8 (`dynamic`, `simplify`, `nms=None` semantics) | New ONNX artifact + hash; rollback = current `weapon_yolo.onnx` (sha256 96991cd5…) | Only if dynamic shapes are needed; byte-compare decode outputs old vs new export |
| **I. Paddle / TFLite runtimes** | n/a | n/a | No Python 3.12 Windows GPU wheels (§1.9) | n/a | Excluded |

---

## 3. Export paths (detail)

- **Weapon ONNX is a raw-head export.** Input `images [1,3,640,640]`, output `output0 [1,10,8400]` = 4 box + 6 class channels, `nms: False`, `end2end: false` (REGISTERED, runtime-map §3.2) — i.e. Ultralytics `nms=None` semantics: external NMS in `yolo_onnx.py` (class-aware greedy, IoU 0.5, before border clipping). 103.6 MB fp32 → **mid-size YOLO ≈ 26 M params** [INFERENCE]. This is the *good* export shape: NMS thresholds stay runtime-tunable (`weapon_threshold` in TOML), unlike `nms=True` exports that freeze `conf`/`iou`/`max_det` at export time (§1.8).
- **Static vs dynamic shapes:** all models run fixed 640×640 (YOLO) / 32-frame windows (SlowFast). Static shapes let CUDA EP/TRT pick single tactics; `dynamic=True` only pays off if input size must vary, and for TRT it requires optimization profiles (extra engine build time; ORT TRT page has a "Dynamic Shape Profiling" section for `trt_profile_*` shapes). **Recommendation: keep static 640; do not re-export for dynamic.**
- **torch.onnx legacy vs dynamo:** legacy `torch.onnx.export` (TorchScript trace) is what produced usable exports historically and works on this Python. The dynamo exporter (`torch.onnx.dynamo_export`) shares torch dynamo's Python-version constraints; given the measured Dynamo block on Python 3.12 (§1.4), treat dynamo export as unavailable on this stack until torch is upgraded [INFERENCE from the same limitation; not separately probed]. **Do not churn exports: both current ONNX files satisfy the runtime contracts.**
- **TRT engine build time:** first session build "minutes to seconds" improvement via caches (DOC). Budget the G-13 cold-start against first-build or ship pre-built engines — but engines are ORT/TRT-version + GPU specific (§1.6), so pre-built engines are not part of a clean-checkout story; a cache directory outside the repo with recorded hashes is the workable pattern.
- **Re-export trigger list (nothing else justifies one):** input-size change, class-taxonomy change, NMS-in-graph requirement, or a measured export-level bottleneck. 

## 4. Process topology & IPC (detail; feeds R-01)

Current (REGISTERED, runtime-map §1.1): one `spawn` inference process **per camera**, each owning all three models; frames enter via `mp.Queue(maxsize=3)` of `FramePacket` (max-side 640 BGR ≈ 0.66 MB raw per frame, pickled by `mp.Queue`), results leave via `mp.Queue(maxsize=30)`; evidence ring `deque(maxlen=600)` and per-alert post queue 360 stay in the API process.

| Topology | CUDA context cost | IPC cost | Failure isolation | Assessment |
|---|---|---|---|---|
| **One process per camera (current)** | Each process builds its own CUDA context + ORT/torch arenas — roughly 0.5–1.5 GB VRAM per process [INFERENCE, unmeasured] and duplicated weights (violence 149 MB fp32 file + 2 YOLOs) | Pickle+pipe copy per frame; ~20 MB/s per camera at 30 fps [INFERENCE]; drop-on-full at frame queue (`except queue.Full: pass`, runtime-map R-2, no counter) | Strong: a wedged camera cannot freeze the others; matches the documented R-01 rationale "CUDA isolation" | **Retain for 1–2 cameras** (the demo shape). VRAM math stops working around 3+ concurrent cameras on 12 GB if the violence path lands on GPU in every process |
| Pooled workers (N cameras → M<N model processes) | Fewer contexts; one copy of each model | Frames must hop twice (capture→pool, pool→render) or a shared-memory ring; more coupling | Weaker; a pool crash affects several cameras | Keep as **contingency for ≥3 cameras**; requires SharedMemory ring (below) to not lose the win |
| Threads in the API process | One context | Near-zero copy | None — one GIL/CUDA failure takes down everything; also breaks the B-1 "API must stay importable" discipline | **Reject** for models; threads remain fine for capture/render (current design) |

- **IPC options:** (a) current pickle-through-`mp.Queue` — simple, measured in production shape, ~1 copy + serialize per frame; (b) `multiprocessing.shared_memory` (py3.8+) ring of 2–3 preallocated 640×640×3 buffers + a tiny metadata queue — one memcpy, no pickle for pixels; (c) memory-mapped numpy file — persistent but racy on Windows without careful locking. **Recommendation:** keep (a) until WT-16 measures its actual per-frame cost on this box; adopt (b) only if IPC time is a measurable fraction of end-to-end latency (WT-15 deliverable: instrument copy+queue time separately).
- **Queue sizing & drop policy (3 / 30 / 360 / 600, REGISTERED):**
  - frame_queue 3 + drop-newest (`queue.Full: pass`) is a *freshness* policy — correct for live detection, but the drop is invisible (runtime-map R-2). Add a drop counter to health (S-08 scope) before tuning sizes.
  - result_queue 30 lets the render thread batch-consume ≤30 results per render tick (pipeline_render `_pull_mp_results`) — decision layer then votes once per distinct observation id (D-6), so backlog does not multiply alerts, only staleness. 30 at 30 fps ≈ 1 s of slack; reasonable.
  - evidence 600 = 5 s window at 30 fps per camera (max-side 960 frames) + post-alert queue 360 = 12 s at 30 fps (wired for 5 s deadline). These are storage/RAM costs, not GPU; keep.
  - **Drop policy change worth testing (WT-16):** drop-*oldest* (latest-wins) at the frame queue instead of drop-newest, since the consumer wants the freshest frame; measure decision staleness (`inference_sample_time` age) both ways.
- **Startup / warmup (G-13 ≤ 60 s):** worker constructs violence → weapon → person and only then sets `ready_event` (V-09). Registered violence load alone is 3020 ms (revision `6fb3bcac…`); the untracked `AI_SENTINEL_VIOLENCE_WARMUP_AT_LOAD` flag exists but defaults off (runtime-map §4.2). With GPU: add CUDA context creation (~hundreds of ms per process [INFERENCE]) + first-inference cuDNN/cuBLAS autotune (our provider options pin `cudnn_conv_algo_search: "HEURISTIC"` — the right default to avoid EXHAUSTIVE first-run stalls, DOC: EXHAUSTIVE is the ORT default). **WT-16 must separate: process spawn → model load → first completed inference → first live frame with detection active (the G-13 clock).** If TRT EP is ever tried, engine build time dominates this budget unless cached.

## 5. Scheduling & memory budget (one RTX 3060, 12 GB)

- **Model scheduling:** person + weapon are small YOLOs; violence (SlowFast, 32×224×224 window per registered report) is the heavyweight. In the current per-camera process all three serialize on one stream per process. Options: (i) keep serialized (simplest; per-frame tri-model latency is what WT-16 will measure); (ii) overlap person/weapon (ONNX) with violence (torch) on separate CUDA streams — ORT CUDA EP supports `user_compute_stream`/`use_ep_level_unified_stream` (DOC, CUDA EP config options) but our code doesn't set them; cross-process concurrency is the poor-man's overlap today. **Do not add streams before measurements show idle GPU during the violence call** (WT-16: timeline of the three model calls per frame).
- **Batch vs per-frame:** batch-1 is correct for live latency; batching only helps file/demo throughput and would inflate window latency for SlowFast. Keep batch-1.
- **Memory budget (the "8+ GB risk" analysis):** the violence checkpoint is 149 MB on disk (≈37 M fp32 params) — the *file* is small; the risk is activations + workspaces: SlowFast on (1,3,32,224,224) produces large intermediate maps, cuDNN algorithm search can reserve multi-GB workspaces (`cudnn_conv_use_max_workspace`), and ORT CUDA EP's arena (`gpu_mem_limit` default effectively unlimited, `arena_extend_strategy` powers-of-two growth — DOC) grows per process. With N camera processes each holding torch+CUDA+ORT contexts on one 12 GB card, **N=2 with GPU inference in both is the honest ceiling until VRAM is measured** (WT-16: `torch.cuda.max_memory_allocated`, ORT `device` memory stats, and `nvidia-smi` per-process). The registered "two integrated GPU runs failed to sustain active inference" episode (wt-01 PLAN R-02/R-05) is exactly the failure mode to watch; its root cause is still open.
- **Power/clocks:** sustained 30 fps multi-model load can thermally throttle; if WT-16 sees FPS drift over a soak, record `nvidia-smi -q -d PERFORMANCE` (clocks, throttle reasons) before/after; pinning clocks (`nvidia-smi -lgc`) is a lab-only knob, not a deployment recommendation [INFERENCE].
- **Violence model on GPU across processes:** if cameras > 1 and violence runs on GPU in every process, weights + activations multiply. A single shared violence process (pooled topology row in §4) is the fallback; alternatively keep violence on CPU per process and GPU only for the two YOLOs (the registered configuration) — that hybrid is precisely what the dirty-checkout claim (§7) seems to have changed, and must be measured end-to-end.

## 6. Pitfalls register

1. **ORT CPU/GPU wheel namespace clash.** `onnxruntime`, `onnxruntime-gpu`, `onnxruntime-directml` are different distributions that all own the `onnxruntime` Python package; installing two leaves mixed DLLs and non-deterministic provider loading. `scripts/select_onnx_runtime.py` (untracked operator file, 83 lines) encodes the right discipline: refuses to proceed when both are installed, verifies wheel sha256 against pinned values before touching anything, downloads the **rollback wheel first**, uninstalls, installs from local wheelhouse with `--no-index --no-deps`, validates in a fresh process (fresh process avoids Windows DLL locks), and on failure restores the previous wheel. It is validated for Windows x64 / Python 3.12 only and pins `1.18.0`. Any ORT upgrade must extend this script's `WHEELS` table with new pinned hashes — never pip-install ad hoc.
2. **cuDNN 8 vs 9 DLL mixing.** torch 2.3.0+cu118 carries cuDNN 8.7.0 (MEASURED); ORT GPU builds ≥1.18.1/1.19 default to cuDNN 9 (§1.2). One process importing torch and ORT must have a single cuDNN major. Staying on `onnxruntime-gpu==1.18.0` (cu118/cuDNN8) is the documented-compatible pairing (ORT CUDA EP doc explicitly frames it as "PyTorch 2.3 uses cuDNN 8.x").
3. **TensorRT engine invalidation — correct the folklore.** Documented invalidation triggers: model change, ORT change, TensorRT version change, hardware change (§1.6). NVIDIA additionally hard-fails deserialization on compute-capability mismatch. A **driver update is not a documented trigger** (the assignment's example pitfall is not supported by the official sources we cite); the everyday hazards are ORT/TRT upgrades and GPU swaps. Operational rule: treat the engine cache as disposable and hash-keyed (model sha + ORT ver + TRT ver + GPU name), never authoritative.
4. **fp16 on detection heads.** ORT's own fp16 doc concedes accuracy loss and ships a mixed-precision block-list tool; detection decode heads (`exp`/`sigmoid` on box deltas and class logits) are numerically the fragile part [INFERENCE]. Because our decision thresholds (0.45/0.55) sit on calibrated-ish scores, even small score drift changes alert behavior. Any fp16 step requires the parity harness first (WT-16 parity section) and per-op block-listing of the head as the first remedy.
5. **int8 without domain calibration data is policy-violating.** R-03/R-04 forbid pseudo/synthetic labels as evaluation truth; `model_calibration.json` is absent (F-40). Do not quantize on generic COCO-style calibration and call it safe.
6. **ORT TensorRT provider listed ≠ TensorRT working.** The wheel lists `TensorrtExecutionProvider` (MEASURED) but TRT 10.0 runtime libraries must be installed and compatible (§1.6). Selecting the provider without libs fails at session creation — always fall back to CUDA EP with an explicit health state (SC-10 spirit).
7. **Timing discipline.** Launch timing is meaningless on CUDA; the campaign already mandates completed-inference timing with CUDA synchronization (PLAN.md measurement note, citing `docs.pytorch.org/tutorials/recipes/recipes/benchmark`). Any WT-16 harness that reports "ms" without sync is invalid.
8. **Revision discipline.** Every number in `bench/results/**` and the dirty-checkout docs belongs to revision `6fb3bcac…` or to uncommitted local changes. Comparisons must re-measure both sides in one run.

## 7. Unverified claim register

| Claim | Source | Status |
|---|---|---|
| "GPU ONNX Runtime is the measured selected runtime… two matched full-pipeline trials sustained 30 FPS… person 135.6→24.0/25.7 ms, weapon 696.5→43.0/40.3 ms… raw/decoded parity passed… CUDA node execution confirmed" | Uncommitted dirty-checkout `docs/PLAN.md` (R-02/R-05 paragraph) + `docs/ISSUES.md` performance row + `docs/RUNBOOK.md` runtime section, read 2026-09-29 | **UNVERIFIED for this campaign.** Not in git at the pinned commit; not in registered `bench/results/**`. WT-16 must reproduce or refute with completed-inference CUDA-synced timing, cold vs warm, and CPU-vs-GPU parity on identical fixtures/checkpoints. |
| Isolated GPU speedups 4.94× (person) / 27.18× (weapon); raw/decoded CPU parity; CUDA node execution in profile | Registered evidence (wt-01 PLAN R-02/R-05) | REGISTERED (revision `6fb3bcac…`) — explicitly *not* full-system throughput |
| "Two integrated GPU runs failed to sustain active inference" → rolled back to CPU ORT | Registered evidence (same) | REGISTERED; **root cause open** — the top risk for re-promoting GPU (see §5) |
| DirectML INT8/fp16 support specifics | — | Not documented on the DML EP page we read; treated as unsupported-unknown, irrelevant to the NVIDIA path |

## 8. Recommendation — R-01 / R-02 update proposal (with risks)

**R-01 (process topology) — retain, instrument, cap.**
Keep one inference process per active camera (the implemented topology) for the 1–2 camera demo shape; keep `spawn`; keep camera-local decision state. *Changes to pair with WT-15/16 work:* (a) expose frame-queue drop counts and result-queue depth in health (currently invisible, runtime-map R-2/R-7); (b) measure IPC copy+queue cost and only then consider a SharedMemory ring; (c) write down the ≥3-camera rule: pool the violence model into one shared process (or keep it on CPU per process) before adding cameras — VRAM per context makes naive N-process GPU inference infeasible on 12 GB.
*Risks:* pooled fallback is unmeasured; SharedMemory on Windows needs strict slot ownership to avoid torn frames; per-process contexts can still be the integrated-run failure mode (open root cause).

**R-02 (export/acceleration) — measured promotion of ORT CUDA EP 1.18.0, everything else staged behind parity gates.**
1. Candidate runtime: `onnxruntime-gpu==1.18.0` (CUDA EP) + torch 2.3.0+cu118 for violence — the only ORT/torch pairing whose CUDA/cuDNN majors are documented-compatible (§1.2) and already installed. Promotion **blocked** until WT-16 reproduces full-pipeline CUDA-synced measurements and output parity on the pinned fixtures; the dirty-checkout 24/43 ms numbers stay labeled unverified until then.
2. Install/rollback stays exactly the `scripts/select_onnx_runtime.py` flow (hash-pinned wheels, rollback-first, fresh-process validation). It lives only in the dirty checkout today — **someone must commit it** (proposal: WT-13/WA hygiene owner; see handoff) because R-02 references it.
3. TensorRT EP: the second experiment (same wheel, `trt_engine_cache_*` on a hashed cache dir), only after (1) passes and only with a budgeted first-build; expected upside is real but so is the operational surface (engine invalidation, TRT 10.0 dependency).
4. Precision: fp32 default. fp16 only behind the parity harness with head block-listing; int8 QDQ deferred until real calibration data exists (R-03/R-04).
5. torch.compile excluded (Python 3.12 Dynamo block); Ultralytics re-export excluded (current raw-head/external-NMS contract is the right one); Paddle/TFLite excluded (no viable Windows/Python 3.12 GPU story).

**Explicit risks of the recommendation:** (i) the previously failing *integrated* GPU runs are unresolved — promotion may re-trip them; the plan assumes WT-16's harness captures the failure signature (per-stage timings + health states) if it recurs; (ii) 24/43 ms may not reproduce (different fixtures, revision drift) — the decision must survive that outcome (fall back to registered CPU config); (iii) cuDNN 8 pinning blocks ORT security/feature upgrades until torch is also upgraded — accepted for campaign horizon, revisit at R-09; (iv) CUDA context memory per camera process bounds concurrency at ~2 GPU-inference cameras on 12 GB.

## 9. WT-16 measurement protocol (what the harness must produce)

1. **Completed-inference timing with CUDA sync** per model (person/weapon/violence): p50/p95, n≥300 samples per model per config; separate pre/post-processing from inference; report cold (first 5) vs warm (rest).
2. **Full-pipeline** run (capture→inference→render→decision) at 30 fps file fixtures: end-to-end `processing_latency_ms`, decision staleness (`inference_sample_time` age), frame drops per queue; CPU-EP vs CUDA-EP on **identical fixtures, checkpoints, and thresholds**, same session.
3. **Parity vs accuracy:** raw/decoded output parity (max abs diff, box IoU match rate at fixed NMS params) CPU vs GPU; then the fp16 gate only if pursued: per-class score drift + near-threshold flip rate at 0.45/0.55.
4. **Cold-start budget (G-13):** t=0 spawn → model load (already 3020 ms violence alone) → first completed inference → first frame displayed with active detection; target ≤ 60 s total.
5. **Memory:** `torch.cuda.max_memory_allocated`, ORT device arena, `nvidia-smi` per-process VRAM with 1 and 2 camera workers; system RAM headroom (16 GB shared with dashboard/evidence pipeline).
6. **TRT add-on (only after 1–5 green):** first-session build time, cached-session time, engine cache size, output parity vs CUDA EP.
7. **Stability:** 60-min soak (G-14) with FPS drift + throttle-reason capture (§5).

## 10. Handoff

**To WT-15 (runtime/IPC work, S-01):** §4 table and queue analysis; instrument per-stage timings and drop counters first (the `select_onnx_runtime.py`-style rigor: measure before changing); SharedMemory ring is conditional on measured IPC cost; ≥3-camera pooling rule from §8-R-01.
**To WT-16 (measurement):** the §9 protocol; treat §7 claims as hypotheses; pin wheel/model hashes in every report (`onnxruntime-gpu 1.18.0`; `person_yolo.onnx` 3fafb13e…e60b8; `weapon_yolo.onnx` 96991cd5…75aef; `best_model.pt` 2c8222d3…20d01).
**To WT-13 (hygiene/infra):** `scripts/select_onnx_runtime.py` is R-02's install/rollback path but is **untracked in the dirty checkout** — needs a committed home + tests, with the wheel-hash table kept authoritative; also the `.runtime-wheels` cache dir must stay untracked/ignored.

**Gaps / limitations (honest):** no inference benchmark was run in this task (research-only by assignment); `torch.onnx.dynamo_export` was not separately probed (inference from the Dynamo/Python-3.12 block); DirectML fp16/INT8 behavior is undocumented on the page we read; TRT runtime libraries on this box were not checked (provider listed ≠ working, §6.6); the integrated-GPU-run failure root cause remains open and is the biggest single unknown behind §8; wt-03's reconciled blueprint was absent at writing time; "expected speed/memory" cells in §2 are expectations — the only hard performance numbers in this document are the UNVERIFIED dirty-checkout claims (§7) and REGISTERED revision-`6fb3bcac…` figures, each labeled as such.

## Sources (all accessed 2026-09-29)

1. https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html — ORT/CUDA/cuDNN build matrix, minor-version compatibility, cuDNN 8-vs-9 incompatibility, provider options (`cudnn_conv_algo_search`, `gpu_mem_limit`, `arena_extend_strategy`, `enable_cuda_graph`, `user_compute_stream`).
2. https://onnxruntime.ai/docs/install/ — PyPI CUDA 12 default since 1.19.0; 1.18.0/1.18.1 CUDA 11.8 downloads; PyTorch-compatible CUDA/cuDNN sharing.
3. https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html — ORT↔TRT↔CUDA matrix (1.18→TRT 10.0), engine/timing caches and invalidation triggers, `trt_builder_optimization_level`, `trt_engine_hw_compatible`, `trt_fp16_enable`/`trt_int8_enable`, dynamic-shape profiles.
4. https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/engine-compatibility.html — default single-version engine compatibility, `VERSION_COMPATIBLE`, compute-capability plan check, `kAMPERE_PLUS`, "engines … contain compiled CUDA tactics" warning.
5. https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html — "sustained engineering", WinML successor, Windows 10 1903+ requirement.
6. https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html — QOperator vs QDQ, static-vs-dynamic guidance, calibration methods, accuracy-loss warning.
7. https://onnxruntime.ai/docs/performance/model-optimizations/float16.html — fp16 benefits/accuracy-loss caveat, Mixed Precision block-list tool.
8. https://docs.ultralytics.com/modes/export/ — `dynamic`/`simplify`/`opset`/`workspace`/`nms` semantics, deprecated `half`/`int8` flags.
9. https://pypi.org/pypi/onnxruntime/json · https://pypi.org/pypi/onnxruntime-gpu/json · https://pypi.org/pypi/onnxruntime-directml/json — cp312-win_amd64 wheel existence per version (queried programmatically).
10. https://download.pytorch.org/whl/cu118/torch/ — cp312-win_amd64 cu118 wheels 2.2.0–2.7.1.
11. https://pypi.org/pypi/paddlepaddle/json · https://pypi.org/pypi/paddlepaddle-gpu/json · https://pypi.org/pypi/tflite-runtime/json · https://pypi.org/pypi/ai-edge-litert/json — Windows wheel availability for the Paddle/TFLite relevance check.
12. Local probes (2026-09-29, shared venv, commands in §0/§1.4): ORT/torch/provider/DLL/cuDNN introspection; `torch.compile` Dynamo block; `nvidia-smi` GPU/driver query.
