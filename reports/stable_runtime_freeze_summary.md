# Stable Runtime Freeze Summary

- Freeze date: `2026-05-07`
- `FINAL_LIVE_ALERT_API_CHECK: PASS`
- `SAFE_TO_RUN_LIVE_DEMO: True`
- `VIOLENCE_CLS = 1`
- Decision policy: `Live Alert Decision Layer V2`
- False-positive replay after V2: `5 -> 0 confirmed alerts`
- Stable runtime reference SHA256:
  `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`
- Workspace-local `backend/best_model.pt` SHA256:
  `1fb38eeb54821d827a4621ac3fce4ad98488bc05fbf99df9ab78a13ed223b6cb`

The freeze is preserved for documentation, manifests, backup creation, and safe GitHub preparation. The local model SHA mismatch remains an explicit warning and must be reconciled before trusting the workspace-local model file for demo restore.
