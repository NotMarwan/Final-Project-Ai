---
authority: scoped
non_authoritative: true
---

# EXP-17 E-5 transport latency (MJPEG publish-to-display)

- **Hypothesis:** MJPEG-over-HTTP delivery on the local machine shows publish-to-display latency below the 300 ms LAN target, measurable by burning a millisecond timer into a generated fixture, serving it through `/video_feed`, and diffing the displayed burned-in value against the browser wall clock at screenshot time.
- **Requirement link:** WT-17 step 4 (E-5, WT-10 catalog) → F-19 (MJPEG stream) / F-13 (display render + MJPEG encode); supports F-37 gating (`webrtc.enabled` stays false until a measured WebRTC row exists — this card measures the MJPEG baseline only).
- **Baseline (pre-registered):**
  - Commit: _the WT-17 branch tip at run time (recorded in the result below)_.
  - Model hashes: N/A for the transport row; the demo worker's normal inference runs concurrently and its only effect is CPU/GPU contention (recorded, not claimed as a variable).
  - Preprocessing / decision config: unchanged defaults (`config/thresholds.toml`, decision config from the running worker).
  - Data split: N/A — fixture is generated, not a dataset sample.
  - Env: Windows x64, RTX 3060 12 GB, Node 24, bundled ffmpeg (imageio-ffmpeg `ffmpeg-win-x86_64-v7.1.exe`), Chromium via DevTools.
  - Source mode: **generated fixture** (`testsrc2` + burned-in millisecond timer), served as a replay/demo source — **file-media**, never labelled live.
  - Resolution: fixture 854×480 @30 fps (`STREAM_QUALITY=medium` → Q75, stream width ≈854).
  - Workload: capture → render/annotate → JPEG encode → `/video_feed` multipart → browser `<img>` paint; the demo worker's inference runs as in normal operation.
- **Candidate:** per-part frame identity headers (`X-Frame-Sequence`, `X-Frame-Age-Ms`) + exponential-backoff stream restart (WT-17 changes) — the transport behaviour under measurement; both additive to the baseline delivery path.
- **Success criteria (defined BEFORE inspecting results):**
  - ≥ 30 timestamped samples (one screenshot + `Date.now()` per sample).
  - MJPEG publish-to-display median < 300 ms on this local (LAN-equivalent) browser; p05 and p95 reported; slow tail visible.
  - Sample count + denominator (samples attempted vs samples where the burned-in frame was identified) reported.
  - Fixture clock reference (`T0`, the wall time when media time 0 was first displayed) estimated from the first observed frame and disclosed with its uncertainty.
- **Failure criteria / rollback:** a median ≥ 300 ms rejects the "LAN-fast MJPEG baseline" claim and is reported as-is (no threshold tuning). If the burned-in frame cannot be identified for >20 % of samples the method is reported as inconclusive and the raw screenshots are kept. Rollback for the code path: revert the additive headers/restart hunks (the delivery path is unchanged otherwise).
- **Explicit non-claims:** this row is **publish-to-display**, NOT glass-to-alert and NOT glass-to-display (sensor readout + 3A + USB/ISP + driver buffering are structurally invisible to `captured_at`, per WT-10 §9). The fixture has no camera and no onset labels.
- **Cold vs warm:** separated — the first frames after worker start are reported separately from the steady-state samples.
- **Result:** _filled after the measured window (RESOURCE-LOCK slot 8, per the orchestrator queue)._ Raw artifacts (screenshots + sample table + script) under the run directory; SHA-256 recorded in the run report.
- **Verdict:** _pending measurement._
