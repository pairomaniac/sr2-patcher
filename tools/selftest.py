#!/usr/bin/env python3
"""Apply the patch tables to a real install and report.

    python3 tools/selftest.py GAMEDIR        # an installed game, patched or not

CI cannot do this - the game is not in the repository - so it runs from
~/.sr2-test through tools/check.py. It checks what nothing else can:

  * every original byte string in the tables is really in the file
  * every patch applies alone, in every pair and in a hundred random sets, not just all on
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
        'SEGA RALLY 2.exe': '4159b950f5b844585e1918a1c14e955d',
        'Options.dll': '2b3820776c71a1d79c850cdd20633bcb',
    },
    'American': {
        'SEGA RALLY 2.exe': '41141e144ee592e8c9870f1b7ec86c0b',
        'Options.dll': '2b3820776c71a1d79c850cdd20633bcb',
    },
    'Australian': {
        'SEGA RALLY 2.exe': '352ab40d22e4f28d5dd90f307506456b',
        'Options.dll': '9ece57286ac7c71e5d01bdbeb233a4b2',
    },
    'Japanese (DigiCube, MediaKite)': {
        'SEGA RALLY 2.exe': '1b7deb0a7b7008d93800cf38345bb660',
        'Options.dll': '2b3820776c71a1d79c850cdd20633bcb',
    },
}
EXPECTED = {
    'European': {
        'SEGA RALLY 2.exe': 'f54fac7cbea61148e99ee98973114743',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '31516b1229bb5922bc61f9b1daf8fb89',
        'MUSASHI\\MGAudio.dll': '7793a537317e3a45dd51c1776af63e90',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '2ca3d4bd5e810780f2e4280f50f3982d',
        'MUSASHI\\MGInput.dll': 'd2b51cb4d42fd7a126b22893461f8282',
        'Title.dll': 'e1c9c52c9e1d4baa6119b3ee1c7309cf',
        'Options.dll': 'af7cdfbcf503c319374366ce58cbf8e2',
        'ReplayGallery.dll': '26b937c025a7da3f2a9117424821089a',
    },
    'American': {
        'SEGA RALLY 2.exe': '3a9e13fd8c70eca48e9050fd39dd60b5',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '31516b1229bb5922bc61f9b1daf8fb89',
        'MUSASHI\\MGAudio.dll': '7793a537317e3a45dd51c1776af63e90',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '2ca3d4bd5e810780f2e4280f50f3982d',
        'MUSASHI\\MGInput.dll': 'a7b29785fb197f8f24ce2493e3cb11af',
        'Title.dll': '7740270e74b79c7e88910878d037563b',
        'Options.dll': 'af7cdfbcf503c319374366ce58cbf8e2',
        'ReplayGallery.dll': '26b937c025a7da3f2a9117424821089a',
    },
    'Australian': {
        'SEGA RALLY 2.exe': '18a28ab050a424b93862f73b01345358',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '31516b1229bb5922bc61f9b1daf8fb89',
        'MUSASHI\\MGAudio.dll': '0ef438db85e4d4d28d7b42084edcff07',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '2ca3d4bd5e810780f2e4280f50f3982d',
        'MUSASHI\\MGInput.dll': '5cd3b75d6afa1092319d2ccec0b2da37',
        'Title.dll': '49c1c4c34da3afdac51b515a17100003',
        'Options.dll': '5085b4806db04d3dd3adb5e0b0e33b06',
        'ReplayGallery.dll': 'df6943632cc46c835bc5b7bf0c33c8b6',
    },
    'Japanese (DigiCube, MediaKite)': {
        'SEGA RALLY 2.exe': '298e7a9b9dd67524e3f711e762a4c0c0',
        'MUSASHI\\MGameGL.dll': '0dddd6b6300d818c009d409043b2424c',
        'MUSASHI\\MGameD3D.dll': '31516b1229bb5922bc61f9b1daf8fb89',
        'MUSASHI\\MGAudio.dll': '7793a537317e3a45dd51c1776af63e90',
        'MUSASHI\\MGSound.dll': 'f53d3c4ca507da0f04e8a81f0882388b',
        'MUSASHI\\MGNetWk.dll': '2ca3d4bd5e810780f2e4280f50f3982d',
        'MUSASHI\\MGInput.dll': 'd2b51cb4d42fd7a126b22893461f8282',
        'Title.dll': 'e1c9c52c9e1d4baa6119b3ee1c7309cf',
        'Options.dll': 'af7cdfbcf503c319374366ce58cbf8e2',
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
    # the diagnostics too: each with what it needs, each on top of everything, and in random sets
    diagnostics = [k for k in patcher.DIAGNOSTIC if k in patcher.patches(build)]

    def with_needs(sel):
        for _ in range(len(patcher.NEEDS)):
            sel |= set(need for key, need in patcher.NEEDS if key in sel)
        return sel
    trials += [with_needs({d}) for d in diagnostics] + [set(keys) | {d} for d in diagnostics]
    trials += [with_needs(set(random.sample(keys, random.randint(3, len(keys) - 1))) | {random.choice(diagnostics)})
               for _ in range(20)]
    keys += diagnostics                             # the order apply_all takes them in; the pin below is the patches alone
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
