---
authority: scoped
non_authoritative: true
---

# EXP-21-02 Native-resolution vs 640-max-side face detection on fixtures

- Hypothesis: running YuNet at the full decoded resolution detects faces that are lost when frames are downscaled to the 640-max-side geometry of WT-22's scoring ring (the WT-08 "detection at full decoded resolution" recommendation is load-bearing on CCTV-grade footage).
- Requirement link: S-15 / F-56; WT-08 §2 ("run detection at full decoded resolution … min-face-size gate for REPORTING, not detection"); frame-crop reference contract with WT-22 (`bbox_space`, sparse native ring request).
- Baseline: same YuNet candidate as EXP-21-01 (weights sha256 `8f2383e4…52fa4`), detection on each fixture frame resized so max side = 640 (INTER_AREA) — the WT-22 ring geometry.
- Candidate: same detector at native frame resolution (1920x1080 / 480x360).
- Success criteria (defined BEFORE inspecting results): native counts ≥ 640-max-side counts on every frame AND strictly greater on at least one frame (i.e. downscale loses at least one face somewhere in the set).
- Failure criteria / rollback: no per-frame loss ⇒ the cheaper 640 geometry would suffice for crops and the native-ring request to WT-22 is withdrawn.
- Result (same raw artifact as EXP-21-01, `docs/campaign/experiments/artifacts/21-face-detect-measurement.json`, sha256 `7e8e6ad5b257d0d617fe54138432bc41503cc6557026c26c2b37d07c483acfec`; counts are deterministic pixel computations — the contention disclosure of EXP-21-01 does not affect them):
  - Totals over 27 frames: native **7** faces across **4** frames; 640-max-side **6** faces across **4** frames.
  - The per-frame loss: `FXC43fACfPc__f000000.jpg` (1920x1080) — native **2**, max640 **1**. All 480x360 frames are below 640 max side already (scale 1.0) and match trivially.
  - Denominator caveat: the fixture set has NO labeled ground truth (no hand-verified face census). These are detector outputs under two geometries on the same pixels; a face "lost by downscale" here means "fired at native, not fired at 640", not "human-visible face missed".
- Verdict: **adopt** — face crops and association consume native-resolution frames (the evidence pre/post fan-out is native at baseline); WT-22's sparse native ring accepted when available (`bbox_space: "source"`); 640 ring frames remain fine for best-frame SCORING only. Impact: crop path records `bbox_space` per crop; both box copies always carried.
- Cold vs warm: not applicable (count comparison, single pass per geometry).
- Variability: deterministic for fixed pixels/model; no repeats needed.
