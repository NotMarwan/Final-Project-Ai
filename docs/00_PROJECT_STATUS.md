# Project Status

> See also: [README](../README.md) | [Runtime Restore Guide](01_RUNTIME_RESTORE_GUIDE.md) | [Demo Runbook](04_DEMO_RUNBOOK.md) | [Model and Data Policy](06_MODEL_AND_DATA_POLICY.md) | [Changelog](../CHANGELOG.md)

## Freeze Date

- Freeze snapshot date: `2026-05-07`

## Latest Successful Runtime Reference

- `FINAL_LIVE_ALERT_API_CHECK: PASS`
- `SAFE_TO_RUN_LIVE_DEMO: True`
- `VIOLENCE_CLS = 1`
- Live Alert Decision Layer V2: enabled and documented (see [full docs](02_LIVE_ALERT_DECISION_LAYER_V2.md))
- False-positive replay after V2:
  - `FALSE_POSITIVE_REPLAY_COUNT: 5`
  - `STILL_CONFIRMED_ALERT_COUNT: 0`
  - Result: `PASS`

## Model Reference

- Stable runtime reference SHA256:
  `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`
- Workspace-local `backend/best_model.pt` SHA256 at freeze time:
  `1fb38eeb54821d827a4621ac3fce4ad98488bc05fbf99df9ab78a13ed223b6cb`

Status note: the local file currently present in this workspace does not match the documented stable runtime SHA. Do not assume the workspace-local model file is the canonical demo model until this is reconciled.

## Live Alert Decision Layer V2

- Problem fixed: stale-frame repeated probability updates could behave like repeated votes and inflate alert confirmation risk.
- Current protection:
  - `WATCH_THRESHOLD = 0.45`
  - `CONFIRM_THRESHOLD = 0.65`
  - `CONFIRM_N = 2`
  - `CONFIRM_M = 3`
  - `MIN_DECISION_INTERVAL_SECONDS = 0.50`
  - `ALERT_COOLDOWN_SECONDS = 3.0`
- Visible alert safety:
  - red alert uses `confirmed_alert`
  - `model_prediction` is internal only
- See [Live Alert Decision Layer V2](02_LIVE_ALERT_DECISION_LAYER_V2.md) for state machine and design rationale

## Safe To Run

- Backend API with `backend/api.py`
- Live decision layer reset endpoint: `POST /decision_layer/reset` (see [API Reference](API_REFERENCE.md))
- Combined status endpoint: `GET /system/status`
- Verification notebook:
  - `notebooks/colab_verify_live_alert_decision_layer.ipynb`
- Demo flow described in [Demo Runbook](04_DEMO_RUNBOOK.md)
- Environment variable reference: [Env Vars](ENV_VARS.md)

## Do Not Change During Preservation Freeze

- Do not train.
- Do not fine-tune.
- Do not change model weights.
- Do not overwrite `backend/best_model.pt`.
- Do not change model/input compatibility logic unless only documenting it.
- Do not switch visible red alert logic back to `model_prediction`.
- Do not push heavy local-only artifacts to normal GitHub history.
