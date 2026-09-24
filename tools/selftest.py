#!/usr/bin/env python3
"""Apply the patch tables to a real install and report.

    python3 tools/selftest.py GAMEDIR        # an installed game, patched or not

CI cannot do this - the game is not in the repository - so it runs from
~/.sr2-test through tools/check.py. It checks what nothing else can:

  * every original byte string in the tables is really in the file
  * every patch applies alone, in every pair and in a hundred random sets, not just all on
  * the fully patched result has the MD5 it had last time

A patched install that does not hold that result is noted, not failed:
it is older than the tables, and a re-patch brings it up.

The tables are the patcher. A wrong offset passes every other check in
this repository and corrupts somebody's game.
"""
import hashlib
import itertools
import os
import random
import sys

from uctest import patcher

# MD5 of each patched file with every patch on, per build. Update
# deliberately, and only when a patch actually changed.
EXPECTED = {
    'European': {
        'SEGA RALLY 2.exe': '3435e14a5699853b60386ecb8b1f67a6',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '43a4d813412a16bdf0e7594edc62bf13',
        'MUSASHI\\MGAudio.dll': '63ce2a85470987c60de08dfb39270e99',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '66811b4f65d686ca9b3682f6cf2d31e1',
        'MUSASHI\\MGInput.dll': 'd2b51cb4d42fd7a126b22893461f8282',
        'Title.dll': '44820b86f991575fc7d696fd2d88df57',
        'Options.dll': '0491aa518fc3cb4f9e9e9025a754d344',
        'ReplayGallery.dll': '26b937c025a7da3f2a9117424821089a',
    },
    'American': {
        'SEGA RALLY 2.exe': '0b2262e044752f631b49b2ed46533305',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '43a4d813412a16bdf0e7594edc62bf13',
        'MUSASHI\\MGAudio.dll': '63ce2a85470987c60de08dfb39270e99',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '66811b4f65d686ca9b3682f6cf2d31e1',
        'MUSASHI\\MGInput.dll': 'a7b29785fb197f8f24ce2493e3cb11af',
        'Title.dll': 'f6bc04020ed3b2520a325ea00bd97181',
        'Options.dll': '0491aa518fc3cb4f9e9e9025a754d344',
        'ReplayGallery.dll': '26b937c025a7da3f2a9117424821089a',
    },
    'Australian': {
        'SEGA RALLY 2.exe': '899cec001b75153e9c7255ce7a31f7f9',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '43a4d813412a16bdf0e7594edc62bf13',
        'MUSASHI\\MGAudio.dll': '4394c4357861970e78e638de6fa0b287',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '66811b4f65d686ca9b3682f6cf2d31e1',
        'MUSASHI\\MGInput.dll': '5cd3b75d6afa1092319d2ccec0b2da37',
        'Title.dll': '9389461a46a6447a9cd1d799c31d4203',
        'Options.dll': 'f51cec79a4997da6bb240d730ed17303',
        'ReplayGallery.dll': 'df6943632cc46c835bc5b7bf0c33c8b6',
    },
    'Japanese (DigiCube, MediaKite)': {
        'SEGA RALLY 2.exe': 'dc6919eb6958dffd577e54eda7f86cfa',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '43a4d813412a16bdf0e7594edc62bf13',
        'MUSASHI\\MGAudio.dll': '63ce2a85470987c60de08dfb39270e99',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '66811b4f65d686ca9b3682f6cf2d31e1',
        'MUSASHI\\MGInput.dll': 'd2b51cb4d42fd7a126b22893461f8282',
        'Title.dll': '44820b86f991575fc7d696fd2d88df57',
        'Options.dll': '0491aa518fc3cb4f9e9e9025a754d344',
        'ReplayGallery.dll': '26b937c025a7da3f2a9117424821089a',
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
