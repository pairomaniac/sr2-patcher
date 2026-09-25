# Map

Where things are: in the repository, inside `sr2-patcher.py`, and inside
the Pentium III `SEGA RALLY 2.exe` and the DLLs the patches touch. The
other documents say how things work; this one says where to look.
Addresses are the European build's; the American and Australian rows in
`BUILDS` map the exe's (NOTES.md, *Builds*), and the DLLs are the same
file in every build unless a section says otherwise.

Six DLLs have a section here. `MGameGL.dll`'s addresses are in
WIDESCREEN.md, `ReplayGallery.dll` has three sites and no section of its
own, and `MGNetWk.dll` is replaced whole rather than patched
(NETWORK.md). Section 10 lists every patch's sites whatever file they
are in.

## 1. The repository

| Path | What |
| --- | --- |
| `sr2-patcher.py` | the patcher: tables, the disc image and IS5 cabinet readers, installer, manifests, patch and restore, window, CLI |
| `asm/` | the assembly source of every code patch, `mix.inc` with the mix's numbers and `padpoll.inc` with the pad poll the pad stubs share; `build.py` assembles them into `sr2-patcher.py` |
| `tools/check.py` | runs every check; `tools/selftest.py` applies the tables to a real install, `tools/cabtest.py` reads a real disc, the `*test.py` beside them run the stubs under Unicorn |
| `tools/iso2bin.py` | wraps an .iso as MODE1/2352 bin + cue, to test the disc reader without a dump |
| `tools/sr2.sh`, `tools/sr2-test.example` | installs, rips, patches, restores or runs one build with the paths from `~/.sr2-test`, whose template the example is |
| `tools/frames.py` | reads the `logs\\frames.log` the frametrace diagnostic writes: frame rate, intervals, catch-ups, the worst gaps |
| `tools/discsurvey.py` | hashes every file on one or more install discs and lists what differs; `--play` lists a play disc's label, root and tracks |
| `tools/setup-dev.sh` | says what the toolchain is missing |
| `tools/loudness.py` | the RMS of the CD rips and the streamed music, and the `CD_DB - STREAM_DB` that makes them equal at equal sliders |
| `tools/uctest.py` | what the Unicorn tests share: the patcher module, the skip when Unicorn is missing, the build a file belongs to, a PE image mapped and relocated into an emulator |
| `tools/txrdump.py` | dumps a `.TXR` texture archive to PNGs, one a texture and a montage |
| `net/` | the replacement `MGNetWk.dll`: the core (`sr2net.c`), the socket shim, the COM shell (`com.c`); `build.py` compiles `MGNetWk.dll` beside them and records its hashes in `sr2-patcher.py`; `directory.py` and its unit, the INTERNET server; `net/README.md` |
| `tools/directory-install.sh` | installs `net/directory.py` as `sr2-directory.service` on a machine that should keep it up |
| `tools/nettest.c`, `tools/nettest.py` | the network core over loopback, a host and guests with packet loss; the `nettest` check |
| `tools/directorytest.py` | `net/directory.py`'s list limit, no network; the `directorytest` check |
| `tools/padbits.py` | prints which menu flag each action lands on, by running the exe's input wrapper update and pad poll under Unicorn |
| `tools/labels.py` | renders the connection screen's labels in the stock face and bakes them into `sr2-patcher.py` (needs Pillow and `fonts-urw-base35`); `--check` in the checks, `--show DIR` writes the BMPs |
| `tools/kit.py` | bundles every build's installed files and `data1.head` into the gitignored `tools/sr2-kit.tar.gz` |
| `docs/` | this and the other documents; `docs/README.md` is the index |
| `sr2-patcher.spec` | the PyInstaller build: version from the script's `VERSION` line, `net/MGNetWk.dll` as data, a one-dir bundle |
| `.github/workflows/build.yml` | CI: the checks, and the Windows exe built and released from a tag |

## 2. `sr2-patcher.py`

The regions, in file order:

| Region | Starts with |
| --- | --- |
| Constants | `VERSION`; `BUILDS` the four builds' fingerprints, sites, slots and addresses, `build_of`; the patch keys' comment; `VOLTRACE_HEADS`; the DirectInput ids; `WIDEGL_SITES`, `WIDE2D_SITES`, `RESOLUTION_TABLES`, `RESOLUTIONS`, `resolution_table`; `TITLEROW_SITE`, `PRESENT_SITE`, `SIZE_SITE`, `D3DINIT_SITES`, `FULLWIN_RELOCS`; `wide_sites`; `LOBBY_ROWS`, `lobby_sites`; `patches` the patch table; `DIAGNOSTIC`, `BYNAME`; `MUSASHI` the CLSID table |
| Generated | the `*_BLOB`s and `*_MAGICS` written by `asm/build.py`; `LOBBY_LABELS` by `tools/labels.py`; `MGNETWK_SRC` and `MGNETWK_SHA` by `net/build.py` |
| Disc image | `parse_cue`, `data_track`, the ripper (`WavWriter`, `audio_spans`, `rip`), `class DataTrack`, `iso_entries`, `iso_root`, `class DiscFile`, `open_source` |
| InstallShield 5 cabinet | `class Cabinet` |
| Install | `install_groups`, `write_manifests`, `install` |
| Music patch | `append_section`, `_off_to_rva`, `_rva_to_off`, `_iat_slot`, `_drop_relocations`, `apply_music` |
| Restore-all patch | `apply_restore` |
| Exe stubs | `_branch`, `exe_blob`, `_check_call`, `apply_activate`, `apply_textcolor`; `BGROW_LEN`, `apply_windowed`; `apply_clearsize`, `apply_loadhold`, `apply_padmenu`, `apply_replaypad`, `apply_pagepad`, `apply_hudlast`, `apply_altenter` |
| Gamepad | `apply_xinput` and the pad annex (`annex_tables` and the tables before it); `apply_dinput8`, `apply_nogeneric`, `_fill_relative` |
| No-mixer patch | `apply_mixerless` |
| Mix patch | `apply_mix` (its second entry from `BLOB_LABELS`), `apply_sfxoptions` |
| Device Settings | `apply_devices`, `patch_txr` and the page's tables |
| Connection rows | `LOBBY_DIR`, `LOBBY_BACKDROP_MD5`, `lobby_mask`, `bmp24`, `lobby_backdrop`, `lobby_art`, `clamp_mpdata` |
| Diagnostics and the rest of the exe | `apply_voltrace`, `apply_frametrace`, `apply_titlebg`, `apply_widescreen`, `apply_gltrace`, `apply_d3dtrace`, `apply_d3dtrace2d` |
| The DLLs' sections | `apply_widegl`, `apply_wide2d`, `apply_resolution`; `_self_section`; `apply_netplay`, `apply_texrange`, `apply_d3dinit`, `apply_replayfree`, `apply_sortpad`, `apply_fullwin` |
| Patch | `md5`, `check_build`, `carry_display_block`, `write_settings`, `patch`, `restore` |
| Window | `run_tk` and the classes under the `# Window` comment |
| CLI | `selfcheck`, `NEEDS`, `parse_keys`, `main` |

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
| `0x421399`–`0x484b84` | the nine `CoCreateInstance` sites (NOTES.md, *Musashi*) | manifests |
| `0x426af0` | `RegisterClassA`; `0x426b80` the window procedure; `0x426bc5` its `WM_ACTIVATEAPP` case; `0x426bf7` the resume call | altab |
| `0x420fa0` | the lobby name entry: `TextOutA` of the buffer at `0x4d3d1c`, `DSTINVERT` caret; `0x41fe20` its `WM_CHAR` handler; `0x435400`, `0x4356f0`, `0x435ad0`, `0x436100`, `0x436c90` the list, status, timer, IP and chat text | textcolor |
| `0x435df4`, `0x435e9b`, `0x435f33` | the three Courier New fonts (`0x4eacd8`, `0x4ea8c8`, `0x4e84c4`) | - |
| `0x426cbc` | the window procedure's call to the text-input handler `0x41fe20`, its default for every message without a case | altenter |
| `0x4214f0` | builds MGameD3D's init struct at `0x4d5e18`: hwnd, 640, 480, 16 bpp, 120 textures, format -1, "Direct3D HAL", fullscreen at `+0x2c`; `0x427fe5` pushes that flag | windowed |
| `0x432ca0` | the name entry after a time attack: its init, `SetPerspective` 0x3000 at `0x432e4b`; `0x433fe0` its start, the centre (320, 240) through MGameGL `+0x38` at `0x434037`; `0x434040`–`0x43493d` its 3D letters through the renderer's matrix stack and `0x487a60`; `0x48656c` the exe's own model list flushed | widescreen3d |
| `0x454cf0` | sprites at 3D points: each projected through MGameGL `+0x78` (`0x454ea6`, `0x454f0e`, `0x454f40`) and drawn as a 2D triangle list at `0x45510f`; `0x407840` a trail strip the same way (`0x407965`, `0x4079fd`) | widescreen3d |
| `0x448c70` | the race's background layers: a sky over (0, 0, 640, 256) and a sea over (0, 256, 640, 480) - `.SKY` and `.SEA` course files loaded at `0x462b80`, `MGLBackground` objects made at `0x462e10`; the sea's class at `0x49dca4` (`0x4633b0` update, `0x463500` draw), a ground plane `MGLBackground` builds at `0x100030a0` from the renderer's focal and centre and draws as 2D strips at `0x10003de0` | widescreen3d |
| `0x4219f0` | the resolution mode setter: the mode at `0x4d5e54`, the size into the struct, the renderer re-inited; `0x421450` reloads the textures, `0x4216a0` sets the viewport (`0x46bfd0`) and the 84.375° field of view (`0x46bf90`, MGameGL `+0x114`); the rect table at `0x4b12f0` | widescreen |
| `0x47f2d0` | the input wrapper's update (vtable `0x4a158c` `+8`): the button mask at `+0x34` from `GetActionState` on actions 10, 11, 12, 2-5 to bits 0, 1, 6, 9-12, ±5000 the threshold; `0x43f8e0` packs it into the pad's menu flags at `0x4ef7e4`, `0x4edcb4` the frame's, `0x4d5e08` the keyboard's from `0x41fe20` (NOTES.md, *The menus' directions*) | xinput |
| `0x415110` | the .bg loader; `0x415180` its 565→555 pass; `0x415210` copies the picture into the locked back buffer, row copy at `0x415271` | windowed |
| `0x4272b0` | language from `GetUserDefaultLangID`, 0 Japanese to 6 other, into the settings block's `+0x60`; `0x4edcd0` its copy, the lobby's `_US` bitmaps and font when not 0 (NOTES.md, *Invisible lobby text*) | - |
| `0x4273c0` | **the disc check**: `SR2.CFG` present → message 2 or 3, drive scan, retry loop | nodisc |
| `0x427450` | `SR2.CFG` exists beside the exe | - |
| `0x4274e0` | drive scan: CD-ROM, label `SEGARALLY2`, `DISKID.2` | - |
| `0x427600` | main init; `0x427657` constructs the loader; `0x427b10` the rest, one `jl` at `0x427e05` to the error box `0x4404b0` ("Failed to initialize. Error code %X") | - |
| `0x426ea0` | device select by the `display` string; `0x427240` the card warning, string 5 OK/Cancel | nocardwarn |
| `0x46e160` | the CD wrapper's SetVolume(percent, flags): values = percent × the level read at startup / 100, to MGAudio's method; called from `0x473c5c` (the menu's level, step × 11.11), `0x473f11` (the race's, step × 9, bit 31), `0x474210` (the mute at a race start, bit 31), `0x4741bc` (an entry's percentage: the fade) | cdlevel |
| `0x4280a0` | one frame: step, `0x428000`, `0x4287f0` (present, catch-up steps, the spin until 1/60 s), draw; `0x427eef` the timer init, QPF/60; `0x4287a0` the counter; `0x4288a6` the catch-up test, `0x42890b` the gate's exit (NOTES.md, *Frame timing*) | frametrace |
| `0x4187b0` | the race state's draw: the scene pass `0x418b00`, the full viewport through `0x46bfd0`, the HUD `0x429d70` at `0x418ab1` while `+0x3c` is set, the reset `0x46cec0`; the frame's root-tree draw `0x470ff0` at `0x4280f2` carries the lake and the fade node (`0x426930` → `0x46bd80`, the renderer's fade quad) (NOTES.md, *HUD after the water*) | hudlast |
| `0x419af0` | the ending, the race state's sub-state 8: `0x418f30` its scene pass (the zoom to the window through `0x41905f`), `0x48656c` the credits' draw, `0x4198fc` and `0x419ab7` the two branches that gate it (WIDESCREEN.md, *The credits*) | - |
| `0x420f10` | the lobby entry's init (surface, x, y, field, width shown): the field copied to `0x4d3d1c`, its length to `0x4d454c`; `0x41fe20` its character handler, `0x41fef1` and `0x420849` its 0x800 cap. Patched by lobby (entrycap) |
| `0x43ca20` | the IP entry popup's input state: `0x43cb4e` the OK press's length compare (blank was a broadcast search) and copy to `0x4eacec`, `0x43cbac` its sound call; `0x43cd30` the popup's init, the entry `0x420f10` on `0x4d3d1c`, 18 characters shown of 2048 (`0x41fef1`) | lobby (ipcheck) |
| `0x43bd30` | the connection screen's drawer: four button blits at y 54, 106, 158, 210 from the row table `0x4b4274` (ON2 rows from `0x4b42d8`); `0x43bef0` its input, the cursor wrap at `0x43bf55`/`0x43bf75`, the confirm at `0x43bfbd`; `0x43fff0` the type → `OpenConnection`, the latency test at `0x4400d6`; `0x43efd8` the SHOW TEAMS jump table; `0x4eace6` the type, `0x4edcc0` the cursor (NOTES.md, *The connection screen*; NETWORK.md) | lobby |
| `0x428140` | the debug-build overlay, `FPS:%2d TPF:%5d`; unreachable in retail (NOTES.md, *RallyDebug.ini*) | - |
| `0x421330` | D3D bring-up: `0x421380` creates MGameD3D and inits it (`0x4214f0`), `0x421450` clears and presents three times, `0x4215a0` creates and inits MGameGL, `0x421670` | - |
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
| `.sr2` at `0x63b000` | the annex: every exe stub, one after the other |
| `0x54d188` | the loader object |
| `0x50b108` | pointer to the current-race block (`+0x38` mode, `+0x54`/`+0x58` course indices) |

## 4. `MUSASHI\MGameD3D.dll`

Image base `0x10000000`; file offset = VA − `0x10000000`.

| Address | What |
| --- | --- |
| `0x10003e70` | fills the video-memory texture descriptor; caps at `0x10003e91`, AGP variant at `0x10003eb7`; `0x100043f0` the `Load`, `0x10004385` releases the system copy |
| `0x10003ff2` | creates the video-memory texture and `Load`s it from its system-memory twin |
| `0x10004530` | creates the system-memory texture (and palette); colour key `{0,0}` at `0x10012734` set at `0x100046ce` and `0x100043d1` |
| `0x10003cf0` | `EnumTextureFormats` callback: slots at `0x10012594`, 32 bytes each (0 P8, 1 X1R5G5B5, 2 R5G6B5, 3 A1R5G5B5, 4 A4R4G4B4, 5 P4, 6-10 DXT, 11 X8R8G8B8, 12 a 16-bit RGB); the default picked from the list at `0x1000f79c`, chosen index in `0x10012740`, "not 565" flag `0x1001273c`. Patched by texfmt |
| `0x10004af0`, `0x10004bb0` | 16-bit texture copy: as is for 555, expanded for 565 |
| `0x100025d0` | cooperative level and mode: fullscreen path to `0x1000263c`, windowed after; the desktop-depth check at `0x1000271e`; the window sized at `0x100026be`. Patched by anydepth, borderless |
| `0x10004d50` | present: `Flip` when fullscreen, `Blt` to the client rect when windowed, from `0x10004d7b`. Patched by borderless |
| `0x10004cb0` | `+0x58`, the flip flags: `DDFLIP_WAIT` or `NOVSYNC`, `INTERVAL2`-`4`; the exe sets (1, 1). `0x10004d30` `+0x54`, `WaitForVerticalBlank(BLOCKBEGIN)`, never called by the exe |
| `0x1001240c` | the fullscreen flag; `0x100123f8`–`0x10012408` hwnd, width, height, bpp, refresh |
| `0x10007b30` | offscreen surface create: `dwCaps` by the wrapper's kind at `+0x14` - 0 and 1 `0x840` system memory, 2 `0x4040` video memory (`0x10007cab`), 3 `0x20004040` non-local, 4 and 5 the primary and the back buffer, 6 a texture. Patched by surfmem |
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
| `0x10002090` | `Init(struct)`: `0x10001fd0` → `0x10002160`, the step list - `0x10002df0` and `0x10002d80` the DirectDraw object (`DirectDrawCreate`, `IDirectDraw4`), `0x100024b0` the `IDirect3D3` (with the struct's `+0x30`, the texture count), `0x10002eb0` the mode check (`EnumDisplayModes` for the struct's width, height and depth; `E_FAIL` at `0x10002ef7` when none matches, patched by anymode), `0x100025d0` the cooperative level and mode or window, `0x10003520` the primary, back buffer (`0x100036c0` the windowed one, at the picture size) and clipper, `0x10003840` the viewport and its caps (the `IDirect3D3` came at `0x100024b0`; `0x100022e0` makes the Z-buffer at `0x10002ab0` and the device at `0x10003080`), `0x100022e0` with textures - then `0x100071e0` the texture table, `0x10005fe0`, `0x10003320`. Every step stores its HRESULT at `0x10011fc4` and `jl`s out; those stores are what d3dinit logs, by RVA |

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
| `.sr2` at `0x1000f000` | the annex; the music blob: `+0` hook thunk, `+5` setup thunk, `+10` hook-address thunk, `+15` setvolume thunk, `+20` getvolume thunk, data after the code |

## 7. `MUSASHI\MGInput.dll`

Image base `0x10000000`, relocated at load; one build in the European,
American, DigiCube and MediaKite releases (MD5 `7aa0b3ae…`), an older
one in the Australian (`594a3435…`) with the same vtables at
`0x1000f764`, `0x1000f7b0`, `0x1000f868` and so on, its record update at
`0x10008170` dispatching to static polls, the keyboard's `0x10007e40`.
Vtables: the input object at `0x1000f764`, the device at `0x1000f7b0`,
the config at `0x1000f868`, the registry helper at `0x1000f8f4`, the
record at `0x1000f918`.

| Address | What |
| --- | --- |
| `0x10002010` | input `+0x28`: the config named, made and registered |
| `0x10002920` | input: the DirectInput object made, `DirectInputCreateA` at `0x1000294d` and `QueryInterface(IID_IDirectInput2A)` at `0x10002963`, kept at `+0x10`; a dinput8 site |
| `0x10002580` | input: every attached device enumerated (`EnumDevices` at `0x100025e1`, callback `0x10002300`) into a vector of `DIDEVICEINSTANCE`s, the devices made from it in the loop at `0x100026ab`; a nogeneric site at its null-GUID branch, `0x100026d2` |
| `0x10003910` | device init from a DirectInput device: `GetDeviceInfo` to `+0x14`, `GetCapabilities` to `+0x258` (the type byte `+0x260`, a dinput8 site at its first read, `0x100039ac`), `QueryInterface(IID_IDirectInputDevice2A)` at `0x100039c2` unless a keyboard, then `EnumObjects` and the data format |
| `0x10002990` | input `+0x20`: the device of a type (3 keyboard, 4 joystick, 2 mouse) and index |
| `0x100056c0` | device `+0x58`: poll `(this, source, &value, &range)`, by the type byte at `+0x260` to `0x10005390` keyboard, `0x100054b0` joystick, `0x100053e0` mouse; an xinput site |
| `0x10007100` | config `+0x2c`: update, every record over every device then finalised; an xinput site |
| `0x10007510` | config `+0x30`: `Persist(name, flags)`, bit 0 save, bit 1 keep the loaded set |
| `0x100078b0` | config `+0x38`: `GetActionState(id, &state, mode)`, the largest magnitude among the id's records |
| `0x10008130`, `0x10008210` | registry helper `+0x14` load and `+0x10` save of a slot's records; xinput sites |
| `0x10008630` | record `+0x20`: `Update(device)`, the sources polled and ANDed; `Update(0)` scales, deadzones and counts the press |
| `0x10008890`, `0x10008910` | record import and export, the `0x34`-byte layout |

## 8. `MUSASHI\MGSound.dll`

Image base `0x10000000`, relocated at load; identical in all four builds
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

## 9. `Options.dll`

Image base `0x10000000`, relocated at load; `.text` at RVA `0x1000`, file
offset `0x400`. The European, American, DigiCube and MediaKite DLLs are
one file; the Australian is its own build (addresses in `BUILDS`).

| Address | What |
|---|---|
| `0x10003770` | `OptionsModeInit`: loads `options.txr`, binds the ten pages, constructs the top-level object at `0x100b8fe0` |
| `0x10003af0` | the top-level state machine, 12 states through `0x10003d90`: 1 menu, 3/5/7 the pages, 0xb exit; `0x10003b0c` the state count, `0x10003cd6` the epilogue. Patched by devices |
| `0x10003c6b` | the menu's result dispatched through `0x10003dc0`, four slots. Patched by devices |
| `0x10003dd0`, `0x10003f40` | the menu: init and exec; `0x10003ff8` and `0x1000400f` construct the cursor and the icon set with count 3. Patched by devices |
| `0x10003e10` | draws the labels from `0x1009c838`–`0x1009c844` and the BACK button. Patched by devices |
| `0x1000ba40`, `0x1000bab0` | the cursor class: table, index, count, z; left/right slide at 10 a frame, confirm `0x400`, cancel `0x800` |
| `0x10002330`, `0x10002370` | the icon-set class over a sprite table |
| `0x1000ed90` | binds a page's UV entries to texture handles |
| `0x1000b610` | the sound manager's play: (id, 0, 0, 0), `ecx` the manager at `0x100b8bd8` |
| `0x100b9464` | the input object's holder: `+8` the object, vtable `+0x14(1)` the frame's key bits, `+0x20(1)` the stick |
| `0x1000df10` | draws a string in the 14-px font: (string, x, y, z, advance, sx, sy, a, r, g, b, glyph table, flags); `0x1009c080` the glyph sprites, `0x100fcc04` the character map |
| `0x100025f0` | draws the Game Settings page: `0x100a3128` the header band, `0x100a3290` a group plate, `0x100a4198` a row plate, the glyph-sprite labels from `0x1009c400`; `0x10002c30` its cursor, `0x10002a23` its pulse |
| `0x10001cc0` | the frame object's exec: the OPTIONS plate, the bands, and the hint bar by the message in `0x1009c784` (-1 none), popped in and out by `0x100021b0` |
| `0x1000e850` | draws a sprite: descriptor, x, y, z, rotation, scale, colour; `0x1000e5e0` at its own position; `0x1000e390` flushes the list, sorted far to near by `0x1000e510` |
| `0x1009c820`, `0x1009c82c`, `0x1009c838` | the menu's item tables: cursor frames, icons, labels |
| `0x100ac9d8` | the menu's page: 54 UV entries; `0x100ace10` its sprite list |
| `0x100ad368`, `0x100ad3c0`, `0x100ad060` | the first item's frame, icon and label sprites; the rest follow |

## 10. Sites by patch

What each patch writes, file by file. The exe's sites are the European
build's file offsets with the other builds' where they differ; the DLLs'
are VAs at the preferred base, file offsets the same minus it unless
given.

| Patch | Sites | Where |
| --- | --- | --- |
| nodisc | 2 | exe `0x4273c0` (file `0x267c0`), `0x47632e` (file `0x7572e`); DigiCube/MediaKite `0x7571e` |
| nocardwarn | 1 | exe `0x427278` (file `0x26678`), 2 bytes; American `0x26938`, Australian `0x4b263` |
| voldefault | 1 | exe `0x5a23a8` (file `0xd01a8`, 12 bytes); American `0xd05a8`, Australian `0x60c3a8` (`0x1159a8`); DigiCube/MediaKite `0xd01a8` |
| cdlevel | 1 | exe `0x473c48` (file `0x73048`), 1 byte of 4; American `0x73478`, Australian `0xb2668`; DigiCube/MediaKite `0x73038` |
| altab | 1 + section | exe `0x426bf7` (file `0x25ff7`), the annex |
| zdetach | 4 | `MGameD3D.dll` `0x10002930`, `0x10002b31`, `0x10002d11`, `0x100037f4` (file offsets the same minus the base) |
| restoreall | 1 | `MGameD3D.dll` `0x10007710`–`0x1000778c` (file `0x7710`), 44 bytes over 124, ten relocation entries dropped |
| texfmt | 1 | `MGameD3D.dll` `0x1000f79c` (file `0xf79c`), 12 bytes |
| surfmem | 1 | `MGameD3D.dll` `0x10007cb2` (file `0x7cb2`), 4 bytes |
| textcolor | 10 + section | exe `0x420fc7`, `0x421166` (`mov esi`), `0x43545f`, `0x43572a`, `0x435afc`, `0x436133`, `0x436cc3`, `0x43b2c0`, `0x43daf4`, `0x43e696` (`call`), the annex |
| altenter | 1 + section | exe `0x426cbc` (file `0x260bc`), the annex |
| widescreen | 4 + section | exe `0x4219fe` (file `0x20dfe`, 10 bytes), `0x421a18` (file `0x20e18`, 42; American `0x421aa8`, 73), `0x451e8a` (file `0x5128a`, 8), `0x4010e5` (file `0x4e5`, 6, the element walker's callback call), the annex; American `0x2108e`, `0x210a8`, `0x5160a`, `0x6e5`; Australian `0x40b1e`, `0x40b38`, `0x895c8`, `0x4e5`; DigiCube/MediaKite `0x20dfe`, `0x20e18`, `0x5127a`, `0x4e5` |
| widescreen3d | 6 + section | `MGameGL.dll` `0x100037c0` (file `0x2bc0`, 10 bytes), `0x10003870` (file `0x2c70`, 9), `0x100039e0` (file `0x2de0`, 9), `0x100033f0` (file `0x27f0`, 9), `0x10003a80` (file `0x2e80`, 8), `0x10003ae0` (file `0x2ee0`, 8), the annex |
| hudlast | 3 + section | `SEGA RALLY 2.exe` `0x418ab1`, `0x4280f2` and `0x426930` (11 bytes) (file `0x17eb1`, `0x274f2`, `0x25d30`; American `0x18161`, `0x277b2`, `0x25fe0`; Australian `0x2de01`, `0x4c119`, `0x4a940`), the annex |
| netplay | the file | `MUSASHI\MGNetWk.dll` replaced whole (stock 121344 bytes, MD5 `0a9f86f5…`, the same in every build) |
| lobby | 15 + 2 sections + art | exe `0x43cb4e` (file `0x3bf4e`, the annex's address check), `0x420f10`, `0x41fef1`, `0x420849` (files `0x20310`, `0x1f2f1`, `0x1fc49`, the entry caps), `0x43bd58`, `0x43bd76` (50 bytes), `0x43bda8`, `0x43bdcc`, `0x43bddd`, `0x43bf57`, `0x43bf77`, `0x43bf85`, `0x43bfcf`, `0x4400dd`, `0x43efe0` (files `0x3b158`, `0x3b176`, `0x3b1a8`, `0x3b1cc`, `0x3b1dd`, `0x3b357`, `0x3b377`, `0x3b385`, `0x3b3cf`, `0x3f4dd`, `0x3e3e0`; the other builds' anchors in `BUILDS`); `BINDATA\connect\PROTOCOL\CONNECT.BMP` repainted, `CONNECT_{IPX,TCPIP,MODEM}_{OFF,ON,ON2}.BMP` and `button\showteam_*.BMP` rewritten, `IP_ENTRY\Ip_entry_US.bmp` redrawn under the box |
| loadhold | 2 + section | `SEGA RALLY 2.exe` `0x41a7bb` and `0x4195be` (6 bytes each), the annex |
| padmenu | 1 + section | `SEGA RALLY 2.exe` `0x43f94f` (file `0x3ed4f`, 6 bytes; American `0x3f07f`, Australian `0x6d63f`, DigiCube/MediaKite `0x3ed4f`), the annex |
| sortpad | 1 + section | `ReplayGallery.dll` `0x10002764` (file `0x1b64`, 9 bytes; the same in every build), the annex |
| pagepad | 1 + section | `SEGA RALLY 2.exe` `0x47f506` (file `0x7e906`, 6 bytes; American `0x7ed26`, Australian `0xbdef8`, DigiCube/MediaKite `0x7e8f6`), the annex |
| replaypad | 1 + section | `SEGA RALLY 2.exe` `0x440cea` (file `0x400ea`, 5 bytes; American `0x4047a`, Australian `0x6e99a`, DigiCube/MediaKite `0x400ea`), the annex |
| clearsize | 1 + section | `SEGA RALLY 2.exe` `0x441783` (12 bytes), the annex; Australia only |
| widescreen2d | 9 + section | `MGameD3D.dll` `0x10005120`, `0x100050d0` (6 bytes each), `0x10004fe0`, `0x10005170`, `0x10005030`, `0x10005080` (10 each), `0x10006040` (9), `0x10004d50` (8), `0x1000411c` (13), seven relocation entries dropped, the annex |
| resolution | 11 + section | `Options.dll` `0x10003415` (file `0x2815`, 14 bytes), `0x10003426` (file `0x2826`, 13, a jump over), `0x10003128` (file `0x2528`, 8), `0x10003701` (file `0x2b01`, 12), `0x1000365b` (file `0x2a5b`, 6), the "7"s at `0x10003124`, `0x100034e4`, `0x10003533`, `0x1000357d`, `0x100035c4`, `0x100035f9` (a byte each), three relocation entries dropped, the annex; the same in the Australian |
| windowed | 2 + section | exe `0x427fe6` (file `0x273e6`), `0x415271` (file `0x14671`, 20 bytes), the annex |
| anydepth | 1 | `MGameD3D.dll` `0x1000271e` (file `0x271e`) |
| anymode | 1 | `MGameD3D.dll` `0x10002ef8` (file `0x2ef8`, 4 bytes) |
| titlebg | 1 + section | `Title.dll` `0x100014ba` (file `0x8ba`, 22 bytes), the annex |
| replayfree | 2 + section | `ReplayGallery.dll` `0x10003b65` (file `0x2f65`, 5 bytes), `0x1000471f` (file `0x3b1f`, 6 bytes), the annex |
| texrange | 1 + section | `MGameD3D.dll` `0x10004430` (file `0x4430`, 10 bytes), one relocation entry dropped, the annex |
| borderless | 2 + section | `MGameD3D.dll` `0x10004d7b` (6 of 96 bytes, the rest dead), `0x100026be`, ten relocation entries dropped, the annex |
| mix | 2 + section | `MGSound.dll` `0x1000439f` (file `0x439f`, 8 bytes), `0x10006980` (file `0x6980`, 6 bytes), the annex |
| sfxlevel | 3 | Australian exe `0x4b32cb`, `0x4b332e`, `0x4b3382` (files `0xb26cb`, `0xb272e`, `0xb2782`) |
| sfxoptions | 3 | Australian `Options.dll` `0x1001052a`, `0x1001058d`, `0x100105e1` (files `0xf92a`, `0xf98d`, `0xf9e1`), three relocation entries dropped |
| win9x | 1 | Australian exe `0x44bfb0` (file `0x4b3b0`) |
| mixerless | 1 + section | Australian `MGAudio.dll` `0x10002278` (file `0x2278`), the annex |
| music | 14 + entry + section | `MGAudio.dll`, the calls and the load above, the entry point, the annex |
| devices | 6 + section + TXR | `Options.dll` `0x10003ff8`, `0x1000400f`, `0x10003e14`, `0x10003e67`, `0x10003b0c`, `0x10004238` (files `0x33f8`, `0x340f`, `0x3214`, `0x3267`, `0x2f0c`, `0x3638`; the transform also writes the dispatch entry at `0x10003dcc` (file `0x31c0` + 12) and reads the item tables at `0x1009c820`, file `0x9aa20`), nine `x` floats and UV entries `0xe`, `0x11` in `.data`, the annex with its relocation blocks; `BINDATA\\MISC\\OPTIONS.TXR` grown by a 256x256 sheet |
| noregistry | 2 | exe `0x5a29c0` (file `0xd07c0`, the 7-byte name string), `0x47ef59` (file `0x7e359`, 21 bytes); American files `0xd0bc0`, `0x7e779`; Australian `0x115fd4`, `0xbd959`; DigiCube/MediaKite `0xd07c0`, `0x7e349` |
| xinput | 4 + section | `MGInput.dll` `0x10008130`, `0x10008210` (6 bytes each), `0x10007100` (6), `0x100056c0` (9), files the same minus the base, the annex; Australian `0x10007940`, `0x10007a20`, `0x10006940`, and the dword at `0x100081a8` |
| dinput8 | 4 + section | `MGInput.dll` `0x10002940` (18 bytes), `0x100039ac` (7), the ids at `0x10010680`, `0x100106c0` (16 each), files the same minus the base, the annex; Australian `0x10002870`, `0x100039f9` (6), `0x10010678`, `0x100106b8` |
| nogeneric | 1 + section | `MGInput.dll` `0x100026d2` (5 bytes), file the same minus the base, the annex; Australian `0x10002694` |
