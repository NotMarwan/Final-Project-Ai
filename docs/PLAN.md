# Current execution plan

Revision: 2026-09-29 integration review. This is the single pending-work plan. The current user request supersedes its scheduling where explicitly stated. The old ASTRA prompt is retired; corrected findings live in ISSUES.md. No frozen May release is authoritative.

## Current boundary

The user explicitly authorized parallel implementation across phases despite missing camera/evaluation inputs. The old sequential phase block is superseded. Continue independent engineering work; actual acceptance evidence remains required and must not be fabricated. Camera unavailability blocks live measurements, not source fixes, UI, offline reporting or evaluation tooling.

This sprint implemented the decision/perception/transport/evidence foundations and visible health/trace/report UI. docs/ISSUES.md contains only the remaining actionable limitations plus current verified contracts. CURRENT.md records the latest matched replay evidence. The phase table below is the remaining acceptance map, not an instruction to redo completed fixes.

## Campaign workstreams (accepted addition, 2026-09-29)

The 30 workstreams were executed in parallel worktrees against pinned `e86d34b`. WT-01…WT-28 and WT-30 are integrated in the assembled review candidate; WT-29's four evaluation commits were then fast-forwarded. Their scoped research, experiments and dispositions are recorded under `docs/campaign/`; the review matrix records omissions and required follow-up. Integration means the files and code are present in this candidate, not that a runtime or acceptance gate passed. `docs/campaign/**` remains non-authoritative for product status and design.

| Workstream | Scope | Scoped artifact / owner slice |
|---|---|---|
| WT-01 | Verified runtime map | `codex/sentinel-01-runtime-map`; `docs/blueprint/runtime-map.md`, `runtime-map-verification.md`, `ownership-map.md` |
| WT-02 | Verified design map + UI contracts | `codex/sentinel-02-design-map`; `docs/blueprint/design-map.md`, `ui-contract.md` |
| WT-03 | Docs contract + living blueprint seed | `codex/sentinel-03-docs-gen`; `docs/blueprint/index.json`, `docs/blueprint/INDEX.md`, `docs/campaign/` |
| WT-04 | Commercial competitor research | `codex/sentinel-04-commercial`; `docs/campaign/research/04-commercial-competitors.md` |
| WT-05 | Open-source competitor research | `codex/sentinel-05-oss`; `docs/campaign/research/05-opensource-competitors.md` |
| WT-06 | Violence research | `codex/sentinel-06-violence-research`; `docs/campaign/research/06-violence-research.md` |
| WT-07 | Weapon research | `codex/sentinel-07-weapon-research`; `docs/campaign/research/07-weapon-research.md` |
| WT-08 | Faces / tracking / imaging research | `codex/sentinel-08-faces-research`; `docs/campaign/research/08-faces-tracking-imaging.md` |
| WT-09 | Inference / runtime research | `codex/sentinel-09-inference-research`; `docs/campaign/research/09-inference-runtime.md` |
| WT-10 | Camera / transport research | `codex/sentinel-10-camera-research`; `docs/campaign/research/10-camera-transport.md` |
| WT-11 | Web app / analytics research | `codex/sentinel-11-webapp-research`; `docs/campaign/research/11-webapp-analytics.md` |
| WT-12 | Evaluation data & methodology (fixtures + protocols + baseline) | `codex/sentinel-12-eval-data` |
| WT-13 | Measurement & telemetry | `codex/sentinel-13-telemetry` |
| WT-14 | Camera & capture quality (`backend/pipeline_capture.py`, api.py capture-loop hunks) | `codex/sentinel-14-capture-quality`; `S-01` boundary, `F-04`/`F-05` |
| WT-15 | Worker & resource architecture (`frame_pipeline.py`, `inference_process.py`, `temporal_frames.py`, queue/IPC policy) | `codex/sentinel-15-worker-arch`; `S-01`, `F-06`/`F-12` |
| WT-16 | Inference acceleration (`yolo_onnx.py` provider/session/precision/export) | `codex/sentinel-16-inference-accel`; `S-03` boundary, `F-09`/`F-10` |
| WT-17 | Video transport & synchronization | `codex/sentinel-17-transport` |
| WT-18 | Weapon detection engineering (`yolo_onnx.py` decoder/NMS/taxonomy boundary) | `codex/sentinel-18-weapon-eng`; `S-03`, `F-09` |
| WT-19 | Violence detection engineering | `codex/sentinel-19-violence-eng` |
| WT-20 | Decision & calibration (alert payload additions, calibration status) | `codex/sentinel-20-decision-calib`; `S-05`/`S-06`, `SC-4`, `F-14`/`F-15`/`F-40` |
| WT-21 | Person & face detection | `codex/sentinel-21-face-detect` |
| WT-22 | Tracking, counting & best frames | `codex/sentinel-22-tracking-counting` |
| WT-23 | Image enhancement | `codex/sentinel-23-enhancement` |
| WT-24 | Evidence pipeline | `codex/sentinel-24-evidence`; `S-07`, `SC-8` |
| WT-25 | Operator interface & alerts | `codex/sentinel-25-ui-alerts`; `U-01`…`U-10`, `SC-4` |
| WT-26 | Statistics & dashboard correctness | `codex/sentinel-26-stats` |
| WT-27 | Arabic reporting & offline operation | `codex/sentinel-27-arabic-reporting`; `F-25`/`F-28` |
| WT-28 | Security & API contracts (optional imports `SC-10`, route authorization `R-8`, `/security/session` `F-45`) | `codex/sentinel-28-security-api`; `docs/campaign/security/28-api-security-audit.md` |
| WT-29 | Independent evaluation & resilience | no source branch of its own (branch created at integration); runs against the assembled candidate |
| WT-30 | Integration & reproducibility | branch created at integration; assembles the candidate in `wt-30` and consumes all branches, including the blueprint re-assessment pass |

Workstream evidence uses the non-authority marker (see `docs/campaign/README.md`). Product status and design claims still move only through generated `docs/CURRENT.md`, `docs/DESIGN.md`, this plan and `docs/ISSUES.md`. The assembled source changes require blueprint fingerprint reassessment and regenerated documents after implementation stabilizes.

## Rebuild sequence

| Phase | Pending outcome | Completion evidence |
|---|---|---|
| 0 | Baseline harness, verified positive/negative suite, semantic test audit | Reproducible baseline and labeled evaluation; no fabricated glass latency |
| 1 | Restructure working code, secure packaging, dependency decisions | G-12 and baseline within5%; verified backups before deleting weights |
| 2 | Unified decision core, thresholds, sampling, evidence and API correctness | G-05/G-07/G-10/G-11/G-15; falling false positives |
| 3 | Domain adaptation, calibration, window/stride derivation | G-02/G-03/G-06 |
| 4 | Measured inference/IPC/transport optimization | G-01/G-04/G-13 |
| 5 | Implement dashboard credibility and interaction consistency | Visible decision state, traces, health, stable overlays; verified UI |
| 6 | Arabic forensic reporting offline | G-09 under concurrent detection |
| 7 | Demo hardening and reproducible operation | All gates, including live evidence and60-minute soak |

Phase transitions require evidence, not an additional habitual approval question. Preserve the user's low-intervention constraint: research ways to remove manual work first. Do not ask for bulk manual filming before testing public-data, zero-shot, adaptation and synthetic-training options. Test truth must remain independently labeled. Do not train or delete weights without a verified recoverable copy and the task's required authority.

## Research mandates still requiring decisions

R-01 process topology; R-02 export/acceleration; R-03 domain gap with minimal human labeling; R-04 reproducible calibration; R-05 one or two object detectors and authoritative weights; R-06 local Arabic VLM; R-07 video transport; R-08 frontend architecture/visual implementation; R-09 dependency modernization and existing open-source pipelines. Compare primary sources and local measurements, then record the decision in this document or a registered ADR. None is presumed complete because a tool was mentioned.

## Acceptance targets

Every gate is measured by the Phase 0 harness on the RTX 3060 and reported as a number. A gate is not passed until the measurement exists.

| ID | Gate | Target |
|---|---|---|
| **G-01** | Sustained live throughput, all detection active | ≥ 30 fps median, ≥ 25 fps p95 |
| **G-02** | False positives on the negatives suite (≥ 20 benign clips: hugging, handshakes, waving, walking, phone use) | **0 confirmed alerts** |
| **G-03** | True positives on the positives suite (staged violence + visible weapon, close-range, webcam) | ≥ 90 % detected |
| **G-04** | Glass-to-alert latency, p50 / p95 | ≤ 1200 ms / ≤ 2000 ms |
| **G-05** | Threshold sources in the codebase | Exactly 1 file. Zero inline numeric literals in the decision path |
| **G-06** | Calibration | Artifact exists, is reproducible from a committed script, ECE reported. Pipeline refuses to start without it |
| **G-07** | Temporal window integrity | Every window's wall-clock span within ±10 % of nominal; asserted in tests |
| **G-08** | Evidence clips | Correct duration ±5 %, correct frame rate, plays in Chrome, chain-of-custody entry written. Verified under live-camera conditions |
| **G-09** | Offline operation | Full demo runs with the network disabled — detection, alerts, evidence, and forensic report |
| **G-10** | Silent failures | Zero bare `except: pass` in perception/decision/streaming. Every subsystem exposes health |
| **G-11** | Decision core coverage | ≥ 95 % line coverage, all §4 false-positive scenarios covered |
| **G-12** | Repository hygiene | No binaries > 10 MB outside LFS, no build output, no secrets, no junk directories, one coherent doc set |
| **G-13** | Cold start | Launch to first live frame with detection active ≤ 60 s |
| **G-14** | Stability | 60-minute continuous run: no crash, no memory growth > 10 %, no FPS degradation > 10 % |
| **G-15** | API responsiveness under load | Every mutating endpoint returns ≤ 300 ms p95 while a live stream and 2 SSE clients are active, with no interruption to stream cadence |

---

Interpretation: report both FPS p05 (slow tail) and p95 so the inherited G-01 wording cannot conceal stalls. These are targets, not current results. Gate results require evidence hashes, date, workload, environment and limitations. Documentation consistency passing is separate from these15 runtime gates.

## Research observations already established

Retain the native installation while recording baseline; this is a temporary comparison boundary, not a permanent architecture choice. Frigate's installation guide does not officially support Windows (https://docs.frigate.video/frigate/installation/); Viseron documents Docker installation (https://viseron.netlify.app/docs/documentation/installation/); Savant builds on DeepStream (https://github.com/insight-platform/Savant). DeepStream documents WSL2 support: https://docs.nvidia.com/metropolis/deepstream/8.0/text/DS_on_WSL2.html . No local comparison justified adopting those larger platforms. The local dependency decision is updated under R-09 below. These platform observations were last checked 2026-09-12; reverify upstream support before a new platform decision.

KTH's original publisher offers auxiliary single-person action clips with noncommercial/citation conditions (https://www.csc.kth.se/cvap/actions/). They cannot by themselves satisfy the required hugging/handshake/phone and close-range positive domains. Initial acquisition failed in the September 12 session; the later campaign acquired auxiliary fixtures and WT-29 recorded the failed G-02/G-03 slice described in ISSUES.md. The RWF-2000 author repository withdrew videos for privacy (https://github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection); do not assume an unofficial mirror solves rights/provenance. Training pseudo-labels or synthetic data cannot serve as independent test truth.

Measure completed inference, including CUDA synchronization when required, rather than launch timing: https://docs.pytorch.org/tutorials/recipes/recipes/benchmark . Preserve the current environment until each upgrade has a comparable measurement and rollback. These observations narrow the research; they do not falsely close R-01 through R-09.

## Current implementation decisions

R-01: retain one inference process per active source for CUDA isolation, with bounded persistent model threads and camera-local decision state. Inference IPC uses max-side640 frames; evidence preserves a timestamped max-side960 ring. This is implemented; a multi-camera resource comparison remains pending.

R-02/R-05: retain installed weights and the corrected ONNX contracts. The measured local Windows/Python 3.12 environment currently uses ONNX Runtime GPU 1.18.0 with Torch 2.3.0+cu118. Four matched full-pipeline file-replay reports at revision `1218a6cb` are valid, each with active violence, weapon and person model calls. CUDA runs used `CUDAExecutionProvider` with CPU fallback and rendered 30 FPS median; the two CUDA reports measured person medians 22.29/22.05 ms and weapon medians 51.78/52.86 ms, versus CPU medians 78.57/82.58 ms and 515.90/539.65 ms. Those paired reports remain historical comparisons. The latest report is `bench/results/integration-review-2026-09-29/report.json` from final source `e1a5636`; all 62 backend hashes match. It records 25/30/30.55 render FPS p05/p50/p95 and 240/19/147 person/weapon/violence calls. This fresh CUDA replay verifies the reviewed source; no new matched CPU speedup ratio is claimed. It is replay throughput evidence, not accuracy, live throughput, or end-to-end latency evidence. The base `backend/requirements.txt` still pins CPU ONNX Runtime; a fresh install is not a GPU-default setup. Keep CPU/GPU distributions mutually exclusive and use `scripts/select_onnx_runtime.py` only after stopping the backend; its provider check alone is not promotion evidence. Official compatibility reference: https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html .

R-03/R-04: no pseudo-labels or synthetic labels are accepted as independent evaluation truth. bench/calibrate.py now validates unique source hashes and split separation, fits temperature only on the calibration split, and reports held-out NLL/Brier/ECE. It emits a candidate artifact, never a runtime certification. Method reference: https://proceedings.mlr.press/v70/guo17a.html . Data acquisition and camera-domain validation remain required.

R-06: an offline deterministic Arabic facts-only report is implemented and exposed in the UI. For future image-language analysis, first evaluate Qwen3.5-2B against Qwen3-VL-2B; official model cards show vision support, but Arabic forensic quality and concurrent12GB operation are unmeasured. Qwen3.5-2B weights are4.55GB on disk (not peakVRAM); 4B requires9.32GB unquantized weights and is not a safe default beside active detection. Qwen2.5-VL-3B has a noncommercial research license, unlike the Apache2.0 cards for the shortlisted versions. Sources: https://huggingface.co/Qwen/Qwen3.5-2B , https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct , https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/blob/main/LICENSE . No VLM weights downloaded or model-quality claim made.

R-07/R-08: keep current MJPEG/SSE with event-driven frame availability and monotonic frame/observation identities while transport alternatives are measured. The implemented dashboard uses existing semantic design tokens, displays per-model traces/health/window validity, treats replay and stale data explicitly, and offers a local report before optional online reporting. A security-driven Next.js update is recorded under R-09; other library changes still require a reproducible comparison.

Runtime controls: /set_threshold changes violence/watch thresholds while preserving the startup confirmation margin (clamped at1 without permanently shrinking the margin). /set_cooldown changes the shared validated runtime policy. /decision/config accepts a complete validated policy. These are runtime changes, not persistent TOML edits. Legacy environment/calibration thresholds no longer override the decision policy at startup.

File replay samples violence windows on original media time; captured_at remains actual read time for processing latency and weapon age. Live source windows use actual monotonic capture time and reject gaps outside the window contract. A file-media window must never be reported as proof of live capture integrity.

R-09: upgrade `next` and `eslint-config-next` to 16.3.6 and apply compatible lockfile security fixes. The prior dependency audit reported 9 production vulnerabilities, including a critical Windows-hosted unauthenticated RCE affecting Next.js 16.0 through versions before 16.3.3 (GHSA-p293-qw3h-jr36 / CVE-2026-75604). The official advisory says affected Windows-hosted applications have no known workaround and should upgrade; 16.3.6 is beyond the patched 16.3.3 release and includes an additional security fix. Its official peer range accepts React and React DOM `^19.0.0`, consistent with the project's 19.2.4 versions. After the compatible updates, `docs/campaign/security/integration-dependency-audit.json` reports zero vulnerabilities across production and development dependencies. This audit is dependency evidence only; it does not establish application security, runtime acceptance, or vulnerability-free transitive software beyond that lockfile snapshot. Sources: https://github.com/vercel/next.js/security/advisories/GHSA-p293-qw3h-jr36 , https://github.com/vercel/next.js/releases/tag/v16.3.6 , https://github.com/vercel/next.js/blob/v16.3.6/packages/next/package.json .

The user-authorized integration is complete at the source/contract level: the 30-workstream review and dispositions are in `docs/campaign/handoff/integration-review.md`, with verification scope in `integration-validation.json`. Astra/Luna orchestration is installed as a project-scoped kit and was used for bounded workers and independent review. Remaining phase targets above require the listed measurements/data, not another source merge.
