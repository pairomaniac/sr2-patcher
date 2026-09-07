# Notes

How the game works and what the patcher does about it, rather than how to
use it. For using the patcher see [README.md](../README.md); for addresses
and file offsets see [MAP.md](MAP.md).

Everything below was read off the retail English release (disc stamps
20-21 Oct 1999, VC6 linker 6.0) with pefile, capstone and unshield. Nothing
has been traced on a running game yet.

## Patches

| Patch | File | Offsets | Change |
| --- | --- | --- | --- |
| **No disc required** | `SEGA RALLY 2.exe` | `0x267c0`, `0x7572e` | the startup check returns 0, "found" (`mov eax,[esp+4]` → `xor eax,eax; ret`); the loader constructor's drive scan replaced by `lstrcpyA(disc root, exe dir)` and a jump to its epilogue |
| **Z-buffer detach crash** | `MUSASHI\MGameD3D.dll` | `0x2930`, `0x2b31`, `0x2d11`, `0x37f4` | `call [ecx+0x20]` → `add esp,0xc` - `DeleteAttachedSurface(0, NULL)` on the back buffer skipped |
| **Music from files** | `MUSASHI\MGAudio.dll` | appended `.sr2m` section, 12 sites, the entry point | every `call [__imp__mciSendCommandA]` → `call hook; nop`; the `mov esi, [__imp__mciSendCommandA]` at `0x10003108` → `call hookaddr; nop`; entry → the setup thunk; see [asm/README.md](../asm/README.md) |

Offsets are file offsets. Neither file is relocated or has an overlay: in
the exe, VA = offset − 0x400 + 0x401000 inside `.text`; in `MGameD3D.dll`,
VA = offset + 0x10000000.

### Z-buffer detach

`MGameD3D` keeps the back buffer at `0x10012554` and the Z-buffer at
`0x1001255c`. Before it creates the Z-buffer (two init paths, `0x10002b25`
and `0x10002d05`), when it releases it (`0x10002920`) and at teardown
(`0x100037df`) it calls the back buffer's `DeleteAttachedSurface(0, NULL)`
with a literal null and ignores the result. DirectX 6 answers with an error
code; Wine's ddraw does the same; the ddraw in Proton (Proton-CachyOS at
least) dereferences the null and the process dies in the SEH handler, seen
as an immediate exit with no window. The four calls become `add esp, 0xc`,
which leaves the stack as the stdcall would have. Under plain Wine the
call was already a no-op with an error code, so nothing changes there. If
real DirectX treated the null as "detach everything", the difference is a
Z-buffer that stays attached until the back buffer goes - a leak at exit,
not a fault.

## The executable

The exe is a shell: main loop, file loader, the Musashi glue, the
network lobby (WSOCK32, IPX, serial, modem) and the results/records
screens. Every other screen is a DLL loaded by name with four exports
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
`CoCreateInstance`) and `WINMM` (`timeGetTime`). No DirectX DLL is imported
by the exe or by any screen DLL. `cabinet.dll` (FDI) is loaded by name for
the play disc's cabinets. `QueryPerformanceCounter` is imported; the frame
timing has not been looked at.

Sections: `.text`, `.rdata`, `.data`, `STATUSDA`, `METERDAT`, `MYDATA`,
`ALIGN16D`, `MGAMEMAT` (P3 only, 512 KB writable, the SSE scratch),
`.rsrc` (icon, accelerators, version - no manifest).

### Three CPU builds

`data1.cab` carries the base build and two overlay groups, *PentiumIII
Modules* and *AMD Modules*, each replacing the same six files (README,
*Builds*). The P3 exe carries about eighty SSE instructions (`movups`,
`mulps`, `addps`, `shufps`) in its vector paths; `MGameGL.dll` is where
the rest of the SIMD math lives, which is why the Musashi renderer is
among the six. The three builds compute physics differently, so netplay
and replays between builds are not expected to match. That is the reason
to support one build, and the P3 one is the obvious choice.

### The processor check

`0x444be0`: `LoadLibrary("MISCDLL.DLL")`, `GetProcAddress("CheckKatmai")`,
call with a pointer to a DWORD, expect 1, else `MessageBox("CPU Version
error")` and return −1. `CheckKatmai` (`miscdll.dll` `0x10001020`) is
three tests: CPUID present (EFLAGS bit 21 toggles), `CPUID(1).EDX &
0x02808001 == 0x02808001` (FPU, MMX, FXSR, SSE), and an SSE instruction
executed under SEH. No vendor or family test. It passes on every x86 made
since 1999, so no patch; if `miscdll.dll` were missing the exe would fail
at `LoadLibrary` first.

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
| `{ACEF8F00-D517-11D1-A496-0000C02DB0F3}` | `MGAudio.dll` | `WINMM.dll` | audio playback |
| `{0D5837F0-3E3C-11D2-924E-00A0C9697E45}` | `MGNetWk.dll` | `DPLAYX.dll` | DirectPlay networking |
| `{EE799FC0-D56F-11D2-8D16-00105A6B7166}` | `MGameReg.dll` | `ADVAPI32` | registry (`Software\%s\%s`) |
| `{F8743DC0-627C-11D2-BD4E-0000C02DB0F3}` | `MEvent.dll` | - | internal |
| `{08A33BE0-61C6-11D2-BD4E-0000C02DB0F3}` | `MStream.dll` | - | internal |

`MUSASHI\SR2.dll` is the launcher's settings page (COMCTL32), not used by
the game.

Two consequences:

- DirectDraw, DirectInput and DirectSound are imported by name by the
  Musashi DLLs, so wrapper DLLs (`ddraw.dll` and so on) placed beside the
  exe are found by the normal search order. No reroute patch needed.
- Without registration every `CoCreateInstance` fails. The installer ran
  `LAUNCH.exe -musashi` to register. The patcher instead writes an
  application manifest beside the exe that depends on assembly `MUSASHI`,
  and `MUSASHI\MUSASHI.manifest` with a `comClass` per DLL. Windows
  honours an external `.exe.manifest` because the exe embeds none.
  Untested on Windows as of this writing.

`MGameReg.dll` writes to the registry at runtime. Whether it also expects
something the installer seeded is not known; nothing in `setup.ins` writes
under `Software\` except the DirectPlay lobby key
`Software\Microsoft\DirectPlay\Applications\SEGA RALLY 2`.

## Startup and files

### The install contract

No registry reads in the exe. At startup:

1. `0x427450`: `GetModuleFileNameA`, open `SR2.CFG` beside the exe. Must
   exist.
2. `0x4274e0`: `GetLogicalDrives`, for each drive `GetDriveTypeA ==
   DRIVE_CDROM`, `GetVolumeInformationA` label `SEGARALLY2`, open
   `X:\DISKID.2`. Returns the drive index or −1.
3. `0x4273c0` wraps 2: on −1, `MessageBox` with a "insert disc" string from
   `SR2_MSG.dll` (id 2 or 3, depending on whether `SR2.CFG` was found) and
   retry, or give up. Returns 0 for found. This is the nodisc site.

`SR2.CFG` is 100 bytes and is read straight into the settings block at
`[0x50afe0]` (`0x427740`): the string `display`, then at `0x20` five
DWORDs `2, 2, 1, 1, 2` as shipped, written by `LAUNCH.EXE`, meanings not
traced. Two fields are overwritten after the read: `+0x5c` the disc flag
(below) and `+0x60` the language from `GetUserDefaultLangID` (`0x4272b0`,
1 English, 2 French, 3 German, 4 Italian, 5 Spanish, 6 Japanese).
The loader switches to the `BINDATA\800x600\` asset set when
`[[0x50afdc]+0x50] == 1` (`0x476512`), so one of them is the 640x480 /
800x600 choice.

### The loader

`0x476260` constructs the loader object. Two prefixes: `+0x108` is the exe's
directory (`GetModuleFileNameA`, cut after the last backslash); `+0x4` is the
play disc's root, from the same drive scan as above but done again here,
empty if not found.

`0x476a50` opens a file. Three tries, in order:

1. `<exe dir>BINDATA\<dir>\<file>` - a loose file (`0x4764e0` builds the path)
2. `<exe dir>BINDATA\<dir>.CAB` - a cabinet beside the exe (`0x476780` builds the name)
3. `<disc>BINDATA\<dir>.CAB` - the cabinet on the play disc

Cabinets are read through `cabinet.dll` FDI. Local files win, so a full
install never opens the disc for data.

### The disc flag

The mode select dims everything but MULTI-PLAYER, OPTIONS and EXIT when
`settings+0x5c` is 0. It is set at `0x42775f` (after `SR2.CFG` is read)
and `0x426ef8` as `isalpha(*root)`, where `root` is the loader's disc
root at `+4` (`0x476ef0` returns its first byte). So the disc dependency
is two-fold: the startup check at `0x4273c0` for the dialog, and the
loader's own scan for the menu. The nodisc patch handles both: the check
returns "found", and the constructor copies the exe directory into the
root slot. The root's first character then is a drive letter, the flag is
1, and the loader's third fallback looks for cabinets in the install
folder. A UNC install path (`\\server\...`) would still read as no disc.
The same drive letter is formatted into `%c:\AUTORUN.EXE` at `0x4277d0`;
nothing in the exe reads that buffer.

### RallyDebug.ini

Read with `GetPrivateProfileStringA`: `[DebugSettings]` with `DebugInfo`,
`CourseCollision`, `CarCollision`, `CPUCar`, `Course`, plus a debug overlay
`Total:%5dKB Used:%5dKB Free:%5dKB Quality:%s FPS:%2d TPF:%5d` and a
`DebugDLL.DLL` hook. Not investigated further; it is the game's own
equivalent of an extras menu.

### Music

`MGAudio.dll` is the only user of `winmm`: `mciSendCommandA` for the CD,
`mixer*` for its volume. It opens the device by type ID
(`MCI_OPEN_TYPE|MCI_OPEN_TYPE_ID`, `MCI_DEVTYPE_CD_AUDIO`, at `0x10003100`),
sets TMSF, plays with `MCI_FROM` (track N+1 in the low byte, `0x10003160`),
seeks to a TMSF it computes from milliseconds (`0x100032f0`), pauses,
resumes, stops, closes, and polls `MCI_STATUS` for position, track count
and per-track length (`0x10003220`–`0x100032df`). The `MCI_NOTIFY` flag it
sets on play goes nowhere: nothing in the game handles `MM_MCINOTIFY`.
Position is polled against `GetTickCount` bookkeeping around `0x100023cf`,
which is presumably how a course loops.

The open routine (`0x10003100`) does not call through the slot; it loads
it into `esi` and calls `esi` twice, for the open and the time-format set.
The first cut of the patch rewrote only the eleven `FF 15` calls, so the
open still reached the real driver, Wine's `mcicda` answered the first
status with `MCIERR_UNSUPPORTED_FUNCTION` and MGAudio closed the device:
the game ran silent with the track table full. The load is now rewritten
too, to a thunk that returns the hook's address.

MGAudio calls MCI from threads it creates per action (`CreateThread` and
`TerminateThread` are among its imports): in one run the play came from
thread `01a4`, the stop from `01b4`, the next play from `01b8`. Wine's
`winmm` refuses commands to a device from any thread but the one that
opened it (`MCIERR_INVALID_DEVICE_NAME`, `0x107`), so a `waveaudio` device
opened by the hook on the first play was unreachable afterwards: the first
track played and nothing ever changed it. The hook therefore runs all its
string commands on a worker thread of its own.

The rewritten call sites were `FF 15 <slot>`, each with a `.reloc` entry
for the absolute slot address at `site+2`. Writing `E8 rel32 90` over them
without dropping those entries left the loader adding the relocation
delta to the middle of the displacement whenever the DLL moved - which it
always does - and the first MCI call jumped to `0xDEDDF000`. `apply_music`
turns the eleven entries into padding; `tools/musictest.py` relocates the
image before running it, so a left-over entry fails the check.

The play disc's audio: tracks 2–14, each in its own bin in the Redump
dump with a 150-sector pregap at `INDEX 00`. The ripper starts each track
at `INDEX 01` and stops at the end of its file.

## The install disc

Disc 1 (`diskid.1`) is InstallShield 5: `setup.exe`, `setup.ins` (compiled
script), `data1.cab` (370 MB, single volume), `_sys1.cab`, `_user1.cab`,
`layout.bin`, `os.dat`, `lang.dat`, `setupdir/<lang>/_setup.dll`, plus a
`directx/` runtime, `dxgo.exe`, `dsetup*.dll`, the six `msg_?.dll` and
`miscdll.dll` loose for the script's own CPU check.

`setup.ins` strings show what it did: components *Compact*/*MEDIUM*/*FULL*,
a *PentiumIII Files* component gated on `CheckKatmai`, `LAUNCH.exe -musashi`
for COM registration, `SR2_CPL.cpl` to the system folder, the DirectPlay
lobby key, and HEAT (Sega's online service) shortcuts.

### Reading the image

`open_source` takes a `.cue` (the first data track of the bin it names,
found beside the sheet whatever path the sheet carries), an `.iso` or a
bare `.bin`, a mounted folder, or `data1.cab`. `DataTrack` finds the sector
form by looking for `CD001` at sector 16 under each of MODE1/2352,
MODE2/2352, MODE1/2048 and MODE2/2336, so a cue sheet naming the wrong
mode still works. `iso_root`/`iso_entries` walk ISO9660 directory records
(no Joliet, no Rock Ridge - names are the `8.3;1` ones, lowercased).
`DiscFile` presents one extent as a file object, and `Cabinet` reads
`data1.cab` through it without extracting the 370 MB first. Multi-extent
files are refused; `data1.cab` is well under the 4 GB extent limit.

### `data1.cab` (InstallShield 5)

Read by `Cabinet` in the script. Layout, all little-endian:

- Common header at 0: signature `0x28635349`, version (`0x01000004` here),
  volume info, cab descriptor offset (`0x200`), cab descriptor size.
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
- File data: at the data offset in `data1.cab` itself. A compressed file
  is one raw deflate stream - no zlib header, and no final-block marker,
  so the stream is read to the expected size and not to EOF.

Checked against unshield's listing (identical, 5,725 files in 25 groups)
and against a Pentium III install (every extracted file identical), from
the cab directly and through a MODE1/2352 image built around it.

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

Disc 2 (`diskid.2`, volume label `SEGARALLY2`, no audio tracks): the same
assets as MS cabinets, 230 MB, MSZIP-compressed (plain deflate): one
`bindata\<dir>.cab` per tier directory, `bindata\tenyear\N_M.cab` for the
41 ten-year courses, `bindata\root.cab` for the root-level files. Every
cabinet checked (`root`, `serial`, `adv`) contains exactly the files the
tiers hold. `diskid.2` is the text `Please enjoy SEGA RALLY 2.` The disc is
not needed by a full install.

## What is not done

- The manifests work under Wine and Proton; Windows has not been tried.
- The music patch is verified under Unicorn, not yet in the game; the
  BGM volume slider does not reach the WAV playback.
- `SR2.CFG` values, the 640x480/800x600 switch, and what `LAUNCH.EXE` and
  `MUSASHI\SR2.dll` offer.
- Frame timing, input, resolution: nothing traced yet. The renderer is
  `MGameGL.dll` + `MGameD3D.dll`, so resolution work lives there rather
  than in the exe.
- Whether `MGameReg.dll` needs anything seeded.
