#!/usr/bin/env python3
"""Run the replay gallery's two thunks under Unicorn.

    python3 tools/replayfreetest.py

REPLAYFREE_BLOB is mapped as the patcher would place it, with the CRT's
new and free replaced by recording stubs at their RVAs. `alloc` must
call new with the caller's size, hand its block back and keep the stack
as a cdecl new does; `free` must free that block and no other, and leave
the pointer pushed for the caller's `add esp, 4`. Needs python3-unicorn;
exits 0 with a note when it is missing.
"""
import importlib.util
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('patcher', os.path.join(HERE, '..', 'sr2-patcher.py'))
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESP
except ImportError:
    print('replayfreetest: skipped, python3-unicorn not installed')
    sys.exit(0)

BASE, SELF, IMAGE = 0x00a40000, 0x160000, 0x170000       # a relocated load, as Windows did
STACK, RETURN = 0x30000000, 0xdead0000
NEW, FREE, BLOCK = 0xbdeb, 0xbde0, 0x00c30000


def machine():
    blob = patcher.REPLAYFREE_BLOB.replace(struct.pack('<I', patcher.FULLWIN_MAGIC), struct.pack('<I', SELF))
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(BASE, IMAGE)
    mu.mem_map(STACK, 0x10000)
    mu.mem_write(BASE + SELF, blob)
    mu.mem_write(BASE + NEW, b'\xc3')                    # cdecl: the caller drops the argument
    mu.mem_write(BASE + FREE, b'\xc3')
    calls = []

    def stub(mu_, address, size_, user):
        esp = mu_.reg_read(UC_X86_REG_ESP)
        arg = struct.unpack('<I', mu_.mem_read(esp + 4, 4))[0]
        if address == BASE + NEW:
            calls.append(('new', arg))
            mu_.reg_write(UC_X86_REG_EAX, BLOCK)
        elif address == BASE + FREE:
            calls.append(('free', arg))
    mu.hook_add(UC_HOOK_CODE, stub, begin=BASE + FREE, end=BASE + NEW + 1)
    return mu, calls


def main(argv):
    mu, calls = machine()
    # alloc, as `call` at 0x3b65 with the size pushed
    esp = STACK + 0x8000
    mu.mem_write(esp, struct.pack('<II', RETURN, 0x1234))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.emu_start(BASE + SELF, RETURN, count=100)
    assert calls == [('new', 0x1234)] and mu.reg_read(UC_X86_REG_EAX) == BLOCK, calls
    assert mu.reg_read(UC_X86_REG_ESP) == esp + 4, 'cdecl: the size still on the stack'
    # free of another pointer: nothing freed, the pointer pushed for the add esp, 4
    del calls[:]
    esp = STACK + 0x8000
    mu.mem_write(esp, struct.pack('<I', RETURN))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.reg_write(UC_X86_REG_EAX, 0x0d7062b8)             # MainMode's replay
    mu.emu_start(BASE + SELF + 5, RETURN, count=100)
    assert calls == [] and mu.reg_read(UC_X86_REG_ESP) == esp
    assert struct.unpack('<I', mu.mem_read(esp, 4))[0] == 0x0d7062b8, 'the argument left as pushed'
    # free of the gallery's own: freed, once
    for expect in ([('free', BLOCK)], []):
        del calls[:]
        mu.mem_write(esp, struct.pack('<I', RETURN))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EAX, BLOCK)
        mu.emu_start(BASE + SELF + 5, RETURN, count=100)
        assert calls == expect and mu.reg_read(UC_X86_REG_ESP) == esp, calls
    print('replayfreetest OK: new kept, its block freed once, another pointer left alone')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
