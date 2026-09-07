# Documentation map

The root [README](../README.md) is for playing: installing, what the
patches do, builds. Everything here is for working on the patcher.

| Read | For |
| --- | --- |
| [NOTES.md](NOTES.md) | how the game works: the executable and its DLLs, the three CPU builds, the processor check, Musashi and the manifests, the startup and loader logic, both discs and the `data1.cab` format |
| [MAP.md](MAP.md) | where things are: the repository, the regions of `sr2-patcher.py`, the exe's sections and every address mapped so far |
| [DEVELOPING.md](DEVELOPING.md) | setup, the checks and what each catches, adding a patch, what is not there yet |

Where something lives, by question:

- *What does the game do at startup, and why is the disc check where it is?* NOTES.md, *Startup and files*.
- *What is at this address?* MAP.md.
- *How is the image read, and what is in `data1.cab`?* NOTES.md, *The install disc*.
- *Why manifests instead of registration?* NOTES.md, *Musashi*.
