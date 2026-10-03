# The game

This document describes the game as it shipped: the executable and its
builds, Musashi, startup and files, and the two discs. What the patches
change is in [NOTES.md](NOTES.md); addresses and file offsets are in
[MAP.md](MAP.md).

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

A row of `BUILDS` holds four things: the fingerprints of fifteen files
(the six the P3 build replaces and the nine more the patches touch),
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
itself, and one different branch in Init (NOTES.md, *No mixer needed*).

#### The patched files

Twelve files are patched in every build: `SEGA RALLY 2.exe`,
`MUSASHI\MGameD3D.dll`, `MUSASHI\MGameGL.dll`, `MUSASHI\MGAudio.dll`,
`MUSASHI\MGSound.dll`, `MUSASHI\MGInput.dll`, `MUSASHI\MGNetWk.dll`,
`Title.dll`, `Options.dll`, `ReplayGallery.dll`, `Record.dll` and
`AdvTelop.dll`. So are eleven sheet files under `BINDATA\MISC`
(`OPTIONS.TXR`, `Record.txr`, `TITLE.TXR`, `ADV_TXT.TXR`, the three
`Rank*.txr` and the four `RG_*.txr`), the lobby's art and `MPDATA.DAT`. Each
patched file gets a `.bak` beside it, which is the untouched original.
Four files are new, `BINDATA\chat\TAB_MENU_SEL.BMP`, `TAB_MENU_SEL2.BMP`,
`TAB_MENU_BACK.BMP` and `TAB_MENU_BACK_SEL.BMP`, which a restore takes away.
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
and save replaced (GAMEPAD.md), the key is never made. That is also what
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

The in-game options live in `SR2_SAVE.DAT`. With the `noregistry` patch the
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

The `frametrace` diagnostic is described in NOTES.md, *Frame log*.

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
