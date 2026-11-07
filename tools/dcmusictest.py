#!/usr/bin/env python3
"""The Dreamcast music's ending and replays under Unicorn.

    python3 tools/dcmusictest.py

dcmusic.asm's entries, with each build's addresses in place, each entered
as the call of the sound bank's play it replaces: with ecx the bank and
the slot at [esp+4], and the race block the build's pointer names.

The ending (+0), slot 9: without music\\track18.wav the play gets slot 9
and the bank is untouched; with it, slot 14 and slot 14's record holds
17, the CD track less one. The files are looked for once and beside the
exe, and a directory of the name is not a file.

A championship replay (+5 for race 1, +10 for the later ones): race 1
plays track 15, race 2 slot 9 (track 11), races 3 and 4 tracks 16 and 17,
races past 4 going round; a track without its file keeps the course's
slot, and without any of tracks 15 to 17 every race keeps it. +10 on race
0 is the slot-7 branch and is left alone.

Another mode's replay (+15): one of the four the files allow, by the time
stamp counter; not a replay, or mode 1 or 10, is left alone.

The play always gets ecx and the return as they were.

Needs python3-unicorn; exits 0 with a note when it is missing.
"""
import struct

from uctest import patcher
import uctest

uctest.unicorn('dcmusictest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP,
                               UC_X86_REG_EIP)

CODE, STUBS, STACK, BANK, RECORDS, BLOCK = 0x900000, 0xa00000, 0xb00000, 0xc00000, 0xc10000, 0xc20000
RETURN = 0xd00000
EXE = 'C:\\Games\\SEGA RALLY 2\\SEGA RALLY 2.exe'
MUSIC = 'C:\\Games\\SEGA RALLY 2\\music\\'
EXTRA, RECORD, ENDING, ELEVEN = 14, 0x28, 18, 9
OWN = 0xe                       # slot 14's record as the descriptor leaves it: track 15 less one
COURSE = 3                      # a course's slot
ENDING_AT, FIRST_AT, LATER_AT, SINGLE_AT = 0, 5, 10, 15
REPLAYS = ('track15.wav', 'track16.wav', 'track17.wav')


def run(build, files, dirs=(), calls=1, entry=ENDING_AT, slot=ELEVEN, mode=1, bits=0, race=0, tsc=0):
    row = patcher.BUILDS[build]
    blob = patcher.exe_blob(patcher.DCMUSIC_BLOB, build)
    play = row['addresses']['BGMPLAY']
    pointer = row['addresses']['RACEBLOCK']
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr in (CODE, STUBS, STACK, BANK, RECORDS, BLOCK, RETURN):
        mu.mem_map(addr, 0x10000)
    for addr in (play, pointer, row['slots']['LoadLibraryA'], row['slots']['GetProcAddress'],
                 row['slots']['GetModuleFileNameA']):
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
    mu.mem_write(RECORDS + EXTRA * RECORD, struct.pack('<I', OWN))
    mu.mem_write(pointer, struct.pack('<I', BLOCK))
    mu.mem_write(BLOCK + 0x38, struct.pack('<I', mode))
    mu.mem_write(BLOCK + 0x44, struct.pack('<I', bits))
    mu.mem_write(BLOCK + 0x64, struct.pack('<I', race))
    rdtsc = blob.find(b'\x0f\x31')
    if rdtsc < 0 or blob.find(b'\x0f\x31', rdtsc + 1) >= 0:
        raise SystemExit('dcmusictest: not one rdtsc in the blob')
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
        elif addr == CODE + rdtsc:
            mu.reg_write(UC_X86_REG_EAX, tsc)
            mu.reg_write(UC_X86_REG_EDX, 0x12345)
            mu.reg_write(UC_X86_REG_EIP, addr + 2)
    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x31)
    mu.hook_add(UC_HOOK_CODE, stub, begin=play, end=play)
    mu.hook_add(UC_HOOK_CODE, stub, begin=CODE + rdtsc, end=CODE + rdtsc)

    for _ in range(calls):
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<5I', RETURN, slot, 1, 0, 0))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_ECX, BANK)
        mu.emu_start(CODE + entry, RETURN)
        if mu.reg_read(UC_X86_REG_EIP) != RETURN or mu.reg_read(UC_X86_REG_ESP) != esp + 0x14:
            raise SystemExit('dcmusictest: %s came back at %x with esp %x' % (build, mu.reg_read(UC_X86_REG_EIP), mu.reg_read(UC_X86_REG_ESP)))
    return state


def played(slot, record=OWN):
    return [(BANK, (RETURN, slot, 1, 0, 0), record)]


def expect(build, what, state, want):
    if state['plays'] != want:
        raise SystemExit('dcmusictest: %s, %s: played %r, wanted %r' % (build, what, state['plays'], want))


def main():
    names = ['track%02d.wav' % n for n in range(15, 19)]
    for build in patcher.BUILDS:
        # the ending. No file: slot 9, the record as the descriptor left it; all four files looked for, once, beside the exe
        state = run(build, (), calls=2)
        expect(build, 'the ending without track18.wav', state, played(ELEVEN) * 2)
        if state['asked'] != [MUSIC + n for n in names]:
            raise SystemExit('dcmusictest: %s looked for %r' % (build, state['asked']))
        if state['procs'] != [(0x7c800000, 'GetFileAttributesA')]:
            raise SystemExit('dcmusictest: %s resolved %r' % (build, state['procs']))
        # the file: slot 14 with track 18 less one in its record
        state = run(build, ('track18.wav',), calls=2)
        expect(build, 'the ending with track18.wav', state, played(EXTRA, ENDING - 1) * 2)
        if len(state['asked']) != 4:
            raise SystemExit('dcmusictest: %s looked %d times' % (build, len(state['asked'])))
        # the other extras there but not 18, or a directory named track18.wav: slot 9
        expect(build, 'the ending with 15 to 17', run(build, REPLAYS), played(ELEVEN))
        expect(build, 'the ending with a directory', run(build, (), ('track18.wav',)), played(ELEVEN))

        # a championship's replay, all three files there
        replay = dict(slot=COURSE, mode=1, bits=4 | 0x100)
        expect(build, 'race 1', run(build, REPLAYS, entry=FIRST_AT, **replay), played(EXTRA, 14))
        for race, want in ((1, played(ELEVEN)), (2, played(EXTRA, 15)), (3, played(EXTRA, 16)),
                           (5, played(ELEVEN)), (7, played(EXTRA, 16))):
            expect(build, 'race %d' % (race + 1), run(build, REPLAYS, entry=LATER_AT, race=race, **replay), want)
        expect(build, 'the slot-7 branch', run(build, REPLAYS, entry=LATER_AT, race=0, **dict(replay, slot=7)),
               played(7))
        expect(build, 'race 1 of ten years', run(build, REPLAYS, entry=FIRST_AT, **dict(replay, mode=4)),
               played(EXTRA, 14))
        # only track 16: race 3 plays it, race 2 track 11, races 1 and 4 the course's
        only = ('track16.wav',)
        expect(build, 'race 1, only 16', run(build, only, entry=FIRST_AT, **replay), played(COURSE))
        for race, want in ((1, played(ELEVEN)), (2, played(EXTRA, 15)), (3, played(COURSE))):
            expect(build, 'race %d, only 16' % (race + 1), run(build, only, entry=LATER_AT, race=race, **replay), want)
        # none of 15 to 17 (track 18 alone): every race the course's
        expect(build, 'race 1, no set', run(build, ('track18.wav',), entry=FIRST_AT, **replay), played(COURSE))
        for race in (1, 2, 3):
            expect(build, 'race %d, no set' % (race + 1),
                   run(build, ('track18.wav',), entry=LATER_AT, race=race, **replay), played(COURSE))

        # another mode's replay: the counter picks among the choices there
        for mode in (2, 3, 5, 6):
            single = dict(entry=SINGLE_AT, slot=COURSE, mode=mode, bits=4)
            for tsc, want in ((0, played(EXTRA, 14)), (1, played(ELEVEN)), (2, played(EXTRA, 15)),
                              (3, played(EXTRA, 16)), (6, played(EXTRA, 15))):
                expect(build, 'mode %d, counter %d' % (mode, tsc), run(build, REPLAYS, tsc=tsc, **single), want)
            for tsc, want in ((0, played(ELEVEN)), (1, played(EXTRA, 16)), (2, played(ELEVEN))):
                expect(build, 'mode %d, counter %d, only 17' % (mode, tsc),
                       run(build, ('track17.wav',), tsc=tsc, **single), want)
            expect(build, 'mode %d, no set' % mode, run(build, ('track18.wav',), **single), played(COURSE))
            expect(build, 'mode %d racing' % mode, run(build, REPLAYS, **dict(single, bits=0)), played(COURSE))
        # the same call's other scenes: the arcade ending (mode 1, slot 8) and mode 10's
        expect(build, 'the arcade ending', run(build, REPLAYS, entry=SINGLE_AT, slot=8, mode=1, bits=4 | 0x20),
               played(8))
        expect(build, 'mode 10', run(build, REPLAYS, entry=SINGLE_AT, slot=10, mode=10, bits=4), played(10))
    print('dcmusictest: the ending plays track 18, the replays tracks 15, 11, 16 and 17, '
          'each when its file is there, in %d builds OK' % len(patcher.BUILDS))


if __name__ == '__main__':
    main()
