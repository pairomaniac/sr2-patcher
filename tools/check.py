#!/usr/bin/env python3
"""Run every check in the project.

    python3 tools/check.py                    # everything that needs no game
    python3 tools/check.py data1.cab          # and the cabinet reader on a real cab
    python3 tools/check.py data1.cab GAMEDIR  # and compare it with an installed game

tables  a patch site outside the file, two patches on one byte, a
        replacement longer than the original
lint    pyflakes: unused and undefined names
cab     the IS5 reader misreading a real data1.cab; skipped without one
"""
import os
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
    ok &= run('lint', [PY, '-m', 'pyflakes', 'sr2-patcher.py', 'tools/check.py', 'tools/cabtest.py', 'tools/iso2bin.py'])
    if len(argv) > 1:
        ok &= run('cab', [PY, 'tools/cabtest.py'] + argv[1:])
    else:
        print('== cab\n   skipped: no data1.cab given')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
