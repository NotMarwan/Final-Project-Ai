---
authority: scoped
non_authoritative: true
---

# WT-23 — image enhancement: what it does, what it does NOT do, and how derivatives are labeled

Workstream WT-23 (image enhancement). Slices: F-52 (deterministic tier-0 + async
placement + GPU budget), F-53 (SC-8 derivative records + on-image/UI labeling),
F-54 (distortion/utility harness), F-55 (conditional learned tier-1
Real-ESRGAN behind the harness). Pinned baseline
`e86d34b5d16abcc133ad3470c8d135d00b2423d4` (`final-demo-transfer`).

Modules: `backend/enhance.py`, `backend/enhance_harness.py`, `backend/enhance_tier1.py`.
Tests: `backend/tests/test_enhance.py`, `backend/tests/test_enhance_tier1.py`.
Experiments: `docs/campaign/experiments/23-01…23-04`.
Research basis: `wt-08/docs/campaign/research/08-faces-tracking-imaging.md` §5 (enhancement), §8 (never-claim list).

## 1. What enhancement does

* **Tier 0 (default, shipped)**: deterministic pixel operations — crop, CLAHE
  (LAB-L), gamma (256-entry LUT), percentile contrast stretch, classical
  non-local-means denoise. No learned model. Same input + parameters ⇒
  byte-identical output (verified, 3 repeats). Measured on the public-domain
  fixture: distortion and utility in EXP-23-01. Default op set is `gamma 1.2`
  (PSNR 25.96 dB / SSIM 0.977 / LPIPS 0.0101 / identity similarity 0.9935).
* **Tier 1 (conditional, gated)**: Real-ESRGAN x4plus (RRDBNet, arXiv:2107.10833,
  weights BSD-3-Clause, SHA-256 `4fa0d389…82f1`) run post-alert, CPU or CUDA,
  **only** when the distortion harness accepts the output (EXP-23-04).
* **Both tiers** publish a *new* file; the original is never modified (asserted in
  tests). Every output is a labeled derivative with a chained SC-8 record.

## 2. What enhancement does NOT do (never-claim list)

Adapted from the WT-08 catalog §8 and binding for any UI copy, report text, or
demo narration that touches an enhanced image:

1. **We do not claim enhanced/super-resolved detail is what actually existed.**
   Synthesized texture is possible-but-unobserved. Wording: *"enhanced
   derivative — detail may be reconstructed"*. Never: "we recovered/restored the
   face", "we can now see what he looks like".
2. **We do not identify people.** No names, no identity match, no "recognized
   person". `backend/face_intel.py` (F-30, recognition engine) stays unwired.
3. **We do not label anyone a perpetrator, suspect, or participant** from
   proximity, co-occurrence, or being near a weapon/fight.
4. **We do not claim enhancement improves detection accuracy in general.** The
   measured tier-0 effect on YuNet detectability is within ±0.007 (noise-level);
   the only measured gain is SR on a deliberately low-resolution face
   (+0.0088, EXP-23-04, n = 1 subject). Never: "enhancement makes the detector
   more accurate".
5. **We do not present an enhanced crop as evidence-grade** without its
   transformation record and preserved original.
6. **We do not claim identity verification from the identity-similarity bound.**
   SFace cosine is a *distortion proxy* between one crop and its own derivative —
   never a match against a gallery, never stored, never compared across incidents.
7. **We do not claim completeness.** "No usable face/evidence frame found" is a
   true state and is reported as such; a refused enhancement is reported as
   refused, not as an absence of an alert.
8. **We do not make legal claims about admissibility.** We follow the documented
   practices (preservation + reproducible documentation); admissibility is for
   courts.
9. **We do not claim calibrated confidence** or use enhancement to justify any
   confidence/severity change.
10. **No cross-camera or longitudinal linking** of a person or face via
    derivatives.

## 3. Labeling contract (mandatory, three places)

| Place | Field | Value |
|---|---|---|
| Image metadata (inside the PNG) | `Label` / `Disclaimer` (tEXt/iTXt chunks) | `ENHANCED DERIVATIVE` · `ENHANCED DERIVATIVE — synthesized detail may be present; not an observation` (pure crop without pixel ops: `CROP DERIVATIVE` · `CROP DERIVATIVE — unmodified pixels from the original`) |
| Ledger record | `label`, `labelText`, `labelLocations`, `isEnhanced`, `tier`, `derivationBasis` | same wording; `labelLocations` always includes `image_metadata`, `ledger_record`, `ui_contract` |
| UI contract (WT-25) | `uiContract.originalFirst = true`, `originalRequired = true`, `badge`, `disclaimer` | original is shown first and is required; the derivative is visually distinct |

Copy rules for reports/UI: the badge `ENHANCED DERIVATIVE` must appear with the
disclaimer `enhanced derivative — detail may be reconstructed` next to any
derivative; the original must be reachable from the same view; a refused
enrichment is surfaced as *"enhancement refused by distortion bounds"* (with the
failing bound), never as a silent absence.

## 4. Derivative records (SC-8 extension)

Appended to the same `evidence_ledger.jsonl` hash chain as alert receipts, with
`recordType: "enhancement-derivative"`, `derivativeId` (monotone, unique),
`alertId`, parent identity (`parentKind`, `parentPath`, `parentSha256`,
`parentHashBasis`, `parentHashFormat`, SC-6 `parentCapturedAt` /
`parentSampleTimestamp`), `subjectRef` (crop id, track id, bbox + bbox space),
`derivativePath`/`derivativeSha256` (hash of the published file bytes), the
operation list with parameters, `model` (name/version/weights SHA-256/license —
all null for tier 0), `libraryVersions`, `operator`, and the `harness` block.

Integrity rules enforced in code:

* **No placeholder hashes.** A missing parent raises
  `DerivativeParentMissing`/`DerivativeParentUnhashed`; `"N/A"`, `null`, `""`,
  `"unknown"` and non-hex strings are refused. This closes runtime-map R-4 *for
  derivatives* (the alert-receipt path is WT-24/S-07's fix).
* **Append-only.** Records only append; nothing rewrites a line. A damaged chain
  blocks further appends (`EvidenceIntegrityError`) instead of extending a
  broken ledger.
* **Ordering guard.** A derivative may only be appended after the alert's
  receipt record exists, so receipt lookups can never be shadowed by a
  derivative (matches the S-07 `get()`/`append_entry` guard).
* **Idempotency.** Replay of the same `derivativeId` returns the existing record.
* **Single writer.** Derivative appends reuse the shared S-07 chain primitive
  (`EvidenceLedger.append_record`: per-path `RLock`, `prevHash`/`currentHash`
  chaining, `fsync`, rollback of a partial write on storage failure); the
  derivative-specific idempotency and receipt-ordering guards live in
  `DerivativeLedger.append_derivative`.
* **JSON safety.** All metric values are finite or `null`; identical pixels are
  recorded as `psnrDb: null` + `identicalPixels: true` + a note (the ledger
  serializes with `allow_nan=False`).
* **File layout.** `EVIDENCE_DIR/derivatives/{alert_id}.{subject}.{frame}.enhanced.png`
  (`subject` = `face{N}` / `person{track}` / `frame`, `frame` = media-clock ms,
  else frame sequence, else monotonic-ms tag).

## 5. Measurement harness

* `psnrDb` (full-scale 255), `ssim` (Gaussian 11×11, σ=1.5, per-channel mean,
  local implementation), `lpips` (LPIPS 0.1.4, official linear weights;
  **trunk provenance is recorded per measurement**), `identitySimilarity`
  (transient SFace cosine, discarded immediately), `utility`
  (YuNet detection score + inter-eye distance px before/after).
* **LPIPS provenance caveat (honest statement)**: `download.pytorch.org`
  answered HTTP 403 for both AlexNet checkpoint filenames from this host on
  2026-09-29, so the trunk is loaded from the *legacy-format* checkpoint already
  present in the local torch hub cache — `alexnet-owt-7be5be79.pth`,
  244 408 911 B, SHA-256
  `7be5be791159472b1fbf3c69796f7cb30dca7ad8466c2df70058c37116cdee02`
  (filename hash prefix matches the file digest; 16 tensors load with 0 missing /
  0 unexpected into `torchvision.alexnet`). The metric refuses to report a number
  unless a self-check passes (identical pair must measure `0.000000`), and every
  record stores the trunk file + hash used.
* Bounds: tier 0 `psnrDb>=14, ssim>=0.60, lpips<=0.55, identity>=0.90, face
  preserved`; tier 1 `psnrDb>=20, ssim>=0.70, lpips<=0.35, identity>=0.92, LPIPS
  must be measurable, face preserved`. Selection rule for the same-size
  reference: fewest failed bounds → lowest LPIPS → highest SSIM → declaration
  order (deterministic).
* **Calibration status: provisional.** Thresholds were set from the single
  public-domain fixture in EXP-23-01/02/04 (1 face). They must be re-calibrated
  on a wider licensed face set (WT-12's fixture library is the natural home)
  before any official presentation of face derivatives.

## 6. Placement and resource policy

* Enhancement runs strictly after alert dispatch/finalization; `enqueue` is
  lock-only (median 1.6 µs, p95 2.9 µs — EXP-23-03). The alert path contains
  zero enhancement work.
* Bounded queue with counted drop-oldest overflow; failures are counted, never
  raised into the alert path.
* Tier-1 yields while detection is active (CPU-only tier-0 remains available as
  the fallback); deferral exhaustion and a broken detection probe both drop/fail
  closed with an explicit counter and reason. Measured runs take the campaign
  `RESOURCE-LOCK`; a contended measurement is not reported as evidence.
* **Contended-run disclosure (2026-09-29)**: the WT-23 timing numbers in
  EXP-23-03 (enqueue latency, tier-0 op cost) and EXP-23-04 (CPU/CUDA inference)
  were taken while `RESOURCE-LOCK` ownership was ambiguous (a non-exclusive
  `mkdir -p` acquisition, later clobbered by WT-21's `owner.txt`), and they are
  therefore reported as **upper bounds** with the contention stated in the EXP
  cards. Metric values, determinism, gate verdicts, labeling and chain integrity
  are unaffected (deterministic computations on fixed inputs). A clean
  re-measurement is queued (WT-21 → WT-19 → WT-16 → WT-23) under the corrected
  atomic-`mkdir` protocol.

## 7. Asset provenance (untracked — never committed)

| Asset | Size | SHA-256 | License / provenance |
|---|---|---|---|
| `assets/face_detection_yunet_2023mar.onnx` | 232 589 B | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` | MIT (OpenCV Zoo model directory); copy of WT-08's verified download; used for utility + alignment |
| `assets/face_recognition_sface_2021dec.onnx` | 38 696 353 B | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` | MIT (OpenCV Zoo directory); `huggingface.co/opencv/face_recognition_sface`; transient identity bound only |
| `assets/RealESRGAN_x4plus.pth` | 67 040 989 B | `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1` | BSD-3-Clause (`assets/Real-ESRGAN-LICENSE.txt`, fetched from `xinntao/Real-ESRGAN`); tier-1 only |
| `assets/pylibs/lpips` (0.1.4) | 53 kB wheel + bundled linear weights | wheel `sha256` recorded by pip in the dist-info | BSD-2-Clause (`dist-info/LICENSE`, "Copyright (c) 2018, Richard Zhang …"); harness only |
| torchvision AlexNet trunk | 244 408 911 B | `7be5be79…ee02` | torchvision model zoo (BSD-3-Clause); already present in the local torch cache; see §5 |
| `assets/fixtures/face_pd_nasa.jpg` | 243 764 B | `6c7866ed5f9ef8777db5840055bfac34615a5449b89f0be788c955e29613ca0a` | **Public domain** — Wikimedia Commons `File:Neil Armstrong pose.jpg`, NASA photo ID S69-31741 |

None of these are committed; the modules degrade explicitly when an asset is
absent (metric reported as `unavailable` with a reason; tier-1 refuses to load).

## 8. Explicit absences / limitations

* No camera device exists in this environment: all measurements are file-media on
  a public-domain fixture, never live capture.
* Single-subject calibration (§5) and a single IED-region sweep.
* The identity bound uses a face-recognition *embedding model* (SFace) transiently;
  it is a distortion metric, not recognition — but any reviewer must know a
  recognition model is loaded during harness runs (never in the runtime path).
* Tier-1 is refused on already-legible crops in every reference framing
  (EXP-23-04) — on this evidence SR is an aid for low-resolution faces only.
* No UI wiring is included in this branch: `uiContract` fields are the contract
  for WT-25 (original-first ordering, badge, disclaimer), and the api.py
  integration hunk is listed for the integrator in the WT-23 handoff.
* Enhancement does not run for alerts that never finalize evidence (the trigger
  is evidence finalization), so no derivative exists for aborted alerts — an
  honest absence, not a silent failure.

## 9. Blueprint delta (for the orchestrator)

New IDs allocated from the workstream range (all `proposed` at baseline, now
`implemented` on `codex/sentinel-23-enhancement` unless noted):

| ID | Title | Status | Source refs |
|---|---|---|---|
| F-52 | Enhancement scheduler + GPU budget (post-alert, bounded, drop-oldest) | implemented | `backend/enhance.py` (`EnhancementScheduler`, `GpuBudget`, `EnhancementService`, `CropRef`, `default_tier0_ops`) |
| F-53 | SC-8 derivative records + labeling (PNG metadata + ledger + UI contract) | implemented | `backend/enhance.py` (`DerivativeLedger`, `build_derivative_record`, `write_derivative_png`, `ui_contract_fields`) |
| F-54 | Distortion/utility harness (PSNR/SSIM/LPIPS/identity/utility + bounds) | implemented | `backend/enhance_harness.py` |
| F-55 | Conditional tier-1 Real-ESRGAN behind the harness | implemented (gated; refused where bounds fail) | `backend/enhance_tier1.py` |

SC-8 is extended additively (`recordType: "enhancement-derivative"`, new record
shape, new `EVIDENCE_DIR/derivatives/` layout); SC-2 is untouched; SC-6 fields
are consumed verbatim (`captured_at` monotonic, `sample_timestamp` media clock);
SC-7 monotone IDs are used for `derivativeId`. Slices touched/adjacent: S-07
(evidence, WT-24 — the `get()`/receipt guard lands there), S-19/WT-25 (UI
contract for original-first derivative display), WT-12 (fixture library for
re-calibration), WT-26 (telemetry for refusal/drop counters).
