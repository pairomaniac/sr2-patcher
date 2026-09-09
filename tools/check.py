#!/usr/bin/env python3
"""Run every check in the project.

    python3 tools/check.py                    # everything; discs and games from ~/.sr2-test
    python3 tools/check.py data1.cab          # the cabinet reader on this cab instead
    python3 tools/check.py data1.cab GAMEDIR  # and compare it with this installed game

~/.sr2-test (template: tools/sr2-test.example) names, per build, the
install disc and the installed game: SR2_DISC_EU, SR2_GAME_EU, and the
same with US and AU. Each that is set runs the cab, music and altab
checks below on that build.

tables  a patch site outside the file, two patches on one byte, a
        replacement longer than the original, a placeholder left in a
        stub
asm     asm/ edited without asm/build.py being run; skipped without nasm
lint    pyflakes: unused and undefined names
cab     the IS5 reader misreading a real data1.cab; skipped without one
music   the music hook under Unicorn, driven the way MGAudio drives it;
        needs GAMEDIR and python3-unicorn, skipped without
altab   the alt-tab stub and the rewritten restore routine under Unicorn,
        same requirements
bgrow   the .bg row copies under Unicorn at 16 and 32 bits; needs
        python3-unicorn, skipped without
fullwin the borderless present and window sizing under Unicorn, same
altenter the ALT+ENTER toggle under Unicorn, same
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable or 'python3'
CONF = os.path.expanduser('~/.sr2-test')
BUILDS = ('EU', 'US', 'AU')


def config():
    """KEY=VALUE lines of ~/.sr2-test, quotes and ~ resolved."""
    out = {}
    if not os.path.isfile(CONF):
        return out
    with open(CONF) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.replace('export ', '').strip()
            value = value.strip().strip('"\'')
            out[key] = os.path.expanduser(value.replace('$HOME', '~'))
    return out


def run(name, cmd):
    print('== %s' % name)
    rc = subprocess.call(cmd, cwd=ROOT)
    print('   %s' % ('OK' if rc == 0 else 'FAILED (%d)' % rc))
    return rc == 0


def main(argv):
    ok = run('tables', [PY, 'sr2-patcher.py', '--selfcheck'])
    if shutil.which('nasm'):
        ok &= run('asm', [PY, 'asm/build.py', '--check'])
    else:
        print('== asm\n   skipped: nasm not installed')
    ok &= run('lint', [PY, '-m', 'pyflakes', 'sr2-patcher.py', 'asm/build.py', 'tools/check.py',
                       'tools/cabtest.py', 'tools/iso2bin.py', 'tools/musictest.py', 'tools/activatetest.py',
                       'tools/bgrowtest.py', 'tools/fullwintest.py', 'tools/altentertest.py'])
    ok &= run('bgrow', [PY, 'tools/bgrowtest.py'])
    ok &= run('fullwin', [PY, 'tools/fullwintest.py'])
    ok &= run('altenter', [PY, 'tools/altentertest.py'])
    if len(argv) > 1:
        targets = [('', argv[1], argv[2] if len(argv) > 2 else None)]
    else:
        conf = config()
        targets = [(b, conf.get('SR2_DISC_' + b), conf.get('SR2_GAME_' + b)) for b in BUILDS]
        targets = [t for t in targets if t[1] or t[2]]
    if not targets:
        print('== cab, music, altab\n   skipped: no disc or game given, none in %s' % CONF)
    for build, disc, game in targets:
        tag = ' ' + build if build else ''
        if disc:
            ok &= run('cab' + tag, [PY, 'tools/cabtest.py', disc] + ([game] if game else []))
        if game:
            ok &= run('music' + tag, [PY, 'tools/musictest.py', game])
            ok &= run('altab' + tag, [PY, 'tools/activatetest.py', game])
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
