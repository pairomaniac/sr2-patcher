#!/usr/bin/env python3
"""The pad's LB and RB on the Replay Gallery's sort, under Unicorn.

    python3 tools/sortpadtest.py GAMEDIR

The real ReplayGallery.dll with replayfree and sortpad applied, mapped
at a base other than its own with the relocations applied as the loader
would, run from the site to the instruction after it, frame by frame,
with the sort block's global set and the exe's poll slot pointing at a
stub that answers side 0's inputs from a table. Checked: a press of LB
steps the mode left and RB right, round at both ends; held, nothing
more; both pressed at once, LB; other inputs and side 1's ignored; the
order never touched; the site's two instructions made as before; an
empty poll slot or no sort block passed over.

Needs python3-unicorn; exits 77 with a note when missing.
"""
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('sortpadtest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP,
                               UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_EDI)

BASE = 0x20000000                       # not the DLL's own, so a missed relocation shows
HEAP, STACK, STUBS = 0x3000000, 0x3100000, 0x3200000
BLOCK, LIST = HEAP + 0x100, HEAP + 0x200
SORTBLOCK_RVA = 0xbe620
LB, RB, BTN_A = 0x308, 0x309, 0x30c


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    build = patcher.check_build(argv[1])
    buf = uctest.stock(argv[1], 'ReplayGallery.dll')
    out = patcher.apply_sortpad(patcher.apply_replayfree(buf, build), build)
    slot = patcher.BUILDS[build]['addresses']['PADPOLL']
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    uctest.map_image(mu, out, BASE)
    for addr in (HEAP, STACK, STUBS):
        mu.mem_map(addr, 0x10000)
    mu.mem_map(slot & ~0xfff, 0x1000)
    site = BASE + 0x1000 + patcher.SORTPAD_SITE - patcher._rva_to_off(out, 0x1000)
    w = lambda a, v: mu.mem_write(a, struct.pack('<I', v & 0xffffffff))
    r = lambda a: struct.unpack('<I', mu.mem_read(a, 4))[0]

    mu.mem_write(STUBS, b'\xc2\x0c\x00')         # the page poll: stdcall (source, &value, &range)
    state = {'down': {}, 'calls': []}

    def poll(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        source, value, rng = struct.unpack('<III', mu.mem_read(esp + 4, 12))
        state['calls'].append(source)
        w(value, state['down'].get(source, 0))
        w(rng, 0x80)
        mu.reg_write(UC_X86_REG_EAX, 0x5a5a5a5a)
    mu.hook_add(UC_HOOK_CODE, poll, begin=STUBS, end=STUBS + 1)

    def frame(mode, down=(), order=7, polled=True, block=BLOCK):
        state['down'] = {s: 0x80 for s in down}
        w(slot, STUBS if polled else 0)
        w(BASE + SORTBLOCK_RVA, block)
        w(BLOCK + 4, mode)
        w(BLOCK + 8, order)
        w(LIST + 0x50, 0x5a)
        regs = {UC_X86_REG_EAX: 0x11111111, UC_X86_REG_EBX: 0x22222222, UC_X86_REG_EDX: 0x33333333,
                UC_X86_REG_EBP: 0x44444444, UC_X86_REG_ESI: LIST}
        for reg, v in regs.items():
            mu.reg_write(reg, v)
        mu.reg_write(UC_X86_REG_EDI, 0x12345)
        mu.reg_write(UC_X86_REG_ECX, 0x55555555)
        esp = STACK + 0x8000
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(site, site + 9, timeout=2000000)
        assert mu.reg_read(UC_X86_REG_ESP) == esp, 'the stack came back wrong'
        for reg, v in regs.items():
            assert mu.reg_read(reg) == v, 'a register came back changed'
        assert mu.reg_read(UC_X86_REG_ECX) == 0x5a and mu.reg_read(UC_X86_REG_EDI) == 0x45, 'the site\'s own two not made'
        assert r(BLOCK + 8) == order, 'the order changed'
        return r(BLOCK + 4)

    assert frame(1) == 1, 'nothing pressed'
    assert sorted(set(state['calls'])) == [LB, RB], 'the wrong sources asked for'
    assert frame(1, [LB]) == 0, 'LB from CAR'
    assert frame(1, [LB]) == 1, 'LB held: a step again'
    assert frame(1) == 1
    assert frame(0, [LB]) == 2, 'LB from MODE, round to DATE'
    assert frame(1) == 1
    assert frame(1, [RB]) == 2, 'RB from CAR'
    assert frame(1) == 1
    assert frame(2, [RB]) == 0, 'RB from DATE, round to MODE'
    assert frame(1) == 1
    assert frame(1, [LB, RB]) == 0, 'both: LB'
    assert frame(1) == 1
    assert frame(1, [BTN_A, 0x348, 0x349]) == 1, 'another input, or side 1, taken'
    n = len(state['calls'])
    assert frame(1, [LB], polled=False) == 1 and len(state['calls']) == n, 'asked with the slot empty'
    assert frame(1, [RB], block=0) == 1, 'no sort block'
    print('sortpad: LB and RB step the gallery\'s sort, %s' % build.lower())
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
