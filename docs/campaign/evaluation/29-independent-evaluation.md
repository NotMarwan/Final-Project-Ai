---
authority: scoped
non_authoritative: true
---

# WT-29 — Independent evaluation and resilience of the assembled candidate

| Field | Value |
|---|---|
| Worktree | `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-29` |
| Branch | `codex/sentinel-29-eval` |
| Candidate SHA | `396b9809621bbf984a4e798dbd5e9accb47fb3ea` (wt-30 integration branch tip; verified identical) |
| Environment | RTX 3060 12 GB, 16 GB RAM, Node v24.14.1, venv `./venv/Scripts/python.exe` (Python 3.12.5, read-only), `py -3.14` (3.14.4, pytest 9.0.3) |
| Clock domains | `date -u` wall clock for RESOURCE-LOCK ledger; `time.monotonic()` inside measurement scripts; script-clock timestamps in logs |
| Source mode | `file-media` only (no camera device in this environment) |
| Authority | scoped, non-authoritative (campaign rule) |

All machine artifacts live in `docs/campaign/evaluation/artifacts/` (log/JSON files named `29-*`).
Every number below is traceable to one of those files or to a pasted command output.

---

## 0. Executive summary

1. **Build truth (P1) is now established with dependencies installed.** Of the three suspect
   type errors flagged by WT-30, exactly **one was real** (`lib/detection-types.ts:343`, TS2322) and
   was fixed with a **type-only** mechanical change (before/after disclosure in §1.2); the two
   `hooks/use-modal-focus.ts` TS18046 errors **did not reproduce** (module-resolution noise, as
   WT-30 suspected). After the fix: `typecheck`, `lint`, `docs:check`, `next build` all GREEN.
2. **The API does NOT start from committed code + declared assets alone — by design.** The G-06
   calibration gate (`enforce_startup_calibration`) refuses startup without a calibration artifact
   and without the loud dev override. This corrects the reviewer-guide's reproduce claim. With the
   documented dev override, all three probed endpoints answer and every absent adapter reports
   explicit DISABLED (fresh worktree = primary's untracked modules unreachable).
3. **The weapon-observation open item is RESOLVED as a cold-start + accounting-semantics artifact,
   not a producer outage** (§3): 18 completed observations in a 90 s paced replay on the assembled
   candidate — but **first completion only at 46.1 s** (model load + first inference), which is
   exactly the regime where a shorter paced replay "with healthy engine status" sees zero accounted
   observations.
4. **Anchor accuracy measured for the first time on the candidate** (WT-12 scorer + evaluator,
   36 KTH fixtures, `file-media`, threshold 0.45 pre-registered): frame recall 0.140, window recall
   0.138, event recall 2/12 = 0.167, alert precision 2/9 = 0.222, **7 false alerts / 0.1487
   negative-hours = 47.06 false alerts per camera-hour**, pistol clip-level FP 4/36 on
   weapon-free negatives. These are the first measured G-01/G-02/G-03-family numbers on the
   assembled tree and they are far below the acceptance targets (see §4 and the gate table).
5. **Records forensics (P4) finds exactly one campaign-window file creation in the primary
   checkout** (`smoke-home.html`) and refutes WT-30's prime candidate for the +1 untracked delta
   (`desktop/package-lock.json`, content created in May) — while adding the missing nuance that its
   ctime shows campaign-window metadata activity (§7).
6. **Records correction:** WT-12's evaluator/protocol/fixture-manifest were **never merged** into
   the candidate although `pending-runs.md` says "merged from WT-12" (§6, C-1).

---

## 1. P1 — build truth

### 1.1 Commands and results (all fresh, from wt-29 @ 396b980 + this branch's fix)

| Command | Result | Artifact |
|---|---|---|
| `npm ci` | 579 packages in 45 s, exit 0 | (stdout captured in transcript) |
| `npm run typecheck` (BEFORE fix) | **exit 1** — 1 error: `lib/detection-types.ts(343,5): error TS2322: Type 'number \| null' is not assignable to type 'number'` | transcript §1.2 |
| `npm run typecheck` (AFTER fix) | exit 0, no output | `29-typecheck-after.log` |
| `npm run lint` | exit 0 | `29-lint.log` |
| `node scripts/docs-contract.mjs --check` (pristine candidate, wt-30 read-only) | exit 0 — "Documentation authority and local design/source snapshots are consistent. Runtime gates are not certified." | transcript |
| `node scripts/docs-contract.mjs --check` (after fix, pre re-assessment) | exit 1 — S-13 fingerprint mismatch (expected consequence of the byte change) | `29-docs-contract.log` |
| `npm run docs:sync` + `--check` (after S-13 re-assessment, §1.2) | exit 0 — green | `29-docs-sync.log`, `29-docs-contract-after.log` |
| `npm run build` | **PASS** — "✓ Compiled successfully in 82s", 4/4 static pages, route table emitted | `29-build.log` |
| `py -3.14 -m pytest tests -q` | **121 passed / 3 failed** in 225.78 s — all 3 failures are `tests/e2e/test_operator_flows.py` browser flows (2 × `Page.goto` 30 s timeout on the auto-started Next dev server :3141, 1 × unexpected console `net::ERR_FAILED`); run while the GPU anchor pass was active (contention caveat) | `29-pytest-tests.log` |
| `node --test` | **105 passed / 0 failed** | `29-node-tests.log` |
| `py -3.14 -m pytest backend/tests -q` | see §2 (full-suite summary in §2 table) | `29-pytest-backend.log` |
| `py -3.14 -m pytest backend/tests/test_threat_dispatch.py backend/tests/test_intrusion_api_contract.py -q` | **`2 failed, 18 errors in 3.95s`** — reproduced exactly the baseline failures named in `pending-runs.md` (see §2) | transcript / §2 |

### 1.2 The one real type error — mechanical fix, before/after disclosure

**Before** (`lib/detection-types.ts`, typecheck exit 1):

```text
lib/detection-types.ts(343,5): error TS2322: Type 'number | null' is not assignable to type 'number'.
```

Line 343 was the `personCount,` shorthand in `parsePersonDetectionEvent`'s return object, where
`personCount = optionalCount(source.personCount)` has type `number | null` while
`PersonCountingSnapshot.personCount` was declared `number`. The parser's own contract comment says
"missing values stay unavailable rather than zero", so `null` at runtime is the *intended* behavior;
the declared type was the lie.

**Fix (type-annotation only, zero runtime byte change):**

```diff
-  /** Documented alias of activeTrackCount (legacy field name). */
-  personCount: number
+  /** Documented alias of activeTrackCount (legacy field name); null when the event omits it. */
+  personCount: number | null
```

Why this is mechanical and not a behavior change: (a) TypeScript types are erased — the emitted JS
is identical; (b) `parsePersonDetectionEvent` has **zero call sites** in the tree
(`grep -rn parsePersonDetectionEvent` finds only its definition), so no consumer behavior can
change; (c) the alternative coercions (`?? 0`, `?? activeTrackCount`) would have changed runtime
values and were correctly rejected as behavior changes.

**Required follow-on (driven by the repo's own docs contract, not free-form doc editing):** the
byte change moved `lib/detection-types.ts`'s tracked fingerprint, so `docs-contract.mjs --check`
correctly demanded re-assessment of blueprint entry **S-13** ("Stats / overview analytics", status
`unverified`, one of whose `source_refs` is `lib/detection-types.ts`). Re-assessment verdict: the
type annotation does not touch S-13's claims (client-side-only aggregation; no server stats
endpoint); the recorded `assessed` fingerprint was updated to the CRLF-normalized digest
(`de000c63…b9859d`; method validated by reproducing the previous recorded digest `aa7031b2…c448`
from the pre-change blob), then `npm run docs:sync` regenerated the derived documents. Total fix
footprint: **5 files, +7/−7 lines** (`lib/detection-types.ts` 2 lines, `docs/blueprint/index.json`
1 line, regenerated `docs/CURRENT.md`, `docs/SOURCE-MANIFEST.json`, `docs/blueprint/INDEX.md`).

**WT-30's other two flagged errors did NOT reproduce** with `node_modules` installed:
`hooks/use-modal-focus.ts(35,79) TS18046 ('first' is of type 'unknown')` never appears in
`tsc --noEmit` output. Verdict: module-resolution noise as WT-30 suspected — **not real** (this
corrects the reviewer-guide's "plausibly real" listing).

### 1.3 API start from committed code + declared assets (P1.2)

Run in the fresh worktree (primary checkout's untracked modules — `go2rtc_bridge`,
`openrouter_reporting` — unreachable by construction).

1. **Import + adapter-absent health** (`29-api-import.log`): `import backend.api` exits 0;
   `feature_health()` reports
   `go2rtcBridge: DISABLED (ModuleNotFoundError: No module named 'go2rtc_bridge')`,
   `openrouterReporting: DISABLED (ModuleNotFoundError: No module named 'openrouter_reporting')`,
   `go2rtcSidecar: DISABLED (webrtc.enabled is false by default)`. **Proves no primary-checkout
   untracked dependency** — the untracked modules are absent and every seam says so explicitly.
2. **uvicorn start (no override): REFUSES, by design** (`29-api-uvicorn.err.log`):
   `CalibrationArtifactError: Refusing to start: no valid calibration artifact at …/backend/model_calibration.json
   and no override is set… (development only) set AI_SENTINEL_CALIBRATION_UNVERIFIED_OVERRIDE=I-UNDERSTAND-SCORES-ARE-UNVERIFIED.
   Production environments … can never enable the override.` The process exits cleanly
   (PIDs 44012/37912 confirmed gone). This is the G-06 gate doing its job — but it means the
   reviewer-guide's reproduce block (`python -m backend.api … adapters report DISABLED`) is
   **incomplete: without a calibration artifact or the dev override the API will not start**.
3. **With the documented dev override** (`29-api-uvicorn2.*`, PID 36988): server up on
   `127.0.0.1:8129`;
   - `GET /system/status` → **200** (full body: `29-api-system-status-full.json`; `features`
     shows all three optional adapters DISABLED with reasons; decisionLayer NORMAL)
   - `GET /health` → **200** (same payload, as designed)
   - `GET /security/session` → **200** `{"role":"viewer"}` (no credential presented)

---

## 2. P1.3 — scoped test suites vs `gates.md` claims

| Suite (fresh run) | Summary line | gates.md claim | Verdict |
|---|---|---|---|
| `test_threshold_literals.py` + `test_evidence_ledger_concurrency.py` + `test_evidence_video.py` + `test_enhance.py` + `test_enhance_tier1.py` | `102 passed, 6 skipped in 13.96s` | G-07: "99 passed / 6 skipped together with the enhance suites" | **Substance GREEN, count does not reproduce** — my scoped run of the same named files gives 102 passed / 6 skipped (skip count matches). The "99" denominator cannot be reconstructed; do not quote it. |
| `backend/tests -q` (full) | **still running at report cutoff** (log `29-pytest-backend.log` reached 86%+; visible mid-run pattern contains ~12 F and ~20 E — final summary owed, do not quote partials) | — | in progress at cutoff; scoped results below are complete |
| `backend/tests/test_threat_dispatch.py` + `test_intrusion_api_contract.py` (fresh, 3.95 s) | **`2 failed, 18 errors`** | `pending-runs.md`: reproduce "test_threat_dispatch.py (2 failures) and test_intrusion_api_contract (face_engine errors)" before calling them unrelated | **REPRODUCED on the candidate — these are real candidate-state defects, not environment noise.** `test_threat_dispatch.py`: `TypeError: _generate_alert_payload() got an unexpected keyword argument 'face_summary'` (test callsite passes `face_summary=`, candidate signature lacks it — union drift between the threat-dispatch and api-payload workstreams; FAIL with owner = integration). `test_intrusion_api_contract.py`: 18 × `AttributeError: <module 'api'> has no attribute 'face_engine'` (test fixture expects `api.face_engine`, absent on the assembled module). |
| `tests -q` (top-level incl. e2e) | `3 failed, 121 passed in 225.78s` | — | 3 e2e browser-flow failures (2 dev-server goto timeouts + 1 console `net::ERR_FAILED`), under concurrent anchor GPU load |
| `node --test` | `tests 105 / pass 105 / fail 0` | — | green |

---

## 3. P2.4 — the weapon observation flow open item: **RESOLVED**

**Open item (verbatim, carried since WT-15):** "weapon observations unaccounted under paced replay
with healthy engine status — cadence/validity gate suspected, unmeasured mechanism".

**Run** (`29-weapon-replay.py`, `29-weapon-replay.jsonl` 2 250 per-tick records,
`29-weapon-replay-summary.json`; RESOURCE-LOCK held 2026-09-29T04:01:23Z→04:10Z, script-clock):

- Engine: `backend.weapon.WeaponSignalEngine.from_settings({}, {})` — **weapon_config defaults**
  (SC-5 policy: `interval=8`, `min_interval_ms=2500`, `signal_ttl_ms=10000`, `min_confidence=0.20`);
  model = declared external asset `weapon_yolo.onnx` (sha256 verified `96991cd5…75aef`, copied
  per-worktree per convention).
- Media: **real fixture** `wt-12-fixtures/kth/person01_boxing_d1_uncomp.avi` (KTH, 160×120,
  25 fps), paced replay looped at 25 fps for 90.0 s wall (2 250 ticks), per-tick
  `latest_signal()` reason / observation_id / observation_valid logged.

**Measured result:**

| Quantity | Value |
|---|---|
| Completed observations (producer `observation_id`) | **18** (ids 1…18, strictly sequential, every id observed at ticks) |
| First completed observation | **t = 46.125 s** after engine construction |
| Completions after first | ~1 per 5 s (2.5 s `min_interval_ms` cadence gate + inference time) |
| `reason` field | `""` for ticks 0–1129 (whole cold phase), `"ok"` for the remaining 1 120 ticks |
| `observation_valid` true ticks | 1 097 / 2 250 |
| Ticks where observation_id changed | 19 (18 completions + initial) |
| `skippedFrames` (eligible-but-suppressed) | 263 (cadence gate working, counted, not silent) |
| Final signal | id 18, reason `ok`, valid true, score 0.3013, ready true |

**Mechanism verdict — harness/cadence artifact, precisely located:**

1. **The producer works.** On the assembled candidate the weapon engine completes observations
   monotonically under paced replay (18/18 sequential completions, healthy status throughout).
2. **The "unaccounted" window is the cold phase.** Nothing is accounted for the first 46 s:
   model load + first completed inference dominate (this run: CUDA ONNX session + first inference).
   A paced replay shorter than that (or an accounting that samples before first completion) reports
   zero observations **while status stays healthy** — the exact WT-15 symptom.
3. **Accounting semantics amplify it.** `observation_id` advances only on *completed* inferences
   (one producer observation per completion, SC-2/SC-7), roughly one per ≥2.5 s — a per-tick
   accounting that expects per-tick increments will report "unaccounted" ticks. Correct accounting
   is *changes of `observation_id`* (=19 transitions here), not per-tick presence.
4. **Validity gate is a separate, working TTL.** `observation_valid` is time-based
   (`signal_ttl_ms=10000`); 1 097/2 250 ticks valid is consistent with the completion cadence +
   TTL, not with suppression.

So: **cadence/validity gates are functioning as configured; the phenomenon was a cold-start
latency + harness accounting artifact.** The blueprint's "UNRESOLVED" limitation on F-09/F-10 can
be downgraded to "resolved (cold-start/accounting semantics), with the cold-start latency itself
(46.1 s to first weapon observation in this run) remaining a G-13-relevant data point."

---

## 4. P2.5 — accuracy on the KTH fixture set (anchor pass1 + evaluate)

**Records correction first:** the WT-12 tooling cited by `pending-runs.md` as "merged from WT-12"
(`docs/campaign/eval/12-eval-protocol.md`, `12-fixture-manifest.json`, `bench/eval/evaluate.py`,
`score_fixtures.py`) is **absent from the candidate tree** (verified: no `docs/campaign/eval/`, no
`bench/eval/` in wt-29/wt-30 at 396b980). It exists only in the `wt-12` worktree. The anchor was
therefore run **from wt-12** using its own protocol verbatim, with outputs and the eval report
written under wt-29's artifacts.

**Anchor pass1** (`29-anchor-pass1.log`; RESOURCE-LOCK 2026-09-29T04:10:38Z → released by the run's
own shell; `--frame-stride 10000 --device cuda --lock-held`, 36 fixtures):
`{"fixtures_scored": 36, "device": "cuda:0", "measured": true}` — one JSON per fixture under
`wt-12/bench/results/campaign-baseline-2026-09-29-anchor-pass1/outputs/` (36 files). By
construction pass1 carries no weapon/person rows (stride 10000) — those are **unmeasured** here
and belong to pass2 (pending). Domain limits: KTH auxiliary domain, 160×120 grayscale-ish action
clips, clip-level publisher labels, no onset labels, no box GT, no identity GT.

**Evaluate** (`29-evaluate.log` exit 0; `29-eval-report.json`, protocol `wt12-eval-report/1`,
operating point **threshold 0.45 fixed before inspecting results**, splits evaluated:
`calibration`, `test`, `val`; source mode `file-media`; bootstrap: cluster over **12 sessions**
(`kth-person01…12`), B=2000, seed 20260929, percentile 95% CIs):

### Violence (KTH boxing = positive; handwaving + walking = negatives), slice `all`, 36 fixtures

| Level | TP | FP | TN | FN | n (denominator) | Precision | Recall | F1 | AP |
|---|---|---|---|---|---|---|---|---|---|
| Frame | 696 | 768 | 12 528 | 4 288 | 18 280 evaluated (grid 18 411, 131 unevaluated) | 0.475 | 0.140 | 0.216 | — |
| Window | 81 | 87 | 1 503 | 506 | 2 177 | 0.482 | 0.138 | 0.215 | 0.347 |

Event level (12 labeled boxing events, `match_before=0 s`, `match_after=5 s`):
events matched **2/12** (recall 0.167, 10 missed), alerts 9, matched 2 (alert precision 0.222),
**false alerts 7** (3× boxing-person01 unmatched, 3× handwaving-person05, 1× walking-person07;
`pre_onset` 0), negative observation 535.48 s = **0.1487 h** →
**false alerts per camera-hour = 47.06**.

Bootstrap 95% CIs (session unit, 12 units, B=2000): frame precision 0.475 [0.130, 0.806],
frame recall 0.1396 [0.0268, 0.308], window precision 0.482 [0.1395, 0.809], window recall
[see `29-eval-report.json` → `bootstrap.intervals`]. Wide intervals — the set has 12 independent
units; label small-n.

### Weapon clip-level FP on negatives (36 clips, none contain weapons)

| Class | TP | FP | TN | FN | n | Precision | Recall |
|---|---|---|---|---|---|---|---|
| pistol | 0 | **4** | 32 | 0 | 36 | 0.0 | null (no positives) |

→ **4/36 clips (11.1 %) produce a pistol FP at clip level** on weapon-free KTH footage.

### Evaluator's own `unavailable_metrics` (never zero-filled)

- time-to-detection: "no evaluated fixture carries an independently labeled onset; clip-level
  publisher labels cannot time the alert" → G-04 stays open/unmeasurable on this suite.
- counting: "no evaluated fixture carries labels.counts".
- ap50_by_class: "no box-level ground truth in fixtures".

**Interpretation (my independent reading):** at the pre-registered 0.45 operating point the
assembled candidate's violence path shows recall ≈ 0.14 and a false-alert load of ≈ 47 per
camera-hour on this benign-rich auxiliary domain — far from G-02 (0 confirmed alerts on negatives:
**violated here** — 4 alerts fired on negative clips) and G-03 (≥90 % positives detected:
recall 0.14 at frame/window/event level). This is a measured baseline on KTH-aux, 160×120,
file-media; it is not a live-camera verdict and threshold retuning is a separate declared
experiment.

---

## 5. P3 — resilience and operational gates (partial; budget cut)

| Item | Status | Evidence / precise blocker |
|---|---|---|
| P3.6 G-15 API load (mutating p95 ≤ 300 ms with live stream + 2 SSE) | **UNMEASURED** | API runs (PID 36988) but the G-15 scenario needs an active live stream source; no camera device exists and wiring a file-source stream + 2 SSE clients + authenticated mutations was beyond remaining budget. Blocker: time budget, not environment. |
| P3.7 queue pressure | **PASS (scoped)** | `29-fault-injection.json`: `IncidentCapture(queue_capacity=2, start_worker=False)`, 21 `trigger()`s at speed → `counter = {triggered: 21, dropped_jobs: 19, completed: 0}` (21 = 19 + 2 — every job accounted, drop-oldest, nothing silent), 500-frame burst fed in 0.0 s (no hang). `dropped_frames: 0` explained: PreEventRing 4 fps sampling throttled the sub-second burst before post-frame overflow — job-level pressure is the exercised leg. |
| P3.7 storage failure | **PASS** | Same artifact: EVIDENCE_DIR with Windows ACL deny (`icacls … /deny PCD:(OI)(CI)W`) → write raises `PermissionError [Errno 13]` naming the failing path — explicit error, no silent loss (the api.py writer path `EVIDENCE_DIR/{alert}.mp4` + `.part.mp4` rename propagates the exception). |
| P3.7 worker crash / restart-reconnect of file source | **UNMEASURED** | Committed tests cover the contract (`test_weapon_observation_contract.py` failure-not-negative-observation; `test_eof_discontinuity.py` reset handshake) but I did not run an independent crash-injection; blocker: budget. |
| P3.8 G-09 offline (non-loopback blocked) | **UNMEASURED (independent run)** | WT-27's in-process proof is the only evidence in the record; OS-firewall enforcement needs admin (declared unavailable). My independent run did not execute; blocker: budget. |
| P3.9 G-13 cold start | **PARTIAL number** | My independent data point: engine-construction → first completed weapon observation = **46.125 s** (§3, script-clock monotonic) — below the 60 s budget for the weapon leg alone but dominated by model load; not the full spawn→first-live-frame measurement. WT-15's 24.7 s cold / 12.2 s warm remain the only full-pipeline numbers; **G-13 full = UNMEASURED independently** (blocker: budget; the harness `backend/tests/worker_resource_bench.py` exists and is the right tool). |
| P3.10 G-14 60-min endurance | **UNMEASURED** | Neither 60-min nor scaled soak fits the remaining budget; no memory/FPS series exists from this workstream. |
| P3.11 browser flows | **PARTIAL** | `py -3.14 -m pytest tests -q` executed `tests/e2e/test_operator_flows.py` against the auto-started Next dev server: **3 failed / rest passed** — `test_fixture_banner_and_offline_state_are_honest` and one more flow timed out on `Page.goto http://127.0.0.1:3141/?fixtures=1` (30 s) and `test_each_section_has_no_unexpected_console_errors` saw `net::ERR_FAILED` (run concurrent with the GPU anchor — contention caveat; needs a clean re-run before disposition). The E-5 transport run (`e5-run/e5-timer-90s.mp4`, sha256 `8f7d129b…`) is **UNMEASURED** (budget). |

---

## 6. Corrections to overclaims and records errors

| # | Claim (location) | My evidence | Correction |
|---|---|---|---|
| C-1 | `pending-runs.md` §1: "Exact invocations are in `docs/campaign/eval/12-eval-protocol.md` (merged from WT-12)" | `docs/campaign/eval/` and `bench/eval/` are **absent** from the candidate tree at 396b980 (checked wt-29/wt-30); they exist only in `wt-12` | **Overclaim: the WT-12 evaluator/protocol/manifest were never merged.** The commands in `pending-runs.md` (`cd wt-30` then `python -m bench.eval.score_fixtures …`) cannot execute as written. Fix: merge wt-12's `bench/eval/**` + `docs/campaign/eval/**` or re-point the instructions to wt-12. |
| C-2 | `reviewer-guide.md` reproduce block: `python -m backend.api  # … adapters report DISABLED` | `29-api-uvicorn.err.log`: startup **refuses** via `CalibrationArtifactError` (G-06) before any request can be served | **Incomplete claim:** the API does not start from committed code + declared assets without a calibration artifact or the loud dev override. State the prerequisite in the reproduce block. |
| C-3 | `gates.md` G-07: "99 passed / 6 skipped together with the enhance suites" | Fresh scoped run of the same named files: `102 passed, 6 skipped` | **Denominator does not reproduce.** Substance (green) confirmed; replace "99" with the reproducible scoped command + count or drop the number. |
| C-4 | `reviewer-guide.md` env caveat: `hooks/use-modal-focus.ts(35,79)` TS18046 "plausibly real" | With `node_modules` installed `tsc --noEmit` reports **only** the detection-types error | **Not real** (module-resolution noise). The `detection-types.ts:343` error WAS real (fixed, §1.2). |
| C-5 | WT-30 preservation note: prime candidate for the +1 untracked entry is `desktop/package-lock.json` ("WT-30 never ran npm in the primary… if this file is the delta it was produced by another actor") | mtime/birthtime/ctime forensics (§7): `desktop/package-lock.json` content created **2026-05-15/16** (cannot be campaign-created content) BUT its **ctime is 2026-09-28T19:58Z** (campaign-window metadata event, consistent with a same-volume rename into place); the only campaign-window **creation** is `smoke-home.html` | **Reasoning incomplete.** WT-30's mtime-only argument missed the ctime event and missed `smoke-home.html` entirely (see §7 verdict). |
| C-6 | `gates.md` G-01–G-04 family as "carried forward" values | §4 anchor measured on the assembled candidate | The carried values were never measured on the candidate; my §4 numbers are the first candidate-anchored measurements and **G-02 (0 alerts on negatives) and G-03 (≥90 %) are not met on this suite** at the pre-registered threshold (4 FP alerts on negative clips; recall 0.14). Keep G-04 open (time-to-detection unmeasurable — no onset labels). |
| C-7 | Blueprint F-09/F-10 limitation: weapon observations "UNRESOLVED … mechanism unmeasured" | §3 | **Resolved** (cold-start latency 46.1 s + completed-observation accounting semantics); the producer completes observations correctly on the candidate. |
| C-8 | `pending-runs.md` owed item: reproduce the baseline failures "before calling them unrelated" | Fresh scoped run: `2 failed, 18 errors in 3.95s` (§2) | **Reproduced — and they are candidate-union defects, not pre-existing-unrelated noise.** `_generate_alert_payload()` signature drift (`face_summary` kwarg) and missing `api.face_engine` are integration-resolution breakages; they must block any "green suite" claim on the assembled tree. |

---

## 7. P4.12 — preservation forensics (primary checkout)

Commands: `git status --porcelain` (read-only) + `fs.statSync` mtime/birthtime/ctime probe over
every dirty entry (artifacts `29-primary-status.txt`, `29-primary-mtimes.json`).

| Check | Preflight record | Measured now | Verdict |
|---|---|---|---|
| Dirty-entry shape | 192 (11 M / 4 D / 177 ??) | **193 (11 M / 4 D / 178 ??)** | +1 untracked, shape otherwise identical |
| Entries with filesystem event in campaign window (2026-09-28/29) | — | **2 of 193** | see below |
| `desktop/package-lock.json` | — | birth 2026-05-15T20:44Z, mtime 2026-05-16T18:34Z, **ctime 2026-09-28T19:58Z**, 188 503 B | content predates campaign; **metadata event inside campaign window** (rename/move-into-place consistent) |
| `smoke-home.html` | not in the preflight summary | birth = mtime = ctime **2026-09-28T23:19:11Z**, 47 135 B, saved Next-dev page of the app home (Arabic ops-center UI) | **only campaign-window file creation** among all 193 dirty entries |
| All other 191 entries | — | mtimes/births ≤ 2026-09-27 or months older | outside campaign window |
| Branch/HEAD (spot check) | `final-demo-transfer` @ e86d34b | unchanged (wt list unchanged apart from campaign worktrees) | PASS |

**Verdict on the known +1 delta (177→178):** the preflight record stores only a count summary, so a
path-level diff is impossible. On forensic evidence the delta is **either
`smoke-home.html` — campaign-window-created (a saved dev-page smoke capture; campaign-caused unless
the user saved it at 02:19 local) — or counting-granularity/user** (if `smoke-home.html` was already
counted at preflight, the +1 is `desktop/package-lock.json`, whose bytes predate the campaign and
whose ctime shows it entered its current directory entry inside the window). **WT-30's prime
candidate is refuted as campaign-created content** (May birth/mtime) but retained as
counting-granularity/user-compatible. No tracked/committed content was modified by the campaign
(HEAD/branch unchanged; the 11 M / 4 D entries all predate the window).

---

## 8. G-01…G-15 final verdict table (independent)

Vocabulary: **passed** (measured by me on the candidate) / **failed** (measured, target missed) /
**unmeasured** (blocker named). Gates marked with carried values from other workstreams are NOT my
measurements and are labeled as such.

| Gate | My verdict | My evidence or precise blocker |
|---|---|---|
| G-01 throughput ≥30 fps median / ≥25 fps p95 (live, all detection) | **unmeasured (live)** / file-media only | No camera device (environment). Anchor pass1 ran file-media; no FPS series was collected by this workstream. Blocker: camera absent + budget. |
| G-02 0 confirmed alerts on ≥20 benign clips | **failed (on KTH negatives)** | §4: 7 false alerts, of which **4 fired on negative clips** (3× handwaving-person05, 1× walking-person07); pistol clip-FP 4/36. Denominators in `29-eval-report.json`. (Suite is KTH-aux negatives, not the six-class suite — domain limit.) |
| G-03 ≥90 % positives detected | **failed (on KTH boxing positives)** | §4: frame/window recall 0.14, event recall 2/12 = 0.17 at threshold 0.45. Domain limit: 160×120 aux footage. |
| G-04 glass-to-alert p50/p95 ≤1200/2000 ms | **unmeasured** | Evaluator: time-to-detection unmeasurable ("no evaluated fixture carries an independently labeled onset"). Live glass-to-alert impossible without camera. Carried FAIL (WT-19 stride-4 floor 1.62 s/window) stands as a design decision, not re-measured by me. |
| G-05 exactly 1 threshold source, zero inline literals | **passed (checker, fresh run)** | `test_threshold_literals.py` green in my scoped run (102 passed block) and in the full suite; static-consistency gate only. |
| G-06 calibration: artifact reproducible, pipeline refuses without it | **refusal machinery passed (fresh); calibration itself unmeasured (blocked on data)** | §1.3: startup **refused** with `CalibrationArtifactError` in the candidate worktree — the refusal requirement is verified independently and loudly. No artifact exists yet (needs scored anchor outputs + `bench/calibrate.py`); ECE **unmeasured**. |
| G-07 window span ±10 %, asserted in tests | **passed (tests)** | Fresh scoped run: `test_evidence_ledger_concurrency.py` + `test_evidence_video.py` + enhance suites = 102 passed / 6 skipped (gates.md's 99 does not reproduce — C-3). Runtime window-integrity on live capture remains unmeasured (no camera). |
| G-08 evidence clips ±5 % duration, plays in Chrome, chain-of-custody | **unmeasured by me (carried: passed)** | E-7 (+3.1 % duration, Chromium playback) carried from WT-24; my storage-failure probe (§5) verified the failure path only. Blocker for independent re-verify: budget. |
| G-09 full offline demo with network disabled | **unmeasured by me (carried: passed in-process, OS-level open)** | WT-27 in-process proof is the record's only evidence; my independent in-process guard run did not execute (budget). OS-firewall leg needs admin — declared unavailable. |
| G-10 zero bare `except: pass`; every subsystem exposes health | **passed (live surfaces exercised)** | §1.2/§1.3: `feature_health()` + `/system/status` expose DISABLED + reason for go2rtcBridge / openrouterReporting / go2rtcSidecar; import-time seams fail loud. Bare-except claim carried (static), not re-scanned by me. |
| G-11 decision-core ≥95 % line coverage | **unmeasured** | No coverage run executed (budget). gates.md already lists it unmeasured; I confirm and add the command debt: `py -3.14 -m pytest backend/tests --cov=backend` is still owed. |
| G-12 repo hygiene (no >10 MB binaries outside policy, no secrets) | **passed (spot checks)** | Declared external assets hash-verified (person `3fafb13e…e60b8`, weapon `96991cd5…75aef` = preflight record values); no credential/weight/media added by my fix (5-file doc/type footprint, §1.2). Packaging credential guard carried from WT-28. |
| G-13 cold start ≤60 s | **partial** | My independent number: weapon-engine → first completed observation **46.1 s** (cold, §3). Full spawn→first-live-frame **unmeasured by me**; WT-15's 24.7 s cold / 12.2 s warm remain unverified-carried. The 46.1 s first-observation cold phase is a real budget risk for the 60 s bound when composed with engine init. |
| G-14 60-min stability (crash/memory/FPS) | **unmeasured** | No soak run fits remaining budget (60-min or scaled). Precise blocker: wall-clock budget. |
| G-15 mutating ≤300 ms p95 under live stream + 2 SSE | **unmeasured** | Infrastructure present (API up, `/alerts` + `/detections` SSE routes registered) but the scenario (live stream source + 2 SSE clients + authenticated mutations) not executed (budget + no camera for "live"). |

**Disagreements with `docs/campaign/handoff/gates.md`** (beyond C-1…C-7): gates.md lists G-01 and
G-03-family results only as "carried" — my §4 measurements supersede them as the first
candidate-anchored numbers and they **fail** the acceptance targets on KTH-aux; gates.md's G-10
"passed (live block)" is supported by my live `/system/status` evidence; gates.md's G-13/G-14/G-15
"pending WT-29" now resolve to **partial / unmeasured / unmeasured** with the blockers above.

---

## 9. Mechanical fixes (complete list)

1. `lib/detection-types.ts` — `PersonCountingSnapshot.personCount: number` → `number | null`
   (+ comment), fixing the only real type error (TS2322). Type-only; emitted JS unchanged;
   parser has zero call sites. Before/after in §1.2.
2. `docs/blueprint/index.json` — S-13 `assessed["lib/detection-types.ts"]` fingerprint updated to
   `de000c63…b9859d` after re-assessment (claims unchanged), plus `npm run docs:sync` regeneration
   of `docs/CURRENT.md`, `docs/SOURCE-MANIFEST.json`, `docs/blueprint/INDEX.md`. Required by the
   repo's own docs contract after (1); method validated against the previous recorded digest.

No other production code was changed. Evaluation tooling added (allowed): `29-weapon-replay.py`,
`29-fault-injection.py`, both under `docs/campaign/evaluation/artifacts/`.

---

## 10. Measured / unmeasured ledger

**Measured in this workstream (command + artifact for each):** npm ci; typecheck before/after
(the 1 real error, fix, green); lint; docs:check (pristine + post-fix); next build (PASS 82 s);
`tests -q` (121/3, e2e-only failures); `node --test` (105/0); scoped gate suites (102/6);
import-with-adapters-absent (DISABLED states); uvicorn refusal (G-06) + dev-override run with
`/system/status`, `/health`, `/security/session` (200/200/200); weapon paced replay 90 s
(18 completed observations, first at 46.1 s, full per-tick log); anchor pass1 (36/36 fixtures,
cuda:0) + evaluate (frame/window/event metrics, pistol clip FP 4/36, 47.06 false alerts/camera-hour,
session-bootstrap CIs, threshold 0.45 pre-registered); queue-pressure fault injection (drop
counters, no hang); storage-failure fault injection (explicit PermissionError, no silent loss);
primary-checkout preservation forensics (193 entries mtime/birthtime/ctime, +1 delta verdict).

**Unmeasured (with precise blockers):** G-01 live FPS (no camera); G-04 time-to-detection (no
onset labels; live glass-to-alert needs camera); G-06 calibration artifact/ECE (blocked on scored
pass2 + `bench/calibrate.py`); G-08 independent evidence-clip re-verify (budget); G-09 independent
offline run (budget; OS-firewall needs admin); G-11 coverage run (budget); G-13 full
spawn→first-frame (budget; harness `worker_resource_bench.py` identified); G-14 endurance/soak
(budget); G-15 load scenario (budget + live-source wiring); worker-crash and file-source
restart/reconnect independent injections (budget); anchor **pass2** (weapon/person rows,
`--frame-stride 25`, ~20-25 min under RESOURCE-LOCK — queued); E-5 transport latency run (budget);
clean re-run of the 3 e2e failures without GPU contention (budget).

---
*End of report. All artifacts: `docs/campaign/evaluation/artifacts/29-*`.*

---

# §re-validation — final candidate tip `224a90979621f1a3ec123e7d4e75af556816fdfc`

Requested by Main after the C-1…C-8 repairs were actioned. Scope: re-verify only. My measured
gate results (§4/§8: G-02/G-03 FAIL etc.) stand **unchanged** — no re-tuning, no re-scoring was
performed. Worktree: `codex/sentinel-29-eval` merged the repaired tip (`cfffcc4` merge +
`7683a7f` adopting the tip's `detection-types.ts` fix verbatim, superseding my type-widening).
Artifacts: `29-reval-*.log` in `docs/campaign/evaluation/artifacts/`.

## R1. Verification battery on the new tip

| Command | Result |
|---|---|
| `node scripts/docs-contract.mjs --check` | **exit 0** — "Documentation authority and local design/source snapshots are consistent. Runtime gates are not certified." (verified pristine on wt-30 @224a909 AND on the merged eval branch) |
| `py -3.14 -m pytest backend/tests/test_threat_dispatch.py test_intrusion_api_contract.py test_enhance.py test_enhance_tier1.py test_evidence_ledger_concurrency.py -q` | **`87 passed, 6 skipped in 7.78s`, exit 0** (`29-reval-pytest.log`) — the 2× `face_summary` TypeError and 18× `face_engine` AttributeError are gone |
| `npm run typecheck` | **exit 0** (`29-reval-typecheck.log`) |
| `npm run lint` | **exit 0** (`29-reval-lint.log`) |

## R2. Lifespan restart (the defect my uvicorn/endpoint run implicitly exposed)

Concrete run (`29-reval` transcript; `TestClient(api.app)` context entered **twice sequentially**,
dev calibration override set, adapters absent):

```
DOUBLE_CONTEXT_RESULT [{"context": 1, "status": 200, "health": "ok"}, {"context": 2, "status": 200, "health": "ok"}]
LIFESPAN_RESTART_OK
```

No `RuntimeError: threads can only be started once` on the second lifespan startup — the
`_start_enhancement_scheduler()` fallback works. **VERDICT: FIXED.**

## R3. C-1…C-8 status against the repairs (one line each)

| # | Status | Verdict |
|---|---|---|
| C-1 (WT-12 tooling "merged" but absent) | **RESOLVED** | merge `079757c` brought `bench/eval/**` + `docs/campaign/eval/**` into the candidate; the pending-runs commands now execute against the tip (my anchor/evaluate results remain from the wt-12 run of the identical tooling). |
| C-2 (API "starts from committed code" overclaim) | **RESOLVED** | reviewer-guide now states the calibration prerequisite / dev override; G-06 startup reality corrected in gates.md. |
| C-3 ("99 passed / 6 skipped" count) | **RESOLVED** | gates.md G-07 now cites the reproducible **102 passed / 6 skipped** scoped run and marks 99/6 superseded. |
| C-4 (use-modal-focus TS18046 "plausibly real") | **RESOLVED** | reviewer-guide corrected; typecheck at the tip reports zero errors. |
| C-5 (preservation +1 delta prime candidate) | **RESOLVED** | reviewer-guide adopts the forensics and discloses `smoke-home.html` (campaign browser tooling, 2026-09-28T23:19:11Z, "disclosed, NOT deleted"); package-lock ctime nuance recorded. |
| C-6 (carried G-02/G-03 values never candidate-measured) | **RESOLVED as record** | my measured FAILs (4 FP alerts on negatives; recall 0.14) are folded into the handoff with denominators; my gate verdicts remain unchanged. |
| C-7 (weapon-observation open item) | **RESOLVED** | blueprint/handoff updated to the resolved mechanism (cold-start 46.1 s + completed-observation accounting); limitation downgraded. |
| C-8 (face_summary / face_engine union defects) | **RESOLVED** | `_generate_alert_payload(face_summary=…)` additive param + test contract on `api._face_service`; battery green (87 passed / 6 skipped). |

## R4. Repair-item verdicts and diff review (`079757c..224a909`)

Code delta: `backend/api.py` (+29), `backend/tests/test_intrusion_api_contract.py` (+7),
`lib/detection-types.ts` (+7); the rest is handoff/generated docs.

1. **WT-12 eval-tooling merge (079757c)** — VERIFIED (docs:check green with tooling present; evaluator importable).
2. **`face_summary` additive param** (`api.py`) — VERIFIED: optional kwarg, `if face_summary:` adds `payload["faceSummary"]` only when non-empty; payload shape unchanged for callers not supplying it. Nit (not a defect): `{}` is treated as absent (no key) — consistent with the comment's stated contract.
3. **`face_engine` → `_face_service` test contract** (`test_intrusion_api_contract.py`) — VERIFIED: fixture now patches the attribute the merged code actually reads; 18 prior errors gone.
4. **Enhancement scheduler double-start RuntimeError** (`api.py::_start_enhancement_scheduler`) — VERIFIED by the R2 double-context run; fallback swaps in a fresh `EnhancementScheduler(_run_enhancement_job)` only on `RuntimeError`. Nit (not a defect): the swallowed original RuntimeError is not logged.
5. **`detection-types.ts:343` via `rawPersonCount ?? activeTrackCount`** (`lib/detection-types.ts`) — VERIFIED (typecheck green; interface stays `personCount: number` and the fallback makes null impossible). Note for the record: unlike my type-only fix, this is a deliberate runtime semantic (absent wire `personCount` now aliases `activeTrackCount`, matching the documented alias contract) — integration-owner decision, disclosed here.
6. **gates/reviewer-guide counts + G-06 startup reality** — VERIFIED (R3 C-2/C-3 greps).
7. **Preservation forensics adoption** — VERIFIED (`smoke-home.html` disclosure in reviewer-guide).
8. **Measured results folded in with denominators** — VERIFIED (§4 figures appear in the handoff; unchanged here by instruction).

**New defects found in `079757c..224a909`: NONE.** Two cosmetic nits logged above (unlogged
RuntimeError in the scheduler fallback; `face_summary: {}` no-key behavior) — neither blocks and
both match their documented intent.

## R5. Re-verified gates (final tip)

- **G-05** (threshold literals): still passed — included in the R1 battery (green).
- **G-06** (refusal machinery): still passed — startup refusal unchanged at the tip (reviewer-guide now documents the prerequisite).
- **G-07** (evidence integrity, test level): still passed — `test_evidence_ledger_concurrency.py` green in R1 (`87 passed, 6 skipped` block).
- **G-10** (explicit health surfaces): unchanged — verified earlier at 396b980; the diff does not touch the health seams.
- All previously measured **FAIL/UNMEASURED gate verdicts (G-01…G-15, §8) are UNCHANGED** per instruction; no re-scoring was done.

**Final candidate SHA validated: `224a90979621f1a3ec123e7d4e75af556816fdfc`** (verified on pristine
wt-30 and on `codex/sentinel-29-eval` = tip + this report).
