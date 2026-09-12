#!/usr/bin/env python3
"""Run the Device Settings page's binding routines under Unicorn.

    python3 tools/devicestest.py GAMEDIR     # GAMEDIR holds Options.dll

Patches a copy of Options.dll in memory, maps it relocated, and stands in
for the game's input objects with stubs: an input object whose GetConfig
and GetDevice hand out a config with a record list and a device whose
poll answers a scripted pad and whose GetState hands out a key array.
Drives refresh, a wait that binds a key (swapping with the row that had
it), one that binds a pad input, the deadzone step and DEFAULT, and
checks the records, the value strings and the Persist calls. Needs
python3-unicorn; exits 0 with a note when it is missing.
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
    from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EBP, UC_X86_REG_ECX, UC_X86_REG_EDX
except ImportError:
    print('devicestest: skipped, python3-unicorn not installed')
    sys.exit(0)

BASE = 0x02110000
STUBS = 0x03000000
SCRATCH = 0x04000000
STACK = 0x05000000
INPUT, CFG0, CFG1, DEV, KEYS, HOLDER, WRAPPER = (SCRATCH + i * 0x1000 for i in range(1, 8))
RECORDS = SCRATCH + 0x10000            # 0x200 bytes each, the node before the record


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    path = os.path.join(argv[1], 'Options.dll')
    if os.path.isfile(path + '.bak'):
        path += '.bak'
    with open(path, 'rb') as fh:
        raw = bytearray(fh.read())
    build = next((b for b, row in patcher.BUILDS.items()
                  if row['files']['Options.dll'][1] == hashlib.md5(raw).hexdigest()), None)
    if build is None:
        print('devicestest: %s is not an Options.dll the patcher knows' % path)
        return 1
    image = patcher.apply_devices(raw, build)

    pe_off = struct.unpack_from('<I', image, 0x3c)[0]
    nsec = struct.unpack_from('<H', image, pe_off + 6)[0]
    opt = pe_off + 24
    size = struct.unpack_from('<I', image, opt + 56)[0]
    table = opt + struct.unpack_from('<H', image, pe_off + 20)[0]
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(BASE, (size + 0xfff) & ~0xfff)
    mu.mem_write(BASE, bytes(image[:0x1000]))
    sec = None
    for i in range(nsec):
        name, vsize, va, rsize, roff = struct.unpack_from('<8sIIII', image, table + i * 40)
        mu.mem_write(BASE + va, bytes(image[roff:roff + rsize]))
        if name.rstrip(b'\0') == patcher.DEVICES_SECTION:
            sec = va
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
    mu.mem_map(SCRATCH, 0x20000)
    mu.mem_map(STACK, 0x100000)

    # The page's code: the blob after the menu's data. Its routines by
    # their offsets in the assembled blob, found from the source's labels
    # through nasm's listing would be nicer; here from the bytes.
    blob = patcher.DEVICES_BLOB
    page = struct.unpack('<I', mu.mem_read(BASE + patcher._off_to_rva(image, patcher.BUILDS[build]['sites']['devices'][6] + 12), 4))[0] - len(blob)
    assert bytes(mu.mem_read(page, 16)) == blob[:16], 'the page blob not at %#x' % page
    section = bytes(mu.mem_read(BASE + sec, size - sec))
    data = BASE + sec + section.index(bytes(a for _n, a in patcher.PAGE_ACTIONS))
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.lst') as lst:
        subprocess.check_call(['nasm', '-f', 'bin', '-l', lst.name, '-o', os.devnull, os.path.join(HERE, '..', 'asm', 'devices.asm')])
        listing = open(lst.name).read()
    labels, pending = {}, []
    for line in listing.splitlines():
        src = line[40:].strip()
        word = src.split()[0] if src else ''
        if word.endswith(':') and not word.startswith('.'):
            pending.append(word[:-1])
        if len(line) > 15 and line[7:15].strip() and all(c in '0123456789ABCDEF' for c in line[7:15]):
            for name in pending:
                labels[name] = int(line[7:15], 16)
            pending = []
    for need in ('refresh', 'snapshot', 'waittick', 'defaults', 'bindkey', 'held', 'binding', 'row', 'snapkeys', 'shown'):
        assert need in labels, need

    # stubs: each `ret N`, its work done in the hook
    names = ['Release', 'GetDevice', 'GetConfig', 'Persist', 'GetState', 'Poll', 'PlaySound', 'Bits']
    argc = {'Release': 1, 'GetDevice': 4, 'GetConfig': 3, 'Persist': 3, 'GetState': 3, 'Poll': 3, 'PlaySound': 4, 'Bits': 1}
    addr = {n: STUBS + 0x10 * k for k, n in enumerate(names)}
    for n in names:
        mu.mem_write(addr[n], b'\xc2' + struct.pack('<H', argc[n] * 4))
    vt_input, vt_cfg, vt_dev, vt_wrap, vt_sound = (STUBS + 0x200 + i * 0x80 for i in range(5))
    for vt, entries in ((vt_input, {0x8: 'Release', 0x20: 'GetDevice', 0x34: 'GetConfig'}),
                        (vt_cfg, {0x8: 'Release', 0x30: 'Persist'}),
                        (vt_dev, {0x8: 'Release', 0x38: 'GetState'}),
                        (vt_wrap, {0x14: 'Bits'})):
        for o, n in entries.items():
            mu.mem_write(vt + o, struct.pack('<I', addr[n]))
    mu.mem_write(INPUT, struct.pack('<I', vt_input))
    mu.mem_write(CFG0, struct.pack('<I', vt_cfg))
    mu.mem_write(CFG1, struct.pack('<I', vt_cfg))
    mu.mem_write(DEV, struct.pack('<I', vt_dev))
    mu.mem_write(WRAPPER, struct.pack('<II', vt_wrap, INPUT))
    mu.mem_write(HOLDER + 8, struct.pack('<I', WRAPPER))
    publish = patcher.BUILDS[build]['addresses']['PADPOLL']   # the annex's page poll, as the annex publishes it
    mu.mem_map(publish & ~0xfff, 0x1000)
    mu.mem_write(publish, struct.pack('<I', addr['Poll']))
    opt_row = patcher.BUILDS[build]['options']
    mu.mem_write(BASE + opt_row['INPUT'] - 0x10000000, struct.pack('<I', HOLDER))
    mu.mem_write(BASE + opt_row['SOUNDOBJ'] - 0x10000000, struct.pack('<I', SCRATCH))
    mu.mem_write(BASE + opt_row['PLAYSOUND'] - 0x10000000, b'\xc2\x10\x00')     # a `ret 0x10` in place of the sound

    # the records: per config a ring of nodes, each node (next, prev, record)
    recs = {}

    def build_records(cfg, sets):
        head = cfg + 0x200                      # the head node, pointed at from +0x124 as the DLL keeps it
        mu.mem_write(cfg + 0x124, struct.pack('<I', head))
        nodes = []
        for i, (action, source) in enumerate(sets):
            node = RECORDS + len(recs) * 0x200
            rec = node + 0x20
            mu.mem_write(rec + 0x10c, struct.pack('<I', action))
            mu.mem_write(rec + 0x138, struct.pack('<II', 1, source))
            mu.mem_write(node + 8, struct.pack('<I', rec))
            recs[(cfg, i)] = rec
            nodes.append(node)
        ring = nodes + [head]
        for a, b in zip(ring, ring[1:] + ring[:1]):
            mu.mem_write(a, struct.pack('<I', b))
            mu.mem_write(b + 4, struct.pack('<I', a))

    def sources(cfg):
        out = {}
        head = struct.unpack('<I', mu.mem_read(cfg + 0x124, 4))[0]
        node = struct.unpack('<I', mu.mem_read(head, 4))[0]
        while node != head:
            rec = struct.unpack('<I', mu.mem_read(node + 8, 4))[0]
            action, src = struct.unpack('<I', mu.mem_read(rec + 0x10c, 4))[0], struct.unpack('<I', mu.mem_read(rec + 0x13c, 4))[0]
            out.setdefault(action, []).append(src)
            node = struct.unpack('<I', mu.mem_read(node, 4))[0]
        return out

    for player, cfg in enumerate((CFG0, CFG1)):
        build_records(cfg, [(struct.unpack_from('<I', r, 0)[0], struct.unpack_from('<I', r, 0x14)[0]) for r in patcher.annex_records(player)])
    mu.mem_write(KEYS, b'\0' * 256)

    pad = {0x33f: 1000, 0x37f: 1000}   # source: value
    log = {'persist': [], 'bits': 0}

    def cstr(p):
        return bytes(mu.mem_read(p, 300)).split(b'\0')[0].decode('latin-1')

    def stub(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        args = struct.unpack('<6I', mu.mem_read(esp + 4, 24))
        name = names[(address - STUBS) // 0x10]
        ret = 0
        if name == 'GetDevice':
            assert args[0] == INPUT and args[1] == 3 and args[2] == 0
            mu.mem_write(args[3], struct.pack('<I', DEV))
        elif name == 'GetConfig':
            assert args[0] == INPUT and args[1] in (0, 1)
            mu.mem_write(args[2], struct.pack('<I', (CFG0, CFG1)[args[1]]))
        elif name == 'Persist':
            log['persist'].append((0 if args[0] == CFG0 else 1, cstr(args[1]) if args[1] else None, args[2]))
        elif name == 'GetState':
            assert args[0] == DEV
            mu.mem_write(args[1], struct.pack('<I', KEYS))
        elif name == 'Poll':
            assert 0x300 <= args[0] < 0x380
            mu.mem_write(args[1], struct.pack('<I', pad.get(args[0], 0)))
        elif name == 'Bits':
            ret = log['bits']
        mu.reg_write(UC_X86_REG_EAX, ret)

    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x100)

    def call(label, eax=0, ecx=0, edx=0):
        esp = STACK + 0x80000
        mu.mem_write(esp, struct.pack('<I', 0xDEAD0000))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_EBX, BASE)                  # the blob's ebx, the image base
        mu.reg_write(UC_X86_REG_EBP, page)
        mu.reg_write(UC_X86_REG_EAX, eax)
        mu.reg_write(UC_X86_REG_ECX, ecx)
        mu.reg_write(UC_X86_REG_EDX, edx)
        try:
            mu.emu_start(page + labels[label], 0xDEAD0000, count=5000000)
        except Exception:
            from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_EDI
            print('at %#x (blob +%#x) eax %#x ecx %#x edx %#x esi %#x edi %#x' % (mu.reg_read(UC_X86_REG_EIP), mu.reg_read(UC_X86_REG_EIP) - page,
                  mu.reg_read(UC_X86_REG_EAX), mu.reg_read(UC_X86_REG_ECX), mu.reg_read(UC_X86_REG_EDX), mu.reg_read(UC_X86_REG_ESI), mu.reg_read(UC_X86_REG_EDI)))
            raise
        return mu.reg_read(UC_X86_REG_EAX)

    def value(player, row, col):
        """A row's value string, after showing that player."""
        if var('shown') != player:
            var('shown', player)
            call('refresh')
        return cstr(data + patcher.DATA_VALUES + (row * 2 + col) * 16)

    def var(label, v=None):
        if v is None:
            return struct.unpack('<I', mu.mem_read(page + labels[label], 4))[0]
        mu.mem_write(page + labels[label], struct.pack('<I', v))

    # 1. refresh: the values from the records, and the label
    call('refresh')
    assert cstr(data + patcher.DATA_VALUES + 18 * 16) == 'PLAYER 1'
    var('shown', 1)
    call('refresh')
    assert cstr(data + patcher.DATA_VALUES + 18 * 16) == 'PLAYER 2'
    assert (value(0, 0, 0), value(0, 0, 1)) == ('LEFT', 'LS LEFT'), (value(0, 0, 0), value(0, 0, 1))
    assert (value(0, 2, 0), value(0, 2, 1)) == ('X', 'RT')
    assert (value(1, 3, 0), value(1, 3, 1)) == ('S', 'LT')
    assert (value(0, 8, 0), value(1, 8, 0)) == ('10', '10')
    assert value(0, 6, 0) == 'SPACE' and value(1, 4, 1) == 'A'

    # 2. a wait on 1P's ACCEL (row 3): C, which BRAKE has, binds and swaps
    var('shown', 0)
    var('row', 3)
    mu.mem_write(KEYS + 0x1c, b'\x80')          # Return held from the confirm
    call('snapshot')
    var('binding', 1)
    var('held', 0)
    call('waittick')
    assert var('binding') == 1 and log['persist'] == []      # nothing fresh
    mu.mem_write(KEYS + 0x2e, b'\x80')          # C
    call('waittick')
    assert var('binding') == 0
    s0 = sources(CFG0)
    assert s0[0][0] == 0x2e and s0[1][0] == 0x2d, s0
    assert log['persist'] == [(0, None, 1), (1, None, 1)], log['persist']
    assert (value(0, 2, 0), value(0, 3, 0)) == ('C', 'X')
    mu.mem_write(KEYS + 0x2e, b'\0')
    mu.mem_write(KEYS + 0x1c, b'\0')

    # 3. a wait on 2P's VIEW (row 8): A on 2P's pad, which its SHIFT UP has, binds and swaps; 1P untouched
    del log['persist'][:]
    var('shown', 1)
    var('row', 8)
    pad[0x340 + 12] = 0x80                      # A held from the confirm
    call('snapshot')
    var('binding', 1)
    call('waittick')
    assert var('binding') == 1
    pad[0x340 + 12] = 0
    call('waittick')
    pad[0x340 + 12] = 0x80
    call('waittick')
    assert var('binding') == 0
    s1 = sources(CFG1)
    assert s1[9][1] == 0x340 + 12 and s1[6][1] == 0x340 + 15, s1
    assert log['persist'] == [(1, None, 1)]
    assert (value(1, 7, 1), value(1, 4, 1)) == ('A', 'Y')
    assert sources(CFG0)[9][1] == 0x300 + 15
    pad[0x340 + 12] = 0

    # 4. Start held a second gives up
    var('shown', 0)
    var('row', 1)
    call('snapshot')
    var('binding', 1)
    var('held', 0)
    pad[0x300 + 4] = 0x80
    for _ in range(59):
        call('waittick')
    assert var('binding') == 1 and var('held') == 59
    call('waittick')
    assert var('binding') == 0
    pad[0x300 + 4] = 0
    # ESC too, at once
    var('binding', 1)
    call('snapshot')
    mu.mem_write(KEYS + 1, b'\x80')
    call('waittick')
    assert var('binding') == 0
    mu.mem_write(KEYS + 1, b'\0')

    # the menus' own records are not the rows': binding 1P STEER LEFT to F1 and its pad to LB leaves the arrow, the D-pad and the stick on action 4
    var('shown', 0)
    var('row', 1)
    call('snapshot')
    var('binding', 1)
    mu.mem_write(KEYS + 0x3b, b'\x80')
    call('waittick')
    assert var('binding') == 0 and sources(CFG0)[4][0] == 0x3b
    mu.mem_write(KEYS + 0x3b, b'\0')
    call('snapshot')
    var('binding', 1)
    pad[0x300 + 8] = 0x80
    call('waittick')
    pad[0x300 + 8] = 0
    assert var('binding') == 0
    src = sources(CFG0)
    assert src[4] == [0x3b, 0x300 + 8, 0x400 + 0xcb, 0x300 + patcher.PAD_LEFT + 0x20, 0x300 + patcher.PAD_LS_LEFT + 0x20], src[4]   # the bound pair, then the menus' own
    assert (value(0, 0, 0), value(0, 0, 1)) == ('F1', 'LB')

    # 5. DEFAULT puts everything back and saves both with the deadzone
    del log['persist'][:]
    call('defaults')
    assert sources(CFG0)[0][0] == 0x2d and sources(CFG0)[1][0] == 0x2e
    assert sources(CFG1)[9][1] == 0x340 + 15 and sources(CFG1)[6][1] == 0x340 + 12
    assert log['persist'] == [(0, 'DZ1000', 1), (1, 'DZ1000', 1)], log['persist']
    assert (value(0, 2, 0), value(1, 7, 1)) == ('X', 'Y')
    print('devicestest: %s Options.dll OK' % build)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
