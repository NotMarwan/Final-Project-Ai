---
authority: scoped
non_authoritative: true
---

# WT-28 — API security & contract audit (slice S-19, SC-1 coordinator)

Campaign ticket WT-28 · worktree `wt-28` · branch `codex/sentinel-28-security-api` · baseline `e86d34b5d16abcc133ad3470c8d135d00b2423d4`.
**Phase A = audit only. No runtime code was changed to produce this document.** Every statement is either
`[MEASURED]` (observed from source/tests/scan output in this campaign run) or `[INFERENCE]` (reasoned from
source without an execution) or `[UNVERIFIED]` (could not be checked with the available offline tooling).
Sources cross-referenced: wt-01 `runtime-map.md`/`runtime-map-verification.md` (V-entries), wt-02
`design-map.md` (G-gaps) / `ui-contract.md` (C-contracts), and independent re-verification in this worktree.

Line numbers refer to `backend/api.py` at the pinned baseline.

---

## 1. Route-by-route table (42 routes — matches wt-01 V-06 count)

Legend — **Auth now**: who can call today (demo mode = `ADMIN_API_KEY` empty; see §1.2). **Az-before-mut**:
`security_controller.authorize()` is invoked before any state change. **Validation**: request input checks.
**Traversal**: path/identifier injection exposure. **Errors**: response error detail sanitization.
**Evidence**: control over incident media/reports/ledger (F-21…F-25).

### 1.1 The table

| # | Method / Path (F-ID) | Auth now | Az-before-mut | Validation | Traversal | Errors | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | GET `/api/webrtc/{cam_id}` (F-37) | none | n/a (read) | `cam_id` passed to untracked `go2rtc_bridge.get_whep_url` | forwarded to untracked module — trust boundary [INFERENCE] | 503/404 fixed strings ✓ | — |
| 2 | POST `/api/webrtc/{cam_id}/whep` (F-37) | **none** | **NO — mutation** (SDP offer proxied, go2rtc session created) | raw body bytes forwarded | as #1 | upstream status echoed; fixed detail ✓ | — |
| 3 | PATCH `/api/webrtc/{cam_id}/whep` (F-37) | **none** | **NO — mutation** (ICE trickle) | raw body forwarded | as #1 | as #2 | — |
| 4 | GET `/video_feed?camera_id=` (F-19) | none | n/a (read) | `camera_id` allowlist `CAMERA_SOURCES ∪ EXAMPLE_SOURCES` → 503 | ✓ allowlist | fixed string ✓ | live/replay frames unauthenticated (G-9 class) |
| 5 | POST `/webrtc/offer/{camera_id}` (F-37) | **none** | **NO — mutation** (peer connection created) | `await request.json()` then `data["sdp"]`,`data["type"]` — KeyError/JSON errors → raw 500 | `camera_id` **not allowlisted**, forwarded to `handle_offer` | **leaks internals**: `detail=f"WebRTC offer failed: {exc}"` (api.py:1572) | — |
| 6 | GET `/cameras/status` (F-03/F-38) | none | n/a | — | — | ✓ | **discloses `source` strings** (api.py:1582) — an RTSP/HTTP source URL with inline credentials would be returned verbatim [INFERENCE] |
| 7 | GET `/alerts` SSE (F-17) | none | n/a | — | — | ✓ | full alert stream incl. `clipUrl`, `faceSummary` unauthenticated (G-9) |
| 8 | GET `/detections?camera_id=` SSE (F-18) | none | n/a | `camera_id` allowlist → 503 | ✓ | ✓ | telemetry unauthenticated (G-9) |
| 9 | POST `/demo_start/{clip_id}` (F-20) | **none** | **NO — mutation** (spawns analysis worker thread) | `clip_id` allowlist `EXAMPLE_SOURCES` → 404 | ✓ allowlist; file path from server-side map | 404 fixed strings ✓ | spawns CPU/GPU worker — unauthenticated resource abuse (see §4) |
| 10 | DELETE `/demo_stop/{clip_id}` (F-20) | **none** | **NO — mutation** (stops worker) | allowlist → 404 | ✓ | ✓ | — |
| 11 | GET `/demo_video/{clip_id}` (F-20) | none | n/a | allowlist → 404 | ✓ (`Path(EXAMPLE_SOURCES[clip_id])`) | ✓ | demo media unauthenticated |
| 12 | GET `/clips/{alert_id}` (F-21/F-23) | **none** | n/a | `_validate_alert_id` regex `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$` + defense-in-depth substring check (api.py:1390-1403) | ✓ guarded | ✓ | **evidence clip readable without any auth** |
| 13 | GET `/api/clips/list` (F-23) | none | n/a | — | ✓ (glob of server dir) | ✓ | **lists all evidence metadata (ids, times, confidence) unauthenticated** |
| 14 | GET `/api/categories` (F-29) | none | n/a | — | — | 503 fixed ✓ | — |
| 15 | POST `/api/analyze` (F-29) | **none** | **NO** — nominally read-only, but **R-5: `analyze_context(weapon)` mutates the shared global `weapon_engine`**, injecting a live observation into the decision path | `AnalyzeRequest` pydantic; category enum-checked; context `parse_detection_context` | — | **echoes parser internals**: `detail=f"Malformed context: {exc}"` (api.py:1773) | — |
| 16 | POST `/api/categories/{category_id}/toggle` (F-29) | admin | **YES** (api.py:1787 before mutation; audited) | `category_id` enum; `enabled: bool` query | ✓ | 400 fixed ✓; non-ValueError exceptions unhandled → raw 500 [INFERENCE] | — |
| 17 | GET `/notifications/status` (F-32) | none | n/a | — | — | see §2.5 (`lastError` surface) | — |
| 18 | POST `/notifications/telegram/test` (F-32) | admin | **YES** (api.py:1822; audited `telegram_test`) | — | — | 503 fixed ✓ | sends external message |
| 19 | POST `/notifications/telegram/test_video?clip_id=` (F-32) | admin | **YES** (api.py:1844; audited) | `clip_id` allowlist → 404 | ✓ | ✓ | sends demo clip externally |
| 20 | GET `/reports/deepseek/status` (F-26) | none | n/a | — | — | ✓ | exposes `apiKeyPresent` flag only (by design) |
| 21 | POST `/reports/deepseek/test` (F-26) | **viewer** | called (api.py:1964) but role is viewer for a **mutation**: LLM call (`force=True`) + cache write + external spend | — | validated not needed | **echoes service internals** `detail=str(exc)` (502/503/504) | writes report cache |
| 22 | POST `/reports/deepseek/{alert_id}?force=` (F-26) | **viewer** | called (api.py:1986) — **contract C-5 documents this as admin-gated** (mismatch) | `_validate_alert_id` ✓ | ✓ | `detail=str(exc)` leak | writes report cache |
| 23 | GET `/reports/deepseek/{alert_id}` (F-26) | viewer | n/a (read) | ✓ | ✓ | `detail=str(exc)` leak | report content viewer-gated ✓ |
| 24 | GET `/download_report/{alert_id}` (F-25) | viewer | called (api.py:2015) — **GET with side effects**: writes PDF + appends evidence ledger | ✓ | ✓ | ✓ | viewer-gated ✓; ledger append idempotent by `alertId` (V-11) |
| 25 | POST `/switch_camera` (F-03) | n/a | n/a — raises 410 immediately (api.py:2072), no state change ✓ | pydantic body unused | — | ✓ | — |
| 26 | GET `/decision/config` (F-01/F-35) | viewer | n/a | — | — | ✓ | — |
| 27 | POST `/decision/config` (F-35) | admin | **YES** (api.py:2081; audited) | `DecisionConfig.from_mapping` → 422 on invalid | — | ✓ typed | — |
| 28 | GET `/reports/local/{alert_id}` (F-28) | viewer | n/a | ✓ | ✓ | ✓ | viewer-gated ✓ |
| 29 | POST `/reports/local/{alert_id}` (F-28) | admin | **YES** (api.py:2100) — **no audit record** (inconsistent with peers) | ✓ | ✓ | ✓ | writes report text |
| 30 | POST `/set_threshold` (F-35) | admin | **YES** (api.py:2111; audited) | `ThresholdRequest` 0.10–0.95 | — | ✓ | — |
| 31 | POST `/set_cooldown` (F-35) | admin | **YES** (api.py:2118; audited) | `CooldownRequest` 0–120 s | — | ✓ | — |
| 32 | GET `/download_evidence/{alert_id}` (F-24) | viewer | n/a | ✓ | ✓ | 202 writing / 500 error states ✓ | viewer-gated ✓ |
| 33 | GET `/security/status` (F-33) | none | n/a | — | — | ✓ | `enabled`+`apiKeyConfigured` flags (harmless) |
| 34 | GET `/audit/status` (F-34) | none | n/a | — | — | ✓ | **discloses audit log filesystem path** |
| 35 | GET `/audit/recent?limit=` (F-34) | **none** | n/a | `limit` clamped 1–100 ✓ | ✓ | ✓ | **audit records (roles, actions, alert ids, paths) readable unauthenticated** |
| 36 | GET `/evidence_chain/{alert_id}` (F-22) | viewer | n/a | ✓ | ✓ | ✓ | viewer-gated ✓; hash chain verified on read ✓ |
| 37 | POST `/audio/analyze` (F-31) | viewer | called (api.py:2170) — analysis only, audited | `AudioAnalysisRequest.audio_base64: str` — **no size bound** → unbounded decode [MEASURED schema] | — | ✓ | — |
| 38 | GET `/audio/status` (F-31) | none | n/a | — | — | ✓ | — |
| 39 | GET `/system/status` (F-36) | none | n/a | — | — | ✓ | exposes storage paths + engine config (demo-acceptable; note) |
| 40 | GET `/system/metrics` (F-36) | none | n/a | — | — | **failure path returns HTTP 200 `{"error": str(exc)}`** (api.py:2227) — internals leak + contract break | — |
| 41 | POST `/decision_layer/reset` (F-35) | admin | **YES** (api.py:2236; audited) | — | — | ✓ | — |
| 42 | GET `/health` (F-36) | none | n/a | — | — | ✓ (alias of #39) | — |

Counts `[MEASURED]` (grep of `security_controller.authorize` call sites, api.py:1787,1822,1844,1964,1986,2005,
2015,2076,2081,2092,2100,2111,2118,2126,2161,2170,2236 = 17 sites): **17 of 42 routes call `authorize()`;
25 never do** — reproduces wt-01 R-8 exactly. Of the 25, the mutating ones are #2, #3, #5, #9, #10
(plus #15 with its R-5 side effect and #25 dead by 410).

### 1.2 Auth semantics recap (`backend/security.py:45-70`) `[MEASURED]`

- Single `ADMIN_API_KEY` (env, or `security.api_key` in `backend/config.yml`); compared with
  `hmac.compare_digest` (constant-time) — good.
- Any valid key ⇒ server-assigned role `admin`; **client role headers confer no authority** (covered by
  `test_security_contract.py`).
- Empty key ⇒ **demo mode**: `viewer` granted to everyone; any `required_role != "viewer"` raises
  **503 "Administrator authentication is not configured"** (stable string). This is the demo-mode contract
  to preserve in Phase B.
- 401 "Invalid API key" on mismatch when configured.

### 1.3 Frontend-consumed contract mismatches

| Contract (wt-02 `ui-contract.md`) | Backend reality at baseline | Verdict |
|---|---|---|
| `GET /security/session → { role?: string }` ("admin"\|"viewer"), non-2xx = expired/invalid credential (`hooks/use-api-access.ts:29`, `components/api-access.tsx:23`) | **route does not exist → 404** | **broken (F-45)**; fix in Phase B, shape must match ui-contract exactly |
| `GET /security/status → { enabled: boolean }` | returns `{ enabled, apiKeyConfigured }` | compatible (superset) |
| Operator mutations sent with `X-API-Key` via `apiFetch` include `/demo_start`, `/demo_stop`, `/notifications/telegram/test` (ui-contract C-6 table) | demo_start/demo_stop accept the call **with or without any key** (no `authorize`) | mismatch: UI believes the key gates these; backend ignores it |
| `POST /reports/deepseek/{alertId}?force` "admin-gated server-side" (C-5) | only `viewer` required | mismatch (backend weaker than documented contract) |
| `GET /reports/local/{id}`: "401/403 = reader-access required" (C-5) | 401 on wrong key when configured; **200 for anyone when unconfigured** | partial: demo-mode read is open by design; document, don't silently change |
| `POST /notifications/telegram/test → { success?: boolean }` (C-6) | returns `{ status: "queued", telegram: … }` — no `success` field | minor mismatch (frontend treats `success?` optional) |
| Alert `severity` union `{"critical","high","medium"}` (C-1, parser fail-closed) | backend can emit `severity: "none"` (`DecisionConfig.severity_for`) | latent mismatch (wt-01 R-3); alert silently dropped client-side |
| camelCase vs snake_case | producers emit both styles (e.g. `_build_detection_payload` camelCase top-level + snake_case `window.*` keys; `decision_layer/reset` duplicates both); frontend parsers accept both aliases | no breakage, but two on-the-wire vocabularies; do not "normalize" unilaterally — parsers in `lib/` are the single normalization point |

Note: `/api/analyze`, `/api/categories/*`, `/audio/*`, `/audit/*`, `/cameras/status`, `/decision/config*`,
`/notifications/status`, `/system/metrics`, `/webrtc/*`, `/decision_layer/reset`, `/switch_camera` have
**zero frontend callers** at baseline (wt-01 V-07) — their consumers are tests/bench/external tools.

---

## 2. Secrets exposure audit (names, locations, counts, hashes only — no values)

Evidence artifact: `docs/campaign/security/28-secret-scan-summary.json` (redaction-preserving; written by a
temporary scan script since deleted; logic mirrors `bench/security_scan.py` which scans all reachable Git
blobs and never stores values).

### 2.1 Git-history scan — claim VERIFIED `[MEASURED]`

`docs/ISSUES.md:34` claims "Current Telegram and administrator credentials matched ten historical Git objects
in the previous redacted scan and still require revocation/rotation." Independent re-scan in this worktree
(shared object DB of the same repository; all local refs; 2,396 blobs / ~bytes field in the JSON):

- **10 findings on 10 distinct historical objects** — exactly reproducing the "ten historical Git objects" claim.
- Kinds (names only): `ADMIN_API_KEY` value matched in historical blobs with path hints `README.md` (×2
  objects), `frontend/README.md` (×1), `components/ai-report.tsx` (×1); `TELEGRAM_BOT_TOKEN` value matched in
  5 historical `backend/config.yml` blobs and 1 `.kilo/agent/notifications-agent.md` blob.
- `OPENROUTER_API_KEY` value did **not** match any historical object; `GROQ_API_KEY` was not usable as a
  known-value probe (absent/placeholder in the operator `.env`).
- Object ids (sha1) are listed in the JSON artifact. **Rotation of the Telegram bot token and the
  administrator key is still outstanding — owner action, not performable from this campaign** (no credential
  rotation allowed). History rewrite is likewise owner-policy.

### 2.2 Untracked config risks `[MEASURED]`

| Item | Location | Risk |
|---|---|---|
| Live secrets file | operator checkout `backend/.env` (untracked, 928 B) | source of known values; fine per-se (untracked), but see below |
| **Packaged build embeds live secrets** | operator checkout `desktop/dist/win-unpacked/backend/.env` (untracked, 786 B) — matched kinds: `ADMIN_API_KEY`, `OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`, `openrouter_token`, `telegram_token_shape` | **any distribution of `desktop/dist/` ships live credentials** (this is the ISSUES.md "OpenRouter credentials were copied into local build configuration" item, now pinned to a path). Recommendation: strip before packaging; rotate. |
| Untracked backend modules | operator checkout `backend/go2rtc_bridge.py`, `backend/openrouter_reporting.py` | per SC-10 BINDING decision: not copied into campaign branches; their import becomes optional |
| Committed identifier | `backend/config.yml` (tracked) — Telegram **chat id** at line ~21 (wt-01 §6.3) | identifier, not a token; current tree matched **no** credential values `[MEASURED]` (the current `config.yml` is clean; historical versions held the bot token) |

### 2.3 `ADMIN_API_KEY` semantics `[MEASURED]`

See §1.2. Additional notes: empty ⇒ 503 on every admin mutation (stable error contract — preserve); the key
is a **single shared administrator credential with no roles, no expiry, no revocation list, no audit of key
identity** (audit entries record `role`, not a principal). `NEXT_PUBLIC_ADMIN_API_KEY` appears in the frontend
env surface (wt-01 F-45 config key) — anything `NEXT_PUBLIC_*` is compiled into the browser bundle; verify it
is a **demo** key only before any public exposure `[INFERENCE]`.

### 2.4 Telegram / OpenRouter credential handling paths `[MEASURED]`

- Telegram: `backend/notifications.py` — `TELEGRAM_BOT_TOKEN` from env or `notifications.telegram.bot_token`
  (config.yml) (`:72-96`); token embedded into request URL `https://api.telegram.org/bot{token}/{method}`
  (`:347`, `:397`); chat id from `TELEGRAM_CHAT_ID`/config. Values are never returned by `status()` (only
  readiness flags) `[MEASURED]`.
- OpenRouter (untracked `backend/openrouter_reporting.py`, read-only inspection): `OPENROUTER_API_KEY` from
  env only (`:75`); sent as `Authorization: Bearer …` (`:234`); raised error text names the variable but not
  its value (`:133`).
- Groq: `GROQ_API_KEY` env (`api.py:315` region); client only built when set; feature flags `GROQ_ENABLED`.

### 2.5 Log files containing secrets `[MEASURED]` + one `[INFERENCE]` risk

- Tracked logs `backend-sse.{out,err}.log`, `backend-test.{out,err}.log` at repo root: present in git,
  **0 bytes at baseline** — no secrets (they are also a G-11 hygiene item for the UI workstreams).
- No log file in either checkout matched any credential value or token signature at scan time
  (scan JSON `current_file_matches`).
- **Risk (sanitization debt)**: `notifications.py:358,405` wrap network errors as
  `RuntimeError(f"Telegram request failed: {exc}")` and `:326` prints `last_error` to stdout; the same error
  object can surface as `lastError` in `status()`, which is served **unauthenticated** via
  `/notifications/status`, `/system/status`, `/health`. `urllib` errors usually do not embed the request URL,
  so a token leak via this path is **[INFERENCE: unlikely but not disproven]**; the token is nevertheless
  formatted into every request URL and nothing prevents an error message from quoting it. Phase B error
  sanitization should redact token-shaped substrings from any error surface.
- Console `print` of startup/config paths is benign (no values observed) `[MEASURED]`.

---

## 3. Dependency risk (offline review only — no manifests uploaded anywhere)

Method: lockfile review + installed-version inspection + training-data advisory knowledge. **No online
scanner was run** (policy); advisory recall past early-2025 is limited — rows are labelled.

### 3.1 Node (`package-lock.json`, lockfileVersion 3, 649 packages) `[MEASURED]`

Supply-chain posture: **no git/URL-resolved dependencies, no `http://` resolutions**; exactly 2 packages with
install scripts (`sharp`, `unrs-resolver`) — normal for this stack. Key pins: `next 16.1.6`, `react/react-dom
19.2.4`, `typescript 5.7.3`, `eslint 9.39.4`, `recharts 2.15.0`; transitive `semver 7.7.4`, `tar 7.5.15`,
`braces 3.0.3` (≥3.0.3 — past CVE-2024-4068), `cross-spawn 7.0.6` (≥7.0.5 — past CVE-2024-21538), `glob 13.0.6`.

- Next.js 16.x is beyond the offline knowledge window — **[UNVERIFIED]** against current Next advisories.
  Historical Next line advisories (CVE-2024-34351 SSRF in Server Actions; CVE-2025-29927 middleware auth
  bypass via `x-middleware-subrequest`) were fixed on 14/15 lines; whether 16.1.6 carries every fix is
  **[UNVERIFIED]**. Given the app uses middleware/auth-adjacent patterns only in `lib/api-auth.ts` (client
  side), direct exposure looks low `[INFERENCE]`.
- Action: run `npm audit` **locally** (no upload) during integration and pin any fix; not run here to avoid
  touching shared state mid-campaign.

### 3.2 Python (`backend/requirements.txt` + `backend/requirements-evidence.txt`) `[MEASURED]`

Direct pins: fastapi 0.115.0, uvicorn 0.30.0, opencv-python 4.10.0.84, numpy 1.26.4, torch 2.3.0,
torchvision 0.18.0, ultralytics 8.2.0, pyyaml 6.0.1, python-dotenv 1.0.1, groq 0.11.0, reportlab 4.2.0,
arabic-reshaper 3.0.0, python-bidi 0.6.0, google-genai 0.3.0, `openai>=1.0.0` (**unbounded**), onnxruntime
1.18.0, httpx 0.27.0, imageio-ffmpeg 0.6.0. There is **no Python lockfile** (only direct pins); the operator
venv currently resolves starlette **0.38.6**, openai 2.37.0, onnxruntime absent from venv metadata (CUDA wheel
installed under a different dist name — [UNVERIFIED]).

| Package | Finding | Confidence |
|---|---|---|
| starlette 0.38.6 (via fastapi 0.115.0) | in range of **CVE-2024-47874** (multipart DoS, fixed 0.40.0) and **CVE-2024-53981** (fixed 0.41.2). The API serves JSON only (no `UploadFile`/form routes; `python-multipart` **not installed**), so practical exposure is low, but the vulnerable code is installed | high confidence the CVEs exist; exposure assessment [INFERENCE] |
| torch 2.3.0 | **CVE-2025-32434** (`torch.load` arbitrary code execution; fixed in 2.6.0) affects this line. The runtime loads `best_model.pt`/checkpoints via torch — loading an untrusted checkpoint would execute code | high (advisory); reachability of untrusted checkpoints [INFERENCE] |
| httpx 0.27.0 | 0.27.x line had TLS-verification advisories around `verify=False` client reuse (CVE-2024-35195 family); fixed versions debated in recall → upgrade to current 0.28.x regardless | **[UNVERIFIED — advisory numbering]** |
| onnxruntime 1.18.0 | no specific advisory recalled for 1.18.0 | [UNVERIFIED] |
| ultralytics 8.2.0 | old (2024) line; ultralytics had multiple security fixes since; no specific CVE pinned here | [UNVERIFIED] |
| google-genai 0.3.0, groq 0.11.0 | very old client pins; no specific advisory; maintenance risk | [UNVERIFIED] |
| `openai>=1.0.0` | unbounded upper version = supply-chain drift; venv already at 2.37.0 while requirements say ≥1.0.0 | [MEASURED] drift |
| numpy 1.26.4 | last 1.x line; fine | — |

Recommendation order: introduce a lockfile (`pip freeze` or uv lock) for reproducibility; bump starlette/fastapi
to a ≥0.41.2-starlette resolution; plan torch ≥2.6 for CVE-2025-32434 (GPU wheel coordination needed);
pin `openai` to a tested range.

---

## 4. Mutation-safety inventory (every state-changing endpoint)

| Endpoint | Authn | Authz (role) | Idempotency | Rate/abuse exposure | Concurrent-write safety | Exact failure states today |
|---|---|---|---|---|---|---|
| POST `/api/webrtc/{cam}/whep` | none | **none** | not idempotent (SDP offer creates session) | unauthenticated session spam to go2rtc | untracked module — [UNVERIFIED] | 503 bridge absent; upstream status echoed as 4xx/5xx "WHEP negotiation failed" |
| PATCH `/api/webrtc/{cam}/whep` | none | **none** | n/a (ICE) | as above | [UNVERIFIED] | 503; "ICE trickle failed" |
| POST `/webrtc/offer/{camera_id}` | none | **none** | no | unauthenticated peer-connection creation (aiortc CPU) | [UNVERIFIED] | 501 not initialized / not available; 500 **with exception text** |
| POST `/demo_start/{clip_id}` | none | **none** (UI sends key; ignored) | guarded: `already_running` no-op ✓ | **unauthenticated GPU/CPU worker spawn** (1 thread per clip; only 3 clips ⇒ bounded) | `state.create_worker_stop_event` registry | 404 unknown clip / file missing; 200 already_running/started |
| DELETE `/demo_stop/{clip_id}` | none | **none** | yes (not_running → status) | low | stop-event registry | 404; `{"status":"not_running"}` |
| POST `/api/analyze` | none | **none** (call is viewer-class) | read-only except **R-5 shared `weapon_engine` mutation** | unauthenticated CPU inference call | shared-global mutation, no lock [INFERENCE: racy] | 503 detector missing; 400 invalid category / malformed context |
| POST `/api/categories/{id}/toggle` | key | admin ✓ | state-set (idempotent result) | low | replaces global `category_detector` — in-flight readers may use old/new mix [INFERENCE] | 400 invalid / unsupported; 503 |
| POST `/notifications/telegram/test` | key | admin ✓ | no (sends each call) | external message spam **if key leaks** | queue `maxsize=128`; `queue.Full` swallowed (R-1 class) | 503 not configured; 200 queued |
| POST `/notifications/telegram/test_video` | key | admin ✓ | no | external video send | as above | 503; 404 clip; 200 queued |
| POST `/reports/deepseek/test` | key | **viewer** (contract says admin) | `force=True` always regenerates | **external LLM spend** per call, viewer-gated only | cache write per service impl | 503 not configured (ValueError); 504 timeout; 502 runtime |
| POST `/reports/deepseek/{id}?force=` | key | **viewer** (contract says admin) | cache-hit unless `force` | LLM spend via `force=true` | cache write | 404 no alert; 502/503/504 echo internals |
| GET `/download_report/{id}` | key | viewer | **ledger append idempotent** by alertId (duplicate returns existing record) | PDF build per call (CPU) | ledger `RLock` + fsync, single-process only (V-11) | 404 no alert; 200 PDF; ledger failure would bubble as raw 500 [INFERENCE] |
| POST `/decision/config` | key | admin ✓ | state-set | low | `state.apply_decision_config` — propagation across cameras; lock semantics [UNVERIFIED under load] | 422 invalid policy |
| POST `/reports/local/{id}` | key | admin ✓ | state-set report text | low | `state.store_report_text` under lock | 404 no alert; success |
| POST `/set_threshold` | key | admin ✓ | state-set | low (but 0.10 floor enables R-3 severity "none" path) | propagates to pipelines (V-10) | 422 pydantic bounds |
| POST `/set_cooldown` | key | admin ✓ | state-set | low | as above | 422 pydantic bounds |
| POST `/decision_layer/reset` | key | admin ✓ | state-set reset | low | per-camera layers | 200 with full status |
| POST `/switch_camera` | n/a | n/a | n/a | n/a | n/a | **410** immediately (safe dead route) |
| POST `/audio/analyze` | key | viewer | read-only + audit | **unbounded `audio_base64`** ⇒ decode memory/CPU DoS | analyzer stateless? [UNVERIFIED] | 200 result; audit written |

Cross-cutting: **no rate limiting exists anywhere** (no middleware, no token bucket) `[MEASURED]`; every
mutation audited except `/reports/local` POST and the demo/webrtc/deepseek mutation set (audit coverage
inconsistent). The evidence **ledger** is safe under the API's single process (RLock + fsync + hash chain,
duplicate-id idempotent) but explicitly not multi-process (wt-01 §5) — keep the API single-instance or the
chain can fork.

---

## 5. Prioritized fix list (mapped to G-gates and F-IDs)

Gate references: **G-10** = silent-failure / health-surface gaps (wt-01 §6.1 "G-10 relevant"); **G-15** =
mutation-path validation gate (wt-01 §6.2: only `/decision/config`, `/set_threshold`, `/set_cooldown`
measured so far; full G-15 requires every mutating route to be exercised with `post_failures: []`);
G-9 = SSE unauthenticated (wt-02 §5) — listed because the SSE policy decision lands in this slice.

| P | Fix | Gate relevance | F-IDs | Notes |
|---|---|---|---|---|
| **P0** | **SC-10**: make `go2rtc_bridge` / `openrouter_reporting` imports optional; explicit **DISABLED/degraded** feature health (never silent); API starts from committed code alone | **G-10** (no silent feature loss), G-15 unblocks (server must run at all) | F-26, F-37 (+B-1/B-2) | Phase B first standalone commit; tests: import-without-modules / feature-disabled health / feature-enabled with fake module |
| **P1** | Authz-before-mutation on `POST|PATCH /api/webrtc/{cam}/whep`, `POST /webrtc/offer/{cam}`, `POST /demo_start`, `DELETE /demo_stop` (+ role: admin for infra, operator+ for demo workers), sanitized errors | **G-15** (all mutation routes), G-10 | F-20, F-37 | keep demo-mode semantics: empty key ⇒ 503 stable contract |
| **P1** | `/security/session` route matching ui-contract C-6 exactly (`{ role?: string }`, 401 on bad key) | G-15 adjacent (authenticated UX) | **F-45** | do not invent extra fields |
| **P1** | Promote `POST /reports/deepseek/test` + `POST /reports/deepseek/{id}` to **admin** per ui-contract C-5 ("admin-gated server-side") | G-15 (external-spend mutations) | F-26 | backend must match documented contract |
| **P2** | SSE policy for `/alerts` + `/detections`: chosen policy = **documented public-read + rate limiting + explicit residual-risk note** (EventSource cannot carry `X-API-Key`; tokenized alternative is ticket/cookie-based and needs UI changes owned by other workstreams) | G-9 | F-17, F-18, F-43 | do not break frontend; list minimal UI deltas if any |
| **P2** | Error sanitization sweep: `webrtc_offer` `str(exc)` detail (api.py:1572), `/system/metrics` `{"error":…}` 200 (api.py:2227), `Malformed context: {exc}` (api.py:1773), deepseek `str(exc)` details, Telegram `lastError` redaction (§2.5) | G-10 | F-37, F-36, F-29, F-26, F-32 | stable error contract per route |
| **P2** | Evidence-read access decision: `/clips/{id}` + `/api/clips/list` today unauthenticated — align with the SSE policy or gate at viewer; document whichever is chosen | G-9 class | F-23, F-21, F-44 | UI clip sidebar works unauthenticated today (F-44) — gate only with UI coordination |
| **P3** | Audit consistency: audit record for `POST /reports/local/{id}`; audit identity (which key) not just role | — | F-34, F-28 | additive |
| **P3** | `POST /audio/analyze` payload cap; `camera_id` allowlist on `/webrtc/offer/{camera_id}` | G-15 (input validation) | F-31, F-37 | |
| **P3** | `/audit/recent` + `/audit/status` + `/cameras/status` source-string disclosure: gate at viewer or redact | — | F-34, F-03 | source URLs may embed camera credentials (§1.1 #6) |
| **P4** | Secrets: rotate Telegram bot token + admin key (owner); scrub `desktop/dist/**/backend/.env` before any packaging (owner); purge historical README/config blobs per owner policy | — | — | **owner actions**; campaign cannot rotate |
| **P4** | Dependencies: starlette ≥0.41.2 resolution, torch ≥2.6 plan, Python lockfile, pin `openai` | — | F-02/F-47 adjacent | §3 |
| **P5** | Severity contract R-3 (`"none"` vs parser union) — coordinate with UI parsers before any producer change | — | F-42, F-15 | parser is normalization authority |

Out of scope here by contract: UI component changes (owned by UI workstreams), retention/rotation policy,
ledger multi-process support.

---

## 7. Phase B — implemented fixes (this branch `codex/sentinel-28-security-api`)

Phase B started after the reconciled seed landed at wt-03 (commit `27c18d2`); the registered IDs used here
(F-20, F-26, F-33, F-34, F-37, F-45, SC-1, SC-10, S-19) come from `wt-03/docs/blueprint/INDEX.md`.

### 7.1 Commits and per-hunk notes (for the integrator)

| Commit | Subject | api.py hunks (baseline line refs → new) |
|---|---|---|
| `1928e71` | docs(security): WT-28 Phase A audit | `docs/campaign/security/28-api-security-audit.md`, `28-secret-scan-summary.json` (no runtime code) |
| `b7d1f43` | fix(api): SC-10 optional imports + DISABLED health | import block: `import sys` (:13) + bootstrap `sys.path.insert(0, str(BASE_DIR))` (:34-40); go2rtc optional `Go2RTCBridge=None`/`_GO2RTC_IMPORT_ERROR` (:56-68); openrouter optional + `_DisabledDeepSeekReportService` (:313-364); `_init_engines` guard (:399-403); new `feature_health()` (:407-428) and `_webrtc_bridge_unavailable_detail()` (:430-434); `/system/status` `"features"` key (:2405); 3 WebRTC routes use the new 503 detail (:1619, :1628, :1641 baseline-equivalent lines) |
| `7b09b46` | fix(api): authorize before mutation + sanitized errors | `/api/webrtc/{cam}/whep` POST+PATCH authorize (:1679, :1692 — baseline 1529/1541); `/webrtc/offer/{cam}` authorize + camera allowlist + sanitized 500 (:1713, :1733 — baseline 1560); `demo_start`/`demo_stop` authorize(viewer) + `Request` param (:1820, :1846 — baseline 1646/1671); DeepSeek POSTs viewer→admin (:2139, :2164 — baseline 1962/1983); DeepSeek error mapping sanitized (both blocks); `/system/metrics` sanitized failure (:2429); `/api/analyze` generic 400 (:1943); `AudioAnalysisRequest.max_length` (:468); `POST /reports/local/{id}` audit record (:2287) |
| `b4d10e1` | feat(api): GET /security/session (F-45) | new route (:2329-2340) |
| `feat(api): bound public read streams + packaging guard` (this section's commit) | feat(api): bounded public read streams + packaging guard + docs | `_STREAM_LIMITS`/`_acquire_stream_slot`/`_release_stream_slot` (:1626-1664); `/video_feed` (:1704-1708), `/alerts` (:1748), `/detections` (:1798) acquire and release; guards/tests + this section |
| `fix(api): bind build_incident_pdf at module scope` (follow-up, WT-27/WT-30 defect) | fix(api): /download_report 500 NameError | import block: module-scope `from .reporting import build_incident_pdf` with the tracked-module fallback (:70-77). Pre-existing defect (not SC-10): the route called `build_incident_pdf` as a global while `_get_imports()` only bound it in `locals()` → HTTP 500 `NameError` at api.py:2222. Reported by WT-27; ownership of api.py kept by S-19/SC-1 (reporting.py untouched). |

All api.py edits are additive or single-line in-place changes inside the functions listed; **no
capture-loop, queue/IPC, `yolo_onnx`, or `pipeline_capture` code was touched** (WT-14/WT-16 ownership
boundary respected). Other importers of the two optional modules: only `bench/runtime.py` (it *stubs* them
when absent, `bench/runtime.py:235/263`) — left untouched; no tracked module imports them directly besides
`backend/api.py`.

### 7.2 Decisions

- **SC-10 (BINDING orchestrator decision)**: optional + explicit DISABLED health. Implemented as above.
  Acceptance command `import backend.api` from the repo root now succeeds with no untracked modules
  (see §7.4). Root cause of the *first* baseline import failure was not the optional modules but
  `backend/person_detector.py:12 from yolo_onnx import ...` (absolute sibling import) — fixed by the
  one-line backend-dir sys.path bootstrap in api.py, **not** by editing `person_detector.py`
  (recommendation for integration: convert backend modules to package-relative imports and drop the
  bootstrap; see §7.5).
- **Demo-worker tier**: `POST /demo_start`, `DELETE /demo_stop` use `authorize(required_role="viewer")`
  instead of `admin`. Reason: demo-clip analysis is the reference demo's only data source (no camera
  device, demo mode = no `ADMIN_API_KEY`); an admin gate would answer 503 to the flagship demo while
  adding nothing in the key-configured case (viewer already rejects a missing/wrong key with 401 there).
  This still fixes the audit finding (the backend now validates the key the UI sends). One-line change to
  make it strict `admin` — but that requires the UI delta listed in §7.5.
- **DeepSeek regeneration = admin**: promoted to match ui-contract C-5 ("admin-gated server-side") and the
  external LLM spend; `GET`s stay viewer.
- **SSE/stream policy (G-9)**: chosen = *documented public read + rate limiting* (not tokenized access).
  `/alerts` and `/detections` (EventSource cannot send `X-API-Key`) and the MJPEG fallback are public
  reads bounded by a global concurrency cap (SSE 32, MJPEG 64) plus a per-client connection-rate limit
  (60/min SSE, 120/min MJPEG), answering HTTP 429 with `Retry-After`. Slots are released in each
  generator's `finally`. Residual risks (documented, not fixed): (a) an on-network attacker can read the
  live alert/telemetry streams while holding a slot; (b) the cap is per-process — multi-worker deployment
  multiplies it; (c) no per-camera read restriction; (d) the `_stream_attempts` map grows with distinct
  client keys (bounded by connection rate, no eviction). A tokenized EventSource alternative
  (query token / short-lived ticket) needs frontend changes in `hooks/use-detection-stream.ts` +
  `lib/sentinel-store.tsx` and is deferred to the UI workstreams.
- **Error sanitization**: internals removed from `webrtc_offer` 500, `/system/metrics` failure payload,
  `/api/analyze` generic parse error, and DeepSeek timeout/runtime mapping. `ValueError` details from the
  DeepSeek service are intentionally kept — they are the documented "not configured / DISABLED" message
  the UI shows (`components/ai-report.tsx`) and the SC-10 explicit-disabled contract.
- **Not changed (deliberately)**: `/clips/{id}` and `/api/clips/list` remain public reads (F-44's clip
  sidebar depends on them); `/audit/recent` + `/audit/status` remain public (F-34 has no frontend
  consumer; gating them is a policy call for the integrator, listed in §7.5); `notifications.py` untouched
  (its `status()` never exposes `lastError` — the token-in-log risk is stdout-only, see §2.5).

### 7.3 Security action items (owner-level; cannot be performed by this campaign)

1. **Rotate before any distribution**: the Telegram bot token and the administrator API key must be
   revoked/rotated before this artifact is distributed or deployed. Ten historical Git objects still carry
   those current values (object ids in `28-secret-scan-summary.json`); rotation is the only remediation
   that removes their value (history rewrite is a separate owner decision).
2. **Strip-before-package rule (BINDING, WT-30 handoff)**: `desktop/dist/**` must never contain `backend/.env`
   or any credential-shaped value. The operator checkout today has
   `desktop/dist/win-unpacked/backend/.env` carrying live `ADMIN_API_KEY`, `OPENROUTER_API_KEY`,
   `TELEGRAM_BOT_TOKEN` and an `sk-or-v1-` token. Guard implemented in this branch (§7.4,
   `test_packaging_guard_*` — scanning `desktop/dist` when present; it currently FAILS in the operator
   checkout, which is the intended signal).
   **Proposed `docs/ISSUES.md` wording (for DocsSeed/WT-30, canonical edits are not mine):**
   > Packaged desktop builds leak credentials: `desktop/dist/**/backend/.env` is copied into the
   > distribution and contains the live administrator key, Telegram bot token and OpenRouter key. Packaging
   > must exclude `.env` files (and any credential-shaped value) from the staged tree; the exposed
   > credentials require rotation before distribution. A packaging guard test
   > (`backend/tests/test_authenticated_routes.py::test_packaging_guard_*`) fails when a staged
   > distribution contains dotenv files or token-shaped values.
3. **Dependencies (offline review, §3)**: resolve starlette ≥ 0.41.2; plan torch ≥ 2.6 (CVE-2025-32434,
   `torch.load`); add a Python lockfile; pin `openai`.

### 7.4 Validation actually run (this branch, real outputs)

| Command | Result |
|---|---|
| `py -3.14 -m pytest backend/tests/test_security_contract.py backend/tests/test_authenticated_routes.py -q` | **49 passed, 1 skipped** (skip = no staged `desktop/dist` in this worktree; 1 warning = `reporting.py:253 datetime.utcnow()` deprecation, WT-27's file). The 49th test is the `/download_report` regression: before the fix it failed exactly as WT-27 measured (`NameError: name 'build_incident_pdf' is not defined`, backend/api.py:2222 → HTTP 500), after the module-scope binding it returns 200 with a real `%PDF` body via the reportlab builder. |
| baseline (pinned `e86d34b`, before Phase B): same command | `test_security_contract.py` alone: **4 passed**; `test_authenticated_routes.py` did not exist; `py -3.14 -c "import backend.api"` → **ModuleNotFoundError: No module named 'person_detector'** (plus, under the venv, the same) |
| `py -3.14 -c "import backend.api"` (after SC-10) | exit 0; `Go2RTCBridge None`; `DeepSeekReportService None`; `deepseek_service.status()` → `{'available': False, 'state': 'DISABLED', 'apiKeyPresent': False, 'reason': "…module 'openrouter_reporting' is not installed…"}`; `feature_health()` → both DISABLED with reasons; routes 46 (42 API + docs/openapi) |
| `py -3.14 -m pytest backend/tests/test_authenticated_routes.py -q` | 36 → 43 → 48 → **49 passed** across the Phase B commits and the `/download_report` follow-up |
| wide tracked-API check (`test_api_sprint`, `test_api_categories`, `test_api_runtime_config`, `test_intrusion_api_contract`, `test_demo_clips`) | **26 passed, 1 failed, 18 errors** — all failures pre-existing at baseline per wt-01 N-10/N-13 (`face_engine` attribute in the mock-based intrusion contract tests; AVI fixture path in `test_demo_clips`). No failure references a route or model changed here. |
| `node scripts/docs-contract.mjs --check` (Phase A commit; this branch's checker predates DocsSeed's `scoped_artifacts` allowlist) | **exit 1**, exact text: `Unregistered active document: docs/campaign/security/28-api-security-audit.md` / `Stale generated document: docs/SOURCE-MANIFEST.json` / `Stale generated document: docs/CURRENT.md`. The two "Stale" lines are pre-existing at the pinned baseline (wt-01 V-16); the "Unregistered" line is the expected pre-allowlist behaviour for a scoped `docs/campaign/**` file (frontmatter `authority: scoped` / `non_authoritative: true` is present). No checker or authority file was modified. |
| `npm run docs:sync` / `docs:check` | not run: no generated-doc source changed (`docs/SOURCE-MANIFEST.json`, `docs/CURRENT.md`, `docs/DESIGN.md` untouched; the audit artifact is scoped, not generated) |

**Live ASGI smoke run (committed code alone, repo venv, capture loop off, no `ADMIN_API_KEY`)** —
`venv/Scripts/python.exe -m uvicorn api:app --app-dir backend --port 8123` (engines initialized: `device: cuda`,
`threshold 0.45`); probes:

| Probe | Observed |
|---|---|
| `GET /security/status` | 200 `{"enabled":false,"apiKeyConfigured":false}` |
| `GET /security/session` (no key / any key) | 200 `{"role":"viewer"}` (demo mode) |
| `GET /system/status`, `GET /health` | 200; `features.go2rtcBridge.state="DISABLED"`, `features.openrouterReporting.state="DISABLED"` with reasons |
| `GET /reports/deepseek/status` | 200 `{"available":false,"state":"DISABLED","apiKeyPresent":false,"reason":"…module 'openrouter_reporting' is not installed…"}` |
| `GET /api/webrtc/CAM-01` | 503 `{"detail":"WebRTC bridge DISABLED: go2rtc_bridge module is not installed"}` |
| `POST /set_threshold` (no key / arbitrary key) | 503 `{"detail":"Administrator authentication is not configured"}` (stable demo-mode contract) |
| `POST /api/webrtc/CAM-01/whep` (no key) | 503 admin gate (demo mode) |
| `POST /reports/deepseek/test` (no key) | 503 admin gate (proves the C-5 promotion) |
| `POST /demo_start/NOPE` (no key) | 404 `Unknown demo clip` → demo-mode viewer tier preserved (no 503) |
| `GET /clips/nonexistent-alert` | 404 (public evidence read, documented) |
| `GET /audit/status` | 200 (audit logger initialized) |
| `GET /openapi.json` | 39 paths; `/security/session` registered |


### 7.5 Handoff notes for the integrator / other workstreams

1. **`backend/person_detector.py:12`** (`from yolo_onnx import ...`, absolute) and similar absolute sibling
   imports are why `backend.api` was not importable as a package. Recommendation at integration: convert
   the backend modules to package-relative imports (with a local fallback) and delete the sys.path
   bootstrap added here. Not done in this slice to avoid touching another slice's file (person_detector.py
   is F-10 / S-04 territory).
2. **UI deltas required** by the stricter gating choices (owned by the UI workstreams; no frontend file was
   changed here):
   - If the orchestrator wants `demo_start`/`demo_stop` at admin tier, `app/page.tsx:68/75` must gate the
     calls on the access state or surface the 503 (currently the errors are swallowed).
   - DeepSeek regeneration is now admin-tier per C-5: `components/ai-report.tsx` regenerate must require a
     verified session (it already sends `X-API-Key` via `apiFetch`).
3. **Deferred policy calls**: whether `/clips/{id}`, `/api/clips/list`, `/audit/recent` should be
   viewer-gated (F-44 and F-34 consumers must be updated first).
4. **`docs/ISSUES.md`**: apply the §7.3 wording via DocsSeed/WT-30 (canonical-doc authority is not mine).

### 7.6 Blueprint delta (registered IDs only)

| ID | Registered status | Status on this branch | Note |
|---|---|---|---|
| SC-10 | proposed | **implemented-active** | optional imports + explicit DISABLED health + tests |
| F-45 | partial | **implemented-active** | `/security/session` route matches ui-contract C-6 shape |
| F-33 | implemented-active | implemented-active (strengthened) | 17 → 30 authorize call sites in api.py; demo/webrtc mutations covered |
| F-34 | implemented-active | implemented-active (strengthened) | audit record added to `POST /reports/local/{id}` |
| F-20 | implemented-active | implemented-active (auth) | `demo_start`/`demo_stop` now authenticate (viewer tier, see §7.2) |
| F-26 | unverified | **unverified (now explicit)** | absent module → DISABLED status/generate contract instead of an import failure |
| F-37 | disconnected | **disconnected (now explicit)** | absent bridge → DISABLED health + explicit 503 detail; routes gated admin |
| S-19 | partial | **implemented-active for the audited surface** | audit + fixes + tests; residual risks listed in §7.2/§7.5 |
| G-9 (wt-02 gap) | open | **bounded + documented** | public read + 429 rate limiting; tokenized alternative deferred |
| G-10 (wt-01 §6.1) | open | improved | optional-feature availability now has a server-side signal (`/system/status.features`, `/reports/deepseek/status`) |
| F-25 | implemented-active (registered) | **partial at baseline, fixed here** | `/download_report/{id}` answered HTTP 500 `NameError: build_incident_pdf` at the pinned baseline (pre-existing, not SC-10 — reported by WT-27). **Registry correction for the integrator: F-25 = "partial: route broken at baseline, fixed by the `fix(api): bind build_incident_pdf at module scope` commit on this branch"** |

No new IDs were allocated; no UI (U-*) files were touched.

---

## 6. Limitations

**Phase A (audit)**
- Audit-only; **no runtime behavior was exercised** (server not started in Phase A). Route semantics read from
  source; interplay claims under concurrency are `[INFERENCE]` except where a cited test covers them.
- Secret scan covers all locally reachable Git blobs and current files listed in the JSON artifact; does not
  cover remote-only refs, unreachable objects, LFS payloads, or archives. Matching used the current `.env`
  values plus public token signatures — unknown/other-site credentials are not detectable.
- Dependency advisories recalled from offline knowledge (through early-2025 window); no online scanner run;
  2025-2026 advisories for the newer lines (Next 16, React 19, starlette post-0.41, onnxruntime, ultralytics)
  are **[UNVERIFIED]**.
- The two untracked modules (`go2rtc_bridge.py`, `openrouter_reporting.py`) were inspected read-only for
  credential-handling and interface facts only; they were **not** copied anywhere.

**Phase B (fixes)**
- Behaviour is proven by unit/route tests plus one live ASGI smoke run; the WebRTC/aportc offer path, the
  go2rtc WHEP proxy, real Telegram delivery and real LLM reporting remain **unexercised** (their modules are
  absent by design — that absence is now explicit rather than an import failure).
- The stream rate limiter is per-process and in-memory; it was unit-tested through the helpers and the
  route-level 429 path, but no long-running load test was performed.
- The packaging guard test skips when `desktop/dist` is absent (this worktree); in the operator checkout it
  is expected to FAIL on `desktop/dist/win-unpacked/backend/.env` (measured during Phase A scanning).
- `docs/campaign/security/28-api-security-audit.md` is a scoped, non-authoritative artifact
  (`authority: scoped`); it must not be read as status authority. `docs:check` on this branch predates the
  `scoped_artifacts` allowlist and therefore still reports it as an unregistered active document.
