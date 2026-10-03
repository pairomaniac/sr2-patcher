#!/usr/bin/env python3
"""Apply the patch tables to a real install and report.

    python3 tools/selftest.py GAMEDIR        # an installed game, patched or not

CI cannot do this - the game is not in the repository - so it runs from
~/.sr2-test through tools/check.py. It checks what nothing else can:

  * every original byte string in the tables is really in the file
  * every patch applies alone, in every pair and in a hundred random sets, not just all on,
    each set with what its patches need
  * the fully patched result has the MD5 it had last time, with the full
    resolution table and with the one capped at 2048 a side that patch()
    writes on Windows without the dgVoodoo add-on

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
# EXPECTED_CAPPED: the files the capped resolution table changes.
EXPECTED_CAPPED = {
    'European': {
        'SEGA RALLY 2.exe': '3d3d0065bdd6bfbb865889c61f28b3b7',
        'Options.dll': '64de22b3ec728c8373659a7578d780e8',
    },
    'American': {
        'SEGA RALLY 2.exe': '54c258bb2cc11333ac130383f0a9d817',
        'Options.dll': '64de22b3ec728c8373659a7578d780e8',
    },
    'Australian': {
        'SEGA RALLY 2.exe': '53a911ddd53252f82e50a98f760f4b34',
        'Options.dll': '18a3dcabac729e80f31153053da0be13',
    },
    'Japanese (DigiCube, MediaKite)': {
        'SEGA RALLY 2.exe': 'fde1fb31acc8cb5c4c96df225d32959b',
        'Options.dll': '64de22b3ec728c8373659a7578d780e8',
    },
}
EXPECTED = {
    'European': {
        'SEGA RALLY 2.exe': '7319472bc2e02f495f174ab92867185a',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '2fdba927154ccb2cc0e22cb43b675059',
        'MUSASHI\\MGAudio.dll': '7793a537317e3a45dd51c1776af63e90',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '9665e26a5396926b0db8d505954a2203',
        'MUSASHI\\MGInput.dll': 'abe98034301aafdaf92554f0a8c7d7f5',
        'Title.dll': '432a6d65e596f4c909d9c07af64e8a4b',
        'Options.dll': 'a2404043d58f73537312795c714e730e',
        'ReplayGallery.dll': '2ba9a104b6937becb2e0e2a65e889da7',
        'Record.dll': '580a555f8b1961d71c9cc2de62e19e9d',
        'AdvTelop.dll': '6d8e54fdddcbde12b627fa522fdc913e',
    },
    'American': {
        'SEGA RALLY 2.exe': 'a9f70233ec45aecec4e5b5249b5a9d6d',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '2fdba927154ccb2cc0e22cb43b675059',
        'MUSASHI\\MGAudio.dll': '7793a537317e3a45dd51c1776af63e90',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '9665e26a5396926b0db8d505954a2203',
        'MUSASHI\\MGInput.dll': '4f15e627caf77adc2ac0b48e059261a8',
        'Title.dll': 'c3615cdc3c6a60f876ca66010d572fdd',
        'Options.dll': 'a2404043d58f73537312795c714e730e',
        'ReplayGallery.dll': '2ba9a104b6937becb2e0e2a65e889da7',
        'Record.dll': '580a555f8b1961d71c9cc2de62e19e9d',
        'AdvTelop.dll': '6d8e54fdddcbde12b627fa522fdc913e',
    },
    'Australian': {
        'SEGA RALLY 2.exe': 'aa749c85b9914c80e44c3ed2dbab166a',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '2fdba927154ccb2cc0e22cb43b675059',
        'MUSASHI\\MGAudio.dll': '0ef438db85e4d4d28d7b42084edcff07',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '9665e26a5396926b0db8d505954a2203',
        'MUSASHI\\MGInput.dll': '0e39f9b494c56476905ef688173899b2',
        'Title.dll': 'cc9285aee0c5dc00a8f55ccfa9d6d090',
        'Options.dll': '0aadf9270a4a069129520c4c5867b65e',
        'ReplayGallery.dll': '1b93ce6a681adcfda55d1aef77d1f8f0',
        'Record.dll': 'be9e6c5cb93956003c4012e869ee2e79',
        'AdvTelop.dll': 'eea793ceff7b2d7b297903dd324f0396',
    },
    'Japanese (DigiCube, MediaKite)': {
        'SEGA RALLY 2.exe': '6c43072a7fd1c38b72bf903b0b473ca2',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '2fdba927154ccb2cc0e22cb43b675059',
        'MUSASHI\\MGAudio.dll': '7793a537317e3a45dd51c1776af63e90',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '9665e26a5396926b0db8d505954a2203',
        'MUSASHI\\MGInput.dll': 'abe98034301aafdaf92554f0a8c7d7f5',
        'Title.dll': '432a6d65e596f4c909d9c07af64e8a4b',
        'Options.dll': 'a2404043d58f73537312795c714e730e',
        'ReplayGallery.dll': '2ba9a104b6937becb2e0e2a65e889da7',
        'Record.dll': '580a555f8b1961d71c9cc2de62e19e9d',
        'AdvTelop.dll': '6d8e54fdddcbde12b627fa522fdc913e',
    },
}


def apply_all(build, original, name, keys):
    """The patcher's own site and transform loop, on one file."""
    table = patcher.patches(build)
    keys = [key for key in table if key in keys] + [key for key in keys if key not in table]       # the table's order, as patch() takes them
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

    def with_needs(sel):
        for _ in range(len(patcher.NEEDS)):
            sel |= set(need for key, need in patcher.NEEDS if key in sel)
        return sel
    # every patch with what it needs: alone, in pairs and in random sets
    trials = [with_needs(set(c)) for r in (1, 2) for c in itertools.combinations(keys, r)]
    trials += [with_needs(set(random.sample(keys, random.randint(3, len(keys) - 1)))) for _ in range(100)]
    # the diagnostics too: each with what it needs, each on top of everything, and in random sets
    diagnostics = [k for k in patcher.DIAGNOSTIC if k in patcher.patches(build)]
    trials += [with_needs({d}) for d in diagnostics] + [set(keys) | {d} for d in diagnostics]
    trials += [with_needs(set(random.sample(keys, random.randint(3, len(keys) - 1))) | {random.choice(diagnostics)})
               for _ in range(20)]
    keys += diagnostics
    keys = [k for k in patcher.patches(build) if k in keys]     # the table's order, as patch() applies them; the pin below is the patches alone
    for name in patcher.PATCHED:
        path = os.path.join(game, *name.split('\\'))
        pristine = path + '.bak' if os.path.isfile(path + '.bak') else path
        with open(pristine, 'rb') as fh:
            original = fh.read()
        failed = 0
        for sel in trials:
            try:
                apply_all(build, original, name, [k for k in keys if k in sel])
            except Exception as exc:                # anything a transform raises is the failure counted
                failed += 1
                if failed == 1:
                    print('  %s: %s fails: %s' % (name, ' '.join(sorted(sel)), exc))
        result = apply_all(build, original, name, [k for k in keys if k not in diagnostics])
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
        patcher.select_resolutions('capped')
        try:
            capped = hashlib.md5(apply_all(build, original, name, [k for k in keys if k not in diagnostics])).hexdigest()
        finally:
            patcher.select_resolutions('full')
        if capped != digest:
            expected = EXPECTED_CAPPED.get(build, {}).get(name)
            note = 'not pinned' if expected is None else ('CHANGED, expected %s' % expected if capped != expected else '')
            bad += note.startswith('CHANGED')
            print('  %-24s capped resolution table: %s %s' % ('', capped, note))
    print('FAILED' if bad else 'OK')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
