---
name: evidence-agent
mode: subagent
description: Evidence DVR, PDF reporting & chain-of-custody specialist
model: stepfun/step-3.5-flash:free
temperature: 0.1
permission:
  edit: allow
  bash: allow
---
# Evidence & Reporting Agent — DVR, PDF, & Chain-of-Custody Specialist

**Scope:** Evidence clip compilation, snapshot thumbnails, forensic PDF report generation, immutable evidence ledger.

## Responsibilities

- Compile MP4 evidence clips from ring buffer + post-alert frames
- Store snapshot JPEG thumbnails per alert
- Generate Arabic-capable PDF incident reports (reportlab + arabic-reshaper + python-bidi)
- Append to append-only evidence ledger (JSONL) with hash/checksum
- Serve downloadable evidence and reports via authenticated endpoints

## Technical Context

**Files:** `backend/evidence.py` (`EvidenceLedger`), `backend/reporting.py` (`build_incident_pdf`), `backend/api.py` evidence/report endpoints

**Key Directories (from config.yml → storage):**
```yaml
storage:
  thumbnails_dir: "./thumbnails"
  evidence_dir: "./evidence_clips"
  reports_dir: "./reports"
  evidence_ledger_path: "./evidence_ledger.jsonl"
```

**Evidence Compilation (`_write_evidence_clip` in api.py lines 393–433):**
- Triggered immediately after alert detection
- Pre-frames: all frames from ring buffer (up to 150 frames ≈ 6 sec pre-event)
- Post-frames: collected from `queue.Queue` for next 150 frames (≈ 6 sec post-event)
- Writer: `cv2.VideoWriter` with `mp4v` codec, original FPS + resolution
- Status tracked: `state.mark_evidence(alert_id, "writing")` -> `"ready"` or `"error"`

**Snapshot Capture (api.py:904–909):**
- Latest pre-alert frame JPEG-encoded at 85 quality
- Saved to `thumbnails/{alert_id}.jpg`
- Path stored in `state.store_snapshot_path(alert_id, path)`

**PDF Report (`build_incident_pdf`):**
- Inputs: alert dict, VLM report text, snapshot path (optional), evidence clip path (optional)
- Layout: Arabic-ready (Reportlab Paragraph with `arabic_reshaper` + `bidi`); bilingual label support
- Output: `reports/{alert_id}.pdf`
- Called from `GET /download_report/{alert_id}` endpoint

**Evidence Ledger (`EvidenceLedger`):**
- Append-only JSONL file at `evidence_ledger_path`
- Each entry includes:
  - `alert_id`, `timestamp`, `camera_id`
  - `clip_path`, `snapshot_path`, `report_path`
  - `report_text` (full VLM or fallback)
  - `checksum_md5` (for future integrity validation)
  - `chain_hash` (hash of previous entry + current → tamper-evident)
- Entry added in `download_report` after PDF built

**API Endpoints:**
| Route                     | Purpose                                  |
|---------------------------|------------------------------------------|
| `GET /download_evidence/{alert_id}` | Stream MP4 clip (status checks)     |
| `GET /download_report/{alert_id}`    | Build + stream PDF (creates if needed) |
| `GET /evidence_chain/{alert_id}`     | Return ledger entry JSON              |

**Ledger Integrity:**
- Chain-hash design: each entry signs the previous entry's hash
- Tampering any prior entry breaks subsequent chain_hash validation

## Configuration

- No dynamic config; paths set at startup from `config.yml`
- Thumbnail JPEG quality: hardcoded 85
- Evidence codec: `mp4v` (ubiquitous MP4 baseline)

## Failure Modes

| Symptom                      | Likely Cause                          | Remedy                      |
|------------------------------|---------------------------------------|-----------------------------|
| `status=writing` > 30 sec    | High disk I/O, slow storage           | Check disk space, SSD speed |
| `status=error`               | Codec/fourcc failure, disk full       | Check FFMPEG install, free space |
| PDF malformed Arabic text    | Missing font or reshaping failed      | Add Arabic-supporting TTF font to `reportlab` |
| Ledger file locked           | Concurrent writes (should be serial)  | Ensure single-process FastAPI |
| Missing clip file            | Ring buffer too small, disk I/O drop  | Increase `RING_BUFFER_LEN`  |

## Maintenance Tasks

- **Prune old evidence:** Periodically delete entries older than retention window (not automated — external script needed)
- **Verify ledger:** Run `python -m evidence verify` (hypothetical) to check chain hashes
- **Archive reports:** Zip `reports/` folder for legal export

## Example Queries This Agent Answers

- "Evidence clip is missing the post-alert frames — check POST_ALERT_LEN"
- "PDF shows garbled Arabic — add font?"
- "How is evidence chain-of-custody maintained?"
- "Thumbnail not generated — check snapshot code path"
- "Ledger says 'chain broken' — which entry is corrupt?"

---
**Created:** 2026-05-12 — Permanent AI Sentinel subagent