---
authority: scoped
non_authoritative: true
---
# Runtime-map verification log

Worktree: `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-01`, branch `codex/sentinel-01-runtime-map`,
baseline `e86d34b5d16abcc133ad3470c8d135d00b2423d4`.
Run date: **2026-09-29**. Python used for all backend commands:
`C:/Users/PCD/Downloads/Final Project AI Sentinel/venv/Scripts/python.exe` (3.12.5, onnxruntime 1.18.0, torch 2.3.0+cu118)
— invoked **read-only**, nothing installed into it.

Conventions: commands are shown as executed; outputs are verbatim excerpts (long traces trimmed with `…`).
Anything not reproduced here is marked in `runtime-map.md` as UNVERIFIED/UNKNOWN.

---

## V-01 Baseline is clean and pinned

```console
$ git status && git log --oneline -1
On branch codex/sentinel-01-runtime-map
nothing to commit, working tree clean
e86d34b docs: regenerate current state and design system after the rebuild
```

## V-02 `go2rtc_bridge` / `openrouter_reporting` are not in git

```console
$ git ls-files | grep -i "go2rtc\|openrouter"   # exit 1, no output
$ git log --oneline --all -- backend/go2rtc_bridge.py   # no output
$ git -C "C:/Users/PCD/Downloads/Final Project AI Sentinel" status --porcelain backend/go2rtc_bridge.py backend/openrouter_reporting.py
?? backend/go2rtc_bridge.py
?? backend/openrouter_reporting.py
```
Referenced at `backend/api.py:48,50` and `backend/api.py:296,298`. Files present only in the operator's dirty checkout.

## V-03 Direct import of the API module fails

```console
$ cd backend && venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); import api"
IMPORT FAILED: ModuleNotFoundError No module named 'go2rtc_bridge'
```

## V-04 The canonical start command fails identically

Canonical command from `run_backend.ps1`: `venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port 8002 --app-dir backend`

```console
$ venv/Scripts/python.exe -m uvicorn api:app --host 127.0.0.1 --port 18099 --app-dir backend
  File "…/uvicorn/importer.py", line 19, in import_from_string
    module = importlib.import_module(module_str)
  File "…/backend/api.py", line 50, in <module>
    from go2rtc_bridge import Go2RTCBridge
ModuleNotFoundError: No module named 'go2rtc_bridge'
```

## V-05 The bench harness stubs exactly those two modules

```console
$ sed -n '230,284p' bench/runtime.py
    if "go2rtc_bridge" not in sys.modules and importlib.util.find_spec("go2rtc_bridge") is None:
        module = types.ModuleType("go2rtc_bridge")
        class DisabledGo2RTCBridge: …
    if ("openrouter_reporting" not in sys.modules and
            importlib.util.find_spec("openrouter_reporting") is None):
        module = types.ModuleType("openrouter_reporting")
        class DisabledDeepSeekReportService: …

$ cat bench/results/perf-after-2026-09-26/benchmark-overrides.json
{ "disabled_optional_modules": ["go2rtc_bridge","openrouter_reporting"],
  "reason": "These optional services are outside the local replay capture-to-alert workload." }
```

## V-06 Backend route table vs frontend call sites

```console
$ grep -nE "@app\.(get|post|patch|delete|put)" backend/api.py | sed -E 's/.*@app\.([a-z]+)\("([^"]+)".*/\1 \2/' | sort
delete /demo_stop/{clip_id}
get    /alerts
get    /api/categories
get    /api/clips/list
get    /api/webrtc/{cam_id}
get    /audio/status
get    /audit/recent
get    /audit/status
get    /cameras/status
get    /clips/{alert_id}
get    /decision/config
get    /demo_video/{clip_id}
get    /detections
get    /download_evidence/{alert_id}
get    /download_report/{alert_id}
get    /evidence_chain/{alert_id}
get    /health
get    /notifications/status
get    /reports/deepseek/status
get    /reports/deepseek/{alert_id}
get    /reports/local/{alert_id}
get    /security/status
get    /system/metrics
get    /system/status
get    /video_feed
patch  /api/webrtc/{cam_id}/whep
post   /api/analyze
post   /api/categories/{category_id}/toggle
post   /api/webrtc/{cam_id}/whep
post   /audio/analyze
post   /decision/config
post   /decision_layer/reset
post   /demo_start/{clip_id}
post   /notifications/telegram/test
post   /notifications/telegram/test_video
post   /reports/deepseek/test
post   /reports/deepseek/{alert_id}
post   /reports/local/{alert_id}
post   /set_cooldown
post   /set_threshold
post   /switch_camera   (returns 410)
post   /webrtc/offer/{camera_id}
```

Frontend call sites (enumerated with a node scan over tracked `lib/ hooks/ app/ components/` plus manual confirm):

```console
$ grep -rhoE "API_BASE \+ \"[^\"]+\"|\$\{API_BASE\}[^\"\`]*|apiFetch\(\`[^\`]+\`|new EventSource\([^)]*\)" --include=*.ts --include=*.tsx lib hooks app components | sort -u
${API_BASE}/alerts
${API_BASE}/download_evidence/${alert.id}
${API_BASE}/video_feed?camera_id=…&k=…
API_BASE + "/api/clips/list"
API_BASE + "/clips/"
API_BASE + "/download_evidence/"
API_BASE + "/download_report/"
API_BASE + "/evidence_chain/"
apiFetch(`${API_BASE}/api/categories`
apiFetch(`${API_BASE}/api/webrtc/${…}`)
apiFetch(`${API_BASE}/demo_start/${id}`)
apiFetch(`${API_BASE}/demo_stop/${id}`)
apiFetch(`${API_BASE}/health`)
apiFetch(`${API_BASE}/notifications/telegram/test`)
apiFetch(`${API_BASE}/reports/deepseek/${…}`)   and  …/status
apiFetch(`${API_BASE}/reports/local/${…}`)
apiFetch(`${API_BASE}/security/session`)
apiFetch(`${API_BASE}/security/status`)
apiFetch(`${API_BASE}/system/status`)
new EventSource(`${API_BASE}/detections?camera_id=…`)
```

**Result:** exactly **one** genuine frontend→backend mismatch: `/security/session`
(`hooks/use-api-access.ts:29`, `components/api-access.tsx:23`) exists only in the operator's dirty `api.py`
(dirty line 2357) — not at this commit ⇒ HTTP 404 (finding F-45).
All other frontend paths resolve to a route above. Backend routes with **zero** frontend callers (verified by per-path
grep counts): `/api/analyze`, `/api/categories/{id}/toggle`, `/audio/analyze`, `/audio/status`, `/audit/recent`,
`/audit/status`, `/cameras/status`, `/decision/config`, `/decision_layer/reset`, `/demo_video/{id}`,
`/notifications/status`, `/notifications/telegram/test_video`, `/reports/deepseek/test`, `/system/metrics`,
`/webrtc/offer/{id}`. `components/category-filter.tsx:31` uses `/api/categories` (GET) only.

```console
$ git -C "C:/Users/PCD/Downloads/Final Project AI Sentinel" grep -n 'security/session' backend/api.py
2357:@app.get("/security/session", summary="Verify the current local UI credential")
```

## V-07 Frontend test suites run and pass (behavioural subset)

```console
$ node --experimental-strip-types --test tests/*.test.mjs lib/__tests__/*.mjs hooks/__tests__/*.mjs components/overview/*.test.mjs components/shell/*.test.mjs
ℹ tests 57
ℹ pass 57
ℹ fail 0
```
Note `tests/api-auth.test.mjs` performs source-text regex assertions (6 `readFile` calls), not behaviour checks (N-9).
No `package.json` script runs any `.mjs` test.

## V-08 Configuration keys that are declared but never read

```console
$ grep -rn "sentinel.db" backend/*.py                                  # no output
$ grep -rn "clip_retention_days\|max_clips_stored\|auto_loop" backend/*.py   # no output
$ grep -rn "inference_timeout_ms\|frame_cache_size\|async_inference" backend/*.py  # no output
$ grep -rn "confidence_threshold" backend/*.py                         # no output
$ grep -rn "person_overlay" backend/*.py
backend/api.py:1241: 'person_overlay_enabled':_env_flag('PERSON_OVERLAY_ENABLED',True)…
backend/inference_process.py:211:    if config.get('person_overlay_enabled',True):
$ grep -rn "CORS" backend/*.py
backend/api.py:26:from fastapi.middleware.cors import CORSMiddleware
backend/api.py:1486:    CORSMiddleware,
```
Consequences: no retention enforcement exists; `.env.example`'s `CORS_ORIGINS` is inert (`api.py:1487` reads
`config['server']['cors_origins']` from YAML only).

## V-09 Inference worker startup vs model load (required cross-check)

```console
$ grep -n "violence_pipeline=ViolenceInferencePipeline|weapon_engine=WeaponSignalEngine|person_detector=PersonDetector|ready_event.set()|mark('calibration'"
197:        violence_pipeline=ViolenceInferencePipeline(config.get('weights_path','best_model.pt'),device,threshold=policy.violence_threshold,stride=config.get('violence_stride',16))
198:        mark('violence','OK' if violence_pipeline.enabled else 'FAILED',…)
204:        weapon_engine=WeaponSignalEngine(WeaponConfig.from_settings(config.get('weapon_config',{}),os.environ),device=device)
214:            person_detector=PersonDetector(conf_threshold=config.get('person_conf_threshold',.45),device=device.type)
222:    mark('calibration','DEGRADED','No validated calibration integration; scores are not calibrated probabilities')
246:        ready_event.set()
```
Order: violence → weapon → person, each with its own try/except that records `FAILED` health and continues; the
per-camera thresholds handed to the worker come from `DecisionConfig` (`policy.violence_threshold`), while the profile
path (`calibration_utils.load_calibration_profile`) only shapes logit temperature/bias/EMA/hysteresis.
`ready_event` is set **after** all three attempts, so the parent's media-loop reset handshake never waits on a
still-loading model (`api.py:1310-1325`).

Registered model identities (from `bench/results/sprint2-verified-480p/report.json`, revision `6fb3bcac…`):

```json
{"violence":{"device":"cuda:0","is_x3d_flag":false,"actual_model_class":"ViolenceDetector",
             "stride":16,"threshold":0.45,"load_ms":3020.17},
 "weapon":{"actual_backend":"_ONNXBackend","ready":true,"providers":["CPUExecutionProvider"],
           "config":{"labels":["pistol","rifle","shotgun","knife","sword","revolver"],"interval":4,"min_interval_ms":500}}}
```

## V-10 Decision votes vs cooldown configuration (required cross-check)

```console
$ grep -n "cooldown_seconds|confirm_n|confirm_m|watch_threshold" config/thresholds.toml
7:watch_threshold = 0.45
9:confirm_n = 2
10:confirm_m = 3
12:cooldown_seconds = 3.0

$ grep -n "_cooldown = load_decision_config|_decision_config = load_decision_config|layer.apply_config(policy)|pipeline.threshold = policy.violence_threshold" backend/api.py
426:        self._cooldown = load_decision_config().cooldown_seconds
429:        self._decision_config = load_decision_config()
517:                layer.apply_config(policy)
524:                    pipeline.threshold = policy.violence_threshold
```
Confirmation rule enforced at `live_alert_decision.py:175-176` (`≥ confirm_n of last confirm_m votes ≥ confirm_threshold`),
cooldown at `:170-174` (`now + cooldown_seconds`, monotonic, cannot be rewound by out-of-order producer timestamps),
and `POST /set_cooldown` / `POST /set_threshold` route through the same `apply_decision_config` (`api.py:504-560`,
`2109-2121`). Behaviour covered by `backend/tests/test_decision_observations.py` and `test_api_sprint.py`.

## V-11 Evidence writer vs clip list API (required cross-check)

```console
$ grep -n 'EVIDENCE_DIR / f"{alert_id}.mp4"|EVIDENCE_DIR.glob|endswith(".part.mp4")' backend/api.py
727:    out_path = EVIDENCE_DIR / f"{alert_id}.mp4"
1701:    clip_path = EVIDENCE_DIR / f"{alert_id}.mp4"          # GET /clips/{id}
1717:        paths = sorted(EVIDENCE_DIR.glob("*.mp4"), …)     # GET /api/clips/list
1719:            if clip_path.name.endswith(".part.mp4"): continue
2137:        str(EVIDENCE_DIR / f"{alert_id}.mp4"),               # GET /download_evidence/{id}
```
Write path is `.part.mp4` → verified encode → `Path.replace(out_path)` (`api.py:776-785`); `EVIDENCE_DIR` resolves from
`config['storage']['evidence_dir']` = `./evidence_clips` relative to `backend/` (`api.py:286`). Consistent with list,
stream and download routes. Ledger receipt appended after publication (`api.py:813-822`).

## V-12 Model assets: hashes and ONNX metadata (read-only from operator checkout)

```console
$ node -e "<sha256 stream over the 4 weight files>"
e85b15fe74a16de9ac98562a072a50bffdcda5a7fb6ef4d8594dc7de466ab6b5  6230954    backend/weapon_hadi_yolo.pt
3fafb13e995667e7f877c647b33df05be6d587e75aa79d9cc34e9b3f493e60b8  12851087   backend/models/person_yolo.onnx
96991cd5d5dbeb7e8d439b3e5b75517bc8c55ea4ac740ec5bc8491d545875aef  103636665  backend/models/weapon_yolo.onnx
2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01  149344325  backend/best_model.pt

$ venv/Scripts/python.exe -c "<onnxruntime metadata dump>"
=== backend/models/person_yolo.onnx
input images [1, 3, 640, 640] tensor(float)
output output0 [1, 84, 8400] tensor(float)
names {0: 'person', 1: 'bicycle', …}
args {'batch': 1, 'half': False, 'dynamic': False, 'simplify': True, 'opset': 12, 'nms': False}
end2end False
=== backend/models/weapon_yolo.onnx
input images [1, 3, 640, 640] tensor(float)
output output0 [1, 10, 8400] tensor(float)
names {0: 'pistol', 1: 'rifle', 2: 'shotgun', 3: 'knife', 4: 'sword', 5: 'revolver'}
args {'batch': 1, 'half': False, 'dynamic': False, 'simplify': True, 'opset': 12, 'nms': False}
end2end False

$ ls backend/model_calibration.json
ls: cannot access 'backend/model_calibration.json': No such file or directory   (exit 2)
```

## V-13 Backend test collection depends on the working directory

```console
$ cd backend && venv/Scripts/python.exe -B -m pytest tests --collect-only -q -p no:cacheprovider
ERROR tests/test_api_sprint.py … tests/test_security_contract.py
E   ModuleNotFoundError: No module named 'backend'
190 tests collected, 8 errors in 8.26s

$ cd . && venv/Scripts/python.exe -B -m pytest backend/tests --collect-only -q -p no:cacheprovider
283 tests collected in 27.33s
```
`backend/tests/conftest.py:8-11` prepends `backend/` to `sys.path`, which fixes top-level imports from repo root but
breaks the `backend.*` imports when pytest's rootdir is `backend/`.

## V-14 API-dependent backend tests error at runtime (supports B-1)

```console
$ venv/Scripts/python.exe -B -m pytest backend/tests/test_api_sprint.py backend/tests/test_decision_observations.py backend/tests/test_api_categories.py -q -p no:cacheprovider
… backend\api.py:50: ModuleNotFoundError: No module named 'go2rtc_bridge'
46 passed, 22 errors in 11.72s
```
Every one of the 22 errors is the same missing module; all 22 are tests whose fixture imports `backend.api`.

## V-15 Full backend suite

Superseded by V-21: all 41 tracked `backend/tests/test_*.py` files were executed in grouped runs from the repository
root. A single uninterrupted 283-test run was launched but did not complete within the harness's inline window; the
grouped results in V-21 cover the same files and are the authoritative numbers recorded by this agent.
`docs/ISSUES.md` states that the "140 tests, 0 failures" figure belongs to the 2026-09-12 sprint and that "the older
full-suite report remains a dated baseline with pre-existing collection/fixture errors".

## V-16 `docs:check` at this commit

```console
$ node scripts/docs-contract.mjs --check
Stale generated document: docs/SOURCE-MANIFEST.json
Stale generated document: docs/CURRENT.md
EXIT=1
```

Cause (read-only recomputation of the generator's own outputs, no files written):

```console
$ venv/Scripts/python.exe -B -c "<import scripts/docs_contract.py; generate(ROOT); diff vs on-disk>"
docs/SOURCE-MANIFEST.json DIFF
   field source_fingerprint -> 13a7aec9… != 4f020c0f…
   field baseline_backend_changed -> ['backend/api.py','backend/inference.py','backend/inference_process.py','backend/yolo_onnx.py']
                                  != ['backend/_pipeline_ai_deprecated.py','backend/api.py','backend/audio.py','backend/augmentations.py','backend/check_model_sha.py', …]
docs/design-tokens.json MATCH
docs/DESIGN.md MATCH
docs/design-preview.html MATCH
docs/CURRENT.md DIFF
   -Implementation fingerprint: `13a7aec9…`   +Implementation fingerprint: `4f020c0f…`
```
The generator compares the registered baseline report's `environment.source_hashes` against files present in *this*
checkout; the report lists 43 backend files including untracked ones (B-4), so a clean checkout can never reproduce the
committed generated text.

`check_policy()` also fails **any** `docs/**/*.md` not listed in `docs/authority.json:canonical_docs`
(`scripts/docs_contract.py:110-120`). The three blueprint files added by this campaign therefore appear in the failure
list. Per assignment, the checker was **not** modified, no rule/retirement record was deleted, and the registry was
**not** edited to force a pass.

Verbatim output after this campaign's documents were committed (`node scripts/docs-contract.mjs --check`):

```console
Unregistered active document: docs/blueprint/ownership-map.md
Unregistered active document: docs/blueprint/runtime-map-verification.md
Unregistered active document: docs/blueprint/runtime-map.md
Stale generated document: docs/SOURCE-MANIFEST.json
Stale generated document: docs/CURRENT.md
EXIT=1
```

Two distinct failure classes are therefore present: (a) the pre-existing generated-document staleness of B-6, and
(b) this campaign's blueprint documents not being in the authority registry. This is an intentional, recorded
consequence (ownership-map SC-9), to be resolved by an orchestrator decision — an authorized registry entry, or
relocating campaign artifacts outside `docs/**`. `npm run docs:sync` was deliberately **not** run: it would rewrite
generated files outside this agent's permitted paths and would not fix (b).

## V-17 Repo hygiene counts (supports N-7/N-8)

```console
$ git -c core.quotepath=false ls-files | grep -a احتياطي
backend/احتياطي/api.py
backend/احتياطي/inference.py
components/احتياطي/dashboard-header.tsx
components/احتياطي/incident-panel.tsx
components/احتياطي/video-player.tsx
$ git ls-files | grep -c "Repository search results_files"     # 58
$ git ls-files | grep -iE "\.(zip|pptx|onnx|pt|mp4|avi|exe|pdf)$"
backend/best_model.pt
backend/weapon_hadi_yolo.pt
components/files (1).zip
components/files.zip
demo_assets/videos/FXC43fACfPc_0.avi
demo_assets/videos/Wq0BuA8GM84_0.avi
demo_assets/videos/YJzChqSg_0 (1).avi
docs/AI_Sentinel_Phase2_Midterm_Deck.pptx
```

## V-18 Dead-code counts inside `backend/api.py`

```console
$ for f in _open_capture _drain_to_latest _read_cap_props _estimate_motion_score _weapon_signal_from_report \
           _encode_snapshot _is_rtsp_source _call_vlm_forensics; do grep -c "$f" backend/api.py; done
1 1 1 1 1 1 1 1        # definition only, no call sites anywhere in the repo
$ grep -rn "update_decision_layer" --include=*.py .   # definition only (api.py:645)
$ grep -rn "pipeline_metrics" --include=*.py backend/  # definition + single read at api.py:2221
$ grep -rn "broadcast_person_data" --include=*.py backend/  # definition only (api.py:479)
```

## V-19 Frontend↔backend severity enumeration check

```console
$ grep -n "SEVERITIES\|Weapon Detection" lib/detection-envelope.ts lib/sentinel-selectors.ts
lib/detection-envelope.ts:24: const SEVERITIES = new Set(["low", "medium", "high", "critical"])
lib/sentinel-selectors.ts:29: … Math.min(4, …)  and  value.type === "Weapon Detection" ? "Weapon" : …
$ grep -n "severity_medium_threshold\|def severity_for" backend/decision_config.py
```

Frontend accepts `severity ∈ {critical, high, medium}` for an alert (and additionally `low` for multi-threat boxes);
`DecisionConfig.severity_for()` can return `"none"` for scores below `severity_medium_threshold` (0.40). A confirmed
alert whose reported observation score is below that bound is emitted by the backend and then **rejected** by
`parseAlertEnvelope`, with no server-side record of the drop (finding R-3). Not reproducible without a live run;
recorded as a contract risk, not a measured failure.

## V-20 Route authorisation coverage

```console
$ node -e "<scan @app.<method> blocks in backend/api.py for an authorize( call>"
total routes 42 | without authorize(): 25
  GET     /api/webrtc/{cam_id} @api.py:1520
  POST    /api/webrtc/{cam_id}/whep @api.py:1529
  PATCH   /api/webrtc/{cam_id}/whep @api.py:1541
  GET     /video_feed @api.py:1553
  POST    /webrtc/offer/{camera_id} @api.py:1560
  GET     /cameras/status @api.py:1577
  GET     /alerts @api.py:1589
  GET     /detections @api.py:1635
  POST    /demo_start/{clip_id} @api.py:1646
  DELETE  /demo_stop/{clip_id} @api.py:1671
  GET     /demo_video/{clip_id} @api.py:1681
  GET     /clips/{alert_id} @api.py:1694
  GET     /api/clips/list @api.py:1711
  GET     /api/categories @api.py:1738
  POST    /api/analyze @api.py:1752
  GET     /notifications/status @api.py:1813
  GET     /reports/deepseek/status @api.py:1957
  POST    /switch_camera @api.py:2070
  GET     /security/status @api.py:2143
  GET     /audit/status @api.py:2148
  GET     /audit/recent @api.py:2153
  GET     /audio/status @api.py:2181
  GET     /system/status @api.py:2186
  GET     /system/metrics @api.py:2218
  GET     /health @api.py:2266
```

`AccessController.authorize` grants `"admin"` whenever the provided `X-API-Key` matches, and returns 503 for any
non-`viewer` requirement when no key is configured (`backend/security.py:48-60`). Consequently, in the default
(demo) configuration every mutation is closed but every read/stream route above is open — including
`DELETE /demo_stop/{id}` and `POST /api/analyze`, which are *not* routed through the 503 gate.

---

## V-21 Backend test baseline at this commit (all 41 tracked test files exercised)

Commands: `venv/Scripts/python.exe -B -m pytest <files> -q -p no:cacheprovider` from the repository root (the only
invocation that collects cleanly, V-13), `PYTHONDONTWRITEBYTECODE=1` to keep the worktree clean. Grouped runs:

| Run | Files (summary) | Result |
|---|---|---|
| R-1 | `test_api_sprint`, `test_decision_observations`, `test_api_categories` | 46 passed, **22 errors** (all B-1) |
| R-2 | `test_yolo_onnx_contract`, `test_weapon_observation_contract`, `test_weapon_category`, `test_categories` | 44 passed, **1 failed** |
| R-3 | `test_motion_score`, `test_resize_pixel_contract`, `test_runtime_contracts`, `test_runtime_observation_contract`, `test_security_contract`, `test_threat_dispatch`, `test_api_runtime_config`, `test_intrusion_category` | 34 passed, **3 failed** |
| R-4 | `test_evidence_ledger_concurrency`, `test_demo_clips`, `test_face_policy`, `test_face_policy_persistence`, `test_dataset_loader`, `test_manifest_dataset`, `test_video_loader`, `test_video_input_contract`, `test_train_config`, `test_train_finetune_sampling`, `test_live_visual_pipeline`, `test_intrusion_api_contract` | 24 passed, **17 failed**, **25 errors** |
| R-5 | `test_eof_discontinuity`, `test_evidence_video`, `test_inference_optimization`, `test_inspect_model_checkpoint`, `test_rwf2000_manifest`, `test_weapon_smoke_tool` | 20 passed, **1 failed** |
| R-6 | `test_gpu_activation`, `test_angle_invariance`, `test_multi_angle_benchmarks`, `test_rwf2000_smoke` | 17 passed, **2 failed** |
| R-7 | `test_latency`, `test_threat_latency_benchmark`, `test_train_rwf2000_smoke_actual`, `test_weapon_accuracy` | 12 passed, **2 failed**, **18 skipped** |

Failure causes, all reproduced individually:

1. **B-1 missing module (52 outcomes across R-1/R-3/R-4/R-5).** e.g.
   `backend/api.py:50: ModuleNotFoundError: No module named 'go2rtc_bridge'`; `test_threat_dispatch.py` additionally
   surfaces `AttributeError: module 'backend' has no attribute 'api'`.
2. **Tracked tests that assert behaviour the current code no longer has (5 outcomes):**
   - `test_weapon_category.py::test_weapon_engine_cooldown_skipping` — expects wall-clock `_last_inference_at` to gate
     skipping; the engine now gates on `_last_start_monotonic` + frame interval (`weapon.py:457-459`). Reproduced alone:
     `1 failed, 7 passed`.
   - `test_multi_angle_benchmarks.py::{test_bulk_benchmark_scanning,test_bulk_benchmark_error_handling}` —
     `AttributeError: module 'tools' has no attribute 'benchmark_threat_latency'` (`backend/tools/` has no
     `__init__.py`, so `tools.benchmark_threat_latency` is never imported).
   - `test_latency.py::{test_inference_latency_under_500ms,test_stride_processing_does_not_block}` —
     `AttributeError: 'ViolenceInferencePipeline' object has no attribute '_sample_times'` (the window-validity deque
     added with the timestamp contract is not created by the test's ad-hoc construction).
   - `test_demo_clips.py::test_all_three_avi_files_exist` — the test resolves `test/*.avi` and
     `unrelated/archived-projects/violence/…`, while `_load_example_sources()` resolves
     `demo_assets/videos/{Wq0BuA8GM84_0.avi, YDOJvzChqSg_0 (1).avi, FXC43fACfPc_0.avi}` (`api.py:247-253`).
3. **Cross-test `sys.modules` pollution (16 outcomes in R-4).** `backend/tests/test_face_policy.py:18-39` installs a
   fake `torch` (`types.ModuleType("torch")` with only `cuda`/`device`) when real torch is not yet imported, and its
   `sys.modules` backup/restore only runs if the test class reaches setup — which it cannot, because B-1 fails the
   import first. Later tests in the same session then fail with
   `ModuleNotFoundError: No module named 'torch.utils'; 'torch' is not a package` or
   `AttributeError: module 'torch' has no attribute 'Tensor'`. Each of `test_dataset_loader.py`,
   `test_manifest_dataset.py`, `test_video_loader.py`, `test_train_finetune_sampling.py` **passes in isolation**
   (`5 passed`, `5 passed`, …).
4. **Accuracy suite silently self-skips (18 skips in R-7).** `test_weapon_accuracy.py` looks for the weapon checkpoint
   at `backend/../best.pt` (repository-root `best.pt`), which does not exist; the tracked weapon weights are
   `backend/weapon_hadi_yolo.pt` and the untracked `backend/models/weapon_yolo.onnx`. The only weapon-accuracy test
   set therefore never executes at this commit.

**Conclusion:** the committed suite is not a usable green/red baseline. `docs/ISSUES.md` already warns that "the older
full-suite report remains a dated baseline with pre-existing collection/fixture errors"; this log quantifies that for
the pinned revision. Downstream agents must not report "tests pass" from this suite without first resolving B-1 and
recording the exact file/result.

## V-22 Face API routes exist nowhere in the committed source

```console
$ grep -rn '"/face' --include=*.py .            # tracked trees
backend/tests/test_face_policy.py:157,166,175,185,192,200,216,223,237   # test only
$ grep -c "/face" backend/api.py
0
$ grep -n '@app\..*"/face' "C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/api.py"
(no output — the operator's dirty api.py has no face routes either)
$ grep -rn '"/face' --include=*.py "C:/Users/PCD/Downloads/Final Project AI Sentinel"
…/.runlogs/colab_bridge_repro/backend/api.py:1177  @app.get("/face/status" …)
…/.runlogs/colab_bridge_repro/backend/api.py:1195  @app.post("/face/policy" …)
… (11 routes total, incl. /face/policy/reload, /face/registry, /face/registry/{person_id}/enroll)
```

The only place in the whole project where the face API exists is an **untracked run-log snapshot** of `backend/api.py`
inside the operator's checkout (`.runlogs/colab_bridge_repro/backend/api.py`). The tracked test
`backend/tests/test_face_policy.py` therefore asserts an API that was never committed, and `backend/face_intel.py`
(F-30) has no route layer at this revision.

## Not verified by this agent (explicitly open)

- Full backend suite result (see V-15) and any model-accuracy claim.
- Live-camera behaviour of any kind: no capture device present (documented operator condition).
- `bench/runtime.py` end-to-end run: it writes into `bench/results/**`, outside this agent's permitted paths.
- `bench/security_scan.py` re-run for credential history (same path restriction); only the names/kinds recorded in
  `docs/ISSUES.md` and the targeted grep in runtime-map §6.3 were used.
- Whether `aiortc`, `groq`, `reportlab`, `imageio-ffmpeg`, `ultralytics` are importable in a fresh environment
  (the shared venv was used read-only; dependency resolution is an orchestrator concern).
- Anything in the operator's dirty working copy beyond the diffs quoted in runtime-map B-7/B-2.
