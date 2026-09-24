#!/usr/bin/env python3
"""Run the widescreen stubs under Unicorn.

    python3 tools/widetest.py

wide.asm (the European exe's, with a stubbed SR2.CFG): the mode check
takes a wide size from the file and asks for a re-init once, the size
setter applies it for mode 0 and keeps 800x600 for mode 1. widegl.asm:
SetViewport scales a 640x480 rect and its centre and leaves a full-size
one alone, SetPerspective widens the angle for the aspect and leaves it
at 4:3; the trace lines come out as documented. wide2d.asm: a quad in
640x480 terms comes out scaled and centred in a 1920x1080 buffer, a
full-width one stretched, one at the left edge drawn out to it with its
texture coordinate shifted, a 640x480 buffer or another FVF untouched,
and the lists likewise; the texture create's entry marks a texture as
a picture, a black one or nothing, and a picture's strip at the edge
gets the picture stretched into the side area beside it, sixteen added
passes across at their share of the colour; the device's viewport for
the countdown is scaled into the 4:3 box with its fractions; with the
HUD flag set a draw in the left or right part of the 640 moves out to
a 16:9 frame's edge, and the exe's walk entry sets that flag, and the
bounds of the HUD's own draws beside it, around a
HUD callback through a fake MGameD3D.
Needs python3-unicorn; exits 77 with a note when it is missing.
"""
import math
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('widetest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EBP,
                               UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EFLAGS)

PASSES, PASSSHARE, BLURPX = 16, 17, 20      # the passes a bar is drawn in, each one's share of the colour,
DIM = 0x66                                  # the 640's pixels they spread across, and the bar's brightness
KPICTURE, KBLACK = 1, 2             # what texload makes of a texture: a picture, or one all but black
DARKPIX, MOSTLY = 6, 3              # a pixel this dark is black, and a texture this many quarters of them
ROW = patcher.BUILDS['European']
CODE, STACK, STUBS, VTABLE, RECTS, VERTS = 0x5a0000, 0x3000000, 0x600000, 0x610000, 0x620000, 0x4000000
PIXELS = VERTS + 0x20000                     # a 640x480 16-bit surface's pixels, for the lobby's background
ZF = 1 << 6


def exe_stub():
    """WIDE_BLOB placed with its table, the exe's globals and two kernel32
    stubs around it; the profile answer is settable."""
    blob = patcher.exe_blob(patcher.WIDE_BLOB, 'European') + patcher.resolution_table()
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr in (CODE, STUBS, VTABLE, RECTS, 0x4d5000, 0x495000, 0x50a000):
        mu.mem_map(addr, 0x1000)
    mu.mem_map(STACK, 0x10000)
    mu.mem_write(CODE, blob)
    slots = ROW['slots']
    mu.mem_write(slots['GetModuleFileNameA'], struct.pack('<I', STUBS))
    mu.mem_write(slots['GetPrivateProfileStringA'], struct.pack('<I', STUBS + 0x10))
    mu.mem_write(STUBS, b'\xc2\x0c\x00')                # ret 12
    mu.mem_write(STUBS + 0x10, b'\xc2\x18\x00')         # ret 24
    mu.mem_write(VTABLE + 0x114, struct.pack('<I', STUBS + 0x20))
    mu.mem_write(STUBS + 0x20, b'\xc2\x10\x00')         # SetPerspective(this, angle, near, far): ret 16
    state = {'answer': b'', 'fov': None}

    def stub(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        args = struct.unpack('<6I', mu.mem_read(esp + 4, 24))
        if address == STUBS:
            mu.mem_write(args[1], b'C:\\game\\SEGA RALLY 2.exe\0')
        elif address == STUBS + 0x10:
            assert bytes(mu.mem_read(args[0], 8)) == b'Display\0' and bytes(mu.mem_read(args[1], 11)) == b'Resolution\0'
            assert bytes(mu.mem_read(args[5], 16)) == b'C:\\game\\SR2.CFG\0'
            mu.mem_write(args[3], state['answer'] + b'\0')
        elif address == STUBS + 0x20:
            state['fov'] = args[1]
            state['args'] = args[:4]
        mu.reg_write(UC_X86_REG_EAX, 0)

    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x30)

    def call(entry, *args, eax=0, ecx=0, edx=0, retaddr=0xDEAD0000):
        """The entry, with the stack as the site's function has it: args
        from its own return address up. ebx as set before."""
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<I', retaddr) + b''.join(struct.pack('<I', a) for a in args))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EAX, eax)
        mu.reg_write(UC_X86_REG_ECX, ecx)
        mu.reg_write(UC_X86_REG_EDX, edx)
        mu.emu_start(CODE + entry, retaddr, count=100000)
        return mu
    return mu, call, state


def size(mu):
    return tuple(struct.unpack('<I', mu.mem_read(ROW['addresses'][k], 4))[0] for k in ('WIDTH', 'HEIGHT'))


def angle(hfov, w, h):
    return round(2 * math.atan(math.tan(hfov / 2) * (w / h) / (4 / 3)) * 65536 / (2 * math.pi))


def test_gl():
    """widegl.asm over a stand-in MGameD3D's size dwords, found through a
    stubbed GetModuleHandleA; each entry with the stack as the method
    has it, the method's epilogue standing in for its body."""
    base, rva, d3d = 0x10000000, 0x20000, 0x20000000
    blob = patcher.WIDEGL_BLOB.replace(struct.pack('<I', patcher.FULLWIN_MAGIC), struct.pack('<I', rva))
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(base, 0x30000)
    mu.mem_map(d3d, 0x13000)
    mu.mem_map(STACK, 0x10000)
    mu.mem_map(RECTS, 0x1000)
    mu.mem_map(STUBS, 0x1000)
    mu.mem_write(base + rva, blob)
    for site, length in zip((0x37c0, 0x3870, 0x39e0), (10, 9, 9)):
        mu.mem_write(base + site + length, b'\x8b\xe5\x5d\xc3')     # the method resumes: its epilogue, back to the test
    # the projection's body, called from the fourth entry with eax the point and ecx out: the point copied to out, ret 0xc
    mu.mem_write(base + 0x3a88, bytes.fromhex('8b1089118b5004895104c20c00'))
    # the parameter getter's body, after the prologue the thunk did: out = the dword at PARAMS + id * 4; the epilogue, ret 0xc
    mu.mem_write(base + 0x33f9, bytes.fromhex('8b450c8b5510') + b'\x8b\x04\x85' + struct.pack('<I', RECTS + 0x100)
                 + bytes.fromhex('89028be55dc20c00'))
    # unproject's body, after the two loads: out = the point eax points at, as it is; ret 0x10
    mu.mem_write(base + 0x3ae8, bytes.fromhex('8b1089118b5004895104c21000'))
    mu.mem_write(STUBS + 0x40, b'\xc2\x04\x00')                      # GetModuleHandleA
    mu.mem_write(base + 0x1008c, struct.pack('<I', STUBS + 0x40))
    found = {'d3d': False}

    def module(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        name = bytes(mu.mem_read(struct.unpack('<I', mu.mem_read(esp + 4, 4))[0], 20)).split(b'\0')[0]
        if name != b'MGameD3D.dll':
            raise SystemExit('widetest: GetModuleHandleA asked for %r' % name)
        found['d3d'] = True
        mu.reg_write(UC_X86_REG_EAX, d3d)
    mu.hook_add(UC_HOOK_CODE, module, begin=STUBS + 0x40, end=STUBS + 0x43)

    def size(w, h):
        mu.mem_write(d3d + 0x123fc, struct.pack('<II', int(w), int(h)))

    def call(entry, *args, retaddr=0x0046c04f, above=0x00421819):
        """The entry as called from the exe's wrapper (a return in the
        exe's image, the wrapper's own caller's above its three saved
        registers) unless retaddr or above says a DLL - relocated, so
        anywhere else."""
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<I', retaddr) + b''.join(struct.pack('<I', a) for a in args))
        mu.mem_write(esp + 4 + 4 * len(args), struct.pack('<IIII', 0, 0, 0, above))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EBX, 0xB0B0)
        mu.reg_write(UC_X86_REG_EBP, 0xB1B1)
        mu.emu_start(base + rva + entry, retaddr, count=100000)
        # the prologue re-done and the epilogue run: ebx and ebp as they were, the stack at the return
        # the prologue re-done and the epilogue run: ebx and ebp as they were, the stack at the return
        if mu.reg_read(UC_X86_REG_EBX) != 0xB0B0 or mu.reg_read(UC_X86_REG_EBP) != 0xB1B1 or mu.reg_read(UC_X86_REG_ESP) != esp + 4:
            raise SystemExit('widetest: a MGameGL entry re-did its prologue wrong')
        return struct.unpack('<5I', mu.mem_read(esp, 20))

    size(1920.0, 1080.0)
    mu.mem_write(RECTS, struct.pack('<4i', 0, 256, 640, 480))
    _, _, rect, cx, cy = call(0, 0x7715, RECTS, 320, 240)
    got = struct.unpack('<4i', mu.mem_read(rect, 16))
    if got != (0, 576, 1920, 1080) or (cx, cy) != (960, 540) or rect == RECTS:
        raise SystemExit('widetest: SetViewport gave %r %r' % (got, (cx, cy)))
    mu.mem_write(RECTS, struct.pack('<4i', 0, 0, 1920, 1080))
    _, _, rect, cx, cy = call(0, 0x7715, RECTS, 960, 540)
    if rect != RECTS or (cx, cy) != (960, 540):
        raise SystemExit('widetest: a full-size viewport changed')
    # a centre off the middle - the transmission select's - goes by height and the bar, not the width
    mu.mem_write(RECTS, struct.pack('<4i', 0, 0, 640, 480))
    _, _, rect, cx, cy = call(0, 0x7715, RECTS, 168, 266)
    got = struct.unpack('<4i', mu.mem_read(rect, 16))
    if got != (0, 0, 1920, 1080) or (cx, cy) != (240 + 378, 598) or rect == RECTS:
        raise SystemExit('widetest: an off-centre viewport gave %r %r' % (got, (cx, cy)))
    # the countdown's zoom: a 640x480 frame doubled about its centre, still 640x480 terms
    mu.mem_write(RECTS, struct.pack('<4i', -320, -240, 960, 720))
    _, _, rect, cx, cy = call(0, 0x7715, RECTS, 320, 240)
    got = struct.unpack('<4i', mu.mem_read(rect, 16))
    if got != (-960, -540, 2880, 1620) or (cx, cy) != (960, 540):
        raise SystemExit('widetest: a zoomed viewport gave %r %r' % (got, (cx, cy)))
    # a window narrower than the 640 - the ending's replay - goes into the 4:3 box as the 2D does, and the angle
    # stays 4:3 while it is set; the next full rect puts both back
    mu.mem_write(RECTS, struct.pack('<4i', 351, 222, 607, 415))
    _, _, rect, cx, cy = call(0, 0x7715, RECTS, 479, 318)
    got = struct.unpack('<4i', mu.mem_read(rect, 16))
    if got != (240 + 790, 500, 240 + 1366, 934) or (cx, cy) != (240 + 1078, 716):
        raise SystemExit('widetest: a window viewport gave %r %r' % (got, (cx, cy)))
    _, _, a, _, _ = call(5, 0x7715, 15360, 0x3f000000, 0x43700000)
    if a != 15360:
        raise SystemExit('widetest: SetPerspective widened the angle for a window: %d' % a)
    # the ending's zoom down to the window, about the window's centre: wider than 640 but off the middle, a window
    mu.mem_write(RECTS, struct.pack('<4i', 100, 50, 858, 586))
    _, _, rect, cx, cy = call(0, 0x7715, RECTS, 479, 318)
    got = struct.unpack('<4i', mu.mem_read(rect, 16))
    if got != (240 + 225, 112, 240 + 1930, 1318):
        raise SystemExit('widetest: a zoom about a window gave %r' % (got,))
    mu.mem_write(RECTS, struct.pack('<4i', 0, 0, 640, 480))
    call(0, 0x7715, RECTS, 320, 240)
    # a screen DLL's 640x480, direct or through the exe's wrapper: the whole picture like the exe's
    for where in ({'retaddr': 0x03b5550f}, {'above': 0x03b4a46f}):
        mu.mem_write(RECTS, struct.pack('<4i', 0, 0, 640, 480))
        _, _, rect, cx, cy = call(0, 0x7715, RECTS, 320, 240, **where)
        got = struct.unpack('<4i', mu.mem_read(rect, 16))
        if got != (0, 0, 1920, 1080) or (cx, cy) != (960, 540):
            raise SystemExit('widetest: a DLL\'s viewport gave %r %r' % (got, (cx, cy)))
    _, _, a, near, far = call(5, 0x7715, 15360, 0x3f000000, 0x43700000)
    want = angle(84.375 * math.pi / 180, 1920, 1080)
    if abs(a - want) > 1 or (near, far) != (0x3f000000, 0x43700000):
        raise SystemExit('widetest: SetPerspective gave %d, expected %d' % (a, want))
    size(1600.0, 1200.0)
    _, _, a, _, _ = call(5, 0x7715, 15360, 0x3f000000, 0x43700000)
    if a != 15360:
        raise SystemExit('widetest: SetPerspective changed a 4:3 angle')
    # the centre alone - the name entry's (320, 240) - scaled as the viewport's is
    size(1920.0, 1080.0)
    _, _, cx, cy, _ = call(10, 0x7715, 320, 240, 0)
    if (cx, cy) != (960, 540):
        raise SystemExit('widetest: SetCentre gave %r' % ((cx, cy),))
    _, _, cx, cy, _ = call(10, 0x7715, 168, 266, 0)
    if (cx, cy) != (240 + 378, 598):
        raise SystemExit('widetest: an off-centre SetCentre gave %r' % ((cx, cy),))

    def project(x, y, cx, cy):
        """The fourth entry over the stand-in body: what the method would have written, (x, y) about the centre it holds,
        converted; the stdcall return checked."""
        mu.mem_write(base + 0x128d0, struct.pack('<f', cx))
        mu.mem_write(base + 0x128cc, struct.pack('<f', cy))
        mu.mem_write(RECTS + 0x40, struct.pack('<fff', x, y, 0.5))
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<4I', 0x0046c04f, 0x7715, RECTS + 0x80, RECTS + 0x40))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EBX, 0xB0B0)
        mu.reg_write(UC_X86_REG_EBP, 0xB1B1)
        mu.emu_start(base + rva + 15, 0x0046c04f, count=100000)
        if mu.reg_read(UC_X86_REG_EBX) != 0xB0B0 or mu.reg_read(UC_X86_REG_EBP) != 0xB1B1 or mu.reg_read(UC_X86_REG_ESP) != esp + 16:
            raise SystemExit('widetest: the projection entry returned wrong')
        return struct.unpack('<ff', mu.mem_read(RECTS + 0x80, 8))
    # 5120x1440: the 2D's scale 3 and bar 1600, the centre (320, 240) at (2560, 720); an offset of 30 in the method's
    # 640-wide units is 240 real pixels, 80 in 640x480 terms
    size(5120.0, 1440.0)
    got = project(2560 + 30, 720 - 15, 2560, 720)
    if got != (400.0, 200.0):
        raise SystemExit('widetest: a projection at 5120x1440 gave %r' % (got,))
    size(800.0, 600.0)
    got = project(450, 280, 400, 300)
    if got != (370.0, 220.0):
        raise SystemExit('widetest: a projection at 800x600 gave %r' % (got,))
    size(640.0, 480.0)
    got = project(350, 225, 320, 240)
    if got != (350.0, 225.0):
        raise SystemExit('widetest: a projection changed at 640x480')

    def param(i, value, cx, cy):
        """The fifth entry over the stand-in body: the value the method would give for id i, converted; ints for 7 and 8."""
        mu.mem_write(base + 0x128d0, struct.pack('<f', cx))
        mu.mem_write(base + 0x128cc, struct.pack('<f', cy))
        mu.mem_write(RECTS + 0x100 + i * 4, struct.pack('<f' if i == 4 else '<i', value))
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<4I', 0x0046c04f, 0x7715, i, RECTS + 0x80))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EBX, 0xB0B0)
        mu.reg_write(UC_X86_REG_EBP, 0xB1B1)
        mu.emu_start(base + rva + 20, 0x0046c04f, count=100000)
        if mu.reg_read(UC_X86_REG_EBX) != 0xB0B0 or mu.reg_read(UC_X86_REG_EBP) != 0xB1B1 or mu.reg_read(UC_X86_REG_ESP) != esp + 16:
            raise SystemExit('widetest: the parameter entry returned wrong')
        return struct.unpack('<f' if i == 4 else '<i', mu.mem_read(RECTS + 0x80, 4))[0]

    def unproject(x, y, cx, cy):
        """The sixth entry into the stand-in body: the point as the method gets it, converted."""
        mu.mem_write(base + 0x128d0, struct.pack('<f', cx))
        mu.mem_write(base + 0x128cc, struct.pack('<f', cy))
        mu.mem_write(RECTS + 0x40, struct.pack('<fff', x, y, 7.0))
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<5I', 0x0046c04f, 0x7715, RECTS + 0x80, RECTS + 0x40, 0x42480000))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EBX, 0xB0B0)
        mu.reg_write(UC_X86_REG_EBP, 0xB1B1)
        mu.emu_start(base + rva + 25, 0x0046c04f, count=100000)
        if mu.reg_read(UC_X86_REG_EBX) != 0xB0B0 or mu.reg_read(UC_X86_REG_EBP) != 0xB1B1 or mu.reg_read(UC_X86_REG_ESP) != esp + 20:
            raise SystemExit('widetest: the unproject entry returned wrong')
        return struct.unpack('<ff', mu.mem_read(RECTS + 0x80, 8))
    # 5120x1440: the centre (2560, 720) answered as (320, 240), the focal of the widened angle by 8/3; the same point
    # as project's, (400, 200) in 640x480 terms, goes in as (2590, 705); the other ids untouched
    size(5120.0, 1440.0)
    got = param(7, 2560, 2560, 720), param(8, 720, 2560, 720), param(4, 132.4, 2560, 720), param(5, 640, 2560, 720)
    if got[:2] != (320, 240) or abs(got[2] - 132.4 * 8 / 3) > 0.01 or got[3] != 640:
        raise SystemExit('widetest: the parameters at 5120x1440 came out %r' % (got,))
    got = unproject(400, 200, 2560, 720)
    if got[:2] != (2590.0, 705.0):
        raise SystemExit('widetest: unproject at 5120x1440 gave %r' % (got,))
    size(800.0, 600.0)
    got = param(7, 400, 400, 300), param(8, 300, 400, 300), param(4, 353.07, 400, 300)
    if got[:2] != (320, 240) or abs(got[2] - 353.07) > 0.01:
        raise SystemExit('widetest: the parameters at 800x600 came out %r' % (got,))
    if unproject(370, 220, 400, 300)[:2] != (450.0, 280.0):
        raise SystemExit('widetest: unproject at 800x600 gave %r' % (unproject(370, 220, 400, 300),))
    size(640.0, 480.0)
    if (param(7, 320, 320, 240), param(8, 240, 320, 240)) != (320, 240) or unproject(350, 225, 320, 240)[:2] != (350.0, 225.0):
        raise SystemExit('widetest: a parameter or unproject changed at 640x480')
    mu.mem_write(RECTS, struct.pack('<4i', 0, 0, 640, 480))
    _, _, rect, cx, cy = call(0, 0x7715, RECTS, 320, 240)
    if rect != RECTS or (cx, cy) != (320, 240):
        raise SystemExit('widetest: a viewport changed at 640x480')
    _, _, cx, cy, _ = call(10, 0x7715, 320, 240, 0)
    if (cx, cy) != (320, 240):
        raise SystemExit('widetest: a centre changed at 640x480')
    if not found['d3d']:
        raise SystemExit('widetest: MGameD3D never looked for')
    # the trace: the flag set as gltrace sets it, kernel32 stubbed
    at = blob.find(b'GLTRACE\0') + 8
    mu.mem_write(base + rva + at, struct.pack('<I', 1))
    mu.mem_write(STUBS, b'\xc2\x04\x00' + b'\x90' * 13 + b'\xc2\x08\x00' + b'\x90' * 13 + b'\xc2\x04\x00')
    mu.mem_write(base + 0x100ec, struct.pack('<I', STUBS))
    mu.mem_write(base + 0x10088, struct.pack('<I', STUBS + 0x10))
    lines = []

    def stub(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        arg = struct.unpack('<I', mu.mem_read(esp + 4, 4))[0]
        if address == STUBS + 0x20:
            lines.append(bytes(mu.mem_read(arg, 128)).split(b'\0')[0].decode())
        mu.reg_write(UC_X86_REG_EAX, STUBS + 0x20 if address == STUBS + 0x10 else 0x1234)
    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x30)
    size(1920.0, 1080.0)
    mu.mem_write(base + 0x128d4, struct.pack('<ff', 480.0, 640.0))    # MGameGL's own, stale, as traced
    mu.mem_write(RECTS, struct.pack('<4i', 0, 0, 640, 480))
    call(0, 0x7715, RECTS, 320, 240)
    call(5, 0x7715, 15360, 0x3f000000, 0x43700000)
    if lines != ['sr2 vp 00000000 00000000 00000280 000001e0 00000140 000000f0 0046c04f 00421819 ',
                 'sr2 vp> 00000000 00000000 00000780 00000438 000003c0 0000021c ',
                 'sr2 fov 00003c00 44f00000 44870000 %08x ' % want]:
        raise SystemExit('widetest: the trace said %r' % (lines,))


def test_exe():
    mu, call, state = exe_stub()
    mode = ROW['addresses']['MODE']
    # the mode check: no file, no wide size, mode 0 equal to MODE 0
    call(0, 0, 0xCAFE0000, 0)                           # the pushed esi, the setter's return, the mode
    if not mu.reg_read(UC_X86_REG_EFLAGS) & ZF:
        raise SystemExit('widetest: a re-init asked for with no wide size')
    state['answer'] = b'1920x1080'
    call(0, 0, 0xCAFE0000, 0)
    if mu.reg_read(UC_X86_REG_EFLAGS) & ZF:
        raise SystemExit('widetest: no re-init asked for with a new wide size')
    call(5, eax=0)                                      # setsize for mode 0
    if size(mu) != (1920, 1080):
        raise SystemExit('widetest: the wide size not applied: %r' % (size(mu),))
    call(0, 0, 0xCAFE0000, 0)
    if not mu.reg_read(UC_X86_REG_EFLAGS) & ZF:
        raise SystemExit('widetest: a re-init asked for with the wide size in force')
    mu.mem_write(mode, struct.pack('<I', 1))
    call(0, 0, 0xCAFE0000, 1)
    if not mu.reg_read(UC_X86_REG_EFLAGS) & ZF:
        raise SystemExit('widetest: a re-init asked for with mode 1 unchanged')
    # mode 1 keeps 800x600 and clears the wide size; a stock or odd size in the file counts for nothing
    call(5, eax=1)
    if size(mu) != (800, 600):
        raise SystemExit('widetest: mode 1 not 800x600: %r' % (size(mu),))
    for answer in (b'800x600', b'1234x999', b'', b'1920'):
        state['answer'] = answer
        mu.mem_write(mode, struct.pack('<I', 0))
        call(0, 0, 0xCAFE0000, 0)
        call(5, eax=0)
        if size(mu) != (640, 480):
            raise SystemExit('widetest: %r taken as a wide size' % answer)
    # the screen change: the setter with the front end's mode once the file's size differs from the one in force
    settings, setter = ROW['addresses']['SETTINGS'], ROW['addresses']['SETTER']
    mu.mem_map(setter & ~0xfff, 0x1000)
    mu.mem_write(setter, b'\xc3')
    mu.mem_write(settings, struct.pack('<I', RECTS + 0x100))
    mu.mem_write(RECTS + 0x150, struct.pack('<I', 1))
    calls = []

    def setter_stub(mu, address, size_, user):
        calls.append(struct.unpack('<I', mu.mem_read(mu.reg_read(UC_X86_REG_ESP) + 4, 4))[0])
    mu.hook_add(UC_HOOK_CODE, setter_stub, begin=setter, end=setter + 1)

    def screen(answer):
        state['answer'] = answer
        mu.reg_write(UC_X86_REG_EBX, 0xB0B0B0B0)
        mu.reg_write(UC_X86_REG_EBP, 0xB1B1B1B1)
        call(10)
        if (mu.reg_read(UC_X86_REG_EAX), mu.reg_read(UC_X86_REG_ECX), mu.reg_read(UC_X86_REG_EBX), mu.reg_read(UC_X86_REG_EBP),
                mu.reg_read(UC_X86_REG_ESP)) != (RECTS + 0x100, 1, 0xB0B0B0B0, 0xB1B1B1B1, STACK + 0x8004):
            raise SystemExit('widetest: the screen entry resumed wrong')
    screen(b'640x480')
    screen(b'1920x1080')
    screen(b'1920x1080')
    if calls != [1, 1]:
        raise SystemExit('widetest: the screen entry called the setter %r' % (calls,))
    call(5, eax=0)                                      # the setter applies it
    screen(b'1920x1080')
    screen(b'1600x900')
    if calls != [1, 1, 1]:
        raise SystemExit('widetest: the screen entry called the setter %r' % (calls,))
    # the walk entry: the flag after wide2d's marker in a fake MGameD3D, found through the device object, is set
    # for a callback in the HUD's range and left set (the present clears it); a callback outside it sees it as it
    # was; the callback gets its element and every register comes back
    dll, gamed3d, resume = 0x700000, ROW['addresses']['GAMED3D'], ROW['addresses']['WALKRESUME']
    mu.mem_map(dll, 0x18000)
    mu.mem_map(gamed3d & ~0xfff, 0x1000)
    mu.mem_map(resume & ~0xfff, 0x1000)
    mu.mem_write(dll, b'MZ')
    mu.mem_write(dll + 0x3c, struct.pack('<I', 0x80))
    mu.mem_write(dll + 0x80 + 0x50, struct.pack('<I', 0x18000))
    mu.mem_write(dll + 0xf5d4 + 0xb4, struct.pack('<I', dll + 0x5120))
    mu.mem_write(dll + 0x17100, b'HUDFRAME' + struct.pack('<I', 7))
    mu.mem_write(RECTS + 0x200, struct.pack('<I', dll + 0xf5d4))
    mu.mem_write(gamed3d, struct.pack('<I', RECTS + 0x200))
    mu.mem_write(resume, b'\xc3')                       # the walker after the site: return to the test
    seen = []

    def callback(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        seen.append((address, struct.unpack('<I', mu.mem_read(esp + 4, 4))[0], struct.unpack('<I', mu.mem_read(dll + 0x17108, 4))[0]))
    callbacks = (ROW['addresses']['HUDLO'], ROW['addresses']['HUDHI'], ROW['addresses']['HUDHI'] + 0x10)
    for page in sorted(set(cb & ~0xfff for cb in callbacks)):
        mu.mem_map(page, 0x1000)
    for cb in callbacks:
        mu.mem_write(cb, b'\xc3')
        mu.hook_add(UC_HOOK_CODE, callback, begin=cb, end=cb + 1)
    for cb, want in zip(callbacks, (1, 1, 0)):
        seen.clear()
        mu.mem_write(dll + 0x17108, struct.pack('<I', 0))
        mu.reg_write(UC_X86_REG_EBX, 0xB0B0B0B0)
        mu.reg_write(UC_X86_REG_EDI, 0xB2B2B2B2)
        call(15, eax=0xE1E1E1E1, ecx=cb, retaddr=resume)
        after = struct.unpack('<I', mu.mem_read(dll + 0x17108, 4))[0]
        if seen != [(cb, 0xE1E1E1E1, want)] or after != want:
            raise SystemExit('widetest: the walk entry around %#x: %r, flag after %d' % (cb, seen, after))
        bounds = struct.unpack('<II', mu.mem_read(dll + 0x1710c, 8))
        if want and bounds != (ROW['addresses']['HUDDRAW'], ROW['addresses']['HUDHI']):
            raise SystemExit('widetest: the walk entry left the HUD draw bounds %r' % (bounds,))
        if (mu.reg_read(UC_X86_REG_EBX), mu.reg_read(UC_X86_REG_EDI), mu.reg_read(UC_X86_REG_ESP)) != (0xB0B0B0B0, 0xB2B2B2B2, STACK + 0x8000):    # reached by a jump, not a call
            raise SystemExit('widetest: the walk entry resumed wrong')


VERTEX = '<4f2I2f'


def test_2d():
    base, rva = 0x10000000, 0x20000
    blob = patcher.WIDE2D_BLOB.replace(struct.pack('<I', patcher.FULLWIN_MAGIC), struct.pack('<I', rva))
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(base, 0x100000)                      # the blob, whose grid of colours is the bulk of it
    mu.mem_map(STACK, 0x10000)
    mu.mem_map(VERTS, 0x20000 + 640 * 480 * 2 * 2)   # the background's pixels, then the lobby surface's
    mu.mem_write(base + rva, blob)
    for site, length in zip(patcher.WIDE2D_SITES, (6, 6, 10, 10, 10, 10, 9, 8, 13)):
        mu.mem_write(base + site + length, b'\xc3')     # the draw resumes: return to the test
    mu.mem_write(base + 0x4d58, b'\x83\xc4\x10\xc3')   # the present resumes: add esp, 0x10; ret
    mu.mem_write(base + 0x1240c, struct.pack('<I', 0xF0F0F0F0))
    mu.mem_write(base + 0x11220, struct.pack('<I', 0x18))
    mu.mem_write(base + 0x12764, struct.pack('<I', 0xD3D3D3D3))
    device, vtable = VERTS + 0x10000, VERTS + 0x10100          # the draw's `this`, with +0xf8, +0xac and +0xb4 stubbed
    mu.mem_write(device, struct.pack('<I', vtable))
    mu.mem_write(vtable + 0xf8, struct.pack('<I', VERTS + 0x10200))
    mu.mem_write(vtable + 0xac, struct.pack('<I', VERTS + 0x10210))
    mu.mem_write(vtable + 0xb4, struct.pack('<I', VERTS + 0x10220))
    mu.mem_write(vtable + 0xe8, struct.pack('<I', VERTS + 0x10230))     # alpha blending on or off
    mu.mem_write(vtable + 0xfc, struct.pack('<I', VERTS + 0x10240))     # its filtering
    mu.mem_write(vtable + 0xec, struct.pack('<I', VERTS + 0x10250))     # and its blend factors, two arguments
    for at in (0x10200, 0x10210, 0x10220, 0x10230, 0x10240):
        mu.mem_write(VERTS + at, b'\xc2\x08\x00')
    mu.mem_write(VERTS + 0x10250, b'\xc2\x0c\x00')
    wraps, calls = [], []

    def setwrap(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        wraps.append(struct.unpack('<II', mu.mem_read(esp + 4, 8)))
    mu.hook_add(UC_HOOK_CODE, setwrap, begin=VERTS + 0x10200, end=VERTS + 0x10203)

    def method(mu, address, size_, user):
        """The texture select and the quad draw as the bar calls them: the texture's number, or the quad's vertices."""
        esp = mu.reg_read(UC_X86_REG_ESP)
        this, arg = struct.unpack('<Ii', mu.mem_read(esp + 4, 8))
        if address == VERTS + 0x10210:
            calls.append(('texture', this, arg))
            mu.mem_write(base + 0x11224, struct.pack('<i', arg))
        else:
            calls.append(('quad', this, [(lambda v: (v[0], v[1], v[2], v[3], v[4], v[6], v[7]))(struct.unpack(VERTEX, mu.mem_read(arg + i, 32))) for i in range(0, 128, 32)]))
    mu.hook_add(UC_HOOK_CODE, method, begin=VERTS + 0x10210, end=VERTS + 0x10223)

    def blending(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        this, arg = struct.unpack('<Ii', mu.mem_read(esp + 4, 8))
        calls.append(('blend' if address == VERTS + 0x10230 else 'filter', this, arg))
        if address == VERTS + 0x10230:
            mu.mem_write(base + 0x11234, struct.pack('<i', arg))
    mu.hook_add(UC_HOOK_CODE, blending, begin=VERTS + 0x10230, end=VERTS + 0x10243)

    def factors(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        this, src, dst = struct.unpack('<Iii', mu.mem_read(esp + 4, 12))
        calls.append(('factors', src, dst))
    mu.hook_add(UC_HOOK_CODE, factors, begin=VERTS + 0x10250, end=VERTS + 0x10253)

    def texel(v, fmt):
        """texload's reading of a pixel: five bits a channel, or None when it is not opaque. A format-0 texture is
        1555 by the time the create sees it, the DLL's loader having expanded its 565 in place."""
        if fmt == 8:
            if v >> 12 != 15:
                return None
            r, g, b = v >> 8 & 15, v >> 4 & 15, v & 15
            return r * 2 + (r >> 3), g * 2 + (g >> 3), b * 2 + (b >> 3)
        if not v & 0x8000:
            return None
        return v >> 10 & 31, v >> 5 & 31, v & 31

    def kind(pixels, fmt):
        """texload's verdict in Python: nothing for a sprite, else a picture, or one all but black."""
        texels = [texel(v, fmt) for v in pixels]
        if not texels or None in texels:
            return 0
        dark = sum(1 for t in texels if sum(t) <= DARKPIX)
        return KBLACK if dark * 4 >= len(texels) * MOSTLY else KPICTURE

    def load(index, pixels, fmt, size=None):
        """The texture create's entry: the kind it leaves in the table."""
        size = size or int(len(pixels) ** 0.5)
        where, desc = VERTS + 0x12000, VERTS + 0x11800
        mu.mem_write(where, struct.pack('<%dH' % len(pixels), *pixels))
        mu.mem_write(desc, struct.pack('<III', where, size, fmt))
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<I', 0xDEAD0000))
        mu.mem_write(esp + 0x20, b'\xa5' * 0x7c)
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_ESI, index)
        mu.reg_write(UC_X86_REG_EBP, desc)
        mu.emu_start(base + rva + 40, 0xDEAD0000, count=3000000)
        if (mu.reg_read(UC_X86_REG_ESP) != esp + 4 or mu.reg_read(UC_X86_REG_ESI) != index or mu.reg_read(UC_X86_REG_EBP) != desc
                or mu.reg_read(UC_X86_REG_EAX) != 0 or mu.reg_read(UC_X86_REG_ECX) != 0 or mu.mem_read(esp + 0x20, 0x7c) != bytes(0x7c)):
            raise SystemExit('widetest: the texture create resumed wrong: esp %x/%x esi %x ebp %x eax %x ecx %x zeroed %r' % (
                mu.reg_read(UC_X86_REG_ESP), esp + 4, mu.reg_read(UC_X86_REG_ESI), mu.reg_read(UC_X86_REG_EBP), mu.reg_read(UC_X86_REG_EAX),
                mu.reg_read(UC_X86_REG_ECX), mu.mem_read(esp + 0x20, 0x7c) == bytes(0x7c)))
        return struct.unpack('<I', mu.mem_read(base + rva + blob.find(b'KINDTABLE') + 12 + index * 4, 4))[0]

    hud = base + rva + patcher.WIDE2D_BLOB.find(b'HUDFRAME') + 8    # the flag the exe's walk entry sets

    def draw(entry, verts, fvf=0x1c4, w=1920, h=1080, uv=None, diffuse=0xffffffff):
        mu.mem_write(base + 0x1121c, struct.pack('<I', fvf))
        mu.mem_write(base + 0x123fc, struct.pack('<II', w, h))
        uv = uv or [(0.0, 0.0)] * len(verts)
        data = b''.join(struct.pack(VERTEX, x, y, 0.5, 1.0, diffuse, 0, u, v) for (x, y), (u, v) in zip(verts, uv))
        mu.mem_write(VERTS, data)
        esp = STACK + 0x8000
        # the return, `this`, the vertices, a list's count (an indexed list's vertex count), its indices and index count
        mu.mem_write(esp, struct.pack('<IIIIII', 0xDEAD0000, device, VERTS, len(verts), 0x1D1D0000, 0x99))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(base + rva + entry, 0xDEAD0000, count=1000000)
        if entry in (10, 15, 20, 25):
            resumed = (mu.reg_read(UC_X86_REG_EAX), mu.reg_read(UC_X86_REG_ECX)) == (len(verts) if entry != 15 else 0x99, 0xD3D3D3D3)
        else:
            resumed = mu.reg_read(UC_X86_REG_EDX) == 0x18
        if (not resumed or mu.reg_read(UC_X86_REG_ESP) != esp + 4
                or struct.unpack('<I', mu.mem_read(esp + 4, 4))[0] != device):
            raise SystemExit('widetest: the 2D draw resumed wrong')
        at = struct.unpack('<I', mu.mem_read(esp + 8, 4))[0]
        out = mu.mem_read(at, len(data))
        return at != VERTS, [(lambda v: (v[0], v[1], v[6]))(struct.unpack(VERTEX, out[i:i + 32])) for i in range(0, len(out), 32)]

    def present():
        """The present's entry: the frame's widths become last frame's."""
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<II', 0xDEAD0000, device))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(base + rva + 35, 0xDEAD0000, count=100000)
        if mu.reg_read(UC_X86_REG_EAX) != 0xF0F0F0F0 or mu.reg_read(UC_X86_REG_ESP) != esp + 4:
            raise SystemExit('widetest: the present resumed wrong')

    def grid(w, h, cols, rows, x0=0.0, y0=0.0):
        """cols by rows quads of w by h from (x0, y0), as a background draws its tiles."""
        for r in range(rows):
            for c in range(cols):
                x, y = x0 + c * w, y0 + r * h
                draw(0, [(x, y), (x + w, y), (x, y + h), (x + w, y + h)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])

    quad = [(100.0, 100.0), (200.0, 100.0), (100.0, 200.0), (200.0, 200.0)]
    copied, got = draw(0, quad)
    want = [(x * 2.25 + 240, y * 2.25) for x, y in quad]
    if not copied or any(abs(a - b) > 0.01 for p, q in zip(got, want) for a, b in zip(p[:2], q)):
        raise SystemExit('widetest: a quad came out %r' % (got,))
    copied, got = draw(0, [(0.0, 0.0), (640.0, 0.0), (0.0, 480.0), (640.0, 480.0)])
    if not copied or [p[:2] for p in got] != [(0.0, 0.0), (1920.0, 0.0), (0.0, 1080.0), (1920.0, 1080.0)]:
        raise SystemExit('widetest: a full-width quad came out %r' % (got,))
    # the HUD's 16:9 frame: with the flag set, a draw wholly in the left 0.42 of the 640 moves
    # out by min(bar, 2H/9), one in the right 0.42 the other way, the middle and a draw across the split stay
    left, right = [(20.0, 20.0), (120.0, 20.0), (20.0, 80.0), (120.0, 80.0)], [(500.0, 300.0), (600.0, 300.0), (500.0, 400.0), (600.0, 400.0)]
    middle, across = [(250.0, 20.0), (350.0, 20.0), (250.0, 80.0), (350.0, 80.0)], [(150.0, 20.0), (300.0, 20.0), (150.0, 80.0), (300.0, 80.0)]
    for w, h, shift in ((1920, 1080, 240.0), (5120, 1440, 320.0), (1680, 1050, 140.0)):
        scale, bar = h / 480.0, (w - 640 * h / 480.0) / 2
        for flag, quads in ((0, ((left, 0.0), (right, 0.0))), (1, ((left, -shift), (right, shift), (middle, 0.0), (across, 0.0)))):
            mu.mem_write(hud, struct.pack('<I', flag))
            for verts, dx in quads:
                copied, got = draw(0, verts, w=w, h=h)
                moved = [(x * scale + bar + dx, y * scale) for x, y in verts]
                if not copied or any(abs(a - b) > 0.01 for p, q in zip(got, moved) for a, b in zip(p[:2], q)):
                    raise SystemExit('widetest: with the HUD flag %d at %dx%d a quad came out %r, not %r' % (flag, w, h, got, moved))
    # a list of quads is moved a quad at a time - the race's text is one list of glyphs from both sides -
    # a strip as a whole
    for entry in (10, 15):
        copied, got = draw(entry, left + right + middle)
        moved = [(x * 2.25 + 240 + dx, y * 2.25) for verts, dx in ((left, -240.0), (right, 240.0), (middle, 0.0)) for x, y in verts]
        if not copied or any(abs(a - b) > 0.01 for p, q in zip(got, moved) for a, b in zip(p[:2], q)):
            raise SystemExit('widetest: a list of quads across the HUD came out %r' % (got,))
    # adjacent quads of a list are a string and move together: a glyph at 250-265 and its neighbour at
    # 267-282 straddle the split and both stay, one at 500 after them goes right
    glyphs = [(250.0, 300.0), (265.0, 300.0), (250.0, 316.0), (265.0, 316.0), (267.0, 300.0), (282.0, 300.0), (267.0, 316.0), (282.0, 316.0)]
    copied, got = draw(15, glyphs + right)
    moved = [(x * 2.25 + 240, y * 2.25) for x, y in glyphs] + [(x * 2.25 + 480, y * 2.25) for x, y in right]
    if not copied or any(abs(a - b) > 0.01 for p, q in zip(got, moved) for a, b in zip(p[:2], q)):
        raise SystemExit('widetest: a string across the split came out %r' % (got,))
    # a string at the right edge - POSITION's two-digit place, 591 to 639.5 - is text, not a tile or a
    # fade, and moves out with the rest, alone or in the race's list; a lone quad touching an edge still stays
    place = [(591.0, 191.0), (639.5, 191.0), (591.0, 207.0), (639.5, 207.0)]
    copied, got = draw(15, place)
    moved = [(x * 2.25 + 480, y * 2.25) for x, y in place]
    if not copied or any(abs(a - b) > 0.01 for p, q in zip(got, moved) for a, b in zip(p[:2], q)):
        raise SystemExit('widetest: a string touching the right edge came out %r' % (got,))
    copied, got = draw(0, place)
    if [p[:2] for p in got] != [(x * 2.25 + 240, y * 2.25) for x, y in place]:
        raise SystemExit('widetest: a quad touching the right edge came out %r' % (got,))
    times = [(8.0, 12.0), (68.0, 12.0), (8.0, 28.0), (68.0, 28.0)]
    copied, got = draw(15, times + place)
    moved = [(x * 2.25, y * 2.25) for x, y in times] + [(x * 2.25 + 480, y * 2.25) for x, y in place]
    if not copied or any(abs(a - b) > 0.01 for p, q in zip(got, moved) for a, b in zip(p[:2], q)):
        raise SystemExit('widetest: a list with a string at the right edge came out %r' % (got,))
    # the band between split screen's halves, 224 to 256 down: the car icons and their labels stay with the
    # bar, alone or in the race's list; a string reaching below it (the lower half's lap time) moves
    icons = [(20.0, 237.0), (44.0, 237.0), (20.0, 250.0), (44.0, 250.0), (20.0, 225.0), (36.0, 225.0), (20.0, 235.0), (36.0, 235.0)]
    lower = [(8.0, 252.0), (68.0, 252.0), (8.0, 268.0), (68.0, 268.0)]
    copied, got = draw(15, icons + lower + place)
    moved = [(x * 2.25 + 240, y * 2.25) for x, y in icons] + [(x * 2.25, y * 2.25) for x, y in lower] + [(x * 2.25 + 480, y * 2.25) for x, y in place]
    if not copied or any(abs(a - b) > 0.01 for p, q in zip(got, moved) for a, b in zip(p[:2], q)):
        raise SystemExit('widetest: the band between the halves came out %r' % (got,))
    copied, got = draw(0, icons[:4])
    if [p[:2] for p in got] != [(x * 2.25 + 240, y * 2.25) for x, y in icons[:4]]:
        raise SystemExit('widetest: a quad in the band came out %r' % (got,))
    copied, got = draw(20, left + right)
    moved = [(x * 2.25 + 240, y * 2.25) for x, y in left + right]
    if not copied or any(abs(a - b) > 0.01 for p, q in zip(got, moved) for a, b in zip(p[:2], q)):
        raise SystemExit('widetest: a strip across the HUD came out %r' % (got,))
    # the bounds the exe writes beside the flag: in a HUD frame, only a draw returning inside them is
    # anchored - the results row draws from elsewhere in the same frame and keeps its 4:3 place
    bounds = base + rva + patcher.WIDE2D_BLOB.find(b'HUDFRAME') + 12
    for lo, hi, dx in ((0xDEAC0000, 0xDEAE0000, -240.0), (0x00400000, 0x00500000, 0.0)):
        mu.mem_write(bounds, struct.pack('<II', lo, hi))
        copied, got = draw(0, left)
        moved = [(x * 2.25 + 240 + dx, y * 2.25) for x, y in left]
        if not copied or any(abs(a - b) > 0.01 for p, q in zip(got, moved) for a, b in zip(p[:2], q)):
            raise SystemExit('widetest: with the HUD draw bounds %#x-%#x a quad came out %r, not %r' % (lo, hi, got, moved))
    mu.mem_write(bounds, struct.pack('<II', 0, 0))
    present()                                       # which clears the flag for the next frame
    if struct.unpack('<I', mu.mem_read(hud, 4))[0] != 0:
        raise SystemExit('widetest: the present left the HUD flag set')
    # a tile at the edge extends only once its width tiled the whole frame the frame before: a sprite of 128 at the
    # edge with no such frame behind it keeps its place, as does one after a frame of four such quads, or of a row
    edge = [(-40.0, 0.0), (88.0, 0.0), (-40.0, 128.0), (88.0, 128.0)]
    mu.mem_write(base + 0x11240, struct.pack('<I', 0))
    present()
    copied, got = draw(0, edge, uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if [p[:2] for p in got] != [(150.0, 0.0), (438.0, 0.0), (150.0, 288.0), (438.0, 288.0)]:
        raise SystemExit('widetest: a lone edge quad extended: %r' % (got,))
    grid(128, 128, 2, 2)
    present()
    copied, got = draw(0, edge, uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if [p[:2] for p in got] != [(150.0, 0.0), (438.0, 0.0), (150.0, 288.0), (438.0, 288.0)]:
        raise SystemExit('widetest: an edge quad extended after four of its width: %r' % (got,))
    grid(128, 128, 5, 1, y0=100.0)
    present()
    copied, got = draw(0, edge, uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if [p[:2] for p in got] != [(150.0, 0.0), (438.0, 0.0), (150.0, 288.0), (438.0, 288.0)]:
        raise SystemExit('widetest: an edge quad extended after a row of its width: %r' % (got,))
    # a frame tiled 5 by 4 with them (the last row past the bottom, as a grid falls), scrolled 40 px left
    grid(128, 128, 6, 4, x0=-40.0)
    present()
    # a clamped tile at the left edge, 128 wide, u 0..1: out to the edge, u shifted by 240 / (128 * 2.25), wrap switched on
    copied, got = draw(0, edge, uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    # scrolled 40 px off the left edge first: its left vertex moves 240 - 40 * 2.25 picture pixels, the shift follows that
    tile = [(0.0, 0.0, -(240 / 2.25 - 40) / 128), (438.0, 0.0, 1.0), (0.0, 288.0, -(240 / 2.25 - 40) / 128), (438.0, 288.0, 1.0)]
    if not copied or any(abs(a - b) > 0.001 for p, q in zip(got, tile) for a, b in zip(p, q)):
        raise SystemExit('widetest: a scrolled edge tile came out %r' % (got,))
    # the widths seen this frame count only from the next present: a 64-wide sprite at the edge stays where it is
    copied, got = draw(0, [(-20.0, 200.0), (44.0, 200.0), (-20.0, 264.0), (44.0, 264.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if [p[:2] for p in got] != [(195.0, 450.0), (339.0, 450.0), (195.0, 594.0), (339.0, 594.0)]:
        raise SystemExit('widetest: a sprite at the edge extended: %r' % (got,))
    grid(128, 128, 5, 4)
    present()
    del wraps[:]
    copied, got = draw(0, [(0.0, 0.0), (128.0, 0.0), (0.0, 128.0), (128.0, 128.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if wraps != [(device, 1)]:
        raise SystemExit('widetest: wrap not switched on for a clamped tile: %r' % (wraps,))
    shift = 240 / (128 * 2.25)
    tile = [(0.0, 0.0, -shift), (528.0, 0.0, 1.0), (0.0, 288.0, -shift), (528.0, 288.0, 1.0)]
    if not copied or any(abs(a - b) > 0.001 for p, q in zip(got, tile) for a, b in zip(p, q)):
        raise SystemExit('widetest: an edge tile came out %r' % (got,))
    copied, got = draw(0, [(512.0, 0.0), (640.0, 0.0), (512.0, 128.0), (640.0, 128.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    tile = [(1392.0, 0.0, 0.0), (1920.0, 0.0, 1.0 + shift), (1392.0, 288.0, 0.0), (1920.0, 288.0, 1.0 + shift)]
    if not copied or any(abs(a - b) > 0.001 for p, q in zip(got, tile) for a, b in zip(p, q)):
        raise SystemExit('widetest: a right-edge tile came out %r' % (got,))
    # a strip of a picture at the right edge, tile-wide but tall, keeps its place
    copied, got = draw(0, [(512.0, 0.0), (640.0, 0.0), (512.0, 480.0), (640.0, 480.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if [p[:2] for p in got] != [(1392.0, 0.0), (1680.0, 0.0), (1392.0, 1080.0), (1680.0, 1080.0)]:
        raise SystemExit('widetest: a picture strip came out %r' % (got,))
    # the texture create's entry says what each texture is: a picture a bar can be drawn from, one so nearly
    # black that the bar should be black instead, or nothing at all - a sprite, a palette, a render target,
    # one with no pixels, or a number past the table
    teal = [0x8000 | (v >> 2) << 10 | (v | (y & 1)) << 5 | v for y in range(32) for x in range(32) for v in ((x * 7 + y * 3) % 20 + 4,)]
    if load(3, teal, 0) != KPICTURE or kind(teal, 0) != KPICTURE:
        raise SystemExit('widetest: the teal texture came out %r' % (load(3, teal, 0),))
    black = [0x8000 | 1 << 10 | 1 << 5 | 1] * 900 + [0x8000 | 0x1f << 10] * 124
    if load(4, black, 0) != KBLACK or kind(black, 0) != KBLACK:
        raise SystemExit('widetest: a texture all but black came out %r' % (load(4, black, 0),))
    clear = [0x8000 | 0x1234] * 1023 + [0x1234]
    if (load(5, clear, 2) or load(6, teal, 0x102) or load(7, teal, 0x1000) or load(8, [], 2, size=0)
            or load(200, teal, 0)):
        raise SystemExit('widetest: a texture counted as a picture that should not have')
    # a flag the description carries beside the format - anything but a palette or a render target - is no reason to refuse
    if load(10, teal, 0x10) != KPICTURE or load(11, teal, 0x2000) != KPICTURE:
        raise SystemExit('widetest: a texture with a flag beside its format was refused')
    if load(9, [0xf000 | 0xa << 8 | 0x5 << 4 | 0xf] * 1024, 8) != KPICTURE:
        raise SystemExit('widetest: a plain 4444 texture was not a picture')

    def bar_quad(calls):
        return [[(v[0], v[1], v[4], round(v[5], 5), round(v[6], 5)) for v in c[2]] for c in calls if c[0] == 'quad']


    def want_bar(xouter, xinner, y0, y1, uouter, uinner, v0, v1, left, upx, diffuse=0xffffffff):
        """The quads a bar is: the picture's own sliver stretched from its edge out to the screen's, drawn with
        the texture still on once for each pass, the passes spread across BLURPX of the 640's pixels - upx the
        quad's u per pixel - each at its share of the quad's diffuse, so they add up to a motion blur across."""
        d = (diffuse & 0xff000000) | sum(min(((diffuse >> s & 0xff) * DIM >> 8) * PASSSHARE >> 8, 0xff) << s
                                         for s in (0, 8, 16))
        x0, x1 = (xouter, xinner) if left else (xinner, xouter)
        a, b = (uouter, uinner) if left else (uinner, uouter)
        step = BLURPX * upx / (PASSES - 1)
        return [[(x0, y0, d, round(a + at, 5), v0), (x1, y0, d, round(b + at, 5), v0),
                 (x0, y1, d, round(a + at, 5), v1), (x1, y1, d, round(b + at, 5), v1)]
                for at in ((i - (PASSES - 1) / 2) * step for i in range(PASSES))]

    def u_at(x, x0, x1, u0, u1):
        return u0 + (x - x0) * (u1 - u0) / (x1 - x0)
    # a right-edge strip of texture 3: one textured quad from the picture's edge to the screen's, carrying the
    # 640's own last eighty pixels - a bar's share of the 1920 - stretched across it, and the strip as before
    mu.mem_write(base + 0x11224, struct.pack('<I', 3))
    del calls[:]
    copied, got = draw(0, [(512.0, 0.0), (640.0, 0.0), (512.0, 480.0), (640.0, 480.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    bars = want_bar(1920.0, 1680.0, 0.0, 1080.0, u_at(640.0, 512.0, 640.0, 0.0, 1.0),
                    u_at(560.0, 512.0, 640.0, 0.0, 1.0), 0.0, 1.0, False, 1.0 / 128)
    if ([c for c in calls if c[0] != 'quad'] != [('filter', device, 1), ('factors', 2, 2), ('blend', device, 1),
                                                 ('blend', device, 0), ('factors', 5, 6)]
            or bar_quad(calls) != bars
            or [p[:2] for p in got] != [(1392.0, 0.0), (1680.0, 0.0), (1392.0, 1080.0), (1680.0, 1080.0)]):
        raise SystemExit('widetest: the bar came out %r, not %r' % (bar_quad(calls)[:1], bars[:1]))
    # a sprite gets none
    mu.mem_write(base + 0x11224, struct.pack('<I', 5))
    del calls[:]
    draw(0, [(512.0, 0.0), (640.0, 0.0), (512.0, 480.0), (640.0, 480.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if calls:
        raise SystemExit('widetest: a bar drawn for a sprite: %r' % (calls,))
    # a texture all but black gets a black bar, drawn with no texture at all and its own put back after
    mu.mem_write(base + 0x11224, struct.pack('<I', 4))
    del calls[:]
    draw(0, [(512.0, 0.0), (640.0, 0.0), (512.0, 480.0), (640.0, 480.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if (calls[0] != ('texture', device, -1) or calls[-1] != ('texture', device, 4)
            or [v[2] for v in bar_quad(calls)[0]] != [0xff000000] * 4):
        raise SystemExit('widetest: a black texture\'s bar came out %r' % (calls,))
    # a tile running past the 640, as the mode select's right-hand ones do: the bar starts at the 640, not at
    # the tile's own edge, and carries the 640's last eighty pixels as the others do
    mu.mem_write(base + 0x11224, struct.pack('<I', 3))
    del calls[:]
    draw(0, [(512.0, 0.0), (768.0, 0.0), (512.0, 480.0), (768.0, 480.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    bars = want_bar(1920.0, 1680.0, 0.0, 1080.0, u_at(640.0, 512.0, 768.0, 0.0, 1.0),
                    u_at(560.0, 512.0, 768.0, 0.0, 1.0), 0.0, 1.0, False, 1.0 / 256)
    if bar_quad(calls) != bars:
        raise SystemExit('widetest: a tile past the 640 came out %r, not %r' % (bar_quad(calls), bars))
    # the left bar: from the screen's edge to the picture's, carrying the 640's own first eighty pixels
    del calls[:]
    draw(0, [(0.0, 0.0), (256.0, 0.0), (0.0, 240.0), (256.0, 240.0)], uv=[(0, 0), (1, 0), (0, 0.5), (1, 0.5)])
    bars = want_bar(0.0, 240.0, 0.0, 540.0, u_at(0.0, 0.0, 256.0, 0.0, 1.0),
                    u_at(80.0, 0.0, 256.0, 0.0, 1.0), 0.0, 0.5, True, 1.0 / 256)
    if bar_quad(calls) != bars:
        raise SystemExit('widetest: the left bar came out %r, not %r' % (bar_quad(calls), bars))
    # a plate sliding through the edge - wide, opaque, but not tall - gets no bar
    del calls[:]
    draw(0, [(-8.0, 100.0), (265.0, 100.0), (-8.0, 140.0), (265.0, 140.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if calls:
        raise SystemExit('widetest: a bar drawn for a plate: %r' % (calls,))
    # each pass carries its share of the quad's diffuse
    del calls[:]
    draw(0, [(512.0, 0.0), (640.0, 0.0), (512.0, 480.0), (640.0, 480.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)], diffuse=0x80808080)
    if [v[2] for v in bar_quad(calls)[0]] != [0x80000000 | sum(((0x80 * DIM >> 8) * PASSSHARE >> 8) << s for s in (0, 8, 16))] * 4:
        raise SystemExit('widetest: the bar\'s diffuse came out %r' % (bar_quad(calls),))
    # the bar's own draw, arriving through the quad entry with the flag set, goes as it is
    flag = base + rva + blob.find(b'BARFLAG') + 8
    mu.mem_write(flag, struct.pack('<I', 1))
    if draw(0, quad)[0]:
        raise SystemExit('widetest: the bar\'s draw was scaled')
    mu.mem_write(flag, struct.pack('<I', 0))
    mu.mem_write(base + 0x11224, struct.pack('<I', 0x80000000))
    del calls[:]

    # a plain quad at one edge - no texture selected - is a cover and goes out to the screen's edge on that
    # side: the ending's black left of its replay window (-1 to 351, 222 to 639) and right of it (607 to 642)
    for cover, want_x in (([(-1.0, 222.0), (351.0, 222.0), (-1.0, 639.0), (351.0, 639.0)], (0.0, 1029.75)),
                          ([(607.0, 222.0), (642.0, 222.0), (607.0, 639.0), (642.0, 639.0)], (1605.75, 1920.0))):
        copied, got = draw(0, cover)
        if not copied or [p[0] for p in got] != [want_x[0], want_x[1]] * 2 or [p[1] for p in got] != [499.5, 499.5, 1437.75, 1437.75]:
            raise SystemExit('widetest: a plain cover at the edge came out %r' % (got,))
    # a clamped quad wider than a tile at the left edge - a picture - keeps its place; wrapping, it extends
    mu.mem_write(base + 0x11224, struct.pack('<I', 8))           # a sprite's texture, no bar for it
    photo = [(0.0, 0.0), (320.0, 0.0), (0.0, 480.0), (320.0, 480.0)]
    del wraps[:]
    copied, got = draw(0, photo, uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if wraps or [p[:2] for p in got] != [(240.0, 0.0), (960.0, 0.0), (240.0, 1080.0), (960.0, 1080.0)]:
        raise SystemExit('widetest: a clamped picture came out %r' % (got,))
    mu.mem_write(base + 0x11240, struct.pack('<I', 1))
    copied, got = draw(0, photo, uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if wraps or [p[:2] for p in got] != [(240.0, 0.0), (960.0, 0.0), (240.0, 1080.0), (960.0, 1080.0)]:
        raise SystemExit('widetest: a wrapping picture came out %r' % (got,))
    mu.mem_write(base + 0x11240, struct.pack('<I', 0))
    mu.mem_write(base + 0x11224, struct.pack('<I', 0x80000000))
    copied, got = draw(5, quad[:3])
    if not copied or any(abs(a - b) > 0.01 for p, q in zip(got, want[:3]) for a, b in zip(p[:2], q)):
        raise SystemExit('widetest: a triangle came out %r' % (got,))
    if draw(0, quad, w=640, h=480)[0] or draw(0, quad, fvf=0x1e2)[0]:
        raise SystemExit('widetest: a quad copied that should have gone as it was')
    text = [(x, y) for i in range(20) for x, y in ((10.0 + i * 8, 20.0), (18.0 + i * 8, 20.0), (10.0 + i * 8, 28.0))]
    copied, got = draw(10, text)
    if not copied or any(abs(a - b) > 0.01 for p, (x, y) in zip(got, text) for a, b in zip(p[:2], (x * 2.25 + 240, y * 2.25))):
        raise SystemExit('widetest: a list came out %r' % (got[:3],))
    if draw(10, [(1.0, 1.0)] * 2049)[0]:
        raise SystemExit('widetest: an oversized list copied')
    mu.mem_write(device, struct.pack('<I', vtable))     # that list's vertices reach the device's own address
    # the trace: the flag set as d3dtrace sets it, kernel32 stubbed; a quad and a list report
    mu.mem_write(base + rva + blob.find(b'D3DTRACE\0') + 9, struct.pack('<I', 1))
    mu.mem_map(STUBS, 0x1000)
    mu.mem_write(STUBS, b'\xc2\x04\x00' + b'\x90' * 13 + b'\xc2\x08\x00' + b'\x90' * 13 + b'\xc2\x04\x00' + b'\x90' * 13
                 + b'\xc2\x10\x00' + b'\x90' * 13 + b'\xc2\x18\x00' + b'\x90' * 13 + b'\xc2\x14\x00' + b'\x90' * 13
                 + b'\xc2\x08\x00' + b'\x90' * 13 + b'\xc2\x10\x00' + b'\x90' * 13 + b'\xc2\x04\x00' + b'\x90' * 13
                 + b'\xc2\x0c\x00' + b'\x90' * 13 + b'\xc2\x08\x00' + b'\x90' * 13 + b'\xc2\x1c\x00' + b'\x90' * 13
                 + b'\xc2\x14\x00')
    # LoadLibraryA, GetProcAddress, ODS, VirtualProtect, Blt, Lock, Unlock, CreateSurface, Release,
    # GetModuleFileNameA, CreateDirectoryA, CreateFileA, WriteFile
    mu.mem_write(base + 0xf114, struct.pack('<I', STUBS))
    mu.mem_write(base + 0xf0ac, struct.pack('<I', STUBS + 0x10))
    mu.mem_write(base + 0xf038, struct.pack('<I', STUBS + 0x90))
    procs = {b'VirtualProtect': STUBS + 0x30, b'CreateDirectoryA': STUBS + 0xa0, b'CreateFileA': STUBS + 0xb0,
             b'WriteFile': STUBS + 0xc0}
    lines = []
    logged = []
    paths = []
    protects = []
    blits = []
    locks = []
    creates = []
    releases = []

    def stub(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        arg = struct.unpack('<I', mu.mem_read(esp + 4, 4))[0]
        if address == STUBS + 0x20:
            lines.append(bytes(mu.mem_read(arg, 128)).split(b'\0')[0].decode())
        elif address == STUBS + 0x10:
            name = bytes(mu.mem_read(struct.unpack('<I', mu.mem_read(esp + 8, 4))[0], 32)).split(b'\0')[0]
            mu.reg_write(UC_X86_REG_EAX, procs.get(name, STUBS + 0x20))
            return
        elif address == STUBS + 0x90:                       # GetModuleFileNameA: the exe's path
            mu.mem_write(struct.unpack('<I', mu.mem_read(esp + 8, 4))[0], b'C:\\SR2\\SEGA RALLY 2.exe\0')
            mu.reg_write(UC_X86_REG_EAX, 21)
            return
        elif address in (STUBS + 0xa0, STUBS + 0xb0):       # CreateDirectoryA, CreateFileA: the path
            paths.append(bytes(mu.mem_read(arg, 64)).split(b'\0')[0].decode())
            mu.reg_write(UC_X86_REG_EAX, 7)
            return
        elif address == STUBS + 0xc0:                       # WriteFile: the line as written
            handle, at, length = struct.unpack('<III', mu.mem_read(esp + 4, 12))
            logged.append((handle, bytes(mu.mem_read(at, length))))
            mu.reg_write(UC_X86_REG_EAX, 1)
            return
        elif address == STUBS + 0x30:
            at, size, prot, old = struct.unpack('<IIII', mu.mem_read(esp + 4, 16))
            protects.append((at, size, prot))
            mu.mem_write(old, struct.pack('<I', 0x20))
        elif address == STUBS + 0x40:
            this, rect, src, srect, flags, fx = struct.unpack('<IIIIII', mu.mem_read(esp + 4, 24))
            fill = flags & 0x400 and fx and struct.unpack('<I', mu.mem_read(fx + 0x50, 4))[0]
            blits.append((this, rect and struct.unpack('<4i', mu.mem_read(rect, 16)),
                          srect and struct.unpack('<4i', mu.mem_read(srect, 16))) + ((('fill', fill),) if flags & 0x400 else ()))
        elif address == STUBS + 0x50:                       # a surface's Lock: 640x480 at 16 bits, the lobby's
            this, rect, desc, flags_, event = struct.unpack('<IIIII', mu.mem_read(esp + 4, 20))   # pixels after
            locks.append(('lock', this, rect, flags_))       # the background's
            mu.mem_write(desc + 0x8, struct.pack('<II', 480, 640))
            mu.mem_write(desc + 0x10, struct.pack('<I', 1280))
            mu.mem_write(desc + 0x24, struct.pack('<I', PIXELS + (640 * 480 * 2 if this == VERTS + 0x12700 else 0)))
            mu.mem_write(desc + 0x54, struct.pack('<I', 16))
            mu.reg_write(UC_X86_REG_EAX, 0)
            return
        elif address == STUBS + 0x60:
            locks.append(('unlock', struct.unpack('<I', mu.mem_read(esp + 4, 4))[0]))
            mu.reg_write(UC_X86_REG_EAX, 0)
            return
        elif address == STUBS + 0x70:                       # IDirectDraw4::CreateSurface
            this, desc, out, outer = struct.unpack('<IIII', mu.mem_read(esp + 4, 16))
            size, flags_, height, width = struct.unpack('<IIII', mu.mem_read(desc, 16))
            creates.append((this, size, flags_, height, width, struct.unpack('<I', mu.mem_read(desc + 0x68, 4))[0]))
            mu.mem_write(out, struct.pack('<I', VERTS + 0x12700))
            mu.reg_write(UC_X86_REG_EAX, 0)
            return
        elif address == STUBS + 0x80:                       # a surface's Release
            releases.append(struct.unpack('<I', mu.mem_read(esp + 4, 4))[0])
            mu.reg_write(UC_X86_REG_EAX, 0)
            return
        mu.reg_write(UC_X86_REG_EAX, 0x1234)
    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0xd0)
    draw(0, [(10.0, 20.0), (50.0, 20.0), (10.0, 60.0), (50.0, 60.0)], fvf=0x1e2)
    draw(10, text[:6])
    if lines != ['sr2 d q 000001e2 00000004 dead0000 41200000 41a00000 3f000000 80000000 00000000 ',
                 'sr2 d l 000001c4 00000006 dead0000 41200000 41a00000 3f000000 80000000 00000000 ']:
        raise SystemExit('widetest: the trace said %r' % (lines,))
    # and the same lines to logs\d3dtrace.log beside the exe, opened once
    if paths != ['C:\\SR2\\logs', 'C:\\SR2\\logs\\d3dtrace.log']:
        raise SystemExit('widetest: the trace log was opened as %r' % (paths,))
    if logged != [(7, line.encode() + b'\r\n') for line in lines]:
        raise SystemExit('widetest: the trace log got %r' % (logged,))
    # barquad reports too: a strip at the right edge of a picture, then of a sprite
    del lines[:]
    mu.mem_write(base + 0x11224, struct.pack('<I', 3))
    draw(0, [(512.0, 0.0), (640.0, 0.0), (512.0, 480.0), (640.0, 480.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    mu.mem_write(base + 0x11224, struct.pack('<I', 5))
    draw(0, [(512.0, 0.0), (640.0, 0.0), (512.0, 480.0), (640.0, 480.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    bar_lines = [ln for ln in lines if ln.startswith('sr2 b ')]
    if ([ln.split()[2] for ln in bar_lines] != ['00000005', '00000004']
            or bar_lines[0].split()[3:5] != ['00000003', '%08x' % KPICTURE]
            or bar_lines[0].split()[5:] != ['44000000', '44200000', '00000000', '43f00000']):
        raise SystemExit('widetest: the bar trace said %r' % (bar_lines,))
    mu.mem_write(base + 0x11224, struct.pack('<I', 0x80000000))
    copied, got = draw(15, text)
    if not copied or any(abs(a - b) > 0.01 for p, (x, y) in zip(got, text) for a, b in zip(p[:2], (x * 2.25 + 240, y * 2.25))):
        raise SystemExit('widetest: an indexed list came out %r' % (got[:3],))
    # the countdown: a 640x480-terms strip; and a fan
    digit = [(170.0, 40.0), (470.0, 40.0), (170.0, 440.0), (470.0, 440.0)]
    for entry in (20, 25):
        copied, got = draw(entry, digit)
        if not copied or any(abs(a - b) > 0.01 for p, (x, y) in zip(got, digit) for a, b in zip(p[:2], (x * 2.25 + 240, y * 2.25))):
            raise SystemExit('widetest: a strip or fan came out %r' % (got,))
    if draw(20, digit, fvf=0x1e2)[0]:
        raise SystemExit('widetest: a 3D strip copied')
    # the device's viewport setter: the exe's 640x480 and a split half scaled into the picture's own 4:3 box, as the
    # 2D is - the four are a rect, left, top, right, bottom, so both sides take the bar - MGameGL's real one and a
    # 640x480 picture's left alone
    mu.mem_write(base + 0x6049, b'\x5f\x5e\x83\xc4\x08\xc2\x08\x00')     # the setter resumes: pop edi; pop esi; add esp,8; ret 8

    where = VERTS + 0x11000

    def setvp(rect, w=1920, h=1080):
        mu.mem_write(base + 0x123fc, struct.pack('<II', w, h))
        mu.mem_write(where, struct.pack('<4i4f', *rect, 0.5, 0.5, 1.0, 1.0))
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<III', 0xDEAD0000, 0x7715, where))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(base + rva + 30, 0xDEAD0000, count=100000)
        at = struct.unpack('<I', mu.mem_read(esp + 8, 4))[0]
        return at != where, struct.unpack('<4i4f', mu.mem_read(at, 32))
    # the two fractions at the end take the box's share of the screen's width, so the clip volume the setter
    # makes from the rect's share of the screen comes out as the 4:3 screen's
    if setvp((0, 0, 640, 480)) != (True, (240, 0, 1680, 1080, 0.5, 0.5, 0.75, 0.75)):
        raise SystemExit('widetest: the device viewport for 640x480 came out %r' % (setvp((0, 0, 640, 480)),))
    if setvp((0, 240, 640, 480)) != (True, (240, 540, 1680, 1080, 0.5, 0.5, 0.75, 0.75)):
        raise SystemExit('widetest: the device viewport for a split half came out %r' % (setvp((0, 240, 640, 480)),))
    if setvp((0, 0, 640, 480), w=5120, h=1440) != (True, (1600, 0, 3520, 1440, 0.5, 0.5, 0.375, 0.375)):
        raise SystemExit('widetest: the device viewport at 32:9 came out %r' % (setvp((0, 0, 640, 480), w=5120, h=1440),))
    if setvp((0, 0, 640, 480), w=1920, h=1440) != (True, (0, 0, 1920, 1440, 0.5, 0.5, 1.0, 1.0)):
        raise SystemExit('widetest: a 4:3 screen\'s viewport came out %r' % (setvp((0, 0, 640, 480), w=1920, h=1440),))
    # the lobby's blits: the present hooks the back buffer's Blt once, through VirtualProtect; a Blt into the back
    # buffer with a 640x480-sized rect goes to a 640x480 surface of the lobby's own instead, made through
    # IDirectDraw4::CreateSurface when first wanted, cut to it; and the present stretches that surface into the
    # 4:3 box and fills the sides with the background's colour
    surface, ddvtable = VERTS + 0x12000, VERTS + 0x12100
    mu.mem_write(surface, struct.pack('<I', ddvtable))
    mu.mem_write(ddvtable + 0x14, struct.pack('<I', STUBS + 0x40))
    mu.mem_write(ddvtable + 0x8, struct.pack('<I', STUBS + 0x80))
    mu.mem_write(ddvtable + 0x64, struct.pack('<I', STUBS + 0x50))      # Lock and Unlock, for the trace's descriptions
    mu.mem_write(ddvtable + 0x80, struct.pack('<I', STUBS + 0x60))
    mu.mem_write(base + 0x12554, struct.pack('<I', surface))
    mu.mem_write(base + 0x123fc, struct.pack('<II', 1920, 1080))
    present()
    present()
    hooked = struct.unpack('<I', mu.mem_read(ddvtable + 0x14, 4))[0]
    if hooked == STUBS + 0x40 or protects != [(ddvtable + 0x14, 4, 0x40), (ddvtable + 0x14, 4, 0x20)]:
        raise SystemExit('widetest: the Blt hook went in wrong: %08x %r' % (hooked, protects))

    source, srcvtable = VERTS + 0x12300, VERTS + 0x12400
    mu.mem_write(source, struct.pack('<I', srcvtable))
    mu.mem_write(srcvtable + 0x64, struct.pack('<I', STUBS + 0x50))
    mu.mem_write(srcvtable + 0x80, struct.pack('<I', STUBS + 0x60))
    mu.mem_write(PIXELS + 240 * 1280, struct.pack('<H', 0x2b4d))       # the background's colour at (0, 240)
    ddraw, ddrawvt, lobby = VERTS + 0x12500, VERTS + 0x12600, VERTS + 0x12700
    mu.mem_write(ddraw, struct.pack('<I', ddrawvt))
    mu.mem_write(ddrawvt + 0x18, struct.pack('<I', STUBS + 0x70))      # CreateSurface
    mu.mem_write(lobby, struct.pack('<I', ddvtable))                     # the lobby's surface, ddraw's vtable
    mu.mem_write(base + 0x1254c, struct.pack('<I', ddraw))

    def blit(this, rect, srect=None, w=1920, h=1080):
        at, sat = VERTS + 0x12200, VERTS + 0x12210
        mu.mem_write(base + 0x123fc, struct.pack('<II', w, h))
        if rect:
            mu.mem_write(at, struct.pack('<4i', *rect))
        if srect:
            mu.mem_write(sat, struct.pack('<4i', *srect))
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<7I', 0xDEAD0000, this, at if rect else 0, source, sat if srect else 0, 0x1000000, 0))
        del locks[:]
        mu.reg_write(UC_X86_REG_ESP, esp)
        del blits[:]
        mu.reg_write(UC_X86_REG_ESI, 0x5151)
        mu.reg_write(UC_X86_REG_EDI, 0x6161)
        mu.emu_start(hooked, 0xDEAD0000, count=1000000)     # room for the copy's 480 rows
        if mu.reg_read(UC_X86_REG_ESP) != esp + 4 + 24:
            raise SystemExit('widetest: the Blt hook left the stack at %x' % mu.reg_read(UC_X86_REG_ESP))
        if (mu.reg_read(UC_X86_REG_ESI), mu.reg_read(UC_X86_REG_EDI)) != (0x5151, 0x6161):
            raise SystemExit('widetest: the Blt hook did not keep esi and edi')
        return blits
    panel = (0, 0, 398, 287)
    if blit(surface, (126, 118, 524, 405), panel) != [(lobby, (126, 118, 524, 405), panel)]:
        raise SystemExit('widetest: a lobby blit came out %r' % (blit(surface, (126, 118, 524, 405), panel),))
    if creates != [(ddraw, 0x7c, 0x7, 480, 640, 0x4040)]:
        raise SystemExit('widetest: the lobby\'s surface was made wrong, or more than once: %r' % (creates,))
    # the background: its colour read from its surface at (0, 240) under a read-only lock, then the blit as it
    # was; the first time the lobby surface's pixel there is read back after the blit and, matching, the blit
    # is kept (copymode 2)
    LPIXELS = PIXELS + 640 * 480 * 2
    mu.mem_write(LPIXELS + 240 * 1280, struct.pack('<H', 0x2b4d))
    if blit(surface, (0, 0, 640, 480), (0, 0, 640, 480)) != [(lobby, (0, 0, 640, 480), (0, 0, 640, 480))]:
        raise SystemExit('widetest: the lobby background came out %r' % (blit(surface, (0, 0, 640, 480), (0, 0, 640, 480)),))
    if locks != [('lock', source, 0, 0x11), ('unlock', source), ('lock', lobby, 0, 0x11), ('unlock', lobby),
                 ('lock', source, 0, 0x11), ('unlock', source), ('lock', lobby, 0, 0x11), ('unlock', lobby)]:
        raise SystemExit('widetest: the background surface was locked wrong: %r' % (locks,))
    if lines[-3:] != ['sr2 x 00001234 %08x %08x 01000000 00000000 00000000 00000280 000001e0 00000000 00000000 00000280 000001e0 ' % (lobby, source),
                      'sr2 s %08x 00000000 00000000 00000280 000001e0 00000000 00000010 00000000 00002b4d ' % source,
                      'sr2 s %08x 00000000 00000000 00000280 000001e0 00000000 00000010 00000000 00002b4d ' % lobby]:
        raise SystemExit('widetest: the blit trace said %r' % (lines[-3:],))
    # the pixel read back not matching - dgVoodoo 2 - the background is copied through Lock instead, that first
    # time and from then on without a blit
    copymode = base + rva + blob.find(b'BGBLOCK\0') - 31 * 4 - 4   # before cpydesc, which is before the marker
    mu.mem_write(copymode, struct.pack('<I', 0))
    mu.mem_write(LPIXELS + 240 * 1280, struct.pack('<H', 0))
    mu.mem_write(PIXELS, bytes(range(256)) * (640 * 480 * 2 // 256))
    mu.mem_write(PIXELS + 240 * 1280, struct.pack('<H', 0x2b4d))
    if blit(surface, (0, 0, 640, 480), (0, 0, 640, 480)) != [(lobby, (0, 0, 640, 480), (0, 0, 640, 480))]:
        raise SystemExit('widetest: the first background under dgVoodoo came out %r' % (blits,))
    if struct.unpack('<I', mu.mem_read(copymode, 4))[0] != 1 or mu.mem_read(LPIXELS, 640 * 480 * 2) != mu.mem_read(PIXELS, 640 * 480 * 2):
        raise SystemExit('widetest: the background was not copied through Lock')
    mu.mem_write(LPIXELS, b'\0' * (640 * 480 * 2))
    if blit(surface, (0, 0, 640, 480), (0, 0, 640, 480)) != [] or mu.reg_read(UC_X86_REG_EAX) != 0:
        raise SystemExit('widetest: the next background was blitted: %r' % (blits,))
    if mu.mem_read(LPIXELS, 640 * 480 * 2) != mu.mem_read(PIXELS, 640 * 480 * 2) or lines[-3][:14] != 'sr2 x 00000000':
        raise SystemExit('widetest: the next background was not copied: %r' % (lines[-3],))
    mu.mem_write(copymode, struct.pack('<I', 2))
    # a panel sliding in from the right reaches past 640: cut at 640 with its source cut to match, as the
    # screen's edge cut it at 4:3; one off the left likewise; one below 480 before it slides up is not drawn
    if blit(surface, (606, 118, 1004, 405), panel) != [(lobby, (606, 118, 640, 405), (0, 0, 34, 287))]:
        raise SystemExit('widetest: a sliding panel came out %r' % (blit(surface, (606, 118, 1004, 405), panel),))
    if blit(surface, (-200, 118, 198, 405), panel) != [(lobby, (0, 118, 198, 405), (200, 0, 398, 287))]:
        raise SystemExit('widetest: a panel off the left came out %r' % (blit(surface, (-200, 118, 198, 405), panel),))
    if blit(surface, (460, 532, 600, 722), (0, 0, 140, 190)) != [] or mu.reg_read(UC_X86_REG_EAX) != 0:
        raise SystemExit('widetest: a panel below the picture came out %r' % (blit(surface, (460, 532, 600, 722), (0, 0, 140, 190)),))
    if (blit(surface, (0, 0, 1920, 1080), (0, 0, 1920, 1080)) != [(surface, (0, 0, 1920, 1080), (0, 0, 1920, 1080))]
            or blit(surface + 8, (0, 0, 640, 480), panel)[0][:2] != (surface + 8, (0, 0, 640, 480))
            or blit(surface, (1300, 0, 1500, 100), panel)[0][:2] != (surface, (1300, 0, 1500, 100))
            or blit(surface, None)[0][:2] != (surface, 0)):
        raise SystemExit('widetest: a blit that should pass was sent to the lobby\'s surface')
    # the present, with the lobby drawn lately: its surface stretched into the box and the sides filled, for
    # LOBBYLIVE presents after the last blit and no longer
    del blits[:]
    present()
    if blits != [(surface, (240, 0, 1680, 1080), (0, 0, 640, 480)), (surface, (0, 0, 240, 1080), 0, ('fill', 0x2b4d)),
                 (surface, (1680, 0, 1920, 1080), 0, ('fill', 0x2b4d))]:
        raise SystemExit('widetest: the lobby present came out %r' % (blits,))
    # at a size where the box or a side fill is itself no bigger than 640x480, those blits are still ours and
    # go to the back buffer, not round again into the lobby's surface
    mu.mem_write(base + 0x123fc, struct.pack('<II', 854, 480))
    del blits[:]
    present()
    if blits != [(surface, (107, 0, 747, 480), (0, 0, 640, 480)), (surface, (0, 0, 107, 480), 0, ('fill', 0x2b4d)),
                 (surface, (747, 0, 854, 480), 0, ('fill', 0x2b4d))]:
        raise SystemExit('widetest: the lobby present at 854x480 came out %r' % (blits,))
    mu.mem_write(base + 0x123fc, struct.pack('<II', 1920, 1080))
    for _ in range(6):                                  # eight presents in all since the last lobby blit
        del blits[:]
        present()
        if len(blits) != 3:
            raise SystemExit('widetest: the lobby present stopped early')
    del blits[:]
    present()
    if blits:
        raise SystemExit('widetest: the lobby present went on: %r' % (blits,))
    # the .bg pictures' surface: made at the present, 1600x600 in video memory, and kept in the block bgrow finds
    # by its marker; a composite bgrow leaves there is stretched into the whole screen at the next draw, or
    # present, and only once
    if creates.count((ddraw, 0x7c, 0x7, 600, 2176, 0x4040)) != 1:
        raise SystemExit('widetest: the .bg surface was made wrong, or more than once: %r' % (creates,))
    present()
    block = base + rva + blob.find(b'BGBLOCK\0') + 8
    if struct.unpack('<I', mu.mem_read(block, 4))[0] != lobby:
        raise SystemExit('widetest: the .bg surface is not in the block')
    mu.mem_write(block + 8, struct.pack('<III', 1, 1040, 480))
    del blits[:]
    draw(0, quad)
    if blits != [(surface, (0, 0, 1920, 1080), (0, 0, 1040, 480))] or struct.unpack('<I', mu.mem_read(block + 8, 4))[0]:
        raise SystemExit('widetest: the composite was not stretched in at the draw: %r' % (blits,))
    del blits[:]
    draw(0, quad)
    present()
    if blits:
        raise SystemExit('widetest: the composite was stretched in again: %r' % (blits,))
    mu.mem_write(block + 8, struct.pack('<III', 1, 800, 600))
    del blits[:]
    present()
    if blits != [(surface, (0, 0, 1920, 1080), (0, 0, 800, 600))]:
        raise SystemExit('widetest: the composite was not stretched in at the present: %r' % (blits,))
    # a new back buffer after a mode change: the old lobby surface released, a new one made
    mu.mem_write(base + 0x12554, struct.pack('<I', surface + 8))
    mu.mem_write(surface + 8, struct.pack('<I', ddvtable))
    del creates[:]
    del releases[:]
    blit(surface + 8, (126, 118, 524, 405), panel)
    if releases != [lobby] or creates != [(ddraw, 0x7c, 0x7, 480, 640, 0x4040)]:
        raise SystemExit('widetest: the lobby surface was not remade for a new back buffer: %r %r' % (releases, creates))
    mu.mem_write(base + 0x12554, struct.pack('<I', 0))
    if setvp((0, 0, 1920, 1080))[0] or setvp((0, 0, 640, 480), w=640, h=480)[0]:
        raise SystemExit('widetest: a device viewport scaled that should have passed')


def main():
    test_exe()
    test_gl()
    test_2d()
    print('widetest: the size stubs, the viewport and perspective hooks and the 2D scaling OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
