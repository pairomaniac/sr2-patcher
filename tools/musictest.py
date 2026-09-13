#!/usr/bin/env python3
"""Run the music hook under Unicorn against a scripted MCI session.

    python3 tools/musictest.py GAMEDIR      # GAMEDIR holds MUSASHI/MGAudio.dll

Patches a copy of MGAudio.dll in memory, maps it at a relocated base, stubs
every import the blob resolves, and drives it the way MGAudio does: open by
type ID, set, status, play, position, seek, pause, resume, stop, close, plus
the cases that must be forwarded or refused; then runs the worker on each
operation and checks the waveOut and file calls it makes. Needs
python3-unicorn; exits 0 with a note when it is missing so tools/check.py
can skip it.
"""
import hashlib
import importlib.util
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('patcher', os.path.join(HERE, '..', 'sr2-patcher.py'))
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EIP
except ImportError:
    print('musictest: skipped, python3-unicorn not installed')
    sys.exit(0)

BASE = 0x01DD0000                       # where Proton put it, not the preferred base
STUBS = 0x03000000
SCRATCH = 0x04000000
STACK = 0x05000000
TRACKS = {2: 1000, 3: 2000, 5: 75 * 60 * 3}     # track: length in frames
EXE = 'S:\\Sega Rally 2\\SEGA RALLY 2.exe'


def tmsf(t, m, s, f):
    return t | m << 8 | s << 16 | f << 24


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    path = os.path.join(argv[1], 'MUSASHI', 'MGAudio.dll')
    if os.path.isfile(path + '.bak'):           # the folder is patched already
        path += '.bak'
    with open(path, 'rb') as fh:
        raw = bytearray(fh.read())
    build = next((b for b, row in patcher.BUILDS.items()
                  if row['files']['MUSASHI\\MGAudio.dll'][1] == hashlib.md5(raw).hexdigest()), None)
    if build is None:
        print('musictest: %s is not an MGAudio.dll the patcher knows' % path)
        return 1
    image = patcher.apply_music(raw, build)

    # Map the image by section, like a loader would.
    pe_off = struct.unpack_from('<I', image, 0x3c)[0]
    nsec = struct.unpack_from('<H', image, pe_off + 6)[0]
    opt = pe_off + 24
    entry = struct.unpack_from('<I', image, opt + 16)[0]
    size = struct.unpack_from('<I', image, opt + 56)[0]
    table = opt + struct.unpack_from('<H', image, pe_off + 20)[0]
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(BASE, (size + 0xfff) & ~0xfff)
    mu.mem_write(BASE, bytes(image[:0x1000]))
    hook_rva = None
    for i in range(nsec):
        name, vsize, va, rsize, roff = struct.unpack_from('<8sIIII', image, table + i * 40)
        mu.mem_write(BASE + va, bytes(image[roff:roff + rsize]))
        if name.rstrip(b'\0') == patcher.MUSIC_SECTION:
            hook_rva = va
    assert entry == hook_rva + 5
    # Relocate, as the loader does at this base: this is what catches a
    # relocation entry left on a byte that is no longer absolute.
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
    # Every rewritten call site must still point at the hook after that.
    code = bytes(mu.mem_read(BASE + 0x1000, 0x8000))
    sites = [m.start() for m in re.finditer(b'\xe8....\x90', code)]
    targets = [0x1000 + s_ + 5 + struct.unpack_from('<i', code, s_ + 1)[0] for s_ in sites]
    assert targets.count(hook_rva) == patcher.MCI_CALL_SITES, 'call sites after relocation: %r' % targets
    assert targets.count(hook_rva + 10) == patcher.MCI_LOAD_SITES, 'load site after relocation: %r' % targets
    mu.mem_map(STUBS, 0x1000)
    mu.mem_map(SCRATCH, 0x10000)
    mu.mem_map(STACK, 0x100000)

    # Import slots -> stubs. Each stub is `ret N` at STUBS + 0x10 * k.
    # The imports, then the two COM vtables' methods (this counted in argc).
    names = ['LoadLibraryA', 'GetProcAddress', 'GetModuleFileNameA', 'mciSendCommandA',
             'CreateFileA', 'GetFileSize', 'CloseHandle', 'CreateFileMappingA', 'MapViewOfFile',
             'UnmapViewOfFile', 'CreateThread', 'CreateEventA', 'SetEvent', 'WaitForSingleObject',
             'OutputDebugStringA', 'DirectSoundCreate', 'GetDesktopWindow', 'CreateMutexA', 'ReleaseMutex',
             'CreateSoundBuffer', 'SetCooperativeLevel',
             'Release', 'GetCurrentPosition', 'GetStatus', 'Lock', 'Play', 'SetCurrentPosition',
             'SetVolume', 'Stop', 'Unlock']
    argc = {'LoadLibraryA': 1, 'GetProcAddress': 2, 'GetModuleFileNameA': 3, 'mciSendCommandA': 4,
            'CreateFileA': 7, 'GetFileSize': 2, 'CloseHandle': 1, 'CreateFileMappingA': 6,
            'MapViewOfFile': 5, 'UnmapViewOfFile': 1, 'CreateThread': 6, 'CreateEventA': 4,
            'SetEvent': 1, 'WaitForSingleObject': 2, 'OutputDebugStringA': 1, 'DirectSoundCreate': 3,
            'GetDesktopWindow': 0, 'CreateMutexA': 3, 'ReleaseMutex': 1, 'CreateSoundBuffer': 4,
            'SetCooperativeLevel': 3,
            'Release': 1, 'GetCurrentPosition': 3, 'GetStatus': 2, 'Lock': 8, 'Play': 4,
            'SetCurrentPosition': 2, 'SetVolume': 2, 'Stop': 1, 'Unlock': 5}
    HREQ, HDONE, HMUTEX, HMAP, VIEW, DESKTOP = 0x501, 0x502, 0x503, 0x800, 0x06000000, 0x77
    DS, DSVT, BUF, BUFVT, BUFMEM = SCRATCH + 0x1000, SCRATCH + 0x1010, SCRATCH + 0x1100, SCRATCH + 0x1110, 0x07000000
    OPS = {1: 'open', 2: 'play', 3: 'stop', 4: 'pause', 5: 'resume', 6: 'close', 7: 'pos', 8: 'vol'}
    blob_len = len(patcher.MUSIC_BLOB)
    D_OP = BASE + hook_rva + blob_len - 12
    D_RESULT = BASE + hook_rva + blob_len - 4
    addr = {n: STUBS + 0x10 * k for k, n in enumerate(names)}
    for n in names:
        mu.mem_write(addr[n], b'\xc2' + struct.pack('<H', argc[n] * 4))
    for n in ('LoadLibraryA', 'GetProcAddress', 'GetModuleFileNameA'):
        mu.mem_write(BASE + patcher._iat_slot(image, 'kernel32.dll', n), struct.pack('<I', addr[n]))
    mu.mem_write(BASE + patcher._iat_slot(image, 'winmm.dll', 'mciSendCommandA'),
                 struct.pack('<I', addr['mciSendCommandA']))
    mu.mem_map(VIEW, 0x1000)
    mu.mem_map(BUFMEM, 0x1000)
    # the fake IDirectSound and IDirectSoundBuffer: vtables of stubs
    mu.mem_write(DS, struct.pack('<I', DSVT))
    mu.mem_write(DSVT + 0x0c, struct.pack('<I', addr['CreateSoundBuffer']))
    mu.mem_write(DSVT + 0x18, struct.pack('<I', addr['SetCooperativeLevel']))
    mu.mem_write(BUF, struct.pack('<I', BUFVT))
    for off, n in ((0x08, 'Release'), (0x10, 'GetCurrentPosition'), (0x24, 'GetStatus'), (0x2c, 'Lock'),
                   (0x30, 'Play'), (0x34, 'SetCurrentPosition'), (0x3c, 'SetVolume'), (0x48, 'Stop'),
                   (0x4c, 'Unlock')):
        mu.mem_write(BUFVT + off, struct.pack('<I', addr[n]))
    mu.mem_write(VIEW + 44, bytes(range(256)) * 4)

    # requests: what the hook asked the worker, as (op, arg); calls: what
    # the worker did, as (function, args...). The SetEvent stub answers a
    # request the way the worker would, so the hook can be driven alone.
    log = {'requests': [], 'calls': [], 'opened': [], 'thread': None, 'events': 0, 'waits': [],
           'answer': 0, 'position': 62500 * 1764 // 10, 'status': 1}

    def cstr(p):
        out = b''
        while b'\0' not in out:
            out += bytes(mu.mem_read(p + len(out), 16))
        return out.split(b'\0')[0].decode('latin-1')

    def stub(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        args = struct.unpack('<8I', mu.mem_read(esp + 4, 32))
        name = names[(address - STUBS) // 0x10]
        ret = 0
        if name == 'LoadLibraryA':
            ret = {'dsound.dll': 1, 'user32.dll': 3, 'kernel32.dll': 2}.get(cstr(args[0]), 0)
        elif name == 'GetProcAddress':
            ret = addr.get(cstr(args[1]), 0)
        elif name == 'GetModuleFileNameA':
            mu.mem_write(args[1], EXE.encode() + b'\0')
            ret = len(EXE)
        elif name == 'CreateFileA':
            path = cstr(args[0])
            log['opened'].append(path)
            prefix = 'S:\\Sega Rally 2\\music\\track'
            ret = 0xFFFFFFFF
            if path.startswith(prefix) and path.endswith('.wav'):
                n = int(path[len(prefix):len(prefix) + 2])
                if n in TRACKS:
                    ret = 0x100 + n
        elif name == 'GetFileSize':
            ret = TRACKS[args[0] - 0x100] * 2352 + 44
        elif name == 'CloseHandle':
            log['calls'].append(('CloseHandle', args[0]))
            ret = 1
        elif name == 'CreateFileMappingA':
            log['calls'].append(('CreateFileMappingA', args[0], args[2]))
            ret = HMAP
        elif name == 'MapViewOfFile':
            log['calls'].append(('MapViewOfFile', args[0], args[1]))
            ret = VIEW
        elif name == 'UnmapViewOfFile':
            log['calls'].append(('UnmapViewOfFile', args[0]))
            ret = 1
        elif name == 'CreateThread':
            log['thread'] = args[2]
            ret = 0x600
        elif name == 'CreateEventA':
            log['events'] += 1
            ret = HREQ if log['events'] == 1 else HDONE
        elif name == 'SetEvent':
            if args[0] == HREQ:
                op, arg = struct.unpack('<II', mu.mem_read(D_OP, 8))
                log['requests'].append((OPS[op], arg))
                mu.mem_write(D_RESULT, struct.pack('<I', log['answer']))
            ret = 1
        elif name == 'WaitForSingleObject':
            log['waits'].append(args[0])
        elif name == 'mciSendCommandA':
            log.setdefault('forwarded', []).append((args[0], args[1]))
            ret = 0x9999
        elif name == 'DirectSoundCreate':
            log['calls'].append(('DirectSoundCreate', args[0], args[2]))
            mu.mem_write(args[1], struct.pack('<I', DS))
        elif name == 'GetDesktopWindow':
            ret = DESKTOP
        elif name == 'CreateMutexA':
            ret = HMUTEX
        elif name == 'ReleaseMutex':
            log['released'] = log.get('released', 0) + 1
            ret = 1
        elif name == 'SetCooperativeLevel':
            log['calls'].append(('SetCooperativeLevel', args[0], args[1], args[2]))
        elif name == 'CreateSoundBuffer':
            desc = struct.unpack('<IIIII', mu.mem_read(args[1], 20))
            fmt = struct.unpack('<HHIIHHH', mu.mem_read(desc[4], 18))
            log['calls'].append(('CreateSoundBuffer', args[0], desc[:4], fmt, args[3]))
            mu.mem_write(args[2], struct.pack('<I', BUF))
        elif name == 'Lock':
            log['calls'].append(('Lock', args[0], args[1], args[2], args[7]))
            mu.mem_write(args[3], struct.pack('<I', BUFMEM))
            mu.mem_write(args[4], struct.pack('<I', 1000))
            mu.mem_write(args[5], struct.pack('<I', 0))
            mu.mem_write(args[6], struct.pack('<I', 0))
        elif name == 'GetCurrentPosition':
            log['calls'].append(('GetCurrentPosition', args[0]))
            mu.mem_write(args[1], struct.pack('<I', log['position']))
        elif name == 'GetStatus':
            log['calls'].append(('GetStatus', args[0]))
            mu.mem_write(args[1], struct.pack('<I', log['status']))
        elif name in ('Release', 'Play', 'SetCurrentPosition', 'SetVolume', 'Stop', 'Unlock'):
            log['calls'].append((name,) + tuple(a if a < 0x80000000 else a - 0x100000000 for a in args[:argc[name]]))
        elif name == 'OutputDebugStringA':
            log.setdefault('traced', []).append(cstr(args[0]))
        mu.reg_write(UC_X86_REG_EAX, ret)
        # caller-saved, as any real import may leave them
        mu.reg_write(UC_X86_REG_ECX, 0xC1C1C1C1)
        mu.reg_write(UC_X86_REG_EDX, 0xD2D2D2D2)

    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x200)

    def call(target, *args):
        esp = STACK + 0x80000
        mu.mem_write(esp, struct.pack('<I', 0xDEAD0000) + b''.join(struct.pack('<I', a) for a in args))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(target, 0xDEAD0000, count=2000000)
        return mu.reg_read(UC_X86_REG_EAX)

    rounds = []

    def stop_second_wait(mu_, address, size_, user):
        if names[(address - STUBS) // 0x10] == 'WaitForSingleObject':
            rounds.append(1)
            if len(rounds) == 2:
                mu_.emu_stop()

    def work(op, arg=0):
        """One worker round on (op, arg): wait, do, answer, wait again."""
        mu.mem_write(D_OP, struct.pack('<II', op, arg))
        log['calls'] = []
        del rounds[:]
        h = mu.hook_add(UC_HOOK_CODE, stop_second_wait, begin=STUBS, end=STUBS + 0x200)
        mu.reg_write(UC_X86_REG_ESP, STACK + 0x40000)
        mu.mem_write(STACK + 0x40000, struct.pack('<II', 0xDEAD0000, 0))
        mu.emu_start(log['thread'], 0xDEAD0000, count=1000000)
        mu.hook_del(h)
        assert len(rounds) == 2, 'worker did not loop'
        return struct.unpack('<I', mu.mem_read(D_RESULT, 4))[0]

    # DllMain(hinst, DLL_PROCESS_ATTACH, 0): startup, stopping where it chains.
    orig_entry = struct.unpack_from('<I', raw, pe_off + 24 + 16)[0]
    esp = STACK + 0x80000
    mu.mem_write(esp, struct.pack('<IIII', 0xDEAD0000, BASE, 1, 0))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.emu_start(BASE + entry, BASE + orig_entry, count=5000000)
    assert mu.reg_read(UC_X86_REG_EIP) == BASE + orig_entry, 'startup did not chain'
    assert mu.reg_read(UC_X86_REG_ESP) == esp, 'startup left the stack moved'
    assert log['opened'] == ['S:\\Sega Rally 2\\music\\trace'] + \
        ['S:\\Sega Rally 2\\music\\track%02d.wav' % n for n in range(2, 100)], log['opened'][:3]
    assert log['thread'] and log['events'] == 2, 'no worker thread or events'
    # a second attach must not rebuild
    log['opened'] = []
    mu.mem_write(esp, struct.pack('<IIII', 0xDEAD0000, BASE, 1, 0))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.emu_start(BASE + entry, BASE + orig_entry, count=5000000)
    assert log['opened'] == []

    hook = BASE + hook_rva
    P = SCRATCH
    # the +10 thunk: esi = hook, ebx untouched
    from unicorn.x86_const import UC_X86_REG_ESI, UC_X86_REG_EBX
    mu.reg_write(UC_X86_REG_EBX, 0x12345678)
    call(hook + 10)
    assert mu.reg_read(UC_X86_REG_ESI) == hook and mu.reg_read(UC_X86_REG_EBX) == 0x12345678
    # open cdaudio by type id
    mu.mem_write(P, struct.pack('<IIIII', 0, 0, 0x204, 0, 0))
    assert call(hook, 0, 0x803, 0x3100, P) == 0
    assert struct.unpack_from('<I', mu.mem_read(P, 20), 4)[0] == 0xFACE, 'no fake id'
    # open of anything else is forwarded
    mu.mem_write(P, struct.pack('<IIIII', 0, 0, 0x400, 0, 0))
    assert call(hook, 0, 0x803, 0x3100, P) == 0x9999 and log['forwarded'][-1] == (0, 0x803)
    # a call with another device id is forwarded
    assert call(hook, 7, 0x814, 0x100, P) == 0x9999
    # set time format
    assert call(hook, 0xFACE, 0x80D, 0x400, P) == 0
    # status: number of tracks, length of track 5 (3:00:00 MSF), position when idle
    mu.mem_write(P, struct.pack('<IIII', 0, 0, 3, 0))
    assert call(hook, 0xFACE, 0x814, 0x100, P) == 0
    assert struct.unpack_from('<I', mu.mem_read(P, 16), 4)[0] == 5, 'ntracks'
    mu.mem_write(P, struct.pack('<IIII', 0, 0, 1, 5))
    assert call(hook, 0xFACE, 0x814, 0x110, P) == 0
    assert struct.unpack_from('<I', mu.mem_read(P, 16), 4)[0] == (3 | 0 << 8 | 0 << 16), 'length'
    assert log['requests'] == [], 'a request before any play: %r' % log['requests']
    # play track 5 from 0:01:00 (TMSF) -> open 5, play from 1000
    mu.mem_write(P, struct.pack('<III', 0, tmsf(5, 0, 1, 0), 0))
    assert call(hook, 0xFACE, 0x806, 5, P) == 0
    assert log['requests'] == [('open', 5), ('play', 1000)], log['requests']
    assert log['waits'] and set(log['waits']) == {HMUTEX, HDONE}, 'the hook waits on the mutex, then the done event'
    assert log['waits'].count(HMUTEX) == log['waits'].count(HDONE) == log['released'], 'a release per request'
    # an open the worker refuses: the play returns its error and sends no play
    log['requests'], log['answer'] = [], 0x115
    assert call(hook, 0xFACE, 0x806, 5, P) == 0x115 and log['requests'] == [('open', 5)]
    log['answer'] = 0
    call(hook, 0xFACE, 0x806, 5, P)
    # play a track with no file -> out of range, nothing sent
    log['requests'] = []
    mu.mem_write(P, struct.pack('<III', 0, tmsf(4, 0, 0, 0), 0))
    assert call(hook, 0xFACE, 0x806, 4, P) == 0x112 and log['requests'] == []
    # position while playing: 62500 ms on track 5 -> 1:02 frame 37
    log['answer'] = 62500
    mu.mem_write(P, struct.pack('<IIII', 0, 0, 2, 0))
    assert call(hook, 0xFACE, 0x814, 0x100, P) == 0 and log['requests'] == [('pos', 0)]
    assert struct.unpack_from('<I', mu.mem_read(P, 16), 4)[0] == tmsf(5, 1, 2, 37), hex(struct.unpack_from('<I', mu.mem_read(P, 16), 4)[0])
    log['answer'] = 0
    # seek within the open track: a play from there
    log['requests'] = []
    mu.mem_write(P, struct.pack('<II', 0, tmsf(5, 2, 0, 15)))
    assert call(hook, 0xFACE, 0x807, 8, P) == 0 and log['requests'] == [('play', 120200)], log['requests']
    # the exe's seek names the track below the one it plays: the same
    mu.mem_write(P, struct.pack('<II', 0, tmsf(4, 0, 0, 0)))
    log['requests'] = []
    assert call(hook, 0xFACE, 0x807, 8, P) == 0 and log['requests'] == [('play', 0)], log['requests']
    # pause, resume, stop, close
    log['requests'] = []
    for msg in (0x809, 0x855, 0x808, 0x804):
        assert call(hook, 0xFACE, msg, 0, P) == 0
    assert log['requests'] == [('pause', 0), ('resume', 0), ('stop', 0), ('close', 0)], log['requests']
    # position when closed: track 5, 0:00, and nothing asked
    log['requests'] = []
    mu.mem_write(P, struct.pack('<IIII', 0, 0, 2, 0))
    assert call(hook, 0xFACE, 0x814, 0x100, P) == 0 and log['requests'] == []
    assert struct.unpack_from('<I', mu.mem_read(P, 16), 4)[0] == tmsf(5, 0, 0, 0)
    # seek on a closed device, then play without FROM starts that track there
    log['requests'] = []
    mu.mem_write(P, struct.pack('<II', 0, tmsf(3, 0, 10, 0)))
    assert call(hook, 0xFACE, 0x807, 8, P) == 0 and log['requests'] == []
    mu.mem_write(P, struct.pack('<III', 0, 0, 0))
    assert call(hook, 0xFACE, 0x806, 0, P) == 0
    assert log['requests'] == [('open', 3), ('play', 10000)], log['requests']

    # The volume, by the exe's four sites: the menu's level (flags 0x40
    # once cdlevel marks it, or told by its value, a multiple of 1100),
    # the race's level and the mute (flags bit 31), the fade (flags 0).
    # A level is the step on the mix's curve plus CD_DB, in hundredths of
    # a dB, 0 dB at 9, -10000 at 0; the fade is amplitude percent of it.
    CURVE = [-10000] + [-3950 + 350 * s + 300 for s in range(1, 10)]
    MENU, RACE = 0x40, 0x80000000

    def vol():
        return struct.unpack('<i', mu.mem_read(D_VOLADDR, 4))[0]

    def setvol(v, flags=0):
        mu.mem_write(V, struct.pack('<IIIII', 0x2c, 0, 2, v, v))
        log['requests'] = []
        assert call(hook + 15, 0x1234, V, flags) == 0
        return vol()

    V = STACK + 0x300
    mu.mem_write(V, struct.pack('<IIIII', 0x2c, 0, 0, 0, 0))
    assert call(hook + 20, 0x1234, V, 0x80000000) == 0
    assert struct.unpack_from('<III', mu.mem_read(V, 20), 8) == (2, 10000, 10000), 'getvolume: full'
    # D_SLIDER is stored right after the curve's `lea ecx, [eax - 3150]`
    # in setvolume; D_VOL is the dword before it
    i = patcher.MUSIC_BLOB.index(b'\x8d\x88' + struct.pack('<i', -3950 + 300)) + 6
    assert patcher.MUSIC_BLOB[i:i + 2] == b'\x89\x8b'
    D_VOLADDR = hook + struct.unpack_from('<I', patcher.MUSIC_BLOB, i + 2)[0] - 4
    # the menu's level, marked: step x 1100, 10000 at 9
    assert setvol(8800, MENU) == CURVE[8] and log['requests'] == [('vol', CURVE[8] & 0xFFFFFFFF)], log['requests']
    assert setvol(10000, MENU) == CURVE[9] == -500
    assert setvol(4400, MENU) == CURVE[4]
    # a step of a fade with no fade begun is dropped
    assert setvol(5000) == CURVE[4] and log['requests'] == []
    # the fade: amplitude percent of the level, from its start at 100
    assert setvol(10000) == CURVE[4], 'the fade starts at the level'
    assert setvol(9000) == CURVE[4] - 92
    assert setvol(5000) == CURVE[4] - 602
    assert setvol(1000) == CURVE[4] - 2000
    # a level ends it: the fade's stragglers on the next track are dropped
    assert setvol(4400, MENU) == CURVE[4]
    assert setvol(1000) == CURVE[4] and log['requests'] == []
    # the race's level: step x 900; the mute keeps the level and ends a fade
    assert setvol(7200, RACE) == CURVE[8]
    assert setvol(10000) == CURVE[8]
    assert setvol(0, RACE) == -10000, 'mute'
    assert setvol(5000) == -10000 and log['requests'] == []
    assert setvol(10000) == CURVE[8], 'the level survived the mute'
    assert setvol(5000) == CURVE[8] - 602
    assert setvol(8100, RACE) == CURVE[9]
    # unmarked, a value is a fade's, whatever it is
    assert setvol(7700) == CURVE[9] and log['requests'] == []
    assert setvol(10000) == CURVE[9]
    assert setvol(7700) == CURVE[9] - 227
    assert setvol(12000, MENU) == CURVE[9], 'over the top clamps to 10000'
    assert setvol(0, MENU) == -10000, 'the slider at 0'
    assert setvol(10000) == -10000 and setvol(5000) == -10000, 'off stays off'
    assert setvol(0) == -10000
    mu.mem_write(V, struct.pack('<IIIII', 0x2c, 0, 0, 0, 0))              # no channels: keeps it
    log['requests'] = []
    assert call(hook + 15, 0x1234, V, 0) == 0 and vol() == -10000 and log['requests'] == []
    setvol(10000, MENU)

    # The worker: each operation and the DirectSound calls it makes. Track
    # 5's samples are 3:00 of frames, 2352 bytes each; the lock hands back
    # 1000 bytes at a time here, which is what the copy must honour.
    size5 = TRACKS[5] * 2352
    fmt = (1, 2, 44100, 176400, 4, 16, 0)
    assert work(6) == 0 and log['calls'] == [], 'close with nothing open'
    assert work(1, 5) == 0
    assert log['calls'] == [('DirectSoundCreate', 0, 0), ('SetCooperativeLevel', DS, DESKTOP, 1),
                            ('CreateFileMappingA', 0x105, 2), ('MapViewOfFile', HMAP, 4),
                            ('CreateSoundBuffer', DS, (36, 0x18088, size5, 0), fmt, 0),
                            ('Lock', BUF, 0, size5, 0), ('Unlock', BUF, BUFMEM, 1000, 0, 0),
                            ('UnmapViewOfFile', VIEW), ('CloseHandle', HMAP), ('CloseHandle', 0x105),
                            ('SetVolume', BUF, CURVE[9])], log['calls']
    assert mu.mem_read(BUFMEM, 1000) == mu.mem_read(VIEW + 44, 1000), 'the samples copied'
    assert work(2, 1000) == 0
    off = 1000 * 1764 // 10
    assert log['calls'] == [('SetCurrentPosition', BUF, off), ('SetVolume', BUF, CURVE[9]), ('Play', BUF, 0, 0, 0)], log['calls']
    assert work(7) == 62500 and log['calls'] == [('GetStatus', BUF), ('GetCurrentPosition', BUF)]
    assert work(4) == 0 and log['calls'] == [('SetVolume', BUF, -10000), ('Stop', BUF)]
    assert work(4) == 0 and log['calls'] == [], 'pause twice'
    assert work(7) == 62500 and log['calls'] == [('GetCurrentPosition', BUF)], 'paused: the cursor, no status'
    assert work(5) == 0 and log['calls'] == [('SetVolume', BUF, CURVE[9]), ('Play', BUF, 0, 0, 0)]
    assert work(5) == 0 and log['calls'] == [], 'resume twice'
    assert work(8) == 0 and log['calls'] == [('SetVolume', BUF, CURVE[9])]
    # a play past the end starts on the last frame; the buffer then stops
    # itself, which the position reports as the end
    assert work(2, 999999) == 0 and log['calls'] == [('SetCurrentPosition', BUF, size5 - 4), ('SetVolume', BUF, CURVE[9]), ('Play', BUF, 0, 0, 0)]
    log['status'] = 0
    assert work(7) == TRACKS[5] * 2352 * 1000 // 176400 and log['calls'] == [('GetStatus', BUF)]
    log['status'] = 1
    assert work(3) == 0 and log['calls'] == [('SetVolume', BUF, -10000), ('Stop', BUF), ('SetCurrentPosition', BUF, 0)]
    log['position'] = 0
    assert work(7) == 0 and log['calls'] == [('GetCurrentPosition', BUF)], 'stopped: the cursor, no status'
    assert work(5) == 0 and log['calls'] == [], 'a resume when stopped is nothing'
    assert work(6) == 0 and log['calls'] == [('SetVolume', BUF, -10000), ('Stop', BUF), ('Release', BUF)]
    assert work(7) == 0 and log['calls'] == [], 'position with nothing open'
    assert work(2, 0) == 0x115 and log['calls'] == [], 'play with nothing open'
    # an open of a missing file fails and holds nothing; the DirectSound object stays
    assert work(1, 4) == 0x115 and log['calls'] == []
    assert work(1, 2) == 0 and log['calls'][0] == ('CreateFileMappingA', 0x102, 2)
    assert work(1, 3) == 0 and log['calls'][:3] == [('SetVolume', BUF, -10000), ('Stop', BUF), ('Release', BUF)]
    print('musictest OK: startup, hook, worker: open, play, position, seek, pause/resume/stop/close, volume, forwarding')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
