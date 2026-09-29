---
authority: scoped
non_authoritative: true
---

# EXP-1901 Backbone identity reconciliation (SlowFast vs "X3D" vs R(2+1)D)

| Field | Value |
|---|---|
| Worktree / branch | `wt-19` / `codex/sentinel-19-violence-eng` |
| Requirement link | R8 (WT-06 §6 rec. 8, §7.8) → F-07 identity, F-29 wording |
| Baseline revision | `e86d34b5d16abcc133ad3470c8d135d00b2423d4` (primary checkout, READ-ONLY) |
| Weights | `backend/best_model.pt`, 149,344,325 bytes, sha256 `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01` |
| Env | Windows 11, RTX 3060 12 GB, venv Py3.12 / torch 2.3.0+cu118, pytorchvideo hub cache present, RESOURCE-LOCK held by WT-19 |
| Source mode | checkpoint file + synthetic random windows (no camera exists) |
| Artifacts | `exp1901-throughput.json` (sha256 in `SHA256SUMS.txt`), `identity` mode output in the handoff doc |

## Hypothesis
The loaded engine's identity is mislabelled (F-29 claims "X3D"; the class name `X3DViolenceModel` wraps R(2+1)D-18; the runtime map says SlowFast). Making the identity truthful in code/labels, and deciding the engine from measured throughput, removes a documented defect and prevents false capability claims.

## Candidate
- Structural checkpoint identification (`identify_checkpoint`) + truthful `architecture_id`/`architecture_label` on every model class and the pipeline; legacy names kept only as documented string contracts (S-21 dataset profiles, `train_calibration.py`).
- Deleted the no-op `SpatialTransformer` (16,384,230 dead parameters, per-window discarded computation) and the unused `AngleInvariantWrapper`/`preprocess_window_multi_angle` duplicates.

## Measured results

Checkpoint-internal identity (structural, no filename use):

```
{"family": "slowfast", "variant": "pytorchvideo_slowfast_r50",
 "num_classes": 2, "head_dim": 2304, "confidence": "structural-keys"}
```

Checkpoint-internal training provenance (recovered from the state dict; runtime-map §3.6 says UNKNOWN — it is not):
`epoch 1`, `best_f1 0.9337`, `best_balanced_accuracy 0.938`, `best_loss 0.19320`, `git_commit null`,
`manifest_path /content/drive/MyDrive/AI-Sentinel/manifests/violence_data_manifest.jsonl`,
`source_weights_path /content/ai-sentinel/backend/best_model.pt`, lr 1e-4, batch 2, val_ratio 0.15, seed 42,
max_train/val samples 1581/395, `unfreeze_backbone false`, device NVIDIA L4, run start 2026-05-05T23:48:59Z,
output `.../full_finetune/stage4_controlled_20260505_234853`.
Logged val metrics (their split, **not ours, not reproducible here**): accuracy 0.9367, precision 0.9119,
recall 0.9565, specificity 0.9194, f1 0.9337, tp 176 / tn 194 / fp 17 / fn 8 (n=395).
The manifest is not present in this repository; these numbers are metadata, never test truth.

Parameter counts and throughput (RTX 3060, FP32, CUDA-synced, 30 iters, window 32, random windows):

| Engine | params | cold ms | median ms | p05/p95 ms | completed inf/s | preprocess median ms |
|---|---|---|---|---|---|---|
| SlowFast R-50 (shipped checkpoint) | 34,830,282 | 58.7 | 55.5 | 53.5 / 61.8 | 18.01 | 14.8 |
| R(2+1)D-18 "X3DViolenceModel" (`window 16`) | 31,301,151 | 47.5 | 45.8 | 43.9 / 58.1 | 21.73 | 17.5 |
| R(2+1)D-18 "X3DViolenceModel" (`window 32`) | 31,301,151 | 88.1 | 86.7 | 85.3 / 92.6 | 11.53 | 16.4 |
| SlowFast R-50 at `window 16` | — | **INFEASIBLE** | — | — | — | — |

Infeasibility (measured error, not inferred): SlowFast slow pathway requires `T_slow = window/4 >= 8`
(final `avg_pool3d` kernel 8) → `window 16` raises
`RuntimeError: input image (T: 4 H: 7 W: 7) smaller than kernel size (kT: 8 kH: 7 kW: 7)`.
Removed dead `spatial_transformer` parameters: 16,384,230 (state-dict keys stripped on load for legacy
checkpoints; outputs unchanged).

## Success criteria (set before the run)
Identity is structurally verifiable and truthful in labels; measured per-window latency exists for each
engine at equal window length; any engine claim is backed by a number.

## Failure criteria / rollback
If the checkpoint had turned out to be R(2+1)D-native, the truthful identity would have been routed the
other way; the identity helpers are additive and the load path keeps both branches.

## Verdict — **adopt** (engine decision: keep SlowFast)
* The shipped, trained engine is SlowFast R-50 (`pytorchvideo_slowfast_r50`, 2304-d head, 2 classes). It is
  the only engine with weights, and it is **faster** than the R(2+1)D legacy path at `window 32`
  (55.5 ms vs 86.7 ms median) while being the only one that can run `window 32` at all.
* The X3D efficiency claim (4.8x fewer MACs, arXiv 2004.04730, cited from WT-06) does **not** transfer:
  the legacy path is R(2+1)D-18, not X3D, and measures slower here.
* Accuracy comparison SlowFast vs the alternative: **NOT RUN** — no fixture harness yet (WT-12 pending) and
  **no trained R(2+1)D weights exist** in this repository (random-init timing only; labelled as such).
* F-29 wording fix ("Connected to active X3D temporal engine") is proposed to the orchestrator/WT-30;
  S-17 owns `detection_categories.py`.

## Cold vs warm
Separated above (cold = probe + first timed call; warm = 30 CUDA-synced iterations after a warm-up call).
