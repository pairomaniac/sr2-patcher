# asm

Source for the machine code the patches install. `sr2-patcher.py` carries the
finished bytes between GENERATED markers, so running the patcher needs no
nasm; only editing this directory does.

```
vim asm/music.asm
python3 asm/build.py             # assemble and write the hex into sr2-patcher.py
python3 asm/build.py --check     # what CI runs: assembly and hex still match
```

Never edit the hex by hand; the next build overwrites it.

| File | What it holds |
| --- | --- |
| `music.asm` | CD audio from files: the DllMain thunk that builds the track table, the `mciSendCommandA` hook, and the worker that plays a track from a DirectSound buffer |
| `activate.asm` | calls the renderer's restore when the game regains focus |
| `textcolor.asm` | `SetTextColor` with the colour masked to RGB, for the lobby's `-1` |
| `bgrow.asm` | one row of a .bg picture into the back buffer, expanded to 32 bits when the buffer is; built twice, for the exe and for `Title.dll` |
| `fullwin.asm` | the windowed mode filling the monitor: window sizing and a letterboxed present |
| `altenter.asm` | ALT+ENTER between the borderless window and a framed one |
| `voltrace.asm` | diagnostic, applied by name: five volume entry points in the exe report their arguments through `OutputDebugStringA` |
| `mix.inc` | the mix's numbers: the effects' range, the two music offsets; `mix.asm` and `music.asm` include it |
| `mix.asm` | in `MGSound.dll`: every buffer's dB range remapped to −43..−8 in `SetRange`, and the streamed music on that curve plus `OFFSET` in the streaming buffer's `SetVolume` |
| `devices.asm` | in `Options.dll`: the Device Settings page's two states, init and exec - the list drawn, the cursor, binding through the game's input objects - over the sprites, draw list and data the patcher builds after it; `DEVICES_MAGICS` are its placeholders |
| `padinput.asm` | in `MGInput.dll`: XInput answering the pad source ids at the device's poll (the Australian build's keyboard poll), the pad refreshed in the config's update, the registry helper's load and save on the `SR2.CFG` text; `PADINPUT_MAGICS` are its placeholders, two replay slots the sites' displaced bytes |
| `restore.asm` | that restore, redone as `RestoreAllSurfaces` so the textures come back too |
| - | the `mixerless` stub is three instructions, written by `apply_mixerless` in the patcher rather than assembled here |
| `build.py` | assembles the above and splices them into the patcher; `MAGICS` lists the placeholders the patcher fills in the music blob, `EXE_MAGICS` the addresses it fills in the exe stubs from the build's row |

## music.asm

The game's music is Redbook audio on the play disc, played over MCI by
`MUSASHI\MGAudio.dll` - *open cdaudio*, *play from track 5*, *status
position*. No disc means nothing to play, so the game runs silent.

This impersonates the CD drive from inside `MGAudio.dll` and plays WAV
files instead. The patcher appends it as a `.sr2m` section, rewrites the
DLL's eleven `call [__imp__mciSendCommandA]` into direct calls to the
hook, rewrites the one `mov esi, [__imp__mciSendCommandA]` - the open
routine loads the import once and calls `esi` for the open and the set -
into a call to a thunk that returns the hook's address in `esi`, and
points the entry point at the setup thunk. No reference to the import
slot is left in the DLL's code.

**Position-independent.** The DLL prefers `0x10000000` but `SR2_MSG.DLL`
already holds that, so it is relocated on every load. The blob finds its
own base with a `call`/`pop` and reaches everything as `[ebx + offset]`.
The five `MAGIC_` placeholders are offsets from the blob to the DLL's
import slots and old entry point, constant wherever the DLL lands, filled
by `apply_music`. Nothing in the blob needs a relocation entry - and the
eleven call sites, which had one each for their absolute slot address,
lose theirs, or the loader would corrupt the new relative displacement.

**Setup** runs at `DllMain` on `DLL_PROCESS_ATTACH`, once. It resolves
`DirectSoundCreate`, `GetDesktopWindow` and the eleven `kernel32`
functions in `S_MODULES` through the DLL's own `LoadLibraryA`/`GetProcAddress`
imports, takes the game folder from `GetModuleFileNameA(NULL)`, and walks `music\track02.wav` to
`track99.wav`. It never reads a track: after the 44-byte header the file
size is the length in 2352-byte frames. Then it chains to the original
entry with the stack untouched. No tracks found leaves the count at zero,
and the hook forwards everything.

**The hook** watches for an open of device type `MCI_DEVTYPE_CD_AUDIO`
(MGAudio opens by type ID, not by name) and answers with device ID
`0xFACE`. Calls carrying that ID are its own; everything else, and every
call while the table is empty, goes through the import slot untouched.

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

**The worker.** MGAudio issues its commands from short-lived threads of
its own and terminates them, so no device call is made on one: startup
creates two auto-reset events, a mutex and a worker thread; `request`
takes the mutex, writes the operation and its argument, signals the
request event, waits on the done event and releases the mutex, and the
worker does it and answers. The mutex is there because the exe fades
on one thread while another changes screen, and two requests at once
left one unrun; a mutex and not a critical section since a terminated
holder's mutex is handed on.

The operations, on the worker. The first open makes the `IDirectSound`
(`DirectSoundCreate`, cooperative level normal on the desktop window)
that lives for the process. `OP_OPEN` releases what is open, opens
`music\trackNN.wav`, creates a secondary buffer of its sample size -
`CTRLVOLUME`, `GLOBALFOCUS` so no window of the game's matters,
`GETCURRENTPOSITION2`, software - reads the samples straight into it
between `Lock` and `Unlock`, closes the file and sets the volume; `OP_PLAY` is
`SetCurrentPosition` to the byte the ms names and `Play`, no loop;
`OP_STOP` is `Stop` and the cursor back to 0; `OP_PAUSE` is `Stop` with the
cursor kept, `OP_RESUME` `Play` on from it; `OP_POS` is the play cursor,
or the track's end once a play has run out, which `GetStatus` says since
the buffer stops itself there; `OP_CLOSE` releases the buffer. The game's
own polling drives everything; at the end the exe seeks and plays again.
`tools/musictest.py` runs the hook's session and each operation under
Unicorn, against a scripted `IDirectSound` and buffer.

**The volume.** The BGM slider reaches the DLL's set-volume method
through the exe's CD wrapper (`0x46e160`), which multiplies a percentage
by the level the get-volume method gave it at startup, divided by 100;
both methods fail without a mixer. Both entries jump into the blob.
`getvolume` says 10000, so every value is its percentage × 100.
`setvolume` gets four kinds of call and tells them by the flags and the
value: the menu's level, the slider's step × 11.11 percent, from
`0x473c5c`, flags `0x40` by the `cdlevel` patch; the race's level, step × 9, from `0x473f11`, flags `0x80000000`;
the mute when a race starts, 0 from `0x474210`, the same flag; and the
fade before a stop, 100 down to 10 a frame, from `0x4741bc`, flags 0. A
level is the step in hundredths of a dB straight from `mix.inc` -
`MIX_BOTTOM + step × MIX_STEP + CD_DB`, −5 dB at 9, `DSBVOLUME_MIN` at 0 -
the units the mix keeps every other level in, and is remembered; the
mute is off without forgetting it. The fade was written for a mixer
line that took amplitude, from full whatever the slider said - on the
curve that would open up to 33 dB above the level - so it is an
amplitude percentage of the level: the level plus `20 log10(v / 10000)`,
from `S_PCTDB`. `cdlevel` is required for that: the menu's level is
told from the fade by nothing but the flag. A fade counts from its
start, 100, and ends at any level or mute; a step arriving outside one
is dropped, since a screen change can cut across a fade and its last
steps then landed on the new track.
The original DLL read only bit 31 of the flags, to wait for the previous
set's thread. The worker sets the level on the open buffer (`OP_VOL`);
the next open sets it again. This is why the music is a
DirectSound buffer and not a wave stream: winmm's volume, by handle or by
device id, is the application's session volume on Windows since Vista,
and moved the DirectSound effects with the music.

**Trace mode.** An empty `music\trace` beside the tracks makes the hook
report every command it receives to `OutputDebugStringA` as `sr2 <id>
<msg> <flags> <p1> <p2> <p3>`, and the worker every operation it
answers as `sr2 op <op> <arg> <result> <last DirectSound HRESULT>`, in
decimal; for the volume the arg is the dB value set, as unsigned.

## activate.asm

Twenty-three bytes in a `.sr2a` section appended to the exe. The window
procedure's `WM_ACTIVATEAPP` case resumes the sound object on activation
with a `call 0x46e260`; that call is pointed here. The stub saves `ecx`
(the sound object, a `thiscall` argument), calls slot 16 of the MGameD3D
interface at `0x50b118` - `IsLost`/`Restore` on the primary, the back
buffer and the Z-buffer - restores `ecx`, and continues to the resume
with `push`/`ret`, so the stack is what the original call left. With no
MGameD3D object yet it skips straight to the resume. The exe is never
relocated, so the addresses are absolute and nothing is filled at apply
time. `tools/activatetest.py` runs it under Unicorn.

## textcolor.asm

Fourteen bytes in a `.sr2c` section appended to the exe. The lobby's
ten `SetTextColor` sites pass `-1` for white; NT and Wine read bit 24 of
that as `PALETTEINDEX` and draw black, the colour key of the blit that
follows. The stub masks the colour argument on the stack to its RGB
bytes and jumps through the import slot, so it has the import's stdcall
shape and the sites keep theirs: the eight `call [slot]` become `call`
here, the two `mov esi, [slot]` become `mov esi` of this address. No
reference to the slot is left in the exe's code.

## bgrow.asm

A hundred and twenty-one bytes in a `.sr2w` section appended to the exe,
replacing the twenty-byte row copy at `0x415271` that puts the 16-bit
`.bg` pictures into the locked back buffer. It reads the lock's bit depth
from the description at `0x4e6878` and either runs the original copy or
expands each 565 pixel to XRGB8888. `eax`, `ebx` and `edx` come out as
they went in; the rest were scratch at the site. Assembled again with
`-DTITLE` for `Title.dll`'s copy of the loop (`0x100014ba`), which keeps
its lock description on the stack and advances the source itself:
that build reads the depth at `[esp+0x70]` and adds the row to `ebx`.
`tools/bgrowtest.py` runs both at both depths under Unicorn.

## fullwin.asm

Two thunks in a `.sr2f` section appended to `MGameD3D.dll`. It is
relocated on every load, so the blob takes its own address with a
call/pop, subtracts its RVA (filled in over `MAGIC_SELFRVA` by the
patcher) for the image base, and reaches the DLL's globals and import
slots as RVAs from there.

`present` (+0) is jumped to from the first instruction of the windowed
present, inside the 16-byte frame that routine had made, and leaves
through that frame's `ret 4`. It takes the client rect in screen
coordinates, fits the back buffer's aspect into it, fills whichever bars
have area with `Blt(DDBLT_COLORFILL)` and blits the back buffer into the
middle, storing the result where the original did.

`sizewindow` (+5) has `MoveWindow`'s stdcall shape and is called in its
place from the windowed init, which runs on every screen change. It
leaves a framed window (ALT+ENTER) alone and moves a `WS_POPUP` one to
the monitor under the cursor - `GetCursorPos`, `MonitorFromPoint`, `GetMonitorInfoA`,
resolved through the DLL's own `LoadLibraryA` and `GetProcAddress` - or
where the game asked if any step fails. `tools/fullwintest.py` runs both
under Unicorn with those calls recorded.

## altenter.asm

In a `.sr2k` section appended to the exe, in front of the text-input
handler the window procedure calls for every message it has no case for
(`0x426cbc` → `0x41fe20`, cdecl). ALT+ENTER - `WM_SYSKEYDOWN`,
`VK_RETURN`, ALT bit set, repeat bit clear - toggles the window between
`WS_POPUP` over its monitor and `WS_OVERLAPPEDWINDOW` with a client area
of the picture's size, centred on that monitor, and answers 0; any other
message goes on to the handler by `push`/`ret`, the stack untouched. The
section keeps the five user32 entry points it resolves on first use, so
it is writable, and reaches its own data from a call/pop base since its
address is only known once appended. `tools/altentertest.py` runs it
under Unicorn.

## restore.asm

Forty-four bytes written over MGameD3D's restore routine at `0x10007710`,
which had 124 and restored only the primary, the back buffer and the
Z-buffer - textures are DirectDraw surfaces as well and stayed lost. The
replacement calls `IDirectDraw4::RestoreAllSurfaces` on the object at
`0x1001254c` and stores the result where the original did, with the same
stdcall shape. It finds its two globals relative to itself (the DLL is
relocated on every load), so the ten relocation entries the original
routine carried are dropped by the patcher. `tools/activatetest.py` runs
it relocated.
