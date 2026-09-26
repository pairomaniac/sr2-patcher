#!/usr/bin/env python3
"""Run the borderless patch's two thunks under Unicorn.

    python3 tools/fullwintest.py

FULLWIN_BLOB is mapped as the patcher would place it, with user32 and the
primary surface's Blt replaced by recording stubs. `present` must fill the
bars and blit the picture into a rect of the back buffer's aspect, centred
in the client rect, for 16:9, 16:10, 4:3 and a taller-than-4:3 window, and
leave the stack as the routine it replaces did, return the blit's result
and keep the counter after the blit, with QueryPerformanceCounter
resolved once. A client rect leaving the primary monitor must go through
GDI instead - the back buffer's DC stretched into the window's, the bars
PatBlt - and through the blit when gdi32 is missing.
`sizewindow` must move a WS_POPUP window to the monitor under the cursor
the first time, to the one it is on after that, and leave a framed one
where it is. Needs python3-unicorn; exits 77
with a note when it is missing.
"""
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('fullwintest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESP

BASE, SELF, IMAGE = 0x10000000, 0x16000, 0x20000
STACK, FAKE, RETURN = 0x30000000, 0x40000000, 0xdead0000
HWND, PRIMARY, BACK, SRCRECT, LASTHR = 0x123f8, 0x12550, 0x12554, 0x12410, 0x11fc4
SLOTS = {'GetClientRect': 0xf140, 'ClientToScreen': 0xf13c, 'MoveWindow': 0xf12c,
         'GetWindowLongA': 0xf138, 'LoadLibraryA': 0xf114, 'GetProcAddress': 0xf0ac}
# Stubs and how many argument bytes each pops.
STUBS = {'GetClientRect': 8, 'ClientToScreen': 8, 'MoveWindow': 24, 'GetWindowLongA': 8, 'LoadLibraryA': 4,
         'GetProcAddress': 8, 'Blt': 24, 'GetCursorPos': 4, 'MonitorFromPoint': 12, 'MonitorFromWindow': 8,
         'GetMonitorInfoA': 8, 'QueryPerformanceCounter': 4, 'GetSystemMetrics': 4, 'GetDC': 4,
         'ReleaseDC': 8, 'SetStretchBltMode': 8, 'StretchBlt': 44, 'PatBlt': 24,
         'SurfaceGetDC': 8, 'SurfaceReleaseDC': 8}
MODULES = {'kernel32.dll': 0x77760000, 'user32.dll': 0x77770000, 'gdi32.dll': 0x77780000}
DDBLT_COLORFILL, DDBLT_WAIT = 0x400, 0x1000000


class Machine:
    def __init__(self, client, monitor, style=0x90000000, user32=True, primary=None, gdi32=True):
        """client: (w, h) of the window's client area; monitor: (x, y, w, h);
        style: what GetWindowLongA answers, WS_POPUP|WS_VISIBLE by default;
        user32, gdi32: whether LoadLibraryA finds them; primary: (w, h)
        GetSystemMetrics answers, the monitor's size by default."""
        self.client, self.monitor, self.style, self.calls = client, monitor, style, []
        self.user32, self.gdi32, self.counter = user32, gdi32, 1000
        self.primary = primary or monitor[2:]
        blob = patcher.FULLWIN_BLOB.replace(struct.pack('<I', patcher.FULLWIN_MAGIC), struct.pack('<I', SELF))
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(BASE, IMAGE)
        mu.mem_map(STACK, 0x10000)
        mu.mem_map(FAKE, 0x1000)
        mu.mem_write(BASE + SELF, blob)
        self.addr = {name: FAKE + i * 16 for i, name in enumerate(STUBS)}
        for name, pops in STUBS.items():   # ecx and edx clobbered, as a real callee may
            mu.mem_write(self.addr[name], b'\xb9\xef\xbe\xad\xde\xba\xef\xbe\xad\xde'
                         + ((b'\xc2' + struct.pack('<H', pops)) if pops else b'\xc3'))
        for name, rva in SLOTS.items():
            mu.mem_write(BASE + rva, struct.pack('<I', self.addr[name]))
        vtable, surface = BASE + 0x18000, BASE + 0x18100
        mu.mem_write(BASE + HWND, struct.pack('<I', 0x1234))
        mu.mem_write(BASE + PRIMARY, struct.pack('<I', surface))
        mu.mem_write(surface, struct.pack('<I', vtable))
        mu.mem_write(vtable + 0x14, struct.pack('<I', self.addr['Blt']))
        back = BASE + 0x18200
        mu.mem_write(BASE + BACK, struct.pack('<I', back))
        mu.mem_write(back, struct.pack('<I', vtable))
        mu.mem_write(vtable + 0x44, struct.pack('<I', self.addr['SurfaceGetDC']))
        mu.mem_write(vtable + 0x68, struct.pack('<I', self.addr['SurfaceReleaseDC']))
        self.back = back
        mu.mem_write(BASE + SRCRECT, struct.pack('<4i', 0, 0, 640, 480))
        self.byaddr = {a: n for n, a in self.addr.items()}
        mu.hook_add(UC_HOOK_CODE, self.hook)

    def arg(self, i):
        esp = self.mu.reg_read(UC_X86_REG_ESP)
        return struct.unpack('<I', self.mu.mem_read(esp + 4 + 4 * i, 4))[0]

    def text(self, addr):
        raw = bytes(self.mu.mem_read(addr, 64))
        return raw[:raw.index(b'\0')].decode()

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
        elif name == 'GetWindowLongA':
            result = self.style
        elif name == 'LoadLibraryA':
            module = self.text(self.arg(0))
            self.calls.append(('LoadLibraryA', module))
            missing = (not self.user32 and module == 'user32.dll') or (not self.gdi32 and module == 'gdi32.dll')
            result = 0 if missing else MODULES[module]
        elif name == 'GetProcAddress':
            text = bytes(mu.mem_read(self.arg(1), 32))
            result = self.addr[text[:text.index(b'\0')].decode()]
        elif name == 'GetCursorPos':
            mu.mem_write(self.arg(0), struct.pack('<2i', mx + 5, my + 5))
        elif name == 'MonitorFromPoint':
            self.calls.append(('MonitorFromPoint', self.arg(0), self.arg(1), self.arg(2)))
            result = 0x77
        elif name == 'MonitorFromWindow':
            self.calls.append(('MonitorFromWindow', self.arg(0), self.arg(1)))
            result = 0x77
        elif name == 'GetSystemMetrics':
            result = self.primary[self.arg(0)]
        elif name == 'SurfaceGetDC':
            self.calls.append(('SurfaceGetDC', self.arg(0)))
            mu.mem_write(self.arg(1), struct.pack('<I', 0x5dc))
            result = 0
        elif name == 'SurfaceReleaseDC':
            self.calls.append(('SurfaceReleaseDC', self.arg(0), self.arg(1)))
            result = 0
        elif name == 'GetDC':
            self.calls.append(('GetDC', self.arg(0)))
            result = 0x1dc
        elif name == 'ReleaseDC':
            self.calls.append(('ReleaseDC', self.arg(0), self.arg(1)))
        elif name == 'SetStretchBltMode':
            self.calls.append(('SetStretchBltMode', self.arg(0), self.arg(1)))
        elif name == 'PatBlt':
            self.calls.append(('PatBlt',) + tuple(self.arg(i) for i in range(6)))
        elif name == 'StretchBlt':
            self.calls.append(('StretchBlt',) + tuple(self.arg(i) for i in range(11)))
        elif name == 'GetMonitorInfoA':
            mu.mem_write(self.arg(1), struct.pack('<5i', 40, mx, my, mx + mw, my + mh))
        elif name == 'QueryPerformanceCounter':
            self.counter += 100
            self.calls.append(('QueryPerformanceCounter', self.counter))
            mu.mem_write(self.arg(0), struct.pack('<Q', self.counter))
            result = 1
        elif name == 'Blt':
            self.calls.append(('Blt', struct.unpack('<4i', mu.mem_read(self.arg(1), 16)),
                               self.arg(2), self.arg(4)))
            if self.arg(2) == self.back:
                self.calls[-1] = ('Blt', self.calls[-1][1], 'back', self.arg(4))
            result = 0x887601c2 if self.arg(4) == DDBLT_WAIT else 0   # the picture's blit "fails"
        elif name == 'MoveWindow':
            self.calls.append(('MoveWindow',) + tuple(self.arg(i) for i in range(6)))
        mu.reg_write(UC_X86_REG_EAX, result)

    def present(self, result=0x887601c2):
        """As 0x10004d7b is reached: a 16-byte frame below the return and
        the one argument. result: what it must return and store, the
        blit's failure by default, DD_OK from the GDI path."""
        esp = STACK + 0x8000
        self.mu.mem_write(esp + 0x10, struct.pack('<II', RETURN, 0))
        self.mu.reg_write(UC_X86_REG_ESP, esp)
        self.mu.emu_start(BASE + SELF, RETURN, timeout=2000000)
        if self.mu.reg_read(UC_X86_REG_ESP) != esp + 0x18:
            raise SystemExit('fullwintest: present left the stack wrong')
        if self.mu.reg_read(UC_X86_REG_EAX) != result \
                or struct.unpack('<I', self.mu.mem_read(BASE + LASTHR, 4))[0] != result:
            raise SystemExit('fullwintest: present did not return and store %#x' % result)
        return self.calls

    def take(self):
        calls, self.calls = self.calls, []
        return calls

    def sizewindow(self):
        esp = STACK + 0x8000
        self.mu.mem_write(esp, struct.pack('<7I', RETURN, 0x1234, 0, 0, 650, 500, 1))
        self.mu.reg_write(UC_X86_REG_ESP, esp)
        self.mu.emu_start(BASE + SELF + 5, RETURN, timeout=2000000)
        if self.mu.reg_read(UC_X86_REG_ESP) != esp + 4 + 0x18:
            raise SystemExit('fullwintest: sizewindow left the stack wrong')
        return self.calls


def check_present(client, monitor, picture, bars, primary=None):
    calls = Machine(client, monitor, primary=primary).present()
    fills = [c[1] for c in calls if c[0] == 'Blt' and c[3] == DDBLT_COLORFILL | DDBLT_WAIT]
    blits = [c for c in calls if c[0] == 'Blt' and c[3] == DDBLT_WAIT]
    if blits != [('Blt', picture, 'back', DDBLT_WAIT)] or sorted(fills) != sorted(bars):
        raise SystemExit('fullwintest: %dx%d on %r: %r' % (client + (monitor, calls)))
    if [c for c in calls if c[0] in ('GetDC', 'SurfaceGetDC', 'StretchBlt', 'PatBlt')]:
        raise SystemExit('fullwintest: GDI used inside the primary monitor: %r' % (calls,))


def check_gdi():
    """A client rect leaving the primary monitor: the back buffer's DC
    stretched into the window's, the bars PatBlt, no blit to the primary,
    DD_OK; the blit again with gdi32 missing, or the window straddling
    the monitors."""
    m = Machine((1920, 1080), (2560, 0, 1920, 1080), primary=(2560, 1440))
    calls = [c for c in m.present(result=0) if c[0] not in ('LoadLibraryA', 'QueryPerformanceCounter')]
    want = [('SurfaceGetDC', m.back), ('GetDC', 0x1234), ('SetStretchBltMode', 0x1dc, 3),
            ('PatBlt', 0x1dc, 0, 0, 240, 1080, 0x42), ('PatBlt', 0x1dc, 1680, 0, 240, 1080, 0x42),
            ('StretchBlt', 0x1dc, 240, 0, 1440, 1080, 0x5dc, 0, 0, 640, 480, 0xcc0020),
            ('ReleaseDC', 0x1234, 0x1dc), ('SurfaceReleaseDC', m.back, 0x5dc)]
    if calls != want:
        raise SystemExit('fullwintest: the GDI present: %r' % (calls,))
    m = Machine((1000, 1000), (-1000, 200, 1000, 1000), primary=(2560, 1440))
    calls = [c for c in m.present(result=0) if c[0] in ('PatBlt', 'StretchBlt', 'Blt')]
    want = [('PatBlt', 0x1dc, 0, 0, 1000, 125, 0x42), ('PatBlt', 0x1dc, 0, 875, 1000, 125, 0x42),
            ('StretchBlt', 0x1dc, 0, 125, 1000, 750, 0x5dc, 0, 0, 640, 480, 0xcc0020)]
    if calls != want:
        raise SystemExit('fullwintest: the GDI present left of the primary: %r' % (calls,))
    calls = Machine((640, 480), (2400, 100, 640, 480), primary=(2560, 1440)).present(result=0)
    if [c for c in calls if c[0] == 'Blt'] or [c for c in calls if c[0] == 'StretchBlt'] \
            != [('StretchBlt', 0x1dc, 0, 0, 640, 480, 0x5dc, 0, 0, 640, 480, 0xcc0020)]:
        raise SystemExit('fullwintest: a window straddling the monitors: %r' % (calls,))
    calls = Machine((1920, 1080), (2560, 0, 1920, 1080), primary=(2560, 1440), gdi32=False).present()
    if [c for c in calls if c[0] == 'Blt' and c[3] == DDBLT_WAIT] != [('Blt', (2800, 0, 4240, 1080), 'back', DDBLT_WAIT)] \
            or [c for c in calls if c[0] in ('GetDC', 'SurfaceGetDC')]:
        raise SystemExit('fullwintest: the blit without gdi32: %r' % (calls,))


def check_stamp():
    """The counter after the picture's blit kept in the annex,
    QueryPerformanceCounter and the GDI set resolved once."""
    m = Machine((1920, 1080), (0, 0, 1920, 1080))
    calls = list(m.present())
    m.take()
    calls += m.present()
    if [c[1] for c in calls if c[0] == 'LoadLibraryA'] != ['kernel32.dll', 'user32.dll', 'gdi32.dll']:
        raise SystemExit('fullwintest: the counter and the GDI set were not resolved once: %r' % calls)
    order = [c[0] for c in calls if c[0] in ('Blt', 'QueryPerformanceCounter')]
    if order[-2:] != ['Blt', 'QueryPerformanceCounter']:
        raise SystemExit('fullwintest: the stamp is not after the blit: %r' % order)
    counted = [c[1] for c in calls if c[0] == 'QueryPerformanceCounter']
    stamp = struct.unpack('<I', m.mu.mem_read(BASE + SELF + patcher.fullwin_stamp(), 4))[0]
    if len(counted) != 2 or stamp != counted[-1]:
        raise SystemExit('fullwintest: the stamp: %r after %r' % (stamp, counted))


def main():
    check_present((2560, 1440), (0, 0, 2560, 1440), (320, 0, 2240, 1440),
                  [(0, 0, 320, 1440), (2240, 0, 2560, 1440)])
    check_present((1920, 1200), (1920, 0, 1920, 1200), (2080, 0, 3680, 1200),
                  [(1920, 0, 2080, 1200), (3680, 0, 3840, 1200)], primary=(3840, 1200))
    check_present((640, 480), (100, 50, 640, 480), (100, 50, 740, 530), [], primary=(1920, 1080))
    check_present((1000, 1000), (0, 0, 1000, 1000), (0, 125, 1000, 875),
                  [(0, 0, 1000, 125), (0, 875, 1000, 1000)])
    check_stamp()
    check_gdi()
    # an empty source rect: no blit, no bars, no division, DD_OK
    m = Machine((1920, 1080), (0, 0, 1920, 1080))
    m.mu.mem_write(BASE + SRCRECT, struct.pack('<4i', 0, 0, 0, 0))
    esp = STACK + 0x8000
    m.mu.mem_write(esp + 0x10, struct.pack('<II', RETURN, 0))
    m.mu.reg_write(UC_X86_REG_ESP, esp)
    m.mu.emu_start(BASE + SELF, RETURN, timeout=2000000)
    if m.mu.reg_read(UC_X86_REG_ESP) != esp + 0x18 or m.mu.reg_read(UC_X86_REG_EAX) != 0 \
            or [c for c in m.calls if c[0] == 'Blt']:
        raise SystemExit('fullwintest: an empty source rect: %r' % (m.calls,))
    m = Machine((640, 480), (2560, 0, 1920, 1080))
    calls = [c for c in m.sizewindow() if c[0] != 'LoadLibraryA']
    if calls != [('MonitorFromPoint', 2565, 5, 2), ('MoveWindow', 0x1234, 2560, 0, 1920, 1080, 1)]:
        raise SystemExit('fullwintest: sizewindow: %r' % calls)
    m.take()
    calls = [c for c in m.sizewindow() if c[0] != 'LoadLibraryA']
    if calls != [('MonitorFromWindow', 0x1234, 2), ('MoveWindow', 0x1234, 2560, 0, 1920, 1080, 1)]:
        raise SystemExit('fullwintest: sizewindow placed again: %r' % calls)
    calls = [c for c in Machine((640, 480), (2560, 0, 1920, 1080), style=0x10cf0000).sizewindow() if c[0] != 'LoadLibraryA']
    if calls:
        raise SystemExit('fullwintest: sizewindow moved a framed window: %r' % calls)
    print('fullwin: present letterboxes at four aspects, through GDI off the primary monitor, and keeps '
          'the counter after the blit; sizewindow covers the monitor, leaves a framed window alone')
    return 0


if __name__ == '__main__':
    sys.exit(main())
