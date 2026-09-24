#!/usr/bin/env python3
"""Run the d3dinit diagnostic under Unicorn.

    python3 tools/d3dinittest.py

D3DINIT_BLOB is mapped as the patcher would place it in a relocated
MGameD3D.dll, with the three kernel32 import slots pointing at stubs
here that play GetModuleHandleA, GetProcAddress, GetModuleFileNameA,
CreateDirectoryA, CreateFileA and WriteFile. Three calls from three
sites must store each HRESULT in the last-HRESULT slot, make logs\
beside the exe, write the header and one line per call to a file in it,
and return with every register and the flags as they were. Needs python3-unicorn; exits 77 with a note when
it is missing.
"""
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('d3dinittest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI,
                               UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EFLAGS)

BASE, SELF, IMAGE = 0x02ba0000, 0x16000, 0x20000     # a relocated load, as Windows did
STACK, RETURN = 0x30000000, 0xdead0000
LASTHR, WIDTH, HEIGHT, MAXTEX = 0x11fc4, 0x123fc, 0x12400, 0x124e4
SLOTS = {0xf0b0: 'GetModuleHandleA', 0xf0ac: 'GetProcAddress', 0xf038: 'GetModuleFileNameA'}
STUBS = 0x40000000                      # the stubs: one hlt each, 16 apart
NAMES = ['GetModuleHandleA', 'GetProcAddress', 'GetModuleFileNameA', 'CreateDirectoryA', 'CreateFileA', 'WriteFile']
HANDLE = 0x777
EXE = b'C:\\Games\\SR2\\SEGA RALLY 2.exe'


class Kernel:
    def __init__(self, mu):
        self.mu, self.opened, self.made, self.written, self.calls = mu, None, None, b'', []

    def string(self, at):
        out = b''
        while True:
            c = bytes(self.mu.mem_read(at + len(out), 1))
            if c == b'\0':
                return out
            out += c

    def hook(self, mu, address, _size, _user):
        if not STUBS <= address < STUBS + 16 * len(NAMES):
            return
        name = NAMES[(address - STUBS) // 16]
        esp = mu.reg_read(UC_X86_REG_ESP)
        args = struct.unpack('<8I', mu.mem_read(esp, 32))
        self.calls.append(name)
        if name == 'GetModuleHandleA':
            assert self.string(args[1]) == b'kernel32.dll'
            eax, n = 0x7c800000, 1
        elif name == 'GetProcAddress':
            assert args[1] == 0x7c800000
            eax, n = STUBS + 16 * NAMES.index(self.string(args[2]).decode()), 2
        elif name == 'GetModuleFileNameA':
            assert args[1] == 0 and args[3] == 260
            mu.mem_write(args[2], EXE + b'\0')
            eax, n = len(EXE), 3
        elif name == 'CreateDirectoryA':
            self.made = self.string(args[1])
            assert args[2] == 0
            eax, n = 0, 2                   # as when it exists already: ignored
        elif name == 'CreateFileA':
            self.opened = self.string(args[1])
            assert args[2:8] == (0x40000000, 1, 0, 2, 0x80, 0), args[2:8]
            eax, n = HANDLE, 7
        else:
            assert args[1] == HANDLE and args[5] == 0
            self.written += bytes(mu.mem_read(args[2], args[3]))
            mu.mem_write(args[4], struct.pack('<I', args[3]))
            eax, n = 1, 5
        mu.reg_write(UC_X86_REG_EAX, eax)
        mu.reg_write(UC_X86_REG_ESP, esp + 4 + 4 * n)      # stdcall: the return and the arguments
        mu.reg_write(UC_X86_REG_EIP, args[0])


def main(argv):
    blob = patcher.D3DINIT_BLOB.replace(struct.pack('<I', patcher.FULLWIN_MAGIC), struct.pack('<I', SELF))
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(BASE, IMAGE)
    mu.mem_map(STACK, 0x10000)
    mu.mem_map(STUBS, 0x1000)
    mu.mem_write(BASE + SELF, blob)
    for slot, name in SLOTS.items():
        mu.mem_write(BASE + slot, struct.pack('<I', STUBS + 16 * NAMES.index(name)))
    mu.mem_write(STUBS, b'\xf4' * 16 * len(NAMES))
    mu.mem_write(BASE + WIDTH, struct.pack('<II', 1920, 1080))
    mu.mem_write(BASE + MAXTEX, struct.pack('<II', 16384, 16384))
    for slot in (1, 2, 3, 4, 11):                       # the format slots the device filled: dwSize set
        mu.mem_write(BASE + 0x12594 + slot * 32, struct.pack('<I', 32))
    mu.mem_write(BASE + 0x1273c, struct.pack('<II', 1, 3))    # not-565 flag, the slot chosen
    kernel = Kernel(mu)
    mu.hook_add(UC_HOOK_CODE, kernel.hook)
    regs = {UC_X86_REG_EAX: 0, UC_X86_REG_EBX: 0x42424242, UC_X86_REG_ECX: 0x43434343, UC_X86_REG_EDX: 0x44444444,
            UC_X86_REG_ESI: 0x45454545, UC_X86_REG_EDI: 0x46464646, UC_X86_REG_EBP: 0x47474747}
    for site, hr, flags in ((0x3593, 0, 0x246), (0x36c7, 0x887601c2, 0x286), (0x20c5, 0, 0x246), (0x2725, 0x80004005, 0x202)):
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<I', BASE + site + 5))
        mu.mem_write(BASE + site + 5, b'\xf4')
        regs[UC_X86_REG_EAX] = hr
        for reg, value in regs.items():
            mu.reg_write(reg, value)
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EFLAGS, flags)
        mu.emu_start(BASE + SELF, BASE + site + 5, count=20000)
        assert mu.reg_read(UC_X86_REG_EIP) == BASE + site + 5, 'site %x: did not return, eip %x' % (site, mu.reg_read(UC_X86_REG_EIP))
        assert mu.reg_read(UC_X86_REG_ESP) == esp + 4, 'site %x: the return popped' % site
        for reg, value in regs.items():
            assert mu.reg_read(reg) == value, 'site %x: register %d changed' % (site, reg)
        assert mu.reg_read(UC_X86_REG_EFLAGS) & 0x8d5 == flags & 0x8d5, 'site %x: flags changed' % site
        assert struct.unpack('<I', mu.mem_read(BASE + LASTHR, 4))[0] == hr, 'site %x: the store not done' % site
    assert kernel.made == b'C:\\Games\\SR2\\logs', kernel.made
    assert kernel.opened == b'C:\\Games\\SR2\\logs\\d3dinit.log', kernel.opened
    assert kernel.calls.count('CreateFileA') == 1, 'opened more than once'
    assert kernel.written == (b'site hr WxH maxtex\r\n00003593 00000000 1920x1080 16384x16384\r\n'
                              b'000036c7 887601c2 1920x1080 16384x16384\r\n000020c5 00000000 1920x1080 16384x16384\r\n'
                              b'fmt 0000081e 00000003 00000001\r\n00002725 80004005 1920x1080 16384x16384\r\n'), kernel.written
    print('d3dinittest OK: four stores logged in logs\\ with the format line, registers and flags kept')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
