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
PATCHED = (EXE, 'MUSASHI\\MGameD3D.dll', 'MUSASHI\\MGameGL.dll', 'MUSASHI\\MGAudio.dll', 'MUSASHI\\MGSound.dll',
           'MUSASHI\\MGInput.dll', 'Title.dll', 'Options.dll', 'ReplayGallery.dll')

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
                  'frametrace': (0x27d0b, 0x27bf0),
                  'wide': (0x20dfe, 0x20e18, 0x5128a),
                  'voltrace': ((0x6e6e0, 6), (0x6fa30, 9), (0x6d560, 5), (0x6e770, 9), (0x6e0e0, 6)),
                  'volume': 0x1db0, 'getvolume': 0x1e40,   # in MGAudio.dll: the CD-volume methods
                  'mix': (0x439f, 0x6980)},  # in MGSound.dll: the buffer's SetRange, the stream's SetVolume
        # `ff15` call [slot], `8b35` mov esi, [slot]; the slot is SetTextColor's.
        'textcolor': ((0x203c7, '8b35'), (0x20566, '8b35'), (0x3485f, 'ff15'), (0x34b2a, 'ff15'),
                      (0x34efc, 'ff15'), (0x35533, 'ff15'), (0x360c3, 'ff15'), (0x3a6c0, 'ff15'),
                      (0x3cef4, 'ff15'), (0x3da96, 'ff15')),
        'slots': {'SetTextColor': 0x495028, 'GetLogicalDriveStringsA': 0x495198, 'lstrcpyA': 0x4950f4,
                  'LoadLibraryA': 0x495090, 'GetProcAddress': 0x4950f0,
                  'GetPrivateProfileStringA': 0x4951b8, 'GetModuleFileNameA': 0x495074},
        'options': {'BINDPAGE': 0x1000ed90, 'DRAW': 0x1000e850, 'PLAYSOUND': 0x1000b610, 'INPUT': 0x100b9464,
                    'SOUNDOBJ': 0x100b8bd8, 'HANDLES': 0x100b8bdc, 'TOPTABLE': 0x10003d90,
                    'TEXT': 0x1000df10, 'GLYPHS': 0x1009c080,
                    'LOADLIB': 0x10019010, 'GETPROC': 0x10019048, 'GETMODFN': 0x10019030},
        'addresses': {'MENUTABLES': 0x1009c820, 'REGNAMES': (0x5a2714, 0x4cff94), 'CARS': 0x4d64bc, 'PADPOLL': 0x5a1ff0, 'RESUME': 0x46e260, 'GAMED3D': 0x50b118, 'HANDLER': 0x41fe20, 'HWND': 0x5088ac,
                      'WIDTH': 0x4d5e1c, 'HEIGHT': 0x4d5e20, 'LOCKDESC': 0x4e6878, 'MODE': 0x4d5e54, 'HIRES': 0, 'SETTER': 0x4219f0,
                      'SETTINGS': 0x50afdc, 'OPTSETTINGS': 0x100b9320,
                      'RUNNING': 0x4d6a3c, 'PAUSED': 0x4d6a6c, 'DEBUGDLL': 0x5a2660, 'CATCHUP': 0x4d6930},
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
                  'frametrace': (0x27fcb, 0x27eb0),
                  'wide': (0x2108e, 0x210a8, 0x5160a),
                  'volume': 0x1db0, 'getvolume': 0x1e40, 'mix': (0x439f, 0x6980)},
        'textcolor': ((0x20657, '8b35'), (0x207f6, '8b35'), (0x34b8f, 'ff15'), (0x34e5a, 'ff15'),
                      (0x3522c, 'ff15'), (0x35863, 'ff15'), (0x363f3, 'ff15'), (0x3aae0, 'ff15'),
                      (0x3d314, 'ff15'), (0x3ddc6, 'ff15')),
        'slots': {'SetTextColor': 0x495028, 'GetLogicalDriveStringsA': 0x49519c, 'lstrcpyA': 0x4950f4,
                  'LoadLibraryA': 0x495090, 'GetProcAddress': 0x4950f0,
                  'GetPrivateProfileStringA': 0x4951b8, 'GetModuleFileNameA': 0x495074},
        'options': {'BINDPAGE': 0x1000ed90, 'DRAW': 0x1000e850, 'PLAYSOUND': 0x1000b610, 'INPUT': 0x100b9464,
                    'SOUNDOBJ': 0x100b8bd8, 'HANDLES': 0x100b8bdc, 'TOPTABLE': 0x10003d90,
                    'TEXT': 0x1000df10, 'GLYPHS': 0x1009c080,
                    'LOADLIB': 0x10019010, 'GETPROC': 0x10019048, 'GETMODFN': 0x10019030},
        'addresses': {'MENUTABLES': 0x1009c820, 'REGNAMES': (0x5a2714, 0x4d0074), 'CARS': 0x4d65ac, 'PADPOLL': 0x5a1ff0, 'RESUME': 0x46e480, 'GAMED3D': 0x50b218, 'HANDLER': 0x41feb0, 'HWND': 0x5089ac,
                      'WIDTH': 0x4d5f0c, 'HEIGHT': 0x4d5f10, 'LOCKDESC': 0x4e6968, 'MODE': 0x4d5f44, 'HIRES': 0x4efa1c, 'SETTER': 0x421a80,
                      'SETTINGS': 0x50b0dc, 'OPTSETTINGS': 0x100b9320,
                      'RUNNING': 0x4d6b2c, 'PAUSED': 0x4d6b5c, 'DEBUGDLL': 0x5a2660, 'CATCHUP': 0x4d6a20},
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
                  'frametrace': (0x4c94e, 0x4c830),
                  'wide': (0x40b1e, 0x40b38, 0x895c8),
                  'volume': 0x1d90, 'getvolume': 0x1e20, 'mixer': 0x2278,    # all in MGAudio.dll
                  'mix': (0x439f, 0x6980),
                  'sfxlevel': (0xb26cb, 0xb272e, 0xb2782), 'sfxoptions': (0xf92a, 0xf98d, 0xf9e1)},
        'textcolor': ((0x400f7, '8b35'), (0x40296, '8b35'), (0x5e28f, 'ff15'), (0x5e55a, 'ff15'),
                      (0x5e91c, 'ff15'), (0x5ef53, 'ff15'), (0x5fae3, 'ff15'), (0x66930, 'ff15'),
                      (0x69164, 'ff15'), (0x69c16, 'ff15')),
        'slots': {'SetTextColor': 0x4d402c, 'GetLogicalDriveStringsA': 0x4d4198, 'lstrcpyA': 0x4d40fc,
                  'LoadLibraryA': 0x4d4094, 'GetProcAddress': 0x4d40f8,
                  'GetPrivateProfileStringA': 0x4d41a8, 'GetModuleFileNameA': 0x4d4078},
        'options': {'BINDPAGE': 0x10013df0, 'DRAW': 0x100138b0, 'PLAYSOUND': 0x10010670, 'INPUT': 0x100c1b1c,
                    'SOUNDOBJ': 0x100be46c, 'HANDLES': 0x100be470, 'TOPTABLE': 0x10006500,
                    'TEXT': 0x10012f70, 'GLYPHS': 0x100a1090,
                    'LOADLIB': 0x1001e010, 'GETPROC': 0x1001e048, 'GETMODFN': 0x1001e030},
        'addresses': {'MENUTABLES': 0x100a2708, 'REGNAMES': (0x60c714, 0x5151cc), 'CARS': 0x52f9cc, 'PADPOLL': 0x60bff0, 'RESUME': 0x4ad790, 'GAMED3D': 0x575ae8, 'HANDLER': 0x43fb50, 'HWND': 0x57327c,
                      'WIDTH': 0x52dc1c, 'HEIGHT': 0x52dc20, 'LOCKDESC': 0x53fd88, 'MODE': 0x52dc50, 'HIRES': 0, 'SETTER': 0x441710, 'SETTINGS': 0x5759ac, 'OPTSETTINGS': 0x100c19d8,
                      'RUNNING': 0x52ff4c, 'PAUSED': 0x52ff7c, 'DEBUGDLL': 0x60c660, 'CATCHUP': 0x52fe40},
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
#   nodisc      the disc check returns "found"; the loader takes the exe's directory
#   nocardwarn  the video-card warning box skipped
#   altab       the resume call restores the DirectDraw surfaces first
#   zdetach     DeleteAttachedSurface(0, NULL) calls removed (Proton crash)
#   restoreall  the restore routine becomes RestoreAllSurfaces
#   texfmt      A1R5G5B5 first in the texture-format preference list
#   textcolor   the lobby's SetTextColor(-1) masked to RGB
#   windowed    the fullscreen flag cleared; the .bg row copy expands to 32 bits (always on)
#   anydepth    the windowed path's 16-bit desktop check skipped
#   altenter    ALT+ENTER toggles a framed window
#   titlebg     Title.dll's own .bg row copy, the same stub
#   texrange    the texture release checks its index; VendorLogo releases -128
#   replayfree  the replay gallery frees only the replay it loaded, not a race's in MainMode's data
#   borderless  the window covers its monitor, the present letterboxes (always on)
#   mix         MGSound: every buffer's dB range remapped to -43..-8, the streams on the same curve
#   cdlevel     the menu's CD-level set flagged, so the music hook tells it from a fade; music needs it
#   music       CD audio from music\trackNN.wav; the BGM slider sets its volume
#   devices     a fourth Options item, Device Settings, placed for the controller page; also grows OPTIONS.TXR
#   noregistry  the controls in SR2.CFG as text; the registry never opened
#   xinput      XInput pads through MGInput's own action records
#   win9x       the Windows 9x check returns "fine" (Australian)
#   sfxlevel    the effects at 100% of their ceiling, as the other builds (Australian exe)
#   sfxoptions  the same in the Australian Options.dll, which re-applies on the way out
#   mixerless   MGAudio Init without a mixer CD line (Australian)
#   voltrace    diagnostic, by name only: volume calls reported on +debugstr
#   frametrace  diagnostic, by name only: every drawn frame logged to frames.log beside the exe

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


WIDEGL_SITES = (0x2bc0, 0x2c70)         # MGameGL, file offsets: SetViewport 0x100037c0, SetPerspective 0x10003870
WIDE2D_SITES = (0x5120, 0x50d0, 0x4fe0, 0x5170, 0x5030, 0x5080, 0x6040, 0x4d50, 0x411c)   # MGameD3D, the quad, triangle, list, indexed-list, strip and fan draws', the viewport setter's and the present's first instructions, the texture create after its system-memory copy
WIDE2D_RELOCS = {0x5122, 0x50d2, 0x4fe6, 0x5176, 0x5036, 0x5086, 0x4d51}  # the absolute in each draw's and the present's
RESOLUTION_INIT, RESOLUTION_COUNT, RESOLUTION_DRAW, RESOLUTION_LEAVE = 0x2815, 0x2826, 0x2528, 0x2b01   # Options.dll
RESOLUTION_RESET = 0x2a5b               # Options.dll, DEFAULT's store of the row
RESOLUTION_VALTAB = 0x259c              # Options.dll, the imm of `mov edx, [valtab]` at 0x1000319a
RESOLUTION_PLATES = 0x2482              # and of `mov edi, [plates]` at 0x10003081, the row plates' list
# The page's "7"s - the settings rows before the button row - made "8"
# for the aspect row: the value loop's bound, right and left on the
# button row, down past the last row, up from the first, ENTER on the buttons.
RESOLUTION_EIGHTS = ((0x2523, 'bd07000000', 'bd08000000'), (0x28e2, '83f807', '83f808'), (0x2931, '83f807', '83f808'),
                     (0x297b, '83f807', '83f808'), (0x29c1, 'c7461007000000', 'c7461008000000'), (0x29f6, '837e1007', '837e1008'))
RESOLUTION_RELOCS = {0x3416, 0x3427, 0x3703}   # the absolutes in the replaced init, count and leave instructions
# The resolution list, the stock two first, grouped by aspect: (width,
# height). The exe takes a size from SR2.CFG only when it is here past
# the stock two; the page's ASPECT RATIO row picks a group.
RESOLUTIONS = ((640, 480), (800, 600), (1024, 768), (1280, 960), (1600, 1200),
               (1280, 800), (1440, 900), (1680, 1050), (1920, 1200), (2560, 1600),
               (1280, 720), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160),
               (2560, 1080), (3440, 1440), (3840, 1080), (5120, 1440))
RESOLUTION_GROUPS = ((4, 3, 5), (16, 10, 5), (16, 9, 5), (21, 9, 2), (32, 9, 2))   # (aspect, sizes), in the list's order; resolution.asm names them


def resolution_groups():
    """(first entry, entries) per aspect group; the sizes checked against
    the aspect loosely (the 21:9 sizes are 64:27 and 43:18)."""
    out, start = [], 0
    for w, h, n in RESOLUTION_GROUPS:
        for rw, rh in RESOLUTIONS[start:start + n]:
            if abs(rw / rh - w / h) > 0.06:
                raise ValueError('%dx%d is not %d:%d' % (rw, rh, w, h))
        out.append((start, n))
        start += n
    if start != len(RESOLUTIONS):
        raise ValueError('the groups do not cover the list')
    return b''.join(struct.pack('<II', *g) for g in out)


def resolution_table(strings=False):
    """The (width, height) pairs, 0, 0 after the last; with the strings,
    each size as WIDTHxHEIGHT after that, for the page."""
    out = b''.join(struct.pack('<II', w, h) for w, h in RESOLUTIONS) + bytes(8)
    if strings:
        out += b''.join(('%dX%d' % wh).encode() + b'\0' for wh in RESOLUTIONS)
    return out
TITLEROW_SITE, TITLEROW_LEN = 0x8ba, 22  # Title.dll, the row copy at 0x100014ba
PRESENT_SITE = 0x4d7b                   # MGameD3D, the windowed present's first instruction
SIZE_SITE = 0x26be                      # MGameD3D, `call [__imp__MoveWindow]` in the windowed init
# HIGHLOW entries inside the replaced present (absolute addresses, now dead
# code) and the one under the MoveWindow call.
FULLWIN_RELOCS = {0x4d7d, 0x4d8a, 0x4d8f, 0x4d95, 0x4da3, 0x4db1, 0x4db6, 0x4dc4, 0x4dd3, 0x26c0}



def wide_sites(offsets, addresses, american):
    """The exe's widescreen sites: the mode setter's `mov eax, [esp+8];
    cmp [MODE], eax` and its literal size stores (the American build's
    have a third size behind a flag), and the screen-change routine's
    `mov eax, [SETTINGS]; mov ecx, [eax+0x50]`."""
    modecheck, setsize, screen = offsets
    w, h = struct.pack('<I', addresses['WIDTH']), struct.pack('<I', addresses['HEIGHT'])

    def size(width, height):
        return bytes.fromhex('c705') + w + struct.pack('<I', width) + bytes.fromhex('c705') + h + struct.pack('<I', height)
    if american:
        stores = (size(640, 480) + bytes.fromhex('7433a1') + struct.pack('<I', addresses['HIRES']) + bytes.fromhex('85c07516')
                  + size(800, 600) + bytes.fromhex('eb14') + size(1024, 768))
    else:
        stores = size(640, 480) + bytes.fromhex('7414') + size(800, 600)
    return ((modecheck, bytes.fromhex('8b4424083905') + struct.pack('<I', addresses['MODE']), None),
            (setsize, stores, None),
            (screen, b'\xa1' + struct.pack('<I', addresses['SETTINGS']) + bytes.fromhex('8b4850'), None))


def resolution_sites(settings):
    """The Graphic Settings page's sites in Options.dll: the row's load
    from the settings, the count's 800x600 check (skipped), the draw
    loop's head, and the row's store to the settings on leaving."""
    st = struct.pack('<I', settings)
    return ((RESOLUTION_INIT, b'\xa1' + st + bytes.fromhex('8b5050894e70895630'), None),
            (RESOLUTION_COUNT, bytes.fromhex('a1') + struct.pack('<I', settings + 4) + bytes.fromhex('8448307503895e70'),
             bytes.fromhex('eb0b')),
            (RESOLUTION_DRAW, bytes.fromhex('8b449e3833ff85c0'), None),
            (RESOLUTION_LEAVE, bytes.fromhex('8b15') + st + bytes.fromhex('8b4e30894a50'), None),
            (RESOLUTION_RESET, bytes.fromhex('8b4850894e30'), None)) + tuple(
                (off, bytes.fromhex(old), bytes.fromhex(new)) for off, old, new in RESOLUTION_EIGHTS)


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
        'widescreen': (EXE, wide_sites(site['wide'], row['addresses'], build == 'American'), 'apply_widescreen'),
        'widescreen2d': ('MUSASHI\\MGameD3D.dll', (
            (WIDE2D_SITES[0], bytes.fromhex('8b1520120110'), None),
            (WIDE2D_SITES[1], bytes.fromhex('8b1520120110'), None),
            (WIDE2D_SITES[2], bytes.fromhex('8b44240c8b0d64270110'), None),
            (WIDE2D_SITES[3], bytes.fromhex('8b4424148b0d64270110'), None),
            (WIDE2D_SITES[4], bytes.fromhex('8b44240c8b0d64270110'), None),
            (WIDE2D_SITES[5], bytes.fromhex('8b44240c8b0d64270110'), None),
            (WIDE2D_SITES[6], bytes.fromhex('83ec08568b74241457'), None),
            (WIDE2D_SITES[7], bytes.fromhex('a10c24011083ec10'), None),
            (WIDE2D_SITES[8], bytes.fromhex('33c0b91f0000008d7c2420f3ab'), None)), 'apply_wide2d'),
        'gltrace': ('MUSASHI\\MGameGL.dll', (), 'apply_gltrace'),
        'd3dtrace': ('MUSASHI\\MGameD3D.dll', (), 'apply_d3dtrace'),
        'widescreen3d': ('MUSASHI\\MGameGL.dll', (
            (WIDEGL_SITES[0], bytes.fromhex('558bec83ec2889742404'), None),
            (WIDEGL_SITES[1], bytes.fromhex('558bec83ec18891c24'), None)), 'apply_widegl'),
        'resolution': ('Options.dll', resolution_sites(row['addresses']['OPTSETTINGS']), 'apply_resolution'),
    }
    if 'oscheck' in site:
        table['win9x'] = (EXE, ((site['oscheck'], bytes.fromhex('81ec94000000'), bytes.fromhex('31c0c3')),), None)
    if 'voltrace' in site:
        table['voltrace'] = (EXE, tuple((off, VOLTRACE_HEADS[i], None) for i, (off, _n) in enumerate(site['voltrace'])),
                             'apply_voltrace')
    # the frame gate's exit, pop edi; mov [esi+0x1c],eax; pop esi, and its
    # entry, mov eax,[RUNNING]
    table['frametrace'] = (EXE, ((site['frametrace'][0], bytes.fromhex('5f89461c5e'), None),
                                 (site['frametrace'][1], b'\xa1' + struct.pack('<I', row['addresses']['RUNNING']), None)),
                           'apply_frametrace')
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
DIAGNOSTIC = ('voltrace', 'frametrace', 'gltrace', 'd3dtrace')

# Every patch any build has, in table order.
PATCH_KEYS = tuple(k for k in dict.fromkeys(k for b in BUILDS for k in patches(b)) if k not in DIAGNOSTIC)

# The mciSendCommandA sites in MGAudio.dll: 11 `call dword [slot]`, and
# one `mov esi, dword [slot]` in the open routine, which then calls esi.
MCI_CALL_SITES = 11
MCI_LOAD_SITES = 1

# The section each transform appends, one per patch so any one can be
# left out. Code that keeps no data of its own is read-only.
ANNEX = b'.sr2'                         # the one section the patches append to a file, each growing it
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
    'bef1f1f1f189c1d1e98b6c241c8b6d048b6d08394e0c0f856a070000396e080f'
    '8561070000837e5420741589c189cdc1e90289de89d7f3a589e983e103f3a4c3'
    '50535289c1d1e9741389de89d70fb70683c602e8eb060000ab4975f15a5b58c3'
    '8b45082b451cd1e889454085c00f840c02000031d2b940000000f7f189454485'
    'c00f84f80100008b4504c1e8047505b80100000089453cc7455c000000008b45'
    '000faf454031d2f77508b900000000e8cc0100008945548b85b00100008985a8'
    '0100008b454003451c0faf450031d2f7750889859c000000c1e0108945608b8d'
    '9c0000008b4500e8940100008945588b85b00100008985ac010000c785b40100'
    '00ffffffffc785b8010000ffffffffc74550000000008b455c8b4d54e8ec0300'
    '007307894548834d50018b45608b4d58e8d8030000730789454c834d5002c785'
    '98000000000000008b450c2b4520d1e88945308b75148b550c8b8598000000c1'
    'e810e848010000565289f7f7455001000000740d8b45488b4d40e8a6050000eb'
    '4b8b8598000000c1e8103b85b401000074298985b40100008b85a80100008985'
    'b00100008d85a00000008985bc0100008b455c8b4d54e8720100008d85a00000'
    '008985bc010000e8340200008b7d40037d1c837d18207502d1e78d3c7ef74550'
    '0200000074138b454c8b4d082b4d402b4d1ce82e050000eb4b8b8598000000c1'
    'e8103b85b801000074298985b80100008b85ac0100008985b00100008d85c001'
    '00008985bc0100008b45608b4d58e8fa0000008d85c00100008985bc010000e8'
    'bc0100005a5e837d30007405ff4d30eb248b45280185980000008b8598000000'
    'c1e8103b4504720d8b450448c1e0108985980000000375104a0f85dafeffffc3'
    '29c85031d2b940000000f7f185c075014001c08985b00100005a29c2790231d2'
    '89d0c1e01031d2b940000000f7f1c3502b453c790231c08945685803453c3b45'
    '0472048b45044889456cc351525657c1e81089859000000031c0894574894578'
    '89457c8945708b556889d00faf45000385900000008d34000375348b8db00100'
    '000fb70683c6028d7d74e8d4030000ff45704975ec83c2043b556c76cc8b4d70'
    '8d7d74e8d60300005f5e5a59c35752898594000000898d880000008bbdbc0100'
    '00ba410000008b8594000000e87affffffab8b85880000000185940000004a75'
    'e5c785cc0200004d000000568bb5bc010000ba410000008b06e8230000008906'
    '83c6044a75f15e5a5fc389c2c1ea0b5289c2c1ea0683e21f83e01f01d05a01d0'
    'c3515689c6c1e80b0faf85cc020000c1e80883f81f7605b81f00000089c1c1e1'
    '0b89f0c1e80583e03f0faf85cc020000c1e80883f83f7605b83f000000c1e005'
    '09c189f083e01f0faf85cc020000c1e80883f81f7605b81f00000009c85e59c3'
    '5652b940000000894d648bb5bc0100008b068b560483c6048b4d44837d640175'
    '1a8b4d40899590000000ba3f0000000faf554429d18b9590000000e808000000'
    'ff4d6475cb5a5ec35653894d7089c689d331c989f0e89a00000089448d748984'
    '8d8000000089d8e8880000002b448d74c1e0109951f77d705989848d8c000000'
    'c1a48d80000000104183f90372c58b4d708b8580000000c1e810c1e00b8b9584'
    '000000c1ea10c1e20509d08b9588000000c1ea1009d0837d1820750c5152e880'
    '0200005a59abeb0266ab8b858c0000000185800000008b859000000001858400'
    '00008b85940000000185880000004975a05b5ec383f9007504c1e80bc383f901'
    '7507c1e80583e03fc383e01fc352565753898594000000898d880000008b4504'
    'c1e8057505b80100000089858c00000031c089457489457889457c894570c745'
    '6400000000bb410000008b8594000000c1e81089859000000031d289d00faf45'
    '000385900000008d34000375340fb7065052e813feffff83f8047703ff45645a'
    '588d7d74e85a010000ff457003958c0000003b550472c48b8588000000018594'
    '0000004b75a48b4d708d7d74e84d0100008985a00000008b45646bc0048b4d70'
    '6bc90339c8720fc785a000000000000000e99d0000008b85880000006bc04129'
    '8594000000c7457c00000000bb410000008b8594000000c1e810898590000000'
    '31d289d00faf45000385900000008d34000375340fb706e86f00000001457c03'
    '958c0000003b550472d88b85880000000185940000004b75b88b457c31d2f775'
    '7083f802762d8b85a000000089c2c1ea0b89d189c2c1ea0683e21f01d189c283'
    'e21f01d183f9087716c785a0000000000000008b85a00000005b5f5e5af9c38b'
    '85a00000005b5f5e5af8c35152568bb5a000000089c1c1e90b89f2c1ea0b29d1'
    'e83700000089ca89c1c1e90683e11f5289f2c1ea0683e21f29d1e81d0000005a'
    '01ca89c183e11f5289f283e21f29d1e8080000005a8d040a5e5a59c385c97902'
    'f7d9c35289c2c1ea0b011789c2c1ea0583e23f01570483e01f0147085ac35152'
    '8b0731d2f7f1c1e00b508b470431d2f7f1c1e0055a09d0508b470831d2f7f15a'
    '09d05a59c385c97419837d1820740666ab4975fbc35253e8070000005b5aab49'
    '75fcc35589c389c281e300f8000081e2e007000083e01f89ddc1e308c1e50381'
    'e50000070009eb89d5c1e205d1ed81e50003000009ea89c5c1e003c1ed0209e8'
    '09d809d05dc33b56240f852e01000050535256575589e981ecd002000089e589'
    '4d04895d3489c1d1e9894d008b460c8945088b460889450c8b46108945108b46'
    '248945148b46548945188b7d148b550c8b4d10c1e90231c057f3ab5f037d104a'
    '75ee8b45080faf45048b4d0c0faf4d0039c8761289c831d2f7750489451c8b45'
    '0c894520eb0e31d2f775008945208b450889451c8b4500c1e01031d2f7751c89'
    '45248b4504c1e01031d2f77520894528c7452c000000008b450c2b4520d1e80f'
    'af45100345148b4d082b4d1cd1e9837d18207502d1e18d04488945388b452089'
    '45308b452cc1e8100faf45008d34000375348b7d3831d28b4d1c52c1ea100fb7'
    '0456837d1820740466abeb0851e8b1feffff59ab5a0355244975df8b45280145'
    '2c8b4510014538ff4d3075b6e8aff7ffff8da5d00200005d5f5e5a5b58c3'
)
TITLEROW_BLOB = bytes.fromhex(
    '8d74241c89c1d1e98b6c2414394e0c0f8565070000837e5420741789c189cdc1'
    'e90289de89d7f3a589e983e103f3a401c3c350535289c1d1e9741389de89d70f'
    'b70683c602e8ed060000ab4975f15a5b5801c3c38b45082b451cd1e889454085'
    'c00f840c02000031d2b940000000f7f189454485c00f84f80100008b4504c1e8'
    '047505b80100000089453cc7455c000000008b45000faf454031d2f77508b900'
    '000000e8cc0100008945548b85b00100008985a80100008b454003451c0faf45'
    '0031d2f7750889859c000000c1e0108945608b8d9c0000008b4500e894010000'
    '8945588b85b00100008985ac010000c785b4010000ffffffffc785b8010000ff'
    'ffffffc74550000000008b455c8b4d54e8ec0300007307894548834d50018b45'
    '608b4d58e8d8030000730789454c834d5002c78598000000000000008b450c2b'
    '4520d1e88945308b75148b550c8b8598000000c1e810e848010000565289f7f7'
    '455001000000740d8b45488b4d40e8a6050000eb4b8b8598000000c1e8103b85'
    'b401000074298985b40100008b85a80100008985b00100008d85a00000008985'
    'bc0100008b455c8b4d54e8720100008d85a00000008985bc010000e834020000'
    '8b7d40037d1c837d18207502d1e78d3c7ef745500200000074138b454c8b4d08'
    '2b4d402b4d1ce82e050000eb4b8b8598000000c1e8103b85b801000074298985'
    'b80100008b85ac0100008985b00100008d85c00100008985bc0100008b45608b'
    '4d58e8fa0000008d85c00100008985bc010000e8bc0100005a5e837d30007405'
    'ff4d30eb248b45280185980000008b8598000000c1e8103b4504720d8b450448'
    'c1e0108985980000000375104a0f85dafeffffc329c85031d2b940000000f7f1'
    '85c075014001c08985b00100005a29c2790231d289d0c1e01031d2b940000000'
    'f7f1c3502b453c790231c08945685803453c3b450472048b45044889456cc351'
    '525657c1e81089859000000031c089457489457889457c8945708b556889d00f'
    'af45000385900000008d34000375348b8db00100000fb70683c6028d7d74e8d4'
    '030000ff45704975ec83c2043b556c76cc8b4d708d7d74e8d60300005f5e5a59'
    'c35752898594000000898d880000008bbdbc010000ba410000008b8594000000'
    'e87affffffab8b85880000000185940000004a75e5c785cc0200004d00000056'
    '8bb5bc010000ba410000008b06e823000000890683c6044a75f15e5a5fc389c2'
    'c1ea0b5289c2c1ea0683e21f83e01f01d05a01d0c3515689c6c1e80b0faf85cc'
    '020000c1e80883f81f7605b81f00000089c1c1e10b89f0c1e80583e03f0faf85'
    'cc020000c1e80883f83f7605b83f000000c1e00509c189f083e01f0faf85cc02'
    '0000c1e80883f81f7605b81f00000009c85e59c35652b940000000894d648bb5'
    'bc0100008b068b560483c6048b4d44837d6401751a8b4d40899590000000ba3f'
    '0000000faf554429d18b9590000000e808000000ff4d6475cb5a5ec35653894d'
    '7089c689d331c989f0e89a00000089448d7489848d8000000089d8e888000000'
    '2b448d74c1e0109951f77d705989848d8c000000c1a48d80000000104183f903'
    '72c58b4d708b8580000000c1e810c1e00b8b9584000000c1ea10c1e20509d08b'
    '9588000000c1ea1009d0837d1820750c5152e8800200005a59abeb0266ab8b85'
    '8c0000000185800000008b85900000000185840000008b859400000001858800'
    '00004975a05b5ec383f9007504c1e80bc383f9017507c1e80583e03fc383e01f'
    'c352565753898594000000898d880000008b4504c1e8057505b8010000008985'
    '8c00000031c089457489457889457c894570c7456400000000bb410000008b85'
    '94000000c1e81089859000000031d289d00faf45000385900000008d34000375'
    '340fb7065052e813feffff83f8047703ff45645a588d7d74e85a010000ff4570'
    '03958c0000003b550472c48b85880000000185940000004b75a48b4d708d7d74'
    'e84d0100008985a00000008b45646bc0048b4d706bc90339c8720fc785a00000'
    '0000000000e99d0000008b85880000006bc041298594000000c7457c00000000'
    'bb410000008b8594000000c1e81089859000000031d289d00faf450003859000'
    '00008d34000375340fb706e86f00000001457c03958c0000003b550472d88b85'
    '880000000185940000004b75b88b457c31d2f7757083f802762d8b85a0000000'
    '89c2c1ea0b89d189c2c1ea0683e21f01d189c283e21f01d183f9087716c785a0'
    '000000000000008b85a00000005b5f5e5af9c38b85a00000005b5f5e5af8c351'
    '52568bb5a000000089c1c1e90b89f2c1ea0b29d1e83700000089ca89c1c1e906'
    '83e11f5289f2c1ea0683e21f29d1e81d0000005a01ca89c183e11f5289f283e2'
    '1f29d1e8080000005a8d040a5e5a59c385c97902f7d9c35289c2c1ea0b011789'
    'c2c1ea0583e23f01570483e01f0147085ac351528b0731d2f7f1c1e00b508b47'
    '0431d2f7f1c1e0055a09d0508b470831d2f7f15a09d05a59c385c97419837d18'
    '20740666ab4975fbc35253e8070000005b5aab4975fcc35589c389c281e300f8'
    '000081e2e007000083e01f89ddc1e308c1e50381e50000070009eb89d5c1e205'
    'd1ed81e50003000009ea89c5c1e003c1ed0209e809d809d05dc33b56240f852e'
    '01000050535256575589e981ecd002000089e5894d04895d3489c1d1e9894d00'
    '8b460c8945088b460889450c8b46108945108b46248945148b46548945188b7d'
    '148b550c8b4d10c1e90231c057f3ab5f037d104a75ee8b45080faf45048b4d0c'
    '0faf4d0039c8761289c831d2f7750489451c8b450c894520eb0e31d2f7750089'
    '45208b450889451c8b4500c1e01031d2f7751c8945248b4504c1e01031d2f775'
    '20894528c7452c000000008b450c2b4520d1e80faf45100345148b4d082b4d1c'
    'd1e9837d18207502d1e18d04488945388b45208945308b452cc1e8100faf4500'
    '8d34000375348b7d3831d28b4d1c52c1ea100fb70456837d1820740466abeb08'
    '51e8b1feffff59ab5a0355244975df8b452801452c8b4510014538ff4d3075b6'
    'e8aff7ffff8da5d00200005d5f5e5a5b5801c3c3'
)
FULLWIN_BLOB = bytes.fromhex(
    'e91a000000e91a020000e8000000005b81eb0f00000089de81ebe7e7e7e7c355'
    '89e581ecb0000000535657e8daffffff83be64030000007505e8b20100008d45'
    'f050ffb3f8230100ff9340f100008d45f050ffb3f8230100ff933cf100008d45'
    'f850ffb3f8230100ff933cf100008b75f82b75f08b7dfc2b7df48b8b18240100'
    '2b8b10240100894dc08b931c2401002b93142401008955bc89f00fafc289f90f'
    'af4dc039c8720f897db489c831d2f775bc8945b8eb0b8975b831d2f775c08945'
    'b489f02b45b8d1e80345f08945e00345b88945e889f82b45b4d1e80345f48945'
    'e40345b48945ec8dbd50ffffff31c0b919000000f3abc78550ffffff64000000'
    '8b45f08945d08b45f48945d48b45f88945d88b45e48945dce8a20000008b45ec'
    '8945d48b45fc8945dce8910000008b45e48945d48b45e08945d88b45ec8945dc'
    'e87a0000008b45e88945d08b45f88945d8e8690000008b83502501008b086a00'
    '68000000018d931024010052ffb3542501008d55e05250ff51148983c41f0100'
    'e885feffffe8180000008986680300008b83c41f01005f5e5b89ec5d83c410c2'
    '04008b866403000083f8ff740f85c0740a83ec0854ffd05883c404c331c0c38b'
    '45d83b45d07e288b45dc3b45d47e208b83502501008b088d9550ffffff526800'
    '0400016a006a008d55d05250ff5114c3c78664030000ffffffff8d863f030000'
    '50ff9314f1000085c074188d8e4c0300005150ff93acf0000085c07406898664'
    '030000c35589e583ec40535657e8d8fdffff6af0ff7508ff9338f10000a90000'
    '00800f84b50000008d860603000050ff9314f1000085c00f848800000089c78d'
    '86110300005057ff93acf0000085c074748d4dd051ffd085c0746a8d861e0300'
    '005057ff93acf0000085c074586a02ff75d4ff75d0ffd085c0744a8945cc8d86'
    '2f0300005057ff93acf0000085c07435c745d8280000008d4dd851ff75ccffd0'
    '85c074216a018b45e82b45e0508b45e42b45dc50ff75e0ff75dcff7508ff932c'
    'f10000eb18ff751cff7518ff7514ff7510ff750cff7508ff932cf100005f5e5b'
    '89ec5dc218007573657233322e646c6c00476574437572736f72506f73004d6f'
    '6e69746f7246726f6d506f696e74004765744d6f6e69746f72496e666f41006b'
    '65726e656c33322e646c6c005175657279506572666f726d616e6365436f756e'
    '746572000000000000000000'
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
FRAMETRACE_BLOB = bytes.fromhex(
    'e92f000000e9000000005152ff15e1e7e7e7e8000000005a81ea170000008982'
    '870200008b828f0200008b005a59ff25e2e7e7e760e8000000005d81ed3a0000'
    '008b8d7b02000085c97514ff7628ff7624e8ad00000083c4088b8d7b02000083'
    'f9ff0f849300000031d28b8d9b0200008339000f95c28b8d970200008339000f'
    '95c10fb6c98d14518b8d930200008339000f95c10fb6c98d14518b8d8f020000'
    '8339000f95c10fb6c98d145183ec6089e752ff742474ffb4248400000031c98b'
    '958b02000085d274028b0a51ffb5870200008d85260300005057ff9583020000'
    '83c41c6a008d4c2454515057ffb57b020000ff957f02000083c460615f89461c'
    '5e5bc353565781ec1c010000c7857b020000ffffffff8b1de4e4e4e4a1e3e3e3'
    'e3898424180100008d859f02000050ff94241c01000085c00f843301000089c6'
    '8d85f40200005056ffd385c00f841f01000089857f0200008d85ac02000050ff'
    '94241c01000085c00f84030100008d8dfe0200005150ffd385c00f84f1000000'
    '8985830200008d85ca0200005056ffd385c074298d8ddb02000051ffd085c074'
    '1c80b87b4d0000e975138b887c4d00008d8408e3e7e7e789858b0200008d85b7'
    '0200005056ffd385c00f84a200000068040100008d4c2404516a00ffd085c00f'
    '848c0000008d3c0439e774074f803f5c75f6478d8d080300008a018807414784'
    'c075f68d85e80200005056ffd385c074606a0068800000006a026a006a016800'
    '0000408d4c241851ffd083f8ff744289857b02000089c7ffb42430010000ffb4'
    '24300100008d8513030000508d44240c50ff958302000083c4106a008d8c2418'
    '01000051508d44240c5057ff957f02000081c41c0100005f5e5bc30000000000'
    '000000000000000000000000000000f3f3f3f3f4f4f4f4f5f5f5f5f6f6f6f66b'
    '65726e656c33322e646c6c007573657233322e646c6c004765744d6f64756c65'
    '46696c654e616d6541004765744d6f64756c6548616e646c6541004d47616d65'
    '4433442e646c6c0043726561746546696c654100577269746546696c65007773'
    '7072696e746641006672616d65732e6c6f670062756467657420257520717063'
    '2025750d0a0025752025752025752025752025750d0a00'
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
    'e923000000e980000000e9e4070000e9be080000e911090000e956090000e800'
    '0000005b83eb23c3535657e8eeffffffe8350200008b742414e834010000723f'
    '31c9837c2418007524e8330100008b7c241c85ff74173b4c242076048b4c2420'
    '516bc90d8db384290000f3a5598b54242485d27402890a31c05f5e5bc21800b8'
    '570007805f5e5bc21800535657e88cffffffe8d30100008b742414e8d2000000'
    '0f82c100000089c78b74241885f6742266813e445a751b83c602e85b0400003d'
    '102700007605b8102700008984bb7c2100006bc7348d941814210000b90d0000'
    '0066c702000066c74202ff0083c2044975ef8b74241c8b4c242085c9745c8b06'
    '83f80d734f6bd7348d14828d9413142100008b46143d00010000730f85c07434'
    '66833a00752e668902eb293d0003000072223d80030000731b66817a02ff0075'
    '1383e03f83f83f740ba92000000075046689420283c63449eba0e8d903000031'
    'c05f5e5bc21400b8570007805f5e5bc214000fb60683e83083f8017702f8c3f9'
    'c35256575589c58dbb842900006bf0348db4331421000031c931d2520fb70651'
    '89d1e88c00000059410fb746023dff000000740fe86b0000005189d1e8720000'
    '0059415a83c6044283fa0d72ce6bf5088db433e020000031d20fb70605000400'
    '00510fb68c130d210000e844000000594183c6024283fa0472df8db3f0200000'
    'ba080000000fb64601e816000000510fb60ee81c000000594183c6024a75e65d'
    '5f5e5ac35189e9c1e10601c8050003000059c3515089c8ab31c083f902721383'
    'f905770eb80a000000abb803000000abeb02abab31c0abb810270000ab58ab31'
    'c0b907000000f3ab59c383bb6c0c0000000f859c00000060e875080000c7836c'
    '0c0000010000008d4319a3edededed8db3782000008dbb14210000b91a000000'
    'f3a5c7837c210000e8030000c78380210000e80300006a036800000080e8c404'
    '000083f8ff744b89c68d83842100006a008d8b7c0c00005168ff0700005056ff'
    '934c0c000056ff93580c00008b837c0c0000c68418842100000031c081bb8421'
    '0000646973707505b864000000e80200000061c38db41884210000c783740c00'
    '00ffffffffe895010000750e803e000f844a010000e933010000803e5b756cc7'
    '83740c0000ffffffff0fb6460183e83183f8010f8714010000807e02500f850a'
    '0100008983780c000089fee84f0100000f84f7000000c783740c000001000000'
    '803e430f84e4000000c783740c000000000000803e4b0f84d1000000c783740c'
    '0000ffffffffe9c200000083bb740c0000ff0f84b500000083f9087544813e44'
    '656164753c817e047a6f6e65753383bb740c0000010f859200000089fee8b400'
    '00000f8485000000e82d010000e8bd0000008b93780c00008984937c210000eb'
    '6c8d93a81f00006a0de8d7000000785d5089fee87e000000745083bb740c0000'
    '01741d8d93a80d00006800010000e8b200000078355ae845000000668906eb2d'
    'b8ff00000083f9017505803e2d740f8d93a81d00006a20e889000000780c5ae8'
    '1c00000066894602eb0383c40489fe8a0684c0740a463c0a75f5e9a6feffffc3'
    '508bb3780c00006bf6348d34968db4331421000058c3e824000000741183f901'
    '750c803e3d750789fee811000000c36bc0643d282300007605b828230000c331'
    'c98a063c2074083c0974043c0d750346ebef89f78a0784c074083c2076044741'
    'ebf285c9c356575189d731c05657518a163a17750f46474975f5803f00750559'
    '5f5eeb10595f5e83c710403b44241072db83c8ff595f5ec2040031c0803e2075'
    '0346ebf80fb61683ea3083fa0977086bc00a01d046ebedc360e8b40500008dbb'
    '842100008db3fd060000e87d01000031edc783740c000001000000b00aaab05b'
    'aa8d4531aab050aab020aa8db36307000083bb740c00000174068db36e070000'
    'e847010000b05daab00aaa83bb740c000001751a8db377070000e82d0100008b'
    '84ab7c210000e82a010000b00aaa31d20fb68413002100003dff000000746b50'
    'c1e0048db418a81f0000e8fd0000008db382070000e8f2000000586bf5348d34'
    '868db4331421000083bb740c00000175210fb746023dff0000007505b02daaeb'
    '23c1e0048db418a81d0000e8bc000000eb120fb706c1e0048db418a80d0000e8'
    'a8000000b00aaa42eb86ff8b740c00000f8925ffffff4583fd020f8211ffffff'
    '578d83a40c0000506a208d8343070000508d8342070000508d8337070000508d'
    '832f07000050ff93640c00005f80bb430700000074198db316070000e84b0000'
    '008db343070000e840000000b00aaa8db38421000029f76a0468000000c0e8e3'
    '00000083f8ff742289c56a008d8b7c0c000051575655ff93500c000055ff9360'
    '0c000055ff93580c000061c3ac84c07403aaebf8c35152b96400000031d2f7f1'
    'b220881747b90a00000031d2f7f185c074030430aa88d00430aa5a59c33b2053'
    '4547412052414c4c59203220636f6e74726f6c730a000a5b446973706c61795d'
    '0a5265736f6c7574696f6e203d2000446973706c6179005265736f6c7574696f'
    '6e00000000000000000000000000000000000000000000000000000000000000'
    '000000436f6e74726f6c6c6572004b6579626f61726400446561647a6f6e6520'
    '3d00203d200056578dbba40c00006804010000576a00ff935c0c000089fe8a07'
    '84c07409473c5c75f589feebf1c7065352322ec74604434647006a0068800000'
    '00ff7424186a006a03ff7424208d83a40c000050ff93480c000083f8ff740f50'
    '6a006a006a0050ff93540c0000585f5ec2080060e825f8ffff8d83e6e6e6e689'
    '44241c8b4424240fb6700c83ee3083fe01771485f6750ba1e9e9e9e98983700c'
    '0000e80900000061c1c1c1c1c1c1ffe0e8bd0200008b83680c000083f8017667'
    '0fb68c33800c000085c9741c49e86b00000085c07466c68433800c000000c684'
    '33820c00003ceb3ffe8c33820c00007936c68433820c00003c31c98d41018d56'
    'fff7da3a8413800c00007415e82c00000085c0750c8d4101888433800c0000eb'
    '1b4183f90472d48dbb880c00006bc61001c731c08907894704894708c3516bc6'
    '108d8418840c00005051ff93680c000059c3535657e844f7ffff8b44241031d2'
    '80b8600200000375068b90080300008b4c2414e8b4000000731c8b4c241c85c9'
    '740289118b4c241885c97402890131c05f5e5bc210008d93e8e8e8e85f5e5bc2'
    'c2c2c2c2c2c2c2c2ffe2535657e8ecf6ffff8b44241031d28078080375048b54'
    '24148b4c2418e861000000731c8b4c242085c9740289118b4c241c85c9740289'
    '0131c05f5e5bc214008d83ecececec5f5e5bffe0535657e8a2f6ffff8b4c2410'
    '31d2e825000000720731c0ba800000008b4c241885c9740289118b4c241485c9'
    '7402890131c05f5e5bc20c0081e90003000081f980000000723181e900010000'
    '81f9000100007202f8c331c085d2741483bb700c000000750b803c0a007405b8'
    '80000000ba80000000f9c389cec1ee0683e13f83f93f741df7c1200000007415'
    '83e1df83bb700c000000740931c0ba80000000f9c3e802000000f9c36bfe108d'
    'bc3b840c000083f93f0f84ae00000083f91073190fb747040fa3c8b800000000'
    '7305b880000000ba80000000c383e91083f90273120fb6440f0683f81e730231'
    'c0baff000000c383e90283f908737b0fb6944b310c00000fbf041780bc4b320c'
    '0000007502f7d885c07f0831c0ba10270000c3508b84b37c21000069c0ff7f00'
    '00b91027000031d2f7f189c15829c87f0831c0ba10270000c369c010270000f7'
    'd981c1ff7f000031d2f7f13d102700007605b810270000ba10270000c38b84b3'
    '7c210000ba10270000c331c0ba10270000c383bb440c000000757860c783440c'
    '0000010000008d83740b000050ff93e3e3e3e389c68dbb480c00008dab810b00'
    '005556ff93e4e4e4e4ab45807dff0075f9807d000075ea8dabf50b000055ff93'
    'e3e3e3e385c074128d8b220c00005150ff93e4e4e4e485c0751245807dff0075'
    'f9807d000075d6b8010000008983680c000061c36b65726e656c33322e646c6c'
    '0043726561746546696c6541005265616446696c6500577269746546696c6500'
    '53657446696c65506f696e74657200436c6f736548616e646c65004765744d6f'
    '64756c6546696c654e616d654100536574456e644f6646696c65004765745072'
    '697661746550726f66696c65537472696e6741000078696e707574315f342e64'
    '6c6c0078696e707574315f332e646c6c0078696e707574395f315f302e646c6c'
    '000058496e707574476574537461746500080008010a010a000c000c010e010e'
    '0090909000000000000000000000000000000000000000000000000000000000'
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
    '0000000000000000'
)
WIDE_BLOB = bytes.fromhex(
    'e917000000e95b000000e9cf000000e8000000005b81eb14000000c360e8edff'
    'ffffe8fa000000618b44240c3905f7f7f7f775305351e8d4ffffff8b8b140200'
    '003b8b1c02000075178b8b180200003b8b200200007509595b3905f7f7f7f7c3'
    '595b85e4c35351e8a3ffffffc705eeeeeeee80020000c705efefefefe0010000'
    '31c985c07416c705eeeeeeee20030000c705efefefef58020000eb228b8b1402'
    '000085c97418890deeeeeeee8b8b18020000890defefefef8b8b14020000898b'
    '1c0200008b8b1802000083bb1c02000000750231c9898b20020000595bc360e8'
    '2bffffffe8380000008b8b140200003b8b1c020000750e8b8b180200003b8b20'
    '0200007412a1fbfbfbfbff7050bafcfcfcfcffd283c40461a1fbfbfbfb8b4850'
    'c3c7831402000000000000c78318020000000000008dbb440200006804010000'
    '576a00ff15f9f9f9f989fe8a0784c07409473c5c75f589feebf1c7065352322e'
    'c74604434647008d8344020000506a208d8324020000508d8311020000508d83'
    '06020000508d83fe01000050ff15f8f8f8f88db324020000e841000000723e89'
    'c7803e787405803e58753246e82d000000722a8db34803000083c6108b0e85c9'
    '741b39f97512394604750d89bb14020000898318020000c383c608ebdfc331c0'
    '31c90fb61683ea3083fa0977096bc00a01d04641ebec85c97402f8c3f9c34469'
    '73706c6179005265736f6c7574696f6e00009090000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000'
)
WIDE_US_BLOB = bytes.fromhex(
    'e917000000e95b000000e9ec000000e8000000005b81eb14000000c360e8edff'
    'ffffe817010000618b44240c3905f7f7f7f775305351e8d4ffffff8b8b300200'
    '003b8b3802000075178b8b340200003b8b3c0200007509595b3905f7f7f7f7c3'
    '595b85e4c35351e8a3ffffffc705eeeeeeee80020000c705efefefefe0010000'
    '31c985c07433c705eeeeeeee20030000c705efefefef58020000833dfafafafa'
    '007438c705eeeeeeee00040000c705efefefef00030000eb228b8b3002000085'
    'c97418890deeeeeeee8b8b34020000890defefefef8b8b30020000898b380200'
    '008b8b3402000083bb3802000000750231c9898b3c020000595bc360e80effff'
    'ffe8380000008b8b300200003b8b38020000750e8b8b340200003b8b3c020000'
    '7412a1fbfbfbfbff7050bafcfcfcfcffd283c40461a1fbfbfbfb8b4850c3c783'
    '3002000000000000c78334020000000000008dbb600200006804010000576a00'
    'ff15f9f9f9f989fe8a0784c07409473c5c75f589feebf1c7065352322ec74604'
    '434647008d8360020000506a208d8340020000508d832e020000508d83230200'
    '00508d831b02000050ff15f8f8f8f88db340020000e841000000723e89c7803e'
    '787405803e58753246e82d000000722a8db36403000083c6108b0e85c9741b39'
    'f97512394604750d89bb30020000898334020000c383c608ebdfc331c031c90f'
    'b61683ea3083fa0977096bc00a01d04641ebec85c97402f8c3f9c3446973706c'
    '6179005265736f6c7574696f6e00009000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '00000000'
)
WIDE2D_BLOB = bytes.fromhex(
    'e928000000e927000000e926000000e92e000000e936000000e93e000000e922'
    '020000e9b6020000e9d50d00006a04eb366a03eb32ff74240c810c2400000040'
    'eb25ff74240c810c2400000060eb18ff74240c810c2400000050eb0bff74240c'
    '810c24000000485553e8c201000083bb2c100000000f853f010000e86f040000'
    '81bd1c120100c40100000f852a0100008b4c240881e1ffffff8781f900080000'
    '0f871401000081bdfc23010080020000751081bd00240100e00100000f84f800'
    '000056578b74241c83f9047505e8490200008dbb2016000051c1e103f3a5598d'
    'bb2016000089fedb8500240100d8b3c80f0000db85fc230100d9c1d88bc40f00'
    '00dee9d88bcc0f0000d993dc0f0000d9c1d99be00f000051d906d89bcc0f0000'
    'dfe09e7307810c2400000100d906d89bd00f0000dfe09e7207810c2400000200'
    '83c6204975d259f7c1000001007432f7c100000200742a81e1ffff0000ddd8db'
    '85fc230100d8b3c40f0000d907d8c9d91fd94704d8cad95f0483c7204975eceb'
    '29898be40f000081e1ffff000051d907d8cad8c1d91fd94704d8cad95f0483c7'
    '204975ea59e842060000ddd8ddd88d83201600008944241c5f5e8b442408a900'
    '000040751b8b952012010083f804740881c5d6500000eb5181c526510000eb49'
    '8b8d64270100a9000000207532a9000000107513a90000000875188b44241881'
    'c5ea4f0000eb228b44241881c53a500000eb168b44241881c58a500000eb0a8b'
    '44242081c57a510000896c24085b5dc3e8000000005b81eb3502000089dd81ed'
    'e7e7e7e7c35355e8e4ffffff81bdfc2301008002000076738b44241081780880'
    '0200007f6681780ce00100007f5d56575189c68dbb4c070000b908000000f3a5'
    '8dbb4c07000031c98b048ff7c10100000075150faf85fc230100529951b98002'
    '0000f7f9595aeb130faf8500240100529951b9e0010000f7f9595a89048f4183'
    'f90472c4897c241c595f5e8d85496000005d5b83ec08568b74241457ffe05355'
    'e84bffffff5657518db3141300008dbb98140000b961000000f3a5c783941400'
    '0000000000595f5e8b850c2401008d95584d00005d5b83ec10ffe25157b90400'
    '0000e8c9000000d98314100000d8a310100000d99b201000008dbb141300008b'
    '9394140000e826010000734283fa100f83980000008b83201000008907c74704'
    '000000008b83101000008947088b831410000089470c8b83181000008947108b'
    '831c100000894714ff8394140000ff4704d98310100000d85f08dfe09e73098b'
    '8310100000894708d98314100000d85f0cdfe09e76098b831410000089470cd9'
    '8318100000d85f10dfe09e73098b8318100000894710d9831c100000d85f14df'
    'e09e76098b831c1000008947145f59c356518b06898310100000898314100000'
    '8b460489831810000089831c100000d906d89b10100000dfe09e73088b068983'
    '10100000d906d89b14100000dfe09e76088b06898314100000d94604d89b1810'
    '0000dfe09e73098b4604898318100000d94604d89b1c100000dfe09e76098b46'
    '0489831c10000083c6204975a2595ec35189d1e31ad98320100000d827d9e1d8'
    '9bd80f0000dfe09e720883c718e2e6f959c3f859c357528dbb981400008b9318'
    '160000e8c8ffffff7242837f0406723bd94708d89bcc0f0000dfe09e772dd947'
    '0cd89bd00f0000dfe09e721fd94710d89bcc0f0000dfe09e7711d94714d89bd4'
    '0f0000dfe09e7203f8eb01f95a5fc383bb3d070000000f84c700000083bb4807'
    '0000000f84ba000000ff8b48070000608dbb6c0700008db3ef060000e88a0100'
    '008b44242c89c181e1ffff0000b27183f9047426b274a900000040741db26ca9'
    '000000207402b269a9000000107402b273a9000000087402b26688d0aab020aa'
    '8b851c120100e82301000089c8e81c0100008b442430e8130100008b7424388b'
    '06e8080100008b4604e8000100008b4608e8f80000008b8524120100e8ed0000'
    '0031c08b8d2412010081f98000000073078b848b94100000e8d1000000e8f200'
    '000061c383bb3d07000000747483bb4807000000746bff8b48070000608dbb6c'
    '0700008db3f6060000e8bd0000008b8334100000e8950000008b8524120100e8'
    '8a0000008b8338100000e87f0000008b83e80f0000e8740000008b83f40f0000'
    'e8690000008b83ec0f0000e85e0000008b83f00f0000e853000000e874000000'
    '61c383bb3d07000000744283bb48070000007439ff8b48070000608dbb6c0700'
    '008db3fd060000e83f0000008db33c100000b9080000008b065156e80e000000'
    '5e5983c604e2f0e82800000061c351b908000000c1c0045083e00f8a84032407'
    '0000aa58e2eeb020aa59c3ac84c07403aaebf8c3c6070083bb44070000007521'
    '8d830407000050ff9514f100008d8b110700005150ff95acf000008983440700'
    '008d836c07000050ff9344070000c37372322064200073723220622000737232'
    '207420006b65726e656c33322e646c6c004f7574707574446562756753747269'
    '6e67410030313233343536373839616263646566443344545241434500000000'
    '009090900000000060ea00000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000008b83e40f000025000003000f84e50100003d0000'
    '03000f84da01000083f9040f87d101000056578b742428d906d993e80f0000d9'
    '9bf40f0000d94604d993ec0f0000d99bf00f00008b46188983f80f00008983fc'
    '0f00008b461c89830010000089830410000051d94604d89bec0f0000dfe09e73'
    '128b46048983ec0f00008b461c898300100000d94604d89bf00f0000dfe09e76'
    '128b46048983f00f00008b461c898304100000d906d89be80f0000dfe09e7311'
    '8b068983e80f00008b46188983f80f0000d906d89bf40f0000dfe09e76118b06'
    '8983f40f00008b46188983fc0f000083c620490f857affffff59d983f40f0000'
    'd8a3e80f0000d99320100000d9c0d89bb40f0000dfe09e7773d983f00f0000d8'
    'a3ec0f0000d89bb40f0000dfe09e775ce880fbffff7251d9c0d89bcc0f0000df'
    'e09e724483bd4012010000751351528b4c242c8b116a0151ff92f80000005a59'
    'd983fc0f0000d8a3f80f0000def1d99b08100000d983dc0f0000d8b3e00f0000'
    'd99b0c100000eb0dddd8eb74ddd8e870000000eb6b8b7424288dbb20160000d9'
    '06d89bcc0f0000dfe09e731cc70700000000d906d8830c100000d88b08100000'
    'd86f18d95f18eb2fd906d89bd00f0000dfe09e7222db85fc230100d91fd983c4'
    '0f0000d8830c100000d826d88b08100000d84718d95f1883c62083c72049759f'
    '5f5ec3c7833810000000000000c783341000000100000083f9040f858c030000'
    'c7833410000002000000d983f00f0000d8a3ec0f0000d89bb80f0000dfe09e0f'
    '8267030000c78334100000030000008b85241201003d800000000f834c030000'
    '8b848394100000898338100000c783341000000400000085c00f842d030000c7'
    '8334100000050000005657d99b60100000d99b5c1000008b7424348dbb941200'
    '00b9040000008b56088957088b560c89570c31d289571483c7204975e98dbb94'
    '1200008b461083bb38100000027407e8de020000eb0525000000ff8947108947'
    '30894750894770d983ec0f0000d88be00f0000d95704d95f24d983f00f0000d8'
    '8be00f0000d95744d95f648b830010000089471c89473c8b830410000089475c'
    '89477cf783e40f000000000100745131c08907894740d9eee8a9020000d99b70'
    '100000d983e80f0000d88be00f0000d883dc0f0000d95720d95f60e8af020000'
    'd983f40f0000d8d1dfe09e7304ddd9eb02ddd8e86e020000d99b74100000eb76'
    'db85fc230100d95720d95f60d983c40f0000e84f020000d99b74100000d983c4'
    '0f0000d983f40f0000d8d1dfe09e7608ddd8d983c40f0000d88be00f0000d883'
    'dc0f0000d917d95f40ddd8d983c40f0000e839020000dee9d983e80f0000d8d1'
    'dfe09e7604ddd9eb02ddd8e8f6010000d99b701000008b852412010089833010'
    '0000c7832c1000000100000083bb3810000002754d8b4c24308b116aff51ff92'
    'ac0000008b83701000008947188947588b83741000008947388947788b4c2430'
    '8b115751ff92b40000008b4c24308b11ffb33010000051ff92ac000000e93201'
    '00008b85341201008983801000008b4c24308b116a0151ff92fc0000008b4c24'
    '308b116a026a0251ff92ec0000008b854012010089838410000085c0740f8b4c'
    '24308b116a0051ff92f80000008b4c24308b116a0151ff92e80000008b837010'
    '00008947188947588b8374100000894738894778d98304100000d8a300100000'
    'd88bbc0f0000d983f00f0000d8a3ec0f0000def9d99378100000d88bc00f0000'
    'd99b7c100000b90800000051d98300100000d8837c100000d9571cd95f3cd983'
    '04100000d8837c100000d9575cd95f7cd9837c100000d88378100000d99b7c10'
    '00008b4c24348b115751ff92b4000000594975b78b4c24308b11ffb380100000'
    '51ff92e80000008b4c24308b116a066a0551ff92ec00000083bb841000000074'
    '138b4c24308b11ffb38410000051ff92f8000000c7832c10000000000000d983'
    '5c100000d983601000005f5ee833f8ffffc351525689c631d2b90000000089f0'
    'd3e825ff0000006bc00ac1e808d3e009c283c10883f91872e589f025000000ff'
    '09d05e5a59c3d8a3e80f0000d983fc0f0000d8a3f80f0000dec9d983f40f0000'
    'd8a3e80f0000def9d883f80f0000c3d983c40f0000d88bdc0f0000dab5fc2301'
    '00c35553e827f4ffff31c089835810000089834410000089834810000089834c'
    '10000089835010000089b340100000c7833c1000000100000081fe800000000f'
    '83ef000000c784b3941000000000000056578b7c240c8b4708898344100000c7'
    '833c10000002000000a9001700000f85be00000083e0088983641000008b4704'
    '8983481000000fafc085c0c7833c100000030000000f84970000008983681000'
    '00c7836c100000000000008b370fb70689834c1000008b8b681000000fb70683'
    'c602e889000000724f01d001f883f8067706ff836c1000004975e18b936c1000'
    '00c1e2028b8b681000006bc903b80100000039ca7205b8020000008983581000'
    '008b4c240489848b94100000c7833c10000005000000eb1a0fb746fe89835010'
    '0000898b54100000c7833c100000040000005f5e31c0b91f0000008d7c2428f3'
    'abe8fcf6ffff8d95294100005b5dffe283bb6410000008741ca9008000007452'
    '89c2c1ea0583e21f89c783e71fc1e80a83e01ff8c389c2c1ea0c83fa0f753389'
    'c2c1ea0483e20f89c783e70fc1e80883e00fe81000000092e80a0000009297e8'
    '0300000097f8c35289c2c1ea038d04425ac3f9c3000000430000204300008040'
    '000060c0000020440000f0430000003f00c01f440080ef430000803f00000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '00000000424152464c4147000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000046494c4c5441424c45000000000000000000000000000000'
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
    '0000000000000000000000000000000000000000000000000000000090909090'
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
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
)
WIDEGL_BLOB = bytes.fromhex(
    'e957000000e94f010000e8000000005b81eb0f00000089dd81ede7e7e7e7c38b'
    '832004000085c075178d833a03000050ff958c00010085c07420898320040000'
    'db80fc230100d99b24040000db8000240100d99b28040000f8c3f9c3535551e8'
    'a6ffffffe861010000e8b1ffffff0f82a9000000d98324040000d89b00040000'
    'dfe09e0f86940000008b4c24148b8320040000833900752283790400751c8b80'
    'fc23010039410875118b83200400008b800024010039410c7463565789ce8dbb'
    '2c04000031c9db048ee869000000db1c8f4183f90472ef897c241cdb442420d8'
    '8b28040000d8b304040000d98328040000d88b0c040000d8ab24040000d88b10'
    '040000dec1db5c2420b901000000db442424e820000000db5c24245f5ee8ff00'
    '0000598d85ca3700005d5b5589e583ec2889742404ffe0f7c101000000750dd8'
    '8b24040000d8b300040000c3d88b28040000d8b304040000c35355e8aafeffff'
    '8b44241089837c030000e8b0feffff7241d98324040000d8b328040000d88b08'
    '040000d9c0d89b14040000dfe09e7620db442410d88b18040000d9f2ddd8dec9'
    'd9e8d9f3d88b1c040000db5c2410eb02ddd8e8af0000008d85793800005d5b55'
    '89e583ec18891c24ffe083bb7203000000744d608dbb800300008db313030000'
    'e8ea0000008b742438b904000000ade8be000000e2f88b44243ce8b30000008b'
    '442440e8aa0000008b442430e8a10000008b442450e898000000e8b900000061'
    'c383bb7203000000743b608dbb800300008db31b030000e8930000008b742438'
    'b904000000ade867000000e2f88b44243ce85c0000008b442440e853000000e8'
    '7400000061c383bb72030000007442608dbb800300008db324030000e84e0000'
    '008b837c030000e8260000008b8324040000e81b0000008b8328040000e81000'
    '00008b442434e807000000e82800000061c351b908000000c1c0045083e00f8a'
    '84035a030000aa58e2eeb020aa59c3ac84c07403aaebf8c3c6070083bb780300'
    '000075218d832d03000050ff95ec0001008d8b470300005150ff958800010089'
    '83780300008d838003000050ff9378030000c373723220767020007372322076'
    '703e200073723220666f7620006b65726e656c33322e646c6c004d47616d6544'
    '33442e646c6c004f75747075744465627567537472696e674100303132333435'
    '36373839616263646566474c5452414345000000000090900000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '000020440000f0430000403fabaaaa3f0000003f0000803fdb0f493883f9a246'
    '00000000000000000000000000000000000000000000000000000000'
)
RESOLUTION_BLOB = bytes.fromhex(
    'e924000000e96b000000e922030000e9f3020000e8000000005b81eb19000000'
    '89dd81ede7e7e7e7c3535551e8e3ffffff8b85d3d3d3d38b505052e864040000'
    'e88d0300005a83f8027c0289c289d0e874020000895630894e34898b88050000'
    '8b84cbc4060000894670c7467405000000595d5bc383fb06741283fb070f8482'
    '0000008b449e3831ff85c0c353555657e87fffffff8b4e343b8b880500007417'
    '898b88050000c74630000000008b84cbc40600008946708b85d4d4d4d48b388b'
    '4718898390050000d94714d8460cd99b8c050000b906000000e8890100008983'
    '940500008b46308b4e340384cbc0060000e8b8020000b904000000e87c010000'
    'e95901000053555657e806ffffff8d85d7d7d7d78b78186a006a006a00837e10'
    '0775106a206a2068000100006800010000eb1468000100006800010000680001'
    '000068d8000000680000803f680000803f6a006a006a006800004041d94718d8'
    '8364050000d9939005000051d91c24d94714d8460cd9938c05000051d91c2457'
    '8d85d6d6d6d6ffd083c440d9838c050000d88368050000d99b8c050000d98390'
    '050000d8836c050000d99b90050000c78394050000000100008d83e7040000b9'
    '04000000e8b3000000d98370050000d8460cd99398050000d88374050000d99b'
    '8c050000b907000000e8790000008983940500008b4634e8eb00000052b90500'
    '0000e8750000008d83f4040000b904000000e865000000d98390050000d8a378'
    '050000d99b900500008d83f4040000e848000000d98390050000d88378050000'
    'd99b90050000d98398050000d8837c050000d99b8c05000058e81e0000005f5e'
    '5d5b31ff31c0c3b800010000394e10750a8b4678d1f80580000000c351518d8d'
    'dcdcdcdc51680001000068000100006800010000ffb394050000680000803f68'
    '0000803f68000020416800002041ffb390050000ffb38c050000508d85dbdbdb'
    'dbffd083c43459c331c989c22b94cbc00600003b94cbc4060000720a4183f905'
    '72e831c931d2c38d93f604000001c085c0740a42807aff0075f948ebf289d042'
    '807aff0075f9c35355e806fdffff8b4850894e30c7463400000000c783880500'
    '00000000008b8bc4060000894e705d5bc35355e8dcfcffff8b46308b4e340384'
    'cbc00600008b95d3d3d3d383f802720231c0894250e84a010000e80e0100008b'
    '46308b4e340384cbc0060000e83d000000565789c68dbb9c050000ac3c587502'
    'b078aa84c075f45f5e8d8bbc050000518d839c050000508d8317050000508d83'
    '0f05000050ff93840500005d5bc38d93ec060000833a00740583c208ebf683c2'
    '0885c0740a42807aff0075f948ebf289d0c35657e8940000008d83bc05000050'
    '6a208d839c050000508d8322050000508d8317050000508d830f05000050ff93'
    '800500008db39c050000e83e000000723689c7803e787405803e58752a46e82a'
    '00000072228db3ec06000031c98b1685d2741439fa7505394604740683c60841'
    'ebeb89c85f5ec383c8ff5f5ec331c031c90fb61683ea3083fa0977096bc00a01'
    'd04641ebec85c97402f8c3f9c356578dbbbc0500006804010000576a00ff95e5'
    'e5e5e589fe8a0784c07409473c5c75f589feebf1c7065352322ec74604434647'
    '005f5ec383bb80050000007539568d832305000050ff95e3e3e3e389c68d8330'
    '0500005056ff95e4e4e4e48983800500008d83490500005056ff95e4e4e4e489'
    '83840500005ec341535045435420524154494f002e0034003300313600313000'
    '313600390032310039003332003900446973706c6179005265736f6c7574696f'
    '6e00006b65726e656c33322e646c6c004765745072697661746550726f66696c'
    '65537472696e67410057726974655072697661746550726f66696c6553747269'
    '6e6741000000d8410000204100000040000087430000e0410000c04000000842'
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
    'LOCKDESC': 0xF1F1F1F1,
    'SETTEXTCOLOR': 0xF2F2F2F2,
    'RUNNING': 0xF3F3F3F3,
    'PAUSED': 0xF4F4F4F4,
    'DEBUGDLL': 0xF5F5F5F5,
    'CATCHUP': 0xF6F6F6F6,
    'MODE': 0xF7F7F7F7,
    'GETPPS': 0xF8F8F8F8,
    'GETMODFN': 0xF9F9F9F9,
    'HIRES': 0xFAFAFAFA,
    'SETTINGS': 0xFBFBFBFB,
    'SETTER': 0xFCFCFCFC,
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
RESOLUTION_MAGICS = {
    'SETTINGS': 0xD3D3D3D3,
    'VALTAB': 0xD4D4D4D4,
    'TEXT': 0xDBDBDBDB,
    'GLYPHS': 0xDCDCDCDC,
    'LOADLIB': 0xE3E3E3E3,
    'GETPROC': 0xE4E4E4E4,
    'GETMODFN': 0xE5E5E5E5,
    'DRAW': 0xD6D6D6D6,
    'PLATES': 0xD7D7D7D7,
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


# The annex: one section appended to a file, grown by each patch

def _align(n, a):
    return (n + a - 1) // a * a


def append_section(buf, data, chars=CODE_SECTION | 0x80000040):
    """Places data in the file's annex, the `.sr2` section: appended when
    there is none, grown when there is - the last section can grow freely.
    Its characteristics are the union of what its data asks; the data is
    16-aligned within it. Returns (buffer, RVA)."""
    pe_off = struct.unpack_from('<I', buf, 0x3c)[0]
    nsec = struct.unpack_from('<H', buf, pe_off + 6)[0]
    opt = pe_off + 24
    opt_size = struct.unpack_from('<H', buf, pe_off + 20)[0]
    sect_align = struct.unpack_from('<I', buf, opt + 32)[0]
    file_align = struct.unpack_from('<I', buf, opt + 36)[0]
    headers = struct.unpack_from('<I', buf, opt + 60)[0]
    table = opt + opt_size
    last = table + (nsec - 1) * 40
    if buf[last:last + 8] == ANNEX.ljust(8, b'\0'):
        vsize, va, raw_size, raw, old_chars = (struct.unpack_from('<IIII', buf, last + 8)
                                              + struct.unpack_from('<I', buf, last + 36))
        if raw + raw_size != len(buf):
            raise ValueError('the annex is not at the end of the file')
        at = _align(vsize, 16)
        vsize, raw_size = at + len(data), _align(at + len(data), file_align)
        out = bytearray(buf[:raw + at]) + data + b'\0' * (raw_size - at - len(data))
        struct.pack_into('<II', out, last + 8, vsize, va)
        struct.pack_into('<I', out, last + 16, raw_size)
        struct.pack_into('<I', out, last + 36, old_chars | chars)
        struct.pack_into('<I', out, opt + 56, _align(va + vsize, sect_align))
        return out, va + at
    if table + (nsec + 1) * 40 > headers:
        raise ValueError('no room in the section table')
    last_vsize, last_va = struct.unpack_from('<II', buf, last + 8)
    rva = _align(last_va + last_vsize, sect_align)
    raw = _align(len(buf), file_align)
    raw_size = _align(len(data), file_align)
    out = bytearray(buf) + b'\0' * (raw - len(buf)) + data + b'\0' * (raw_size - len(data))
    struct.pack_into('<8sIIIIIIHHI', out, table + nsec * 40, ANNEX.ljust(8, b'\0'),
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
    out, rva = append_section(buf, MUSIC_BLOB)
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
def exe_blob(blob, build):
    """A stub with the build's addresses in place of the placeholders."""
    row = BUILDS[build]
    values = dict(row['addresses'], LOADLIB=row['slots']['LoadLibraryA'], GETPROC=row['slots']['GetProcAddress'],
                  SETTEXTCOLOR=row['slots']['SetTextColor'], GETPPS=row['slots']['GetPrivateProfileStringA'],
                  GETMODFN=row['slots']['GetModuleFileNameA'])
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
    out, rva = append_section(buf, exe_blob(ACTIVATE_BLOB, build), chars=CODE_SECTION)
    _branch(out, row['sites']['activate'], rva)
    return out


def apply_textcolor(buf, build):
    """The SetTextColor stub in the exe; the eight calls and two loads of
    the import slot become a call to it and a load of its address."""
    out, rva = append_section(buf, exe_blob(TEXTCOLOR_BLOB, build), chars=CODE_SECTION)
    base = struct.unpack_from('<I', out, struct.unpack_from('<I', out, 0x3c)[0] + 24 + 28)[0]
    for off, op in BUILDS[build]['textcolor']:
        if op == 'ff15':
            _branch(out, off, rva, 6)
        else:
            out[off:off + 6] = b'\xbe' + struct.pack('<I', base + rva) + b'\x90'
    return out


def apply_windowed(buf, build):
    """The .bg row copy in the exe through bgrow.asm."""
    out, rva = append_section(buf, exe_blob(BGROW_BLOB, build), chars=CODE_SECTION)
    _branch(out, BUILDS[build]['sites']['bgrow'], rva, BGROW_LEN)
    return out


def apply_altenter(buf, build):
    """altenter.asm in front of the window procedure's default handler.
    The annex keeps the user32 entry points it resolves, so it is writable."""
    row = BUILDS[build]
    _check_call(buf, row['sites']['altenter'], row['addresses']['HANDLER'], 'the text-input handler')
    out, rva = append_section(buf, exe_blob(ALTENTER_BLOB, build))
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
    out, rva = append_section(buf, blob, chars=CODE_SECTION | 0x80000000)
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
    out, rva = append_section(buf, stub + b'\xe9' + b'\0' * 4, chars=CODE_SECTION)
    start = _rva_to_off(out, rva)
    struct.pack_into('<i', out, start + len(stub) + 1, site_rva + 6 - (rva + len(stub) + 5))
    out[site:site + 6] = b'\x0f\x85' + struct.pack('<i', rva - (site_rva + 6))
    return out


MIX_STREAM = 51                                  # the second routine in mix.asm


def apply_mix(buf, build):
    """mix.asm in MGSound.dll: the buffer's SetRange loads min and max
    through the first routine (8 bytes), the streaming buffer's SetVolume
    finishes its mapping through the second (6 bytes, whose flags the
    branch after them tests)."""
    sites = BUILDS[build]['sites']['mix']
    out, rva = append_section(buf, MIX_BLOB, chars=CODE_SECTION)
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
# NAME_LEN bytes each. devices.asm reads it through MAGIC_BINDDATA.
NAME_LEN = 12
DATA_ROWACTS, DATA_DEFAULTS, DATA_VALUES, DATA_KEYNAMES, DATA_PADNAMES = 0, 16, 16 + 64, 16 + 64 + 2 * 9 * 2 * 16, 16 + 64 + 2 * 9 * 2 * 16 + 256 * NAME_LEN
DATA_SIZE = DATA_PADNAMES + 32 * NAME_LEN
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
        out[DATA_KEYNAMES + code * NAME_LEN:DATA_KEYNAMES + code * NAME_LEN + len(name)] = name.encode('ascii')
    for i, name in enumerate(PAD_NAMES):
        out[DATA_PADNAMES + i * NAME_LEN:DATA_PADNAMES + i * NAME_LEN + len(name)] = name.encode('ascii')
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
    out, got = append_section(buf, bytes(blob), chars=DATA_SECTION | 0x20000000)
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




def apply_voltrace(buf, build):
    """The diagnostic: five volume entry points jump into voltrace.asm,
    which reports and jumps back through a return-address table placed
    after the blob."""
    sites = BUILDS[build]['sites']['voltrace']
    blob = exe_blob(VOLTRACE_BLOB, build)
    out, rva = append_section(buf, blob + b'\0' * (4 * len(sites)), chars=CODE_SECTION)
    start = _rva_to_off(out, rva)
    text_off = _rva_to_off(out, 0x1000)
    for i, (off, length) in enumerate(sites):
        slot_va = IMAGE_BASE + rva + len(blob) + 4 * i
        struct.pack_into('<I', out, start + len(blob) + 4 * i, IMAGE_BASE + 0x1000 + off - text_off + length)
        out[start:start + len(blob)] = bytes(out[start:start + len(blob)]).replace(
            struct.pack('<I', 0xE7E7E7E1 + i), struct.pack('<I', slot_va))
        _branch(out, off, rva + 5 * i, length, op=b'\xe9')
    return out


def fullwin_stamp():
    """The offset in fullwin.asm's blob of the counter stamp its present
    keeps, the dword after its QueryPerformanceCounter pointer."""
    return FULLWIN_BLOB.index(b'QueryPerformanceCounter\0') + len(b'QueryPerformanceCounter\0') + 4


FRAMETRACE_STAMP = PRESENT_SITE + 5     # plus the stamp's offset: from the present to the stamp, via the jump's rel32


def apply_frametrace(buf, build):
    """The diagnostic: the frame gate's first five bytes and its last five
    before `pop ebx; ret` jump into frametrace.asm, which keeps the counter
    at the entry, logs the frame at the exit and leaves as the gate did.
    Two dwords after the blob hold the counter routine's address (from the
    `call` the exit site follows) and the gate's sixth byte; the blob's
    third placeholder becomes the borderless present's stamp, relative to
    the present. The annex is writable for the file handle."""
    (exit_site, entry_site), row = BUILDS[build]['sites']['frametrace'], BUILDS[build]
    gate = bytes(buf[entry_site:exit_site])
    for name in ('RUNNING', 'PAUSED', 'DEBUGDLL', 'CATCHUP'):
        if b'\xa1' + struct.pack('<I', row['addresses'][name]) not in gate:
            raise ValueError('the frame gate does not read %s where the row says' % name)
    if buf[exit_site - 5] != 0xe8:
        raise ValueError('no call before the frame gate\'s exit')
    text_off = _rva_to_off(buf, 0x1000)
    counter = IMAGE_BASE + 0x1000 + exit_site - text_off + struct.unpack_from('<i', buf, exit_site - 4)[0]
    blob = exe_blob(FRAMETRACE_BLOB, build)
    out, rva = append_section(buf, blob + b'\0' * 8)
    start = _rva_to_off(out, rva)
    slots = IMAGE_BASE + rva + len(blob)
    struct.pack_into('<II', out, start + len(blob), counter, IMAGE_BASE + 0x1000 + entry_site - text_off + 5)
    out[start:start + len(blob)] = blob.replace(struct.pack('<I', 0xE7E7E7E1), struct.pack('<I', slots)) \
        .replace(struct.pack('<I', 0xE7E7E7E2), struct.pack('<I', slots + 4)) \
        .replace(struct.pack('<I', 0xE7E7E7E3), struct.pack('<I', FRAMETRACE_STAMP + fullwin_stamp()))
    _branch(out, exit_site, rva, 5, op=b'\xe9')
    _branch(out, entry_site, rva + 5, 5, op=b'\xe9')
    return out


def apply_titlebg(buf, _build=None):
    """Title.dll's own .bg row copy through bgrow.asm's TITLE build. The
    site holds no absolute address, so no relocation entry goes."""
    out, rva = append_section(buf, TITLEROW_BLOB, chars=CODE_SECTION)
    _branch(out, TITLEROW_SITE, rva, TITLEROW_LEN)
    return out


def apply_widescreen(buf, build):
    """wide.asm in the exe, with the resolution table after it: the mode
    setter's compare and size stores and the screen-change routine's
    settings load call its three entries."""
    row = BUILDS[build]
    blob = WIDE_US_BLOB if build == 'American' else WIDE_BLOB
    out, rva = append_section(buf, exe_blob(blob, build) + resolution_table())
    modecheck, setsize, screen = row['sites']['wide']
    _branch(out, modecheck, rva, 10)
    _branch(out, setsize, rva + 5, 0x49 if build == 'American' else 42)
    _branch(out, screen, rva + 10, 8)
    return out


def apply_gltrace(buf, _build=None):
    """The trace flag in widegl.asm, found by its marker in the annex."""
    at = buf.find(b'GLTRACE\0')
    if at < 0:
        raise ValueError('gltrace needs widescreen3d')
    buf[at + 8:at + 12] = struct.pack('<I', 1)
    return buf


def apply_d3dtrace(buf, _build=None):
    """The trace flag in wide2d.asm, found by its marker in the annex."""
    at = buf.find(b'D3DTRACE\0')
    if at < 0:
        raise ValueError('d3dtrace needs widescreen2d')
    buf[at + 9:at + 13] = struct.pack('<I', 1)
    return buf


def apply_widegl(buf, _build=None):
    """widegl.asm in MGameGL: SetViewport and SetPerspective jump to its
    two entries from their prologues, which hold no absolute. The section
    is writable for the rect copy."""
    out, rva = _self_section(buf, WIDEGL_BLOB)
    _branch(out, WIDEGL_SITES[0], rva, 10, op=b'\xe9')
    _branch(out, WIDEGL_SITES[1], rva + 5, 9, op=b'\xe9')
    return out


def apply_wide2d(buf, _build=None):
    """wide2d.asm in MGameD3D: the quad, triangle, list, indexed-list,
    strip and fan draws jump to its first six entries and the present to
    its eighth, the absolute in each replaced span losing its relocation
    entry; the viewport setter jumps to the seventh from its first nine
    bytes and the texture create to the ninth from the thirteen after
    its system-memory copy, which hold none. The section is writable:
    the scaled copies, the tile tables and the fill table live in it."""
    if _drop_relocations(buf, WIDE2D_RELOCS) != len(WIDE2D_RELOCS):
        raise ValueError('relocation entries for the 2D draws not all found')
    out, rva = _self_section(buf, WIDE2D_BLOB)
    _branch(out, WIDE2D_SITES[0], rva, 6, op=b'\xe9')
    _branch(out, WIDE2D_SITES[1], rva + 5, 6, op=b'\xe9')
    _branch(out, WIDE2D_SITES[2], rva + 10, 10, op=b'\xe9')
    _branch(out, WIDE2D_SITES[3], rva + 15, 10, op=b'\xe9')
    _branch(out, WIDE2D_SITES[4], rva + 20, 10, op=b'\xe9')
    _branch(out, WIDE2D_SITES[5], rva + 25, 10, op=b'\xe9')
    _branch(out, WIDE2D_SITES[6], rva + 30, 9, op=b'\xe9')
    _branch(out, WIDE2D_SITES[7], rva + 35, 8, op=b'\xe9')
    _branch(out, WIDE2D_SITES[8], rva + 40, 13, op=b'\xe9')
    return out


def apply_resolution(buf, build):
    """resolution.asm in Options.dll, with the table and its strings after
    it: the page's row load, draw loop and row store call its entries,
    the count's 800x600 check is jumped over; the absolutes in the
    replaced instructions lose their relocation entries. The RVAs it names come
    from the row and from the page's own code (the choice sprites'
    pointer); the section is writable for the file path it builds."""
    opt = BUILDS[build]['options']
    if buf[RESOLUTION_VALTAB - 2:RESOLUTION_VALTAB] != b'\x8b\x15':
        raise ValueError('the choice sprites load is not where the page puts it')
    if _drop_relocations(buf, RESOLUTION_RELOCS) != len(RESOLUTION_RELOCS):
        raise ValueError('relocation entries for the resolution row not all found')
    if buf[RESOLUTION_PLATES - 1:RESOLUTION_PLATES] != b'\xbf':
        raise ValueError('the row plates load is not where the page puts it')
    values = {'SETTINGS': BUILDS[build]['addresses']['OPTSETTINGS'], 'VALTAB': struct.unpack_from('<I', buf, RESOLUTION_VALTAB)[0],
              'PLATES': struct.unpack_from('<I', buf, RESOLUTION_PLATES)[0], 'DRAW': opt['DRAW'],
              'TEXT': opt['TEXT'], 'GLYPHS': opt['GLYPHS'], 'LOADLIB': opt['LOADLIB'], 'GETPROC': opt['GETPROC'],
              'GETMODFN': opt['GETMODFN']}
    base = struct.unpack_from('<I', buf, struct.unpack_from('<I', buf, 0x3c)[0] + 24 + 28)[0]
    blob = bytes(RESOLUTION_BLOB)
    for name, magic in RESOLUTION_MAGICS.items():
        blob = blob.replace(struct.pack('<I', magic), struct.pack('<I', values[name] - base))
    groups = resolution_groups()
    # the groups, the count, then the table
    blob = blob[:-4 - len(groups)] + groups + struct.pack('<I', len(RESOLUTIONS)) + resolution_table(strings=True)
    out, rva = _self_section(buf, blob)
    _branch(out, RESOLUTION_INIT, rva, 14)
    _branch(out, RESOLUTION_DRAW, rva + 5, 8)
    _branch(out, RESOLUTION_LEAVE, rva + 10, 12)
    _branch(out, RESOLUTION_RESET, rva + 15, 6)
    return out


def _self_section(buf, blob, chars=CODE_SECTION | 0x80000040):
    """Places in the annex a blob that finds the image base from its own
    RVA, written over its MAGIC_SELFRVA. Returns (buffer, RVA)."""
    out, rva = append_section(buf, blob, chars=chars)
    start = _rva_to_off(out, rva)
    out[start:start + len(blob)] = blob.replace(struct.pack('<I', FULLWIN_MAGIC), struct.pack('<I', rva))
    return out, rva


def apply_texrange(buf, _build=None):
    """texrange.asm in MGameD3D: the texture release's first ten bytes
    jump to it; the absolute in them loses its relocation entry."""
    if _drop_relocations(buf, {0x4431}) != 1:
        raise ValueError('relocation entry for the texture table not found')
    out, rva = _self_section(buf, TEXRANGE_BLOB, chars=CODE_SECTION)
    _branch(out, 0x4430, rva, 10, op=b'\xe9')
    return out


def apply_replayfree(buf, _build=None):
    """replayfree.asm in ReplayGallery: the gallery's new at 0x10003b65
    calls the first thunk, its End's free of the replay the second. The
    section is writable: the thunks keep the block's address in it."""
    out, rva = _self_section(buf, REPLAYFREE_BLOB)
    _branch(out, 0x2f65, rva, 5)
    _branch(out, 0x3b1f, rva + 5, 6)
    return out


def apply_fullwin(buf, _build=None):
    """fullwin.asm in MGameD3D: the windowed present jumps to its first
    thunk, the window sizing calls its second. The section is writable:
    the present keeps its answer on the monitor's refresh rate in it."""
    if _drop_relocations(buf, FULLWIN_RELOCS) != len(FULLWIN_RELOCS):
        raise ValueError('relocation entries for the present not all found')
    out, rva = _self_section(buf, FULLWIN_BLOB)
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
        for blob in (ACTIVATE_BLOB, ALTENTER_BLOB, BGROW_BLOB, TEXTCOLOR_BLOB, WIDE_BLOB, WIDE_US_BLOB):
            for magic in EXE_MAGICS.values():
                if struct.pack('<I', magic) in exe_blob(blob, build):
                    raise ValueError('%s: a placeholder left in a stub' % build)
    resolution_groups()
    if b''.join(b'%d\0%d\0' % (w, h) for w, h, _n in RESOLUTION_GROUPS) not in RESOLUTION_BLOB:
        raise ValueError('resolution.asm names the aspect groups differently from RESOLUTION_GROUPS')
    print('tables OK: %d builds, %d patches, %d sites, %d files'
          % (len(BUILDS), len(PATCH_KEYS), sites, len(PATCHED)))
    return 0


# What a key needs: dropping the second drops the first with it.
NEEDS = (('xinput', 'noregistry'), ('devices', 'xinput'), ('music', 'cdlevel'),
         ('widescreen2d', 'widescreen'), ('widescreen3d', 'widescreen'), ('resolution', 'widescreen'),
         ('gltrace', 'widescreen3d'), ('d3dtrace', 'widescreen2d'))
# The game's mode, not options: borderless full screen, framed with ALT+ENTER.
FIXED = ('windowed', 'borderless')


def parse_keys(words):
    """The patches --patch's key words name: every patch, or the ones
    listed, less any given with a leading minus; a diagnostic named is
    added to either, and the windowed mode to any list. Words may be
    separated by commas or spaces (PowerShell hands a,b over as two)."""
    keys = [k for w in words for k in w.split(',') if k]
    unknown = [k for k in keys if k.lstrip('-') not in PATCH_KEYS + DIAGNOSTIC]
    if unknown:
        raise ValueError('no patch named %s; the patches are %s' % (unknown[0].lstrip('-'), ', '.join(PATCH_KEYS)))
    named = [k for k in keys if not k.startswith('-')]
    wanted = [k for k in named if k not in DIAGNOSTIC] or list(PATCH_KEYS)
    wanted += [k for k in named if k in DIAGNOSTIC]
    dropped = set(k[1:] for k in keys if k.startswith('-'))
    if dropped & set(FIXED):
        raise ValueError('%s is the game\'s mode, not an option' % ' and '.join(sorted(dropped & set(FIXED))))
    wanted = [k for k in PATCH_KEYS if k in wanted or k in FIXED] + [k for k in wanted if k in DIAGNOSTIC]
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
