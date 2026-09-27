# -*- coding: utf-8 -*-
"""
Simulates a user talking to the bot, without any network access, by
monkeypatching telegram_api's send/edit/answer functions to just record
what would have been sent. This exercises the real handlers/db/quiz_engine
code paths so we can catch bugs before deploying anywhere.
"""
import os
import sys
import random
import tempfile

# Emoji in the output would crash on Windows consoles using a legacy codepage.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TEST_DB = os.path.join(tempfile.gettempdir(), "test_bot.db")

sys.path.insert(0, os.path.dirname(__file__))
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["DB_PATH"] = TEST_DB

if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

from bot import telegram_api as tg  # noqa: E402
from bot import db, handlers, quiz_engine, data_loader, config  # noqa: E402

SENT = []


def fake_send_message(chat_id, text, reply_markup=None, parse_mode=None):
    SENT.append({"type": "send", "chat_id": chat_id, "text": text, "reply_markup": reply_markup})
    return {"ok": True, "result": {"message_id": len(SENT)}}


def fake_edit_message_text(chat_id, message_id, text, reply_markup=None):
    SENT.append({"type": "edit", "chat_id": chat_id, "text": text, "reply_markup": reply_markup})
    return {"ok": True}


def fake_answer_callback_query(callback_query_id, text=None, show_alert=False):
    return {"ok": True}


tg.send_message = fake_send_message
tg.edit_message_text = fake_edit_message_text
tg.answer_callback_query = fake_answer_callback_query

USER = {"id": 111, "username": "tester", "first_name": "Tester"}
CHAT = {"id": 111}


def msg_update(text):
    return {"message": {"chat": CHAT, "from": USER, "text": text}}


def cb_update(data, message_id=1):
    return {"callback_query": {"id": "cbq1", "from": USER, "data": data,
                                "message": {"chat": CHAT, "message_id": message_id}}}


def last_text():
    return SENT[-1]["text"] if SENT else None


def last_buttons():
    rm = SENT[-1].get("reply_markup")
    if not rm:
        return []
    # skip non-callback buttons (e.g. web_app) — this helper is only used to
    # find/verify callback-driven navigation buttons in tests
    return [(b["text"], b["callback_data"]) for row in rm["inline_keyboard"] for b in row if "callback_data" in b]


def find_callback_by_prefix(prefix):
    for text, cb in last_buttons():
        if cb.startswith(prefix):
            return cb
    return None


def run_mc_quiz_answering_all_correctly(lektion, mode_code):
    """Drives a full quiz where we always click the button holding the correct answer."""
    handlers.handle_update(cb_update(f"go:{lektion}:{mode_code}"))
    steps = 0
    while True:
        session = db.load_session(USER["id"])
        if session is None:
            break
        q = session["questions"][session["index"]]
        idx = session["index"]
        assert q["kind"] in ("vocab_mc", "grammar_mc")
        correct_cb = f"mc:{idx}:{q['correct_index']}"
        handlers.handle_update(cb_update(correct_cb))
        steps += 1
        if steps > 100:
            raise RuntimeError("infinite loop suspected")
    return SENT[-1]["text"]


def main():
    db.init_db()
    print("== /start ==")
    handlers.handle_update(msg_update("/start"))
    assert "Welcome" in last_text()
    buttons = last_buttons()
    assert buttons[0] == ("🔓1", "lek:1")
    assert buttons[1][0].startswith("🔒"), "Lektion 2 should start locked"
    print("OK: lesson menu shows 1 unlocked, others locked")

    print("\n== Open Lektion 1 menu ==")
    handlers.handle_update(cb_update("lek:1"))
    assert "Lektion 1" in last_text()
    has_grammar_button = find_callback_by_prefix("go:1:grammar")
    assert has_grammar_button, "Lektion 1 should offer a grammar quiz"
    print("OK: lektion menu shows vocabulary + grammar + final test")

    print("\n== Vocabulary submenu ==")
    handlers.handle_update(cb_update("vocmenu:1"))
    assert "Vocabulary practice" in last_text()
    assert find_callback_by_prefix("go:1:mc")
    assert find_callback_by_prefix("go:1:type")
    assert find_callback_by_prefix("go:1:match")
    assert find_callback_by_prefix("go:1:flash")
    assert find_callback_by_prefix("go:1:missed")
    print("OK: all 5 vocab modes present")

    print("\n== Multiple choice: answer everything correctly ==")
    final_text = run_mc_quiz_answering_all_correctly(1, "mc")
    assert "10/10" in final_text or "%" in final_text
    print("Result:", final_text.replace("\n", " | "))

    print("\n== Multiple choice: answer everything WRONG on purpose (to build missed list) ==")
    handlers.handle_update(cb_update("go:1:mc"))
    while True:
        session = db.load_session(USER["id"])
        if session is None:
            break
        q = session["questions"][session["index"]]
        idx = session["index"]
        wrong = 0 if q["correct_index"] != 0 else 1
        handlers.handle_update(cb_update(f"mc:{idx}:{wrong}"))
    missed = db.get_missed_ids(USER["id"], 1)
    print(f"Missed words recorded: {len(missed)}")
    assert len(missed) > 0

    print("\n== Missed words round should now be available ==")
    handlers.handle_update(cb_update("go:1:missed"))
    session = db.load_session(USER["id"])
    assert session is not None and session["mode"] == "vocab_missed"
    # answer all correctly this time to clear the missed list
    while True:
        session = db.load_session(USER["id"])
        if session is None:
            break
        q = session["questions"][session["index"]]
        idx = session["index"]
        handlers.handle_update(cb_update(f"mc:{idx}:{q['correct_index']}"))
    missed_after = db.get_missed_ids(USER["id"], 1)
    print(f"Missed words after clearing: {len(missed_after)}")

    print("\n== Type-the-word mode ==")
    handlers.handle_update(cb_update("go:1:type"))
    session = db.load_session(USER["id"])
    q = session["questions"][0]
    print("Prompt (Uzbek meaning):", q["prompt"], "-> expecting:", q["answer_display"])
    n_before = len(SENT)
    handlers.handle_update(msg_update(q["answer_display"]))
    # the handler sends feedback, THEN (via _advance) the next question/summary,
    # so the feedback is the first new message, not necessarily the last one.
    feedback = SENT[n_before]["text"]
    assert "Correct" in feedback, feedback
    print("OK: exact match accepted ->", feedback)
    # test normalization: umlaut-less / different case
    session = db.load_session(USER["id"])
    if session:
        q2 = session["questions"][session["index"]]
        variant = q2["answer_display"].upper()
        n_before = len(SENT)
        handlers.handle_update(msg_update(variant))
        print("Uppercase variant ->", SENT[n_before]["text"].splitlines()[0])

    print("\n== Matching mode ==")
    # flush any active session first
    db.clear_session(USER["id"])
    handlers.handle_update(cb_update("go:1:match"))
    session = db.load_session(USER["id"])
    q = session["questions"][0]
    correct_answer = " ".join(f"{num}{letter}" for num, letter in q["correct_letter"].items())
    print("Auto-solved answer string:", correct_answer)
    n_before = len(SENT)
    handlers.handle_update(msg_update(correct_answer))
    feedback = SENT[n_before]["text"]
    assert "matched" in feedback.lower(), feedback
    print("Result:", feedback, "|", last_text())

    print("\n== Flashcards ==")
    db.clear_session(USER["id"])
    handlers.handle_update(cb_update("go:1:flash"))
    session = db.load_session(USER["id"])
    idx = session["index"]
    handlers.handle_update(cb_update(f"flash:{idx}:show"))
    assert "\n= " in last_text()  # card flipped in place
    handlers.handle_update(cb_update(f"flash:{idx}:know"))
    print("OK: flashcard flow (show -> know) works")

    print("\n== Grammar quiz ==")
    db.clear_session(USER["id"])
    final_text = run_mc_quiz_answering_all_correctly(1, "grammar")
    print("Result:", final_text.replace("\n", " | "))

    print("\n== Final test: fail on purpose, confirm Lektion 2 stays locked ==")
    handlers.handle_update(cb_update("go:1:final"))
    while True:
        session = db.load_session(USER["id"])
        if session is None:
            break
        q = session["questions"][session["index"]]
        idx = session["index"]
        wrong = 0 if q["correct_index"] != 0 else 1
        handlers.handle_update(cb_update(f"mc:{idx}:{wrong}"))
    print("Result:", last_text().replace("\n", " | "))
    assert not db.get_progress(USER["id"], 1)["passed"]
    assert not db.is_unlocked(USER["id"], 2)
    print("OK: failing the final test does not unlock Lektion 2")

    print("\n== Final test: pass, confirm Lektion 2 unlocks ==")
    final_text = run_mc_quiz_answering_all_correctly(1, "final")
    print("Result:", final_text.replace("\n", " | "))
    assert db.get_progress(USER["id"], 1)["passed"]
    assert db.is_unlocked(USER["id"], 2)
    print("OK: passing the final test (>=80%) unlocks Lektion 2")

    print("\n== Lektion 2 should now be reachable, Lektion 3 still locked ==")
    handlers.handle_update(cb_update("lek:2"))
    assert "locked" not in last_text().lower()
    handlers.handle_update(cb_update("lek:3"))
    assert "locked" in last_text().lower()
    print("OK")

    print("\n== Lektion with vocab only (no grammar yet), e.g. Lektion 13 ==")
    # force-unlock 13 for this test by marking 1..12 passed
    for n in range(1, 13):
        db.record_final_attempt(USER["id"], n, 1.0)
    assert db.is_unlocked(USER["id"], 13)
    handlers.handle_update(cb_update("lek:13"))
    assert "isn't added yet" in last_text()
    assert find_callback_by_prefix("go:13:grammar") is None
    print("OK: Lektion 13 hides the grammar option and final test will be vocab-only")
    db.clear_session(USER["id"])
    handlers.handle_update(cb_update("go:13:final"))
    session = db.load_session(USER["id"])
    assert session["total"] == config.FINAL_VOCAB_COUNT + config.FINAL_GRAMMAR_COUNT
    print(f"OK: Lektion 13 final test has {session['total']} vocab-only questions")

    print("\nALL OFFLINE TESTS PASSED")


if __name__ == "__main__":
    random.seed(42)
    main()
