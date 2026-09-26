# Developing sr2-patcher

This document says how to build the patcher, what to run before pushing,
and what each check is for. [README.md](../README.md) says how to use the
patcher, [NOTES.md](NOTES.md) says what the patches do, and
[asm/](../asm/) holds the assembly sources.

## The two layers

```
asm/*.asm  ──nasm──►  hex strings in sr2-patcher.py  ──►  the one file a player downloads
 you edit             asm/build.py writes these
```

`sr2-patcher.py` cannot read `asm/` at runtime. So `asm/build.py`
assembles the sources and writes the machine code into the script as hex
text between GENERATED markers. **Never edit a blob by hand.** The next
build run overwrites it.

## Setup, once

```bash
sh tools/setup-dev.sh          # says what is missing and the install line
cp tools/sr2-test.example ~/.sr2-test
```

Every package comes from the distribution; there is no venv and no pip.
None of them is needed to run the patcher, only to work on it.

| Package | For |
| --- | --- |
| `nasm` | rebuilding `asm/` |
| `python3-pyflakes` | the `lint` check |
| `python3-unicorn` | the checks that run the stubs |
| `python3-pil`, `fonts-urw-base35` | `tools/txrdump.py`, `tools/assets.py`; `tools/labels.py` and its check |
| `gcc-mingw-w64-i686` | `net/build.py`, the network DLL |
| a C compiler (`cc`) | the `nettest` check |
| `tkinter` | the window |
| `xvfb` | the `gui` check |

`~/.sr2-test` names four paths per build: the install disc, the play
disc, the installed game and the Wine prefix. For the European build the
variables are `SR2_DISC_EU`, `SR2_PLAY_EU`, `SR2_GAME_EU` and
`SR2_PFX_EU`. The other builds use the same names with `US`, `AU`, `JP`
(Sega's own disc) or `JP_MK` (the DigiCube and MediaKite reissue) in
place of `EU`. The example file describes each variable. A variable that
is in the file but left empty shows as N/A in `check.py` and in `sr2.sh
BUILD show`; it is not counted as a skip.

## Daily loop

```bash
vim sr2-patcher.py              # or asm/*.asm, then python3 asm/build.py
python3 tools/check.py          # everything
tools/sr2.sh au run             # play it
```

`tools/sr2.sh BUILD ACTION` works on one build, with the paths taken
from `~/.sr2-test`. BUILD is `eu`, `us`, `au`, `jp` or `jp_mk`. It can
also be `all`, which runs the action on every build that has a game
folder; `run` and `debug` do not take `all`. ACTION is `run` when it is
left out:

| Action | Does |
| --- | --- |
| `install [LANG]` | installs from the disc and patches; the language is English unless LANG is given |
| `rip` | rips the play disc's music into the game folder |
| `patch [KEYS]` | patches the installed game; with KEYS, a comma-separated list, only those patches are applied |
| `restore` | puts the original files back |
| `run` | runs the game under umu (Proton) or plain wine; the Wine log goes to `logs/` |
| `debug [CHANNELS]` | the same as `run`, with `WINEDEBUG=+seh,+loaddll,+mci` or the channels given |
| `show` | prints the paths it would use |

Some patches need others, and the patcher refuses a set that names a
patch without what it needs:

- `xinput` needs `noregistry`. `noregistry` gives the game's own
  settings block a file of its own, `SR2.DSP`, and leaves `SR2.CFG` to
  the controls text that `xinput` writes.
- `devices` needs `xinput`.
- `nogeneric` needs `dinput8`.
- `music` needs `cdlevel`.
- `lobby` and `netplay` need each other.
- `starting` needs `lobby`.
- `widescreen2d`, `widescreen3d` and `resolution` need `widescreen`.
- Among the diagnostics, `gltrace` needs `widescreen3d`, `d3dtrace` and
  `d3dtrace2d` need `widescreen2d`, and `netlog` needs `netplay`.

`windowed` and `borderless` are always in the set.

Two more tools serve the daily work:

- `tools/loudness.py GAMEDIR` measures the CD rips against the streamed
  music and says what value of `CD_DB - STREAM_DB` makes them equally
  loud at equal slider settings. The mix's numbers - the effects' range
  and the two music offsets - live in `asm/mix.inc`, which `mix.asm` and
  `music.asm` include.
- `python3 tools/kit.py` bundles every build's installed files into the
  gitignored `tools/sr2-kit.tar.gz`. It leaves out the assets, except
  `BINDATA\connect\button` and `IP_ENTRY`, and adds the first 16 MB of
  each `data1.cab`. The notes are written against this bundle.

## The checks

`tools/check.py` runs every check. `--list` names them and `--only a,b`
picks some. There are 37. The first 22, down to `gui`, need only nasm,
pyflakes, Unicorn, Pillow and the URW fonts, tkinter, xvfb and a C
compiler, and CI runs them. Every test that maps a PE image does so
through `tools/uctest.py`. The last fifteen need the discs and the
installed games, and they skip without them. `devices` also needs nasm,
because it reads nasm's listing. A tool that cannot run exits 77 and is
reported SKIP, never OK. `clearsize` applies to the Australian build only
and skips on the others.

| Check | Catches |
| --- | --- |
| `tables` | a site outside the file, two patches on one byte, a replacement longer than the original, or a placeholder left unfilled |
| `asm` | `asm/` edited without `asm/build.py` being run |
| `labels` | `tools/labels.py` edited without being run. The labels are rendered here and compared with the baked ones; a rasteriser's few pixels of difference are allowed. Skips without Pillow and the font |
| `net` | `net/` edited without `net/build.py` being run |
| `nettest` | the network core. A host and five guests run over loopback with a third of the datagrams dropped, and the test covers joins, names, the reliable and unreliable classes, ordering, closed sessions and slots, leaving, silence, the host going away, an oversized reliable datagram, and a welcome with a seat past the table. It also checks the name lookup on its own thread. Then a directory server is started for the run (a failure to start fails the check), a session is found through it, and one guest joins directly and one through the relay. Skips without a C compiler |
| `directorytest` | the directory server's list limit per address, the token, the registration cookie, and N and X, with a hand-set clock |
| `lint` | pyflakes |
| `bgrow`, `wide`, `fullwin`, `altenter`, `starting`, `loadhold`, `padmenu`, `pagepad`, `hudlast`, `frametrace`, `d3dinit`, `texrange`, `replayfree` | those stubs under Unicorn, with the exe's routines stubbed. `wide` runs both the European and the American exe blobs. `tools/uctest.py` holds what these tests share |
| `cab` | the disc and cabinet readers on a real dump |
| `dgvoodoo` | the dgVoodoo 2 add-on's download and unpack, against a made-up release |
| `gui` | the window driven headlessly: every widget is reachable, the palette's contrast is measured, and the feature rows are compared with the patch keys. Skips without a display |
| `offsets` | the tables against a real install. Every original byte string is in the file; every patch applies alone, in every pair, in a hundred random sets, and with the diagnostics in sets of their own; and the all-on result has its pinned MD5, both with the full resolution table and with the capped one. An install older than the tables is noted, not failed |
| `music` | the music hook under Unicorn, on the build's real `MGAudio.dll` |
| `altab` | the alt-tab stub and the rewritten restore routine under Unicorn |
| `padinput`, `dinput8`, `nogeneric` | the pad annex, the DirectInput 8 create and type translation, and the device-list filter, each under Unicorn on the build's real `MGInput.dll` |
| `devices` | the Device Settings page's binding under Unicorn, on the real `Options.dll` over stubbed input objects |
| `resolution` | the resolution row's init, draw and store under Unicorn, on the real `Options.dll` |
| `lobby` | the connection screen's confirm under Unicorn, on the real exe: the list opens searching for INTERNET and LAN, and not for DIRECT IP |
| `buttons` | the SEARCH button composed from the install's stock `showteam_*` and `create_*` files, and the IP entry popup composed from its stock file, both against pinned digests. A file the install lacks gives a note |
| `ipcheck` | the lobby entries on the real exe under Unicorn: the IP entry's address check, the caps by field, CTRL+V kept within the cap, and the status line's stub |
| `clearsize` | the Australian clear's two arguments under Unicorn, on the real exe |
| `sortpad` | the gallery's sort site on the real `ReplayGallery.dll`, relocated, with the annex's poll stubbed |
| `replaypad` | the replay controls' update under Unicorn, on the real exe patched with `replaypad` alone, with the input objects and the annex's poll stubbed |

A truncated `data1.cab` (`head -c 16M`) is enough for `cab`, as long as
it keeps the `.cab` name. To exercise the disc reader without a dump,
wrap the truncated cab in an image:

```bash
genisoimage -o sr2.iso -graft-points DATA1.CAB=data1.head
python3 tools/iso2bin.py sr2.iso sr2.bin
```

A pre-push hook catches a forgotten build before CI does:

```bash
cat > .git/hooks/pre-push <<'EOF'
#!/bin/sh
exec python3 tools/check.py
EOF
chmod +x .git/hooks/pre-push
```

## Adding a patch

A patch is a key in `patches()`. Its entry names the file, lists its
sites as `(offset, original bytes, replacement)`, and names a transform
or `None`. Exe offsets come from the build's row in `BUILDS`; a DLL site
is the same in every build. A transform takes the image and the build
name. An exe stub gets its addresses through `EXE_MAGICS` placeholders,
which `exe_blob` fills from the row. `patch()` verifies the original
bytes, writes the sites, and then runs the transform.

Code goes in `asm/` and is installed by a transform. These are the
shapes a transform takes:

| Shape | Examples |
| --- | --- |
| a blob in the file's annex, with the sites pointed at it by `_branch` | `altab`, `textcolor`, `windowed`, `altenter`, `starting`, `loadhold`, `padmenu`, `replaypad`, `pagepad` in the exe; `titlebg` in `Title.dll`, `mixerless` in `MGAudio.dll`, `mix` in `MGSound.dll` |
| a blob in a relocated DLL's annex, which finds its own base | `music`, `borderless`, `xinput` |
| a routine rewritten in place | `restoreall` |
| plain sites, plus a transform that drops relocation entries | `borderless`, `texrange` |
| a whole file replaced from a baked build | `netplay`; `lobby` also writes art and `MPDATA.DAT` beside the exe |

The annex is one `.sr2` section per file. The first patch that needs it
appends it, and the rest grow it (`append_section`), so any set of
patches fits. Each transform appends its own data, so any patch can be
left out.

When a patch changes what it writes, update `EXPECTED` in
`tools/selftest.py`. For the exe or `Options.dll` also update
`EXPECTED_CAPPED`, which is pinned under the capped resolution table.
Then document the change in NOTES.md's table and in MAP.md.

## Adding a build

A build is a row in `BUILDS`: the fingerprints, the exe sites, the
SetTextColor sites, the import slots and the addresses. Where a build's
file differs in shape, the row carries the original bytes or the extra
site; examples are the older `MGInput.dll`'s static polls (`kbdpoll`),
its six-byte type read, and the exe's `pagepad` site. Nothing in the
code tests the build's name. No stub may name an exe address in its
source, and `asm/build.py` refuses one that does; everything a stub
reads goes through a placeholder and the row.

`tools/discsurvey.py` gives the fingerprints. To find each site, search
the new exe for the European site's bytes with the addresses and
`rel32`s masked, and read the hit back in a disassembler. `check_build`
compares the row with the exe's import table and the `call` sites, so a
wrong row fails before anything is written.

A rebuild of a known exe is the easy case, and `Japanese (DigiCube,
MediaKite)` is the example. Search it for each European site's bytes
unmasked first. The hits come back at the old offset or at a constant
delta, which shows where code moved. Data addresses stay put if the
sections do. Then run `tools/selftest.py` on an install from the disc;
it checks every site and pins the result.

## Reading a Wine log

`tools/sr2.sh BUILD debug` sets `WINEDEBUG=+seh,+loaddll,+mci`, or the
channels given. These lines in the log are the ones to look for:

| Line | Means |
| --- | --- |
| the last `loaddll` before an exit | the DLL whose init failed |
| `err:actctx`, `80040154` | the manifests |
| `seh:dispatch_exception` with its `eip` | a crash |
| `+debugstr` | what the Musashi DLLs and the diagnostics print |

## Diagnostics

A diagnostic is a patch that is applied only when it is named, or when
its box in the window is ticked. Naming one adds it to the set; the word
`logs` names all of them but `d3dtrace2d`; and a plain patch with no
diagnostic named takes them out again:

```
tools/sr2.sh eu patch voltrace
python3 sr2-patcher.py --patch ~/games/sr2 frametrace
```

`voltrace` and `gltrace` report through `+debugstr` (`tools/sr2.sh eu
debug debugstr`, or DebugView on Windows). The rest write files under
`logs\`. `netlog` is not a patch: it sets `Log = 1` in `SR2.CFG`, which
turns on the netplay DLL's own log (net/README.md).

### voltrace

Five volume entry points in the exe report their arguments as `sr2 vN
this a1 a2 a3`. The sites are known in the European and DigiCube/MediaKite
builds; on the other builds the box does nothing.

An empty file `music\trace` beside the tracks makes the music hook report
in the same way. The hook reports every command it receives as `sr2 <id>
<msg> <flags> <p1> <p2> <p3>`, and the worker reports every operation it
performs as `sr2 op <op> <arg> <result> <last DirectSound HRESULT>`. The
values are in decimal.

### frametrace

This diagnostic is for the frame pacing. The frame gate logs every drawn
frame to `logs\frames.log` in the game folder. The file starts with a
header giving the ticks per 1/60 s; then each line holds the counter at
the gate's entry, after the blit and at its exit, the simulation steps,
and the gate's flags. Play, quit, and run

```
python3 tools/frames.py ~/games/sr2/logs/frames.log
```

which prints the frame rate, the spread of the intervals, the catch-up
frames, and the worst intervals with the time each happened. NOTES.md,
*Frame timing*, says what the numbers mean.

Take a baseline of the stock configuration first and read every later
log against it. Make one change per run; the `-key` form gives an A/B
comparison without touching anything else.

### gltrace

This diagnostic is for the widescreen work. It reports MGameGL's viewport
and projection calls, all in hex.

| Line | Reports |
| --- | --- |
| `sr2 vp L T R B cx cy r1 r2` | `SetViewport` as called: the rect and the centre, then `r1`, the return address, and `r2`, the return address one stack frame up, past a wrapper |
| `sr2 vp> ...` | the same call as it went on after conversion |
| `sr2 fov a W H a>` | `SetPerspective`: the angle, the picture's size, and the angle as it went on |
| `sr2 ct cx cy cx> cy>` | `SetCentre`: the centre as called and as it went on |
| `sr2 pj x y x> y>` | the projection, as floats; only the first 2000 are reported |
| `sr2 gp id v v>` | the parameters the getter converts: the id, the value read, the value returned |

### d3dtrace, d3dtrace2d

`d3dtrace` reports every present as `sr2 p`, which marks a frame's end,
and every draw through MGameD3D's six hooked entries, up to the first
400000. The lines go to `OutputDebugString` (DebugView on Windows,
`WINEDEBUG` under Wine) and to `logs\d3dtrace.log` in the game folder:

```
sr2 d e fvf count ret x0 y0 z0 tex kind
```

`e` is the entry: q, t, l, i, s or f for quad, triangle, list, indexed,
strip or fan. `ret` is the draw's return address; the `loaddll` lines in
the same log say which module it is in. Then come the first vertex in
hex, before any scaling, and the selected texture and its kind. The
menus' quads fill those 400000 lines in a couple of minutes.
`d3dtrace2d` instead reports only the 2D draws that are not quads - the
lists, strips and fans, which are the HUD's text and the race's
background layers - and nothing else. That is enough for a race and its
results rather than one lap.

Two more lines serve the side bars (WIDESCREEN.md, *The side bars*):

| Line | Reports |
| --- | --- |
| `sr2 b why tex kind xmin xmax ymin ymax` | every quad that reaches the bar's decision. `why` is 1 for not a quad, 2 for shorter than 160, 3 for no texture selected, 4 for a texture that is not a picture, and 5 for the bar drawn |
| `sr2 t why slot flags size first bad left kind` | every texture create. `why` is 1 for past the table, 2 for paletted or a render target, 3 for no pixels, 4 for a transparent pixel, and 5 for the kind kept |
| `sr2 l hr ddraw surface` | the lobby's surface create |
| `sr2 x hr this source flags L T R B [l t r b]` | every blit sent to the lobby's surface, as it went: the result, the two surfaces, the flags, the destination rect, and the source rect if there is one |
| `sr2 s surface hr flags w h pf bpp caps pixel` | after each blit, one line for the source and one for the destination: `Lock`'s result, the description's flags, size, pixel format flags, bit count and caps, and the pixel at (0, 240), which is 0 on a surface with no such row |

### d3dinit

This diagnostic is for a "Failed to initialize" box. Every step of
MGameD3D's bring-up - the DirectDraw object, the cooperative level and
the window or display mode, the surfaces, the device, the textures -
appends `<site> <hr> <w>x<h> <tw>x<th>` to `logs\d3dinit.log` in the
game folder. The fields are the store's RVA in `MGameD3D.dll`, its
HRESULT, the picture size in force, and the device's largest texture
from its caps, which is 0 until the device enumeration. The last line
with a negative `hr` names the call that failed, and MAP.md's `Init` row
says which function each site is in. The device enumeration's sites
(`0x1a34` to `0x1be3`) and the texture format enumeration's (`0x3b6d`,
`0x3bc7`) are in the list too. After site `0x20c5` one more line is
written:

```
fmt <slots> <chosen> <not565>
```

`slots` has one bit per texture format slot the enumeration filled; bit
0 is the first of the 13 slots, at `0x10012594`. `chosen` is the slot
the DLL picked, and `not565` is its flag for a chosen format other than
R5G6B5. The command is the same on either system:

```
python3 sr2-patcher.py --patch ~/games/sr2 d3dinit
```

## Commits

Commits are the author's own, `pairo <pairo@segaonline.net>`, whatever
tool wrote the change. They carry no co-author or session trailers.

### Working with a patch file

Changes arrive as `git format-patch` files made against `origin/main` as
it is at that moment. A patch made against an older commit fails on
every file it touches. Apply them with `git am` on a clean tree.

## Releasing

The tag does the work. Pushing one runs the checks, builds the exe, and
creates the release with both zips attached. Releases before v0.4.0 were
marked pre-releases; from v0.4.0 on they are not. On a clean `main` with
the checks passing:

```
git tag -a v0.4.0 -m "v0.4.0"
git push origin v0.4.0
```

`VERSION` stays `dev` in the repository. The workflow stamps it with the
tag name less its `v`, so the exe's filename, its Windows file properties
and `--version` all say the tag's number; the zips carry the `v`. A push
that is not a tag builds the same two zips as an artifact named with the
short SHA.

Then write the notes over the generated ones. The sections are
*Changes*, *Requirements* and *Known issues*, in plain words, and they
say only what has been seen.

```
gh release edit v0.4.0 --notes-file notes.md
```

Moving the tag (`git tag -f`, then `git push --force origin
refs/tags/v0.4.0`) re-runs the build and re-uploads the zips, but leaves
the notes as they are. `gh release view` shows the notes and both zips.

Before a release, put the exe through VirusTotal by hand and read the
verdicts. The build log prints the exe's checksum and a lookup link.

## The window

`run_tk` and the tables above it are the whole of the window. `FEATURES`
is what the window lists and what the README describes: one row per
thing somebody would say the patcher does, with the patch keys that
thing takes. `group_keys` turns the ticked boxes into the key set that
`patch` is given, and drops any key whose `NEEDS` went out with an
unticked box. `--selfcheck` holds the two together: every patch is in
exactly one row, and every diagnostic has a label.

`tools/assets.py` bakes `assets/SR2PatcherLogo2.png` and
`assets/SR2PatcherIcon.png` into the script as the logo and the window
icon, and writes `assets/icon.ico` for the exe. Run it after changing
the artwork. Never edit the blob by hand.

`tools/guitest.py` drives the window under xvfb. It checks what each
button is offered for, which cards start open, that every description
opens, and that the disc and folder probes run off the window's thread.
It skips when there is no display; CI installs xvfb. Its first pass
needs no display: it measures every pair of `PALETTE` colours that
carries meaning against the contrast WCAG asks for, which is 4.5:1 for
text, 3:1 for a border or a tick, and 1.25:1 between each surface and
the one behind it. The colours were quantised out of the box art, the
Stratos watercolour and the cabinet. To change one, pick a new colour
from the artwork and then measure it. The band behind the logo is an
image, because the canvas does not antialias; it is redrawn once a
resize has stopped.

The window opens `LINE_CAP` lines of its own text tall; 48 lines puts the
heading of the last numbered card on screen. `winfo_screenheight`
reports every monitor together, so it serves only as the upper bound.
`_settle_height` re-measures the window for the first half second after
it is mapped, because nothing measured before that can be trusted. Then
it stops, so the window can be dragged.

## The Windows build

`sr2-patcher.spec` is the whole build. The version comes out of the
script's `VERSION` line, `net/MGNetWk.dll` goes in as data, and the
result is a one-dir bundle: the exe beside an `_internal` folder. Fewer
scanners object to that than to a one-file exe.

    pip install pyinstaller
    pyinstaller sr2-patcher.spec

The `windows` job in
[.github/workflows/build.yml](../.github/workflows/build.yml) runs it on
every push to main and on a tag, after `verify` passes. The job does four
things beyond the build. It builds PyInstaller's bootloader from source
rather than taking the wheel's, because every PyInstaller exe shares the
wheel's bootloader and scanners know it. It stamps the version from the
tag, or from the short SHA. It checks that tkinter, the certifi CA list
and the netplay DLL are in the bundle. And it runs the exe's
`--selfcheck`, which catches an over-eager entry in the spec's
`EXCLUDES` among the modules the tables import. On a tag the job also
uploads both zips to the release page.
