# Developing

## Setup

```bash
sh tools/setup-dev.sh          # says what is missing
cp tools/sr2-test.example ~/.sr2-test
```

Everything comes from the distribution: `python3-pyflakes` (the `lint`
check), `nasm` (rebuilds `asm/`), `python3-unicorn` (runs the stubs),
`tkinter` (the window); `python3-pefile` for the `clearsize` check and
`python3-pil` for `tools/txrdump.py`. None is needed to run the patcher.

`~/.sr2-test` names, per build, the install disc, the play disc, the
installed game and the Wine prefix: `SR2_DISC_EU`, `SR2_PLAY_EU`,
`SR2_GAME_EU`, `SR2_PFX_EU`, and `US`, `AU`, `JP` likewise.

## The loop

```
vim sr2-patcher.py              # or asm/*.asm, then python3 asm/build.py
python3 tools/check.py          # everything
tools/sr2.sh au run             # play it
```

`tools/sr2.sh BUILD ACTION`: `install [LANG]`, `rip`, `patch [KEYS...]`,
`restore`, `run`, `debug [CHANNELS]`, `show`, with the paths from
`~/.sr2-test`. `xinput` needs `noregistry` (which gives the game's own
block a file of its own and leaves `SR2.CFG` to the text) and `devices`
needs `xinput`; the patcher refuses the combinations without. `run` and `debug` go through umu (Proton) or plain wine
and leave the Wine log in `logs/`.

The mix's numbers - the effects' range and the two music offsets - are
`asm/mix.inc`, included by `mix.asm` and `music.asm`. `tools/loudness.py
GAMEDIR` measures the CD rips against the streamed music and says what
`CD_DB - STREAM_DB` makes them equally loud at equal sliders.

`python3 tools/kit.py` bundles every build's installed files, minus the
assets, with the first 16 MB of each `data1.cab`, into the gitignored
`tools/sr2-kit.tar.gz`: what the notes are written against.

## The checks

`tools/check.py` runs them all; `--list` names them, `--only a,b` picks.
The first twelve need nothing but nasm, pyflakes and Unicorn; CI
installs the first two, so it runs `tables`, `asm` and `lint` and the
Unicorn ones skip themselves there. The rest need the discs and games
and skip themselves without.

| Check | Catches |
| --- | --- |
| `tables` | a site outside the file, two patches on one byte, a replacement longer than the original, a placeholder left unfilled |
| `asm` | `asm/` edited without `asm/build.py` being run |
| `lint` | pyflakes |
| `bgrow`, `fullwin`, `altenter`, `loadhold`, `hudlast`, `frametrace`, `texrange`, `replayfree`, `wide` | those stubs under Unicorn, with the exe's routines stubbed; `tools/uctest.py` is what the tests share |
| `cab` | the disc and cabinet readers on a real dump |
| `offsets` | every original byte string in the file, every patch alone, every pair and a hundred random sets applying, the all-on result at its pinned MD5; an install older than the tables is noted, not failed |
| `music` | the music hook under Unicorn, on the build's real `MGAudio.dll` |
| `altab` | the alt-tab stub and the rewritten restore routine under Unicorn |
| `padinput`, `dinput8`, `nogeneric` | the pad annex, the DirectInput 8 create and type translation, and the device-list filter under Unicorn, on the build's real `MGInput.dll` |
| `devices` | the Device Settings page's binding under Unicorn, on the real `Options.dll` over stubbed input objects |
| `resolution` | the resolution row's init, draw and store under Unicorn, on the real `Options.dll` |
| `clearsize` | the Australian clear's two arguments under Unicorn, on the real exe |

A truncated `data1.cab` works for `cab` (`head -c 16M`). To exercise the
disc reader without a dump: `genisoimage -o sr2.iso -graft-points
DATA1.CAB=data1.head`, then `tools/iso2bin.py sr2.iso sr2.bin`.

## Adding a patch

A patch is a key in `patches()`: the file, its `(offset, original bytes,
replacement)` sites, and a transform or `None`. Exe offsets come from the
build's row in `BUILDS`; a DLL site is the same in every build. A
transform takes the image and the build name; an exe stub gets its
addresses through `EXE_MAGICS` placeholders that `exe_blob` fills from
the row. `patch()` verifies the originals, writes the sites, then runs
the transform.

Code goes in `asm/`, as a transform. The shapes:

- a blob in the file's annex, sites pointed at it with `_branch`:
  `altab`, `textcolor`, `windowed`, `altenter` in the exe; `titlebg` in
  `Title.dll`, `mixerless` in `MGAudio.dll`, `mix` in `MGSound.dll`.
  The annex is one `.sr2` section per file, appended by the first patch
  that needs it and grown by the rest (`append_section`), so any set of
  patches fits;
- a blob in a relocated DLL's annex, finding its own base: `music`,
  `borderless`, `xinput`;
- a routine rewritten in place: `restoreall`;
- plain sites plus a transform that drops relocation entries:
  `borderless`, `texrange`.

Each transform appends its own section, so any patch can be left out.
When a patch changes what it writes, update `EXPECTED` in
`tools/selftest.py`; document it in NOTES.md's table and MAP.md.

## Adding a build

A row in `BUILDS`: the fingerprints, the exe sites, the SetTextColor
sites, the import slots and the addresses. An exe stub may not name an
exe address in its source (`asm/build.py` refuses one); everything a
stub reads goes through a placeholder and the row.
`tools/discsurvey.py` gives the fingerprints; find each site by
searching the new exe for the European site's bytes with addresses and
`rel32`s masked, and read the hit back in a disassembler. `check_build`
compares the row with the exe's import table and the `call` sites, so a
wrong row fails before anything is written.

A relink of a build already known is the easy case, and the
`Japanese (MediaKite)` row is the worked example: search the new exe for every European exe site's
bytes, unmasked first, and the hits come back at the old offset or at a
constant delta from it - `0x10` back, there - which says where the code
moved and by how much. Then the row is the European one with those sites
moved, the code addresses the stubs read moved with them and the data
addresses left alone. `tools/selftest.py` on an install from the new disc
proves it: it fails on any site whose bytes are not where the row says,
and the patched DLLs come out at the MD5s the other build's row pins,
since only the exe differs.

## Reading a Wine log

`tools/sr2.sh BUILD debug` sets `WINEDEBUG=+seh,+loaddll,+mci`, or the
channels given. The last `loaddll` before an exit names the DLL whose
init failed; `err:actctx` and `80040154` are the manifests;
`seh:dispatch_exception` with its `eip` is a crash; `+debugstr` shows
what the Musashi DLLs print. An empty `music\trace` beside the tracks makes the hook
report every command it receives as `sr2 <id> <msg> <flags> <p1> <p2>
<p3>` on `+debugstr`.

`voltrace` is a patch applied only by name: five volume entry points in
the exe report their arguments as `sr2 vN this a1 a2 a3` on `+debugstr`.
Naming a diagnostic adds it to the set:

```
tools/sr2.sh eu patch voltrace
```

`frametrace` is the second diagnostic, for the frame pacing: the frame
gate logs every drawn frame to `frames.log` beside the exe - a header
with the ticks per 1/60 s, then the counters at the gate's entry, after
the blit and at its exit, the simulation steps and the gate's flags. On
either system:

```
python3 sr2-patcher.py --patch ~/games/sr2 frametrace
```

Play, quit, and `python3 tools/frames.py frames.log` prints the frame
rate, the spread of the intervals, the catch-up frames and the worst
intervals with when they happened. See NOTES.md, *Frame timing*, for
what the numbers mean.

`gltrace` is the third diagnostic, for the widescreen work: MGameGL's
`SetViewport` and `SetPerspective` report every call on `+debugstr` as
`sr2 vp L T R B cx cy r1 r2` (the rect and centre as they came, the
return address and the one a wrapper's frame above it), `sr2 vp> ...`
as they went on, `sr2 fov a W H a>` (the picture's size), `sr2 ct cx
cy cx> cy>` for `SetCentre`, `sr2 pj x y x> y>` for the projection
(floats, the first 2000) and `sr2 gp id v v>` for the parameters the
getter converts; all in hex. `tools/sr2.sh eu patch gltrace`,
then `tools/sr2.sh eu debug debugstr`.

`d3dtrace` reports every present as `sr2 p`, a frame's end, and every draw through MGameD3D's six hooked entries, the
first 60000: `sr2 d e fvf count ret x0 y0 z0`, `e` the entry (q, t, l,
i, s, f: quad, triangle, list, indexed, strip, fan), `ret` the draw's
return address - the `loaddll` lines in the same log say whose - and the
first vertex in hex, before any scaling. The menus' quads fill those
60000 before a race starts; `d3dtrace2d` instead reports only the 2D
draws that are not quads - the lists, strips and fans, which is the
HUD's text and the race's background layers - and nothing else.

## Commits

Commits are the author's own: `pairo <pairo@segaonline.net>`, no
co-author or session trailers, whatever tool wrote the change.

## Working with a patch file

Changes arrive as a `git diff`. Before making one, `git fetch` and diff
against `origin/main` as it is at that moment - a patch against an
older commit fails on every file it touches, and "already exists in
working directory" for a new file means the earlier version of the
patch was already committed. Before applying one, the tree must be
clean: `git status` empty, or `git checkout -- .` and `git clean -f`
on the files the patch adds. New files need `git add` before the
commit; `-a` does not take them.

## Investigating with a trace

Take the baseline first: a `frametrace` run of the stock configuration,
before any change, kept. Every later log is read against it. A change
made before the baseline exists cannot be told from the problem it was
meant to fix, and a change that fixes a problem the change before it
introduced looks like an improvement. One change per run; the `-key`
form gives the A/B without touching anything else. Numbers over feel:
a run that felt smoother with the same log is the same run.

## Releasing

A release is a pre-release on GitHub, made with `gh`, with the script
stamped by hand as its one download; CI only verifies, nothing builds
from the tag. In order, on a clean `main` with the checks passing:

```
sed "s/^VERSION = 'dev'/VERSION = 'v0.1.1'/" sr2-patcher.py > /tmp/sr2-patcher-v0.1.1.py
python3 /tmp/sr2-patcher-v0.1.1.py --version        # sr2-patcher v0.1.1
git tag -a v0.1.1 -m "v0.1.1"
git push origin v0.1.1
gh release create v0.1.1 --prerelease --title "v0.1.1" --notes-file notes.md /tmp/sr2-patcher-v0.1.1.py
```

The notes: *Changes*, *Requirements*, *Known issues*, plain, only what
has been seen. The tag, the release notes and the asset are three
separate things: moving the tag (`git tag -f`, `git push --force origin
refs/tags/v0.1.1`) changes neither of the others - `gh release edit
--notes-file` for the notes, `gh release upload --clobber` for a
re-stamped script. `gh release view` shows all three as they stand.

## Not there yet

- A Windows build (PyInstaller spec and the release job).
- A `gui` check under xvfb.
