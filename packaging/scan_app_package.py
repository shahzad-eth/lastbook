"""Looks inside a built Lastbook folder, including the archives in the exe, for what must not ship.

  python -I -B scan_app_package.py "<dist folder>" [--terms file] [--report file.json]

Fails (exit 1) on: test code, the macOS shell, pywebview, remote_storage as a module or file, any word from --terms,
user-folder paths in our own files, a native message channel in the code of the shell, and in our own files the household's
area, working names and local files that ship_edits.json lists (web/ and content/ must come from ship_app_files.py), and,
in the local AI's runner folder (_internal/llm), a missing runner, an RPC backend, or any program or library that imports a
network library (Winsock, WinHTTP, WinINet, URL Moniker, DNS). First-run setup: engine.setup.download is the only setup module
that may name a network module, the host names in it must be exactly SETUP_HOSTS and SETUP_SUFFIXES, and every address in the
bundled setup/manifest-v1.json must be on them.
The word "remote_storage" may appear only in engine.library, in the loader that refuses to run when packaged.
"""
import argparse
import json
import re
import sys
import types
import zipfile
from pathlib import Path

import pefile
from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

FIRST_PARTY_MODULES = re.compile(r'^(main|server|retrieval|assistant|llm_local|bridge|ui_language|shell_windows|engine(\..*)?)$')
BANNED_MODULES = re.compile(r'^(shell_macos|remote_storage|lastbook_launcher|test_bridge|fixture|http_regression|real_data_check|'
                            r'mac_driver|mac_offscreen|mac_ui_check|mac_main_check|win_app|win_driver|cdp|tests(\..*)?|app\.tests(\..*)?|'
                            r'webview(\..*)?|bottle|proxy_tools|objc(\..*)?|AppKit|WebKit|Foundation)$')
BANNED_FILES = re.compile(r'(?i)(^|[\\/])(tests|win_pages)[\\/]|\.ps1$|\.mjs$|win_suite|(^|[\\/])(remote_storage|shell_macos|lastbook_launcher)\b|vendor-macos|[\\/]webview[\\/](?!.*WebView2)')
THIRD_PARTY_TESTS = re.compile(r'(^|\.)(tests?|testing|conftest)(\.|$)')
USER_PATHS = re.compile(rb'(?i)[a-z]:[\\/]+users[\\/]+[a-z0-9_.-]+|/Users/[A-Za-z0-9_.-]+|/home/[a-z0-9_.-]+|/Volumes/[A-Za-z0-9_.-]+|/private/tmp')
ADDRESSES = re.compile(rb'\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b|\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b')
CHANNEL_NAMES = {'AddHostObjectToScript', 'add_WebMessageReceived', 'WebMessageReceived', 'PostWebMessageAsJson', 'PostWebMessageAsString', 'add_script_message_handler', 'addScriptMessageHandler_name_'}
EXPECTED_REMOTE_NAME = 'engine.library'
# What first-run setup may reach (engine/setup/download.py ALLOWED_HOSTS and ALLOWED_SUFFIXES). A change there must be made here too.
SETUP_HOSTS = {'downloads.lastbook.org', 'huggingface.co', 'cas-bridge.xethub.hf.co'}
SETUP_SUFFIXES = {'.hf.co'}
# http.server is left out: setup's handler class (engine.setup.api), like server.py's, answers the window in-process and listens on nothing.
NET_MODULES = {'http.client', 'socket', '_socket', 'ssl', '_ssl', 'urllib.request', 'asyncio', 'ftplib', 'smtplib', 'xmlrpc.client'}
# A host name in the code: dotted words ending in a top-level domain (so 'x.part.json' and '.tmp' are file names, not hosts).
TLDS = r'(?:com|org|net|co|dev|io|app|ai|cloud|info|me|xyz|edu|gov|us|uk|de|eu|ca|ws|sh|to|link|site|tech|online)'
HOST_NAME = re.compile(r'^(?:[a-z0-9-]+\.)+' + TLDS + r'$')
HOST_SUFFIX = re.compile(r'^\.(?:[a-z0-9-]+\.)*' + TLDS + r'$')
LLM_DIR = ('_internal\\llm\\', '_internal/llm/')
NETWORK_DLLS = re.compile(r'(?i)^(ws2_32|wsock32|mswsock|winhttp|wininet|urlmon|dnsapi|iphlpapi|netapi32|rpcrt4|webio|httpapi|winsock|wsnmp32)\.dll$')
SHIP = json.loads((Path(__file__).resolve().with_name('ship_edits.json')).read_text(encoding='utf-8'))
HOUSEHOLD = re.compile('|'.join(SHIP['forbidden']).encode(), re.I)


def const_strings(code, out):
    for k in code.co_consts:
        if isinstance(k, str):
            out.add(k)
        elif isinstance(k, (tuple, frozenset)):
            out.update(x for x in k if isinstance(x, str))
        elif isinstance(k, types.CodeType):
            const_strings(k, out)


def host_allowed(host):
    host = (host or '').lower()
    return host in SETUP_HOSTS or any(host.endswith(x) and len(host) > len(x) for x in SETUP_SUFFIXES)


def code_names(code, out):
    out.update(code.co_names)
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            code_names(const, out)


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


def context(data, m):
    return re.sub(rb'[^\x20-\x7e]', b'.', data[max(0, m.start() - 40):m.end() + 40]).decode()


class Scan:
    def __init__(self, terms):
        self.terms = [(t, re.compile(re.escape(t).encode(), re.I)) for t in terms]
        self.fails, self.review, self.notes = [], [], []
        self.modules, self.files, self.third_party_tests = [], [], []
        self.remote_refs = []
        self.setup_hosts = None
        self.items = 0

    def text(self, name, data, first_party):
        self.items += 1
        data = data or b""
        views = [data]
        if b'\x00' in data[:65536] or b'\x00' in data[-65536:]:
            views.append(data.replace(b'\x00', b''))    # UTF-16 strings in binaries
        for view in views:
            for term, rx in self.terms:
                m = rx.search(view)
                if m:
                    # the listed word is left out of the report, which may be shared
                    self.fails.append(f'listed word {self.terms.index((term, rx)) + 1} in {name}: at byte {m.start()}')
            for m in re.finditer(rb'remote_storage', view):
                if name == EXPECTED_REMOTE_NAME:
                    self.remote_refs.append(context(view, m))
                else:
                    self.fails.append(f'remote_storage in {name}: {context(view, m)}')
            if first_party:
                for m in HOUSEHOLD.finditer(view):
                    self.fails.append(f'household or working name in {name}: {context(view, m)}')
                for m in USER_PATHS.finditer(view):
                    self.fails.append(f'user path in {name}: {context(view, m)}')
                for m in ADDRESSES.finditer(view):
                    self.review.append(f'private address form in {name}: {context(view, m)}')
            else:
                m = USER_PATHS.search(view)
                if m:
                    self.notes.append(f'user-style path in third-party {name}: {context(view, m)}')

    def module(self, name, raw):
        self.modules.append(name)
        if BANNED_MODULES.match(name):
            self.fails.append(f'banned module: {name}')
        if THIRD_PARTY_TESTS.search(name):
            self.third_party_tests.append(name)
        self.text(name, raw, bool(FIRST_PARTY_MODULES.match(name)))


def scan_exe(scan, path):
    pkg = CArchiveReader(str(path))
    for name, entry in pkg.toc.items():
        typecode = entry[-1] if isinstance(entry[-1], str) else entry[4]
        if typecode == 'z':
            pyz = pkg.open_embedded_archive(name)
            for mod in pyz.toc:
                code = pyz.extract(mod)
                scan.module(mod, pyz.extract(mod, raw=True))
                if isinstance(code, types.CodeType) and FIRST_PARTY_MODULES.match(mod):
                    for m in HOUSEHOLD.finditer(numbers(code)):
                        scan.fails.append(f'household area in the numbers of {mod}: {m.group(0).decode()}')
                    names = set()
                    code_names(code, names)
                    if mod.startswith('engine.setup') and mod != 'engine.setup.download' and names & NET_MODULES:
                        scan.fails.append(f'network module in {mod}: {sorted(names & NET_MODULES)} (only engine.setup.download may)')
                    if mod == 'engine.setup.download':
                        strs = set()
                        const_strings(code, strs)
                        hosts = {x for x in strs if HOST_NAME.match(x)}
                        suffixes = {x for x in strs if HOST_SUFFIX.match(x)}
                        scan.setup_hosts = sorted(hosts | suffixes)
                        if hosts != SETUP_HOSTS or suffixes != SETUP_SUFFIXES:
                            scan.fails.append(f'engine.setup.download names hosts {sorted(hosts)} {sorted(suffixes)}, '
                                              f'expected {sorted(SETUP_HOSTS)} {sorted(SETUP_SUFFIXES)}')
                    found = names & CHANNEL_NAMES
                    if found:
                        scan.fails.append(f'native channel in {mod}: {sorted(found)}')
                    if mod == 'shell_windows':
                        for need in ('IsWebMessageEnabled', 'AreHostObjectsAllowed', 'NewWindowRequested'):
                            if need not in names:
                                scan.fails.append(f'shell_windows does not set {need}')
        else:
            data = pkg.extract(name)
            data = data if isinstance(data, bytes) else b''
            scan.text(f'exe:{name}', data, FIRST_PARTY_MODULES.match(name) is not None)
            if BANNED_MODULES.match(name) or BANNED_FILES.search(name):
                scan.fails.append(f'banned entry in the exe: {name}')
            scan.notes.append(f'exe entry {name} type {typecode} {len(data)} bytes')


def pe_imports(data):
    """The DLLs a Windows program or library names in its import tables, delay-loaded ones too."""
    pe = pefile.PE(data=data, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
                                           pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
    out = set()
    for attr in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT'):
        for e in getattr(pe, attr, []):
            out.add(e.dll.decode('ascii', 'replace'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder')
    ap.add_argument('--terms')
    ap.add_argument('--report')
    a = ap.parse_args()
    root = Path(a.folder)
    terms = []
    if a.terms:
        terms = [t.strip() for t in open(a.terms, encoding='utf-8') if t.strip() and not t.startswith('#')]
    scan = Scan(terms)
    scan_exe(scan, root / 'Lastbook.exe')
    if b'X utf8' not in (root / 'Lastbook.exe').read_bytes():
        scan.fails.append('the exe does not carry the UTF-8 option')
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        rel = str(path.relative_to(root))
        scan.files.append(rel)
        if BANNED_FILES.search(rel) and 'webview2' not in rel.lower():
            scan.fails.append(f'banned file: {rel}')
        if path.name in SHIP['never_ship']:
            scan.fails.append(f'local file that never ships: {rel}')
        ours = rel.startswith(('_internal\\web\\', '_internal\\content\\', '_internal/web/', '_internal/content/'))
        data = path.read_bytes()
        scan.text(rel, data, ours)
        if rel.startswith(LLM_DIR):           # the local AI's runner may not reach a network at all
            if 'rpc' in path.name.lower():
                scan.fails.append(f'RPC backend in the runner folder: {rel}')
            if path.suffix.lower() in ('.exe', '.dll'):
                dlls = pe_imports(data)
                net = sorted(d for d in dlls if NETWORK_DLLS.match(d))
                if net:
                    scan.fails.append(f'network library imported by {rel}: {net}')
                scan.notes.append(f'llm {path.name} imports {sorted(dlls)}')
                m = USER_PATHS.search(data)
                if m and path.name.lower() in ('libc++.dll', 'libunwind.dll', 'libomp.dll'):
                    scan.notes.append(f'build path of the C++ runtime (llvm-mingw release) in {rel}: {context(data, m)}')
                elif m:                                # what packaging/llm/build_llm_windows.sh compiles
                    scan.fails.append(f'user path in {rel}: {context(data, m)}')
        if path.suffix == '.zip':
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    scan.text(f'{rel}!{name}', z.read(name), False)
    need = ['Lastbook.exe', 'Lastbook.exe.config', '_internal/webview2/Microsoft.Web.WebView2.Core.dll', '_internal/webview2/Microsoft.Web.WebView2.WinForms.dll',
            '_internal/webview2/WebView2Loader.dll', '_internal/web/index.html', '_internal/llm/lastbook-llm.exe', '_internal/llm/libllama.dll',
            '_internal/llm/ggml-vulkan.dll', '_internal/llm/ggml-cpu-x64.dll', '_internal/setup/manifest-v1.json',
            '_internal/web/setup.html', '_internal/web/setup.js', '_internal/web/setup.css', '_internal/engine/setup/roots.pem',
            '_internal/zim-9.dll']   # ZIM wikis: PyInstaller leaves libzim out if it fails to load at build time (its .pyd is checked below)
    sq = root / '_internal' / 'sqlite3.dll'      # SQLite 3.50.3 or later (CVE-2025-7709, FTS5; packs bring search databases)
    if not sq.is_file():
        scan.fails.append('missing from the package: _internal/sqlite3.dll')
    elif sys.platform == 'win32':
        import ctypes
        lib = ctypes.CDLL(str(sq), winmode=0x8)    # LOAD_WITH_ALTERED_SEARCH_PATH: this file, by its full path
        lib.sqlite3_libversion.restype = ctypes.c_char_p
        v = lib.sqlite3_libversion().decode()
        scan.notes.append(f'sqlite3.dll is SQLite {v}')
        if tuple(int(x) for x in v.split('.')[:3]) < (3, 50, 3):
            scan.fails.append(f'_internal/sqlite3.dll is SQLite {v}; 3.50.3 or later is needed (CVE-2025-7709)')
    if not list((root / '_internal').glob('libzim.cp3*-win_amd64.pyd')):
        scan.fails.append('missing from the package: _internal/libzim.cp3*-win_amd64.pyd')
    for rel in need:
        if not (root / rel).is_file():
            scan.fails.append(f'missing from the package: {rel}')
    for mod in ('main', 'server', 'bridge', 'ui_language', 'shell_windows', 'engine.library', 'llm_local', 'engine.setup.api', 'engine.setup.download', 'clr'):
        if mod not in scan.modules and not any(n.endswith(f'exe:{mod}') for n in scan.notes):
            if mod != 'main':
                scan.fails.append(f'module missing from the package: {mod}')
    if scan.setup_hosts is None:
        scan.fails.append('engine.setup.download was not found in the archive, so its hosts were not checked')
    mf = root / '_internal' / 'setup' / 'manifest-v1.json'
    setup_urls = []
    if mf.is_file():
        def urls(v):
            if isinstance(v, dict):
                for x in v.values():
                    yield from urls(x)
            elif isinstance(v, list):
                for x in v:
                    yield from urls(x)
            elif isinstance(v, str) and '://' in v:
                yield v
        import urllib.parse
        for u in urls(json.loads(mf.read_text(encoding='utf-8'))):
            setup_urls.append(u)
            parts = urllib.parse.urlsplit(u)
            if parts.scheme != 'https' or not host_allowed(parts.hostname):
                scan.fails.append(f'setup manifest address not on the allowed hosts: {u}')
    size = sum((root / f).stat().st_size for f in scan.files)
    result = {'folder': str(root), 'files': len(scan.files), 'bytes': size, 'modules': len(scan.modules), 'items_scanned': scan.items, 'terms': len(terms),
              'fails': scan.fails, 'review': sorted(set(scan.review)), 'third_party_test_modules': scan.third_party_tests,
              'remote_storage_refs_in_engine_library': scan.remote_refs, 'setup_hosts': scan.setup_hosts, 'setup_manifest_urls': setup_urls, 'notes': sorted(set(scan.notes))[:200]}
    if a.report:
        Path(a.report).write_text(json.dumps({**result, 'all_modules': sorted(scan.modules), 'all_files': scan.files}, indent=1), encoding='utf-8')
    print(f'{len(scan.files)} files, {size / 1048576:.0f} MiB, {len(scan.modules)} modules in the archive, {scan.items} items scanned, {len(terms)} listed words')
    print(f'fails: {len(scan.fails)}')
    for f in scan.fails[:60]:
        print('  FAIL', f)
    print(f'third-party test modules: {len(scan.third_party_tests)}')
    print(f'remote_storage mentions in engine.library: {len(scan.remote_refs)}')
    print(f'setup hosts in engine.setup.download: {scan.setup_hosts}; manifest addresses: {len(setup_urls)}')
    for r in sorted(set(scan.review))[:20]:
        print('  review', r)
    return 1 if scan.fails else 0


if __name__ == '__main__':
    sys.exit(main())
