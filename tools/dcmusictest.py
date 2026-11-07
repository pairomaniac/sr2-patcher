#!/usr/bin/env python3
"""The Dreamcast music's ending under Unicorn.

    python3 tools/dcmusictest.py

dcmusic.asm's entry, with each build's addresses in place, entered as the
ten-year ending's call of the sound bank's play: with ecx the bank and
slot 9 at [esp+4]. Without music\\track18.wav the play gets slot 9 and the
bank is untouched; with it, slot 14 and slot 14's record holds 17, the
CD track less one. The play gets ecx and the return as they were, the
files are looked for once and beside the exe, and a directory of the name
is not a file.

Needs python3-unicorn; exits 0 with a note when it is missing.
"""
import struct

from uctest import patcher
import uctest

uctest.unicorn('dcmusictest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_EIP

CODE, STUBS, STACK, BANK, RECORDS = 0x900000, 0xa00000, 0xb00000, 0xc00000, 0xc10000
RETURN = 0xd00000
EXE = 'C:\\Games\\SEGA RALLY 2\\SEGA RALLY 2.exe'
MUSIC = 'C:\\Games\\SEGA RALLY 2\\music\\'
EXTRA, RECORD, ENDING = 14, 0x28, 18


def run(build, files, dirs=(), calls=1):
    row = patcher.BUILDS[build]
    blob = patcher.exe_blob(patcher.DCMUSIC_BLOB, build)
    play = row['addresses']['BGMPLAY']
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr in (CODE, STUBS, STACK, BANK, RECORDS, RETURN):
        mu.mem_map(addr, 0x10000)
    for addr in (play, row['slots']['LoadLibraryA'], row['slots']['GetProcAddress'], row['slots']['GetModuleFileNameA']):
        try:
            mu.mem_map(addr & ~0xfff, 0x1000)
        except Exception:
            pass
    mu.mem_write(CODE, blob)
    # LoadLibraryA at STUBS (ret 4), GetProcAddress at +0x10 (ret 8), GetModuleFileNameA at +0x20 (ret 0xc),
    # GetFileAttributesA at +0x30 (ret 4); the play is `ret 0x10` at its own address
    mu.mem_write(STUBS, b'\xc2\x04\x00')
    mu.mem_write(STUBS + 0x10, b'\xc2\x08\x00')
    mu.mem_write(STUBS + 0x20, b'\xc2\x0c\x00')
    mu.mem_write(STUBS + 0x30, b'\xc2\x04\x00')
    mu.mem_write(play, b'\xc2\x10\x00')
    mu.mem_write(row['slots']['LoadLibraryA'], struct.pack('<I', STUBS))
    mu.mem_write(row['slots']['GetProcAddress'], struct.pack('<I', STUBS + 0x10))
    mu.mem_write(row['slots']['GetModuleFileNameA'], struct.pack('<I', STUBS + 0x20))
    mu.mem_write(BANK, struct.pack('<I', RECORDS))
    mu.mem_write(RECORDS + EXTRA * RECORD, struct.pack('<I', 0xe))        # the descriptor's own: track 15
    state = {'asked': [], 'procs': [], 'plays': []}

    def cstr(addr):
        return bytes(mu.mem_read(addr, 300)).split(b'\0')[0].decode('latin-1')

    def stub(mu, addr, size, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        if addr == STUBS:
            mu.reg_write(UC_X86_REG_EAX, 0x7c800000 if cstr(struct.unpack('<I', mu.mem_read(esp + 4, 4))[0]).lower() == 'kernel32.dll' else 0)
        elif addr == STUBS + 0x10:
            module, name = struct.unpack('<II', mu.mem_read(esp + 4, 8))
            state['procs'].append((module, cstr(name)))
            mu.reg_write(UC_X86_REG_EAX, STUBS + 0x30)
        elif addr == STUBS + 0x20:
            module, buf, size = struct.unpack('<III', mu.mem_read(esp + 4, 12))
            if module != 0 or size < len(EXE) + 1 + 24:
                raise SystemExit('dcmusictest: GetModuleFileNameA(%x, ..., %d)' % (module, size))
            mu.mem_write(buf, EXE.encode() + b'\0')
            mu.reg_write(UC_X86_REG_EAX, len(EXE))
        elif addr == STUBS + 0x30:
            path = cstr(struct.unpack('<I', mu.mem_read(esp + 4, 4))[0])
            state['asked'].append(path)
            name = path[len(MUSIC):] if path.startswith(MUSIC) else None
            mu.reg_write(UC_X86_REG_EAX, 0x20 if name in files else 0x10 if name in dirs else 0xffffffff)
        elif addr == play:
            state['plays'].append((mu.reg_read(UC_X86_REG_ECX), struct.unpack('<5I', mu.mem_read(esp, 20)),
                                   struct.unpack('<I', mu.mem_read(RECORDS + EXTRA * RECORD, 4))[0]))
    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x31)
    mu.hook_add(UC_HOOK_CODE, stub, begin=play, end=play)

    for _ in range(calls):
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<5I', RETURN, 9, 0, 0, 0))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_ECX, BANK)
        mu.emu_start(CODE, RETURN)
        if mu.reg_read(UC_X86_REG_EIP) != RETURN or mu.reg_read(UC_X86_REG_ESP) != esp + 0x14:
            raise SystemExit('dcmusictest: %s came back at %x with esp %x' % (build, mu.reg_read(UC_X86_REG_EIP), mu.reg_read(UC_X86_REG_ESP)))
    return state


def main():
    names = ['track%02d.wav' % n for n in range(15, 19)]
    for build in patcher.BUILDS:
        # no file: slot 9, the record as the descriptor left it; all four files looked for, once, beside the exe
        state = run(build, (), calls=2)
        if state['plays'] != [(BANK, (RETURN, 9, 0, 0, 0), 0xe)] * 2:
            raise SystemExit('dcmusictest: %s without track18.wav played %r' % (build, state['plays']))
        if state['asked'] != [MUSIC + n for n in names]:
            raise SystemExit('dcmusictest: %s looked for %r' % (build, state['asked']))
        if state['procs'] != [(0x7c800000, 'GetFileAttributesA')]:
            raise SystemExit('dcmusictest: %s resolved %r' % (build, state['procs']))
        # the file: slot 14 with track 18 less one in its record, the rest of the call as it was
        state = run(build, ('track18.wav',), calls=2)
        if state['plays'] != [(BANK, (RETURN, EXTRA, 0, 0, 0), ENDING - 1)] * 2 or len(state['asked']) != 4:
            raise SystemExit('dcmusictest: %s with track18.wav played %r, looked %d times' % (build, state['plays'], len(state['asked'])))
        # the other extras there but not 18, or a directory named track18.wav: slot 9
        for files, dirs in ((('track15.wav', 'track16.wav', 'track17.wav'), ()), ((), ('track18.wav',))):
            state = run(build, files, dirs)
            if state['plays'] != [(BANK, (RETURN, 9, 0, 0, 0), 0xe)]:
                raise SystemExit('dcmusictest: %s with %r %r played %r' % (build, files, dirs, state['plays']))
    print('dcmusictest: the ending plays track 18 in slot 14 when its file is there, slot 9 otherwise, '
          'in %d builds OK' % len(patcher.BUILDS))


if __name__ == '__main__':
    main()
