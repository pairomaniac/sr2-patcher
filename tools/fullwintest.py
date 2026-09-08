#!/usr/bin/env python3
"""Run the borderless patch's two thunks under Unicorn.

    python3 tools/fullwintest.py

FULLWIN_BLOB is mapped as the patcher would place it, with user32 and the
primary surface's Blt replaced by recording stubs. `present` must fill the
bars and blit the picture into a rect of the back buffer's aspect, centred
in the client rect, for 16:9, 16:10, 4:3 and a taller-than-4:3 window, and
leave the stack as the routine it replaces did. `sizewindow` must move the
window to the monitor under the cursor. Needs python3-unicorn; exits 0
with a note when it is missing.
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
    print('fullwintest: skipped, python3-unicorn not installed')
    sys.exit(0)

BASE, SELF, IMAGE = 0x10000000, 0x16000, 0x20000
STACK, FAKE, RETURN = 0x30000000, 0x40000000, 0xdead0000
HWND, PRIMARY, BACK, SRCRECT = 0x123f8, 0x12550, 0x12554, 0x12410
SLOTS = {'GetClientRect': 0xf140, 'ClientToScreen': 0xf13c, 'MoveWindow': 0xf12c,
         'LoadLibraryA': 0xf114, 'GetProcAddress': 0xf0ac}
# Stubs and how many argument bytes each pops.
STUBS = {'GetClientRect': 8, 'ClientToScreen': 8, 'MoveWindow': 24, 'LoadLibraryA': 4,
         'GetProcAddress': 8, 'Blt': 24, 'GetCursorPos': 4, 'MonitorFromPoint': 12,
         'GetMonitorInfoA': 8}
DDBLT_COLORFILL, DDBLT_WAIT = 0x400, 0x1000000


class Machine:
    def __init__(self, client, monitor):
        """client: (w, h) of the window's client area; monitor: (x, y, w, h)."""
        self.client, self.monitor, self.calls = client, monitor, []
        blob = patcher.FULLWIN_BLOB.replace(struct.pack('<I', patcher.FULLWIN_MAGIC), struct.pack('<I', SELF))
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(BASE, IMAGE)
        mu.mem_map(STACK, 0x10000)
        mu.mem_map(FAKE, 0x1000)
        mu.mem_write(BASE + SELF, blob)
        self.addr = {name: FAKE + i * 16 for i, name in enumerate(STUBS)}
        for name, pops in STUBS.items():
            mu.mem_write(self.addr[name], b'\xc2' + struct.pack('<H', pops))
        for name, rva in SLOTS.items():
            mu.mem_write(BASE + rva, struct.pack('<I', self.addr[name]))
        vtable, surface = BASE + 0x18000, BASE + 0x18100
        mu.mem_write(BASE + HWND, struct.pack('<I', 0x1234))
        mu.mem_write(BASE + PRIMARY, struct.pack('<I', surface))
        mu.mem_write(surface, struct.pack('<I', vtable))
        mu.mem_write(vtable + 0x14, struct.pack('<I', self.addr['Blt']))
        mu.mem_write(BASE + BACK, struct.pack('<I', 0xbacc))
        mu.mem_write(BASE + SRCRECT, struct.pack('<4i', 0, 0, 640, 480))
        self.byaddr = {a: n for n, a in self.addr.items()}
        mu.hook_add(UC_HOOK_CODE, self.hook)

    def arg(self, i):
        esp = self.mu.reg_read(UC_X86_REG_ESP)
        return struct.unpack('<I', self.mu.mem_read(esp + 4 + 4 * i, 4))[0]

    def hook(self, mu, address, _size, _user):
        name = self.byaddr.get(address)
        if not name:
            return
        mx, my, mw, mh = self.monitor
        result = 1
        if name == 'GetClientRect':
            mu.mem_write(self.arg(1), struct.pack('<4i', 0, 0, self.client[0], self.client[1]))
        elif name == 'ClientToScreen':
            x, y = struct.unpack('<2i', mu.mem_read(self.arg(1), 8))
            mu.mem_write(self.arg(1), struct.pack('<2i', x + mx, y + my))
        elif name == 'LoadLibraryA':
            result = 0x77770000
        elif name == 'GetProcAddress':
            text = bytes(mu.mem_read(self.arg(1), 32))
            result = self.addr[text[:text.index(b'\0')].decode()]
        elif name == 'GetCursorPos':
            mu.mem_write(self.arg(0), struct.pack('<2i', mx + 5, my + 5))
        elif name == 'MonitorFromPoint':
            self.calls.append(('MonitorFromPoint', self.arg(0), self.arg(1), self.arg(2)))
            result = 0x77
        elif name == 'GetMonitorInfoA':
            mu.mem_write(self.arg(1), struct.pack('<5i', 40, mx, my, mx + mw, my + mh))
        elif name == 'Blt':
            self.calls.append(('Blt', struct.unpack('<4i', mu.mem_read(self.arg(1), 16)),
                               self.arg(2), self.arg(4)))
            result = 0
        elif name == 'MoveWindow':
            self.calls.append(('MoveWindow',) + tuple(self.arg(i) for i in range(6)))
        mu.reg_write(UC_X86_REG_EAX, result)

    def present(self):
        """As 0x10004d7b is reached: a 16-byte frame below the return and
        the one argument."""
        esp = STACK + 0x8000
        self.mu.mem_write(esp + 0x10, struct.pack('<II', RETURN, 0))
        self.mu.reg_write(UC_X86_REG_ESP, esp)
        self.mu.emu_start(BASE + SELF, RETURN)
        if self.mu.reg_read(UC_X86_REG_ESP) != esp + 0x18:
            raise SystemExit('fullwintest: present left the stack wrong')
        return self.calls

    def sizewindow(self):
        esp = STACK + 0x8000
        self.mu.mem_write(esp, struct.pack('<7I', RETURN, 0x1234, 0, 0, 650, 500, 1))
        self.mu.reg_write(UC_X86_REG_ESP, esp)
        self.mu.emu_start(BASE + SELF + 5, RETURN)
        if self.mu.reg_read(UC_X86_REG_ESP) != esp + 4 + 0x18:
            raise SystemExit('fullwintest: sizewindow left the stack wrong')
        return self.calls


def check_present(client, monitor, picture, bars):
    calls = Machine(client, monitor).present()
    fills = [c[1] for c in calls if c[0] == 'Blt' and c[3] == DDBLT_COLORFILL | DDBLT_WAIT]
    blits = [c for c in calls if c[0] == 'Blt' and c[3] == DDBLT_WAIT]
    if blits != [('Blt', picture, 0xbacc, DDBLT_WAIT)] or sorted(fills) != sorted(bars):
        raise SystemExit('fullwintest: %dx%d on %r: %r' % (client + (monitor, calls)))


def main():
    check_present((2560, 1440), (0, 0, 2560, 1440), (320, 0, 2240, 1440),
                  [(0, 0, 320, 1440), (2240, 0, 2560, 1440)])
    check_present((1920, 1200), (1920, 0, 1920, 1200), (2080, 0, 3680, 1200),
                  [(1920, 0, 2080, 1200), (3680, 0, 3840, 1200)])
    check_present((640, 480), (100, 50, 640, 480), (100, 50, 740, 530), [])
    check_present((1000, 1000), (0, 0, 1000, 1000), (0, 125, 1000, 875),
                  [(0, 0, 1000, 125), (0, 875, 1000, 1000)])
    calls = Machine((640, 480), (2560, 0, 1920, 1080)).sizewindow()
    if calls != [('MonitorFromPoint', 2565, 5, 2), ('MoveWindow', 0x1234, 2560, 0, 1920, 1080, 1)]:
        raise SystemExit('fullwintest: sizewindow: %r' % calls)
    print('fullwin: present letterboxes at four aspects, sizewindow covers the monitor')
    return 0


if __name__ == '__main__':
    sys.exit(main())
