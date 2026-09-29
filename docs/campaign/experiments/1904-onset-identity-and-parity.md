---
authority: scoped
non_authoritative: true
---

# EXP-1904 R7 onset/window identity instrumentation + score parity

| Field | Value |
|---|---|
| Worktree / branch | `wt-19` / `codex/sentinel-19-violence-eng` |
| Requirement link | R7 (WT-06 §6 rec. 7, §7.7) → SC-2/SC-4/SC-6/SC-7, G-04 measurability |
| Baseline revision | primary checkout `e86d34b5…` (READ-ONLY execution, `PYTHONDONTWRITEBYTECODE=1`) |
| Weights | `best_model.pt` sha256 `2c8222d3…20d1` (both revisions) |
| Env | RTX 3060, demo AVIs, RESOURCE-LOCK held by WT-19 |
| Artifacts | `exp1904-winscores-baseline.json`, `exp1904-winscores-branch.json`, `exp1904-window-parity.json`, `exp1904-scores-branch-k1.json`, `exp1904-scores-baseline-k1.json`, `exp1904-parity.json` |

## Hypothesis
Time-to-detection from an independently labelled onset becomes computable iff every observation carries a
monotone window identity plus the window's capture-clock start/end and an onset-candidate marker; the
instrumentation must be additive (SC-2) and must not change any existing score or `captured_at` semantics.

## Candidate (additive only)
`window_status` gains: `window_id` (monotone per completed window), `window_start_timestamp`,
`window_end_timestamp` (same clock domain as the existing window stamps), `onset_candidate_timestamp`,
`onset_candidate_window_id` (first window of the current candidate-positive run; cleared on release),
`ensemble_k/ensemble_score/ensemble_spread`, `motion_energy/motion_gated`, `raw_conf/calibrated_conf/
smoothed_conf/logit_margin/logits`, plus G-07 fields `span_tolerance_seconds/max_gap_seconds/
gap_bound_seconds/integrity_reason`. `_window_score_history` keeps the per-window score sequence for the
WT-20/`bench/calibrate.py` schema. SC-2 forwarding keys are proposed to WT-15 (owner of
`inference_process.py`) — see the handoff doc.

## Measured results
* **Deterministic score parity (baseline vs branch, 12 fixed windows, same weights/device):**
  `raw_conf`, `calibrated_conf`, `smoothed_conf` → **max_abs_delta = 0.0**, `parity_at_1e-4 = true`.
  The scores are non-degenerate (raw margin sigmoid range 0.0051–0.6866), so the parity is not vacuous.
* **Onset tracking works on real footage:** in the deterministic run the candidate-positive run flips match
  `onset_candidate_timestamp` being set at the first positive window and cleared at release
  (e.g. clip 1: window 4 sets onset `3.2 s`, window 5 clears it; clip 3: windows 10–11 keep the onset from
  window 10 at `1.0667 s`).
* **Monotone identity:** observation ids 1..12 across 12 completions (deterministic mode); streaming run
  observation ids 1..7 with `window_id` 1..7.
* **Measured ingress caveat (important for G-01/G-04 comparisons):** streaming identical frames through the
  baseline and branch revisions produced different completed-window counts (baseline probes 5/2/2 per clip,
  branch 3/2/2 in one pair) because a completion only happens on a stride tick when the single-flight
  worker is idle — i.e. ingress completion count depends on feed-vs-inference pacing, not on the revision.
  Parity gates must therefore use the deterministic fixed-window mode; per-camera feed pacing must be
  controlled before quoting G-01/G-04 numbers.

## Success criteria (set before the run)
Additive fields present end-to-end; IDs monotone; baseline scores unchanged (parity); TTD recomputable from
the payload given an independent onset label.

## Failure criteria / rollback
Any score/ID/semantics change other than the additive fields rejects the change; the fields are additive
with defaults and the pipeline keeps `captured_at` (SC-6) untouched.

## Verdict — **adopt**
* Fields and identity tracking work and are parity-neutral. Best-fit onset label in the deterministic run:
  the instrumentation is complete, but **TTD itself remains UNMEASURED**: WT-12 reports no independently
  labelled onset set has been secured (KTH annotations are clip-level, staged single-person action), so
  G-04 stays unmeasurable and is reported as such rather than estimated.
* SC-4 alert-payload mirror fields (`onsetCandidateAt`, `onsetCandidateWindowId`, `violenceWindowId`, …)
  are proposed to WT-20/WT-30 (they own `pipeline_render.py`); no edits made there by WT-19.
