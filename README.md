# SR2 Patcher

Gets *SEGA RALLY 2* (PC, 1999) running on a modern system from your own
disc dumps. No original installer, no registry, no disc in the drive: one
folder with the game in it, the music included, and a handful of fixes so
it starts, survives ALT+TAB and plays its soundtrack.

Runs under Wine and Proton today; Windows is untested. See [Status](#status).

<h4 align="center">
  <a href="#quick-start">Quick start</a> &nbsp;·&nbsp;
  <a href="#what-you-need">What you need</a> &nbsp;·&nbsp;
  <a href="#what-the-patcher-fixes">Fixes</a> &nbsp;·&nbsp;
  <a href="#music">Music</a> &nbsp;·&nbsp;
  <a href="#status">Status</a>
</h4>

## Quick start

Run `sr2-patcher.py` with Python 3. A window opens; fill it in from the
top:

1. **Disc 1 image** - the `.cue` of your install disc dump.
2. **Disc 2 cue** - the `.cue` of your play disc dump.
3. **Install to** - an empty folder. About 800 MB with the music.
4. **Language** - which manual, help pages and in-game messages to
   install.
5. **Install**, then **Rip soundtrack**.

Then run `SEGA RALLY 2.exe` from that folder. Under Wine or Proton, point
your launcher at it as you would any other game.

If you already have the game installed - by the patcher, or by the
original installer as a Pentium III install - **Patch** applies the fixes
to that folder, and **Restore original** takes them back out.

The same from a terminal:

```
python3 sr2-patcher.py --install "Sega Rally 2 (Disc 1).cue" ~/games/sr2 English
python3 sr2-patcher.py --rip "Sega Rally 2 (Disc 2).cue" ~/games/sr2
python3 sr2-patcher.py --patch ~/games/sr2
python3 sr2-patcher.py --restore ~/games/sr2
```

## What you need

- **Both discs as bin/cue.** The install disc for the game, the play disc
  for the music. Redump-style dumps with one bin per track are fine; so is
  a single bin. A plain `.iso` works for the install disc, but not for the
  play disc, since an ISO has no audio tracks.
- **Python 3**, with tkinter for the window. The command line needs
  nothing else.

The patcher reads the images directly: nothing is mounted, and nothing is
written outside the folder you choose. It installs the Pentium III build
of the game, which every CPU made since can run, and refuses anything
that is not an unmodified copy of it.

## What the patcher fixes

| Fix | What you'd see without it |
| --- | --- |
| **No disc required** | An "insert the play disc" box at startup, and a menu with everything but multiplayer greyed out. The game now finds everything in its own folder. |
| **Startup crash** | Under Proton the game closes before its window appears. A renderer bug that Proton's DirectDraw does not forgive. |
| **Survive ALT+TAB** | Switching away and back leaves a blank screen, or the world with no textures. The game now restores its display when it regains focus, and keeps its textures where they cannot be lost. |
| **Missing lettering** | The SELECT GAME and SELECT CAR headings, and other black text on the 2D screens, drawn as hollow outlines. Black in those textures read as transparent on modern DirectX and Wine. |
| **Music from files** | Silence, because the music was audio tracks on the play disc. The game now plays it from the files the patcher rips. |

Everything else is the game as it shipped. Resolution, controls and
frame rate are on the list; see [Status](#status).

## Music

**Rip soundtrack** copies the thirteen audio tracks off the play disc dump
into `music\` beside the game, as plain WAV files (230 MB). The game plays
them wherever it used to play the disc. Without that folder it behaves as
it did with no disc: silent, but otherwise fine.

One thing does not carry over: the in-game BGM volume slider drove the CD
volume on old sound cards and has no effect on the files. Set the volume
in the system mixer.

## Status

Installs, starts, plays with music, survives ALT+TAB - under Wine and
under Proton (via umu, e.g. Faugus). Windows has not been tried; the
patched game should run there as well, and if it does not, an issue with
what happens is welcome.

Not done yet: resolution above 640x480, controller configuration (the
original Control Panel item is gone, the game runs on its defaults), and
frame timing. The controls can still be set in the game's own Options.

Supported: the European release, Pentium III build - the one the original
installer picked on any Pentium III or later. The exact files it expects
are listed in [docs/NOTES.md](docs/NOTES.md), *Builds*. Other releases
would need their own tables; a disc dump of one is the way to get there.

## Working on the patcher

Everything about how the game works inside and how the patches are made
is under [docs/](docs/README.md). `tools/check.py` runs the checks.

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

Successor to [v-on-patcher](https://github.com/pairomaniac/v-on-patcher),
in spirit and design. Rights to the game belong to SEGA. `LICENSE` (MIT)
covers the patcher, its tools and its documentation - not the game and
not the bytes quoted from it.

Bug reports and patches are welcome as issues and pull requests. For
anything else - a disc image of a build the patcher does not know, or a
question that does not fit an issue - write to pairo@segaonline.net.
