# Map

Where things are: in the repository, inside `sr2-patcher.py`, and inside
the Pentium III `SEGA RALLY 2.exe`. NOTES.md says how things work; this
says where to look.

## 1. The repository

| Path | What |
| --- | --- |
| `sr2-patcher.py` | the patcher: tables, the IS5 cabinet reader, installer, manifests, patch and restore, window, CLI |
| `tools/check.py` | runs every check; `tools/cabtest.py` is the cabinet check it calls |
| `tools/setup-dev.sh` | says what the toolchain is missing |
| `docs/` | this and the other documents; `docs/README.md` is the index |
| `.github/workflows/build.yml` | CI: the checks |

## 2. `sr2-patcher.py`

In file order:

| Region | Starts with |
| --- | --- |
| Constants | `VERSION`; `P3_FILES` the six fingerprints; `PATCHES` the site table; `MUSASHI` the CLSID table; the two manifest templates |
| InstallShield 5 cabinet | `class Cabinet` |
| Install | `install_groups`, `find_cab`, `write_manifests`, `install` |
| Patch | `md5`, `check_build`, `patch`, `restore` |
| Window | `gui` |
| CLI | `selfcheck`, `main` |

## 3. `SEGA RALLY 2.exe` (Pentium III)

Image base `0x400000`. File offset = VA − `0x401000` + `0x400` inside
`.text`.

### Sections

| Section | VA | Virtual size | Raw | Raw size |
| --- | --- | --- | --- | --- |
| `.text` | `0x401000` | `0x936ca` | `0x400` | `0x93800` |
| `.rdata` | `0x495000` | `0x12df0` | `0x93c00` | `0x12e00` |
| `.data` | `0x4a8000` | `0xf91bc` | `0xa6a00` | `0x29400` |
| `STATUSDA` | `0x5a2000` | `0xaad` | `0xcfe00` | `0xc00` |
| `METERDAT` | `0x5a3000` | `0x10323` | `0xd0a00` | `0x10400` |
| `MYDATA` | `0x5b4000` | `0x3faf` | `0xe0e00` | `0x4000` |
| `ALIGN16D` | `0x5b8000` | `0x15a6` | `0xe4e00` | `0x1600` |
| `MGAMEMAT` | `0x5ba000` | `0x80000` | `0xe6400` | `0x80000` |
| `.rsrc` | `0x63a000` | `0x980` | `0x166400` | `0xa00` |

Entry point `0x488b46`. The base build differs in layout (`.rdata`
`0x93590` bytes, no `MGAMEMAT`); its addresses are not mapped.

### Code, as far as it is mapped

| Address | What | Touched by |
| --- | --- | --- |
| `0x421399`–`0x484b84` | the nine `CoCreateInstance` sites, one per Musashi server (NOTES.md, *Musashi*) | manifests |
| `0x4272c0`–`0x427340` | reads `SR2.CFG`, picks a value 1–6 | - |
| `0x4273c0` | **the disc check**: `SR2.CFG` present → message 2 or 3, drive scan, retry loop | nodisc |
| `0x427450` | `SR2.CFG` exists beside the exe | - |
| `0x4274e0` | drive scan: CD-ROM, label `SEGARALLY2`, `DISKID.2` | - |
| `0x427600` | main init; `0x427657` constructs the loader | - |
| `0x444be0` | processor check via `miscdll.dll!CheckKatmai` | - |
| `0x476260` | loader constructor: exe dir at `+0x108`, disc root at `+0x4` | - |
| `0x4764e0` | builds `<prefix>BINDATA\<dir>\<file>`; `0x476512` the `800x600` switch | - |
| `0x476780` | builds `BINDATA\<dir>.CAB` | - |
| `0x476a50` | open: loose file, local cab, disc cab | - |
| `0x476b50` | open a loose file | - |
| `0x476bb0` | open through a cabinet (FDI) | - |

### Data

| Address | What |
| --- | --- |
| `0x495000`–`0x4a8000` | `.rdata`: IATs, the dxguid table (217 GUIDs, shared with every screen DLL), `0x49e078`–`0x49ed78` the Musashi CLSIDs |
| `0x4cf1f8`–`0x4cf304` | the loader's format strings: `%sDISKID.2`, `%sBINDATA\%s\%s\%s`, `BINDATA\%s%s`, `.CAB` |
| `0x5a2978`–`0x5a29c0` | `SEGARALLY2`, `DISKID.2`, `%c:\`, `SR2.CFG`, `%c:\AUTORUN.EXE` |
| `0x4b69b8` | `CPU Version error`, `CheckKatmai`, `MISCDLL.DLL` |
| `0x50afdc` | pointer to the settings block; `+0x50 == 1` selects `800x600` assets |
| `0x50b108` | pointer to the current-race block (`+0x38` mode, `+0x54`/`+0x58` course indices) |

### Sites by patch

| Patch | Sites | Where |
| --- | --- | --- |
| nodisc | 1 | `0x4273c0` (file `0x267c0`) |
