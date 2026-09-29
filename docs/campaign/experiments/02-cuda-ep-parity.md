---
authority: scoped
non_authoritative: true
---

# EXP-02 CUDA-EP candidate + CPU↔CUDA output parity

- Hypothesis: The same ORT 1.18.0 build on CUDA EP (`use_tf32=0`, `cudnn_conv_algo_search=HEURISTIC`) completes person/weapon inference faster than CPU EP on identical model bytes, identical prepared inputs, identical thresholds, while producing numerically equivalent outputs (fp32) and identical decisions at the 0.45/0.55 thresholds.
- Requirement link: F-09/F-10 provider status; WT-09 §9 items 1+3; R-02 promotion gate.
- Baseline: EXP-01 CPU-EP numbers (same commit `86d7697`, same model hashes `3fafb13e…e60b8` / `96991cd5…75aef`, same fixture manifest, same preprocessing, same decision config, same env). CPU reference run in the SAME session-of-runs as the CUDA candidate (matched measurement, revision discipline respected).
- Candidate: CUDA EP via `yolo_onnx.select_providers(ort, "cuda")`; n=5 cold + 300 warm completed inferences per model; completed-inference timing with `torch.cuda.synchronize()` before every stop stamp (plus ORT sync-at-fetch); parity on the 10 fixed fixture frames: raw max abs diff, decoded match rate at fixed NMS (conf 0.25, IoU 0.5, max_det 300, model space), near-threshold flips at 0.45/0.55 — for the person COCO-80 head (all classes + production class-0 filter) and the weapon 6-class head (all classes).
- Success criteria (defined BEFORE inspecting results): (a) parity: raw max abs diff ≤ 0.01 AND decoded match rate ≥ 0.99 AND zero near-threshold flips at 0.45/0.55; (b) speed: CUDA warm p50 < CPU warm p50 for BOTH models, target ≥1.5× per model.
- Failure criteria / rollback: any parity gate missed → candidate REJECTED regardless of speed (fp32 CPU is the reference; rollback = no change, registered CPU config stands). Speed gate missed for both models → do not promote (keep CPU). Measurement invalid if samples <300 or sync missing.
- Result: **MEASURED** (2026-09-29, same clean lock window + same fixture/models as EXP-01; `raw/raw-person-cpu.json` vs `raw/raw-person-cuda.json`, `raw/raw-weapon-cpu.json` vs `raw/raw-weapon-cuda.json`, parity `raw/raw-parity-person.json` + `raw/raw-parity-weapon.json`):
  - person CUDA: warm p50 **10.55 ms** (p05 9.72 / p95 14.03 / max 21.24, n=300); cold p50 20.16 ms; load 181.9 ms; first inference 247.0 ms → **6.42× vs CPU** (67.70 ms).
  - weapon CUDA: warm p50 **26.02 ms** (p05 25.36 / p95 27.62 / max 65.16, n=300); cold p50 38.79 ms; load 298.3 ms; first inference 305.1 ms → **18.01× vs CPU** (468.58 ms).
  - Parity (CPU vs CUDA, identical model bytes + identical prepared tensors): person raw max abs diff **0.00314**; decoded 50/50 matched (matchRate 1.0), matched IoU min 0.999997, max |score diff| 3e-06; class-0 filtered 47/47 (1.0). Weapon raw max abs diff **0.00171**; decoded 4/4 matched (1.0), IoU min 0.999996, max |score diff| 2e-06. Near-threshold flips at 0.45/0.55: **0** for both models. NMS fixed: conf 0.25 / IoU 0.5 / max_det 300, model space.
  - Harness note (MEASURED): CUDA EP session creation in a fresh process FAILS without torch's CUDA/cuDNN DLLs loaded ("CUDA_PATH is set but CUDA wasnt able to be loaded"); production never sees this because `inference.py` imports torch before any session (ORT "Preload DLLs"/PyTorch-sharing pattern); `bench/accel/harness.build_session` replicates it. Recorded because any standalone CUDA tool must do the same.
- Verdict: **adopt** — all pre-declared gates pass: parity raw ≤0.01 ✓, match rate ≥0.99 ✓ (1.0), zero threshold flips ✓, speed ≥1.5× both models ✓ (6.4× / 18.0×)
- Cold vs warm: separated per config. Completed-inference timing WITH CUDA synchronization (`cudaSyncApplied: true` on CUDA records), never launch timing.
