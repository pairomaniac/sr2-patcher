# Notes

How the game works and what the patcher does about it, rather than how to
use it. For using the patcher see [README.md](../README.md); for addresses
and file offsets see [MAP.md](MAP.md).

Everything below is read off the retail European release (files stamped
20-21 Oct 1999, VC6 linker 6.0) with pefile, capstone and unshield, and
checked on the game running under Wine and Proton. The American and
Australian releases map onto it; *Builds* says how far.

## Patches

*The annex* is the one `.sr2` section the patcher appends to a file,
grown by each patch that puts code or data there.

| Patch | File | Offsets | Change |
| --- | --- | --- | --- |
| **Windows 9x check** (Australian only) | `SEGA RALLY 2.exe` | `0x4b3b0` | `0x44bfb0`, "Please run on Windows 9x." unless `GetVersionExA` gives `dwPlatformId` 1, returns 0 at once (`sub esp,0x94` → `xor eax,eax; ret`); the other builds have no such check |
| **No disc required** | `SEGA RALLY 2.exe` | `0x267c0`, `0x7572e` | the startup check returns 0, "found" (`mov eax,[esp+4]` → `xor eax,eax; ret`); the loader constructor's drive scan replaced by `lstrcpyA(disc root, exe dir)` and a jump to its epilogue |
| **No card warning** | `SEGA RALLY 2.exe` | `0x26678` (`0x26938` American, `0x4b263` Australian) | `0x427240` shows string 5 of `SR2_MSG.dll`, OK/Cancel, when the chosen device's free video memory is under 4,000,000 bytes or the two capability bits `0x1800` at `+0x34` of its entry are both clear; Cancel makes it return 1 and the caller exit. The `push 5` before the string load → `jmp` to the return-0 tail. The Australian exe has no memory test |
| **Replay freed once** | `ReplayGallery.dll` | `0x2f65`, `0x3b1f` and the annex | the gallery's End (`0x100046c0`) frees the replay at `+0x50` of the exe's block, which is its own when it loaded it from a file (`new` at `0x10003b65`) and MainMode's static buffer when it came from a race; Windows 9x's HeapFree refused that, the heap since Windows 8 ends the process. The `new` → a thunk that keeps the block, the `push eax; call free` → one that frees only that block; see asm/replayfree.asm |
| **Texture release checked** | `MUSASHI\MGameD3D.dll` | `0x4430` and the annex | the release of texture N (`0x10004430`) checks N against the count at `0x10012590`, as the create does; `VendorLogo.dll`'s End (`0x100014e0`) releases −128, 512 bytes before the table, and calls through whatever is there. The first ten bytes → `jmp` asm/texrange.asm, one relocation entry dropped |
| **Survive ALT+TAB** | `SEGA RALLY 2.exe`, `MUSASHI\MGameD3D.dll` | exe `0x25ff7` and the annex; DLL `0x7710`–`0x778c` | the `WM_ACTIVATEAPP` handler's `call 0x46e260` (resume sound) → a stub that calls MGameD3D's restore method first; that method rewritten as `IDirectDraw4::RestoreAllSurfaces`; see [asm/README.md](../asm/README.md) |
| **Z-buffer detach crash** | `MUSASHI\MGameD3D.dll` | `0x2930`, `0x2b31`, `0x2d11`, `0x37f4` | `call [ecx+0x20]` → `add esp,0xc` - `DeleteAttachedSurface(0, NULL)` on the back buffer skipped |
| **Missing lettering** (`texfmt`) | `MUSASHI\MGameD3D.dll` | `0xf79c` (12 bytes) | the 16-bit texture-format preference list `1, 2, 3` (X1R5G5B5, R5G6B5, A1R5G5B5) → `3, 1, 2`, so the format with the alpha bit the black lettering keys on is taken when the device has it; see *Texture formats* |
| **Invisible lobby text** | `SEGA RALLY 2.exe` | the annex; `0x203c7`, `0x20566`, `0x3485f`, `0x34b2a`, `0x34efc`, `0x35533`, `0x360c3`, `0x3a6c0`, `0x3cef4`, `0x3da96` | the eight `call [__imp__SetTextColor]` → `call stub; nop`, the two `mov esi, [__imp__SetTextColor]` → `mov esi, stub; nop`; the stub masks the colour to RGB; see [asm/README.md](../asm/README.md) |
| **Windowed** | `SEGA RALLY 2.exe` | `0x273e6`; `0x14671` and the annex | the fullscreen flag pushed at `0x427fe5` → 0; the .bg row copy at `0x415271` → `call` asm/bgrow.asm, which also scales the picture to a buffer of another size; see *Windowed mode* |
| **Any desktop depth** | `MUSASHI\MGameD3D.dll` | `0x271e` | `je` → `jmp`: the windowed path's "desktop must be 16-bit" check skipped |
| **Title picture** | `Title.dll` | `0x8ba` and the annex | the DLL's own .bg row copy at `0x100014ba` → `call` asm/bgrow.asm assembled for its stack |
| **Frame log** (`frametrace`, by name only) | `SEGA RALLY 2.exe` | `0x27bf0`, `0x27d0b` and the annex | the frame gate's first five bytes and its last five before `pop ebx; ret` → `jmp` asm/frametrace.asm, which keeps the counter at the entry, logs the frame at the exit and leaves as the gate did |
| **Borderless** | `MUSASHI\MGameD3D.dll` | `0x4d7b`, `0x26be` and the annex | the windowed present → `jmp` asm/fullwin.asm's present, `call [__imp__MoveWindow]` in the windowed init → `call` its sizewindow; ten relocation entries dropped |
| **ALT+ENTER** | `SEGA RALLY 2.exe` | `0x260bc` and the annex | the window procedure's `call 0x41fe20` at `0x426cbc` → asm/altenter.asm, which takes ALT+ENTER and passes everything else on |
| **No mixer needed** (Australian only) | `MUSASHI\MGAudio.dll` | `0x2278` and the annex | Init looks for a CD line on the mixer for the volume slider; without one the European DLL returns `S_FALSE`, the Australian `E_FAIL`, and Wine has none. The `jne fail` → a stub that zeroes the control count at `+0x84` (uninitialised until the search fills it) and eax, and jumps back to the allocation |
| **The mix** | `MUSASHI\MGSound.dll` | `0x439f`, `0x6980` and the annex | the sound manager - in the exe and, as a copy of the same code, in every screen DLL - gives each effect a −40..0 dB range and sets its ceiling at `(step+1)/10` of it from the slider: 4 dB a step, 0 dB at 9. The buffer's `SetRange` (`0x10004380`) loads min and max through asm/mix.asm, each mapped onto `MIX_MIN..MIX_MAX` from asm/mix.inc, −43..−8: 3.5 dB a step, 9 the old 7, for every client. The streamed music - every client ends in the streaming buffer's `SetVolume` (`0x10006940`) with the step × 1111 as a 0..10000 value mapped across the stream's own range - finishes that mapping through the second routine, the step on the same curve plus `STREAM_DB` (200), 0 off |
| **Effects at full** (Australian only) | `SEGA RALLY 2.exe`, `Options.dll` | exe `0xb26cb`, `0xb272e`, `0xb2782`; `Options.dll` `0xf92a`, `0xf98d`, `0xf9e1` | the volume routine sets each effect's ceiling from its slider and then its level as a percentage of that; the other builds pass 100, the Australian's passes the slider × 11 - the slider twice - in the exe and in its `Options.dll`, which re-applies on the way out of the screen. The setting's load → `mov eax, 9`, which the × 100 × 0.111 after it makes 100; in the DLL the load's relocation entry goes with it. The percentage is also how every build drives the engine's level by throttle, so it stays a percentage |
| **Music from files** | `MUSASHI\MGAudio.dll` | the annex, 12 sites, the entry point, the CD-volume methods `0x1db0` and `0x1e40` (`0x1d90`, `0x1e20` Australian) | every `call [__imp__mciSendCommandA]` → `call hook; nop`; the `mov esi, [__imp__mciSendCommandA]` at `0x10003108` → `call hookaddr; nop`; entry → the setup thunk; the CD-volume methods' entries → `jmp setvolume` / `jmp getvolume`: the slider's step becomes hundredths of a dB on the mix's curve plus `CD_DB` (300), −5 dB at 9, set on the track's DirectSound buffer; the exe's fade before a stop, from full down by 10% a frame, is taken as amplitude percent of that level; see [asm/README.md](../asm/README.md) |
| **CD level marked** | `SEGA RALLY 2.exe` | `0x73048` (`0x73478` American, `0xb2668` Australian) | the menu's CD-level set at `0x473c48` pushes flags 0 → `0x40`, a bit the DLL never read, so the music hook tells it from the fade's values without guessing; the race's level and the mute already carry bit 31 |
| **Device Settings** | `Options.dll`, `BINDATA\MISC\OPTIONS.TXR` | DLL `0x33f8`, `0x340f`, `0x3214`, `0x3267`, `0x2f0c`, `0x3638` and the dispatch entry at `0x31c0` + 12 (Australian `0x5b68`, `0x5b7f`, `0x5984`, `0x59d7`, `0x567c`, `0x5da8`, `0x5930`), nine `x` fields and two UV entries in `.data`, the annex; the TXR grows a thirteenth sheet | a fourth item on the Options menu and the page behind it: the cursor's and the icon set's item counts 3 → 4, the item tables and the top-level state table moved to the annex with a fourth item and two more states, the dispatch table's fourth slot → a stub that selects the page's state; the page is asm/devices.asm over data the patcher builds. See *The Options screen* |
| **No registry** | `SEGA RALLY 2.exe` | `0xd07c0`, `0x7e359` | the game's file name string `SR2.CFG` (one, for the read at `0x427740` and the write at `0x427880`) → `SR2.DSP`, so its 100-byte display block - the DirectDraw device name and capability flags recomputed from video memory at every start (`0x426ec0`), the launcher's options, the disc flag and the language - keeps its own stock-shaped file (`carry_display_block` copies a stock `SR2.CFG`'s block there at patch time, once) and `SR2.CFG` is the controls text from byte 0; and `MGameReg`'s Open at `0x47ef59` (21 bytes) → `xor esi,esi`, so `Software\SEGA` is never created. See *Gamepad* |
| **Widescreen** (`widescreen`) | `SEGA RALLY 2.exe` | `0x20dfe`, `0x20e18`, `0x5128a`, `0x4e5` and the annex | the mode setter's `mov eax,[esp+8]; cmp [0x4d5e54],eax`, its literal 640x480/800x600 stores, the screen-change routine's `mov eax,[0x50afdc]; mov ecx,[eax+0x50]` and the element walker's `push eax; call ecx; add esp,4` → `call`s into asm/wide.asm, with the size table after it; see *Widescreen* |
| **Widescreen, the 3D** (`widescreen3d`) | `MUSASHI\MGameGL.dll` | `0x2bc0`, `0x2c70`, `0x2de0`, `0x27f0`, `0x2e80`, `0x2ee0` and the annex | `SetViewport`'s ten-byte, `SetPerspective`'s, `SetCentre`'s and the parameter getter's nine-byte prologues → `jmp` asm/widegl.asm, which scales a 640x480 rect and its centre to the picture, widens the angle for its aspect and answers the focal and centre in 640x480 terms; the projection's and its inverse's first eight bytes → entries that put the point in 640x480 terms one way and the method's own the other |
| **HUD after the water** (`hudlast`) | `SEGA RALLY 2.exe` | `0x17eb1`, `0x274f2`, `0x25d30` (11 bytes) (`0x18161`, `0x277b2`, `0x25fe0` American; `0x2de01`, `0x4c119`, `0x4a940` Australian) and the annex | the race state's HUD call (`0x418ab1`), the frame's root-tree draw (`0x4280f2`) and the fade node's draw thunk (`0x426930`) → branches into asm/hudlast.asm: the HUD held back while the tree is going to be drawn, then drawn before the fade's quad or after the tree, with the full viewport set and the state's reset made; see *The gauge over the lake* |
| **Loading screens** (`loadhold`) | `SEGA RALLY 2.exe` | `0x19bbb`, `0x189be` (6 bytes each) and the annex | the store of the new loading picture at its create (`0x41a7bb`) and the load of it at the step that deletes it (`0x4195be`) → `call` asm/loadhold.asm, which notes the tick at the one and waits out the hold at the other |
| **The clear's height** (`clearsize`, Australia only) | `SEGA RALLY 2.exe` | `0x40b83` (12 bytes) and the annex | the mode setter's `mov eax, [WIDTH]` and the two pushes of it → `call` a thunk that pushes `[HEIGHT]` and `[WIDTH]` and jumps into the clear at `0x441180` |
| **Widescreen, the 2D** (`widescreen2d`) | `MUSASHI\MGameD3D.dll` | `0x5120`, `0x50d0`, `0x4fe0`, `0x5170`, `0x5030`, `0x5080`, `0x6040`, `0x4d50`, `0x411c` and the annex | the quad and triangle draws' first six bytes, the list, indexed-list, strip and fan draws' first ten, the device viewport setter's first nine, the present's first eight and the texture create's thirteen after its system-memory copy → `jmp` asm/wide2d.asm, seven relocation entries dropped |
| **Resolution list** (`resolution`) | `Options.dll` | `0x2815`, `0x2826`, `0x2528`, `0x2b01`, `0x2a5b`, six bytes and the annex | the Graphic Settings page's row load, count check, draw loop head, row store and DEFAULT's row store → asm/resolution.asm, the check jumped over, the page's six "7"s made "8" for the aspect row; three relocation entries dropped |
| **XInput** | `MUSASHI\MGInput.dll` | `0x8130`, `0x8210`, `0x7100`, `0x56c0` (Australian `0x7940`, `0x7a20`, `0x6940`, `0x81a8`) and the annex | the registry helper's load and save, the config's update and the device's poll → `jmp` asm/padinput.asm, the Australian build's keyboard-poll address pointed at it instead; the section carries the name tables and defaults, then the working area, after the code. See *Gamepad* |
| **DirectInput 8** (`dinput8`) | `MUSASHI\MGInput.dll` | `0x2940` (18 bytes), `0x39ac` (7), the two ids at `0x10680`, `0x106c0` (Australian `0x2870`, `0x39f9` (6), `0x10678`, `0x106b8`) and the annex | the `DirectInputCreateA` call → `jmp` asm/dinput8.asm, which calls `dinput8.dll`'s `DirectInput8Create`; the first read of the device's type byte → `call` its translation of DirectInput 8's type codes; `IID_IDirectInput8A` and `IID_IDirectInputDevice8A` written over the DirectInput 2 ids the two `QueryInterface` calls name. See *Gamepad* |
| **Devices of no kind** (`nogeneric`) | `MUSASHI\MGInput.dll` | `0x26d2` (5 bytes; Australian `0x2694`) and the annex | the device loop's null-GUID branch and the two instructions after it → `jmp` asm/nogeneric.asm, which makes the branch, skips a `DI8DEVTYPE_DEVICE` (0x11) instance the same way and does the two on the way back; needs `dinput8`. See *Gamepad* |

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
The stub in the annex masks the colour and continues into the import, so
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
which reads the lock's description (`0x4e6878`: size, pitch, surface,
`dwRGBBitCount` at `+0x54`) and expands 565 to XRGB8888 when the depth
is 32; and when the surface is not the picture's size (a wide picture
size, below) it composes the whole picture on the first row, at source
size with its side areas, into a surface `MGameD3D` keeps, for one blit
to stretch into the screen - see the widescreen section - and nothing
on the rows after. `Title.dll` carries its own copy of the same loop
for `TITLE640.BG` (`0x100014ba`, the lock description on its stack, the
source advanced at the end), and gets the same stub assembled for that.
The `.bg` path with brightness or contrast set goes through `0x46c900`
instead and is untouched. No other screen DLL locks the back buffer and
copies; the lobby goes through DirectDraw blits, the rest through
Direct3D.

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

The present keeps the counter after its blit in the annex, which is
writable for it, for `frametrace`; `QueryPerformanceCounter` is
resolved on the first present.

### Widescreen

The stock resolution setting is one dword in the game object,
`settings+0x50`, 0 or 1, kept in `SR2_SAVE.DAT` (an obfuscated file,
`0x44f710`): 1 switches the loader to `BINDATA\800x600\` for the root
files and is read as a yes/no by a dozen places in the exe (`0x4188bf`,
`0x418a74`, `0x421852`, `0x427893`, `0x451e8f`, `0x4630da`, `0x463414`,
`0x463459`, ...) and by the screen DLLs' own loader copies, so it cannot
hold anything else. And 800x600 is the front end only: `0x451e8f` forces
mode 0 for the race screens (4-0xe), so the race is always 640x480. The
mode setter `0x4219f0(mode)` stores it at `0x4d5e54`, returns 1 when it
is unchanged, and otherwise puts 640x480 or 800x600 (the American exe
also 1024x768 behind `0x4efa1c`) into the init struct's `WIDTH`/`HEIGHT`
and re-inits the renderer, the textures (`0x421450`) and the viewport and
projection (`0x4216a0`).

The wide size is therefore its own setting, `[Display]` / `Resolution =
1920x1080` in the `SR2.CFG` text, one of the patcher's table
(`RESOLUTIONS`) past the stock two. The exe's stub reads it with
`GetPrivateProfileStringA` at every call of the mode setter: mode 0
takes it, mode 1 stays 800x600, and the setter's entry compare is made
to fail once when it changes. The stock calls the setter at the
screen-change routine (`0x451e8a`) only for the race screens, and for
the front end's only on some of the ways in (`0x4504a9`, `0x450661`),
so a size chosen in Options waited for a race; the routine's settings
load now goes through the stub, which reads the file and calls the
setter with the front end's mode when the size differs from the one in
force, so the new size applies at the next screen change wherever it
goes. The Options page writes it with the Write
counterpart and stores 0 in `+0x50` for a wide entry; the controls save
in `padinput.asm` copies the section through, since it rewrites the
file.

What the size changes, in three DLLs.

The 3D, in `MGameGL` (`widegl.asm`): the projection is set in
`SetPerspective` (`0x10003870`: focal = width / (2 tan(fov/2)), the
angle horizontal, 84.375° for the race at `0x421819`, 15360 in 65536ths
of a turn) and the viewport in `SetViewport` (`0x100037c0`; rect,
centre). The exe's wrapper (`0x46bf90`, `0x46bfd0`) is one caller;
MSelect sets the car select's viewport and perspective on the renderer
itself, Champagn its perspective; so the two methods are taken at their
prologues. Every rect but the picture's own full one - the table at
`0x4b12f0` (full, top 0-224, bottom 256-480), the DLLs' literals, the
countdown's zoom at `0x41905f`, which scales the 640 frame about its
centre to more than 640x480 - is in 640x480 terms and is scaled to the
whole picture; the full one, which only the exe's re-init sets,
passes. A rect narrower than the 640, or not about its middle (left +
right ≠ 640), is a window and goes into the picture's 4:3 box - x by
height plus the bar - as the 2D around it does, with the angle left at
4:3 while it is set (*The credits*, below). The projection centre goes
by height and the bar, as the 2D does: the middle is the middle either
way, but a centre the game sets off it - the transmission select's, at
168, which puts the car left of the spec panel - keeps its place
against the panel instead of moving out with the width. The angle becomes 2 atan(tan(a/2) · (W/H) / (4/3))
while the picture is wider than 4:3: the 4:3 vertical field, the extra
width showing more, whatever camera set it (the exe never culls on the
angle it keeps at `+0x563c`). The size is MGameD3D's, its dwords at
`0x100123fc`/`0x10012400` through `GetModuleHandleA`: MGameGL's own
floats (`0x100128d8`, `0x100128d4`) are set at its one init and stay
640x480 through every resize. Four more methods set or hand back the
same numbers and are taken the same way, on the rule that a caller of
the renderer thinks in 640x480 terms, because what it does with the
answer goes through the 2D. `SetCentre` (`+0x38`, `0x100039e0`;
cx, cy) is the centre alone: the name entry after a time attack (exe
`0x434037`) sets (320, 240) through it and never through `SetViewport`,
so its 3D letters, models drawn through the renderer, sat about the
picture's own pixel (320, 240) - the top-left corner of a wide one,
clipped by its edges. The centre is scaled as `SetViewport` scales one.
The screen-space projection (`+0x78`, `0x10003a80`; &out, &point) makes
a point's screen position as the centre plus the offset at the focal,
and the focal is `0x100128d8`'s 640 over the tangent of the (widened)
angle whatever the width: the offset comes out in the units of a
picture 640 wide, about a centre in real pixels. The exe draws sprites
at those positions through the 2D - a triangle list at `0x45510f` of
points projected at `0x454ea6`, a strip at `0x407965`; neither has been
seen to run in a race yet - and wide2d would scale them once more as
640x480, off the picture's right edge at any wide size. The fourth
entry runs the method and converts its result into 640x480 terms - the
centre as it was asked for, the offset by (W/H)/(4/3), which is what
the 3D's real-pixel offset is to the 640x480 one - so wide2d puts the
sprite where the 3D projects the point. The lake on
Mountain is `MGLBackground`'s: the race's `.SEA` layer (*The sea*,
below), a ground plane whose vertices' depth it makes from the focal
and the centre it asks the renderer for once, through the parameter
getter (`+0x48`, `0x100033f0`; ids 4, 7, 8), and whose texture
coordinates it makes through the inverse projection (`+0x7c`,
`0x10003ae0`). With the real-pixel centre and the widened angle's focal
against y in 640x480 terms, `y - cy` went negative on a wide picture
and every vertex's z came out above 1 (1.10-1.18 at 5120x1440 against
0.97-1.00 at 640x480, in `d3dtrace`), which wined3d drops. The getter
answers the three in 640x480 terms and the inverse takes its point in
them, so the plane is built as at 4:3. The rect-only `SetViewport`
(`+0x34`, `0x10003370`) has no caller seen and is not taken. One thing
that was tried and taken out: mapping a screen DLL's rect to the 4:3
box instead, for the car select's carousel that leans on the 640
frame's edges to hide six of its seven cars - the device's viewport
clips the 2D as well, and the sides went with the cars, so the carousel
is still open.

The 2D, in `MGameD3D` (`wide2d.asm`): every screen DLL, MainMode and the
exe draw their sprites, text and HUD as pre-transformed geometry, FVF
`0x1c4`, in 640x480 pixels straight to `DrawPrimitive`, through the
quad (`+0xb4`, `0x10005120`), triangle (`+0xb0`), list (`+0xb8`,
`0x10004fe0`), indexed-list (`+0xc4`, `0x10005170`, the race's HUD text
from `0x429f11` and its neighbours), strip (`+0xbc`, `0x10005030`) and
fan (`+0xc0`, `0x10005080`) draws. MGameGL's 3D is untransformed - FVF
`0x1e2` or `0x112` (`0x1000d970`), the device transforms it through the
matrices it sets - so every `0x1c4` draw is 2D, whichever entry. The
six entries' vertices are scaled into a copy (2048 vertices; a longer
list goes as it is), by height and centred - the 4:3 layout in the
middle of the picture - a quad spanning the whole width (a fade, a
background) stretched across, and a quad or triangle with a vertex at
one edge of the 640 drawn out to the picture's edge on that side with
its texture coordinate shifted at the quad's own rate for the distance
the vertex moves, so a tiling texture goes on, scrolling or not: only a
tile-sized quad (128 px or less each way), a wider or taller one at the
edge being a picture or a strip of one - the mode select's collage -
that keeps its 4:3 place, with the picture itself stretched into the
side area beside it (below), unless no texture is selected (`+0xac`,
cached at `0x10011224`, bit 31) - then it is a plain cover and its
edge goes out to the screen's (*The credits*); a clamped tile (the
texture addressing, `+0xf8`, cached at `0x10011240`) has wrap set for
its draw through the
method, as the Options background needs, the course select's tiles
wrapping already. A tile is told from a sprite of the same size by the
frame before: every quad's width goes into a table (16 widths, each
with its count of quads and the extent they covered), the present
(`+0x80`, `0x10004d50`) closes the frame's table and keeps it, and a
quad at the edge is drawn out only when its width covered the whole
640x480 last frame with six quads or more. The Options icons and
buttons sliding through the edge, and the car select's outgoing car,
were being repeated across the side area by the same rule that
carries the tiles out.

**The HUD's frame.** In a race the HUD is anchored to a 16:9 frame
rather than the 4:3 box: a 2D draw wholly in the left part of the 640
(no vertex past 268, 0.42 of the width: the speed ends at 256, the
countdown starts at 291) has its bar reduced, and one wholly in the
right part (none short of 372) its bar raised, by min(bar, 2H/9) - the 4:3
box's edge to the edge of a 16:9 frame no wider than the picture. So at
16:9 the tachometer, the times, the position and the car's name sit at
the picture's edges, on 21:9 and 32:9 at a centred 16:9's, and at 16:10
at the picture's; 4:3 has no bar and moves nothing. The middle - the
countdown, the arrows, the results - keeps its place, as does a draw
touching the 640's edges, which is a tile or a fade. A list of quads
(four vertices each) is moved a run at a time - the race's text is one
indexed list of glyphs from both sides of the screen, and a run is the
quads in a row whose left ends fall within 16 px of the run's right end
so far, a string; a strip or a fan goes as a whole. The speed's digits
are single quads each, so the split falls where no element straddles
it. What
is HUD is settled by who draws it: the race's HUD is a set of elements
on the exe's element list (`0x4e6948`, registered through `0x401260`
with a callback at `+0xc` and drawn by the walker `0x4010d0`, which
calls each callback with the element pushed), and so are the results
overlay and the credits, with callbacks elsewhere. The exe's `wide.asm`
takes the walker's callback call (`0x4010e5`, `push eax; call ecx; add
esp, 4`, the same in every build): it sets a flag before a callback in
the HUD's range (`HUDLO`-`HUDHI`, `0x42ac60`-`0x42ffc0` in the European
exe: the thirty-two callbacks the race's HUD setup at `0x429228`
registers, nothing else on the list in between; per build), `wide2d`
anchors the frame's 2D while it is set and clears it at the present.
A list from a HUD callback is anchored whatever edge it touches: the
anchoring left alone any draw with a vertex at the 640's edges, a tile
or a fade for `extend`, and the race's position piece - a string from
591 whose two-digit place reaches 639 - fell under that and sat at the
4:3 box's edge until the place shortened, which in split screen was the
right side of the HUD for the first seconds of a race (a `d3dtrace` of
one: the piece `0x429fd2` draws at x 591 every frame). A list is text,
never a tile, so the edge rule now applies to quads, triangles, strips
and fans only. Split screen's position bar is another exception: the
band between the halves (the quad `0x42a217` draws at y 224, 32 tall)
carries a bar drawn through MGameGL, which the anchoring never sees,
and along it the cars' icons (a list of three quads from `0x42f7dc`,
y 237 to 250) and their 1P/2P labels (glyphs in the race's list, y
225 to 235), which it did: at the bar's left end at a race's start
they sat at the 16:9 frame's edge instead. A piece whose vertices all
lie between 224 and 256 down stays where it is; the lower half's own
text starts at 252 and reaches below, so it still moves. It has to be
the frame and not the callback: the callbacks queue their
strings, and the screen's tail draws the lot as one indexed list
(`0x418ab1` calling `0x429d70`) after the walker has finished, so a
flag cleared after the callback caught the tachometer and nothing
else. The flag is `wide2d`'s, after its `HUDFRAME` marker in
`MGameD3D`'s annex, found through the device object as `bgrow` finds
its block and kept once found. Three things tried first and taken out: the screen id at the
screen-change routine (4-0xe turned out to be the 3D front end - the
car select, the name entry - and the race showed as neither those nor
0x11-0x12); a car in the exe's car table, which is true through the
results and the credits as well, whose centred tables then broke at the
split; and `wide2d` looking up the stack for the walker's return over
the element, which found stale copies of it in uninitialised locals and
crashed on what lay beside them.

**The side bars.** A quad at one edge that is wider or taller than a
tile, and at least 160 tall (a plate sliding through the edge is wide
but not tall), is a picture or a strip of one - the mode select's
backdrop is `BINDATA\MISC\MAINMODE.TXR`, a 640x480 collage in five
256x256 tiles, and `TITLE.TXR` is the same layout. It keeps its 4:3
place, and the side area beside it gets the picture itself, stretched:
the texture is still bound when the quad is drawn, so the bar is a quad
covering the side area with that texture on it and its coordinates
carried past the quad's own edge. What it shows is the 640's own sliver
- a bar's share of the picture's width, in from that end, and no
further in than the quad itself reaches, since a tile holds only its
own part of the picture - spread across. That is the mapping `bgrow`
uses for the `.bg` screens, so the two look alike; a tile ends where
the next begins, and the bars meet as the tiles do. A quad running past
the 640 - the mode select's right-hand tiles reach 768 - has its bar
started at the 640, not at its own edge, which would be off the picture.

The motion blur across it is the device's: the quad is drawn sixteen
times, spread across twenty of the 640's pixels in u - a thirty-second
of the picture, which the eightfold stretch makes some 160 on the
screen - each at 17/256 of the quad's diffuse dimmed to two fifths,
with blending turned on (`+0xe8`, its old state cached at `0x10011234`)
and both factors ONE (`+0xec`) so the passes add: sixteen shares of
17/256 make 255 for 255. `+0xfc` puts the filtering to linear for them
and `+0xf8` the addressing to clamp, so a pass shifted past the
texture's edge carries its last column out; blending goes back as it
was after and the factors to source-alpha and its inverse, the pair the
game's own blending wants. Note which states these methods set: `+0xfc`
is `TEXTUREMAG` and `TEXTUREMIN`, 17 and 18, and the blend factors are
19 and 20 under `+0xec` - set the wrong pair and the passes overwrite
one another instead. Four passes a sixteenth of the sliver apart, an
earlier try, showed as four copies; sixteen a hundred-and-twentieth
apart read as a smear.

What may be drawn from is settled at the load, by the texture create's
entry (`0x1000411c`, esi the texture's number, ebp its description:
pixels, size, flags): a picture, one so nearly black that a bar of it
should be black instead - three quarters of its pixels dark, which is
`empire.txr` and `segalogo.txr`, black but for the logo - or nothing,
which is a sprite, a palette or a render target. One word per texture
number, 128 of them. The logo screens are textures, not `.bg` pictures:
they come through here and not `bgrow`. The description's flags are a
bitfield, not the TXR's format alone: bit 3 is 4444 and the palette and
render-target bits (`0x700`, `0x1000`) are skipped, everything else
read as 1555. By the create a format-0 texture is 1555 with bit 15 set,
not 565 - the screen DLLs' loaders (MainMode `0x10006b80`, the others
the same library) expand it in place - so 0 and 2 read alike.

With `d3dtrace` on, every quad that reaches the bar's decision reports
it: `sr2 b why tex kind xmin xmax ymin ymax`, why 1 not a quad, 2
shorter than 160, 3 no texture selected, 4 the texture is not a picture,
5 the bar drawn; the draw lines carry the selected texture and its kind
as their last two fields, and every texture create reports `sr2 t why
slot flags size first bad left kind`, why 1 past the table, 2 paletted
or a render target, 3 no pixels, 4 a transparent pixel, 5 the kind
kept.

The `.bg` pictures go through `bgrow.asm`, above, which is built twice,
and the build is the screen: `Title.dll`'s copy loop draws the title
screen and nothing else, the exe's the loading, game-over and course
screens and nothing else, so what a bar should be is settled at
assembly with no look at the pixels. In `Title.dll`'s build the bars
carry the picture behind them, the whole of it stretched to the
surface's width with the drawn one over the middle - so each bar shows
the sliver past the drawn edge spread across its width - with the same
motion blur and dimming as the textured screens: each row's sliver is
box-blurred, every column the mean of those a sixty-fourth of the width
either side, a running sum that stays inside the sliver so the picture
beside the bar does not bleed into it, at two fifths of the picture's
brightness. In the exe's build the screens are pictures on a plain
background - white, or `loading.bg`'s black - whose slivers reach well
into the picture, so each bar is that background - the picture's
corner pixel - throughout, and nothing more; the row's own edge would
carry the card's blur and its red rule out as streaks.

Neither build stretches anything itself. Drawing the scaled picture
and its bars into the locked back buffer was some seven million CPU
pixel writes a frame at 5120x1440, the same cost that made the lobby
drag; instead `bgrow` composes the picture at source size into a
surface `MGameD3D` keeps - 2176x600, offscreen plain in video memory,
made at the present through the same `CreateSurface` as the lobby's -
and one blit stretches the composite into the whole screen, video
memory to video memory. The composite is the picture in the middle,
each side area beside it as its sliver, blurred or plain, pre-stretched
by the picture's width over the screen's into the side area's columns
so the one uniform stretch after makes the bar's own eightfold one, and
the bands above and below as the first and last rows. `bgrow` finds
the surface through the exe's device object (`GAMED3D`, which
`Title.dll`'s build reads from the exe too, the exe being at a fixed
base): its vtable is `MGameD3D`'s at `0xf5d4`, so the base falls out,
and the annex from `0x17000` is scanned for the block's marker
`BGBLOCK`, the blob's place in it depending on which patches went in.
The block holds the surface, the composite's size and a flag; `bgrow`
locks the surface, composes, unlocks, sets the flag and touches the
back buffer not at all. The lock's description has to hold the
composite - its width and height when the lock gives them, and a pitch
of at least the composite's row at the depth the lock reports - or the
surface is unlocked untouched and the picture drawn as before: under
Proton-CachyOS 10.0 the lock reported 32 bits over a surface whose
rows were not that long, and the bars ran off its end (a write fault in
`Title.dll`'s `stretch`, the right bar's 351st column); 11.0 gives a
surface the composite fits. The stretch cannot happen there, the game
holding the back buffer locked around the row copy, so it happens at
the next draw through `MGameD3D`, or the next present, whichever comes
first - before any 2D the game draws over the picture, since that goes
through the same draws. Without a device, a block or a surface, or
with a composite too big for it, `bgrow` draws as it did. Split screen
comes out of the rect scaling.

The multiplayer lobby is the one screen that is not a draw at all: the
exe blits its BMP strips - the background, the chat panel composed
offscreen, keyed icons - into the back buffer itself through
`IDirectDrawSurface4::Blt`, at 640x480 coordinates (a `+ddraw` trace
shows them all: `(0,0)-(640,480)`, `(126,118)-(524,405)`,
`(611,451)-(635,475)` into the surface the present then blits to the
primary, which is `MGameD3D`'s back buffer at `0x10012554`; never
`BltFast`), so the whole screen sat in the picture's top-left unscaled.

`wide2d.asm`'s present hooks that `Blt` in ddraw's own vtable - shared
by every surface, so it is done once, with `VirtualProtect` around the
write. Scaling each blit into the box was the first version, and made
the menu drag: every one became a stretch, and Wine stretches on the
CPU. Now the lobby draws into a 640x480 surface of its own, made
through `IDirectDraw4::CreateSurface` (`[0x1001254c]`, offscreen plain
in video memory, the primary's format) the first time it is wanted and
again after a mode change has given the game a new back buffer: every
`Blt` into the back buffer whose rect is a 640x480-sized one within a
screen of the 640x480 - a panel sliding in starts off the picture, past
640 or below 480 - has its `this` swapped for that surface and its rect
cut to 640x480, the source rect cut by the same share, since a rect off
a surface fails the blit and the screen's edge cut a sliding panel at
4:3; a rect with nothing left is not drawn, DD_OK. So the lobby draws
exactly as it did into a 640x480 back buffer. At each present, for
eight presents after the last such blit (the lobby draws only what
changes, and the back buffer keeps between presents), that surface is
stretched into the 4:3 box with one blit, video memory to video
memory, and the side areas filled with a colour-fill blit each: the
background's colour, read from the surface behind the one blit that is
the whole 640x480 at (0, 240) - the plain part, left of the panel and
between the title bands - under a read-only lock, at 16 or 32 bits as
its format says. A rect bigger than 640x480, a null one, or another
surface's, passes; so does everything, unchanged, when the surface
cannot be made, and `d3dtrace` reports the create as `sr2 l hr ddraw
surface`. The GDI text is rasterised at 640x480 and stretched with the
rest. `DDSURFACEDESC2`'s `ddsCaps` is at `0x68`, after the 32-byte
pixel format at `0x48`; the caps written four bytes on land in
`dwCaps2`, and a surface asked for with no caps is refused.

The sides were tried two other ways first: the background's first
column stretched across, which came out as streaks of the surface's
dither, and a strip of it tiled at the box's scale, which came out
with pieces of the title in it - the title is composed into that
surface - and mirrored to hide the seams went through Wine's CPU
blitter.

The Australian build's mode setter clears the back buffer with the
width for both dimensions: at `0x441783` it loads `[WIDTH]` and pushes
that same value twice into the clear at `0x441180`, where Europe's
(`0x421a75`) and America's push the height as the first argument. The
clear zeroes width rows of a height-row surface. At 640x480 that is 160
rows past the end, which on a real card landed in whatever the driver
had left there; at 5120x1440 it is some three thousand seven hundred
rows past, and under wined3d the first frame takes a page fault -
`rep stosd` at `0x4411ce`, writing off the end of the surface, with ebx
the row's 0x2800 bytes and esi still counting down from the width. The
`clearsize` patch puts a thunk in the annex that hands the clear the two
globals the right way round - the height first, as Europe's caller does
- and the site takes a call to it. The thunk pops its return, pushes the
two, puts the return back on top and jumps into the clear rather than
calling it: the clear is cdecl and this caller cleans at `0x441794`, so
a thunk that called and returned would leave the width where the return
address belongs. `tools/clearsizetest.py` walks it.

**The sea.** The race's backdrop below the horizon is a layer the exe
builds at the race's start (`0x448c70`, one over (0, 256, 640, 480) - two
in split screen - `.SEA` loaded at `0x462b80`, the object made at
`0x462e10` with the class at `0x49dca4`, its update `0x4633b0`, its draw
`0x463500`) on an `MGLBackground` layer (interface `452593f2`, class
vtable `0x1000b0f0`: init `0x100030a0`, update `0x10003360`, draw
`0x10003de0`). The init lays a grid of 64-px cells over the rect widened
by 96 px a side, four rows of a 28-vertex strip, each vertex's depth
`-h * focal / (y - cy)` and its z and rhw from the renderer's `+0x40` and
`+0x44` at that depth, its texture coordinates from the inverse
projection at it; the update rotates it about a point by the camera's
roll and drops it by the pitch, and scrolls the texture; the draw is
four strips of FVF `0x1c4` through `+0xbc`, fog off. The lake is that
plane through a hole in the ground mesh. `sky*.mdl` is the sky.

In split screen there is no lake, and that is the game's own doing:
the sea's draw (`0x463500`) opens with `cmp dword [game+0x38], 5; je`
(`0x463517`), mode 5 being split screen, and draws nothing there, so
the hole shows the backdrop. The two layers the exe still makes for
split screen (the table at `0x4bc080`) are built before either half's
viewport is set, both about the full screen's centre (320, 240) - a
`gltrace`: the six `gp` reads come right after the exe's full-screen
`vp`, the halves' fourteen lines later - so the top one's rows all lie
above its horizon and its z above 1, the bottom's horizon is 128 rows
above its own; presumably what Sega saw, and switched the draw off
rather than fix. Tried and taken out: each half's viewport set before
its layer through the exe's `SetViewport` wrapper (`0x46bfd0`), which
gave the layers the right centres, and the `je` made nops, which
would have drawn them; the Dreamcast has no lake in split screen
either, so it stays as shipped.

The device's viewport, also in `MGameD3D`: the exe draws the countdown
digit itself, an untransformed indexed list (`0x42bd2f`, FVF `0x1e2`),
after setting the device's viewport itself (`0x42bcda`, MGameD3D's
`+0x158` of the second interface, `0x10006040`) from its own table at
`0x5b24f0` - 640x480, the split-screen halves, the 800x600 set, each
with the projection-centre fractions. The four numbers are a rect, left,
top, right and bottom, not a corner and a size: the setter takes the
width from right minus left (`0x1000605f`). They are a path MGameGL's `SetViewport`
never sees, which put the digit in the picture's top-left 640x480.
`wide2d.asm` takes that setter too: a rect no wider than 640 and no
taller than 480 while the picture is wider is scaled through a copy into
the picture's own 4:3 box, everything by the height and both its sides
carried past the bar, exactly as the 2D is scaled; MGameGL's rects, in
real pixels, pass. The rect alone does not settle the digit's size: the
setter makes the clip volume from the rect's share of the *screen* -
`clipW = 2 w / (screenW · f1)`, `clipH = 2 h (screenH / screenW) /
(screenH · f2)`, with `0x10012420` and `0x10012424` the display size
from the device's creation and f1, f2 the two floats at the end of the
struct - so a rect the size of the 4:3 box on a 32:9 screen holds
three eighths of the clip width the 4:3 screen has, and what is in it
is drawn as large as a viewport the whole screen wide would draw it.
The two fractions take the box's share of the screen's width, which
brings the clip volume back to the 4:3 screen's 2.0 by 1.5. Scaling the
rect to the whole picture, as the first version did, was worse again by
the ratio of the widths.
`d3dtrace` found it (every draw with its caller), after `gltrace` had
ruled out the renderer's paths.

The Graphic Settings page (`0x10003370` exec, `0x10002f20` draw; the
page object at `Options+0x14`, rows at `+0x18`, counts at `+0x58`,
cursor `+0x10`, pulse `+0x78`) showed the row's two choices side by
side from sprites (`0x1009c714`) and greyed the second without the
800x600 capability bit (`0x10003426`). `resolution.asm` makes the row a
list and adds an ASPECT RATIO row under it: the table is grouped by
aspect (`RESOLUTION_GROUPS`, five groups, the 21:9 sizes the usual
64:27 and 43:18), row 7 holds the group and row 6 the index within it,
its count the group's; a change of aspect puts row 6 to the group's
first at the next draw. Row 7 is the page's own machinery - the page
object has room for sixteen rows and left and right are generic - with
the page's six "7"s (the value loop's bound, the button-row tests in
the exec) made "8" so the cursor reaches it; its plate is row 6's
drawn 27 px lower with the loop's colours, its label and value text
through the stock 14-px routine (the font has no colon: two dots, one
6 px up). The resolution value is drawn as text at the first choice
sprite's place (`1920X1080`; no lowercase, no arrows), a wide size in
`SR2.CFG` that is in the table selects its group and entry on
entering, and DEFAULT gives 640x480 in 4:3.

### The credits

The ten-year championship ends on the credits: the race state's
sub-state 8 (`0x419af0`), which replays year ten's Super S.S. in a
window at 351-607 x 222-415 while the names scroll. The window is the
race's own scene pass (`0x418f30`, mode 4 with flag `0x20`): the
countdown full screen, then the frame shrunk about the window's centre
in 32-px steps to the window, through the exe's `SetViewport` wrapper
(`0x41905f`), and the rest blacked out by untextured quads from the
credits' draw (`0x48672a`, in `0x48656c`): the bands above and below
full width, the side pieces from -1 to the window's left and from its
right to 642. The per-frame clear is MGameD3D's, a `Clear2` with one
rect that is the whole back buffer (`0x10012410`, `SetRect(0, 0, W,
H)` at its init, `0x10005f40`), never the viewport. Two things went
wrong on a wide picture: `widegl` scaled the window's rect to the whole
width as it does the race's, so the replay rendered beside its black
frame; and the side pieces, scaled into the 4:3 box as 2D is, left the
clear showing in the side areas at the window's rows (a `d3dtrace`:
`sr2 b` why 3 for both pieces, nothing drawn). So a viewport rect that
is narrower than the 640 or off its middle goes into the box, and a
quad at one edge with no texture selected is drawn out to the screen's
edge. The fade at the end is the window's own, a quad over the right
half whose alpha ramps as the replay ends.

For a test without a year-ten save: the results step (`0x419830`)
hands on to the season's end step (`0x419a70`) only after a year's last
stage, `cmp [game+0x64], 3; je` at `0x4198fc`, and that step to the
ending only in year ten, `cmp eax, 0xa; jne` at `0x419ab7`; a `jmp`
over the one and nops over the other roll the credits after any stage.
There is then no Super S.S. replay to play, so the window shows an
unlit car at 0'00"000 and fades at once; the zoom and the window's
place are what can be checked that way.

### Loading screens

The stage's card - `des_AC.bg` and the rest, or `loading.bg` - is an
object the exe creates when the loading screen opens (`0x41a6f0` picks
the file by course and mode, `new` of 12 bytes with the vtable at
`0x49b138`, the object kept at `0x4d6938`) and deletes the moment the
course has loaded, in the state step at `0x4195b0`: `call 0x418070`,
the deleting destructor through the vtable's first entry, the object
zeroed and `inc dword [ebx+0x14]` on to the next state. A load that
took a while on the hardware of 1999 takes well under a second now, and
the card is gone before it is seen.

`loadhold.asm` replaces the six-byte store of the new object at the
create (`0x41a7bb`, `mov [0x4d6938], ecx`) and the six-byte load of it
at the step (`0x4195be`, `mov ecx, [0x4d6938]`) with calls into its two
entries. The first makes the store and notes `GetTickCount` - imported
by all four builds - and the second waits, `Sleep(10)` at a time,
until 3000 ms have passed since the note, then makes the load; `Sleep`
is resolved once through `GetProcAddress`. The wait is a plain sleep:
the game's loop does not run meanwhile, and the picture stays on screen
as the last frame presented. It is skipped when no note was taken, so
the other path that deletes the picture (`0x419d00`, an aborted load)
is left alone. `tools/loadholdtest.py` runs both entries under Unicorn
with the clock and `Sleep` stubbed.

### The gauge over the lake

The tachometer's plate is alpha-blended, drawn with the rest of the
HUD (`0x429d70`, called from the race state's draw at `0x418ab1` while
the state's `+0x3c` says so) after the scene pass, at z `0.0002` with
the z-write on. The lake (*The sea*) is not part of that pass: it is a
node of the root tree the frame object draws afterwards (`0x4280a0`:
the state's draw, then, with `[0x4d6a3c]` set and `[0x4e68fc]` clear
and a `BeginScene`, `0x470ff0` at `0x4280f2`, then the present), a
screen-space plane at z `0.96`–`1.0`, z-tested, meant to show through
the hole in the ground mesh. Under the plate it fails the test, and
the plate blends over what the scene pass left there - the backdrop's
flat grey. A `d3dtrace2d` with the `sr2 p` present markers shows the
order per frame: the HUD's lists, the sea's four strips, the present.
Stock does the same; the Australian build has no `[0x4e68fc]`.

`hudlast.asm` moves the HUD after the tree. Its first entry, in place
of the HUD call, draws the HUD there as before when the tree is not
going to run - the game not running (a paused race), or the flag set -
and otherwise draws nothing and notes the HUD as pending. Its third,
in place of the tree draw, draws the tree and then, with a HUD
pending, sets the full viewport through the exe's own wrapper
(`0x46bfd0`, the rect at `0x4b12f0`, as the state's draw did before
the HUD in split screen), draws the HUD and makes the reset the
state's draw made after it (`0x46cec0`: colour key and blending off,
on the renderer at `0x50b110`). The pending note, not the state's own
flag, so a state of another kind never gets the race's HUD.

The fade is a node of the same tree (class vtable `0x49b644`: update
`0x426860` takes the colour and alpha from the node's bytes at `+0x18`,
draw `0x426930` is `mov ecx, [0x50b110]; jmp 0x46bd80`, the renderer's
fade quad over the rect at its `+0x5650`, alpha at `+0x5668`, nothing
drawn at 0). The quad is at z `0.00014` with the z-write on, under the
HUD's `0.00024`, so a HUD drawn after the tree failed the test under it
and appeared the frame the fade-in ended - seventeen frames into a
race in a `d3dtrace`, a pop. The second entry, in place of the thunk's
eleven bytes, draws a pending HUD first and then the fade, so the fade
stays over the HUD as it was, and the late entry only draws a HUD the
fade node did not. `tools/hudlasttest.py` runs the three entries under
Unicorn with the exe's routines stubbed.

### Frame timing

The game steps its simulation at 60 Hz and times itself in `0x4287f0`,
called from each frame's `0x4280a0` between the step and the draw.
Init (`0x427eef`) takes `QueryPerformanceFrequency` / 60 as the budget
(timer object `+0x24`; `+0x28` says QPC is there, `0x4287a0` reads the
counter, `timeGetTime` only as the fallback). No `Sleep`, no
`timeBeginPeriod`. Each frame: present (`MGameD3D` `+0x80`); if more than
n budgets have passed since the last exit, extra steps of the simulation
without a draw, up to four (`0x428897`); then a spin on the counter until
elapsed > n × budget (`0x4288f0`); then `last = now`, so the overshoot is
not carried. n is `[0x4b2354]`, 1 or 2 from `settings+0x40` in `SR2.CFG`
at `0x41754b`.

Stock, in exclusive 640x480@60, the `Flip(DDFLIP_WAIT)` blocked on the
vertical blank; the spin was the fallback. The borderless `Blt` returns
at once, so the pace is the spin: 60.000 Hz on the counter, free-running
against the display. `frametrace` on Windows shows the game's own work
at 1-2 ms a frame, the blit at 0.2 ms, the spin the rest, and one
catch-up a run, at the race start. With managed textures it showed a
hundred catch-ups a run and 200-500 ms stage loads; that is why they
are not used. The catch-up test is a strict "elapsed > steps × budget",
so anything that holds a present for a fraction of a frame costs a
second simulation step and a second budget of spin: the present must
not wait. A wait for the vertical blank in it did exactly that on
Windows and is not there; `MGameD3D` `+0x54` (`0x10004d30`) is that
wait as a method the exe never calls. On Windows the layer renders the
frame after the blit returns, on its own thread; the loop never sees
the render.

`frametrace`, a diagnostic applied by name, hooks the gate's entry
(`0x4287f0`, `mov eax,[0x4d6a3c]`) and its exit (`0x42890b`, the five
bytes before `pop ebx; ret`) and logs every drawn frame to `frames.log`
beside the exe: the counter at the entry, after the borderless present's
blit (found through the borderless patch's jump at MGameD3D's present),
at the exit, the step count and the gate's four flags, with the budget
and which counter in a header; `tools/frames.py` reads it and splits
each frame into work (step and draw), blit and rest. An interval of two refreshes with two steps is the catch-up; with
one step, a present the display held, or a frame the game chose not to
catch up. The step count logged is `ebx`, which in the Australian exe is
the divisor's countdown - its count is in `edi`. The flags: `0x4d6a3c` running, `0x4d6a6c`
paused (the Start-button menu, `0x41932d`; the present is skipped too),
`0x5a2660` the debug DLL, `0x4d6930` catch-up allowed, cleared on the
first tick of the two-frame transition object of class `0x49b138`
(`0x41a9e0`) and set on its second, which builds the next scene.
DEVELOPING.md says how to apply it.

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

Borderless full screen, or the framed window, is how the game runs; the
stock exclusive 640x480 display mode is no longer an option the patcher
offers (`windowed` and `borderless` cannot be left out). Alt-tab keeps its two patches. `DDSCL_NORMAL` surfaces can still be
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
the screen stays blank. Two patches:

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
on success (`0x10004385`). A lost video-memory surface comes back empty
from `Restore` - DirectX's contract, and Wine keeps to it - so if a
surface were ever lost the textures would come back blank until the
next load. A task switch from a window loses nothing, and no loss has
been seen on Windows 10/11 or Wine. Managed textures
(`DDSCAPS2_TEXTUREMANAGE`) would cover it, but the Windows DirectDraw
layer's managed path is slow - long stage loads, runs of slow frames -
so they are not used; if a loss ever shows, the answer is to keep the
system copy and `Load` again after `RestoreAllSurfaces`.

### The Options screen

`Options.dll` draws from `BINDATA\MISC\OPTIONS.TXR`: `RTEX`, a count,
16-byte entries `(format, size, bytes, 0)` and, from `0x1000`, the pixels
back to back. Format 0 is 565, 2 is 1555, 8 is 4444. Twelve textures; the
Dreamcast Device Settings page survives in them unused - both controller
diagrams (8, 9), every label and the full uppercase font (6), the
calibration bars (7). What is not there is a steering-wheel icon: sheet 10
holds car, speaker, monitor and a blank plate, and the blank plate is the
cursor's red frame, drawn as a nine-slice of 28-texel pieces.

`OptionsModeInit` (`0x10003770`) loads the TXR and binds ten *pages*
through `0x1000ed90`: a page is a table of 20-byte UV entries
`(texture, u0, v0, u1, v1)`, and the loader swaps each texture index for
its handle in place. A *sprite* is 32 bytes - page, quads, count, width,
height, x, y, 0 - and a *quad* 52: UV index, a rectangle about the sprite's
centre, four vertex colours. `0x1000e850` draws a sprite at a position,
scale and colour, `0x1000e5e0` at its own position. Both put the quads on
one list, which the flush (`0x1000e390`) sorts by depth (`0x1000e510`, a
stable merge on the value the device makes of z) and draws far to near:
a sprite at z 16 goes under one at z 12, and among equals the order of
submission stands. The menu's page is `0x100ac9d8` with 54 entries, one
`-1` between sprites; those separators are spare, and `0xe` and `0x11`
now hold "DEVICE" from sheet 6 and the new icon.

The menu itself (`0x10003dd0` init, `0x10003f40` exec) owns a cursor
(`0x1000ba40`) and an icon set (`0x10002330`), both over three-entry
tables at `0x1009c820` (frames), `0x1009c82c` (icons), `0x1009c838`
(labels), and draws the labels itself at `0x10003e10`. The cursor draws
the frame table's entry for the item in place while it rests, the first
entry at its animated x while it slides, at z 16 with its pulse as
alpha; the icons go at z 12, so the frame sits under the plate and shows
as its red holes and a 4-px outline. The menu's state after a confirm
(`0x1000421c`) draws the frame once more at z 14 while the icon set
zooms the icon. That is five code references to the tables in all, and
the patch moves every one of them. Confirming returns the index with bit
15, and `0x10003c6b` dispatches it through `0x10003dc0` to the page
states; the fourth slot was the exit state, never reached with three
items. The stub in the annex selects state 0xc. The four items sit at
x 110, 250, 390, 530.

The item's label is "DEVICE" over the stock "SETTINGS". Its icon is on
a thirteenth sheet the patcher appends to `OPTIONS.TXR` (the count and a
16-byte entry in the 4 KB header, the pixels at the end; 256x256 like the
icon sheet; the loader sizes its handle and entry arrays from the count,
and the DLL's copy of the handles has room for 256): the monitor icon's
plate with the picture's box filled back to the plate's grey, and a
steering wheel cut out of it the way the stock pictures are - holes in
the plate, alpha 0 with a one-texel ramp, the menu's dark background
showing through - drawn by the patcher (`wheel_mask`), not copied from
anywhere, with the car icon's own UVs (the page's UVs are three-decimal
values, 126.2 texels across 126 pixels, and exact fractions sample
visibly differently). The label sheet is checked by the texels of its
font and label rows before anything is written. Only one of the twelve
sheets is localised, and it is not that one: sheet 6, the font and the
labels, is the same file in the English and the Japanese
`OPTIONS.TXR` - so is everything else - while **sheet 4, the frame's
message lettering, is Japanese artwork in the Japanese one**, all
twenty-one letters the hint lines need among the differences. That is
why the lettering is carried in the patcher (`HINT_LETTERING`) rather
than cut from the file being patched; cutting gave a hint bar of
nonsense on a Japanese install, and the check, which looks at sheet 6,
passed it. The carried texels are the English sheet's own, so an English
install's appended sheet is unchanged, and every language now gets the
same bar.

The top-level machine (`0x10003af0`) has twelve states behind `cmp eax,
0xb` and a table at `0x10003d90`: 1 re-inits the menu, 2 runs it, 3/5/7
init a page and 4/6/8 run it, 0xb leaves. The table moves to the annex
with two more entries and the compare goes to 0xd: 0xc is the page's
init, 0xd its exec, both in asm/devices.asm, entered as every case is
with `esi` the Options object and leaving through the dispatcher's
epilogue (`0x10003cd6`). Init binds the page's own UV table through
`0x1000ed90` - once per load of the DLL, flagged in the blob, since the
binding writes handles over indices in place (the stock pages are bound
once, in `OptionsModeInit`; the exe reloads the DLL for each visit) -
and starts the slide-in. Exec draws the list, moves the cursor, and
slides: in from the right at 640 down by 40 a frame, out to the left on
cancel or on confirm over BACK, the menu's state set at -640, the stock
pages' numbers.

The list is 40-byte entries - kind, sprite or string, x, y, z or text
flags, alpha, red, green, blue in 256ths, and the cursor's hold on the
entry - built by `devices_page` in the patcher in the Game Settings
page's terms (`0x100025f0` draws it): its header band, group plate and
row plate are that page's own sprites (`0x100a3128`, `0x100a3290`,
`0x100a4198`, found by their first quad), plates at z 14 with alpha
0xd8, text at z 10, the text through the stock routine `0x1000df10`
over its 14-px glyph sprites (`0x1009c080`, one sprite a glyph, a
256-byte character map at `0x100fcc04` it fills on first use): (string,
x, y, z, advance for a missing glyph, sx, sy, alpha, r, g, b, table,
flags), flags 4 proportional, 1 right-aligned, 2 centred. The table has
letters, digits, `.`, `+`, `-` only; the colon is a piece. The glyph
cells carry a texel of margin around the ink and need it: boxes cut to
the ink render narrow and ragged. Geometry as the stock's: the band and
heading at y 87, the group plate at (48, 106), rows of 18 from (261,
106), 6 more between groups, group text at x 56, action at 269, colon
at 397, value at 405, the buttons at y 404. Two groups, PLAYER 1 and
PLAYER 2, seven rows each.

The cursor is the stock's (`0x10002c30`): up and down through the rows
and the button row, DEFAULT then BACK with left and right between them,
wrapping; the stock's sounds, 0xe for a move, 0xf for a confirm, BACK
included, 0x10 for backing out. What it holds is drawn as Game Settings
draws it: the row's plate (0x100, 0x100, 0, 0), its group's (0x100,
0x100, 0x20, 0x20), the button (0x100, 0x100, p, p) and the row's values
white with alpha 0x80 + p/2, p the page's pulse, 0 to 0x100 and back by
0x10 a frame (`0x10002a23`). Each entry carries which rows hold it and
how. The page shows one player at a time: a selector row - the group
plate centred, PLAYER 1 or 2 on it, left, right or confirm switching -
then the KEY and PAD headings and the nine rows, the eight driving
actions and the deadzone, on Graphic Settings' own row sprite - a
123-px label plate, a 30-px fade, a 273-px value plate, three quads - at
its x and 24 px apart as it spaces them, a line between the key and pad
columns cut from a hint strip's white margin.

The values are live. The page reaches the game's input objects through
the holder (`0x100b9464`, the exe's `0x50b120` block): its `+8` is the
exe's input wrapper (vtable `0x4a158c`; `+0x14(mask)` a player's
pressed-edge key bits), whose `+4` is `MGInput`'s input object, and from
there `GetConfig` (`+0x34`), `GetDevice(3, 0)` (`+0x20`) for the
keyboard and its `GetState` (`+0x38`, the 256 key bytes), the config's
record list at
`+0x124` - a pointer to the head node of a ring of (next, prev, record)
- and `Persist` (`+0x30`) to save (*Gamepad*); the pad through the poll
the annex publishes at `PADPOLL`, a dword in the writable room past the
end of `.data` (`0x5a1ff0`; Australian `0x60bff0`), since the Australian
device has no poll method. A row's key record is
the first of its action with a source under 0x100, its pad record the
first at 0x300-0x37f without the menu-only bit. Confirm on a row
snapshots what is down and waits: the row pulses blue to white and the
bar says to press the button. A key or pad input released since the
wait began and pressed binds - the row that had it, either player's for
a key, the same player's for a pad input, takes the row's old one - and
both configs are saved; ESC, or Start held 60 frames, gives up. Left and
right on the deadzone row step it 5%, saved through a `DZnnnn` name.
DEFAULT puts the shipped set back from the page's data block, which
follows the strings (`bind_data`): the rows' action ids and a live
flag, the defaults, the value strings the page fills, a name per
scancode and per pad input.
`tools/devicestest.py` drives the routines under Unicorn against stubs
for those objects.

The hint bar under every stock page belongs to the frame object
(`0x10001cc0`), which pops one of fifteen lettered messages in and out
by a message number in `0x1009c784` (`0x100021b0`, height 0 to 1 by 0.1
a frame, the bar growing from its bottom edge at y 451). All fifteen are
lettered, so the page leaves that at -1 and draws its own: the bar's
plate and white strip copied from message 14, grown the same way once
the page is in place and dropped before it leaves, and on it one of two
lines set letter by letter from the frame's own lettering - sheet 4, six
lines in a condensed face, dark ink on opaque white - one texel box a
letter, at the boxes `HINT_GLYPHS` names on the English sheet, from the
texels `HINT_LETTERING` carries because that sheet is localised (see
*The Options screen*): 17 rows from a row above each line's ascenders,
since the two lines the capitals come from sit a row lower against their
tops, a texel apart, 5 for a space, onto
white on the appended sheet at patch time, two texels of white
beyond each end so the edge samples filter to white and not to the clear
gutter. The lines say what those six lines' letters allow; there is no N
or R among the capitals, so no ENTER.

The new data carries absolute pointers, so the annex gets a relocation
block appended to the directory in `.reloc`'s zero tail.

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

Four pressings are supported, told apart by the exe's MD5 in `BUILDS`:

| | Exe linked | `.text` | Cabinet | Against the European |
| --- | --- | --- | --- | --- |
| **Australian** | 3 Jun 1999 | 0xd2c9a | `0x01005100` | the first release: 259 KB more code, a Windows 9x check, no `LAUNCH.EXE`, English and Japanese only; its own `AdvTelop`, `Champagn`, `MSelect`, `MainMode`, `Options`, `Record`, `ReplayGallery`, `SegaLogo`, `Title.dll`, `miscdll.dll`, `MGAudio.dll`, `MGInput.dll` |
| **European** | 21 Oct 1999 | 0x936ca | `0x01000004` | - |
| **Japanese (MediaKite)** | 29 Nov 1999 | 0x936ba | `0x01000004` | MediaKite's rerelease, MKW-166: a relink of the exe alone, sixteen bytes shorter; no `VendorLogo.dll` and two fewer files in *BINDATA 2* |
| **American** | 3 Oct 2000 | 0x9367a | `0x01005100` | a relink: the exe (`.data1` added, `.data` 0x100 longer), `LAUNCH.EXE`, `MSG_S.dll`, `VendorLogo.dll`, `sr2_cpl.cpl`; its own `TENYEAR` trackside art |

Everything else is byte-identical across the four, `MGameD3D.dll`
included. The play discs carry the same assets and one soundtrack (see
*The play disc*).

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
for byte** (`51b3da97…`), and its `MGInput.dll`, `MGAudio.dll` and
`miscdll.dll` are the European files too. The European release is the
Japanese one at patch level 2.50 with a later `Champagn.dll` (2.0.0.8,
20 Oct 1999, in no update). The exe versions in order: 2.0.0.2
Australian, 2.0.0.6 UPDATE231, 2.0.0.7 UPDATE240, 2.0.0.8 UPDATE250 and
European, 2.0.1.1 American. The Australian is older than every update,
by version and by date. 2.0.1.0 has not been seen.

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

The Japanese pressings: HCJ-0145 (Sega, 25 Jun 1999), DWRPD-00081
(DigiCube, 22 Nov 2000), MKW-166 (MediaKite, 2 Mar 2001) and SPB-040
(bundled with I-O DATA's GA-TNT2). Upstream holds all four out of
`BUILDS`: its rows are checked against Redump dumps, and no verified
dump of any of the four has been seen - Redump has no MKW-166 sample at
all, none as of 20 September 2026, so this disc cannot reach that state
by waiting.

**This fork carries the MediaKite one anyway, as `Japanese
(MediaKite)`, and it is not upstream's row.** It came from a single
image of an MKW-166 disc rather than a verified dump, and a problem with
it belongs in this fork, not in upstream's issues. What stands behind it
is that disc, read closely, and every check this repository has, run
against an install made from it; see *The Japanese releases* below for
the pressing itself and what is known of the other three.

The MediaKite exe is the European one relinked five weeks later with
sixteen bytes less `.text` and nothing else moved: the same sections at
the same addresses, the same import slots, the same globals. The missing
sixteen fall between `0x4404b0`, the error box, which is where Europe has
it, and `0x444bd0`, the processor check, sixteen back from Europe's
`0x444be0`; nothing in the tables sits between the two. So every site and
code address past it - the screen change, the CD level, the loader's
drive scan, the registry open, the five volume entries, `RESUME`, and of
the HUD work `TREEDRAW` and `FADEDRAW` - is the European one less
`0x10`, and everything before it, every data address and every import
slot, is the European one unchanged. Every exe site in the row was
matched byte for byte at those offsets before it went in, the call sites
read back through `_check_call`, and the twelve other files the row
fingerprints are the European bytes, so the eight DLL patches come out
at the European MD5s. Its disc carries all six languages, as Europe's
does.

The MediaKite release ships no `VendorLogo.dll`, though its exe still
looks for one: the loader at `0x4533e8` tests the handle and leaves the
module's five entry points zero when the `LoadLibrary` fails, so the
screen is simply not there.

A row of `BUILDS` holds the fingerprints of the six P3 files and the
three patched DLLs, the exe's sites, the import slots those sites name,
and the addresses the exe stubs read. Every patched instruction is
the same bytes in all four exes bar its operands; each site was found
by its masked context and read back before it went in:

| European | American | Australian | MediaKite | |
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

The ten SetTextColor sites are in the rows; the MediaKite exe has all
ten where Europe has them. The American import table is
the European one with six CRT slots reordered, none the patches use; the
Australian is laid out afresh, so its row names the five slots. The
eight slots the MediaKite row names sit where Europe's do. The
Australian `Title.dll` has the row copy at the same offset in identical
code; its `MGAudio.dll` has the same eleven calls and one load of
`mciSendCommandA`, which the music patch finds for itself, and one
different branch in Init, for which see *No mixer needed* in the table
above.

Nine files are patched in every build - `SEGA RALLY 2.exe`,
`MUSASHI\MGameD3D.dll`, `MUSASHI\MGameGL.dll`, `MUSASHI\MGAudio.dll`,
`MUSASHI\MGSound.dll`, `MUSASHI\MGInput.dll`, `Title.dll`, `Options.dll`,
`ReplayGallery.dll` -
and `BINDATA\MISC\OPTIONS.TXR`. Each gets
a `.bak` beside it, the untouched original; the patcher always starts
from those, so patching twice is patching once and restoring is a
rename, and a file that a run with fewer keys leaves alone goes back to
its `.bak`, so the keys given are the patches in place.

### The Japanese releases

Japan had four pressings of its own. One of them, MediaKite's, is the
`Japanese (MediaKite)` row - this fork's own, not upstream's, for the
reasons under *Builds* above. The other three are builds of their own
and that row is not them:

| Part number | Released | Known as | Patch level |
| --- | --- | --- | --- |
| HCJ-0145 | 25 Jun 1999 | the Sega PC release | none |
| DWRPD-00081 | 22 Nov 2000 | the DigiCube release | unknown |
| MKW-166 | 2 Mar 2001 | the MediaKite release | UPDATE250 |
| SPB-040 | unknown | the I-O DATA bundle | unknown |

SPB-040 was never sold on its own: it came with an I-O DATA graphics
card, and its play disc is printed `GA-TNT216専用` - for the GA-TNT2/16.
[I-O DATA's own page](https://www.iodata.jp/products/graphics/tnt2/stage4.htm)
for that card says two games come with the GA-TNT2 series, the first of
them *PC版 SEGARALLY2(製品版)* - the retail game, not a demo - beside
*Expendable Lite*; the card and the page are of 1999. The page gives no
part number, so SPB-040 is tied to it by what is printed on the disc and
by the dates, not by I-O DATA. Which build is on it is unknown, as is
when it went out; almost nothing about this pressing is recorded.

HCJ-0145 is the original Japanese release, and the one Sega's updates
were for. What each update carries is under *Sega's updates* above, read
off the files themselves; what sega.jp said it published, and when, is
this - the installers named are the FULL ones, the whole update in a
single file:

| Published | Installer |
| --- | --- |
| 25 Jun 1999 | `UPDATE231FULL.EXE` |
| 29 Jun 1999 | `UPDATE232FULL.EXE` |
| 14 Jul 1999 | `DisplaySettings.exe` (the settings tool, not an update) |
| 15 Jul 1999 | `UPDATE240FULL.EXE` |
| 25 Oct 1999 | `UPDATE250FULL.EXE` |

(The pressings, their patch levels and these dates come from
[sega.jp's patch page](https://web.archive.org/web/20080611152022/https:/sega.jp/pc/rally2/patch_old.shtml)
and [its library index](https://web.archive.org/web/20010823045326/http://www.sega.co.jp/sega/pc/lib/lib.html)
as the Internet Archive kept them. The publication dates run a few days
ahead of the link dates in the files, as they would.)

Nothing on the MediaKite disc names a patch level. What its exe does say
is that it was linked on 29 Nov 1999, five weeks after UPDATE250 went
out, which fits; its version resource reads `2, 0, 0, 9` and its language
0x0411. An HCJ-0145 disc, patched or not, a DigiCube one and an SPB-040
are unknown builds here: their exe will not have the MediaKite MD5,
`build_of` will not place it, and the patcher stops with *is not a
Pentium III build the patcher knows* before it writes anything. An image
of any of the three would be welcome - SPB-040 most of all, since nothing
is known about it.

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
warns - string 5, `WARNING`, OK/Cancel - when that memory is under
4,000,000 bytes or bits `0x1800` of the entry's `+0x34` are clear; bit 0
of the same word clear returns −1, "No 3D capability". Wine passes the
bits; a Radeon R9 380 on Windows does not, or wraps the DWORD, and gets
the box on every start. No card sold since is on the list, so nocardwarn
skips the box; the −1 path stays.

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
  Wine, Proton and Windows 10.

### Car models

A `.mdl` is one block of file offsets, fixed up to pointers at load
(`0x474e80`): dword 0 the size, dword 2 the top node's link. A node is
0x80 bytes: `+0` mesh, `+4` its flag block, `+8` an index, `+0xc` a
kind (0 body, 1 wheel or interior, 2 window, -1 lamp or light), `+0x10`
bounding centre and `+0x1c` radius, `+0x20` position, `+0x2c` rotation,
`+0x40` scale, then at `+0x60` child and `+0x64` next; the header points
at that link, so the top node is at size - 0x80. A mesh descriptor is
0x20: vertices (32 bytes each: position, normal, u, v), indices,
material, counts, and at `+0x18` 10 for the ordinary path; its flag
block follows: `0x903` body, `0x103` wheel, `0x113` window, `0x1003`
lamp glass, `3` a glow quad. A node whose flag block is null holds a
light (`tenkougen.mdl`, the two headlight cones in a body). Nothing
applies the node transforms but the exe: the wheels' draw (`0x47e450`)
translates, rotates and scales by them; the body's (`0x44bba0` and the
LOD table at `0x4bc398`) and the lamp models' (`0x44c320`, walking the
tree at `0x44c3f0`) draw each mesh under the car's matrix as it is.

A car's set (`CAR\<name>\`, the name table at `0x4cc400`, loaded at
`0x469b69`): `s_`, `m_`, `l_`, `r_<car>.mdl` the body by detail, each a
body, four wheels, more parts with the detail, one or two windows and
the two lights, mapped into `body.txr` and its dirt variants;
`normal.mdl`, `snowy.mdl` + `sn_light.mdl`, `desert.mdl` +
`de_light.mdl` the lamp kit by course type (`0x4ccf44`: 0 desert, 2
snow, else normal - `normal.mdl` is the lens glass alone, `snowy.mdl`
the pod and its glass, `desert.mdl` the snorkel, scuttle lamps, bull
bar and spare-wheel rack, into `option.txr`); `ft_light`, `bk_light`,
`hazard`, `bkfire`, `tenkougen`, `brake`, `small`, `close` the glows,
each a quad at the lamp's place, +z the front. A race's car object
(`0x469f12`) gets a 0x68-byte glow object (`0x485250`) per glow model
holding a clone of its top node; `0x4855f0` draws it translated by the
node's position, the quad's size and brightness from the view angle
and distance. A car's `Draw` (`0x44b0c0` the player's, `0x442b30` an
opponent's) is wheels, glows and kit, then the body, under one push of
the car's matrix (`0x128` in the car). The desert kit's black pieces on
the Celica - the snorkel up the left A-pillar, the backs of the two
scuttle lamps - are that model as drawn, not a placement fault; a
trace of the model draws showed the kit under the body's own matrix.

One thing the creation does to the loaded data: with the desert kit
it adds `0x4cd2cc[car]` (0.125 for half the cars) to the top node's z
of `de_light.mdl` (`0x46a609`), and the models stay loaded between
races of the same car, so that glow creeps forward a step each race.

### The registry

The exe imports no registry function. `MGameReg.dll` is the registry: its
Open (`0x10001420`) is `RegCreateKeyExA(HKEY_LOCAL_MACHINE, "Software\%s\%s",
KEY_ALL_ACCESS)`, called from the exe (`0x47ef5e`) with `"SEGA"` and
`"SEGA RALLY 2"`, and the resulting object is handed to `MGInput`'s init
(`0x47ef9e`): the controller configuration lived under that key, written
by `SR2_CPL.cpl`, the "Controller Settings" Control Panel item the
installer added. The game only reads it and runs on its defaults when it
is empty - and writes player 1's defaults there itself on that first
run; player 2 has none without the applet. The object serves nothing else
in the exe (`MGameReg`'s `App Paths` lookup is never reached), so with
the Open skipped and `MGInput`'s load and save replaced (*Gamepad*) the
key is never made, which is also what Windows without administrator
rights needs. Nothing in `setup.ins` writes under `Software\` except the
DirectPlay lobby key `Software\Microsoft\DirectPlay\Applications\SEGA
RALLY 2`.

### Gamepad

`MGInput.dll` (`0x10000000`, relocated; one build in the European and
American releases, an older one in the Australian with the same
interfaces at other addresses) reads every action.

**The model.** The exe's init (`0x47eff0`) makes a config per player,
named `"0"`/`"1"` at `+0xc`, attaches the keyboard device and loads it
through `Persist` (vtable `+0x30`, `0x10007510`; flags bit 0 save, bit 1
keep what is there) - player 1's twice, unnamed and clearing
(`0x47f094`), then named `"0"` and appending (`0x47f0ca`). An action is a
`0x34`-byte record: id, repeat delay and rate in frames, deadzone and
saturation in 0..10000, up to eight source ids that are ANDed, the first
carrying the value. Its object is `0x15c` bytes: `+0x10c` id, `+0x110`
deadzone, `+0x114` saturation, `+0x118` delay, `+0x11c` rate, `+0x120`
the scaled value, `+0x124` frames held, `+0x128` the press event,
`+0x12c`/`+0x130` raw value and range, `+0x134` sources seen, `+0x138`
their count, `+0x13c` the ids; import and export at `0x10008890`,
`0x10008910`. Ids: 0 accel, 1 brake, 2-5 up, down, left, right (the
menus, with repeat; 4 and 5 are also the steering), 6 shift up, 7 shift
down, 8 handbrake, 9 view, 10 enter, 11 escape, 12 start - the race's
pause (`0x419306`) and a confirm in the menus, like 10. Sources: 1-0xff
keyboard scancodes, 0x101-0x168 joystick, 0x201-0x20b mouse, answered by
the device's poll (`0x100056c0`, `(this, source, &value, &range)`). The
config's update (`0x10007100`) has every record poll every attached
device, then finalise; `GetActionState` (`0x100078b0`) takes the largest
magnitude among an id's records, so a key record and a pad record for
one action coexist.

**XInput.** asm/padinput.asm, hooked at the load, the save, the update
and the device's poll - the Australian build has no poll method, its
record update (`0x10008170`) calling a static poll per device type, so
there the keyboard poll's address in that dispatch (`0x100081a8`,
`0x10007e40`, five arguments) is pointed at the annex's own entry; a
third entry, `(source, &value, &range)` for the page, is published at
`PADPOLL` - answers sources `0x300 + player * 0x40 + input`: the sixteen buttons as `0x80`/`0x80` like a key, the triggers
over 255 past the usual threshold, the eight stick halves rescaled past
the player's deadzone to 0..10000. The update hook refreshes the
config's player first: each side keeps an XInput slot, takes the first
free one when it has none, looking every 60 frames, and clears its state
when the pad goes. Side 1 looks only while side 0 holds a pad, so the one
pad there is - at the start, or plugged back in - is player 1's whichever
side's look falls first; before that, a pad unplugged and replugged in
the menu came back as player 2's (seen in a `+xinput` log: side 1's
look, a frame ahead, took slot 0, and side 0 then skipped it as held).

**DirectInput 8.** The DLL made its DirectInput object with
`DirectInputCreateA(hinst, 0x500, &out, NULL)` (`0x1000294d`, through
the thunk at `0x10008a30`, the one `DINPUT.dll` import), took
`IDirectInput2` from it (`0x10002963`) and kept that at `+0x10` of the
input object; `EnumDevices(0, cb 0x10002300, &vector, ATTACHEDONLY)` at
`0x100025e1` collects every attached device, `DIDEVICEINSTANCE` by
`DIDEVICEINSTANCE`, with no type filter, and the device init
(`0x10003910`) takes `GetDeviceInfo` and `GetCapabilities` and asks each
device but the keyboard for `IDirectInputDevice2` (`0x100039c2`). That
enumeration runs through Windows' legacy `dinput.dll`, which is where
the starts that hang on a white window with certain HID devices go
wrong; `dinput8.dll` does not. Its objects carry the same vtables -
`IDirectInput8` matches `IDirectInput2` slot for slot, `CreateDevice`
`+0xc` and `EnumDevices` `+0x10` where they were, and
`IDirectInputDevice8` is `IDirectInputDevice2` with three methods after
- the enumeration flags and class values are the same numbers, and
`DIDEVICEINSTANCE`, `DIDEVCAPS` and `DIDEVICEOBJECTINSTANCE` keep their
DirectX 5 layouts, so the DLL's calls stand once the object is
DirectInput 8's. asm/dinput8.asm makes it so: the eighteen bytes of the
create call become a jump to it, and it calls
`DirectInput8Create(hinst, 0x800, IID_IDirectInput8A, &out, NULL)`,
found once through the DLL's own `LoadLibraryA` and `GetProcAddress`
slots, the result back at the site's continuation; a machine without
`dinput8.dll` gets `E_FAIL`, as a failed create did. The two interface
ids in `.rdata` are rewritten to DirectInput 8's, so the two
`QueryInterface` calls succeed and hand back the same pointers. The one
thing that changed meaning is `DIDEVCAPS.dwDevType`'s low byte, the
device's kind at `+0x260` of the device object, which the DLL switches
on as 2 mouse, 3 keyboard, 4 joystick (`0x10003490`, `0x10003570`,
`0x10006550`) and carries as the kind byte at `+0x24c` of the record
the game and the Device Settings page see: DirectInput 8 says 0x12,
0x13 and 0x14-0x1c for the joystick kinds, 0x11 for a device of no
kind. The stub's second entry, called where the DLL first reads the
byte - the `cmp byte [esi+0x260], 3` at `0x100039ac`; the Australian
build's `mov edx, [esi+0x260]` at `0x100039f9`, it having asked for
`IDirectInputDevice2` before - writes the old code over the new and
then does what the displaced instruction did, the flags kept through
the `ret`. The instance copies in the enumeration vector keep
DirectInput 8's `dwDevType`; nothing reads it, the loop over them
(`0x100026ab`) looking only at the instance GUID. This is what dinputto8
does for the DLL at run time, done once at the three sites; DirectInput
wheels and pads go on working through the same calls.
`tools/dinput8test.py` drives the DLL's own create routine under
Unicorn against a stubbed `dinput8.dll`, with and without the DLL, and
the kind entry across the type codes.

**Devices of no kind.** With the list enumerated, the loop at
`0x100026ab` makes a device of every instance whose GUID is not null:
`CreateDevice`, the init above, an object of the DLL's own, polled every
frame. On a machine of today that is a dozen things that can never give
input - LED controllers, a stream deck, an audio device's control
collection, a receiver's spare collections; the Xidi logs from the
repack's testers list them - each opened, each a place for a driver to
stall a `CreateDevice`, which DirectInput 8 does not save. DirectInput 8
reports them as `DI8DEVTYPE_DEVICE`, 0x11, a device of no kind, and
asm/nogeneric.asm leaves those out: the loop's `je skip; mov ecx,
[esi]; push edx` after the null-GUID compare becomes a jump to it; it
makes the branch on the compare's flags, looks at `dwDevType` (eax
holds `guidInstance`, so `+0x20`), skips a 0x11 the same way the null
GUID is skipped - the list keeps a zero in that slot, a state the DLL
already handles - and does the two displaced instructions on the way to
the continuation. Mice (0x12), keyboards (0x13) and every controller
kind (0x14-0x1c, wheels 0x16 among them) go through as before. It needs
`dinput8`, whose type codes these are. `tools/nogenerictest.py` enters
the site as the DLL would, for a null GUID, a 0x11 and each kept type.

**The store.** The registry helper's load and save (`0x10008130`,
`0x10008210`) become the annex's own: a table of key and pad input per
action per player and the two deadzones, kept as text in `SR2.CFG` - a
section a player and device, `[1P Controller]`, `[1P Keyboard]`, of
`Name = value` lines for the eight driving actions and `Deadzone = 10`
in percent; the names are the page's with spaces as underscores, `-`
for none; the `=` is optional, an unreadable section header closes the
section, unreadable lines keep the defaults, the deadzone clamps to
0-90%. A file with the game's 100-byte block ahead of the text (from
before *No registry* moved it to `SR2.DSP`) is read past it. A load
generates the player's records: the action's key record and pad record,
then the menus' fixed ones - arrows (WASD for player 2), D-pad and stick
halves on 2-5 - the bindable first, which is what the page takes as a
row's; only unnamed loads get records, or player 1's would double. A
save takes the table back out of the exported records (the first key
and pad source per action), a name beginning `DZ` the digits after it as
the deadzone, and rewrites the text. The menus' left and right are the
steering's actions, so their fixed sources are *menu-only* - a key at
`0x400` + scancode, read from the keyboard device's array at `+0x308`
(type byte `+0x260` is 3), or a pad input with bit 5 set - and answer
only while the exe's car table (`CARS`, `0x4d64bc`) has no car in slot
0: the cars exist from a race's setup (`0x412aac`) to its teardown
(`0x412c67`), whatever the mode. Input `0x3f` reads a player's deadzone.
The name tables and defaults are data the patcher appends after the
code (`annex_tables`); `annex_records` and `annex_text` model the
output. `tools/padinputtest.py` runs the four entries under Unicorn
against the real DLL.

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

`SR2.CFG` is 100 bytes, read straight into the settings block at
`[0x50afe0]` (`0x427740`) and written back at shutdown (`0x427880`): the
DirectDraw device name (`display`, the primary), which `0x426ec0` looks
for among the enumerated devices, zeroing the block when none matches;
five DWORDs at `0x20`, of which `+0x28`, `+0x2c` and bits 1-2 of `+0x30`
are capability flags recomputed each start from the device's video
memory (thresholds `0x426fb8`-`0x4270ac`) and the rest `LAUNCH.EXE`'s
options; `+0x58` a copy of the live block's `+0x54`; `+0x5c` the disc
flag (below); `+0x60` the language from `GetUserDefaultLangID`
(`0x4272b0`, 1 English, 2 French, 3 German, 4 Italian, 5 Spanish, 6
Japanese). The in-game options live in `SR2_SAVE.DAT`. With *No
registry* the block's file is `SR2.DSP`.
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

Read from beside the exe with `GetPrivateProfileStringA` (`0x427c01`):
`[DebugSettings]` with `DebugInfo`, `CourseCollision`, `CarCollision`,
`CPUCar`, `Course`. `DebugInfo` goes to `0x5a2688`, which nothing reads.
The overlay `Total:%5dKB Used:%5dKB Free:%5dKB Quality:%s FPS:%2d
TPF:%5d` (`0x428140`) is gated on `0x4e68f8`, set only when a
`DebugDLL.DLL` beside the exe loads and exports `NagaSp` (`0x427340`),
and its one call site (`0x428107`) is on the branch taken only when that
flag is clear, so it cannot draw in the retail build: a leftover of the
debug builds, in which the DLL did the presenting (`0x428825`). There
is no in-game frame counter.

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
  (`MCIERR_INVALID_DEVICE_NAME`, `0x107`). The hook therefore makes every
  device call from one worker thread of its own.
- The tracks play from a DirectSound buffer of the hook's own rather
  than through MCI's `waveaudio`, because of the slider. `mciwave`
  exposes no handle, and winmm's volume - `waveOutSetVolume` by device
  id, and by handle too - has been the application's audio-session
  volume on Windows since Vista: it moved the DirectSound effects with
  the music, and muted them every time the game sent 0, which it does
  between the loading screen and the start signal, and in Time Trial
  until the start. Wine treats the same calls as the wave device's, which
  is why it played correctly there. A buffer's volume is its own on both,
  and in the mix's units.
- The DLL is relocated on every load (`SR2_MSG.DLL` holds its preferred
  base). Each rewritten site carried a `.reloc` entry for its absolute
  slot address at `site+2`; `apply_music` drops those, or the loader
  would add the relocation delta into the new relative displacement.
  `tools/musictest.py` relocates the image before running it for that
  reason.

At "Go!" the exe seeks the course track to 0:00 with a track number one
below the one its play used, and sends no play after it; the hook takes
a seek to the open track or the one below it as a restart.

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

The MediaKite cabinet holds the same twenty-five groups with the same
counts bar two: *Program Executable Files* has 37 files and 11.6 MB, with
no `VendorLogo.dll`, and *BINDATA 2* 469 files and 72.0 MB.

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
The MediaKite play disc carries the same thirteen tracks, 2-14, under
the same `SEGARALLY2` label, and `tools/loudness.py` puts its rip within a dB
of the figure `asm/mix.inc` holds, so the mix's offsets stand for it; the
tracks have not been compared with the other three sample by sample.

## What is not done

- `E_FAIL` at start, through `0x4404b0` from the `jl` at `0x427e05` -
  the return of the bring-up at `0x427fe0`, which is `0x421330(hwnd,
  640, 480, fullscreen)` whatever the saved size, since `0x4214f0`
  writes its own arguments over `WIDTH`/`HEIGHT`. Seen once on Linux
  with borderless, where under WinDbg every return in `0x421330` -
  MGameD3D Init, MGameGL Init, its `+0x18`, `0x421670` - was 0; and on
  Windows on an NVIDIA machine with the MediaKite build, where it was
  deterministic: one good start, then the box on every run afterwards,
  with the game's folder byte for byte as it was before the good one.
  A build with only `nodisc` and `nocardwarn` applied fails identically,
  so the patches are not in it. Windows' 8/16-bit DWM mitigation
  (`__COMPAT_LAYER=DWM8And16BitMitigation`) cleared it there, three
  starts for three, and without it the very next start failed again.
  What makes a machine need the shim, and what the one good start had
  that the rest did not, is still open; the game prints nothing about
  it (`OutputDebugString` on that machine carries only the missing
  `VendorLogo.dll` and MGInput's own device failures, which are there
  on a good start too).
- What `LAUNCH.EXE` and `MUSASHI\SR2.dll` offer, and `SR2_SAVE.DAT`'s
  layout beyond the records table.
- Widescreen: an aspect-ratio row on the page to filter the list; the
  value text's exact place and whether every 2D element scales are to
  be checked on the running game; the `.bg` path with brightness or
  contrast set (`0x46c900`).
- Pacing by the display on Wine: the game free-runs at 60.000 Hz there.
