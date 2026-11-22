#!/usr/bin/env python3
"""Offline encyclopedia search and Chat tools, with fake ZIM archives. No libzim, no library, no network.

  python3 -B -m unittest app.tests.test_encyclopedias
"""
import os, sys, unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


# Lastbook's own top-level modules and package: what load() may import and must not leave behind.
PROJECT_MODULES = ('assistant', 'retrieval', 'server', 'llm_local', 'bridge', 'engine')


def ours(name):
    return name.split('.')[0] in PROJECT_MODULES


def load():
    """encyclopedias and the Chat helpers, imported without leaving a data-folder path behind."""
    before, env = dict(sys.modules), dict(os.environ)
    sys.path.insert(0, str(ROOT))
    sys.modules['onnxruntime'] = None
    try:
        from engine import encyclopedias
        import assistant
        return encyclopedias, assistant
    finally:
        # Drop Lastbook's own modules from sys.modules so later tests (test_what_ships and
        # others) can import engine.paths / server against their own LASTBOOK_DATA.
        # This file keeps the module objects it returned. Third-party modules (NumPy above all,
        # which cannot be imported twice in one process) stay loaded.
        if str(ROOT) in sys.path:
            sys.path.remove(str(ROOT))
        for name in set(sys.modules) - set(before):
            if ours(name):
                del sys.modules[name]
        sys.modules.update(before)
        if 'onnxruntime' not in before:
            sys.modules.pop('onnxruntime', None)
        os.environ.clear()
        os.environ.update(env)


encyclopedias, assistant = load()

ZIM = 'mdwiki_en_all_maxi_2025-11.zim'
CHOLERA = (
    '<html><head><script>alert(1)</script></head><body>'
    '<h1>Cholera</h1><p>Cholera is an infection of the small intestine.</p>'
    '<p>Rehydration with ORS is the main treatment. Antibiotics may help some people.</p>'
    '</body></html>'
)
BLEACH = (
    '<html><body><h1>Water disinfection</h1>'
    '<p>Introduction and background about storing rainwater in clean containers.</p>\n\n'
    '<p>For disinfection, the usual unscented household bleach dose is two drops per litre of clear water, '
    'then wait 30 minutes. Do not use scented or colour-safe bleach.</p>\n\n'
    '<p>See also boiling, which is preferred when fuel is available.</p>'
    '</body></html>'
)


class Item:
    def __init__(self, content, mimetype='text/html'):
        self.content = content.encode() if isinstance(content, str) else content
        self.mimetype = mimetype


class Entry:
    def __init__(self, title, content, mimetype='text/html', redirect=None, path=None):
        self.title = title
        self.path = path or title
        self.is_redirect = redirect is not None
        self._redirect = redirect
        self._item = Item(content, mimetype)

    def get_redirect_entry(self):
        return self._redirect

    def get_item(self):
        return self._item


class Archive:
    def __init__(self, entries, has_index=True, index=None):
        self.has_fulltext_index = has_index
        self._entries = entries
        self._index = index or {}

    def get_entry_by_path(self, p):
        if p not in self._entries:
            raise KeyError(p)
        return self._entries[p]


def search_paths(arc, q, per_file):
    q = (q or '').lower()
    hits = []
    for needle, paths in (arc._index or {}).items():
        if needle in q or q in needle:
            hits.extend(paths)
    return hits[:per_file]


def mdwiki():
    cholera = Entry('Cholera', CHOLERA, path='Cholera')
    bleach = Entry('Water disinfection', BLEACH, path='Water_disinfection')
    alias = Entry('Cholera (redirect)', '', path='Cholera_alias', redirect=cholera)
    return Archive(
        {'Cholera': cholera, 'Cholera_alias': alias, 'Water_disinfection': bleach},
        index={'cholera': ['Cholera'], 'bleach': ['Water_disinfection'], 'water': ['Water_disinfection']},
    )


class Keys(unittest.TestCase):
    def test_parse_key_accepts_usual_shapes(self):
        self.assertEqual(encyclopedias.parse_key('zim/' + ZIM + '/Cholera'), (ZIM, 'Cholera'))
        self.assertEqual(encyclopedias.parse_key(ZIM + '/Cholera'), (ZIM, 'Cholera'))
        self.assertEqual(encyclopedias.parse_key('/zim/' + ZIM + '/A/B'), (ZIM, 'A/B'))

    def test_parse_key_rejects_traversal_and_junk(self):
        self.assertIsNone(encyclopedias.parse_key(''))
        self.assertIsNone(encyclopedias.parse_key(ZIM))
        self.assertIsNone(encyclopedias.parse_key('zim/../evil.zim/Cholera'))
        self.assertIsNone(encyclopedias.parse_key('zim/' + ZIM + '/../../etc/passwd'))
        self.assertIsNone(encyclopedias.parse_key('zim/' + ZIM + '/%2e%2e/etc/passwd'))
        self.assertIsNone(encyclopedias.parse_key('zim/' + ZIM + '/'))

    def test_key_ok_needs_a_present_file(self):
        key = 'zim/' + ZIM + '/Cholera'
        self.assertTrue(encyclopedias.key_ok(key, names=[ZIM]))
        self.assertFalse(encyclopedias.key_ok(key, names=[]))
        self.assertFalse(encyclopedias.key_ok('zim/missing.zim/Cholera', names=[ZIM]))

    def test_publisher_and_year(self):
        self.assertEqual(encyclopedias.publisher(ZIM), 'Medical encyclopedia (MDWiki)')
        self.assertEqual(encyclopedias.year_of(ZIM), 2025)
        self.assertIn('Wikipedia', encyclopedias.publisher('wikipedia_en_all_nopic_2025-11.zim'))

    def test_prefer_primary_puts_english_ahead_of_translations(self):
        paths = [
            'Solar_water_purification/ar',
            'Solar_water_purification/hi',
            'Water_supply_and_purification_for_emergencies',
            'Solar_water_purification',
            'Only_spanish/es',
        ]
        got = encyclopedias.prefer_primary(paths)
        self.assertEqual(got[0], 'Water_supply_and_purification_for_emergencies')
        self.assertEqual(got[1], 'Solar_water_purification')
        self.assertNotIn('Solar_water_purification/ar', got)
        self.assertNotIn('Solar_water_purification/hi', got)
        self.assertIn('Only_spanish/es', got)

    def test_html_to_text_strips_markup_and_scripts(self):
        text = encyclopedias.html_to_text(CHOLERA)
        self.assertIn('Cholera is an infection', text)
        self.assertNotIn('<', text)
        self.assertNotIn('alert', text)

    def test_pick_section_jumps_to_the_matching_paragraph_and_caps(self):
        text = encyclopedias.html_to_text(BLEACH)
        got = encyclopedias.pick_section(text, 'bleach dose', cap=180)
        self.assertIn('two drops per litre', got)
        self.assertNotIn('rainwater', got)
        self.assertLessEqual(len(got), 180)
        self.assertEqual(encyclopedias.pick_section(text, '', cap=40), text[:40])


class SearchAndRead(unittest.TestCase):
    def setUp(self):
        self.arc = mdwiki()
        self.archives = [(ZIM, self.arc)]

    def test_search_returns_capped_hits_from_a_fake_archive(self):
        hits = encyclopedias.search('cholera', archives=self.archives, search_paths=search_paths, limit=3, excerpt=80)
        self.assertEqual(len(hits), 1)
        h = hits[0]
        self.assertEqual(h['title'], 'Cholera')
        self.assertEqual(h['zim'], ZIM)
        self.assertEqual(h['article'], 'Cholera')
        self.assertEqual(h['kind'], 'zim')
        self.assertEqual(h['zim_key'], 'zim/' + ZIM + '/Cholera')
        self.assertTrue(h['path'].startswith('zim/'))
        self.assertLessEqual(len(h['excerpt']), 80)
        self.assertIn('small intestine', h['excerpt'])
        self.assertNotIn('<script', h['excerpt'])

    def test_search_follows_a_redirect_and_filters_by_collection(self):
        def paths(arc, q, per_file):
            return ['Cholera_alias']
        hits = encyclopedias.search('cholera', archives=self.archives, search_paths=paths, collection='mdwiki')
        self.assertEqual(hits[0]['title'], 'Cholera')
        none = encyclopedias.search('cholera', archives=self.archives, search_paths=paths, collection='appropedia')
        self.assertEqual(none, [])

    def test_search_empty_query_and_all_files_failing(self):
        self.assertEqual(encyclopedias.search('', archives=self.archives, search_paths=search_paths), [])

        class Broken:
            has_fulltext_index = True

            def get_entry_by_path(self, p):
                raise RuntimeError('damaged')

        with self.assertRaises(RuntimeError):
            encyclopedias.search('cholera', archives=[(ZIM, Broken())], search_paths=lambda *a: ['Cholera'])

    def test_search_skips_a_file_without_an_index(self):
        empty = Archive({'Cholera': Entry('Cholera', CHOLERA)}, has_index=False)
        # Default search_paths respects has_fulltext_index; do not pass a custom one here.
        # Without libzim, the real _search_paths would import libzim, so stub that instead.
        with mock.patch.object(encyclopedias, '_search_paths', return_value=[]):
            hits = encyclopedias.search('cholera', archives=[(ZIM, empty)])
        self.assertEqual(hits, [])

    def test_read_caps_and_rejects_an_unsafe_or_missing_key(self):
        hit = encyclopedias.read('zim/' + ZIM + '/Water_disinfection', query='bleach', cap=200, archives=self.archives)
        self.assertEqual(hit['title'], 'Water disinfection')
        self.assertIn('two drops per litre', hit['text'])
        self.assertLessEqual(len(hit['text']), 200)
        self.assertIsNone(encyclopedias.read('zim/' + ZIM + '/../x', archives=self.archives))
        self.assertIsNone(encyclopedias.read('zim/' + ZIM + '/Missing', archives=self.archives))
        self.assertIsNone(encyclopedias.read('zim/other.zim/Cholera', archives=self.archives))

    def test_list_files_only_returns_real_zim_names(self):
        import tempfile, shutil
        tmp = Path(tempfile.mkdtemp())
        try:
            folder = tmp / 'collections'
            folder.mkdir()
            (folder / ZIM).write_bytes(b'not a real zim, just a name')
            (folder / 'notes.txt').write_text('x')
            self.assertEqual(encyclopedias.list_files(tmp), [ZIM])
        finally:
            shutil.rmtree(tmp)


class LinkedFiles(unittest.TestCase):
    """The same check as the /zim/ reader (library.zim_file): a file in collections/ that is really a link to somewhere
    outside it is not listed, searched, read or cited. A normal file inside collections/ works."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.lib = base / 'library-data'
        folder = self.lib / 'collections'
        folder.mkdir(parents=True)
        (folder / ZIM).write_bytes(b'fake zim inside the library')
        outside = base / 'elsewhere'
        outside.mkdir()
        (outside / 'linked.zim').write_bytes(b'fake zim outside the library')
        try:
            os.symlink(outside / 'linked.zim', folder / 'linked.zim')
        except (OSError, NotImplementedError):
            self.skipTest('cannot make a symlink here')
        self.opened = []
        self.saved_s = assistant.S

    def tearDown(self):
        assistant.S = self.saved_s
        self.tmp.cleanup()

    def opener(self, path):
        self.opened.append(Path(path).name)
        return mdwiki()

    def test_shared_check_refuses_the_link(self):
        safe_paths = encyclopedias.safe_paths   # the module engine/library.py zim_file() uses
        self.assertEqual(safe_paths.zim_file(self.lib, ZIM), self.lib / 'collections' / ZIM)
        with self.assertRaises(ValueError):
            safe_paths.zim_file(self.lib, 'linked.zim')
        self.assertIsNotNone(encyclopedias.zim_path(ZIM, self.lib))
        self.assertIsNone(encyclopedias.zim_path('linked.zim', self.lib))

    def test_not_listed(self):
        self.assertEqual(encyclopedias.list_files(self.lib), [ZIM])
        self.assertEqual([n for n, _, _ in encyclopedias.iter_archives(self.lib, opener=self.opener)], [ZIM])
        self.assertNotIn('linked.zim', self.opened)

    def test_not_searched(self):
        with mock.patch.object(encyclopedias, '_open_archive', side_effect=self.opener):
            hits = encyclopedias.search('cholera', root=self.lib, search_paths=search_paths)
        self.assertEqual(self.opened, [ZIM])
        self.assertTrue(hits)
        self.assertEqual({h['zim'] for h in hits}, {ZIM})

    def test_not_read(self):
        with mock.patch.object(encyclopedias, '_open_archive', side_effect=self.opener):
            self.assertIsNone(encyclopedias.read('zim/linked.zim/Cholera', root=self.lib))
            hit = encyclopedias.read('zim/' + ZIM + '/Cholera', root=self.lib)
        self.assertEqual(self.opened, [ZIM])
        self.assertEqual(hit['title'], 'Cholera')

    def test_not_cited(self):
        self.assertFalse(encyclopedias.key_ok('zim/linked.zim/A', root=self.lib))
        self.assertTrue(encyclopedias.key_ok('zim/' + ZIM + '/A', root=self.lib))
        # Chat checks citations against server.zim_names(), which is list_files() of the open library.
        assistant.S = mock.Mock()
        assistant.S.zim_names.side_effect = lambda: encyclopedias.list_files(self.lib)
        sess = assistant.Session()
        bad = sess.add(assistant.wiki_row({'zim_key': 'zim/linked.zim/Cholera', 'zim': 'linked.zim', 'title': 'Cholera'}))
        good = sess.add(assistant.wiki_row({'zim_key': 'zim/' + ZIM + '/Cholera', 'zim': ZIM, 'title': 'Cholera'}))
        _, valid, invalid = assistant.validate_citations(f'A [{bad}] B [{good}]', sess)
        self.assertEqual(valid, [good])
        self.assertEqual(invalid, [bad])


class ChatTools(unittest.TestCase):
    def setUp(self):
        self.arc = mdwiki()
        self.archives = [(ZIM, self.arc)]
        self.sess = assistant.Session()
        self.saved_s = assistant.S
        assistant.S = mock.Mock()
        assistant.S.catalog.return_value = {'by_id': {'fema-water': {'pages': 10, 'kind': 'pdf'}}}
        assistant.S.zim_names.return_value = [ZIM]

    def tearDown(self):
        assistant.S = self.saved_s

    def test_wiki_row_and_citation_validation(self):
        hits = encyclopedias.search('cholera', archives=self.archives, search_paths=search_paths)
        src = assistant.wiki_row(hits[0])
        self.assertEqual(src['kind'], 'zim')
        k = self.sess.add(src)
        answer, valid, invalid = assistant.validate_citations(f'Treat dehydration with ORS. [{k}][S99]', self.sess)
        self.assertEqual(valid, [k])
        self.assertEqual(invalid, ['S99'])
        # Grouped keys are split, then checked.
        answer, valid, invalid = assistant.validate_citations(f'ORS. [{k}, S99]', self.sess)
        self.assertIn(f'[{k}]', answer)
        self.assertIn('[S99]', answer)
        self.assertEqual(valid, [k])
        self.assertEqual(invalid, ['S99'])

    def test_wiki_row_carries_the_encoded_reader_path(self):
        hit = {'zim_key': 'zim/' + ZIM + '/100%_Juice', 'zim': ZIM, 'title': '100% Juice',
               'path': encyclopedias.ui_path(ZIM, '100%_Juice')}
        self.assertEqual(assistant.wiki_row(hit)['path'], 'zim/' + ZIM + '/100%25_Juice')
        # A hit without one gets it from its key, encoded the same way.
        row = assistant.wiki_row({'zim_key': 'zim/' + ZIM + '/X"onmouseover="alert(1)', 'zim': ZIM})
        self.assertEqual(row['path'], encyclopedias.ui_path(ZIM, 'X"onmouseover="alert(1)'))
        self.assertNotIn('"', row['path'])
        self.assertEqual(assistant.wiki_row({'zim_key': 'zim/' + ZIM + '/Why?', 'zim': ZIM})['path'], 'zim/' + ZIM + '/Why%3F')

    def test_invented_or_unknown_catalog_keys_are_rejected(self):
        self.sess.add({'doc_id': 'not-in-catalog', 'kind': 'pdf', 'page': 1, 'title': 'X'})
        self.sess.add({'doc_id': 'fema-water', 'kind': 'pdf', 'page': 99, 'title': 'Y'})  # page out of range
        _, valid, invalid = assistant.validate_citations('A [S1] B [S2]', self.sess)
        self.assertEqual(valid, [])
        self.assertEqual(invalid, ['S1', 'S2'])

    def _patch_zim(self, **kwargs):
        """Point the Chat helpers at this test's fake archives."""
        self.assertIs(encyclopedias, assistant.encyclopedias)
        return mock.patch.multiple(assistant.encyclopedias, **kwargs)

    def test_search_encyclopedia_registers_sources(self):
        hits = encyclopedias.search('cholera', archives=self.archives, search_paths=search_paths)
        with self._patch_zim(search=mock.Mock(return_value=hits)):
            text, summary = assistant.run_tool('search_encyclopedia', {'query': 'cholera'}, self.sess, [])
        self.assertEqual(summary['count'], 1)
        self.assertIn('[S1]', text)
        self.assertIn('Cholera', text)
        self.assertIn('S1', self.sess.sources)
        self.assertTrue(assistant.source_known(self.sess.sources['S1']))

    def test_read_encyclopedia_accepts_a_citation_key_and_caps_text(self):
        # First register a search hit, then read it as [S1].
        hits = encyclopedias.search('bleach', archives=self.archives, search_paths=search_paths)
        with self._patch_zim(search=mock.Mock(return_value=hits)):
            text, summary = assistant.run_tool('search_encyclopedia', {'query': 'bleach'}, self.sess, [])
        self.assertEqual(summary['count'], 1)
        self.assertIn('S1', self.sess.sources)
        hit = encyclopedias.read('zim/' + ZIM + '/Water_disinfection', query='bleach', cap=200, archives=self.archives)
        self.assertLessEqual(len(hit['text']), 200)
        with self._patch_zim(read=mock.Mock(return_value=hit)):
            text, summary = assistant.run_tool('read_encyclopedia', {'article': 'S1', 'query': 'bleach'}, self.sess, [])
        self.assertEqual(summary['title'], 'Water disinfection')
        self.assertIn('two drops per litre', text)
        self.assertNotIn('error', summary)

    def test_read_encyclopedia_unknown_article(self):
        with mock.patch.object(encyclopedias, 'read', return_value=None):
            text, summary = assistant.run_tool('read_encyclopedia', {'article': 'zim/missing.zim/X'}, self.sess, [])
        self.assertEqual(summary.get('error'), 'unknown')
        self.assertIn('not in this library', text)

    def test_a_citation_on_page_zero_is_rejected(self):
        """PDF pages are 1-based. 0 is a value, not 'no page', and must not pass as a real citation."""
        self.sess.add({'doc_id': 'fema-water', 'kind': 'pdf', 'page': 0, 'title': 'X'})
        _, valid, invalid = assistant.validate_citations('A [S1]', self.sess)
        self.assertEqual(valid, [])
        self.assertEqual(invalid, ['S1'])

    def test_encyclopedia_hits_never_raises(self):
        with mock.patch.object(encyclopedias, 'search', side_effect=RuntimeError('no collection could be searched')):
            self.assertEqual(assistant.encyclopedia_hits('cholera'), [])

    def test_tools_are_registered(self):
        names = [t['function']['name'] for t in assistant.TOOLS]
        self.assertIn('search_encyclopedia', names)
        self.assertIn('read_encyclopedia', names)
        self.assertIn('search_encyclopedia', assistant.SYSTEM)
        self.assertIn('read_encyclopedia', assistant.SYSTEM)


if __name__ == '__main__':
    unittest.main()
