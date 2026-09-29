---
authority: scoped
non_authoritative: true
---

# EXP-04 fp16 precision gate (optional; naive whole-model candidate)

- Hypothesis: A whole-model fp16 export of the weapon detector may speed inference/memory further, but detection-head numerics (exp/sigmoid on box deltas and 6-class logits) make accuracy drift likely; the gate exists to REJECT it if decision behavior changes.
- Requirement link: F-09 provider/precision status; WT-09 §8 R-02 item 4 + §6 pitfall 4; R-03/R-04 (fp16 only, int8 excluded without calibration data).
- Baseline: fp32 export from `weapon_hadi_yolo.pt` (sha256 `e85b15fe…6ab6b5`, read-only copy to untracked scratch `wt-16-artifacts/fp16/`), exported with ultralytics 8.2.0 `export(format='onnx')`, run on CUDA EP.
- Candidate: SAME export path with `half=True` (whole-model fp16 — the naive variant; detection-head block-listing NOT possible here because `onnxconverter_common` is absent and the shared venv is read-only, so the ORT Mixed-Precision tool variant is DEFERRED with this reason, not dropped silently). Comparison fp32-export vs fp16-export on CUDA EP on the 10 fixed fixture frames; registered `weapon_yolo.onnx` vs fp32-export reported separately as export drift (never conflated with the precision variable).
- Success criteria (defined BEFORE inspecting results): candidate non-finite values == 0 AND raw max abs diff ≤ 0.02 AND decoded match rate ≥ 0.98 at fixed NMS (conf 0.25, IoU 0.5) AND zero near-threshold flips at 0.45/0.55.
- Failure criteria / rollback: ANY gate missed → REJECT fp16; fp32 stays the default; rollback = the fp32 artifact (registered `weapon_yolo.onnx`, sha256 `96991cd5…75aef`, unchanged). No fp16 artifact is ever promoted without this harness passing.
- Result: *(filled after run)*
- Verdict: *(filled after run)*
- Cold vs warm: not a timing experiment (accuracy gate only); stageModelLoadMs recorded for both artifacts. Completed-inference outputs compared (CUDA sync applied), not launch outputs.
