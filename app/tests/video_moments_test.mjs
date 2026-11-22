// Exercise the shipped storage code, including reloads and failed writes. No browser or network.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../../web/video-moments.js', import.meta.url), 'utf8');
const key = 'sg.saved', memory = new Map();
let failRead = false, failWrite = false, checks = 0;
const storage = {
  getItem(k) { if (failRead) throw new Error('denied'); return memory.has(k) ? memory.get(k) : null },
  setItem(k, value) { if (failWrite) throw new Error('quota'); memory.set(k, value) },
};
function reload() {
  const context = vm.createContext({ localStorage: storage });
  vm.runInContext(source, context);
  return context.VideoMoments;
}
const plain = value => JSON.parse(JSON.stringify(value));
const video = { id: 'video-a', title: 'Workshop demonstration' };
const legacy = [
  { key: 'd:manual:9', title: 'Manual, page 9', href: '#/read/manual?p=9', sub: 'Manual publisher' },
  { key: 'v:video-a', title: video.title, href: '#/watch/video-a', sub: 'Video' },
  { key: 'w:reference', title: 'Reference', href: '#/wiki/reference', extra: { kept: true } },
];
function test(name, run) {
  memory.clear(); failRead = failWrite = false;
  memory.set(key, JSON.stringify(legacy));
  run(reload()); checks++;
  console.log('PASS ' + name);
}

test('saving two times preserves every existing saved item', api => {
  api.save(video, 12.9, 'Tools needed'); api.save(video, 31, 'Reassembly');
  const items = plain(reload().readSaved());
  assert.equal(items.length, 5);
  assert.deepEqual(items.slice(2), legacy);
  assert.deepEqual(items.slice(0, 2).map(x => x.time), [31, 12]);
});
test('time zero remains an explicit position after reopening', api => {
  const item = api.save(video, 0, 'Introduction');
  assert.equal(reload().href(reload().readSaved()[0]), '#/watch/video-a?t=0');
  assert.equal(item.time, 0);
});
test('same video and second updates one moment rather than duplicating it', api => {
  const first = api.save(video, 12.1, 'First name');
  const second = api.save(video, 12.9, 'Better name');
  assert.equal(second.at, first.at);
  assert.equal(api.readSaved().filter(api.isMoment).length, 1);
  assert.equal(api.readSaved()[0].title, 'Better name');
});
test('two videos at the same second remain separate', api => {
  api.save(video, 10, 'First'); api.save({ id: 'video-b', title: 'Another video' }, 10, 'Second');
  assert.equal(api.readSaved().filter(api.isMoment).length, 2);
});
test('renaming preserves the position and the original video title', api => {
  const item = api.save(video, 23, 'Original');
  const changed = reload().rename(item.key, '  New name  ');
  assert.equal(changed.title, 'New name');
  assert.equal(changed.time, 23); assert.equal(changed.videoTitle, video.title);
  assert.equal(changed.href, item.href);
});
test('removing one moment leaves the video and all other saved items', api => {
  const first = api.save(video, 8, 'First'); api.save(video, 24, 'Second');
  reload().remove(first.key);
  const items = plain(api.readSaved());
  assert.equal(items.length, 4); assert.equal(items[0].time, 24);
  assert.deepEqual(items.slice(1), legacy);
});
test('a save reads the current list instead of overwriting intervening changes', api => {
  const other = { key: 'd:new:1', title: 'Another page', href: '#/read/new?p=1' };
  memory.set(key, JSON.stringify([...legacy, other]));
  api.save(video, 5, 'First');
  assert.deepEqual(plain(api.readSaved()).slice(1), [...legacy, other]);
});
test('renaming a removed moment does not recreate it', api => {
  const item = api.save(video, 5, 'First'); reload().remove(item.key);
  assert.throws(() => api.rename(item.key, 'Changed'), /no longer saved/);
  assert.deepEqual(plain(api.readSaved()), legacy);
});
test('legacy saved records cannot be renamed or removed as moments', api => {
  const before = memory.get(key);
  assert.throws(() => api.rename('v:video-a', 'Changed'), /no longer saved/);
  assert.throws(() => api.remove('d:manual:9'), /no longer saved/);
  assert.equal(memory.get(key), before);
});
test('quota failures leave all previous data unchanged', api => {
  const item = api.save(video, 9, 'First'), before = memory.get(key);
  failWrite = true;
  for (const write of [() => api.save(video, 10, 'Next'), () => api.rename(item.key, 'Next'), () => api.remove(item.key)]) {
    assert.throws(write, /left unchanged/); assert.equal(memory.get(key), before);
  }
});
test('a write succeeds after storage becomes available again', api => {
  failWrite = true; assert.throws(() => api.save(video, 5, 'First'));
  failWrite = false; api.save(video, 5, 'First');
  assert.equal(reload().readSaved()[0].title, 'First');
});
test('inaccessible storage is reported instead of claiming a successful save', api => {
  failRead = true;
  assert.throws(() => api.readSaved(), /could not be read/);
  assert.throws(() => api.save(video, 1, 'First'), /Nothing was changed/);
  failRead = false; assert.deepEqual(plain(api.readSaved()), legacy);
});
test('malformed JSON and non-list data are never overwritten', api => {
  for (const bad of ['{broken', '{}', 'null', '42', '"text"']) {
    memory.set(key, bad);
    assert.throws(() => api.readSaved(), /Nothing was changed/);
    assert.throws(() => api.save(video, 5, 'First'));
    assert.equal(memory.get(key), bad);
  }
});
test('an unused Saved list can receive its first moment', api => {
  memory.delete(key); assert.equal(api.readSaved().length, 0);
  api.save(video, 0, 'Start'); assert.equal(reload().readSaved().length, 1);
});
test('invalid times never write a saved item', api => {
  const before = memory.get(key);
  for (const time of [-1, NaN, Infinity, -Infinity, '10', null, undefined, 1e20])
    assert.throws(() => api.save(video, time, 'First'), /position/);
  assert.equal(memory.get(key), before);
});
test('Unicode and HTML-like names remain literal data', api => {
  const name = '<img onerror="bad()"> 測試 & café';
  const item = api.save(video, 5, name);
  assert.equal(reload().readSaved()[0].title, name);
  assert.equal(item.videoTitle, video.title);
});
test('empty and overlong names fail without changing data', api => {
  const before = memory.get(key);
  for (const title of ['', '   ', 'a'.repeat(121), null, 1])
    assert.throws(() => api.save(video, 5, title), /120 characters/);
  assert.equal(memory.get(key), before);
  api.save(video, 5, 'a'.repeat(120));
});
test('routes encode video IDs and never use a stored href', api => {
  const item = api.save({ id: 'clip:/?x#% café', title: 'Example' }, 12, 'First');
  item.href = 'javascript:bad()';
  assert.equal(api.href(item), '#/watch/clip%3A%2F%3Fx%23%25%20caf%C3%A9?t=12');
  assert.ok(api.isMoment(item));
});
test('malformed moment records are not treated as usable bookmarks', api => {
  const item = api.save(video, 5, 'First');
  for (const change of [{ time: -1 }, { time: 1.5 }, { time: null }, { key: 'wrong' }, { videoId: '' }, { videoId: '\uD800' }, { videoTitle: null }, { title: null }])
    assert.equal(api.isMoment({ ...item, ...change }), false);
  for (const bad of [null, 1, {}, 'text', ...legacy]) assert.equal(api.isMoment(bad), false);
});
test('unknown saved records are preserved during every write', api => {
  const unknown = { kind: 'future-kind', key: 'future:1', payload: { value: 7 } };
  memory.set(key, JSON.stringify([...legacy, unknown]));
  const item = api.save(video, 1, 'First'); api.rename(item.key, 'Next'); api.remove(item.key);
  assert.deepEqual(plain(api.readSaved()), [...legacy, unknown]);
});
test('a conflicting unknown record is not silently replaced', api => {
  const record = { key: 'm:video-a:5', kind: 'future-kind' };
  memory.set(key, JSON.stringify([record]));
  assert.throws(() => api.save(video, 5, 'First'), /could not be changed/);
  assert.deepEqual(plain(api.readSaved()), [record]);
});
console.log(JSON.stringify({ checks }));
