#!/usr/bin/env python3
"""The connection screen's confirm under Unicorn, against the real exe.

    python3 tools/lobbytest.py GAMEDIR

With the lobby patch, confirming a row stores the type, points the next
screen at the team list, and for INTERNET and LAN sets the flag the list
searches on when it opens; DIRECT IP leaves it clear, since its search
needs an address first. Needs python3-unicorn; exits 77 without it.
"""
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('lobbytest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESP

STACK = 0x900000


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    build = patcher.check_build(argv[1])
    buf = bytearray(uctest.stock(argv[1], patcher.EXE))
    for off, old, new in patcher.patches(build)['lobby'][1]:
        assert buf[off:off + len(old)] == old, 'lobby: bytes at %#x' % off
        if new is not None:
            buf[off:off + len(new)] = new
    row = patcher.BUILDS[build]
    confirm = row['sites']['lobby'][2]
    nextscreen, modem, flag = row['addresses']['LISTOPEN']
    base = patcher._image_base(buf)
    entry = base + patcher._off_to_rva(buf, confirm + 0x5)
    end = entry + 15 + 10 + 5                            # the flag, the next screen, the type store
    typeslot = struct.unpack('<I', buf[confirm + 0x1f:confirm + 0x23])[0]      # mov [type], al

    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    uctest.map_image(mu, buf, base)
    mu.mem_map(STACK, 0x10000)
    for cursor, want in ((0, 1), (1, 0), (2, 1)):
        mu.mem_write(flag, struct.pack('<I', 0))
        mu.mem_write(nextscreen, struct.pack('<I', 0))
        mu.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
        mu.reg_write(UC_X86_REG_EAX, cursor)
        mu.emu_start(entry, end, count=100)
        got = struct.unpack('<I', mu.mem_read(flag, 4))[0]
        screen = struct.unpack('<I', mu.mem_read(nextscreen, 4))[0]
        stored = mu.mem_read(typeslot, 1)[0]
        if got != want or screen == modem or stored != cursor:
            raise SystemExit('lobbytest: row %d: flag %d, next screen %#x, type %d' % (cursor, got, screen, stored))
    print('lobbytest: %s: INTERNET and LAN open the list searching, DIRECT IP does not' % build)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
