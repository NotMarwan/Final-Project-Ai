---
authority: scoped
non_authoritative: true
---

# EXP-1906 Model/data fit (fine-tuning candidate) — BLOCKED

| Field | Value |
|---|---|
| Worktree / branch | `wt-19` / `codex/sentinel-19-violence-eng` |
| Requirement link | item 6 (R6a/R6b) → F-48, S-21 |
| Baseline revision | `e86d34b5d16abcc133ad3470c8d135d00b2423d4` |

## Gate conditions (both required before any fine-tuning run)
1. WT-12 delivers **rights-checked labelled data** (redistribution-clear, with usable labels).
2. A **verified recoverable copy** of the existing weights exists (separate output path; originals never
   overwritten; nothing promoted silently).

## Status of each condition
1. **NOT MET.** WT-12 (EvalDataMethodology) reports (2026-09-29): nothing yet secured that is labelled AND
   redistribution-clear; KTH is non-commercial + citation (evaluation-only); RWF-2000 / XD-Violence /
   UCF-Crime remain excluded per WT-06 §3; AIRTLab and other permissive candidates under check.
2. **MET (weights side).** `backend/best_model.pt` is present and hash-verified:
   sha256 `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`, 149,344,325 bytes, and the
   checkpoint-internal provenance was recovered (EXP-1901). A recoverable copy would be taken to an
   untracked `assets/` path under the orchestrator's weight-governance rule at run time.

## Result
No training run was started; no output path was created; no weights were modified or promoted. This is not a
failure to execute — it is the explicit gate in the assignment being closed correctly.

## Verdict — **blocked**
Blocked item recorded precisely: fine-tuning is gated on rights-checked labelled data from WT-12 (item 6);
the alternative architecture (R(2+1)D-18) additionally has **no trained weights at all** in this repository
(EXP-1901), so even a throughput-motivated re-train would need that data first.

## What would unblock it
WT-12 confirms a rights-clear labelled corpus + split discipline (session-level hold-out, no tuning on final
test). Then: fine-tune in a separate output path, record dataset licence + hashes, and evaluate against
EXP-1902's sweep cells with the S-20 harness.
