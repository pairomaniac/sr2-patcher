#!/usr/bin/env python3
"""The HUD drawn after the tree under Unicorn.

    python3 tools/hudlasttest.py

hudlast.asm's three entries, with the European and then the Australian
build's addresses in place (the latter has no flag). The state's entry
draws the HUD there when the tree is not going to run - the flag set or
the game not running - and otherwise draws nothing and leaves the HUD
pending. The fade entry draws a pending HUD - the full viewport, the
HUD, the reset - before the fade; the late entry draws the tree and
then a HUD still pending, once. The exe's routines are stubs that note
the call and the registers.

Needs python3-unicorn; exits 77 with a note when it is missing.
"""
import struct

from uctest import patcher
import uctest

uctest.unicorn('hudlasttest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESI, UC_X86_REG_ESP

CODE, STACK, FRAME, RENDER = 0x900000, 0xb00000, 0x1234560, 0x2345670


def check(build):
    A = patcher.BUILDS[build]['addresses']
    STUBS = {A['HUDDRAW']: ('hud', 0), A['TREEDRAW']: ('tree', 0), A['HUDRESET']: ('reset', 0), A['SETVIEWPORT']: ('viewport', 8),
             A['FADEDRAW']: ('fade', 0)}
    blob = patcher.exe_blob(patcher.HUDLAST_BLOB, build)
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr in (CODE, STACK):
        mu.mem_map(addr, 0x10000)
    for addr in list(STUBS) + [A['RUNNING'], A['LATEFLAG'] or A['RUNNING'], A['RENDERER']]:
        try:
            mu.mem_map(addr & ~0xfff, 0x1000)
        except Exception:
            pass
    mu.mem_write(CODE, blob)
    for addr, (_name, argc) in STUBS.items():
        mu.mem_write(addr, b'\xc2' + struct.pack('<H', argc) if argc else b'\xc3')
    mu.mem_write(A['RENDERER'], struct.pack('<I', RENDER))
    calls = []

    def stub(mu, addr, size, user):
        if addr in STUBS:
            esp = mu.reg_read(UC_X86_REG_ESP)
            calls.append((STUBS[addr][0], mu.reg_read(UC_X86_REG_ECX), mu.reg_read(UC_X86_REG_ESI),
                          struct.unpack('<II', mu.mem_read(esp + 4, 8)) if STUBS[addr][1] else ()))
    for addr in STUBS:
        mu.hook_add(UC_HOOK_CODE, stub, begin=addr, end=addr + 1)

    def run(entry, running, flag):
        mu.mem_write(A['RUNNING'], struct.pack('<I', running))
        if A['LATEFLAG']:
            mu.mem_write(A['LATEFLAG'], struct.pack('<I', flag))
        del calls[:]
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<I', CODE + len(blob)))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_ESI, FRAME)
        mu.reg_write(UC_X86_REG_ECX, 0x77)
        mu.emu_start(CODE + entry, CODE + len(blob), timeout=2000000)
        if mu.reg_read(UC_X86_REG_ESP) != esp + 4:
            raise SystemExit('hudlasttest: the stack came back at %x, not %x' % (mu.reg_read(UC_X86_REG_ESP), esp + 4))
        return [c[0] for c in calls]

    # the state's entry: the HUD there when the tree is not going to run
    for running, flag in ((0, 0), (0, 1), (1, 1))[:3 if A['LATEFLAG'] else 1]:
        if run(0, running, flag) != ['hud'] or run(5, running, flag) != ['tree']:
            raise SystemExit('hudlasttest: running %d, flag %d: the HUD was not drawn in the state' % (running, flag))
    # the tree going to run: nothing there, then tree, viewport, HUD, reset after it
    if run(0, 1, 0) != []:
        raise SystemExit('hudlasttest: the state drew with the tree to come')
    if run(5, 1, 0) != ['tree', 'viewport', 'hud', 'reset']:
        raise SystemExit('hudlasttest: the late entry made %r' % (calls,))
    if calls[1][1:] != (RENDER, FRAME, (A['VPRECTS'], 0)) or calls[3][1:3] != (RENDER, FRAME):
        raise SystemExit('hudlasttest: the viewport or reset was called wrong: %r' % (calls,))
    # once: the next late entry draws the tree alone
    if run(5, 1, 0) != ['tree']:
        raise SystemExit('hudlasttest: the HUD was drawn again')
    # the fade entry: the HUD pending is drawn before the fade, then the late entry has nothing left
    run(0, 1, 0)
    if run(10, 1, 0) != ['viewport', 'hud', 'reset', 'fade'] or calls[3][1] != RENDER:
        raise SystemExit('hudlasttest: the fade entry made %r' % (calls,))
    if run(5, 1, 0) != ['tree'] or run(10, 1, 0) != ['fade']:
        raise SystemExit('hudlasttest: the HUD was drawn again after the fade')
    # a state draw that drew the HUD itself leaves nothing pending
    run(0, 1, 0)
    run(0, 0, 0)
    if run(5, 1, 0) != ['tree']:
        raise SystemExit('hudlasttest: a HUD drawn in the state was still pending')


def main():
    for build in ('European', 'Australian'):
        check(build)
    print('hudlasttest: the HUD after the tree when it runs, in the state otherwise OK')


if __name__ == '__main__':
    main()
