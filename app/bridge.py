"""No-port transport between the app's window and the engine. Nothing in here opens a socket.

A request from the web view runs the engine's unchanged request Handler on a worker thread, over in-memory streams.
Both shells use this one file; the platform parts live in shell_windows.py and shell_macos.py.

  mode='stream'   (macOS, WKURLSchemeHandler)  start(...) calls a Sink piece by piece, with backpressure.
  mode='buffer'   (Windows, WebResourceRequested)  fetch(...) hands back one whole Response. WebView2 has no way to
                  stream a response, so chat becomes small polls (top_script and /__bridge/stream/) and video is capped.

What holds on both:
  - Lanes. The app's own small requests, everyone else's /api/, page renders, chat and large files each have their own workers
    and their own byte budget, so a flood of one never takes a worker or a byte from another. The two /api/ lanes also add workers
    when a request has waited, because a slow answer mostly sleeps: it must not hold up a quick one behind it.
  - In flight. LANES below sums to TOTAL_INFLIGHT, the most bytes this process can be holding between the engine and
    the web view. What the web view keeps after it has them is its own, and has to be measured in the real window.
  - The flood gate. An answer over BIG_BODY reaches only a navigation the app itself started (give_ticket).
  - POST. Every POST needs the key made at launch, which only the app's top frame gets (top_script).
  - The key also marks the top frame's own /api/ reads, which is how they keep a lane that a saved page cannot get into.
  - No PDF ever reaches the web view. A PDF can carry scripts and both platforms' viewers run them, so what arrives is a page of images PDFium has drawn (_answer_pdf).
"""
import hashlib
import html
import io
import json
import os
import queue
import re
import secrets
import tempfile
import threading
import time
import traceback
import urllib.parse
from collections import deque

import ui_language

ORIGIN_WINDOWS = 'https://lastbook.invalid'
ORIGIN_MAC = 'lastbook://app'

MiB = 1024 * 1024
CHUNK = MiB                         # largest piece handed to a stream Sink
VIDEO_PIECE = {'stream': 8 * MiB,   # most bytes one video Range answer holds. The player asks for the rest.
               'buffer': 4 * MiB}   # 2.38 MB is the largest request seen from a player, and a 256 KB cap broke playback.
BIG_BODY = 32 * MiB                 # above this, only a navigation the app started gets the whole answer
WHOLE_MAX = 256 * MiB               # the largest answer of any kind. The largest real page is 44 MB, and PDFs and videos come in pieces. Handing over one answer costs far more than its size, see shell_windows.py.
SPOOL_AT = 16 * MiB                 # buffer mode: a larger generated body goes to a temp file, not memory
PER_REQUEST = 8 * MiB               # stream mode: most unacknowledged bytes for one request
TICKET_LIFE = 30
MAX_POST = 256 * 1024               # the engine's own limit on a chat request is 200,000 bytes
MAX_STREAMS = 4                     # chat polls at one time
STREAM_IDLE = 120                   # a poll stream nobody has asked about for this long is cancelled
POLL_WAIT = 15
KEY_HEADER = 'x-lastbook-key'

# name: (workers, most waiting, byte budget). Budgets are separate on purpose: one shared pool would let large files starve /api/.
LANES = {
    'small': (8, 5000, 24 * MiB),    # the app's own files, and /api/ asked for with the key: the top frame's own script
    'guest': (8, 5000, 24 * MiB),    # /api/ with no key: a saved page, a worker, an <img> the top frame's script did not make
    'render': (2, 500, 8 * MiB),     # PDF page images: PDFium runs one at a time anyway, so more workers would only sit waiting
    'chat': (8, 32, 8 * MiB),        # long-lived: must not hold a small worker for the length of an answer
    'large': (6, 1000, 64 * MiB),    # video, PDF, saved pages, encyclopedia entries
}
TOTAL_INFLIGHT = sum(v[2] for v in LANES.values())
GROW_TO = {'small': 48, 'guest': 24}    # most workers once requests are kept waiting. The byte budgets above do not grow with them.
GROW_AFTER = 0.05                       # seconds a request waits before a lane adds workers for what is waiting
SHRINK_AFTER = 10                       # seconds an added worker sits idle before it goes

PASS_HEADERS = {'range', 'content-type', 'accept'}  # all a page can send the engine, besides the mapped Origin. The key never goes on.
FRAME_PREFIXES = ('/documents/', '/pages/', '/videos/', '/videos-external/', '/transcripts/', '/metadata/videos/', '/courses/', '/collections/', '/assets/', '/zim/')
FILE_PREFIXES = tuple(p for p in FRAME_PREFIXES if p != '/zim/')
HOP = {'connection', 'keep-alive', 'transfer-encoding', 'te', 'upgrade', 'proxy-connection', 'trailer'}
DROP = HOP | {'server', 'date'}
VIDEO_SUFFIXES = ('.mp4', '.webm', '.mkv')
ENGINE_RANGE = re.compile(r'bytes=(\d+)-(\d*)')   # read as the engine reads it: match at the start, so a second range is ignored there too
PDF_PAGE = re.compile(r'[?&]pdf-page=(\d+)(?:&|$)')
PDF_WIDTH = 1400                    # the longer side of a drawn page
PDF_MAX_PAGES = 20000               # the most one viewer page lists
PDF_SIZES_KEPT = 16
PDF_NOTICE = b'This PDF could not be shown here.'
BAD_TARGET = re.compile(r'[\x00-\x20\x7f]')
RENDER = re.compile(r'/api/page/[^/]+/\d+\.png$')
TOO_LARGE = b'This file is too large to show here.'
GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)

TOP_SCRIPT = r"""(() => {
  if (window.top !== window || window.origin === 'null') return;  // a saved page, in a frame or not, gets nothing
  if (__UI_LANGUAGE__) window.LB_DESKTOP_LANGUAGE = true;
  // Asking for a location goes to the system's location service, which can ask the network. The map's button shows this message.
  const none = { getCurrentPosition(ok, no) { if (no) setTimeout(no, 0, { code: 1, message: 'Lastbook stays offline and does not ask where you are.' }) }, watchPosition() { return 0 }, clearWatch() { } };
  try { Object.defineProperty(Navigator.prototype, 'geolocation', { get() { return none }, configurable: false }) } catch { }
  const KEY = '__KEY__', POLL = __POLL__, own = location.protocol + '//' + location.host;
  const real = window.fetch.bind(window);
  const mine = u => u.protocol + '//' + u.host === own;
  const keyed = (req) => { const headers = new Headers(req.headers); headers.set('X-Lastbook-Key', KEY); return real(new Request(req, { headers })) };
  const call = (p, body) => real('/__bridge/stream' + p, { method: 'POST', body: body || '', headers: { 'Content-Type': 'application/octet-stream', 'X-Lastbook-Key': KEY } });
  const aborted = () => new DOMException('The operation was aborted.', 'AbortError');
  async function polled(body, signal) {
    if (signal && signal.aborted) throw aborted();
    const s = await call('/start', body);
    if (!s.ok) return s;
    const id = s.headers.get('X-Bridge-Stream');
    let ctl, over = false;
    const cancel = () => { if (!over) { over = true; call('/' + id + '/cancel').catch(() => { }) } };
    const stream = new ReadableStream({
      start(c) { ctl = c },
      async pull(c) {
        for (; ;) {
          if (over) return;
          const r = await call('/' + id + '/next');
          if (over) return;
          const b = new Uint8Array(await r.arrayBuffer());
          if (over) return;
          if (b.length) c.enqueue(b);
          if (r.headers.get('X-Bridge-End')) { over = true; c.close(); return }
          if (b.length) return;
        }
      },
      cancel() { cancel() }
    });
    if (signal) signal.addEventListener('abort', () => { cancel(); try { ctl.error(aborted()) } catch { } });
    return new Response(stream, { status: +s.headers.get('X-Bridge-Status'), headers: JSON.parse(s.headers.get('X-Bridge-Headers') || '[]') });
  }
  window.fetch = async function (input, init) {
    const req = new Request(input, init);
    const u = new URL(req.url);
    if (!mine(u)) return real(req);
    if (req.method !== 'POST') return u.pathname.startsWith('/api/') ? keyed(req) : real(req);
    if (POLL && u.pathname === '/api/chat') return polled(await req.arrayBuffer(), req.signal);
    return keyed(req);
  };
})();
"""

def headers_dict(headers):
    """For a platform call that takes a dictionary. Repeated names are joined, as HTTP allows."""
    out = {}
    for k, v in headers:
        out[k] = f'{out[k]}, {v}' if k in out else v
    return out


class Sink:
    """What the macOS shell implements. All three run on a worker thread, in order, for one request, so post them to the
    main thread in order. There, check `exchange.stopped` before touching the task, and never touch it once stopped."""

    def head(self, status, reason, headers):
        """headers: a list of (name, value)."""

    def data(self, chunk, ack):
        """chunk: bytes, at most CHUNK. Call ack() once the web view has them, or when dropping them. Until then they
        count against the lane's budget. Calling ack twice, or after a cancel, is harmless."""

    def finish(self, ok):
        """The last call. ok False: the answer stopped short (didFailWithError, not didFinish)."""


class Response:
    """What fetch hands the Windows shell. Exactly one of body and path is set, or neither for an empty answer."""

    def __init__(self, status, reason, headers, body=None, path=None, delete=False, release=None):
        self.status, self.reason, self.headers = status, reason, headers
        self.body, self.path, self.delete = body, path, delete   # delete: a temp file; open it with FileOptions.DeleteOnClose
        self._release = release
        self.lane = None

    def release(self):
        """Call once the bytes are in the web view's hands, or if the answer is dropped. Calling it twice is harmless."""
        r, self._release = self._release, None
        if r:
            r()


class _Budget:
    def __init__(self, cap, per_request=None):
        self.cap, self.per_request = cap, per_request
        self.used = self.peak = 0
        self.cond = threading.Condition()

    def _fits(self, n, ex):
        if self.used + n > self.cap and self.used:   # `and self.used`: a piece bigger than the whole budget goes alone
            return False
        return not (self.per_request and ex.held and ex.held + n > self.per_request)

    def _take(self, n, ex):
        self.used += n
        ex.held += n
        self.peak = max(self.peak, self.used)

    def acquire(self, n, ex):
        with self.cond:
            while not ex.stopped and not self._fits(n, ex):
                self.cond.wait(0.25)
            if ex.stopped:
                raise BrokenPipeError
            self._take(n, ex)

    def try_acquire(self, n, ex):
        with self.cond:
            if ex.stopped or not self._fits(n, ex):
                return False
            self._take(n, ex)
            return True

    def release(self, n, ex):
        with self.cond:
            n = min(n, ex.held)
            self.used -= n
            ex.held -= n
            self.cond.notify_all()

    def release_all(self, ex):
        with self.cond:
            self.used -= ex.held
            ex.held = 0
            self.cond.notify_all()


class _Lane:
    def __init__(self, name, workers, max_waiting, budget_bytes, per_request, grow_to=None):
        self.name, self.workers, self.max_waiting = name, workers, max_waiting
        self.budget = _Budget(budget_bytes, per_request)
        self.waiting = deque()
        self.cond = threading.Condition()
        self.grow_to = max(workers, grow_to or 0)
        self.threads = self.active = self.peak_active = self.peak_waiting = self.peak_threads = self.done = 0

    def _add_thread(self):
        self.threads += 1
        self.peak_threads = max(self.peak_threads, self.threads)
        threading.Thread(target=self._work, daemon=True, name=f'lane-{self.name}').start()

    def submit(self, ex):
        with self.cond:
            if len(self.waiting) >= self.max_waiting:
                return False
            self.waiting.append(ex)
            self.peak_waiting = max(self.peak_waiting, len(self.waiting))
            if self.threads < self.workers and self.threads < self.active + len(self.waiting):
                self._add_thread()
            self.cond.notify()
        return True

    def grow(self):
        """Called now and then while anything is waiting. True if this lane still has requests waiting."""
        with self.cond:
            if self.waiting and time.time() - self.waiting[0].t0 >= GROW_AFTER:
                for _ in range(min(len(self.waiting), self.grow_to - self.threads)):
                    self._add_thread()
            return bool(self.waiting)

    def _work(self):
        while True:
            with self.cond:
                while not self.waiting:
                    if not self.cond.wait(SHRINK_AFTER if self.threads > self.workers else None) and not self.waiting and self.threads > self.workers:
                        self.threads -= 1
                        return
                ex = self.waiting.popleft()
                self.active += 1
                self.peak_active = max(self.peak_active, self.active)
            try:
                ex.run()
            except Exception:
                traceback.print_exc()
            finally:
                with self.cond:
                    self.active -= 1
                    self.done += 1


class _Sock:
    """All of a socket the Handler touches."""

    def __init__(self, raw, ex):
        self.raw, self.ex = raw, ex

    def makefile(self, mode, buffering=-1):
        return io.BufferedReader(io.BytesIO(self.raw))

    def settimeout(self, t):
        pass

    def sendall(self, b):
        self.ex.write(bytes(b))

    def getsockname(self):
        return ('127.0.0.1', 0)

    def shutdown(self, how):
        pass

    def close(self):
        pass


def _make_handler(base, language_file):
    class BridgeHandler(base):
        def do_GET(self):
            if language_file is not None and self.path == ui_language.ROUTE:
                return ui_language.handle(self, language_file)
            return super().do_GET()

        def do_HEAD(self):
            if language_file is not None and self.path == ui_language.ROUTE:
                return ui_language.handle(self, language_file)
            return super().do_HEAD()

        def do_POST(self):
            if language_file is not None and self.path == ui_language.ROUTE:
                return ui_language.handle(self, language_file)
            return super().do_POST()

        def copyfile(self, source, outputfile):
            self.connection.ex.file_body(source)

        def send_head(self):
            self.connection.ex.local = self.translate_path(self.path)
            return super().send_head()

    return BridgeHandler


class Exchange:
    """One request. `stopped` is safe to read from any thread; cancel() may be called from any thread."""

    def __init__(self, bridge, method, target, raw, lane, is_document):
        self.b, self.method, self.target, self.raw, self.lane, self.is_document = bridge, method, target, raw, lane, is_document
        self.budget = lane.budget if lane else None
        self.path = urllib.parse.unquote(target.split('?', 1)[0])
        self.stopped = False
        self.held = 0
        self.hbuf = bytearray()
        self.head_done = False
        self.status = None
        self.reason = ''
        self.headers = []
        self.announced = None    # Content-Length, when the engine gave one
        self.sent = 0
        self.local = None        # the file the engine is answering from, once it has found one
        self.ticket = is_document is not False and bridge._take_ticket(target)   # now, not when the engine has its answer: that can take longer than a ticket lasts
        self.swallow = False     # the engine's body is not wanted: a refusal or a redirect replaced it
        self.note = None
        self.t0 = time.time()

    def cancel(self):
        """The web view gave up on this request. The Handler stops at its next write, and a worker waiting on the budget wakes at once."""
        if self.stopped:
            return
        self.stopped = True
        if self.budget:
            self.budget.release_all(self)
        self.b._log_end(self, 'cancelled')

    # ---- worker side
    def run(self):
        if self.stopped:
            return
        try:
            self.b.Handler(_Sock(self.raw, self), ('127.0.0.1', 0), None)  # the constructor runs the whole request
        except GONE:
            pass
        except Exception:
            traceback.print_exc()
            self.note = 'exception'
        self._end()

    def write(self, b):
        if self.stopped:
            raise BrokenPipeError
        if self.head_done:
            return self._body(b)
        self.hbuf += b
        i = self.hbuf.find(b'\r\n\r\n')
        if i < 0:
            return
        head, rest = bytes(self.hbuf[:i]), bytes(self.hbuf[i + 4:])
        self.hbuf = bytearray()
        self.head_done = True
        self._parse_head(head)
        self._on_head()
        if rest:
            self._body(rest)

    def _parse_head(self, head):
        lines = head.decode('latin-1').split('\r\n')
        parts = lines[0].split(None, 2)
        self.status, self.reason = int(parts[1]), parts[2] if len(parts) > 2 else ''
        for ln in lines[1:]:
            k, _, v = ln.partition(':')
            k, v = k.strip(), v.strip()
            if k.lower() not in DROP:
                self.headers.append((k, v))

    def _header(self, name):
        return next((v for k, v in self.headers if k.lower() == name), None)

    def _set_header(self, name, value):
        self.headers = [(k, v) for k, v in self.headers if k.lower() != name.lower()] + [(name, value)]

    def _replace(self, status, reason, ctype, body, *extra):
        """This answer instead of the engine's. Stops the Handler before it sends any of its own."""
        self.status, self.reason, self.swallow, self.announced = status, reason, True, len(body)
        self.headers = [('Content-Type', ctype), ('Content-Length', str(len(body))), ('X-Content-Type-Options', 'nosniff'), *extra]
        self._send_head()
        if self.method != 'HEAD':
            self._send(body)
        raise BrokenPipeError

    def _answer_pdf(self):
        """The file itself is never handed over, whoever asks: not to a frame, an object, a fetch or a Range. A library address with ?pdf-page=N is one page as a picture.
        Without it, it is a page holding them all. PDFium as packaged has no script engine, and the engine draws pages with it already.
        The engine has already judged the address, so everything it refuses stays refused."""
        csp = ('Content-Security-Policy', self.b.server.Handler.SAVED_PAGE_CSP)
        path = self.path
        if self.local and path.startswith(FILE_PREFIXES) and os.path.isfile(self.local):
            try:
                m = PDF_PAGE.search(self.target)
                if m:
                    body = self.b.pdf_page(path, self.local, int(m.group(1)))
                    self._replace(200, 'OK', 'image/png', body, csp, ('Cache-Control', 'max-age=86400'))
                body = self.b.pdf_viewer(path, self.local)
                self._replace(200, 'OK', 'text/html; charset=utf-8', body, ('Content-Security-Policy', self.b.viewer_csp()))
            except GONE:
                raise
            except Exception as e:     # a damaged or locked PDF
                print('PDF not shown:', type(e).__name__, flush=True)
        self.note = 'pdf-refused'
        self._replace(404, 'Not Found', 'text/html; charset=utf-8', PDF_NOTICE, csp)

    def _on_head(self):
        """The Handler's headers are in and no body has moved. Everything that can change the answer happens here."""
        if self.status in (200, 206) and 'pdf' in (self._header('content-type') or '').lower():
            self._answer_pdf()
        length = self._header('content-length')
        self.announced = int(length) if length and length.isdigit() else None
        refusal = self._flood_gate()
        if refusal:
            self.note = 'flood-gate'
            self.b.count('flood-gate')
            self.status, self.reason = refusal
            self.headers = [('Content-Type', 'text/html; charset=utf-8'), ('Content-Length', str(len(TOO_LARGE))), ('X-Content-Type-Options', 'nosniff'),   # as plain text, a frame showed it blank
                            ('Content-Security-Policy', self.b.server.Handler.SAVED_PAGE_CSP)]
            self.announced = len(TOO_LARGE)
            self.swallow = True
            self._send_head()
            self._send(TOO_LARGE)
            raise BrokenPipeError   # stops the Handler before it reads the file
        if self.b.meta_redirects and 300 <= self.status < 400 and self._header('location'):
            # No public WKURLSchemeTask call follows a redirect, so hand the frame a page that moves itself.
            # A sandbox would stop the refresh, so this one page says instead that it runs nothing and loads nothing. It holds only the engine's address, escaped.
            body = f'<!doctype html><meta http-equiv="refresh" content="0;url={html.escape(self._header("location"), quote=True)}">'.encode()
            self.status, self.reason = 200, 'OK'
            self.headers = [('Content-Type', 'text/html; charset=utf-8'), ('Content-Length', str(len(body))), ('X-Content-Type-Options', 'nosniff'),
                            ('Content-Security-Policy', "default-src 'none'; script-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'")]
            self.announced = len(body)
            self.swallow = True
            self._send_head()
            self._send(body)
            return
        ctype = (self._header('content-type') or '').lower()
        if 'html' in ctype and not self._header('content-security-policy'):   # the app's own page may not sit inside a frame
            self.headers.append(('Content-Security-Policy', "frame-ancestors 'none'"))
        self._send_head()

    def _flood_gate(self):
        if self.method != 'GET' or self.status not in (200, 206) or self.announced is None or self.announced <= BIG_BODY:
            return None
        if self.b.whole_max and self.announced > self.b.whole_max:
            return 413, 'Too Large'
        if self.ticket:
            return None
        return 403, 'Not For This Page'

    def file_body(self, source):
        """The Handler offers a whole open file. Buffer mode can hand it over by name, with nothing copied through Python."""
        if self.swallow:
            return
        if self._file_by_name(getattr(source, 'name', None)):
            return
        while True:
            if self.stopped:
                raise BrokenPipeError
            b = source.read(CHUNK)
            if not b:
                break
            self._body(b)

    def _body(self, b):
        if self.swallow or not b:
            return
        self.sent += len(b)
        unknown_limit = None if self.lane is self.b.lanes['chat'] else BIG_BODY
        if self.announced is None and unknown_limit and self.sent > unknown_limit:   # a body that never said how long it was
            self.note = 'unknown-length-over-limit'
            self.b.count('unknown-length')
            raise BrokenPipeError
        self._send(b)

    def _end(self):
        raise NotImplementedError

    def _send_head(self):
        raise NotImplementedError

    def _send(self, b):
        raise NotImplementedError

    def refuse(self):
        """Still waiting, and nobody wants it any more. Only buffer mode needs this: there is no other way to hear that the web view has given up on a request."""
        self.cancel()

    def _file_by_name(self, name):
        return False


class _Streamed(Exchange):
    def __init__(self, bridge, method, target, raw, lane, is_document, sink):
        super().__init__(bridge, method, target, raw, lane, is_document)
        self.sink = sink

    def _send_head(self):
        self.sink.head(self.status, self.reason, list(self.headers))

    def _send(self, b):
        for i in range(0, len(b), CHUNK):
            piece = b[i:i + CHUNK]
            self.budget.acquire(len(piece), self)
            self.sink.data(piece, self._acker(len(piece)))

    def _acker(self, n):
        state = [n]

        def ack():
            taken, state[0] = state[0], 0
            if taken:
                self.budget.release(taken, self)
        return ack

    def _end(self):
        if self.stopped:
            return
        if not self.head_done:
            self.status, self.reason, self.note = 502, 'No Answer', self.note or 'no-answer'
            self.headers = [('Content-Length', '0')]
            self.head_done = True
            self.announced = 0
            self._send_head()
        short = self.method != 'HEAD' and self.announced is not None and not self.swallow and self.sent < self.announced and self.status not in (204, 304)
        cut = self.note == 'unknown-length-over-limit'
        self.sink.finish(not (short or cut))
        self.b._log_end(self, 'short' if short or cut else 'finished')


class _Buffered(Exchange):
    def __init__(self, bridge, method, target, raw, lane, is_document, done):
        super().__init__(bridge, method, target, raw, lane, is_document)
        self.done_cb = done
        self.mem = bytearray()
        self.spool = None        # (open file, path)
        self.named = None
        self.size = 0

    def _send_head(self):
        pass

    def _file_by_name(self, name):
        if isinstance(name, str) and self.method == 'GET':
            self.named = name
            self.sent = self.announced or 0
            return True
        return False

    def _send(self, b):
        self.size += len(b)
        if self.b.whole_max and self.size > self.b.whole_max:   # a body that never said how long it was
            self._drop_memory()
            self._drop_spool()
            self.status, self.reason, self.headers, self.note = 413, 'Too Large', [('Content-Type', 'text/html; charset=utf-8'), ('Content-Security-Policy', self.b.server.Handler.SAVED_PAGE_CSP)], 'too-large'
            self.mem = bytearray(TOO_LARGE)
            self.swallow = True
            raise BrokenPipeError
        if self.spool:
            self.spool[0].write(b)
            return
        if self.size <= SPOOL_AT:
            if self.budget.try_acquire(len(b), self):
                self.mem += b
                return
            if not self.held:     # holding nothing, so waiting cannot deadlock: whoever holds bytes will finish or spill
                self.budget.acquire(len(b), self)
                self.mem += b
                return
        self._spill(b)

    def _spill(self, b):
        fd, path = tempfile.mkstemp(prefix='lb-spool-', dir=self.b.tmpdir)
        f = os.fdopen(fd, 'wb')
        self.spool = (f, path)
        f.write(self.mem)
        f.write(b)
        self._drop_memory()
        self.b.count('spilled')

    def refuse(self):
        self.cancel()
        status, reason, hs, text = _plain(503, 'Busy', b'no longer wanted')
        self.done_cb(Response(status, reason, hs, body=text))

    def _drop_memory(self):
        self.mem = bytearray()
        self.budget.release_all(self)

    def _drop_spool(self):
        if self.spool:
            self.spool[0].close()
            try:
                os.unlink(self.spool[1])
            except OSError:
                pass
            self.spool = None

    def _end(self):
        if self.stopped:
            self._drop_memory()
            self._drop_spool()
            return
        if self.note == 'unknown-length-over-limit':
            self._drop_memory()
            self._drop_spool()
            self.status, self.reason, self.headers = 413, 'Too Large', [('Content-Type', 'text/html; charset=utf-8'), ('Content-Security-Policy', self.b.server.Handler.SAVED_PAGE_CSP)]
            self.mem = bytearray(TOO_LARGE)
        if not self.head_done:
            self.status, self.reason, self.note = 502, 'No Answer', self.note or 'no-answer'
        headers = self.headers
        if self.spool:
            self.spool[0].close()
            resp = Response(self.status, self.reason, headers, path=self.spool[1], delete=True)
        elif self.named:
            resp = Response(self.status, self.reason, headers, path=self.named)
        else:
            resp = Response(self.status, self.reason, headers, body=bytes(self.mem), release=lambda: self.budget.release_all(self))
            self.mem = bytearray()
        resp.lane = self.lane.name
        self.b._log_end(self, 'finished', size=self.size)
        self.done_cb(resp)


class _PollSink(Sink):
    def __init__(self):
        self.q = queue.Queue()
        self.headed = threading.Event()
        self.status, self.headers = None, []

    def head(self, status, reason, headers):
        self.status, self.headers = status, headers
        self.headed.set()

    def data(self, chunk, ack):
        self.q.put((chunk, ack))

    def finish(self, ok):
        self.q.put(None)
        self.headed.set()


class Bridge:
    def __init__(self, server_module, mode, origin, tmpdir=None, log=None, lanes=None, per_request=PER_REQUEST, piece=None,
                 whole_max='default', poll_wait=POLL_WAIT, *, language_file=None):
        """server_module: the imported engine, after server.init(). mode: 'stream' or 'buffer'. origin: ORIGIN_MAC or ORIGIN_WINDOWS.
        tmpdir: where buffer mode spools (None: the system's). log: a function taking one dict per request; it never sees the key."""
        if mode not in ('stream', 'buffer'):
            raise ValueError(mode)
        self.server, self.mode, self.origin = server_module, mode, origin
        self.tmpdir, self.logger = tmpdir, log
        self.language_file = language_file
        self.Handler = _make_handler(server_module.Handler, language_file)
        self.key = secrets.token_urlsafe(32)     # new each launch; never written to a log
        self.piece = piece or VIDEO_PIECE[mode]
        self.whole_max = WHOLE_MAX if whole_max == 'default' else whole_max
        self.meta_redirects = mode == 'stream'
        self.poll_wait = poll_wait
        self.lanes = {n: _Lane(n, w, q, b, per_request if mode == 'stream' else None, GROW_TO.get(n)) for n, (w, q, b) in (lanes or LANES).items()}
        self.waiting_now = threading.Event()
        threading.Thread(target=self._grow_lanes, daemon=True, name='lane-grow').start()
        self.tickets = {}
        self.ticket_lock = threading.Lock()
        self.streams = {}
        self.stream_lock = threading.Lock()
        self.counts = {}
        self.count_lock = threading.Lock()
        self.pdf_sizes = {}
        self.pdf_lock = threading.Lock()

    # ---- for the shell: requests
    def start(self, method, url, headers, body, sink, is_document=None):
        """Stream mode. Runs sink's calls on a worker. Returns the Exchange, whose cancel() the shell calls when the web view
        stops the task, or None if the bridge answered at once (a refusal), in which case sink already has the whole answer.
        headers: (name, value) pairs or a dict. body: bytes or None. is_document: False when the shell knows this is no document."""
        refused, prepared = self._prepare(method, url, headers, body, is_document)
        if refused:
            status, reason, hs, text = refused
            sink.head(status, reason, hs)
            if method != 'HEAD':
                sink.data(text, lambda: None)
            sink.finish(True)
            return None
        target, raw, lane = prepared
        ex = _Streamed(self, method, target, raw, lane, is_document, sink)
        if not lane.submit(ex):
            self.count('queue-full')
            status, reason, hs, text = _plain(503, 'Busy', b'too many requests')
            sink.head(status, reason, hs)
            if method != 'HEAD':
                sink.data(text, lambda: None)
            sink.finish(True)
            return None
        self.waiting_now.set()
        return ex

    def fetch(self, method, url, headers, body, done, is_document=None):
        """Buffer mode. done(Response) runs on a worker, or at once on this thread for a refusal. Returns the Exchange or None."""
        refused, prepared = self._prepare(method, url, headers, body, is_document)
        if refused:
            done(Response(refused[0], refused[1], refused[2], body=None if method == 'HEAD' else refused[3]))
            return None
        target, raw, lane = prepared
        if target.split('?', 1)[0].startswith('/__bridge/'):
            ex = _BridgeRoute(self, method, target, raw, lane, is_document, done, body)
        else:
            ex = _Buffered(self, method, target, raw, lane, is_document, done)
        if not lane.submit(ex):
            self.count('queue-full')
            status, reason, hs, text = _plain(503, 'Busy', b'too many requests')
            done(Response(status, reason, hs, body=None if method == 'HEAD' else text))
            return None
        self.waiting_now.set()
        return ex

    def drop_waiting(self, older_than=1.0):
        """The app has moved on to another document. What a page before it asked for and is still in line would only hold up the new one."""
        lane = self.lanes['large']
        now = time.time()
        with lane.cond:
            drop = [ex for ex in lane.waiting if now - ex.t0 >= older_than]
            lane.waiting = deque(ex for ex in lane.waiting if now - ex.t0 < older_than)
        for ex in drop:
            ex.refuse()
        return len(drop)

    def has_key(self, headers):
        """Did this come from the app's top frame's own script? Tells a shell whether a POST's body is worth reading at all."""
        return secrets.compare_digest(_lower(headers).get(KEY_HEADER, '').encode('utf-8', 'replace'), self.key.encode())

    # ---- PDFs, as pictures
    def pdf_page(self, path, real, n):
        rec = self.server.catalog()['by_path'].get(path.lstrip('/'))
        if not rec or rec.get('kind') != 'pdf':     # a file a course page links to, with no entry of its own
            rec = {'id': 'file-' + hashlib.sha256(path.encode()).hexdigest()[:32], 'path': real}
        return self.server.render_page(rec, n, PDF_WIDTH)

    def _pdf_page_sizes(self, real):
        st = os.stat(real)
        key = (real, st.st_mtime_ns, st.st_size)
        with self.pdf_lock:
            sizes = self.pdf_sizes.get(key)
        if sizes is None:
            import pypdfium2
            with self.server._pdf_lock:
                pdf = pypdfium2.PdfDocument(real)
                try:
                    sizes = [pdf.get_page_size(i) for i in range(min(len(pdf), PDF_MAX_PAGES))]
                finally:
                    pdf.close()
            with self.pdf_lock:
                while len(self.pdf_sizes) >= PDF_SIZES_KEPT:
                    self.pdf_sizes.pop(next(iter(self.pdf_sizes)))
                self.pdf_sizes[key] = sizes
        return sizes

    def pdf_viewer(self, path, real):
        """A page this program writes, with no script in it and a policy allowing none. Each picture loads when it comes near the view; the ids are what #page=N looks for."""
        rec = self.server.catalog()['by_path'].get(path.lstrip('/')) or {}
        title = html.escape(str(rec.get('title') or os.path.basename(real)))
        rows = [f'<div class="p" id="page={i}"><img loading="lazy" decoding="async" alt="Page {i}" width="{max(round(w), 1)}" height="{max(round(h), 1)}" src="?pdf-page={i}"></div>'
                for i, (w, h) in enumerate(self._pdf_page_sizes(real), 1)]
        return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>' + title + '</title><style>'
                'html{background:#525659}body{margin:0;padding:8px}'
                '.p{max-width:1000px;margin:0 auto 8px}'
                '.p img{display:block;width:100%;height:auto;background:#fff}'
                '</style></head><body>' + ''.join(rows) + '</body></html>').encode()

    def is_pdf_viewer(self, url):
        """A browser loads a picture lazily only where scripting is on, even with no script to run, so this one page has it on: see viewer_csp.
        A library address ending in .pdf is always this page or a plain refusal, because _answer_pdf replaces every answer with that type."""
        target = self.target_of(url)
        if target is None or PDF_PAGE.search(target):
            return False
        path = urllib.parse.unquote(target.split('?', 1)[0])
        return path.lower().endswith('.pdf') and path.startswith(FILE_PREFIXES)

    def viewer_csp(self):
        return 'sandbox allow-scripts; ' + self.server.Handler.NO_CODE_CSP     # no script is allowed from anywhere, and the page keeps no origin of its own

    # ---- for the shell: what may go where
    def frame_url_ok(self, url):
        """What a frame may show: library content, never the app or its API. Not data: or blob:, which a link in a saved page could
        otherwise open in its own frame: the new document would not have that page's policy, and would run its scripts."""
        if url in ('about:blank', 'about:srcdoc'):
            return True
        target = self.target_of(url)
        if target is None:
            return False
        path = urllib.parse.unquote(target.split('?', 1)[0])
        return path.startswith(FRAME_PREFIXES) and '/..' not in path and '\\' not in path

    def top_url_ok(self, url):
        """The only thing the window's top level may show is the app's own page, at any of its # routes, or its setup page."""
        return url.split('#', 1)[0] in (self.origin, self.origin + '/', self.origin + '/ui/setup.html')

    def new_window(self, url, from_top, gesture):
        """Every new-window request is cancelled by the shell. This says what, if anything, happens instead:
        ('inside', url)   navigate the one window there: an address on the app's own page
        ('nothing', None)
        from_top: the request came from the app's top frame. A frame, or a shell that cannot tell, passes False.
        gesture: True for a real user gesture, False for none, None when the shell cannot tell.
        A gesture the shell cannot tell apart is accepted only from the top frame, and saved pages cannot be the top frame.
        A web address does nothing: this app never hands anything to a browser, and the UI shows such an address as text."""
        if not from_top or gesture is False:
            return 'nothing', None
        if self.target_of(url) is not None:
            route = self.inside_route(url)
            return ('inside', self.origin + '/' + route) if route else ('nothing', None)
        return 'nothing', None

    def inside_route(self, url):
        """The app's own route for a library address, for the UI's 'open in its own tab' and 'open the original file' links."""
        target = self.target_of(url)
        if target is None:
            return None
        frag = url.split('#', 1)[1] if '#' in url else ''
        path = urllib.parse.unquote(target.split('?', 1)[0])
        if path in ('/', '/index.html'):
            return '#' + frag if frag.startswith('/') else ''
        if path.startswith('/zim/'):
            parts = [p for p in path.split('/')[2:] if p]
            if not parts:
                return None
            return '#/wiki/' + '/'.join(urllib.parse.quote(p, safe='') for p in parts)
        rec = self.server.catalog()['by_path'].get(path.lstrip('/'))
        if not rec:
            return None
        rid = urllib.parse.quote(str(rec['id']), safe='')
        if rec.get('kind') == 'video':
            return f'#/watch/{rid}'
        if rec.get('kind') == 'pdf':
            m = re.search(r'(?:^|&)page=(\d+)', frag)
            return f'#/read/{rid}?p={m.group(1) if m else 1}&view=pdf'
        return f'#/read/{rid}'

    def give_ticket(self, url):
        """A navigation the app's own top frame started: its target may get a whole big answer, once, within TICKET_LIFE seconds."""
        target = self.target_of(url)
        if target is None:
            return
        with self.ticket_lock:
            now = time.time()
            self.tickets = {k: t for k, t in self.tickets.items() if now - t < TICKET_LIFE}
            self.tickets[target] = now

    def top_script(self, polling=None):
        """Install in the top frame only where possible (macOS: forMainFrameOnly; WebView2 runs it in every frame, and it returns at once there)."""
        polling = self.mode == 'buffer' if polling is None else polling
        return (TOP_SCRIPT.replace('__KEY__', self.key).replace('__POLL__', 'true' if polling else 'false')
                .replace('__UI_LANGUAGE__', 'true' if self.language_file is not None else 'false'))

    def target_of(self, url):
        if url == self.origin:
            return '/'
        if not url.startswith(self.origin + '/'):
            return None
        target = url[len(self.origin):].split('#', 1)[0]
        return re.sub(r'[\x80-\U0010ffff]', lambda m: urllib.parse.quote(m.group()), target)

    def stats(self):
        return {'counts': dict(self.counts), 'lanes': {n: {'active': l.active, 'waiting': len(l.waiting), 'peak_active': l.peak_active, 'peak_waiting': l.peak_waiting,
                                                           'done': l.done, 'threads': l.threads, 'peak_threads': l.peak_threads, 'used': l.budget.used, 'peak_bytes': l.budget.peak, 'cap': l.budget.cap}
                                                       for n, l in self.lanes.items()}}

    def count(self, what):
        with self.count_lock:
            self.counts[what] = self.counts.get(what, 0) + 1

    # ---- inside
    def _refusal(self, why, status, reason, url):
        self.count(why)
        self._log(kind='refused', why=why, status=status, url=url[:300])
        return _plain(status, reason, b'refused')

    def _prepare(self, method, url, headers, body, is_document):
        target = self.target_of(url)
        if target is None:
            return self._refusal('host', 400, 'Bad Request', url), None
        if not target.startswith('/') or target.startswith('//') or BAD_TARGET.search(target):
            return self._refusal('target', 400, 'Bad Request', url), None
        if method not in ('GET', 'HEAD', 'POST'):
            return self._refusal('method', 405, 'Method Not Allowed', url), None
        low = _lower(headers)
        path = target.split('?', 1)[0]
        origin = low.get('origin')
        keyed = self.has_key(low)
        # Ordinary API reads use the key for scheduling only. This route holds
        # desktop state, so reads also require the top frame's key.
        if self.language_file is not None and target == ui_language.ROUTE and method in ('GET', 'HEAD'):
            if not keyed or (origin is not None and origin != self.origin):
                return self._refusal('language-read', 403, 'Forbidden', url), None
        poll = path.startswith('/__bridge/')
        if poll and self.mode != 'buffer':
            return self._refusal('no-such-route', 404, 'Not Found', url), None
        if method == 'POST':
            # WebKit sends no Origin on the app's own POST, and none on a sandboxed page's no-cors POST either, so Origin alone
            # cannot tell them apart. Nor can Content-Type: a no-cors POST of a Blob typed application/json arrives with that type.
            # Only the key is proof, and a no-cors request cannot carry a custom header.
            ctype = low.get('content-type', '').lower()
            wanted = 'application/octet-stream' if poll else 'application/json'
            if origin is not None and origin != self.origin:
                return self._refusal('post-origin', 403, 'Forbidden', url), None
            if not ctype.startswith(wanted):
                return self._refusal('post-type', 403, 'Forbidden', url), None
            if not keyed:
                return self._refusal('post-key', 403, 'Forbidden', url), None
            if body is not None and len(body) > MAX_POST:
                return self._refusal('post-size', 413, 'Too Large', url), None
        elif poll:
            return self._refusal('poll-method', 403, 'Forbidden', url), None
        lines = [f'{method} {target} HTTP/1.1', 'Host: localhost', 'Connection: close']
        for k, v in low.items():
            if k in PASS_HEADERS and k != 'range' and not re.search(r'[\r\n]', v):
                lines.append(f'{k}: {v}')
        rng = self._engine_range(method, path, low.get('range'))
        if rng:
            lines.append(f'Range: {rng}')
        if origin:
            lines.append(f'Origin: {"http://localhost" if origin == self.origin else origin}')
        if method == 'POST':
            lines.append(f'Content-Length: {len(body or b"")}')
        raw = ('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1', 'replace') + (body or b'' if method == 'POST' else b'')
        return None, (target, raw, self.lanes[_lane_for(method, path, keyed, target)])

    def _engine_range(self, method, path, asked):
        """What the Handler gets as Range. A video answer holds at most one piece, and a video asked for with no Range gets the first."""
        real = urllib.parse.unquote(path).lower()
        if not real.endswith(VIDEO_SUFFIXES) or not real.startswith(FILE_PREFIXES):
            return asked
        if method != 'GET':
            return asked
        if not asked:
            return f'bytes=0-{self.piece - 1}'
        m = ENGINE_RANGE.match(asked)
        if not m:
            return asked   # the engine answers 416
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else None
        if end is None or end - start + 1 > self.piece:
            end = start + self.piece - 1
        return f'bytes={start}-{end}'

    def _grow_lanes(self):
        while True:
            self.waiting_now.wait()
            time.sleep(GROW_AFTER)
            self.waiting_now.clear()
            if any([lane.grow() for lane in self.lanes.values()]):
                self.waiting_now.set()

    def _take_ticket(self, target):
        with self.ticket_lock:
            t = self.tickets.pop(target, None)
        return t is not None and time.time() - t < TICKET_LIFE

    def _log(self, **kw):
        if self.logger:
            try:
                self.logger({'ts': round(time.time(), 3), **kw})
            except Exception:
                traceback.print_exc()

    def _log_end(self, ex, end, size=None):
        self._log(kind='req', m=ex.method, t=ex.target[:240], lane=ex.lane.name if ex.lane else None, status=ex.status, sent=size if size is not None else ex.sent,
                  ms=round((time.time() - ex.t0) * 1000, 1), end=end, note=ex.note)

    # ---- chat by polling, for a web view that cannot be streamed to
    def _reap_streams(self):
        now = time.time()
        with self.stream_lock:
            old = [k for k, s in self.streams.items() if now - s['seen'] > STREAM_IDLE]
            dead = [self.streams.pop(k) for k in old]
        for s in dead:
            s['ex'].cancel()

    def _stream_start(self, body):
        self._reap_streams()
        with self.stream_lock:
            if len(self.streams) >= MAX_STREAMS:
                return 429, 'Busy', [('Content-Type', 'text/plain')], b'too many answers at once'
            sid = secrets.token_hex(16)
            sink = _PollSink()
            raw = ('POST /api/chat HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nOrigin: http://localhost\r\n'
                   f'Content-Length: {len(body)}\r\n\r\n').encode() + body
            ex = _Streamed(self, 'POST', '/api/chat', raw, self.lanes['chat'], None, sink)
            self.streams[sid] = {'sink': sink, 'ex': ex, 'seen': time.time()}
        threading.Thread(target=ex.run, daemon=True, name='bridge-chat').start()   # a thread of its own: lives as long as the answer
        sink.headed.wait(30)
        if sink.status is None:
            with self.stream_lock:
                self.streams.pop(sid, None)
            ex.cancel()
            return 502, 'No Answer', [], b''
        hs = [(k, v) for k, v in sink.headers if k.lower() != 'content-length']
        return 200, 'OK', [('X-Bridge-Stream', sid), ('X-Bridge-Status', str(sink.status)), ('X-Bridge-Headers', json.dumps(hs))], b''

    def _stream_op(self, path, body):
        m = re.fullmatch(r'/__bridge/stream/(start|([0-9a-f]{32})/(next|cancel))', path)
        if not m:
            return 404, 'Not Found', [], b''
        if m.group(1) == 'start':
            return self._stream_start(body or b'{}')
        with self.stream_lock:
            s = self.streams.get(m.group(2))
            if s:
                s['seen'] = time.time()
        if not s:
            return 404, 'Not Found', [], b''
        if m.group(3) == 'cancel':
            with self.stream_lock:
                self.streams.pop(m.group(2), None)
            s['ex'].cancel()
            return 200, 'OK', [], b''
        items, end = [], False
        try:
            items.append(s['sink'].q.get(timeout=self.poll_wait))
            while True:
                items.append(s['sink'].q.get_nowait())
        except queue.Empty:
            pass
        data = bytearray()
        for it in items:
            if it is None:
                end = True
            else:
                data += it[0]
                it[1]()
        if end:
            with self.stream_lock:
                self.streams.pop(m.group(2), None)
        return 200, 'OK', [('Content-Type', 'application/octet-stream'), ('Cache-Control', 'no-store')] + ([('X-Bridge-End', '1')] if end else []), bytes(data)


class _BridgeRoute(Exchange):
    def __init__(self, bridge, method, target, raw, lane, is_document, done, body):
        super().__init__(bridge, method, target, raw, lane, is_document)
        self.done_cb, self.body = done, body

    def run(self):
        status, reason, hs, data = self.b._stream_op(self.target.split('?', 1)[0], self.body)
        self.status = status
        self.done_cb(Response(status, reason, hs, body=data))


def _plain(status, reason, text):
    return status, reason, [('Content-Type', 'text/plain'), ('Content-Length', str(len(text))), ('X-Content-Type-Options', 'nosniff')], text


def _lower(headers):
    items = headers.items() if hasattr(headers, 'items') else headers
    return {str(k).lower(): str(v) for k, v in (items or ())}


def _lane_for(method, path, keyed=False, target=''):
    if path.startswith('/__bridge/') or (method == 'POST' and path == '/api/chat'):
        return 'chat'
    if RENDER.match(path) or PDF_PAGE.search(target):
        return 'render'
    if path.startswith('/api/'):
        return 'small' if keyed else 'guest'
    if path.startswith('/ui/') or path in ('/', '/index.html', '/sw.js', '/reader.css'):
        return 'small'
    return 'large'
