# AI-Sentinel

AI-Sentinel is a graduation-project surveillance system with a FastAPI backend for violence/threat inference and a Next.js frontend for the live dashboard and alert review workflow.

## Current Stable Runtime Reference

- `FINAL_LIVE_ALERT_API_CHECK: PASS`
- `SAFE_TO_RUN_LIVE_DEMO: True`
- `VIOLENCE_CLS = 1`
- Live Alert Decision Layer V2 is the intended stable decision policy.
- Stable runtime reference model SHA256:
  `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`
- Workspace-local `backend/best_model.pt` SHA256 at freeze time:
  `1fb38eeb54821d827a4621ac3fce4ad98488bc05fbf99df9ab78a13ed223b6cb`

Important: the local `backend/best_model.pt` file in this workspace does not match the documented stable runtime SHA above. Treat the documented SHA as the reference for Colab restore and verify the canonical model file before the next live demo.

## Safety Rule

The visible red alert must be controlled by `confirmed_alert` / `confirmedAlert`, not by `model_prediction`. `model_prediction` is internal runtime telemetry only.

## Project Layout

- Backend source: `backend/`
- Frontend source: `app/`, `components/`, `hooks/`, `lib/`, `public/`, `styles/`
- Frontend preservation note: see `frontend/README.md`
- Notebooks: `notebooks/`
- Documentation: `docs/`
- Preservation manifests: `manifests/`
- Freeze reports: `reports/`

## Restore Runtime In Colab

1. Upload or extract the GitHub-safe project archive into `/content/ai-sentinel`.
2. Copy the canonical `best_model.pt` from Google Drive into `/content/ai-sentinel/backend/best_model.pt`.
3. Verify SHA256 against the stable runtime reference:

```python
import hashlib
from pathlib import Path

model_path = Path("/content/ai-sentinel/backend/best_model.pt")
sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
print(sha)
assert sha == "2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01"
```

4. If the runtime was reset and the decision-layer files were lost, restore:
   - `backend/live_alert_decision.py`
   - `backend/api.py`
5. Run the backend verification notebook:
   - `notebooks/colab_verify_live_alert_decision_layer.ipynb`

See `docs/01_RUNTIME_RESTORE_GUIDE.md` for the full restore checklist.

## Run Backend

From the project root:

```powershell
cd backend
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Expected verification endpoints:

- `GET /health`
- `GET /system/status`
- `POST /decision_layer/reset`

## Run Live Demo

1. Start the backend.
2. Start the frontend from the project root:

```powershell
npm install
npm run dev
```

3. Open the dashboard.
4. Confirm `/system/status` reports:
   - `violenceClassIndex = 1`
   - decision-layer thresholds are loaded
5. Reset the decision layer before the demo:

```powershell
curl -X POST http://localhost:8000/decision_layer/reset
```

See `docs/04_DEMO_RUNBOOK.md` for the full demo sequence.

## Model And GitHub Policy

- Do not train during preservation freeze.
- Do not change model weights during preservation freeze.
- Do not overwrite `best_model.pt`.
- Do not commit model weights to normal GitHub history.
- Do not rely on Git LFS unless it is explicitly approved and configured.
- The current `.gitattributes` documents recommended Git LFS patterns only; it does not enable LFS automatically.

## Key References

- [Project Status](/C:/Users/PCD/Downloads/Final%20Project%20AI%20Sentinel/docs/00_PROJECT_STATUS.md)
- [Runtime Restore Guide](/C:/Users/PCD/Downloads/Final%20Project%20AI%20Sentinel/docs/01_RUNTIME_RESTORE_GUIDE.md)
- [Live Alert Decision Layer V2](/C:/Users/PCD/Downloads/Final%20Project%20AI%20Sentinel/docs/02_LIVE_ALERT_DECISION_LAYER_V2.md)
- [Stage 12 External Eval](/C:/Users/PCD/Downloads/Final%20Project%20AI%20Sentinel/docs/03_STAGE12_EXTERNAL_EVAL.md)
- [Demo Runbook](/C:/Users/PCD/Downloads/Final%20Project%20AI%20Sentinel/docs/04_DEMO_RUNBOOK.md)
- [Troubleshooting](/C:/Users/PCD/Downloads/Final%20Project%20AI%20Sentinel/docs/05_TROUBLESHOOTING.md)
- [Model And Data Policy](/C:/Users/PCD/Downloads/Final%20Project%20AI%20Sentinel/docs/06_MODEL_AND_DATA_POLICY.md)
