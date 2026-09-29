---
authority: scoped
non_authoritative: true
---
# AI Sentinel — candidate ownership map for the engineering workstreams

Companion to `docs/blueprint/runtime-map.md`. Purpose: let two agents work in parallel without editing the same file,
and make the interfaces that must be frozen by the orchestrator explicit.

**Rules encoded here**
- A slice owns the listed files exclusively. Unlisted files are read-only for that slice.
- Any edit to a **shared-contract file** (§0) requires orchestrator assignment of a single integration owner.
- Every slice that changes runtime behaviour must state its revision and re-measure; `bench/results/**` belongs to
  revision `6fb3bcac…`, not to the pinned commit (runtime-map B-5).
- Nothing in this file authorizes touching `docs/CURRENT.md`, `docs/DESIGN.md`, `docs/design-*.*`, `docs/SOURCE-MANIFEST.json`
  (all generated) or the `docs/authority.json` registry.

---

## 0. Shared contracts (orchestrator must coordinate one owner each)

| ID | Contract | Canonical artifact | Consumers | Freeze requirement |
|---|---|---|---|---|
| SC-1 | FastAPI route table + `AppState` | `backend/api.py` (2280 lines, single file) | every frontend slice, bench harness, evidence, transport, security | one owner at a time; split only via a pre-agreed refactor PR |
| SC-2 | Inference result schema | `backend/inference_process.py:427-455` (`result.update({...})`) | render/decision, telemetry, fusion, evidence metadata, frontend overlay | field names/types are the de-facto protocol; add fields additively, never rename silently |
| SC-3 | Detection SSE payload | `backend/api.py:1594-1622` + `lib/pipeline-telemetry.ts` + `lib/detection-envelope.ts` | UI overlay, telemetry freshness | change in one commit across backend+`lib/` |
| SC-4 | Alert SSE payload | `backend/pipeline_render.py:206-233` + `lib/sentinel-selectors.ts:44-100` | UI store, alerts, telegram, ledger | `type`/`severity` enumerations must match the frontend validator (runtime-map R-3) |
| SC-5 | Decision policy schema | `config/thresholds.toml` + `backend/decision_config.py` | API, workers, fusion, decision layer, UI labels | schema_version 1; a key addition is a cross-slice change (G-05) |
| SC-6 | Timestamp semantics | `captured_at` (monotonic), `sample_timestamp`/`inference_sample_time` (media clock for files), `isoTime` (UTC wall) | capture, IPC, decision, evidence, UI | renames require all three layers |
| SC-7 | Observation identity | `inference_sequence`, `violence_observation_id`, `weapon_observation_id`, `inference_generation` | decision layer, telemetry, frontend traces | every producer change must keep IDs monotone and unique per completion |
| SC-8 | Evidence storage layout | `EVIDENCE_DIR/{alert_id}.mp4`, `.part.mp4`, ledger `evidence_ledger.jsonl` | evidence writer, clip API, PDF report, bench | path/name changes break `/api/clips/list`, `/clips/{id}`, `/download_evidence/{id}` and `_validate_alert_id` |
| SC-9 | Generated-docs contract | `scripts/docs_contract.py`, `docs/authority.json` | any slice adding a `docs/**/*.md` | adding a document to the registry is an orchestrator decision, never a local workaround |
| SC-10 | Missing-module policy for `go2rtc_bridge` / `openrouter_reporting` | `backend/api.py:46-50,295-298`; `bench/runtime.py:229-284` | every backend slice | orchestrator decides: commit the modules, or make imports optional with an explicit disabled health state (B-1) |

---

## 1. Slice table

| Slice | Owns (exclusive) | Reads (no writes) | Tests it owns | Primary risk to manage |
|---|---|---|---|---|
| **S-01 Worker architecture / IPC** | `backend/inference_process.py`, `backend/frame_pipeline.py`, `backend/pipeline_capture.py`, `backend/temporal_frames.py` | `backend/api.py` (worker wiring), `backend/metrics.py` | `backend/tests/test_inference_optimization.py`, `test_motion_score.py`, `test_resize_pixel_contract.py`, `test_eof_discontinuity.py` | queue sizes (3/30/360/600), `spawn` start method, reset handshake timing |
| **S-02 Violence path** | `backend/inference.py`, `backend/models/multi_angle_x3d.py` | `backend/best_model.pt` (hashes in runtime-map §3.1), `backend/calibration_utils.py` | `test_runtime_observation_contract.py`, `test_angle_invariance.py`, `test_inspect_model_checkpoint.py`, `test_multi_angle_benchmarks.py` | window/stride semantics (F-08), SlowFast-vs-X3D identity, EMA/hysteresis interaction with thresholds |
| **S-03 Weapon path** | `backend/weapon.py`, `backend/yolo_onnx.py` | `backend/models/weapon_yolo.onnx` (untracked), `backend/models/person_yolo.onnx` | `test_weapon_observation_contract.py`, `test_weapon_category.py`, `test_weapon_accuracy.py`, `test_weapon_smoke_tool.py`, `test_yolo_onnx_contract.py` | class-index vs name mapping (6 classes), label filter defaults, decay/TTL semantics |
| **S-04 Tracking / counting** | `backend/person_detector.py` | `backend/yolo_onnx.py`, `lib/detection-types.ts` | `test_live_visual_pipeline.py`, `test_yolo_onnx_contract.py` (person cases) | ByteTrack path is unmeasured; `person_count` currently = len(tracks) |
| **S-05 Decision / calibration** | `backend/live_alert_decision.py`, `backend/decision_config.py`, `config/thresholds.toml`, `backend/calibration_utils.py`, `backend/train_calibration.py`, `bench/calibrate.py` | `backend/fusion.py`, `backend/inference.py` (score fields) | `test_decision_observations.py`, `test_runtime_contracts.py` | SC-5 freeze; keep one threshold authority (G-05); calibration artifact absence (F-40) |
| **S-06 Fusion / severity** | `backend/fusion.py` | `backend/decision_config.py` | `test_threat_dispatch.py` | fusion weights only in TOML; motion must stay context-only |
| **S-07 Evidence** | `backend/evidence.py`, `backend/evidence_video.py` | `backend/api.py` (`_write_evidence_clip`, `EVIDENCE_DIR`), `backend/local_forensics.py` | `test_evidence_video.py`, `test_evidence_ledger_concurrency.py`, `test_api_sprint.py` (evidence cases) | atomic publish + probe verification; single-process ledger; `"N/A"` hash substitution (R-4) |
| **S-08 Telemetry / observability** | `backend/metrics.py`, `lib/pipeline-telemetry.ts`, `components/pipeline-telemetry.tsx`, `hooks/use-detection-stream.ts` | `backend/api.py` (`/system/status`, `/detections`) | `tests/pipeline-telemetry.test.mjs`, `tests/visual-state.test.mjs`, `tests/detection-envelope.test.mjs` | make `/system/metrics` real (N-3); expose queue depths/drops (R-1/R-2) |
| **S-09 Transport** | `backend/webrtc_streamer.py`, `components/webrtc-player.tsx`, `components/video-player.tsx` | `backend/api.py` (stream routes), `go2rtc_bridge` (SC-10) | `tests/e2e/test_operator_flows.py` | MJPEG/SSE are retained pending measurement; WebRTC is disabled/unavailable |
| **S-10 UI shell & dashboard** | `app/`, `components/shell/`, `components/sections/`, `components/overview/`, `styles/` | `lib/sentinel-store.tsx`, `lib/api-auth.ts` | `components/overview/overview-time.test.mjs`, `components/shell/locale.test.mjs`, `tests/e2e/test_operator_flows.py` | `app/globals.css` is the design-token source consumed by the docs generator (SC-9) |
| **S-11 Incidents UI (alerts/clips)** | `components/alert-feed.tsx`, `components/alert-history.tsx`, `components/alert-toast.tsx`, `components/clip-sidebar.tsx`, `components/clip-player.tsx`, `components/incident-replay.tsx`, `components/incident-panel.tsx`, `components/ai-report.tsx` | `lib/dashboard-data.ts`, `lib/local-report.ts`, `lib/sentinel-selectors.ts` | `hooks/__tests__/alert-feed.test.mjs`, `tests/local-report.test.mjs` | alert envelope validator (SC-4); `/security/session` 404 (F-45) |
| **S-12 Store / selectors / filtering** | `lib/sentinel-store.tsx`, `lib/sentinel-selectors.ts`, `lib/dashboard-data.ts`, `lib/ui-fixtures.ts`, `lib/live-visual-state.ts` | `components/video-player.tsx` (type source) | `lib/__tests__/sentinel-selectors.test.mjs`, `lib/__tests__/ui-fixtures.test.mjs` | type files live under `components/` (awkward direction) — coordinate with S-09 before moving |
| **S-13 Stats / overview analytics** | `components/overview/overview-charts.tsx`, `components/overview/hero-incident-instrument.tsx`, `lib/detection-types.ts` (label/colour maps) | `lib/sentinel-selectors.ts` | `components/overview/overview-time.test.mjs` | client-side-only aggregation; no server stats endpoint exists |
| **S-14 Reporting (offline + PDF + remote text)** | `backend/reporting.py`, `backend/local_forensics.py`, `backend/openrouter_reporting.py` (absent, SC-10) | `backend/api.py` (report routes), `docs/` (never) | `tests/e2e/test_operator_flows.py` (report view), `tests/local-report.test.mjs` | facts-only claim discipline: the offline report must never assert image analysis |
| **S-15 Faces** | `backend/face_intel.py` | `backend/api.py` (would need new routes) | `test_face_policy.py`, `test_face_policy_persistence.py` | fully disconnected (F-30): wiring requires SC-1 change |
| **S-16 Audio** | `backend/audio.py` | `backend/api.py` (audio routes) | — | no UI caller; `audio.enabled: false` |
| **S-17 Categories / multi-detection** | `backend/detection_categories.py` | `backend/api.py` (category routes), `lib/detection-types.ts` | `test_categories.py`, `test_api_categories.py`, `test_intrusion_category.py`, `test_intrusion_api_contract.py` | must stop mutating the shared `weapon_engine` (R-5); fix the "X3D" label claim (F-29) |
| **S-18 Notifications (Telegram)** | `backend/notifications.py`, `components/telegram-status.tsx` | `backend/api.py` (notification routes) | — | untested; queue-full drops invisible |
| **S-19 Security / auth / audit** | `backend/security.py`, `lib/api-auth.ts`, `hooks/use-api-access.ts`, `components/api-access.tsx`, `components/shell/access-notice.tsx`, `backend/colab_bridge_server.py` | `backend/api.py` (auth calls per route) | `test_security_contract.py`, `lib/__tests__/api-auth.test.mjs` | every mutating route must authorize before mutation; `ADMIN_API_KEY` empty ⇒ 503 for all mutations (demo-mode semantics) |
| **S-20 Bench / measurement harness** | `bench/**` (incl. `runtime.py`, `run.py`, `calibrate.py`, `probe.py`, `security_scan.py`, `common.py`, `test_*.py`) | `backend/**` (read-only), `docs/evidence.json` (registry) | `bench/test_*.py` | only slice allowed to write `bench/results/**`; must record revision + hashes |
| **S-21 Training / dataset tooling** | `backend/train_finetune.py`, `backend/training/`, `backend/datasets/`, `backend/tools/`, `backend/export_models.py`, `backend/prepare_colab_bundle.py`, `backend/render_colab_notebook.py`, `notebooks/` | `bench/**` | `test_dataset_loader.py`, `test_manifest_dataset.py`, `test_video_loader.py`, `test_video_input_contract.py`, `test_train_*` | provenance for shipped weights is UNKNOWN (F-48) |
| **S-22 Docs contract / repo hygiene** | `scripts/docs_contract.py`, `scripts/docs-contract.mjs`, `tests/docs_contract/`, `docs/authority.json` (registry edits need orchestrator), `AGENTS.md`, `CLAUDE.md`, `.kilo/**`, `.roo/**`, `.opencode/**` | everything | `tests/docs_contract/test_docs_contract.py` | B-6 is already red; do not delete check rules to force green |

### 1.1 Files with no owner above (deliberately unassigned)

`README.md`, `PROJECT_DOCUMENTATION.md`, `SETUP_NEW_LAPTOP.md`, `TRANSFER_PLAN.md`, `run_*.ps1`, `start*.ps1`,
`stop.bat`, `setup*.bat/ps1`, `Dockerfile`, `docker-compose.yml`, `desktop/`, `manifests/`, `reports/`, `backups/`,
`notebooks/`, `thesis_results/`, `archive/`, `public/`, `components/احتياطي/`, `backend/احتياطي/`,
`backend/Repository search results*.{html,_files/}`, `components/files*.zip`, `docs/AI_Sentinel_Phase2_Midterm_Deck.pptx`,
`docs/*.py` (generator script), `bench/fixtures.json`, `bench/legacy_tests.py`.
Treat as hygiene/cleanup targets (runtime-map N-7, N-8) requiring an explicit orchestrator task; do not delete silently.

---

## 2. Suggested parallelization waves

| Wave | Slices (disjoint files) | Rationale |
|---|---|---|
| W-0 (unblock) | S-22 or orchestrator: decide SC-10 (missing modules) + B-6 docs staleness | nothing else can be validated green first |
| W-1 | S-02, S-03, S-04, S-05, S-06, S-07, S-16, S-17, S-21 | backend modules with disjoint files, all behind SC-1 read-only |
| W-2 | S-08, S-09, S-10, S-11, S-12, S-13, S-19 | frontend slices; S-09/S-12 need one coordinator for the `video-player.tsx`↔`lib` type direction |
| W-3 | S-01, S-14, S-15, S-18, S-20 | SC-1 (api.py) and SC-2 (result schema) owners — serialize these |
| Integration | one owner per SC-1..SC-10 | merge api.py-touching work one at a time |

---

## 3. Per-slice hand-off checklist (mandatory for every downstream agent)

1. State the pinned commit and prove your worktree was clean at it (`git status --porcelain`).
2. Name the owned files you changed; if you touched a SC file, name the orchestrator approval.
3. Provide `path:line` evidence for every behavioural claim; separate "measured" from "inferred".
4. Run the *scoped* tests for your slice and paste the command + result summary.
5. Do not run repo-wide build/lint/test; the orchestrator runs the single integration pass.
6. Record any new unmeasured path and any new silent failure you observed.
7. Do not regenerate `docs/CURRENT.md`, `docs/DESIGN.md`, `docs/design-*`, `docs/SOURCE-MANIFEST.json`, and do not add
   your document to `docs/authority.json` unless the orchestrator owns that change.
