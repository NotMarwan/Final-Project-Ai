---
authority: scoped
non_authoritative: true
---

# EXP-2203 Alert dispatch path is unaffected by incident capture (async queue)

- **Hypothesis**: with the incident capture queue enabled, `RenderThread._emit_alert`
  costs the same as without it, because `trigger()` only snapshots ring references and
  enqueues; all scoring/crop/record work happens on the capture worker thread.
- **Requirement link**: S-04; campaign rule "zero face/enhancement/recording work in the
  alert dispatch path (proof in tests: alert path timing unaffected with capture enabled)".
- **Baseline**: `RenderThread` with `incident_capture=None` (previous behaviour).
- **Candidate**: same `RenderThread` with an `IncidentCapture` holding a populated
  pre-event ring (20 sampled frames) and `post_seconds = 3.0`.
- **Success criteria (before results)**: (a) zero calls into the scorer during
  `trigger()`; (b) no job is resolved synchronously; (c) median `_emit_alert` duration
  within 5 ms of the baseline; (d) a capture subsystem failure never blocks or delays the
  alert and is surfaced as degraded health.
- **Failure criteria / rollback**: any inline scoring, any synchronous job completion, or
  a >5 ms median regression → capture wiring reverted to a no-op flag
  (`incident_capture=None`), feature reported as not done.
- **Result** (`tests/test_alert_path_capture.py`, run 2026-09-29 on the pinned
  environment; see the scoped suite output in the handoff):
  - sabotaged-scorer proof: `trigger()` returns `state="pending"` with **0** scorer calls
    and < 1 ms; the worker then attempts exactly 1 selection, and its failure is recorded
    as `failed` (never raised into the alert path);
  - median `_emit_alert` duration with capture enabled vs disabled differed by less than
    the 5 ms budget — the enqueue is a rounding error next to the JPEG encode + annotation
    work that dominates the call;
  - `BrokenCapture.trigger()` raising `RuntimeError` still delivered the alert and marked
    `health["incident_capture"] = "degraded"`.
  Denominators: 5 `_emit_alert` calls per arm (median of 5); queue-shaped tests use 12
  triggers against capacity 3 (9 dropped, telemetry exact).
- **Verdict**: **adopt**. Honest limits: this is a microbenchmark of one method with a
  3 ms post window, not a full pipeline run; the 5 ms budget is deliberately loose to
  avoid flaky timing assertions, so it rules out *synchronous capture work* (which costs
  tens of ms per scored frame) rather than detecting sub-millisecond deltas.
- **Cold vs warm**: not applicable — no model inference and no GPU; timings are pure
  Python/JPEG-encode work on synthetic 32–64 px frames, CPU only.
