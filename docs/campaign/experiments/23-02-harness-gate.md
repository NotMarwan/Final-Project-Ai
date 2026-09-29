---
authority: scoped
non_authoritative: true
---

# EXP-23-02 Harness gate: does it refuse identity-altering / generative-surrogate artifacts?

Pre-registered before inspecting results. Workstream WT-23, slice F-54 (distortion/utility harness).

- **Hypothesis**: the harness (PSNR + SSIM + LPIPS + transient SFace identity-similarity bound + YuNet detectability utility) accepts mild deterministic derivatives inside the tier-0 envelope and **refuses** artifacts that destroy structure or invent texture, with the failing bound named. A tier-1 artifact is refused when LPIPS is not measurable at all (no silent "probably fine").
- **Requirement link**: WT-08 catalog §5.3 ("distortion measurement harness before any enhancement ships"; "identity-altering enhancement … is disallowed for capture use"), §5.2 items 3–4 (perception–distortion tradeoff; PULSE: a low-resolution face maps to many plausible faces).
- **Baseline**: the untouched native crop (identity similarity 1.0000, PSNR ∞, LPIPS 0.00000).
- **Candidate / adversarial set** (n = 3 synthetic adversarial transforms of one public-domain crop, deliberately outside anything tier-0 can produce): identity-erasing Gaussian blur (31×31, σ=9), "invented texture" surrogate (additive Gaussian σ=60), posterize/crush (quantize to 48 levels).
- **Success criteria (defined BEFORE inspecting results)**: (1) all three adversarial cases must report `passed: false` with at least one named failing bound; (2) mild tier-0 candidates must report `passed: true`; (3) a candidate whose score cannot be measured must be reported as `null` plus an explicit status — never as a passing number; (4) `assert_within_bounds` must raise for both a failed report and an unmeasured report.
- **Failure criteria / rollback**: if an adversarial case passes, the corresponding bound is tightened (documented change) or the metric is declared unfit; if a mild tier-0 case fails, the op set is dropped from defaults (see EXP-23-01).
- **Environment/weights**: as EXP-23-01; LPIPS 0.1.4 (BSD-2-Clause) with the verified local AlexNet trunk; SFace/YuNet MIT (OpenCV Zoo); no camera (file-media only). `RESOURCE-LOCK` acquisition was not exclusive for this window (disclosed in EXP-23-03); no timing claim is made here — all numbers are deterministic computations on fixed pixels.

## Result

Adversarial cases (tier-1 bounds, `docs/campaign` run of 2026-09-29, n = 3):

| Adversarial transform | PSNR dB | SSIM | LPIPS | identity sim. | YuNet before→after | Verdict |
|---|---|---|---|---|---|---|
| identity-erasing blur (31×31, σ=9) | 20.30 | 0.5081 | 0.7255 | 0.2251 | 0.937→0.816 | **refused** — `ssim<0.7`, `lpips>0.35`, `identitySimilarity<0.92` |
| invented-texture surrogate | 13.90 | 0.1153 | 1.0196 | *null* (no face found in derivative) | 0.937→*none* | **refused** — `psnrDb<20`, `ssim<0.7`, `lpips>0.35`, `identity-not-measurable(no-face-detected-in-derivative)`, `face-lost-by-enhancement` |
| posterize/crush (48 levels) | 19.59 | 0.6222 | 0.3113 | 0.7928 | 0.937→0.923 | **refused** — `psnrDb<20`, `ssim<0.7`, `identitySimilarity<0.92` |

Mild deterministic cases (from EXP-23-01): all six op sets that stayed inside the tier-0 envelope reported `passed: true`; the one that left it (`CLAHE+gamma+denoise`, identity 0.8960) reported `passed: false` with the bound named.

Unmeasured-metric behaviour: with no LPIPS backend configured, `evaluate` returns `lpips: null` with `lpipsStatus: "lpips-unavailable"` and `notes`, and a tier-1 gate (`require_lpips=True`) then reports `passed: false` / `lpips-not-measurable`. Verified in `backend/tests/test_enhance.py::test_tier1_gate_refuses_when_lpips_cannot_be_measured` and `::test_harness_without_backends_reports_unmeasured_metrics_not_fake_numbers`.

Identity-bound discrimination (identical crop vs destroyed structure): cosine 1.0000 vs 0.2251/blur and 0.7928/posterize — the bound separates "same face pixels, mild tone change" from "face no longer the same evidence" with a wide margin on this fixture.

Sample counts/denominators: 3 adversarial transforms, 6 tier-0 candidates, 1 source image/1 face, bounds as in `enhance_harness.default_bounds`. Single-subject engineering measurement; not a population estimate.

## Verdict

**adopt** the harness as the tier-1 precondition and as the tier-0 recording requirement:

- the gate refuses every adversarial case with a named bound, and refuses unmeasurable LPIPS rather than assuming;
- the transient identity bound is computed on embeddings that are never returned, logged or stored (`IdentitySimilarity.measure` returns only a scalar; policy test `::test_identity_similarity_is_one_for_identical_crops_and_drops_for_destruction`);
- LPIPS is only reported when the official linear weights *and* a verified trunk are loaded, with a self-check (identical pair must measure 0.000000) and trunk provenance in the record — a silently mis-loaded trunk is refused (`lpips self-check failed`), not reported as a number.
