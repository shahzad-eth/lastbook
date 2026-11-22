#!/usr/bin/env python3
"""packaging/linux/run_source_linux.sh --check with stand-in GStreamer tools, so it needs no GStreamer and no real library.

  python3 -B app/tests/test_run_source_linux.py [-v]

The script runs from a copy in a temporary folder, so the plugin it "builds" lands there and never in the checkout's derived/gst/.
PATH holds only the stand-ins and the few system tools the script uses, so a gst-discoverer-1.0 installed on this computer is not seen.
Skipped where there is no bash, and on Windows even with Git Bash: the script is for Linux, and the stand-in folder is made of
symbolic links, which Windows refuses to an ordinary account. Never packaged."""
import os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'packaging' / 'linux' / 'run_source_linux.sh'
SYSTEM_TOOLS = ('dirname', 'realpath', 'mkdir', 'sed', 'head', 'tail', 'grep', 'find', 'sort', 'timeout')

# gcc writes the file named after -o; everything else succeeds.
GCC = '#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = -o ] && : > "$2"; shift; done\n'
OK = '#!/bin/sh\nexit 0\n'
# Says yes to every element except the ones listed in GST_MISSING.
INSPECT = '#!/bin/sh\n[ "$1" = --exists ] && case " $GST_MISSING " in *" $2 "*) exit 1;; esac\nexit 0\n'


@unittest.skipIf(sys.platform == 'win32', 'the script is for Linux; not run on Windows, where Git Bash would otherwise be found')
@unittest.skipUnless(shutil.which('bash') and all(shutil.which(t) for t in SYSTEM_TOOLS), 'needs bash and coreutils')
class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='lastbook-runsrc-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        linux = self.tmp / 'checkout' / 'packaging' / 'linux'
        (linux / 'gst').mkdir(parents=True)
        (linux / 'gst' / 'lastbooksrc.c').write_text('', encoding='utf-8')
        self.script = linux / SCRIPT.name
        shutil.copy(SCRIPT, self.script)
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        for tool in SYSTEM_TOOLS:
            (self.bin / tool).symlink_to(shutil.which(tool))
        for name, body in (('gcc', GCC), ('pkg-config', OK), ('gst-inspect-1.0', INSPECT), ('gst-launch-1.0', OK)):
            (self.bin / name).write_text(body, encoding='utf-8')
            (self.bin / name).chmod(0o755)
        self.data = self.tmp / 'LastbookData'
        (self.data / 'library-data' / 'videos' / 'clips').mkdir(parents=True)
        (self.data / 'library-data' / 'videos' / 'clips' / 'one.mp4').write_bytes(b'')

    def run_check(self, missing=''):
        env = {'PATH': str(self.bin), 'PYTHON': sys.executable, 'HOME': str(self.tmp), 'GST_MISSING': missing}
        return subprocess.run([shutil.which('bash'), str(self.script), '--check', str(self.data)],
                              env=env, capture_output=True, text=True, timeout=60)

    def test_no_discoverer(self):
        self.assertIsNone(shutil.which('gst-discoverer-1.0', path=str(self.bin)))
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('ok    ?  videos/clips/one.mp4', r.stdout)
        self.assertTrue((self.tmp / 'checkout' / 'derived' / 'gst' / 'libgstlastbooksrc.so').exists())

    def test_av1dec_is_enough(self):   # Ubuntu's gstreamer1.0-plugins-bad has av1dec and no dav1ddec
        r = self.run_check(missing='dav1ddec')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('AV1', r.stderr)

    def test_no_av1_decoder_warns(self):
        r = self.run_check(missing='dav1ddec av1dec')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('warning: no AV1 decoder (dav1ddec or av1dec)', r.stderr)


if __name__ == '__main__':
    unittest.main()
