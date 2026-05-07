# Demo Runbook

## Before Demo Checklist

- Verify the canonical demo model file is available.
- Verify model SHA256 matches the documented stable runtime reference.
- Start backend successfully.
- Start frontend successfully.
- Confirm the dashboard is reading `confirmedAlert` / `confirmed_alert` only for the visible red alert.
- Reset the decision layer before the demo.
- Keep a normal greeting clip and a real violence clip ready for sanity checks.

## Start Backend

```powershell
cd backend
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

## Check `/system/status`

Verify:

- `health = ok`
- `model.violenceClassIndex = 1`
- decision-layer thresholds are loaded
- no runtime import failure is blocking decision-layer state reporting

## Reset Decision Layer Endpoint

```powershell
curl -X POST http://localhost:8000/decision_layer/reset
```

Expected result:

- state resets to `NORMAL`
- rolling history clears
- cooldown clears

## Normal Greeting Expected Result

- final state should remain `NORMAL` or briefly `WATCH`
- `confirmed_alert = false`
- visible red alert must remain off

## Real Violence Expected Result

- state should move through `WATCH`
- then reach `CONFIRMED_VIOLENCE`
- `confirmed_alert = true`
- visible red alert turns on only after confirmation

## Dashboard Rule

The dashboard must use `confirmedAlert` / `confirmed_alert` only. It must not use `model_prediction` for the visible red alert.

## After Demo

- preserve any important logs, screenshots, or evidence clips separately
- do not retrain before committing or archiving the stable demo state
