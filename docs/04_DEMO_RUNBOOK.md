# Demo Runbook

## Before Demo Checklist

- Verify the canonical demo model file is available.
- Verify model SHA256 matches the documented stable runtime reference.
- Start backend successfully.
- Start frontend successfully.
- Confirm the dashboard is reading `confirmedAlert` / `confirmed_alert` only for the visible red alert.
- Reset the decision layer before the demo.
- Keep a normal greeting clip and a real violence clip ready for sanity checks.

### Telegram Pre-Demo Checklist
- [ ] `TELEGRAM_ENABLED=true` in `backend/.env`
- [ ] `TELEGRAM_BOT_TOKEN` is set and valid
- [ ] `TELEGRAM_CHAT_ID` is set correctly
- [ ] Bot is added to the target chat/group
- [ ] Bot has admin permissions (for groups)
- [ ] Backend started without Telegram errors
- [ ] `GET /system/status` shows `"telegram": {"configured": true}`
- [ ] Test message sent successfully via `POST /notifications/telegram/test`
- [ ] Message received in Telegram chat
- [ ] `TELEGRAM_MIN_ALERT_INTERVAL_SECONDS` set appropriately (60+ recommended)
- [ ] Verify no tokens exposed in logs or status endpoints

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

## Telegram Alert Testing During Demo

### Test Telegram Configuration
```bash
curl http://localhost:8002/system/status | jq '.notifications'
```

Expected: `"telegram": {"enabled": true, "configured": true}`

### Send Test Alert
```bash
curl -X POST http://localhost:8002/notifications/telegram/test \
  -H "Authorization: Bearer <admin_token>"
```

Verify message received in Telegram chat.

### Demo Violence Alert
1. Play violence clip to trigger detection
2. Confirm `confirmed_alert=true` in decision layer
3. Verify Telegram message received with format:
   ```
   AI-Sentinel Alert
   Type: violence
   Camera: CAM-01
   Time: <timestamp>
   Severity: high
   Confidence: <confidence>%
   Alert State: confirmed
   Confirmed: true
   Alert ID: <alert_id>
   ```

### Verify Alert Cooldown
- Send two rapid test alerts
- Only one should arrive (respects `TELEGRAM_MIN_ALERT_INTERVAL_SECONDS`)

## After Demo

- preserve any important logs, screenshots, or evidence clips separately
- do not retrain before committing or archiving the stable demo state
