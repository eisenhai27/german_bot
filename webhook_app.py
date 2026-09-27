# -*- coding: utf-8 -*-
"""
Webhook entry point. Telegram will POST every update to this URL.

Use this on hosts that give you a public HTTPS URL but don't let you run
an endless background loop (e.g. PythonAnywhere's free tier). See README.md
for the full setup.
"""
import hmac
import logging

from flask import Flask, abort, request, jsonify

from bot import db, handlers, config

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
db.init_db()

# The token in the path makes the webhook URL hard to guess for anyone
# scanning for open endpoints. If WEBHOOK_SECRET is set, we additionally
# require Telegram's secret_token header on every request.
WEBHOOK_PATH = f"/webhook/{config.BOT_TOKEN}"


@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    if config.WEBHOOK_SECRET and not hmac.compare_digest(
        request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), config.WEBHOOK_SECRET
    ):
        abort(403)
    update = request.get_json(force=True, silent=True) or {}
    handlers.handle_update(update)
    return jsonify({"ok": True})


@app.route("/")
def index():
    return "German A1 study bot is running."


if __name__ == "__main__":
    # Only used for local testing. On PythonAnywhere, the WSGI file points
    # at this Flask `app` object directly instead of running this block.
    app.run(host="0.0.0.0", port=5000)
