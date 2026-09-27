# -*- coding: utf-8 -*-
import json
import os

from . import config


def _load(name):
    path = os.path.join(config.DATA_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_VOCAB = _load("vocabulary_data.json")
try:
    _GRAMMAR_Q = _load("grammar_questions.json")
except FileNotFoundError:
    _GRAMMAR_Q = {"lessons": []}

_VOCAB_BY_LEKTION = {l["lektion"]: l["items"] for l in _VOCAB["lessons"]}
_GRAMMAR_BY_LEKTION = {l["lektion"]: l["questions"] for l in _GRAMMAR_Q["lessons"]}
_VOCAB_BY_ID = {item["id"]: item for l in _VOCAB["lessons"] for item in l["items"]}

LEKTION_TITLES = {
    1: "Ich heiße Miriam.", 2: "Was macht ihr beruflich?", 3: "Das ist meine Schwester.",
    4: "Das Bild ist so schön.", 5: "Ist das ein Tisch?", 6: "Wir haben einen Termin.",
    7: "Sie können super tanzen!", 8: "Ich habe leider keine Zeit.", 9: "Ich mag Hamburger.",
    10: "Wann kommst du denn an?", 11: "Was haben Sie gestern gemacht?",
    12: "Im Frühling bin ich nach Hamburg gefahren.",
}


def get_vocab(lektion):
    """All vocabulary items for a lektion (list of dicts with id/de/uz/gender/pos)."""
    return _VOCAB_BY_LEKTION.get(lektion, [])


def get_vocab_item(word_id):
    return _VOCAB_BY_ID.get(word_id)


def get_grammar_questions(lektion):
    return _GRAMMAR_BY_LEKTION.get(lektion, [])


def lektion_has_grammar(lektion):
    return len(get_grammar_questions(lektion)) > 0


def lektion_title(lektion):
    return LEKTION_TITLES.get(lektion, f"Lektion {lektion}")


def total_lektionen():
    return config.TOTAL_LEKTIONEN
