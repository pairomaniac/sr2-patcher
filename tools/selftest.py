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
        'SEGA RALLY 2.exe': 'b002dfbabc7f50b15adc212f201c3cfc',
        'MUSASHI\\MGameD3D.dll': '1bf6b62a6bed2552924097fae3344634',
        'MUSASHI\\MGAudio.dll': '11b2f8cd6dccd4df4b0b4d49c9a6c1d6',
        'MUSASHI\\MGSound.dll': '8acc33de7866061672e989844bb38929',
        'MUSASHI\\MGInput.dll': 'b0f146bb86654086e65e0cdc8bad9dc8',
        'Title.dll': '17a6a4f0b36e4f98dcebc3e038ddfb3c',
        'Options.dll': '87b19122a6f90587825ca70bc0238b55',
    },
    'American': {
        'SEGA RALLY 2.exe': '97e9d93bdf7586d31cb51fa4c3d7bf13',
        'MUSASHI\\MGameD3D.dll': '1bf6b62a6bed2552924097fae3344634',
        'MUSASHI\\MGAudio.dll': '11b2f8cd6dccd4df4b0b4d49c9a6c1d6',
        'MUSASHI\\MGSound.dll': '8acc33de7866061672e989844bb38929',
        'MUSASHI\\MGInput.dll': '00be105598ae163718f2a125db309815',
        'Title.dll': '17a6a4f0b36e4f98dcebc3e038ddfb3c',
        'Options.dll': '87b19122a6f90587825ca70bc0238b55',
    },
    'Australian': {
        'SEGA RALLY 2.exe': 'b4da2fd7281a23268ccc1b5ff79f88a8',
        'MUSASHI\\MGameD3D.dll': '1bf6b62a6bed2552924097fae3344634',
        'MUSASHI\\MGAudio.dll': 'bddcc15cf4d8f2e246b32a82742e1afa',
        'MUSASHI\\MGSound.dll': '8acc33de7866061672e989844bb38929',
        'MUSASHI\\MGInput.dll': 'ab9e57ce1eec012542ca4b41ce88088d',
        'Title.dll': '12af6ad8236f168605d0b2ef526c9244',
        'Options.dll': 'd04741c541518da943b443abce16a969',
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
