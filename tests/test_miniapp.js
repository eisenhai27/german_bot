// Unit tests for miniapp/quiz.js. Run: node tests/test_miniapp.js
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const Q = require('../miniapp/quiz.js');

// Load the generated data.js the same way the browser does.
const sandbox = { window: {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'miniapp', 'data.js'), 'utf8'), sandbox);
const { VOCAB_DATA, GRAMMAR_DATA, LEKTION_TITLES } = sandbox.window;

let passed = 0;
function test(name, fn) { fn(); passed++; console.log('ok -', name); }

test('data.js has all 24 lektionen and titles for the grammar ones', () => {
  assert.strictEqual(Object.keys(VOCAB_DATA).length, 24);
  assert.ok(Object.keys(GRAMMAR_DATA).length >= 12);
  assert.strictEqual(LEKTION_TITLES['1'], 'Ich heiße Miriam.');
});

test('normalizeDe folds umlauts, articles, punctuation', () => {
  assert.strictEqual(Q.normalizeDe('  Der  Bäcker '), 'backer');
  assert.strictEqual(Q.normalizeDe('Wie heißt du?'), 'wie heisst du');
  assert.strictEqual(Q.normalizeDe('- aus'), 'aus');
});

test('acceptedAnswers handles parentheses', () => {
  assert.deepStrictEqual(Q.acceptedAnswers('öko(logisch)').sort(), ['oko', 'okologisch']);
  assert.ok(Q.acceptedAnswers('bist (sein)').includes('bist'));
});

test('gradeTypeAnswer: exact, typo-tolerant, wrong', () => {
  const q = { accepted: Q.acceptedAnswers('Der Schreibtisch') };
  assert.deepStrictEqual(Q.gradeTypeAnswer(q, 'schreibtisch'), { correct: true, exact: true });
  assert.deepStrictEqual(Q.gradeTypeAnswer(q, 'Schreibtish'), { correct: true, exact: false });
  assert.strictEqual(Q.gradeTypeAnswer(q, 'Tisch').correct, false);
  assert.strictEqual(Q.gradeTypeAnswer(q, '').correct, false);
  const short = { accepted: Q.acceptedAnswers('Bus') };
  assert.strictEqual(Q.gradeTypeAnswer(short, 'Bis').correct, false, 'no typo tolerance for short words');
});

test('every typeable word accepts its own displayed spelling', () => {
  for (const n in VOCAB_DATA) {
    for (const item of VOCAB_DATA[n]) {
      if (!item.uz || Q.hasGap(item.de)) continue;
      const q = { accepted: Q.acceptedAnswers(item.de) };
      assert.ok(Q.gradeTypeAnswer(q, item.de).exact, 'own answer must grade exact: ' + item.de);
    }
  }
});

test('every lektion builds every mode with valid questions', () => {
  for (let n = 1; n <= 24; n++) {
    const vocab = VOCAB_DATA[n], gq = GRAMMAR_DATA[n] || [];
    for (const q of Q.buildVocabMc(vocab)) {
      assert.strictEqual(q.options.length, 4);
      assert.strictEqual(new Set(q.options).size, 4, 'options must be distinct');
      assert.ok(q.correctIndex >= 0);
    }
    for (const q of Q.buildVocabType(vocab)) {
      assert.ok(q.accepted.length > 0, 'type question needs an accepted answer: ' + q.answerDisplay);
      assert.ok(Q.gradeTypeAnswer(q, q.answerDisplay).exact, 'own answer must grade exact: ' + q.answerDisplay);
    }
    for (const q of Q.buildArticleDrill(vocab)) {
      assert.ok(['der', 'die', 'das'][q.correctIndex]);
      assert.ok(!/^(der|die|das)\s/i.test(q.prompt), 'article must be stripped: ' + q.prompt);
    }
    const m = Q.buildMatchingRound(vocab);
    assert.strictEqual(m.left.length, m.right.length);
    const final = Q.buildFinalTest(vocab, gq);
    assert.strictEqual(final.length, 15);
  }
});

test('review pile needs two correct answers to clear', () => {
  let pile = Q.updateReview({}, 'w1', false);
  assert.strictEqual(pile.w1, 2);
  pile = Q.updateReview(pile, 'w1', true);
  assert.strictEqual(pile.w1, 1);
  pile = Q.updateReview(pile, 'w1', true);
  assert.ok(!('w1' in pile));
  assert.deepStrictEqual(Q.updateReview({}, 'w2', true), {}, 'correct answers never add words');
});

test('final test gate and unlocking', () => {
  let r = Q.recordFinal(undefined, 0.7);
  assert.strictEqual(r.passedNow, false);
  r = Q.recordFinal(r.progress, 0.8);
  assert.strictEqual(r.passedNow, true);
  r = Q.recordFinal(r.progress, 0.2);
  assert.deepStrictEqual(r.progress, { best: 0.8, passed: true, attempts: 3 }, 'a later fail keeps the pass');
  const map = { 1: r.progress };
  assert.ok(Q.isUnlocked(map, 2));
  assert.ok(!Q.isUnlocked(map, 3));
  assert.strictEqual(Q.currentLektion(map, 24), 2);
});

test('daily streak', () => {
  let s = Q.bumpStreak(null, '2026-09-01');
  assert.deepStrictEqual(s, { last: '2026-09-01', count: 1 });
  s = Q.bumpStreak(s, '2026-09-01');
  assert.strictEqual(s.count, 1, 'same day does not double count');
  s = Q.bumpStreak(s, '2026-09-02');
  assert.strictEqual(s.count, 2);
  assert.strictEqual(Q.liveStreak(s, '2026-09-03'), 2, 'alive the next day');
  assert.strictEqual(Q.liveStreak(s, '2026-09-04'), 0, 'broken after a skipped day');
  assert.strictEqual(Q.bumpStreak(s, '2026-09-05').count, 1);
  assert.strictEqual(Q.bumpStreak({ last: '2026-02-28', count: 4 }, '2026-03-01').count, 5, 'month boundary');
});

console.log(`\nALL ${passed} MINI APP TESTS PASSED`);
