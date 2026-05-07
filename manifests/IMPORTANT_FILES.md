# Important Files

## Canonical Runtime And Source

- `backend/api.py`
- `backend/live_alert_decision.py`
- `backend/inference.py`
- `backend/requirements.txt`
- `backend/tests/`
- `app/`
- `components/`
- `hooks/`
- `lib/`
- `public/`
- `styles/`

## Restore / Evaluation Assets

- `notebooks/colab_verify_live_alert_decision_layer.ipynb`
- `notebooks/colab_existing_dataset_probe.ipynb`
- `plans/stage12_ubi_fightsall_cells.md`
- `plans/stage12_external_dataset_test_cells.md`
- `live_alert_changes.patch`

## Preservation Docs

- `README.md`
- `CHANGELOG.md`
- `docs/00_PROJECT_STATUS.md`
- `docs/01_RUNTIME_RESTORE_GUIDE.md`
- `docs/02_LIVE_ALERT_DECISION_LAYER_V2.md`
- `docs/03_STAGE12_EXTERNAL_EVAL.md`
- `docs/04_DEMO_RUNBOOK.md`
- `docs/05_TROUBLESHOOTING.md`
- `docs/06_MODEL_AND_DATA_POLICY.md`
- `reports/*.json`
- `manifests/*.md`
- `manifests/FILE_MANIFEST_SHA256.csv`

## Critical Warning

- The documented stable runtime SHA256 and the current workspace-local `backend/best_model.pt` SHA256 do not match. Preserve both facts in all future handoffs until reconciled.
