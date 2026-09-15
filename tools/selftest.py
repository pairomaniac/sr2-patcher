#!/usr/bin/env python3
"""Apply the patch tables to a real install and report.

    python3 tools/selftest.py GAMEDIR        # an installed game, patched or not

CI cannot do this - the game is not in the repository - so it runs from
~/.sr2-test through tools/check.py. It checks what nothing else can:

  * every original byte string in the tables is really in the file
  * every combination of patches applies, not just the all-on case
  * the fully patched result has the MD5 it had last time

A patched install that does not hold that result is noted, not failed:
it is older than the tables, and a re-patch brings it up.

The tables are the patcher. A wrong offset passes every other check in
this repository and corrupts somebody's game.
"""
import hashlib
import importlib.util
import itertools
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('patcher', os.path.join(HERE, '..', 'sr2-patcher.py'))
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

# MD5 of each patched file with every patch on, per build. Update
# deliberately, and only when a patch actually changed.
EXPECTED = {
    'European': {
        'SEGA RALLY 2.exe': '2ba8418b60d523a86b079e9c491e9a5d',
        'MUSASHI\\MGameGL.dll': 'fcca6e46daa16a23184e1c1daa21274a',
        'MUSASHI\\MGameD3D.dll': 'a5732b9c9de6a60b6a4e8a0d73941233',
        'MUSASHI\\MGAudio.dll': 'd62b598085dd18757cdd2933efc91166',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGInput.dll': 'a03f777988d1ec4a7c92ff5fce1ae2d0',
        'Title.dll': '7332e5ba63f85591939e7e4f8a895116',
        'Options.dll': '147385fcb2d3e307e0d9a400d0b1003f',
        'ReplayGallery.dll': '5fff3c2a55232543a6278a7f3f6c16ea',
    },
    'American': {
        'SEGA RALLY 2.exe': 'be49adc3c6dae1b3862abccfd2c4d4da',
        'MUSASHI\\MGameGL.dll': 'fcca6e46daa16a23184e1c1daa21274a',
        'MUSASHI\\MGameD3D.dll': 'a5732b9c9de6a60b6a4e8a0d73941233',
        'MUSASHI\\MGAudio.dll': 'd62b598085dd18757cdd2933efc91166',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGInput.dll': '639dda3670988674018fe3d356f6d223',
        'Title.dll': '7332e5ba63f85591939e7e4f8a895116',
        'Options.dll': '147385fcb2d3e307e0d9a400d0b1003f',
        'ReplayGallery.dll': '5fff3c2a55232543a6278a7f3f6c16ea',
    },
    'Australian': {
        'SEGA RALLY 2.exe': '66721c92b4848e916821e772ae14f782',
        'MUSASHI\\MGameGL.dll': 'fcca6e46daa16a23184e1c1daa21274a',
        'MUSASHI\\MGameD3D.dll': 'a5732b9c9de6a60b6a4e8a0d73941233',
        'MUSASHI\\MGAudio.dll': 'aac1d9efcb2a43fd7442fcffefa5e4d5',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGInput.dll': '2b118aa24ccb0b96f2448a7cf417a642',
        'Title.dll': '590c0b3a8b3e871de11eb9b0f2af5f5c',
        'Options.dll': '6bb2f825c9dbe524bf427d2b876a624b',
        'ReplayGallery.dll': '38c87f78822e3a6ce762c3003e3b8090',
    },
}


def apply_all(build, original, name, keys):
    """The patcher's own site and transform loop, on one file."""
    table = patcher.patches(build)
    buf = bytearray(original)
    for key in keys:
        if key not in table or table[key][0] != name:
            continue
        for off, old, new in table[key][1]:
            if buf[off:off + len(old)] != old:
                raise AssertionError('%s: bytes at 0x%x are not the original' % (key, off))
            if new is not None:
                buf[off:off + len(new)] = new
    for key in keys:
        if key in table and table[key][0] == name and table[key][2]:
            buf = getattr(patcher, table[key][2])(buf, build)
    return bytes(buf)


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    game = argv[1]
    bad = 0
    try:
        build = patcher.check_build(game)
    except (OSError, ValueError) as exc:
        print(str(exc))
        return 1
    print('%s build' % build)
    keys = [k for k in patcher.PATCH_KEYS if k in patcher.patches(build)]
    random.seed(1)
    trials = [set(c) for r in (1, 2) for c in itertools.combinations(keys, r)]
    trials += [set(random.sample(keys, random.randint(3, len(keys) - 1))) for _ in range(100)]
    for name in patcher.PATCHED:
        path = os.path.join(game, *name.split('\\'))
        pristine = path + '.bak' if os.path.isfile(path + '.bak') else path
        with open(pristine, 'rb') as fh:
            original = fh.read()
        failed = 0
        for sel in trials:
            try:
                apply_all(build, original, name, [k for k in keys if k in sel])
            except Exception as exc:                # noqa: BLE001
                failed += 1
                if failed == 1:
                    print('  %s: %s fails: %s' % (name, ' '.join(sorted(sel)), exc))
        result = apply_all(build, original, name, keys)
        digest = hashlib.md5(result).hexdigest()
        note = ''
        expected = EXPECTED.get(build, {}).get(name)
        if expected is None:
            note = 'not pinned'
        elif digest != expected:
            note = 'CHANGED, expected %s' % expected
            bad += 1
        if pristine != path:
            with open(path, 'rb') as fh:
                if fh.read() != result:
                    note = (note + '; ' if note else '') + 'the install is older than this: re-patch'
        print('  %-24s %d -> %d bytes, %d of %d combinations failed, all on %s %s'
              % (name, len(original), len(result), failed, len(trials) + 1, digest, note))
        bad += failed
    print('FAILED' if bad else 'OK')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
