---
authority: scoped
non_authoritative: true
---

# WT-12 — Evaluation data and methodology (protocol)

| Field | Value |
|---|---|
| Worktree | `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12` |
| Branch | `codex/sentinel-12-eval-data` |
| Baseline commit | `e86d34b5d16abcc133ad3470c8d135d00b2423d4` |
| Owns | S-20 `bench/**`, `docs/campaign/eval/**` |
| Authority | scoped, non-authoritative (campaign rule) |
| Tooling | `bench/eval/contracts.py`, `bench/eval/metrics.py`, `bench/eval/evaluate.py`, `bench/fetch_fixtures.py` |
| Truth source | `docs/campaign/eval/12-fixture-manifest.json` (validated input; labels = publisher annotation or independent human review ONLY) |

This protocol defines how AI Sentinel detection quality is measured so that
G-02 (negative suite), G-03 (positive detection), G-04 (time-to-detection) and
WT-16/18/19/20/22 verification share one set of denominators. Every metric below
carries sample counts and denominators; every unmeasurable metric is reported
with an explicit reason, never as zero.

## 0. Truth discipline (binding)

1. **Label provenance** must be `publisher` (source-dataset annotation) or
   `independent-human`. Model output, pseudo-labels and synthetic data can NEVER
   establish evaluation truth (`bench/eval/contracts.py` rejects them;
   `bench/calibrate.py` enforces the same rule for calibration inputs).
2. **Pre-registration**: the operating threshold, matching tolerances and slice
   definitions are fixed BEFORE results are inspected. Threshold retuning is a
   separate, declared experiment (EXP-##), otherwise every change "passes" by
   moving the threshold.
3. **Source mode**: no camera device exists in this environment. All runs are
   `file-media` (or `webcam-synthetic`), labeled as such. A `live` record is
   rejected by the contract validator. File-media windows are never reported as
   live capture integrity.
4. **Revision discipline**: every measured run records code SHA, model hashes
   (SHA-256 of each `.pt`/`.onnx`), preprocessing, decision config, dataset and
   split, environment and source mode (`report.json` schema below).
5. **Stubs**: through `bench/runtime.py`, absent `go2rtc_bridge` /
   `openrouter_reporting` modules are auto-stubbed (SC-10); measurements through
   stub adapters say so. Offline scoring (`bench/eval/score_fixtures.py`) runs
   the models directly and is adapter-free.

## 1. Metric definitions

Time base: all times are clip-relative seconds derived from the runtime's
capture/observation timestamps (SC-6 monotonic clock mapped onto the clip
timeline). Alert `time_s` is the decision-confirmation time of the alert, not
the display time.

### 1.1 Frame-level

- Grid: frame samples at `1/fps` (fps from `media.fps`); a sample takes the
  score of the **latest window covering it** (`max start_s`); samples without a
  covering window are `unevaluated` and leave every denominator.
- Label: positive iff the sample time lies in a labeled positive interval
  (`labels.frames`); with clip-level labels only, the whole clip of a positive
  fixture is one interval — the coarser granularity is recorded in the manifest
  (`labels.frames: null`), not hidden.
- Reported at the fixed threshold: TP/FP/TN/FN, precision, recall, F1, and
  all-point interpolated **AP** over frame scores (needs both classes; otherwise
  `null` with reason). Detector mAP/AP50 requires box-level ground truth
  (`labels.boxes`); where absent, AP50 is reported `unavailable`
  ("no box-level ground truth in fixtures"), never estimated from clip labels.

### 1.2 Window-level

- Unit: one temporal window (32 frames, stride = run config; effective stride
  derivable from `windows[].start_s` deltas). Window label = positive iff ≥50% of
  its span overlaps labeled positive time.
- Reported: TP/FP/TN/FN, precision, recall, F1, AP over window scores.
- **Window integrity** (G-07 companion): `valid`, `frames_collected` vs
  `frames_required`, `span_s` vs nominal — reported per run, not mixed into
  quality metrics.

### 1.3 Event-level (operator-facing)

- Ground-truth events: labeled positive intervals (merged). `onset_known` only
  when an **independently labeled onset** exists (`labels.onset_s`).
- Alert↔event matching: greedy, earliest alert first; an alert matches an event
  iff `onset − match_before_s ≤ alert_time ≤ offset + match_after_s` (defaults
  `match_before_s=0`, `match_after_s=5`); each alert and event matches at most
  once.
- Reported:
  - **event recall** = matched events / total events, with a missed-events list;
  - **alert precision** = matched alerts / total alerts;
  - **false alerts** = unmatched alerts (detail rows: fixture, alert, time,
    `pre_onset` flag). Alerts before the onset of their clip's event are counted
    as false AND flagged `pre_onset` (pre-onset control: context-driven firing);
  - **false alerts per camera-hour** = false alerts / labeled-negative
    observation hours (total fixture duration minus labeled positive intervals
    across the evaluated fixtures). This is the alarm-load metric; balanced-clip
    accuracy alone is never reported as deployment behavior;
  - **time-to-detection** = matched alert time − labeled onset (only when
    `onset_known`): count, p50, p95. With no onset labels in the fixture set,
    time-to-detection is **unmeasurable** and reported as such (G-04 stays open).

### 1.4 Counting (WT-22 path)

Inputs: track rows (`tracks[]`) vs `labels.counts` (`visible_persons` at
`sample_times_s`, `unique_persons`, `events`, optional `failure_modes`).

- **Visible count** per labeled sample time: |distinct `track_id` with a row
  within ±0.25 s| vs labeled `visible_persons` → MAE, RMSE, bias, exact-match
  rate (denominator = labeled sample count).
- **Unique count** per clip: distinct track ids vs labeled `unique_persons` →
  absolute error.
- **Event count** per clip: track births (first appearance of an id) vs labeled
  `events` → absolute error.
- **Failure taxonomy** (id-switch / occlusion / re-entry / merge / split):
  aggregated from `labels.counts.failure_modes` per tag with the mean absolute
  visible-count error of tagged fixtures. Counting failure modes are classified
  by the labeler; the evaluator only aggregates.
- **Identity ground truth is absent by annotation type**: the planned fixture set
  (KTH action labels) carries no MOT-style per-person identity annotations
  across frames. **HOTA and IDF1 on real footage are UNMEASURABLE with this
  suite** — unavailable because of the annotation type, not because downloads are
  pending. `labels.counts.unique_persons` supports unique-count evaluation only,
  never identity tracking metrics. No-GT tracking-health diagnostics (id churn,
  dropout/recovery, merge/split suspicion) are reportable as health signals and
  must never be presented as tracking accuracy. Any synthetic-fixture HOTA
  number is synthetic-only evidence.

### 1.5 Per-class detection metrics (weapon path, WT-18)

- Clip-level: per detection class, max class score per fixture vs the fixture's
  clip label → TP/FP/TN/FN, precision, recall, AP at the fixed threshold.
- Box-level (AP50): greedy IoU≥0.5 matching at labeled frames
  (±0.25 s). Detections outside labeled frames are excluded from denominators —
  stated in the output. Without `labels.boxes`, AP50 is unavailable.

## 2. Split discipline (leakage prevention)

- Splits: `train` / `val` (=dev) / `calibration` / `test` / `regression-only`.
  Calibration and test are disjoint sessions (G-06 input requirement); policy
  selection (e.g. N-of-M) happens on `val` only; `test` is reported once after
  selection is frozen.
- **Session/clip independence**: the independent unit is the session
  (`session_id`; for KTH, the subject). All clips of one session sit in one
  split — enforced by `bench/eval/contracts.py` (raises on straddle).
- **Duplicate content**: media SHA-256 must be unique across all fixtures
  (enforced). Duplicate/adjacent-frame leakage rule: any two clips derived from
  the same source recording must sit in the same split with a guard gap of at
  least one window (≥32 frames / 1 s) — for the current single-clip-per-file
  fixtures this reduces to the session rule.
- **Pretraining overlap**: if Kinetics/UCF-style pretraining data is ever used,
  record it and exclude overlapping content from test sets.
- Bootstrap resampling is done over independent units (session preferred, clip
  fallback), never over adjacent frames/windows.

## 3. Difficult-condition slices

Every fixture carries `difficulty_tags`; the evaluator reports every metric per
tag slice plus `all`, each with `fixtures_n` and the fixture-id list. Tags used
by the secured set: `low_resolution`, `static_camera`, `staged_single_person`,
`out_of_cctv_domain`. Planned tags for future fixtures: `motion_blur`,
`low_light`, `occlusion`, `distance`, `compression`. Empty slices are omitted,
never zero-filled.

## 4. Uncertainty

- Cluster bootstrap over independent units (`--bootstrap-unit session|clip`),
  B=2000 resamples default, fixed seed (default 20260929), percentile 95% CIs.
- Report `estimate`, `ci95_low`, `ci95_high`, `resamples_with_value`, unit count
  and unit ids. With <2 independent units the CI is `null` (point estimate only)
  — never a fake interval.
- Metrics are always reported with raw counts and denominators next to them.
  Small-n sets (current fixtures are small) are labeled as such in the report's
  `limitations` by the caller.

## 5. Run commands

```powershell
# 0) environment: use the campaign venv interpreter (the `python` stub is broken)
$PY = "C:/Users/PCD/Downloads/Final Project AI Sentinel/venv/Scripts/python.exe"

# 1) acquire fixtures (rights statement is re-checked at acquisition; aborts if changed)
& $PY -m bench.fetch_fixtures --acquire --actions walking,handwaving,boxing,handclapping `
    --media-root C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12-fixtures `
    --write-manifest docs/campaign/eval/12-fixture-manifest.json

# 2) validate manifest (+ media hashes)
& $PY -m bench.eval.contracts --manifest docs/campaign/eval/12-fixture-manifest.json --verify-media

# 3) score fixtures with the CURRENT models (GPU run: hold RESOURCE-LOCK first).
#    ANCHOR = two passes (Main's ruling 2026-09-29); each pass = one clean lock window.
#    Pass 1 (windows + decision alerts + scoring exports; weapon/person rows ABSENT
#    by construction and reported as unmeasured, never zero):
mkdir C:/Users/PCD/Downloads/jobs/sentinel-campaign/RESOURCE-LOCK   # + owner.txt inside
& $PY -m bench.eval.score_fixtures --manifest docs/campaign/eval/12-fixture-manifest.json `
    --output-dir bench/results/campaign-baseline-2026-09-29-anchor-pass1/outputs `
    --frame-stride 10000 --device cuda --lock-held
rmdir C:/Users/PCD/Downloads/jobs/sentinel-campaign/RESOURCE-LOCK   # release when done
#    Pass 2 (weapon detections + person counting rows; cadence 25th frame; run id
#    anchor-pass2; same manifest/splits; cadence recorded in report.preprocessing):
mkdir C:/Users/PCD/Downloads/jobs/sentinel-campaign/RESOURCE-LOCK   # + owner.txt inside
& $PY -m bench.eval.score_fixtures --manifest docs/campaign/eval/12-fixture-manifest.json `
    --output-dir bench/results/campaign-baseline-2026-09-29-anchor-pass2/outputs `
    --frame-stride 25 --device cuda --lock-held
rmdir C:/Users/PCD/Downloads/jobs/sentinel-campaign/RESOURCE-LOCK   # release when done
#    Cadence-consistency rule (binding): any compared runs must share the same
#    sampling cadence; a different cadence is a separate diagnostic, not a baseline.

# 4) compute protocol metrics (threshold fixed BEFORE inspecting results)
& $PY -m bench.eval.evaluate --manifest docs/campaign/eval/12-fixture-manifest.json `
    --outputs bench/results/campaign-baseline-2026-09-29/outputs `
    --report bench/results/campaign-baseline-2026-09-29/eval-report.json `
    --threshold 0.45 --bootstrap-unit session --bootstrap-resamples 2000 --seed 20260929

# 5) self-tests of the evaluation tooling (synthetic outputs -> known metrics)
& $PY -B -m pytest bench/eval/test_eval.py -q -p no:cacheprovider
```

## 6. Report schema (comparison anchor for WT-16/18/19/20/22)

`bench/results/<run>/report.json` records:

- `code`: git SHA + branch of the run;
- `models`: per-model class + SHA-256 of weights;
- `preprocessing`: resize/normalization/window assembly as executed;
- `decision_config`: thresholds, N-of-M, cooldown (SC-2 `decision_config`);
- `dataset`: manifest path + manifest SHA-256 + splits evaluated + fixture ids;
- `environment`: python/package versions, GPU/driver;
- `source_mode`: `file-media` (always, in this environment);
- `adapter_state`: stub or real `go2rtc_bridge`/`openrouter_reporting`;
- `runProvenance`: when a run consumes WT-13's `sentinel-metrics-export/1`,
  the provenance block carries `fixture_id` AND `source_sha256` (manifest
  hashes) so a metrics export and the recorded outputs join by hash — a stale
  or mismatched export is rejected at report time, never silently paired;
- `eval`: the `wt12-eval-report/1` payload from `bench.eval.evaluate`.

Counting caveats that MUST accompany any counting number (WT-22):

1. Person/weapon rows are frame-SAMPLED (`--frame-stride`, default every 5th
   frame) — visible-count comparisons must state the cadence, or sampling looks
   like detector recall.
2. KTH boxes are ~10-30 px tall at 160×120: IoU association is unstable at that
   scale; id-churn/drift/area-jump counters are rate diagnostics at small-box
   regimes, not failures, and synthetic-regime thresholds do not transfer.
3. Count semantics: `labels.counts.visible_persons` counts labeled persons at
   sample times; `unique_persons` is clip-level; neither is identity GT.

`eval-report.json` (`wt12-eval-report/1`) carries `slices.{all,<tag>}` with
`frame_level`, `window_level`, `frame_level_by_class`, `event_level`,
`counting`, `bootstrap`, `unavailable_metrics` and `operating_point`.

## 7. Known gaps of the current fixture set (2026-09-29)

- `negative/hugging`, `negative/handshakes`, `negative/phone_use`: no lawful
  public corpus (see `unavailable_categories` in the manifest). G-02's six-class
  suite CANNOT be closed with these fixtures; the honest denominator is "the
  secured negative suite".
- `positive/violence_with_independent_onset`: none secured → time-to-detection
  (G-04) unmeasurable.
- `positive/weapon_visible_close_range`: none secured yet (licence verification
  of image-level candidates pending) → weapon metrics rest on clip labels only.
- Domain: all secured clips are KTH auxiliary domain (160×120, static camera,
  staged). Same-scene/auxiliary-domain numbers are not deployment predictors;
  cross-dataset evidence (WT-06 §4.3) shows collapses to chance.
