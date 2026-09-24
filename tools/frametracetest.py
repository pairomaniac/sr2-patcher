#!/usr/bin/env python3
"""Run the frametrace stub under Unicorn.

    python3 tools/frametracetest.py

FRAMETRACE_BLOB is mapped with the two IAT slots pointing at recording
stubs, the four flags in a page of their own and the two slots after it
filled as the patcher fills them, and entered as the frame gate would:
its entry first, then its exit. The entry must take the counter through
the routine given, leave ecx and edx alone and continue with eax as the
displaced load. The first exit must make logs\\ beside the exe, open frames.log in it, write
the header and its line; the next only its line, with the entry counter,
the stamp found through the jump at the fake MGameD3D's present and the
flags as bits; and leave as the gate did: three registers popped, the
counter stored in the timer object, the stack back where it was. With
user32 missing nothing is written and nothing is retried; without the
jump (the borderless patch not in) the stamp is 0. Needs python3-unicorn; exits 77 with a note when it is missing.
"""
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('frametracetest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI, \
UC_X86_REG_EDI, UC_X86_REG_ESP

BLOB, SLOTS, TIMER, STACK, FAKE, RETURN = 0x600000, 0x500000, 0x510000, 0x30000000, 0x40000000, 0xdead0000
COUNTER, BACK = 0x40000100, 0xdead0100  # the game's counter routine; the gate's sixth byte
DLL, DLL_BLOB = 0x10000000, 0x17000     # a fake MGameD3D.dll, where its borderless blob would be
FLAGS = 0x520000                        # RUNNING, PAUSED, DEBUGDLL, CATCHUP, a dword each
M = patcher.EXE_MAGICS
MAGICS = {M['LOADLIB']: SLOTS, M['GETPROC']: SLOTS + 4, M['RUNNING']: FLAGS, M['PAUSED']: FLAGS + 4,
          M['DEBUGDLL']: FLAGS + 8, M['CATCHUP']: FLAGS + 12}
EXE = 'C:\\games\\sr2\\SEGA RALLY 2.exe'
STUBS = {'LoadLibraryA': 4, 'GetProcAddress': 8, 'GetModuleFileNameA': 12, 'CreateDirectoryA': 8, 'CreateFileA': 28,
         'WriteFile': 20, 'wsprintfA': 0, 'GetModuleHandleA': 4}
MODULES = {'kernel32.dll': 0x77770000, 'user32.dll': 0x77780000}


class Machine:
    def __init__(self, user32=True, borderless=True, entry=0x12345678):
        self.user32, self.calls = user32, []
        blob = patcher.FRAMETRACE_BLOB
        for magic, value in MAGICS.items():
            blob = blob.replace(struct.pack('<I', magic), struct.pack('<I', value))
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(BLOB, 0x1000)
        mu.mem_map(SLOTS, 0x1000)
        mu.mem_map(TIMER, 0x1000)
        mu.mem_map(STACK, 0x10000)
        mu.mem_map(FAKE, 0x1000)
        mu.mem_map(FLAGS, 0x1000)
        after = BLOB + len(blob)        # the two dwords the patcher writes after the blob
        blob = blob.replace(struct.pack('<I', patcher.SITE_MAGICS[0]), struct.pack('<I', after)) \
            .replace(struct.pack('<I', patcher.SITE_MAGICS[1]), struct.pack('<I', after + 4)) \
            .replace(struct.pack('<I', patcher.SITE_MAGICS[2]), struct.pack('<I', patcher.FRAMETRACE_STAMP + patcher.fullwin_stamp()))
        mu.mem_write(BLOB, blob)
        # the present's first bytes: the borderless patch's jump to its blob, or the stock load
        mu.mem_map(DLL, 0x18000)
        site = DLL + patcher.PRESENT_SITE
        mu.mem_write(site, b'\xe9' + struct.pack('<i', DLL + DLL_BLOB - (site + 5)) if borderless
                     else bytes.fromhex('8b0df8230110'))
        mu.mem_write(DLL + DLL_BLOB + patcher.fullwin_stamp(), struct.pack('<I', 1100))
        mu.mem_write(after, struct.pack('<II', COUNTER, BACK))
        mu.mem_write(COUNTER, b'\xb8' + struct.pack('<I', entry) + b'\xc3')   # mov eax, entry; ret
        self.addr = {name: FAKE + i * 16 for i, name in enumerate(STUBS)}
        for name, pops in STUBS.items():
            mu.mem_write(self.addr[name], (b'\xc2' + struct.pack('<H', pops)) if pops else b'\xc3')
        mu.mem_write(SLOTS, struct.pack('<II', self.addr['LoadLibraryA'], self.addr['GetProcAddress']))
        mu.mem_write(TIMER + 0x24, struct.pack('<II', 166666, 1))
        self.byaddr = {a: n for n, a in self.addr.items()}
        mu.hook_add(UC_HOOK_CODE, self.hook)

    def arg(self, i):
        esp = self.mu.reg_read(UC_X86_REG_ESP)
        return struct.unpack('<I', self.mu.mem_read(esp + 4 + 4 * i, 4))[0]

    def text(self, addr):
        raw = bytes(self.mu.mem_read(addr, 300))
        return raw[:raw.index(b'\0')].decode()

    def hook(self, mu, address, _size, _user):
        name = self.byaddr.get(address)
        if not name:
            return
        result = 0
        if name == 'LoadLibraryA':
            module = self.text(self.arg(0))
            self.calls.append(('LoadLibraryA', module))
            result = MODULES[module] if self.user32 or module != 'user32.dll' else 0
        elif name == 'GetProcAddress':
            result = self.addr[self.text(self.arg(1))]
        elif name == 'GetModuleHandleA':
            self.calls.append(('GetModuleHandleA', self.text(self.arg(0))))
            result = DLL
        elif name == 'GetModuleFileNameA':
            mu.mem_write(self.arg(1), EXE.encode() + b'\0')
            result = len(EXE)
        elif name == 'CreateDirectoryA':
            self.calls.append(('CreateDirectoryA', self.text(self.arg(0)), self.arg(1)))
            result = 0                  # as when it exists already: ignored
        elif name == 'CreateFileA':
            self.calls.append(('CreateFileA', self.text(self.arg(0))) + tuple(self.arg(i) for i in range(1, 7)))
            result = 0x600
        elif name == 'WriteFile':
            self.calls.append(('WriteFile', self.arg(0), bytes(mu.mem_read(self.arg(1), self.arg(2))).decode()))
            mu.mem_write(self.arg(3), struct.pack('<I', self.arg(2)))
            result = 1
        elif name == 'wsprintfA':
            fmt = self.text(self.arg(1))
            out = fmt % tuple(self.arg(2 + i) for i in range(fmt.count('%')))
            mu.mem_write(self.arg(0), out.encode() + b'\0')
            result = len(out)
        mu.reg_write(UC_X86_REG_EAX, result)

    def frame(self, now, steps, flags=(1, 0, 0, 1)):
        """The gate's entry, ecx = the timer object; then its exit: ebx, esi,
        edi pushed under the return, eax the counter, ebx the steps, esi
        the timer object; the four flags as the exe holds them."""
        mu = self.mu
        mu.mem_write(FLAGS, struct.pack('<4I', *flags))
        mu.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
        mu.reg_write(UC_X86_REG_ECX, TIMER)
        mu.reg_write(UC_X86_REG_EDX, 0xd2d2)
        mu.emu_start(BLOB + 5, BACK, timeout=2000000)
        if (mu.reg_read(UC_X86_REG_ECX), mu.reg_read(UC_X86_REG_EDX), mu.reg_read(UC_X86_REG_ESP)) != (TIMER, 0xd2d2, STACK + 0x8000):
            raise SystemExit('frametracetest: the entry clobbered registers or the stack')
        if mu.reg_read(UC_X86_REG_EAX) != flags[0]:
            raise SystemExit('frametracetest: the entry did not load the running flag')
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<4I', 0xd1, 0x51, 0xb1, RETURN))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EAX, now)
        mu.reg_write(UC_X86_REG_EBX, steps)
        mu.reg_write(UC_X86_REG_ESI, TIMER)
        mu.emu_start(BLOB, RETURN, timeout=2000000)
        if mu.reg_read(UC_X86_REG_ESP) != esp + 16:
            raise SystemExit('frametracetest: the stack was left wrong')
        if (mu.reg_read(UC_X86_REG_EDI), mu.reg_read(UC_X86_REG_ESI), mu.reg_read(UC_X86_REG_EBX)) != (0xd1, 0x51, 0xb1):
            raise SystemExit('frametracetest: the registers were not popped')
        if struct.unpack('<I', mu.mem_read(TIMER + 0x1c, 4))[0] != now:
            raise SystemExit('frametracetest: the counter was not stored')
        calls, self.calls = self.calls, []
        return calls


def main():
    m = Machine()
    calls = m.frame(1000, 1)
    made = [c for c in calls if c[0] == 'CreateDirectoryA']
    if made != [('CreateDirectoryA', 'C:\\games\\sr2\\logs', 0)]:
        raise SystemExit('frametracetest: the folder: %r' % made)
    opened = [c for c in calls if c[0] == 'CreateFileA']
    if opened != [('CreateFileA', 'C:\\games\\sr2\\logs\\frames.log', 0x40000000, 1, 0, 2, 0x80, 0)]:
        raise SystemExit('frametracetest: the open: %r' % opened)
    writes = [c[2] for c in calls if c[0] == 'WriteFile']
    if writes != ['budget 166666 qpc 1\r\n', '305419896 1100 1000 1 9\r\n'] \
            or any(c[1] != 0x600 for c in calls if c[0] == 'WriteFile'):
        raise SystemExit('frametracetest: the first frame wrote %r' % writes)
    if [c for c in calls if c[0] == 'GetModuleHandleA'] != [('GetModuleHandleA', 'MGameD3D.dll')]:
        raise SystemExit('frametracetest: the DLL was not looked up: %r' % calls)
    calls = m.frame(4000000000, 3, flags=(0, 7, 3, 0))
    if [c for c in calls if c[0] != 'WriteFile'] or [c[2] for c in calls] != ['305419896 1100 4000000000 3 6\r\n']:
        raise SystemExit('frametracetest: the second frame: %r' % calls)
    m = Machine(entry=4294967293)       # the longest line there is
    m.mu.mem_write(DLL + DLL_BLOB + patcher.fullwin_stamp(), struct.pack('<I', 4294967295))
    calls = m.frame(4294967292, 4, flags=(1, 1, 1, 1))
    calls = [c for c in calls if c[0] == 'WriteFile'][1:]
    if [c[2] for c in calls] != ['4294967293 4294967295 4294967292 4 15\r\n']:
        raise SystemExit('frametracetest: the longest line: %r' % calls)
    calls = Machine(borderless=False).frame(1000, 1)
    if [c[2] for c in calls if c[0] == 'WriteFile'][1] != '305419896 0 1000 1 9\r\n':
        raise SystemExit('frametracetest: without the borderless patch: %r' % calls)
    m = Machine(user32=False)
    calls = m.frame(1000, 1)
    if any(c[0] in ('CreateFileA', 'WriteFile') for c in calls):
        raise SystemExit('frametracetest: wrote without user32: %r' % calls)
    if m.frame(2000, 1):
        raise SystemExit('frametracetest: retried after a failure')
    print('frametrace: keeps the counter at the entry, opens logs\\frames.log, writes the header and '
          'a line a frame with the present\'s stamp and the flags, leaves as the gate did, gives up once')
    return 0


if __name__ == '__main__':
    sys.exit(main())
