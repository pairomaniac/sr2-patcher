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
| `music.asm` | CD audio from files: the DllMain thunk that builds the track table, and the `mciSendCommandA` hook |
| `build.py` | assembles the above and splices it into the patcher; `MAGICS` lists the placeholders the patcher fills |

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
`mciSendStringA`, `CreateFileA`, `GetFileSize` and `CloseHandle` through
the DLL's own `LoadLibraryA`/`GetProcAddress` imports, takes the game
folder from `GetModuleFileNameA(NULL)`, and walks `music\track02.wav` to
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
| `MCI_PLAY` `MCI_FROM` TMSF | `close`, `open "<dir>music\trackNN.wav" type waveaudio alias sr2bgm`, `set … milliseconds`, `play sr2bgm [from ms]`; `MCIERR_OUTOFRANGE` for a track with no file |
| `MCI_SEEK` `MCI_TO` TMSF | `seek sr2bgm to ms` if that track is open, else remembered for the next play |
| `MCI_PAUSE`, `MCI_RESUME`, `MCI_STOP`, `MCI_CLOSE` | the same word to `sr2bgm` |
| `MCI_STATUS` number of tracks | the highest track with a file |
| `MCI_STATUS` length of track N | from the file size, as MSF |
| `MCI_STATUS` position | `status sr2bgm position`, converted to TMSF on the current track |

**One thread for MCI.** MGAudio issues its commands from short-lived
threads of its own, and Wine's `winmm` keeps an MCI device private to the
thread that opened it - a `stop` from another thread gets
`MCIERR_INVALID_DEVICE_NAME`. So startup creates two auto-reset events and
a worker thread; `mcistr` writes the command, signals the request event
and waits on the done event, and the worker does the `mciSendStringA` and
answers. Every `waveaudio` command comes from that one thread. Calls are
not serialised against each other beyond that; MGAudio does not issue two
at once.

The worker only ever waits; the game's own polling drives everything.
`tools/musictest.py` runs this session under Unicorn, including one round
of the worker.

**Known gap.** In-game BGM volume goes through the mixer's CD line, which a
`waveaudio` stream does not follow.
