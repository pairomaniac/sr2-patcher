#!/usr/bin/env python3
"""Run every check in the project.

    python3 tools/check.py                    # everything; discs and games from ~/.sr2-test
    python3 tools/check.py data1.cab          # the cabinet reader on this cab instead
    python3 tools/check.py data1.cab GAMEDIR  # and the game checks on this install
    python3 tools/check.py --list             # what there is
    python3 tools/check.py --only cab,music   # some of it

~/.sr2-test (template: tools/sr2-test.example, used by tools/sr2.sh too)
names, per build, the install disc and the installed game: SR2_DISC_EU,
SR2_GAME_EU, and the same with US, AU, JP (Sega's disc) and JP_MK (the
DigiCube and MediaKite reissue). Each that is set runs the checks that
need a disc or a game on that build, labelled cab/EU and so on; one that
is in the file but empty is shown as N/A. Each check is a script of its
own; this only decides what to run and reports the result, and shows a
script's output when it fails.
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
SKIPPED = 77            # tools/uctest.py's exit code for "could not run"
TIMEOUT = 900           # seconds a check may take; a looping stub would otherwise hang the run
BUILDS = ('EU', 'US', 'AU', 'JP', 'JP_MK')

# name, what, command, needs: '' for none, 'disc' for the install disc
# (and the game if there is one), 'game' for the installed game.
CHECKS = [
    ('tables', 'the patch tables: sites in range, no overlap, no placeholder',
     [PY, 'sr2-patcher.py', '--selfcheck'], ''),
    ('asm', 'asm/ sources match the committed blobs',
     [PY, 'asm/build.py', '--check'], ''),
    ('lint', 'pyflakes',
     [PY, '-m', 'pyflakes', 'sr2-patcher.py', 'asm/build.py', 'tools/check.py', 'tools/cabtest.py',
      'tools/iso2bin.py', 'tools/musictest.py', 'tools/activatetest.py', 'tools/bgrowtest.py',
      'tools/fullwintest.py', 'tools/texrangetest.py', 'tools/replayfreetest.py', 'tools/altentertest.py', 'tools/clearsizetest.py', 'tools/lobbytest.py', 'tools/buttonstest.py', 'tools/loadholdtest.py', 'tools/padmenutest.py', 'tools/replaypadtest.py', 'tools/pagepadtest.py', 'tools/sortpadtest.py', 'tools/discsurvey.py', 'tools/kit.py',
      'tools/frametracetest.py', 'tools/frames.py', 'tools/d3dinittest.py', 'tools/dgvoodootest.py',
      'tools/selftest.py', 'tools/guitest.py', 'tools/assets.py', 'tools/padinputtest.py', 'tools/devicestest.py', 'tools/widetest.py',
      'tools/resolutiontest.py', 'tools/dinput8test.py', 'tools/nogenerictest.py', 'tools/hudlasttest.py', 'tools/loudness.py', 'tools/txrdump.py', 'tools/uctest.py', 'tools/labels.py', 'tools/nettest.py', 'tools/directorytest.py', 'net/build.py', 'net/directory.py', 'tools/padbits.py'], ''),
    ('labels', 'the baked labels against a render (skips without Pillow)',
     [PY, 'tools/labels.py', '--check'], ''),
    ('net', 'net/ matches the MGNetWk.dll build the script carries',
     [PY, 'net/build.py', '--check'], ''),
    ('nettest', 'the network core over loopback, with loss (skips without cc)',
     [PY, 'tools/nettest.py'], ''),
    ('directorytest', 'the directory server\'s list limit',
     [PY, 'tools/directorytest.py'], ''),
    ('bgrow', 'the .bg copies under Unicorn, 16 and 32 bits, scaled',
     [PY, 'tools/bgrowtest.py'], ''),
    ('wide', 'the widescreen stubs: the size, FOV, viewport and 2D scaling',
     [PY, 'tools/widetest.py'], ''),
    ('fullwin', 'the borderless present and window sizing under Unicorn',
     [PY, 'tools/fullwintest.py'], ''),
    ('altenter', 'the ALT+ENTER toggle under Unicorn',
     [PY, 'tools/altentertest.py'], ''),
    ('loadhold', 'the loading screens\' hold under Unicorn',
     [PY, 'tools/loadholdtest.py'], ''),
    ('padmenu', 'the pad\'s Back as TAB under Unicorn',
     [PY, 'tools/padmenutest.py'], ''),
    ('pagepad', 'the pad\'s bumpers as Page Up and Page Down under Unicorn',
     [PY, 'tools/pagepadtest.py'], ''),
    ('hudlast', 'the HUD drawn after the tree under Unicorn',
     [PY, 'tools/hudlasttest.py'], ''),
    ('frametrace', 'the frame log stub under Unicorn',
     [PY, 'tools/frametracetest.py'], ''),
    ('texrange', 'the texture release\'s index check under Unicorn',
     [PY, 'tools/texrangetest.py'], ''),
    ('d3dinit', 'the bring-up log stub under Unicorn',
     [PY, 'tools/d3dinittest.py'], ''),
    ('replayfree', 'the replay gallery\'s free under Unicorn',
     [PY, 'tools/replayfreetest.py'], ''),
    ('dgvoodoo', 'the dgVoodoo 2 add-on against a made-up release',
     [PY, 'tools/dgvoodootest.py'], ''),
    ('gui', 'the window, driven headlessly (skips without a display)',
     [PY, 'tools/guitest.py'], ''),
    ('cab', 'the cabinet reader on a real disc',
     [PY, 'tools/cabtest.py', '{disc}'], 'disc'),
    ('offsets', 'every patch on the real files, every combination, pinned',
     [PY, 'tools/selftest.py', '{game}'], 'game'),
    ('music', 'the music hook, the real MGAudio.dll',
     [PY, 'tools/musictest.py', '{game}'], 'game'),
    ('altab', 'the alt-tab stub and restore routine, the real files',
     [PY, 'tools/activatetest.py', '{game}'], 'game'),
    ('padinput', 'the pad annex, the real MGInput.dll',
     [PY, 'tools/padinputtest.py', '{game}'], 'game'),
    ('dinput8', 'the DirectInput 8 create and type map, the real MGInput.dll',
     [PY, 'tools/dinput8test.py', '{game}'], 'game'),
    ('nogeneric', 'the device list filter, the real MGInput.dll',
     [PY, 'tools/nogenerictest.py', '{game}'], 'game'),
    ('devices', 'the Device Settings page binding, the real Options.dll',
     [PY, 'tools/devicestest.py', '{game}'], 'game'),
    ('resolution', 'the resolution row, the real Options.dll',
     [PY, 'tools/resolutiontest.py', '{game}'], 'game'),
    ('lobby', "the connection screen's confirm, the real exe",
     [PY, 'tools/lobbytest.py', '{game}'], 'game'),
    ('buttons', 'the REFRESH button from the stock lettering, pinned',
     [PY, 'tools/buttonstest.py', '{game}'], 'game'),
    ('clearsize', "the clear's two arguments, the real exe",
     [PY, 'tools/clearsizetest.py', '{game}'], 'game'),
    ('replaypad', "the pad on the replay's camera controls, the real exe",
     [PY, 'tools/replaypadtest.py', '{game}'], 'game'),
    ('sortpad', "the pad's LB and RB on the gallery's sort, ReplayGallery.dll",
     [PY, 'tools/sortpadtest.py', '{game}'], 'game'),
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
    """(label, disc, game) per build in ~/.sr2-test. A variable that is
    absent is None, one that is in the file but empty is ''."""
    if args.source:
        return [('', args.source, args.game)]
    conf = config()
    out = [(b, conf.get('SR2_DISC_' + b), conf.get('SR2_GAME_' + b)) for b in BUILDS]
    return [t for t in out if t[1] is not None or t[2] is not None]


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
            print('  %-13s %-60s %s' % (name, what, 'needs the %s' % needs if needs else ''))
        return 0

    wanted = set(args.only.split(',')) if args.only else None
    if wanted:
        unknown = wanted - {n for n, _w, _c, _nd in CHECKS}
        if unknown:
            ap.error('no check named %s; --list names them' % ', '.join(sorted(unknown)))
    builds = targets(args)
    labels = [b[0] for b in builds if b[0]]
    width = max([13] + [len(n) + (1 + max(map(len, labels)) if nd and labels else 0)
                        for n, _w, _c, nd in CHECKS])

    def pad(tag):
        return tag.ljust(width)
    os.chdir(ROOT)
    results = []
    for name, what, cmd, needs in CHECKS:
        if wanted and name not in wanted:
            continue
        if name == 'asm' and not shutil.which('nasm'):
            print('  %s%s SKIP%s  %s %s(nasm not installed)%s' % (c['warn'], pad(name), c['off'], what, c['dim'], c['off']))
            results.append((name, None))
            continue
        col = 1 if needs == 'disc' else 2
        runs = [(None, None, None)] if not needs else [t for t in builds if t[col] is not None]
        if not runs:
            print('  %s%s SKIP%s  %s %s(no %s %s)%s'
                  % (c['warn'], pad(name), c['off'], what, c['dim'], needs,
                     'given' if args.source else 'in ' + CONF, c['off']))
            results.append((name, None))
            continue
        for label, disc, game in runs:
            tag = name + '/' + label if label else name
            if needs and not (disc if needs == 'disc' else game):
                var = 'SR2_%s_%s' % ('DISC' if needs == 'disc' else 'GAME', label)
                print('  %s%s N/A   %s (%s empty)%s' % (c['dim'], pad(tag), what, var, c['off']))
                results.append((tag, 'n/a'))
                continue
            run = [a.replace('{disc}', disc or '').replace('{game}', game or '') for a in cmd]
            run = [a for a in run if a]
            start = time.time()
            proc = subprocess.run(run, capture_output=True, text=True, errors='replace', timeout=TIMEOUT)
            took = time.time() - start
            if proc.returncode == SKIPPED:      # the tool said it could not run, which is not a pass
                print('  %s%s SKIP%s  %-60s %s(%s)%s'
                      % (c['warn'], pad(tag), c['off'], what, c['dim'],
                         (proc.stdout + proc.stderr).strip().split('\n')[-1], c['off']))
                results.append((tag, None))
                continue
            good = proc.returncode == 0
            results.append((tag, good))
            print('  %s%s%s %s  %-60s %s%5.1fs%s'
                  % (c['bold'], pad(tag), c['off'],
                     '%sOK  %s' % (c['ok'], c['off']) if good else '%sFAIL%s' % (c['bad'], c['off']),
                     what, c['dim'], took, c['off']))
            out = (proc.stdout + proc.stderr).strip().split('\n')
            for line in out if not good else [l for l in out if l.startswith('note: ')]:
                print('      %s%s%s' % (c['dim'], line.replace('note: ', '', 1), c['off']))

    blank = [n for n, r in results if r == 'n/a']
    results = [(n, r) for n, r in results if r != 'n/a']
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
    if blank:
        print('%s%d n/a: %s%s' % (c['dim'], len(blank), ' '.join(blank), c['off']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
