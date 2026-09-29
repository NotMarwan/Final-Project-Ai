---
authority: scoped
non_authoritative: true
---

# EXP-1907 WT-12 fixture-output adapter + contract verification (slot-9 enablement)

| Field | Value |
|---|---|
| Worktree / branch | `wt-19` / `codex/sentinel-19-violence-eng` |
| Requirement link | WT-12 eval protocol (G-02/G-03/G-04 measurement path); assignment item 6's data gate |
| Contract source | `wt-12` `bench/eval/contracts.py::load_manifest/load_outputs` (commit `a9cb03d`), read-only |
| Lock | **none needed** (CPU-only, offline; no model inference, no measured run) |
| Artifact | `artifacts/exp1907-fixture-output-contract-check.json` |

## Hypothesis
The gap between WT-19's window-score records and WT-12's recorded-outputs contract can be closed with a
tested adapter, so that the post-WT-12 measurement slot (Main's slot 9) becomes a closed, reproducible
pipeline rather than an integration guess — and the field names come from the committed contract, not
from invention.

## Candidate
* `build_fixture_outputs(manifest, scores, run_id)` (pure) + `cmd_fixture_outputs` CLI mode
  (`to-fixture-outputs --manifest --scores --out-dir --run-id [--no-strict]`) in
  `backend/tests/wt19_sweep_harness.py`.
* Mapping (contract names → source): `fixture_id` ← manifest join on `media.path` basename **or** full path
  versus the score record's `clip_id`; `source_sha256` ← manifest `media.sha256`; `source_mode` =
  `"file-media"`; `windows[].start_s/end_s` ← `window_start_timestamp`/`window_end_timestamp`;
  `windows[].violence_conf` ← `smoothed_conf` (the decision-relevant EMA/ensemble output) with
  `ensemble_score` → `calibrated_conf` fallbacks, clipped to [0, 1].
* Contract `runtime_contract.window_integrity_fields` carried per window: `valid`, `frames_collected`,
  `frames_required`, `span_s` — produced by new upstream plumbing so the value is the integrity of **that
  submitted window**, not of the stream at read time (producer change: `process_frame` passes the
  `assess_window_integrity` snapshot into `_infer_window_async`; the four `window_*` keys ride in
  `_completed_window_fields` and `_window_score_history`).
* Additive extras preserved on each window: `raw_conf`, `calibrated_conf`, `smoothed_conf`,
  `logit_margin`, `ensemble_k`, `ensemble_score`, `ensemble_spread`, `motion_energy`, `motion_gated`,
  `window_id`; a `producer` block records code SHA, weights SHA-256, window/stride, ensemble config, motion
  gate, threshold and an explicit `score_semantics` string.
* Strict by default: any scored clip that matches no manifest fixture aborts the CLI (`SystemExit`) so a
  mis-joined run cannot silently produce a partial evaluation set.

## Measured / verified results
Fed synthetic records through **WT-12's real validators** (`load_manifest` + `load_outputs`):

```
validated_records: ["kth-boxing-07", "kth-walking-01"]   (fixture order is WT-12's own sort)
windows_per_record: {kth-boxing-07: 2, kth-walking-01: 2}
unmatched: []
window_field_names: [calibrated_conf, end_s, ensemble_k, ensemble_score, ensemble_spread,
                     frames_collected, frames_required, logit_margin, motion_energy, motion_gated,
                     raw_conf, smoothed_conf, span_s, start_s, valid, violence_conf, window_id]
negative controls (all rejected as expected):
  - tampered source_sha256  -> "carries source_sha256 'ddd…' but the manifest names '114049bf…'"
  - source_mode "live"      -> "no camera device exists in this environment; a 'live' … cannot be accepted"
  - violence_conf 1.4       -> "window.violence_conf must be in [0,1]"
empty manifest -> 0 payloads, 4 unmatched (strict mode therefore fails loudly)
```

Six self-contained unit tests (`backend/tests/test_fixture_outputs_adapter.py`, no cross-worktree
dependency): field mapping + sorting, unmatched reporting, full-path clip ids, degenerate/unscored window
dropping, clipping + `ensemble_score` fallback, and the strict CLI failure path.

Real-manifest join check (run after WT-12 landed batch 1 — KTH walking, 12 clips; artifact
`artifacts/exp1907b-real-manifest-join-check.txt`, still offline/CPU-only, no lock, no inference):

```
manifest fixtures: 12        payloads: 12        unmatched: 0
media present on disk: 12/12 (media_root C:\Users\PCD\Downloads\jobs\sentinel-campaign\wt-12-fixtures)
validated by wt-12 load_outputs: 12
splits: {train: 2, val: 2, calibration: 2, test: 6}
```

So the slot-9 pipeline is joined and contract-clean on the real fixtures; what remains is the measured
model run itself (needs RESOURCE-LOCK) and the accuracy/FP read-out from WT-12's evaluator.

## Success criteria (set before the run)
An emitted record set passes WT-12's own validator with zero contract errors, and the validator is shown to
be genuinely exercised (negative controls rejected).

## Failure criteria / rollback
Any contract violation on emission, or a silent mis-join, rejects the adapter; it is additive (a new CLI
mode) and removing it would not affect the pipeline or prior evidence.

## Verdict — **adopt**
Slot 9 is now executable as three commands: (1) `window-scores` over the fixture media under
RESOURCE-LOCK, (2) `to-fixture-outputs` (CPU, instant, strict), (3) WT-12's
`python -m bench.eval.evaluate --manifest … --outputs <dir> --report … --threshold <pre-registered> …`.
Accuracy/G-02/G-03 remain **unmeasured** until the fixture media complete — this card removes the
*integration* blocker, not the *data* blocker.
