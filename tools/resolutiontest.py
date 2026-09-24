#!/usr/bin/env python3
"""Run the resolution row's routines under Unicorn.

    python3 tools/resolutiontest.py GAMEDIR     # GAMEDIR holds Options.dll

Patches a copy of Options.dll in memory, maps it relocated - which must
leave the patched sites as written - and stands in
for kernel32's profile routines, GetModuleFileNameA and the page's text
routine. Drives the row's init (the stock choice, then a wide size in
SR2.CFG), a draw of the row and the write-back on leaving, and checks the
row, the count, the text drawn and the profile write. Needs
python3-unicorn; exits 77 with a note when it is missing.
"""
import os
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('resolutiontest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                               UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_EFLAGS)

BASE = 0x02110000
STUBS = 0x03000000
SCRATCH = 0x04000000
STACK = 0x05000000
PAGE, SETTINGS, SPRITE, PLATES, PLATE6 = SCRATCH + 0x1000, SCRATCH + 0x2000, SCRATCH + 0x3000, SCRATCH + 0x4000, SCRATCH + 0x4100
ZF = 1 << 6


def cstr(mu, p):
    return bytes(mu.mem_read(p, 300)).split(b'\0')[0].decode('latin-1')


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    path = os.path.join(argv[1], 'Options.dll')
    if os.path.isfile(path + '.bak'):
        path += '.bak'
    with open(path, 'rb') as fh:
        raw = bytearray(fh.read())
    build = uctest.build_of(raw, 'Options.dll')
    if build is None:
        print('resolutiontest: %s is not an Options.dll the patcher knows' % path)
        return 1
    image = patcher.apply_resolution(raw, build)
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    annex = uctest.map_image(mu, image, BASE)
    mu.mem_map(STUBS, 0x1000)
    mu.mem_map(SCRATCH, 0x20000)
    # the sites as relocated must be as patched: no relocation entry may be left in them
    for site, length in ((patcher.RESOLUTION_INIT, 14), (patcher.RESOLUTION_COUNT, 13),
                         (patcher.RESOLUTION_DRAW, 8), (patcher.RESOLUTION_LEAVE, 12)):
        rva = patcher._off_to_rva(image, site)
        if bytes(mu.mem_read(BASE + rva, length)) != bytes(image[site:site + length]):
            raise SystemExit('resolutiontest: the site at 0x%x changed under relocation' % site)

    row = patcher.BUILDS[build]
    optbase = 0x10000000
    names = ['LoadLibraryA', 'GetProcAddress', 'GetModuleFileNameA', 'GetPrivateProfileStringA',
             'WritePrivateProfileStringA', 'text', 'draw']
    argc = {'LoadLibraryA': 1, 'GetProcAddress': 2, 'GetModuleFileNameA': 3, 'GetPrivateProfileStringA': 6,
            'WritePrivateProfileStringA': 4, 'text': 0, 'draw': 0}
    addr = {n: STUBS + 0x10 * k for k, n in enumerate(names)}
    for n in names:
        mu.mem_write(addr[n], b'\xc2' + struct.pack('<H', argc[n] * 4))
    for n, key in (('LoadLibraryA', 'LOADLIB'), ('GetProcAddress', 'GETPROC'), ('GetModuleFileNameA', 'GETMODFN')):
        mu.mem_write(BASE + row['options'][key] - optbase, struct.pack('<I', addr[n]))
    # the text routine fills its character map on first use (its first call, five bytes in); the
    # label drawn before the aspect's value has done it in the game, so it is done here first
    text_at = BASE + row['options']['TEXT'] - optbase
    if bytes(mu.mem_read(text_at + 5, 1)) != b'\xe8':
        raise SystemExit('resolutiontest: the text routine does not open with its map\'s fill')
    mapfill = text_at + 10 + struct.unpack('<i', mu.mem_read(text_at + 6, 4))[0]
    mu.mem_map(STACK, 0x100000)
    mu.mem_write(STACK + 0x8000, struct.pack('<I', 0xDEAD0000))
    mu.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
    mu.emu_start(mapfill, 0xDEAD0000, count=100000)
    for n, key in (('text', 'TEXT'), ('draw', 'DRAW')):
        at = BASE + row['options'][key] - optbase
        mu.mem_write(at, b'\xe9' + struct.pack('<i', addr[n] - (at + 5)))
    state = {'answer': b'', 'written': None, 'text': None, 'texts': [], 'plate': None}

    def stub(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        args = struct.unpack('<13I', mu.mem_read(esp + 4, 52))
        name = names[(address - STUBS) // 0x10]
        ret = 0
        if name == 'LoadLibraryA':
            ret = 7 if cstr(mu, args[0]) == 'kernel32.dll' else 0
        elif name == 'GetProcAddress':
            ret = addr.get(cstr(mu, args[1]), 0)
        elif name == 'GetModuleFileNameA':
            assert args[0] == 0
            mu.mem_write(args[1], b'C:\\game\\SEGA RALLY 2.exe\0')
            ret = 24
        elif name == 'GetPrivateProfileStringA':
            assert (cstr(mu, args[0]), cstr(mu, args[1]), cstr(mu, args[5])) == ('Display', 'Resolution', 'C:\\game\\SR2.CFG')
            mu.mem_write(args[3], state['answer'] + b'\0')
            ret = len(state['answer'])
        elif name == 'WritePrivateProfileStringA':
            assert (cstr(mu, args[0]), cstr(mu, args[1]), cstr(mu, args[3])) == ('Display', 'Resolution', 'C:\\game\\SR2.CFG')
            state['written'] = cstr(mu, args[2])
            ret = 1
        elif name == 'text':
            x, y = struct.unpack('<ff', mu.mem_read(esp + 8, 8))
            state['text'] = (cstr(mu, args[0]), x, y, args[7], args[12])   # the string, x, y, alpha, flags
            state['texts'].append(state['text'])
        elif name == 'draw':
            x, y, z = struct.unpack('<fff', mu.mem_read(esp + 8, 12))
            state['plate'] = (args[0], x, y, z, args[9], args[10], args[11], args[12])   # the sprite, x, y, z, alpha, r, g, b
        mu.reg_write(UC_X86_REG_EAX, ret)
        mu.reg_write(UC_X86_REG_ECX, 0x0C0C0C0C)      # as a real call would: only ebx, esi, edi, ebp survive
        mu.reg_write(UC_X86_REG_EDX, 0x0D0D0D0D)

    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x100)

    settings_ptr = BASE + row['addresses']['OPTSETTINGS'] - optbase
    mu.mem_write(settings_ptr, struct.pack('<I', SETTINGS))
    valtab = struct.unpack_from('<I', image, patcher.RESOLUTION_VALTAB)[0]
    mu.mem_write(BASE + valtab - optbase, struct.pack('<I', SPRITE))
    mu.mem_write(SPRITE, struct.pack('<I', SPRITE + 0x100))
    mu.mem_write(SPRITE + 0x100, struct.pack('<IIIfff', 0, 0, 0, 64.0, 14.0, 400.0) + struct.pack('<f', 250.0))   # x, y at +0x14, +0x18
    plates = struct.unpack_from('<I', image, patcher.RESOLUTION_PLATES)[0]
    mu.mem_write(BASE + plates - optbase + 6 * 4, struct.pack('<I', PLATE6))
    mu.mem_write(PLATE6, struct.pack('<IIIfff', 0, 0, 3, 426.0, 18.0, 107.0) + struct.pack('<f', 306.0))
    entry = BASE + annex

    def call(off, ebx=0, esi=PAGE, ecx=0):
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<I', 0xDEAD0000))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EBX, ebx)
        mu.reg_write(UC_X86_REG_ESI, esi)
        mu.reg_write(UC_X86_REG_ECX, ecx)
        mu.reg_write(UC_X86_REG_EBP, 0x7777)
        mu.emu_start(entry + off, 0xDEAD0000, count=1000000)
        if mu.reg_read(UC_X86_REG_ESP) != esp + 4 or mu.reg_read(UC_X86_REG_EBX) != ebx or mu.reg_read(UC_X86_REG_EBP) != 0x7777:
            raise SystemExit('resolutiontest: an entry left the stack or a register wrong')

    def page(off):
        return struct.unpack('<I', mu.mem_read(PAGE + off, 4))[0]

    G16_9 = 2                                               # the 16:9 group
    N16_9 = patcher.RESOLUTION_GROUPS[G16_9][2]              # and its sizes
    I1080 = patcher.RESOLUTIONS.index((1920, 1080)) - sum(n for _w, _h, n in patcher.RESOLUTION_GROUPS[:G16_9])
    # init: the stock choice 1 with no file: 4:3, its second; then a wide size in the file: its group and entry
    mu.mem_write(SETTINGS + 0x50, struct.pack('<I', 1))
    call(0, ebx=1, ecx=2)
    if (page(0x30), page(0x34), page(0x70), page(0x74), mu.reg_read(UC_X86_REG_ECX)) != (1, 0, 5, 5, 2):
        raise SystemExit('resolutiontest: init from the stock choice gave %r' % ((page(0x30), page(0x34), page(0x70), page(0x74)),))
    state['answer'] = b'1920x1080'
    call(0, ebx=1, ecx=2)
    if (page(0x30), page(0x34), page(0x70)) != (I1080, G16_9, N16_9):
        raise SystemExit('resolutiontest: init from the file gave %r' % ((page(0x30), page(0x34), page(0x70)),))
    state['answer'] = b'1234x567'
    call(0, ebx=1, ecx=2)
    if (page(0x30), page(0x34)) != (1, 0):
        raise SystemExit('resolutiontest: an unknown size in the file taken')
    # draw: another row goes on as before; row 6 draws the value and ends the loop
    mu.mem_write(PAGE + 0x38 + 2 * 4, struct.pack('<I', 3))
    call(5, ebx=2)
    if mu.reg_read(UC_X86_REG_EAX) != 3 or mu.reg_read(UC_X86_REG_EDI) != 0 or mu.reg_read(UC_X86_REG_EFLAGS) & ZF:
        raise SystemExit('resolutiontest: another row not drawn as before')
    state['answer'] = b'1920x1080'
    call(0, ebx=1, ecx=2)
    mu.mem_write(PAGE + 0x10, struct.pack('<I', 6))          # the cursor on the row
    mu.mem_write(PAGE + 0x78, struct.pack('<I', 0x40))        # the pulse
    mu.mem_write(PAGE + 0xc, struct.pack('<f', -30.0))        # the slide
    call(5, ebx=6)
    if not mu.reg_read(UC_X86_REG_EFLAGS) & ZF or mu.reg_read(UC_X86_REG_EDI) != 0:
        raise SystemExit('resolutiontest: the value row did not end the choice loop')
    if state['text'] != ('1920X1080', 400.0 - 30.0, 250.0, 0xa0, 4):
        raise SystemExit('resolutiontest: the value drawn as %r' % (state['text'],))
    # the aspect changed by the page: row 6 goes to the group's first, its count the group's
    mu.mem_write(PAGE + 0x34, struct.pack('<I', 3))           # 21:9
    call(5, ebx=6)
    first = '%dX%d' % patcher.RESOLUTIONS[sum(n for _w, _h, n in patcher.RESOLUTION_GROUPS[:3])]
    if (page(0x30), page(0x70)) != (0, patcher.RESOLUTION_GROUPS[3][2]) or state['text'][0] != first:
        raise SystemExit('resolutiontest: an aspect change gave %r %r' % ((page(0x30), page(0x70)), state['text']))
    # row 7: the plate a pitch under row 6's, red on the cursor's row, the label and the value's two parts and colon
    del state['texts'][:]
    mu.mem_write(PAGE + 0x10, struct.pack('<I', 7))
    call(5, ebx=7)
    if not mu.reg_read(UC_X86_REG_EFLAGS) & ZF or mu.reg_read(UC_X86_REG_EDI) != 0:
        raise SystemExit('resolutiontest: the aspect row did not end the choice loop')
    if state['plate'] != (PLATE6, 107.0 - 30.0, 306.0 + 27.0, 12.0, 0x100, 0x100, 0x20, 0x20):
        raise SystemExit('resolutiontest: the aspect row plate drawn as %r' % (state['plate'],))
    def width(text):
        """The text routine's advance of a string, from the DLL's own map and glyphs."""
        opt = patcher.BUILDS[build]['options']
        w = 0.0
        for ch in text.encode():
            g = struct.unpack('<b', mu.mem_read(BASE + opt['CHARMAP'] - 0x10000000 + ch, 1))[0]
            if g < 0:
                continue
            glyph = struct.unpack('<I', mu.mem_read(BASE + opt['GLYPHS'] - 0x10000000 + g * 4, 4))[0]
            w += struct.unpack('<f', mu.mem_read(glyph + 0xc, 4))[0] if glyph else 10.0
        return w
    colon = 270.0 - 30.0 + width('21')
    if width('21') == width('11') == width('M') == width('I') or not 10.0 < width('21') < 40.0:
        raise SystemExit('resolutiontest: the widths do not look measured: %r' % [width(t) for t in ('21', '11', 'M', 'I')])
    if state['texts'] != [('ASPECT RATIO', 107.0 - 30.0 + 10.0, 335.0, 0x100, 4), ('21', 270.0 - 30.0, 335.0, 0xa0, 4),
                          ('.', colon, 335.0, 0xa0, 4), ('.', colon, 329.0, 0xa0, 4), ('9', colon + 6.0, 335.0, 0xa0, 4)]:
        raise SystemExit('resolutiontest: the aspect row drawn as %r' % (state['texts'],))
    mu.mem_write(PAGE + 0x10, struct.pack('<I', 6))
    del state['texts'][:]
    call(5, ebx=7)
    if state['plate'][4:] != (0xd8, 0x100, 0x100, 0x100) or state['texts'][1][3] != 0x100:
        raise SystemExit('resolutiontest: the aspect row off the cursor drawn as %r %r' % (state['plate'], state['texts']))
    # leave: a wide row stores 0 and writes the group's size; a stock row stores itself
    mu.mem_write(PAGE + 0x34, struct.pack('<I', G16_9))
    mu.mem_write(PAGE + 0x30, struct.pack('<I', I1080))
    call(10)
    if struct.unpack('<I', mu.mem_read(SETTINGS + 0x50, 4))[0] != 0 or state['written'] != '1920x1080':
        raise SystemExit('resolutiontest: leaving with a wide size gave %r' % ((state['written'],)))
    mu.mem_write(PAGE + 0x34, struct.pack('<I', 0))
    mu.mem_write(PAGE + 0x30, struct.pack('<I', 1))
    call(10)
    if struct.unpack('<I', mu.mem_read(SETTINGS + 0x50, 4))[0] != 1 or state['written'] != '800x600':
        raise SystemExit('resolutiontest: leaving with 800x600 gave %r' % ((state['written'],)))
    # reset (DEFAULT): row 6 the defaults block's, row 7 4:3
    mu.mem_write(PAGE + 0x34, struct.pack('<I', G16_9))
    mu.mem_write(SCRATCH + 0x50, struct.pack('<I', 0))
    mu.reg_write(UC_X86_REG_EAX, SCRATCH)
    esp = STACK + 0x8000
    mu.mem_write(esp, struct.pack('<I', 0xDEAD0000))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.reg_write(UC_X86_REG_ESI, PAGE)
    mu.emu_start(entry + 15, 0xDEAD0000, count=10000)
    if (page(0x30), page(0x34), page(0x70), mu.reg_read(UC_X86_REG_ECX)) != (0, 0, 5, 5):
        raise SystemExit('resolutiontest: DEFAULT gave %r' % ((page(0x30), page(0x34), page(0x70)),))
    print('resolutiontest: %s Options.dll OK' % build)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
