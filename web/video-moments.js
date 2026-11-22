'use strict';
// Named positions in videos use the existing Saved list. Nothing leaves this device.
globalThis.VideoMoments = (() => {
  const storageKey = 'sg.saved';
  const keyFor = (id, time) => 'm:' + encodeURIComponent(id) + ':' + time;
  const isMoment = item => {
    try {
      return !!item && item.kind === 'video-moment'
        && typeof item.videoId === 'string' && item.videoId.length > 0
        && Number.isSafeInteger(item.time) && item.time >= 0
        && typeof item.videoTitle === 'string' && typeof item.title === 'string'
        && item.key === keyFor(item.videoId, item.time);
    } catch { return false } // A damaged ID must not hide the rest of Saved.
  };
  const href = item => '#/watch/' + encodeURIComponent(item.videoId) + '?t=' + item.time;

  function readSaved() {
    try {
      const raw = localStorage.getItem(storageKey);
      const items = raw === null ? [] : JSON.parse(raw);
      if (!Array.isArray(items)) throw new Error();
      return items;
    } catch {
      throw new Error('Saved items could not be read. Nothing was changed.');
    }
  }

  function writeSaved(items) {
    try { localStorage.setItem(storageKey, JSON.stringify(items)) }
    catch { throw new Error('Could not update Saved. Your saved items were left unchanged.') }
  }

  function label(text) {
    if (typeof text !== 'string' || !text.trim() || text.trim().length > 120)
      throw new Error('Use a name between 1 and 120 characters.');
    return text.trim();
  }

  function save(video, seconds, title) {
    if (!video || typeof video.id !== 'string' || !video.id || typeof video.title !== 'string'
      || !Number.isFinite(seconds) || seconds < 0 || !Number.isSafeInteger(Math.floor(seconds)))
      throw new Error('This video position could not be saved.');
    // Keep the start of this second, so opening a moment does not skip past it.
    const time = Math.floor(seconds), key = keyFor(video.id, time), items = readSaved();
    const old = items.find(x => x && x.key === key);
    if (old && !isMoment(old)) throw new Error('This saved item could not be changed.');
    const item = { key, kind: 'video-moment', videoId: video.id, videoTitle: video.title, time,
      title: label(title), sub: video.title, at: old ? old.at : Date.now() };
    item.href = href(item);
    if (old) items[items.indexOf(old)] = item;
    else items.unshift(item);
    writeSaved(items);
    return item;
  }

  function rename(key, title) {
    const items = readSaved(), index = items.findIndex(x => isMoment(x) && x.key === key);
    if (index < 0) throw new Error('This moment is no longer saved.');
    items[index] = { ...items[index], title: label(title) };
    writeSaved(items);
    return items[index];
  }

  function remove(key) {
    const items = readSaved(), index = items.findIndex(x => isMoment(x) && x.key === key);
    if (index < 0) throw new Error('This moment is no longer saved.');
    items.splice(index, 1);
    writeSaved(items);
  }

  return Object.freeze({ readSaved, isMoment, href, save, rename, remove });
})();
