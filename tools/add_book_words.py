# -*- coding: utf-8 -*-
"""
One-off (but safe to re-run) import of the words listed in
tools/book_additions.tsv into data/vocabulary_data.json, plus a few OCR
typo fixes found while checking the data against the Momente A1.1
"Lernwortschatz" pages.

    python tools/add_book_words.py
    python tools/build_miniapp.py     # then refresh the mini app data

Entries already present in a lektion (compared case-insensitively, with
or without the article) are skipped, so running it twice changes nothing.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOCAB = os.path.join(ROOT, "data", "vocabulary_data.json")
ADDITIONS = os.path.join(ROOT, "tools", "book_additions.tsv")
SOURCE_TAG = "Momente A1.1 Lernwortschatz"

# (lektion, wrong "de" in the data) -> correct spelling, as printed in the book
TYPO_FIXES = {
    (2, "gechieden sein"): "geschieden sein",
    (3, "Welche Sprache sprichst du?"): "Welche Sprachen sprichst du?",
    (6, "Ach, das ist er ja!"): "Ach, da ist er ja!",
    (8, "okey"): "okay",
    (9, "inteligent"): "intelligent",
    (12, "Die Betreffziele"): "Die Betreffzeile",
}


def key(de):
    t = de.lower().strip().rstrip(".!?")
    return re.sub(r"^(der|die|das)\s+", "", t)


def main():
    with open(VOCAB, encoding="utf-8") as f:
        vocab = json.load(f)
    lessons = {l["lektion"]: l for l in vocab["lessons"]}

    fixed = 0
    for (n, wrong), right in TYPO_FIXES.items():
        for item in lessons[n]["items"]:
            if item["de"] == wrong:
                item["de"] = right
                fixed += 1

    added = skipped = 0
    with open(ADDITIONS, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            n, de, uz, gender, pos = line.rstrip("\n").split("\t")
            lesson = lessons[int(n)]
            if any(key(i["de"]) == key(de) for i in lesson["items"]):
                skipped += 1
                continue
            last = max(int(i["id"].split("-")[1]) for i in lesson["items"])
            lesson["items"].append({
                "id": f"L{n}-{last + 1:03d}",
                "de": de,
                "uz": uz,
                "gender": None if gender == "-" else gender,
                "pos": pos,
                "source": SOURCE_TAG,
            })
            added += 1

    for lesson in vocab["lessons"]:
        lesson["count"] = len(lesson["items"])
    vocab["meta"]["total_entries"] = sum(l["count"] for l in vocab["lessons"])
    vocab["meta"]["book_check"] = (
        "Lektion 1-12 checked against Momente A1.1 Kursbuch Lernwortschatz; "
        f"entries tagged source='{SOURCE_TAG}' were added from it."
    )

    with open(VOCAB, "w", encoding="utf-8", newline="\n") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"typo fixes: {fixed}, added: {added}, already present: {skipped}, "
          f"total entries now: {vocab['meta']['total_entries']}")


if __name__ == "__main__":
    main()
