# SR2 Patcher

Gets *SEGA RALLY 2* (PC, 1999) running on a modern system. It installs the
game from a disc image of the install disc without the original installer -
no InstallShield, no registry, no mounting - and patches it to run without
the play disc.

This is the successor to [v-on-patcher](https://github.com/pairomaniac/v-on-patcher)
in spirit and design: one Python script, no dependencies, byte edits
verified against the original before anything is written, and a backup
the patcher restores from. See [Status](#status) for how far it goes.

<h4 align="center">
  <a href="#quick-start">Quick start</a> &nbsp;·&nbsp;
  <a href="#installing-from-the-disc">Installing</a> &nbsp;·&nbsp;
  <a href="#what-the-patches-do">Patches</a> &nbsp;·&nbsp;
  <a href="#music">Music</a> &nbsp;·&nbsp;
  <a href="#builds">Builds</a> &nbsp;·&nbsp;
  <a href="#status">Status</a>
</h4>

## Quick start

Run `sr2-patcher.py` with Python 3 (tkinter for the window; the command
line needs nothing beyond the standard library).

1. **Disc 1 image** - the `.cue` of your install disc dump (Disc 1); the
   `.bin` sits beside it. A plain `.iso`, a mounted disc folder or
   `data1.cab` itself work too.
2. **Disc 2 cue** - the `.cue` of the play disc dump, for the music.
3. **Install to** - an empty folder. The install is about 580 MB, the
   music 230 MB more.
4. **Language** - which manual, help pages and message DLL to install.
5. **Install** - extracts the game, writes the files that replace the
   installer's registry work, and applies the patches. Then **Rip
   soundtrack**. See [Music](#music).

**Patch** does the patching alone on a game already installed this way,
or by the original installer as a Pentium III install. **Restore original**
puts the unpatched files back from the backups.

The same from a terminal:

```
python3 sr2-patcher.py --install "SEGA RALLY 2 (Disc 1).cue" ~/games/sr2 English
python3 sr2-patcher.py --rip "SEGA RALLY 2 (Disc 2).cue" ~/games/sr2
python3 sr2-patcher.py --patch ~/games/sr2
python3 sr2-patcher.py --restore ~/games/sr2
```

## Installing from the disc

The image is read directly - the ISO9660 filesystem out of the data track,
`data1.cab` out of that, and the game's files out of the cabinet - with
nothing mounted and nothing written outside the install folder. The
original installer did four things: copy files out of `data1.cab`, choose
one of three CPU builds, register the game's own COM middleware
(`LAUNCH.exe -musashi`), and write `SR2.CFG`. The patcher does the same.

- **Files.** Everything a *Full* install copies: the executables, the
  Pentium III modules over the base ones, one language, all four `BINDATA`
  tiers, the region-specific HUD textures and the car-profile narration.
  The play disc holds the same assets as MS cabinets and nothing else
  the game needs, so with a full install it is only ever asked for at the
  startup disc check - which the patch removes.
- **Musashi.** The game is built on Sega's Musashi middleware, ten COM
  servers under `MUSASHI\`. Instead of registering them, the patcher writes
  `SEGA RALLY 2.exe.manifest` and `MUSASHI\MUSASHI.manifest`: registration-free
  COM, per folder, nothing in the registry.
- **`SR2.CFG`** comes out of the cabinet as shipped; the launcher and the
  control-panel applet that used to write it are not needed.

Reading the image and `data1.cab` (InstallShield 5) is done by the script
itself; see [docs/NOTES.md](docs/NOTES.md), *The install disc*.

## What the patches do

| Patch | What it fixes |
| --- | --- |
| **No disc required** | The game scans CD-ROM drives for a disc labelled `SEGARALLY2` twice: once to put up an "insert disc" dialog, once to decide whether the menu offers the full game or multiplayer only. The first now answers "found"; the second is given the install folder as the disc. |
| **Z-buffer detach crash** | The renderer detaches a Z-buffer that does not exist yet, passing DirectDraw a null surface and ignoring the answer. Wine's ddraw in Proton dereferences the null and the game dies before its window appears; plain Wine and DirectX 6 return an error. The four calls are removed. |
| **Survive ALT+TAB** | Switching away marks the DirectDraw surfaces lost, and the game never restores them - it comes back to a blank screen. Three changes: the window procedure now calls the renderer's restore routine when the game regains focus; that routine restores every surface instead of three; and the textures are created as managed, so DirectDraw keeps its own copy and they are never lost in the first place. |
| **Music from files** | The course music is CD audio on the play disc, asked for over MCI. A routine added to `MUSASHI\MGAudio.dll` answers those requests from `music\trackNN.wav` instead. With no such files it stays out of the way and the game reads a disc as before. |

Not patched: the processor check (`miscdll.dll!CheckKatmai`) tests for
CPUID, the MMX/FXSR/SSE feature bits and a live SSE instruction, and passes
on any current CPU.

## Music

Disc 2 carries thirteen audio tracks (2-14) after its data track. **Rip
soundtrack** reads them from the play disc's bin/cue into
`music\track02.wav` … `track14.wav` beside the exe, 230 MB of plain
44.1 kHz stereo WAV, pregaps dropped. The music patch, always applied,
plays those in place of the disc, from inside the DLL that owns the CD.

What it does not do: the in-game BGM volume slider drives the CD line of
the Windows mixer, which the WAV playback does not follow. Set it at the
system level for now.

The ripper takes a cue sheet with its bins - the Redump one-file-per-track
form as well as a single bin. A `.iso` has no audio tracks, so it cannot
be a source for the music.

## Builds

The installer shipped three variants of the game and picked one by CPU:
base (x87), Pentium III (SSE) and AMD (3DNow!). Each swaps six files:
`SEGA RALLY 2.exe`, `AdvTelop.dll`, `Champagn.dll`, `MSelect.dll`,
`MUSASHI\MGameGL.dll` and `MUSASHI\MGLBackground.dll`. The patcher installs
and patches the **Pentium III** build only - every CPU since has SSE - and
refuses the other two by size and MD5.

| File | Size | MD5 |
| --- | --- | --- |
| `SEGA RALLY 2.exe` | 1469952 | `51b3da97c3c73611d3516b65bb684cb5` |
| `AdvTelop.dll` | 636928 | `977dd8801a281e987c4503c9fb2f8778` |
| `Champagn.dll` | 699392 | `b8dbfe718eef561f12c99223ba7b9ec4` |
| `MSelect.dll` | 1137152 | `1e6f713c39efb1558c79b795754d6e3a` |
| `MUSASHI\MGameGL.dll` | 601600 | `3d095385ece996088381dd77a0f5f954` |
| `MUSASHI\MGLBackground.dll` | 579584 | `e7cc2a9f084a39c6f119fa1a1d769e30` |

The base and AMD executables are known (`65e7537e…`, 1470976 bytes, and
1467392 bytes) but have no patch tables.

### What gets written

Three files are patched: `SEGA RALLY 2.exe`, `MUSASHI\MGameD3D.dll` and
`MUSASHI\MGAudio.dll`; the exe and `MGAudio.dll` grow by a section. Each gets a `.bak` beside it, the untouched
original; **Patch** always
starts from those, so patching twice is the same as patching once, and
**Restore original** is a rename. Nothing else in the folder is changed
by patching.

## Status

Installs from the disc image, starts, plays with music, under Wine and
under Proton (umu, Faugus). Windows is untested; the one thing specific to
it is the registration-free COM manifest, and if the game fails at its
first `CoCreateInstance` there, that is where to look - the fallback is
copying the ten Musashi DLLs beside the exe.

Nothing has been done yet about resolution, input or frame timing. The
ground work for those is in [docs/NOTES.md](docs/NOTES.md).

## Working on the patcher

`docs/README.md` is the index. `tools/check.py` runs the checks; give it a
disc image (or `data1.cab`, or the first 16 MB of one) and an install
folder to run the disc and cabinet check too. `sh tools/setup-dev.sh` says what is missing.

## AI Disclaimer

LLMs are part of the toolchain here, alongside pefile, capstone, unshield
and Unicorn on the game's files, and Wine's own tracing on the running
game. The scope, the disc dumps, the testing and the debugging are human.
Every change is read before it goes in and played before it ships.
Offsets and bytes are verified against the original before anything is
written, and the patcher refuses any file that is not an unmodified build
it has tables for. It is still a hobby project poking at a 27-year-old
binary, so expect bugs.

## Credits and licence

Rights to the game belong to SEGA. `LICENSE` (MIT) covers the patcher,
its tools and its documentation - not the game and not the bytes quoted
from it.

Bug reports and patches are welcome as issues and pull requests. For
anything else - a disc image of a build the patcher does not know, or a
question that does not fit an issue - write to pairo@segaonline.net.
