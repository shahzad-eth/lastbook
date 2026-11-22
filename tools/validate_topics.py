#!/usr/bin/env python3
"""Check curated topic files: every doc id exists, pages are in range, ZIM paths resolve.

  python3 tools/validate_topics.py [--data /path/to/LastbookData] [content/topics/water.json ...]

The library is looked for in --data, then LASTBOOK_DATA, then this source tree, the same data folder the app takes: the
folder that holds library-data/. With no topic files named, every file in content/topics/ is checked.

Encyclopedia (ZIM) paths are looked up in the ZIM files themselves, under library-data/collections/, with libzim. Nothing
is asked of a server and no port is used. A ZIM file that is not in this library counts as an error, because the guide
would point at nothing here; a smaller pack may hold fewer ZIM files than the guides cite.
"""
import argparse, json, os, sys, urllib.parse
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]


def library(args):
    """(the library-data folder, the topic files named). Exits with a plain message when there is no library to check against."""
    ap = argparse.ArgumentParser(description='Check curated topic files against a library.')
    ap.add_argument('--data', help='the data folder, the one that holds library-data/ (default: LASTBOOK_DATA, then this source tree)')
    ap.add_argument('files', nargs='*', type=Path, help='topic files to check (default: every file in content/topics/)')
    a = ap.parse_args(args)
    lib = Path(a.data or os.environ.get('LASTBOOK_DATA') or HERE) / 'library-data'
    if not (lib / 'catalog.json').is_file():
        sys.exit(f'No library at {lib} (no catalog.json). Pass --data or set LASTBOOK_DATA to the folder that holds library-data/.')
    return lib, a.files


def items(t):
    for k in ('prepare', 'learn'):
        yield from ((k, i) for i in t.get(k, []))
    for c in t.get('choices', []):
        yield from (('choice:' + c.get('id', '?'), i) for i in c.get('read', []))
    for s in t.get('route', []):
        yield from (('route:' + str(s.get('title')), i) for i in s.get('read', []))
    for l in t.get('limits', []):
        if l.get('doc') or l.get('zim'): yield ('limits', l)


ARCHIVES = {}
def zim_problem(lib, ref):
    """None when 'zim/<file>.zim/<Article_path>' names an entry that is in the library, otherwise why not. The path is read
    the way the app reads the address it is given: percent-escapes decoded, anything after '?' or '#' left out."""
    parts = urllib.parse.urlsplit('/' + ref.lstrip('/')).path.split('/', 3)
    name = urllib.parse.unquote(parts[2]) if len(parts) > 2 else ''
    entry = urllib.parse.unquote(parts[3]) if len(parts) > 3 else ''
    if parts[1] != 'zim' or not name.lower().endswith('.zim') or Path(name).name != name or not entry:
        return 'not of the form zim/<file>.zim/<Article_path>'
    path = lib / 'collections' / name
    if not path.is_file(): return f'{name} is not in this library'
    try:
        if name not in ARCHIVES:
            from libzim.reader import Archive
            ARCHIVES[name] = Archive(path)
        return None if ARCHIVES[name].has_entry_by_path(entry) else 'no such entry'
    except ImportError:
        return 'libzim is not installed (it is in the requirements file for your platform)'
    except Exception as e:
        return type(e).__name__              # libzim's own messages carry the full file path


def main(args):
    lib, files = library(args)
    cat = {r['id']: r for r in json.loads((lib / 'catalog.json').read_text(encoding='utf-8'))}
    files = files or sorted((HERE / 'content/topics').glob('*.json'))
    topics = set()
    for folder in sorted({f.parent for f in files}):   # related ids are checked inside the folder the named files live in
        for p in folder.glob('*.json'):
            try:
                d = json.loads(p.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and isinstance(d.get('id'), str):
                topics.add(d['id'])
    errors = 0
    for f in files:
        t = json.loads(f.read_text(encoding='utf-8')); n = 0
        for where, i in items(t):
            n += 1
            if i.get('zim'):
                why = zim_problem(lib, i['zim'])
                if why: print(f'{f.name} {where}: ZIM path fails {i["zim"]}: {why}'); errors += 1
                continue
            r = cat.get(i.get('doc'))
            if not r: print(f'{f.name} {where}: unknown doc {i.get("doc")}'); errors += 1; continue
            if r['kind'] == 'metadata': print(f'{f.name} {where}: use the video id, not metadata {i["doc"]}'); errors += 1
            p = i.get('page')
            if p is not None:
                if not isinstance(p, int) or isinstance(p, bool) or p < 1:
                    print(f'{f.name} {where}: page {p!r} is not a page number'); errors += 1
                elif r.get('pages') and p > r['pages']:
                    print(f'{f.name} {where}: page {p} out of range for {i["doc"]} ({r["pages"]})'); errors += 1
            if not i.get('label') and where != 'limits': print(f'{f.name} {where}: missing label for {i.get("doc")}'); errors += 1
        rel = t.get('related', [])
        if not isinstance(rel, list):
            print(f'{f.name} related: not a list'); errors += 1
        else:
            for r in rel:
                if not isinstance(r, str) or r not in topics: print(f'{f.name} related: unknown topic {r!r}'); errors += 1
        print(f'{f.name}: {n} references checked')
    print('ERRORS', errors)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
