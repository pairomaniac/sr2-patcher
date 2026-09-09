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
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('patcher', os.path.join(HERE, '..', 'sr2-patcher.py'))
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

LIST_LIMIT = 40
CPU_GROUPS = ('Program Executable Files', 'PentiumIII Modules', 'AMD Modules')


def _inflate(data):
    """(bytes out, error) for one raw deflate stream."""
    d = zlib.decompressobj(-15)
    try:
        return d.decompress(data), None
    except zlib.error as exc:
        return b'', exc


def _diagnose(fh, e, exc):
    """What is at a file that did not inflate: its descriptor, the first
    bytes, and whether the data is chunked (u16 length + deflate stream)."""
    print('  cannot read %s\\%s: %s' % (e.group, e.path, exc))
    print('    flags 0x%x size %d compressed %d offset 0x%x' % (e.flags, e.size, e.compressed, e.offset))
    fh.seek(e.offset)
    head = fh.read(min(e.compressed, 64))
    print('    first bytes %s' % head[:16].hex())
    chunk = struct.unpack_from('<H', head)[0]
    fh.seek(e.offset + 2)
    out, err = _inflate(fh.read(min(chunk, e.compressed - 2)))
    print('    as a chunk: u16 length %d, inflates to %d bytes%s'
          % (chunk, len(out), '' if err is None else ' (%s)' % err))


def survey(src):
    """{(group, path): (size, md5)} for every valid file in the cab."""
    fh, close = patcher.open_source(src)
    try:
        sig, ver = struct.unpack('<2I', fh.read(8))
        fh.seek(0)
        cab = patcher.Cabinet(fh)
        print('  %d files, %d groups, cabinet version 0x%08x' % (len(cab.entries), len(cab.groups), ver))
        for name, entries in cab.groups.items():
            print('    %-28s %5d files %8.1f MB' % (name, len(entries), sum(e.size for e in entries) / 1e6))
        files, failed = {}, 0
        for e in cab.entries:
            if not e.group:
                continue
            try:
                files[e.group, e.path] = (e.size, hashlib.md5(cab.read(e)).hexdigest())
            except (zlib.error, ValueError) as exc:
                if not failed:
                    _diagnose(fh, e, exc)
                failed += 1
                files[e.group, e.path] = (e.size, 'unreadable')
        if failed:
            print('  %d files unreadable' % failed)
    finally:
        close()
    return files


def fingerprints(files):
    """The patcher's known files against this cab, and the three CPU
    builds' copies of the six overlay files."""
    known = dict(patcher.PATCHED_FILES)
    for path, size, digest in patcher.P3_FILES:
        known.pop(path, None)
        print('    %-9s %s' % (_state(files.get(('PentiumIII Modules', path)), size, digest), path))
    for path, (size, digest) in sorted(known.items()):
        print('    %-9s %s' % (_state(files.get(('Program Executable Files', path)), size, digest), path))
    print('  overlay files by build:')
    for path, _s, _d in patcher.P3_FILES:
        for group in CPU_GROUPS:
            got = files.get((group, path))
            if got:
                print('    %-24s %8d %s %s' % (group, got[0], got[1], path))


def _state(got, size, digest):
    if got is None:
        return 'missing'
    if got == (size, digest):
        return 'known'
    return 'UNKNOWN %d %s' % got


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
    groups = {}
    for group, path in sorted(set().union(*surveys)):
        got = [s.get((group, path)) for s in surveys]
        same = got[0] is not None and all(g == got[0] for g in got)
        groups.setdefault(group, [0, []])
        if same:
            groups[group][0] += 1
        else:
            tags = ['-' if g is None else '%d %s' % (g[0], g[1][:8]) for g in got]
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
