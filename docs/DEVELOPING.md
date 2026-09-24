# Developing sr2-patcher

How to build, what to run before pushing, and what each check is for.
For using the patcher see [README.md](../README.md); for what the patches
do see [NOTES.md](NOTES.md); for the assembly sources see
[asm/](../asm/).

## The two layers

```
asm/*.asm  ──nasm──►  hex strings in sr2-patcher.py  ──►  the one file a player downloads
 you edit             asm/build.py writes these
```

`sr2-patcher.py` cannot read `asm/` at runtime, so the machine code is
baked in as text between GENERATED markers by `asm/build.py`. **Never
edit a blob by hand**; the next build run discards it.

## Setup, once

```bash
sh tools/setup-dev.sh          # says what is missing and the install line
cp tools/sr2-test.example ~/.sr2-test
```

Everything comes from the distribution; no venv, no pip. None of it is
needed to run the patcher.

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

`~/.sr2-test` names, per build, the install disc, the play disc, the
installed game and the Wine prefix: `SR2_DISC_EU`, `SR2_PLAY_EU`,
`SR2_GAME_EU`, `SR2_PFX_EU`, and `US`, `AU`, `JP` (Sega's own disc) and
`JP_MK` (the DigiCube and MediaKite reissue) likewise; the example file
describes each. One left empty shows as N/A in `check.py` and `sr2.sh
BUILD show`, not as a skip.

## Daily loop

```bash
vim sr2-patcher.py              # or asm/*.asm, then python3 asm/build.py
python3 tools/check.py          # everything
tools/sr2.sh au run             # play it
```

`tools/sr2.sh BUILD ACTION` works on one build with the paths from
`~/.sr2-test`; BUILD is `eu`, `us`, `au`, `jp` or `jp_mk`, and ACTION
is `run` when left out:

| Action | Does |
| --- | --- |
| `install [LANG]` | install from the disc and patch; English unless given |
| `rip` | rip the play disc's music into the game folder |
| `patch [KEYS]` | patch the installed game; KEYS a comma list to apply only those |
| `restore` | put the original files back |
| `run` | run under umu (Proton) or plain wine; the Wine log goes to `logs/` |
| `debug [CHANNELS]` | the same with `WINEDEBUG=+seh,+loaddll,+mci`, or the channels given |
| `show` | print the paths it would use |

Some patches need others, and the patcher refuses a set without them:
`xinput` needs `noregistry` (which gives the game's own block a file of
its own and leaves `SR2.CFG` to the text), `devices` needs `xinput`,
`nogeneric` needs `dinput8`, `music` needs `cdlevel`, `lobby` and
`netplay` need each other, and the three other widescreen patches need
`widescreen`. Among the diagnostics `gltrace` needs `widescreen3d`,
`d3dtrace` and `d3dtrace2d` `widescreen2d`. `windowed` and `borderless`
are always in.

Two more tools for the daily work:

- `tools/loudness.py GAMEDIR` measures the CD rips against the streamed
  music and says what `CD_DB - STREAM_DB` makes them equally loud at
  equal sliders. The mix's numbers - the effects' range and the two
  music offsets - are `asm/mix.inc`, included by `mix.asm` and
  `music.asm`.
- `python3 tools/kit.py` bundles every build's installed files, minus
  the assets, with the first 16 MB of each `data1.cab`, into the
  gitignored `tools/sr2-kit.tar.gz`: what the notes are written against.

## The checks

`tools/check.py` runs them all; `--list` names them, `--only a,b` picks.
There are 33. The first 21, down to `gui`, need only nasm, pyflakes,
Unicorn, Pillow and the URW fonts, tkinter, xvfb and a C compiler, and
CI runs them; every test that maps a PE image does it through
`tools/uctest.py`. The last twelve need the discs and the games and skip
without them; `devices` also needs nasm, whose listing it reads. A tool
that cannot run exits 77 and is reported SKIP, never OK. `clearsize` is
Australian only and says so on the other builds.

| Check | Catches |
| --- | --- |
| `tables` | a site outside the file, two patches on one byte, a replacement longer than the original, a placeholder left unfilled |
| `asm` | `asm/` edited without `asm/build.py` being run |
| `labels` | `tools/labels.py` edited without being run: the labels rendered here against the baked ones, a rasteriser's few pixels of difference allowed (skips without Pillow and the font) |
| `net` | `net/` edited without `net/build.py` being run |
| `nettest` | the network core: a host and five guests over loopback, a third of the datagrams dropped - joins, names, the reliable and unreliable classes, ordering, closed sessions and slots, leaving, silence, the host going, an oversized reliable datagram and a welcome with a seat past the table; the name lookup on its thread; then a directory server started for the run (a failure to start fails the check), a session found through it, a direct join and a relayed one (skips without a C compiler) |
| `directorytest` | the directory server's list limit per address, the token, the registration cookie, N and X, with a hand-set clock |
| `lint` | pyflakes |
| `bgrow`, `wide`, `fullwin`, `altenter`, `loadhold`, `padmenu`, `pagepad`, `hudlast`, `frametrace`, `d3dinit`, `texrange`, `replayfree` | those stubs under Unicorn, with the exe's routines stubbed (`wide` runs the European and the American exe blobs); `tools/uctest.py` is what the tests share |
| `cab` | the disc and cabinet readers on a real dump |
| `dgvoodoo` | the dgVoodoo 2 add-on's download and unpack against a made-up release |
| `gui` | the window driven headlessly: the widgets reachable, the palette measured, the feature rows against the patch keys (skips without a display) |
| `offsets` | every original byte string in the file, every patch alone, every pair, a hundred random sets and the diagnostics in sets of their own applying, the all-on result at its pinned MD5 with the full resolution table and with the capped one; an install older than the tables is noted, not failed |
| `music` | the music hook under Unicorn, on the build's real `MGAudio.dll` |
| `altab` | the alt-tab stub and the rewritten restore routine under Unicorn |
| `padinput`, `dinput8`, `nogeneric` | the pad annex, the DirectInput 8 create and type translation, and the device-list filter under Unicorn, on the build's real `MGInput.dll` |
| `devices` | the Device Settings page's binding under Unicorn, on the real `Options.dll` over stubbed input objects |
| `resolution` | the resolution row's init, draw and store under Unicorn, on the real `Options.dll` |
| `clearsize` | the Australian clear's two arguments under Unicorn, on the real exe |
| `sortpad` | the gallery's sort site on the real `ReplayGallery.dll`, relocated, with the annex's poll stubbed |
| `replaypad` | the replay controls' update under Unicorn, on the real exe patched with `replaypad` alone, the input objects and the annex's poll stubbed |

A truncated `data1.cab` works for `cab` (`head -c 16M`), as long as it
keeps the `.cab` name. To exercise the disc reader without a dump:

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

A patch is a key in `patches()`: the file, its `(offset, original bytes,
replacement)` sites, and a transform or `None`. Exe offsets come from the
build's row in `BUILDS`; a DLL site is the same in every build. A
transform takes the image and the build name; an exe stub gets its
addresses through `EXE_MAGICS` placeholders that `exe_blob` fills from
the row. `patch()` verifies the originals, writes the sites, then runs
the transform.

Code goes in `asm/`, as a transform. The shapes:

| Shape | Examples |
| --- | --- |
| a blob in the file's annex, sites pointed at it with `_branch` | `altab`, `textcolor`, `windowed`, `altenter`, `loadhold`, `padmenu`, `replaypad`, `pagepad` in the exe; `titlebg` in `Title.dll`, `mixerless` in `MGAudio.dll`, `mix` in `MGSound.dll` |
| a blob in a relocated DLL's annex, finding its own base | `music`, `borderless`, `xinput` |
| a routine rewritten in place | `restoreall` |
| plain sites plus a transform that drops relocation entries | `borderless`, `texrange` |
| a whole file replaced from a baked build | `netplay`; `lobby` also writes art and `MPDATA.DAT` beside the exe |

The annex is one `.sr2` section per file, appended by the first patch
that needs it and grown by the rest (`append_section`), so any set of
patches fits; each transform appends its own, so any patch can be left
out.

When a patch changes what it writes, update `EXPECTED` in
`tools/selftest.py`; document it in NOTES.md's table and MAP.md.

## Adding a build

A row in `BUILDS`: the fingerprints, the exe sites, the SetTextColor
sites, the import slots and the addresses. An exe stub may not name an
exe address in its source (`asm/build.py` refuses one); everything a
stub reads goes through a placeholder and the row.

`tools/discsurvey.py` gives the fingerprints. Find each site by searching
the new exe for the European site's bytes with addresses and `rel32`s
masked, and read the hit back in a disassembler. `check_build` compares
the row with the exe's import table and the `call` sites, so a wrong row
fails before anything is written.

A rebuild of a known exe is the easy case; `Japanese (DigiCube,
MediaKite)` is the example. Search it for each European site's bytes
unmasked first: the hits come back at the old offset or at a constant
delta, which shows where code moved. Data addresses stay put if the
sections do. `tools/selftest.py` on an install from the disc then checks
every site and pins the result.

## Reading a Wine log

`tools/sr2.sh BUILD debug` sets `WINEDEBUG=+seh,+loaddll,+mci`, or the
channels given. In the log:

| Line | Means |
| --- | --- |
| the last `loaddll` before an exit | the DLL whose init failed |
| `err:actctx`, `80040154` | the manifests |
| `seh:dispatch_exception` with its `eip` | a crash |
| `+debugstr` | what the Musashi DLLs and the diagnostics print |

## Diagnostics

A diagnostic is a patch applied only by name, or by its box in the
window; naming one adds it to the set:

```
tools/sr2.sh eu patch voltrace
python3 sr2-patcher.py --patch ~/games/sr2 frametrace
```

All but `frametrace` and `d3dinit` report on `+debugstr`: `tools/sr2.sh
eu debug debugstr`.

### voltrace

Five volume entry points in the exe report their arguments as `sr2 vN
this a1 a2 a3`. Sited in the European build only.

An empty `music\trace` beside the tracks does the same for the music
hook: every command it receives as `sr2 <id> <msg> <flags> <p1> <p2>
<p3>`, and the worker every operation it answers as `sr2 op <op> <arg>
<result> <last DirectSound HRESULT>`, in decimal.

### frametrace

For the frame pacing. The frame gate logs every drawn frame to
`logs\\frames.log` in the game folder: a header with the ticks per 1/60 s, then
the counters at the gate's entry, after the blit and at its exit, the
simulation steps and the gate's flags. Play, quit, and:

```
python3 tools/frames.py ~/games/sr2/logs/frames.log
```

prints the frame rate, the spread of the intervals, the catch-up frames
and the worst intervals with when they happened. NOTES.md, *Frame
timing*, says what the numbers mean.

Take a baseline of the stock configuration first and read every later
log against it. One change per run; the `-key` form gives the A/B
without touching anything else.

### gltrace

For the widescreen work: MGameGL's viewport and projection calls, all in
hex.

| Line | Reports |
| --- | --- |
| `sr2 vp L T R B cx cy r1 r2` | `SetViewport` as called: the rect and centre, the return address and the one a wrapper's frame above it |
| `sr2 vp> ...` | the same as it went on |
| `sr2 fov a W H a>` | `SetPerspective`: the angle, the picture's size, the angle as it went on |
| `sr2 ct cx cy cx> cy>` | `SetCentre` |
| `sr2 pj x y x> y>` | the projection, floats, the first 2000 |
| `sr2 gp id v v>` | the parameters the getter converts |

### d3dtrace, d3dtrace2d

Every present as `sr2 p`, a frame's end, and every draw through
MGameD3D's six hooked entries, the first 400000, to `OutputDebugString`
(DebugView on Windows, `WINEDEBUG` under Wine) and to
`logs\\d3dtrace.log` in the game folder:

```
sr2 d e fvf count ret x0 y0 z0 tex kind
```

`e` is the entry (q, t, l, i, s, f: quad, triangle, list, indexed,
strip, fan), `ret` the draw's return address - the `loaddll` lines in
the same log say whose - then the first vertex in hex before any
scaling, and the selected texture and its kind. The menus' quads fill
those 400000 in a couple of minutes; `d3dtrace2d` instead reports only
the 2D draws that are not quads - the lists, strips and fans, which is
the HUD's text and the race's background layers - and nothing else,
which is a race and its results rather than a lap of one.

Two more lines, for the side bars (WIDESCREEN.md, *The side bars*):

| Line | Reports |
| --- | --- |
| `sr2 b why tex kind xmin xmax ymin ymax` | every quad that reaches the bar's decision; why 1 not a quad, 2 shorter than 160, 3 no texture selected, 4 the texture is not a picture, 5 the bar drawn |
| `sr2 t why slot flags size first bad left kind` | every texture create; why 1 past the table, 2 paletted or a render target, 3 no pixels, 4 a transparent pixel, 5 the kind kept |
| `sr2 l hr ddraw surface` | the lobby's surface create |
| `sr2 x hr this source flags L T R B [l t r b]` | every blit sent to the lobby's surface, as it went: the result, the two surfaces, the flags, the destination rect and the source rect if one |
| `sr2 s surface hr flags w h pf bpp caps pixel` | after each, the source and then the destination: `Lock`'s result, the description's flags, size, pixel format flags, bit count and caps, and the pixel at (0, 240), 0 on a surface with no such row |

### d3dinit

For a "Failed to initialize" box. Every step of MGameD3D's bring-up -
the DirectDraw object, the cooperative level and the window or display
mode, the surfaces, the device, the textures - appends `<site> <hr>
<w>x<h> <tw>x<th>` to `logs\\d3dinit.log` in the game folder: the store's RVA in
`MGameD3D.dll`, its HRESULT, the picture size in force and the device's
largest texture from its caps (0 until the device enumeration). The last
line with a negative `hr` is the call that failed; MAP.md's `Init` row
says which function each site is in. The device enumeration's sites
(`0x1a34` to `0x1be3`) and the texture format enumeration's (`0x3b6d`,
`0x3bc7`) are in the list too, and after site `0x20c5` one more line:

```
fmt <slots> <chosen> <not565>
```

`slots` has a bit per texture format slot the enumeration filled (bit 0
the first of the 13, `0x10012594` on), `chosen` the slot the DLL picked
and `not565` its flag for a chosen format other than R5G6B5. On either
system:

```
python3 sr2-patcher.py --patch ~/games/sr2 d3dinit
```

## Commits

Commits are the author's own: `pairo <pairo@segaonline.net>`, no
co-author or session trailers, whatever tool wrote the change.

### Working with a patch file

Changes arrive as `git format-patch` files against `origin/main` as it
is at that moment; a patch against an older commit fails on every file
it touches. Apply them with `git am` on a clean tree.

## Releasing

The tag does the work: pushing one runs the checks, builds the exe and
creates the release with both zips on it. Releases before v0.4.0 were
marked pre-releases; from v0.4.0 they are not. On a clean `main` with the
checks passing:

```
git tag -a v0.4.0 -m "v0.4.0"
git push origin v0.4.0
```

`VERSION` stays `dev` in the repository; the workflow stamps it from the
tag name less its `v`, so the tag, the exe's filename, its Windows file
properties and `--version` cannot disagree. A push that is not a tag
builds the same two zips as an artifact named with the short SHA.

Then write the notes over the generated ones: *Changes*, *Requirements*,
*Known issues*, plain, only what has been seen.

```
gh release edit v0.4.0 --notes-file notes.md
```

Moving the tag (`git tag -f`, `git push --force origin
refs/tags/v0.4.0`) re-runs the build and re-uploads the zips but leaves
the notes as they are; `gh release view` shows all three.

Before a release, put the exe through VirusTotal by hand and read the
verdicts; the build log prints its checksum and a lookup link.

## The window

`run_tk` and the tables above it are the whole of it: `FEATURES` is what
the window lists and the README describes - one row per thing somebody
would say the patcher does, with the patch keys it takes - and
`group_keys` turns the boxes into the key set `patch` is given, dropping
anything whose `NEEDS` went with it. `--selfcheck` holds the two
together: every patch in exactly one row, every diagnostic with a label.

`tools/assets.py` bakes `assets/SR2PatcherLogo2.png` and
`assets/SR2PatcherIcon.png` into the script as the logo and the window
icon, and writes `assets/icon.ico` for the exe. Run it after changing
the artwork; never edit the blob by hand.

`tools/guitest.py` drives the window under xvfb: what each button is
offered for, which cards start open, that every description opens, and
that the disc and folder probes run off the window's thread. It skips
with no display; CI installs xvfb. Its first pass needs no display: every
pair of `PALETTE` colours that carries meaning against the contrast WCAG
asks - 4.5:1 for text, 3:1 for a border or a tick, 1.25:1 between each
surface and the one behind it. The colours are quantised out of the box
art, the Stratos watercolour and the cabinet; pick a new one from the
artwork and then measure it. The band behind the logo is an image, since
the canvas does not antialias, redrawn once a resize has stopped.

The window opens `LINE_CAP` lines of its own text tall - 48 puts the
heading of the last numbered card on screen. `winfo_screenheight` is
every monitor together, so it is only the upper bound. `_settle_height`
re-measures for the first half second after the window is mapped, since
nothing measured before that can be trusted, and then stops so the
window can be dragged.

## The Windows build

`sr2-patcher.spec` is the whole build: the version comes out of the
script's `VERSION` line, `net/MGNetWk.dll` goes in as data, and the
result is a one-dir bundle - the exe beside an `_internal` folder, which
fewer scanners object to than a one-file exe.

    pip install pyinstaller
    pyinstaller sr2-patcher.spec

The `windows` job in
[.github/workflows/build.yml](../.github/workflows/build.yml) runs it on
every push to main and on a tag, after `verify` passes. It builds
PyInstaller's bootloader from source rather than taking the wheel's,
which every PyInstaller exe shares and scanners know; stamps the version
from the tag, or the short SHA; checks that tkinter, the certifi CA list
and the netplay DLL are in the bundle; and runs the exe's `--selfcheck`,
which catches an over-eager entry in the spec's `EXCLUDES` among the
modules the tables import. A tag also uploads both zips to the release
page.
