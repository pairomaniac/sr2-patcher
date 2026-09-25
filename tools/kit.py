#!/usr/bin/env python3
"""Bundle the game files the checks and the notes are written against.

    python3 tools/kit.py            # writes tools/sr2-kit.tar.gz from ~/.sr2-test

For every build named in ~/.sr2-test: the installed game without BINDATA\\
and music\\ (the executables, DLLs, manifests, help and config) - but
with BINDATA\\connect\\button, which the buttons check needs - with each
patched file replaced by its .bak so the kit holds the originals, and the
first 16 MB of the install disc's data1.cab as data1.head. Not the
repository's to distribute; the tarball is gitignored.
"""
import io
import os
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check import BUILDS, CONF, config  # noqa: E402  (after the sys.path line above)
from uctest import patcher  # noqa: E402

OUT = os.path.join(HERE, 'sr2-kit.tar.gz')
SKIP = ('bindata', 'music')
KEEP = ('bindata/connect/button',)       # small, and a check composes from it
HEAD = 16 << 20


def add_game(tar, build, game):
    n = 0
    for root, dirs, files in os.walk(game):
        rel = os.path.relpath(root, game).replace(os.sep, '/').lower()
        dirs[:] = [d for d in dirs if d.lower() not in SKIP
                   or any(k.startswith((rel + '/' if rel != '.' else '') + d.lower()) for k in KEEP)]
        if rel.startswith('bindata') and not any(rel.startswith(k) for k in KEEP):
            files = []                      # a folder walked only on the way to a kept one
        for name in files:
            if name.endswith('.bak'):
                continue
            path = os.path.join(root, name)
            if os.path.isfile(path + '.bak'):
                path += '.bak'
            tar.add(path, arcname='/'.join((build, 'game', os.path.relpath(os.path.join(root, name), game))))
            n += 1
    return n


def add_head(tar, build, disc):
    fh, close = patcher.open_source(disc)
    try:
        data = fh.read(HEAD)
    finally:
        close()
    info = tarfile.TarInfo(build + '/data1.head')
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def main(argv):
    if len(argv) > 1:
        print(__doc__.strip())
        return 2
    conf = config()
    with tarfile.open(OUT, 'w:gz') as tar:
        for build in BUILDS:
            game, disc = conf.get('SR2_GAME_' + build), conf.get('SR2_DISC_' + build)
            if not game and not disc:
                continue
            if game:
                print('%s: %d files from %s' % (build, add_game(tar, build, game), game))
            if disc:
                add_head(tar, build, disc)
                print('%s: data1.head from %s' % (build, os.path.basename(disc)))
    if os.path.getsize(OUT) < 1000:
        os.remove(OUT)
        print('nothing to bundle: no SR2_GAME_* or SR2_DISC_* in %s' % CONF)
        return 1
    print('wrote %s, %d MB' % (OUT, os.path.getsize(OUT) >> 20))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
