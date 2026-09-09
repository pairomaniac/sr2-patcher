#!/usr/bin/env python3
"""Exercise the disc and cabinet readers against a real install disc.

    python3 tools/cabtest.py SOURCE

SOURCE is what the patcher accepts: a .cue, an .iso or .bin, a mounted
disc folder, or data1.cab itself. Every file that fits is extracted, and
the Pentium III files are checked against the build's row.

A truncated copy works too (head -c 16M data1.cab > data1.head): the file
table is at the front, and only files whose bytes fall inside the copy are
extracted.
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
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    fh, close = patcher.open_source(argv[1])
    cab = patcher.Cabinet(fh)
    size = fh.seek(0, 2)
    for name in patcher.install_groups('English'):
        if name not in cab.groups:
            print('missing group: %s' % name)
            return 1
    p3, read = {}, 0
    for e in cab.entries:
        if not e.group or e.offset + e.compressed > size:
            continue
        data = cab.read(e)
        read += 1
        if e.group == 'PentiumIII Modules':
            p3[e.path] = (len(data), hashlib.md5(data).hexdigest())
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
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
