#!/usr/bin/env python3
"""Run the exe's input wrapper update (0x47f2d0) and its pad poll
(0x43f8e0) under Unicorn with MGInput's GetActionState stubbed to answer
one action at a time, and print which menu flag each action lands on.

    python3 tools/padbits.py GAMEDIR      # a European install; the addresses are that build's
"""
import struct
import sys
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX

EXE = 'SEGA RALLY 2.exe'
BASE = 0x400000
UPDATE = 0x47f2d0        # wrapper vtable +8: the frame's masks from GetActionState
POLL = 0x43f8e0          # the pad flags from the wrapper's +0x1c
WRAPPER_VTBL = 0x4a158c
HOLDER = 0x50b120        # -> object; [obj+8] the input wrapper
FLAGS_EDGE = 0x4ef7e4
PREV = 0x4ef7d4
REPEAT = (0x4b5630, 0x4b5634, 0x4b5638)

STACK = 0x200000
SCRATCH = 0x700000
RET = 0x900000
MASK = SCRATCH + 0xff0   # the actions GetActionState answers with 10000


def load(path):
    with open(path, 'rb') as fh:
        raw = fh.read()
    pe = struct.unpack_from('<I', raw, 0x3c)[0]
    nsec = struct.unpack_from('<H', raw, pe + 6)[0]
    opt = struct.unpack_from('<H', raw, pe + 20)[0]
    size = struct.unpack_from('<I', raw, pe + 24 + 56)[0]
    hdr = struct.unpack_from('<I', raw, pe + 24 + 60)[0]
    img = bytearray(size)
    img[:hdr] = raw[:hdr]
    for i in range(nsec):
        s = pe + 24 + opt + i * 40
        rva, rsz, ptr = struct.unpack_from('<III', raw, s + 12)
        img[rva:rva + rsz] = raw[ptr:ptr + rsz]
    return bytes(img)


def probe(game):
    img = load(game + '/' + EXE)
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(BASE, (len(img) + 0xfff) & ~0xfff | 0x1000)
    mu.mem_write(BASE, img)
    mu.mem_map(STACK - 0x10000, 0x20000)
    mu.mem_map(SCRATCH, 0x1000)
    mu.mem_map(RET, 0x1000)

    # stubs, stdcall like the DLL's methods
    ret = SCRATCH + 0x100                                   # wrapper +0x94: nothing
    mu.mem_write(ret, b'\xc3')
    count = SCRATCH + 0x110                                 # input +0x2c(&n): n = 1
    mu.mem_write(count, bytes.fromhex('8b442408') + bytes.fromhex('c700 01000000'.replace(' ', '')) + b'\x31\xc0\xc2\x08\x00')
    cfg = SCRATCH + 0x300
    getconfig = SCRATCH + 0x130                             # input +0x34(i, &cfg)
    mu.mem_write(getconfig, bytes.fromhex('8b44240c') + b'\xc7\x00' + struct.pack('<I', cfg) + b'\x31\xc0\xc2\x0c\x00')
    getstate = SCRATCH + 0x150                              # config +0x38(id, &state, mode): state+8 = 10000 if MASK has id
    mu.mem_write(getstate, bytes.fromhex('8b442408 8b4c240c') + b'\x8b\x15' + struct.pack('<I', MASK)
                 + bytes.fromhex('0fa3c2 b800000000 7305 b810270000 894108 31c0 c21000'))
    release = SCRATCH + 0x190                               # config +8
    mu.mem_write(release, b'\x31\xc0\xc2\x04\x00')

    input_vtbl = SCRATCH + 0x200
    mu.mem_write(input_vtbl, struct.pack('<16I', *[ret] * 16))
    mu.mem_write(input_vtbl + 0x2c, struct.pack('<I', count))
    mu.mem_write(input_vtbl + 0x34, struct.pack('<I', getconfig))
    cfg_vtbl = SCRATCH + 0x280
    mu.mem_write(cfg_vtbl, struct.pack('<16I', *[ret] * 16))
    mu.mem_write(cfg_vtbl + 0x08, struct.pack('<I', release))
    mu.mem_write(cfg_vtbl + 0x38, struct.pack('<I', getstate))
    mu.mem_write(cfg, struct.pack('<I', cfg_vtbl))
    inp = SCRATCH + 0x320
    mu.mem_write(inp, struct.pack('<I', input_vtbl))

    # the wrapper: the exe's own vtable but +0x94 stubbed, +4 the input object
    wrapper_vtbl = SCRATCH + 0x400
    mu.mem_write(wrapper_vtbl, bytes(mu.mem_read(WRAPPER_VTBL, 0xa0)))
    mu.mem_write(wrapper_vtbl + 0x94, struct.pack('<I', ret))
    wrapper = SCRATCH + 0x600
    mu.mem_write(wrapper, struct.pack('<II', wrapper_vtbl, inp))
    holder = SCRATCH + 0x900
    mu.mem_write(holder, struct.pack('<3I', 0, 0, wrapper))
    mu.mem_write(HOLDER, struct.pack('<I', holder))

    names = {0: 'accel', 1: 'brake', 2: 'up', 3: 'down', 4: 'left', 5: 'right', 6: 'shift up',
             7: 'shift down', 8: 'handbrake', 9: 'view', 10: 'enter', 11: 'escape', 12: 'start'}
    menu = {0: 'UP', 1: 'DOWN', 2: 'LEFT', 3: 'RIGHT', 4: 'CONFIRM', 5: 'CANCEL', 15: 'ENTER'}
    print('%-4s %-11s %-10s %s' % ('act', 'name', 'menu bit', 'meaning'))
    for act in range(13):
        for addr, val in ((PREV, 0), (FLAGS_EDGE, 0), (REPEAT[0], 1000), (REPEAT[1], 1000), (REPEAT[2], 1000)):
            mu.mem_write(addr, struct.pack('<I', val))
        mu.mem_write(MASK, struct.pack('<I', 1 << act))
        for entry in (UPDATE, POLL):
            mu.reg_write(UC_X86_REG_ESP, STACK)
            mu.reg_write(UC_X86_REG_ECX, wrapper)
            mu.mem_write(STACK, struct.pack('<I', RET))
            mu.emu_start(entry, RET)
        edge = struct.unpack('<I', mu.mem_read(FLAGS_EDGE, 4))[0]
        bits = [b for b in range(32) if edge >> b & 1]
        print('%-4d %-11s %-10s %s' % (act, names.get(act, '?'),
                                       ','.join(str(b) for b in bits) or '-',
                                       ' '.join(menu.get(b, '?') for b in bits)))


if __name__ == '__main__':
    probe(sys.argv[1])
