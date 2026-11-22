"""Unpacking a pack and switching to it, so that a working library is never broken.

  <parent>/LastbookData.setup/unpack/LastbookData    the new library, built here from the pack's zip files
  <parent>/LastbookData                             the library Lastbook opens

Every member of a zip is checked before anything is written: a relative name under LastbookData/, no '..', no drive or root,
no symbolic link, no device, and a total no larger than the manifest's installed_bytes. Files are written as <name>.partial and
renamed when whole, so an unpack that stops (a crash, power) carries on where it was. Switching is one rename on one disk.
An upgrade first moves the old library aside to LastbookData.old-<date>; when the app restarts it opens the new one, and only if
that fails to open is the old one put back (apply_pending, called by app/main.py before the engine starts).
"""
import json
import os
import re
import shutil
import stat
import time
import zipfile
from pathlib import Path, PurePosixPath

DATA_NAME = 'LastbookData'
CATALOG = Path('library-data') / 'catalog.json'
SLACK = 1.02            # installed_bytes is measured; a zip's members may add a little in directory entries
SPACE_MARGIN = 2 * 10 ** 9
PENDING = 'pending.json'
COPY = 4 * 1024 * 1024


class Refused(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _my_sid():
    """This account's SID, from Windows' own whoami (a name can fail to map, for example under a service or ssh)."""
    import subprocess
    whoami = Path(os.environ.get('SystemRoot') or 'C:\\Windows') / 'System32' / 'whoami.exe'
    out = subprocess.run([str(whoami), '/user', '/fo', 'csv', '/nh'], capture_output=True, timeout=30, creationflags=0x08000000)
    m = re.search(r'"(S-1-[0-9-]+)"', out.stdout.decode('utf-8', 'replace'))
    if not m:
        raise OSError('no SID for this account')
    return m.group(1)


def private_folder(path):
    """Makes the folder if it is not there and returns True if this user can save in it. On Windows a folder it makes is closed to
    other accounts, or not used: a folder at the top of a drive otherwise lets every signed-in user change what is inside. The rights
    are set with Windows' own icacls to this account, SYSTEM and Administrators, by SID. No admin rights needed."""
    import subprocess
    import tempfile
    p = Path(path)
    try:
        made = not p.exists()
        p.mkdir(parents=True, exist_ok=True)
        if made and os.name == 'nt':
            icacls = Path(os.environ.get('SystemRoot') or 'C:\\Windows') / 'System32' / 'icacls.exe'
            try:
                r = subprocess.run([str(icacls), str(p), '/inheritance:r', '/grant:r', f'*{_my_sid()}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F',
                                    '*S-1-5-32-544:(OI)(CI)F'], capture_output=True, timeout=30, creationflags=0x08000000)
                closed = r.returncode == 0
            except (OSError, subprocess.SubprocessError):
                closed, r = False, None
            if not closed:
                print('setup: could not close the folder to other accounts, so it is not used:', r and r.stdout[-300:], flush=True)
                p.rmdir()
                return False
        with tempfile.TemporaryFile(dir=p):
            return True
    except (OSError, ValueError):
        return False


def is_library(folder):
    try:
        return (Path(folder) / CATALOG).is_file()
    except OSError:
        return False


def _member_parts(info, top_optional=False):
    name = info.filename
    if '\\' in name or '\x00' in name:
        raise Refused('unpack', f'The pack holds a file with a name Lastbook does not accept ({name[:80]!r}).')
    p = PurePosixPath(name)
    if p.is_absolute() or name.startswith('/') or (p.parts and ':' in p.parts[0]):
        raise Refused('unpack', f'The pack holds a file with an absolute path ({name[:80]!r}).')
    parts = [x for x in p.parts if x not in ('', '.')]
    if any(x == '..' for x in parts):
        raise Refused('unpack', f'The pack holds a file that would land outside the library ({name[:80]!r}).')
    if top_optional and parts and parts[0] != DATA_NAME:
        parts = [DATA_NAME] + parts     # a state map zip may hold its files at the top, without the LastbookData folder
    if not parts or parts[0] != DATA_NAME:
        raise Refused('unpack', f'The pack holds a file outside its LastbookData folder ({name[:80]!r}).')
    mode = (info.external_attr >> 16) & 0o170000
    if mode and mode not in (stat.S_IFREG, stat.S_IFDIR):
        raise Refused('unpack', f'The pack holds a link or a special file ({name[:80]!r}).')
    if info.flag_bits & 0x1:
        raise Refused('unpack', 'The pack is encrypted.')
    return parts


MAP_FIXED = {'map-set.json', 'derived/geo/national-status.json', 'derived/geo/socal-cells.json', 'library-data/geography/resources/atlas.sqlite'}
MAP_DIRS = {'', 'derived', 'derived/geo', 'library-data', 'library-data/geography', 'library-data/geography/resources'}
MAP_SQLITE = re.compile(r'derived/geo/[A-Za-z0-9._-]+\.sqlite')
SQLITE_SIDES = ('-wal', '-shm', '-journal')     # SQLite's own files beside a database: they move with it, or the new one could be damaged


def map_member(rel, is_dir=False):
    """Is this path (under LastbookData) one a state map zip may hold? docs/SETUP-API.md, State maps."""
    rel = rel.strip('/')
    if is_dir:
        return rel in MAP_DIRS
    return rel in MAP_FIXED or bool(MAP_SQLITE.fullmatch(rel))


def check_zip(path, installed_bytes=None, allowed=None):
    """(list of (info, parts), total bytes) once every member has passed, else Refused. allowed(rel, is_dir): a narrower rule."""
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as e:
        raise Refused('unpack', f'The pack could not be opened as a zip file ({type(e).__name__}).')
    with z:
        members, total, seen = [], 0, set()
        for info in z.infolist():
            parts = _member_parts(info, top_optional=allowed is not None)
            if allowed and not allowed('/'.join(parts[1:]), info.is_dir()):
                raise Refused('unpack', f'The map holds a file that is not part of a map ({info.filename[:80]!r}).')
            key = '/'.join(parts).lower()      # two names that differ only in case would overwrite each other on a Mac or Windows
            if key in seen and not info.is_dir():
                raise Refused('unpack', f'The pack holds the same file twice ({info.filename[:80]!r}).')
            seen.add(key)
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise Refused('unpack', f'The pack uses a kind of compression Lastbook does not accept ({info.filename[:80]!r}).')
            if info.compress_type == zipfile.ZIP_STORED and info.compress_size != info.file_size:
                raise Refused('unpack', f'The pack holds a stored file whose sizes disagree ({info.filename[:80]!r}).')
            total += info.file_size
            members.append((info, parts))
        # No two entries may share bytes: each one's local header (at least 30 bytes) and data must end before the next begins,
        # and the last before the central directory. Python's zipfile does not check this in every version that ships.
        spans = sorted(z.infolist(), key=lambda i: i.header_offset)
        end_of_data = getattr(z, 'start_dir', None)
        for a, b in zip(spans, spans[1:] + [None]):
            limit = b.header_offset if b is not None else end_of_data
            if limit is not None and a.header_offset + 30 + a.compress_size > limit:
                raise Refused('unpack', f'The pack holds entries that overlap ({a.filename[:80]!r}).')
    if installed_bytes is not None and total > installed_bytes * SLACK + 1024 * 1024:
        raise Refused('unpack', f'The pack unpacks to {total:,} bytes, more than the {installed_bytes:,} it should.')
    return members, total


def unpack(zip_path, into, installed_bytes, control, progress, allowed=None, verify=None):
    """Unpacks into <into>/LastbookData. progress(done, total). control.check() raises to pause or cancel. Resumable.
    allowed: map_member for a state map, which then needs map-set.json instead of a catalog."""
    members, total = check_zip(zip_path, installed_bytes, allowed)
    into = Path(into)
    into.mkdir(parents=True, exist_ok=True)
    plain = into.resolve()
    # Windows: written through the \\?\ form, which has no 260-character limit. The unpack folder sits deeper than the library
    # will (LastbookData.setup\unpack\), and with Windows' long paths off (the default) a pack's longest file could not be made.
    root = Path('\\\\?\\' + str(plain)) if os.name == 'nt' and not str(plain).startswith('\\\\') else plain
    done = 0
    with zipfile.ZipFile(zip_path) as z:
        for info, parts in members:
            control.check()
            dest = root.joinpath(*parts)
            if root not in dest.parents and dest != root:
                raise Refused('unpack', 'The pack holds a file that would land outside the library.')
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink():
                raise Refused('unpack', 'A link appeared in the unpack folder.')
            if dest.is_file() and dest.stat().st_size == info.file_size:
                done += info.file_size          # whole from an earlier run
                progress(done, total)
                continue
            part = dest.with_name(dest.name + '.partial')
            with z.open(info) as src, open(part, 'wb') as out:
                written = 0
                while True:
                    control.check()
                    b = src.read(COPY)
                    if not b:
                        break
                    written += len(b)
                    if written > info.file_size:        # stop at once, not after: a member never grows past its declared size
                        raise Refused('unpack', f'A file in the pack is larger than it says ({info.filename[:80]!r}).')
                    out.write(b)
                    done += len(b)
                    progress(done, total)
            if part.stat().st_size != info.file_size:
                raise Refused('unpack', f'A file in the pack came out the wrong size ({info.filename[:80]!r}).')
            os.replace(part, dest)
            t = time.mktime(info.date_time + (0, 0, -1))
            os.utime(dest, (t, t))
    lib = plain / DATA_NAME
    if verify:
        verify(lib)
    elif allowed:
        check_map(lib)
    elif not is_library(lib):
        raise Refused('unpack', 'The unpacked pack has no library catalog in it.')
    return lib


# ------------------------------------------------------------------------------------------------------------ space --
def need_bytes(pack, model, have_files=()):
    """Room needed on the target disk: what is still to download, plus the unpacked size, plus SPACE_MARGIN."""
    n = SPACE_MARGIN
    if pack:
        n += sum(f['size'] for f in pack['files'] if f['name'] not in have_files) + (pack.get('installed_bytes') or 0)
    if model:
        n += model['size'] if model['file'] not in have_files else 0
    return n


# ------------------------------------------------------------------------------------------------- comparing packs --
def read_pack_manifest(path):
    """[(path, bytes, sha256)] from a pack-manifest.tsv, read the way repair reads it: the first line is the header, blank
    lines are skipped, and the columns after sha256 (how, changes) are not needed. A missing header, a list with no files,
    a row that is too short, a size that is not a whole number of bytes, a SHA-256 that is not 64 hex digits, an empty path
    or a path listed twice raises ValueError, because a list we cannot trust is no basis for keeping files."""
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    if not lines or lines[0].split('\t')[:3] != ['path', 'bytes', 'sha256']:
        raise ValueError(f'{path} does not start with the header path, bytes, sha256')
    rows, seen = [], set()
    for n, line in enumerate(lines[1:], 2):
        if not line.strip():
            continue
        r = line.split('\t')
        try:
            rel, size, digest = r[0], int(r[1]), r[2]
        except (ValueError, IndexError):
            raise ValueError(f'line {n} of {path} is not path, bytes, sha256') from None
        if not rel or size < 0 or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError(f'line {n} of {path} is not path, bytes, sha256')
        if rel in seen:
            raise ValueError(f'line {n} of {path} lists {rel} a second time')
        seen.add(rel)
        rows.append((rel, size, digest))
    if not rows:
        raise ValueError(f'{path} lists no files')
    return rows


def compare_pack_manifests(installed, new):
    """What an upgrade from one pack to another would need, from their manifests alone. Read-only: it looks at no file on
    disk and downloads nothing. Nothing in setup calls it yet (issue #144).

    installed and new are lists of (path, bytes, sha256), as read_pack_manifest returns them. A path in both is unchanged
    when its size and SHA-256 are both the same, otherwise changed. A path that would leave the library ('..', a drive, a
    root or a backslash, on every system, as in _member_parts) is never kept: it goes in unsafe, apart from the rest, and
    counts toward no total.
    Lists are sorted by path. fetch_bytes (added plus changed, at their new size) is what would have to come in;
    reuse_bytes (unchanged) is what is already here."""
    def safe(rel):
        parts = PurePosixPath(rel).parts
        return bool(parts) and '..' not in parts and ':' not in parts[0] and not rel.startswith('/') and not set('\\\x00') & set(rel)
    old = {rel: (size, digest) for rel, size, digest in installed}
    out = {'added': [], 'removed': [], 'changed': [], 'unchanged': [], 'unsafe': []}
    size_of = {}
    for rel, size, digest in new:
        size_of[rel] = size
        if not safe(rel):
            out['unsafe'].append(rel)
        elif rel not in old:
            out['added'].append(rel)
        elif old[rel] == (size, digest):
            out['unchanged'].append(rel)
        else:
            out['changed'].append(rel)
    out['removed'] = [rel for rel in old if rel not in size_of and safe(rel)]
    out['unsafe'] += [rel for rel in old if rel not in size_of and not safe(rel)]
    for k in out:
        out[k].sort()
    total = {k: sum(size_of[rel] for rel in out[k]) for k in ('added', 'changed', 'unchanged')}
    total['removed'] = sum(old[rel][0] for rel in out['removed'])
    out['bytes'] = total
    out['fetch_bytes'] = total['added'] + total['changed']
    out['reuse_bytes'] = total['unchanged']
    return out


KEPT_KINDS = ('map', 'model', 'addresses', 'other')


def plan_update(lib, new):
    """What updating the installed library at lib to a release would do, without doing any of it (issue #144). new is the
    release's rows, as read_pack_manifest returns them; the installed list is lib's own pack-manifest.tsv. Read-only: it
    reads the two lists and the names and sizes of the library's files, and opens, downloads, writes and deletes nothing.
    Nothing in setup calls it yet.

    The pack's own files are compared as compare_pack_manifests does, and its keys are all here. What is not the pack's is
    never counted as removed or changed, and is listed apart in kept, as it would stay:
      - map: a map installed on its own (map-set.json), whose files replace the pack's map files. While it is there, map
        files on either list are left out of the comparison, as repair checks them against map-set.json instead.
      - model: the local AI, in models/.
      - addresses: address indexes, in derived/geo/addresses/.
      - other: any other file neither list names, such as the app's own state and logs, or files the person added.
    kept maps each kind to [(path, bytes)], sorted; kept_bytes to their total. map is the installed map's name, or None."""
    lib = Path(lib)
    installed = read_pack_manifest(lib / 'pack-manifest.tsv')
    own_map = has_separate_map(lib, pack_lists_map=any(rel == 'map-set.json' for rel, _, _ in installed))
    map_paths = set(map_files(lib)) if own_map else set()

    def pack_side(rows):
        return [r for r in rows if not (own_map and map_member(r[0]))]
    out = compare_pack_manifests(pack_side(installed), pack_side(new))
    listed = {r[0] for r in installed} | {r[0] for r in new} | {'pack-manifest.tsv'}   # the list itself comes with the release
    kept = {k: [] for k in KEPT_KINDS}
    for root, dirs, files in os.walk(lib):       # links to folders are not followed
        dirs.sort()
        for name in files:
            p = Path(root) / name
            rel = p.relative_to(lib).as_posix()
            if own_map and rel in map_paths:
                kind = 'map'
            elif rel in listed:
                continue                          # the pack's own: in the comparison above
            elif rel.startswith('models/'):
                kind = 'model'
            elif rel.startswith('derived/geo/addresses/'):
                kind = 'addresses'
            else:
                kind = 'other'
            try:
                kept[kind].append((rel, p.lstat().st_size))
            except OSError:
                continue
    for k in kept:
        kept[k].sort()
    out['kept'] = kept
    out['kept_bytes'] = {k: sum(n for _, n in v) for k, v in kept.items()}
    out['map'] = map_name(lib) if own_map else None
    return out


# -------------------------------------------------------------------------------------------------------- switching --
def _write_json(path, d):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(d, indent=1), encoding='utf-8')
    os.replace(tmp, path)


def old_name(target):
    base = target.with_name(f'{target.name}.old-{time.strftime("%Y%m%d")}')
    p, i = base, 2
    while p.exists():
        p = base.with_name(f'{base.name}-{i}')
        i += 1
    return p


def stage_switch(pend, new_lib, target, model_file=None, kind=None, model_sha256=None):
    """Writes what the switch will do to `pend`, a file in the app's own settings folder (never the work folder), for
    apply_pending. Nothing is renamed yet."""
    d = {'new': str(new_lib), 'target': str(target), 'model_file': model_file, 'written': time.time()}
    if kind:
        d['kind'] = kind
    if model_sha256:
        d['model_sha256'] = model_sha256     # the digest setup matched, for llm_local.mark_checked after the switch
    Path(pend).parent.mkdir(parents=True, exist_ok=True)
    _write_json(pend, d)
    return d


def carry_over(old, new, moved=None):
    """What belongs to the person, not the pack, goes with them: the model file, address indexes, and the AI's on/off setting.
    Each move is added to `moved` as it happens, so a caller still knows what moved when a later move raises."""
    old, new = Path(old), Path(new)
    moved = [] if moved is None else moved
    src = old / 'models'
    if src.is_dir():
        (new / 'models').mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            dest = new / 'models' / f.name
            if f.is_file() and not dest.exists():
                os.replace(f, dest)
                moved.append(dest)
    addresses = old / 'derived' / 'geo' / 'addresses'
    if addresses.is_dir():
        dest_dir = new / 'derived' / 'geo' / 'addresses'
        dest_dir.mkdir(parents=True, exist_ok=True)
        for source in addresses.iterdir():
            dest = dest_dir / source.name
            if source.is_file() and re.fullmatch(r'[A-Z]{2}\.(sqlite|json)', source.name) and not dest.exists():
                os.replace(source, dest)
                moved.append(dest)
    state = old / 'derived' / 'llm' / 'state.json'
    if state.is_file() and not (new / 'derived' / 'llm' / 'state.json').exists():
        (new / 'derived' / 'llm').mkdir(parents=True, exist_ok=True)
        shutil.copy2(state, new / 'derived' / 'llm' / 'state.json')
    return moved


def switch(new_lib, target):
    """The renames. Returns the old library's new name, or None when there was none. Raises Refused, leaving things as they were."""
    new_lib, target = Path(new_lib), Path(target)
    if not is_library(new_lib):
        raise Refused('activate', 'The new library is not complete.')
    old = None
    carried = []
    if target.exists():
        old = old_name(target)
        if is_library(target):
            try:
                carry_over(target, new_lib, carried)
            except OSError as e:
                _refuse_carried_back(carried, new_lib, target, f'Lastbook could not move your files into the new library ({type(e).__name__}). Close anything using them, then try again.')
        try:
            os.replace(target, old)
        except OSError as e:
            _refuse_carried_back(carried, new_lib, target, f'Lastbook could not move the old library aside ({type(e).__name__}). Close anything using it, then try again.')
    try:
        os.replace(new_lib, target)
    except OSError as e:
        if old:
            try:
                os.replace(old, target)
            except OSError:
                still = [str(moved) for moved in carried if moved.is_file()]
                raise Refused('activate', f'Lastbook could not put the new library in place ({type(e).__name__}), nor the old one back. '
                                          f'The old library is in {old}.'
                                          + (' These files of yours are still in the new library: ' + ', '.join(still) if still else ''))
        _refuse_carried_back(carried, new_lib, target, f'Lastbook could not put the new library in place ({type(e).__name__}).')
    return old


def _refuse_carried_back(carried, new_lib, target, message):
    """Undo carry_over after a failed step, so the library that stays in place keeps its model and address indexes.
    A file that cannot go back stays where it is, and the message says where."""
    stuck = []
    for moved in carried:
        back = target / moved.relative_to(new_lib)
        try:
            if moved.is_file() and not back.exists():
                os.replace(moved, back)
        except OSError:
            stuck.append(str(moved))
    if stuck:
        message += ' These files could not be moved back and are still here: ' + ', '.join(stuck)
    raise Refused('activate', message)


# ----------------------------------------------------------------------------------------------------------- state maps --
def map_set(lib):
    """The map set's map-set.json ({name, files: {path: bytes}}), or None."""
    try:
        d = json.loads((Path(lib) / 'map-set.json').read_text(encoding='utf-8'))
        return d if isinstance(d, dict) and isinstance(d.get('files'), dict) else None
    except (OSError, ValueError):
        return None


def map_name(lib):
    """'base', 'us' or a state code: from map-set.json, else the pack's own pack.json, else 'base'."""
    d = map_set(lib)
    if d and d.get('name'):
        return str(d['name'])
    try:
        return str(json.loads((Path(lib) / 'pack.json').read_text(encoding='utf-8')).get('map') or 'base')
    except (OSError, ValueError, AttributeError):
        return 'base'


def has_separate_map(lib, *, pack_lists_map=None):
    """Does the library hold a map set installed apart from its pack (a state map), rather than the pack's own (All's whole US)?
    The pack's own set is named by pack.json's `map`, and its map-set.json is listed in pack-manifest.tsv with its other files,
    so they are checked and fetched with the pack. Ownership never depends on map-set.json's contents being whole: a damaged one
    of the pack's own then shows up as a damaged pack file.

    Callers that have read the pack manifest can supply whether it lists map-set.json."""
    lib = Path(lib)
    d = map_set(lib)
    if not d:
        return False
    try:
        own = json.loads((lib / 'pack.json').read_text(encoding='utf-8')).get('map')
        if pack_lists_map is None:
            pack_lists_map = any(line.split('\t', 1)[0] == 'map-set.json'
                                 for line in (lib / 'pack-manifest.tsv').read_text(encoding='utf-8').splitlines()[1:])
    except (OSError, ValueError, AttributeError):
        return True
    return not (pack_lists_map and d.get('name') == own)


def check_map(lib):
    """Every file map-set.json lists is there at its size, and each is a map file."""
    d = map_set(lib)
    if not d:
        raise Refused('unpack', 'The map has no map-set.json in it.')
    for rel, size in d['files'].items():
        if not map_member(rel) or '..' in Path(rel).parts:
            raise Refused('unpack', f'The map lists a file that is not part of a map ({rel[:80]!r}).')
        p = Path(lib) / rel
        if not p.is_file() or p.stat().st_size != size:
            raise Refused('unpack', f'The map’s {rel} is missing or the wrong size.')
    return d


def map_files(lib):
    """The files of a library's map set as they are on disk, relative to it, with SQLite's side files and map-set.json."""
    lib = Path(lib)
    d = map_set(lib)
    rels = {r for r in d['files'] if map_member(r) and '..' not in Path(r).parts} if d else set()    # the fixed list only
    geo = lib / 'derived' / 'geo'
    if geo.is_dir():
        rels |= {f'derived/geo/{p.name}' for p in geo.iterdir() if p.is_file() and map_member(f'derived/geo/{p.name}')}
    rels |= {r for r in MAP_FIXED if (lib / r).is_file()}
    out = set()
    for r in rels:
        for side in ('',) + (SQLITE_SIDES if r.endswith('.sqlite') else ()):
            if (lib / (r + side)).is_file():
                out.add(r + side)
    return sorted(out)


def map_bytes(lib):
    """Space needed to keep the current detailed map during a content refresh."""
    total = 0
    for rel in map_files(lib):
        try:
            total += (Path(lib) / rel).stat().st_size
        except OSError:
            continue
    return total


def copy_map(old, new):
    """Keep an installed map while refreshing the same library's content."""
    old, new = Path(old), Path(new)
    for rel in map_files(new):
        os.unlink(new / rel)
    for rel in map_files(old):
        destination = new / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old / rel, destination)


def swap_map(lib, new, old_dir):
    """Puts the map set in `new` (a LastbookData holding only map files) into `lib`; the old set's files go to old_dir first.
    Renames only, on one disk. On any failure what was moved is put back and Refused is raised."""
    lib, new, old_dir = Path(lib), Path(new), Path(old_dir)
    check_map(new)
    moved_out, moved_in = [], []
    try:
        for rel in map_files(lib):
            dest = old_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(lib / rel, dest)
            moved_out.append(rel)
        for rel in map_files(new):
            dest = lib / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(new / rel, dest)
            moved_in.append(rel)
    except OSError as e:
        for rel in moved_in:
            os.replace(lib / rel, new / rel)
        for rel in moved_out:
            os.replace(old_dir / rel, lib / rel)
        raise Refused('activate', f'Lastbook could not put the new map in place ({type(e).__name__}).')


def replace_map_in(staged, new):
    """A pack being installed with a state map: the map's files replace the pack's own map set inside the staged library."""
    staged, new = Path(staged), Path(new)
    check_map(new)
    for rel in map_files(staged):
        os.unlink(staged / rel)
    for rel in map_files(new):
        (staged / rel).parent.mkdir(parents=True, exist_ok=True)
        os.replace(new / rel, staged / rel)


def _apply_map(work, pend, d, target, note):
    """A state map staged for the open library: swap its files in; if the library then does not check out, swap the old ones back."""
    old_dir = Path(work) / 'map-old'
    note['map_old'] = str(old_dir)
    if not d.get('switched'):
        try:
            swap_map(target, d['new'], old_dir)
        except Refused as e:
            print('setup: map switch failed:', e.message, flush=True)
            pend.unlink()
            note['error'] = e.message
            return (target if is_library(target) else None), note
        d['switched'] = True
        _write_json(pend, d)
    try:
        check_map(target)
        ok = is_library(target)
    except Refused:
        ok = False
    if not ok and old_dir.is_dir():
        broken = Path(work) / 'map-failed'
        shutil.rmtree(broken, ignore_errors=True)
        for rel in map_files(target):
            (broken / rel).parent.mkdir(parents=True, exist_ok=True)
            os.replace(target / rel, broken / rel)
        for root, _, files in os.walk(old_dir):
            for f in files:
                rel = Path(root, f).relative_to(old_dir)
                (target / rel).parent.mkdir(parents=True, exist_ok=True)
                os.replace(Path(root, f), target / rel)
        note['error'] = 'The new map did not open, so Lastbook put the old one back.'
    return target if is_library(target) else None, note


def _real(p):
    return os.path.normcase(os.path.realpath(str(p)))


def _pending_ok(d, work):
    """Only what setup itself stages: the work folder's own library, its own staged copy, and a LastbookData.old-* beside it.
    Compared as real paths. Anything else is not a pending switch."""
    if not isinstance(d, dict) or not isinstance(d.get('target'), str) or not isinstance(d.get('new'), str):
        return False
    if not Path(work).name.endswith('.setup') or len(Path(work).name) <= len('.setup'):
        return False
    target = Path(work).with_name(Path(work).name[:-len('.setup')])     # the library the work folder belongs to, whatever its name
    new = Path(work) / ('unpack-map' if d.get('kind') == 'map' else 'unpack') / DATA_NAME
    if d.get('kind') not in (None, 'map') or _real(d['target']) != _real(target) or _real(d['new']) != _real(new):
        return False
    old = d.get('old')
    if old is not None and not (isinstance(old, str) and _real(Path(old).parent) == _real(target.parent)
                                and Path(old).name.startswith(target.name + '.old-')):
        return False
    sha = d.get('model_sha256')
    if sha is not None and not (isinstance(sha, str) and re.fullmatch(r'[0-9a-f]{64}', sha)):
        return False
    mf = d.get('model_file')
    if mf is not None and not (isinstance(mf, str) and _real(Path(mf).parent) == _real(target / 'models')):
        return False
    return True


def apply_pending(pend, work):
    """Runs at startup, before the engine opens anything. Returns (library folder or None, a note dict or None).
    pend: the pending switch in the app's own settings folder. If one was staged, do it; if the new library then does not
    open, put the old one back. A file that is not exactly what setup stages for this work folder is removed, not obeyed."""
    pend, work = Path(pend), Path(work)
    try:
        d = json.loads(pend.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None, None
    if not _pending_ok(d, work):
        print('setup: a pending switch that does not match its work folder was ignored', flush=True)
        try:
            pend.unlink()
        except OSError:
            pass
        return None, None
    target = Path(d['target'])
    note = {'target': str(target), 'old': None, 'model_file': d.get('model_file'), 'model_sha256': d.get('model_sha256')}
    if d.get('kind') == 'map':
        return _apply_map(work, pend, d, target, note)
    if d.get('switched'):
        lib_ok = is_library(target)
    else:
        try:
            old = switch(d['new'], target)
        except Refused as e:
            print('setup: switch failed:', e.message, flush=True)
            pend.unlink()
            note['error'] = e.message
            return (target if is_library(target) else None), note
        d['switched'], d['old'] = True, old and str(old)
        _write_json(pend, d)
        lib_ok = is_library(target)
    note['old'] = d.get('old')
    if not lib_ok and d.get('old') and Path(d['old']).exists():
        broken = target.with_name(target.name + '.failed')
        os.replace(target, broken)
        os.replace(d['old'], target)
        carry_over(broken, target)      # the model file, moved into the new one, goes back too
        note['error'] = 'The new library did not open, so Lastbook put the old one back.'
        note['old'] = None
    return target if is_library(target) else None, note


def confirm(pend):
    """The new library opened: the switch is done. The old one stays until the person deletes it from setup."""
    try:
        Path(pend).unlink()
    except OSError:
        pass
