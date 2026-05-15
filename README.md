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
- **Live Alert Decision Layer**: Multi-signal confirmation with motion, weapon, and fusion analysis
- **Groq VLM Forensic Reports**: AI-generated incident descriptions in Arabic

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
| `GROQ_API_KEY` | Groq API key for VLM forensic reports | - |

## API Endpoints

### System Status
```
GET /system/status
```
Returns system health including Telegram configuration status and decision layer state.

### Telegram Test
```
POST /notifications/telegram/test
Authorization: Bearer <admin_token>
```
Sends a test message to verify Telegram configuration.

### Face Policy
```
GET /face/policy
```
Returns current face recognition policy settings.

```
POST /face/policy
```
Updates face recognition policy (identity labeling, audit enabled, cooldown).

### Video Feed
```
GET /video_feed?camera_id=<camera_id>
```
Streams MJPEG video feed from specified camera.

### Decision Layer
```
POST /decision_layer/reset
```
Resets the live alert decision layer to initial state.

## Security

⚠️ **Important Security Notes:**
- Never commit `.env` file to version control
- Keep Telegram bot token secret (like a password)
- Use `.env.example` as template, copy to `.env` and fill in values
- Ensure `config.yml` is in `.gitignore`
- Rotate token if accidentally exposed

## Model And GitHub Policy

- Do not train during preservation freeze.
- Do not change model weights during preservation freeze.
- Do not overwrite `best_model.pt`.
- Do not commit model weights to normal GitHub history.
- Do not rely on Git LFS unless it is explicitly approved and configured.
- The current `.gitattributes` documents recommended Git LFS patterns only; it does not enable LFS automatically.

## Documentation

- [Project Status](docs/00_PROJECT_STATUS.md)
- [Runtime Restore Guide](docs/01_RUNTIME_RESTORE_GUIDE.md)
- [Live Alert Decision Layer V2](docs/02_LIVE_ALERT_DECISION_LAYER_V2.md)
- [Stage 12 External Eval](docs/03_STAGE12_EXTERNAL_EVAL.md)
- [Demo Runbook](docs/04_DEMO_RUNBOOK.md)
- [Troubleshooting](docs/05_TROUBLESHOOTING.md)
- [Model And Data Policy](docs/06_MODEL_AND_DATA_POLICY.md)
- [Telegram Alerts Setup](docs/07_TELEGRAM_ALERTS.md)

## License

[Add your license information here]
