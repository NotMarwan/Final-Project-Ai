---
authority: scoped
non_authoritative: true
---
# Pending integration-time runs (WT-30) — exact commands, nothing fabricated

No run below was executed by WT-30 (budget end). Run them in this order under the RESOURCE-LOCK protocol
(atomic `mkdir`, script-clock timestamps in the ledger). A command that cannot execute is UNMEASURED.

## 1. WT-12 two-pass anchor (priority a)

```bash
cd "C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-30"
# pass 1 — all 36 fixtures, run id campaign-baseline-2026-09-29-anchor-pass1 (~12 min)
# pass 2 — weapon/person counting, cadence every 25th frame (~20-25 min)
```
Exact invocations are in `docs/campaign/eval/12-eval-protocol.md` (merged from WT-12) and
`docs/campaign/experiments/EXP-12-baseline-eval-anchor.md`; write `Result`/`Verdict` only from real output.

## 2. WT-17 E-5 transport latency (priority b)

Fixture `e5-run/e5-timer-90s.mp4` (sha256 `8f7d129b…`); harness
`docs/campaign/engineering/17-e5-measure.py` + `17-e5-samples.py`; card
`docs/campaign/experiments/17-e5-transport-latency.md` (fill Result/Verdict, never invent).

## 3. WT-23 clean re-measure (priority c, ~4 min)

```bash
cd "C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-23"   # or copy assets/
py assets/measure_wt23_tier1.py
py assets/measure_wt23_async.py
```

## 4. WT-20 EXP-20/21 on scored anchor outputs (priority d, needs §1)

One sweep command as documented in `docs/campaign/experiments/20-threshold-policy.md`
(+ `21-calibration-temperature.md`); then WT-19's tail (EXP-1908 follow-up on the anchor outputs).

## Also owed (not measurement runs)

- `npm run typecheck`, `npm run lint`, `npm run build` **with `node_modules` installed in the worktree**.
- `py -3.14 -m pytest tests/e2e -q` with the backend running.
- Baseline-failure citation: reproduce `test_threat_dispatch.py` (2 failures) and
  `test_intrusion_api_contract` (face_engine errors) against the wt-01/wt-15 records before calling them
  unrelated.
- Preservation check vs `local://sentinel-preflight.md` (192 entries: 11 M / 4 D / 177 ??; model hashes).
- Fresh-clone proof (`scripts/provision_assets.py` or README section) from committed code + declared assets.
- Blueprint semantic re-assessment (entry claims + branch deltas + F-50…F-58/N-17 ID table + weapon
  observation limitation).
