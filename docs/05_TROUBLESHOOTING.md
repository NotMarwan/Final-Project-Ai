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

## Telegram Alert Issues

### Telegram Bot Token Empty
**Symptoms:**
- `GET /system/status` shows `"telegram": {"configured": false}`
- No alerts sent

**Solution:**
1. Verify `TELEGRAM_BOT_TOKEN` is set in `backend/.env`
2. Check token from @BotFather is correct
3. Restart backend

### Telegram Chat ID Empty
**Symptoms:**
- Configured but messages not received
- `"telegram": {"configured": true}` but no delivery

**Solution:**
1. Set `TELEGRAM_CHAT_ID` in `backend/.env`
2. Get chat ID using @userinfobot or getUpdates method
3. For groups, ensure bot is added and made admin

### Telegram Request Timed Out
**Symptoms:**
- `"lastSendStatus": "error"`
- `"lastError": "Telegram timeout after 8.0s"`

**Solution:**
1. Increase `TELEGRAM_TIMEOUT_SECONDS` in `.env` (try 15.0)
2. Check network connectivity to `api.telegram.org`
3. Verify no firewall blocking outbound HTTPS

### Bot Blocked by User
**Symptoms:**
- `"lastError": "Forbidden: bot was blocked by the user"`

**Solution:**
1. Unblock the bot in Telegram settings
2. Start a conversation with the bot before expecting alerts

### Chat Not Found
**Symptoms:**
- `"lastError": "Chat not found"`

**Solution:**
1. Verify `TELEGRAM_CHAT_ID` is correct
2. For groups: re-add bot to group
3. Ensure bot has permission to send messages

### Bot Not Member of Chat
**Symptoms:**
- `"lastError": "Bot is not a member of the chat"`

**Solution:**
1. Re-add bot to the group
2. Make bot an admin (required for some group settings)
3. Verify chat ID is for the correct group

### Alerts Not Sending (No Errors)
**Symptoms:**
- Telegram configured and connected
- No alerts received for violence events

**Solution:**
1. Verify `TELEGRAM_ENABLED=true`
2. Check `confirmed_alert=true` in decision layer
3. Verify `TELEGRAM_MIN_ALERT_INTERVAL_SECONDS` not too high
4. Check `TELEGRAM_MIN_SEVERITY` matches alert severity
5. Violence alerts ONLY sent when `confirmed_alert=true`

### Too Many Requests
**Symptoms:**
- `"lastError": "Too many requests: retry after X"`

**Solution:**
1. Increase `TELEGRAM_MIN_ALERT_INTERVAL_SECONDS` (recommend 60+)
2. Check for alert flooding in logs
3. Verify cooldown logic is working

### Token Exposed in Logs/Status
**Symptoms:**
- Bot token visible in logs or API responses

**Solution:**
1. Check `notifications.py` masks token in status responses
2. Never print token in code or logs
3. Rotate token if exposed (use @BotFather `/mybots` → Revoke token)

### Verify Telegram Configuration
```bash
curl http://localhost:8002/system/status | jq '.notifications'
```

### Test Telegram Connectivity
```bash
curl -X POST http://localhost:8002/notifications/telegram/test \
  -H "Authorization: Bearer <admin_token>"
```

## What To Re-run

- verification notebook:
  - `notebooks/colab_verify_live_alert_decision_layer.ipynb`
- backend status check:
  - `GET /system/status`
- decision-layer reset:
  - `POST /decision_layer/reset`
- Telegram test:
  - `POST /notifications/telegram/test`
