#!/usr/bin/env python3
"""Run the pad annex under Unicorn in the real MGInput.dll.

    python3 tools/padinputtest.py GAMEDIR    # GAMEDIR holds MUSASHI/MGInput.dll

Patches a copy in memory, maps it relocated, stubs kernel32 and XInput,
and drives the four entries: loads with no text, after a save, from a
fresh session, from an old file with the game's block ahead of the text
and from a hand-written text; the save's text and deadzone; the update
taking the first free pad and reading the race gate; the poll's
buttons, triggers, stick halves through the deadzone, menu-only sources
in and out of a race, and keyboard sources left to the DLL. Needs
python3-unicorn; exits 0 with a note when it is missing so tools/check.py
can skip it.
"""
import hashlib
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
    from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_ECX
except ImportError:
    print('padinputtest: skipped, python3-unicorn not installed')
    sys.exit(0)

BASE = 0x01DD0000
STUBS = 0x03000000
SCRATCH = 0x04000000
STACK = 0x05000000
EXE = 'S:\\Sega Rally 2\\SEGA RALLY 2.exe'
CFG = 'S:\\Sega Rally 2\\SR2.CFG'
HFILE = 0x777


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    path = os.path.join(argv[1], 'MUSASHI', 'MGInput.dll')
    if os.path.isfile(path + '.bak'):
        path += '.bak'
    with open(path, 'rb') as fh:
        raw = bytearray(fh.read())
    build = next((b for b, row in patcher.BUILDS.items()
                  if row['files']['MUSASHI\\MGInput.dll'][1] == hashlib.md5(raw).hexdigest()), None)
    if build is None:
        print('padinputtest: %s is not an MGInput.dll the patcher knows' % path)
        return 1
    image = patcher.apply_xinput(raw, build)
    sites = patcher.BUILDS[build]['sites']['xinput']
    load_off, save_off, update_off, poll_off = sites[:4]
    australian = len(sites) == 5          # the keyboard poll's address in the dispatch, not a device method

    pe_off = struct.unpack_from('<I', image, 0x3c)[0]
    nsec = struct.unpack_from('<H', image, pe_off + 6)[0]
    opt = pe_off + 24
    size = struct.unpack_from('<I', image, opt + 56)[0]
    table = opt + struct.unpack_from('<H', image, pe_off + 20)[0]
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(BASE, (size + 0xfff) & ~0xfff)
    mu.mem_write(BASE, bytes(image[:0x1000]))
    annex = None
    for i in range(nsec):
        name, vsize, va, rsize, roff = struct.unpack_from('<8sIIII', image, table + i * 40)
        mu.mem_write(BASE + va, bytes(image[roff:roff + rsize]))
        if name.rstrip(b'\0') == patcher.XINPUT_SECTION:
            annex = va
    assert annex is not None
    delta = BASE - struct.unpack_from('<I', image, opt + 28)[0]
    rel_rva, rel_size = struct.unpack_from('<II', image, opt + 136)
    off = patcher._rva_to_off(image, rel_rva)
    end = off + rel_size
    while off + 8 <= end:
        page, bsize = struct.unpack_from('<II', image, off)
        if not bsize:
            break
        for i in range(8, bsize, 2):
            e = struct.unpack_from('<H', image, off + i)[0]
            if e >> 12 == 3:
                a = BASE + page + (e & 0xfff)
                v = struct.unpack('<I', mu.mem_read(a, 4))[0]
                mu.mem_write(a, struct.pack('<I', (v + delta) & 0xffffffff))
        off += bsize
    mu.mem_map(STUBS, 0x1000)
    mu.mem_map(SCRATCH, 0x10000)
    mu.mem_map(STACK, 0x100000)
    flag = patcher.BUILDS[build]['addresses']['CARS']         # the exe's car table: a car in slot 0 means a race
    mu.mem_map(flag & ~0xfff, 0x1000)
    publish = patcher.BUILDS[build]['addresses']['PADPOLL']   # the exe slot the annex publishes the page's poll at
    if publish & ~0xfff != flag & ~0xfff:
        mu.mem_map(publish & ~0xfff, 0x1000)

    names = ['LoadLibraryA', 'GetProcAddress', 'GetModuleFileNameA', 'CreateFileA', 'ReadFile',
             'WriteFile', 'SetFilePointer', 'CloseHandle', 'SetEndOfFile', 'XInputGetState']
    argc = {'LoadLibraryA': 1, 'GetProcAddress': 2, 'GetModuleFileNameA': 3, 'CreateFileA': 7, 'ReadFile': 5,
            'WriteFile': 5, 'SetFilePointer': 4, 'CloseHandle': 1, 'SetEndOfFile': 1, 'XInputGetState': 2}
    addr = {n: STUBS + 0x10 * k for k, n in enumerate(names)}
    for n in names:
        mu.mem_write(addr[n], b'\xc2' + struct.pack('<H', argc[n] * 4))
    for n in ('LoadLibraryA', 'GetProcAddress'):
        mu.mem_write(BASE + patcher._iat_slot(image, 'kernel32.dll', n), struct.pack('<I', addr[n]))

    # the file as the stubs see it, and the pads
    disk = {'text': None, 'pos': 0, 'opened': [], 'loaded': [], 'ended': 0}
    pads = {}                                   # slot: (buttons, lt, rt, lx, ly, rx, ry)

    def cstr(p):
        return bytes(mu.mem_read(p, 300)).split(b'\0')[0].decode('latin-1')

    def stub(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        args = struct.unpack('<8I', mu.mem_read(esp + 4, 32))
        name = names[(address - STUBS) // 0x10]
        ret = 0
        if name == 'LoadLibraryA':
            lib = cstr(args[0])
            disk['loaded'].append(lib)
            ret = {'kernel32.dll': 2, 'xinput1_3.dll': 3}.get(lib, 0)
        elif name == 'GetProcAddress':
            ret = addr.get(cstr(args[1]), 0)
        elif name == 'GetModuleFileNameA':
            mu.mem_write(args[1], EXE.encode() + b'\0')
            ret = len(EXE)
        elif name == 'CreateFileA':
            disk['opened'].append((cstr(args[0]), args[1], args[4]))
            ret = 0xFFFFFFFF
            if cstr(args[0]) == CFG and (disk['text'] is not None or args[4] == 4):
                ret = HFILE
        elif name == 'SetFilePointer':
            assert args[0] == HFILE and args[3] == 0
            disk['pos'] = args[1]
            ret = args[1]
        elif name == 'ReadFile':
            assert args[0] == HFILE and disk['pos'] == 0
            data = (disk['text'] or b'')[:args[2]]
            mu.mem_write(args[1], data)
            mu.mem_write(args[3], struct.pack('<I', len(data)))
            ret = 1
        elif name == 'WriteFile':
            assert args[0] == HFILE and disk['pos'] == 0
            disk['text'] = bytes(mu.mem_read(args[1], args[2]))
            mu.mem_write(args[3], struct.pack('<I', args[2]))
            ret = 1
        elif name == 'SetEndOfFile':
            assert args[0] == HFILE
            disk['ended'] += 1
            ret = 1
        elif name == 'CloseHandle':
            ret = 1
        elif name == 'XInputGetState':
            if args[0] in pads:
                mu.mem_write(args[1], struct.pack('<IHBBhhhh', 1, *pads[args[0]]))
                ret = 0
            else:
                ret = 1167                      # ERROR_DEVICE_NOT_CONNECTED
        mu.reg_write(UC_X86_REG_EAX, ret)

    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x100)

    def call(target, *args, ecx=0):
        esp = STACK + 0x80000
        mu.mem_write(esp, struct.pack('<I', 0xDEAD0000) + b''.join(struct.pack('<I', a) for a in args))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_ECX, ecx)
        mu.emu_start(target, 0xDEAD0000, count=2000000)
        return mu.reg_read(UC_X86_REG_EAX), mu.reg_read(UC_X86_REG_ESP) - esp

    def site(off):
        return BASE + patcher._off_to_rva(image, off)

    def records(buf, n):
        return [struct.unpack('<13I', mu.mem_read(buf + i * 0x34, 0x34)) for i in range(n)]

    this, slot0, slot1, buf, got = SCRATCH, SCRATCH + 0x10, SCRATCH + 0x14, SCRATCH + 0x100, SCRATCH + 0x20
    mu.mem_write(this, b'\0' * 16)              # a helper whose registry object is null
    mu.mem_write(slot0, b'0\0')
    mu.mem_write(slot1, b'1\0')

    blob = patcher.PADINPUT_BLOB
    tableok = len(blob) - 260 - 32 - 4 - 4 - 4 - 4 - 4 - 4    # before path, the states, retry and index bytes, got, the section and its player, inrace

    def fresh():
        """A new session: the table's flag cleared, the working area zeroed."""
        mu.mem_write(BASE + annex + tableok, b'\0\0\0\0')
        mu.mem_write(BASE + annex + len(blob) + patcher.ANNEX_TABLES, b'\0' * (patcher.ANNEX_END - patcher.ANNEX_TABLES))

    def load(slot, n=64):
        ret, popped = call(site(load_off), this, slot, 0, buf, n, got)
        assert ret == 0 and popped == 4 + 0x18, (hex(ret), popped)
        count = struct.unpack('<I', mu.mem_read(got, 4))[0]
        return [bytes(mu.mem_read(buf + i * 0x34, 0x34)) for i in range(min(count, n))], count

    # 1. no text on disk: the count, then the defaults; the page's poll published
    ret, popped = call(site(load_off), this, slot0, 0, 0, 0, got)
    assert ret == 0 and popped == 4 + 0x18, (hex(ret), popped)
    assert struct.unpack('<I', mu.mem_read(publish, 4))[0] == BASE + annex + 25
    want0 = patcher.annex_records(0)
    assert struct.unpack('<I', mu.mem_read(got, 4))[0] == len(want0) == 38
    recs, count = load(slot0)
    assert recs == want0, [r.hex() for r in recs[:3]]
    assert disk['opened'] == [(CFG, 0x80000000, 3)], disk['opened']
    recs, count = load(slot1, 2)                # fewer wanted than held: that many
    assert count == 2 and recs == patcher.annex_records(1)[:2]
    mu.mem_write(SCRATCH + 0x18, b'2\0')
    ret, _p = call(site(load_off), this, SCRATCH + 0x18, 0, buf, 32, got)
    assert ret == 0x80070057, hex(ret)
    mu.mem_write(SCRATCH + 0x1c, b'0\0')
    ret, _p = call(site(load_off), this, slot0, SCRATCH + 0x1c, buf, 32, got)   # the exe's second, named load: nothing
    assert ret == 0 and struct.unpack('<I', mu.mem_read(got, 4))[0] == 0

    # 2. a save: three records for 2P and a deadzone in the name; the text rewritten
    handbrake_b = patcher.annex_records(1, [(0, None)] * 8 + [(0, 13)])[9]
    three = b''.join(patcher.annex_records(1, [(0x11, None), (0x1f, None)])[:2]) + handbrake_b
    mu.mem_write(buf, three)
    name = SCRATCH + 0x40
    mu.mem_write(name, b'DZ4000\0')
    ret, popped = call(site(save_off), this, slot1, name, buf, 3)
    assert ret == 0 and popped == 4 + 0x14, (hex(ret), popped)
    assert disk['text'] is not None and disk['opened'][-1] == (CFG, 0xC0000000, 4) and disk['ended'] == 1
    t2 = [(0x11, None), (0x1f, None)] + [(0, None)] * 6 + [(0, 13)] + [(0, None)] * 4
    assert disk['text'] == patcher.annex_text([None, t2], (1000, 4000)), disk['text'].decode()
    recs, count = load(slot1)
    assert recs == patcher.annex_records(1, t2), count
    assert count == 13 + 1 + 4 + 8

    # 3. a fresh session parses that text back; 1P still the defaults
    fresh()
    recs, count = load(slot0)
    assert recs == want0
    recs, count = load(slot1)
    t3 = list(t2)                               # the menus' actions are not in the text: their defaults again
    for a in (2, 3, 10, 11, 12):
        t3[a] = (patcher.KEYS_2P[a], patcher.PAD_DEFAULT[a])
    assert recs == patcher.annex_records(1, t3), count
    ret, _p = call(site(save_off), this, slot0, 0, buf, 0)      # a save with no records: 1P's row emptied, no deadzone change
    assert b'[1P Controller]\nDeadzone = 10\nSteeringLeft = -\n' in disk['text'] and b'[1P Keyboard]\nSteeringLeft = -\n' in disk['text']
    assert b'MenuUp' not in disk['text'] and b'Enter' not in disk['text']

    # 3b. an old file, the game's 100 binary bytes before the text: skipped
    disk['text'] = b'display' + b'\0' * 93 + b'\n[1P Keyboard]\nAccelerate = Q\n'
    fresh()
    recs, count = load(slot0)
    t = [(patcher.KEYS_1P[a], patcher.PAD_DEFAULT[a]) for a in range(13)]
    t[0] = (0x10, patcher.PAD_DEFAULT[0])
    assert recs == patcher.annex_records(0, t), count

    # 4. a hand-written text: CRLF, blank lines, comments, no "=", unknown names dropped, sections in any order
    disk['text'] = (b'\r\n; mine\r\n[2P Keyboard]\r\nView NUM_ENTER\r\nSteeringLeft = -\r\n\r\n[1P Controller]\r\nDeadzone = 30\r\n'
                    b'Accelerate = LB\r\nSteeringLeft = DPAD_LEFT\r\nBrake = NOSUCH\r\nView\r\n[2P Controller]\r\nDeadzone 5\r\n'
                    b'SteeringLeft = -\r\nView = RS_UP\r\n[1P Keyboard]\r\nAccelerate = Q\r\n[Nonsense]\r\nBrake = X\r\n')
    fresh()
    recs, count = load(slot0)
    t = [(patcher.KEYS_1P[a], patcher.PAD_DEFAULT[a]) for a in range(13)]
    t[0] = (0x10, patcher.PAD_LB)
    t[4] = (patcher.KEYS_1P[4], patcher.PAD_LEFT)
    assert recs == patcher.annex_records(0, t), count
    recs, count = load(slot1)
    t = [(patcher.KEYS_2P[a], patcher.PAD_DEFAULT[a]) for a in range(13)]
    t[9] = (0x9c, 24)
    t[4] = (0, None)
    assert recs == patcher.annex_records(1, t), count

    # 4. the pads: 1P's config update with a pad in slot 1 only
    cfg0, cfg1 = SCRATCH + 0x1000, SCRATCH + 0x2000
    mu.mem_write(cfg0 + 0xc, b'0\0')
    mu.mem_write(cfg1 + 0xc, b'1\0')
    mu.mem_write(cfg0 + 0x124, struct.pack('<I', cfg0 + 0x124))   # an empty record list: the DLL's loop ends at once
    mu.mem_write(cfg1 + 0x124, struct.pack('<I', cfg1 + 0x124))
    pads[1] = (0x1000 | 0x0001, 0, 200, -20000, 0, 0, 30000)       # A and D-pad up, RT, stick left, RS up
    ret, popped = call(site(update_off), cfg0)
    assert popped == 4 + 4, popped              # the DLL's Update, ret 4, ran to its end
    dev = SCRATCH + 0x3000
    mu.mem_write(dev + 0xc, struct.pack('<I', 1))
    keys = SCRATCH + 0x4000
    if australian:                                          # a device descriptor, its type byte at +8
        mu.mem_write(dev + 8, b'\x03')
    else:                                                   # a keyboard device object
        mu.mem_write(dev + 0x260, b'\x03')
        mu.mem_write(dev + 0x308, struct.pack('<I', keys))
    value, rng = SCRATCH + 0x50, SCRATCH + 0x54

    def poll(source):
        if australian:
            ret, popped = call(BASE + annex + 20, dev, keys, source, value, rng)
            assert popped == 4 + 0x14, popped
        else:
            ret, popped = call(site(poll_off), dev, source, value, rng)
            assert popped == 4 + 0x10, popped
        return ret, struct.unpack('<I', mu.mem_read(value, 4))[0], struct.unpack('<I', mu.mem_read(rng, 4))[0]

    assert poll(0x300 + patcher.PAD_A) == (0, 0x80, 0x80)
    assert poll(0x300 + patcher.PAD_UP) == (0, 0x80, 0x80)
    assert poll(0x300 + patcher.PAD_B) == (0, 0, 0x80)
    assert poll(0x300 + patcher.PAD_RT) == (0, 200, 255)
    assert poll(0x300 + patcher.PAD_LT) == (0, 0, 255)
    ret, v, r = poll(0x300 + patcher.PAD_LS_LEFT)
    dz = 3000 * 32767 // 10000
    assert (ret, r) == (0, 10000) and v == (20000 - dz) * 10000 // (32767 - dz), (v, r)
    assert poll(0x300 + patcher.PAD_LS_RIGHT) == (0, 0, 10000)
    assert poll(0x300 + 25)[1] == 0             # right stick down: it is up
    assert poll(0x300 + 24)[1] == (30000 - dz) * 10000 // (32767 - dz)   # right stick up
    assert poll(0x300 + 0x3f) == (0, 3000, 10000)
    assert poll(0x340 + 0x3f) == (0, 500, 10000)
    # menu-only inputs and keys answer outside a race and not in one; 1P's update reads the exe's car table
    mu.mem_write(keys + 0xcb, b'\x80')
    assert poll(0x300 + patcher.PAD_UP + patcher.MENU_ONLY) == (0, 0x80, 0x80)
    assert poll(patcher.MENUKEY_BASE + 0xcb) == (0, 0x80, 0x80)
    assert poll(patcher.MENUKEY_BASE + 0xcd) == (0, 0, 0x80)
    mu.mem_write(flag, struct.pack('<I', 0x4a000000))   # a car
    call(site(update_off), cfg1)                        # 2P's update does not look
    assert poll(0x300 + patcher.PAD_UP + patcher.MENU_ONLY) == (0, 0x80, 0x80)
    call(site(update_off), cfg0)
    assert poll(0x300 + patcher.PAD_UP + patcher.MENU_ONLY) == (0, 0, 0x80)
    assert poll(0x300 + patcher.PAD_UP) == (0, 0x80, 0x80)              # the bindable one still does
    assert poll(patcher.MENUKEY_BASE + 0xcb) == (0, 0, 0x80)
    assert poll(0x300 + 0x3f) == (0, 3000, 10000)                      # the deadzone read is not menu-only
    mu.mem_write(flag, struct.pack('<I', 0))
    call(site(update_off), cfg0)                        # no car: a menu again
    assert poll(0x300 + patcher.PAD_UP + patcher.MENU_ONLY) == (0, 0x80, 0x80)
    kind = dev + 8 if australian else dev + 0x260        # another device's type does not answer menu keys
    mu.mem_write(kind, b'\x04')
    assert poll(patcher.MENUKEY_BASE + 0xcb) == (0, 0, 0x80)
    mu.mem_write(kind, b'\x03')
    assert poll(0x340 + patcher.PAD_A) == (0, 0, 0x80)     # 2P holds no pad
    # 2P's update looks for a pad and must not take 1P's
    ret, _p = call(site(update_off), cfg1)
    assert poll(0x340 + patcher.PAD_A) == (0, 0, 0x80)
    pads[3] = (0x2000, 0, 0, 0, 0, 0, 0)
    for _ in range(61):
        call(site(update_off), cfg1)
    assert poll(0x340 + patcher.PAD_B) == (0, 0x80, 0x80)
    assert poll(0x300 + patcher.PAD_B) == (0, 0, 0x80)
    # 1P's pad unplugged: its state clears, and the deadzone stays readable
    del pads[1]
    call(site(update_off), cfg0)
    assert poll(0x300 + patcher.PAD_A) == (0, 0, 0x80)
    assert poll(0x300 + patcher.PAD_RT) == (0, 0, 255)
    # a keyboard source goes to the DLL's own keyboard poll
    mu.mem_write(keys + 0x2d, b'\x80')
    assert poll(0x2d)[1] == 0x80
    assert poll(0x2c)[1] == 0
    # the page's poll: pads and the deadzone, no keyboard behind it
    ret, popped = call(BASE + annex + 25, 0x340 + patcher.PAD_B, value, rng)
    assert popped == 4 + 0xc and struct.unpack('<I', mu.mem_read(value, 4))[0] == 0x80
    call(BASE + annex + 25, 0x300 + 0x3f, value, rng)
    assert struct.unpack('<I', mu.mem_read(value, 4))[0] == 3000
    call(BASE + annex + 25, patcher.MENUKEY_BASE + 0x2d, value, rng)
    assert struct.unpack('<I', mu.mem_read(value, 4))[0] == 0
    assert 'xinput1_4.dll' in disk['loaded'] and 'xinput1_3.dll' in disk['loaded']
    print('padinputtest: %s MGInput.dll OK' % build)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
