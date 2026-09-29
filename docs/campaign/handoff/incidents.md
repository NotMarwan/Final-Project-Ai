---
authority: scoped
non_authoritative: true
---
# Incidents and process corrections (WT-30)

## 1. Process-kill incident (corrected record, verbatim from Main's corrected finding)

> "substring process-kills are FORBIDDEN (PID preview-and-confirm)"

The correction stands as the campaign rule: a kill must be issued against a previewed, confirmed PID —
never a substring/name match that can hit an unrelated process. No process-kill was issued by WT-30: the
only process-level operations in this workstream were `git merge`, `npm run docs:*`, `node`, and
`py -3.14 -m pytest` invocations launched in this worktree.

## 2. RESOURCE-LOCK ledger disputes (carried, resolved by arbitration)

- WT-23's EXP-23-03/04 timings were taken while RESOURCE-LOCK ownership was ambiguous (non-exclusive
  `mkdir -p` acquisition later clobbered by WT-21's `owner.txt`). Resolution: those timings are reported as
  **upper bounds** with the contention disclosed in the EXP cards; metric values/determinism/gate verdicts
  are unaffected; a clean re-measurement is queued (see `pending-runs.md` §3).
- WT-22's tracking-eval run is marked **CONTENDED** under the corrected atomic-`mkdir` protocol (no lock
  held by WT-22); a clean-window re-run is queued.
- WT-30 itself took **no** lock and ran **no** measurement, so it neither holds nor disputes a lock slot.

## 3. Tool-layer command duplication (this session, disclosed)

The harness re-sent some Edit/bash calls, so a few edits were applied twice against the same file. All
duplications were detected and repaired in the same turn: one double-inserted lifespan stop block, one
double-inserted `GET /evidence_derivatives/{alert_id}` route, and one wrongly-replaced test `def`
(restored). Verified afterwards: 0 conflict markers in `backend/api.py`, `backend/metrics.py`,
`backend/pipeline_render.py`, `lib/sentinel-store.tsx`, `backend/tests/test_metrics_telemetry.py`;
`py_compile` clean. Reviewers should still diff those files against the branch tips.

## 4. Weapon-observation item (escalated by the orchestrator) — RESOLVED (WT-29)

Original verbatim classification from Main's escalation (WT-15 EXP-15.01/15.02):

> "weapon observations unaccounted under paced replay with healthy engine status — cadence/validity gate
> suspected, unmeasured mechanism"

Nuance that was preserved while unresolved: WT-16's matched full-pipeline trials **did** measure weapon
windows completing (`weapon_window` p50 539.65 → 52.86 ms) and WT-18's FP runs produced weapon
detections/observations — so a production-wide weapon outage was unlikely.

**Resolution (WT-29 measured on the assembled candidate):** **18 completed observations** were recorded;
the mechanism is **cold-start + cadence accounting** (observations complete once the engine is warm and
the per-interval / `min_interval_ms` validity gate is satisfied). The item is closed; the F-09/F-10
blueprint limitations carry both the original verbatim classification and this resolution.

## 5. Preservation forensics (WT-29 C-5, adopted verbatim in substance)

- `smoke-home.html` — created **2026-09-28T23:19:11Z** in the primary checkout by campaign browser
  tooling. This is the **one campaign-caused untracked file**: **do NOT delete it; disclose it** (done here
  and in `reviewer-guide.md`).
- `desktop/package-lock.json` — **ctime 19:58Z rename-into-place**, content unchanged since May:
  a campaign-window **metadata event**; file content preserved.
- Verdict: tracked content + weights + settings preserved byte-identical; untracked space saw exactly one
  small campaign artifact + one metadata event; the pre-existing dirty work stands.
