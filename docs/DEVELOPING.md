# Developing sr2-patcher

How to run the checks and what each is for. For using the patcher see
[README.md](../README.md); for how the game works see [NOTES.md](NOTES.md).

## Setup, once

```bash
sh tools/setup-dev.sh          # says what is missing and the install line
```

Everything comes from the distribution - no venv, nothing from pip.
`python3-pyflakes` is the `lint` check; `tkinter` is the window. Neither is
needed to run the patcher from the command line.

## The loop

```
vim sr2-patcher.py
python3 tools/check.py                              # tables, lint
python3 tools/check.py data1.head ~/games/sr2       # and the cabinet reader
```

`data1.head` is the first 16 MB of `data1.cab` (`head -c 16M`): enough for
the file table and the executables, small enough to keep around. The real
cabinet works the same and checks everything.

## What CI checks

The `verify` job in `.github/workflows/build.yml` runs `tools/check.py` on
every push, tag and pull request:

| Check | Catches |
| --- | --- |
| `tables` | a patch site outside the file, two patches on one byte, a replacement longer than the original |
| `lint` | pyflakes: unused and undefined names |

`cab` needs a `data1.cab`, which is not in the repository, so CI skips it.
Run it locally before tagging.

## Adding a patch

A patch is a key in `PATCHES` with one or more `(file offset, original
bytes, replacement)` sites in the Pentium III exe. `patch()` verifies the
original bytes before writing, and `--selfcheck` catches the structural
mistakes at import time. Document it in NOTES.md's table and MAP.md's
*Sites by patch*.

There is no `asm/` yet; the one patch so far is three hand-written bytes.
When a patch needs more than that, the plan is v-on-patcher's: sources in
`asm/`, assembled by a build script into hex strings in the patcher,
checked by CI against the committed bytes.

## Not there yet

- A Windows build (PyInstaller spec and the release job). Copy from
  v-on-patcher when the first release is near.
- A `gui` check under xvfb.
- An `offsets` check against a real install, once there is more than one
  site to check.
