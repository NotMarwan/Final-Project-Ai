# AI-Sentinel Surveillance System

AI-Sentinel is an intelligent surveillance system that uses AI to detect violence, weapons, and security threats in real-time video feeds. The system provides instant Telegram alerts, a web-based dashboard, and comprehensive incident reporting.

## Features

- **Real-time Violence Detection**: AI-powered detection of violent behavior in video feeds
- **Weapon Detection**: Identifies weapons in camera feeds
- **Danger Alert System**: Detects dangerous situations automatically
- **Telegram Alerts**: Instant notifications sent to security personnel via Telegram
- **Web Dashboard**: Modern React-based interface for monitoring cameras and alerts
- **Incident Reporting**: Automated report generation for security incidents
- **Multi-Camera Support**: Monitor multiple camera feeds simultaneously
- **Face Recognition**: Optional face identification and tracking (when enabled)
- **Evidence Capture**: Automatic clip recording and thumbnail generation

## Quick Start

1. Copy the environment file:
   ```bash
   cp backend/.env.example backend/.env
   ```

2. Configure your settings in `backend/.env` (see [Telegram Alerts Setup](#telegram-alerts) below)

3. Install dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. Start the backend:
   ```bash
   python api.py
   ```

5. Start the frontend:
   ```bash
   npm install
   npm run dev
   ```

## Telegram Alerts

AI-Sentinel can send real-time security alerts to Telegram. This feature enables instant notification of violence, weapon detection, and danger events.

### Setup

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather)
2. Get your chat ID (see [documentation](docs/07_TELEGRAM_ALERTS.md))
3. Configure environment variables in `backend/.env`:
   ```bash
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

### Documentation

For detailed setup instructions, testing steps, and troubleshooting, see:
- **[Telegram Alerts Documentation](docs/07_TELEGRAM_ALERTS.md)** - Complete setup and configuration guide
- **[Demo Runbook](docs/04_DEMO_RUNBOOK.md)** - Steps for demonstrating Telegram alerts
- **[Troubleshooting Guide](docs/05_TROUBLESHOOTING.md)** - Common issues and solutions

## Project Structure

```
├── backend/              # Python FastAPI backend
│   ├── api.py           # Main API server
│   ├── inference.py     # AI inference engine
│   ├── notifications.py # Telegram alert system
│   └── config.yml       # Backend configuration
├── components/          # React frontend components
│   ├── telegram-status.tsx  # Telegram status display
│   ├── alert-feed.tsx   # Live alert feed
│   └── video-player.tsx # Camera video player
├── app/                 # Next.js app directory
├── docs/                # Documentation
│   ├── 07_TELEGRAM_ALERTS.md  # Telegram setup guide
│   ├── 04_DEMO_RUNBOOK.md     # Demo instructions
│   └── 05_TROUBLESHOOTING.md  # Troubleshooting guide
└── public/              # Static assets
```

## Environment Variables

Key environment variables (see `backend/.env.example` for full list):

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_ENABLED` | Enable Telegram alerts | `false` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | - |
| `TELEGRAM_CHAT_ID` | Chat ID for alerts | - |
| `TELEGRAM_TIMEOUT_SECONDS` | API timeout | `8.0` |
| `TELEGRAM_MIN_ALERT_INTERVAL_SECONDS` | Min interval between alerts | `60` |
| `TELEGRAM_SEND_TEST_ON_STARTUP` | Send test on startup | `false` |

## API Endpoints

### System Status
```
GET /system/status
```
Returns system health including Telegram configuration status.

### Telegram Test
```
POST /notifications/telegram/test
Authorization: Bearer <admin_token>
```
Sends a test message to verify Telegram configuration.

## Security

⚠️ **Important Security Notes:**
- Never commit `.env` file to version control
- Keep Telegram bot token secret (like a password)
- Use `.env.example` as template, copy to `.env` and fill in values
- Ensure `config.yml` is in `.gitignore`

## Documentation

- [Telegram Alerts Setup](docs/07_TELEGRAM_ALERTS.md) - Complete Telegram configuration guide
- [Demo Runbook](docs/04_DEMO_RUNBOOK.md) - Pre-demo checklist and testing steps
- [Troubleshooting](docs/05_TROUBLESHOOTING.md) - Common issues and solutions

## License

[Add your license information here]
