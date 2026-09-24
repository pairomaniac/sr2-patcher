#!/usr/bin/env python3
"""The pad on the multiplayer screens under Unicorn.

    python3 tools/padmenutest.py

padmenu.asm's entry with the European build's addresses in place, called
as the poll's site is: ecx the level packed so far, edx the edge the exe
made from it and the previous level, the return address the site's. It
asks the poll slot's routine for side 0's twelve inputs with the stdcall
frame the annex's page poll expects, puts A, B and Start into the level
as their bits and takes the wrapper's directions out of it, makes the
edge again against the stored previous level, stores level, edge and
previous, returns thirteen bytes past the site, and in the keyboard word sets the directions as pulses - on a
change, then every PERIOD frames once DELAY frames held - bit 31 on any
press and bit 13 on a press of Back. Nothing is asked with the slot
empty. The registers come back as they were.

Needs python3-unicorn; exits 77 with a note when it is missing.
"""
import struct

from uctest import patcher
import uctest

uctest.unicorn('padmenutest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_EDI

CODE, STUBS, STACK = 0x900000, 0xa00000, 0xb00000
ROW = patcher.BUILDS['European']
A = ROW['addresses']
LEVEL, EDGE, PREV, KEYS, SLOT = A['PADLEVEL'], A['PADEDGE'], A['PADPREV'], A['MENUKEYS'], A['PADPOLL']
UP, DOWN, LEFT, RIGHT, START, BACK, LS_LEFT, LS_RIGHT, LS_UP, LS_DOWN, BTN_A, BTN_B = 0, 1, 2, 3, 4, 5, 18, 19, 20, 21, 12, 13


def main():
    blob = patcher.exe_blob(patcher.PADMENU_BLOB, 'European')
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr in (CODE, STUBS, STACK):
        mu.mem_map(addr, 0x10000)
    for addr in (LEVEL, EDGE, PREV, KEYS, SLOT):
        try:
            mu.mem_map(addr & ~0xfff, 0x1000)
        except Exception:
            pass
    mu.mem_write(CODE, blob)
    mu.mem_write(STUBS, b'\xc2\x0c\x00')      # the poll: what it answers happens in the hook
    state = {'down': {}, 'calls': []}

    def poll(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        source, value, rng = struct.unpack('<III', mu.mem_read(esp + 4, 12))
        state['calls'].append(source)
        v = state['down'].get(source - 0x300, 0)
        full = 10000 if source - 0x300 >= 16 else 0x80
        mu.mem_write(value, struct.pack('<I', v))
        mu.mem_write(rng, struct.pack('<I', full))
        mu.reg_write(UC_X86_REG_EAX, 0)
    mu.hook_add(UC_HOOK_CODE, poll, begin=STUBS, end=STUBS + 1)

    def frame(down, level=0, prev=None, slot=STUBS):
        state['down'] = down
        mu.mem_write(SLOT, struct.pack('<I', slot))
        if prev is None:
            prev = struct.unpack('<I', mu.mem_read(PREV, 4))[0]
        else:
            mu.mem_write(PREV, struct.pack('<I', prev))
        for addr in (LEVEL, EDGE):
            mu.mem_write(addr, b'\0' * 4)
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<I', CODE + len(blob) - 13))    # the site's return: +13 is the end
        mu.reg_write(UC_X86_REG_ESP, esp)
        regs = {UC_X86_REG_EAX: 0x11111111, UC_X86_REG_ESI: 0x22222222, UC_X86_REG_EDI: 0x33333333, UC_X86_REG_EBP: 0x44444444}
        for r, v in regs.items():
            mu.reg_write(r, v)
        mu.reg_write(UC_X86_REG_ECX, level)
        mu.reg_write(UC_X86_REG_EDX, ~prev & level & 0xffffffff)   # the edge, as the site's `not edx; and edx, ecx` left it
        mu.emu_start(CODE, CODE + len(blob), timeout=2000000)
        assert mu.reg_read(UC_X86_REG_ESP) == esp + 4, 'the stack came back wrong'
        for r, v in regs.items():
            assert mu.reg_read(r) == v, 'a register came back changed'
        got = [struct.unpack('<I', mu.mem_read(a, 4))[0] for a in (LEVEL, EDGE, PREV, KEYS)]
        assert got[0] == got[2], 'the previous level is not the level'
        assert got[1] == ~prev & got[0] & 0xffffffff, 'the edge is not down-now-not-before'
        return got[0], got[1], got[3]

    DELAY, PERIOD, ANY, TAB = 30, 2, 0x80000000, 0x2000

    def clear():
        mu.mem_write(KEYS, b'\0' * 4)                                 # the tasks clear the word once read

    def rest():
        frame({})
        clear()

    clear()
    mu.mem_write(PREV, b'\0' * 4)
    assert frame({}) == (0, 0, 0), 'bits with nothing pressed'
    assert frame({UP: 0x80}) == (0, 0, ANY | 1), 'D-pad up: a pulse in the keyboard word, any key'
    clear()
    for i in range(DELAY - 1):
        assert frame({UP: 0x80}) == (0, 0, 0), 'up held: a pulse before the delay, frame %d' % i
    assert frame({UP: 0x80}) == (0, 0, 1), 'up held: no pulse after the delay'
    clear()
    for i in range(PERIOD - 1):
        assert frame({UP: 0x80}) == (0, 0, 0), 'up held: a pulse before the period, frame %d' % i
    assert frame({UP: 0x80}) == (0, 0, 1), 'up held: no pulse after the period'
    assert frame({UP: 0x80}) == (0, 0, 1), 'the pulse not left waiting in the word'
    clear()
    assert frame({UP: 0x80, RIGHT: 0x80}) == (0, 0, ANY | 9), 'a change while held: no pulse'
    clear()
    assert frame({}) == (0, 0, 0), 'a release: a pulse'
    assert frame({DOWN: 0x80, LEFT: 0x80}) == (0, 0, ANY | 6), 'down, left'
    rest()
    assert frame({LS_UP: 10000, LS_LEFT: 5001}) == (0, 0, ANY | 5), 'the stick past half'
    rest()
    assert frame({LS_DOWN: 5000, LS_RIGHT: 4999}) == (0, 0, 0), 'the stick at half or under'
    assert frame({BTN_A: 0x80, BTN_B: 0x80, START: 0x80}) == (0x8030, 0x8030, ANY), 'A, B, Start'
    clear()
    assert frame({BTN_A: 0x80, BTN_B: 0x80, START: 0x80}) == (0x8030, 0, 0), 'buttons held: an edge again, or any key again'
    clear()
    assert frame({BTN_A: 0x80}, level=0x10, prev=0x8030) == (0x10, 0, 0), 'A held through the wrapper too: an edge'
    assert frame({}, level=0, prev=0x10) == (0, 0, 0), 'a release: an edge'
    assert frame({BTN_A: 0x80}, level=0x10, prev=0) == (0x10, 0x10, ANY), 'a press through both: one edge'
    rest()
    assert frame({}, level=0x8010, prev=0x8010) == (0x8010, 0, 0), 'the wrapper\'s button bits lost'
    assert frame({}, level=0xf, prev=0) == (0, 0, 0), 'the wrapper\'s direction bits kept'
    assert frame({UP: 0x80}, level=0x1f, prev=0x10) == (0x10, 0, ANY | 1), 'the pad\'s pulse beside the wrapper\'s'
    rest()
    assert frame({BACK: 0x80}) == (0, 0, ANY | TAB), 'no TAB on a press of Back'
    clear()
    assert frame({BACK: 0x80}) == (0, 0, 0), 'TAB again while held'
    assert frame({}) == (0, 0, 0), 'TAB on the release'
    mu.mem_write(KEYS, struct.pack('<I', 0x8000))
    assert frame({BACK: 0x80}) == (0, 0, 0x8000 | ANY | TAB), 'the keyboard word\'s other bits lost'
    assert sorted(set(state['calls'])) == sorted(0x300 + i for i in (0, 1, 2, 3, 4, 5, 12, 13, 18, 19, 20, 21)), 'the wrong sources asked for'
    n = len(state['calls'])
    clear()
    assert frame({UP: 0x80, BACK: 0x80}, level=3, prev=1, slot=0) == (3, 2, 0) and len(state['calls']) == n, 'the empty slot: not the site\'s own stores'
    print('padmenutest: OK')


if __name__ == '__main__':
    main()
