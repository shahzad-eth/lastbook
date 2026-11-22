"""Looks inside a built Lastbook.app, compressed Python modules included, and exits 1 if it holds what must not ship.

  python scan_package_macos.py Lastbook.app [--terms-file FILE]

Refused: test code, the old window, model libraries, the Windows shell, the remote_storage module, machine names, any
library linked from outside the package, and in our own files the household's area, working names and local files that ship_edits.json lists. FILE holds private words to refuse, one per line. They stay out of this script, which is public.
engine/library.py names remote_storage in the code that skips it when packaged: the shared engine has that string and nothing more,
so it is reported and allowed there alone.
"""
import argparse
import json
import re
import subprocess
import sys
import types
import zipfile
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

BAD_SEGMENTS = {'test', 'tests', 'testing', 'pytest', 'unittest', 'doctest', 'PyObjCTest', 'remote_storage', 'webview', 'bottle', 'proxy_tools',
                'onnxruntime', 'tokenizers', 'shell_windows', 'clr', 'clr_loader', 'pythonnet', 'lastbook_launcher', 'tkinter', 'PyInstaller',
                'mac_offscreen', 'mac_driver', 'mac_ui_check', 'mac_main_check', 'mac_package_smoke', 'mac_package_contents', 'mac_ax', 'test_bridge', 'fixture', 'real_data_check',
                'http_regression', 'win_app', 'win_driver', 'cdp'}
BAD_FILE = re.compile(r'(^|/)(test_[^/]*|[^/]*_test\.(py|pyc|so)|[^/]*\.onnx)$', re.I)
TEST_MARKERS = [b'TEST-STUB', b'mac_offscreen', b'stub_chat', b'stub-chat']
ALLOWED_REMOTE = {'engine.library'}
SYSTEM = ('/usr/lib/', '/System/', '@rpath/', '@loader_path/', '@executable_path/')
USER_PATH = re.compile(rb'/Users/[A-Za-z0-9._-]+')
SHIP = json.loads((Path(__file__).resolve().with_name('ship_edits.json')).read_text(encoding='utf-8'))
HOUSEHOLD = re.compile('|'.join(SHIP['forbidden']).encode(), re.I)
FIRST_PARTY = re.compile(r'(^|/)(web|content)/|^(main|server|retrieval|assistant|llm_local|bridge|ui_language|shell_macos|engine(\.\w+)?)$')
NETWORK = re.compile(r'^_(socket|connect|bind|listen|accept|getaddrinfo|gethostbyname|sendto|recvfrom)$|CFNetwork|CFSocket|CFStream|NSURLSession|NSURLConnection|NSStream|^_nw_')


def numbers(code):
    """The numbers in compiled code written out as text, in order: a float is stored as binary, so the area's coordinates would pass a look at the bytes."""
    out = []

    def walk(c):
        for k in (c.co_consts if isinstance(c, types.CodeType) else c):
            if isinstance(k, (int, float)) and not isinstance(k, bool):
                out.append(repr(k))
            elif isinstance(k, (tuple, frozenset, types.CodeType)):
                walk(k)
    walk(code)
    return ', '.join(out).encode()


def bad_name(name):
    parts = re.split(r'[./]', name)
    return sorted((set(parts) & BAD_SEGMENTS) | {p for p in parts if p.endswith('_tests') or p.startswith('test_')})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('app', type=Path)
    ap.add_argument('--terms-file', type=Path)
    a = ap.parse_args()
    terms = []
    if a.terms_file and a.terms_file.is_file():
        terms = [t.strip().lower().encode() for t in a.terms_file.read_text(encoding='utf-8').splitlines() if t.strip()]
    print(f'private words checked: {len(terms)}' + ('' if terms else ' (no terms file: machine names NOT checked)'))
    problems, remote_hits, user_paths = [], {}, {}

    def scan_bytes(where, data):
        low = data.lower()
        for t in terms:
            if t in low:
                problems.append(f'private word #{terms.index(t) + 1} in {where}')
        for m in TEST_MARKERS:
            if m in data:
                problems.append(f'test marker {m.decode()} in {where}')
        if b'remote_storage' in data:
            remote_hits[where] = data.count(b'remote_storage')
        for u in set(USER_PATH.findall(data)):
            user_paths.setdefault(u.decode('ascii', 'replace'), []).append(where)
        if FIRST_PARTY.search(where):
            m = HOUSEHOLD.search(data)
            if m:
                problems.append(f'household or working name in {where}: {data[max(0, m.start() - 30):m.end() + 30]!r}')

    n_files = n_macho = n_mods = 0
    executable = a.app / 'Contents' / 'MacOS' / 'Lastbook'
    minos = {}
    files = [p for p in sorted(a.app.rglob('*')) if p.is_file() and not p.is_symlink()]
    for p in files:
        rel = p.relative_to(a.app).as_posix()
        n_files += 1
        if bad_name(rel) or BAD_FILE.search(rel) or p.name in SHIP['never_ship']:
            problems.append(f'file not allowed: {rel}')
        data = p.read_bytes()
        scan_bytes(rel, data)
        if data[:4] in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe'):
            n_macho += 1
            archs = subprocess.run(['lipo', '-archs', str(p)], capture_output=True, text=True).stdout.split()
            if archs != ['arm64']:
                problems.append(f'not arm64 only ({archs}): {rel}')
            for line in subprocess.run(['otool', '-L', str(p)], capture_output=True, text=True).stdout.splitlines()[1:]:
                lib = line.strip().split(' (')[0]
                if not lib.startswith(SYSTEM):
                    problems.append(f'links outside the package: {rel} -> {lib}')
            if rel.startswith('Contents/Frameworks/llm/'):   # the local AI's runner may not reach a network at all
                calls = [n for n in subprocess.run(['nm', '-u', str(p)], capture_output=True, text=True).stdout.split() if NETWORK.search(n)]
                if calls:
                    problems.append(f'network calls in {rel}: {calls[:5]}')
            found = re.search(r'minos ([0-9.]+)', subprocess.run(['otool', '-l', str(p)], capture_output=True, text=True).stdout)
            if found:
                minos.setdefault(found.group(1), []).append(rel)
        if p.suffix == '.zip':
            with zipfile.ZipFile(p) as z:
                for name in z.namelist():
                    n_mods += 1
                    if bad_name(name.removesuffix('.pyc')):
                        problems.append(f'module not allowed: {rel}!{name}')
                    scan_bytes(f'{rel}!{name}', z.read(name))
    pkg = CArchiveReader(str(executable))
    modules = set()
    for name, entry in pkg.toc.items():
        if entry[-1] == 'z':
            pyz = pkg.open_embedded_archive(name)
            modules.update(pyz.toc)
            for mod in pyz.toc:
                n_mods += 1
                if bad_name(mod):
                    problems.append(f'module not allowed: {mod}')
                scan_bytes(mod, pyz.extract(mod, raw=True) or b'')
                if FIRST_PARTY.search(mod):
                    m = HOUSEHOLD.search(numbers(pyz.extract(mod) or ()))
                    if m:
                        problems.append(f'household area in the numbers of {mod}: {m.group(0).decode()}')
        else:
            if bad_name(name):
                problems.append(f'entry not allowed: {name}')
            scan_bytes(f'pkg:{name}', pkg.extract(name))
    for where in remote_hits:
        if where not in ALLOWED_REMOTE:
            problems.append(f'remote_storage named in {where}')
    roots = [a.app / 'Contents' / d / 'engine' / 'setup' / 'roots.pem' for d in ('Resources', 'Frameworks')]
    if not any(r.is_file() for r in roots):    # setup's downloader trusts only these roots; without them it downloads nothing
        problems.append('missing from the package: engine/setup/roots.pem')
    if 'ui_language' not in modules:
        problems.append('missing module from the package: ui_language')
    print(f'files {n_files}, native binaries {n_macho}, modules looked inside {n_mods}')
    print(f'remote_storage string: {remote_hits or "nowhere"} (the module itself is refused above)')
    print(f'/Users/... strings: { {u: w[:3] for u, w in user_paths.items()} or "none"}')
    print(f'minimum macOS named by binaries: { {v: len(w) for v, w in sorted(minos.items())} }')
    for line in problems:
        print('PROBLEM:', line)
    print('SCAN FAILED' if problems else 'SCAN PASSED')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
