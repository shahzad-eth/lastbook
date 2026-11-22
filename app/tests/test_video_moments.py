"""Named video positions persist across reloads without changing existing Saved items.

Runs the shipped JavaScript in Node with in-memory Storage and page stand-ins.
No browser, library, model or network is needed. Browser checks are separate.
"""
import shutil
import subprocess
import unittest
from pathlib import Path


class VideoMoments(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the video moment tests')
    def test_moment_progress_preserves_watched_choices(self):
        result = subprocess.run(
            [shutil.which('node'), str(Path(__file__).with_name('video_watched_test.mjs'))],
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"checks":9', result.stdout)

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the video moment tests')
    def test_saved_positions_and_storage_failures(self):
        result = subprocess.run(
            [shutil.which('node'), str(Path(__file__).with_name('video_moments_test.mjs'))],
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"checks":21', result.stdout)

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the video moment tests')
    def test_saved_read_errors_preserve_history_and_progress(self):
        result = subprocess.run(
            [shutil.which('node'), str(Path(__file__).with_name('saved_page_test.mjs'))],
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"checks":12', result.stdout)


if __name__ == '__main__':
    unittest.main()
