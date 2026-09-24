#!/usr/bin/env python3
"""The stage loading screens' hold under Unicorn.

    python3 tools/loadholdtest.py

loadhold.asm's two entries, with the European build's addresses in
place: the create's entry makes the store the site made and notes the
tick; the step's entry sleeps until HOLD milliseconds have passed since
it, then makes the load the site made, with eax and edx as they were.
The clock and Sleep are stubs, the clock advancing by what Sleep is
asked for. A step with no create before it does not wait.

Needs python3-unicorn; exits 77 with a note when it is missing.
"""
import struct

from uctest import patcher
import uctest

uctest.unicorn('loadholdtest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP

CODE, STUBS, STACK, OBJ = 0x900000, 0xa00000, 0xb00000, 0x1234560
HOLD, NAP = 3000, 10
ROW = patcher.BUILDS['European']
PICTURE, TICK, LOADLIB, GETPROC = ROW['addresses']['LOADPIC'], ROW['slots']['GetTickCount'], ROW['slots']['LoadLibraryA'], ROW['slots']['GetProcAddress']


def main():
    blob = patcher.exe_blob(patcher.LOADHOLD_BLOB, 'European')
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr in (CODE, STUBS, STACK):
        mu.mem_map(addr, 0x10000)
    for slot in (PICTURE, TICK, LOADLIB, GETPROC):
        try:
            mu.mem_map(slot & ~0xfff, 0x1000)
        except Exception:
            pass
    mu.mem_write(CODE, blob)
    # the stubs: GetTickCount at STUBS (ret), LoadLibraryA at +0x10 (ret 4), GetProcAddress at +0x20 (ret 8),
    # Sleep at +0x30 (ret 4); what they do happens in the hook
    mu.mem_write(STUBS, b'\xc3')
    mu.mem_write(STUBS + 0x10, b'\xc2\x04\x00')
    mu.mem_write(STUBS + 0x20, b'\xc2\x08\x00')
    mu.mem_write(STUBS + 0x30, b'\xc2\x04\x00')
    mu.mem_write(TICK, struct.pack('<I', STUBS))
    mu.mem_write(LOADLIB, struct.pack('<I', STUBS + 0x10))
    mu.mem_write(GETPROC, struct.pack('<I', STUBS + 0x20))
    state = {'tick': 1000000, 'sleeps': [], 'procs': []}

    def stub(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        if addr == STUBS:
            mu.reg_write(UC_X86_REG_EAX, state['tick'])
        elif addr == STUBS + 0x10:
            mu.reg_write(UC_X86_REG_EAX, 0x7c800000)
        elif addr == STUBS + 0x20:
            module, name = struct.unpack('<II', mu.mem_read(esp + 4, 8))
            state['procs'].append((module, bytes(mu.mem_read(name, 8)).split(b'\0')[0].decode()))
            mu.reg_write(UC_X86_REG_EAX, STUBS + 0x30)
        elif addr == STUBS + 0x30:
            ms = struct.unpack('<I', mu.mem_read(esp + 4, 4))[0]
            state['sleeps'].append(ms)
            state['tick'] += ms
    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x31)

    def run(entry, eax, ecx, edx):
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<I', CODE + len(blob)))     # the return, past the blob
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EAX, eax)
        mu.reg_write(UC_X86_REG_ECX, ecx)
        mu.reg_write(UC_X86_REG_EDX, edx)
        mu.emu_start(CODE + entry, CODE + len(blob), timeout=2000000)
        if mu.reg_read(UC_X86_REG_ESP) != esp + 4:
            raise SystemExit('loadholdtest: the stack came back at %x, not %x' % (mu.reg_read(UC_X86_REG_ESP), esp + 4))
        return tuple(mu.reg_read(r) for r in (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX))

    # the create: the store made, the tick noted, the registers as they were
    regs = run(0, 0x11, OBJ, 0x22)
    if regs != (0x11, OBJ, 0x22) or struct.unpack('<I', mu.mem_read(PICTURE, 4))[0] != OBJ:
        raise SystemExit('loadholdtest: the create came out %r, the object %x' % (regs, struct.unpack('<I', mu.mem_read(PICTURE, 4))[0]))
    # the step, a second later: sleeps until the hold is out, then the load, eax and edx kept
    state['tick'] += 1000
    regs = run(5, 0x33, 0, 0x44)
    if regs != (0x33, OBJ, 0x44):
        raise SystemExit('loadholdtest: the step came out %r' % (regs,))
    if state['procs'] != [(0x7c800000, 'Sleep')]:
        raise SystemExit('loadholdtest: Sleep was resolved wrong: %r' % (state['procs'],))
    if set(state['sleeps']) != {NAP} or not (HOLD - 1000) // NAP <= len(state['sleeps']) <= (HOLD - 1000) // NAP + 1:
        raise SystemExit('loadholdtest: %d sleeps of %r, for a hold of %d with %d gone' % (len(state['sleeps']), set(state['sleeps']), HOLD, 1000))
    # the step again with no create before it: the load, no wait
    del state['sleeps'][:]
    regs = run(5, 0x55, 0, 0x66)
    if regs != (0x55, OBJ, 0x66) or state['sleeps']:
        raise SystemExit('loadholdtest: a step without a create waited: %r %r' % (regs, state['sleeps']))
    # a create and a step with the hold already out: no wait, Sleep not looked up again
    run(0, 0, OBJ, 0)
    state['tick'] += HOLD + 1
    run(5, 0, 0, 0)
    if state['sleeps'] or len(state['procs']) != 1:
        raise SystemExit('loadholdtest: a step past the hold waited, or Sleep was looked up again')
    print('loadholdtest: the create notes the tick, the step waits the hold out and the load is made OK')


if __name__ == '__main__':
    main()
