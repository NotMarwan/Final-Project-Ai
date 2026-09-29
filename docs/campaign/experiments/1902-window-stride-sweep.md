---
authority: scoped
non_authoritative: true
---

# EXP-1902 Window/stride re-derivation (R3) and G-04 latency arithmetic

| Field | Value |
|---|---|
| Worktree / branch | `wt-19` / `codex/sentinel-19-violence-eng` |
| Requirement link | R3 (WT-06 §6 rec. 3, §7.3) → F-08, G-04, G-07 |
| Baseline revision | `e86d34b5d16abcc133ad3470c8d135d00b2423d4` |
| Weights | `best_model.pt` sha256 `2c8222d3…20d1` |
| Env | RTX 3060 12 GB, FP32, CUDA-synced, 15 iters/cell, RESOURCE-LOCK held by WT-19 |
| Source mode | synthetic 30 fps stamp streams (validity) + random windows (cost) — **no accuracy claim** |
| Artifact | `exp1902-sweep.json` |

## Hypothesis
Window length and stride are the dominant levers on glass-to-alert latency (WT-06 §1.3/§5.2); a shorter
window should buy G-04 headroom at some accuracy cost. The sweep must report the real feasible space.

## Measured results (all numbers measured this session unless marked arithmetic)

| window | stride | feasible on shipped SlowFast | inference median ms | floor + inference s | G-04 p50 (1.2 s) met before fusion | window-valid rate (clean 30 fps) | (disordered stream) |
|---|---|---|---|---|---|---|---|
| 16 | 4/8/16 | **NO** | — | — | — | 1.000 | 0.311 |
| 32 | 4 | yes | 55.0 | **1.62** | no | 1.000 | **0.000** |
| 32 | 8 | yes | 55.1 | **2.16** | no | 1.000 | 0.000 |
| 32 | 16 | yes | 56.5 | **3.22** | no | 1.000 | 0.000 |
| 64 | 16/32 | **NO** | — | — | — | 1.000 | 0.000 |

Infeasibility errors (measured):
* `window 16`: `input image (T: 4 H: 7 W: 7) smaller than kernel size (kT: 8 kH: 7 kW: 7)` — slow-pathway pool.
* `window 64`: `Sizes of tensors must match except in dimension 1. Expected size 9 but got size 33` — pathway concat.

Latency budget arithmetic, `window 32 @30 fps` (explicit, per WT-06 §5.2):
* window span `31/30 = 1.033 s` = **86 %** of the G-04 p50 budget (1.2 s) and 52 % of p95 (2.0 s);
* stride quantisation `stride/30` s: 0.133 (s4) / 0.267 (s8) / 0.533 (s16);
* EMA ramp: one extra stride (alpha 0.45, smoothing only starts after `_counter > window_size`);
* N-of-M (`confirm_n 2` of `confirm_m 3`, WT-20's policy): up to `2 × stride/30` s;
* measured model inference: 55–56 ms (≈4 % of the floor);
* ⇒ implied floor before fusion/render: **1.62 s (s4) / 2.16 s (s8) / 3.22 s (s16)**.

Window-integrity (G-07) behaviour measured on a stream with 5 %-class clock disorder (every 23rd stamp
pulled back 0.5 s): for `window 16` 31 % of windows remain valid; for `window 32/64` **0 %** — a single
non-monotone stamp invalidates every overlapping window. Clean streams: 1.000 in all cells.

Overlap variant (R3's "one overlap variant"): `window 32 / stride 16` with a K=2 ensemble over consecutive
completed windows (16-frame offset = 50 % overlap). 0 extra model forwards (see EXP-1903).

## Success criteria (set before the run)
Each grid cell reports time-to-detection-relevant arithmetic, measured inference cost, and window-valid
rate; the decision rule from WT-06 §7.3 (G-04 p50 while maximising G-03, not regressing G-02) is applied.

## Failure criteria / rollback
If no cell meets G-04 p50, the honest answer is "the model/config must get faster", not "the budget moved".
Both the window-size configurability and the integrity assessment are additive and default-preserving
(`window 32` default; parity proven in EXP-1904).

## Verdict — **adapt**
* The window is **not a free parameter** for the shipped engine: the pytorchvideo slowfast_r50 pathway
  geometry pins it to **32** (16 and 64 both fail structurally). The intended `window 16` cell of R3's grid
  is impossible without changing the architecture and retraining.
* Consequently **G-04 p50 ≤ 1.2 s is unreachable with the shipped engine at any feasible window/stride**:
  the window span alone consumes 86 % of the budget and the floor-before-fusion is ≥ 1.62 s. Even G-04 p95
  (2.0 s) is met only at stride 4 (1.62 s), and only before fusion/render/transport cost.
* Stride remains the only free temporal lever (cost ≈ constant, 55–56 ms across strides; the latency
  difference is quantisation + EMA + decision votes). Choosing the operating cell is a **cross-slice
  decision** (G-04 vs G-03 tension) and is proposed to WT-20/Main with these numbers.
* Accuracy per cell and TTD per cell: **NOT MEASURED** — blocked on WT-12 fixtures (no positives with
  independent onset labels secured; negative suite not yet committed).
