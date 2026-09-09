# Notes

How the game works and what the patcher does about it, rather than how to
use it. For using the patcher see [README.md](../README.md); for addresses
and file offsets see [MAP.md](MAP.md).

Everything below is read off the retail European release (files stamped
20-21 Oct 1999, VC6 linker 6.0) with pefile, capstone and unshield, and
checked on the game running under Wine and Proton. The American and
Australian releases map onto it; *Builds* says how far.

## Patches

| Patch | File | Offsets | Change |
| --- | --- | --- | --- |
| **Windows 9x check** (Australian only) | `SEGA RALLY 2.exe` | `0x4b3b0` | `0x44bfb0`, "Please run on Windows 9x." unless `GetVersionExA` gives `dwPlatformId` 1, returns 0 at once (`sub esp,0x94` → `xor eax,eax; ret`); the other builds have no such check |
| **No disc required** | `SEGA RALLY 2.exe` | `0x267c0`, `0x7572e` | the startup check returns 0, "found" (`mov eax,[esp+4]` → `xor eax,eax; ret`); the loader constructor's drive scan replaced by `lstrcpyA(disc root, exe dir)` and a jump to its epilogue |
| **Survive ALT+TAB** | `SEGA RALLY 2.exe`, `MUSASHI\MGameD3D.dll` | exe `0x25ff7` and appended `.sr2a` section; DLL `0x3e91`, `0x3eb7`, `0x7710`–`0x778c` | the `WM_ACTIVATEAPP` handler's `call 0x46e260` (resume sound) → a stub that calls MGameD3D's restore method first; that method rewritten as `IDirectDraw4::RestoreAllSurfaces`; textures created managed (`dwCaps` `TEXTURE`, `dwCaps2` `TEXTUREMANAGE`) instead of `ALLOCONLOAD\|TEXTURE\|VIDEOMEMORY`; see [asm/README.md](../asm/README.md) |
| **Z-buffer detach crash** | `MUSASHI\MGameD3D.dll` | `0x2930`, `0x2b31`, `0x2d11`, `0x37f4` | `call [ecx+0x20]` → `add esp,0xc` - `DeleteAttachedSurface(0, NULL)` on the back buffer skipped |
| **Invisible lobby text** | `SEGA RALLY 2.exe` | appended `.sr2c` section; `0x203c7`, `0x20566`, `0x3485f`, `0x34b2a`, `0x34efc`, `0x35533`, `0x360c3`, `0x3a6c0`, `0x3cef4`, `0x3da96` | the eight `call [__imp__SetTextColor]` → `call stub; nop`, the two `mov esi, [__imp__SetTextColor]` → `mov esi, stub; nop`; the stub masks the colour to RGB; see [asm/README.md](../asm/README.md) |
| **Windowed** | `SEGA RALLY 2.exe` | `0x273e6`; `0x14671` and appended `.sr2w` section | the fullscreen flag pushed at `0x427fe5` → 0; the .bg row copy at `0x415271` → `call` asm/bgrow.asm; see *Windowed mode* |
| **Any desktop depth** | `MUSASHI\MGameD3D.dll` | `0x271e` | `je` → `jmp`: the windowed path's "desktop must be 16-bit" check skipped |
| **Title picture** | `Title.dll` | `0x8ba` and appended `.sr2t` section | the DLL's own .bg row copy at `0x100014ba` → `call` asm/bgrow.asm assembled for its stack |
| **Borderless** | `MUSASHI\MGameD3D.dll` | `0x4d7b`, `0x26be` and appended `.sr2f` section | the windowed present → `jmp` asm/fullwin.asm's present, `call [__imp__MoveWindow]` in the windowed init → `call` its sizewindow; ten relocation entries dropped |
| **ALT+ENTER** | `SEGA RALLY 2.exe` | `0x260bc` and appended `.sr2k` section | the window procedure's `call 0x41fe20` at `0x426cbc` → asm/altenter.asm, which takes ALT+ENTER and passes everything else on |
| **No mixer needed** (Australian only) | `MUSASHI\MGAudio.dll` | `0x2278` and appended `.sr2v` section | Init looks for a CD line on the mixer for the volume slider; without one the European DLL returns `S_FALSE`, the Australian `E_FAIL`, and Wine has none. The `jne fail` → a stub that zeroes the control count at `+0x84` (uninitialised until the search fills it) and eax, and jumps back to the allocation |
| **Stream level** | `MUSASHI\MGSound.dll` | `0x6980` and appended `.sr2b` section | the menu loops, the settings-menu music and the replay music are streamed, and every path that sets a stream's level - the exe's, and the copy of the same client code in each screen DLL, `Options.dll` for the settings-menu music - ends in the streaming buffer's `SetVolume` (`0x10006940`): `min + (max−min) × value / 10000` in hundredths of a dB into the DirectSound buffer. The effects and the announcer have a `SetVolume` of their own and are created with a −40..0 dB range; the streams with a narrower, higher one, so the same slider value lands them louder, and scaling the value moves them only a few dB. The mapping's last step → `call` asm/bgmvol.asm, which takes `ATTEN` (600) off the result, floored at −10000 |
| **Music from files** | `MUSASHI\MGAudio.dll` | appended `.sr2m` section, 12 sites, the entry point, the CD-volume methods `0x1db0` and `0x1e40` (`0x1d90`, `0x1e20` Australian) | every `call [__imp__mciSendCommandA]` → `call hook; nop`; the `mov esi, [__imp__mciSendCommandA]` at `0x10003108` → `call hookaddr; nop`; entry → the setup thunk; the set-volume method's entry → `jmp setvolume`, which keeps the slider's 0..10000 as a `waveOutSetVolume` value, at 0.5 of full for the top of the slider, applied at once and by the worker after every play until the stream exists, to device 0 (Windows) and Wine's stream handles `0xFF00`, `0xFF01`, `0xC000`, and the get-volume method's → `jmp getvolume`, which reports it, since the exe divides that reading by 100 for its scale; see [asm/README.md](../asm/README.md) |

Offsets are the European build's file offsets; the other builds' are in
`BUILDS` and under *Builds*. In the exe, which is never relocated, VA =
offset − 0x400 + 0x401000 inside `.text` (− 0x600 in the American). In the two DLLs raw and virtual
layouts coincide, so VA = offset + 0x10000000 at the preferred base; both
are relocated at load, which is why every patch that lands in them is
position-independent and drops the relocation entries of the bytes it
replaces.

### Texture formats

`MGameD3D` enumerates the device's texture formats at `0x10003cf0` into
slots at `0x10012594` (0 P8, 1 X1R5G5B5, 2 R5G6B5, 3 A1R5G5B5, 4 A4R4G4B4,
5 P4, 6-10 DXT) and picks the default 16-bit one from the list at
`0x1000f79c`, first slot present wins. Texture data is 1555 with bit 15
set on opaque pixels; for a 555 target it is copied as is (`0x10004af0`),
for 565 expanded with bit 15 dropped (`0x10004bb0`). Every texture gets
`SetColorKey(DDCKEY_SRCBLT, {0, 0})` (`0x100046ce`, `0x100043d1`).

Opaque black is therefore `0x8000` in an X1R5G5B5 texture. Drivers of the
day compared the raw texel against the key and drew it; modern DirectX and
wined3d mask the X bit before comparing, so it matches 0 and is dropped.
The visible result: the black lettering on the mode-select and car-select
headings gone, leaving the white plate and a dashed grey anti-aliasing
edge. A1R5G5B5 first makes bit 15 alpha, which is what the data is, and
leaves the key exact. The copy path is unchanged: `0x1001273c` ("not
565") stays set.

### Lobby text

Every mode DLL draws through MGameD3D; the only GDI text in the game is
the exe's, and all of it is the multiplayer lobby: the name entry
(`0x420fa0`), the team and chat list (`0x435400`), the status line, the
timer and the IP list. One face, Courier New (MS Gothic on the Japanese
build), three sizes, created at `0x435df4`, `0x435e9b` and `0x435f33`.

The lobby chrome is BMPs (`CHAT_*.BMP`, `MENU_*.BMP`) loaded into 16-bit
surfaces in the back buffer's format, and the text goes onto them
through `IDirectDrawSurface4::GetDC`: blit a strip of the background into
the surface, `TextOutA` the buffer, `BitBlt DSTINVERT` for the caret,
`ReleaseDC`, then `Blt` the strip to the back buffer with
`DDBLT_KEYSRC` and a key of black.

Every site sets the colour with `SetTextColor(dc, -1)`. Windows 95 took
the low three bytes and drew white. NT-family GDI and Wine read bit 24
as `PALETTEINDEX`, look up entry 0xffff in the DC's palette, fail, and
fall back to entry 0: black, which the keyed blit drops. The caret, an
inversion, survives, and moves as the extent of the invisible text grows.
The stub in `.sr2c` masks the colour and continues into the import, so
the sites keep their shape; the IME path at `0x421166` pushes 0 and is
unaffected.

### Windowed mode

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

Two things stood in the way. The windowed path calls `GetDisplayMode`
and refuses a desktop whose depth is not the 16 bits it was asked for
(`0x1000271e`, `E_FAIL` → "Failed to initialize"); nothing after the check
depends on it, every surface takes the primary's format. And the
full-screen pictures - title, loading, game over, the course cards, all
`.bg` files - are 16-bit 565, copied straight into the locked back buffer
row by row (`0x415271`, `rep movsd`; the loader at `0x415180` converts
565 to 555 in place when the lock's green mask says so, which a 32-bit
mask also does). On a 32-bit desktop that put two pixels' bytes into
each pixel: the picture at half width. The copy is now `bgrow.asm`,
which reads the lock's `dwRGBBitCount` (`0x4e68cc`) and expands 565 to
XRGB8888 when it is 32. `Title.dll` carries its own copy of the same
loop for `TITLE640.BG` (`0x100014ba`, the lock description on its stack,
the source advanced at the end), and gets the same stub assembled for
that. No other screen DLL locks the back buffer and copies; the lobby
goes through GDI, the rest through Direct3D.

### Borderless

The windowed path sizes the window to the picture (`MoveWindow` at
`0x100026be`, after `AdjustWindowRectEx`) and presents by blitting the
back buffer to the client rect, which DirectDraw stretches. `fullwin.asm`
replaces both ends: the `MoveWindow` call goes to a thunk that moves the
window to the monitor under the cursor (`GetCursorPos`,
`MonitorFromPoint`, `GetMonitorInfoA`, resolved through the DLL's
`LoadLibraryA`/`GetProcAddress` since it imports none of them; the
window as asked if any of that fails; a framed window - ALT+ENTER - is
left as the player has it, since the init, and with it this call, runs
again on every screen change: the game tears the renderer down and
brings it back up between screens, `SetClipper(NULL)`, `SetCooperativeLevel`,
new primary, clipper and back buffer), and the present from `0x10004d7b`
on is replaced by one that fits the back buffer's aspect into the client
rect, fills the bars with `DDBLT_COLORFILL` and blits the picture into
the middle. A `WS_POPUP` window the size of its monitor is what Wine
reports to the compositor as fullscreen, with no display mode behind it
to restore on activation. The picture is still 640x480, point-sampled up.
The 96 bytes of the old present carry nine relocation entries and the
call one; all go, since the bytes are dead or relative.

### ALT+ENTER

The window procedure has cases for a handful of messages and hands the
rest to the text-input handler at `0x41fe20` (`call` at `0x426cbc`),
whose -1 means "not handled" and goes on to `DefWindowProcA`. That call
now goes through `altenter.asm`: `WM_SYSKEYDOWN` for `VK_RETURN` with
bit 29 of lParam (ALT) set and bit 30 (a repeat) clear toggles the
window and answers 0; everything else continues to the handler. The
toggle sets the style with `SetWindowLongA` - `WS_OVERLAPPEDWINDOW`
framed, `WS_POPUP` borderless, `WS_VISIBLE` kept - and places the window
with `SetWindowPos(SWP_FRAMECHANGED)`: framed, a client area of the
picture's size (from the init struct at `0x4d5e1c`) centred on the
monitor the window is on; borderless, that monitor's rect. The present
letterboxes into whatever client rect results, so the framed window can
be resized or maximised. The five user32 entry points are resolved once
through the exe's `LoadLibraryA`/`GetProcAddress` and kept in the
section, which is therefore writable.

Alt-tab keeps its three patches. `DDSCL_NORMAL` surfaces can still be
lost - another exclusive application, a locked screen - and the restore
on activation costs nothing when nothing is lost.

### Z-buffer detach

`MGameD3D` keeps the back buffer at `0x10012554` and the Z-buffer at
`0x1001255c`. Before it creates the Z-buffer (two init paths, `0x10002b25`
and `0x10002d05`), when it releases it (`0x10002920`) and at teardown
(`0x100037df`) it calls the back buffer's `DeleteAttachedSurface(0, NULL)`
with a literal null and ignores the result. DirectX 6 and Wine's ddraw
answer with an error code; Proton's ddraw dereferences the null and the
process dies in the SEH handler before its window appears. The four calls
become `add esp, 0xc`, which leaves the stack as the stdcall would have.
Where the call returned an error nothing changes. If DirectX treated the
null as "detach everything", the difference is a Z-buffer that stays
attached until the back buffer goes - a leak at exit, not a fault.

### Activation

The window procedure (`0x426b80`, registered at `0x426af0`) handles
`WM_ACTIVATEAPP` at `0x426bc5`: with the sound object at `0x50b12c`, it
calls `0x46e260` on activation and `0x46e210` on deactivation, resume and
pause of the sound (`thiscall`, `ecx` = the object). Nothing restores the
DirectDraw surfaces. `MGameD3D` has the routine - slot 16 (`+0x40`) of its
interface, at `0x10007710`: `IsLost`/`Restore` on the primary, the back
buffer and the Z-buffer - and no code in the game calls it; the exe holds
the interface at `0x50b118`. So after a switch away every flip fails and
the screen stays blank. Three patches:

- the resume call goes through a stub that calls the restore method
  first;
- the method itself is rewritten as `IDirectDraw4::RestoreAllSurfaces`
  on the object at `0x1001254c`, since the original restores three
  surfaces and everything else DirectDraw owns stays lost;
- the textures are created managed. `MGameD3D` builds each texture as a
  system-memory surface (`0x10004530`, caps `0x1800`) and a video-memory
  twin (`0x10003ff2`; descriptor from `0x10003e70`, caps
  `ALLOCONLOAD|TEXTURE|VIDEOMEMORY`, `NONLOCALVIDMEM` for AGP when the
  hardware flag at `0x1001253c` says so), filled with
  `IDirect3DTexture2::Load`. A lost video-memory surface comes back
  empty from `Restore` - DirectX's contract, and Wine keeps to it - so
  restoring them gives geometry with blank textures, and the startup
  activation wipes the ones already loaded. With `dwCaps2`
  `DDSCAPS2_TEXTUREMANAGE` DirectDraw holds the copy and re-uploads on
  its own, and neither Windows nor Wine ever marks the surface lost.
  `Load` into a managed texture works as before.

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

### Builds

`data1.cab` carries the base build (x87) and two overlay groups,
*PentiumIII Modules* (SSE) and *AMD Modules* (3DNow!), each replacing the
same six files: `SEGA RALLY 2.exe`, `AdvTelop.dll`, `Champagn.dll`,
`MSelect.dll`, `MUSASHI\MGameGL.dll` and `MUSASHI\MGLBackground.dll`. The
patcher installs and patches the Pentium III build only: the three
compute physics differently, so replays and netplay between them would
not match, and every CPU since runs SSE.

Three pressings are supported, told apart by the exe's MD5 in `BUILDS`:

| | Exe linked | `.text` | Cabinet | Against the European |
| --- | --- | --- | --- | --- |
| **Australian** | 3 Jun 1999 | 0xd2c9a | `0x01005100` | the first release: 259 KB more code, a Windows 9x check, no `LAUNCH.EXE`, English and Japanese only; its own `AdvTelop`, `Champagn`, `MSelect`, `MainMode`, `Options`, `Record`, `ReplayGallery`, `SegaLogo`, `Title.dll`, `miscdll.dll`, `MGAudio.dll`, `MGInput.dll` |
| **European** | 21 Oct 1999 | 0x936ca | `0x01000004` | - |
| **American** | 3 Oct 2000 | 0x9367a | `0x01005100` | a relink: the exe (`.data1` added, `.data` 0x100 longer), `LAUNCH.EXE`, `MSG_S.dll`, `VendorLogo.dll`, `sr2_cpl.cpl`; its own `TENYEAR` trackside art |

Everything else is byte-identical across the three, `MGameD3D.dll`
included. The play discs carry the same assets and one soundtrack (see
*The play disc*).

A row of `BUILDS` holds the fingerprints of the six P3 files and the
three patched DLLs, the exe's sites, the import slots those sites name,
and the addresses the exe stubs read. Every patched instruction is
the same bytes in all three exes bar its operands; each site was found
by its masked context and read back before it went in:

| European | American | Australian | |
| --- | --- | --- | --- |
| `0x267c0` | `0x26a80` | `0x4b420` | the disc check |
| - | - | `0x4b3b0` | the Windows 9x check |
| `0x7572e` | `0x75b5e` | `0xb4dbe` | the loader's drive scan; its epilogue 0xcf past the jump in all three |
| `0x25ff7` | `0x262a7` | `0x4abfd` | `call` resume in the window procedure |
| `0x273e6` | `0x276a6` | `0x4c026` | the fullscreen flag |
| `0x14671` | `0x14921` | `0x27e71` | the .bg row copy |
| `0x260bc` | `0x2636c` | `0x4acc2` | `call` the text-input handler |
| `0x46e260` | `0x46e480` | `0x4ad790` | `RESUME` |
| `0x41fe20` | `0x41feb0` | `0x43fb50` | `HANDLER` |
| `0x50b118` | `0x50b218` | `0x575ae8` | `GAMED3D` |
| `0x5088ac` | `0x5089ac` | `0x57327c` | `HWND` |
| `0x4d5e1c` | `0x4d5f0c` | `0x52dc1c` | `WIDTH`; `HEIGHT` four bytes on |
| `0x4e68cc` | `0x4e69bc` | `0x53fddc` | `BITCOUNT` |
| `0x495028` | `0x495028` | `0x4d402c` | `SETTEXTCOLOR`, the import slot the textcolor stub jumps through |

The ten SetTextColor sites are in the rows. The American import table is
the European one with six CRT slots reordered, none the patches use; the
Australian is laid out afresh, so its row names the five slots. The
Australian `Title.dll` has the row copy at the same offset in identical
code; its `MGAudio.dll` has the same eleven calls and one load of
`mciSendCommandA`, which the music patch finds for itself, and one
different branch in Init, for which see *No mixer needed* in the table
above.

Three files are patched in every build - `SEGA RALLY 2.exe`,
`MUSASHI\MGameD3D.dll`, `MUSASHI\MGAudio.dll` - and `Title.dll`; the exe
and `MGAudio.dll` grow by a section. Each gets a `.bak` beside it, the
untouched original; the patcher always starts from those, so patching
twice is patching once, and restoring is a rename.

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
| `{ACEF8F00-D517-11D1-A496-0000C02DB0F3}` | `MGAudio.dll` | `WINMM.dll` | CD audio over MCI, its volume over the mixer |
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
  and `MUSASHI\MUSASHI.manifest` with a `comClass` per DLL. An external
  `.exe.manifest` is honoured because the exe embeds none. Works under
  Wine and Proton; untested on Windows.

### The registry

The exe imports no registry function. `MGameReg.dll` is the registry: its
Open (`0x10001420`) is `RegCreateKeyExA(HKEY_LOCAL_MACHINE, "Software\%s\%s",
KEY_ALL_ACCESS)`, called from the exe (`0x47ef5e`) with `"SEGA"` and
`"SEGA RALLY 2"`, and the resulting object is handed to `MGInput`'s init
(`0x47ef9e`): the controller configuration lived under that key, written
by `SR2_CPL.cpl`, the "Controller Settings" Control Panel item the
installer added. The game only reads it and runs on its defaults when it
is empty. `HKEY_LOCAL_MACHINE` is pushed at three sites in `MGameReg.dll`
(file `0x1476`, `0x1942`, `0x1b46`); which of them serve the
`App Paths` lookup has not been checked, so none is redirected to
`HKEY_CURRENT_USER` yet. Under Wine the key is writable as it is. Nothing
in `setup.ins` writes under `Software\` except the DirectPlay lobby key
`Software\Microsoft\DirectPlay\Applications\SEGA RALLY 2`.

## Startup and files

### The install contract

The exe itself touches no registry; that is `MGameReg`'s, above. At
startup:

1. `0x427450`: `GetModuleFileNameA`, open `SR2.CFG` beside the exe. Must
   exist.
2. `0x4274e0`: `GetLogicalDrives`, for each drive `GetDriveTypeA ==
   DRIVE_CDROM`, `GetVolumeInformationA` label `SEGARALLY2`, open
   `X:\DISKID.2`. Returns the drive index or −1.
3. `0x4273c0` wraps 2: on −1, `MessageBox` with a "insert disc" string from
   `SR2_MSG.dll` (id 2 or 3, depending on whether `SR2.CFG` was found) and
   retry, or give up. Returns 0 for found. This is nodisc's first site;
   the second is in the loader, below.

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

Three properties of the DLL shape the patch:

- The open routine (`0x10003100`) does not call through the import slot;
  it loads the slot into `esi` and calls `esi` twice, for the open and the
  time-format set. So there are twelve sites to rewrite, not eleven: the
  calls go to the hook, the load to a thunk that returns the hook's
  address. A load left in place sends the open to the real driver, and
  the first status it answers with `MCIERR_UNSUPPORTED_FUNCTION` makes
  MGAudio close the device.
- MGAudio issues its MCI commands from threads it creates per action
  (`CreateThread`, `TerminateThread`), and Wine's `winmm` refuses commands
  to a device from any thread but the one that opened it
  (`MCIERR_INVALID_DEVICE_NAME`, `0x107`). The hook therefore sends every
  string command from one worker thread of its own.
- The DLL is relocated on every load (`SR2_MSG.DLL` holds its preferred
  base). Each rewritten site carried a `.reloc` entry for its absolute
  slot address at `site+2`; `apply_music` drops those, or the loader
  would add the relocation delta into the new relative displacement.
  `tools/musictest.py` relocates the image before running it for that
  reason.

At "Go!" the exe seeks the course track to 0:00 - with the track number
one below the one its play used, in every build - and sends no play
after it. On a drive that left the CD stopped on the wrong track for
`MGAudio`'s poller to sort out; the hook takes it as a restart of the
open track.

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
- File data: at the data offset in `data1.cab` itself. In the `0x01000004`
  cabinet a compressed file is one raw deflate stream - no zlib header,
  and no final-block marker, so the stream is read to the expected size
  and not to EOF. The `0x01005100` cabinets on the other two pressings
  store it as chunks, each a u16 length followed by a complete raw deflate
  stream of 10240 bytes of output; the chunks are inflated in turn until
  the expected size is reached.

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
thirteen audio tracks are under *Music* above): the same assets as MS
cabinets, 230 MB,
MSZIP-compressed (plain deflate): one `bindata\<dir>.cab` per tier
directory, `bindata\tenyear\N_M.cab` for the 41 ten-year courses,
`bindata\root.cab` for the root-level files. Every
cabinet checked (`root`, `serial`, `adv`) contains exactly the files the
tiers hold. `diskid.2` is the text `Please enjoy SEGA RALLY 2.` The disc is
not needed by a full install.

The three pressings hold one soundtrack: stripped of digital silence,
the American and Australian tracks are bit-identical and the European
within eleven samples. Europe trims the tail; the other two keep two
seconds of it per track, and America adds 62 ms of lead. A rip from any
of them plays the same music, with the disc's own silence at the loop.

## What is not done

- Windows has not been tried; Wine and Proton have. To check there: the
  stock game is said to crash on returning to the main menu after saving
  a replay; it does not under Wine with only `nodisc` and `music` on, so
  nothing here fixes it. And the volume patch's device-id
  `waveOutSetVolume(0, …)` is the Windows path; only the Wine handles
  have been seen to work.
- `SR2.CFG` values, the 640x480/800x600 switch, and what `LAUNCH.EXE` and
  `MUSASHI\SR2.dll` offer.
- Frame timing, input, resolution: nothing traced yet. The renderer is
  `MGameGL.dll` + `MGameD3D.dll`, so resolution work lives there rather
  than in the exe.
- The controller configuration: what `SR2_CPL.cpl` wrote under the
  registry key, and what replaces it. `MGameReg.dll` to `HKEY_CURRENT_USER`
  for Windows without administrator rights.
