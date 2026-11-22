#!/usr/bin/env python3
"""server.py as the HTTP server version, on port 8943 only, started and stopped here by PID. Never packaged.

  http_regression.py <python> <data folder> [--lan] [--fixture]"""
import json, os, signal, socket, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

PY, DATA = sys.argv[1], sys.argv[2]
LAN, FIXTURE = '--lan' in sys.argv, '--fixture' in sys.argv
ROOT = Path(__file__).resolve().parents[2]
PORT = 8943
BASE = f'http://127.0.0.1:{PORT}'
results = []


def note(name, ok, detail=''):
    ok = bool(ok)
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


opener = urllib.request.build_opener(NoRedirect)


def req(path, method='GET', headers=None, data=None, base=BASE):
    r = urllib.request.Request(base + path, method=method, headers=headers or {}, data=data)
    try:
        with opener.open(r, timeout=30) as x:
            return x.status, dict((k.lower(), v) for k, v in x.headers.items()), x.read()
    except urllib.error.HTTPError as e:
        return e.code, dict((k.lower(), v) for k, v in e.headers.items()), e.read()


def listening():
    return subprocess.run(['/usr/sbin/lsof', '-nP', f'-iTCP:{PORT}', '-sTCP:LISTEN', '-t'], capture_output=True, text=True).stdout.split()


assert not listening(), f'port {PORT} is taken'
env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'SURVIVAL_MODEL_BASE': 'http://127.0.0.1:9', 'SURVIVAL_DISABLE_INDEX_WATCH': '1'}
log = open(ROOT / 'derived' / 'app-build' / 'logs' / f'http-regression-{"lan" if LAN else Path(PY).parts[-3]}.out', 'w')
cmd = [PY, '-B', str(ROOT / 'server.py'), '--port', str(PORT), '--no-index', '--data', DATA] + (['--lan'] if LAN else [])
p = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd='/')
print('started pid', p.pid, ' '.join(cmd), flush=True)
try:
    for _ in range(600):
        try:
            if req('/api/health')[0] == 200:
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise SystemExit('never answered')
    s, h, d = req('/')
    note('home page', s == 200 and b'<' in d[:50] and 'content-security-policy' not in h, f'{s} {len(d)} bytes, no CSP added')
    for t in ('/ui/app.js', '/ui/words.js', '/ui/video-moments.js', '/ui/chat.js', '/ui/map.js', '/api/topics', '/api/library', '/api/shelves', '/sw.js', '/reader.css'):
        s, h, d = req(t)
        note(f'GET {t}', s == 200, f'{s} {len(d)} bytes')
    s, h, d = req('/api/map/info')
    info = json.loads(d)
    note('/api/map/info has what the map reads, and no local paths', s == 200 and all(k in info for k in ('national', 'version', 'datasets', 'aerial_detail', 'aerial_rev', 'terrain_circle')) and 'source' not in info['national'] and 'database' not in info['national'], json.dumps(info['national'])[:100])
    s, h, d = req('/api/chat', 'POST', {'Content-Type': 'application/json'}, b'{}')
    note('chat with no model is plain', s == 200 and b'model_unavailable' in d, d[:90].decode())
    s, h, d = req('/api/chat', 'POST', {'Content-Type': 'application/json', 'Origin': 'null'}, b'{}')
    note('POST with Origin null refused', s == 403, str(s))
    s, h, d = req('/api/health', headers={'Host': 'evil.example'})
    note('foreign Host refused', s == 403, str(s))
    for t in ('/canary-root.txt', '/video-auth.json', '/%2e%2e/canary-root.txt', '/catalog.json', '/tools/x', '/documents/x.info.json'):
        s, h, d = req(t)
        note(f'refused {t}', s in (400, 403, 404) and b'CANARY' not in d, str(s))
    if FIXTURE:
        s, h, d = req('/videos/a.mp4', headers={'Range': 'bytes=0-99'})
        note('video Range', s == 206 and h['content-range'] == f'bytes 0-99/{20 * 1024 * 1024}' and len(d) == 100, h.get('content-range'))
        s, h, d = req('/videos/a.mp4', headers={'Range': 'bytes=0-'})
        note('video open Range is not capped over HTTP', s == 206 and len(d) == 20 * 1024 * 1024, f'{len(d)} bytes')
        s, h, d = req('/documents/s.pdf', headers={'Range': 'bytes=0-9'})
        note('PDF over HTTP unchanged, whole and no Accept-Ranges', s == 200 and len(d) == 1024 * 1024 and 'accept-ranges' not in h, f'{s} {len(d)} bytes')
        s, h, d = req('/documents/big.bin')
        note('no flood gate over HTTP', s == 200 and len(d) == 40 * 1024 * 1024, f'{s} {len(d)} bytes')
        s, h, d = req('/documents/hl.txt')
        note('hard link refused', s == 404 and b'CANARY' not in d, str(s))
        s, h, d = req('/documents/plain.txt')
        note('plain file served', s == 200, str(s))
        tp = Path(DATA) / 'library-data' / 'courses' / 'c1' / 'resources' / 'tools'
        tp.mkdir(parents=True, exist_ok=True)
        (tp / 'index.html').write_bytes(b'<!doctype html><p>a real page')
        s, h, d = req('/courses/c1/resources/tools/index.html')
        note('a course page in a folder named tools opens', s == 200 and b'a real page' in d and h.get('content-security-policy', '').startswith('sandbox;'), str(s))
        s, h, d = req('/pages/s.html')
        csp = h.get('content-security-policy', '')
        note('saved page runs no code', s == 200 and csp.startswith('sandbox;') and "script-src 'none'" in csp and 'allow-' not in csp, csp[:60])
    else:
        s, h, d = req('/api/find?q=water')
        note('keyword search', s == 200 and json.loads(d).get('results'), f"{len(json.loads(d).get('results', []))} results")
    if LAN:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.connect(('10.255.255.255', 1))
        ip = sk.getsockname()[0]
        sk.close()
        lan = f'http://{ip}:{PORT}'
        key = (Path(DATA) / 'derived' / 'lan-key').read_text().strip()
        s, h, d = req('/', base=lan)
        note('--lan: another address without the key is refused', s == 403 and b'access link' in d, f'{s}')
        s, h, d = req('/?key=wrong', base=lan)
        note('--lan: wrong key refused', s == 403, str(s))
        s, h, d = req('/?key=' + key, base=lan)
        note('--lan: right key gets the cookie', s == 302 and 'sg_key=' in h.get('set-cookie', ''), f'{s}')
        s, h, d = req('/', headers={'Cookie': f'sg_key={key}'}, base=lan)
        note('--lan: cookie gets the page', s == 200, str(s))
        s, h, d = req('/')
        note('--lan: this computer needs no key', s == 200, str(s))
        rows = subprocess.run(['/usr/sbin/lsof', '-nP', f'-iTCP:{PORT}', '-sTCP:LISTEN'], capture_output=True, text=True).stdout
        note('--lan: bound to every address', f'*:{PORT}' in rows, rows.strip().splitlines()[-1][:80])
        out = (ROOT / 'derived' / 'app-build' / 'logs' / 'http-regression-lan.out').read_text()
        note('--lan: prints the phone link', 'Phones on this network' in out, '')
    else:
        rows = subprocess.run(['/usr/sbin/lsof', '-nP', f'-iTCP:{PORT}', '-sTCP:LISTEN'], capture_output=True, text=True).stdout
        note('bound to loopback only', f'127.0.0.1:{PORT}' in rows, rows.strip().splitlines()[-1][:80])
    files = subprocess.run(['/usr/sbin/lsof', '-nP', '-p', str(p.pid)], capture_output=True, text=True).stdout.lower()
    note('no model file open', 'bge-small' not in files and 'onnxruntime' not in files and 'model.onnx' not in files)
    conns = subprocess.run(['/usr/sbin/lsof', '-nP', '-a', '-p', str(p.pid), '-iTCP:19443'], capture_output=True, text=True).stdout
    note('nothing to port 19443', not conns.strip())
finally:
    os.kill(p.pid, signal.SIGTERM)
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        os.kill(p.pid, signal.SIGKILL)
        p.wait(5)
    print('stopped pid', p.pid, 'exit', p.returncode, flush=True)
time.sleep(0.2)
note('port closed again', not listening())
print(f'{sum(results)} of {len(results)} passed', flush=True)
sys.exit(0 if all(results) else 1)
