#!/usr/bin/env python3
"""Run the widescreen stubs under Unicorn.

    python3 tools/widetest.py

wide.asm (the European exe's, with a stubbed SR2.CFG): the mode check
takes a wide size from the file and asks for a re-init once, the size
setter applies it for mode 0 and keeps 800x600 for mode 1. widegl.asm:
SetViewport scales a 640x480 rect and its centre and leaves a full-size
one alone, SetPerspective widens the angle for the aspect and leaves it
at 4:3; the trace lines come out as documented. wide2d.asm: a quad in 640x480 terms comes out scaled and centred
in a 1920x1080 buffer, a full-width one stretched, one at the left edge
drawn out to it with its texture coordinate shifted, a 640x480 buffer or
another FVF untouched, and the lists likewise; the texture create's
entry reduces an opaque texture to the grid of mean colours the Python
reference here does, and a strip of it at the edge gets a bar shaded
down that grid's edge column.
Needs python3-unicorn; exits 0 with a note when it is missing.
"""
import importlib.util
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('patcher', os.path.join(HERE, '..', 'sr2-patcher.py'))
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EBP,
                                   UC_X86_REG_ESI, UC_X86_REG_EFLAGS)
except ImportError:
    print('widetest: skipped, python3-unicorn not installed')
    sys.exit(0)

PASSES, PASSDIM, BLURSTEP = 8, 10, 4    # the passes a bar is drawn in, each one's share of the quad's colour,
                                        # and the picture's rows between one and the next
KPICTURE, KBLACK = 1, 2             # what texload makes of a texture: a picture, or one all but black
DARKPIX, MOSTLY = 6, 3              # a pixel this dark is black, and a texture this many quarters of them
ROW = patcher.BUILDS['European']
CODE, STACK, STUBS, VTABLE, RECTS, VERTS = 0x5a0000, 0x3000000, 0x600000, 0x610000, 0x620000, 0x4000000
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
    for site, length in zip((0x37c0, 0x3870), (10, 9)):
        mu.mem_write(base + site + length, b'\x8b\xe5\x5d\xc3')     # the method resumes: its epilogue, back to the test
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
    size(640.0, 480.0)
    mu.mem_write(RECTS, struct.pack('<4i', 0, 0, 640, 480))
    _, _, rect, cx, cy = call(0, 0x7715, RECTS, 320, 240)
    if rect != RECTS or (cx, cy) != (320, 240):
        raise SystemExit('widetest: a viewport changed at 640x480')
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
    screen(b'2560x1440')
    if calls != [1, 1, 1]:
        raise SystemExit('widetest: the screen entry called the setter %r' % (calls,))


VERTEX = '<4f2I2f'


def test_2d():
    base, rva = 0x10000000, 0x20000
    blob = patcher.WIDE2D_BLOB.replace(struct.pack('<I', patcher.FULLWIN_MAGIC), struct.pack('<I', rva))
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(base, 0x100000)                      # the blob, whose grid of colours is the bulk of it
    mu.mem_map(STACK, 0x10000)
    mu.mem_map(VERTS, 0x20000)
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

    def fill(pixels, fmt):
        """texload's verdict in Python: nothing for a sprite, else a picture, or one all but black."""
        texels = [texel(v, fmt) for v in pixels]
        if not texels or None in texels:
            return 0
        dark = sum(1 for t in texels if sum(t) <= DARKPIX)
        return KBLACK if dark * 4 >= len(texels) * MOSTLY else KPICTURE

    def load(index, pixels, fmt, size=None):
        """The texture create's entry: the fill it leaves in the table."""
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
        return struct.unpack('<I', mu.mem_read(base + rva + blob.find(b'FILLTABLE') + 12 + index * 4, 4))[0]

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
    if load(3, teal, 0) != KPICTURE or fill(teal, 0) != KPICTURE:
        raise SystemExit('widetest: the teal texture came out %r' % (load(3, teal, 0),))
    black = [0x8000 | 1 << 10 | 1 << 5 | 1] * 900 + [0x8000 | 0x1f << 10] * 124
    if load(4, black, 0) != KBLACK or fill(black, 0) != KBLACK:
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


    def want_bar(xouter, xinner, y0, y1, uouter, uinner, v0, v1, left, rows=480.0, diffuse=0xffffffff):
        """The quads a bar is: the picture's own sliver stretched from its edge out to the screen's, drawn with
        the texture still on, once for each pass, each shifted a little further down the picture and carrying a
        pass's share of the quad's diffuse, so the passes add up to a blur down."""
        d = (diffuse & 0xff000000) | sum(((diffuse >> s & 0xff) * PASSDIM >> 8) << s for s in (0, 8, 16))
        x0, x1 = (xouter, xinner) if left else (xinner, xouter)
        a, b = (uouter, uinner) if left else (uinner, uouter)
        step = (v1 - v0) * BLURSTEP / rows
        out = []
        for i in range(PASSES):
            at = (i - (PASSES - 1) / 2) * step
            out.append([(x0, y0, d, round(a, 5), round(v0 + at, 5)), (x1, y0, d, round(b, 5), round(v0 + at, 5)),
                        (x0, y1, d, round(a, 5), round(v1 + at, 5)), (x1, y1, d, round(b, 5), round(v1 + at, 5))])
        return out

    def u_at(x, x0, x1, u0, u1):
        return u0 + (x - x0) * (u1 - u0) / (x1 - x0)
    # a right-edge strip of texture 3: one textured quad from the picture's edge to the screen's, carrying the
    # 640's own last eighty pixels - a bar's share of the 1920 - stretched across it, and the strip as before
    mu.mem_write(base + 0x11224, struct.pack('<I', 3))
    del calls[:]
    copied, got = draw(0, [(512.0, 0.0), (640.0, 0.0), (512.0, 480.0), (640.0, 480.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    bars = want_bar(1920.0, 1680.0, 0.0, 1080.0, u_at(640.0, 512.0, 640.0, 0.0, 1.0),
                    u_at(560.0, 512.0, 640.0, 0.0, 1.0), 0.0, 1.0, False)
    if ([c for c in calls if c[0] not in ('quad',)] != [('filter', device, 1), ('factors', 2, 2), ('blend', device, 1),
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
                    u_at(560.0, 512.0, 768.0, 0.0, 1.0), 0.0, 1.0, False)
    if bar_quad(calls) != bars:
        raise SystemExit('widetest: a tile past the 640 came out %r, not %r' % (bar_quad(calls), bars))
    # the left bar: from the screen's edge to the picture's, carrying the 640's own first eighty pixels
    del calls[:]
    draw(0, [(0.0, 0.0), (256.0, 0.0), (0.0, 240.0), (256.0, 240.0)], uv=[(0, 0), (1, 0), (0, 0.5), (1, 0.5)])
    bars = want_bar(0.0, 240.0, 0.0, 540.0, u_at(0.0, 0.0, 256.0, 0.0, 1.0),
                    u_at(80.0, 0.0, 256.0, 0.0, 1.0), 0.0, 0.5, True, rows=240.0)
    if bar_quad(calls) != bars:
        raise SystemExit('widetest: the left bar came out %r, not %r' % (bar_quad(calls), bars))
    # a plate sliding through the edge - wide, opaque, but not tall - gets no bar
    del calls[:]
    draw(0, [(-8.0, 100.0), (265.0, 100.0), (-8.0, 140.0), (265.0, 140.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)])
    if calls:
        raise SystemExit('widetest: a bar drawn for a plate: %r' % (calls,))
    # the quad's diffuse is halved into the bar's
    del calls[:]
    draw(0, [(512.0, 0.0), (640.0, 0.0), (512.0, 480.0), (640.0, 480.0)], uv=[(0, 0), (1, 0), (0, 1), (1, 1)], diffuse=0x80808080)
    if [v[2] for v in bar_quad(calls)[0]] != [0x80000000 | sum((0x80 * PASSDIM >> 8) << s for s in (0, 8, 16))] * 4:
        raise SystemExit('widetest: the bar\'s diffuse came out %r' % (bar_quad(calls),))
    # the bar's own draw, arriving through the quad entry with the flag set, goes as it is
    flag = base + rva + blob.find(b'BARFLAG') + 8
    mu.mem_write(flag, struct.pack('<I', 1))
    if draw(0, quad)[0]:
        raise SystemExit('widetest: the bar\'s draw was scaled')
    mu.mem_write(flag, struct.pack('<I', 0))
    mu.mem_write(base + 0x11224, struct.pack('<I', 0x80000000))
    del calls[:]

    # a clamped quad wider than a tile at the left edge - a picture - keeps its place; wrapping, it extends
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
    mu.mem_write(STUBS, b'\xc2\x04\x00' + b'\x90' * 13 + b'\xc2\x08\x00' + b'\x90' * 13 + b'\xc2\x04\x00')
    mu.mem_write(base + 0xf114, struct.pack('<I', STUBS))
    mu.mem_write(base + 0xf0ac, struct.pack('<I', STUBS + 0x10))
    lines = []

    def stub(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        arg = struct.unpack('<I', mu.mem_read(esp + 4, 4))[0]
        if address == STUBS + 0x20:
            lines.append(bytes(mu.mem_read(arg, 128)).split(b'\0')[0].decode())
        mu.reg_write(UC_X86_REG_EAX, STUBS + 0x20 if address == STUBS + 0x10 else 0x1234)
    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x30)
    draw(0, [(10.0, 20.0), (50.0, 20.0), (10.0, 60.0), (50.0, 60.0)], fvf=0x1e2)
    draw(10, text[:6])
    if lines != ['sr2 d q 000001e2 00000004 dead0000 41200000 41a00000 3f000000 80000000 00000000 ',
                 'sr2 d l 000001c4 00000006 dead0000 41200000 41a00000 3f000000 80000000 00000000 ']:
        raise SystemExit('widetest: the trace said %r' % (lines,))
    # barquad reports too: a strip at the right edge of a texture with a fill, then of one without
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
    # the device's viewport setter: the exe's 640x480 and a split half scaled, MGameGL's real one and a 640x480 picture's alone
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
    if setvp((0, 0, 640, 480)) != (True, (0, 0, 1920, 1080, 0.5, 0.5, 1.0, 1.0)):
        raise SystemExit('widetest: the device viewport for 640x480 came out %r' % (setvp((0, 0, 640, 480)),))
    if setvp((0, 240, 640, 480)) != (True, (0, 540, 1920, 1080, 0.5, 0.5, 1.0, 1.0)):
        raise SystemExit('widetest: the device viewport for a split half came out %r' % (setvp((0, 240, 640, 480)),))
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
