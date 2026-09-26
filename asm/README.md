# asm

Source for the machine code the patches install. `sr2-patcher.py`
carries the finished bytes between GENERATED markers, so running the
patcher needs no nasm; only editing this directory does.

```
vim asm/music.asm
python3 asm/build.py             # assemble and write the hex into sr2-patcher.py
python3 asm/build.py --check     # what CI runs: assembly and hex still match
```

Never edit the hex by hand; the next build overwrites it.

The blobs must assemble to the same bytes on every machine, since
`tools/selftest.py` pins the patched files' digests: where nasm releases
encode an instruction two ways - a scaled index with no base, a `rep` on
a word-sized string instruction - the source spells it out.

Two rules every blob follows:

- No source or include names an exe address (`build.py` refuses one);
  everything a stub reads comes through a placeholder from the tables in
  `build.py`, filled by the patcher from the build's row. The exe is
  never relocated, so those are absolute. An offset the patcher needs
  inside a blob - `mix.asm`'s second entry, the borderless present's
  stamp, the resolution table's groups - is a label named in `build.py`'s
  `LABELS`, read off nasm's listing and written out as `BLOB_LABELS`;
  nothing of the kind is kept by hand.
- A DLL stub is position-independent: the DLLs are relocated on every
  load, so the blob takes its own address with a `call`/`pop` and
  reaches the DLL's globals and import slots relative to that, and the
  patcher drops the relocation entries of the bytes it replaces.

## The files

| File | In | What it holds |
| --- | --- | --- |
| `music.asm` | `MGAudio.dll` | CD audio from files: the DllMain thunk that builds the track table, the `mciSendCommandA` hook, the worker that plays a track from a DirectSound buffer, the volume |
| `activate.asm` | exe | calls the renderer's restore when the game regains focus |
| `restore.asm` | `MGameD3D.dll` | that restore, redone as `RestoreAllSurfaces` so the textures come back too |
| `textcolor.asm` | exe | `SetTextColor` with the colour masked to RGB, for the lobby's `-1` |
| `bgrow.asm` | exe, `Title.dll` | a .bg picture into the back buffer at either depth, or composed with its side areas for one blit to stretch; built twice |
| `fullwin.asm` | `MGameD3D.dll` | the windowed mode filling the monitor: window sizing and a letterboxed present |
| `altenter.asm` | exe | ALT+ENTER between the borderless window and a framed one |
| `starting.asm` | exe | a box on the team room while the race setup gathers the players |
| `ipcheck.asm` | exe | the IP entry popup's OK refused for a blank or malformed address |
| `entrycap.asm` | exe | the lobby's text entries capped at what their fields hold, CTRL+V included |
| `status.asm` | exe | the team room's status line asked of the netplay DLL: local and public address |
| `hudlast.asm` | exe | the race HUD drawn after the frame's root tree, so the tachometer's plate blends over the lake; before the tree's fade quad, so the fade stays over it |
| `loadhold.asm` | exe | the stage loading screens held three seconds |
| `padmenu.asm` | exe | the pad on the multiplayer screens straight from MGInput's annex; Back is TAB, which is how the team room's MENU row opens |
| `sortpad.asm` | `ReplayGallery.dll` | the pad's LB and RB step the gallery's sort, which the exe's F6-F8 accelerators set |
| `pagepad.asm` | exe | the pad's LB and RB from MGInput's annex as Page Up and Page Down in the wrapper's level word: the Records pages, the car select's alternative colour |
| `replaypad.asm` | exe | the pad on the replay's camera controls from MGInput's annex, ORed into the level word the keyboard fills |
| `texrange.asm` | `MGameD3D.dll` | the texture release with its index checked against the count |
| `replayfree.asm` | `ReplayGallery.dll` | the gallery's `new` remembered, its End freeing that block and no other |
| `wide.asm` | exe | the picture's size from `SR2.CFG`, and the HUD frame flag; built twice, the American build's size setter has a third size |
| `widegl.asm` | `MGameGL.dll` | the viewports, centres, field of view and projections kept in 640x480 terms at the six methods every caller goes through |
| `wide2d.asm` | `MGameD3D.dll` | the 2D scaled to the back buffer through six draws, the side bars, the lobby's blits, the device viewport |
| `resolution.asm` | `Options.dll` | the Graphic Settings page's RESOLUTION row as a list over the patcher's table, and an ASPECT RATIO row |
| `devices.asm` | `Options.dll` | the Device Settings page's two states, init and exec, over the sprites, draw list and data the patcher builds after it |
| `padinput.asm` | `MGInput.dll` | XInput answering the pad source ids at the device's poll, the pad refreshed in the config's update, the load and save on the `SR2.CFG` text |
| `dinput8.asm` | `MGInput.dll` | the DirectInput object made through `dinput8.dll`, and DirectInput 8's device type codes written as DirectInput 5's |
| `nogeneric.asm` | `MGInput.dll` | the device loop skipping a DirectInput 8 device of no kind (type 0x11) |
| `mix.asm` | `MGSound.dll` | every buffer's dB range remapped to −43..−8 in `SetRange`, and the streamed music on that curve plus `STREAM_DB` |
| `mix.inc` | - | the mix's numbers: the effects' range, the two music offsets; `mix.asm` and `music.asm` include it |
| `padpoll.inc` | - | one pad input through MGInput's annex's page poll, and the past-half test; `padmenu.asm`, `replaypad.asm`, `pagepad.asm` and `sortpad.asm` include it |
| `frametrace.asm` | exe | a diagnostic: every drawn frame's counter and step count appended to `logs\\frames.log` |
| `voltrace.asm` | exe | a diagnostic: five volume entry points report their arguments through `OutputDebugStringA` |
| `d3dinit.asm` | `MGameD3D.dll` | a diagnostic: every step of the bring-up with its HRESULT appended to `logs\\d3dinit.log` |
| `build.py` | - | assembles the above and splices them into the patcher; `MUSIC_MAGICS` lists the placeholders the patcher fills in the music blob, `EXE_MAGICS` the addresses it fills in the exe stubs from the build's row |

The `mixerless` stub is three instructions, written by `apply_mixerless`
in the patcher rather than assembled here. Each file's placeholders are
named after it: `DEVICES_MAGICS`, `PADINPUT_MAGICS`, `DINPUT8_MAGICS`,
`NOGENERIC_MAGICS`, `RESOLUTION_MAGICS`, `SORTPAD_MAGICS`; voltrace's and
frametrace's return slots (`0xE7E7E7E1` on) are `SITE_MAGICS`, counted
per blob.

The trace formats the diagnostics and the widescreen blobs print are in
[docs/DEVELOPING.md](../docs/DEVELOPING.md), *Diagnostics*.

## music.asm

The game's music is Redbook audio on the play disc, played over MCI by
`MUSASHI\MGAudio.dll` - *open cdaudio*, *play from track 5*, *status
position*. No disc means nothing to play, so the game runs silent.

This impersonates the CD drive from inside `MGAudio.dll` and plays WAV
files instead. The patcher places it in the annex, rewrites the DLL's
eleven `call [__imp__mciSendCommandA]` into direct calls to the hook,
rewrites the one `mov esi, [__imp__mciSendCommandA]` - the open routine
loads the import once and calls `esi` for the open and the set - into a
call to a thunk that returns the hook's address in `esi`, and points the
entry point at the setup thunk. No reference to the import slot is left
in the DLL's code.

### Position-independent

The DLL prefers `0x10000000` but `SR2_MSG.DLL` already holds that, so it
is relocated on every load. The blob finds its own base with a
`call`/`pop` and reaches everything as `[ebx + offset]`. The five
`MAGIC_` placeholders are offsets from the blob to the DLL's import slots
and old entry point, constant wherever the DLL lands, filled by
`apply_music`. Nothing in the blob needs a relocation entry - and the
eleven call sites, which had one each for their absolute slot address,
lose theirs, or the loader would corrupt the new relative displacement.

### Setup

Runs at `DllMain` on `DLL_PROCESS_ATTACH`, once. It resolves
`DirectSoundCreate`, `GetDesktopWindow` and the eleven `kernel32`
functions in `S_MODULES` through the DLL's own
`LoadLibraryA`/`GetProcAddress` imports, takes the game folder from
`GetModuleFileNameA(NULL)`, and walks `music\track02.wav` to
`track99.wav`. It never reads a track: after the 44-byte header the file
size is the length in 2352-byte frames. Then it chains to the original
entry with the stack untouched. No tracks found leaves the count at
zero, and the hook forwards everything.

### The hook

Watches for an open of device type `MCI_DEVTYPE_CD_AUDIO` (MGAudio opens
by type ID, not by name) and answers with device ID `0xFACE`. Calls
carrying that ID are its own; everything else, and every call while the
table is empty, goes through the import slot untouched.

What MGAudio sends, and the answer:

| Command | Answer |
| --- | --- |
| `MCI_SET` time format | ok; TMSF is assumed |
| `MCI_PLAY` `MCI_FROM` TMSF | `OP_OPEN` track N, `OP_PLAY` from ms; `MCIERR_OUTOFRANGE` for a track with no file |
| `MCI_SEEK` `MCI_TO` TMSF | `OP_PLAY` from ms if that track is open - or the one below it, since the exe seeks with the track its play adds one to, and no play follows - else remembered for the next play |
| `MCI_PAUSE`, `MCI_RESUME`, `MCI_STOP`, `MCI_CLOSE` | the operation of that name |
| `MCI_STATUS` number of tracks | the highest track with a file |
| `MCI_STATUS` length of track N | from the file size, as MSF |
| `MCI_STATUS` position | `OP_POS`, converted to TMSF on the current track |

### The worker

MGAudio issues its commands from short-lived threads of its own and
terminates them, so no device call is made on one. Startup creates two
auto-reset events, a mutex and a worker thread; `request` takes the
mutex, writes the operation and its argument, signals the request event,
waits on the done event and releases the mutex, and the worker does it
and answers. The mutex is there because the exe fades on one thread
while another changes screen, and two requests at once left one unrun;
a mutex and not a critical section since a terminated holder's mutex is
handed on.

The operations, on the worker:

| Operation | Does |
| --- | --- |
| first open | makes the `IDirectSound` (`DirectSoundCreate`, cooperative level normal on the desktop window) that lives for the process |
| `OP_OPEN` | releases what is open, opens `music\trackNN.wav`, creates a secondary buffer of its sample size - `CTRLVOLUME`, `GLOBALFOCUS` so no window of the game's matters, `GETCURRENTPOSITION2`, software - reads the samples straight into it between `Lock` and `Unlock`, closes the file and sets the volume |
| `OP_PLAY` | `SetCurrentPosition` to the byte the ms names and `Play`, no loop |
| `OP_STOP` | `Stop` and the cursor back to 0 |
| `OP_PAUSE`, `OP_RESUME` | `Stop` with the cursor kept; `Play` on from it |
| `OP_POS` | the play cursor, or the track's end once a play has run out, which `GetStatus` says since the buffer stops itself there |
| `OP_VOL` | the level on the open buffer; the next open sets it again |
| `OP_CLOSE` | releases the buffer |

The game's own polling drives everything; at the end the exe seeks and
plays again. `tools/musictest.py` runs the hook's session and each
operation under Unicorn, against a scripted `IDirectSound` and buffer.

### The volume

The BGM slider reaches the DLL's set-volume method through the exe's CD
wrapper (`0x46e160`), which multiplies a percentage by the level the
get-volume method gave it at startup, divided by 100; both methods fail
without a mixer. Both entries jump into the blob. `getvolume` says
10000, so every value is its percentage × 100.

`setvolume` gets four kinds of call and tells them by the flags and the
value:

| Call | From | Value | Flags |
| --- | --- | --- | --- |
| the menu's level | `0x473c5c` | the slider's step × 11.11 percent | `0x40`, by the `cdlevel` patch |
| the race's level | `0x473f11` | step × 9 | `0x80000000` |
| the mute when a race starts | `0x474210` | 0 | `0x80000000` |
| the fade before a stop | `0x4741bc` | 100 down to 10 a frame | 0 |

A level is the step in hundredths of a dB straight from `mix.inc` -
`MIX_BOTTOM + step × MIX_STEP + CD_DB`, −5 dB at 9, `DSBVOLUME_MIN` at 0
- the units the mix keeps every other level in, and is remembered; the
mute is off without forgetting it.

The fade was written for a mixer line that took amplitude, from full
whatever the slider said - on the curve that would open up to 33 dB
above the level - so it is an amplitude percentage of the level: the
level plus `20 log10(v / 10000)`, from `S_PCTDB`. `cdlevel` is required
for that: the menu's level is told from the fade by nothing but the
flag. A fade counts from its start, 100, and ends at any level or mute;
a step arriving outside one is dropped, since a screen change can cut
across a fade and its last steps then landed on the new track. The
original DLL read only bit 31 of the flags, to wait for the previous
set's thread.

This is why the music is a DirectSound buffer and not a wave stream:
winmm's volume, by handle or by device id, is the application's session
volume on Windows since Vista, and moved the DirectSound effects with
the music.

### Trace mode

An empty `music\trace` beside the tracks makes the hook report every
command it receives to `OutputDebugStringA`, and the worker every
operation it answers; DEVELOPING.md, *Diagnostics*, has the lines.

## activate.asm

Twenty-three bytes in the exe's annex. The window procedure's
`WM_ACTIVATEAPP` case resumes the sound object on activation with a
`call 0x46e260`; that call is pointed here. The stub saves `ecx` (the
sound object, a `thiscall` argument), calls slot 16 of the MGameD3D
interface at `0x50b118` - `IsLost`/`Restore` on the primary, the back
buffer and the Z-buffer - restores `ecx`, and continues to the resume
with `push`/`ret`, so the stack is what the original call left. With no
MGameD3D object yet it skips straight to the resume. The two addresses
(the MGameD3D pointer, the resume) are filled from the build's row.
`tools/activatetest.py` runs it under Unicorn.

## restore.asm

Forty-four bytes written over MGameD3D's restore routine at
`0x10007710`, which had 124 and restored only the primary, the back
buffer and the Z-buffer - textures are DirectDraw surfaces as well and
stayed lost. The replacement calls `IDirectDraw4::RestoreAllSurfaces` on
the object at `0x1001254c` and stores the result where the original did,
with the same stdcall shape. It finds its two globals relative to
itself, so the ten relocation entries the original routine carried are
dropped by the patcher. `tools/activatetest.py` runs it relocated.

## texrange.asm

A `jmp` over the first ten bytes of MGameD3D's texture release at
`0x10004430`, into this routine in the annex. The release took
the pointer at `[table + N*4]`, released it and cleared the slot without
looking at `N`. VendorLogo's End releases texture −128, the dword 512
bytes before the table: whatever the heap left there. Zero and nothing
happens; a pointer and the game calls through it, which is the crash
after the vendor logo. The stub does what the ten bytes did once the
index is checked against the count at `0x10012590`, as the create
already does, and returns for one out of range. `tools/texrangetest.py`.

## replayfree.asm

Two thunks in a section appended to `ReplayGallery.dll`. The gallery's
End frees the replay at `+0x50` of the screen block, which is right when
the gallery loaded it from a file and wrong when it came from a race:
that pointer is MainMode's own `.data`. Windows 9x's `HeapFree` refused
the address and carried on; the heap since Windows 8 ends the process,
which is the crash on returning to the menu after saving a replay.
`alloc` stands in for the gallery's own `new` and keeps the block's
address; `free` stands in for the `push eax; call free`, leaving the
argument for the caller's `add esp, 4`, and frees `eax` only when it is
that block. `tools/replayfreetest.py`.

## textcolor.asm

Fourteen bytes in the exe's annex. The lobby's ten `SetTextColor` sites
pass `-1` for white; NT and Wine read bit 24 of that as `PALETTEINDEX`
and draw black, the colour key of the blit that follows. The stub masks
the colour argument on the stack to its RGB bytes and jumps through the
import slot, so it has the import's stdcall shape and the sites keep
theirs: the eight `call [slot]` become `call` here, the two `mov esi,
[slot]` become `mov esi` of this address. No reference to the slot is
left in the exe's code.

## bgrow.asm

In the exe's annex, replacing the twenty-byte row copy at `0x415271`
that puts the 16-bit `.bg` pictures into the locked back buffer. It
reads the lock's description at `0x4e6878`:

- with the surface the picture's size it runs the original copy, or
  expands each 565 pixel to XRGB8888 for a 32-bit surface;
- with another size it draws the whole picture on the first row -
  nearest pixel, the largest size of the picture's aspect that fits,
  centred between bars - the picture itself, motion-blurred and
  stretched, in the `Title.dll` build; each side filled with the
  picture's corner pixel in the exe's - composed at source size into
  `MGameD3D`'s surface, or drawn here when there is none - and nothing
  on the rows after.

`eax`, `ebx` and `edx` come out as they went in; the rest were scratch
at the site.

Assembled again with `-DTITLE` for `Title.dll`'s copy of the loop
(`0x100014ba`), which keeps its lock description on the stack and
advances the source itself: that build reads the description at
`[esp+0x1c]`, the height from the loop's row count, and adds the row to
`ebx`. `tools/bgrowtest.py` runs both at both depths and both sizes
under Unicorn. What the two builds put in the bars is in
[docs/WIDESCREEN.md](../docs/WIDESCREEN.md), *The .bg screens*.

## wide.asm, widegl.asm, wide2d.asm, resolution.asm

The widescreen patch, [docs/WIDESCREEN.md](../docs/WIDESCREEN.md).

**`wide.asm`** has four entries through a jump table: the mode setter's
entry compare and its size stores, the screen-change routine's size read
and the element walker's HUD frame flag, which it writes with the bounds
of the HUD's own draws beside it. The size table the patcher
appends follows the code, and the annex is writable for the `SR2.CFG`
path.

**`widegl.asm`** takes over `SetViewport`, `SetPerspective` and
`SetCentre` at their prologues, adjusts the arguments on the stack, does
the prologue itself and jumps on with the resume address in `eax`, dead
at that point of the methods. The projection and the parameter getter it takes
at their entries, calls the rest as a routine with the arguments pushed
again and converts what it wrote; the inverse projection continues into
the method with its point argument at a converted copy.

**`wide2d.asm`** finds its own base and the image's, and takes over the
six draws' first instructions, resuming after them with the vertex
argument pointing at its scaled copy. The device's viewport setter is
taken the same way, its rect argument pointed at a scaled copy - the
rect into the picture's 4:3 box, both by the height, and its fractions
taking the box's share of the screen so the countdown digit keeps its
4:3 size. Its eighth entry is the present: it closes the frame's tile
table, hooks ddraw's `Blt` for the lobby's stretch and keeps the `.bg`
surface. Its ninth sits in the texture create, marks what the texture
is for the side bars' sake and replays the thirteen bytes it took.

`widegl` and `wide2d` each carry a trace, off unless the `gltrace` or
`d3dtrace` diagnostic sets its flag; the patcher finds the flag by a
marker string in the annex. `wide2d`'s lines also go to
`logs\\d3dtrace.log`, opened on the first line as `d3dinit.asm` opens
its log.

**`resolution.asm`** follows `devices.asm`'s pattern for `Options.dll`,
its placeholders RVAs; kernel32's two profile routines come through
`LoadLibraryA`/`GetProcAddress`.

`tools/widetest.py` runs the first three, `tools/resolutiontest.py` the
fourth on the real `Options.dll`.

## fullwin.asm

Two thunks in `MGameD3D.dll`'s annex. The blob takes its own address
with a call/pop, subtracts its RVA (filled in over `MAGIC_SELFRVA` by the
patcher) for the image base, and reaches the DLL's globals and import
slots as RVAs from there.

**`present`** (+0) is jumped to from the first instruction of the
windowed present, inside the 16-byte frame that routine had made, and
leaves through that frame's `ret 4`. It takes the client rect in screen
coordinates, fits the back buffer's aspect into it, fills whichever bars
have area with `Blt(DDBLT_COLORFILL)` and blits the back buffer into the
middle, storing the result where the original did. The counter after
the blit goes to `t_blt` for frametrace.asm, `QueryPerformanceCounter`
resolved on the first present; the annex is writable for them.

**`sizewindow`** (+5) has `MoveWindow`'s stdcall shape and is called in
its place from the windowed init, which runs on every screen change. It
leaves a framed window (ALT+ENTER) alone and moves a `WS_POPUP` one to
the monitor under the cursor - `GetCursorPos`, `MonitorFromPoint`,
`GetMonitorInfoA`, resolved through the DLL's own `LoadLibraryA` and
`GetProcAddress` - or where the game asked if any step fails.

`tools/fullwintest.py` runs both under Unicorn with those calls recorded.

## altenter.asm

In the exe's annex, in front of the text-input handler the window
procedure calls for every message it has no case for (`0x426cbc` →
`0x41fe20`, cdecl). ALT+ENTER - `WM_SYSKEYDOWN`, `VK_RETURN`, ALT bit
set, repeat bit clear - toggles the window between `WS_POPUP` over its
monitor and `WS_OVERLAPPEDWINDOW` with a client area of the picture's
size, centred on that monitor, and answers 0; any other message goes on
to the handler by `push`/`ret`, the stack untouched.

The section keeps the five user32 entry points it resolves on first use,
so it is writable, and reaches its own data from a call/pop base since
its address is only known once appended. `tools/altentertest.py` runs it
under Unicorn.

## ipcheck.asm

In the exe's annex, called in place of the length compare the IP entry
popup's OK press makes (`0x43cb4e`; blank meant DirectPlay's broadcast).
The text passes as at most 47 characters - the settings' 16-byte slot
and the unused modem number's after it - of a dotted quad or a name of
letters, digits, dots and hyphens, with an optional `:port` in
1..65535; then the compare is redone and the press goes on. Otherwise
the return address is dropped, the popup's sound arguments pushed with
the cancel sound, and its own sound call (`0x43cbac`) continued into,
so the popup stays up. `tools/ipchecktest.py` runs it on the real exe
under Unicorn.

## entrycap.asm

In the exe's annex, at the lobby entry widget's init (`0x420f10`) and
in place of its character handler's two `cmp eax, 0x800`. The init
entry keeps a cap for the field the text goes back to - 47 for the
address slot, 35 for the team name, 255 for the chat line, 20 for the
driver name, which shares the chat's buffer and is known by the width
shown, 0x800 otherwise - and redoes the two loads its call displaced.
The compare entry compares against that cap and returns with the flags
for the `jae` that follows. The third entry stands in for CTRL+V's
`lstrcpyA` of the clipboard and the `lstrlenA` after it: it copies up
to the room the cap leaves, drops characters under a space, and
returns the count. The section keeps the cap, so it is writable.
`tools/ipchecktest.py` runs all three on the real exe under Unicorn.

## status.asm

In the exe's annex, in place of the `lea` that starts the team room's
own status line on DIRECT IP (`0x43604b`: `gethostbyname` and
`IP Address : %d.%d.%d.%d`). It asks the netplay DLL's network object
for the line (its added slot `+0x38`, `Network_StatusLine(buf, len)`)
into the same buffer and continues at the draw (`0x43611c`); with no
object, an error or an empty line it redoes the `lea` and returns.
`tools/ipchecktest.py` runs it under Unicorn with a fake object.

## starting.asm

In the exe's annex, in place of the two calls into the race setup
(`0x438dc0`), which spins for the other players without drawing. It
draws a box - a white border, a near-black fill, `STARTING THE RACE`
and `WAITING FOR THE OTHER PLAYERS` centred in white, as the game's own
popups - in the middle of the room's background surface with gdi32
(resolved once through the import slots: `SelectObject` the lobby's
font, `GetTextExtentPoint32A`, `SetBkMode`, `SetBkColor`,
`SetTextColor`, `ExtTextOutA` for the fills and the lines;
`CreateCompatibleDC`, `CreateCompatibleBitmap`, `BitBlt`,
`DeleteObject`, `DeleteDC` to keep the rectangle and put it back), blits
the box's rectangle alone onto the back buffer through the surface's
wrapper, calls MGameD3D's present, restores the rectangle, and jumps to
the setup, which returns to the site. Placeholders: the surface and size tables,
the font, the setup, MGameD3D's object, LoadLibraryA and GetProcAddress.
`tools/startingtest.py` runs it under Unicorn on every build.

## hudlast.asm

Three entries in the exe's annex, in place of the race state's HUD call,
the frame's root-tree draw and the fade node's draw thunk: the HUD is
held back while the tree is going to be drawn, then drawn before the
fade's quad or after the tree, with the full viewport set and the
state's reset made. [docs/NOTES.md](../docs/NOTES.md), *HUD after the
water*, has the account; `tools/hudlasttest.py` runs the three entries
under Unicorn.

## loadhold.asm

Two entries in the exe's annex, in place of the store of the new loading
picture at its create and the load of it at the step that deletes it:
the tick noted at the one, the other made to wait until three seconds
have passed. [docs/NOTES.md](../docs/NOTES.md), *Loading screens*;
`tools/loadholdtest.py`.

## padmenu.asm

One entry in the exe's annex, in place of the store of the pad poll's
level word: MGInput's annex asked for the pad's D-pad, stick, A, B,
Start and Back through the poll it publishes, the buttons put into the
level as the screens' bits, the edge made again against the stored
previous level (the exe made one before the site, from a level without
the annex's bits) and the three stores, and the directions, at the keyboard's repeat, a press of Back as TAB and any
press as a key put into the keyboard's menu word, which waits for the
task that reads it.
[docs/NOTES.md](../docs/NOTES.md), *The menus' directions*;
`tools/padmenutest.py`.

## sortpad.asm

One entry in `ReplayGallery.dll`'s annex, in place of the two
instructions after the list's row update in its browse state: MGInput's
annex asked for side 0's LB and RB through the poll it publishes, the
sort mode stepped left on a press of LB and right on RB, then the two
instructions. Finds the image base from its own RVA; keeps what was
down.
[docs/NOTES.md](../docs/NOTES.md), *Page Up and Page Down*;
`tools/sortpadtest.py`.

## pagepad.asm

One entry in the exe's annex, in place of the load and test after the
input wrapper's action table loop: MGInput's annex asked for the
player's LB and RB through the poll it publishes, ORed into the
player's level word as the keyboard's Page Up and Page Down bits, then
the load and test for the site's branch.
[docs/NOTES.md](../docs/NOTES.md), *Page Up and Page Down*;
`tools/pagepadtest.py`.

## replaypad.asm

One entry in the exe's annex, in place of the two loads at the join of
the replay controls' keyboard and joystick paths: MGInput's annex asked
for the player's bumpers, left stick, triggers, Y and X through the
poll it publishes, their bits ORed into the player's level word, the
left stick's x put into the analog when the keyboard left it at 0, then
the two loads.
[docs/NOTES.md](../docs/NOTES.md), *The replay's controls*;
`tools/replaypadtest.py`.

## padinput.asm

The XInput annex, appended to `MGInput.dll`, and the largest stub here.
An action in MGInput is a record of up to eight source ids, and each
config polls its device for a source through the device's `+0x58`
`(source, &value, &range)`. Keyboard sources are 1-0xff, joystick
0x101-0x168, mouse 0x201-0x20b; the annex answers 0x300-0x37f from
XInput, `0x300 + player * 0x40 + input`. The config's per-frame update
is hooked so a pad is read once a frame.

The menus' left and right are the steering's own actions, so the fixed
sources that keep a menu navigable whatever is bound - D-pad, stick
halves, arrows - carry a menu-only bit and are answered only while the
exe's car table has no car in slot 0, which it has from a race's setup
to its teardown.

The registry helper's load and save become the `SR2.CFG` text store: a
save whose name starts `DZ` takes the digits after it as that player's
deadzone, and source 0x3f reads it back. The European, American and
Japanese builds' device poll is hooked at the same site; the Australian
build has no such method, so its keyboard poll's address in the per-type
dispatch is pointed at the annex instead. The Device Settings page polls
the pad through an entry whose address the annex writes to an exe slot.
`tools/padinputtest.py`.

## dinput8.asm

MGInput makes its DirectInput object with `DirectInputCreateA` and takes
`IDirectInput2` from it, all through the legacy `dinput.dll`, whose
enumeration of every attached HID device is where the starts that hang
on a white window go wrong. `dinput8.dll`'s objects carry the same
vtables - `IDirectInput8` matches `IDirectInput2` slot for slot,
`IDirectInputDevice8` is `IDirectInputDevice2`'s with three methods
after - so the DLL's calls stand once the object is DirectInput 8's.
Three things differ: the create becomes `DirectInput8Create`, resolved
once through the DLL's own `LoadLibraryA` and `GetProcAddress` slots;
the patcher writes the version 8 interface ids over the version 2 ones
in `.rdata`; and `kind` writes the old device-type code over the new one
where the DLL first reads the byte, since DirectInput 8 renumbered them.
`tools/dinput8test.py`.

## nogeneric.asm

One entry reached by a jump from MGInput's device loop, five bytes after
the null-GUID compare. The DLL makes a device of every instance the
enumeration returns, and on a machine of today that list holds LED
controllers, stream decks, audio control collections and a composite
pad's spare collections - DirectInput 8 types 0x11 and 0x19-0x1c, kinds
the game can do nothing with. The stub makes the null-GUID branch, looks
at `dwDevType` at `+0x20` of the instance, skips those kinds and does
the two displaced instructions on the way out. Mice, keyboards and every
controller kind go through as before. Needs `dinput8`, whose type codes
these are. `tools/nogenerictest.py`.

## devices.asm

Two entries in the top-level state table the patcher moves into
`Options.dll`'s annex, reached with `esi` the Options object as every
case there is. `init` binds the page's UV table to the loaded sheets,
fills the value strings from the records, starts the slide-in and falls
into `exec`; `exec` draws the page's list, moves the cursor, shows the
other player, waits for a key or a pad input on an action row and binds
it - swapping with the row that had it - steps the deadzone, restores
the defaults, and slides out to the left before putting the menu's state
back.

The input objects are reached through a holder the exe fills: the exe's
input wrapper, MGInput's input object, a config's record list, and the
pad through the entry `padinput.asm` publishes. The sprites, their
quads, the draw list and the data block are built by the patcher after
this code, so the assembly holds none of the page's layout.
`tools/devicestest.py`.

## mix.asm

Two routines in `MGSound.dll`. The sound manager gives each effect a dB
range of −40..0 and sets its ceiling at `(step+1)/10` of it: 4 dB a
step. The streamed music went across a range of its own and the CD music
was linear in amplitude, so one step of a slider meant three things.
`range` is where the buffer's `SetRange` loads its min and max, each
mapped onto the range in `mix.inc` - 3.5 dB a step, 9 the old 7; `stream`
is where the streaming buffer's `SetVolume` finishes its mapping, onto
the same curve plus `STREAM_DB`. The CD music in `music.asm` is on that
curve plus `CD_DB`. The numbers live in `mix.inc`, which both include,
and nothing here is absolute.

## frametrace.asm

A diagnostic in the exe's annex, applied by name. The frame gate's first
five bytes jump to `entry`, which takes the counter through the game's
own routine (its address in a dword after the blob) and keeps it; the
gate ends by taking the counter into `eax` and storing it as the frame's
time, with the step count in `ebx`, and its last five bytes before `pop
ebx; ret` jump to `trace`.

That appends `<entry> <blit> <exit> <steps> <flags>` to `logs\\frames.log`
in the game folder, the folder made on the first frame - blit read from fullwin.asm's stamp, found once through
the jump the borderless patch put at MGameD3D's present - opening it on
the first frame with a header `budget <ticks> qpc <0|1>` from the timer
object in `esi`, then leaves as the gate did.

`GetModuleHandleA`, `GetModuleFileNameA`, `CreateDirectoryA`,
`CreateFileA`, `WriteFile` and `wsprintfA` are resolved once through the
IAT placeholders and kept in the section,
which is writable for them and the handle; any failure leaves the handle
-1 and nothing is logged. `tools/frametracetest.py` runs it under
Unicorn, `tools/frames.py` reads the log.

## voltrace.asm

A diagnostic in the exe's annex, applied by name. Five entry points in
the sound code get a jump here; each thunk reports its call through
`OutputDebugStringA` as `sr2 vN this a1 a2 a3` in hex, does the
displaced instructions and jumps back through a dword the patcher fills
with the site's address past them. `LoadLibraryA` and `GetProcAddress`
come from the usual placeholders. What the five sites are is in the
source's header.

## d3dinit.asm

A diagnostic in MGameD3D's annex, applied by name. Every step of the
renderer's Init ends with `mov [0x10011fc4], eax`, the DLL's
last-HRESULT slot, and a `jl` out on a failure; the patcher makes each
of those stores in the bring-up tree (`D3DINIT_SITES`) a call to
`entry`, which does the store and appends `<site> <hr> <w>x<h>
<tw>x<th>` to `logs\\d3dinit.log` in the game folder, the folder made
on the first call - the store's RVA, the HRESULT, the picture size in
the init struct's copy and the largest texture in the device's caps
(`D3DDEVICEDESC` at `0x10012430`, kept by the device enumeration; 0
before it). Flags and registers are kept,
since the site's `jl` reads the `test` before the store; the absolute
in each replaced store loses its relocation entry.

`CreateDirectoryA`, `CreateFileA` and `WriteFile` are resolved on the
first call through the DLL's own `GetModuleHandleA` and `GetProcAddress`
imports, the path from its `GetModuleFileNameA`; any failure leaves the
handle -1 and
nothing is logged. The lines stop at 4096. `tools/d3dinittest.py` runs
it under Unicorn.
