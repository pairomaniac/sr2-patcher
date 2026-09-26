# Notes

This document describes how the game works and what the patcher does
about it. It does not describe how to use the patcher; that is in
[README.md](../README.md). Addresses and file offsets are in
[MAP.md](MAP.md). The widescreen patch, which is the largest, has
[WIDESCREEN.md](WIDESCREEN.md) to itself. The assembly sources are in
[asm/](../asm/).

Everything below was read off the retail European release (files stamped
20-21 Oct 1999, VC6 linker 6.0) with pefile, capstone and unshield, and
checked on the game running under Wine and Proton. The American and
Australian releases map onto the European one; *Builds* says how far.

## Patches

*The annex* is the one `.sr2` section the patcher appends to a file. Each
patch that puts code or data in the file grows it. The offsets in the
table are the European build's file offsets; the other builds' offsets
are in `BUILDS` and under *Builds*. Bold names are the ones the README
lists. The key in parentheses is what `--patch` takes.

| Patch | File | Offsets | Change |
| --- | --- | --- | --- |
| **Windows 9x check** (`win9x`, Australian only) | `SEGA RALLY 2.exe` | `0x4b3b0` | the check at `0x44bfb0` returns 0 at once: its `sub esp,0x94` becomes `xor eax,eax; ret` |
| **No disc required** (`nodisc`) | `SEGA RALLY 2.exe` | `0x267c0`, `0x7572e` | the startup check returns 0, meaning "found": its `mov eax,[esp+4]` becomes `xor eax,eax; ret`. The loader constructor's drive scan becomes `lstrcpyA(disc root, exe dir)` and a jump to the constructor's epilogue |
| **No card warning** (`nocardwarn`) | `SEGA RALLY 2.exe` | `0x26678` (`0x26938` American, `0x4b263` Australian) | the `push 5` before the warning's string load becomes a `jmp` to the tail that returns 0 |
| **Replay freed once** (`replayfree`) | `ReplayGallery.dll` | `0x2f65`, `0x3b1f`, the annex | the gallery's `new` becomes a thunk that remembers the block it returned; the gallery's `push eax; call free` becomes a thunk that frees only that block |
| **Texture release checked** (`texrange`) | `MUSASHI\MGameD3D.dll` | `0x4430`, the annex | the release's first ten bytes become a `jmp` into asm/texrange.asm; one relocation entry is dropped |
| **Survive ALT+TAB** (`altab`, `restoreall`) | `SEGA RALLY 2.exe`, `MUSASHI\MGameD3D.dll` | exe `0x25ff7`, the annex; DLL `0x7710`–`0x778c`, ten relocation entries | in the exe, the `WM_ACTIVATEAPP` handler's `call 0x46e260` (resume the sound) becomes a call to a stub that calls MGameD3D's restore method first. In the DLL, that restore method is rewritten as `IDirectDraw4::RestoreAllSurfaces` |
| **Z-buffer detach crash** (`zdetach`) | `MUSASHI\MGameD3D.dll` | `0x2930`, `0x2b31`, `0x2d11`, `0x37f4` | each `call [ecx+0x20]` becomes `add esp,0xc`, so the `DeleteAttachedSurface(0, NULL)` on the back buffer is skipped |
| **Missing lettering** (`texfmt`) | `MUSASHI\MGameD3D.dll` | `0xf79c` (12 bytes) | the 16-bit texture-format preference list `1, 2, 3` becomes `3, 1, 2` |
| **Invisible lobby text** (`textcolor`) | `SEGA RALLY 2.exe` | `0x203c7`, `0x20566`, `0x3485f`, `0x34b2a`, `0x34efc`, `0x35533`, `0x360c3`, `0x3a6c0`, `0x3cef4`, `0x3da96`, the annex | eight `call [__imp__SetTextColor]` become `call stub; nop`; two `mov esi, [__imp__SetTextColor]` become `mov esi, stub; nop` |
| **Lobby panels** (`surfmem`) | `MUSASHI\MGameD3D.dll` | `0x7cb2` | the offscreen surface create's video-memory caps `0x4040` become `0x840`, system memory |
| **Windowed** (`windowed`) | `SEGA RALLY 2.exe` | `0x273e6`; `0x14671`, the annex | the fullscreen flag pushed at `0x427fe5` becomes 0; the .bg row copy at `0x415271` becomes a `call` into asm/bgrow.asm |
| **Any desktop depth** (`anydepth`) | `MUSASHI\MGameD3D.dll` | `0x271e` | a `je` becomes a `jmp`, so the windowed path's "desktop must be 16-bit" check is skipped |
| **Any mode** (`anymode`) | `MUSASHI\MGameD3D.dll` | `0x2ef8` | `and eax, 0x80004005` becomes `and eax, 0`: the `E_FAIL` the mode check returns when `EnumDisplayModes` lists no 640x480x16 mode becomes `S_OK` |
| **Title picture** (`titlebg`) | `Title.dll` | `0x8ba`, the annex | the DLL's own .bg row copy at `0x100014ba` becomes a `call` into asm/bgrow.asm, assembled for that routine's stack layout |
| **Frame log** (`frametrace`, by name only) | `SEGA RALLY 2.exe` | `0x27bf0`, `0x27d0b`, the annex | the frame gate's first five bytes, and its last five before `pop ebx; ret`, become `jmp`s into asm/frametrace.asm |
| **Borderless** (`borderless`) | `MUSASHI\MGameD3D.dll` | `0x4d7b`, `0x26be`, the annex | the windowed present becomes a `jmp` to asm/fullwin.asm's present; the `call [__imp__MoveWindow]` in the windowed init becomes a `call` to its sizewindow; ten relocation entries are dropped |
| **ALT+ENTER** (`altenter`) | `SEGA RALLY 2.exe` | `0x260bc`, the annex | the window procedure's `call 0x41fe20` at `0x426cbc` becomes a call into asm/altenter.asm |
| **No mixer needed** (`mixerless`, Australian only) | `MUSASHI\MGAudio.dll` | `0x2278`, the annex | Init's `jne fail` becomes a jump to a stub that zeroes the control count at `+0x84` and eax, then jumps back to the allocation |
| **The mix** (`mix`) | `MUSASHI\MGSound.dll` | `0x439f`, `0x6980`, the annex | the buffer's `SetRange` loads its min and max through asm/mix.asm's first routine; the streaming buffer's `SetVolume` finishes its mapping through the second routine |
| **Effects at full** (`sfxlevel`, `sfxoptions`, Australian only) | `SEGA RALLY 2.exe`, `Options.dll` | exe `0xb26cb`, `0xb272e`, `0xb2782`; DLL `0xf92a`, `0xf98d`, `0xf9e1` | the setting's load becomes `mov eax, 9`; in the DLL the load's relocation entry is dropped with it |
| **Music from files** (`music`) | `MUSASHI\MGAudio.dll` | the annex, 12 sites, the entry point, the CD-volume methods `0x1db0` and `0x1e40` (`0x1d90`, `0x1e20` Australian) | every `call [__imp__mciSendCommandA]` becomes `call hook; nop`; the `mov esi, [__imp__mciSendCommandA]` at `0x10003108` becomes `call hookaddr; nop`; the entry point is repointed at the setup thunk; the CD-volume methods' entries become `jmp setvolume` and `jmp getvolume` |
| **Quieter defaults** (`voldefault`) | `SEGA RALLY 2.exe` | `0xd01a8` (`0xd05a8` American, `0x1159a8` Australian), 12 bytes | the defaults block's three sliders go from 9 to 6 |
| **CD level marked** (`cdlevel`) | `SEGA RALLY 2.exe` | `0x73048` (`0x73478` American, `0xb2668` Australian) | the menu's CD-level set at `0x473c48` pushes flags `0x40` instead of 0 |
| **Device Settings** (`devices`) | `Options.dll`, `BINDATA\MISC\OPTIONS.TXR` | DLL `0x33f8`, `0x340f`, `0x3214`, `0x3267`, `0x2f0c`, `0x3638`, the dispatch entry at `0x31c0` + 12 (Australian `0x5b68`, `0x5b7f`, `0x5984`, `0x59d7`, `0x567c`, `0x5da8`, `0x5930`), nine `x` fields and two UV entries in `.data`, the annex; the TXR grows a thirteenth sheet | the cursor's and the icon set's item counts go from 3 to 4; the item tables and the state table move to the annex, with a fourth item and two more states; the dispatch table's fourth slot becomes a stub that selects the page's state |
| **No registry** (`noregistry`) | `SEGA RALLY 2.exe` | `0xd07c0`, `0x7e359` | the file name string `SR2.CFG` becomes `SR2.DSP`; `MGameReg`'s Open at `0x47ef59` (21 bytes) becomes `xor esi,esi` |
| **Widescreen** (`widescreen`) | `SEGA RALLY 2.exe` | `0x20dfe`, `0x20e18`, `0x5128a`, `0x4e5`, the annex | four sites become `call`s into asm/wide.asm: the mode setter's entry compare, the mode setter's size stores, the screen-change routine's settings load, and the element walker's callback call. The size table follows the code in the annex |
| **Widescreen, the 3D** (`widescreen3d`) | `MUSASHI\MGameGL.dll` | `0x2bc0`, `0x2c70`, `0x2de0`, `0x27f0`, `0x2e80`, `0x2ee0`, the annex | the prologues of `SetViewport`, `SetPerspective`, `SetCentre` and the parameter getter become `jmp`s into asm/widegl.asm; the first eight bytes of the projection and of its inverse become jumps to entries of their own |
| **Widescreen, the 2D** (`widescreen2d`) | `MUSASHI\MGameD3D.dll` | `0x5120`, `0x50d0`, `0x4fe0`, `0x5170`, `0x5030`, `0x5080`, `0x6040`, `0x4d50`, `0x411c`, the annex | the first bytes of the six 2D draws, the device viewport setter, the present and the texture create become `jmp`s into asm/wide2d.asm; seven relocation entries are dropped |
| **Resolution list** (`resolution`) | `Options.dll` | `0x2815`, `0x2826`, `0x2528`, `0x2b01`, `0x2a5b`, six bytes, the annex | five sites on the Graphic Settings page go into asm/resolution.asm: the row load, the count check, the draw loop head, the row store and DEFAULT's row store. The page's six "7"s become "8". Three relocation entries are dropped |
| **HUD after the water** (`hudlast`) | `SEGA RALLY 2.exe` | `0x17eb1`, `0x274f2`, `0x25d30` (11 bytes) (`0x18161`, `0x277b2`, `0x25fe0` American; `0x2de01`, `0x4c119`, `0x4a940` Australian), the annex | the race state's HUD call, the frame's root-tree draw and the fade node's draw thunk become branches into asm/hudlast.asm |
| **Gallery sort on LB/RB** (`sortpad`) | `ReplayGallery.dll` | `0x1b64` (9 bytes), the annex | the list's `mov ecx, [esi+0x50]; and edi, 0xff` after its row update (`0x10002764`) becomes a `call` into asm/sortpad.asm. The stub steps the sort mode on a press of the annex's LB or RB |
| **Bumpers as Page Up/Down** (`pagepad`) | `SEGA RALLY 2.exe` | `0x7e906` (6 bytes) (`0x7ed26` American, `0xbdef8` Australian), the annex | the load and test after the input wrapper's action table loop (`0x47f506`) become a `call` into asm/pagepad.asm. The stub ORs the annex's LB and RB into the player's level word as 0x80 and 0x100, then does the load and test itself |
| **Pad in a replay** (`replaypad`) | `SEGA RALLY 2.exe` | `0x400ea` (5 bytes) (`0x4047a` American, `0x6e99a` Australian), the annex | the two loads where the replay controls' keyboard and joystick paths join (`0x440cea`) become a `call` into asm/replaypad.asm. The stub ORs the annex's bumpers, left stick, triggers, Y and X into the player's level word, then does the two loads itself |
| **Pad on the multiplayer screens** (`padmenu`) | `SEGA RALLY 2.exe` | `0x3ed4f` (6 bytes), the annex | the store of the pad poll's level word (`0x43f94f`) becomes a `call` into asm/padmenu.asm. The stub puts the annex's buttons into the level word. It puts the annex's directions, Back as TAB and any press as a key into the keyboard's menu word. Then it makes the edge word and does the three stores |
| **Loading screens** (`loadhold`) | `SEGA RALLY 2.exe` | `0x19bbb`, `0x189be` (6 bytes each), the annex | the store of the new loading picture when it is created (`0x41a7bb`) and the load of it at the step that deletes it (`0x4195be`) become `call`s into asm/loadhold.asm |
| **Connection rows** (`lobby`) | `SEGA RALLY 2.exe`, `BINDATA\connect\PROTOCOL\` | `0x3b158`, `0x3b176` (50 bytes), `0x3b1a8`, `0x3b1cc`, `0x3b1dd`, `0x3b357`, `0x3b377`, `0x3b385`, `0x3b3c2`, `0x3f4dd`, `0x3e3e0`; `CONNECT.BMP`, nine button files, three `showteam_*` files and `Ip_entry_US.bmp` | the connection screen's four rows IPX / TCP-IP / MODEM / SERIAL become three, INTERNET / DIRECT IP / LAN, centred. In the exe: the drawer's row y's change, its fourth blit is skipped, the cursor wraps in 0..2, the confirm never picks the modem screen, the latency is read for every type, SHOW TEAMS on row 2 searches at once, and SHOW TEAMS is relettered SEARCH. The IP entry's OK goes through asm/ipcheck.asm (`0x3bf4e`, the annex). The entries are capped by field and CTRL+V is bounded through asm/entrycap.asm (`0x20310`, `0x1f2f1`, `0x1fc49`, `0x1f7ba`, `0x200d5`, the annex). The team room's status line comes from the DLL through asm/status.asm (`0x3544b`, the annex). The chat line's block is 64 bytes larger (`0x344e4`). The popup's lower lines are redrawn. The labels are rendered by `tools/labels.py` and carried as masks. See *The connection screen* |
| **Starting box** (`starting`) | `SEGA RALLY 2.exe` | `0x367c8`, `0x359bf`, `0x27c35` (7 bytes), `0x63a0` (8 bytes), the annex | the two calls into the race setup (`0x438dc0`) go into asm/starting.asm. The stub draws a box saying the race is starting on the team room's background, blits it onto the room's last frame, presents, then runs the setup. The frame gate's present call goes through the stub's second entry, which keeps the box up. The lobby's surface loader goes through the stub's third entry, which takes the box down. Needs `lobby`. See *The starting box* |
| **Network DLL** (`netplay`) | `MUSASHI\MGNetWk.dll`, `SR2.CFG` | the whole file | the DLL is replaced by the build of `net/`: the stock DLL's CLSID and three vtables, over plain UDP. It offers a LAN search, an address typed in, and the internet through a directory server. It reads `SR2.CFG`'s `[Network]` section (Staging, Log, both 0), and writes the section when the file has none. See [NETWORK.md](NETWORK.md) and [net/README.md](../net/README.md) |
| **The clear's height** (`clearsize`, Australian only) | `SEGA RALLY 2.exe` | `0x40b83` (12 bytes), the annex | the mode setter's `mov eax, [WIDTH]` and its two pushes become a `call` to a thunk that pushes `[HEIGHT]` and `[WIDTH]` and jumps into the clear |
| **XInput** (`xinput`) | `MUSASHI\MGInput.dll` | `0x8130`, `0x8210`, `0x7100`, `0x56c0` (Australian `0x7940`, `0x7a20`, `0x6940`, `0x81a8`), the annex | the registry helper's load and save, the config's update and the device's poll become `jmp`s into asm/padinput.asm. The Australian build has no device poll, so there the keyboard-poll address is pointed at the annex instead |
| **DirectInput 8** (`dinput8`) | `MUSASHI\MGInput.dll` | `0x2940` (18 bytes), `0x39ac` (7), the ids at `0x10680`, `0x106c0` (Australian `0x2870`, `0x39f9` (6), `0x10678`, `0x106b8`), the annex | the `DirectInputCreateA` call becomes a `jmp` into asm/dinput8.asm; the first read of the device's type byte becomes a `call` to the stub's translation entry; `IID_IDirectInput8A` and `IID_IDirectInputDevice8A` are written over the DirectInput 2 ids |
| **Devices of no kind** (`nogeneric`) | `MUSASHI\MGInput.dll` | `0x26d2` (5 bytes; Australian `0x2694`), the annex | the device loop's null-GUID branch and the two instructions after it become a `jmp` into asm/nogeneric.asm. Needs `dinput8` |

The exe is never relocated. Inside its `.text`, VA = offset − 0x400 +
0x401000 (− 0x600 in the American build). In the Musashi DLLs the raw
and virtual layouts coincide, so VA = offset + 0x10000000 at the
preferred base. In `MGameGL.dll`, `Title.dll`, `Options.dll` and
`ReplayGallery.dll`, `.text` starts at raw 0x400 for RVA 0x1000, so VA =
offset + 0x10000c00. The DLLs are relocated at load. That is why every
patch that lands in a DLL is position-independent and drops the
relocation entries of the bytes it replaces.

## The executable

The exe is a shell. It holds the main loop, the file loader, the Musashi
glue, the network lobby (WSOCK32, IPX, serial, modem) and the results
and records screens. Every other screen is a DLL loaded by name, with
four exports `_XxxInit@4`, `_XxxExec@4`, `_XxxDraw@4`, `_XxxEnd@4`:

| DLL | Screen |
| --- | --- |
| `SegaLogo.dll`, `VendorLogo.dll` | logos |
| `Title.dll` | title |
| `MSelect.dll` | mode select |
| `MainMode.dll` | the race |
| `Options.dll` | options |
| `Record.dll`, `ReplayGallery.dll` | records, replays |
| `AdvTelop.dll` | attract-mode ticker |
| `Champagn.dll` | podium (`Init`/`Exec`/`Draw`/`Quit`/`CreateCamera`) |
| `SR2_MSG.dll` | message strings, one per language (`MSG_E/F/G/I/J/S.dll` are the six; the installer copies one as `SR2_MSG.dll`) |
| `miscdll.dll` | `CheckKatmai`, `CheckCab`, `CheckUK` |
| `spcArcdll.dll` | Sega's archive reader (`ReadArchiveFile`, `GetCmpFileList`) |
| `PASSWORD.dll` | `WritePassword`, the marketing password screen |

The imports are the plain Win32 set plus `ole32` (`CoInitialize`,
`CoCreateInstance`) and `WINMM` (`timeGetTime`). Neither the exe nor any
screen DLL imports a DirectX DLL. `cabinet.dll` (FDI) is loaded by name
for the play disc's cabinets.

The sections are `.text`, `.rdata`, `.data`, `STATUSDA`, `METERDAT`,
`MYDATA`, `ALIGN16D`, `MGAMEMAT` (P3 only, 512 KB writable, the SSE
scratch) and `.rsrc` (icon, accelerators, version; no manifest).

### Builds

`data1.cab` carries the base build (x87) and two overlay groups,
*PentiumIII Modules* (SSE) and *AMD Modules* (3DNow!). Each overlay
replaces the same six files: `SEGA RALLY 2.exe`, `AdvTelop.dll`,
`Champagn.dll`, `MSelect.dll`, `MUSASHI\MGameGL.dll` and
`MUSASHI\MGLBackground.dll`. The patcher installs and patches the
Pentium III build only. The three builds compute physics differently, so
replays and netplay between them would not match, and every CPU since
runs SSE.

Four builds are supported. `BUILDS` tells them apart by the exe's MD5.
Each was checked against a disc matching its Redump dump (EI-1183-1,
40924-0919, MK-85078-40, DWRPD-00081):

| | Exe linked | `.text` | Cabinet | Against the European |
| --- | --- | --- | --- | --- |
| **Australian** | 3 Jun 1999 | 0xd2c9a | `0x01005100` | the first release. It has 259 KB more code, a Windows 9x check, no `LAUNCH.EXE`, and English and Japanese only. It has its own `AdvTelop`, `Champagn`, `MSelect`, `MainMode`, `Options`, `Record`, `ReplayGallery`, `SegaLogo`, `Title.dll`, `miscdll.dll`, `MGAudio.dll` and `MGInput.dll` |
| **European** | 21 Oct 1999 | 0x936ca | `0x01000004` | - |
| **Japanese (DigiCube, MediaKite)** | 29 Nov 1999 | 0x936ba | `0x01000004` | a rebuild of the exe alone, version 2.0.0.9. Two functions were recompiled and `.text` is 0x10 shorter (*The DigiCube and MediaKite build*). The disc has no `VendorLogo.dll` and two fewer files in *BINDATA 2* |
| **American** | 3 Oct 2000 | 0x9367a | `0x01005100` | a relink. The exe has `.data1` added and `.data` 0x100 longer. `LAUNCH.EXE`, `MSG_S.dll`, `VendorLogo.dll` and `sr2_cpl.cpl` are its own, as is its `TENYEAR` trackside art |

Everything else is byte-identical across the four builds, `MGameD3D.dll`
included. The play discs carry the same assets and one soundtrack (*The
play disc*).

#### The rows

A row of `BUILDS` holds four things: the fingerprints of fourteen files
(the six the P3 build replaces and the eight more the patches touch),
the exe's sites, the import slots those sites name, and the addresses
the exe stubs read. Every patched instruction is the same bytes in all
four exes apart from its operands. Each site was found by its masked
context and read back before it went into the table:

| European | American | Australian | DigiCube, MediaKite | |
| --- | --- | --- | --- | --- |
| `0x267c0` | `0x26a80` | `0x4b420` | `0x267c0` | the disc check |
| - | - | `0x4b3b0` | - | the Windows 9x check |
| `0x7572e` | `0x75b5e` | `0xb4dbe` | `0x7571e` | the loader's drive scan; its epilogue 0xcf past the jump in all four |
| `0x25ff7` | `0x262a7` | `0x4abfd` | `0x25ff7` | `call` resume in the window procedure |
| `0x273e6` | `0x276a6` | `0x4c026` | `0x273e6` | the fullscreen flag |
| `0x14671` | `0x14921` | `0x27e71` | `0x14671` | the .bg row copy |
| `0x260bc` | `0x2636c` | `0x4acc2` | `0x260bc` | `call` the text-input handler |
| `0x46e260` | `0x46e480` | `0x4ad790` | `0x46e250` | `RESUME` |
| `0x41fe20` | `0x41feb0` | `0x43fb50` | `0x41fe20` | `HANDLER` |
| `0x50b118` | `0x50b218` | `0x575ae8` | `0x50b118` | `GAMED3D` |
| `0x5088ac` | `0x5089ac` | `0x57327c` | `0x5088ac` | `HWND` |
| `0x4d5e1c` | `0x4d5f0c` | `0x52dc1c` | `0x4d5e1c` | `WIDTH`; `HEIGHT` four bytes on |
| `0x4e6878` | `0x4e6968` | `0x53fd88` | `0x4e6878` | `LOCKDESC`, the lock description; `dwRGBBitCount` at `+0x54` |
| `0x4d5e54` | `0x4d5f44` | `0x52dc50` | `0x4d5e54` | `MODE`, the resolution mode the setter last applied |
| - | `0x4efa1c` | - | - | `HIRES`, the American build's 1024x768 flag |
| `0x50afdc` | `0x50b0dc` | `0x5759ac` | `0x50afdc` | `SETTINGS`, the game object |
| `0x4951b8`, `0x495074` | the same | `0x4d41a8`, `0x4d4078` | the same | `GetPrivateProfileStringA`, `GetModuleFileNameA` slots |
| `0x495028` | `0x495028` | `0x4d402c` | `0x495028` | `SETTEXTCOLOR`, the import slot the textcolor stub jumps through |

The ten SetTextColor sites are in the rows. Each row also names the eight
import slots the patches read. The American import table differs from
the European one in one slot, `GetLogicalDriveStringsA`, which `nodisc`
verifies. The Australian import table is laid out afresh, so all eight
slots move. The DigiCube and MediaKite exe has the European ten sites and
the European eight slots.

The Australian `Title.dll` has the row copy at the same offset, in
identical code. The Australian `MGAudio.dll` has the same eleven calls
and one load of `mciSendCommandA`, which the music patch finds for
itself, and one different branch in Init (*No mixer needed*).

#### The patched files

Ten files are patched in every build: `SEGA RALLY 2.exe`,
`MUSASHI\MGameD3D.dll`, `MUSASHI\MGameGL.dll`, `MUSASHI\MGAudio.dll`,
`MUSASHI\MGSound.dll`, `MUSASHI\MGInput.dll`, `MUSASHI\MGNetWk.dll`,
`Title.dll`, `Options.dll` and `ReplayGallery.dll`. So are
`BINDATA\MISC\OPTIONS.TXR`, the lobby's art and `MPDATA.DAT`. Each
patched file gets a `.bak` beside it, which is the untouched original.
The patcher always starts from the `.bak`, so patching twice is the same
as patching once, and restoring is a rename. A file that a run with
fewer keys leaves alone goes back to its `.bak`. So the keys given on a
run are exactly the patches in place after it.

### Sega's updates

Sega Japan published four updates for its own 1999 release (HCJ-0145),
plus a settings tool. Each update is a self-extracting installer with a
`PATCH.exe`. None was published for the English releases. The table
lists what each carries in its P3 set, by the files' version resources
and link dates:

| Update | Exe | Other files |
| --- | --- | --- |
| UPDATE231 | 2.0.0.6, 11 Jun 1999 | `Champagn.dll` 2.0.0.6, `MGInput.dll` (10 Jun), `miscdll.dll` (11 Jun, `2d0f7f64…`), `SR2_CPL.cpl`, `CABINET.DLL` |
| UPDATE232 | - | `MGAudio.dll` (28 Jun) |
| UPDATE240 | 2.0.0.7, 13 Jul 1999 | `MGAudio.dll` (13 Jul, `b05b9c8e…`), `miscdll.dll` |
| UPDATE250 | 2.0.0.8, 21 Oct 1999 | `MGInput.dll` (28 Sep, `7aa0b3ae…`), `MGAudio.dll` (`b05b9c8e…`), `miscdll.dll`, `SR2_CPL.cpl` (27 Sep), `CABINET.DLL` |
| DisplaySettings.exe | - | a tool, not a patch: writes the display block of `SR2.CFG` (System/640x480/800x600, AGP, 3D device) |

**UPDATE250's P3 `RALLY2.exe` is the European `SEGA RALLY 2.exe`, byte
for byte** (`51b3da97…`). Its i586 and AMD exes, `MGInput.dll`,
`MGAudio.dll`, `miscdll.dll` and `SR2_CPL.cpl` are the European files
too. So the European release is the Japanese one at patch level 2.50,
with a later `Champagn.dll` (2.0.0.8, 20 Oct 1999) that appears in no
update.

The exe versions in order are: 2.0.0.2 Australian and HCJ-0145, 2.0.0.6
UPDATE231, 2.0.0.7 UPDATE240, 2.0.0.8 UPDATE250 and European, 2.0.0.9
DigiCube and MediaKite, 2.0.1.1 American. The Australian exe is older
than every update, by version and by date. 2.0.1.0 has not been seen.

The 2.31 and 2.40 exes are of the Australian lineage: 1.75 MB, with
`.text` 0xd306a and 0xd30ca against the Australian 0xd2c9a. 2.50 is
where the 259 KB went. The FULL installers carry i586, AMD and P3 exes
and a `supcpu.txt` (1, 4, 2; 7 for all three). `PATCH.exe` reads that
file from the game's folder to pick one exe. It finds the game through
`HKLM\...\App Paths\SEGA RALLY 2.exe` and checks the exe's
`FileDescription` for the CPU tag. It checks nothing about the region.

So an HCJ-0145 install at 2.50 has the European exe, and `build_of`
places it as European. The check then stops at `Champagn.dll is not the
European build's`, because 2.50 leaves 2.31's `Champagn.dll` in place.
The install's other DLLs were in no update either, so an HCJ-0145
install keeps the Australian `Options.dll`, `Title.dll` and
`ReplayGallery.dll`; its disc carries the Australian contents (below).
The same happens to an Australian install run through the Japanese
updater: it ends up with the European exe over Australian DLLs, and the
patcher refuses it.

#### The Japanese pressings

Japan had three pressings: HCJ-0145 (Sega, 25 Jun 1999), DWRPD-00081
(DigiCube, 22 Nov 2000) and MKW-166 (MediaKite, 2 Mar 2001). I-O DATA
also bundled the game with its GA-TNT2 graphics cards in 1999.

| Pressing | Build |
| --- | --- |
| HCJ-0145 | Australian. It has its own barcode but the Australian disc's contents: the same data track, with the volume made on 4 Jun 1999, and the same audio |
| DWRPD-00081 | Japanese (DigiCube, MediaKite) |
| MKW-166 | Japanese (DigiCube, MediaKite); the same data tracks |
| I-O DATA bundle | not seen |

HCJ-0145 and the Australian disc install the same files, so the patcher
cannot tell them apart. It calls the row *Australian / Japanese (Sega)*
(`BUILD_NAMES`). The Australian exe (2.0.0.2) is older than every
update, and the disc carries only English and Japanese. Sega's updates,
as sega.jp published them, are `UPDATE231FULL.EXE` (25 Jun 1999),
`UPDATE232FULL.EXE` (29 Jun), `UPDATE240FULL.EXE` (15 Jul),
`UPDATE250FULL.EXE` (25 Oct), and `DisplaySettings.exe` (14 Jul), which
is a settings tool.

#### The DigiCube and MediaKite build

The MediaKite disc's data tracks are the DigiCube ones Redump lists. They
come from one master: the install disc's volume was made on 29 Nov 1999
and the play disc's on 2 Nov 1999. So one row covers both pressings.

The exe is the European one rebuilt five weeks later: version 2.0.0.9,
linked 29 Nov 1999, language 0x0411. It has the same sections at the
same addresses and sizes apart from `.text`, and the same import slots.
The code is the European code except for two functions:

| Where | What |
| --- | --- |
| `0x442180` | grows by 0x20. The functions after it, up to `0x443de0`, sit 0x20 later, and so do the eleven pointers to them in `.rdata` |
| `0x443de0` | shrinks by 0x30, so it ends at `0x444120` where Europe's ends at `0x444130` |
| from `0x444130` | everything is 0x10 earlier, and so is every pointer to it |
| `0x5b4d48` (`MYDATA`) | a default changes from 1 to 3 |

No site or address in the row falls between `0x442180` and `0x444130`.
So each exe site and code address is either the European one or, past
that range, the European one less 0x10. The addresses past the range are
the loader's drive scan, the registry open, the CD level, the bumpers'
page keys, the five volume entries, `RESUME`, `SETVIEWPORT`, `TREEDRAW`,
`HUDRESET` and `FADEDRAW`. Every data address is the European one. The
other thirteen files the row fingerprints are the European bytes.

The disc has no `VendorLogo.dll`, though the exe still tries to load one.
The loader at `0x4533e8` leaves the module's five entry points zero when
`LoadLibrary` fails, so the screen is skipped. `MSG_S.dll`, `sr2_cpl.cpl`
and the Spanish help are the American files; `LAUNCH.EXE` is this
build's own. The cabinet has the European 25 groups, with 37 files in
*Program Executable Files* and 469 in *BINDATA 2* (no vendor logo art).

### The processor check

The check at `0x444be0` does `LoadLibrary("MISCDLL.DLL")` and
`GetProcAddress("CheckKatmai")`, calls the function with a pointer to a
DWORD, and expects 1. Otherwise it shows `MessageBox("CPU Version
error")` and returns −1. `CheckKatmai` (`miscdll.dll` `0x10001020`) makes
three tests: CPUID is present (EFLAGS bit 21 toggles), `CPUID(1).EDX &
0x02808001 == 0x02808001` (FPU, MMX, FXSR, SSE), and an SSE instruction
executes under SEH. There is no vendor or family test. The check passes
on every x86 made since 1999, so there is no patch for it. If
`miscdll.dll` were missing, the exe would fail at `LoadLibrary` first.

### The card check

The device-select routine at `0x426ea0` walks the entries MGameD3D
enumerated (`0x2c0` bytes each) and picks the one whose name matches the
`display` string in `SR2.CFG`. For entry 0 it adds the desktop's
`bpp × width × height / 8` to the entry's free video memory. `0x427240`
then warns (string 5 of `SR2_MSG.dll`, `WARNING`, OK/Cancel) when that
memory is under 4,000,000 bytes or when bits `0x1800` of the entry's
`+0x34` are clear. Cancel makes the routine return 1 and the caller exit.
If bit 0 of the same word is clear, the routine returns −1, "No 3D
capability".

Wine passes the bits. A Radeon R9 380 on Windows does not pass them, or
wraps the DWORD, and gets the box on every start. No card sold since is
on the list, so `nocardwarn` skips the box. The −1 path stays. The
Australian exe has no memory test.

### The Windows 9x check

Australian only. The check at `0x44bfb0` shows "Please run on Windows
9x." unless `GetVersionExA` gives `dwPlatformId` 1. The patch makes the
check return 0 at once. The other builds have no such check.

## Musashi

The game is written on Sega's *MUSASHI* middleware. The middleware is a
set of in-process COM servers under `MUSASHI\`, each with
`DllRegisterServer`. The exe creates eight of them by CLSID, the screen
DLLs create the sound one again, and two are created internally:

| CLSID | DLL | Imports | Role |
| --- | --- | --- | --- |
| `{1A413041-D93C-11D1-8F44-00A0C9697E45}` | `MGameD3D.dll` | `DDRAW.dll` | DirectDraw/Direct3D device (DX6: `IDirect3D3`, `IDirectDrawSurface4`, "Direct3D HAL") |
| `{27AFF141-DA17-11D1-8F44-00A0C9697E45}` | `MGameGL.dll` | - | the renderer ("MUSASHI Graphic Library", not OpenGL) |
| `{452593F0-F878-11D2-ADB9-00A0C9A0FB23}` | `MGLBackground.dll` | - | background/sky renderer |
| `{5784B940-F4BC-11D1-A496-0000C02DB0F3}` | `MGInput.dll` | `DINPUT.dll` | input |
| `{6177AF40-D601-11D1-A496-0000C02DB0F3}` | `MGSound.dll` | `DSOUND.dll` | sound; also created by every screen DLL |
| `{ACEF8F00-D517-11D1-A496-0000C02DB0F3}` | `MGAudio.dll` | `WINMM.dll` | CD audio over MCI, its volume over the mixer |
| `{0D5837F0-3E3C-11D2-924E-00A0C9697E45}` | `MGNetWk.dll` | `DPLAYX.dll` | DirectPlay networking |
| `{EE799FC0-D56F-11D2-8D16-00105A6B7166}` | `MGameReg.dll` | `ADVAPI32` | registry (`Software\%s\%s`) |
| `{F8743DC0-627C-11D2-BD4E-0000C02DB0F3}` | `MEvent.dll` | - | internal |
| `{08A33BE0-61C6-11D2-BD4E-0000C02DB0F3}` | `MStream.dll` | - | internal |

`MUSASHI\SR2.dll` is the launcher's settings page (COMCTL32). The game
does not use it.

This arrangement has two consequences:

- The Musashi DLLs import DirectDraw, DirectInput and DirectSound by
  name, and COM loads the Musashi DLLs with
  `LOAD_WITH_ALTERED_SEARCH_PATH`. That flag searches the DLL's own
  directory first, then the system ones, and never the exe's. So a
  wrapper `ddraw.dll` goes in `MUSASHI\`, not beside the exe, where it
  would never be found. A wrapper's `D3DImm.dll` is loaded by the system
  `ddraw` machinery, so it goes beside the exe. No reroute patch is
  needed.
- Without registration every `CoCreateInstance` fails. The installer ran
  `LAUNCH.exe -musashi` to register the servers. The patcher instead
  writes an application manifest beside the exe that depends on assembly
  `MUSASHI`, and writes `MUSASHI\MUSASHI.manifest` with a `comClass` per
  DLL. An external `.exe.manifest` is honoured because the exe embeds
  none. This works under Wine, Proton and Windows 10. The same manifest
  declares the process `dpiAware`. Without that declaration Windows
  scales the window on a high-DPI display, and once it has noticed the
  scaling it puts up the Program Compatibility Assistant and sets the
  override itself.

### The registry

The exe imports no registry function. `MGameReg.dll` is the registry.
Its Open (`0x10001420`) is `RegCreateKeyExA(HKEY_LOCAL_MACHINE,
"Software\%s\%s", KEY_ALL_ACCESS)`. The exe calls it (`0x47ef5e`) with
`"SEGA"` and `"SEGA RALLY 2"` and hands the resulting object to
`MGInput`'s init (`0x47ef9e`).

The controller configuration lived under that key. `SR2_CPL.cpl`, the
"Controller Settings" Control Panel item the installer added, wrote it.
The game only reads the key. It runs on its defaults when the key is
empty, and on that first run it writes player 1's defaults there itself.
Player 2 has no configuration without the applet.

The object serves nothing else in the exe; `MGameReg`'s `App Paths`
lookup is never reached. So with the Open skipped and `MGInput`'s load
and save replaced (*Gamepad*), the key is never made. That is also what
Windows without administrator rights needs. Nothing in `setup.ins`
writes under `Software\` except the DirectPlay lobby key
`Software\Microsoft\DirectPlay\Applications\SEGA RALLY 2`.

### Car models

A `.mdl` is one block of file offsets, which the load (`0x474e80`) fixes
up to pointers. Dword 0 is the size and dword 2 is the top node's link.
A node is 0x80 bytes:

| Offset | Field |
| --- | --- |
| `+0` | mesh |
| `+4` | its flag block |
| `+8` | an index |
| `+0xc` | kind: 0 body, 1 wheel or interior, 2 window, -1 lamp or light |
| `+0x10`, `+0x1c` | bounding centre and radius |
| `+0x20`, `+0x2c`, `+0x40` | position, rotation, scale |
| `+0x60`, `+0x64` | child, next |

The header points at that link, so the top node is at size − 0x80. A
mesh descriptor is 0x20 bytes: vertices (32 bytes each: position,
normal, u, v), indices, material, counts, and at `+0x18` the value 10 for
the ordinary path. The mesh's flag block follows the descriptor: `0x903`
is a body, `0x103` a wheel, `0x113` a window, `0x1003` lamp glass, `3` a
glow quad. A node whose flag block is null holds a light
(`tenkougen.mdl`, the two headlight cones in a body).

Only the exe applies the node transforms. The wheels' draw (`0x47e450`)
translates, rotates and scales by them. The body's draw (`0x44bba0`, with
the LOD table at `0x4bc398`) and the lamp models' draw (`0x44c320`, which
walks the tree at `0x44c3f0`) draw each mesh under the car's matrix as it
is.

A car's set lives in `CAR\<name>\`. The name table is at `0x4cc400` and
the set is loaded at `0x469b69`. It holds:

- `s_`, `m_`, `l_`, `r_<car>.mdl`: the body at each level of detail. Each
  is a body, four wheels, more parts as the detail rises, one or two
  windows and the two lights, mapped into `body.txr` and its dirt
  variants.
- `normal.mdl`, `snowy.mdl` with `sn_light.mdl`, `desert.mdl` with
  `de_light.mdl`: the lamp kit by course type (`0x4ccf44`: 0 desert, 2
  snow, otherwise normal). `normal.mdl` is the lens glass alone.
  `snowy.mdl` is the pod and its glass. `desert.mdl` is the snorkel, the
  scuttle lamps, the bull bar and the spare-wheel rack. These map into
  `option.txr`.
- `ft_light`, `bk_light`, `hazard`, `bkfire`, `tenkougen`, `brake`,
  `small`, `close`: the glows. Each is a quad at the lamp's place, with
  +z the front.

A race's car object (`0x469f12`) gets a 0x68-byte glow object
(`0x485250`) per glow model. The glow object holds a clone of the model's
top node. `0x4855f0` draws the glow translated by the node's position,
with the quad's size and brightness taken from the view angle and
distance. A car's `Draw` (`0x44b0c0` for the player's car, `0x442b30` for
an opponent's) draws the wheels, the glows and the kit, then the body,
all under one push of the car's matrix (`0x128` in the car).

The desert kit's black pieces on the Celica, the snorkel up the left
A-pillar and the backs of the two scuttle lamps, are that model as it is
drawn, not a placement fault. A trace of the model draws showed the kit
under the body's own matrix.

The creation changes the loaded data in one way. With the desert kit it
adds `0x4cd2cc[car]` (0.125 for half the cars) to the z of
`de_light.mdl`'s top node (`0x46a609`). The models stay loaded between
races of the same car, so that glow creeps forward a step each race.

## Startup and files

### The install contract

The exe itself touches no registry; the registry is `MGameReg`'s, above.
At startup the exe does three things:

1. `0x427450` calls `GetModuleFileNameA` and opens `SR2.CFG` beside the
   exe. The file must exist.
2. `0x4274e0` calls `GetLogicalDrives`. For each drive it checks
   `GetDriveTypeA == DRIVE_CDROM`, checks that `GetVolumeInformationA`
   gives the label `SEGARALLY2`, and opens `X:\DISKID.2`. It returns the
   drive index, or −1.
3. `0x4273c0` wraps step 2. On −1 it shows a `MessageBox` with an "insert
   disc" string from `SR2_MSG.dll` (id 2 or 3, depending on whether
   `SR2.CFG` was found) and either retries or gives up. It returns 0 for
   found. This is `nodisc`'s first site; the second is in the loader,
   below.

`SR2.CFG` is 100 bytes. It is read straight into the settings block at
`[0x50afe0]` (`0x427740`) and written back at shutdown (`0x427880`):

| Offset | Field |
| --- | --- |
| `0` | the DirectDraw device name (`display`, the primary). `0x426ec0` looks for it among the enumerated devices and zeroes the block when none matches |
| `0x20` | five DWORDs. `+0x28`, `+0x2c` and bits 1-2 of `+0x30` are capability flags, recomputed at each start from the device's video memory (thresholds `0x426fb8`-`0x4270ac`). The rest are `LAUNCH.EXE`'s options |
| `+0x50` | the 640x480 / 800x600 choice. The loader switches to the `BINDATA\800x600\` asset set when `[[0x50afdc]+0x50] == 1` (`0x476512`) |
| `+0x58` | a copy of the live block's `+0x54` |
| `+0x5c` | the disc flag (below) |
| `+0x60` | the language from `GetUserDefaultLangID` (`0x4272b0`), set at every start (`0x427672`): 0 Japanese, 1 English (UK, New Zealand, Ireland), 2 English (others), 3 French, 4 Spanish, 5 German, 6 any other |

The in-game options live in `SR2_SAVE.DAT`. With *No registry* the
block's file is `SR2.DSP`.

### The loader

`0x476260` constructs the loader object. The object holds two prefixes.
`+0x108` is the exe's directory, from `GetModuleFileNameA` cut after the
last backslash. `+0x4` is the play disc's root, from the same drive scan
as above, done again here; it is empty if no disc is found.

`0x476a50` opens a file. It makes three tries, in order:

1. `<exe dir>BINDATA\<dir>\<file>`, a loose file (`0x4764e0` builds the
   path)
2. `<exe dir>BINDATA\<dir>.CAB`, a cabinet beside the exe (`0x476780`
   builds the name)
3. `<disc>BINDATA\<dir>.CAB`, the cabinet on the play disc

Cabinets are read through `cabinet.dll` FDI. Local files win, so a full
install never opens the disc for data.

### The disc flag

The mode select dims everything but MULTI-PLAYER, OPTIONS and EXIT when
`settings+0x5c` is 0. That flag is set at `0x42775f` (after `SR2.CFG` is
read) and at `0x426ef8`, as `isalpha(*root)`. `root` is the loader's disc
root at `+4`; `0x476ef0` returns its first byte. So the disc dependency
is two-fold: the startup check at `0x4273c0` decides the dialog, and the
loader's own scan decides the menu.

The `nodisc` patch handles both. The check returns "found", and the
constructor copies the exe directory into the root slot. The root's first
character is then a drive letter, so the flag is 1, and the loader's
third fallback looks for cabinets in the install folder. A UNC install
path (`\\server\...`) would still read as no disc. The same drive letter
is formatted into `%c:\AUTORUN.EXE` at `0x4277d0`; nothing in the exe
reads that buffer.

### RallyDebug.ini

The exe reads `RallyDebug.ini` from beside itself with
`GetPrivateProfileStringA` (`0x427c01`). The section is `[DebugSettings]`
and the keys are `DebugInfo`, `CourseCollision`, `CarCollision`, `CPUCar`
and `Course`. `DebugInfo` goes to `0x5a2688`, which nothing reads.

The overlay `Total:%5dKB Used:%5dKB Free:%5dKB Quality:%s FPS:%2d
TPF:%5d` (`0x428140`) is gated on `0x4e68f8`. That flag is set only when
a `DebugDLL.DLL` beside the exe loads and exports `NagaSp` (`0x427340`).
The overlay's one call site (`0x428107`) is on the branch taken only when
the flag is clear, so the overlay cannot draw in the retail build. It is
a leftover of the debug builds, in which the DLL did the presenting
(`0x428825`). There is no in-game frame counter.

### Frame timing

The game steps its simulation at 60 Hz. It times itself in `0x4287f0`,
which each frame's `0x4280a0` calls between the step and the draw. Init
(`0x427eef`) takes `QueryPerformanceFrequency` / 60 as the budget and
keeps it in the timer object at `+0x24`. `+0x28` says whether QPC is
there; `0x4287a0` reads the counter, with `timeGetTime` only as the
fallback. There is no `Sleep` and no `timeBeginPeriod`.

Each frame does the following:

1. It presents (`MGameD3D` `+0x80`).
2. If more than n budgets have passed since the last exit, it runs extra
   steps of the simulation without a draw, up to four (`0x428897`).
3. It spins on the counter until elapsed > n × budget (`0x4288f0`).
4. It sets `last = now`, so the overshoot is not carried.

n is `[0x4b2354]`, which is 1 or 2, taken from `settings+0x40` in
`SR2.CFG` at `0x41754b`.

In the stock game, in exclusive 640x480@60, the `Flip(DDFLIP_WAIT)`
blocked on the vertical blank, and the spin was the fallback. The
borderless `Blt` returns at once, so the pace is now set by the spin:
60.000 Hz on the counter, free-running against the display. `frametrace`
on Windows shows the game's own work at 1-2 ms a frame, the blit at 0.2
ms, and the spin taking the rest. It shows one catch-up a run, at the
race start. With managed textures it showed a hundred catch-ups a run
and 200-500 ms stage loads; that is why managed textures are not used.

The catch-up test is a strict "elapsed > steps × budget". So anything
that holds a present for a fraction of a frame costs a second simulation
step and a second budget of spin. The present must therefore not wait. A
wait for the vertical blank in the present did exactly that on Windows,
and is not there. `MGameD3D` `+0x54` (`0x10004d30`) is that wait, as a
method the exe never calls. On Windows the layer renders the frame after
the blit returns, on its own thread, so the loop never sees the render.

On Windows the patcher turns on dgVoodoo's `ForceVerticalSync` (the one
under `[DirectX]`; its default is off). Each frame then goes up on a
refresh, with no tearing, and on a display at a multiple of 60 Hz every
frame stays up equally long. The wait is meant to be dgVoodoo's, on its
thread, not the loop's. `frametrace` shows whether the wait ever holds a
present and costs a catch-up.

The gate reads four flags:

| Flag | Meaning |
| --- | --- |
| `0x4d6a3c` | running |
| `0x4d6a6c` | paused (the Start-button menu, `0x41932d`; the present is skipped too) |
| `0x5a2660` | the debug DLL |
| `0x4d6930` | catch-up allowed. The two-frame transition object of class `0x49b138` (`0x41a9e0`) clears it on its first tick and sets it on its second, which builds the next scene |

The `frametrace` diagnostic is described under *How each patch works*.

### Music

`MGAudio.dll` is the only user of `winmm`. It uses `mciSendCommandA` for
the CD and `mixer*` for the CD's volume. It opens the device by type ID
(`MCI_OPEN_TYPE|MCI_OPEN_TYPE_ID`, `MCI_DEVTYPE_CD_AUDIO`, at
`0x10003100`) and sets the TMSF time format. It plays with `MCI_FROM`
(track N+1 in the low byte, `0x10003160`), seeks to a TMSF it computes
from milliseconds (`0x100032f0`), pauses, resumes, stops and closes. It
polls `MCI_STATUS` for the position, the track count and each track's
length (`0x10003220`–`0x100032df`). The `MCI_NOTIFY` flag it sets on a
play goes nowhere: nothing in the game handles `MM_MCINOTIFY`. The
position is polled against `GetTickCount` bookkeeping around
`0x100023cf`, which is presumably how a course loops.

At "Go!" the exe seeks the course track to 0:00 with a track number one
below the one its play used, and sends no play after the seek. The hook
takes a seek to the open track, or to the one below it, as a restart.

The play disc's audio is tracks 2–14. In the Redump dump each track is
in its own bin with a 150-sector pregap at `INDEX 00`. The ripper starts
each track at `INDEX 01` and stops at the end of its file.

## How each patch works

The patches follow in the order of the table above. Rows that are a
single obvious byte edit are skipped. The widescreen patches have
[WIDESCREEN.md](WIDESCREEN.md) to themselves. Most patches install
assembled machine code rather than editing bytes; the sources, and a
longer account of each, are in [asm/](../asm/).

### No disc required

The patch has two sites, one for each place the game looks for the disc:
the startup check and the loader's own scan. *The disc flag*, above, has
the account.

### Replay freed once

The gallery's End (`0x100046c0`) frees the replay at `+0x50` of the exe's
block. When the gallery loaded the replay from a file, that block is the
gallery's own (`new` at `0x10003b65`). When the replay came from a race,
the block is MainMode's static buffer. Windows 9x's HeapFree refused the
static buffer and the game carried on; the heap since Windows 8 ends the
process for it. The `new` becomes a thunk that remembers the block it
returned. The `push eax; call free` becomes a thunk that frees only that
block. See asm/replayfree.asm.

### Texture release checked

The release of texture N (`0x10004430`) did not check N against the
count at `0x10012590`, though the create does. `VendorLogo.dll`'s End
(`0x100014e0`) releases texture −128, which is 512 bytes before the
table, and the release calls through whatever is there.
asm/texrange.asm adds the check.

### Survive ALT+TAB

The window procedure (`0x426b80`, registered at `0x426af0`) handles
`WM_ACTIVATEAPP` at `0x426bc5`. With the sound object at `0x50b12c`, it
calls `0x46e260` on activation and `0x46e210` on deactivation. Those are
the resume and pause of the sound (`thiscall`, with `ecx` the object).
Nothing restores the DirectDraw surfaces. `MGameD3D` has a routine for
that: slot 16 (`+0x40`) of its interface, at `0x10007710`, which does
`IsLost`/`Restore` on the primary, the back buffer and the Z-buffer. No
code in the game calls it. The exe holds the interface at `0x50b118`. So
after a switch away every flip fails and the screen stays blank. Two
patches fix this:

- the resume call goes through a stub that calls the restore method
  first;
- the restore method itself is rewritten as
  `IDirectDraw4::RestoreAllSurfaces` on the object at `0x1001254c`. The
  original restores three surfaces, and everything else DirectDraw owns
  stays lost.

The textures are the game's own. `MGameD3D` builds each texture as a
system-memory surface (`0x10004530`, caps `0x1800`) and a video-memory
twin (`0x10003ff2`; the descriptor comes from `0x10003e70`, with caps
`ALLOCONLOAD|TEXTURE|VIDEOMEMORY`, plus `NONLOCALVIDMEM` for AGP when the
hardware flag at `0x1001253c` says so). It fills the twin with
`IDirect3DTexture2::Load` (`0x100043f0`) and releases the system copy on
success (`0x10004385`).

A lost video-memory surface comes back empty from `Restore`. That is
DirectX's contract, and Wine keeps to it. So if a surface were ever lost,
the textures would come back blank until the next load. A task switch
from a window loses nothing, and no loss has been seen on Windows 10/11
or Wine. Managed textures (`DDSCAPS2_TEXTUREMANAGE`) would cover the
case, but the Windows DirectDraw layer's managed path is slow, with long
stage loads and runs of slow frames, so they are not used. If a loss
ever shows, the answer is to keep the system copy and `Load` again after
`RestoreAllSurfaces`.

The game now runs in a borderless full-screen window or a framed window,
so the stock exclusive display mode is gone. The two alt-tab patches
stay. `DDSCL_NORMAL` surfaces can still be lost, to another exclusive
application or a locked screen, and the restore on activation costs
nothing when nothing is lost.

### Z-buffer detach

`MGameD3D` keeps the back buffer at `0x10012554` and the Z-buffer at
`0x1001255c`. At four places it calls the back buffer's
`DeleteAttachedSurface(0, NULL)` with a literal null and ignores the
result: before it creates the Z-buffer (two init paths, `0x10002b25` and
`0x10002d05`), when it releases the Z-buffer (`0x10002920`) and at
teardown (`0x100037df`). DirectX 6 and Wine's ddraw answer the null with
an error code. Proton's ddraw dereferences the null, and the process dies
in the SEH handler before its window appears.

The four calls become `add esp, 0xc`, which leaves the stack as the
stdcall would have. Where the call returned an error, nothing changes. If
DirectX treated the null as "detach everything", the difference is a
Z-buffer that stays attached until the back buffer goes. That is a leak
at exit, not a fault.

### Missing lettering

`MGameD3D` enumerates the device's texture formats at `0x10003cf0` into
slots at `0x10012594` (0 P8, 1 X1R5G5B5, 2 R5G6B5, 3 A1R5G5B5, 4
A4R4G4B4, 5 P4, 6-10 DXT). It picks the default 16-bit format from the
list at `0x1000f79c`; the first slot present wins. Texture data is 1555
with bit 15 set on opaque pixels. For a 555 target the data is copied as
it is (`0x10004af0`); for a 565 target it is expanded, with bit 15
dropped (`0x10004bb0`). Every texture gets `SetColorKey(DDCKEY_SRCBLT, {0, 0})`
(`0x100046ce`, `0x100043d1`).

Opaque black is therefore `0x8000` in an X1R5G5B5 texture. Drivers of
the day compared the raw texel against the key and drew it. Modern
DirectX and wined3d mask the X bit before comparing, so the texel
matches 0 and is dropped. The visible result is that the black lettering
on the mode-select and car-select headings is gone, leaving the white
plate and a dashed grey anti-aliasing edge.

The list becomes `3, 1, 2`. With A1R5G5B5 first, bit 15 is alpha, which
is what the data is, and the key stays exact. The copy path is
unchanged: `0x1001273c` ("not 565") stays set.

### Invisible lobby text

Every mode DLL draws through MGameD3D. The only GDI text in the game is
the exe's, and all of it is in the multiplayer lobby: the name entry
(`0x420fa0`), the team and chat list (`0x435400`), the status line, the
timer and the IP list. The lobby uses one face, Courier New (MS Gothic
when Windows is Japanese, below), in three sizes, created at `0x435df4`,
`0x435e9b` and `0x435f33`.

The lobby's language follows Windows, not the install. The settings
block's `+0x60` is copied to `0x4edcd0` (`0x439269`). When that value is
not 0, the network screens load the `_US` bitmaps (`CONNECT2_US.BMP`,
`WINDOW1_US.BMP`, `MESSAGE_*_US.BMP`, `MENU_TITLE_US.BMP` and the rest)
over the Japanese ones, and the fonts are Courier New. Only a Japanese
Windows language shows the Japanese screens and MS Gothic. Both sets are
in *BINDATA 3*, except the chat menu's three `MENU_*_US.BMP`, which come
with *English Binary*. So a Japanese install on any other Windows
language does not have those three.

The lobby chrome is BMPs (`CHAT_*.BMP`, `MENU_*.BMP`) loaded into 16-bit
surfaces in the back buffer's format. The text goes onto them through
`IDirectDrawSurface4::GetDC`: the exe blits a strip of the background
into the surface, draws the buffer with `TextOutA`, draws the caret with
`BitBlt DSTINVERT`, calls `ReleaseDC`, then `Blt`s the strip to the back
buffer with `DDBLT_KEYSRC` and a key of black.

Every site sets the colour with `SetTextColor(dc, -1)`. Windows 95 took
the low three bytes and drew white. NT-family GDI and Wine read bit 24
as `PALETTEINDEX`, look up entry 0xffff in the DC's palette, fail, and
fall back to entry 0. That is black, which the keyed blit drops. The
caret survives, because it is an inversion, and it moves as the extent
of the invisible text grows.

The stub in the annex masks the colour to RGB and continues into the
import, so the sites keep their shape. The IME path at `0x421166` pushes
0 and is unaffected. See [asm/README.md](../asm/README.md).

### The lobby's panels

MGameD3D's offscreen surface create (`0x10007b30`) takes `dwCaps` from
the kind its wrapper carries at `+0x14`. Kinds 0 and 1 are system memory
(`0x840`), 2 is local video memory (`0x4040`), 3 is non-local
(`0x20004040`), 4 and 5 are the primary and the back buffer, and 6 is a
texture (`0x1800`). The team room's surfaces are kind 2: a `d3dtrace` of
the screen reports the background, the team list, the chat line, the
timer, the course box and the button icon all as `0x10004040`. The exe
draws its text into them through `GetDC`, which locks them.

With dgVoodoo 2's *Fast video memory access*, a lock of a video-memory
surface does not preserve what is already in the surface. The chrome
blitted into the panel is gone by the time `ReleaseDC` returns, so the
panel reaches the screen black with the text on it. The blit itself
returns `DD_OK`, and a `Lock` of the source reads the same black.
Turning the setting off is not an answer: without it nearly every
texture comes up white or as noise.

`surfmem` makes kind 2 system memory, which is what the connection
screen's panels already ask for. A lock of a system-memory surface has
nothing to discard. The texture path is kind 6 and is untouched. The
cost is that these blits become uploads, which a still screen does not
notice.

### Windowed

MGameD3D's init struct is built at `0x4214f0` and lives at `0x4d5e18`.
It carries a fullscreen flag at `+0x2c`, which the DLL copies to
`0x1001240c`. The exe passes a literal 1 (`0x427fe5`). With 0, the DLL's
own windowed path runs (`0x1000263c`). That path calls
`AdjustWindowRectEx` and `MoveWindow` for a 640x480 client area, sets
`SetCooperativeLevel(NORMAL|FPUSETUP)`, creates a primary in the
desktop's format with a clipper on the window, and creates an offscreen
3D back buffer (init path 2). The present at `0x10004d50` then becomes a
`Blt` of the back buffer to the window's client rect, which is a stretch
when the window is larger. The fullscreen path instead sets
`EXCLUSIVE|FULLSCREEN|ALLOWREBOOT|FPUSETUP`, calls
`SetDisplayMode(640, 480, 16)` and presents with `Flip`. The window class is `WS_POPUP`
(`0x426b25`), so the window has no frame.

Three things stood in the way of the windowed path.

**The mode check.** Before it sets the cooperative level, windowed or
not, Init runs `EnumDisplayModes` (`0x10002eb0`). Its callback
(`0x10002f10`) looks for the init struct's width, height and depth,
640x480 at 16 bits, and Init fails the start with `E_FAIL` when no
listed mode matches. The window sets no mode, so in the windowed path
the check serves nothing. On one Windows 11 machine (NVIDIA, driver
610.62) DirectDraw lists no such mode: the `d3dinit` log shows the
enumeration succeeding and the match flag clear, twice, as the exe tries
the bring-up again. `anymode` makes the result `S_OK`:
`and eax, 0x80004005` becomes `and eax, 0`, four bytes. In fullscreen an unlisted
mode would then fail at `SetDisplayMode` with the same box, so nothing
is lost.

**The size of the target.** `IDirect3D3::CreateDevice` (`0x10003080`, on
the back buffer) returns `DDERR_INVALIDOBJECT` (`0x88760082`) on
Windows' own DirectDraw for a back buffer wider or taller than 2048. The
`d3dinit` log shows the surface and its Z-buffer created at 2560x1440
and the device refused (`0x2313`). 1920x1080 goes through, and
2560x1080 fails on the width alone. The line is the same whatever the
driver reports: AMD gives `dwMaxTextureWidth/Height` as 2048 in the
device desc, one NVIDIA machine gives 16384, and both refuse at 2048.
Making the device on a 64x64 dummy and pointing it at the back buffer
with `SetRenderTarget` (`0x10002d64`, which the DLL itself calls) does
not help: the runtime refuses the target there as well. So on Windows
without the dgVoodoo 2 add-on, the resolution table the patcher writes
stops at 2048 a side (WIDESCREEN.md, *The setting*), and the present
stretches the picture into the window. wined3d has no such line, and
neither do the D3D7 wrappers; those get the full table.

**dgVoodoo 2.** dgVoodoo 2 runs the game once its `ddraw.dll` is in
`MUSASHI\` and its `D3DImm.dll` is beside the exe (above). The patcher's
`dgvoodoo` add-on fetches the latest release from GitHub (the release
API, then the `dgVoodoo2_*.zip` asset) and places those two files, with
a `dgVoodoo.conf` beside the DLL, where dgVoodoo looks for it first. The
conf turns fast video memory access on, turns the watermark off and
leaves ALT+ENTER to the game. The release is stamped in
`MUSASHI\dgVoodoo.version`. The add-on is on by default on Windows
proper; the patcher tells Windows from Wine by `ntdll`'s
`wine_get_version`. dgVoodoo's device desc gives the largest texture as
2048x2048 whatever the backend allows. Its texture format enumeration
gives every format the game's list holds except P4 (`fmt 00001fdf`), and
A1R5G5B5 is chosen as on Windows. With *Fast video memory access* off,
the textures come up white or as noise. With it on, the game draws as it
should, somewhat slower than on Windows' own DirectDraw. The multiplayer
lobby's background came out black inside the 4:3 box, with the panel and
the side colour right. The reason is that dgVoodoo blits the game's
video-memory background surface as empty, with DD_OK, while a `Lock` of
the same surface reads it whole. The lobby copies the surface through
`Lock` when it finds that (WIDESCREEN.md, *The lobby*). `surfmem` puts
that surface in system memory, where the blit carries it, and the copy
stays as a fallback. The same setting is what blanked the team room's
panels (*The lobby's panels*, above).

A start that died in a refused re-init (window moved, surfaces made,
device refused, error box) left Windows' display stack wedged on two
machines until a reboot or `Win+Ctrl+Shift+B`. After it, every
DirectDraw window presented at 3 fps, and `EnumDisplayModes` stopped
listing 640x480x16, which is the case `anymode` covers.

**The depth check.** The windowed path calls `GetDisplayMode` and refuses
a desktop whose depth is not the 16 bits it was asked for (`0x1000271e`;
the `E_FAIL` becomes "Failed to initialize"). Nothing after the check
depends on the depth, because every surface takes the primary's format.
`anydepth` skips the check.

**The `.bg` pictures.** The full-screen pictures (title, loading, game
over, the course cards; all `.bg` files) are 16-bit 565. The game copies
them straight into the locked back buffer row by row (`0x415271`,
`rep movsd`). The loader at `0x415180` converts 565 to 555 in place when the
lock's green mask says so, and a 32-bit mask also says so. On a 32-bit
desktop the row copy put two pixels' bytes into each pixel, so the
picture came out at half width.

The copy is now `bgrow.asm`. It reads the lock's description (`0x4e6878`:
size, pitch, surface, `dwRGBBitCount` at `+0x54`) and expands 565 to
XRGB8888 when the depth is 32. When the surface is not the picture's
size (a wide picture size), it composes the whole picture on the first
row into a surface `MGameD3D` keeps, so that one blit can stretch it
into the screen, and it draws nothing on the rows after (WIDESCREEN.md,
*The .bg screens*).

`Title.dll` carries its own copy of the same loop for `TITLE640.BG`
(`0x100014ba`; that copy keeps the lock description on its stack and
advances the source at the end of the loop). It gets the same stub,
assembled for that layout (`titlebg`). The `.bg` path with brightness or
contrast set goes through `0x46c900` instead and is untouched. No other
screen DLL locks the back buffer and copies into it: the lobby goes
through DirectDraw blits, and the rest goes through Direct3D.

### Borderless

The windowed path sizes the window to the picture, with `MoveWindow` at
`0x100026be` after `AdjustWindowRectEx`. It presents by blitting the back
buffer to the client rect, and DirectDraw stretches the blit.
`fullwin.asm` replaces both ends: the window sizing and the present.

**The window.** The `MoveWindow` call goes to a thunk that moves the
window to the monitor under the cursor. The thunk uses `GetCursorPos`,
`MonitorFromPoint` and `GetMonitorInfoA`, resolved through the DLL's
`LoadLibraryA` and `GetProcAddress`, because the DLL imports none of
them. If any of those calls fails, the thunk leaves the window where the
game asked. A framed window (the player pressed ALT+ENTER) is left as the
player has it. This matters because the init, and with it this call,
runs again on every screen change: the game tears the renderer down and
brings it back up between screens (`SetClipper(NULL)`,
`SetCooperativeLevel`, a new primary, clipper and back buffer). Once the
thunk has placed the window, it goes by the monitor the window is on
(`MonitorFromWindow`) rather than by the cursor. So a borderless window
that ALT+ENTER put on another monitor stays there through the next
screen.

A `WS_POPUP` window the size of its monitor is what Wine reports to the
compositor as fullscreen, and there is no display mode behind it to
restore on activation.

**The present.** From `0x10004d7b` on, the present is replaced by one
that fits the back buffer's aspect into the client rect, fills the bars
with `DDBLT_COLORFILL` and blits the picture into the middle. The picture
is still 640x480, point-sampled up, until a wide size is chosen. The 96
bytes of the old present carry nine relocation entries, and the call
carries one. All ten go, because the bytes are either dead or relative.

**Another monitor.** The game creates DirectDraw on the default device
(`DirectDrawCreate` with the null GUID, `0x10002da0`). That device's
primary surface is the primary monitor. On Windows the other monitors
are separate devices. On Wine, `ddraw` sizes its front buffer to output
0, and `DirectDrawCreate` takes no other. A blit whose destination leaves
that surface fails. Wine's `wined3d_texture_blt` refuses the rect and the
window stays white; Windows with dgVoodoo 2 drew black with a strip of
garbage. So a window that ALT+ENTER had put on a second monitor, or that
had been dragged across the edge of the first, showed nothing. The
present now checks the client rect against
`GetSystemMetrics(SM_CXSCREEN, SM_CYSCREEN)`, the primary monitor's size.
When the rect leaves the primary monitor, the present goes through GDI
instead: `IDirectDrawSurface4::GetDC` on the back buffer, `StretchBlt`
(`COLORONCOLOR`) into the window's DC, `PatBlt(BLACKNESS)` for the bars,
and `ReleaseDC` on both. The six entry points this needs are resolved on
the first present, together with `QueryPerformanceCounter`. If any is
missing, the DirectDraw blit is kept. On the primary monitor nothing
changes. GDI costs a readback of the back buffer and a software stretch
per frame, which is fine for 640x480 into 1440p. Whether dgVoodoo's
window takes GDI drawing over its swap chain is untested.

After its blit the present stores the counter value in the annex, for
`frametrace`. The annex is writable for that store.

### Frame log

`frametrace` is a diagnostic applied by name. It hooks the gate's entry
(`0x4287f0`, `mov eax,[0x4d6a3c]`) and its exit (`0x42890b`, the five
bytes before `pop ebx; ret`) and logs every drawn frame to
`logs\frames.log` beside the exe. Each line holds the counter at the
entry, the counter after the borderless present's blit (found through
the borderless patch's jump at MGameD3D's present), the counter at the
exit, the step count and the gate's four flags (*Frame timing*). A header
line gives the budget and which counter is in use.

`tools/frames.py` reads the log and splits each frame into work (step
and draw), blit and rest. An interval of two refreshes with two steps is
the catch-up. An interval of two refreshes with one step is either a
present the display held or a frame the game chose not to catch up. The
step count logged is `ebx`. In the Australian exe `ebx` is the divisor's
countdown; that build's count is in `edi`. DEVELOPING.md says how to
apply the diagnostic.

### ALT+ENTER

The window procedure has cases for a handful of messages and hands the
rest to the text-input handler at `0x41fe20` (the `call` at `0x426cbc`).
The handler's -1 means "not handled", and the procedure then goes on to
`DefWindowProcA`. That call now goes through `altenter.asm`. A
`WM_SYSKEYDOWN` for `VK_RETURN` with bit 29 of lParam (ALT) set and bit
30 (a repeat) clear toggles the window and answers 0. Everything else
continues to the handler.

The toggle sets the style with `SetWindowLongA`: `WS_OVERLAPPEDWINDOW`
for framed, `WS_POPUP` for borderless, with `WS_VISIBLE` kept. It then
places the window with `SetWindowPos(SWP_FRAMECHANGED)`. Framed, the
window gets a client area of the picture's size (from the init struct at
`0x4d5e1c`), centred on the monitor the window is on. Borderless, it gets
that monitor's rect. The present letterboxes into whatever client rect
results, so the framed window can be resized or maximised. The five
user32 entry points are resolved once through the exe's `LoadLibraryA`
and `GetProcAddress` and kept in the section, which is therefore
writable.

`windowed` and `borderless` are the game's mode and cannot be left out.

### No mixer needed

Australian only. `MGAudio.dll`'s Init looks for a CD line on the mixer,
for the volume slider. Without one, the European DLL returns `S_FALSE`
and the Australian DLL returns `E_FAIL`. Wine has no such line. The
`jne fail` becomes a jump to a stub that zeroes the control count at `+0x84`
(which is uninitialised until the search fills it) and zeroes eax, then
jumps back to the allocation.

### The mix

The sound manager lives in the exe and, as a copy of the same code, in
every screen DLL. It gives each effect a −40..0 dB range and sets the
effect's ceiling at `(step+1)/10` of that range from the slider: 4 dB a
step, 0 dB at 9. The CD music followed a curve of its own, in amplitude.
The streamed music had a range of its own. So a step meant something
different on each slider.

`asm/mix.asm` puts every buffer on one curve. The buffer's `SetRange`
(`0x10004380`) loads its min and max through the first routine, which
maps each onto `MIX_MIN..MIX_MAX` from `asm/mix.inc`, −43..−8. That is
3.5 dB a step, with step 9 landing where the old step 7 did, for every
client. For the streamed music, every client ends in the streaming
buffer's `SetVolume` (`0x10006940`) with the step × 1111 as a 0..10000
value mapped across the stream's own range. That mapping now finishes
through the second routine, which puts the step on the same curve plus
`STREAM_DB` (200); 0 is off. The CD music's level is set by the music
hook, below, on the same curve plus `CD_DB`. `tools/loudness.py`
measures the two musics against each other, for setting those two
offsets.

### Quieter defaults

The settings the game starts with are a block of 0x29 dwords in the exe
(`0x5a2348`, `STATUSDA`). At start (`0x427b6c`) the block is copied into
the live settings (`0x4d6d50`, `[0x50afdc]`); the saved options replace
those once there are any. The block is also kept as `[0x50b10c]`, and
every Options page's DEFAULT reads it back from there (`Options.dll`
`0x10005143` takes `+0x58` to `+0x68`). The three volume sliders are the
block's `+0x60`, `+0x64` and `+0x68`, each 9, the top. `voldefault` makes
them 6. A first start, or DEFAULT, then sits 10.5 dB below the top on the
mix's curve. The block is the same in every build.

### Effects at full

Australian only. The volume routine sets each effect's ceiling from its
slider and then sets the effect's level as a percentage of that ceiling.
The other builds pass 100 as the percentage. The Australian build passes
the slider × 11, so the slider is applied twice. It does this in the exe
and in its `Options.dll`, which re-applies the volume on the way out of
the screen. The setting's load becomes `mov eax, 9`, which the × 100 ×
0.111 after it makes 100. In the DLL the load's relocation entry goes
with it. The percentage is also how every build drives the engine's
level by throttle, so it stays a percentage.

### Music from files

*Music*, above, says what the DLL does with the CD. Three properties of
the DLL shape the patch:

- The open routine (`0x10003100`) does not call through the import slot.
  It loads the slot into `esi` and calls `esi` twice, once for the open
  and once for the time-format set. So there are twelve sites to
  rewrite, not eleven: the calls go to the hook, and the load goes to a
  thunk that returns the hook's address. If the load were left in place,
  it would send the open to the real driver. The first status the real
  driver answered with `MCIERR_UNSUPPORTED_FUNCTION` would then make
  MGAudio close the device.
- MGAudio issues its MCI commands from threads it creates per action
  (`CreateThread`, `TerminateThread`). Wine's `winmm` refuses commands to
  a device from any thread but the one that opened it
  (`MCIERR_INVALID_DEVICE_NAME`, `0x107`). The hook therefore makes every
  device call from one worker thread of its own.
- The tracks play from a DirectSound buffer of the hook's own, not
  through MCI's `waveaudio`. The reason is the slider. `mciwave` exposes
  no handle, and winmm's volume (`waveOutSetVolume` by device id, and by
  handle too) has been the application's audio-session volume on Windows
  since Vista. It moved the DirectSound effects with the music, and it
  muted them every time the game sent 0. The game sends 0 between the
  loading screen and the start signal, and in Time Trial until the
  start. Wine treats the same calls as the wave device's, which is why
  the music played correctly there. A buffer's volume is its own on both
  systems, and it is in the mix's units.

The DLL is relocated on every load, because `SR2_MSG.DLL` holds its
preferred base. Each rewritten site carried a `.reloc` entry for the
absolute slot address at `site+2`. `apply_music` drops those entries;
otherwise the loader would add the relocation delta into the new relative
displacement. `tools/musictest.py` relocates the image before running it
for that reason.

**The volume.** The CD-volume methods' entries jump into the blob. The
slider's step becomes hundredths of a dB on the mix's curve plus `CD_DB`
(300), which is −5 dB at 9, and is set on the track's DirectSound buffer.
The exe's fade before a stop goes from full down by 10% a frame; the blob
takes it as an amplitude percentage of that level. The `cdlevel` patch is
what tells the menu's level call from the fade. The menu's CD-level set
at `0x473c48` pushed flags 0, and now pushes `0x40`, a bit the DLL never
read. The race's level and the mute already carry bit 31. The full
account is in [asm/README.md](../asm/README.md), *music.asm*.

### Device Settings

This patch adds a fourth item to the Options menu and the page behind
it. *The Options screen*, below, describes it.

### No registry

The game has one file name string `SR2.CFG`, used for the read at
`0x427740` and the write at `0x427880`. It becomes `SR2.DSP`, so the
game's 100-byte display block (*The install contract*) keeps a file of
its own in the stock shape, and `SR2.CFG` is the controls text from byte
0. `carry_display_block` copies a stock `SR2.CFG`'s block into `SR2.DSP`
at patch time, once. `write_settings` then writes `SR2.CFG` with the
sections the applied patches read: the controls for `xinput`, `[Display]`
for `resolution` and `[Network]` for `netplay`, laid out as the pad annex
expects them. It writes the whole file when there is none, or when the
file holds only the block; otherwise it appends a missing section to the
text. `MGameReg`'s Open at `0x47ef59` (21 bytes) becomes `xor esi,esi`,
so `Software\SEGA` is never created. *The registry* and *Gamepad* have
the rest.

### HUD after the water

The tachometer's plate is alpha-blended. It is drawn with the rest of the
HUD (`0x429d70`, called from the race state's draw at `0x418ab1` while
the state's `+0x3c` says so) after the scene pass, at z `0.0002` with the
z-write on. The lake (WIDESCREEN.md, *The sea*) is not part of that pass.
It is a node of the root tree, which the frame object draws afterwards.
The frame (`0x4280a0`) runs the state's draw, then, when `[0x4d6a3c]` is
set and `[0x4e68fc]` is clear, a `BeginScene` and the tree draw
(`0x470ff0` at `0x4280f2`), then the present. The lake is a screen-space
plane at z `0.96`–`1.0`, z-tested, meant to show through the hole in the
ground mesh. Under the plate it fails the z-test, so the plate blends
over what the scene pass left there: the backdrop's flat grey. A
`d3dtrace2d` with the `sr2 p` present markers shows the order in each
frame: the HUD's lists, the sea's four strips, the present. The stock
game does the same. The Australian build has no `[0x4e68fc]`.

`hudlast.asm` moves the HUD after the tree. It has three entries:

- **state**, in place of the HUD call. When the tree is not going to run,
  because the game is not running (a paused race) or the flag is set, it
  draws the HUD there as before. Otherwise it draws nothing and notes the
  HUD as pending.
- **late**, in place of the tree draw. It draws the tree. Then, if a HUD
  is pending, it sets the full viewport through the exe's own wrapper
  (`0x46bfd0`, with the rect at `0x4b12f0`, as the state's draw did
  before the HUD in split screen), draws the HUD, and makes the reset
  that the state's draw made after the HUD (`0x46cec0`: colour key and
  blending off, on the renderer at `0x50b110`). It goes by the pending
  note, not by the state's own flag, so a state of another kind never
  gets the race's HUD.
- **fade**, in place of the fade node's draw thunk. The fade is a node of
  the same tree (class vtable `0x49b644`). Its update (`0x426860`) takes
  the colour and alpha from the node's bytes at `+0x18`. Its draw
  (`0x426930`) is `mov ecx, [0x50b110]; jmp 0x46bd80`, the renderer's
  fade quad over the rect at its `+0x5650`, with the alpha at `+0x5668`;
  nothing is drawn at alpha 0. The quad is at z `0.00014` with the
  z-write on, under the HUD's `0.00024`. So a HUD drawn after the tree
  failed the z-test under the quad and appeared on the frame the fade-in
  ended, seventeen frames into a race in a `d3dtrace`: a pop. This entry
  draws a pending HUD first and then the fade, so the fade stays over the
  HUD as it did. *late* then only draws a HUD the fade node did not.

`tools/hudlasttest.py` runs the three entries under Unicorn with the
exe's routines stubbed.

### Loading screens

The stage's card (`des_AC.bg` and the rest, or `loading.bg`) is an object
the exe creates when the loading screen opens. `0x41a6f0` picks the file
by course and mode and does a `new` of 12 bytes with the vtable at
`0x49b138`; the object is kept at `0x4d6938`. The exe deletes the object
the moment the course has loaded, in the state step at `0x4195b0`. That
step does `call 0x418070`, the deleting destructor through the vtable's
first entry, zeroes the object, and does `inc dword [ebx+0x14]` to move
on to the next state. A load that took a while on the hardware of 1999
takes well under a second now, so the card is gone before it is seen.

`loadhold.asm` replaces two six-byte instructions with calls into its two
entries: the store of the new object at the create (`0x41a7bb`,
`mov [0x4d6938], ecx`) and the load of it at the step (`0x4195be`,
`mov ecx, [0x4d6938]`). The first entry makes the store and notes `GetTickCount`,
which all four builds import. The second entry waits, `Sleep(10)` at a
time, until 3000 ms have passed since the note, then makes the load.
`Sleep` is resolved once through `GetProcAddress`.

The wait is a plain sleep. The game's loop does not run meanwhile, and
the picture stays on screen as the last frame presented. The wait is
skipped when no note was taken, so the other path that deletes the
picture (`0x419d00`, an aborted load) is left alone.
`tools/loadholdtest.py` runs both entries under Unicorn with the clock
and `Sleep` stubbed.

### The connection screen

The multiplayer lobby's first choice (`0x43c160`, art in
`BINDATA\connect\PROTOCOL\`) is IPX, TCP/IP, MODEM or SERIAL.
`CONNECT.BMP` is the panel, with the four labels baked in grey. The
drawer at `0x43bd30` blits a 218x32 button over each label, at y 54,
106, 158 and 210. The button is `CONNECT_<row>_OFF`, `_ON` or `_ON2`,
chosen by the cursor through the table at `0x4b4274`: five rows of four
surface indices for the ON states, and five more from `0x4b42d8` for the
ON2 flash of the confirm. The cursor (`0x4edcc0`) wraps in 0..3. The
confirm stores the cursor as the connection type at `0x4eace6`, then
goes to the modem screen for type 2 and to the session list otherwise.
`OpenConnection` maps the type to the DLL's kind (`0x43fff0`). It takes
the modem's latency as 10000 ms and the other types' latency from
`GetCaps`. SHOW TEAMS dispatches on the type through `0x43efd8`: the IPX
row searches at once, and TCP/IP goes through the IP entry.
[NETWORK.md](NETWORK.md) has the rest.

With `lobby` the rows are INTERNET, DIRECT IP and LAN. They occupy the
IPX, TCP/IP and MODEM slots, types 0, 1 and 2, at y 82, 134 and 186:
three rows at the stock pitch, centred in the panel (`LOBBY_ROWS`). Row
1's y of 134 does not fit the drawer's `push imm8`, so that blit is
re-encoded in place: its `add esi, 4` goes, `push 0x86` takes the room,
and the next blit reads `[esi+8]` instead. The fourth blit is jumped
over. The cursor wraps in 0..2. The confirm's modem check (`cmp eax,2`
and the modem screen's address, fifteen bytes) becomes
`cmp eax,1; je; mov [0x4edccc],1`. That store sets the flag the list's first state
(`0x43f210`) searches on, the same flag the IP entry sets for its own
search, so INTERNET and LAN open the list already searching. The latency
test's `jne` becomes a `jmp`, so the latency is read for every type. The
SHOW TEAMS table's third entry becomes a copy of its first.
`tools/lobbytest.py` runs the confirm under Unicorn. The SHOW TEAMS
button itself is relettered SEARCH. Its three files in
`BINDATA\connect\button` (105x19, 24-bit, a 102x16 face and a bevel) are
rewritten with E, A, R and C cut from `create_*` and S and H cut from
`showteam_*`, centred at the stock letter gap (`lobby_buttons`). The
stock files are checked by digest first and kept as `.bak`.
`tools/buttonstest.py` pins the result. `MPDATA.DAT` keeps the type from
last time; a stock 3 there is reset to 0 at patch time.

On DIRECT IP, SEARCH puts up the IP entry (`0x43cd30`). The text is
edited at `0x4d3d1c`, with 18 characters shown of 2048. On OK it is
`lstrcpyA`d to the settings at `0x4eacec`, a 16-byte slot with the modem
number's 32 bytes after it, so a long entry ran over the settings block.
The OK (`0x43ca20`, at `0x43cb4e`) compared the length with zero and
then copied; a blank entry meant DirectPlay's broadcast, which is now
the LAN row. That compare is now a call to asm/ipcheck.asm in the annex.
The stub accepts a dotted quad, or a name of letters, digits, dots and
hyphens, with an optional `:port` of 1 to 65535, and 47 characters at
most. Anything else is refused with the cancel sound (`0x1c` at the
popup's sound call, `0x43cbac`), and the popup stays up.
`tools/ipchecktest.py` runs the stub on the real exe. The popup's
bitmap, `BINDATA\connect\IP_ENTRY\Ip_entry_US.bmp`, said under the box
that a blank entry searches. Those two lines are painted over, and two
lines on the address form and the port are drawn from a mask
(`lobby_popup`). The stock file is checked by digest and kept as `.bak`.
The face is Liberation Sans Narrow Bold at 17.5 px, 90% wide, with half
a pixel of tracking, fitted to the stock lines by overlap.

The same entry widget serves every text field in the lobby. Its
character handler took up to 0x800 characters (`0x41fef1`, `0x420849`)
whatever the field. The OK then `lstrcpy`d the text into a slot of 16
bytes (the address), 36 bytes (the team name, `0x4ead1c`) or a chat
message. Only the driver name's OK checked the length (20, `0x43acd1`).
asm/entrycap.asm sits in the widget's init (`0x420f10`, in place of its
first two loads) and keeps a cap chosen by the field's address: 47 for
the address, 35 for the team name, 255 for the chat line and 20 for the
driver name. The driver name shares the chat's buffer, so it is told
apart by the width shown. The two compares against 0x800 call the stub
instead. CTRL+V (`0x420337`, `0x420c4c`) `lstrcpyA`d the clipboard into
the buffer at the cursor with no check, past the buffer's 0x830 bytes and
past the entry's length and cursor, which follow the buffer. A pasted
paragraph died in the heap's checks. The `lstrcpyA` and the `lstrlenA`
after it become one call to the stub's third entry. That entry copies up
to the room the cap leaves, drops characters below a space, and returns
the count copied. `tools/ipchecktest.py` covers both.

On DIRECT IP only, the team room's init prints `IP Address :` and up to
three addresses from `gethostbyname` (`0x43604b`-`0x43611c`, `TextOutA`
at (150, 456)). asm/status.asm is called in place of the `lea` that
starts that lookup. It asks the DLL's network object for the line (slot
`+0x38`, `Network_StatusLine`, NETWORK.md) into the same buffer and
continues at the draw. When there is no object or no line, it redoes the
`lea` and lets the exe print its own line.

A chat line is kept for the team room's list as `name>text` (`0x4350e0`,
on sending and on receipt). It is `wsprintf`ed into a block of
`(len + 0x13) & ~3` bytes, which is room for the text and a name of ten
characters. A longer name ran the line over the next heap block, and the
game died in the heap's checks a few lines later. `0x344e4` adds 64 to
the allocation, which is the DLL's name length.

The lettering is ITC Avant Garde Gothic Demi, 20 px capitals, spaced.
OFF is the ON at 98/255; ON2 is the ON under a glow. `tools/labels.py`
sets each new label in URW Gothic Demi, the face's free clone, at size
27 with 7 px tracking, and makes the glow as a Gaussian of σ 2.4 at gain
2. That reproduces the stock buttons within a pixel. It bakes the three
states into `sr2-patcher.py` as zlib masks (`LOBBY_LABELS`, 7 KB), so the
patcher needs neither Pillow nor the font. At patch time the patcher
writes the nine button files as 24-bit BMPs and repaints `CONNECT.BMP`:
it clears the stock rows and paints the OFF masks at the new rows, a
pixel left of the blit (where the stock labels sit), through the nearest
of the palette's 41 greys. Each file gets a `.bak`. The SERIAL and OTHER
sets are not drawn and not touched.

### The starting box

START on the host, and the host's word (`0x2d`) on a guest, call the race
setup (`0x438dc0`, from `0x4373c8` and `0x4365bf`). The setup is a
routine that spins on `timeGetTime`. It waits up to 15 s for every
racer's state 0xa, then a guest waits a stagger of 0.5 s + 0.2 s × index,
then the clock sync sends a request a second for up to 15 s, then state
0x10 and its wait follow. Between looks it calls only the receive loop
(`0x438720`). So no frame is drawn, and the screen holds the room's last
frame while the setup runs. The game looks stuck.

asm/starting.asm stands in for the call. It puts a box on the screen for
the wait. The stub takes a DC on the room's background (`[0x4eade0]`, the
surface the strip's `IP Address :` went on) through MGameD3D's wrapper
(`GetDC` at `+0x28`, `ReleaseDC` at `+0x2c`). It draws the box in the
middle of that surface, the way the game's own popups look: a white
border, a fill of near black, and `STARTING THE RACE` over
`WAITING FOR THE OTHER PLAYERS` in white, centred in the lobby's font
(`[0x4e84c4]`).
The fill is never pure black, because the wrapper's blit keys black out
when a surface has a key. The box is sized from the two lines' extents
and centred on the width and height in `[0x4eaea0]`. The stub notes the
box's rectangle and raises a flag. It then blits that rectangle alone
from the background to the back buffer through the wrapper (the target
at `+0x34`, the blit at `+0x1c`). Under `widescreen2d` the Blt hook lands
that blit on the lobby surface, over the room's last frame with its names
and chat, and the present stretches it. The stub then calls MGameD3D's
present and the call the gate makes after it (`+0x80` and `+0x88` on
`[0x50b118]`), and jumps to the setup, which returns to the original
site.

A guest's setup blocks until the race, so that one frame is what the
guest sees. The host's setup returns while the guests load, to a room
that draws on (the fade to the race). The room draws in six registered
layers (`0x435f57` to `0x435faa`), the background first and the panels
over it, and those layers would bury the box. So the frame gate's present
call (`0x428835`, `push eax; call [ecx+0x80]`; the Australian gate has
two of them) goes through the stub's second entry. While the flag is up,
that entry blits the box's rectangle again, over everything the frame
drew, and then presents.

The third entry sits over the first eight bytes of the lobby's surface
loader (`0x406fa0`). Every lobby screen's init calls that loader for its
own surface set, into the same table (`0x4eade0`). The entry takes the
flag down, because the surface the box was drawn in is gone with the
room, then does the displaced bytes and continues into the rest of the
loader. A flag left up drew the next screen's backdrop as a blank
rectangle.

gdi32 is resolved once through the import slots. Without gdi32, a
surface or a DC, the first entry goes straight to the setup.
`tools/startingtest.py` runs the three entries under Unicorn on every
build, with the surface, the present, the load and gdi32 stubbed.

### The clear's height

Australian only. This build's mode setter clears the back buffer with the
width for both dimensions. At `0x441783` it loads `[WIDTH]` and pushes
that same value twice into the clear at `0x441180`. Europe's caller
(`0x421a75`) and America's push the height as the first argument. The
Australian clear therefore zeroes width rows of a surface that has
height rows. At 640x480 that is 160 rows past the end, which on a real
card landed in whatever the driver had left there. At 5120x1440 it is
some three thousand seven hundred rows past the end, and under wined3d
the first frame takes a page fault: the `rep stosd` at `0x4411ce` writes
off the end of the surface, with ebx the row's 0x2800 bytes and esi
still counting down from the width.

The `clearsize` patch puts a thunk in the annex that hands the clear the
two globals the right way round, the height first, as Europe's caller
does. The site becomes a call to the thunk. The thunk pops its return
address, pushes the two values, puts the return address back on top and
jumps into the clear rather than calling it. The clear is cdecl and this
caller cleans up at `0x441794`, so a thunk that called the clear and
returned would leave the width where the return address belongs.
`tools/clearsizetest.py` walks it.

### Gamepad

A pad binding goes in where the key it stands for enters the game, and
the keyboard is left as it was. A key the input wrapper reads as a bit
gets the pad in the wrapper, where every screen that reads the bit sees
it (`pagepad`: Page Up and Page Down). A key that a screen takes from a
word of its own gets the pad in that word (`padmenu`: the multiplayer
screens' menu word; `replaypad`: the replay controls' word). A key the
game never reads as input gets the pad read where the key's effect is
used (`sortpad`: F6-F8 are accelerators, so the gallery reads LB and RB
itself). Each of these reads the pad through the page poll MGInput's
annex publishes (`PADPOLL`, through the shared `asm/padpoll.inc`). Each
takes an input past half its range as down, and does nothing when the
poll slot is empty.

`MGInput.dll` (`0x10000000`, relocated) reads every action. The European,
American and DigiCube/MediaKite releases share one build of it; the
Australian release has an older build with the same interfaces at other
addresses. Four patches touch it: `xinput`, `dinput8`, `nogeneric` and,
in the exe, `noregistry`.

#### The model

The exe's init (`0x47eff0`) makes a config per player, named `"0"` or
`"1"` at `+0xc`, attaches the keyboard device and loads the config
through `Persist` (vtable `+0x30`, `0x10007510`; flags bit 0 means save,
bit 1 means keep what is there). Player 1's config is loaded twice:
first unnamed and clearing (`0x47f094`), then named `"0"` and appending
(`0x47f0ca`).

An action is a `0x34`-byte record: an id, a repeat delay and rate in
frames, a deadzone and saturation in 0..10000, and up to eight source ids
that are ANDed, of which the first carries the value. The action's object
is `0x15c` bytes:

| Offset | Field |
| --- | --- |
| `+0x10c` | id |
| `+0x110`, `+0x114` | deadzone, saturation |
| `+0x118`, `+0x11c` | delay, rate |
| `+0x120` | the scaled value |
| `+0x124` | frames held |
| `+0x128` | the press event |
| `+0x12c`, `+0x130` | raw value and range |
| `+0x134`, `+0x138` | sources seen, their count |
| `+0x13c` | the ids |

Import and export are at `0x10008890` and `0x10008910`.

The action ids are: 0 accel, 1 brake, 2-5 up, down, left, right (the
menus, with repeat; 4 and 5 are also the steering), 6 shift up, 7 shift
down, 8 handbrake, 9 view, 10 enter, 11 escape, 12 start. Start is the
race's pause (`0x419306`) and a confirm in the menus, like 10. The
sources are: 1-0xff keyboard scancodes, 0x101-0x168 joystick, 0x201-0x20b
mouse. The device's poll answers them (`0x100056c0`,
`(this, source, &value, &range)`).

The config's update (`0x10007100`) has every record poll every attached
device, then finalises. `GetActionState` (`0x100078b0`) takes the largest
magnitude among an id's records, so a key record and a pad record for
one action coexist.

#### XInput

asm/padinput.asm is hooked at the load, the save, the update and the
device's poll. The Australian build has no poll method. Its record update
(`0x10008170`) calls a static poll per device type, so there the keyboard
poll's address in that dispatch (`0x100081a8`, `0x10007e40`, five
arguments) is pointed at the annex's own entry. A third entry,
`(source, &value, &range)`, serves the Device Settings page and is published at
`PADPOLL`.

The poll answers sources `0x300 + player * 0x40 + input`. The sixteen
buttons answer `0x80`/`0x80` like a key. The triggers answer over 255,
past the usual threshold. The eight stick halves are rescaled past the
player's deadzone to 0..10000.

The update hook refreshes the config's player first. Each side keeps an
XInput slot. When a side has none, it looks for the first free slot,
every 60 frames, and it clears its state when its pad goes. Side 1 looks
only while side 0 holds a pad. So when there is one pad, at the start or
plugged back in, it is player 1's, whichever side's look falls first.
Before that rule, a pad unplugged and replugged in the menu came back as
player 2's. A `+xinput` log showed why: side 1's look, a frame ahead,
took slot 0, and side 0 then skipped that slot as held.

#### DirectInput 8

The DLL made its DirectInput object with `DirectInputCreateA(hinst,
0x500, &out, NULL)` (`0x1000294d`, through the thunk at `0x10008a30`,
which is the one `DINPUT.dll` import). It took `IDirectInput2` from that
object (`0x10002963`) and kept it at `+0x10` of the input object.
`EnumDevices(0, cb 0x10002300, &vector, ATTACHEDONLY)` at `0x100025e1`
collects every attached device, one `DIDEVICEINSTANCE` at a time, with
no type filter. The device init (`0x10003910`) calls `GetDeviceInfo` and
`GetCapabilities` and asks each device but the keyboard for
`IDirectInputDevice2` (`0x100039c2`).

That enumeration runs through Windows' legacy `dinput.dll`. That is where
the starts that hang on a white window with certain HID devices go
wrong; `dinput8.dll`'s enumeration does not. DirectInput 8's objects
carry the same vtables. `IDirectInput8` matches `IDirectInput2` slot for
slot, with `CreateDevice` at `+0xc` and `EnumDevices` at `+0x10` where
they were. `IDirectInputDevice8` is `IDirectInputDevice2` with three
methods appended. The enumeration flags and class values are the same
numbers, and `DIDEVICEINSTANCE`, `DIDEVCAPS` and `DIDEVICEOBJECTINSTANCE`
keep their DirectX 5 layouts. So the DLL's calls stand once the object is
DirectInput 8's.

asm/dinput8.asm makes the switch in three places:

- The create. The eighteen bytes of the call become a jump to the stub.
  The stub calls `DirectInput8Create(hinst, 0x800, IID_IDirectInput8A,
  &out, NULL)`, found once through the DLL's own `LoadLibraryA` and
  `GetProcAddress` slots, and returns the result at the site's
  continuation. A machine without `dinput8.dll` gets `E_FAIL`, as a
  failed create did before.
- The interface ids. The two in `.rdata` are rewritten to DirectInput
  8's, so the two `QueryInterface` calls succeed and hand back the same
  pointers as before.
- The device type. The one thing that changed meaning is the low byte of
  `DIDEVCAPS.dwDevType`. That is the device's kind, at `+0x260` of the
  device object. The DLL switches on it as 2 mouse, 3 keyboard, 4
  joystick (`0x10003490`, `0x10003570`, `0x10006550`), and carries it as
  the kind byte at `+0x24c` of the record the game and the Device
  Settings page see. DirectInput 8 uses 0x12, 0x13 and 0x14-0x18 for the
  controller kinds, 0x11 for a device of no kind, and 0x19-0x1c for a
  device control, screen pointer, remote or supplemental collection. The
  stub's second entry is called where the DLL first reads the byte: the
  `cmp byte [esi+0x260], 3` at `0x100039ac`, or in the Australian build
  the `mov edx, [esi+0x260]` at `0x100039f9`, that build having asked
  for `IDirectInputDevice2` before that point. The entry writes the old
  code over the new one and then does what the displaced instruction
  did, keeping the flags through the `ret`. Kinds 0x19-0x1c take the
  no-kind code, 1. The game can use such a collection no more than it
  can use a 0x11, and if they were left as joysticks they would take
  the slot the exe asks for by kind (`0x47f0a6`, joystick index 0) away
  from the pad itself. A device of no kind fails the DLL's own
  data-format and state lookups with `E_NOINTERFACE`, and its slot in
  the list stays null, which is the state a skipped instance leaves.

The instance copies in the enumeration vector keep DirectInput 8's
`dwDevType`. Nothing reads it; the loop over them (`0x100026ab`) looks
only at the instance GUID. This is what dinputto8 does for the DLL at run
time, done here once at the three sites. DirectInput wheels and pads go
on working through the same calls. `tools/dinput8test.py` drives the
DLL's own create routine under Unicorn against a stubbed `dinput8.dll`,
both with and without the DLL present, and drives the kind entry across
the type codes.

#### Devices of no kind

With the list enumerated, the loop at `0x100026ab` makes a device of
every instance whose GUID is not null: it calls `CreateDevice`, runs the
init above, and makes an object of the DLL's own, which is polled every
frame. On a machine of today that is a dozen things that can never give
input: LED controllers, a stream deck, an audio device's control
collection, a receiver's spare collections. The Xidi logs from the
repack's testers list them. Each is opened, and each is a place for a
driver to stall a `CreateDevice`. DirectInput 8 does not save the game
from that.

DirectInput 8 reports those devices as `DI8DEVTYPE_DEVICE`, 0x11, a
device of no kind, and asm/nogeneric.asm leaves them out. The loop's `je
skip; mov ecx, [esi]; push edx` after the null-GUID compare becomes a
jump to the stub. The stub makes the branch on the compare's flags, looks
at `dwDevType` (eax holds `guidInstance`, so the field is at `+0x20`),
and skips a 0x11 the same way the null GUID is skipped: the list keeps a
zero in that slot, which is a state the DLL already handles. Then it does
the two displaced instructions on the way to the continuation. The four
kinds above the controllers go the same way: 0x19 `DEVICECTRL`, 0x1a
`SCREENPOINTER`, 0x1b `REMOTE` and 0x1c `SUPPLEMENTAL`. `SUPPLEMENTAL`
is what a composite pad's spare collections come up as. An 8BitDo dongle
presents a gamepad, a keyboard, a consumer collection, a mouse and a
vendor collection, and only the first is a controller. Mice (0x12),
keyboards (0x13) and every controller kind (0x14-0x18, wheels 0x16 among
them) go through as before. The patch needs `dinput8`, whose type codes
these are. `tools/nogenerictest.py` enters the site as the DLL would, for
a null GUID, for each skipped type and for each kept type.

#### The store

The registry helper's load and save (`0x10008130`, `0x10008210`) become
the annex's own. The annex keeps a table of the key and pad input for
each action of each player, and the two deadzones, as text in `SR2.CFG`.
There is a section for each player and device (`[1P Controller]`,
`[1P Keyboard]`), holding `Name = value` lines for the eight driving actions
and `Deadzone = 10` in percent. The names are the page's names with
spaces as underscores; `-` means none. The `=` is optional. An unreadable
section header closes the section. Unreadable lines keep the defaults.
The deadzone clamps to 0-90%. A file with the game's 100-byte block ahead
of the text (from before *No registry* moved the block to `SR2.DSP`) is
read past the block.

A load generates the player's records. First come each action's key
record and pad record. Then come the menus' fixed records: the arrows
(WASD for player 2) on actions 2-5, and the D-pad and stick halves twice
over, once on actions 2-5 and once on the four actions the exe's screens
read (below). The bindable records come first, because the page takes
the first record as a row's. Only unnamed loads get records; otherwise
player 1's would double. A save takes the table back out of the exported
records (the first key source and the first pad source per action). A
name beginning `DZ` gives the digits after it as the deadzone. The save
then rewrites the text. The `[Display]` Resolution line and the
`[Network]` section (the netplay DLL's Staging and Log, 0 or 1) are
carried over as the file had them, and only when the file had them.

The menus' left and right are the steering's actions, so their fixed
sources are *menu-only*. A menu-only key is `0x400` + scancode, read from
the keyboard device's array at `+0x308` (the device whose type byte at
`+0x260` is 3). A menu-only pad input has bit 5 set. Menu-only sources
answer only while the exe's car table (`CARS`, `0x4d64bc`) has no car in
slot 0. The cars exist from a race's setup (`0x412aac`) to its teardown
(`0x412c67`), whatever the mode. Input `0x3f` reads a player's deadzone.

#### The menus' directions

The exe's multiplayer screens (the driver select, the connection screens
and the team room) test a word of menu flags. Bits 0-3 are up, down,
left and right; bit 4 is confirm; bit 5 is cancel; bit 15 is Enter; bits
13 and 14 are back. Two such words exist. The keyboard fills one
(`0x4d5e08`) from the exe's `WM_KEYDOWN` handler (`0x41fe20`: the
arrows, CR at `0x41feb3`, TAB and ESC at `0x42018f` and `0x420172`),
never through `MGInput`. The pad fills the other (`0x4edcb4`) from the
poll at `0x43f8e0`. That poll packs the input wrapper's button mask
(`[0x50b120] + 8`, vtable `+0x1c`). The mask is built each frame at
`0x47f2d0` by a fixed table of `GetActionState` calls, with ±5000 as the
threshold: action 10 (enter) goes to bit 0, 11 (escape) to bit 1, 12
(start) to bit 6 and 2-5 (up, down, left, right) to bits 9-12. The
packing `((m & 0x40) << 5 | (m & 0x3f)) << 4 | ((m >> 9) & 0xf)` turns
those into flags 4, 5, 15 and 0-3. The screens test both words
(`0x43bef0` in the connection screen, `0x437983` in the team room's menu
row, `0x436716` in its list).

So the directions are the steering's actions 2-5, where the fixed
bindings already put the D-pad and the stick. Confirm, back and Enter
are the enter, escape and start rows, whose defaults are A, B and Start.
The fixed set carries those three as well, menu-only, so a rebound pad
still confirms and backs out of those screens. A row's fixed inputs sit
beside whatever the row is bound to. The poll has a repeat of its own:
it clears the low four bits of the previous frame's flags every
`[0x4b5638]` frames, so a held direction re-triggers. `padmenu`, below,
takes that repeat out of play.

Three things keep a pad off the team room. First, in the team room the
wrapper's mask carries nothing from an XInput pad, so the pad word stays
empty. The connection screens do take the pad through the mask, and why
the room does not is not settled. Second, the room is two tasks. The
slot list (`0x4366b0`) takes up, down and confirm from either word. But
its way to the MENU row, a task it spawns (`0x437b10`) on TAB, is bit 13
of the keyboard word alone (`0x4366c9`), and the row's way back
(`0x437983`) is bits 13 and 14 of the same word. No pad bit reaches
those. The list's confirm with no chat typed opens the player's stat
card (`0x43684d`), which any key closes through bit 31 of the keyboard
word, `WM_KEYDOWN`'s mark (`0x4366bb`). No pad bit sets that either.
Third, the poll's repeat of a held direction runs at the keyboard's
rate: `0x43f880` takes the delay and rate from `SystemParametersInfo`,
and a held stick walks the rows two frames a step once the delay is out.

The `padmenu` patch (asm/padmenu.asm) goes around all three. The poll's
six-byte store of its level word at `0x43f94f` becomes a call into the
stub. The stub asks MGInput's annex for side 0's D-pad, left stick, A, B,
Start and Back through the poll the annex publishes at `PADPOLL`. That is
the page's poll, `(source, &value, &range)`, with sources `0x300` + the
input; down is a value past half its range. A, B and Start go into the
level word as bits 4, 5 and 15, and the wrapper's directions come out of
it. The pad's directions go the keyboard's way instead: into the
keyboard word as bits 0-3, on a change and then every 2 frames once the
direction has been held for 30. That is the walk `WM_KEYDOWN`'s repeat
gives a key. A bit in the keyboard word waits for the task that reads
and clears the word (`0x43687e`, `0x437a5c`, `0x43bb99` and the rest),
so no screen misses one. The edge word, by contrast, is made and cleared
by the frame: a pulse in it reached the connection screens only now and
then, and on those screens the wrapper's level bits ran the poll's repeat without
its delay whenever anything else was held. A press of Back sets bit 13
in the keyboard word, which is TAB to the list and back to the row. Any
press sets bit 31, which closes the card as a key would. Then the stub
makes the edge word again, against the stored previous level, because
the exe made its edge at `0x43f94b`, before the site, from a level
without the annex's bits. Then it does the three stores. With the poll
slot empty, the exe's own edge is stored as it is. The poll runs only
from the multiplayer controller (`0x43fcd9`), so no other screen sees
any of this. `tools/padmenutest.py` runs the entry under Unicorn.
`tools/padbits.py` prints the action-to-flag table by running the
wrapper's update and the poll under Unicorn with `GetActionState`
stubbed (European offsets).

The name tables and defaults are data the patcher appends after the code
(`annex_tables`). `tools/uctest.py`'s `annex_records` and `annex_text`
(the patcher's `settings_text`) model that output for the tests.
`tools/padinputtest.py` runs the four entries under Unicorn against the
real DLL.

#### Page Up and Page Down

The wrapper's update (`0x47f2d0`) builds each player's level word from a
fixed table, one action per bit: 10, 11, -, -, -, -, 12, -, -, 2, 3, 4, 5
for bits 0-12. A value past ±5000 sets the bit; in the Australian build,
any value does. Bits 7 and 8 have no action, so only the keyboard sets
them. They are Page Up and Page Down in the wrapper's own scancode table
(`0x47f5c0`; the keyboard's word is at `+0x44`, and the query `0x47f750`
ORs it into player 1's). Two screens read them, through the level
(`+0x1c`). The Records page turns its pages on them (`Record.dll`
`0x1000798b`, `0x10007a2c`, with a repeat of its own). The car select
takes a held Page Up as the alternative colour (`MSelect.dll`
`0x100091d3`): a confirm sets a flag and counts 40 frames, and the flag
is cleared on any frame the bit is not in player 1's level. If the flag
survives, the five cars that have an alternative colour take it. Nothing
else in the exe or the DLLs tests the two bits after a read of the
wrapper.

The `pagepad` patch (asm/pagepad.asm) gives those two bits the bumpers.
The load and test after the table loop (`0x47f506`, `mov eax, [esp+0x10];
test eax, eax`; the Australian `0x4beaf8` compares with ebp, which is 0
there) become a call into the stub. The stub asks the annex's page poll
for the player's LB and RB, the player being side `[esp+0x18]` of the
caller. It ORs them into the level at `[esi-0xa0]` as 0x80 and 0x100.
Then it does the load and test, so the site's branch sees the right
flags. `tools/pagepadtest.py` runs the entry under Unicorn with each
build's addresses.

The Replay Gallery's sort is not input the game reads at all. F6, F7 and
F8 are accelerators in the exe's resources (VK_F6-F8, commands
40043-40045). The window procedure's `WM_COMMAND` handler (`0x428320`)
sets the mode (0 MODE, 1 CAR, 2 DATE) at `+4` of a block at `0x4e6908`,
and turns the order over (`+8`) when the mode picked is the one already
set. The gallery gets the block as its init block's `+0x6c`: the exe's
gallery screen passes `+0x28` of its own object, and the block's `+0x6c`
is that object's `+0x94`. The list's browse state (`0x1000271f`) compares
its own copy of both values every frame and sorts again when they differ.
Nothing a pad sends reaches an accelerator.

So the pad is read where the sort is used. The `sortpad` patch
(asm/sortpad.asm) makes the two instructions after the list's row update
in that state (`0x10002764`, `mov ecx, [esi+0x50]; and edi, 0xff`, the
same in every build) a call into the stub. The stub asks the annex's page
poll for side 0's LB and RB and keeps track of what was already down. On
a press of LB it steps the mode left, and on a press of RB it steps the
mode right, wrapping round at both ends. Then it does the two
instructions. The compare after them sorts the list as an F key would.
The order stays as it was; an F key pressed again still turns it over,
and the keyboard's Page Up and Page Down do nothing here, as before. The
DLL is relocated at load, so the stub finds the image base from its own
RVA and the sort block's global (`0x100be620`) from that base. The poll
slot is an exe address, filled per build. `tools/sortpadtest.py` runs the
site on the real DLL, relocated, under Unicorn.

#### The replay's controls

A replay's cameras do not read `MGInput`'s actions. The camera manager
(`0x411335`) keeps an input object of its own (vtable `0x49b868`, made at
`0x440b40`, `0x38` bytes) and updates it every frame (`0x440c30`, from
`0x411811`). Per player the object holds the device kind at `+8`, the
device's index at `+0x10`, the edge at `+0x18`, the level at `+0x20`, the
previous level at `+0x28` and the analog x at `+0x30`, in -127..127. `+4`
is the player count: two in 2 PLAYER BATTLE, otherwise one. The level's
bits are: 0-3 up, down, left, right; 0x10 and 0x20 the meter on and off;
0x40 the screen switch (in 2 PLAYER BATTLE, to the winner) or the watched
car (in MULTIPLAYER); 0x80 and 0x100 the revolving camera's zoom, which
is the manual's smooth in and out. Each frame the zoom is held adds or
takes 1.75/120 from `+0xd8` of the camera, clamped to ±1.75. That value
is added to the depth of the camera's offset from the car (`+0x18`, which
is copied fresh from the camera table each frame, `0x44137e`), so the
distance stays where it was left.

The keyboard fills the object from fixed scancodes (`0x440d20`). Player 1
has the arrows, Insert, Delete, TAB, Page Up and Page Down. Player 2 has
S, X, Z, C, T, G and TAB. That is the manual's table. The analog is ±127
from left and right. A joystick adds to the object only when the player's
config had one at start. The wrapper's setup (`0x47f0e9`) looks at the
first source of the config's steering record. If that source is past
`0x100`, the setup attaches joystick 0 and marks the player's kind at
`+0x14` of the player's block in the exe's input holder. The update then
reads that device's `DIJOYSTATE` directly (`0x440e20`): the axes go to
the directions and the analog, the POV is read on a kind-2 stick, and
buttons 1, 2 and 3 go to 0x30, 0xc0 and 0x100. The annex's records put a
key first on every action, so the kind is always the keyboard. An XInput
pad only answers source ids, so it never reaches this object.

The camera switch (`0x411cf0`) runs while bit 2 of the game's `+0x44`
flags is set. The replay's starts set that bit (`0x451540`, `0x4516b2`,
and the ten-year credits' `0x419b14`). The switch takes up and down from
the edge, 0x10 and 0x20 for the meter and 0x40 for the switch, and hands
the object to the camera's own input (`0x441860`). On the automatic and
side cameras, left or right on the edge turns the driver's view to the
rear, or turns the side camera to the other side. On the revolving camera
the analog turns it, or left and right from the level when the analog is
near 0, and 0x80 and 0x100 from the level zoom. The pause is the
wrapper's Start edge, as in a race.

The `replaypad` patch (asm/replaypad.asm) makes the pad a player's
whatever the kind. The two loads at the join of both paths (`0x440cea`,
`mov edx, [esi+8]; mov eax, [esi]`, where the edge is made) become a call
into the stub. The stub asks the annex's page poll (`PADPOLL`) for the
player's side (`0x300 + player * 0x40`): the bumpers, the left stick, the
triggers, Y and X. It ORs the ones past half their range into the level:
RB as up and LB as down, the next and previous camera; the left stick's
halves as left and right; RT as 0x80 and LT as 0x100, the zoom; Y as
0x30, the meter; X as 0x40, the switch. It sets the analog from the left
stick's x when the keyboard left the analog at 0. Then it does the two
loads. The D-pad, right stick, A and B are left out. The routine is the
same in every build. `tools/replaypadtest.py` runs the real update on the
patched exe under Unicorn with the input objects stubbed.

### The Options screen

The `devices` patch adds a fourth item to the Options menu and the page
behind it.

#### The texture

`Options.dll` draws from `BINDATA\MISC\OPTIONS.TXR`. The file is `RTEX`,
a count, 16-byte entries `(format, size, bytes, 0)` and, from `0x1000`,
the pixels back to back. Format 0 is 565, 2 is 1555, 8 is 4444. There are
twelve textures. The Dreamcast Device Settings page survives in them
unused: both controller diagrams (8, 9), every label and the full
uppercase font (6), and the calibration bars (7). What is not there is a
steering-wheel icon. Sheet 10 holds the car, speaker and monitor icons
and a blank plate, and the blank plate is the cursor's red frame, drawn
as a nine-slice of 28-texel pieces.

#### Pages and sprites

`OptionsModeInit` (`0x10003770`) loads the TXR and binds ten *pages*
through `0x1000ed90`. A page is a table of 20-byte UV entries `(texture,
u0, v0, u1, v1)`, and the loader swaps each texture index for its handle
in place. A *sprite* is 32 bytes: page, quads, count, width, height, x,
y, 0. A *quad* is 52 bytes: a UV index, a rectangle about the sprite's
centre, and four vertex colours.

`0x1000e850` draws a sprite at a given position, scale and colour;
`0x1000e5e0` draws it at its own position. Both put the quads on one
list. The flush (`0x1000e390`) sorts that list by depth (`0x1000e510`, a
stable merge on the value the device makes of z) and draws far to near.
So a sprite at z 16 goes under one at z 12, and among equals the order of
submission stands. The menu's page is `0x100ac9d8`, with 54 entries and
one `-1` between sprites. Those separators are spare, and `0xe` and
`0x11` now hold "DEVICE" from sheet 6 and the new icon.

#### The menu

The menu itself (`0x10003dd0` init, `0x10003f40` exec) owns a cursor
(`0x1000ba40`) and an icon set (`0x10002330`). Both work over three-entry
tables at `0x1009c820` (frames), `0x1009c82c` (icons) and `0x1009c838`
(labels), and the menu draws the labels itself at `0x10003e10`. While
the cursor rests, it draws the frame table's entry for the item in place.
While it slides, it draws the first entry at its animated x. It draws at
z 16, with its pulse as alpha. The icons go at z 12, so the frame sits
under the plate and shows through as the plate's red holes and a 4-px
outline. The menu's state after a confirm (`0x1000421c`) draws the frame
once more at z 14 while the icon set zooms the icon.

That is five code references to the tables in all, and the patch moves
every one of them. Confirming returns the index with bit 15 set, and
`0x10003c6b` dispatches it through `0x10003dc0` to the page states. The
fourth slot was the exit state, which three items never reached. The stub
in the annex selects state 0xc. The four items sit at x 110, 250, 390 and
530.

#### The item

The label is "DEVICE" over the stock "SETTINGS". The icon is on a
thirteenth sheet the patcher appends to `OPTIONS.TXR`. The patcher adds
the count and a 16-byte entry in the 4 KB header and puts the pixels at
the end. The sheet is 256x256, like the icon sheet. The loader sizes its
handle and entry arrays from the count, and the DLL's copy of the
handles has room for 256. The icon is the monitor icon's plate with the
picture's box filled back to the plate's grey, and a steering wheel cut
out of it the way the stock pictures are: holes in the plate, alpha 0
with a one-texel ramp, and the menu's dark background showing through.
The patcher draws it (`wheel_mask`); it is not copied from anywhere. It
uses the car icon's own UVs, because the page's UVs are three-decimal
values, 126.2 texels across 126 pixels, and exact fractions sample
visibly differently. The label sheet is checked by the texels of its font
and label rows. Of the twelve sheets only sheet 4, the frame's message
lettering, differs between the English and the Japanese `OPTIONS.TXR`.
So the hint lettering is carried in the patcher (`HINT_LETTERING`, the
English sheet's texels) rather than cut from the file being patched.

#### The states

The top-level machine (`0x10003af0`) has twelve states behind `cmp eax,
0xb` and a table at `0x10003d90`. State 1 re-inits the menu, 2 runs it,
3/5/7 init a page, 4/6/8 run a page, and 0xb leaves. The table moves to
the annex with two more entries, and the compare goes to 0xd. State 0xc
is the page's init and 0xd is its exec, both in asm/devices.asm. They are
entered as every case is, with `esi` the Options object, and they leave
through the dispatcher's epilogue (`0x10003cd6`).

Init binds the page's own UV table through `0x1000ed90` and starts the
slide-in. It binds once per load of the DLL, flagged in the blob, because
the binding writes handles over indices in place. The stock pages are
bound once, in `OptionsModeInit`, and the exe reloads the DLL for each
visit. Exec draws the list, moves the cursor, and slides the page. The
page slides in from the right, from 640 down by 40 a frame. It slides out
to the left on cancel or on a confirm over BACK, and the menu's state is
set at -640. Those are the stock pages' numbers.

#### The list

The list is 40-byte entries: kind, sprite or string, x, y, z or text
flags, alpha, red, green, blue in 256ths, and the cursor's hold on the
entry. `devices_page` in the patcher builds it in the Game Settings
page's terms, and `0x100025f0` draws it. The header band, group plate and
row plate are that page's own sprites (`0x100a3128`, `0x100a3290`,
`0x100a4198`, found by their first quad). The plates are at z 14 with
alpha 0xd8, and the text is at z 10.

The text goes through the stock routine `0x1000df10` over its 14-px glyph
sprites (`0x1009c080`, one sprite per glyph, with a 256-byte character
map at `0x100fcc04` that the routine fills on first use). Its arguments
are `(string, x, y, z, advance for a missing glyph, sx, sy, alpha, r, g,
b, table, flags)`; flag 4 is proportional, 1 right-aligned, 2 centred.
The table has letters, digits, `.`, `+` and `-` only, so the colon is a
separate piece. The glyph cells carry a texel of margin around the ink
and need it: boxes cut to the ink render narrow and ragged.

The geometry is the stock's. The band and heading are at y 87, the group
plate at (48, 106), the rows of 18 from (261, 106) with 6 more between
groups, the group text at x 56, the action at 269, the colon at 397, the
value at 405, and the buttons at y 404. There are two groups, PLAYER 1
and PLAYER 2, with seven rows each.

#### The cursor

The cursor is the stock's (`0x10002c30`). It moves up and down through
the rows and the button row, with DEFAULT then BACK on the button row and
left and right between them, wrapping. The sounds are the stock's: 0xe
for a move, 0xf for a confirm (BACK included), 0x10 for backing out. What
the cursor holds is drawn as Game Settings draws it: the row's plate
(0x100, 0x100, 0, 0), its group's plate (0x100, 0x100, 0x20, 0x20), the
button (0x100, 0x100, p, p) and the row's values in white with alpha
0x80 + p/2. p is the page's pulse, which goes from 0 to 0x100 and back by
0x10 a frame (`0x10002a23`). Each entry carries which rows hold it and
how.

The page shows one player at a time. A selector row comes first: the
group plate centred, with PLAYER 1 or 2 on it, and left, right or confirm
switching between them. Then come the KEY and PAD headings and the nine
rows, which are the eight driving actions and the deadzone. The rows use
Graphic Settings' own row sprite (a 123-px label plate, a 30-px fade, a
273-px value plate, three quads) at its x, and are spaced 24 px apart as
that page spaces them.

#### Binding

The values are live. The page reaches the game's input objects through
the holder (`0x100b9464`, the exe's `0x50b120` block). The holder's `+8`
is the exe's input wrapper (vtable `0x4a158c`; its `+0x14(mask)` gives a
player's pressed-edge key bits). The wrapper's `+4` is `MGInput`'s input
object. From there the page reaches `GetConfig` (`+0x34`),
`GetDevice(3, 0)` (`+0x20`) for the keyboard and its `GetState` (`+0x38`, the 256 key
bytes), the config's record list at `+0x124` (a pointer to the head node
of a ring of (next, prev, record)), and `Persist` (`+0x30`) to save
(*Gamepad*). The pad comes through the poll the annex publishes at
`PADPOLL`. That is a dword in the writable room past the end of `.data`
(`0x5a1ff0`; Australian `0x60bff0`), because the Australian device has no
poll method.

A row's key record is the first record of its action with a source under
0x100. Its pad record is the first at 0x300-0x37f without the menu-only
bit. Confirm on a row snapshots what is down and waits: the row pulses
blue to white and the bar says to press the button. A key or pad input
that has been released since the wait began and is then pressed binds to
the row. The row that had that input before takes the row's old one;
for a key that may be either player's row, for a pad input the same
player's. Both configs are then saved. ESC pressed since the wait began,
or Start held for 60 frames, gives up. Left and right on the deadzone row
step it by 5%, and it is saved through a `DZnnnn` name. DEFAULT puts the
shipped set back from the page's data block, which follows the strings
(`bind_data`). The block holds the rows' action ids and a live flag, the
defaults, the value strings the page fills, and a name per scancode and
per pad input. `tools/devicestest.py` drives the routines under Unicorn
against stubs for those objects.

#### The hint bar

The hint bar under every stock page belongs to the frame object
(`0x10001cc0`). The frame pops one of fifteen lettered messages in and
out by a message number in `0x1009c784` (`0x100021b0`; the height goes
from 0 to 1 by 0.1 a frame, and the bar grows from its bottom edge at y
451). All fifteen messages are lettered, so the page leaves that number
at -1 and draws its own bar: the bar's plate and white strip copied from
message 14, grown the same way once the page is in place and dropped
before it leaves.

On the bar is one of two lines, set letter by letter from the frame's own
lettering. That lettering is sheet 4: six lines in a condensed face, dark
ink on opaque white. Each letter is one texel box at the English sheet's
boxes, from the carried `HINT_LETTERING` (`HINT_GLYPHS`). The boxes are
17 rows, from a row above each line's ascenders, because the two lines
the capitals come from sit a row lower against their tops. The letters
are set a texel apart, with 5 for a space, onto white on the appended
sheet at patch time, with two texels of white beyond each end so the edge
samples filter to white and not to the clear gutter. The lines say what
those six lines' letters allow. There is no N or R among the capitals, so
there is no ENTER.

The new data carries absolute pointers, so the annex gets a relocation
block appended to the directory in `.reloc`'s zero tail.

## The install disc

Disc 1 (`diskid.1`) is an InstallShield 5 disc. It holds `setup.exe`,
`setup.ins` (the compiled script), `data1.cab` (370 MB, a single volume),
`_sys1.cab`, `_user1.cab`, `layout.bin`, `os.dat`, `lang.dat` and
`setupdir/<lang>/_setup.dll`. It also holds a `directx/` runtime,
`dxgo.exe`, `dsetup*.dll`, the six `msg_?.dll`, and a loose `miscdll.dll`
for the script's own CPU check.

The strings in `setup.ins` show what the installer did. It had components
*Compact*, *MEDIUM* and *FULL*, and a *PentiumIII Files* component gated
on `CheckKatmai`. It ran `LAUNCH.exe -musashi` for COM registration,
copied `SR2_CPL.cpl` to the system folder, wrote the DirectPlay lobby
key, and made shortcuts for HEAT, Sega's online service.

### Reading the image

`open_source` takes one of: a `.cue` (it uses the first data track of
the bin the sheet names, found beside the sheet whatever path the sheet
carries), an `.iso`, a bare `.bin`, a mounted folder, or `data1.cab`.
`DataTrack` finds the sector form by looking for `CD001` at sector 16
under each of MODE1/2352, MODE2/2352, MODE1/2048 and MODE2/2336, so a cue
sheet that names the wrong mode still works. `iso_root` and `iso_entries`
walk the ISO9660 directory records. There is no Joliet and no Rock Ridge,
so the names are the `8.3;1` ones, lowercased. `DiscFile` presents one
extent as a file object, and `Cabinet` reads `data1.cab` through it
without extracting the 370 MB first. Multi-extent files are refused;
`data1.cab` is well under the 4 GB extent limit.

### `data1.cab` (InstallShield 5)

`Cabinet` in the script reads this file. Its layout, all little-endian:

- The common header is at 0: signature `0x28635349`, version
  (`0x01000004` here), volume info, cab descriptor offset (`0x200`), cab
  descriptor size.
- The cab descriptor has the file table offset at `+0x0c` (relative to
  the descriptor), the file table size at `+0x14`, the directory count
  at `+0x1c` and the file count at `+0x28`. At `+0x3e` are 71 file-group
  list heads.
- The file table is `dirs + files` DWORD offsets, relative to the table's
  start. Directories are NUL-terminated names. A file descriptor is a
  name offset, a directory index, flags (u16), the expanded size, the
  compressed size, 20 bytes, and the data offset. The flags are `1` split
  across volumes, `4` compressed, `8` invalid (there are 20 such entries
  here, all blank).
- A file group node holds a name offset, a descriptor offset and a next
  pointer, all relative to the cab descriptor. The group descriptor holds
  the first and last file index at `+0x4c`. Groups are contiguous index
  ranges.
- The file data is at the data offset in `data1.cab` itself. In the
  `0x01000004` cabinet a compressed file is one raw deflate stream, with
  no zlib header and no final-block marker, so the stream is read to the
  expected size and not to EOF. The `0x01005100` cabinets on the other
  two pressings store a file as chunks. Each chunk is a u16 length
  followed by a complete raw deflate stream of 10240 bytes of output. The
  chunks are inflated in turn until the expected size is reached.

The reader was checked against unshield's listing (5,725 files in 25
groups) and against a Pentium III install (every extracted file
identical), both from the cab directly and through a disc image.

### Groups

| Group | Files | MB | Content |
| --- | --- | --- | --- |
| Program Executable Files | 38 | 12.2 | base exe, screen DLLs, `MUSASHI\`, `LAUNCH.EXE`, `SR2.CFG`, `SR2_SAVE.DAT`, `MPDATA.*` |
| PentiumIII Modules, AMD Modules | 6 each | 5.1 | the six CPU-specific files |
| English, French, German, Italian, Spanish, Japanese | ~337 | 5.2 | `SR2_MSG.dll`, `README.txt`, `PICS\`, `HELP\` |
| * Files | 1 | 0.3 | `SR2_CPL.cpl` per language |
| BINDATA 0 | 207 | 41.7 | `SEDATA` (the sound effects; the co-driver's calls are English on every disc), `BGM` |
| BINDATA 1 | 2354 | 27.9 | small models, tyre textures, `TENYEAR`, `ARCADE`, effects, UI objects |
| BINDATA 2 | 471 | 74.3 | car body textures, engine samples, `800x600`, the root-level `.bg`, `.txr` and `sky*.mdl` files |
| BINDATA 3 | 512 | 348.0 | course data, `TENYEAR`, `CAR`, `CHAMPAGN`, `connect`, `chat` |
| English Binary, UK Binary | 24 | 25.2 | `MISC`, `chat`, `meterNNus.txr`; the two groups are identical |
| Japanese Binary | 18 | 23.3 | `MISC` |
| Carprofile English / Japanese | 18 / 19 | 42 / 59 | the `BGM\cp_*.wav` narration, with the same names in both; `comment.wav` is Japanese only |
| Cabinet Files | 1 | 0.1 | `CABINET.DLL` for Windows 95 |

The four `BINDATA` tiers are one asset set, split by size to make the
compact, medium and full install sizes. No path appears in two tiers with
different content. A full install is the whole set on disk, not higher
detail.

## The play disc

Disc 2 (`diskid.2`) has the volume label `SEGARALLY2` on every pressing.
Its thirteen audio tracks are described under *Music*, above. It holds
the same assets as MS cabinets, 230 MB, MSZIP-compressed (plain
deflate): one `bindata\<dir>.cab` per tier directory,
`bindata\tenyear\N_M.cab` for the 41 ten-year courses, and
`bindata\root.cab` for the root-level files. Every cabinet checked
(`root`, `serial`, `adv`) contains exactly the files the tiers hold.
`diskid.2` is the text `Please enjoy SEGA RALLY 2.` A full install does
not need the disc.

The pressings hold one soundtrack. Stripped of digital silence, the
American and Australian tracks are bit-identical, and the European tracks
are within eleven samples of them. Europe trims the tail. The other two
keep two seconds of tail per track, and America adds 62 ms of lead. A rip
from any of them plays the same music, with the disc's own silence at the
loop. HCJ-0145's play disc carries the Australian audio. The DigiCube and
MediaKite play disc has the same thirteen tracks, and is 11 samples off
the Australian, as the European is.

## What is not done

- One start on Windows with borderless failed with `E_FAIL` through
  `0x4404b0`, from the `jl` at `0x427e05`. Under WinDbg every return in
  `0x421330` (MGameD3D Init, MGameGL Init, its `+0x18`, `0x421670`) was
  0. So the failure is not deterministic, and it has not been seen twice.
- What `LAUNCH.EXE` and `MUSASHI\SR2.dll` offer, and `SR2_SAVE.DAT`'s
  layout beyond the records table.
- Widescreen: the resolution value text's exact place, and whether every
  2D element scales, are to be checked on the running game. The `.bg`
  path with brightness or contrast set (`0x46c900`) and the car select's
  carousel (WIDESCREEN.md, *The 3D*) are not done.
- Pacing by the display on Wine: the game free-runs at 60.000 Hz there.
