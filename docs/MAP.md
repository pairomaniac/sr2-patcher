# Map

Where things are: in the repository, inside `sr2-patcher.py`, and inside
the Pentium III `SEGA RALLY 2.exe`. NOTES.md says how things work; this
says where to look.

## 1. The repository

| Path | What |
| --- | --- |
| `sr2-patcher.py` | the patcher: tables, the disc image and IS5 cabinet readers, installer, manifests, patch and restore, window, CLI |
| `asm/` | the assembly source of every code patch, `mix.inc` with the mix's numbers and `curve.inc` derived from it; `build.py` assembles them into `sr2-patcher.py` |
| `tools/check.py` | runs every check; `tools/selftest.py` applies the tables to a real install, `tools/cabtest.py` reads a real disc, the `*test.py` beside them run the stubs under Unicorn |
| `tools/iso2bin.py` | wraps an .iso as MODE1/2352 bin + cue, to test the disc reader without a dump |
| `tools/sr2.sh`, `tools/sr2-test.example` | installs, rips, patches, restores or runs one build with the paths from `~/.sr2-test`, whose template the example is |
| `tools/discsurvey.py` | hashes every file on one or more install discs and lists what differs; `--play` lists a play disc's label, root and tracks |
| `tools/setup-dev.sh` | says what the toolchain is missing |
| `tools/kit.py` | bundles every build's installed files and `data1.head` into the gitignored `tools/sr2-kit.tar.gz` |
| `docs/` | this and the other documents; `docs/README.md` is the index |
| `.github/workflows/build.yml` | CI: the checks |

## 2. `sr2-patcher.py`

In file order:

| Region | Starts with |
| --- | --- |
| Constants | `VERSION`; `BUILDS` the three builds' fingerprints, sites, slots and addresses, `build_of`; `patches` the patch table; `MUSASHI` the CLSID table; the two manifest templates |
| Generated | the `*_BLOB`s, `MUSIC_MAGICS`, `EXE_MAGICS`, written by `asm/build.py` |
| Disc image | `parse_cue`, `data_track`, the ripper (`WavWriter`, `audio_spans`, `rip`), `class DataTrack`, `iso_entries`, `iso_root`, `class DiscFile`, `open_source` |
| InstallShield 5 cabinet | `class Cabinet` |
| Install | `install_groups`, `write_manifests`, `install` |
| Music patch | `append_section`, `_off_to_rva`, `_rva_to_off`, `_iat_slot`, `_drop_relocations`, `apply_music` |
| Managed textures | `apply_managed` |
| Restore-all patch | `apply_restore` |
| Activation patch | `exe_blob`, `_check_call`, `apply_activate` |
| Text-colour patch | `apply_textcolor` |
| Windowed patch | `BGROW_LEN`, `apply_windowed` |
| ALT+ENTER patch | `apply_altenter` |
| Mix patch | `MIX_STREAM`, `apply_mix`, `apply_sfxoptions` |
| No-mixer patch | `apply_mixerless` |
| Title picture patch | `TITLEROW_SITE`, `apply_titlebg` |
| Borderless patch | `PRESENT_SITE`, `SIZE_SITE`, `FULLWIN_RELOCS`, `apply_fullwin` |
| Patch | `md5`, `check_build`, `patch`, `restore` |
| Window | `gui` |
| CLI | `selfcheck`, `main` |

## 3. `SEGA RALLY 2.exe` (Pentium III, European)

Image base `0x400000`. File offset = VA − `0x401000` + `0x400` inside
`.text`.

### Sections

| Section | VA | Virtual size | Raw | Raw size |
| --- | --- | --- | --- | --- |
| `.text` | `0x401000` | `0x936ca` | `0x400` | `0x93800` |
| `.rdata` | `0x495000` | `0x12df0` | `0x93c00` | `0x12e00` |
| `.data` | `0x4a8000` | `0xf91bc` | `0xa6a00` | `0x29400` |
| `STATUSDA` | `0x5a2000` | `0xaad` | `0xcfe00` | `0xc00` |
| `METERDAT` | `0x5a3000` | `0x10323` | `0xd0a00` | `0x10400` |
| `MYDATA` | `0x5b4000` | `0x3faf` | `0xe0e00` | `0x4000` |
| `ALIGN16D` | `0x5b8000` | `0x15a6` | `0xe4e00` | `0x1600` |
| `MGAMEMAT` | `0x5ba000` | `0x80000` | `0xe6400` | `0x80000` |
| `.rsrc` | `0x63a000` | `0x980` | `0x166400` | `0xa00` |

Entry point `0x488b46`. The base build differs in layout (`.rdata`
`0x93590` bytes, no `MGAMEMAT`); its addresses are not mapped.

### Code, as far as it is mapped

| Address | What | Touched by |
| --- | --- | --- |
| `0x421399`–`0x484b84` | the nine `CoCreateInstance` sites, one per Musashi server (NOTES.md, *Musashi*) | manifests |
| `0x426af0` | `RegisterClassA`; `0x426b80` the window procedure; `0x426bc5` its `WM_ACTIVATEAPP` case; `0x426bf7` the resume call | altab |
| `0x420fa0` | the lobby name entry: `TextOutA` of the buffer at `0x4d3d1c`, `DSTINVERT` caret; `0x41fe20` its `WM_CHAR` handler; `0x435400`, `0x4356f0`, `0x435ad0`, `0x436100`, `0x436c90` the list, status, timer, IP and chat text | textcolor |
| `0x435df4`, `0x435e9b`, `0x435f33` | the three Courier New fonts (`0x4eacd8`, `0x4ea8c8`, `0x4e84c4`) | - |
| `0x426cbc` | the window procedure's call to the text-input handler `0x41fe20`, its default for every message without a case | altenter |
| `0x4214f0` | builds MGameD3D's init struct at `0x4d5e18`: hwnd, 640, 480, 16 bpp, 120 textures, format -1, "Direct3D HAL", fullscreen at `+0x2c`; `0x427fe5` pushes that flag | windowed |
| `0x415110` | the .bg loader; `0x415180` its 565→555 pass; `0x415210` copies the picture into the locked back buffer, row copy at `0x415271` | windowed |
| `0x4272b0` | language from `GetUserDefaultLangID`, 1–6 | - |
| `0x4273c0` | **the disc check**: `SR2.CFG` present → message 2 or 3, drive scan, retry loop | nodisc |
| `0x427450` | `SR2.CFG` exists beside the exe | - |
| `0x4274e0` | drive scan: CD-ROM, label `SEGARALLY2`, `DISKID.2` | - |
| `0x427600` | main init; `0x427657` constructs the loader | - |
| `0x444be0` | processor check via `miscdll.dll!CheckKatmai` | - |
| `0x46e210`, `0x46e260` | pause and resume of the sound object at `0x50b12c` | - |
| `0x476260` | loader constructor: exe dir at `+0x108`, disc root at `+0x4`; `0x47632e` the drive scan | nodisc |
| `0x476ef0` | first byte of the disc root; `0x476f00` the exe dir | - |
| `0x427740` | reads `SR2.CFG` into the settings block, sets the disc flag at `+0x5c` | - |
| `0x4764e0` | builds `<prefix>BINDATA\<dir>\<file>`; `0x476512` the `800x600` switch | - |
| `0x476780` | builds `BINDATA\<dir>.CAB` | - |
| `0x476a50` | open: loose file, local cab, disc cab | - |
| `0x476b50` | open a loose file | - |
| `0x476bb0` | open through a cabinet (FDI) | - |

### Data

| Address | What |
| --- | --- |
| `0x495000`–`0x4a8000` | `.rdata`: IATs, the dxguid table (217 GUIDs, shared with every screen DLL), `0x49e078`–`0x49ed78` the Musashi CLSIDs |
| `0x4cf1f8`–`0x4cf304` | the loader's format strings: `%sDISKID.2`, `%sBINDATA\%s\%s\%s`, `BINDATA\%s%s`, `.CAB` |
| `0x5a2978`–`0x5a29c0` | `SEGARALLY2`, `DISKID.2`, `%c:\`, `SR2.CFG`, `%c:\AUTORUN.EXE` |
| `0x4b69b8` | `CPU Version error`, `CheckKatmai`, `MISCDLL.DLL` |
| `0x50afdc` | pointer to the settings block; `+0x50 == 1` selects `800x600` assets |
| `0x50afe0` | the settings block (`SR2.CFG` image): `+0x5c` disc flag, `+0x60` language |
| `0x50b118` | the MGameD3D interface; `0x50b12c` the sound object |
| `.sr2a` at `0x63b000` | the alt-tab stub |
| `0x54d188` | the loader object |
| `0x50b108` | pointer to the current-race block (`+0x38` mode, `+0x54`/`+0x58` course indices) |

## 4. `MUSASHI\MGameD3D.dll`

Image base `0x10000000`; file offset = VA − `0x10000000`.

| Address | What |
| --- | --- |
| `0x10003e70` | fills the video-memory texture descriptor; caps at `0x10003e91`, AGP variant at `0x10003eb7`. Patched by managed |
| `0x10003ff2` | creates the video-memory texture and `Load`s it from its system-memory twin |
| `0x10004530` | creates the system-memory texture (and palette); colour key `{0,0}` at `0x10012734` set at `0x100046ce` and `0x100043d1` |
| `0x10003cf0` | `EnumTextureFormats` callback: slots at `0x10012594`, 32 bytes each (0 P8, 1 X1R5G5B5, 2 R5G6B5, 3 A1R5G5B5, 4 A4R4G4B4, 5 P4, 6-10 DXT); the default picked from the list at `0x1000f79c`, chosen index in `0x10012740`, "not 565" flag `0x1001273c`. Patched by texfmt |
| `0x10004af0`, `0x10004bb0` | 16-bit texture copy: as is for 555, expanded for 565 |
| `0x100025d0` | cooperative level and mode: fullscreen path to `0x1000263c`, windowed after; the desktop-depth check at `0x1000271e`; the window sized at `0x100026be`. Patched by anydepth, borderless |
| `0x10004d50` | present: `Flip` when fullscreen, `Blt` to the client rect when windowed, from `0x10004d7b`. Patched by borderless |
| `0x1001240c` | the fullscreen flag; `0x100123f8`–`0x10012408` hwnd, width, height, bpp, refresh |
| `0x10007710` | restore surfaces: `IsLost`/`Restore` on primary, back buffer, Z-buffer; interface slot 16 (`+0x40`) and 93. Rewritten by restoreall |
| `0x1001254c` | the `IDirectDraw4`; `0x10012560` the `IDirect3D3`; `0x10012564` the device; `0x1001253c` the hardware flag; `0x10012580` the texture table |
| `0x10002920` | release the Z-buffer: detach from the back buffer, release |
| `0x10002970` | pick a Z-buffer format: `EnumZBufferFormats` against the four preferred at `0x100111dc` |
| `0x10002ae0`–`0x10002b7e` | create the Z-buffer (init path 1): pick, detach, create at `0x10003500`, `AddAttachedSurface` |
| `0x10002b80`–`0x10002d6e` | the same, init path 2 (a second surface description, `0x4400` caps) |
| `0x100037df` | teardown: detach, release the back buffer, release the primary |
| `0x10012554` | the back buffer |
| `0x1001255c` | the Z-buffer |
| `0x10011fc4` | last HRESULT |

## 5. `Title.dll`

Image base `0x10000000`; `.text` at RVA `0x1000`, file offset `0x400`, so
file offset = VA − `0x10000c00` there.

| Address | What |
| --- | --- |
| `0x100010e0` | loads `TITLE640.BG` (`0x100040a0`), locks the back buffer, converts 565→555 in place if the mask says so (`0x100011d0`) |
| `0x10001450` | copies the picture into the locked back buffer each frame; row copy at `0x100014ba`. Patched by titlebg |
| `0x1012892c` | the MGameD3D interface, from the exe |

## 6. `MUSASHI\MGAudio.dll`

Image base `0x10000000`, relocated at load (`.reloc` present).

| Address | What |
| --- | --- |
| `0x10003826` | the entry point (`DllMain`), repointed to the blob's `+5` |
| `0x10009110` | `__imp__mciSendCommandA` |
| `0x10002415`, `0x100030ee`, `0x1000318f`, `0x100031ac`, `0x100031ce`, `0x100031ee`, `0x1000320e`, `0x1000323f`, `0x1000327f`, `0x100032c8`, `0x1000336e` | the eleven `call [__imp__mciSendCommandA]` |
| `0x10003108` | `mov esi, [__imp__mciSendCommandA]`; `0x10003123` and the set after it call `esi` |
| `0x10003100` | open by type ID; `0x10003160` play; `0x100031c0`/`0x100031e0`/`0x10003200` pause/resume/stop; `0x10003220`–`0x100032df` status; `0x100032f0` seek |
| `.sr2m` at `0x1000f000` | the music blob: `+0` hook thunk, `+5` setup thunk, `+10` hook-address thunk, `+15` setvolume thunk, `+20` getvolume thunk, data after the code |

### Sites by patch

| Patch | Sites | Where |
| --- | --- | --- |
| nodisc | 2 | exe `0x4273c0` (file `0x267c0`), `0x47632e` (file `0x7572e`) |
| altab | 1 + section | exe `0x426bf7` (file `0x25ff7`), the appended `.sr2a` |
| zdetach | 4 | `MGameD3D.dll` `0x10002930`, `0x10002b31`, `0x10002d11`, `0x100037f4` (file offsets the same minus the base) |
| managed | 2 | `MGameD3D.dll` `0x10003e91` (32 bytes), `0x10003eb7` (7 bytes), one relocation entry dropped |
| restoreall | 1 | `MGameD3D.dll` `0x10007710`–`0x1000778c` (file `0x7710`), 44 bytes over 124 |
| texfmt | 1 | `MGameD3D.dll` `0x1000f79c` (file `0xf79c`), 12 bytes |
| textcolor | 10 + section | exe `0x420fc7`, `0x421166` (`mov esi`), `0x43545f`, `0x43572a`, `0x435afc`, `0x436133`, `0x436cc3`, `0x43b2c0`, `0x43daf4`, `0x43e696` (`call`), the appended `.sr2c` |
| altenter | 1 + section | exe `0x426cbc` (file `0x260bc`), the appended `.sr2k` |
| windowed | 2 + section | exe `0x427fe6` (file `0x273e6`), `0x415271` (file `0x14671`, 20 bytes), the appended `.sr2w` |
| anydepth | 1 | `MGameD3D.dll` `0x1000271e` (file `0x271e`) |
| titlebg | 1 + section | `Title.dll` `0x100014ba` (file `0x8ba`, 22 bytes), the appended `.sr2t` |
| borderless | 2 + section | `MGameD3D.dll` `0x10004d7b` (6 of 96 bytes, the rest dead), `0x100026be`, ten relocation entries dropped, the appended `.sr2f` |
| mix | 2 + section | `MGSound.dll` `0x1000439f` (file `0x439f`, 8 bytes), `0x10006980` (file `0x6980`, 6 bytes), the appended `.sr2b` |
| sfxlevel | 3 | Australian exe `0x4b32cb`, `0x4b332e`, `0x4b3382` (files `0xb26cb`, `0xb272e`, `0xb2782`) |
| sfxoptions | 3 | Australian `Options.dll` `0x1001052a`, `0x1001058d`, `0x100105e1` (files `0xf92a`, `0xf98d`, `0xf9e1`), three relocation entries dropped |
| win9x | 1 | Australian exe `0x44bfb0` (file `0x4b3b0`) |
| mixerless | 1 + section | Australian `MGAudio.dll` `0x10002278` (file `0x2278`), the appended `.sr2v` |
| music | 14 + entry + section | `MGAudio.dll`, the calls and the load above, the entry point, the appended `.sr2m` |
| devices | 6 + section + TXR | `Options.dll` `0x10003ff8`, `0x1000400f`, `0x10003e14`, `0x10003e67`, `0x10003dcc`, `0x10003b0c` (files `0x33f8`, `0x340f`, `0x3214`, `0x3267`, `0x31cc`, `0x2f0c`), nine `x` floats and UV entries `0xe`, `0x11` in `.data`, the appended `.sr2d` with its relocation blocks; `BINDATA\\MISC\\OPTIONS.TXR` grown by a 256x256 sheet |

## 7. `MUSASHI\MGSound.dll`

Image base `0x10000000`, relocated at load; identical in all three builds
(MD5 `a9698c1d…`). The wave and streaming sound engine over DirectSound;
the exe and `Options.dll` each carry a copy of the same client code for
it, which is why a fix for the settings-menu music has to live here.

| Address | What |
|---|---|
| `0x10006940` | the streaming buffer's `SetVolume(this, value)`: `min + (max−min) × value / 10000` in dB (`min` at `+0xdc`, `max` at `+0xe0`) into `IDirectSoundBuffer::SetVolume`; `0x6980` finishes the mapping, a `mix` site |
| `0x10004380` | the buffer's `SetRange(this, min, max)`: stores them and re-applies the current level; `0x439f` loads them, a `mix` site |
| `0x100041c0` | the buffer's `SetVolume(this, value)`, the effects and the announcer: `min + (max−min) × value / 10000`; the engine's throttle level comes through here as a percentage, so it is not patched |
| `0x10005d36` | the streaming buffer's `SetParameters`: bit 2 of the struct's `+4` is the volume, its value at `+0xc` |
| `0x1001138e` | `CMGameSoundBuffer::SetVolume... volume overflow!` - the range check |

## 8. `Options.dll`

Image base `0x10000000`, relocated at load; `.text` at RVA `0x1000`, file
offset `0x400`. The European and American DLLs are one file; the
Australian is its own build (addresses in `BUILDS`).

| Address | What |
|---|---|
| `0x10003770` | `OptionsModeInit`: loads `options.txr`, binds the ten pages, constructs the top-level object at `0x100b8fe0` |
| `0x10003af0` | the top-level state machine, 12 states through `0x10003d90`: 1 menu, 3/5/7 the pages, 0xb exit; `0x10003b0c` the state count, `0x10003cd6` the epilogue. Patched by devices |
| `0x10003c6b` | the menu's result dispatched through `0x10003dc0`, four slots. Patched by devices |
| `0x10003dd0`, `0x10003f40` | the menu: init and exec; `0x10003ff8` and `0x1000400f` construct the cursor and the icon set with count 3. Patched by devices |
| `0x10003e10` | draws the labels from `0x1009c838`–`0x1009c844` and the BACK button. Patched by devices |
| `0x1000ba40`, `0x1000bab0` | the cursor class: table, index, count, speed; left/right slide, confirm `0x400`, cancel `0x800` |
| `0x10002330`, `0x10002370` | the icon-set class over a sprite table |
| `0x1000ed90` | binds a page's UV entries to texture handles |
| `0x1000b610` | the sound manager's play: (id, 0, 0, 0), `ecx` the manager at `0x100b8bd8` |
| `0x100b9464` | the input object's holder: `+8` the object, vtable `+0x14(1)` the frame's key bits, `+0x20(1)` the stick |
| `0x1000df10` | draws a string in the 14-px font: (string, x, y, z, advance, sx, sy, a, r, g, b, glyph table, flags); `0x1009c080` the glyph sprites, `0x100fcc04` the character map |
| `0x100025f0` | draws the Game Settings page: `0x100a3128` the header band, `0x100a3290` a group plate, `0x100a4198` a row plate, the glyph-sprite labels from `0x1009c400`; `0x1009f500` the hint bar and `0x1009f370` the frame on the shared page `0x1009e708` |
| `0x1000e850` | draws a sprite: descriptor, x, y, z, rotation, scale, colour |
| `0x1009c820`, `0x1009c82c`, `0x1009c838` | the menu's item tables: cursor frames, icons, labels |
| `0x100ac9d8` | the menu's page: 54 UV entries; `0x100ace10` its sprite list |
| `0x100ad368`, `0x100ad3c0`, `0x100ad060` | the first item's frame, icon and label sprites; the rest follow |
