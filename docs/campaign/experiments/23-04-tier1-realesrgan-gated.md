---
authority: scoped
non_authoritative: true
---

# EXP-23-04 Tier-1 Real-ESRGAN x4 behind the harness: publish where it helps, refuse where it rewrites

Pre-registered before inspecting results. Workstream WT-23, slice F-55 (tier-1 learned enhancement).

- **Hypothesis**: a *conditional* learned tier can be shipped safely if (a) it is refused whenever the distortion harness fails, and (b) it is published only where it demonstrably helps — i.e. on genuinely low-resolution faces, not on already-legible crops where a GAN rewrites texture with no detection benefit.
- **Requirement link**: campaign brief step 3 ("Tier 1 (conditional): Real-ESRGAN (BSD-3) … only behind the distortion harness, only as clearly labeled derivatives, original-first UI ordering"); WT-08 catalog §5.1–5.3 (Real-ESRGAN BSD-3, hallucination risk HIGH) and §5.2 items 3–4 (perception–distortion tradeoff; PULSE).
- **Baseline**: three deterministic, non-generative x4 upscales of the original crop (nearest / cubic / Lanczos). Super-resolution changes resolution, so a same-size reference is required; the gate uses the reference **most favourable to the candidate** (deterministic selection rule: fewest failed bounds → lowest LPIPS → highest SSIM → declaration order) so a refusal cannot be an artifact of a poor comparator. Every reference's numbers are stored.
- **Candidate**: Real-ESRGAN x4plus (RRDBNet, 23 blocks, arXiv:2107.10833; weights `RealESRGAN_x4plus.pth`, 67 040 989 B, SHA-256 `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1`, BSD-3-Clause per the fetched LICENSE) run in-process via `backend/enhance_tier1.py`; loaded with `strict=True` (a mismatch between my RRDBNet implementation and the published weights is a hard error, not a warning).
- **Success criteria (defined BEFORE inspecting results)**: (1) strict load succeeds (architecture matches the published weights); (2) output is deterministic byte-for-byte over repeats; (3) tier-1 bounds (`psnrDb>=20`, `ssim>=0.70`, `lpips<=0.35`, `identitySimilarity>=0.92`, LPIPS measurable, face preserved) decide publish/refuse; (4) a refusal publishes **nothing** (no derivative file, no ledger record); (5) utility (YuNet detectability) is reported per case, including cases where it does not improve; (6) timings reported per device, separated from the alert path.
- **Failure criteria / rollback**: strict-load failure ⇒ tier-1 abandoned; non-deterministic output ⇒ tier-1 abandoned; a candidate that passes the harness but is published without labels/record ⇒ reject; any tier-1 artifact published while detection was active ⇒ reject the budget policy.
- **Environment**: Windows 11 x64, RTX 3060 12 GB (torch 2.3.0+cu118, cuDNN default benchmark off), 16 GB RAM, Python 3.12.5. Source mode: file-media (public-domain fixture, no camera). `RESOURCE-LOCK` held for the whole sweep; no other workload on the GPU/CPU. FP32 (no fp16/AMP) — deliberately, for reproducibility.

## Result (raw artifact `assets/measurements-wt23-tier1.json`)

> **CONTENDED-RUN DISCLOSURE (2026-09-29).** The `Inference`/`wall` columns below
> were taken in the 01:38–02:2x window under ambiguous `RESOURCE-LOCK` ownership
> (non-exclusive `mkdir -p` acquisition, later `owner.txt` clobbered by WT-21).
> They are therefore **upper bounds**; a clean re-measurement is queued behind
> WT-21 → WT-19 → WT-16. All distortion/identity/utility numbers, the
> strict-load result, the byte-identical determinism check and the gate verdicts
> are computed from fixed tensors/pixels and are unaffected by contention. The
> device *ratio* (GPU ≈ 12–19× faster) is robust because both arms ran in the
> same sweep.

Real-ESRGAN x4 on the native crop (479×305, face IED 74.25 px, crop detection score 0.94412):

| Device | Inference | PSNR dB | SSIM | LPIPS | identity sim. | YuNet before→after | Gate |
|---|---|---|---|---|---|---|---|
| CPU | 26 553.7 ms | 29.91 | 0.8701 | 0.4982 (ref cubic) | 0.9617 | 0.94412→0.94615 (+0.00203) | **REFUSED** `lpips>0.35` |
| CUDA | 1 378.8 ms | 29.91 | 0.8701 | 0.4982 | 0.9620 | 0.94412→0.94616 (+0.00204) | **REFUSED** `lpips>0.35` |

Per-reference numbers for the same output (CPU/GPU identical to 3 decimals): nearest LPIPS 0.5913 / SSIM 0.804; cubic 0.4982 / 0.8701; Lanczos 0.5107 / 0.8601. **Every deterministic framing fails the LPIPS bound** — the refusal is not a comparator artifact.

Real-ESRGAN x4 on a genuinely low-resolution face (288×240 crop upscaled from IED ≈ 20 px, detection score 0.90202):

| Device | Inference | PSNR dB | SSIM | LPIPS | identity sim. | YuNet before→after | Gate |
|---|---|---|---|---|---|---|---|
| CPU | 11 396.7 ms | 32.52 | 0.9272 | 0.3030 (ref Lanczos) | 0.9759 | 0.90202→0.91084 (**+0.00882**) | **PASS** |
| CUDA | 894.4 ms | 32.52 | 0.9271 | 0.3030 | 0.9752 | 0.90202→0.91070 (+0.00868) | **PASS** |

Determinism: repeated inference on the same crop is byte-identical (verified for the real model and asserted in `backend/tests/test_enhance_tier1.py::test_realesrgan_output_is_scaled_uint8_and_deterministic`). Device speed ratio ≈ 12–19× (CUDA vs CPU: 1378.8 ms vs 26 553.7 ms on 479×305; 894.4 ms vs 11 396.7 ms on 288×240).

Sample counts/denominators: 1 public-domain source image, 1 face, 2 crop regimes (native 479×305; low-resolution 288×240), 2 devices, 3 deterministic references per case, 1 repeat for determinism (byte-identical output is a stronger statement than a variance estimate here). This is a single-subject engineering measurement — **not** an accuracy/precision claim about the model, and not evidence about other faces.

## Verdict

**adapt (conditional adoption, narrowed):**

1. **Tier 1 is shippable only in the low-resolution regime** on this evidence: it passes the harness there (LPIPS 0.303 ≤ 0.35, identity 0.976, PSNR 32.5) and measurably improves face detectability by **+0.87 points** (0.9021→0.9108). On an already-legible crop it is **refused** in every reference framing (LPIPS 0.498–0.591 ≫ 0.35, detection gain +0.17 points ≈ noise). Publishing that would mean presenting rewritten texture as if it were camera detail — the exact failure mode the WT-08 catalog's SWGIT/PULSE/perception–distortion citations warn about.
2. **Never inline**: even on CUDA the honest cost is ~0.9–1.4 s per crop (11–27 s on CPU). Tier 1 therefore stays strictly post-alert/on-demand behind the bounded queue of EXP-23-03, never on the alert path, and never in the live loop.
3. **Refusal is a first-class outcome**: refused candidates publish no file and no ledger record, and are counted (`tier1_refused_by_harness`) — the UI/telemetry story is "enrichment refused by distortion bounds", not a silent absence.
4. **Labeling is not optional**: every published tier-1 artifact carries `derivationBasis: "learned"`, the model name/version/weights SHA-256/license, an `ENHANCED DERIVATIVE` badge in PNG metadata, the ledger record and the UI contract, plus `originalFirst: true`.
5. **Open item (not a claim)**: the identity bound (SFace cosine) is a *distortion proxy*, not an identity verification, and the calibration here rests on one face. It is measured and bounded, but its thresholds (0.92 tier-1 / 0.90 tier-0) should be re-calibrated on a wider licensed face set before any official presentation of face derivatives (WT-12 fixture library is the natural place).
