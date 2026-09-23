# Notes

How the game works and what the patcher does about it, rather than how to
use it. For using the patcher see [README.md](../README.md); for addresses
and file offsets see [MAP.md](MAP.md); for the widescreen patch, which is
the largest, see [WIDESCREEN.md](WIDESCREEN.md); for the assembly sources
see [asm/](../asm/).

Everything below is read off the retail European release (files stamped
20-21 Oct 1999, VC6 linker 6.0) with pefile, capstone and unshield, and
checked on the game running under Wine and Proton. The American and
Australian releases map onto it; *Builds* says how far.

## Patches

*The annex* is the one `.sr2` section the patcher appends to a file, grown
by each patch that puts code or data there. Offsets are the European
build's file offsets; the other builds' are in `BUILDS` and under
*Builds*. Bold names are the ones the README lists; the key in
parentheses is what `--patch` takes.

| Patch | File | Offsets | Change |
| --- | --- | --- | --- |
| **Windows 9x check** (`win9x`, Australian only) | `SEGA RALLY 2.exe` | `0x4b3b0` | `0x44bfb0` returns 0 at once: `sub esp,0x94` → `xor eax,eax; ret` |
| **No disc required** (`nodisc`) | `SEGA RALLY 2.exe` | `0x267c0`, `0x7572e` | the startup check returns 0, "found" (`mov eax,[esp+4]` → `xor eax,eax; ret`); the loader constructor's drive scan → `lstrcpyA(disc root, exe dir)` and a jump to its epilogue |
| **No card warning** (`nocardwarn`) | `SEGA RALLY 2.exe` | `0x26678` (`0x26938` American, `0x4b263` Australian) | the `push 5` before the warning's string load → `jmp` to the return-0 tail |
| **Replay freed once** (`replayfree`) | `ReplayGallery.dll` | `0x2f65`, `0x3b1f`, the annex | the gallery's `new` → a thunk that keeps the block; its `push eax; call free` → one that frees only that block |
| **Texture release checked** (`texrange`) | `MUSASHI\MGameD3D.dll` | `0x4430`, the annex | the release's first ten bytes → `jmp` asm/texrange.asm; one relocation entry dropped |
| **Survive ALT+TAB** (`altab`, `restoreall`) | `SEGA RALLY 2.exe`, `MUSASHI\MGameD3D.dll` | exe `0x25ff7`, the annex; DLL `0x7710`–`0x778c`, ten relocation entries | the `WM_ACTIVATEAPP` handler's `call 0x46e260` (resume sound) → a stub that calls MGameD3D's restore method first; that method rewritten as `IDirectDraw4::RestoreAllSurfaces` |
| **Z-buffer detach crash** (`zdetach`) | `MUSASHI\MGameD3D.dll` | `0x2930`, `0x2b31`, `0x2d11`, `0x37f4` | `call [ecx+0x20]` → `add esp,0xc`: `DeleteAttachedSurface(0, NULL)` on the back buffer skipped |
| **Missing lettering** (`texfmt`) | `MUSASHI\MGameD3D.dll` | `0xf79c` (12 bytes) | the 16-bit texture-format preference list `1, 2, 3` → `3, 1, 2` |
| **Invisible lobby text** (`textcolor`) | `SEGA RALLY 2.exe` | `0x203c7`, `0x20566`, `0x3485f`, `0x34b2a`, `0x34efc`, `0x35533`, `0x360c3`, `0x3a6c0`, `0x3cef4`, `0x3da96`, the annex | eight `call [__imp__SetTextColor]` → `call stub; nop`; two `mov esi, [__imp__SetTextColor]` → `mov esi, stub; nop` |
| **Lobby panels** (`surfmem`) | `MUSASHI\MGameD3D.dll` | `0x7cb2` | the offscreen surface create's video-memory caps `0x4040` → `0x840`, system memory |
| **Windowed** (`windowed`) | `SEGA RALLY 2.exe` | `0x273e6`; `0x14671`, the annex | the fullscreen flag pushed at `0x427fe5` → 0; the .bg row copy at `0x415271` → `call` asm/bgrow.asm |
| **Any desktop depth** (`anydepth`) | `MUSASHI\MGameD3D.dll` | `0x271e` | `je` → `jmp`: the windowed path's "desktop must be 16-bit" check skipped |
| **Any mode** (`anymode`) | `MUSASHI\MGameD3D.dll` | `0x2ef8` | `and eax, 0x80004005` → `and eax, 0`: the mode check's `E_FAIL` when `EnumDisplayModes` lists no 640x480x16 made `S_OK` |
| **Title picture** (`titlebg`) | `Title.dll` | `0x8ba`, the annex | the DLL's own .bg row copy at `0x100014ba` → `call` asm/bgrow.asm assembled for its stack |
| **Frame log** (`frametrace`, by name only) | `SEGA RALLY 2.exe` | `0x27bf0`, `0x27d0b`, the annex | the frame gate's first five bytes and its last five before `pop ebx; ret` → `jmp` asm/frametrace.asm |
| **Borderless** (`borderless`) | `MUSASHI\MGameD3D.dll` | `0x4d7b`, `0x26be`, the annex | the windowed present → `jmp` asm/fullwin.asm's present; `call [__imp__MoveWindow]` in the windowed init → `call` its sizewindow; ten relocation entries dropped |
| **ALT+ENTER** (`altenter`) | `SEGA RALLY 2.exe` | `0x260bc`, the annex | the window procedure's `call 0x41fe20` at `0x426cbc` → asm/altenter.asm |
| **No mixer needed** (`mixerless`, Australian only) | `MUSASHI\MGAudio.dll` | `0x2278`, the annex | Init's `jne fail` → a stub that zeroes the control count at `+0x84` and eax, and jumps back to the allocation |
| **The mix** (`mix`) | `MUSASHI\MGSound.dll` | `0x439f`, `0x6980`, the annex | the buffer's `SetRange` loads min and max through asm/mix.asm; the streaming buffer's `SetVolume` finishes its mapping through the second routine |
| **Effects at full** (`sfxlevel`, `sfxoptions`, Australian only) | `SEGA RALLY 2.exe`, `Options.dll` | exe `0xb26cb`, `0xb272e`, `0xb2782`; DLL `0xf92a`, `0xf98d`, `0xf9e1` | the setting's load → `mov eax, 9`; in the DLL the load's relocation entry goes with it |
| **Music from files** (`music`) | `MUSASHI\MGAudio.dll` | the annex, 12 sites, the entry point, the CD-volume methods `0x1db0` and `0x1e40` (`0x1d90`, `0x1e20` Australian) | every `call [__imp__mciSendCommandA]` → `call hook; nop`; the `mov esi, [__imp__mciSendCommandA]` at `0x10003108` → `call hookaddr; nop`; entry → the setup thunk; the CD-volume methods' entries → `jmp setvolume` / `jmp getvolume` |
| **Quieter defaults** (`voldefault`) | `SEGA RALLY 2.exe` | `0xd01a8` (`0xd05a8` American, `0x1159a8` Australian), 12 bytes | the defaults block's three sliders, 9 → 6 |
| **CD level marked** (`cdlevel`) | `SEGA RALLY 2.exe` | `0x73048` (`0x73478` American, `0xb2668` Australian) | the menu's CD-level set at `0x473c48` pushes flags 0 → `0x40` |
| **Device Settings** (`devices`) | `Options.dll`, `BINDATA\MISC\OPTIONS.TXR` | DLL `0x33f8`, `0x340f`, `0x3214`, `0x3267`, `0x2f0c`, `0x3638`, the dispatch entry at `0x31c0` + 12 (Australian `0x5b68`, `0x5b7f`, `0x5984`, `0x59d7`, `0x567c`, `0x5da8`, `0x5930`), nine `x` fields and two UV entries in `.data`, the annex; the TXR grows a thirteenth sheet | the cursor's and the icon set's item counts 3 → 4; the item tables and the state table moved to the annex with a fourth item and two more states; the dispatch table's fourth slot → a stub that selects the page's state |
| **No registry** (`noregistry`) | `SEGA RALLY 2.exe` | `0xd07c0`, `0x7e359` | the file name string `SR2.CFG` → `SR2.DSP`; `MGameReg`'s Open at `0x47ef59` (21 bytes) → `xor esi,esi` |
| **Widescreen** (`widescreen`) | `SEGA RALLY 2.exe` | `0x20dfe`, `0x20e18`, `0x5128a`, `0x4e5`, the annex | the mode setter's entry compare and size stores, the screen-change routine's settings load and the element walker's callback call → `call`s into asm/wide.asm, the size table after it |
| **Widescreen, the 3D** (`widescreen3d`) | `MUSASHI\MGameGL.dll` | `0x2bc0`, `0x2c70`, `0x2de0`, `0x27f0`, `0x2e80`, `0x2ee0`, the annex | `SetViewport`'s, `SetPerspective`'s, `SetCentre`'s and the parameter getter's prologues → `jmp` asm/widegl.asm; the projection's and its inverse's first eight bytes → entries of their own |
| **Widescreen, the 2D** (`widescreen2d`) | `MUSASHI\MGameD3D.dll` | `0x5120`, `0x50d0`, `0x4fe0`, `0x5170`, `0x5030`, `0x5080`, `0x6040`, `0x4d50`, `0x411c`, the annex | the six 2D draws', the device viewport setter's, the present's and the texture create's first bytes → `jmp` asm/wide2d.asm; seven relocation entries dropped |
| **Resolution list** (`resolution`) | `Options.dll` | `0x2815`, `0x2826`, `0x2528`, `0x2b01`, `0x2a5b`, six bytes, the annex | the Graphic Settings page's row load, count check, draw loop head, row store and DEFAULT's row store → asm/resolution.asm; the page's six "7"s → "8"; three relocation entries dropped |
| **HUD after the water** (`hudlast`) | `SEGA RALLY 2.exe` | `0x17eb1`, `0x274f2`, `0x25d30` (11 bytes) (`0x18161`, `0x277b2`, `0x25fe0` American; `0x2de01`, `0x4c119`, `0x4a940` Australian), the annex | the race state's HUD call, the frame's root-tree draw and the fade node's draw thunk → branches into asm/hudlast.asm |
| **Gallery sort on LB/RB** (`sortpad`) | `ReplayGallery.dll` | `0x1b64` (9 bytes), the annex | the list's `mov ecx, [esi+0x50]; and edi, 0xff` after its row update (`0x10002764`) → `call` asm/sortpad.asm, which steps the sort mode on a press of the annex's LB or RB |
| **Bumpers as Page Up/Down** (`pagepad`) | `SEGA RALLY 2.exe` | `0x7e906` (6 bytes) (`0x7ed26` American, `0xbdef8` Australian), the annex | the load and test after the input wrapper's action table loop (`0x47f506`) → `call` asm/pagepad.asm, which ORs the annex's LB and RB into the player's level word as 0x80 and 0x100, then makes them |
| **Pad in a replay** (`replaypad`) | `SEGA RALLY 2.exe` | `0x400ea` (5 bytes) (`0x4047a` American, `0x6e99a` Australian), the annex | the two loads at the join of the replay controls' keyboard and joystick paths (`0x440cea`) → `call` asm/replaypad.asm, which ORs the annex's bumpers, left stick, triggers, Y and X into the player's level word, then makes them |
| **Pad on the multiplayer screens** (`padmenu`) | `SEGA RALLY 2.exe` | `0x3ed4f` (6 bytes), the annex | the store of the pad poll's level word (`0x43f94f`) → `call` asm/padmenu.asm, which puts the annex's buttons into the level and its directions, Back as TAB and any press as a key into the keyboard's menu word, then makes the edge and the three stores |
| **Loading screens** (`loadhold`) | `SEGA RALLY 2.exe` | `0x19bbb`, `0x189be` (6 bytes each), the annex | the store of the new loading picture at its create (`0x41a7bb`) and the load of it at the step that deletes it (`0x4195be`) → `call` asm/loadhold.asm |
| **Connection rows** (`lobby`) | `SEGA RALLY 2.exe`, `BINDATA\connect\PROTOCOL\` | `0x3b158`, `0x3b176` (50 bytes), `0x3b1a8`, `0x3b1cc`, `0x3b1dd`, `0x3b357`, `0x3b377`, `0x3b385`, `0x3b3cf`, `0x3f4dd`, `0x3e3e0`; `CONNECT.BMP` and nine button files | the connection screen's four rows IPX / TCP-IP / MODEM / SERIAL → three, INTERNET / DIRECT IP / LAN, centred: the drawer's row y's, its fourth blit skipped, the cursor wrapping in 0..2, the confirm never picking the modem screen, the latency read for every type, SHOW TEAMS on row 2 searching at once; the labels rendered by `tools/labels.py` and carried as masks. See *The connection screen* |
| **Network DLL** (`netplay`) | `MUSASHI\MGNetWk.dll` | the whole file | replaced by the build of `net/`: the stock DLL's CLSID and three vtables over plain UDP - a LAN search, an address typed, and the internet through a directory server; see [NETWORK.md](NETWORK.md) and [net/README.md](../net/README.md) |
| **The clear's height** (`clearsize`, Australian only) | `SEGA RALLY 2.exe` | `0x40b83` (12 bytes), the annex | the mode setter's `mov eax, [WIDTH]` and its two pushes → `call` a thunk that pushes `[HEIGHT]` and `[WIDTH]` and jumps into the clear |
| **XInput** (`xinput`) | `MUSASHI\MGInput.dll` | `0x8130`, `0x8210`, `0x7100`, `0x56c0` (Australian `0x7940`, `0x7a20`, `0x6940`, `0x81a8`), the annex | the registry helper's load and save, the config's update and the device's poll → `jmp` asm/padinput.asm; the Australian build's keyboard-poll address pointed at it instead |
| **DirectInput 8** (`dinput8`) | `MUSASHI\MGInput.dll` | `0x2940` (18 bytes), `0x39ac` (7), the ids at `0x10680`, `0x106c0` (Australian `0x2870`, `0x39f9` (6), `0x10678`, `0x106b8`), the annex | the `DirectInputCreateA` call → `jmp` asm/dinput8.asm; the first read of the device's type byte → `call` its translation; `IID_IDirectInput8A` and `IID_IDirectInputDevice8A` written over the DirectInput 2 ids |
| **Devices of no kind** (`nogeneric`) | `MUSASHI\MGInput.dll` | `0x26d2` (5 bytes; Australian `0x2694`), the annex | the device loop's null-GUID branch and the two instructions after it → `jmp` asm/nogeneric.asm; needs `dinput8` |

In the exe, which is never relocated, VA = offset − 0x400 + 0x401000
inside `.text` (− 0x600 in the American). In the DLLs raw and virtual
layouts coincide, so VA = offset + 0x10000000 at the preferred base. The
DLLs are relocated at load, which is why every patch that lands in one is
position-independent and drops the relocation entries of the bytes it
replaces.

## The executable

The exe is a shell: main loop, file loader, the Musashi glue, the network
lobby (WSOCK32, IPX, serial, modem) and the results/records screens.
Every other screen is a DLL loaded by name with four exports
`_XxxInit@4`, `_XxxExec@4`, `_XxxDraw@4`, `_XxxEnd@4`:

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

Imports are the plain Win32 set plus `ole32` (`CoInitialize`,
`CoCreateInstance`) and `WINMM` (`timeGetTime`). No DirectX DLL is
imported by the exe or by any screen DLL. `cabinet.dll` (FDI) is loaded
by name for the play disc's cabinets.

Sections: `.text`, `.rdata`, `.data`, `STATUSDA`, `METERDAT`, `MYDATA`,
`ALIGN16D`, `MGAMEMAT` (P3 only, 512 KB writable, the SSE scratch),
`.rsrc` (icon, accelerators, version - no manifest).

### Builds

`data1.cab` carries the base build (x87) and two overlay groups,
*PentiumIII Modules* (SSE) and *AMD Modules* (3DNow!), each replacing the
same six files: `SEGA RALLY 2.exe`, `AdvTelop.dll`, `Champagn.dll`,
`MSelect.dll`, `MUSASHI\MGameGL.dll` and `MUSASHI\MGLBackground.dll`. The
patcher installs and patches the Pentium III build only: the three
compute physics differently, so replays and netplay between them would
not match, and every CPU since runs SSE.

Four builds are supported, told apart by the exe's MD5 in `BUILDS`, each
checked against a disc matching its Redump dump (EI-1183-1, 40924-0919,
MK-85078-40, DWRPD-00081):

| | Exe linked | `.text` | Cabinet | Against the European |
| --- | --- | --- | --- | --- |
| **Australian** | 3 Jun 1999 | 0xd2c9a | `0x01005100` | the first release: 259 KB more code, a Windows 9x check, no `LAUNCH.EXE`, English and Japanese only; its own `AdvTelop`, `Champagn`, `MSelect`, `MainMode`, `Options`, `Record`, `ReplayGallery`, `SegaLogo`, `Title.dll`, `miscdll.dll`, `MGAudio.dll`, `MGInput.dll` |
| **European** | 21 Oct 1999 | 0x936ca | `0x01000004` | - |
| **Japanese (DigiCube, MediaKite)** | 29 Nov 1999 | 0x936ba | `0x01000004` | a rebuild of the exe alone, 2.0.0.9: two functions recompiled, `.text` 0x10 shorter (*The DigiCube and MediaKite build*); no `VendorLogo.dll` and two fewer files in *BINDATA 2* |
| **American** | 3 Oct 2000 | 0x9367a | `0x01005100` | a relink: the exe (`.data1` added, `.data` 0x100 longer), `LAUNCH.EXE`, `MSG_S.dll`, `VendorLogo.dll`, `sr2_cpl.cpl`; its own `TENYEAR` trackside art |

Everything else is byte-identical across the four, `MGameD3D.dll`
included. The play discs carry the same assets and one soundtrack (*The
play disc*).

#### The rows

A row of `BUILDS` holds the fingerprints of fourteen files - the six the
P3 build replaces and the eight more the patches touch - the exe's
sites, the import slots those sites name,
and the addresses the exe stubs read. Every patched instruction is the
same bytes in all four exes bar its operands; each site was found by
its masked context and read back before it went in:

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

The ten SetTextColor sites are in the rows. Each row names the eight
import slots the patches read. The American table differs from the
European in one of them, `GetLogicalDriveStringsA`, which `nodisc`
verifies; the Australian is laid out afresh, so all eight move. The
DigiCube and MediaKite exe has the European ten and the European eight.

The Australian `Title.dll` has the row copy at the same offset in
identical code. Its `MGAudio.dll` has the same eleven calls and one load
of `mciSendCommandA`, which the music patch finds for itself, and one
different branch in Init (*No mixer needed*).

#### The patched files

Ten files are patched in every build - `SEGA RALLY 2.exe`,
`MUSASHI\MGameD3D.dll`, `MUSASHI\MGameGL.dll`, `MUSASHI\MGAudio.dll`,
`MUSASHI\MGSound.dll`, `MUSASHI\MGInput.dll`, `MUSASHI\MGNetWk.dll`,
`Title.dll`, `Options.dll`, `ReplayGallery.dll` - and
`BINDATA\MISC\OPTIONS.TXR`. Each gets a `.bak`
beside it, the untouched original. The patcher always starts from those,
so patching twice is patching once and restoring is a rename; a file that
a run with fewer keys leaves alone goes back to its `.bak`, so the keys
given are the patches in place.

### Sega's updates

Sega Japan published four updates for its own 1999 release (HCJ-0145),
each a self-extracting installer with a `PATCH.exe`, plus a settings
tool. None was published for the English releases. What they carry, P3
set, by the files' version resources and link dates:

| Update | Exe | Other files |
| --- | --- | --- |
| UPDATE231 | 2.0.0.6, 11 Jun 1999 | `Champagn.dll` 2.0.0.6, `MGInput.dll` (10 Jun), `miscdll.dll` (11 Jun, `2d0f7f64…`), `SR2_CPL.cpl`, `CABINET.DLL` |
| UPDATE232 | - | `MGAudio.dll` (28 Jun) |
| UPDATE240 | 2.0.0.7, 13 Jul 1999 | `MGAudio.dll` (13 Jul, `b05b9c8e…`), `miscdll.dll` |
| UPDATE250 | 2.0.0.8, 21 Oct 1999 | `MGInput.dll` (28 Sep, `7aa0b3ae…`), `MGAudio.dll` (`b05b9c8e…`), `miscdll.dll`, `SR2_CPL.cpl` (27 Sep), `CABINET.DLL` |
| DisplaySettings.exe | - | a tool, not a patch: writes the display block of `SR2.CFG` (System/640x480/800x600, AGP, 3D device) |

**UPDATE250's P3 `RALLY2.exe` is the European `SEGA RALLY 2.exe`, byte
for byte** (`51b3da97…`), and its i586 and AMD exes, `MGInput.dll`,
`MGAudio.dll`, `miscdll.dll` and `SR2_CPL.cpl` are the European files
too. The European release is the
Japanese one at patch level 2.50 with a later `Champagn.dll` (2.0.0.8,
20 Oct 1999, in no update).

The exe versions in order: 2.0.0.2 Australian,
2.0.0.6 UPDATE231, 2.0.0.7 UPDATE240, 2.0.0.8 UPDATE250 and European,
2.0.0.9 DigiCube and MediaKite, 2.0.1.1 American. The
Australian is older than every update, by version and by date. 2.0.1.0
has not been seen.

The 2.31 and 2.40 exes are of the Australian lineage - 1.75 MB, `.text`
0xd306a and 0xd30ca against the Australian 0xd2c9a - and 2.50 is where
the 259 KB went. The FULL installers carry i586, AMD and P3 exes and a
`supcpu.txt` (1, 4, 2; 7 for all three) that `PATCH.exe` reads from the
game's folder to pick one; it finds the game through
`HKLM\...\App Paths\SEGA RALLY 2.exe` and checks the exe's
`FileDescription` for the CPU tag, nothing about the region.

So an HCJ-0145 install at 2.50 has the European exe and `build_of`
places it as European; the check then stops at `Champagn.dll is not the
European build's`, since 2.50 leaves 2.31's `Champagn.dll` in place. Its
other DLLs were in no update either, so what an HCJ-0145 install has for
`Options.dll`, `Title.dll` and `ReplayGallery.dll` is unknown without
the disc. The same happens to an Australian install run through the
Japanese updater: the European exe over Australian DLLs, refused.

#### The Japanese pressings

HCJ-0145 (Sega, 25 Jun 1999), DWRPD-00081
(DigiCube, 22 Nov 2000), MKW-166 (MediaKite, 2 Mar 2001) and SPB-040
(bundled with I-O DATA's GA-TNT2), per
[sega.jp's patch page](https://web.archive.org/web/20080611152022/https:/sega.jp/pc/rally2/patch_old.shtml)
and [its library index](https://web.archive.org/web/20010823045326/http://www.sega.co.jp/sega/pc/lib/lib.html).
SPB-040's play disc is printed `GA-TNT216専用`; I-O DATA's
[card page](https://www.iodata.jp/products/graphics/tnt2/stage4.htm)
lists the retail game with the GA-TNT2 series.

| Pressing | Build |
| --- | --- |
| HCJ-0145 | not seen |
| DWRPD-00081 | Japanese (DigiCube, MediaKite); Redump [install](https://redump.info/disc/110322) and [play](https://redump.info/disc/110323) disc |
| MKW-166 | Japanese (DigiCube, MediaKite): the same data tracks |
| SPB-040 | not seen |

The Australian exe (2.0.0.2) is older than every update, and the
Australian disc carries only English and Japanese, so HCJ-0145 may well
be that build; without an image of it, that is a guess. Sega's updates,
as sega.jp published them: `UPDATE231FULL.EXE` 25 Jun 1999,
`UPDATE232FULL.EXE` 29 Jun, `UPDATE240FULL.EXE` 15 Jul,
`UPDATE250FULL.EXE` 25 Oct, and `DisplaySettings.exe`, a settings tool,
14 Jul.

#### The DigiCube and MediaKite build

The MediaKite disc's data tracks are the DigiCube ones Redump lists: one
master, the install disc's volume made on 29 Nov 1999 and the play
disc's on 2 Nov 1999, so one row covers both.

The exe is the European one rebuilt five weeks later: 2.0.0.9, linked 29
Nov 1999, language 0x0411, the same sections at the same addresses and
sizes bar `.text`, the same import slots. The code is the European code
but for two functions:

| Where | What |
| --- | --- |
| `0x442180` | grows 0x20; the functions after it, to `0x443de0`, sit 0x20 later, and eleven pointers to them in `.rdata` with them |
| `0x443de0` | shrinks 0x30, to end at `0x444120` against Europe's `0x444130` |
| from `0x444130` | everything 0x10 earlier, and every pointer to it |
| `0x5b4d48` (`MYDATA`) | a default, 1 → 3 |

No site or address in the row falls between `0x442180` and `0x444130`.
So each exe site and code address is the European one, or 0x10 less past
that range - the loader's drive scan, the registry open, the CD level,
the bumpers' page keys, the five volume entries, `RESUME`, `SETVIEWPORT`,
`TREEDRAW`, `HUDRESET`, `FADEDRAW` - and every data address is the
European one. The other thirteen files the row fingerprints are the
European bytes.

The disc has no `VendorLogo.dll`, though the exe still loads one: the
loader at `0x4533e8` leaves the module's five entry points zero when
`LoadLibrary` fails, so the screen is skipped. `MSG_S.dll`, `sr2_cpl.cpl`
and the Spanish help are the American files; `LAUNCH.EXE` is its own.
The cabinet has the European 25 groups, with 37 files in *Program
Executable Files* and 469 in *BINDATA 2* (no vendor logo art).

### The processor check

`0x444be0`: `LoadLibrary("MISCDLL.DLL")`, `GetProcAddress("CheckKatmai")`,
call with a pointer to a DWORD, expect 1, else `MessageBox("CPU Version
error")` and return −1. `CheckKatmai` (`miscdll.dll` `0x10001020`) is
three tests: CPUID present (EFLAGS bit 21 toggles), `CPUID(1).EDX &
0x02808001 == 0x02808001` (FPU, MMX, FXSR, SSE), and an SSE instruction
executed under SEH. No vendor or family test. It passes on every x86 made
since 1999, so no patch; if `miscdll.dll` were missing the exe would fail
at `LoadLibrary` first.

### The card check

The device-select routine `0x426ea0` walks the entries MGameD3D
enumerated (`0x2c0` bytes each), picks the one whose name matches the
`display` string in `SR2.CFG`, and for entry 0 adds the desktop's
`bpp × width × height / 8` to its free video memory. `0x427240` then
warns - string 5 of `SR2_MSG.dll`, `WARNING`, OK/Cancel - when that
memory is under 4,000,000 bytes or bits `0x1800` of the entry's `+0x34`
are clear; Cancel makes it return 1 and the caller exit. Bit 0 of the
same word clear returns −1, "No 3D capability".

Wine passes the bits; a Radeon R9 380 on Windows does not, or wraps the
DWORD, and gets the box on every start. No card sold since is on the
list, so `nocardwarn` skips the box; the −1 path stays. The Australian
exe has no memory test.

### The Windows 9x check

Australian only. `0x44bfb0` shows "Please run on Windows 9x." unless
`GetVersionExA` gives `dwPlatformId` 1. The patch makes it return 0 at
once. The other builds have no such check.

## Musashi

The game is written on Sega's *MUSASHI* middleware: in-process COM servers
under `MUSASHI\`, each with `DllRegisterServer`. The exe creates eight of
them by CLSID, the screen DLLs create the sound one again, and two are
created internally:

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

`MUSASHI\SR2.dll` is the launcher's settings page (COMCTL32), not used by
the game.

Two consequences:

- DirectDraw, DirectInput and DirectSound are imported by name by the
  Musashi DLLs, and COM loads those with `LOAD_WITH_ALTERED_SEARCH_PATH`:
  the DLL's own directory first, then the system ones, never the exe's.
  So a wrapper `ddraw.dll` goes in `MUSASHI\`, not beside the exe, where
  it is never found; a wrapper's `D3DImm.dll`, loaded by the system
  `ddraw` machinery, goes beside the exe. No reroute patch needed.
- Without registration every `CoCreateInstance` fails. The installer ran
  `LAUNCH.exe -musashi` to register. The patcher instead writes an
  application manifest beside the exe that depends on assembly `MUSASHI`,
  and `MUSASHI\MUSASHI.manifest` with a `comClass` per DLL. An external
  `.exe.manifest` is honoured because the exe embeds none. Works under
  Wine, Proton and Windows 10. The same manifest declares the process
  `dpiAware`: without it Windows scales the window on a high-DPI display
  and, having noticed, puts up the Program Compatibility Assistant and
  sets the override itself.

### The registry

The exe imports no registry function. `MGameReg.dll` is the registry: its
Open (`0x10001420`) is `RegCreateKeyExA(HKEY_LOCAL_MACHINE,
"Software\%s\%s", KEY_ALL_ACCESS)`, called from the exe (`0x47ef5e`) with
`"SEGA"` and `"SEGA RALLY 2"`, and the resulting object is handed to
`MGInput`'s init (`0x47ef9e`).

The controller configuration lived under that key, written by
`SR2_CPL.cpl`, the "Controller Settings" Control Panel item the installer
added. The game only reads it and runs on its defaults when it is empty -
and writes player 1's defaults there itself on that first run; player 2
has none without the applet.

The object serves nothing else in the exe (`MGameReg`'s `App Paths`
lookup is never reached), so with the Open skipped and `MGInput`'s load
and save replaced (*Gamepad*) the key is never made, which is also what
Windows without administrator rights needs. Nothing in `setup.ins` writes
under `Software\` except the DirectPlay lobby key
`Software\Microsoft\DirectPlay\Applications\SEGA RALLY 2`.

### Car models

A `.mdl` is one block of file offsets, fixed up to pointers at load
(`0x474e80`): dword 0 the size, dword 2 the top node's link. A node is
0x80 bytes:

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
mesh descriptor is 0x20: vertices (32 bytes each: position, normal, u,
v), indices, material, counts, and at `+0x18` 10 for the ordinary path.
Its flag block follows: `0x903` body, `0x103` wheel, `0x113` window,
`0x1003` lamp glass, `3` a glow quad. A node whose flag block is null
holds a light (`tenkougen.mdl`, the two headlight cones in a body).

Nothing applies the node transforms but the exe: the wheels' draw
(`0x47e450`) translates, rotates and scales by them; the body's
(`0x44bba0` and the LOD table at `0x4bc398`) and the lamp models'
(`0x44c320`, walking the tree at `0x44c3f0`) draw each mesh under the
car's matrix as it is.

A car's set (`CAR\<name>\`, the name table at `0x4cc400`, loaded at
`0x469b69`):

- `s_`, `m_`, `l_`, `r_<car>.mdl` - the body by detail, each a body,
  four wheels, more parts with the detail, one or two windows and the
  two lights, mapped into `body.txr` and its dirt variants;
- `normal.mdl`, `snowy.mdl` + `sn_light.mdl`, `desert.mdl` +
  `de_light.mdl` - the lamp kit by course type (`0x4ccf44`: 0 desert, 2
  snow, else normal). `normal.mdl` is the lens glass alone, `snowy.mdl`
  the pod and its glass, `desert.mdl` the snorkel, scuttle lamps, bull
  bar and spare-wheel rack, into `option.txr`;
- `ft_light`, `bk_light`, `hazard`, `bkfire`, `tenkougen`, `brake`,
  `small`, `close` - the glows, each a quad at the lamp's place, +z the
  front.

A race's car object (`0x469f12`) gets a 0x68-byte glow object
(`0x485250`) per glow model holding a clone of its top node; `0x4855f0`
draws it translated by the node's position, the quad's size and
brightness from the view angle and distance. A car's `Draw` (`0x44b0c0`
the player's, `0x442b30` an opponent's) is wheels, glows and kit, then
the body, under one push of the car's matrix (`0x128` in the car).

The desert kit's black pieces on the Celica - the snorkel up the left
A-pillar, the backs of the two scuttle lamps - are that model as drawn,
not a placement fault; a trace of the model draws showed the kit under
the body's own matrix.

One thing the creation does to the loaded data: with the desert kit it
adds `0x4cd2cc[car]` (0.125 for half the cars) to the top node's z of
`de_light.mdl` (`0x46a609`), and the models stay loaded between races of
the same car, so that glow creeps forward a step each race.

## Startup and files

### The install contract

The exe itself touches no registry; that is `MGameReg`'s, above. At
startup:

1. `0x427450`: `GetModuleFileNameA`, open `SR2.CFG` beside the exe. Must
   exist.
2. `0x4274e0`: `GetLogicalDrives`, for each drive `GetDriveTypeA ==
   DRIVE_CDROM`, `GetVolumeInformationA` label `SEGARALLY2`, open
   `X:\DISKID.2`. Returns the drive index or −1.
3. `0x4273c0` wraps 2: on −1, `MessageBox` with an "insert disc" string
   from `SR2_MSG.dll` (id 2 or 3, depending on whether `SR2.CFG` was
   found) and retry, or give up. Returns 0 for found. This is `nodisc`'s
   first site; the second is in the loader, below.

`SR2.CFG` is 100 bytes, read straight into the settings block at
`[0x50afe0]` (`0x427740`) and written back at shutdown (`0x427880`):

| Offset | Field |
| --- | --- |
| `0` | the DirectDraw device name (`display`, the primary), which `0x426ec0` looks for among the enumerated devices, zeroing the block when none matches |
| `0x20` | five DWORDs: `+0x28`, `+0x2c` and bits 1-2 of `+0x30` are capability flags recomputed each start from the device's video memory (thresholds `0x426fb8`-`0x4270ac`), the rest `LAUNCH.EXE`'s options |
| `+0x50` | the 640x480 / 800x600 choice: the loader switches to the `BINDATA\800x600\` asset set when `[[0x50afdc]+0x50] == 1` (`0x476512`) |
| `+0x58` | a copy of the live block's `+0x54` |
| `+0x5c` | the disc flag (below) |
| `+0x60` | the language from `GetUserDefaultLangID` (`0x4272b0`): 1 English, 2 French, 3 German, 4 Italian, 5 Spanish, 6 Japanese |

The in-game options live in `SR2_SAVE.DAT`. With *No registry* the
block's file is `SR2.DSP`.

### The loader

`0x476260` constructs the loader object. Two prefixes: `+0x108` is the
exe's directory (`GetModuleFileNameA`, cut after the last backslash);
`+0x4` is the play disc's root, from the same drive scan as above but
done again here, empty if not found.

`0x476a50` opens a file. Three tries, in order:

1. `<exe dir>BINDATA\<dir>\<file>` - a loose file (`0x4764e0` builds the
   path)
2. `<exe dir>BINDATA\<dir>.CAB` - a cabinet beside the exe (`0x476780`
   builds the name)
3. `<disc>BINDATA\<dir>.CAB` - the cabinet on the play disc

Cabinets are read through `cabinet.dll` FDI. Local files win, so a full
install never opens the disc for data.

### The disc flag

The mode select dims everything but MULTI-PLAYER, OPTIONS and EXIT when
`settings+0x5c` is 0. It is set at `0x42775f` (after `SR2.CFG` is read)
and `0x426ef8` as `isalpha(*root)`, where `root` is the loader's disc
root at `+4` (`0x476ef0` returns its first byte). So the disc dependency
is two-fold: the startup check at `0x4273c0` for the dialog, and the
loader's own scan for the menu.

The `nodisc` patch handles both: the check returns "found", and the
constructor copies the exe directory into the root slot. The root's first
character then is a drive letter, the flag is 1, and the loader's third
fallback looks for cabinets in the install folder. A UNC install path
(`\\server\...`) would still read as no disc. The same drive letter is
formatted into `%c:\AUTORUN.EXE` at `0x4277d0`; nothing in the exe reads
that buffer.

### RallyDebug.ini

Read from beside the exe with `GetPrivateProfileStringA` (`0x427c01`):
`[DebugSettings]` with `DebugInfo`, `CourseCollision`, `CarCollision`,
`CPUCar`, `Course`. `DebugInfo` goes to `0x5a2688`, which nothing reads.

The overlay `Total:%5dKB Used:%5dKB Free:%5dKB Quality:%s FPS:%2d
TPF:%5d` (`0x428140`) is gated on `0x4e68f8`, set only when a
`DebugDLL.DLL` beside the exe loads and exports `NagaSp` (`0x427340`),
and its one call site (`0x428107`) is on the branch taken only when that
flag is clear, so it cannot draw in the retail build: a leftover of the
debug builds, in which the DLL did the presenting (`0x428825`). There is
no in-game frame counter.

### Frame timing

The game steps its simulation at 60 Hz and times itself in `0x4287f0`,
called from each frame's `0x4280a0` between the step and the draw. Init
(`0x427eef`) takes `QueryPerformanceFrequency` / 60 as the budget (timer
object `+0x24`; `+0x28` says QPC is there, `0x4287a0` reads the counter,
`timeGetTime` only as the fallback). No `Sleep`, no `timeBeginPeriod`.

Each frame:

1. present (`MGameD3D` `+0x80`);
2. if more than n budgets have passed since the last exit, extra steps of
   the simulation without a draw, up to four (`0x428897`);
3. a spin on the counter until elapsed > n × budget (`0x4288f0`);
4. `last = now`, so the overshoot is not carried.

n is `[0x4b2354]`, 1 or 2 from `settings+0x40` in `SR2.CFG` at
`0x41754b`.

Stock, in exclusive 640x480@60, the `Flip(DDFLIP_WAIT)` blocked on the
vertical blank; the spin was the fallback. The borderless `Blt` returns
at once, so the pace is the spin: 60.000 Hz on the counter, free-running
against the display. `frametrace` on Windows shows the game's own work at
1-2 ms a frame, the blit at 0.2 ms, the spin the rest, and one catch-up a
run, at the race start. With managed textures it showed a hundred
catch-ups a run and 200-500 ms stage loads; that is why they are not
used.

The catch-up test is a strict "elapsed > steps × budget", so anything
that holds a present for a fraction of a frame costs a second simulation
step and a second budget of spin: the present must not wait. A wait for
the vertical blank in it did exactly that on Windows and is not there;
`MGameD3D` `+0x54` (`0x10004d30`) is that wait as a method the exe never
calls. On Windows the layer renders the frame after the blit returns, on
its own thread; the loop never sees the render.

The gate's four flags:

| Flag | Meaning |
| --- | --- |
| `0x4d6a3c` | running |
| `0x4d6a6c` | paused (the Start-button menu, `0x41932d`; the present is skipped too) |
| `0x5a2660` | the debug DLL |
| `0x4d6930` | catch-up allowed, cleared on the first tick of the two-frame transition object of class `0x49b138` (`0x41a9e0`) and set on its second, which builds the next scene |

The `frametrace` diagnostic is under *How each patch works*.

### Music

`MGAudio.dll` is the only user of `winmm`: `mciSendCommandA` for the CD,
`mixer*` for its volume. It opens the device by type ID
(`MCI_OPEN_TYPE|MCI_OPEN_TYPE_ID`, `MCI_DEVTYPE_CD_AUDIO`, at
`0x10003100`), sets TMSF, plays with `MCI_FROM` (track N+1 in the low
byte, `0x10003160`), seeks to a TMSF it computes from milliseconds
(`0x100032f0`), pauses, resumes, stops, closes, and polls `MCI_STATUS`
for position, track count and per-track length (`0x10003220`–
`0x100032df`). The `MCI_NOTIFY` flag it sets on play goes nowhere:
nothing in the game handles `MM_MCINOTIFY`. Position is polled against
`GetTickCount` bookkeeping around `0x100023cf`, which is presumably how a
course loops.

At "Go!" the exe seeks the course track to 0:00 with a track number one
below the one its play used, and sends no play after it; the hook takes
a seek to the open track or the one below it as a restart.

The play disc's audio: tracks 2–14, each in its own bin in the Redump
dump with a 150-sector pregap at `INDEX 00`. The ripper starts each track
at `INDEX 01` and stops at the end of its file.

## How each patch works

In the order of the table above; rows that are a single obvious byte
edit are skipped. The widescreen patches have [WIDESCREEN.md](WIDESCREEN.md)
to themselves. Most patches install assembled machine code rather than
editing bytes; the sources and a longer account of each are in
[asm/](../asm/).

### No disc required

Two sites, for the two places the game looks: the startup check and the
loader's own scan. *The disc flag*, above, has the account.

### Replay freed once

The gallery's End (`0x100046c0`) frees the replay at `+0x50` of the exe's
block. That block is its own when it loaded it from a file (`new` at
`0x10003b65`) and MainMode's static buffer when it came from a race.
Windows 9x's HeapFree refused the latter; the heap since Windows 8 ends
the process for it. The `new` becomes a thunk that keeps the block, the
`push eax; call free` one that frees only that block. See
asm/replayfree.asm.

### Texture release checked

The release of texture N (`0x10004430`) did not check N against the
count at `0x10012590`, as the create does. `VendorLogo.dll`'s End
(`0x100014e0`) releases −128, 512 bytes before the table, and calls
through whatever is there. asm/texrange.asm adds the check.

### Survive ALT+TAB

The window procedure (`0x426b80`, registered at `0x426af0`) handles
`WM_ACTIVATEAPP` at `0x426bc5`: with the sound object at `0x50b12c`, it
calls `0x46e260` on activation and `0x46e210` on deactivation, resume and
pause of the sound (`thiscall`, `ecx` = the object). Nothing restores the
DirectDraw surfaces. `MGameD3D` has the routine - slot 16 (`+0x40`) of
its interface, at `0x10007710`: `IsLost`/`Restore` on the primary, the
back buffer and the Z-buffer - and no code in the game calls it; the exe
holds the interface at `0x50b118`. So after a switch away every flip
fails and the screen stays blank. Two patches:

- the resume call goes through a stub that calls the restore method
  first;
- the method itself is rewritten as `IDirectDraw4::RestoreAllSurfaces`
  on the object at `0x1001254c`, since the original restores three
  surfaces and everything else DirectDraw owns stays lost.

The textures are the game's own: `MGameD3D` builds each as a
system-memory surface (`0x10004530`, caps `0x1800`) and a video-memory
twin (`0x10003ff2`; descriptor from `0x10003e70`, caps
`ALLOCONLOAD|TEXTURE|VIDEOMEMORY`, `NONLOCALVIDMEM` for AGP when the
hardware flag at `0x1001253c` says so), filled with
`IDirect3DTexture2::Load` (`0x100043f0`), and releases the system copy
on success (`0x10004385`).

A lost video-memory surface comes back empty from `Restore` - DirectX's
contract, and Wine keeps to it - so if a surface were ever lost the
textures would come back blank until the next load. A task switch from a
window loses nothing, and no loss has been seen on Windows 10/11 or Wine.
Managed textures (`DDSCAPS2_TEXTUREMANAGE`) would cover it, but the
Windows DirectDraw layer's managed path is slow - long stage loads, runs
of slow frames - so they are not used; if a loss ever shows, the answer
is to keep the system copy and `Load` again after `RestoreAllSurfaces`.

Borderless full screen, or the framed window, is how the game runs, so
the stock exclusive display mode is gone; the two alt-tab patches stay.
`DDSCL_NORMAL` surfaces can still be lost - another exclusive
application, a locked screen - and the restore on activation costs
nothing when nothing is lost.

### Z-buffer detach

`MGameD3D` keeps the back buffer at `0x10012554` and the Z-buffer at
`0x1001255c`. Before it creates the Z-buffer (two init paths,
`0x10002b25` and `0x10002d05`), when it releases it (`0x10002920`) and at
teardown (`0x100037df`) it calls the back buffer's
`DeleteAttachedSurface(0, NULL)` with a literal null and ignores the
result. DirectX 6 and Wine's ddraw answer with an error code; Proton's
ddraw dereferences the null and the process dies in the SEH handler
before its window appears.

The four calls become `add esp, 0xc`, which leaves the stack as the
stdcall would have. Where the call returned an error nothing changes. If
DirectX treated the null as "detach everything", the difference is a
Z-buffer that stays attached until the back buffer goes - a leak at exit,
not a fault.

### Missing lettering

`MGameD3D` enumerates the device's texture formats at `0x10003cf0` into
slots at `0x10012594` (0 P8, 1 X1R5G5B5, 2 R5G6B5, 3 A1R5G5B5, 4
A4R4G4B4, 5 P4, 6-10 DXT) and picks the default 16-bit one from the list
at `0x1000f79c`, first slot present wins. Texture data is 1555 with bit
15 set on opaque pixels; for a 555 target it is copied as is
(`0x10004af0`), for 565 expanded with bit 15 dropped (`0x10004bb0`).
Every texture gets `SetColorKey(DDCKEY_SRCBLT, {0, 0})` (`0x100046ce`,
`0x100043d1`).

Opaque black is therefore `0x8000` in an X1R5G5B5 texture. Drivers of
the day compared the raw texel against the key and drew it; modern
DirectX and wined3d mask the X bit before comparing, so it matches 0 and
is dropped. The visible result: the black lettering on the mode-select
and car-select headings gone, leaving the white plate and a dashed grey
anti-aliasing edge.

The list becomes `3, 1, 2`: A1R5G5B5 first makes bit 15 alpha, which is
what the data is, and leaves the key exact. The copy path is unchanged:
`0x1001273c` ("not 565") stays set.

### Invisible lobby text

Every mode DLL draws through MGameD3D; the only GDI text in the game is
the exe's, and all of it is the multiplayer lobby: the name entry
(`0x420fa0`), the team and chat list (`0x435400`), the status line, the
timer and the IP list. One face, Courier New (MS Gothic on the Japanese
build), three sizes, created at `0x435df4`, `0x435e9b` and `0x435f33`.

The lobby chrome is BMPs (`CHAT_*.BMP`, `MENU_*.BMP`) loaded into 16-bit
surfaces in the back buffer's format, and the text goes onto them
through `IDirectDrawSurface4::GetDC`: blit a strip of the background into
the surface, `TextOutA` the buffer, `BitBlt DSTINVERT` for the caret,
`ReleaseDC`, then `Blt` the strip to the back buffer with `DDBLT_KEYSRC`
and a key of black.

Every site sets the colour with `SetTextColor(dc, -1)`. Windows 95 took
the low three bytes and drew white. NT-family GDI and Wine read bit 24 as
`PALETTEINDEX`, look up entry 0xffff in the DC's palette, fail, and fall
back to entry 0: black, which the keyed blit drops. The caret, an
inversion, survives, and moves as the extent of the invisible text grows.

The stub in the annex masks the colour to RGB and continues into the
import, so the sites keep their shape; the IME path at `0x421166` pushes
0 and is unaffected. See [asm/README.md](../asm/README.md).

### The lobby's panels

MGameD3D's offscreen surface create (`0x10007b30`) takes `dwCaps` from
the kind its wrapper carries at `+0x14`: 0 and 1 system memory
(`0x840`), 2 local video memory (`0x4040`), 3 non-local
(`0x20004040`), 4 and 5 the primary and the back buffer, 6 a texture
(`0x1800`). The team room's are kind 2 - a `d3dtrace` of the screen
reports the background, the team list, the chat line, the timer, the
course box and the button icon all as `0x10004040` - and the exe draws
its text into them through `GetDC`, which locks them.

With dgVoodoo 2's *Fast video memory access*, a lock of a video-memory
surface does not preserve what is already in it. The chrome blitted
into the panel is gone by the time `ReleaseDC` returns, so the panel
reaches the screen black with the text on it, while the blit itself
returns `DD_OK` and a `Lock` of the source reads the same black.
Turning the setting off is not an answer: without it nearly every
texture comes up white or as noise.

`surfmem` makes kind 2 system memory, which is what the connection
screen's panels already ask for, so a lock has nothing to discard. The
texture path is kind 6 and untouched. The cost is that these blits
become uploads, which a still screen does not notice.

### Windowed

MGameD3D's init struct (built at `0x4214f0`, at `0x4d5e18`) carries a
fullscreen flag at `+0x2c`, copied to `0x1001240c`. The exe passes a
literal 1 (`0x427fe5`). With 0 the DLL's own windowed path runs
(`0x1000263c`): `AdjustWindowRectEx` + `MoveWindow` to a 640x480 client
area, `SetCooperativeLevel(NORMAL|FPUSETUP)`, a primary in the desktop's
format with a clipper on the window, an offscreen 3D back buffer (init
path 2), and the present at `0x10004d50` becomes a `Blt` of the back
buffer to the window's client rect - a stretch when the window is
larger. Fullscreen is `EXCLUSIVE|FULLSCREEN|ALLOWREBOOT|FPUSETUP`,
`SetDisplayMode(640, 480, 16)` and `Flip`. The window class is `WS_POPUP`
(`0x426b25`), so the window has no frame.

Three things stood in the way.

**The mode check.** Before the cooperative level, windowed or not, Init
runs `EnumDisplayModes` (`0x10002eb0`) and its callback (`0x10002f10`)
looks for the init struct's width, height and depth - 640x480 at 16
bits - and `E_FAIL`s the start when no listed mode matches. The window
sets no mode, so the check is for nothing there; and on one Windows 11
machine (NVIDIA, driver 610.62) DirectDraw lists no such mode - the
`d3dinit` log shows the enumeration succeeding and the match flag
clear, twice, as the exe tries the bring-up again. `anymode` makes the
result `S_OK`: `and eax, 0x80004005` → `and eax, 0`, four bytes. In
fullscreen an unlisted mode would then fail at `SetDisplayMode` with
the same box, so nothing is lost.

**The size of the target.** `IDirect3D3::CreateDevice` (`0x10003080`, on
the back buffer) returns `DDERR_INVALIDOBJECT` (`0x88760082`) on
Windows' own DirectDraw for a back buffer wider or taller than 2048 -
the `d3dinit` log shows the surface and its Z-buffer created at
2560x1440 and the device refused (`0x2313`), while 1920x1080 goes
through and 2560x1080 fails on the width alone. The line is the same
whatever the driver reports: AMD gives `dwMaxTextureWidth/Height` as
2048 in the device desc, one NVIDIA machine 16384, and both refuse at
2048. Making the device on a 64x64 dummy and pointing it at the back
buffer with `SetRenderTarget` (`0x10002d64`, which the DLL itself
calls) does not help: the runtime refuses the target there as well. So
on Windows without the dgVoodoo 2 add-on the resolution table written
stops at 2048 a side (WIDESCREEN.md, *The setting*), and the present
stretches the picture into the window. wined3d has no such line, and
neither do the D3D7 wrappers; those get the full table.

**dgVoodoo 2.** Runs the game once its `ddraw.dll` is in `MUSASHI\` and
`D3DImm.dll` beside the exe (above); the patcher's `dgvoodoo` add-on
fetches the latest release from GitHub (the release API, then the
`dgVoodoo2_*.zip` asset) and places those two with a `dgVoodoo.conf`
beside the DLL, where it is looked for first - fast video memory access
on, the watermark off, ALT+ENTER left to the game - stamped in
`MUSASHI\dgVoodoo.version`. It is on by default on Windows proper, told
from Wine by `ntdll`'s `wine_get_version`. Its device desc gives the largest
texture as 2048x2048 whatever the backend allows, and the texture format
enumeration gives every format the game's list holds but P4 (`fmt
00001fdf`), A1R5G5B5 chosen as on Windows. With *Fast video memory
access* off the textures come up white or as noise; on, the game draws
as it should, somewhat slower than Windows' own DirectDraw. The
multiplayer lobby's background came out black inside the 4:3 box with
the panel and the side colour right: dgVoodoo blits the game's
video-memory background surface as empty, DD_OK, while `Lock` reads it
whole; the lobby copies it through `Lock` when it finds that
(WIDESCREEN.md, *The lobby*). `surfmem` puts that surface in system
memory, where the blit carries it, and the copy stays a fallback. The
same setting is what blanked the team room's panels - *The lobby's
panels*, above.

A start dying in a refused re-init - window moved, surfaces made, device
refused, error box - left Windows' display stack wedged on two machines
until a reboot (or `Win+Ctrl+Shift+B`): every DirectDraw window after it
presented at 3 fps, and `EnumDisplayModes` stopped listing 640x480x16,
which is what `anymode` covers.

**The depth check.** The windowed path calls `GetDisplayMode` and refuses
a desktop whose depth is not the 16 bits it was asked for (`0x1000271e`,
`E_FAIL` → "Failed to initialize"); nothing after the check depends on
it, every surface takes the primary's format. `anydepth` skips it.

**The `.bg` pictures.** The full-screen pictures - title, loading, game
over, the course cards, all `.bg` files - are 16-bit 565, copied straight
into the locked back buffer row by row (`0x415271`, `rep movsd`; the
loader at `0x415180` converts 565 to 555 in place when the lock's green
mask says so, which a 32-bit mask also does). On a 32-bit desktop that
put two pixels' bytes into each pixel: the picture at half width.

The copy is now `bgrow.asm`, which reads the lock's description
(`0x4e6878`: size, pitch, surface, `dwRGBBitCount` at `+0x54`) and
expands 565 to XRGB8888 when the depth is 32. When the surface is not
the picture's size (a wide picture size) it composes the whole picture
on the first row into a surface `MGameD3D` keeps, for one blit to
stretch into the screen, and nothing on the rows after - WIDESCREEN.md,
*The .bg screens*.

`Title.dll` carries its own copy of the same loop for `TITLE640.BG`
(`0x100014ba`, the lock description on its stack, the source advanced at
the end), and gets the same stub assembled for that (`titlebg`). The
`.bg` path with brightness or contrast set goes through `0x46c900`
instead and is untouched. No other screen DLL locks the back buffer and
copies; the lobby goes through DirectDraw blits, the rest through
Direct3D.

### Borderless

The windowed path sizes the window to the picture (`MoveWindow` at
`0x100026be`, after `AdjustWindowRectEx`) and presents by blitting the
back buffer to the client rect, which DirectDraw stretches.
`fullwin.asm` replaces both ends.

**The window.** The `MoveWindow` call goes to a thunk that moves the
window to the monitor under the cursor (`GetCursorPos`,
`MonitorFromPoint`, `GetMonitorInfoA`, resolved through the DLL's
`LoadLibraryA`/`GetProcAddress` since it imports none of them), or leaves
it where the game asked if any of that fails. A framed window - ALT+ENTER
- is left as the player has it, since the init, and with it this call,
runs again on every screen change: the game tears the renderer down and
brings it back up between screens (`SetClipper(NULL)`,
`SetCooperativeLevel`, new primary, clipper and back buffer).

A `WS_POPUP` window the size of its monitor is what Wine reports to the
compositor as fullscreen, with no display mode behind it to restore on
activation.

**The present.** From `0x10004d7b` on it is replaced by one that fits
the back buffer's aspect into the client rect, fills the bars with
`DDBLT_COLORFILL` and blits the picture into the middle. The picture is
still 640x480, point-sampled up, until a wide size is chosen. The 96
bytes of the old present carry nine relocation entries and the call one;
all go, since the bytes are dead or relative.

The present keeps the counter after its blit in the annex, which is
writable for it, for `frametrace`; `QueryPerformanceCounter` is resolved
on the first present.

### Frame log

`frametrace`, a diagnostic applied by name, hooks the gate's entry
(`0x4287f0`, `mov eax,[0x4d6a3c]`) and its exit (`0x42890b`, the five
bytes before `pop ebx; ret`) and logs every drawn frame to `logs\\frames.log`
beside the exe: the counter at the entry, after the borderless present's
blit (found through the borderless patch's jump at MGameD3D's present),
at the exit, the step count and the gate's four flags (*Frame timing*),
with the budget and which counter in a header.

`tools/frames.py` reads it and splits each frame into work (step and
draw), blit and rest. An interval of two refreshes with two steps is the
catch-up; with one step, a present the display held, or a frame the game
chose not to catch up. The step count logged is `ebx`, which in the
Australian exe is the divisor's countdown - its count is in `edi`.
DEVELOPING.md says how to apply it.

### ALT+ENTER

The window procedure has cases for a handful of messages and hands the
rest to the text-input handler at `0x41fe20` (`call` at `0x426cbc`),
whose -1 means "not handled" and goes on to `DefWindowProcA`. That call
now goes through `altenter.asm`: `WM_SYSKEYDOWN` for `VK_RETURN` with
bit 29 of lParam (ALT) set and bit 30 (a repeat) clear toggles the
window and answers 0; everything else continues to the handler.

The toggle sets the style with `SetWindowLongA` - `WS_OVERLAPPEDWINDOW`
framed, `WS_POPUP` borderless, `WS_VISIBLE` kept - and places the window
with `SetWindowPos(SWP_FRAMECHANGED)`: framed, a client area of the
picture's size (from the init struct at `0x4d5e1c`) centred on the
monitor the window is on; borderless, that monitor's rect. The present
letterboxes into whatever client rect results, so the framed window can
be resized or maximised. The five user32 entry points are resolved once
through the exe's `LoadLibraryA`/`GetProcAddress` and kept in the
section, which is therefore writable.

`windowed` and `borderless` are the game's mode and cannot be left out.

### No mixer needed

Australian only. `MGAudio.dll`'s Init looks for a CD line on the mixer
for the volume slider; without one the European DLL returns `S_FALSE`,
the Australian `E_FAIL`, and Wine has none. The `jne fail` becomes a stub
that zeroes the control count at `+0x84` (uninitialised until the search
fills it) and eax, and jumps back to the allocation.

### The mix

The sound manager - in the exe and, as a copy of the same code, in every
screen DLL - gives each effect a −40..0 dB range and sets its ceiling at
`(step+1)/10` of it from the slider: 4 dB a step, 0 dB at 9. The CD music
followed a curve of its own in amplitude, the streamed music a range of
its own, so a step meant something different on each slider.

`asm/mix.asm` puts every buffer on one curve. The buffer's `SetRange`
(`0x10004380`) loads min and max through it, each mapped onto
`MIX_MIN..MIX_MAX` from `asm/mix.inc`, −43..−8: 3.5 dB a step, 9 the old
7, for every client. The streamed music - every client ends in the
streaming buffer's `SetVolume` (`0x10006940`) with the step × 1111 as a
0..10000 value mapped across the stream's own range - finishes that
mapping through the second routine, the step on the same curve plus
`STREAM_DB` (200), 0 off. The CD music's level is the music hook's,
below, on the same curve plus `CD_DB`. `tools/loudness.py` measures the
two musics against each other for those two offsets.

### Quieter defaults

The settings the game starts with are a block of 0x29 dwords in the
exe (`0x5a2348`, `STATUSDA`), copied into the live settings
(`0x4d6d50`, `[0x50afdc]`) at start (`0x427b6c`), the saved options
replacing them once there are any, and kept as `[0x50b10c]`, the block
every Options page's DEFAULT reads back (`Options.dll` `0x10005143`
takes `+0x58` to `+0x68`). The three volume sliders are its `+0x60`,
`+0x64` and `+0x68`, 9 each, the top. `voldefault` makes them 6: a first
start, or DEFAULT, sits 10.5 dB below the top on the mix's curve. The
block is the same in every build.

### Effects at full

Australian only. The volume routine sets each effect's ceiling from its
slider and then its level as a percentage of that; the other builds pass
100, the Australian's passes the slider × 11 - the slider twice - in the
exe and in its `Options.dll`, which re-applies on the way out of the
screen. The setting's load becomes `mov eax, 9`, which the × 100 × 0.111
after it makes 100; in the DLL the load's relocation entry goes with it.
The percentage is also how every build drives the engine's level by
throttle, so it stays a percentage.

### Music from files

*Music*, above, says what the DLL does with the CD. Three properties of
it shape the patch:

- The open routine (`0x10003100`) does not call through the import slot;
  it loads the slot into `esi` and calls `esi` twice, for the open and
  the time-format set. So there are twelve sites to rewrite, not eleven:
  the calls go to the hook, the load to a thunk that returns the hook's
  address. A load left in place sends the open to the real driver, and
  the first status it answers with `MCIERR_UNSUPPORTED_FUNCTION` makes
  MGAudio close the device.
- MGAudio issues its MCI commands from threads it creates per action
  (`CreateThread`, `TerminateThread`), and Wine's `winmm` refuses
  commands to a device from any thread but the one that opened it
  (`MCIERR_INVALID_DEVICE_NAME`, `0x107`). The hook therefore makes every
  device call from one worker thread of its own.
- The tracks play from a DirectSound buffer of the hook's own rather
  than through MCI's `waveaudio`, because of the slider. `mciwave`
  exposes no handle, and winmm's volume - `waveOutSetVolume` by device
  id, and by handle too - has been the application's audio-session
  volume on Windows since Vista: it moved the DirectSound effects with
  the music, and muted them every time the game sent 0, which it does
  between the loading screen and the start signal, and in Time Trial
  until the start. Wine treats the same calls as the wave device's,
  which is why it played correctly there. A buffer's volume is its own
  on both, and in the mix's units.

The DLL is relocated on every load (`SR2_MSG.DLL` holds its preferred
base). Each rewritten site carried a `.reloc` entry for its absolute slot
address at `site+2`; `apply_music` drops those, or the loader would add
the relocation delta into the new relative displacement.
`tools/musictest.py` relocates the image before running it for that
reason.

**The volume.** The CD-volume methods' entries jump into the blob. The
slider's step becomes hundredths of a dB on the mix's curve plus `CD_DB`
(300), −5 dB at 9, set on the track's DirectSound buffer; the exe's fade
before a stop, from full down by 10% a frame, is taken as amplitude
percent of that level. The `cdlevel` patch is what tells the menu's
level from the fade: the menu's CD-level set at `0x473c48` pushed flags
0, and now pushes `0x40`, a bit the DLL never read; the race's level and
the mute already carry bit 31. The full account is in
[asm/README.md](../asm/README.md), *music.asm*.

### Device Settings

A fourth item on the Options menu and the page behind it. *The Options
screen*, below.

### No registry

The game's file name string `SR2.CFG` (one, for the read at `0x427740`
and the write at `0x427880`) becomes `SR2.DSP`, so its 100-byte display
block (*The install contract*) keeps its own stock-shaped file and
`SR2.CFG` is the controls text from byte 0. `carry_display_block` copies
a stock `SR2.CFG`'s block there at patch time, once. `MGameReg`'s Open at
`0x47ef59` (21 bytes) becomes `xor esi,esi`, so `Software\SEGA` is never
created. *The registry* and *Gamepad* have the rest.

### HUD after the water

The tachometer's plate is alpha-blended, drawn with the rest of the HUD
(`0x429d70`, called from the race state's draw at `0x418ab1` while the
state's `+0x3c` says so) after the scene pass, at z `0.0002` with the
z-write on. The lake (WIDESCREEN.md, *The sea*) is not part of that
pass: it is a node of the root tree the frame object draws afterwards
(`0x4280a0`: the state's draw, then, with `[0x4d6a3c]` set and
`[0x4e68fc]` clear and a `BeginScene`, `0x470ff0` at `0x4280f2`, then
the present), a screen-space plane at z `0.96`–`1.0`, z-tested, meant to
show through the hole in the ground mesh. Under the plate it fails the
test, and the plate blends over what the scene pass left there - the
backdrop's flat grey. A `d3dtrace2d` with the `sr2 p` present markers
shows the order per frame: the HUD's lists, the sea's four strips, the
present. Stock does the same; the Australian build has no `[0x4e68fc]`.

`hudlast.asm` moves the HUD after the tree. Three entries:

- **state**, in place of the HUD call: draws the HUD there as before
  when the tree is not going to run - the game not running (a paused
  race), or the flag set - and otherwise draws nothing and notes the HUD
  as pending.
- **late**, in place of the tree draw: draws the tree and then, with a
  HUD pending, sets the full viewport through the exe's own wrapper
  (`0x46bfd0`, the rect at `0x4b12f0`, as the state's draw did before
  the HUD in split screen), draws the HUD and makes the reset the
  state's draw made after it (`0x46cec0`: colour key and blending off,
  on the renderer at `0x50b110`). The pending note, not the state's own
  flag, so a state of another kind never gets the race's HUD.
- **fade**, in place of the fade node's draw thunk. The fade is a node
  of the same tree (class vtable `0x49b644`: update `0x426860` takes the
  colour and alpha from the node's bytes at `+0x18`, draw `0x426930` is
  `mov ecx, [0x50b110]; jmp 0x46bd80`, the renderer's fade quad over the
  rect at its `+0x5650`, alpha at `+0x5668`, nothing drawn at 0). The
  quad is at z `0.00014` with the z-write on, under the HUD's `0.00024`,
  so a HUD drawn after the tree failed the test under it and appeared
  the frame the fade-in ended - seventeen frames into a race in a
  `d3dtrace`, a pop. This entry draws a pending HUD first and then the
  fade, so the fade stays over the HUD as it was, and *late* only draws
  a HUD the fade node did not.

`tools/hudlasttest.py` runs the three entries under Unicorn with the
exe's routines stubbed.

### Loading screens

The stage's card - `des_AC.bg` and the rest, or `loading.bg` - is an
object the exe creates when the loading screen opens (`0x41a6f0` picks
the file by course and mode, `new` of 12 bytes with the vtable at
`0x49b138`, the object kept at `0x4d6938`) and deletes the moment the
course has loaded, in the state step at `0x4195b0`: `call 0x418070`, the
deleting destructor through the vtable's first entry, the object zeroed
and `inc dword [ebx+0x14]` on to the next state. A load that took a
while on the hardware of 1999 takes well under a second now, and the
card is gone before it is seen.

`loadhold.asm` replaces the six-byte store of the new object at the
create (`0x41a7bb`, `mov [0x4d6938], ecx`) and the six-byte load of it
at the step (`0x4195be`, `mov ecx, [0x4d6938]`) with calls into its two
entries. The first makes the store and notes `GetTickCount` - imported by
all four builds - and the second waits, `Sleep(10)` at a time, until
3000 ms have passed since the note, then makes the load; `Sleep` is
resolved once through `GetProcAddress`.

The wait is a plain sleep: the game's loop does not run meanwhile, and
the picture stays on screen as the last frame presented. It is skipped
when no note was taken, so the other path that deletes the picture
(`0x419d00`, an aborted load) is left alone. `tools/loadholdtest.py`
runs both entries under Unicorn with the clock and `Sleep` stubbed.

### The connection screen

The multiplayer lobby's first choice (`0x43c160`, `BINDATA\connect\PROTOCOL\`)
is IPX, TCP/IP, MODEM or SERIAL: `CONNECT.BMP` is the panel with the four
labels baked in grey, and the drawer `0x43bd30` blits a 218x32 button
over each at y 54, 106, 158, 210 - `CONNECT_<row>_OFF`, `_ON` or `_ON2`
by the cursor, through the table at `0x4b4274` (five rows of four
surface indices for the ON states, five more from `0x4b42d8` for the
ON2 flash of the confirm). The cursor (`0x4edcc0`) wraps in 0..3, the
confirm stores it as the connection type at `0x4eace6` and goes to the
modem screen for 2, the session list otherwise; `OpenConnection` maps
the type to the DLL's kind (`0x43fff0`), takes the modem's latency as
10000 ms and the others' from `GetCaps`; SHOW TEAMS dispatches on the
type through `0x43efd8`, the IPX row searching at once and TCP/IP
through the IP entry. [NETWORK.md](NETWORK.md) has the rest.

With `lobby` the rows are INTERNET, DIRECT IP and LAN - the IPX, TCP/IP
and MODEM slots, types 0, 1, 2 - at y 82, 134 and 186, three rows at
the stock pitch centred in the panel (`LOBBY_ROWS`). Row 1's 134 does
not fit the drawer's `push imm8`, so that blit is re-encoded in place:
its `add esi, 4` goes, `push 0x86` takes the room, and the next blit
reads `[esi+8]`; the fourth blit is jumped over. The cursor wraps in
0..2, the confirm's `je` to the modem screen is two nops, the latency
test's `jne` a `jmp`, and the SHOW TEAMS table's third entry the first's.
`MPDATA.DAT`, which keeps the type from last time, has a stock 3 reset
to 0 at patch time.

The lettering is ITC Avant Garde Gothic Demi, 20 px capitals, spaced;
OFF is the ON at 98/255, ON2 the ON under a glow. `tools/labels.py`
sets each new label in URW Gothic Demi (the face's free clone, size 27,
7 px tracking, the glow a Gaussian of σ 2.4 at gain 2) - which
reproduces the stock buttons within a pixel - and bakes the three states
into `sr2-patcher.py` as zlib masks (`LOBBY_LABELS`, 7 KB), so the
patcher needs neither Pillow nor the font. At patch time it writes the
nine button files as 24-bit BMPs and repaints `CONNECT.BMP`: the stock
rows cleared, the OFF masks at the new rows a pixel left of the blit
(as the stock labels sit), through the nearest of the palette's 41
greys. Each file gets a `.bak`; the SERIAL and OTHER sets are not drawn
and not touched.

### The clear's height

Australian only. The build's mode setter clears the back buffer with the
width for both dimensions: at `0x441783` it loads `[WIDTH]` and pushes
that same value twice into the clear at `0x441180`, where Europe's
(`0x421a75`) and America's push the height as the first argument. The
clear zeroes width rows of a height-row surface. At 640x480 that is 160
rows past the end, which on a real card landed in whatever the driver
had left there; at 5120x1440 it is some three thousand seven hundred
rows past, and under wined3d the first frame takes a page fault - `rep
stosd` at `0x4411ce`, writing off the end of the surface, with ebx the
row's 0x2800 bytes and esi still counting down from the width.

The `clearsize` patch puts a thunk in the annex that hands the clear the
two globals the right way round - the height first, as Europe's caller
does - and the site takes a call to it. The thunk pops its return, pushes
the two, puts the return back on top and jumps into the clear rather
than calling it: the clear is cdecl and this caller cleans at
`0x441794`, so a thunk that called and returned would leave the width
where the return address belongs. `tools/clearsizetest.py` walks it.

### Gamepad

A pad bind goes in where the key it stands for enters the game, and the
keyboard is left as it was. A key the input wrapper reads as a bit gets
the pad in the wrapper, where every screen reading the bit sees it
(`pagepad`: Page Up and Page Down); a key a screen takes from a word of
its own gets the pad in that word (`padmenu`: the multiplayer screens'
menu word, `replaypad`: the replay controls'); a key the game never
reads as input gets the pad read where its effect is used (`sortpad`:
F6-F8 are accelerators, so the gallery reads LB and RB itself). Each
reads the pad through the page poll MGInput's annex publishes
(`PADPOLL`, the shared `asm/padpoll.inc`), takes an input past half its
range as down, and does nothing when the slot is empty.

`MGInput.dll` (`0x10000000`, relocated; one build in the European and
American releases, an older one in the Australian with the same
interfaces at other addresses) reads every action. Four patches touch
it: `xinput`, `dinput8`, `nogeneric` and, in the exe, `noregistry`.

#### The model

The exe's init (`0x47eff0`) makes a config per player, named `"0"`/`"1"`
at `+0xc`, attaches the keyboard device and loads it through `Persist`
(vtable `+0x30`, `0x10007510`; flags bit 0 save, bit 1 keep what is
there) - player 1's twice, unnamed and clearing (`0x47f094`), then named
`"0"` and appending (`0x47f0ca`).

An action is a `0x34`-byte record: id, repeat delay and rate in frames,
deadzone and saturation in 0..10000, up to eight source ids that are
ANDed, the first carrying the value. Its object is `0x15c` bytes:

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

Import and export are at `0x10008890`, `0x10008910`.

Ids: 0 accel, 1 brake, 2-5 up, down, left, right (the menus, with repeat;
4 and 5 are also the steering), 6 shift up, 7 shift down, 8 handbrake, 9
view, 10 enter, 11 escape, 12 start - the race's pause (`0x419306`) and a
confirm in the menus, like 10. Sources: 1-0xff keyboard scancodes,
0x101-0x168 joystick, 0x201-0x20b mouse, answered by the device's poll
(`0x100056c0`, `(this, source, &value, &range)`).

The config's update (`0x10007100`) has every record poll every attached
device, then finalise; `GetActionState` (`0x100078b0`) takes the largest
magnitude among an id's records, so a key record and a pad record for
one action coexist.

#### XInput

asm/padinput.asm is hooked at the load, the save, the update and the
device's poll. The Australian build has no poll method - its record
update (`0x10008170`) calls a static poll per device type - so there the
keyboard poll's address in that dispatch (`0x100081a8`, `0x10007e40`,
five arguments) is pointed at the annex's own entry. A third entry,
`(source, &value, &range)` for the Device Settings page, is published at
`PADPOLL`.

The poll answers sources `0x300 + player * 0x40 + input`: the sixteen
buttons as `0x80`/`0x80` like a key, the triggers over 255 past the
usual threshold, the eight stick halves rescaled past the player's
deadzone to 0..10000.

The update hook refreshes the config's player first: each side keeps an
XInput slot, takes the first free one when it has none, looking every 60
frames, and clears its state when the pad goes. Side 1 looks only while
side 0 holds a pad, so the one pad there is - at the start, or plugged
back in - is player 1's whichever side's look falls first. Before that,
a pad unplugged and replugged in the menu came back as player 2's (seen
in a `+xinput` log: side 1's look, a frame ahead, took slot 0, and side
0 then skipped it as held).

#### DirectInput 8

The DLL made its DirectInput object with `DirectInputCreateA(hinst,
0x500, &out, NULL)` (`0x1000294d`, through the thunk at `0x10008a30`,
the one `DINPUT.dll` import), took `IDirectInput2` from it
(`0x10002963`) and kept that at `+0x10` of the input object.
`EnumDevices(0, cb 0x10002300, &vector, ATTACHEDONLY)` at `0x100025e1`
collects every attached device, `DIDEVICEINSTANCE` by
`DIDEVICEINSTANCE`, with no type filter, and the device init
(`0x10003910`) takes `GetDeviceInfo` and `GetCapabilities` and asks each
device but the keyboard for `IDirectInputDevice2` (`0x100039c2`).

That enumeration runs through Windows' legacy `dinput.dll`, which is
where the starts that hang on a white window with certain HID devices go
wrong; `dinput8.dll` does not. Its objects carry the same vtables -
`IDirectInput8` matches `IDirectInput2` slot for slot, `CreateDevice`
`+0xc` and `EnumDevices` `+0x10` where they were, and
`IDirectInputDevice8` is `IDirectInputDevice2` with three methods after
- the enumeration flags and class values are the same numbers, and
`DIDEVICEINSTANCE`, `DIDEVCAPS` and `DIDEVICEOBJECTINSTANCE` keep their
DirectX 5 layouts, so the DLL's calls stand once the object is
DirectInput 8's.

asm/dinput8.asm makes it so, in three places:

- The create. The eighteen bytes of the call become a jump to it, and it
  calls `DirectInput8Create(hinst, 0x800, IID_IDirectInput8A, &out,
  NULL)`, found once through the DLL's own `LoadLibraryA` and
  `GetProcAddress` slots, the result back at the site's continuation. A
  machine without `dinput8.dll` gets `E_FAIL`, as a failed create did.
- The interface ids. The two in `.rdata` are rewritten to DirectInput
  8's, so the two `QueryInterface` calls succeed and hand back the same
  pointers.
- The device type. The one thing that changed meaning is
  `DIDEVCAPS.dwDevType`'s low byte, the device's kind at `+0x260` of the
  device object, which the DLL switches on as 2 mouse, 3 keyboard, 4
  joystick (`0x10003490`, `0x10003570`, `0x10006550`) and carries as
  the kind byte at `+0x24c` of the record the game and the Device
  Settings page see. DirectInput 8 says 0x12, 0x13 and 0x14-0x18 for
  the controller kinds, 0x11 for a device of no kind and 0x19-0x1c for
  a device control, screen pointer, remote or supplemental collection.
  The stub's second entry, called where the DLL first reads the byte -
  the `cmp byte [esi+0x260], 3` at `0x100039ac`; the Australian build's
  `mov edx, [esi+0x260]` at `0x100039f9`, it having asked for
  `IDirectInputDevice2` before - writes the old code over the new and
  then does what the displaced instruction did, the flags kept through
  the `ret`. 0x19-0x1c take the no-kind code, 1: the game can use such a
  collection no more than a 0x11, and left as joysticks they take the
  slot the exe asks for by kind (`0x47f0a6`, joystick index 0) from the
  pad itself. A device of no kind fails the DLL's own data-format and
  state lookups with `E_NOINTERFACE` and its slot in the list stays
  null, the state a skipped instance leaves.

The instance copies in the enumeration vector keep DirectInput 8's
`dwDevType`; nothing reads it, the loop over them (`0x100026ab`) looking
only at the instance GUID. This is what dinputto8 does for the DLL at run
time, done once at the three sites; DirectInput wheels and pads go on
working through the same calls. `tools/dinput8test.py` drives the DLL's
own create routine under Unicorn against a stubbed `dinput8.dll`, with
and without the DLL, and the kind entry across the type codes.

#### Devices of no kind

With the list enumerated, the loop at `0x100026ab` makes a device of
every instance whose GUID is not null: `CreateDevice`, the init above, an
object of the DLL's own, polled every frame. On a machine of today that
is a dozen things that can never give input - LED controllers, a stream
deck, an audio device's control collection, a receiver's spare
collections; the Xidi logs from the repack's testers list them - each
opened, each a place for a driver to stall a `CreateDevice`, which
DirectInput 8 does not save.

DirectInput 8 reports them as `DI8DEVTYPE_DEVICE`, 0x11, a device of no
kind, and asm/nogeneric.asm leaves those out: the loop's `je skip; mov
ecx, [esi]; push edx` after the null-GUID compare becomes a jump to it;
it makes the branch on the compare's flags, looks at `dwDevType` (eax
holds `guidInstance`, so `+0x20`), skips a 0x11 the same way the null
GUID is skipped - the list keeps a zero in that slot, a state the DLL
already handles - and does the two displaced instructions on the way to
the continuation. The four kinds above the controllers go the same way:
0x19 `DEVICECTRL`, 0x1a `SCREENPOINTER`, 0x1b `REMOTE` and 0x1c
`SUPPLEMENTAL`, which is what a composite pad's spare collections come
up as - an 8BitDo dongle presents a gamepad, a keyboard, a consumer
collection, a mouse and a vendor collection, and only the first is a
controller. Mice (0x12), keyboards (0x13) and every controller kind
(0x14-0x18, wheels 0x16 among them) go through as before. It needs
`dinput8`, whose type codes these are. `tools/nogenerictest.py` enters
the site as the DLL would, for a null GUID, each skipped type and each
kept one.

#### The store

The registry helper's load and save (`0x10008130`, `0x10008210`) become
the annex's own: a table of key and pad input per action per player and
the two deadzones, kept as text in `SR2.CFG`. A section a player and
device - `[1P Controller]`, `[1P Keyboard]` - of `Name = value` lines for
the eight driving actions and `Deadzone = 10` in percent. The names are
the page's with spaces as underscores, `-` for none; the `=` is optional,
an unreadable section header closes the section, unreadable lines keep
the defaults, the deadzone clamps to 0-90%. A file with the game's
100-byte block ahead of the text (from before *No registry* moved it to
`SR2.DSP`) is read past it.

A load generates the player's records: the action's key record and pad
record, then the menus' fixed ones - arrows (WASD for player 2) on
actions 2-5, and the D-pad and stick halves twice over, on 2-5 and on
the four the exe's screens read (below) - the bindable first, which is
what the page takes as a row's; only unnamed loads get records, or
player 1's would double. A save takes the table back out of the exported records (the
first key and pad source per action), a name beginning `DZ` the digits
after it as the deadzone, and rewrites the text.

The menus' left and right are the steering's actions, so their fixed
sources are *menu-only* - a key at `0x400` + scancode, read from the
keyboard device's array at `+0x308` (type byte `+0x260` is 3), or a pad
input with bit 5 set - and answer only while the exe's car table (`CARS`,
`0x4d64bc`) has no car in slot 0: the cars exist from a race's setup
(`0x412aac`) to its teardown (`0x412c67`), whatever the mode. Input
`0x3f` reads a player's deadzone.

#### The menus' directions

The exe's multiplayer screens - the driver select, the connection
screens and the team room - test a word of menu flags: bits
0-3 up, down, left, right, bit 4 confirm, bit 5 cancel, bit 15 Enter,
bits 13 and 14 back. The keyboard fills one such word (`0x4d5e08`) from
the exe's `WM_KEYDOWN` handler (`0x41fe20`: the arrows, CR at
`0x41feb3`, TAB and ESC at `0x42018f` and `0x420172`), never through
`MGInput`. The pad fills another (`0x4edcb4`) from the poll at
`0x43f8e0`, which packs the input wrapper's button mask (`[0x50b120] +
8`, vtable `+0x1c`); that mask is built each frame at `0x47f2d0` by a
fixed table of `GetActionState` calls, ±5000 the threshold: action 10
(enter) to bit 0, 11 (escape) to bit 1, 12 (start) to bit 6 and 2-5
(up, down, left, right) to bits 9-12, which the packing
`((m & 0x40) << 5 | (m & 0x3f)) << 4 | ((m >> 9) & 0xf)` turns into
flags 4, 5, 15 and 0-3. Both words are tested (`0x43bef0` the connection
screen, `0x437983` the team room's menu row, `0x436716` its list).

So the directions are the steering's actions 2-5, where the fixed
bindings already put the D-pad and the stick, and confirm, back and
Enter are the enter, escape and start rows, whose defaults are A, B and
Start; the fixed set carries those three as well, menu-only, so a
rebound pad still confirms and backs out of those screens. A row's fixed
inputs sit beside whatever the row is bound to. The poll has a repeat
of its own - it clears the low four bits of the previous frame's flags
every `[0x4b5638]` frames, so a held direction re-triggers - which
`padmenu`, below, takes out of play.

Three things keep a pad off the team room. There the wrapper's mask
carries nothing from an XInput pad - the connection screens take it,
and why the room does not is not settled - so the pad word stays empty.
The room is two tasks: the slot list (`0x4366b0`) takes up, down and
confirm from either word, but its way to the MENU row - a task it spawns
(`0x437b10`) on TAB - is bit 13 of the keyboard word alone (`0x4366c9`),
and the row's way back (`0x437983`) bits 13 and 14 of the same, which
no pad bit reaches; the list's confirm with no chat typed opens the
player's stat card (`0x43684d`), which any key closes - bit 31 of the
keyboard word, `WM_KEYDOWN`'s mark (`0x4366bb`) - and no pad bit sets
that either. And the poll's repeat of a held direction is the
keyboard's: `0x43f880` takes the delay and rate from
`SystemParametersInfo`, and a held stick walks the rows two frames a
step once the delay is out.

The `padmenu` patch (asm/padmenu.asm) goes around all three. The
poll's six-byte store of its level word at `0x43f94f` becomes a call
that asks MGInput's annex for side 0's D-pad, left stick, A, B, Start
and Back through the poll it publishes at `PADPOLL` (the page's poll,
`(source, &value, &range)`, sources `0x300` + the input; down is a value
past half its range). A, B and Start go into the level as bits 4, 5 and
15, and the wrapper's directions come out of it. The pad's directions
go the keyboard's way instead: into the keyboard word as bits 0-3, on a
change and then every 2 frames once held 30 - the walk `WM_KEYDOWN`'s
repeat gives a key. A bit there waits for the task that reads and
clears the word (`0x43687e`, `0x437a5c`, `0x43bb99` and the rest), so
no screen misses one; a pulse in the edge word, which the frame makes
and clears, reached the connection screens only now and then, and the
wrapper's level bits there ran the poll's repeat without its delay
whenever anything else was held. A press of Back sets bit 13 in the
same word - TAB to the list, back to the row - and any press sets bit
31, which closes the card as a key would. Then the edge against the
previous level and the three stores. The poll runs only from the
multiplayer controller (`0x43fcd9`), so no other screen sees any of
this.
`tools/padmenutest.py` runs the entry under Unicorn.
`tools/padbits.py` prints the action-to-flag table by running the
wrapper's update and the poll under Unicorn with `GetActionState`
stubbed (European offsets).

The name tables and defaults are data the patcher appends after the code
(`annex_tables`); `annex_records` and `annex_text` model the output.
`tools/padinputtest.py` runs the four entries under Unicorn against the
real DLL.

#### Page Up and Page Down

The wrapper's update (`0x47f2d0`) builds each player's level word from
a fixed table, one action per bit: 10, 11, -, -, -, -, 12, -, -, 2, 3, 4,
5 for bits 0-12, a value past ±5000 setting the bit (the Australian
build: any value). Bits 7 and 8 have no action, so only the keyboard
sets them - Page Up and Page Down in the wrapper's own scancode table
(`0x47f5c0`, the keyboard's word at `+0x44`, ORed into player 1's by
the query `0x47f750`). Two screens read them, through the level
(`+0x1c`): the Records page turns on them (`Record.dll` `0x1000798b`,
`0x10007a2c`, with a repeat of its own), and the car select takes a
held Page Up as the alternative colour (`MSelect.dll` `0x100091d3`: a
confirm sets a flag and counts 40 frames, the flag cleared on any frame
the bit is not in player 1's level; if it survives, the five cars that
have one take their other colour).
Nothing else in the exe or the DLLs tests the two bits after a read of
the wrapper.

The `pagepad` patch (asm/pagepad.asm) gives them the bumpers. The load
and test after the table loop (`0x47f506`, `mov eax, [esp+0x10]; test
eax, eax`; the Australian `0x4beaf8` compares with ebp, 0 there) become
a call that asks the annex's page poll for the player's LB and RB -
side `[esp+0x18]` of the caller - ORs them into the level at
`[esi-0xa0]` as 0x80 and 0x100, and makes the load and test for the
site's branch. `tools/pagepadtest.py` runs the entry under Unicorn with
each build's addresses.

The Replay Gallery's sort is not input the game reads at all: F6, F7
and F8 are accelerators in the exe's resources (VK_F6-F8, commands
40043-40045), and the window procedure's `WM_COMMAND` handler
(`0x428320`) sets the mode - 0 MODE, 1 CAR, 2 DATE - at `+4` of a block
at `0x4e6908`, turning the order over (`+8`) when the mode picked is
the one already set. The gallery gets the block as its init block's
`+0x6c` (the exe's gallery screen passes `+0x28` of its own object, the
block's `+0x6c` being its `+0x94`), and the list's browse state
(`0x1000271f`) compares its own copy of both every frame, sorting again
when they differ. Nothing a pad sends reaches an accelerator.

So the pad is read where the sort is used. The `sortpad` patch
(asm/sortpad.asm) makes the two instructions after the list's row
update in that state (`0x10002764`, `mov ecx, [esi+0x50]; and edi,
0xff`, the same in every build) a call that asks the annex's page
poll for side 0's LB and RB, keeps what was down, steps the mode left on
a press of LB and right on RB, round at both ends, and makes the two
instructions; the compare after them sorts the list as an F key would.
The order stays; an F key pressed again still turns it over, and the
keyboard's Page Up and Page Down do nothing here, as before. The DLL is
relocated at load, so the stub finds the image base from its own RVA
and the sort block's global (`0x100be620`) from it; the poll slot is an
exe address, filled per build. `tools/sortpadtest.py` runs the site on
the real DLL, relocated, under Unicorn.

#### The replay's controls

A replay's cameras do not read `MGInput`'s actions. The camera manager
(`0x411335`) keeps an object of its own (vtable `0x49b868`, made at
`0x440b40`, `0x38` bytes) and updates it every frame (`0x440c30`, from
`0x411811`): per player, `+8` the device kind, `+0x10` its index,
`+0x18` the edge, `+0x20` the level, `+0x28` the previous level,
`+0x30` the analog x in -127..127, `+4` the count - two in 2 PLAYER
BATTLE, else one. The level's bits are 0-3 up, down, left, right, 0x10
and 0x20 the meter on and off, 0x40 the screen switch (2 PLAYER BATTLE,
the winner) or the watched car (MULTIPLAYER), 0x80 and 0x100 the
revolving camera's zoom, the manual's smooth in and out: each frame held
adds or takes 1.75/120 from `+0xd8` of the camera, clamped to ±1.75,
which is added to the depth of its offset from the car (`+0x18`, copied
fresh from the camera table each frame, `0x44137e`), so the distance
stays where it was left.

The keyboard fills it from fixed scancodes (`0x440d20`): the arrows,
Insert, Delete, TAB, Page Up and Page Down for player 1; S, X, Z, C, T,
G and TAB for player 2 - the manual's table - and the analog ±127 from
left and right. A joystick adds to it only when the player's config had
one at start: the wrapper's setup (`0x47f0e9`) looks at the first
source of the config's steering record and, past `0x100`, attaches
joystick 0 and marks the player's kind at `+0x14` of its block in the
exe's input holder; the update then reads that device's `DIJOYSTATE`
straight (`0x440e20`) - the axes to the directions and the analog, the
POV on a kind-2 stick, buttons 1, 2 and 3 to 0x30, 0xc0 and 0x100. The
annex's records put a key first on every action, so the kind is always
the keyboard and an XInput pad, which only answers source ids, never
reaches it.

The camera switch (`0x411cf0`, reached while bit 2 of the game's `+0x44`
flags is set, which the replay's starts set: `0x451540`, `0x4516b2`,
the ten-year credits' `0x419b14`) takes up and down from the edge, 0x10
and 0x20 for the meter, 0x40 for the switch, and hands the object to
the camera's own input (`0x441860`): on the automatic and side cameras
left or right on the edge turns the driver's view to the rear or the
side camera to the other side; on the revolving camera the analog, or
left and right from the level when it is near 0, turns it, and 0x80 and
0x100 from the level zoom. The pause is the wrapper's Start edge, as in
a race.

The `replaypad` patch (asm/replaypad.asm) makes the pad a player's
whatever the kind. The two loads at the join of both paths
(`0x440cea`, `mov edx, [esi+8]; mov eax, [esi]`, where the edge is
made) become a call that asks the annex's page poll (`PADPOLL`) for the
player's side - `0x300 + player * 0x40` - bumpers, left stick,
triggers, Y and X, ORs past-half ones into the level (RB up and LB down,
the next and previous camera; the left stick's halves left and right;
RT 0x80 and LT 0x100, the zoom; Y 0x30, the meter; X 0x40, the switch),
sets the analog from the left stick's x when the keyboard left it at 0,
and makes the two loads. The D-pad, right stick, A and B are left out.
The routine is the same in every build. `tools/replaypadtest.py`
runs the real update on the patched exe under Unicorn with the input
objects stubbed.

### The Options screen

The `devices` patch adds a fourth item to the Options menu and the page
behind it.

#### The texture

`Options.dll` draws from `BINDATA\MISC\OPTIONS.TXR`: `RTEX`, a count,
16-byte entries `(format, size, bytes, 0)` and, from `0x1000`, the pixels
back to back. Format 0 is 565, 2 is 1555, 8 is 4444. Twelve textures; the
Dreamcast Device Settings page survives in them unused - both controller
diagrams (8, 9), every label and the full uppercase font (6), the
calibration bars (7). What is not there is a steering-wheel icon: sheet
10 holds car, speaker, monitor and a blank plate, and the blank plate is
the cursor's red frame, drawn as a nine-slice of 28-texel pieces.

#### Pages and sprites

`OptionsModeInit` (`0x10003770`) loads the TXR and binds ten *pages*
through `0x1000ed90`: a page is a table of 20-byte UV entries `(texture,
u0, v0, u1, v1)`, and the loader swaps each texture index for its handle
in place. A *sprite* is 32 bytes - page, quads, count, width, height, x,
y, 0 - and a *quad* 52: UV index, a rectangle about the sprite's centre,
four vertex colours.

`0x1000e850` draws a sprite at a position, scale and colour, `0x1000e5e0`
at its own position. Both put the quads on one list, which the flush
(`0x1000e390`) sorts by depth (`0x1000e510`, a stable merge on the value
the device makes of z) and draws far to near: a sprite at z 16 goes under
one at z 12, and among equals the order of submission stands. The menu's
page is `0x100ac9d8` with 54 entries, one `-1` between sprites; those
separators are spare, and `0xe` and `0x11` now hold "DEVICE" from sheet 6
and the new icon.

#### The menu

The menu itself (`0x10003dd0` init, `0x10003f40` exec) owns a cursor
(`0x1000ba40`) and an icon set (`0x10002330`), both over three-entry
tables at `0x1009c820` (frames), `0x1009c82c` (icons), `0x1009c838`
(labels), and draws the labels itself at `0x10003e10`. The cursor draws
the frame table's entry for the item in place while it rests, the first
entry at its animated x while it slides, at z 16 with its pulse as alpha;
the icons go at z 12, so the frame sits under the plate and shows as its
red holes and a 4-px outline. The menu's state after a confirm
(`0x1000421c`) draws the frame once more at z 14 while the icon set
zooms the icon.

That is five code references to the tables in all, and the patch moves
every one of them. Confirming returns the index with bit 15, and
`0x10003c6b` dispatches it through `0x10003dc0` to the page states; the
fourth slot was the exit state, never reached with three items. The stub
in the annex selects state 0xc. The four items sit at x 110, 250, 390,
530.

#### The item

The label is "DEVICE" over the stock "SETTINGS". The icon is on a
thirteenth sheet the patcher appends to `OPTIONS.TXR` (the count and a
16-byte entry in the 4 KB header, the pixels at the end; 256x256 like the
icon sheet; the loader sizes its handle and entry arrays from the count,
and the DLL's copy of the handles has room for 256). It is the monitor
icon's plate with the picture's box filled back to the plate's grey, and
a steering wheel cut out of it the way the stock pictures are - holes in
the plate, alpha 0 with a one-texel ramp, the menu's dark background
showing through - drawn by the patcher (`wheel_mask`), not copied from
anywhere, with the car icon's own UVs (the page's UVs are three-decimal
values, 126.2 texels across 126 pixels, and exact fractions sample
visibly differently). The label sheet is checked by the texels of its
font and label rows. Of the twelve sheets only sheet 4, the frame's
message lettering, differs between the English and the Japanese
`OPTIONS.TXR`, so the hint lettering is carried in the patcher
(`HINT_LETTERING`, the English sheet's texels) rather than cut from the
file being patched.

#### The states

The top-level machine (`0x10003af0`) has twelve states behind `cmp eax,
0xb` and a table at `0x10003d90`: 1 re-inits the menu, 2 runs it, 3/5/7
init a page and 4/6/8 run it, 0xb leaves. The table moves to the annex
with two more entries and the compare goes to 0xd: 0xc is the page's
init, 0xd its exec, both in asm/devices.asm, entered as every case is
with `esi` the Options object and leaving through the dispatcher's
epilogue (`0x10003cd6`).

Init binds the page's own UV table through `0x1000ed90` - once per load
of the DLL, flagged in the blob, since the binding writes handles over
indices in place (the stock pages are bound once, in `OptionsModeInit`;
the exe reloads the DLL for each visit) - and starts the slide-in. Exec
draws the list, moves the cursor, and slides: in from the right at 640
down by 40 a frame, out to the left on cancel or on confirm over BACK,
the menu's state set at -640, the stock pages' numbers.

#### The list

The list is 40-byte entries - kind, sprite or string, x, y, z or text
flags, alpha, red, green, blue in 256ths, and the cursor's hold on the
entry - built by `devices_page` in the patcher in the Game Settings
page's terms (`0x100025f0` draws it). Its header band, group plate and
row plate are that page's own sprites (`0x100a3128`, `0x100a3290`,
`0x100a4198`, found by their first quad), plates at z 14 with alpha
0xd8, text at z 10.

The text goes through the stock routine `0x1000df10` over its 14-px
glyph sprites (`0x1009c080`, one sprite a glyph, a 256-byte character map
at `0x100fcc04` it fills on first use): `(string, x, y, z, advance for a
missing glyph, sx, sy, alpha, r, g, b, table, flags)`, flags 4
proportional, 1 right-aligned, 2 centred. The table has letters, digits,
`.`, `+`, `-` only; the colon is a piece. The glyph cells carry a texel
of margin around the ink and need it: boxes cut to the ink render narrow
and ragged.

Geometry as the stock's: the band and heading at y 87, the group plate
at (48, 106), rows of 18 from (261, 106), 6 more between groups, group
text at x 56, action at 269, colon at 397, value at 405, the buttons at
y 404. Two groups, PLAYER 1 and PLAYER 2, seven rows each.

#### The cursor

The cursor is the stock's (`0x10002c30`): up and down through the rows
and the button row, DEFAULT then BACK with left and right between them,
wrapping; the stock's sounds, 0xe for a move, 0xf for a confirm, BACK
included, 0x10 for backing out. What it holds is drawn as Game Settings
draws it: the row's plate (0x100, 0x100, 0, 0), its group's (0x100,
0x100, 0x20, 0x20), the button (0x100, 0x100, p, p) and the row's values
white with alpha 0x80 + p/2, p the page's pulse, 0 to 0x100 and back by
0x10 a frame (`0x10002a23`). Each entry carries which rows hold it and
how.

The page shows one player at a time: a selector row - the group plate
centred, PLAYER 1 or 2 on it, left, right or confirm switching - then
the KEY and PAD headings and the nine rows, the eight driving actions and
the deadzone, on Graphic Settings' own row sprite - a 123-px label plate,
a 30-px fade, a 273-px value plate, three quads - at its x and 24 px
apart as it spaces them.

#### Binding

The values are live. The page reaches the game's input objects through
the holder (`0x100b9464`, the exe's `0x50b120` block): its `+8` is the
exe's input wrapper (vtable `0x4a158c`; `+0x14(mask)` a player's
pressed-edge key bits), whose `+4` is `MGInput`'s input object, and from
there `GetConfig` (`+0x34`), `GetDevice(3, 0)` (`+0x20`) for the keyboard
and its `GetState` (`+0x38`, the 256 key bytes), the config's record list
at `+0x124` - a pointer to the head node of a ring of (next, prev,
record) - and `Persist` (`+0x30`) to save (*Gamepad*). The pad comes
through the poll the annex publishes at `PADPOLL`, a dword in the
writable room past the end of `.data` (`0x5a1ff0`; Australian
`0x60bff0`), since the Australian device has no poll method.

A row's key record is the first of its action with a source under 0x100,
its pad record the first at 0x300-0x37f without the menu-only bit.
Confirm on a row snapshots what is down and waits: the row pulses blue to
white and the bar says to press the button. A key or pad input released
since the wait began and pressed binds - the row that had it, either
player's for a key, the same player's for a pad input, takes the row's
old one - and both configs are saved; ESC, or Start held 60 frames, gives
up. Left and right on the deadzone row step it 5%, saved through a
`DZnnnn` name. DEFAULT puts the shipped set back from the page's data
block, which follows the strings (`bind_data`): the rows' action ids and
a live flag, the defaults, the value strings the page fills, a name per
scancode and per pad input. `tools/devicestest.py` drives the routines
under Unicorn against stubs for those objects.

#### The hint bar

The hint bar under every stock page belongs to the frame object
(`0x10001cc0`), which pops one of fifteen lettered messages in and out
by a message number in `0x1009c784` (`0x100021b0`, height 0 to 1 by 0.1
a frame, the bar growing from its bottom edge at y 451). All fifteen are
lettered, so the page leaves that at -1 and draws its own: the bar's
plate and white strip copied from message 14, grown the same way once
the page is in place and dropped before it leaves.

On it is one of two lines set letter by letter from the frame's own
lettering - sheet 4, six lines in a condensed face, dark ink on opaque
white - one texel box a letter at the English sheet's boxes, from the
carried `HINT_LETTERING` (`HINT_GLYPHS`; 17 rows from a row above each line's ascenders, since the
two lines the capitals come from sit a row lower against their tops), a
texel apart, 5 for a space, onto white on the appended sheet at patch
time, two texels of white beyond each end so the edge samples filter to
white and not to the clear gutter. The lines say what those six lines'
letters allow; there is no N or R among the capitals, so no ENTER.

The new data carries absolute pointers, so the annex gets a relocation
block appended to the directory in `.reloc`'s zero tail.

## The install disc

Disc 1 (`diskid.1`) is InstallShield 5: `setup.exe`, `setup.ins`
(compiled script), `data1.cab` (370 MB, single volume), `_sys1.cab`,
`_user1.cab`, `layout.bin`, `os.dat`, `lang.dat`,
`setupdir/<lang>/_setup.dll`, plus a `directx/` runtime, `dxgo.exe`,
`dsetup*.dll`, the six `msg_?.dll` and `miscdll.dll` loose for the
script's own CPU check.

`setup.ins` strings show what it did: components *Compact*/*MEDIUM*/
*FULL*, a *PentiumIII Files* component gated on `CheckKatmai`,
`LAUNCH.exe -musashi` for COM registration, `SR2_CPL.cpl` to the system
folder, the DirectPlay lobby key, and HEAT (Sega's online service)
shortcuts.

### Reading the image

`open_source` takes a `.cue` (the first data track of the bin it names,
found beside the sheet whatever path the sheet carries), an `.iso` or a
bare `.bin`, a mounted folder, or `data1.cab`. `DataTrack` finds the
sector form by looking for `CD001` at sector 16 under each of
MODE1/2352, MODE2/2352, MODE1/2048 and MODE2/2336, so a cue sheet naming
the wrong mode still works. `iso_root`/`iso_entries` walk ISO9660
directory records (no Joliet, no Rock Ridge - names are the `8.3;1` ones,
lowercased). `DiscFile` presents one extent as a file object, and
`Cabinet` reads `data1.cab` through it without extracting the 370 MB
first. Multi-extent files are refused; `data1.cab` is well under the 4 GB
extent limit.

### `data1.cab` (InstallShield 5)

Read by `Cabinet` in the script. Layout, all little-endian:

- Common header at 0: signature `0x28635349`, version (`0x01000004`
  here), volume info, cab descriptor offset (`0x200`), cab descriptor
  size.
- Cab descriptor: at `+0x0c` file table offset (relative to the
  descriptor), `+0x14` file table size, `+0x1c` directory count, `+0x28`
  file count; at `+0x3e` 71 file-group list heads.
- File table: `dirs + files` DWORD offsets, relative to the table's
  start. Directories are NUL-terminated names. A file descriptor is name
  offset, directory index, flags (u16), expanded size, compressed size,
  20 bytes, data offset. Flags: `1` split across volumes, `4`
  compressed, `8` invalid (20 such entries here, blank).
- File group node (offsets relative to the descriptor): name offset,
  descriptor offset, next. The group descriptor holds first and last
  file index at `+0x4c`. Groups are contiguous index ranges.
- File data: at the data offset in `data1.cab` itself. In the
  `0x01000004` cabinet a compressed file is one raw deflate stream - no
  zlib header, and no final-block marker, so the stream is read to the
  expected size and not to EOF. The `0x01005100` cabinets on the other
  two pressings store it as chunks, each a u16 length followed by a
  complete raw deflate stream of 10240 bytes of output; the chunks are
  inflated in turn until the expected size is reached.

Checked against unshield's listing (5,725 files in 25 groups) and against
a Pentium III install (every extracted file identical), from the cab
directly and through a disc image.

### Groups

| Group | Files | MB | Content |
| --- | --- | --- | --- |
| Program Executable Files | 38 | 12.2 | base exe, screen DLLs, `MUSASHI\`, `LAUNCH.EXE`, `SR2.CFG`, `SR2_SAVE.DAT`, `MPDATA.*` |
| PentiumIII Modules, AMD Modules | 6 each | 5.1 | the six CPU-specific files |
| English, French, German, Italian, Spanish, Japanese | ~337 | 5.2 | `SR2_MSG.dll`, `README.txt`, `PICS\`, `HELP\` |
| * Files | 1 | 0.3 | `SR2_CPL.cpl` per language |
| BINDATA 0 | 207 | 41.7 | `SEDATA` (sound effects), `BGM` |
| BINDATA 1 | 2354 | 27.9 | small models, tyre textures, `TENYEAR`, `ARCADE`, effects, UI objects |
| BINDATA 2 | 471 | 74.3 | car body textures, engine samples, `800x600`, root `.bg`/`.txr`/`sky*.mdl` |
| BINDATA 3 | 512 | 348.0 | course data, `TENYEAR`, `CAR`, `CHAMPAGN`, `connect`, `chat` |
| English Binary, UK Binary | 24 | 25.2 | `MISC`, `chat`, `meterNNus.txr` (the two are identical) |
| Japanese Binary | 18 | 23.3 | `MISC` |
| Carprofile English / Japanese | 18 / 19 | 42 / 59 | `BGM\cp_*.wav` narration |
| Cabinet Files | 1 | 0.1 | `CABINET.DLL` for Windows 95 |

The four `BINDATA` tiers are one asset set split by size to make the
compact/medium/full install sizes; no path appears in two tiers with
different content. A full install is the whole set on disk, not higher
detail.

## The play disc

Disc 2 (`diskid.2`, volume label `SEGARALLY2` on every pressing; the
thirteen audio tracks are under *Music* above) holds the same assets as
MS cabinets, 230 MB, MSZIP-compressed (plain deflate): one
`bindata\<dir>.cab` per tier directory, `bindata\tenyear\N_M.cab` for
the 41 ten-year courses, `bindata\root.cab` for the root-level files.
Every cabinet checked (`root`, `serial`, `adv`) contains exactly the
files the tiers hold. `diskid.2` is the text `Please enjoy SEGA RALLY
2.` The disc is not needed by a full install.

The pressings hold one soundtrack: stripped of digital silence, the
American and Australian tracks are bit-identical and the European within
eleven samples. Europe trims the tail; the other two keep two seconds of
it per track, and America adds 62 ms of lead. A rip from any of them
plays the same music, with the disc's own silence at the loop. The
DigiCube and MediaKite play disc has the same thirteen tracks, 11
samples off the Australian as the European is.

## What is not done

- One start on Windows with borderless failed with `E_FAIL` through
  `0x4404b0` from the `jl` at `0x427e05`; under WinDbg every return in
  `0x421330` - MGameD3D Init, MGameGL Init, its `+0x18`, `0x421670` -
  was 0, so it is not deterministic and has not been seen twice.
- What `LAUNCH.EXE` and `MUSASHI\SR2.dll` offer, and `SR2_SAVE.DAT`'s
  layout beyond the records table.
- Widescreen: the resolution value text's exact place and whether every
  2D element scales are to be checked on the running game; the `.bg`
  path with brightness or contrast set (`0x46c900`); the car select's
  carousel (WIDESCREEN.md, *The 3D*).
- Pacing by the display on Wine: the game free-runs at 60.000 Hz there.
