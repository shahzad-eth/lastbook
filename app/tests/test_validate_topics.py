#!/usr/bin/env python3
"""tools/validate_topics.py against a small made-up library: no real library, no server, no port.

  python3 -B -m unittest app.tests.test_validate_topics

The tool is run the way a curator runs it, as its own process, so what is checked is what they would see: the lines it
prints and its exit code. The library is a catalog of two records and, where libzim can write one, a ZIM file of one page.
"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'tools' / 'validate_topics.py'
ZIM = 'tiny_en_test.zim'


def make_zim(path):
    """A ZIM file holding one page, 'Boil_water'. False where there is no libzim to write one. libzim prints its progress
    from C++, past Python's own output, so the writing is done in a child process whose output is not shown."""
    r = subprocess.run([sys.executable, '-B', __file__, '--zim', str(path)], capture_output=True)
    return r.returncode == 0 and Path(path).is_file()


def write_zim(path):
    from libzim.writer import Creator, Hint, Item, StringProvider

    class Page(Item):
        def get_path(self): return 'Boil_water'
        def get_title(self): return 'Boil water'
        def get_mimetype(self): return 'text/html'
        def get_contentprovider(self): return StringProvider('<p>Water</p>')
        def get_hints(self): return {Hint.FRONT_ARTICLE: True}

    with Creator(path).config_indexing(False, 'eng') as c:
        c.add_item(Page())
        c.add_metadata('Title', 'Tiny')


class Validate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.data = Path(cls.dir.name) / 'LastbookData'
        lib = cls.data / 'library-data'
        (lib / 'collections').mkdir(parents=True)
        # A title outside ASCII: the catalog and the guides are UTF-8 whatever the computer's own encoding is.
        cat = [{'id': 'doc-water', 'kind': 'pdf', 'pages': 10, 'title': 'Agua segura: “guía” para el niño'},
               {'id': 'metadata-video-1', 'kind': 'metadata', 'title': 'A video’s details'}]
        (lib / 'catalog.json').write_text(json.dumps(cat, ensure_ascii=False), encoding='utf-8')
        cls.zim = make_zim(lib / 'collections' / ZIM)
        cls.topics = Path(cls.dir.name) / 'topics'
        cls.topics.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def topic(self, name, **parts):
        f = self.topics / name
        f.write_text(json.dumps({'id': 'water', 'intro': 'Safe water, in “plain words”', **parts}, ensure_ascii=False), encoding='utf-8')
        return str(f)

    def run_tool(self, *args, env=None):
        e = {k: v for k, v in os.environ.items() if k != 'LASTBOOK_DATA'}
        e.update(env or {})
        r = subprocess.run([sys.executable, '-B', str(TOOL), *args], capture_output=True, text=True, encoding='utf-8', errors='replace', env=e, cwd=self.dir.name)
        return r.returncode, r.stdout + r.stderr

    def test_good_topic_passes_with_data_option(self):
        f = self.topic('good.json', prepare=[{'doc': 'doc-water', 'page': 3, 'label': 'Boil it'}],
                       limits=[{'text': 'Get help.', 'doc': 'doc-water', 'page': 10}])
        code, out = self.run_tool('--data', str(self.data), f)
        self.assertEqual(code, 0, out)
        self.assertIn('good.json: 2 references checked', out)
        self.assertIn('ERRORS 0', out)
        code, out = self.run_tool(f, '--data', str(self.data))                  # the option may come after the files
        self.assertEqual(code, 0, out)

    def test_data_folder_from_the_environment(self):
        f = self.topic('env.json', learn=[{'doc': 'doc-water', 'label': 'The whole manual'}])
        code, out = self.run_tool(f, env={'LASTBOOK_DATA': str(self.data)})
        self.assertEqual(code, 0, out)
        self.assertIn('env.json: 1 references checked', out)

    def test_each_kind_of_mistake_is_named(self):
        f = self.topic('bad.json', choices=[{'id': 'unsafe', 'read': [
            {'doc': 'doc-missing', 'label': 'x'},
            {'doc': 'doc-water', 'page': 11, 'label': 'x'},
            {'doc': 'metadata-video-1', 'label': 'x'},
            {'doc': 'doc-water', 'page': 2}]}])
        code, out = self.run_tool('--data', str(self.data), f)
        self.assertEqual(code, 1, out)
        for line in ('bad.json choice:unsafe: unknown doc doc-missing',
                     'bad.json choice:unsafe: page 11 out of range for doc-water (10)',
                     'bad.json choice:unsafe: use the video id, not metadata metadata-video-1',
                     'bad.json choice:unsafe: missing label for doc-water',
                     'ERRORS 4'):
            self.assertIn(line, out)

    def test_page_must_be_a_positive_integer(self):
        """The guide's `page` is a 1-based PDF page. 0, a string, a boolean and a fraction are author mistakes and must
        be named, not skipped or crashed on."""
        f = self.topic('pages.json', prepare=[
            {'doc': 'doc-water', 'page': 0, 'label': 'zero'},
            {'doc': 'doc-water', 'page': '3', 'label': 'text'},
            {'doc': 'doc-water', 'page': True, 'label': 'bool'},
            {'doc': 'doc-water', 'page': 3.5, 'label': 'fraction'}])
        code, out = self.run_tool('--data', str(self.data), f)
        self.assertEqual(code, 1, out)
        self.assertNotIn('Traceback', out)
        for page in ('0', "'3'", 'True', '3.5'):
            self.assertIn(f'page {page} is not a page number', out)
        self.assertIn('ERRORS 4', out)

    def test_related_must_name_existing_topics(self):
        """`related` is a list of topic ids the app turns into links; a missing id is silently dropped there, so the
        curator must hear about it here."""
        (self.topics / 'food.json').write_text(json.dumps({'id': 'food', 'intro': 'Food'}), encoding='utf-8')
        good = self.topic('related.json', related=['water', 'food', 'missing', 7])
        bad = self.topic('related-bad.json', related='water')
        code, out = self.run_tool('--data', str(self.data), good, bad)
        self.assertEqual(code, 1, out)
        self.assertIn("related.json related: unknown topic 'missing'", out)
        self.assertIn('related.json related: unknown topic 7', out)
        self.assertIn('related-bad.json related: not a list', out)
        self.assertIn('ERRORS 3', out)

    def test_no_library_says_so(self):
        empty = Path(self.dir.name) / 'empty'
        empty.mkdir(exist_ok=True)
        code, out = self.run_tool('--data', str(empty))
        self.assertNotEqual(code, 0)
        self.assertIn('No library at', out)
        self.assertIn('LASTBOOK_DATA', out)
        self.assertNotIn('Traceback', out)

    def test_zim_entry_found_without_a_server(self):
        if not self.zim:
            self.skipTest('no libzim here to write the small ZIM file')
        f = self.topic('zim.json', learn=[
            {'zim': f'zim/{ZIM}/Boil_water', 'title': 'Boil water', 'label': 'x'},
            {'zim': f'zim/{ZIM}/Not_here', 'title': 'Missing', 'label': 'x'},
            {'zim': 'zim/absent_en_all.zim/Boil_water', 'title': 'Another file', 'label': 'x'},
            {'zim': f'zim/../{ZIM}/Boil_water', 'title': 'Outside', 'label': 'x'}])
        code, out = self.run_tool('--data', str(self.data), f)
        self.assertEqual(code, 1, out)
        self.assertNotIn(f'fails zim/{ZIM}/Boil_water', out)                    # the entry that is there is not reported
        self.assertIn(f'ZIM path fails zim/{ZIM}/Not_here: no such entry', out)
        self.assertIn('ZIM path fails zim/absent_en_all.zim/Boil_water: absent_en_all.zim is not in this library', out)
        self.assertIn(f'ZIM path fails zim/../{ZIM}/Boil_water: not of the form', out)
        self.assertIn('ERRORS 3', out)
        self.assertNotIn(str(self.data), out)                                   # no full path of the library in what is printed


if __name__ == '__main__':
    if sys.argv[1:2] == ['--zim']:
        write_zim(sys.argv[2])
    else:
        unittest.main()
