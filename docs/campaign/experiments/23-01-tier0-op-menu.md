---
authority: scoped
non_authoritative: true
---

# EXP-23-01 Deterministic tier-0 enhancement: distortion and utility of the op menu

Pre-registered before inspecting results. Workstream WT-23 (image enhancement),
new slice F-52/F-53 (see the blueprint delta in `23-enhancement-honesty.md`).

- **Hypothesis**: deterministic tier-0 operations (crop / CLAHE / gamma / classical denoise / percentile stretch) improve human review legibility of a person crop while keeping measured distortion inside a stated envelope, **and** they do *not* materially raise YuNet detection scores — i.e. tier-0 is a review aid, not a detection booster. A subset of the op menu (gamma-only) should be visibly cheaper in distortion than CLAHE or denoise.
- **Requirement link**: "useful crop enhancement that never endangers evidence integrity" (campaign brief WT-23); derivative discipline and preservation assumption of SWGIT §11 (WT-08 catalog §5.2–5.3); F-21 evidence clip writer + F-22 evidence ledger (SC-8), F-30 `face_intel.py` MUST stay unwired.
- **Baseline**: commit `e86d34b5d16abcc133ad3470c8d135d00b2423d4` (`final-demo-transfer`) + branch `codex/sentinel-23-enhancement`; the untouched crop of the same pixels ("crop only").
- **Candidate**: the same crop through `crop`, `clahe`, `gamma`, `contrast_stretch`, `denoise_lite` in the fixed order implemented in `backend/enhance.py::apply_tier0`; parameters recorded per output.
- **Success criteria (defined BEFORE inspecting results)**: (1) every candidate publishes a derivative whose harness block has `psnrDb`, `ssim`, `lpips` and `identitySimilarity` all *measured* (no placeholders); (2) each candidate that ships as a default passes the tier-0 bounds (`psnrDb>=14`, `ssim>=0.60`, `lpips<=0.55`, `identitySimilarity>=0.90`, face preserved); (3) byte-identical output for the same input+parameters over 3 repeats (determinism); (4) utility reported honestly — if detection scores do not improve, the verdict must say so.
- **Failure criteria / rollback**: any op set that fails the tier-0 bounds is removed from the default op set (kept available but opt-in), and the measured failure is recorded here. If determinism fails (more than one unique output hash), tier 0 is rejected outright.
- **Fixture**: `assets/fixtures/face_pd_nasa.jpg` — Wikimedia Commons `File:Neil Armstrong pose.jpg` (NASA photo ID S69-31741), **public domain**, fetched 2026-09-29, SHA-256 `6c7866ed5f9ef8777db5840055bfac34615a5449b89f0be788c955e29613ca0a` (960×1200). Face box from YuNet: `[510, 225, 671, 434]`, IED 74.25 px, detection score 0.9321. Native crop 305×481.
- **Environment**: Windows 11 x64, RTX 3060 12 GB, 16 GB RAM, Python 3.12.5, OpenCV 4.10.0, NumPy 1.26.4, onnxruntime 1.18.0, torch 2.3.0+cu118. **Source mode**: file-media (no camera device exists) — never reported as live capture. CPU-only for tier 0. `RESOURCE-LOCK` was attempted for this run but the acquisition was **not exclusive** (non-exclusive `mkdir -p`; the ownership ambiguity of the 01:38–02:2x window is disclosed in EXP-23-03). No timing claim is made in this card: every number here is a deterministic computation on fixed pixels, unaffected by contention.
- **Raw artifact**: `assets/measurements-wt23.json` (untracked scratch output; hashes below). Harness weights: YuNet `sha256 8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` (MIT), SFace `sha256` recorded in the artifact (MIT), LPIPS 0.1.4 (BSD-2-Clause) + torchvision AlexNet trunk `alexnet-owt-7be5be79.pth` `sha256 7be5be791159472b1fbf3c69796f7cb30dca7ad8466c2df70058c37116cdee02` (see the honesty doc).

## Result — op menu on the native crop (n = 1 source crop; deterministic ops ⇒ repeat variance is exactly 0 by construction, verified: 3 repeats, unique output hashes = 1)

| Op set | PSNR dB | SSIM | LPIPS | identity similarity | YuNet score before→after | tier-0 bounds |
|---|---|---|---|---|---|---|
| crop only | ∞ | 1.0000 | 0.00000 | 1.0000 | 0.937→0.937 | pass |
| gamma 1.2 | 25.96 | 0.9766 | 0.01014 | 0.9935 | 0.937→0.937 | pass |
| contrast stretch (1–99 %) | 31.52 | 0.9974 | 0.00114 | 0.9972 | 0.937→0.938 | pass |
| CLAHE 2.0 (LAB-L, 8×8) | 20.12 | 0.7677 | 0.12022 | 0.9158 | 0.937→0.937 | pass (thin margin) |
| CLAHE 2.0 + gamma 1.2 | 17.77 | 0.7411 | 0.11589 | 0.9130 | 0.937→0.937 | pass (thin margin) |
| CLAHE 2.0 + gamma 1.2 + denoise-lite (h=3) | 17.80 | 0.7454 | 0.12945 | **0.8960** | 0.937→0.936 | **FAIL** `identitySimilarity<0.90` |

Enhancement applied *after* synthetic degradation (CLAHE+gamma+stretch on the degraded crop, n = 6 degradation types): PSNR 17.71–22.45 dB, SSIM 0.798–0.850, LPIPS 0.102–0.127, identity 0.902–0.941, YuNet score before→after within ±0.006 (e.g. motion blur 0.929→0.936 → +0.007, JPEG q25 0.943→0.938 → −0.005).

IED sweep (NIST IR 8485 axis; the face downscaled then nearest-upscaled ×3 before enhancement, n = 4 IED points):

| Target IED | crop-only YuNet | after CLAHE+gamma | identity similarity | tier-0 bounds |
|---|---|---|---|---|
| 60 px | 0.947 | 0.943 (−0.004) | 0.8953 | **FAIL** `identitySimilarity<0.90` |
| 40 px | 0.945 | 0.945 (±0.000) | 0.8791 | **FAIL** `identitySimilarity<0.90` |
| 24 px | 0.937 | 0.938 (+0.001) | 0.9237 | pass |
| 16 px | 0.936 | 0.935 (−0.001) | 0.9301 | pass |

Sample counts/denominators: 1 public-domain source image, 1 face, 6 op sets, 6 degradation contexts, 4 IED points, 3 determinism repeats. This is a **single-subject engineering measurement, not a population estimate**; no accuracy claim is made from it.

## Verdict

**adopt** — with a narrowed default op set.

1. **Default tier-0 op set = `gamma` only** (`Tier0Ops(gamma=1.2)`): PSNR 25.96 dB / SSIM 0.9766 / LPIPS 0.0101 / identity 0.9935 — the least-distortion op that still lifts an under-exposed crop. Contrast stretch measures even milder (PSNR 31.52 / identity 0.9972) but is a no-op on well-exposed frames, so it is opt-in, not default.
2. **CLAHE stays available and opt-in.** It is the only op that materially changes local contrast (LPIPS 0.120 vs 0.010), and its measured identity distortion sits close to the bound (0.913–0.916 on the native crop, 0.879–0.895 at 40–60 px IED where it *fails*). Silently defaulting CLAHE on would therefore publish near-bound derivatives.
3. **Denoise-lite must never be silently combined**: `CLAHE+gamma+denoise` measured **0.8960** identity similarity and is refused by the tier-0 bounds. Classical NLM denoise removes structure the face embedding uses; it stays off by default and the harness refuses it where it crosses the bound.
4. **Utility is honestly negative for detectability**: no op set produced a material YuNet gain (max +0.007 on a blurred crop, −0.005 on JPEG q25; ±0.004 across the IED sweep). Tier-0 enhancement is a *human review legibility* aid. Any UI/report wording that implies "enhancement improves detection" is unsupported by this measurement and is forbidden by the honesty doc.
5. Route to the product: derivative files carry the label in PNG metadata, the ledger record, and the UI contract fields; originals are untouched (verified in `backend/tests/test_enhance.py::test_service_publishes_a_labeled_derivative_and_records_its_hash`).
