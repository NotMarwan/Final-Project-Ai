---
authority: scoped
non_authoritative: true
---

# EXP E-07 (WT-10 E-7) — Evidence encoder opt-in: NVENC vs libx264

- Hypothesis: `h264_nvenc` can produce evidence clips that meet the exact SC-8
  output contract (H.264/yuv420p/fast-start, exact frame count, full decode)
  while (a) sustaining 2 concurrent encode sessions and (b) not materially
  slowing concurrent torch-CUDA inference on the same GPU. If both hold with
  small deltas, `auto`/`h264_nvenc` can be recommended for GPU deployments;
  otherwise the validated `libx264` default stands and NVENC stays strictly
  opt-in.
- Requirement link: WT-24 step 4 (encoder opt-in, "validate 2 concurrent NVENC
  sessions + torch-CUDA interference before recommending default; libx264 safe
  fallback") → F-21 (evidence clip writer), SC-8 (output contract must be
  encoder-agnostic).
- Baseline: commit `codex/sentinel-24-evidence` worktree state before this run;
  workload = 300 synthetic BGR uint8 frames 960x540 (max-side 960 evidence
  frames), encoded at 15 fps to MP4 through `backend/evidence_video.
  encode_browser_mp4` with `AI_SENTINEL_EVIDENCE_ENCODER=libx264`; ffmpeg =
  imageio-ffmpeg bundled build (`resolve_ffmpeg()`); decision config not
  involved; source mode = synthetic in-memory frames (no camera device exists);
  env = venv PyTorch 2.3.0+cu118, RTX 3060 12 GB, Windows x64.
  Torch interference workload: 200 × (2048×2048 float32 matmul + `torch.cuda.synchronize()`)
  on cuda:0, iteration time measured post-warmup.
- Candidate: identical workload with `AI_SENTINEL_EVIDENCE_ENCODER=h264_nvenc`
  (`-preset p4 -cq 23 -b:v 0`), same probe contract (`_probe_output`: exact
  frame count + full decode + h264/yuv420p + moov-before-mdat).
- Success criteria (defined BEFORE inspecting results):
  1. Every NVENC encode passes the same probe contract as libx264 (exact 300
     frames, h264, yuv420p, fast-start) — 0 failures in ≥3 runs per cell.
  2. 2 concurrent NVENC sessions both complete correctly in ≥3 runs.
  3. Interference: median encode wall-time during concurrent torch load and
     median torch iteration time during concurrent NVENC sessions each within
     +20 % of their solo baselines.
  4. Session capacity: the validated concurrent-session count is ≥2 (the value
     hard-coded in `evidence_video._NVENC_SESSION_LIMIT`).
- Failure criteria / rollback: any probe/encode failure, session capacity <2,
  or either interference delta >+20 % → do NOT recommend NVENC as default;
  `libx264` remains the shipped default and `h264_nvenc` stays explicit opt-in
  (rollback = keep `resolve_encoder_mode()` returning "libx264" for unset env).
  The capability probe + safe fallback code remains either way (it cannot
  weaken the output contract).
- Result: RESOURCE-LOCK RUN (acquired by atomic mkdir 23:27:19Z, released
  23:31:50Z; exclusive per filesystem-verified acquisition — see the CONTENTION
  NOTE below for a possible external CPU overlap). Workload per cell: 4 runs × (300 frames 960x540
  @15 fps, `encode_browser_mp4` incl. verify). GPU: NVIDIA GeForce RTX 3060;
  torch 2.3.0+cu118. An earlier pilot run was DISCARDED as contended (two
  duplicated processes of my own harness shared a temp outdir and overlapped
  on CPU ~17 s; results not used).
  - libx264 solo: runs [3.236, 2.852, 2.631, 2.761] s (cold 3.236; warm median
    2.761 s). n=4.
  - h264_nvenc solo: runs [1.099, 1.032, 1.070, 1.072] s (cold 1.099; warm
    median 1.070 s) → 2.6× faster than libx264. n=4. All runs passed the full
    probe contract (exact 300 frames, h264, yuv420p, fast-start).
  - 2 concurrent h264_nvenc sessions (3 runs, 6 sessions total): per-session
    [1.680, 1.579], [1.735, 1.734], [1.732, 1.772] s; errors: [] — 6/6
    sessions completed and passed the probe contract. Session capacity ≥ 2
    validated (`_NVENC_SESSION_LIMIT = 2` matches).
  - torch CUDA loop (200 × 2048² matmul + sync, n=200 iterations/cell):
    solo median 2.395 ms (p05 2.281, p95 3.043); during 2 NVENC sessions
    median 4.458 ms (p05 2.299, p95 6.555) → median +86 %, p95 +115 %.
  - h264_nvenc during continuous torch load: runs [1.077, 1.059, 1.105] s,
    warm median 1.082 s → +1.1 % vs solo warm median. n=3.
  - Raw artifact: `docs/campaign/experiments/07-evidence-encoder-opt-in.results.json`
    (SHA-256 `395d2455533e3a5efcfac1d53fc8be567b6efa9226ecf27f74f9c104461670d8`);
    sample count/denominators as listed per cell.
  - CONTENTION NOTE (per Main's 02:23–02:27 lock-ledger arbitration): WT-14's
    CPU-only bg_490 batch started 02:26:04 with an end time unknown to this
    workstream and MAY have overlapped the final pass. CPU-sensitive cells
    (libx264_solo, and the host-side portions of the NVENC cells) are therefore
    labeled POTENTIALLY CONTENDED upper bounds; deterministic counts (frames,
    sessions succeeded, probe-contract passes) stand as measured. The
    interference deltas are same-run, back-to-back cell comparisons and keep
    their measured values with this caveat; their p05-stable/p95-inflated
    signature (p05 2.28→2.30 ms, p95 3.04→6.56 ms) is consistent with GPU-side
    scheduling contention rather than uniform CPU load. The verdict direction
    is the conservative one and cannot be flipped by contention: a potentially
    contended measurement can never justify switching the default encoder.
- Verdict: **adapt** — criteria 1, 2, 4 PASS; criterion 3 FAILS (inference
  iteration degrades far beyond +20 % while NVENC encodes run). Per the
  pre-registered rollback rule: `libx264` remains the shipped default (unset
  env → libx264), `h264_nvenc` stays strict opt-in, and `auto`'s
  capability-based NVENC preference must be documented as NOT safe to combine
  with GPU inference (see the S-07 quality audit, encoder section). NVENC is
  otherwise validated: contract-preserving, 2 concurrent sessions, 2.6× faster
  solo, +1.1 % interference in the encode direction.
- Cold vs warm: first run of each cell is reported separately as cold; medians
  computed over warm runs only. Encode timing is end-to-end wall time of
  `encode_browser_mp4` (includes verify); torch timing uses CUDA sync per
  iteration, never launch timing.
