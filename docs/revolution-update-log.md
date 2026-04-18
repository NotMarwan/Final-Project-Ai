# AI Sentinel Revolution Update Log

This file is the official running log for the new project direction.
Every major decision and implementation step must be appended here as a dated update.

## Current Strategic Direction

Primary specialization focus:

- Face intelligence pipeline for real events.
- Known-person identification (pre-registered attendees).
- Unknown-person indexing with stable numeric IDs per event/session.

## Feature Decision Register

| Feature | Decision | Status | Reason |
|---|---|---|---|
| Motion Masks (`#7`) | Deferred for now | On hold | Camera angles are changing frequently during the trial phase. |
| Roles/Permissions (`#14`) | Keep minimal mode | Simplified | We are still in testing and need fast iteration. |
| VLAN isolation (`#16`) | Deferred for now | On hold | Not needed in current experimental stage. |
| License Plate Recognition (`#18`) | Removed from near-term scope | Dropped (current phase) | Focus budget and effort on face specialization. |
| Face Recognition (`#19`) | Elevated to core specialization | Active priority | High value for documented events and meetings. |

## Face Intelligence Scope (Phase Focus)

### Goal A: Known-Person Recognition

- Register documented participants before the event (government events, meetings, official sessions).
- Detect when a known person appears in live stream or recorded event.
- Show recognized name/label with confidence.

### Goal B: Unknown-Person Numbering

- Detect every face in the frame.
- Assign each unknown face a numeric ID (example: `U-01`, `U-02`, `U-03`).
- Keep each unknown ID stable across nearby frames in the same event/session.
- Reset/rebuild IDs when a new event/session starts.

### Goal C: Event-Level Face Summary

- For each alert/event, store:
  - known people seen
  - unknown people count
  - unknown IDs that appeared
  - first/last seen timestamps
- Include this summary in incident review and reports.

## Technical Blueprint (Implementation Order)

### Step 1: Face Pipeline Skeleton

- Add a dedicated face module and clear interfaces:
  - `detect_faces(frame)`
  - `extract_embedding(face_crop)`
  - `match_known_face(embedding)`
  - `assign_unknown_id(embedding, track_hint)`
- Keep it configurable and optional by feature flag.

### Step 2: Known Registry

- Add local registry store for known people:
  - person ID
  - display name
  - optional role/title
  - one or more reference embeddings/images
- Add update endpoints or admin scripts for registry maintenance.

### Step 3: Unknown ID Tracker

- Add short-term association logic to keep unknown IDs stable.
- Start simple with IoU + embedding distance heuristics.
- Add TTL rules for when an unknown identity expires.

### Step 4: API and Event Enrichment

- Attach face findings to event payloads:
  - recognized list
  - unknown IDs list
  - counts and confidence fields
- Expose in `/alerts`, `/system/status`, and report generation flow.

### Step 5: UI Rendering

- Draw known labels and unknown numeric tags.
- Show a compact "faces in event" panel:
  - recognized names
  - unknown IDs count
- Keep design minimal during the trial phase.

### Step 6: Quality and Guardrails

- Add confidence thresholds and anti-flicker smoothing.
- Add policy switch to disable identity labeling when required.
- Log recognition actions to audit trail.

## Update Log

### Update 001 - 2026-04-18

Direction change accepted and activated:

- Focus moved to face specialization as primary expansion path.
- Motion masks deferred due to moving camera positions in test phase.
- Roles kept in simplified mode for faster iteration.
- VLAN deferred for now.
- License plate feature removed from current phase.
- Started official revolution log to track every upcoming step.

Immediate next implementation target:

- Build Step 1 (face pipeline skeleton) with placeholders and config wiring.

### Update 002 - 2026-04-18

Step 1 implementation delivered:

- Added `backend/face_intel.py` with explicit skeleton interfaces:
  - `detect_faces(frame)`
  - `extract_embedding(face_crop)`
  - `match_known_face(embedding)`
  - `assign_unknown_id(embedding, track_hint)`
- Added a configurable `FaceIntelConfig` with env overrides.
- Added optional OpenCV Haar detector mode for pilot testing (`detector_backend: haar`).
- Added known-registry loader from local JSON file path.
- Added unknown-person numeric indexing (`U-001`, `U-002`, ...) with short-term stability logic.
- Enriched alert payloads with `faceSummary`.
- Added API endpoints:
  - `GET /face/status`
  - `POST /face/session/reset`
- Added face subsystem to `GET /system/status`.
- Added configuration wiring in:
  - `backend/config.yml`
  - `backend/.env.example`
- Added starter registry template:
  - `backend/known_faces_registry.example.json`

Notes:

- Face module is feature-flagged and safe by default (`FACE_INTEL_ENABLED=false`).
- Roles remain simplified as requested.
- Deferred items remain deferred with no change in decision.

Immediate next implementation target:

- Build Step 2 (Known Registry management): add maintenance endpoint/script and registration workflow for documented attendees.

### Update 003 - 2026-04-18

Step 2 implementation delivered:

- Implemented registry CRUD and enrollment in `backend/face_intel.py`:
  - `list_known_people(include_embeddings=False)`
  - `get_known_person(person_id, include_embeddings=False)`
  - `upsert_known_person(person_id, display_name, role)`
  - `delete_known_person(person_id)`
  - `clear_person_embeddings(person_id)`
  - `enroll_person_from_base64(person_id, image_base64, display_name, role)`
- Added persistent registry save/load with safe JSON serialization for embeddings.
- Added enrollment flow from `base64` image payload with automatic face crop fallback.
- Added API models in `backend/api.py`:
  - `FacePersonUpdateRequest`
  - `FaceEnrollRequest`
- Added new endpoints:
  - `GET /face/registry`
  - `GET /face/registry/{person_id}`
  - `PUT /face/registry/{person_id}`
  - `DELETE /face/registry/{person_id}`
  - `DELETE /face/registry/{person_id}/embeddings`
  - `POST /face/registry/{person_id}/enroll`
- Added audit log records for registry changes and enrollment actions.

Validation performed:

- Syntax compile for `backend/face_intel.py` and `backend/api.py`.
- Runtime check for upsert and enrollment methods.
- Runtime check confirmed face status remains available through system status.

Immediate next implementation target:

- Build Step 3 (unknown ID stabilization upgrade): add track hints (bbox IoU) and stronger anti-flicker smoothing for numbered unknown faces.

### Update 004 - 2026-04-18

Step 3 implementation delivered:

- Upgraded unknown-face tracking to use hybrid matching:
  - embedding distance
  - bounding-box IoU (`track_hint`)
  - weighted combined scoring
- Added anti-flicker reuse rules so unknown IDs do not switch quickly on small movement:
  - direct distance gate
  - relaxed distance with strong IoU gate
  - minimum IoU gate for spatial continuity
- Added per-track fields for stabilization:
  - last bbox
  - hit streak
  - first/last seen frame
- Added stable processing order of detections (`y,x` sorted) to reduce numbering jitter.
- Exposed new tuning parameters in config/env/status:
  - `unknown_match_relax_factor`
  - `unknown_min_iou`
  - `unknown_strong_iou`
  - `unknown_embedding_weight`
  - `unknown_iou_weight`

Validation performed:

- Syntax compile passed for face and API modules.
- Runtime probe passed for face status.
- Unit-style runtime check passed for unknown ID reuse under moving bbox conditions.

Immediate next implementation target:

- Build Step 4 polish: attach richer face-event metadata (first_seen/last_seen per unknown ID) into alert payload and report pipeline.

### Update 005 - 2026-04-18

Step 4 polish delivered:

- Enriched face-event metadata in `backend/face_intel.py`:
  - `unknownDetails` now includes:
    - `id`
    - `firstSeenFrame`
    - `lastSeenFrame`
    - `durationFrames`
    - `firstSeenAt`
    - `lastSeenAt`
    - `hitStreak`
    - `lastBbox`
  - Added `recognizedCount` to frame summary.
- Attached richer face payload in alerts from `backend/api.py`:
  - `frameIndex`
  - `recognizedCount`
  - `unknownDetails`
- Extended PDF report output in `backend/reporting.py`:
  - face metadata rows (recognized/unknown counts and labels)
  - unknown timeline section (`first/last seen`, frames, hits)
- Extended evidence ledger in `backend/evidence.py` with face fields:
  - `faceRecognizedCount`
  - `faceUnknownCount`
  - `faceUnknownIds`

Validation performed:

- Syntax compile passed.
- Runtime checks confirmed new face metadata keys in summaries and status.
- Unknown-ID stability checks remain passing after metadata enrichment.

Immediate next implementation target:

- Build Step 5: render known labels and unknown numeric tags clearly in frontend live view and incident panel.

### Update 006 - 2026-04-18

Step 5 UI rendering delivered:

- Extended frontend alert payload typing in `components/video-player.tsx`:
  - added `FaceSummaryPayload`, `FaceObservation`, and `FaceUnknownDetail` interfaces
  - connected optional `faceSummary` into `LiveAlert`
- Added live-view face overlay card in `components/video-player.tsx` (during active alert):
  - shows `Known` and `Unknown` counts
  - shows recognized labels
  - shows unknown numeric IDs (`U-...`)
- Added dedicated Face Intelligence section in `components/incident-panel.tsx`:
  - status badge (`ACTIVE/OFF`)
  - total/known/unknown metrics
  - recognized people chips
  - unknown IDs chips
  - compact unknown timeline list (`durationFrames`, `hitStreak`)
- Aligned frontend API base fallback to the active backend default (`http://localhost:8002`) for consistent local testing.

Validation performed:

- Frontend production build passed:
  - `npm run build` completed successfully.

Immediate next implementation target:

- Build Step 6: quality guardrails (confidence gates, anti-flicker refinements, identity-label policy toggle, and expanded recognition audit trail).

### Update 007 - 2026-04-18

Step 6 quality and policy guardrails delivered:

- Strengthened known-face guardrails in `backend/face_intel.py`:
  - added `known_min_confidence` gate before accepting known matches
  - added known-face anti-flicker stabilization using strong IoU + relaxed threshold window
  - added known-track TTL pruning (`max_known_age_frames`) to keep runtime state clean
- Added face identity policy controls:
  - runtime toggle for identity labeling (`identityLabelingEnabled`)
  - when disabled, known labels are masked to neutral aliases (`K-001`, `K-002`, ...)
- Added configurable recognition audit behavior:
  - enable/disable recognition audit stream
  - configurable audit cooldown seconds to reduce noisy repeated entries
- Added new admin endpoint in `backend/api.py`:
  - `POST /face/policy` to update:
    - `identity_labeling_enabled`
    - `recognition_audit_enabled`
    - `recognition_audit_cooldown_sec`
- Expanded audit trail in capture pipeline:
  - logs known-person sightings (`face_known_seen`) with cooldown dedupe
  - logs unknown-ID sightings (`face_unknown_seen`) with cooldown dedupe
  - enriches `alert_detected` audit details with face totals and labeling-policy state
- Extended configuration surface:
  - `backend/config.yml` and `backend/.env.example` now include new known-match and policy/audit keys.

Validation performed:

- Syntax compile passed:
  - `python -m py_compile backend/face_intel.py backend/api.py`

Immediate next implementation target:

- Step 7 candidate: add operator-side controls in frontend settings for face policy toggles and audit cooldown with safe defaults.

### Update 008 - 2026-04-18

Step 7 operator controls delivered:

- Added frontend policy controls in `components/incident-panel.tsx`:
  - toggle identity labeling (`ON` / `MASKED`)
  - toggle recognition audit (`ENABLED` / `PAUSED`)
  - audit cooldown slider (seconds)
- Wired controls to backend policy endpoint:
  - `POST /face/policy`
  - sends:
    - `identity_labeling_enabled`
    - `recognition_audit_enabled`
    - `recognition_audit_cooldown_sec`
- Added initial policy sync on UI load:
  - reads `GET /face/status`
  - hydrates current policy values into sliders/toggles.
- Improved face card visibility:
  - Face Intelligence panel now shows an explicit identity mode badge (`IDENTITY ON` / `MASKED`).
- Extended face payload typing in `components/video-player.tsx`:
  - added `identityLabelingEnabled` to `FaceSummaryPayload`.

Validation performed:

- Frontend production build passed:
  - `npm run build`

Immediate next implementation target:

- Step 8 candidate: add lightweight integration tests for `/face/policy` and face-summary masking behavior to lock regression risk.

### Update 009 - 2026-04-18

Step 8 integration tests delivered:

- Added backend test suite folder:
  - `backend/tests/`
- Added lightweight integration tests in:
  - `backend/tests/test_face_policy.py`
- Coverage included:
  - `/face/policy` runtime update flow (identity labeling toggle, recognition audit toggle, cooldown update)
  - `GET /face/status` policy reflection after update
  - face-summary masking behavior via `_public_face_summary(...)` when identity labeling is disabled
- Test harness safeguards:
  - disables capture loop in test runtime (`AI_SENTINEL_ENABLE_CAPTURE_LOOP=false`) so tests stay fast and deterministic.

Validation performed:

- Test run passed:
  - `python -m unittest discover -s backend/tests -p "test_*.py" -v`
  - 2 tests passed.

Immediate next implementation target:

- Step 9 candidate: add edge-case tests (empty policy payload -> `400`, alias consistency across multiple known observations, and audit cooldown boundary behavior).

### Update 010 - 2026-04-18

Step 9 edge-case tests delivered:

- Expanded `backend/tests/test_face_policy.py` with additional coverage:
  - empty `/face/policy` payload returns `400`
  - alias consistency when multiple known observations exist in one summary
  - audit dedupe cooldown behavior in `_emit_face_audit_events(...)`
- Kept tests deterministic using:
  - patched clock values for cooldown boundary checks
  - patched audit logger calls for exact event-count assertions.

Validation performed:

- Test run passed:
  - `python -m unittest discover -s backend/tests -p "test_*.py" -v`
  - 5 tests passed.

Immediate next implementation target:

- Step 10 candidate: expose a lightweight `npm` script or backend command alias for running only face-policy tests during rapid iteration.

### Update 011 - 2026-04-18

Step 10 rapid-test command delivered:

- Added dedicated script in `package.json`:
  - `test:face-policy`
  - command: `python -m unittest discover -s backend/tests -p "test_face_policy.py" -v`
- This gives a fast one-command loop for policy/masking regression checks without running full frontend build.

Validation performed:

- Script run passed:
  - `npm run test:face-policy`
  - 5 tests passed.

Immediate next implementation target:

- Step 11 candidate: add a minimal CI workflow job to run `npm run test:face-policy` on pushes/PRs.

### Update 012 - 2026-04-18

Step 11 CI workflow prepared (push permission blocked):

- Added local GitHub Actions workflow draft:
  - `.github/workflows/face-policy-tests.yml` (local draft)
- Workflow draft behavior:
  - triggers on `push` and `pull_request`
  - sets up Python 3.11 + Node 20
  - installs lightweight Python dependencies required by backend import path
  - runs `npm run test:face-policy`
- Push blocker encountered:
  - remote rejected workflow-file update because the active token does not have `workflow` scope.

Validation performed:

- Local command passed:
  - `npm run test:face-policy`
  - 5 tests passed.

Immediate next implementation target:

- Step 12 candidate: push workflow file after enabling token `workflow` scope, then add path filters.

### Update 013 - 2026-04-18

Step 12 policy persistence delivered:

- Added persistent face-policy overrides in `backend/face_intel.py`:
  - new config key: `policy_overrides_path`
  - policy updates from `/face/policy` are now saved to JSON on disk
  - overrides are reloaded automatically on engine initialization
- Expanded policy status payload:
  - `policy.policyOverridesPath` is now exposed in `/face/status`
- Extended backend configuration surface:
  - `backend/config.yml` includes `face_intel.policy_overrides_path`
  - `backend/.env.example` includes `FACE_POLICY_OVERRIDES_PATH`
- Added dedicated persistence test:
  - `backend/tests/test_face_policy_persistence.py`
  - verifies save + reload behavior across engine re-instantiation
- Updated rapid test command:
  - `package.json` script `test:face-policy` now runs `test_face_policy*.py`
  - includes both policy API tests and persistence test.

Validation performed:

- Syntax compile passed:
  - `python -m py_compile backend/face_intel.py`
- Test run passed:
  - `npm run test:face-policy`
  - 6 tests passed.

Immediate next implementation target:

- Step 13 candidate: add path-filtered CI workflow trigger once workflow push permission (`workflow` scope) is available.

### Update 014 - 2026-04-18

Step 13 dedicated policy-read API delivered:

- Added new endpoint in `backend/api.py`:
  - `GET /face/policy`
  - returns current policy object directly (`identityLabelingEnabled`, `recognitionAuditEnabled`, `recognitionAuditCooldownSec`, and path metadata)
- Frontend policy loader updated in `components/incident-panel.tsx`:
  - prefers `GET /face/policy`
  - keeps fallback to `GET /face/status` for compatibility.
- Extended policy tests in `backend/tests/test_face_policy.py`:
  - validates `GET /face/policy` reflects current runtime updates.

Validation performed:

- Syntax compile passed:
  - `python -m py_compile backend/api.py backend/face_intel.py`
- Policy test suite passed:
  - `npm run test:face-policy`
  - 7 tests passed.
- Frontend production build passed:
  - `npm run build`

Immediate next implementation target:

- Step 14 candidate: expose a small policy-state badge in top-level dashboard status using `GET /face/policy` for quicker operator visibility.

### Update 015 - 2026-04-18

Step 14 top-level face-policy status badge delivered:

- Updated dashboard policy polling in `app/page.tsx`:
  - added periodic policy refresh (`GET /face/policy` with fallback to `/face/status`)
  - stores policy state in page-level `facePolicy` state
  - passes policy state to header for global visibility
- Updated header status in `components/dashboard-header.tsx`:
  - added `Face Policy` status indicator in top bar
  - shows compact value:
    - identity mode (`ID:ON` / `ID:MASK`)
    - audit mode (`AUD:ON` / `AUD:OFF`)
    - cooldown seconds
  - indicator color shifts to `danger` when masking or audit pause is active.

Validation performed:

- Frontend production build passed:
  - `npm run build`
- Face policy regression suite passed:
  - `npm run test:face-policy`
  - 7 tests passed.

Immediate next implementation target:

- Step 15 candidate: add a click action from header badge to jump/focus the Face Policy controls section inside Incident Panel.

### Update 016 - 2026-04-18

Step 15 header-to-policy focus navigation delivered:

- Updated `components/dashboard-header.tsx`:
  - `Face Policy` status indicator is now clickable
  - click emits a callback to open/focus policy controls in the right panel
- Updated `app/page.tsx`:
  - added a `facePolicyFocusSignal` channel from header to incident panel
  - clicking header policy indicator increments signal token
- Updated `components/incident-panel.tsx`:
  - listens to focus signal
  - smoothly scrolls Face Policy Controls into view
  - applies a short highlight pulse to draw operator attention

Validation performed:

- Frontend production build passed:
  - `npm run build`
- Face policy regression suite passed:
  - `npm run test:face-policy`
  - 7 tests passed.

Immediate next implementation target:

- Step 16 candidate: add tiny UX hint tooltip on header policy badge ("Click to open controls") in Arabic/English format for trial users.

### Update 017 - 2026-04-18

Step 16 policy sync-health indicator delivered:

- Updated `app/page.tsx` policy polling:
  - tracks policy sync health with `facePolicySynced`
  - sets sync state to `false` on fetch failures
  - sets sync state to `true` after successful policy fetch
- Updated `components/dashboard-header.tsx`:
  - face policy badge now reflects sync health
  - shows `SYNC:LOST` when policy fetch is unavailable
  - keeps bilingual tooltip:
    - `Open Face Policy Controls | افتح إعدادات سياسة الوجوه`

Validation performed:

- Frontend production build passed:
  - `npm run build`
- Face policy regression suite passed:
  - `npm run test:face-policy`
  - 7 tests passed.

Immediate next implementation target:

- Step 17 candidate: add a tiny retry action near `SYNC:LOST` to force immediate policy refresh without waiting for interval.
