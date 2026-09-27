# -*- coding: utf-8 -*-
"""
Builds question sets for every mode and grades answers.

A "session" dict (persisted via db.save_session) looks like:

{
  "mode": "vocab_mc" | "vocab_type" | "vocab_match" | "vocab_flash" | "vocab_missed"
          | "grammar" | "final",
  "lektion": 7,
  "questions": [ ... mode-specific question objects ... ],
  "index": 0,
  "score": 0,
  "total": 10,
  "missed_ids": []          # vocab ids missed this round (for updating the missed-words pool)
}

Every "question object" carries a "kind" field so the handler knows how to
render it and how to interpret the next incoming update (button press or
free-text message).
"""
import random
import string

from . import data_loader, config

UMLAUT_MAP = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})
ARTICLES = ("der ", "die ", "das ")


def normalize_de(text):
    t = text.strip().lower()
    t = t.translate(UMLAUT_MAP)
    for art in ARTICLES:
        if t.startswith(art):
            t = t[len(art):]
            break
    # collapse repeated whitespace
    t = " ".join(t.split())
    return t


# ---------------------------------------------------------------- vocab MC

def _make_mc_item(item, all_items):
    # Some lektionen list true synonyms (two German words with the exact
    # same translation, e.g. "der Job" / "der Beruf" both = "kasb"). Dedupe
    # candidates by translation as we build the pool so the 4 final options
    # can never collide with each other, not just with the correct answer.
    seen_uz = {item["uz"]}
    unique_candidates = []
    for i in all_items:
        if i["id"] == item["id"]:
            continue
        uz = i.get("uz")
        if not uz or uz in seen_uz:
            continue
        seen_uz.add(uz)
        unique_candidates.append(i)
    distractors = random.sample(unique_candidates, min(3, len(unique_candidates)))
    options = [item["uz"]] + [d["uz"] for d in distractors]
    random.shuffle(options)
    return {
        "kind": "vocab_mc",
        "id": item["id"],
        "prompt": item["de"],
        "options": options,
        "correct_index": options.index(item["uz"]),
    }


def build_vocab_mc(lektion, n=None, id_pool=None):
    n = n or config.PRACTICE_BATCH_SIZE
    all_items = data_loader.get_vocab(lektion)
    usable = [i for i in all_items if i.get("uz")]
    if id_pool is not None:
        usable = [i for i in usable if i["id"] in id_pool]
    chosen = random.sample(usable, min(n, len(usable)))
    return [_make_mc_item(item, all_items) for item in chosen]


# ---------------------------------------------------------------- vocab type-the-word

def build_vocab_type(lektion, n=None):
    n = n or config.PRACTICE_BATCH_SIZE
    all_items = data_loader.get_vocab(lektion)
    pool = [i for i in all_items if i.get("pos") != "phrase" and i.get("uz")]
    if len(pool) < 5:
        pool = [i for i in all_items if i.get("uz")]
    chosen = random.sample(pool, min(n, len(pool)))
    questions = []
    for item in chosen:
        questions.append({
            "kind": "vocab_type",
            "id": item["id"],
            "prompt": item["uz"],
            "accepted": [normalize_de(item["de"])],
            "answer_display": item["de"],
        })
    return questions


def grade_type_answer(question, user_text):
    return normalize_de(user_text) in question["accepted"]


# ---------------------------------------------------------------- vocab matching

def build_matching_round(lektion, size=None):
    size = size or config.MATCH_ROUND_SIZE
    all_items = data_loader.get_vocab(lektion)
    # dedupe by translation so the round never shows two identical meanings
    # (which would make the puzzle unfairly ambiguous)
    seen_uz, pool = set(), []
    for i in all_items:
        uz = i.get("uz")
        if uz and uz not in seen_uz:
            seen_uz.add(uz)
            pool.append(i)
    n = min(size, len(pool))
    chosen = random.sample(pool, n)

    letters = list(string.ascii_lowercase[:n])
    shuffled_positions = list(range(n))
    random.shuffle(shuffled_positions)

    # uz_display[pos] shows chosen[shuffled_positions[pos]], labelled letters[pos]
    uz_display = [(letters[pos], chosen[shuffled_positions[pos]]["uz"]) for pos in range(n)]
    # correct letter for original item i (1-indexed) is the letter at the position where shuffled_positions[pos] == i
    correct_letter = {}
    for pos, original_idx in enumerate(shuffled_positions):
        correct_letter[original_idx + 1] = letters[pos]

    de_display = [(i + 1, chosen[i]["de"]) for i in range(n)]
    return {
        "kind": "vocab_match",
        "ids": [c["id"] for c in chosen],
        "de_display": de_display,
        "uz_display": uz_display,
        "correct_letter": {str(k): v for k, v in correct_letter.items()},  # json-safe keys
    }


def render_matching(question):
    lines = ["Match the numbers with the letters. Reply like: 1b 2a 3e 4c 5d\n"]
    lines.append("German:")
    for num, de in question["de_display"]:
        lines.append(f"{num}. {de}")
    lines.append("\nMeaning:")
    for letter, uz in question["uz_display"]:
        lines.append(f"{letter}) {uz}")
    return "\n".join(lines)


def grade_matching_answer(question, user_text):
    """Returns (num_correct, total, wrong_ids) — wrong_ids are vocab ids to mark as missed."""
    correct_letter = question["correct_letter"]  # str(number) -> letter
    n = len(correct_letter)
    given = {}
    for tok in user_text.replace(",", " ").split():
        tok = tok.strip().lower()
        digits = "".join(c for c in tok if c.isdigit())
        letters = "".join(c for c in tok if c.isalpha())
        if digits and letters:
            given[digits] = letters[0]
    num_correct = 0
    wrong_ids = []
    for i in range(1, n + 1):
        key = str(i)
        ok = given.get(key) == correct_letter.get(key)
        if ok:
            num_correct += 1
        else:
            wrong_ids.append(question["ids"][i - 1])
    return num_correct, n, wrong_ids


# ---------------------------------------------------------------- flashcards

def build_flashcards(lektion, n=None):
    n = n or config.FLASHCARD_BATCH_SIZE
    all_items = data_loader.get_vocab(lektion)
    pool = [i for i in all_items if i.get("uz")]
    chosen = random.sample(pool, min(n, len(pool)))
    return [{"kind": "vocab_flash", "id": i["id"], "de": i["de"], "uz": i["uz"]} for i in chosen]


# ---------------------------------------------------------------- missed words

def build_missed_round(user_id, lektion):
    from . import db  # local import to avoid a circular import at module load time
    ids = db.get_missed_ids(user_id, lektion)
    if not ids:
        return []
    random.shuffle(ids)
    ids = ids[:config.MISSED_ROUND_SIZE]
    items = [data_loader.get_vocab_item(i) for i in ids]
    items = [i for i in items if i]
    all_items = data_loader.get_vocab(lektion)
    return [_make_mc_item(item, all_items) for item in items]


# ---------------------------------------------------------------- grammar

def build_grammar_quiz(lektion, n=None):
    qs = data_loader.get_grammar_questions(lektion)
    if not qs:
        return []
    n = n or len(qs)
    chosen = random.sample(qs, min(n, len(qs)))
    out = []
    for q in chosen:
        out.append({
            "kind": "grammar_mc",
            "prompt": q["q"],
            "options": q["options"],
            "correct_index": q["correct"],
            "explanation": q["explanation"],
        })
    return out


# ---------------------------------------------------------------- final test

def build_final_test(lektion):
    has_grammar = data_loader.lektion_has_grammar(lektion)
    if has_grammar:
        vocab_qs = build_vocab_mc(lektion, n=config.FINAL_VOCAB_COUNT)
        grammar_qs = build_grammar_quiz(lektion, n=config.FINAL_GRAMMAR_COUNT)
    else:
        # No grammar written for this lektion yet: fill the final test with
        # vocab only, so it's still a meaningful 15-question test.
        vocab_qs = build_vocab_mc(lektion, n=config.FINAL_VOCAB_COUNT + config.FINAL_GRAMMAR_COUNT)
        grammar_qs = []
    all_qs = vocab_qs + grammar_qs
    random.shuffle(all_qs)
    return all_qs


def mode_label(mode):
    return {
        "vocab_mc": "Vocabulary — Multiple Choice",
        "vocab_type": "Vocabulary — Type the Word",
        "vocab_match": "Vocabulary — Matching",
        "vocab_flash": "Vocabulary — Flashcards",
        "vocab_missed": "Vocabulary — Missed Words Review",
        "grammar": "Grammar Quiz",
        "final": "Final Test",
    }.get(mode, mode)
