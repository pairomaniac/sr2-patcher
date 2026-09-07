#!/usr/bin/env python3
"""Exercise the disc and cabinet readers against a real install disc.

    python3 tools/cabtest.py SOURCE            list groups, extract what fits
    python3 tools/cabtest.py SOURCE GAMEDIR    and compare with an installed game

SOURCE is what the patcher accepts: a .cue, an .iso or .bin, a mounted
disc folder, or data1.cab itself.

A truncated copy works too (head -c 16M data1.cab > data1.head): the file
table is at the front, and only files whose bytes fall inside the copy are
extracted. With GAMEDIR, every extracted file that also exists there is
compared; the base-build files differ from a Pentium III install by
design and are counted, not reported.
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
    print('%d files, %d groups' % (len(cab.entries), len(cab.groups)))
    for name, entries in cab.groups.items():
        print('  %-28s %5d files %8.1f MB' % (name, len(entries), sum(e.size for e in entries) / 1e6))
    for name in patcher.install_groups('English'):
        if name not in cab.groups:
            print('missing group: %s' % name)
            return 1
    p3 = {n: (s, d) for n, s, d in patcher.P3_FILES}
    read = same = differ = 0
    for e in cab.entries:
        if not e.group or e.offset + e.compressed > size:
            continue
        data = cab.read(e)
        read += 1
        if e.group == 'PentiumIII Modules' and e.path in p3:
            if (len(data), hashlib.md5(data).hexdigest()) != p3[e.path]:
                print('P3 fingerprint mismatch: %s' % e.path)
                return 1
        if game:
            local = os.path.join(game, *e.path.split('\\'))
            if os.path.isfile(local):
                with open(local, 'rb') as fh:
                    if fh.read() == data:
                        same += 1
                    else:
                        differ += 1
                        if e.group != 'Program Executable Files':
                            print('differs: %s\\%s' % (e.group, e.path))
    close()
    print('extracted %d files' % read)
    if game:
        print('compared with %s: %d identical, %d differ' % (game, same, differ))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
