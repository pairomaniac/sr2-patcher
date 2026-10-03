#!/usr/bin/env python3
"""The team room's TAB button by device, under Unicorn.

    python3 tools/tabmenutest.py

tabmenu.asm with the European build's addresses in place, its five
entries called as their sites are, with the exe's loader, its release,
the surfaces' SetTarget and Blit and the annex's poll played by stubs.
Checked: room passes the site's seven loader arguments on unchanged,
then loads TAB_MENU_BACK.BMP and TAB_MENU_BACK_SEL.BMP with the same
arguments but the name (context, directory 0xc, flag 0, name, &object,
&size, 1); init loads TAB_MENU_SEL.BMP and TAB_MENU_SEL2.BMP, calls each
new object's SetTarget (+0x34) with the first chat object and then with
0, blits nothing, and ends with the site's own load; frame asks for one
input, side 0's pad, and nothing with the slot empty or nothing loaded;
while the menu's objects are loaded it writes the array's two TAB
entries as the pad's or the stock's; while the backdrop's are, and the
answer has changed, it blits the backdrop's box - SEL or stock - onto
the backdrop at (18, 454), whole, the target set to the backdrop before
and to 0 after, not again while the answer holds, and not at all
without a backdrop; free puts the stock entries back and releases the
two buttons once each; roomfree releases the backdrop's two, and the
buttons too when the menu was still open, so nothing is released twice
and a frame after it writes nothing. The registers come back as they
were at every entry.

Needs python3-unicorn; exits 77 with a note when it is missing.
"""
import struct

from uctest import patcher
import uctest

uctest.unicorn('tabmenutest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EBP,
                               UC_X86_REG_ESI, UC_X86_REG_EDI)

CODE, STUBS, STACK, OBJECTS = 0x900000, 0xa00000, 0xb00000, 0xc00000
ROW = patcher.BUILDS['European']
A = ROW['addresses']
LOAD, FREE, CTX, CHAT, TAB, FLAG, POLLBASE, SLOT, ROOMBG = (A['ROOMLOAD'], A['BMPFREE'], A['HWND'], A['CHATOBJS'], A['TABOBJS'],
                                                            A['ROOMFLAG'], A['POLLBASE'], A['PADPOLL'], A['ROOMBG'])
HELD = patcher.PAD_BASE + 0x3e
METHOD, BLIT = 0x34, 0x1c
BOX = (18, 454, (0, 0, 98, 18))         # where the backdrop's patch goes, and its source rect
FILES = len(patcher.TABMENU_FILES)
STOCK = (0x11110000, 0x22220000)        # the stock TAB objects, as the room's init left them
FIRST = 0x33330000                      # the first chat object
VTABLE = OBJECTS + 0x100                # the new objects' vtable, its +0x34 and +0x1c stubs


def main():
    blob = patcher.exe_blob(patcher.TABMENU_BLOB, 'European')
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr in (CODE, STUBS, STACK, OBJECTS):
        mu.mem_map(addr, 0x10000)
    for addr in (LOAD, FREE, CTX, CHAT, TAB, FLAG, POLLBASE, SLOT, ROOMBG):
        try:
            mu.mem_map(addr & ~0xfff, 0x1000)
        except Exception:
            pass
    mu.mem_write(CODE, blob)
    w = lambda a, v: mu.mem_write(a, struct.pack('<I', v & 0xffffffff))
    r = lambda a: struct.unpack('<I', mu.mem_read(a, 4))[0]
    # the exe's routines: the loader (cdecl, 7 args), the release (cdecl, 1), SetTarget (stdcall, 2), Blit (stdcall, 4), the poll (stdcall, 3)
    mu.mem_write(LOAD, b'\xc3')
    mu.mem_write(FREE, b'\xc3')
    mu.mem_write(VTABLE + METHOD, struct.pack('<I', STUBS + 0x10))
    mu.mem_write(STUBS + 0x10, b'\xc2\x08\x00')
    mu.mem_write(VTABLE + BLIT, struct.pack('<I', STUBS + 0x20))
    mu.mem_write(STUBS + 0x20, b'\xc2\x10\x00')
    mu.mem_write(STUBS, b'\xc2\x0c\x00')
    w(CTX, 0x44440000)
    w(CHAT, FIRST)
    w(TAB, STOCK[0])
    w(TAB + 4, STOCK[1])
    w(FLAG, 0x5a5a0001)
    w(POLLBASE, 0x5a5a0002)
    state = {'loads': [], 'frees': [], 'methods': [], 'blits': [], 'polls': [], 'held': False, 'next': OBJECTS + 0x1000}

    def loader(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        ctx, folder, flag, name, obj, sizes, one = struct.unpack('<7I', mu.mem_read(esp + 4, 28))
        text = bytes(mu.mem_read(name, 32)).split(b'\0')[0].decode('ascii')
        state['loads'].append((ctx, folder, flag, text, obj, sizes, one))
        w(state['next'], VTABLE)        # a new object: its vtable pointer
        w(obj, state['next'])
        w(sizes, 98)
        w(sizes + 4, 18)
        state['next'] += 0x100
        mu.reg_write(UC_X86_REG_EAX, 1)

    def release(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        state['frees'].append(r(esp + 4))

    def method(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        state['methods'].append(struct.unpack('<II', mu.mem_read(esp + 4, 8)))

    def blit(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        this, x, y, rect = struct.unpack('<4I', mu.mem_read(esp + 4, 16))
        state['blits'].append((this, x, y, struct.unpack('<4I', mu.mem_read(rect, 16))))

    def poll(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        source, value, rng = struct.unpack('<III', mu.mem_read(esp + 4, 12))
        state['polls'].append(source)
        w(value, 0x80 if state['held'] else 0)
        w(rng, 0x80)
        mu.reg_write(UC_X86_REG_EAX, 0)
    mu.hook_add(UC_HOOK_CODE, loader, begin=LOAD, end=LOAD + 1)
    mu.hook_add(UC_HOOK_CODE, release, begin=FREE, end=FREE + 1)
    mu.hook_add(UC_HOOK_CODE, method, begin=STUBS + 0x10, end=STUBS + 0x11)
    mu.hook_add(UC_HOOK_CODE, blit, begin=STUBS + 0x20, end=STUBS + 0x21)
    mu.hook_add(UC_HOOK_CODE, poll, begin=STUBS, end=STUBS + 1)

    def call(entry, expect, args=()):
        """One entry, as a call from its site: the registers kept, the
        site's own load in the register expected, the site's arguments
        (room's) left on the stack for the site to pop."""
        regs = {UC_X86_REG_EAX: 0x11111111, UC_X86_REG_EBX: 0x22222222, UC_X86_REG_ECX: 0x55555555, UC_X86_REG_EDX: 0x33333333,
                UC_X86_REG_EBP: 0x44444444, UC_X86_REG_ESI: 0x66666666, UC_X86_REG_EDI: 0x77777777}
        for reg, v in regs.items():
            mu.reg_write(reg, v)
        esp = STACK + 0x8000
        for i, arg in enumerate(args):
            w(esp + 4 + 4 * i, arg)
        w(esp, 0xdeadbeef)                          # the site's return address, as the call left it
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(CODE + entry, 0xdeadbeef, timeout=2000000)
        assert mu.reg_read(UC_X86_REG_ESP) == esp + 4, 'the stack came back wrong'
        reg, value = expect
        for k, v in regs.items():
            assert mu.reg_read(k) == (value if k == reg else v) or (reg is None and k == UC_X86_REG_EAX), 'a register came back changed'
        assert [r(esp + 4 + 4 * i) for i in range(len(args))] == list(args), 'the site\'s arguments were touched'

    INIT, FREE_, FRAME, ROOM, ROOMFREE = 0, 5, 10, 15, 20
    NAME = 0x4b3b6c                                     # the exe's own name for the backdrop
    mu.mem_map(NAME & ~0xfff, 0x1000)
    mu.mem_write(NAME, b'CHAT.BMP\0')
    SITE = (0x44440000, 0xc, 0, NAME, ROOMBG, A['ROOMSIZE'], 1)      # the constructor's own call: the backdrop into the table
    w(SLOT, STUBS)
    # a frame with nothing loaded: nothing
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert (r(TAB), r(TAB + 4)) == STOCK and state['polls'] == [], 'a frame with nothing loaded touched something'
    # the room's constructor: the site's load passed on, then the backdrop's two files
    call(ROOM, (None, None), SITE)
    assert [(l[0], l[1], l[2], l[3], l[6]) for l in state['loads']] == [(0x44440000, 0xc, 0, 'CHAT.BMP', 1)] \
        + [(0x44440000, 0xc, 0, name, 1) for name in patcher.TABMENU_FILES[2:]], 'the room\'s loads: %r' % (state['loads'],)
    assert (state['loads'][0][4], state['loads'][0][5]) == (ROOMBG, A['ROOMSIZE']), 'the site\'s own load went elsewhere'
    backs = [r(l[4]) for l in state['loads'][1:]]
    backdrop = r(ROOMBG)                                    # the loader's new backdrop
    assert backdrop == OBJECTS + 0x1000 and state['methods'] == [] and state['blits'] == [], 'room called a surface or lost the backdrop'
    # frames in the room with the menu closed: the backdrop's box by the pad, the array untouched
    patched = lambda obj: [(obj, backdrop), (obj, 0)]       # SetTarget around one blit of the backdrop's box
    blitted = lambda obj: [(obj, BOX[0], BOX[1], BOX[2])]
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert state['polls'] == [HELD] and state['blits'] == [] and state['methods'] == [], 'no pad on a fresh backdrop: blitted'
    state['held'] = True
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert (r(TAB), r(TAB + 4)) == STOCK, 'the array written with the menu closed'
    assert state['blits'] == blitted(backs[1]) and state['methods'] == patched(backs[1]), 'a pad held: the backdrop not patched as SEL: %r %r' % (state['blits'], state['methods'])
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert state['blits'] == blitted(backs[1]), 'the pad still held: blitted again'
    state['held'] = False
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert state['blits'] == blitted(backs[1]) + blitted(backs[0]) and state['methods'] == patched(backs[1]) + patched(backs[0]), 'the pad gone: the backdrop not patched back'
    state['blits'], state['methods'], state['polls'] = [], [], []
    state['held'] = True
    w(SLOT, 0)
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert state['polls'] == [] and state['blits'] == [], 'asked or blitted with the slot empty'
    w(SLOT, STUBS)
    w(ROOMBG, 0)
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert state['blits'] == [], 'blitted without a backdrop'
    w(ROOMBG, backdrop)
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert state['blits'] == blitted(backs[1]), 'the backdrop back: not patched'
    state['held'] = False
    # the menu opens: init
    state['loads'], state['methods'], state['blits'] = [], [], []
    call(INIT, (UC_X86_REG_EDX, 0x5a5a0001))
    assert [(l[0], l[1], l[2], l[3], l[6]) for l in state['loads']] == [(0x44440000, 0xc, 0, name, 1) for name in patcher.TABMENU_FILES[:2]], \
        'the loads are not the exe\'s own: %r' % (state['loads'],)
    objects = [r(l[4]) for l in state['loads']]
    sizes = [l[5] for l in state['loads']]
    assert objects == [OBJECTS + 0x1300, OBJECTS + 0x1400] and sizes[1] == sizes[0] + 8 \
        and all(CODE <= l[4] < CODE + len(blob) for l in state['loads']), 'the objects and sizes are not in the blob'
    assert state['methods'] == [call_ for obj in objects for call_ in ((obj, FIRST), (obj, 0))], 'the +0x34 calls: %r' % (state['methods'],)
    assert (r(TAB), r(TAB + 4)) == STOCK and state['blits'] == [], 'init changed the array or blitted'
    state['methods'] = []
    # frames with the menu open: the array by the pad, the backdrop too
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert (r(TAB), r(TAB + 4)) == STOCK and state['blits'] == blitted(backs[0]), 'no pad: not the stock'
    state['held'] = True
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert (r(TAB), r(TAB + 4)) == tuple(objects), 'a pad held: not the pad\'s'
    assert state['blits'] == blitted(backs[0]) + blitted(backs[1]), 'a pad held with the menu open: the backdrop not patched'
    state['held'] = False
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert (r(TAB), r(TAB + 4)) == STOCK, 'the pad gone: not back to the stock'
    state['held'] = True
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert (r(TAB), r(TAB + 4)) == tuple(objects)
    # the menu closes: free, with the pad's in the array
    call(FREE_, (UC_X86_REG_ESI, CHAT))
    assert (r(TAB), r(TAB + 4)) == STOCK, 'free did not put the stock back'
    assert state['frees'] == objects, 'the releases: %r' % (state['frees'],)
    state['blits'] = []
    state['held'] = False
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert (r(TAB), r(TAB + 4)) == STOCK and state['blits'] == blitted(backs[0]), 'the menu closed: the array written, or the backdrop not patched back'
    call(FREE_, (UC_X86_REG_ESI, CHAT))
    assert state['frees'] == objects, 'freed twice'
    # the room's destructor: the backdrop's two released
    call(ROOMFREE, (UC_X86_REG_ESI, ROOMBG))
    assert state['frees'] == objects + backs, 'roomfree\'s releases: %r' % (state['frees'],)
    state['held'] = True
    state['polls'] = []
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert (r(TAB), r(TAB + 4)) == STOCK and state['blits'] == blitted(backs[0]) and state['polls'] == [], 'a frame after roomfree did something'
    call(ROOMFREE, (UC_X86_REG_ESI, ROOMBG))
    assert state['frees'] == objects + backs, 'roomfree released twice'
    # a second room, left with the menu open: roomfree puts the stock back and releases all four
    state['loads'], state['frees'], state['blits'] = [], [], []
    call(ROOM, (None, None), SITE)
    backs2 = [r(l[4]) for l in state['loads'][1:]]
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert state['blits'] == blitted(backs2[1]), 'a second room: the fresh backdrop not patched for the pad'
    call(INIT, (UC_X86_REG_EDX, 0x5a5a0001))
    objects2 = [r(l[4]) for l in state['loads'][3:]]
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert (r(TAB), r(TAB + 4)) == tuple(objects2)
    call(ROOMFREE, (UC_X86_REG_ESI, ROOMBG))
    assert (r(TAB), r(TAB + 4)) == STOCK and sorted(state['frees']) == sorted(objects2 + backs2), 'the room left with the menu open: %r' % (state['frees'],)
    call(FRAME, (UC_X86_REG_EAX, 0x5a5a0002))
    assert (r(TAB), r(TAB + 4)) == STOCK and sorted(state['frees']) == sorted(objects2 + backs2) and state['blits'] == blitted(backs2[1]), 'a frame after the room did something'
    print('tabmenu: the backdrop\'s box loaded with the room and the buttons with the menu, both switched by the pad, released with each')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
