---
authority: scoped
non_authoritative: true
---

# EXP-1905 Perception-level benign-motion rejection (motion gate)

| Field | Value |
|---|---|
| Worktree / branch | `wt-19` / `codex/sentinel-19-violence-eng` |
| Requirement link | item 5 (R5 partial: perception-level half) → G-02, F-07 |
| Baseline revision | `e86d34b5d16abcc133ad3470c8d135d00b2423d4` |
| Weights | `best_model.pt` sha256 `2c8222d3…20d1` |
| Env | RTX 3060, file-media demo AVIs + synthetic static windows, RESOURCE-LOCK held by WT-19 |
| Artifacts | `exp1905-scores-motionblock.json`, `exp1904-winscores-branch.json` |

## Hypothesis
A cheap motion-saliency gate at the perception layer suppresses violence scores on low-motion (benign)
windows, reducing false positives on negative footage, without touching any decision threshold (SC-5).

## Candidate
`_window_motion_energy` = mean absolute gray-level frame difference (0..255, 32×32 gray, consecutive
frames). Gate modes via `AI_SENTINEL_VIOLENCE_MOTION_GATE` ∈ {off, damp, block} with floor
`AI_SENTINEL_VIOLENCE_MOTION_FLOOR` (default off ⇒ zero behaviour change):
* `block` forces the window score to 0 below the floor (marked `motion_gated`),
* `damp` scales the score by `motion/floor`.

## Measured results
* Motion energy on the deterministic demo-AVI windows: 0.472–3.278 (mean 1.647) — real footage separates
  from synthetic static windows (measured 0.000 for constant frames).
* With `block` and floor 1.0 over the streaming demo run: 2 of 7 completions gated (energies 0.745, 0.790
  < floor) → exactly those windows scored 0.0; all other windows unchanged.
* Default `off` preserves the baseline bit-for-bit (parity proof in EXP-1904), so shipping it off is
  risk-free; enabling it is a policy decision requiring the negatives suite.
* Cost: negligible (32 small resizes per window; not separable from the measured 55 ms forward).

## Success criteria (set before the run)
Zero confirmed FPs on the negatives suite (G-02) with no positive-loss on labelled positives.

## Failure criteria / rollback
If the gate suppresses positives (violence onset windows that are momentarily low-motion) it must not ship
enabled; mode stays `off` until measured on the negatives suite.

## Verdict — **adapt** (implementation, default off); effectiveness **UNMEASURED**
The G-02 claim is explicitly **not** made: WT-12's negatives suite was not available during this window
(landing the same day; KTH-based, with hugging/handshake/phone-use classes expected missing). The gate is
therefore reported as *implemented, cost-measured, and reversible*, with the FP effect pending a fixtures run
(command recorded in the handoff). EMA/hysteresis constant re-derivation proposals were sent to WT-20;
decision thresholds remain theirs (SC-5 single authority).
