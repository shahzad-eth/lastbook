"""The Windows window: WinForms and WebView2, driven through pythonnet. Opens no port and has no way for a page to call Python.

Every request for https://lastbook.invalid goes to bridge.py through WebResourceRequested; that host never resolves anywhere else.
On purpose absent: AddHostObjectToScript, WebMessageReceived, PostWebMessage. IsWebMessageEnabled and AreHostObjectsAllowed are off too.

One window. A new-window request is always cancelled; what happens instead comes from Bridge.new_window. Nothing is ever handed to a browser or another program.
Frames show library content only (Bridge.frame_url_ok) and the top level shows the app's own page only (Bridge.top_url_ok).
Nothing is saved to disk without the person choosing where, and a page's memory has a limit (MEMORY_LIMIT).
The runtime's crash reports stay on this computer (IsCustomCrashReportingEnabled), and its right-click menu keeps only editing (MENU_KEEP): the rest of that menu can reach other programs.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

import bridge as B

# Audit W6: in the packaged app, nothing outside may steer WebView2 or pythonnet. WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS could open a
# debugging port on this no-port app, WEBVIEW2_BROWSER_EXECUTABLE_FOLDER could swap the runtime, PYTHONNET_* the .NET runtime.
# Removed here, before either starts, from Python's copy and from the Win32 environment their loaders read.
if getattr(sys, 'frozen', False):
    for _k in [k for k in os.environ if k.upper().startswith(('WEBVIEW2_', 'PYTHONNET_'))]:
        os.environ.pop(_k, None)
        ctypes.windll.kernel32.SetEnvironmentVariableW(_k, None)

_SYSTEM32_ONLY = 0x00000800    # LOAD_LIBRARY_SEARCH_SYSTEM32
_dlls = {}


def system_dll(name):
    """A Windows DLL that is not a known DLL, from System32 only, never from a folder searched first (audit W2)."""
    if name not in _dlls:
        _dlls[name] = ctypes.WinDLL(name, winmode=_SYSTEM32_ONLY)
    return _dlls[name]

TITLE = 'Lastbook'
WIDTH, HEIGHT = 1280, 860
SURFACE = {True: (0xf3, 0xf3, 0xf3), False: (0x20, 0x20, 0x20)}   # the page's pane colour, light and dark: the caption takes it too, so they read as one surface
MIN_SIZE = (640, 480)   # the page's area, in CSS pixels (see fit_min). Below 900 the page folds its pane to a rail; it never needs the phone layout here
PACE_BYTES = 100 * 1024 * 1024    # a second, for library content. Far above any video, and it keeps a flood from a saved page from swamping the window's thread.
PACE_FROM = 64 * 1024             # smaller answers are not held back
PACE_LANES = ('large', 'guest', 'render')   # never the app's own: those must not wait behind a page
HEAP_SOFT = 192 * 1024 * 1024    # see collect_loop
RESTART_GAP = 10    # seconds. A page that crashes its renderer gets the app reloaded, but not in a tight loop.

# The web view's processes together. Measured here: about 0.3 GB idle, 1.3 GB holding the largest PDF, 1.4 GB playing the largest video.
# A page holds its memory in those processes, and only ending its renderer makes them give it back. Over the limit that renderer is ended
# and the app starts again at home. This samples and then acts, so a page allocating very fast goes over by what it takes in that time.
# Counted with them: this program's .NET heap, where what a page asks for passes on its way to the runtime. Not counted: the engine's own Python memory, which no page sets.
MEMORY_LIMIT_MOST = 3 * 1024 ** 3
MEMORY_EVERY = 0.1
MEMORY_QUIET = 10   # seconds after ending a renderer before ending another: the system needs a moment to give the memory back
WHOLE_COPIES = 11   # measured: while the runtime takes one whole answer of 476 MB, this process holds about ten times that for 2 to 3 seconds, wherever the bytes come from.
                    # Only the app's own navigation can get such an answer, and none is larger than bridge.WHOLE_MAX, or too large for half this computer's memory at that rate.
TOO_BIG = 'A page was using too much memory, so it was closed.'

# msOneAuthWAM: without it the runtime makes outbound connections for account sign-in even with everything else here off.
# Measured on runtime 156.0.4314.50. An Evergreen update could change it.
# The WebRTC policy: a peer connection's UDP packets are never seen by the host rule or the request filter. There is no proxy, so this leaves it nothing to send.
# msForceOneAuthWAM: without it, WebView2 loads Office's sign-in library (oneauth.dll) and the Windows account broker and fetches the
# signed-in Microsoft account's profile and picture from substrate.office.com. Measured 12 Nov 2026, WebView2 157.0.4341.46.
BROWSER_ARGS = ('--disable-features=ElasticOverscroll,msOneAuthWAM,msForceOneAuthWAM --disable-background-networking --disable-component-update '
                '--disable-domain-reliability --no-pings --host-resolver-rules="MAP * ^NOTFOUND" '    # ^NOTFOUND: Chromium's token since 120 (audit X1)
                '--webrtc-ip-handling-policy=disable_non_proxied_udp --force-webrtc-ip-handling-policy=disable_non_proxied_udp')   # both layers' spelling
NO_RUNTIME = ('Lastbook needs the Microsoft Edge WebView2 Runtime, and it was not found on this computer.\n\n'
              'Windows 11 normally includes it. Install "WebView2 Runtime" from Microsoft, then start Lastbook again.')
BLOCKED_SCHEMES = ('http', 'https', 'ws', 'wss', 'ftp')
# All a right-click offers. Anything else in the runtime's menu, now or after an update, goes: its Share panel posts to other programs and makes the runtime write a crash report.
MENU_KEEP = {'cut', 'copy', 'paste', 'pasteAndMatchStyle', 'selectAll', 'undo', 'redo', 'copyImage'}


def light_theme():
    """Windows' own app theme: Settings > Personalisation > Colours."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as k:
            return bool(winreg.QueryValueEx(k, 'AppsUseLightTheme')[0])
    except OSError:
        return True


def caption(hwnd, light):
    """The title bar in the pane's colour, dark when Windows is, with round corners. Windows 10 refuses the colours silently; nothing else changes."""
    r, g, b = SURFACE[light]
    ink = 0x1b1b1b if light else 0xffffff
    for attr, value in ((20, 0 if light else 1),              # DWMWA_USE_IMMERSIVE_DARK_MODE
                        (33, 2),                               # DWMWA_WINDOW_CORNER_PREFERENCE: round
                        (35, r | g << 8 | b << 16),            # DWMWA_CAPTION_COLOR, as COLORREF
                        (36, ink)):                            # DWMWA_TEXT_COLOR
        v = ctypes.c_int(value)
        system_dll('dwmapi').DwmSetWindowAttribute(wt.HWND(hwnd), attr, ctypes.byref(v), ctypes.sizeof(v))


def dark_menus():
    """The window's menu (Restore, Move, Size, Minimise, Maximise, Close) dark when Windows' apps are, as in Windows' own apps. Windows has no
    documented call for a Win32 menu's theme; this is uxtheme's SetPreferredAppMode (ordinal 135, 'follow the system'), which Windows 10 1903
    and later have. Elsewhere it is not called, and menus stay light."""
    if sys.getwindowsversion().build < 18362:
        return
    try:
        ux = system_dll('uxtheme')
        ux[135](ctypes.c_int(1))      # SetPreferredAppMode(AllowDark)
        ux[136]()                     # FlushMenuThemes
    except Exception:
        traceback.print_exc()


def system_menu(hwnd, x, y):
    """The window's menu at a point, as Alt+Space opens it: the system's own menu, with the items enabled as the system would. Its choice goes
    to the window as the system's own command would. Opened as a popup, so Esc closes it fully and leaves no menu mode behind (posting
    SC_KEYMENU did, which kept Win+arrow keys from the window until a menu was opened again)."""
    u = ctypes.windll.user32
    u.GetSystemMenu.restype = ctypes.c_void_p
    u.GetSystemMenu.argtypes = (wt.HWND, wt.BOOL)
    u.EnableMenuItem.argtypes = (ctypes.c_void_p, wt.UINT, wt.UINT)
    u.SetMenuDefaultItem.argtypes = (ctypes.c_void_p, wt.UINT, wt.UINT)
    u.TrackPopupMenu.argtypes = (ctypes.c_void_p, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, ctypes.c_void_p)
    menu = u.GetSystemMenu(wt.HWND(hwnd), False)
    if not menu:
        return
    zoomed, iconic = bool(u.IsZoomed(wt.HWND(hwnd))), bool(u.IsIconic(wt.HWND(hwnd)))
    for cmd, on in ((0xF120, zoomed or iconic), (0xF010, not zoomed), (0xF000, not zoomed and not iconic), (0xF020, not iconic), (0xF030, not zoomed), (0xF060, True)):
        u.EnableMenuItem(menu, cmd, 0 if on else 1)      # MF_BYCOMMAND | MF_ENABLED or MF_GRAYED: SC_RESTORE, SC_MOVE, SC_SIZE, SC_MINIMIZE, SC_MAXIMIZE, SC_CLOSE
    u.SetMenuDefaultItem(menu, 0xF060, 0)
    cmd = u.TrackPopupMenu(menu, 0x0100 | (0x0008 if u.GetSystemMetrics(40) else 0), x, y, 0, wt.HWND(hwnd), None)     # TPM_RETURNCMD; TPM_RIGHTALIGN where menus open right to left (SM_MENUDROPALIGNMENT)
    if cmd:
        u.PostMessageW(wt.HWND(hwnd), 0x0112, cmd, 0)      # WM_SYSCOMMAND


def accent_shades():
    """Windows' own accent (Settings > Personalisation > Colours), as the two shades Fluent fills a selection with: AccentDark1 on a light
    theme, AccentLight2 on a dark one. None if this Windows does not say."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\Accent') as k:
            pal = bytes(winreg.QueryValueEx(k, 'AccentPalette')[0])
    except OSError:
        return None
    if len(pal) < 32:
        return None
    shade = lambda i: '#%02x%02x%02x' % tuple(pal[i * 4:i * 4 + 3])    # eight colours of R, G, B, A: lightest first, the accent itself fourth
    return shade(4), shade(1)


WM_NCCALCSIZE, WM_NCHITTEST, WM_ACTIVATE, WM_DPICHANGED = 0x0083, 0x0084, 0x0006, 0x02E0
HTCLIENT, HTCAPTION, HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 1, 2, 10, 11, 12, 13, 14
WS_CAPTION, WS_THICKFRAME = 0x00C00000, 0x00040000
DWMWA_CAPTION_BUTTON_BOUNDS = 5
TOP_GRIP = 5    # the window's top edge, in CSS pixels, kept for resizing over the page's band, as a Windows 11 title bar keeps it


WM_WINDOWPOSCHANGING, SWP_NOSIZE, SWP_STATECHANGED = 0x0046, 0x0001, 0x8000


class _WindowPos(ctypes.Structure):
    _fields_ = [('hwnd', wt.HWND), ('after', wt.HWND), ('x', ctypes.c_int), ('y', ctypes.c_int), ('cx', ctypes.c_int), ('cy', ctypes.c_int), ('flags', wt.UINT)]


class _Margins(ctypes.Structure):
    _fields_ = [('l', ctypes.c_int), ('r', ctypes.c_int), ('t', ctypes.c_int), ('b', ctypes.c_int)]


_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class Frame:
    """One band at the top, as Windows 11's own apps have: the page draws the title bar's row (Back, the pane button, the name) up to the
    window's top edge, and the window keeps its real caption buttons, drawn and run by the system (snap layouts on the maximise button,
    their hover and press, the inactive grey). The caption is taken out of the frame (WM_NCCALCSIZE) and the frame is extended under the
    client (DWM), so the system draws the buttons there; the web view's own window has those buttons and a thin strip at the top edge cut
    out of it (a window region), so those pixels are this window's: WM_NCHITTEST says what they are. Over the page, the band's
    app-region: drag areas are the caption (the web view's non-client region support): drag, double-click, Snap and the system menu.
    The page is told the band's height (--cap-h) and that it draws it (wcap). Nothing goes from the page to this program."""

    def __init__(self, shell):
        self.shell, self.n = shell, shell.n
        self.hwnd = None
        self.old = None
        self.proc = _WNDPROC(self.wndproc)      # held: Windows calls it for as long as the window lives
        self.cut = None     # (buttons rect, strip height) the web view's region was last cut to, in client pixels
        self.cap_h, self.cap_top = 32, 0
        self.restoring = False     # while WinForms hears that the window came out of maximised or minimised (keep_restored)
        u = self.u = ctypes.windll.user32
        u.SetWindowLongPtrW.restype = ctypes.c_void_p
        u.SetWindowLongPtrW.argtypes = (wt.HWND, ctypes.c_int, ctypes.c_void_p)
        u.CallWindowProcW.restype = ctypes.c_ssize_t
        u.CallWindowProcW.argtypes = (ctypes.c_void_p, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
        u.GetWindowLongW.restype = ctypes.c_long
        self.dwm = ctypes.WinDLL('dwmapi', winmode=_SYSTEM32_ONLY)    # its own handle: argtypes are set on it below
        self.dwm.DwmDefWindowProc.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, ctypes.POINTER(ctypes.c_ssize_t))

    def attach(self, hwnd):
        if hwnd == self.hwnd and self.old:
            return      # already this window's
        self.hwnd = hwnd
        self.old = self.u.SetWindowLongPtrW(hwnd, -4, ctypes.cast(self.proc, ctypes.c_void_p))   # GWLP_WNDPROC
        self.extend()
        self.u.SetWindowPos(wt.HWND(hwnd), None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)   # NOSIZE NOMOVE NOZORDER NOACTIVATE FRAMECHANGED

    def framed(self):
        """True while the window has its normal frame: not in a page's full screen, which takes the frame away (on_fullscreen)."""
        style = self.u.GetWindowLongW(wt.HWND(self.hwnd), -16)
        return bool(style & WS_CAPTION) and bool(style & WS_THICKFRAME)

    def maximized(self):
        return bool(self.u.IsZoomed(wt.HWND(self.hwnd)))

    def scale(self):
        return (self.u.GetDpiForWindow(wt.HWND(self.hwnd)) or 96) / 96

    def buttons(self):
        """The system's caption buttons, in client pixels: (left, top, right, bottom), or None."""
        r = wt.RECT()
        if self.dwm.DwmGetWindowAttribute(wt.HWND(self.hwnd), DWMWA_CAPTION_BUTTON_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0 or r.right <= r.left:
            return None
        w, c = wt.RECT(), wt.POINT(0, 0)
        self.u.GetWindowRect(wt.HWND(self.hwnd), ctypes.byref(w))
        self.u.ClientToScreen(wt.HWND(self.hwnd), ctypes.byref(c))
        dx, dy = c.x - w.left, c.y - w.top      # the window's origin is outside its client: the invisible resize borders
        return (r.left - dx, r.top - dy, r.right - dx, r.bottom - dy)

    def extend(self):
        b = self.buttons()
        m = _Margins(0, 0, max(b[3], 1) if b else 1, 0)
        self.dwm.DwmExtendFrameIntoClientArea(wt.HWND(self.hwnd), ctypes.byref(m))

    def wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_WINDOWPOSCHANGING and self.framed():
                self.keep_restored(ctypes.cast(lp, ctypes.POINTER(_WindowPos))[0])
            if msg == WM_NCCALCSIZE and wp and self.framed():
                return self.calc(hwnd, msg, wp, lp)
            if self.framed() and (msg == WM_NCHITTEST or 0x00A0 <= msg <= 0x00AD or msg == 0x02A2):    # hit tests, non-client mouse, WM_NCMOUSELEAVE
                if msg == WM_NCHITTEST and self.on_top_edge(hwnd, lp):
                    return self.hit(hwnd, msg, wp, lp)     # the top edge resizes, above the caption buttons too, as a native frame's does
                res = ctypes.c_ssize_t(0)
                if self.dwm.DwmDefWindowProc(hwnd, msg, wp, lp, ctypes.byref(res)):
                    return res.value        # over the caption buttons: the system's own
                if msg == WM_NCHITTEST:
                    return self.hit(hwnd, msg, wp, lp)
            if msg == WM_ACTIVATE:
                self.extend()
            if msg in (0x0047, 0x031E, WM_DPICHANGED):     # WM_WINDOWPOSCHANGED, WM_DWMCOMPOSITIONCHANGED: the buttons may have moved
                self.shell.ui(self.shell.fit_band)
            if msg == 0x0047 and self.framed() and ctypes.cast(lp, ctypes.POINTER(_WindowPos))[0].flags & SWP_STATECHANGED and not self.maximized() and not self.u.IsIconic(wt.HWND(hwnd)):
                self.restoring = True       # out of maximised or minimised: what WinForms does while it hears of it is kept_restored's
                try:
                    return self.u.CallWindowProcW(self.old, hwnd, msg, wp, lp)
                finally:
                    self.restoring = False
        except Exception:
            traceback.print_exc()
        return self.u.CallWindowProcW(self.old, hwnd, msg, wp, lp)

    def keep_restored(self, w):
        """Out of maximised (a double-click, the Restore button, Win+Down, Win+Up, Win+Left, a drag down from the top), the system puts the
        window where it belongs, restored or snapped; WinForms, as it hears of the change, then sets bounds of its own, made from its client
        size with a caption added (Form.RestoreWindowBoundsIfNecessary), which this window no longer has: the window would grow by a
        caption's height each time, and lose a snap. While it hears of it, its moves and sizes are dropped, and the system's place stands."""
        if self.restoring and not w.flags & SWP_STATECHANGED:
            w.flags |= SWP_NOSIZE | 0x0002      # SWP_NOMOVE

    def calc(self, hwnd, msg, wp, lp):
        """The client takes the caption's place; the sides and bottom keep their resize borders. A maximised window reaches past the
        screen by its border on every side, and its client keeps that top too: the system hit-tests its caption buttons there only
        then. The page is told how much of its band is above the screen (hidden)."""
        rc = ctypes.cast(lp, ctypes.POINTER(wt.RECT))     # NCCALCSIZE_PARAMS starts with the proposed window rect
        top = rc[0].top
        res = self.u.CallWindowProcW(self.old, hwnd, msg, wp, lp)
        rc[0].top = top
        if self.maximized() and self.autohide_taskbar():
            rc[0].bottom -= 1     # a client that fills the screen reads as full screen, and a hidden taskbar would not come up
        return res

    def autohide_taskbar(self):
        class AppBarData(ctypes.Structure):
            _fields_ = [('cb', wt.DWORD), ('hwnd', wt.HWND), ('msg', wt.UINT), ('edge', wt.UINT), ('rc', wt.RECT), ('lp', wt.LPARAM)]
        d = AppBarData()
        d.cb = ctypes.sizeof(d)
        return bool(ctypes.windll.shell32.SHAppBarMessage(4, ctypes.byref(d)) & 1)     # ABM_GETSTATE, ABS_AUTOHIDE

    def on_top_edge(self, hwnd, lp):
        if self.maximized():
            return False
        p = wt.POINT(ctypes.c_short(lp & 0xffff).value, ctypes.c_short((lp >> 16) & 0xffff).value)
        self.u.ScreenToClient(wt.HWND(hwnd), ctypes.byref(p))
        return p.y < int(TOP_GRIP * self.scale())

    def hit(self, hwnd, msg, wp, lp):
        """Only the parts the web view leaves to this window come here: the caption buttons' place, and the strip along the top edge."""
        res = self.u.CallWindowProcW(self.old, hwnd, msg, wp, lp)
        p = wt.POINT(ctypes.c_short(lp & 0xffff).value, ctypes.c_short((lp >> 16) & 0xffff).value)
        self.u.ScreenToClient(wt.HWND(hwnd), ctypes.byref(p))
        if not self.maximized() and p.y < int(TOP_GRIP * self.scale()) and res in (HTCLIENT, HTTOP, HTLEFT, HTRIGHT):
            corner = int(16 * self.scale())
            width = self.n.Forms.Control.FromHandle(self.n.System.IntPtr(hwnd)).ClientSize.Width
            return HTTOPLEFT if p.x < corner else HTTOPRIGHT if p.x >= width - corner else HTTOP
        if res != HTCLIENT:
            return res      # the side and bottom borders
        return HTCAPTION

    def layout(self):
        """Cuts the web view's window to leave the caption buttons and the top strip to this window, and returns the band's height in CSS
        pixels when it changed. Called on every size change."""
        view = self.shell.view
        if not self.framed():
            if self.cut is not None:
                view.Region = None
                self.cut = None
            return None
        b = self.buttons()
        if not b:
            return None
        grip = 0 if self.maximized() else int(TOP_GRIP * self.scale())
        cut = (b, grip, view.Width, view.Height)
        if cut != self.cut:
            D = self.n.Drawing
            region = D.Region(D.Rectangle(0, 0, view.Width, view.Height))
            region.Exclude(D.Rectangle(b[0], 0, view.Width - b[0], b[3]))     # to the window's right edge: nothing of the page shows beside them
            if grip:
                region.Exclude(D.Rectangle(0, 0, view.Width, grip))
            view.Region = region
            self.cut = cut
            self.extend()
        h = max(24, round(b[3] / self.scale()))
        hidden = round(self.hidden() / self.scale())
        if (h, hidden) != (self.cap_h, self.cap_top):
            self.cap_h, self.cap_top = h, hidden
            return h
        return None

    def hidden(self):
        """How far the client's top is above the window's visible top: a maximised window's border, past the screen's edge."""
        f, c = wt.RECT(), wt.POINT(0, 0)
        self.dwm.DwmGetWindowAttribute(wt.HWND(self.hwnd), 9, ctypes.byref(f), ctypes.sizeof(f))     # DWMWA_EXTENDED_FRAME_BOUNDS
        self.u.ClientToScreen(wt.HWND(self.hwnd), ctypes.byref(c))
        return max(0, f.top - c.y)

    def paint(self, sender, e):
        """Black is clear in the extended frame: the system's caption, with its buttons, shows there."""
        b = self.buttons()
        if b and self.framed():
            e.Graphics.FillRectangle(self.n.Drawing.Brushes.Black, 0, 0, self.shell.form.ClientSize.Width, b[3])

    def release(self):
        """Back to the plain frame: the web view could not take the band."""
        if self.old:
            self.u.SetWindowLongPtrW(self.hwnd, -4, self.old)
            self.old = None
        self.shell.view.Region = None
        m = _Margins(0, 0, 0, 0)
        self.dwm.DwmExtendFrameIntoClientArea(wt.HWND(self.hwnd), ctypes.byref(m))
        self.u.SetWindowPos(wt.HWND(self.hwnd), None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)


# Native to page only, like the accent: the band's height, and that the page draws it, on the app's own top page.
FRAME_SCRIPT = """(() => { if (window.top !== window || location.origin !== %s) return;
  const set = () => { const e = document.documentElement; e.classList.add('wcap'); e.style.setProperty('--cap-h', '%dpx'); e.style.setProperty('--cap-top', '%dpx') };
  if (document.documentElement) set(); else new MutationObserver((m, o) => { if (document.documentElement) { o.disconnect(); set() } }).observe(document, { childList: true });
})()"""


# Native to page only, like the bridge's own script: two colours this program read from the registry, set on the app's own top page.
ACCENT_SCRIPT = """(() => { if (window.top !== window || location.origin !== %s) return;
  const set = () => { const s = document.documentElement.style; s.setProperty('--sys-acc-l', %s); s.setProperty('--sys-acc-d', %s) };
  if (document.documentElement) set(); else new MutationObserver((m, o) => { if (document.documentElement) { o.disconnect(); set() } }).observe(document, { childList: true });
})()"""


def note(**kw):
    """One decision of the shell. Nothing in the product listens."""


def _lib_dir():
    root = getattr(sys, '_MEIPASS', None)
    return (Path(root) if root else Path(__file__).resolve().parent) / 'webview2'


def message(text, error=True):
    ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10 if error else 0x40)   # MB_ICONERROR, MB_ICONINFORMATION


class _Guid(ctypes.Structure):
    _fields_ = [('a', ctypes.c_uint32), ('b', ctypes.c_uint16), ('c', ctypes.c_uint16), ('d', ctypes.c_ubyte * 8)]


def _guid(text):
    g = _Guid()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(g))
    return g


def _com(ptr, index, *argtypes):
    """Method <index> of the COM object at ptr, as a function taking the remaining arguments and giving back its HRESULT."""
    vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[index])
    return lambda *a: fn(ptr, *a)


def downloads():
    p = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(_guid('{374DE290-123F-4565-9164-39C4925E467B}')), 0, None, ctypes.byref(p)) != 0:
        return Path.home() / 'Downloads'
    try:
        return Path(p.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(p)


def pick_folder(prompt, start, *, files=False):
    """Windows' native folder or existing-file picker, opened at the requested location."""
    vp, wstr = ctypes.c_void_p, ctypes.c_wchar_p
    ctypes.windll.ole32.CoInitializeEx(None, 0x2)    # COINIT_APARTMENTTHREADED; already so on this thread is fine
    dialog = vp()
    if ctypes.windll.ole32.CoCreateInstance(ctypes.byref(_guid('{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}')), None, 1,    # CLSID_FileOpenDialog, CLSCTX_INPROC_SERVER
                                            ctypes.byref(_guid('{D57C7288-D4AD-4768-BE02-9D969532D960}')), ctypes.byref(dialog)) != 0:
        raise OSError('Windows could not open its folder picker.')
    try:
        options = ctypes.c_uint32()
        _com(dialog, 10, ctypes.POINTER(ctypes.c_uint32))(ctypes.byref(options))                       # GetOptions
        pick_kind = 0x1000 if files else 0x20   # FILEMUSTEXIST or PICKFOLDERS
        _com(dialog, 9, ctypes.c_uint32)(options.value | pick_kind | 0x40 | 0x800 | 0x8)  # FORCEFILESYSTEM, PATHMUSTEXIST, NOCHANGEDIR
        _com(dialog, 17, wstr)(prompt)                                                                 # SetTitle
        _com(dialog, 18, wstr)('Choose')                                                               # SetOkButtonLabel
        folder = vp()
        if ctypes.windll.shell32.SHCreateItemFromParsingName(wstr(str(start)), None, ctypes.byref(_guid('{43826D1E-E718-42EE-BC55-A1E261C37BFE}')),
                                                             ctypes.byref(folder)) == 0:
            _com(dialog, 12, vp)(folder)                                                               # SetFolder
            _com(folder, 2)()                                                                          # Release
        if _com(dialog, 3, vp)(None) != 0:                                                             # Show: cancelled, or it could not
            return None
        item = vp()
        if _com(dialog, 20, ctypes.POINTER(vp))(ctypes.byref(item)) != 0 or not item:                 # GetResult
            return None
        try:
            name = wstr()
            if _com(item, 5, ctypes.c_uint32, ctypes.POINTER(wstr))(0x80058000, ctypes.byref(name)) != 0:   # GetDisplayName(SIGDN_FILESYSPATH)
                return None
            try:
                return name.value
            finally:
                ctypes.windll.ole32.CoTaskMemFree(name)
        finally:
            _com(item, 2)()
    finally:
        _com(dialog, 2)()


def system_dpi():
    try:
        return ctypes.windll.user32.GetDpiForSystem() or 96
    except AttributeError:    # before Windows 10 1607
        return 96


def choose_folder(title, text):
    """Before there is a window: the chosen folder's path, '' if the picker was cancelled, or None if they quit."""
    ctypes.windll.user32.SetProcessDPIAware()
    n = net()
    F, D = n.Forms, n.Drawing
    chosen, failure = [], []
    k = system_dpi() / 96    # this process is DPI aware, so sizes in pixels are scaled here; fonts in points scale by themselves
    S = lambda v: int(round(v * k))
    light = light_theme()
    C = lambda h: D.ColorTranslator.FromHtml(h)
    back, ink = (C('#f3f3f3'), C('#1b1b1b')) if light else (C('#202020'), C('#ffffff'))
    button_back, button_line = (C('#fbfbfb'), C('#d1d1d1')) if light else (C('#2d2d2d'), C('#454545'))

    def body():
        try:
            ask()
        except Exception as e:   # an exception must not cross into .NET
            traceback.print_exc()
            failure.append(e)

    def ask():
        F.Application.EnableVisualStyles()
        form = F.Form()
        form.Text, form.Font, form.StartPosition = title, D.SystemFonts.MessageBoxFont, F.FormStartPosition.CenterScreen
        form.FormBorderStyle, form.MaximizeBox, form.MinimizeBox, form.ShowIcon = F.FormBorderStyle.FixedDialog, False, False, False
        form.AutoSize, form.AutoSizeMode, form.Padding = True, F.AutoSizeMode.GrowAndShrink, F.Padding(S(20))
        form.BackColor, form.ForeColor = back, ink
        label = F.Label()
        label.Text, label.AutoSize, label.MaximumSize, label.Margin = text, True, D.Size(S(420), 0), F.Padding(0, 0, 0, S(20))
        label.ForeColor = ink
        buttons = F.FlowLayoutPanel()
        buttons.FlowDirection, buttons.AutoSize, buttons.Dock = F.FlowDirection.RightToLeft, True, F.DockStyle.Fill
        buttons.Margin = F.Padding(0)
        for name, result in (('Quit', F.DialogResult.Cancel), ('Choose Folder…', F.DialogResult.OK)):
            b = F.Button()
            b.Text, b.AutoSize, b.DialogResult = name, True, result
            b.MinimumSize, b.Padding, b.Margin = D.Size(S(96), S(30)), F.Padding(S(10), 0, S(10), 0), F.Padding(S(8), 0, 0, 0)
            if not light:
                b.FlatStyle, b.BackColor, b.ForeColor, b.UseVisualStyleBackColor = F.FlatStyle.Flat, button_back, ink, False
                b.FlatAppearance.BorderColor = button_line
            buttons.Controls.Add(b)
            if result == F.DialogResult.OK:
                form.AcceptButton = choose = b
            else:
                form.CancelButton = b
        grid = F.TableLayoutPanel()
        grid.ColumnCount, grid.AutoSize, grid.Location = 1, True, D.Point(S(20), S(16))   # the form's padding keeps only the right and bottom clear
        grid.Controls.Add(label)
        grid.Controls.Add(buttons)
        form.Controls.Add(grid)
        form.ActiveControl = choose   # Enter chooses a folder; it never quits
        form.HandleCreated += lambda s, a: caption(form.Handle.ToInt64(), light)
        if form.ShowDialog() != F.DialogResult.OK:
            return
        chosen.append(pick_folder('Choose the folder called LastbookData', downloads()) or '')

    thread = n.Threading.Thread(n.Threading.ThreadStart(body))   # WinForms and the picker need a single-threaded apartment
    thread.SetApartmentState(n.Threading.ApartmentState.STA)
    thread.Start()
    thread.Join()
    if failure:
        raise failure[0]
    return chosen[0] if chosen else None


_net = None


class _Net:
    """The .NET side. Loaded on first use, so a missing piece can still become a plain message."""

    def __init__(self):
        import clr
        lib = _lib_dir()
        clr.AddReference('System.Windows.Forms')
        clr.AddReference('System.Drawing')
        clr.AddReference(str(lib / 'Microsoft.Web.WebView2.Core.dll'))
        clr.AddReference(str(lib / 'Microsoft.Web.WebView2.WinForms.dll'))
        import System
        import System.Drawing as Drawing
        import System.IO as IO
        import System.Threading as Threading
        import System.Windows.Forms as Forms
        import Microsoft.Web.WebView2.Core as Core
        import Microsoft.Web.WebView2.WinForms as WvForms
        from System.Runtime.InteropServices import Marshal
        self.System, self.Drawing, self.IO, self.Threading, self.Forms = System, Drawing, IO, Threading, Forms
        self.Core, self.WvForms, self.Marshal = Core, WvForms, Marshal
        Core.CoreWebView2Environment.SetLoaderDllFolderPath(str(lib))


def net():
    global _net
    if _net is None:
        _net = _Net()
    return _net


def preflight():
    """A plain sentence if the window cannot work on this computer, or None. Runs before the engine starts."""
    try:
        n = net()
    except Exception:
        traceback.print_exc()
        return f'Lastbook could not load the files it needs to show its window.\n\nThey should be in {_lib_dir()}.'
    try:
        version = n.Core.CoreWebView2Environment.GetAvailableBrowserVersionString()
    except Exception as e:
        print('WebView2 runtime check:', type(e).__name__, e, flush=True)
        return NO_RUNTIME
    print('WebView2 runtime', version, flush=True)
    global RUNTIME
    RUNTIME = str(version or '')
    return None if version else NO_RUNTIME


RUNTIME = ''
BAND_FROM = 124     # the runtime's major version from which a page's app-region is the window's caption (IsNonClientRegionSupportEnabled)


def band_ok():
    """Whether the window can give its title bar to the page: Windows 11's caption button bounds, and a runtime that takes app-region."""
    try:
        major = int(RUNTIME.split('.')[0])
    except ValueError:
        return False
    return major >= BAND_FROM and sys.getwindowsversion().build >= 22000 and os.environ.get('LASTBOOK_PLAIN_CAPTION') != '1'


def guarded(fn):
    """An exception must not cross into .NET: it would end the process."""
    def wrapped(*a):
        try:
            return fn(*a)
        except Exception:
            traceback.print_exc()
    return wrapped


class _PageMemory(ctypes.Structure):
    _fields_ = [('cb', wt.DWORD), ('PageFaultCount', wt.DWORD), ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t), ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t), ('PrivateUsage', ctypes.c_size_t)]


class _ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('cntUsage', wt.DWORD), ('th32ProcessID', wt.DWORD), ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wt.DWORD),
                ('cntThreads', wt.DWORD), ('th32ParentProcessID', wt.DWORD), ('pcPriClassBase', ctypes.c_long), ('dwFlags', wt.DWORD), ('szExeFile', ctypes.c_wchar * 260)]


class _MemoryStatus(ctypes.Structure):
    _fields_ = [('dwLength', wt.DWORD), ('dwMemoryLoad', wt.DWORD), ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong), ('ullTotalPageFile', ctypes.c_ulonglong),
                ('ullAvailPageFile', ctypes.c_ulonglong), ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong), ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]


class _Processes:
    """This program and every process under it, read directly from the system: the web view gives its own list only on the window's thread."""
    QUERY_AND_END = 0x1000 | 0x0001    # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE

    def __init__(self):
        k = self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.restype = wt.HANDLE
        k.OpenProcess.argtypes = (wt.DWORD, wt.BOOL, wt.DWORD)
        k.CloseHandle.argtypes = (wt.HANDLE,)
        k.TerminateProcess.argtypes = (wt.HANDLE, wt.UINT)
        k.CreateToolhelp32Snapshot.restype = wt.HANDLE
        k.CreateToolhelp32Snapshot.argtypes = (wt.DWORD, wt.DWORD)
        k.Process32FirstW.argtypes = k.Process32NextW.argtypes = (wt.HANDLE, ctypes.POINTER(_ProcessEntry))
        k.GlobalMemoryStatusEx.argtypes = (ctypes.POINTER(_MemoryStatus),)
        self.psapi = system_dll('psapi')
        self.psapi.GetProcessMemoryInfo.argtypes = (wt.HANDLE, ctypes.POINTER(_PageMemory), wt.DWORD)
        self.handles = {}

    def physical(self):
        m = _MemoryStatus()
        m.dwLength = ctypes.sizeof(m)
        return m.ullTotalPhys if self.k.GlobalMemoryStatusEx(ctypes.byref(m)) else 0

    def refresh(self):
        parents, names = {}, {}
        snap = self.k.CreateToolhelp32Snapshot(2, 0)     # TH32CS_SNAPPROCESS
        if snap in (None, wt.HANDLE(-1).value):
            return
        try:
            e = _ProcessEntry()
            e.dwSize = ctypes.sizeof(e)
            ok = self.k.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                parents[e.th32ProcessID] = e.th32ParentProcessID
                names[e.th32ProcessID] = e.szExeFile.lower()
                ok = self.k.Process32NextW(snap, ctypes.byref(e))
        finally:
            self.k.CloseHandle(snap)
        mine = {os.getpid()}
        grew = True
        while grew:
            # The local AI's runner is not the web view's: its memory is the model's (about 19 GB of commit with a GPU), which
            # llm_local fits to this computer before it starts. Counted here, it ended the page over and over once the model loaded.
            more = {pid for pid, parent in parents.items() if parent in mine and pid not in mine and names.get(pid) != 'lastbook-llm.exe'}
            mine |= more
            grew = bool(more)
        for pid in list(self.handles):
            if pid not in mine:
                self.k.CloseHandle(self.handles.pop(pid))
        for pid in mine - set(self.handles):
            h = self.k.OpenProcess(self.QUERY_AND_END, False, pid)
            if h:
                self.handles[pid] = h

    def sizes(self):
        out = {}
        for pid, h in self.handles.items():
            m = _PageMemory()
            m.cb = ctypes.sizeof(m)
            if self.psapi.GetProcessMemoryInfo(h, ctypes.byref(m), m.cb):
                out[pid] = m.PrivateUsage
        return out

    def end(self, pid):
        h = self.handles.get(pid)
        return bool(h and self.k.TerminateProcess(h, 1))


class Pace:
    """Holds a worker until the window has had time for the last large answer. A worker held here holds its lane, so the page's requests wait in line, in Python."""

    def __init__(self, rate):
        self.rate, self.free_at = rate, 0.0
        self.lock = threading.Lock()

    def wait(self, n):
        with self.lock:
            now = time.time()
            start = max(now, self.free_at)
            self.free_at = start + n / self.rate
        if start > now:
            time.sleep(start - now)


class Shell:
    def __init__(self, server_module, data, *, language_file=None):
        self.n = net()
        spool = Path(data) / 'derived' / 'spool'
        spool.mkdir(parents=True, exist_ok=True)
        for old in spool.glob('lb-spool-*'):   # left by a run that was killed. A young one may be another copy's, still in use.
            try:
                if time.time() - old.stat().st_mtime > 86400:
                    old.unlink()
            except OSError:
                pass
        self.store = Path(data) / 'derived' / 'webview'
        physical = _Processes().physical() or 2 * WHOLE_COPIES * B.WHOLE_MAX
        self.b = B.Bridge(server_module, 'buffer', B.ORIGIN_WINDOWS, tmpdir=str(spool),
                          whole_max=min(B.WHOLE_MAX, physical // (2 * WHOLE_COPIES)), language_file=language_file)
        self.core = self.env = self.form = self.view = None
        self.frames = set()     # pythonnet would let these go otherwise, and with them the frame's event
        self.pace = Pace(PACE_BYTES)
        self.fullscreen_was = None
        self.last_restart = 0.0
        self.renderers = frozenset()
        self.ended_why = None       # why this program ended a renderer, until the web view says it has gone
        self.telling = False
        self.frame = None

    # ---- window
    def build(self):
        n, Forms, Drawing = self.n, self.n.Forms, self.n.Drawing
        Forms.Application.EnableVisualStyles()
        Forms.Application.SetCompatibleTextRenderingDefault(False)
        back = Drawing.Color.FromArgb(*SURFACE[light_theme()])
        form = self.form = Forms.Form()
        form.Text = TITLE
        form.BackColor = back
        form.StartPosition = Forms.FormStartPosition.CenterScreen
        scale = ctypes.windll.user32.GetDpiForSystem() / 96     # the form itself says 96 until it has a handle
        area = Forms.Screen.PrimaryScreen.WorkingArea
        form.Size = Drawing.Size(min(int(WIDTH * scale), area.Width), min(int(HEIGHT * scale), area.Height))     # Size, not ClientSize: the border counts against the screen
        try:
            icon_dir = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent / 'packaging' / 'icon'))
            form.Icon = Drawing.Icon(str(icon_dir / 'Lastbook.ico'))
        except Exception:
            traceback.print_exc()
            try:
                form.Icon = Drawing.Icon.ExtractAssociatedIcon(sys.executable)
            except Exception:
                pass
        view = self.view = n.WvForms.WebView2()
        view.AllowExternalDrop = False      # a file dropped on the window would be a navigation to it
        view.DefaultBackgroundColor = back
        view.Dock = Forms.DockStyle.Fill
        view.CoreWebView2InitializationCompleted += guarded(self.on_ready)
        form.Controls.Add(view)
        if band_ok():
            self.frame = Frame(self)
            form.Paint += guarded(self.frame.paint)
            form.SizeChanged += guarded(lambda s, a: self.fit_band())
            form.HandleCreated += guarded(lambda s, a: self.frame.attach(int(form.Handle.ToInt64())))     # a new handle needs the frame again
            form.Shown += guarded(lambda s, a: self.fit_band())    # the system places its buttons once the window is on screen
        dark_menus()
        form.Load += guarded(lambda s, a: (self.fit_min(), self.follow_theme(), self.fit_band(), self.start_runtime()))
        from Microsoft.Win32 import SystemEvents
        SystemEvents.UserPreferenceChanged += guarded(lambda s, a: self.ui(self.follow_theme))   # light or dark changed in Settings
        Forms.Application.Run(form)

    def fit_min(self):
        """MIN_SIZE is the page's own area, so the smallest window still has the sidebar and never the phone layout. Once the form has a handle
        its frame is known: the minimum is that area plus the frame."""
        form = self.form
        scale = ctypes.windll.user32.GetDpiForSystem() / 96
        frame_w, frame_h = form.Width - form.ClientSize.Width, form.Height - form.ClientSize.Height
        form.MinimumSize = self.n.Drawing.Size(int(MIN_SIZE[0] * scale) + frame_w, int(MIN_SIZE[1] * scale) + frame_h)

    def fit_band(self):
        if self.frame is None:
            return
        h = self.frame.layout()
        if h and self.core is not None:
            self.core.ExecuteScriptAsync(self.frame_script())

    def frame_script(self):
        return FRAME_SCRIPT % (json.dumps(self.b.origin), self.frame.cap_h, self.frame.cap_top)

    def accent_script(self):
        shades = accent_shades()
        return ACCENT_SCRIPT % (json.dumps(self.b.origin), json.dumps(shades[0]), json.dumps(shades[1])) if shades else None

    def follow_theme(self):
        light = light_theme()
        back = self.n.Drawing.Color.FromArgb(*SURFACE[light])
        self.form.BackColor = back
        self.view.DefaultBackgroundColor = back
        caption(int(self.form.Handle.ToInt64()), light)
        script = self.accent_script()
        if self.core is not None and script:
            self.core.ExecuteScriptAsync(script)    # the accent may have changed with the theme

    def start_runtime(self):
        """The control's own CreationProperties has no way to set the crash report option, so the runtime's environment is made here. It finishes on this thread's
        message loop, so nothing may wait for it: a timer looks."""
        n = self.n
        options = n.Core.CoreWebView2EnvironmentOptions()
        options.AdditionalBrowserArguments = BROWSER_ARGS
        options.IsCustomCrashReportingEnabled = True    # with this on, Windows does not send a crash's report to Microsoft. It stays in the data folder.
        try:
            options.ScrollBarStyle = n.Core.CoreWebView2ScrollbarStyle.FluentOverlay    # Windows 11's thin scroll bars; an older runtime keeps its own
        except AttributeError:
            pass
        task = n.Core.CoreWebView2Environment.CreateAsync(None, str(self.store), options)
        timer = self.env_timer = n.Forms.Timer()
        timer.Interval = 20

        def look(s, a):
            if not task.IsCompleted:
                return
            timer.Stop()
            if task.IsFaulted:
                print('WebView2 environment:', task.Exception, flush=True)
                message(NO_RUNTIME)
                self.form.Close()
                return
            self.view.EnsureCoreWebView2Async(task.Result)

        timer.Tick += guarded(look)
        timer.Start()

    def on_ready(self, sender, args):
        if not args.IsSuccess:
            print('WebView2 did not start:', args.InitializationException, flush=True)
            message(NO_RUNTIME if 'NotFound' in str(type(args.InitializationException)) else f'Lastbook could not open its window.\n\n{args.InitializationException.Message}')
            self.form.Close()
            return
        Core = self.n.Core
        core = self.core = self.view.CoreWebView2
        self.env = core.Environment
        s = core.Settings
        s.IsWebMessageEnabled = False
        s.AreHostObjectsAllowed = False
        s.AreDevToolsEnabled = False
        s.IsPasswordAutosaveEnabled = False
        s.IsGeneralAutofillEnabled = False
        s.IsReputationCheckingRequired = False     # no lookups from an offline library
        s.IsStatusBarEnabled = False
        if self.frame is not None:
            try:
                s.IsNonClientRegionSupportEnabled = True    # the page's app-region: drag is the caption; nothing else is enabled by it
                core.AddScriptToExecuteOnDocumentCreatedAsync(self.frame_script())
                core.DOMContentLoaded += guarded(lambda s_, a: self.core.ExecuteScriptAsync(self.frame_script()))   # the band's height now, if it changed since
            except Exception:
                traceback.print_exc()
                self.frame.release()
                self.frame = None
        core.AddWebResourceRequestedFilter('*', Core.CoreWebView2WebResourceContext.All, Core.CoreWebView2WebResourceRequestSourceKinds.All)
        core.WebResourceRequested += guarded(self.on_request)
        core.NavigationStarting += guarded(self.on_nav)
        core.FrameNavigationStarting += guarded(self.on_frame_nav)
        core.FrameCreated += guarded(self.on_frame_created)
        core.NewWindowRequested += guarded(self.on_new_window)
        core.PermissionRequested += guarded(self.on_permission)
        core.LaunchingExternalUriScheme += guarded(self.on_external_scheme)
        core.ProcessFailed += guarded(self.on_process_failed)
        core.ContainsFullScreenElementChanged += guarded(self.on_fullscreen)
        core.ContextMenuRequested += self.on_context_menu     # not guarded: it refuses the whole menu itself if anything goes wrong
        core.DownloadStarting += guarded(self.on_download)
        core.IsDefaultDownloadDialogOpenChanged += guarded(self.on_download_flyout)
        core.AddScriptToExecuteOnDocumentCreatedAsync(self.b.top_script())    # WebView2 runs this in every frame; it returns at once there
        accent = self.accent_script()
        if accent:
            core.AddScriptToExecuteOnDocumentCreatedAsync(accent)    # so are these two colours; the script itself keeps to the app's top page
        core.DocumentTitleChanged += guarded(lambda s, a: setattr(self.form, 'Text', str(core.DocumentTitle) or TITLE))   # the page's name in the title bar and taskbar, as Explorer does
        self.watch_keys()
        # The runtime lets a page have one download and then refuses the rest without asking. on_download judges every one, and only the app's own pass.
        core.Profile.SetPermissionStateAsync(Core.CoreWebView2PermissionKind.MultipleAutomaticDownloads, self.b.origin, Core.CoreWebView2PermissionState.Allow)
        note(kind='ready', browser=str(self.env.BrowserVersionString), pid=int(core.BrowserProcessId))
        core.Navigate(self.b.origin + '/')
        threading.Thread(target=self.watch_memory, daemon=True, name='memory').start()

    def watch_keys(self):
        """Ctrl+F, Ctrl+G and F3 open the runtime's own find bar, over the toolbar and outside the page. The page has its own search for them, so the
        browser's part of those keys is switched off and the key goes on to the page. The WinForms control keeps its controller private."""
        flags = self.n.System.Reflection.BindingFlags
        field = self.view.GetType().GetField('_coreWebView2Controller', flags.NonPublic | flags.Instance)
        controller = field.GetValue(self.view) if field is not None else None
        if controller is None:
            print('no controller: the find bar keys stay the runtime\'s', flush=True)
            return
        self.controller = controller    # pythonnet would let it go otherwise, and with it the event
        controller.AcceleratorKeyPressed += guarded(self.on_key)

    def on_key(self, sender, args):
        vk = int(args.VirtualKey)
        ctrl = bool(ctypes.windll.user32.GetKeyState(0x11) & 0x8000)
        if vk == 0x72 or (ctrl and vk in (0x46, 0x47)):     # F3; Ctrl+F, Ctrl+G
            args.IsBrowserAcceleratorKeyEnabled = False
        if vk == 0x20 and args.KeyEventKind == self.n.Core.CoreWebView2KeyEventKind.SystemKeyDown and not ctrl:
            args.Handled = True     # Alt+Space: the window's menu (Restore, Move, Size, Minimise, Maximise, Close), which the web view keeps to itself
            self.ui(self.alt_space)     # after this key's handler: the menu runs its own message loop

    def alt_space(self):
        """Opens the window's menu where Windows opens it for Alt+Space: under the top-left corner of the title bar."""
        hwnd = int(self.form.Handle.ToInt64())
        f = wt.RECT()
        system_dll('dwmapi').DwmGetWindowAttribute(wt.HWND(hwnd), 9, ctypes.byref(f), ctypes.sizeof(f))     # DWMWA_EXTENDED_FRAME_BOUNDS: the visible frame
        scale = (ctypes.windll.user32.GetDpiForWindow(wt.HWND(hwnd)) or 96) / 96
        cap = self.frame.cap_h if self.frame is not None else 31
        system_menu(hwnd, f.left + int(8 * scale), f.top + int(cap * scale))

    def ui(self, fn):
        try:
            self.form.BeginInvoke(self.n.System.Action(guarded(fn)))
            return True
        except Exception:     # the window has closed
            return False

    # ---- requests
    def on_request(self, sender, args):
        req = args.Request
        uri = str(req.Uri)
        if not (uri == self.b.origin or uri.startswith(self.b.origin + '/')):
            if uri.split(':', 1)[0].lower() in BLOCKED_SCHEMES:
                args.Response = self.env.CreateWebResourceResponse(None, 403, 'Blocked', '')
                note(kind='blocked', uri=uri[:300], ctx=str(args.ResourceContext))
            return
        method = str(req.Method)
        headers = [(str(h.Key), str(h.Value)) for h in req.Headers]
        body = self.read_body(req.Content) if method == 'POST' else None
        document = args.ResourceContext == self.n.Core.CoreWebView2WebResourceContext.Document
        deferral = args.GetDeferral()
        self.b.fetch(method, uri, headers, body, lambda r: self.answer(args, deferral, method, r), is_document=document)

    def read_body(self, stream):
        """A page can POST any size. One byte past the limit is enough for the bridge to refuse it, so no more than that is read."""
        if stream is None:
            return b''
        n = self.n
        chunk = n.System.Array.CreateInstance(n.System.Byte, 65536)
        out = n.IO.MemoryStream()
        while out.Length <= B.MAX_POST:
            got = stream.Read(chunk, 0, chunk.Length)
            if got <= 0:
                break
            out.Write(chunk, 0, got)
        arr = out.ToArray()
        size = arr.Length
        if not size:
            return b''
        buf = ctypes.create_string_buffer(size)
        n.Marshal.Copy(arr, 0, n.System.IntPtr(ctypes.addressof(buf)), size)
        return buf.raw

    def to_net(self, data):
        n = self.n
        arr = n.System.Array.CreateInstance(n.System.Byte, len(data))
        n.Marshal.Copy(n.System.IntPtr(ctypes.cast(ctypes.c_char_p(data), ctypes.c_void_p).value), arr, 0, len(data))
        return arr

    def answer(self, args, deferral, method, r):
        """On a worker, or on the UI thread for a refusal. The copy into .NET happens here, so the UI thread only hands it over."""
        stream, status, reason, headers = None, r.status, r.reason, r.headers
        n = self.n
        try:
            if r.path:
                options = n.IO.FileOptions.DeleteOnClose if r.delete else n.IO.FileOptions.SequentialScan
                stream = n.IO.FileStream(r.path, n.IO.FileMode.Open, n.IO.FileAccess.Read, n.IO.FileShare.ReadWrite | n.IO.FileShare.Delete, 65536, options)
                if r.lane in PACE_LANES:
                    self.pace.wait(int(stream.Length))
            elif r.body:
                if len(r.body) >= PACE_FROM and r.lane in PACE_LANES:
                    self.pace.wait(len(r.body))
                stream = n.IO.MemoryStream(self.to_net(r.body))
            elif method != 'HEAD' and status not in (204, 304):
                stream = n.IO.MemoryStream()
        except Exception:
            traceback.print_exc()
            stream, status, reason, headers = n.IO.MemoryStream(), 500, 'Could Not Read', []
        r.body = None

        def complete():
            try:
                head = '\r\n'.join(f'{k}: {v}' for k, v in headers)
                args.Response = self.env.CreateWebResourceResponse(stream, status, reason or 'OK', head)
            finally:
                deferral.Complete()
                r.release()

        if not self.ui(complete):
            r.release()

    # ---- what may go where
    def act(self, what, where):
        note(kind='act', what=what, where=(where or '')[:300])
        if what == 'inside':
            self.ui(lambda: self.core.Navigate(where))

    def on_nav(self, sender, args):
        uri = str(args.Uri)
        allowed = self.b.top_url_ok(uri)
        note(kind='nav', uri=uri[:300], allowed=allowed, user=bool(args.IsUserInitiated))
        if allowed:
            return
        args.Cancel = True
        self.act(*self.b.new_window(uri, True, bool(args.IsUserInitiated)))

    def on_frame_nav(self, sender, args):
        uri = str(args.Uri)
        allowed = self.b.frame_url_ok(uri)
        note(kind='frame-nav', uri=uri[:300], allowed=allowed)
        if not allowed:
            args.Cancel = True

    def on_frame_created(self, sender, args):
        """Only frames the app's own page made raise this. A frame inside a saved page raises it on its parent frame, which nothing here listens to.
        The frame's first real navigation is the app's: the UI writes a new iframe with its src for every document. That one may get one whole large
        answer. Any later one may be the saved page now in the frame moving itself, and this event cannot tell, so it gets none."""
        frame = args.Frame
        self.frames.add(frame)
        self.b.drop_waiting()
        first = [True]

        def started(s, e):
            uri = str(e.Uri)
            allowed = self.b.frame_url_ok(uri)
            note(kind='app-frame-nav', uri=uri[:300], allowed=allowed, first=first[0])
            if not allowed:
                e.Cancel = True     # this frame's own event: a Cancel on the web view's FrameNavigationStarting alone did not hold here
            elif uri.startswith(self.b.origin + '/'):
                if first[0]:
                    self.b.give_ticket(uri)
                first[0] = False

        frame.NavigationStarting += guarded(started)
        frame.Destroyed += guarded(lambda s, e: self.frames.discard(frame))

    def on_new_window(self, sender, args):
        args.Handled = True     # with no NewWindow set, this cancels it: nothing opens
        uri = str(args.Uri)
        source = args.OriginalSourceFrameInfo
        from_top = source is not None and source.FrameKind == self.n.Core.CoreWebView2FrameKind.MainFrame
        gesture = bool(args.IsUserInitiated)
        note(kind='new-window', uri=uri[:300], from_top=from_top, user=gesture)
        self.act(*self.b.new_window(uri, from_top, gesture))

    def on_permission(self, sender, args):
        Core = self.n.Core
        note(kind='permission', what=str(args.PermissionKind), uri=str(args.Uri)[:200], user=bool(args.IsUserInitiated))
        if args.PermissionKind == Core.CoreWebView2PermissionKind.MultipleAutomaticDownloads:
            args.State = Core.CoreWebView2PermissionState.Allow     # refused once, the app's own export stops working until a reload. on_download still judges every one.
            return
        args.State = Core.CoreWebView2PermissionState.Deny
        note(kind='permission-denied', what=str(args.PermissionKind), uri=str(args.Uri)[:200])

    def on_download(self, sender, args):
        """The runtime's own flow saves silently to Downloads and offers to open the file, from a flyout over the window. Here nothing is saved unless
        it is the app's own and the person chose where: the chat's export, asked here.
        A frame that lands on a file type no web view can show also arrives here, and is refused. Saved pages cannot start a download at all:
        their sandbox has no allow-downloads."""
        op = args.DownloadOperation
        uri = str(op.Uri)
        export = uri.startswith('blob:' + self.b.origin + '/')
        note(kind='download', uri=uri[:300], export=export, path=str(args.ResultFilePath))
        if not export:
            args.Cancel = True
            return
        args.Handled = True     # no flyout
        deferral = args.GetDeferral()
        suggested = str(args.ResultFilePath)

        def choose():
            try:
                self.ask_save(args, suggested)
            finally:
                deferral.Complete()

        self.ui(choose)

    def ask_save(self, args, suggested):
        Forms = self.n.Forms
        d = Forms.SaveFileDialog()
        d.FileName = Path(suggested).name
        d.OverwritePrompt = True
        if d.ShowDialog(self.form) == Forms.DialogResult.OK:
            args.ResultFilePath = d.FileName
        else:
            args.Cancel = True

    def on_context_menu(self, sender, args):
        try:
            items = args.MenuItems
            Separator = self.n.Core.CoreWebView2ContextMenuItemKind.Separator
            for i in range(items.Count - 1, -1, -1):
                if items[i].Kind != Separator and str(items[i].Name) not in MENU_KEEP:
                    items.RemoveAt(i)
            for i in range(items.Count - 1, -1, -1):      # separators with nothing left between them
                alone = items[i].Kind == Separator and (i == items.Count - 1 or i == 0 or items[i - 1].Kind == Separator)
                if alone:
                    items.RemoveAt(i)
            if not items.Count:
                args.Handled = True     # no menu at all
        except Exception:
            traceback.print_exc()
            args.Handled = True

    def on_download_flyout(self, sender, args):
        if self.core.IsDefaultDownloadDialogOpen:      # Ctrl+J, or the context menu's own save: it offers to open files, so it does not stay
            self.core.CloseDefaultDownloadDialog()

    def on_external_scheme(self, sender, args):
        args.Cancel = True
        note(kind='scheme-refused', uri=str(args.Uri)[:200])

    # ---- the rest of being a window
    def on_process_failed(self, sender, args):
        Kind = self.n.Core.CoreWebView2ProcessFailedKind
        kind = args.ProcessFailedKind
        print('web view process failed:', kind, args.Reason, flush=True)
        note(kind='process-failed', what=str(kind), reason=str(args.Reason))
        if kind == Kind.BrowserProcessExited:
            message('The window part of Lastbook stopped working, so Lastbook will close. Your library is not affected.')
            self.ui(self.form.Close)
        elif self.ended_why and kind in (Kind.RenderProcessExited, Kind.FrameRenderProcessExited):
            why, self.ended_why = self.ended_why, None
            self.b.drop_waiting(0)
            self.core.Navigate(self.b.origin + '/')
            self.ui(lambda: self.tell(why))
        elif kind in (Kind.RenderProcessExited, Kind.RenderProcessUnresponsive):
            now = time.time()
            if now - self.last_restart > RESTART_GAP:
                self.last_restart = now
                self.core.Navigate(self.b.origin + '/')

    def tell(self, text):
        if self.telling:    # one at a time: a box does not stop this thread's other work, so they would stack
            return
        self.telling = True
        try:
            ctypes.windll.user32.MessageBoxW(int(self.form.Handle.ToInt64()), text, TITLE, 0x40)
        finally:
            self.telling = False

    # ---- a page's memory
    def note_renderers(self):
        Renderer = self.n.Core.CoreWebView2ProcessKind.Renderer
        self.renderers = frozenset(int(p.ProcessId) for p in self.env.GetProcessInfos() if p.Kind == Renderer)

    def watch_memory(self):
        """On a thread of its own: a page can keep the window's thread busy. Counts private bytes, which a page cannot hide by not touching them."""
        procs = _Processes()
        limit = min(MEMORY_LIMIT_MOST, (procs.physical() // 2) or MEMORY_LIMIT_MOST)
        GC = self.n.System.GC
        last_list = 0.0
        ended_at = 0.0
        while True:
            time.sleep(MEMORY_EVERY)
            try:
                now = time.monotonic()
                if now - last_list >= 1:
                    last_list = now
                    procs.refresh()
                    self.ui(self.note_renderers)
                sizes = procs.sizes()
                total = sum(sizes.values()) - sizes.get(os.getpid(), 0) + GC.GetTotalMemory(False)
                if total <= limit or now - ended_at < MEMORY_QUIET or self.ended_why:
                    continue
                candidates = [p for p in self.renderers if p in sizes]
                if not candidates:
                    continue
                pid = max(candidates, key=sizes.get)
                ended_at = now
                print(f'ending renderer {pid}: the web view holds {total} bytes, {sizes[pid]} of it there', flush=True)
                note(kind='memory-limit', total=total, pid=pid, size=sizes[pid])
                self.ended_why = TOO_BIG
                if not procs.end(pid):
                    self.ended_why = None
                    print('could not end it', ctypes.get_last_error(), flush=True)
            except Exception:
                traceback.print_exc()

    def on_fullscreen(self, sender, args):
        Forms = self.n.Forms
        form = self.form
        if self.core.ContainsFullScreenElement:
            normal = form.Bounds if form.WindowState == Forms.FormWindowState.Normal else form.RestoreBounds
            self.fullscreen_was = (form.WindowState, form.FormBorderStyle, normal)
            form.WindowState = Forms.FormWindowState.Normal   # a maximized window would keep the taskbar
            form.FormBorderStyle = getattr(Forms.FormBorderStyle, 'None')   # a Python keyword
            form.WindowState = Forms.FormWindowState.Maximized
        elif self.fullscreen_was:
            state, border, normal = self.fullscreen_was
            self.fullscreen_was = None
            form.WindowState = Forms.FormWindowState.Normal
            form.FormBorderStyle = border
            form.Bounds = normal    # WinForms would size it again from its client with a caption added, which the band's window has not
            form.WindowState = state
        self.fit_band()


def collect_loop(GC):
    """Every answer becomes large .NET arrays: ours, and a new one per read in WebView2's stream wrapper. Large arrays leave only with a full
    collection, and with a lot of free RAM .NET can put that off for gigabytes. Nothing long-lived is in this heap, so a collection costs little."""
    limit = HEAP_SOFT
    while True:
        time.sleep(0.25)
        if GC.GetTotalMemory(False) > limit:
            GC.Collect()
            limit = max(HEAP_SOFT, GC.GetTotalMemory(False) * 2)


def run(server_module, data, *, language_file=None):
    """Blocks until the window closes. WinForms and WebView2 need a single-threaded apartment, which Python's main thread is not."""
    ctypes.windll.user32.SetProcessDPIAware()
    shell = Shell(server_module, data, language_file=language_file)
    failure = []

    def body():
        try:
            shell.build()
        except Exception as e:
            traceback.print_exc()
            failure.append(e)

    n = shell.n
    threading.Thread(target=collect_loop, args=(n.System.GC,), daemon=True, name='collect').start()
    thread = n.Threading.Thread(n.Threading.ThreadStart(body))
    thread.SetApartmentState(n.Threading.ApartmentState.STA)
    thread.Start()
    thread.Join()
    if failure:
        raise failure[0]
    print('window closed', flush=True)
    os._exit(0)     # the engine's threads and any web view reads still under way end here
