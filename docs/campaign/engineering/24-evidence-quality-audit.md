---
authority: scoped
non_authoritative: true
---

# 24 — Evidence quality audit (S-07, WT-24)

Scope: exactly which pixels reach evidence artifacts, what each artifact IS,
and which quality claims survive review. Baseline `e86d34b` (+ cherry-pick
`018b5c4` SC-10) on branch `codex/sentinel-24-evidence`. Every number below is
either measured in this worktree (commands noted) or traced to source lines;
nothing here claims live-camera behavior (no camera device exists — all runs
are synthetic/file sources, labeled as such).

## 1. Pixel path: decode → ring → clip encode → file

Traced at `backend/api.py` `camera_worker` and `backend/evidence_video.py`
(line refs post-`018b5c4`):

| Stage | What happens | Pixel facts |
|---|---|---|
| Decode | `capture.read_frame()` returns `raw` | Full decoded source frame, BGR uint8, source resolution (e.g. 1920×1080) |
| Display copy | `render_queue.append(raw.copy())` | Source resolution; annotated later for the UI/MJPEG |
| **Evidence ring** | `evidence_frame = downscale_for_inference(raw, 960)` (`api.py`, `temporal_frames.py:41-47`) | **Max-side 960**, INTER_AREA resize, full frame, **no crop**, aspect preserved; BGR uint8 |
| Ring buffer | `deque(maxlen=600)`, entries `(captured_at, frame)`, pruned to a 5.0 s **monotonic** window | Pre-event coverage = up to 5 s / 600 frames; nothing older is retained |
| Inference view | `small = downscale_for_inference(raw, 640)` | Max-side 640 — **separate array, never enters the ring** |
| Clip assembly | `_write_evidence_clip` nearest-sample resamples ring+post frames onto a constant-fps grid (`fps` = source fps) | Frame duplication/skipping only at resample; pixels untouched |
| Encode | rawvideo bgr24 → libx264 `-crf 23` (or NVENC `-cq 23`) → yuv420p, avc1, `+faststart` | **Lossy re-encode**; odd dims padded `BORDER_REPLICATE` to even; frames resized INTER_AREA only if caller dims mismatch |
| Verify | `_probe_output`: full ffmpeg decode, exact frame count, `Video: h264` + `yuv420p` in stream summary; `_mp4_box_positions` asserts `moov` before `mdat` | Verification is **encoder-agnostic** (same contract for libx264 and h264_nvenc) |
| Publish | fsync of `{id}.part.mp4` → atomic `Path.replace` → `{id}.mp4` → ledger receipt | A torn `.part.mp4` is never served (`/api/clips/list` skips it, `/clips/{id}` 404s) |

**Evidence path bypasses the 640 inference view — proven two ways.** Source:
the ring is fed only from `downscale_for_inference(raw, 960)`; the 640 array is
constructed afterwards for `FramePacket` IPC and is never referenced by the
ring or the writer. Test:
`test_evidence_view_bypasses_the_inference_view` (synthetic 1920×1080 frame →
960×540 evidence frame vs 640×360 inference view; distinct shapes; aspect
ratio preserved ⇒ no crop).

Measured sample (synthetic 320×180 smoke through the real writer path, 33
frames @5 fps, ffmpeg `Lavf61.7.100`):

```
Duration: 00:00:06.60, start: 0.000000, bitrate: 3 kb/s
Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(progressive), 320x180, 1 kb/s, 5 fps, 5 tbr, 10240 tbn (default)
      Metadata: encoder         : Lavc61.19.100 libx264
frame=   33 fps=0.0 q=-0.0 Lsize=N/A time=00:00:06.60 bitrate=N/A speed= 305x
```

## 2. What each artifact IS (no claim beyond what survives)

| Artifact | Identity | NOT a claim we make |
|---|---|---|
| Evidence clip `evidence_clips/{id}.mp4` | **Lossy H.264 re-encode of max-side-960 downscaled decoded frames** (CRF 23, yuv420p) | Not full-resolution (source >960 loses detail at the downscale); not pixel-exact (lossy codec); not the inference view |
| Snapshot `thumbnails/{id}.jpg` | **JPEG Q85 lossy re-encode of the annotated source-resolution decoded frame** (`pipeline_render.py:186-206`, annotations + weapon box drawn) | Not a source master; annotations are burned in; not the clip frame |
| Report PDF `reports/{id}.pdf` | Rendered document embedding report text + snapshot; hashed at publication | Not a raw data export |
| Ledger `evidence_ledger.jsonl` | Append-only JSONL hash chain (`prevHash`→`currentHash` over sorted-key JSON) with per-asset real SHA-256 + explicit hash status | Not a multi-process store (single-writer, documented) |
| Demo clip review | Original source file served as-is (`/demo_video/{id}`) | Not produced by this pipeline |

"Full-resolution evidence" is therefore **not claimed anywhere**: the clip is a
960-side derivative and the snapshot is an annotated JPEG. The only
full-decoded-resolution artifact is the snapshot's pre-JPEG source frame, which
is itself JPEG-lossy afterwards.

## 3. Coordinate mapping (tested)

`inference_process._scale_person_tracks` maps **model-input → original source**
by `x·source_w/input_w`, `y·source_h/input_h`, clipped to the source frame.
**Display** is the annotated copy of the source frame (`render_queue` =
`raw.copy()`), so display coordinates are source coordinates 1:1. The snapshot
draws the weapon box from normalized `[0,1]` coords scaled by snapshot
dimensions (`pipeline_render.py:186-206`) — same mapping family.

Test: `test_model_input_to_source_to_display_coordinate_mapping` (640×360 input
→ 1920×1080 source: `[64,36,320,180] → [192,108,960,540]` exact; out-of-range
input clips to `[0,0,1920,1080]`; invalid dims raise). Evidence caveat: clip
frames are 960-side, so clip-space = source·(960/source_max_side); the receipt
records `clipFrameMaxSide` so consumers can re-derive the scale.

## 4. Timestamps (SC-6) and duration (G-08)

- Receipt `timestamp`: wall-clock UTC ISO, labeled `timestampClockDomain:
  "utc-wall"`.
- Clip spans (`clipPreEventSpanSeconds` etc.): producer stamps =
  `time.monotonic()`, labeled `clipCaptureClockDomain: "monotonic"`. WT-14
  adds a config-gated `perf-qpc` capture clock for measurement runs — the
  receipt label tracks the deployment default; F-38 health `clockBase` is
  authoritative for gated runs (coordinated with WT-14).
- MP4 container timeline is synthetic: frame index / fps starting at 0 —
  **never** wall time; the real captured span lives in the receipt
  (`clipSourceSpanSeconds`).
- Duration semantics: `clipDurationSeconds = frames/fps` (what a player shows);
  source span = last stamp − first stamp = (frames−1)/fps. The +1/fps boundary
  term is the accuracy limit. Measured: span 6.4 s → duration 6.6 s = **+3.1 %
  (G-08 ≤5 % bound respected)**; container `Duration: 00:00:06.60`, `5 fps`
  verified by real decode (33/33 frames) and `cv2.CAP_PROP_FPS == 5`.
- Partial clips are explicit, never silently short: status `"partial"` +
  receipt `clipComplete: false` + `clipPartialReason ∈ {"stream-closed",
  "stalled"}` (`/api/clips/list` surfaces both fields). Stream start without
  pre-event frames records `clipPreEventSpanSeconds ≈ 0` honestly.

## 5. Integrity hardening (R-4) and adversarial results

R-4 was `sha256_file` returning the literal `"N/A"` for missing assets — a
silent substitution recorded as data. Now:

- `sha256_file` (pure primitive): real SHA-256 or `EvidenceIntegrityError`;
  **never** a placeholder.
- `hash_asset` (recorder): `(hash, status)` with `hashed` / `absent`
  (`path is None`) / `unreadable` (declared but unreadable). Chain records keep
  the C-4a wire sentinel (`"N/A"` = no hash recorded — the `lib/local-report.ts:33`
  parser normalizes it to null and ignores unknown keys, VERIFIED in this
  worktree) but every NEW record carries `clipHashStatus`/`snapshotHashStatus`/
  `reportHashStatus`, so absence and breakage are explicit, distinguishable
  data. Every published artifact gets a real SHA-256 chain entry or an explicit
  failure marker.
- Primary-artifact strictness: `_write_evidence_clip` withdraws the published
  clip (unlink + `"error"` status) if it cannot be chained with a real hash —
  no unchained published clip can exist.
- Report PDFs chain as `report-receipt` follow-up records (idempotent per
  distinct PDF hash); `get()`/`GET /evidence_chain` serve only the primary
  alert receipt. WT-23 derivative records (`DERIVATIVE_RECORD_TYPE`, exported
  from `evidence.py`) are skipped the same way; `append_record` is the shared
  primitive.
- Append rollback: a storage failure (e.g. disk-full) truncates the partial
  append and raises `EvidenceStorageError`; the chain file stays byte-identical.
- Duplicate alert ids: under `_evidence_publish_lock`, a second writer never
  overwrites a chained artifact — intact chain → idempotent `"ready"`;
  hash mismatch → `"error"` + `evidence_clip_conflict`, original bytes kept.

Adversarial coverage (all in `test_evidence_ledger_concurrency.py` /
`test_evidence_video.py`): torn write (`.part.mp4` never served; retry
recovers), ledger corruption (writer aborts, nothing published; chain reads
raise loudly), concurrent finalization (48 parallel appends = one chain; racing
replays idempotent), disk-full (rollback + chain valid), duplicate alert ids
(idempotent + conflict paths), path traversal (`../secret`, `alert/path`,
`alert\path`, `..`, 65-char ids rejected 400 on `/clips`, `/download_evidence`,
`/evidence_chain`, and before any writer file I/O).

## 6. Encoder opt-in (E-7) — measured

`AI_SENTINEL_EVIDENCE_ENCODER`: unset → **libx264 (validated default)**;
`auto` → NVENC capability probe + bounded sessions with automatic libx264
fallback; `h264_nvenc` → strict opt-in, fails loudly. Probe contract is
encoder-agnostic (§1). Full card:
`docs/campaign/experiments/07-evidence-encoder-opt-in.md` (results JSON
SHA-256 `395d2455533e3a5efcfac1d53fc8be567b6efa9226ecf27f74f9c104461670d8`).

| Cell (300×960×540 frames/encode, incl. verify) | Result |
|---|---|
| libx264 solo | warm median 2.76 s (n=4) |
| h264_nvenc solo | warm median 1.07 s — 2.6× faster; probe contract passed |
| 2 concurrent NVENC sessions | 6/6 sessions OK over 3 runs; 1.58–1.77 s/session |
| NVENC during torch-CUDA load | warm median 1.08 s = **+1.1 %** |
| torch iteration during 2 NVENC sessions | median 2.40→4.46 ms = **+86 %**; p95 3.04→6.56 ms = +115 % |

**Verdict: adapt.** Capability, concurrency (session limit 2 matches
`_NVENC_SESSION_LIMIT`) and output contract are validated, but inference
interference (+86 % ≫ pre-registered +20 %) means NVENC must NOT be the default
on GPU-inference deployments: unset/libx264 stays the shipped default,
`h264_nvenc` remains explicit opt-in, and `auto`'s capability-based preference
is documented as unsafe to combine with concurrent GPU inference (the p05-stable
/p95-inflated signature points at GPU scheduling contention). CPU-encode
timings carry the arbitration's POTENTIALLY CONTENDED label (external WT-14 CPU
batch may have overlapped); deterministic counts stand.

## 7. Retention (P-6) and access (P-2)

- Retention: `clips.clip_retention_days` (30, previously inert) is now read by
  `GET /api/evidence/retention` — a **dry-run plan only**. No deletion code
  path exists (`EvidenceRetentionPolicy` has no prune/delete/apply methods —
  pinned by test). Legal holds (`POST /api/evidence/retention/hold`, admin,
  audited) always win over age; holds persist atomically in
  `evidence_holds.json`. Report PDFs rebuilt per download get new
  report-receipts (each distinct PDF is a distinct chained artifact).
- Read-audit (Axon-style P-2): every `/clips/{id}`, `/download_evidence/{id}`,
  `/evidence_chain/{id}` access appends an audit record (actor/role, action,
  artifact SHA-256, ledger SHA-256, AuditLogger ISO timestamp). Served bytes
  that mismatch the chained hash return **500 before serving**, and the read
  audit entry is recorded with `status: "error"` carrying both hashes so the
  tamper attempt is visible. Legacy `"N/A"`/null ledger hashes
  count as "no hash recorded" (serve + audit), not as mismatch.
- **Actor semantics caveat**: `/clips/{id}` and `/api/clips/list` remain
  public reads by deliberate, documented policy (SecurityApiAudit §7.2 — the
  UI media element cannot send `X-API-Key`; gating breaks playback). The audit
  records the actor best-effort: a valid shared key reports its role, a
  missing/wrong key reports `"anonymous"` and the read still succeeds —
  the audit actor is **not** an authentication result. Residual risk: with
  `ADMIN_API_KEY` configured, clip bytes are still readable without a key;
  the follow-up is a UI transport change (blob-fetch via `apiFetch` or
  short-lived ticket) deferred to the UI workstreams.

## 8. Playback verification

- Real decode: every encode is fully decoded by ffmpeg (exact frame count) and
  OpenCV before publication; `moov` before `mdat` asserted byte-level
  (fast-start) — encoder-agnostic (§1, tests).
- **Chromium playback: VERIFIED** against a real generated clip (headless
  Chrome `--headless=new`, real media pipeline): `{"readyState":4,
  "duration":6.6, "currentTime":6.6, "videoWidth":320, "videoHeight":180,
  "error":null, "canPlayH264":"probably"}` — full playback to end of a 33-frame
  H.264/yuv420p fast-start clip.
- The repo e2e fixture path (`tests/e2e`, Playwright + Next dev) is **NOT RUN**
  here: this worktree has no `node_modules` and the venv has no `playwright`
  module — 'unmeasured' by the harness rule, not 'passed'. Pending-integration
  note: run `npm ci` + Playwright setup, then
  `pytest tests/e2e` against the assembled candidate.

## 9. New unmeasured paths / limitations (honest list)

- Live-camera evidence behavior: impossible on this hardware (no device);
  all verification is synthetic/file-media. Evidence duration under live
  capture remains unmeasured (consistent with the G-08 gap rows).
- Multi-process ledger appends: unsupported (single-writer design, unchanged).
- `auto` encoder mode co-scheduled with GPU inference: not recommended per E-7;
  its behavior under NVENC driver loss falls back to libx264 (retry path
  tested via simulation; real driver-loss not reproducible here).
- Snapshot provenance depends on `pipeline_render._emit_alert` (WT-20 may add
  SC-4 payload keys; receipt schema grows additively only).
- The e2e/UI integration of `partial` clip states (badge in clip sidebar) is
  surfaced by `/api/clips/list` but no UI consumer exists yet (additive keys,
  old UI unaffected).
