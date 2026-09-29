---
authority: scoped
non_authoritative: true
---
# Comparable measurements carried into the candidate (before/after)

All numbers below were produced by the owning workstream **before** integration and are recorded with
their raw artifacts inside the merged `docs/campaign/**` trees and `bench/results/**`. WT-30 ran **no**
new measurement (see `pending-runs.md`); treat every figure as "measured on that workstream's tree,
environment and denominators" — re-verify on the candidate before quoting.

| Area | Experiment | Artifact (in candidate tree) | Note |
|---|---|---|---|
| CPU→CUDA runtime | EXP-01/02/03 | `backend/…`, `bench/results/campaign-accel-2026-09-29/**`, `docs/campaign/accel/16-inference-acceleration.md` | matched full-pipeline trials; precision gate and TRT probe included |
| Tracking | EXP-2201 ByteTrack vs IoU | `docs/campaign/experiments/2201-bytetrack-vs-iou-baseline.md`, `tracking-eval-report.json` | ByteTrack adopted as the measured default |
| Faces | EXP-21-01 YuNet latency (clean confirm) | `docs/campaign/experiments/21-01-yunet-latency.md`, `artifacts/21-face-detect-confirm.json` | supersedes the contended figures |
| Enhancement | EXP-23-01..04 | `docs/campaign/experiments/23-0*.md` | tier-0 op menu, harness gate, async/GPU budget (enqueue median 0.0016 ms, p95 0.0029 ms, max 0.249 ms; queue bound 16 with 4984 counted drop-oldest evictions at 5000 enqueues — EXP-23-03), tier-1 gated |
| Evidence encoder | E-7 | `docs/campaign/experiments/07-evidence-encoder-opt-in.md` (+ `.results.json`) | NVENC opt-in, default libx264; +3.1 % duration, Chromium playback verified |
| Capture queue | EXP-15.02 / 15.03 | `docs/campaign/experiments/15-02-queue-policy.md`, `15-03-ipc-pickle.md` + artifacts | drop-newest vs latest-wins policy; pickle IPC probe |
| Startup | EXP-15.04 | `docs/campaign/experiments/15-04-startup.md` + artifacts | startup timing |
| Violence FP | EXP-1908 + WT-20 screen | `docs/campaign/experiments/1908-*`, `docs/campaign/experiments/artifacts/exp1908-*`, `wt20-fpscreen-C*.json` | three pre-registered configs on the secured negative suite; WT-20's negatives-only screen |
| Weapon FP | WT-18 runs | `bench/results/wt18-weapon-kth-{boxing,walking,waving}/**` | per-subcategory FP runs with `fp_detections.jsonl` |
| Real-time budget | WT-19 floor | `docs/campaign/experiments/1902-window-stride-sweep.md` | stride-4 floor 1.62 s → **G-04 FAILED WITH EVIDENCE** |

## Rejections and deferrals (kept, not hidden)

- Temporal ensemble K=3 — **REJECTED** (no accuracy gain for the cost).
- SharedMemory IPC — **REJECTED** (EXP-15.03 probe).
- TensorRT on this host — **rejected** (stage-2 probe; see `docs/campaign/experiments/05-trt-stage2-probe.md`).
- fp16 — **deferred** (precision gate).
- CLAHE + denoise combination — **rejected** in the tier-0 op selection (EXP-23-01 menu).
- Tier-1 Real-ESRGAN — **gated/refused** where harness bounds fail; weights are untracked by policy.

## WT-29 independent evaluation on the assembled candidate (measured, exact denominators)

| Result | Measured value | Denominator / setting |
|---|---|---|
| Negative-suite false positives (G-02) | **4 confirmed alerts on negatives**; pistol clip **FP 4/36** | KTH-aux negatives → **47.06 false alerts/camera-hour** |
| Detection recall (G-03) | **0.140 / 0.138 / 2-of-12** | threshold **0.45** (exact denominators as run) |
| First weapon observation latency (G-13) | **46.1 s** | assembled candidate, paced replay |
| Weapon observations completed | **18 completed observations** | mechanism = **cold-start + cadence accounting** (open item RESOLVED) |
| Evidence/enhance suite reproduction (G-07) | **102 passed / 6 skipped** | fresh run; supersedes the earlier 99/6 count (which omitted three suites) |

These rows replace nothing above: the workstream rows remain the owning workstream's own measurements,
and the WT-29 rows are the independent reproduction on the assembled tree. Both sets keep their own
denominators; do not pool them.
