#!/usr/bin/env python3
"""Run the music hook under Unicorn against a scripted MCI session.

    python3 tools/musictest.py GAMEDIR      # GAMEDIR holds MUSASHI/MGAudio.dll

Patches a copy of MGAudio.dll in memory, maps it at a relocated base, stubs
the five imports the blob uses, and drives it the way MGAudio does: open by
type ID, set, status, play, position, seek, pause, resume, stop, close, plus
the cases that must be forwarded or refused. Needs python3-unicorn; exits 0
with a note when it is missing so tools/check.py can skip it.
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
    from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EIP
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
    names = ['LoadLibraryA', 'GetProcAddress', 'GetModuleFileNameA', 'mciSendCommandA',
             'mciSendStringA', 'CreateFileA', 'GetFileSize', 'CloseHandle',
             'CreateThread', 'CreateEventA', 'SetEvent', 'WaitForSingleObject', 'waveOutSetVolume']
    argc = {'LoadLibraryA': 1, 'GetProcAddress': 2, 'GetModuleFileNameA': 3, 'mciSendCommandA': 4,
            'mciSendStringA': 4, 'CreateFileA': 7, 'GetFileSize': 2, 'CloseHandle': 1,
            'CreateThread': 6, 'CreateEventA': 4, 'SetEvent': 1, 'WaitForSingleObject': 2,
            'waveOutSetVolume': 2}
    HREQ, HDONE = 0x501, 0x502
    blob_len = len(patcher.MUSIC_BLOB)
    D_CMD = BASE + hook_rva + blob_len - (512 + 32 + 4)
    D_RET = BASE + hook_rva + blob_len - (32 + 4)
    D_RESULT = BASE + hook_rva + blob_len - 4
    addr = {n: STUBS + 0x10 * k for k, n in enumerate(names)}
    for n in names:
        mu.mem_write(addr[n], b'\xc2' + struct.pack('<H', argc[n] * 4))
    for n in ('LoadLibraryA', 'GetProcAddress', 'GetModuleFileNameA'):
        mu.mem_write(BASE + patcher._iat_slot(image, 'kernel32.dll', n), struct.pack('<I', addr[n]))
    mu.mem_write(BASE + patcher._iat_slot(image, 'winmm.dll', 'mciSendCommandA'),
                 struct.pack('<I', addr['mciSendCommandA']))

    log = {'strings': [], 'forwarded': [], 'opened': [], 'thread': None, 'events': 0, 'waits': [], 'volume': []}

    def cstr(p):
        return bytes(mu.mem_read(p, 300)).split(b'\0')[0].decode('latin-1')

    def stub(mu, address, size_, user):
        esp = mu.reg_read(UC_X86_REG_ESP)
        args = struct.unpack('<8I', mu.mem_read(esp + 4, 32))
        name = names[(address - STUBS) // 0x10]
        ret = 0
        if name == 'LoadLibraryA':
            ret = {'winmm.dll': 1, 'kernel32.dll': 2}.get(cstr(args[0]), 0)
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
            ret = 1
        elif name == 'mciSendStringA':
            cmd = cstr(args[0])
            log['strings'].append(cmd)
            if cmd == 'status sr2bgm position':
                mu.mem_write(args[1], b'62500\0')
        elif name == 'CreateThread':
            log['thread'] = args[2]
            ret = 0x600
        elif name == 'CreateEventA':
            log['events'] += 1
            ret = HREQ if log['events'] == 1 else HDONE
        elif name == 'SetEvent':
            if args[0] == HREQ:
                # what the worker would do with the request
                cmd = cstr(D_CMD)
                log['strings'].append(cmd)
                mu.mem_write(D_RET, b'62500\0' if cmd == 'status sr2bgm position' else b'\0')
                mu.mem_write(D_RESULT, struct.pack('<I', 0))
            ret = 1
        elif name == 'WaitForSingleObject':
            log['waits'].append(args[0])
            ret = 0
        elif name == 'mciSendCommandA':
            log['forwarded'].append((args[0], args[1]))
            ret = 0x9999
        elif name == 'waveOutSetVolume':
            log['volume'].append((args[0], args[1]))
        mu.reg_write(UC_X86_REG_EAX, ret)

    mu.hook_add(UC_HOOK_CODE, stub, begin=STUBS, end=STUBS + 0x100)

    def call(target, *args):
        esp = STACK + 0x80000
        mu.mem_write(esp, struct.pack('<I', 0xDEAD0000) + b''.join(struct.pack('<I', a) for a in args))
        mu.reg_write(UC_X86_REG_ESP, esp)
        mu.emu_start(target, 0xDEAD0000, count=2000000)
        return mu.reg_read(UC_X86_REG_EAX)

    # DllMain(hinst, DLL_PROCESS_ATTACH, 0): startup, stopping where it chains.
    orig_entry = struct.unpack_from('<I', raw, pe_off + 24 + 16)[0]
    esp = STACK + 0x80000
    mu.mem_write(esp, struct.pack('<IIII', 0xDEAD0000, BASE, 1, 0))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.emu_start(BASE + entry, BASE + orig_entry, count=5000000)
    assert mu.reg_read(UC_X86_REG_EIP) == BASE + orig_entry, 'startup did not chain'
    assert mu.reg_read(UC_X86_REG_ESP) == esp, 'startup left the stack moved'
    assert log['opened'] == ['S:\\Sega Rally 2\\music\\track%02d.wav' % n for n in range(2, 100)], log['opened'][:3]
    assert log['thread'] and log['events'] == 2, 'no worker thread or events'
    # the worker body, one round: wait for a request, send D_CMD, answer
    mu.mem_write(D_CMD, b'stop sr2bgm\0')
    log['strings'] = []
    log['waits'] = []
    rounds = []

    def stop_second_wait(mu_, address, size_, user):
        if names[(address - STUBS) // 0x10] == 'WaitForSingleObject':
            rounds.append(1)
            if len(rounds) == 2:
                mu_.emu_stop()
    h = mu.hook_add(UC_HOOK_CODE, stop_second_wait, begin=STUBS, end=STUBS + 0x100)
    mu.reg_write(UC_X86_REG_ESP, STACK + 0x40000)
    mu.mem_write(STACK + 0x40000, struct.pack('<II', 0xDEAD0000, 0))
    mu.emu_start(log['thread'], 0xDEAD0000, count=100000)
    mu.hook_del(h)
    assert log['waits'][:1] == [HREQ] and log['strings'] == ['stop sr2bgm'], (log['waits'], log['strings'])
    assert len(rounds) == 2, 'worker did not loop'
    log['strings'] = []
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
    # play track 5 from 0:01:00 (TMSF) -> open, set, play from 1000
    mu.mem_write(P, struct.pack('<III', 0, tmsf(5, 0, 1, 0), 0))
    log['strings'] = []
    assert call(hook, 0xFACE, 0x806, 5, P) == 0
    assert log['strings'] == ['close sr2bgm',
                              'open "S:\\Sega Rally 2\\music\\track05.wav" type waveaudio alias sr2bgm',
                              'set sr2bgm time format milliseconds',
                              'play sr2bgm from 1000'], log['strings']
    assert log['waits'].count(HDONE) >= 4, 'hook did not wait for the worker'
    log['waits'] = []
    # play a track with no file -> out of range, nothing sent
    log['strings'] = []
    mu.mem_write(P, struct.pack('<III', 0, tmsf(4, 0, 0, 0), 0))
    assert call(hook, 0xFACE, 0x806, 4, P) == 0x112 and log['strings'] == []
    # position while playing: 62500 ms on track 5 -> 1:02 frame 37
    mu.mem_write(P, struct.pack('<IIII', 0, 0, 2, 0))
    assert call(hook, 0xFACE, 0x814, 0x100, P) == 0
    assert struct.unpack_from('<I', mu.mem_read(P, 16), 4)[0] == tmsf(5, 1, 2, 37), hex(struct.unpack_from('<I', mu.mem_read(P, 16), 4)[0])
    # seek within the open track
    log['strings'] = []
    mu.mem_write(P, struct.pack('<II', 0, tmsf(5, 2, 0, 15)))
    assert call(hook, 0xFACE, 0x807, 8, P) == 0 and log['strings'] == ['seek sr2bgm to 120200'], log['strings']
    # pause, resume, stop, close
    log['strings'] = []
    for msg in (0x809, 0x855, 0x808, 0x804):
        assert call(hook, 0xFACE, msg, 0, P) == 0
    assert log['strings'] == ['pause sr2bgm', 'resume sr2bgm', 'stop sr2bgm', 'close sr2bgm'], log['strings']
    # position when closed: track 5, 0:00
    mu.mem_write(P, struct.pack('<IIII', 0, 0, 2, 0))
    assert call(hook, 0xFACE, 0x814, 0x100, P) == 0
    assert struct.unpack_from('<I', mu.mem_read(P, 16), 4)[0] == tmsf(5, 0, 0, 0)
    # seek on a closed device, then play without FROM starts that track there
    log['strings'] = []
    mu.mem_write(P, struct.pack('<II', 0, tmsf(3, 0, 10, 0)))
    assert call(hook, 0xFACE, 0x807, 8, P) == 0 and log['strings'] == []
    mu.mem_write(P, struct.pack('<III', 0, 0, 0))
    assert call(hook, 0xFACE, 0x806, 0, P) == 0
    assert log['strings'][-1] == 'play sr2bgm from 10000' and 'track03.wav' in log['strings'][1], log['strings']
    assert log['waits'] and set(log['waits']) == {HDONE}, 'the hook waits only on the done event'

    # The volume. Pending after every open and play, applied from the
    # status polls until waveOutSetVolume succeeds; the stub always does.
    assert log['volume'] and set(log['volume']) == {(0, 0xFFFFFFFF)}, log['volume']
    log['volume'] = []
    call(hook, 0xFACE, 0x814, 0x100, P)                                   # the play above left it pending
    call(hook, 0xFACE, 0x814, 0x100, P)
    assert log['volume'] == [(0, 0xFFFFFFFF)], 'once after a play, then nothing: %r' % log['volume']
    log['volume'] = []
    V = STACK + 0x300
    mu.mem_write(V, struct.pack('<IIIII', 0x2c, 0, 2, 5000, 5000))        # the slider at half
    assert call(hook + 15, 0x1234, V, 0) == 0
    assert log['volume'] == [(0, 0x7FFF7FFF)], log['volume']
    mu.mem_write(V, struct.pack('<IIIII', 0x2c, 0, 2, 12000, 12000))      # over the top clamps
    call(hook + 15, 0x1234, V, 0)
    assert log['volume'][-1] == (0, 0xFFFFFFFF)
    mu.mem_write(V, struct.pack('<IIIII', 0x2c, 0, 0, 0, 0))              # no channels: keeps it
    assert call(hook + 15, 0x1234, V, 0) == 0 and log['volume'][-1] == (0, 0xFFFFFFFF)
    mu.mem_write(V, struct.pack('<IIIII', 0x2c, 0, 2, 0, 0))
    call(hook + 15, 0x1234, V, 0)
    log['volume'] = []
    call(hook, 0xFACE, 0x806, 0, P)                                       # play leaves it pending
    call(hook, 0xFACE, 0x814, 0x100, P)
    call(hook, 0xFACE, 0x814, 0x100, P)
    assert log['volume'] == [(0, 0)], 'applied once from the polls after a play: %r' % log['volume']
    print('musictest OK: startup, worker, open, status, play, position, seek, pause/resume/stop/close, forwarding, volume')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
