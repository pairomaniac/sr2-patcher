#!/usr/bin/env python3
"""Run the .bg row copies of the windowed and title patches under Unicorn.

    python3 tools/bgrowtest.py

BGROW_BLOB and TITLEROW_BLOB are called with a row of 565 pixels as the
game calls the copies they replace: eax the row's byte count, ebx the
source, edx the destination. With the lock description saying 16 bits the
row must come out byte for byte; with 32 it must come out as XRGB8888
with the low bits replicated; eax and edx must survive, and ebx too for
the exe's, advanced by a row for Title.dll's, which reads the depth from
the stack rather than the exe's global. Needs python3-unicorn; exits 0
with a note when it is missing.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('patcher', os.path.join(HERE, '..', 'sr2-patcher.py'))
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EDX,
                                   UC_X86_REG_ESP)
except ImportError:
    print('bgrowtest: skipped, python3-unicorn not installed')
    sys.exit(0)

CODE, DESC, SRC, DST, STACK = 0x400000, 0x4e6000, 0x1000000, 0x1008000, 0x3000000
BITCOUNT = 0x4e68cc
PIXELS = (0x0000, 0xffff, 0xf800, 0x07e0, 0x001f, 0x8410, 0x1234)


def expand(p):
    r, g, b = (p >> 11) & 0x1f, (p >> 5) & 0x3f, p & 0x1f
    return ((r << 3 | r >> 2) << 16) | ((g << 2 | g >> 4) << 8) | (b << 3 | b >> 2)


def run(bpp, title=False):
    blob = patcher.TITLEROW_BLOB if title else patcher.BGROW_BLOB
    src = b''.join(p.to_bytes(2, 'little') for p in PIXELS)
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr in (CODE, DESC):
        mu.mem_map(addr, 0x1000)
    mu.mem_map(SRC, 0x10000)
    mu.mem_map(STACK, 0x10000)
    mu.mem_write(CODE, blob)
    mu.mem_write(BITCOUNT, bpp.to_bytes(4, 'little'))
    mu.mem_write(STACK + 0x8000 + 0x70, bpp.to_bytes(4, 'little'))    # Title.dll's, past the return
    mu.mem_write(SRC, src)
    end = CODE + len(blob)
    mu.mem_write(STACK + 0x8000, end.to_bytes(4, 'little'))
    mu.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
    mu.reg_write(UC_X86_REG_EAX, len(src))
    mu.reg_write(UC_X86_REG_EBX, SRC)
    mu.reg_write(UC_X86_REG_EDX, DST)
    mu.emu_start(CODE, end)
    regs = tuple(mu.reg_read(r) for r in (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EDX))
    if regs != (len(src), SRC + (len(src) if title else 0), DST):
        raise SystemExit('bgrowtest: registers wrong at %d bpp%s: %r'
                         % (bpp, ', title' if title else '', regs))
    width = 4 if bpp == 32 else 2
    out = bytes(mu.mem_read(DST, len(PIXELS) * width))
    return [int.from_bytes(out[i:i + width], 'little') for i in range(0, len(out), width)]


def main():
    for title in (False, True):
        if run(16, title) != list(PIXELS):
            raise SystemExit('bgrowtest: 16-bit row not copied as is')
        got, want = run(32, title), [expand(p) for p in PIXELS]
        if got != want:
            raise SystemExit('bgrowtest: 32-bit row wrong: %s' % ' '.join('%06x' % x for x in got))
    print('bgrow: 16-bit copy and 32-bit expand OK, exe and Title.dll')
    return 0


if __name__ == '__main__':
    sys.exit(main())
