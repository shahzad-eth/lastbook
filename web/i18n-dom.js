/* Explicit, opt-in bindings for first-party UI. Does not observe or rewrite
   arbitrary text or library content. Call again after rendering new UI. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.applyI18n = factory();
})(globalThis, function () {
  "use strict";

  const bindings = [
    ["data-i18n", null],
    ["data-i18n-aria-label", "aria-label"],
    ["data-i18n-placeholder", "placeholder"],
    ["data-i18n-title", "title"],
    ["data-i18n-alt", "alt"],
  ];
  const selector = bindings.map(([marker]) => "[" + marker + "]").join(",");
  // No strong registry of documents, detached subtrees, or old screens. The
  // last explicit provider belongs to each element/key and translator pair.
  const providers = new WeakMap();

  function applyI18n(root, i18n, paramsFor) {
    if (paramsFor !== undefined && paramsFor !== null && typeof paramsFor !== "function") {
      throw new TypeError("Expected a parameter provider function or null");
    }
    if (!providers.has(i18n)) providers.set(i18n, new WeakMap());
    const stored = providers.get(i18n);
    const elements = [...root.querySelectorAll(selector)];
    if (root.nodeType === 1 && root.matches(selector)) elements.unshift(root);

    for (const element of elements) {
      // One broken binding or provider must not leave the rest of the page
      // half translated. The element keeps whatever it already shows.
      try { bind(element, i18n, paramsFor, stored); } catch { /* keep the current text */ }
    }
  }

  function bind(element, i18n, paramsFor, stored) {
    const previous = stored.get(element);
    if (previous) {
      const active = new Set(bindings.map(([marker]) => element.getAttribute(marker)));
      for (const key of previous.keys()) if (!active.has(key)) previous.delete(key);
    }
    let language;
    for (const [marker, target] of bindings) {
      const key = element.getAttribute(marker);
      if (!key) continue;
      // Never erase SVGs, nested controls or other child markup.
      if (target === null && element.childElementCount !== 0) continue;
      if (paramsFor !== undefined) {
        if (!stored.has(element)) stored.set(element, new Map());
        if (paramsFor === null) stored.get(element).delete(key);
        else stored.get(element).set(key, paramsFor);
      }
      const provider = stored.get(element)?.get(key);
      let result;
      try { result = i18n.resolve(key, provider?.(element, key)); } catch { continue; }  // this binding keeps its text
      if (!result) continue;  // Original English remains readable.
      if (target === null) {
        if (element.textContent !== result.text) element.textContent = result.text;
      } else if (element.getAttribute(target) !== result.text) element.setAttribute(target, result.text);
      if (!language) language = result.locale;
    }
    // An attribute on a container must not change its unmarked descendants'
    // language/direction unless the container explicitly opts in (e.g. an
    // icon-only button). In mixed-language controls use marked leaves.
    if (language && (element.childElementCount === 0 || element.getAttribute("data-i18n-lang") !== null)) {
      const dir = i18n.direction(language);
      if (element.getAttribute("lang") !== language) element.setAttribute("lang", language);
      if (element.getAttribute("dir") !== dir) element.setAttribute("dir", dir);
    }
  }

  return applyI18n;
});
