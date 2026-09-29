---
authority: scoped
non_authoritative: true
---

# WT-19 / S-02 — Violence detection engineering handoff

| Field | Value |
|---|---|
| Worktree | `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-19` |
| Branch | `codex/sentinel-19-violence-eng` |
| Base revision | `e86d34b5d16abcc133ad3470c8d135d00b2423d4` (worktree clean at start; `git status --porcelain` empty) |
| Slice | S-02 (owns `backend/inference.py`, `backend/models/multi_angle_x3d.py`, scoped tests) |
| Inputs consumed | WT-06 `docs/campaign/research/06-violence-research.md` (sha256 `127ac325…a811`), wt-03 seed `docs/blueprint/` (INDEX + index.json), WT-20 decision semantics, WT-12 fixture status |
| Resource window | RESOURCE-LOCK held 2026-09-29 01:56:13 → release (see lock record section) |

## 1. Files changed (owned slice only)

| File | Change |
|---|---|
| `backend/inference.py` | Truthful architecture identity (`identify_checkpoint`, `architecture_id/label`, `architecture_identity()`); configurable `window_size` + ensemble (`ensemble_k/agg`) + motion gate; `assess_window_integrity()` (G-07) extracted and used by `process_frame`; monotone `window_id`; onset-candidate tracking; `_window_score_history`; raw-margin/logits exposure; legacy-tolerant state-dict loading (`_load_compatible`, `_drop_legacy_dead_keys`); dead code removed (`preprocess_window_multi_angle`); legacy print labels fixed |
| `backend/models/multi_angle_x3d.py` | Truthful docstrings + `ARCHITECTURE_ID/LABEL` (it is R(2+1)D-18, not X3D); removed no-op `SpatialTransformer` (16,384,230 dead params) and unused `AngleInvariantWrapper` |
| `backend/tests/test_temporal_window_integrity.py` | **new** — G-07 assertions across window {16,32} × fps {25,30}, tolerance/gap/incompleteness boundaries, pipeline window-id monotonicity |
| `backend/tests/test_ensemble_semantics.py` | **new** — one-vote-per-completion, K=1 legacy parity, onset run semantics, motion gate, checkpoint identity, legacy key handling |
| `backend/tests/test_fixture_outputs_adapter.py` | **new** — WT-19 → WT-12 recorded-outputs mapping (contract names, strict CLI, negative paths) |
| `backend/tests/wt19_sweep_harness.py` | **new** — reproducible measurement harness (identity/throughput/sweep/scores/window-scores/to-fixture-outputs/compare) |
| `docs/campaign/experiments/1901..1907-*.md` + `artifacts/*` | EXP cards + raw artifacts (no multi-MB binaries) |

No SC-1/SC-2/SC-4/SC-5 file was edited (see §3 proposals). No cherry-pick of the SC-10 API fix was needed
(module-level verification only); recorded as not-required for this slice.

## 2. Additive payload field declaration (SC-2 / SC-7 / SC-6)

Producer side (`window_status`, merged by `process_frame`; persisted from the completed window):

| field | type | semantics |
|---|---|---|
| `window_id` | int | monotone, unique per completed window evaluation (starts at 1) |
| `window_start_timestamp` / `window_end_timestamp` | float | first/last sample stamp of the scored window, **same clock domain** as `span_seconds` (monotonic capture for live, media clock for files) |
| `onset_candidate_timestamp` | float \| null | capture-clock stamp of the first window of the current candidate-positive run; null when no run |
| `onset_candidate_window_id` | int \| null | `window_id` where that run started |
| `ensemble_k`, `ensemble_score`, `ensemble_spread` | int/float/float | ensemble size, aggregate score, population std over members (WT-20 covariate) |
| `motion_energy`, `motion_gated` | float/bool | perception motion energy (mean abs gray diff 0..255) and gate state |
| `raw_conf`, `calibrated_conf`, `smoothed_conf` | float | pre-EMA softmax prob, pre-EMA calibrated value, post-EMA value (WT-20 calibration input) |
| `logit_margin`, `logits` | float / float[] | raw pre-temperature margin and the raw logit vector |
| `window_valid`, `window_frames_collected`, `window_frames_required`, `window_span_seconds` | bool/int/int/float | G-07 integrity **of the submitted window** (satisfies WT-12 `runtime_contract.window_integrity_fields`: valid/frames_collected/frames_required/span_s) |
| `span_tolerance_seconds`, `max_gap_seconds`, `gap_bound_seconds`, `integrity_reason` | float/str | G-07 accounting |

SC-7: `violence_observation_id` keeps its meaning — exactly one bump per completed evaluation (verified:
ids 1..N for N completions at K=1/3/5). SC-6: `captured_at` semantics untouched. Legacy consumers use
`dict.get`, so the additions are non-breaking; parity of all existing scores is proven (max_abs_delta 0.0).

## 3. Proposals sent (not edited by WT-19)

* **WT-15 / S-01 (`backend/inference_process.py`)** — forward the fields above into the SC-2 result
  (`violence_window_id`, `violence_window_start_timestamp`, `violence_window_end_timestamp`,
  `violence_onset_candidate_timestamp`, `violence_onset_candidate_window_id`, `violence_raw_conf`,
  `violence_calibrated_conf`, `violence_logit_margin`, `violence_ensemble_k`,
  `violence_ensemble_variance`, `violence_motion_energy`, `violence_motion_gated`) plus
  `observation_kind` ("violence"/"weapon"/"mixed") requested by WT-20 for vote attribution.
* **WT-20 (`pipeline_render.py` SC-4 / decision layer)** — alert mirror keys `onsetCandidateAt`,
  `onsetCandidateWindowId`, `violenceWindowId`, `violenceWindowStartTimestamp`, `violenceWindowEndTimestamp`;
  confirmed their one-vote-per-completion contract and that `ensemble_spread` is available.
* **WT-30 / orchestrator (S-17 file)** — F-29 wording: `detection_categories.py:240-243` says
  "Connected to active X3D temporal engine"; the measured runtime loads SlowFast R-50. Proposed text:
  "Connected to the active SlowFast R-50 temporal engine (2-class head)." (Measured identity: EXP-1901.)
* **WT-20 / Main** — G-04 ruling request: with the shipped engine the implied glass-to-alert floor is
  1.62 s (stride 4) / 2.16 s (stride 8) / 3.22 s (stride 16) before fusion; G-04 p50 ≤ 1.2 s is unreachable
  at any feasible window/stride (EXP-1902).

## 4. Blueprint delta (F-## statuses)

| ID | From → to | Evidence |
|---|---|---|
| **F-07** Violence inference | `implemented-active` → `implemented-active` (contract extended; identity now truthful) | `architecture_identity()`, `identify_checkpoint()`, EXP-1901; new contract fields in §2 |
| **F-08** Temporal window validity | `implemented-active` → `implemented-active` (extracted pure function `assess_window_integrity`, G-07 accounting surfaced; window size configurable) | EXP-1902 validity rates; `test_temporal_window_integrity.py` |
| **F-29** Category capability API | `partial` → `partial` (**wording defect now specified with a measured counter-claim**; fix proposed to S-17) | `detection_categories.py:240-243` vs EXP-1901 identity |
| Suggested new IDs | **RETRACTED** — Main's binding reallocation assigns F-50 = incident capture queue (WT-22), F-51 = best-frame selection (WT-22), F-52..F-55 = WT-23, F-56/F-57 = WT-21, and F-58+ to additional WT-20 calibration/decision items. WT-19 therefore allocates **no** IDs and requests that the integrator register, from F-58 upward, (a) violence onset/window identity instrumentation (SC-2 additive) and (b) temporal ensemble over stride offsets — or fold both into F-07/F-08 contract text if the registry prefers that shape | EXP-1903, EXP-1904 — integrator to assign |

Also relevant to the map: runtime-map §3.6 (dataset provenance UNKNOWN for the shipped weights) is
**superseded** by EXP-1901's checkpoint-internal provenance recovery (manifest path, run config, logged
metrics) — still not verifiable truth, but no longer "no record in the repo".

## 5. Validation performed

| Command | Result |
|---|---|
| `python -m pytest tests/test_runtime_observation_contract.py tests/test_angle_invariance.py tests/test_inspect_model_checkpoint.py tests/test_multi_angle_benchmarks.py tests/test_temporal_window_integrity.py tests/test_ensemble_semantics.py tests/test_fixture_outputs_adapter.py -q` (cwd `backend/`, primary venv) | **59 passed** (19 pre-existing scoped + 40 new) |
| Deterministic parity: `wt19_sweep_harness.py window-scores` on baseline vs branch, then `compare` | `raw/calibrated/smoothed max_abs_delta = 0.0`, `parity_at_1e-4 = true` (12 windows) |
| Adapter contract verification: emitted records fed through WT-12's **real** `load_manifest`/`load_outputs` | 2 records validated, 0 contract errors, `windows[]` field names as emitted; 3 negative controls rejected as expected (tampered `source_sha256`, `source_mode: live`, `violence_conf` > 1) — artifact `exp1907-fixture-output-contract-check.json` |
| `backend/tests/test_fixture_outputs_adapter.py` (6 tests) | passed — mapping, sorting, unmatched reporting, degenerate-window dropping, clipping/fallback, strict CLI failure |
| `wt19_sweep_harness.py identity/throughput/sweep/scores` | artifacts in `docs/campaign/experiments/artifacts/` (measured numbers in EXP-1901..1905) |
| EXP-1908 measured run (12 KTH negatives × 3 configs, threshold 0.45 pre-registered) | C1 window FP 9/206 (frame 279/6386, ≈120 FP windows/camera-hour, 4/12 clips); C2 K=3 max **25/206 (frame 775/6386)** → rejected; C3 gate **9/206** → no effect. Reports: `exp1908-eval-C{1,2,3}.json`, summary `exp1908-summary.json` |
| `npm run docs:sync` + `docs:check` | see commit message / §7 |

Resource-exclusive measurements: all GPU runs executed while WT-19 held RESOURCE-LOCK (01:56:13 onward);
GPU was idle at acquisition (nvidia-smi: 5 % util, 2327/12288 MiB ambient desktop usage — recorded, not a
compute process). Runs before the lock (none of mine; the `identity` mode is deterministic counting/hashing,
not a benchmark) are unaffected.

## 6. Limitations and unmeasured paths (honest list)

1. **The only accuracy-adjacent number that exists is EXP-1908's false-positive measurement on the secured
   negative suite** (KTH walking, aux domain): the shipped default fires 9/206 windows on 4/12 clips at
   threshold 0.45 (≈120 FP windows per camera-hour), and neither tested "improvement" helps (K=3 `max`
   triples it; the motion gate is a no-op on this suite). There is still **no positive-class recall,
   precision or accuracy number** for the violence path, no CCTV-domain number, and no G-02 closure: the
   six-class suite (hugging/handshake/phone-use) remains unavailable, and all earlier accuracy claims
   remain blocked as documented in EXP-1902/1903/1905/1906.
2. **G-04 remains unmeasured end-to-end.** The instrumentation now makes TTD *computable*, but with no
   independent onset labels it is not computed. The arithmetic floors in EXP-1902 are arithmetic, not
   measurements, and exclude fusion/render/transport.
3. **No camera device** → no live-capture integrity claim anywhere; all footage use is file-media and
   labelled as such.
4. **Ingress completion rate is pacing-dependent** (measured): identical frames through baseline and branch
   completed different window counts because the single-flight worker skips stride ticks while busy. This is
   a pre-existing property, now documented; it means G-01/G-04 comparisons need a controlled feed clock.
5. **R(2+1)D legacy path has no trained weights** (random-init timing only) and window 16/64 are structurally
   impossible on the shipped SlowFast — so "X3D adoption" is not a live option without a retrain + data.
6. **`window 32` pinning** was derived from measured runtime errors against the pytorchvideo architecture; a
   different slow-pathway subsampling (e.g. `::2`) was **not** attempted and would invalidate the pretrained
   temporal semantics (would require retraining).
7. Motion gate FP effect and ensemble accuracy effect: not measured (see 1).
8. `docs:check` on this branch is expected to report unregistered scoped documents (SC-9 ruling) — recorded
   verbatim in §7, not worked around.
9. Observed warning in **every** GPU run (both revisions): `UserWarning: Plan failed with a cudnnException:
   CUDNN_BACKEND_EXECUTION_PLAN_DESCRIPTOR ... CUDNN_STATUS_NOT_SUPPORTED` from `torch/nn/modules/conv.py`
   (cuDNN plan fallback). Its isolated timing effect was not measured; all reported numbers use the same
   fallback path on both revisions, so comparisons are like-for-like.
10. `docs:sync` was run and **deliberately not committed**: the regenerated `SOURCE-MANIFEST.json` /
    `CURRENT.md` described 7 files that do not exist in this branch (`backend/_pipeline_ai_deprecated.py`,
    `go2rtc_bridge.py`, `openrouter_reporting.py`, `dataset_manager.py`, `check_model_sha.py`,
    `augmentations.py`, `train_pipeline.py`) and untracked user-local modules — a cross-cutting docs-authority
    change driven by pre-existing staleness (B-6), not by this slice. Integrator action: run `docs:sync` after
    assembly (per the SC-9 ruling the scoped-doc allowlist fix lands from the seed branch).
11. Platform clock nuance reported by WT-13 (2026-09-29): on this venv interpreter `time.monotonic()` /
    `time.time()` are **15.625 ms-quantized** while `perf_counter` is QPC-backed. My pipeline's *live-clock
    fallback* (`captured_at is None`) uses `time.monotonic()`, so that fallback's span/gap tolerances inherit
    15.6 ms granularity — tolerable against a ±10 % tolerance on a 1.033 s window (103 ms), but it is another
    reason the measurement path uses explicit caller-supplied capture stamps (file-media), which is what every
    number in these cards used. No change made to inference.py for this; recorded as a known characteristic.

## 11. EXP-1908 — measured (this slice's only accuracy-adjacent number)

Executed in a hand-off gap (RESOURCE-LOCK acquired by bounded atomic retry after WT-21's release; GPU idle;
dir removed immediately after ~4 min; WT-16 resumed on my release).

**Result (threshold 0.45 fixed pre-registration, 12 KTH walking negatives, 206 windows / 6386 frames per
config, WT-12 scorer with session-clustered bootstrap 2000, seed 20260929):**

| Config | window FP | frame FP | FP windows / camera-hour | clips firing |
|---|---|---|---|---|
| C1 K=1, gate off (shipped) | **9 / 206** | 279 / 6386 | ≈ 120 | 4 / 12 |
| C2 K=3 `max` | **25 / 206** | 775 / 6386 | ≈ 334 | 6 / 12 → **REJECTED by the pre-registered rule** |
| C3 K=1 + motion gate `block` | 9 / 206 | 279 / 6386 | ≈ 120 | 4 / 12 → **no effect, gate stays off** |

Per-clip (C1): person01 2/17, person06 2/13, person07 4/14, person09 1/21 windows; other 8 clean. Firing
clips span train/calibration/test splits, so it is not a split artifact.

**Level distinction (must not be conflated):** 9/206 is a **window-level** FP count across all 12 clips.
WT-20 replayed these streams through the real decision layer on the **non-test** subset (6 clips / 94 windows)
and measured **0 confirmed FPs for all 268 feasible policies** (max non-test window score 0.568), while the
K=3 `max` stream *does* produce confirmed alerts at low confirm thresholds — independent decision-level
support for rejecting C2. G-02 is a confirmed-alert question and is neither claimed nor closed here.

**Binding non-claims:** FP figure on the *secured negative suite (KTH aux domain, walking-only)* — never
G-02 (six-class suite still open); TTD unmeasurable (no onset labels; scorer-native `unavailable_metrics`);
no positive-class statement anywhere. **No default behaviour changes ship** — C1 is now a measured choice,
and both "improvements" (ensemble `max`, motion gate) are rejected/no-op at this operating point, which is
itself the deliverable value: it prevents a wrong improvement from shipping.
Artifacts: `exp1908-*.json` (win-scores, adapter reports, three eval reports, summary).

## 12. Lock record and queue

* RESOURCE-LOCK acquired atomically by WT-19 at `2026-09-29T01:56:13+03:00` (dir was absent at that instant;
  WT-23 had removed the pre-existing dir, and WT-21 released at 01:55:48 per their report).
* Incident record (for the cross-workstream log): the 01:38 acquisition window was racy — WT-16's owner.txt
  write clobbered WT-19's despite losing the mkdir; WT-23 used `mkdir -p` and later removed the dir; the
  corrected protocol (atomic mkdir is the only gate) is now broadcast by the orchestrator and was applied
  by everyone afterwards. No measurement of mine was taken during another holder's window.
* **Lesson recorded by Main's 02:2x arbitration (WT-14 vs WT-19 ledger dispute):** lock ledgers must record
  **script-clock timestamps at acquisition and release**, not wall estimates — the apparent 02:23–02:27
  overlap was timestamp approximation on both sides (the dir was provably absent at 02:27:19). Consequences
  applied to EXP-1908: deterministic FP counts and GPU timings stand; the run's CPU decode phases carry the
  POTENTIALLY CONTENDED label.
* Release: dir removed after the final measurement; next in line per Main's order **WT-16 (InferenceAccel)**,
  then WT-21 (approved ~2 min re-run), WT-15, WT-27, and WT-17 requested to be appended after WT-27.

## 8. Reproduce / re-run commands

```
# scoped tests
cd backend && "C:/Users/PCD/Downloads/Final Project AI Sentinel/venv/Scripts/python.exe" -m pytest \
  tests/test_runtime_observation_contract.py tests/test_angle_invariance.py \
  tests/test_inspect_model_checkpoint.py tests/test_multi_angle_benchmarks.py \
  tests/test_temporal_window_integrity.py tests/test_ensemble_semantics.py -q

# measurements (require a clean RESOURCE-LOCK acquisition)
python backend/tests/wt19_sweep_harness.py --out <out.json> identity
python backend/tests/wt19_sweep_harness.py --out <out.json> throughput --device cuda --iters 30 --windows 16 32
python backend/tests/wt19_sweep_harness.py --out <out.json> sweep --device cuda --iters 15 --fps 30
python backend/tests/wt19_sweep_harness.py --out <out.json> window-scores --device cuda --window 32
python backend/tests/wt19_sweep_harness.py --out <out.json> compare <a.json> <b.json>

# accuracy / FP / TTD re-run once WT-12 fixtures land (same schema as WT-12's baseline)
python backend/tests/wt19_sweep_harness.py --out <out.json> window-scores --videos <fixture-root> \
  --ensemble-k {1,3,5} ; # join with WT-12 labels offline for FP/hour + TTD
```

## 9. Assets

`backend/best_model.pt` was read in place / hash-verified; nothing was copied or committed.
sha256 `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`, 149,344,325 bytes.
Artifact hashes: `docs/campaign/experiments/artifacts/SHA256SUMS.txt`.

## 10. WT-12 harness interface (recorded 2026-09-29, commit `a9cb03d`, branch `codex/sentinel-12-eval-data`)

WT-12 landed the fixture/eval harness **after** this slice's measurement window; fixture *entries* (media)
were still downloading at the time, so no accuracy/FP/TTD run was possible for WT-19 — the blocked statuses
in EXP-1902/1903/1905/1906 stand as of this handoff.

Coordinates for the unblock:
* manifest `docs/campaign/eval/12-fixture-manifest.json` (schema `wt12-fixture-manifest/1`; runtime contract
  window 32, stride = run config; subject/session splits 01-02/03-04/05-06/07-12 = train/val/calibration/test;
  5 `unavailable_categories` recorded), protocol `docs/campaign/eval/12-eval-protocol.md`,
  media root `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12-fixtures/` (out of git, per-fixture sha256).
* outputs schema expected by their scorer: `{fixture_id, source_sha256, run_id, source_mode:"file-media",
  windows[], detections[], alerts[], tracks[]}`; validator rejects pseudo-labels/live mode.
* command: `python -m bench.eval.evaluate --manifest docs/campaign/eval/12-fixture-manifest.json
  --outputs <dir> --report <file> --threshold <fixed-before-inspection> --bootstrap-unit session
  --bootstrap-resamples 2000 --seed 20260929` (run from wt-12).
* mapping from this slice's artifacts: **implemented and contract-verified** — `wt19_sweep_harness.py
  to-fixture-outputs --manifest <wt-12 manifest> --scores <window-scores.json> --out-dir <dir> --run-id <id>`
  emits one record per matched fixture (`fixture_id`, `source_sha256`, `source_mode: "file-media"`,
  `windows[]` with contract names `start_s`/`end_s`/`violence_conf` plus the runtime-contract integrity
  fields and additive extras, empty `detections`/`alerts`/`tracks`, a `producer` provenance block). Strict by
  default: an unmatched scored clip aborts the CLI. See EXP-1907 for the verification evidence and the
  exact field list; `alerts[]` still has to come from the decision layer's own export (WT-20), not from here.
* honest denominator language to reuse verbatim: negatives = "secured negative suite (KTH aux domain)";
  G-02's six-class suite is not closable with those fixtures; time-to-detection remains UNMEASURABLE until an
  onset-labelled fixture exists.
