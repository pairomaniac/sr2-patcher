# asm

This directory holds the source of every piece of machine code the
patches install. `sr2-patcher.py` does not read it: the assembled bytes
are baked into the script as hex strings between GENERATED markers, so
running the patcher needs no nasm. Only editing this directory does.

```
vim asm/music.asm
python3 asm/build.py             # assemble everything and write the hex into sr2-patcher.py
python3 asm/build.py --check     # what CI runs: fail if the hex no longer matches the sources
```

Never edit the hex by hand. The next build overwrites it.

The blobs have to assemble to the same bytes on every machine, because
`tools/selftest.py` pins the MD5 of every patched file. Where nasm
releases differ on how to encode an instruction - a scaled index with
no base register, a `rep` prefix on a word-sized string instruction -
the source spells the encoding out.

## Two rules every blob follows

**No source names an exe address.** The exe is never relocated, so an
exe stub reads its globals and calls its routines through absolute
addresses, but those addresses differ between the four builds. Every one
of them is a placeholder (the `*_MAGICS` tables in `build.py`) that the
patcher fills from the build's row in `BUILDS`. `build.py` refuses a
source that contains a literal `0x4xxxxx`-`0x6xxxxx` address outside a
comment. The same
goes the other way: when the patcher needs an offset *inside* a blob -
`mix.asm`'s second entry, `fullwin.asm`'s counter stamp, the resolution
table's groups - that offset is a label named in `build.py`'s `LABELS`,
read off nasm's listing and written out as `BLOB_LABELS`. Nothing of the
kind is kept by hand.

**A DLL stub is position-independent.** The DLLs are relocated on every
load, so a DLL stub cannot hold an absolute address of anything. It
takes its own address with a `call`/`pop` and reaches everything
relative to that. Some blobs (`music`, `padinput`, `dinput8`,
`nogeneric`) have their placeholders filled with offsets from the blob to
the DLL's import slots and sites, and `restore` reaches its two globals
relative to its own position; the others work out the image base by
subtracting their own RVA, which the patcher fills in, and reach the
DLL's globals and import slots as RVAs from there. The bytes a DLL
patch overwrites usually carried relocation entries for absolute
addresses that are no longer there; the patcher drops those entries, or
the loader would add the relocation delta into the new code.

## The files

| File | In | What it does |
| --- | --- | --- |
| `music.asm` | `MGAudio.dll` | plays the soundtrack from WAV files by impersonating the CD drive: the `mciSendCommandA` hook, the setup that builds the track table at `DllMain`, the worker thread that plays a track from a DirectSound buffer, the volume |
| `activate.asm` | exe | restores the DirectDraw surfaces when the game regains focus |
| `restore.asm` | `MGameD3D.dll` | the restore routine itself, rewritten as `RestoreAllSurfaces` so the textures come back too |
| `textcolor.asm` | exe | `SetTextColor` with the colour masked to RGB, so the lobby's `-1` means white again |
| `bgrow.asm` | exe, `Title.dll` | copies a `.bg` picture into the back buffer at either colour depth, or composes it with its side areas for one stretching blit; built twice |
| `fullwin.asm` | `MGameD3D.dll` | the windowed mode filling the monitor: the window sizing and a letterboxed present |
| `altenter.asm` | exe | ALT+ENTER toggling between the borderless window and a framed one |
| `starting.asm` | exe | a "starting the race" box on the team room while the race setup gathers the players |
| `ipcheck.asm` | exe | the IP entry popup refusing OK for a blank or malformed address |
| `entrycap.asm` | exe | the lobby's text entries capped at what their fields can hold, CTRL+V included |
| `status.asm` | exe | the team room's status line asked of the netplay DLL: local and public address |
| `hudlast.asm` | exe | the race HUD drawn after the frame's root tree, so the tachometer's plate blends over the lake, but before the tree's fade quad, so the fade stays over the HUD |
| `loadhold.asm` | exe | the stage loading screens held on screen for three seconds |
| `padmenu.asm` | exe | the pad on the multiplayer screens, read straight from MGInput's annex; Back acts as TAB, which is how the team room's MENU row opens |
| `sortpad.asm` | `ReplayGallery.dll` | LB and RB step the gallery's sort, which the exe's F6-F8 accelerators set |
| `pagepad.asm` | exe | LB and RB act as Page Up and Page Down in the input wrapper's level word: the Records pages, the car select's alternative colour |
| `replaypad.asm` | exe | the pad on the replay's camera controls, ORed into the level word the keyboard fills |
| `texrange.asm` | `MGameD3D.dll` | the texture release with its index checked against the count |
| `replayfree.asm` | `ReplayGallery.dll` | the gallery remembers the block its own `new` returned and frees only that |
| `wide.asm` | exe | the picture size from `SR2.CFG`, and the HUD frame flag for `wide2d`; built twice, since the American build's size setter has a third size |
| `widegl.asm` | `MGameGL.dll` | the viewports, centres, field of view and projections kept in 640x480 terms at the six methods every caller goes through |
| `wide2d.asm` | `MGameD3D.dll` | the 2D scaled to the back buffer through the six draw methods, the side bars, the lobby's blits, the device viewport |
| `resolution.asm` | `Options.dll` | the Graphic Settings page's RESOLUTION row as a list over the patcher's table, and an ASPECT RATIO row |
| `devices.asm` | `Options.dll` | the Device Settings page: its two states, init and exec, over the sprites, draw list and data the patcher builds after the code |
| `padinput.asm` | `MGInput.dll` | XInput pads answering the pad source ids at the device's poll, the pad refreshed in the config's update, and the load and save of bindings as text in `SR2.CFG` |
| `dinput8.asm` | `MGInput.dll` | the DirectInput object made through `dinput8.dll`, with DirectInput 8's device type codes translated back to DirectInput 5's |
| `nogeneric.asm` | `MGInput.dll` | the device loop skipping DirectInput 8 devices of no usable kind (types 0x11, 0x19-0x1c) |
| `mix.asm` | `MGSound.dll` | every buffer's dB range remapped to −43..−8 in `SetRange`, and the streamed music put on that curve plus `STREAM_DB` |
| `mix.inc` | - | the mix's numbers: the effects' range and the two music offsets; included by `mix.asm` and `music.asm` |
| `padpoll.inc` | - | one pad input read through the page poll MGInput's annex publishes, and the "past half its range" test; included by `padmenu.asm`, `replaypad.asm`, `pagepad.asm` and `sortpad.asm` |
| `frametrace.asm` | exe | a diagnostic: every drawn frame's counter and step count appended to `logs\frames.log` |
| `voltrace.asm` | exe | a diagnostic: five volume entry points report their arguments through `OutputDebugStringA` |
| `d3dinit.asm` | `MGameD3D.dll` | a diagnostic: every step of the renderer's bring-up appended to `logs\d3dinit.log` with its HRESULT |
| `build.py` | - | assembles the above and splices the hex into the patcher; holds the placeholder tables |

One stub is not assembled here: the `mixerless` patch's stub is three
instructions, written out directly by `apply_mixerless` in the patcher.

The placeholder tables in `build.py` are named after their file:
`MUSIC_MAGICS` (the music blob), `EXE_MAGICS` (shared by every exe
stub), `DEVICES_MAGICS`, `PADINPUT_MAGICS`, `DINPUT8_MAGICS`,
`NOGENERIC_MAGICS`, `RESOLUTION_MAGICS` and `SORTPAD_MAGICS`.
`SITE_MAGICS` (`0xE7E7E7E1` onwards) are the per-site return slots of
`voltrace.asm` and `frametrace.asm`; `frametrace`'s third one is filled
with the offset of the borderless present's counter stamp instead.

The line formats the diagnostics and the widescreen traces print are in
[docs/DEVELOPING.md](../docs/DEVELOPING.md), *Diagnostics*.

## music.asm

The game's music is Redbook audio on the play disc. `MUSASHI\MGAudio.dll`
plays it over MCI - *open cdaudio*, *play from track 5*, *status
position* - and with no disc in the drive there is nothing to play, so
the game runs silent.

This blob sits inside `MGAudio.dll`, pretends to be the CD drive, and
plays WAV files from `music\` instead. The patcher appends the blob to
the DLL's annex and cuts every path from the DLL to the real MCI
import:

- the eleven `call [__imp__mciSendCommandA]` become direct calls to the
  hook;
- the one `mov esi, [__imp__mciSendCommandA]` - the open routine loads
  the import once and calls through `esi` for both the open and the
  time-format set - becomes a call to a thunk that puts the hook's
  address in `esi`;
- the DLL's entry point is repointed at the setup thunk, which runs
  first and then chains to the original entry.

After that no reference to the import slot is left in the DLL's code.

### Position independence

The DLL asks for base `0x10000000`, but `SR2_MSG.DLL` already occupies
it, so `MGAudio.dll` is relocated on every load. The blob finds its own
base with a `call`/`pop` and addresses everything as `[ebx + offset]`.
Its five `MAGIC_` placeholders are offsets from the blob to the DLL's
import slots and old entry point; those offsets are the same wherever the
DLL lands, and `apply_music` fills them. Nothing in the blob needs a
relocation entry. The eleven rewritten call sites *had* one each, for
the absolute slot address they used to hold; `apply_music` drops those,
or the loader would corrupt the new relative displacements.

### Setup

The setup thunk runs at `DllMain` on `DLL_PROCESS_ATTACH`, once. It
resolves `DirectSoundCreate`, `GetDesktopWindow` and the eleven
`kernel32` functions listed in `S_MODULES` through the DLL's own
`LoadLibraryA` and `GetProcAddress` imports, takes the game folder from
`GetModuleFileNameA(NULL)`, and looks for `music\track02.wav` through
`track99.wav`. It never reads the audio: a track's length is its file
size less the 44-byte header, in 2352-byte frames. Then it chains to the
original entry point with the stack untouched.

If no track is found the count stays at zero, and the hook forwards
every command to the real MCI as if the patch were not there.

### The hook

MGAudio opens the CD device by type ID, not by name. The hook watches for
an open of `MCI_DEVTYPE_CD_AUDIO` and answers it with device ID `0xFACE`.
From then on any command carrying that ID is the hook's to answer;
anything else - and everything while the track table is empty - goes
through the import slot untouched.

What MGAudio sends, and what the hook answers:

| Command | Answer |
| --- | --- |
| `MCI_SET` time format | ok; TMSF is assumed |
| `MCI_PLAY` with `MCI_FROM` in TMSF | `OP_OPEN` on track N, then `OP_PLAY` from the millisecond position; `MCIERR_OUTOFRANGE` for a track that has no file |
| `MCI_SEEK` with `MCI_TO` in TMSF | if the seek names the open track, or the track one below it, `OP_PLAY` from that position; otherwise the position is remembered for the next play. The "one below" case exists because a play arrives as track N+1 while the exe's seek at "Go!" arrives as track N, and no play follows it, so the seek has to restart the track by itself |
| `MCI_PAUSE`, `MCI_RESUME`, `MCI_STOP`, `MCI_CLOSE` | the operation of that name |
| `MCI_STATUS` number of tracks | the highest track that has a file |
| `MCI_STATUS` length of track N | from the file size, as MSF |
| `MCI_STATUS` position | `OP_POS`, converted to TMSF on the current track |

### The worker thread

MGAudio issues its MCI commands from short-lived threads it creates per
action and then terminates. Wine's `winmm` refuses a command to a device
from any thread but the one that opened it, so no device call can be made
on those threads. Instead, the setup creates two auto-reset events, a
mutex and one worker thread. A `request` takes the mutex, writes the
operation and its argument, signals the request event, waits on the done
event and releases the mutex; the worker performs the operation and
signals back.

The mutex is there because two requests can arrive at once: the exe fades
the music on one thread while another changes screen, and without the
mutex one of the two requests was lost. It is a mutex and not a critical
section because a terminated thread's mutex is handed on to the next
waiter, whereas a critical section would stay locked forever.

The operations the worker performs:

| Operation | Does |
| --- | --- |
| first open | creates the `IDirectSound` (`DirectSoundCreate`, cooperative level normal on the desktop window); it lives for the rest of the process |
| `OP_OPEN` | releases whatever is open, opens `music\trackNN.wav`, creates a secondary buffer of the sample data's size (`CTRLVOLUME`, `GLOBALFOCUS` so it keeps playing whichever window has focus, `GETCURRENTPOSITION2`, software), reads the samples straight into it between `Lock` and `Unlock`, closes the file and sets the volume |
| `OP_PLAY` | `SetCurrentPosition` to the byte offset the millisecond position names, then `Play` without looping |
| `OP_STOP` | `Stop`, and the cursor back to 0 |
| `OP_PAUSE`, `OP_RESUME` | `Stop` with the cursor kept; `Play` on from where it was |
| `OP_POS` | the play cursor, or the track's end once the buffer has played out (`GetStatus` reports that, since the buffer stops itself) |
| `OP_VOL` | sets the level on the open buffer; the next `OP_OPEN` applies it again |
| `OP_CLOSE` | releases the buffer |

Nothing here runs on its own timer: the game's own polling of `MCI_STATUS`
drives everything, and at a track's end the exe seeks and plays again.
`tools/musictest.py` runs a whole session through the hook under Unicorn,
against a scripted `IDirectSound` and buffer.

### The volume

The BGM slider reaches the DLL's set-volume method through the exe's CD
wrapper at `0x46e160`. That wrapper multiplies a percentage by the level
the get-volume method returned at startup and divides by 100, and both
DLL methods fail on a machine with no mixer line. Both method entries
now jump into the blob. `getvolume` always says 10000, so every value the
wrapper passes is its percentage × 100.

`setvolume` receives four kinds of call and tells them apart by the flags
and the value:

| Call | From | Value | Flags |
| --- | --- | --- | --- |
| the menu's level | `0x473c5c` | the slider's step × 11.11 percent | `0x40`, put there by the `cdlevel` patch |
| the race's level | `0x473f11` | step × 9 | `0x80000000` |
| the mute when a race starts | `0x474210` | 0 | `0x80000000` |
| the fade before a stop | `0x4741bc` | 100 down to 10, one step a frame | 0 |

A *level* is converted to hundredths of a dB on the curve in `mix.inc`:
`MIX_BOTTOM + step × MIX_STEP + CD_DB`, which is −5 dB at step 9 and
`DSBVOLUME_MIN` at step 0. Those are the units the mix keeps every other
sound at. The level is remembered; a mute silences the buffer without
forgetting it.

The *fade* is different. It was written for a mixer line that took an
amplitude percentage, and it always starts from 100 regardless of the
slider - on the curve that would start up to 33 dB above the set
level. So the
hook treats a fade value as an amplitude percentage *of the current
level*: level plus `20 log10(v / 10000)`, from the `S_PCTDB` table. That
is why the `cdlevel` patch is required: the menu's level call and the
fade's call are indistinguishable except for the `0x40` flag `cdlevel`
adds. A fade counts down from 100 and ends at any level or mute call; a
fade step that arrives when no fade is in progress is dropped, because a
screen change can cut across a fade and its last steps then landed on
the newly started track. The original DLL read only bit 31 of the flags,
and only to wait for the previous set's thread.

This volume handling is also why the music is a DirectSound buffer and
not a wave stream. `winmm`'s volume - whether by handle or by device id -
has been the application's session volume on Windows since Vista, so
setting it moved the DirectSound effects along with the music.

### Trace mode

An empty file `music\trace` beside the tracks makes the hook report every
command it receives, and the worker every operation it performs, through
`OutputDebugStringA`. DEVELOPING.md, *Diagnostics*, gives the line
formats.

## activate.asm

Switching away from the stock game, in its exclusive display mode,
marks its DirectDraw surfaces lost, and nothing in the game restores
them: the window procedure's
`WM_ACTIVATEAPP` case only pauses and resumes the sound object. MGameD3D
has a restore routine (slot 16 of its interface, `IsLost`/`Restore` on
the primary, the back buffer and the Z-buffer) that nothing calls.

This stub is twenty-three bytes in the exe's annex. The `call 0x46e260`
that resumes the sound on activation is pointed at it. The stub saves
`ecx` (the sound object, a `thiscall` argument), calls slot 16 of the
MGameD3D interface at `0x50b118`, restores `ecx`, and continues to the
resume with `push`/`ret` so the stack is exactly what the original call
left. If there is no MGameD3D object yet it skips straight to the resume.
The two addresses - the MGameD3D pointer and the resume - are filled
from the build's row. `tools/activatetest.py` runs it under Unicorn.

## restore.asm

MGameD3D's restore routine at `0x10007710` restores only the primary,
the back buffer and the Z-buffer. The textures are DirectDraw surfaces
too, and they stayed lost, so the game came back from a switch with its
geometry and no textures.

This is forty-four bytes written over the original routine's 124. It
calls `IDirectDraw4::RestoreAllSurfaces` on the object at `0x1001254c`,
which restores every surface the object created, and stores the result
where the original did, with the same stdcall shape. It reads its two
globals relative to its own position, so it needs no relocation entries;
the ten the original routine carried are dropped by the patcher.
`tools/activatetest.py` runs it relocated.

## texrange.asm

MGameD3D's texture release at `0x10004430` takes the pointer at
`[table + N*4]`, releases it and clears the slot, without ever checking
`N`. `VendorLogo.dll`'s End releases texture −128, which is the dword 512
bytes before the table: whatever the heap happens to have left there. If
that dword is zero nothing happens; if it is a pointer the game calls
through it, and that is the crash after the vendor logo.

The release's first ten bytes become a `jmp` into this routine in the
annex. It checks the index against the count at `0x10012590` - the same
check the texture create already makes - and returns for one out of
range; otherwise it does what the ten displaced bytes did and continues.
`tools/texrangetest.py` runs it.

## replayfree.asm

The gallery's End frees the replay at `+0x50` of the screen block. That
is right when the gallery loaded the replay from a file, because then the
block is its own `new`. It is wrong when the replay came from a race,
because then the pointer is into `MainMode.dll`'s `.data`. Windows 9x's
`HeapFree` refused the bad address and the game carried on; the heap
since Windows 8 treats it as corruption and ends the process, which is
the crash on returning to the menu after saving a replay.

Two thunks in a section appended to `ReplayGallery.dll`: `alloc` stands
in for the gallery's own `new` and remembers the address it returned;
`free` stands in for the `push eax; call free` - it leaves the argument
on the stack for the caller's `add esp, 4` - and frees `eax` only when it
is the block `alloc` remembered. `tools/replayfreetest.py` runs both.

## textcolor.asm

The lobby's ten `SetTextColor` sites pass `-1` to mean white. Windows 95
ignored the top byte of a COLORREF; NT and Wine read bit 24 as
`PALETTEINDEX`, fail the lookup and fall back to black, which is also
the colour key of the blit that follows. The text is drawn and never
seen.

The stub is fourteen bytes in the exe's annex. It masks the colour
argument on the stack down to its RGB bytes and jumps through the import
slot, so it has the import's stdcall shape and the call sites keep
theirs. The eight `call [slot]` become `call stub`; the two `mov esi,
[slot]` become `mov esi, stub`. No reference to the import slot is left
in the exe's code.

## bgrow.asm

The full-screen `.bg` pictures - title, loading, game over, the course
cards - are 16-bit 565 files the game copies straight into the locked
back buffer with a twenty-byte row copy at `0x415271`. That was right
for a 16-bit 640x480 mode. In a window on a 32-bit desktop the copy puts
two pixels' bytes into each pixel and the picture comes out at half
width; on a wide picture size the buffer is larger than the picture,
which would sit in its top-left corner.

The stub replaces the row copy. It reads the lock's description at
`0x4e6878` and then:

- If the surface is the picture's size, it runs the original copy, or
  expands each 565 pixel to XRGB8888 when the surface is 32-bit.
- If the surface is any other size, it draws the whole picture on the
  first row and nothing on the rows after. The picture is composed at
  source size into a surface `MGameD3D`'s annex keeps, and one blit later
  stretches that composite into the screen. The picture goes in the
  middle at the largest size of its own aspect that fits, and the side
  areas get bars. What the bars hold depends on which build this is:
  `Title.dll`'s build fills them with the picture itself, motion-blurred
  and stretched; the exe's build fills them with the picture's corner
  pixel, because its screens are pictures on a plain background. Without
  the annex surface the stub draws the same layout into the back buffer
  itself, nearest-pixel.

`eax`, `ebx` and `edx` come out as they went in; the other registers were
scratch at the site.

The file is assembled a second time with `-DTITLE` for `Title.dll`'s copy
of the same loop at `0x100014ba`. That copy keeps its lock description on
the stack and advances the source pointer itself, so the `TITLE` build
reads the description at `[esp+0x1c]`, takes the height from the loop's
row count, and adds the row to `ebx`. `tools/bgrowtest.py` runs both
builds at both depths and both sizes under Unicorn. What the two builds
put in the bars, and why, is in [docs/WIDESCREEN.md](../docs/WIDESCREEN.md),
*The .bg screens*.

## wide.asm, widegl.asm, wide2d.asm, resolution.asm

These four are the widescreen patch, which
[docs/WIDESCREEN.md](../docs/WIDESCREEN.md) describes in full. This
section covers only how each blob is wired in.

**`wide.asm`** has four entries reached through a jump table at the top.
Two are in the mode setter: one replaces its entry compare, one its size
stores. One is in the screen-change routine, replacing its settings
read. The fourth is in the element walker, where it sets the HUD frame
flag for `wide2d` and writes the bounds of the HUD's own draws beside it.
The size table the patcher appends follows the code. The annex is
writable, for the `SR2.CFG` path.

**`widegl.asm`** takes over `SetViewport`, `SetPerspective` and
`SetCentre` at their prologues: it adjusts the arguments on the stack,
does the prologue itself, and jumps on into the method with the resume
address in `eax`, which is dead at that point. The projection and the
parameter getter it takes at their entries; it calls the rest of the
method as a routine with the arguments pushed again, then converts what
the method wrote. The inverse projection it continues into, with the
point argument pointing at a converted copy.

**`wide2d.asm`** finds its own base and the image base, and takes over
the first instructions of the six draw methods; each resumes after them
with the vertex argument pointing at the blob's scaled copy. The device's
viewport setter is taken the same way, with its rect argument pointed at
a scaled copy: the rect goes into the picture's 4:3 box, scaled by
height, and the rect's fractions take the box's share of the screen so
the countdown digit keeps its 4:3 size. The eighth entry is the present:
it closes the frame's tile table, hooks ddraw's `Blt` for the lobby's
stretch, and keeps the `.bg` surface. The ninth entry sits in the texture
create; it records what kind of texture this is, for the side bars'
sake, and then replays the thirteen bytes it displaced.

`widegl` and `wide2d` each carry a trace that is off unless the
`gltrace` or `d3dtrace` diagnostic sets its flag. The patcher finds the
flag by a marker string in the annex. `wide2d`'s lines also go to
`logs\d3dtrace.log`, opened on the first line the way `d3dinit.asm`
opens its log.

**`resolution.asm`** follows `devices.asm`'s pattern for `Options.dll`,
with its placeholders as RVAs. The two kernel32 profile routines it uses
come through `LoadLibraryA` and `GetProcAddress`.

`tools/widetest.py` runs the first three; `tools/resolutiontest.py` runs
the fourth on the real `Options.dll`.

## fullwin.asm

MGameD3D's windowed path sizes the window to the 640x480 it draws
(`MoveWindow` at `0x100026be`) and presents by blitting the back buffer
into the window's client rect (`0x10004d7b`). This blob replaces both
ends, so the window can cover the monitor and the picture is letterboxed
into it.

The blob is two thunks in `MGameD3D.dll`'s annex. It takes its own
address with a `call`/`pop`, subtracts its RVA (filled in over
`MAGIC_SELFRVA` by the patcher) to get the image base, and reaches the
DLL's globals and import slots as RVAs from there.

**`present`** (`+0`) is jumped to from the first instruction of the
windowed present, inside the 16-byte stack frame that routine had already
set up, and leaves through that frame's `ret 4`. It takes the client rect
in screen coordinates, fits the back buffer's aspect into it, fills
whichever bars have any area with `Blt(DDBLT_COLORFILL)`, blits the back
buffer into the middle, and stores the result where the original did.

There is one complication. DirectDraw's primary surface is the primary
monitor, on Windows and Wine alike, so a blit whose destination leaves
that monitor fails. When the client rect leaves it (checked against
`GetSystemMetrics`), the present goes through GDI instead: the back
buffer's DC is stretched into the window's DC with `StretchBlt`, the bars
are filled with `PatBlt`, and `DD_OK` is stored. `QueryPerformanceCounter`
and the six user32 and gdi32 entry points this needs are resolved on the
first present; if any is missing, the DirectDraw blit is kept. The
counter value after the blit goes to `t_blt`, for `frametrace.asm`. The
annex is writable for these.

**`sizewindow`** (`+5`) has `MoveWindow`'s stdcall shape and is called in
its place from the windowed init, which runs on every screen change. A
framed window (the player pressed ALT+ENTER) is left alone. A `WS_POPUP`
window is moved to cover a monitor: the one under the cursor the first
time (`GetCursorPos`, `MonitorFromPoint`, `GetMonitorInfoA`, resolved
through the DLL's own `LoadLibraryA` and `GetProcAddress`), and the one
it is already on after that (`MonitorFromWindow`), so a window ALT+ENTER
moved to another monitor stays there. If any of those calls fails the
window goes where the game asked.

`tools/fullwintest.py` runs both under Unicorn with those calls recorded.

## altenter.asm

The window procedure hands every message it has no case for to the
text-input handler at `0x41fe20` (cdecl, called at `0x426cbc`). That call
now goes through this stub in the exe's annex.

ALT+ENTER - `WM_SYSKEYDOWN` with `VK_RETURN` and the ALT bit set - toggles
the window between `WS_POPUP` covering its monitor and
`WS_OVERLAPPEDWINDOW` with a client area of the picture's size, centred
on that monitor, and answers 0. A key repeat (bit 30 of lParam) is
answered 0 without toggling. Any other message goes on to the handler by
`push`/`ret` with the stack untouched.

The five user32 entry points the stub uses are not among the exe's
imports; it resolves them on first use and keeps them in the section,
which is therefore writable. The section's own address is not known
until it is appended, so the stub reaches its data from a `call`/`pop`
base. `tools/altentertest.py` runs it under Unicorn.

## ipcheck.asm

The IP entry popup's OK press compares the entry's length with zero
(`0x43cb4e`; a blank entry meant DirectPlay's broadcast search) and then
copies the text into a 16-byte settings slot from an entry that holds
2048 characters. This stub in the exe's annex is called in place of that
compare.

It accepts at most 47 characters - the settings' 16-byte slot plus the
unused modem number's after it - of either a dotted quad or a host name
of letters, digits, dots and hyphens, with an optional `:port` in
1..65535. For a valid entry it redoes the compare and lets the press go
on. For anything else it drops the return address, pushes the popup's
sound arguments with the cancel sound, and continues into the popup's
own sound call at `0x43cbac`, so the popup stays up. `tools/ipchecktest.py`
runs it on the real exe under Unicorn.

## entrycap.asm

One text-entry widget serves every field in the lobby, and its character
handler accepts up to 0x800 characters whatever the field. The fields
are far smaller, and the exe copies the text into them with `lstrcpy`,
so a long entry overwrote what followed. CTRL+V was worse: it pasted the
clipboard into the entry's buffer with no check at all.

Three entries in the exe's annex:

- **init** is called at the widget's init (`0x420f10`) in place of its
  first two loads. It works out a cap for the field the text will be
  copied back to - 47 for the address slot, 35 for the team name, 255
  for the chat line, 20 for the driver name, and 0x800 otherwise - keeps
  it, and redoes the two loads it displaced. The driver name shares the
  chat's buffer, so it is told apart by the width shown.
- **cap** is called in place of the handler's two `cmp eax, 0x800`. It
  compares against the kept cap and returns with the flags set for the
  `jae` that follows.
- **paste** stands in for CTRL+V's `lstrcpyA` of the clipboard and the
  `lstrlenA` after it. It copies up to the room the cap leaves, drops
  characters below a space, and returns the count copied.

The section keeps the cap, so it is writable. `tools/ipchecktest.py`
runs all three on the real exe under Unicorn.

## status.asm

On DIRECT IP the team room prints its own status line from
`gethostbyname`, starting at the `lea` at `0x43604b` and drawing at
`0x43611c`. That shows the machine's local address, which is useless to a
guest across a router. The netplay DLL's network object has a slot for a
better line (`+0x38`, `Network_StatusLine(buf, len)`: the local and
public addresses).

This stub in the exe's annex is called in place of that `lea`. It asks
the DLL for the line into the same buffer and continues at the draw. If
there is no network object, the call fails, or the line is empty, it
redoes the `lea` and returns so the exe prints its own line as before.
`tools/ipchecktest.py` runs it under Unicorn with a fake network object.

## starting.asm

When the host presses START, and when a guest receives the host's word,
the exe calls the race setup at `0x438dc0`. That routine spins on
`timeGetTime` waiting for the other players and draws nothing, so the
screen holds the room's last frame and the game looks stuck. This blob
puts a box on the screen for the wait.

Three entries in the exe's annex:

- The first is called in place of the two calls into the race setup. It
  draws a box in the middle of the room's background surface with gdi32
  (`SelectObject` with the lobby's font, `GetTextExtentPoint32A`,
  `SetBkMode`, `SetBkColor`, `SetTextColor`, and `ExtTextOutA` for both
  the fills and the text): a white border, a near-black fill, and
  `STARTING THE RACE` over `WAITING FOR THE OTHER PLAYERS` centred in
  white, the way the game's own popups look. It raises a flag, blits the
  box's rectangle alone onto the back buffer through the surface's
  wrapper, calls MGameD3D's present, and jumps to the setup, which
  returns to the original site.
- The second is called in place of the frame gate's present call
  (`0x428835`). While the flag is up it blits the box over whatever the
  frame drew, then presents. This is for the host, whose setup returns
  while the guests are still loading, to a room that keeps drawing and
  would bury the box.
- The third sits over the first eight bytes of the lobby's surface
  loader (`0x406fa0`), which every lobby screen's init calls. It takes
  the flag down - the surface the box was drawn on is gone with the room
  - and goes on into the loader.

The gdi32 entry points are resolved once through the import slots. The
placeholders are the room's surface and size tables, the lobby's font,
the surface loader, the setup, MGameD3D's object, `LoadLibraryA` and
`GetProcAddress`. `tools/startingtest.py` runs the three entries under
Unicorn on every build.

## hudlast.asm

The tachometer's plate is alpha-blended and drawn with the HUD after the
scene pass, but the lake on Mountain is drawn later still, as a node of
the root tree the frame object draws. Under the plate the lake fails the
z-test, so the plate blends over the flat grey backdrop instead of the
water.

Three entries in the exe's annex move the HUD after the tree. One
replaces the race state's HUD call and holds the HUD back when the tree
is about to be drawn. One replaces the frame's root-tree draw and draws
the pending HUD after the tree, with the full viewport set and the
state's reset made. One replaces the fade node's draw thunk and draws the
pending HUD before the fade's quad, so the fade stays over the HUD as it
did. [docs/NOTES.md](../docs/NOTES.md), *HUD after the water*, has the
full account. `tools/hudlasttest.py` runs the three entries under
Unicorn.

## loadhold.asm

The stage's loading card is an object the exe creates when the loading
screen opens and deletes the moment the course has loaded. A modern
machine loads a course in well under a second, so the card is gone before
it can be read.

Two entries in the exe's annex. One replaces the store of the new
picture object at its create and notes the tick. The other replaces the
load of that object at the step that deletes it, and sleeps until three
seconds have passed since the note. [docs/NOTES.md](../docs/NOTES.md),
*Loading screens*, has the detail. `tools/loadholdtest.py` runs both.

## padmenu.asm

Three things keep a pad off the multiplayer team room: the input
wrapper's mask carries nothing from an XInput pad there, the MENU row
opens only on the keyboard's TAB bit, and a held direction repeats at
the keyboard's rate. The same poll serves the driver select and the
connection screens.

One entry in the exe's annex replaces the store of the pad poll's level
word. It asks MGInput's annex for the pad's D-pad, left stick, A, B,
Start and Back through the poll the annex publishes. The buttons go into
the level word as the screens' bits. The directions go the keyboard's
way instead: into the keyboard's menu word, at the keyboard's repeat
timing, where they wait for the task that reads the word rather than
being cleared by the frame. A press of Back sets TAB there, and any press
sets the "any key" bit. Then the edge word is made again against the
stored previous level - the exe made one before the site, from a level
without the annex's bits - and the three stores are done.
[docs/NOTES.md](../docs/NOTES.md), *The menus' directions*, has the
account. `tools/padmenutest.py` runs it.

## sortpad.asm

The Replay Gallery's sort is set by the exe's F6-F8 accelerators, which
no pad input can reach. One entry in `ReplayGallery.dll`'s annex replaces
the two instructions after the list's row update in its browse state. It
asks MGInput's annex for side 0's LB and RB through the published poll,
steps the sort mode left on a press of LB and right on a press of RB,
then does the two displaced instructions. It finds the image base from
its own RVA and keeps track of which buttons were already down.
[docs/NOTES.md](../docs/NOTES.md), *Page Up and Page Down*, has the
account. `tools/sortpadtest.py` runs it.

## pagepad.asm

The input wrapper's level word has two bits, Page Up and Page Down,
that only the keyboard can set, and two screens read them: the Records
pages and the car select's alternative colour. One entry in the exe's
annex replaces the load and test after the wrapper's action table loop.
It asks MGInput's annex for the player's LB and RB through the published
poll, ORs them into the player's level word as the Page Up and Page Down
bits, then does the load and test so the site's branch sees the right
flags. [docs/NOTES.md](../docs/NOTES.md), *Page Up and Page Down*, has
the account. `tools/pagepadtest.py` runs it.

## replaypad.asm

The replay's camera controls have their own input object, filled from
fixed keyboard scancodes and from a DirectInput joystick only when the
player's config had one at start; MGInput's actions are never asked, so
an XInput pad never reaches it. One entry in the exe's annex replaces
the two loads at the point where the keyboard and joystick paths join.
It asks MGInput's annex for the player's bumpers, left stick, triggers,
Y and X through the published poll, ORs their bits into the player's
level word, puts the left stick's x into the analog value when the
keyboard left it at 0, then does the two loads.
[docs/NOTES.md](../docs/NOTES.md), *The replay's controls*, has the
account. `tools/replaypadtest.py` runs it.

## padinput.asm

This is the XInput annex appended to `MGInput.dll`, and the largest stub
here.

MGInput reads every action as a record of up to eight source ids, and
each player's config polls its device for each source through the
device's `+0x58` method, `(source, &value, &range)`. Keyboard sources are
1-0xff, joystick 0x101-0x168, mouse 0x201-0x20b. The annex answers a new
range, 0x300-0x37f, from XInput: `0x300 + player * 0x40 + input`. The
config's per-frame update is hooked so that each player's pad is read
once a frame before the records poll it.

The menus' left and right are the steering's own actions, so the fixed
sources that keep a menu navigable whatever the player has bound -
D-pad, stick halves, arrow keys - carry a menu-only bit. They answer only
while the exe's car table has no car in slot 0, which is true everywhere
except from a race's setup to its teardown.

The registry helper's load and save become the `SR2.CFG` text store. A
save whose name starts `DZ` takes the digits after it as that player's
deadzone, and source 0x3f reads the deadzone back.

The European, American and Japanese builds have their device poll hooked
at the same site. The Australian build's older DLL has no such method;
its record update calls a static poll per device type, so there the
keyboard poll's address in that dispatch is pointed at the annex
instead. The Device Settings page polls the pad through a third entry
whose address the annex writes to an exe slot. `tools/padinputtest.py`
runs it.

## dinput8.asm

MGInput makes its DirectInput object with `DirectInputCreateA` and takes
`IDirectInput2` from it, all through the legacy `dinput.dll`. That DLL's
enumeration of every attached HID device is where the start-ups that hang
on a white window go wrong; `dinput8.dll`'s does not.

The switch works because `dinput8.dll`'s objects carry the same
vtables: `IDirectInput8` matches `IDirectInput2` slot for slot, and
`IDirectInputDevice8` is `IDirectInputDevice2` with three methods
appended. So MGInput's existing calls work unchanged once the object is
DirectInput 8's. Three things have to change:

- The create becomes `DirectInput8Create`, resolved once through the
  DLL's own `LoadLibraryA` and `GetProcAddress` slots.
- The patcher writes the version 8 interface ids over the version 2 ones
  in `.rdata`, so the two `QueryInterface` calls still succeed.
- DirectInput 8 renumbered the device type codes, and MGInput switches
  on them. The `kind` entry is called where the DLL first reads the type
  byte; it writes the old code over the new one, then does what the
  displaced instruction did.

`tools/dinput8test.py` runs it.

## nogeneric.asm

MGInput makes a device object of every instance the enumeration returns.
On a machine of today that list holds LED controllers, stream decks,
audio control collections and a composite pad's spare collections -
DirectInput 8 types 0x11 and 0x19-0x1c - which the game can do nothing
with, and each of which is a chance for a driver to stall the start-up.

One entry, reached by a jump from the device loop five bytes after its
null-GUID compare. The stub makes the null-GUID branch, looks at
`dwDevType` at `+0x20` of the instance, skips those kinds the same way a
null GUID is skipped, and does the two displaced instructions on the way
out. Mice, keyboards and every controller kind go through as before. It
needs `dinput8`, whose type codes these are. `tools/nogenerictest.py`
runs it.

## devices.asm

The Device Settings page. Two entries in the top-level state table,
which the patcher moves into `Options.dll`'s annex; both are entered
with `esi` as the Options object, as every case in that table is.

`init` binds the page's UV table to the loaded texture sheets, fills the
value strings from the input records, starts the slide-in and falls
through into `exec`. `exec` draws the page's list, moves the cursor,
switches between the two players, waits for a key or pad input on an
action row and binds it (swapping with whichever row had that input
before), steps the deadzone, restores the defaults, and slides the page
out to the left before handing the menu its state back.

The page reaches the game's input objects through a holder the exe fills:
the exe's input wrapper, MGInput's input object, a config's record list,
and the pad through the poll entry `padinput.asm` publishes. The sprites,
their quads, the draw list and the data block are built by the patcher
and placed after this code, so the assembly holds none of the page's
layout. `tools/devicestest.py` runs it.

## mix.asm

The sound manager gives each effect a dB range of −40..0 and sets its
ceiling at `(step+1)/10` of that range, which is 4 dB a slider step. The
streamed music had a range of its own, and the CD music was linear in
amplitude, so one step of a slider meant three different things.

Two routines in `MGSound.dll` put everything on one curve. `range` sits
where the buffer's `SetRange` loads its min and max, and maps each onto
the range in `mix.inc`: 3.5 dB a step, with step 9 landing where the old
step 7 did. `stream` sits where the streaming buffer's `SetVolume`
finishes mapping its value to dB, and puts it on the same curve plus
`STREAM_DB`. The CD music in `music.asm` is on the same curve plus
`CD_DB`. The numbers live in `mix.inc`, which both files include, and
nothing here is absolute.

## frametrace.asm

A diagnostic in the exe's annex, applied by name only. The frame gate's
first five bytes jump to `entry`, which reads the counter through the
game's own routine (its address in a dword after the blob) and keeps it.
The gate ends by reading the counter into `eax` and storing it as the
frame's time, with the step count in `ebx`; its last five bytes before
`pop ebx; ret` jump to `trace`.

`trace` appends `<entry> <blit> <exit> <steps> <flags>` to
`logs\frames.log` in the game folder, then leaves as the gate did. The
`blit` value is read from `fullwin.asm`'s counter stamp, found once
through the jump the borderless patch put at MGameD3D's present. On the
first frame the folder is made and the file opened with a header line
`budget <ticks> qpc <0|1>`, taken from the timer object in `esi`.

`GetModuleHandleA`, `GetModuleFileNameA`, `CreateDirectoryA`,
`CreateFileA`, `WriteFile` and `wsprintfA` are resolved once through the
IAT placeholders and kept in the section, which is writable for them and
for the file handle. Any failure leaves the handle at -1 and nothing is
logged. `tools/frametracetest.py` runs it under Unicorn; `tools/frames.py`
reads the log.

## voltrace.asm

A diagnostic in the exe's annex, applied by name only. Five entry points
in the sound code get a jump into it. Each thunk reports its call through
`OutputDebugStringA` as `sr2 vN this a1 a2 a3` in hex, does the
displaced instructions, and jumps back through a dword the patcher fills
with the address just past the site. `LoadLibraryA` and `GetProcAddress`
come from the usual placeholders. The five sites are listed in the
source's header.

## d3dinit.asm

A diagnostic in MGameD3D's annex, applied by name only, for the "Failed
to initialize" box.

Every step of the renderer's Init ends with `mov [0x10011fc4], eax` -
the DLL's last-HRESULT slot - and a `jl` out on failure. The patcher
turns each of those stores in the bring-up tree (`D3DINIT_SITES`) into a
call to `entry`. `entry` does the store and appends one line, `<site>
<hr> <w>x<h> <tw>x<th>`, to `logs\d3dinit.log` in the game folder: the
store's RVA, the HRESULT, the picture size in the init struct's copy, and
the largest texture the device's caps allow (from the `D3DDEVICEDESC` at
`0x10012430`, which the device enumeration fills; 0 before that). So the
last line with a negative `hr` names the call that failed.

After the second of Init's stores (`FMTSITE`, by which point the texture
formats have been enumerated) one more line is written: `fmt <slots>
<chosen> <not565>` - which of the thirteen format slots the device
filled, the slot picked for 16-bit textures, and the "not 565" flag.

Flags and registers are preserved, because the site's `jl` reads the
result of a `test` made before the store. The absolute address in each
replaced store loses its relocation entry.

`CreateDirectoryA`, `CreateFileA` and `WriteFile` are resolved on the
first call through the DLL's own `GetModuleHandleA` and `GetProcAddress`
imports, and the path comes from its `GetModuleFileNameA`. Any failure
leaves the handle at -1 and nothing is logged. The log stops at 4096
lines. `tools/d3dinittest.py` runs it under Unicorn.
