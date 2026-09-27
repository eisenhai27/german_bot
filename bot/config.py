# -*- coding: utf-8 -*-
"""
Configuration for the German A1 study bot.

BOT_TOKEN must be set as an environment variable. Never hard-code it here.
"""
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# Optional but recommended for webhook mode: a random string you choose.
# set_webhook.py registers it with Telegram, and webhook_app.py rejects any
# request that doesn't carry it in the X-Telegram-Bot-Api-Secret-Token header.
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()

# Where the SQLite database file lives. On most hosts the working directory
# is writable; override with the DB_PATH env var if you need a specific path.
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot_data.db"))

# Folder containing vocabulary_data.json / grammar_data.json / grammar_questions.json
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# --- Learning rules (from the plan we agreed on) ---
PASS_THRESHOLD = 0.8          # 80% required to pass the Final Test and unlock the next lesson
FINAL_VOCAB_COUNT = 10        # vocab questions in a Final Test
FINAL_GRAMMAR_COUNT = 5       # grammar questions in a Final Test (0 if lesson has no grammar yet)
PRACTICE_BATCH_SIZE = 10      # questions per round in practice modes (MC / type-the-word)
MATCH_ROUND_SIZE = 5          # pairs per matching round
FLASHCARD_BATCH_SIZE = 10     # cards per flashcard round
MISSED_ROUND_SIZE = 10        # max items per "missed words" round

TOTAL_LEKTIONEN = 24

# The mini app is your own file: miniapp/index.html. It needs to live at a
# public HTTPS URL for Telegram to open it (Telegram can't load a file
# straight off your computer). Set it via the MINI_APP_URL env var once you have one — the
# simplest free option is GitHub Pages (see README.md). Leave blank to hide
# the "Open Study App" button until it's set.
MINI_APP_URL = os.environ.get("MINI_APP_URL", "").strip()
