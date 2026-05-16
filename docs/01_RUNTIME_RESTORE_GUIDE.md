# Runtime Restore Guide

> See also: [Project Status](00_PROJECT_STATUS.md) | [Demo Runbook](04_DEMO_RUNBOOK.md) | [Model and Data Policy](06_MODEL_AND_DATA_POLICY.md) | [API Reference](API_REFERENCE.md) | [README](../README.md)

## Goal

Restore a known AI-Sentinel runtime in Colab after a runtime reset without retraining or changing weights.

## Canonical Restore Target

- Project root in Colab: `/content/ai-sentinel`
- Model path in runtime: `/content/ai-sentinel/backend/best_model.pt`
- Stable runtime reference SHA256:
  `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`

## Restore From ZIP

1. Upload the preserved GitHub-safe archive or project ZIP.
2. Extract it into `/content`.
3. Ensure the final path is exactly:

```python
import os
assert os.path.isdir("/content/ai-sentinel")
```

If the extracted folder name is different, rename it to `ai-sentinel`.

## Copy `best_model.pt` From Drive

```python
from google.colab import drive
drive.mount("/content/drive")
```

Copy the canonical model file from its preserved Drive location into:

```python
/content/ai-sentinel/backend/best_model.pt
```

Do not overwrite the canonical model with an unverified file.

## Verify SHA256

```python
import hashlib
from pathlib import Path

model_path = Path("/content/ai-sentinel/backend/best_model.pt")
sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
print("SHA256:", sha)
assert sha == "2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01"
```

If the assertion fails:

- stop immediately
- do not run the live demo
- locate the correct canonical model copy first

## Re-apply Runtime Files If Reset Removed Them

If the runtime lost the current stable logic, restore these files into `/content/ai-sentinel/backend/`:

- `live_alert_decision.py`
- `api.py`

These two files are the critical runtime files for the live alert decision policy and the API integration path.

## Final Verification Cell Summary

Run the verification notebook or equivalent cells to confirm:

1. `VIOLENCE_CLS == 1`
2. base runtime threshold remains `0.45`
3. decision layer imports successfully
4. decision layer thresholds are:
   - watch `0.45`
   - confirm `0.65`
   - `2 of last 3`
   - min decision interval `0.50`
   - cooldown `3.0`
5. false handshake / stale single spikes do not produce confirmed alerts
6. real violence reaches `WATCH` then `CONFIRMED_VIOLENCE`
7. `/system/status` reports the decision-layer payload correctly
8. `FINAL_LIVE_ALERT_API_CHECK: PASS`
9. `SAFE_TO_RUN_LIVE_DEMO: True`

## Recommended Cells / Files

- Notebook:
  - `notebooks/colab_verify_live_alert_decision_layer.ipynb`
- Runtime files:
  - `backend/live_alert_decision.py`
  - `backend/api.py`
