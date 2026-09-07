#!/usr/bin/env python3
"""Run every check in the project.

    python3 tools/check.py                    # everything that needs no game
    python3 tools/check.py data1.cab          # and the cabinet reader on a real cab
    python3 tools/check.py data1.cab GAMEDIR  # and compare it with an installed game

tables  a patch site outside the file, two patches on one byte, a
        replacement longer than the original
asm     asm/ edited without asm/build.py being run; skipped without nasm
lint    pyflakes: unused and undefined names
cab     the IS5 reader misreading a real data1.cab; skipped without one
music   the music hook under Unicorn, driven the way MGAudio drives it;
        needs GAMEDIR and python3-unicorn, skipped without
altab   the alt-tab stub under Unicorn, same requirements
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable or 'python3'


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
                       'tools/cabtest.py', 'tools/iso2bin.py', 'tools/musictest.py', 'tools/activatetest.py'])
    if len(argv) > 1:
        ok &= run('cab', [PY, 'tools/cabtest.py'] + argv[1:])
    else:
        print('== cab\n   skipped: no data1.cab given')
    if len(argv) > 2:
        ok &= run('music', [PY, 'tools/musictest.py', argv[2]])
        ok &= run('altab', [PY, 'tools/activatetest.py', argv[2]])
    else:
        print('== music\n   skipped: no game folder given')
        print('== altab\n   skipped: no game folder given')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
