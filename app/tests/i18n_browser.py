"""Browser integration over staged files, the real bridge and the HTTP handler.

Run with the optional Playwright development tool and Chromium:
  python3 -B app/tests/i18n_browser.py --chromium /path/to/chromium
The loopback relay stands in for WebView2's resource callback. It is test-only.
"""
import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'app')]
import fixture

DATA = fixture.ensure()
os.environ['LASTBOOK_DATA'] = str(DATA)
import bridge
import server
from engine.setup.manifest import Manifest

ROUTE = bridge.ui_language.ROUTE


class Relay(BaseHTTPRequestHandler):
    def do_GET(self):
        b = self.server.bridge
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        hold = self.server.holds.get((self.command, self.path))
        if hold is not None and not hold.wait(15):
            self.send_error(503)
            return
        gate = None
        if self.path == ROUTE:
            try:
                gate = self.server.language_replies[self.command].get_nowait()
            except (Empty, KeyError):
                pass
        done = threading.Event()
        responses = []

        def answer(response):
            responses.append(response)
            done.set()

        b.fetch(self.command, b.origin + self.path, self.headers, body, answer)
        if not done.wait(15):
            self.send_error(504)
            return
        response = responses[0]
        try:
            if gate:
                arrived, release = gate
                arrived.set()
                if not release.wait(15):
                    self.send_error(504)
                    return
            self.send_response(response.status)
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(Path(response.path).read_bytes() if response.path else response.body or b'')
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if response.delete:
                Path(response.path).unlink()
            response.release()

    do_POST = do_HEAD = do_GET

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def serve(module=None, language_file=None):
    handler = Relay if module else server.Handler
    with ThreadingHTTPServer(('127.0.0.1', 0), handler) as http:
        host = 'lastbook.invalid' if module else '127.0.0.1'
        origin = f'http://{host}:{http.server_port}'
        http.holds = {}
        http.language_replies = {method: Queue() for method in ('GET', 'POST')}
        if module:
            http.bridge = bridge.Bridge(module, 'buffer', origin, language_file=language_file)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            yield origin, http
        finally:
            for gate in http.holds.values():
                gate.set()
            http.shutdown()
            worker.join()


@contextlib.contextmanager
def delay_language_reply(http, method):
    arrived, release = threading.Event(), threading.Event()
    http.language_replies[method].put((arrived, release))
    try:
        yield arrived, release
    finally:
        release.set()


class Browser(unittest.TestCase):
    chromium = None

    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        web = Path(scratch.name) / 'web'
        subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'packaging' / 'ship_app_files.py'), scratch.name],
                       check=True)
        cls.enterClassContext(patch.object(server, 'WEB', web))
        cls.enterClassContext(patch.object(server.setup_api, 'web_dir', return_value=web))
        server.init(no_index=True)
        runtime = cls.enterClassContext(sync_playwright())
        cls.browser = runtime.chromium.launch(executable_path=cls.chromium,
                                             ignore_default_args=['--disable-back-forward-cache'],
                                             args=['--no-proxy-server', '--host-resolver-rules=MAP lastbook.invalid 127.0.0.1'])
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.language_file = self.tmp / bridge.ui_language.FILENAME

    def configure_setup(self, current=None, library=DATA):
        return server.setup_api.configure(mode='manage' if current else 'first-run', current=current,
                                          settings_dir=self.tmp, default_parent=self.tmp, manifest=Manifest(remote=None),
                                          pick_folder=lambda files=False: str(library))

    @contextlib.contextmanager
    def page(self, origin, http, locale='en-US'):
        context = self.browser.new_context(locale=locale, viewport={'width': 1280, 'height': 850})
        try:
            if hasattr(http, 'bridge'):
                context.add_init_script(http.bridge.top_script())
            page = context.new_page()
            page.set_default_timeout(5000)
            requests, errors = [], []
            page.on('request', lambda r: requests.append(r.url))
            page.on('pageerror', lambda e: errors.append(str(e)))
            yield page
            self.assertEqual(errors, [])
            self.assertTrue(all(url.startswith(origin + '/') for url in requests), requests)
        finally:
            context.close()

    def test_setup_save_and_library_in_a_fresh_profile(self):
        self.configure_setup()
        with serve(server.setup_api.SetupServer, self.language_file) as (origin, http), self.page(origin, http) as page:
            hold = http.holds[('GET', '/api/setup/state')] = threading.Event()
            page.goto(origin, wait_until='domcontentloaded')
            expect(page.locator('.loading')).to_have_text('Looking at this computer…')
            select = page.get_by_label('Interface language')
            expect(select).to_have_value('en')
            self.assertEqual(select.locator('[lang="es-419"]').inner_text(), 'Español (Latinoamérica)')
            select.select_option('es-419')
            page.get_by_role('button', name='Save language').click()
            expect(page.get_by_role('status')).to_have_text('Idioma guardado.')
            expect(page.locator('.loading')).to_have_text('Revisando esta computadora…')
            self.assertEqual(json.loads(self.language_file.read_bytes()), {'language': 'es-419'})
            hold.set()
            expect(page.locator('h1')).to_have_text('Configuración inicial de Lastbook')
            expect(page.get_by_role('button', name='Guardar idioma')).to_be_focused()
            expect(page.locator('#packH')).to_have_text('Biblioteca')
            page.locator('#haveLib').click()
            with page.expect_response('**/api/setup/finish') as done:
                page.locator('#open').click()
            self.assertEqual(done.value.json()['folder'], str(DATA))

        self.configure_setup(current=DATA)
        with serve(server, self.language_file) as (origin, http), self.page(origin, http) as page:
            page.add_init_script("addEventListener('pageshow', event => window.restoredFromCache = event.persisted)")
            page.goto(origin + '/#/guides')
            sidebar = page.locator('.side')
            guides = sidebar.get_by_role('link', name='Guías')
            expect(guides).to_have_attribute('aria-current', 'page')
            expect(guides).to_have_attribute('lang', 'es-419')
            expect(page.locator('html')).to_have_attribute('lang', 'en')
            top = page.get_by_role('searchbox', name='Buscar en la biblioteca')
            expect(top).to_have_attribute('placeholder', 'Buscar en la biblioteca')
            page.set_viewport_size({'width': 780, 'height': 820})
            expect(guides).to_have_attribute('title', 'Guías')
            page.set_viewport_size({'width': 390, 'height': 780})
            tab = page.locator('.tabbar').get_by_role('link', name='Guías')
            expect(tab).to_be_visible()
            expect(tab).to_have_attribute('aria-current', 'page')
            page.set_viewport_size({'width': 1280, 'height': 850})
            expect(guides).not_to_have_attribute('title', 'Guías')
            # Force the usual narrow toolbar field, independently of host fonts.
            page.locator('#topQ').evaluate("(el) => el.style.width='110px'")
            expect(top).to_have_attribute('placeholder', 'Buscar')
            top.fill('user text')
            page.locator('.skip').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#main')).to_be_focused()
            self.assertTrue(page.url.endswith('#/guides'))
            expect(top).to_have_value('user text')

            markup = '<img src=x onerror=window.bad=1>'
            page.set_viewport_size({'width': 390, 'height': 780})
            page.evaluate("(q) => location.hash = '#/search?q=' + encodeURIComponent(q)", markup)
            search = page.locator('#searchQ')
            expect(search).to_have_value(markup)
            expect(search).to_have_accessible_name('Buscar')
            self.assertEqual(page.locator('img[src=x]').count(), 0)
            self.assertIsNone(page.evaluate('window.bad'))
            page.evaluate("location.hash = '#/watch/vida?from=%23%2Fsearch'")
            expect(page.locator('.rtop .back')).to_have_text('Resultados de búsqueda')
            expect(page.locator('h1')).to_have_text('vida')  # library title
            page.evaluate("location.hash = '#/missing'")
            expect(page.get_by_role('link', name='Ir a Videos')).to_be_visible()

            page.set_viewport_size({'width': 1280, 'height': 850})
            page.evaluate("location.hash = '#/guides'")
            expect(page.locator('h1')).to_have_text('What do you need?')
            page.evaluate("window.guideView = document.querySelector('.hero')")
            sidebar.get_by_role('link', name='Ajustes').click()
            expect(page.locator('h1')).to_have_text('Biblioteca e IA local')
            expect(page.get_by_role('link', name='Volver a la biblioteca')).to_be_visible()
            page.get_by_label('Idioma de la interfaz').select_option('en')
            pending = http.holds[('POST', ROUTE)] = threading.Event()
            page.get_by_role('button', name='Guardar idioma').click()
            expect(page.get_by_role('status')).to_have_text('Guardando el idioma…')
            expect(page.locator('h1')).to_have_text('Biblioteca e IA local')
            self.assertEqual(json.loads(self.language_file.read_bytes()), {'language': 'es-419'})
            page.get_by_label('Idioma de la interfaz').select_option('es-419')
            pending.set()
            expect(page.get_by_role('status')).to_have_text('Language saved.')
            expect(page.get_by_label('Interface language')).to_have_value('en')
            expect(page.locator('h1')).to_have_text('Library and local AI')
            expect(page.get_by_role('button', name='Save language')).to_be_focused()
            page.evaluate('history.back()')
            page.wait_for_url('**/#/guides', wait_until='commit')
            expect(sidebar.get_by_role('link', name='Guides')).to_be_visible()
            self.assertTrue(page.evaluate('window.restoredFromCache'))
            self.assertTrue(page.evaluate("window.guideView === document.querySelector('.hero')"))
            sidebar.get_by_role('link', name='Settings').click()
            page.get_by_role('link', name='Back to the library').click()
            expect(page.locator('.side').get_by_role('link', name='Guides')).to_be_visible()

    def test_setup_polling_and_a_completed_action_preserve_the_selector(self):
        setup = self.configure_setup()
        setup.job = {'state': 'downloading', 'items': []}
        with serve(server.setup_api.SetupServer, self.language_file) as (origin, http), self.page(origin, http) as page:
            pause = http.holds[('POST', '/api/setup/pause')] = threading.Event()
            with page.expect_response('**/api/setup/job'):
                page.goto(origin)
                expect(page.get_by_role('button', name='Pause')).to_be_visible()
            page.get_by_role('button', name='Pause').click()
            select = page.get_by_label('Interface language')
            select.focus()
            with setup.lock:
                setup.job['state'] = 'paused'
            pause.set()
            expect(page.get_by_role('button', name='Resume')).to_be_visible()
            expect(select).to_be_focused()
            select.select_option('es-419')
            page.get_by_role('button', name='Save language').click()
            expect(page.get_by_role('status')).to_have_text('Idioma guardado.')
            expect(page.get_by_role('button', name='Resume')).to_be_visible()

    def test_preference_loading_guards_submit_on_success_and_failure(self):
        self.configure_setup()
        for fails in (False, True):
            with self.subTest(fails=fails), serve(server.setup_api.SetupServer, self.language_file) as (origin, http):
                with self.page(origin, http) as page, delay_language_reply(http, 'GET') as (arrived, release):
                    if fails:
                        with patch.object(bridge.ui_language, '_load', side_effect=PermissionError):
                            page.goto(origin)
                            self.assertTrue(arrived.wait(5))
                    else:
                        page.goto(origin)
                        self.assertTrue(arrived.wait(5))
                    posts = []
                    page.on('request', lambda r: posts.append(r) if r.method == 'POST' and r.url.endswith(ROUTE) else None)
                    expect(page.locator('#languageSettings')).to_be_hidden()
                    page.eval_on_selector('#languageSettings', """form => {
                        form.querySelector('select').value = 'es-419';
                        form.requestSubmit();
                    }""")
                    expect(page.locator('h1')).to_have_text('Set up Lastbook')
                    if fails:
                        expect(page.locator('#languageStatus')).to_be_empty()
                    release.set()
                    expect(page.get_by_label('Interface language')).to_have_value('en')
                    if fails:
                        expect(page.get_by_role('status')).to_have_text('Could not load the saved language.')
                    self.assertEqual(posts, [])
                    self.assertFalse(self.language_file.exists())
                    page.get_by_label('Interface language').select_option('es-419')
                    page.get_by_role('button', name='Save language').press('Enter')
                    expect(page.get_by_role('status')).to_have_text('Idioma guardado.')
                self.language_file.unlink()

    def test_library_ignores_an_old_get_after_a_save_and_route_change(self):
        self.configure_setup(current=DATA)
        with serve(server, self.language_file) as (origin, http), self.page(origin, http) as library:
            library.add_init_script("""window.languageReads = 0;
                const readJSON = Response.prototype.json;
                Response.prototype.json = async function () {
                    const data = await readJSON.call(this);
                    if (this.url.endsWith('/api/ui-language')) setTimeout(() => window.languageReads++, 0);
                    return data;
                };""")
            with delay_language_reply(http, 'GET') as (arrived, release):
                library.goto(origin + '/#/guides')
                self.assertTrue(arrived.wait(5))
                with self.page(origin, http) as settings:
                    settings.goto(origin + '/ui/setup.html#manage')
                    settings.get_by_label('Interface language').select_option('es-419')
                    settings.get_by_role('button', name='Save language').click()
                    expect(settings.get_by_role('status')).to_have_text('Idioma guardado.')
                library.evaluate("""() => {
                    location.hash = '#/search';
                    dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
                }""")
                expect(library.locator('.side').get_by_role('link', name='Guías')).to_be_visible()
                search = library.get_by_role('searchbox', name='Buscar en la biblioteca')
                search.focus()
                release.set()
                library.wait_for_function('window.languageReads === 2')
                expect(search).to_be_focused()
                expect(library.locator('.side').get_by_role('link', name='Guías')).to_be_visible()

    def test_delayed_save_replies_from_two_windows_preserve_the_last_commit(self):
        self.configure_setup()
        for fails in (False, True):
            with self.subTest(fails=fails), serve(server.setup_api.SetupServer, self.language_file) as (origin, http):
                with self.page(origin, http) as first, self.page(origin, http) as second:
                    first.goto(origin)
                    second.goto(origin)
                    first_posts = []
                    first.on('request', lambda r: first_posts.append(r) if r.method == 'POST' and r.url.endswith(ROUTE) else None)
                    first.get_by_label('Interface language').select_option('es-419')
                    expect(second.get_by_label('Interface language')).to_have_value('en')
                    with delay_language_reply(http, 'POST') as (arrived, release):
                        if fails:
                            with patch.object(bridge.ui_language.os, 'replace', side_effect=PermissionError):
                                first.get_by_role('button', name='Save language').click()
                                self.assertTrue(arrived.wait(5))
                        else:
                            first.get_by_role('button', name='Save language').click()
                            self.assertTrue(arrived.wait(5))
                        expect(first.get_by_role('status')).to_have_text('Saving language…')
                        first.get_by_label('Interface language').select_option('en')
                        first.eval_on_selector('#languageSettings', 'form => form.requestSubmit()')
                        second.get_by_role('button', name='Save language').click()
                        expect(second.get_by_role('status')).to_have_text('Language saved.')
                        release.set()
                        expected = 'Could not save the language. Try again.' if fails else 'Idioma guardado.'
                        expect(first.get_by_role('status')).to_have_text(expected)
                        expect(second.get_by_role('status')).to_have_text('Language saved.')
                        self.assertEqual(len(first_posts), 1)
                        self.assertEqual(json.loads(self.language_file.read_bytes()), {'language': 'en'})
                with self.page(origin, http, 'es-UY') as restarted:
                    restarted.goto(origin)
                    expect(restarted.get_by_label('Interface language')).to_have_value('en')
                self.language_file.unlink()

    def test_failures_are_visible_and_never_replace_the_saved_preference(self):
        self.configure_setup()
        self.language_file.mkdir()  # replacing a directory with the preference file fails at the filesystem
        with serve(server.setup_api.SetupServer, self.language_file) as (origin, http), self.page(origin, http) as page:
            page.goto(origin)
            page.get_by_label('Interface language').select_option('es-419')
            page.get_by_role('button', name='Save language').click()
            expect(page.get_by_role('status')).to_have_text('Could not save the language. Try again.')
            expect(page.get_by_label('Interface language')).to_have_value('en')
            expect(page.locator('h1')).to_have_text('Set up Lastbook')
            self.assertTrue(self.language_file.is_dir())
            self.language_file.rmdir()
            self.language_file.write_text('{"language":"es-419"}', encoding='utf-8')
            written = self.language_file.read_bytes()
            # Simulate a broken Spanish asset while still loading the real UI and English catalogue.
            page.route('**/i18n-locales.js*', lambda route: route.fulfill(
                status=200, content_type='text/javascript', body='window.lastbookI18nLocales = {"es-419":{"invalid":"bad"}};'))
            page.reload()
            expect(page.get_by_role('status')).to_have_text('Spanish is unavailable. Lastbook is using English.')
            expect(page.get_by_label('Interface language')).to_have_value('es-419')
            self.assertEqual(self.language_file.read_bytes(), written)
            page.unroute('**/i18n-locales.js*')
            page.reload()
            expect(page.locator('h1')).to_have_text('Configuración inicial de Lastbook')
            self.assertEqual(self.language_file.read_bytes(), written)
            invalid = b'{"language":"en","language":"es-419"}'
            self.language_file.write_bytes(invalid)
            page.reload()
            expect(page.get_by_label('Interface language')).to_have_value('en')
            expect(page.locator('h1')).to_have_text('Set up Lastbook')
            self.assertEqual(self.language_file.read_bytes(), invalid)

    def test_desktop_requires_opt_in_even_with_spanish_or_invalid_browser_locales(self):
        self.configure_setup(current=DATA)
        with serve(server, self.language_file) as (origin, http):
            for locale in ('en-US', 'es-UY', 'es-AR', 'es-CL', 'es-ES', 'fr-FR', 'malformed_tag'):
                with self.subTest(locale=locale), self.page(origin, http) as page:
                    page.add_init_script(f"Object.defineProperty(navigator, 'languages', {{value: [{json.dumps(locale)}]}})")
                    page.goto(origin + '/ui/setup.html#manage')
                    expect(page.get_by_label('Interface language')).to_have_value('en')
                    self.assertFalse(self.language_file.exists())
            self.language_file.write_text('{"language":"es-419"}', encoding='utf-8')
            with self.page(origin, http, 'fr-FR') as page:
                page.goto(origin + '/ui/setup.html#manage')
                expect(page.get_by_label('Idioma de la interfaz')).to_have_value('es-419')
                expect(page.locator('h1')).to_have_text('Biblioteca e IA local')

    def test_remembered_language_shows_before_the_bridge_replies_and_the_file_wins(self):
        self.configure_setup(current=DATA)
        self.language_file.write_text('{"language":"es-419"}', encoding='utf-8')
        with serve(server, self.language_file) as (origin, http), self.page(origin, http) as page:
            page.goto(origin + '/#/guides')
            expect(page.locator('.side').get_by_role('link', name='Guías')).to_be_visible()
            # Next page load: the GET is held, yet the sidebar is already Spanish (no English flash).
            with delay_language_reply(http, 'GET') as (arrived, release):
                page.reload(wait_until='commit')
                self.assertTrue(arrived.wait(5))
                expect(page.locator('.side').get_by_role('link', name='Guías')).to_be_visible()
                release.set()
            # The file is the truth: a change made elsewhere replaces the remembered language once read.
            self.language_file.write_text('{"language":"en"}', encoding='utf-8')
            with delay_language_reply(http, 'GET') as (arrived, release):
                page.reload(wait_until='commit')
                self.assertTrue(arrived.wait(5))
                expect(page.locator('.side').get_by_role('link', name='Guías')).to_be_visible()
                release.set()
            expect(page.locator('.side').get_by_role('link', name='Guides')).to_be_visible()
            with delay_language_reply(http, 'GET') as (arrived, release):
                page.reload(wait_until='commit')
                self.assertTrue(arrived.wait(5))
                expect(page.locator('.side').get_by_role('link', name='Guides')).to_be_visible()
                release.set()
        # A profile with nothing remembered starts in English, whatever the browser locale says.
        with serve(server, self.language_file) as (origin, http), self.page(origin, http, locale='es-AR') as page:
            with delay_language_reply(http, 'GET') as (arrived, release):
                page.goto(origin + '/#/guides', wait_until='commit')
                self.assertTrue(arrived.wait(5))
                expect(page.locator('.side').get_by_role('link', name='Guides')).to_be_visible()
                release.set()

    def test_a_remembered_value_that_is_not_a_supported_language_is_ignored(self):
        self.configure_setup(current=DATA)
        with serve(server, self.language_file) as (origin, http), self.page(origin, http) as page:
            page.add_init_script("localStorage.setItem('lastbook.ui-language', 'fr')")
            with delay_language_reply(http, 'GET') as (arrived, release):
                page.goto(origin + '/#/guides', wait_until='commit')
                self.assertTrue(arrived.wait(5))
                expect(page.locator('.side').get_by_role('link', name='Guides')).to_be_visible()
                release.set()

    def test_a_hung_read_or_save_times_out_and_the_selector_recovers(self):
        self.configure_setup()
        with serve(server.setup_api.SetupServer, self.language_file) as (origin, http), self.page(origin, http) as page:
            page.clock.install()
            with delay_language_reply(http, 'GET') as (arrived, release):
                page.goto(origin)
                self.assertTrue(arrived.wait(5))
                expect(page.locator('#languageSettings')).to_be_hidden()
                page.clock.fast_forward(9000)  # past the read timeout
                expect(page.locator('#languageSettings')).to_be_visible()
                expect(page.get_by_role('status')).to_have_text('Could not load the saved language.')
                expect(page.get_by_label('Interface language')).to_have_value('en')
                release.set()
            with delay_language_reply(http, 'POST') as (arrived, release):
                page.get_by_label('Interface language').select_option('es-419')
                page.get_by_role('button', name='Save language').click()
                self.assertTrue(arrived.wait(5))
                expect(page.get_by_role('status')).to_have_text('Saving language…')
                expect(page.get_by_role('button', name='Save language')).to_have_attribute('aria-disabled', 'true')
                page.clock.fast_forward(16000)  # past the save timeout
                expect(page.get_by_role('status')).to_have_text('Could not save the language. Try again.')
                expect(page.get_by_role('button', name='Save language')).not_to_have_attribute('aria-disabled', 'true')
                expect(page.get_by_label('Interface language')).to_have_value('en')
                release.set()
            page.get_by_label('Interface language').select_option('es-419')
            page.get_by_role('button', name='Save language').click()
            expect(page.get_by_role('status')).to_have_text('Idioma guardado.')

    def test_label_helpers_accept_plain_strings_and_pairs(self):
        self.configure_setup(current=DATA)
        self.language_file.write_text('{"language":"es-419"}', encoding='utf-8')
        with serve(server, self.language_file) as (origin, http), self.page(origin, http) as page:
            page.goto(origin + '/#/guides')
            expect(page.locator('.side').get_by_role('link', name='Guías')).to_be_visible()
            html = page.evaluate("""() => [
                backButton('#/videos', 'Videos'), backButton('#/library', ['nav.library', 'Library']), backButton('#/x', 'Custom label'),
                backButton('#/x', ['nav.back', 'Back']), backButton('#/x'),
                searchBox('a', '', 'p', 'Filter'), searchBox('b', '', 'p', ['search.go', 'Go']), searchBox('c', '', 'p', 'Other'), searchBox('d', '', 'p'),
            ]""")
            def parse(markup):
                return page.evaluate("""(markup) => {
                    const box = document.createElement('div');
                    box.innerHTML = markup;
                    window.LastbookI18n.apply(box);
                    const target = box.querySelector('a[data-back] span, form button');
                    return [target.textContent, target.getAttribute('data-i18n')];
                }""", markup)
            self.assertEqual([parse(m) for m in html], [
                ['Videos', 'nav.videos'], ['Biblioteca', 'nav.library'], ['Custom label', None],
                ['Atrás', 'nav.back'], ['Atrás', 'nav.back'],
                ['Filtrar', 'search.filter'], ['Ir', 'search.go'], ['Other', None], ['Buscar', 'search.label'],
            ])
            self.assertNotIn('data-i18n="null"', ''.join(html))
            self.assertNotIn('data-i18n="undefined"', ''.join(html))

    def test_navigation_helpers_keep_their_labels_and_local_back_target(self):
        self.configure_setup(current=DATA)
        self.language_file.write_text('{"language":"es-419"}', encoding='utf-8')
        with serve(server, self.language_file) as (origin, http), self.page(origin, http) as page:
            page.goto(origin + '/#/videos/all')
            expect(page.get_by_role('button', name='Ir', exact=True)).to_be_visible()
            page.locator('#vq').fill('water')
            page.get_by_role('button', name='Ir', exact=True).click()
            page.wait_for_url('**/#/videos/all?*q=water*')
            page.evaluate("(id) => location.hash = '#/shelf/' + id", server.SHELVES[0][0])
            expect(page.get_by_role('button', name='Filtrar', exact=True)).to_be_visible()
            expect(page.locator('a[data-back]')).to_have_text('Biblioteca')
            page.evaluate("(from) => location.hash = '#/watch/vida?from=' + encodeURIComponent(from)", 'javascript:void(0)')
            expect(page.locator('a[data-back]')).to_have_attribute('href', '#/')
            page.evaluate("location.hash = '#/watch/vida?from=%23guides'")
            back = page.locator('a[data-back]')
            expect(back).to_have_attribute('href', '#guides')
            page.set_viewport_size({'width': 390, 'height': 780})
            back.click()
            page.wait_for_url('**/#guides')
            expect(page.locator('h1')).to_have_text('What do you need?')

    def test_local_http_has_no_preference_route_and_keeps_its_shell_offline(self):
        self.configure_setup(current=DATA)
        with serve() as (origin, http):
            connection = HTTPConnection('127.0.0.1', http.server_port, timeout=5)
            try:
                for method in ('GET', 'HEAD', 'POST'):
                    connection.request(method, ROUTE, '{"language":"es-419"}' if method == 'POST' else None,
                                       {'Content-Type': 'application/json', bridge.KEY_HEADER: 'not-a-native-key'})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 404)
                    response.read()
            finally:
                connection.close()
            self.assertFalse(self.language_file.exists())
            for locale in ('en-US', 'es-UY', 'es-AR', 'es-CL', 'es-ES', 'fr-FR'):
                with self.page(origin, http, locale) as page:
                    page.goto(origin + '/#/guides')
                    guides = page.locator('.side').get_by_role('link', name='Guides')
                    expect(guides).to_be_visible()
                    expect(page.locator('#sideSettings')).to_be_hidden()
                    page.wait_for_function('!!navigator.serviceWorker.controller')
                    if locale == 'es-CL':
                        self.assertFalse(page.evaluate("async () => !!await caches.match('/api/ui-language')"))
                        page.context.set_offline(True)
                        page.reload(wait_until='domcontentloaded')
                        expect(guides).to_be_visible()
                        self.assertTrue(page.evaluate('!!window.LastbookI18n'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium', help='path to Chromium, or use the Playwright-managed browser')
    options, rest = parser.parse_known_args()
    Browser.chromium = options.chromium
    unittest.main(argv=[sys.argv[0], *rest])
