#!/usr/bin/env python3
"""Run every check in the project.

    python3 tools/check.py                    # everything; discs and games from ~/.sr2-test
    python3 tools/check.py data1.cab          # the cabinet reader on this cab instead
    python3 tools/check.py data1.cab GAMEDIR  # and the game checks on this install
    python3 tools/check.py --list             # what there is
    python3 tools/check.py --only cab,music   # some of it

~/.sr2-test (template: tools/sr2-test.example, used by tools/sr2.sh too) names, per build, the
install disc and the installed game: SR2_DISC_EU, SR2_GAME_EU, and the
same with US and AU. Each that is set runs the cab, offsets, music and
altab checks on that build, labelled cab/EU and so on. Each check is a script
of its own; this only decides what to run and reports the result, and
shows a script's output when it fails.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable or 'python3'
CONF = os.path.expanduser('~/.sr2-test')
BUILDS = ('EU', 'US', 'AU')

# name, what, command, needs: '' for none, 'disc' for the install disc
# (and the game if there is one), 'game' for the installed game.
CHECKS = [
    ('tables', 'patch tables: sites inside the file, no overlap, placeholders filled',
     [PY, 'sr2-patcher.py', '--selfcheck'], ''),
    ('asm', 'asm/ sources match the committed blobs',
     [PY, 'asm/build.py', '--check'], ''),
    ('lint', 'pyflakes',
     [PY, '-m', 'pyflakes', 'sr2-patcher.py', 'asm/build.py', 'tools/check.py', 'tools/cabtest.py',
      'tools/iso2bin.py', 'tools/musictest.py', 'tools/activatetest.py', 'tools/bgrowtest.py',
      'tools/fullwintest.py', 'tools/texrangetest.py', 'tools/replayfreetest.py', 'tools/altentertest.py', 'tools/discsurvey.py', 'tools/kit.py',
      'tools/selftest.py', 'tools/padinputtest.py', 'tools/devicestest.py'], ''),
    ('bgrow', 'the .bg row copies under Unicorn, 16 and 32 bits',
     [PY, 'tools/bgrowtest.py'], ''),
    ('fullwin', 'the borderless present and window sizing under Unicorn',
     [PY, 'tools/fullwintest.py'], ''),
    ('altenter', 'the ALT+ENTER toggle under Unicorn',
     [PY, 'tools/altentertest.py'], ''),
    ('texrange', 'the texture release\'s index check under Unicorn',
     [PY, 'tools/texrangetest.py'], ''),
    ('replayfree', 'the replay gallery\'s free under Unicorn',
     [PY, 'tools/replayfreetest.py'], ''),
    ('cab', 'the cabinet reader on a real disc',
     [PY, 'tools/cabtest.py', '{disc}'], 'disc'),
    ('offsets', 'every patch against the real files, in every combination, pinned',
     [PY, 'tools/selftest.py', '{game}'], 'game'),
    ('music', 'the music hook under Unicorn, the real MGAudio.dll',
     [PY, 'tools/musictest.py', '{game}'], 'game'),
    ('altab', 'the alt-tab stub and restore routine under Unicorn, real files',
     [PY, 'tools/activatetest.py', '{game}'], 'game'),
    ('padinput', 'the pad annex under Unicorn, the real MGInput.dll',
     [PY, 'tools/padinputtest.py', '{game}'], 'game'),
    ('devices', 'the Device Settings page binding under Unicorn, the real Options.dll',
     [PY, 'tools/devicestest.py', '{game}'], 'game'),
]


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


def colours(force):
    on = force if force is not None else (
        sys.stdout.isatty() and os.environ.get('NO_COLOR') is None and os.environ.get('TERM') != 'dumb')
    if not on:
        return {k: '' for k in ('ok', 'bad', 'warn', 'dim', 'bold', 'off')}
    return {'ok': '\033[32m', 'bad': '\033[31m', 'warn': '\033[33m',
            'dim': '\033[90m', 'bold': '\033[1m', 'off': '\033[0m'}


def targets(args):
    """(label, disc, game) per build to check."""
    if args.source:
        return [('', args.source, args.game)]
    conf = config()
    out = [(b, conf.get('SR2_DISC_' + b), conf.get('SR2_GAME_' + b)) for b in BUILDS]
    return [t for t in out if t[1] or t[2]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source', nargs='?', help='data1.cab or a disc image')
    ap.add_argument('game', nargs='?', help='an installed game')
    ap.add_argument('--only', help='comma-separated names from --list')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--colour', choices=['auto', 'always', 'never'], default='auto')
    args = ap.parse_args()
    c = colours({'auto': None, 'always': True, 'never': False}[args.colour])
    if args.list:
        for name, what, _cmd, needs in CHECKS:
            print('  %-9s %-64s %s' % (name, what, 'needs the %s' % needs if needs else ''))
        return 0

    wanted = set(args.only.split(',')) if args.only else None
    builds = targets(args)
    os.chdir(ROOT)
    results = []
    for name, what, cmd, needs in CHECKS:
        if wanted and name not in wanted:
            continue
        if name == 'asm' and not shutil.which('nasm'):
            print('  %s%-13s SKIP%s  %s %s(nasm not installed)%s' % (c['warn'], name, c['off'], what, c['dim'], c['off']))
            results.append((name, None))
            continue
        runs = [(None, None, None)] if not needs else \
            [t for t in builds if (t[1] if needs == 'disc' else t[2])]
        if not runs:
            print('  %s%-13s SKIP%s  %s %s(no %s in %s)%s'
                  % (c['warn'], name, c['off'], what, c['dim'], needs, CONF, c['off']))
            results.append((name, None))
            continue
        for label, disc, game in runs:
            run = [a.replace('{disc}', disc or '').replace('{game}', game or '') for a in cmd]
            run = [a for a in run if a]
            start = time.time()
            proc = subprocess.run(run, capture_output=True, text=True)
            took = time.time() - start
            good = proc.returncode == 0
            tag = name + '/' + label if label else name
            results.append((tag, good))
            print('  %s%-13s%s %s  %-64s %s%.1fs%s'
                  % (c['bold'], tag, c['off'],
                     '%sOK  %s' % (c['ok'], c['off']) if good else '%sFAIL%s' % (c['bad'], c['off']),
                     what, c['dim'], took, c['off']))
            out = (proc.stdout + proc.stderr).strip().split('\n')
            for line in out if not good else [l for l in out if l.startswith('note: ')]:
                print('      %s%s%s' % (c['dim'], line.replace('note: ', '', 1), c['off']))

    ran = [r for _n, r in results if r is not None]
    failed = [n for n, r in results if r is False]
    skipped = [n for n, r in results if r is None]
    print()
    if failed:
        print('%s%d of %d failed: %s%s' % (c['bad'], len(failed), len(ran), ' '.join(failed), c['off']))
    else:
        print('%sall %d passed%s' % (c['ok'], len(ran), c['off']))
    if skipped:
        print('%s%d skipped: %s%s' % (c['warn'], len(skipped), ' '.join(skipped), c['off']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
