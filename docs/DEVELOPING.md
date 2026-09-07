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
python3 tools/check.py                              # tables, asm, lint
python3 tools/check.py data1.head ~/games/sr2       # and the cabinet reader, the music hook
python3 tools/check.py disc1.cue ~/games/sr2        # through a disc image
```

`data1.head` is the first 16 MB of `data1.cab` (`head -c 16M`): enough for
the file table and the executables, small enough to keep around. The real
cabinet or a real dump works the same and checks everything. To exercise
the disc reader without a dump, wrap the head in an image:

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
| `tables` | a patch site outside the file, two patches on one byte, a replacement longer than the original |
| `asm` | `asm/` edited without `asm/build.py` being run: the hex in the patcher would install last week's code |
| `lint` | pyflakes: unused and undefined names |

`cab` and `music` need an image or `data1.cab` and an install folder,
none in the repository, so CI skips them. Run them locally before tagging.

## Adding a patch

A patch is a key in `PATCHES` naming a file and one or more `(file
offset, original bytes, replacement)` sites in it. The file needs an
entry in `PATCHED_FILES` with the original's size and MD5. `patch()`
verifies the original bytes before writing, and `--selfcheck` catches the
structural mistakes at import time. Document it in NOTES.md's table and
MAP.md's *Sites by patch*.

`tools/sr2-run.sh debug` runs the game under umu or wine with the Wine
log in `logs/`; `~/.sr2-test` holds the paths. Reading a log: the last
`loaddll` before the exit names the DLL whose init failed, `err:actctx`
and `80040154` are the manifests, `seh:dispatch_exception` with its `eip`
is a crash and the module it lands in.

A patch that is code rather than bytes goes in `asm/` and gets an apply
function in the patcher instead of a site list; `music` is the model.
`asm/build.py` puts the assembled bytes into the GENERATED region of the
patcher, and the `asm` check keeps the two in step.

## Not there yet

- A Windows build (PyInstaller spec and the release job). Copy from
  v-on-patcher when the first release is near.
- A `gui` check under xvfb.
- An `offsets` check against a real install, once there is more than one
  site to check.
