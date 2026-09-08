# Map

Where things are: in the repository, inside `sr2-patcher.py`, and inside
the Pentium III `SEGA RALLY 2.exe`. NOTES.md says how things work; this
says where to look.

## 1. The repository

| Path | What |
| --- | --- |
| `sr2-patcher.py` | the patcher: tables, the disc image and IS5 cabinet readers, installer, manifests, patch and restore, window, CLI |
| `asm/` | `music.asm` the music hook, `activate.asm` the alt-tab stub, `restore.asm` the restore-all routine; `build.py` assembles them into `sr2-patcher.py` |
| `tools/check.py` | runs every check; `tools/cabtest.py` is the disc and cabinet check, `tools/musictest.py` and `tools/activatetest.py` the two blobs under Unicorn |
| `tools/iso2bin.py` | wraps an .iso as MODE1/2352 bin + cue, to test the disc reader without a dump |
| `tools/sr2-run.sh` | runs the installed game under umu or wine with the log in `logs/`; paths in `~/.sr2-test` |
| `tools/setup-dev.sh` | says what the toolchain is missing |
| `docs/` | this and the other documents; `docs/README.md` is the index |
| `.github/workflows/build.yml` | CI: the checks |

## 2. `sr2-patcher.py`

In file order:

| Region | Starts with |
| --- | --- |
| Constants | `VERSION`; `P3_FILES` the six fingerprints; `PATCHED_FILES` and `PATCHES` the patch table; `MUSASHI` the CLSID table; the two manifest templates |
| Generated | `MUSIC_BLOB`, `ACTIVATE_BLOB`, `RESTORE_BLOB`, `MUSIC_MAGICS`, written by `asm/build.py` |
| Disc image | `parse_cue`, `data_track`, the ripper (`WavWriter`, `audio_spans`, `rip`), `class DataTrack`, `iso_entries`, `iso_root`, `class DiscFile`, `open_source` |
| InstallShield 5 cabinet | `class Cabinet` |
| Install | `install_groups`, `write_manifests`, `install` |
| Music patch | `append_section`, `_rva_to_off`, `_iat_slot`, `_drop_relocations`, `apply_music` |
| Managed textures | `apply_managed` |
| Restore-all patch | `apply_restore` |
| Activation patch | `apply_activate` |
| Text-colour patch | `TEXTCOLOR_SITES`, `apply_textcolor` |
| Windowed patch | `BGROW_SITE`, `apply_windowed` |
| ALT+ENTER patch | `ALTENTER_SITE`, `apply_altenter` |
| Title picture patch | `TITLEROW_SITE`, `apply_titlebg` |
| Borderless patch | `PRESENT_SITE`, `SIZE_SITE`, `FULLWIN_RELOCS`, `apply_fullwin` |
| Patch | `md5`, `check_build`, `patch`, `restore` |
| Window | `gui` |
| CLI | `selfcheck`, `main` |

## 3. `SEGA RALLY 2.exe` (Pentium III)

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
| `.sr2m` at `0x1000f000` | the music blob: `+0` hook thunk, `+5` setup thunk, `+10` hook-address thunk, data after the code |

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
| music | 12 + entry + section | `MGAudio.dll`, the calls and the load above, the entry point, the appended `.sr2m` |
