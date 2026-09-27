# -*- coding: utf-8 -*-
"""
Routes incoming Telegram updates to the right logic. This module has no
knowledge of *how* updates arrive (webhook vs polling) — both entry points
just call handle_update(update).
"""
import logging

from . import config, db, data_loader, quiz_engine, telegram_api as tg

log = logging.getLogger("handlers")

HELP_TEXT = (
    "This bot only tests what you already studied — it doesn't teach.\n\n"
    "/menu - see your lessons\n"
    "/cancel - stop the current quiz\n"
    "/help - this message\n\n"
    "Each lektion has: Vocabulary practice (flashcards, multiple choice, "
    "matching, type-the-word, missed words), a Grammar quiz (where available), "
    "and a Final Test that mixes both. Score 80%+ on the Final Test to unlock "
    "the next lektion — you can retry it as many times as you need."
)

MODE_CODES = {
    "mc": "vocab_mc",
    "type": "vocab_type",
    "match": "vocab_match",
    "flash": "vocab_flash",
    "missed": "vocab_missed",
    "grammar": "grammar",
    "final": "final",
}


# --------------------------------------------------------------- entry point

def handle_update(update: dict):
    try:
        if "callback_query" in update:
            _handle_callback(update["callback_query"])
        elif "message" in update:
            _handle_message(update["message"])
    except Exception:
        log.exception("Error handling update: %s", update)


# --------------------------------------------------------------- messages

def _handle_message(message):
    chat_id = message["chat"]["id"]
    frm = message.get("from", {})
    user_id = frm.get("id")
    if user_id is None:
        return
    db.ensure_user(user_id, frm.get("username") or frm.get("first_name"))

    text = (message.get("text") or "").strip()

    if text.startswith("/start"):
        db.clear_session(user_id)
        _send_main_menu(chat_id, user_id, greeting=True)
        return
    if text.startswith("/menu"):
        db.clear_session(user_id)
        _send_main_menu(chat_id, user_id)
        return
    if text.startswith("/cancel"):
        db.clear_session(user_id)
        tg.send_message(chat_id, "Cancelled. Use /menu to see your lessons.")
        return
    if text.startswith("/help"):
        tg.send_message(chat_id, HELP_TEXT)
        return

    session = db.load_session(user_id)
    if not session:
        tg.send_message(chat_id, "No active quiz. Use /menu to pick a lesson.")
        return

    q = session["questions"][session["index"]]
    if q["kind"] == "vocab_type":
        _handle_type_answer(chat_id, user_id, session, q, text)
    elif q["kind"] == "vocab_match":
        _handle_match_answer(chat_id, user_id, session, q, text)
    else:
        tg.send_message(chat_id, "Please use the buttons above to answer this one.")


# --------------------------------------------------------------- callbacks

def _handle_callback(cbq):
    chat_id = cbq["message"]["chat"]["id"]
    message_id = cbq["message"]["message_id"]
    frm = cbq.get("from", {})
    user_id = frm.get("id")
    data = cbq.get("data", "")
    tg.answer_callback_query(cbq["id"])
    if user_id is None:
        return
    db.ensure_user(user_id, frm.get("username") or frm.get("first_name"))

    parts = data.split(":")
    action = parts[0]

    if action == "menu":
        db.clear_session(user_id)
        _send_main_menu(chat_id, user_id, edit_message_id=message_id)

    elif action == "lek":
        n = int(parts[1])
        _send_lektion_menu(chat_id, user_id, n, edit_message_id=message_id)

    elif action == "vocmenu":
        n = int(parts[1])
        _send_vocab_menu(chat_id, n, edit_message_id=message_id)

    elif action == "go":
        n, mode_code = int(parts[1]), parts[2]
        _start_session(chat_id, user_id, n, mode_code)

    elif action == "mc":
        q_index, choice = int(parts[1]), int(parts[2])
        _handle_mc_answer(chat_id, message_id, user_id, q_index, choice)

    elif action == "flash":
        q_index, sub = int(parts[1]), parts[2]
        _handle_flash_action(chat_id, message_id, user_id, q_index, sub)


# --------------------------------------------------------------- menus

def _send_or_edit(chat_id, edit_message_id, text, kb):
    if edit_message_id:
        res = tg.edit_message_text(chat_id, edit_message_id, text, reply_markup=kb)
        if res.get("ok"):
            return
    tg.send_message(chat_id, text, reply_markup=kb)


def _send_main_menu(chat_id, user_id, edit_message_id=None, greeting=False):
    total = data_loader.total_lektionen()
    rows = []
    if config.MINI_APP_URL:
        rows.append([("🛂 Open Study App", {"web_app": {"url": config.MINI_APP_URL}})])
    row = []
    for n in range(1, total + 1):
        p = db.get_progress(user_id, n)
        unlocked = db.is_unlocked(user_id, n)
        if p["passed"]:
            label = f"✅{n}"
        elif unlocked:
            label = f"🔓{n}"
        else:
            label = f"🔒{n}"
        row.append((label, f"lek:{n}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    text = "Your German A1 lessons\n✅ passed   🔓 unlocked   🔒 locked\n\nTap a lesson number:"
    if greeting:
        text = ("Welcome! I only test what you've studied — no teaching here.\n\n" + text)
    _send_or_edit(chat_id, edit_message_id, text, tg.inline_keyboard(rows))


def _send_lektion_menu(chat_id, user_id, n, edit_message_id=None):
    if not db.is_unlocked(user_id, n):
        text = f"🔒 Lektion {n} is locked.\nPass Lektion {n - 1}'s Final Test (80%+) to unlock it."
        kb = tg.inline_keyboard([[("« Back to lessons", "menu")]])
        _send_or_edit(chat_id, edit_message_id, text, kb)
        return

    title = data_loader.lektion_title(n)
    p = db.get_progress(user_id, n)
    has_grammar = data_loader.lektion_has_grammar(n)

    lines = [f"Lektion {n}: {title}"]
    if p["attempts"]:
        status = "✅ passed" if p["passed"] else "not passed yet"
        lines.append(f"Best Final Test score: {int(round(p['best_score'] * 100))}% ({status})")
    if not has_grammar:
        lines.append("\n(Grammar for this lektion isn't added yet — vocabulary only for now.)")

    rows = [[("📚 Vocabulary", f"vocmenu:{n}")]]
    if has_grammar:
        rows.append([("📖 Grammar Quiz", f"go:{n}:grammar")])
    rows.append([("🏁 Final Test", f"go:{n}:final")])
    rows.append([("« Back to lessons", "menu")])
    _send_or_edit(chat_id, edit_message_id, "\n".join(lines), tg.inline_keyboard(rows))


def _send_vocab_menu(chat_id, n, edit_message_id=None):
    text = f"Lektion {n} — Vocabulary practice:"
    rows = [
        [("🗂 Flashcards", f"go:{n}:flash")],
        [("❓ Multiple Choice", f"go:{n}:mc")],
        [("🔗 Matching", f"go:{n}:match")],
        [("⌨️ Type the Word", f"go:{n}:type")],
        [("🔁 Missed Words", f"go:{n}:missed")],
        [("« Back", f"lek:{n}")],
    ]
    _send_or_edit(chat_id, edit_message_id, text, tg.inline_keyboard(rows))


# --------------------------------------------------------------- sessions

def _compute_total(questions):
    total = 0
    for q in questions:
        if q["kind"] == "vocab_match":
            total += len(q["correct_letter"])
        else:
            total += 1
    return total


def _start_session(chat_id, user_id, n, mode_code):
    mode = MODE_CODES.get(mode_code)
    if mode is None:
        return
    if not db.is_unlocked(user_id, n):
        tg.send_message(chat_id, f"Lektion {n} is locked.")
        return

    if mode == "vocab_mc":
        questions = quiz_engine.build_vocab_mc(n)
    elif mode == "vocab_type":
        questions = quiz_engine.build_vocab_type(n)
    elif mode == "vocab_match":
        questions = [quiz_engine.build_matching_round(n)]
    elif mode == "vocab_flash":
        questions = quiz_engine.build_flashcards(n)
    elif mode == "vocab_missed":
        questions = quiz_engine.build_missed_round(user_id, n)
        if not questions:
            tg.send_message(chat_id, "No missed words saved for this lektion yet — keep practicing and this list will fill in.")
            return
    elif mode == "grammar":
        questions = quiz_engine.build_grammar_quiz(n)
        if not questions:
            tg.send_message(chat_id, "No grammar quiz for this lektion yet.")
            return
    elif mode == "final":
        questions = quiz_engine.build_final_test(n)
        if not questions:
            tg.send_message(chat_id, "Nothing to test yet for this lektion.")
            return
    else:
        questions = []

    if not questions:
        tg.send_message(chat_id, "Not enough content for this yet.")
        return

    session = {
        "mode": mode,
        "lektion": n,
        "questions": questions,
        "index": 0,
        "score": 0,
        "total": _compute_total(questions),
    }
    db.save_session(user_id, session)
    tg.send_message(chat_id, f"{quiz_engine.mode_label(mode)} — Lektion {n}\nLet's go!")
    _send_current_question(chat_id, session)


def _send_current_question(chat_id, session):
    idx = session["index"]
    q = session["questions"][idx]
    header = f"[{idx + 1}/{len(session['questions'])}]"

    if q["kind"] in ("vocab_mc", "grammar_mc"):
        text = f"{header} {q['prompt']}"
        rows = [[(opt, f"mc:{idx}:{i}")] for i, opt in enumerate(q["options"])]
        tg.send_message(chat_id, text, reply_markup=tg.inline_keyboard(rows))

    elif q["kind"] == "vocab_type":
        text = f"{header} Type the German word for:\n\n{q['prompt']}"
        tg.send_message(chat_id, text)

    elif q["kind"] == "vocab_match":
        tg.send_message(chat_id, quiz_engine.render_matching(q))

    elif q["kind"] == "vocab_flash":
        text = f"{header} {q['de']}"
        rows = [[("Show meaning", f"flash:{idx}:show")]]
        tg.send_message(chat_id, text, reply_markup=tg.inline_keyboard(rows))


def _advance(chat_id, user_id, session):
    session["index"] += 1
    if session["index"] >= len(session["questions"]):
        _finish_session(chat_id, user_id, session)
    else:
        db.save_session(user_id, session)
        _send_current_question(chat_id, session)


def _finish_session(chat_id, user_id, session):
    total = session["total"] or 1
    score = session["score"]
    pct = score / total * 100
    mode = session["mode"]
    lektion = session["lektion"]
    lines = [f"Done! Score: {score}/{total} ({pct:.0f}%)"]

    if mode == "final":
        passed_now, _best = db.record_final_attempt(user_id, lektion, score / total)
        if passed_now:
            if lektion < data_loader.total_lektionen():
                lines.append(f"✅ Passed! Lektion {lektion + 1} is now unlocked.")
            else:
                lines.append("✅ Passed! That was the last lektion available.")
        else:
            need = int(config.PASS_THRESHOLD * 100)
            lines.append(f"Need {need}% to pass and unlock the next lektion. Practice the weak spots and try the Final Test again anytime.")

    db.clear_session(user_id)
    kb = tg.inline_keyboard([[("« Lektion menu", f"lek:{lektion}")], [("Lesson list", "menu")]])
    tg.send_message(chat_id, "\n".join(lines), reply_markup=kb)


# --------------------------------------------------------------- grading

def _current_session_for(user_id, expected_index):
    session = db.load_session(user_id)
    if not session:
        return None
    if session["index"] != expected_index:
        return None
    return session


def _handle_mc_answer(chat_id, message_id, user_id, q_index, choice):
    session = _current_session_for(user_id, q_index)
    if session is None:
        return  # stale button from a previous / already-answered question
    q = session["questions"][session["index"]]
    if q["kind"] not in ("vocab_mc", "grammar_mc"):
        return

    correct = (choice == q["correct_index"])
    # Replace the answer buttons with the chosen answer, so old questions
    # in the chat can't be tapped again and show what you picked.
    mark = "✅" if correct else "❌"
    tg.edit_message_text(
        chat_id, message_id,
        f"[{q_index + 1}/{len(session['questions'])}] {q['prompt']}\n\n{mark} {q['options'][choice]}",
    )
    if correct:
        session["score"] += 1
        tg.send_message(chat_id, "✅ Correct!")
        if q["kind"] == "vocab_mc":
            db.remove_missed(user_id, session["lektion"], q["id"])
    else:
        correct_text = q["options"][q["correct_index"]]
        if q["kind"] == "vocab_mc":
            tg.send_message(chat_id, f"❌ Not quite. Correct answer: {correct_text}")
            db.add_missed(user_id, session["lektion"], q["id"])
        else:
            tg.send_message(chat_id, f"❌ Not quite. Correct answer: {correct_text}\n💡 {q['explanation']}")

    _advance(chat_id, user_id, session)


def _handle_type_answer(chat_id, user_id, session, q, text):
    correct = quiz_engine.grade_type_answer(q, text)
    if correct:
        session["score"] += 1
        tg.send_message(chat_id, "✅ Correct!")
        db.remove_missed(user_id, session["lektion"], q["id"])
    else:
        tg.send_message(chat_id, f"❌ Not quite. Correct answer: {q['answer_display']}")
        db.add_missed(user_id, session["lektion"], q["id"])
    _advance(chat_id, user_id, session)


def _handle_match_answer(chat_id, user_id, session, q, text):
    num_correct, total, wrong_ids = quiz_engine.grade_matching_answer(q, text)
    session["score"] += num_correct
    for wid in wrong_ids:
        db.add_missed(user_id, session["lektion"], wid)
    for wid in q["ids"]:
        if wid not in wrong_ids:
            db.remove_missed(user_id, session["lektion"], wid)
    tg.send_message(chat_id, f"You matched {num_correct}/{total} correctly.")
    _advance(chat_id, user_id, session)


def _handle_flash_action(chat_id, message_id, user_id, q_index, sub):
    session = _current_session_for(user_id, q_index)
    if session is None:
        return
    q = session["questions"][session["index"]]
    if q["kind"] != "vocab_flash":
        return

    card = f"[{q_index + 1}/{len(session['questions'])}] {q['de']}\n= {q['uz']}"
    if sub == "show":
        # Flip the card in place instead of sending a new message.
        rows = [[("I knew it ✅", f"flash:{q_index}:know"), ("Missed it ❌", f"flash:{q_index}:miss")]]
        res = tg.edit_message_text(chat_id, message_id, card, reply_markup=tg.inline_keyboard(rows))
        if not res.get("ok"):
            tg.send_message(chat_id, f"= {q['uz']}", reply_markup=tg.inline_keyboard(rows))
        return  # wait for the know/miss tap; don't advance yet

    tg.edit_message_text(chat_id, message_id, f"{card}\n\n{'✅ knew it' if sub == 'know' else '❌ missed'}")

    if sub == "know":
        session["score"] += 1
        db.remove_missed(user_id, session["lektion"], q["id"])
    elif sub == "miss":
        db.add_missed(user_id, session["lektion"], q["id"])
    _advance(chat_id, user_id, session)
