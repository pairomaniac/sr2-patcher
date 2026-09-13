#!/usr/bin/env python3
"""Run the texture-release check under Unicorn.

    python3 tools/texrangetest.py

TEXRANGE_BLOB is mapped as the patcher would place it. An index below
the count must fall through to the function's eleventh byte with what
the replaced ten left: eax the table, esi the index, esi pushed. One at
or above it, including VendorLogo's -128, must return with the stack as
a stdcall leaves it and nothing else touched. Needs python3-unicorn;
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
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EIP
except ImportError:
    print('texrangetest: skipped, python3-unicorn not installed')
    sys.exit(0)

BASE, SELF, IMAGE = 0x02ba0000, 0x16000, 0x20000     # a relocated load, as Windows did
STACK, RETURN, TABLE_AT = 0x30000000, 0xdead0000, 0x01230000
TABLE, COUNT, RESUME = 0x12580, 0x12590, 0x443a


def run(index, count=120):
    blob = patcher.TEXRANGE_BLOB.replace(struct.pack('<I', patcher.FULLWIN_MAGIC), struct.pack('<I', SELF))
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(BASE, IMAGE)
    mu.mem_map(STACK, 0x10000)
    mu.mem_write(BASE + SELF, blob)
    mu.mem_write(BASE + TABLE, struct.pack('<I', TABLE_AT))
    mu.mem_write(BASE + COUNT, struct.pack('<I', count))
    mu.mem_write(BASE + RESUME, b'\xf4')            # hlt: where the function goes on
    esp = STACK + 0x8000
    mu.mem_write(esp, struct.pack('<Ii', RETURN, index))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.reg_write(UC_X86_REG_ESI, 0x51515151)
    mu.reg_write(UC_X86_REG_EAX, 0x41414141)
    mu.emu_start(BASE + SELF, RETURN, count=100)   # stops at RETURN or on the hlt
    return mu


def main(argv):
    mu = run(7)
    assert mu.reg_read(UC_X86_REG_EIP) in (BASE + RESUME, BASE + RESUME + 1), 'in range: did not go on, eip %x' % mu.reg_read(UC_X86_REG_EIP)
    assert mu.reg_read(UC_X86_REG_EAX) == TABLE_AT and mu.reg_read(UC_X86_REG_ESI) == 7
    esp = mu.reg_read(UC_X86_REG_ESP)
    assert struct.unpack('<II', mu.mem_read(esp, 8)) == (0x51515151, RETURN), 'esi pushed over the return'
    for index in (120, 121, -128, -1):
        mu = run(index)
        assert mu.reg_read(UC_X86_REG_EIP) == RETURN, 'out of range %d: did not return' % index
        assert mu.reg_read(UC_X86_REG_ESP) == STACK + 0x8000 + 8, 'ret 4'
        assert mu.reg_read(UC_X86_REG_EAX) == 0 and mu.reg_read(UC_X86_REG_ESI) == 0x51515151
    mu = run(0, count=0)
    assert mu.reg_read(UC_X86_REG_EIP) == RETURN, 'no textures: every index is out of range'
    print('texrangetest OK: in range goes on, -128 and past the count return')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
