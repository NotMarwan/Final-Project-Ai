---
authority: scoped
non_authoritative: true
---

# EXP-1908 False positives on the secured negative suite (KTH walking) × 3 violence configs

**Pre-registered before any result was inspected** (2026-09-29, WT-19). Written while the RESOURCE-LOCK was
held by WT-16, i.e. before the measured run.

| Field | Value |
|---|---|
| Worktree / branch | `wt-19` / `codex/sentinel-19-violence-eng` (commits through `45a7136`) |
| Requirement link | G-02 (no / few confirmed false alerts) — **FP figure on the secured negative suite only**; R4 (ensemble), item 5 (motion gate) |
| Fixtures | WT-12 `kth-walking-person01..12` (12 clips, manifest `wt-12` branch `codex/sentinel-12-eval-data` commit `b14bbbb`; media root `C:\Users\PCD\Downloads\jobs\sentinel-campaign\wt-12-fixtures`, `kth/*.avi`, 160×120 @25 fps, publisher-labelled negatives, subject-level splits train 2 / val 2 / calibration 2 / test 6) |
| Weights | `backend/best_model.pt` sha256 `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01` |
| Model config | window **32** (the only feasible window, EXP-1902), scoring window step 32 frames (non-overlapping) via `window-scores` |
| **Threshold (fixed before inspection)** | **0.45** (= the committed `config/thresholds.toml` violence threshold). Declared retunes only; no post-hoc choice. |
| Source mode | file-media (no camera exists) |
| Lock | RESOURCE-LOCK acquired atomically for the whole run; release = dir removed + broadcast |

## Hypotheses
1. **H1 (shipped default, K=1, gate off)** yields a non-zero FP count on this suite (the score is an
   uncalibrated logit-margin sigmoid and the suite is a *different domain* from the demos).
2. **H2 (ensemble K=3, `max`)** does not increase FP windows at fixed threshold 0.45 relative to H1, while
   raising score stability (per the R4 design premise).

## Candidate configs (identical otherwise)
| ID | ensemble | motion gate |
|---|---|---|
| C1 | K=1 (shipped default) | off |
| C2 | K=3, agg `max` | off |
| C3 | K=1 | `block`, floor 1.0 |

## Metric definitions (fixed before the run)
* **FP window** = a scored window with `violence_conf >= 0.45` on a fixture the manifest labels `negative`.
* **FP clip** = a clip with ≥1 FP window (per-clip denominator = 12 clips; also reported per split).
* **Windows scored** = total windows across clips (denominator for the window rate); per-clip counts reported.
* **FP per camera-hour** = FP windows ÷ (total scored footage hours), stated with the footage total.
* Reported by WT-12's `bench.eval.evaluate` (bootstrap by session, 2000 resamples, seed 20260929) — its report
  is the primary artifact; my own counts are a cross-check.

## Success criteria (numeric, set before inspection)
* Every config produces a report with explicit denominators (clips = 12, windows scored, footage hours) and a
  bootstrap interval; no metric is reported without its denominator.
* H2 verdict: adopt K=3 only if FP windows(C2) ≤ FP windows(C1) **and** median per-window score on negatives
  does not increase by more than 0.02 absolute.
* C3 verdict: adopt the gate as a *shippable option* only if FP windows(C3) < FP windows(C1) with the same
  window count (no window dropped) — otherwise keep `off` and say so.

## Failure criteria / rollback
If any config shows a positive-class claim, a missing denominator, or a threshold different from 0.45, the
result is rejected and re-run. All three configs are defaults-preserving: shipping nothing from this card
leaves C1 behaviour unchanged (parity proven in EXP-1904).

## Explicit non-claims (binding wording)
* This is **NOT** G-02 closure: the suite is the *secured negative suite (KTH aux domain, walking-only)*.
  WT-12's manifest declares hugging / handshake / phone-use as unavailable GAPS — the six-class suite is not
  closable with these fixtures.
* **Time-to-detection stays UNMEASURED** — no independently labelled onsets exist (boxing positives are
  staged, clip-level).
* No positive-class recall/accuracy statement of any kind.

## Command sequence (copy-paste; each measured step inside the lock)
```
# 1) model runs (my harness; lock held)
python backend/tests/wt19_sweep_harness.py --out docs/campaign/experiments/artifacts/exp1908-winscores-C1.json \
  window-scores --device cuda --videos C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12-fixtures/kth \
  --window 32 --max-frames 700 --ensemble-k 1 --threshold 0.45
# C2: --ensemble-k 3 ; C3: --ensemble-k 1 --motion-gate block --motion-floor 1.0   (-> -C2.json / -C3.json)
# 2) adapter to WT-12 outputs contract (CPU)
python backend/tests/wt19_sweep_harness.py to-fixture-outputs \
  --manifest C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12/docs/campaign/eval/12-fixture-manifest.json \
  --scores docs/campaign/experiments/artifacts/exp1908-winscores-C1.json \
  --out-dir docs/campaign/experiments/artifacts/exp1908-outputs-C1 --run-id wt19-exp1908-C1
# 3) WT-12 scorer (run from wt-12; writes the report into wt-19 artifacts)
python -m bench.eval.evaluate --manifest docs/campaign/eval/12-fixture-manifest.json \
  --outputs <abs path>/exp1908-outputs-C1 --report <abs path>/exp1908-eval-C1.json \
  --threshold 0.45 --bootstrap-unit session --bootstrap-resamples 2000 --seed 20260929
```

## Pre-flight (offline, no lock, no inference — NOT a measurement)
Run before attempting the measured run, to prove the scoring path works on a negatives-only manifest:
synthetic zero-score records for all 12 fixtures were fed to **WT-12's scorer** (`python -m bench.eval.evaluate`
with `--threshold 0.45 --bootstrap-unit session --bootstrap-resamples 200 --seed 20260929`). It completed and
emitted `wt12-eval-report/1` with `fixtures_evaluated` = all 12, `splits_evaluated` = calibration/test/val,
frame-level `{tp: 0, fp: 0, tn: 384, fn: 0, n: 384, grid_frames: 6742}`, and an `unavailable_metrics` block
naming `time_to_detection_s` ("no evaluated fixture carries an independently labeled onset; clip-level
publisher labels cannot time the alert"), `counting`, and `ap50_by_class`. Artifact:
`artifacts/exp1908-preflight-evaluator-report.json` (label: PRE-FLIGHT, synthetic zeros).

Consequence: the gap run will produce a scorer-native FP report with denominators, and the TTD non-claim is
enforced by WT-12's own tooling rather than by prose — exactly the honesty requirement Main restated.

## Result — MEASURED 2026-09-29 (~02:23–02:27, RESOURCE-LOCK held by WT-19 via bounded atomic retry after WT-21's hand-off; GPU idle at acquisition)

**Arbitrator's labelling (Main, 02:2x arbitration vs WT-14).** The apparent 02:23–02:27 overlap with WT-14's
window is resolved as approximate ledger timestamps on both sides (filesystem fact: the dir was absent at
02:27:19 per WT-24's successful mkdir). Ruling applied here verbatim:
* the **FP window/frame counts below are deterministic and stand** (they are a function of the weights, the
  frames and the fixed threshold, not of machine speed);
* the **GPU timings stand as measured** — WT-14's concurrent batch was CPU-only encode/decode + mode probes,
  so no competing GPU workload existed;
* the **CPU decode phases of this run are labelled POTENTIALLY CONTENDED** (WT-14's CPU batch overlapped);
  no latency claim in this card depends on them.
* Lesson recorded for the handoff: acquisition/release stamps must come from the script clock, not wall
  estimates (this card's own header timestamp is a wall estimate and is therefore approximate).

Run: `window-scores` over all 12 manifest fixtures (media present 12/12, 160×120 @25 fps, 269.7 s total ≈
0.0749 h of footage), non-overlapping 32-frame windows → **206 windows / 6386 grid frames per config**;
then the verified adapter (strict, 0 unmatched) and **WT-12's scorer** (`bench.eval.evaluate`,
session-clustered bootstrap, 2000 resamples, seed 20260929). Artifacts: `exp1908-winscores-C{1,2,3}.json`,
`exp1908-outputs-C{1,2,3}/`, `exp1908-eval-C{1,2,3}.json`, `exp1908-summary.json`.

| Config | window-level FP | frame-level FP | FP windows / camera-hour | clips with ≥1 FP window | verdict |
|---|---|---|---|---|---|
| **C1** K=1, gate off (shipped default) | **9 / 206** | 279 / 6386 | **≈ 120** | **4 / 12** | reference |
| **C2** K=3, `max` | **25 / 206** | 775 / 6386 | ≈ 334 | 6 / 12 | **REJECT** (pre-registered rule) |
| **C3** K=1 + motion gate `block`, floor 1.0 | **9 / 206** | 279 / 6386 | ≈ 120 | 4 / 12 | **no effect → keep gate off** |

Score ranges (smoothed/decision-relevant): C1 0.026–0.700; C2 0.048–0.700; C3 0.000–0.700.
WT-12's difficulty slices (`low_resolution`, `out_of_cctv_domain`, `staged_single_person`, `static_camera`)
are identical to `all` because all 12 fixtures carry all four tags — no slice-level differentiation here.
Scorer-native `unavailable_metrics`: `time_to_detection_s` ("no evaluated fixture carries an independently
labeled onset…"), `counting`, `ap50_by_class`.

### Per-clip detail (C1, the shipped default)
FP windows are concentrated: `person01` 2/17 windows, `person06` 2/13, `person07` 4/14, `person09` 1/21 —
the other 8 clips produced none. The four firing clips span the declared splits (person01 = train,
person06 = calibration, person07/person09 = test), so this is not a split artifact; `person07` (29 % of its
windows) and `person06` (15 %) are the strongest hard-negative candidates for a targeted review
(full table in `exp1908-summary.json`).

### Cross-check at the decision level (WT-20's measurement, not mine — recorded for the level distinction)

WT-20 replayed these streams through the **real decision layer** (commit `4bee457`, reports in their artifacts;
my three input files hash-verified byte-for-byte). Deliberately screened on **non-test** negatives only
(val+train+calibration = 6 clips / 94 windows) so their EXP-20 test evaluation stays unspent:

* **C1 (shipped default): 0 confirmed FPs for all 268 feasible policies at every confirm threshold
  0.45–0.65** — no clip accumulates the required 2 qualifying votes (max non-test window score 0.568).
* **C3: identical to C1** (0/268), matching my "no effect" finding.
* **C2 (K=3 `max`): the decision layer DOES confirm FPs** — at confirm threshold 0.45, 42/268 policies fire
  (150 confirmations), degrading to none only at ≥0.60. Independent decision-level support for rejecting C2.
* Their confidence-weight lever (`confirm_weight_sum`/`gain`, SC-5) restores 0 confirmed FP at the lowest bar
  — first measured evidence those keys buy FP headroom.

**Interpretation I now state explicitly in this card:** my headline **9/206 is a WINDOW-level false-positive
count across all 12 clips and is not a confirmed-alert count.** The per-window and per-alert levels must not
be conflated (the template's frame/window/event separation): at window level the shipped default fires 9
times; through the N-of-M confirmation layer on the non-test subset it produced **zero confirmed alerts**.
Both numbers are honest and they answer different questions — G-02's "confirmed alerts" question is the
decision-level one, which is why WT-20's screen is the right instrument and my card must not claim G-02 either
way.

### Verdicts against the pre-registered criteria
* **H1 CONFIRMED** — the shipped default produces **non-zero false positives on a secured negative suite**:
  9 FP windows on 4 of 12 walking clips (≈120 FP windows per camera-hour at threshold 0.45, on this
  auxiliary-domain footage). This is the first honest FP figure for the violence path; it is *not* G-02
  closure and says nothing about CCTV scenes.
* **H2 REFUTED → C2 REJECTED for default use.** K=3 `max` roughly **tripled** FP windows (25 vs 9) and
  raised the frame-level FP count (775 vs 279) at the same threshold; the pre-registered adoption rule
  (FP(C2) ≤ FP(C1)) fails clearly. Mechanism consistent with the design: `max` over recent windows both
  inflates the score on borderline negatives and holds a high score after the peak passes.
* **C3 NOT ADOPTED.** The motion gate did not remove any of the FP windows (9 → 9), i.e. these false
  positives are *motion-backed* (the walking clips have ample motion). Gate stays `off` by default; the
  implementation remains available for suites where low-motion false triggers are the failure mode.
* **No default behaviour changes ship from this card** — C1 remains the operating point, and that is now a
  measured choice rather than an assumption.

### Honest non-claims (binding wording, restated after results)
This is an **FP figure on the secured negative suite (KTH aux domain, walking-only)** — never G-02. The
six-class suite remains open (hugging / handshake / phone-use declared unavailable by WT-12). **TTD is
unmeasurable** (no independently labelled onsets; the scorer says so itself). No positive-class precision,
recall or accuracy statement is made anywhere in this card — `precision: 0.0, recall: null` in the reports
reflects a negatives-only denominator, not a system claim.

### Follow-ups this measurement motivates (for the record, not claimed as done)
1. Investigate the 4 firing clips' windows (artifact `exp1908-summary.json` lists them) — a per-clip review
   is the cheapest next step toward hard-negative mining (WT-06 R5).
2. Any ensemble aggregator other than `max` (e.g. mean, or max-then-EMA with a shorter memory) must be
   measured against C1 before being considered; `max` is now empirically disfavoured at this operating point.
3. The FP windows are motion-backed, so motion-family levers are exhausted at this operating point.
   **Correction to an earlier draft of this line (credit: WT-22 / TrackingCounting, same session):**
   *person-presence* gating **cannot** fix these four clips either — the suite is KTH *walking*, so a person
   is present, moving and centred in every window by construction; a presence gate would be ~always true on
   exactly the firing windows while adding a new failure mode (suppressing windows where the detector misses a
   person at 160×120, where subjects are ~10–30 px tall). WT-22's tracking thresholds were validated on
   24–40 × 60–80 px synthetic boxes and the person path samples every `person_interval` (default 3) frames, so
   KTH person counts are also unvalidated at that resolution and cannot serve as a discriminator; the
   *defensible* variant, if anyone wants it, is a different claim — suppress alert **escalation** when
   `activeTrackCount == 0` across the whole decision window — and it needs its own pre-registered test.
   Consequently the honest next levers are decision/cascade-side (scene context, per-camera calibration,
   confidence-weighted N-of-M) rather than perception-side, and any of them must be measured against C1 first.
