#!/usr/bin/env python3
"""Run the starting-line stub under Unicorn, every build.

    python3 tools/startingtest.py

STARTING_BLOB is called in place of the race setup, with gdi32, the
room's background surface, MGameD3D and the room's draw replaced by
recording stubs. It must resolve gdi32 once, write the line centred on
the status strip's row with the row cleared to its own pixel colour,
give the DC back, draw the room and present it, and reach the setup with
the stack and the callee-saved registers as the site left them; without
gdi32, a surface or a DC it must reach the setup having drawn nothing.
Needs python3-unicorn; exits 77 with a note when it is missing.
"""
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('startingtest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ESP, UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI,
                               UC_X86_REG_EBP)

CODE, FAKE, STACK, RETURN = 0x63e000, 0x40000000, 0x30000000, 0xdead0000
HDC, FONT, PIXEL, WIDTH, CX, CY = 0x7777, 0x8888, 0x123456, 640, 300, 16
LINE = 'STARTING - WAITING FOR THE OTHERS'
STUBS = {'LoadLibraryA': 4, 'GetProcAddress': 8, 'SelectObject': 8, 'SetTextColor': 8, 'GetPixel': 12,
         'SetBkColor': 8, 'SetBkMode': 8, 'GetTextExtentPoint32A': 16, 'ExtTextOutA': 32,
         'GetDC': 8, 'ReleaseDC': 8, 'Present': 4, 'After': 4, 'RoomDraw': 0, 'RaceSetup': 0}


class Machine:
    def __init__(self, build):
        self.build = build
        self.row = row = patcher.BUILDS[build]
        self.calls, self.loads = [], 0
        self.have = {'gdi32': True, 'surface': True, 'dc': True}
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0x400000, 0x300000)
        mu.mem_map(FAKE, 0x1000)
        mu.mem_map(STACK, 0x10000)
        mu.mem_write(CODE, patcher.exe_blob(patcher.STARTING_BLOB, build))
        self.addr = {name: FAKE + i * 16 for i, name in enumerate(STUBS)}
        for name, pops in STUBS.items():
            mu.mem_write(self.addr[name], (b'\xc2' + struct.pack('<H', pops)) if pops else b'\xc3')
        mu.mem_write(row['slots']['LoadLibraryA'], struct.pack('<I', self.addr['LoadLibraryA']))
        mu.mem_write(row['slots']['GetProcAddress'], struct.pack('<I', self.addr['GetProcAddress']))
        a = row['addresses']
        self.surface, self.d3d = FAKE + 0x800, FAKE + 0x900       # the objects, their vtables after them
        mu.mem_write(self.surface, struct.pack('<I', self.surface + 0x40))
        mu.mem_write(self.surface + 0x40 + 0x28, struct.pack('<II', self.addr['GetDC'], self.addr['ReleaseDC']))
        mu.mem_write(self.d3d, struct.pack('<I', self.d3d + 0x40))
        mu.mem_write(self.d3d + 0x40 + 0x80, struct.pack('<I', self.addr['Present']))
        mu.mem_write(self.d3d + 0x40 + 0x88, struct.pack('<I', self.addr['After']))
        mu.mem_write(a['ROOMBG'], struct.pack('<I', self.surface))
        mu.mem_write(a['ROOMSIZE'], struct.pack('<II', WIDTH, 480))
        mu.mem_write(a['ROOMFONT'], struct.pack('<I', FONT))
        mu.mem_write(a['GAMED3D'], struct.pack('<I', self.d3d))
        mu.mem_write(a['ROOMDRAW'], b'\xe9' + struct.pack('<i', self.addr['RoomDraw'] - a['ROOMDRAW'] - 5))
        mu.mem_write(a['RACESETUP'], b'\xe9' + struct.pack('<i', self.addr['RaceSetup'] - a['RACESETUP'] - 5))
        self.byaddr = {v: k for k, v in self.addr.items()}
        mu.hook_add(UC_HOOK_CODE, self.hook)

    def arg(self, i):
        esp = self.mu.reg_read(UC_X86_REG_ESP)
        return struct.unpack('<i', self.mu.mem_read(esp + 4 + 4 * i, 4))[0]

    def hook(self, mu, address, _size, _user):
        name = self.byaddr.get(address)
        if not name:
            return
        result = 1
        if name == 'LoadLibraryA':
            self.loads += 1
            result = 0x77770000 if self.have['gdi32'] else 0
        elif name == 'GetProcAddress':
            text = bytes(mu.mem_read(self.arg(1), 32))
            result = self.addr[text[:text.index(b'\0')].decode()]
        elif name == 'GetDC':
            self.calls.append(('GetDC', self.arg(0)))
            mu.mem_write(self.arg(1), struct.pack('<I', HDC if self.have['dc'] else 0))
        elif name == 'GetPixel':
            self.calls.append(('GetPixel', self.arg(0), self.arg(1), self.arg(2)))
            result = PIXEL
        elif name == 'GetTextExtentPoint32A':
            text = bytes(mu.mem_read(self.arg(1), self.arg(2))).decode()
            self.calls.append(('GetTextExtentPoint32A', self.arg(0), text))
            mu.mem_write(self.arg(3), struct.pack('<II', CX, CY))
        elif name == 'ExtTextOutA':
            rect = struct.unpack('<4i', mu.mem_read(self.arg(4), 16))
            text = bytes(mu.mem_read(self.arg(5), self.arg(6))).decode()
            self.calls.append(('ExtTextOutA', self.arg(0), self.arg(1), self.arg(2), self.arg(3), rect, text, self.arg(7)))
        elif name in ('SelectObject', 'SetTextColor', 'SetBkColor', 'SetBkMode', 'ReleaseDC'):
            self.calls.append((name, self.arg(0), self.arg(1)))
        elif name in ('Present', 'After'):
            self.calls.append((name, self.arg(0)))
        elif name == 'RoomDraw':
            self.calls.append(('RoomDraw',))
            mu.reg_write(UC_X86_REG_EAX, 0x11111111)          # the draw's scratch, as the real one leaves it
            return
        elif name == 'RaceSetup':
            self.calls.append(('RaceSetup', mu.reg_read(UC_X86_REG_ESP)))
            return
        mu.reg_write(UC_X86_REG_EAX, result)

    def start(self):
        """The site's call: the return address on the stack, the callee-saved
        registers marked; what the stub did, in order."""
        self.calls = []
        mu = self.mu
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<I', RETURN))
        mu.reg_write(UC_X86_REG_ESP, esp)
        for reg, mark in ((UC_X86_REG_EBX, 0xb0b0b0b0), (UC_X86_REG_ESI, 0x51515151), (UC_X86_REG_EDI, 0xd1d1d1d1), (UC_X86_REG_EBP, 0xb5b5b5b5)):
            mu.reg_write(reg, mark)
        mu.mem_write(self.row['addresses']['ROOMBG'], struct.pack('<I', self.surface if self.have['surface'] else 0))
        mu.emu_start(CODE, RETURN, timeout=2000000, count=5000)
        kept = [mu.reg_read(r) for r in (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)]
        if kept != [0xb0b0b0b0, 0x51515151, 0xd1d1d1d1, 0xb5b5b5b5]:
            raise SystemExit('startingtest: %s: a callee-saved register changed: %s' % (self.build, [hex(k) for k in kept]))
        if not self.calls or self.calls[-1] != ('RaceSetup', esp):
            raise SystemExit('startingtest: %s: the setup not reached with the site\'s stack: %r' % (self.build, self.calls[-3:]))
        if mu.reg_read(UC_X86_REG_ESP) != esp + 4:
            raise SystemExit('startingtest: %s: stack wrong after the setup' % self.build)
        return self.calls[:-1]


def main():
    for build in ('European', 'American', 'Australian', 'Japanese (DigiCube, MediaKite)'):
        m = Machine(build)
        want = [('GetDC', m.surface), ('SelectObject', HDC, FONT), ('SetTextColor', HDC, -1),
                ('GetPixel', HDC, 2, 458), ('SetBkColor', HDC, PIXEL), ('SetBkMode', HDC, 2),
                ('GetTextExtentPoint32A', HDC, LINE),
                ('ExtTextOutA', HDC, (WIDTH - CX) // 2, 456, 2, (0, 456, WIDTH, 456 + CY), LINE, 0),
                ('ReleaseDC', m.surface, HDC), ('RoomDraw',), ('Present', m.d3d), ('After', m.d3d)]
        got = m.start()
        if got != want:
            raise SystemExit('startingtest: %s: the line: %r' % (build, got))
        if m.start() != want or m.loads != 1:
            raise SystemExit('startingtest: %s: the second call, gdi32 loaded %d times' % (build, m.loads))
        for what in ('surface', 'dc'):
            m.have[what] = False
            got = m.start()
            m.have[what] = True
            drew = [c for c in got if c[0] not in ('GetDC',)]
            if drew:
                raise SystemExit('startingtest: %s: without the %s: %r' % (build, what, drew))
        m2 = Machine(build)
        m2.have['gdi32'] = False
        if m2.start() or m2.loads != 1:
            raise SystemExit('startingtest: %s: without gdi32: %r' % (build, m2.calls))
        m2.have['gdi32'] = True
        if m2.start() != want or m2.loads != 2:
            raise SystemExit('startingtest: %s: gdi32 not tried again' % build)
    print('starting: the line centred on the strip\'s row, the row cleared to its colour, the room drawn and presented, then the setup; nothing without gdi32, a surface or a DC; every build')
    return 0


if __name__ == '__main__':
    sys.exit(main())
