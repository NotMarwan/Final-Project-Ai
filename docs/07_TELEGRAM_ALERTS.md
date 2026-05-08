# AI-Sentinel Telegram Alerts Documentation

## Purpose

The AI-Sentinel Telegram alert system provides real-time notifications for security events detected by the AI-Sentinel surveillance system. Alerts are sent directly to a Telegram chat when violence, weapon, or danger events are confirmed, enabling rapid response to security incidents.

## Environment Variables

Configure Telegram alerts using the following environment variables in `backend/.env`:

```bash
# Enable/disable Telegram alerts (default: false)
TELEGRAM_ENABLED=false

# Telegram bot token from @BotFather (required when enabled)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Chat ID where alerts will be sent (required when enabled)
TELEGRAM_CHAT_ID=your_chat_id_here

# Timeout for Telegram API requests in seconds (default: 8.0)
TELEGRAM_TIMEOUT_SECONDS=8.0

# Minimum interval between alerts in seconds (default: 60)
# Prevents alert flooding
TELEGRAM_MIN_ALERT_INTERVAL_SECONDS=60

# Send test message on backend startup (default: false)
TELEGRAM_SEND_TEST_ON_STARTUP=false

# Minimum severity level for alerts (default: high)
TELEGRAM_MIN_SEVERITY=high
```

## Bot Setup

### Creating a Telegram Bot with @BotFather

1. Open Telegram and search for `@BotFather`
2. Start a conversation and send `/newbot`
3. Choose a name for your bot (e.g., "AI-Sentinel Alerts")
4. Choose a username ending in `bot` (e.g., `ai_sentinel_alerts_bot`)
5. BotFather will return a token like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
6. Copy this token and set it as `TELEGRAM_BOT_TOKEN` in your `.env` file

**Important:** The bot token is like a password - keep it secret!

## Chat ID Setup

### Getting Your Chat ID

**Method 1: Using the Bot**
1. Add your bot to a Telegram group or start a private chat with it
2. Send a message to the bot
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Look for `"chat":{"id":...}` in the JSON response
5. Copy the chat ID and set it as `TELEGRAM_CHAT_ID`

**Method 2: Using @userinfobot**
1. Search for `@userinfobot` on Telegram
2. Start a conversation and send any message
3. The bot will reply with your user ID (this is your chat ID for private chats)

**For Group Chats:**
- Add the bot to your group
- Make the bot an admin (required to send messages)
- Use Method 1 above to get the group chat ID (negative number for groups)

## Windows/Linux Setup

### Windows Setup

1. Copy `backend/.env.example` to `backend/.env`:
   ```cmd
   copy backend\.env.example backend\.env
   ```

2. Edit `backend/.env` with your Telegram credentials:
   ```
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=your_actual_token
   TELEGRAM_CHAT_ID=your_actual_chat_id
   ```

3. Install dependencies (if not already installed):
   ```cmd
   cd backend
   pip install -r requirements.txt
   ```

4. Start the backend:
   ```cmd
   python api.py
   ```

### Linux/macOS Setup

1. Copy `backend/.env.example` to `backend/.env`:
   ```bash
   cp backend/.env.example backend/.env
   ```

2. Edit `backend/.env` with your Telegram credentials:
   ```bash
   nano backend/.env
   ```

3. Install dependencies (if not already installed):
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. Start the backend:
   ```bash
   python3 api.py
   ```

## Testing Steps

### 1. Verify Configuration

Check that Telegram is properly configured via the system status endpoint:

```bash
curl http://localhost:8002/system/status | jq '.notifications'
```

Expected output when configured:
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

### 2. Send Test Message

Send a test message using the admin endpoint:

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

You should receive "AI-Sentinel Telegram test message" in your Telegram chat.

### 3. Test Violence Alert

Trigger a violence detection event (via camera or test):

Expected message format:
```
AI-Sentinel Alert
Type: violence
Camera: CAM-01
Time: 2026-05-07T23:40:00Z
Severity: high
Confidence: 87.5%
Alert State: confirmed
Confirmed: true
Alert ID: abc123
```

### 4. Test Weapon/Danger Alerts

Weapon and danger alerts use `weapon_alert` and `danger_alert` flags respectively.

## Expected Outputs

### Successful Alert Delivery
- Message appears in Telegram chat with all fields populated
- System status shows `"lastSendStatus": "success"`
- No errors in backend logs

### Configuration Not Set
```json
{
  "telegram": {
    "enabled": false,
    "configured": false,
    "lastSendStatus": null,
    "lastError": null,
    "lastSentAt": null,
    "minAlertIntervalSeconds": 60,
    "provider": "telegram"
  }
}
```

### Failed Delivery
```json
{
  "telegram": {
    "enabled": true,
    "configured": true,
    "lastSendStatus": "error",
    "lastError": "Telegram timeout after 8.0s",
    "lastSentAt": null,
    "minAlertIntervalSeconds": 60,
    "provider": "telegram"
  }
}
```

## Common Failures and Solutions

### 1. "Telegram bot token is empty"
**Cause:** `TELEGRAM_BOT_TOKEN` not set in `.env`  
**Solution:** Set the token from @BotFather

### 2. "Telegram chat ID is empty"
**Cause:** `TELEGRAM_CHAT_ID` not set in `.env`  
**Solution:** Get chat ID using methods described above

### 3. "Telegram request timed out"
**Cause:** Network issues or timeout too low  
**Solution:** Increase `TELEGRAM_TIMEOUT_SECONDS` or check network connectivity

### 4. "Forbidden: bot was blocked by the user"
**Cause:** User blocked the bot  
**Solution:** Unblock the bot in Telegram settings

### 5. "Chat not found"
**Cause:** Invalid chat ID or bot not added to group  
**Solution:** Verify chat ID and ensure bot is added to the chat

### 6. "Bot is not a member of the chat"
**Cause:** Bot was removed from group  
**Solution:** Re-add bot to the group and make it admin

### 7. Alerts not sending (no errors)
**Cause:** `TELEGRAM_ENABLED=false` or `confirmed_alert` not true  
**Solution:** Set `TELEGRAM_ENABLED=true` and ensure alerts are confirmed

### 8. "Too many requests"
**Cause:** Hit Telegram rate limits  
**Solution:** Increase `TELEGRAM_MIN_ALERT_INTERVAL_SECONDS`

## Message Format

All Telegram alerts follow this format:

```
AI-Sentinel Alert
Type: <alert type>
Camera: <camera id>
Time: <timestamp>
Severity: <severity>
Confidence: <confidence>%
Alert State: <alert_state>
Confirmed: <confirmed_alert>
Alert ID: <alert_id>
```

**Alert Types:**
- `violence` - Violence detected
- `weapon_alert` - Weapon detected
- `danger_alert` - Danger detected

## Security Warnings

⚠️ **CRITICAL SECURITY WARNINGS** ⚠️

- **NEVER commit `.env` file to version control**
- **NEVER hardcode `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` in `config.yml` or source code**
- **Ensure `config.yml` is listed in `.gitignore`**
- **Telegram bot token is like a password - keep it secret**
- **Use `.env.example` as template, copy to `.env` and fill in values**
- **Status endpoints never expose token values** - they are masked in responses
- **Do not share screenshots containing bot tokens**
- **Rotate bot token if accidentally exposed (use @BotFather `/mybots` → Revoke token)**

## Pre-Demo Checklist

Verify these items before demonstrating Telegram alerts:

- [ ] `TELEGRAM_ENABLED=true` in `.env`
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

## Alert Logic

Telegram alerts are sent based on the following rules:

1. **Violence Alerts:** Sent ONLY when `confirmed_alert=true`
2. **Weapon Alerts:** Sent when `weapon_alert=true`
3. **Danger Alerts:** Sent when `danger_alert=true`

All alerts respect the minimum interval setting (`TELEGRAM_MIN_ALERT_INTERVAL_SECONDS`) to prevent flooding.

## Frontend Integration

The frontend displays Telegram status via the `TelegramStatus` component at [`components/telegram-status.tsx`](components/telegram-status.tsx). It shows:
- Connection status (connected/disconnected)
- Last message status
- Configuration warnings
- Quick test button (admin only)
