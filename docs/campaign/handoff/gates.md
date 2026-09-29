---
authority: scoped
non_authoritative: true
---
# Gate status on the assembled candidate (WT-30)

Status vocabulary: **passed** (measured, evidence path recorded) / **failed** / **unmeasured** (no run).
Rows marked *WT-29* are the independent evaluation's fresh runs on the assembled candidate and keep
their exact denominators. Rows not marked were carried forward from the owning workstream's own runs
(no new measurement by WT-30 itself).

| Gate | Status | Evidence or precise blocker |
|---|---|---|
| G-01 accuracy (KTH anchor) | **partial (WT-29)** | WT-29 ran the anchor on the assembled candidate; the recall-side results are recorded under G-03 and the negative-side under G-02. The full six-class suite remains uncovered (KTH-aux only). |
| G-02 negative-FP discipline | **FAILED (WT-29)** | Measured on KTH-aux negatives: **4 confirmed alerts on negatives**, plus the pistol clip **FP 4/36** → **47.06 false alerts/camera-hour** on KTH-aux. (Earlier context: EXP-1908 three pre-registered configs + WT-20's negatives-only screen; the six-class suite is declared uncovered.) |
| G-03 detection recall | **FAILED (WT-29)** | Recall **0.140 / 0.138 / 2-of-12 at threshold 0.45** (exact denominators as recorded in the WT-29 run). |
| G-04 real-time budget | **FAILED WITH EVIDENCE** | WT-19's measured floor: 1.62 s per window at stride-4 (below the stride-1 requirement). Disposition is a design decision, not a bug fix — flagged for independent review. |
| G-05 threshold literals | **passed (checker)** | WT-20's threshold-literal checker is green on the merged tree (`backend/tests/test_threshold_literals.py`); static-consistency gate, not a runtime result. |
| G-06 calibration startup gate | **machinery passed / blocked-on-data** | Gate implemented + verified single-application in `_init_engines` (`enforce_startup_calibration`). **Startup reality**: a bare start REFUSES with `CalibrationArtifactError`; endpoints serve only with `AI_SENTINEL_CALIBRATION_UNVERIFIED_OVERRIDE=I-UNDERSTAND-SCORES-ARE-UNVERIFIED`. Calibration itself is blocked-on-data until anchor scores enable EXP-20/21. |
| G-07 evidence integrity | **passed (tested)** | S-07 chain primitive + per-window integrity + artifact-hash discipline over git-stored bytes (WT-19/WT-15 suites); `test_evidence_ledger_concurrency.py` + `test_evidence_video.py` + `test_enhance*.py` reproduce as **102 passed / 6 skipped** (fresh WT-29 run — supersedes the earlier 99/6 count, which omitted three suites). |
| G-08 evidence clip completeness | **passed (measured)** | Explicit partial clips with reasons (never silently short "ready"); encoder E-7 measured as +3.1 % duration overhead with Chromium playback verified (WT-24). |
| G-09 offline operation | **passed in-process / OS-level open** | WT-27 proved the local Arabic report path offline in-process (404/401 contract edges recorded); an OS-firewall-enforced offline run is still open. |
| G-10 subsystem health | **passed (live block)** | `feature_health()`/DISABLED states wired and exercised by WT-13's telemetry tests + the WT-30 smoke import (enhance service builds; go2rtc sidecar reports DISABLED by default). |
| G-11 decision coverage | **unmeasured** | No coverage run recorded on the assembled tree. |
| G-12 hygiene | **passed (policy)** | Packaging credential guard (WT-28 7f1f854) + binaries/weights policy recorded; no credential, weight or large media added by the merges. |
| G-13 first weapon observation latency | **partial (WT-29)** | **46.1 s** to first weapon observation on the assembled candidate (measured). |
| G-14, G-15 | **unmeasured pending WT-29 follow-up** | Not measured in the runs recorded here. |

## Weapon-observation open item — RESOLVED (WT-29)

The WT-15 diagnostic item ("weapon observations unaccounted under paced replay with healthy engine
status — cadence/validity gate suspected, unmeasured mechanism") is **RESOLVED** by WT-29's measured
run on the assembled candidate: **18 completed observations** were recorded; the mechanism is
**cold-start + cadence accounting** (observations complete once the engine is warm and the
per-interval/min-interval validity gate is satisfied), not a production-wide weapon outage. The
F-09/F-10 blueprint limitations note this resolution alongside the original verbatim classification.

## Note for reviewers

`npm run docs:check` is GREEN on the candidate (verified after regeneration + fingerprint
re-assessment). That certifies documentation authority/consistency only — the checker's own output says
so: "Runtime gates are not certified."
