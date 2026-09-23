# Widescreen

The widescreen patch: what the game assumes about 640x480, and what the
four patches - `widescreen` in the exe, `widescreen3d` in `MGameGL.dll`,
`widescreen2d` in `MGameD3D.dll`, `resolution` in `Options.dll` - do about
it. For the sites see [NOTES.md](NOTES.md)'s table; for the sources see
[asm/README.md](../asm/README.md), *wide.asm, widegl.asm, wide2d.asm,
resolution.asm*; for the two trace diagnostics see
[DEVELOPING.md](DEVELOPING.md), *Diagnostics*.

The picture is rendered at the chosen size, with the 3D's field of view
widened to match. The 2D - menus, HUD, text - is drawn in 640x480 terms
by every screen and is scaled to a 4:3 box in the middle of the picture,
with three exceptions: tiled backgrounds are carried out to the edges,
picture screens get side bars of the picture itself, and the race HUD is
anchored to a 16:9 frame.

## The setting

The stock resolution setting is one dword in the game object,
`settings+0x50`, 0 or 1, kept in `SR2_SAVE.DAT` (an obfuscated file,
`0x44f710`). 1 switches the loader to `BINDATA\800x600\` for the root
files and is read as a yes/no by a dozen places in the exe (`0x4188bf`,
`0x418a74`, `0x421852`, `0x427893`, `0x451e8f`, `0x4630da`, `0x463414`,
`0x463459`, ...) and by the screen DLLs' own loader copies, so it cannot
hold anything else. And 800x600 is the front end only: `0x451e8f` forces
mode 0 for the race screens (4-0xe), so the race is always 640x480.

The mode setter `0x4219f0(mode)` stores the mode at `0x4d5e54`, returns
1 when it is unchanged, and otherwise puts 640x480 or 800x600 (the
American exe also 1024x768 behind `0x4efa1c`) into the init struct's
`WIDTH`/`HEIGHT` and re-inits the renderer, the textures (`0x421450`) and
the viewport and projection (`0x4216a0`).

The wide size is therefore its own setting, `[Display]` / `Resolution =
1920x1080` in the `SR2.CFG` text, one of the patcher's table
(`RESOLUTIONS`) past the stock two. `wide.asm` reads it with
`GetPrivateProfileStringA` at every call of the mode setter: mode 0
takes it, mode 1 stays 800x600, and the setter's entry compare is made
to fail once when it changes.

Stock calls the setter at the screen-change routine (`0x451e8a`) only
for the race screens, and for the front end's only on some of the ways
in (`0x4504a9`, `0x450661`), so a size chosen in Options waited for a
race. The routine's settings load now goes through the stub, which reads
the file and calls the setter with the front end's mode when the size
differs from the one in force, so the new size applies at the next
screen change wherever it goes. The Options page writes the setting with
the Write counterpart and stores 0 in `+0x50` for a wide entry; the
controls save in `padinput.asm` copies the section through, since it
rewrites the file.

There are two tables (`RESOLUTION_TABLES`): the full one, and one with
nothing over 2048 a side, the largest target Windows' own Direct3D
takes (NOTES.md, *The size of the target*) - the standard sizes up to
1920x1200, and for 21:9 and 32:9 the halves of 2560x1080, 3440x1440 and
3840x1080. `patch()` writes the capped one on Windows proper without the
dgVoodoo 2 add-on, the full one otherwise; the present stretches the
picture into the window either way.

## The 3D

In `MGameGL`, `widegl.asm`. The projection is set in `SetPerspective`
(`0x10003870`: focal = width / (2 tan(fov/2)), the angle horizontal,
84.375° for the race at `0x421819`, 15360 in 65536ths of a turn) and the
viewport in `SetViewport` (`0x100037c0`; rect, centre). The exe's
wrapper (`0x46bf90`, `0x46bfd0`) is one caller; MSelect sets the car
select's viewport and perspective on the renderer itself, Champagn its
perspective; so the two methods are taken at their prologues.

**The rects.** Every rect but the picture's own full one - the table at
`0x4b12f0` (full, top 0-224, bottom 256-480), the DLLs' literals, the
countdown's zoom at `0x41905f`, which scales the 640 frame about its
centre to more than 640x480 - is in 640x480 terms and is scaled to the
whole picture; the full one, which only the exe's re-init sets, passes.
A rect narrower than the 640, or not about its middle (left + right ≠
640), is a window and goes into the picture's 4:3 box - x by height plus
the bar - as the 2D around it does, with the angle left at 4:3 while it
is set (*The credits*).

**The centre.** The projection centre goes by height and the bar, as the
2D does: the middle is the middle either way, but a centre the game sets
off it - the transmission select's, at 168, which puts the car left of
the spec panel - keeps its place against the panel instead of moving out
with the width.

**The angle** becomes 2 atan(tan(a/2) · (W/H) / (4/3)) while the
picture is wider than 4:3: the 4:3 vertical field, the extra width
showing more, whatever camera set it (the exe never culls on the angle
it keeps at `+0x563c`).

**The size** is MGameD3D's, its dwords at `0x100123fc`/`0x10012400`
through `GetModuleHandleA`: MGameGL's own floats (`0x100128d8`,
`0x100128d4`) are set at its one init and stay 640x480 through every
resize.

### The other four methods

Four more methods set or hand back the same numbers and are taken the
same way, on the rule that a caller of the renderer thinks in 640x480
terms, because what it does with the answer goes through the 2D.

- `SetCentre` (`+0x38`, `0x100039e0`; cx, cy) is the centre alone. The
  name entry after a time attack (exe `0x434037`) sets (320, 240)
  through it and never through `SetViewport`, so its 3D letters, models
  drawn through the renderer, sat about the picture's own pixel (320,
  240) - the top-left corner of a wide one, clipped by its edges. The
  centre is scaled as `SetViewport` scales one.
- The screen-space projection (`+0x78`, `0x10003a80`; &out, &point)
  makes a point's screen position as the centre plus the offset at the
  focal, and the focal is `0x100128d8`'s 640 over the tangent of the
  (widened) angle whatever the width: the offset comes out in the units
  of a picture 640 wide, about a centre in real pixels. The exe draws
  sprites at those positions through the 2D - a triangle list at
  `0x45510f` of points projected at `0x454ea6`, a strip at `0x407965`;
  neither has been seen to run in a race yet - and wide2d would scale
  them once more as 640x480, off the picture's right edge at any wide
  size. The entry runs the method and converts its result into 640x480
  terms - the centre as it was asked for, the offset by (W/H)/(4/3),
  which is what the 3D's real-pixel offset is to the 640x480 one - so
  wide2d puts the sprite where the 3D projects the point.
- The parameter getter (`+0x48`, `0x100033f0`; ids 4, 7, 8) and the
  inverse projection (`+0x7c`, `0x10003ae0`) are what the lake on
  Mountain is built from (*The sea*): `MGLBackground` makes its ground
  plane's depths from the focal and the centre it asks the renderer for
  once, through the getter, and its texture coordinates through the
  inverse. With the real-pixel centre and the widened angle's focal
  against y in 640x480 terms, `y - cy` went negative on a wide picture
  and every vertex's z came out above 1 (1.10-1.18 at 5120x1440 against
  0.97-1.00 at 640x480, in `d3dtrace`), which wined3d drops. The getter
  answers the three in 640x480 terms and the inverse takes its point in
  them, so the plane is built as at 4:3.

The rect-only `SetViewport` (`+0x34`, `0x10003370`) has no caller seen
and is not taken.

Tried and taken out: mapping a screen DLL's rect to the 4:3 box instead,
for the car select's carousel that leans on the 640 frame's edges to
hide six of its seven cars. The device's viewport clips the 2D as well,
and the sides went with the cars, so the carousel is still open.

## The 2D

In `MGameD3D`, `wide2d.asm`. Every screen DLL, MainMode and the exe draw
their sprites, text and HUD as pre-transformed geometry, FVF `0x1c4`, in
640x480 pixels straight to `DrawPrimitive`, through six draws:

| Entry | Method | Draw |
| --- | --- | --- |
| `+0xb4` | `0x10005120` | quad |
| `+0xb0` | `0x100050d0` | triangle |
| `+0xb8` | `0x10004fe0` | list |
| `+0xc4` | `0x10005170` | indexed list (the race's HUD text from `0x429f11` and its neighbours) |
| `+0xbc` | `0x10005030` | strip |
| `+0xc0` | `0x10005080` | fan |

MGameGL's 3D is untransformed - FVF `0x1e2` or `0x112` (`0x1000d970`),
the device transforms it through the matrices it sets - so every `0x1c4`
draw is 2D, whichever entry.

The six entries' vertices are scaled into a copy (2048 vertices; a
longer list goes as it is), by height and centred - the 4:3 layout in
the middle of the picture. Then the exceptions:

- A quad spanning the whole width (a fade, a background) is stretched
  across.
- A quad or triangle with a vertex at one edge of the 640 is drawn out
  to the picture's edge on that side, with its texture coordinate
  shifted at the quad's own rate for the distance the vertex moves, so a
  tiling texture goes on, scrolling or not. Only a tile-sized quad (128
  px or less each way) is carried out this way; a wider or taller one at
  the edge is a picture or a strip of one - the mode select's collage -
  and keeps its 4:3 place, with the picture itself stretched into the
  side area beside it (*The side bars*).
- A quad at the edge with no texture selected (`+0xac`, cached at
  `0x10011224`, bit 31) is a plain cover and its edge goes out to the
  screen's (*The credits*).
- A clamped tile (the texture addressing, `+0xf8`, cached at
  `0x10011240`) has wrap set for its draw through the method, as the
  Options background needs; the course select's tiles wrap already.

A tile is told from a sprite of the same size by the frame before: every
quad's width goes into a table (16 widths, each with its count of quads
and the extent they covered), the present (`+0x80`, `0x10004d50`) closes
the frame's table and keeps it, and a quad at the edge is drawn out only
when its width covered the whole 640x480 last frame with six quads or
more. Without that rule the Options icons and buttons sliding through
the edge, and the car select's outgoing car, were repeated across the
side area.

### The HUD's frame

In a race the HUD is anchored to a 16:9 frame rather than the 4:3 box: a
2D draw wholly in the left part of the 640 (no vertex past 268, 0.42 of
the width: the speed ends at 256, the countdown starts at 291) has its
bar reduced, and one wholly in the right part (none short of 372) its
bar raised, by min(bar, 2H/9) - the 4:3 box's edge to the edge of a 16:9
frame no wider than the picture. So at 16:9 the tachometer, the times,
the position and the car's name sit at the picture's edges, on 21:9 and
32:9 at a centred 16:9's, and at 16:10 at the picture's; 4:3 has no bar
and moves nothing. The middle - the countdown, the arrows, the results -
keeps its place, as does a draw touching the 640's edges, which is a
tile or a fade.

A list of quads (four vertices each) is moved a run at a time - the
race's text is one indexed list of glyphs from both sides of the screen,
and a run is the quads in a row whose left ends fall within 16 px of the
run's right end so far, a string; a strip or a fan goes as a whole. The
speed's digits are single quads each, so the split falls where no
element straddles it.

**What is HUD** is settled by who draws it. The race's HUD is a set of
elements on the exe's element list (`0x4e6948`, registered through
`0x401260` with a callback at `+0xc` and drawn by the walker `0x4010d0`,
which calls each callback with the element pushed), and so are the
results overlay and the credits, with callbacks elsewhere. The exe's
`wide.asm` takes the walker's callback call (`0x4010e5`, `push eax; call
ecx; add esp, 4`, the same in every build): it sets a flag before a
callback in the HUD's range (`HUDLO`-`HUDHI`, `0x42ac60`-`0x42ffc0` in
the European exe: the thirty-two callbacks the race's HUD setup at
`0x429228` registers, nothing else on the list in between; per build),
and `wide2d` anchors the frame's 2D while it is set and clears it at the
present.

It has to be the frame and not the callback: the callbacks queue their
strings, and the screen's tail draws the lot as one indexed list
(`0x418ab1` calling `0x429d70`) after the walker has finished, so a flag
cleared after the callback caught the tachometer and nothing else. The
flag is `wide2d`'s, after its `HUDFRAME` marker in `MGameD3D`'s annex,
found through the device object as `bgrow` finds its block and kept once
found.

The flag is a frame's, but the anchoring is a draw's: a frame that
draws the HUD draws other things as well, and they are not HUD. So the
walk entry writes `HUDDRAW`..`HUDHI` - the HUD's own draw and the last
of its callbacks - into the two cells after the flag, and `wide2d`
anchors only a draw returning between them. The race's own draws are
`0x429f17`, `0x429fd2`, `0x42a08d`, `0x42a0c6` (the tail's list),
`0x42a217` and `0x42e6b3`, all inside; the results row - the stage name,
BEST LAP and TOTAL TIME, one glyph list each from `0x447663`,
`0x447948` and `0x447b68` - is outside, and used to be torn in two by
the run rule, half of TOTAL TIME moved to the picture's edge and half
left at the 4:3 box's. With the bounds it keeps its 640x480 place
whole. Bounds of zero - an exe patched before this - anchor as before.

Two refinements:

- A list from a HUD callback is anchored whatever edge it touches. The
  anchoring left alone any draw with a vertex at the 640's edges, a tile
  or a fade for `extend`, and the race's position piece - a string from
  591 whose two-digit place reaches 639 - fell under that and sat at the
  4:3 box's edge until the place shortened, which in split screen was
  the right side of the HUD for the first seconds of a race (a
  `d3dtrace` of one: the piece `0x429fd2` draws at x 591 every frame). A
  list is text, never a tile, so the edge rule applies to quads,
  triangles, strips and fans only.
- Split screen's position bar is left alone. The band between the
  halves (the quad `0x42a217` draws at y 224, 32 tall) carries a bar
  drawn through MGameGL, which the anchoring never sees, and along it
  the cars' icons (a list of three quads from `0x42f7dc`, y 237 to 250)
  and their 1P/2P labels (glyphs in the race's list, y 225 to 235),
  which it did: at the bar's left end at a race's start they sat at the
  16:9 frame's edge instead. A piece whose vertices all lie between 224
  and 256 down stays where it is; the lower half's own text starts at
  252 and reaches below, so it still moves.

Three things tried first and taken out: the screen id at the
screen-change routine (4-0xe turned out to be the 3D front end - the car
select, the name entry - and the race showed as neither those nor
0x11-0x12); a car in the exe's car table, which is true through the
results and the credits as well, whose centred tables then broke at the
split; and `wide2d` looking up the stack for the walker's return over
the element, which found stale copies of it in uninitialised locals and
crashed on what lay beside them.

### The side bars

A quad at one edge that is wider or taller than a tile, and at least 160
tall (a plate sliding through the edge is wide but not tall), is a
picture or a strip of one. The mode select's backdrop is
`BINDATA\MISC\MAINMODE.TXR`, a 640x480 collage in five 256x256 tiles,
and `TITLE.TXR` is the same layout. It keeps its 4:3 place, and the side
area beside it gets the picture itself, stretched: the texture is still
bound when the quad is drawn, so the bar is a quad covering the side
area with that texture on it and its coordinates carried past the quad's
own edge.

What it shows is the 640's own sliver - a bar's share of the picture's
width, in from that end, and no further in than the quad itself reaches,
since a tile holds only its own part of the picture - spread across.
That is the mapping `bgrow` uses for the `.bg` screens, so the two look
alike; a tile ends where the next begins, and the bars meet as the tiles
do. A quad running past the 640 - the mode select's right-hand tiles
reach 768 - has its bar started at the 640, not at its own edge, which
would be off the picture.

**The blur** across it is the device's: the quad is drawn sixteen times,
spread across twenty of the 640's pixels in u - a thirty-second of the
picture, which the eightfold stretch makes some 160 on the screen - each
at 17/256 of the quad's diffuse dimmed to two fifths, with blending
turned on (`+0xe8`, its old state cached at `0x10011234`) and both
factors ONE (`+0xec`) so the passes add: sixteen shares of 17/256 make
255 for 255. `+0xfc` puts the filtering to linear for them and `+0xf8`
the addressing to clamp, so a pass shifted past the texture's edge
carries its last column out; blending goes back as it was after and the
factors to source-alpha and its inverse, the pair the game's own
blending wants.

Note which states these methods set: `+0xfc` is `TEXTUREMAG` and
`TEXTUREMIN`, 17 and 18, and the blend factors are 19 and 20 under
`+0xec` - set the wrong pair and the passes overwrite one another
instead. Four passes a sixteenth of the sliver apart, an earlier try,
showed as four copies; sixteen a hundred-and-twentieth apart read as a
smear.

**What may be drawn from** is settled at the load, by the texture
create's entry (`0x1000411c`, esi the texture's number, ebp its
description: pixels, size, flags): a picture; one so nearly black that a
bar of it should be black instead - three quarters of its pixels dark,
which is `empire.txr` and `segalogo.txr`, black but for the logo; or
nothing, which is a sprite, a palette or a render target. One word per
texture number, 128 of them. The logo screens are textures, not `.bg`
pictures: they come through here and not `bgrow`.

The description's flags are a bitfield, not the TXR's format alone: bit
3 is 4444 and the palette and render-target bits (`0x700`, `0x1000`) are
skipped, everything else read as 1555. By the create a format-0 texture
is 1555 with bit 15 set, not 565 - the screen DLLs' loaders (MainMode
`0x10006b80`, the others the same library) expand it in place - so 0 and
2 read alike.

With `d3dtrace` on, every quad that reaches the bar's decision reports
it, and every texture create its kind; DEVELOPING.md, *Diagnostics*, has
the formats.

### The .bg screens

The `.bg` pictures go through `bgrow.asm` (NOTES.md, *Windowed*), which
is built twice, and the build is the screen: `Title.dll`'s copy loop
draws the title screen and nothing else, the exe's the loading,
game-over and course screens and nothing else, so what a bar should be
is settled at assembly with no look at the pixels.

In `Title.dll`'s build the bars carry the picture behind them, the whole
of it stretched to the surface's width with the drawn one over the
middle - so each bar shows the sliver past the drawn edge spread across
its width - with the same motion blur and dimming as the textured
screens: each row's sliver is box-blurred, every column the mean of
those a sixty-fourth of the width either side, a running sum that stays
inside the sliver so the picture beside the bar does not bleed into it,
at two fifths of the picture's brightness.

In the exe's build the screens are pictures on a plain background -
white, or `loading.bg`'s black - whose slivers reach well into the
picture, so each bar is that background - the picture's corner pixel -
throughout, and nothing more; the row's own edge would carry the card's
blur and its red rule out as streaks.

**The composite.** Neither build stretches anything itself. Drawing the
scaled picture and its bars into the locked back buffer was some seven
million CPU pixel writes a frame at 5120x1440, the same cost that made
the lobby drag. Instead `bgrow` composes the picture at source size into
a surface `MGameD3D` keeps - 2176x600, offscreen plain in video memory,
made at the present through the same `CreateSurface` as the lobby's -
and one blit stretches the composite into the whole screen, video memory
to video memory. The composite is the picture in the middle, each side
area beside it as its sliver, blurred or plain, pre-stretched by the
picture's width over the screen's into the side area's columns so the
one uniform stretch after makes the bar's own eightfold one, and the
bands above and below as the first and last rows.

`bgrow` finds the surface through the exe's device object (`GAMED3D`,
which `Title.dll`'s build reads from the exe too, the exe being at a
fixed base): its vtable is `MGameD3D`'s at `0xf5d4`, so the base falls
out, and the annex from `0x17000` is scanned for the block's marker
`BGBLOCK`, the blob's place in it depending on which patches went in.
The block holds the surface, the composite's size and a flag; `bgrow`
locks the surface, composes, unlocks, sets the flag and touches the back
buffer not at all.

The lock's description has to hold the composite - its width and height
when the lock gives them, and a pitch of at least the composite's row at
the depth the lock reports - or the surface is unlocked untouched and
the picture drawn as before: under Proton-CachyOS 10.0 the lock reported
32 bits over a surface whose rows were not that long, and the bars ran
off its end (a write fault in `Title.dll`'s `stretch`, the right bar's
351st column); 11.0 gives a surface the composite fits.

The stretch cannot happen there, the game holding the back buffer locked
around the row copy, so it happens at the next draw through `MGameD3D`,
or the next present, whichever comes first - before any 2D the game
draws over the picture, since that goes through the same draws. Without
a device, a block or a surface, or with a composite too big for it,
`bgrow` draws as it did. Split screen comes out of the rect scaling.

### The lobby

The multiplayer lobby is the one screen that is not a draw at all: the
exe blits its BMP strips - the background, the chat panel composed
offscreen, keyed icons - into the back buffer itself through
`IDirectDrawSurface4::Blt`, at 640x480 coordinates (a `+ddraw` trace
shows them all: `(0,0)-(640,480)`, `(126,118)-(524,405)`,
`(611,451)-(635,475)` into the surface the present then blits to the
primary, which is `MGameD3D`'s back buffer at `0x10012554`; never
`BltFast`), so the whole screen sat in the picture's top-left unscaled.

`wide2d.asm`'s present hooks that `Blt` in ddraw's own vtable - shared
by every surface, so it is done once, with `VirtualProtect` around the
write. Scaling each blit into the box was the first version, and made
the menu drag: every one became a stretch, and Wine stretches on the
CPU.

Now the lobby draws into a 640x480 surface of its own, made through
`IDirectDraw4::CreateSurface` (`[0x1001254c]`, offscreen plain in video
memory, the primary's format) the first time it is wanted and again
after a mode change has given the game a new back buffer. Every `Blt`
into the back buffer whose rect is a 640x480-sized one within a screen
of the 640x480 - a panel sliding in starts off the picture, past 640 or
below 480 - has its `this` swapped for that surface and its rect cut to
640x480, the source rect cut by the same share, since a rect off a
surface fails the blit and the screen's edge cut a sliding panel at 4:3;
a rect with nothing left is not drawn, DD_OK. So the lobby draws exactly
as it did into a 640x480 back buffer.

At each present, for eight presents after the last such blit (the lobby
draws only what changes, and the back buffer keeps between presents),
that surface is stretched into the 4:3 box with one blit, video memory
to video memory, and the side areas filled with a colour-fill blit each:
the background's colour, read from the surface behind the one blit that
is the whole 640x480 at (0, 240) - the plain part, left of the panel and
between the title bands - under a read-only lock, at 16 or 32 bits as
its format says.

Under dgVoodoo 2 that background blit came back DD_OK and black: the
game's background was a 640x480 video-memory surface (caps
`0x10004040`) which dgVoodoo blits as empty while a `Lock` of it reads
the picture whole. `surfmem` puts it and the lobby's other offscreen
surfaces in system memory (NOTES.md, *The lobby's panels*), where the
blit carries it; the copy below stays a fallback. So after the first
background blit the lobby surface's pixel at (0, 240) is read back and
compared with the source's; the same, the blit serves from then on;
different, the background is copied through `Lock` on both surfaces,
row by row, that time and every time after, without a blit. The blit
goes on serving on Windows' own DirectDraw and under Wine.

A rect bigger than 640x480, a null one, or another surface's, passes; so
does everything, unchanged, when the surface cannot be made, and
`d3dtrace` reports the create as `sr2 l hr ddraw surface`, every blit
sent to the lobby's surface as `sr2 x` and the two surfaces as `sr2 s`
(DEVELOPING.md, *d3dtrace*). The GDI text
is rasterised at 640x480 and stretched with the rest. `DDSURFACEDESC2`'s
`ddsCaps` is at `0x68`, after the 32-byte pixel format at `0x48`; the
caps written four bytes on land in `dwCaps2`, and a surface asked for
with no caps is refused.

The sides were tried two other ways first: the background's first column
stretched across, which came out as streaks of the surface's dither, and
a strip of it tiled at the box's scale, which came out with pieces of
the title in it - the title is composed into that surface - and mirrored
to hide the seams went through Wine's CPU blitter.

### The device viewport

The exe draws the countdown digit itself, an untransformed indexed list
(`0x42bd2f`, FVF `0x1e2`), after setting the device's viewport itself
(`0x42bcda`, MGameD3D's `+0x158` of the second interface, `0x10006040`)
from its own table at `0x5b24f0` - 640x480, the split-screen halves, the
800x600 set, each with the projection-centre fractions. The four numbers
are a rect, left, top, right and bottom, not a corner and a size: the
setter takes the width from right minus left (`0x1000605f`). They are a
path MGameGL's `SetViewport` never sees, which put the digit in the
picture's top-left 640x480.

`wide2d.asm` takes that setter too: a rect no wider than 640 and no
taller than 480 while the picture is wider is scaled through a copy into
the picture's own 4:3 box, everything by the height and both its sides
carried past the bar, exactly as the 2D is scaled; MGameGL's rects, in
real pixels, pass.

The rect alone does not settle the digit's size: the setter makes the
clip volume from the rect's share of the *screen* - `clipW = 2 w /
(screenW · f1)`, `clipH = 2 h (screenH / screenW) / (screenH · f2)`,
with `0x10012420` and `0x10012424` the display size from the device's
creation and f1, f2 the two floats at the end of the struct - so a rect
the size of the 4:3 box on a 32:9 screen holds three eighths of the clip
width the 4:3 screen has, and what is in it is drawn as large as a
viewport the whole screen wide would draw it. The two fractions take the
box's share of the screen's width, which brings the clip volume back to
the 4:3 screen's 2.0 by 1.5. Scaling the rect to the whole picture, as
the first version did, was worse again by the ratio of the widths.
`d3dtrace` found it (every draw with its caller), after `gltrace` had
ruled out the renderer's paths.

## The sea

The race's backdrop below the horizon is a layer the exe builds at the
race's start (`0x448c70`, one over (0, 256, 640, 480) - two in split
screen - `.SEA` loaded at `0x462b80`, the object made at `0x462e10` with
the class at `0x49dca4`, its update `0x4633b0`, its draw `0x463500`) on
an `MGLBackground` layer (interface `452593f2`, class vtable
`0x1000b0f0`: init `0x100030a0`, update `0x10003360`, draw `0x10003de0`).

The init lays a grid of 64-px cells over the rect widened by 96 px a
side, four rows of a 28-vertex strip, each vertex's depth `-h * focal /
(y - cy)` and its z and rhw from the renderer's `+0x40` and `+0x44` at
that depth, its texture coordinates from the inverse projection at it;
the update rotates it about a point by the camera's roll and drops it by
the pitch, and scrolls the texture; the draw is four strips of FVF
`0x1c4` through `+0xbc`, fog off. The lake is that plane through a hole
in the ground mesh. `sky*.mdl` is the sky.

In split screen there is no lake, and that is the game's own doing: the
sea's draw (`0x463500`) opens with `cmp dword [game+0x38], 5; je`
(`0x463517`), mode 5 being split screen, and draws nothing there, so the
hole shows the backdrop. The two layers the exe still makes for split
screen (the table at `0x4bc080`) are built before either half's
viewport is set, both about the full screen's centre (320, 240) - a
`gltrace`: the six `gp` reads come right after the exe's full-screen
`vp`, the halves' fourteen lines later - so the top one's rows all lie
above its horizon and its z above 1, the bottom's horizon is 128 rows
above its own; presumably what Sega saw, and switched the draw off
rather than fix.

Tried and taken out: each half's viewport set before its layer through
the exe's `SetViewport` wrapper (`0x46bfd0`), which gave the layers the
right centres, and the `je` made nops, which would have drawn them. The
Dreamcast has no lake in split screen either, so it stays as shipped.

## The credits

The ten-year championship ends on the credits: the race state's
sub-state 8 (`0x419af0`), which replays year ten's Super S.S. in a window
at 351-607 x 222-415 while the names scroll. The window is the race's
own scene pass (`0x418f30`, mode 4 with flag `0x20`): the countdown full
screen, then the frame shrunk about the window's centre in 32-px steps
to the window, through the exe's `SetViewport` wrapper (`0x41905f`), and
the rest blacked out by untextured quads from the credits' draw
(`0x48672a`, in `0x48656c`): the bands above and below full width, the
side pieces from -1 to the window's left and from its right to 642. The
per-frame clear is MGameD3D's, a `Clear2` with one rect that is the
whole back buffer (`0x10012410`, `SetRect(0, 0, W, H)` at its init,
`0x10005f40`), never the viewport.

Two things went wrong on a wide picture: `widegl` scaled the window's
rect to the whole width as it does the race's, so the replay rendered
beside its black frame; and the side pieces, scaled into the 4:3 box as
2D is, left the clear showing in the side areas at the window's rows (a
`d3dtrace`: `sr2 b` why 3 for both pieces, nothing drawn). So a viewport
rect that is narrower than the 640 or off its middle goes into the box,
and a quad at one edge with no texture selected is drawn out to the
screen's edge. The fade at the end is the window's own, a quad over the
right half whose alpha ramps as the replay ends.

For a test without a year-ten save: the results step (`0x419830`) hands
on to the season's end step (`0x419a70`) only after a year's last stage,
`cmp [game+0x64], 3; je` at `0x4198fc`, and that step to the ending only
in year ten, `cmp eax, 0xa; jne` at `0x419ab7`; a `jmp` over the one and
nops over the other roll the credits after any stage. There is then no
Super S.S. replay to play, so the window shows an unlit car at 0'00"000
and fades at once; the zoom and the window's place are what can be
checked that way.

## The Graphic Settings page

The page (`0x10003370` exec, `0x10002f20` draw; the page object at
`Options+0x14`, rows at `+0x18`, counts at `+0x58`, cursor `+0x10`, pulse
`+0x78`) showed the row's two choices side by side from sprites
(`0x1009c714`) and greyed the second without the 800x600 capability bit
(`0x10003426`).

`resolution.asm` makes the row a list and adds an ASPECT RATIO row under
it. The table is grouped by aspect (`RESOLUTION_GROUPS`, five groups,
the 21:9 sizes 64:27, 43:18 and 12:5); row 7 holds the group and row
6 the index within it, its count the group's; a change of aspect puts
row 6 to the group's first at the next draw.

Row 7 is the page's own machinery - the page object has room for sixteen
rows and left and right are generic - with the page's six "7"s (the
value loop's bound, the button-row tests in the exec) made "8" so the
cursor reaches it. Its plate is row 6's drawn 27 px lower with the
loop's colours, its label and value text through the stock 14-px routine
(the font has no colon: two dots, one 6 px up). Both values start at the
first choice sprite's place, as the rows above do (`1920X1080`, `21:9`;
no lowercase, no arrows): the aspect's colon goes after its left part,
measured through the routine's own character map and glyph advances. A wide size in `SR2.CFG` that is in the table
selects its group and entry on entering, and DEFAULT gives 640x480 in
4:3.
