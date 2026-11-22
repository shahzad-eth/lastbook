const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const { runInNewContext } = require("node:vm");
const createI18n = require("../../web/i18n-core.js");
const applyI18n = require("../../web/i18n-dom.js");

test("the shared iPad scheme without the desktop marker skips desktop localization", () => {
  const window = {
    get createI18n() { assert.fail("desktop localization started"); },
  };
  const script = readFileSync(resolve(__dirname, "../../web/i18n-app.js"), "utf8");
  runInNewContext(script, { window, location: { protocol: "lastbook:" } });
  assert.equal(window.LastbookI18n, undefined);
});

const catalogs = {
  en: {
    greeting: "Hello, {name}",
    files: { "=0": "No files", one: "{count} file", other: "{count} files" },
    fallback: "English only",
    caption: "Picture {position}",
  },
  "es-419": {
    greeting: "Hola, {name}",
    files: { "=0": "No hay archivos", one: "{count} archivo", other: "{count} archivos" },
    caption: "Imagen {position}",
  },
  "es-AR": { greeting: "Buenas, {name}" },
};

const inheritance = { "es-UY": ["es-419"], "es-AR": ["es-419"], "es-CL": ["es-419"] };

function translator(locale) {
  return createI18n({ catalogs, locale, fallbacks: inheritance });
}

test("regional Spanish routes to es-419, with exact catalogs and English fallback", () => {
  for (const locale of ["ES-uy", "es-CL", "es-UY-u-nu-latn", "es-419"]) {
    assert.deepEqual(translator(locale).resolve("greeting", { name: "Ana" }),
      { text: "Hola, Ana", locale: "es-419" });
  }
  const i18n = translator("es-AR");
  assert.equal(i18n.t("greeting", { name: "Ana" }), "Buenas, Ana");
  assert.equal(i18n.t("files", { count: 2 }), "2 archivos");
  assert.equal(i18n.t("fallback"), "English only");
  for (const locale of ["fr-CA", "es-ES", "es", "es-MX", "es-ES-u-nu-arab"]) {
    i18n.setLocale(locale);
    assert.equal(i18n.t("greeting", { name: "Ana" }), "Hello, Ana");
    assert.equal(i18n.catalogLocale, "en");
  }
  i18n.setLocale("es-UY-u-nu-arab");
  assert.equal(i18n.catalogLocale, "es-419");
  assert.equal(i18n.locale, "es-UY-u-nu-arab");
  assert.equal(i18n.t("constructor"), undefined);
});

test("plural selection uses exact counts and the grammar of the matched catalog", () => {
  for (const [locale, expected] of [
    ["en", ["No files", "1 file", "2 files"]],
    ["es-UY", ["No hay archivos", "1 archivo", "2 archivos"]],
  ]) {
    const i18n = translator(locale);
    assert.deepEqual([0, 1, 2].map(count => i18n.t("files", { count })), expected);
    // No usable count: the "other" form renders and nothing throws.
    assert.equal(i18n.t("files", { count: "2" }), expected[2].replace(/^\d+/, "2"));
    assert.equal(i18n.t("files", { count: Infinity }), expected[2].replace(/^\d+/, "Infinity"));
  }
  const i18n = createI18n({
    locale: "ja", fallbackLocale: "en",
    catalogs: { en: catalogs.en, ja: { files: catalogs.en.files } },
  });
  assert.equal(i18n.t("files", { count: 1 }), "1 files");
});

test("interpolation performs one plain-text pass over own primitive parameters", () => {
  const i18n = translator("en");
  const input = '<img src=x onerror="alert(1)">{name}$&';
  assert.equal(i18n.t("greeting", { name: input }), "Hello, " + input);
  for (const params of [
    Object.create({ name: "Inherited" }),
    { get name() { assert.fail("parameter getter ran"); } },
    { name: { toString() { assert.fail("parameter was coerced"); } } },
  ]) assert.equal(i18n.t("greeting", params), "Hello, {name}");
});

test("browser preference negotiation ignores unsupported earlier languages", () => {
  const i18n = translator("en");
  assert.equal(i18n.chooseLocale(["fr-CA", "es-UY"]), "es-UY");
  assert.equal(i18n.chooseLocale(["es-ES", "es-CL"]), "es-CL");
  assert.equal(i18n.chooseLocale(["es-ES", "es"]), "en");
  assert.equal(i18n.usePreferredLocales(["fr-CA", "es-CL"]), "es-CL");
  assert.equal(i18n.t("greeting", { name: "Ana" }), "Hola, Ana");
  assert.equal(i18n.chooseLocale(["en-US", "es-UY"]), "en-US");
  assert.equal(i18n.chooseLocale(["malformed_tag", "fr"]), "en");
  assert.equal(i18n.chooseLocale([]), "en");
  assert.equal(i18n.locale, "es-CL"); // chooseLocale is non-mutating
  assert.equal(i18n.usePreferredLocales(["en-US", "es-UY"]), "en-US");
  assert.equal(i18n.t("greeting", { name: "Ana" }), "Hello, Ana");
  assert.throws(() => i18n.setLocale("malformed_tag"), RangeError);
  assert.equal(i18n.locale, "en-US"); // invalid selection is atomic
  assert.deepEqual(i18n.supportedLocales, ["en", "es-419", "es-AR"]);
});

test("plural grammar and count formatting agree for fractional quantities", () => {
  assert.equal(translator("en").t("files", { count: 1.0004 }), "1 file");
  assert.equal(translator("en").t("files", { count: 1.001 }), "1.001 files");
  assert.equal(translator("es-UY").t("files", { count: 1.001 }),
    new Intl.NumberFormat("es-UY").format(1.001) + " archivos");
  for (const count of [NaN, Infinity, "2", undefined]) {
    assert.doesNotThrow(() => translator("en").t("files", { count }));
  }
});

test("a plural message without a numeric count falls back to its other form", () => {
  const en = translator("en");
  assert.equal(en.t("files"), "{count} files");
  assert.equal(en.t("files", {}), "{count} files");
  assert.equal(en.t("files", null), "{count} files");
  assert.equal(en.resolve("files", { count: undefined }).locale, "en");
  assert.equal(translator("es-UY").t("files"), "{count} archivos");
  assert.equal(en.t("files", { count: "many" }), "many files");
  assert.equal(en.t("files", { count: 1 }), "1 file");
});

test("explicit routes to the default never hide later supported preferences", () => {
  const i18n = createI18n({ catalogs, fallbacks: { fr: ["en"], ...inheritance } });
  assert.equal(i18n.chooseLocale(["fr", "es-AR"]), "es-AR");
  assert.equal(i18n.chooseLocale(["fr-CA", "es-UY"]), "es-UY");
  assert.equal(i18n.chooseLocale(["es-ES", "es-CL"]), "es-CL");
  assert.equal(i18n.chooseLocale(["es-ES", "es"]), "en");
  assert.equal(i18n.chooseLocale(["en-US", "es-AR"]), "en-US");
  assert.equal(i18n.chooseLocale(["en", "es-AR"]), "en");
  assert.equal(i18n.chooseLocale(["fr"]), "en");
});

test("plural grammar follows the message while count respects selected numbering", () => {
  const spanish = translator("es-UY-u-nu-arab");
  assert.equal(spanish.t("files", { count: 1.0004 }),
    new Intl.NumberFormat(spanish.locale).format(1.0004) + " archivo");
  assert.equal(spanish.t("files", { count: 2.001 }),
    new Intl.NumberFormat(spanish.locale).format(2.001) + " archivos");
  const en = { quantity: { one: "one {count}", other: "other {count}" } };
  const i18n = createI18n({ locale: "fa-IR-u-nu-latn", catalogs: { en, fa: en } });
  assert.equal(i18n.t("quantity", { count: 0 }), "one \u20680\u2069"); // Persian zero is one
  assert.equal(i18n.t("quantity", { count: 1.0004 }), "one \u20681\u2069");
  assert.equal(i18n.t("quantity", { count: 2.125 }), "other \u20682.125\u2069");
  i18n.setLocale("ja-JP-u-nu-fullwide"); // English fallback still uses English grammar
  assert.equal(i18n.t("quantity", { count: 1 }), "one １");
});

test("exact plural integers reject unsafe precision and cover the safe boundary", () => {
  for (const form of ["=1000000000000000000000", "=9007199254740992", "=9007199254740993", "=1e21", "=-1", "=1.5", "=01"]) {
    assert.throws(() => createI18n({ catalogs: { en: { n: { [form]: "exact", other: "other" } } } }), TypeError);
  }
  const i18n = createI18n({ catalogs: { en: { n: {
    "=9007199254740991": "exact", "=0": "zero", other: "other {count}",
  } } } });
  assert.equal(i18n.t("n", { count: Number.MAX_SAFE_INTEGER }), "exact");
  assert.equal(i18n.t("n", { count: -0 }), "zero");
  assert.match(i18n.t("n", { count: 1e21 }), /^other /);
});

test("Arabic plural categories, script direction and bidi isolation", () => {
  const forms = Object.fromEntries(["zero", "one", "two", "few", "many", "other"].map(form => [form, form + " {count}"]));
  const i18n = createI18n({ locale: "ar", catalogs: { en: { greeting: "Hello {name}", n: forms, fallback: "English" }, ar: { greeting: "مرحبا {name}", n: forms } } });
  for (const [count, form] of [[0, "zero"], [1, "one"], [2, "two"], [3, "few"], [11, "many"], [100, "other"], [1.5, "other"]]) {
    assert.equal(i18n.t("n", { count }), form + " \u2068" + new Intl.NumberFormat("ar").format(count) + "\u2069");
  }
  assert.equal(i18n.t("greeting", { name: "Ana / file.txt" }), "مرحبا \u2068Ana / file.txt\u2069");
  for (const tag of ["ar", "fa", "he", "az-Arab", "en-Arab"]) assert.equal(i18n.direction(tag), "rtl");
  for (const tag of ["en", "es-UY", "az-Latn", "ar-Latn"]) assert.equal(i18n.direction(tag), "ltr");
  const arabic = new FakeElement({ "data-i18n": "greeting" });
  const english = new FakeElement({ "data-i18n": "fallback", dir: "rtl" });
  const untouched = new FakeElement({}, "Unmarked English");
  const container = new FakeElement({ "data-i18n-aria-label": "greeting" }, "", [untouched]);
  applyI18n(new FakeElement({}, "", [arabic, english, container]), i18n, () => ({ name: "Ana" }));
  assert.equal(arabic.getAttribute("dir"), "rtl");
  assert.equal(english.getAttribute("dir"), "ltr");
  assert.equal(english.getAttribute("lang"), "en");
  assert.equal(container.getAttribute("dir"), null);
  assert.equal(container.getAttribute("lang"), null);
  assert.equal(untouched.textContent, "Unmarked English");
});

test("catalogs have explicit contracts and reject accessors or unexpected shapes", () => {
  const bad = [
    { en: { hello: "Hello, {name}" }, es: { hello: "Hola, {persona}" } },
    { en: { hello: "Hello" }, es: { surprise: "Sorpresa" } },
    { en: { hello: "   " } },
    { en: { n: { "=0": "Nothing", other: "{count} items" } }, es: { n: { other: "{count} cosas" } } },
    { en: { hello: "{incomplete" } },
    { en: { hello: {} } },
    { en: { hello: { one: "One" } } },
    { en: { hello: { other: "{count} file", one: "{count} {x} file" } } },
    { en: { hello: { other: "{count} file", invalid: "{count} files" } } },
    { en: { get hello() { assert.fail("catalog getter executed"); } } },
    { en: { hello: ["A", "B"] } },
    { en: { hello: "Hi" }, EN: { hello: "Hello" } },
  ];
  for (const catalogs of bad) {
    assert.throws(() => createI18n({ catalogs }), TypeError);
  }
  assert.throws(() => createI18n({ catalogs: { fr: { hi: "Bonjour" } } }), /Missing fallback catalog/);
  assert.throws(() => createI18n({ catalogs: { en: {} } }), /Missing fallback catalog/);
  assert.throws(() => createI18n({
    catalogs: { en: { hi: "Hi" } }, fallbacks: { fr: "en" },
  }), TypeError);
  const original = { en: { hello: "Hi" } };
  const i18n = createI18n({ catalogs: original });
  original.en.hello = "Changed later";
  assert.equal(i18n.t("hello"), "Hi");
});

test("number and date formatting use the selected locale", () => {
  const i18n = translator("es-UY");
  assert.equal(i18n.number(1234.5), new Intl.NumberFormat("es-UY").format(1234.5));
  const date = new Date("2024-01-15T12:00:00.000Z");
  const options = { timeZone: "UTC", dateStyle: "short" };
  assert.equal(i18n.date(date, options), new Intl.DateTimeFormat("es-UY", options).format(date));
});

class FakeElement {
  constructor(attrs = {}, content = "", children = []) {
    this.attrs = { ...attrs };
    this.textContent = content;
    this.children = children;
    this.nodeType = 1;
  }
  get childElementCount() { return this.children.length; }
  getAttribute(name) { return this.attrs[name] ?? null; }
  setAttribute(name, value) { this.attrs[name] = value; }
  matches(selector) {
    return selector.split(",").some(part => this.getAttribute(part.slice(1, -1)) !== null);
  }
  querySelectorAll(selector) {
    const found = [];
    function visit(parent) {
      for (const child of parent.children) {
        if (child.matches(selector)) found.push(child);
        visit(child);
      }
    }
    visit(this);
    return found;
  }
}

test("DOM adapter updates only opted-in leaf text and safe attributes", () => {
  const leaf = new FakeElement({ "data-i18n": "greeting" }, "Hello, Ana");
  const image = new FakeElement({ "data-i18n-alt": "caption" });
  const search = new FakeElement({
    "data-i18n-placeholder": "greeting", "data-i18n-title": "fallback",
  });
  const icon = new FakeElement();
  const parent = new FakeElement({
    "data-i18n": "greeting", "data-i18n-aria-label": "greeting",
  }, "Untouched", [icon]);
  const untouched = new FakeElement({}, "Library content");
  const root = new FakeElement({}, "", [leaf, image, search, parent, untouched]);
  const paramsFor = (element, key) => key === "greeting" ? { name: "Ana" } : { position: 4 };
  const i18n = translator("es-UY");
  applyI18n(root, i18n, paramsFor);
  assert.equal(leaf.textContent, "Hola, Ana");
  assert.equal(leaf.getAttribute("lang"), "es-419");
  assert.equal(image.getAttribute("alt"), "Imagen 4");
  assert.equal(search.getAttribute("placeholder"), "Hola, Ana");
  assert.equal(search.getAttribute("title"), "English only");
  assert.equal(parent.textContent, "Untouched");
  assert.equal(parent.children[0], icon);
  assert.equal(parent.getAttribute("aria-label"), "Hola, Ana");
  assert.equal(untouched.textContent, "Library content");
  i18n.setLocale("en");
  applyI18n(leaf, i18n, paramsFor);
  assert.equal(leaf.textContent, "Hello, Ana");
  assert.equal(leaf.getAttribute("lang"), "en");
});

test("parameter providers survive reapply, stay per engine/element/key and can be cleared", () => {
  const first = translator("en"), second = translator("en");
  const leaf = new FakeElement({ "data-i18n": "greeting" });
  const root = new FakeElement({}, "", [leaf]);
  let name = "Ana";
  applyI18n(root, first, () => ({ name }));
  name = "Bea";
  first.setLocale("es-UY");
  applyI18n(root, first);
  assert.equal(leaf.textContent, "Hola, Bea");
  applyI18n(leaf, second);
  assert.equal(leaf.textContent, "Hello, {name}");
  applyI18n(root, first, () => ({ name: "New" }));
  assert.equal(leaf.textContent, "Hola, New");
  applyI18n(root, first, null);
  assert.equal(leaf.textContent, "Hola, {name}");
  const fresh = new FakeElement({ "data-i18n": "greeting" });
  root.children = [fresh];
  applyI18n(root, first);
  assert.equal(fresh.textContent, "Hola, {name}");
  assert.throws(() => applyI18n(root, first, {}), TypeError);
});

test("narrow provider updates preserve siblings and marker changes release old bindings", () => {
  const first = new FakeElement({ "data-i18n": "greeting" });
  const second = new FakeElement({ "data-i18n": "greeting" });
  const root = new FakeElement({}, "", [first, second]);
  const i18n = translator("en");
  applyI18n(root, i18n, () => ({ name: "Ana" }));
  applyI18n(first, i18n, () => ({ name: "Bea" }));
  i18n.setLocale("es-UY");
  applyI18n(root, i18n);
  assert.equal(first.textContent, "Hola, Bea");
  assert.equal(second.textContent, "Hola, Ana");
  first.setAttribute("data-i18n", "fallback");
  applyI18n(first, i18n);
  first.setAttribute("data-i18n", "greeting");
  applyI18n(first, i18n);
  assert.equal(first.textContent, "Hola, {name}");
});

test("cyclic fallback routes terminate and invalid catalogs never execute accessors", () => {
  const i18n = createI18n({ catalogs, locale: "es-UY", fallbacks: { ...inheritance, "es-419": ["es-UY"] } });
  assert.equal(i18n.t("greeting", { name: "Ana" }), "Hola, Ana");
  const hidden = {};
  Object.defineProperty(hidden, "greeting", { value: "Hi" });
  const symbol = { [Symbol("key")]: "Hi" };
  const inherited = Object.create({ greeting: "Hi" });
  for (const en of [hidden, symbol, inherited]) assert.throws(() => createI18n({ catalogs: { en } }), TypeError);
});

test("older Intl runtimes retain ordinary RTL scripts", () => {
  const context = { Intl: {
    getCanonicalLocales: Intl.getCanonicalLocales, NumberFormat: Intl.NumberFormat,
    PluralRules: Intl.PluralRules, DateTimeFormat: Intl.DateTimeFormat,
  } };
  runInNewContext(readFileSync(resolve(__dirname, "../../web/i18n-core.js"), "utf8"), context);
  assert.equal(runInNewContext('createI18n({ catalogs: { en: { hello: "Hello" } } }).direction("ar")', context), "rtl");
  assert.equal(runInNewContext('createI18n({ catalogs: { en: { hello: "Hello" } } }).direction("az-Arab")', context), "rtl");
});

test("generated files preserve UTF-8 and initialize both entry points before their controllers", () => {
  const web = resolve(__dirname, "../../web");
  const local = name => readFileSync(resolve(web, name), "utf8");
  const assets = ["i18n-core.js", "i18n-dom.js", "i18n-en.js", "i18n-locales.js", "i18n-app.js"];
  for (const [entry, controller] of [["setup.html", "setup.js"], ["index.html", "app.js"]]) {
    const scripts = [...local(entry).matchAll(/<script src="\/ui\/([^"?]+)[^"]*"><\/script>/g)].map(match => match[1]);
    assert.deepEqual(scripts.slice(-6), [...assets, controller]);
    assert.match(local(entry), /<html lang="en"/);
  }
  const context = {};
  for (const name of assets.slice(0, 4)) runInNewContext(local(name), context);
  assert.equal(runInNewContext(`
    createI18n({ locale: "es-419", catalogs: { en: lastbookI18nEnglish, ...lastbookI18nLocales } })
      .t("nav.guides")
  `, context), "Guías");
});

test("injected parameters are plain text in both text and attribute sinks", () => {
  const text = new FakeElement({ "data-i18n": "greeting" });
  const attr = new FakeElement({ "data-i18n-aria-label": "greeting" }, "", [new FakeElement()]);
  Object.defineProperty(text, "innerHTML", { set: () => assert.fail("HTML sink used") });
  const markup = '<img src=x onerror="boom()">';
  applyI18n(new FakeElement({}, "", [text, attr]), translator("es-UY"), () => ({ name: markup }));
  assert.equal(text.textContent, "Hola, " + markup);
  assert.equal(attr.getAttribute("aria-label"), "Hola, " + markup);
  assert.equal(text.childElementCount, 0);
  assert.equal(attr.getAttribute("lang"), null);
  attr.setAttribute("data-i18n-lang", "");
  applyI18n(attr, translator("es-UY"), () => ({ name: markup }));
  assert.equal(attr.getAttribute("lang"), "es-419");
});

test("prototype-named keys and plural forms stay isolated from the source catalogue", () => {
  const original = {
    en: { constructor: "A constructor", files: { other: "{count} files" } },
    "es-419": { files: { other: "{count} archivos" } },
  };
  const i18n = createI18n({ catalogs: original, locale: "es-419" });
  original["es-419"].files.other = "changed";
  delete original.en.constructor;
  assert.equal(i18n.t("files", { count: 2 }), "2 archivos");
  assert.equal(i18n.t("constructor"), "A constructor");
  assert.equal(i18n.t("toString"), undefined);
  assert.throws(() => createI18n({ catalogs: JSON.parse('{"en":{"__proto__":"invalid"}}') }), TypeError);
});

test("a failing binding or provider leaves its element alone and the rest still translates", () => {
  const bad = new FakeElement({ "data-i18n": "greeting" }, "Hello, bad");
  const good = new FakeElement({ "data-i18n": "greeting", "data-i18n-title": "files" }, "Hello, good");
  const plural = new FakeElement({ "data-i18n": "files" }, "files");
  const root = new FakeElement({}, "", [bad, good, plural]);
  const i18n = translator("es-419");
  const provider = element => {
    if (element === bad) throw new Error("provider failed");
    return { name: "Ana", count: 2 };
  };
  assert.doesNotThrow(() => applyI18n(root, i18n, provider));
  assert.equal(bad.textContent, "Hello, bad");
  assert.equal(bad.getAttribute("lang"), null);
  assert.equal(good.textContent, "Hola, Ana");
  assert.equal(good.getAttribute("title"), "2 archivos");
  assert.equal(plural.textContent, "2 archivos");
  // A resolve() failure inside one binding must not stop the element's other bindings.
  const broken = { ...i18n, resolve(key, params) {
    if (key === "greeting") throw new Error("resolve failed");
    return i18n.resolve(key, params);
  } };
  const both = new FakeElement({ "data-i18n": "greeting", "data-i18n-title": "files" }, "Hello");
  assert.doesNotThrow(() => applyI18n(new FakeElement({}, "", [both]), broken, () => ({ name: "Ana", count: 1 })));
  assert.equal(both.textContent, "Hello");
  assert.equal(both.getAttribute("title"), "1 archivo");
});
