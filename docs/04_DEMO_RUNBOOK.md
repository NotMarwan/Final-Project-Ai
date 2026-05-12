# Demo Runbook - AI-Sentinel Telegram Alerts

## Before Demo Checklist

### System Preparation
- [ ] Backend started successfully with Telegram enabled
- [ ] Frontend started and accessible
- [ ] Verify model SHA256 matches documented stable runtime reference
- [ ] Reset decision layer before demo: `POST /decision_layer/reset`

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
- [ ] Test a violence alert to confirm full message format
- [ ] Confirm alert cooldown works (send two rapid alerts, only one should arrive)

## Start Backend

```powershell
cd backend
python api.py
```

Or with uvicorn:
```powershell
cd backend
python -m uvicorn api:app --host 0.0.0.0 --port 8002 --reload
```

## Check System Status

Verify Telegram configuration:
```bash
curl http://localhost:8002/system/status | jq '.notifications'
```

Expected output:
```json
{
  "telegram": {
    "enabled": true,
    "configured": true,
    "lastSendStatus": "success",
    "lastError": null,
    "lastSentAt": "2026-05-07T23:40:00Z",
    "minAlertIntervalSeconds": 60,
    "provider": "telegram"
  }
}
```

## Reset Decision Layer Endpoint

```bash
curl -X POST http://localhost:8002/decision_layer/reset
```

Expected result:
- state resets to `NORMAL`
- rolling history clears
- cooldown clears

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

Expected response:
```json
{
  "status": "sent",
  "message": "AI-Sentinel Telegram test message"
}
```

Verify message received in Telegram chat: "AI-Sentinel Telegram test message"

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

### Demo Weapon/Danger Alerts
- Weapon detection triggers `weapon_alert` messages
- Danger detection triggers `danger_alert` messages

### Verify Alert Cooldown
- Send two rapid test alerts
- Only one should arrive (respects `TELEGRAM_MIN_ALERT_INTERVAL_SECONDS`)

## Normal Greeting Expected Result

- final state should remain `NORMAL` or briefly `WATCH`
- `confirmed_alert = false`
- no Telegram alert sent
- visible red alert must remain off

## Real Violence Expected Result

- state should move through `WATCH`
- then reach `CONFIRMED_VIOLENCE`
- `confirmed_alert = true`
- Telegram alert sent automatically
- visible red alert turns on only after confirmation

## Dashboard Rule

The dashboard must use `confirmedAlert` / `confirmed_alert` only. It must not use `model_prediction` for the visible red alert. The `TelegramStatus` component at [`components/telegram-status.tsx`](components/telegram-status.tsx) displays Telegram connection status.

## After Demo

- preserve any important logs, screenshots, or evidence clips separately
- do not retrain before committing or archiving the stable demo state
- check Telegram last send status: `GET /system/status`
