# Troubleshooting

## Colab Runtime Reset

Symptoms:

- files disappeared from `/content`
- imports fail even though they worked before

Actions:

1. restore `/content/ai-sentinel` from the preserved ZIP
2. restore `backend/best_model.pt` from Drive
3. verify SHA256 before running anything live
4. re-run the verification notebook

## Missing `/content/ai-sentinel`

Actions:

- extract the archive again
- rename the extracted folder to exactly `/content/ai-sentinel`
- confirm `backend/api.py` and `backend/live_alert_decision.py` exist

## Missing `best_model.pt`

Actions:

- copy the canonical model from Drive or the preserved local-only backup location
- place it at `/content/ai-sentinel/backend/best_model.pt`
- verify SHA256 before starting the backend

## SHA Mismatch

Actions:

- stop immediately
- do not run the live demo
- locate the canonical model copy
- compare against the documented stable runtime SHA:
  `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`

## `backend.live_alert_decision` Import Failure

Actions:

- confirm `backend/live_alert_decision.py` exists
- confirm it is in the backend package/runtime path
- if runtime was reset, re-copy `live_alert_decision.py` and `api.py`

## `NameError` From Type Annotations Or Runtime Imports

Symptoms may include missing pipeline symbols or backend startup failures.

Actions:

- re-run the last known working backend file set
- confirm the preserved `backend/api.py` is the same code used in the stable live-alert V2 runtime
- avoid mixing partial old/new backend files after a reset

## Stage 12 Zero Processed

Actions:

- confirm the external evaluation subset actually contains copied files
- confirm the model SHA verification cell passed
- confirm the inference pipeline initializes successfully
- verify `VIOLENCE_CLS = 1`

## False Positives Still Confirmed

Actions:

1. reset the decision layer
2. verify thresholds:
   - watch `0.45`
   - confirm `0.65`
   - `2 of 3`
   - min decision interval `0.50`
   - cooldown `3.0`
3. verify the UI is not using `model_prediction`
4. verify `decision_sample_accepted` is being respected for stale/too-soon duplicate frames

## What To Re-run

- verification notebook:
  - `notebooks/colab_verify_live_alert_decision_layer.ipynb`
- backend status check:
  - `GET /system/status`
- decision-layer reset:
  - `POST /decision_layer/reset`
