"""Catalogue schema, deterministic generation and the release staging gate."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packaging'))
import i18n_catalogs as catalogues  # noqa: E402


class Catalogues(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.english = self.work / 'en.json'
        self.spanish = self.work / 'es-419.json'
        self.english.write_text('{"hi":"Hello, {name}", "files":{"=0":"None", "other":"{count} files"}}', encoding='utf-8')
        self.spanish.write_text('{"hi":"Hola, {name}"}', encoding='utf-8')

    def test_rejects_missing_catalogues(self):
        for file in (self.english, self.spanish):
            with self.subTest(file=file.name):
                contents = file.read_bytes()
                file.unlink()
                with self.assertRaisesRegex(ValueError, f'missing catalogues: {file.stem}'):
                    catalogues.generate(self.work)
                file.write_bytes(contents)

    def test_rejects_duplicate_keys_at_every_depth(self):
        for text in ('{"hi":"A", "hi":"B"}', '{"files":{"other":"A", "other":"B"}}'):
            self.spanish.write_text(text, encoding='utf-8')
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'duplicate key'):
                catalogues.generate(self.work)

    def test_rejects_invalid_values_and_placeholders(self):
        for value in [None, False, 2, {}, [], '', ' ', '\ufeff \ufeff', '{name', '{{name}}', '{first-name}', '\ud800', {'other': False},
                      {'other': 'a', '=9007199254740992': 'b'}, {'other': 'a', '=01': 'b'}, {'one': 'one'},
                      {'other': 'Hello, {name}', 'one': 'one'}, {'other': 'a', 'notACategory': 'b'}]:
            self.spanish.write_text(json.dumps({'hi': value}), encoding='utf-8')
            with self.subTest(value=value), self.assertRaises(ValueError):
                catalogues.generate(self.work)
        self.spanish.write_bytes(b'{"hi":"\xff {name}"}')
        with self.assertRaisesRegex(ValueError, 'utf-8'):
            catalogues.generate(self.work)

    def test_rejects_unknown_keys_and_incompatible_contracts(self):
        for value, message in [({'__proto__': 'x'}, 'invalid message key'), ({'unknown': 'x'}, 'unknown message key'),
                               ({'hi': 'Hola, {persona}'}, 'incompatible message'),
                               ({'hi': {'other': 'Hola, {name}'}}, 'incompatible message'),
                               ({'files': '{count} archivos'}, 'incompatible message'),
                               ({'files': {'other': '{count} archivos'}}, 'incompatible message')]:
            self.spanish.write_text(json.dumps(value), encoding='utf-8')
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, message):
                catalogues.generate(self.work)

    def test_allows_missing_messages_and_locale_specific_plural_categories(self):
        self.spanish.write_text('{"files":{"=0":"Ninguno", "many":"{count} archivos", "other":"{count} archivos"}}', encoding='utf-8')
        self.assertIn('Ninguno', catalogues.generate(self.work)['i18n-locales.js'].decode('utf-8'))

    def test_output_is_order_independent_and_writes_literal_data(self):
        value = '¡Está listo! \u2028 <img src=x onerror="bad()"> "); bad(); ({name}'
        messages = {'hi': value, 'files': {'other': '{count} archivos', '=0': 'Ninguno'}}
        self.spanish.write_text(json.dumps(messages, ensure_ascii=False), encoding='utf-8')
        first = catalogues.generate(self.work)
        self.spanish.write_text(json.dumps(dict(reversed(list(messages.items())))), encoding='utf-8')
        self.assertEqual(catalogues.generate(self.work), first)
        js = first['i18n-locales.js'].decode('utf-8')
        self.assertIn('¡Está listo!', js)
        self.assertNotIn('\u2028', js)
        literal = js.split(' = JSON.parse(', 1)[1].removesuffix(');\n')
        self.assertEqual(json.loads(json.loads(literal)), {'es-419': messages})

    def test_source_staging_and_missing_or_stale_assets(self):
        generated = catalogues.generate()
        catalogues.check_assets(ROOT / 'web', generated)
        stage = self.work / 'stage'
        subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'packaging' / 'ship_app_files.py'), str(stage)],
                       check=True, capture_output=True)
        web = stage / 'web'
        catalogues.check_assets(web, generated)
        self.assertFalse((stage / 'translations').exists())
        for name in ('i18n-en.js', 'i18n-locales.js', 'i18n-app.js', 'app.js'):
            with self.subTest(name=name):
                (web / name).unlink()
                with self.assertRaisesRegex(ValueError, 'required localization asset missing'):
                    catalogues.check_assets(web, generated)
                shutil.copyfile(ROOT / 'web' / name, web / name)
        (web / 'setup.html').write_text('<!doctype html><title>Old Setup</title>', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'missing or misordered localization scripts'):
            catalogues.check_assets(web, generated)
        setup = (ROOT / 'web' / 'setup.html').read_text(encoding='utf-8')
        script = next(line for line in setup.splitlines() if 'src="/ui/i18n-app.js' in line)
        for bad in ('<!--' + script + '-->', script.replace('src=', 'data-src='), script.replace('<script ', '<script defer ')):
            with self.subTest(script=bad):
                (web / 'setup.html').write_text(setup.replace(script, bad), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'missing or misordered localization scripts'):
                    catalogues.check_assets(web, generated)
        shutil.copyfile(ROOT / 'web' / 'setup.html', web / 'setup.html')
        (web / 'app.js').write_bytes(b'// old controller\n')
        with self.assertRaisesRegex(ValueError, 'packaged web asset differs from source'):
            catalogues.check_assets(web, generated)
        shutil.copyfile(ROOT / 'web' / 'app.js', web / 'app.js')
        (web / 'i18n-locales.js').write_bytes(b'// stale\n')
        with self.assertRaisesRegex(ValueError, 'stale catalogue'):
            catalogues.check_assets(web, generated)


class SpanishWording(unittest.TestCase):
    """The shipped es-419 catalogue keeps the terms docs/i18n.md#sample-locale-wording-es-419 asks for."""

    @classmethod
    def setUpClass(cls):
        load = lambda name: json.loads((ROOT / 'translations' / 'desktop' / name).read_text(encoding='utf-8'))
        cls.en, cls.es = load('en.json'), load('es-419.json')

    def test_setup_and_settings_are_different_words(self):
        self.assertEqual(self.es['nav.settings'], 'Ajustes')
        self.assertIn('Configuración inicial', self.es['setup.title'])
        self.assertIn('configuración inicial', self.es['setup.error'])
        self.assertNotEqual(self.es['nav.settings'], self.es['setup.title'])
        # Where a sentence names both screens, it names both.
        preview = self.es['language.preview']
        self.assertIn('configuración inicial', preview)
        self.assertIn('ajustes', preview)
        self.assertIn('Setup and Settings', self.en['language.preview'])

    def test_state_prompt_and_everyday_words(self):
        self.assertIn('estado o región', self.es['setup.chooseIntro'])
        self.assertIn('computadora', self.es['setup.loading'])
        everything = ' '.join(self.es.values())
        for avoid in (' equipo', 'Equipo', 'ordenador', 'vídeo', 'Vídeo'):
            self.assertNotIn(avoid, everything)
        self.assertEqual(self.es['language.unavailable'], 'El español no está disponible. Lastbook usa inglés.')
        self.assertNotIn('está en inglés', self.es['language.unavailable'])

    def test_no_message_is_left_in_english(self):
        # Words that must differ from English (brand names and loan words such as "Chat" may match).
        same = {key for key in self.es if self.es[key] == self.en[key]}
        self.assertLessEqual(same, {'nav.chat', 'nav.videos', 'nav.video'})
