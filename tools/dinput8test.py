#!/usr/bin/env python3
"""Run the dinput8 stub under Unicorn in the real MGInput.dll.

    python3 tools/dinput8test.py GAMEDIR    # GAMEDIR holds MUSASHI/MGInput.dll

Patches a copy in memory, maps it relocated, stubs kernel32 and
dinput8.dll, and drives the DLL's own create routine: DirectInput8Create
called with (hinst, 0x800, IID_IDirectInput8A, &out, NULL), the object
queried for IID_IDirectInput8A and kept, the original released; E_FAIL
and nothing kept when dinput8.dll is not there. Then the kind entry:
DirectInput 8's device types written as DirectInput 5's, the displaced
instruction's edx and flags. Needs python3-unicorn; exits 77 with a note
when it is missing so tools/check.py can skip it.
"""
import os
import struct
import sys

from uctest import patcher
import uctest

uctest.unicorn('dinput8test')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EFLAGS

BASE = 0x01DD0000
STUBS = 0x03000000
SCRATCH = 0x04000000
STACK = 0x05000000
HINST = 0x00400000
DIOBJ = SCRATCH + 0x800                     # the object DirectInput8Create hands out
DIVTBL = SCRATCH + 0x900                    # its vtable: QueryInterface, AddRef, Release
E_FAIL = 0x80004005
ZF = 1 << 6


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    path = os.path.join(argv[1], 'MUSASHI', 'MGInput.dll')
    if os.path.isfile(path + '.bak'):
        path += '.bak'
    with open(path, 'rb') as fh:
        raw = bytearray(fh.read())
    build = uctest.build_of(raw, 'MUSASHI\\MGInput.dll')
    if build is None:
        print('dinput8test: %s is not an MGInput.dll the patcher knows' % path)
        return 1
    _file, sites, _t = patcher.patches(build)['dinput8']
    for off, old, new in sites:
        assert raw[off:off + len(old)] == old, 'bytes at 0x%x are not the original' % off
        if new is not None:
            raw[off:off + len(new)] = new
    image = patcher.apply_dinput8(raw, build)
    create, kind = patcher.BUILDS[build]['sites']['dinput8'][:2]

    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    annex = uctest.map_image(mu, image, BASE)
    assert annex is not None
    mu.mem_map(STUBS, 0x1000)
    mu.mem_map(SCRATCH, 0x10000)
    mu.mem_map(STACK, 0x100000)

    names = ['LoadLibraryA', 'GetProcAddress', 'DirectInput8Create', 'QueryInterface', 'AddRef', 'Release']
    argc = {'LoadLibraryA': 1, 'GetProcAddress': 2, 'DirectInput8Create': 5, 'QueryInterface': 3, 'AddRef': 1, 'Release': 1}
    addr = {n: STUBS + 0x10 * k for k, n in enumerate(names)}
    for n in names:
        mu.mem_write(addr[n], b'\xc2' + struct.pack('<H', argc[n] * 4))
    for n in ('LoadLibraryA', 'GetProcAddress'):
        mu.mem_write(BASE + patcher._iat_slot(image, 'kernel32.dll', n), struct.pack('<I', addr[n]))
    mu.mem_write(DIOBJ, struct.pack('<I', DIVTBL))
    mu.mem_write(DIVTBL, struct.pack('<3I', addr['QueryInterface'], addr['AddRef'], addr['Release']))

    seen = {'loaded': [], 'create': [], 'qi': [], 'addref': 0, 'release': 0, 'dll': True}

    def cstr(p):
        return bytes(mu.mem_read(p, 300)).split(b'\0')[0].decode('latin-1')

    def stub(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        args = struct.unpack('<8I', mu.mem_read(esp + 4, 32))
        name = names[(address - STUBS) // 0x10]
        ret = 0
        if name == 'LoadLibraryA':
            seen['loaded'].append(cstr(args[0]))
            ret = 7 if seen['dll'] and cstr(args[0]) == 'dinput8.dll' else 0
        elif name == 'GetProcAddress':
            ret = addr.get(cstr(args[1]), 0) if args[0] == 7 else 0
        elif name == 'DirectInput8Create':
            seen['create'].append((args[0], args[1], bytes(mu.mem_read(args[2], 16)), args[3], args[4]))
            mu.mem_write(args[3], struct.pack('<I', DIOBJ))
        elif name == 'QueryInterface':
            iid = bytes(mu.mem_read(args[1], 16))
            seen['qi'].append((args[0], iid))
            if iid == patcher.IID_IDIRECTINPUT8A:
                mu.mem_write(args[2], struct.pack('<I', args[0]))
                seen['addref'] += 1
            else:
                mu.mem_write(args[2], b'\0' * 4)
                ret = 0x80004002                # E_NOINTERFACE
        elif name == 'AddRef':
            seen['addref'] += 1
        elif name == 'Release':
            seen['release'] += 1
        mu.reg_write(UC_X86_REG_EAX, ret)

    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x100)

    def call(target, *args):
        esp = STACK + 0x80000
        mu.mem_write(esp, struct.pack('<I', 0xDEAD0000) + b''.join(struct.pack('<I', a) for a in args))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(target, 0xDEAD0000, count=200000)
        return mu.reg_read(UC_X86_REG_EAX), mu.reg_read(UC_X86_REG_ESP) - esp

    def site(off):
        return BASE + patcher._off_to_rva(image, off)

    # The DLL's create routine, (this, hinst, arg): the site is inside it.
    routine = site(create - 0x20)
    assert bytes(mu.mem_read(routine, 3)) == b'\x53\x56\x57', 'the create routine does not start where expected'
    this = SCRATCH
    mu.mem_write(this, b'\0' * 0x20)
    hr, popped = call(routine, this, HINST, 0x1234)
    assert (hr, popped) == (0, 16), 'create returned 0x%x, popped %d' % (hr, popped)
    assert seen['loaded'] == ['dinput8.dll'], seen['loaded']
    assert [c[:3] + c[4:] for c in seen['create']] == [(HINST, 0x800, patcher.IID_IDIRECTINPUT8A, 0)], seen['create']
    assert STACK <= seen['create'][0][3] < STACK + 0x100000     # the out slot is the routine's own argument slot
    assert seen['qi'] == [(DIOBJ, patcher.IID_IDIRECTINPUT8A)], seen['qi']
    assert seen['release'] == 1 and seen['addref'] == 1
    assert struct.unpack_from('<3I', mu.mem_read(this + 8, 12)) == (HINST, 0x1234, DIOBJ)
    print('  create: DirectInput8Create(hinst, 0x800, IID_IDirectInput8A, &out, NULL), the object queried and kept')

    # A second create finds the entry without loading again; a machine
    # without dinput8.dll gets E_FAIL and keeps nothing.
    mu.mem_write(this, b'\0' * 0x20)
    hr, _p = call(routine, this, HINST, 0x1234)
    assert hr == 0 and seen['loaded'] == ['dinput8.dll'] and len(seen['create']) == 2
    fn_slot = BASE + annex + bytes(mu.mem_read(BASE + annex, len(patcher.DINPUT8_BLOB))).index(struct.pack('<I', addr['DirectInput8Create']))
    mu.mem_write(fn_slot, b'\0' * 4)
    seen['dll'] = False
    mu.mem_write(this, b'\0' * 0x20)
    hr, popped = call(routine, this, HINST, 0x1234)
    assert (hr, popped) == (E_FAIL, 16) and len(seen['create']) == 2, hex(hr)
    assert bytes(mu.mem_read(this, 0x20)) == b'\0' * 0x20
    print('  create: E_FAIL without dinput8.dll, nothing kept')

    # The kind entry: DirectInput 8's types to DirectInput 5's, and the
    # displaced instruction's edx and flags.
    dev = SCRATCH + 0x1000
    entry = BASE + annex + 5
    for di8, di5 in ((0x12, 2), (0x13, 3), (0x14, 4), (0x15, 4), (0x16, 4), (0x17, 4), (0x18, 4),
                     (0x19, 1), (0x1a, 1), (0x1b, 1), (0x1c, 1), (0x11, 1), (3, 3), (4, 4), (0, 0)):
        mu.mem_write(dev + 0x260, struct.pack('<I', 0x10000 | 0x0400 | di8))
        mu.reg_write(UC_X86_REG_ESI, dev)
        mu.reg_write(UC_X86_REG_EAX, 0x55AA)
        _r, popped = call(entry)
        got = struct.unpack('<I', mu.mem_read(dev + 0x260, 4))[0]
        assert popped == 4 and got == (0x10000 | 0x0400 | di5), '0x%x: 0x%x' % (di8, got)
        assert mu.reg_read(UC_X86_REG_EDX) == got and mu.reg_read(UC_X86_REG_EAX) == 0x55AA
        assert bool(mu.reg_read(UC_X86_REG_EFLAGS) & ZF) == (di5 == 3)
    print('  kind: 0x12/0x13/0x14-0x18/0x11 and 0x19-0x1c -> 2/3/4/1, the rest kept, edx and the flags as the site had them')
    print('OK')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
