# -*- coding: utf-8 -*-
"""
Minimal Telegram Bot API client built on plain HTTP requests.

We deliberately avoid the python-telegram-bot / aiogram frameworks here:
they're asyncio-based, which complicates deployment on simple hosts (e.g.
a synchronous Flask app on PythonAnywhere). Telegram's Bot API is just
plain JSON over HTTPS, so a thin requests-based wrapper is more portable
and easier to debug.
"""
import logging
import requests

from . import config

log = logging.getLogger("telegram_api")

BASE = "https://api.telegram.org"


def _url(method):
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Set it as an environment variable before running the bot.")
    return f"{BASE}/bot{config.BOT_TOKEN}/{method}"


def _post(method, payload, timeout=15):
    try:
        r = requests.post(_url(method), json=payload, timeout=timeout)
        data = r.json()
        if not data.get("ok"):
            log.warning("Telegram API error on %s: %s", method, data)
        return data
    except (requests.RequestException, ValueError) as e:
        # ValueError covers non-JSON responses (e.g. a 502 page from a proxy).
        log.error("Error calling %s: %s", method, e)
        return {"ok": False, "error": str(e)}


def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _post("sendMessage", payload)


def edit_message_text(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return _post("editMessageText", payload)


def answer_callback_query(callback_query_id, text=None, show_alert=False):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    return _post("answerCallbackQuery", payload)


def set_webhook(url, secret_token=None):
    payload = {"url": url}
    if secret_token:
        payload["secret_token"] = secret_token
    return _post("setWebhook", payload)


def delete_webhook():
    return _post("deleteWebhook", {})


def get_updates(offset=None, timeout=25):
    payload = {"timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    try:
        r = requests.get(_url("getUpdates"), params=payload, timeout=timeout + 10)
        return r.json()
    except (requests.RequestException, ValueError) as e:
        log.error("Error calling getUpdates: %s", e)
        return {"ok": False, "result": []}


def inline_keyboard(rows):
    """
    rows: list of rows, each row is a list of (text, data) tuples.
    `data` is normally a callback_data string. Pass a dict instead (e.g.
    {"web_app": {"url": "https://..."}}) to build a different button type,
    such as one that opens a Telegram Mini App.
    Returns a dict ready to be used as reply_markup.
    """
    out_rows = []
    for row in rows:
        out_row = []
        for text, data in row:
            if isinstance(data, dict):
                btn = {"text": text}
                btn.update(data)
            else:
                btn = {"text": text, "callback_data": data}
            out_row.append(btn)
        out_rows.append(out_row)
    return {"inline_keyboard": out_rows}
