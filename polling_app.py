# -*- coding: utf-8 -*-
"""
Polling entry point: the bot repeatedly asks Telegram "anything new?"
Use this if you're running the bot on something you keep online yourself
(a VPS, Oracle Cloud's free tier, a Raspberry Pi, or Termux on Android).
No public URL is needed for this mode. See README.md.
"""
import logging
import time

from bot import db, handlers, telegram_api as tg

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("polling")


def main():
    db.init_db()
    tg.delete_webhook()  # a bot can only use one mode at a time
    log.info("Bot started in polling mode. Press Ctrl+C to stop.")
    offset = None
    while True:
        resp = tg.get_updates(offset=offset, timeout=25)
        if not resp.get("ok"):
            time.sleep(2)
            continue
        for update in resp.get("result", []):
            offset = update["update_id"] + 1
            handlers.handle_update(update)


if __name__ == "__main__":
    main()
