#!/usr/bin/env python3
"""The clearsize thunk under Unicorn, against the real exe.

    python3 tools/clearsizetest.py GAMEDIR

Australia's mode setter clears the back buffer with the width for both
of its arguments. The thunk the patch puts in the annex has to hand the
clear the height and the width the right way round, return to the site
it was called from, and leave the arguments where the caller's own
`add esp, 8` will take them off - the clear is cdecl. Anything else and
the site's return address is not where the game left it.

Nothing to do on the other two builds, which pass the height already.
Needs python3-unicorn; exits 77 with a note when it is missing.
"""
import struct
import sys

from uctest import patcher
import uctest

try:
    import pefile
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn.x86_const import UC_X86_REG_ESP
except ImportError:
    print('clearsizetest: skipped, python3-unicorn or pefile not installed')
    sys.exit(77)

WIDTH, HEIGHT = 5120, 1440
STACK = 0x900000


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    build = patcher.check_build(argv[1])
    if 'clearsize' not in patcher.patches(build):
        print('note: clearsize is Australian only; nothing was run on the %s build' % build.lower())
        return 0
    buf = uctest.stock(argv[1], patcher.EXE)
    out = patcher.apply_clearsize(buf, build)

    row = patcher.BUILDS[build]['addresses']
    site = patcher.BUILDS[build]['sites']['clearsize']
    pe = pefile.PE(data=bytes(out))
    base = pe.OPTIONAL_HEADER.ImageBase
    image = pe.get_memory_mapped_image()
    resume = base + 0x1000 + site - patcher._rva_to_off(out, 0x1000) + patcher.CLEARSIZE_LEN - 7

    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(base, (len(image) + 0xfff) & ~0xfff)
    mu.mem_write(base, bytes(image))
    mu.mem_map(STACK, 0x10000)
    mu.mem_write(row['WIDTH'], struct.pack('<I', WIDTH))
    mu.mem_write(row['HEIGHT'], struct.pack('<I', HEIGHT))
    mu.mem_write(row['CLEAR'], b'\xc3')                  # the clear itself: return at once
    esp = STACK + 0x8000
    mu.mem_write(esp, struct.pack('<I', 0xDEAD0000))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.emu_start(base + 0x1000 + site - patcher._rva_to_off(out, 0x1000), row['CLEAR'], timeout=2000000)

    sp = mu.reg_read(UC_X86_REG_ESP)
    ret, width, height = struct.unpack('<III', mu.mem_read(sp, 12))
    if (width, height) != (WIDTH, HEIGHT):
        raise SystemExit('clearsizetest: the clear was given %dx%d, not %dx%d' % (width, height, WIDTH, HEIGHT))
    if ret != resume:
        raise SystemExit('clearsizetest: the clear would return to %08x, not the site at %08x' % (ret, resume))
    if sp + 4 + 8 != esp:
        raise SystemExit("clearsizetest: the caller's own add esp, 8 would leave the stack at %08x, not %08x"
                         % (sp + 4 + 8, esp))
    print('clearsize: the thunk hands the clear %dx%d and returns to the site, %s' % (WIDTH, HEIGHT, build.lower()))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
