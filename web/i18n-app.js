/* Language policy shared by Setup, Settings and the library. */
(() => {
  'use strict';
  const desktop = window.LB_DESKTOP_LANGUAGE === true;
  // The iPad also uses the lastbook: scheme, with a different router and copy.
  if (location.protocol === 'lastbook:' && !desktop) return;
  if (typeof window.createI18n !== 'function' || typeof window.applyI18n !== 'function' || !window.lastbookI18nEnglish) return;

  const english = window.lastbookI18nEnglish;
  const regional = window.lastbookI18nLocales?.['es-419'];
  const fallbacks = { 'es-AR': ['es-419'], 'es-CL': ['es-419'], 'es-UY': ['es-419'] };
  let engine;
  try { engine = createI18n({ catalogs: { en: english } }); } catch { return; }
  if (regional && Object.keys(regional).length) {
    try { engine = createI18n({ catalogs: { en: english, 'es-419': regional }, fallbacks }); } catch { /* Keep English. */ }
  }

  const form = desktop && document.getElementById('languageSettings');
  const select = form && form.querySelector('select');
  const button = form && form.querySelector('button');
  const status = form && document.getElementById('languageStatus');
  let selection = 'en';
  let phase = 'loading';
  let readGeneration = 0;

  const apply = (scope = document, paramsFor) => applyI18n(scope, engine, paramsFor);
  window.LastbookI18n = Object.freeze({ apply });

  // The file behind the bridge is the truth. Its last answer is also kept in this window's own storage, only so the
  // next page can start in the right language instead of flashing English until the bridge replies.
  const HINT = 'lastbook.ui-language';
  function readHint() {
    try { const hint = localStorage.getItem(HINT); return ['en', 'es-419'].includes(hint) ? hint : null; } catch { return null; }
  }
  function writeHint(saved) {
    try { saved ? localStorage.setItem(HINT, saved) : localStorage.removeItem(HINT); } catch { /* storage is optional */ }
  }

  function activate(saved) {
    selection = saved || 'en';
    engine.usePreferredLocales(selection);
    apply();
    document.dispatchEvent(new Event('lastbook:languagechange'));
  }

  function announce(key) {
    if (!status) return;
    if (key) {
      status.setAttribute('data-i18n', key);
      apply(status);
    } else {
      status.removeAttribute('data-i18n');
      status.textContent = '';
    }
  }

  // A hung bridge must not keep the selector hidden or the button busy for ever.
  const READ_TIMEOUT = 8000, WRITE_TIMEOUT = 15000;

  async function preference(language) {
    const options = { cache: 'no-store' };
    if (language !== undefined) {
      options.method = 'POST';
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify({ language });
    }
    const abort = new AbortController();
    options.signal = abort.signal;
    const timer = setTimeout(() => abort.abort(), language === undefined ? READ_TIMEOUT : WRITE_TIMEOUT);
    let saved;
    try {
      const response = await fetch('/api/ui-language', options);
      if (!response.ok) throw new Error('Could not access the desktop language preference');
      saved = (await response.json()).language;
    } finally { clearTimeout(timer); }
    if (![null, 'en', 'es-419'].includes(saved) || (language !== undefined && language !== saved)) {
      throw new Error('Unexpected desktop language preference');
    }
    return saved;
  }

  async function load() {
    const generation = ++readGeneration;
    let message;
    try {
      const saved = await preference();
      if (generation !== readGeneration) return;
      writeHint(saved);
      activate(saved);
      if (saved && saved !== engine.catalogLocale) message = 'language.unavailable';
    } catch { message = 'language.loadFailed'; }
    if (generation !== readGeneration) return;
    if (form) {
      select.value = selection;
      phase = 'idle';
      form.hidden = false;
      announce(message);
    }
  }

  if (form) {
    select.querySelector('[value="es-419"]').disabled = !engine.supportedLocales.includes('es-419');
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const next = select.value;
      // Settings load once before accepting edits. Keep only one write in
      // flight per document so its replies cannot arrive out of order.
      if (phase !== 'idle' || !engine.supportedLocales.includes(next)) return;
      phase = 'saving';
      button.setAttribute('aria-disabled', 'true');
      announce('language.saving');
      try {
        const saved = await preference(next);
        writeHint(saved);
        activate(saved);
        select.value = saved;
        announce('language.saved');
      } catch {
        select.value = selection;
        announce('language.saveFailed');
      } finally {
        button.removeAttribute('aria-disabled');
        phase = 'idle';
      }
    });
  }

  activate(desktop ? readHint() : null);
  if (desktop) {
    load();
    // Returning from Settings can restore the old library document and its
    // in-memory state. Apply the preference without rerunning the route.
    if (!form) addEventListener('pageshow', event => { if (event.persisted) load() });
  }
})();
