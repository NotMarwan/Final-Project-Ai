---
authority: scoped
non_authoritative: true
experiment: EXP-2701
workstream: WT-27
status: pre-registered (criteria fixed before the measured run)
---

# EXP-2701 optional local VLM (Qwen3-VL-2B) as an offline Arabic incident-analyser

- **Hypothesis:** a ≤5 GB locally-runnable vision-language model can add an *optional, clearly
  labelled* Arabic interpretation layer for incidents whose facts report already exists, without
  needing the network and without meaningfully disturbing the concurrent detection pipeline.
- **Requirement link:** user requirement "Arabic factual reporting" → G-09 (offline operation);
  R-06 (VLM verdict); blueprint F-26 (remote model report, currently unverified/DISABLED) and
  F-27 (Groq VLM forensic text, disconnected) are the alternatives this candidate would replace
  as a *local* option.

- **Baseline (facts path, already measured):** local facts report via
  `backend/local_forensics.py` — deterministic, stdlib-only, no GPU, 0 network calls; RTX 3060
  otherwise occupied by the detection pipeline; source mode file-media (demo clips) /
  synthetic frames; resolution: whichever the fixture frame carries (1920×1080 garage CCTV;
  400×300 store CCTV; VGA night capture).
- **Candidate:** `Qwen/Qwen3-VL-2B-Instruct` (apache-2.0), single `model.safetensors`
  4 255 140 312 B, HF LFS SHA-256 `7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0`,
  local untracked copy under `assets/qwen3-vl-2b/`; transformers 4.57.1 + torch 2.3.0+cu118 from
  the read-only venv (`assets/pylibs/` for the new Python packages); bf16 on cuda:0; greedy
  decoding (`do_sample=False`); Arabic incident prompt; fixtures = 5 still frames extracted from
  the repo's committed demo clips (`assets/vlm-fixtures/`, provenance in `PROVENANCE.json`,
  ground truth in `GROUND_TRUTH.json`).

- **Success criteria (defined BEFORE inspecting results):**
  1. unsupported-claim rate ≤ 20 % of atomic claims (hand-counted against ground truth);
  2. no fabricated identity/crime assertion in ≥ 2 of the 5 fixtures;
  3. median completed-inference latency ≤ 20 s per frame (CUDA-synchronised);
  4. peak total GPU use ≤ 10 GB while the detection load runs concurrently (≥ 2 GB headroom);
  5. inference completes with non-loopback sockets blocked (and additionally with *all* sockets
     blocked).
- **Failure criteria / rollback:** reject if unsupported-claim rate > 50 %, or identity/crime
  fabricated in ≥ 2 fixtures, or the concurrent detection process is killed (OOM), or median
  latency > 60 s/frame. Between the two bands → adopt *with guardrails*. Rollback is trivial:
  the candidate is untracked (`assets/`) and never wired into the report path; the facts report
  and PDF are unchanged by this experiment.
- **Result:** **NOT MEASURED in this run — blocked on two external gates**, both documented with
  exact state, plus all pre-work that *was* measured:
  1. **Model transfer incomplete.** `model.safetensors` reached **4.031 GB of 4.255 GB
     (115/127 × 32 MiB blocks)** via a resumable range downloader (`assets/download_parallel.mjs`,
     sidecar `model.safetensors.blocks.json`); throughput fell to ~0.5–1 MB/s on this shared link
     (two concurrent downloader instances; a first sequential attempt died after 260 MB). The
     partial file is a valid prefix and the remaining 12 blocks resume with the same command, so
     no work is lost. HF LFS target hash `7de1838c…977a0` pinned in `assets/verify_model.py`.
  2. **RESOURCE-LOCK window not reached.** Queue order (Main-arbitrated) was
     WT-18/WT-19 → WT-16 → WT-21(done) → WT-15 → **WT-27**; the run must be exclusive (any
     concurrent workload makes it CONTENDED/INVALID per campaign rule), and my slot had not
     arrived when the request budget expired.
  Measured enablers (evidence that the run is ready to execute): HF metadata for the whole
  shortlist; processor loads fully offline (`Qwen3VLProcessor`, image+text → 185-token prompt for
  a 400×300 fixture frame) with `HF_HUB_OFFLINE=1`; a tiny random-config
  `Qwen3VLForConditionalGeneration` forward pass succeeds on **transformers 4.57.1 + torch
  2.3.0+cu118** (`(1,8,1000)` logits) — the version pair had to be pinned because transformers 5.x
  refuses torch < 2.5; 5 fixture frames extracted from the repo's demo clips with ground truth
  hand-written (`assets/vlm-fixtures/{PROVENANCE,GROUND_TRUTH}.json`).
- **Verdict:** **blocked** (this workstream/run) — not a rejection of the candidate, and not an
  adoption. The candidate remains *undecided*; the pre-registered criteria above stand and the
  run is reproducible with:
  `mkdir …/RESOURCE-LOCK` → `py assets/download_parallel.mjs` → `py assets/verify_model.py` →
  `py assets/vlm_measure.py --label run1` → `py assets/vlm_measure.py --label run1-hard
  --hard-offline --fixtures 2` → remove the lock.
  Until it runs, the recommendation for the product is unchanged: keep the remote model report
  (F-26) DISABLED-honest and rely on the deterministic facts report (F-28); no VLM text may be
  wired into the report path (`backend/reporting.py` labels any non-local-facts text
  "تفسيرات النموذج — غير مُتحقَّق منها" and would keep doing so).
- **Cold vs warm:** not applicable (no inference run). Cold-load plumbing is measured (processor
  load time recorded by the smoke test, model load not reached).
- **Discipline notes:** VLM text would only ever be rendered under
  "تفسيرات النموذج — غير مُتحقَّق منها" (`backend/reporting.py` already labels any non-local-facts
  text that way); it can never enter the facts sections. Fixtures are the repo's own demo clips,
  processed locally only — nothing is uploaded.
