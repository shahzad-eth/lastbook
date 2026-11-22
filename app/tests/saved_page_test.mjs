// Run the shipped Saved page and storage reader with stand-ins for its DOM and library.
// The browser regression check separately covers the complete page and navigation.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = name => readFileSync(new URL('../../web/' + name, import.meta.url), 'utf8');
const app = source('app.js'), start = app.indexOf('async function savedPage() {');
const end = app.indexOf('\n/* ', start);
assert.ok(start >= 0 && end > start, 'the shipped Saved page is present');
const pageSource = app.slice(start, end);
const legacy = { key: 'd:manual:9', title: 'Saved manual', href: '#/read/manual?p=9', sub: 'Manual' };
const moment = { key: 'm:video-a:12', kind: 'video-moment', videoId: 'video-a',
  videoTitle: 'Workshop demonstration', title: 'Tools needed', time: 12 };
const valid = JSON.stringify([legacy, moment]);
let checks = 0;

function open(raw = valid, denied = false) {
  const memory = new Map([
    ['sg.recent', JSON.stringify([{ key: 'd:recent:1', title: 'Recent manual', href: '#/read/recent?p=1', sub: 'Manual' }])],
    ['sg.vprog', JSON.stringify({ 'video-a': { t: 31, d: 90, title: 'Workshop demonstration' } })],
  ]);
  if (raw !== null) memory.set('sg.saved', raw);
  const state = { denied, writes: [], wired: 0 }, main = { innerHTML: '' }, clear = {};
  const localStorage = {
    getItem(key) { if (key === 'sg.saved' && state.denied) throw Error('denied'); return memory.get(key) ?? null },
    setItem(key, value) { state.writes.push(key); memory.set(key, value) },
  };
  const esc = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const context = vm.createContext({
    localStorage, main, esc, setTitle() {}, ico: () => '', rowSub: x => x.sub,
    recents: async () => JSON.parse(localStorage.getItem('sg.recent')),
    resumable: async () => Object.entries(JSON.parse(localStorage.getItem('sg.vprog'))),
    held: async ids => ids,
    secHead: title => `<h2>${title}</h2>`, rail: html => `<div>${html}</div>`,
    vcard: video => `<a href="#/watch/${video.id}">${esc(video.title)}</a>`, clock: time => String(time),
    momentSection: () => '<section>Video moments</section>', wireMoments() { state.wired++ },
    $: selector => selector === '#clr' && main.innerHTML.includes('id="clr"') ? clear : null,
    store: { set: (key, value) => localStorage.setItem('sg.' + key, JSON.stringify(value)) },
  });
  vm.runInContext(source('video-moments.js'), context, { filename: 'video-moments.js' });
  vm.runInContext(pageSource, context, { filename: 'savedPage from app.js' });
  return { context, memory, state, main, clear };
}

function independentSections(page) {
  assert.match(page.main.innerHTML, /Continue watching/);
  assert.match(page.main.innerHTML, /href="#\/watch\/video-a"/);
  assert.match(page.main.innerHTML, /Workshop demonstration/);
  assert.match(page.main.innerHTML, /Recently opened/);
}
function readError(page) {
  independentSections(page);
  assert.match(page.main.innerHTML, /role="alert"[^>]*>Saved items could not be read\. Nothing was changed\./);
  assert.match(page.main.innerHTML, /href="#\/read\/recent\?p=1"/);
  assert.doesNotMatch(page.main.innerHTML, /Nothing saved yet/);
  assert.equal(page.state.wired, 0);
}
async function test(name, run) {
  await run(); checks++; console.log('PASS ' + name);
}

for (const raw of ['{broken', '{}', 'null', '42', '"text"', 'true']) {
  await test('unreadable Saved preserves other sections and bytes: ' + raw, async () => {
    const page = open(raw);
    await page.context.savedPage();
    readError(page);
    assert.equal(page.memory.get('sg.saved'), raw);
    assert.deepEqual(page.state.writes, []);
  });
}
await test('a denied Saved read does not hide readable history or progress', async () => {
  const page = open(valid, true);
  await page.context.savedPage();
  readError(page);
  assert.equal(page.memory.get('sg.saved'), valid);
  assert.deepEqual(page.state.writes, []);
});
await test('valid saved items and moments still render without writing storage', async () => {
  const page = open();
  await page.context.savedPage();
  independentSections(page);
  assert.match(page.main.innerHTML, /Saved manual/);
  assert.equal(page.state.wired, 1);
  assert.doesNotMatch(page.main.innerHTML, /could not be read|Nothing saved yet/);
  assert.equal(page.memory.get('sg.saved'), valid);
  assert.deepEqual(page.state.writes, []);
});
for (const raw of [null, '[]']) {
  await test('an empty or unused Saved list keeps its normal empty state: ' + raw, async () => {
    const page = open(raw);
    await page.context.savedPage();
    independentSections(page);
    assert.match(page.main.innerHTML, /Nothing saved yet/);
    assert.doesNotMatch(page.main.innerHTML, /could not be read/);
    assert.equal(page.memory.get('sg.saved') ?? null, raw);
    assert.deepEqual(page.state.writes, []);
  });
}
await test('clearing recent history while Saved is unreadable changes only recent history', async () => {
  const page = open(valid, true);
  await page.context.savedPage();
  page.clear.onclick();
  await new Promise(setImmediate);
  independentSections(page);
  assert.match(page.main.innerHTML, /Saved items could not be read/);
  assert.doesNotMatch(page.main.innerHTML, /Recent manual/);
  assert.equal(page.memory.get('sg.saved'), valid);
  assert.equal(page.memory.get('sg.recent'), '[]');
  assert.deepEqual(page.state.writes, ['sg.recent']);
});
await test('reopening Saved after reads recover restores the original saved items', async () => {
  const page = open(valid, true);
  await page.context.savedPage();
  page.state.denied = false;
  await page.context.savedPage();
  independentSections(page);
  assert.match(page.main.innerHTML, /Saved manual/);
  assert.doesNotMatch(page.main.innerHTML, /could not be read/);
  assert.equal(page.state.wired, 1);
  assert.equal(page.memory.get('sg.saved'), valid);
  assert.deepEqual(page.state.writes, []);
});
console.log(JSON.stringify({ checks }));
