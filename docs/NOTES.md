# Notes

This document describes what each patch changes. It does not describe
how to use the patcher; that is in [README.md](../README.md). The game
as it shipped - the executable and its builds, Musashi, startup and
files, and the two discs - is in [GAME.md](GAME.md). Addresses and file
offsets are in [MAP.md](MAP.md). The widescreen patch, which is the
largest, has [WIDESCREEN.md](WIDESCREEN.md) to itself, and the gamepad
patches have [GAMEPAD.md](GAMEPAD.md). The assembly sources are in
[asm/](../asm/).

Everything below was read off the retail European release (files stamped
20-21 Oct 1999, VC6 linker 6.0) with pefile, capstone and unshield, and
checked on the game running under Wine and Proton. The American and
Australian releases map onto the European one; GAME.md, *Builds*, says
how far.

## Patches

*The annex* is the one `.sr2` section the patcher appends to a file. Each
patch that puts code or data in the file grows it. The offsets in the
tables are the European build's file offsets; the other builds' offsets
are in `BUILDS` and in GAME.md, *Builds*. Bold names are the ones the README
lists. The key in parentheses is what `--patch` takes.

**Starting and crashes**

| Patch | File | Offsets | Change |
| --- | --- | --- | --- |
| **Windows 9x check** (`win9x`, Australian only) | `SEGA RALLY 2.exe` | `0x4b3b0` | the check at `0x44bfb0` returns 0 at once: its `sub esp,0x94` becomes `xor eax,eax; ret` |
| **No disc required** (`nodisc`) | `SEGA RALLY 2.exe` | `0x267c0`, `0x7572e` | the startup check returns 0, meaning "found": its `mov eax,[esp+4]` becomes `xor eax,eax; ret`. The loader constructor's drive scan becomes `lstrcpyA(disc root, exe dir)` and a jump to the constructor's epilogue |
| **No card warning** (`nocardwarn`) | `SEGA RALLY 2.exe` | `0x26678` (`0x26938` American, `0x4b263` Australian) | the `push 5` before the warning's string load becomes a `jmp` to the tail that returns 0 |
| **Replay freed once** (`replayfree`) | `ReplayGallery.dll` | `0x2f65`, `0x3b1f`, the annex | the gallery's `new` becomes a thunk that remembers the block it returned; the gallery's `push eax; call free` becomes a thunk that frees only that block |
| **Texture release checked** (`texrange`) | `MUSASHI\MGameD3D.dll` | `0x4430`, the annex | the release's first ten bytes become a `jmp` into asm/texrange.asm; one relocation entry is dropped |
| **Survive ALT+TAB** (`altab`, `restoreall`) | `SEGA RALLY 2.exe`, `MUSASHI\MGameD3D.dll` | exe `0x25ff7`, the annex; DLL `0x7710`–`0x778c`, ten relocation entries | in the exe, the `WM_ACTIVATEAPP` handler's `call 0x46e260` (resume the sound) becomes a call to a stub that calls MGameD3D's restore method first. In the DLL, that restore method is rewritten as `IDirectDraw4::RestoreAllSurfaces` |
| **Z-buffer detach crash** (`zdetach`) | `MUSASHI\MGameD3D.dll` | `0x2930`, `0x2b31`, `0x2d11`, `0x37f4` | each `call [ecx+0x20]` becomes `add esp,0xc`, so the `DeleteAttachedSurface(0, NULL)` on the back buffer is skipped |
| **No registry** (`noregistry`) | `SEGA RALLY 2.exe` | `0xd07c0`, `0x7e359` | the file name string `SR2.CFG` becomes `SR2.DSP`; `MGameReg`'s Open at `0x47ef59` (21 bytes) becomes `xor esi,esi` |

**Picture and window**

| Patch | File | Offsets | Change |
| --- | --- | --- | --- |
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
| **Widescreen** (`widescreen`) | `SEGA RALLY 2.exe` | `0x20dfe`, `0x20e18`, `0x5128a`, `0x4e5`, the annex | four sites become `call`s into asm/wide.asm: the mode setter's entry compare, the mode setter's size stores, the screen-change routine's settings load, and the element walker's callback call. The size table follows the code in the annex |
| **Widescreen, the 3D** (`widescreen3d`) | `MUSASHI\MGameGL.dll` | `0x2bc0`, `0x2c70`, `0x2de0`, `0x27f0`, `0x2e80`, `0x2ee0`, the annex | the prologues of `SetViewport`, `SetPerspective`, `SetCentre` and the parameter getter become `jmp`s into asm/widegl.asm; the first eight bytes of the projection and of its inverse become jumps to entries of their own |
| **Widescreen, the 2D** (`widescreen2d`) | `MUSASHI\MGameD3D.dll` | `0x5120`, `0x50d0`, `0x4fe0`, `0x5170`, `0x5030`, `0x5080`, `0x6040`, `0x4d50`, `0x411c`, the annex | the first bytes of the six 2D draws, the device viewport setter, the present and the texture create become `jmp`s into asm/wide2d.asm; seven relocation entries are dropped |
| **Resolution list** (`resolution`) | `Options.dll` | `0x2815`, `0x2826`, `0x2528`, `0x2b01`, `0x2a5b`, six bytes, the annex | five sites on the Graphic Settings page go into asm/resolution.asm: the row load, the count check, the draw loop head, the row store and DEFAULT's row store. The page's six "7"s become "8". Three relocation entries are dropped |
| **HUD after the water** (`hudlast`) | `SEGA RALLY 2.exe` | `0x17eb1`, `0x274f2`, `0x25d30` (11 bytes) (`0x18161`, `0x277b2`, `0x25fe0` American; `0x2de01`, `0x4c119`, `0x4a940` Australian), the annex | the race state's HUD call, the frame's root-tree draw and the fade node's draw thunk become branches into asm/hudlast.asm |
| **Loading screens** (`loadhold`) | `SEGA RALLY 2.exe` | `0x19bbb`, `0x189be` (6 bytes each), the annex | the store of the new loading picture when it is created (`0x41a7bb`) and the load of it at the step that deletes it (`0x4195be`) become `call`s into asm/loadhold.asm |
| **The clear's height** (`clearsize`, Australian only) | `SEGA RALLY 2.exe` | `0x40b83` (12 bytes), the annex | the mode setter's `mov eax, [WIDTH]` and its two pushes become a `call` to a thunk that pushes `[HEIGHT]` and `[WIDTH]` and jumps into the clear |

**Sound**

| Patch | File | Offsets | Change |
| --- | --- | --- | --- |
| **No mixer needed** (`mixerless`, Australian only) | `MUSASHI\MGAudio.dll` | `0x2278`, the annex | Init's `jne fail` becomes a jump to a stub that zeroes the control count at `+0x84` and eax, then jumps back to the allocation |
| **The mix** (`mix`) | `MUSASHI\MGSound.dll` | `0x439f`, `0x6980`, the annex | the buffer's `SetRange` loads its min and max through asm/mix.asm's first routine; the streaming buffer's `SetVolume` finishes its mapping through the second routine |
| **Effects at full** (`sfxlevel`, `sfxoptions`, Australian only) | `SEGA RALLY 2.exe`, `Options.dll` | exe `0xb26cb`, `0xb272e`, `0xb2782`; DLL `0xf92a`, `0xf98d`, `0xf9e1` | the setting's load becomes `mov eax, 9`; in the DLL the load's relocation entry is dropped with it |
| **Music from files** (`music`) | `MUSASHI\MGAudio.dll` | the annex, 12 sites, the entry point, the CD-volume methods `0x1db0` and `0x1e40` (`0x1d90`, `0x1e20` Australian) | every `call [__imp__mciSendCommandA]` becomes `call hook; nop`; the `mov esi, [__imp__mciSendCommandA]` at `0x10003108` becomes `call hookaddr; nop`; the entry point is repointed at the setup thunk; the CD-volume methods' entries become `jmp setvolume` and `jmp getvolume` |
| **Quieter defaults** (`voldefault`) | `SEGA RALLY 2.exe` | `0xd01a8` (`0xd05a8` American, `0x1159a8` Australian), 12 bytes | the defaults block's three sliders go from 9 to 6 |
| **CD level marked** (`cdlevel`) | `SEGA RALLY 2.exe` | `0x73048` (`0x73478` American, `0xb2668` Australian) | the menu's CD-level set at `0x473c48` pushes flags `0x40` instead of 0 |

**Controls**

| Patch | File | Offsets | Change |
| --- | --- | --- | --- |
| **Device Settings** (`devices`) | `Options.dll`, `BINDATA\MISC\OPTIONS.TXR` | DLL `0x33f8`, `0x340f`, `0x3214`, `0x3267`, `0x2f0c`, `0x3638`, the dispatch entry at `0x31c0` + 12 (Australian `0x5b68`, `0x5b7f`, `0x5984`, `0x59d7`, `0x567c`, `0x5da8`, `0x5930`), nine `x` fields and two UV entries in `.data`, the annex; the TXR grows a thirteenth sheet | the cursor's and the icon set's item counts go from 3 to 4; the item tables and the state table move to the annex, with a fourth item and two more states; the dispatch table's fourth slot becomes a stub that selects the page's state |
| **XInput** (`xinput`) | `MUSASHI\MGInput.dll` | `0x8130`, `0x8210`, `0x7100`, `0x56c0` (Australian `0x7940`, `0x7a20`, `0x6940`, `0x81a8`), the annex | the registry helper's load and save, the config's update and the device's poll become `jmp`s into asm/padinput.asm. The Australian build has no device poll, so there the keyboard-poll address is pointed at the annex instead |
| **DirectInput 8** (`dinput8`) | `MUSASHI\MGInput.dll` | `0x2940` (18 bytes), `0x39ac` (7), the ids at `0x10680`, `0x106c0` (Australian `0x2870`, `0x39f9` (6), `0x10678`, `0x106b8`), the annex | the `DirectInputCreateA` call becomes a `jmp` into asm/dinput8.asm; the first read of the device's type byte becomes a `call` to the stub's translation entry; `IID_IDirectInput8A` and `IID_IDirectInputDevice8A` are written over the DirectInput 2 ids |
| **Devices of no kind** (`nogeneric`) | `MUSASHI\MGInput.dll` | `0x26d2` (5 bytes; Australian `0x2694`), the annex | the device loop's null-GUID branch and the two instructions after it become a `jmp` into asm/nogeneric.asm. Needs `dinput8` |
| **Gallery sort on LB/RB** (`sortpad`) | `ReplayGallery.dll` | `0x1b64` (9 bytes), `0x1c6a` (6 bytes), the annex | the list's `mov ecx, [esi+0x50]; and edi, 0xff` after its row update (`0x10002764`) becomes a `call` into asm/sortpad.asm. The stub steps the sort mode on a press of the annex's LB or RB. `push 0; mov edi, eax; mov edx, [ecx]` in the empty gallery's state (`0x1000286a`) calls its second entry, which does the same |
| **Pad prompts on the Records pages** (`padprompts`) | `Record.dll`, `BINDATA\MISC\Record.txr` | the export table's entry for `_RecordModeExec@4`, the annex; sheet 13 | the export's entry (`0x3e00`) becomes asm/padprompts.asm's RVA. Each frame the stub writes the v0 and v1 of the five pages' two label entries, as PAGE UP KEY and PAGE DOWN KEY or, while a pad is the device last used, as LB BUTTON and RB BUTTON, then jumps to the export's own routine. The patcher writes that lettering over the sheet's unused L LEVER and R LEVER. It also moves the hint bar's two quads apart to meet at 0 (`0xc40e0`, `0xc4114`, 16 bytes each): stock they overlap by two pixels and cut the `a` in `change` |
| **Pad prompt on the title** (`padtitle`) | `Title.dll`, `BINDATA\MISC\TITLE.TXR` | the export table's entry for `_TitleExec@4`, the annex; sheet 5 | the same stub over the export (`0x12c0`). It writes the prompt's sprite size, its two quads and their two UV boxes, as PRESS ENTER KEY or as PRESS START BUTTON, which the patcher writes on the sheet's free rows 77 to 141 |
| **Pad prompt on the attract screen** (`padattract`) | `AdvTelop.dll`, `BINDATA\MISC\ADV_TXT.TXR` | the export table's entry for `_AdvTelopExec@4`, 20 bytes at `0x93e8c`, 6 bytes at `0x112d`, the annex; sheet 3 | the same stub over the export (`0x11c0`). It writes the prompt's sprite size and its quad's rectangle and UV entry index, 18 or 111. Entry 111, spare in the stock file, becomes the box of PRESS START BUTTON, which the patcher writes on sheet 3's free rows 176 to 194. Init's release of sheet 3 for the telop types that do not draw it becomes `nop`s, so the sheet is there for the prompt |
| **Pad prompts in the Replay Gallery** (`padgallery`) | `ReplayGallery.dll`, the four `BINDATA\MISC\RG_*.txr` | the export table's entry for `_GalleryModeExec@4`, 6 UV entries, the annex; a tenth sheet | the same stub over the export (`0x4660`). It switches the foot's bar and the popups' two lines to the pad's (B button), and the sort box's SORT, MODE, CAR and DATE plates to ones that name LB and RB. The pad's strips and plates are on a sheet appended to each RG file; the bars' quads go to spare entries filled in as the strips' boxes, and the 42 plate entries are switched in place, box and texture handle |
| **Pad prompts in Options** (`padoptions`) | `Options.dll`, `BINDATA\MISC\OPTIONS.TXR` | the export table's entry for `_OptionsModeExec@4`, 8 UV entries, the annex; a fourteenth sheet | the same stub over the export (`0x39c0`; Australian `0x6130`). It switches the frame's Cursor keys bar on every page, and the Device Settings page's two hint lines, to the pad's. Needs `devices` |
| **Bumpers as Page Up/Down** (`pagepad`) | `SEGA RALLY 2.exe` | `0x7e906` (6 bytes) (`0x7ed26` American, `0xbdef8` Australian), the annex | the load and test after the input wrapper's action table loop (`0x47f506`) become a `call` into asm/pagepad.asm. The stub ORs the annex's LB, RB and X into the player's level word as 0x80, 0x100 and 0x08, then does the load and test itself |
| **Backspace erases** (`erasekey`) | `SEGA RALLY 2.exe` | `0xce89c` (4 bytes) (`0xceb7c` American, `0x1140d4` Australian) | the input wrapper's key for bit 3 (`0x4cfe9c`) goes from -1 to `0x0e`, Backspace, which the name entries take as erase |
| **Pad in a replay** (`replaypad`) | `SEGA RALLY 2.exe` | `0x400ea` (5 bytes) (`0x4047a` American, `0x6e99a` Australian), the annex | the two loads where the replay controls' keyboard and joystick paths join (`0x440cea`) become a `call` into asm/replaypad.asm. The stub ORs the annex's bumpers, left stick, triggers, Y and X into the player's level word, then does the two loads itself |
| **Pad on the multiplayer screens** (`padmenu`) | `SEGA RALLY 2.exe` | `0x3ed4f` (6 bytes), the annex | the store of the pad poll's level word (`0x43f94f`) becomes a `call` into asm/padmenu.asm. The stub puts the annex's buttons into the level word. It puts the annex's directions, Back as TAB and any press as a key into the keyboard's menu word. Then it makes the edge word and does the three stores |
| **SEL on the team room's TAB button** (`tabmenu`) | `SEGA RALLY 2.exe`, `BINDATA\chat\TAB_MENU_SEL.BMP`, `TAB_MENU_SEL2.BMP`, `TAB_MENU_BACK.BMP` and `TAB_MENU_BACK_SEL.BMP` | `0x35002`, `0x35629`, `0x37053` (6 bytes), `0x36eac`, `0x3ed13` (5 each), the annex; the four files, new | five `call`s into asm/tabmenu.asm. The room constructor's call that loads the backdrop (`0x435c02`) goes through the stub, which makes that call and then loads the two backdrop files; the room destructor's release loop (`0x436229`) frees them. After the menu layer's first draw has loaded its thirty bitmaps and called the TAB pair's `+0x34` (`0x437c53`), the stub loads the two button files beside them; the menu's release loop (`0x437aac`) puts the stock's back and frees them. In the multiplayer pad poll (`0x43f913`), every frame, it writes the array's two TAB entries as the pad's objects while a pad is the device last used, else the stock's, and when that changes blits the backdrop's TAB MENU box (`CHAT.BMP` at (18, 454), 98 by 18) as SEL or as stock through the surfaces' `SetTarget` (`+0x34`) and `Blit` (`+0x1c`). The button files are the stock pair with SEL over TAB, from a mask `tools/prompts.py` renders; the backdrop files are that box of `CHAT.BMP` as it is and with SEL over TAB |

**Online**

| Patch | File | Offsets | Change |
| --- | --- | --- | --- |
| **Connection rows** (`lobby`) | `SEGA RALLY 2.exe`, `BINDATA\connect\PROTOCOL\` | `0x3b158`, `0x3b176` (50 bytes), `0x3b1a8`, `0x3b1cc`, `0x3b1dd`, `0x3b357`, `0x3b377`, `0x3b385`, `0x3b3c2`, `0x3f4dd`, `0x3e3e0`; `CONNECT.BMP`, nine button files, three `showteam_*` files and `Ip_entry_US.bmp` | the connection screen's four rows IPX / TCP-IP / MODEM / SERIAL become three, INTERNET / DIRECT IP / LAN, centred. In the exe: the drawer's row y's change, its fourth blit is skipped, the cursor wraps in 0..2, the confirm never picks the modem screen, the latency is read for every type, SHOW TEAMS on row 2 searches at once, and SHOW TEAMS is relettered SEARCH. The IP entry's OK goes through asm/ipcheck.asm (`0x3bf4e`, the annex). The entries are capped by field and CTRL+V is bounded through asm/entrycap.asm (`0x20310`, `0x1f2f1`, `0x1fc49`, `0x1f7ba`, `0x200d5`, the annex). The team room's status line comes from the DLL through asm/status.asm (`0x3544b`, the annex). The chat line's block is 64 bytes larger (`0x344e4`). The popup's lower lines are redrawn. The labels are rendered by `tools/labels.py` and carried as masks. See *The connection screen* |
| **Starting box** (`starting`) | `SEGA RALLY 2.exe` | `0x367c8`, `0x359bf`, `0x27c35` (7 bytes), `0x63a0` (8 bytes), the annex | the two calls into the race setup (`0x438dc0`) go into asm/starting.asm. The stub draws a box saying the race is starting on the team room's background, blits it onto the room's last frame, presents, then runs the setup. The frame gate's present call goes through the stub's second entry, which keeps the box up. The lobby's surface loader goes through the stub's third entry, which takes the box down. Needs `lobby`. See *The starting box* |
| **Network DLL** (`netplay`) | `MUSASHI\MGNetWk.dll`, `SR2.CFG` | the whole file | the DLL is replaced by the build of `net/`: the stock DLL's CLSID and three vtables, over plain UDP. It offers a LAN search, an address typed in, and the internet through a directory server. It reads `SR2.CFG`'s `[Network]` section (Staging, Log, both 0), and writes the section when the file has none. See [NETWORK.md](NETWORK.md) and [net/README.md](../net/README.md) |

The exe is never relocated. Inside its `.text`, VA = offset − 0x400 +
0x401000 (− 0x600 in the American build). In the Musashi DLLs the raw
and virtual layouts coincide, so VA = offset + 0x10000000 at the
preferred base. In `MGameGL.dll`, `Title.dll`, `Options.dll` and
`ReplayGallery.dll`, `.text` starts at raw 0x400 for RVA 0x1000, so VA =
offset + 0x10000c00. The DLLs are relocated at load. That is why every
patch that lands in a DLL is position-independent and drops the
relocation entries of the bytes it replaces.

The sections below take the patches group by group, in the tables'
order. Rows that are a single obvious byte edit are skipped. The
widescreen patches have [WIDESCREEN.md](WIDESCREEN.md) to themselves, and
the gamepad patches and the Device Settings page have
[GAMEPAD.md](GAMEPAD.md). Most patches install assembled machine code
rather than editing bytes; the sources, and a longer account of each, are
in [asm/](../asm/).

## Starting and crashes

### No disc required

The patch has two sites, one for each place the game looks for the disc:
the startup check and the loader's own scan. GAME.md, *The disc flag*, has
the account.

### No registry

The game has one file name string `SR2.CFG`, used for the read at
`0x427740` and the write at `0x427880`. It becomes `SR2.DSP`, so the
game's 100-byte display block (GAME.md, *The install contract*) keeps a file of
its own in the stock shape, and `SR2.CFG` is the controls text from byte
0. `carry_display_block` copies a stock `SR2.CFG`'s block into `SR2.DSP`
at patch time, once. `write_settings` then writes `SR2.CFG` with the
sections the applied patches read: the controls for `xinput`, `[Display]`
for `resolution` and `[Network]` for `netplay`, laid out as the pad annex
expects them. It writes the whole file when there is none, or when the
file holds only the block; otherwise it appends a missing section to the
text. `MGameReg`'s Open at `0x47ef59` (21 bytes) becomes `xor esi,esi`,
so `Software\SEGA` is never created. GAME.md, *The registry*, and
GAMEPAD.md have the rest.

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

## Picture and window

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

#### The mode check

Before it sets the cooperative level, windowed or
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

#### The size of the target

`IDirect3D3::CreateDevice` (`0x10003080`, on
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

#### dgVoodoo 2

dgVoodoo 2 runs the game once its `ddraw.dll` is in
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

#### The depth check

The windowed path calls `GetDisplayMode` and refuses
a desktop whose depth is not the 16 bits it was asked for (`0x1000271e`;
the `E_FAIL` becomes "Failed to initialize"). Nothing after the check
depends on the depth, because every surface takes the primary's format.
`anydepth` skips the check.

#### The `.bg` pictures

The full-screen pictures (title, loading, game
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

#### The window

The `MoveWindow` call goes to a thunk that moves the
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

#### The present

From `0x10004d7b` on, the present is replaced by one
that fits the back buffer's aspect into the client rect, fills the bars
with `DDBLT_COLORFILL` and blits the picture into the middle. The picture
is still 640x480, point-sampled up, until a wide size is chosen. The 96
bytes of the old present carry nine relocation entries, and the call
carries one. All ten go, because the bytes are either dead or relative.

#### Another monitor

The game creates DirectDraw on the default device
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
per frame, which is fine for 640x480 into 1440p. It works with dgVoodoo
as well.

After its blit the present stores the counter value in the annex, for
`frametrace`. The annex is writable for that store.

### Frame log

`frametrace` is a diagnostic applied by name. It hooks the gate's entry
(`0x4287f0`, `mov eax,[0x4d6a3c]`) and its exit (`0x42890b`, the five
bytes before `pop ebx; ret`) and logs every drawn frame to
`logs\frames.log` beside the exe. Each line holds the counter at the
entry, the counter after the borderless present's blit (found through
the borderless patch's jump at MGameD3D's present), the counter at the
exit, the step count and the gate's four flags (GAME.md, *Frame timing*). A header
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

`windowed` and `borderless` are the game's mode. The patcher's window
always applies them; `--patch DIR -borderless` leaves the stock window
(640x480, the present a plain stretch), and `-windowed` the stock
exclusive mode, with `borderless` and `altenter` out as well. The
exclusive mode is for tests: the other patches apply there, and none has
been played in it. `noregistry` is in every set and `--patch` refuses to
leave it out: without it the game writes its display block over
`SR2.CFG`, the other patches' settings with it.

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

## Sound

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

GAME.md, *Music*, says what the DLL does with the CD. Three properties of
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

## Controls

### Device Settings

This patch adds a fourth item to the Options menu and the page behind
it. GAMEPAD.md, *The Options screen*, describes it.

## Online

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

#### The three rows

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
`BINDATA\connect\button` (105x19, 24-bit, a 102x16 face and a bevel)
are rewritten with the face cleared and SEARCH laid over it from a mask
`tools/prompts.py` renders in Noto Sans Mono, the open face closest to
the buttons' own (`lobby_buttons`; GAMEPAD.md, *The pad's prompts*). The stock
files are checked by digest first and kept as `.bak`.
`tools/buttonstest.py` pins the result. `MPDATA.DAT` keeps the type from
last time; a stock 3 there is reset to 0 at patch time.

#### The IP entry

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

#### The text fields

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

#### The team room's address line

On DIRECT IP only, the team room's init prints `IP Address :` and up to
three addresses from `gethostbyname` (`0x43604b`-`0x43611c`, `TextOutA`
at (150, 456)). asm/status.asm is called in place of the `lea` that
starts that lookup. It asks the DLL's network object for the line (slot
`+0x38`, `Network_StatusLine`, NETWORK.md) into the same buffer and
continues at the draw. When there is no object or no line, it redoes the
`lea` and lets the exe print its own line.

#### Chat lines

A chat line is kept for the team room's list as `name>text` (`0x4350e0`,
on sending and on receipt). It is `wsprintf`ed into a block of
`(len + 0x13) & ~3` bytes, which is room for the text and a name of ten
characters. A longer name ran the line over the next heap block, and the
game died in the heap's checks a few lines later. `0x344e4` adds 64 to
the allocation, which is the DLL's name length.

#### The lettering

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
