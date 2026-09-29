# Current unresolved issues

This is the current defect register for the 2026-09-29 integration review. The baseline findings below describe pinned revision `e86d34b`, not the assembled candidate; their resolution status is explicit. Archived line references are not instructions to reintroduce old behavior. Source tests establish contracts, not real-world accuracy.

## Baseline findings recorded from the verified runtime map (2026-09-29)

These findings describe the pinned baseline; current candidate resolution is shown in the final column. Full evidence: `docs/blueprint/runtime-map.md` (§0 baseline integrity, §6.1 risks) and `docs/blueprint/runtime-map-verification.md` (V-01…V-22); registry entries in `docs/blueprint/index.json`.

| ID | Finding (baseline `e86d34b`) | Evidence | Resolution status |
|---|---|---|---|
| B-1 | At baseline, API imports required two untracked optional modules and could fail in a clean checkout | runtime-map §0, verification V-02/V-03/V-04 | Candidate integrates guarded optional imports and tests; verify fresh-install behavior after final dependency installation |
| B-3 | Baseline HTTP/throughput measurements used disabled bridge/report adapters when optional modules were absent | runtime-map §0, verification V-05 | Historical baseline remains invalid for real bridge/report claims. The registered campaign replay has active person, weapon and violence inference, but does not validate external integrations |
| B-5 | The baseline's registered runtime evidence was measured at another revision and recorded backend drift and missing files | runtime-map §0, verification V-12, `docs/evidence.json` | Fresh final-source CUDA replay at `e1a5636` is registered and all 62 backend source hashes match. Older CPU/CUDA pairs remain historical comparisons; no live/accuracy acceptance follows |
| B-6 | `npm run docs:check` failed at the pinned baseline due stale generated outputs | runtime-map §0, verification V-16, `docs/campaign/docs-sync-baseline-delta.md` | Regenerated snapshots and strict documentation checks pass after semantic reassessment; runtime gates remain separate |
| R-8 | Baseline left 25 of 42 routes without `security_controller.authorize()`, including mutating routes and reads/streams | runtime-map §6.1, verification V-20 | WT-28 integrated route guards and `/security/session`; the current candidate authorizes `POST /api/analyze` as admin. Behavior tests cover missing, viewer and admin credentials, including admin demo start/stop and report publication; live concurrency across all mutating routes remains unmeasured |
| F-45 | At baseline, the frontend credential flow called a missing `GET /security/session` route | runtime-map §2 (`F-45`), verification V-06 | Candidate integrates `/security/session`; viewer/admin API contracts and offline browser flows pass; live integration remains separate |

## Campaign evaluation and runtime evidence (2026-09-29)

WT-29's auxiliary KTH evaluation at threshold 0.45 is a measured negative result, not a deployment-domain estimate. It recorded frame recall 0.140, window recall 0.138, event recall 2/12 (0.167), and alert precision 2/9 (0.222). Seven false alerts occurred in 0.1487 negative camera-hours (47.06 per camera-hour); four were on negative clips (three handwaving and one walking), and three were unmatched alerts on boxing-positive sessions. This fails the evaluated G-02 negatives and does not close the required six-class benign set. The evaluated positives also fail G-03. Do not tune thresholds on these test labels.

The weapon auxiliary set has 4 false positives across 36 weapon-free clips (11.1%); no weapon-positive ground truth was available, so weapon recall is unmeasured. No independent event-onset labels were available, so G-04 glass-to-alert latency is unmeasured; the inherited stride-4 floor is not a remeasurement. G-06 remains open: no validated calibration artifact or ECE exists. Startup now raises `CalibrationArtifactError` without an artifact unless the explicit development override is used; that fail-safe does not count as calibration or production readiness.

## Remaining acceptance work

| Area | Current limitation | Required next evidence |
|---|---|---|
| Live evaluation | Camera unavailable; the auxiliary KTH negatives and boxing positives fail G-02/G-03 and do not cover the required target domains | Real live run, independently labeled representative positives and negatives, false positives/recall and glass-to-alert measurements |
| Calibration | No validated runtime calibration artifact or ECE; scores remain unverified. Startup refuses without the artifact except under the explicit development override | Use `bench/calibrate.py` on disjoint independently labeled scores, assess held-out ECE, then validate window-level runtime integration |
| Temporal sampling | Invalid live windows are rejected and health degrades; file sampling uses original media time | Test interrupted/reconnected camera and derive window/stride with accuracy and latency measurements |
| Performance | Final-source CUDA replay has active inference, 30 FPS median and 25 FPS p05; all 62 backend hashes match. Historical matched CPU/CUDA pairs demonstrate the prior provider comparison; base requirements still install CPU ONNX Runtime | Remeasure on source changes; use matched pairs for future comparisons and complete live-load acceptance. File replay does not establish default GPU setup or live acceptance |
| Evidence video | H.264/yuv420p fast-start output fully decoded and played in Chromium; atomic publication and SHA receipt | Verify actual live duration and production browser playback with camera evidence |
| Health coverage | Active worker failures are surfaced; legacy peripheral catches remain | Complete subsystem fault injection and remove remaining silent failure paths |
| API coverage | Operational read/viewer and mutation/admin contracts pass, including fail-closed startup, PDF publication, demo controls and triage | Exercise every mutating route under live load; the measured threshold/cooldown/policy trio does not close G-15 |
| Offline reporting | Deterministic Arabic facts-only summary works without a language model | Full network-disabled demo, local VLM Arabic quality and concurrent memory/latency evaluation |
| Stability | Only bounded development replay runs | 60-minute isolated soak and reconnect/shutdown audit |
| Packaging | Pre-existing untracked assets, duplicate exports and user changes remain | Review recoverable artifacts and runtime dependency packaging; no unreviewed bulk deletion |
| Dependency audit | `next`/`eslint-config-next` are upgraded to 16.3.6; the post-update npm audit snapshot reports zero vulnerabilities | Keep the lockfile report with the reviewed tree and complete application-level security tests; dependency audit does not prove application security |

## Implemented and contract-tested

Raw YOLO outputs now use metadata class order, correct cxcywh/letterbox conversion and NMS. Real CPU person fixture returns three detections and agrees with the installed Ultralytics decoder. This is decoder parity, not detector accuracy. Weapon metadata contains six classes; configured filters cannot redefine their indices.

Each camera has its own decision layer. Distinct positive and negative observations reach the confirmation window; cached render ticks cannot add votes; cooldown and age bounds use a monotonic clock. config/thresholds.toml supplies validated default decision policy, and runtime API updates propagate to workers. Some legacy model preprocessing/EMA parameters remain separate and still need calibration review.

Resize is based on current pixels, model workers are persistent and bounded, inference IPC downsizes before transfer, person boxes return to original source coordinates, capture does not discard two frames per live read, and rendering/JPEG streaming use frame availability plus monotonic sequence. CPU thread limits prevent each ONNX session from creating competing full-size pools.

Evidence writers use captured timestamps and bounded FFmpeg H.264/yuv420p encoding, fully decode-check temporary fast-start video before atomic publication, and join at source shutdown. Missing encoders fail explicitly; imageio-ffmpeg0.6.0 is pinned and installed in the project environment. Ledger append is serialized across ledger instances in one process, validates prior chain integrity and fsyncs before returning a receipt. External multi-process ledger writers remain unsupported. Incomplete .part.mp4 files are excluded from clip lists.

The frontend independently ages violence and weapon observations; one model cannot refresh another model's stale score or healthy status. The frontend does not replace an unavailable live camera with a sample video. Missing modality scores remain unknown, each trace advances only on its own model completion, and stale inference is distinct from a connected transport. The offline Arabic report is labeled facts-only and does not invent image analysis.

## Security work still required

Protected admin mutations reject missing server authentication and verify keys with a constant-time comparison; client role headers do not grant authority. Demo start/stop and `/api/analyze` are admin-gated in the current candidate; operational reads and evidence routes require viewer authorization. Keyless demo mode may explicitly grant viewer access; it never grants admin mutation rights. Current Telegram and administrator credentials matched ten historical Git objects in the previous redacted scan and still require owner-led revocation/rotation. OpenRouter credentials were copied into local build configuration; review sharing exposure. No credentials were rotated, transmitted or copied into these documents.

## Test interpretation

The final integration checks pass: 817 backend/root Python tests plus 43 measurement/evaluation-harness tests (860 total), 108 Node tests, typecheck, lint and production build. All eight browser checks pass across a seven-pass full run and the corrected console test's focused run. The Next.js 16.3.6 fixture uses localhost to comply with dev-origin protection; expected offline API errors are identified by their exact URL origin and all JavaScript page errors still fail. Ten Python skips cover absent desktop packaging and optional untracked model assets; five integration tests were deliberately deselected. Real person, weapon and violence inference completed in the fresh replay. This establishes covered contracts, not total coverage or model accuracy. Detailed scope: `docs/campaign/handoff/integration-validation.json`.
