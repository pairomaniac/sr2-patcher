#!/usr/bin/env python3
"""SEGA RALLY 2 (PC, 1999) patcher. See README.md.

    python3 sr2-patcher.py                          the window
    python3 sr2-patcher.py --install SRC DIR [LANG] install from a .cue, .iso, disc folder or data1.cab
    python3 sr2-patcher.py --patch DIR [KEYS]       patch an installed game: every patch, the ones KEYS names, or all but the ones it names with a minus (-music);
                                                    the dgvoodoo add-on with them on Windows, named or -dgvoodoo elsewhere or not
    python3 sr2-patcher.py --rip CUE DIR             rip the play disc's music into DIR/music
    python3 sr2-patcher.py --restore DIR            put the original files back
    python3 sr2-patcher.py --selfcheck              validate the patch tables and exit
    python3 sr2-patcher.py --version

The version is the VERSION line below and nowhere else.

https://github.com/pairomaniac/sr2-patcher
"""
import base64
import errno
import hashlib
import io
import json
import os
import queue
import re
import shutil
import ssl
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile
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
# four. Everything else in the script is written against the European
# row; the others map it.
PATCHED = (EXE, 'MUSASHI\\MGameD3D.dll', 'MUSASHI\\MGameGL.dll', 'MUSASHI\\MGAudio.dll', 'MUSASHI\\MGSound.dll',
           'MUSASHI\\MGInput.dll', 'MUSASHI\\MGNetWk.dll', 'Title.dll', 'Options.dll', 'ReplayGallery.dll')

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
            'MUSASHI\\MGNetWk.dll': (121344, '0a9f86f51aa5b864bb56340cacd2b4a5'),
            'MUSASHI\\MGInput.dll': (90112, '7aa0b3aede10fd247835ad346c2ecee8'),
            'Options.dll': (767488, '25c523277608e7cf2491ee8c67dd7fce'),
            'Title.dll': (637952, 'b1c6ea70b15cc41752c630ae0fb0cf0c'),
            'ReplayGallery.dll': (792576, 'f0db027aa72f43d146859eaef51d74f0'),
        },
        'sites': {'check': 0x267c0, 'loader': 0x7572e, 'activate': 0x25ff7,
                  'devices': (0x33f8, 0x340f, 0x3214, 0x3267, 0x31c0, 0x9aa20, 0x2f0c, 0x3638),   # Options.dll
                  'noregistry': (0xd07c0, 0x7e359), 'xinput': (0x8130, 0x8210, 0x7100, 0x56c0),   # the latter MGInput.dll
                  'dinput8': (0x2940, 0x39ac, 0x10680, 0x106c0),   # MGInput.dll: the create, the type byte's first read, the two interface ids
                  'nogeneric': 0x26d2,                                # MGInput.dll: the device loop's null-GUID branch
                  'flag': 0x273e6, 'cardwarn': 0x26678, 'cdlevel': 0x73048, 'bgrow': 0x14671, 'altenter': 0x260bc,
                  'frametrace': (0x27d0b, 0x27bf0), 'padmenu': 0x3ed4f, 'replaypad': 0x400ea, 'pagepad': 0x7e906, 'loadhold': (0x19bbb, 0x189be), 'hudlast': (0x17eb1, 0x274f2, 0x25d30),
                  'wide': (0x20dfe, 0x20e18, 0x5128a, 0x4e5),
                  'lobby': (0x3b130, 0x3b34f, 0x3b3bd, 0x3f4d6, 0x3e3d8, 0x43ef27, 0x43ee9d),
                  'voltrace': ((0x6e6e0, 6), (0x6fa30, 9), (0x6d560, 5), (0x6e770, 9), (0x6e0e0, 6)),   # the European build only: the diagnostic was never sited elsewhere
                  'volume': 0x1db0, 'getvolume': 0x1e40,   # in MGAudio.dll: the CD-volume methods
                  'mix': (0x439f, 0x6980),  # in MGSound.dll: the buffer's SetRange, the stream's SetVolume
                  'voldefault': 0xd01a8},  # the defaults block's three sliders
        # `ff15` call [slot], `8b35` mov esi, [slot]; the slot is SetTextColor's.
        'textcolor': ((0x203c7, '8b35'), (0x20566, '8b35'), (0x3485f, 'ff15'), (0x34b2a, 'ff15'),
                      (0x34efc, 'ff15'), (0x35533, 'ff15'), (0x360c3, 'ff15'), (0x3a6c0, 'ff15'),
                      (0x3cef4, 'ff15'), (0x3da96, 'ff15')),
        'slots': {'SetTextColor': 0x495028, 'GetLogicalDriveStringsA': 0x495198, 'lstrcpyA': 0x4950f4,
                  'LoadLibraryA': 0x495090, 'GetProcAddress': 0x4950f0,
                  'GetPrivateProfileStringA': 0x4951b8, 'GetModuleFileNameA': 0x495074, 'GetTickCount': 0x495088},
        'options': {'BINDPAGE': 0x1000ed90, 'DRAW': 0x1000e850, 'PLAYSOUND': 0x1000b610, 'INPUT': 0x100b9464,
                    'SOUNDOBJ': 0x100b8bd8, 'HANDLES': 0x100b8bdc, 'TOPTABLE': 0x10003d90,
                    'TEXT': 0x1000df10, 'GLYPHS': 0x1009c080, 'CHARMAP': 0x100fcc04,
                    'LOADLIB': 0x10019010, 'GETPROC': 0x10019048, 'GETMODFN': 0x10019030},
        'addresses': {'MENUTABLES': 0x1009c820, 'REGNAMES': (0x5a2714, 0x4cff94), 'PADLEVEL': 0x4ef7c4, 'PADEDGE': 0x4ef7e4, 'PADPREV': 0x4ef7d4, 'MENUKEYS': 0x4d5e08, 'CARS': 0x4d64bc, 'HUDLO': 0x42ac60, 'HUDHI': 0x42ffc0, 'WALKRESUME': 0x4010eb, 'PADPOLL': 0x5a1ff0, 'RESUME': 0x46e260, 'GAMED3D': 0x50b118, 'LOADPIC': 0x4d6938, 'HANDLER': 0x41fe20, 'HWND': 0x5088ac,
                      'WIDTH': 0x4d5e1c, 'HEIGHT': 0x4d5e20, 'LOCKDESC': 0x4e6878, 'MODE': 0x4d5e54, 'HIRES': 0, 'SETTER': 0x4219f0,
                      'SETTINGS': 0x50afdc, 'OPTSETTINGS': 0x100b9320,
                      'RUNNING': 0x4d6a3c, 'PAUSED': 0x4d6a6c, 'DEBUGDLL': 0x5a2660, 'CATCHUP': 0x4d6930, 'LOBBYSURF': (0x4eaea0, 0x4eade0),
                      'RENDERER': 0x50b110, 'SETVIEWPORT': 0x46bfd0, 'VPRECTS': 0x4b12f0, 'HUDDRAW': 0x429d70, 'TREEDRAW': 0x470ff0, 'HUDRESET': 0x46cec0, 'LATEFLAG': 0x4e68fc, 'FADEDRAW': 0x46bd80},
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
            'MUSASHI\\MGNetWk.dll': (121344, '0a9f86f51aa5b864bb56340cacd2b4a5'),
            'MUSASHI\\MGInput.dll': (90112, '7aa0b3aede10fd247835ad346c2ecee8'),
            'Options.dll': (767488, '25c523277608e7cf2491ee8c67dd7fce'),
            'Title.dll': (637952, 'b1c6ea70b15cc41752c630ae0fb0cf0c'),
            'ReplayGallery.dll': (792576, 'f0db027aa72f43d146859eaef51d74f0'),
        },
        'sites': {'check': 0x26a80, 'loader': 0x75b5e, 'activate': 0x262a7,
                  'devices': (0x33f8, 0x340f, 0x3214, 0x3267, 0x31c0, 0x9aa20, 0x2f0c, 0x3638),   # Options.dll
                  'noregistry': (0xd0bc0, 0x7e779), 'xinput': (0x8130, 0x8210, 0x7100, 0x56c0),
                  'dinput8': (0x2940, 0x39ac, 0x10680, 0x106c0), 'nogeneric': 0x26d2,
                  'flag': 0x276a6, 'cardwarn': 0x26938, 'cdlevel': 0x73478, 'bgrow': 0x14921, 'altenter': 0x2636c,
                  'frametrace': (0x27fcb, 0x27eb0), 'padmenu': 0x3f07f, 'replaypad': 0x4047a, 'pagepad': 0x7ed26, 'loadhold': (0x19e6b, 0x18c6e), 'hudlast': (0x18161, 0x277b2, 0x25fe0),
                  'wide': (0x2108e, 0x210a8, 0x5160a, 0x6e5),
                  'lobby': (0x3b550, 0x3b76f, 0x3b7dd, 0x3f7f6, 0x3e708, 0x43f057, 0x43efcd),
                  'volume': 0x1db0, 'getvolume': 0x1e40, 'mix': (0x439f, 0x6980), 'voldefault': 0xd05a8},
        'textcolor': ((0x20657, '8b35'), (0x207f6, '8b35'), (0x34b8f, 'ff15'), (0x34e5a, 'ff15'),
                      (0x3522c, 'ff15'), (0x35863, 'ff15'), (0x363f3, 'ff15'), (0x3aae0, 'ff15'),
                      (0x3d314, 'ff15'), (0x3ddc6, 'ff15')),
        'slots': {'SetTextColor': 0x495028, 'GetLogicalDriveStringsA': 0x49519c, 'lstrcpyA': 0x4950f4,
                  'LoadLibraryA': 0x495090, 'GetProcAddress': 0x4950f0,
                  'GetPrivateProfileStringA': 0x4951b8, 'GetModuleFileNameA': 0x495074, 'GetTickCount': 0x495088},
        'options': {'BINDPAGE': 0x1000ed90, 'DRAW': 0x1000e850, 'PLAYSOUND': 0x1000b610, 'INPUT': 0x100b9464,
                    'SOUNDOBJ': 0x100b8bd8, 'HANDLES': 0x100b8bdc, 'TOPTABLE': 0x10003d90,
                    'TEXT': 0x1000df10, 'GLYPHS': 0x1009c080, 'CHARMAP': 0x100fcc04,
                    'LOADLIB': 0x10019010, 'GETPROC': 0x10019048, 'GETMODFN': 0x10019030},
        'addresses': {'MENUTABLES': 0x1009c820, 'REGNAMES': (0x5a2714, 0x4d0074), 'PADLEVEL': 0x4ef8b4, 'PADEDGE': 0x4ef8d4, 'PADPREV': 0x4ef8c4, 'MENUKEYS': 0x4d5ef8, 'CARS': 0x4d65ac, 'HUDLO': 0x42ad40, 'HUDHI': 0x4300a0, 'WALKRESUME': 0x4010eb, 'PADPOLL': 0x5a1ff0, 'RESUME': 0x46e480, 'GAMED3D': 0x50b218, 'LOADPIC': 0x4d6a28, 'HANDLER': 0x41feb0, 'HWND': 0x5089ac,
                      'WIDTH': 0x4d5f0c, 'HEIGHT': 0x4d5f10, 'LOCKDESC': 0x4e6968, 'MODE': 0x4d5f44, 'HIRES': 0x4efa1c, 'SETTER': 0x421a80,
                      'SETTINGS': 0x50b0dc, 'OPTSETTINGS': 0x100b9320,
                      'RUNNING': 0x4d6b2c, 'PAUSED': 0x4d6b5c, 'DEBUGDLL': 0x5a2660, 'CATCHUP': 0x4d6a20, 'LOBBYSURF': (0x4eaf90, 0x4eaed0),
                      'RENDERER': 0x50b210, 'SETVIEWPORT': 0x46c1e0, 'VPRECTS': 0x4b12f0, 'HUDDRAW': 0x429e50, 'TREEDRAW': 0x471220, 'HUDRESET': 0x46d0d0, 'LATEFLAG': 0x4e69ec, 'FADEDRAW': 0x46bf90},
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
            'MUSASHI\\MGNetWk.dll': (121344, '0a9f86f51aa5b864bb56340cacd2b4a5'),
            'MUSASHI\\MGInput.dll': (90112, '594a3435f9c2ef6f1ac23cd3ba5dd6b1'),
            'Options.dll': (798720, '0af388650bc11dcd6df2377d3d78a535'),
            'Title.dll': (637952, 'a8017ec64efb1eba81e3e80f8afb875b'),
            'ReplayGallery.dll': (793088, 'be260f94b8791b91cfc3588de5b3473f'),
        },
        'sites': {'check': 0x4b420, 'loader': 0xb4dbe, 'activate': 0x4abfd,
                  'devices': (0x5b68, 0x5b7f, 0x5984, 0x59d7, 0x5930, 0xa0b08, 0x567c, 0x5da8),   # Options.dll
                  'noregistry': (0x115fd4, 0xbd959), 'xinput': (0x7940, 0x7a20, 0x6940, 0x81a8, 0x7e40),   # the latter MGInput.dll
                  'dinput8': (0x2870, 0x39f9, 0x10678, 0x106b8), 'nogeneric': 0x2694,
                  'flag': 0x4c026, 'bgrow': 0x27e71, 'altenter': 0x4acc2, 'oscheck': 0x4b3b0, 'cardwarn': 0x4b263, 'cdlevel': 0xb2668,
                  'clearsize': 0x40b83,
                  'frametrace': (0x4c94e, 0x4c830), 'padmenu': 0x6d63f, 'replaypad': 0x6e99a, 'pagepad': 0xbdef8, 'loadhold': (0x349eb, 0x3107e), 'hudlast': (0x2de01, 0x4c119, 0x4a940),
                  'wide': (0x40b1e, 0x40b38, 0x895c8, 0x4e5),
                  'lobby': (0x673a0, 0x675bf, 0x6762d, 0x6ddb6, 0x6a558, 0x46b0a7, 0x46b01d),
                  'volume': 0x1d90, 'getvolume': 0x1e20, 'mixer': 0x2278,    # all in MGAudio.dll
                  'mix': (0x439f, 0x6980), 'voldefault': 0x1159a8,
                  'sfxlevel': (0xb26cb, 0xb272e, 0xb2782), 'sfxoptions': (0xf92a, 0xf98d, 0xf9e1)},
        'textcolor': ((0x400f7, '8b35'), (0x40296, '8b35'), (0x5e28f, 'ff15'), (0x5e55a, 'ff15'),
                      (0x5e91c, 'ff15'), (0x5ef53, 'ff15'), (0x5fae3, 'ff15'), (0x66930, 'ff15'),
                      (0x69164, 'ff15'), (0x69c16, 'ff15')),
        'slots': {'SetTextColor': 0x4d402c, 'GetLogicalDriveStringsA': 0x4d4198, 'lstrcpyA': 0x4d40fc,
                  'LoadLibraryA': 0x4d4094, 'GetProcAddress': 0x4d40f8,
                  'GetPrivateProfileStringA': 0x4d41a8, 'GetModuleFileNameA': 0x4d4078, 'GetTickCount': 0x4d406c},
        'options': {'BINDPAGE': 0x10013df0, 'DRAW': 0x100138b0, 'PLAYSOUND': 0x10010670, 'INPUT': 0x100c1b1c,
                    'SOUNDOBJ': 0x100be46c, 'HANDLES': 0x100be470, 'TOPTABLE': 0x10006500,
                    'TEXT': 0x10012f70, 'GLYPHS': 0x100a1090, 'CHARMAP': 0x101052bc,
                    'LOADLIB': 0x1001e010, 'GETPROC': 0x1001e048, 'GETMODFN': 0x1001e030},
        'addresses': {'MENUTABLES': 0x100a2708, 'REGNAMES': (0x60c714, 0x5151cc), 'PADLEVEL': 0x55001c, 'PADEDGE': 0x55003c, 'PADPREV': 0x55002c, 'MENUKEYS': 0x52dc08, 'CARS': 0x52f9cc, 'HUDLO': 0x452030, 'HUDHI': 0x457390, 'WALKRESUME': 0x4010eb, 'PADPOLL': 0x60bff0, 'RESUME': 0x4ad790, 'GAMED3D': 0x575ae8, 'LOADPIC': 0x52fe48, 'HANDLER': 0x43fb50, 'HWND': 0x57327c,
                      'WIDTH': 0x52dc1c, 'HEIGHT': 0x52dc20, 'LOCKDESC': 0x53fd88, 'MODE': 0x52dc50, 'HIRES': 0, 'SETTER': 0x441710, 'CLEAR': 0x441180, 'SETTINGS': 0x5759ac, 'OPTSETTINGS': 0x100c19d8,
                      'RUNNING': 0x52ff4c, 'PAUSED': 0x52ff7c, 'DEBUGDLL': 0x60c660, 'CATCHUP': 0x52fe40, 'LOBBYSURF': (0x549fe8, 0x549f28),
                      'RENDERER': 0x575ae0, 'SETVIEWPORT': 0x4ab580, 'VPRECTS': 0x4f3bb0, 'HUDDRAW': 0x451150, 'TREEDRAW': 0x4b0610, 'HUDRESET': 0x4ac420, 'LATEFLAG': 0, 'FADEDRAW': 0x4ab330},
    },
    # DigiCube's DWRPD-00081 (2000) and MediaKite's MKW-166 (2001) reissues:
    # one master, the install disc's data track the one Redump lists for
    # DWRPD-00081. Sega's own 1999 disc is the Australian build.
    #
    # The exe is the European one rebuilt on 29 Nov 1999 (2.0.0.9): the
    # functions at 0x442180 and 0x443de0 were recompiled, net 0x10 shorter,
    # so sites and code addresses past 0x444130 are the European ones less
    # 0x10 and everything else - data, import slots, the other thirteen
    # files - is the European. docs/NOTES.md, *The DigiCube and MediaKite
    # build*.
    'Japanese (DigiCube, MediaKite)': {
        'files': {
            EXE: (1469952, '5c0242443ea289d3d461b15eddb63388'),
            'AdvTelop.dll': (636928, '977dd8801a281e987c4503c9fb2f8778'),
            'Champagn.dll': (699392, 'b8dbfe718eef561f12c99223ba7b9ec4'),
            'MSelect.dll': (1137152, '1e6f713c39efb1558c79b795754d6e3a'),
            'MUSASHI\\MGameGL.dll': (601600, '3d095385ece996088381dd77a0f5f954'),
            'MUSASHI\\MGLBackground.dll': (579584, 'e7cc2a9f084a39c6f119fa1a1d769e30'),
            'MUSASHI\\MGameD3D.dll': (86016, '201a9cc68096231eebcd602a65b7af6e'),
            'MUSASHI\\MGAudio.dll': (57344, 'b05b9c8e84e8a5b051045e48ea9d6bab'),
            'MUSASHI\\MGSound.dll': (86016, 'a9698c1d866a34cd632c8d6e7e8f5fbb'),
            'MUSASHI\\MGNetWk.dll': (121344, '0a9f86f51aa5b864bb56340cacd2b4a5'),
            'MUSASHI\\MGInput.dll': (90112, '7aa0b3aede10fd247835ad346c2ecee8'),
            'Options.dll': (767488, '25c523277608e7cf2491ee8c67dd7fce'),
            'Title.dll': (637952, 'b1c6ea70b15cc41752c630ae0fb0cf0c'),
            'ReplayGallery.dll': (792576, 'f0db027aa72f43d146859eaef51d74f0'),
        },
        'sites': {'check': 0x267c0, 'loader': 0x7571e, 'activate': 0x25ff7,
                  'devices': (0x33f8, 0x340f, 0x3214, 0x3267, 0x31c0, 0x9aa20, 0x2f0c, 0x3638),   # Options.dll
                  'noregistry': (0xd07c0, 0x7e349), 'xinput': (0x8130, 0x8210, 0x7100, 0x56c0),   # the latter MGInput.dll
                  'dinput8': (0x2940, 0x39ac, 0x10680, 0x106c0),   # MGInput.dll: the create, the type byte's first read, the two interface ids
                  'nogeneric': 0x26d2,                                # MGInput.dll: the device loop's null-GUID branch
                  'flag': 0x273e6, 'cardwarn': 0x26678, 'cdlevel': 0x73038, 'bgrow': 0x14671, 'altenter': 0x260bc,
                  'frametrace': (0x27d0b, 0x27bf0), 'padmenu': 0x3ed4f, 'replaypad': 0x400ea, 'pagepad': 0x7e8f6, 'loadhold': (0x19bbb, 0x189be), 'hudlast': (0x17eb1, 0x274f2, 0x25d30),
                  'wide': (0x20dfe, 0x20e18, 0x5127a, 0x4e5),
                  'lobby': (0x3b130, 0x3b34f, 0x3b3bd, 0x3f4d6, 0x3e3d8, 0x43ef27, 0x43ee9d),
                  'voltrace': ((0x6e6d0, 6), (0x6fa20, 9), (0x6d550, 5), (0x6e760, 9), (0x6e0d0, 6)),
                  'volume': 0x1db0, 'getvolume': 0x1e40,   # in MGAudio.dll: the CD-volume methods
                  'mix': (0x439f, 0x6980),  # in MGSound.dll: the buffer's SetRange, the stream's SetVolume
                  'voldefault': 0xd01a8},  # the defaults block's three sliders, in STATUSDA where the relink left it
        'textcolor': ((0x203c7, '8b35'), (0x20566, '8b35'), (0x3485f, 'ff15'), (0x34b2a, 'ff15'),
                      (0x34efc, 'ff15'), (0x35533, 'ff15'), (0x360c3, 'ff15'), (0x3a6c0, 'ff15'),
                      (0x3cef4, 'ff15'), (0x3da96, 'ff15')),
        'slots': {'SetTextColor': 0x495028, 'GetLogicalDriveStringsA': 0x495198, 'lstrcpyA': 0x4950f4,
                  'LoadLibraryA': 0x495090, 'GetProcAddress': 0x4950f0,
                  'GetPrivateProfileStringA': 0x4951b8, 'GetModuleFileNameA': 0x495074, 'GetTickCount': 0x495088},
        'options': {'BINDPAGE': 0x1000ed90, 'DRAW': 0x1000e850, 'PLAYSOUND': 0x1000b610, 'INPUT': 0x100b9464,
                    'SOUNDOBJ': 0x100b8bd8, 'HANDLES': 0x100b8bdc, 'TOPTABLE': 0x10003d90,
                    'TEXT': 0x1000df10, 'GLYPHS': 0x1009c080, 'CHARMAP': 0x100fcc04,
                    'LOADLIB': 0x10019010, 'GETPROC': 0x10019048, 'GETMODFN': 0x10019030},
        'addresses': {'MENUTABLES': 0x1009c820, 'REGNAMES': (0x5a2714, 0x4cff94), 'PADLEVEL': 0x4ef7c4, 'PADEDGE': 0x4ef7e4, 'PADPREV': 0x4ef7d4, 'MENUKEYS': 0x4d5e08, 'CARS': 0x4d64bc, 'HUDLO': 0x42ac60, 'HUDHI': 0x42ffc0, 'WALKRESUME': 0x4010eb, 'PADPOLL': 0x5a1ff0, 'RESUME': 0x46e250, 'GAMED3D': 0x50b118, 'LOADPIC': 0x4d6938, 'HANDLER': 0x41fe20, 'HWND': 0x5088ac,
                      'WIDTH': 0x4d5e1c, 'HEIGHT': 0x4d5e20, 'LOCKDESC': 0x4e6878, 'MODE': 0x4d5e54, 'HIRES': 0, 'SETTER': 0x4219f0,
                      'SETTINGS': 0x50afdc, 'OPTSETTINGS': 0x100b9320,
                      'RUNNING': 0x4d6a3c, 'PAUSED': 0x4d6a6c, 'DEBUGDLL': 0x5a2660, 'CATCHUP': 0x4d6930, 'LOBBYSURF': (0x4eaea0, 0x4eade0),
                      'RENDERER': 0x50b110, 'SETVIEWPORT': 0x46bfc0, 'VPRECTS': 0x4b12f0, 'HUDDRAW': 0x429d70, 'TREEDRAW': 0x470fe0, 'HUDRESET': 0x46ceb0, 'LATEFLAG': 0x4e68fc, 'FADEDRAW': 0x46bd70},
    },
}


# What the window and the log call a row, where that is not its key. Sega's
# own Japanese disc carries the Australian contents, so the two cannot be
# told apart.
BUILD_NAMES = {'Australian': 'Australian / Japanese (Sega)'}


def build_name(build):
    return BUILD_NAMES.get(build, build)


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
#   surfmem     MGameD3D's video-memory offscreen surfaces made in system memory
#   textcolor   the lobby's SetTextColor(-1) masked to RGB
#   windowed    the fullscreen flag cleared; the .bg row copy expands to 32 bits (always on)
#   anydepth    the windowed path's 16-bit desktop check skipped
#   anymode     the mode check before the window, EnumDisplayModes for 640x480x16, passes
#   altenter    ALT+ENTER toggles a framed window
#   hudlast     the race's HUD drawn after the water, so the gauge's plate blends over the lake
#   loadhold    the stage loading screens held three seconds
#   padmenu     the pad on the multiplayer screens straight from MGInput's annex, the directions the keyboard's way; Back is TAB, which opens the team room's MENU row
#   pagepad     LB and RB as Page Up and Page Down: the Records pages, the car select's alternative colour
#   sortpad     the pad's LB and RB step the Replay Gallery's sort (MODE, CAR, DATE), which F6-F8 set as accelerators
#   replaypad   the pad on the replay's camera controls, from MGInput's annex: RB/LB the camera, left stick turns, RT/LT zoom, Y the meter, X the 2P screen or watched car
#   titlebg     Title.dll's own .bg row copy, the same stub
#   texrange    the texture release checks its index; VendorLogo releases -128
#   replayfree  the replay gallery frees only the replay it loaded, not a race's in MainMode's data
#   borderless  the window covers its monitor, the present letterboxes (always on)
#   mix         MGSound: every buffer's dB range remapped to -43..-8, the streams on the same curve
#   voldefault  the three volume sliders' defaults 6 rather than 9, for a first start and DEFAULT
#   cdlevel     the menu's CD-level set flagged, so the music hook tells it from a fade; music needs it
#   music       CD audio from music\trackNN.wav; the BGM slider sets its volume
#   devices     a fourth Options item, Device Settings, placed for the controller page; also grows OPTIONS.TXR
#   widescreen  the picture at the size SR2.CFG names, the 3D field widened (exe)
#   widescreen2d  the 2D scaled into the picture's 4:3 box, the race HUD to a 16:9 frame (MGameD3D)
#   widescreen3d  the viewports and centres scaled, the angle widened (MGameGL)
#   resolution  a Resolution row on the Graphic Settings page (Options.dll)
#   noregistry  the controls in SR2.CFG as text; the registry never opened
#   xinput      XInput pads through MGInput's own action records
#   dinput8     MGInput's DirectInput object made through dinput8.dll, not the legacy dinput.dll
#   nogeneric   HID devices of no kind (LED controllers, spare collections) left out of MGInput's device list; needs dinput8
#   lobby       the connection screen's rows INTERNET, DIRECT IP and LAN, and the art for them
#   netplay     MGNetWk.dll replaced by the UDP build of net/, the directory for INTERNET
#   clearsize   the mode setter's clear given the height as well (Australian)
#   win9x       the Windows 9x check returns "fine" (Australian)
#   sfxlevel    the effects at 100% of their ceiling, as the other builds (Australian exe)
#   sfxoptions  the same in the Australian Options.dll, which re-applies on the way out
#   mixerless   MGAudio Init without a mixer CD line (Australian)
#
# Diagnostics, by name only (--patch DIR KEYS): voltrace reports the volume
# calls on +debugstr, frametrace logs every drawn frame to logs\\frames.log,
# gltrace MGameGL's viewports and angles, d3dtrace and d3dtrace2d
# MGameD3D's draws (all, or the 2D lists, strips and fans), d3dinit
# every step of MGameD3D's bring-up with its HRESULT to logs\\d3dinit.log.

# The first bytes of the five volume entry points voltrace hooks.
VOLTRACE_HEADS = (bytes.fromhex('558bec83ec0c'), bytes.fromhex('558bec81ec80000000'), bytes.fromhex('568b3185f6'),
                  bytes.fromhex('558bec81ec88000000'), bytes.fromhex('558bec83ec0c'))


# The DirectInput interface ids MGInput.dll's two QueryInterface calls
# name, and DirectInput 8's in their place; the DirectInputCreateA thunk
# the create site calls, per build (its RVA, for the site's call operand).
IID_IDIRECTINPUT2A = bytes.fromhex('62e64459 8aaa cf11 bfc7 444553540000'.replace(' ', ''))
IID_IDIRECTINPUT8A = bytes.fromhex('308079bf 3a48 a24d aa99 5d64ed369700'.replace(' ', ''))
IID_IDIRECTINPUTDEVICE2A = bytes.fromhex('82e64459 2ec9 cf11 bfc7 444553540000'.replace(' ', ''))
IID_IDIRECTINPUTDEVICE8A = bytes.fromhex('8010d454 15dc 3348 a41b 748f73a38179'.replace(' ', ''))
DI_THUNK = {'European': 0x8a30, 'American': 0x8a30, 'Australian': 0x8550, 'Japanese (DigiCube, MediaKite)': 0x8a30}


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


WIDEGL_SITES = (0x2bc0, 0x2c70, 0x2de0, 0x2e80, 0x27f0, 0x2ee0)     # MGameGL, file offsets: SetViewport 0x100037c0,
        # SetPerspective 0x10003870, SetCentre 0x100039e0, Project 0x10003a80, GetParameter 0x100033f0, Unproject 0x10003ae0
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
# the stock two; the page's ASPECT RATIO row picks a group. Two lists:
# the full one, and one with nothing over 2048 a side for Windows' own
# Direct3D, which refuses a larger picture as a drawing target
# (docs/NOTES.md, The size of the target) - there the 21:9 and 32:9
# sizes are the halves of 2560x1080, 3440x1440 and 3840x1080. patch()
# picks by the system and the dgvoodoo add-on; the full list otherwise.
RESOLUTION_TABLES = {
    'full': (((640, 480), (800, 600), (1024, 768), (1280, 960), (1600, 1200),
              (1280, 800), (1440, 900), (1680, 1050), (1920, 1200), (2560, 1600), (2880, 1800), (3840, 2400),
              (1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1440), (3200, 1800), (3840, 2160),
              (5120, 2880),
              (2560, 1080), (3440, 1440), (3840, 1600), (5120, 2160),
              (3840, 1080), (5120, 1440), (7680, 2160)),
             ((4, 3, 5), (16, 10, 7), (16, 9, 8), (21, 9, 4), (32, 9, 3))),
    'capped': (((640, 480), (800, 600), (1024, 768), (1280, 960), (1600, 1200),
                (1280, 800), (1440, 900), (1680, 1050), (1920, 1200),
                (1280, 720), (1366, 768), (1600, 900), (1920, 1080),
                (1280, 540), (1720, 720),
                (1920, 540)),
               ((4, 3, 5), (16, 10, 4), (16, 9, 4), (21, 9, 2), (32, 9, 1))),
}
RESOLUTIONS, RESOLUTION_GROUPS = RESOLUTION_TABLES['full']   # (aspect, sizes), in the list's order; resolution.asm names the groups


def select_resolutions(which):
    """The table apply_wide and apply_resolution build in."""
    global RESOLUTIONS, RESOLUTION_GROUPS
    RESOLUTIONS, RESOLUTION_GROUPS = RESOLUTION_TABLES[which]


def resolution_groups(table=None):
    """(first entry, entries) per aspect group; the sizes checked against
    the aspect loosely (the 21:9 sizes are 64:27, 43:18 and 12:5)."""
    sizes, groups = table or (RESOLUTIONS, RESOLUTION_GROUPS)
    out, start = [], 0
    for w, h, n in groups:
        for rw, rh in sizes[start:start + n]:
            if abs(rw / rh - w / h) > 0.07:
                raise ValueError('%dx%d is not %d:%d' % (rw, rh, w, h))
        out.append((start, n))
        start += n
    if start != len(sizes):
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
TEXRANGE_SITE = 0x4430                  # MGameD3D, the texture release's first ten bytes
SURFMEM_SITE = 0x7cb2                   # MGameD3D, the offscreen surface create's video-memory caps
# MGameD3D, every `mov [0x10011fc4], eax` (the last-HRESULT slot) in the
# bring-up tree, by function: Init 0x10002090 and its 0x10001fd0, the
# step list 0x10002160, the fullscreen extras 0x100022e0, the DirectDraw
# object 0x10002d80/0x10002df0/0x100024b0/0x10002eb0, the cooperative
# level and window 0x100025d0, the surfaces 0x10003320/0x10003500/
# 0x10003520, the device 0x10003840, the textures 0x100071e0, 0x10005fe0.
D3DINIT_SITES = (0x1a34, 0x1a8c, 0x1ac1, 0x1ada, 0x1af6, 0x1b12, 0x1b2e, 0x1b4f, 0x1b6c, 0x1b9a, 0x1be3, 0x3b6d, 0x3bc7,
                 0x20a3, 0x20c5, 0x20d5, 0x20e5, 0x20ef, 0x1ff5, 0x200b,
                 0x2175, 0x21be, 0x21e6, 0x2200, 0x2210, 0x2220, 0x2234, 0x2244, 0x225c,
                 0x2303, 0x2313, 0x2323, 0x2333, 0x2343, 0x2351,
                 0x2da7, 0x2dc3, 0x2dcc, 0x2e2e, 0x2e42, 0x2e4f, 0x24f8, 0x250a, 0x2ee4, 0x2efc,
                 0x25f9, 0x262d, 0x26de, 0x270d, 0x2725,
                 0x332d, 0x34ea, 0x3517, 0x3593, 0x35c9, 0x35fb, 0x3626, 0x366e, 0x36c7, 0x3701, 0x3718, 0x373b, 0x3757, 0x3772, 0x377b,
                 0x388c, 0x38a3, 0x38e3, 0x38fe, 0x3919, 0x393e,
                 0x7222, 0x7253, 0x6038, 0x6114, 0x612f)
D3DINIT_STORE = bytes.fromhex('a3c41f0110')   # `mov [0x10011fc4], eax`
REPLAYFREE_SITES = (0x2f65, 0x3b1f)     # ReplayGallery, the gallery's new and its End's free
SORTPAD_SITE = 0x1b64                   # ReplayGallery, after the list's row update in its browse state; every build
# HIGHLOW entries inside the replaced present (absolute addresses, now dead
# code) and the one under the MoveWindow call.
FULLWIN_RELOCS = {0x4d7d, 0x4d8a, 0x4d8f, 0x4d95, 0x4da3, 0x4db1, 0x4db6, 0x4dc4, 0x4dd3, 0x26c0}



def wide_sites(offsets, addresses, american):
    """The exe's widescreen sites: the mode setter's `mov eax, [esp+8];
    cmp [MODE], eax` and its literal size stores (the American build's
    have a third size behind a flag), and the screen-change routine's
    `mov eax, [SETTINGS]; mov ecx, [eax+0x50]`, and the element walker's
    `push eax; call ecx; add esp, 4`."""
    modecheck, setsize, screen, walk = offsets
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
            (screen, b'\xa1' + struct.pack('<I', addresses['SETTINGS']) + bytes.fromhex('8b4850'), None),
            (walk, bytes.fromhex('50ffd183c404'), None))


LOBBY_ROWS = (82, 134, 186)             # the three rows' y, at the stock pitch, centred in the panel (stock 54, 106, 158, 210)


def lobby_sites(anchors, surfaces):
    """The connection screen as three rows - INTERNET, DIRECT IP, LAN - in
    place of IPX, TCP/IP, MODEM, SERIAL: the drawer (0x43bd30) blits the
    rows at LOBBY_ROWS and not the fourth, the cursor wraps in 0..2, the
    confirm never picks the modem screen, the latency after the connection
    is the DLL's for every type, and SHOW TEAMS on row 2 searches at once
    as row 0 does. The anchors are the drawer, the cursor wrap, the confirm,
    the latency test and the SHOW TEAMS jump table, as file offsets, then
    the table's stock and wanted entries; surfaces the two tables the
    drawer indexes. Row 1's y does not fit the stock `push imm8`, so that
    blit is re-encoded in place: its `add esi,4` dropped for a `push imm32`,
    the next blit reading `[esi+8]`."""
    drawer, wrap, confirm, latency, table, stock, wanted = anchors
    handles, surface = surfaces
    blit = (bytes.fromhex('8b4604') + bytes.fromhex('8b14c5') + struct.pack('<I', handles + 4)
            + bytes.fromhex('8b0cc5') + struct.pack('<I', handles) + bytes.fromhex('8b0485') + struct.pack('<I', surface))
    tail = bytes.fromhex('895424108d542404526a6a6a00894c24188b0850ff511c')
    old = blit + bytes.fromhex('83c604') + tail
    new = blit + tail[:9] + b'\x68' + struct.pack('<I', LOBBY_ROWS[1]) + tail[11:]
    return (
        (drawer + 0x28, bytes.fromhex('6a36'), bytes([0x6a, LOBBY_ROWS[0]])),
        (drawer + 0x46, old, new),
        (drawer + 0x78, bytes.fromhex('8b4604'), bytes.fromhex('8b4608')),
        (drawer + 0x9c, bytes.fromhex('689e000000'), b'\x68' + struct.pack('<I', LOBBY_ROWS[2])),
        (drawer + 0xad, bytes.fromhex('83c604'), bytes.fromhex('eb3290')),
        (wrap + 0x8, b'\x03', b'\x02'),
        (wrap + 0x28, b'\x03', b'\x02'),
        (wrap + 0x36, b'\x03', b'\x02'),
        (confirm + 0x12, bytes.fromhex('740a'), bytes.fromhex('9090')),
        (latency + 0x7, bytes.fromhex('7513'), bytes.fromhex('eb13')),
        (table + 8, struct.pack('<I', stock), struct.pack('<I', wanted)),
    )


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
        'surfmem': ('MUSASHI\\MGameD3D.dll', ((SURFMEM_SITE, bytes.fromhex('40400000'),
                                                bytes.fromhex('40080000')),), None),
        'textcolor': (EXE, tuple(
            (off, bytes.fromhex(op) + slot('SetTextColor'), None)
            for off, op in row['textcolor']), 'apply_textcolor'),
        'windowed': (EXE, (
            (site['flag'], b'\x01', b'\x00'),
            (site['bgrow'], bytes.fromhex('8bc88be9c1e9028bf38bfaf3a58bcd83e103f3a4'), None)), 'apply_windowed'),
        'anydepth': ('MUSASHI\\MGameD3D.dll', ((0x271e, b'\x74', b'\xeb'),), None),
        'anymode': ('MUSASHI\\MGameD3D.dll', ((0x2ef8, bytes.fromhex('05400080'), bytes(4)),), None),
        'altenter': (EXE, ((site['altenter'], b'\xe8', None),), 'apply_altenter'),
        'hudlast': (EXE, (
            (site['hudlast'][0], b'\xe8', None),
            (site['hudlast'][1], b'\xe8', None),
            (site['hudlast'][2], b'\x8b\x0d' + struct.pack('<I', row['addresses']['RENDERER']) + b'\xe9', None)), 'apply_hudlast'),
        'loadhold': (EXE, (
            (site['loadhold'][0], b'\x89\x0d' + struct.pack('<I', row['addresses']['LOADPIC']), None),
            (site['loadhold'][1], b'\x8b\x0d' + struct.pack('<I', row['addresses']['LOADPIC']), None)), 'apply_loadhold'),
        'padmenu': (EXE, ((site['padmenu'], b'\x89\x0d' + struct.pack('<I', row['addresses']['PADLEVEL']), None),), 'apply_padmenu'),
        'replaypad': (EXE, ((site['replaypad'], bytes.fromhex('8b56088b06'), None),), 'apply_replaypad'),
        'pagepad': (EXE, ((site['pagepad'], bytes.fromhex('8b4424103bc5' if build == 'Australian' else '8b44241085c0'), None),),
                    'apply_pagepad'),
        'titlebg': ('Title.dll', ((TITLEROW_SITE, bytes.fromhex('8bc88bf38be98bfac1e902f3a58bcd03d883e103f3a4'), None),),
                    'apply_titlebg'),
        'texrange': ('MUSASHI\\MGameD3D.dll', ((TEXRANGE_SITE, bytes.fromhex('a180250110568b742408'), None),), 'apply_texrange'),
        'd3dinit': ('MUSASHI\\MGameD3D.dll', tuple((off, D3DINIT_STORE, None) for off in D3DINIT_SITES), 'apply_d3dinit'),
        'replayfree': ('ReplayGallery.dll', ((REPLAYFREE_SITES[0], bytes.fromhex('e881820000'), None),
                                             (REPLAYFREE_SITES[1], bytes.fromhex('50e8bb760000'), None)), 'apply_replayfree'),
        'sortpad': ('ReplayGallery.dll', ((SORTPAD_SITE, bytes.fromhex('8b4e5081e7ff000000'), None),), 'apply_sortpad'),
        'borderless': ('MUSASHI\\MGameD3D.dll', (
            (PRESENT_SITE, bytes.fromhex('8b0df8230110'), None),
            (SIZE_SITE, bytes.fromhex('ff152cf10010'), None)), 'apply_fullwin'),
        'mix': ('MUSASHI\\MGSound.dll', ((site['mix'][0], bytes.fromhex('8b4c240c8b542410'), None),
                                        (site['mix'][1], bytes.fromhex('03d68bf285f6'), None)), 'apply_mix'),
        'cdlevel': (EXE, ((site['cdlevel'], bytes.fromhex('6a00d80d'), bytes.fromhex('6a40d80d')),), None),
        'voldefault': (EXE, ((site['voldefault'], struct.pack('<3I', 9, 9, 9), struct.pack('<3I', 6, 6, 6)),), None),
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
        'd3dtrace2d': ('MUSASHI\\MGameD3D.dll', (), 'apply_d3dtrace2d'),
        'widescreen3d': ('MUSASHI\\MGameGL.dll', (
            (WIDEGL_SITES[0], bytes.fromhex('558bec83ec2889742404'), None),
            (WIDEGL_SITES[1], bytes.fromhex('558bec83ec18891c24'), None),
            (WIDEGL_SITES[2], bytes.fromhex('558bec83ec28891c24'), None),
            (WIDEGL_SITES[3], bytes.fromhex('8b44240c8b4c2408'), None),
            (WIDEGL_SITES[4], bytes.fromhex('558bec81eca8000000'), None),
            (WIDEGL_SITES[5], bytes.fromhex('8b44240c8b4c2408'), None)), 'apply_widegl'),
        'resolution': ('Options.dll', resolution_sites(row['addresses']['OPTSETTINGS']), 'apply_resolution'),
        'lobby': (EXE, lobby_sites(site['lobby'], row['addresses']['LOBBYSURF']), None),
        'netplay': ('MUSASHI\\MGNetWk.dll', (), 'apply_netplay'),
    }
    if 'clearsize' in site:
        table['clearsize'] = (EXE, ((site['clearsize'], bytes.fromhex('a11cdc52005050e8f1f9ffff'), None),), 'apply_clearsize')
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
    # key is never opened.
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
    # Every MGInput.dll but the Australian hooks the device's poll; the
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
    # The kind site is the type byte's first read: a seven-byte cmp in every
    # MGInput.dll but the Australian, where it is a six-byte load.
    create, kind, iid_di, iid_dev = site['dinput8']
    table['dinput8'] = ('MUSASHI\\MGInput.dll', (
        (create, bytes.fromhex('8d4424106a00506800050000') + b'\x53\xe8' + struct.pack('<i', DI_THUNK[build] - (create + 18)), None),
        (kind, bytes.fromhex('80be6002000003') if kind == 0x39ac else bytes.fromhex('8b9660020000'), None),
        (iid_di, IID_IDIRECTINPUT2A, IID_IDIRECTINPUT8A),
        (iid_dev, IID_IDIRECTINPUTDEVICE2A, IID_IDIRECTINPUTDEVICE8A)), 'apply_dinput8')
    table['nogeneric'] = ('MUSASHI\\MGInput.dll', ((site['nogeneric'], bytes.fromhex('741c8b0e52'), None),), 'apply_nogeneric')
    return table


# Diagnostics: applied only by name (--patch DIR KEYS), never by default.
DIAGNOSTIC = ('voltrace', 'frametrace', 'gltrace', 'd3dtrace', 'd3dtrace2d', 'd3dinit')
BYNAME = DIAGNOSTIC

# Every patch any build has, in table order.
PATCH_KEYS = tuple(k for k in dict.fromkeys(k for b in BUILDS for k in patches(b)) if k not in BYNAME)


# What the window shows, and what the README lists. One row is one thing
# somebody would say the patcher does; the patch keys behind it are the
# edits it takes, which is a table matter and not theirs. A row is
# (group, label, description, keys); the description is prose, then
# `heading<TAB>meaning` rows for the bubble's table. selfcheck() checks
# that every key is in exactly one row.
FEATURES = (
    ('nodisc', 'No disc required',
     'The game\'s data read from the folder it is installed in, in place\n'
     'of the play disc it used to scan your drives for. Every mode is open\n'
     'with nothing in the drive.', ('nodisc',)),

    ('start', 'Skip the start-up checks',
     'The four checks the game makes before it opens its window, and what\n'
     'each one now allows.\n'
     '\n'
     'Video card\tAny card. The check weighed yours against a 1999 list\n'
     '\tand 4 MB of video memory, and put up an OK/Cancel box\n'
     '\teither way.\n'
     'Display mode\tAny mode list. It wanted 640x480 at 16 bits offered,\n'
     '\tand stopped at "Failed to initialize. Error code\n'
     '\t80004005" without it.\n'
     'Desktop depth\tAny depth. The windowed path wanted a 16-bit desktop.\n'
     'Windows version\tAny version. The Australian release wanted 98 or\n'
     '\tolder.', ('nocardwarn', 'anymode', 'anydepth', 'win9x')),

    ('crashes', 'Crash fixes',
     'Three reads and frees past the end of something, each of which\n'
     'Windows ends the process for.\n'
     '\n'
     'Starting up\tThe back buffer detached from its Z-buffer, which\n'
     '\tclosed the game before its window appeared under Proton.\n'
     'After the logos\tA texture released from outside the table\'s range,\n'
     '\ton the logo screen.\n'
     'The gallery\tA buffer freed that was not the replay gallery\'s own,\n'
     '\twhich the heap has ended the process for since Windows 8.',
     ('zdetach', 'texrange', 'replayfree')),

    ('altab', 'Fix the picture after ALT+TAB',
     'The game\'s surfaces, rebuilt as the window comes back to the front.\n'
     'A stock game carried on drawing to the ones the driver threw away\n'
     'while it was in the background, and came back to a blank screen.',
     ('altab', 'restoreall')),

    ('devicescan', 'Fix the device scan',
     'The device list, asked for through dinput8 - the one Windows still\n'
     'ships - and filtered to keyboards, mice and controllers. A stock\n'
     'game went through the legacy dinput and read every HID device on the\n'
     'machine, which is where the white window on start came from: lit\n'
     'keyboards, composite pads, some wheels.',
     ('dinput8', 'nogeneric')),

    ('window', 'Windowed and borderless',
     'The game in a window, in place of taking over the display at\n'
     '640x480.\n'
     '\n'
     'Borderless\tHow it starts: the monitor it opens on, no frame, no\n'
     '\tmode change.\n'
     'ALT+ENTER\tA framed window to move, resize or maximise, and back.\n'
     'ALT+TAB\tEither mode, and the window comes back where it was.\n'
     'The picture\tFitted to the window: 4:3 with black bars until a\n'
     '\twidescreen size is picked.',
     ('windowed', 'borderless', 'altenter', 'titlebg', 'clearsize')),

    ('lettering', 'Text and panel fixes',
     'Text the game drew and the card did not show, and the panels behind\n'
     'it.\n'
     '\n'
     'Menu screens\tThe black lettering of SELECT GAME, SELECT CAR and\n'
     '\tthe rest, which came out as hollow outlines.\n'
     'Multiplayer\tThe name you type, the team list and the chat, which\n'
     '\tdid not appear at all.\n'
     'Team room\tThe panels themselves - the team list, the chat line,\n'
     '\tthe timer and the course box - black with dgVoodoo 2.',
     ('texfmt', 'textcolor', 'surfmem')),

    ('hud', 'Fix the HUD over the scenery',
     'The HUD drawn after the scene rather than in the middle of it. The\n'
     'tachometer\'s plate blanked the lake behind it on Mountain, and the\n'
     'ten-year championship\'s credits ran behind the replay\'s frame.',
     ('hudlast',)),

    ('sound', 'Sound fixes',
     'One curve behind all three volume sliders - music, effects and\n'
     'engine - with the two musics matched to it, so equal settings are\n'
     'equally loud. Each slider had a curve of its own, and the Australian\n'
     'release ran its effects at a fraction of the others\' and wanted a\n'
     'mixer device before it would start at all. A first start and\n'
     'DEFAULT put the sliders at 6, not at the top.',
     ('mix', 'sfxlevel', 'sfxoptions', 'mixerless', 'voldefault')),

    ('settings', 'No registry',
     'The game\'s settings as plain files beside the exe: SR2.DSP for the\n'
     'display, SR2.CFG for the controls. Nothing in the registry and\n'
     'nothing an installer has to write, so the folder can be copied as it\n'
     'is.', ('noregistry',)),

    ('widescreen', 'Native widescreen',
     'The game renders at the size you pick, 640x480 to 3840x2160, in\n'
     'place of 640x480 stretched to the window.\n'
     '\n'
     'Aspect Ratio\tA row under Options - Graphic Settings: 4:3, 16:10,\n'
     '\t16:9, 21:9 and 32:9.\n'
     'Resolution\tThe sizes of that aspect, listed for it.\n'
     'The race\tMore of the stage at the sides, rather than a stretched\n'
     '\tmiddle.\n'
     'Menus and HUD\tTheir own shape in the middle of the screen, with the\n'
     '\tbackgrounds carried out to the edges.',
     ('widescreen', 'widescreen2d', 'widescreen3d', 'resolution')),

    ('music', 'Music from files',
     'The soundtrack as files - music\\track02.wav onward beside the game -\n'
     'in place of the audio tracks on the play disc. Rip soundtrack above\n'
     'writes them, about 550 MB, and the in-game slider drives them.',
     ('music', 'cdlevel')),

    ('gamepad', 'XInput gamepad support',
     'A modern pad wherever the game takes input, with every control\n'
     'rebindable from inside it.\n'
     '\n'
     'Driving\tStick to steer, triggers for the pedals, Start to pause.\n'
     'Menus\tD-pad or stick to move, A and Start to choose, B to go\n'
     '\tback.\n'
     'Device Settings\tA page of its own under Options: both players\'\n'
     '\tcontrols, keyboard and pad side by side. Press a key or\n'
     '\ta button to rebind it.\n'
     'Multiplayer\tThe team room takes the pad as well, with Back where\n'
     '\tTAB was.\n'
     'Replays\tRB and LB change the camera, the left stick turns it,\n'
     '\tRT and LT zoom, Y the meter, X the switch.\n'
     'LB and RB\tThe Records pages and the Replay Gallery\'s sort; LB\n'
     '\theld through choosing a car picks its other colour.', ('xinput', 'devices', 'padmenu', 'replaypad', 'pagepad', 'sortpad')),

    ('internet', 'Internet play',
     'Play over the internet, in place of the DirectPlay the game shipped\n'
     'with and with nobody forwarding a port. The team room, the chat, the\n'
     'car and course selection and the race are the game\'s own; up to four\n'
     'players, all on the same patcher version.\n'
     '\n'
     'INTERNET\tSHOW TEAMS, the teams open anywhere.\n'
     'DIRECT IP\tThe host\'s address, or host:port. The host forwards UDP\n'
     '\t47626.\n'
     'LAN\tThe local network, searched.\n'
     'In place of\tIPX, TCP/IP, modem and serial.', ('netplay', 'lobby')),

    ('loading', 'Loading screens',
     'The stage\'s card - its artwork and its name - held for three\n'
     'seconds. The course loads in well under one on a machine of today,\n'
     'so the card was gone before you had read it.', ('loadhold',)),
)


# Display order. Essential fixes what is broken on a modern system and
# has no trade-off, so it is applied without tick boxes; extra is taste,
# and starts ticked.
ESSENTIAL = ('nodisc', 'start', 'crashes', 'altab', 'devicescan', 'window',
             'lettering', 'hud', 'sound', 'settings')
EXTRA = ('widescreen', 'music', 'gamepad', 'internet', 'loading')

BY_GROUP = {group: (label, tip, keys) for group, label, tip, keys in FEATURES}

# The diagnostics, which are patches applied only by name or by their box
# in the window. Each writes a log beside the game for a bug report; see
# docs/DEVELOPING.md.
DIAGNOSTIC_INFO = {
    'voltrace': ('Volume calls', 'Reports every call into the five volume '
                 'routines on +debugstr, for a slider that is not doing what '
                 'it says. The European release only.'),
    'frametrace': ('Frame pacing', 'Logs every drawn frame to '
                   'logs\\frames.log: when it started, how long it took and '
                   'what it waited for. For stutter and for a frame rate that '
                   'is not 60.'),
    'gltrace': ('MGameGL draws', 'Reports the 3D renderer\'s viewports, '
                'angles and projections on +debugstr. For a picture that is '
                'the wrong shape at a widescreen size.'),
    'd3dtrace': ('MGameD3D draws', 'Reports every draw MGameD3D makes on '
                 '+debugstr. The loudest of them; for something drawn in the '
                 'wrong place.'),
    'd3dtrace2d': ('MGameD3D 2D draws', 'The same for the 2D lists, strips '
                   'and fans only - the menus, the HUD and the text.'),
    'd3dinit': ('Direct3D bring-up', 'Logs every step of MGameD3D\'s '
                'start-up with its HRESULT to logs\\d3dinit.log. This is '
                'the one to send for "Failed to initialize. Error code '
                '80004005".'),
}


def group_keys(groups, extra=()):
    """The patch keys for a set of feature groups, plus anything named in
    extra - a diagnostic, the dgvoodoo add-on. Essential groups are in
    whether they were asked for or not, and a key whose NEEDS is missing
    goes out with it."""
    wanted = set(ESSENTIAL) | set(groups)
    keys = [k for k in PATCH_KEYS
            if any(k in BY_GROUP[g][2] for g in wanted if g in BY_GROUP)]
    keys += [k for k in extra if k not in keys]
    for _ in range(len(NEEDS)):             # a dropped need may drop another
        keys = [k for k in keys if all(need in keys
                                       for key, need in NEEDS if key == k)]
    return tuple(keys)

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
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true</dpiAware>
    </windowsSettings>
  </application>
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
    'bef1f1f1f189c1d1e98b6c241c8b6d048b6d08394e0c0f8551060000396e080f'
    '8548060000837e5420741589c189cdc1e90289de89d7f3a589e983e103f3a4c3'
    '50535289c1d1e9741389de89d70fb70683c602e8d2050000ab4975f15a5b58c3'
    'a1eaeaeaea85c00f842d0300008b008b88b40000002dd4f5000029c181f92051'
    '00000f85120300006681384d5a0f85070300008b483c8b4c085001c183e9088d'
    '9000700100813a4247424c7509817a044f434b00740c83c20439ca76e8e9d802'
    '000083c2088995100100008b3285f60f84c50200008b45082b451cd1e80faf45'
    '0031d2f7751c8985140100008b450c2b4520d1e80faf450431d2f77520898518'
    '0100008b45082b451c0faf450031d28b4d08d1e1f7f183c0023b450076038b45'
    '008985300100008b451cc1e01031d2f775088985340100008b45000385140100'
    '0003851401000089851c0100003d800800000f87420200008b45040385180100'
    '000385180100008985200100003d580200000f87220200008dbd90000000b91f'
    '00000031c0f3abc785900000007c0000008b066a006a018d9590000000526a00'
    '56ff506485c00f85ee0100008b85a00000008985240100008b85e40000008945'
    '188b859c00000085c0740c39851c0100000f87b80100008b859800000085c074'
    '0c3985200100000f87a20100008b851c0100000faf4518c1e8033b8524010000'
    '0f87890100008b85180100000faf85240100000385b40000008985280100008b'
    '4500c1e8067505b80100000089454cc7852c010000000000008b852c0100000f'
    'af45008d1c00035d348bbd2801000083bd140100000074338b8d3001000031c0'
    '578dbd40010000e88e0200005f538d9d400100008b853401000089454031c08b'
    '8d14010000e8740300005bc745400000010031c08b4d00e86203000083bd1401'
    '00000074368b8d300100008b450029c8578dbd40010000e83e0200005f538d9d'
    '400100008b853401000089454031c08b8d14010000e8240300005b8b85240100'
    '00018528010000ff852c0100008b852c0100003b45040f823dffffff8b8d1801'
    '000085c9745d8b851c0100000faf4518c1e80389852c0100008bb5180100000f'
    'afb52401000003b5b40000008bbdb4000000e8650000008bb518010000037504'
    '4e0fafb52401000003b5b400000089f703bd24010000e8410000008bb5100100'
    '008b368b066a0056ff90800000008b95100100008b851c01000089420c8b8520'
    '010000894210c7420801000000f9c38b066a0056ff9080000000f8c351565751'
    '56578b8d2c010000c1e902f3a55f5e5903bd240100004975e65f5e59c38b4508'
    '2b451cd1e889453c85c00f84290100008b4500c1e01031d2f775088945408b45'
    '00c1e8067505b80100000089454c8b453c03451c8945640faf4540894568c1e8'
    '108b4d0029c181f9000200007605b900020000894d6c8b453c0faf4540c1e810'
    '403d000200007605b800020000894570c74548000000008b450c2b4520d1e889'
    '45308b75148b550c8b4548c1e8100faf45008d1c00035d34565231c08b4d708d'
    'bd40010000e8900000008d9d4001000089f731c08b4d3ce8820100008b4548c1'
    'e8100faf45008d1c00035d348b4568c1e8108b4d6c8dbd40010000e85a000000'
    '8d9d400100008b7d64837d18207502d1e78d3c7e8b456825ffff00008b4d082b'
    '4d64e8370100005a5e837d30007405ff4d30eb1b8b45280145488b4548c1e810'
    '3b4504720a8b450448c1e0108945480375104a0f854fffffffc3518b45340fb7'
    '00f366ab59c35652894d7489457889858800000001c149898d8c00000031c989'
    '4d54894d58894d5c894d5089c689c203554c3b958c00000076068b958c000000'
    '0fb70473e8770000004639d676f28b455431d2f775506bc066c1e808c1e00b89'
    'c18b455831d2f775506bc066c1e808c1e00509c18b455c31d2f775506bc066c1'
    'e80809c866ab8b45782b454c3b85880000007c090fb70443e8420000008b4578'
    '03454c403b858c00000077090fb70443e80b000000ff4578ff4d7475915a5ec3'
    '5289c2c1ea0b01555489c2c1ea0583e23f01555883e01f01455cff45505ac352'
    '89c2c1ea0b29555489c2c1ea0583e23f29555883e01f29455cff4d505ac35652'
    '89c689f0c1e8100fb70443837d1820750e515253e8110000005b5a59abeb0266'
    'ab0375404975db5a5ec35589c389c281e300f8000081e2e007000083e01f89dd'
    'c1e308c1e50381e50000070009eb89d5c1e205d1ed81e50003000009ea89c5c1'
    'e003c1ed0209e809d809d05dc33b56240f853901000050535256575589e981ec'
    '4005000089e5894d04895d3489c1d1e9894d008b460c8945088b460889450c8b'
    '46108945108b46248945148b46548945188b45080faf45048b4d0c0faf4d0039'
    'c8761289c831d2f7750489451c8b450c894520eb0e31d2f775008945208b4508'
    '89451c8b4500c1e01031d2f7751c8945248b4504c1e01031d2f77520894528c7'
    '452c00000000e855f9ffff0f82920000008b7d148b550c8b4d10c1e90231c057'
    'f3ab5f037d104a75ee8b450c2b4520d1e80faf45100345148b4d082b4d1cd1e9'
    '837d18207502d1e18d04488945388b45208945308b452cc1e8100faf45008d34'
    '000375348b7d3831d28b4d1c52c1ea100fb70456837d1820740466abeb0851e8'
    'a6feffff59ab5a0355244975df8b452801452c8b4510014538ff4d3075b6e81a'
    'fcffff8da5400500005d5f5e5a5b58c3'
)
TITLEROW_BLOB = bytes.fromhex(
    '8d74241c89c1d1e98b6c2414394e0c0f8542060000837e5420741789c189cdc1'
    'e90289de89d7f3a589e983e103f3a401c3c350535289c1d1e9741389de89d70f'
    'b70683c602e8ca050000ab4975f15a5b5801c3c3a1eaeaeaea85c00f842d0300'
    '008b008b88b40000002dd4f5000029c181f9205100000f85120300006681384d'
    '5a0f85070300008b483c8b4c085001c183e9088d9000700100813a4247424c75'
    '09817a044f434b00740c83c20439ca76e8e9d802000083c2088995100100008b'
    '3285f60f84c50200008b45082b451cd1e80faf450031d2f7751c898514010000'
    '8b450c2b4520d1e80faf450431d2f775208985180100008b45082b451c0faf45'
    '0031d28b4d08d1e1f7f183c0023b450076038b45008985300100008b451cc1e0'
    '1031d2f775088985340100008b450003851401000003851401000089851c0100'
    '003d800800000f87420200008b45040385180100000385180100008985200100'
    '003d580200000f87220200008dbd90000000b91f00000031c0f3abc785900000'
    '007c0000008b066a006a018d9590000000526a0056ff506485c00f85ee010000'
    '8b85a00000008985240100008b85e40000008945188b859c00000085c0740c39'
    '851c0100000f87b80100008b859800000085c0740c3985200100000f87a20100'
    '008b851c0100000faf4518c1e8033b85240100000f87890100008b8518010000'
    '0faf85240100000385b40000008985280100008b4500c1e8067505b801000000'
    '89454cc7852c010000000000008b852c0100000faf45008d1c00035d348bbd28'
    '01000083bd140100000074338b8d3001000031c0578dbd40010000e88e020000'
    '5f538d9d400100008b853401000089454031c08b8d14010000e86a0300005bc7'
    '45400000010031c08b4d00e85803000083bd140100000074368b8d300100008b'
    '450029c8578dbd40010000e83e0200005f538d9d400100008b85340100008945'
    '4031c08b8d14010000e81a0300005b8b8524010000018528010000ff852c0100'
    '008b852c0100003b45040f823dffffff8b8d1801000085c9745d8b851c010000'
    '0faf4518c1e80389852c0100008bb5180100000fafb52401000003b5b4000000'
    '8bbdb4000000e8650000008bb5180100000375044e0fafb52401000003b5b400'
    '000089f703bd24010000e8410000008bb5100100008b368b066a0056ff908000'
    '00008b95100100008b851c01000089420c8b8520010000894210c74208010000'
    '00f9c38b066a0056ff9080000000f8c35156575156578b8d2c010000c1e902f3'
    'a55f5e5903bd240100004975e65f5e59c38b45082b451cd1e889453c85c00f84'
    '290100008b4500c1e01031d2f775088945408b4500c1e8067505b80100000089'
    '454c8b453c03451c8945640faf4540894568c1e8108b4d0029c181f900020000'
    '7605b900020000894d6c8b453c0faf4540c1e810403d000200007605b8000200'
    '00894570c74548000000008b450c2b4520d1e88945308b75148b550c8b4548c1'
    'e8100faf45008d1c00035d34565231c08b4d708dbd40010000e8900000008d9d'
    '4001000089f731c08b4d3ce8780100008b4548c1e8100faf45008d1c00035d34'
    '8b4568c1e8108b4d6c8dbd40010000e85a0000008d9d400100008b7d64837d18'
    '207502d1e78d3c7e8b456825ffff00008b4d082b4d64e82d0100005a5e837d30'
    '007405ff4d30eb1b8b45280145488b4548c1e8103b4504720a8b450448c1e010'
    '8945480375104a0f854fffffffc3eb005652894d7489457889858800000001c1'
    '49898d8c00000031c9894d54894d58894d5c894d5089c689c203554c3b958c00'
    '000076068b958c0000000fb70473e8770000004639d676f28b455431d2f77550'
    '6bc066c1e808c1e00b89c18b455831d2f775506bc066c1e808c1e00509c18b45'
    '5c31d2f775506bc066c1e80809c866ab8b45782b454c3b85880000007c090fb7'
    '0443e8420000008b457803454c403b858c00000077090fb70443e80b000000ff'
    '4578ff4d7475915a5ec35289c2c1ea0b01555489c2c1ea0583e23f01555883e0'
    '1f01455cff45505ac35289c2c1ea0b29555489c2c1ea0583e23f29555883e01f'
    '29455cff4d505ac3565289c689f0c1e8100fb70443837d1820750e515253e811'
    '0000005b5a59abeb0266ab0375404975db5a5ec35589c389c281e300f8000081'
    'e2e007000083e01f89ddc1e308c1e50381e50000070009eb89d5c1e205d1ed81'
    'e50003000009ea89c5c1e003c1ed0209e809d809d05dc33b56240f8539010000'
    '50535256575589e981ec4005000089e5894d04895d3489c1d1e9894d008b460c'
    '8945088b460889450c8b46108945108b46248945148b46548945188b45080faf'
    '45048b4d0c0faf4d0039c8761289c831d2f7750489451c8b450c894520eb0e31'
    'd2f775008945208b450889451c8b4500c1e01031d2f7751c8945248b4504c1e0'
    '1031d2f77520894528c7452c00000000e85ff9ffff0f82920000008b7d148b55'
    '0c8b4d10c1e90231c057f3ab5f037d104a75ee8b450c2b4520d1e80faf451003'
    '45148b4d082b4d1cd1e9837d18207502d1e18d04488945388b45208945308b45'
    '2cc1e8100faf45008d34000375348b7d3831d28b4d1c52c1ea100fb70456837d'
    '1820740466abeb0851e8a6feffff59ab5a0355244975df8b452801452c8b4510'
    '014538ff4d3075b6e824fcffff8da5400500005d5f5e5a5b5801c3c3'
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
    'b70200008b82bf0200008b005a59ff25e2e7e7e760e8000000005d81ed3a0000'
    '008b8dab02000085c97514ff7628ff7624e8ad00000083c4088b8dab02000083'
    'f9ff0f849300000031d28b8dcb0200008339000f95c28b8dc70200008339000f'
    '95c10fb6c98d14518b8dc30200008339000f95c10fb6c98d14518b8dbf020000'
    '8339000f95c10fb6c98d145183ec6089e752ff742474ffb4248400000031c98b'
    '95bb02000085d274028b0a51ffb5b70200008d856c0300005057ff95b3020000'
    '83c41c6a008d4c2454515057ffb5ab020000ff95af02000083c460615f89461c'
    '5e5bc353565781ec24010000c785ab020000ffffffff8b1de4e4e4e4a1e3e3e3'
    'e3898424200100008d85cf02000050ff94242401000085c00f845801000089c6'
    '8d853a0300005056ffd385c00f84440100008985af0200008d85dc02000050ff'
    '94242401000085c00f84280100008d8d440300005150ffd385c00f8416010000'
    '8985b30200008d85fa0200005056ffd385c074298d8d0b03000051ffd085c074'
    '1c80b87b4d0000e975138b887c4d00008d8408e3e7e7e78985bb0200008d85e7'
    '0200005056ffd385c00f84c700000068040100008d4c2404516a00ffd085c00f'
    '84b10000008d3c0439e774074f803f5c75f6478d8d35030000e8a20000008d85'
    '180300005056ffd385c00f84860000006a008d4c240451ffd0c647ff5c8d8d4e'
    '030000e8780000008d85290300005056ffd385c074606a0068800000006a026a'
    '006a0168000000408d4c241851ffd083f8ff74428985ab02000089c7ffb42438'
    '010000ffb424380100008d8559030000508d44240c50ff95b302000083c4106a'
    '008d8c242001000051508d44240c5057ff95af02000081c4240100005f5e5bc3'
    '8a018807414784c075f6c30000000000000000000000000000000000000000f3'
    'f3f3f3f4f4f4f4f5f5f5f5f6f6f6f66b65726e656c33322e646c6c0075736572'
    '33322e646c6c004765744d6f64756c6546696c654e616d6541004765744d6f64'
    '756c6548616e646c6541004d47616d654433442e646c6c004372656174654469'
    '726563746f7279410043726561746546696c6541006c6f677300577269746546'
    '696c650077737072696e746641006672616d65732e6c6f670062756467657420'
    '2575207170632025750d0a0025752025752025752025752025750d0a00'
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
    'e923000000e980000000e9e4070000e9cb080000e91e090000e963090000e800'
    '0000005b83eb23c3535657e8eeffffffe8350200008b742414e834010000723f'
    '31c9837c2418007524e8330100008b7c241c85ff74173b4c242076048b4c2420'
    '516bc90d8db394290000f3a5598b54242485d27402890a31c05f5e5bc21800b8'
    '570007805f5e5bc21800535657e88cffffffe8d30100008b742414e8d2000000'
    '0f82c100000089c78b74241885f6742266813e445a751b83c602e85b0400003d'
    '102700007605b8102700008984bb8c2100006bc7348d941824210000b90d0000'
    '0066c702000066c74202ff0083c2044975ef8b74241c8b4c242085c9745c8b06'
    '83f80d734f6bd7348d14828d9413242100008b46143d00010000730f85c07434'
    '66833a00752e668902eb293d0003000072223d80030000731b66817a02ff0075'
    '1383e03f83f83f740ba92000000075046689420283c63449eba0e8d903000031'
    'c05f5e5bc21400b8570007805f5e5bc214000fb60683e83083f8017702f8c3f9'
    'c35256575589c58dbb942900006bf0348db4332421000031c931d2520fb70651'
    '89d1e88c00000059410fb746023dff000000740fe86b0000005189d1e8720000'
    '0059415a83c6044283fa0d72ce6bf5088db433ec20000031d20fb70605000400'
    '00510fb68c131f210000e844000000594183c6024283fa0472df8db3fc200000'
    'ba0b0000000fb64601e816000000510fb60ee81c000000594183c6024a75e65d'
    '5f5e5ac35189e9c1e10601c8050003000059c3515089c8ab31c083f902721383'
    'f905770eb80a000000abb803000000abeb02abab31c0abb810270000ab58ab31'
    'c0b907000000f3ab59c383bb780c0000000f859c00000060e882080000c78378'
    '0c0000010000008d4319a3edededed8db3842000008dbb24210000b91a000000'
    'f3a5c7838c210000e8030000c78390210000e80300006a036800000080e8c404'
    '000083f8ff744b89c68d83942100006a008d8b880c00005168ff0700005056ff'
    '93580c000056ff93640c00008b83880c0000c68418942100000031c081bb9421'
    '0000646973707505b864000000e80200000061c38db41894210000c783800c00'
    '00ffffffffe895010000750e803e000f844a010000e933010000803e5b756cc7'
    '83800c0000ffffffff0fb6460183e83183f8010f8714010000807e02500f850a'
    '0100008983840c000089fee84f0100000f84f7000000c783800c000001000000'
    '803e430f84e4000000c783800c000000000000803e4b0f84d1000000c783800c'
    '0000ffffffffe9c200000083bb800c0000ff0f84b500000083f9087544813e44'
    '656164753c817e047a6f6e65753383bb800c0000010f859200000089fee8b400'
    '00000f8485000000e82d010000e8bd0000008b93840c00008984938c210000eb'
    '6c8d93b41f00006a0de8d7000000785d5089fee87e000000745083bb800c0000'
    '01741d8d93b40d00006800010000e8b200000078355ae845000000668906eb2d'
    'b8ff00000083f9017505803e2d740f8d93b41d00006a20e889000000780c5ae8'
    '1c00000066894602eb0383c40489fe8a0684c0740a463c0a75f5e9a6feffffc3'
    '508bb3840c00006bf6348d34968db4332421000058c3e824000000741183f901'
    '750c803e3d750789fee811000000c36bc0643d282300007605b828230000c331'
    'c98a063c2074083c0974043c0d750346ebef89f78a0784c074083c2076044741'
    'ebf285c9c356575189d731c05657518a163a17750f46474975f5803f00750559'
    '5f5eeb10595f5e83c710403b44241072db83c8ff595f5ec2040031c0803e2075'
    '0346ebf80fb61683ea3083fa0977086bc00a01d046ebedc360e8c10500008dbb'
    '942100008db3fd060000e87d01000031edc783800c000001000000b00aaab05b'
    'aa8d4531aab050aab020aa8db36307000083bb800c00000174068db36e070000'
    'e847010000b05daab00aaa83bb800c000001751a8db377070000e82d0100008b'
    '84ab8c210000e82a010000b00aaa31d20fb68413122100003dff000000746b50'
    'c1e0048db418b41f0000e8fd0000008db382070000e8f2000000586bf5348d34'
    '868db4332421000083bb800c00000175210fb746023dff0000007505b02daaeb'
    '23c1e0048db418b41d0000e8bc000000eb120fb706c1e0048db418b40d0000e8'
    'a8000000b00aaa42eb86ff8b800c00000f8925ffffff4583fd020f8211ffffff'
    '578d83b00c0000506a208d8343070000508d8342070000508d8337070000508d'
    '832f07000050ff93700c00005f80bb430700000074198db316070000e84b0000'
    '008db343070000e840000000b00aaa8db39421000029f76a0468000000c0e8e3'
    '00000083f8ff742289c56a008d8b880c000051575655ff935c0c000055ff936c'
    '0c000055ff93640c000061c3ac84c07403aaebf8c35152b96400000031d2f7f1'
    'b220881747b90a00000031d2f7f185c074030430aa88d00430aa5a59c33b2053'
    '4547412052414c4c59203220636f6e74726f6c730a000a5b446973706c61795d'
    '0a5265736f6c7574696f6e203d2000446973706c6179005265736f6c7574696f'
    '6e00000000000000000000000000000000000000000000000000000000000000'
    '000000436f6e74726f6c6c6572004b6579626f61726400446561647a6f6e6520'
    '3d00203d200056578dbbb00c00006804010000576a00ff93680c000089fe8a07'
    '84c07409473c5c75f589feebf1c7065352322ec74604434647006a0068800000'
    '00ff7424186a006a03ff7424208d83b00c000050ff93540c000083f8ff740f50'
    '6a006a006a0050ff93600c0000585f5ec2080060e825f8ffff8d83e6e6e6e689'
    '44241c8b4424240fb6700c83ee3083fe01771485f6750ba1e9e9e9e989837c0c'
    '0000e80900000061c1c1c1c1c1c1ffe0e8ca0200008b83740c000083f8017674'
    '0fb68c338c0c000085c9741c49e87800000085c07473c684338c0c000000c684'
    '338e0c00003ceb4c85f6740980bb8c0c000000743ffe8c338e0c00007936c684'
    '338e0c00003c31c98d41018d56fff7da3a84138c0c00007415e82c00000085c0'
    '750c8d41018884338c0c0000eb1b4183f90472d48dbb940c00006bc61001c731'
    'c08907894704894708c3516bc6108d8418900c00005051ff93740c000059c353'
    '5657e837f7ffff8b44241031d280b8600200000375068b90080300008b4c2414'
    'e8b4000000731c8b4c241c85c9740289118b4c241885c97402890131c05f5e5b'
    'c210008d93e8e8e8e85f5e5bc2c2c2c2c2c2c2c2c2ffe2535657e8dff6ffff8b'
    '44241031d28078080375048b5424148b4c2418e861000000731c8b4c242085c9'
    '740289118b4c241c85c97402890131c05f5e5bc214008d83ecececec5f5e5bff'
    'e0535657e895f6ffff8b4c241031d2e825000000720731c0ba800000008b4c24'
    '1885c9740289118b4c241485c97402890131c05f5e5bc20c0081e90003000081'
    'f980000000723181e90001000081f9000100007202f8c331c085d2741483bb7c'
    '0c000000750b803c0a007405b880000000ba80000000f9c389cec1ee0683e13f'
    '83f93f741df7c120000000741583e1df83bb7c0c000000740931c0ba80000000'
    'f9c3e802000000f9c36bfe108dbc3b900c000083f93f0f84ae00000083f91073'
    '190fb747040fa3c8b8000000007305b880000000ba80000000c383e91083f902'
    '73120fb6440f0683f81e730231c0baff000000c383e90283f908737b0fb6944b'
    '3e0c00000fbf041780bc4b3f0c0000007502f7d885c07f0831c0ba10270000c3'
    '508b84b38c21000069c0ff7f0000b91027000031d2f7f189c15829c87f0831c0'
    'ba10270000c369c010270000f7d981c1ff7f000031d2f7f13d102700007605b8'
    '10270000ba10270000c38b84b38c210000ba10270000c331c0ba10270000c383'
    'bb500c000000757860c783500c0000010000008d83810b000050ff93e3e3e3e3'
    '89c68dbb540c00008dab8e0b00005556ff93e4e4e4e4ab45807dff0075f9807d'
    '000075ea8dab020c000055ff93e3e3e3e385c074128d8b2f0c00005150ff93e4'
    'e4e4e485c0751245807dff0075f9807d000075d6b8010000008983740c000061'
    'c36b65726e656c33322e646c6c0043726561746546696c654100526561644669'
    '6c6500577269746546696c650053657446696c65506f696e74657200436c6f73'
    '6548616e646c65004765744d6f64756c6546696c654e616d654100536574456e'
    '644f6646696c65004765745072697661746550726f66696c65537472696e6741'
    '000078696e707574315f342e646c6c0078696e707574315f332e646c6c007869'
    '6e707574395f315f302e646c6c000058496e7075744765745374617465000800'
    '08010a010a000c000c010e010e00909000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
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
DINPUT8_BLOB = bytes.fromhex(
    'e933000000500fb686600200003c1172183c1973083c1473082c10eb06b001eb'
    '02b004888660020000588b966002000080be6002000003c355e8000000005d81'
    'ed3e0000008b85d000000085c075298d859e00000050ff95e3e3e3e385c07430'
    '8d8daa0000005150ff95e4e4e4e485c0741e8985d00000008d4c24146a00518d'
    '8dc000000051680008000053ffd0eb05b8054000808d8de6e6e6e65dffe16469'
    '6e707574382e646c6c00446972656374496e7075743843726561746500909090'
    '308079bf3a48a24daa995d64ed36970000000000'
)
NOGENERIC_BLOB = bytes.fromhex(
    '74298078201174238078201972068078201c7617e8000000005f81ef19000000'
    '8dbfe6e6e6e68b0e52ffe7e8000000005f81ef300000008dbfe7e7e7e7ffe7'
)
WIDE_BLOB = bytes.fromhex(
    'e91c000000e960000000e9d4000000e912010000e8000000005b81eb19000000'
    'c360e8edffffffe89d010000618b44240c3905f7f7f7f775305351e8d4ffffff'
    '8b8bbc0200003b8bc402000075178b8bc00200003b8bc80200007509595b3905'
    'f7f7f7f7c3595b85e4c35351e8a3ffffffc705eeeeeeee80020000c705efefef'
    'efe001000031c985c07416c705eeeeeeee20030000c705efefefef58020000eb'
    '228b8bbc02000085c97418890deeeeeeee8b8bc0020000890defefefef8b8bbc'
    '020000898bc40200008b8bc002000083bbc402000000750231c9898bc8020000'
    '595bc360e82bffffffe8db0000008b8bbc0200003b8bc4020000750e8b8bc002'
    '00003b8bc80200007412a1fbfbfbfbff7050bafcfcfcfcffd283c40461a1fbfb'
    'fbfb8b4850c35081f9c9c9c9c9721981f9cacacaca771160e8d7feffffbe0100'
    '0000e80c00000061ffd183c40468cbcbcbcbc38b93cc02000085d2755ba1eaea'
    'eaea85c074628b008b88b40000002dd4f5000029c181f920510000754b668138'
    '4d5a75448b483c8b4c085001c183e9088d9000700100813a485544467509817a'
    '0452414d45740883c20439ca76e8c383c2088993cc0200008932c74204c6c6c6'
    'c6c74208cacacacac3c783bc02000000000000c783c0020000000000008dbbf0'
    '0200006804010000576a00ff15f9f9f9f989fe8a0784c07409473c5c75f589fe'
    'ebf1c7065352322ec74604434647008d83f0020000506a208d83d0020000508d'
    '83b9020000508d83ae020000508d83a602000050ff15f8f8f8f88db3d0020000'
    'e841000000723e89c7803e787405803e58753246e82d000000722a8db3f40300'
    '0083c6108b0e85c9741b39f97512394604750d89bbbc0200008983c0020000c3'
    '83c608ebdfc331c031c90fb61683ea3083fa0977096bc00a01d04641ebec85c9'
    '7402f8c3f9c3446973706c6179005265736f6c7574696f6e0000909000000000'
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
WIDE_US_BLOB = bytes.fromhex(
    'e91c000000e960000000e9f1000000e92f010000e8000000005b81eb19000000'
    'c360e8edffffffe8ba010000618b44240c3905f7f7f7f775305351e8d4ffffff'
    '8b8bd80200003b8be002000075178b8bdc0200003b8be40200007509595b3905'
    'f7f7f7f7c3595b85e4c35351e8a3ffffffc705eeeeeeee80020000c705efefef'
    'efe001000031c985c07433c705eeeeeeee20030000c705efefefef5802000083'
    '3dfafafafa007438c705eeeeeeee00040000c705efefefef00030000eb228b8b'
    'd802000085c97418890deeeeeeee8b8bdc020000890defefefef8b8bd8020000'
    '898be00200008b8bdc02000083bbe002000000750231c9898be4020000595bc3'
    '60e80effffffe8db0000008b8bd80200003b8be0020000750e8b8bdc0200003b'
    '8be40200007412a1fbfbfbfbff7050bafcfcfcfcffd283c40461a1fbfbfbfb8b'
    '4850c35081f9c9c9c9c9721981f9cacacaca771160e8bafeffffbe01000000e8'
    '0c00000061ffd183c40468cbcbcbcbc38b93e802000085d2755ba1eaeaeaea85'
    'c074628b008b88b40000002dd4f5000029c181f920510000754b6681384d5a75'
    '448b483c8b4c085001c183e9088d9000700100813a485544467509817a045241'
    '4d45740883c20439ca76e8c383c2088993e80200008932c74204c6c6c6c6c742'
    '08cacacacac3c783d802000000000000c783dc020000000000008dbb0c030000'
    '6804010000576a00ff15f9f9f9f989fe8a0784c07409473c5c75f589feebf1c7'
    '065352322ec74604434647008d830c030000506a208d83ec020000508d83d602'
    '0000508d83cb020000508d83c302000050ff15f8f8f8f88db3ec020000e84100'
    '0000723e89c7803e787405803e58753246e82d000000722a8db31004000083c6'
    '108b0e85c9741b39f97512394604750d89bbd80200008983dc020000c383c608'
    'ebdfc331c031c90fb61683ea3083fa0977096bc00a01d04641ebec85c97402f8'
    'c3f9c3446973706c6179005265736f6c7574696f6e0000900000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '00000000000000000000000000000000'
)
WIDE2D_BLOB = bytes.fromhex(
    'e928000000e927000000e926000000e92e000000e936000000e93e000000e9bd'
    '030000e9bf0b0000e9051d00006a04eb366a03eb32ff74240c810c2400000040'
    'eb25ff74240c810c2400000060eb18ff74240c810c2400000050eb0bff74240c'
    '810c24000000485553e85d030000e8ca08000083bb8c1f0000000f8544010000'
    'e8960d000081bd1c120100c40100000f852f0100008b4c240881e1ffffff8781'
    'f9000800000f871901000081bdfc23010080020000751081bd00240100e00100'
    '000f84fd00000056578b74241c83f9047505e8700b00008dbb8025000051c1e1'
    '03f3a5598dbb8025000089fedb8500240100d8b3fc1e0000db85fc230100d9c1'
    'd88bf81e0000dee9d88b001f0000d9933c1f0000d9c1d99b401f000051d906d8'
    '9b001f0000dfe09e7307810c2400000100d906d89b041f0000dfe09e7207810c'
    '240000020083c6204975d259f7c1000001007432f7c100000200742a81e1ffff'
    '0000ddd8db85fc230100d8b3f81e0000d907d8c9d91fd94704d8cad95f0483c7'
    '204975eceb2e898b441f000081e1ffff000051d907d8cad8c1d91fd94704d8ca'
    'd95f0483c7204975ea59e88b000000e8fc140000ddd8ddd88d83802500008944'
    '241c5f5e8b442408a900000040751b8b952012010083f804740881c5d6500000'
    'eb5181c526510000eb498b8d64270100a9000000207532a9000000107513a900'
    '00000875188b44241881c5ea4f0000eb228b44241881c53a500000eb168b4424'
    '1881c58a500000eb0a8b44242081c57a510000896c24085b5dc383bb281f0000'
    '000f8483010000f744241400000040740af7442414000000187410f783441f00'
    '00000003000f855f010000608b832c1f000085c074188b54243839c20f824701'
    '00003b93301f00000f873b010000db8500240100d88b181f0000d9833c1f0000'
    'd8d1dfe09e7302d9c9ddd8d99b1c1f000089ca8b442434a9000000407414a900'
    '000018750df7c1030000007505ba040000008b7424408dbb8025000031c05050'
    '516a0089d1d906d9c08b46043d0000604372073d000080437604830c2404d906'
    'd89b101f0000dfe09e7604830c2401d906d89b141f0000dfe09e7304830c2402'
    'd906d8d2dfe09e7302d9cad8d1dfe09e7602d9c9ddd883c6204975ad58595083'
    '7c2404007425d9c1d8a3341f0000d9e1d89b381f0000dfe09e7610ddd8ddd858'
    '81ee8000000083c104eb18d99b341f0000ddd8580944240401142429d10f855d'
    'ffffff5a58a904000000742b83e00383f8037423d9831c1f0000a90100000074'
    '02d9e05189d1d907d8e1d91f83c7204975f459ddd8eb05c1e20501d7ba040000'
    '0085c90f8513ffffff61c3e8000000005b81ebd003000089dd81ede7e7e7e7c3'
    '5355e8e4ffffff81bdfc2301008002000076648b442410817808800200007f57'
    '81780ce00100007f4e56575189c68dbb40140000b908000000f3a58dbb401400'
    '00e844000000db8500240100d88bf81e0000d8b3fc1e0000dab5fc230100d947'
    '18d8c9d95f18d9471cd8c9d95f1cddd8897c241c595f5e8d85496000005d5b83'
    'ec08568b74241457ffe05152b8800200000faf850024010031d2b9e0010000f7'
    'f18b8dfc23010029c1d1e9898b3c14000031c98b048f0faf85002401005199b9'
    'e0010000f7f959f7c101000000750603833c14000089048f4183f90472d55a59'
    'c35355e803ffffff83bb641400000075608b855425010085c0745656578b308d'
    '76148d839f13000050ff9514f100008d8bbf1300005150ff95acf0000089c78d'
    '8368140000506a406a0456ffd78b068983641400008d833405000089068d8368'
    '14000050ffb3681400006a0456ffd75f5e5d5bc35355e890feffff83bb601400'
    '00000f858f0100008b44240c3b85542501000f857f01000081bdfc2301008002'
    '00000f866f0100008b44241085c00f84630100008b48082b0881f9800200000f'
    '8f520100008b480c2b480481f9e00100000f8f40010000813880fdffff0f8c34'
    '0100008138000500000f8d2801000081780420feffff0f8c1b010000817804c0'
    '0300000f8d0e010000565751e8260300000f84fd00000089442418c783901500'
    '00000000008b74241c8dbb6c140000b904000000f3a583bb6c14000000753083'
    'bb7014000000752781bb7414000080020000751b81bb78140000e0010000750f'
    'c7839015000001000000e8ba0300008b74242485f674228dbb7c140000b90400'
    '0000f3a58db37c1400008dbb6c140000e820050000897424248dbb6c14000089'
    '7c241c8b47083b077e778b470c3b47047e6fc7838415000008000000598d7424'
    '1483bb9015000000741083bb94150000017507e8b3000000eb28b906000000ff'
    '742428e2faff936414000083bb9015000000740e83bb94150000007505e82900'
    '000089838c150000e81e0900005f5e5d5bc21800595f5e8b83641400005d5bff'
    'e0595f5e5d5b31c0c2180050568b368dbb98150000e81e0100005e75428b83a8'
    '15000069c0f00000000383bc15000083bbec1500001075050fb710eb028b1052'
    '568b36e81e0100005e5a3b93ec140000740dc783941500000100000058eb0cc7'
    '83941500000200000058c356575589f58b75088dbb98150000e8ba0000000f85'
    'b00000008b75008dbb00150000e8ad0000000f859200000081bba41500008002'
    '0000756d81bba0150000e0010000756181bb0c15000080020000755581bb0815'
    '0000e001000075498b83ec1500003b8354150000753b6bc0148bb3bc1500008b'
    'bb24150000bae001000089c1f3a529c629c629c629c603b3a815000029c729c7'
    '29c729c703bb101500004a75dd31c0eb0fc7839415000002000000b805400080'
    '508b7500e83d00000058508b7508e833000000585d5f5ec3ba11000000eb05ba'
    '010000005752b91f00000031c0f3ab5a5fc7077c0000008b066a0052576a0056'
    'ff506485c0c38b066a0056ff9080000000c38b0785c0741f518b8d542501003b'
    '4f04590f848b00000051508b08ff510859c7070000000057518dbb00150000b9'
    '1f00000031c0f3ab595fc783001500007c000000c78304150000070000008993'
    '08150000898b0c150000c78368150000404000008b854c25010085c0742d8b08'
    '6a00578d93001500005250ff5118898388150000e8c006000085c0750e8b8554'
    '2501008947048b0785c0c3c7070000000031c0c385c0c3578dbb7c150000b980'
    '020000bae0010000e845ffffff5fc35355e8b5faffff83bd5425010000741b51'
    '52578dbb1c160000b980080000ba58020000e81bffffff5f5a595d5bc383bb24'
    '160000000f849e00000083bd54250100000f8491000000c78324160000000000'
    '0060c783601400000100000031c089836c14000089837014000089837c140000'
    '8983801400008b85fc2301008983741400008b85002401008983781400008b83'
    '281600008983841400008b832c1600008983881400008b85542501008b086a00'
    '68000000018d937c14000052ffb31c1600008d936c1400005250ff5114c78360'
    '1400000000000061c38b44242485c07469565789c68dbb00150000b91f000000'
    '31c0f3abc783001500007c0000008b066a006a118d9300150000526a0056ff50'
    '6485c075338b831015000069c0f000000003832415000083bb54150000107505'
    '0fb710eb028b108993ec1400008b066a0056ff90800000005f5ec35355e869f9'
    'ffff83bb84150000000f84df000000ff8b84150000565751c783601400000100'
    '00008dbb6c14000031c08907894704c7470880020000c7470ce0010000e8c8f9'
    'ffff31c089837c140000898380140000c7838414000080020000c78388140000'
    'e00100006a0068000000018d837c14000050ffb37c1500008d836c14000050ff'
    'b554250100ff9364140000c7839c140000640000008b8b3c14000085c9744231'
    'c089838c140000898390140000898b941400008b8500240100898398140000e8'
    '2d0000008b85fc2301008983941400002b833c14000089838c140000e8100000'
    '00c7836014000000000000595f5e5d5bc38d839c1400005068000400016a006a'
    '008d838c14000050ffb554250100ff9364140000c331c0b980020000e8190000'
    '0083c60483c70431c0b9e0010000e80700000083ee0483ef04c351508b47082b'
    '077e408b56082b1650528b4c2408390f7d1189c82b070faf042499f77c240401'
    '06890f8b4c240c394f087e148b470829c80faf042499f77c2404294608894f08'
    '83c40883c408c3e8d5f8ffffe81efdffffe865feffff5355e8cef7ffffe83bfd'
    'ffffe85d050000c783281f0000000000005657518db3782200008dbbfc230000'
    'b961000000f3a5c783f823000000000000595f5e8b850c2401008d95584d0000'
    '5d5b83ec10ffe25157b904000000e8c9000000d983741f0000d8a3701f0000d9'
    '9b801f00008dbb782200008b93f8230000e826010000734283fa100f83980000'
    '008b83801f00008907c74704000000008b83701f00008947088b83741f000089'
    '470c8b83781f00008947108b837c1f0000894714ff83f8230000ff4704d98370'
    '1f0000d85f08dfe09e73098b83701f0000894708d983741f0000d85f0cdfe09e'
    '76098b83741f000089470cd983781f0000d85f10dfe09e73098b83781f000089'
    '4710d9837c1f0000d85f14dfe09e76098b837c1f00008947145f59c356518b06'
    '8983701f00008983741f00008b46048983781f000089837c1f0000d906d89b70'
    '1f0000dfe09e73088b068983701f0000d906d89b741f0000dfe09e76088b0689'
    '83741f0000d94604d89b781f0000dfe09e73098b46048983781f0000d94604d8'
    '9b7c1f0000dfe09e76098b460489837c1f000083c6204975a2595ec35189d1e3'
    '1ad983801f0000d827d9e1d89b0c1f0000dfe09e720883c718e2e6f959c3f859'
    'c357528dbbfc2300008b937c250000e8c8ffffff7242837f0406723bd94708d8'
    '9b001f0000dfe09e772dd9470cd89b041f0000dfe09e721fd94710d89b001f00'
    '00dfe09e7711d94714d89b081f0000dfe09e7203f8eb01f95a5fc383bb201400'
    '00000f84f200000083bb38140000000f84e500000083bb2014000002752281bd'
    '1c120100c40100000f85cc0000008b44240c25ffff000083f8040f84ba000000'
    'ff8b38140000608dbb301600008db36f130000e8860300008b44242c89c181e1'
    'ffff0000b27183f9047426b274a900000040741db26ca9000000207402b269a9'
    '000000107402b273a9000000087402b26688d0aab020aa8b851c120100e81f03'
    '000089c8e8180300008b442430e80f0300008b7424388b06e8040300008b4604'
    'e8fc0200008b4608e8f40200008b8524120100e8e902000031c08b8d24120100'
    '81f98000000073078b848bf81f0000e8cd020000e8ee02000061c383bb201400'
    '0001757483bb3814000000746bff8b38140000608dbb301600008db376130000'
    'e8b90200008b83941f0000e8910200008b8524120100e8860200008b83981f00'
    '00e87b0200008b83481f0000e8700200008b83541f0000e8650200008b834c1f'
    '0000e85a0200008b83501f0000e84f020000e87002000061c383bb2014000000'
    '744883bb3814000000743fff8b38140000608dbb301600008db384130000e83b'
    '0200008b8388150000e8130200008b854c250100e8080200008b837c150000e8'
    'fd010000e81e02000061c383bb2014000000747183bb38140000007468ff8b38'
    '1400006089f28dbb301600008db38b130000e8e70100008b838c150000e8bf01'
    '00008b02e8b80100008b4208e8b00100008b4210e8a80100008b7204e8250000'
    '008b720c85f67405e81900000052e8b40100005aff328b7208e8160000005ee8'
    '1000000061c3b904000000ade870010000e2f8c385f60f84e70000008dbb3016'
    '0000568db392130000e8700100005e89f0e84b010000578dbb00150000b91f00'
    '000031c0f3ab5fc783001500007c0000008b066a006a118d9300150000526a00'
    '56ff506450e8170100005885c00f858b0000008b8304150000e8030100008b83'
    '0c150000e8f80000008b8308150000e8ed0000008b834c150000e8e20000008b'
    '8354150000e8d70000008b8368150000e8cc00000031c083bb2415000000742e'
    '81bb08150000f000000076228b831015000069c0f000000003832415000083bb'
    '541500001075050fb700eb028b00e88e0000008b066a0056ff9080000000e8a4'
    '000000c383bb2014000000742783bb3814000000741eff8b38140000608dbb30'
    '1600008db399130000e870000000e87400000061c383bb2014000000744283bb'
    '38140000007439ff8b38140000608dbb301600008db37d130000e83f0000008d'
    'b3a01f0000b9080000008b065156e80e0000005e5983c604e2f0e82800000061'
    'c351b908000000c1c0045083e00f8a840307140000aa58e2eeb020aa59c3ac84'
    'c07403aaebf8c3c6070083bb241400000075268d839f13000050ff9514f10000'
    '8d8bac1300005150ff95acf00000898324140000e83e0000008d833016000050'
    'ff932414000083bb28140000ff742766c7070d0a8d8b301600008d470229c86a'
    '008d9334140000525051ffb328140000ff932c140000c3565781ec20010000c7'
    '8328140000ffffffff8d839f13000050ff9514f1000085c00f84c800000089c6'
    '8d83ce1300005056ff95acf0000085c00f84b000000089832c1400008d83d813'
    '00005056ff95acf0000085c00f84940000008983301400008d83e41300005056'
    'ff95acf0000085c0747c8984241c01000068040100008d4c2404516a00ff9538'
    'f0000085c0745f8d3c0439e774074f803f5c75f6478db3f5130000e8defeffff'
    'c607006a008d4c240451ff942424010000c6075c478db3fa130000e8befeffff'
    'c607006a0068800000006a026a006a0168000000408d4c241851ff9330140000'
    '89832814000081c4200100005f5ec37372322064200073723220622000737232'
    '20742000737232206c200073723220782000737232207320007372322070006b'
    '65726e656c33322e646c6c004f75747075744465627567537472696e67410056'
    '69727475616c50726f7465637400577269746546696c65004372656174654669'
    '6c6541004372656174654469726563746f727941006c6f677300643364747261'
    '63652e6c6f670030313233343536373839616263646566443344545241434500'
    '000000000000000000000000000000000000000000000000801a060000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '00000000000000000000000000000000000000004247424c4f434b0000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000008b83441f000025000003000f84410200'
    '003d000003000f843602000083f9040f872d02000056578b742428d906d99348'
    '1f0000d99b541f0000d94604d9934c1f0000d99b501f00008b46188983581f00'
    '0089835c1f00008b461c8983601f00008983641f000051d94604d89b4c1f0000'
    'dfe09e73128b460489834c1f00008b461c8983601f0000d94604d89b501f0000'
    'dfe09e76128b46048983501f00008b461c8983641f0000d906d89b481f0000df'
    'e09e73118b068983481f00008b46188983581f0000d906d89b541f0000dfe09e'
    '76118b068983541f00008b461889835c1f000083c620490f857affffff59d983'
    '541f0000d8a3481f0000d993801f0000d9c0d89be41e0000dfe09e7776d98350'
    '1f0000d8a34c1f0000d89be41e0000dfe09e775fe8e8f5ffff7251d9c0d89b00'
    '1f0000dfe09e724483bd4012010000751351528b4c242c8b116a0151ff92f800'
    '00005a59d9835c1f0000d8a3581f0000def1d99b681f0000d9833c1f0000d8b3'
    '401f0000d99b6c1f0000eb69ddd8e9cd000000ddd8898b9c1f0000e8c3000000'
    'f78524120100000000800f84b00000008b8b9c1f00008b7424288dbb80250000'
    'd906d89b001f0000dfe09e7308c70700000000eb15d906d89b041f0000dfe09e'
    '7208db85fc230100d91f83c62083c7204975cdeb6b8b7424288dbb80250000d9'
    '06d89b001f0000dfe09e731cc70700000000d906d8836c1f0000d88b681f0000'
    'd86f18d95f18eb2fd906d89b041f0000dfe09e7222db85fc230100d91fd983f8'
    '1e0000d8836c1f0000d826d88b681f0000d84718d95f1883c62083c72049759f'
    '5f5ec3c783981f000000000000c783941f00000100000083f9040f858d030000'
    'c783941f000002000000d983501f0000d8a34c1f0000d89be81e0000dfe09e0f'
    '8268030000c783941f0000030000008b85241201003d800000000f834d030000'
    '8b8483f81f00008983981f0000c783941f00000400000085c00f842e030000c7'
    '83941f0000050000005657d99bc41f0000d99bc01f00008b7424348dbbf82100'
    '00b9040000008b56088957088b560c89570c31d289571483c7204975e98dbbf8'
    '2100008b461083bb981f000002750525000000ff894710894730894750894770'
    '8b83601f000089471c89473c8b83641f000089475c89477cf783441f00000000'
    '0100745131c08907894740d9eee8e4020000d99bd41f0000d983481f0000d88b'
    '401f0000d8833c1f0000d95720d95f60e8ea020000d983541f0000d8d1dfe09e'
    '7304ddd9eb02ddd8e8a9020000d99bd81f0000eb76db85fc230100d95720d95f'
    '60d983f81e0000e88a020000d99bd81f0000d983f81e0000d983541f0000d8d1'
    'dfe09e7608ddd8d983f81e0000d88b401f0000d8833c1f0000d917d95f40ddd8'
    'd983f81e0000e874020000dee9d983481f0000d8d1dfe09e7604ddd9eb02ddd8'
    'e831020000d99bd41f00008b83d41f00008947188947588b83d81f0000894738'
    '894778d9834c1f0000d88b401f0000d95704d95f24d983501f0000d88b401f00'
    '00d95744d95f648b85241201008983901f0000c7838c1f00000100000083bb98'
    '1f00000275358b4c24308b116aff51ff92ac0000008b4c24308b115751ff92b4'
    '0000008b4c24308b11ffb3901f000051ff92ac000000e93a0100008b85341201'
    '008983e41f00008b4c24308b116a0151ff92fc0000008b4c24308b116a026a02'
    '51ff92ec0000008b85401201008983e81f000085c0740f8b4c24308b116a0051'
    'ff92f80000008b4c24308b116a0151ff92e80000008b7424348b4610e8f20000'
    '00894710894730894750894770d983ec1e0000d9835c1f0000d8a3581f0000de'
    'c9d983541f0000d8a3481f0000def9d8b3f01e0000d993dc1f0000d88bf41e00'
    '00d99be01f0000b91000000051d983d41f0000d883e01f0000d95718d95f58d9'
    '83d81f0000d883e01f0000d95738d95f78d983e01f0000d883dc1f0000d99be0'
    '1f00008b4c24348b115751ff92b4000000594975b78b4c24308b11ffb3e41f00'
    '0051ff92e80000008b4c24308b116a066a0551ff92ec00000083bbe81f000000'
    '74138b4c24308b11ffb3e81f000051ff92f8000000c7838c1f000000000000d9'
    '83c01f0000d983c41f00005f5ee869f2ffffc351525689c631d231c989f0d3e8'
    '25ff0000006bc066c1e8086bc011c1e8083dff0000007605b8ff000000d3e009'
    'c283c10883f91872d389f025000000ff09d05e5a59c3d8a3481f0000d9835c1f'
    '0000d8a3581f0000dec9d983541f0000d8a3481f0000def9d883581f0000c3d9'
    '83f81e0000d88b3c1f0000dab5fc230100c35553e892e6ffff31c08983bc1f00'
    '008983a81f00008983ac1f00008983b01f00008983b41f000089b3a41f0000c7'
    '83a01f00000100000081fe800000000f83ef000000c784b3f81f000000000000'
    '56578b7c240c8b47088983a81f0000c783a01f000002000000a9001700000f85'
    'be00000083e0088983c81f00008b47048983ac1f00000fafc085c0c783a01f00'
    '00030000000f84970000008983cc1f0000c783d01f0000000000008b370fb706'
    '8983b01f00008b8bcc1f00000fb70683c602e889000000724f01d001f883f806'
    '7706ff83d01f00004975e18b93d01f0000c1e2028b8bcc1f00006bc903b80100'
    '000039ca7205b8020000008983bc1f00008b4c240489848bf81f0000c783a01f'
    '000005000000eb1a0fb746fe8983b41f0000898bb81f0000c783a01f00000400'
    '00005f5e31c0b91f0000008d7c2428f3abe81ff3ffff8d95294100005b5dffe2'
    '83bbc81f000008741ca900800000745289c2c1ea0583e21f89c783e71fc1e80a'
    '83e01ff8c389c2c1ea0c83fa0f753389c2c1ea0483e20f89c783e70fc1e80883'
    'e00fe81000000092e80a0000009297e80300000097f8c35289c2c1ea038d0442'
    '5ac3f9c300000043000020430000a041000070410000f0c0000020440000f043'
    '0000003f00c01f440080ef430000803f000086430000ba43398e633e00000000'
    '4855444652414d45000000000000000000000000000000000000804100000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '00000000424152464c4147000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000004b494e445441424c450000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
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
    'e9ed000000e9f5010000e96a020000e9aa020000e932030000e9b5030000e800'
    '0000005b81eb2300000089dd81ede7e7e7e7c38b83c807000085c075178d83ca'
    '06000050ff958c00010085c074208983c8070000db80fc230100d99bcc070000'
    'db8000240100d99bd0070000f8c3f9c3e8beffffff7213d983cc070000d89ba8'
    '070000dfe09e7602f8c3f9c35883ec0cd983d0070000d8b3ac070000d91424d9'
    '83d0070000d88bb4070000d8abcc070000d88bb8070000d95c2404d983cc0700'
    '00d8b3a8070000def1d95c2408ffe050e8b7ffffff8b44240cdb00d80c24d844'
    '2404db18db4004d80c24db580483c40c58c3535551e824ffffffe85e030000e8'
    '6cffffff0f82890000008b4c24148b83c8070000833900752283790400751c8b'
    '80fc23010039410875118b83c80700008b800024010039410c7458565789ce8d'
    'bbd4070000c783e4070000000000008b46082b063d800200007c0c8b46080306'
    '3d80020000740ac783e40700000100000031c9db048ee832000000db1c8f4183'
    'f90472ef897c241c8d442420e83effffff5f5ee81c030000598d85ca3700005d'
    '5b5589e583ec2889742404ffe0f7c101000000753d83bbe407000000750dd88b'
    'cc070000d8b3a8070000c3d88bd0070000d8b3ac070000d983d0070000d88bb4'
    '070000d8abcc070000d88bb8070000dec1c3d88bd0070000d8b3ac070000c353'
    '55e818feffff8b44241089830c070000e81efeffff724ad983cc070000d8b3d0'
    '070000d88bb0070000d9c0d89bbc070000dfe09e762983bbe4070000007520db'
    '442410d88bc0070000d9f2ddd8dec9d9e8d9f3d88bc4070000db5c2410eb02dd'
    'd8e8930200008d85793800005d5b5589e583ec18891c24ffe0535551e89dfdff'
    'ff8b4424148983100700008b442418898314070000e8d6fdffff72098d442414'
    'e82afeffffe89b020000598d85e93900005d5b5589e583ec28891c24ffe05355'
    'e859fdffffff742414ff742414ff7424148b4424088b4c24048d95883a0000ff'
    'd28b4c24108b018983180700008b410489831c070000e875fdffff7244e88afd'
    'ffff8b4c241cd901d8a5d0280100d84c2408d985d0280100d8642404d83424de'
    'c1d919d94104d8a5cc280100d84c2408d985cc280100d83424dec1d9590483c4'
    '0ce88a0200005d5bc20c005355e8ccfcffffff742414ff742414ff7424148d95'
    'f9330000e85f0000008b4c24148b018983240700008b44241083f804740a83f8'
    '07740583f8087536e8e3fcffff722fe8f8fcffff8b4c24208b44241c83f80475'
    '0ad901d84c2408d919eb10db0183f8077504d8642404d83424db1983c40ce8cc'
    '0100005d5bc20c005589e581eca8000000ffe25355e844fcffff8b4424148b08'
    '898be80700008b4804898bec0700008b4808898bf0070000e873fcffff724ae8'
    '88fcffffd985d0280100d8642404d83424d8abe8070000d8742408d885d02801'
    '00d99be8070000d985cc280100d83424d8abec070000d8742408d885cc280100'
    'd99bec07000083c40c8d83e80700008b4c24108d95e83a00005d5bffe283bb02'
    '07000000744d608dbb280700008db38b060000e8cf0100008b742438b9040000'
    '00ade8a3010000e2f88b44243ce8980100008b442440e88f0100008b442430e8'
    '860100008b442450e87d010000e89e01000061c383bb0207000000743b608dbb'
    '280700008db393060000e8780100008b742438b904000000ade84c010000e2f8'
    '8b44243ce8410100008b442440e838010000e85901000061c383bb0207000000'
    '7442608dbb280700008db39c060000e8330100008b830c070000e80b0100008b'
    '83cc070000e8000100008b83d0070000e8f50000008b442434e8ec000000e80d'
    '01000061c383bb02070000007440608dbb280700008db3a5060000e8e7000000'
    '8b8310070000e8bf0000008b8314070000e8b40000008b442438e8ab0000008b'
    '44243ce8a2000000e8c300000061c383bb02070000007437608dbb280700008d'
    'b3b5060000e89d0000008b442434e8770000008b8324070000e86c0000008b74'
    '24388b06e861000000e88200000061c383bb0207000000745083bb2007000000'
    '7447ff8b20070000608dbb280700008db3ad060000e84d0000008b8318070000'
    'e8250000008b831c070000e81a0000008b7424348b06e80f0000008b4604e807'
    '000000e82800000061c351b908000000c1c0045083e00f8a8403ea060000aa58'
    'e2eeb020aa59c3ac84c07403aaebf8c3c6070083bb080700000075218d83bd06'
    '000050ff95ec0001008d8bd70600005150ff95880001008983080700008d8328'
    '07000050ff9308070000c373723220767020007372322076703e200073723220'
    '666f762000737232206374200073723220706a200073723220677020006b6572'
    '6e656c33322e646c6c004d47616d654433442e646c6c004f7574707574446562'
    '7567537472696e67410030313233343536373839616263646566474c54524143'
    '4500000000009090000000000000000000000000000000000000000000000000'
    'd007000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000020440000f0430000403fabaaaa3f0000003f0000803f'
    'db0f493883f9a246000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000'
)
RESOLUTION_BLOB = bytes.fromhex(
    'e924000000e96b000000e966030000e937030000e8000000005b81eb19000000'
    '89dd81ede7e7e7e7c3535551e8e3ffffff8b85d3d3d3d38b505052e8a8040000'
    'e8d10300005a83f8027c0289c289d0e8b8020000895630894e34898bcc050000'
    '8b84cb08070000894670c7467405000000595d5bc383fb06741283fb070f8482'
    '0000008b449e3831ff85c0c353555657e87fffffff8b4e343b8bcc0500007417'
    '898bcc050000c74630000000008b84cb080700008946708b85d4d4d4d48b388b'
    '47188983d4050000d94714d8460cd99bd0050000b906000000e8cd0100008983'
    'd80500008b46308b4e340384cb04070000e8fc020000b904000000e8c0010000'
    'e96c01000053555657e806ffffff8d85d7d7d7d78b78186a006a006a00837e10'
    '0775106a206a2068000100006800010000eb1468000100006800010000680001'
    '000068d8000000680000803f680000803f6a006a006a006800004041d94718d8'
    '83a8050000d993d405000051d91c24d94714d8460cd993d005000051d91c2457'
    '8d85d6d6d6d6ffd083c440d983d0050000d883ac050000d99bd0050000d983d4'
    '050000d883b0050000d99bd4050000c783d8050000000100008d832b050000b9'
    '04000000e8f7000000d983b4050000d8460cd99bd0050000b907000000e8c900'
    '00008983d80500008b4634e83b0100005250e883000000d883d0050000d99bdc'
    '05000058b904000000e8b2000000d983dc050000d99bd00500008d8338050000'
    'b904000000e896000000d983d4050000d8a3bc050000d99bd40500008d833805'
    '0000e879000000d983d4050000d883bc050000d99bd4050000d983dc050000d8'
    '83c0050000d99bd005000058e84f0000005f5e5d5b31ff31c0c3d9ee89c20fbe'
    '0285c07425420fbe8c05d8d8d8d885c97cec8b8c8ddcdcdcdc85c97405d8410c'
    'ebdcd883b8050000ebd4c3b800010000394e10750a8b4678d1f80580000000c3'
    '51518d8ddcdcdcdc51680001000068000100006800010000ffb3d80500006800'
    '00803f680000803f68000020416800002041ffb3d4050000ffb3d0050000508d'
    '85dbdbdbdbffd083c43459c331c989c22b94cb040700003b94cb08070000720a'
    '4183f90572e831c931d2c38d933a05000001c085c0740a42807aff0075f948eb'
    'f289d042807aff0075f9c35355e8c2fcffff8b4850894e30c7463400000000c7'
    '83cc050000000000008b8b08070000894e705d5bc35355e898fcffff8b46308b'
    '4e340384cb040700008b95d3d3d3d383f802720231c0894250e84a010000e80e'
    '0100008b46308b4e340384cb04070000e83d000000565789c68dbbe0050000ac'
    '3c587502b078aa84c075f45f5e8d8b00060000518d83e0050000508d835b0500'
    '00508d835305000050ff93c80500005d5bc38d932c070000833a00740583c208'
    'ebf683c20885c0740a42807aff0075f948ebf289d0c35657e8940000008d8300'
    '060000506a208d83e0050000508d8366050000508d835b050000508d83530500'
    '0050ff93c40500008db3e0050000e83e000000723689c7803e787405803e5875'
    '2a46e82a00000072228db32c07000031c98b1685d2741439fa75053946047406'
    '83c60841ebeb89c85f5ec383c8ff5f5ec331c031c90fb61683ea3083fa097709'
    '6bc00a01d04641ebec85c97402f8c3f9c356578dbb000600006804010000576a'
    '00ff95e5e5e5e589fe8a0784c07409473c5c75f589feebf1c7065352322ec746'
    '04434647005f5ec383bbc4050000007539568d836705000050ff95e3e3e3e389'
    'c68d83740500005056ff95e4e4e4e48983c40500008d838d0500005056ff95e4'
    'e4e4e48983c80500005ec341535045435420524154494f002e00340033003136'
    '00313000313600390032310039003332003900446973706c6179005265736f6c'
    '7574696f6e00006b65726e656c33322e646c6c00476574507269766174655072'
    '6f66696c65537472696e67410057726974655072697661746550726f66696c65'
    '537472696e6741000000d841000020410000004000008743000020410000c040'
    '0000c04000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
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
LOADHOLD_BLOB = bytes.fromhex(
    'e905000000e927000000890dc1c1c1c150515255e8000000005d81ed19000000'
    'ff15c2c2c2c28985bc0000005d5a5958c3505255e8000000005d81ed39000000'
    '83bdbc00000000744b83bdc00000000075258d85a800000050ff15e3e3e3e38d'
    '95b50000005250ff15e4e4e4e48985c000000085c0741dff15c2c2c2c22b85bc'
    '0000003db80b0000730a6a0aff95c0000000ebe3c785bc000000000000005d5a'
    '588b0dc1c1c1c1c36b65726e656c33322e646c6c00536c656570009000000000'
    '00000000'
)
HUDLAST_BLOB = bytes.fromhex(
    'e90a000000e94f000000e938000000e800000000582d14000000c680a6000000'
    '00b9cccccccc85c974058339007511833df3f3f3f3007408c680a600000001c3'
    'b8c6c6c6c6ffe0e8160000008b0dc3c3c3c3b8cdcdcdcdffe0b8c7c7c7c7ffd0'
    'eb00e800000000582d6700000080b8a600000000742fc680a6000000008b0dc3'
    'c3c3c36a0068c5c5c5c5b8c4c4c4c4ffd0b8c6c6c6c6ffd08b0dc3c3c3c3b8c8'
    'c8c8c8ffd0c300'
)
D3DINIT_BLOB = bytes.fromhex(
    '9c60e8000000005d81ed0700000089eb81ebe7e7e7e78983c41f01008b742424'
    '83ee0529de89c283bd94020000007505e84501000083bd94020000ff0f84fb00'
    '000081bd9c020000001000000f83eb000000ff859c02000083ec4089e789f0e8'
    'dc000000b020aa89d0e8d2000000b020aa8b83fc230100e8df000000b078aa8b'
    '8300240100e8d1000000b020aa8b83e4240100e8c3000000b078aa8b83e82401'
    '00e8b5000000b00daab00aaa89f829e06a008d4c243c51508d4c240c51ffb594'
    '020000ff959802000081fec5200000756989e7b8666d7420ab31c0b90d000000'
    '8d9314270100d1e0833a00740383c80183ea204975f0e845000000b020aa8b83'
    '40270100e837000000b020aa8b833c270100e829000000b00daab00aaa89f829'
    'e06a008d4c243c51508d4c240c51ffb594020000ff959802000083c440619dc3'
    '51b908000000c1c00450240f3c0a720204270430aa584975ed59c3515253bb0a'
    '00000031c931d2f7f3524185c075f6580430aa4975f95b5a59c352565781ec24'
    '010000c78594020000ffffffff8d85a002000050ff93b0f0000085c00f84dd00'
    '000089c68d85cf0200005056ff93acf0000085c00f84c5000000898598020000'
    '8d85be0200005056ff93acf0000085c00f84a9000000898424200100008d85ad'
    '0200005056ff93acf0000085c00f848c00000089c668040100008d4c2404516a'
    '00ff9338f0000085c074748d3c0439e774074f803f5c75f6478d8dca020000e8'
    '650000006a008d4c240451ffd6c647ff5c8d8dd9020000e84d0000006a006880'
    '0000006a026a006a0168000000408d4c241851ff94243c01000083f8ff742089'
    '85940200006a008d8c2420010000516a148d8de50200005150ff959802000081'
    'c4240100005f5e5ac38a018807414784c075f6c3000000000000000000000000'
    '6b65726e656c33322e646c6c004372656174654469726563746f727941004372'
    '6561746546696c6541006c6f677300577269746546696c6500643364696e6974'
    '2e6c6f67007369746520687220577848206d61787465780d0a'
)
PADMENU_BLOB = bytes.fromhex(
    '8304240d50565755e8000000005d81ed0d000000833ddfdfdfdf000f849a0000'
    '00525131f631ff0fb6843df70000000500030000e8b40000007308660bb47d03'
    '0100004783ff0c72de595a89f08bbd1c01000089b51c010000f7d721f7741c81'
    '0dcfcfcfcf00000080f7c700200000740a810dcfcfcfcf0020000083e1f083e0'
    '0f3b85200100008985200100007514ff8d240100007f1cc78524010000020000'
    '00eb0ac785240100001e0000000905cfcfcfcf81e6f0dfffff09f1f7d221ca89'
    '0db1b1b1b18915cececece890db2b2b2b25d5f5e58c383ec088d4c2404518d4c'
    '24045150ff15dfdfdfdf585ac3e8e4ffffff01c039c2c300010203141512130c'
    '0d04050100020004000800010002000400080010002000008000209000000000'
    '0000000000000000'
)
REPLAYPAD_BLOB = bytes.fromhex(
    '60833ddfdfdfdf007466e8000000005d81ed0f000000c1e70681c70003000031'
    'db31f60fb684359800000001f8e85c0000007308660b9c75a00000004683fe08'
    '72e18b742404091e837e100075228d4713e821000000508d4712e81800000059'
    '29c16bc17f99b910270000f7f9894610618b56088b06c383ec088d4c2404518d'
    '4c24045150ff15dfdfdfdf585ac3e8e4ffffff01c039c2c30908121311100f0e'
    '01000200040008008000000130004000'
)
PAGEPAD_BLOB = bytes.fromhex(
    '60833ddfdfdfdf0074358b7c243cc1e70681c70003000031db8d4708e83d0000'
    '00730681cb800000008d4709e82d000000730681cb00010000099e60ffffff61'
    '8b44241485c0c383ec088d4c2404518d4c24045150ff15dfdfdfdf585ac3e8e4'
    'ffffff01c039c2c3'
)
SORTPAD_BLOB = bytes.fromhex(
    '60e8000000005d81ed06000000833ddfdfdfdf00746331ffb808030000e87900'
    '0000730383cf01b809030000e86a000000730383cf028b85a800000089bda800'
    '0000f7d021f8743189eb81ebe7e7e7e78b9320e60b0085d2741f8b4a04a90100'
    '0000740a49790fb902000000eb084183f903720231c9894a04618b4e5081e7ff'
    '000000c383ec088d4c2404518d4c24045150ff15dfdfdfdf585ac3e8e4ffffff'
    '01c039c2c390909000000000'
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
    'LOADPIC': 0xC1C1C1C1,
    'GETTICK': 0xC2C2C2C2,
    'HUDLO': 0xC9C9C9C9,
    'HUDHI': 0xCACACACA,
    'WALKRESUME': 0xCBCBCBCB,
    'RENDERER': 0xC3C3C3C3,
    'SETVIEWPORT': 0xC4C4C4C4,
    'VPRECTS': 0xC5C5C5C5,
    'HUDDRAW': 0xC6C6C6C6,
    'TREEDRAW': 0xC7C7C7C7,
    'HUDRESET': 0xC8C8C8C8,
    'LATEFLAG': 0xCCCCCCCC,
    'FADEDRAW': 0xCDCDCDCD,
    'PADLEVEL': 0xB1B1B1B1,
    'PADEDGE': 0xCECECECE,
    'PADPREV': 0xB2B2B2B2,
    'MENUKEYS': 0xCFCFCFCF,
    'PADPOLL': 0xDFDFDFDF,
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
    'CHARMAP': 0xD8D8D8D8,
}
DINPUT8_MAGICS = {
    'LOADLIB': 0xE3E3E3E3,
    'GETPROC': 0xE4E4E4E4,
    'CONT': 0xE6E6E6E6,
}
NOGENERIC_MAGICS = {
    'CONT': 0xE6E6E6E6,
    'SKIP': 0xE7E7E7E7,
}
# --- GENERATED by asm/build.py: END ---

# --- GENERATED by tools/labels.py: BEGIN (do not edit) ---
# The connection screen's labels: slot -> (text, OFF, ON, ON2), each a
# zlib-compressed 218x32 8-bit mask; see tools/labels.py.
LOBBY_LABELS = {
    'IPX': ('INTERNET',
        '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'
        'i3m7578sXaGl',
    ),
    'TCPIP': ('DIRECT IP',
        'eNrtmG1X2jAUx1NG7axuTGVubur0OBybOsFRnuThMGBnaluBTfEMaku+/4dYbrtCy0PS03bjxfp/AffeJml+NNzcFKFIkSJF'
        'iuRRG5hopD3IlaOV2Ss5dzuMH/vf9me6W5Lc3WMHtd5Qv2+meWe0M2n/dsFsctOjG8NuIemTzJKW4ZhkIPmZB7LDu8mwsWBk'
        'pgpcADKM27wXMnzHs8hiZeewihCcDJ/6IVMKpYb1E3+lkilSodKDZhdTYVN7jr51c43L9Up7ANbtGO1Eki5JoEPaJ7yRKfli'
        '/Rf8D+I+yMyxNtswh/c0MtP7CA9t0VT+6BSGKq+aTy8FbDXHxXXiF1mzcbuiSoxDv2QIFV1zXkSG4C48lWxVI9GU7b241zQt'
        'GYgMpYhx7p8s1iX2NpMMVtoaleyCBBsL7+iHbHvu0vBMhj4Q+wuT7IZYcSrZD5KpxVDJMsT4FIBMJHadRXYAGcEVlnOmxnsB'
        '72oRnIxPnI+IsRmAjDMwvqaQfT85k+CJ4eN5efm1HUsQpxoamS0VBSBDOsY3HvazJkcle06cUthk+hb6i6vR0kiKISpZnDhX'
        'IZN1XqIgZMcLcobt/YR7nImUqYwLDWM9LDJFymXTGz4rYjvrQ+mzQ8sgzZlJzSWDTHbNhZkbUTCyPHOnfgplzj6TTBhCGWmj'
        '7Siqqm4tkSwJD8S5aczL+u/I50BkkaG0WQebS+hJxpiqR/8lmZyvtqyKuIUY1VVtaqE59rNdR1+r1L+tlltQaOEHcUlkk5OX'
        'wCJb6ZPvLPN8xknOYTtraLlkRpZx8gTvDeT9V+yT517Xjj+WeLQ8Mn3Qa7DfFuTsE0FfYL8t4HYvuwO91/osLCk3RooUKdJ/'
        'rd84Ppfx',
        'eNpjYBgFo2AUjIJRQCTQ/g8Efz8/OzY3ih9Tph1V3f9/Xx5v98PQDgHdqNpZgxde+/DtwbpMPmTR8wj17jhc045u+s8PVyaY'
        'kOkzCPhUx0TIZ2BwXJEIn4XfhYl/rGGhzGdg0MdEgc/+/9/MS4zP/t/lJeQz1unIxp4QpNxn/4vJ8dnJvqmr7oC1r8Xrs5Pd'
        '/XOvgpQ1oQmDgQ+S3iXgNH588Zwt70Css3CvFXZ3zwIKnAeqVyfOZyd7Ji55DaS/cpPhM7BZBltAbojD5zMwLwvIuIfLKVBQ'
        'DDJqmjiIyZL4FshehCQpD+RPJuQaVK7kaSAjlFyfMTBOAiU0gj5jANnCi9dn4p+BogkwntbDz58/m1LkM4ZEIKOKbJ8xsF4C'
        'si0I+mwxkCWL12fNQMEVOG0kx2dWWJMG0T5jSAOyWwn67AiQxYXXZ9eBJbU0VX1WB2TkUuAzaSB7CSGfBf37//8civDxdjCA'
        '1wW8oDKDgWo+Y+RVr/oDZOhT4DOmX///H8Djsz35pd2HQIVDMrZy2R4mpgHkzKOaz2DgDAMFPmP88f//ISLqs3VMeH2mCuRM'
        'pbbPvhlS4jNJAqkRAv50sjHg9RkXkLOfyj67aM5Aic+ScZQZMN4tUMuxRBqPUyDgwv//vxWo5bOT3e31GTpktoihZrGAmj6O'
        'eHzWsQ5ITGIg6LMaoOBBJmqWjQyU+awX1LpgxFc2ir4Ekn4EfSb8HijayQzlOZw8ffq00QD6zHj9f9RKA1upHwAk30gT8hlD'
        'Jsiok+AkxFH7E8heM0Bxdrxn3iZIp2MTI4HW1UIgdYCZAVt95oVk6gywaWcXTN/4CcR4JjVAPkP0vAQZCPiM/xGQrifYP2Pu'
        'Rjb2oizDwPrsZz0zAyGfMbgAmyB/bAn3PL2vwMS/TuFlGDif/Xh3dSXh0QIwbzKQ8ViI8GgBk9fMy2++Xd1UITRAZeMoGAWj'
        'YBSMaAAAUpclFg==',
        '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'
        'zm+ZuO0Xb5ma9B9aI7hl6uCC6X8dKBDs',
    ),
    'MODEM': ('LAN',
        'eNrtlktPwkAUhcc2sV2IPGKIREQTZKESNGYa8UHYALJATASfhZSe//8jvKU0QuZuTbhmzmbuPT2bL3dmOkpZWVlZWf2pigA0'
        '+2UAPHJp1FZNn2qJZLkYiDyObOrIJgsSiCZHlrlCydwwYXhjyWa+ZLLGkgFVjgx3ksmegY850DfT30BckEt2QHbQJYackb6d'
        'AgO5ZB2yS9UEz0zXVrtUJJkXARPl0C0SumZ6CLw6Qsma5F4r9UBLw0wX6Vd3LpSMjhLySlVoGTPpe5rlrkiyIzLnWuuAhoOy'
        'mfZndJGIJOthTV0mfQks9gWS7cXrZJFvpp0J0BNIprGhKyZ9TMWXODKXXhk4TOsyle87TPoppd5yspFOdJpZdbJesmZMzQlD'
        'VlhIIEvVyawRNfWsOaNmyE24LY+sRPWns7E18wyZF4ojSx4erd/ADbVt7lRebDmZlZWV1T/RD3/hsZE=',
        'eNrtls0rRFEYxs/E9bFjGmtRqGExZcNGWQmFhd0UWUvJbNhY2NyMUhILicX8A5OPqNmTsEWNjVj4mNsUNYkZj/e6cxmdd6vm'
        '1XkW97zPc5/Nr3vO7ShlZGRkZPSnagdgs2/2gU2ujeGi2aVZIllTAcgFObJ0lWyyuAsR48gwI5qsJuMyXAc4smxIMtn4FwP6'
        'OTKsSSY7AW6fgT29/QTkw3LJOileTACFZq29nAYO5JJtURwZoMeS3h4q7lKRZPU54FJZDuDU6u0UcFEplCxG6bxSG7RM6O2O'
        'PDApkyxARwmtSvXScsa014FMnUiyPgpfbNuO0z0EXXo7lKUfiUiyHZQowbSngbcWgWSNhVKy1wa9bV0BSYFkNn5pjmkP0nAv'
        'jqz6kbIeb+6m8aaCaR961GVOdmy7GvWjKEXnvjklM8KQhd8lkHna9qMjMlHfjJFJcV94VR5ZhOY763trPgAfbQxZ0BFH5l48'
        'Zn8KC2RXuFM5VeZkRkZGRv9En3f7zdE=',
        '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',
    ),
}
# --- GENERATED by tools/labels.py: END ---

# --- GENERATED by net/build.py: BEGIN (do not edit) ---
# MUSASHI\MGNetWk.dll, built from net/ and carried beside the patcher
# rather than inside it; MGNETWK_SRC the sources' hash, MGNETWK_SHA the
# file's.
MGNETWK_SRC = '56125eacbce87563fab6dd5caa904347c71eaa2932693fb08e3a3aed3f6b88e2'
MGNETWK_SHA = 'c9bc4e2eaf5614588bbeae2247728598dd9d9a823c6934823ec99baeca5a5951'
# --- GENERATED by net/build.py: END ---

MGNETWK_NAME = 'MGNetWk.dll'


def netplay_dll():
    """The DLL's bytes, read from the file that ships with the patcher:
    a checkout's net/, or beside the script, where the release puts it.

    A whole DLL written out as a blob in the middle of the script is
    what a scanner calls a dropper, and it cost the patcher a string of
    false positives. It travels as a file instead."""
    here = os.path.dirname(os.path.abspath(__file__))
    paths = [os.path.join(here, 'net', MGNETWK_NAME),
             os.path.join(here, MGNETWK_NAME)]
    if getattr(sys, 'frozen', False):
        paths.insert(0, os.path.join(getattr(sys, '_MEIPASS', here),
                                     MGNETWK_NAME))
    for path in paths:
        try:
            with open(path, 'rb') as fh:
                data = fh.read()
        except OSError:
            continue
        if hashlib.sha256(data).hexdigest() != MGNETWK_SHA:
            raise ValueError('%s is not the DLL this patcher was built with'
                             % path)
        return data
    raise ValueError('%s is missing: the internet play patch needs it beside '
                     '%s. It is in net/ in the repository and in the release.'
                     % (MGNETWK_NAME, os.path.basename(__file__)))


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
                if len(parts) < 3:
                    raise DiscError('%s: %r is not a TRACK line.' % (os.path.basename(path), line))
                cur = {'no': int(parts[1]), 'mode': parts[2].upper(), 'bin': curbin,
                       'start': 0, 'pregap': None}
                tracks.append(cur)
            elif up.startswith('INDEX') and cur is not None:
                parts = line.split()
                if len(parts) < 3:
                    raise DiscError('%s: %r is not an INDEX line.' % (os.path.basename(path), line))
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


def rip(cue, dest, log=print, progress=None):
    """Every audio track of the play disc into DEST\\music\\trackNN.wav.

    progress(track, done, total) is called as each track is written, in
    the bytes of that one track; raising out of it throws the part-written
    track away with the WavWriter."""
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
            total = (end - start) * RAW
            left = total
            while left > 0:
                chunk = src.read(min(left, RAW * 512))
                if not chunk:
                    raise DiscError('%s ends early.' % os.path.basename(t['bin']))
                dst.write(chunk)
                left -= len(chunk)
                if progress:
                    progress(t['no'], total - left, total)
        log('rip: track %02d, %d:%02d' % (t['no'], (end - start) // 75 // 60, (end - start) // 75 % 60))
    log('rip: %d tracks in %s' % (len(spans), outdir))
    return [t['no'] for t, _s, _e in spans]


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


def install(src, dest, lang='English', log=print, progress=None):
    """Copy the game out of the disc into dest. Returns the file count.

    Patching is a separate step: --install does it after this, and the
    window has its own button for it."""
    if lang not in LANGUAGES:
        raise ValueError('unknown language %s' % lang)
    fh, close = open_source(src)
    written = 0
    try:
        cab = Cabinet(fh)
        groups = install_groups(lang)
        missing = [g for g in groups if g not in cab.groups]
        if missing:
            raise ValueError('this disc has no %s' % ', '.join(missing))
        total = sum(e.size for g in groups for e in cab.groups[g])
        log('install: %d MB to %s' % (total // 1000000, dest))
        done = 0
        for g in groups:
            for e in cab.groups[g]:
                out = os.path.join(dest, *e.path.split('\\'))
                data = cab.read(e)              # decoded first: opening the file truncates it
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, 'wb') as dst:
                    dst.write(data)
                done += e.size
                written += 1
                if progress:
                    progress(done, total)
            log('install: %s, %d files' % (g, len(cab.groups[g])))
    finally:
        close()
    write_manifests(dest)
    log('install: manifests written')
    return written


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
CLEARSIZE_LEN = 12                      # exe, the clear's two arguments and its call
def exe_blob(blob, build):
    """A stub with the build's addresses in place of the placeholders."""
    row = BUILDS[build]
    values = dict(row['addresses'], LOADLIB=row['slots']['LoadLibraryA'], GETPROC=row['slots']['GetProcAddress'],
                  SETTEXTCOLOR=row['slots']['SetTextColor'], GETPPS=row['slots']['GetPrivateProfileStringA'],
                  GETMODFN=row['slots']['GetModuleFileNameA'], GETTICK=row['slots']['GetTickCount'])
    out = bytes(blob)
    for name, magic in EXE_MAGICS.items():
        out = out.replace(struct.pack('<I', magic), struct.pack('<I', values[name]))
    return out


def _image_base(buf):
    """The optional header's ImageBase."""
    return struct.unpack_from('<I', buf, struct.unpack_from('<I', buf, 0x3c)[0] + 24 + 28)[0]


def _call_target(buf, off):
    """The VA a `call rel32` at a file offset in .text goes to."""
    rva = 0x1000 + off - _rva_to_off(buf, 0x1000) + 5 + struct.unpack_from('<i', buf, off + 1)[0]
    return rva + _image_base(buf)


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


def apply_clearsize(buf, build):
    """Australia's mode setter clears the back buffer with the width for
    both the width and the height (`0x441783`: `mov eax, [WIDTH]` and the
    same value pushed twice), where Europe's and America's pass the
    height. The clear writes width rows of a height-row surface, which
    off the end of a 640x480 one lands in whatever the driver left there
    and at a widescreen size runs thousands of rows past it: on wined3d
    that is a page fault on the first frame.

    A thunk in the annex pushes the two globals the right way round -
    the height first, as Europe's caller does - and jumps into the clear
    rather than calling it, so the clear returns straight to the site
    and the arguments stay for the caller's own `add esp, 8` to take
    off. The clear is cdecl; a thunk that called it and returned would
    leave its two arguments where the return address belongs."""
    row, site = BUILDS[build]['addresses'], BUILDS[build]['sites']['clearsize']
    thunk = (b'\x58'                                              # pop eax, the return into the site
             + b'\xff\x35' + struct.pack('<I', row['HEIGHT'])     # push dword [HEIGHT]
             + b'\xff\x35' + struct.pack('<I', row['WIDTH'])      # push dword [WIDTH]
             + b'\x50'                                            # push eax, the return back on top
             + b'\xe9' + b'\0' * 4)                               # jmp the clear
    out, rva = append_section(buf, thunk, chars=CODE_SECTION)
    base = struct.unpack_from('<I', out, struct.unpack_from('<I', out, 0x3c)[0] + 24 + 28)[0]
    struct.pack_into('<i', out, _rva_to_off(out, rva) + 15, row['CLEAR'] - (base + rva + len(thunk)))
    _branch(out, site, rva, CLEARSIZE_LEN)
    return out


def apply_loadhold(buf, build):
    """loadhold.asm: the store of the new loading picture at its create and
    the load of it at the step that deletes it once the course is in, six
    bytes each, become calls into the blob's two entries, which make the
    same store and load around noting the tick and waiting out the hold.
    The annex keeps the tick and Sleep, so it is writable."""
    create, step = BUILDS[build]['sites']['loadhold']
    out, rva = append_section(buf, exe_blob(LOADHOLD_BLOB, build))
    _branch(out, create, rva, 6)
    _branch(out, step, rva + 5, 6)
    return out


def apply_padmenu(buf, build):
    """padmenu.asm: the six-byte store of the pad poll's level word becomes
    a call into the blob, which puts the annex's buttons into the level,
    makes the edge and the three stores, and puts its directions, a press
    of Back as TAB and any press as a key into the keyboard's menu word.
    The annex keeps what was down and the repeat's count, so it is
    writable."""
    out, rva = append_section(buf, exe_blob(PADMENU_BLOB, build))
    _branch(out, BUILDS[build]['sites']['padmenu'], rva, 6)
    return out


def apply_replaypad(buf, build):
    """replaypad.asm: the two loads at the join of the replay controls'
    keyboard and joystick paths (`mov edx, [esi+8]; mov eax, [esi]`)
    become a call into the blob, which ORs the annex's pad into the
    player's level word and the stick into its analog, then makes them."""
    out, rva = append_section(buf, exe_blob(REPLAYPAD_BLOB, build))
    _branch(out, BUILDS[build]['sites']['replaypad'], rva, 5)
    return out


def apply_pagepad(buf, build):
    """pagepad.asm: the load and test after the input wrapper's table loop
    (`mov eax, [esp+0x10]`; `test eax, eax`, the Australian `cmp eax, ebp`
    with ebp 0) become a call into the blob, which ORs the annex's LB and
    RB into the player's level word as Page Up and Page Down, then makes
    them."""
    out, rva = append_section(buf, exe_blob(PAGEPAD_BLOB, build))
    _branch(out, BUILDS[build]['sites']['pagepad'], rva, 6)
    return out


def apply_hudlast(buf, build):
    """hudlast.asm: the HUD call in the state's draw, the tree draw in the
    frame's and the fade node's draw thunk become branches into the
    blob's three entries."""
    row = BUILDS[build]
    state, late, fade = row['sites']['hudlast']
    _check_call(buf, state, row['addresses']['HUDDRAW'], 'the HUD draw')
    _check_call(buf, late, row['addresses']['TREEDRAW'], 'the tree draw')
    _check_call(buf, fade + 6, row['addresses']['FADEDRAW'], 'the fade draw')
    out, rva = append_section(buf, exe_blob(HUDLAST_BLOB, build))
    _branch(out, state, rva)
    _branch(out, late, rva + 5)
    _branch(out, fade, rva + 10, 11, op=b'\xe9')
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
# stay plain, for the pause menu. The exe's own screens take their
# confirm, back and Enter from actions 10, 11 and 12 (NOTES.md, *The
# menus' directions*), so A, B and Start sit on those as well, menu-only.
MENU_ONLY, MENUKEY_BASE = 0x20, 0x400
MENU_CONFIRM, MENU_BACK, MENU_ENTER = 10, 11, 12
FIXED_ACTIONS = (2, 3, 4, 5)
FIXED_KEYS = ((0xc8, 0xd0, 0xcb, 0xcd), (0x11, 0x1f, 0x1e, 0x20))
FIXED_PADS = ((2, PAD_UP), (3, PAD_DOWN), (4, PAD_LEFT | MENU_ONLY), (5, PAD_RIGHT | MENU_ONLY),
              (2, PAD_LS_UP), (3, PAD_LS_DOWN), (4, PAD_LS_LEFT | MENU_ONLY), (5, PAD_LS_RIGHT | MENU_ONLY),
              (MENU_CONFIRM, PAD_A | MENU_ONLY), (MENU_BACK, PAD_B | MENU_ONLY), (MENU_ENTER, PAD_START | MENU_ONLY))
ANNEX_NAME = 16
# The annex's table offsets, as padinput.asm's T_* define them; the
# working area follows at ANNEX_TABLES and ends at ANNEX_END.
T_PADNAMES, T_ACTNAMES, T_DEFAULTS, T_FIXKEYS, T_FIXPADS, T_ORDER, T_FIXACTS = 4096, 4608, 4816, 4920, 4936, 4958, 4971
ANNEX_TABLES, ANNEX_END = 4976, 9280


def annex_tables():
    """The name tables and defaults after padinput.asm's code."""
    out = bytearray(ANNEX_TABLES)

    def names(offset, table):
        for i, name in enumerate(table):
            name = name.replace(' ', '_').encode('ascii')
            out[offset + i * ANNEX_NAME:offset + i * ANNEX_NAME + len(name)] = name
    names(0, [KEY_NAMES.get(code, 'KEY %d' % code) for code in range(256)])
    names(T_PADNAMES, PAD_NAMES)
    names(T_ACTNAMES, ACTION_NAMES)
    for player, keys in enumerate((KEYS_1P, KEYS_2P)):
        for action in range(13):
            struct.pack_into('<HH', out, T_DEFAULTS + (player * 13 + action) * 4, keys[action], PAD_DEFAULT[action])
        struct.pack_into('<4H', out, T_FIXKEYS + player * 8, *FIXED_KEYS[player])
    for i, (action, pad) in enumerate(FIXED_PADS):
        out[T_FIXPADS + i * 2], out[T_FIXPADS + i * 2 + 1] = action, pad
    out[T_ORDER:T_ORDER + len(TEXT_ORDER) + 1] = bytes(TEXT_ORDER) + b'\xff'
    out[T_FIXACTS:T_FIXACTS + 4] = bytes(FIXED_ACTIONS)
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
    device's poll too on every build but the Australian, where the keyboard
    poll's address in the record update's dispatch is pointed at the
    annex's five-argument entry."""
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


def _fill_relative(out, rva, blob, magics, values):
    """A blob placed at rva with each placeholder replaced by the offset,
    from the blob's start, of the RVA named for it: what a DLL stub, which
    finds its own base with call/pop, adds to reach the thing."""
    code = bytes(blob)
    for name, magic in magics.items():
        code = code.replace(struct.pack('<I', magic), struct.pack('<i', values[name] - rva))
    start = _rva_to_off(out, rva)
    out[start:start + len(code)] = code


def apply_dinput8(buf, build):
    """dinput8.asm in MGInput.dll: the DirectInputCreateA call becomes a
    jump to its create, the first read of the device's type byte a call
    to its translation; the interface ids were rewritten as sites."""
    create, kind, _iid_di, _iid_dev = BUILDS[build]['sites']['dinput8']
    out, rva = append_section(buf, DINPUT8_BLOB, chars=CODE_SECTION | 0x80000000)
    _fill_relative(out, rva, DINPUT8_BLOB, DINPUT8_MAGICS, {
        'LOADLIB': _iat_slot(buf, 'kernel32.dll', 'LoadLibraryA'),
        'GETPROC': _iat_slot(buf, 'kernel32.dll', 'GetProcAddress'),
        'CONT': _off_to_rva(buf, create + 18)})
    _branch(out, create, rva, 18, op=b'\xe9')
    _branch(out, kind, rva + 5, 7 if kind == 0x39ac else 6)
    return out


def apply_nogeneric(buf, build):
    """nogeneric.asm in MGInput.dll: the device loop's null-GUID branch and
    the two instructions after it become a jump to the filter, which makes
    the branch, skips a type-0x11 instance the same way, and does the two
    on the way back."""
    at = BUILDS[build]['sites']['nogeneric']
    out, rva = append_section(buf, NOGENERIC_BLOB)
    _fill_relative(out, rva, NOGENERIC_BLOB, NOGENERIC_MAGICS, {'CONT': _off_to_rva(buf, at + 5), 'SKIP': _off_to_rva(buf, at + 2 + 0x1c)})
    _branch(out, at, rva, 5, op=b'\xe9')
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
PAGE_HEADER_Y = 136.0                   # the KEY and PAD headings above the columns
PAGE_LABEL_VALUE = 18                    # the value string the selector's label lives in
FLAGS_CENTRED = 2
PAGE_HEADER_COLOUR = (0x100, 0xff, 0xd0, 0xa0)  # (alpha, red, green, blue) in 256ths: a warm off-white
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


def bind_data():
    """The page's data block: the rows' actions, the live flag the page
    tests (byte 15, always set now that every build's MGInput carries the
    annex), the defaults and the key and pad names."""
    out = bytearray(DATA_SIZE)
    for i, (_name, action) in enumerate(PAGE_ACTIONS):
        out[DATA_ROWACTS + i] = action
    out[DATA_ROWACTS + 15] = 1
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

# The twenty-one letters the hint lines need, cut from sheet 4 of the
# English OPTIONS.TXR at the boxes above: 565 texels, each glyph
# (x1 - x0) by HINT_ROWS, the letters in sorted order, deflated. The
# lettering travels with the patcher rather than being cut from the file
# being patched because sheet 4 is localised - on a Japanese install
# every one of the twenty-one is different artwork, and letters cut from
# there come out as nonsense. Cutting from the English sheet gives these
# same bytes, so an English install's OPTIONS.TXR is unchanged by this.
HINT_LETTERING = zlib.decompress(bytes.fromhex(
    '78dacd983f8eab3010c62928285270058eb057e00689948222558e90928e224514e5045c2147e00a505050440a47c811'
    'b2fae97b23db6ff769c942a48725c763ecf1fcfd3c647c8e935bf4e7199f557adaaccf45ebbf2ddaa1d93d341e9a38d3'
    'daf519ba4aa328c92f07666ef7a189a22a65ed6acf8af599b7acebeb24efebae345a6d3a0defdbddd18cba323c0f2943'
    '799097199ebefe4e9f398dd3ed4972a838eb4a5a5f43394d7ea2ec9146c665685ee3129eee249bafa9f34657bab397a0'
    '7d39e55d34c09bcbf0f7e9256cb07be0151b9f3692bd4a9923daabb42b99add2f199e4763e3953b4d28ac8bb1c929c28'
    '64eff1c3f891251607ceafcab7d5de7260f7800ffc9c7eace94ace67ddf83c7e907d45cbbacb41ebc906e35fa5960dbe'
    '3eef6de88b0c8c0c439016e9567be959b46004abd04072f5b55693b3cc26b9de91e3ecc7ca43a3de283cb0da6fafda27'
    '3bc7193bb657e93c2fff8595ff1a0f0df829dfca9beaf18f6642cc7d6d4c7e181ff5e824bbcabecb358b8ddb5d3ea8d2'
    'ed5576c7b671665657fe9ac7cc0be118b9fdf5e2834de2ccf1575cce45e8af3e217734e644df7eebb3c3a1dffa053ef2'
    '0bde5064dbb9e15dba64131e68acf3a2e8b4199f4800aa284f0c25f44b8fdf841846d1743b3be4c14e6e1f58024ff661'
    '49ddb08637caa979d1179efe1d65790b75da70af57a96a823893b6d228d476696a9ecf42b4fa7b667a3fbd42995e3f40'
    'e1d7d346d4edaeea4a14984acda79a8b6808ab173c63379aeca47d420a77027bb757a374272e67d339fd5279e9c76992'
    'fb714a7500ad98ba1cfedf389d83416082e105b150b43e96086f7fa391cf136f59f505e6992cef435b7786fb32511eec'
    '1e3e066dafcb79139e20aeb0f9f8e19f273cfc09395fd34ddf4951f0509bf977dd94df57505fb2861cc847ec2b59a809'
    '5e91801850a528845a2e26acbe53b5b3dc787d160e2aa2e991fdfdd16cdf0eaacff03572e0117efb1afb935d58f37627'
    '3e407d7dddd84ecb3fa4e6f6d0ff02faf2972f84067e6ce82bddc76f8b5855fba6376f40c9afed13951e448f'
))


def hint_lettering():
    """{glyph box: its 565 texels, HINT_ROWS rows} from HINT_LETTERING."""
    out, at = {}, 0
    for c in sorted(set(''.join(HINT_LINES)) - {' '}):
        glyph = HINT_GLYPHS[c]
        n = (glyph[2] - glyph[0]) * HINT_ROWS * 2
        out[glyph] = HINT_LETTERING[at:at + n]
        at += n
    return out


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
    UV entries. Confirming selects the page's state (devices_page). The
    stock items move to four-across positions."""
    cursor, icons, labels, labelend, dispatch, ftab, topcmp, confirm = BUILDS[build]['sites']['devices']
    base = _image_base(buf)

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
    base = _image_base(buf)
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

    def piece(key):
        """A sprite of one texel box, drawn at its own size about its centre."""
        sheet, x0, y0, x1, y1 = key
        w, h = float(x1 - x0), float(y1 - y0)
        rect = (-w / 2, -h / 2, w / 2, h / 2)
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
    blob[off_data:] = bind_data()
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
    letters = hint_lettering()          # the frame's messages' lettering, carried, not cut
    tops = iter(HINT_STRIP_TOPS)
    for line in HINT_LINES:                 # the hint lines, letter by letter, each in two halves
        placed, _width, cut = hint_layout(line)
        for half in (placed[:cut], placed[cut:]):
            top, x0 = next(tops), half[0][0]
            width = half[-1][0] + half[-1][1][2] - half[-1][1][0] - x0
            for y in range(HINT_ROWS):          # the strip opaque white, a margin each side, then the letters
                for x in range(width + 2 * HINT_MARGIN):
                    struct.pack_into('<H', texture, ((top + y) * 256 + 1 + x) * 2, 0xffff)
            for x, glyph in half:
                gx0, _gy0, gx1 = glyph
                for y in range(HINT_ROWS):
                    for gx in range(gx1 - gx0):
                        v = struct.unpack_from('<H', letters[glyph], (y * (gx1 - gx0) + gx) * 2)[0]   # 565 to 4444, opaque
                        texel = 0xf000 | (v >> 12) << 8 | (v >> 7 & 15) << 4 | (v >> 1 & 15)
                        struct.pack_into('<H', texture, ((top + y) * 256 + 1 + HINT_MARGIN + x - x0 + gx) * 2, texel)
    out = bytearray(data)
    struct.pack_into('<I', out, 4, len(TXR_ENTRIES) + 1)
    struct.pack_into('<4I', out, 16 + 16 * len(TXR_ENTRIES), 8, 256, len(texture), 0)
    return bytes(out + texture)


# The connection screen's art, with the lobby patch: the three labels in
# LOBBY_LABELS over the stock button files of rows 0-2, and the backdrop's
# baked-in labels redone at the rows' new places.
LOBBY_DIR = 'BINDATA\\connect\\PROTOCOL'
LOBBY_BACKDROP = 'CONNECT.BMP'
LOBBY_BACKDROP_MD5 = 'dc4135471bb4a5c6e6de5a2b882e1c2e'
LOBBY_BACKDROP_SIZE = (228, 287)
LOBBY_LABEL_SIZE = (218, 32)
LOBBY_STATES = ('OFF', 'ON', 'ON2')
LOBBY_CLEAR = (54, 246)                 # the stock rows' span in the backdrop, cleared
LOBBY_FILES = tuple('CONNECT_%s_%s.BMP' % (slot, state) for slot in LOBBY_LABELS for state in LOBBY_STATES)
MPDATA = 'MPDATA.DAT'


def lobby_mask(slot, state):
    return zlib.decompress(base64.b64decode(LOBBY_LABELS[slot][1 + LOBBY_STATES.index(state)]))


def bmp24(mask, size=LOBBY_LABEL_SIZE):
    """A 24-bit BMP of an 8-bit mask, grey on black, as the stock buttons."""
    w, h = size
    stride = (w * 3 + 3) & ~3
    rows = bytearray()
    for y in range(h - 1, -1, -1):
        row = mask[y * w:(y + 1) * w]
        rows += bytes(v for v in row for _ in range(3)) + b'\0' * (stride - w * 3)
    head = b'BM' + struct.pack('<IHHI', 54 + len(rows), 0, 0, 54)
    info = struct.pack('<IiiHHIIiiII', 40, w, h, 1, 24, 0, len(rows), 2834, 2834, 0, 0)
    return head + info + bytes(rows)


def lobby_backdrop(data):
    """CONNECT.BMP (8-bit) with the stock rows' labels cleared and the
    three OFF labels painted at LOBBY_ROWS, as the buttons land, through
    the nearest greys of its own palette."""
    w, h = LOBBY_BACKDROP_SIZE
    if len(data) != 54 + 1024 + w * h or data[:2] != b'BM' or struct.unpack_from('<iiHH', data, 18) != (w, h, 1, 8):
        raise ValueError('%s is not the stock file' % LOBBY_BACKDROP)
    start = struct.unpack_from('<I', data, 10)[0]
    palette = [tuple(data[54 + i * 4:54 + i * 4 + 3]) for i in range(256)]
    greys = {}
    for i, (b, g, r) in enumerate(palette):
        if r == g == b:
            greys.setdefault(r, i)
    levels = sorted(greys)
    nearest = [greys[min(levels, key=lambda l: abs(l - v))] for v in range(256)]
    out = bytearray(data)

    def offset(x, y):                   # rows bottom-up
        return start + (h - 1 - y) * w + x
    for y in range(*LOBBY_CLEAR):
        out[offset(0, y):offset(0, y) + LOBBY_LABEL_SIZE[0]] = bytes([greys[0]]) * LOBBY_LABEL_SIZE[0]
    for slot, y0 in zip(LOBBY_LABELS, LOBBY_ROWS):
        mask = lobby_mask(slot, 'OFF')
        lw, lh = LOBBY_LABEL_SIZE
        for y in range(lh):
            for x in range(lw):
                v = mask[y * lw + x]
                if v and 0 <= x - 1 < w:
                    out[offset(x - 1, y0 + y)] = nearest[v]
    return bytes(out)


def lobby_art(dest, wanted, log):
    """Write the lobby's art, or put the stock files back."""
    folder = os.path.join(dest, *LOBBY_DIR.split('\\'))
    names = (LOBBY_BACKDROP,) + LOBBY_FILES
    if not wanted:
        for name in names:
            path = os.path.join(folder, name)
            if os.path.isfile(path + '.bak'):
                os.replace(path + '.bak', path)
                log('patch: %s\\%s back to stock' % (LOBBY_DIR, name))
        return
    for name in names:
        path = os.path.join(folder, name)
        source = path + '.bak' if os.path.isfile(path + '.bak') else path
        if not os.path.isfile(source):
            raise ValueError('%s\\%s is missing' % (LOBBY_DIR, name))
    backdrop = os.path.join(folder, LOBBY_BACKDROP)
    source = backdrop + '.bak' if os.path.isfile(backdrop + '.bak') else backdrop
    if md5(source) != LOBBY_BACKDROP_MD5:
        raise ValueError('%s\\%s is not the file the patcher knows' % (LOBBY_DIR, LOBBY_BACKDROP))
    with open(source, 'rb') as fh:
        data = fh.read()
    outputs = [(LOBBY_BACKDROP, lobby_backdrop(data))]
    for slot in LOBBY_LABELS:
        for state in LOBBY_STATES:
            outputs.append(('CONNECT_%s_%s.BMP' % (slot, state), bmp24(lobby_mask(slot, state))))
    for name, out in outputs:
        path = os.path.join(folder, name)
        if not os.path.isfile(path + '.bak'):
            os.replace(path, path + '.bak')
        with open(path, 'wb') as fh:
            fh.write(out)
    log('patch: %s\\%s and the %d button files written, lobby' % (LOBBY_DIR, LOBBY_BACKDROP, len(LOBBY_FILES)))
    clamp_mpdata(dest, log)


def clamp_mpdata(dest, log):
    """MPDATA.DAT keeps the connection type chosen last time; a stock 3
    (serial) is past the three rows, so it goes back to 0."""
    path = os.path.join(dest, MPDATA)
    if not os.path.isfile(path):
        return
    with open(path, 'rb') as fh:
        data = bytearray(fh.read())
    if data[:4] == b'MPFH' and len(data) >= 0x80 and data[6] > 2:
        data[6] = 0
        with open(path, 'wb') as fh:
            fh.write(data)
        log('patch: %s connection type reset' % MPDATA)


def _next_section_rva(buf):
    """Where append_section will put the next section, while the annex
    is not there yet: once it is, append_section grows it in place at
    its own RVA. apply_devices needs this before it appends, so devices
    must come before resolution, the other Options.dll patch with an
    annex, in patches() - and does."""
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


def apply_titlebg(buf, build):
    """Title.dll's own .bg row copy through bgrow.asm's TITLE build. The
    site holds no absolute address, so no relocation entry goes; the blob
    holds one, the exe's device object, which the exe is fixed enough
    for."""
    out, rva = append_section(buf, exe_blob(TITLEROW_BLOB, build), chars=CODE_SECTION)
    _branch(out, TITLEROW_SITE, rva, TITLEROW_LEN)
    return out


def apply_widescreen(buf, build):
    """wide.asm in the exe, with the resolution table after it: the mode
    setter's compare and size stores and the screen-change routine's
    settings load call its three entries; the element walker's callback
    call jumps to the fourth."""
    row = BUILDS[build]
    blob = WIDE_US_BLOB if build == 'American' else WIDE_BLOB
    out, rva = append_section(buf, exe_blob(blob, build) + resolution_table())
    modecheck, setsize, screen, walk = row['sites']['wide']
    _branch(out, modecheck, rva, 10)
    _branch(out, setsize, rva + 5, 0x49 if build == 'American' else 42)
    _branch(out, screen, rva + 10, 8)
    _branch(out, walk, rva + 15, 6, op=b'\xe9')
    return out


def apply_gltrace(buf, _build=None):
    """The trace flag in widegl.asm, found by its marker in the annex."""
    at = buf.find(b'GLTRACE\0')
    if at < 0:
        raise ValueError('gltrace needs widescreen3d')
    buf[at + 8:at + 12] = struct.pack('<I', 1)
    return buf


def apply_d3dtrace(buf, _build=None, value=1):
    """The trace flag in wide2d.asm, found by its marker in the annex."""
    at = buf.find(b'D3DTRACE\0')
    if at < 0:
        raise ValueError('d3dtrace needs widescreen2d')
    buf[at + 9:at + 13] = struct.pack('<I', value)
    return buf


def apply_d3dtrace2d(buf, _build=None):
    """The same flag at 2: the lists, strips and fans of the 2D only."""
    return apply_d3dtrace(buf, _build, 2)


def apply_widegl(buf, _build=None):
    """widegl.asm in MGameGL: SetViewport, SetPerspective, SetCentre and
    the parameter getter jump to its entries from their prologues, the
    projection and its inverse from their first two loads; none of the
    replaced bytes holds an absolute. The section is writable for the
    copies."""
    out, rva = _self_section(buf, WIDEGL_BLOB)
    _branch(out, WIDEGL_SITES[0], rva, 10, op=b'\xe9')
    _branch(out, WIDEGL_SITES[1], rva + 5, 9, op=b'\xe9')
    _branch(out, WIDEGL_SITES[2], rva + 10, 9, op=b'\xe9')
    _branch(out, WIDEGL_SITES[3], rva + 15, 8, op=b'\xe9')
    _branch(out, WIDEGL_SITES[4], rva + 20, 9, op=b'\xe9')
    _branch(out, WIDEGL_SITES[5], rva + 25, 8, op=b'\xe9')
    return out


def apply_wide2d(buf, _build=None):
    """wide2d.asm in MGameD3D: the quad, triangle, list, indexed-list,
    strip and fan draws jump to its first six entries and the present to
    its eighth, the absolute in each replaced span losing its relocation
    entry; the viewport setter jumps to the seventh from its first nine
    bytes and the texture create to the ninth from the thirteen after
    its system-memory copy, which hold none. The section is writable:
    the scaled copies, the tile tables, the texture kinds and the block
    the lobby's and the .bg pictures' surfaces are kept in live in it."""
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
    it: the page's row load, draw loop, row store and DEFAULT's row store
    call its entries, the count's 800x600 check is jumped over; the absolutes in the
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
              'GETMODFN': opt['GETMODFN'], 'CHARMAP': opt['CHARMAP']}
    base = _image_base(buf)
    blob = bytes(RESOLUTION_BLOB)
    for name, magic in RESOLUTION_MAGICS.items():
        blob = blob.replace(struct.pack('<I', magic), struct.pack('<I', values[name] - base))
    groups = resolution_groups()
    # the groups, then the table
    blob = blob[:-len(groups)] + groups + resolution_table(strings=True)
    out, rva = _self_section(buf, blob)
    _branch(out, RESOLUTION_INIT, rva, 14)
    _branch(out, RESOLUTION_DRAW, rva + 5, 8)
    _branch(out, RESOLUTION_LEAVE, rva + 10, 12)
    _branch(out, RESOLUTION_RESET, rva + 15, 6)
    return out


def _self_section(buf, blob, chars=CODE_SECTION | 0x80000040):
    """Places in the annex a blob that finds the image base from its own
    RVA, written over its MAGIC_SELFRVA (FULLWIN_MAGIC here, the same
    value in every self-locating stub). Returns (buffer, RVA)."""
    out, rva = append_section(buf, blob, chars=chars)
    start = _rva_to_off(out, rva)
    out[start:start + len(blob)] = blob.replace(struct.pack('<I', FULLWIN_MAGIC), struct.pack('<I', rva))
    return out, rva


def apply_netplay(buf, _build=None):
    """MUSASHI\\MGNetWk.dll replaced whole by the build in net/: the
    same CLSID and vtables over UDP; see docs/NETWORK.md and net/."""
    del buf
    return bytearray(netplay_dll())


def apply_texrange(buf, _build=None):
    """texrange.asm in MGameD3D: the texture release's first ten bytes
    jump to it; the absolute in them loses its relocation entry."""
    if _drop_relocations(buf, {0x4431}) != 1:
        raise ValueError('relocation entry for the texture table not found')
    out, rva = _self_section(buf, TEXRANGE_BLOB, chars=CODE_SECTION)
    _branch(out, TEXRANGE_SITE, rva, 10, op=b'\xe9')
    return out


def apply_d3dinit(buf, _build=None):
    """The diagnostic: every last-HRESULT store in MGameD3D's bring-up
    tree calls d3dinit.asm, which does the store and logs it; each
    store's absolute loses its relocation entry. The section is
    writable for the handle and the count."""
    if _drop_relocations(buf, {off + 1 for off in D3DINIT_SITES}) != len(D3DINIT_SITES):
        raise ValueError('relocation entries for the HRESULT stores not all found')
    out, rva = _self_section(buf, D3DINIT_BLOB)
    for off in D3DINIT_SITES:
        _branch(out, off, rva, 5)
    return out


def apply_replayfree(buf, _build=None):
    """replayfree.asm in ReplayGallery: the gallery's new at 0x10003b65
    calls the first thunk, its End's free of the replay the second. The
    section is writable: the thunks keep the block's address in it."""
    out, rva = _self_section(buf, REPLAYFREE_BLOB)
    _branch(out, REPLAYFREE_SITES[0], rva, 5)
    _branch(out, REPLAYFREE_SITES[1], rva + 5, 6)
    return out


def apply_sortpad(buf, build):
    """sortpad.asm in ReplayGallery: the two instructions after the list's
    row update in its browse state become a call into the blob, which
    steps the sort mode on a press of the pad's LB or RB, then makes them.
    The exe's poll slot is the build's; the section is writable, the blob
    keeping what was down."""
    blob = SORTPAD_BLOB.replace(struct.pack('<I', 0xDFDFDFDF), struct.pack('<I', BUILDS[build]['addresses']['PADPOLL']))
    out, rva = _self_section(buf, blob)
    _branch(out, SORTPAD_SITE, rva, 9)
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


# --- dgVoodoo 2 -----------------------------------------------------------
# Not ours and not bundled: fetched from its GitHub release at the user's
# request rather than shipped. Windows' own Direct3D refuses a target over
# 2048 a side (docs/NOTES.md, The size of the target); dgVoodoo 2's does not.
# COM loads the Musashi DLLs with the altered search path, so its ddraw.dll
# goes in MUSASHI\, the D3DImm.dll it loads beside the exe, and the config
# beside the DLL, where it is looked for first. On by default on Windows
# proper, not under Wine or Proton, which have wined3d.

DGVOODOO_RELEASE = 'https://api.github.com/repos/dege-diosg/dgVoodoo2/releases/latest'
DGVOODOO_ASSET = re.compile(r'^dgVoodoo2_[0-9_]+\.zip$')      # the release build, not _dbg or _dev64
DGVOODOO_MAX = 32 << 20
DGVOODOO_FILES = (('ms/x86/ddraw.dll', 'MUSASHI\\ddraw.dll'),   # the archive member, by its tail, and where it goes
                  ('ms/x86/d3dimm.dll', 'D3DImm.dll'),
                  ('dgvoodoo.conf', 'MUSASHI\\dgVoodoo.conf'))
DGVOODOO_STAMP = 'MUSASHI\\dgVoodoo.version'                     # the release installed, and the mark of ours
# The archive's own dgVoodoo.conf, its [DirectX] section changed once,
# when the file is first written: the textures come up white or as noise
# without the fast access, the watermark off, ALT+ENTER left to the game,
# and each frame presented on the display's refresh (docs/NOTES.md, Frame
# timing).
DGVOODOO_SETTINGS = (('FastVideoMemoryAccess', 'true'),
                     ('dgVoodooWatermark', 'false'),
                     ('DisableAltEnterToToggleScreenMode', 'false'),
                     ('ForceVerticalSync', 'true'))
ADDONS = ('dgvoodoo',)


def windows_native():
    """Windows itself, not Wine running the patcher."""
    if sys.platform != 'win32':
        return False
    import ctypes
    try:
        return not hasattr(ctypes.windll.ntdll, 'wine_get_version')
    except (AttributeError, OSError):
        return True


def hide_console():
    """The console Windows opens behind a double-clicked script, hidden.

    Only the one opened for us. A console with another process on it is
    a terminal somebody is working in, and its output is theirs to
    keep. Hidden rather than freed, so stdout stays open and a
    traceback still has somewhere to go."""
    if sys.platform != 'win32':
        return
    import ctypes
    try:
        kernel32 = ctypes.windll.kernel32
        window = kernel32.GetConsoleWindow()
        if not window:
            return                      # pythonw, or no console at all
        listed = (ctypes.c_uint * 2)()
        if kernel32.GetConsoleProcessList(listed, 2) != 1:
            return                      # a terminal, with a shell on it
        ctypes.windll.user32.ShowWindow(window, 0)       # SW_HIDE
    except (AttributeError, OSError, ValueError):
        pass                            # not worth failing to start over


def default_keys():
    return PATCH_KEYS + (ADDONS if windows_native() else ())


def _urlopen(req, timeout=30):
    """urlopen, retried against a bundled CA list: Windows fetches roots on
    demand through CryptoAPI, which OpenSSL never consults, so a root not
    seen before reads as missing. certifi covers that when present."""
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as exc:
        if not isinstance(getattr(exc, 'reason', None), ssl.SSLCertVerificationError):
            raise
        try:
            import certifi
        except ImportError:
            raise exc
        context = ssl.create_default_context(cafile=certifi.where())
    return urllib.request.urlopen(req, timeout=timeout, context=context)


def _fetch(url, limit, accept=None, progress=None):
    req = urllib.request.Request(url, headers={'User-Agent': '%s/%s' % (NAME, VERSION),
                                               'Accept': accept or '*/*'})
    blob = io.BytesIO()
    with _urlopen(req) as resp:
        total = int(resp.headers.get('Content-Length') or 0)
        while True:
            chunk = resp.read(64 << 10)
            if not chunk:
                break
            blob.write(chunk)
            if blob.tell() > limit:
                raise ValueError('%s is larger than %d MB' % (url, limit >> 20))
            if progress:
                progress(blob.tell(), total)
    return blob.getvalue()


def configure_dgvoodoo(text):
    """DGVOODOO_SETTINGS set in the [DirectX] section, the rest of the file
    as it came; a key not found is added at the section's end."""
    lines = text.split('\n')
    want = dict(DGVOODOO_SETTINGS)
    section, end = None, None
    for n, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('['):
            if section == 'directx':
                break
            section = stripped[1:-1].lower()
            if section == 'directx':
                end = n
            continue
        if section != 'directx' or stripped.startswith(';') or '=' not in line:
            continue
        key = line.split('=', 1)[0].strip()
        end = n
        if key in want:
            lines[n] = '%-36s= %s' % (key, want.pop(key))
    if want and end is not None:
        lines[end + 1:end + 1] = ['%-36s= %s' % kv for kv in DGVOODOO_SETTINGS if kv[0] in want]
    return '\n'.join(lines)


def dgvoodoo_status(dest):
    """The release stamped in place, if the files are there too."""
    stamp = os.path.join(dest, *DGVOODOO_STAMP.split('\\'))
    if not os.path.isfile(stamp):
        return None
    for _member, name in DGVOODOO_FILES:
        if not os.path.isfile(os.path.join(dest, *name.split('\\'))):
            return None
    with open(stamp) as fh:
        return fh.read().strip()


UNFETCHED = object()            # install_dgvoodoo's "fetch it yourself"


def fetch_dgvoodoo(dest, log=print, progress=None):
    """The latest release's archive in memory, as (tag, name, bytes), or
    None when the stamp says the DLLs are already there. patch() calls
    this before it writes a byte: a download that fails then leaves the
    game as it was rather than patched without the add-on it was told to
    use."""
    have = dgvoodoo_status(dest)
    if have:
        log('dgvoodoo: %s in place' % have)
        return None
    release = json.loads(_fetch(DGVOODOO_RELEASE, 1 << 20, 'application/vnd.github+json').decode('utf-8'))
    assets = [a for a in release.get('assets', ()) if DGVOODOO_ASSET.match(a.get('name', ''))]
    if len(assets) != 1:
        raise ValueError('dgvoodoo: no release archive in %s' % release.get('html_url', DGVOODOO_RELEASE))
    tag = release.get('tag_name', '?')
    log('dgvoodoo: downloading %s, %s' % (tag, assets[0]['name']))
    return tag, assets[0]['name'], _fetch(assets[0]['browser_download_url'], DGVOODOO_MAX, progress=progress)


def install_dgvoodoo(dest, log=print, progress=None, fetched=UNFETCHED):
    """The DLLs in place from `fetched`, or fetched here when it is not
    given; an existing dgVoodoo.conf is never rewritten."""
    if fetched is UNFETCHED:
        fetched = fetch_dgvoodoo(dest, log, progress)
    if fetched is None:
        return dgvoodoo_status(dest)
    tag, archive, blob = fetched
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = {n.lower().replace('\\', '/'): n for n in zf.namelist()}
        for tail, name in DGVOODOO_FILES:
            found = [n for n in names if n == tail or n.endswith('/' + tail)]
            if len(found) != 1:
                raise ValueError('dgvoodoo: %s not in %s' % (tail, archive))
            out = os.path.join(dest, *name.split('\\'))
            if name.lower().endswith('.conf') and os.path.isfile(out):
                continue                        # someone's settings
            data = zf.read(names[found[0]])
            if name.lower().endswith('.conf'):
                text = data.decode('utf-8', 'replace').replace('\r\n', '\n')
                data = configure_dgvoodoo(text).replace('\n', '\r\n').encode('utf-8')
            with open(out, 'wb') as fh:
                fh.write(data)
            log('dgvoodoo: %s written' % name)
    with open(os.path.join(dest, *DGVOODOO_STAMP.split('\\')), 'w') as fh:
        fh.write(tag + '\n')
    return tag


def remove_dgvoodoo(dest, log=print, everything=False):
    """The DLLs out again, only when the stamp says they are ours, the
    config left; with everything, all of it whether stamped or not, for
    Restore original."""
    stamp = os.path.join(dest, *DGVOODOO_STAMP.split('\\'))
    if not everything and not os.path.isfile(stamp):
        return False
    gone = False
    for _member, name in DGVOODOO_FILES:
        path = os.path.join(dest, *name.split('\\'))
        if (everything or not name.lower().endswith('.conf')) and os.path.isfile(path):
            os.remove(path)
            log('dgvoodoo: %s removed' % name)
            gone = True
    if os.path.isfile(stamp):
        os.remove(stamp)
        gone = True
    return gone


def patch(dest, log=print, keys=None):
    """Write every wanted patch. Each touched file is patched from its
    backup, written on the first run, so patching twice is patching once;
    a file nothing wanted touches goes back to its backup, so patching
    with fewer keys takes the others out. The manifests are written too,
    so an install from before a change to them has it."""
    if keys is None:
        keys = default_keys()
    build = check_build(dest)
    table = patches(build)
    log('patch: %s build' % build_name(build))
    capped = windows_native() and 'dgvoodoo' not in keys
    select_resolutions('capped' if capped else 'full')
    if capped:
        log('patch: resolutions to 2048 a side, for Windows\' own Direct3D; the dgvoodoo add-on lifts that')
    for key, needs in NEEDS:
        if key in keys and key in table and needs not in keys:
            raise ValueError('%s needs %s' % (key, needs))
    if 'netplay' in keys and 'netplay' in table:
        netplay_dll()           # say so now, not half way through
    dgvoodoo = fetch_dgvoodoo(dest, log) if 'dgvoodoo' in keys else None
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
    lobby_art(dest, 'lobby' in keys, log)
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
    write_manifests(dest)
    log('patch: manifests written')
    if 'dgvoodoo' in keys:
        install_dgvoodoo(dest, log, fetched=dgvoodoo)
    elif remove_dgvoodoo(dest, log):
        log('patch: dgVoodoo 2 taken out')


def restore(dest, log=print):
    """The backups back in place, and dgVoodoo 2 out, config and all."""
    found = False
    for name in PATCHED + (TXR,) + tuple(LOBBY_DIR + '\\' + f for f in (LOBBY_BACKDROP,) + LOBBY_FILES):
        path = os.path.join(dest, *name.split('\\'))
        if os.path.isfile(path + '.bak'):
            os.replace(path + '.bak', path)
            log('restore: original %s back in place' % name)
            found = True
    if remove_dgvoodoo(dest, log, everything=True):
        log('restore: dgVoodoo 2 taken out')
        found = True
    if not found:
        raise FileNotFoundError('no backups in %s' % dest)


# What the window needs to describe a disc, a folder or a failure. None
# of it writes anything, so it runs on a pick rather than on a press.

# The play disc's audio: tracks 2 to 14 on every pressing, and the game
# asks for them by number, so a different layout is a different disc.
SR2_AUDIO = tuple(range(2, 15))
MUSIC_SUBDIR = 'music'
WAV_HEADER = 44


class Cancelled(Exception):
    """Raised out of a progress callback to stop a copy or a rip.

    It travels the same path as a real failure, so WavWriter's context
    manager discards the part-written track on the way out."""


def describe(text):
    """Split a description into prose and any 'key<TAB>meaning' rows.

    A blank line starts a paragraph; the breaks stay in the prose so it
    can go into one wrapped label."""
    paragraphs, para, rows = [], [], []
    for line in text.split('\n'):
        if '\t' in line:
            key, _, meaning = line.partition('\t')
            if not key.strip() and rows:
                # A continuation of the row above. The source wraps long
                # meanings to keep its own lines short; the bubble wraps
                # them again at its own width, so join them back up first.
                rows[-1] = (rows[-1][0], rows[-1][1] + ' ' + meaning.strip())
            else:
                rows.append((key.strip(), meaning.strip()))
        elif line.strip():
            para.append(line.strip())
        elif para:
            paragraphs.append(' '.join(para))
            para = []
    if para:
        paragraphs.append(' '.join(para))
    return '\n\n'.join(paragraphs), rows


def why_unwritable(folder, exc, name=None, elsewhere=None):
    """Turn a failed write into advice.

    Windows is checked first, because it folds several different causes
    into EACCES: a write-protected drive, a file another process has
    open, and an actual permission problem all arrive as errno 13, and
    the answer to each is different."""
    elsewhere = elsewhere or ('Copy the game folder somewhere you own - your '
                              'home or Documents - and patch it there.')
    # The caller passes both rather than this guessing from the path:
    # splitting a Windows path on a Linux box gets it wrong, and the
    # sentences need the folder in some cases and the file in others.
    name = name or folder
    win = getattr(exc, 'winerror', None)
    if win == 32 or win == 33:              # SHARING_VIOLATION, LOCK_VIOLATION
        return ('Something else has %s open. Close the game and any launcher '
                'or anti-virus scanning it, then try again.' % name)
    if win == 19:                           # WRITE_PROTECT
        return ('%s is write protected. If the game is on a mounted disc '
                'image, copy it to your hard drive first.' % folder)
    if exc.errno in (errno.EACCES, errno.EPERM):
        # Deliberately not "run as administrator": that writes files the
        # player then cannot delete, and Program Files is the usual cause.
        return 'No permission to write in %s. %s' % (folder, elsewhere)
    if exc.errno == errno.EROFS:
        return ('%s is read-only. If the game is on a mounted disc image, '
                'copy it to your hard drive first.' % folder)
    if exc.errno == errno.ENOSPC:
        return 'No space left on the drive holding %s.' % folder
    if exc.errno == errno.ENOENT:
        return ('%s is gone. Has the folder been moved, or a drive '
                'disconnected, since it was selected?' % folder)
    if exc.errno == errno.ETXTBSY:          # the same thing on Linux
        return '%s is in use. Close the game and try again.' % name
    return 'Cannot write in %s: %s.' % (folder, exc.strerror or exc)


def copy_failure(folder, exc):
    """What to say when a copy or a rip stops part way.

    The destination is checked before either one starts, so anything that
    gets here happened during the write - a disk that filled up, a drive
    pulled out - and reads as a bare OSError otherwise."""
    if isinstance(exc, OSError):
        return why_unwritable(folder, exc)
    return str(exc)


def writable(folder):
    """Can a file actually be created here? Returns (ok, why not).

    A real write, not os.access: on Windows os.access(W_OK) only reports
    the read-only attribute and says nothing about ACLs, so a folder
    under Program Files passes it and then fails on the first file."""
    probe = os.path.join(folder, '.sr2-patcher-write-test')
    try:
        with open(probe, 'wb') as fh:
            fh.write(b'x')
        os.remove(probe)
    except OSError as exc:
        return False, why_unwritable(
            folder, exc, elsewhere='Choose a folder you own - your home, '
                                   'Documents or Games.')
    return True, ''


def room_for(folder, needed, what=''):
    """A message if `folder` cannot take `needed` more bytes, else ''.

    The folder may not exist yet - it is often the one about to be
    created - so the nearest parent that does is what gets asked. No
    answer at all is not the same as a bad one, and gets out of the way."""
    if not needed:
        return ''
    while folder and not os.path.isdir(folder):
        parent = os.path.dirname(folder)
        if parent == folder:
            return ''
        folder = parent
    try:
        free = shutil.disk_usage(folder or '.').free
    except OSError:
        return ''
    if free >= needed:
        return ''
    return ('Not enough room%s: %d MB free, %d MB needed.'
            % (' for ' + what if what else '', free >> 20, needed >> 20))


def dest_problem(path, needed):
    """(message, level) for an install folder, or (None, None).

    Checked before the copy starts: filling a disk and then failing on
    the last file leaves half a game and no clue why."""
    if not path:
        return None, None
    exists = os.path.isdir(path)
    probe = path if exists else os.path.dirname(os.path.abspath(path)) or '.'
    if not os.path.isdir(probe):
        return 'There is no %s to create that folder in.' % probe, 'bad'
    ok, why = writable(probe)
    if not ok:
        return why, 'bad'
    short = room_for(probe, needed)
    if short:
        return short, 'bad'
    if exists and os.path.exists(os.path.join(path, EXE)):
        return ('A game is already installed there. Installing replaces it, '
                'settings and patches included.'), 'warn'
    if exists and os.listdir(path):
        return ('That folder is not empty. Files with the same name are '
                'replaced.'), 'warn'
    return None, None


def music_dir(gamedir):
    return os.path.join(gamedir, MUSIC_SUBDIR)


def music_status(gamedir):
    """One line on the music folder. It names the folder either way:
    where the tracks are going is the thing somebody with the game
    already installed cannot otherwise see."""
    if not gamedir:
        return ''
    out = music_dir(gamedir)
    found = ([f for f in os.listdir(out)
              if re.match(r'track\d+\.wav$', f, re.I)]
             if os.path.isdir(out) else [])
    if not found:
        return 'No tracks yet. They go to %s' % out
    mb = sum(os.path.getsize(os.path.join(out, f)) for f in found) >> 20
    return '%d tracks in %s (%d MB)' % (len(found), out, mb)


def probe_install_disc(src):
    """What is on the install disc, without writing anything: which
    build, how many files an install takes and how big it is, and the
    languages the disc carries.

    Only the exe is decompressed, and only to name the build."""
    fh, close = open_source(src)
    try:
        cab = Cabinet(fh)
        languages = [name for name in LANGUAGES if name in cab.groups]
        groups = install_groups(languages[0] if languages else 'English')
        missing = [g for g in groups if g not in cab.groups]
        if missing:
            raise DiscError('This disc has no %s, so it is not a SEGA RALLY '
                            '2 install disc.' % ', '.join(missing))
        files = [e for g in groups for e in cab.groups[g]]
        # Later groups overwrite earlier ones, so the last one wins - the
        # Pentium III exe over the base one, which is the one installed.
        entry = None
        for e in files:
            if e.path.lower() == EXE.lower():
                entry = e
        build = build_of(hashlib.md5(cab.read(entry)).hexdigest()) if entry else None
        return {'build': build, 'languages': languages,
                'default_language': languages[0] if languages else 'English',
                'count': len(files), 'bytes': sum(e.size for e in files)}
    finally:
        close()


def probe_play_disc(cue):
    """The audio tracks of the play disc and what they rip to."""
    spans = list(audio_spans(parse_cue(cue)))
    return {'tracks': tuple(t['no'] for t, _s, _e in spans),
            'bytes': sum((end - start) * RAW + WAV_HEADER
                         for _t, start, end in spans)}


def installed_build(dest):
    """(build, patched) for a game folder. Raises with the reason a
    folder cannot be patched, which is what the window shows."""
    if not dest or not os.path.isdir(dest):
        raise FileNotFoundError('There is no folder at that path.')
    if not os.path.isfile(os.path.join(dest, EXE)):
        raise FileNotFoundError('No %s in that folder.' % EXE)
    build = check_build(dest)
    patched = any(os.path.isfile(os.path.join(dest, *name.split('\\')) + '.bak')
                  for name in PATCHED)
    return build, patched


def in_background(work, done):
    """Run work() on a thread; done(error, result) fires off the UI
    thread either way, and the window polls a queue for it."""
    def body():
        try:
            result = work()
        except Exception as exc:                # any failure, one path
            done(exc, None)
        else:
            done(None, result)

    thread = threading.Thread(target=body, daemon=True)
    thread.start()
    return thread


# Window
#
# Painted rather than themed: clam with every colour set, from the game's
# own artwork. The layout is two columns of cards where there is room and
# one where there is not, in a canvas that scrolls only when the content
# outgrows the screen.

# Sampled off the box art, the Stratos watercolour and the cabinet: a
# neutral paper white, a neutral near-black, cool greys, the badge's red
# and the deep green of the Lancia's livery. The green is the window
# behind everything, which is the car's own arrangement - white panels
# on green - with the paper ruling the logo off from the rest.
# The band behind the logo is that green cut by a lighter one along a
# stripe in the livery's white and red. None of it does any reading:
# that is left to the greys on the paper, and to the wheels' gold taken
# down far enough to read, for the step numbers.
#
# Four surfaces, each a step apart so they can be told from one another:
# the card is the paper, the band under a heading sits below it, the
# boxes text is typed into are recessed into a card, and the window is
# behind the lot. Every pair that carries meaning is at least 4.5:1,
# every border and tick at least 3:1, and every surface 1.25:1 from the
# one behind it - measured in tools/guitest.py rather than judged by
# eye.
PALETTE = {
    'ink': '#24503a',       # window: the livery's green, the one strong colour
    'trough': '#1c3e2d',    # the scrollbar, which sits on the window
    'sweep': '#327a52',     # the lighter green the banner is cut with
    'frame': '#fafbfb',     # the rule under the logo, the car's own
                            # white
    'field': '#bdc1c8',     # a box text is typed into, and the log
    'card': '#fafbfb',      # panel
    'head': '#dfe2e6',      # section header and status bar
    'line': '#8c929a',      # borders
    'text': '#15171a',
    'dim': '#474c53',       # hints, disabled, the log
    'red': '#ab1c1f',       # the step numbers, a refusal, a bubble title
    'go': '#1f5b3c',        # Apply, ticks, links, prompts
    'go_hi': '#256d48',     # hovered
    'go_lo': '#174630',     # pressed
    'amber': '#7e5d14',     # the step numbers, the key column of a
                            # description, warnings: the wheels' gold
                            # taken down until it reads on paper
    'ok': '#1f5b3c',
    'bad': '#ab1c1f',
}

# The version is in the title because it is the only place somebody who
# double-clicked the script can see it, and it is the first thing worth
# knowing about a bug report.
TITLE = '%s %s' % (LABEL, VERSION)
REPO_URL = 'https://github.com/pairomaniac/sr2-patcher'
LOGO_CREDIT = 'Logo by SirRockEmSockEm'
# How long after the last resize event the static widgets are redrawn, in
# milliseconds. See App._nudge.
NUDGE_MS = 60
# How tall the window opens, in lines of its own text. The screen is
# the other bound, but not a useful one: it is reported as every
# monitor together, so on a desktop with more than one it is not the
# height of anything anybody is looking at. A count of lines is, since
# lines are scaled by whatever the display is. 48 puts the heading of
# the last numbered card on screen, which is as much as needs to be
# showing - the rest is a scroll away. Neither bounds how far the
# window can then be dragged: that is the screen and the content.
LINE_CAP = 48

# Column widths in characters of the hint font, not pixels, so they hold
# at any display scaling. 60-90 characters is the readable range for a
# line of prose.
MIN_CHARS = 68                  # per column; narrower and hints wrap badly
MAX_CHARS = 88                  # wider only makes lines harder to read
GUTTER_CHARS = 2                # between the two columns
ALPHABET = 'abcdefghijklmnopqrstuvwxyz'
# One character of the default font on an unscaled display. Every fixed
# gap in this window was chosen against it, so those numbers stay written
# as the pixel counts they were and are scaled by how far the real font
# has moved.
BASE_EM = 6.8
# The logo across the top of the window, in pixels at 100%. The image is
# drawn at twice this and subsampled below 200%.
LOGO_HEIGHT = 120
# The logo and the window icon, as PNG. Baked in so the script is one
# file; tools/assets.py makes them from the artwork in assets/.
# ASSETS BLOB BEGIN - tools/assets.py
LOGO_PNG = (
    'iVBORw0KGgoAAAANSUhEUgAAAS8AAADwCAMAAABmHxKkAAADAFBMVEXeMSz+/v7+/v4AAAD+'
    '/Pz9/f39/f3+/v7dKSQBAQHcIh3hKSPgNTDsiIXkWFTulpTmYFzqeHT9/Pz56OcXFxfiSUXx'
    'qKb419b2yMfnaWXzt7bvmJUlJSXhQT3Hx8eIiIg2Nja6urq6urrY2NhGRkaYmJj8/Px4eHjx'
    '6OhWVlZnZ2enp6fCwsLsiIX41tX1x8brgX7v7+/Z2dnqeXbxqKZoaGhYWFjztrR2dnbDw8Pq'
    '6uqIiIj64N+VlZXW1tbwoJ7u7u7u7u5GRkanp6e1tbXwoJ7o6OiZmZmmpqbX19f1wL7bHBbo'
    'bmr0urmGhobGxsbrgX70wL/1wL7n5+cAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABs'
    'u0JYAAABAHRSTlP+/goAjk9uLf7+///+//3P/v+p/vv8////+///9/2z0e+xxrHuzcvUru3r'
    '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'
    'OF41LwAAAABJRU5ErkJggg=='
)
ICON_PNG = (
    'iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAMAAABrrFhUAAADAFBMVEXeMSwAAAD+/v7dKiXn'
    'NC/cIx341dTiS0a/Pz/eMCv2ysnkV1P75+f0ubjul5TnaWbsiYbxqKb/AADpdnP/VVXhQT3m'
    'YV30OjjeMCvcMSveMCviMSyqVQDrgX7hMSvdMSviMSziMSzbGxbiMSzVKir1wL7hLivwoJ7i'
    'MSzUMyzeMCuqAAB/AADlKyuqVVXbLSr64N/dLivdLyv/VQDUVSr/f3/fHx/eLyz/Hx8AAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADm'
    'r/PTAAABAHRSTlP+AP///v///wSM//////////8B/wP//wmvMHGvA/9UTzKU/9MQ/zP/cQ/S'
    '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'
)
# ASSETS BLOB END


def scaled(value, em):
    """A gap chosen at 100%, in the pixels it should be now.

    Takes a number or a pack/grid pair and gives back the same shape, so
    a call site keeps reading as the spacing it asks for."""
    if isinstance(value, tuple):
        return tuple(scaled(part, em) for part in value)
    return max(1, int(round(value * em / BASE_EM))) if value else value


# What the window says. Kept together so the wording can be read as a
# whole rather than hunted through the layout.

INSTALL_HINT = ('Copies the game off your disc images into the folder '
                'above. Nothing to mount, and no disc in the drive '
                'afterwards. Skip it if the game is already there.')

INSTALL_TIP = ('Install disc\tDisc 1, as a .cue with its .bin beside it, an '
               '.iso, a folder you have already copied the disc to, or '
               'data1.cab out of one.\n'
               'Play disc\tDisc 2, as a .cue with its .bin files. The music '
               'is on this one, and an .iso will not do - it drops the '
               'audio tracks.\n'
               'Manual\tWhich of the six languages the manual, the readme '
               'and the menus are in. The game itself is the same either '
               'way.\n'
               'Room\tThe game takes about 800 MB in the folder above, and '
               'the soundtrack another 550 MB.')

INSTALL_PICK = 'Pick the install disc to start.'
INSTALL_NEEDS_DEST = 'Choose a game folder above to install it into.'
INSTALL_BUSY = 'Copying\u2026'
INSTALL_CANCELLED = 'Cancelled. The folder holds a part-written copy.'
INSTALL_OK = 'Installed %d files to %s.'
INSTALL_NO_PATH = 'There is nothing at that path.'
# What a good disc looks like, in one line: which build, and how much of
# your disk it is about to take.
INSTALL_FOUND = '%s release. %d files, %d MB.'
# The copy is the same work whichever build is on the disc; only the
# patches need one the patcher has tables for.
INSTALL_FOUND_OTHER = ('Not a release the patcher knows. %d files, %d MB - '
                       'installs, does not patch.')

GAME_HINT = ('Where the game is, or an empty folder to put it in. '
             'Everything below works on this one folder.')
NO_GAME = 'No game folder selected'
# Not a refusal: an empty folder is where an install is about to go, and
# the card below is what fills it.
NO_GAME_YET = 'Nothing installed there yet. Install it below.'
GAME_TO_CREATE = 'That folder does not exist yet. Install game creates it.'
GAME_READY = 'READY - %s release. %d patches selected. Press Apply patches.'
GAME_PATCHED = 'Already patched - %s release. Apply patches writes it again.'
GAME_HELP = ('Only an untouched Pentium III install is accepted - the build '
             'the original installer chose on any modern CPU. A modified or '
             'mixed copy is refused; install afresh from the disc.')

ESSENTIAL_HINT = ('Always applied. Each fixes something that is broken on a '
                  'modern system, and none of them has a trade-off.')
EXTRA_HINT = 'Optional. Untick what you do not want.'

ADDONS_HINT = ('An extra file beside the game rather than an edit to it. '
               'Applied with the patches: tick it and press Apply patches.')

DGVOODOO_LINK = ('dgVoodoo 2', 'dege-diosg/dgVoodoo2',
                 'https://github.com/dege-diosg/dgVoodoo2',
                 'dege\'s DirectDraw on Direct3D 11. Windows\' own '
                 'DirectDraw refuses a picture over 2048 a side and has '
                 'grown slow and erratic with this game on some machines; '
                 'this has neither problem. Apply downloads the latest '
                 'release and puts it beside the game.')
DGVOODOO_WINE = ('Wine and Proton have wined3d, which has no such limit, so '
                 'this is off and not needed there.')
DGVOODOO_CAPPED = ('Without it the resolution list stops at 2048 a side.')

DIAGNOSTICS_HINT = ('Off unless asked for. Each writes a log beside the game '
                    'for a bug report; none of them changes how it plays.')

MUSIC_HINT = ('Rips the play disc to music\\ beside the game, where the '
              'Music from files patch reads it. About 550 MB.')
MUSIC_NEEDS_DEST = 'Choose a game folder above.'
MUSIC_BUSY = 'Track %02d  %d%%'
MUSIC_NO_AUDIO = ('This image has no audio tracks - the music is not in it. '
                  'The play disc is the one with them.')
# The game asks for tracks by number, so a different count is a different
# disc. Said rather than refused: it is their disc and their call.
MUSIC_ODD_AUDIO = ('This image has %d audio tracks; the play disc has %d. '
                   'Ripping it will not give the right music.')

# %d is the number of patches written. The count is the one thing anybody
# can check against what they ticked, and it is what a bug report needs.
DONE = 'Done - %d patches written. Restore original puts the game back.'
FAILED = 'Nothing was written and the game is untouched - see the log below.'
RESTORED = 'Restored. The game is as it was installed.'
BUSY = 'Working\u2026'

ABOUT_NOTE = ('Every patched file is backed up as a .bak beside it, and '
              'patching starts from those, so patching twice is the same '
              'as patching once and Restore original is putting them '
              'back.')


def win_dpi():
    """Ask Windows not to scale our window, and report the real DPI.

    A process that has not declared awareness gets its window rendered at
    96 DPI and bitmap-stretched to whatever the display is set to, which
    softens every border and glyph. This has to happen before the first
    window exists. Returns the DPI so Tk can be told, or None off Windows
    and on releases without the call."""
    if sys.platform != 'win32':
        return None
    import ctypes
    for dll, call, arg in (('shcore', 'SetProcessDpiAwareness', 2),
                           ('user32', 'SetProcessDPIAware', None)):
        try:
            fn = getattr(getattr(ctypes.windll, dll), call)
            fn() if arg is None else fn(arg)
            break
        except (AttributeError, OSError):
            continue
    else:
        return None
    try:
        dc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)      # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, dc)
        return dpi or None
    except (AttributeError, OSError):
        return None


def run_tk():
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import ttk, filedialog

    showing = []

    def close_info(_event=None):
        for bubble in list(showing):
            bubble.hide()

    class Info:
        """Click-to-open description bubble; Tk has no popover."""

        def __init__(self, parent, title, text, app):
            self.app, self.title, self.text, self.win = app, title, text, None
            self.btn = app._static_label(ttk.Label(
                parent, text='\u24d8', style='Card.TLabel',
                foreground=PALETTE['dim'], cursor='question_arrow'))
            self.btn.bind('<Button-1>', self.toggle)
            self.btn.bind('<Enter>', lambda _e: self.btn.config(
                foreground=PALETTE['text']))
            self.btn.bind('<Leave>', lambda _e: self.btn.config(
                foreground=PALETTE['dim']))

        def toggle(self, _event=None):
            was_open = self.win is not None
            close_info()
            if not was_open:
                self.show()
            return 'break'                  # keep close_info from undoing it

        def show(self):
            prose, rows = describe(self.text)
            self.win = win = tk.Toplevel(self.app.root)
            win.wm_overrideredirect(True)
            frame = tk.Frame(win, background=PALETTE['card'], borderwidth=0,
                             highlightbackground=PALETTE['line'],
                             highlightthickness=1)
            frame.pack()
            body = tk.Frame(frame, background=PALETTE['card'])
            body.pack(padx=11, pady=10)     # one margin, the same on all sides
            # One text width for the whole bubble, measured in the font
            # rather than fixed in pixels so it holds at any scaling. Two
            # widths wrap the prose and the table differently and let a
            # long meaning run off the screen.
            em = self.app.small.measure(ALPHABET) / float(len(ALPHABET))
            gap = 12
            keys = max([self.app.bold.measure(key) for key, _ in rows] or [0])
            widest = max([self.app.small.measure(m) for _, m in rows] or [0])
            # Let the table widen the bubble if it only wants a little
            # more: a fixed split leaves one row wrapping on its own among
            # short ones, which reads worse than a slightly wider box.
            wrap = min(int(em * 62), max(int(em * 58), keys + gap + widest))
            self._line(body, self.title, self.app.bold,
                       colour=PALETTE['red']).pack(anchor='w')
            if prose:
                self._line(body, prose, self.app.small, wrap=wrap).pack(
                    anchor='w', pady=(4, 0))
            if rows:
                table = tk.Frame(body, background=PALETTE['card'])
                table.pack(anchor='w', pady=(8, 0))
                for line, (key, meaning) in enumerate(rows):
                    self._line(table, key, self.app.bold,
                               colour=PALETTE['amber']).grid(
                                   row=line, column=0, sticky='nw',
                                   padx=(0, gap), pady=1)
                    self._line(table, meaning, self.app.small,
                               wrap=max(140, wrap - keys - gap)).grid(
                        row=line, column=1, sticky='w', pady=1)
            win.update_idletasks()
            wide, high = win.winfo_reqwidth(), win.winfo_reqheight()
            x = self.btn.winfo_rootx() + self.btn.winfo_width() - wide
            x = max(4, min(x, self.btn.winfo_screenwidth() - wide - 4))
            # Below the button by preference. The tall ones are 350px and
            # more, so from a checkbox low on the screen there is no room
            # below: flip above, and clamp only if neither side fits.
            below = self.btn.winfo_rooty() + self.btn.winfo_height() + 3
            screen = self.btn.winfo_screenheight()
            if below + high > screen - 4:
                above = self.btn.winfo_rooty() - high - 3
                y = above if above >= 4 else max(4, screen - high - 4)
            else:
                y = below
            win.wm_geometry('+%d+%d' % (x, y))
            showing.append(self)

        @staticmethod
        def _line(parent, text, font, wrap=0, colour=None):
            return tk.Label(parent, text=text, background=PALETTE['card'],
                            fg=colour or PALETTE['text'], font=font,
                            justify='left', wraplength=wrap)

        def hide(self):
            if self.win:
                self.win.destroy()
                self.win = None
            if self in showing:
                showing.remove(self)

    def _blend(a, b, t):
        a, b = int(a[1:], 16), int(b[1:], 16)
        return '#%02x%02x%02x' % tuple(
            round(((a >> shift) & 255) * (1 - t) + ((b >> shift) & 255) * t)
            for shift in (16, 8, 0))

    TICK = (((4.0, 8.0), (6.6, 10.8)), ((6.6, 10.8), (11.6, 4.8)))

    def _rounded(width_px, height_px, back, fill, edge, tick=None,
                 radius=4.0, line=1.4, corners='nw ne sw se', scale=1.0):
        """A rounded rectangle, which is how the checkboxes are drawn. It
        works by coverage rather than by pixels, each point blending by
        its distance to the shape's edge, because Tk has no drawing API
        past put() and its -subsample does not average.

        clam has no border radius and its checkbox is a flat square with
        two settable colours, so anything rounded has to be an image."""
        def cover(distance):
            return min(1.0, max(0.0, 0.5 - distance))

        img = tk.PhotoImage(width=width_px, height=height_px)
        cx, cy = (width_px - 1) / 2.0, (height_px - 1) / 2.0
        hw, hh = width_px / 2.0 - 0.5, height_px / 2.0 - 0.5
        rows = []
        for y in range(height_px):
            row = []
            for x in range(width_px):
                vert = 'n' if y < cy else 's'
                horz = 'w' if x < cx else 'e'
                r = radius if vert + horz in corners else 0.0
                dx = abs(x - cx) - (hw - r)
                dy = abs(y - cy) - (hh - r)
                # distance to the edge: the corner arc where both axes are
                # past it, the nearer side otherwise. Taking only the first
                # term leaves every square corner at zero, which paints
                # that whole quadrant a half blend instead of the fill.
                edge_d = ((max(dx, 0.0) ** 2 + max(dy, 0.0) ** 2) ** 0.5
                          + min(max(dx, dy), 0.0) - r)
                px = _blend(back, edge, cover(edge_d))
                px = _blend(px, fill, cover(edge_d + line))
                for (x0, y0), (x1, y1) in (
                        [[(a * scale, b * scale) for a, b in seg]
                         for seg in TICK] if tick else ()):
                    vx, vy = x1 - x0, y1 - y0
                    along = max(0.0, min(1.0, ((x - x0) * vx + (y - y0) * vy)
                                         / (vx * vx + vy * vy)))
                    ex, ey = x - x0 - vx * along, y - y0 - vy * along
                    px = _blend(px, tick,
                                cover((ex * ex + ey * ey) ** 0.5
                                      - 1.1 * scale))
                row.append(px)
            rows.append('{%s}' % ' '.join(row))
        img.put(' '.join(rows))
        return img

    def _em(font):
        """The width of one character of a font, which everything laid out
        in pixels is measured against."""
        return max(1.0, font.measure(ALPHABET) / len(ALPHABET))

    def _hint(parent, text, colour, font, pady=0, gutter=0):
        """The quiet explanatory line under a section heading; most of the
        cards have one and they only differ in their text.

        The width is taken from a holder frame rather than the card body.
        A ttk frame's winfo_width() counts its own padding, so wrapping to
        that made every hint wider than the space it had and clipped the
        last word against the card edge. An empty frame filled to the
        content area measures it exactly.

        Packs itself, because the holder is nobody else's business."""
        em = _em(font)
        holder = ttk.Frame(parent, style='Card.TFrame')
        holder.pack(fill='x', pady=scaled(pady, em))
        label = ttk.Label(holder, text=text, style='Card.TLabel',
                          foreground=colour, font=font, justify='left')

        def fit(_event=None):
            # Written on every event: setting wraplength is also what
            # marks the label for redraw. Skip it and an unpainted label
            # stays blank.
            width = holder.winfo_width()
            if width > 1:
                edge = gutter() if callable(gutter) else gutter
                label.configure(wraplength=min(
                    int(MAX_CHARS * em),
                    max(int(20 * em), width - 2 - edge)))
        holder.bind('<Configure>', fit, add='+')
        label.bind('<Map>', fit, add='+')       # a collapsed card gets no
        #                                         Configure until it reopens
        label.pack(anchor='w')
        return label

    def _gap(image, extra, colour):
        """Widen an image with blank space on its right. A layout cannot
        carry padding on an element, so the gap between a checkbox and its
        label has to be part of the picture."""
        wide = tk.PhotoImage(width=image.width() + extra,
                             height=image.height())
        wide.put(colour, to=(0, 0, wide.width(), wide.height()))
        wide.tk.call(wide, 'copy', image, '-to', 0, 0)
        return wide

    class App:

        def __init__(self, root):
            self.root = root
            self.vars, self.checks = {}, {}
            self.diagnostics = {}
            self._bodies = []
            self._openers = {}
            self._worker = None
            self._busy = None               # 'install', 'music', 'patch'
            self._cancel = False
            self._disc_after = self._game_after = None
            self._status_text, self._status_font = NO_GAME, None
            # Widgets whose text is written once and never touched again;
            # the ones left blank after a resize, see _nudge.
            self._static, self._nudge_after = [], None
            self._nudge_at = 0.0
            self._cut_after, self._cut_at = None, 0.0
            self._settle_tries = 0
            self._settle_rounds = 0
            root.title(TITLE)
            root.minsize(430, 0)
            root.maxsize(root.winfo_screenwidth(), root.winfo_screenheight())

            root.bind_all('<Button-1>', close_info, add='+')
            root.bind_all('<Escape>', close_info, add='+')
            root.protocol('WM_DELETE_WINDOW', self._close)

            self._styles()
            self._icon(root)

            outer = ttk.Frame(root, style='Ink.TFrame')
            outer.pack(fill='both', expand=True)
            self._statusbar(outer)                  # pinned before the body
            self._logo_h = self._logo(outer)        # fixed above it
            left, right, band, foot_left, foot_right = self._body(outer)

            # In the order the work is done: the folder first, because
            # everything else is done to it - the install writes into it,
            # the rip beside it, the patches inside it. Two columns where
            # there is room - getting the game in place is one job,
            # patching it another; on a narrow screen _body gives back
            # the same frame five times and it stacks.
            self._section(left, '1  GAME FOLDER', self._game_body)
            self._section(left, '2  INSTALL', self._install_body)
            self._section(right, '3  ESSENTIAL PATCHES',
                          lambda p: self._feature_body(p, ESSENTIAL,
                                                       ESSENTIAL_HINT))
            self._section(right, '4  EXTRA PATCHES',
                          lambda p: self._feature_body(p, EXTRA, EXTRA_HINT))
            self._section(band, '5  ADD-ONS', self._addons_body)
            self._section(band, 'DIAGNOSTICS', self._diagnostics_body,
                          expanded=False)
            # Side by side at the foot, on the same split as the columns
            # above, so the two headings line up whatever is open.
            self._section(foot_left, 'LOG', self._log_body, expanded=False)
            self._section(foot_right, 'ABOUT', self._about_body,
                          expanded=False)

            # The last card in each column stretches to the bottom of it.
            # The columns are as tall as the taller one, so without this
            # the shorter column stops early and its last card's lower
            # edge sits opposite nothing.
            for column in (left, right, foot_left, foot_right):
                cards = column.winfo_children()
                if cards and column is not self.inner:
                    last = cards[-1]
                    last.fills = True
                    if last.winfo_children()[-1].winfo_manager():
                        last.pack_configure(fill='both', expand=True)

            # Set the width before measuring. Unconstrained, a paragraph
            # asks for its longest line unwrapped, and the window's
            # minimum came out as wide as the longest sentence in it.
            wide = self.min_content * self.columns \
                + (self.gutter if self.columns > 1 else 0)
            self.canvas.itemconfigure(self.window, width=wide)
            root.update_idletasks()

            # Every section open, which is as tall as the window may be
            # dragged and no taller.
            for body, shown in self._bodies:
                if not shown:
                    body.pack(fill='x')
            root.update_idletasks()
            full = self.inner.winfo_reqheight()
            wide = max(wide, self.inner.winfo_reqwidth())
            for body, shown in self._bodies:
                if not shown:
                    body.pack_forget()
            # A starting height only. The hints wrap on a Configure,
            # which is a real event rather than an idle task, so before
            # the window is on screen a paragraph still counts the lines
            # it had at some other width - _settle_height takes the
            # measurement again once that has happened.
            root.update_idletasks()
            natural = self.inner.winfo_reqheight()
            self.canvas.configure(width=wide, height=min(natural, self.cap))
            # the minimum has to leave room for the scrollbar as well
            bar = self.vbar.winfo_reqwidth()
            root.minsize(wide + bar, self.px(320))
            # And a maximum, so that maximising lands on the largest size
            # that is any use rather than on the size of the screen.
            root.update_idletasks()
            chrome = root.winfo_reqheight() - min(natural, self.cap)
            root.maxsize(
                min(root.winfo_screenwidth() - self.px(40),
                    max(wide + int(8 * self.em),
                        self.max_content * self.columns
                        + (self.gutter if self.columns > 1 else 0)) + bar),
                min(root.winfo_screenheight() - self.px(60),
                    full + chrome))
            self._fit()
            self._sync_buttons()
            root.after_idle(self._settle_height)
            # Everything above is a starting size. What the window can
            # really have is only known once it is on screen, which
            # _settle_height sees to.

        def _settle_height(self):
            """Give the body the height it should open at, once the
            window is on screen.

            Everything measured before that is a guess: a widget that
            has never been mapped reports what it would like rather than
            what it needs, and what the banner and the status bar cost
            around the body cannot be known at all.

            Runs for the first half second and then stops. It has to
            stop: a window that answers every resize with a size of its
            own cannot be dragged anywhere."""
            # Measured again rather than trusted from build time. A line
            # was 15 pixels and the screen 931 on a desktop that a
            # moment later said 22 and 2160, and the window had already
            # sized itself against the first of those.
            self.row = self.small.metrics('linespace')
            high, seen = self.root.winfo_height(), self.canvas.winfo_height()
            if high <= 1 or seen <= 1:
                # Not on screen yet; ask again shortly. The count is
                # there so a window that never appears stops asking.
                if self._settle_tries < 40:
                    self._settle_tries += 1
                    self.root.after(25, self._settle_height)
                return
            chrome = max(high - seen, 0)
            self.cap = min(
                max(self.px(360),
                    self.root.winfo_screenheight() - self.px(150) - chrome),
                self.row * LINE_CAP)
            want = min(self.inner.winfo_reqheight(), self.cap)
            if abs(seen - want) > 2:
                self.canvas.configure(height=want)
                # And say it as a window size too, rather than leaving it
                # to propagate out of the canvas: a mapped toplevel is
                # the window manager's, and not all of them take a late
                # request from a widget inside it.
                self.root.geometry('%dx%d' % (self.root.winfo_width(),
                                              want + chrome))
                self._fit()
            # Once is not enough. The height a paragraph needs depends on
            # the width it wraps at, the width depends on the scrollbar,
            # and the scrollbar depends on the height - and the hints are
            # rewritten on a timer after a resize besides. So this runs
            # for the first half second and then stops, because a window
            # that keeps answering with a size of its own cannot be
            # dragged anywhere.
            if self._settle_rounds < 8:
                self._settle_rounds += 1
                self.root.after(60, self._settle_height)

        def _body(self, parent):
            """Size to the content, scrolling only if it outgrows the
            screen.

            Returns the two columns, the full-width band under them, and
            the two half-width feet under that. With one column they are
            all the same frame and the sections simply stack."""
            holder = ttk.Frame(parent, style='Ink.TFrame')
            holder.pack(fill='both', expand=True)
            self.canvas = tk.Canvas(holder, highlightthickness=0,
                                    borderwidth=0,
                                    background=PALETTE['ink'])
            self.vbar = ttk.Scrollbar(holder, orient='vertical',
                                      style='Sr2.Vertical.TScrollbar',
                                      command=self.canvas.yview)
            # The bar is packed first so pack reserves its width. The
            # other way round the canvas expands into the whole row and
            # the bar is squeezed off the edge at the minimum width.
            self.vbar.pack(side='right', fill='y')
            self.canvas.pack(side='left', fill='both', expand=True)
            self.canvas.configure(yscrollcommand=self.vbar.set)

            self.inner = ttk.Frame(self.canvas, padding=self.px(12),
                                   style='Ink.TFrame')
            self.window = self.canvas.create_window((0, 0), window=self.inner,
                                                    anchor='nw')
            # How tall the window may grow before the content scrolls
            # instead. Settled properly in _settle_height; this is only
            # a floor to build against.
            self.row = self.small.metrics('linespace')
            self.cap = min(max(self.px(360),
                               parent.winfo_screenheight() - self.px(150)
                               - self._logo_h),
                           self.row * LINE_CAP)
            self.inner.bind('<Configure>', self._fit)
            self.canvas.bind('<Configure>', self._fit)
            self.canvas.bind('<Configure>', self._nudge, add='+')
            for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                self.canvas.bind_all(seq, self._wheel)

            # Two columns need both of them at the readable width plus the
            # padding, the gutter and the scrollbar. Below that, one
            # column and the sections stack - a squeezed pair wraps every
            # hint to three lines and reads worse than scrolling.
            self.columns = 2 if (parent.winfo_screenwidth() - 80
                                 >= 2 * self.min_content + self.gutter
                                 + int(6 * self.em)) else 1
            if self.columns == 1:
                self.left = self.right = self.band = self.inner
                self.foot_left = self.foot_right = self.inner
                return (self.inner,) * 5
            self.inner.columnconfigure(0, weight=1, uniform='col')
            self.inner.columnconfigure(1, weight=1, uniform='col')
            self.left = ttk.Frame(self.inner, style='Ink.TFrame')
            self.left.grid(row=0, column=0, sticky='nsew',
                           padx=(0, self.gutter // 2))
            self.right = ttk.Frame(self.inner, style='Ink.TFrame')
            self.right.grid(row=0, column=1, sticky='nsew',
                            padx=(self.gutter // 2, 0))
            self.band = ttk.Frame(self.inner, style='Ink.TFrame')
            self.band.grid(row=1, column=0, columnspan=2, sticky='ew')
            self.foot_left = ttk.Frame(self.inner, style='Ink.TFrame')
            self.foot_left.grid(row=2, column=0, sticky='nsew',
                                padx=(0, self.gutter // 2))
            self.foot_right = ttk.Frame(self.inner, style='Ink.TFrame')
            self.foot_right.grid(row=2, column=1, sticky='nsew',
                                 padx=(self.gutter // 2, 0))
            return (self.left, self.right, self.band,
                    self.foot_left, self.foot_right)

        def _fit(self, _event=None):
            """Answer a resize, in the event that caused it, doing the
            same work every time. Tk repaints as part of handling the
            event, and these calls are what mark the canvas and its window
            item as needing it."""
            need = self.inner.winfo_reqheight()
            wide = self.canvas.winfo_width()
            if wide > 1:
                self.canvas.itemconfigure(self.window, width=wide)
            # Only the scroll extent. Height is settled at startup and
            # left alone: driving it from here resizes the window on every
            # expand and collapse.
            self.canvas.configure(
                scrollregion=(0, 0, self.inner.winfo_reqwidth(), need))
            # The bar stays packed whether it is needed or not. Showing
            # and hiding it moves the window by its own width the moment
            # the content outgrows the cap.
            if need <= max(self.canvas.winfo_height(), 1) + 1:
                self.canvas.yview_moveto(0)

        def _wheel(self, event):
            # bind_all reaches every toplevel, so an open description
            # bubble would otherwise scroll the window behind it.
            if event.widget.winfo_toplevel() is not self.root:
                return
            # The log scrolls itself, and so does its scrollbar. Tk widget
            # names are paths, so one prefix covers the pair.
            log = getattr(self, 'log_wrap', None)
            if log is not None and str(event.widget).startswith(str(log)):
                return
            if self.inner.winfo_reqheight() <= self.canvas.winfo_height():
                return
            step = -1 if getattr(event, 'num', 0) == 4 or \
                getattr(event, 'delta', 0) > 0 else 1
            self.canvas.yview_scroll(step, 'units')

        # -- look

        def _styles(self):
            """Theme the widgets. clam is the only stock theme where every
            colour can be set.

            These must all stay *named* styles. Setting the root '.' style
            also repaints Tk's file dialog, whose file list is a canvas
            iconlist.tcl hardcodes to white."""
            p = PALETTE
            style = ttk.Style()
            if 'clam' in style.theme_names():
                style.theme_use('clam')
            self.root.configure(background=p['ink'])
            # clam draws its border two pixels wide and bevels it with
            # lightcolor and darkcolor. One flat pixel of 'line' instead:
            # a box is told from the card by its own fill, so the border
            # is only there to close the shape.
            edges = dict(bordercolor=p['line'], darkcolor=p['line'],
                         lightcolor=p['line'], troughcolor=p['card'],
                         borderwidth=1)
            style.configure('Ink.TFrame', background=p['ink'])
            style.configure('Card.TFrame', background=p['card'])
            style.configure('Card.TLabel', background=p['card'],
                            foreground=p['text'])
            style.configure('Dim.TLabel', background=p['card'],
                            foreground=p['dim'])
            style.configure('Link.TLabel', background=p['card'],
                            foreground=p['go'])
            style.configure('Head.TFrame', background=p['head'])
            style.configure('Head.TLabel', background=p['head'],
                            foreground=p['text'])
            style.configure('Bar.TFrame', background=p['head'])
            style.configure('Bar.TLabel', background=p['head'],
                            foreground=p['dim'])

            style.configure('Card.TCheckbutton', background=p['card'],
                            foreground=p['text'], focuscolor=p['dim'],
                            indicatorbackground=p['field'],
                            indicatorforeground=p['field'], **edges)
            style.map(
                'Card.TCheckbutton',
                background=[('active', p['card'])],
                foreground=[('disabled', p['dim'])],
                # ttk takes the first spec that matches, so the disabled
                # pairs go first or a disabled tick paints itself bright.
                indicatorbackground=[('disabled', 'selected', p['line']),
                                     ('disabled', p['field']),
                                     ('selected', p['go']),
                                     ('!selected', p['field'])],
                indicatorforeground=[('disabled', 'selected', p['dim']),
                                     ('selected', p['field'])])

            style.configure('Sr2.TButton', background=p['head'],
                            foreground=p['text'], focuscolor=p['dim'],
                            **edges)
            style.map('Sr2.TButton',
                      background=[('pressed', p['field']),
                                  ('active', p['field']),
                                  ('disabled', p['card'])],
                      foreground=[('disabled', p['dim'])])
            style.configure('Go.TButton', background=p['go'],
                            foreground=p['card'], focuscolor=p['card'],
                            **edges)
            style.map('Go.TButton',
                      background=[('pressed', p['go_lo']),
                                  ('active', p['go_hi']),
                                  ('disabled', p['card'])],
                      foreground=[('pressed', p['card']),
                                  ('active', p['card']),
                                  ('disabled', p['dim'])])

            style.configure('Sr2.TEntry', fieldbackground=p['field'],
                            foreground=p['text'], insertcolor=p['go'],
                            **edges)
            style.map('Sr2.TEntry',
                      fieldbackground=[('readonly', p['field'])],
                      foreground=[('readonly', p['dim'])])
            style.configure('Sr2.TCombobox', fieldbackground=p['field'],
                            background=p['head'], foreground=p['text'],
                            arrowcolor=p['dim'], **edges)
            style.map('Sr2.TCombobox',
                      fieldbackground=[('readonly', p['field'])],
                      foreground=[('readonly', p['text'])],
                      selectbackground=[('readonly', p['field'])],
                      selectforeground=[('readonly', p['text'])])
            # The dropdown is a plain Tk listbox that ttk does not theme,
            # so its colours have to be set through the option database.
            for option, colour in (('background', p['field']),
                                   ('foreground', p['text']),
                                   ('selectBackground', p['go']),
                                   ('selectForeground', p['field'])):
                self.root.option_add('*TCombobox*Listbox.%s' % option, colour)
            # The scrollbar is the one widget that sits on the window
            # rather than on a card, so its trough follows the window and
            # not the paper: a light trough against the green read as a
            # strip of something else down the edge.
            style.configure('Sr2.Vertical.TScrollbar', background=p['head'],
                            arrowcolor=p['dim'],
                            **dict(edges, troughcolor=p['trough']))
            style.map('Sr2.Vertical.TScrollbar',
                      background=[('active', p['card'])])

            default = tkfont.nametofont('TkDefaultFont')
            small = max(7, abs(default.cget('size')) - 1)
            self.head_font = default.copy()
            self.head_font.configure(size=small, weight='bold')
            self.small = default.copy()
            self.small.configure(size=small)
            self.bold = default.copy()
            self.bold.configure(weight='bold')
            self.mono = tkfont.nametofont('TkFixedFont').copy()
            self.mono.configure(size=small)
            self.dim = p['dim']

            self.em = _em(self.small)
            self.min_content = int(MIN_CHARS * self.em)
            self.max_content = int(MAX_CHARS * self.em)
            self.gutter = max(2, int(GUTTER_CHARS * self.em))

            # Drawn last, because the tick box is sized against the text it
            # sits beside: a fixed 16px box next to 27px letters at 200%
            # looked like a mistake.
            self._draw_indicator(style, p)

        def px(self, value):
            """A gap written as pixels at 100%, in this display's pixels."""
            return scaled(value, self.em)

        def _draw_indicator(self, style, p):
            """Swap clam's indicator for drawn images. Keep the
            references: Tk does not own them, and a collected image leaves
            a blank box."""
            side = max(16, int(round(self.em * 2.4)))
            scale = side / 16.0
            gap = max(6, int(round(self.em)))
            try:
                self._boxes = tuple(
                    _gap(box, gap, p['card']) for box in (
                        _rounded(side, side, p['card'], p['field'],
                                 p['line'],
                                 radius=4.0 * scale, line=1.4 * scale),
                        _rounded(side, side, p['card'], p['go'], p['go'],
                                 tick=p['field'], radius=4.0 * scale,
                                 line=1.4 * scale, scale=scale),
                        _rounded(side, side, p['card'], p['field'],
                                 p['card'],
                                 radius=4.0 * scale, line=1.4 * scale),
                        _rounded(side, side, p['card'], p['line'], p['line'],
                                 tick=p['dim'], radius=4.0 * scale,
                                 line=1.4 * scale, scale=scale)))
                off, on, off_off, on_off = self._boxes
                style.element_create(
                    'Sr2.indicator', 'image', off,
                    ('disabled', 'selected', on_off),
                    ('disabled', off_off),
                    ('selected', on), sticky='')
                style.layout('Card.TCheckbutton', [
                    ('Checkbutton.padding', {'sticky': 'nswe', 'children': [
                        ('Sr2.indicator', {'side': 'left', 'sticky': ''}),
                        ('Checkbutton.focus', {
                            'side': 'left', 'sticky': 'w', 'children': [
                                ('Checkbutton.label',
                                 {'sticky': 'nswe'})]})]})])
                style.configure('Card.TCheckbutton',
                                padding=self.px((0, 3, 0, 3)))
            except tk.TclError:
                pass            # keep clam's square rather than no box at all

        def _section(self, parent, title, build, expanded=True):
            card = ttk.Frame(parent, style='Card.TFrame')
            card.pack(fill='x', pady=self.px((0, 8)))

            head = ttk.Frame(card, style='Head.TFrame',
                             padding=self.px((10, 6)))
            head.pack(fill='x')
            arrow = self._static_label(ttk.Label(
                head, style='Head.TLabel',
                text='\u25be' if expanded else '\u25b8'))
            arrow.pack(side='left', padx=self.px((0, 8)))
            # The step number is set apart from the name, in the gold
            # the description tables already use for a key. It is the one
            # thing in the heading that is a sequence rather than a label.
            number, _, rest = title.partition('  ')
            labels = [arrow]
            if rest:
                step = self._static_label(ttk.Label(
                    head, text=number, style='Head.TLabel',
                    foreground=PALETTE['amber'], font=self.head_font))
                step.pack(side='left', padx=self.px((0, 8)))
                labels.append(step)
            else:
                rest = number
            name = self._static_label(ttk.Label(
                head, text=rest, style='Head.TLabel', font=self.head_font))
            name.pack(side='left')
            labels.append(name)

            inner = ttk.Frame(card, style='Card.TFrame',
                              padding=self.px((12, 8, 10, 10)))
            self._bodies.append((inner, expanded))
            if expanded:
                inner.pack(fill='x')
            build(inner)

            def set_open(flag):
                # Drives the widget rather than trusting a flag: the sizing
                # pass hides bodies by their starting state, so anything
                # that opened one before that ran would be left marked open
                # and packed away.
                arrow.config(text='\u25be' if flag else '\u25b8')
                if flag:
                    inner.pack(fill='x')
                else:
                    inner.pack_forget()
                # The last card in a column takes up the slack so the two
                # sides end level - but only while it has something in it.
                if getattr(card, 'fills', False):
                    card.pack_configure(fill='both' if flag else 'x',
                                        expand=flag)

            def toggle(_event=None):
                set_open(not inner.winfo_manager())

            for widget in [head] + labels:
                widget.bind('<Button-1>', toggle)

            self._openers[title] = lambda: set_open(True)
            return inner

        def _field(self, grid, line, label, var, browse):
            """One labelled path row. They share a grid so the entries line
            up rather than each starting after its own word."""
            self._static_label(ttk.Label(
                grid, text=label, style='Card.TLabel', font=self.small,
                width=12, anchor='w')).grid(row=line, column=0, sticky='w',
                                            padx=(0, 8), pady=(0, 5))
            # width=12 on purpose: it expands into whatever the row has
            # spare, and a larger request only widens the window.
            entry = ttk.Entry(grid, textvariable=var, style='Sr2.TEntry',
                              width=12)
            entry.grid(row=line, column=1, sticky='ew', pady=(0, 5))
            ttk.Button(grid, text='Browse\u2026', style='Sr2.TButton',
                       command=browse).grid(row=line, column=2, sticky='w',
                                            padx=(8, 0), pady=(0, 5))
            return entry

        # -- 2 INSTALL

        def _install_body(self, parent):
            """Both discs in; the folder above is where they go.

            The play disc sits here rather than in a card of its own: it
            is the same job - getting the game onto the disk - and asking
            for it later is how people end up with no music."""
            _hint(parent, INSTALL_HINT, self.dim, self.small, pady=(0, 6))

            grid = ttk.Frame(parent, style='Card.TFrame')
            grid.pack(fill='x')
            grid.columnconfigure(1, weight=1)

            self.disc_var = tk.StringVar()
            self._field(grid, 0, 'Install disc', self.disc_var,
                        self._pick_disc)
            Info(grid, 'INSTALL', INSTALL_TIP, self).btn.grid(
                row=0, column=3, sticky='e', padx=(6, 2))
            self.play_var = tk.StringVar()
            self._field(grid, 1, 'Play disc', self.play_var, self._pick_play)

            # Only shown once a disc has been read and offers a choice.
            self.lang_row = ttk.Frame(grid, style='Card.TFrame')
            # The note absorbs the slack, not the box: with the weight on
            # column 1 the row overflowed and the combobox was squeezed.
            self.lang_row.columnconfigure(2, weight=1)
            self._static_label(ttk.Label(
                self.lang_row, text='Manual', style='Card.TLabel',
                font=self.small, width=12, anchor='w')).grid(
                    row=0, column=0, sticky='w', padx=(0, 8))
            self.lang_var = tk.StringVar(value=LANGUAGES[0])
            self.lang_box = ttk.Combobox(self.lang_row, state='readonly',
                                         style='Sr2.TCombobox', width=14,
                                         textvariable=self.lang_var)
            self.lang_box.grid(row=0, column=1, sticky='w')

            self.disc_note = _hint(parent, INSTALL_PICK, PALETTE['go'],
                                   self.small, pady=(8, 0))
            self.dest_note = _hint(parent, '', self.dim, self.small,
                                   pady=(4, 0))

            buttons = ttk.Frame(parent, style='Card.TFrame')
            buttons.pack(fill='x', pady=(10, 0))
            self.install_btn = ttk.Button(buttons, text='Install game',
                                          style='Sr2.TButton',
                                          state='disabled',
                                          command=self._install)
            self.install_btn.pack(side='left')
            self.rip_btn = ttk.Button(buttons, text='Rip soundtrack',
                                      style='Sr2.TButton', state='disabled',
                                      command=self._rip)
            self.rip_btn.pack(side='left', padx=(8, 0))

            _hint(parent, MUSIC_HINT, self.dim, self.small, pady=(8, 0))
            self.music_note = _hint(parent, '', self.dim, self.small,
                                    pady=(4, 0))
            self.disc_ok = False
            self.rip_ok = False
            self._audio_warning = ''
            self._disc_bytes = self._rip_bytes = 0
            # Typing a path counts as picking one. Reading a disc opens
            # files, so it waits for a pause rather than running on every
            # keystroke.
            self.disc_var.trace_add('write', lambda *_a: self._later(
                '_disc_after', lambda: self._check_disc(self.disc_var.get())))
            self.play_var.trace_add('write', lambda *_a: self._later(
                '_disc_after', lambda: self._check_play(self.play_var.get())))

        def _later(self, slot, call, delay=400):
            """Run call once the typing has stopped."""
            pending = getattr(self, slot)
            if pending:
                self.root.after_cancel(pending)
            setattr(self, slot, self.root.after(delay, call))

        def _pick_disc(self):
            path = filedialog.askopenfilename(
                title='Select the install disc image',
                filetypes=[('Disc image', '*.cue *.iso *.bin *.CUE *.ISO'),
                           ('Cabinet', 'data1.cab'), ('All files', '*')])
            if path:
                self.disc_var.set(path)       # the trace runs the check

        def _pick_play(self):
            path = filedialog.askopenfilename(
                title='Select the play disc cue sheet',
                filetypes=[('Cue sheet', '*.cue *.CUE'), ('All files', '*')])
            if path:
                self.play_var.set(path)

        def _check_disc(self, source):
            """Read the disc and say what is on it, or what is wrong.

            Only the cabinet's index and the exe are read - a second or so
            - so it runs the moment a source is picked and the buttons
            below light up or do not."""
            self.disc_ok = False
            self._disc_bytes = 0
            self.lang_row.grid_forget()
            source = (source or '').strip()
            if not source:
                self._disc_note(INSTALL_PICK, PALETTE['go'])
            elif not os.path.exists(source):
                self._disc_note(INSTALL_NO_PATH, PALETTE['bad'])
            else:
                try:
                    info = probe_install_disc(source)
                except (DiscError, OSError, ValueError, struct.error) as exc:
                    self._disc_note(str(exc), PALETTE['bad'])
                else:
                    self._describe_disc(info)
            self._sync_buttons()

        def _describe_disc(self, info):
            self.disc_ok = True
            self._disc_bytes = info['bytes']
            if len(info['languages']) > 1:
                self.lang_box.config(values=info['languages'])
                if self.lang_var.get() not in info['languages']:
                    self.lang_var.set(info['default_language'])
                self.lang_row.grid(row=2, column=0, columnspan=3,
                                   sticky='ew', pady=(0, 6))
            if info['build']:
                self._disc_note(INSTALL_FOUND % (build_name(info['build']), info['count'],
                                                 info['bytes'] >> 20),
                                PALETTE['ok'])
                self._log('disc: %s release, %d files, %d MB'
                          % (build_name(info['build']), info['count'],
                             info['bytes'] >> 20))
            else:
                # Copying is the same work whichever build is on the disc,
                # so it runs; only the patches need one with tables.
                self._disc_note(INSTALL_FOUND_OTHER % (info['count'],
                                                       info['bytes'] >> 20),
                                PALETTE['amber'])
                self._log('disc: %s is not a build the patcher knows' % EXE)

        def _check_play(self, source):
            """The play disc, which the ripper reads and nothing else."""
            self.rip_ok = False
            self._audio_warning = ''
            self._rip_bytes = 0
            source = (source or '').strip()
            if source:
                try:
                    info = probe_play_disc(source)
                except (DiscError, OSError, ValueError) as exc:
                    self._audio_warning = str(exc)
                else:
                    self.rip_ok = bool(info['tracks'])
                    self._rip_bytes = info['bytes']
                    if not info['tracks']:
                        self._audio_warning = MUSIC_NO_AUDIO
                    elif tuple(info['tracks']) != SR2_AUDIO:
                        self._audio_warning = MUSIC_ODD_AUDIO % (
                            len(info['tracks']), len(SR2_AUDIO))
                    else:
                        self._log('play disc: %d tracks, %d MB'
                                  % (len(info['tracks']),
                                     info['bytes'] >> 20))
            self._sync_buttons()

        def _disc_note(self, text, colour):
            self.disc_note.config(text=text, foreground=colour)

        def _target(self):
            """The one folder: what the install writes, what the rip goes
            beside, and what the patches are applied to."""
            return self.game_var.get().strip()

        def _sync_buttons(self, *_args):
            """One place decides what is clickable, because three things
            feed it: both discs and the folder."""
            path = self._target()
            # What is wrong with the folder as somewhere to install, asked
            # only while there is a disc to install from: with no disc,
            # "that folder is not empty" is a complaint about a game that
            # is already there and working.
            if self.disc_ok and path:
                why, level = dest_problem(path, self._disc_bytes)
            elif self.disc_ok:
                why, level = INSTALL_NEEDS_DEST, 'warn'
            else:
                why, level = None, None
            self.dest_note.config(
                text=why or '',
                foreground=PALETTE['bad'] if level == 'bad'
                else PALETTE['amber'] if level == 'warn' else self.dim)

            # In order of importance: no room stops the rip, the wrong
            # tracks are a reason not to press the button, otherwise say
            # where they go.
            target = self._target()
            short = (room_for(target, self._rip_bytes, 'the soundtrack')
                     if self.rip_ok and target else '')
            if short:
                self.music_note.config(text=short, foreground=PALETTE['bad'])
            elif self._audio_warning:
                self.music_note.config(text=self._audio_warning,
                                       foreground=PALETTE['amber'])
            elif self.rip_ok and not target:
                self.music_note.config(text=MUSIC_NEEDS_DEST,
                                       foreground=PALETTE['go'])
            else:
                self.music_note.config(text=music_status(target),
                                       foreground=self.dim)

            for button in (self.install_btn, self.rip_btn, self.apply_btn,
                           self.restore_btn):
                button.state(['disabled'])
            if self._busy:
                return
            if self.disc_ok and path and level != 'bad':
                self.install_btn.state(['!disabled'])
            if self.rip_ok and target and not short:
                self.rip_btn.state(['!disabled'])
            if self.game_ok:
                self.apply_btn.state(['!disabled'])
            if self._restorable():
                self.restore_btn.state(['!disabled'])

        def _restorable(self):
            game = self.game_var.get().strip()
            return bool(game) and any(
                os.path.isfile(os.path.join(game, *name.split('\\')) + '.bak')
                for name in PATCHED)

        # -- 1 GAME FOLDER

        def _game_body(self, parent):
            """The one folder every other card works on: installed into,
            ripped beside, patched, restored."""
            _hint(parent, GAME_HINT, self.dim, self.small, pady=(0, 6))
            grid = ttk.Frame(parent, style='Card.TFrame')
            grid.pack(fill='x')
            grid.columnconfigure(1, weight=1)
            self.game_var = tk.StringVar()
            self._field(grid, 0, 'Game folder', self.game_var, self._pick_game)
            self.game_note = _hint(parent, NO_GAME, self.dim, self.small,
                                   pady=(8, 0))
            # Only filled in when a folder was refused. "Cannot patch" on
            # its own leaves nothing to act on.
            self.game_help = _hint(parent, '', self.dim, self.small,
                                   pady=(4, 0))
            self.game_ok = False
            self.build = None
            self.game_var.trace_add('write', lambda *_a: self._later(
                '_game_after', lambda: self._check_game(
                    self.game_var.get().strip())))

        def _pick_game(self):
            path = filedialog.askdirectory(
                title='The folder holding %s, or an empty one for it' % EXE)
            if path:
                self.game_var.set(path)

        def _check_game(self, path):
            """Name the build, or say what the folder is instead.

            A folder with no game in it is not a refusal: it is where an
            install is about to go, and INSTALL below is what fills it.
            Only a folder that holds something the patcher cannot work on
            is refused, and then the reason is the thing worth saying."""
            self.game_ok = False
            self.build = None
            self.game_help.config(text='')
            if not path:
                self._set_status(NO_GAME, None)
                self._sync_buttons()
                return
            if not os.path.isdir(path):
                self._set_status(GAME_TO_CREATE, None)
                self._sync_buttons()
                return
            if not os.path.isfile(os.path.join(path, EXE)):
                self._set_status(NO_GAME_YET, None)
                self._sync_buttons()
                return
            try:
                self.build, patched = installed_build(path)
            except (OSError, ValueError) as exc:
                self._set_status('CANNOT PATCH - %s' % exc, False)
                self.game_help.config(text=GAME_HELP, foreground=self.dim)
                self._log('game: %s' % exc)
                self._sync_buttons()
                return
            self.game_ok = True
            if patched:
                self._set_status(GAME_PATCHED % build_name(self.build), 'warn')
            else:
                self._set_status(GAME_READY % (build_name(self.build), self._selected()),
                                 True)
            self._log('game: %s release in %s%s'
                      % (build_name(self.build), path, ', patched' if patched else ''))
            self._sync_buttons()

        # -- 3, 4 PATCHES

        def _feature_body(self, parent, groups, hint):
            if hint:
                _hint(parent, hint, self.dim, self.small, pady=(0, 6))
            for group in groups:
                label, tip, _keys = BY_GROUP[group]
                row = ttk.Frame(parent, style='Card.TFrame')
                row.pack(fill='x', pady=self.px(2))
                if group in ESSENTIAL:
                    # A permanently ticked box that cannot be clicked reads
                    # like something is broken. A plain line does not, and
                    # the card's own heading says these are always applied.
                    self._static_label(ttk.Label(
                        row, text=label, style='Card.TLabel',
                        padding=(2, 3))).pack(side='left')
                else:
                    var = tk.BooleanVar(value=True)
                    self.vars[group] = var
                    check = self._static_label(ttk.Checkbutton(
                        row, text=label, variable=var,
                        style='Card.TCheckbutton', command=self._retally))
                    check.pack(side='left')
                    self.checks[group] = check
                Info(row, label, tip, self).btn.pack(side='right',
                                                     padx=(6, 2))

        def _selected(self):
            """How many patches Apply would write right now."""
            return len(group_keys(self._groups(), self._extras()))

        def _groups(self):
            return tuple(g for g in EXTRA if self.vars[g].get())

        def _extras(self):
            keys = tuple(k for k in DIAGNOSTIC if self.diagnostics[k].get())
            if self.dgvoodoo.get():
                keys += ADDONS
            return keys

        def _retally(self, *_args):
            """Keep the count honest as boxes are ticked."""
            if self.game_ok:
                self._set_status(GAME_READY % (build_name(self.build), self._selected()),
                                 True)

        # -- 5 ADD-ONS, DIAGNOSTICS

        def _addons_body(self, parent):
            _hint(parent, ADDONS_HINT, self.dim, self.small, pady=(0, 6))
            row = ttk.Frame(parent, style='Card.TFrame')
            row.pack(fill='x')
            native = windows_native()
            self.dgvoodoo = tk.BooleanVar(value=native)
            label, name, url, note = DGVOODOO_LINK
            box = ttk.Checkbutton(row, text=label, variable=self.dgvoodoo,
                                  style='Card.TCheckbutton',
                                  command=self._retally)
            box.pack(side='left')
            self._static_label(box)
            link = self._static_label(tk.Label(
                row, text=name, cursor='hand2', font=self.small,
                background=PALETTE['card'], foreground=PALETTE['go']))
            link.pack(side='left', padx=self.px((8, 0)))
            link.bind('<Button-1>', lambda _e: webbrowser.open(url))
            link.bind('<Enter>', lambda _e: link.config(
                foreground=PALETTE['go_hi']))
            link.bind('<Leave>', lambda _e: link.config(
                foreground=PALETTE['go']))
            _hint(parent, note, self.dim, self.small, pady=(6, 0))
            if native:
                _hint(parent, DGVOODOO_CAPPED, PALETTE['amber'], self.small,
                      pady=(4, 0))
            else:
                box.state(['disabled'])     # Wine and Proton have wined3d
                _hint(parent, DGVOODOO_WINE, PALETTE['amber'], self.small,
                      pady=(4, 0))

        def _diagnostics_body(self, parent):
            _hint(parent, DIAGNOSTICS_HINT, self.dim, self.small, pady=(0, 6))
            for key in DIAGNOSTIC:
                label, tip = DIAGNOSTIC_INFO[key]
                row = ttk.Frame(parent, style='Card.TFrame')
                row.pack(fill='x', pady=self.px(2))
                var = tk.BooleanVar(value=False)
                self.diagnostics[key] = var
                check = self._static_label(ttk.Checkbutton(
                    row, text=label, variable=var, style='Card.TCheckbutton',
                    command=self._retally))
                check.pack(side='left')
                Info(row, label, tip, self).btn.pack(side='right',
                                                     padx=(6, 2))

        # -- LOG, ABOUT

        def _about_body(self, parent):
            self._static_label(ttk.Label(
                parent, text=TITLE, style='Card.TLabel',
                font=self.bold)).pack(anchor='w')
            # Without the scheme, which is nine characters of nothing and
            # makes the line wider than the card wants to be.
            short = REPO_URL.split('//', 1)[-1]
            link = self._static_label(ttk.Label(
                parent, text=short, style='Link.TLabel', font=self.small,
                cursor='hand2'))
            link.pack(anchor='w', pady=(1, 0))
            link.bind('<Button-1>', lambda _e: webbrowser.open(REPO_URL))
            self._static_label(ttk.Label(
                parent, text=LOGO_CREDIT, style='Card.TLabel',
                foreground=self.dim, font=self.small)).pack(anchor='w',
                                                            pady=(1, 0))
            # A ttk separator takes the theme's colour, which is not one of
            # ours; a one pixel frame in the palette's line colour is.
            tk.Frame(parent, height=1, background=PALETTE['line'],
                     borderwidth=0, highlightthickness=0).pack(
                         fill='x', pady=(10, 8))
            _hint(parent, ABOUT_NOTE, self.dim, self.small)

        def _log_body(self, parent):
            wrap = self.log_wrap = tk.Frame(parent,
                                            background=PALETTE['line'],
                                            borderwidth=0,
                                            highlightthickness=0)
            wrap.pack(fill='both', expand=True, padx=1, pady=1)
            self.log_box = tk.Text(wrap, height=6, width=34, wrap='word',
                                   state='disabled', relief='flat',
                                   highlightthickness=0, padx=6, pady=4,
                                   font=self.small,
                                   background=PALETTE['field'],
                                   foreground=PALETTE['dim'],
                                   insertbackground=PALETTE['go'])
            self.log_box.pack(side='left', fill='both', expand=True)
            bar = ttk.Scrollbar(wrap, orient='vertical',
                                style='Sr2.Vertical.TScrollbar',
                                command=self.log_box.yview)
            bar.pack(side='right', fill='y')
            self.log_box.configure(yscrollcommand=bar.set)

        def _icon(self, root):
            try:
                # Kept on self: Tk does not own the image.
                self._icon_image = tk.PhotoImage(data=ICON_PNG)
                root.iconphoto(True, self._icon_image)
            except tk.TclError:
                pass

        def _cut(self, wide, high):
            """The band's picture: two greens cut by a shallow diagonal
            that rises to the right, with the livery's white and red
            along the cut.

            An image rather than canvas lines because the canvas does
            not antialias, and at this angle a drawn line comes out as a
            staircase. Every edge here is a band with a fractional top
            and bottom, so a pixel takes each colour in proportion to
            how much of it the band covers - which is all antialiasing
            is.

            How much that is depends only on how far the pixel sits
            below the cut, so the colours are worked out once into a
            table and each row is a run of ink, a slice of the table and
            a run of sweep. Every pixel by hand took a fifth of a second
            on a wide window, and a resize waits for it."""
            def rgb(colour):
                return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))

            def over(colour, under, amount):
                if amount <= 0.0:
                    return under
                if amount >= 1.0:
                    return colour
                return tuple(int(round(u + (c - u) * amount))
                             for c, u in zip(colour, under))

            ink, sweep = rgb(PALETTE['ink']), rgb(PALETTE['sweep'])
            white, red = rgb(PALETTE['card']), rgb(PALETTE['red'])
            image = tk.PhotoImage(width=wide, height=high)
            # Low on the left, high on the right, and shallow: a steeper
            # cut reads as a mistake rather than as a stripe.
            left, right = high - self.px(18), high - self.px(46)
            half = self.px(4) / 2.0             # the white rule
            drop = self.px(5)                   # and the red under it
            under = self.px(5) / 2.0
            zone = (max(0, int(min(left, right) - half - 1)),
                    min(high, int(max(left, right) + drop + under + 2)))
            image.put(PALETTE['ink'], to=(0, 0, wide, zone[0]))
            image.put(PALETTE['sweep'], to=(0, zone[1], wide, high))

            # A pixel `below` under the cut: ink until the white rule
            # reaches it, sweep once the red has passed. In between is
            # the table, a sixty-fourth of a pixel to the entry - finer
            # than a colour step.
            first, last = -(half + 1.0), drop + under
            grain = 64.0
            table = []
            for i in range(int((last - first) * grain) + 2):
                below = first + i / grain
                pixel = over(sweep, ink, max(0.0, 1.0 - max(-below, 0.0)))
                pixel = over(white, pixel,
                             max(0.0, min(half - below, 1.0)
                                 - max(-below - half, 0.0)))
                pixel = over(red, pixel,
                             max(0.0, min(drop + under - below, 1.0)
                                 - max(drop - under - below, 0.0)))
                table.append('#%02x%02x%02x' % pixel)
            span = len(table)

            # The cut leans one way only - 18 is above 46 - so `below`
            # always grows to the right, and each row is ink, table,
            # sweep in that order.
            slope = (left - right) / float(max(wide - 1, 1))
            for y in range(*zone):
                start = y - left                # below at the left edge
                if slope <= 0.0:                # no lean to speak of
                    i = int((start - first) * grain + 0.5)
                    image.put(table[i] if 0 <= i < span else
                              (PALETTE['ink'] if start < first
                               else PALETTE['sweep']),
                              to=(0, y, wide, y + 1))
                    continue
                # Generous by a pixel at each end: the table's own
                # bounds decide the colour, not the arithmetic here.
                lo = min(max(int((first - start) / slope) - 1, 0), wide)
                hi = min(max(int((last - start) / slope) + 2, lo), wide)
                if lo:
                    image.put(PALETTE['ink'], to=(0, y, lo, y + 1))
                if hi > lo:
                    row, below = [], start + slope * lo
                    for _ in range(hi - lo):
                        i = int((below - first) * grain + 0.5)
                        row.append(table[i] if 0 <= i < span else
                                   ('#%02x%02x%02x' % ink if below < first
                                    else '#%02x%02x%02x' % sweep))
                        below += slope
                    image.put('{%s}' % ' '.join(row), to=(lo, y, hi, y + 1))
                if hi < wide:
                    image.put(PALETTE['sweep'], to=(hi, y, wide, y + 1))
            return image

        def _logo(self, parent):
            """The band across the top: the logo over the cut, with a
            rule under the lot. Returns the height it takes, which the
            content cap allows for; 0 if Tk cannot read the logo."""
            try:
                image = tk.PhotoImage(data=LOGO_PNG)
            except tk.TclError:
                return 0
            # Shipped at twice the size shown at 100%: whole-number
            # subsampling is all Tk offers.
            factor = max(1, int(round(image.height()
                                      / float(self.px(LOGO_HEIGHT)))))
            if factor > 1:
                image = image.subsample(factor)
            self._logo_image = image
            gap = self.px(12)
            high = image.height() + gap
            band = tk.Canvas(parent, height=high, highlightthickness=0,
                             borderwidth=0, background=PALETTE['ink'])
            band.pack(side='top', fill='x')
            rule = self.px(2)
            tk.Frame(parent, background=PALETTE['frame'], height=rule,
                     borderwidth=0, highlightthickness=0).pack(side='top',
                                                               fill='x')
            cut = band.create_image(0, 0, anchor='nw')
            logo = band.create_image(0, 0, image=image)
            self._cut_image, self._cut_wide = None, 0

            def draw():
                self._cut_after = None
                wide = max(band.winfo_width(), 1)
                if wide == self._cut_wide:
                    return
                if (time.monotonic() - self._cut_at) * 1000 < NUDGE_MS:
                    self._cut_after = self.root.after(NUDGE_MS, draw)
                    return              # still being dragged
                self._cut_wide = wide
                # Kept on self: Tk holds no reference of its own, and a
                # collected image leaves the band empty.
                self._cut_image = self._cut(wide, high)
                band.itemconfigure(cut, image=self._cut_image)
                band.tag_lower(cut, logo)

            def place(_event=None):
                wide = band.winfo_width()
                if wide <= 1:
                    return              # not laid out yet, so not a width
                band.coords(logo, wide // 2, high // 2 + gap // 2)
                if wide == self._cut_wide:
                    return              # a Configure that is not a resize
                # A drag sends an event a pixel, so the picture waits
                # for the dragging to stop. It does not wait when the
                # band has grown well past it - the first draw, or a
                # window maximised - because what shows in the meantime
                # is a bare green strip where the picture runs out.
                self._cut_at = time.monotonic()
                if self._cut_image is None or wide > self._cut_wide * 1.15:
                    if self._cut_after is not None:
                        self.root.after_cancel(self._cut_after)
                        self._cut_after = None
                    self._cut_at -= NUDGE_MS / 1000.0
                    draw()
                elif self._cut_after is None:
                    self._cut_after = self.root.after(NUDGE_MS, draw)

            band.bind('<Configure>', place)
            place()
            return high + rule

        def _statusbar(self, parent):
            bar = ttk.Frame(parent, style='Bar.TFrame',
                            padding=self.px((12, 8)))
            bar.pack(fill='x', side='bottom')
            self.apply_btn = ttk.Button(bar, text='Apply patches',
                                        style='Go.TButton', state='disabled',
                                        command=self._apply)
            self.apply_btn.pack(side='right')
            self.restore_btn = ttk.Button(bar, text='Restore original',
                                          style='Sr2.TButton',
                                          state='disabled',
                                          command=self._restore)
            self.restore_btn.pack(side='right', padx=(0, 8))
            # width=1 so a long note cannot widen the window
            self.status = ttk.Label(bar, text=NO_GAME, style='Bar.TLabel',
                                    foreground=self.dim, font=self.small,
                                    width=1, anchor='w')
            self.status.pack(side='left', fill='x', expand=True)
            # The font is only known once the styles have run, and the
            # first <Configure> arrives while the window is being built.
            self._status_font = self.small
            self.status.bind('<Configure>', self._fit_status, add='+')

        # -- behaviour

        def _set_status(self, text, ok=None, level='bad'):
            # ok True/False is green/red; None is a quiet note; 'warn' is a
            # success worth a second look, in amber.
            if ok == 'warn':
                colour = PALETTE['amber']
            elif ok is None:
                colour = self.dim
            else:
                colour = PALETTE['ok'] if ok else PALETTE[level]
            font = self.small if ok is None else self.bold
            self._status_text, self._status_font = text, font
            self.status.config(foreground=colour, font=font)
            self.game_note.config(text=text, foreground=colour, font=font)
            self._fit_status()

        def _static_label(self, widget):
            """Remember a widget whose text is written once."""
            self._static.append(widget)
            return widget

        def _nudge(self, _event=None):
            """Rewrite the text of every widget that never changes it.

            Resizing this window leaves some widgets undrawn on some X
            stacks: the pixels are missing while the widget itself is
            present and the right size. Every widget that survives is one
            that gets written to during the resize - the hints re-wrap, so
            they repaint; a section heading is set once at startup, so it
            does not, and it is the headings that come back blank.

            Writing a widget's own text back to it costs nothing and marks
            it for redraw, which is the part that was missing."""
            # A drag sends an event a pixel. Noting the time is free;
            # cancelling and rescheduling a Tcl timer for each one is not.
            self._nudge_at = time.monotonic()
            if self._nudge_after is None:
                self._nudge_after = self.root.after(NUDGE_MS, self._settled)

        def _settled(self):
            self._nudge_after = None
            if (time.monotonic() - self._nudge_at) * 1000 < NUDGE_MS:
                self._nudge_after = self.root.after(NUDGE_MS, self._settled)
                return                  # still moving, come back later
            for widget in self._static:
                try:
                    widget.configure(text=widget.cget('text'))
                except tk.TclError:
                    pass                # destroyed with the window

        def _fit_status(self, _event=None):
            """Trim the status line to the room it actually has."""
            text, font = self._status_text, self._status_font
            room = self.status.winfo_width()
            if room <= 1 or font.measure(text) <= room:
                self.status.config(text=text)
                return
            # Bisected rather than walked back a character at a time: each
            # measure is a call into Tcl, and a long message in a narrow
            # window cost one per character on every step of a drag.
            ellipsis = font.measure('\u2026')
            low, high = 1, len(text)
            while low < high:
                mid = (low + high + 1) // 2
                if font.measure(text[:mid]) + ellipsis <= room:
                    low = mid
                else:
                    high = mid - 1
            self.status.config(text=text[:low].rstrip() + '\u2026')

        def _log(self, text):
            # Open the log on the first line written: collapsed to start
            # with, but "see the log" is useless if the log is hidden.
            opener = self._openers.get('LOG')
            if opener:
                opener()
            self.log_box.config(state='normal')
            self.log_box.insert('end', text + '\n')
            self.log_box.see('end')
            self.log_box.config(state='disabled')

        # -- the work
        #
        # Every job runs on a worker and reports back through a queue the
        # UI thread drains: Tk is not safe to call from another one. One
        # queue and one poll for all four, because they differ only in
        # what they put in it.

        def _start(self, job, work, note):
            self._busy = job
            self._cancel = False
            self._queue = queue.Queue()
            self._sync_buttons()
            self._note_for(job, note, self.dim)

            def log(line):
                self._queue.put(('log', line))

            def done(error, result):
                self._queue.put(('done', error, result))

            self._worker = in_background(lambda: work(log), done)
            self._poll()

        def _poll(self):
            try:
                while True:
                    message = self._queue.get_nowait()
                    if message[0] == 'log':
                        self._log(message[1])
                    elif message[0] == 'progress':
                        self._note_for(self._busy, message[1], self.dim)
                    else:
                        job, self._busy = self._busy, None
                        self._finished(job, message[1], message[2])
                        return
            except queue.Empty:
                pass
            self.root.after(80, self._poll)

        def _note_for(self, job, text, colour):
            """Each job reports where it was started from: the two disc
            jobs into their own lines in INSTALL, patching into the status
            bar beside the button that ran it."""
            if job == 'install':
                self.disc_note.config(text=text, foreground=colour)
            elif job == 'music':
                self.music_note.config(text=text, foreground=colour)
            else:
                self._set_status(text, None)

        def _progress(self, text):
            """Called on the worker. Raising out of it unwinds the copy,
            which is how closing the window stops one."""
            if self._cancel:
                raise Cancelled('cancelled')
            self._queue.put(('progress', text))

        def _install(self):
            source = self.disc_var.get().strip()
            dest = self._install_dest = self._target()
            language = self.lang_var.get() or LANGUAGES[0]
            self._log('install: reading %s' % source)
            last = [-1]

            def progress(done, total):
                pct = done * 100 // max(total, 1)
                if pct != last[0]:
                    last[0] = pct
                    self._progress('%s %d%%' % (INSTALL_BUSY, pct))

            self._start('install',
                        lambda log: install(source, dest, language, log,
                                            progress),
                        INSTALL_BUSY)

        def _rip(self):
            source = self.play_var.get().strip()
            # Captured now: the folder can be changed from under a running
            # rip, and the finished message names where the tracks went.
            target = self._rip_dir = self._target()
            self._log('music: ripping from %s' % source)
            last = [-1]

            def progress(track, done, total):
                pct = done * 100 // max(total, 1)
                if pct != last[0]:
                    last[0] = pct
                    self._progress(MUSIC_BUSY % (track, pct))

            self._start('music',
                        lambda log: rip(source, target, log, progress),
                        MUSIC_BUSY % (SR2_AUDIO[0], 0))

        def _apply(self):
            dest = self.game_var.get().strip()
            keys = group_keys(self._groups(), self._extras())
            self._written = len(keys)
            self._log('patch: %d patches to %s' % (len(keys), dest))
            self._start('patch', lambda log: patch(dest, log, keys), BUSY)

        def _restore(self):
            dest = self.game_var.get().strip()
            self._start('restore', lambda log: restore(dest, log), BUSY)

        def _finished(self, job, error, result):
            if isinstance(error, Cancelled):
                if job == 'install':
                    self._note_for(job, INSTALL_CANCELLED, PALETTE['amber'])
                self._log('%s: cancelled' % job)
                self._sync_buttons()
                return
            if error is not None:
                self._failed(job, error)
                self._sync_buttons()
                return
            if job == 'install':
                dest = self._install_dest
                self._note_for(job, INSTALL_OK % (result, dest),
                               PALETTE['ok'])
                self._log('install: %d files written to %s' % (result, dest))
                # The folder is the one already in the window, so this is
                # only a re-read: it holds a game now where a moment ago
                # it did not.
                self._check_game(dest)
            elif job == 'music':
                self._log('music: %d tracks in %s'
                          % (len(result or ()), music_dir(self._rip_dir)))
                self._note_for(job, music_status(self._rip_dir), self.dim)
            else:
                # Re-read the folder first, so the build and the backups
                # are what the window says they are, then have the last
                # word on the status line.
                self._check_game(self.game_var.get().strip())
                self._set_status(DONE % self._written if job == 'patch'
                                 else RESTORED, True)
            self._sync_buttons()

        def _failed(self, job, error):
            if job in ('install', 'music'):
                where = (self._install_dest if job == 'install'
                         else music_dir(self._rip_dir))
                why = copy_failure(where, error)
                self._note_for(job, why, PALETTE['bad'])
            else:
                why = str(error)
                self._set_status(FAILED, False)
                self._log('%s: %s' % (job, why))
                return
            self._log('%s: failed - %s' % (job, why))

        def _close(self):
            """Stop a running copy or rip before the interpreter goes away.

            Both write files, and a worker still running when the
            interpreter is torn down leaves whichever one it was on half
            written. Asking it to stop and waiting a moment is enough:
            both check on the next chunk."""
            self._cancel = True
            if self._worker is not None and self._worker.is_alive():
                self._worker.join(1.5)
            self.root.destroy()

    dpi = win_dpi()
    try:
        _root = tk.Tk()
    except tk.TclError as exc:
        # Tk imports fine on a headless box and then fails here. Only the
        # window needs a display; --install and --patch do not.
        return ('Cannot open a window: %s\n'
                'Set DISPLAY or WAYLAND_DISPLAY, or run --install, --rip '
                'and --patch from the terminal.' % exc)
    if dpi:
        # Tk sizes fonts in points against 72 dpi unless told otherwise.
        _root.tk.call('tk', 'scaling', dpi / 72.0)
    _root.app = App(_root)      # where tools/guitest.py reaches it
    _root.mainloop()
    return 0



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
        for blob in (ACTIVATE_BLOB, ALTENTER_BLOB, BGROW_BLOB, TITLEROW_BLOB, TEXTCOLOR_BLOB, WIDE_BLOB, WIDE_US_BLOB,
                     VOLTRACE_BLOB, FRAMETRACE_BLOB, LOADHOLD_BLOB, HUDLAST_BLOB, PADMENU_BLOB, REPLAYPAD_BLOB, PAGEPAD_BLOB):
            for magic in EXE_MAGICS.values():
                if struct.pack('<I', magic) in exe_blob(blob, build):
                    raise ValueError('%s: a placeholder left in a stub' % build)
    # The window and the README list features, not keys; a key in neither
    # or in both is a patch nobody is offered or is offered twice.
    listed = [k for group in ESSENTIAL + EXTRA for k in BY_GROUP[group][2]]
    if sorted(listed) != sorted(PATCH_KEYS):
        raise ValueError('FEATURES and the patch table disagree: %s'
                         % ', '.join(sorted(set(listed) ^ set(PATCH_KEYS))))
    if len(listed) != len(set(listed)):
        raise ValueError('a patch is in two feature rows')
    if set(DIAGNOSTIC_INFO) != set(DIAGNOSTIC):
        raise ValueError('a diagnostic has no label')
    for table in RESOLUTION_TABLES.values():
        resolution_groups(table)
        if b''.join(b'%d\0%d\0' % (w, h) for w, h, _n in table[1]) not in RESOLUTION_BLOB:
            raise ValueError('resolution.asm names the aspect groups differently from RESOLUTION_TABLES')
    print('tables OK: %d builds, %d patches in %d features, %d sites, %d files'
          % (len(BUILDS), len(PATCH_KEYS), len(FEATURES), sites, len(PATCHED)))
    return 0


# What a key needs: dropping the second drops the first with it.
NEEDS = (('xinput', 'noregistry'), ('nogeneric', 'dinput8'), ('lobby', 'netplay'), ('netplay', 'lobby'), ('devices', 'xinput'), ('music', 'cdlevel'),
         ('widescreen2d', 'widescreen'), ('widescreen3d', 'widescreen'), ('resolution', 'widescreen'),
         ('gltrace', 'widescreen3d'), ('d3dtrace', 'widescreen2d'), ('d3dtrace2d', 'widescreen2d'))
# The game's mode, not options: borderless full screen, framed with ALT+ENTER.
FIXED = ('windowed', 'borderless')


def parse_keys(words):
    """The patches --patch's key words name: every patch, or the ones
    listed, less any given with a leading minus; a diagnostic named is
    added to either, the windowed mode to any list, and the dgvoodoo
    add-on where it is the default unless named with a minus. Words may be
    separated by commas or spaces (PowerShell hands a,b over as two)."""
    keys = [k for w in words for k in w.split(',') if k]
    unknown = [k for k in keys if k.lstrip('-') not in PATCH_KEYS + BYNAME + ADDONS]
    if unknown:
        raise ValueError('no patch named %s; the patches are %s, the diagnostics %s, the add-ons %s'
                         % (unknown[0].lstrip('-'), ', '.join(PATCH_KEYS), ', '.join(DIAGNOSTIC), ', '.join(ADDONS)))
    named = [k for k in keys if not k.startswith('-')]
    extra = BYNAME + ADDONS
    wanted = [k for k in named if k not in extra] or list(PATCH_KEYS)
    wanted += [k for k in named if k in extra]
    wanted += [k for k in ADDONS if k in default_keys() and k not in wanted]
    dropped = set(k[1:] for k in keys if k.startswith('-'))
    if dropped & set(FIXED):
        raise ValueError('%s is the game\'s mode, not an option' % ' and '.join(sorted(dropped & set(FIXED))))
    wanted = [k for k in PATCH_KEYS if k in wanted or k in FIXED] + [k for k in wanted if k in extra]
    for key, needs in NEEDS:
        if needs in dropped:
            dropped.add(key)
    return tuple(k for k in wanted if k not in dropped)


def main(argv):
    args = argv[1:]
    if not args:
        hide_console()
        run_tk()
        return 0
    try:
        if args[0] == '--install' and 3 <= len(args) <= 4:
            install(*args[1:])
            patch(args[2])
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
