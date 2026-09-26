#!/usr/bin/env python3
"""The SEARCH button and the IP entry popup composed from a game's stock files.

    python3 tools/buttonstest.py GAMEDIR [--show DIR]

Reads BINDATA\\connect\\button\\showteam_* and create_* and
BINDATA\\connect\\IP_ENTRY\\Ip_entry_US.bmp from the game (their .bak when
patched), composes the button's three states and the popup the way the
patcher does and checks them against the pinned digests; --show writes
them to DIR to look at.
"""
import hashlib
import os
import sys

from uctest import patcher

PINNED = {'off': 'e656ede44349f4212336591ac0ddb61e', 'on': '397d748a90948215471c736df7127c48', 'on2': 'ecd7fcf191f9c0c04ef96750dcbef430'}
PINNED_POPUP = '89b4564852536c16a5e6ef37f1c0595e'


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
    folder, name = patcher.lobby_popup_path(argv[1])
    path = os.path.join(folder, name)
    if os.path.isfile(path + '.bak'):
        path += '.bak'
    if not os.path.isfile(path):
        print('buttonstest: SEARCH composed from the stock lettering, three states as pinned')
        print('note: no %s in this install; the popup was not tested' % name)
        return 0
    with open(path, 'rb') as fh:
        data = fh.read()
    if hashlib.md5(data).hexdigest() != patcher.LOBBY_POPUP_MD5:
        raise SystemExit('buttonstest: %s is not the stock file' % path)
    popup = patcher.lobby_popup(data)
    if len(argv) == 4 and argv[2] == '--show':
        with open(os.path.join(argv[3], name), 'wb') as fh:
            fh.write(popup)
    if hashlib.md5(popup).hexdigest() != PINNED_POPUP:
        raise SystemExit('buttonstest: %s came out %s, pinned %s' % (name, hashlib.md5(popup).hexdigest(), PINNED_POPUP))
    print('buttonstest: SEARCH composed from the stock lettering, three states as pinned; the popup as pinned')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
