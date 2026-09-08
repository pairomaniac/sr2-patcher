#!/usr/bin/env python3
"""SEGA RALLY 2 (PC, 1999) patcher. See README.md.

    python3 sr2-patcher.py                          the window
    python3 sr2-patcher.py --install SRC DIR [LANG] install from a .cue, .iso, disc folder or data1.cab
    python3 sr2-patcher.py --patch DIR              patch an installed game
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

# The Pentium III build: the six files the installer swaps in for it.
P3_FILES = (
    ('SEGA RALLY 2.exe', 1469952, '51b3da97c3c73611d3516b65bb684cb5'),
    ('AdvTelop.dll', 636928, '977dd8801a281e987c4503c9fb2f8778'),
    ('Champagn.dll', 699392, 'b8dbfe718eef561f12c99223ba7b9ec4'),
    ('MSelect.dll', 1137152, '1e6f713c39efb1558c79b795754d6e3a'),
    ('MUSASHI\\MGameGL.dll', 601600, '3d095385ece996088381dd77a0f5f954'),
    ('MUSASHI\\MGLBackground.dll', 579584, 'e7cc2a9f084a39c6f119fa1a1d769e30'),
)

# Files the patches write, with the untouched original's size and MD5.
PATCHED_FILES = {
    EXE: (1469952, '51b3da97c3c73611d3516b65bb684cb5'),
    'MUSASHI\\MGameD3D.dll': (86016, '201a9cc68096231eebcd602a65b7af6e'),
    'MUSASHI\\MGAudio.dll': (57344, 'b05b9c8e84e8a5b051045e48ea9d6bab'),
    'Title.dll': (637952, 'b1c6ea70b15cc41752c630ae0fb0cf0c'),
}

# The restore-surfaces routine in MGameD3D.dll: RVA == file offset there.
RESTORE_SITE = 0x7710
RESTORE_LEN = 0x7c
RESTORE_RELOCS = 10

# The SetTextColor sites in the exe, file offsets: `ff15` call [slot],
# `8b35` mov esi, [slot]. Every one is followed by the slot 0x495028.
TEXTCOLOR_SITES = (
    (0x203c7, '8b35'), (0x20566, '8b35'),
    (0x3485f, 'ff15'), (0x34b2a, 'ff15'), (0x34efc, 'ff15'), (0x35533, 'ff15'),
    (0x360c3, 'ff15'), (0x3a6c0, 'ff15'), (0x3cef4, 'ff15'), (0x3da96, 'ff15'),
)

# Patch table: key -> (file, sites, transform). A site is (file offset,
# original, replacement); a replacement of None means the bytes are only
# verified, the transform writes them. The transform, if any, runs on the
# file after its sites and may grow it. Applied in this order.
#
# nodisc:  two sites. The startup check that scans CD-ROM drives for the
#          play disc (0x4273c0) returns 0, "found", at once; and the loader
#          constructor (0x47632e) copies the exe's directory into the
#          disc-root slot instead of scanning drives, which is what the
#          menu reads to decide between the full game and multiplayer only.
# zdetach: MGameD3D calls IDirectDrawSurface4::DeleteAttachedSurface(0, NULL)
#          on the back buffer before creating, releasing or tearing down the
#          Z-buffer, and ignores the result. Some ddraw builds dereference the
#          NULL (Proton). The call becomes `add esp, 0xc`.
# altab:   a transform: apply_activate appends a section to the exe holding
#          asm/activate.asm and points the WM_ACTIVATEAPP handler's resume
#          call (0x426bf7) at it, so the DirectDraw surfaces are restored
#          when the game regains focus.
# managed: MGameD3D creates its video-memory textures ALLOCONLOAD|TEXTURE|
#          VIDEOMEMORY (0x10003e91) and fills them from system-memory twins
#          with IDirect3DTexture2::Load. Video-memory surfaces are what a
#          switch away loses and a restore wipes. They become managed
#          (dwCaps TEXTURE, dwCaps2 TEXTUREMANAGE): DirectDraw keeps the
#          copy and re-uploads, and never marks them lost. The AGP variant
#          at 0x10003eb7 goes with it. The one absolute address in the
#          stretch (0x1001253c, the hardware flag) leaves with its
#          relocation entry.
# restoreall: a transform: apply_restore writes asm/restore.asm over
#          MGameD3D's restore-surfaces routine (0x10007710), so it restores
#          every surface and not just three. Managed textures are not
#          lost and need none of it; the rest of what DirectDraw owns does.
# texfmt:  MGameD3D picks its 16-bit texture format from a preference list
#          (0x1000f79c): X1R5G5B5, then R5G6B5, then A1R5G5B5. Its texture
#          data is 1555 with the alpha bit set on opaque pixels and is
#          copied in as is, and every texture is colour-keyed on 0. Opaque
#          black is 0x8000: 1999 drivers compared the raw texel and drew it,
#          modern DirectX and wined3d mask the X bit first and key it out,
#          so black lettering on the 2D screens vanished. The list becomes
#          A1R5G5B5 first, where bit 15 is alpha and the key stays exact.
# textcolor: a transform: apply_textcolor appends a section to the exe
#          holding asm/textcolor.asm and points the ten SetTextColor sites
#          of the lobby at it. They pass the colour as -1; NT and Wine read
#          that as PALETTEINDEX and draw black, the colour key. The stub
#          masks the colour to RGB and continues into the import.
# windowed: the fullscreen flag the exe passes to MGameD3D's init (0x427fe5,
#          `push 1`) becomes 0, which selects the engine's own windowed
#          path: DDSCL_NORMAL, no display mode change, a clipper on the
#          window, Blt to present. The back buffer is then the desktop's
#          depth, so the row copy that puts the 16-bit .bg pictures into it
#          (0x415271) goes through asm/bgrow.asm, which expands to 32 bits
#          when it has to; apply_windowed appends it as a section.
# anydepth: MGameD3D's windowed path refuses a desktop that is not the
#          16 bits it was asked for (0x1000271e). The check is skipped;
#          everything after it takes its format from the primary.
# titlebg: Title.dll copies TITLE640.BG into the locked back buffer with
#          its own copy of that row loop (0x100014ba); the same stub,
#          assembled to read the depth from the DLL's stack, in an
#          appended section.
# borderless: a transform: apply_fullwin appends asm/fullwin.asm to
#          MGameD3D and points the windowed present (0x10004d7b) and the
#          window sizing (0x100026be) at it: the window covers the
#          monitor under the cursor, the picture is letterboxed into it.
# altenter: a transform: apply_altenter appends asm/altenter.asm to the exe
#          and points the window procedure's call to the text-input handler
#          (0x426cbc) at it. ALT+ENTER switches the window between
#          borderless over its monitor and framed at the picture's size.
# music:   a transform: apply_music appends a section to MGAudio.dll holding
#          asm/music.asm, rewrites its 11 mciSendCommandA calls to call the
#          hook and its one load of the import into esi to fetch the hook's
#          address, and repoints the entry point at the setup thunk.
PATCHES = {
    'nodisc': (EXE, (
        (0x267c0, bytes.fromhex('8b442404'), bytes.fromhex('31c0c3')),
        (0x7572e, bytes.fromhex('8d4c2420516880000000ff15985149008a44242084c0'),
         bytes.fromhex('8d8608010000508d460450ff15f4504900e9cf000000'))), None),
    'altab': (EXE, ((0x25ff7, bytes.fromhex('e864760400'), None),), 'apply_activate'),
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
        (off, bytes.fromhex(op) + bytes.fromhex('28504900'), None)
        for off, op in TEXTCOLOR_SITES), 'apply_textcolor'),
    'windowed': (EXE, (
        (0x273e6, b'\x01', b'\x00'),
        (0x14671, bytes.fromhex('8bc88be9c1e9028bf38bfaf3a58bcd83e103f3a4'), None)), 'apply_windowed'),
    'anydepth': ('MUSASHI\\MGameD3D.dll', ((0x271e, b'\x74', b'\xeb'),), None),
    'altenter': (EXE, ((0x260bc, bytes.fromhex('e85f91ffff'), None),), 'apply_altenter'),
    'titlebg': ('Title.dll', ((0x8ba, bytes.fromhex('8bc88bf38be98bfac1e902f3a58bcd03d883e103f3a4'), None),),
                'apply_titlebg'),
    'borderless': ('MUSASHI\\MGameD3D.dll', (
        (0x4d7b, bytes.fromhex('8b0df8230110'), None),
        (0x26be, bytes.fromhex('ff152cf10010'), None)), 'apply_fullwin'),
    'music': ('MUSASHI\\MGAudio.dll', (), 'apply_music'),
}

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
    'e9f9010000e98b040000eb0de8000000005b81eb11000000c353e8edffffff89'
    'de5bc3acaa84c075fa4fc331d2b90a000000f7f10430aa88d00430aac353b90a'
    '00000031db31d2f7f1524385c075f6580430aa4b75f9c607005bc331c031c98a'
    '0e80e93080f90977086bc00a01c846ebeec3ffb3fc060000ff93f40600006aff'
    'ffb300070000ff93f80600008b83100d0000c3e874ffffff6affffb3fc060000'
    'ff93f80600006a006a208d83f00c0000508d83f00a000050ff93dc0600008983'
    '100d0000ffb300070000ff93f4060000ebc689c1c1e9080fb6d16bd23cc1e908'
    '0fb6f101f269d2e8030000c1e9086bc928505289c831d2b903000000f7f15a01'
    'd0599125ff000000c35389cb31d2b9e8030000f7f16bd24b5089d031d2f7f189'
    'c158c1e11831d251b93c000000f7f159c1e21009d1c1e00809c109d989c85bc3'
    '31d2b94b000000f7f189d1c1e11031d251b93c000000f7f159c1e20809d009c8'
    'c38dbb9408000003bbd8060000e8b9feffff8db3310a0000e8a6feffffc38983'
    'cc060000508dbbf00a00008db3360a0000e88dfeffffe8d7feffffc783d00600'
    '000000000058e8b6ffffff8dbbf00a00008db3430a0000e867feffff8db39408'
    '0000e85cfeffff8db34a0a0000e851feffffe89bfeffff85c075228dbbf00a00'
    '008db3680a0000e837feffffe881feffffc783d00600000100000031c0c35589'
    'e5535657e803feffff8b450c3d03080000753e83bbc8060000000f8469020000'
    '8b4d1081e10030000081f9003000000f85540200008b5514817a08040200000f'
    '8544020000c74204cefa0000e92f020000817d08cefa00000f852b0200003d04'
    '08000074373d06080000747a3d070800000f84f90000003d0808000074383d09'
    '08000074413d55080000744a3d140800000f8435010000e9e40100008db3360a'
    '0000e8c8010000c783d006000000000000e9ca0100008db3af0a0000e8ae0100'
    '00e9ba0100008db3bb0a0000e89e010000e9aa0100008db3c80a0000e88e0100'
    '00e99a0100008b8bd40600008b83cc060000f7451004000000740b8b55148b42'
    '04e8ccfdffffc783d40600000000000085c074523b83c8060000774a83bc8304'
    '07000000744051e852feffff5985c00f854d0100008dbbf00a00008db38c0a00'
    '00e8ddfcffff85c974128db3980a0000e8cefcffff89c8e8e1fcffffe811fdff'
    'ffe91c010000b812010000e912010000f74510080000000f84030100008b5514'
    '8b4204e84afdffff898bd406000083bbd006000000742a3b83cc06000075228d'
    'bbf00a00008db39f0a0000e873fcffff89c8e886fcffffe8b6fcffffe9bf0000'
    '008983cc060000e9b40000008b5514c7420400000000f74510000100000f849d'
    '0000008b420883f803740f83f801741583f8027435e9860000008b83c8060000'
    '894204eb7bf745101000000074728b420c83f863776a8b848304070000e81efd'
    'ffff8b5514894204eb568b8bcc06000031c083bbd00600000074278dbbf00a00'
    '008db3d60a0000e8d7fbffffe821fcffff8db3f00c0000e8fffbffff8b8bcc06'
    '0000e8a2fcffff8b5514894204eb118dbbf00a0000e8a9fbffffe8f3fbffffc3'
    '31c05f5e5b5dc210008b83e2e2e2e25f5e5b5dffe0837c2408010f8514020000'
    '60e866fbffff83bbc4060000000f8500020000c783c4060000010000008d83a4'
    '09000050ff93e3e3e3e385c00f84e10100008d8bae0900005150ff93e4e4e4e4'
    '85c00f84cb0100008983dc0600008d83bd09000050ff93e3e3e3e385c00f84b0'
    '01000089c68d8bca0900005156ff93e4e4e4e48983e00600008d8bd609000051'
    '56ff93e4e4e4e48983e40600008d8be20900005156ff93e4e4e4e48983e80600'
    '008d8bee0900005156ff93e4e4e4e48983ec0600008d8bfb0900005156ff93e4'
    'e4e4e48983f00600008d8b080a00005156ff93e4e4e4e48983f40600008d8b11'
    '0a00005156ff93e4e4e4e48983f80600008db3e0060000b907000000833e000f'
    '840e01000083c6044975f168040100008d8394080000506a00ff93e5e5e5e585'
    'c00f84ec0000008dbb9408000001c74f803f5c75fa478db3250a0000e842faff'
    'ff29df81ef9408000089bbd8060000bd0200000089e8e866fbffff6a00688000'
    '00006a036a006a0168000000808d839408000050ff93e006000083f8ff742f89'
    'c76a0057ff93e40600005057ff93e80600005883e82c761631d2b930090000f7'
    'f18984ab0407000089abc80600004583fd6376a06a006a006a006a00ff93f006'
    '00008983fc0600006a006a006a006a00ff93f00600008983000700006a006a00'
    '6a008d8393000000506a006a00ff93ec06000085c0741283bbfc060000007409'
    '83bb0007000000750ac783c8060000000000006153e852f9ffff8d83e1e1e1e1'
    '5bffe09000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000077696e6d6d2e646c6c006d636953656e64537472696e6741006b6572'
    '6e656c33322e646c6c0043726561746546696c65410047657446696c6553697a'
    '6500436c6f736548616e646c6500437265617465546872656164004372656174'
    '654576656e7441005365744576656e740057616974466f7253696e676c654f62'
    '6a656374006d757369635c747261636b002e77617600636c6f73652073723262'
    '676d006f70656e2022002220747970652077617665617564696f20616c696173'
    '2073723262676d007365742073723262676d2074696d6520666f726d6174206d'
    '696c6c697365636f6e647300706c61792073723262676d002066726f6d200073'
    '65656b2073723262676d20746f200073746f702073723262676d007061757365'
    '2073723262676d00726573756d652073723262676d0073746174757320737232'
    '62676d20706f736974696f6e0090909000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
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
    '51a118b1500085c074068b1050ff5240596860e24600c3'
)
RESTORE_BLOB = bytes.fromhex(
    'e800000000598b8137ae000085c074118b105150ff5264598981afa80000c204'
    '0031c08981afa80000c20400'
)
TEXTCOLOR_BLOB = bytes.fromhex(
    '81642408ffffff00ff2528504900'
)
BGROW_BLOB = bytes.fromhex(
    '833dcc684e0020741589c189cdc1e90289de89d7f3a589e983e103f3a4c35053'
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
    '00407505e81600000031c0c36820fe4100c3e8000000005b81eb37000000c353'
    '56575589e583ec40e8e5ffffff83bbec01000000753f8d837a01000050ff1590'
    '50490085c00f840801000089c631ff8b84bbd601000001d85056ff15f0504900'
    '85c00f84eb0000008984bbec0100004783ff0572da8b3dac8850006a0257ff93'
    'f801000085c00f84c7000000c745d8280000008d4dd85150ff93fc01000085c0'
    '0f84ad00000080b3ea01000001f683ea010000017470680000cf106af057ff93'
    'ec01000031c08945c08945c4a11c5e4d008945c8a1205e4d008945cc6a006a00'
    '680000cf108d45c050ff93f40100008b75c82b75c08b55cc2b55c46a6452568b'
    '45e82b45e029d0d1f80345e0508b45e42b45dc29f0d1f80345dc506a0057ff93'
    'f0010000eb2d68000000906af057ff93ec0100006a648b45e82b45e0508b45e4'
    '2b45dc50ff75e0ff75dc6a0057ff93f001000089ec5d5f5e5bc3757365723332'
    '2e646c6c0053657457696e646f774c6f6e67410053657457696e646f77506f73'
    '0041646a75737457696e646f77526563744578004d6f6e69746f7246726f6d57'
    '696e646f77004765744d6f6e69746f72496e666f41008501000094010000a101'
    '0000b4010000c601000000900000000000000000000000000000000000000000'
)
MUSIC_MAGICS = {
    'MAGIC_ORIGENTRY': 0xE1E1E1E1,
    'MAGIC_IATMCI': 0xE2E2E2E2,
    'MAGIC_LOADLIB': 0xE3E3E3E3,
    'MAGIC_GETPROC': 0xE4E4E4E4,
    'MAGIC_GETMODFN': 0xE5E5E5E5,
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
            raise ValueError('cabinet lacks groups: %s' % ', '.join(missing))
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


def apply_music(buf):
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
    struct.pack_into('<I', out, opt + 16, rva + 5)
    return out


# The managed-textures patch: sites, plus one relocation entry to drop

def apply_managed(buf):
    """The sites are written by patch(); this drops the relocation entry of
    the absolute address they removed."""
    if _drop_relocations(buf, {0x3e9a}) != 1:
        raise ValueError('relocation entry of the hardware flag not found')
    return buf


# The restore-all patch: MGameD3D's routine rewritten in place

def apply_restore(buf):
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


ACTIVATE_SITE = 0x25ff7                 # exe, `call 0x46e260` at 0x426bf7
BGROW_SITE, BGROW_LEN = 0x14671, 20     # exe, the .bg row copy at 0x415271
ALTENTER_SITE = 0x260bc                 # exe, `call 0x41fe20` at 0x426cbc
TITLEROW_SITE, TITLEROW_LEN = 0x8ba, 22  # Title.dll, the row copy at 0x100014ba
PRESENT_SITE = 0x4d7b                   # MGameD3D, the windowed present's first instruction
SIZE_SITE = 0x26be                      # MGameD3D, `call [__imp__MoveWindow]` in the windowed init
# HIGHLOW entries inside the replaced present (absolute addresses, now dead
# code) and the one under the MoveWindow call.
FULLWIN_RELOCS = {0x4d7d, 0x4d8a, 0x4d8f, 0x4d95, 0x4da3, 0x4db1, 0x4db6, 0x4dc4, 0x4dd3, 0x26c0}


def apply_activate(buf):
    """The alt-tab stub in the exe, called from the WM_ACTIVATEAPP case."""
    out, rva = append_section(buf, ACTIVATE_SECTION, ACTIVATE_BLOB, chars=CODE_SECTION)
    _branch(out, ACTIVATE_SITE, rva)
    return out


def apply_textcolor(buf):
    """The SetTextColor stub in the exe; the eight calls and two loads of
    the import slot become a call to it and a load of its address."""
    out, rva = append_section(buf, TEXTCOLOR_SECTION, TEXTCOLOR_BLOB, chars=CODE_SECTION)
    base = struct.unpack_from('<I', out, struct.unpack_from('<I', out, 0x3c)[0] + 24 + 28)[0]
    for off, op in TEXTCOLOR_SITES:
        if op == 'ff15':
            _branch(out, off, rva, 6)
        else:
            out[off:off + 6] = b'\xbe' + struct.pack('<I', base + rva) + b'\x90'
    return out


def apply_windowed(buf):
    """The .bg row copy in the exe through bgrow.asm."""
    out, rva = append_section(buf, BGROW_SECTION, BGROW_BLOB, chars=CODE_SECTION)
    _branch(out, BGROW_SITE, rva, BGROW_LEN)
    return out


def apply_altenter(buf):
    """altenter.asm in front of the window procedure's default handler.
    The section keeps the user32 entry points it resolves, so it is writable."""
    out, rva = append_section(buf, ALTENTER_SECTION, ALTENTER_BLOB)
    _branch(out, ALTENTER_SITE, rva)
    return out


def apply_titlebg(buf):
    """Title.dll's own .bg row copy through bgrow.asm's TITLE build. The
    site holds no absolute address, so no relocation entry goes."""
    out, rva = append_section(buf, TITLEROW_SECTION, TITLEROW_BLOB, chars=CODE_SECTION)
    _branch(out, TITLEROW_SITE, rva, TITLEROW_LEN)
    return out


def apply_fullwin(buf):
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
    """Every P3 file present and untouched. Files the patches write are
    checked from their backup when one exists."""
    for name, size, digest in P3_FILES:
        path = os.path.join(dest, *name.split('\\'))
        if not os.path.isfile(path):
            raise FileNotFoundError('missing %s' % name)
        if name in PATCHED_FILES and os.path.isfile(path + '.bak'):
            path += '.bak'
        if os.path.getsize(path) != size or md5(path) != digest:
            raise ValueError('%s is not the Pentium III build' % name)


def patch(dest, log=print, keys=tuple(PATCHES)):
    """Write every wanted patch. Each touched file is patched from its
    backup, written on the first run, so patching twice is patching once."""
    check_build(dest)
    for name, (size, digest) in PATCHED_FILES.items():
        wanted = [PATCHES[key] for key in keys if PATCHES[key][0] == name]
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
            buf = transform(buf)
        with open(path, 'wb') as fh:
            fh.write(buf)
        log('patch: %s written, %s' % (name, ', '.join(k for k in keys if PATCHES[k][0] == name)))


def restore(dest, log=print):
    found = False
    for name in PATCHED_FILES:
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
    """Fail here, not half way through somebody's executable: every site
    inside the file, no two patches on one byte, replacement no longer
    than what it replaces."""
    taken = {}
    for key, (name, sites, transform) in PATCHES.items():
        if name not in PATCHED_FILES:
            raise ValueError('%s: no fingerprint for %s' % (key, name))
        if transform and transform not in globals():
            raise ValueError('%s: no transform named %s' % (key, transform))
        size = PATCHED_FILES[name][0]
        for off, old, new in sites:
            if new is not None and len(new) > len(old):
                raise ValueError('%s: replacement longer than original at 0x%x' % (key, off))
            if off + len(old) > size:
                raise ValueError('%s: site 0x%x past the end of %s' % (key, off, name))
            for i in range(off, off + len(old)):
                if (name, i) in taken:
                    raise ValueError('%s and %s both write %s:0x%x' % (key, taken[(name, i)], name, i))
                taken[(name, i)] = key
    print('tables OK: %d patches, %d sites, %d files'
          % (len(PATCHES), sum(len(v[1]) for v in PATCHES.values()), len(PATCHED_FILES)))
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
