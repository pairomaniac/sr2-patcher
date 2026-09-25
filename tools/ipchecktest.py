#!/usr/bin/env python3
"""Run the lobby entries' address check and length caps under Unicorn.

    python3 tools/ipchecktest.py GAMEDIR    # the install folder

A copy of the exe patched in memory, the rewritten OK press run on a set
of entries: an address or a name, either with a port, must come back to
the press's own code with the registers as they were and the length
compare's flags; a blank, over-long or malformed one must land on the
popup's sound call with the cancel sound's four arguments pushed. Then
the entry's init run on each field, and the character handler's compare
on the cap it left: the address slot 47, the team name 35, the chat
line 255, the driver name 20, anything else the stock 0x800. Needs
python3-unicorn; exits 77 with a note when it is missing.
"""
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('ipchecktest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EBX,
                               UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_EFLAGS)

BASE = 0x400000
STACK = 0x3000000
ZF = 1 << 6
CF = 1
CANCEL = 0x1c

ACCEPTED = ('192.168.1.20', '192.168.1.20:47626', '10.0.0.1:1', '1.2.3.4:65535', '255.255.255.255',
            'host', 'my-host.example.com', 'a1:7', 'x' * 47, 'x' * 41 + ':47626')
REFUSED = ('', '192.168.1', '192.168.1.256', '1.2.3.4.5', '1..2.3', '1.2.3.', '.1.2.3', '12345',
           ':47626', '1.2.3.4:', '1.2.3.4:0', '1.2.3.4:65536', '1.2.3.4:4a', '1.2.3.4:1:2', 'host name',
           'x' * 48, 'x' * 42 + ':47626')


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    image = uctest.stock(argv[1], patcher.EXE)
    build = uctest.build_of(image, patcher.EXE)
    if build is None:
        print('ipchecktest: the exe is not a build the patcher knows')
        return 1
    row = patcher.BUILDS[build]
    edit, length, deny = (row['addresses'][k] for k in ('IPEDIT', 'IPLEN', 'IPDENY'))
    site = BASE + patcher._off_to_rva(image, row['sites']['ipcheck'])
    init, first, second = (BASE + patcher._off_to_rva(image, off) for off in row['sites']['entries'])
    image = patcher.apply_entries(image, build)
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    uctest.map_image(mu, image, BASE)
    mu.mem_map(STACK, 0x10000)
    stops = (site + 6, deny)

    def stop(mu_, address, size_, user):
        if address in stops:
            mu_.emu_stop()
    mu.hook_add(UC_HOOK_CODE, stop)

    def press(text):
        mu.mem_write(edit, text.encode() + b'\0')
        mu.mem_write(length, struct.pack('<I', len(text)))
        esp = STACK + 0x8000
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_ESI, 0)
        mu.reg_write(UC_X86_REG_EBX, 1)
        mu.reg_write(UC_X86_REG_EDI, 0x1111)
        mu.reg_write(UC_X86_REG_EBP, 0x2222)
        mu.emu_start(site, 0, count=5000)
        eip = mu.reg_read(UC_X86_REG_EIP)
        assert eip in stops, '%r: stopped at 0x%x' % (text, eip)
        regs = tuple(mu.reg_read(r) for r in (UC_X86_REG_ESI, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_EBP))
        assert regs == (0, 1, 0x1111, 0x2222), '%r: registers %r' % (text, regs)
        if eip == deny:
            assert mu.reg_read(UC_X86_REG_ESP) == esp - 16, '%r: stack on refusal' % text
            args = struct.unpack('<4I', mu.mem_read(esp - 16, 16))
            assert args == (CANCEL, 0, 0, 0), '%r: sound arguments %r' % (text, args)
            return False
        assert mu.reg_read(UC_X86_REG_ESP) == esp, '%r: stack on acceptance' % text
        assert not mu.reg_read(UC_X86_REG_EFLAGS) & ZF, '%r: accepted as blank' % text
        return True

    for text in ACCEPTED:
        assert press(text), '%r refused' % text
    for text in REFUSED:
        assert not press(text), '%r accepted' % text
    # the caps: the init run with each field, then the compare at both
    # sites with a length under, at and over the cap
    fields = {row['addresses']['IPSLOT']: (0x12, 47), row['addresses']['TEAMSLOT']: (0x12, 35),
              row['addresses']['LINEBUF']: (0x1a, 255), row['addresses']['LINEBUF'] + 1: (0x12, 0x800), 0x1234: (0x12, 0x800)}
    fields[row['addresses']['LINEBUF']] = (0x1a, 255)
    cases = [(field, width, cap) for field, (width, cap) in fields.items()] + [(row['addresses']['LINEBUF'], 0x12, 20)]
    stops = (init + 8, first + 5, second + 5)
    for field, width, cap in cases:
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<6I', 0, 0x1111, 0x2222, 0x3333, field, width))    # a return slot, then the init's arguments
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(init, 0, count=200)
        assert mu.reg_read(UC_X86_REG_EIP) == init + 8, 'init for %#x stopped at 0x%x' % (field, mu.reg_read(UC_X86_REG_EIP))
        assert mu.reg_read(UC_X86_REG_ESP) == esp, 'init for %#x: stack' % field
        assert (mu.reg_read(UC_X86_REG_EAX), mu.reg_read(UC_X86_REG_ECX)) == (0x1111, 0x2222), 'init for %#x: the loads' % field
        for site in (first, second):
            for length, over in ((cap - 1, False), (cap, True), (cap + 1, True)):
                mu.reg_write(UC_X86_REG_ESP, esp)
                mu.reg_write(UC_X86_REG_EAX, length)
                mu.reg_write(UC_X86_REG_EBX, 0x4444)
                mu.emu_start(site, 0, count=100)
                assert mu.reg_read(UC_X86_REG_EIP) == site + 5 and mu.reg_read(UC_X86_REG_EBX) == 0x4444
                assert bool(mu.reg_read(UC_X86_REG_EFLAGS) & CF) != over, 'field %#x: %d against a cap of %d' % (field, length, cap)
    print('ipchecktest: %s: %d addresses accepted, %d entries refused with the cancel sound; %d fields capped'
          % (build, len(ACCEPTED), len(REFUSED), len(cases)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
