# Developing

## Setup

```bash
sh tools/setup-dev.sh          # says what is missing
cp tools/sr2-test.example ~/.sr2-test
```

Everything comes from the distribution: `python3-pyflakes` (the `lint`
check), `nasm` (rebuilds `asm/`), `python3-unicorn` (runs the stubs),
`tkinter` (the window). None is needed to run the patcher.

`~/.sr2-test` names, per build, the install disc, the play disc, the
installed game and the Wine prefix: `SR2_DISC_EU`, `SR2_PLAY_EU`,
`SR2_GAME_EU`, `SR2_PFX_EU`, and `US`, `AU` likewise.

## The loop

```
vim sr2-patcher.py              # or asm/*.asm, then python3 asm/build.py
python3 tools/check.py          # everything
tools/sr2.sh au run             # play it
```

`tools/sr2.sh BUILD ACTION`: `install [LANG]`, `rip`, `patch [KEYS]`,
`restore`, `run`, `debug [CHANNELS]`, `show`, with the paths from
`~/.sr2-test`. `run` and `debug` go through umu (Proton) or plain wine
and leave the Wine log in `logs/`.

The mix's numbers - the effects' range and the two music offsets - are
`asm/mix.inc`; `build.py` derives the CD table (`curve.inc`) from it.

`python3 tools/kit.py` bundles every build's installed files, minus the
assets, with the first 16 MB of each `data1.cab`, into the gitignored
`tools/sr2-kit.tar.gz`: what the notes are written against.

## The checks

`tools/check.py` runs them all; `--list` names them, `--only a,b` picks.
The first six need nothing and are what CI runs; the rest need the discs
and games and skip themselves without.

| Check | Catches |
| --- | --- |
| `tables` | a site outside the file, two patches on one byte, a replacement longer than the original, a placeholder left unfilled |
| `asm` | `asm/` edited without `asm/build.py` being run, `curve.inc` included |
| `lint` | pyflakes |
| `bgrow`, `fullwin`, `altenter` | those stubs under Unicorn |
| `cab` | the disc and cabinet readers on a real dump |
| `offsets` | every original byte string in the file, every combination of patches applying, the all-on result at its pinned MD5 |
| `music` | the music hook under Unicorn, on the build's real `MGAudio.dll` |
| `altab` | the alt-tab stub and the rewritten restore routine under Unicorn |

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

- a section appended, sites pointed at it with `_branch`: `altab`,
  `textcolor`, `windowed`, `altenter` in the exe; `titlebg` in
  `Title.dll`, `mixerless` in `MGAudio.dll`, `mix` in `MGSound.dll`.
  The European and Australian exes have room for exactly four appended
  sections, all taken; a further exe stub has to go in the slack at the
  end of `.text` (0x136 bytes European, 0x166 Australian);
- a section appended to a relocated DLL, the blob finding its own base:
  `music`, `borderless`;
- a routine rewritten in place: `restoreall`;
- plain sites plus a transform that drops a relocation entry: `managed`.

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

## Reading a Wine log

`tools/sr2.sh BUILD debug` sets `WINEDEBUG=+seh,+loaddll,+mci`, or the
channels given. The last `loaddll` before an exit names the DLL whose
init failed; `err:actctx` and `80040154` are the manifests;
`seh:dispatch_exception` with its `eip` is a crash; `mciSendStringW`
lines are the music hook's commands; `+debugstr` shows what the Musashi
DLLs print. An empty `music\trace` beside the tracks makes the hook
report every command it receives as `sr2 <id> <msg> <flags> <p1> <p2>
<p3>` on `+debugstr`.

`voltrace` is a patch applied only by name: five volume entry points in
the exe report their arguments as `sr2 vN this a1 a2 a3` on `+debugstr`.
It needs a section-table slot, so apply it in place of one exe patch:

```
tools/sr2.sh eu patch nodisc,altab,textcolor,windowed,titlebg,zdetach,managed,restoreall,texfmt,anydepth,borderless,music,voltrace
```

## Not there yet

- A Windows build (PyInstaller spec and the release job).
- A `gui` check under xvfb.
