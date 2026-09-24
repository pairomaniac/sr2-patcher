#!/usr/bin/env python3
"""Run the .bg copies of the windowed and title patches under Unicorn.

    python3 tools/bgrowtest.py

BGROW_BLOB and TITLEROW_BLOB are called with the rows of a small 565
picture as the game calls the copies they replace: eax the row's byte
count, ebx the source row, edx the destination row, the lock description
at its place (the exe's global, Title.dll's stack) and the picture's
height where each loop keeps it. With the surface the picture's size a
16-bit row must come out byte for byte, a 32-bit one as XRGB8888 with the
low bits replicated. With a larger surface the whole picture must land on
the first row, scaled to fit with its aspect kept and centred on black,
and the rows after must touch nothing, with a bar each side: in
Title.dll's build the picture's own sliver beyond the drawn edge, blurred
across and stretched over it; in the exe's the picture's corner pixel. eax and edx must survive, and ebx
too for the exe's, advanced by a row for Title.dll's. Needs
python3-unicorn; exits 77 with a note when it is missing.
"""
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('bgrowtest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EDX,
                               UC_X86_REG_ESP)

CODE, DESC, SRC, DST, STACK, OBJ = 0x400000, 0x4e6000, 0x1000000, 0x1008000, 0x3000000, 0x2000000
LOCKDESC = patcher.BUILDS['European']['addresses']['LOCKDESC']
GAMED3D = patcher.BUILDS['European']['addresses']['GAMED3D']
D3D, D3DIMAGE, BGSURF, BGPIX = 0x2100000, 0x3200000, 0x2200000, 0x4000000   # a device object, a stand-in MGameD3D
BLOCK = D3DIMAGE + 0x17000 + 0x40                                            # image, the .bg surface, its pixels
BGSURFW, BGSURFH = 2176, 600
PIXELS = (0x0000, 0xffff, 0xf800, 0x07e0, 0x001f, 0x8410, 0x1234, 0x4321)   # a 4x2 picture
SRC_W, SRC_H = 4, 2


BIG_W, BIG_H = 64, 32                           # a picture wide enough for its stretch to show columns
DIM = 0x66                                      # the bars' brightness against the picture's


def big_picture():
    """A picture whose columns differ, so the stretch of it shows them."""
    return [((x >> 1) & 31) << 11 | ((y >> 1) & 63) << 5 | ((x + y) & 31) for y in range(BIG_H) for x in range(BIG_W)]


def blurred(row, src_w, first, last, dim):
    """A sliver of a row box-blurred as bgrow does it: each column the
    mean, channel by channel, of the columns a sixty-fourth of the width
    either side of it that the sliver has, dimmed."""
    reach = max(src_w >> 6, 1)
    out = [None] * src_w
    for c in range(first, last + 1):
        box = row[max(c - reach, first):min(c + reach, last) + 1]
        r = (sum(p >> 11 for p in box) // len(box)) * dim >> 8
        g = (sum((p >> 5) & 63 for p in box) // len(box)) * dim >> 8
        b = (sum(p & 31 for p in box) // len(box)) * dim >> 8
        out[c] = r << 11 | g << 5 | b
    return out


def stretched(pixels, src_w, src_h, dst_w, drawn_w, drawn_h, dst_h, title):
    """The bars as bgrow draws them: the whole picture stretched to the
    surface's width, nearest pixel, the drawn one covering the middle;
    rows above and below the picture take its first and last. In
    Title.dll's build each sliver is blurred across within itself and
    dimmed; in the exe's each bar is the picture's corner pixel throughout."""
    bar = (dst_w - drawn_w) // 2
    top = (dst_h - drawn_h) // 2
    ystep, xstep = (src_h << 16) // drawn_h, (src_w << 16) // dst_w
    lfirst, llast = 0, ((bar * xstep) >> 16)
    rfirst, rlast = ((bar + drawn_w) * xstep) >> 16, src_w - 1
    rows = [pixels[y * src_w:(y + 1) * src_w] for y in range(src_h)]
    out = []
    for y in range(dst_h):
        row = min(max(y - top, 0) * ystep >> 16, src_h - 1) if y >= top else 0
        if y >= top + drawn_h:
            row = min(((drawn_h - 1) * ystep) >> 16, src_h - 1)
        if title:
            soft = blurred(rows[row], src_w, lfirst, llast, DIM)
            soft = [a if a is not None else b for a, b in zip(soft, blurred(rows[row], src_w, rfirst, rlast, DIM))]
            line = [soft[(x * xstep) >> 16] for x in range(dst_w)]
            out.append((line[:bar], line[bar + drawn_w:]))
        else:
            out.append(([pixels[0]] * bar, [pixels[0]] * (dst_w - bar - drawn_w)))
    return out


def composed(pixels, src_w, src_h, dst_w, drawn_w, drawn_h, dst_h, title):
    """The composite bgrow leaves in MGameD3D's surface, for one stretch to
    the whole screen: the picture at source size in the middle, each side
    area as the sliver its bar shows - src_w * bar / dst_w columns,
    blurred and dimmed in Title.dll's build, the picture's corner pixel in the
    exe's - stretched into bar / scale columns, nearest, so the one stretch
    after makes the bar's own; bands above and below the first and last
    composed rows. Returns (cw, ch, rows)."""
    bar, top = (dst_w - drawn_w) // 2, (dst_h - drawn_h) // 2
    s, t = bar * src_w // drawn_w, top * src_h // drawn_h
    n = min(src_w * bar // dst_w + 2, src_w)
    step = (drawn_w << 16) // dst_w
    rows = [pixels[y * src_w:(y + 1) * src_w] for y in range(src_h)]
    out = []
    for row in rows:
        if s:
            if title:
                left = blurred(row, src_w, 0, n - 1, DIM)
                right = blurred(row, src_w, src_w - n, src_w - 1, DIM)[src_w - n:]
            else:
                left, right = [pixels[0]] * n, [pixels[0]] * n
            line = [left[(x * step) >> 16] for x in range(s)] + row + [right[(x * step) >> 16] for x in range(s)]
        else:
            line = list(row)
        out.append(line)
    out = [out[0]] * t + out + [out[-1]] * t
    return src_w + 2 * s, src_h + 2 * t, out


def expand(p):
    r, g, b = (p >> 11) & 0x1f, (p >> 5) & 0x3f, p & 0x1f
    return ((r << 3 | r >> 2) << 16) | ((g << 2 | g >> 4) << 8) | (b << 3 | b >> 2)


def run(bpp, title, dst_w, dst_h, pixels=None, src_w=None, src_h=None, surface=False, wrongvtable=False, lockpitch=None):
    """The rows of the picture copied into a dst_w x dst_h surface of the
    given depth: the surface's pixels, row by row, and the register check.
    With surface, a stand-in MGameD3D is there with the .bg block in its
    annex and a surface in it: what comes back is that surface's pixels
    over the composite's size, the block's size and flag, the lock calls
    and the destination untouched."""
    pixels = PIXELS if pixels is None else pixels
    src_w = SRC_W if src_w is None else src_w
    src_h = SRC_H if src_h is None else src_h
    blob = patcher.exe_blob(patcher.TITLEROW_BLOB if title else patcher.BGROW_BLOB, 'European')
    src = b''.join(p.to_bytes(2, 'little') for p in pixels)
    width = 4 if bpp == 32 else 2
    pitch = dst_w * width + 16
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr in (CODE, DESC, OBJ, D3D, BGSURF):
        mu.mem_map(addr, 0x1000)
    mu.mem_map(SRC, 0x20000)                    # the destination sits inside this one too
    mu.mem_map(STACK, 0x10000)
    mu.mem_map(GAMED3D & ~0xfff, 0x1000)
    mu.mem_write(GAMED3D, struct.pack('<I', D3D if surface else 0))
    mu.mem_write(CODE, blob)
    locks = []
    if surface:
        # the device's vtable at the stand-in's VTABLE_RVA with the quad draw where MGameD3D keeps it, an MZ and
        # a size in its header, the marker and the block in its annex, and a surface whose Lock hands out BGPIX
        # at the surface's pitch and depth
        mu.mem_map(D3DIMAGE, 0x18000)
        mu.mem_map(BGPIX, (BGSURFW * 4 * BGSURFH + 0xfff) & ~0xfff)
        mu.mem_write(D3D, struct.pack('<I', D3DIMAGE + 0xf5d4))
        mu.mem_write(D3DIMAGE + 0xf5d4 + 0xb4, struct.pack('<I', D3DIMAGE + (0x5130 if wrongvtable else 0x5120)))
        mu.mem_write(D3DIMAGE, b'MZ' + b'\0' * 0x3a + struct.pack('<I', 0x80))
        mu.mem_write(D3DIMAGE + 0x80 + 0x50, struct.pack('<I', 0x18000))
        mu.mem_write(BLOCK - 8, b'BGBLOCK\0' + struct.pack('<5I', BGSURF, 0, 0, 0, 0))
        mu.mem_write(BGSURF, struct.pack('<I', BGSURF + 0x100))
        mu.mem_write(BGSURF + 0x100 + 0x64, struct.pack('<I', BGSURF + 0x200))
        mu.mem_write(BGSURF + 0x100 + 0x80, struct.pack('<I', BGSURF + 0x210))
        mu.mem_write(BGSURF + 0x200, b'\xc2\x14\x00' + b'\x90' * 13 + b'\xc2\x08\x00')
        mu.mem_write(BGPIX, b'\xaa' * (BGSURFW * width * BGSURFH))

        def lock(mu, address, size_, user):
            esp = mu.reg_read(UC_X86_REG_ESP)
            if address == BGSURF + 0x200:
                this, rect, desc, flags, event = struct.unpack('<IIIII', mu.mem_read(esp + 4, 20))
                locks.append(('lock', this, rect, flags))
                mu.mem_write(desc + 0x10, struct.pack('<I', BGSURFW * width if lockpitch is None else lockpitch))
                mu.mem_write(desc + 0x24, struct.pack('<I', BGPIX))
                mu.mem_write(desc + 0x54, struct.pack('<I', bpp))
            else:
                locks.append(('unlock', struct.unpack('<I', mu.mem_read(esp + 4, 4))[0]))
            mu.reg_write(UC_X86_REG_EAX, 0)
        mu.hook_add(UC_HOOK_CODE, lock, begin=BGSURF + 0x200, end=BGSURF + 0x213)
    mu.mem_write(SRC, src)
    mu.mem_write(DST, b'\xaa' * (pitch * dst_h))
    desc = bytearray(0x7c)
    struct.pack_into('<III', desc, 8, dst_h, dst_w, pitch)
    struct.pack_into('<I', desc, 0x24, DST)
    struct.pack_into('<I', desc, 0x54, bpp)
    end = CODE + len(blob)
    esp = STACK + 0x8000
    mu.mem_write(esp, end.to_bytes(4, 'little'))
    if title:
        mu.mem_write(esp + 0x1c, bytes(desc))
    else:
        mu.mem_write(LOCKDESC, bytes(desc))
        mu.mem_write(OBJ, struct.pack('<II', 0, OBJ + 0x100))    # the loop's object: +4 the picture
        mu.mem_write(OBJ + 0x100, struct.pack('<III', 0, src_w, src_h))
        mu.mem_write(esp + 4 + 0x18, OBJ.to_bytes(4, 'little'))
    row_bytes = src_w * 2
    for row in range(src_h):
        if title:
            mu.mem_write(esp + 4 + 0x10, (src_h - row).to_bytes(4, 'little'))     # rows still to copy
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EAX, row_bytes)
        mu.reg_write(UC_X86_REG_EBX, SRC + row * row_bytes)
        mu.reg_write(UC_X86_REG_EDX, DST + row * pitch)
        mu.emu_start(CODE, end, timeout=2000000)
        regs = tuple(mu.reg_read(r) for r in (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EDX))
        want = (row_bytes, SRC + row * row_bytes + (row_bytes if title else 0), DST + row * pitch)
        if regs != want:
            raise SystemExit('bgrowtest: registers wrong at %d bpp%s, row %d: %r'
                             % (bpp, ', title' if title else '', row, regs))
    out = bytes(mu.mem_read(DST, pitch * dst_h))
    rows = [[int.from_bytes(out[y * pitch + x * width:y * pitch + (x + 1) * width], 'little')
             for x in range(dst_w)] for y in range(dst_h)]
    if not surface:
        return rows
    surf, made_for, pending, cw, ch = struct.unpack('<5I', mu.mem_read(BLOCK, 20))
    pix = bytes(mu.mem_read(BGPIX, BGSURFW * width * ch)) if ch else b''
    composite = [[int.from_bytes(pix[y * BGSURFW * width + x * width:y * BGSURFW * width + (x + 1) * width], 'little')
                  for x in range(cw)] for y in range(ch)]
    return rows, (pending, cw, ch), composite, locks


def main():
    picture = [list(PIXELS[:4]), list(PIXELS[4:])]
    for title in (False, True):
        where = 'Title.dll' if title else 'the exe'
        if run(16, title, SRC_W, SRC_H) != picture:
            raise SystemExit('bgrowtest: 16-bit rows not copied as is, %s' % where)
        got = run(32, title, SRC_W, SRC_H)
        if got != [[expand(p) for p in row] for row in picture]:
            raise SystemExit('bgrowtest: 32-bit rows wrong, %s: %r' % (where, got))
        # twice the size: each source pixel becomes 2x2, the bars the picture's own ends stretched over them
        got = run(16, title, 12, 4)
        bars = stretched(PIXELS, SRC_W, SRC_H, 12, 8, 4, 4, title)
        want = [bars[y][0] + [p for p in picture[y // 2] for _ in range(2)] + bars[y][1] for y in range(4)]
        if got != want:
            raise SystemExit('bgrowtest: scaled 16-bit picture wrong, %s: %r' % (where, got))
        # a wider picture, stretched five times: the bars are the picture's own columns, nearest, and not one colour
        big = big_picture()
        got = run(16, title, 320, 32, big, BIG_W, BIG_H)
        bars = stretched(big, BIG_W, BIG_H, 320, 64, 32, 32, title)
        bar = (320 - 64) // 2
        if any((row[:bar], row[bar + 64:]) != bars[y] for y, row in enumerate(got)):
            raise SystemExit('bgrowtest: the stretched bars wrong, %s: %r' % (where, got[0][:bar]))
        if title and len(set(got[0][:bar])) < 4:
            raise SystemExit('bgrowtest: the bar did not carry the picture across, %s: %r' % (where, got[0][:bar]))
        # with MGameD3D's surface there, the picture is composed into it at source size and the destination is
        # not touched; the block carries the composite's size and the flag, the surface locked once and unlocked
        for bpp in (16, 32):
            rows, block, comp, locks = run(bpp, title, 320, 32, big, BIG_W, BIG_H, surface=True)
            cw, ch, want = composed(big, BIG_W, BIG_H, 320, 64, 32, 32, title)
            if bpp == 32:
                want = [[expand(p) for p in line] for line in want]
            if any(set(r) != {0xaaaa if bpp == 16 else 0xaaaaaaaa} for r in rows):
                raise SystemExit('bgrowtest: the destination was drawn on with a surface there, %s at %d' % (where, bpp))
            if block != (1, cw, ch):
                raise SystemExit('bgrowtest: the block came out %r, not %r, %s at %d' % (block, (1, cw, ch), where, bpp))
            if comp != want:
                bad = next((y, x) for y in range(ch) for x in range(cw) if comp[y][x] != want[y][x])
                raise SystemExit('bgrowtest: the composite differs at %r: %r not %r, %s at %d'
                                 % (bad, comp[bad[0]][bad[1]], want[bad[0]][bad[1]], where, bpp))
            if locks != [('lock', BGSURF, 0, 1), ('unlock', BGSURF)]:
                raise SystemExit('bgrowtest: the surface was locked wrong: %r, %s' % (locks, where))
        # a surface whose lock reports a pitch too short for the composite's rows is unlocked and left alone:
        # drawn as before
        rows, block, comp, locks = run(32, title, 320, 32, big, BIG_W, BIG_H, surface=True, lockpitch=64)
        if block[0] or locks != [('lock', BGSURF, 0, 1), ('unlock', BGSURF)] or any(set(r) == {0xaaaaaaaa} for r in rows):
            raise SystemExit('bgrowtest: a surface too narrow for the composite was composed into, %s' % where)
        # a device whose vtable is not MGameD3D's - the quad draw elsewhere - is left alone: drawn as before
        rows, block, comp, locks = run(16, title, 320, 32, big, BIG_W, BIG_H, surface=True, wrongvtable=True)
        if block[0] or locks or any(set(r) == {0xaaaa} for r in rows):
            raise SystemExit('bgrowtest: a stranger\'s vtable was taken for MGameD3D\'s, %s' % where)
        # letterboxed the same way: bands above and below, two rows each here, and the sides empty
        for bpp in (16, 32):
            rows, block, comp, locks = run(bpp, title, 8, 12, surface=True)
            cw, ch, want = composed(PIXELS, SRC_W, SRC_H, 8, 8, 4, 12, title)
            if bpp == 32:
                want = [[expand(p) for p in line] for line in want]
            if block != (1, cw, ch) or comp != want:
                raise SystemExit('bgrowtest: the letterboxed composite came out %r %r, not %r %r, %s at %d'
                                 % (block, comp, (1, cw, ch), want, where, bpp))
        got = run(32, title, 8, 6)     # letterboxed: a row of black above and below
        want = ([[0] * 8] + [[expand(p) for p in row for _ in range(2)] for row in picture for _ in range(2)]
                + [[0] * 8])
        if got != want:
            raise SystemExit('bgrowtest: scaled 32-bit picture wrong, %s: %r' % (where, got))
    print('bgrow: 16-bit copy, 32-bit expand and the scaled picture OK, exe and Title.dll')
    return 0


if __name__ == '__main__':
    sys.exit(main())
