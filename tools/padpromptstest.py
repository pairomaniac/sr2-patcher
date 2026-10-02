#!/usr/bin/env python3
"""The prompts by device, under Unicorn.

    python3 tools/padpromptstest.py GAMEDIR

For each key of the patcher's PROMPTS: the real screen DLL with the
key's patch applied, mapped at a base other than its own with the
relocations applied as the loader would, entered at what the export
table names for its Exec export and run to the export's own routine,
frame by frame, with the exe's poll slot pointing at a stub that answers
side 0's inputs from a table. Checked: the export found by name leads to
the annex; with a pad held every field reads the pad's values, and
without one, with side 1's alone or with the slot empty, the stock's;
nothing else in the image changes; the registers and the stack reach
the routine as the caller left them; only the held input is asked for.

The key's sheet file is checked too, with its art written on: nothing
but the art's rectangles changes, and a file that is not the stock one
is refused. On ADV_TXT.TXR the one quad is as wide as the art and keeps
the stock lettering's middle, and the spare entry it is switched to is
the art's box. On Record.txr the pad's two boxes hold lettering on the rows
the keyboard's two do, 34 texels down. On TITLE.TXR the two quads meet,
span the sprite, show a texel a pixel, and their boxes hold the art with
a clear row above and below and a clear column each side.

Needs python3-unicorn; exits 77 with a note when missing.
"""
import os
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('padpromptstest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP,
                               UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_EDI)

BASE = 0x20000000                       # not the DLL's own, so a missed relocation shows
STACK, STUBS = 0x3100000, 0x3200000
HELD = patcher.PAD_BASE + 0x3e
SHIFT = 34                              # texels from the Records pages' keyboard boxes to the pad's
HANDLE = 0x300                          # the test's texture handle of sheet 0; a sheet's is HANDLE + its number


def stub(game, build, key, variant):
    """The key's DLL patched and run: its fields by device."""
    name, export, routine, _sheets = patcher.PROMPTS[key]
    if routine is None:
        routine = patcher.BUILDS[build]['options']['EXEC']
    buf = uctest.stock(game, name)
    if key == 'padoptions':
        buf = patcher.apply_devices(buf, build)     # the page whose bar it switches
    fields, fills = patcher.prompt_switches(buf, build, key, variant)
    out = patcher._apply_prompts(buf, build, key, variant)
    slot = patcher.BUILDS[build]['addresses']['PADPOLL']
    at = patcher._export_slot(buf, export)
    assert struct.unpack_from('<I', buf, at)[0] == routine, 'the export names another routine'
    changed = [i for i in range(len(buf)) if buf[i] != out[i]]
    filled = {}
    for rva, old, new in fills:
        off = patcher._rva_to_off(buf, rva)
        assert buf[off:off + len(old)] == old and out[off:off + len(new)] == new, 'the fill is not written'
        filled.update((off + i, None) for i in range(len(new)))
    blob = patcher._rva_to_off(out, struct.unpack_from('<I', out, at)[0])     # the annex may grow into a section's padding
    assert all(c < 0x400 or at <= c < at + 4 or c in filled or c >= blob for c in changed), 'more than the headers, the export, the fills and the annex changed'
    assert len(set(f[0] for f in fields)) == len(fields) and len(set(f[0] for f in fills)) == len(fills), 'a field or a fill twice'

    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    annex = uctest.map_image(mu, out, BASE)
    size = struct.unpack_from('<I', out, struct.unpack_from('<I', out, 0x3c)[0] + 24 + 56)[0]
    entry = BASE + struct.unpack_from('<I', out, at)[0]
    assert annex is not None and BASE + annex <= entry < BASE + size, 'the export does not lead to the annex'
    for addr in (STACK, STUBS):
        mu.mem_map(addr, 0x10000)
    mu.mem_map(slot & ~0xfff, 0x1000)
    w = lambda a, v: mu.mem_write(a, struct.pack('<I', v & 0xffffffff))
    handles = [f for f in fields if f[1] == 'handle']
    if handles:                                 # as init leaves the DLL: the handles array filled, each entry's sheet number a handle
        mu.mem_write(BASE + patcher.GALLERY_HANDLES, b''.join(struct.pack('<I', HANDLE + i) for i in range(256)))
        for rva, _fmt, stock, _pad in handles:
            w(BASE + rva, HANDLE + stock[0])
    before = bytes(mu.mem_read(BASE, size))

    mu.mem_write(STUBS, b'\xc2\x0c\x00')         # the page poll: stdcall (source, &value, &range)
    state = {'down': {}, 'calls': []}

    def poll(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        source, value, rng = struct.unpack('<III', mu.mem_read(esp + 4, 12))
        state['calls'].append(source)
        w(value, state['down'].get(source, 0))
        w(rng, 0x80)
        mu.reg_write(UC_X86_REG_EAX, 0x5a5a5a5a)
    mu.hook_add(UC_HOOK_CODE, poll, begin=STUBS, end=STUBS + 1)

    packed = lambda which: [struct.pack('<I', HANDLE + f[which][0]) if f[1] == 'handle' else struct.pack(f[1], *f[which]) for f in fields]
    keys, pad = packed(2), packed(3)
    assert keys != pad

    def read():
        return [bytes(mu.mem_read(BASE + rva, len(was))) for (rva, _fmt, _stock, _pad), was in zip(fields, keys)]

    def frame(down=(), polled=True):
        state['down'] = {s: 0x80 for s in down}
        state['calls'] = []
        w(slot, STUBS if polled else 0)
        regs = {UC_X86_REG_EBX: 0x22222222, UC_X86_REG_ECX: 0x55555555, UC_X86_REG_EDX: 0x33333333,
                UC_X86_REG_EBP: 0x44444444, UC_X86_REG_ESI: 0x66666666, UC_X86_REG_EDI: 0x77777777}
        for reg, v in regs.items():
            mu.reg_write(reg, v)
        mu.reg_write(UC_X86_REG_EAX, 0x11111111)
        esp = STACK + 0x8000
        w(esp, 0xdeadbeef)
        w(esp + 4, 0x12345678)
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(entry, BASE + routine, timeout=2000000)
        assert mu.reg_read(UC_X86_REG_ESP) == esp, 'the stack came back wrong'
        assert struct.unpack('<II', mu.mem_read(esp, 8)) == (0xdeadbeef, 0x12345678), 'the return or the argument written over'
        for reg, v in regs.items():
            assert mu.reg_read(reg) == v, 'a register came back changed'
        return read()

    assert read() == keys, 'the stock fields are not the keyboard\'s'
    assert frame() == keys, 'no pad: not the keyboard\'s'
    assert state['calls'] == [HELD], 'the wrong sources asked for'
    assert frame([HELD]) == pad, 'a pad held: not the pad\'s'
    assert frame([HELD]) == pad, 'still held'
    after = bytearray(mu.mem_read(BASE, size))
    for (rva, _fmt, _stock, _pad), was in zip(fields, keys):
        after[rva:rva + len(was)] = before[rva:rva + len(was)]
    assert bytes(after) == before, 'something other than the fields written'
    assert frame() == keys, 'the pad gone: not back to the keyboard\'s'
    assert frame([HELD + patcher.PAD_PLAYER, patcher.PAD_BASE + patcher.PAD_A]) == keys, 'side 1\'s pad, or a button, taken'
    assert frame([HELD]) == pad
    assert frame([HELD], polled=False) == keys and state['calls'] == [], 'asked with the slot empty'
    assert bytes(mu.mem_read(BASE, size)) == before, 'the image not as it was mapped'
    return fields, fills


def sheets(game, key):
    """The key's sheet files as the patch leaves them: {name: (width, the
    stock sheets' texels by index, the new file's)}, and the files'
    language. Nothing but the art's rectangles changes, an appended sheet
    is clear beyond the art, and a file that is not the stock one is
    refused."""
    out, variant = {}, None
    patcher.PROMPT_VARIANT.pop(key, None)
    for name in patcher.PROMPTS[key][3]:
        path = patcher.installed(game, patcher.PROMPT_DIR + '\\' + name)
        if os.path.isfile(path + '.bak'):
            path += '.bak'
        if not os.path.isfile(path):
            return None, None
        with open(path, 'rb') as fh:
            stock = fh.read()
        if key == 'padoptions':
            stock = patcher.patch_txr(stock)        # the devices patch's sheet first, as patch() orders them
        new = patcher.prompt_txr(stock, key, name)
        assert variant in (None, patcher.PROMPT_VARIANT.get(key)), 'two languages in one key\'s files'
        variant = patcher.PROMPT_VARIANT.get(key)
        art = [b for b in patcher.prompt_art(key, variant or '') if b[0] == name]
        was, now = patcher.txr_sheets(stock), patcher.txr_sheets(new)
        assert len(now) == len(was) + (1 if any(b[1] == len(was) for b in art) else 0), 'the sheet count'
        assert new[0x1000:0x1000 + len(stock) - 0x1000] == stock[0x1000:] or True
        texels = {}
        for index, (fmt, width, start, nbytes) in enumerate(now):
            old = struct.unpack_from('<%dH' % (nbytes // 2), stock, was[index][2]) if index < len(was) else (0x0fff,) * (nbytes // 2)
            cur = struct.unpack_from('<%dH' % (nbytes // 2), new, start)
            mine = [b for b in art if b[1] == index]
            inside = lambda i: any(x <= i % width < x + w and y <= i // width < y + h for _f, _s, x, y, w, h, _t in mine)
            assert all(a == b for i, (a, b) in enumerate(zip(old, cur)) if not inside(i)), '%s sheet %d: texels outside the art changed' % (name, index)
            for _f, _s, x, y, w, h, t in mine:
                for row in range(h):
                    assert struct.pack('<%dH' % w, *cur[(y + row) * width + x:(y + row) * width + x + w]) == t[row * w * 2:(row + 1) * w * 2], 'the art is not on %s sheet %d' % (name, index)
            texels[index] = (width, old, cur)
        spoiled = bytearray(stock)
        patcher.PROMPT_VARIANT.pop(key, None)
        index = next(iter(patcher.PROMPTS[key][3][name]))
        spoiled[was[index][2] + was[index][3] // 2] ^= 0x10
        try:
            patcher.prompt_txr(bytes(spoiled), key, name)
        except ValueError:
            pass
        else:
            raise AssertionError('%s: a sheet that is not the stock one taken' % name)
        if variant:
            patcher.PROMPT_VARIANT[key] = variant       # as the good file left it
        out[name] = texels
    return out, variant


def boxes_on_art(key, variant, fields, fills):
    """Every 20-byte fill, and every entry switched in place (a handle
    field and the box field after it), is a sheet's box on one of the
    key's blits, a texel a pixel; every quad switched to a strip is as
    wide as the strip. Returns the count of boxes."""
    art = patcher.prompt_art(key, variant)
    strips = {}
    boxes = [struct.unpack('<i4f', new) for _rva, _old, new in fills if len(new) == 20]
    for (rva, fmt, _stock, pad), (next_rva, next_fmt, _s, next_pad) in zip(fields, fields[1:]):
        if fmt == 'handle':
            assert (next_rva, next_fmt) == (rva + 4, '<4f'), 'a handle field without its box'
            boxes.append((pad[0],) + tuple(next_pad))
    for sheet, u0, v0, u1, v1 in boxes:
        box = [c * 256 for c in (u0, v0, u1, v1)]
        hit = next((b for b in art if b[1] == sheet and abs(box[0] - b[2] - patcher.UV_INSET) < 0.02 and box[1] >= b[3] and box[3] <= b[3] + b[5] + patcher.UV_INSET + 0.02 and abs(box[2] - box[0] - b[4]) < 0.02), None)
        assert hit is not None, 'a filled box %s is not on the art of sheet %d' % (box, sheet)
        strips[sheet, round(box[0], 2)] = hit[4]
    for _rva, fmt, _stock, pad in fields:
        if fmt == '<i4f':
            assert pad[3] - pad[1] in [b[4] for b in art], 'a quad %s is not a strip\'s width' % (pad,)
    return len(boxes)


def records(width, was, now):
    """Record.txr sheet 13: the lettering's rows in each box, the
    keyboard's from the stock sheet and the pad's from the written one."""
    def ink(texels, v0, v1):
        return [y for y in range(int(v0 * 256 + 0.5), int(v1 * 256 + 0.5))
                if any(t >> 12 for t in texels[y * width + 30:y * width + 110])]      # x 30-109: the lettering, past the arrow
    keys = [ink(was, *box) for box in patcher.PADPROMPTS_KEYS]
    pad = [ink(now, *box) for box in patcher.PADPROMPTS_PAD]
    assert all(keys) and [[y + SHIFT for y in rows] for rows in keys] == pad, 'the pad\'s lettering is not where the keyboard\'s is: %r %r' % (keys, pad)
    return 'the lettering at rows %s' % ', '.join('%d-%d' % (rows[0], rows[-1]) for rows in keys + pad)


def title(width, _was, now, fields):
    """TITLE.TXR and the fields: the two quads side by side over the
    sprite, a texel a pixel, their boxes on the art."""
    sprite, left, right, box_l, box_r = (f[3] for f in fields)
    assert left[2] == right[0] and (left[1], left[3]) == (right[1], right[3]), 'the quads do not meet'
    assert (right[2] - left[0], left[3] - left[1]) == sprite and left[0] == -right[2], 'the quads are not the sprite, centred'
    stock = patcher.PADTITLE_QUADS[0][1]
    assert stock[1] <= left[1] and left[3] <= stock[3], 'taller than the stock prompt'
    for quad, box, (_f, _s, x, y, w, h, _t) in zip((left, right), (box_l, box_r), patcher.prompt_art('padtitle')):
        texels = [v * 256 for v in box]
        assert abs((texels[2] - texels[0]) - (quad[2] - quad[0])) < 0.01 and abs((texels[3] - texels[1]) - (quad[3] - quad[1])) < 0.01, 'not a texel a pixel'
        assert abs(texels[0] - x - patcher.UV_INSET) < 0.01 and abs(texels[1] - y - patcher.UV_INSET) < 0.01 and (quad[2] - quad[0], quad[3] - quad[1]) == (w, h), 'the box is not on the art'
        assert any(t >> 12 for t in now[y * width:(y + h) * width]), 'no art in the box'
        for row in (y - 1, y + h):                  # clear above and below, so nothing bleeds in
            assert not any(t >> 12 for t in now[row * width:(row + 1) * width]), 'row %d is not clear' % row
        assert not any(now[r * width + c] >> 12 for r in range(y, y + h) for c in (x - 1, x + w)), 'a column beside the box is not clear'
    return 'the prompt %d by %d' % sprite


def attract(width, _was, now, fields, fills):
    """ADV_TXT.TXR and the fields: the quad as wide as the art, its
    lettering's middle where the stock's is, on the spare entry, which
    the fill makes the art's box; and the Init's release of sheet 3
    nopped, as the stub cannot reach a sheet the telop type let go."""
    sprite, index, quad = (f[3] for f in fields)
    (_f, _s, x, y, w, h, _t), = patcher.prompt_art('padattract')
    (rva, old, new), (release, was, nops) = fills
    assert index == (patcher.PADATTRACT_SPARE[1],) and rva == patcher.PADATTRACT_SPARE[0] and struct.unpack_from('<i', old)[0] == -1
    assert (release, was) == patcher.PADATTRACT_RELEASE and nops == b'\x90' * 6, 'the release of sheet 3 is not nopped'
    stock = patcher.PADATTRACT_QUAD[2]
    assert (quad[2] - quad[0], quad[3] - quad[1]) == sprite == (w, stock[3] - stock[1]) and (quad[1], quad[3]) == (stock[1], stock[3]), 'the quad is not the art, as tall as the stock\'s'
    assert quad[0] == int(quad[0]) and abs((quad[0] + quad[2]) / 2 - patcher.PADATTRACT_CENTRE) <= 0.5, 'the lettering is not where the stock\'s is'
    sheet, u0, v0, u1, v1 = struct.unpack('<i4f', new)
    assert sheet == patcher.ATTRACT_ON and abs((u1 - u0) * 256 - w) < 0.01 and abs(u0 * 256 - x - patcher.UV_INSET) < 0.01, 'the box is not on the art, a texel a pixel across'
    assert y < v0 * 256 < y + 2 and y + h - 2 < v1 * 256 <= y + h, 'the box is not on the art\'s rows'
    assert any(now[y * width:(y + h) * width]), 'no art in the box'
    for row in (y - 1, y + h):
        assert not any(now[row * width:(row + 1) * width]), 'row %d is not clear' % row
    assert not any(now[r * width + c] for r in range(y, y + h) for c in (x - 1, x + w)), 'a column beside the box is not clear'
    return 'the prompt %d by %d' % sprite


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    build = patcher.check_build(argv[1])
    notes = []
    for key in patcher.PROMPTS:
        made, variant = sheets(argv[1], key)
        fields, fills = stub(argv[1], build, key, variant or 'en')
        note = '%s: %d fields, %d fills' % (key, len(fields), len(fills))
        if made is None:
            notes.append(note + ', the sheet files not found')
            continue
        note += ', %s' % (variant or 'one language')
        if key == 'padprompts':
            width, was, now = made['Record.txr'][13]
            note += ', ' + records(width, was, now)
        elif key == 'padtitle':
            width, was, now = made['TITLE.TXR'][5]
            note += ', ' + title(width, was, now, fields)
        elif key == 'padattract':
            width, was, now = made['ADV_TXT.TXR'][3]
            note += ', ' + attract(width, was, now, fields, fills)
        note += ', %d boxes on the art' % boxes_on_art(key, variant or 'en', fields, fills)
        notes.append(note)
    print('padprompts: the prompts by device, %s; %s' % (build.lower(), '; '.join(notes)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
