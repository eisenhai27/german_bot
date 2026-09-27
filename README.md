# German A1 Study Bot

A Telegram bot that **only tests** what you've studied — vocabulary and
grammar, no explanations up front. Built around your *Momente A1*
vocabulary (24 lektionen) and grammar (Lektion 1–12 so far).

## What it does

- **Vocabulary practice**, per lektion: Flashcards, Multiple Choice,
  Matching, Type-the-Word, and a "Missed Words" review that recycles
  whatever you've gotten wrong.
- **Grammar Quiz**, per lektion (Lektion 1–12 for now).
- **Final Test** per lektion: a mix of vocab + grammar. Score **80%+** to
  unlock the next lektion. You can retry it as many times as you want.
- Wrong vocabulary answers show the correct answer only. Wrong grammar
  answers show the correct answer **plus** a short explanation.
- Progress is saved (SQLite file `bot_data.db`), so it remembers you
  between sessions.

## Project layout

```
german_bot/
  data/                     vocabulary + grammar content
  bot/                      all the bot logic (no Telegram framework, just requests)
  webhook_app.py            entry point for webhook hosting (e.g. PythonAnywhere)
  polling_app.py            entry point for polling hosting (e.g. a VPS, Termux)
  set_webhook.py            run once after deploying webhook_app.py
  test_offline.py           simulates a full conversation with no network — run this
                            any time you change the code, to catch bugs before deploying
  run_bot.ps1               Windows: start the bot on this PC (asks for the token)
  miniapp/                  the Telegram Mini App (see below)
    index.html                UI
    quiz.js                   pure quiz logic, unit-tested in tests/test_miniapp.js
    data.js                   GENERATED from data/ by tools/build_miniapp.py
  tools/build_miniapp.py    regenerates miniapp/data.js + cache-busting script hashes;
                            run it after editing data/ or miniapp/quiz.js
  tests/                    mini app tests (node tests/test_miniapp.js)
  requirements.txt
```

## Before you deploy: test it locally

Wherever you end up running this, first sanity-check the logic itself:

```
pip install -r requirements.txt
python test_offline.py
```

This plays through menus, every quiz mode, the missed-words loop, and the
80% pass/fail gate — all without touching Telegram — and should print
`ALL OFFLINE TESTS PASSED`. If you ever edit `bot/quiz_engine.py` or
`bot/handlers.py`, run this again before deploying.

## Setting your bot token

Never paste the token into the code. Set it as an environment variable
named `BOT_TOKEN`. How you do that depends on where you host it (see
below). Anyone with this token can control your bot, so treat it like a
password — if it ever leaks, message @BotFather with `/revoke` to get a
new one.

---

## Option A — PythonAnywhere (recommended: free, always on, no computer needed)

This uses **webhook mode**: Telegram calls your bot's URL directly, so
nothing needs to run in a loop. PythonAnywhere's free tier gives you a
permanent HTTPS URL, which is exactly what that needs. You can do this
entire setup from your phone's browser.

1. **Create a free account** at pythonanywhere.com.
2. **Upload the project**: zip the `german_bot` folder, then in
   PythonAnywhere go to the **Files** tab, upload the zip, and unzip it
   from a **Bash console** (Consoles tab → Bash):
   ```
   unzip german_bot.zip
   cd german_bot
   ```
3. **Install dependencies** (same Bash console):
   ```
   pip3.10 install --user -r requirements.txt
   ```
   (If `pip3.10` doesn't exist, run `python3 --version` to see what's
   installed and use the matching `pip3.x`.)
4. **Set your bot token.** The simplest reliable way on PythonAnywhere is
   to set it inside the WSGI file you'll edit in the next step — see
   below.
5. **Create the web app**: go to the **Web** tab → "Add a new web app" →
   choose **Manual configuration** (not a Flask template) → pick the
   Python version matching step 3.
6. **Edit the WSGI file** (the Web tab gives you a link to it,
   something like `/var/www/yourusername_pythonanywhere_com_wsgi.py`).
   Replace its contents with:
   ```python
   import sys, os

   path = '/home/yourusername/german_bot'
   if path not in sys.path:
       sys.path.insert(0, path)

   os.environ['BOT_TOKEN'] = 'paste-your-real-token-here'
   os.environ['WEBHOOK_SECRET'] = 'any-random-string-you-make-up'

   from webhook_app import app as application
   ```
   (Use your actual PythonAnywhere username in the path. `WEBHOOK_SECRET`
   is optional but recommended: the web app then rejects any request that
   doesn't come from Telegram. Use the same value in step 8.)
7. **Reload the web app** (green "Reload" button on the Web tab).
8. **Register the webhook** — in a Bash console:
   ```
   cd german_bot
   BOT_TOKEN=paste-your-real-token-here WEBHOOK_SECRET=any-random-string-you-make-up python3 set_webhook.py https://yourusername.pythonanywhere.com
   ```
9. Open Telegram, message your bot `/start`. You should see the lesson
   menu.

If nothing happens, check the **Web tab → error log** on PythonAnywhere —
it'll show you exactly what broke.

*Free-tier note:* PythonAnywhere occasionally asks free accounts to
"click to keep this web app running" every few months if inactive — just
a login and a click, not a rebuild.

---

## Option B — Run it on your own phone with Termux (Android only)

This uses **polling mode**: the bot itself asks Telegram for new messages
in a loop, so it needs to keep running. No hosting account needed at all
— but your phone has to stay on with Termux running (Android may kill
background apps aggressively; disable battery optimization for Termux if
it keeps stopping).

1. Install **Termux** from F-Droid (the Play Store version is outdated).
2. In Termux:
   ```
   pkg update && pkg install python
   pip install -r requirements.txt
   ```
3. Transfer the `german_bot` folder to your phone (e.g. via a cloud
   drive) and `cd` into it in Termux.
4. Run it:
   ```
   BOT_TOKEN=paste-your-real-token-here python polling_app.py
   ```
5. Leave Termux running. Message your bot on Telegram.

## Option C — A real always-on server (Oracle Cloud Free Tier, a VPS, etc.)

Same as Option B (`polling_app.py`), just running on a machine that's
always on instead of your phone. If you go this route later, set
`BOT_TOKEN` as a proper environment variable and consider running it
under `systemd` or `screen`/`tmux` so it survives you disconnecting.

---

## Adding Lektion 13–24 grammar later

Once you send the rest of the course book, the new grammar goes into
`data/grammar_data.json` (reference) and `data/grammar_questions.json`
(the actual quiz bank, same format as Lektion 1–12 already in there).
The bot automatically shows the Grammar Quiz option and includes it in
the Final Test for any lektion that has questions in
`grammar_questions.json` — no code changes needed. Afterwards run
`python tools/build_miniapp.py` so the mini app picks up the new content too.

## The mini app (miniapp/)

A visual version of the same study tool, designed as a German passport:
you collect a stamp for each of the 24 lektionen.

- **Practice modes:** flashcards, multiple choice, matching (tap either
  side first), type-it, a **der · die · das** article drill for every
  noun, a Review pile, and the grammar quiz.
- **Final test:** 15 questions, 80% unlocks the next lektion. The result
  screen lists every mistake so you know what to practise.
- **Review pile:** a missed word stays in it until you get it right
  twice in a row.
- **Type-it:** ignores der/die/das and umlaut spelling (a/ä), forgives
  a one-letter typo on longer words, and has ä ö ü ß buttons.
- **Pronunciation:** 🔊 buttons read German words aloud, using the
  phone's own text-to-speech.
- **Daily streak** and a stats card on the home screen.
- **Inside Telegram:** it uses Telegram's theme, back button and
  vibration feedback, and progress **syncs across your devices** through
  Telegram CloudStorage. In a normal browser it saves progress on that
  device.
- Keyboard shortcuts on a computer: 1–4 to answer, Enter/Space to
  continue or flip a card, Esc to go back.

It keeps its own progress, separate from the chat bot's database.

**Preview it right now:** double-click `miniapp/index.html`. It opens
straight in your browser with no server and no account.

**Putting it inside the Telegram bot** needs one more thing: Telegram
can only open a Mini App at a public **https://** address — it can't
reach a file sitting on your computer. This repo is published with
GitHub Pages (Settings → Pages → branch `main`, folder `/ (root)`), so
the mini app lives at:

**https://eisenhai27.github.io/german_bot/miniapp/**

Every push to `main` updates it automatically. To show it in the bot:

1. Set the `MINI_APP_URL` environment variable (same place you set
   `BOT_TOKEN`):
   ```python
   os.environ['MINI_APP_URL'] = 'https://eisenhai27.github.io/german_bot/miniapp/'
   ```
2. Restart the bot. The "🛂 Open Study App" button now appears on
   `/start` and opens the real thing inside Telegram.

No Claude account, no sign-in — it's a plain static page on your own
GitHub Pages, which is exactly what Telegram Mini Apps expect.

## Notes on the data

The vocabulary was OCR'd from a scanned book, so a few entries carry
typos or regional-variant notes from the original — nothing that breaks
the bot, just something to be aware of if an answer looks odd.
