# SR2 Patcher

Gets *SEGA RALLY 2* (PC, 1999) running on a modern system. It installs the
game from the install disc without the original installer - no
InstallShield, no registry, no CD-ROM drive - and patches it to run without
the play disc.

This is the successor to [v-on-patcher](https://github.com/pairomaniac/v-on-patcher)
in spirit and design: one Python script, no dependencies, byte edits
verified against the original before anything is written, and a backup
the patcher restores from. It is early. What works today is the install
and the disc check; see [Status](#status).

<h4 align="center">
  <a href="#quick-start">Quick start</a> &nbsp;·&nbsp;
  <a href="#installing-from-the-disc">Installing</a> &nbsp;·&nbsp;
  <a href="#what-the-patches-do">Patches</a> &nbsp;·&nbsp;
  <a href="#builds">Builds</a> &nbsp;·&nbsp;
  <a href="#status">Status</a>
</h4>

## Quick start

Run `sr2-patcher.py` with Python 3 (tkinter for the window; the command
line needs nothing beyond the standard library).

1. **data1.cab** - browse to `data1.cab` on the install disc (Disc 1). A
   mounted image is fine; the play disc (Disc 2) is not needed at all.
2. **Install to** - an empty folder. The install is about 580 MB.
3. **Language** - which manual, help pages and message DLL to install.
4. **Install** - extracts the game, writes the files that replace the
   installer's registry work, and applies the patches.

**Patch** does the last step alone on a game already installed this way,
or by the original installer as a Pentium III install. **Restore original**
puts the unpatched executable back from the backup.

The same from a terminal:

```
python3 sr2-patcher.py --install /path/to/data1.cab ~/games/sr2 English
python3 sr2-patcher.py --patch ~/games/sr2
python3 sr2-patcher.py --restore ~/games/sr2
```

## Installing from the disc

The original installer did four things: copy files out of `data1.cab`,
choose one of three CPU builds, register the game's own COM middleware
(`LAUNCH.exe -musashi`), and write `SR2.CFG`. The patcher does the same
without touching anything outside the game folder.

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

Reading `data1.cab` (InstallShield 5) is done by the script itself; see
[docs/NOTES.md](docs/NOTES.md), *The install disc*.

## What the patches do

| Patch | What it fixes |
| --- | --- |
| **No disc required** | The startup check scans CD-ROM drives for a disc labelled `SEGARALLY2` and refuses to start without one. It now answers "found" without looking. |

The processor check (`miscdll.dll!CheckKatmai`) tests for CPUID, the
MMX/FXSR/SSE feature bits and a live SSE instruction, and passes on any
current CPU, so it is left alone.

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

`SEGA RALLY 2.exe.bak` is the untouched executable; **Patch** always
starts from it, so patching twice is the same as patching once, and
**Restore original** is a rename. Nothing else in the folder is changed
by patching.

## Status

Written, and checked against a real `data1.cab` and a real Pentium III
install, but not yet run on Windows:

- The cabinet reader lists all 5,725 files and extracts them byte-identical
  to what the installer wrote.
- The disc-check patch changes three bytes at a verified site.
- The registration-free COM manifests are untested. If the game fails at
  its first `CoCreateInstance`, that is where to look; the fallback is
  copying the ten Musashi DLLs beside the exe.
- The window has not been opened - the machine this was written on has no
  tkinter.

Nothing has been done yet about resolution, input, frame rate or anything
else on the modernisation list. The ground work for those is in
[docs/NOTES.md](docs/NOTES.md).

## Working on the patcher

`docs/README.md` is the index. `tools/check.py` runs the checks; give it a
`data1.cab` (or the first 16 MB of one) and an install folder to run the
cabinet check too. `sh tools/setup-dev.sh` says what is missing.

## AI Disclaimer

LLMs are part of the toolchain here, alongside pefile, capstone and
unshield on the game's files. The scope, the disc dumps, the testing and
the debugging are human. Every change is read before it goes in. Offsets
and bytes are verified against the original before anything is written,
and the patcher refuses any file that is not an unmodified build it has
tables for. It is still a hobby project poking at a 27-year-old binary, so
expect bugs.

## Credits and licence

Rights to the game belong to SEGA. `LICENSE` (MIT) covers the patcher,
its tools and its documentation - not the game and not the bytes quoted
from it.

Bug reports and patches are welcome as issues and pull requests. For
anything else - a disc image of a build the patcher does not know, or a
question that does not fit an issue - write to pairo@segaonline.net.
