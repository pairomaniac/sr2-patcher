#!/usr/bin/env python3
"""Exercise the disc and cabinet readers against a real install disc.

    python3 tools/cabtest.py SOURCE            list groups, extract what fits
    python3 tools/cabtest.py SOURCE GAMEDIR    and compare with an installed game

SOURCE is what the patcher accepts: a .cue, an .iso or .bin, a mounted
disc folder, or data1.cab itself.

A truncated copy works too (head -c 16M data1.cab > data1.head): the file
table is at the front, and only files whose bytes fall inside the copy are
extracted. With GAMEDIR, the files an install of its language writes are
compared with what is there, patched files by their .bak; every one
should be identical.
"""
import hashlib
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('patcher', os.path.join(HERE, '..', 'sr2-patcher.py'))
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


def main(argv):
    if not 2 <= len(argv) <= 3:
        print(__doc__.strip())
        return 2
    fh, close = patcher.open_source(argv[1])
    cab = patcher.Cabinet(fh)
    size = fh.seek(0, 2)
    game = argv[2] if len(argv) == 3 else None
    for name in patcher.install_groups('English'):
        if name not in cab.groups:
            print('missing group: %s' % name)
            return 1
    p3 = {}
    read = 0
    written = {}
    for e in cab.entries:
        if not e.group or e.offset + e.compressed > size:
            continue
        data = cab.read(e)
        read += 1
        if e.group == 'PentiumIII Modules':
            p3[e.path] = (len(data), hashlib.md5(data).hexdigest())
        if game:
            written.setdefault(e.group, {})[e.path] = hashlib.md5(data).hexdigest()
    close()
    build = patcher.build_of(p3.get(patcher.EXE, (0, ''))[1])
    if build is None:
        print('the P3 exe is not a build the patcher knows')
        return 1
    files = patcher.BUILDS[build]['files']
    for path, got in p3.items():
        if got != files[path]:
            print('%s is not the %s build\'s' % (path, build))
            return 1
    print('%d files in %d groups, %d read, %s build' % (len(cab.entries), len(cab.groups), read, build))
    if not game:
        return 0
    # The installed language: the one whose SR2_MSG.dll is in the folder.
    # A truncated cab may hold no language group at all; then English.
    msg = os.path.join(game, 'SR2_MSG.dll')
    have = [l for l in patcher.LANGUAGES if 'SR2_MSG.dll' in written.get(l, {})]
    lang = next((l for l in have if os.path.isfile(msg) and
                 written[l]['SR2_MSG.dll'] == patcher.md5(msg)), None if have else 'English')
    if lang is None:
        print('%s holds no language the cabinet has' % game)
        return 1
    expect = {}
    for group in patcher.install_groups(lang):
        expect.update(written.get(group, {}))
    same = differ = missing = 0
    for path, digest in sorted(expect.items()):
        local = os.path.join(game, *path.split('\\'))
        if os.path.isfile(local + '.bak'):
            local += '.bak'
        if not os.path.isfile(local):
            missing += 1
        elif patcher.md5(local) == digest:
            same += 1
        else:
            differ += 1
            print('differs: %s' % path)
    print('%s install in %s: %d identical, %d differ, %d missing' % (lang, game, same, differ, missing))
    return 0 if not differ else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
