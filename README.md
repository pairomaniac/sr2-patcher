# SR2 Patcher

Gets *SEGA RALLY 2* (PC, 1999) running on a modern PC. It installs the
game straight from your disc images - no installer, no registry, no disc
in the drive - fixes the crashes, keeps the picture through ALT+TAB,
brings the music back, makes an XInput pad work out of the box with the
controls rebindable in-game, and renders at your monitor's size.
Windows 10 and 11, Wine and Proton.

**Work in progress.** The game plays start to finish on the European,
American and Australian releases; MediaKite's Japanese rerelease installs
and patches like them but has not been played through yet. This is a
hobby project poking at a 27-year-old binary, and things will turn up.
[Reporting a bug](#reporting-a-bug) says what helps.

**Status.** The latest release is
[v0.2](https://github.com/pairomaniac/sr2-patcher/releases), which adds
native widescreen; the script here is that release plus whatever has
landed since.

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
apart automatically, and **this fork adds a fourth**: MediaKite's
Japanese rerelease, MKW-166. That one is not upstream's - see
[The Japanese releases](#the-japanese-releases). Japan's three other
pressings (Sega's own HCJ-0145, DigiCube's DWRPD-00081 and SPB-040, the
disc I-O DATA bundled with a graphics card) are unknown builds here, and
a dump of any of them would be welcome. Sega's own updates for the
Japanese release are documented in `docs/NOTES.md`; the European release
already carries their final files.

## Builds

The patcher knows the European, American, Australian and Japanese
(MediaKite) releases, each in its Pentium III build - the one the
original installer chose on any CPU of the last twenty-five years, and
the one Install always picks. It tells them apart by the exe's checksum
and then checks the thirteen files of that build by size and checksum
before it writes anything: the nine it patches and the four other files
the Pentium III set replaced. If one doesn't match you get a line naming
it, such as `MUSASHI\MGAudio.dll is not the European build's`, and
nothing is touched.
That means a modified game, a previous patcher's work, or a mixed install;
the fix is to install afresh from the disc.

Each patched file gets a `.bak` beside it, the untouched original. Patch
starts from those every time, so patching twice is the same as once, and
**Restore original** is just putting them back.

## The Japanese releases

**The MediaKite build is this fork's, not upstream's.** Upstream
([pairomaniac/sr2-patcher](https://github.com/pairomaniac/sr2-patcher))
carries the European, American and Australian rows only, and holds the
four Japanese pressings back until a verified dump of one turns up. That
is a sound rule: its three rows are checked against Redump dumps, and
Redump has no MKW-166 sample at all - none as of 20 September 2026 - so
"verified" is not a state this disc can reach at the moment.

This fork adds the row anyway, from one image of an MKW-166 disc, and
says so plainly rather than implying upstream's blessing. What stands
behind it is the disc itself: the exe is the European one relinked
sixteen bytes shorter, every one of its patch sites was matched byte for
byte in that exe before the row went in, the other twelve fingerprinted
files are the European bytes, and the whole of `tools/check.py` passes
against an install made from the disc, which has also been played. The
details are in [docs/NOTES.md](docs/NOTES.md), *The Japanese releases*.

So: a problem with the MediaKite build belongs in this fork's issues,
not upstream's. Japan's other three pressings are not here either way.

## Playing

The game runs in a borderless window on the monitor it starts on, 4:3
with black bars until you pick a widescreen size: **Options → Graphic
Settings** has an **Aspect Ratio** row - 4:3, 16:10, 16:9, 21:9, 32:9 -
and its **Resolution** row lists that aspect's sizes, 640x480 to
5120x1440; the picture takes the new size at the next screen change.
The race shows more at the sides; the menus and HUD keep their shape in
the middle, with the tiled backgrounds carried out to the edges and the
picture screens - the title, the mode select - kept 4:3 with the
picture itself stretched, motion-blurred and dimmed behind them to fill
the sides; the loading, game-over and logo screens, pictures on a plain
background, get that background. **ALT+ENTER**
switches to a framed
window you can move, resize or maximise. ALT+TAB works either way.

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
| **ALT+TAB** | Switching away and back leaves a blank screen. |
| **Borderless window** | The game takes over the display at 640x480 and comes back from ALT+TAB on the wrong monitor. |
| **ALT+ENTER** | No windowed mode at all. |
| **Missing lettering** | The black lettering on the 2D screens - SELECT GAME, SELECT CAR - drawn as outlines. |
| **Invisible lobby text** | In multiplayer, the name you type, the team list and the chat never appear. |
| **Music** | Silence: the music was audio tracks on the play disc. The patcher rips them to `music\` and the game plays them from there. |
| **The mix** | The three sliders each followed their own curve - effects in dB, CD music in amplitude, streamed music across a range of its own - so a step meant something different on each, and the Australian release ran its effects at a fraction of the others'. All three now follow one curve, 3.5 dB a step, and the two musics are measured against each other so equal sliders are equally loud. |
| **Gamepad** | Pads are DirectInput only, set up in a Control Panel applet that no longer installs; an XInput pad does nothing. |
| **Legacy DirectInput** | The game's input goes through Windows' legacy `dinput.dll`, whose scan of every attached HID device hangs some starts on a white window (RGB controllers, some keyboards). It now goes through `dinput8.dll`, the same calls on the same objects, and the HID devices that are neither keyboard, mouse nor controller - LED controllers, a receiver's spare collections - are left out of the game's device list rather than opened and polled. |
| **Widescreen** | 640x480 stretched to the monitor. The game renders at the size you choose, with the field of view widened to match and the 2D scaled to the middle, the race HUD anchored to a 16:9 frame (the picture's edges at 16:9, a centred 16:9 on anything wider, 4:3 as it was), tiled backgrounds carried to the edges and the picture screens given side bars of the picture itself, stretched and motion-blurred; the choice is kept as `[Display]` / `Resolution` in `SR2.CFG`. |
| **Device Settings** | No way to see or change the controls from inside the game. |
| **Gauge over the lake** | On Mountain the tachometer's plate blanks the water behind it: the lake is drawn after the HUD and fails the depth test under the plate. The HUD is now drawn after it. |
| **Credits** | The ten-year championship's credits on a wide screen: the replay window rendered beside its black frame, and the black left the picture showing at the sides. Both in the 4:3 box now. |
| **Loading screens** | The stage's card - its artwork and name - is gone the moment the course has loaded, well under a second on a machine of today. It stays at least three seconds. |

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
those (the names are listed at the top of `sr2-patcher.py`), or with a
leading minus to leave them out, as in `--patch ~/games/sr2 -music`.
Leaving a patch out also leaves out whatever needs it; `windowed` and
`borderless` are the game's mode and cannot be left out.

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
which release you have (European, American, Australian, Japanese
MediaKite), whether you are on Windows or Wine/Proton, and what you were
doing just before. For a crash on Windows, the entry under Event Viewer →
Windows Logs → Application names the faulting module and offset, which is
usually enough to find it. For a disc image of a release the patcher
doesn't know, or anything that doesn't fit an issue:
pairo@segaonline.net.

## Known issues

- **Split screen: no lake on Mountain** - the game does not draw the
  water in split screen (its draw skips itself there); the same on the
  Dreamcast. Not a patcher issue.
- **Windows: a start that hangs on a white window** with the keyboard
  connected was traced, on one machine, to the MSI Mystic Light HID
  device and Windows' legacy DirectInput. The `dinput8` patch takes the
  game off that DLL; if a start still hangs with it on, please report it
  with the device.
- **Windows: `Failed to initialize. Error code 80004005`** at start, on
  two machines so far (one AMD, one NVIDIA). The game's own DirectDraw
  bring-up fails; a nearly stock build - only `nodisc` and `nocardwarn`
  applied - fails the same way, so it is not the patching. On the NVIDIA
  machine it was deterministic and Windows' **8/16-bit DWM mitigation**
  cleared it: a `.cmd` beside the exe with

  ```
  set __COMPAT_LAYER=DWM8And16BitMitigation
  start "" "%~dp0SEGA RALLY 2.exe"
  ```

  starts the game every time and writes nothing to the registry. The
  flag is not one the Compatibility tab offers; to have it for good
  instead, add the exe's full path as a value name under
  `HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers`
  with the data `~ DWM8And16BitMitigation`. Why a machine needs it, and
  why one start can succeed before the rest fail, is not known; please
  report it with the card and driver.

## Planned

In no particular order, none of it promised:

- **A Windows exe** of the patcher, so Python isn't needed - built on
  GitHub from this repository, as v-on-patcher's is.
- **Online play** - the game's own multiplayer is DirectPlay over IPX,
  serial and modem. The aim is an internet lobby with a code to share and
  no port forwarding, as v-on-patcher has.
- **Japan's other three pressings** - Sega's HCJ-0145, DigiCube's and the
  I-O DATA bundle - once a dump of one turns up. The European exe is
  Sega's UPDATE250 exe byte for byte, so the 2.50-patched original is
  probably a small row; the unpatched original and DigiCube's are
  unknown builds.

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
