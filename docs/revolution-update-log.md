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

