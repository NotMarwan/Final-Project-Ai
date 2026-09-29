---
authority: scoped
non_authoritative: true
---

# EXP-15.03 IPC/memory: numpy→pickle cost at 640 max-side (SharedMemory gate)

- Hypothesis (R-01): For 1–2 cameras the per-frame numpy→pickle cost of the 640-max-side inference view (640×360×3 ≈ 675 KiB) is small relative to the 33 ms frame period and to model inference time; a SharedMemory ring is therefore NOT warranted and should be rejected in favor of the simpler mp.Queue path (which already carries the bounded-queue backpressure semantics).
- Requirement link: WT-15 step 3; R-01 (instrument IPC cost first; SharedMemory only if measured cost warrants); zero avoidable extra copies (compiled-code discipline).
- Baseline: `pickle.dumps`/`pickle.loads` of a real `FramePacket` (same fields as production, protocol HIGHEST) on the project venv interpreter; n=300; frame 720×1280×3 → `downscale_for_inference(., 640)`; single-threaded; no other workload active (short microbench; run inside my acquisition window to honor the letter of the lock rule).
- Candidate: SharedMemory ring (NOT implemented — gated by this measurement).
- Success criteria (defined BEFORE inspecting results): SharedMemory is considered only if (dumps+loads) median ≥ 20% of the 33.3 ms frame period (≥6.7 ms) OR p95 ≥ 50% of period (≥16.7 ms); otherwise REJECT SharedMemory and document the measured cost as the `stageIpcTransferMs` static benchmark for WT-13's `staticBenchmarks` block.
- Failure criteria / rollback: measurement-only; nothing to roll back. If the measured cost crosses the gate, the follow-up is a scoped design (hashed ring slots, segment lifecycle at media reset) — not silently implemented.
- Result: MEASURED (n=300, same lock window; artifact 15-03-ipc-pickle.json). FramePacket payload 691,585 B (640×360×3 + envelope). pickle.dumps p05/median/p95: 0.060/0.076/0.117 ms; pickle.loads: 0.032/0.035/0.057 ms; round-trip median ≈ 0.11 ms = 0.33 % of the 33.3 ms frame period (p95 round-trip 0.17 ms = 0.5 %). Live-protocol cross-check: stageEnqueueToDequeueMs median 0.87-0.97 ms (measured EXP-15.01/15.02) — consistent with serialization + bounded queue wait + scheduling as documented.
- Verdict: reject (SharedMemory ring NOT warranted — pre-registered gate was ≥6.7 ms median or ≥16.7 ms p95; measured is ~60× below). R-01 honored: instrument first, adopt SharedMemory only if measured cost warrants — it does not. Static copy audit: hot path produces exactly one inference view (cv2.resize output, or the documented passthrough edge pinned by test) plus one pickle copy into the queue buffer; no avoidable extra copies added by this slice.
- Cold vs warm: warm (first 10 iterations recorded separately as warmup; not mixed into distributions). Note: mp.Queue pickles in the producer feeder thread; the live `stageEnqueueToDequeueMs` includes transfer + bounded queue wait + scheduling and is reported separately (EXP-15.01/15.02).
