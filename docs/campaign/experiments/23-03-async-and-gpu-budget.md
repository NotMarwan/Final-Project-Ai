---
authority: scoped
non_authoritative: true
---

# EXP-23-03 Post-alert placement: does enhancement add latency to the alert path, and does the GPU budget yield to detection?

Pre-registered before inspecting results. Workstream WT-23, slice F-52 (async scheduler + GPU budget).

- **Hypothesis**: attaching enhancement to the post-alert path costs microseconds on that path (bounded drop-oldest queue, no I/O, no model work inside `enqueue`), and tier-1 (learned) work never starts while detection is active — with an explicit counter when the deferral budget is spent rather than a silent stall. Tier-0 remains available as the CPU-only fallback.
- **Requirement link**: campaign brief step 4 ("enhancement runs AFTER alert dispatch, bounded queue, GPU budget shared with detection … if detection is active, enhancement must yield"); WT-08 catalog §4.3 rules 1–4 (alert path contains zero face/enhancement work; bounded queue with drop-oldest; capture work completes seconds later).
- **Baseline**: direct synchronous invocation on the alert path (counterfactual: any enhancement work inside `_emit_alert`/evidence finalization).
- **Candidate**: `EnhancementScheduler.enqueue` (lock-only, no I/O) + `GpuBudget.permits(tier)` policy.
- **Success criteria (defined BEFORE inspecting results)**: (1) `enqueue` p95 ≤ 1 ms over ≥ 5000 calls; (2) queue depth never exceeds the configured bound and every eviction is counted; (3) tier-1 job does not execute while `detection_active()` is true, tier-0 does; (4) once detection goes idle, the deferred tier-1 job executes; (5) with a permanently busy detector and an exhausted deferral budget the job is dropped **with a counter and a reason string**, not retried forever; (6) a broken detection probe fails closed (blocks tier-1).
- **Failure criteria / rollback**: p95 above 1 ms or any unbounded queue growth ⇒ the scheduler is not attachable to the alert path; silent drops (drop not counted) ⇒ reject.
- **Environment**: as EXP-23-01 (Windows 11, RTX 3060, Python 3.12.5, OpenCV 4.10.0). Stub handler, 640×480 synthetic frames, CPU. `RESOURCE-LOCK` held; no other workload running.

## Result (raw artifact `assets/measurements-wt23-async.json`)

> **CONTENDED-RUN DISCLOSURE (2026-09-29).** These timings were taken in the
> 01:38–02:2x window in which the campaign `RESOURCE-LOCK` ownership was
> ambiguous (my acquisition used `mkdir -p`, which is not exclusive, and WT-21
> subsequently rewrote `owner.txt`). Per the binding protocol correction these
> timing numbers are **upper bounds, not clean measurements**; the distortion /
> identity / utility *values* in EXP-23-01/02/04 are deterministic computations
> on fixed pixels and are unaffected. A clean re-measurement is queued
> (WT-21 → WT-19 → WT-16 → WT-23) with the command
> `py assets/measure_wt23_async.py` under atomic `mkdir` acquisition.
> Robustness argument for the headline claim: the measured p95 is ~350× below the
> 1 ms criterion, and `enqueue` consists only of a lock, a `deque.append`, an
> eviction counter and an `Event.set` — no I/O, no model call, no frame copy.

| Measurement | Value |
|---|---|
| `enqueue` latency, n = 5000 (no I/O, probe job kept queued) | median **0.0016 ms**, p95 **0.0029 ms**, max 0.249 ms |
| queue depth after 5000 enqueues into a size-16 queue | 16 (bounded) with **4984 counted evictions** (drop-oldest) |
| tier-0 job while `detection_active()` is true | **executed** (`tier0_completed_while_detection_active: true`) |
| tier-1 job while `detection_active()` is true | **did not start** (`tier1_started_while_detection_active: false`), 1 deferral recorded |
| tier-1 job after detection goes idle | **executed** (`tier1_completed_after_detection_idle: true`) |
| tier-1 job with permanently busy detector, deferral budget spent | **dropped**, counter `1`, reason `dropped tier1-drop: detection active, GPU budget exhausted` |
| broken detection probe (`detection_active` raises) | fails closed: tier-1 blocked (unit test `::test_gpu_budget_fails_closed_when_the_detection_probe_breaks`) |
| tier-0 default op cost (`gamma 1.2`, 224×224 crop of a 256×256 frame), n = 20 | median **0.11 ms**, p95 **0.135 ms** |

Sample counts/denominators: 5000 enqueue calls, 20 tier-0 timing repeats, 2 policy scenarios (busy/idle + budget-spent). Timing excludes process start-up and model loads by construction (no model is used in tier-0; tier-1 timings are in EXP-23-04). Clock: `perf_counter_ns` monotonic; values are *processing* costs, never glass-to-alert.

## Verdict

**adopt.** The measurement supports the placement rule: enhancement can be attached after alert dispatch (p95 = 2.9 µs on the alert path), the queue is bounded with counted drop-oldest overflow, and the GPU budget yields tier-1 to detection while leaving the CPU-only tier-0 path available — the fallback the brief asks for. Tier-1 deferral exhaustion and probe failure are both explicit, counted states, so the operator surface can report "capture/enrichment pending" instead of a silent stall.
