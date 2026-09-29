---
authority: scoped
non_authoritative: true
---

# WT-05 — Open-source competitors and reusable architecture for AI Sentinel

**Status:** scoped campaign research artifact (non-authoritative). `docs/CURRENT.md` (status) and `docs/DESIGN.md` (design system) remain the only status/design authorities; `docs/PLAN.md` holds pending work and `docs/ISSUES.md` holds defects. This document must never become a competing status or design document.
**Worktree:** `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-05` · **branch:** `codex/sentinel-05-oss` · **baseline:** `e86d34b5d16abcc133ad3470c8d135d00b2423d4`
**Access date for every URL below:** 2026-09-29 (unless a different date is stated).
**Runtime code changed by this ticket:** none.

---

## 0. Purpose, method, and how to read this

### 0.1 Question
Which **maintained** open-source surveillance / NVR / VMS / edge-AI / incident systems contain architecture or code that AI Sentinel (Windows-native, RTX 3060 12 GB, Python backend + Next.js frontend) can **integrate**, **adapt**, or must **reject**, and why?

### 0.2 Method
1. Candidate discovery: GitHub REST search + direct repository metadata (stars, `pushed_at`, SPDX license, archived flag). Stars were treated as a *signal only*; every verdict rests on LICENSE text, README/official docs, or code read from a shallow clone.
2. License verification: raw `LICENSE*` files fetched from the repository's default branch (or GitLab equivalent). Code, model weights, and bundled data are assessed **separately** (a permissive code license does not cover weights).
3. Windows verification: the project's own installation/support documentation, quoted verbatim, with the URL. Projects that only support Linux-in-Docker are marked as such; "runs on Windows via WSL2" is distinguished from "native Windows".
4. Code inspection: shallow clones of `AlexxIT/go2rtc`, `FoundationVision/ByteTrack`, `roboflow/supervision` (untracked `clones/`, not committed). Inspected SHAs are recorded in §8.3 with file:line citations.
5. Claims that could not be verified in this session are explicitly labelled **[UNVERIFIED]**.

### 0.3 Evidence legend
- `[DOC]` official documentation/README statement (quoted, URL + access date).
- `[LIC]` LICENSE file text (URL).
- `[CODE]` inspected source at a recorded SHA (`path:line`).
- `[META]` repository metadata (stars / last push / release tag) from the GitHub API.
- `[UNVERIFIED]` believed but not verified here — never to be treated as fact.

### 0.4 Non-goals
No benchmarking was possible for third-party stack alternatives (no camera device; the campaign environment forbids installing their runtimes: Frigate/Viseron/Savant all require Linux/Docker or WSL2, which is out of scope for this ticket's Windows-native target and would not be a fair measurement anyway). No code from any candidate was copied into the repository.

---

## 1. Environment constraints that drive every verdict

| Constraint | Consequence for this document |
|---|---|
| Native Windows 11 x64 target; no Docker/Linux runtime in the product | Frigate, Viseron, Savant, ZoneMinder, AgentDVR(service), Kerberos are Linux/container-first → usable as **pattern sources**, not as dependencies |
| RTX 3060 12 GB = *GeForce*, WDDM | DeepStream-on-WSL2 explicitly supports only GeForce/Quadro in WDDM mode (Tesla/datacenter excluded) → technically viable but adds a Linux runtime + documented throughput penalty (§3.2) |
| 16 GB RAM, ~2.6 GB free during the campaign; ~45 GB disk | Any candidate whose runtime is a container stack with its own CUDA stack is disqualified as a *runtime* dependency |
| No camera device | go2rtc/ffmpeg "live camera" paths can only be exercised with file/synthetic sources |
| Python 3.12 project venv; `python` is a broken Store stub | Vendored Python trackers must be import-safe without build steps (this matters for ByteTrack's C extensions, §3.2.4) |
| Models are untracked multi-MB ONNX (`person_yolo.onnx`, `weapon_yolo.onnx`) | Reusing a candidate's model weights is a licensing question, not just a technical one (§5) |

---

## 2. Candidate catalog

Legend — **Win:** native Windows support evidence; **Verdict:** `INTEGRATE` (use as a dependency/component), `ADAPT` (copy the pattern, not the code), `REJECT` (do not use), `TOOLING` (offline/dev-time only).

### 2.1 NVR / VMS / streaming

| ID | Project | Version / last push | License (code) | Win | Verdict |
|---|---|---|---|---|---|
| OSS-NVR-01 | [Frigate](https://github.com/blakeblackshear/frigate) | v0.18.0 (2026-09-12); pushed 2026-09-28; 36.2k★ | MIT `[LIC]` | Not officially supported; WSL/VirtualBox only `[DOC]` | **ADAPT** |
| OSS-NVR-02 | [Viseron](https://github.com/roflcoopter/viseron) | v3.7.0 (2026-09-17); 3.6k★ | MIT `[LIC]` | Docker-first `[DOC]` | **ADAPT** (component model) |
| OSS-NVR-03 | [go2rtc](https://github.com/AlexxIT/go2rtc) | v1.9.14 (2026-01-19); pushed 2026-09-06; 14.3k★ | MIT `[LIC]` | **Yes — Windows 10+ 32/64/ARM64 zips** `[DOC]` | **INTEGRATE** |
| OSS-NVR-04 | [ZoneMinder](https://github.com/ZoneMinder/zoneminder) | active (2026-09-28); 5.9k★ | GPL-2.0 `[LIC]` | Docs list "Windows 10+ using WSL" `[DOC]` | **ADAPT** (pattern) |
| OSS-NVR-05 | [Motion](https://github.com/Motion-Project/motion) / [motionEye](https://github.com/motioneye-project/motioneye) | motion pushed 2026-09-14; motionEye pushed 2026-09-28 (953 open issues) | GPL-3.0 `[LIC]` | Linux/APT+systemd install path `[DOC]` | **REJECT** |
| OSS-NVR-06 | [Kerberos Agent](https://github.com/kerberos-io/agent) | pushed 2026-09-27; 1.1k★ | MIT `[LIC]` | container/binary deployment, OS not asserted `[DOC]` | **ADAPT** (config model) |
| OSS-NVR-07 | [SentryShot](https://github.com/SentryShot/sentryshot) | Cargo workspace 0.3.11, Rust 1.85/edition 2024; pushed 2026-04-27; 363★ | GPL-2.0+ `[LIC]` `[CODE]` | no Windows claim found | **ADAPT** (plugin boundaries) |
| OSS-NVR-08 | [Scrypted](https://github.com/koush/scrypted) | pushed 2026-09-28; 6.0k★ | **per-directory, mixed** (`LICENSE.md`: "See individual project directories for licensing… Some plugins may have dependencies that require GPL compliance") `[LIC]` | Node/TS, cross-platform core | **REJECT** (license indeterminacy) |
| OSS-NVR-09 | [Shinobi](https://gitlab.com/Shinobi-Systems/Shinobi) | GitLab active 2026-09-26, 722★ (GitHub mirrors frozen 2020) | custom "SHINOBI OPEN SOURCE SOFTWARE LICENSE AGREEMENT v1, © 2023 Shinobi Systems" `[LIC]` | Node.js; no Windows claim found | **REJECT** |
| OSS-NVR-10 | [AgentDVR (iSpy)](https://www.ispyconnect.com/) | n/a | **closed source freeware** — no public repo; only `ispysoftware/AgentDVR-Plugins` (Apache-2.0); site: "Free for personal use" + paid licensing `[DOC]` `[META]` | Windows-first (its niche) | **REJECT** (no source; see CVE note §3.1.3) |

### 2.2 Edge-AI / video-analytics pipelines

| ID | Project | Version / last push | License | Win | Verdict |
|---|---|---|---|---|---|
| OSS-EDGE-01 | [NVIDIA DeepStream](https://docs.nvidia.com/metropolis/deepstream/dev-guide/) | DS 9.1 docs (Ubuntu 24.04 / CUDA 13.2 / TRT 10.16.0.72) | SDK under NVIDIA EULA (reference apps separate) | **WSL2 documented**, constraints `[DOC]` | **REJECT** for runtime; keep as future option |
| OSS-EDGE-02 | [Savant](https://github.com/insight-platform/Savant) | v0.6.0 (2025-12-08); 856★ | Apache-2.0 `[LIC]` | Linux/Docker + DeepStream `[DOC]` | **REJECT** (inherits DeepStream) |
| OSS-EDGE-03 | [Ultralytics](https://github.com/ultralytics/ultralytics) | v8.4.165 (2026-09-28); 62k★ | **AGPL-3.0** or paid Enterprise License `[LIC]` `[DOC]` | pip, Windows OK | **REJECT as dependency** (license), see §5.3 |
| OSS-EDGE-04 | [supervision](https://github.com/roboflow/supervision) | 0.30.5 (2026-09-22); 51k★ | MIT `[LIC]` | pure Python | **ADAPT** |
| OSS-EDGE-05 | [ByteTrack](https://github.com/FoundationVision/ByteTrack) | pushed 2024-06-19; 6.7k★ | MIT `[LIC]` | pure Python + 2 C-extras `[CODE]` | **INTEGRATE (vendored, trimmed)** |
| OSS-EDGE-06 | [BoT-SORT](https://github.com/NirAharon/BoT-SORT) | pushed 2024-08-08; 1.6k★ | MIT `[LIC]` | pure Python + C-extras | **ADAPT** (fallback) |
| OSS-EDGE-07 | [BoxMOT](https://github.com/mikel-brostrom/boxmot) | pushed 2026-09-18; 8.3k★ | **AGPL-3.0** `[LIC]` | pip | **REJECT** (license) |
| OSS-EDGE-08 | [Norfair](https://github.com/tryolabs/norfair) | pushed 2025-04-30; 2.7k★ | BSD-3-Clause `[LIC]` | pip | **REJECT** (redundant with ByteTrack) |
| OSS-EDGE-09 | [SAM 2](https://github.com/facebookresearch/sam2) | pushed 2026-05-30; 19.9k★ | Apache-2.0 **incl. checkpoints** `[LIC]` `[DOC]` | README: "strongly recommended to use WSL" on Windows `[DOC]` | **TOOLING** (offline labelling only) |
| OSS-EDGE-10 | [OpenCV Zoo](https://github.com/opencv/opencv_zoo) / [PINTO model zoo](https://github.com/PINTO0309/PINTO_model_zoo) | 2026-05-28 / 2026-09-05 | Apache-2.0 / MIT (repo; **upstream model licenses vary**) `[LIC]` | ONNX, cross-platform | **ADAPT** (model sourcing with per-model license check) |
| OSS-EDGE-11 | [onnxruntime](https://github.com/microsoft/onnxruntime) | v1.30.0 (2026-09-10) | MIT `[LIC]` | first-class Windows | **INTEGRATE** (already in use) |
| OSS-EDGE-12 | [NVIDIA VideoProcessingFramework (PyNvCodec)](https://github.com/NVIDIA/VideoProcessingFramework) | **ARCHIVED**, last push 2024-06-10; 1.4k★ | Apache-2.0 `[LIC]` | Windows build docs existed | **REJECT** (archived) |
| OSS-EDGE-13 | [FFmpeg](https://github.com/FFmpeg/FFmpeg) | mirror pushed 2026-09-28 | LGPL/GPL depending on build flags `[LIC]` | Windows builds available | **INTEGRATE** (already in use at `F-21`) |
| OSS-EDGE-14 | [VidGear](https://github.com/abhitronix/vidgear) | pushed 2026-05-18; 3.7k★ | Apache-2.0 `[LIC]` | pip | **REJECT** (redundant with our ffmpeg/OpenCV paths) |

### 2.3 Violence / weapon detection projects

GitHub repository search on 2026-09-29 (`violence detection deep learning`, `weapon gun detection yolo`) returned 236 resp. 34 repositories. The population is dominated by student/coursework repositories:

| Observation | Evidence |
|---|---|
| Highest-starred violence repo has **no license** (liorsidi/violence-detection-deep-learning-cnnlstm, 146★, last push 2020-08-13) | `[META]` GitHub search |
| Best-licensed violence repo is Apache-2.0 but stale (hasnainnaeem/Violence-Detection-in-Videos, 102★, last push 2022-03-28, Keras/TF, reported 98.5 % video accuracy on a private split) | `[META]` |
| Every weapon-detection repository found is ≤ 15★ and 9/10 declare **no license** | `[META]` |
| No candidate ships a documented, citable evaluation protocol, dataset card, or calibration artifact | `[META]` READMEs |

**Verdict: REJECT all of them as integration sources.** Nothing in this population is a credible substitute for, or improvement on, the project's own weapon engine (`F-09`, `S-03`) or the SlowFast violence path (`F-07`, `S-02`). They are at best *dataset pointers* for `S-21`, and even then the datasets, not the code, are the artifact — each dataset needs its own license review (see §5.4).

### 2.4 Incident / evidence / notification tooling

| ID | Project | What it is | License | Verdict |
|---|---|---|---|---|
| OSS-INC-01 | [zmeventnotification](https://github.com/ZoneMinder/zmeventnotification) (legacy) → [zmeventnotificationNg](https://github.com/pliablepixels/zmeventnotificationNg) | "Event Notification Server … offers real time notifications, support for push notifications as well as Machine Learning powered recognition … detection of 80 types of objects … face recognition … deep license plate recognition" `[DOC]` | see §5 | **ADAPT** (split: recorder vs. notification/ML consumer) |
| OSS-INC-02 | Frigate's retention model (continuous / motion / alert / detection + `pre_capture` / `post_capture`) | recording policy configuration `[DOC]` | MIT | **ADAPT** (evidence writer config, `S-07`) |
| OSS-INC-03 | Shodan-style audit/ledger tooling (SAM 2 demo, etc.) | — | — | not applicable — no open-source incident ledger matched `SC-8`'s chain-of-custody design |

---

## 3. Deep dives

### 3.1 NVR/VMS that are architecturally relevant but not Windows-native

#### 3.1.1 Frigate (OSS-NVR-01) — the reference architecture for a single-box NVR
- **License:** MIT, "Copyright (c) 2026 Frigate, Inc. (Frigate™)" `[LIC]` — permissive, but note the trademark; the *Frigate+* model service is commercial and out of scope.
- **Windows:** "Windows is not officially supported, but some users have had success getting it to run under WSL or Virtualbox." (docs.frigate.video/frigate/installation) `[DOC]`. Its hardware page additionally notes that pre-installed Windows machines require installing Linux `[DOC]`.
- **Pipeline model:** "At a high level, there are five processing steps that could be applied to a camera feed… all feeds first need to be acquired. Depending on the data source, it may be as simple as using FFmpeg to connect to an RTSP source via TCP or something more involved like connecting to an Apple Homekit camera using go2rtc… the resolution may be downscaled and an image sampling frequency may be imposed… These frames will then be compared over time to detect movement areas… combined into motion regions and… analyzed by a machine learning model to detect known objects. Finally, the snapshot and recording retention config will decide what video clips and events should be saved." (docs.frigate.video/frigate/video_pipeline) `[DOC]`.
  - This is **structurally the same pipeline as AI Sentinel's** `F-04 → F-05 → F-11 → F-06/F-07/F-09 → F-14 → F-16/F-21`, which validates the existing decomposition rather than demanding a rewrite.
- **Streaming:** "Frigate uses go2rtc to provide its restream and MSE/WebRTC capabilities." and "You can access the go2rtc stream info at `/api/go2rtc/streams`" (docs.frigate.video/configuration/restream) `[DOC]`. Latency tip worth stealing: birdseye idle heartbeat (`idle_heartbeat_fps`) "makes Frigate periodically push the last frame even when no motion is detected, reducing initial connection latency" `[DOC]` — directly applicable to our disconnected WebRTC path `F-37`/`S-09`.
- **Detectors:** Coral EdgeTPU, OpenVINO, ONNX, TensorRT, ROCm, Apple Silicon; the hardware page explicitly warns the Coral "is no longer recommended for new Frigate installations" `[DOC]`. Relevant: our ONNX runtime path (`F-03`/`S-03`) is in line with where the ecosystem moved.
- **Evidence/recording:** retention is tiered — `continuous`, `motion`, `alerts`, `detections`, each with `days` and a `mode` (`all`/`motion`), plus per-class `pre_capture`/`post_capture` seconds (docs.frigate.video/configuration/record) `[DOC]`. AI Sentinel currently hard-codes an evidence clip on alert (`F-21`, `SC-8`); Frigate's tiered-retention vocabulary is a ready-made schema for a future retention config without touching `SC-8` paths.
- **Why not integrate:** container/Linux runtime, its own detector management, and its own API/UI — duplicating what AI Sentinel already has. **Adapt the models/patterns only.**

#### 3.1.2 go2rtc (OSS-NVR-03) — the one dependency that *does* fit Windows natively
- **License:** MIT, "Copyright (c) 2022 Alexey Khit" `[LIC]`.
- **Windows:** README lists a zero-dependency binary "for all OS (Windows, macOS, Linux, FreeBSD)" and release assets `go2rtc_win64.zip` (Windows 10+ 64-bit), `go2rtc_win32.zip`, `go2rtc_win_arm64.zip` `[DOC]`.
- **Relevance to `SC-10`:** AI Sentinel's committed `backend/api.py` imports an **untracked** `go2rtc_bridge` (`B-1`; `api.py:46-50,295-298`), and the orchestrator decision `SC-10` is "commit the modules, or make imports optional with an explicit disabled health state". go2rtc is the upstream project that this bridge would front, is MIT, ships a native Windows binary, and is the same streaming substrate Frigate uses `[DOC]`. That makes "go2rtc child process + explicit disabled health state" the lowest-risk realization of `SC-10` for the transport slice (`S-09`, `F-37`).
- **Reusable internals** (clone `AlexxIT/go2rtc@c245815`):
  - `pkg/core/core.go:47-76` — `Producer`/`Consumer` interfaces with a `Mode` enum (`ModeActiveProducer`, `ModePassiveConsumer`, …) `[CODE]`. Clean vocabulary for our capture/inference/render roles.
  - `pkg/core/track.go:22-32` — a `Receiver` fan-outs each packet to `childs` by calling their `Input`; there is no per-child unbounded buffering in the hot path `[CODE]`.
  - `pkg/core/readbuffer.go:8-25` — explicit buffer semantics: positive `BufferSize` = buffering with seek, `BufferDisable = 0` = pass-through, `BufferDrainAndClear = -1` = drop everything buffered `[CODE]`. This "declare the drop policy as a first-class constant" idea is exactly what our queue-depth findings (`R-1`/`R-2`, queue sizes 3/30/360/600) lack: a named, testable drop policy per queue.
  - `internal/streams/README.md` — "Preload stream … useful for cameras that take a long time to start up" `[CODE]`; the same idea as Frigate's idle heartbeat, and applicable to our file-loop/demo sources (`F-20`, `F-39`).
- **Why not vendor the code:** it is Go. The right integration is "run the binary, talk HTTP", with a health probe (`/api/streams`) and a 503-when-down path matching the existing `F-37` contract.
- **[UNVERIFIED]:** process RSS/CPU of `go2rtc_win64` under our file-source workload; no measurement was run in this ticket.

#### 3.1.3 ZoneMinder / Motion / motionEye / Kerberos / SentryShot / Scrypted / Shinobi / AgentDVR
- **ZoneMinder (GPL-2.0, active)** documents an installation route "Windows 10+ using WSL" (zoneminder.readthedocs.io install guide nav) `[DOC]` — i.e. still not native. Its FAQ is dominated by Linux-specific concerns (SELinux) `[DOC]`. The value to us is the **event-server split** embodied by zmeventnotification / zmeventnotificationNg (§2.4), not the recorder.
- **Motion + motionEye (GPL-3.0):** motionEye's README install path is APT + `systemd` (`motioneye_init` "assumes either an APT- or RPM-based distribution with `systemd` as init system") `[DOC]`; 953 open issues `[META]`. GPL-3.0 plus a Linux-only core plus maintenance load ⇒ **REJECT**.
- **Kerberos Agent (MIT, active):** explicitly positioned as "an isolated and scalable video (surveillance) management agent … available as Open Source under the MIT License", deployable as "a binary or container", advertising "Low memory and CPU usage" and configuration via file + environment overrides `[DOC]`. No explicit Windows statement was found `[UNVERIFIED]`. The reusable idea is the **per-camera agent = config file + env overrides + factory modules** model, which maps onto our camera-source config (`F-03`) and per-camera worker (`F-06`).
- **SentryShot (GPL-2.0+):** a Rust workspace (`Cargo.toml`: version 0.3.11, edition 2024, rust-version 1.85) whose plugin crates are `auth_basic, auth_none, motion, mqtt, object_detection, object_detection_tflite, thumb_scale` `[CODE]`; the GitHub repo is a mirror of Codeberg and last moved 2026-04-27 `[META]`. The **plugin boundary for optional capabilities** is a good architecture reference for our optional-module policy (`SC-10`, `F-26`, `F-31`, `F-37`); the GPL license and Rust stack mean **no code reuse**.
- **Scrypted:** the root `LICENSE.md` is not a license at all — "See individual project directories for licensing, as it will vary throughout the repository. Some plugins may have dependencies that require GPL compliance." `[LIC]`. Reputable project, but **license indeterminacy is disqualifying** for anything we ship.
- **Shinobi:** the GitHub mirrors stopped in 2020; development is on GitLab (active 2026-09-26) `[META]`. Its license is a bespoke "SHINOBI OPEN SOURCE SOFTWARE LICENSE AGREEMENT" `[LIC]` — not an OSI license, so **REJECT**.
- **AgentDVR:** **closed source** (no source repository found via GitHub search; only the Apache-2.0 `ispysoftware/AgentDVR-Plugins` exists) and "Free for personal use" with paid licensing off the vendor site `[DOC]` `[META]`. It is nonetheless instructive as the *only* Windows-first product in the set — it demonstrates the Windows-native niche AI Sentinel occupies. Security note: the version pair CVE-2024-22515 (arbitrary file upload) / CVE-2024-22514 (RCE) affected AgentDVR 5.1.6.0 `[META]`; the existence of a *network-facing unauthenticated file-upload class* bug in a camera/NVR product is a reminder that our own `S-19` (25 of 42 routes never call `authorize()`) is the same class of exposure.

### 3.2 Edge-AI stacks

#### 3.2.1 DeepStream on WSL2 (OSS-EDGE-01) — viable on paper, expensive in practice
Official DeepStream documentation contains dedicated pages "DeepStream On WSL" and "FAQ for DeepStream On WSL", and the release notes state: "Performance in WSL is not at par with Ubuntu system. There is a known throughput issue while running multiple decode instances in WSL. So you may observe lower FPS compared to Ubuntu." `[DOC]`.
The WSL guide's constraints (quoted):
- "Windows 11 system with NVIDIA GPU: NOTE: Tesla/Datacenter GPUs are not supported for WSL. Only GeForce and Quadro GPUs in WDDM mode are supported."
- "Currently validated Driver Version and GPU info: GameReady Driver version 595.79 with GeForce RTX-3050 … This is the only driver you need to install on Windows. Do not install any Linux display driver inside WSL."
- "Currently validated WSL Version: wsl.2.7.3.0.x64"; "Install Ubuntu version required for Deepstream 9.1 $ wsl --install Ubuntu-24.04"; "This page describes the steps to run a Deepstream docker container inside WSL2."
`[DOC]` (docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_on_WSL2.html)
Implication: the RTX 3060 qualifies (GeForce + WDDM), but adopting DeepStream means shipping/recommending a Linux-in-WSL2 runtime with a **documented decode-throughput penalty** and a second CUDA/TensorRT stack. **REJECT for the Windows-native product**; keep as an opt-in "high-throughput mode" idea only if the project ever accepts a Linux runtime.

#### 3.2.2 Savant (OSS-EDGE-02) — DeepStream with a Python face
- Apache-2.0 `[LIC]`, built on DeepStream `[DOC]`; compatibility table in its README: production 0.5.x targets DeepStream 7.0 (verifiable on "dGPU (Turing, Volta, Ampere, Ada) and Jetson Orin"), development 0.6.x targets "a customized DeepStream 7.1 with TensorRT 10.9", adds Blackwell, drops Pascal, requires "X86 Driver 570.133.20+" `[DOC]`.
- Because it inherits DeepStream, it inherits §3.2.1. **REJECT**; the reusable idea is its *pipelines + adapters* framing (a graph of sources → inference → sinks with messaging adapters). **[UNVERIFIED]**: the ZeroMQ/Kafka/Redis adapter claims were not confirmed from the docs in this session.

#### 3.2.3 Ultralytics (OSS-EDGE-03) — a licensing exposure we already carry
- License: "AGPL-3.0 License … Ultralytics Enterprise License: For development and production use, this license enables seamless integration of Ultralytics software and AI models into business products" `[DOC]`; the LICENSE file is the AGPL-3.0 text `[LIC]`. The models are *also* covered by the same dual scheme (`[DOC]`: "integration of Ultralytics software and AI models").
- The baseline uses Ultralytics only as a **fallback** for person detection (`F-10`: "ONNX or `yolov8n.pt` (fallback)") and names it among the weapon engine's backends (`F-09`). If the product is ever distributed, shipping an AGPL dependency (even unused-by-default) is a legal question for the orchestrator, not an engineering one. Two mitigations are cheap: (a) remove the Ultralytics code path entirely in favour of the existing ONNX paths (`person_yolo.onnx`, `weapon_yolo.onnx`), or (b) purchase the Enterprise License. This is flagged, not decided (§7, F-4).

#### 3.2.4 Tracking: ByteTrack / BoT-SORT / BoxMOT / supervision
- **ByteTrack** (MIT) `[LIC]`: `yolox/tracker/byte_tracker.py:1-11` imports `numpy`, `collections.deque`, `os`, `copy`, **`torch` + `torch.nn.functional`** and the local `kalman_filter`/`matching`/`basetrack` modules `[CODE]`. `torch` appears **only on lines 6-7 and is never used** — a vendored port must drop those two lines (they would otherwise drag a 2 GB dependency into a code path that needs none). `matching.py:1-9` imports `cv2`, `numpy`, `scipy`, **`lap`** and **`cython_bbox`** `[CODE]` — both are C extensions, i.e. Windows wheels/build friction for `S-04`; the standard workaround is to replace `lap`/`cython_bbox` with `scipy.optimize.linear_sum_assignment` and an IoU implementation (as several ports do) rather than build them.
- Empirical note: ByteTrack's own repo has been quiet since 2024-06 `[META]`, and `person_count` in AI Sentinel is currently "len(tracks)" with the ByteTrack path explicitly *unmeasured* (`F-10`, `S-04`). Adopting ByteTrack is therefore a **measurement-and-correctness** task first, not a feature task — the verification experiment in §6.2 is the deliverable.
- **supervision** (MIT) `[LIC]`: at clone `roboflow/supervision@0159909` (`0.31.0.dev0`, `requires-python >= 3.10`, `numpy>=1.21.2` `[CODE]`) the package **no longer vendors a tracker**: `ByteTrack` appears only in `annotators/core.py`, `annotators/utils.py`, `detection/line_zone.py`, `detection/tools/smoother.py` and `__init__.py`, and there is no `tracker/` package `[CODE]`. What remains genuinely useful to us is `detection/line_zone.py:25 class LineZone` (line-crossing counting driven by track IDs) `[CODE]` — an *adaptable* pattern for defining what "person count" means (`F-10`, `S-04`) beyond "number of live tracks".
- **BoT-SORT** (MIT) `[LIC]`, quiet since 2024-08 `[META]`: same C-extension issue; keep as documented fallback.
- **BoxMOT** (AGPL-3.0) `[LIC]`: the most actively maintained tracker collection, and **unusable** in this codebase without AGPL obligations. **REJECT.**
- **Norfair** (BSD-3) `[LIC]`: permissive but adds a second tracker abstraction for no measured benefit over ByteTrack. **REJECT.**

#### 3.2.5 SAM 2 (OSS-EDGE-09)
Apache-2.0 **including model checkpoints** — the README's License section states "The SAM 2 model checkpoints, SAM 2 demo code (front-end and back-end), and SAM 2 training code are licensed under Apache 2.0" `[DOC]` (the Inter font used by the demo is SIL OFL 1.1). On Windows the README says "If you are installing on Windows, it's strongly recommended to use Windows Subsystem for Linux (WSL) with Ubuntu", and it needs a custom CUDA kernel compiled with `nvcc` (the install may print `Failed to build the SAM 2 CUDA extension`, which is tolerable but degrades post-processing) `[DOC]`. Verdict: **TOOLING only** — good for offline mask-assisted dataset preparation under `S-21`; unsuitable for the live runtime on this hardware.

#### 3.2.6 ONNX acceleration on Windows
- Repository facts we rely on: the project venv (Python 3.12) has `onnxruntime 1.18.0` reporting CUDA + TensorRT providers, and `torch 2.3.0+cu118` (campaign baseline). The models are evaluated with the ONNX backend on `CPUExecutionProvider` in the registered evidence (weapon), while violence runs on `cuda:0` (SlowFast) — i.e. **the GPU is under-used for the ONNX paths today**.
- Upstream: `onnxruntime` v1.30.0 (MIT) `[LIC]`. Its **DirectML Execution Provider** page states: "DirectML is in sustained engineering. DirectML continues to be supported, but new feature development has moved to WinML for Windows-based ONNX Runtime deployments." `[DOC]` — so DirectML is a *fallback* for machines without CUDA, not a strategic path; the TensorRT/CUDA EPs remain the throughput path for an RTX 3060, with the known Windows caveat that TRT/cuDNN DLLs must be on `PATH` (general ORT behavior; not re-verified here `[UNVERIFIED]`).
- Model sourcing: OpenCV Zoo (Apache-2.0 repo) and PINTO_model_zoo (MIT repo) both host third-party models whose **own** licenses differ from the repo license `[LIC]`; any model swap into `S-03`/`S-21` needs a per-file license review. NVIDIA's VPF/PyNvCodec is Apache-2.0 but **archived since 2024-06** `[META]` `[LIC]` → do not build a decode path on it.

#### 3.2.7 Violence/weapon open-source landscape
See §2.3. The absence of a credible permissively-licensed, maintained, evaluated weapon/violence project means **the project's own calibrated engines are the justified choice** — and it raises the importance of the missing calibration artifact (`F-40`: `backend/model_calibration.json` does not exist) because there is no upstream reference to substitute for it. The open-source population cannot be used to validate our thresholds either (no shared dataset/protocol), which is itself a finding for `S-05`.

---

## 4. Reusable patterns (the real deliverable)

Each pattern is stated as *what to copy* + *where it applies* + *citations*.

- **P-1 — Declared drop policy per queue.** go2rtc models buffering as explicit constants (`BufferDisable = 0`, `BufferDrainAndClear = -1`, positive = buffered seek) `[CODE] AlexxIT/go2rtc@c245815 pkg/core/readbuffer.go:8-25`. Apply to the `F-12` result queue and the four capture queues (3/30/360/600): each queue should expose a named policy + a drop counter, which is also what `R-1`/`R-2` ask for. Verification cost: low.
- **P-2 — Fan-out without buffering in the hot path; buffer at the edge.** `Receiver.Input` walks `childs` synchronously; there is no implicit per-consumer queue `[CODE] pkg/core/track.go:22-32`. Mirrors our render/decision/telemetry consumers of `SC-2`/`SC-3`.
- **P-3 — Producer/Consumer + Mode vocabulary.** `pkg/core/core.go:47-76` `[CODE]`. Useful documentation-level alignment for `S-01`'s capture/inference/render roles and the `SC-10` disabled-health state (a "disabled" mode is a first-class state, not an exception).
- **P-4 — Preload / idle heartbeat to kill connection latency.** go2rtc preloads streams that are slow to start `[CODE] internal/streams/README.md`; Frigate pushes the last frame at a low rate to make restream connections fast `[DOC] docs.frigate.video/configuration/restream`. Apply to `F-37`/`S-09` (MJPEG/WebRTC first-frame latency) and to demo clip startup (`F-20`).
- **P-5 — Tiered retention with pre/post-capture windows.** Frigate's `continuous/motion/alerts/detections` × `days` × `mode` + `pre_capture`/`post_capture` `[DOC] docs.frigate.video/configuration/record`. Apply as a *schema* for `S-07` evidence policy (do not change `SC-8` paths/names).
- **P-6 — Streaming substrate as a child process with a health probe.** Frigate → go2rtc `[DOC]`; go2rtc exposes `/api/streams` for diagnostics `[DOC]`. Apply to `SC-10`: spawn `go2rtc_win64.exe`, probe it, and surface an explicit disabled/degraded health state instead of a module-level import crash (`B-1`, `B-2`).
- **P-7 — Per-camera agent configured by file + env overrides.** Kerberos Agent `[DOC]`. Apply to `F-03` camera-source config for parity between `camera_profiles.yml`, env vars and the API surface.
- **P-8 — Optional capabilities as isolated plugins/modules with explicit auth modules.** SentryShot's workspace crates (`auth_basic/auth_none/motion/mqtt/object_detection/object_detection_tflite/thumb_scale`) `[CODE] SentryShot@master Cargo.toml`. Apply as the shape of the `SC-10` decision: `go2rtc_bridge` and `openrouter_reporting` become optional modules with a health state, like an auth module that can be "none".
- **P-9 — Recorder/notification separation.** zmES "sits along with ZoneMinder" and consumes events to push notifications + ML recognition `[DOC]`. Our `F-14`→`F-16`→`F-32` chain already implements the consumer side; the pattern to borrow is the *explicit contract boundary* (event schema + delivery guarantees), which is exactly the missing piece in `SC-4`/`R-3` (severity enum mismatch silently drops alerts).
- **P-10 — Vendored tracker with import hygiene.** ByteTrack is MIT and its tracker math is numpy/scipy, but the shipped module imports torch (unused) and two C extensions `[CODE] ByteTrack@d1bf019 yolox/tracker/byte_tracker.py:6-7`, `matching.py:1-9`. Pattern: vendor only `basetrack.py`, `byte_tracker.py`, `kalman_filter.py` and a `matching.py` rewritten on `scipy.optimize.linear_sum_assignment`, keeping a `THIRD_PARTY_NOTICES` entry.

---

## 5. License matrix and obligations

### 5.1 Permissive, reusable (code)
MIT: Frigate, Viseron, go2rtc, ByteTrack, BoT-SORT, supervision, onnxruntime, FFmpeg's LGPL configuration (verify build flags), Kerberos Agent, PINTO_model_zoo (repo only).
Apache-2.0: Savant, SAM 2 (code **and** checkpoints), OpenCV Zoo, VidGear, NVIDIA VPF (archived).
BSD-3: Norfair.
**Obligation:** MIT/BSD/Apache require attribution only; Apache-2.0 additionally requires a NOTICE/patent grant. Any vendored file must be recorded in a `THIRD_PARTY_NOTICES` file (none exists today — an integration prerequisite for P-10).

### 5.2 Copyleft / non-OSI (do not link into shipped code)
GPL-2.0: ZoneMinder, SentryShot. GPL-3.0: Motion, motionEye. AGPL-3.0: Ultralytics (already present as a fallback — see §5.3), BoxMOT. Custom non-OSI: Shinobi. Mixed/indeterminate: Scrypted. Closed: AgentDVR.

### 5.3 Ultralytics exposure (actionable)
The baseline's `F-10` fallback and `F-09` backend list include Ultralytics, whose license is AGPL-3.0 or a paid Enterprise License `[LIC]` `[DOC]`. **Owner: orchestrator** (license decision) with engineering support (delete the fallback path if the decision is "no enterprise license"). Note that `S-03`/`S-04` already have ONNX-only paths (`person_yolo.onnx`, `weapon_yolo.onnx`), so removal is technically cheap — **[INFERENCE]**, the code deletion was not performed in this research ticket.

### 5.4 Model weights and data (separate from code)
- SAM 2 checkpoints: Apache-2.0 (explicit in README) → safe for offline tooling `[DOC]`.
- OpenCV Zoo / PINTO zoo: repo license ≠ model license; per-model review required `[LIC]`.
- Violence/weapon community repositories: mostly **no license at all**, which means *no grant* of any rights, including for the weights and the video datasets they ship. Do not ingest.

---

## 6. Fit decisions (mapped to campaign IDs)

### 6.1 Integrate
| Candidate | Target | Effort | Runtime cost | Risk | Verification experiment |
|---|---|---|---|---|---|
| **go2rtc (binary)** | `SC-10`, `F-37`, `S-09` transport | M | +1 process (~tens of MB RSS `[UNVERIFIED]`) | process supervision on Windows; port conflicts; firewall prompts | Start `go2rtc_win64.exe` with a file/synthetic source; `GET /api/streams` returns the configured stream; kill it → API returns the disabled/degraded health state instead of an import error (`B-1`) |
| **ByteTrack tracker (vendored, trimmed)** | `S-04`, `F-10` | M | negligible (numpy) | C-extension ports (`lap`, `cython_bbox`) → replace with SciPy; unmeasured today | Synthetic/recorded clip through `person_detector.detect`; assert stable IDs across frames (no ID churn on a static subject) and measure per-frame tracker latency; document `person_count` semantics |
| **onnxruntime CUDA/TensorRT EP for `person_yolo.onnx`/`weapon_yolo.onnx`** | `S-03`, `F-09`, `F-10` | S–M | GPU instead of CPU (frees CPU) | cuDNN/TensorRT DLL discovery on Windows; provider fallback must be explicit | Force `CPUExecutionProvider` vs `CUDAExecutionProvider` on the same file and record per-inference latency + score equality |
| **FFmpeg (already used)** | `F-21`, `S-07` | — | — | — | Keep; add the go2rtc/ffmpeg path documented as recommended in Frigate `[DOC]` |

### 6.2 Adapt (pattern only, no code)
- **P-1/P-2 queue drop policy** → `S-01`, addresses `R-1`/`R-2` (make `/system/metrics` real for queue depths/drops, `F-36`/`S-08`).
- **P-5 retention model** → `S-07` evidence policy (config-level; do not change `SC-8`).
- **P-3/P-8 optional-module state machine** → `SC-10` decision text (missing module = explicit disabled state with health surface; matches `B-1`, `B-2`, `B-3`).
- **P-4 preload/heartbeat** → `S-09` first-frame latency for MJPEG and the future WebRTC path.
- **P-7 per-camera config layering** → `F-03`.
- **P-9 event-contract discipline** → `SC-4`, `R-3` (severity enum `none` accepted by backend, rejected by frontend validator — a silent alert drop).
- **supervision `LineZone` counting semantics** → `S-04` (define person count beyond `len(tracks)`).

### 6.3 Reject (and why)
Frigate/Viseron as runtimes (Linux/Docker); DeepStream + Savant (WSL2 + documented throughput penalty + second CUDA stack); ZoneMinder/Motion/motionEye (GPL + Linux-only + maintenance); Scrypted (license indeterminacy); Shinobi (non-OSI license, mirror rot); AgentDVR (closed source; CVE class); BoxMOT (AGPL); Norfair/VidGear (redundant); VPF/PyNvCodec (archived); SAM 2 in the live path (WSL/CUDA-ext cost); all community violence/weapon repositories (no license, no evaluation protocol).

---

## 7. Engineer handoff — 10 actionable findings

> **Workstream mapping.** The assignment texts for `WT-15/16/17/22` are not present anywhere under `jobs/sentinel-campaign/**` (workspace-wide grep, 2026-09-29; the sibling tickets report the same gap), but the sibling research artifacts identify who consumes what: **WT-15** = instrumentation/measurement design (IPC copy + queue timing) and **WT-16** = inference-runtime measurement (CPU/GPU parity, latency, VRAM) per `wt-09/docs/campaign/research/09-inference-runtime.md`; **WT-17** = transport/streaming per `wt-10/docs/campaign/research/10-camera-transport.md`; **WT-22** = tracking/counting/alerts wiring per `wt-08/docs/campaign/research/08-faces-tracking-imaging.md`; adjacent: WT-14 capture, WT-18 weapon, WT-19 violence, WT-21/23/27 faces/tracking/imaging, WT-24 recording/evidence.
> **Ownership (orchestrator broadcast, 2026-09-29 — authoritative).** WT-14 = capture quality (`backend/pipeline_capture.py` + `api.py` capture-loop hunks); WT-15 = worker/resources (`backend/frame_pipeline.py`, `backend/inference_process.py`, `backend/temporal_frames.py`, queue/IPC policy; boundary = the frame queue capture feeds); WT-16 = inference acceleration (`backend/yolo_onnx.py` provider/session/precision/export); WT-18 = weapon engineering (`backend/yolo_onnx.py` decoder/NMS/postprocess/taxonomy); WT-22 = tracking/counting/alerts wiring; WT-17 = transport/streaming. **The SC-10 fix (optional imports + explicit DISABLED health for the absent `go2rtc_bridge`/`openrouter_reporting`) is already owned by WT-28 on `codex/sentinel-28-security-api`** — as of 2026-09-29 it has landed there as commit `b7d1f43` ("fix(api): SC-10 — optional go2rtc_bridge/openrouter_reporting imports with explicit DISABLED health", reported 48 passed / 1 skipped scoped tests; orchestrator broadcast), which removes the `B-1`/`B-2` import-time crash this document cites — findings 1 and 2 below are *evidence for that change*, not a competing implementation. This research ticket deliberately did **not** cherry-pick it: no runnable API was needed for a documentation/license/code-inspection deliverable ([UNVERIFIED] at this revision: the runtime behaviour of the DISABLED health state, which WT-17/WT-28 measure).
> **Corroboration (independent, read-only comparison with sibling artifacts):** finding 1 independently reaches the same transport conclusion as `wt-10` §"Recommendation (WT-17)" — a go2rtc sidecar behind the existing `go2rtc_bridge` seam; finding 4 is the same Ultralytics AGPL rule `wt-07` already made binding for WT-18, so this document reports only the research-side evidence and defers to that rule.

#### 7.1 Routing table (finding → workstream → campaign IDs)

| # | Workstream(s) | IDs touched |
|---|---|---|
| 1 | WT-17 | `SC-10`, `F-37`, `S-09` |
| 2 | WT-17 (+ WT-24 for the report path) | `SC-10`, `F-26`, `F-37`, `S-20` |
| 3 | WT-15 (instrument), WT-16 (measure) | `S-01`, `S-08`, `F-12`, `F-36` |
| 4 | WT-18 (rule already binding in `wt-07`) | `F-09`, `F-10`, `S-03`, `S-04`, `S-21` |
| 5 | WT-22 (counting), WT-16 (measure) | `S-04`, `F-10` |
| 6 | WT-24 | `S-07`, `SC-8`, `F-21`, `F-23` |
| 7 | WT-22 | `SC-4`, `R-3` |
| 8 | WT-17 | `S-09`, `F-37` |
| 9 | WT-16 (runtime selection) | `S-03`, `S-21`, `F-47` |
| 10 | repo hygiene (`S-22`) | `S-22`, any slice that vendors code |

1. **`SC-10` is realizable now, cheaply, and defensibly: adopt the upstream go2rtc binary (MIT, native `go2rtc_win64.zip`) behind an explicit disabled health state.** Frigate — the most mature OSS NVR — uses exactly this component for restream/MSE/WebRTC `[DOC]`. *Touches:* `SC-10`, `F-37`, `S-09`. *Proof:* start binary → `/api/streams` OK → kill binary → API reports disabled/degraded, no `ModuleNotFoundError`. *Coordination:* WT-28 already owns the SC-10 code change on `codex/sentinel-28-security-api`; this finding supplies the transport-side evidence (upstream MIT binary + Frigate precedent) for that change rather than a competing patch.
2. **Make the missing-module policy a first-class state, not an exception (P-3/P-8).** `B-1`/`B-2` (import-time crash) and `B-3` (bench stubs) show the two current "solutions" are a crash and a fake. SentryShot's `auth_none` plugin is a working precedent for "capability present but disabled" `[CODE]`. *Touches:* `SC-10`, `F-26`, `F-37`, `S-20`.
3. **Give every bounded queue a named drop policy + counter (P-1).** go2rtc's `BufferDisable/BufferDrainAndClear` constants are the pattern `[CODE]`; our `R-1`/`R-2` risks and the always-zero `/system/metrics` (`F-36`, `N-3`) are the problem. *Touches:* `S-01`, `S-08`, `F-12`, `F-36`.
4. **Decide the Ultralytics license question before any distribution.** AGPL-3.0 or Enterprise `[LIC]` `[DOC]`; the ONNX paths already exist so removal is cheap. *Touches:* `F-09`, `F-10`, `S-03`, `S-04`, `S-21`. *Owner:* orchestrator.
5. **If tracking is to be trusted, vendor ByteTrack (MIT) with import hygiene and SciPy matching (P-10).** Drop the unused `torch` import (`byte_tracker.py:6-7`) and avoid `lap`/`cython_bbox` on Windows (`matching.py:1-9`); then *measure* the currently-unmeasured ByteTrack path (`F-10`, `S-04`).
6. **Adopt the tiered-retention schema for evidence policy without touching `SC-8` paths** (`continuous/motion/alerts/detections` + pre/post-capture) `[DOC]`, because it is the sector's converged vocabulary and our current policy is "one clip on alert" (`F-21`). *Touches:* `S-07`, `SC-8`, `F-21`, `F-23`.
7. **Fix the alert-envelope contract in one commit across backend + `lib/` (P-9).** `SC-4`/`R-3`: backend can emit `severity: "none"`, the frontend validator rejects it, so alerts vanish silently — the same *silent-drop* failure class that ZoneMinder's ecosystem solves with a separate, contract-checked notification server `[DOC]`.
8. **Add first-frame latency handling to the stream paths (P-4).** Frigate's idle heartbeat and go2rtc's preload are the two documented mitigations `[DOC]` `[CODE]`; apply to MJPEG today and to the WebRTC path when `SC-10` lands.
9. **Never adopt DeepStream/Savant for the Windows target** (§3.2.1): WSL2 + GeForce-only/WDDM constraint, validated on a different driver/GPU, and a documented "throughput issue while running multiple decode instances in WSL". Keep the ONNX/TensorRT EP route instead; treat DirectML as a sustained-engineering fallback only `[DOC]`.
10. **Write down `THIRD_PARTY_NOTICES` before the first vendoring.** Today there is no notice file; MIT/BSD/Apache vendoring (ByteTrack, supervision patterns) requires attribution and Apache NOTICE handling. *Touches:* `S-22` (repo hygiene), any slice that vendors code.

---

## 8. Gaps, limitations, provenance

### 8.1 Blueprint seed inputs read
- `wt-01/docs/blueprint/runtime-map.md`, `ownership-map.md`, `runtime-map-verification.md` (F-01…F-49, SC-1…SC-10, S-01…S-22 read directly).
- `wt-02/docs/blueprint/design-map.md` (screens U-01…U-10), `ui-contract.md`.
- **`wt-03/docs/blueprint/INDEX.md` (generated view, 91,918 B) and `index.json` (registry) are present and were read** after the orchestrator's seed-ready broadcast (branch `codex/sentinel-03-docs-gen`, commit `27c18d2`). The registry is `kind: living-blueprint-index`, `non_authoritative: true`, baseline `e86d34b5…`, and its namespaces (F / U / SC / S / B / N / R) plus status semantics are the ones used throughout this document; note the INDEX warning that `R-1..R-8` (silent-failure/health) is a *different* namespace from `docs/PLAN.md`'s two-digit `R-01..R-08` rebuild decisions — this document cites only the former. Its `assessed` fingerprints were used only as cross-checks.
- Sibling research artifacts consulted **read-only, as excerpts**, for cross-checks and workstream routing: `wt-06/…/06-violence-research.md` (WT-19), `wt-07/…/07-weapon-research.md` (WT-18 + the Ultralytics AGPL rule), `wt-08/…/08-faces-tracking-imaging.md` (WT-22 counting/alerts wiring), `wt-09/…/09-inference-runtime.md` (WT-15/WT-16 measurement design), `wt-10/…/10-camera-transport.md` (WT-17 transport). Where this document agrees with them it says so explicitly (§7) rather than restating their evidence as its own.

### 8.2 Not verified in this ticket (do not treat as fact)
- Any performance/throughput/resource number for the candidates (Frigate, go2rtc RSS, DeepStream, Savant, SAM 2) — no candidate runtime was installed or executed.
- Savant's ZeroMQ/Kafka/Redis adapter documentation.
- Kerberos Agent's explicit Windows support (deployment as a binary is documented, the OS matrix is not).
- Whether `lap`/`cython_bbox` have usable wheels for this project's Python 3.12 venv (a build attempt was out of scope; this is the main integration risk in finding 5).
- Runtime behavior of Windows TensorRT EP DLL resolution for onnxruntime.
- ZoneMinder's exact "Windows 10+ using WSL" instructions (nav entry observed; page body not read).

### 8.3 Repositories inspected (commits) and search provenance
- Clone `AlexxIT/go2rtc` @ `c245815e75e2a5fd60b4290f12bfc04e55a984d3` — `pkg/core/core.go`, `pkg/core/track.go`, `pkg/core/readbuffer.go`, `internal/streams/README.md`.
- Clone `FoundationVision/ByteTrack` @ `d1bf0191adff59bc8fcfeaa0b33d3d1642552a99` — `yolox/tracker/byte_tracker.py`, `yolox/tracker/matching.py`.
- Clone `roboflow/supervision` @ `0159909f22a66ff1a06e610b196c659796de973c` (declares `0.31.0.dev0`) — `src/supervision/detection/line_zone.py`, `src/supervision/__init__.py`, `pyproject.toml`.
- Raw-file reads (no clone): `SentryShot/sentryshot` (`Cargo.toml`, `README.md`), `koush/scrypted` (`LICENSE.md`), `ZoneMinder/zmeventnotification` (`README.md`), `blakeblackshear/frigate` (`LICENSE`), `roflcoopter/viseron` (`README.md`, `LICENSE`), `insight-platform/Savant` (`README.md`, `LICENSE`), `ultralytics/ultralytics` (`LICENSE`, `README.md`), `facebookresearch/sam2` (`LICENSE`, `README.md`), `NVIDIA/VideoProcessingFramework` (`LICENSE`), `opencv/opencv_zoo` (`LICENSE`), `mikel-brostrom/boxmot` (`LICENSE`), `tryolabs/norfair` (`LICENSE`), `abhiTronix/vidgear` (`LICENSE`), `ShinobiCCTV/Shinobi` (`LICENSE`), GitLab `Shinobi-Systems/Shinobi` (`LICENSE.md`, `README.md`).
- Search queries executed 2026-09-29: `agentdvr`; `violence detection deep learning`; `weapon gun detection yolo`; `boxmot tracking`; `VideoProcessingFramework PyNvCodec`. Repository metadata via `api.github.com/repos/*` and `/releases/latest` (unauthenticated quota exhausted mid-session — later repository facts used raw-file reads instead).
- Docs pages read with verbatim quotes: docs.frigate.video (`/frigate/installation`, `/frigate/hardware`, `/frigate/video_pipeline`, `/configuration/restream`, `/configuration/record`), docs.nvidia.com DeepStream (`DS_Installation.html`, `DS_on_WSL2.html`, `DS_Release_notes.html`), viseron.netlify.app, zoneminder.readthedocs.io (`faq.html`, install guide), onnxruntime.ai DirectML EP page, ispyconnect.com.

### 8.4 Limitations
- Stars were used only to *rank* search results, never as a quality claim.
- License labels come from LICENSE text, but **model weights and bundled datasets were not exhaustively enumerated** for every project — only SAM 2's checkpoint license was verified as a separate grant.
- The Windows verdicts are documentation-based: no candidate was actually installed on this machine, so "runs on Windows" claims from third parties remain `[INFERENCE]` except where the project itself ships Windows artifacts (go2rtc) or documents them (DeepStream-on-WSL2).
- No candidate code was copied, so this document creates no new licensing obligation; any follow-up vendoring (ByteTrack, supervision patterns) creates one (finding 10).
- Effort estimates (S/M/L) are qualitative and unvalidated by implementation.
