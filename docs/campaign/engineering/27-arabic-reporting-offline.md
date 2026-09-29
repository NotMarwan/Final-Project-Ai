---
authority: scoped
non_authoritative: true
workstream: WT-27
slice: S-14
scope: Arabic offline reporting (F-25, F-26, F-28), G-09 offline proof, R-06 VLM verdict
---

# WT-27 — Arabic reporting, offline operation, and VLM verdict (scoped evidence)

Not authoritative: this document records WT-27's measurements and stated limitations for the
integration pass. Canonical contracts live in `docs/blueprint/**` (owned by WT-01/WT-02).

## 1. Facts-first discipline (implemented + tested)

`backend/local_forensics.py` renders a deterministic offline Arabic report in three labelled
sections, so no reader has to guess what is measured and what is inferred:

| Section | Contents | Guard |
| --- | --- | --- |
| أولاً: الحقائق المسجلة | ids, camera scope, recorded time, decision state, counts, time window, evidence fingerprints | only recorded fields; missing stays missing |
| ثانياً: تفسيرات النموذج — غير مُتحقَّق منها | confidence/fusion/motion/weapon scores, labels, face-track summary | explicitly labelled unverified unless `calibrationStatus == "calibrated"` |
| ثالثاً: معلومات غير متاحة أو غير معروفة | null scores, unknown source kind, absent clip hash, no usable face frame | absence is stated, never defaulted to zero or invented |

Correctness edges covered by tests (`tests/test_local_forensics.py`, 26 cases):

- null/NaN/∞ scores → "لم تُسجَّل" (never 0); observed zero preserved (`motionScore 0` renders `0.00`).
- duplicate observation ids (across `unknownIds` and `unknownDetails`) counted once.
- stale observations: rule is *printed in the report* — any observation ending more than
  300 s before the recorded event time is marked "قديمة — مستثناة من العد" and excluded from
  the counted total; counts still cover every recorded row.
- camera scope line states the report covers this camera only; an observation row carrying a
  different `cameraId` is flagged "خارج نطاق هذه الكاميرا — مستثناة من العد" and excluded from
  the counted total (count of exclusions is stated in the facts section).
- replay/live/unverified source labels follow the product vocabulary
  (`lib/live-visual-state.ts`); absent hints stay "غير مُتحقَّق", never assumed live.
- no usable face frame → explicit Arabic absence sentence; no identity is ever invented.
- report length is bounded to the UI contract (< 100 000 chars, `lib/local-report.ts`) by display
  caps (20 ids / 20 labels / 50 rows) plus a line-boundary truncation with a visible note.

`backend/reporting.py` (PDF, F-25) uses the same split: recorded facts, evidence fingerprints
(C-C1 SHA-256 per referenced artifact), unverified model interpretations, explicit unknowns and
limitations. Model/VLM text is detected by its source and rendered **only** as
"نص النموذج — تفسير غير مُتحقَّق"; text starting with the local facts header stays in the facts
sections. Pending text reports a pending state instead of looking like analysis.
Tests: `tests/test_reporting_pdf.py` (7 cases).

Evidence fingerprints adopt C-C1 semantics
(`docs/campaign/research/04-commercial-competitors.md`): every referenced artifact's SHA-256 is
listed with its provenance; a ledger receipt can be passed via `build_local_report(alert, chain=…)`
(WT-24 receipt shape, unknown keys tolerated). Snapshot provenance wording per WT-24 correction:
"JPEG Q85 lossy re-encode of the annotated source-resolution decoded frame — not a source master,
not the clip frame" (`docs/campaign/engineering/24-evidence-quality-audit.md`).

## 2. G-09 offline proof (measured)

(a) **Zero-network unit test** — `tests/test_local_forensics.py::OfflineDeterminism` replaces
`socket.socket`, `socket.create_connection` and `socket.getaddrinfo` with raising stubs and builds
the report successfully; a determinism test asserts byte-identical output across builds and with
sockets blocked. No admin rights, no firewall change. Module import audit test asserts the module
imports stdlib only.

(b) **Integration run against the real app** — `assets/integration_offline_report.py` (untracked)
starts the FastAPI app in-process with every non-loopback socket blocked (guard verified live by a
blocked `example.com:443` connect) and exercises the report routes:

| Call | Result |
| --- | --- |
| GET /reports/local/{id} (twice) | 200, bodies byte-identical (`sha256 e34ab6e3…170b5`, 2529 chars, mode `local-evidence-summary`) |
| POST /reports/local/{id} (no key configured) | 503 "Administrator authentication is not configured" (honest) |
| POST /reports/local/{id} (in-process ADMIN_API_KEY) | 200, regenerated report byte-identical to the stored one |
| GET /download_report/{id} | 500 at baseline/SC-10 (pre-existing api.py name binding; fixed by WT-28 `1f5489a`) — direct `build_incident_pdf` call produced a 29 587-byte `%PDF` |
| GET /reports/deepseek/status | 200 `{available:false, state:"DISABLED", reason:"module 'openrouter_reporting' is not installed"}` (SC-10 pattern) |
| GET /reports/local/{unknown id} | 404 (matches ui-contract C-5 "missing") |
| GET /reports/local/{id} without `x-api-key` while auth is configured | 401 `Invalid API key` (drives the UI's reader-access copy) |

Logs: `assets/evidence/integration-with-key.log`, `assets/evidence/integration-no-key.log`.

(c) **Residual gate (not closable here)** — a true OS-level network-disabled full-demo run
(firewall rule, demo capture loop with a demo source) requires admin rights and is out of scope;
the loopback-only guard above is the maximal honest verification available in this worktree.

**Disclosure (B-3):** these runs were taken on a branch where the optional `openrouter_reporting`
module is genuinely absent (the same condition the bench harness simulates by stubbing). The
DISABLED state above is therefore measured against a real absence, not a stub. The SC-10 fix
itself is cherry-picked from `codex/sentinel-28-security-api` (`b7d1f43`), so the API starts from
committed code alone.

## 3. R-06 VLM verdict (pre-registered criteria, then measured)

Shortlist (measured metadata, 2026-09-29):

| Model | License | Size | Vision | Decision |
| --- | --- | --- | --- | --- |
| Qwen/Qwen3-VL-2B-Instruct | apache-2.0 | 4.26 GB (single safetensors) | yes | **downloaded** (preferred) |
| Qwen/Qwen3.5-2B | apache-2.0 | 4.55 GB | HF pipeline tag says `image-text-to-text` (the task brief called it text-only — measured tag differs) | not downloaded (at-most-one rule) |
| Qwen/Qwen2.5-VL-3B-Instruct | qwen-research (noncommercial, verified in model card) | 7.51 GB | yes | excluded |

Model file pinned by SHA-256 `7de1838c…977a0` (HF LFS oid, re-verified after download).

Criteria fixed before the measured run (RTX 3060 12 GB, RTX-grade fp16/bf16, detection running
concurrently):

- **adopt as optional offline analyser** if unsupported-claim rate ≤ 20 % of claims, no
  fabricated identity/crime in ≥ 2 of the fixtures judged, median latency ≤ 20 s/frame, peak
  total GPU use ≤ 10 GB, and every inference completes with all sockets blocked;
- **reject** if unsupported-claim rate > 50 %, or identity/crime fabricated in ≥ 2 fixtures, or
  the concurrent detection process is OOM-killed, or median latency > 60 s/frame;
- otherwise **adopt with guardrails** (mandatory "interpretation, not observation" labelling +
  human review), with the numbers stated;
- **blocked** only if the stack cannot run at all (recorded precisely, with the exact error).

### Measurements

**Verdict: blocked for this run** (two external gates; full detail in
`docs/campaign/experiments/2701-vlm-offline-verdict.md`).

| Item | Measured state |
| --- | --- |
| Shortlist metadata (HF API) | Qwen3-VL-2B-Instruct apache-2.0 4.26 GB vision **chosen**; Qwen3.5-2B apache-2.0 4.55 GB (HF pipeline tag `image-text-to-text`, i.e. not text-only as briefed) not downloaded; Qwen2.5-VL-3B `license_name: qwen-research` (noncommercial) excluded |
| Model transfer | 4.031 GB / 4.255 GB (115/127 blocks) at budget expiry; resumable via `assets/download_parallel.mjs`; LFS SHA-256 `7de1838c…977a0` pinned in `assets/verify_model.py` |
| Stack compatibility (no weights) | transformers 4.57.1 + torch 2.3.0+cu118: tiny `Qwen3VLForConditionalGeneration` forward pass OK; transformers 5.17 refused torch < 2.5, hence the pin; libs installed under untracked `assets/pylibs/` |
| Offline plumbing | `Qwen3VLProcessor` loads with `HF_HUB_OFFLINE=1`; 400×300 fixture → 185-token prompt (image tokens expanded) |
| Fixtures | 5 frames from the repo's committed demo clips, provenance + hand-written ground truth in `assets/vlm-fixtures/`; the 4.26 GB weights never touch git |
| RESOURCE-LOCK window | not reached (queue WT-18/WT-19 → WT-16 → WT-21 ✓ → WT-15 → WT-27); no GPU measurement was taken, so **no contended numbers are published** |
| Unsupported-claim counting | not run (needs the model); criteria pre-registered before any result was seen |

Everything needed to finish the experiment is committed or untracked-in-place; the exact command
sequence is in the EXP card. Until it runs, no VLM output is wired anywhere: the facts report
(F-28) and PDF (F-25) remain deterministic and offline-only.
