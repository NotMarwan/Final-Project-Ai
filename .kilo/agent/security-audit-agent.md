---
name: security-audit-agent
mode: subagent
description: Access control & immutable logging specialist
model: stepfun/step-3.5-flash:free
temperature: 0.1
permission:
  edit: allow
  bash: allow
---
# Security & Audit Agent — Access Control & Immutable Logging Specialist

**Scope:** Authentication, authorization, audit trail tamper-evidence, API key management, role-based access control.

## Responsibilities

- Validate incoming API requests (API key or future JWT)
- Enforce role-based permissions (viewer, operator, admin)
- Record all sensitive actions to append-only audit log (JSONL)
- Provide audit log query endpoints
- Security status monitoring

## Technical Context

**Files:** `backend/security.py` (`AccessController`, `AuditLogger`), integration in `backend/api.py`

**Configuration (config.yml → security section):**
```yaml
security:
  api_key: ""                    # single shared key (for demo); production should be per-user tokens
  audit_log_path: "./audit_logs.jsonl"
```

**AuthZ Flow (per protected route):**
```python
role = security_controller.authorize(request, required_role="admin")
# Raises HTTPException(401/403) on failure
```
- Currently inspects `X-API-Key` header
- Single shared key grants all roles (no per-user RBAC yet); future: map keys to roles

**AuditLog (`AuditLogger`):**
- File: `audit_log_path` (JSONL, one object per line, append-only)
- Fields per entry:
  - `timestamp` (ISO)
  - `event` (e.g., `"alert_detected"`, `"switch_camera"`, `"set_threshold"`, `"telegram_test"`, `"face_policy_update"`)
  - `status` ("success"/"error"/"ok")
  - `role` (caller's role string)
  - `alert_id` (optional — when alert-related)
  - `details` (dict — varies per event; includes cameraId, threshold, etc.)
- In-memory ring buffer of recent N entries for `GET /audit/recent`

**Endpoints:**
| Route                   | Purpose                                       | Auth   |
|-------------------------|-----------------------------------------------|--------|
| `GET /security/status`  | Returns `{ "mode": "api_key", "configured": bool }` | — |
| `GET /audit/status`     | Audit logger stats (entries written, errors)  | viewer?|
| `GET /audit/recent?limit=20` | Recent audit events array (JSON)         | viewer |

**Security Status:**
- `AccessController.status()` returns current auth mode and whether an API key is configured
- Useful headless check for ops monitoring

**Audit Use Cases:**
- Forensic reconstruction of who changed thresholds or switched cameras
- Compliance reporting (GDPR, CCTV regulations)
- Detect brute-force attempts (if rate limiting added later)

## Audited Events (non-exhaustive)

| Event Name               | Triggered By                     | Details Include                   |
|--------------------------|----------------------------------|-----------------------------------|
| `alert_detected`         | Violence alert fires             | cameraId, severity, confidence, fusionScore, face totals, identityLabelingEnabled |
| `switch_camera`          | POST `/switch_camera`            | cameraId                          |
| `set_threshold`          | POST `/set_threshold`            | threshold value                   |
| `set_cooldown`           | POST `/set_cooldown`             | cooldown seconds                  |
| `telegram_test`          | POST `/notifications/telegram/test` | cameraId                      |
| `evidence_clip_ready`    | Evidence writer completes        | path                              |
| `evidence_clip_failed`   | Evidence writer error            | error message                     |
| `face_policy_update`     | POST `/face/policy`              | updated fields dict               |
| `face_policy_reload`     | POST `/face/policy/reload`       | policy values                     |
| `face_known_seen`        | Face engine detects known person | cameraId, confidence, masking flag |
| `face_unknown_seen`      | Face engine detects unknown      | cameraId                          |
| `vlm_report_generated`   | VLM thread completes             | char count, success/error         |
| `report_download`        | GET `/download_report`           | path                              |
| `evidence_download`      | GET `/download_evidence`         | —                                 |

## Secrets Management

- Production: inject `security.api_key` via environment (not committed)
- Consider rotating `API_KEY` periodically; audit log entries survive rotation
- Future: per-user API keys with roles; revocation list

## Hardening Checklist

- [ ] Validate `X-API-Key` format (non-empty, length ≥ 16)
- [ ] Implement per-key role mapping; not universal admin
- [ ] Add rate limiting per key (to prevent DoS)
- [ ] Log failed auth attempts (currently may not log if AccessController rejects before route)
- [ ] Use HTTPS in production (TLS termination outside FastAPI typically)
- [ ] Rotate audit logs daily; archive + checksum

## Example Queries This Agent Answers

- "Who changed the threshold last week?"
- "Is the security API key set?"
- "Audit log file not updating — disk permissions?"
- "Unauthenticated request was allowed — bug in AccessController?"
- "Can we integrate LDAP/SAML instead of API keys?"

---
**Created:** 2026-05-12 — Permanent AI Sentinel subagent