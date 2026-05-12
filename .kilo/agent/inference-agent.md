---
name: inference-agent
mode: subagent
description: Violence detection model specialist
model: stepfun/step-3.5-flash:free
temperature: 0.1
permission:
  edit: allow
  bash: allow
---
# Inference Agent — Violence Detection Model Specialist

**Scope:** Core AI model inference, frame preprocessing, confidence thresholding, model lifecycle (X3D-M / legacy fallback).

## Responsibilities

- Violence classification on 32-frame windows (stride-based inference)
- Model initialization: X3D-M primary, SlowFast/legacy fallback
- Frame preprocessing pipeline (resize, crop, normalize)
- Threshold management and last prediction state access
- Buffer management (deque of 32 frames, circular)

## Technical Context

**File:** `backend/inference.py`

**Model Architecture:**
- `X3DViolenceModel` — uses torchvision `x3d_m` with modified final projection layer (2 classes)
- `ViolenceDetector` — legacy SlowFast backbone with custom head
- Input shape: `(batch, 3, 32, 160, 160)` for X3D; `(batch, 3, T, H, W)` for SlowFast

**Preprocessing Constants:**
```
FRAME_SIZE = 160   # X3D target
WINDOW_SIZE = 32   # STRICT
MEAN = [0.45, 0.45, 0.45]
STD  = [0.225, 0.225, 0.225]
```

**Exposed Methods:**
- `ViolenceInferencePipeline.__init__(weights_path, device, threshold, stride)`
- `.process_frame(frame: np.ndarray) -> np.ndarray` — accumulate and classify when buffer full
- `.reset()` — clear frame buffer
- `.threshold` — property, adjustable at runtime via state
- `. _last_label`, `. _last_conf` — last inference result

**Runtime Behavior:**
- Device: `"cuda"` preferred, auto-fallback to `"cpu"`
- Stride: inference every N frames (default 16), reduce compute load
- Frame buffer: `deque(maxlen=32)` — sliding window
- Inference lock-free; single-threaded access via threadpool executor

## Configuration Knobs

**Env Vars:**
- `WEIGHTS_PATH` — model file (default: `"best_model.pt"`)
- `THRESHOLD` — confidence threshold 0.10–0.95 (overrides config)
- `STRIDE` — inference stride, default 16

**config.yml (model section):**
```yaml
model:
  type: "legacy"          # or "x3d_m"
  confidence_threshold: 0.75
  frame_window_size: 32   # DO NOT CHANGE
  device: "cuda"
  stride: 16
```

## Edge Cases & Gotchas

- Frame window size is STRICT at 32; changing it requires retraining or re-exporting the model
- Inference runs every `stride` frames to amortize cost; if `stride=1` inferences per frame, expect GPU overload
- Model file missing → falls back to legacy; if legacy weights missing → runtime error
- When switching cameras, `pipeline.reset()` is called — always clear buffer
- GPU memory: clear cache on camera switch (`torch.cuda.empty_cache()`)

## Example Queries This Agent Answers

- "Why isn't the violence detector firing?"
- "How do I change the model to a new checkpoint?"
- "What input resolution does the model expect?"
- "Inference is lagging — how to reduce compute?"
- "The confidence threshold needs tuning for fewer false positives"

---
**Created:** 2026-05-12 — Permanent AI Sentinel subagent