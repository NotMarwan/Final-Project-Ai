---
authority: scoped
non_authoritative: true
---

# EXP-21-01 YuNet CPU detection latency on fixture frames

- Hypothesis: YuNet (OpenCV Zoo 2023mar, MIT) detects faces on repository demo-clip fixture frames at CPU latency consistent with the WT-08 research reference (7.56 ms median, CPU), and full-resolution detection latency is characterized well enough to size the off-alert-path sampling budget.
- Requirement link: S-15 (faces) / F-56 (incident face detection + capture; orchestrator-reallocated from a proposed F-50); WT-08 "run detection at full decoded resolution (or the largest budget allows)".
- Baseline: research reference only — WT-08 measured YuNet median 7.56 ms CPU (recorded in `wt-08/docs/campaign/research/08-faces-tracking-imaging.md`); no local baseline existed at `e86d34b5`.
- Candidate: `backend/face_detect.py` `YuNetFaceDetector` (weights `assets/yunet/face_detection_yunet_2023mar.onnx`, sha256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`), score 0.6 / NMS 0.3 / top_k 5000; 27 fixture frames (`assets/fixtures/*.jpg`, extracted from `demo_assets/videos/*.avi`): 9× 1920x1080, 18× 480x360; 20 warm repeats per frame after 1 cold call; Windows 11 x64, Intel CPU (RTX 3060 present but UNUSED — CPU path), Python 3.12 / OpenCV 4.10.0; source mode = file-media fixtures (NOT live capture).
- Success criteria (defined BEFORE inspecting results): warm median at 480x360 ≤ 23 ms (≤3× the 7.56 ms reference); 1080p latency reported per class so the sampling budget is derivable; no hidden stalls (p05/p95 always reported).
- Failure criteria / rollback: median > 23 ms at 480x360 ⇒ do not adopt YuNet on CPU at this cadence (fall back to sparser sampling or reconsider detector); unbounded latency tail ⇒ detector unusable on the capture path (would force removal from `on_evidence` consumption).
- Result (raw artifact `docs/campaign/experiments/artifacts/21-face-detect-measurement.json`, sha256 `7e8e6ad5b257d0d617fe54138432bc41503cc6557026c26c2b37d07c483acfec`):
  - **CONTENDED-RUN DISCLOSURE (2026-09-29)**: WT-23 confirmed brief CPU bursts (test suite, `docs:sync`, and a smoke script loading YuNet+SFace+AlexNet twice) executed inside my measurement window 01:53:53–01:55:48; WT-15 additionally self-reported short pytest bursts (~4–5 s each, exact timestamps unrecorded) around the same period. Per the lock protocol correction these latency numbers are **UPPER BOUNDS, not clean measurements** (seconds-scale bursts can inflate p95 and slightly lift medians). Acquisition was the correct atomic `mkdir`; the overlap was external. A ~2-min clean confirm re-run is queued with the scheduling owner at queue position 3 (after WT-19 and WT-16); if it lands before integration this card is updated, else the label stands. Detection COUNTS are load-independent and stand regardless.
  - Warm latency per resolution class (n = frames × 20 repeats):
    - 480x360: n=360, p05 **8.959 ms**, median **9.957 ms**, p95 **12.044 ms**, mean 10.218 ms
    - 1920x1080: n=180, p05 **140.156 ms**, median **154.878 ms**, p95 **197.468 ms**, mean 160.311 ms
  - Cold first-call per frame (n=27, includes the lazy session creation on the very first): median 9.790 ms, p95 183.420 ms (the p95 tail = first-ever 1080p call + session init).
  - Detection output over the same 27 frames: 7 faces across 4 frames at native resolution (no ground truth labels — this is a detection-output count, not an accuracy figure).
- Verdict: **adopt** — 480x360 median 9.957 ms (≤23 ms criterion, and same order as the 7.56 ms research reference at comparable scale). The 1080p class (~155 ms) is adopted ONLY with sparse sampling off the alert path (default `FACE_CAPTURE_SAMPLE_EVERY=3`, documented recommendation ≥10 for 1080p CPU deployments).
- **CLEAN CONFIRM RUN (supersedes the contended latency figures above)**: re-run under a solo RESOURCE-LOCK window (atomic `mkdir` acquisition 02:20:10, released 02:22:16; run wall ~31 s; no other holder, CPU-only, single process; same 27 fixtures, 20 warm repeats). Raw artifact `docs/campaign/experiments/artifacts/21-face-detect-confirm.json`, sha256 `db5ddf712d939bc4a70842ca7829b9996759c922d24fb0161a0c75fb02d4e095`.
  - 480x360 warm: n=360, p05 **8.723 ms**, median **9.358 ms**, p95 **10.736 ms**, mean 9.528 ms
  - 1920x1080 warm: n=180, p05 **127.787 ms**, median **134.405 ms**, p95 **146.538 ms**, mean 135.638 ms
  - Cold first-call (n=27): median 9.565 ms, p95 159.916 ms (lazy session-init tail).
  - Detection counts identical to the first run (7 native / 6 max-640 across the same frames) — deterministic outputs re-confirmed; failure-state outcomes identical.
  - Contention effect quantified: the contended run's medians were +0.6 ms (480x360) and +20.5 ms/+15% (1080p), p95 +51 ms — consistent with the disclosed bursts; the CLEAN numbers are the reported latency evidence. All success criteria hold a fortiori (480x360 median 9.358 ms ≤ 23 ms).
  - runProvenance (WT-13/WT-12 join convention): run_id `wt21-yunet-latency-confirm-20260929T0220`, sourceMode `file-media`, adapterState baseline `e86d34b5` + cherry-pick `e023b59`, fixtures joined by `fixture_id` + per-frame content in the artifact; distinguishes this clean run from the earlier contended run (`wt21-yunet-latency-20260929T0153`).
- Cold vs warm: separated above (cold = first call per frame incl. lazy init; warm = 20 steady-state repeats). Completed-inference timing (`detect()` returns detections; no async queue inside YuNet).
- Variability: 20 repeats/frame × 27 frames; p05/median/p95 reported per class; the clean run supersedes the contended run for latency only — counts were deterministic in both.
