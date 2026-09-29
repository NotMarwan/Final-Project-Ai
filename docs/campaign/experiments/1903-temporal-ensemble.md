---
authority: scoped
non_authoritative: true
---

# EXP-1903 Temporal ensemble over stride offsets (R4)

| Field | Value |
|---|---|
| Worktree / branch | `wt-19` / `codex/sentinel-19-violence-eng` |
| Requirement link | R4 (WT-06 §6 rec. 4, §7.4) → F-14 interaction, F-07 |
| Baseline revision | `e86d34b5d16abcc133ad3470c8d135d00b2423d4` |
| Weights | `best_model.pt` sha256 `2c8222d3…20d1` |
| Env | RTX 3060, file-media demo AVIs (`demo_assets/videos/*.avi`), RESOURCE-LOCK held by WT-19 |
| Source mode | file-media, **unlabelled** → cost/semantics only, no accuracy claim |
| Artifacts | `exp1903-scores-k3.json`, `exp1903-scores-k5.json` |

## Hypothesis
Aggregating scores over K stride-offset windows (K ∈ {1,3,5}) improves temporal stability of the violence
score without adding inference cost and without double-counting decision votes.

## Candidate
`ViolenceInferencePipeline(ensemble_k=K, ensemble_agg∈{max,mean})`: the pipeline keeps the last K completed
per-window scores in a bounded deque and emits `agg(members)` as the per-observation score; EMA continues to
operate on the ensemble output. Default `K=1` reproduces the legacy single-window score exactly.

## Measured results
* **One observation per completion** (SC-7): observation ids are strictly monotone 1..N with
  `N = completed windows` for K=1/3/5 (7 streaming windows; 12/12 in the deterministic mode). The ensemble
  never emits per-member votes — WT-20 confirmed the decision layer votes once per `inference_sequence`.
* **Zero extra model forwards**: K only changes a deque aggregation (structural); each completion performs
  exactly one forward pass. Verified indirectly by identical completed-window counts (7/7/7) at K=1/3/5.
* **Aggregation cost measured** (micro-benchmark, median of 20,000 iterations): 0.20 µs (K=1), 20.5 µs (K=3),
  20.6 µs (K=5) — 0.04 % of the 55.5 ms per-window forward.
* **`ensemble_spread`** (population std over the K members) is populated for WT-20's decision-history
  covariate: 0.0000 for the first window, 0.118–0.334 once the deque fills.
* Ensemble score is monotone-max behaviour where expected (max over members ≥ last member score).
* Cross-run window-by-window comparison is **not** valid: the async ingress completes a
  pacing-dependent number of windows (see EXP-1904), so ensemble effect on accuracy needs the fixtures.

## Success criteria (set before the run)
FPs/hour do not increase while recall rises, at a stated cost in inferences/second (WT-06 §7.4).
Not decidable this session: no labelled positives/negatives exist yet.

## Failure criteria / rollback
If the ensemble created extra decision votes or extra forwards it would be rejected; it does neither.
`ensemble_k=1` is the default and parity with the baseline score path is proven in EXP-1904.

## Verdict — **adapt** (machinery + semantics adopted); **inconclusive** on accuracy/FP effect
Blocked metric: FPs/hour and recall delta per K — requires WT-12 fixtures (negatives suite landed later the
same day; positives with independent onset labels still at risk). Re-run command recorded in the handoff.
