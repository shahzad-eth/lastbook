// Runs web/words.js in a fresh context and answers the cases in a JSON file.
// Usage: node topic_search_test.mjs <words.js> <cases.json> <segmenter|webkit|fallback|throwing>
// "fallback" removes Intl.Segmenter from the context first, as an older engine would; "throwing" leaves one
// whose constructor throws. "webkit" marks numbers as not word-like, as JavaScriptCore's Segmenter does
// (WebKitGTK 2.52 gives "112" isWordLike false; V8 gives true).
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const [, , wordsFile, casesFile, mode] = process.argv;
const ctx = vm.createContext({});   // its own globals, its own Intl
if (mode === 'fallback') vm.runInContext('delete Intl.Segmenter', ctx);
if (mode === 'webkit') vm.runInContext(`{
  const Real = Intl.Segmenter;
  Intl.Segmenter = class extends Real {
    segment(t) { return Array.from(super.segment(t), x => /^\\p{N}+$/u.test(x.segment) ? { ...x, isWordLike: false } : x) }
  };
}`, ctx);
if (mode === 'throwing') vm.runInContext("Intl.Segmenter = function () { throw new Error('no segmenter') }", ctx);
vm.runInContext(readFileSync(wordsFile, 'utf8'), ctx, { filename: 'words.js' });
const W = ctx.SearchWords;
const cases = JSON.parse(readFileSync(casesFile, 'utf8'));
const stop = new Set(cases.stop || []);

// topicMatches() as it was before words.js, kept here only to check English search ranks the same.
function before(q, topics) {
  const words = q.toLowerCase().split(/[^a-z0-9]+/).filter(w => w.length > 2 && !stop.has(w));
  if (!words.length || !topics) return [];
  const has = (hay, w) => new RegExp('\\b' + w).test(hay);
  const out = [];
  for (const t of topics) {
    const hay = [t.title, t.short, ...(t.keywords || [])].join(' ').toLowerCase();
    const s = words.filter(w => has(hay, w)).length;
    let best = null, bs = 0;
    for (const c of t.choices || []) { if (c.goto) continue; const ch = (c.label + ' ' + (c.hint || '')).toLowerCase(); const n = words.filter(w => has(ch, w)).length; if (n > bs) { bs = n; best = c } }
    if (s || bs) out.push({ t, c: best, s: s + bs * 1.5 });
  }
  out.sort((a, b) => b.s - a.s);
  return out.filter(o => o.s >= out[0]?.s * 0.6).slice(0, 3);
}
const brief = r => r.map(o => [o.t.id, o.c ? o.c.label : null]);
const safe = f => { try { return { ok: f() } } catch (e) { return { error: String(e) } } };

process.stdout.write(JSON.stringify({
  segmenter: W.hasSegmenter(),
  fold: (cases.fold || []).map(s => W.fold(s)),
  words: (cases.words || []).map(q => safe(() => W.queryWords(q, stop))),
  tops: (cases.tops || []).map(q => safe(() => W.rankTopics(q, cases.topics, stop).map(o => [o.t.id, o.c ? o.c.id : null]))),
  // The same searches ranked with the guides' phrases taken out, to compare with.
  topsPlain: (cases.topsPlain || []).map(q => safe(() => W.rankTopics(q, cases.plainTopics, stop).map(o => [o.t.id, o.c ? o.c.id : null]))),
  match: (cases.match || []).map(([text, w]) => safe(() => W.matcher(text)(w))),
  rank: (cases.rank || []).map(q => ({ q, now: safe(() => brief(W.rankTopics(q, cases.topics, stop))), before: brief(before(q, cases.topics)) })),
  rankOwn: (cases.rankOwn || []).map(([q, topics]) => safe(() => brief(W.rankTopics(q, topics, stop)))),
  rankForms: (cases.rankForms || []).map(([q, topics]) => safe(() => brief(W.rankTopics(q, topics, stop)))),
}));
