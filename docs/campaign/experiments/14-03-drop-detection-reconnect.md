---
authority: scoped
non_authoritative: true
---

# EXP-1403 Drop detection + reconnect storm (WT-10 E-3)

- Hypothesis: counting every drop-NEWEST event on the bounded inference queue and tracking inter-arrival gap stats makes overload visible (runtime-map R-2 closure), and exponential reconnect backoff (1,2,4,...,30 s cap, +/-20% jitter) survives a reconnect storm without zombie state and without the fixed 2 s sleep.
- Requirement link: F-38 (camera health), R-1/R-2 (queue drop invisibility), WT-10 E-3 + §4.4 backoff recommendation.
- Baseline: commit e86d34b; `except queue.Full: pass` (silent drop, no counter), CaptureThread.reconnect() fixed 2.0 s wait, no gap stats.
- Candidate: commit e7dc49e/7e4e5d6; bounded_put_drop_newest() counts frameQueueDropped + samples frameQueueDepth; CaptureStats keeps readGapP50/P95/Max+SampleCount, duplicateFrameCount, reconnectCount, stageFrameRead*; next_backoff_delay() pure schedule function; reconnect() states interrupted -> reconnecting -> ok|interrupted.
- Success criteria (BEFORE results): (a) slow-consumer harness (producer ~100 Hz, consumer ~10 Hz, queue depth 3) shows frameQueueDropped > 0 with exact counts and depth <= 3; (b) backoff schedule = [1,2,4,8,16,30,30,30] s at jitter 0 (unit); jitter samples stay within [0.8x, 1.2x] of base over 220 draws; (c) reconnect storm (5 consecutive open failures then success) records delays [0.01,0.02,0.04,0.05,0.05] s in the scaled config, reconnectCount=1, final state ok, single thread; (d) stop_event interrupts the backoff wait.
- Failure criteria / rollback: any uncounted drop path or storm leaving state stuck/zombie rejects; revert e7dc49e/7e4e5d6.
- Result: MEASURED harness (producer 200 puts @ ~1 ms vs ~10 Hz consumer, queue maxsize=3; counts deterministic; Contention label per Main arbitration 2026-09-29: latency-sensitive figures are POTENTIALLY CONTENDED (WT-19 hold-timestamp dispute over the 02:23-02:27 window; deterministic byte totals/counts stand as measured).): consumed=7/200, frameQueueDropped=193/200 (denominator 200), frameQueueDepth=3 — every drop counted, none silent (R-2 closed). Schedule/backoff/storm acceptance proven timing-independently in tests/test_capture_freshness.py: backoff [1,2,4,8,16,30,30,30] s at jitter 0; 220 jitter draws within [0.8x,1.2x] of base; reconnect storm (5 consecutive open failures then success) recorded delays [0.01,0.02,0.04,0.05,0.05] s (scaled config), reconnectCount=1, final state ok, no threads spawned; failure state "interrupted"; stop_event interrupts the backoff wait. Gap stats + stageFrameRead + duplicate counters validated with scripted clocks (readGap 39/39 ms, duplicateFrameCount=1/3). Scoped suite 36/36 green.
- Verdict: adopt
- Cold vs warm: timing-independent (scripted clocks + RecordingEvent); wall-clock values in the Result section are informational only.
