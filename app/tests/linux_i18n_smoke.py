"""Offline localization smoke check for the installed Ubuntu package.

Run as an ordinary user in an isolated X11 and D-Bus session:
  xvfb-run -a -s '-screen 0 1280x900x24 -nolisten tcp' dbus-run-session -- \
    bash -c 'openbox & exec python3 -B app/tests/linux_i18n_smoke.py'
Requires xdotool, python3-pyatspi and the packaged lastbook command.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import linux_at
import pyatspi


def key(*keys):
    subprocess.run(['xdotool', 'key', '--clearmodifiers', *keys], check=True)


def wait_for(check, message, deadline=30):
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        try:
            if value := check():
                return value
        except SystemExit:
            pass
        time.sleep(.2)
    raise AssertionError(message)


def children(proc):
    return linux_at.walk(linux_at.app(str(proc.pid), tries=1))


def text(proc):
    nodes = children(proc)
    return linux_at.text(nodes) + '\n' + '\n'.join(
        linux_at.own_text(n['acc']) for n in nodes if n['role'] == pyatspi.ROLE_STATUS_BAR)


def wait_text(proc, name):
    try:
        return wait_for(lambda: name in text(proc), name)
    except AssertionError:
        print(text(proc), flush=True)
        raise


def select(proc, title, end):
    wait_text(proc, title)
    combos = [n for n in children(proc) if n['role'] == pyatspi.ROLE_COMBO_BOX]
    assert combos, 'no language select'
    for n in combos:
        if title in linux_at.words(n):
            break
    else:
        n = combos[0]
    assert n['acc'].queryComponent().grabFocus(), 'the select could not take focus'
    wait_for(lambda: n['acc'].getState().contains(pyatspi.STATE_FOCUSED), 'language select did not take focus')
    # The chooser has two options. Move directly from the saved/default option
    # without depending on when WebKitGTK's separate popup is ready for keys.
    key('Down' if end else 'Up')


def press(proc, name):
    wait_text(proc, name)
    result = linux_at.press(children(proc), name)
    assert result['ok'], result


def quit_app(proc):
    key('ctrl+q')
    proc.wait(timeout=12)
    assert proc.returncode == 0, proc.returncode


def run(tmp):
    tmp = Path(tmp)
    env = {**os.environ, 'XDG_CONFIG_HOME': str(tmp / 'config'), 'XDG_DATA_HOME': str(tmp / 'userdata'),
           'XDG_CACHE_HOME': str(tmp / 'cache'), 'LC_ALL': 'C.UTF-8'}
    env.pop('LASTBOOK_DATA', None)
    path = tmp / 'config/Lastbook/ui-language.json'
    library = tmp / 'one/LastbookData'
    other = tmp / 'two/LastbookData'
    for lib in (library, other):
        (lib / 'library-data').mkdir(parents=True)
        (lib / 'library-data/catalog.json').write_text('[]', encoding='utf-8')

    def start(arguments=()):
        return subprocess.Popen(['lastbook', *arguments], env=env)

    proc = start()
    try:
        wait_text(proc, 'Set up Lastbook')
        select(proc, 'Interface language', True)
        press(proc, 'Save language')
        wait_text(proc, 'Idioma guardado.')
        wait_text(proc, 'Configuración inicial de Lastbook')
        assert json.loads(path.read_text(encoding='utf-8')) == {'language': 'es-419'}
        print('PASS: first-run Spanish save in the installed WebView', flush=True)
        press(proc, 'Choose an existing library folder')
        wait_for(lambda: subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', '^Choose a folder$'],
                                        capture_output=True).returncode == 0, 'GTK chooser did not appear')
        key('ctrl+l')
        subprocess.run(['xdotool', 'type', '--', str(library.parent)], check=True)
        key('Return')
        wait_text(proc, 'Open the library')
        press(proc, 'Open the library')
        wait_text(proc, 'Guías')
        assert json.loads(path.with_name('settings.json').read_text(encoding='utf-8')) == {'library': str(library)}
        print('PASS: Setup used an existing local library and relaunched into Spanish', flush=True)
        quit_app(proc)

        env['XDG_DATA_HOME'] = str(tmp / 'fresh-profile')
        env['XDG_CACHE_HOME'] = str(tmp / 'fresh-cache')
        proc = start(('--data', str(other)))
        wait_text(proc, 'Guías')
        wait_text(proc, 'Buscar en la biblioteca')
        assert json.loads(path.read_text(encoding='utf-8')) == {'language': 'es-419'}
        print('PASS: restart with a new WebView profile and different library', flush=True)
        press(proc, 'Ajustes')
        wait_text(proc, 'Biblioteca e IA local')
        select(proc, 'Idioma de la interfaz', False)
        press(proc, 'Guardar idioma')
        wait_text(proc, 'Language saved.')
        wait_text(proc, 'Library and local AI')
        assert json.loads(path.read_text(encoding='utf-8')) == {'language': 'en'}
        press(proc, 'Back to the library')
        wait_text(proc, 'Guides')
        print('PASS: Settings switched back to English without relaunch', flush=True)
        quit_app(proc)
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='lastbook-native-i18n-') as tmp:
        run(tmp)
