# Documentation map

The root [README](../README.md) is for playing. It covers installing,
what each patch does, the window, the pad, the music and the terminal.
Everything in this folder is for working on the patcher.

| Read | For |
| --- | --- |
| [NOTES.md](NOTES.md) | Says how the game works and what each patch changes. It holds the patch table with every site, the builds and Sega's updates, the executable, Musashi, startup and files, a section per patch, and the two discs. |
| [WIDESCREEN.md](WIDESCREEN.md) | Describes the widescreen patch: the setting, the 3D, the 2D and its exceptions (the HUD's frame, the side bars, the `.bg` screens, the lobby, the device viewport), the sea, the credits, and the Graphic Settings page. |
| [NETWORK.md](NETWORK.md) | Describes the multiplayer. It covers what ships (MGNetWk, DirectPlay, the exe's protocol, the race data path, the screens) and what replaces it: the UDP DLL, the three rows, the directory and the relay, and what is and is not reproduced. |
| [MAP.md](MAP.md) | Says where things are: the repository, the regions of `sr2-patcher.py`, the addresses mapped in the exe and six of the DLLs, and then the sites by patch. |
| [DEVELOPING.md](DEVELOPING.md) | Covers setup, the daily loop, the checks and what each catches, adding a patch or a build, the diagnostics, reading a Wine log, and releasing. |
| [../asm/README.md](../asm/README.md) | Covers the assembly sources: how they become bytes in the patcher, then a line per file in a table, then a section on each file. |
| [../net/README.md](../net/README.md) | Covers the replacement `MGNetWk.dll`: its files, building and testing it, the wire format, and the directory server and how to run one. |

Where something lives, by question:

- *What is at this address, or where does patch X write?* MAP.md has
  both.
- *What does patch X change?* Start with NOTES.md's table, then read the
  patch's section under *How each patch works*. The four widescreen
  patches are in WIDESCREEN.md.
- *Which builds are there, and how do their offsets map?* NOTES.md,
  *Builds*, lists them.
- *How do I rebuild after editing assembly?* asm/README.md says how.
- *How do I run the checks, or one of them?* DEVELOPING.md, *The
  checks*, says how.
- *How do I trace what the game is doing?* DEVELOPING.md,
  *Diagnostics*, lists the traces.
- *How does multiplayer work, and what replaces DirectPlay?* NETWORK.md
  answers that. The wire format and the server are in net/README.md.
- *What is in `data1.cab`, and how is it read?* NOTES.md, *The install
  disc*, describes it.
- *How do I cut a release?* DEVELOPING.md, *Releasing*, gives the steps.
