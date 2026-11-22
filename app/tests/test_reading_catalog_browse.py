"""Regression checks for browsing the exported offline reading catalog."""
import json
import tempfile
import unittest
from pathlib import Path
from tools.export_reading_catalog import export


class ReadingCatalogBrowseTests(unittest.TestCase):
    def test_format_and_title_initial_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            output = root / "catalog.html"
            catalog.write_text(json.dumps([
                {"kind": "pdf", "title": "Alpha", "collection": "Z"},
                {"kind": "html", "title": "Beta", "collection": "A"},
                {"kind": "pptx", "title": "Another title", "collection": "B"},
            ]), encoding="utf-8")
            self.assertEqual(export(catalog, output), 3)
            page = output.read_text(encoding="utf-8")
            for expected in ('id="type"', 'id="letter"', 'All formats', 'All titles',
                             'option value="PDF">PDF</option>', 'option value="HTML">HTML</option>', 'option value="PPTX">PPTX</option>',
                             'r.cells[1].textContent', 'r.cells[2].textContent===type.value',
                             'title.charAt(0).toLocaleUpperCase()===letter.value',
                             "r.textContent.toLocaleLowerCase().includes(v)",
                             "n+' of '+rs.length+' titles'"):
                self.assertIn(expected, page)
            self.assertLess(page.index('<td>A</td><td>Beta'), page.index('<td>B</td><td>Another title'))
            self.assertLess(page.index('id="type"'), page.index("const q=document.getElementById"))
            self.assertLess(page.index('id="letter"'), page.index("const q=document.getElementById"))
            self.assertIn("for(const control of [q,type,letter])", page)

    def test_empty_catalog_keeps_filters_and_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            output = root / "catalog.html"
            catalog.write_text("[]", encoding="utf-8")
            self.assertEqual(export(catalog, output), 0)
            page = output.read_text(encoding="utf-8")
            self.assertIn('<tbody></tbody>', page)
            self.assertIn('new Set(rs.map(', page)
            self.assertIn("filter();", page)
            self.assertIn('id="type"', page)
            self.assertIn('id="letter"', page)


if __name__ == "__main__":
    unittest.main()
