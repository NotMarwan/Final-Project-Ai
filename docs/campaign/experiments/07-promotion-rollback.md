---
authority: scoped
non_authoritative: true
---

# EXP-07 Promotion decision + rollback evidence (select_onnx_runtime.py flow)

- Hypothesis: With EXP-01..06 evidence, exactly one runtime configuration is defensible; the promotion (or rejection) is executable and reversible through `scripts/select_onnx_runtime.py` with hash-pinned wheels, rollback wheel obtained BEFORE any uninstall, and fresh-process validation.
- Requirement link: R-02 (export/acceleration decision); F-09/F-10 provider status; WT-09 §6.1 wheel-pair hazard; G-13.
- Baseline: registered CPU configuration (ONNX CPU EP + violence CUDA), revision `6fb3bcac…` evidence.
- Candidate: decision rule pre-declared — **promote CUDA EP** iff (a) EXP-02 parity gates all pass (raw ≤0.01, match rate ≥0.99, zero flips at 0.45/0.55), AND (b) EXP-03 shows ≥1.5× per-model median speedup in both matched runs with no new pipeline failure state, AND (c) EXP-06 shows 2-worker VRAM ≤10 GB. **Adopt CPU (keep registered config)** if any of (a)/(b)/(c) fails. **TRT stage-2** only if EXP-05 all three gates pass. **fp16** only if EXP-04 passes (independent, additive).
- Success criteria (defined BEFORE inspecting results): the decision rule above yields exactly one outcome; the rollback path is demonstrated by the scoped switch tests (tampered-wheel refusal, failed-install restore, overlapping-distribution refusal — `backend/tests/test_onnx_switch.py`) and the CPU rollback wheel downloads with sha256 matching the script's pin (`1fa175bd…63ef`) BEFORE any uninstall step would run.
- Failure criteria / rollback: The shared venv is READ-ONLY for this campaign (no pip installs; validation requires `pip show onnxruntime-gpu` unchanged at the end). Therefore no wheel switch is executed here: the promoted config is delivered as a documented, operator-executable flow (stop backend → `python scripts/select_onnx_runtime.py --device <cpu|cuda>` → fresh-process provider check). If the rollback wheel cannot be obtained/verified, that is recorded as a rollback-evidence gap and promotion must not proceed operationally until closed.
- Result: *(filled after run)*
- Verdict: *(filled after run)*
- Cold vs warm: n/a (decision experiment); the decision consumes cold/warm-separated evidence from EXP-01/02/03 only.
