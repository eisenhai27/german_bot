# -*- coding: utf-8 -*-
"""
Run this ONCE after your webhook app is deployed and reachable, to tell
Telegram where to send updates.

Usage:
    python set_webhook.py https://yourusername.pythonanywhere.com
"""
import sys

from bot import telegram_api as tg, config

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python set_webhook.py https://your-public-url")
        sys.exit(1)
    if not config.BOT_TOKEN:
        print("BOT_TOKEN is not set. Set it as an environment variable first.")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    full_url = f"{base_url}/webhook/{config.BOT_TOKEN}"
    result = tg.set_webhook(full_url, secret_token=config.WEBHOOK_SECRET or None)
    print(result)
    if result.get("ok"):
        print(f"\nWebhook set to: {full_url}")
    else:
        print("\nSomething went wrong — check the URL and your BOT_TOKEN.")
