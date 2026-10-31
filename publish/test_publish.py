"""Tests for publish.py: python publish/test_publish.py (from the toolkit folder)."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish as P  # noqa: E402


class Collect(unittest.TestCase):
    def test_collects_source_and_data(self):
        files = P.collect(P.config())
        for p in ('README.md', 'LICENSE', 'NOTICE', 'pyproject.toml', '.gitignore', 'docs/PITFALLS.md', 'vmsspatial/__init__.py', 'vmsspatial/selector.py',
                  'vmsspatial/resources/data_manifest.json', 'vmsspatial/resources/path1_order.json', 'vmsspatial/audit/review.py', 'js/sources.js', 'js/measure_cli.js',
                  'viewer/index.html', 'viewer/atlas.js', 'viewer/test/atlas.test.js', 'tests/test_selector_measures.py', 'publish/publish.py', 'scripts/component_contrast.py'):
            self.assertIn(p, files, p)
        if (P.TOOLKIT / 'data/manuscript/words.json.gz').is_file():
            self.assertIn('data/manuscript/words.json.gz', files)
        self.assertFalse(any('__pycache__' in p or p.endswith('.pyc') for p in files))
        optional = P.optional_data_paths()
        self.assertGreater(len(optional), 200)                                   # the 225 XML pages, the study files, the scans
        self.assertFalse(optional & set(files), sorted(optional & set(files))[:5])
        self.assertNotIn('publish_manifest.json', files)

    def test_no_local_paths_and_required_files(self):
        files = P.collect(P.config())
        problems, _ = P.verify(files, P.config())
        self.assertEqual(problems, [])
        self.assertNotEqual(P.verify({k: v for k, v in files.items() if k != 'LICENSE'}, P.config())[0], [])
        bad = dict(files)
        bad['x.py'] = ('# ' + str(Path.home())).encode()
        self.assertTrue(any('local path' in p for p in P.verify(bad, P.config())[0]))

    def test_gitattributes_marks_data_binary(self):
        text = P.gitattributes(P.config()).decode()
        self.assertIn('data/** -diff', text)
        self.assertIn('viewer/data/** -diff', text)

    def test_versions(self):
        d = date(2026, 10, 28)
        self.assertEqual(P.next_version(None, d), '2026.10.28')
        self.assertEqual(P.next_version('2026.10.28', d), '2026.10.28.2')
        self.assertEqual(P.next_version('2026.10.28.2', d), '2026.10.28.3')
        self.assertEqual(P.next_version('2026.10.27.5', d), '2026.10.28')


if __name__ == '__main__':
    unittest.main()
