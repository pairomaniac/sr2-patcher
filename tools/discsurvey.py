#!/usr/bin/env python3
"""Compare install discs: what is in each data1.cab, and what differs.

    python3 tools/discsurvey.py SOURCE [SOURCE ...]

SOURCE is what the patcher accepts: a .cue, an .iso or .bin, a mounted
disc folder, or data1.cab itself. Every file in every cabinet is read and
hashed, so a disc takes a minute or two.

For each disc: the root files (folders only), the groups, and whether the
files the patcher fingerprints are the ones it knows. With more than one
disc: per group, how many files are identical across all of them, and the
paths that differ or are missing on some.
"""
import hashlib
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('patcher', os.path.join(HERE, '..', 'sr2-patcher.py'))
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

LIST_LIMIT = 40


def survey(src):
    """{path: (group, size, md5)} for every valid file in the cab."""
    fh, close = patcher.open_source(src)
    try:
        cab = patcher.Cabinet(fh)
        print('  %d files, %d groups' % (len(cab.entries), len(cab.groups)))
        for name, entries in cab.groups.items():
            print('    %-28s %5d files %8.1f MB' % (name, len(entries), sum(e.size for e in entries) / 1e6))
        files = {}
        for e in cab.entries:
            if e.group:
                files[e.path] = (e.group, e.size, hashlib.md5(cab.read(e)).hexdigest())
    finally:
        close()
    return files


def fingerprints(files):
    """The patcher's known files against this cab's P3 and base copies."""
    known = {n: (s, d) for n, s, d in patcher.P3_FILES}
    known.update(patcher.PATCHED_FILES)
    for path, (size, digest) in sorted(known.items()):
        got = files.get(path)
        if got is None:
            state = 'missing'
        elif (got[1], got[2]) == (size, digest):
            state = 'known'
        else:
            state = 'UNKNOWN %d %s' % (got[1], got[2])
        print('    %-9s %s' % (state, path))


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    surveys = []
    for src in argv[1:]:
        print('== %s' % src)
        if os.path.isdir(src):
            for name in sorted(os.listdir(src)):
                p = os.path.join(src, name)
                print('  %10s %s' % (os.path.getsize(p) if os.path.isfile(p) else '<dir>', name))
        files = survey(src)
        print('  fingerprints:')
        fingerprints(files)
        surveys.append(files)
    if len(surveys) < 2:
        return 0

    print('== across %d discs' % len(surveys))
    paths = sorted(set().union(*surveys))
    groups = {}
    for path in paths:
        got = [s.get(path) for s in surveys]
        group = next(g[0] for g in got if g)
        same = all(g and g[1:] == got[0][1:] for g in got) if got[0] else False
        groups.setdefault(group, [0, []])
        if same:
            groups[group][0] += 1
        else:
            tags = ['-' if g is None else '%d %s' % (g[1], g[2][:8]) for g in got]
            groups[group][1].append('%s: %s' % (path, ' | '.join(tags)))
    for group, (same, diffs) in sorted(groups.items()):
        print('  %-28s %5d identical, %5d differ or missing' % (group, same, len(diffs)))
        for line in diffs[:LIST_LIMIT]:
            print('    %s' % line)
        if len(diffs) > LIST_LIMIT:
            print('    ... and %d more' % (len(diffs) - LIST_LIMIT))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
