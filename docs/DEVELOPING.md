# Developing sr2-patcher

How to run the checks and what each is for. For using the patcher see
[README.md](../README.md); for how the game works see [NOTES.md](NOTES.md).

## Setup, once

```bash
sh tools/setup-dev.sh          # says what is missing and the install line
```

Everything comes from the distribution - no venv, nothing from pip.
`python3-pyflakes` is the `lint` check, `nasm` rebuilds `asm/` and is the
`asm` check, `python3-unicorn` runs the music hook in the `music` check,
`tkinter` is the window. None is needed to run the patcher.

## The loop

```
vim sr2-patcher.py                                  # or asm/music.asm, then asm/build.py
python3 tools/check.py                              # everything, the discs and games from ~/.sr2-test
python3 tools/check.py data1.head ~/games/sr2       # one cabinet and one game instead
python3 tools/check.py disc1.cue ~/games/sr2        # through a disc image
```

`~/.sr2-test` names the install disc and the installed game per build -
`SR2_DISC_EU`, `SR2_GAME_EU`, and `US`, `AU` likewise - and the cabinet,
music and alt-tab checks run on each that is set. Start from
`tools/sr2-test.example`, which describes every variable; the file stays
on your machine. `data1.head` is the
first 16 MB of `data1.cab` (`head -c 16M`): enough for the file table and
the executables, small enough to keep around. `python3 tools/kit.py`
bundles it with every build's installed files, minus the assets, into
`tools/sr2-kit.tar.gz` - the set the notes and the tools are written
against, and what to hand over when a second machine needs it. The real cabinet or a real
dump works the same and checks everything. To exercise the disc reader
without a dump, wrap the head in an image:

```
genisoimage -o sr2.iso -graft-points DATA1.CAB=data1.head
python3 tools/iso2bin.py sr2.iso sr2.bin            # writes sr2.bin and sr2.cue
python3 tools/check.py sr2.cue ~/games/sr2
```

## What CI checks

The `verify` job in `.github/workflows/build.yml` runs `tools/check.py` on
every push, tag and pull request:

| Check | Catches |
| --- | --- |
| `tables` | a patch site outside the file, two patches on one byte, a replacement longer than the original, a placeholder left in a stub - for every build |
| `asm` | `asm/` edited without `asm/build.py` being run: the hex in the patcher would install last week's code |
| `lint` | pyflakes: unused and undefined names |

`cab`, `music` and `altab` need an image or `data1.cab` and an install
folder, none in the repository, so CI skips them. Run them locally before
tagging.

## Adding a patch

A patch is a key in `patches()`: the file it writes, its `(file offset,
original bytes, replacement)` sites, and the name of a transform function
or `None`. A site in the exe takes its offset from the build's row in
`BUILDS`, one per build; a site in a DLL is the same in every build. A
transform takes the image and the build name, and an exe stub gets its
addresses through `EXE_MAGICS` placeholders that `exe_blob` fills from
the row. `patch()` verifies the original bytes before writing sites, then
runs the transform, which may grow the file; `--selfcheck` checks every
build's table. Document it in NOTES.md's table and MAP.md's *Sites by
patch*.

## Adding a build

A row in `BUILDS`: the nine fingerprints, the six exe sites, the ten
SetTextColor sites, the five import slots and the seven addresses. Find
the sites by searching the new exe for each European site's bytes with
addresses and `rel32`s masked (`tools/discsurvey.py` gives the
fingerprints); read each hit back in a disassembler before it goes in.
`check_build` compares the slots with the exe's import table, and the
`call` sites are checked against `RESUME` and `HANDLER` when the stubs
are applied, so a wrong row fails before anything is written.

A patch that is code rather than bytes goes in `asm/` and is a transform.
The shapes there are:

- a section appended to the fixed exe, sites pointed at it with `_branch`:
  `altab`, `textcolor`, `windowed`, `altenter`; `titlebg` the same in
  `Title.dll`, which nothing in the site made position-dependent;
- a section appended to a relocated DLL, the blob finding its own base and
  a placeholder filled at apply time: `music`, `borderless`;
- a routine rewritten in place: `restoreall`;
- plain sites with a transform only to drop the relocation entry of an
  absolute address they removed: `managed`.

Each transform appends its own section, so any patch can be left out
without moving another's. A site with `None` for its replacement is
verified before the transform runs and written by it. `asm/build.py` puts the assembled bytes into the
GENERATED region of the patcher, and the `asm` check keeps the two in
step.

## One build at a time

`tools/sr2.sh eu|us|au ACTION` does everything on one build with the
paths from `~/.sr2-test` (template: `tools/sr2-test.example`): `install`,
`rip`, `patch` and `restore` call the patcher, `run` and `debug` start
the game under umu (Proton) or plain wine with the Wine log in `logs/`,
`show` prints the paths. `debug` adds `+seh,+loaddll,+mci`; edit the line for
other channels. Reading a log: the last `loaddll` before the exit names
the DLL whose init failed, `err:actctx` and `80040154` are the manifests,
`seh:dispatch_exception` with its `eip` is a crash and the module it lands
in, `mciSendStringW (L"…")` lines are the music hook's commands and the
thread id in front of them should be the same on every one.

## Not there yet

- A Windows build (PyInstaller spec and the release job).
- A `gui` check under xvfb.
- An `offsets` check that applies every patch to a real install and
  compares the result against a known MD5.
