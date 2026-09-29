---
authority: scoped
non_authoritative: true
---

# WT-12 blueprint delta (S-20 evaluation foundation)

IDs referenced are the reconciled seed registry (`docs/blueprint/index.json`,
wt-03 `27c18d2`). No new IDs allocated (per the orchestrator's reallocation
ruling; integrator assigns from F-58 upward).

| ID | Current status (seed) | Delta proposed by WT-12 | Evidence |
|---|---|---|---|
| S-20 (Bench / measurement harness) | implemented-active | add evaluation capability: rights-checked fixture manifest (`docs/campaign/eval/12-fixture-manifest.json`, schema `wt12-fixture-manifest/1`), evaluation protocol (`docs/campaign/eval/12-eval-protocol.md`), deterministic metrics tooling (`bench/eval/**`) + baseline anchor run under RESOURCE-LOCK (`bench/results/campaign-baseline-2026-09-29/`). Suggested status: `implemented-active (eval-harness-landed)`; tests `bench/eval/test_eval.py` (20) | this branch: a9cb03d, b14bbbb, cbcbbcc + baseline report.json |
| F-07 (Violence inference) | implemented-active | no code change (perception is out of WT-12 scope). Adds EVALUATION evidence: per-window raw scores on rights-checked fixtures (`window_scores.json`, WT-20 schema); scores recorded as `raw_model_score` (uncalibrated softmax) | bench/results/campaign-baseline-2026-09-29/window_scores.json |
| F-08 (Temporal window validity) | implemented-active | no code change. Anchor records `valid`, `frames_collected/frames_required`, `span_s` per window (the runtime_contract window integrity fields) on every fixture | baseline outputs/*.json |
| F-40 (Calibration profile ingestion) | partial (no `backend/model_calibration.json`) | unchanged; ADDS the labeled-score inputs (`clip_scores_max.json` / `clip_scores_mean.json`, publisher labels, calibration/test splits) that make G-06 fitting possible — artifact production remains WT-20's | baseline clip_scores_*.json |
| SC-2 (Inference result schema) | implemented-active | consumed as contract by `bench/eval/contracts.py` recorded-output schema (windows/detections/tracks field names mirror SC-2); additive extras allowed | bench/eval/contracts.py |
| SC-4 (Alert SSE payload) | implemented-active | consumed as contract by the alert replay (decision layer export mapped to `alerts[]`); WT-20's additive keys accepted without rename | bench/eval/score_fixtures.py |
| SC-6 (Timestamp semantics) | implemented-active | honored: fixture times are clip-relative file-frame-index times; pipeline clocks are never subtracted from fixture times (glass-to-alert rule) | 12-eval-protocol.md §1.3 |

Goal-status language for the campaign (G-## live in `docs/PLAN.md`, reported
here for the integrator):

- **G-02** (0 confirmed alerts on ≥20 benign clips incl. hugging/handshakes/
  waving/walking/phone use): the fixture suite provides ≥20 benign clips
  (KTH walking + waving, aux domain) but **cannot close the six-class suite** —
  hugging/handshakes/phone-use have no lawful public corpus (declared in
  `unavailable_categories`). Measured scope is "secured negative suite (KTH aux
  domain)".
- **G-03** (≥90% detection on staged positives): staged positives (KTH boxing)
  land as clip-level labels; no onset labels → clip/window-level recall only.
- **G-04** (time-to-detection): **remains UNMEASURABLE** — no fixture carries an
  independently labeled onset. Never estimated from model output.
- **G-06**: calibration inputs (publisher-labeled scores, split-separated) now
  exist; the artifact itself is WT-20's, and in-domain calibration stays open
  (auxiliary domain only).
