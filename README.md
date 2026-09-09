# SR2 Patcher

Runs *SEGA RALLY 2* (PC, 1999) on a modern system from your own disc
dumps: one folder with the game and its music in it, no installer, no
registry, no disc in the drive. Works under Wine and Proton; Windows is
untested.

## Quick start

Run `sr2-patcher.py` with Python 3 and fill the window in from the top:
the `.cue` of the install disc, the `.cue` of the play disc, an empty
folder (about 800 MB), the language. **Install**, then **Rip
soundtrack**, then run `SEGA RALLY 2.exe` from that folder.

**Patch** applies the fixes to an existing install, the patcher's or the
original installer's Pentium III one; **Restore original** takes them
out.

From a terminal:

```
python3 sr2-patcher.py --install "Sega Rally 2 (Disc 1).cue" ~/games/sr2 English
python3 sr2-patcher.py --rip "Sega Rally 2 (Disc 2).cue" ~/games/sr2
python3 sr2-patcher.py --patch ~/games/sr2
python3 sr2-patcher.py --restore ~/games/sr2
```

## What you need

- Both discs as bin/cue. One bin per track or a single bin; an `.iso`
  does for the install disc but not the play disc, which is where the
  audio tracks are.
- Python 3, with tkinter for the window.

Nothing is mounted and nothing is written outside the folder you choose.
The patcher installs the Pentium III build, which any CPU since can run,
and refuses anything that is not an unmodified copy of it.

## Fixes

| Fix | Without it |
| --- | --- |
| **Windows 9x check** | The Australian release refuses to start. |
| **No disc required** | An "insert the play disc" box, and a menu with everything but multiplayer greyed out. |
| **Startup crash** | Under Proton the game closes before its window appears. |
| **ALT+TAB** | Switching away and back leaves a blank screen or a world with no textures. |
| **Missing lettering** | The black lettering on the 2D screens - SELECT GAME, SELECT CAR - drawn as outlines. |
| **Invisible lobby text** | In multiplayer, the name you type, the team list and the chat never appear. |
| **Borderless fullscreen** | The game takes the display over at 640x480 and comes back from ALT+TAB on the wrong monitor. It now runs in a borderless window on the monitor it starts on, 4:3, black bars. |
| **ALT+ENTER** | Toggles a framed window you can move, resize or maximise. |
| **Music** | Silence: the music was audio tracks on the play disc. The patcher rips them to `music\` and the game plays them from there. |
| **The mix** | The three sliders followed three different curves - effects in dB, CD music in amplitude, streamed music across a range of its own - so a step meant something different on each; the Australian release also ran its effects at a fraction of theirs. All three follow one curve now, 3.5 dB a step, topping out at −8 dB - the old 7 - with the CD music 7 dB above the effects and the streamed music 3 dB above. The Australian release no longer needs a CD volume control on the sound card. |

Everything else is the game as it shipped.

## Status

Work in progress. Installs, starts, plays with music, survives ALT+TAB,
under Wine and Proton (via umu). Supported: the European, American and
Australian releases, Pentium III build, told apart by the exe. The
Japanese release has not been seen.

Planned: native widescreen with split-screen to match, controller
configuration and XInput (the game runs on its defaults for now), online
play with a lobby, frame timing, a Windows exe of the patcher.

## Working on it

[docs/](docs/README.md) covers how the game works and how the patches
are made; `tools/check.py` runs the checks.

## AI disclaimer

LLMs are part of the toolchain, alongside pefile, capstone, unshield,
Unicorn and Wine's tracing. Scope, testing and debugging are human; every
change is read before it goes in and played before it ships. Offsets are
verified against the originals before anything is written. A hobby
project on a 27-year-old binary: expect bugs.

## Credits and licence

Successor to [v-on-patcher](https://github.com/pairomaniac/v-on-patcher).
The game is SEGA's. `LICENSE` (MIT) covers the patcher, its tools and
its documentation, not the game or the bytes quoted from it.

Issues and pull requests are welcome. For a disc image of a build the
patcher does not know, or anything that does not fit an issue:
pairo@segaonline.net.
