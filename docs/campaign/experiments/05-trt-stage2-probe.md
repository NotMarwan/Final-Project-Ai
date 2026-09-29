---
authority: scoped
non_authoritative: true
---

# EXP-05 TensorRT EP availability + engine-build budget (stage-2 gate)

- Hypothesis: The ORT 1.18.0 wheel lists `TensorrtExecutionProvider`, but the TensorRT 10.0 runtime libraries are not installed on this host (`nvinfer.dll` not found on PATH at reconnaissance), so TRT session creation will fail with a provider-load error and stage-2 cannot proceed here. If it unexpectedly works, the first engine build must fit the G-13 cold-start budget (≤60 s) and a hashed engine cache must cut subsequent session creation.
- Requirement link: F-09/F-10 provider status (stage-2 option C of WT-09 §2); G-13; WT-09 §1.6 + §6 pitfall 6.
- Baseline: CUDA EP session creation times from EXP-02/EXP-03 (same model bytes).
- Candidate: `TensorrtExecutionProvider` + `trt_engine_cache_enable=1` with a hashed cache dir outside the repo (`wt-16-artifacts/trt-engine-cache/<hash16>`, key = model sha256 + ORT version + GPU name); fp32 (`trt_fp16_enable=0`); person model first (smallest build). Engine-cache invalidation triggers documented: model change, ORT version change, TensorRT version change, hardware change (NVIDIA docs additionally hard-fail on compute-capability mismatch). Driver updates are NOT a documented invalidation trigger (WT-09 §6.3 correction) but re-measurement after a driver bump is prudent [INFERENCE].
- Success criteria (defined BEFORE inspecting results): session creation with TRT EP succeeds (TRT appears in `session.get_providers()`) AND first-session engine build ≤ 60 s AND cached session creation ≤ 25% of first-session time. All three needed to even propose TRT stage-2.
- Failure criteria / rollback: session creation fails → TRT stage-2 REJECTED on this host with the failure signature recorded (rollback = provider policy without TRT, which is exactly the shipped `yolo_onnx.select_providers` policy); build >60 s → not shippable for G-13 cold start; cache ineffective → operational cost unjustified. Engine cache is disposable, never authoritative.
- Result: *(filled after run)*
- Verdict: *(filled after run)*
- Cold vs warm: first-session (cold, includes engine build) vs cached-session measured separately; both completed-session-creation timings (host clock, `perf_counter`).
