# -*- coding: utf-8 -*-
"""
All persistent state for the bot lives in a small SQLite database:

- users            : who has talked to the bot
- progress         : per user, per lektion -> best final-test score & pass/fail
- missed_words     : per user, per lektion -> vocabulary item ids the user got wrong
- sessions         : per user -> the currently active quiz, serialized as JSON

SQLite is more than enough for a personal study tool, and it's a single
file, which is the simplest thing to run on a free host.
"""
import json
import sqlite3
import threading
from contextlib import contextmanager

from . import config

_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _cursor():
    with _lock:
        conn = _connect()
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        finally:
            conn.close()


def init_db():
    with _cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS progress (
                user_id INTEGER NOT NULL,
                lektion INTEGER NOT NULL,
                best_score REAL NOT NULL DEFAULT 0,
                passed INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, lektion)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS missed_words (
                user_id INTEGER NOT NULL,
                lektion INTEGER NOT NULL,
                word_id TEXT NOT NULL,
                PRIMARY KEY (user_id, lektion, word_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id INTEGER PRIMARY KEY,
                state_json TEXT NOT NULL
            )
        """)


# ---------- users ----------

def ensure_user(user_id, username=None):
    with _cursor() as cur:
        cur.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        if username:
            cur.execute(
                "UPDATE users SET username = ? WHERE user_id = ?",
                (username, user_id),
            )


# ---------- progress ----------

def get_progress(user_id, lektion):
    with _cursor() as cur:
        cur.execute(
            "SELECT best_score, passed, attempts FROM progress WHERE user_id = ? AND lektion = ?",
            (user_id, lektion),
        )
        row = cur.fetchone()
        if row is None:
            return {"best_score": 0.0, "passed": False, "attempts": 0}
        return {"best_score": row["best_score"], "passed": bool(row["passed"]), "attempts": row["attempts"]}


def record_final_attempt(user_id, lektion, score_fraction):
    """Record a Final Test attempt; updates best score and pass flag."""
    passed_now = score_fraction >= config.PASS_THRESHOLD
    current = get_progress(user_id, lektion)
    new_best = max(current["best_score"], score_fraction)
    new_passed = current["passed"] or passed_now
    with _cursor() as cur:
        cur.execute("""
            INSERT INTO progress (user_id, lektion, best_score, passed, attempts)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id, lektion) DO UPDATE SET
                best_score = excluded.best_score,
                passed = excluded.passed,
                attempts = progress.attempts + 1
        """, (user_id, lektion, new_best, int(new_passed)))
    return passed_now, new_best


def is_unlocked(user_id, lektion):
    if lektion <= 1:
        return True
    return get_progress(user_id, lektion - 1)["passed"]


def all_progress(user_id, total_lektionen):
    return {n: get_progress(user_id, n) for n in range(1, total_lektionen + 1)}


# ---------- missed words ----------

def add_missed(user_id, lektion, word_id):
    with _cursor() as cur:
        cur.execute(
            "INSERT OR IGNORE INTO missed_words (user_id, lektion, word_id) VALUES (?, ?, ?)",
            (user_id, lektion, word_id),
        )


def remove_missed(user_id, lektion, word_id):
    with _cursor() as cur:
        cur.execute(
            "DELETE FROM missed_words WHERE user_id = ? AND lektion = ? AND word_id = ?",
            (user_id, lektion, word_id),
        )


def get_missed_ids(user_id, lektion):
    with _cursor() as cur:
        cur.execute(
            "SELECT word_id FROM missed_words WHERE user_id = ? AND lektion = ?",
            (user_id, lektion),
        )
        return [r["word_id"] for r in cur.fetchall()]


# ---------- session state (the currently active quiz for a user) ----------

def save_session(user_id, state: dict):
    with _cursor() as cur:
        cur.execute("""
            INSERT INTO sessions (user_id, state_json) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET state_json = excluded.state_json
        """, (user_id, json.dumps(state, ensure_ascii=False)))


def load_session(user_id):
    with _cursor() as cur:
        cur.execute("SELECT state_json FROM sessions WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return json.loads(row["state_json"])


def clear_session(user_id):
    with _cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
