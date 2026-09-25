<p align="center">
  <img src="assets/SR2PatcherLogo2.png" alt="SR2 Patcher logo" width="420" />
</p>

# SR2 Patcher

Gets *SEGA RALLY 2* (PC, 1999) running properly on a modern system.
Install it from your disc images, press a button, and it plays: no
crashes, no invisible text, no dead controller, no disc in the drive.

You also get the picture at your monitor's size and shape, the soundtrack
from files, an XInput pad you can rebind in-game, and online play with no
port forwarding. Windows 10 and 11, Wine and Proton.

<img src="https://github.com/user-attachments/assets/6b1f92c1-9f66-407a-a0a5-181b7f205aae" alt="Lancia Stratos on a coastal stage at 32:9" width="100%" />

**Work in progress.** The game plays start to finish on all four
releases, but this is a hobby project poking at a 27-year-old binary and
things will turn up. [Reporting a bug](#reporting-a-bug) says what helps.

<h4 align="center">
  <a href="#quick-start">Quick start</a> &nbsp;·&nbsp;
  <a href="#virus-warnings">Virus warnings</a> &nbsp;·&nbsp;
  <a href="#disc-images">Disc images</a> &nbsp;·&nbsp;
  <a href="#what-the-patches-do">Patches</a> &nbsp;·&nbsp;
  <a href="#widescreen">Widescreen</a> &nbsp;·&nbsp;
  <a href="#controls">Controls</a>
  <br /><br />
  <a href="#internet-play">Internet play</a> &nbsp;·&nbsp;
  <a href="#music">Music</a> &nbsp;·&nbsp;
  <a href="#builds">Builds</a> &nbsp;·&nbsp;
  <a href="#from-a-terminal">Terminal</a> &nbsp;·&nbsp;
  <a href="#reporting-a-bug">Bugs</a> &nbsp;·&nbsp;
  <a href="#known-issues">Known issues</a>
</h4>

## Quick start

**Download** `sr2-patcher-*-win.zip` from the
[latest release](https://github.com/pairomaniac/sr2-patcher/releases/latest),
unzip it anywhere and run `sr2-patcher-*.exe`; the `_internal` folder
beside it has to stay. It is unsigned, so SmartScreen warns the first
time. If a virus scanner objects, see [Virus warnings](#virus-warnings).

On Linux, or on Windows without the exe, take `-python.zip` from the same
page:

1. **Install Python** 3.8 or newer from
   [python.org](https://www.python.org/downloads/), ticking **Add
   python.exe to PATH** on the installer's first page. On Linux, see
   [From a terminal](#from-a-terminal).
2. **Unzip it** somewhere of its own; `MGNetWk.dll` has to stay in the
   `net` folder beside the script.
3. **Run it.** Double-click `sr2-patcher.py`, or `py sr2-patcher.py` from
   a terminal in its folder.

<p align="center">
  <img src="https://github.com/user-attachments/assets/4ff8c15d-4f36-4d15-83b9-e28c1a35c46f" alt="The patcher window, showing its numbered sections" width="480" />
</p>

Work through the numbered sections in order:

1. **GAME FOLDER** - where the game is, or an empty folder to put it in.
   An install of your own has to be unmodified; if yours is refused, see
   [Builds](#builds).
2. **INSTALL** - disc 1's `.cue` in **Install disc**, disc 2's in **Play
   disc**, then **Install game** and **Rip soundtrack**. Skip it if the
   game is already in the folder. See [Disc images](#disc-images) and
   [Music](#music).
3. **ESSENTIAL PATCHES** - always applied.
4. **EXTRA PATCHES** - all ticked, yours to change. The ⓘ beside each
   says what it does. Press **Apply patches**.
5. **ADD-ONS** - on Windows **dgVoodoo 2** is ticked and downloaded on
   Apply. See [Add-ons](#add-ons).

Then run `SEGA RALLY 2.exe` from that folder. **Restore original** puts
the game back.

## Virus warnings

Defender and other scanners sometimes flag the patcher: an unsigned
program that edits another program is what they warn about. To allow it
in Defender: Windows Security → Virus & threat protection → Protection
history → the entry for the file → Allow, then run it again.

Every release is built on GitHub from this repository and the build log
lists the exe's checksum. The `-python.zip` on the same page is the
script itself. The one binary the patcher installs is `MGNetWk.dll` for
[Internet play](#internet-play), compiled from the C in `net/` and
checked against a known hash before it is written.

## Disc images

The patcher reads the images itself: nothing to mount, no virtual drive.
You need both discs: the game is on the first, the music on the second.

- **Install disc** - a `.cue` with its `.bin` beside it, an `.iso`, a
  folder you have already copied the disc to, or its `data1.cab`. The
  `.cue` is the small text file, not the `.bin`.
- **Play disc** - a `.cue` with its `.bin` files. An `.iso` will not do
  here: it drops the audio tracks, and those are the music.

The game takes about 550 MB and the soundtrack about as much again.

### If you have the discs, not images

Image them once:

- **Windows** - [ImgBurn](https://www.imgburn.com) in *Read* mode, with
  the output set to **BIN/CUE** rather than ISO.
- **Linux** - `cdrdao`, then its own `toc2cue`:

  ```bash
  cdrdao read-cd --driver generic-mmc-raw --datafile sr2-disc2.bin \
      sr2-disc2.toc /dev/sr0
  toc2cue sr2-disc2.toc sr2-disc2.cue
  ```

## What the patches do

**Essential** patches fix what is broken on a modern machine and are
always applied. **Extra** patches are down to taste: unticking one takes
it back out on the next **Apply patches**. What each changes, down to
the byte, is in [docs/NOTES.md](docs/NOTES.md).

### Essential

- **No disc required** - every mode plays with nothing in the drive.
- **Skip the start-up checks** - a 1999 video card, a 640x480 16-bit
  display mode, a 16-bit desktop and, on the Australian release, Windows
  9x. Nothing today passes them.
- **Crash fixes** - on start-up, on the logo screen, and on the way out
  of the replay gallery.
- **Fix the picture after ALT+TAB** - it comes back instead of staying
  black.
- **Fix the device scan** - the white window on start: the game read
  every USB device on the machine, and modern ones choked it.
- **Windowed and borderless** - **ALT+ENTER** switches. Stock it took the
  whole screen at 640x480.
- **Text and panel fixes** - the menu text, the name you type, the team
  list and the chat were all invisible, and the team room's panels came
  out black with dgVoodoo 2.
- **Fix the HUD over the scenery** - the tachometer no longer blanks the
  lake behind it on Mountain.
- **Sound fixes** - the three volume sliders now match each other, and
  start at 6 rather than full.
- **No registry** - settings sit beside the game, so the folder can be
  copied anywhere.

### Extra

- **Native widescreen** - the game renders at your screen's size and
  shape instead of 640x480 stretched. See [Widescreen](#widescreen).
- **Music from files** - the soundtrack plays from the folder instead of
  the disc. See [Music](#music).
- **XInput gamepad support** - a modern pad works everywhere, the
  driving and menu controls rebindable in-game. See [Controls](#controls).
- **Internet play** - race anyone, no port forwarding. See
  [Internet play](#internet-play).
- **Loading screens** - the stage card is held for three seconds;
  today's machines load faster than you can read it.

### Add-ons

An add-on is an extra file beside the game rather than an edit to it,
downloaded when you press **Apply patches**.

**dgVoodoo 2** is [dege's](https://github.com/dege-diosg/dgVoodoo2)
DirectDraw on Direct3D 11. Windows' own DirectDraw refuses a picture
over 2048 a side and is slow and erratic with this game on some
machines; dgVoodoo has neither problem and waits for the display's
refresh before showing a frame. Ticked by default on Windows, off under
Wine and Proton, which have no such limit. Untick it and Apply to take
it out, your settings kept; **Restore original** takes those as well.

### Diagnostics

The collapsed **DIAGNOSTICS** section adds logging for a bug report. All
off by default, none of it changes how the game plays. What each writes
is in [docs/DEVELOPING.md](docs/DEVELOPING.md).

## Widescreen

<img src="https://github.com/user-attachments/assets/08f9bc67-2735-4285-ae23-1da9a218304a" alt="Desert stage in a Celica ST-205 at 32:9" width="100%" />

<p align="center">
  <img src="https://github.com/user-attachments/assets/8b1fdec0-f93a-4075-8fb5-f5a26d0c4daf" alt="Time Attack name entry at 16:9, its tiled background carried out to the edges" width="49.5%" />
  <img src="https://github.com/user-attachments/assets/55294acc-cc60-45c6-b8c9-b32a762380e9" alt="Jungle stage in a Peugeot 306 Maxi at 16:9" width="49.5%" />
</p>

**Options → Graphic Settings** gains an **Aspect Ratio** row - 4:3,
16:10, 16:9, 21:9, 32:9 - and a **Resolution** row listing that shape's
sizes, up to 5120x2880 at 16:9, 3840x2400 at 16:10, 5120x2160 at 21:9
and 7680x2160 at 32:9. The picture changes at the next screen.

A wide screen shows more at the sides rather than stretching the middle.
The menus and the HUD keep their shape in the centre; the title and mode
select stay 4:3, with the picture blurred behind them to fill the sides.

Two-player split screen follows the same size:

<img src="https://github.com/user-attachments/assets/68e2c826-8400-49fa-8045-b57aa1c7e766" alt="Two-player split screen at 16:9" width="100%" />

On Windows the list stops at 2048 a side without the dgVoodoo 2 add-on -
see [Known issues](#known-issues).

## Controls

An XInput pad works as it is: stick to steer, triggers for the pedals,
Start to pause. In the menus the D-pad or stick moves, A and Start
choose, and B goes back; in the multiplayer team room Back switches
between the slot list and the MENU row, as TAB does.

In a replay:

| | Pad | Keyboard 1P | Keyboard 2P |
| --- | --- | --- | --- |
| Next / previous camera | RB / LB | Up / Down | S / X |
| Turn the revolving camera; driver's or rear view; the side camera's side | Left stick | Left / Right | Z / C |
| Zoom the revolving camera | RT / LT | Page Up / Page Down | - |
| Meter on / off | Y | Insert / Delete | T / G |
| Switch the screen (2 PLAYER BATTLE, the winner) or the car watched (multiplayer) | X | TAB | TAB |
| Pause | Start | Enter | Space |

In 2 PLAYER BATTLE each player's pad drives their own half. Pause is
each player's Start as bound in Device Settings; the other replay
controls are fixed.

In the menus LB and RB stand in for Page Up and Page Down: they turn
the pages of the Records screen, and on the car select LB held from
pressing A until the car is taken picks the Stratos', Corolla's,
Impreza's, Lancer Evo VI's or ST185's other colour. In the Replay
Gallery they step the sort between MODE, CAR and DATE, as F6-F8 do.

**Options → Device Settings** is a new page showing both players'
controls, keyboard and pad side by side; press a key or a button to
rebind one. They are saved as plain text in `SR2.CFG` beside the game,
with the resolution and the network settings; delete the file for the
defaults, and the game writes it again as you change things.

<p align="center">
  <img src="https://github.com/user-attachments/assets/0d95eeed-3834-4f0a-8291-4cc210de0abb" alt="Options menu with Device Settings selected" width="49.5%" />
  <img src="https://github.com/user-attachments/assets/ff647971-3dde-47d4-b933-1600a1744af4" alt="Device Settings page listing each control's key and pad binding" width="49.5%" />
</p>

## Internet play

<p align="center">
  <img src="https://github.com/user-attachments/assets/4eeb4842-b05f-47c0-8f26-d7516f391eba" alt="Multiplayer connection screen offering INTERNET, DIRECT IP and LAN" width="480" />
</p>

The connection screen offers three rows in place of IPX, TCP/IP, modem
and serial:

- **INTERNET** - the teams open anywhere, listed as the screen opens;
  **REFRESH** asks again. Joining needs no port forwarding.
- **DIRECT IP** - type the host's address, or `host:port`. The host
  forwards UDP 47626.
- **LAN** - the local network, searched as the screen opens.

The team room, the chat, the car and course selection and the race are
the game's own. Up to four players, all on 0.7.1 or later. How it works
is in [docs/NETWORK.md](docs/NETWORK.md).

### The network log

Set `Log = 1` under `[Network]` in `SR2.CFG` beside `SEGA RALLY 2.exe`
(the patcher writes the section, both keys at 0) and the game logs
its connections, joins, refusals and drops to `logs\sr2-net.log`, with the
reason for each. When something goes wrong online, send that file from
each machine.

## Music

The soundtrack is thirteen audio tracks on the play disc, which is why
a stock install is silent without it in the drive. **Rip soundtrack**
copies them into a `music` folder beside the game (about 550 MB) and
the **Music from files** patch plays them from there.

Or from a terminal:

```bash
python3 sr2-patcher.py --rip "Sega Rally 2 (Disc 2).cue" ~/games/sr2
```

Any pressing's disc 2 will do: they all carry the same recording.

## Builds

The patcher knows the European, American and Australian releases and
the Japanese reissue, tells them apart by itself, and installs and
patches the Pentium III build of each - the one the original installer
picks on any modern CPU.

| Release | `SEGA RALLY 2.exe` | MD5 | Redump |
| --- | --- | --- | --- |
| European | 1,469,952 | `51b3da97c3c73611d3516b65bb684cb5` | EI-1183-1 |
| American | 1,472,000 | `90d1f25110781707a888475ca37e9240` | 40924-0919 |
| Australian / Japanese (Sega) | 1,754,624 | `84c95aed1b8cd8402fcff98f1687df7b` | MK-85078-40 |
| Japanese (DigiCube, MediaKite) | 1,469,952 | `5c0242443ea289d3d461b15eddb63388` | DWRPD-00081 |

Sega's own 1999 Japanese disc (HCJ-0145) carries the same contents as
the Australian one, so that row covers both; the Japanese row covers
DigiCube's and MediaKite's reissues, whose discs are also the same.

Before writing anything the patcher checks every file it knows by size
and checksum. If one does not match, nothing is touched and a line names
it - usually a modified or half-patched install; install afresh from the
disc.

Each patched file gets a `.bak` beside it. Apply starts from those every
time, so patching twice is the same as patching once, and **Restore
original** puts them back.

## From a terminal

Everything the window does, without the window:

```bash
python3 sr2-patcher.py --install "Sega Rally 2 (Disc 1).cue" ~/games/sr2 English
python3 sr2-patcher.py --rip "Sega Rally 2 (Disc 2).cue" ~/games/sr2
python3 sr2-patcher.py --patch ~/games/sr2
python3 sr2-patcher.py --restore ~/games/sr2
```

`--patch` applies every patch unless you name some: by name to apply
only those (listed at the top of `sr2-patcher.py`), or with a leading
minus to leave them out, as in `--patch ~/games/sr2 -music`. Leaving a
patch out also leaves out whatever needs it. The `dgvoodoo` add-on is on
by default on Windows; `-dgvoodoo` leaves it out, naming it puts it in
elsewhere.

On Linux the terminal commands need nothing extra; the window needs Tk:

```bash
sudo apt install python3-tk        # Debian, Ubuntu, Mint
sudo dnf install python3-tkinter   # Fedora
sudo pacman -S tk                  # Arch
```

Under Wine or Proton the patched folder runs as it is: the manifests
beside the exe replace the installer's COM registration.

## Reporting a bug

Open an [issue](https://github.com/pairomaniac/sr2-patcher/issues) with
the release (the window names it), Windows or Wine/Proton, and what you
were doing just before. For a crash on Windows, Event Viewer → Windows
Logs → Application names the faulting module and offset. For anything
online, `logs\sr2-net.log` from each machine
([The network log](#the-network-log)). For a disc image of a release
the patcher does not know, or anything that does not fit an issue:
pairo@segaonline.net.

## Known issues

- **Windows: error 80004005 at start.** One cause is fixed. If it still
  happens, tick **Direct3D bring-up** under DIAGNOSTICS, Apply, start the
  game, and send `logs\d3dinit.log` with the card and driver.
- **A LAN team nobody can see.** The game uses UDP port 47626; if
  something else has it on the host (a second copy of the game, say),
  LAN search cannot find that host. DIRECT IP and INTERNET still work.
- **Choppy on a 144 or 165 Hz display.** The game runs at a fixed 60
  frames a second. On Windows, dgVoodoo 2 now waits for the display's
  refresh; if you installed it with an earlier version, delete
  `MUSASHI\dgVoodoo.conf` in the game folder and press **Apply patches**
  to get that. 60 frames still cannot land evenly on a refresh that is
  not a multiple of 60: a 120 or 60 Hz desktop, or G-SYNC or FreeSync
  with windowed mode enabled, makes it even.

## Planned

In no particular order:

- **Proper controller prompts** - right now it's the usual keyboard labels.
- **Controller rumble** - which the Dreamcast version does have.
- **Fleshing out the online functionality** - this one's a long term goal,
  but something I am interested in.

## Working on the patcher

[docs/](docs/README.md) covers how the game works and how the patches
are made; `tools/check.py` runs every check. The Windows build is
`sr2-patcher.spec`, run on a tag by
[.github/workflows/build.yml](.github/workflows/build.yml).

## AI disclaimer

Much of the assembly and the documentation was written with an LLM.
The reverse engineering was not: the addresses and behaviour each
patch relies on come from tracing and debugging the running game with
pefile, capstone, unshield, Unicorn, Wine's channels and WinDbg, and
the LLM writes to that brief. This edits a few hundred bytes of an
existing binary, not a reimplementation of it.

Everything it writes is read line by line before it goes in, and every
patch is play-tested on every supported build before it ships. Offsets
are verified against the originals before anything is written, and the
patcher refuses any file that is not an unmodified build it has tables
for.

## Credits and licence

Successor to
[v-on-patcher](https://github.com/pairomaniac/v-on-patcher). The logo
and icon are the work of SirRockEmSockEm. The DigiCube and MediaKite
support is by [chmcl95](https://github.com/chmcl95). The game is SEGA's.
`LICENSE` (MIT) covers the patcher, its tools and its documentation, not
the game or the bytes quoted from it.
