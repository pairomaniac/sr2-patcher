#!/usr/bin/env python3
"""The REFRESH button composed from a game's stock button files.

    python3 tools/buttonstest.py GAMEDIR [--show DIR]

Reads BINDATA\\connect\\button\\showteam_* and create_* from the game (their
.bak when patched), composes the three states the way the patcher does
and checks them against the pinned digests; --show writes them to DIR to
look at.
"""
import hashlib
import os
import sys

from uctest import patcher

PINNED = {'off': '8ae1dd5a2a2d291f3e9f3d57de9042bc', 'on': '4f91c129123ae1c7c42d3bd08b53a8f0', 'on2': 'b0a9cd79b7cd0b9edf4918b6ab1fb7b7'}


def main(argv):
    if len(argv) not in (2, 4):
        print(__doc__.strip())
        return 2
    folder = os.path.join(argv[1], *patcher.LOBBY_BUTTON_DIR.split('\\'))
    stock = {}
    for name, digests in patcher.LOBBY_BUTTON_MD5.items():
        stock[name] = []
        for state, digest in zip(patcher.LOBBY_BUTTON_STATES, digests):
            path = os.path.join(folder, '%s_%s.BMP' % (name, state))
            if os.path.isfile(path + '.bak'):
                path += '.bak'
            if not os.path.isfile(path):
                print('note: no %s; the button folder is not in this install' % path)
                return 0
            with open(path, 'rb') as fh:
                data = fh.read()
            if hashlib.md5(data).hexdigest() != digest:
                raise SystemExit('buttonstest: %s is not the stock file' % path)
            stock[name].append(data)
    out = patcher.lobby_buttons(stock)
    if len(argv) == 4 and argv[2] == '--show':
        os.makedirs(argv[3], exist_ok=True)
        for state, data in out.items():
            with open(os.path.join(argv[3], 'showteam_%s.BMP' % state), 'wb') as fh:
                fh.write(data)
    for state, data in out.items():
        if hashlib.md5(data).hexdigest() != PINNED[state]:
            raise SystemExit('buttonstest: showteam_%s.BMP came out %s, pinned %s' % (state, hashlib.md5(data).hexdigest(), PINNED[state]))
    print('buttonstest: REFRESH composed from the stock lettering, three states as pinned')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
