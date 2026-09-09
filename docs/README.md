# Documentation map

The root [README](../README.md) is for playing. Everything here is for
working on the patcher.

| Read | For |
| --- | --- |
| [NOTES.md](NOTES.md) | how the game works and what each patch changes: the executable and its DLLs, the builds and their fingerprints, the processor check, Musashi and the manifests, the registry, startup, the loader, activation, the texture formats, the lobby text, windowed mode, music, both discs and the `data1.cab` format |
| [MAP.md](MAP.md) | where things are: the repository, the regions of `sr2-patcher.py`, the exe's sections and every address mapped so far |
| [DEVELOPING.md](DEVELOPING.md) | setup, `~/.sr2-test`, the checks and what each catches, adding a patch or a build, reading a Wine log |
| [../asm/README.md](../asm/README.md) | the assembly source of every code patch, how it is built into the patcher, and what each stub does |

Where something lives, by question:

- *What does the game do at startup, and why is the disc check where it is?* NOTES.md, *Startup and files*.
- *What is at this address?* MAP.md.
- *How is the image read, and what is in `data1.cab`?* NOTES.md, *The install disc*.
- *Why manifests instead of registration?* NOTES.md, *Musashi*.
- *Why does the game run in a window now, and what did that break?* NOTES.md, *Windowed mode*, *Borderless*, *ALT+ENTER*.
- *What does a screen change do to the renderer?* NOTES.md, *Borderless*.
