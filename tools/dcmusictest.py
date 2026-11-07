#!/usr/bin/env python3
"""The Dreamcast music under Unicorn: the exe's ending, replays and course
choices, and Options.dll's BGM page.

    python3 tools/dcmusictest.py

dcmusic.asm's entries, with each build's addresses in place, each entered
as the call it replaces: with ecx the bank and the slot at [esp+4], and the
race block the build's pointer names.

The ending (+0), slot 9: without music\\track18.wav the play gets slot 9
and the bank is untouched; with it, slot 14 and slot 14's record holds
17, the CD track less one. The files are looked for once and beside the
exe, and a directory of the name is not a file.

A championship replay (+5 for race 1, +10 for the later ones): race 1
plays track 15, race 2 slot 9 (track 11), races 3 and 4 tracks 16 and 17,
races past 4 going round; a track without its file keeps the course's
music, and without any of tracks 15 to 17 every race keeps it. +10 on
race 0 is the slot-7 branch and is left alone.

Another mode's scene (+15): in a replay, one of the four the files allow,
by the time stamp counter; a race in such a mode is the course's music;
mode 1 or 10 is left alone.

The course's music (+20 play, +25 fade, +30 restart; and every fallback
above): choices 0 to 6, slots 1 to 7, as they were; choices 7 to 10,
slots 8 to 11, are tracks 15, 11, 16 and 17 - slot 14 with the track in
its record, or slot 9 - and slot 9 when the track's file is not there.
Each leaves through its own routine.

Options.dll's build, placed at its preferred base: the init's count is 11
with one of tracks 15 to 17 there, else 7; a row's name for choices 7 to
10 is the blob's own string, and the text routine gets the rest of its
call as it was; the preview maps its slot as the exe's course music does,
with slots 13 and 12. The sound page's BGM TEST: the count is 13 and one
for each of tracks 15 to 18 there; past the 13th, the tracks there in
order, named by the blob and played in slot 13 with the track in its
record; the stock 13 pass as they were.

The routine called always gets ecx and the return as they were.

Needs python3-unicorn; exits 0 with a note when it is missing.
"""
import struct

from uctest import patcher
import uctest

uctest.unicorn('dcmusictest')
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI,
                               UC_X86_REG_EDI, UC_X86_REG_ESP, UC_X86_REG_EIP)

CODE, STUBS, STACK, BANK, RECORDS, BLOCK, PAGE = 0x900000, 0xa00000, 0xb00000, 0xc00000, 0xc10000, 0xc20000, 0xc30000
RETURN = 0xd00000
EXE = 'C:\\Games\\SEGA RALLY 2\\SEGA RALLY 2.exe'
MUSIC = 'C:\\Games\\SEGA RALLY 2\\music\\'
EXTRA, RECORD, ENDING, ELEVEN = 14, 0x28, 18, 9
OWN = 0xe                       # slot 14's record as the descriptor leaves it: track 15 less one
COURSE = 3                      # a course's slot
ENDING_AT, FIRST_AT, LATER_AT, SINGLE_AT, COURSE_AT, FADE_AT, RESTART_AT = 0, 5, 10, 15, 20, 25, 30
REPLAYS = ('track15.wav', 'track16.wav', 'track17.wav')
OPTIONS_RVA = 0x150000          # where the Options.dll blob is put, from the base
SIGIL = 0xC0DE5EED              # a string pointer the stock rows would pass


class Machine:
    """A blob at an address with its imports and the routines it leaves
    through stubbed; calls an entry with ecx the bank and four arguments."""

    def __init__(self, blob, at, slots, targets, files, dirs):
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_32)
        self.at, self.targets, self.files, self.dirs = at, targets, files, dirs
        for addr in (STUBS, STACK, BANK, RECORDS, BLOCK, PAGE, RETURN):
            mu.mem_map(addr, 0x10000)
        mu.mem_map(at & ~0xfff, (len(blob) + 0x1fff) & ~0xfff)
        for addr in list(targets) + list(slots):
            try:
                mu.mem_map(addr & ~0xfff, 0x1000)
            except Exception:
                pass
        mu.mem_write(at, blob)
        # LoadLibraryA at STUBS (ret 4), GetProcAddress at +0x10 (ret 8), GetModuleFileNameA at +0x20 (ret 0xc),
        # GetFileAttributesA at +0x30 (ret 4); each routine left through is `ret 0x10` at its own address
        for off, code in ((0, b'\xc2\x04\x00'), (0x10, b'\xc2\x08\x00'), (0x20, b'\xc2\x0c\x00'), (0x30, b'\xc2\x04\x00')):
            mu.mem_write(STUBS + off, code)
        for addr in targets:
            mu.mem_write(addr, b'\xc2\x10\x00')
        for slot, stub in zip(slots, (STUBS, STUBS + 0x10, STUBS + 0x20)):
            mu.mem_write(slot, struct.pack('<I', stub))
        mu.mem_write(BANK, struct.pack('<I', RECORDS))
        self.state = {'asked': [], 'procs': [], 'calls': []}
        self.tsc = 0
        self.rdtsc = None
        mu.hook_add(UC_HOOK_CODE, self.stub, begin=STUBS, end=STUBS + 0x31)
        for addr in targets:
            mu.hook_add(UC_HOOK_CODE, self.stub, begin=addr, end=addr)

    def counter(self, offset):
        self.rdtsc = self.at + offset
        self.mu.hook_add(UC_HOOK_CODE, self.stub, begin=self.rdtsc, end=self.rdtsc)

    def cstr(self, addr):
        return bytes(self.mu.mem_read(addr, 300)).split(b'\0')[0].decode('latin-1')

    def arg(self, n):
        return struct.unpack('<I', self.mu.mem_read(self.mu.reg_read(UC_X86_REG_ESP) + 4 * n, 4))[0]

    def stub(self, mu, addr, size, user):
        state = self.state
        if addr == STUBS:
            mu.reg_write(UC_X86_REG_EAX, 0x7c800000 if self.cstr(self.arg(1)).lower() == 'kernel32.dll' else 0)
        elif addr == STUBS + 0x10:
            state['procs'].append((self.arg(1), self.cstr(self.arg(2))))
            mu.reg_write(UC_X86_REG_EAX, STUBS + 0x30)
        elif addr == STUBS + 0x20:
            module, buf, size = self.arg(1), self.arg(2), self.arg(3)
            if module != 0 or size < len(EXE) + 1 + 24:
                raise SystemExit('dcmusictest: GetModuleFileNameA(%x, ..., %d)' % (module, size))
            mu.mem_write(buf, EXE.encode() + b'\0')
            mu.reg_write(UC_X86_REG_EAX, len(EXE))
        elif addr == STUBS + 0x30:
            path = self.cstr(self.arg(1))
            state['asked'].append(path)
            name = path[len(MUSIC):] if path.startswith(MUSIC) else None
            mu.reg_write(UC_X86_REG_EAX, 0x20 if name in self.files else 0x10 if name in self.dirs else 0xffffffff)
        elif addr == self.rdtsc:
            mu.reg_write(UC_X86_REG_EAX, self.tsc)
            mu.reg_write(UC_X86_REG_EDX, 0x12345)
            mu.reg_write(UC_X86_REG_EIP, addr + 2)
        elif addr in self.targets:
            esp = mu.reg_read(UC_X86_REG_ESP)
            state['calls'].append((self.targets[addr], mu.reg_read(UC_X86_REG_ECX),
                                   struct.unpack('<5I', mu.mem_read(esp, 20)),
                                   struct.unpack('<I', mu.mem_read(RECORDS + self.extra * RECORD, 4))[0]))

    def call(self, entry, args, regs=(), what=''):
        mu = self.mu
        esp = STACK + 0x8000
        mu.mem_write(esp, struct.pack('<5I', RETURN, *args))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.reg_write(UC_X86_REG_ECX, BANK)
        for reg, value in regs:
            mu.reg_write(reg, value)
        mu.emu_start(self.at + entry, RETURN)
        if mu.reg_read(UC_X86_REG_EIP) != RETURN or mu.reg_read(UC_X86_REG_ESP) != esp + 0x14:
            raise SystemExit('dcmusictest: %s came back at %x with esp %x' % (what, mu.reg_read(UC_X86_REG_EIP),
                                                                             mu.reg_read(UC_X86_REG_ESP)))


def exe_machine(build, files, dirs=(), mode=1, bits=0, race=0, tsc=0):
    row = patcher.BUILDS[build]
    blob = patcher.exe_blob(patcher.DCMUSIC_BLOB, build)
    addr = row['addresses']
    targets = {addr['BGMPLAY']: 'play', addr['BGMFADE']: 'fade', addr['BGMRESTART']: 'restart'}
    m = Machine(blob, CODE, (row['slots']['LoadLibraryA'], row['slots']['GetProcAddress'],
                             row['slots']['GetModuleFileNameA']), targets, files, dirs)
    m.extra = EXTRA
    mu = m.mu
    pointer = addr['RACEBLOCK']
    try:
        mu.mem_map(pointer & ~0xfff, 0x1000)
    except Exception:
        pass
    mu.mem_write(RECORDS + EXTRA * RECORD, struct.pack('<I', OWN))
    mu.mem_write(pointer, struct.pack('<I', BLOCK))
    mu.mem_write(BLOCK + 0x38, struct.pack('<I', mode))
    mu.mem_write(BLOCK + 0x44, struct.pack('<I', bits))
    mu.mem_write(BLOCK + 0x64, struct.pack('<I', race))
    rdtsc = blob.find(b'\x0f\x31')
    if rdtsc < 0 or blob.find(b'\x0f\x31', rdtsc + 1) >= 0:
        raise SystemExit('dcmusictest: not one rdtsc in the blob')
    m.counter(rdtsc)
    m.tsc = tsc
    return m


def run(build, files, dirs=(), calls=1, entry=ENDING_AT, slot=ELEVEN, mode=1, bits=0, race=0, tsc=0):
    m = exe_machine(build, files, dirs, mode, bits, race, tsc)
    for _ in range(calls):
        m.call(entry, (slot, 1, 0, 0), what=build)
    return m.state


def played(slot, record=OWN, via='play'):
    return [(via, BANK, (RETURN, slot, 1, 0, 0), record)]


def expect(build, what, state, want):
    if state['calls'] != want:
        raise SystemExit('dcmusictest: %s, %s: called %r, wanted %r' % (build, what, state['calls'], want))


def exe(build):
    names = ['track%02d.wav' % n for n in range(15, 19)]
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
    # ... and the course's music is a replay-set choice: race 1 falls back to it, track 16 (choice 9, slot 10)
    expect(build, 'race 1, only 16, choice 9', run(build, only, entry=FIRST_AT, **dict(replay, slot=10)),
           played(EXTRA, 15))
    # none of 15 to 17 (track 18 alone): every race the course's
    expect(build, 'race 1, no set', run(build, ('track18.wav',), entry=FIRST_AT, **replay), played(COURSE))
    for race in (1, 2, 3):
        expect(build, 'race %d, no set' % (race + 1),
               run(build, ('track18.wav',), entry=LATER_AT, race=race, **replay), played(COURSE))

    # another mode's scene: in a replay the counter picks among the choices there
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
        expect(build, 'mode %d racing, choice 10' % mode, run(build, REPLAYS, **dict(single, bits=0, slot=11)),
               played(EXTRA, 16))
    # the same call's other scenes: the arcade ending (mode 1, slot 8) and mode 10's
    expect(build, 'the arcade ending', run(build, REPLAYS, entry=SINGLE_AT, slot=8, mode=1, bits=4 | 0x20),
           played(8))
    expect(build, 'mode 10', run(build, REPLAYS, entry=SINGLE_AT, slot=10, mode=10, bits=4), played(10))

    # the course's music: play, fade and restart
    for entry, via in ((COURSE_AT, 'play'), (FADE_AT, 'fade'), (RESTART_AT, 'restart')):
        for slot in range(1, 8):
            expect(build, '%s of slot %d' % (via, slot), run(build, REPLAYS, entry=entry, slot=slot),
                   played(slot, via=via))
        for files, wants in ((REPLAYS, ((EXTRA, 14), (ELEVEN, OWN), (EXTRA, 15), (EXTRA, 16))),
                             (('track16.wav',), ((ELEVEN, OWN), (ELEVEN, OWN), (EXTRA, 15), (ELEVEN, OWN))),
                             ((), ((ELEVEN, OWN),) * 4)):
            for choice, (slot, record) in zip(range(7, 11), wants):
                expect(build, '%s of choice %d with %r' % (via, choice, files),
                       run(build, files, entry=entry, slot=choice + 1), played(slot, record, via))


def options():
    """Options.dll is one file in the European, American and MediaKite builds and another in the Australian."""
    seen = set()
    for build, row in patcher.BUILDS.items():
        opt = row['options']
        if opt['TEXT'] in seen:
            continue
        seen.add(opt['TEXT'])
        base = 0x10000000
        blob = bytes(patcher.DCOPTIONS_BLOB)
        for key, magic in patcher.DCOPTIONS_MAGICS.items():
            blob = blob.replace(struct.pack('<I', magic), struct.pack('<I', opt[key] - base))
        blob = blob.replace(struct.pack('<I', patcher.FULLWIN_MAGIC), struct.pack('<I', OPTIONS_RVA))

        def machine(files):
            m = Machine(blob, base + OPTIONS_RVA, (opt['LOADLIB'], opt['GETPROC'], opt['GETMODFN']),
                        {opt['TEXT']: 'text', opt['PLAYSOUND']: 'play'}, files, ())
            m.extra = 13
            m.mu.mem_write(RECORDS + 13 * RECORD, struct.pack('<I', OWN))
            return m

        # the count: ebx, the rest kept
        for files, count in ((REPLAYS, 11), (('track17.wav',), 11), (('track18.wav',), 7), ((), 7)):
            m = machine(files)
            mu = m.mu
            esp = STACK + 0x8000
            mu.mem_write(esp, struct.pack('<I', RETURN))
            mu.reg_write(UC_X86_REG_ESP, esp)
            regs = ((UC_X86_REG_EAX, 0x1111), (UC_X86_REG_ECX, 0x2222), (UC_X86_REG_EDX, 0x3333),
                    (UC_X86_REG_ESI, 0x4444), (UC_X86_REG_EDI, 0x5555), (UC_X86_REG_EBX, 0x6666))
            for reg, value in regs:
                mu.reg_write(reg, value)
            mu.emu_start(base + OPTIONS_RVA, RETURN)
            got = [mu.reg_read(reg) for reg, _ in regs]
            if got != [0x1111, 0x2222, 0x3333, 0x4444, 0x5555, count] or mu.reg_read(UC_X86_REG_ESP) != esp + 4:
                raise SystemExit('dcmusictest: %s options init with %r: %r' % (build, files, [hex(g) for g in got]))
        # the names: row edi of the page esi
        m = machine(REPLAYS)
        for choice in range(11):
            m.state['calls'].clear()
            m.mu.mem_write(PAGE + 0x18 + 4 * 6, struct.pack('<I', choice))
            m.call(5, (SIGIL, 0x41200000, 0x41200000, 0x3f800000),
                   ((UC_X86_REG_ESI, PAGE), (UC_X86_REG_EDI, 6)), build)
            (via, _ecx, frame, _record), = m.state['calls']
            want = (["IGNITION'98", "NIGHT GROOVIN'", 'ESTRADA NOVA', 'M N F ?'][choice - 7]
                    if choice >= 7 else None)
            text = m.cstr(frame[1]) if want else frame[1]
            if via != 'text' or text != (want or SIGIL) or frame[2:] != (0x41200000, 0x41200000, 0x3f800000):
                raise SystemExit('dcmusictest: %s options name of choice %d: %r' % (build, choice, (via, text, frame)))
        # the preview: the page bank's slots 13 and 12
        for files, wants in ((REPLAYS, ((13, 14), (12, OWN), (13, 15), (13, 16))),
                             (('track17.wav',), ((12, OWN), (12, OWN), (12, OWN), (13, 16)))):
            for slot in range(1, 12):
                m = machine(files)
                m.call(10, (slot, 0, 0, 0), what=build)
                want = ((slot, OWN) if slot < 8 else wants[slot - 8])
                (via, ecx, frame, record), = m.state['calls']
                if (via, ecx, frame[1], record) != ('play', BANK, want[0], want[1]):
                    raise SystemExit('dcmusictest: %s options preview of slot %d with %r: %r'
                                     % (build, slot, files, m.state['calls']))

        # BGM TEST: the count at [esi+0x68], 13 and the extra tracks there; every register kept
        titles = {15: "IGNITION'98", 16: 'ESTRADA NOVA', 17: 'M N F ?', 18: 'TILL YOU SEE THE DAWN'}
        sets = (('track15.wav', 'track16.wav', 'track17.wav', 'track18.wav'), ('track16.wav', 'track18.wav'),
                ('track17.wav',), ())
        for files in sets:
            m = machine(files)
            mu = m.mu
            esp = STACK + 0x8000
            mu.mem_write(esp, struct.pack('<I', RETURN))
            mu.mem_write(PAGE + 0x68, struct.pack('<I', 0xdead))
            mu.reg_write(UC_X86_REG_ESP, esp)
            regs = ((UC_X86_REG_EAX, 0x1111), (UC_X86_REG_ECX, 0x2222), (UC_X86_REG_EDX, 0x3333),
                    (UC_X86_REG_ESI, PAGE), (UC_X86_REG_EDI, 0x5555), (UC_X86_REG_EBX, 0x6666))
            for reg, value in regs:
                mu.reg_write(reg, value)
            mu.emu_start(base + OPTIONS_RVA + 15, RETURN)
            got = [mu.reg_read(reg) for reg, _ in regs]
            count = struct.unpack('<I', mu.mem_read(PAGE + 0x68, 4))[0]
            if got != [v for _, v in regs] or mu.reg_read(UC_X86_REG_ESP) != esp + 4 or count != 13 + len(files):
                raise SystemExit('dcmusictest: %s BGM TEST count with %r: %d, %r' % (build, files, count, got))
            # past the 13th, the tracks there in order: the name and the play of slot 13 with the track in its record
            there = sorted(int(f[5:7]) for f in files)
            for value in range(13 + len(files) + 1):
                track = there[value - 13] if 13 <= value < 13 + len(there) else None
                m.state['calls'].clear()
                mu.mem_write(PAGE + 0x3c, struct.pack('<I', value))
                m.call(20, (SIGIL, 0x41200000, 0x41200000, 0x3f800000), ((UC_X86_REG_ESI, PAGE),), build)
                (via, _ecx, frame, _record), = m.state['calls']
                text = m.cstr(frame[1]) if track else frame[1]
                if via != 'text' or text != (titles[track] if track else SIGIL) or frame[2] != 0x41200000:
                    raise SystemExit('dcmusictest: %s BGM TEST name of %d with %r: %r' % (build, value, files, text))
                m.state['calls'].clear()
                mu.mem_write(RECORDS + 13 * RECORD, struct.pack('<I', OWN))
                m.call(25, (value, 0, 0, 0), what=build)
                (via, ecx, frame, record), = m.state['calls']
                want = ('play', BANK, 13, track - 1) if track else ('play', BANK, value, OWN)
                if (via, ecx, frame[1], record) != want:
                    raise SystemExit('dcmusictest: %s BGM TEST play of %d with %r: %r'
                                     % (build, value, files, m.state['calls']))


def main():
    for build in patcher.BUILDS:
        exe(build)
    options()
    print('dcmusictest: the ending plays track 18, the replays tracks 15, 11, 16 and 17, the course choices '
          '7 to 10 the same, OPTION names and previews them and BGM TEST plays 15 to 18, each when its file is there, '
          'in %d builds OK'
          % len(patcher.BUILDS))


if __name__ == '__main__':
    main()
