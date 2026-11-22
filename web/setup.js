'use strict';
/* Lastbook setup: choose a library and the local AI, then download, check, unpack and switch. The contract is docs/SETUP-API.md.
   Works on its own page in setup mode (no library, so none of /api/topics and the rest) and inside the app (Library → Library and local AI).
   Views: manage (what is here now), choose (what to get), job (progress, pause, errors), done. Plain fetch: in the app the bridge adds the key. */
(() => {
  const $ = s => document.querySelector(s);
  const main = $('#main'), live = $('#live');
  const languageHasFocus = () => $('#languageSettings')?.contains(document.activeElement);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const WIN = document.documentElement.classList.contains('plat-win');
  const UNIT = WIN ? 1024 : 1000;   // each system's own way of counting a gigabyte, so the numbers match Finder or Explorer
  const CAN = { removeAi: true, repair: true };   // one switch each, should a build of the engine be without remove-ai or repair
  const MANAGE_ASKED = /manage/.test(location.hash);   // #manage: the bridge allows no ?query on the top page

  const ICO = {
    disk: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 15h.01M11 15h6"/>',
    chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    gpu: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="9" cy="12" r="3"/><path d="M15 10h3M15 14h3"/>',
    book: '<path d="M4 4v16M9 4v16M14 5l4 15M3 20h18"/>',
    ai: '<path d="M4 5h16v11H9l-5 4z"/><path d="M9 9.5h6M9 12.5h4"/>',
    ok: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    warn: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
    file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
    pause: '<path d="M9 6v12M15 6v12"/>',
    play: '<path d="m8 5 11 7-11 7z"/>',
    back: '<path d="M15 18 9 12l6-6"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    retry: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    repair: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.2L3 17.8 6.2 21l6.3-6.3a4 4 0 0 0 5.2-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
    down: '<path d="M12 5v14M5 12l7 7 7-7"/>',
    up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
    map: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  };
  const ico = (k, cls) => `<svg viewBox="0 0 24 24" aria-hidden="true"${cls ? ` class="${cls}"` : ''}>${ICO[k] || ''}</svg>`;

  /* ------------------------------------------------------------ numbers */
  function size(b) {
    if (b == null || !isFinite(b)) return '';
    const g = b / UNIT ** 3;
    if (g >= 100) return Math.round(g).toLocaleString() + ' GB';
    if (g >= 1) return g.toFixed(1) + ' GB';
    const m = b / UNIT ** 2;
    return (m >= 10 ? Math.round(m) : m.toFixed(1)) + ' MB';
  }
  const ram = b => Math.round(b / 1024 ** 3) + ' GB';   // memory is counted in binary by both systems
  const rate = bps => bps > 0 ? (bps / UNIT ** 2 >= 10 ? Math.round(bps / UNIT ** 2) : (bps / UNIT ** 2).toFixed(1)) + ' MB/s' : '';
  function eta(s) {
    if (s == null || !isFinite(s) || s < 0) return '';
    if (s < 60) return 'under a minute left';
    const m = Math.round(s / 60);
    if (m < 60) return `about ${m} min left`;
    const h = Math.floor(m / 60), r = m % 60;
    return `about ${h} h${r ? ` ${r} min` : ''} left`;
  }
  const retryIn = s => `The server is busy. Retrying in ${s < 60 ? 'under a minute' : Math.ceil(s / 60) + ' min'}`;
  const home = p => String(p || '').replace(/^\/Users\/[^/]+/, '~').replace(/^[A-Z]:\\Users\\[^\\]+\\/i, '');   // ~/… on a Mac; Documents\… on Windows, as Explorer names it

  /* ------------------------------------------------------------ the engine */
  async function call(path, body) {
    const opts = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    let r; try { r = await fetch('/api/setup/' + path, opts) } catch { throw Object.assign(new Error('Lastbook did not answer. Close it and open it again.'), { status: 0 }) }
    let d = null; try { d = await r.json() } catch { }
    if (!r.ok && !(d && (d.error || d.need_bytes))) throw Object.assign(new Error(r.status === 404 ? 'Not available.' : 'Lastbook sent an unreadable reply.'), { status: r.status });
    return d;
  }
  const errCode = e => e && (typeof e === 'object' ? e.code : null);
  const errText = e => e && (typeof e === 'object' ? e.message || e.error : e);

  /* ------------------------------------------------------------ state */
  let S = null;           // GET state
  let view = 'choose';
  let choice = { pack: null, ai: false, map: null };   // map: the selected state code
  let folder = '';
  let shortfall = null;   // the answer to a start that had no room: {need_bytes, free_bytes}
  let pollT = 0;
  let confirmCancel = false, confirmRemove = false, confirmOld = false;
  let note = '', noteOk = false;
  let repair = null;      // a repair under way: {fixed} turns true once it had to download something; {sure}: this page saw it from the start

  const packs = () => (S.manifest && S.manifest.packs) || [];
  const model = () => ((S.manifest && S.manifest.models) || [])[0] || null;
  const cur = () => S.current || null;
  const packById = id => packs().find(p => p.id === id);
  function packNeedsInstall(pack) {
    if (!pack) return false;
    const current = cur();
    if (!current || pack.id !== current.pack) return true;
    return Boolean(pack.revision && pack.revision !== current.content_revision);
  }

  /* state maps (docs/SETUP-API.md, State maps). The person picks the state; Lastbook never looks for where it is */
  const maps = () => ((S.manifest && S.manifest.maps) || []).slice().sort((a, b) => String(a.title).localeCompare(String(b.title)));   // by name, as people look for theirs
  const mapById = id => maps().find(m => m.id === id);
  const mapName = id => id === 'us' ? 'the whole US' : (mapById(id) || {}).title || id;
  /* the detailed map the library will have once the chosen pack is in: the person's state map, or the one the pack carries */
  const PACK_MAP = { medium: 'CA', all: 'us' };   // what the packs carry today; a manifest packs[].map, when there, wins
  const packMap = id => { const p = packById(id) || {}; return 'map' in p ? p.map || null : PACK_MAP[id] || null };
  const mapNow = () => { const c = cur() || {}; return choice.pack && choice.pack !== c.pack ? packMap(choice.pack) : (c.map && c.map !== 'base' ? c.map : packMap(c.pack)) };
  const selectedState = () => choice.map || (mapNow() !== 'us' && mapNow()) || ((cur() || {}).address_indexes || [])[0] || '';
  const addresses = () => (S.manifest && S.manifest.address_indexes) || [];
  const addressById = id => addresses().find(a => a.id === id);
  const addressAdds = () => { const a = addressById(selectedState()); return a && a.available !== false && !((cur() || {}).address_indexes || []).includes(a.id) ? a : null };
  const mapMissing = () => !selectedState();
  const mapAdds = () => choice.map && choice.map !== mapNow() && mapNow() !== 'us' ? mapById(choice.map) : null;
  function packSummary(p) {
    const text = p.summary || '';
    if (p.id !== 'medium' || !maps().length) return text;
    // The manifest describes the archive's bundled map. Setup replaces it with the chosen state map.
    const state = selectedState();
    return text.replace(/\ba detailed map of California\b/, () => 'a detailed map of ' + (state ? mapName(state) : 'your state'));
  }
  const packDl = p => p.download_bytes || (p.files || []).reduce((n, f) => n + (f.size || 0), 0);
  const SEP = WIN ? '\\' : '/', DATA = 'LastbookData';
  const asData = p => /[\\/]LastbookData[\\/]?$/i.test(p) ? p.replace(/[\\/]$/, '') : String(p).replace(/[\\/]$/, '') + SEP + DATA;
  /* a file already on this computer, of the right size, for a pack or the model: setup uses it instead of downloading */
  const foundFor = (kind, id) => (S.found || []).find(f => f.kind === kind && (f.size_ok !== false) && (kind === 'model' || f.id === id || f.pack === id));
  const aiFits = () => !!(S.hardware && S.hardware.ai && S.hardware.ai.fits);

  function diskFor(path) {
    const ds = (S.hardware && S.hardware.disks) || [];
    const norm = s => WIN ? String(s).toLowerCase().replace(/\//g, '\\') : String(s);
    const p = norm(path);
    let best = null;
    for (const d of ds) if (p.startsWith(norm(d.path)) && (!best || d.path.length > best.path.length)) best = d;
    return best || (path ? null : ds[0] || null);   // a folder on a disk the engine did not report: its free space is not known here
  }
  const diskName = d => !d ? 'this disk' : d.name || (WIN ? (String(d.path).match(/^[A-Z]:/i) || ['this disk'])[0].toUpperCase()   // C:, D:
    : /^\/Volumes\/[^/]+/.test(d.path) ? d.path.split('/')[2] : /Linux/.test(navigator.platform || '') ? 'this computer' : 'this Mac');

  function plan() {   // what the current choice adds: bytes to download, space it needs (download + unpacked + 2 GB, as the engine counts)
    const c = cur() || {};
    let dl = 0, need = 0;
    const p = packById(choice.pack);
    if (packNeedsInstall(p)) {
      const got = foundFor('pack', p.id);
      if (!got) dl += packDl(p);
      need += (got ? 0 : packDl(p)) + (p.installed_bytes || 0);
      if (p.id === c.pack) need += c.map_bytes || 0;
    }
    const m = model();
    if (choice.ai && m && !c.model && aiFits()) { const got = foundFor('model'); if (!got) { dl += m.size || 0; need += m.size || 0 } else need += m.size || 0 }
    const mp = mapAdds();
    if (mp) { const got = foundFor('map', mp.id); if (!got) dl += packDl(mp); need += (got ? 0 : packDl(mp)) + (mp.installed_bytes || 0) }
    const a = addressAdds();
    if (a) { dl += packDl(a); need += packDl(a) + (a.installed_bytes || 0) }
    if (need) need += 2 * 1000 ** 3;
    return { dl, need };
  }

  async function load() {
    try { S = await call('state') }
    catch (e) {
      main.innerHTML = `<div class="s-err" role="alert">${ico('warn')}<div><b data-i18n="setup.error">Setup could not start.</b><p>${esc(e.message)}</p><p><button class="btn" id="again" data-i18n="setup.tryAgain">Try again</button></p></div></div>`;
      globalThis.LastbookI18n?.apply(main);
      $('#again').onclick = load;
      return;
    }
    const rf = (S.recommend || {}).folder;
    folder = folder || (cur() && cur().folder) || S.default_folder || (rf ? asData(rf) : '');
    if (!choice.pack) {
      const rec = S.recommend || {};
      const small = packById('small');
      choice.pack = small && small.available !== false ? 'small' : null;
      choice.ai = !!rec.ai && aiFits();
      if (cur()) { choice.pack = cur().pack; choice.ai = !!cur().model }
    }
    const j = S.job;
    if (j && j.state && j.state !== 'done' && !(j.state === 'failed' && errCode(j.error) === 'cancelled')) view = 'job';
    else if (j && j.state === 'done') view = j.copy && cur() ? 'manage' : 'done';   // a finished copy: back to Library and local AI
    else if (cur() || S.mode === 'manage' || MANAGE_ASKED) view = cur() ? 'manage' : 'choose';
    $('#sBack').hidden = !cur();
    render(true);
  }

  /* ------------------------------------------------------------ views */
  function render(focus) {
    clearTimeout(pollT);
    shapeKey = '';
    if (view === 'manage') manageView();
    else if (view === 'choose') chooseView();
    else if (view === 'job') jobView(S.job);
    else if (view === 'done') doneView();
    else if (view === 'copy') copyView();
    if (focus && !languageHasFocus()) { const h = main.querySelector('h1'); if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }) } scrollTo(0, 0) }
  }
  function go(v) { view = v; confirmCancel = confirmRemove = confirmOld = false; note = ''; if (v === 'manage' || v === 'choose') repair = null; render(true) }

  /* ---- this computer */
  function computer() {
    const h = S.hardware || {}, d = diskFor(folder), tiles = [];
    if (d) tiles.push([ico('disk'), size(d.free_bytes), `free on ${esc(diskName(d))}`]);
    if (h.ram_bytes) tiles.push([ico('chip'), ram(h.ram_bytes), h.unified_memory ? 'memory, shared with graphics' : 'memory']);
    if (!h.unified_memory) {
      const g = (h.gpus || []).slice().sort((a, b) => (b.vram_bytes || 0) - (a.vram_bytes || 0))[0];
      tiles.push(g ? [ico('gpu'), g.vram_bytes ? ram(g.vram_bytes) : '—', `graphics: ${esc(g.name)}`] : [ico('gpu'), 'None', 'graphics card for the AI']);
    }
    return `<section class="s-pc" aria-label="This computer">${tiles.map(t => `<div class="s-tile">${t[0]}<b>${t[1]}</b><small>${t[2]}</small></div>`).join('')}</section>`;
  }
  function recommendLine() {
    const r = S.recommend || {}, p = packById(r.pack);
    if (!p) return r.why ? `<p class="s-rec bad">${ico('warn')}<span>${esc(r.why)}</span></p>` : '';
    const what = `${esc(p.title)}${r.ai && aiFits() ? ' with the local AI' : ''}`;
    return `<p class="s-rec">${ico('ok')}<span><b>Suggested: ${what}.</b> ${esc(r.why || '')}</span></p>`;
  }

  /* ---- choose */
  function chooseView() {
    const c = cur(), m = model();
    const packCards = packs().map(p => {
      const update = c && c.pack === p.id && packNeedsInstall(p);
      const off = p.available === false, here = c && c.pack === p.id && !update, rec = (S.recommend || {}).pack === p.id && !c;
      const badge = off ? '<span class="s-badge later">Coming later</span>' : update ? '<span class="s-badge rec">Update available</span>' : here ? '<span class="s-badge here">Installed</span>' : rec ? '<span class="s-badge rec">Suggested</span>' : '';
      return `<label class="s-opt${off ? ' off' : ''}">
        <input type="radio" name="pack" value="${esc(p.id)}"${choice.pack === p.id ? ' checked' : ''}${off ? ' disabled' : ''}>
        <span class="s-opt-in"><span class="s-opt-h"><b>${esc(p.title)}</b>${badge}</span>
        <small data-pack-summary="${esc(p.id)}">${esc(packSummary(p))}</small>
        <span class="s-sizes">${off ? 'Not ready to download yet' : here ? 'On this computer' : `<span>${foundFor('pack', p.id) ? 'Already downloaded' : size(packDl(p)) + ' download'}</span><span>${size(p.installed_bytes)} on disk</span>`}</span></span></label>`;
    }).join('');
    let ai = '';
    if (m && m.available !== false) {
      const has = c && c.model;
      ai = aiFits() || has
        ? `<label class="s-opt s-ai"><input type="checkbox" id="aiBox"${choice.ai || has ? ' checked' : ''}${has ? ' disabled' : ''}>
            <span class="s-opt-in"><span class="s-opt-h"><b>Local AI</b>${has ? '<span class="s-badge here">Installed</span>' : (S.recommend || {}).ai && !c ? '<span class="s-badge rec">Suggested</span>' : '<span class="s-badge">Optional</span>'}</span>
            <small>Answers questions from the library, in plain words. Works offline.</small>
            <span class="s-sizes">${has ? 'On this computer' : foundFor('model') ? '<span>Already downloaded</span>' : `<span>About ${size(m.size)} download</span>`}</span></span></label>`
        : `<div class="s-opt s-ai off" role="group" aria-label="Local AI"><span class="s-opt-in"><span class="s-opt-h"><b>Local AI</b><span class="s-badge later">Not for this computer</span></span>
            <small>${esc((S.hardware.ai && S.hardware.ai.why) || 'This computer does not have enough memory for it.')}</small></span></div>`;
    }
    const found = (S.found || []).map((f, i) => f.rejected ? `<div class="s-found off">${ico('file')}<span><b>${esc(f.name || f.path.split(/[\\/]/).pop())}</b><small>${esc(home(f.path))} · doesn’t match the published file, so it is not used</small></span></div>`
      : f.size_ok === false ? '' : `<div class="s-found">${ico(f.kind === 'library' ? 'folder' : 'file')}<span><b>${esc(f.kind === 'library' ? 'A Lastbook library' : f.kind === 'model' ? 'The local AI file' : (packById(f.id) ? packById(f.id).title + ' library' : f.title || f.name))}</b><small>${esc(home(f.path))}${f.size ? ' · ' + size(f.size) : ''}</small></span>
        <button class="btn plain" data-use="${i}">Use the file you already have</button></div>`).join('');

    main.innerHTML = `${c ? `<button class="s-link" id="toManage">${ico('back')}<span data-i18n="setup.settingsTitle">Library and local AI</span></button>` : ''}
      ${c ? '<h1 data-i18n="setup.changeLibrary">Change the library</h1>' : '<h1 data-i18n="setup.title">Set up Lastbook</h1>'}
      ${c ? '' : '<p class="lead" data-i18n="setup.chooseIntro">Choose your state and library. Lastbook downloads them for offline use.</p>'}
      ${computer()}
      ${c ? '' : recommendLine()}
      ${found ? `<h2>Found on this computer</h2><div class="s-founds">${found}</div>` : ''}
      <section id="mapBox" class="s-map-panel" aria-label="Your local map"></section>
      <h2 id="packH" data-i18n="nav.library">Library</h2>
      <div class="s-opts" role="radiogroup" aria-labelledby="packH">${packCards}</div>
      ${ai ? `<h2>Local AI</h2>${ai}` : ''}
      <section class="s-sum" id="sum" aria-live="polite"></section>
      <div class="s-go">
        <button class="btn big" id="start"></button>
        ${c ? '' : '<button class="s-link" id="haveLib">Choose an existing library folder</button>'}
        <button class="s-link" id="haveFile">Choose a library zip or AI model file</button>
      </div>
      <p class="s-note" id="haveNote" hidden></p>`;
    main.querySelectorAll('input[name=pack]').forEach(r => r.onchange = () => { choice.pack = r.value; shortfall = null; mapSection(); summary() });
    const box = $('#aiBox'); if (box && !box.disabled) box.onchange = () => { choice.ai = box.checked; shortfall = null; summary() };
    main.querySelectorAll('[data-use]').forEach(b => b.onclick = () => useFile((S.found || [])[+b.dataset.use].path, b));
    $('#start').onclick = start;
    if ($('#toManage')) $('#toManage').onclick = () => go('manage');
    if ($('#haveLib')) $('#haveLib').onclick = () => haveLibrary(false);
    $('#haveFile').onclick = () => haveLibrary(true);
    mapSection();
    summary();
    globalThis.LastbookI18n?.apply(main);
  }
  /* Map geometry and address indexes are separate downloads, chosen by state. */
  function mapSection() {
    const box = $('#mapBox'), now = mapNow();
    if (!box) return;
    main.querySelectorAll('[data-pack-summary]').forEach(el => { el.textContent = packSummary(packById(el.dataset.packSummary)) });
    const selected = selectedState();
    const opts = maps().map(m => {
      const a = addressById(m.id), included = now === 'us' || m.id === now;
      const addressIncluded = ((cur() || {}).address_indexes || []).includes(m.id);
      const off = !included && m.available === false;
      const bytes = (included ? 0 : packDl(m)) + (a && a.available !== false && !addressIncluded ? packDl(a) : 0);
      const details = off ? 'coming later' : bytes ? size(bytes) + ' download' : 'included';
      return `<option value="${esc(m.id)}"${selected === m.id ? ' selected' : ''}${off ? ' disabled' : ''}>${esc(m.title)} — ${details}</option>`;
    }).join('');
    const sel = mapById(selected), a = addressAdds();
    const mapIncluded = now === 'us' || selected === now;
    const bytes = (sel && !mapIncluded ? packDl(sel) : 0) + (a ? packDl(a) : 0);
    const disk = (sel && !mapIncluded ? sel.installed_bytes || 0 : 0) + (a ? a.installed_bytes || 0 : 0);
    const unavailable = selected && addresses().length && (!addressById(selected) || addressById(selected).available === false);
    let hint = !sel ? 'Select your state to continue.' : bytes ? `${size(bytes)} download · ${size(disk)} on disk${mapIncluded && a ? '. Your map is already included; only the address index downloads.' : ''}` : 'Your state map and available address index are already included.';
    if (unavailable) hint = (bytes ? `${size(bytes)} download · ${size(disk)} on disk.` : 'Your state map is already included.') + ' Street-address search is not available for this state yet.';
    box.innerHTML = `<h2>${ico('map')}Your local map</h2>
      <p class="s-mapnote">Local streets, buildings, water and places to get help. Available offline.</p>
      ${now === 'us' ? '<p class="s-mapnote">All includes every state map. Choose your state for offline street-address search.</p>' : ''}
      <label class="s-maplabel" for="mapSel">Choose your state</label>
      <select id="mapSel" class="s-select" required aria-describedby="mapHint"><option value="" disabled${selected ? '' : ' selected'}>Select a state</option>${opts}</select>
      <p class="s-hint" id="mapHint">${hint}</p>`;
    $('#mapSel').onchange = e => { choice.map = e.target.value; shortfall = null; mapSection(); summary(); $('#mapSel').focus() };
  }
  function summary() {
    const { dl, need } = plan(), d = diskFor(folder), free = d ? d.free_bytes : null;
    const short = shortfall || (need && free != null && free < need ? { need_bytes: need, free_bytes: free } : null);
    const pct = need && free ? Math.min(100, need / free * 100) : short ? 100 : 0;
    const c = cur();
    $('#sum').innerHTML = need ? `
      <div class="s-nums"><span><small>Download</small><b>${dl ? size(dl) : 'None'}</b></span><span><small>Space needed</small><b>${size(short ? short.need_bytes : need)}</b></span><span><small>Free on ${esc(diskName(d))}</small><b>${short ? size(short.free_bytes) : free != null ? size(free) : 'Checked at start'}</b></span></div>
      ${free == null && !short ? '' : `<div class="s-meter${short ? ' bad' : ''}" role="img" aria-label="Uses ${Math.round(pct)} percent of the free space"><i style="width:${pct}%"></i></div>`}
      ${short ? `<p class="s-short">${ico('warn')}<span>Not enough room: this needs ${size(short.need_bytes)}, and ${esc(diskName(d))} has ${size(short.free_bytes)} free. Pick a smaller library or another folder.</span></p>` : ''}
      ${folderRow()}`
      : `<p class="s-nothing">${c ? 'This is what you have now.' : 'Pick a library.'}</p>${c ? '' : folderRow()}`;
    const b = $('#start');
    b.disabled = !need || !!short || mapMissing();
    const newPack = c && packNeedsInstall(packById(choice.pack)), newAi = c && choice.ai && !c.model, newMap = c && mapAdds(), newAddresses = c && addressAdds();
    const parts = [newPack && packById(choice.pack).title, newAi && 'the local AI', newMap && `the ${newMap.title} map`, newAddresses && !newMap && 'offline address search'].filter(Boolean);
    b.textContent = mapMissing() ? 'Choose your state to continue' : !c ? 'Download and install' : parts.length ? 'Get ' + parts.join(parts.length > 2 ? ', ' : ' and ').replace(/, ([^,]*)$/, ' and $1') : 'Nothing to add';
    if (newPack && choice.pack === c.pack && !mapMissing()) b.textContent = 'Download and install update';
    const ch = $('#chFolder'); if (ch) ch.onclick = pickFolder;
  }
  const folderRow = () => `<div class="s-folder">${ico('folder')}<span><small>Saves to</small><b title="${esc(folder)}">${esc(home(folder))}</b></span>${cur() ? '' : '<button class="btn plain" id="chFolder">Change…</button>'}</div>`;

  async function pickFolder() {
    const b = $('#chFolder'); b.disabled = true;
    try {
      const r = await call('pick', {});
      if (r && r.path) {
        folder = asData(r.path);
        if (r.free_bytes != null) (S.hardware.disks = S.hardware.disks || []).push({ path: r.path, name: r.disk, free_bytes: r.free_bytes });   // the chosen place's own disk
        shortfall = null;
        const pc = main.querySelector('.s-pc'); if (pc) pc.outerHTML = computer();
      }
      summary();
    } catch { b.disabled = false; b.textContent = 'Can’t change here' }
  }
  async function haveLibrary(files, btn, only) {
    const n = $('#haveNote');
    try {
      const r = await call('pick', { files });
      if (r && r.path) return useFile(r.path, btn || $(files ? '#haveFile' : '#haveLib'), only);
      if (r && (r.cancelled || r.path === null)) return;
      throw 0;
    } catch {
      n.hidden = false;
      n.textContent = 'The picker could not open. Try choosing the file or folder again.';
    }
  }
  async function useFile(path, btn, only) {
    if (btn) btn.disabled = true;
    try {
      const r = await call('use', { path, ...only });
      if (r && r.error) throw new Error(r.error);
      if (r && r.noted) { S = await call('state').catch(() => S); choice.ai = true; chooseView(); const n = $('#haveNote'); n.hidden = false; n.textContent = 'The local AI file will be used. No need to download it.'; return }
      S.job = r; go(r.state === 'done' ? 'done' : 'job'); poll();
    } catch (e) {
      if (btn) btn.disabled = false;
      const n = $('#haveNote'); n.hidden = false; n.textContent = e.message;
    }
  }
  async function start() {
    if (mapMissing()) { $('#mapSel')?.focus(); return }
    const b = $('#start'); b.disabled = true;
    const r = await call('start', { pack: packNeedsInstall(packById(choice.pack)) ? choice.pack : null, ai: !!choice.ai && aiFits() && !(cur() || {}).model, map: mapAdds() ? choice.map : null, address_id: addressById(selectedState())?.available !== false && addressById(selectedState()) ? selectedState() : null, folder }).catch(e => ({ error: e.message }));
    if (r && r.need_bytes) { shortfall = r; summary(); return }
    if (!r || r.error) { b.disabled = false; const n = $('#haveNote'); n.hidden = false; n.textContent = (r && r.error) || 'Setup could not start.'; return }
    S.job = r; go('job'); poll();
  }

  /* ---- manage */
  function manageView() {
    const c = cur(), p = packById(c.pack), m = model();
    const libraryUpdate = p && p.available !== false && packNeedsInstall(p);
    const o = [].concat(c.old || [])[0], old = o ? (typeof o === 'string' ? { path: o } : o) : null;   // the engine lists the paths it moved aside
    const larger = packs().filter(x => (x.installed_bytes || 0) > ((p && p.installed_bytes) || 0));
    const bigger = larger.filter(x => x.available !== false), later = larger.find(x => x.available === false);
    main.innerHTML = `<h1 data-i18n="setup.settingsTitle">Library and local AI</h1>
      <div class="s-have">
        <div class="s-row">${ico('book', 's-ri')}<span><b>${esc(p ? p.title : c.pack || 'Library')} library</b><small>${libraryUpdate ? 'Updated edition available · ' : p ? size(p.installed_bytes) + ' · ' : ''}${esc(home(c.folder))}</small></span>
          ${libraryUpdate ? `<button class="btn" id="libraryUpdate">Update ${esc(p.title)}</button>` : bigger.length ? `<button class="btn" id="upgrade">${ico('up')}Get ${esc(bigger[0].title)}</button>` : later ? `<span class="s-badge later">${esc(later.title)} comes later</span>` : '<span class="s-badge here">The largest</span>'}</div>
        ${m && m.available !== false ? `<div class="s-row">${ico('ai', 's-ri')}<span><b>Local AI</b><small>${c.model ? 'On this computer · ' + size(m.size) : aiFits() ? 'Not installed · about ' + size(m.size) : esc((S.hardware.ai && S.hardware.ai.why) || 'Not for this computer.')}</small></span>
          ${c.model ? (!CAN.removeAi ? '' : confirmRemove ? `<span class="s-confirm"><button class="btn danger" id="rmYes">Remove</button><button class="btn plain" id="rmNo">Keep</button></span>` : '<button class="btn plain" id="rmAi">Remove</button>') : aiFits() ? `<button class="btn" id="addAi">Add</button>` : ''}</div>` : ''}
        ${maps().length ? (() => { const mNow = c.map && c.map !== 'base' ? c.map : packMap(c.pack);
          return `<div class="s-row">${ico('map', 's-ri')}<span><b>${mNow ? 'Detailed map: ' + esc(mapName(mNow)) : 'Detailed map'}</b><small>${mNow ? (mNow === 'us' ? 'Local streets and terrain everywhere' : 'Local streets, buildings and terrain') : 'None yet. Add one for your state.'}</small></span>
          <button class="btn plain" id="mapCh">${(c.address_indexes || []).length ? 'Choose state' : 'Add address search'}</button></div>` })() : ''}
      </div>
      ${old ? `<div class="s-row s-old">${ico('folder', 's-ri')}<span><b>The old library is still here</b><small>${esc(home(old.path))}${old.bytes ? ' · ' + size(old.bytes) : ''}</small></span>${confirmOld ? `<span class="s-confirm"><span>Delete it for good?</span><button class="btn danger" id="oldYes">Delete</button><button class="btn plain" id="oldNo">Keep</button></span>` : `<button class="btn plain" id="rmOld">${ico('trash')}Delete it</button>`}</div>` : ''}
      ${computer()}
      <div class="s-have"><div class="s-row">${ico('folder', 's-ri')}<span><b data-i18n="setup.copyTitle">Copy for someone else</b><small>Puts this library on a drive, with a START-HERE.txt, so someone can set up Lastbook with no internet. Nothing of yours is copied.</small></span><button class="btn plain" id="copyOut">Copy to a drive…</button></div></div>
      <div class="s-go left">${CAN.repair ? `<button class="btn plain" id="repair">${ico('repair')}Check and repair</button>` : ''}
        <button class="s-link" id="otherLib">${ico('folder')}Open another library folder</button></div>
      <p class="s-note${noteOk ? ' ok' : ''}" id="haveNote"${note ? '' : ' hidden'}>${esc(note)}</p>`;
    $('#otherLib').onclick = () => haveLibrary(false, $('#otherLib'), { library: true });   // only another LastbookData, on a USB stick or another drive (#266)
    if ($('#libraryUpdate')) $('#libraryUpdate').onclick = () => { choice.pack = c.pack; choice.ai = !!c.model; go('choose') };
    if ($('#upgrade')) $('#upgrade').onclick = () => { choice.pack = bigger[0].id; choice.ai = !!c.model; go('choose') };
    if ($('#mapCh')) $('#mapCh').onclick = () => { choice.pack = c.pack; choice.ai = !!c.model; choice.map = null; go('choose'); const m = $('#mapSel'); if (m) m.focus() };
    if ($('#addAi')) $('#addAi').onclick = () => { choice.pack = c.pack; choice.ai = true; go('choose') };
    if ($('#rmAi')) $('#rmAi').onclick = () => { confirmRemove = true; manageView(); $('#rmNo').focus() };
    if ($('#rmNo')) $('#rmNo').onclick = () => { confirmRemove = false; manageView(); $('#rmAi').focus() };
    if ($('#rmYes')) $('#rmYes').onclick = () => act('remove-ai', 'The local AI was removed.');   // the engine stops the AI first
    if ($('#rmOld')) $('#rmOld').onclick = () => { confirmOld = true; manageView(); $('#oldNo').focus() };
    if ($('#oldNo')) $('#oldNo').onclick = () => { confirmOld = false; manageView(); $('#rmOld').focus() };
    if ($('#oldYes')) $('#oldYes').onclick = () => act('delete-old', 'The old library is being deleted.', { path: old.path });
    if ($('#copyOut')) $('#copyOut').onclick = async () => {   // #114: choose the drive, then say what will be copied before copying
      const r = await call('pick', {}).catch(() => null);
      if (!r || !r.path) { if (!r) { note = 'The picker could not open. Try again.'; manageView() } return }
      copyTo = r; go('copy');
    };
    if ($('#repair')) $('#repair').onclick = async () => {
      const r = await call('start', { repair: true, ai: !!c.model }).catch(e => ({ error: e.message }));
      if (!r || r.error) { note = (r && r.error) || 'Repair could not start.'; manageView(); return }
      repair = { fixed: false, sure: true }; S.job = r; go('job'); poll();
    };
    globalThis.LastbookI18n?.apply(main);
  }
  /* ---- copy for someone else (#114): what goes onto the drive, and what does not */
  let copyTo = null;
  function copyView() {
    const c = cur() || {}, p = packById(c.pack), r = copyTo || {};
    const need = p && p.installed_bytes;
    main.innerHTML = `<h1 data-i18n="setup.copyTitle">Copy for someone else</h1>
      <p class="lead">Copy the ${esc(p ? p.title : 'Lastbook')} library${need ? ` (${size(need)})` : ''} to ${esc(r.disk || home(r.path || ''))}, with a START-HERE.txt that says how to set it up on another computer.</p>
      <div class="s-have"><div class="s-row">${ico('folder', 's-ri')}<span><b>${esc(home(r.path || ''))}</b><small>${r.free_bytes != null ? size(r.free_bytes) + ' free there' : ''}</small></span></div></div>
      <p class="s-note">Not copied: your settings, saved things, chats, notes, address search and the local AI. Only the library’s own files go onto the drive, and each is read back from the drive to make sure it arrived whole.</p>
      <p class="s-two"><button class="btn big" id="copyGo">Copy</button> <button class="btn big plain" id="copyBack">Back</button></p>
      <p class="s-note" id="haveNote"${note ? '' : ' hidden'}>${esc(note)}</p>`;
    $('#copyBack').onclick = () => go('manage');
    $('#copyGo').onclick = async () => {
      $('#copyGo').disabled = true;
      const x = await call('start', { copy_to: r.path }).catch(e => ({ error: e.message }));
      if (!x || x.error) { note = (x && x.error) || 'The copy could not start.'; copyView(); return }
      repair = null; S.job = x; go('job'); poll();
    };
    globalThis.LastbookI18n?.apply(main);
  }
  function copiedView() {
    const r = (S.job && S.job.result) || {};
    main.innerHTML = `<div class="s-done">${ico('ok', 's-big')}<h1>Copied</h1>
      <p class="lead">The drive now holds the library (${r.files || 0} files${r.bytes ? ', ' + size(r.bytes) : ''}, each read back and checked) and ${esc(r.start_here || 'START-HERE.txt')}, which says how to set it up on another computer.</p>
      <p class="s-note"><b>Eject the drive before you unplug it</b>, so the last files are written.</p>
      <button class="btn big" id="back">Back to Library and local AI</button></div>`;
    live.textContent = 'Copied.';
    S.job = null;
    $('#back').onclick = async () => { S = await call('state').catch(() => S); go('manage') };
  }
  async function act(path, done, body) {
    const r = await call(path, body || {}).catch(e => ({ error: e.status === 404 ? 'This Lastbook cannot do that yet.' : e.message }));
    confirmRemove = confirmOld = false;
    noteOk = !(r && r.error);
    if (r && r.error) note = r.error;
    else { note = done; S = await call('state').catch(() => S) }
    manageView();
    const n = $('#haveNote'); if (n) { n.tabIndex = -1; n.focus() }
  }

  /* ---- job */
  const STEPS = { pack: [['downloading', 'Download'], ['verifying', 'Check'], ['unpacking', 'Unpack'], ['activating', 'Finish']],
                  model: [['downloading', 'Download'], ['verifying', 'Check'], ['activating', 'Finish']] };
  STEPS.map = [['downloading', 'Download'], ['unpacking', 'Unpack']];   // the engine's map item: waiting, downloading, unpacking, done
  STEPS.addresses = STEPS.map;
  STEPS.copy = [['copying', 'Copy']];
  const WORD = { waiting: 'Waiting', downloading: 'Downloading', paused: 'Paused', verifying: 'Checking', unpacking: 'Unpacking', activating: 'Finishing', copying: 'Copying', done: 'Done', failed: 'Stopped' };
  const ACTIVE = new Set(['waiting', 'downloading', 'verifying', 'unpacking', 'activating', 'copying']);
  let shapeKey = '', lastAct = null;   // lastAct: the button just pressed, so focus lands on what replaced it

  function errorBox(j) {
    const e = j.error, code = errCode(e) || j.code, c = cur();
    const blockedModel = code === 'network' && (j.items || []).some(it => it.kind === 'model' && it.state === 'failed' && !it.bytes_done);
    const safe = c ? 'Your library is untouched and still works.' : 'Nothing else on this computer was changed.';
    const d = diskFor(j.folder || folder);
    const T = {
      found_mismatch: (() => {   // a file of the person's own that did not match: nothing was downloaded, and their file is left alone
        const f = String((e && e.file) || ''), name = f.split(/[\\/]/).pop() || 'file', at = f.split(/[\\/]/).slice(-2, -1)[0];
        return [`The ${esc(name)}${at ? ' in ' + esc(at) : ''} doesn’t match the published file, so it was not used.`, 'It was left as it is. Download it instead?', 'download'];
      })(),
      no_space: j.copy ? ['The drive is full.', 'What was copied is kept. Free some space on it, then retry.', 'retry'] : [`Not enough room on ${esc(diskName(d))}${e && e.need_bytes ? `: this needs ${size(e.need_bytes)}, and ${size(e.free_bytes)} is free` : ''}.`, 'Free some space, then retry, or go back and choose less.', 'retry'],
      network: blockedModel
        ? ['This network could not reach the local AI download server.', 'What is downloaded is kept. Retry, or choose the published AI model file downloaded another way.', 'retry']
        : ['The internet connection dropped.', 'What is downloaded is kept. Retry when you are online again.', 'retry'],
      server: ['The download server stayed busy.', 'Your internet connection is fine, and what is downloaded is kept. Retry in a while.', 'retry'],
      checksum: ['The download came out damaged twice, so it was not used.', 'Retry to download it once more.', 'retry'],
      unpack: ['Unpacking did not finish.', 'Check there is room on the disk, then retry.', 'retry'],
      activate: ['The new library is ready but could not be switched in.', 'Retry, or close Lastbook and open it again.', 'retry'],
      copy: ['The copy stopped.', esc(errText(e) || 'Copy again to the same place to carry on.'), 'retry'],
      cancelled: j.copy ? ['The copy was cancelled.', 'What was copied is still on the drive: copy again to the same place to carry on.', 'back'] : ['The download was cancelled.', 'Start again when you are ready.', 'back'],
    }[code] || [esc(errText(e) || 'Something went wrong.'), 'Retry, or go back and choose again.', 'retry'];
    return `<div class="s-err" role="alert">${ico('warn')}<div><b>${T[0]}</b><p>${T[1]}${code === 'found_mismatch' && !c ? '' : ' ' + safe}</p>
      <p class="s-acts">${T[2] === 'retry' ? `<button class="btn" data-act="retry">${ico('retry')}Retry</button>` : T[2] === 'download' ? `<button class="btn" data-act="retry">${ico('down')}Download it</button>` : ''}${blockedModel ? '<button class="btn plain" data-act="model-file">Choose AI model file</button>' : ''}<button class="btn ${T[2] === 'back' ? '' : 'plain'}" data-act="back">Choose again</button></p>${blockedModel ? '<p class="s-note" id="haveNote" role="status" hidden></p>' : ''}</div></div>`;
  }
  function itemHTML(it, j) {
    const FAILED_AT = { checksum: 'verifying', found_mismatch: 'verifying', unpack: 'unpacking', activate: 'activating' };
    const steps = STEPS[it.kind] || STEPS.pack;
    const st = it.state === 'paused' && noDownload(it) ? (it.paused_from && it.paused_from !== 'downloading' ? it.paused_from : 'verifying')
      : it.state === 'paused' || it.state === 'waiting' ? 'downloading' : it.state === 'failed' ? FAILED_AT[errCode(it.error) || errCode(j.error)] || 'downloading' : it.state;
    const at = it.state === 'done' ? steps.length : (it.state === 'waiting' || it.state === 'paused') && !it.bytes_done && (!noDownload(it) || it.state === 'waiting') ? -1 : Math.max(0, steps.findIndex(s => s[0] === st));
    const busy = it.state === 'activating' || (['verifying', 'unpacking'].includes(it.state) && !it.bytes_total);   // the check and the unpacking count their bytes
    return `<div class="s-item${it.state === 'failed' ? ' bad' : ''}${it.state === 'done' ? ' ok' : ''}" data-item="${esc(it.id)}" data-kind="${esc(it.kind)}">
      <div class="s-item-h">${ico(it.kind === 'model' ? 'ai' : it.kind === 'map' ? 'map' : it.kind === 'copy' ? 'folder' : 'book', 's-ri')}<b>${esc(itemTitle(it))}</b><span class="s-state" data-f="word">${it.state === 'done' ? ico('ok') : ''}${Object.hasOwn(WORD, it.state) ? WORD[it.state] : ''}</span></div>
      <div class="s-bar new${busy && j.state !== 'paused' ? ' busy' : ''}" role="progressbar" aria-label="${esc(it.title)}" aria-valuemin="0" aria-valuemax="100" data-f="bar"><i></i></div>
      <p class="s-line" data-f="line"></p>
      <ol class="s-steps" aria-label="Steps">${steps.map((s, i) => `<li class="${i < at ? 'done' : i === at && it.state !== 'failed' ? 'now' : i === at ? 'stop' : ''}">${s[1]}</li>`).join('')}</ol>
    </div>`;
  }
  const itemTitle = it => it.kind === 'model' ? 'Local AI' : it.kind === 'map' ? `${(mapById(it.id) || it).title || it.id} map` : it.kind === 'addresses' ? it.title : it.id === 'library' || it.id === 'repair' || /library/i.test(it.title) ? it.title : it.title + ' library';
  /* an item that needs nothing from the internet: the person's own file, or one stopped after its download was complete.
     source and paused_from come from the engine (docs/SETUP-API.md); without them, a complete download still counts */
  const noDownload = it => it.source === 'found' || (!!it.paused_from && it.paused_from !== 'downloading') || (it.bytes_total > 0 && it.bytes_done >= it.bytes_total);
  const STOPPED = { verifying: 'Checking stopped', unpacking: 'Unpacking stopped', activating: 'Finishing stopped' };
  const above = it => { const items = (S.job && S.job.items) || [], i = items.findIndex(x => x.id === it.id && x.kind === it.kind); return items.slice(0, Math.max(i, 0)) };
  const behind = it => above(it).some(x => x.state !== 'done' && !noDownload(x));   // a download waits for the downloads above it
  const afterAbove = it => above(it).some(x => x.state !== 'done');                // a file already here waits for everything above it
  const checkOnly = it => noDownload(it) || (!!(S.job && S.job.repair) && it.kind === 'pack' && !(repair && repair.fixed));   // a repair checks the open library before it fetches anything
  const fetching = j => ['downloading', 'unpacking'].includes(j.state) || j.items.some(i => ['downloading', 'unpacking'].includes(i.state) || ['downloading', 'unpacking'].includes(i.paused_from));
  /* a page opened again during a repair learns it from the engine's job (repair: true). It is sure of what the done screen says
     only if nothing could have been fetched before it looked. fixed stays true once a download is seen */
  function syncRepair(j) {
    if (!j) return;
    if (!repair && j.repair) { const f = fetching(j); repair = { fixed: f, sure: f || j.items.every(i => i.state === 'waiting' || i.state === 'verifying') } }
    else if (repair && fetching(j)) repair.fixed = true;
  }
  function fillItem(el, it) {
    const pct = it.bytes_total ? Math.min(100, it.bytes_done / it.bytes_total * 100) : it.state === 'done' ? 100 : 0;
    const bar = el.querySelector('[data-f=bar]'), line = el.querySelector('[data-f=line]');
    const showPct = !bar.classList.contains('busy');
    bar.firstChild.style.width = (showPct ? pct : 100) + '%';
    if (showPct) bar.setAttribute('aria-valuenow', Math.round(pct)); else bar.removeAttribute('aria-valuenow');
    let t = '';
    if (it.state === 'done') t = it.bytes_total ? size(it.bytes_total) : '';
    else if (it.state === 'downloading') t = [`${size(it.bytes_done)} of ${size(it.bytes_total)}`, it.retry_in_s ? retryIn(it.retry_in_s) : rate(it.rate_bps), eta(it.eta_s)].filter(Boolean).join(' · ');
    else if (it.state === 'paused' && noDownload(it)) t = `${STOPPED[it.paused_from] || 'Stopped'}${it.paused_from === 'unpacking' && it.bytes_done && it.bytes_total ? ` at ${size(it.bytes_done)} of ${size(it.bytes_total)}` : ''}. Nothing to download.`;
    else if (it.state === 'waiting' && !it.bytes_done && checkOnly(it)) t = it.bytes_total ? `Already on this computer: ${size(it.bytes_total)} to check${afterAbove(it) ? ', after the one above' : ''}` : '';
    else if ((it.state === 'waiting' || it.state === 'paused') && !it.bytes_done) t = it.bytes_total ? `${size(it.bytes_total)} to download${behind(it) ? ', after the one above' : ''}` : '';
 else if (it.state === 'paused' || it.state === 'waiting' || it.state === 'failed') t = it.bytes_total && it.bytes_done ? `${size(it.bytes_done)} of ${size(it.bytes_total)}` : '';
    else if (it.kind === 'copy' && (it.state === 'copying' || it.state === 'paused' || it.state === 'failed')) t = [`${size(it.bytes_done)} of ${size(it.bytes_total)} copied and checked`, it.state === 'copying' ? rate(it.rate_bps) : '', it.state === 'copying' ? eta(it.eta_s) : ''].filter(Boolean).join(' · ');
    else if (it.state === 'verifying') {
      /* a resumed download re-reads the part it already has while the job stays 'downloading'; a check of a whole item (a repair,
         or a file already here) sets the job to 'verifying' too. Only that whole check has a true time left */
      const resumed = !!(S.job && S.job.state === 'downloading'), whole = !resumed && (it.source === 'found' || !!(S.job && S.job.repair));
      t = !it.bytes_total ? 'Making sure every byte is right'
        : resumed ? `Checking what is already downloaded: ${size(it.bytes_done)} so far`
        : [`Checking: ${size(Math.min(it.bytes_done, it.bytes_total))} of ${size(it.bytes_total)}`, whole ? eta(it.eta_s) : ''].filter(Boolean).join(' · ');
    }
    else if (it.state === 'unpacking') t = it.bytes_total ? `Unpacking: ${size(it.bytes_done)} of ${size(it.bytes_total)}${it.eta_s != null ? ' · ' + eta(it.eta_s) : ''}` : 'Opening the files into the library folder';
    else if (it.state === 'activating') t = it.kind === 'map' ? 'Switching to the new map' : 'Switching to the new library';
    line.textContent = t;
  }
  function jobView(j) {
    if (!j) { go(cur() ? 'manage' : 'choose'); return }
    if (j.state === 'done') { go('done'); return }
    syncRepair(j);
    const key = j.state + '|' + errCode(j.error) + '|' + confirmCancel + '|' + j.items.map(i => i.kind + ':' + i.id + ':' + i.state).join(',');
    const head = { paused: 'Paused', failed: errCode(j.error) === 'cancelled' ? 'Cancelled' : 'Stopped' }[j.state] || (j.copy ? 'Copying to the drive' : repair && !repair.fixed ? 'Checking the library' : repair ? 'Repairing' : 'Installing');
    if (key !== shapeKey) {
      const had = lastAct || (document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.act : null);
      lastAct = null;
      const first = !shapeKey;
      shapeKey = key;
      const lead = jobLead(j);
      main.innerHTML = `<h1>${head}</h1>${lead ? `<p class="lead">${lead}</p>` : ''}
        ${j.state === 'failed' ? errorBox(j) : ''}
        <div class="s-items">${j.items.map(it => itemHTML(it, j)).join('')}</div>
        ${j.state === 'failed' ? '' : `<div class="s-go left">${confirmCancel
          ? `<span class="s-confirm"><span>${j.copy ? 'Stop copying? What is copied stays on the drive.' : 'Stop and throw away the download?'}</span><button class="btn danger" data-act="cancel-yes">Stop</button><button class="btn plain" data-act="cancel-no">Keep going</button></span>`
          : jobControls(j)}</div>`}`;
      main.querySelectorAll('[data-act]').forEach(b => b.onclick = () => jobAct(b.dataset.act, b));
      const again = had && main.querySelector(`[data-act="${had}"]`) || (had && main.querySelector('[data-act]'));
      if (!languageHasFocus()) {
        if (again) again.focus();
        else if (first) { const h = main.querySelector('h1'); h.tabIndex = -1; h.focus({ preventScroll: true }) }
      }
      const s = j.state === 'failed' ? '' : head + (j.items.find(i => ACTIVE.has(i.state)) ? ': ' + WORD[j.items.find(i => ACTIVE.has(i.state)).state] + ' ' + j.items.find(i => ACTIVE.has(i.state)).title : '');
      if (s && live.textContent !== s) live.textContent = s;
    }
    const fresh = main.querySelectorAll('.s-bar.new');
    j.items.forEach(it => { const el = main.querySelector(`[data-item="${CSS.escape(it.id)}"][data-kind="${CSS.escape(it.kind)}"]`); if (el) fillItem(el, it) });
    if (fresh.length) { void main.offsetWidth; fresh.forEach(b => b.classList.remove('new')) }   // a new screen shows the bar where it is, without growing from nothing
  }
  /* The line under the heading. A copy has its own words first: it downloads nothing, and a copy paused at 100% (its last file
     read back, not yet finished) is not "stopped when Lastbook closed" (#204 review). */
  function jobLead(j) {
    if (j.state === 'failed') return '';
    if (j.copy) return j.state === 'paused' ? 'What is copied is kept. Resume when you are ready. If Lastbook closes, copy again to the same place to carry on.'
      : 'You can keep using this computer. If Lastbook closes, copy again to the same place to carry on.';
    const quiet = j.state === 'paused' && j.items.filter(i => i.state === 'paused').every(noDownload);
    return quiet ? 'Stopped when Lastbook closed. Resume to finish; nothing needs downloading.'
      : j.state === 'paused' ? 'What is downloaded is kept. Resume when you are ready, even after closing Lastbook.'
      : 'You can keep using this computer. Closing Lastbook pauses it.';
  }
  /* Resume when paused; Pause while it downloads, waits, or copies (a copy pauses between chunks, as a download does) */
  function jobControls(j) {
    return `${j.state === 'paused' ? `<button class="btn" data-act="resume">${ico('play')}Resume</button>` : (j.state === 'downloading' || j.state === 'copying' || (j.state === 'waiting' && !j.repair)) ? `<button class="btn plain" data-act="pause">${ico('pause')}Pause</button>` : ''}
             <button class="btn plain" data-act="cancel">${ico('x')}Cancel</button>`;
  }
  async function jobAct(a, b) {
    if (a === 'model-file') { await haveLibrary(true, b); return }
    if (a === 'back') { S = await call('state').catch(() => S); S.job = null; shortfall = null; go('choose'); return }   // fresh: found[] may now mark a file as not matching
    if (a === 'cancel') { confirmCancel = true; jobView(S.job); main.querySelector('[data-act="cancel-no"]').focus(); return }
    if (a === 'cancel-no') { confirmCancel = false; jobView(S.job); return }
    if (a === 'cancel-yes') { confirmCancel = false; a = 'cancel' }
    b.disabled = true; lastAct = a;
    try { const j = await call(a, {}); if (j && j.items) S.job = j } catch { }
    if (a === 'cancel') { const was = S.job && S.job.copy; S = await call('state').catch(() => S); S.job = null; go(cur() ? 'manage' : 'choose'); live.textContent = was ? 'The copy was stopped. What was copied is on the drive.' : 'The download was cancelled.'; return }
    jobView(S.job);
    poll();
  }
  function poll() {
    clearTimeout(pollT);
    if (!S.job || !ACTIVE.has(S.job.state)) return;
    pollT = setTimeout(async () => {
      try { const j = await call('job'); if (j) S.job = j } catch { pollT = setTimeout(poll, 3000); return }
      if (view !== 'job') return;
      if (S.job && S.job.state === 'done') { go('done'); return }
      jobView(S.job);
      poll();
    }, 1000);
  }

  /* ---- done */
  function doneView() {
    if (S.job && S.job.copy) return copiedView();
    syncRepair(S.job);
    const j = S.job || { items: [] }, fixed = repair && repair.fixed, checked = repair && !fixed, unsure = checked && !repair.sure;   // unsure: opened again late in a repair
    const got = j.items.filter(i => i.id !== 'repair' && i.id !== 'library').map(i => esc(itemTitle(i))).join(', ').replace(/, ([^,]*)$/, ' and $1');
    main.innerHTML = `<div class="s-done">${ico('ok', 's-big')}<h1>${unsure ? 'Checked' : checked ? 'All good' : fixed ? 'Repaired' : 'Ready'}</h1>
      <p class="lead">${unsure ? 'The library was checked and is complete. Anything that was damaged was downloaded again.' : checked ? 'The library was checked and is complete.' : fixed ? 'A damaged part was downloaded again. The damaged copy is kept aside; you can delete it in Library and local AI.' : got ? `Installed: ${got}.` : j.items.some(i => i.id === 'library') ? 'The library you chose is ready to open.' : 'The library is installed.'}</p>
      <button class="btn big" id="open">Open the library</button><p class="s-note" id="openNote" hidden></p></div>`;
    live.textContent = checked ? 'The library was checked.' : fixed ? 'Repaired. Ready to open.' : 'Installed. Ready to open.';
    $('#open').onclick = async () => {
      const b = $('#open'); b.disabled = true; b.textContent = 'Opening your library…';
      const r = await call('finish', {}).catch(e => ({ error: e.message }));   // on {ok} the app relaunches itself into the library
      if (!r || r.error) { b.disabled = false; b.textContent = 'Open the library'; const n = $('#openNote'); n.hidden = false; n.textContent = (r && r.error) || 'The library did not open. Try again.' }
      else live.textContent = 'Opening your library…';
    };
  }

  /* keyboard: Escape closes a question that is open */
  addEventListener('keydown', e => {
    if (e.key !== 'Escape' || languageHasFocus()) return;
    if (confirmCancel) { confirmCancel = false; jobView(S.job); const b = main.querySelector('[data-act="cancel"]'); if (b) b.focus() }
    else if (confirmRemove || confirmOld) { const f = confirmRemove ? '#rmAi' : '#rmOld'; confirmRemove = confirmOld = false; manageView(); $(f).focus() }
  });
  /* the window comes back to the front: the job may have moved on, or a restart paused it */
  addEventListener('focus', () => { if (view === 'job') call('job').then(j => { if (j) { S.job = j; jobView(j); poll() } }).catch(() => { }) });

  load().then(() => { if (view === 'job') poll() });
})();
