# Developing sr2-patcher

How to run the checks and what each is for. For using the patcher see
[README.md](../README.md); for how the game works see [NOTES.md](NOTES.md);
for the assembly sources see [asm/](../asm/README.md).

## Setup, once

```bash
sh tools/setup-dev.sh          # says what is missing and the install line
cp tools/sr2-test.example ~/.sr2-test
```

Everything comes from the distribution - no venv, nothing from pip.
`python3-pyflakes` is the `lint` check, `nasm` rebuilds `asm/` and is the
`asm` check, `python3-unicorn` runs the stubs, `tkinter` is the window.
None is needed to run the patcher.

`~/.sr2-test` names, per build, the install disc, the play disc, the
installed game and the Wine prefix - `SR2_DISC_EU`, `SR2_PLAY_EU`,
`SR2_GAME_EU`, `SR2_PFX_EU`, and `US`, `AU` likewise. The example
describes every variable. The file stays on your machine.

## The loop

```
vim sr2-patcher.py                  # or asm/*.asm, then asm/build.py
python3 tools/check.py              # everything; the discs and games from ~/.sr2-test
tools/sr2.sh au run                 # play it
```

`tools/sr2.sh BUILD ACTION` does one thing on one build with the paths
from `~/.sr2-test`: `install [LANG]`, `rip`, `patch`, `restore`, `run`,
`debug [CHANNELS]`, `show`. `run` and `debug` go through umu (Proton) or
plain wine and leave the Wine log in `logs/`.

`python3 tools/kit.py` bundles every build's installed files, minus the
assets, with the first 16 MB of each `data1.cab` into the gitignored
`tools/sr2-kit.tar.gz`: the set the notes are written against, and what
to hand over when another machine needs it.

## The checks

`tools/check.py` runs them all and reports one line each; `--list` names
them, `--only a,b` picks. The first six need nothing and are what CI
runs; the rest need the discs and games and skip themselves without.

| Check | Catches |
| --- | --- |
| `tables` | a site outside the file, two patches on one byte, a replacement longer than the original, a stub placeholder left unfilled - for every build |
| `asm` | `asm/` edited without `asm/build.py` being run: the hex in the patcher would install last week's code |
| `lint` | pyflakes: unused and undefined names |
| `bgrow`, `fullwin`, `altenter` | the .bg row copies, the borderless present and window sizing, and the ALT+ENTER toggle, run under Unicorn |
| `cab` | the disc and cabinet readers on a real dump, and the P3 files against the build's row |
| `offsets` | every original byte string really in the file, every combination of patches applying, the all-on result at its pinned MD5, and a patched install holding exactly that result. The tables are the patcher; a wrong offset passes everything else |
| `music` | the music hook under Unicorn, driven the way the build's real `MGAudio.dll` drives it |
| `altab` | the alt-tab stub and the rewritten restore routine under Unicorn, on the real files |

A truncated `data1.cab` works for `cab` (`head -c 16M`: the file table
and the executables are at the front). To exercise the disc reader
without a dump, wrap it in an image: `genisoimage -o sr2.iso
-graft-points DATA1.CAB=data1.head`, then `tools/iso2bin.py sr2.iso
sr2.bin`.

## Adding a patch

A patch is a key in `patches()`: the file it writes, its `(file offset,
original bytes, replacement)` sites, and the name of a transform or
`None`. A site in the exe takes its offset from the build's row in
`BUILDS`; a site in a DLL is the same in every build, or the build's own
if only one has it. A transform takes the image and the build name; an
exe stub gets its addresses through `EXE_MAGICS` placeholders that
`exe_blob` fills from the row. `patch()` verifies the original bytes,
writes the sites, then runs the transform, which may grow the file.

Code rather than bytes goes in `asm/` and is a transform. The shapes:

- a section appended to the fixed exe, sites pointed at it with `_branch`:
  `altab`, `textcolor`, `windowed`, `altenter`; `titlebg` the same in
  `Title.dll`, `mixerless` in `MGAudio.dll`, `bgmvol` in `MGSound.dll`.
  The European and Australian exes have room for exactly four appended
  sections, all taken; a further small exe stub goes in the slack at the
  end of `.text` with `append_text`;
- a section appended to a relocated DLL, the blob finding its own base and
  a placeholder filled at apply time: `music`, `borderless`;
- a routine rewritten in place: `restoreall`;
- plain sites with a transform only to drop the relocation entry of an
  absolute address they removed: `managed`.

Each transform appends its own section, so any patch can be left out
without moving another's. A site with `None` for its replacement is
verified before the transform runs and written by it. Update
`EXPECTED` in `tools/selftest.py` when a patch changes what it writes,
and document the patch in NOTES.md's table and MAP.md's *Sites by patch*.

## Adding a build

A row in `BUILDS`: the nine fingerprints, the six exe sites, the ten
SetTextColor sites, the five import slots and the seven addresses. An
exe stub may not name an exe address in its source - `asm/build.py`
refuses one - so everything a stub reads goes through a placeholder and
the row.
`tools/discsurvey.py` gives the fingerprints and what differs from the
discs you have; find each site by searching the new exe for the European
site's bytes with addresses and `rel32`s masked, and read the hit back in
a disassembler before it goes in. `check_build` compares the slots with
the exe's import table and the `call` sites with `RESUME` and `HANDLER`,
so a wrong row fails before anything is written; `offsets` then pins the
result.

## Reading a Wine log

`tools/sr2.sh BUILD debug` sets `WINEDEBUG=+seh,+loaddll,+mci`, or the
channels given. The last `loaddll` before the exit names the DLL whose
init failed; `err:actctx` and `80040154` are the manifests;
`seh:dispatch_exception` with its `eip` is a crash and the module it
lands in; `mciSendStringW (L"…")` lines are the music hook's commands,
and `+debugstr` shows what the Musashi DLLs say for themselves. An empty
file `music\trace` beside the tracks makes the hook report every command
it receives from the game through `OutputDebugStringA` as `sr2 <id> <msg>
<flags> <p1> <p2> <p3>`, so `+mci,+debugstr` shows both sides.

## Diagnostics

`voltrace` is a patch applied only by name: five volume entry points in
the exe report every call through `OutputDebugStringA` as `sr2 vN this
a1 a2 a3`, so `tools/sr2.sh eu debug +debugstr` shows which one fires
when a slider moves and what it carries. It needs a section-table slot,
so apply it in place of one of the exe patches that take one:

```
tools/sr2.sh eu patch nodisc,altab,textcolor,windowed,titlebg,zdetach,managed,restoreall,texfmt,anydepth,borderless,music,voltrace
```

The row lists the sites as `(offset, displaced length)`; the thunks in
`asm/voltrace.asm` carry the displaced instructions by hand.

## Not there yet

- A Windows build (PyInstaller spec and the release job).
- A `gui` check under xvfb.
