---
authority: scoped
non_authoritative: true
---

# WT-25 — blueprint delta (operator interface & alerts)

**Ticket:** WT-25 (S-11 incidents UI). **Branch:** `codex/sentinel-25-ui-alerts`, worktree `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-25`.
**Baseline:** `e86d34b5d16abcc133ad3470c8d135d00b2423d4`, plus cherry-picked `b7d1f43` (WT-28 SC-10 fix) — recorded because it is not mine.
**Seed read:** `docs/blueprint/INDEX.md` (WT-03, commit 27c18d2) — IDs below are the registered ones. No new ID was allocated.

## U-screens

| ID | Before | After | Evidence |
|---|---|---|---|
| **U-04** Incidents & Evidence | implemented-active; limitations: "Evidence polling auto-retry hides 404s; chain errors surfaced client-side only." | **implemented-active** (same status, extended). New: incident triage workflow (جديد → قيد المعالجة → مُعلَّق → مُغلق, plus reopen; actor + ISO timestamp + bounded activity log per transition), keyboard verbs `a`/`c` in the alert queue, stacked alert notifications, visible rejected-SSE-frame counter, uncalibrated score wording. Updated limitation: **triage state is process-scoped** — it lives in the in-memory alert registry and is not written to the evidence ledger, and the recorded actor is the authenticated *role* (no per-user identity exists). | `components/incident-panel.tsx:234-254`, `components/alert-feed.tsx:58-72`, `backend/alert_triage.py`, `backend/api.py:1604-1638` |
| **U-08** App shell & global chrome | implemented-active; limitation: "Single-page shell: no per-screen URLs/deep-linking (design-map G-1)." | **implemented-active** (same status). G-1 **partially closed**: `?section=<id>` and `?id=<alertId>` are read on mount (unknown values ignored, `?fixtures=1` preserved) and `?section=` is kept in step with the visible section via `history.replaceState`. Still no real routes, so the limitation stands with "minimal deep link only". | `app/page.tsx:23-37,41,52,90-102` |
| **U-10** Shared UI data contracts | partial; limitation: "alert envelope validator rejects severity 'none' while the backend can emit it (R-3)." | **partial** — the frontend half of R-3 is fixed: `normalizeSeverity` accepts the producer's `none`/`low` band and shows the lowest displayable tier instead of dropping a **confirmed** alert; anything else is still rejected. Two additive contract deltas (SC-1/SC-4) are listed below and need integrator confirmation. | `lib/sentinel-selectors.ts:22-68,175-201` |

## F-features

| ID | Delta |
|---|---|
| **F-41** Frontend shell / dashboard | toast notifications are now a bounded queue (4 tracked, 3 visible, per-item dismiss, "+N" summary) instead of a single slot; deep-link read/write. Files: `app/page.tsx`, `components/alert-toast.tsx`. |
| **F-42** Frontend alert store + envelope validation | additive state: `triage` map (bounded 200 ids, newest-wins), `rejectedEnvelopes` counter; SSE frames are classified by a pure `parseStreamFrame` (moved to `lib/sentinel-selectors.ts` so it is node-testable); new `alert_triage` frame branch. Files: `lib/sentinel-store.tsx`, `lib/sentinel-selectors.ts`. |
| **F-44** Frontend clip/evidence UX | clip modal and escalation dialog now trap Tab focus and restore it on close (`hooks/use-modal-focus.ts`); replay meta labels its score as uncalibrated. Files: `components/clip-sidebar.tsx:72-73,154`, `components/incident-panel.tsx:91-98,308`, `components/incident-replay.tsx:164`. |
| **F-17** Alert SSE | unchanged producer; the consumer accepts one new additive frame type (`alert_triage`). |
| **F-22** Evidence ledger | unchanged. **Triage is deliberately not in the ledger** — see the U-04 limitation. |

## New contract surfaces (SC-1 / SC-4) — flagged for the integrator

1. **`GET /alerts/{alert_id}/triage`** → `{ alertId, triage: record | null }`; `record = { state, action, actor, at, history[] }`. Requires role `viewer`. `alert_triage.py:1-140`, `api.py:1604-1617`.
2. **`POST /alerts/{alert_id}/triage`** body `{ action }` (the acting role is taken from the authenticated session, never from the body) → `record`; `409` for a disallowed transition, `400` unknown action, `404` unknown alert. `api.py:1620-1638`.
3. **SSE `{"type":"alert_triage","alertId","triage"}`** on the existing `/alerts` stream (additive frame; existing consumers ignore unknown frames, the new store branch handles it).
4. **Severity tolerance**: the alert validator now maps `severity ∈ {none, low}` → `medium` (semantic change to SC-4's accepted enumeration, motivated by R-3 and the precedent in ui-contract §C-3 for overlay severity `none` → `medium`). Everything else still fails closed.

## Risks / findings

| ID | Before | After |
|---|---|---|
| **R-3** severity enumeration vs validator | partial ("two independent enumerations with no test") | **partial, mitigated frontend-side**: a regression test pins that `severity: "none"` no longer drops a confirmed alert; the backend enumeration is untouched. |
| **G-1** no URL per screen | open | partially closed (see U-08). |
| **G-10** 50-alert session cap | open | unchanged; the rejected-frame counter makes *parser* drops visible, but the cap itself is still silent (recommendation, below). |
| **N-9** source-text tests | — | this workstream added behaviour tests only (`hooks/__tests__/alert-triage.test.mjs`, `backend/tests/test_alert_triage*.py`). |

## Recommendations (not implemented) — with the candidates that justify them

1. **Evidence read-audit surface** (WT-04 commercial research, Axon `C-C1`; main-agent pointer P-2): the dossier should show who read/exported an artifact. The record belongs to WT-24/SecurityApiAudit (`agent://EvidencePipeline` coordination), not to S-11; the UI slot is ready (the triage activity log pattern).
2. **Export package with a manifest of SHA-256s** (WT-04 `C-A4`/`C-C1`): ZIP of clip + thumbnail + report + `manifest.json`; one-byte tamper must fail verification. Recorded with the E-4 round-trip test spec; not implemented for budget reasons.
3. **Full persistence for triage/notes** (WT-11 T25-7 gap 7): needs a backend store that survives restart; today the state is process-scoped and the UI says so.
4. **`calibrationStatus` / `scoreSemantics` consumption** (WT-20 additive payload fields): consumes `components/video-player.tsx` (`LiveAlert`), owned by S-09/S-12 — needs an ownership decision; until then the score caveat is static ("غير معايرة"), grounded in F-40.
5. **G-9 / G-10**: SSE stays unauthenticated (`EventSource` cannot send `X-API-Key`) and the alert buffer is still capped at 50 without a visible cap notice.

## WT-25 own-scope follow-ups

- The alert-history component is only rendered in compact mode by `components/sections/ui-monitor-section.tsx:89` (S-10); the new full-screen affordances (search, sort, expanded triage state) are reachable only if S-10 mounts the non-compact variant.
- `SEVERITY_LABEL` copies remain in S-10/S-13-owned files (`incidents-section.tsx:9`, `ui-intel-ops-section.tsx:21`, `geo-dashboard.tsx:22`, `category-filter.tsx:17-21`, `dashboard-header.tsx:32`); they should import the single source when those slices are edited.
