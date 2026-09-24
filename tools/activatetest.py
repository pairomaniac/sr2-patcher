#!/usr/bin/env python3
"""Run the two halves of the alt-tab fix under Unicorn.

    python3 tools/activatetest.py GAMEDIR    # the install folder

The exe half: a copy of the exe patched in memory, the rewritten site
called with a fake MGameD3D object - the restore slot must be called with
the object, ecx must survive, and control must arrive at the sound resume
with the stack as the original call would have left it.

The DLL half: MGameD3D.dll patched in memory, mapped and relocated to
another base, its restore routine called - it must call RestoreAllSurfaces
on the IDirectDraw4 and store the result. Needs python3-unicorn; exits 77
with a note when it is missing.
"""
import os
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('activatetest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EIP

BASE = 0x400000
OBJ, VTABLE, RESTORE, STACK = 0x2000000, 0x2001000, 0x2002000, 0x3000000


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    path = os.path.join(argv[1], patcher.EXE)
    if os.path.isfile(path + '.bak'):
        path += '.bak'
    with open(path, 'rb') as fh:
        image = bytearray(fh.read())
    build = patcher.build_of(patcher.md5(path))
    if build is None:
        print('activatetest: %s is not a build the patcher knows' % path)
        return 1
    row = patcher.BUILDS[build]
    gamed3d, resume = row['addresses']['GAMED3D'], row['addresses']['RESUME']
    site = BASE + patcher._off_to_rva(image, row['sites']['activate'])
    image = patcher.apply_activate(image, build)
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    uctest.map_image(mu, image, BASE)
    mu.mem_map(OBJ & ~0xfff, 0x3000)
    mu.mem_map(STACK, 0x10000)
    mu.mem_write(gamed3d, struct.pack('<I', OBJ))
    mu.mem_write(OBJ, struct.pack('<I', VTABLE))
    mu.mem_write(VTABLE + 0x40, struct.pack('<I', RESTORE))
    mu.mem_write(RESTORE, b'\xc2\x04\x00')                      # ret 4
    calls = []

    def on_restore(mu_, address, size_, user):
        esp = mu_.reg_read(UC_X86_REG_ESP)
        calls.append(struct.unpack('<I', mu_.mem_read(esp + 4, 4))[0])
    mu.hook_add(UC_HOOK_CODE, on_restore, begin=RESTORE, end=RESTORE + 1)

    esp = STACK + 0x8000
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.reg_write(UC_X86_REG_ECX, 0x1234)
    mu.emu_start(site, resume, count=1000)
    assert mu.reg_read(UC_X86_REG_EIP) == resume, 'did not reach the resume'
    assert calls == [OBJ], 'restore not called with the object: %r' % calls
    assert mu.reg_read(UC_X86_REG_ECX) == 0x1234, 'ecx clobbered'
    assert mu.reg_read(UC_X86_REG_ESP) == esp - 4, 'stack differs from a plain call'
    assert struct.unpack('<I', mu.mem_read(esp - 4, 4))[0] == site + 5, 'return address'
    # with no MGameD3D object the stub must skip straight to the resume
    mu.mem_write(gamed3d, struct.pack('<I', 0))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.emu_start(site, resume, count=1000)
    assert calls == [OBJ] and mu.reg_read(UC_X86_REG_EIP) == resume
    # --- the DLL half
    path = os.path.join(argv[1], 'MUSASHI', 'MGameD3D.dll')
    if os.path.isfile(path + '.bak'):
        path += '.bak'
    with open(path, 'rb') as fh:
        dll = patcher.apply_restore(bytearray(fh.read()))
    DBASE = 0x01DD0000
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    uctest.map_image(mu, dll, DBASE)
    mu.mem_map(OBJ & ~0xfff, 0x3000)
    mu.mem_map(STACK, 0x10000)
    DDRAW4, LASTERR = DBASE + 0x1254c, DBASE + 0x11fc4
    mu.mem_write(DDRAW4, struct.pack('<I', OBJ))
    mu.mem_write(OBJ, struct.pack('<I', VTABLE))
    mu.mem_write(VTABLE + 0x64, struct.pack('<I', RESTORE))
    mu.mem_write(RESTORE, b'\xb8\x77\x00\x00\x00\xc2\x04\x00')     # mov eax, 0x77; ret 4
    calls.clear()
    mu.hook_add(UC_HOOK_CODE, on_restore, begin=RESTORE, end=RESTORE + 1)
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.mem_write(esp, struct.pack('<II', 0xDEAD0000, 0x5555))
    mu.emu_start(DBASE + 0x7710, 0xDEAD0000, count=1000)
    assert calls == [OBJ], 'RestoreAllSurfaces not called with the IDirectDraw4: %r' % calls
    assert struct.unpack('<I', mu.mem_read(LASTERR, 4))[0] == 0x77, 'result not stored'
    assert mu.reg_read(UC_X86_REG_ESP) == esp + 8, 'stdcall(this) stack'
    mu.mem_write(DDRAW4, struct.pack('<I', 0))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.mem_write(esp, struct.pack('<II', 0xDEAD0000, 0x5555))
    mu.emu_start(DBASE + 0x7710, 0xDEAD0000, count=1000)
    assert calls == [OBJ] and struct.unpack('<I', mu.mem_read(LASTERR, 4))[0] == 0
    print('activatetest OK: exe stub calls the restore slot on activation; '
          'DLL routine calls RestoreAllSurfaces, relocated')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
