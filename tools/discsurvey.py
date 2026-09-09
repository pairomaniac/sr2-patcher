#!/usr/bin/env python3
"""Compare install discs: what is in each data1.cab, and what differs.

    python3 tools/discsurvey.py SOURCE [SOURCE ...]
    python3 tools/discsurvey.py --play PLAY.cue [PLAY.cue ...]

SOURCE is what the patcher accepts: a .cue, an .iso or .bin, a mounted
disc folder, or data1.cab itself. Every file in every cabinet is read and
hashed, so a disc takes a minute or two.

For each disc: the root files (folders only), the groups, and whether the
files the patcher fingerprints are the ones it knows. With more than one
disc: per group, how many files are identical across all of them, and the
paths that differ or are missing on some.

--play takes play-disc cue sheets and prints, per disc, the volume label,
the root of the data track and the audio tracks with their lengths and
MD5s - what the ripper depends on.
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


P3 = ('SEGA RALLY 2.exe', 'AdvTelop.dll', 'Champagn.dll', 'MSelect.dll',
      'MUSASHI\\MGameGL.dll', 'MUSASHI\\MGLBackground.dll')


def fingerprints(files):
    """The build the P3 exe names, its row against this cab, and the
    three CPU builds' copies of the six overlay files."""
    exe = files.get(('PentiumIII Modules', patcher.EXE))
    build = patcher.build_of(exe[1]) if exe else None
    print('  build: %s' % (build or 'unknown'))
    if build:
        for path, (size, digest) in patcher.BUILDS[build]['files'].items():
            group = 'PentiumIII Modules' if path in P3 else 'Program Executable Files'
            got = files.get((group, path))
            state = 'missing' if got is None else 'known' if got == (size, digest) else 'UNKNOWN %d %s' % got
            print('    %-9s %s' % (state, path))
    print('  overlay files by build:')
    for path in P3:
        for group in CPU_GROUPS:
            got = files.get((group, path))
            if got:
                print('    %-24s %8d %s %s' % (group, got[0], got[1], path))


def play(cue):
    """Label, root listing and audio tracks of one play disc."""
    path, start = patcher.data_track(cue)
    track = patcher.DataTrack(path, start)
    try:
        pvd = track.sector(patcher.PRIMARY_VD)
        print('  label %r, data track %s' % (pvd[40:72].decode('latin-1').rstrip(), track.form))
        for name, (is_dir, _lba, size) in sorted(patcher.iso_root(track).items()):
            print('  %10s %s' % ('<dir>' if is_dir else size, name))
    finally:
        track.close()
    spans = list(patcher.audio_spans(patcher.parse_cue(cue)))
    print('  %d audio tracks' % len(spans))
    for t, first, last in spans:
        with open(t['bin'], 'rb') as fh:
            fh.seek(first * patcher.RAW)
            digest = hashlib.md5(fh.read((last - first) * patcher.RAW)).hexdigest()
        n = last - first
        print('    track %02d  %2d:%02d.%02d  %7d sectors  %s' % (t['no'], n // 75 // 60, n // 75 % 60, n % 75, n, digest))


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    if argv[1] == '--play':
        for cue in argv[2:]:
            print('== %s' % cue)
            play(cue)
        return 0
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
