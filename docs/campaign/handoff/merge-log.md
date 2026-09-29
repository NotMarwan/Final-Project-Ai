---
authority: scoped
non_authoritative: true
---
# WT-30 integration merge log (candidate `codex/sentinel-30-integration`)

Distilled from the per-merge commit messages (`git log --merges`). Branch worktrees live under
`C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-NN`; all branches were cut from `e86d34b`.

## Order and commits taken

| # | Branch | Commits taken | Conflicts | Resolution |
|---|---|---|---|---|
| 1 | `-03-docs-gen` | fa155e3, 3879dc1 (+ wt-01/wt-02 blueprint inputs, 8dba654 regen) | none | merged --no-ff; blueprint seed lands first by contract |
| 2 | `-28-security-api` | 1928e71, b7d1f43, 7b09b46, b4d10e1, 7f1f854, 1f5489a | none | — |
| 3 | `-13-telemetry` | b137c0b, 9c4e25e, aaffb13, 6f70392, 64f82b2, 1d77522, d9bed13…63a4d31, ed010fe, 6bfd9da, 2a5d3dd, f5601cd | api.py imports; route-test add/add; generated docs | imports: kept HEAD (`build_incident_pdf` + one SC-10 block). route test: kept WT-28's 510-line strict superset (0 deletions vs the 183-line variant shared byte-identically by every engineering branch). generated docs: ours, regenerated at the end |
| 4 | `-15-worker-arch` | 23bb826, 3674a7b, f346ad3 | api.py imports; route test | as #3 |
| 5 | `-16-inference-accel` | 86d7697, 1218a6c, f80bc43 | api.py imports; route test | as #3 |
| 6 | `-14-capture-quality` | a0b2d4b, e7dc49e, 7e4e5d6, a2dcebe, 4ff1479 | api.py imports; route test; generated docs | as #3; WT-14's capture-loop variant landed as the interim shape |
| 7 | `-18-weapon-eng` | e0938b1, c5762af, c5bd0b7, 38700b5, a16e632, e66129c, a468a89, 41e9af4 | api.py imports; route test; generated docs | as #3 |
| 8 | `-19-violence-eng` | 4a1643c … 70cb2cf (13 commits) | none | clean |
| 9 | `-20-decision-calib` | a86952d, b8e94ec, c4f6bf9, b928762, 9867a7f, 3327f7a, 8ac3994, 4bee457 | api.py imports; route test; generated docs | as #3; **G-06 verified landed ONCE** (`enforce_startup_calibration` imports + single call site in `_init_engines`) |
| 10 | `-21-face-detect` | e023b59, 17bf872, 8653ed6, 0f3853f, 4df04ec, 9af5ce6, f2731a9 | api.py ×3; route test; generated docs | module-scope: union (WT-21 face bootstrap + single openrouter block). `camera_worker` evidence path: union of WT-21's face-capture enqueue (with `_release_face_post` on every path) and WT-14's `_annotate_guard`. Verified `/api/faces/health`, `/api/faces/incidents/{alert_id}`, `.../crops/{crop_id}` present |
| 11 | `-22-tracking-counting` | 1abce2d, 55a5652, 4139dd0, 8a06dbd, 3db92f5, 7144813 | api.py ×6; route test | **capture-loop single-variant rule**: `incident_capture=None` pre-init before `try`; WT-22's real `capture_queue.IncidentCapture` wiring + `on_detection_meta`; WT-14's evidence-ring variant kept in full (writer/`materialize_evidence_samples` contract); options union `_annotate_guard` + `on_detection_meta`; de-duplicated the two auto-merged artifacts (one None-guarded `options['incident_capture']`, one `incident_capture.stop` after `render_t.join`). `pipeline_render.py` has one `_emit_alert` site with a None-guarded incident trigger. Tests: capture/tracking suites 31 + 32 passed |
| 12 | `-23-enhancement` | 9f5b070, 3c600ee, a882ac0, f1ba5f9, d4dadd6 | generated docs | api.py auto-merged; S-07 `append_record` primitive present exactly once (shared with WT-24). **Integrator-authored seam** (no branch shipped it; handoff defers it to the integrator): SC-10-style optional `enhance` import + lazy `_get_enhancement()`; construction after `EvidenceLedger` init in `_init_engines`; lifespan start/stop; evidence-finalization trigger via `enqueue_alert_enhancement` (one `frame` CropRef, parent = published clip file-bytes hash); `GET /evidence_derivatives/{alert_id}` (viewer auth, 503 DISABLED when module/build unavailable). Tests: enhance + evidence suites 99 passed / 6 skipped (tier-1 gated); smoke: route present, service+scheduler build, no import/build error |
| 13 | `-24-evidence` | 018b5c4, 5f28f1d, b0e6cad | api.py ×2; route test; generated docs | S-07 content identical to the copy already integrated via WT-23 (applied once). E-7 encoder opt-in present (unset = validated libx264 CPU path) |
| 14 | `-25-ui-alerts` | e0cca48, 89cd06d, c18fc9a, 1142dac, 6d73eee, d1ace90, 143dc64 | api.py ×2; route test; generated docs | imports region: **union** (build_incident_pdf + `alert_triage` import); module-scope: ours. Triage routes auto-merged; tests 24 passed |
| 15 | `-26-stats` | 07f18bb, e687b96, 0310cbb, d082150, a94eccb, dd11a02, 604c5d3 | generated docs | api.py auto-merged; `GET /stats/overview` present; lib/* merged clean |
| 16 | `-27-arabic-reporting` | cd2a03b … 80b11c1 (13 commits) | api.py ×2; route test; generated docs | as #14; tests 34 passed |
| 17 | `-17-transport` | 693ea8b, b235f5b, b349d4d, 4f2bb36, a344687 + WT-13 telemetry cherry-picks | api.py ×7, metrics.py ×5, pipeline_render.py ×1, sentinel-store.tsx ×1, test_metrics_telemetry ×2, 13-* add/add | unions: MJPEG generator keeps WT-28's bounded-stream `try/finally` + `_release_stream_slot` **and** WT-17's 4-tuple `wait_for_frame` unpack + `X-Frame-*` headers; kept WT-17's `go2rtcSidecar` health entry, SC-3 frame-identity keys in `_build_detection_payload`, `reconnectDelayMs` import; kept HEAD's newer metrics/decision-latency ingest, fusion block, `capture_clock_base`; dropped WT-17's unused envelope-parser imports (lint) and its older `13-*` doc copies (ours = WT-13's latest). 0 conflict markers in those files; `py_compile` clean |
| 18-25 | `-04`…`-11` research | one docs commit each | none | all 8 merged clean; `docs:check` green after |

## Cross-cutting rules applied

- **SC-10 identical content**: every engineering branch carried the same SC-10 optional-import patch (b7d1f43 and 15+ cherry-picks). Always resolved as identical content — one application, never duplicated.
- **Add/add `backend/tests/test_authenticated_routes.py`**: WT-28's 510-line file is a strict superset of the 183-line copy every other branch carried (verified: 0 deletions). Kept WT-28's.
- **Generated docs** (`docs/CURRENT.md`, `docs/SOURCE-MANIFEST.json`, `docs/blueprint/INDEX.md`, `docs/DESIGN.md`, `docs/design-tokens.json`, `docs/design-preview.html`): every conflict resolved as "ours pending regeneration", then regenerated once at the end with `npm run docs:sync` (see commit `af076f3`); `docs:check` GREEN afterwards.
- **Tool-layer duplication**: this session's Edit/bash calls were sometimes executed twice against the same file. Every duplicated application was detected and repaired in the same turn (double-inserted lifespan stop block, double route definition, one wrongly-replaced test `def`) — the final tree has 0 conflict markers and compiles.
