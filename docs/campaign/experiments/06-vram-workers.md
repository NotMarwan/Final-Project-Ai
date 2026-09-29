---
authority: scoped
non_authoritative: true
---

# EXP-06 VRAM per camera process at 1 and 2 workers

- Hypothesis: A production-shaped inference process (violence torch + weapon/person ONNX on `cuda:0`) costs roughly 0.5–1.5 GB VRAM per process [INFERENCE from WT-09 §4]; two such processes fit the 12 GB RTX 3060 with ≥2 GB headroom, three would not.
- Requirement link: F-06 per-camera inference process; WT-09 §5 memory budget + §9 item 5; R-01 ≥3-camera rule input.
- Baseline: GPU idle used-memory sampled before each measurement (`nvidia-smi`).
- Candidate: 1 worker and then 2 workers, each a spawned process constructing the production model trio (violence `ViolenceInferencePipeline` on `cuda:0`, weapon + person ONNX sessions on CUDA EP through the production provider policy), 3 warm completed inferences per ONNX session so arenas reach steady size. Per-process VRAM via `nvidia-smi --query-compute-apps=pid,used_memory` (honest figure: context + ORT arena + torch), `torch.cuda.max_memory_allocated/reserved` inside the worker (torch allocator only — does NOT see ORT allocations), RSS per worker (16 GB system RAM shared). Tagged `processRunId` + `workerPid` per the WT-13 schema.
- Success criteria (defined BEFORE inspecting results): both measurements complete with per-pid samples for every worker; feasibility verdict rule: 2-worker total GPU used ≤ 10.0 GB (≥2 GB headroom) → N=2 GPU inference feasible on this card; else infeasible.
- Failure criteria / rollback: worker OOM or session-creation failure at 2 workers is itself the evidence (recorded as measured failure, N=2 infeasible). Measurement-only: nothing to roll back.
- Result: *(filled after run)*
- Verdict: *(filled after run)*
- Cold vs warm: load times recorded per model per worker; VRAM sampled at steady state after warm inference (2 s settle). No timing distributions claimed from this experiment.
