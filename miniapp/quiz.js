/*
 * Deutsch Pass: pure quiz logic.
 *
 * No DOM or storage access in here, so every function can be unit-tested
 * with plain Node (see tests/test_miniapp.js). Functions take the lesson's
 * data as arguments instead of reading globals.
 */
(function (root) {
  'use strict';

  const CONFIG = {
    PASS_THRESHOLD: 0.8,
    FINAL_VOCAB_COUNT: 10,
    FINAL_GRAMMAR_COUNT: 5,
    PRACTICE_BATCH_SIZE: 10,
    MATCH_ROUND_SIZE: 5,
    FLASHCARD_BATCH_SIZE: 10,
    REVIEW_ROUND_SIZE: 10,
    // A missed word has to be answered correctly this many times in a row
    // before it leaves the review pile.
    REVIEW_CLEAR_STREAK: 2,
    TOTAL_LEKTIONEN: 24,
  };

  const ARTICLE_BY_GENDER = { m: 'der', f: 'die', n: 'das' };
  const ARTICLES = ['der', 'die', 'das'];

  // ------------------------------------------------------------ helpers

  function shuffle(arr, rand) {
    rand = rand || Math.random;
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function sample(arr, n, rand) {
    return shuffle(arr, rand).slice(0, Math.min(n, arr.length));
  }

  /** True for entries like "Das ist …" or "Hallo, …hier" that can't be typed/drilled cleanly. */
  function hasGap(text) {
    return /…|\.\./.test(text || '');
  }

  /** Remove "(...)" notes: "bist (sein)" -> "bist". */
  function stripParens(text) {
    return (text || '').replace(/\s*\([^)]*\)\s*/g, ' ').trim();
  }

  // ------------------------------------------------------------ answer normalisation

  function normalizeDe(text) {
    let t = (text || '').toLowerCase().trim();
    t = t.replace(/ä/g, 'a').replace(/ö/g, 'o').replace(/ü/g, 'u').replace(/ß/g, 'ss');
    t = t.replace(/…|\.\.+/g, ' ');
    t = t.replace(/[!?.,;:()"„“]/g, ' ');
    t = t.replace(/^\s*-\s*/, '').replace(/-\s*$/, '');
    t = t.split(/\s+/).filter(Boolean).join(' ');
    for (const art of ['der ', 'die ', 'das ', 'ein ', 'eine ']) {
      if (t.startsWith(art)) { t = t.slice(art.length); break; }
    }
    return t;
  }

  /** Every spelling we accept for a vocabulary entry. */
  function acceptedAnswers(de) {
    const out = new Set();
    const alternatives = String(de || '').split(/\s+\/\s+|\s*;\s*/);
    for (const alt of alternatives) {
      out.add(normalizeDe(stripParens(alt)));             // "öko(logisch)" -> "oko"
      out.add(normalizeDe(alt.replace(/[()]/g, '')));     // "öko(logisch)" -> "okologisch"
    }
    out.delete('');
    return Array.from(out);
  }

  function levenshtein(a, b) {
    if (a === b) return 0;
    if (!a.length) return b.length;
    if (!b.length) return a.length;
    let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      const cur = [i];
      for (let j = 1; j <= b.length; j++) {
        cur[j] = Math.min(
          prev[j] + 1,
          cur[j - 1] + 1,
          prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
        );
      }
      prev = cur;
    }
    return prev[b.length];
  }

  /**
   * Grade a typed answer.
   * Returns {correct, exact}: `correct && !exact` means a small typo we let
   * slide (1 letter for words of 5+ letters, 2 for 10+), shown as "almost".
   */
  function gradeTypeAnswer(question, userText) {
    const given = normalizeDe(userText);
    if (!given) return { correct: false, exact: false };
    const accepted = question.accepted;
    if (accepted.includes(given)) return { correct: true, exact: true };
    for (const ans of accepted) {
      const allowed = ans.length >= 10 ? 2 : ans.length >= 5 ? 1 : 0;
      if (allowed && levenshtein(given, ans) <= allowed) return { correct: true, exact: false };
    }
    return { correct: false, exact: false };
  }

  // ------------------------------------------------------------ question builders

  function makeMcItem(item, allItems, rand) {
    // Prefer distractors of the same part of speech so the right answer
    // can't be guessed from its shape (a noun among three verbs, etc.).
    const seen = new Set([item.uz]);
    const same = [];
    const other = [];
    for (const i of allItems) {
      if (i.id === item.id || !i.uz || seen.has(i.uz)) continue;
      seen.add(i.uz);
      (i.pos === item.pos ? same : other).push(i);
    }
    let distractors = sample(same, 3, rand);
    if (distractors.length < 3) distractors = distractors.concat(sample(other, 3 - distractors.length, rand));
    const options = shuffle([item.uz].concat(distractors.map(d => d.uz)), rand);
    return {
      kind: 'vocab_mc',
      id: item.id,
      prompt: item.de,
      speak: item.de,
      options,
      correctIndex: options.indexOf(item.uz),
    };
  }

  function buildVocabMc(vocab, n, idPool, rand) {
    let usable = vocab.filter(i => i.uz);
    if (idPool) usable = usable.filter(i => idPool.has(i.id));
    return sample(usable, n || CONFIG.PRACTICE_BATCH_SIZE, rand).map(item => makeMcItem(item, vocab, rand));
  }

  function buildVocabType(vocab, n, rand) {
    let pool = vocab.filter(i => i.uz && i.pos !== 'phrase' && !hasGap(i.de));
    if (pool.length < 5) pool = vocab.filter(i => i.uz && !hasGap(i.de));
    return sample(pool, n || CONFIG.PRACTICE_BATCH_SIZE, rand).map(item => ({
      kind: 'vocab_type',
      id: item.id,
      prompt: item.uz,
      accepted: acceptedAnswers(item.de),
      answerDisplay: item.de,
      speak: item.de,
    }));
  }

  /** "Der Pensionierte (Shveysariya shevasi)" -> "Pensionierte" */
  function nounStem(de) {
    return stripParens(de).replace(/^(der|die|das)\s+/i, '').trim();
  }

  function articleNouns(vocab) {
    return vocab.filter(i => i.pos === 'noun' && ARTICLE_BY_GENDER[i.gender] && !hasGap(i.de) && nounStem(i.de));
  }

  function buildArticleDrill(vocab, n, rand) {
    return sample(articleNouns(vocab), n || CONFIG.PRACTICE_BATCH_SIZE, rand).map(item => {
      const stem = nounStem(item.de);
      const art = ARTICLE_BY_GENDER[item.gender];
      return {
        kind: 'article',
        id: item.id,
        prompt: stem,
        hint: item.uz,
        options: ARTICLES.slice(),
        correctIndex: ARTICLES.indexOf(art),
        speak: art + ' ' + stem,
      };
    });
  }

  function buildMatchingRound(vocab, size, rand) {
    const seen = new Set();
    const pool = [];
    for (const i of vocab) {
      if (i.uz && !seen.has(i.uz)) { seen.add(i.uz); pool.push(i); }
    }
    const chosen = sample(pool, size || CONFIG.MATCH_ROUND_SIZE, rand);
    const rightOrder = shuffle(chosen.map((_, idx) => idx), rand);
    return {
      kind: 'vocab_match',
      left: chosen.map((c, i) => ({ id: c.id, text: c.de, key: i })),
      right: rightOrder.map(idx => ({ text: chosen[idx].uz, matchKey: idx })),
    };
  }

  function buildFlashcards(vocab, n, rand) {
    return sample(vocab.filter(i => i.uz), n || CONFIG.FLASHCARD_BATCH_SIZE, rand)
      .map(i => ({ kind: 'vocab_flash', id: i.id, de: i.de, uz: i.uz, speak: i.de }));
  }

  function buildReviewRound(reviewIds, vocab, rand) {
    if (!reviewIds || !reviewIds.length) return [];
    const byId = Object.fromEntries(vocab.map(i => [i.id, i]));
    return sample(reviewIds, CONFIG.REVIEW_ROUND_SIZE, rand)
      .map(id => byId[id])
      .filter(Boolean)
      .map(item => makeMcItem(item, vocab, rand));
  }

  function buildGrammarQuiz(grammarQs, n, rand) {
    if (!grammarQs || !grammarQs.length) return [];
    return sample(grammarQs, n || grammarQs.length, rand).map(q => ({
      kind: 'grammar_mc',
      prompt: q.q,
      options: q.options,
      correctIndex: q.correct,
      explanation: q.explanation,
    }));
  }

  function buildFinalTest(vocab, grammarQs, rand) {
    const hasGrammar = grammarQs && grammarQs.length > 0;
    const vocabQs = buildVocabMc(vocab, CONFIG.FINAL_VOCAB_COUNT + (hasGrammar ? 0 : CONFIG.FINAL_GRAMMAR_COUNT), null, rand);
    const grammar = hasGrammar ? buildGrammarQuiz(grammarQs, CONFIG.FINAL_GRAMMAR_COUNT, rand) : [];
    return shuffle(vocabQs.concat(grammar), rand);
  }

  // ------------------------------------------------------------ progress model

  /**
   * Review pile for one lektion: {wordId: correctAnswersStillNeeded}.
   * Returns a new object; the input is not mutated.
   */
  function updateReview(pile, wordId, correct) {
    const next = Object.assign({}, pile);
    if (correct) {
      if (wordId in next) {
        next[wordId] -= 1;
        if (next[wordId] <= 0) delete next[wordId];
      }
    } else {
      next[wordId] = CONFIG.REVIEW_CLEAR_STREAK;
    }
    return next;
  }

  function recordFinal(prev, pct) {
    const p = prev || { best: 0, passed: false, attempts: 0 };
    const passedNow = pct >= CONFIG.PASS_THRESHOLD;
    return {
      passedNow,
      progress: {
        best: Math.max(p.best || 0, pct),
        passed: !!p.passed || passedNow,
        attempts: (p.attempts || 0) + 1,
      },
    };
  }

  function isUnlocked(progressMap, lektion) {
    if (lektion <= 1) return true;
    const prev = progressMap[lektion - 1];
    return !!(prev && prev.passed);
  }

  /** The lektion to suggest next: first unlocked one not yet passed. */
  function currentLektion(progressMap, total) {
    for (let n = 1; n <= total; n++) {
      if (!(progressMap[n] && progressMap[n].passed)) return n;
    }
    return total;
  }

  // ------------------------------------------------------------ daily streak

  function dayIndex(isoDate) {
    const [y, m, d] = isoDate.split('-').map(Number);
    return Math.round(Date.UTC(y, m - 1, d) / 86400000);
  }

  /** streak: {last: 'YYYY-MM-DD' | null, count}. Call when the user finishes a round. */
  function bumpStreak(streak, today) {
    const s = streak || { last: null, count: 0 };
    if (s.last === today) return s;
    const gap = s.last ? dayIndex(today) - dayIndex(s.last) : Infinity;
    return { last: today, count: gap === 1 ? s.count + 1 : 1 };
  }

  /** Streak to display today: it stays alive until a full day is skipped. */
  function liveStreak(streak, today) {
    if (!streak || !streak.last) return 0;
    return dayIndex(today) - dayIndex(streak.last) <= 1 ? streak.count : 0;
  }

  const api = {
    CONFIG, ARTICLE_BY_GENDER,
    shuffle, sample, hasGap, stripParens,
    normalizeDe, acceptedAnswers, levenshtein, gradeTypeAnswer,
    buildVocabMc, buildVocabType, buildArticleDrill, articleNouns, nounStem,
    buildMatchingRound, buildFlashcards, buildReviewRound, buildGrammarQuiz, buildFinalTest,
    updateReview, recordFinal, isUnlocked, currentLektion,
    bumpStreak, liveStreak,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Quiz = api;
})(typeof window !== 'undefined' ? window : this);
