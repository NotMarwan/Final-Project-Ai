---
authority: scoped
non_authoritative: true
---

# WT-06 - Violence detection: temporal/video methods, datasets, evaluation protocols, deployment evidence

| Field | Value |
|---|---|
| Worktree | `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-06` |
| Branch | `codex/sentinel-06-violence-research` |
| Baseline commit | `e86d34b5d16abcc133ad3470c8d135d00b2423d4` (clean at start; see hand-off) |
| Status | research catalogue + ranked recommendations for WT-19; **no source-code change** |
| Authority | scoped, non-authoritative (campaign rule: catalogues under `docs/campaign/` never become status or design authority) |
| Date of evidence collection | 2026-09-29 |
| Blueprint features touched (read-only) | F-07, F-08, F-14, F-15, F-40, F-47, F-48 (runtime map); scoped features for WT-19 |
| Deliverable | this file only |

Evidence labels used throughout:

* `[V]` verified this session against a primary source (arXiv API / Crossref / publisher page / official repo / WayBack snapshot), fetched 2026-09-29.
* `[I]` inference or arithmetic derived from verified material; **not** a measurement.
* `[?]` unverified / could not be checked here - do not build on it without a new check.
* Numbers quoted from other people's papers are always attributed to their dataset + protocol; they are **not** transferable to AI Sentinel (see section 8).

---

## 0. Scope, search method, and what could not be searched

### 0.1 Question

What do the literature and public artefacts actually support for improving AI Sentinel's violence path - which is a **SlowFast-style binary violence detector** running on `cuda:0` (runtime map F-07), fed by a **32-frame window with a frame-counter stride** (F-08), whose score is an **uncalibrated logit-margin sigmoid** (F-40), gated by an **N-of-M per-camera decision layer** (F-14), and evaluated today by **nothing** (campaign context: accuracy/recall/FPR are unmeasured; `docs/PLAN.md` G-02/G-03/G-04).

### 0.2 Search stack actually used (and its limits)

| Tool | Result this session |
|---|---|
| `web_search` tool | **Unusable**: every invocation returned a schema validation error (empty arguments reached the tool). All discovery below is therefore API- or fetch-based. |
| DuckDuckGo HTML/Lite | **Blocked** - served a JS/redirect shell with zero result anchors. |
| Bing | **Poisoned/unusable** - returned localised unrelated results regardless of `mkt=en-US`. |
| Semantic Scholar Graph API | **429 rate-limited** on every attempt; not used. |
| arXiv API (`export.arxiv.org/api/query`) | **Works** - all arXiv IDs in this document were fetched and their titles/dates re-read from the API, not recalled. This caught four wrong IDs (see 0.3). |
| OpenAlex API (`api.openalex.org/works`) | **Works** - used for venue/DOI/year discovery and citation counts. |
| Crossref API (`api.crossref.org/works/<doi>`) | **Works** - used for canonical titles, authors, years and **licence URLs**. |
| Direct fetch of official pages/repos/raw READMEs | **Works** - the primary source for dataset licence/availability facts. |
| WayBack Machine availability API | **Works** - used once, to read the (now removed) official DeepMind Kinetics licence statement. |
| GitHub REST search | **Works** (unauthenticated) - used only to test whether official dataset repos are still reachable. |

Consequence: this catalogue is **strong on primary-source licence/availability facts and on paper metadata**, and **weak on discovering grey literature** (blogs, vendor benchmarks, kaggle mirrors). Anything of that kind is marked `[?]`.

### 0.3 Anti-hallucination findings (recorded because they change citations)

The first pass of "IDs I remembered" was wrong four times; the API check caught it:

| Remembered | Actually is | Correct ID |
|---|---|---|
| 1812.03887 = SlowFast | "Facial Landmark Machines..." | SlowFast = **1812.03982** |
| 2010.13903 = X3D | "T^2-Net: ... Turbulence Forecasting" | X3D = **2004.04730** |
| 2303.16927 = VideoMAE V2 | an astronomy paper | VideoMAE V2 = **2303.16727** |
| 1612.08883 = TSN | "Signifying the Schrodinger cat..." | TSN = **1608.00859** |

Every arXiv ID cited below was verified by fetching it. No DOI is quoted from memory.

---

## 1. The current violence path in AI Sentinel (target of every recommendation)

All facts in this section are re-stated from `wt-01 docs/blueprint/runtime-map.md` (itself verified against the pinned commit); they are repeated here only so the recommendations are self-contained. Where the runtime map says "unmeasured", that is preserved.

### 1.1 What runs

| Aspect | Value | Anchor |
|---|---|---|
| Engine | `ViolenceInferencePipeline.process_frame`, `backend/inference.py:242-556`; SlowFast `ViolenceDetector` with X3D fallback | F-07 |
| Weights | `backend/best_model.pt`, 149,344,325 bytes, sha256 `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01` | runtime map 3.1 |
| Device | violence model registered on `cuda:0`; weapon/person ONNX on CPU EP in the registered run | runtime map 3.2 |
| Training provenance | **UNKNOWN** at this commit (no committed file records the checkpoint's lineage) | F-48, runtime map 3.6 |
| Category API text | `detection_categories.py:240-243` labels violence as "Connected to active X3D temporal engine" while the measured runtime loads SlowFast | F-29 |

### 1.2 Temporal contract (F-08) - the part that decides G-04

| Concept | Value | Anchor |
|---|---|---|
| Window | 32 consecutive frames (`WINDOW_SIZE`) | `inference.py:118` |
| Window validity | `abs(span - 31/fps) <= 10%` and every inter-frame gap `> 0` and `<= 2.1/fps` | `inference.py:517-524` |
| Stride gate | inference submitted when `valid and counter % stride == 0`; `stride` = `STRIDE` env else `config.model.stride`; committed YAML = 8, registered run = 16 | `inference.py:539`, `api.py:265` |
| Score | `margin = ((p_violence_logit - max(other_logits)) + bias) / max(0.05, temp)`, clipped to +/-20, sigmoid'd; with no calibration artifact temp=1.0/bias=0.0 | `inference.py:485-508`, F-40 |
| Smoothing | EMA applied only after `_counter > WINDOW_SIZE`, `ema_alpha` default 0.45 | F-07 |
| Hysteresis | release at `threshold - hysteresis_margin` (default 0.08) | F-07 |
| Threshold | `violence_threshold = 0.45` in `config/thresholds.toml` (sole authority) | F-01, 3.4 |
| Decision | N-of-M: `watch 0.45`, `confirm 0.65`, `confirm_n 2`, `confirm_m 3`, `min_decision_interval 0.50 s`, `cooldown 3.0 s`, history 10 s | F-14, 3.4 |
| Modality staleness | 5.0 s for violence and weapon | 3.5 |
| File clock | `captured_at = source_epoch + file_frame_index/source_fps`; live clock = monotonic capture time | SC-6, 3.5 |
| Calibration | `backend/model_calibration.json` **absent** -> defaults -> worker marks calibration `DEGRADED`; all scores carry `calibrationStatus: unverified` | F-40 |

### 1.3 Latency arithmetic implied by the current configuration `[I]`

At 30 fps input and `stride = 8` (committed YAML):

* a valid window spans `31/30 = 1.033 s` of footage;
* a window can only be scored on a stride tick, so worst-case quantisation adds up to `8/30 = 0.267 s`;
* the EMA only starts after `_counter > 32`, so the smoothed score needs additional windows to move (each extra stride = 0.267 s);
* the decision layer needs `confirm_n = 2` of `confirm_m = 3` votes, so up to ~2 more strides (0.533 s);
* then fusion/render/alert emission (F-15/F-16/F-17).

So the **theoretical floor for glass-to-alert is about 1.03 s + 0.27 s = 1.30 s** before EMA/decision-layer penalties, against `G-04 p50 <= 1200 ms`. The 32-frame window alone consumes **86 % of the G-04 p50 budget and 52 % of the p95 budget**, and this is independent of model quality. With the registered run's `stride = 16` the quantisation term doubles. This is arithmetic on committed config, not a measurement - but it means **window length and stride are first-order G-04 levers, not tuning details**, and it makes clear that `G-04` and `G-02/G-03` can push in opposite directions (long windows help recall, hurt latency).

### 1.4 What is missing around the model

* No labelled positives/negatives suite is committed as evaluation data, and no accuracy/recall/FPR measurement exists (`PLAN.md` Phase 0; runtime-map 6.2 `unmeasured_reasons.accuracy`).
* `bench/calibrate.py` exists (F-47) and is the intended home of calibration, but there is no artifact and no committed report of ECE.
* `tools/evaluate_rwf2000_subset.py` + `tools/build_rwf2000_manifest.py` exist (F-48) but RWF-2000 videos are **no longer distributable** (section 3), so this path cannot produce truth today.
* Demo clips (`demo_assets/videos/*.avi`, F-20) are the only committed video material; their content/annotations are not a labelled suite `[?]`.

---

## 2. Methods

### 2.1 The families, and which ones matter for us

The literature splits into five families. For a **32-frame, single-window, binary, real-time** detector the relevant distinctions are: (i) does the model need a second modality at inference (optical flow) or extra pre-training data; (ii) how much temporal context does it require; (iii) how expensive is one window score.

| Family | Representative work | Inference cost shape | Needs flow at inference? | Fit for AI Sentinel |
|---|---|---|---|---|
| Two-stream / motion stream (OF + RGB) | Two-Stream ConvNets - Simonyan & Zisserman, **arXiv 1406.2199** (2014-06-09) `[V]`; TSN, **arXiv 1608.00859** (ECCV 2016) `[V]` | 2x forward passes + OF extraction | **Yes** (unless OF is distilled) | Poor as-is: OF extraction was measured as *the* latency bottleneck in embedded HAR pipelines - **arXiv 2409.05662** (2024-09-09) `[V]` |
| 3D CNN, single stream | I3D - Carreira & Zisserman, **arXiv 1705.07750** (CVPR 2017) `[V]`; TSM - **arXiv 1811.08383** `[V]`; R(2+1)D `[?]` | one 3D forward pass over the clip | No | **Best structural fit**; TSM in particular moves 2D-CNN cost to temporal modelling |
| 3D CNN, dual rate | SlowFast - **arXiv 1812.03982** (2018-12-10) `[V]`; X3D - **arXiv 2004.04730** (2020-04-09) `[V]` | one pass, two pathways / one expanded path | No | This is what we run. X3D's own claim is the efficiency axis: **4.8x fewer multiply-adds and 5.5x fewer parameters for similar accuracy** `[V, arXiv 2004.04730 abstract]` |
| Video transformers | TimeSformer - **arXiv 2102.05095** `[V]`; ViViT - **arXiv 2103.15691** `[V]`; VideoMAE - **arXiv 2203.12602v3** `[V]`; VideoMAE V2 - **arXiv 2303.16727v2** (2023-03-29) `[V]` | one pass, attention over tokens | No | Strong accuracy, heavier per window on a 3060; only worth it with sparse sampling (see 2.6) |
| Weakly/semi-supervised + anomaly framing | UCF-Crime MIL - **arXiv 1801.04264** (CVPR 2018) `[V]`; XD-Violence - **arXiv 2007.04687** (ECCV 2020) `[V]`; RTFM - ICCV 2021, DOI `10.1109/ICCV48922.2021.00493` `[V]`; VadCLIP - AAAI 2024, DOI `10.1609/aaai.v38i6.28423` `[V]` | same forward pass, different head/loss | No | Relevant for **training without frame labels**, which is our situation (we have no labelled suite at all) |

### 2.2 Violence-specific supervised recognisers

| Work | Source | Claim (their data) | Note for us |
|---|---|---|---|
| RWF-2000 + **Flow Gated Network** | **arXiv 1911.05913v3** (2019-11-14; ICPR 2021, DOI `10.1109/ICPR48806.2021.9412502`) `[V]` | 2000 clips, 300k frames, 5 s @ 30 fps from YouTube surveillance footage; FGN "obtains an accuracy of **87.25 %** on the test set" `[V]` | The canonical binary violence baseline. Uses **3D-CNN + optical flow** - i.e. the original SOTA on this corpus needs flow. |
| **ViViD / "Video Vision Transformers for Violence Detection"** | **arXiv 2209.03561v2** (2022-09-08) `[V]` | ViViT-based end-to-end violence detector; data augmentation to compensate for weaker inductive bias; "auspicious performance on some of the challenging benchmark datasets" - **no numeric headline in the abstract** `[V]` | A transformer violence baseline that cites RWF-2000-class corpus; useful only as a citation, not as an accuracy target. |
| **Vision-based Fight Detection from Surveillance Cameras** | **arXiv 2002.04355** (2020-02-11) `[V]` | LSTM (+ attention) over surveillance footage; introduces a new surveillance fight dataset and evaluates on it plus Hockey Fight and "Peliculas" (Movies) | Evidence that **recurrent head over CNN features** was the pre-3D-CNN default; also an extra surveillance corpus. |
| **Fight detection: anomaly detection vs action recognition** | **arXiv 2205.11394** (2022-05-23) `[V]` | Uses **UBI-Fight** and **NTU-CCTV-Fight** (frame-level labels); finds "anomaly detection has similar or even better performance than the action recognition" and uses AD to bootstrap training data iteratively | Directly supports: **binary supervised classification is not automatically the right framing**; also names two surveillance corpora with frame-level labels (see 3.1). |
| **CrimeNet** | Neural Networks 2023, DOI `10.1016/j.neunet.2023.01.048` `[V]` (metadata only) | ViT + neural structured learning for violence detection | `[?]` numbers not read. |
| **Vi-SAFE** | **arXiv 2509.13210** (2025-09-16) `[V]` | YOLOv8 (GhostNetV3 backbone, EMA attention, **pruning**) for person regions + TSN classifier; **RWF-2000 accuracy 0.88 vs TSN alone 0.77** `[V]` | Two lessons: person-cropping + temporal classifier is a competitive cheap design; and pruning is claimed to preserve accuracy while cutting cost. |
| **Short-Window Sliding Learning** | **arXiv 2511.10866v2** (2025-11-14) `[V]` | Divides video into **1-2 s clips**, LLM auto-caption labelling, "each short clip fully utilizes all frames"; **RWF-2000 95.25 %**, **UCF-Crime 83.25 %** `[V]` | The most directly relevant 2025 result for our **window design**: short, dense (non-strided) windows. Caveat: labels come from an LLM auto-labeller, so the numbers are **not** independently-labelled truth. |
| **Multi-task surveillance with temporal event validation** | **arXiv 2607.03131** (2026-07-03) `[V]` | SlowFast-R50 trained on a **purpose-built vandalism set of 614 clips** -> **94.33 %** classification accuracy; then "temporal event-validation architecture based on **multi-frame confirmation, confidence-weighted voting, and cascaded filtering**" to convert frame predictions into events | Best direct evidence for our F-14-style N-of-M gating: the published system explicitly adds a temporal validation stage on top of SlowFast because per-frame outputs are noisy. Note the caveat: 614 self-collected clips, no independent suite reported. |

### 2.3 Weakly/semi-supervised and anomaly-framing

* UCF-Crime introduced deep MIL ranking with sparsity + temporal smoothness constraints to localise anomalies from **video-level** labels (`arXiv 1801.04264`) `[V]`.
* XD-Violence is explicitly built for **weak labels with audio + video, 217 h, 4754 untrimmed videos**, with the paper's own method using three parallel branches plus an "approximator to meet the needs of online detection" (`arXiv 2007.04687`; project page `https://roc-ng.github.io/XD-Violence/`) `[V]`.
* RTFM (ICCV 2021) and VadCLIP (AAAI 2024) are the current strong WS-VAD references; VadCLIP adapts a vision-language model to the weak setting `[V, metadata]`.
* **2026 caveat that matters:** "What Do Interaction Representations Actually Measure? Pre-Event Separability in Weakly-Supervised Violence Detection" (**arXiv 2608.27879**, 2026-08-28) `[V]` reports that, holding tracker/temporal head/supervision/folds fixed, **no pose-based representation outperforms coarse bounding-box geometry**, and that on XD-Violence, **whole-frame context matches or exceeds person-crop appearance**. It then tests what the benchmark measures by scoring **only frames preceding the annotated onset**. Practical implication for us: claims about "richer temporal/pose features" are not automatically true, and **evaluation must control for how much pre-event information leaks into the score**.

### 2.4 Adaptation without new labels

| Method class | Primary source | What it does | Cost/risk for us |
|---|---|---|---|
| Test-time adaptation (TTA) for video | **Video Test-Time Adaptation for Action Recognition**, CVPR 2023, DOI `10.1109/CVPR52729.2023.02198` `[V]` (abstract read) | Aligns online test statistics to training statistics and enforces prediction consistency across temporally augmented views of the same test video | Runs **on the live stream, no labels**; adds forwards per sample. Directly targets the domain gap our staged/webcam footage will create. |
| Self-supervised TTA | **ST2ST**, CVPRW 2024, DOI `10.1109/CVPRW63382.2024.00112` `[V, metadata]` | Self-supervised variant | `[?]` details not read. |
| Unsupervised/semi-supervised DA for action recognition | e.g. drone-to-ground DA, WACV 2020, DOI `10.1109/WACV45572.2020.9093511` `[V, metadata]` | Feature alignment between source and unlabelled target domain | Needs a target-domain corpus; we have none yet. |
| Calibration (not adaptation) | **On Calibration of Modern Neural Networks**, Guo et al., **arXiv 1706.04599** (2017-06-14) `[V]` | Temperature scaling + ECE | This is the method already anticipated by `F-40`/`bench/calibrate.py`; the recommendation is to **run it and commit the artifact**, not to invent a new one. |
| Vision-language weak supervision | VadCLIP (AAAI 2024) `[V, metadata]` | CLIP-style pseudo-labelling for VAD | Heavy on a 3060; only as a *labelling aid* offline. |

### 2.5 Streaming, windowing, time-to-detection

This is the section that maps directly onto F-08 and G-04.

| Source | Evidence | Design consequence |
|---|---|---|
| **Online Detection of Action Start (ODAS)**, **arXiv 1802.06822v3** (2018-02-19) `[V]` | Defines the task as detecting an action **start** in untrimmed streaming video "with high categorization accuracy and **low detection latency**"; contributions include **GAN-generated hard negative samples** for ambiguous background, explicit temporal-consistency modelling around the start, and **adaptive sampling** to handle labelled-start scarcity | Gives us (a) a metric vocabulary - latency from onset, not just classification accuracy; (b) a concrete hard-negative strategy. |
| **StartNet**, **arXiv 1903.09868** (2019-03-23) `[V]` | Decomposes ODAS into per-frame classification (ClsNet) + class-agnostic start localisation (LocNet); notes "subtle appearance difference near the action starts" | Supports a two-head design (score + onset localiser) if we ever need per-second exports. |
| **Short-Window Sliding Learning** (2025) `[V]` | 1-2 s clips fully utilise all frames; strong RWF-2000 result | Suggests **32 frames @ 30 fps (1.07 s) is in the right regime**, but the paper's advantage came from *dense* use of the window, not from sampling fewer frames inside it. |
| **Video Test-Time Adaptation** (CVPR 2023) `[V]` | prediction consistency over **temporally augmented views** of the same sample | A cheap, offline-verifiable ensemble idea: score several temporal offsets/crops of one window and aggregate. |
| **Dense sampling matters (TSM)** `[V]` | TSM's premise: 3D CNNs are accurate but expensive; 2D CNNs are cheap but cannot model time - TSM shifts features along the temporal axis instead | If we keep a 2D-flavoured backbone, temporal shift is the cheap way to gain temporal context. |
| **Sparse clip sampling (X3D / TimeSformer / VideoMAE)** `[V]` | X3D: same accuracy with 4.8x fewer multiply-adds; TimeSformer/VideoMAE papers are built around short, sparsely sampled clips (8-16 frames) | Sparse sampling inside the window is the standard way to cut per-window cost; **but note it reduces within-window temporal resolution**, which is exactly what a fight onset needs. |

**Onset semantics.** Nothing in our codebase defines an "onset" - `window_valid` is a *clock-integrity* flag (F-08), not an event-localisation label, and the alert payload (SC-4) carries no onset timestamp. Any time-to-detection measurement we make must therefore *define* onset externally, from an independently labelled fixture (see section 4).

### 2.6 Hard negatives and where false positives actually come from

| Source | Evidence | Consequence |
|---|---|---|
| ODAS `[V]` | hard negatives generated adversarially for "ambiguous background" | Ambiguity is a **known, modelled** problem - not an implementation detail. |
| **Fight Detection from Still Images in the Wild**, **arXiv 2111.08370v2** `[V]` (abstract read) | "even without exploiting the temporal information, it is possible to detect fights with high accuracy by utilizing appearance only"; same-dataset accuracy near 100 % but **cross-dataset ~70 %**; there is **dataset bias** in fight recognition; SMFI is one of the two most representative of five datasets | Two warnings: (a) appearance-only shortcuts can pass same-dataset tests - our fixtures must include pose-neutral look-alikes; (b) any single-corpus number is inflated. |
| **Public surveillance VAD negative causes** | The 2024 review *Literature Review of Deep-Learning-Based Detection of Violence in Video*, Sensors, DOI `10.3390/s24124016` `[V]`, groups **21 challenges** for AI-based video violence detection | Gives a citable checklist of challenge classes (occlusion, illumination, crowd, camera motion, etc.) without inventing them here. |
| **Deployment reliability audit**, **arXiv 2606.29506** (2026-06-28) `[V]` | Same-dataset frame AUC **0.704** vs cross-dataset **0.499** (chance) across UCSD-Ped1/Ped2, CUHK Avenue, ShanghaiTech and 4 frozen backbones; the strongest backbone (DINOv2, 0.901 same-dataset on Ped2) has the **largest** drop; "even at a favourable operating point the **false-alarm rate is on the order of 31,931 per hour**" | The single most useful number for our G-02 design: benchmark AUC does **not** predict operator-facing alarm load. Report **FPs per camera-hour**, not just AUC/accuracy. |
| **Temporal event validation** (2026) `[V]` | multi-frame confirmation + confidence-weighted voting + cascaded filtering on top of SlowFast-R50 | Validates the *shape* of our F-14 gating, and suggests two cheap upgrades: **confidence-weighted** votes and a **cascade** (cheap gate before the expensive model). |
| **Pre-event separability** (2026) `[V]` | whole-frame context >= person-crop appearance; frames preceding onset carry signal | Some "hits" in naive evaluation may be pre-event context, not violence. Fixtures must control this. |

**Sports and phone-use negatives.** Hockey Fight's non-fight half is literally *sports* footage (NHL) `[V, section 3]`, and the Movies dataset draws its negatives from public action-recognition corpora `[V]` - i.e. the field's two oldest violence corpora already encode "sports" and "general human motion" as negatives. Hugging/handshake/waving/phone-use are the campaign's own G-02 list (`docs/PLAN.md`) and have **no dataset we can lawfully download that isolates them** (section 3.3) - they must come from our own footage or from licence-clean corpora used as *sources of hard clips*, not as a named "hugging dataset".

### 2.7 2024-2026 snapshot (newest first, all `[V]` metadata-level unless noted)

| Date | Work | Why it matters |
|---|---|---|
| 2026-08-28 | **arXiv 2608.27879** pre-event separability in weakly-supervised violence detection | benchmark validity; appearance/context vs geometry |
| 2026-08-09 | **arXiv 2608.08887** City Sentinel: unified multi-threat surveillance framework (6 capabilities incl. violence) | integrated-systems reference |
| 2026-08-07 | **arXiv 2608.06691** CoDAT: dual-attention transformer, "low-cost temporal modeling for **efficient edge** action recognition" | edge transformer efficiency |
| 2026-07-06 | **arXiv 2607.04882 / 2607.14760** (radar, camera-tamper) | out of scope, listed only to show the search space |
| 2026-07-03 | **arXiv 2607.03131** multi-task surveillance + **temporal event validation** | see 2.6 |
| 2026-06-28 | **arXiv 2606.29506** "Benchmark AUC Is Not Deployable Reliability" | see 2.6 / section 4 |
| 2026-05-04 | **arXiv 2605.02659** moderate-violence detection (pushing) via YOLO11 + pose + Random Forest | cheap pose-geometry baseline; relevant to "pushing" hard cases |
| 2026-04-02 | **arXiv 2604.03329v2** AViS-Mamba: audio stream steered by the visual stream | audio evidence can help, but only when present and clean |
| 2026-03-13 | **arXiv 2603.12693** ABAW-10 facial/affect competition report | out of scope |
| 2025-12-21 | **arXiv 2512.18809v3** FedVideoMAE (federated video moderation) | privacy-preserving training |
| 2025-11-14 | **arXiv 2511.10866v2** Short-Window Sliding Learning | window design (2.5) |
| 2025-11-10 / 2025-10-20 | **arXiv 2511.07171**, **2510.17651** federated violence detection; LoRA-tuned VLMs vs personalised CNNs | edge/federated alternatives |
| 2025-09-16 | **arXiv 2509.13210** Vi-SAFE | person-crop + TSN + pruning (2.2) |
| 2025-09-10 | **arXiv 2509.08232** GTA-Crime: **synthetic** dataset + generation framework for fatal violence detection | synthetic data cannot serve as independent truth (see 3.2 note) |
| 2025-08-19 / 2025-07-29 | **arXiv 2508.14203**, **2507.21649** VAD surveys (deep learning; DNN->MLLM) | protocol background |
| 2025-03-21 | **arXiv 2503.16916** temporal action detection compression via progressive block drop | cost reduction with recall tracking |
| 2024-09-09 | **arXiv 2405.19387**, **2409.05383** VAD surveys; **2409.05662** real-time HAR on embedded platforms (OF extraction = latency bottleneck) | deployment evidence |
| 2024-10-29 | **arXiv 2410.21991v7** RuleVAD: lightweight WS-VAD for consumer edge devices | edge VAD design |
| 2024 | **Sensors 24(12):4016** violence-detection review (21 challenges); **Neurocomputing** "Revisiting vision-based violence detection in videos: A critical analysis", DOI `10.1016/j.neucom.2024.128113` | citable modern reviews |

---

## 3. Datasets: licence, size, domain, granularity, leakage, availability (checked 2026-09-29)

### 3.1 Violence / fight specific

| Dataset | Domain | Size (verified) | Label granularity | Licence / rights (verified) | Availability 2026-09-29 | Leakage notes |
|---|---|---|---|---|---|---|
| **RWF-2000** (Cheng, Cai, Li; ICPR 2021, DOI `10.1109/ICPR48806.2021.9412502`; arXiv 1911.05913) | real surveillance footage re-published to YouTube | 2000 clips, 5 s @ 30 fps, ~300k frames | **clip-level** binary | **Videos withdrawn for privacy.** README: "Due to the privacy requirements, video files are currently not available on this website." Terms: no modification/redistribution and no commercial use without SMIIP Lab approval; must cite. `[V]` | **Not distributable.** Do not use mirrors. | Authors state they "dropped duplicated contents which appear in both training set and validation set" `[V]` - i.e. duplication existed; our own splits must dedupe by source session/video, not just by clip. |
| **UCF-Crime** (Sultani, Chen, Shah; CVPR 2018, DOI `10.1109/CVPR.2018.00678`; arXiv 1801.04264) | real CCTV surveillance, 13 anomalies incl. fighting | **1900 untrimmed videos, 128 h** `[V]` | **video-level weak labels** (frame-level in later work) | Project page (`crcv.ucf.edu/projects/real-world/`) carries **no licence text** - only "© Copyright 2011 CRCV". `[V]` Treat as research request; no redistribution. | Project page live; download link on the page `[V]` | Weakly labelled: a "normal" video may contain near-miss behaviour. Same-camera scenes dominate -> same-scene evaluation inflates (see 4.3). |
| **XD-Violence** (Wu et al.; ECCV 2020, DOI `10.1007/978-3-030-58577-8_20`; arXiv 2007.04687) | movies/web, multi-scene, **with audio** | **4754 untrimmed videos, 217 h**, 6 categories (Abuse, Car Accident, Explosion, Fighting, Riot, Shooting) + normal `[V]` | weak labels (multi-label), plus test annotations | Project page publishes cloud-drive links (Baidu/Aliyun/OneDrive) and **no licence/terms text** `[V]` | Distribution links live but unlicensed-from-a-repo standpoint | Repository/annotations are separate; the "score branch"/online approximator implies streaming evaluation is intended. |
| **Hockey Fight** (as described in Serrano Gracia et al., PLoS ONE 2015, DOI `10.1371/journal.pone.0120448`, CC BY 4.0) | **sports** broadcast (NHL) | 1000 clips (500 fight / 500 non-fight), 720x576 source, clips limited to 50 frames and downscaled to 320x240 `[V]` | clip-level binary | The *paper* is CC BY; the *footage* is NHL broadcast -> rights do not flow from the paper. Original host `visilab.etsii.uclm.es/.../FightDetection/` now returns **404** `[V]` | **Original distribution dead**; only unofficial copies `[?]` | The non-fight half is *sports*, exactly the "sports is a hard negative" case - but we cannot lawfully redistribute it. |
| **Movies** ("Peliculas", same source) | action movies | 200 fight clips; non-fight clips drawn from public action-recognition datasets `[V]` | clip-level binary | Movie footage copyright with studios; host **404** `[V]` | **Dead** | Movie lighting/editing distributions differ sharply from CCTV. |
| **VSD / Violent Scenes Dataset** (MediaEval 2011-2014 Affect task; Multimedia Tools & Applications 2014, DOI `10.1007/s11042-014-1984-4`; VSD2014, DOI `10.1109/CBMI.2015.7153604`) | Hollywood movies + web videos | scene selection + features released by InterDigital; 86 web videos under **CC BY 3.0**; movie scenes are references, not redistributed content `[V]` | scene-level | InterDigital terms: "may not be modified or used for commercial purposes"; modification "for scientific research purposes only"; commercial licence negotiable `[V]` | Request via InterDigital ToU page `[V]` | Movie-domain; not surveillance. |
| **Violent Flows** (Rabiee et al., CVPRW 2012, DOI `10.1109/CVPRW.2012.6239348`) | real crowd violence (YouTube) | not verified here | clip-level | Host attempt `openu.ac.il/home/hassner/data/violentflows/` -> **403** `[V]` | `[?]` - must re-check before proposing | Crowd domain; motion-based methods historically evaluated here. |
| **AIRTLab dataset** (Bianculli et al., Data in Brief 2020, DOI `10.1016/j.dib.2020.106587`) | staged/annotated violence for research | not verified here (publisher page 403) | `[?]` | **Article licence CC BY 4.0** (Crossref `vor` field) `[V]`; dataset's own terms not verified | Data-in-Brief requires public availability; locate the Mendeley/other DOI before proposing `[?]` | Potentially the cleanest licence-clean acquisition candidate; must verify composition before use. |
| **SCVD** (introduced in arXiv 2002.04355) | surveillance camera fights | paper says the new dataset "is made publicly available" `[V]` | clip-level | not stated in abstract `[?]` | `[?]` | - |
| **UBI-Fight**, **NTU-CCTV-Fight** (used in arXiv 2205.11394) | surveillance fights | both used because they have **frame-level** annotations `[V]` | frame-level | `[?]` | `[?]` | Frame-level labels are exactly what a time-to-detection protocol needs - worth chasing. |
| **SMFI** (arXiv 2111.08370) | still images of fights | one of five fight datasets compared; found "one of the two most representative" `[V]` | image-level | `[?]` | `[?]` | Useful only as an appearance-only stress set. |
| **GTA-Crime** (arXiv 2509.08232) | **synthetic** fatal-violence generation framework | `[V, abstract]` | synthetic | `[V]` synthetic | paper | **Cannot be independent test truth** (campaign rule; PLAN.md). |

### 3.2 Auxiliary / pretraining corpora

| Dataset | Size (verified) | Licence (verified) | Notes |
|---|---|---|---|
| **KTH Actions** | 2391 sequences, 25 subjects, 6 actions (walking, jogging, running, boxing, hand waving, hand clapping), 25 fps, 160x120, static camera, homogeneous background `[V]` | "publicly available for **non-commercial** use"; cite Schuldt/Laptev/Caputo ICPR'04 `[V]` | Single-person, staged, grayscale-ish, no interaction -> **cannot** supply hugging/handshake/phone negatives (PLAN.md already recorded this). Useful only as an auxiliary clip source. |
| **UCF101** | 13,320 videos, 101 classes `[V]` | Page contains **no licence text** - only "© Copyright 2011 CRCV" `[V]`; underlying content is YouTube-uploaded | Common fine-tuning target; see VideoMAE's 91.3 % UCF101 result `[V]`. |
| **ActivityNet** | Release 1.3: 200 classes, 10,024 train / 4,926 val videos / 5,044 test (labels withheld) `[V]` | Repo `github.com/activitynet/ActivityNet` is **MIT** - that covers *tools*, **not** the annotations/videos `[V]`; annotation licence not stated on the download page `[?]` | Untrimmed videos -> temporal localisation protocols. |
| **Kinetics (K400/600/700)** | 400/600/700 classes, >=400 clips/class, ~10 s per clip `[V, CVDF README]` | Official DeepMind page (WayBack snapshot 2022-03-23): "The kinetics dataset is licensed by Google Inc. under a **Creative Commons Attribution 4.0 International License**." `[V]` Videos are **YouTube links** - upstream copyright stays with uploaders `[V]` | Backbone pretraining source (I3D/SlowFast/X3D/VideoMAE were all pretrained here). CVDF README warns "**the k400 validation set is largely part of the k700 training set**" `[V]` - a textbook cross-version leakage trap. |

### 3.3 Rights-checked acquisition position for AI Sentinel (recommendation, not approval)

**May be pursued (subject to orchestrator approval and the no-downloads-without-rights rule):**

1. **AIRTLab (Data in Brief 2020)** - `CC BY 4.0` for the article, so redistribution terms are at least explicit `[V]`; still need the dataset's own DOI/terms and composition `[?]`.
2. **VSD / MediaEval** - research-only, non-commercial, request-based, and the *movie* part is only references + features `[V]`. Usable as a movie-domain stress set, not as CCTV truth.
3. **Kinetics** - `CC BY 4.0` per the official statement, videos via YouTube `[V]`. Usable for pretraining/auxiliary negatives; not for CCTV-domain claims.
4. **KTH** - non-commercial auxiliary clips `[V]`.
5. **UCF101 / ActivityNet** - no explicit licence text `[V]/[?]`; use only if the orchestrator accepts the research-use convention, and never redistribute.

**Must NOT be used for this campaign:**

* **RWF-2000** videos or any unofficial mirror - the authors withdrew them for privacy and forbid redistribution `[V]`. This invalidates the existing `tools/evaluate_rwf2000_subset.py` path *as an evidence source*: the tool may remain, but it cannot produce truth today.
* **Hockey Fight / Movies** - original hosts are dead `[V]` and the underlying footage is NHL/studio copyright.
* **XD-Violence** - no licence text; cloud-drive redistribution `[V]`. *(Flag for the orchestrator: it is the most attractive corpus on paper - 217 h, audio, weak labels - but we have no documented right to use it.)*
* Any synthetic or LLM-pseudo-labelled corpus as **independent** test truth `[V, PLAN.md; arXiv 2511.10866 relies on LLM auto-labelling - acceptable for training, never for acceptance]`.
* Any footage of identifiable people, as per campaign rules.

**Consequence for G-02/G-03:** no lawfully-available public corpus isolates "hugging / handshake / waving / phone use" in a CCTV setting. Those negatives must be produced locally (consented, non-identifying, or synthetic-free staged clips) - which is a *Phase 0 harness* dependency, not a research output.

---

## 4. Evaluation protocols

### 4.1 Metric families and what each one hides

| Level | Metric | Used by | What it hides |
|---|---|---|---|
| Clip | accuracy / F1 on balanced clips | RWF-2000 (FGN 87.25 %) `[V]`, Vi-SAFE 0.88 `[V]` | Balanced-clip accuracy says nothing about alarm load on hours of quiet footage. |
| Frame | ROC-AUC / AP | UCF-Crime, XD-Violence, VAD literature `[V]` | Frame AUC is dominated by easy negatives; the 2026 audit shows same-dataset AUC 0.704 collapsing to 0.499 cross-dataset `[V]`. |
| Event | AP / tIoU at event level | XD-Violence weak supervision, ActionFormer-style TAD (**arXiv 2202.07925** `[V]`) | Requires event boundaries; we have none. |
| Operator-facing | **false alerts per camera-hour** | quantified in the 2026 audit (~31,931/h for a naive VAD operating point) `[V]` | Nothing - this is the closest analogue to what an operator experiences. |
| Latency | time-to-detection from labelled onset; p50/p95 | ODAS (arXiv 1802.06822) `[V]`; G-04 | - |
| Probability quality | ECE / reliability after temperature scaling | Guo et al. `[V]`; G-06 | - |
| Window integrity | span within +/-10 % of nominal | G-07, F-08 `[V]` | - |

### 4.2 The negatives suite (G-02) should be built from the failure modes the literature names

`docs/PLAN.md` G-02 asks for **0 confirmed alerts on >=20 benign clips: hugging, handshakes, waving, walking, phone use**. Three literature-backed additions:

1. **Ambiguity-focused negatives** (ODAS builds these adversarially `[V]`): close-contact-but-benign, fast arm motion, crowd push.
2. **Sports-like motion** (Hockey Fight's negative half is NHL footage `[V]`): running, celebration, jumping.
3. **Pre-onset context control** (arXiv 2608.27879 `[V]`): include clips whose *pre-event* frames resemble violence, to catch detectors that score context rather than the act.

Also: because appearance-only fights are detectable (`arXiv 2111.08370` `[V]`), the suite must include **pose-neutral** look-alikes (two people leaning over a phone, physiotherapy-like contact), otherwise the model can win by appearance.

### 4.3 Cross-dataset generalization: the strongest warning in this catalogue

The 2026 audit (`arXiv 2606.29506`) is the cleanest evidence available that **same-scene evaluation is not a deployment predictor**:

* same-dataset frame AUC **0.704** vs cross-dataset **0.499** over UCSD-Ped1/Ped2, CUHK Avenue, ShanghaiTech and four frozen backbones `[V]`;
* the best same-dataset backbone (DINOv2, up to 0.901 on Ped2) had the **largest** degradation `[V]`;
* the collapse reproduced with a different detector (PaDiM: 0.202 vs 0.208 gap) `[V]`;
* **false-alarm rate ~31,931 per hour** at a favourable operating point `[V]`.

And `arXiv 2111.08370` independently reports near-100 % same-dataset vs **~70 % cross-dataset** for fight recognition `[V]`.

**Therefore:** any G-02/G-03 number produced by splitting a single recording session into train/test must be labelled `same-scene` and must not be presented as deployment performance. Our fixtures must, at minimum, hold out **whole sessions/cameras**.

### 4.4 Leakage-prevention checklist (derived from verified sources)

| Hazard | Evidence | Rule for our harness |
|---|---|---|
| Duplicate clips across splits | RWF-2000 authors had to remove duplicates that appeared in both train and validation `[V]` | Deduplicate by content hash **and** by source session before splitting. |
| Adjacent frames across a split boundary | standard; our window is 32 frames `[V, F-08]` | Emit a **>= window-length guard gap** (>=32 frames, use 1 s) between a train clip and any test clip from the same source. |
| Same identity/scene on both sides | Kinetics k400-val inside k700-train `[V]` | Split by source file/scene; never by clip within the same scene. |
| Pretraining-set overlap with test set | Kinetics->UCF101 conventions `[V]` | If we ever pretrain on Kinetics/UCF101, record it and exclude overlapping content from our test set. |
| Pseudo/synthetic labels as truth | PLAN.md rule + GTA-Crime `[V]` | Never used for acceptance. |
| Pre-onset signal | arXiv 2608.27879 `[V]` | For any "event" claim, also report the negative control on frames strictly before onset. |

### 4.5 Recommended evaluation protocol for AI Sentinel (concrete, harness-anchored)

This is the protocol every recommendation in section 6 is measured against.

1. **Fixtures** (owned by the Phase-0 harness, stored outside git if they contain footage):
   * positives: >=20 short clips with a **labelled onset frame/time** (staged, close-range, webcam-scale, mirroring the G-03 wording in `PLAN.md`);
   * negatives: >=20 clips covering the six G-02 classes + the three literature additions in 4.2;
   * at least **two distinct sessions/cameras** so a session-level hold-out exists.
2. **Metrics reported together** (never one alone):
   * confirmed alerts per both suites (G-02 = 0, G-03 >= 90 %);
   * **false alerts per camera-hour**, extrapolated from the negative-suite duration (this is the metric `arXiv 2606.29506` shows is non-negotiable) `[V]`;
   * time-to-detection from labelled onset, p50/p95 (G-04), computed as `alert_emit_ts - onset_ts` using the existing monotonic `captured_at` clock (SC-6);
   * window integrity rate (G-07) from `window.valid` + `spanSeconds` fields already emitted by F-08;
   * ECE before/after calibration (G-06) using `bench/calibrate.py`.
3. **Score semantics reported**: `_last_raw_conf`, `_last_calibrated_conf`, `calibrationStatus` - all already in the observation payload (F-07/F-12/SC-2). Reporting only the EMA-smoothed score hides the ramp.
4. **Negative control**: rerun the same measurement with the violence threshold forced to 1.0 (should yield zero alerts) and with a shuffled window clock (should break `valid`) - this catches harness bugs before they become "model improvements".
5. **Two-condition requirement**: a change is accepted only if it is measured with the **same fixtures** before/after, at **fixed threshold**; threshold retuning is a separate, declared step (otherwise every change "passes" by moving the threshold).
6. **Revision discipline**: `bench/results/**` currently belongs to revision `6fb3bcac...`, not our commit `[V, runtime-map B-5]`; every new measurement must record its revision + model hashes.

---

## 5. Deployment evidence on modest hardware

### 5.1 What the literature actually demonstrates

| Source | Evidence | Reading for a 12 GB RTX 3060 |
|---|---|---|
| X3D `[V]` | "4.8x and 5.5x fewer multiply-adds and parameters for similar accuracy than previous work"; high spatiotemporal resolution with very small width | X3D is the **documented efficiency route inside our own codebase** (F-07 already has an X3D fallback) - but the runtime map notes the shipped path loads SlowFast `[V]`. |
| Real-time HAR on embedded platforms (arXiv 2409.05662, 2024) `[V]` | Identifies **optical-flow extraction as the latency bottleneck** in a SOTA HAR pipeline and explores cheaper motion features | Argues against adding an OF stream at inference for G-04. Motion context should come from the backbone (SlowFast fast pathway) or the existing cheap motion score (F-11). |
| Vi-SAFE (arXiv 2509.13210, 2025) `[V]` | Lightweight YOLOv8 (GhostNetV3 + pruning) for person regions + TSN; RWF-2000 0.88 vs 0.77 for TSN alone | Two-stage (detect person -> classify region) is a legitimate cheap design; **but** it adds a detector dependency per frame, and our person detector already runs (F-10). |
| CoDAT (arXiv 2608.06691, 2026) `[V]` | Dual-attention transformer designed for IoT edge latency/memory/power | Evidence that attention can be made cheap, but no FPS numbers were verified here. |
| RuleVAD (arXiv 2410.21991, 2024) `[V]` | Decoupled dual-branch lightweight WS-VAD for consumer edge devices | Precedent for splitting cheap/expensive branches instead of one big model per window. |
| FPGA-QHAR (arXiv 2311.03390) `[V, metadata]` | Throughput-optimised **quantized** HAR on the edge | Quantization is used for throughput; **accuracy-vs-recall effect not verified here**. |
| Energy-aware pruning/quantization for real-time video (J. Real-Time Image Processing 2025, DOI `10.1007/s11554-025-01703-0`) `[V, metadata]` | Pruning + quantization + hardware optimisation for real-time video analysis | Cost-reduction precedent; details not read. |
| TAD compression by progressive block drop (arXiv 2503.16916, 2025) `[V, metadata]` | Compresses temporal-action-detection models by dropping blocks | A method to watch if a heavier temporal model is ever adopted. |

**Honest gap:** we found **no** study that measures INT8/pruned **recall on a violence detector with an operator-facing false-alerts-per-hour metric**. Every quantization/pruning claim above is either throughput-oriented or accuracy-on-a-benchmark. The recall effect on *our* model must be measured locally (RTX 3060, ONNX/TensorRT EP) before adoption.

### 5.2 Window length vs latency budget (our numbers, arithmetic only) `[I]`

Using the committed configuration (`WINDOW_SIZE = 32`, `stride = 8`, threshold 0.45, N-of-M 2/3) from F-07/F-08/F-14:

| Quantity | stride 8 (YAML) | stride 16 (registered run) |
|---|---|---|
| Window span @30 fps | 1.033 s | 1.033 s |
| Scoring period | 0.267 s | 0.533 s |
| Floor: onset -> first scorable window | ~1.03 s + (0-0.27 s) | ~1.03 s + (0-0.53 s) |
| + EMA ramp (alpha 0.45, starts after frame 32) | ~0.27-0.80 s | ~0.53-1.60 s |
| + decision `confirm_n = 2` of `confirm_m = 3` | up to 0.53 s | up to 1.07 s |
| **Implied floor before model inference** | **~1.3-1.6 s** | **~1.6-2.7 s** |
| G-04 budget (PLAN.md) | p50 <= 1200 ms | p95 <= 2000 ms |

Conclusion `[I]`: with the committed stride the implied floor is already **above the G-04 p50 target** before any model inference, fusion, render or transport cost. Latency is therefore a **configuration problem first** (window length, stride, N-of-M), and only second a model-speed problem. Note the tension: shortening the window to hit G-04 reduces the temporal evidence available for G-03.

### 5.3 Where false alerts actually come from (surveillance)

* **Scene/scene shift**: cross-scene AUC collapses to chance; a detector calibrated on one scene is "no better than a coin flip" on another `[V, arXiv 2606.29506]`.
* **Pre-onset context**: context frames alone carry discriminative signal `[V, arXiv 2608.27879]`.
* **Appearance shortcuts**: fights are partly detectable from stills `[V, arXiv 2111.08370]` - so a model may fire on posture alone.
* **Ambiguous-benign interaction**: explicitly modelled as a hard-negative generator in ODAS `[V]`.
* **Accumulated challenge classes**: 21 challenge categories catalogued by the 2024 Sensors review `[V]`.
* **System-level**: our own runtime map records silent alert drops on full subscriber queues (R-1) and frame drops under backpressure (R-2) - these *hide* alerts rather than create them, and `/system/metrics` is inert (N-3), so alarm load cannot currently be attributed `[V]`.

### 5.4 Score semantics under deployment conditions

Two hazards visible in our own code that interact with any "improve recall" work:

1. **EMA ramp after frame 32** (`_counter > WINDOW_SIZE`): the first windows after stream start (and after every EOF reset, F-39) are effectively un-smoothed - a threshold sweep that ignores `_counter` will see inconsistent behaviour `[V, F-07]`.
2. **Uncalibrated sigmoid of a logit margin** with no artifact: the score is monotone in the margin but is **not** a probability, so "0.45" cannot be read as "45 % confidence". Any recommendation that treats the threshold as a probability is invalid until F-40 produces an artifact `[V, F-40 + runtime map 3.3]`.

---

## 6. Recommendation table for WT-19 (ranked)

How to read the columns:

* **Evidence level** - `A` = multiple primary sources agree; `B` = one primary source plus arithmetic; `C` = single source / metadata-only, treat as hypothesis.
* **Evidence dataset/protocol** - what the literature measured; **never** our data.
* **G-benefit** - expected direction only (`++` primary, `+` secondary, `?` uncertain).
* **Effort / F-IDs** - where the change lands in our tree (runtime-map feature IDs; slice IDs from the ownership map in brackets).
* **3060 cost** - inference-time cost relative to today.

| # | Recommendation | Evidence level | Evidence dataset / protocol | G-02 | G-03 | G-04 | Effort / F-IDs [slice] | 3060 cost | Verification experiment (see 7.x) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Build the labelled fixture harness and publish a baseline before touching the model** | **A** - `PLAN.md` Phase 0; `arXiv 2606.29506` proves benchmark numbers are not deployment numbers | four VAD corpora, 4 backbones, same- vs cross-dataset; our fixtures will be local/staged | `++` (enables) | `++` (enables) | `++` (enables) | M - `bench/**` [S-20], demo clips F-20; no backend edit | none | 7.1 |
| 2 | **Calibrate the violence score and commit `model_calibration.json`** (temperature scaling + bias, ECE report) | **A** - Guo et al. `arXiv 1706.04599`; `PLAN.md` G-06; F-40 already implements the consumer | post-hoc calibration on held-out clips; ECE | `+` (threshold becomes meaningful) | `+` (threshold re-derivation) | `-` | S - F-40, `bench/calibrate.py` F-47, S-05 | none | 7.2 |
| 3 | **Re-derive window/stride from a declared latency budget** (sweep window x stride; consider overlapping windows) | **A** for the arithmetic in 1.3/5.2; **B** for the design (short-window sliding `arXiv 2511.10866`; dense sampling TSM `arXiv 1811.08383`; ODAS latency objective `arXiv 1802.06822`) | RWF-2000 95.25 % (LLM-labelled - caveat), UCF-Crime 83.25 %; TSM design rationale | `?` (shorter window can raise FP) | `+` | `++` | M - F-08, F-07, `config/thresholds.toml` [S-02/S-05] | ~1/stride; stride 8->4 doubles violence inference | 7.3 |
| 4 | **Temporal ensemble over stride offsets / overlapping windows** (mean or max over K offsets, or 50 % overlap) | **B** - TTA temporal-view consistency (CVPR 2023 `10.1109/CVPR52729.2023.02198`); multi-frame confirmation in `arXiv 2607.03131`; short-window sliding 2025 | action-recognition TTA; vandalism surveillance (614 clips) event validation | `+` | `++` | `-`/`?` (K x cost) | M - F-14 (+F-07), SC-5/SC-4 discipline [S-05/S-02] | K x per-window cost unless reused | 7.4 |
| 5 | **Hard-negative mining + decision-layer tuning on the negatives suite** (confidence-weighted N-of-M, cascade gate) | **A** - ODAS hard negatives `arXiv 1802.06822`; dataset-bias evidence `arXiv 2111.08370`; temporal event validation `arXiv 2607.03131`; FP/hour evidence `arXiv 2606.29506` | ODAS (streaming, ambiguous background); 5 fight datasets cross-dataset ~70 %; ~31,931 FP/h in VAD | `++` | `-` (must not regress) | `-` | M - F-14, F-15, S-05 [S-05/S-06] | none (logic only) | 7.5 |
| 6a | **Test-time adaptation first; fine-tuning only after a labelled local corpus exists** (TTA: align test statistics to training statistics + temporal-view consistency) | **B** - CVPR 2023 `10.1109/CVPR52729.2023.02198` (abstract read); cross-scene collapse `arXiv 2606.29506` argues against training on the wrong domain | action-recognition distribution shifts; VAD cross-dataset audit | `+` | `+` | `-` | M/L - F-07 [S-02] + S-05; fine-tuning also F-48/S-21 | TTA: small (running stats / K views); fine-tune: offline hours on a 3060 | 7.6 |
| 6b | **Zero-shot / cross-dataset transfer as a baseline, not a solution** | **A** - `arXiv 2111.08370` (~70 % cross-dataset), `arXiv 2606.29506` (0.499 = chance) | cross-corpus evaluations | `-` | `?` | `-` | S (measurement only) | none | 7.6 |
| 7 | **Make time-to-detection measurable: add onset-candidate timestamp + window ids to the alert/observation payloads (additive)** | **A** - ODAS definition of latency as the objective (`arXiv 1802.06822`) | ODAS streaming video | `-` | `-` | `++` (enables measurement) | S - F-12, F-16, F-17; SC-2/SC-4 additive [S-01/S-07] | none | 7.7 |
| 8 | **Reconcile the SlowFast/X3D identity and, if throughput demands it, adopt the X3D path** | **B** - X3D efficiency claim (`arXiv 2004.04730`: 4.8x fewer MACs, 5.5x fewer params at similar accuracy); our own F-07 fallback + F-29 wording drift | Kinetics/Charades/AVA | `-` | `?` | `+`/`++` | M - F-07 [S-02]; F-29 wording [S-17] | measured - could drop substantially | 7.8 |
| 9 | **Quantization / pruning: measure first, do not adopt yet** | **C** (gap) - throughput-oriented results only (`arXiv 2311.03390`, `arXiv 2503.16916`, DOI `10.1007/s11554-025-01703-0`); **no** violence-detector INT8 recall study found | edge HAR throughput; TAD compression | `?` | `?` | `+` | M - F-07 + bench | potentially large speedup, unknown recall cost | 7.9 |
| 10 | **Cheap person-gate / cascade before the violence model** | **B** - Vi-SAFE `arXiv 2509.13210`; RuleVAD `arXiv 2410.21991`; cascade in `arXiv 2607.03131` | RWF-2000 (0.88 vs 0.77 TSN-only); consumer edge VAD; surveillance multi-task | `+` (skip empty scenes) | `?` (risk: person detector misses) | `++` (fewer windows scored) | M - F-10 + F-07 wiring [S-04/S-02, SC-1 coordination] | reduces cost | 7.10 |
| 11 | **Audio-visual fusion** | **B** - XD-Violence `arXiv 2007.04687`; AViS-Mamba `arXiv 2604.03329` | 217 h multimodal weak supervision; Mamba audio-visual | `?` | `?` | `-` (adds audio pipeline) | L - F-31 is disabled; no CCTV audio in scope | extra dependency | (not scheduled) |
| 12 | **Re-frame as anomaly detection (weak supervision)** | **B** - `arXiv 2205.11394` (AD >= binary AR on UBI-Fight / NTU-CCTV-Fight); RTFM/VadCLIP lineage | frame-level fight corpora | `?` | `?` | `-` | L - F-48/S-21 research track; needs frame labels | offline | (research track) |

Ordering rationale: 1-2 are prerequisites (you cannot rank any other change without them); 3 is the only lever that touches G-04's structural floor; 4-5 are the highest-value model-side changes that do **not** require new labelled corpora; 6a is the adaptation path that respects "no new labels"; 7-8 are enablers; 9-12 are explicitly deferred.

---

## 7. Verification experiments (each recommendation names its test)

All experiments use the **same fixtures**, the **same threshold**, and record revision + model hashes. `bench/results/**` is not a valid baseline for our commit (`runtime-map B-5`).

### 7.1 Baseline fixture harness (rec. 1)
* Fixtures: >=20 positives with labelled onset + >=20 negatives (G-02 six classes + 4.2 additions), spanning >=2 sessions.
* Report: confirmed alerts per suite; FPs/camera-hour; TTD p50/p95; window-valid rate; ECE.
* Pass condition: **a number exists** for each metric, with sample counts and denominators, plus the negative control of 4.5(4).

### 7.2 Calibration (rec. 2)
* Fit temperature/bias on a held-out session; write `backend/model_calibration.json` in the schema F-40 already consumes; rerun 7.1.
* Assert: `calibrationStatus` != `unverified`; ECE improves on held-out clips; **alert ordering** on positives is unchanged or better.

### 7.3 Window/stride sweep (rec. 3)
* Grid: window {16, 32} x stride {4, 8, 16} (+ one overlap variant, e.g. 50 % overlap at stride 16).
* Report for each cell: TTD p50/p95 (G-04), FPs per camera-hour (G-02), positives detected (G-03), window-valid rate (G-07), violence inferences/second (G-01 headroom).
* Decision rule: pick the cell that satisfies G-04 p50 <= 1200 ms **while maximising G-03** and not regressing G-02; if no cell does, the answer is "the model must get faster", not "the budget moved".
* Known confound: `stride` is read from `STRIDE` env / `config.model.stride` (`api.py:265`) but the committed YAML says 8 while the registered run used 16 `[V]` - record which value the run actually used.

### 7.4 Temporal ensemble (rec. 4)
* Implement `max` over K stride-offset windows (K in {1, 3, 5}) at fixed per-window threshold; and/or 50 % overlap.
* Report score variance per event, TTD, FPs/hour, and the measured inference rate.
* Pass condition: FPs/hour does not increase while G-03 rises, at a stated cost in inferences/second.

### 7.5 Negative mining / decision tuning (rec. 5)
* Hold out half the negatives; use the other half (plus any historic false-positive clips the harness captured, if consented) to tune N-of-M and weighted voting.
* Report on the **unseen** half: FPs/hour, and confirm positives unchanged within the fixtures' resolution.
* Explicitly test the G-02 six classes separately, since a single aggregate number hides which class fails.

### 7.6 Adaptation ladder (rec. 6)
* Ladder: (i) frozen model, (ii) TTA statistics alignment, (iii) fine-tune on licence-clean corpora only, (iv) fine-tune on local labelled clips.
* Each rung: 7.1 metrics + a **session-level** hold-out. Rung (iii)/(iv) require the orchestrator's weight-backup + governance rule (`PLAN.md`).
* Anti-shortcut control: rerun the still-image-only variant (score a single frame replicated 32x) - if accuracy is close, the model is using appearance shortcuts `[V, arXiv 2111.08370]`.

### 7.7 Onset instrumentation (rec. 7)
* Assert: for every confirmed alert, the emitted payload carries a monotonic onset-candidate timestamp + the window/observation IDs needed to recompute TTD offline; verify one end-to-end run writes both.
* Keep it **additive** (SC-2/SC-4 freeze rule).

### 7.8 Backbone identity / X3D (rec. 8)
* Benchmark SlowFast vs X3D fallback on the same fixtures: per-window latency (p50/p95) on the 3060, plus G-02/G-03.
* Also fix the F-29 category text so the capability API stops claiming an engine that is not loaded `[V, runtime-map F-29]`.

### 7.9 Quantization measurement (rec. 9)
* Only after 7.1 exists: export the violence model through the existing ORT path, try INT8/FP16, measure **recall and FPs/hour** (not just latency). Prereq: an isolated venv (shared venv is read-only) `[V, campaign environment rules]`.

### 7.10 Person-gate (rec. 10)
* Measure the fraction of windows with zero person tracks (F-10) and the recall cost of skipping them; require the person detector's own misses to be quantified first (F-10 is "partial - ByteTrack path unmeasured" `[V]`).

---

## 8. Non-comparability ledger (read before quoting any number)

Every headline number in section 2-5 is **not** an AI Sentinel result.

| Published number | Their setting | Why it cannot be ours |
|---|---|---|
| RWF-2000 87.25 % (Flow Gated Network) `[V, arXiv 1911.05913]` | 2000 curated 5 s surveillance clips, **clip-level**, uses optical flow, videos now withdrawn | our input is a 32-frame window at a stride; our classes are "violence vs not" over a live stream, not balanced 5 s clips; the corpus is not distributable |
| RWF-2000 95.25 % / UCF-Crime 83.25 % (Short-Window Sliding Learning 2025) `[V]` | 1-2 s clips labelled by an **LLM auto-captioner** | training-time labels are machine-generated; this is a training recipe, not an independently-labelled benchmark |
| RWF-2000 0.88 (Vi-SAFE 2025) `[V]` | YOLOv8 person-region + TSN, cluster/session split unknown | unknown split discipline -> possible same-scene inflation `[V, arXiv 2606.29506]` |
| Vandalism 94.33 % with SlowFast-R50 (2026) `[V]` | 614 self-collected clips, one domain | same-domain, custom corpus; no cross-domain number reported |
| Same-dataset AUC 0.704 vs cross-dataset 0.499 `[V, arXiv 2606.29506]` | unsupervised VAD on pedestrian corpora | this is the **warning**, not a target: it tells us what happens if we trust same-scene evaluation |
| ~31,931 false alarms/hour `[V, arXiv 2606.29506]` | naive VAD operating point | an order-of-magnitude warning about uncalibrated alarm load, not a prediction for our system |
| X3D "4.8x fewer multiply-adds, 5.5x fewer parameters at similar accuracy" `[V, arXiv 2004.04730]` | Kinetics/Charades/AVA | says nothing about our checkpoint (whose architecture is only described as "SlowFast-style" and whose lineage is unknown `[V, runtime-map 3.6]`) |
| ~70 % cross-dataset fight accuracy `[V, arXiv 2111.08370]` | five fight corpora, still images | strongest available hint that cross-domain recall will be far below in-domain recall |

Two structural non-comparabilities to state in any WT-19 report:

1. **Metric mismatch**: the literature almost always reports clip accuracy or frame AUC; `G-02` is "0 confirmed alerts" and `G-04` is glass-to-alert latency. Those are different questions.
2. **Hardware/stack mismatch**: our violence model runs on `cuda:0` inside a `spawn`ed per-camera process (F-06) sharing the GPU with ONNX sessions that the registered run actually placed on CPU `[V, runtime-map 3.2]`; throughput claims from papers using single-model, single-stream setups do not transfer.

---

## 9. Gaps and open questions

1. **No fixtures exist.** Everything in section 6 is blocked on section 7.1. This is the single biggest gap in the whole workstream.
2. **No local measurement of the violence model at all** (latency, throughput, recall, FPR) - `PLAN.md` G-02/G-03/G-04 all read `unmeasured` `[V]`.
3. **Onset is undefined** in our data model (F-08 validity is clock-integrity, not event localisation; SC-4 has no onset field) `[V]`.
4. **Calibration artifact absent** -> the threshold 0.45 is not a probability and cannot be swept as one `[V, F-40]`.
5. **Architecture identity is uncertain**: `detection_categories.py` says X3D, the runtime loads SlowFast `[V, F-29]`; the checkpoint's training lineage is unknown `[V, runtime-map 3.6]`. Any "improve the model" claim must first pin what the model is.
6. **No lawful public corpus matches G-02's classes** (section 3.3). This is a rights constraint, not a search failure.
7. **Quantization/pruning recall effect on violence detection is unmeasured in the literature we could reach** (section 5.1) - do not promise it.
8. **Search-tool limitation**: `web_search` was unusable in this environment and general web search engines were blocked/poisoned, so grey-literature (vendor benchmarks, deployments) is under-covered. Anything vendor-specific is `[?]`.
9. **Audio is out of scope in practice**: the audio path is disabled (`audio.enabled: false`, F-31) and CCTV audio is usually absent/mixed; multimodal results like XD-Violence's do not transfer without an audio pipeline.
10. **RWF-2000-based tooling** (`tools/evaluate_rwf2000_subset.py`, `build_rwf2000_manifest.py`, `backend/datasets/*`) can no longer produce acceptance evidence; decide whether it is migrated to a licence-clean corpus or retired.

---

## 10. Engineer hand-off

### 10.1 For WT-19 (violence improvements)

1. **Do 7.1 first.** No model/config change can be justified before a baseline exists; and the baseline must report FPs per camera-hour, TTD p50/p95, and window-valid rate - not a single accuracy.
2. **Freeze the threshold while comparing** changes (declared retunes only), and record stride/window explicitly - the committed YAML (8) and the registered run (16) disagree `[V]`.
3. **Implement rec. 7 (onset instrumentation) early** - it is small, additive, and it makes G-04 measurable in the same pass as 7.1.
4. **Do rec. 2 (calibration) early** - F-40's consumer already exists; the work is fitting and committing an artifact, plus an ECE report. It converts 0.45 from a magic number into a decision.
5. **Prefer rec. 3+4+5 before any training.** They are config/decisions-layer changes with no new labelled data requirement, and 5 directly targets G-02.
6. **Only then consider rec. 6a (TTA)**, and only fine-tune against a session-held-out fixture, with the orchestrator's weight-backup rule.
7. **Report the negative control** (4.5 item 4) in every result - it is cheap and it catches harness bugs that masquerade as model changes.

### 10.2 For WT-12

* The fixture harness (7.1) is shared infrastructure: it needs an owner, a storage location for footage **outside git**, and a documented invocation. Until then WT-12's acceptance tables cannot be filled for G-02/G-03/G-04.
* `bench/calibrate.py` (F-47) is the natural integration point for the ECE/temperature report; keep it inside `bench/**` so S-20 ownership stays clean `[V, ownership-map]`.
* Payload changes for onset (rec. 7) touch SC-2 (`inference_process` result schema) and SC-4 (alert payload + frontend validator) - these require a single integration owner per the ownership map `[V]`.

### 10.3 Cross-slice ownership warnings (from the ownership map)

| Change | Slices involved | Freeze rule |
|---|---|---|
| Window/stride semantics | S-02 (violence path) + S-05 (decision/calibration) + config/thresholds.toml (SC-5) | threshold file is a cross-slice contract |
| Onset fields in payloads | S-01 (worker/IPC) + S-07 (evidence) + S-11/S-12 (UI consumers) | SC-2/SC-4 additive only |
| Person-gate | S-04 (tracking) + S-02 + `api.py` (SC-1) | one owner at a time on SC-1 |
| X3D adoption | S-02 + S-17 (F-29 wording) | - |
| Fine-tuning | S-21 (training tooling) + weights governance | orchestrated |

---

## 11. Source ledger (everything cited here, with the check performed)

All entries below were fetched on **2026-09-29** by the mechanisms in 0.2. "arXiv" entries were read back from the arXiv API (title + date + authors); "DOI" entries were read back from Crossref or OpenAlex; "URL" entries were fetched directly.

### 11.1 Papers (methods, benchmarks, protocols, deployment)

| Ref | Title (as read back) | ID / DOI | Date | Check |
|---|---|---|---|---|
| Simonyan & Zisserman | Two-Stream Convolutional Networks for Action Recognition in Videos | arXiv 1406.2199 | 2014-06-09 | `[V]` |
| Carreira & Zisserman | Quo Vadis, Action Recognition? A New Model and the Kinetics Dataset (I3D) | arXiv 1705.07750 | 2017-05-22 | `[V]` |
| Wang et al. | Temporal Segment Networks: Towards Good Practices for Deep Action Recognition | arXiv 1608.00859 | 2016-08-02 | `[V]` |
| Lin et al. | TSM: Temporal Shift Module for Efficient Video Understanding | arXiv 1811.08383 | 2018-11-20 | `[V]` |
| Feichtenhofer et al. | SlowFast Networks for Video Recognition | arXiv 1812.03982v3 | 2018-12-10 | `[V]` |
| Feichtenhofer | X3D: Expanding Architectures for Efficient Video Recognition | arXiv 2004.04730 | 2020-04-09 | `[V]` |
| Bertasius et al. | Is Space-Time Attention All You Need for Video Understanding? (TimeSformer) | arXiv 2102.05095 | 2021-02-09 | `[V]` |
| Arnab et al. | ViViT: A Video Vision Transformer | arXiv 2103.15691 | 2021-03-29 | `[V]` |
| Tong et al. | VideoMAE: Masked Autoencoders are Data-Efficient Learners for Self-Supervised Video Pre-Training | arXiv 2203.12602v3 | 2022-03-23 | `[V]` |
| Wang et al. | VideoMAE V2: Scaling Video Masked Autoencoders with Dual Masking | arXiv 2303.16727v2 | 2023-03-29 | `[V]` |
| Zhang et al. | ActionFormer: Localizing Moments of Actions with Transformers | arXiv 2202.07925 | 2022-02-16 | `[V]` |
| Shou et al. | Online Detection of Action Start in Untrimmed, Streaming Videos (ODAS) | arXiv 1802.06822v3 | 2018-02-19 | `[V]` |
| Shou et al. | StartNet: Online Detection of Action Start in Untrimmed Videos | arXiv 1903.09868 | 2019-03-23 | `[V]` |
| Guo et al. | On Calibration of Modern Neural Networks | arXiv 1706.04599 | 2017-06-14 | `[V]` |
| Cheng, Cai, Li | RWF-2000: An Open Large Scale Video Database for Violence Detection | arXiv 1911.05913v3 / DOI 10.1109/ICPR48806.2021.9412502 | 2019-11-14 / ICPR 2021 | `[V]` |
| Sultani, Chen, Shah | Real-world Anomaly Detection in Surveillance Videos | arXiv 1801.04264 / DOI 10.1109/CVPR.2018.00678 | 2018-01-12 | `[V]` |
| Wu et al. | Not only Look, but also Listen: Learning Multimodal Violence Detection under Weak Supervision (XD-Violence) | arXiv 2007.04687 / DOI 10.1007/978-3-030-58577-8_20 | 2020-07-09 | `[V]` |
| Rabiee et al. | Violent flows: Real-time detection of violent crowd behavior | DOI 10.1109/CVPRW.2012.6239348 | 2012 | `[V, metadata]` |
| Serrano Gracia et al. | Fast Fight Detection | DOI 10.1371/journal.pone.0120448 (CC BY 4.0) | 2015 | `[V]` |
| Bianculli et al. | A dataset for automatic violence detection in videos (AIRTLab) | DOI 10.1016/j.dib.2020.106587 (CC BY 4.0) | 2020 | `[V, metadata]` |
| Demarty et al. | VSD, a public dataset for the detection of violent scenes in movies... / VSD2014 | DOI 10.1007/s11042-014-1984-4 ; 10.1109/CBMI.2015.7153604 | 2014 / 2015 | `[V, metadata]` |
| Trabelsi et al. | Vision-based Fight Detection from Surveillance Cameras | arXiv 2002.04355 | 2020-02-11 | `[V]` |
| (authors not read) | Detection of Fights in Videos: A Comparison Study of Anomaly Detection and Action Recognition | arXiv 2205.11394 | 2022-05-23 | `[V]` |
| Singh et al. | Video Vision Transformers for Violence Detection (ViViD-class, ViViT-based) | arXiv 2209.03561v2 | 2022-09-08 | `[V]` |
| (authors not read) | Fight Detection from Still Images in the Wild | arXiv 2111.08370v2 | 2021-11-16 | `[V]` |
| (authors not read) | Weakly-Supervised Video Anomaly Detection with Robust Temporal Feature Magnitude Learning (RTFM) | DOI 10.1109/ICCV48922.2021.00493 | 2021 | `[V, metadata]` |
| (authors not read) | VadCLIP: Adapting Vision-Language Models for Weakly Supervised Video Anomaly Detection | DOI 10.1609/aaai.v38i6.28423 | 2024 | `[V, metadata]` |
| (authors not read) | CrimeNet: Neural Structured Learning using Vision Transformer for violence detection | DOI 10.1016/j.neunet.2023.01.048 | 2023 | `[V, metadata]` |
| (authors not read) | Video Test-Time Adaptation for Action Recognition | DOI 10.1109/CVPR52729.2023.02198 | 2023 | `[V]` (abstract read) |
| (authors not read) | ST2ST: Self-Supervised Test-time Adaptation for Video Action Recognition | DOI 10.1109/CVPRW63382.2024.00112 | 2024 | `[V, metadata]` |
| (authors not read) | Short-Window Sliding Learning for Real-Time Violence Detection via LLM-based Auto-Labeling | arXiv 2511.10866v2 | 2025-11-14 | `[V]` |
| (authors not read) | Vi-SAFE: A Spatial-Temporal Framework for Efficient Violence Detection in Public Surveillance | arXiv 2509.13210 | 2025-09-16 | `[V]` |
| (authors not read) | Benchmark AUC Is Not Deployable Reliability: A Cross-Dataset Audit of Off-the-Shelf Features for Surveillance VAD | arXiv 2606.29506 | 2026-06-28 | `[V]` |
| (authors not read) | A Multi-Task Deep Learning Framework for Real-Time Intelligent Video Surveillance with Temporal Event Validation | arXiv 2607.03131 | 2026-07-03 | `[V]` |
| (authors not read) | What Do Interaction Representations Actually Measure? Pre-Event Separability in Weakly-Supervised Violence Detection | arXiv 2608.27879 | 2026-08-28 | `[V]` |
| (authors not read) | AViS-Mamba: Adaptive Visual Steering of Audio State-Space Dynamics for Violence Detection | arXiv 2604.03329v2 | 2026-04-02 | `[V]` |
| (authors not read) | City Sentinel: A Unified AI-Based Smart Surveillance Framework... | arXiv 2608.08887 | 2026-08-09 | `[V]` |
| (authors not read) | Human Activity Recognition Method for Moderate Violence Detection | arXiv 2605.02659 | 2026-05-04 | `[V]` |
| (authors not read) | CoDAT: Collaborative Dual-Attention Transformer with Low-Cost Temporal Modeling for Efficient Edge Action Recognition | arXiv 2608.06691 | 2026-08-07 | `[V]` |
| (authors not read) | A Lightweight Dual-Branch System for Weakly-Supervised VAD on Consumer Edge Devices (RuleVAD) | arXiv 2410.21991v7 | 2024-10-29 | `[V]` |
| (authors not read) | Real-Time Human Action Recognition on Embedded Platforms | arXiv 2409.05662v2 | 2024-09-09 | `[V]` |
| (authors not read) | FPGA-QHAR: Throughput-Optimized for Quantized Human Action Recognition on The Edge | arXiv 2311.03390 | 2023-11-04 | `[V, metadata]` |
| (authors not read) | Temporal Action Detection Model Compression by Progressive Block Drop | arXiv 2503.16916 | 2025-03-21 | `[V, metadata]` |
| (authors not read) | Energy-aware deep learning for real-time video analysis through pruning, quantization, and hardware optimization | DOI 10.1007/s11554-025-01703-0 | 2025 | `[V, metadata]` |
| (authors not read) | Literature Review of Deep-Learning-Based Detection of Violence in Video | DOI 10.3390/s24124016 (CC BY) | 2024 | `[V]` (abstract) |
| (authors not read) | Revisiting vision-based violence detection in videos: A critical analysis | DOI 10.1016/j.neucom.2024.128113 | 2024 | `[V, metadata]` |
| (authors not read) | Video Anomaly Detection in 10 Years: A Survey and Outlook | arXiv 2405.19387 | 2024-05-29 | `[V, metadata]` |
| (authors not read) | Deep Learning for Video Anomaly Detection: A Review | arXiv 2409.05383 | 2024-09-09 | `[V, metadata]` |
| (authors not read) | The Evolution of Video Anomaly Detection: A Unified Framework from DNN to MLLM | arXiv 2507.21649 | 2025-07-29 | `[V, metadata]` |

### 11.2 Dataset pages / licences

| Artefact | URL | What was verified |
|---|---|---|
| RWF-2000 repo | `github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection` (raw README) | withdrawal notice, terms (no redistribute/modify; no commercial), 2000 clips/300k frames/5 s @ 30 fps, duplicate removal `[V]` |
| KTH Actions | `https://www.csc.kth.se/cvap/actions/` | 2391 sequences, 25 subjects, 6 actions, 25 fps, 160x120, "publicly available for non-commercial use", citation request `[V]` |
| Kinetics licence | official DeepMind page via WayBack snapshot `web.archive.org/web/20220323094948/https://deepmind.com/research/open-source/kinetics` | "licensed by Google Inc. under a Creative Commons Attribution 4.0 International License" `[V]` |
| Kinetics distribution + leakage warning | `raw.githubusercontent.com/cvdfoundation/kinetics-dataset/main/README.md` | 400/600/700 classes, >=400 clips/class, ~10 s; k400-val largely inside k700-train `[V]` |
| UCF101 | `https://www.crcv.ucf.edu/data/UCF101.php` | 13,320 videos / 101 classes; **no licence text** (only "© Copyright 2011 CRCV") `[V]` |
| UCF-Crime project page | `https://www.crcv.ucf.edu/projects/real-world/` | page live; **no licence text** `[V]` |
| ActivityNet | `http://activity-net.org/download.html`; `github.com/activitynet/ActivityNet` | release 1.3 counts; repo MIT (tools) `[V]`; annotation licence not stated `[?]` |
| XD-Violence | `https://roc-ng.github.io/XD-Violence/` | 4754 videos / 217 h / 6 categories / audio; cloud-drive distribution; **no licence text** `[V]` |
| Hockey + Movies originals | `visilab.etsii.uclm.es/personas/oscar/FightDetection/index.html` (from the CC BY PLoS paper's Data Availability) | host **404** `[V]`; composition (1000 clips; 200 movie clips) read from the PLoS paper `[V]` |
| VSD licence | `https://www.interdigital.com/data_sets/violent-scenes-dataset` | research-only, non-commercial, modification for research only; 86 web videos CC BY 3.0; movie scenes are references `[V]` |
| Violent Flows dataset host | `http://www.openu.ac.il/home/hassner/data/violentflows/` | **403** `[V]` |

### 11.3 Not verified here (do not quote as fact)

Violent Flows dataset composition/terms; AIRTLab dataset composition and its own DOI; UBI-Fight and NTU-CCTV-Fight availability; SCVD terms; UCF-Crime official download terms; ActivityNet annotation licence; any Kaggle/other mirror of withdrawn corpora; any vendor throughput claim.

---

## 12. Validation performed for this document

* **No runtime measurement was performed** - no camera exists, no fixtures exist, and this task is research-only. Nothing here claims a measured AI Sentinel result.
* Mechanism validation: the arXiv API, OpenAlex, Crossref, direct fetch and the WayBack availability API were each exercised and returned data; `web_search` and general search engines failed (0.2).
* Cross-checking: every arXiv ID was re-fetched and its title compared to the claim made about it; four wrong remembered IDs were corrected and are documented in 0.3.
* Licence claims are traced to the artefact that states them (section 11.2); where a page contained no licence text (`UCF101`, `UCF-Crime`, `XD-Violence`) the document says so rather than inferring a licence.
* `docs:check` for this worktree is reported in the hand-off message, not asserted here.
