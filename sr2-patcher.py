#!/usr/bin/env python3
"""SEGA RALLY 2 (PC, 1999) patcher. See README.md.

    python3 sr2-patcher.py                          the window
    python3 sr2-patcher.py --install SRC DIR [LANG] install from a .cue, .iso, disc folder or data1.cab
    python3 sr2-patcher.py --patch DIR [KEYS]       patch an installed game, or only the patches KEYS names
    python3 sr2-patcher.py --rip CUE DIR             rip the play disc's music into DIR/music
    python3 sr2-patcher.py --restore DIR            put the original files back
    python3 sr2-patcher.py --selfcheck              validate the patch tables and exit
    python3 sr2-patcher.py --version

The version is the VERSION line below and nowhere else.

https://github.com/pairomaniac/sr2-patcher
"""
import hashlib
import os
import queue
import re
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
IMAGE_BASE = 0x400000                   # the exe is never relocated

# Builds. The exe's MD5 picks the row, and the row holds everything a
# patch needs that moves between builds: the fingerprints of the six
# Pentium III files and the three patched DLLs, the exe's patch sites
# (file offsets), the import slots those sites name, and the addresses
# the stubs in asm/ read (VAs). MGameD3D.dll is the same file in all
# three. Everything else in the script is written against the European
# row; the others map it.
PATCHED = (EXE, 'MUSASHI\\MGameD3D.dll', 'MUSASHI\\MGAudio.dll', 'MUSASHI\\MGSound.dll', 'Title.dll', 'Options.dll')

BUILDS = {
    'European': {
        'files': {
            EXE: (1469952, '51b3da97c3c73611d3516b65bb684cb5'),
            'AdvTelop.dll': (636928, '977dd8801a281e987c4503c9fb2f8778'),
            'Champagn.dll': (699392, 'b8dbfe718eef561f12c99223ba7b9ec4'),
            'MSelect.dll': (1137152, '1e6f713c39efb1558c79b795754d6e3a'),
            'MUSASHI\\MGameGL.dll': (601600, '3d095385ece996088381dd77a0f5f954'),
            'MUSASHI\\MGLBackground.dll': (579584, 'e7cc2a9f084a39c6f119fa1a1d769e30'),
            'MUSASHI\\MGameD3D.dll': (86016, '201a9cc68096231eebcd602a65b7af6e'),
            'MUSASHI\\MGAudio.dll': (57344, 'b05b9c8e84e8a5b051045e48ea9d6bab'),
            'MUSASHI\\MGSound.dll': (86016, 'a9698c1d866a34cd632c8d6e7e8f5fbb'),
            'Options.dll': (767488, '25c523277608e7cf2491ee8c67dd7fce'),
            'Title.dll': (637952, 'b1c6ea70b15cc41752c630ae0fb0cf0c'),
        },
        'sites': {'check': 0x267c0, 'loader': 0x7572e, 'activate': 0x25ff7,
                  'devmenu': (0x33f8, 0x340f, 0x3214, 0x3267, 0x31c0, 0x9aa20),   # Options.dll
                  'flag': 0x273e6, 'bgrow': 0x14671, 'altenter': 0x260bc,
                  'voltrace': ((0x6e6e0, 6), (0x6fa30, 9), (0x6d560, 5), (0x6e770, 9), (0x6e0e0, 6)),
                  'volume': 0x1db0, 'getvolume': 0x1e40,   # in MGAudio.dll: the CD-volume methods
                  'mix': (0x439f, 0x6980)},  # in MGSound.dll: the buffer's SetRange, the stream's SetVolume
        # `ff15` call [slot], `8b35` mov esi, [slot]; the slot is SetTextColor's.
        'textcolor': ((0x203c7, '8b35'), (0x20566, '8b35'), (0x3485f, 'ff15'), (0x34b2a, 'ff15'),
                      (0x34efc, 'ff15'), (0x35533, 'ff15'), (0x360c3, 'ff15'), (0x3a6c0, 'ff15'),
                      (0x3cef4, 'ff15'), (0x3da96, 'ff15')),
        'slots': {'SetTextColor': 0x495028, 'GetLogicalDriveStringsA': 0x495198, 'lstrcpyA': 0x4950f4,
                  'LoadLibraryA': 0x495090, 'GetProcAddress': 0x4950f0},
        'addresses': {'MENUTABLES': 0x1009c820, 'RESUME': 0x46e260, 'GAMED3D': 0x50b118, 'HANDLER': 0x41fe20, 'HWND': 0x5088ac,
                      'WIDTH': 0x4d5e1c, 'HEIGHT': 0x4d5e20, 'BITCOUNT': 0x4e68cc},
    },
    'American': {
        'files': {
            EXE: (1472000, '90d1f25110781707a888475ca37e9240'),
            'AdvTelop.dll': (636928, '977dd8801a281e987c4503c9fb2f8778'),
            'Champagn.dll': (699392, 'b8dbfe718eef561f12c99223ba7b9ec4'),
            'MSelect.dll': (1137152, '1e6f713c39efb1558c79b795754d6e3a'),
            'MUSASHI\\MGameGL.dll': (601600, '3d095385ece996088381dd77a0f5f954'),
            'MUSASHI\\MGLBackground.dll': (579584, 'e7cc2a9f084a39c6f119fa1a1d769e30'),
            'MUSASHI\\MGameD3D.dll': (86016, '201a9cc68096231eebcd602a65b7af6e'),
            'MUSASHI\\MGAudio.dll': (57344, 'b05b9c8e84e8a5b051045e48ea9d6bab'),
            'MUSASHI\\MGSound.dll': (86016, 'a9698c1d866a34cd632c8d6e7e8f5fbb'),
            'Options.dll': (767488, '25c523277608e7cf2491ee8c67dd7fce'),
            'Title.dll': (637952, 'b1c6ea70b15cc41752c630ae0fb0cf0c'),
        },
        'sites': {'check': 0x26a80, 'loader': 0x75b5e, 'activate': 0x262a7,
                  'devmenu': (0x33f8, 0x340f, 0x3214, 0x3267, 0x31c0, 0x9aa20),   # Options.dll
                  'flag': 0x276a6, 'bgrow': 0x14921, 'altenter': 0x2636c,
                  'volume': 0x1db0, 'getvolume': 0x1e40, 'mix': (0x439f, 0x6980)},
        'textcolor': ((0x20657, '8b35'), (0x207f6, '8b35'), (0x34b8f, 'ff15'), (0x34e5a, 'ff15'),
                      (0x3522c, 'ff15'), (0x35863, 'ff15'), (0x363f3, 'ff15'), (0x3aae0, 'ff15'),
                      (0x3d314, 'ff15'), (0x3ddc6, 'ff15')),
        'slots': {'SetTextColor': 0x495028, 'GetLogicalDriveStringsA': 0x49519c, 'lstrcpyA': 0x4950f4,
                  'LoadLibraryA': 0x495090, 'GetProcAddress': 0x4950f0},
        'addresses': {'MENUTABLES': 0x1009c820, 'RESUME': 0x46e480, 'GAMED3D': 0x50b218, 'HANDLER': 0x41feb0, 'HWND': 0x5089ac,
                      'WIDTH': 0x4d5f0c, 'HEIGHT': 0x4d5f10, 'BITCOUNT': 0x4e69bc},
    },
    'Australian': {
        'files': {
            EXE: (1754624, '84c95aed1b8cd8402fcff98f1687df7b'),
            'AdvTelop.dll': (636928, '3bfd541b561dfb8477a80fa14f411994'),
            'Champagn.dll': (722432, '30bc25f22c88e0d7570774504e5cedc0'),
            'MSelect.dll': (1137152, '22a4f66685e61e9db2f93eaf77fad573'),
            'MUSASHI\\MGameGL.dll': (601600, '3d095385ece996088381dd77a0f5f954'),
            'MUSASHI\\MGLBackground.dll': (579584, 'e7cc2a9f084a39c6f119fa1a1d769e30'),
            'MUSASHI\\MGameD3D.dll': (86016, '201a9cc68096231eebcd602a65b7af6e'),
            'MUSASHI\\MGAudio.dll': (57344, '35d38d59b6bd2a09eb38f0eced9ec5fb'),
            'MUSASHI\\MGSound.dll': (86016, 'a9698c1d866a34cd632c8d6e7e8f5fbb'),
            'Options.dll': (798720, '0af388650bc11dcd6df2377d3d78a535'),
            'Title.dll': (637952, 'a8017ec64efb1eba81e3e80f8afb875b'),
        },
        'sites': {'check': 0x4b420, 'loader': 0xb4dbe, 'activate': 0x4abfd,
                  'devmenu': (0x5b68, 0x5b7f, 0x5984, 0x59d7, 0x5930, 0xa0b08),   # Options.dll
                  'flag': 0x4c026, 'bgrow': 0x27e71, 'altenter': 0x4acc2, 'oscheck': 0x4b3b0,
                  'volume': 0x1d90, 'getvolume': 0x1e20, 'mixer': 0x2278,    # all in MGAudio.dll
                  'mix': (0x439f, 0x6980),
                  'sfxlevel': (0xb26cb, 0xb272e, 0xb2782), 'sfxoptions': (0xf92a, 0xf98d, 0xf9e1)},
        'textcolor': ((0x400f7, '8b35'), (0x40296, '8b35'), (0x5e28f, 'ff15'), (0x5e55a, 'ff15'),
                      (0x5e91c, 'ff15'), (0x5ef53, 'ff15'), (0x5fae3, 'ff15'), (0x66930, 'ff15'),
                      (0x69164, 'ff15'), (0x69c16, 'ff15')),
        'slots': {'SetTextColor': 0x4d402c, 'GetLogicalDriveStringsA': 0x4d4198, 'lstrcpyA': 0x4d40fc,
                  'LoadLibraryA': 0x4d4094, 'GetProcAddress': 0x4d40f8},
        'addresses': {'MENUTABLES': 0x100a2708, 'RESUME': 0x4ad790, 'GAMED3D': 0x575ae8, 'HANDLER': 0x43fb50, 'HWND': 0x57327c,
                      'WIDTH': 0x52dc1c, 'HEIGHT': 0x52dc20, 'BITCOUNT': 0x53fddc, 'SETTINGS': 0x5759ac, 'OPTSETTINGS': 0x100c19d8},
    },
}


# The DLL each import slot a row names comes from; kernel32 unless listed.
SLOT_DLL = {'SetTextColor': 'gdi32.dll'}


def build_of(digest):
    """The build whose exe has this MD5, or None."""
    for name, row in BUILDS.items():
        if row['files'][EXE][1] == digest:
            return name
    return None


# The restore-surfaces routine in MGameD3D.dll: RVA == file offset there.
RESTORE_SITE = 0x7710
RESTORE_LEN = 0x7c
RESTORE_RELOCS = 10

# Patch table: key -> (file, sites, transform). A site is (file offset,
# original, replacement); a replacement of None means the bytes are only
# verified, the transform writes them. The transform, if any, runs after
# the sites and may grow the file. Applied in this order. Addresses are
# the European build's; docs/NOTES.md has the account of each.
#
#   mixerless   MGAudio Init without a mixer CD line (Australian)
#   mix         MGSound: every buffer's dB range remapped to -43..-8, the streams on the same curve
#   sfxlevel    the effects at 100% of their ceiling, as the other builds (Australian exe)
#   sfxoptions  the same in the Australian Options.dll, which re-applies on the way out
#   win9x       the Windows 9x check returns "fine" (Australian)
#   nodisc      the disc check returns "found"; the loader takes the exe's directory
#   zdetach     DeleteAttachedSurface(0, NULL) calls removed (Proton crash)
#   altab       the resume call restores the DirectDraw surfaces first
#   managed     video-memory textures become managed
#   restoreall  the restore routine becomes RestoreAllSurfaces
#   texfmt      A1R5G5B5 first in the texture-format preference list
#   textcolor   the lobby's SetTextColor(-1) masked to RGB
#   windowed    the fullscreen flag cleared; the .bg row copy expands to 32 bits
#   anydepth    the windowed path's 16-bit desktop check skipped
#   titlebg     Title.dll's own .bg row copy, the same stub
#   borderless  the window covers its monitor, the present letterboxes
#   altenter    ALT+ENTER toggles a framed window
#   music       CD audio from music\trackNN.wav; the BGM slider sets its volume
#   devmenu     a fourth Options item, Device Settings, placed for the controller page; also grows OPTIONS.TXR
#   voltrace    diagnostic, by name only: volume calls reported on +debugstr

# The first bytes of the five volume entry points voltrace hooks.
VOLTRACE_HEADS = (bytes.fromhex('558bec83ec0c'), bytes.fromhex('558bec81ec80000000'), bytes.fromhex('568b3185f6'),
                  bytes.fromhex('558bec81ec88000000'), bytes.fromhex('558bec83ec0c'))


def devmenu_sites(offsets, tables):
    """The Options menu's sites: the cursor and icon-set constructors
    (their item counts go 3 to 4), the label loop's bounds and the
    dispatch table, all naming the three item tables at `tables`."""
    cursor, icons, labels, labelend, _dispatch, _ftab = offsets
    t = struct.pack('<I', tables)
    return ((cursor, bytes.fromhex('6a035068') + t, bytes.fromhex('6a04')),
            (icons, bytes.fromhex('6a0368') + struct.pack('<I', tables + 0xc), bytes.fromhex('6a04')),
            (labels, b'\xbf' + struct.pack('<I', tables + 0x18), None),
            (labelend, bytes.fromhex('81ff') + struct.pack('<I', tables + 0x24), None))


def patches(build):
    """The patch table for one build: key -> (file, sites, transform).
    The exe rows read their offsets and import slots from BUILDS; the DLL
    rows are the same for every build."""
    row = BUILDS[build]
    site = row['sites']

    def slot(name):
        return struct.pack('<I', row['slots'][name])


    table = {
        'nodisc': (EXE, (
            (site['check'], bytes.fromhex('8b442404'), bytes.fromhex('31c0c3')),
            (site['loader'],
             bytes.fromhex('8d4c2420516880000000ff15') + slot('GetLogicalDriveStringsA') + bytes.fromhex('8a44242084c0'),
             bytes.fromhex('8d8608010000508d460450ff15') + slot('lstrcpyA') + bytes.fromhex('e9cf000000'))), None),
        'altab': (EXE, ((site['activate'], b'\xe8', None),), 'apply_activate'),
        'zdetach': ('MUSASHI\\MGameD3D.dll', tuple(
            (off, bytes.fromhex('ff5120'), bytes.fromhex('83c40c'))
            for off in (0x2930, 0x2b31, 0x2d11, 0x37f4)), None),
        'managed': ('MUSASHI\\MGameD3D.dll', (
            (0x3e91, bytes.fromhex('c74068001000048b153c250110f7da1bd281e20038000081c200180004895068'),
             bytes.fromhex('c7406800100000c7406c10000000') + b'\x90' * 18),
            (0x3eb7, bytes.fromhex('81486800400020'), b'\x90' * 7)), 'apply_managed'),
        'restoreall': ('MUSASHI\\MGameD3D.dll', ((RESTORE_SITE, bytes.fromhex(
            'a15025011085c0741e8b0850ff516085c07414a1502501108b1050ff526c85c0a3c41f01107c55a15425011085c0741e8b0850ff516085c07414a1542501108b1050ff526c85c0a3c41f01107c2ea15c25011085c0741e8b0850ff516085c07414a15c2501108b1050ff526c85c0a3c41f01107c0733c0a3c41f0110'), None),), 'apply_restore'),
        'texfmt': ('MUSASHI\\MGameD3D.dll', ((0xf79c, bytes.fromhex('010000000200000003000000'),
                                                bytes.fromhex('030000000100000002000000')),), None),
        'textcolor': (EXE, tuple(
            (off, bytes.fromhex(op) + slot('SetTextColor'), None)
            for off, op in row['textcolor']), 'apply_textcolor'),
        'windowed': (EXE, (
            (site['flag'], b'\x01', b'\x00'),
            (site['bgrow'], bytes.fromhex('8bc88be9c1e9028bf38bfaf3a58bcd83e103f3a4'), None)), 'apply_windowed'),
        'anydepth': ('MUSASHI\\MGameD3D.dll', ((0x271e, b'\x74', b'\xeb'),), None),
        'altenter': (EXE, ((site['altenter'], b'\xe8', None),), 'apply_altenter'),
        'titlebg': ('Title.dll', ((0x8ba, bytes.fromhex('8bc88bf38be98bfac1e902f3a58bcd03d883e103f3a4'), None),),
                    'apply_titlebg'),
        'borderless': ('MUSASHI\\MGameD3D.dll', (
            (0x4d7b, bytes.fromhex('8b0df8230110'), None),
            (0x26be, bytes.fromhex('ff152cf10010'), None)), 'apply_fullwin'),
        'mix': ('MUSASHI\\MGSound.dll', ((site['mix'][0], bytes.fromhex('8b4c240c8b542410'), None),
                                        (site['mix'][1], bytes.fromhex('03d68bf285f6'), None)), 'apply_mix'),
        'music': ('MUSASHI\\MGAudio.dll', ((site['volume'], bytes.fromhex('53568b74240c'), None),
                                          (site['getvolume'], bytes.fromhex('53568b74240c'), None)), 'apply_music'),
        'devmenu': ('Options.dll', devmenu_sites(site['devmenu'], row['addresses']['MENUTABLES']), 'apply_devmenu'),
    }
    if 'oscheck' in site:
        table['win9x'] = (EXE, ((site['oscheck'], bytes.fromhex('81ec94000000'), bytes.fromhex('31c0c3')),), None)
    if 'voltrace' in site:
        table['voltrace'] = (EXE, tuple((off, VOLTRACE_HEADS[i], None) for i, (off, _n) in enumerate(site['voltrace'])),
                             'apply_voltrace')
    if 'sfxlevel' in site:
        # the slider's load in the three branches of the volume routine, the
        # exe's and the Australian Options.dll's copy; the load of the
        # announcer's setting is the middle one
        def slider_again(offsets, settings):
            return tuple((off, bytes.fromhex('8b15') + struct.pack('<I', settings) + bytes.fromhex('8b42' + ('68' if i == 1 else '64')),
                          bytes.fromhex('b809000000') + b'\x90' * 4) for i, off in enumerate(offsets))
        table['sfxlevel'] = (EXE, slider_again(site['sfxlevel'], row['addresses']['SETTINGS']), None)
        table['sfxoptions'] = ('Options.dll', slider_again(site['sfxoptions'], row['addresses']['OPTSETTINGS']), 'apply_sfxoptions')
    if 'mixer' in site:
        table['mixerless'] = ('MUSASHI\\MGAudio.dll', ((site['mixer'], bytes.fromhex('0f8530010000'), None),),
                              'apply_mixerless')
    return table


# Diagnostics: applied only by name (--patch DIR KEYS), never by default.
DIAGNOSTIC = ('voltrace',)

# Every patch any build has, in table order.
PATCH_KEYS = tuple(k for k in dict.fromkeys(k for b in BUILDS for k in patches(b)) if k not in DIAGNOSTIC)

# The mciSendCommandA sites in MGAudio.dll: 11 `call dword [slot]`, and
# one `mov esi, dword [slot]` in the open routine, which then calls esi.
MCI_CALL_SITES = 11
MCI_LOAD_SITES = 1

# The section each transform appends, one per patch so any one can be
# left out. Code that keeps no data of its own is read-only.
MUSIC_SECTION = b'.sr2m'
ACTIVATE_SECTION = b'.sr2a'
TEXTCOLOR_SECTION = b'.sr2c'
BGROW_SECTION = b'.sr2w'
TITLEROW_SECTION = b'.sr2t'
FULLWIN_SECTION = b'.sr2f'
ALTENTER_SECTION = b'.sr2k'
MIXERLESS_SECTION = b'.sr2v'
CODE_SECTION = 0x60000020               # IMAGE_SCN_CNT_CODE | MEM_EXECUTE | MEM_READ


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


# --- GENERATED by asm/build.py: BEGIN (do not edit) ---
MUSIC_BLOB = bytes.fromhex(
    'e962030000e926060000e917000000e9cb020000e927030000e8000000005b81'
    'eb1e000000c353e8edffffff89de5bc3acaa84c075fa4fc331d2b90a000000f7'
    'f10430aa88d00430aac3608dbb3c0900008db32f0d0000e8d4ffffff8b4508e8'
    '43000000c60720478b450ce837000000c60720478b4510e82b0000008b751485'
    'f6741583c6046a03c6072047ade815000000ff0c2475f1588d833c09000050ff'
    '933009000061c353b90a00000031db31d2f7f1524385c075f6580430aa4b75f9'
    'c607005bc331c031c98a0e80e93080f90977086bc00a01c846ebeec3ffb32009'
    '0000ff93180900006affffb324090000ff931c0900008b8310100000c3e817ff'
    'ffff6affffb320090000ff931c0900006a006a208d83f00f0000508d83f00d00'
    '0050ff9300090000898310100000ffb324090000ff931809000083bb34090000'
    '0074bfc783340900000000000083bb2c0900000074acb964000000e83f010000'
    '85c0749e516a04ff932c090000594975eaeb8f89c1c1e9080fb6d16bd23cc1e9'
    '080fb6f101f269d2e8030000c1e9086bc928505289c831d2b903000000f7f15a'
    '01d0599125ff000000c35389cb31d2b9e8030000f7f16bd24b5089d031d2f7f1'
    '89c158c1e11831d251b93c000000f7f159c1e21009d1c1e00809c109d989c85b'
    'c331d2b94b000000f7f189d1c1e11031d251b93c000000f7f159c1e20809d009'
    'c8c38dbb5c0b000003bbfc080000e825feffff8db3340d0000e812feffffc389'
    '83f0080000508dbbf00d00008db3390d0000e8f9fdffffe8a0feffffc783f408'
    '00000000000058e8b6ffffff8dbbf00d00008db3460d0000e8d3fdffff8db35c'
    '0b0000e8c8fdffff8db34d0d0000e8bdfdffffe864feffff85c075228dbbf00d'
    '00008db36b0d0000e8a3fdffffe84afeffffc783f40800000100000031c0c3b8'
    'ffffffff83bb2809000000743151525657bfffffffff8db3b8090000ffb39c09'
    '0000ff36ff932809000085c0750231ff83c604833eff75e489f85f5e5a59c353'
    'e834fdffff8b44240c85c0744d8378080074478b400c3d102700007605b81027'
    '00008983a0090000052b02000031d2b957040000f7f183f8097605b809000000'
    '0fb78443a409000089c2c1e21009d089839c090000e865ffffff31c05bc20c00'
    '53e8d3fcffff8b44240c85c074138b8ba0090000c740080200000089480c8948'
    '1031c05bc20c005589e5535657e8a7fcffff83bb38090000007405e8cafcffff'
    '8b450c3d03080000753e83bbec080000000f848d0200008b4d1081e100300000'
    '81f9003000000f85780200008b5514817a08040200000f8568020000c74204ce'
    'fa0000e953020000817d08cefa00000f854f0200003d0408000074373d060800'
    '00747a3d070800000f84030100003d0808000074383d0908000074413d550800'
    '00744a3d140800000f8459010000e9080200008db3390d0000e8ec010000c783'
    'f408000000000000e9ee0100008db3b20d0000e8d2010000e9de0100008db3be'
    '0d0000e8c2010000e9ce0100008db3cb0d0000e8b2010000e9be0100008b8bf8'
    '0800008b83f0080000f7451004000000740b8b55148b4204e8f6fcffffc783f8'
    '0800000000000085c0745c3b83ec080000775483bc83cc09000000744a51e87c'
    'fdffff5985c00f85710100008dbbf00d00008db38f0d0000e873fbffff85c974'
    '128db39b0d0000e864fbffff89c8e8d4fbffffc7833409000001000000e8fafb'
    'ffffe936010000b812010000e92c010000f74510080000000f841d0100008b55'
    '148b4204e86afcffff898bf808000083bbf40800000074443b83f00800007409'
    '403b83f008000075338dbbf00d00008db3a20d0000e8f6faffff89c8e866fbff'
    'ffe896fbffff8dbbf00d00008db38f0d0000e8d9faffffe977ffffff8983f008'
    '0000e9b40000008b5514c7420400000000f74510000100000f849d0000008b42'
    '0883f803740f83f801741583f8027435e9860000008b83ec080000894204eb7b'
    'f745101000000074728b420c83f863776a8b8483cc090000e824fcffff8b5514'
    '894204eb568b8bf008000031c083bbf40800000074278dbbf00d00008db3d90d'
    '0000e849faffffe8f0faffff8db3f00f0000e8cefaffff8b8bf0080000e8a8fb'
    'ffff8b5514894204eb118dbbf00d0000e81bfaffffe8c2faffffc331c05f5e5b'
    '5dc210008b83e2e2e2e25f5e5b5dffe0837c2408010f859d02000060e8d8f9ff'
    'ff83bbe8080000000f8589020000c783e8080000010000008d836c0c000050ff'
    '93e3e3e3e385c00f846a02000089c68d8b760c00005156ff93e4e4e4e485c00f'
    '84520200008983000900008d8b850c00005156ff93e4e4e4e48983280900008d'
    '83960c000050ff93e3e3e3e385c00f842302000089c68d8ba30c00005156ff93'
    'e4e4e4e48983040900008d8baf0c00005156ff93e4e4e4e48983080900008d8b'
    'bb0c00005156ff93e4e4e4e489830c0900008d8bc70c00005156ff93e4e4e4e4'
    '8983100900008d8bd40c00005156ff93e4e4e4e48983140900008d8be10c0000'
    '5156ff93e4e4e4e48983180900008d8bea0c00005156ff93e4e4e4e489831c09'
    '00008d8bfe0c00005156ff93e4e4e4e489832c0900008d8b040d00005156ff93'
    'e4e4e4e48983300900008db304090000b907000000833e000f845901000083c6'
    '044975f168040100008d835c0b0000506a00ff93e5e5e5e585c00f8437010000'
    '8dbb5c0b000001c74f803f5c75fa47578db3230d0000e875f8ffff6a00688000'
    '00006a036a006a0168000000808d835c0b000050ff930409000083f8ff741a50'
    'ff930c09000083bb3009000000740ac78338090000010000005f8db3170d0000'
    'e82bf8ffff29df81ef5c0b000089bbfc080000bd0200000089e8e8e3f9ffff6a'
    '0068800000006a036a006a0168000000808d835c0b000050ff930409000083f8'
    'ff742f89c76a0057ff93080900005057ff930c0900005883e82c761631d2b930'
    '090000f7f18984abcc09000089abec0800004583fd6376a06a006a006a006a00'
    'ff93140900008983200900006a006a006a006a00ff9314090000898324090000'
    '6a006a006a008d83fd000000506a006a00ff931009000085c0741283bb200900'
    '0000740983bb2409000000750ac783ec080000000000006153e83bf7ffff8d83'
    'e1e1e1e15bffe090000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '00000000000000000000000000000000000000000000000000000000ffffffff'
    '102700000000310a400fd116232214336d4c597218abffff0000000000ff0000'
    '01ff000000c00000ffffffff0000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '00000000000000000000000077696e6d6d2e646c6c006d636953656e64537472'
    '696e674100776176654f7574536574566f6c756d65006b65726e656c33322e64'
    '6c6c0043726561746546696c65410047657446696c6553697a6500436c6f7365'
    '48616e646c6500437265617465546872656164004372656174654576656e7441'
    '005365744576656e740057616974466f7253696e676c654f626a65637400536c'
    '656570004f75747075744465627567537472696e6741006d757369635c747261'
    '636b006d757369635c74726163650073723220002e77617600636c6f73652073'
    '723262676d006f70656e2022002220747970652077617665617564696f20616c'
    '6961732073723262676d007365742073723262676d2074696d6520666f726d61'
    '74206d696c6c697365636f6e647300706c61792073723262676d002066726f6d'
    '20007365656b2073723262676d20746f200073746f702073723262676d007061'
    '7573652073723262676d00726573756d652073723262676d0073746174757320'
    '73723262676d20706f736974696f6e0000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000'
)
ACTIVATE_BLOB = bytes.fromhex(
    '51a1eaeaeaea85c074068b1050ff52405968ebebebebc3'
)
RESTORE_BLOB = bytes.fromhex(
    'e800000000598b8137ae000085c074118b105150ff5264598981afa80000c204'
    '0031c08981afa80000c20400'
)
TEXTCOLOR_BLOB = bytes.fromhex(
    '81642408ffffff00ff25f2f2f2f2'
)
BGROW_BLOB = bytes.fromhex(
    '833df1f1f1f120741589c189cdc1e90289de89d7f3a589e983e103f3a4c35053'
    '5289c1d1e9744e89de89d70fb70683c60289c389c281e300f8000081e2e00700'
    '0083e01f89ddc1e308c1e50381e50000070009eb89d5c1e205d1ed81e5000300'
    '0009ea89c5c1e003c1ed0209e809d809d0ab4975b65a5b58c3'
)
TITLEROW_BLOB = bytes.fromhex(
    '837c247020741789c189cdc1e90289de89d7f3a589e983e103f3a401c3c35053'
    '5289c1d1e9744e89de89d70fb70683c60289c389c281e300f8000081e2e00700'
    '0083e01f89ddc1e308c1e50381e50000070009eb89d5c1e205d1ed81e5000300'
    '0009ea89c5c1e003c1ed0209e809d809d0ab4975b65a5b5801c3c3'
)
FULLWIN_BLOB = bytes.fromhex(
    'e91a000000e9a5010000e8000000005b81eb0f00000089de81ebe7e7e7e7c355'
    '89e581ecb0000000535657e8daffffff8d45f050ffb3f8230100ff9340f10000'
    '8d45f050ffb3f8230100ff933cf100008d45f850ffb3f8230100ff933cf10000'
    '8b75f82b75f08b7dfc2b7df48b8b182401002b8b10240100894dc08b931c2401'
    '002b93142401008955bc89f00fafc289f90faf4dc039c8720f897db489c831d2'
    'f775bc8945b8eb0b8975b831d2f775c08945b489f02b45b8d1e80345f08945e0'
    '0345b88945e889f82b45b4d1e80345f48945e40345b48945ec8dbd50ffffff31'
    'c0b919000000f3abc78550ffffff640000008b45f08945d08b45f48945d48b45'
    'f88945d88b45e48945dce86f0000008b45ec8945d48b45fc8945dce85e000000'
    '8b45e48945d48b45e08945d88b45ec8945dce8470000008b45e88945d08b45f8'
    '8945d8e8360000008b83502501008b086a0068000000018d931024010052ffb3'
    '542501008d55e05250ff51148983c41f01005f5e5b89ec5d83c410c204008b45'
    'd83b45d07e288b45dc3b45d47e208b83502501008b088d9550ffffff52680004'
    '00016a006a008d55d05250ff5114c35589e583ec40535657e84dfeffff6af0ff'
    '7508ff9338f10000a9000000800f84b50000008d869102000050ff9314f10000'
    '85c00f848800000089c78d869c0200005057ff93acf0000085c074748d4dd051'
    'ffd085c0746a8d86a90200005057ff93acf0000085c074586a02ff75d4ff75d0'
    'ffd085c0744a8945cc8d86ba0200005057ff93acf0000085c07435c745d82800'
    '00008d4dd851ff75ccffd085c074216a018b45e82b45e0508b45e42b45dc50ff'
    '75e0ff75dcff7508ff932cf10000eb18ff751cff7518ff7514ff7510ff750cff'
    '7508ff932cf100005f5e5b89ec5dc218007573657233322e646c6c0047657443'
    '7572736f72506f73004d6f6e69746f7246726f6d506f696e74004765744d6f6e'
    '69746f72496e666f4100'
)
ALTENTER_BLOB = bytes.fromhex(
    '8b4424083d040100007521837c240c0d751a8b442410a900000020740fa90000'
    '00407505e81600000031c0c368ececececc3e8000000005b81eb37000000c353'
    '56575589e583ec40e8e5ffffff83bbec01000000753f8d837a01000050ff15e3'
    'e3e3e385c00f840801000089c631ff8b84bbd601000001d85056ff15e4e4e4e4'
    '85c00f84eb0000008984bbec0100004783ff0572da8b3dedededed6a0257ff93'
    'f801000085c00f84c7000000c745d8280000008d4dd85150ff93fc01000085c0'
    '0f84ad00000080b3ea01000001f683ea010000017470680000cf106af057ff93'
    'ec01000031c08945c08945c4a1eeeeeeee8945c8a1efefefef8945cc6a006a00'
    '680000cf108d45c050ff93f40100008b75c82b75c08b55cc2b55c46a6452568b'
    '45e82b45e029d0d1f80345e0508b45e42b45dc29f0d1f80345dc506a0057ff93'
    'f0010000eb2d68000000906af057ff93ec0100006a648b45e82b45e0508b45e4'
    '2b45dc50ff75e0ff75dc6a0057ff93f001000089ec5d5f5e5bc3757365723332'
    '2e646c6c0053657457696e646f774c6f6e67410053657457696e646f77506f73'
    '0041646a75737457696e646f77526563744578004d6f6e69746f7246726f6d57'
    '696e646f77004765744d6f6e69746f72496e666f41008501000094010000a101'
    '0000b4010000c601000000900000000000000000000000000000000000000000'
)
MIX_BLOB = bytes.fromhex(
    '8b4c24108b542414505289c8e80c00000089c158e80400000089c258c369c0ac'
    '0d000051b9a00f000099f7f95905e0fcffffc3518d832b02000031d2b9570400'
    '00f7f15983f8097605b80900000085c0740e69d05e01000081c25af1ffffeb05'
    'baf0d8ffff89d685f6c3'
)
VOLTRACE_BLOB = bytes.fromhex(
    'e9bb000000e9c9000000e9da000000e9e7000000e9f80000006083ec5089e7e8'
    '000000005b81eb240000008db324010000e8820000008b4424740430aab020aa'
    '8b442468e84d0000008b44247ce8440000008b842480000000e8380000008b84'
    '2484000000e82c000000c607008d832a01000050ff15e3e3e3e38d8b37010000'
    '5150ff15e4e4e4e485c0740354ffd083c45061c20400b908000000c1c00488c2'
    '80e20f80c23080fa39760380c207881747e2e8c6072047c3acaa84c075fa4fc3'
    '6a01e852ffffff5589e583ec0cff25e1e7e7e76a02e83fffffff5589e581ec80'
    '000000ff25e2e7e7e76a03e829ffffff568b3185f6ff25e3e7e7e76a04e817ff'
    'ffff5589e581ec88000000ff25e4e7e7e76a05e801ffffff5589e583ec0cff25'
    'e5e7e7e77372322076006b65726e656c33322e646c6c004f7574707574446562'
    '7567537472696e674100'
)
MUSIC_MAGICS = {
    'MAGIC_ORIGENTRY': 0xE1E1E1E1,
    'MAGIC_IATMCI': 0xE2E2E2E2,
    'MAGIC_LOADLIB': 0xE3E3E3E3,
    'MAGIC_GETPROC': 0xE4E4E4E4,
    'MAGIC_GETMODFN': 0xE5E5E5E5,
}
EXE_MAGICS = {
    'GAMED3D': 0xEAEAEAEA,
    'RESUME': 0xEBEBEBEB,
    'HANDLER': 0xECECECEC,
    'LOADLIB': 0xE3E3E3E3,
    'GETPROC': 0xE4E4E4E4,
    'HWND': 0xEDEDEDED,
    'WIDTH': 0xEEEEEEEE,
    'HEIGHT': 0xEFEFEFEF,
    'BITCOUNT': 0xF1F1F1F1,
    'SETTEXTCOLOR': 0xF2F2F2F2,
}
FULLWIN_MAGIC = 0xE7E7E7E7
# --- GENERATED by asm/build.py: END ---


# Disc image
# The install disc is read directly, no mounting: a cue sheet with its bin,
# a plain .iso, or the raw bin on its own. Only the data track matters.

LOGICAL = 2048                  # user bytes in a sector, whatever its form
PRIMARY_VD = 16                 # where the descriptors start, by the standard

# Sector layouts, walked in order; the one whose sector 16 holds an ISO9660
# descriptor wins, so a cue sheet naming the wrong mode still works.
SECTOR_FORMS = (
    ('MODE1/2352', 2352, 16),
    ('MODE2/2352', 2352, 24),
    ('MODE1/2048', 2048, 0),
    ('MODE2/2336', 2336, 8),
)

_MSF = re.compile(r'^(\d+):(\d+):(\d+)$')


class DiscError(Exception):
    """The image cannot be used. The message is shown as it is."""


def _cue_file(base, line):
    """Where a FILE line points: the bin sits beside the cue whatever path
    the sheet carries, so the name is what matters."""
    if '"' in line:
        name = line.split('"')[1]
    else:
        parts = line.split()
        name = ' '.join(parts[1:-1]) if len(parts) > 2 else parts[-1]
    plain = name.replace('\\', '/').rstrip('/').rsplit('/', 1)[-1]
    for candidate in (name, plain):
        here = os.path.join(base, candidate)
        if os.path.exists(here):
            return here
    for entry in os.listdir(base):
        if entry.lower() == plain.lower():
            return os.path.join(base, entry)
    raise DiscError('%s, named by the cue sheet, is not beside it.' % plain)


def _msf_to_sectors(text):
    stamp = _MSF.match(text)
    if not stamp:
        raise DiscError('not a cue sheet timestamp: %r' % text)
    m, s, f = (int(x) for x in stamp.groups())
    return (m * 60 + s) * 75 + f


def parse_cue(path):
    """Every track in a cue sheet: 'no', 'mode', 'bin', 'start' (INDEX 01)
    and 'pregap' (its own INDEX 00, or None)."""
    base = os.path.dirname(os.path.abspath(path))
    curbin, tracks, cur = None, [], None
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as fh:
        for line in fh:
            line = line.strip()
            up = line.upper()
            if up.startswith('FILE'):
                curbin = _cue_file(base, line)
            elif up.startswith('TRACK'):
                parts = line.split()
                cur = {'no': int(parts[1]), 'mode': parts[2].upper(), 'bin': curbin,
                       'start': 0, 'pregap': None}
                tracks.append(cur)
            elif up.startswith('INDEX') and cur is not None:
                parts = line.split()
                if parts[1] == '00':
                    cur['pregap'] = _msf_to_sectors(parts[2])
                elif parts[1] == '01':
                    cur['start'] = _msf_to_sectors(parts[2])
    if not tracks:
        raise DiscError('No TRACK entries in %s.' % os.path.basename(path))
    return tracks


def data_track(path):
    """(bin path, first sector) of the first data track."""
    data = [t for t in parse_cue(path) if 'AUDIO' not in t['mode'] and t['bin']]
    if not data:
        raise DiscError('No data track in %s.' % os.path.basename(path))
    return data[0]['bin'], data[0]['start']


# Ripping: the play disc's audio tracks into WAV files the music patch plays.

RAW = 2352                      # bytes per CD-DA sector
RATE = 44100
WAV_HDR = 44


def _wav_header(pcm_bytes):
    """44 bytes: PCM, stereo, 44100, 16-bit. The hook divides by these to
    get track lengths, so they are not free to change."""
    return (b'RIFF' + struct.pack('<I', 36 + pcm_bytes) + b'WAVEfmt ' +
            struct.pack('<IHHIIHH', 16, 1, 2, RATE, RATE * 4, 4, 16) +
            b'data' + struct.pack('<I', pcm_bytes))


class WavWriter:
    """Writes a WAV whose length is not known until the end; a failed rip
    removes the partial file, since a short file with a valid header would
    pass for a good one."""

    def __init__(self, path):
        self.path = path
        self.f = open(path, 'wb')
        self.f.write(b'\0' * WAV_HDR)
        self.n = 0

    def write(self, data):
        self.f.write(data)
        self.n += len(data)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_rest):
        if exc_type is None:
            self.f.seek(0)
            self.f.write(_wav_header(self.n))
            self.f.close()
        else:
            self.f.close()
            try:
                os.remove(self.path)
            except OSError:
                pass


def audio_spans(tracks):
    """(track, first sector, last sector) per audio track. A track ends at
    the next track's pregap when the two share a bin file, else at the end
    of the file."""
    for i, t in enumerate(tracks):
        if 'AUDIO' not in t['mode'] or not t['bin']:
            continue
        nxt = tracks[i + 1] if i + 1 < len(tracks) else None
        if nxt is None or nxt['bin'] != t['bin']:
            end = os.path.getsize(t['bin']) // RAW
        else:
            end = nxt['pregap'] if nxt['pregap'] is not None else nxt['start']
        if end > t['start']:
            yield t, t['start'], end


def rip(cue, dest, log=print):
    """Every audio track of the play disc into DEST\\music\\trackNN.wav."""
    if not cue:
        raise DiscError('No play disc given.')
    tracks = parse_cue(cue)
    spans = list(audio_spans(tracks))
    if not spans:
        raise DiscError('No audio tracks in %s: is this the play disc?' % os.path.basename(cue))
    outdir = os.path.join(dest, 'music')
    os.makedirs(outdir, exist_ok=True)
    for t, start, end in spans:
        out = os.path.join(outdir, 'track%02d.wav' % t['no'])
        with open(t['bin'], 'rb') as src, WavWriter(out) as dst:
            src.seek(start * RAW)
            left = (end - start) * RAW
            while left > 0:
                chunk = src.read(min(left, RAW * 512))
                if not chunk:
                    raise DiscError('%s ends early.' % os.path.basename(t['bin']))
                dst.write(chunk)
                left -= len(chunk)
        log('rip: track %02d, %d:%02d' % (t['no'], (end - start) // 75 // 60, (end - start) // 75 % 60))
    log('rip: %d tracks in %s' % (len(spans), outdir))


class DataTrack:
    """2048-byte logical sectors out of an image's data track."""

    def __init__(self, path, start=0):
        self.start = start
        self.fh = open(path, 'rb')
        size = os.path.getsize(path)
        for name, stride, offset in SECTOR_FORMS:
            at = (start + PRIMARY_VD) * stride + offset
            if at + 6 <= size:
                self.fh.seek(at)
                if self.fh.read(6)[1:6] == b'CD001':
                    self.form, self.stride, self.offset = name, stride, offset
                    return
        self.fh.close()
        raise DiscError('No filesystem in %s. The image is damaged, or the '
                        'cue sheet names the wrong file for track 1.'
                        % os.path.basename(path))

    def close(self):
        self.fh.close()

    def sector(self, lba):
        self.fh.seek((self.start + lba) * self.stride + self.offset)
        data = self.fh.read(LOGICAL)
        if len(data) != LOGICAL:
            raise DiscError('The image ends early: truncated, or a bin file is missing.')
        return data

    def read(self, lba, length):
        out = bytearray()
        while len(out) < length:
            out += self.sector(lba + len(out) // LOGICAL)
        return bytes(out[:length])


def iso_entries(track, lba, size):
    """{lowercased name: (is_dir, lba, size)} for one directory."""
    out, data, at = {}, track.read(lba, size), 0
    while at < len(data):
        length = data[at]
        if length == 0:                     # records never straddle a sector
            at = (at // LOGICAL + 1) * LOGICAL
            continue
        rec = data[at:at + length]
        at += length
        if len(rec) < 34:
            continue
        flags, name_len = rec[25], rec[32]
        raw = rec[33:33 + name_len]
        if name_len == 1 and raw in (b'\x00', b'\x01'):
            continue
        if flags & 0x80:
            raise DiscError('This image uses multi-extent files, which the patcher cannot read.')
        name = raw.decode('latin-1').split(';')[0].rstrip('.')
        out[name.lower()] = (bool(flags & 0x02),
                             int.from_bytes(rec[2:6], 'little'),
                             int.from_bytes(rec[10:14], 'little'))
    return out


def iso_root(track):
    pvd = track.sector(PRIMARY_VD)
    if pvd[0] != 1:
        raise DiscError('Sector %d of this image is not a volume descriptor.' % PRIMARY_VD)
    root = pvd[156:190]
    return iso_entries(track, int.from_bytes(root[2:6], 'little'),
                       int.from_bytes(root[10:14], 'little'))


class DiscFile:
    """One file on the disc, as a read-only file object: what Cabinet needs."""

    def __init__(self, track, lba, size):
        self.track, self.lba, self.size, self.pos = track, lba, size, 0

    def seek(self, pos, whence=0):
        self.pos = pos if whence == 0 else self.pos + pos if whence == 1 else self.size + pos
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n < 0 or self.pos + n > self.size:
            n = self.size - self.pos
        if n <= 0:
            return b''
        first, skip = divmod(self.pos, LOGICAL)
        data = self.track.read(self.lba + first, skip + n)[skip:]
        self.pos += n
        return data

    def close(self):
        pass


def open_source(src):
    """A file object on data1.cab and a closer, from whatever the user
    gave: a .cue, an .iso or .bin, a mounted disc folder, or the cab."""
    if not src:
        raise DiscError('No install disc given.')
    low = src.lower()
    if os.path.isdir(src):
        for name in os.listdir(src):
            if name.lower() == CAB:
                fh = open(os.path.join(src, name), 'rb')
                return fh, fh.close
        raise DiscError('No %s in %s.' % (CAB, src))
    if low.endswith('.cab'):
        fh = open(src, 'rb')
        return fh, fh.close
    if low.endswith('.cue'):
        path, start = data_track(src)
    else:
        path, start = src, 0
    track = DataTrack(path, start)
    entry = iso_root(track).get(CAB)
    if not entry or entry[0]:
        track.close()
        raise DiscError('No %s in the root of this image, so it is not the install disc.' % CAB)
    return DiscFile(track, entry[1], entry[2]), track.close


# InstallShield 5 cabinet

IS_SIGNATURE = 0x28635349
IS_COMPRESSED = 0x04
IS_INVALID = 0x08
IS_SPLIT = 0x01
IS_UNCHUNKED = 0x01000004
IS_GROUP_SLOTS = 71


class Entry:
    __slots__ = ('name', 'directory', 'flags', 'size', 'compressed', 'offset', 'group')

    @property
    def path(self):
        return self.directory + '\\' + self.name if self.directory else self.name


class Cabinet:
    """data1.cab: the file table and the bytes of any one file. Takes a
    file object; close() is the caller's."""

    def __init__(self, fh):
        self.fh = fh
        sig, self.version, _vol, desc_off, desc_size = struct.unpack('<5I', self.fh.read(0x14))
        if sig != IS_SIGNATURE:
            raise ValueError('not an InstallShield cabinet')
        # 0x01000004 (the European disc) stores a compressed file as one
        # deflate stream; the later engine (0x01005100 on the other two)
        # as chunks, each a u16 length and a stream of its own.
        self.chunked = self.version != IS_UNCHUNKED
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

    def read(self, entry):
        if entry.flags & IS_SPLIT:
            raise ValueError('%s spans volumes' % entry.path)
        self.fh.seek(entry.offset)
        if entry.flags & IS_COMPRESSED and self.chunked:
            raw, at, out = self.fh.read(entry.compressed), 0, []
            while at + 2 <= len(raw) and sum(map(len, out)) < entry.size:
                n = struct.unpack_from('<H', raw, at)[0]
                out.append(zlib.decompressobj(-15).decompress(raw[at + 2:at + 2 + n]))
                at += 2 + n
            data = b''.join(out)
        elif entry.flags & IS_COMPRESSED:
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
    fh, close = open_source(src)
    try:
        cab = Cabinet(fh)
        groups = install_groups(lang)
        missing = [g for g in groups if g not in cab.groups]
        if missing:
            raise ValueError('this disc has no %s' % ', '.join(missing))
        total = sum(e.size for g in groups for e in cab.groups[g])
        log('install: %d MB to %s' % (total // 1000000, dest))
        for g in groups:
            for e in cab.groups[g]:
                out = os.path.join(dest, *e.path.split('\\'))
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, 'wb') as dst:
                    dst.write(cab.read(e))
            log('install: %s, %d files' % (g, len(cab.groups[g])))
    finally:
        close()
    write_manifests(dest)
    log('install: manifests written')
    patch(dest, log)


# The music patch: a section appended to MGAudio.dll

def _align(n, a):
    return (n + a - 1) // a * a


def append_section(buf, name, data, chars=CODE_SECTION | 0x80000040):
    """Append a section to a PE image in buf. Returns (buffer, section RVA)."""
    pe_off = struct.unpack_from('<I', buf, 0x3c)[0]
    nsec = struct.unpack_from('<H', buf, pe_off + 6)[0]
    opt = pe_off + 24
    opt_size = struct.unpack_from('<H', buf, pe_off + 20)[0]
    sect_align = struct.unpack_from('<I', buf, opt + 32)[0]
    file_align = struct.unpack_from('<I', buf, opt + 36)[0]
    headers = struct.unpack_from('<I', buf, opt + 60)[0]
    table = opt + opt_size
    if table + (nsec + 1) * 40 > headers:
        raise ValueError('no room in the section table')
    last_vsize, last_va = struct.unpack_from('<II', buf, table + (nsec - 1) * 40 + 8)
    rva = _align(last_va + last_vsize, sect_align)
    raw = _align(len(buf), file_align)
    raw_size = _align(len(data), file_align)
    out = bytearray(buf) + b'\0' * (raw - len(buf)) + data + b'\0' * (raw_size - len(data))
    struct.pack_into('<8sIIIIIIHHI', out, table + nsec * 40, name.ljust(8, b'\0'),
                     len(data), rva, raw_size, raw, 0, 0, 0, 0, chars)
    struct.pack_into('<H', out, pe_off + 6, nsec + 1)
    struct.pack_into('<I', out, opt + 56, _align(rva + len(data), sect_align))
    return out, rva


def _off_to_rva(buf, off):
    pe_off = struct.unpack_from('<I', buf, 0x3c)[0]
    nsec = struct.unpack_from('<H', buf, pe_off + 6)[0]
    table = pe_off + 24 + struct.unpack_from('<H', buf, pe_off + 20)[0]
    for i in range(nsec):
        va, rsize, raw = struct.unpack_from('<III', buf, table + i * 40 + 12)
        if raw <= off < raw + rsize:
            return va + off - raw
    raise ValueError('offset 0x%x is in no section' % off)


def _rva_to_off(buf, rva):
    pe_off = struct.unpack_from('<I', buf, 0x3c)[0]
    nsec = struct.unpack_from('<H', buf, pe_off + 6)[0]
    table = pe_off + 24 + struct.unpack_from('<H', buf, pe_off + 20)[0]
    for i in range(nsec):
        vsize, va, rsize, roff = struct.unpack_from('<IIII', buf, table + i * 40 + 8)
        if va <= rva < va + max(vsize, rsize):
            return roff + rva - va
    raise ValueError('rva 0x%x is in no section' % rva)


def _iat_slot(buf, dll, func):
    """RVA of the import slot for dll!func."""
    pe_off = struct.unpack_from('<I', buf, 0x3c)[0]
    opt = pe_off + 24
    imp_rva = struct.unpack_from('<I', buf, opt + 104)[0]
    off = _rva_to_off(buf, imp_rva)
    while True:
        oft, _t, _f, name_rva, ft = struct.unpack_from('<IIIII', buf, off)
        if not ft:
            break
        name = buf[_rva_to_off(buf, name_rva):].split(b'\0')[0].decode('latin-1').lower()
        if name == dll:
            i = 0
            while True:
                thunk = struct.unpack_from('<I', buf, _rva_to_off(buf, (oft or ft) + i * 4))[0]
                if not thunk:
                    break
                if not thunk & 0x80000000:
                    fname = buf[_rva_to_off(buf, thunk) + 2:].split(b'\0')[0].decode('latin-1')
                    if fname == func:
                        return ft + i * 4
                i += 1
        off += 20
    raise ValueError('%s!%s is not imported' % (dll, func))


def _drop_relocations(buf, rvas):
    """Turn the HIGHLOW relocation entries for the given RVAs into padding
    (type ABSOLUTE), so the loader no longer fixes up bytes that are now
    relative. Returns how many it dropped."""
    pe_off = struct.unpack_from('<I', buf, 0x3c)[0]
    opt = pe_off + 24
    rel_rva, rel_size = struct.unpack_from('<II', buf, opt + 136)
    if not rel_size:
        return 0
    off = _rva_to_off(buf, rel_rva)
    end = off + rel_size
    dropped = 0
    while off + 8 <= end:
        page, size = struct.unpack_from('<II', buf, off)
        if not size:
            break
        for i in range(8, size, 2):
            entry = struct.unpack_from('<H', buf, off + i)[0]
            if entry >> 12 == 3 and page + (entry & 0xfff) in rvas:
                struct.pack_into('<H', buf, off + i, 0)
                dropped += 1
        off += size
    return dropped


def apply_music(buf, build):
    """The music patch. Returns the grown DLL image."""
    pe_off = struct.unpack_from('<I', buf, 0x3c)[0]
    opt = pe_off + 24
    entry = struct.unpack_from('<I', buf, opt + 16)[0]
    base = struct.unpack_from('<I', buf, opt + 28)[0]
    slot = _iat_slot(buf, 'winmm.dll', 'mciSendCommandA')
    values = {
        'MAGIC_IATMCI': slot,
        'MAGIC_LOADLIB': _iat_slot(buf, 'kernel32.dll', 'LoadLibraryA'),
        'MAGIC_GETPROC': _iat_slot(buf, 'kernel32.dll', 'GetProcAddress'),
        'MAGIC_GETMODFN': _iat_slot(buf, 'kernel32.dll', 'GetModuleFileNameA'),
        'MAGIC_ORIGENTRY': entry,
    }
    # The sites, before anything moves: `FF 15 <slot VA>` calls and the
    # `8B 35 <slot VA>` load. Both are six bytes and become `E8 rel32 90`.
    raw = bytes(buf)
    slot_va = struct.pack('<I', base + slot)
    sites = [m.start() for m in re.finditer(re.escape(b'\xff\x15' + slot_va), raw)]
    loads = [m.start() for m in re.finditer(re.escape(b'\x8b\x35' + slot_va), raw)]
    if len(sites) != MCI_CALL_SITES or len(loads) != MCI_LOAD_SITES:
        raise ValueError('expected %d calls and %d loads of mciSendCommandA, found %d and %d'
                         % (MCI_CALL_SITES, MCI_LOAD_SITES, len(sites), len(loads)))
    text_off = _rva_to_off(buf, 0x1000)                 # .text is the first section
    site_rvas = {0x1000 + off - text_off for off in sites + loads}
    if _drop_relocations(buf, {r + 2 for r in site_rvas}) != len(site_rvas):
        raise ValueError('relocation entries for the sites not all found')
    out, rva = append_section(buf, MUSIC_SECTION, MUSIC_BLOB)
    blob = bytearray(MUSIC_BLOB)
    for name, magic in MUSIC_MAGICS.items():
        pattern = struct.pack('<I', magic)
        if pattern not in blob:
            raise ValueError('%s is missing from the blob' % name)
        blob = blob.replace(pattern, struct.pack('<i', values[name] - rva))
    start = _rva_to_off(out, rva)
    out[start:start + len(blob)] = blob
    for off, thunk in [(o, 0) for o in sites] + [(o, 10) for o in loads]:
        site_rva = 0x1000 + off - text_off
        rel = rva + thunk - (site_rva + 5)
        out[off:off + 6] = b'\xe8' + struct.pack('<i', rel) + b'\x90'
    _branch(out, BUILDS[build]['sites']['volume'], rva + 15, 6, op=b'\xe9')
    _branch(out, BUILDS[build]['sites']['getvolume'], rva + 20, 6, op=b'\xe9')
    struct.pack_into('<I', out, opt + 16, rva + 5)
    return out


# The managed-textures patch: sites, plus one relocation entry to drop

def apply_managed(buf, _build=None):
    """The sites are written by patch(); this drops the relocation entry of
    the absolute address they removed."""
    if _drop_relocations(buf, {0x3e9a}) != 1:
        raise ValueError('relocation entry of the hardware flag not found')
    return buf


# The restore-all patch: MGameD3D's routine rewritten in place

def apply_restore(buf, _build=None):
    """Returns the DLL with the routine replaced."""
    if len(RESTORE_BLOB) > RESTORE_LEN:
        raise ValueError('restore blob does not fit')
    rvas = set(range(RESTORE_SITE, RESTORE_SITE + RESTORE_LEN))
    if _drop_relocations(buf, rvas) != RESTORE_RELOCS:
        raise ValueError('relocation entries of the restore routine not all found')
    buf[RESTORE_SITE:RESTORE_SITE + RESTORE_LEN] = RESTORE_BLOB.ljust(RESTORE_LEN, b'\xcc')
    return buf


# Patches that append a blob and point sites at it

def _branch(buf, off, target_rva, length=5, op=b'\xe8'):
    """A near call (or jump, op e9) at file offset off to target_rva, padded
    with nops to the length of what it replaces. The site's own RVA comes
    from the section table, since .text need not start at its file offset."""
    site_rva = 0x1000 + off - _rva_to_off(buf, 0x1000)
    buf[off:off + length] = (op + struct.pack('<i', target_rva - (site_rva + 5))).ljust(length, b'\x90')


BGROW_LEN = 20                          # exe, the .bg row copy
TITLEROW_SITE, TITLEROW_LEN = 0x8ba, 22  # Title.dll, the row copy at 0x100014ba
PRESENT_SITE = 0x4d7b                   # MGameD3D, the windowed present's first instruction
SIZE_SITE = 0x26be                      # MGameD3D, `call [__imp__MoveWindow]` in the windowed init
# HIGHLOW entries inside the replaced present (absolute addresses, now dead
# code) and the one under the MoveWindow call.
FULLWIN_RELOCS = {0x4d7d, 0x4d8a, 0x4d8f, 0x4d95, 0x4da3, 0x4db1, 0x4db6, 0x4dc4, 0x4dd3, 0x26c0}


def exe_blob(blob, build):
    """A stub with the build's addresses in place of the placeholders."""
    row = BUILDS[build]
    values = dict(row['addresses'], LOADLIB=row['slots']['LoadLibraryA'], GETPROC=row['slots']['GetProcAddress'],
                  SETTEXTCOLOR=row['slots']['SetTextColor'])
    out = bytes(blob)
    for name, magic in EXE_MAGICS.items():
        out = out.replace(struct.pack('<I', magic), struct.pack('<I', values[name]))
    return out


def _call_target(buf, off):
    """The VA a `call rel32` at a file offset in .text goes to."""
    rva = 0x1000 + off - _rva_to_off(buf, 0x1000) + 5 + struct.unpack_from('<i', buf, off + 1)[0]
    return rva + struct.unpack_from('<I', buf, struct.unpack_from('<I', buf, 0x3c)[0] + 24 + 28)[0]


def _check_call(buf, off, target, what):
    if _call_target(buf, off) != target:
        raise ValueError('the call at 0x%x does not go to %s' % (off, what))


def apply_activate(buf, build):
    """The alt-tab stub in the exe, called from the WM_ACTIVATEAPP case."""
    row = BUILDS[build]
    _check_call(buf, row['sites']['activate'], row['addresses']['RESUME'], 'the resume routine')
    out, rva = append_section(buf, ACTIVATE_SECTION, exe_blob(ACTIVATE_BLOB, build), chars=CODE_SECTION)
    _branch(out, row['sites']['activate'], rva)
    return out


def apply_textcolor(buf, build):
    """The SetTextColor stub in the exe; the eight calls and two loads of
    the import slot become a call to it and a load of its address."""
    out, rva = append_section(buf, TEXTCOLOR_SECTION, exe_blob(TEXTCOLOR_BLOB, build), chars=CODE_SECTION)
    base = struct.unpack_from('<I', out, struct.unpack_from('<I', out, 0x3c)[0] + 24 + 28)[0]
    for off, op in BUILDS[build]['textcolor']:
        if op == 'ff15':
            _branch(out, off, rva, 6)
        else:
            out[off:off + 6] = b'\xbe' + struct.pack('<I', base + rva) + b'\x90'
    return out


def apply_windowed(buf, build):
    """The .bg row copy in the exe through bgrow.asm."""
    out, rva = append_section(buf, BGROW_SECTION, exe_blob(BGROW_BLOB, build), chars=CODE_SECTION)
    _branch(out, BUILDS[build]['sites']['bgrow'], rva, BGROW_LEN)
    return out


def apply_altenter(buf, build):
    """altenter.asm in front of the window procedure's default handler.
    The section keeps the user32 entry points it resolves, so it is writable."""
    row = BUILDS[build]
    _check_call(buf, row['sites']['altenter'], row['addresses']['HANDLER'], 'the text-input handler')
    out, rva = append_section(buf, ALTENTER_SECTION, exe_blob(ALTENTER_BLOB, build))
    _branch(out, row['sites']['altenter'], rva)
    return out


def apply_mixerless(buf, build):
    """MGAudio's Init, on finding no CD mixer line: `jne fail` becomes a
    jump to a stub that zeroes the control count it is about to allocate
    for (uninitialised when the search fails) and eax, the HeapAlloc
    flags, then jumps back to that allocation. Nothing absolute, so no
    relocation entries change."""
    site = BUILDS[build]['sites']['mixer']
    site_rva = 0x1000 + site - _rva_to_off(buf, 0x1000)
    stub = bytes.fromhex('31c0') + bytes.fromhex('898684000000')      # xor eax,eax; mov [esi+0x84],eax
    out, rva = append_section(buf, MIXERLESS_SECTION, stub + b'\xe9' + b'\0' * 4, chars=CODE_SECTION)
    start = _rva_to_off(out, rva)
    struct.pack_into('<i', out, start + len(stub) + 1, site_rva + 6 - (rva + len(stub) + 5))
    out[site:site + 6] = b'\x0f\x85' + struct.pack('<i', rva - (site_rva + 6))
    return out


MIX_SECTION = b'.sr2b'
MIX_STREAM = 51                                  # the second routine in mix.asm


def apply_mix(buf, build):
    """mix.asm in MGSound.dll: the buffer's SetRange loads min and max
    through the first routine (8 bytes), the streaming buffer's SetVolume
    finishes its mapping through the second (6 bytes, whose flags the
    branch after them tests)."""
    sites = BUILDS[build]['sites']['mix']
    out, rva = append_section(buf, MIX_SECTION, MIX_BLOB, chars=CODE_SECTION)
    _branch(out, sites[0], rva, 8)
    _branch(out, sites[1], rva + MIX_STREAM, 6)
    return out


def apply_sfxoptions(buf, build):
    """The three sites are written; each carried a relocation entry for
    the settings pointer now gone, dropped here."""
    rvas = [_off_to_rva(buf, off) + 2 for off in BUILDS[build]['sites']['sfxoptions']]
    if _drop_relocations(buf, rvas) != len(rvas):
        raise ValueError('Options.dll: relocation entries for the settings loads not all found')
    return buf


DEVMENU_SECTION = b'.sr2d'
DATA_SECTION = 0xC0000040               # IMAGE_SCN_CNT_INITIALIZED_DATA | MEM_READ | MEM_WRITE
DEVMENU_X = (110.0, 250.0, 390.0, 530.0)   # four items across 640, stock 154, 320, 487
DEVMENU_UV_DEVICE = 0xe                 # spare entries in the page's UV table: "DEVICE" on sheet 6,
DEVMENU_UV_ICON = 0x11                  # and the icon on the appended sheet
DEVMENU_DEVICE = (2, 73, 79, 95)        # "DEVICE" on sheet 6, in texels
TXR = 'BINDATA\\MISC\\OPTIONS.TXR'
TXR_SIZE = 1282048
TXR_ENTRIES = ((2, 128), (0, 128), (8, 256), (8, 256), (0, 256), (0, 256), (8, 256), (2, 256), (8, 256), (8, 256), (8, 256), (8, 128))
TXR_DEVICE_MD5 = '84a4889baf435baf631db36a90078df0'   # the "DEVICE" texels, English sheet
TXR_ICON = 12                           # the appended sheet's index


def _add_relocations(buf, rvas):
    """Append HIGHLOW entries for the given RVAs to the relocation directory,
    in the zero tail of .reloc; the directory grows."""
    pe_off = struct.unpack_from('<I', buf, 0x3c)[0]
    opt = pe_off + 24
    nsec = struct.unpack_from('<H', buf, pe_off + 6)[0]
    table = opt + struct.unpack_from('<H', buf, pe_off + 20)[0]
    rel_rva, rel_size = struct.unpack_from('<II', buf, opt + 136)
    blocks = b''
    for page in sorted({rva & ~0xfff for rva in rvas}):
        entries = sorted(0x3000 | (rva & 0xfff) for rva in rvas if rva & ~0xfff == page)
        if len(entries) % 2:
            entries.append(0)
        blocks += struct.pack('<II', page, 8 + 2 * len(entries)) + struct.pack('<%dH' % len(entries), *entries)
    for i in range(nsec):
        vsize, va, rsize = struct.unpack_from('<III', buf, table + i * 40 + 8)
        if va == rel_rva:
            break
    else:
        raise ValueError('no relocation section')
    if rel_size + len(blocks) > rsize:
        raise ValueError('no room in the relocation section')
    off = _rva_to_off(buf, rel_rva) + rel_size
    if any(buf[off:off + len(blocks)]):
        raise ValueError('the relocation section\'s tail is not empty')
    buf[off:off + len(blocks)] = blocks
    struct.pack_into('<I', buf, opt + 140, rel_size + len(blocks))
    struct.pack_into('<I', buf, table + i * 40 + 8, max(vsize, rel_size + len(blocks)))


def apply_devmenu(buf, build):
    """A fourth item on the Options menu. The three item tables (cursor
    frames, icons, labels) move to a new data section with a fourth entry
    each. The item's icon is the sheet patch_txr appends, its label
    "DEVICE" and "SETTINGS" from the page's own sheets, both through spare
    UV entries. Confirming it returns to the menu until the page exists.
    The stock items move to four-across positions."""
    cursor, icons, labels, labelend, dispatch, ftab = BUILDS[build]['sites']['devmenu']
    base = struct.unpack_from('<I', buf, struct.unpack_from('<I', buf, 0x3c)[0] + 24 + 28)[0]

    def va_off(va):
        return _rva_to_off(buf, va - base)

    def dword(off):
        return struct.unpack_from('<I', buf, off)[0]

    tables = [[dword(ftab + t * 0xc + i * 4) for i in range(3)] for t in range(3)]
    frame0, icon0, label0 = (va_off(tables[t][0]) for t in range(3))
    page = dword(frame0)
    if page != dword(icon0) or page != dword(label0) or dword(frame0 + 8) != 9 or dword(label0 + 8) != 2:
        raise ValueError('Options.dll: the menu tables are not what the patcher knows')
    uvs = {}
    for entry in (DEVMENU_UV_DEVICE, DEVMENU_UV_ICON):
        uvs[entry] = va_off(page) + entry * 0x14
        if struct.unpack_from('<i', buf, uvs[entry])[0] != -1:
            raise ValueError('Options.dll: UV entry %#x is in use' % entry)
    stub_site = dispatch + 12
    cont = va_off(dword(stub_site)) + 7
    if buf[cont - 7:cont] != bytes.fromhex('c746080b000000'):
        raise ValueError('Options.dll: the dispatch table is not what the patcher knows')

    # the stock items, four across
    for t in range(3):
        for i in range(3):
            struct.pack_into('<f', buf, va_off(tables[t][i]) + 0x14, DEVMENU_X[i])
    # the spare UV entries: "DEVICE", and the whole appended sheet but its edge
    struct.pack_into('<i4f', buf, uvs[DEVMENU_UV_DEVICE], 6, *(v / 256.0 for v in DEVMENU_DEVICE))
    struct.pack_into('<i4f', buf, uvs[DEVMENU_UV_ICON], TXR_ICON, 1 / 128.0, 1 / 128.0, 127 / 128.0, 127 / 128.0)

    # the blob: tables, descriptors, quads, stub
    rva = _next_section_rva(buf)
    va = base + rva
    frame_quads = bytes(buf[va_off(dword(frame0 + 4)):va_off(dword(frame0 + 4)) + 9 * 0x34])
    icon_quad = bytearray(buf[va_off(dword(icon0 + 4)):va_off(dword(icon0 + 4)) + 0x34])
    struct.pack_into('<I', icon_quad, 0, DEVMENU_UV_ICON)
    settings = bytes(buf[va_off(dword(label0 + 4)) + 0x34:va_off(dword(label0 + 4)) + 0x68])
    device = struct.pack('<I4f', DEVMENU_UV_DEVICE, -38.0, -22.0, 39.0, 0.0) + settings[0x14:]
    layout = {'ftab': 0x00, 'itab': 0x10, 'ltab': 0x20, 'descf': 0x30, 'desci': 0x50, 'descl': 0x70,
              'quadsf': 0x90, 'quadsi': 0x264, 'quadsl': 0x298, 'stub': 0x300}
    blob = bytearray(0x30c)
    relocs = []
    for t, name in enumerate(('ftab', 'itab', 'ltab')):
        for i in range(3):
            struct.pack_into('<I', blob, layout[name] + i * 4, tables[t][i])
        struct.pack_into('<I', blob, layout[name] + 12, va + layout[('descf', 'desci', 'descl')[t]])
        relocs += [layout[name] + i * 4 for i in range(4)]
    for name, quads, n, w, h, y in (('descf', 'quadsf', 9, 134.0, 134.0, 202.0), ('desci', 'quadsi', 1, 126.0, 126.0, 202.0),
                                   ('descl', 'quadsl', 2, 106.0, 45.0, 296.0)):
        struct.pack_into('<IIIffffI', blob, layout[name], page, va + layout[quads], n, w, h, DEVMENU_X[3], y, 0)
        relocs += [layout[name], layout[name] + 4]
    blob[layout['quadsf']:layout['quadsf'] + 9 * 0x34] = frame_quads
    blob[layout['quadsi']:layout['quadsi'] + 0x34] = icon_quad
    blob[layout['quadsl']:layout['quadsl'] + 0x68] = device + settings
    stub_va = va + layout['stub']
    blob[layout['stub']:layout['stub'] + 12] = bytes.fromhex('c7460801000000') + b'\xe9' + struct.pack('<i', base + _off_to_rva(buf, cont) - (stub_va + 12))
    out, got = append_section(buf, DEVMENU_SECTION, bytes(blob), chars=DATA_SECTION | 0x20000000)
    if got != rva:
        raise ValueError('section placed at %#x, expected %#x' % (got, rva))
    _add_relocations(out, [rva + r for r in relocs])

    # the sites: the counts are written already; the tables and the dispatch entry here
    struct.pack_into('<I', out, cursor + 4, va + layout['ftab'])
    struct.pack_into('<I', out, icons + 3, va + layout['itab'])
    struct.pack_into('<I', out, labels + 1, va + layout['ltab'])
    struct.pack_into('<I', out, labelend + 2, va + layout['ltab'] + 16)
    struct.pack_into('<I', out, stub_site, stub_va)
    return out


def wheel_mask(size=126):
    """Coverage, 0..255, of a steering wheel drawn in the icons' style: a
    rim, three spokes, a hub with a hole. Sixteen samples a pixel."""
    c = size / 2.0
    rim, inner, hub, hole, half = 50.0, 37.0, 14.0, 5.0, 6.0
    mask = bytearray(size * size)
    for y in range(size):
        for x in range(size):
            hits = 0
            for sy in range(4):
                for sx in range(4):
                    dx = x + (sx + 0.5) / 4 - c
                    dy = y + (sy + 0.5) / 4 - c
                    d2 = dx * dx + dy * dy
                    if inner * inner <= d2 <= rim * rim or hole * hole <= d2 <= hub * hub:
                        hits += 1
                    elif d2 < (inner + 1) * (inner + 1) and (abs(dy) <= half or (dy >= 0 and abs(dx) <= half)):
                        hits += 1
            mask[y * size + x] = hits * 255 // 16
    return bytes(mask)


def txr_check(data):
    """The stock OPTIONS.TXR, or why not."""
    if len(data) != TXR_SIZE or data[:4] != b'RTEX' or struct.unpack_from('<I', data, 4)[0] != len(TXR_ENTRIES):
        return 'not the stock OPTIONS.TXR'
    off = 0x1000
    offsets = []
    for i, (fmt, size) in enumerate(TXR_ENTRIES):
        if struct.unpack_from('<4I', data, 16 + 16 * i) != (fmt, size, size * size * 2, 0):
            return 'texture %d is not what the patcher knows' % i
        offsets.append(off)
        off += size * size * 2
    x0, y0, x1, y1 = DEVMENU_DEVICE
    sheet = offsets[6]
    region = b''.join(data[sheet + (y * 256 + x0) * 2:sheet + (y * 256 + x1) * 2] for y in range(y0, y1))
    if hashlib.md5(region).hexdigest() != TXR_DEVICE_MD5:
        return 'the label sheet is not the English one'
    return None


def patch_txr(data):
    """OPTIONS.TXR with a thirteenth sheet: the third icon's plate, its
    picture filled back in, with a steering wheel cut out the same way.
    Returns the grown file."""
    why = txr_check(data)
    if why:
        raise ValueError('%s: %s' % (TXR, why))
    sheet = 0x1000 + sum(size * size * 2 for _f, size in TXR_ENTRIES[:10])
    plate = bytearray(126 * 126 * 2)
    for y in range(126):
        row = sheet + ((129 + y) * 256 + 1) * 2
        plate[y * 252:y * 252 + 252] = data[row:row + 252]
    for y in range(16, 115):                # the picture's box, back to the plate's grey
        for x in range(14, 112):
            struct.pack_into('<H', plate, (y * 126 + x) * 2, 0xf999)
    mask = wheel_mask()
    for i in range(126 * 126):
        texel = struct.unpack_from('<H', plate, i * 2)[0]
        alpha = max(0, (texel >> 12) * 17 - mask[i])
        struct.pack_into('<H', plate, i * 2, (texel & 0xfff) | ((alpha + 8) // 17) << 12)
    texture = bytearray(128 * 128 * 2)
    for y in range(126):
        texture[((y + 1) * 128 + 1) * 2:((y + 1) * 128 + 127) * 2] = plate[y * 252:y * 252 + 252]
    out = bytearray(data)
    struct.pack_into('<I', out, 4, len(TXR_ENTRIES) + 1)
    struct.pack_into('<4I', out, 16 + 16 * len(TXR_ENTRIES), 8, 128, len(texture), 0)
    return bytes(out + texture)


def _next_section_rva(buf):
    """Where append_section will put the next section."""
    pe_off = struct.unpack_from('<I', buf, 0x3c)[0]
    nsec = struct.unpack_from('<H', buf, pe_off + 6)[0]
    opt = pe_off + 24
    table = opt + struct.unpack_from('<H', buf, pe_off + 20)[0]
    sect_align = struct.unpack_from('<I', buf, opt + 32)[0]
    last_vsize, last_va = struct.unpack_from('<II', buf, table + (nsec - 1) * 40 + 8)
    return _align(last_va + last_vsize, sect_align)


VOLTRACE_SECTION = b'.sr2v'


def apply_voltrace(buf, build):
    """The diagnostic: five volume entry points jump into voltrace.asm,
    which reports and jumps back through a return-address table placed
    after the blob. Needs a section-table slot: apply without one of the
    exe patches that take one."""
    sites = BUILDS[build]['sites']['voltrace']
    blob = exe_blob(VOLTRACE_BLOB, build)
    out, rva = append_section(buf, VOLTRACE_SECTION, blob + b'\0' * (4 * len(sites)), chars=CODE_SECTION)
    start = _rva_to_off(out, rva)
    text_off = _rva_to_off(out, 0x1000)
    for i, (off, length) in enumerate(sites):
        slot_va = IMAGE_BASE + rva + len(blob) + 4 * i
        struct.pack_into('<I', out, start + len(blob) + 4 * i, IMAGE_BASE + 0x1000 + off - text_off + length)
        out[start:start + len(blob)] = bytes(out[start:start + len(blob)]).replace(
            struct.pack('<I', 0xE7E7E7E1 + i), struct.pack('<I', slot_va))
        _branch(out, off, rva + 5 * i, length, op=b'\xe9')
    return out


def apply_titlebg(buf, _build=None):
    """Title.dll's own .bg row copy through bgrow.asm's TITLE build. The
    site holds no absolute address, so no relocation entry goes."""
    out, rva = append_section(buf, TITLEROW_SECTION, TITLEROW_BLOB, chars=CODE_SECTION)
    _branch(out, TITLEROW_SITE, rva, TITLEROW_LEN)
    return out


def apply_fullwin(buf, _build=None):
    """fullwin.asm in MGameD3D: the windowed present jumps to its first
    thunk, the window sizing calls its second."""
    if _drop_relocations(buf, FULLWIN_RELOCS) != len(FULLWIN_RELOCS):
        raise ValueError('relocation entries for the present not all found')
    out, rva = append_section(buf, FULLWIN_SECTION, FULLWIN_BLOB, chars=CODE_SECTION)
    start = _rva_to_off(out, rva)
    out[start:start + len(FULLWIN_BLOB)] = FULLWIN_BLOB.replace(
        struct.pack('<I', FULLWIN_MAGIC), struct.pack('<I', rva))
    _branch(out, PRESENT_SITE, rva, 6, op=b'\xe9')
    _branch(out, SIZE_SITE, rva + 5, 6)
    return out


# Patch

def md5(path):
    with open(path, 'rb') as fh:
        return hashlib.md5(fh.read()).hexdigest()


def check_build(dest):
    """Which build is installed: the exe's MD5 (its backup's, once
    patched) names the row, and every file in the row must be untouched.
    The import slots the row names are checked against the exe itself."""
    def source(name):
        path = os.path.join(dest, *name.split('\\'))
        if not os.path.isfile(path):
            raise FileNotFoundError('missing %s' % name)
        return path + '.bak' if name in PATCHED and os.path.isfile(path + '.bak') else path

    build = build_of(md5(source(EXE)))
    if build is None:
        raise ValueError('%s is not a Pentium III build the patcher knows' % EXE)
    row = BUILDS[build]
    for name, (size, digest) in row['files'].items():
        path = source(name)
        if os.path.getsize(path) != size or md5(path) != digest:
            raise ValueError('%s is not the %s build\'s' % (name, build))
    with open(source(EXE), 'rb') as fh:
        exe = fh.read()
    for func, slot in row['slots'].items():
        if _iat_slot(exe, SLOT_DLL.get(func, 'kernel32.dll'), func) != slot - IMAGE_BASE:
            raise ValueError('%s: the import table does not match the %s row' % (func, build))
    return build


def patch(dest, log=print, keys=PATCH_KEYS):
    """Write every wanted patch. Each touched file is patched from its
    backup, written on the first run, so patching twice is patching once."""
    build = check_build(dest)
    table = patches(build)
    log('patch: %s build' % build)
    txr = None
    if 'devmenu' in keys:
        path = os.path.join(dest, *TXR.split('\\'))
        source = path + '.bak' if os.path.isfile(path + '.bak') else path
        with open(source, 'rb') as fh:
            txr = fh.read()
        why = txr_check(txr)
        if why:
            raise ValueError('%s: %s' % (TXR, why))
    for name in PATCHED:
        size, digest = BUILDS[build]['files'][name]
        wanted = [table[key] for key in keys if key in table and table[key][0] == name]
        sites = [site for _f, ss, _t in wanted for site in ss]
        transforms = [globals()[t] for _f, _s, t in wanted if t]
        if not sites and not transforms:
            continue
        path = os.path.join(dest, *name.split('\\'))
        bak = path + '.bak'
        source = bak if os.path.isfile(bak) else path
        if os.path.getsize(source) != size or md5(source) != digest:
            raise ValueError('%s is not the file the patcher knows' % name)
        with open(source, 'rb') as fh:
            buf = bytearray(fh.read())
        if source == path:
            with open(bak, 'wb') as fh:
                fh.write(buf)
            log('patch: backup written to %s.bak' % name)
        for off, old, new in sites:
            if buf[off:off + len(old)] != old:
                raise ValueError('%s: unexpected bytes at 0x%x' % (name, off))
            if new is not None:
                buf[off:off + len(new)] = new
        for transform in transforms:
            buf = transform(buf, build)
        with open(path, 'wb') as fh:
            fh.write(buf)
        log('patch: %s written, %s' % (name, ', '.join(k for k in keys if k in table and table[k][0] == name)))
    if txr is not None:
        path = os.path.join(dest, *TXR.split('\\'))
        if not os.path.isfile(path + '.bak'):
            os.replace(path, path + '.bak')
            log('patch: backup written to %s.bak' % TXR)
        with open(path, 'wb') as fh:
            fh.write(patch_txr(txr))
        log('patch: %s written, devmenu' % TXR)


def restore(dest, log=print):
    found = False
    for name in PATCHED + (TXR,):
        path = os.path.join(dest, *name.split('\\'))
        if os.path.isfile(path + '.bak'):
            os.replace(path + '.bak', path)
            log('restore: original %s back in place' % name)
            found = True
    if not found:
        raise FileNotFoundError('no backups in %s' % dest)


# Window

def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(LABEL)
    root.resizable(True, False)
    msgs = queue.Queue()

    src = tk.StringVar()
    cue = tk.StringVar()
    dest = tk.StringVar()
    lang = tk.StringVar(value=LANGUAGES[0])

    def browse_src():
        p = filedialog.askopenfilename(
            title='Install disc image',
            filetypes=[('Disc image', '*.cue *.iso *.bin'), ('data1.cab', 'data1.cab'), ('All', '*')])
        if p:
            src.set(p)

    def browse_cue():
        p = filedialog.askopenfilename(title='Play disc image (cue sheet)',
                                       filetypes=[('Cue sheet', '*.cue'), ('All', '*')])
        if p:
            cue.set(p)

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
            messagebox.showwarning(LABEL, 'Pick the install disc image and an install folder.')
            return
        run(install, src.get(), dest.get(), lang.get(), log)

    def do_rip():
        if not cue.get() or not dest.get():
            messagebox.showwarning(LABEL, 'Pick the play disc cue sheet and the install folder.')
            return
        run(rip, cue.get(), dest.get(), log)

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

    ttk.Label(frame, text='Disc 1 image').grid(row=0, column=0, sticky='w')
    ttk.Entry(frame, textvariable=src, width=60).grid(row=0, column=1, sticky='ew', padx=4)
    ttk.Button(frame, text='Browse', command=browse_src).grid(row=0, column=2)
    ttk.Label(frame, text='Disc 2 cue').grid(row=1, column=0, sticky='w')
    ttk.Entry(frame, textvariable=cue).grid(row=1, column=1, sticky='ew', padx=4)
    ttk.Button(frame, text='Browse', command=browse_cue).grid(row=1, column=2)
    ttk.Label(frame, text='Install to').grid(row=2, column=0, sticky='w')
    ttk.Entry(frame, textvariable=dest).grid(row=2, column=1, sticky='ew', padx=4)
    ttk.Button(frame, text='Browse', command=browse_dest).grid(row=2, column=2)
    ttk.Label(frame, text='Language').grid(row=3, column=0, sticky='w')
    ttk.Combobox(frame, textvariable=lang, values=LANGUAGES, state='readonly',
                 width=12).grid(row=3, column=1, sticky='w', padx=4)

    row = ttk.Frame(frame)
    row.grid(row=4, column=0, columnspan=3, pady=6, sticky='w')
    buttons = [ttk.Button(row, text='Install', command=do_install),
               ttk.Button(row, text='Rip soundtrack', command=do_rip),
               ttk.Button(row, text='Patch', command=do_patch),
               ttk.Button(row, text='Restore original', command=do_restore)]
    for b in buttons:
        b.pack(side='left', padx=2)

    text = tk.Text(frame, height=12, width=80, state='disabled')
    text.grid(row=5, column=0, columnspan=3, sticky='nsew')

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
    """Fail here, not half way through somebody's executable: for every
    build, every site inside the file, no two patches on one byte,
    replacement no longer than what it replaces, and every stub
    placeholder filled."""
    sites = 0
    for build, row in BUILDS.items():
        table = patches(build)
        taken = {}
        for key, (name, ss, transform) in table.items():
            if name not in PATCHED:
                raise ValueError('%s: %s is not a patched file' % (key, name))
            if transform and transform not in globals():
                raise ValueError('%s: no transform named %s' % (key, transform))
            size = row['files'][name][0]
            for off, old, new in ss:
                if new is not None and len(new) > len(old):
                    raise ValueError('%s: replacement longer than original at 0x%x' % (key, off))
                if off + len(old) > size:
                    raise ValueError('%s: site 0x%x past the end of the %s %s' % (key, off, build, name))
                for i in range(off, off + len(old)):
                    if (name, i) in taken:
                        raise ValueError('%s and %s both write %s:0x%x' % (key, taken[(name, i)], name, i))
                    taken[(name, i)] = key
            sites += len(ss)
        if MIX_BLOB[MIX_STREAM:MIX_STREAM + 3] != b'\x51\x8d\x83':    # `push ecx; lea eax, [ebx+...]` opens the stream routine
            raise ValueError('mix.asm: the stream routine is not at +%d' % MIX_STREAM)
        for blob in (ACTIVATE_BLOB, ALTENTER_BLOB, BGROW_BLOB, TEXTCOLOR_BLOB):
            for magic in EXE_MAGICS.values():
                if struct.pack('<I', magic) in exe_blob(blob, build):
                    raise ValueError('%s: a placeholder left in a stub' % build)
    print('tables OK: %d builds, %d patches, %d sites, %d files'
          % (len(BUILDS), len(PATCH_KEYS), sites, len(PATCHED)))
    return 0


def main(argv):
    args = argv[1:]
    if not args:
        gui()
        return 0
    try:
        if args[0] == '--install' and 3 <= len(args) <= 4:
            install(*args[1:])
        elif args[0] == '--patch' and 2 <= len(args) <= 3:
            keys = tuple(args[2].split(',')) if len(args) == 3 else PATCH_KEYS
            unknown = [k for k in keys if k not in PATCH_KEYS + DIAGNOSTIC]
            if unknown:
                raise ValueError('no patch named %s; the patches are %s' % (unknown[0], ', '.join(PATCH_KEYS)))
            patch(args[1], keys=keys)
        elif args[0] == '--rip' and len(args) == 3:
            rip(args[1], args[2])
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
