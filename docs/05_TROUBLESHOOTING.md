# Troubleshooting Guide - AI-Sentinel Telegram Alerts

> See also: [Telegram Alerts Setup](07_TELEGRAM_ALERTS.md) | [Demo Runbook](04_DEMO_RUNBOOK.md) | [API Reference](API_REFERENCE.md) | [Environment Variables](ENV_VARS.md) | [README](../README.md)

## Telegram-Specific Issues

### 1. Telegram Bot Token Empty

**Symptoms:**
- `GET /system/status` shows `"telegram": {"configured": false}`
- No alerts sent
- Backend logs show "Telegram bot token is empty"

**Cause:** `TELEGRAM_BOT_TOKEN` not set in `.env`

**Solution:**
1. Copy `.env.example` to `.env` (if not done):
   ```bash
   cp backend/.env.example backend/.env
   ```

2. Edit `backend/.env` and set your token:
   ```
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=your_actual_token_from_botfather
   ```

3. Restart the backend

4. Verify with:
   ```bash
   curl http://localhost:8002/system/status | jq '.notifications'
   ```

---

### 2. Telegram Chat ID Empty

**Symptoms:**
- Config shows `"configured": true` but no messages received
- `"lastSendStatus": "error"` with chat ID related errors

**Cause:** `TELEGRAM_CHAT_ID` not set in `.env`

**Solution:**
1. Get your chat ID using one of these methods:

   **Method A: Using @userinfobot**
   - Search for `@userinfobot` on Telegram
   - Start conversation and send any message
   - Bot replies with your user ID (use this as chat ID)

   **Method B: Using getUpdates API**
   - Send a message to your bot
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Look for `"chat":{"id":...}` in the JSON response

2. Set the chat ID in `backend/.env`:
   ```
   TELEGRAM_CHAT_ID=123456789
   ```

3. Restart backend and test

---

### 3. Telegram Request Timed Out

**Symptoms:**
- `"lastSendStatus": "error"`
- `"lastError": "Telegram timeout after 8.0s"`

**Cause:** Network issues or timeout too low

**Solution:**
1. Increase timeout in `backend/.env`:
   ```
   TELEGRAM_TIMEOUT_SECONDS=15.0
   ```

2. Check network connectivity:
   ```bash
   curl -I https://api.telegram.org
   ```

3. Verify no firewall blocking outbound HTTPS (port 443)

4. If using proxy, configure proxy settings for Python

---

### 4. Bot Blocked by User

**Symptoms:**
- `"lastError": "Forbidden: bot was blocked by the user"`

**Cause:** User blocked the bot in Telegram

**Solution:**
1. Open Telegram
2. Find the bot in your contacts/chats
3. Unblock the bot
4. Start a conversation with the bot (send `/start`)
5. Retry sending test message

---

### 5. Chat Not Found

**Symptoms:**
- `"lastError": "Chat not found"`

**Cause:** Invalid chat ID or bot removed from group

**Solution:**
1. Verify `TELEGRAM_CHAT_ID` is correct
2. For group chats:
   - Re-add bot to the group
   - Make bot an admin
   - Get new chat ID using getUpdates method
3. For private chats:
   - Ensure you've started a conversation with the bot

---

### 6. Bot Not Member of Chat

**Symptoms:**
- `"lastError": "Bot is not a member of the chat"`

**Cause:** Bot was removed from group

**Solution:**
1. Add bot back to the group
2. Grant admin permissions (some groups require this)
3. Verify chat ID matches the group
4. Test with a message to the group

---

### 7. Alerts Not Sending (No Errors)

**Symptoms:**
- Telegram configured and connected
- No alerts received for violence events
- No errors in logs

**Cause:** Alert conditions not met

**Solution:**
1. Verify `TELEGRAM_ENABLED=true` in `.env`

2. Check decision layer state:
   ```bash
   curl http://localhost:8002/system/status | jq '.decisionLayer'
   ```

3. Violence alerts ONLY sent when `confirmed_alert=true`

4. Check minimum severity setting:
   ```
   TELEGRAM_MIN_SEVERITY=high
   ```
   Ensure alert severity meets this threshold

5. Verify alert interval not blocking:
   ```
   TELEGRAM_MIN_ALERT_INTERVAL_SECONDS=60
   ```
   Wait 60 seconds between tests or lower this value

---

### 8. Too Many Requests

**Symptoms:**
- `"lastError": "Too many requests: retry after X"`

**Cause:** Hit Telegram rate limits

**Solution:**
1. Increase minimum interval between alerts:
   ```
   TELEGRAM_MIN_ALERT_INTERVAL_SECONDS=120
   ```

2. Check for alert flooding in logs

3. Verify cooldown logic is working correctly

4. Telegram rate limits: ~30 messages/second for bots

---

### 9. Token Exposed in Logs/Status

**Symptoms:**
- Bot token visible in logs or API responses
- Security concern

**Cause:** Code printing token or not masking properly

**Solution:**
1. Verify `notifications.py` masks token in status responses
2. Never print token in code or logs
3. Check `GET /system/status` response - token should NOT be exposed
4. If token was exposed:
   - Rotate token using @BotFather: `/mybots` → Select bot → API Token → Revoke token
   - Update `.env` with new token
   - Never commit `.env` to version control

---

## Verification Commands

### Check Telegram Configuration
```bash
curl http://localhost:8002/system/status | jq '.notifications'
```

Expected output when working:
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

### Send Test Message
```bash
curl -X POST http://localhost:8002/notifications/telegram/test \
  -H "Authorization: Bearer <admin_token>"
```

### Check Backend Logs for Telegram Errors
```bash
tail -f backend/logs/backend.log | grep -i telegram
```

## Security Warnings

⚠️ **CRITICAL SECURITY WARNINGS** ⚠️

- **NEVER commit `.env` file to version control**
- **NEVER hardcode `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` in `config.yml` or source code**
- **Ensure `config.yml` and `.env` are listed in `.gitignore`**
- **Telegram bot token is like a password - keep it secret**
- **Use `.env.example` as template, copy to `.env` and fill in values**
- **Status endpoints never expose token values** - they are masked in responses
- **Do not share screenshots containing bot tokens**
- **Rotate bot token if accidentally exposed (use @BotFather `/mybots` → Revoke token)**

## Common Configuration Issues

| Issue | Check | Fix |
|-------|-------|-----|
| Bot not responding | `TELEGRAM_ENABLED=true` | Set to `true` in `.env` |
| Token invalid | Token from @BotFather | Re-create bot if needed |
| Chat ID wrong | Use getUpdates method | Get correct chat ID |
| Timeout errors | `TELEGRAM_TIMEOUT_SECONDS` | Increase to 15.0 |
| Alerts flooding | `TELEGRAM_MIN_ALERT_INTERVAL_SECONDS` | Increase to 120 |
| Severity filter | `TELEGRAM_MIN_SEVERITY` | Lower to `medium` or `low` |
