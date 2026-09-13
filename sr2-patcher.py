#!/usr/bin/env python3
"""SEGA RALLY 2 (PC, 1999) patcher. See README.md.

    python3 sr2-patcher.py                          the window
    python3 sr2-patcher.py --install SRC DIR [LANG] install from a .cue, .iso, disc folder or data1.cab
    python3 sr2-patcher.py --patch DIR [KEYS]       patch an installed game: every patch, the ones KEYS names, or all but the ones it names with a minus (-borderless)
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
PATCHED = (EXE, 'MUSASHI\\MGameD3D.dll', 'MUSASHI\\MGAudio.dll', 'MUSASHI\\MGSound.dll', 'MUSASHI\\MGInput.dll',
           'Title.dll', 'Options.dll', 'ReplayGallery.dll')

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
            'MUSASHI\\MGInput.dll': (90112, '7aa0b3aede10fd247835ad346c2ecee8'),
            'Options.dll': (767488, '25c523277608e7cf2491ee8c67dd7fce'),
            'Title.dll': (637952, 'b1c6ea70b15cc41752c630ae0fb0cf0c'),
            'ReplayGallery.dll': (792576, 'f0db027aa72f43d146859eaef51d74f0'),
        },
        'sites': {'check': 0x267c0, 'loader': 0x7572e, 'activate': 0x25ff7,
                  'devices': (0x33f8, 0x340f, 0x3214, 0x3267, 0x31c0, 0x9aa20, 0x2f0c, 0x3638),   # Options.dll
                  'noregistry': (0xd07c0, 0x7e359), 'xinput': (0x8130, 0x8210, 0x7100, 0x56c0),   # the latter MGInput.dll
                  'flag': 0x273e6, 'cardwarn': 0x26678, 'cdlevel': 0x73048, 'bgrow': 0x14671, 'altenter': 0x260bc,
                  'voltrace': ((0x6e6e0, 6), (0x6fa30, 9), (0x6d560, 5), (0x6e770, 9), (0x6e0e0, 6)),
                  'volume': 0x1db0, 'getvolume': 0x1e40,   # in MGAudio.dll: the CD-volume methods
                  'mix': (0x439f, 0x6980)},  # in MGSound.dll: the buffer's SetRange, the stream's SetVolume
        # `ff15` call [slot], `8b35` mov esi, [slot]; the slot is SetTextColor's.
        'textcolor': ((0x203c7, '8b35'), (0x20566, '8b35'), (0x3485f, 'ff15'), (0x34b2a, 'ff15'),
                      (0x34efc, 'ff15'), (0x35533, 'ff15'), (0x360c3, 'ff15'), (0x3a6c0, 'ff15'),
                      (0x3cef4, 'ff15'), (0x3da96, 'ff15')),
        'slots': {'SetTextColor': 0x495028, 'GetLogicalDriveStringsA': 0x495198, 'lstrcpyA': 0x4950f4,
                  'LoadLibraryA': 0x495090, 'GetProcAddress': 0x4950f0},
        'options': {'BINDPAGE': 0x1000ed90, 'DRAW': 0x1000e850, 'PLAYSOUND': 0x1000b610, 'INPUT': 0x100b9464,
                    'SOUNDOBJ': 0x100b8bd8, 'HANDLES': 0x100b8bdc, 'TOPTABLE': 0x10003d90,
                    'TEXT': 0x1000df10, 'GLYPHS': 0x1009c080},
        'addresses': {'MENUTABLES': 0x1009c820, 'REGNAMES': (0x5a2714, 0x4cff94), 'CARS': 0x4d64bc, 'PADPOLL': 0x5a1ff0, 'RESUME': 0x46e260, 'GAMED3D': 0x50b118, 'HANDLER': 0x41fe20, 'HWND': 0x5088ac,
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
            'MUSASHI\\MGInput.dll': (90112, '7aa0b3aede10fd247835ad346c2ecee8'),
            'Options.dll': (767488, '25c523277608e7cf2491ee8c67dd7fce'),
            'Title.dll': (637952, 'b1c6ea70b15cc41752c630ae0fb0cf0c'),
            'ReplayGallery.dll': (792576, 'f0db027aa72f43d146859eaef51d74f0'),
        },
        'sites': {'check': 0x26a80, 'loader': 0x75b5e, 'activate': 0x262a7,
                  'devices': (0x33f8, 0x340f, 0x3214, 0x3267, 0x31c0, 0x9aa20, 0x2f0c, 0x3638),   # Options.dll
                  'noregistry': (0xd0bc0, 0x7e779), 'xinput': (0x8130, 0x8210, 0x7100, 0x56c0),
                  'flag': 0x276a6, 'cardwarn': 0x26938, 'cdlevel': 0x73478, 'bgrow': 0x14921, 'altenter': 0x2636c,
                  'volume': 0x1db0, 'getvolume': 0x1e40, 'mix': (0x439f, 0x6980)},
        'textcolor': ((0x20657, '8b35'), (0x207f6, '8b35'), (0x34b8f, 'ff15'), (0x34e5a, 'ff15'),
                      (0x3522c, 'ff15'), (0x35863, 'ff15'), (0x363f3, 'ff15'), (0x3aae0, 'ff15'),
                      (0x3d314, 'ff15'), (0x3ddc6, 'ff15')),
        'slots': {'SetTextColor': 0x495028, 'GetLogicalDriveStringsA': 0x49519c, 'lstrcpyA': 0x4950f4,
                  'LoadLibraryA': 0x495090, 'GetProcAddress': 0x4950f0},
        'options': {'BINDPAGE': 0x1000ed90, 'DRAW': 0x1000e850, 'PLAYSOUND': 0x1000b610, 'INPUT': 0x100b9464,
                    'SOUNDOBJ': 0x100b8bd8, 'HANDLES': 0x100b8bdc, 'TOPTABLE': 0x10003d90,
                    'TEXT': 0x1000df10, 'GLYPHS': 0x1009c080},
        'addresses': {'MENUTABLES': 0x1009c820, 'REGNAMES': (0x5a2714, 0x4d0074), 'CARS': 0x4d65ac, 'PADPOLL': 0x5a1ff0, 'RESUME': 0x46e480, 'GAMED3D': 0x50b218, 'HANDLER': 0x41feb0, 'HWND': 0x5089ac,
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
            'MUSASHI\\MGInput.dll': (90112, '594a3435f9c2ef6f1ac23cd3ba5dd6b1'),
            'Options.dll': (798720, '0af388650bc11dcd6df2377d3d78a535'),
            'Title.dll': (637952, 'a8017ec64efb1eba81e3e80f8afb875b'),
            'ReplayGallery.dll': (793088, 'be260f94b8791b91cfc3588de5b3473f'),
        },
        'sites': {'check': 0x4b420, 'loader': 0xb4dbe, 'activate': 0x4abfd,
                  'devices': (0x5b68, 0x5b7f, 0x5984, 0x59d7, 0x5930, 0xa0b08, 0x567c, 0x5da8),   # Options.dll
                  'noregistry': (0x115fd4, 0xbd959), 'xinput': (0x7940, 0x7a20, 0x6940, 0x81a8, 0x7e40),   # the latter MGInput.dll
                  'flag': 0x4c026, 'bgrow': 0x27e71, 'altenter': 0x4acc2, 'oscheck': 0x4b3b0, 'cardwarn': 0x4b263, 'cdlevel': 0xb2668,
                  'volume': 0x1d90, 'getvolume': 0x1e20, 'mixer': 0x2278,    # all in MGAudio.dll
                  'mix': (0x439f, 0x6980),
                  'sfxlevel': (0xb26cb, 0xb272e, 0xb2782), 'sfxoptions': (0xf92a, 0xf98d, 0xf9e1)},
        'textcolor': ((0x400f7, '8b35'), (0x40296, '8b35'), (0x5e28f, 'ff15'), (0x5e55a, 'ff15'),
                      (0x5e91c, 'ff15'), (0x5ef53, 'ff15'), (0x5fae3, 'ff15'), (0x66930, 'ff15'),
                      (0x69164, 'ff15'), (0x69c16, 'ff15')),
        'slots': {'SetTextColor': 0x4d402c, 'GetLogicalDriveStringsA': 0x4d4198, 'lstrcpyA': 0x4d40fc,
                  'LoadLibraryA': 0x4d4094, 'GetProcAddress': 0x4d40f8},
        'options': {'BINDPAGE': 0x10013df0, 'DRAW': 0x100138b0, 'PLAYSOUND': 0x10010670, 'INPUT': 0x100c1b1c,
                    'SOUNDOBJ': 0x100be46c, 'HANDLES': 0x100be470, 'TOPTABLE': 0x10006500,
                    'TEXT': 0x10012f70, 'GLYPHS': 0x100a1090},
        'addresses': {'MENUTABLES': 0x100a2708, 'REGNAMES': (0x60c714, 0x5151cc), 'CARS': 0x52f9cc, 'PADPOLL': 0x60bff0, 'RESUME': 0x4ad790, 'GAMED3D': 0x575ae8, 'HANDLER': 0x43fb50, 'HWND': 0x57327c,
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
#   nocardwarn  the video-card warning box skipped
#   zdetach     DeleteAttachedSurface(0, NULL) calls removed (Proton crash)
#   altab       the resume call restores the DirectDraw surfaces first
#   managed     video-memory textures become managed
#   restoreall  the restore routine becomes RestoreAllSurfaces
#   texfmt      A1R5G5B5 first in the texture-format preference list
#   textcolor   the lobby's SetTextColor(-1) masked to RGB
#   windowed    the fullscreen flag cleared; the .bg row copy expands to 32 bits
#   anydepth    the windowed path's 16-bit desktop check skipped
#   titlebg     Title.dll's own .bg row copy, the same stub
#   texrange    the texture release checks its index; VendorLogo releases -128
#   replayfree  the replay gallery frees only the replay it loaded, not a race's in MainMode's data
#   borderless  the window covers its monitor, the present letterboxes
#   altenter    ALT+ENTER toggles a framed window
#   cdlevel     the menu's CD-level set flagged, so the music hook tells it from a fade; music needs it
#   music       CD audio from music\trackNN.wav; the BGM slider sets its volume
#   devices     a fourth Options item, Device Settings, placed for the controller page; also grows OPTIONS.TXR
#   voltrace    diagnostic, by name only: volume calls reported on +debugstr

# The first bytes of the five volume entry points voltrace hooks.
VOLTRACE_HEADS = (bytes.fromhex('558bec83ec0c'), bytes.fromhex('558bec81ec80000000'), bytes.fromhex('568b3185f6'),
                  bytes.fromhex('558bec81ec88000000'), bytes.fromhex('558bec83ec0c'))


def devices_sites(offsets, tables):
    """The Options menu's sites: the cursor and icon-set constructors
    (their item counts go 3 to 4), the label loop's bounds, the frame the
    confirm animation draws, and the dispatch table, all naming the three
    item tables at `tables`; and the top-level state count, 0xb to 0xd
    for the page's two states."""
    cursor, icons, labels, labelend, _dispatch, _ftab, topcmp, confirm = offsets
    t = struct.pack('<I', tables)
    return ((cursor, bytes.fromhex('6a035068') + t, bytes.fromhex('6a04')),
            (icons, bytes.fromhex('6a0368') + struct.pack('<I', tables + 0xc), bytes.fromhex('6a04')),
            (labels, b'\xbf' + struct.pack('<I', tables + 0x18), None),
            (labelend, bytes.fromhex('81ff') + struct.pack('<I', tables + 0x24), None),
            (topcmp, bytes.fromhex('83f80b0f87'), bytes.fromhex('83f80d')),
            (confirm, bytes.fromhex('8b0c85') + t, None))


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
        'nocardwarn': (EXE, ((site['cardwarn'], b'\x6a\x05', b'\xeb\x27'),), None),
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
        'texrange': ('MUSASHI\\MGameD3D.dll', ((0x4430, bytes.fromhex('a180250110568b742408'), None),), 'apply_texrange'),
        'replayfree': ('ReplayGallery.dll', ((0x2f65, bytes.fromhex('e881820000'), None),
                                             (0x3b1f, bytes.fromhex('50e8bb760000'), None)), 'apply_replayfree'),
        'borderless': ('MUSASHI\\MGameD3D.dll', (
            (0x4d7b, bytes.fromhex('8b0df8230110'), None),
            (0x26be, bytes.fromhex('ff152cf10010'), None)), 'apply_fullwin'),
        'mix': ('MUSASHI\\MGSound.dll', ((site['mix'][0], bytes.fromhex('8b4c240c8b542410'), None),
                                        (site['mix'][1], bytes.fromhex('03d68bf285f6'), None)), 'apply_mix'),
        'cdlevel': (EXE, ((site['cdlevel'], bytes.fromhex('6a00d80d'), bytes.fromhex('6a40d80d')),), None),
        'music': ('MUSASHI\\MGAudio.dll', ((site['volume'], bytes.fromhex('53568b74240c'), None),
                                          (site['getvolume'], bytes.fromhex('53568b74240c'), None)), 'apply_music'),
        'devices': ('Options.dll', devices_sites(site['devices'], row['addresses']['MENUTABLES']), 'apply_devices'),
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
    # The game's own 100-byte display block goes to SR2.DSP - its file name
    # string renamed, one string for the read and the write - leaving SR2.CFG
    # to the controls text the input DLL keeps from byte 0; and the registry
    # key is never opened. The Australian MGInput.dll is an older build the
    # annex is not written for, so that release keeps both for now.
    if 'xinput' in site:
        cfgname, regopen = site['noregistry']
        table['noregistry'] = (EXE, (
            (cfgname, b'SR2.CFG', b'SR2.DSP'),
            (regopen, bytes.fromhex('8b45008b0868') + struct.pack('<I', row['addresses']['REGNAMES'][0]) + b'\x68'
             + struct.pack('<I', row['addresses']['REGNAMES'][1]) + bytes.fromhex('50ff510c8bf0'),
             bytes.fromhex('33f6') + b'\x90' * 19)), None)
        # The menus' left and right are the steering's actions 4 and 5, read
        # by several routes, so the annex answers the inputs that keep the
        # menus navigable only while the exe's car table (CARS) is empty: the
        # cars exist from a race's setup to its teardown, whatever the mode.
        # The European and American MGInput.dll hook the device's poll; the
        # Australian, an older build with static polls, the keyboard poll's
        # address in the record update's dispatch (a relocated immediate).
        if len(site['xinput']) == 4:
            load, save, update, poll = site['xinput']
            hook = (poll, bytes.fromhex('8b4424048b480c85c9'), None)
            prologue = bytes.fromhex('538b5c240855')
        else:
            load, save, update, poll, kbdpoll = site['xinput']
            hook = (poll, struct.pack('<I', 0x10000000 + kbdpoll), None)
            prologue = bytes.fromhex('81ec94020000')
        table['xinput'] = ('MUSASHI\\MGInput.dll', (
            (load, bytes.fromhex('81ec0c020000'), None),
            (save, bytes.fromhex('81ec04010000'), None),
            (update, prologue, None),
            hook), 'apply_xinput')
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
TEXRANGE_SECTION = b'.sr2x'
REPLAYFREE_SECTION = b'.sr2g'
ALTENTER_SECTION = b'.sr2k'
MIXERLESS_SECTION = b'.sr2v'
XINPUT_SECTION = b'.sr2p'
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
    'e991070000e9e8090000e917000000e956060000e95b070000e8000000005b81'
    'eb1e000000c353e8edffffff89de5bc3acaa84c075fa4fc331d2b90a000000f7'
    'f10430aa88d00430aac3608dbb100c00008db392110000e8d4ffffff8b4508e8'
    '9c000000c60720478b450ce890000000c60720478b4510e8840000008b751485'
    'f6741583c6046a03c6072047ade86e000000ff0c2475f1588d83100c000050ff'
    '93080c000061c3608dbb100c00008db397110000e877ffffff8b83a4110000e8'
    '3c000000c60720478b83a8110000e82d000000c60720478b83ac110000e81e00'
    '0000c60720478b835e0d0000e80f0000008d83100c000050ff93080c000061c3'
    '53b90a00000031db31d2f7f1524385c075f6580430aa4b75f9c607005bc35152'
    '506affffb34e0d0000ff9384100000588b4c24048983a4110000898ba8110000'
    'ffb3460d0000ff93801000006affffb34a0d0000ff93841000008b83ac110000'
    '50ffb34e0d0000ff938c100000585a59c389c1c1e9080fb6d16bd23cc1e9080f'
    'b6f101f269d2e8030000c1e9086bc928505289c831d2b903000000f7f15a01d0'
    '599125ff000000c35389cb31d2b9e8030000f7f16bd24b5089d031d2f7f189c1'
    '58c1e11831d251b93c000000f7f159c1e21009d1c1e00809c109d989c85bc331'
    'd2b94b000000f7f189d1c1e11031d251b93c000000f7f159c1e20809d009c8c3'
    '8dbb4c0f000003bb040c0000e827feffff8db39f110000e814feffffc3e8f7fd'
    'ffff6affffb3460d0000ff93841000008b83a411000083f801744783f802744e'
    '83f803745083f804745483f805745883f806745c83f807746083f808746231c0'
    '8983ac11000083bb0c0c0000007405e833feffffffb34a0d0000ff9380100000'
    'eba0e82b020000e889000000ebd2e854020000ebcbe8a602000031c0ebc2e85c'
    '03000031c0ebb9e86c03000031c0ebb0e8fd01000031c0eba7e8a9020000eba0'
    'e81203000031c0eb9783bb520d000000753a6a008d83520d0000506a00ff935c'
    '10000089835e0d000085c075226a01ff9360100000508b83520d0000508b08ff'
    '511889835e0d000085c0750331c0c3b815010000c3e8afffffff85c00f854301'
    '00008b83a8110000e8d3feffff6a0068800000006a036a006a0168000000808d'
    '834c0f000050ff936410000083f8ff0f84110100008983620d00006a0050ff93'
    '6810000083e82c0f86f900000083e0fc8983660d000089838e0d00006a006a00'
    '6a2cffb3620d0000ff937010000083f8ff0f84cf0000008d83aa0d0000898396'
    '0d00006a008d83560d0000508d83860d0000508b83520d0000508b08ff510c89'
    '835e0d000085c00f85990000006a008d83760d0000508d83720d0000508d836e'
    '0d0000508d836a0d000050ffb3660d00006a008b83560d0000508b08ff512c89'
    '835e0d000085c0755dffb36e0d0000ffb36a0d0000e857000000ffb3760d0000'
    'ffb3720d0000e846000000ffb3760d0000ffb3720d0000ffb36e0d0000ffb36a'
    '0d00008b83560d0000508b08ff514ce842000000e87e010000c7835a0d000000'
    '00000031c0c3e847000000b815010000c38b44240885c0741a6a008d8b7a0d00'
    '005150ff742410ffb3620d0000ff9374100000c208008b83620d000085c07411'
    '50ff936c100000c783620d000000000000c3e8dfffffff8b83560d000085c074'
    '1be88d0100008b83560d0000508b08ff5108c783560d000000000000c7835a0d'
    '000000000000c383bb560d000000744a8b83a811000069c07203000031d2b905'
    '000000f7f183e0fc3b83660d000072098b83660d000083e804508b83560d0000'
    '508b08ff513489835e0d000085c0750ae8f200000085c07501c3b815010000c3'
    '83bb560d000000741de8050100006a008b83560d0000508b08ff5134c7835a0d'
    '000000000000c331c083bb560d000000746483bb5a0d000001752b8d837e0d00'
    '00508b83560d0000508b08ff512485c07514f7837e0d00000100000075088b83'
    '660d0000eb1f6a008d837e0d0000508b83560d0000508b08ff511085c075158b'
    '837e0d0000b9c8000000f7e1b9d0890000f7f1c331c0c383bb560d000000740b'
    'ffb3700c0000e801000000c3ff7424048b83560d0000508b08ff513cc2040083'
    'bb5a0d000001750fe846000000c7835a0d000002000000c383bb5a0d00000275'
    '05e801000000c3e8abffffff6a006a006a008b83560d0000508b08ff51308983'
    '5e0d000085c0750ac7835a0d000001000000c368f0d8ffffe88fffffff8b8356'
    '0d0000508b08ff5148c353e8a9f9ffff8b44240c85c00f84f200000083780800'
    '0f84e80000008b400c3d102700007605b8102700008b542410f7c24000000075'
    '26f7c200000080741385c00f849500000031d2b984030000f7f1eb143d102700'
    '00743e89c1eb4c31d2b94c040000f7f183f8097605b809000000b9f0d8ffff85'
    'c0740c69c05e0100008d88bef1ffff898b740c0000c783780c000000000000eb'
    '54c783780c0000010000008b8b740c0000eb4283bb780c000000745289c831d2'
    'b964000000f7f10fbf84437c0c00008b8b740c000001c181f9f0d8ffff7d16b9'
    'f0d8ffffeb0fc783780c000000000000b9f0d8ffff898b700c000083bbf40b00'
    '0000740ab808000000e8b0f9ffff31c05bc20c008b44240885c07415c7400802'
    '000000c7400c10270000c740101027000031c0c20c005589e5535657e878f8ff'
    'ff83bb0c0c0000007405e89bf8ffff8b450c3d03080000753e83bbf40b000000'
    '0f84200200008b4d1081e10030000081f9003000000f850b0200008b5514817a'
    '08040200000f85fb010000c74204cefa0000e9e6010000817d08cefa00000f85'
    'e20100003d0408000074373d0608000074763d070800000f84f40000003d0808'
    '000074373d09080000743f3d5508000074473d140800000f8417010000e99b01'
    '0000b806000000e889010000c783fc0b000000000000e982010000b803000000'
    'e870010000e973010000b804000000e861010000e964010000b805000000e852'
    '010000e9550100008b8b000c00008b83f80b0000f7451004000000740b8b5514'
    '8b4204e8c9f8ffffc783000c00000000000085c074513b83f40b0000774983bc'
    '83bc0d000000743f8983f80b0000c783fc0b0000000000005189c1b801000000'
    'e839f8ffff5985c00f85f1000000c783fc0b000001000000b802000000e81cf8'
    'ffffe9d8000000b812010000e9ce000000f74510080000000f84bf0000008b55'
    '148b4204e848f8ffff898b000c000083bbfc0b00000074113b83f80b000074b8'
    '403b83f80b000074af8983f80b0000e9890000008b5514c7420400000000f745'
    '100001000074768b420883f803740c83f801741283f8027432eb628b83f40b00'
    '00894204eb57f7451010000000744e8b420c83f86377468b8483bc0d0000e83c'
    'f8ffff8b5514894204eb3231c083bbfc0b000000740cb80700000031c9e85cf7'
    'ffff8b8bf80b0000e8dbf7ffff8b5514894204eb0831c9e842f7ffffc331c05f'
    '5e5b5dc210008b83e2e2e2e25f5e5b5dffe0837c2408010f85e201000060e816'
    'f6ffff83bbf00b0000000f85ce010000c783f00b0000010000008db390100000'
    '8dbb5c100000803e00743656ff93e3e3e3e385c00f84a401000089c5ac84c075'
    'fb803e0074185655ff93e4e4e4e485c00f8488010000abac84c075fbebe346eb'
    'c58d83671100005055ff93e4e4e4e48983080c000068040100008d834c0f0000'
    '506a00ff93e5e5e5e585c00f844d0100008dbb4c0f000001c74f803f5c75fa47'
    '578db386110000e884f5ffff6a0068800000006a036a006a0168000000808d83'
    '4c0f000050ff936410000083f8ff741a50ff936c10000083bb080c000000740a'
    'c7830c0c0000010000005f8db37a110000e83af5ffff29df81ef4c0f000089bb'
    '040c0000bd0200000089e8e8f0f6ffff6a0068800000006a036a006a01680000'
    '00808d834c0f000050ff936410000083f8ff742f89c76a0057ff936810000050'
    '57ff936c1000005883e82c761631d2b930090000f7f18984abbc0d000089abf4'
    '0b00004583fd6376a06a006a006a00ff938810000089834e0d000085c074556a'
    '006a006a006a00ff937c1000008983460d00006a006a006a006a00ff937c1000'
    '0089834a0d00006a006a006a008d831d020000506a006a00ff937810000085c0'
    '741283bb460d000000740983bb4a0d000000750ac783f40b0000000000006153'
    'e834f4ffff8d83e1e1e1e15bffe0909000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '00000000000000000000000000000000000000000000000000000000f0d860f0'
    'baf21af414f5d6f574f6faf66ef7d4f730f883f8cef814f954f990f9c8f9fdf9'
    '2ffa5efa8afab4faddfa03fb28fb4cfb6efb8ffbaefbcdfbeafb07fc22fc3dfc'
    '57fc70fc89fca0fcb8fccefce4fcfafc0efd23fd37fd4afd5efd70fd82fd94fd'
    'a6fdb7fdc8fdd9fde9fdf9fd08fe18fe27fe36fe44fe53fe61fe6ffe7cfe8afe'
    '97fea4feb1febefecafed7fee3feeffefafe06ff12ff1dff28ff33ff3eff49ff'
    '54ff5eff69ff73ff7dff87ff91ff9bffa4ffaeffb8ffc1ffcaffd3ffddffe6ff'
    'eefff7ff00000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000002400000088800100000000000000000000000000000000000000'
    '000000000000000000000100020044ac000010b1020004001000000000000000'
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
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000064736f756e642e646c6c004469726563'
    '74536f756e6443726561746500007573657233322e646c6c004765744465736b'
    '746f7057696e646f7700006b65726e656c33322e646c6c004372656174654669'
    '6c65410047657446696c6553697a6500436c6f736548616e646c650053657446'
    '696c65506f696e746572005265616446696c6500437265617465546872656164'
    '004372656174654576656e7441005365744576656e740057616974466f725369'
    '6e676c654f626a656374004372656174654d75746578410052656c656173654d'
    '757465780000004f75747075744465627567537472696e6741006d757369635c'
    '747261636b006d757369635c7472616365007372322000737232206f7020002e'
    '77617600000000000000000000000000'
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
TEXRANGE_BLOB = bytes.fromhex(
    'e8000000005a81ea0500000081eae7e7e7e78b4c24043b8a9025010073138b82'
    '80250100568b74240881c23a440000ffe231c0c20400'
)
REPLAYFREE_BLOB = bytes.fromhex(
    'e905000000e92c000000e8000000005981e90f00000089ca81eae7e7e7e781c2'
    'ebbd000051ff742408ffd283c4045989816c000000c35a5052e8000000005981'
    'e93e0000003b816c000000751ec7816c0000000000000089ca81eae7e7e7e781'
    'c2e0bd000050ffd283c404c300000000'
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
DEVICES_BLOB = bytes.fromhex(
    'e918000000e9c0000000e8000000005b81eb0f00000081ebd1d1d1d1c35357e8'
    'e6ffffff8dbbd1d1d1d1c787710b000000002044c787790b000000000000c787'
    '7d0b000000000000c787810b000000000000c787850b000010000000c787890b'
    '000000000000c787950b000000000000c787990b000000000000c787a90b0000'
    '0000000083bf6d0b0000007523c7876d0b0000010000008d83d8d8d8d8508d83'
    'd9d9d9d9508d83d3d3d3d3ffd083c4088d83dededede80780f0074095589fde8'
    '940900005dff46085f5b535755e838ffffff8dabd1d1d1d18dbbdadadada8b07'
    '85c00f84c60100008b4f0c898d9d0b0000c785a10b00000000803fe875010000'
    '734980f905724483bd950b000000740b80f9060f8454010000eb0980f9070f84'
    '490100008b8d890b0000898da10b0000d9470cd8a5910b0000d88d890b0000d8'
    '85910b0000d99d9d0b000083f8020f84a20000006a006a006a00e81601000073'
    '5280f905734d80f901751983bd950b000000752b6a006a006800010000680001'
    '0000eb3b31d280f90375068b95810b0000525268000100006800010000eb208b'
    '95810b0000680001000052526800010000eb0cff7720ff771cff7718ff7714ff'
    'b5a10b0000680000803f6a006a006a00ff7710ffb59d0b000050d94708d88571'
    '0b0000d91c24ff77048d83d4d4d4d4ffd083c440eb77ff77108d83dcdcdcdc50'
    'e870000000732480f904751f8b85810b0000d1f8058000000068000100006800'
    '010000680001000050eb0cff7720ff771cff7718ff7714ffb5a10b0000680000'
    '803f68000020416800002041ffb59d0b000050d94708d885710b0000d91c24ff'
    '77048d83dbdbdbdbffd083c43483c728e969feffff508b4f2485c9742e0fb6c1'
    '4839857d0b00007c220fb6c54839857d0b00007f16c1e91080f903750b0fb6c5'
    '3985990b0000750358f9c358f8c38b85850b00000385810b00008985810b0000'
    '3d000100007e14c785810b000000010000c785850b0000f0ffffff85c07914c7'
    '85810b000000000000c785850b00001000000083bd790b000000757b8b85710b'
    '000085c0742fd985710b0000d8a5750b0000d99d710b00008b85710b000085c0'
    '0f8fa5020000c785710b000000000000e9960200008b85890b00003d0000803f'
    '0f8398000000d985890b0000d8858d0b0000d99d890b000081bd890b00000000'
    '803f0f8263020000c785890b00000000803fe9540200008b85890b000085c074'
    '2fd985890b0000d8a58d0b0000d99d890b00008b85890b000085c00f8f2a0200'
    '00c785890b000000000000e91b020000d985710b0000d8a5750b0000d99d710b'
    '000081bd710b0000000020c40f82f9010000c7460801000000e9ed0100008b83'
    'd6d6d6d68b480885c90f84dc0100008b116a01ff521489c783bd950b0000000f'
    '8593010000f6c40474128b857d0b0000403ddddddddd7e1731c0eb13f6c40274'
    '238b857d0b0000487905b8dddddddd89857d0b0000b80e000000e876010000e9'
    '87010000f7c7020000000f854f0100008b857d0b00003ddddddddd755bf7c700'
    '180000741683b5990b000001b80e000000e83f010000e950010000f7c7410000'
    '000f8444010000b80f000000e82401000083bd990b0000010f840b0100008d83'
    'dededede80780f000f841d010000e8e3040000e9130100008d83dededede8078'
    '0f000f8403010000e84302000081fafe000000743c81faff000000745bf7c741'
    '0000000f84e2000000e872020000c785950b000001000000c785a50b00000000'
    '0000b80f000000e8a9000000e9ba000000f7c7411800000f84ae00000083b5a9'
    '0b000001e82f050000b80e000000e882000000e993000000f7c7001800000f84'
    '87000000508d04c5000000008d04c53f030000e861010000f7c700080000740b'
    '2df4010000791531c0eb1105f40100003d282300007605b828230000e8980400'
    '0058e812010000e8cc040000b80e000000e81f000000eb33e805020000eb2cb8'
    '10000000e80c000000c785790b000001000000eb168b8bd7d7d7d76a006a006a'
    '00508d83d5d5d5d5ffd0c38d83d2d2d2d25d5f5bffe08b83d6d6d6d68b40088b'
    '4004c385c0740a50518b0850ff51085958c351526a0089c189e2e8d7ffffff52'
    '51508b00ff5034585a59c356578bb0240100008b0639f0744f8b7808398f0c01'
    '0000753d83bf38010000007434508b873c0100003d00010000721a2d00030000'
    '3d80000000731ea9200000007517b801000000eb0231c039d058750589f85f5e'
    'c38b00ebb058ebf931c05f5ec351525689d60fb68c0bdedededee873ffffff85'
    'c074125089f2e880ffffff89c658e850ffffff89f05e5a59c3505152e851ffff'
    'ff5a85c07410506a0152508b08ff513058e82dffffff5958c351526a008b0ddf'
    'dfdfdf85c9740889e26a005250ffd1585a59c351526a006a00e8f8feffff8d54'
    '2404526a006a03508b08ff51208b44240485c0741489e26a0052508b08ff5138'
    '8b442404e8dafeffff5883c4045a59c38b85a90b00008b8d7d0b0000bafe0000'
    '0085c97409490fb6940bdedededec3518d0cc5000000008d04cd000300005901'
    'c8e873ffffff83f912720c3d881300000f97c00fb6c0c385c00f95c00fb6c0c3'
    '50515657e86affffff8dbdc50b0000b94000000085c0740689c6f3a5eb0431c0'
    'f3abe889ffffff31c950e8a0ffffff88840dc50c0000584183f91a72ec5f5e59'
    '58c35156e82affffff85c0744889c6f6460180740e80bdc60b0000007505e987'
    '000000b902000000f6040e80741680bc0dc50b000000751489c8e8ba000000e9'
    '88000000c6840dc50b0000004181f90001000072d3e816ffffff31c983f90474'
    '2650e828ffffff85c058741380bc0dc50c000000751189c8e8f4000000eb4dc6'
    '840dc50c0000004183f91a72cfb904000000e8f8feffff85c07425ff85a50b00'
    '0083bda50b00003c7236c785950b000000000000b810000000e825000000eb20'
    'c785a50b000000000000eb14c785950b000000000000b80f000000e803000000'
    '5e59c38b8bd7d7d7d76a006a006a00508d83d5d5d5d5ffd0c35152565789c6e8'
    '6cfeffff31d2e8c2fdffff85c0745d89c78b873c0100008985b90b000031c031'
    'c931d250e8a4fdffff85c0741839f8741439b03c010000750c8b95b90b000089'
    '903c010000584183f90872d54083f80272cd89b73c01000031c031d2e898fdff'
    'ff40e892fdffffe84c0100005f5e5a59c35152565789c6e8f4fdffff508d04c5'
    '000000008d04c50003000001c658ba01000000e835fdffff85c0745589c78b87'
    '3c0100008985b90b0000e8c1fdffff31c9ba0100000050e811fdffff85c07418'
    '39f8741439b03c010000750c8b95b90b000089903c010000584183f90872d289'
    'b73c01000031d2e80dfdffffe8c70000005f5e5a59c3505152565731c031c98d'
    '34c50000000001ce8db4b3dededede83c61031d250e8b3fcffff85c074090fb7'
    '1689903c0100008b0424ba01000000e899fcffff85c074188b1424c1e20681c2'
    '000300000fb77e0201fa89903c010000584183f90872a850b8e8030000e81700'
    '000058e891fcffff4083f802728fe8450000005f5e5a5958c35051568db5bd0b'
    '000066c706445a83c602b9e803000031d2f7f104308806465289c831d2b90a00'
    '0000f7f189c15885c975e4c606008d95bd0b00005e5958c350515256578b85a9'
    '0b000031c950518d3c09c1e7048dbc3bdededede83c75031d2e8effbffff31f6'
    '85c074070fb6b03c0100008d34768db4b3dededede81c690020000e8b9000000'
    '8b4424048b0c24ba0100000083c710e8b9fbffff89c685c0741b8bb63c010000'
    '83e63f8d34768db4b3dededede81c6900e0000eb0c8db3dededede81c6900200'
    '00e87300000059584183f9080f8273ffffff8dbbdededede81c750010000508d'
    '04c5000000008d04c53f030000e8a7fbffff31d2b964000000f7f1b90a000000'
    '31d2f7f185c07405043088074780c2308817c6470100588dbbdededede81c770'
    '0100008db5ad0b0000e80b00000004318847075f5e5a5958c3515657b9030000'
    '00f3a5c707000000005f5e59c300000000000000000000204200000000000000'
    '00000000000000000000000000cdcccc3d0080e1430000000000000000000000'
    '00000000000000000000000000504c4159455220310000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000'
)
PADINPUT_BLOB = bytes.fromhex(
    'e923000000e980000000e948070000e922080000e975080000e9ba080000e800'
    '0000005b83eb23c3535657e8eeffffffe8350200008b742414e834010000723f'
    '31c9837c2418007524e8330100008b7c241c85ff74173b4c242076048b4c2420'
    '516bc90d8db3c8280000f3a5598b54242485d27402890a31c05f5e5bc21800b8'
    '570007805f5e5bc21800535657e88cffffffe8d30100008b742414e8d2000000'
    '0f82c100000089c78b74241885f6742266813e445a751b83c602e85b0400003d'
    '102700007605b8102700008984bbc02000006bc7348d941858200000b90d0000'
    '0066c702000066c74202ff0083c2044975ef8b74241c8b4c242085c9745c8b06'
    '83f80d734f6bd7348d14828d9413582000008b46143d00010000730f85c07434'
    '66833a00752e668902eb293d0003000072223d80030000731b66817a02ff0075'
    '1383e03f83f83f740ba92000000075046689420283c63449eba0e8d903000031'
    'c05f5e5bc21400b8570007805f5e5bc214000fb60683e83083f8017702f8c3f9'
    'c35256575589c58dbbc82800006bf0348db4335820000031c931d2520fb70651'
    '89d1e88c00000059410fb746023dff000000740fe86b0000005189d1e8720000'
    '0059415a83c6044283fa0d72ce6bf5088db4332420000031d20fb70605000400'
    '00510fb68c1351200000e844000000594183c6024283fa0472df8db334200000'
    'ba080000000fb64601e816000000510fb60ee81c000000594183c6024a75e65d'
    '5f5e5ac35189e9c1e10601c8050003000059c3515089c8ab31c083f902721383'
    'f905770eb80a000000abb803000000abeb02abab31c0abb810270000ab58ab31'
    'c0b907000000f3ab59c383bbb00b0000000f859c00000060e8d9070000c783b0'
    '0b0000010000008d4319a3edededed8db3bc1f00008dbb58200000b91a000000'
    'f3a5c783c0200000e8030000c783c4200000e80300006a036800000080e82804'
    '000083f8ff744b89c68d83c82000006a008d8bc00b00005168ff0700005056ff'
    '93940b000056ff93a00b00008b83c00b0000c68418c82000000031c081bbc820'
    '0000646973707505b864000000e80200000061c38db418c8200000c783b80b00'
    '00ffffffffe895010000750e803e000f844a010000e933010000803e5b756cc7'
    '83b80b0000ffffffff0fb6460183e83183f8010f8714010000807e02500f850a'
    '0100008983bc0b000089fee84f0100000f84f7000000c783b80b000001000000'
    '803e430f84e4000000c783b80b000000000000803e4b0f84d1000000c783b80b'
    '0000ffffffffe9c200000083bbb80b0000ff0f84b500000083f9087544813e44'
    '656164753c817e047a6f6e65753383bbb80b0000010f859200000089fee8b400'
    '00000f8485000000e82d010000e8bd0000008b93bc0b0000898493c0200000eb'
    '6c8d93ec1e00006a0de8d7000000785d5089fee87e000000745083bbb80b0000'
    '01741d8d93ec0c00006800010000e8b200000078355ae845000000668906eb2d'
    'b8ff00000083f9017505803e2d740f8d93ec1c00006a20e889000000780c5ae8'
    '1c00000066894602eb0383c40489fe8a0684c0740a463c0a75f5e9a6feffffc3'
    '508bb3bc0b00006bf6348d34968db4335820000058c3e824000000741183f901'
    '750c803e3d750789fee811000000c36bc0643d282300007605b828230000c331'
    'c98a063c2074083c0974043c0d750346ebef89f78a0784c074083c2076044741'
    'ebf285c9c356575189d731c05657518a163a17750f46474975f5803f00750559'
    '5f5eeb10595f5e83c710403b44241072db83c8ff595f5ec2040031c0803e2075'
    '0346ebf80fb61683ea3083fa0977086bc00a01d046ebedc360e8180500008dbb'
    'c82000008db3ae060000e82e01000031edc783b80b000001000000b00aaab05b'
    'aa8d4531aab050aab020aa8db3c706000083bbb80b00000174068db3d2060000'
    'e8f8000000b05daab00aaa83bbb80b000001751a8db3db060000e8de0000008b'
    '84abc0200000e8db000000b00aaa31d20fb68413442000003dff000000746b50'
    'c1e0048db418ec1e0000e8ae0000008db3e6060000e8a3000000586bf5348d34'
    '868db4335820000083bbb80b00000175210fb746023dff0000007505b02daaeb'
    '23c1e0048db418ec1c0000e86d000000eb120fb706c1e0048db418ec0c0000e8'
    '59000000b00aaa42eb86ff8bb80b00000f8925ffffff4583fd020f8211ffffff'
    '8db3c820000029f76a0468000000c0e89600000083f8ff742289c56a008d8bc0'
    '0b000051575655ff93980b000055ff93a80b000055ff93a00b000061c3ac84c0'
    '7403aaebf8c35152b96400000031d2f7f1b220881747b90a00000031d2f7f185'
    'c074030430aa88d00430aa5a59c33b20534547412052414c4c59203220636f6e'
    '74726f6c730a00436f6e74726f6c6c6572004b6579626f61726400446561647a'
    '6f6e65203d00203d200056578dbbe80b00006804010000576a00ff93a40b0000'
    '89fe8a0784c07409473c5c75f589feebf1c7065352322ec74604434647006a00'
    '6880000000ff7424186a006a03ff7424208d83e80b000050ff93900b000083f8'
    'ff740f506a006a006a0050ff939c0b0000585f5ec2080060e8c1f8ffff8d83e6'
    'e6e6e68944241c8b4424240fb6700c83ee3083fe01771485f6750ba1e9e9e9e9'
    '8983b40b0000e80900000061c1c1c1c1c1c1ffe0e8bd0200008b83ac0b000083'
    'f80176670fb68c33c40b000085c9741c49e86b00000085c07466c68433c40b00'
    '0000c68433c60b00003ceb3ffe8c33c60b00007936c68433c60b00003c31c98d'
    '41018d56fff7da3a8413c40b00007415e82c00000085c0750c8d4101888433c4'
    '0b0000eb1b4183f90472d48dbbcc0b00006bc61001c731c08907894704894708'
    'c3516bc6108d8418c80b00005051ff93ac0b000059c3535657e8e0f7ffff8b44'
    '241031d280b8600200000375068b90080300008b4c2414e8b4000000731c8b4c'
    '241c85c9740289118b4c241885c97402890131c05f5e5bc210008d93e8e8e8e8'
    '5f5e5bc2c2c2c2c2c2c2c2c2ffe2535657e888f7ffff8b44241031d280780803'
    '75048b5424148b4c2418e861000000731c8b4c242085c9740289118b4c241c85'
    'c97402890131c05f5e5bc214008d83ecececec5f5e5bffe0535657e83ef7ffff'
    '8b4c241031d2e825000000720731c0ba800000008b4c241885c9740289118b4c'
    '241485c97402890131c05f5e5bc20c0081e90003000081f980000000723181e9'
    '0001000081f9000100007202f8c331c085d2741483bbb40b000000750b803c0a'
    '007405b880000000ba80000000f9c389cec1ee0683e13f83f93f741df7c12000'
    '0000741583e1df83bbb40b000000740931c0ba80000000f9c3e802000000f9c3'
    '6bfe108dbc3bc80b000083f93f0f84ae00000083f91073190fb747040fa3c8b8'
    '000000007305b880000000ba80000000c383e91083f90273120fb6440f0683f8'
    '1e730231c0baff000000c383e90283f908737b0fb6944b7c0b00000fbf041780'
    'bc4b7d0b0000007502f7d885c07f0831c0ba10270000c3508b84b3c020000069'
    'c0ff7f0000b91027000031d2f7f189c15829c87f0831c0ba10270000c369c010'
    '270000f7d981c1ff7f000031d2f7f13d102700007605b810270000ba10270000'
    'c38b84b3c0200000ba10270000c331c0ba10270000c383bb8c0b000000757860'
    'c7838c0b0000010000008d83d80a000050ff93e3e3e3e389c68dbb900b00008d'
    'abe50a00005556ff93e4e4e4e4ab45807dff0075f9807d000075ea8dab400b00'
    '0055ff93e3e3e3e385c074128d8b6d0b00005150ff93e4e4e4e485c075124580'
    '7dff0075f9807d000075d6b8010000008983ac0b000061c36b65726e656c3332'
    '2e646c6c0043726561746546696c6541005265616446696c6500577269746546'
    '696c650053657446696c65506f696e74657200436c6f736548616e646c650047'
    '65744d6f64756c6546696c654e616d654100536574456e644f6646696c650000'
    '78696e707574315f342e646c6c0078696e707574315f332e646c6c0078696e70'
    '7574395f315f302e646c6c000058496e70757447657453746174650008000801'
    '0a010a000c000c010e010e000000000000000000000000000000000000000000'
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
    '000000000000000000000000'
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
DEVICES_MAGICS = {
    'SELFRVA': 0xD1D1D1D1,
    'EPILOGUE': 0xD2D2D2D2,
    'BINDPAGE': 0xD3D3D3D3,
    'DRAW': 0xD4D4D4D4,
    'PLAYSOUND': 0xD5D5D5D5,
    'INPUT': 0xD6D6D6D6,
    'SOUNDOBJ': 0xD7D7D7D7,
    'HANDLES': 0xD8D8D8D8,
    'PAGEHDR': 0xD9D9D9D9,
    'DRAWLIST': 0xDADADADA,
    'TEXT': 0xDBDBDBDB,
    'GLYPHS': 0xDCDCDCDC,
    'ROWS': 0xDDDDDDDD,
    'BINDDATA': 0xDEDEDEDE,
    'PADPOLL': 0xDFDFDFDF,
}
PADINPUT_MAGICS = {
    'LOADLIB': 0xE3E3E3E3,
    'GETPROC': 0xE4E4E4E4,
    'UPDATE': 0xE6E6E6E6,
    'POLL': 0xE8E8E8E8,
    'CARS': 0xE9E9E9E9,
    'KBDPOLL': 0xECECECEC,
    'PUBLISH': 0xEDEDEDED,
}
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


# The bind store, as padinput.asm keeps it: SR2.CFG as text, a section a
# player and device of "Name = value" lines for the eight driving actions
# and "Deadzone = 10" in percent, names as below with spaces as
# underscores. The annex generates the game's 0x34-byte records from it.
# Pad sources are 0x300 + player * 0x40 + input.
PAD_BASE = 0x300
PAD_PLAYER = 0x40
PAD_DEADZONE = 1000
# the pad inputs, by index
PAD_UP, PAD_DOWN, PAD_LEFT, PAD_RIGHT, PAD_START, PAD_BACK, PAD_LS, PAD_RS, PAD_LB, PAD_RB = range(10)
PAD_A, PAD_B, PAD_X, PAD_Y, PAD_LT, PAD_RT = 12, 13, 14, 15, 16, 17
PAD_LS_LEFT, PAD_LS_RIGHT, PAD_LS_UP, PAD_LS_DOWN = 18, 19, 20, 21
# the actions: 0 accel, 1 brake, 2 up, 3 down, 4 left, 5 right, 6 shift up,
# 7 shift down, 8 handbrake, 9 view, 10 enter, 11 escape, 12 start (the
# race's pause, a confirm in the menus). 2-5 repeat.
# the driving actions by name; the menus' (2, 3, 10, 11, 12) have none
# and are fixed
ACTION_NAMES = ('Accelerate', 'Brake', '', '', 'SteeringLeft', 'SteeringRight', 'ShiftUp', 'ShiftDown',
                'Handbrake', 'View', '', '', '')
TEXT_ORDER = (4, 5, 0, 1, 6, 7, 8, 9)   # the actions as the text lists them
# the exe's own keyboard table (Type A), and the manual's for player 2
KEYS_1P = {0: 0x2d, 1: 0x2e, 2: 0xc8, 3: 0xd0, 4: 0xcb, 5: 0xcd, 6: 0xd0, 7: 0xc8, 8: 0x39, 9: 0x2f, 10: 0x1c, 11: 0x01, 12: 0x1c}
KEYS_2P = {0: 0x11, 1: 0x1f, 2: 0x11, 3: 0x1f, 4: 0x1e, 5: 0x20, 6: 0x30, 7: 0x31, 8: 0x23, 9: 0x15, 10: 0x39, 11: 0x31, 12: 0x39}
PAD_DEFAULT = {0: PAD_RT, 1: PAD_LT, 2: PAD_UP, 3: PAD_DOWN, 4: PAD_LS_LEFT, 5: PAD_LS_RIGHT, 6: PAD_A, 7: PAD_X, 8: PAD_B, 9: PAD_Y,
               10: PAD_A, 11: PAD_B, 12: PAD_START}
# what the menus keep whatever is bound: keys per player and pad inputs
# on actions 2-5. Left and right are the steering's actions, so those
# are menu-only - a scancode at MENUKEY_BASE, a pad input with MENU_ONLY
# set - answered only outside a race; up and down are nobody else's and
# stay plain, for the pause menu.
MENU_ONLY, MENUKEY_BASE = 0x20, 0x400
FIXED_ACTIONS = (2, 3, 4, 5)
FIXED_KEYS = ((0xc8, 0xd0, 0xcb, 0xcd), (0x11, 0x1f, 0x1e, 0x20))
FIXED_PADS = ((2, PAD_UP), (3, PAD_DOWN), (4, PAD_LEFT | MENU_ONLY), (5, PAD_RIGHT | MENU_ONLY),
              (2, PAD_LS_UP), (3, PAD_LS_DOWN), (4, PAD_LS_LEFT | MENU_ONLY), (5, PAD_LS_RIGHT | MENU_ONLY))
ANNEX_NAME = 16
ANNEX_TABLES, ANNEX_END = 4972, 9180    # the tables' size and the working area's end, as padinput.asm lays them out


def annex_tables():
    """The name tables and defaults after padinput.asm's code."""
    out = bytearray(ANNEX_TABLES)

    def names(offset, table):
        for i, name in enumerate(table):
            name = name.replace(' ', '_').encode('ascii')
            out[offset + i * ANNEX_NAME:offset + i * ANNEX_NAME + len(name)] = name
    names(0, [KEY_NAMES.get(code, 'KEY %d' % code) for code in range(256)])
    names(4096, PAD_NAMES)
    names(4608, ACTION_NAMES)
    for player, keys in enumerate((KEYS_1P, KEYS_2P)):
        for action in range(13):
            struct.pack_into('<HH', out, 4816 + (player * 13 + action) * 4, keys[action], PAD_DEFAULT[action])
        struct.pack_into('<4H', out, 4920 + player * 8, *FIXED_KEYS[player])
    for i, (action, pad) in enumerate(FIXED_PADS):
        out[4936 + i * 2], out[4936 + i * 2 + 1] = action, pad
    out[4952:4952 + len(TEXT_ORDER) + 1] = bytes(TEXT_ORDER) + b'\xff'
    out[4965:4965 + 4] = bytes(FIXED_ACTIONS)
    return bytes(out)


def annex_records(player, table=None):
    """The records the annex generates for a player from a table of
    (key, pad input or None) per action - the defaults when none - in the
    order it lays them out."""
    if table is None:
        keys = (KEYS_1P, KEYS_2P)[player]
        table = [(keys[a], PAD_DEFAULT[a]) for a in range(13)]

    def record(action, source):
        delay, rate = (10, 3) if 2 <= action <= 5 else (0, 0)
        return struct.pack('<13I', action, delay, rate, 0, 10000, source, 0, 0, 0, 0, 0, 0, 0)
    out = []
    for action, (key, pad) in enumerate(table):
        out.append(record(action, key))
        if pad is not None:
            out.append(record(action, PAD_BASE + player * PAD_PLAYER + pad))
    for action, key in zip(FIXED_ACTIONS, FIXED_KEYS[player]):
        out.append(record(action, MENUKEY_BASE + key))
    for action, pad in FIXED_PADS:
        out.append(record(action, PAD_BASE + player * PAD_PLAYER + pad))
    return out


def annex_text(tables=None, deadzones=(PAD_DEADZONE, PAD_DEADZONE)):
    """The text the annex writes, as it lays it out: for the defaults, or
    for a (key, pad input or None) per action per player."""
    defaults = [[(keys[a], PAD_DEFAULT[a]) for a in range(13)] for keys in (KEYS_1P, KEYS_2P)]
    tables = [t or defaults[i] for i, t in enumerate(tables or (None, None))]
    lines = ['; SEGA RALLY 2 controls']
    for player, table in enumerate(tables):
        for device in ('Controller', 'Keyboard'):
            lines += ['', '[%dP %s]' % (player + 1, device)]
            if device == 'Controller':
                lines.append('Deadzone = %d' % (deadzones[player] // 100))
            for action in TEXT_ORDER:
                key, pad = table[action]
                name = KEY_NAMES[key] if device == 'Keyboard' else ('-' if pad is None else PAD_NAMES[pad])
                lines.append('%s = %s' % (ACTION_NAMES[action], name.replace(' ', '_')))
    return ''.join(line + '\n' for line in lines).encode('ascii')


def apply_xinput(buf, build):
    """padinput.asm in MGInput.dll, its tables and working area after the
    code: the registry helper's load and save and the config's update each
    jump to it, their displaced bytes copied into its replay slots; the
    device's poll too on the European and American build, while on the
    Australian the keyboard poll's address in the record update's dispatch
    is pointed at the annex's five-argument entry."""
    sites = BUILDS[build]['sites']['xinput']
    load, save, update, poll = sites[:4]
    blob = PADINPUT_BLOB + annex_tables() + b'\0' * (ANNEX_END - ANNEX_TABLES)
    out, rva = append_section(buf, XINPUT_SECTION, blob, chars=CODE_SECTION | 0x80000000)
    values = {
        'LOADLIB': _iat_slot(buf, 'kernel32.dll', 'LoadLibraryA'),
        'GETPROC': _iat_slot(buf, 'kernel32.dll', 'GetProcAddress'),
        'UPDATE': _off_to_rva(buf, update + 6),
        'POLL': _off_to_rva(buf, poll + 9) if len(sites) == 4 else 0,
        'KBDPOLL': sites[4] if len(sites) == 5 else 0,
    }
    code = bytearray(PADINPUT_BLOB)
    for name, magic in PADINPUT_MAGICS.items():
        if name in ('CARS', 'PUBLISH'):
            code = code.replace(struct.pack('<I', magic), struct.pack('<I', BUILDS[build]['addresses'][{'CARS': 'CARS', 'PUBLISH': 'PADPOLL'}[name]]))
        else:
            code = code.replace(struct.pack('<I', magic), struct.pack('<i', values[name] - rva))
    for marker, site, length in ((b'\xc1' * 6, update, 6), (b'\xc2' * 9, poll if len(sites) == 4 else None, 9)):
        if code.count(marker) != 1:
            raise ValueError('padinput.asm: the replay slot %s is not there once' % marker.hex())
        code = code.replace(marker, bytes(buf[site:site + length]) if site is not None else b'\x90' * length)
    start = _rva_to_off(out, rva)
    out[start:start + len(code)] = code
    for off, entry, length in ((load, 0, 6), (save, 5, 6), (update, 10, 6)):
        _branch(out, off, rva + entry, length, op=b'\xe9')
    if len(sites) == 4:
        _branch(out, poll, rva + 15, 9, op=b'\xe9')
    else:
        struct.pack_into('<I', out, poll, 0x10000000 + rva + 20)
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


DEVICES_SECTION = b'.sr2d'
DATA_SECTION = 0xC0000040               # IMAGE_SCN_CNT_INITIALIZED_DATA | MEM_READ | MEM_WRITE
DEVICES_X = (110.0, 250.0, 390.0, 530.0)   # four items across 640, stock 154, 320, 487
DEVICES_UV_DEVICE = 0xe                 # spare entries in the page's UV table: "DEVICE" on sheet 6,
DEVICES_UV_ICON = 0x11                  # and the icon on the appended sheet
DEVICES_DEVICE = (0.008, 0.286, 0.309, 0.372)   # "DEVICE" on sheet 6, in the page's three-decimal UVs, the row "SOUND" uses
# The page, in the Game Settings page's terms: its group and row plates
# and header band are the stock sprites themselves, found by their first
# quad; text is the stock routine over its 14-px glyph sprites, which lack
# a colon, so that is a piece. The hint bar is the frame's bar without
# its lettering, with the page's own two lines on it, set from the
# frame's lettering (HINT_GLYPHS). Colours are (alpha, red, green, blue)
# in 256ths, as the sprite call takes them.
PAGE_PIECES = {'DEVICE': (6, 2, 73, 79, 95), 'SETTINGS': (6, 72, 50, 178, 72), 'COLON': (6, 143, 16, 151, 30)}
PAGE_STOCK = {'group': (2, (0, 0, 183, 18)), 'gsrow': (3, (0, 0, 123, 18)), 'band': (2, (-154, -13, 0, 13)),
              'bar': (7, (-216, -28, -200, 0)), 'default': (1, (-58, -10, 59, 10))}
PAGE_BUTTON_X = (253.0, 386.0)          # DEFAULT and BACK, as the stock pages place them
PAGE_BAR_QUADS, PAGE_BAR_Y, PAGE_STRIP_Y = 5, 451.0, -20.0
# The rows, each an action the page binds a key and a pad input to; the
# last is the player's stick deadzone, which left and right adjust.
PAGE_ACTIONS = (('STEER LEFT', 4), ('STEER RIGHT', 5), ('ACCEL', 0), ('BRAKE', 1), ('SHIFT UP', 6), ('SHIFT DOWN', 7),
                ('HANDBRAKE', 8), ('VIEW', 9), ('DEADZONE', 0xff))
# One player at a time: a selector row - the group plate with PLAYER 1 or
# 2, left and right switching - the KEY and PAD headings, then the nine
# rows, the stock's 18 px, the block centred.
# the rows Graphic Settings' sprite - a 123-px label plate, a 30-px fade, a
# 273-px value plate - at its x, spaced as it spaces them
PAGE_SELECTOR_X, PAGE_SELECTOR_Y = 229.0, 112.0    # the 183-px group plate, centred
PAGE_ROW_X, PAGE_ROW_Y, PAGE_ROW_STEP = 110.0, 156.0, 24.0
PAGE_ACTION_X, PAGE_VALUE_X, PAGE_PAD_X, PAGE_TEXT_DY = 118.0, 271.0, 405.0, 2.0
PAGE_HEADER_Y, PAGE_DIVIDER_X = 136.0, 398.0   # the KEY and PAD headings above the columns; the line between them
PAGE_LABEL_VALUE = 18                    # the value string the selector's label lives in
FLAGS_CENTRED = 2
PAGE_HEADER_COLOUR = (0x100, 0xff, 0xd0, 0xa0)  # (alpha, red, green, blue) in 256ths: a warm off-white
PAGE_DIVIDER_COLOUR = (0x70, 0x100, 0x100, 0x100)
# The page's data block after its strings, at these offsets: the rows'
# action ids, the shipped bindings (key, pad input) a player-row at a
# time, the value strings the page fills, then the key and pad names,
# NAME bytes each. devices.asm reads it through MAGIC_BINDDATA.
NAME = 12
DATA_ROWACTS, DATA_DEFAULTS, DATA_VALUES, DATA_KEYNAMES, DATA_PADNAMES = 0, 16, 16 + 64, 16 + 64 + 2 * 9 * 2 * 16, 16 + 64 + 2 * 9 * 2 * 16 + 256 * NAME
DATA_SIZE = DATA_PADNAMES + 32 * NAME
PAD_NAMES = ('DPAD UP', 'DPAD DOWN', 'DPAD LEFT', 'DPAD RIGHT', 'START', 'BACK', 'LS', 'RS', 'LB', 'RB', '', '',
             'A', 'B', 'X', 'Y', 'LT', 'RT', 'LS LEFT', 'LS RIGHT', 'LS UP', 'LS DOWN', 'RS LEFT', 'RS RIGHT', 'RS UP', 'RS DOWN')
KEY_NAMES = {0x00: '-', 0x01: 'ESC', 0x0e: 'BACKSPACE', 0x0f: 'TAB', 0x1c: 'ENTER', 0x1d: 'LCTRL', 0x2a: 'LSHIFT', 0x36: 'RSHIFT',
             0x37: 'NUM MULT', 0x38: 'LALT', 0x39: 'SPACE', 0x3a: 'CAPS', 0x45: 'NUM LOCK', 0x46: 'SCROLL',
             0x4a: 'NUM MINUS', 0x4e: 'NUM PLUS', 0x53: 'NUM DOT', 0x9c: 'NUM ENTER', 0x9d: 'RCTRL', 0xb5: 'NUM DIV',
             0xb8: 'RALT', 0xc5: 'PAUSE', 0xc7: 'HOME', 0xc8: 'UP', 0xc9: 'PGUP', 0xcb: 'LEFT', 0xcd: 'RIGHT',
             0xcf: 'END', 0xd0: 'DOWN', 0xd1: 'PGDN', 0xd2: 'INSERT', 0xd3: 'DELETE', 0x29: 'GRAVE', 0x0c: 'MINUS',
             0x0d: 'EQUALS', 0x1a: 'LBRACKET', 0x1b: 'RBRACKET', 0x27: 'SEMICOLON', 0x28: 'QUOTE', 0x2b: 'BACKSLASH',
             0x33: 'COMMA', 0x34: 'PERIOD', 0x35: 'SLASH', 0x56: 'OEM 102'}
KEY_NAMES.update({0x02 + i: '%d' % ((i + 1) % 10) for i in range(10)})
KEY_NAMES.update(zip((0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19), 'QWERTYUIOP'))
KEY_NAMES.update(zip((0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26), 'ASDFGHJKL'))
KEY_NAMES.update(zip((0x2c, 0x2d, 0x2e, 0x2f, 0x30, 0x31, 0x32), 'ZXCVBNM'))
KEY_NAMES.update({0x3b + i: 'F%d' % (i + 1) for i in range(10)})
KEY_NAMES.update({0x57: 'F11', 0x58: 'F12'})
KEY_NAMES.update({0x47: 'NUM 7', 0x48: 'NUM 8', 0x49: 'NUM 9', 0x4b: 'NUM 4', 0x4c: 'NUM 5', 0x4d: 'NUM 6',
                  0x4f: 'NUM 1', 0x50: 'NUM 2', 0x51: 'NUM 3', 0x52: 'NUM 0'})


def bind_data(live):
    """The page's data block; live when the build's MGInput carries the
    annex, else the page only shows and its values say so."""
    out = bytearray(DATA_SIZE)
    for i, (_name, action) in enumerate(PAGE_ACTIONS):
        out[DATA_ROWACTS + i] = action
    out[DATA_ROWACTS + 15] = 1 if live else 0
    if not live:
        for i in range(2 * 9 * 2):
            out[DATA_VALUES + i * 16] = ord('-')
        out[DATA_VALUES + PAGE_LABEL_VALUE * 16:DATA_VALUES + PAGE_LABEL_VALUE * 16 + 8] = b'PLAYER 1'
    for player, keys in enumerate((KEYS_1P, KEYS_2P)):
        for r, (_name, action) in enumerate(PAGE_ACTIONS[:8]):
            struct.pack_into('<HH', out, DATA_DEFAULTS + (player * 8 + r) * 4, keys[action], PAD_DEFAULT[action])
    for code in range(256):
        name = KEY_NAMES.get(code, 'KEY %d' % code)
        out[DATA_KEYNAMES + code * NAME:DATA_KEYNAMES + code * NAME + len(name)] = name.encode('ascii')
    for i, name in enumerate(PAD_NAMES):
        out[DATA_PADNAMES + i * NAME:DATA_PADNAMES + i * NAME + len(name)] = name.encode('ascii')
    return bytes(out)
PAGE_BUTTON_Y = 404.0
PLATE, TEXT = (0xd8, 0x100, 0x100, 0x100), (0x100, 0x100, 0x100, 0x100)
HOLD_ROW, HOLD_BUTTON, HOLD_VALUE = 1, 3, 4      # how the cursor draws an entry it is on
HOLD_BAR, HOLD_BAR_IDLE, HOLD_BAR_BIND = 5, 6, 7             # rises with the hint bar; shown outside, or during, a bind
Z_PLATE, Z_TEXT = 14.0, 10.0
FLAGS_PROPORTIONAL = 4                  # the text routine: 4 proportional, +1 right-aligned, +2 centred

# The hint bar's lettering is the stock's own, from sheet 4, where the
# frame's messages keep six lines in their condensed face: one texel box
# a letter, cut from clean instances there (x0, top, x1; the top a row
# above the line's ascenders, so the box is 17 rows and every baseline
# lands on the same row), laid in a row a texel apart, a word gap of 5.
# The lines say what they can with the letters those six offer.
HINT_GLYPHS = {'S': (104, 59, 112), 'H': (49, 59, 57), 'E': (175, 211, 182), 'C': (192, 211, 200),
               'e': (70, 135, 77), 'l': (138, 135, 141), 'c': (31, 135, 37), 't': (14, 135, 18), 'a': (46, 135, 53),
               'n': (54, 135, 61), 'i': (162, 135, 165), 'o': (19, 135, 26), 'd': (103, 135, 109), 'h': (38, 135, 45),
               'k': (148, 173, 155), 'y': (163, 173, 170), 'p': (31, 173, 38), ',': (23, 173, 25),
               'b': (132, 230, 138), 'u': (42, 230, 48), 'r': (156, 230, 160)}
HINT_SPACING, HINT_SPACE, HINT_ROWS, HINT_MARGIN = 1, 5, 17, 2   # the margin: white texels each side, so the edges filter to white
HINT_LINES = ('Select an action and hit the key to bind it', 'Hit the button to bind it, or hit ESC to keep it')
HINT_STRIP_TOPS = (130, 150, 170, 190)  # the lines' two halves each on the appended sheet, from x 1
HINT_SHEET = 4


def hint_layout(line):
    """The line's letters as (x, glyph) from x 0, its width, and how many
    letters make its first half, cut at the space nearest the middle."""
    placed, x, cut, best = [], 0, 0, None
    for i, c in enumerate(line):
        if c == ' ':
            if best is None or abs(i - len(line) / 2) < best:
                best, cut = abs(i - len(line) / 2), len(placed)
            x += HINT_SPACE
            continue
        placed.append((x, HINT_GLYPHS[c]))
        x += HINT_GLYPHS[c][2] - HINT_GLYPHS[c][0] + HINT_SPACING
    return placed, x - HINT_SPACING, cut


TXR = 'BINDATA\\MISC\\OPTIONS.TXR'
TXR_SIZE = 1282048
TXR_ENTRIES = ((2, 128), (0, 128), (8, 256), (8, 256), (0, 256), (0, 256), (8, 256), (2, 256), (8, 256), (8, 256), (8, 256), (8, 128))
TXR_SHEET6_MD5 = 'f753766b79b10186b5af35be7c1c6c98'   # sheet 6's first 96 rows: the font and the labels, English
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


def apply_devices(buf, build):
    """A fourth item on the Options menu. The three item tables (cursor
    frames, icons, labels) move to a new data section with a fourth entry
    each. The item's icon is the sheet patch_txr appends, its label
    "DEVICE" and "SETTINGS" from the page's own sheets, both through spare
    UV entries. Confirming it returns to the menu until the page exists.
    The stock items move to four-across positions."""
    cursor, icons, labels, labelend, dispatch, ftab, topcmp, confirm = BUILDS[build]['sites']['devices']
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
    for entry in (DEVICES_UV_DEVICE, DEVICES_UV_ICON):
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
            struct.pack_into('<f', buf, va_off(tables[t][i]) + 0x14, DEVICES_X[i])
    # the spare UV entries: "DEVICE", and the appended sheet's top-left quarter with the
    # first icon's exact UVs - the page's are rounded to three decimals, and the tenth of
    # a texel that adds shows at the plate's edge
    struct.pack_into('<i4f', buf, uvs[DEVICES_UV_DEVICE], 6, *DEVICES_DEVICE)
    struct.pack_into('<i4f', buf, uvs[DEVICES_UV_ICON], TXR_ICON, *struct.unpack_from('<4f', buf, va_off(page) + dword(va_off(dword(icon0 + 4))) * 0x14 + 4))

    # the menu's blob: tables, descriptors, quads, stub; then the page's
    rva = _next_section_rva(buf)
    va = base + rva
    frame_quads = bytes(buf[va_off(dword(frame0 + 4)):va_off(dword(frame0 + 4)) + 9 * 0x34])
    icon_quad = bytearray(buf[va_off(dword(icon0 + 4)):va_off(dword(icon0 + 4)) + 0x34])
    struct.pack_into('<I', icon_quad, 0, DEVICES_UV_ICON)
    settings = bytes(buf[va_off(dword(label0 + 4)) + 0x34:va_off(dword(label0 + 4)) + 0x68])
    device = struct.pack('<I4f', DEVICES_UV_DEVICE, -38.0, -22.0, 39.0, 0.0) + settings[0x14:]
    layout = {'ftab': 0x00, 'itab': 0x10, 'ltab': 0x20, 'descf': 0x30, 'desci': 0x50, 'descl': 0x70,
              'quadsf': 0x90, 'quadsi': 0x264, 'quadsl': 0x298, 'stub': 0x300, 'page': 0x310}
    blob = bytearray(layout['page'])
    relocs = []
    for t, name in enumerate(('ftab', 'itab', 'ltab')):
        for i in range(3):
            struct.pack_into('<I', blob, layout[name] + i * 4, tables[t][i])
        struct.pack_into('<I', blob, layout[name] + 12, va + layout[('descf', 'desci', 'descl')[t]])
        relocs += [layout[name] + i * 4 for i in range(4)]
    for name, quads, n, w, h, y in (('descf', 'quadsf', 9, 134.0, 134.0, 202.0), ('desci', 'quadsi', 1, 126.0, 126.0, 202.0),
                                   ('descl', 'quadsl', 2, 106.0, 45.0, 296.0)):
        struct.pack_into('<IIIffffI', blob, layout[name], page, va + layout[quads], n, w, h, DEVICES_X[3], y, 0)
        relocs += [layout[name], layout[name] + 4]
    blob[layout['quadsf']:layout['quadsf'] + 9 * 0x34] = frame_quads
    blob[layout['quadsi']:layout['quadsi'] + 0x34] = icon_quad
    blob[layout['quadsl']:layout['quadsl'] + 0x68] = device + settings
    stub_va = va + layout['stub']
    blob[layout['stub']:layout['stub'] + 12] = bytes.fromhex('c74608') + struct.pack('<I', 0xc) + b'\xe9' + struct.pack('<i', base + _off_to_rva(buf, cont) - (stub_va + 12))
    page_blob, page_relocs = devices_page(buf, build, va + layout['page'], settings[0x14:], cont, labelend)
    blob += page_blob
    relocs += [layout['page'] + r for r in page_relocs]
    out, got = append_section(buf, DEVICES_SECTION, bytes(blob), chars=DATA_SECTION | 0x20000000)
    if got != rva:
        raise ValueError('section placed at %#x, expected %#x' % (got, rva))
    _add_relocations(out, [rva + r for r in relocs])

    # the sites: the counts and the state count are written already; the
    # tables, the dispatch entry and the state table here
    struct.pack_into('<I', out, cursor + 4, va + layout['ftab'])
    struct.pack_into('<I', out, icons + 3, va + layout['itab'])
    struct.pack_into('<I', out, labels + 1, va + layout['ltab'])
    struct.pack_into('<I', out, labelend + 2, va + layout['ltab'] + 16)
    struct.pack_into('<I', out, confirm + 3, va + layout['ftab'])
    struct.pack_into('<I', out, stub_site, stub_va)
    struct.pack_into('<I', out, topcmp + 12, va + layout['page'] + len(DEVICES_BLOB))
    return out


def devices_page(buf, build, va, quad_tail, cont, labelend):
    """The Device Settings page after the menu's data at `va`: the code,
    the top-level state table with the page's two states, the page's UV
    table and header, its sprites and quads, the draw list, the strings.
    Returns (bytes, relocation offsets)."""
    row = BUILDS[build]
    base = struct.unpack_from('<I', buf, struct.unpack_from('<I', buf, 0x3c)[0] + 24 + 28)[0]
    opt = row['options']

    def sprite_by_quad(n, rect):
        """A stock sprite with n quads whose first quad has this rectangle."""
        lo, hi = 0x1009c000 if build != 'Australian' else 0x100a1000, 0x10150000
        for cand in range(lo, hi, 4):
            try:
                off = _rva_to_off(buf, cand - base)
            except ValueError:
                return None
            quads, count = struct.unpack_from('<II', buf, off + 4)
            if count == n and lo <= quads < hi:
                try:
                    q = _rva_to_off(buf, quads - base)
                    if tuple(round(v) for v in struct.unpack_from('<4f', buf, q + 4)) == rect:
                        page = _rva_to_off(buf, struct.unpack_from('<I', buf, off)[0] - base)
                        sheet, _u0, v0 = struct.unpack_from('<iff', buf, page + struct.unpack_from('<I', buf, q)[0] * 0x14)
                        if rect != PAGE_STOCK['default'][1] or (sheet == 11 and v0 < 0.1):
                            return cand
                except ValueError:
                    pass
        return None

    stock = {name: sprite_by_quad(*sig) for name, sig in PAGE_STOCK.items()}
    back, off = None, labelend
    for _ in range(0x100):
        if buf[off] == 0x68 and buf[off + 5] == 0xe8:
            back = struct.unpack_from('<I', buf, off + 1)[0]
            break
        off += 1
    if back is None or struct.unpack_from('<I', buf, _rva_to_off(buf, back - base) + 8)[0] != 1:
        raise ValueError('Options.dll: the menu\'s BACK sprite not found')
    if None in stock.values():
        raise ValueError('Options.dll: the Game Settings sprites not found: %s' % [k for k, v in stock.items() if v is None])

    # the page's own sprites: the pieces
    sprites, uvkeys, strings, draw = [], {}, [], []

    def uv(key):
        if key not in uvkeys:
            uvkeys[key] = len(uvkeys)
        return uvkeys[key]

    def piece(key, size=None, top=False):
        """A sprite of one texel box, drawn at its own size or stretched to
        another, about its centre or from its top edge."""
        sheet, x0, y0, x1, y1 = key
        w, h = size or (float(x1 - x0), float(y1 - y0))
        rect = (-w / 2, 0.0, w / 2, h) if top else (-w / 2, -h / 2, w / 2, h / 2)
        sprites.append(([(uv(key), rect, 0xffffffff)], w, h))
        return len(sprites) - 1

    def copied(sprite, n):
        """A sprite of the first n quads of a stock one, its UV entries into this page."""
        off = _rva_to_off(buf, sprite - base)
        page, quads, _count, w, h = struct.unpack_from('<IIIff', buf, off)
        out = []
        for k in range(n):
            q = _rva_to_off(buf, quads - base) + k * 0x34
            uvi, x0, y0, x1, y1 = struct.unpack_from('<I4f', buf, q)
            sheet, u0, v0, u1, v1 = struct.unpack_from('<i4f', buf, _rva_to_off(buf, page - base) + uvi * 0x14)
            out.append((uv(('raw', sheet, u0, v0, u1, v1)), (x0, y0, x1, y1), struct.unpack_from('<I', buf, q + 0x14)[0]))
        sprites.append((out, w, h))
        return len(sprites) - 1

    def hold(kind, first, last, index=0):
        return index << 24 | kind << 16 | (last + 1) << 8 | (first + 1)

    def add_sprite(sp, x, y, z, colour, held=0):
        draw.append((1, ('sprite', sp), x, y, z, colour, held))

    def add_stock(sp, x, y, z, colour, held=0):
        draw.append((1, ('stock', sp), x, y, z, colour, held))

    def add_text(text, x, y, flags, colour, held=0):
        strings.append(text)
        draw.append((2, ('string', len(strings) - 1), x, y, flags, colour, held))

    def add_value(index, x, y, flags, colour, held=0):
        draw.append((2, ('value', index), x, y, flags, colour, held))

    device, settings, colon = (piece(PAGE_PIECES[k]) for k in ('DEVICE', 'SETTINGS', 'COLON'))
    group_plate, row_plate = copied(stock['group'], 2), copied(stock['gsrow'], 3)
    # a line the height of a group, from the white margin of a hint strip on the appended sheet
    divider = piece((TXR_ICON, 1, HINT_STRIP_TOPS[0] + 1, 2, HINT_STRIP_TOPS[0] + HINT_ROWS - 1), (1.0, 18.0), top=True)
    bar = copied(stock['bar'], PAGE_BAR_QUADS)
    strips, tops = [], iter(HINT_STRIP_TOPS)
    for line in HINT_LINES:
        placed, width, cut = hint_layout(line)
        quads = []
        for half in (placed[:cut], placed[cut:]):
            top, x0 = next(tops), half[0][0]
            w = half[-1][0] + half[-1][1][2] - half[-1][1][0] - x0 + 2 * HINT_MARGIN
            quads.append((uv((TXR_ICON, 1, top, 1 + w, top + HINT_ROWS)),
                          (x0 - width / 2 - HINT_MARGIN, PAGE_STRIP_Y, x0 - width / 2 - HINT_MARGIN + w, PAGE_STRIP_Y + HINT_ROWS),
                          0xffffffff))
        sprites.append((quads, float(width), float(HINT_ROWS)))
        strips.append(len(sprites) - 1)
    rows = 1 + len(PAGE_ACTIONS)            # the selector, then the actions; the button row is one more
    every = (0, 254)

    add_stock(stock['band'], 320.0, 87.0, Z_PLATE, PLATE)
    add_sprite(device, 320.0 - 95.5 + 38.5, 87.0, Z_TEXT, TEXT)
    add_sprite(settings, 320.0 + 95.5 - 53.0, 87.0, Z_TEXT, TEXT)
    add_sprite(group_plate, PAGE_SELECTOR_X, PAGE_SELECTOR_Y, Z_PLATE, PLATE, hold(HOLD_ROW, 0, 0))
    add_value(PAGE_LABEL_VALUE, 320.0, PAGE_SELECTOR_Y + PAGE_TEXT_DY, FLAGS_PROPORTIONAL | FLAGS_CENTRED, TEXT, hold(HOLD_VALUE, 0, 0))
    add_text('KEY', PAGE_VALUE_X, PAGE_HEADER_Y, FLAGS_PROPORTIONAL, PAGE_HEADER_COLOUR)
    add_text('PAD', PAGE_PAD_X, PAGE_HEADER_Y, FLAGS_PROPORTIONAL, PAGE_HEADER_COLOUR)
    y = PAGE_ROW_Y
    for i, (action, code) in enumerate(PAGE_ACTIONS):
        r = 1 + i
        add_sprite(row_plate, PAGE_ROW_X, y, Z_PLATE, PLATE, hold(HOLD_ROW, r, r))
        add_text(action, PAGE_ACTION_X, y + PAGE_TEXT_DY, FLAGS_PROPORTIONAL, TEXT)
        if code != 0xff:
            add_sprite(divider, PAGE_DIVIDER_X, y, Z_TEXT, PAGE_DIVIDER_COLOUR)
        add_value(i * 2, PAGE_VALUE_X, y + PAGE_TEXT_DY, FLAGS_PROPORTIONAL, TEXT, hold(HOLD_VALUE, r, r))
        if code != 0xff:
            add_value(i * 2 + 1, PAGE_PAD_X, y + PAGE_TEXT_DY, FLAGS_PROPORTIONAL, TEXT, hold(HOLD_VALUE, r, r))
        y += PAGE_ROW_STEP
    for i, button in enumerate((stock['default'], back)):
        add_stock(button, PAGE_BUTTON_X[i], PAGE_BUTTON_Y, Z_PLATE, TEXT, hold(HOLD_BUTTON, rows, rows, i))
    add_sprite(bar, 320.0, PAGE_BAR_Y, Z_PLATE, TEXT, hold(HOLD_BAR, *every))
    for sprite, kind in zip(strips, (HOLD_BAR_IDLE, HOLD_BAR_BIND)):
        add_sprite(sprite, 320.0, PAGE_BAR_Y, Z_PLATE, TEXT, hold(kind, *every))

    # lay it out: code, state table, page header, UV table, sprites, quads, draw list, strings
    code = DEVICES_BLOB
    n_uv = len(uvkeys)
    off_table = len(code)
    off_hdr = off_table + 14 * 4
    off_uv = off_hdr + 8
    off_desc = off_uv + n_uv * 0x14
    off_quads = off_desc + len(sprites) * 0x20
    n_quads = sum(len(q) for q, _w, _h in sprites)
    off_draw = off_quads + n_quads * 0x34
    off_strings = off_draw + (len(draw) + 1) * 40
    string_offs, size = [], off_strings
    for text in strings:
        string_offs.append(size)
        size += len(text) + 1
    off_data = _align(size, 4)
    blob = bytearray(off_data + DATA_SIZE)
    blob[off_data:] = bind_data('xinput' in row['sites'])
    relocs = []
    # code, its placeholders filled
    values = dict(opt, SELFRVA=va - base, PAGEHDR=va - base + off_hdr, DRAWLIST=va - base + off_draw,
                  EPILOGUE=_off_to_rva(buf, cont + 5 + buf[cont + 4]), ROWS=rows, BINDDATA=va - base + off_data,
                  PADPOLL=row['addresses']['PADPOLL'])
    for name, magic in DEVICES_MAGICS.items():
        value = values[name] - base if values[name] >= base else values[name]
        code = code.replace(struct.pack('<I', magic), struct.pack('<I', value))
    if any(struct.pack('<I', magic) in code for magic in DEVICES_MAGICS.values()):
        raise ValueError('devices.asm: a placeholder left unfilled')
    blob[:len(code)] = code
    # the state table: the twelve stock states, then init and exec
    top = _rva_to_off(buf, opt['TOPTABLE'] - base)
    for i in range(12):
        struct.pack_into('<I', blob, off_table + i * 4, struct.unpack_from('<I', buf, top + i * 4)[0])
    struct.pack_into('<II', blob, off_table + 48, va, va + 5)
    relocs += [off_table + i * 4 for i in range(14)]
    # the page
    struct.pack_into('<II', blob, off_hdr, va + off_uv, n_uv)
    relocs.append(off_hdr)
    for key, i in uvkeys.items():
        if key[0] == 'raw':
            struct.pack_into('<i4f', blob, off_uv + i * 0x14, *key[1:])
        else:
            sheet, x0, y0, x1, y1 = key
            struct.pack_into('<i4f', blob, off_uv + i * 0x14, sheet, x0 / 256.0, y0 / 256.0, x1 / 256.0, y1 / 256.0)
    q = off_quads
    for i, (quads, w, h) in enumerate(sprites):
        struct.pack_into('<IIIffffI', blob, off_desc + i * 0x20, va + off_uv, va + q, len(quads), w, h, 0.0, 0.0, 0)
        relocs += [off_desc + i * 0x20, off_desc + i * 0x20 + 4]
        for k, (x0, y0, x1, y1), colour in quads:
            blob[q:q + 0x34] = struct.pack('<I4f', k, x0, y0, x1, y1) + quad_tail
            for j in range(4):
                struct.pack_into('<I', blob, q + 0x14 + j * 8, colour)
            q += 0x34
    for i, (kind, (what, ref), x, y, zf, colour, held) in enumerate(draw):
        ptr = {'sprite': lambda: va + off_desc + ref * 0x20, 'stock': lambda: ref, 'string': lambda: va + string_offs[ref],
               'value': lambda: va + off_data + DATA_VALUES + ref * 16}[what]()
        z = struct.unpack('<I', struct.pack('<f', zf))[0] if kind == 1 else zf
        struct.pack_into('<IIffIIIIII', blob, off_draw + i * 40, kind, ptr, x, y, z, *colour, held)
        relocs.append(off_draw + i * 40 + 4)
    for text, off in zip(strings, string_offs):
        blob[off:off + len(text)] = text.encode('ascii')
    return bytes(blob), relocs


def wheel_mask(size=126):
    """Coverage, 0..255, of a steering wheel in the icons' style: a rim,
    three spokes, a hub with a hole. Sixteen samples a texel; the stock
    pictures carry the same one-texel alpha ramp along their edges."""
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
    if hashlib.md5(data[offsets[6]:offsets[6] + 96 * 256 * 2]).hexdigest() != TXR_SHEET6_MD5:
        return 'the label sheet is not the English one'
    return None


def patch_txr(data):
    """OPTIONS.TXR with a thirteenth sheet, 256x256: the icon at its top
    left - the third icon's plate, its picture filled back in, with a
    steering wheel cut out the same way - and the page's hint lines
    below, set letter by letter from the frame's own message lettering on
    sheet 4, as the stock's message strips are (sheets 4 and 5 are format
    0, 565). The gutter is clear white like the stock sheets', so the
    edge texels filter to white, not to black. Returns the grown file."""
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
    texture = bytearray(struct.pack('<H', 0x0fff) * (256 * 256))   # clear white, as the stock sheets' gutters
    for y in range(126):
        texture[((y + 1) * 256 + 1) * 2:((y + 1) * 256 + 127) * 2] = plate[y * 252:y * 252 + 252]
    letters = 0x1000 + sum(size * size * 2 for _f, size in TXR_ENTRIES[:HINT_SHEET])   # the frame's messages' lettering
    tops = iter(HINT_STRIP_TOPS)
    for line in HINT_LINES:                 # the hint lines, letter by letter, each in two halves
        placed, _width, cut = hint_layout(line)
        for half in (placed[:cut], placed[cut:]):
            top, x0 = next(tops), half[0][0]
            width = half[-1][0] + half[-1][1][2] - half[-1][1][0] - x0
            for y in range(HINT_ROWS):          # the strip opaque white, a margin each side, then the letters
                for x in range(width + 2 * HINT_MARGIN):
                    struct.pack_into('<H', texture, ((top + y) * 256 + 1 + x) * 2, 0xffff)
            for x, (gx0, gy0, gx1) in half:
                for y in range(HINT_ROWS):
                    for gx in range(gx1 - gx0):
                        v = struct.unpack_from('<H', data, letters + ((gy0 - 1 + y) * 256 + gx0 + gx) * 2)[0]   # 565 to 4444, opaque
                        texel = 0xf000 | (v >> 12) << 8 | (v >> 7 & 15) << 4 | (v >> 1 & 15)
                        struct.pack_into('<H', texture, ((top + y) * 256 + 1 + HINT_MARGIN + x - x0 + gx) * 2, texel)
    out = bytearray(data)
    struct.pack_into('<I', out, 4, len(TXR_ENTRIES) + 1)
    struct.pack_into('<4I', out, 16 + 16 * len(TXR_ENTRIES), 8, 256, len(texture), 0)
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


def apply_texrange(buf, _build=None):
    """texrange.asm in MGameD3D: the texture release's first ten bytes
    jump to it; the absolute in them loses its relocation entry."""
    if _drop_relocations(buf, {0x4431}) != 1:
        raise ValueError('relocation entry for the texture table not found')
    out, rva = append_section(buf, TEXRANGE_SECTION, TEXRANGE_BLOB, chars=CODE_SECTION)
    start = _rva_to_off(out, rva)
    out[start:start + len(TEXRANGE_BLOB)] = TEXRANGE_BLOB.replace(
        struct.pack('<I', FULLWIN_MAGIC), struct.pack('<I', rva))
    _branch(out, 0x4430, rva, 10, op=b'\xe9')
    return out


def apply_replayfree(buf, _build=None):
    """replayfree.asm in ReplayGallery: the gallery's new at 0x10003b65
    calls the first thunk, its End's free of the replay the second."""
    out, rva = append_section(buf, REPLAYFREE_SECTION, REPLAYFREE_BLOB)
    start = _rva_to_off(out, rva)
    out[start:start + len(REPLAYFREE_BLOB)] = REPLAYFREE_BLOB.replace(
        struct.pack('<I', FULLWIN_MAGIC), struct.pack('<I', rva))
    _branch(out, 0x2f65, rva, 5)
    _branch(out, 0x3b1f, rva + 5, 6)
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


def carry_display_block(dest, log):
    """The game's 100-byte display block from a stock SR2.CFG into SR2.DSP,
    where the noregistry patch has the game keep it, so a resolution choice
    survives; only when SR2.DSP is not there yet."""
    cfg, dsp = os.path.join(dest, 'SR2.CFG'), os.path.join(dest, 'SR2.DSP')
    if os.path.isfile(dsp) or not os.path.isfile(cfg):
        return
    with open(cfg, 'rb') as fh:
        head = fh.read(100)
    if len(head) == 100 and head.startswith(b'display'):
        with open(dsp, 'wb') as fh:
            fh.write(head)
        log('patch: the display block of SR2.CFG carried to SR2.DSP')


def patch(dest, log=print, keys=PATCH_KEYS):
    """Write every wanted patch. Each touched file is patched from its
    backup, written on the first run, so patching twice is patching once;
    a file nothing wanted touches goes back to its backup, so patching
    with fewer keys takes the others out."""
    build = check_build(dest)
    table = patches(build)
    log('patch: %s build' % build)
    for key, needs in NEEDS:
        if key in keys and key in table and needs not in keys:
            raise ValueError('%s needs %s' % (key, needs))
    txr = None
    txr_path = os.path.join(dest, *TXR.split('\\'))
    if 'devices' in keys:
        source = txr_path + '.bak' if os.path.isfile(txr_path + '.bak') else txr_path
        with open(source, 'rb') as fh:
            txr = fh.read()
        why = txr_check(txr)
        if why:
            raise ValueError('%s: %s' % (TXR, why))
    elif os.path.isfile(txr_path + '.bak'):
        os.replace(txr_path + '.bak', txr_path)
        log('patch: %s back to stock' % TXR)
    if 'noregistry' in keys and 'noregistry' in table:
        carry_display_block(dest, log)
    for name in PATCHED:
        size, digest = BUILDS[build]['files'][name]
        wanted = [table[key] for key in keys if key in table and table[key][0] == name]
        sites = [site for _f, ss, _t in wanted for site in ss]
        transforms = [globals()[t] for _f, _s, t in wanted if t]
        path = os.path.join(dest, *name.split('\\'))
        bak = path + '.bak'
        if not sites and not transforms:
            if os.path.isfile(bak):
                os.replace(bak, path)
                log('patch: %s back to stock' % name)
            continue
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
        if not os.path.isfile(txr_path + '.bak'):
            os.replace(txr_path, txr_path + '.bak')
            log('patch: backup written to %s.bak' % TXR)
        with open(txr_path, 'wb') as fh:
            fh.write(patch_txr(txr))
        log('patch: %s written, devices' % TXR)


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


# What a key needs: dropping the second drops the first with it.
NEEDS = (('xinput', 'noregistry'), ('devices', 'xinput'), ('music', 'cdlevel'))


def parse_keys(words):
    """The patches --patch's key words name: every patch, or the ones
    listed, less any given with a leading minus. Words may be separated by
    commas or spaces (PowerShell hands a,b over as two)."""
    keys = [k for w in words for k in w.split(',') if k]
    unknown = [k for k in keys if k.lstrip('-') not in PATCH_KEYS + DIAGNOSTIC]
    if unknown:
        raise ValueError('no patch named %s; the patches are %s' % (unknown[0].lstrip('-'), ', '.join(PATCH_KEYS)))
    wanted = [k for k in keys if not k.startswith('-')] or list(PATCH_KEYS)
    dropped = set(k[1:] for k in keys if k.startswith('-'))
    for key, needs in NEEDS:
        if needs in dropped:
            dropped.add(key)
    return tuple(k for k in wanted if k not in dropped)


def main(argv):
    args = argv[1:]
    if not args:
        gui()
        return 0
    try:
        if args[0] == '--install' and 3 <= len(args) <= 4:
            install(*args[1:])
        elif args[0] == '--patch' and len(args) >= 2:
            patch(args[1], keys=parse_keys(args[2:]))
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
