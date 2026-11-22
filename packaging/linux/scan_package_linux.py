"""Looks inside a built Lastbook .deb and exits 1 if it holds what must not ship (the Linux counterpart of scan_package_macos.py).

  python3 scan_package_linux.py Lastbook_<version>_amd64.deb [--terms-file FILE]

Refused: test code, the old window, model libraries, the Mac and Windows shells, the remote_storage module, machine names (FILE: private
words, one per line, kept out of this public script), /Users/... and /home/<name> paths, the household's area and working names in our
own files (ship_edits.json), native code that is not x86-64 or that links a library from outside the package and the system, a socket in
the local AI's runner, and in our own Python any network module outside the two ways out (setup's downloader and Check for updates) and
the engine's request handler, which the app runs with no port. roots.pem must be there: without it setup downloads nothing.
"""
import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the build invokes this scanner with -I
import i18n_catalogs  # noqa: E402

BAD_SEGMENTS = {'test', 'tests', 'testing', 'pytest', 'unittest', 'doctest', 'remote_storage', 'webview', 'bottle', 'proxy_tools', 'onnxruntime',
                'tokenizers', 'shell_windows', 'shell_macos', 'clr', 'clr_loader', 'pythonnet', 'lastbook_launcher', 'tkinter', 'PyInstaller',
                'objc', 'AppKit', 'Foundation', 'PyObjCTools', 'vendor-macos', 'fixture', 'real_data_check', 'http_regression', 'cdp', 'f2py', 'pypdfium2_cli'}
BAD_FILE = re.compile(r'(^|/)(test_[^/]*|[^/]*_test\.(py|pyc|so)|[^/]*_tests[^/]*\.so|[^/]*\.onnx|[^/]*\.gguf|mac_[^/]*|win_[^/]*)$', re.I)
TEST_MARKERS = [b'TEST-STUB', b'mac_offscreen', b'stub_chat', b'stub-chat']
ALLOWED_REMOTE = {'opt/lastbook/engine/library.py'}     # names remote_storage in the code that skips it when packaged
USER_PATH = re.compile(rb'/Users/[A-Za-z0-9._-]+|/home/(?!runner\b|user\b)[a-z_][a-z0-9_.-]+')
OUR_PY = re.compile(r'^opt/lastbook/(lastbook|server|retrieval|assistant|llm_local)\.py$|^opt/lastbook/(app|engine)/.*\.py$')
FIRST_PARTY = re.compile(r'^opt/lastbook/(web|content|app|engine|setup)/|^opt/lastbook/[^/]+\.py$')
NET_MODULES = {'socket', 'ssl', 'http.client', 'urllib.request', 'http.server', 'socketserver', 'asyncio', 'ftplib', 'smtplib', 'xmlrpc', 'requests', 'urllib3'}
NET_ALLOWED = {
    'opt/lastbook/engine/setup/download.py',   # setup's downloader: HTTPS to the allowlist, roots.pem only
    'opt/lastbook/engine/update.py',           # Check for updates, through download.py
    'opt/lastbook/server.py',                  # the engine's request handler; the app runs it through bridge.py and never opens its port
    'opt/lastbook/engine/setup/api.py',        # BaseHTTPRequestHandler for setup's routes, run the same way
    'opt/lastbook/engine/library.py',          # http.server's handler base, the same
    'opt/lastbook/assistant.py',               # the server version's chat model; the app's chat is llm_local over pipes
}
SOCKET_CALLS = re.compile(r'^(socket|connect|bind|listen|accept4?|getaddrinfo|gethostbyname\w*|sendto|recvfrom|curl_\w+|SSL_\w+)$')
SYSTEM_LIBS = re.compile(r'^(libc|libm|libdl|libpthread|librt|libstdc\+\+|libgcc_s|libgomp|libvulkan|ld-linux-x86-64|libz|libgstreamer-1\.0|libgstbase-1\.0|libglib-2\.0|libgobject-2\.0)\.so')


def bad_name(name):
    parts = re.split(r'[./]', name)
    return sorted((set(parts) & BAD_SEGMENTS) | {p for p in parts if p.endswith('_tests') or p.startswith('test_')})


def net_imports(source):
    out = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return sorted(m for m in out if m in NET_MODULES or m.split('.')[0] in {'requests', 'urllib3', 'xmlrpc'})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('deb', type=Path)
    ap.add_argument('--terms-file', type=Path)
    a = ap.parse_args()
    terms = []
    if a.terms_file and a.terms_file.is_file():
        terms = [t.strip().lower().encode() for t in a.terms_file.read_text(encoding='utf-8').splitlines() if t.strip()]
    print(f'private words checked: {len(terms)}' + ('' if terms else ' (no terms file: machine names NOT checked)'))
    here = Path(__file__).resolve().parent
    ship = json.loads((here.parent / 'ship_edits.json').read_text(encoding='utf-8'))
    household = re.compile('|'.join(ship['forbidden']).encode(), re.I)
    problems, remote_hits, user_paths, net_report = [], {}, {}, {}
    n_files = n_elf = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subprocess.run(['dpkg-deb', '-x', str(a.deb), str(root)], check=True)
        try:
            i18n_catalogs.check_assets(root / 'opt' / 'lastbook' / 'web', i18n_catalogs.generate())
        except (OSError, ValueError) as error:
            problems.append(f'localization: {error}')
        control = subprocess.run(['dpkg-deb', '-f', str(a.deb)], capture_output=True, text=True, check=True).stdout
        print(control.split('\nDescription')[0])
        packaged = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
        for rel in sorted(packaged):
            p = root / rel
            if p.is_symlink():
                target = p.readlink().as_posix()
                if target.startswith('/') or '..' in target:
                    problems.append(f'symlink out of the package: {rel} -> {target}')
                continue
            n_files += 1
            if not rel.startswith(('opt/lastbook/', 'usr/bin/lastbook', 'usr/share/applications/lastbook.desktop', 'usr/share/icons/hicolor/', 'usr/share/doc/lastbook/')):
                problems.append(f'file outside the places the package owns: {rel}')
            if bad_name(rel.removeprefix('opt/lastbook/')) or BAD_FILE.search(rel) or p.name in ship['never_ship']:
                problems.append(f'file not allowed: {rel}')
            data = p.read_bytes()
            low = data.lower()
            for t in terms:
                if t in low:
                    problems.append(f'private word #{terms.index(t) + 1} in {rel}')
            for m in TEST_MARKERS:
                if m in data:
                    problems.append(f'test marker {m.decode()} in {rel}')
            if b'remote_storage' in data and not rel.endswith('.pyc'):
                remote_hits[rel] = data.count(b'remote_storage')
            for u in set(USER_PATH.findall(data)):
                user_paths.setdefault(u.decode('ascii', 'replace'), []).append(rel)
            if FIRST_PARTY.search(rel):
                m = household.search(data)
                if m:
                    problems.append(f'household or working name in {rel}: {data[max(0, m.start() - 30):m.end() + 30]!r}')
            if OUR_PY.search(rel):
                mods = net_imports(data.decode('utf-8'))
                if mods:
                    net_report[rel] = mods
                    if rel not in NET_ALLOWED:
                        problems.append(f'network module in {rel}: {mods}')
            if data[:4] == b'\x7fELF':
                n_elf += 1
                head = subprocess.run(['readelf', '-h', str(p)], capture_output=True, text=True).stdout
                if 'X86-64' not in head:
                    problems.append(f'not x86-64: {rel}')
                dyn = subprocess.run(['readelf', '-d', str(p)], capture_output=True, text=True).stdout
                beside = {q.name for q in p.parent.iterdir()}
                for lib in re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', dyn):
                    if lib not in beside and not SYSTEM_LIBS.match(lib) and not rel.startswith('opt/lastbook/lib/'):
                        problems.append(f'links outside the package and the system: {rel} -> {lib}')
                if rel.startswith(('opt/lastbook/llm/', 'opt/lastbook/gst/')):     # the local AI's runner may not reach a network at all
                    syms = subprocess.run(['nm', '-D', '--undefined-only', str(p)], capture_output=True, text=True).stdout.split()
                    calls = sorted({s.split('@')[0] for s in syms if SOCKET_CALLS.match(s.split('@')[0])})
                    if calls:
                        problems.append(f'network calls in {rel}: {calls[:8]}')
        for rel in remote_hits:
            if rel not in ALLOWED_REMOTE:
                problems.append(f'remote_storage named in {rel}')
        for u, where in user_paths.items():
            if u.startswith('/Users/') or any(FIRST_PARTY.search(w) for w in where):
                problems.append(f'path of a person\'s folder {u} in {where[:3]}')
        if 'opt/lastbook/engine/setup/roots.pem' not in packaged:
            problems.append('missing from the package: opt/lastbook/engine/setup/roots.pem')
        for need in ('opt/lastbook/gst/libgstlastbooksrc.so', 'opt/lastbook/lastbook.py', 'opt/lastbook/app/main.py', 'opt/lastbook/app/shell_linux.py', 'opt/lastbook/app/ui_language.py',
                     'opt/lastbook/setup/manifest-v1.json', 'opt/lastbook/VERSION', 'usr/bin/lastbook', 'usr/share/applications/lastbook.desktop'):
            if need not in packaged:
                problems.append(f'missing from the package: {need}')
        llm = 'opt/lastbook/llm/lastbook-llm' in packaged
    print(f'files {n_files}, native binaries {n_elf}, local AI runner: {"included" if llm else "not included"}')
    print(f'network modules in our Python (allowed there): {net_report or "none"}')
    print(f'remote_storage string: {remote_hits or "nowhere"} (the module itself is refused above)')
    print(f'home-folder strings: { {u: w[:3] for u, w in user_paths.items()} or "none"}')
    for line in problems:
        print('PROBLEM:', line)
    print('SCAN FAILED' if problems else 'SCAN PASSED')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
