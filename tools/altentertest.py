#!/usr/bin/env python3
"""Run the ALT+ENTER stub under Unicorn.

    python3 tools/altentertest.py

ALTENTER_BLOB is called as the window procedure calls the handler it sits
in front of, cdecl (hwnd, msg, wParam, lParam), with user32 replaced by
recording stubs. Any other message must reach the handler with the stack
intact; ALT+ENTER must frame the window at the picture's size centred on
its monitor, a repeat must do nothing, the next press must put it back
over the monitor, and user32 must be loaded once. Needs python3-unicorn;
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
    print('altentertest: skipped, python3-unicorn not installed')
    sys.exit(0)

CODE, FAKE, STACK, RETURN = 0x63e000, 0x40000000, 0x30000000, 0xdead0000
HANDLER, IAT_LOADLIB, IAT_GETPROC, HWND, WIDTH = 0x41fe20, 0x495090, 0x4950f0, 0x5088ac, 0x4d5e1c
WM_SYSKEYDOWN, VK_RETURN, ALT, REPEAT = 0x104, 0x0d, 1 << 29, 1 << 30
STUBS = {'LoadLibraryA': 4, 'GetProcAddress': 8, 'SetWindowLongA': 12, 'SetWindowPos': 28,
         'AdjustWindowRectEx': 16, 'MonitorFromWindow': 8, 'GetMonitorInfoA': 8}
MONITOR = (2560, 0, 1920, 1080)
FRAME = (8, 31, 8, 8)                   # what AdjustWindowRectEx adds: left, top, right, bottom


class Machine:
    def __init__(self):
        self.calls, self.loads = [], 0
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0x400000, 0x300000)
        mu.mem_map(FAKE, 0x1000)
        mu.mem_map(STACK, 0x10000)
        mu.mem_write(CODE, patcher.ALTENTER_BLOB)
        self.addr = {name: FAKE + i * 16 for i, name in enumerate(STUBS)}
        for name, pops in STUBS.items():
            mu.mem_write(self.addr[name], b'\xc2' + struct.pack('<H', pops))
        mu.mem_write(IAT_LOADLIB, struct.pack('<I', self.addr['LoadLibraryA']))
        mu.mem_write(IAT_GETPROC, struct.pack('<I', self.addr['GetProcAddress']))
        mu.mem_write(HWND, struct.pack('<I', 0x1234))
        mu.mem_write(WIDTH, struct.pack('<II', 640, 480))
        mu.mem_write(HANDLER, b'\xb8\xff\xff\xff\xff\xc3')      # mov eax, -1; ret
        self.byaddr = {a: n for n, a in self.addr.items()}
        mu.hook_add(UC_HOOK_CODE, self.hook)

    def arg(self, i):
        esp = self.mu.reg_read(UC_X86_REG_ESP)
        return struct.unpack('<i', self.mu.mem_read(esp + 4 + 4 * i, 4))[0]

    def hook(self, mu, address, _size, _user):
        name = self.byaddr.get(address)
        if not name:
            return
        mx, my, mw, mh = MONITOR
        result = 1
        if name == 'LoadLibraryA':
            self.loads += 1
            result = 0x77770000
        elif name == 'GetProcAddress':
            text = bytes(mu.mem_read(self.arg(1), 32))
            result = self.addr[text[:text.index(b'\0')].decode()]
        elif name == 'MonitorFromWindow':
            self.calls.append(('MonitorFromWindow', self.arg(0), self.arg(1)))
            result = 0x77
        elif name == 'GetMonitorInfoA':
            mu.mem_write(self.arg(1), struct.pack('<5i', 40, mx, my, mx + mw, my + mh))
        elif name == 'AdjustWindowRectEx':
            l, t, r, b = struct.unpack('<4i', mu.mem_read(self.arg(0), 16))
            mu.mem_write(self.arg(0), struct.pack('<4i', l - FRAME[0], t - FRAME[1], r + FRAME[2], b + FRAME[3]))
            self.calls.append(('AdjustWindowRectEx', self.arg(1) & 0xffffffff))
        elif name == 'SetWindowLongA':
            self.calls.append(('SetWindowLongA', self.arg(1), self.arg(2) & 0xffffffff))
        elif name == 'SetWindowPos':
            self.calls.append(('SetWindowPos',) + tuple(self.arg(i) for i in range(7)))
        mu.reg_write(UC_X86_REG_EAX, result)

    def send(self, msg, wparam, lparam):
        self.calls = []
        esp = STACK + 0x8000
        self.mu.mem_write(esp, struct.pack('<5I', RETURN, 0x1234, msg, wparam, lparam))
        self.mu.reg_write(UC_X86_REG_ESP, esp)
        self.mu.emu_start(CODE, RETURN)
        if self.mu.reg_read(UC_X86_REG_ESP) != esp + 4:
            raise SystemExit('altentertest: stack wrong after message 0x%x' % msg)
        return self.mu.reg_read(UC_X86_REG_EAX), self.calls


def main():
    m = Machine()
    mx, my, mw, mh = MONITOR
    w, h = 640 + FRAME[0] + FRAME[2], 480 + FRAME[1] + FRAME[3]
    framed = [('MonitorFromWindow', 0x1234, 2), ('SetWindowLongA', -16, 0x10cf0000),
              ('AdjustWindowRectEx', 0x10cf0000),
              ('SetWindowPos', 0x1234, 0, mx + (mw - w) // 2, my + (mh - h) // 2, w, h, 0x64)]
    borderless = [('MonitorFromWindow', 0x1234, 2), ('SetWindowLongA', -16, 0x90000000),
                  ('SetWindowPos', 0x1234, 0, mx, my, mw, mh, 0x64)]
    checks = [
        ('another message', (0x102, 0x41, 0), (0xffffffff, [])),
        ('ALT+ENTER', (WM_SYSKEYDOWN, VK_RETURN, ALT), (0, framed)),
        ('a repeat', (WM_SYSKEYDOWN, VK_RETURN, ALT | REPEAT), (0, [])),
        ('ALT+ENTER again', (WM_SYSKEYDOWN, VK_RETURN, ALT), (0, borderless)),
        ('ENTER without ALT', (WM_SYSKEYDOWN, VK_RETURN, 0), (0xffffffff, [])),
    ]
    for what, message, want in checks:
        got = m.send(*message)
        if got != want:
            raise SystemExit('altentertest: %s: %r' % (what, got))
    if m.loads != 1:
        raise SystemExit('altentertest: user32 loaded %d times' % m.loads)
    print('altenter: other messages pass, framed and back, repeats ignored')
    return 0


if __name__ == '__main__':
    sys.exit(main())
