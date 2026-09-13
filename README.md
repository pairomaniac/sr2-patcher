# SR2 Patcher

Gets *SEGA RALLY 2* (PC, 1999) running on a modern PC. It installs the
game straight from your disc images - no installer, no registry, no disc
in the drive - fixes the crashes, keeps the picture through ALT+TAB,
brings the music back, and makes an XInput pad work out of the box.
Windows 10 and 11, Wine and Proton.

**Work in progress.** The game plays start to finish on all three
releases, but this is a hobby project poking at a 27-year-old binary, and
things will turn up. [Reporting a bug](#reporting-a-bug) says what helps.

<h4 align="center">
  <a href="#quick-start">Quick start</a> &nbsp;·&nbsp;
  <a href="#disc-images">Disc images</a> &nbsp;·&nbsp;
  <a href="#builds">Builds</a> &nbsp;·&nbsp;
  <a href="#playing">Playing</a> &nbsp;·&nbsp;
  <a href="#what-the-patches-do">Patches</a> &nbsp;·&nbsp;
  <a href="#from-a-terminal">Terminal</a> &nbsp;·&nbsp;
  <a href="#reporting-a-bug">Bugs</a> &nbsp;·&nbsp;
  <a href="#known-issues">Known issues</a> &nbsp;·&nbsp;
  <a href="#planned">Planned</a>
</h4>

## Quick start

There is no exe yet. The patcher is a single Python script with a window.

1. **Install Python** from [python.org](https://www.python.org/downloads/),
   3.8 or newer. On the installer's first page, tick **Add python.exe to
   PATH**. Tk, which draws the window, comes with it. On Linux, see
   [From a terminal](#from-a-terminal).
2. **Get the script.** Download
   [`sr2-patcher.py`](https://raw.githubusercontent.com/pairomaniac/sr2-patcher/main/sr2-patcher.py)
   (right-click, *Save link as*), or use *Code → Download ZIP* on this
   page. That one file is all you need.
3. **Run it.** Double-click `sr2-patcher.py`, or open a terminal in its
   folder and run `py sr2-patcher.py`.
4. **Fill in the window from the top:**
   - **Disc 1 image** - the install disc's `.cue` (or `.iso`).
   - **Disc 2 cue** - the play disc's `.cue`. The music lives here.
   - **Install to** - an empty folder. The game takes about 800 MB.
   - **Language** - one of the six the disc carries.
5. **Install**, then **Rip soundtrack**. The pane at the bottom reports
   progress; each takes a minute or two. Install applies every patch as
   it goes.
6. Run `SEGA RALLY 2.exe` from that folder.

Already have the game installed from the original discs? Point
**Install to** at it and press **Patch**; put the play disc's `.cue` in
**Disc 2 cue** and press **Rip soundtrack** for the music. Only an
unmodified Pentium III install is accepted; see [Builds](#builds).
**Restore original** puts the game's own files back if you change your
mind.

## Disc images

The patcher reads the images itself. Nothing to mount, no virtual drive.

- **Disc 1**, the install disc: a `.cue` with its `.bin` beside it, or an
  `.iso`. The `.cue` is the small text file, not the `.bin`.
- **Disc 2**, the play disc: a `.cue` with its `.bin` file or files. An
  `.iso` won't do here - it drops the audio tracks, and those are the
  music.

If you have the discs but no images, image them once:

- **Windows** - [ImgBurn](https://www.imgburn.com) in *Read* mode, with the
  output set to **BIN/CUE** rather than ISO.
- **Linux** - `cdrdao`, then its own `toc2cue`:

  ```bash
  cdrdao read-cd --driver generic-mmc-raw --datafile sr2-disc2.bin sr2-disc2.toc /dev/sr0
  toc2cue sr2-disc2.toc sr2-disc2.cue
  ```

You need both discs: the game is on the first, the music on the second.
The European, American and Australian releases are supported and told
apart automatically. The Japanese rerelease is next in line. The original
Japanese pressing has never been seen, and a disc image of it would be
welcome.

## Builds

The patcher knows the European, American and Australian releases, each in
its Pentium III build - the one the original installer chose on any CPU
of the last twenty-five years, and the one Install always picks. It tells
them apart by the exe's checksum and then checks the thirteen files of
that build by size and checksum before it writes anything: the eight it
patches and the five other files the Pentium III set replaced. If one
doesn't match you get a line naming it, such as
`MUSASHI\MGAudio.dll is not the European build's`, and nothing is touched.
That means a modified game, a previous patcher's work, or a mixed install;
the fix is to install afresh from the disc.

Each patched file gets a `.bak` beside it, the untouched original. Patch
starts from those every time, so patching twice is the same as once, and
**Restore original** is just putting them back.

## Playing

The game runs in a borderless window on the monitor it starts on, 4:3
with black bars. **ALT+ENTER** switches to a framed window you can move,
resize or maximise. ALT+TAB works either way.

An XInput pad works as it is: stick to steer, triggers for the pedals,
A and B through the menus, Start to pause. **Options → Device Settings**
shows both players' controls, keyboard and pad side by side; press a key
or button to rebind any of them. The controls are saved as plain text in
`SR2.CFG` next to the game.

The music plays from the `music\` folder, ripped from the play disc. The
three volume sliders now share one scale, so equal settings are equally
loud.

## What the patches do

**Install** and **Patch** apply every patch; there is nothing to tick.
The offsets and internals are in [docs/NOTES.md](docs/NOTES.md).

| Patch | Without it |
| --- | --- |
| **No disc required** | An "insert the play disc" box, and a menu with everything but multiplayer greyed out. |
| **Windows 9x check** | The Australian release refuses to start. |
| **Video card warning** | An OK/Cancel box on every start saying your card isn't certified, judged against a 1999 list and 4 MB of video memory. |
| **Startup crash** | Under Proton, the game closes before its window appears. |
| **Crash after the logos** | On Windows, sometimes: the logo screen asks the renderer to release texture −128, a read past its table that lands on whatever the heap happens to hold. |
| **Crash after saving a replay** | On Windows, back at the menu: the replay gallery frees a race's replay that belongs to another module, and the heap since Windows 8 ends the process for it. |
| **ALT+TAB** | Switching away and back leaves a blank screen, or a world with no textures. |
| **Borderless window** | The game takes over the display at 640x480 and comes back from ALT+TAB on the wrong monitor. |
| **ALT+ENTER** | No windowed mode at all. |
| **Missing lettering** | The black lettering on the 2D screens - SELECT GAME, SELECT CAR - drawn as outlines. |
| **Invisible lobby text** | In multiplayer, the name you type, the team list and the chat never appear. |
| **Music** | Silence: the music was audio tracks on the play disc. The patcher rips them to `music\` and the game plays them from there. |
| **The mix** | The three sliders each followed their own curve - effects in dB, CD music in amplitude, streamed music across a range of its own - so a step meant something different on each, and the Australian release ran its effects at a fraction of the others'. All three now follow one curve, 3.5 dB a step, and the two musics are measured against each other so equal sliders are equally loud. |
| **Gamepad** | Pads are DirectInput only, set up in a Control Panel applet that no longer installs; an XInput pad does nothing. |
| **Device Settings** | No way to see or change the controls from inside the game. |

Everything else is the game as it shipped.

## From a terminal

Everything the window does, without the window:

```
python3 sr2-patcher.py --install "Sega Rally 2 (Disc 1).cue" ~/games/sr2 English
python3 sr2-patcher.py --rip "Sega Rally 2 (Disc 2).cue" ~/games/sr2
python3 sr2-patcher.py --patch ~/games/sr2
python3 sr2-patcher.py --restore ~/games/sr2
```

`--patch` applies every patch unless you name some: by name to apply only
those (the names are in [docs/NOTES.md](docs/NOTES.md)'s table), or with
a leading minus to leave them out, as in `--patch ~/games/sr2
-borderless`. Leaving a patch out also leaves out whatever needs it.

On Linux the terminal commands need nothing extra; the window needs Tk:

```bash
sudo apt install python3-tk        # Debian, Ubuntu, Mint
sudo dnf install python3-tkinter   # Fedora
sudo pacman -S tk                  # Arch
```

Under Wine or Proton the patched folder runs as it is. The manifests
beside the exe stand in for the COM registration the installer used to
do.

## Reporting a bug

Open an [issue](https://github.com/pairomaniac/sr2-patcher/issues). Say
which release you have (European, American, Australian), whether you are
on Windows or Wine/Proton, and what you were doing just before. For a
crash on Windows, the entry under Event Viewer → Windows Logs →
Application names the faulting module and offset, which is usually enough
to find it. For a disc image of a release the patcher doesn't know, or
anything that doesn't fit an issue: pairo@segaonline.net.

## Known issues

- **Frame drops on Windows** - hitches when a lot is going on, or at
  random. Not yet researched. The first suspect is frame pacing: the
  present no longer waits for the display, so the pace is set by the
  game's own timer. See *Planned*.
- **Car shadows** render wrongly at some angles.
- **One start with the borderless window** failed with error code
  80004005 and hasn't done so since. If it happens to you, please report
  it.

## Planned

In no particular order, none of it promised:

- **A Windows exe** of the patcher, so Python isn't needed - built on
  GitHub from this repository, as v-on-patcher's is.
- **Native widescreen** - rendering at 1920x1080 instead of 640x480
  stretched, with the split-screen modes to match.
- **Online play** - the game's own multiplayer is DirectPlay over IPX,
  serial and modem. The aim is an internet lobby with a code to share and
  no port forwarding, as v-on-patcher has.
- **Frame timing** - how the game paces its frames and steps its physics
  hasn't been looked at. The original waited for the display's vertical
  blank; the borderless present waits for nothing, so the game's own
  timer sets the pace. This is where the frame drops will be looked for.
- **The Japanese release** - the rerelease's disc image is to hand but
  hasn't been surveyed yet; if its exe is one of the three known builds,
  only the language groups are new. The original pressing has never been
  seen.

## Working on it

[docs/](docs/README.md) covers how the game works and how the patches are
made; `tools/check.py` runs every check.

## AI disclaimer

LLMs are part of the toolchain, alongside pefile, capstone, unshield,
Unicorn, Wine's tracing and WinDbg on the running game. Scope, testing and
debugging are human: every change is read before it goes in and played
before it ships. Offsets are verified against the originals before
anything is written, and the patcher refuses any file that isn't an
unmodified build it has tables for.

## Credits and licence

Successor to [v-on-patcher](https://github.com/pairomaniac/v-on-patcher).
The game is SEGA's. `LICENSE` (MIT) covers the patcher, its tools and its
documentation, not the game or the bytes quoted from it.
