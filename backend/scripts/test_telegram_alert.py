#!/usr/bin/env python3
"""
Fallback script to test Telegram alert functionality.
This script can be run manually: python backend/scripts/test_telegram_alert.py

Security notes:
- Never prints Telegram bot token or chat ID
- Reads configuration from environment variables or config.yml
"""

import os
import sys
import json
from datetime import datetime, timezone

# Add parent directory to path so we can import notifications
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from notifications import TelegramNotifier, TelegramNotificationConfig
except ImportError:
    print("Error: Cannot import TelegramNotifier. Make sure you're running from the project root.")
    sys.exit(1)


def main():
    """Send a test Telegram message and report the result."""
    print("AI-Sentinel Telegram Test Script")
    print("=" * 40)
    
    # Load configuration from environment/config
    notifier = TelegramNotifier.from_settings(None)  # Reads from env vars
    
    # Check configuration
    config = notifier.config
    print(f"Telegram enabled: {config.enabled}")
    print(f"Token configured: {bool(config.bot_token)}")
    print(f"Chat ID configured: {bool(config.chat_id)}")
    print(f"Ready: {config.ready}")
    print()
    
    if not config.ready:
        result = {
            "success": False,
            "provider": "telegram",
            "configured": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": "not_configured"
        }
        print("FAILURE: Telegram is not properly configured.")
        print(f"Response: {json.dumps(result, indent=2)}")
        return result
    
    # Send test message
    print("Sending test message: 'AI-Sentinel Telegram test message'...")
    test_result = notifier.send_test_message()
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    if test_result.get("success"):
        result = {
            "success": True,
            "provider": "telegram",
            "configured": True,
            "timestamp": timestamp
        }
        print("SUCCESS: Test message sent!")
    else:
        error_msg = test_result.get("error", "unknown_error")
        result = {
            "success": False,
            "provider": "telegram",
            "configured": True,
            "timestamp": timestamp,
            "error": error_msg
        }
        print(f"FAILURE: {error_msg}")
    
    print(f"Response: {json.dumps(result, indent=2)}")
    return result


if __name__ == "__main__":
    main()
