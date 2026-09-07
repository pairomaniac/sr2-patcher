#!/usr/bin/env python3
"""SEGA RALLY 2 (PC, 1999) patcher. See README.md.

    python3 sr2-patcher.py                          the window
    python3 sr2-patcher.py --install SRC DIR [LANG] install from data1.cab or the disc folder
    python3 sr2-patcher.py --patch DIR              patch an installed game
    python3 sr2-patcher.py --restore DIR            put the original exe back
    python3 sr2-patcher.py --selfcheck              validate the patch tables and exit
    python3 sr2-patcher.py --version

The version is the VERSION line below and nowhere else.

https://github.com/pairomaniac/sr2-patcher
"""
import hashlib
import os
import queue
import struct
import sys
import threading
import zlib

# Stamped by the build from the tag; a source checkout has no version.
VERSION = 'dev'
NAME = 'sr2-patcher'
LABEL = 'SR2 Patcher'
REPO_URL = 'https://github.com/pairomaniac/sr2-patcher'

EXE = 'SEGA RALLY 2.exe'
CAB = 'data1.cab'

# The Pentium III build: the six files the installer swaps in for it.
P3_FILES = (
    ('SEGA RALLY 2.exe', 1469952, '51b3da97c3c73611d3516b65bb684cb5'),
    ('AdvTelop.dll', 636928, '977dd8801a281e987c4503c9fb2f8778'),
    ('Champagn.dll', 699392, 'b8dbfe718eef561f12c99223ba7b9ec4'),
    ('MSelect.dll', 1137152, '1e6f713c39efb1558c79b795754d6e3a'),
    ('MUSASHI\\MGameGL.dll', 601600, '3d095385ece996088381dd77a0f5f954'),
    ('MUSASHI\\MGLBackground.dll', 579584, 'e7cc2a9f084a39c6f119fa1a1d769e30'),
)

# Patch sites in the P3 exe: (file offset, original, replacement).
# nodisc: the startup check that scans CD-ROM drives for the play disc
# (0x4273c0) returns 0, "found", at once.
PATCHES = {
    'nodisc': ((0x267c0, bytes.fromhex('8b442404'), bytes.fromhex('31c0c3')),),
}

LANGUAGES = ('English', 'French', 'German', 'Italian', 'Spanish', 'Japanese')

# Musashi COM servers, by CLSID, so the game can create them without the
# registry entries LAUNCH.exe -musashi would have written.
MUSASHI = (
    ('MGameD3D.dll', '1A413041-D93C-11D1-8F44-00A0C9697E45'),
    ('MGameGL.dll', '27AFF141-DA17-11D1-8F44-00A0C9697E45'),
    ('MGLBackground.dll', '452593F0-F878-11D2-ADB9-00A0C9A0FB23'),
    ('MGInput.dll', '5784B940-F4BC-11D1-A496-0000C02DB0F3'),
    ('MGSound.dll', '6177AF40-D601-11D1-A496-0000C02DB0F3'),
    ('MGAudio.dll', 'ACEF8F00-D517-11D1-A496-0000C02DB0F3'),
    ('MGNetWk.dll', '0D5837F0-3E3C-11D2-924E-00A0C9697E45'),
    ('MGameReg.dll', 'EE799FC0-D56F-11D2-8D16-00105A6B7166'),
    ('MEvent.dll', 'F8743DC0-627C-11D2-BD4E-0000C02DB0F3'),
    ('MStream.dll', '08A33BE0-61C6-11D2-BD4E-0000C02DB0F3'),
)

APP_MANIFEST = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity name="SEGARALLY2" version="1.0.0.0" type="win32" processorArchitecture="x86"/>
  <dependency>
    <dependentAssembly>
      <assemblyIdentity name="MUSASHI" version="1.0.0.0" type="win32" processorArchitecture="x86"/>
    </dependentAssembly>
  </dependency>
</assembly>
'''

ASM_MANIFEST_HEAD = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity name="MUSASHI" version="1.0.0.0" type="win32" processorArchitecture="x86"/>
'''


# InstallShield 5 cabinet

IS_SIGNATURE = 0x28635349
IS_COMPRESSED = 0x04
IS_INVALID = 0x08
IS_SPLIT = 0x01
IS_GROUP_SLOTS = 71


class Entry:
    __slots__ = ('name', 'directory', 'flags', 'size', 'compressed', 'offset', 'group')

    @property
    def path(self):
        return self.directory + '\\' + self.name if self.directory else self.name


class Cabinet:
    """data1.cab: the file table and the bytes of any one file."""

    def __init__(self, path):
        self.fh = open(path, 'rb')
        sig, _ver, _vol, desc_off, desc_size = struct.unpack('<5I', self.fh.read(0x14))
        if sig != IS_SIGNATURE:
            raise ValueError('not an InstallShield cabinet')
        self.fh.seek(desc_off)
        desc = self.fh.read(desc_size)
        ft_off, _x, ft_size, _y, dirs, _a, _b, files, _z = struct.unpack_from('<9I', desc, 0xc)
        self.fh.seek(desc_off + ft_off)
        table = self.fh.read(ft_size)
        offsets = struct.unpack_from('<%dI' % (dirs + files), table)

        def cstr(buf, off):
            end = buf.find(b'\0', off)
            return buf[off:end].decode('latin-1') if 0 <= off < len(buf) and end >= 0 else ''

        names = [cstr(table, o) for o in offsets[:dirs]]
        self.entries = []
        for i in range(files):
            p = offsets[dirs + i]
            name_off, dir_idx, flags, size, comp = struct.unpack_from('<IIHII', table, p)
            e = Entry()
            e.name = cstr(table, name_off)
            e.directory = names[dir_idx] if dir_idx < dirs else ''
            e.flags, e.size, e.compressed = flags, size, comp
            e.offset = struct.unpack_from('<I', table, p + 18 + 0x14)[0]
            e.group = None
            self.entries.append(e)
        # File groups: linked lists off 71 slots; each descriptor holds the
        # group's first and last file index.
        self.groups = {}
        for o in struct.unpack_from('<%dI' % IS_GROUP_SLOTS, desc, 0x3e):
            while o:
                name_off, d_off, o = struct.unpack_from('<3I', desc, o)
                first, last = struct.unpack_from('<2I', desc, d_off + 0x4c)
                name = cstr(desc, name_off)
                self.groups[name] = [e for e in self.entries[first:last + 1]
                                     if not e.flags & IS_INVALID]
                for e in self.groups[name]:
                    e.group = name

    def close(self):
        self.fh.close()

    def read(self, entry):
        if entry.flags & IS_SPLIT:
            raise ValueError('%s spans volumes' % entry.path)
        self.fh.seek(entry.offset)
        if entry.flags & IS_COMPRESSED:
            # One raw deflate stream per file, without header or end marker.
            data = zlib.decompressobj(-15).decompress(self.fh.read(entry.compressed))
        else:
            data = self.fh.read(entry.size)
        if len(data) != entry.size:
            raise ValueError('%s: %d bytes, expected %d' % (entry.path, len(data), entry.size))
        return data


# Install

def install_groups(lang):
    """The cab groups an install takes, in write order. Later groups
    overwrite earlier ones: the P3 modules go over the base ones."""
    region = 'Japanese' if lang == 'Japanese' else 'English'
    return ['Program Executable Files', 'PentiumIII Modules', lang,
            'BINDATA 0', 'BINDATA 1', 'BINDATA 2', 'BINDATA 3',
            region + ' Binary', 'Carprofile ' + region]


def find_cab(src):
    if os.path.isfile(src):
        return src
    for name in os.listdir(src):
        if name.lower() == CAB:
            return os.path.join(src, name)
    raise FileNotFoundError('no %s in %s' % (CAB, src))


def write_manifests(dest):
    with open(os.path.join(dest, EXE + '.manifest'), 'w', newline='\n') as fh:
        fh.write(APP_MANIFEST)
    lines = [ASM_MANIFEST_HEAD]
    for dll, clsid in MUSASHI:
        lines.append('  <file name="%s">\n    <comClass clsid="{%s}" threadingModel="Both"/>\n'
                     '  </file>\n' % (dll, clsid))
    lines.append('</assembly>\n')
    with open(os.path.join(dest, 'MUSASHI', 'MUSASHI.manifest'), 'w', newline='\n') as fh:
        fh.write(''.join(lines))


def install(src, dest, lang='English', log=print):
    if lang not in LANGUAGES:
        raise ValueError('unknown language %s' % lang)
    cab = Cabinet(find_cab(src))
    try:
        groups = install_groups(lang)
        missing = [g for g in groups if g not in cab.groups]
        if missing:
            raise ValueError('cabinet lacks groups: %s' % ', '.join(missing))
        total = sum(e.size for g in groups for e in cab.groups[g])
        log('install: %d MB to %s' % (total // 1000000, dest))
        for g in groups:
            for e in cab.groups[g]:
                out = os.path.join(dest, *e.path.split('\\'))
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, 'wb') as fh:
                    fh.write(cab.read(e))
            log('install: %s, %d files' % (g, len(cab.groups[g])))
    finally:
        cab.close()
    write_manifests(dest)
    log('install: manifests written')
    patch(dest, log)


# Patch

def md5(path):
    with open(path, 'rb') as fh:
        return hashlib.md5(fh.read()).hexdigest()


def check_build(dest):
    """Every P3 file present and untouched; the exe may already be patched."""
    for name, size, digest in P3_FILES:
        path = os.path.join(dest, *name.split('\\'))
        if not os.path.isfile(path):
            raise FileNotFoundError('missing %s' % name)
        if name == EXE:
            continue
        if os.path.getsize(path) != size or md5(path) != digest:
            raise ValueError('%s is not the Pentium III build' % name)


def patch(dest, log=print, keys=('nodisc',)):
    check_build(dest)
    exe = os.path.join(dest, EXE)
    bak = exe + '.bak'
    if os.path.isfile(bak):
        source = bak
    else:
        source = exe
    if md5(source) != P3_FILES[0][2]:
        raise ValueError('%s is not the Pentium III build' % os.path.basename(source))
    with open(source, 'rb') as fh:
        buf = bytearray(fh.read())
    if source == exe:
        with open(bak, 'wb') as fh:
            fh.write(buf)
        log('patch: backup written to %s' % os.path.basename(bak))
    for key in keys:
        for off, old, new in PATCHES[key]:
            if buf[off:off + len(old)] != old:
                raise ValueError('%s: unexpected bytes at 0x%x' % (key, off))
            buf[off:off + len(new)] = new
        log('patch: %s applied' % key)
    with open(exe, 'wb') as fh:
        fh.write(buf)
    log('patch: %s written' % EXE)


def restore(dest, log=print):
    exe = os.path.join(dest, EXE)
    bak = exe + '.bak'
    if not os.path.isfile(bak):
        raise FileNotFoundError('no backup beside %s' % EXE)
    os.replace(bak, exe)
    log('restore: original %s back in place' % EXE)


# Window

def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(LABEL)
    root.resizable(True, False)
    msgs = queue.Queue()

    src = tk.StringVar()
    dest = tk.StringVar()
    lang = tk.StringVar(value=LANGUAGES[0])

    def browse_src():
        p = filedialog.askopenfilename(title='data1.cab on the install disc',
                                       filetypes=[('data1.cab', 'data1.cab'), ('All', '*')])
        if p:
            src.set(p)

    def browse_dest():
        p = filedialog.askdirectory(title='Install folder')
        if p:
            dest.set(p)

    def log(text):
        msgs.put(text)

    def run(fn, *args):
        def body():
            try:
                fn(*args)
                log('done')
            except Exception as exc:
                log('error: %s' % exc)
            finally:
                log(None)
        for b in buttons:
            b.state(['disabled'])
        threading.Thread(target=body, daemon=True).start()

    def do_install():
        if not src.get() or not dest.get():
            messagebox.showwarning(LABEL, 'Pick data1.cab and an install folder.')
            return
        run(install, src.get(), dest.get(), lang.get(), log)

    def do_patch():
        if not dest.get():
            messagebox.showwarning(LABEL, 'Pick the install folder.')
            return
        run(patch, dest.get(), log)

    def do_restore():
        if not dest.get():
            messagebox.showwarning(LABEL, 'Pick the install folder.')
            return
        run(restore, dest.get(), log)

    frame = ttk.Frame(root, padding=8)
    frame.grid(sticky='nsew')
    root.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    ttk.Label(frame, text='data1.cab').grid(row=0, column=0, sticky='w')
    ttk.Entry(frame, textvariable=src, width=60).grid(row=0, column=1, sticky='ew', padx=4)
    ttk.Button(frame, text='Browse', command=browse_src).grid(row=0, column=2)
    ttk.Label(frame, text='Install to').grid(row=1, column=0, sticky='w')
    ttk.Entry(frame, textvariable=dest).grid(row=1, column=1, sticky='ew', padx=4)
    ttk.Button(frame, text='Browse', command=browse_dest).grid(row=1, column=2)
    ttk.Label(frame, text='Language').grid(row=2, column=0, sticky='w')
    ttk.Combobox(frame, textvariable=lang, values=LANGUAGES, state='readonly',
                 width=12).grid(row=2, column=1, sticky='w', padx=4)

    row = ttk.Frame(frame)
    row.grid(row=3, column=0, columnspan=3, pady=6, sticky='w')
    buttons = [ttk.Button(row, text='Install', command=do_install),
               ttk.Button(row, text='Patch', command=do_patch),
               ttk.Button(row, text='Restore original', command=do_restore)]
    for b in buttons:
        b.pack(side='left', padx=2)

    text = tk.Text(frame, height=12, width=80, state='disabled')
    text.grid(row=4, column=0, columnspan=3, sticky='nsew')

    def poll():
        while True:
            try:
                m = msgs.get_nowait()
            except queue.Empty:
                break
            if m is None:
                for b in buttons:
                    b.state(['!disabled'])
                continue
            text.configure(state='normal')
            text.insert('end', m + '\n')
            text.see('end')
            text.configure(state='disabled')
        root.after(100, poll)

    poll()
    root.mainloop()


def selfcheck():
    """Fail here, not half way through somebody's executable: every site
    inside the file, no two patches on one byte, replacement no longer
    than what it replaces."""
    size = P3_FILES[0][1]
    taken = {}
    for key, sites in PATCHES.items():
        for off, old, new in sites:
            if len(new) > len(old):
                raise ValueError('%s: replacement longer than original at 0x%x' % (key, off))
            if off + len(old) > size:
                raise ValueError('%s: site 0x%x past the end of the file' % (key, off))
            for i in range(off, off + len(old)):
                if i in taken:
                    raise ValueError('%s and %s both write 0x%x' % (key, taken[i], i))
                taken[i] = key
    print('tables OK: %d patches, %d sites' % (len(PATCHES), sum(len(v) for v in PATCHES.values())))
    return 0


def main(argv):
    args = argv[1:]
    if not args:
        gui()
        return 0
    try:
        if args[0] == '--install' and 3 <= len(args) <= 4:
            install(*args[1:])
        elif args[0] == '--patch' and len(args) == 2:
            patch(args[1])
        elif args[0] == '--restore' and len(args) == 2:
            restore(args[1])
        elif args[0] == '--selfcheck':
            return selfcheck()
        elif args[0] == '--version':
            print('%s %s' % (NAME, VERSION))
        else:
            print(__doc__.strip())
            return 2
    except Exception as exc:
        print('error: %s' % exc)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
