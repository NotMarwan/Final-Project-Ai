---
authority: scoped
non_authoritative: true
---

# EXP-21-03 Failure states: tiny face, motion blur, no face (detection vs reporting gate)

- Hypothesis: the capture path behaves honestly at the failure edges — a tiny face is DETECTED but suppressed from capture with explicit reasons (reporting gate ≠ detection gate), a blurred face is handled without silent zeros, and a face-free scene produces no fabricated detections; combined with the unit-tested absent states, every no-capture outcome yields an explicit `absent` record with reasons.
- Requirement link: S-15 / F-56; WT-08 §2 (min-face-size gate for REPORTING, IED px); campaign honesty rule (report the absence; never substitute generated detail).
- Baseline: none (behavioral edges are new surface).
- Candidate: `face_detect.YuNetFaceDetector` + `face_detect.reporting_gate` (min_face_size_px=36, min_ied_px=12) + `face_capture.FaceCaptureService` absent states.
- Success criteria (defined BEFORE inspecting results): (1) tiny face: detected ≥1 AND reportable == 0 with explicit `face_box_too_small`/`ied_too_small` reason strings; (2) blur case: outcome recorded either way — a miss must surface as `absent/no_face_detected_in_window`, never as a silent empty capture; (3) no-face scene: 0 detections (no false fire on the synthetic scene).
- Failure criteria / rollback: tiny face silently captured as usable ⇒ gate broken (rollback the capture path); tiny face silently dropped with no count ⇒ honesty rule broken; false fire on the flat scene ⇒ threshold unusable at 0.6.
- Result (same raw artifact as EXP-21-01, sha256 `7e8e6ad5b257d0d617fe54138432bc41503cc6557026c26c2b37d07c483acfec`; content-deterministic — unaffected by the EXP-21-01 contention disclosure):
  - **tiny face** (whole 1920x1080 fixture frame resized 1/6 → 320x180; the known face box shrinks to ~8 px): detected **1**, reportable **0**, reasons `["face_box_too_small:8.3px<36px", "ied_too_small:4.5px<12px"]` — suppression with explicit reasons, detection itself not gated. ✔ criterion 1.
  - **motion blur** (Gaussian σ=8, 21×21 kernel over the face region of the same frame): detected **1**, reportable **1** — this single blur case did NOT defeat the detector. Honest scope note: one Gaussian kernel is NOT a motion-blur robustness evaluation; no blur-robustness claim is made from n=1 transform. ✔ criterion 2 (outcome recorded; the service would capture).
  - **synthetic no-face scene** (480x640 flat gray + rectangle): detected **0** — no false fire on this scene; n=1 scene, no false-positive-rate claim. ✔ criterion 3.
  - Service-level absent states (no face / all suppressed / no frames / detector absent) are covered by deterministic unit tests (`test_face_capture.py::test_service_absent_states`, `test_service_no_frames_in_window_absent`) rather than fixtures — sample counts 1 per case, asserted reasons verbatim.
- Verdict: **adopt** — gate + absent-state behavior shipped as designed. Limits recorded: blur case n=1 Gaussian (not a sweep), no-face scene n=1 synthetic, tiny-face case n=1 transform of one face.
- Cold vs warm: not applicable (behavioral outcomes).
- Variability: none claimed; each failure case is a single deterministic transform (denominators given above).
