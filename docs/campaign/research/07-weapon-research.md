---
authority: scoped
non_authoritative: true
---

# 07 — Weapon detection research (WT-07)

Scoped research catalog for the weapon detection path of AI Sentinel. This document is
**research input for WT-18 (improvement engineering) and WT-12 (integration)**; it is not a
status or design authority. Web sources were fetched 2026-09-29; every claim is either
(a) measured in this worktree, (b) quoted from a fetched primary source with its date, or
(c) explicitly labelled `[INFERENCE]`/`unverified`.

## 0. Contract anchors (what the recommendations must respect)

From the wt-01 blueprint seed (`docs/blueprint/runtime-map.md`, `ownership-map.md`, read
2026-09-29):

- **Weapon path (runtime-map F-09)**: `backend/weapon.py` (`WeaponSignalEngine`, internal
  weapon-inference thread) with the ONNX backend in `backend/yolo_onnx.py`; output contract
  `score`, `labels`, `bbox`, `observation_id`, `observation_age_ms`, `isRealtime`.
- **NMS/letterbox contract** (runtime-map model-registry section, adjacent to F-09; note the
  assignment cites "F-10/F-11" but in the seed **F-10 = person detection overlay, F-11 =
  motion score** — the letterbox/NMS contract text lives in the registry section, not in those
  rows; flagged as a numbering discrepancy): letterbox to model input size with pad 114,
  BGR→RGB, /255, NCHW fp32; decode modes `"raw"` (this model: `end2end=false`,
  `args={'nms': False, …}`) or explicit `[N,6]`; class-aware greedy NMS `iou_threshold=0.5`,
  `max_detections=300`, NMS applied in model space; config `weapon.labels` substring filter.
- **Model registry facts** (runtime-map, verified by wt-01 `runtime-map-verification.md`):
  `backend/models/weapon_yolo.onnx`, 103,636,665 bytes, sha256 `96991cd5…5875aef`,
  untracked; `images [1,3,640,640]` fp32 → `output0 [1,10,8400]`; names
  `0 pistol, 1 rifle, 2 shotgun, 3 knife, 4 sword, 5 revolver`; registered run placed both
  ONNX sessions on `CPUExecutionProvider` while violence ran on `cuda:0`.
- **Registered latency evidence**: weapon inference on CPU EP ≈ 700 ms in the baseline
  registered report; a GPU path ≈ 43 ms is claimed but uncommitted/unregistered (per campaign
  seed). Both are treated here as *given baseline numbers*, not re-measured.
- **Gates**: G-02 = 0 confirmed alerts on a negatives suite (≥20 benign clips: hugging,
  handshakes, waving, walking, phone use); G-03 = ≥90% detected on the positives suite
  (staged violence + visible weapon, close-range, webcam) (`docs/PLAN.md`, wt-01/wt-02).
- **Threshold surfaces today** (`backend/weapon.py` config read 2026-09-29):
  `WEAPON_MIN_CONFIDENCE` default 0.20, `WEAPON_INDEPENDENT_ALERT_THRESHOLD` default 0.65,
  `WEAPON_SCORE_EMA_ALPHA` 0.45, `WEAPON_INPUT_SIZE` default 640, `WEAPON_INFER_INTERVAL`
  default 8, score-decay half-life 5000 ms, signal TTL 10000 ms. Decision-side authority is
  SC-5 (`config/thresholds.toml`, `backend/decision_config.py`); calibration artifact is
  absent (F-40, S-05).
- **Relevant slices/F-IDs for effort estimates**: F-09 (weapon engine), F-10 (person overlay,
  for person–weapon co-occurrence gating), F-15 (fusion/severity), F-29 (category capability
  API), F-40 (calibration artifact absence), S-05 (decision/calibration, owns
  `bench/calibrate.py`), S-20 (bench/measurement harness), S-21 (training/dataset tooling,
  provenance of shipped weights is UNKNOWN per F-48).

## 1. What the shipped weapon detector actually is (local evidence, 2026-09-29)

Direct inspection of `backend/models/weapon_yolo.onnx` (read-only from the primary checkout;
weights are untracked and were **not** copied) with the shared venv's onnxruntime 1.18.0:

```
providers: ['CPUExecutionProvider']
inputs:  [('images', [1, 3, 640, 640])]      # STATIC shape — no dynamic axes
outputs: [('output0', [1, 10, 8400])]        # 4 box + 6 class channels (v8-style, no objectness)
producer: pytorch                            # default exporter metadata, no training args
CPU EP ms per run (5 runs, 2 warmups, random 640² input):
  299.2, 288.7, 299.2, 309.0, 306.8
```

Findings that constrain every recommendation below:

1. **[MEASURED] Input size is frozen at 640×640.** `backend/yolo_onnx.py:model_input_size()`
   derives the letterbox target from the model's static shape, so `WEAPON_INPUT_SIZE` cannot
   change resolution at runtime; any multi-scale/tiled scheme needs a **re-export with dynamic
   axes** (or multiple exported graphs) before code changes matter.
2. **[MEASURED] ~290–310 ms CPU EP per forward** on this workstation (random input, forward
   only — excludes letterbox, decode, NMS, IPC). The registered ~700 ms baseline presumably
   includes those stages plus contention; the two numbers are **not** comparable as-is but
   bracket the forward-pass share of CPU latency. No GPU re-measurement was run here (16 GB
   RAM machine, shared venv read-only, research-only scope).
3. **[INFERENCE] The graph is YOLOv8m-scale.** File size 103,636,665 B ≈ 25.9 M fp32
   parameters; Ultralytics' model table lists YOLOv8m at 25.9 M params (docs page fetched
   2026-09-29). A 103 MB fp32 export with `output [1,10,8400]` at 640 is consistent with a
   YOLOv8m-sized anchor-free split-head model fine-tuned to 6 classes. Weight provenance is
   unknown (F-48), so architecture identity remains unconfirmed.

## 2. Detector landscape

### 2.1 YOLO-family fine-tunes (v5 / v8 / v11 / v12)

| Family | Primary source | License (fetched LICENSE file) | Relevance to our path |
|---|---|---|---|
| YOLOv8 (Ultralytics, released 2023-01-10) | `github.com/ultralytics/ultralytics`, docs/en/models/yolov8.md | **AGPL-3.0** (LICENSE file read) | Current export format matches v8 head (`[1,4+C,8400]`, no objectness). AGPL is the reference implementation for retraining/export. |
| YOLO11 (Ultralytics, v11.0.0, 2024) | docs/en/models/yolo11.md (fetched) | **AGPL-3.0 + paid Enterprise** (stated in the doc: "YOLO11 models are provided under AGPL-3.0 and Enterprise licenses") | Drop-in accuracy/speed improvements over v8 at same input; same export contract. |
| YOLOv12 (attention-centric, arXiv 2502.12524, 2025-02-18) | `github.com/sunsmarterjie/yolov12` | **AGPL-3.0** (LICENSE file read) | Attention sink backbone; published for real-time; same caveat: license + weight provenance. |
| YOLOv5 (legacy) | ultralytics/yolov5 | AGPL-3.0 (`[unverified]` — LICENSE not fetched in this pass) | Only relevant as the format of `backend/weapon_hadi_yolo.pt`-era tooling. |

**License rule for WT-18**: any *deployment* of a model trained/exported with Ultralytics code
in a distributed product is AGPL-contagious unless an Enterprise license is bought. This
applies to retraining our own detector with `ultralytics` pip package too. If the product
license cannot accept AGPL, the compliant routes are (a) train with an Apache-2.0 stack
(RT-DETR / D-FINE / YOLOX), or (b) use Ultralytics only internally (AGPL allows internal use)
and export ONNX, with legal review of whether the ONNX artifact is a derivative. **This is a
decision WT-18 must not make silently.**

### 2.2 Open weapon-specific weights (HF / Roboflow / Ultralytics hub)

HuggingFace model search (`huggingface.co/api/models?search=…`, fetched 2026-09-29) — none of
these have any published per-class metrics on camera/CCTV domains; treat as candidate
*initializations*, never as evidence:

| Model | Base | License tag | Notes |
|---|---|---|---|
| `keremberke/yolov8m-weapon-detection` | YOLOv8 | **card unreachable** — HF returns HTTP 401 for the repo on 2026-09-29 (deleted/gated/private) | The best-known public "weapon" YOLO card; cannot be verified now → do not build on it without re-checking. |
| `KIRANKALLA/WeaponDetection` | Conditional DETR (transformers) | none declared | TensorBoard logs present; no eval card. |
| `NabilaLM/detr-weapons-detection`, `…_30ep` | DETR (arXiv 1910.09700) | none declared | 2024-07 training runs; no metrics card. |
| `Dricz/gun-obj-detection-1…6` | DETR-style + `best.pt` | **inconsistent across the series: apache-2.0, openrail** | Series of student training runs (2024-03). openrail is use-restricted (not OSI); mixing licenses in one series is a provenance red flag. |
| `obelus0/gun-detection-model-{real,synth-small,synth-big}` | DINO checkpoints | none declared | 2025-04; real-vs-synthetic training comparison — useful prior for §3.7. |
| `fetiska/cold_weapon` | ONNX/PT zoo ("SnowballTarget…") | none declared | Naming/provenance opaque; weights without license = all rights reserved by default. |
| `crangana/xray-weapon-detector` | YOLOv8 training runs | none | X-ray baggage domain — wrong domain, listed to avoid confusion. |

Roboflow Universe "Weapondetect" workspace (`weapon-detection`, `Weapon_Detection` datasets)
and `platform.ultralytics.com/…/weapon-detection` (Matvey Belov) and "Weapondetect Model by
Starling 3" surfaced in web search on 2026-09-29, but **universe.roboflow.com returned HTTP 403
to fetches**, so their licenses/counts are unverified here. Roboflow project licenses vary per
project (CC BY 4.0 / CC BY-NC / custom); each must be checked at download time.

### 2.3 Small-object-focused detectors

A held weapon at CCTV distance is a *small object* (tens of pixels). Routes, ranked by
engineering fit:

1. **Tiled inference (SAHI)** — Akyon et al., *Slicing Aided Hyper Inference and
   Fine-tuning for Small Object Detection*, arXiv 2202.06934 (2022-02-14, ICIP 2022);
   library `github.com/obss/sahi`, **MIT** (LICENSE read). Slices the frame, runs the
   detector per tile, merges boxes. Cost is multiplicative in tile count (N tiles ≈ N
   forwards) — on our CPU EP at ~300 ms/640² forward, full-frame tiling is infeasible
   in real time; **tile only person-crop regions** (F-10 person tracks) to keep ≤1–2
   extra forwards per interval.
2. **P2 (stride-4) detection head** — adds a high-resolution pyramid level for tiny objects;
   increases FLOPs substantially at 640+; requires retraining, so it is tied to the
   dataset decision in §5.
3. **Higher-resolution inputs (960/1280)** — the simplest lever, but blocked today by the
   static 640 graph (§1.1) and by the CPU/GPU cost quadratically scaling (~2.25× at 960).
   YOLO-family accuracy on small objects improves with input size; we cannot cite
   cross-dataset numbers here (metrics are not comparable across datasets/hardware — see
   Validation rule).

### 2.4 Transformer detectors

| Model | Source & date | License | Fit |
|---|---|---|---|
| DETR | arXiv 2005.12872 (2020-05-26) | — (code: Apache-2.0 in `facebookresearch/detr`, `[unverified in this pass]`) | Slow convergence; not a deployment candidate. |
| RT-DETR ("DETRs Beat YOLOs on Real-time Object Detection") | arXiv 2304.08069 (2023-04-17); PyTorch port `lyuwenyu/RT-DETR` | **Apache-2.0** (LICENSE read) | Real-time, NMS-free (end-to-end), strong small/medium objects; the cleanest license story for a weights swap. |
| D-FINE | arXiv 2410.13842 (2024-10-17); `Peterande/D-FINE` | **Apache-2.0** (README badge; LICENSE file at `main` is 404, exists on `master` branch layout) | Fine-grained distribution refinement for box regression; README claims better localization of small/blurred objects than YOLO11 (author claim, own demo video — not cross-comparable). |

Ensemble note: *Confidence Aware SSD Ensemble with Weighted Boxes Fusion for Weapon
Detection* (arXiv 2509.23697, 2025-09-28) reports improved robustness under partial
occlusion/varying light via WBF ensembles. WBF replaces greedy NMS and conflicts with the
current `yolo_onnx.py` NMS contract (class-aware greedy, IoU 0.5) — an ensemble is an
SC-2/contract change, not a config tweak.

### 2.5 Occlusion / low-light robustness

- The weapon FP literature names the same failure drivers we must design for: **partial
  occlusion, varying lighting, cluttered backgrounds** (abstract of 2509.23697, quoted above);
  concealed/hidden weapons need thermal or mmWave modalities (DEF-YOLO, arXiv 2510.13326,
  2025-10-15) — out of scope for a webcam/RGB path, listed to bound expectations: **RGB
  cannot see occluded weapons; the goal is visible-weapon recall** (G-03 says "visible weapon").
- Practical RGB mitigations to test, in order of cost: (a) person-crop re-inference at high
  resolution (§2.3.1), (b) low-light augmentation during fine-tune (gamma/CLAHE-style
  augmentation), (c) score aggregation across frames (already present: EMA α=0.45, decay
  half-life 5 s) — the temporal path is our cheap "occlusion tolerance" and should be
  calibrated rather than re-architected.

### 2.6 Few-shot / domain adaptation for camera-domain shift

Domain-adaptive detection is a mature literature (e.g. *A Robust Learning Approach to Domain
Adaptive Object Detection*, arXiv 1904.02361 (2019-04-04); *Weakly Supervised Test-Time Domain
Adaptation for Object Detection*, arXiv 2407.05607 (2024-07-08); synthetic-to-thermal
adaptation arXiv 2002.06770 (2020-02-17)). For our scale the pragmatic recipe is:

1. **Fine-tune, don't adapt-from-scratch**: start from a weapon fine-tune (§2.2) or COCO
   weights, fine-tune on a small camera-domain set (tens–hundreds of labelled frames).
2. **Capture-first protocol**: because no camera device exists in this environment,
   camera-domain data must come from file/synthetic fixtures plus staged webcam recordings
   made by operators (G-03's positives suite is exactly that: staged, close-range, webcam).
3. Keep adaptation **inside S-21 tooling** (`backend/train_finetune.py`, `backend/training/`)
   so provenance lands in the manifest (F-48 requires weight provenance to stop being
   UNKNOWN).

### 2.7 Synthetic data & pseudo-labels — governing rule

**RULE (binding for WT-18/WT-12): synthetic images and pseudo-labels may only enter
*training*. They MUST NEVER serve as test truth.** Any reported accuracy must come from a
human-annotated, real-image evaluation split; synthetic/pseudo-labeled frames in a test set
make G-02/G-03 numbers meaningless. Corollaries:

- If a model is trained with synthetic/prefix data, the eval suite must record the split's
  provenance per clip (the bench clip schema already carries `label`/`label_source`/
  `split` fields — `bench/calibrate.py` enforces `split ∈ {calibration, test}`).
- Pseudo-labels (self-labeling on target footage) are treated as *noisy training labels*;
  hard-negative mining (§4.3) must curate them by hand before they influence thresholds.
- Precedent: `obelus0/gun-detection-model-synth-*` (HF, 2025-04) shows synthetic-trained
  gun detectors exist in the wild; their cards publish no held-out real-world metrics, which
  is precisely the failure mode this rule prevents.

## 3. Class taxonomy mapping

Our taxonomy (ONNX `names`): `pistol, rifle, shotgun, knife, sword, revolver`.

### 3.1 Mapping problems (the classic ones)

| Source taxonomy | Typical classes | Mapping to ours | Failure mode |
|---|---|---|---|
| COCO-style "weapon"/"handgun" single class | `gun`, `weapon` | collapse all 6 → `weapon` | loses subtype; a `pistol` and a `knife` alert have different severities downstream (F-15 fusion) |
| "gun vs knife" binary (Kaggle `guns-knives…`) | `gun`, `knife` | gun → pistol/rifle/shotgun/revolver (subtype unidentifiable) | over-specific labels on gun-class detections must be **flattened at the mapping layer**, not guessed |
| `handgun` / `pistol` / `revolver` overlap | varies | handgun ≈ pistol; revolver is a handgun subtype | **pistol vs revolver is often unresolvable at CCTV resolution** — recommend a mapping layer that accepts `pistol∨revolver` detections into either alert label |
| `rifle` vs `shotgun` vs `assault rifle` | varies | rifle ← assault-rifle/SMG; shotgun separate | long-gun subtypes degrade quickly with blur/occlusion; alert-level distinction is low value |
| `knife` vs `sword` vs `blade`/`edged` | varies | knife ∪ sword → edged weapon | sword is a rare class in public datasets (mostly cosplay/WSHO-style sets) — expect poor per-class AP until camera-domain data exists |
| WSHO ("Weapons and similar handled objects", ari-dasci) | handled objects incl. tools/umbrella-like negatives | negatives only | valuable as **hard-negative source**, not as positive taxonomy |

**Recommendation**: keep the 6-class head but add a **taxonomy mapping layer** (F-09 output →
alert labels) with explicit rules: `revolver→pistol∨revolver`, `sword→knife∨sword`,
plus a `weapon` fallback for any foreign class. Alert-level severity should key off
coarse groups (firearm vs edged) so subtype errors cannot suppress alerts.

### 3.2 False-positive hard negatives

The G-02 negatives suite (hugging, handshakes, waving, walking, phone use) needs per-object
hard negatives too. Known visual confusers for weapon detectors (from WSHO's "similar handled
objects" framing and general detector FP behavior `[latter is engineering consensus, not a
fetched metric]`): **umbrellas, walking sticks, tools (hammers, drills), power strips/cables,
smartphones and tablets (dark rectangles), camera tripods and monopods, chair/table legs,
hands/fists at low resolution, dark elongated blobs (belts, bags), musical instruments**.
Protocol: run the candidate models on the negatives suite *before* any fine-tune, log every
FP box with class + crop, and build the fine-tune's negative set from those crops (hard-negative
mining). This is the cheapest G-02 protection available.

### 3.3 Per-class and subset metrics required

Report **per-class AP (AP50 and AP50-95), per-class recall at the alert threshold**, plus
subsets: *small* (box area < 32² px in source resolution), *occluded* (≥30% hidden,
human-judged flag), *low-light*. Aggregate mAP alone is disqualifying for a weapon product:
a model can be excellent on `pistol` and useless on `knife`/`sword` (rare classes). Never
compare these numbers across different datasets/hardware (Validation rule).

## 4. Datasets & rights (acquisition routes — rights-checked 2026-09-29)

### 4.1 Name resolution for the assignment's listed sets

The names **GDW, GWD, WeaponDetect, Weapon-NDS, COCONTS** were searched (DuckDuckGo/Bing,
2026-09-29). Findings, honestly reported:

- **GDW / GWD**: no public weapon dataset resolves under these acronyms. "GDW" resolves to
  the *Global Dam Watch* dam database (wrong domain). Plausible intended referents: the
  UGR/DASCI "weapon detection open data" sets (below), or internal shorthand. **Not
  identifiable as public weapon datasets — do not cite as such.**
- **WeaponDetect**: resolves to the **Roboflow Universe "Weapondetect" workspace**
  (`weapon-detection`, `Weapon_Detection` datasets) and a "Weapondetect Model by Starling 3"
  on the Ultralytics hub (search hits 2026-09-29; Roboflow pages 403 to fetch → license and
  counts **unverified**). Also a GitHub "Weapon-Detection-YOLOv8n"
  (`sagar-goyal162005/Weapon-Detection-YOLOv8n`, search hit; repo not fetched).
- **Weapon-NDS / COCONTS**: **zero search results** in 2026-09-29 searches. Treat as
  unidentifiable; ask the requester for the source of these names before using them in any
  procurement or citation.

### 4.2 Verified dataset catalog

| Dataset | Source / date | Task & size | Domain | License / rights | Verdict |
|---|---|---|---|---|---|
| UGR/DASCI **OD-WeaponDetection** ("weapon detection open data": pistol classification/detection, knife classification/detection, WSHO) | `github.com/ari-dasci/OD-WeaponDetection` (README fetched 2026-09-29); related: *Orientation aware weapons detection in visual data: a benchmark dataset*, Computing (2022), doi 10.1007/s00607-022-01095-0 | detection + classification sets, Google-Drive hosted | web/staged imagery | **CC BY-SA 4.0** (stated in README) | Best-documented public option; **ShareAlike is viral for redistributed datasets** — fine for internal training, redistribution of the dataset must stay BY-SA. WSHO doubles as hard-negative material. |
| Kaggle `issaisasank/guns-object-detection` | Kaggle API 2026-09-29 | 5 MB | web | **GPL-2** (as listed) | Odd license for image data (GPL is a software license); use only after reading the dataset card. |
| Kaggle `trainingdatapro/people-with-guns-segmentation-and-detection` | Kaggle API | 70 MB | staged/web | **CC BY-NC-ND 4.0** | **INCOMPATIBLE for model training in a commercial product** (NC restricts use; ND arguably forbids derivative datasets/models — needs legal call). Also mirrored on HF as `UniqueData/people-with-guns-segmentation-and-detection` (same NC-ND). |
| Kaggle `iqmansingh/guns-knives-object-detection` | Kaggle API | 142 MB | web | **CC0** | Usable; annotation quality unknown. |
| Kaggle `ugorjiir/gun-detection` | Kaggle API | 278 MB | web | **ODbL** (share-alike database license) | Usable internally; ODbL obligations attach to redistributed DB — keep it out of shipped artifacts. |
| Kaggle `atulyakumar98/gundetection` (YOLO v2/v3 labels) | Kaggle API | 262 MB | web | **CC0** | Usable; old label formats need conversion checks. |
| Kaggle `snehilsanyal/weapon-detection-test` | Kaggle API | 204 MB | web | **CC0** | Usable as held-out material, but verify it wasn't scraped from the same pools as the train sets (leakage risk). |
| Kaggle `ankan1998/weapon-detection-dataset` | Kaggle API | 511 MB | web | **Unknown** | **Do not use** without provenance investigation (scraped-video risk). |
| Kaggle `kruthisb999/guns-and-knifes-detection-in-cctv-videos` | Kaggle API (updated 2024-12-18) | 1.0 GB video | **CCTV** | **Unknown** | The only CCTV-domain hit; license unknown + scraped-video provenance risk → **blocked for use** until rights are established. Its *existence* is still useful: CCTV-domain weapon data is scarce and usually unlicensed. |
| Kaggle `mohamedgobara/26-class-object-detection-dataset` | Kaggle API | 1.1 GB | mixed | Apache-2.0 | Multi-class; weapon classes need checking before use. |
| HF `Besedo/artificial_weapon` | HF API | 1–10K images | synthetic ("machine-generated" annotations) | **no license declared** | Synthetic source; per §2.7 rule it can only feed training, and no-license = all rights reserved → skip. |
| HF `fcakyon/gun-object-detection`, `JoseArmando07/gun-dataset` | HF API | — | — | none declared | Same skip rule. |
| Kaggle `orvile/x-ray-baggage-anomaly-detection` | Kaggle API | 139 MB | X-ray | CC BY 4.0 | Wrong modality; listed only to exclude. |

### 4.3 CCTV / camera-domain reality check

Public CCTV-domain weapon data with clear rights is effectively **absent** from the catalog
above (the single CCTV hit is license-unknown). Consequences for WT-18:

- The evaluation truth for camera-domain behavior will come from **our own staged clips**
  (G-03 positives suite: staged violence + visible weapon, close-range, webcam) and the
  negatives suite (G-02). These are operator-recorded → clear rights, correct domain.
- Public web imagery is fine for pretraining/initialization but **cannot** establish
  camera-domain accuracy. Every claim in WT-18 must say which split it came from.
- Provenance risk is real: Kaggle/HF gun datasets are frequently bulk-downloaded web images
  (HF `Kaludi/data-csgo-weapon-classification` card even states it was "collected with the
  help of a bulk google image downloader" — game screenshots, wrong domain anyway). Scraped
  video datasets can carry third-party rights problems and subject-privacy problems; the
  campaign's no-upload/no-footage-sharing rules make such sets a poor fit for anything that
  leaves the machine.

## 5. Calibration & operating points

1. **Score calibration.** `bench/calibrate.py` (S-05) already implements binary
   temperature-scaling over clip-level scores: logit temperature search on a `calibration`
   split, NLL objective, ECE-style bin metrics, and `held_out_before/after` on a `test`
   split; its own disclaimer says clip-level calibration does not establish window-level
   calibration or camera-domain accuracy. **Weapon scores are the natural second consumer**
   of this script (it currently serves violence-class scores). Link: model_sha256 is carried
   into the artifact, matching F-40's requirement that a calibration artifact bind to the
   weight hash (`96991cd5…5875aef` for the current ONNX).
2. **Per-class thresholds.** Today there is one global `WEAPON_MIN_CONFIDENCE` (0.20) and one
   alert threshold (0.65). Per-class operating points are justified because class priors and
   FP costs differ wildly (`pistol` common + high FP rate on dark rectangles vs `sword`
   rare). But per-class thresholds must live in the **single threshold authority** (G-05,
   SC-5: `config/thresholds.toml`) — no inline literals in `weapon.py`.
3. **False alerts per camera-hour.** Report operating points as *confirmed alerts per
   camera-hour at recall R* on the negatives suite (e.g. "0 alerts / 20 clip-hours at
   recall ≥0.9" — G-02 is literally the 0-alert point). This is the framing that maps to
   operator cost; per-clip FPR alone hides temporal clustering (a 10 s FP burst triggers
   several confirmations unless the confirm window/dedup absorbs it — that interaction is
   F-15/decision-layer behavior, measured end-to-end).
4. **NMS/ensemble tradeoffs.** Current contract: class-aware greedy NMS IoU 0.5, max 300.
   Options: (a) class-agnostic NMS for pistol/revolver duplicates (helps when the head
   double-fires subtypes on the same object), (b) WBF ensembles (§2.4) — better occlusion
   robustness, but contract + cost change, (c) lowering IoU to ~0.45–0.55 sweep on the eval
   split. All three are measurable without retraining via the bench harness (S-20).
5. **Multi-scale inference cost (RTX 3060 context).** The graph is static 640. At fp32 the
   103 MB model ≈ 25.9 M params [INFERENCE] is a *medium* model: on RTX 3060-class GPUs the
   committed GPU path number (~43 ms, uncommitted claim) is consistent with fp32 640
   inference + preprocessing; TensorRT/fp16 export would typically cut this further
   `[unverified — no GPU measurement run in this research pass]`. Cost projections for
   WT-18 experiments (label these as *estimates to be measured*, not results):
   960 input ≈ 2.25× forward cost; tiled 2×2 on a person-crop ≈ 4× crop-forward cost;
   both exceed the ~500 ms `WEAPON_REALTIME_THRESHOLD_MS` on CPU EP and are only plausible
   on the GPU path at reduced interval (F-09 `WEAPON_INFER_INTERVAL`, default 8 frames).

## 6. Deployment evidence & real-time constraints

- **Latency budget**: G-04 (glass-to-alert p95 ≤ 2000 ms) leaves little room for a 300–700 ms
  weapon forward on CPU; the GPU path (~43 ms claimed) is what makes G-01 (≥30 fps) and G-04
  co-exist with weapon detection active. WT-18 should treat "weapon on CPU EP" as a degraded
  mode with a raised interval and an explicit health state (SC-10-style honesty), not as the
  operating point to tune accuracy against.
- **Input size vs accuracy vs cost**: because the export is static, every input-size
  experiment requires a re-export (dynamic axes) first. Recommended experiment ladder:
  640 (baseline) → 960 (small-object recall) → 640 + person-crop tiling (targeted small
  object). Measure per-class recall on the small subset at each rung.
- **Evidence quality (max-side 640 IPC vs 960 evidence ring)**: detection runs on the
  downscaled/letterboxed view while evidence clips can retain higher resolution. Boxes are
  produced in model space and mapped back; small-object boxes mapped from a 640 view have
  quantization error in the 960 evidence frame. For WT-12: keep detection coordinates in
  **source pixels** (the `tracks` field already carries source-pixel xyxy per SC-2) and never
  upscale boxes into evidence as if they were precise; crop evidence with a padding margin
  (e.g. 10–15% of box size) so the operator sees context. The evidence ring's higher
  resolution does **not** improve detection; it only improves human review — worth stating in
  UI copy (U-slice territory) to avoid "zoom to enhance" expectations.

## 7. Recommendation table for WT-18 (ranked)

Evidence levels: **A** = measured in this repo/worktree; **B** = primary external source
(fetched, dated); **C** = `[INFERENCE]`/engineering prior, needs the listed experiment.

| # | Improvement | Evidence level | Dataset/protocol context | Expected benefit (G-02/G-03) | Effort (F-IDs / slices) | Runtime cost | Verification experiment |
|---|---|---|---|---|---|---|---|
| 1 | **Hard-negative mining + negatives-suite FP log** | A (FP risk is structural: single 0.20 conf floor), C for effect size | G-02 negatives suite (≥20 benign clips) + FP crops; WSHO (CC BY-SA 4.0) as extra negatives | **G-02: primary lever** to reach 0 confirmed alerts; G-03 neutral | F-09 (labels filter), S-21 (dataset tooling), S-20 (logging) | none at runtime | Run current model on negatives suite, log FP crops; fine-tune with/without mined negatives; compare confirmed-alert count (target 0) and recall on positives suite |
| 2 | **Threshold policy: per-class + calibration** (temperature scaling via `bench/calibrate.py`; per-class thresholds in `config/thresholds.toml`) | A (script exists, artifact absent F-40) | staged webcam positives (G-03) + negatives (G-02); split by clip, `label_source` recorded | G-02 via raising FP-cost thresholds on knife/sword; G-03 via not over-thresholding pistol | F-40, SC-5, S-05, F-15 (fusion reads scores) | none | Fit temperature on calibration split; report ECE + alerts/camera-hour before/after on test split; bind artifact to sha256 `96991cd5…` |
| 3 | **Taxonomy mapping layer** (revolver→pistol∨revolver, sword→knife∨sword, foreign-class fallback; alert severity keyed on firearm/edged groups) | B (mapping problems are documented; see §3.1) | any eval with mixed taxonomies | G-03: prevents missed alerts from subtype confusion; G-02: prevents double alerts | F-09 (output mapping), SC-2 (labels field semantics) | none | Confusion study on eval split: map detections → alert labels, count subtype-caused misses/duplicates before vs after |
| 4 | **Weights swap / fine-tune on camera-domain data** (RT-DETR or D-FINE = Apache-2.0; or Ultralytics YOLO = AGPL, see §9) | B (licenses verified; accuracy gains model/dataset-specific) | curated camera-domain set + CC0 Kaggle pretrain; synthetic only for training (§2.7 rule) | G-03: largest potential recall gain on small/low-light weapons; G-02 via FP-aware fine-tune | F-09 (backend switch exists), S-21 (training), F-48 (provenance manifest), S-20 (bench) | +0–50 ms on GPU path `[estimate]`; model load size similar | A/B on positives+negatives suites: per-class AP50/recall-small, alerts/camera-hour; register in `bench/results/**` with hashes (S-20) |
| 5 | **Person-crop tiled inference** (SAHI-style on F-10 person tracks only; MIT license) | B (SAHI paper 2202.06934; cost math local) | small-object subset evaluation | G-03: recall on distant/held weapons; G-02 risk ↑ (more forwards → more FP chances) | F-09 + F-10 coupling, yolo_onnx contract (crop letterbox), S-20 | +1–2 crop forwards per interval (GPU path feasible; CPU EP not) | Measure per-class recall-small with/without crop pass at fixed interval; count added FPs on negatives suite |
| 6 | **Multi-scale/high-res re-export** (dynamic axes; 960) | A (static 640 blocks it — measured §1) | same eval sets | G-03 small-object recall; G-02 may improve (bigger context) | F-09 config, export pipeline (S-21), contract note in yolo_onnx | ≈2.25× forward cost `[estimate]` | Re-export dynamic; sweep 640/960; per-class recall-small + GPU latency registration |
| 7 | **Synthetic-data augmentation** (renderer/paste-augment for rare classes: sword/rifle) | B (precedent HF synth models; effect unverified) | **training only** — eval stays real+human-labelled (§2.7 rule) | G-03 on rare classes; G-02 risk if synthetic negatives too clean | S-21 tooling, F-48 provenance, S-20 eval hygiene | none at runtime | Train w/ and w/o synthetic on identical real splits; evaluate ONLY on real test split; report per-class deltas |
| 8 | **Ensemble/WBF instead of greedy NMS** | B (2509.23697 reports occlusion robustness) | occluded subset | G-03 occluded subset; G-02 risk ↑ | SC-2/`yolo_onnx` NMS contract change, S-20 | +1 full forward per frame (2-model ensemble) | Only if #1–#4 plateau: compare greedy NMS vs WBF on occluded subset at matched alerts/camera-hour |

**Interpretation for WT-18**: #1–#3 are cheap, license-clean, and directly attack G-02; #4 is
the accuracy bet and must decide the license question first (§9); #5–#8 are gated on the GPU
path being real (currently an uncommitted claim).

## 8. License incompatibilities (explicit)

| Asset | License | Incompatibility flag |
|---|---|---|
| Ultralytics code + YOLOv8/YOLO11/YOLOv12 weights | **AGPL-3.0** (LICENSE files read; YOLO11 doc states AGPL + Enterprise) | **Incompatible with closed-source distribution** without an Enterprise license. Internal use OK; distribution of AGPL-derived models/services triggers source-disclosure obligations. |
| Kaggle `trainingdatapro/people-with-guns-segmentation-and-detection` (HF mirror `UniqueData/…`) | **CC BY-NC-ND 4.0** | **NonCommercial + NoDerivatives**: prohibited for commercial product training and arguably for any fine-tuned derivative. Do not use. |
| Dricz gun-detection series | mixed apache-2.0 / **openrail** | openrail is use-restricted (not OSI); mixed licensing within one series is a provenance red flag. |
| Any Roboflow "Weapondetect" project | per-project (unverified, pages 403) | Must be read before download; Roboflow mixes CC BY / CC BY-NC / custom terms. |
| Kaggle ODbL set (`ugorjiir/gun-detection`) | ODbL | Share-alike on redistributed database; keep out of shipped artifacts. |
| UGR/DASCI OD-WeaponDetection | CC BY-SA 4.0 | ShareAlike for dataset redistribution; internal training is fine, re-publishing derived datasets must stay BY-SA. |
| Unknown-license sets (Kaggle `ankan1998/…`, `kruthisb999/…-cctv-videos`, several HF cards with no license field) | none / unknown | Default = all rights reserved + scraped-content risk. **Blocked** from use until rights established. |
| `RT-DETR` (lyuwenyu) / `D-FINE` | **Apache-2.0** | Compatible; preferred stacks if AGPL is unacceptable. |

## 9. Engineer handoff

**For WT-18 (weapon improvements)**:
1. Start with the G-02 protocol: instrument FP logging on the negatives suite before touching
   weights (rec #1). The result doubles as the hard-negative training set.
2. Decide the license question **first** (§8): AGPL (Ultralytics retrain) vs Apache-2.0
   (RT-DETR/D-FINE). It determines the training stack, not the other way around.
3. Adopt `bench/calibrate.py` for weapon scores and record `model_sha256` = the ONNX hash
   (F-40 closure); move all thresholds into `config/thresholds.toml` (G-05/SC-5).
4. Add the taxonomy mapping layer at the F-09 output boundary (rec #3) before any per-class
   threshold work — otherwise subtype noise pollutes calibration.
5. Treat CPU-EP operation as degraded mode with explicit health state; only tune operating
   points on the configuration you will actually run (GPU path must be registered by S-20
   before its numbers enter any claim).

**For WT-12 (integration)**:
1. Detection boxes in model space are quantization-noisy when evidence is 960 — crop evidence
   with padding (§6) and keep source-pixel coordinates authoritative (SC-2 `tracks`).
2. The static-640 export means `WEAPON_INPUT_SIZE` is advisory only; don't document it as a
   working knob until a dynamic export lands (contract note belongs in the runtime map, not
   in UI copy).
3. Alert-level severity should use firearm/edged grouping (§3.1), so a pistol/revolver
   mapping error can never change `severity`.
4. `weapon_score`/`weapon_labels` are `null` until a producer observation id exists (SC-2);
   any analytics on weapon signals must handle that null state (U-13 overview charts).

## 10. Gaps & limitations

- **Unidentifiable dataset names**: GDW/GWD/Weapon-NDS/COCONTS did not resolve to public
  weapon datasets in 2026-09-29 searches (§4.1). If these are internal project names, their
  definitions are outside this research pass.
- **No accuracy benchmark was run.** This is research-only: no weights were trained, no
  eval split exists yet. All accuracy statements are structural (what to measure), not
  results. Metrics must never be compared across incompatible datasets/hardware.
- **GPU latency (~43 ms) is an uncommitted claim** from the campaign seed; CPU forward
  (290–310 ms) is measured here but excludes letterbox/NMS/IPC. Neither is a full-path
  registration.
- **`keremberke/yolov8m-weapon-detection` card is unreachable (401)**; Roboflow pages 403;
  GitHub API was rate-limited (403) in this pass — license facts for repos were instead read
  from raw LICENSE files (all listed with results above); `yolov5` license was not fetched
  (marked unverified).
- **No camera device exists in this environment** (campaign constraint): camera-domain truth
  must come from staged/file fixtures; live-camera gates remain open/unmeasured.
- **wt-03 reconciled blueprint**: `docs/blueprint/` in wt-03 contains `runtime-map.md`,
  `runtime-map-verification.md`, `ownership-map.md`, `design-map.md`, `ui-contract.md` as of
  finalize time but **no INDEX.md was present**, so no reconciled INDEX could be read.
- arXiv API "updated" timestamps for older papers show 2026-09-28 (re-processing artifact of
  the API); **publication dates cited are the `published` field** (original submission dates).

## 11. Sources (fetched 2026-09-29)

Primary sources, with dates:

- Repo-local (2026-09-29 reads): `backend/models/weapon_yolo.onnx` metadata + CPU timing (this
  pass), `backend/yolo_onnx.py`, `backend/weapon.py`, `bench/calibrate.py`, wt-01
  `docs/blueprint/{runtime-map,runtime-map-verification,ownership-map}.md`, `docs/PLAN.md`.
- arXiv (via export.arxiv.org API): 2202.06934 SAHI (2022-02-14, ICIP 2022); 2304.08069
  RT-DETR (2023-04-17); 2410.13842 D-FINE (2024-10-17); 2502.12524 YOLOv12 (2025-02-18);
  2005.12872 DETR (2020-05-26); 2410.19862 Real-Time Weapon Detection Using YOLOv8
  (2024-10-23); 2509.23697 Confidence-Aware SSD Ensemble + WBF (2025-09-28); 2410.09731
  distributed armed-robbery detection (2024-10-13); 2003.00805 firearm ensemble CNNs
  (2020-02-11); 2510.13326 DEF-YOLO thermal concealed weapons (2025-10-15); 1904.02361 robust
  domain-adaptive detection (2019-04-04); 2407.05607 weakly supervised test-time DA
  (2024-07-08); 2002.06770 synthetic-to-thermal adaptation (2020-02-17).
- GitHub raw LICENSE files (read): `obss/sahi` MIT (c) 2020; `ultralytics/ultralytics`
  AGPL-3.0; `lyuwenyu/RT-DETR` Apache-2.0; `sunsmarterjie/yolov12` AGPL-3.0;
  `Peterande/D-FINE` Apache-2.0 (README badge; `master` branch); `ari-dasci/OD-WeaponDetection`
  README CC BY-SA 4.0.
- Ultralytics docs (raw): `docs/en/models/yolov8.md` (YOLOv8 released 2023-01-10; YOLOv8m
  row: 640 | 50.2 mAP | 25.9 M params); `docs/en/models/yolo11.md` (citation block
  v11.0.0, 2024; "provided under AGPL-3.0 and Enterprise licenses").
- HuggingFace REST API (`/api/models`, `/api/datasets`, searches `weapon`, `weapon detection`,
  `gun detection`, `gun`, `author=keremberke`) — listings + license tags + timestamps as cited
  in §2.2/§4.2.
- Kaggle REST API (`/api/v1/datasets/list?search=gun%20detection`) — refs, license names,
  sizes, last-updated dates as cited in §4.2.
- Springer doi 10.1007/s00607-022-01095-0 (*Orientation aware weapons detection in visual
  data: a benchmark dataset*, Computing 2022) — discovered via search; full text not fetched
  in this pass.
- Web search results (DuckDuckGo HTML/Bing, 2026-09-29) for name resolution in §4.1;
  Roboflow Universe pages returned 403 (unverified).
