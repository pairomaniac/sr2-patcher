#!/usr/bin/env python3
"""The pad's bumpers as Page Up and Page Down under Unicorn.

    python3 tools/pagepadtest.py

pagepad.asm's entry with each build's addresses in place, called as the
input wrapper's update calls it: esi the player's slot, its level word
0xa0 below, the player and the config on the caller's stack. Checked: LB
and RB past half set 0x80 and 0x100 on the player's own side's sources
and nothing else; the level's other bits kept; eax the config and the
zero flag its test, as the site's branch needs; nothing asked with the
poll's slot empty; the registers but eax as they were.

Needs python3-unicorn; exits 77 with a note when it is missing.
"""
import struct

from uctest import patcher
import uctest

uctest.unicorn('pagepadtest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP,
                               UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EFLAGS)

CODE, STUBS, STACK, WRAP = 0x900000, 0xa00000, 0xb00000, 0xc00000
LB, RB, BTN_A = 8, 9, 12
ZF = 0x40


def run(build):
    blob = patcher.exe_blob(patcher.PAGEPAD_BLOB, build)
    slot = patcher.BUILDS[build]['addresses']['PADPOLL']
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr in (CODE, STUBS, STACK, WRAP, slot & ~0xfff):
        mu.mem_map(addr, 0x10000 if addr != slot & ~0xfff else 0x1000)
    mu.mem_write(CODE, blob)
    mu.mem_write(STUBS, b'\xc2\x0c\x00')
    state = {'down': {}, 'calls': []}

    def poll(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        source, value, rng = struct.unpack('<III', mu.mem_read(esp + 4, 12))
        state['calls'].append(source)
        mu.mem_write(value, struct.pack('<I', state['down'].get(source, 0)))
        mu.mem_write(rng, struct.pack('<I', 0x80))
        mu.reg_write(UC_X86_REG_EAX, 0x5a5a5a5a)
    mu.hook_add(UC_HOOK_CODE, poll, begin=STUBS, end=STUBS + 1)

    def call(player, down=None, level=0, config=0x1234, polled=True):
        state['down'] = down or {}
        mu.mem_write(slot, struct.pack('<I', STUBS if polled else 0))
        esi = WRAP + 0xd4 + player * 4
        mu.mem_write(esi - 0xa0, struct.pack('<I', level))
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<I', CODE + len(blob)))          # returns to the blob's end
        mu.mem_write(esp + 4 + 0x10, struct.pack('<I', config))
        mu.mem_write(esp + 4 + 0x18, struct.pack('<I', player))
        regs = {UC_X86_REG_EBX: 0x11111111, UC_X86_REG_ECX: 0x22222222, UC_X86_REG_EDX: 0x33333333,
                UC_X86_REG_EBP: 0, UC_X86_REG_ESI: esi, UC_X86_REG_EDI: 0x44444444}
        for r, v in regs.items():
            mu.reg_write(r, v)
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(CODE, CODE + len(blob), timeout=2000000)
        assert mu.reg_read(UC_X86_REG_ESP) == esp + 4, 'the stack came back wrong'
        for r, v in regs.items():
            assert mu.reg_read(r) == v, 'a register came back changed'
        assert mu.reg_read(UC_X86_REG_EAX) == config, 'eax is not the config'
        assert bool(mu.reg_read(UC_X86_REG_EFLAGS) & ZF) == (config == 0), 'the zero flag is not the config\'s test'
        return struct.unpack('<I', mu.mem_read(esi - 0xa0, 4))[0]

    side = lambda player, i: 0x300 + player * 0x40 + i
    assert call(0) == 0, 'bits with nothing pressed'
    assert sorted(state['calls']) == [side(0, LB), side(0, RB)], 'the wrong sources asked for'
    assert call(0, {side(0, LB): 0x80}) == 0x80, 'LB as Page Up'
    assert call(0, {side(0, RB): 0x80}) == 0x100, 'RB as Page Down'
    assert call(0, {side(0, LB): 0x80, side(0, RB): 0x80}, level=0x1041) == 0x11c1, 'the level\'s own bits lost'
    assert call(0, {side(0, LB): 0x40, side(0, BTN_A): 0x80}) == 0, 'LB at half, or another input, taken'
    assert call(1, {side(0, LB): 0x80, side(1, RB): 0x80}) == 0x100, 'player 2 not on side 1'
    assert call(0, {side(0, LB): 0x80}, config=0) == 0x80, 'the config 0'
    n = len(state['calls'])
    assert call(0, {side(0, LB): 0x80}, level=4, polled=False) == 4 and len(state['calls']) == n, 'asked with the slot empty'
    print('pagepad: LB and RB as Page Up and Page Down, %s' % build.lower())


def main():
    for build in patcher.BUILDS:
        run(build)


if __name__ == '__main__':
    main()
