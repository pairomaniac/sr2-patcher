# Developing sr2-patcher

This document says how to build the patcher, what to run before pushing,
and what each check is for. [README.md](../README.md) says how to use the
patcher, [NOTES.md](NOTES.md) says what the patches do, and
[asm/](../asm/) holds the assembly sources.

## The two layers

```
asm/*.asm  ──nasm──►  hex strings in sr2-patcher.py  ──►  the one file a player downloads
 you edit             asm/build.py writes these
```

`sr2-patcher.py` cannot read `asm/` at runtime. So `asm/build.py`
assembles the sources and writes the machine code into the script as hex
text between GENERATED markers. **Never edit a blob by hand.** The next
build run overwrites it.

## Setup, once

```bash
sh tools/setup-dev.sh          # says what is missing and the install line
cp tools/sr2-test.example ~/.sr2-test
```

Every package comes from the distribution; there is no venv and no pip.
None of them is needed to run the patcher, only to work on it.

| Package | For |
| --- | --- |
| `nasm` | rebuilding `asm/` |
| `python3-pyflakes` | the `lint` check |
| `python3-unicorn` | the checks that run the stubs |
| `python3-pil`, `fonts-urw-base35` | `tools/txrdump.py`, `tools/assets.py`; `tools/labels.py`, `tools/prompts.py` and their checks |
| Liberation Sans Narrow, Open Sans, Noto Sans CJK, Noto Sans Mono (Fedora: `liberation-narrow-fonts`, `open-sans-fonts`, `google-noto-sans-cjk-vf-fonts`, `google-noto-sans-mono-fonts`) | `tools/prompts.py` and its check |
| `gcc-mingw-w64-i686` | `net/build.py`, the network DLL |
| a C compiler (`cc`) | the `nettest` check |
| `tkinter` | the window |
| `xvfb` | the `gui` check |

`~/.sr2-test` names four paths per build: the install disc, the play
disc, the installed game and the Wine prefix. For the European build the
variables are `SR2_DISC_EU`, `SR2_PLAY_EU`, `SR2_GAME_EU` and
`SR2_PFX_EU`. The other builds use the same names with `US`, `AU`, `JP`
(Sega's own disc) or `JP_MK` (the DigiCube and MediaKite reissue) in
place of `EU`. The example file describes each variable. A variable that
is in the file but left empty shows as N/A in `check.py` and in `sr2.sh
BUILD show`; it is not counted as a skip.

## Daily loop

```bash
vim sr2-patcher.py              # or asm/*.asm, then python3 asm/build.py
python3 tools/check.py          # everything
tools/sr2.sh au run             # play it
```

`tools/sr2.sh BUILD ACTION` works on one build, with the paths taken
from `~/.sr2-test`. BUILD is `eu`, `us`, `au`, `jp` or `jp_mk`. It can
also be `all`, which runs the action on every build that has a game
folder; `run` and `debug` do not take `all`. ACTION is `run` when it is
left out:

| Action | Does |
| --- | --- |
| `install [LANG]` | installs from the disc and patches; the language is English unless LANG is given |
| `rip` | rips the play disc's music into the game folder |
| `patch [KEYS]` | patches the installed game; with KEYS, a comma-separated list, only those patches are applied |
| `restore` | puts the original files back |
| `run` | runs the game under umu (Proton) or plain wine; the Wine log goes to `logs/` |
| `debug [CHANNELS]` | the same as `run`, with `WINEDEBUG=+seh,+loaddll,+mci` or the channels given |
| `show` | prints the paths it would use |

Some patches need others, and the patcher refuses a set that names a
patch without what it needs:

- `noregistry` is in every set. It gives the game's own settings block
  a file of its own, `SR2.DSP`, and leaves `SR2.CFG` to the text the
  other patches keep there.
- `borderless` and `altenter` need `windowed`.
- `devices` needs `xinput`.
- `nogeneric` needs `dinput8`.
- `music` needs `cdlevel`.
- `lobby` and `netplay` need each other.
- `starting` needs `lobby`.
- `widescreen2d`, `widescreen3d` and `resolution` need `widescreen`.
- Among the diagnostics, `gltrace` needs `widescreen3d`, `d3dtrace` and
  `d3dtrace2d` need `widescreen2d`, and `netlog` needs `netplay`.

`windowed` and `borderless` are always in the set.

`tools/loudness.py GAMEDIR` measures the CD rips against the streamed
music and says what value of `CD_DB - STREAM_DB` makes them equally loud
at equal slider settings. The mix's numbers - the effects' range and the
two music offsets - live in `asm/mix.inc`, which `mix.asm` and
`music.asm` include.

## The checks

`tools/check.py` runs every check. `--list` names them and `--only a,b`
picks some. There are 40. The first 24, down to `gui`, need only nasm,
pyflakes, Unicorn, Pillow and the fonts, tkinter, xvfb and a C
compiler, and CI runs them; `prompts` skips there until CI has its
five fonts. Every test that maps a PE image does so
through `tools/uctest.py`. The last sixteen need the discs and the
installed games, and they skip without them. `devices` also needs nasm,
because it reads nasm's listing. A tool that cannot run exits 77 and is
reported SKIP, never OK. `clearsize` applies to the Australian build only
and skips on the others.

| Check | Catches |
| --- | --- |
| `tables` | a site outside the file, two patches on one byte, a replacement longer than the original, or a placeholder left unfilled |
| `asm` | `asm/` edited without `asm/build.py` being run |
| `labels` | `tools/labels.py` edited without being run. The labels are rendered here and compared with the baked ones; a rasteriser's few pixels of difference are allowed. Skips without Pillow and the font |
| `prompts` | `tools/prompts.py` edited without being run. The pad's prompts and the hint lines are rendered here and compared with the baked texels; a rasteriser's level of difference is allowed. Skips without Pillow and the three fonts |
| `net` | `net/` edited without `net/build.py` being run |
| `nettest` | the network core. A host and five guests run over loopback with a third of the datagrams dropped, and the test covers joins, names, the reliable and unreliable classes, ordering, closed sessions and slots, leaving, silence, the host going away, an oversized reliable datagram, and a welcome with a seat past the table. It also checks the name lookup on its own thread. Then a directory server is started for the run (a failure to start fails the check), a session is found through it, and one guest joins directly and one through the relay. Skips without a C compiler |
| `directorytest` | the directory server's list limit per address, the token, the registration cookie, and N and X, with a hand-set clock |
| `lint` | pyflakes |
| `bgrow`, `wide`, `fullwin`, `altenter`, `starting`, `loadhold`, `padmenu`, `pagepad`, `hudlast`, `frametrace`, `d3dinit`, `texrange`, `replayfree` | those stubs under Unicorn, with the exe's routines stubbed. `wide` runs both the European and the American exe blobs. `tools/uctest.py` holds what these tests share |
| `cab` | the disc and cabinet readers on a real dump |
| `dgvoodoo` | the dgVoodoo 2 add-on's download and unpack, against a made-up release |
| `gui` | the window driven headlessly: every widget is reachable, the palette's contrast is measured, and the feature rows are compared with the patch keys. Skips without a display |
| `offsets` | the tables against a real install. Every original byte string is in the file; every patch applies alone, in every pair, in a hundred random sets, and with the diagnostics in sets of their own; and the all-on result has its pinned MD5, both with the full resolution table and with the capped one. An install older than the tables is noted, not failed |
| `music` | the music hook under Unicorn, on the build's real `MGAudio.dll` |
| `altab` | the alt-tab stub and the rewritten restore routine under Unicorn |
| `padinput`, `dinput8`, `nogeneric` | the pad annex, the DirectInput 8 create and type translation, and the device-list filter, each under Unicorn on the build's real `MGInput.dll` |
| `devices` | the Device Settings page's binding under Unicorn, on the real `Options.dll` over stubbed input objects |
| `resolution` | the resolution row's init, draw and store under Unicorn, on the real `Options.dll` |
| `lobby` | the connection screen's confirm under Unicorn, on the real exe: the list opens searching for INTERNET and LAN, and not for DIRECT IP |
| `buttons` | the SEARCH button composed from the install's stock `showteam_*` and `create_*` files, and the IP entry popup composed from its stock file, both against pinned digests. A file the install lacks gives a note |
| `ipcheck` | the lobby entries on the real exe under Unicorn: the IP entry's address check, the caps by field, CTRL+V kept within the cap, and the status line's stub |
| `clearsize` | the Australian clear's two arguments under Unicorn, on the real exe |
| `sortpad` | the gallery's sort site on the real `ReplayGallery.dll`, relocated, with the annex's poll stubbed |
| `padprompts` | each key of `PROMPTS`: the Exec export of the real DLL (`Record.dll`, `Title.dll`, `AdvTelop.dll`, `ReplayGallery.dll`, `Options.dll`), relocated, with the annex's poll stubbed, its fields with and without a pad; and the key's sheet files as the patcher writes them, in the install's language, every filled box on the art |
| `replaypad` | the replay controls' update under Unicorn, on the real exe patched with `replaypad` alone, with the input objects and the annex's poll stubbed |

A truncated `data1.cab` (`head -c 16M`) is enough for `cab`, as long as
it keeps the `.cab` name. To exercise the disc reader without a dump,
wrap the truncated cab in an image:

```bash
genisoimage -o sr2.iso -graft-points DATA1.CAB=data1.head
python3 tools/iso2bin.py sr2.iso sr2.bin
```

A pre-push hook catches a forgotten build before CI does:

```bash
cat > .git/hooks/pre-push <<'EOF'
#!/bin/sh
exec python3 tools/check.py
EOF
chmod +x .git/hooks/pre-push
```

## Adding a patch

A patch is a key in `patches()`. Its entry names the file, lists its
sites as `(offset, original bytes, replacement)`, and names a transform
or `None`. Exe offsets come from the build's row in `BUILDS`; a DLL site
is the same in every build. A transform takes the image and the build
name. An exe stub gets its addresses through `EXE_MAGICS` placeholders,
which `exe_blob` fills from the row. `patch()` verifies the original
bytes, writes the sites, and then runs the transform.

Code goes in `asm/` and is installed by a transform. These are the
shapes a transform takes:

| Shape | Examples |
| --- | --- |
| a blob in the file's annex, with the sites pointed at it by `_branch` | `altab`, `textcolor`, `windowed`, `altenter`, `starting`, `loadhold`, `padmenu`, `replaypad`, `pagepad` in the exe; `titlebg` in `Title.dll`, `mixerless` in `MGAudio.dll`, `mix` in `MGSound.dll` |
| a blob in a relocated DLL's annex, which finds its own base | `music`, `borderless`, `xinput` |
| a blob in a DLL's annex that an export is pointed at | `padprompts`, `padtitle`, `padattract`, `padgallery`, `padoptions` |
| a routine rewritten in place | `restoreall` |
| plain sites, plus a transform that drops relocation entries | `borderless`, `texrange` |
| a whole file replaced from a baked build | `netplay`; `lobby` also writes art and `MPDATA.DAT` beside the exe |

The annex is one `.sr2` section per file. The first patch that needs it
appends it, and the rest grow it (`append_section`), so any set of
patches fits. Each transform appends its own data, so any patch can be
left out.

When a patch changes what it writes, update `EXPECTED` in
`tools/selftest.py`. For the exe or `Options.dll` also update
`EXPECTED_CAPPED`, which is pinned under the capped resolution table.
Then document the change in NOTES.md's tables and in MAP.md.

## Adding a build

A build is a row in `BUILDS`: the fingerprints, the exe sites, the
SetTextColor sites, the import slots and the addresses. Where a build's
file differs in shape, the row carries the original bytes or the extra
site; examples are the older `MGInput.dll`'s static polls (`kbdpoll`),
its six-byte type read, and the exe's `pagepad` site. Nothing in the
code tests the build's name. No stub may name an exe address in its
source, and `asm/build.py` refuses one that does; everything a stub
reads goes through a placeholder and the row.

`tools/discsurvey.py` gives the fingerprints. To find each site, search
the new exe for the European site's bytes with the addresses and
`rel32`s masked, and read the hit back in a disassembler. `check_build`
compares the row with the exe's import table and the `call` sites, so a
wrong row fails before anything is written.

A rebuild of a known exe is the easy case, and `Japanese (DigiCube,
MediaKite)` is the example. Search it for each European site's bytes
unmasked first. The hits come back at the old offset or at a constant
delta, which shows where code moved. Data addresses stay put if the
sections do. Then run `tools/selftest.py` on an install from the disc;
it checks every site and pins the result.

## Reading a Wine log

`tools/sr2.sh BUILD debug` sets `WINEDEBUG=+seh,+loaddll,+mci`, or the
channels given. These lines in the log are the ones to look for:

| Line | Means |
| --- | --- |
| the last `loaddll` before an exit | the DLL whose init failed |
| `err:actctx`, `80040154` | the manifests |
| `seh:dispatch_exception` with its `eip` | a crash |
| `+debugstr` | what the Musashi DLLs and the diagnostics print |

## Diagnostics

A diagnostic is a patch that is applied only when it is named, or when
its box in the window is ticked. Naming one adds it to the set; the word
`logs` names all of them but `d3dtrace2d`; and a plain patch with no
diagnostic named takes them out again:

```
tools/sr2.sh eu patch voltrace
python3 sr2-patcher.py --patch ~/games/sr2 frametrace
```

`voltrace` and `gltrace` report through `+debugstr` (`tools/sr2.sh eu
debug debugstr`, or DebugView on Windows). The rest write files under
`logs\`. `netlog` is not a patch: it sets `Log = 1` in `SR2.CFG`, which
turns on the netplay DLL's own log (net/README.md).

### voltrace

Five volume entry points in the exe report their arguments as `sr2 vN
this a1 a2 a3`. The sites are known in the European and DigiCube/MediaKite
builds; on the other builds the box does nothing.

An empty file `music\trace` beside the tracks makes the music hook report
in the same way. The hook reports every command it receives as
`sr2 <id> <msg> <flags> <p1> <p2> <p3>`, and the worker reports every
operation it performs as `sr2 op <op> <arg> <result> <last DirectSound HRESULT>`. The
values are in decimal.

### frametrace

This diagnostic is for the frame pacing. The frame gate logs every drawn
frame to `logs\frames.log` in the game folder. The file starts with a
header giving the ticks per 1/60 s; then each line holds the counter at
the gate's entry, after the blit and at its exit, the simulation steps,
and the gate's flags. Play, quit, and run

```
python3 tools/frames.py ~/games/sr2/logs/frames.log
```

which prints the frame rate, the spread of the intervals, the catch-up
frames, and the worst intervals with the time each happened. GAME.md,
*Frame timing*, says what the numbers mean.

Take a baseline of the stock configuration first and read every later
log against it. Make one change per run; the `-key` form gives an A/B
comparison without touching anything else.

### gltrace

This diagnostic is for the widescreen work. It reports MGameGL's viewport
and projection calls, all in hex.

| Line | Reports |
| --- | --- |
| `sr2 vp L T R B cx cy r1 r2` | `SetViewport` as called: the rect and the centre, then `r1`, the return address, and `r2`, the return address one stack frame up, past a wrapper |
| `sr2 vp> ...` | the same call as it went on after conversion |
| `sr2 fov a W H a>` | `SetPerspective`: the angle, the picture's size, and the angle as it went on |
| `sr2 ct cx cy cx> cy>` | `SetCentre`: the centre as called and as it went on |
| `sr2 pj x y x> y>` | the projection, as floats; only the first 2000 are reported |
| `sr2 gp id v v>` | the parameters the getter converts: the id, the value read, the value returned |

### d3dtrace, d3dtrace2d

`d3dtrace` reports every present as `sr2 p`, which marks a frame's end,
and every draw through MGameD3D's six hooked entries, up to the first
400000. The lines go to `OutputDebugString` (DebugView on Windows,
`WINEDEBUG` under Wine) and to `logs\d3dtrace.log` in the game folder:

```
sr2 d e fvf count ret x0 y0 z0 tex kind
```

`e` is the entry: q, t, l, i, s or f for quad, triangle, list, indexed,
strip or fan. `ret` is the draw's return address; the `loaddll` lines in
the same log say which module it is in. Then come the first vertex in
hex, before any scaling, and the selected texture and its kind. The
menus' quads fill those 400000 lines in a couple of minutes.
`d3dtrace2d` instead reports only the 2D draws that are not quads - the
lists, strips and fans, which are the HUD's text and the race's
background layers - and nothing else. That is enough for a race and its
results rather than one lap.

Two more lines serve the side bars (WIDESCREEN.md, *The side bars*):

| Line | Reports |
| --- | --- |
| `sr2 b why tex kind xmin xmax ymin ymax` | every quad that reaches the bar's decision. `why` is 1 for not a quad, 2 for shorter than 160, 3 for no texture selected, 4 for a texture that is not a picture, and 5 for the bar drawn |
| `sr2 t why slot flags size first bad left kind` | every texture create. `why` is 1 for past the table, 2 for paletted or a render target, 3 for no pixels, 4 for a transparent pixel, and 5 for the kind kept |
| `sr2 l hr ddraw surface` | the lobby's surface create |
| `sr2 x hr this source flags L T R B [l t r b]` | every blit sent to the lobby's surface, as it went: the result, the two surfaces, the flags, the destination rect, and the source rect if there is one |
| `sr2 s surface hr flags w h pf bpp caps pixel` | after each blit, one line for the source and one for the destination: `Lock`'s result, the description's flags, size, pixel format flags, bit count and caps, and the pixel at (0, 240), which is 0 on a surface with no such row |

### d3dinit

This diagnostic is for a "Failed to initialize" box. Every step of
MGameD3D's bring-up - the DirectDraw object, the cooperative level and
the window or display mode, the surfaces, the device, the textures -
appends `<site> <hr> <w>x<h> <tw>x<th>` to `logs\d3dinit.log` in the
game folder. The fields are the store's RVA in `MGameD3D.dll`, its
HRESULT, the picture size in force, and the device's largest texture
from its caps, which is 0 until the device enumeration. The last line
with a negative `hr` names the call that failed, and MAP.md's `Init` row
says which function each site is in. The device enumeration's sites
(`0x1a34` to `0x1be3`) and the texture format enumeration's (`0x3b6d`,
`0x3bc7`) are in the list too. After site `0x20c5` one more line is
written:

```
fmt <slots> <chosen> <not565>
```

`slots` has one bit per texture format slot the enumeration filled; bit
0 is the first of the 13 slots, at `0x10012594`. `chosen` is the slot
the DLL picked, and `not565` is its flag for a chosen format other than
R5G6B5. The command is the same on either system:

```
python3 sr2-patcher.py --patch ~/games/sr2 d3dinit
```

## Commits

Commits are the author's own, `pairo <pairo@segaonline.net>`, whatever
tool wrote the change. They carry no co-author or session trailers.

### Working with a patch file

Changes arrive as `git format-patch` files made against `origin/main` as
it is at that moment. A patch made against an older commit fails on
every file it touches. Apply them with `git am` on a clean tree.

## Releasing

The tag does the work. Pushing one runs the checks, builds the Windows
release, signs its exe if it is not signed already, and creates the
release with both zips attached. On a clean `main` with the checks
passing:

```
git tag -a v0.4.0 -m "v0.4.0"
git push origin v0.4.0
```

`VERSION` stays `dev` in the repository. The workflow stamps it with the
tag name less its `v`, so the window title and `--version` say the tag's
number; the zips carry the `v`. A push that is not a tag builds the same
two zips as an artifact named with the short SHA. Its exe is the
committed launcher, or an unsigned fresh one when none is committed.

Then write the notes over the generated ones: the logo, then sections
named for what their bullets are (*Added* first, *Changed* and *Fixed*
when there is something for them), in plain words, saying only what has
been seen. Requirements and known issues stay in the README.

```
gh release edit v0.4.0 --notes-file notes.md
```

Moving the tag (`git tag -f`, then `git push --force origin
refs/tags/v0.4.0`) re-runs the build and re-uploads the zips, but leaves
the notes as they are. `gh release view` shows the notes and both zips.

The exe is the same file in every release until the launcher changes, so
it needs a VirusTotal check and a Microsoft submission only then. The
`sign` job's log prints its checksum and a lookup link.

### Signing

A tag build runs three jobs after `verify`:

1. `windows` builds the release and hands it over unzipped, as an
   artifact named `unsigned` that expires after a day.
2. `sign` signs the exe, the launcher, on Linux with
   [ssign](https://github.com/Le-Syl21/ssign) and a Certum open-source
   code signing certificate. A launcher committed signed is left as it
   is (*The committed launcher*, below). It checks the signature and its
   timestamp with `osslsigncode verify`, prints the signed exe's
   checksum, and zips both packages with `tools/package.py`.
3. `release` uploads the zips to the release page.

With a launcher committed, a tag signs nothing: the secrets are used only
for a release that changes the launcher.

Only `release` can write to the repository, and only `sign` can read the
signing secrets. The Python files in `_internal` carry the Python
Software Foundation's signatures. The netplay DLL is not signed: the
patcher checks it against `MGNETWK_SHA` before installing it, so signing
it would mean signing before the commit and updating the pins.

The certificate is Certum's "Code Signing in the cloud": the private key
stays on Certum's servers and signing is a request to them, logged in
with the account's e-mail and a one-time code from the SimplySign phone
app. ssign does that login and request itself; it is built from a pinned
commit, and moving the pin is a change to review like any other. The
timestamp keeps a signature valid after the one-year certificate
expires.

### Setting up signing

Once, and again whenever the certificate or its QR code is renewed:

1. **Get the `otpauth://` URI.** The QR code the SimplySign app scanned
   holds it. Decode the image locally, never with an online reader, since
   the URI can sign as the certificate's owner:

   ```
   zbarimg --raw qr.png
   ```

   The output is one line starting `otpauth://totp/`. Delete the image
   afterwards.

2. **Create the `signing` environment** in the repository's Settings →
   Environments:
   - *Deployment branches and tags*: selected branches and tags, one rule
     of type Tag with the pattern `v*`.
   - *Environment secrets* (not repository secrets): `CERTUM_EMAIL`, the
     SimplySign account's e-mail, and `CERTUM_OTP`, the whole
     `otpauth://` URI.
   - *Required reviewers*, optional: with one set, each tag's `sign` job
     waits on the run's page until it is approved under **Review
     deployments**. Without, tags sign unattended.

3. **Check the next signing.** A tag signs only when no launcher is
   committed (*The committed launcher*, below). In that tag's `sign`
   job, the *Verify* step ends with `Signature verification: ok`.

4. **Check the exe on Windows**: Properties → Digital Signatures lists
   the signer, issued by *Certum Code Signing 2021 CA*, with a Certum
   timestamp.

If the URI leaks, re-issue the QR code in Certum's SimplySign account,
scan it into the app again and replace `CERTUM_OTP`. A renewed
certificate needs nothing else changed: ssign fetches the certificate
from the account at every signing.

To sign a file by hand, without the workflow, run ssign with the current
code from the phone app instead of the URI:

```
ssign -e <account e-mail> -T <code> sr2-patcher.exe
```

## The window

`run_tk` and the tables above it are the whole of the window. `FEATURES`
is what the window lists and what the README describes: one row per
thing somebody would say the patcher does, with the patch keys that
thing takes. `group_keys` turns the ticked boxes into the key set that
`patch` is given, and drops any key whose `NEEDS` went out with an
unticked box. `--selfcheck` holds the two together: every patch is in
exactly one row, and every diagnostic has a label.

`tools/assets.py` bakes `assets/SR2PatcherLogo2.png` and
`assets/SR2PatcherIcon.png` into the script as the logo and the window
icon, and writes `assets/icon.ico` for the exe. Run it after changing
the artwork. Never edit the blob by hand.

`tools/guitest.py` drives the window under xvfb. It checks what each
button is offered for, which cards start open, that every description
opens, and that the disc and folder probes run off the window's thread.
It skips when there is no display; CI installs xvfb. Its first pass
needs no display: it measures every pair of `PALETTE` colours that
carries meaning against the contrast WCAG asks for, which is 4.5:1 for
text, 3:1 for a border or a tick, and 1.25:1 between each surface and
the one behind it. The colours were quantised out of the box art, the
Stratos watercolour and the cabinet. To change one, pick a new colour
from the artwork and then measure it. The band behind the logo is an
image, because the canvas does not antialias; it is redrawn once a
resize has stopped.

The window opens `LINE_CAP` lines of its own text tall; 48 lines puts the
heading of the last numbered card on screen. `winfo_screenheight`
reports every monitor together, so it serves only as the upper bound.
`_settle_height` re-measures the window for the first half second after
it is mapped, because nothing measured before that can be trusted. Then
it stops, so the window can be dragged.

## The Windows build

The Windows release is Python as python.org ships it, unpacked, with a
small exe to start it:

- `_internal/` holds `pythonw.exe` and `python.exe`, their DLLs and
  Tcl/Tk, the standard library compiled into `python312.zip`, certifi,
  the stamped script as `sr2-patcher.py`, and `net/MGNetWk.dll`.
  `tools/bundle.py` copies it out of the Python it runs under.
  `python312._pth` limits that Python to what it lists, so nothing from
  an installed Python or `PYTHONPATH` gets in.
- `sr2-patcher.exe` beside it is the launcher, `launcher/launcher.c`. It
  runs `_internal\pythonw.exe _internal\sr2-patcher.py` with its own
  arguments and returns the exit code. Python's stderr goes to a
  temporary file. If Python exits with an error and wrote to it, the
  launcher shows the text in a message box, or copies it to its own
  stderr when that is a file or a pipe.

It is not PyInstaller because scanners match on PyInstaller's
bootloader and packed archive.

To build it by hand on Windows, with certifi installed and a Visual
Studio C++ toolset:

    python tools/bundle.py dist\sr2-patcher
    launcher\build.bat %CD%\dist\sr2-patcher\sr2-patcher.exe

The `windows` job in
[.github/workflows/build.yml](../.github/workflows/build.yml) does the
same on every push to main and on a tag, after `verify`. It uses Python
3.12.10, pinned so each release ships the same files. It stamps the
version from the tag, or from the short SHA, and checks that the bundle
has what the patcher needs. Then it runs `--selfcheck` through the
launcher, opens Tk with the bundled Python, and checks that a script that
raises comes back as a failure with its traceback. On a tag it hands the
build to the `sign` job instead of zipping it (*Signing*, above).

### The committed launcher

A release ships `launcher/sr2-patcher.exe`, a signed launcher committed
to the repository, not the one the job compiles. Scanners and SmartScreen
judge a file by its hash, so an unchanged exe keeps its reputation and
one Microsoft submission covers every release. The job still compiles
the launcher so the source stays buildable.

To change the launcher:

1. Change `launcher/`, raise the version in `launcher.rc`, and delete
   `launcher/sr2-patcher.exe`, in one commit.
2. Tag a release. With no committed launcher, the job ships the one it
   compiled and `sign` signs it.
3. Take `sr2-patcher.exe` out of that release's `-win.zip` and commit it
   as `launcher/sr2-patcher.exe`.

The `verify` job fails if the committed launcher is not validly signed,
or was committed before the last change to `launcher/launcher.c`,
`launcher.rc`, `build.bat` or `assets/icon.ico`.
