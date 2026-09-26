# Widescreen

This document describes the widescreen patch: what the game assumes
about 640x480, and what the four patches do about it. The four are
`widescreen` in the exe, `widescreen3d` in `MGameGL.dll`, `widescreen2d`
in `MGameD3D.dll` and `resolution` in `Options.dll`. The patch sites are
in [NOTES.md](NOTES.md)'s table. The sources are described in
[asm/README.md](../asm/README.md), *wide.asm, widegl.asm, wide2d.asm,
resolution.asm*. The two trace diagnostics are in
[DEVELOPING.md](DEVELOPING.md), *Diagnostics*.

The picture is rendered at the chosen size, and the 3D's field of view
is widened to match. Every screen draws its 2D - menus, HUD, text - in
640x480 terms, and the patch scales that 2D into a 4:3 box in the middle
of the picture. There are three exceptions: tiled backgrounds are
carried out to the picture's edges, picture screens get side bars made
from the picture itself, and the race HUD is anchored to a 16:9 frame.

## The setting

The stock resolution setting is one dword in the game object,
`settings+0x50`, holding 0 or 1. It is kept in `SR2_SAVE.DAT`, an
obfuscated file (`0x44f710`). A value of 1 switches the loader to
`BINDATA\800x600\` for the root files. A dozen places in the exe
(`0x4188bf`, `0x418a74`, `0x421852`, `0x427893`, `0x451e8f`, `0x4630da`,
`0x463414`, `0x463459`, ...) read the dword as a yes/no, and so do the
screen DLLs' own copies of the loader, so the dword cannot hold anything
else. 800x600 is also the front end only: `0x451e8f` forces mode 0 for
the race screens (4-0xe), so the race is always 640x480.

The mode setter, `0x4219f0(mode)`, stores the mode at `0x4d5e54` and
returns 1 when the mode is unchanged. Otherwise it puts 640x480 or
800x600 into the init struct's `WIDTH`/`HEIGHT` (the American exe also
has 1024x768, behind `0x4efa1c`) and re-inits the renderer, the textures
(`0x421450`), and the viewport and projection (`0x4216a0`).

The wide size is therefore a setting of its own: `[Display]` /
`Resolution = 1920x1080` in the `SR2.CFG` text, one of the sizes in the
patcher's table (`RESOLUTIONS`) past the stock two. `wide.asm` reads it
with `GetPrivateProfileStringA` at every call of the mode setter. Mode 0
takes the wide size and mode 1 stays 800x600. When the wide size
changes, the setter's entry compare is made to fail once, so the setter
re-inits.

Stock calls the setter at the screen-change routine (`0x451e8a`) only
for the race screens, and for the front end only on some of the ways in
(`0x4504a9`, `0x450661`). So a size chosen in Options took effect only
when a race started. The routine's settings load now goes through the
stub. The stub reads the file and, when the size in the file differs
from the one in force, calls the setter with the front end's mode, so
the new size applies at the next screen change wherever it goes. The
Options page writes the setting with the Write counterpart and stores 0
in `+0x50` for a wide entry. The controls save in `padinput.asm`
rewrites the file, so it copies the section through.

There are two tables (`RESOLUTION_TABLES`). One is the full table. The
other has nothing over 2048 a side, which is the largest target Windows'
own Direct3D takes (NOTES.md, *The size of the target*): the standard
sizes up to 1920x1200, and for 21:9 and 32:9 the halves of 2560x1080,
3440x1440 and 3840x1080. `patch()` writes the capped table on Windows
proper without the dgVoodoo 2 add-on, and the full table otherwise. The
present stretches the picture into the window either way.

## The 3D

The 3D is `MGameGL`'s, and `widegl.asm` handles it. `SetPerspective`
(`0x10003870`) sets the projection: focal = width / (2 tan(fov/2)),
with the angle horizontal. The race's angle is 84.375°, set at
`0x421819` as 15360 in 65536ths of a turn. `SetViewport` (`0x100037c0`)
sets the viewport: a rect and a centre. The exe's wrapper (`0x46bf90`,
`0x46bfd0`) is only one of the callers. MSelect sets the car select's
viewport and perspective on the renderer itself, and Champagn sets its
own perspective. So the two methods are taken at their prologues, which
every caller goes through.

**The rects.** Every rect the game sets is in 640x480 terms: the table
at `0x4b12f0` (full, top 0-224, bottom 256-480), the DLLs' literals, and
the countdown's zoom at `0x41905f`, which scales the 640 frame about its
centre to more than 640x480. All of these are scaled to the whole
picture. The one exception is the picture's own full rect, which only
the exe's re-init sets; it passes unchanged. A rect narrower than the
640, or not centred on its middle (left + right ≠ 640), is a window. A
window goes into the picture's 4:3 box, as the 2D around it does: x by
height, plus the bar. While a window is set the angle is left at 4:3
(*The credits*).

**The centre.** The projection centre is scaled by height and offset by
the bar, as the 2D is. For a centre in the middle this changes nothing,
because the middle of the 640x480 is the middle of the picture either
way. It matters for a centre the game sets off the middle. The
transmission select sets its centre at 168, which puts the car left of
the spec panel. Scaled this way, the car keeps its place against the
panel instead of moving out with the width.

**The angle** becomes 2 atan(tan(a/2) · (W/H) / (4/3)) while the
picture is wider than 4:3. The vertical field of view stays the 4:3 one
and the extra width shows more, whatever camera set the angle. The exe
keeps the angle at `+0x563c` but never culls on it.

**The size** is MGameD3D's: the dwords at `0x100123fc`/`0x10012400`,
reached through `GetModuleHandleA`. MGameGL's own floats (`0x100128d8`,
`0x100128d4`) are set at its one init and stay at 640x480 through every
resize.

### The other four methods

Four more methods set or hand back the same numbers, and they are taken
the same way. The rule is that a caller of the renderer thinks in
640x480 terms, because whatever it does with the answer goes through the
2D.

- `SetCentre` (`+0x38`, `0x100039e0`; cx, cy) sets the centre alone.
  The name entry after a time attack (exe `0x434037`) sets (320, 240)
  through it and never through `SetViewport`. Its 3D letters are models
  drawn through the renderer, so they sat about the picture's own pixel
  (320, 240), which is in the top-left corner of a wide picture, and
  were clipped by its edges. The centre is now scaled as `SetViewport`
  scales one.
- The screen-space projection (`+0x78`, `0x10003a80`; &out, &point)
  makes a point's screen position as the centre plus the offset at the
  focal. The focal is `0x100128d8`'s 640 over the tangent of the widened
  angle, whatever the width. So the offset comes out in the units of a
  picture 640 wide, but about a centre in real pixels. The exe draws
  sprites at those positions through the 2D: a triangle list at
  `0x45510f` of points projected at `0x454ea6`, and a strip at
  `0x407965`. Neither has been seen to run in a race yet. `wide2d` would
  scale those positions once more as 640x480, which put them off the
  picture's right edge at any wide size. The entry runs the method and
  converts its result into 640x480 terms: the centre as it was asked
  for, and the offset by (W/H)/(4/3), which is the ratio of the method's
  640-wide offset to the 2D's 640x480 one. `wide2d` then puts the sprite
  where the 3D projects the point.
- The parameter getter (`+0x48`, `0x100033f0`; ids 4, 7, 8) and the
  inverse projection (`+0x7c`, `0x10003ae0`) are what the lake on
  Mountain is built from (*The sea*). `MGLBackground` asks the renderer
  once, through the getter, for the focal and the centre, and makes its
  ground plane's depths from them. It makes the plane's texture
  coordinates through the inverse projection. The plane's y values are
  in 640x480 terms. With the real-pixel centre and the widened angle's
  focal against them, `y - cy` went negative on a wide picture, and
  every vertex's z came out above 1 (1.10-1.18 at 5120x1440, against
  0.97-1.00 at 640x480, in `d3dtrace`), which wined3d drops. The getter
  now answers the three values in 640x480 terms, and the inverse
  projection takes its point in those terms, so the plane is built as it
  is at 4:3.

The rect-only `SetViewport` (`+0x34`, `0x10003370`) has no caller that
has been seen, and is not taken.

Two things were tried and taken out. The first mapped a screen DLL's
rect to the 4:3 box instead of the whole picture, for the car select's
carousel, which leans on the 640 frame's edges to hide six of its seven
cars. But the device's viewport clips the 2D as well, and the sides of
the 2D went with the cars. The second, tried for 0.7.1, cut the 2D at
the 4:3 box's edge instead. The side area is in view on a wide picture,
so the cut showed as a seam mid-picture on every sprite that passes the
edge, the menus' slide-in transitions as much as the carousel. So the
carousel's other cars stay in view beside the chosen one.

## The 2D

The 2D is `MGameD3D`'s, and `wide2d.asm` handles it. Every screen DLL,
MainMode and the exe draw their sprites, text and HUD as pre-transformed
geometry, FVF `0x1c4`, in 640x480 pixels, straight to `DrawPrimitive`
through six draw methods:

| Entry | Method | Draw |
| --- | --- | --- |
| `+0xb4` | `0x10005120` | quad |
| `+0xb0` | `0x100050d0` | triangle |
| `+0xb8` | `0x10004fe0` | list |
| `+0xc4` | `0x10005170` | indexed list (the race's HUD text from `0x429f11` and its neighbours) |
| `+0xbc` | `0x10005030` | strip |
| `+0xc0` | `0x10005080` | fan |

MGameGL's 3D is untransformed: its FVF is `0x1e2` or `0x112`
(`0x1000d970`), and the device transforms it through the matrices
MGameGL sets. So every `0x1c4` draw is 2D, whichever entry it comes
through.

The six entries scale their vertices into a copy that holds 2048
vertices; a longer list goes as it is. The scale is by height, and the
result is centred, which puts the 4:3 layout in the middle of the
picture. Then there are the exceptions:

- A quad spanning the whole width (a fade, a background) is stretched
  across the picture.
- A quad or triangle with a vertex at one edge of the 640 is drawn out
  to the picture's edge on that side. Its texture coordinate is shifted
  at the quad's own rate for the distance the vertex moves, so a tiling
  texture goes on, scrolling or not. Only a tile-sized quad (128 px or
  less each way) is carried out this way. A wider or taller quad at the
  edge is a picture or a strip of one, such as the mode select's
  collage. It keeps its 4:3 place, and the picture itself is stretched
  into the side area beside it (*The side bars*).
- A quad at the edge with no texture selected (`+0xac`, cached at
  `0x10011224`, bit 31) is a plain cover, and its edge goes out to the
  screen's edge (*The credits*).
- A clamped tile (the texture addressing, `+0xf8`, cached at
  `0x10011240`) has wrap set for its draw through the method, which the
  Options background needs. The course select's tiles wrap already.

A tile is told from a sprite of the same size by the frame before. Every
quad's width goes into a table of 16 widths, each with its count of
quads and the extent they covered. The present (`+0x80`, `0x10004d50`)
closes the frame's table and keeps it. A quad at the edge is drawn out
only when its width covered the whole 640x480 last frame with six quads
or more. Without that rule the Options icons and buttons sliding through
the edge, and the car select's outgoing car, were repeated across the
side area.

### The HUD's frame

In a race the HUD is anchored to a 16:9 frame rather than the 4:3 box. A
2D draw wholly in the left part of the 640 (no vertex past 268, which is
0.42 of the width: the speed ends at 256 and the countdown starts at
291) has its bar reduced, and one wholly in the right part (no vertex
short of 372) has its bar raised. The amount is min(bar, 2H/9), the
distance from the 4:3 box's edge to the edge of a 16:9 frame no wider
than the picture. So at 16:9 the tachometer, the times, the position and
the car's name sit at the picture's edges; on 21:9 and 32:9 they sit at
a centred 16:9's edges; at 16:10 they sit at the picture's edges. 4:3
has no bar and moves nothing. The middle - the countdown, the arrows,
the results - keeps its place. So does a draw touching the 640's edges,
which is a tile or a fade.

A list of quads (four vertices each) is moved a run at a time, because
the race's text is one indexed list of glyphs from both sides of the
screen. A run is a string: the quads in a row whose left ends fall
within 16 px of the run's right end so far. A strip or a fan moves as a
whole. The speed's digits are single quads each, so the split falls
where no element straddles it.

**What is HUD** is settled by who draws it. The race's HUD is a set of
elements on the exe's element list (`0x4e6948`). An element is
registered through `0x401260` with a callback at `+0xc`, and the walker
`0x4010d0` draws the list by calling each callback with the element
pushed. The results overlay and the credits are elements too, with
callbacks elsewhere. The exe's `wide.asm` takes the walker's callback
call (`0x4010e5`, `push eax; call ecx; add esp, 4`, the same in every
build). Before a callback in the HUD's range it sets a flag. The range
is `HUDLO`-`HUDHI`, per build; in the European exe it is
`0x42ac60`-`0x42ffc0`, the thirty-two callbacks the race's HUD setup at
`0x429228` registers, with nothing else on the list in between. `wide2d`
anchors the frame's 2D while the flag is set, and clears it at the
present.

The flag has to last the frame, not only the callback. The callbacks
queue their strings, and the screen's tail draws them all as one indexed
list (`0x418ab1` calling `0x429d70`) after the walker has finished. A
flag cleared after each callback caught the tachometer and nothing else.
The flag is `wide2d`'s, in `MGameD3D`'s annex after its `HUDFRAME`
marker. `wide.asm` finds it through the device object, as `bgrow` finds
its block, and keeps the address once found.

The flag is a frame's, but the anchoring is a draw's. A frame that draws
the HUD draws other things as well, and they are not HUD. So the walk
entry writes `HUDDRAW`..`HUDHI` - the HUD's own draw and the last of its
callbacks - into the two cells after the flag, and `wide2d` anchors only
a draw whose return address lies between them. The race's own draws are
`0x429f17`, `0x429fd2`, `0x42a08d`, `0x42a0c6` (the tail's list),
`0x42a217` and `0x42e6b3`, all inside the bounds. The results row - the
stage name, BEST LAP and TOTAL TIME, one glyph list each from
`0x447663`, `0x447948` and `0x447b68` - is outside them. Before the
bounds, the run rule tore the results row in two: half of TOTAL TIME
moved to the picture's edge and half stayed at the 4:3 box's. With the
bounds it keeps its 640x480 place whole. Bounds of zero, from an exe
patched before this, anchor as before.

Two refinements came later:

- A list from a HUD callback is anchored whatever edge it touches. The
  anchoring leaves alone any draw with a vertex at the 640's edges,
  since that is a tile or a fade for `extend`. The race's position piece
  is a string from 591 whose two-digit place reaches 639, so it fell
  under that rule and sat at the 4:3 box's edge until the place
  shortened. In split screen that was the right side of the HUD for the
  first seconds of a race; a `d3dtrace` of one shows the piece
  `0x429fd2` draws at x 591 every frame. A list is text, never a tile,
  so the edge rule now applies to quads, triangles, strips and fans
  only.
- Split screen's position bar is left alone. The band between the halves
  is the quad `0x42a217` draws at y 224, 32 tall. Along it runs a bar
  drawn through MGameGL, which the anchoring never sees, together with
  the cars' icons (a list of three quads from `0x42f7dc`, y 237 to 250)
  and their 1P/2P labels (glyphs in the race's list, y 225 to 235),
  which it did see. At the bar's left end, at a race's start, the icons
  and labels sat at the 16:9 frame's edge instead of on the bar. So a
  piece whose vertices all lie between 224 and 256 down stays where it
  is. The lower half's own text starts at 252 and reaches below 256, so
  it still moves.

Three ways of telling a HUD frame were tried first and taken out. The
first was the screen id at the screen-change routine, but 4-0xe turned
out to be the 3D front end (the car select, the name entry), and the
race showed as neither those nor 0x11-0x12. The second was a car in the
exe's car table, but that is true through the results and the credits
as well, and their centred tables then broke at the split. The third was
`wide2d` looking up the stack for the walker's return over the element;
it found stale copies of that return in uninitialised locals and crashed
on what lay beside them.

### The side bars

A quad at one edge that is wider or taller than a tile, and at least 160
tall, is a picture or a strip of one. (A plate sliding through the edge
is wide but not tall.) The mode select's backdrop is
`BINDATA\MISC\MAINMODE.TXR`, a 640x480 collage in five 256x256 tiles,
and `TITLE.TXR` has the same layout. Such a quad keeps its 4:3 place,
and the side area beside it gets the picture itself, stretched. The
texture is still bound when the quad is drawn, so the bar is another
quad, covering the side area, with that texture on it and its texture
coordinates carried past the quad's own edge.

What the bar shows is the 640's own sliver, spread across the side area.
The sliver is a bar's share of the picture's width, measured in from
that end. It reaches no further in than the quad itself does, since a
tile holds only its own part of the picture. This is the mapping `bgrow`
uses for the `.bg` screens, so the two kinds of screen look alike. A
tile ends where the next begins, so the bars meet as the tiles do. A
quad that runs past the 640 - the mode select's right-hand tiles reach
768 - has its bar started at the 640, not at its own edge, which would
be off the picture.

**The blur** across the bar is the device's. The quad is drawn sixteen
times, spread across twenty of the 640's pixels in u. That is a
thirty-second of the picture, which the eightfold stretch makes some 160
pixels on the screen. Each pass carries 17/256 of the quad's diffuse,
dimmed to two fifths. Blending is turned on for the passes (`+0xe8`, its
old state cached at `0x10011234`) with both factors ONE (`+0xec`), so
the passes add: sixteen shares of 17/256 make 255 for 255. `+0xfc` sets
the filtering to linear for them and `+0xf8` the addressing to clamp, so
a pass shifted past the texture's edge carries its last column out.
Afterwards blending goes back to what it was, and the factors go back to
source-alpha and its inverse, the pair the game's own blending wants.

Note which states these methods set: `+0xfc` is `TEXTUREMAG` and
`TEXTUREMIN`, states 17 and 18, and the blend factors are states 19 and
20, under `+0xec`. With the wrong pair set, the passes overwrite one
another instead of adding. An earlier try with four passes a
sixteenth of the sliver apart showed as four copies; sixteen passes a
hundred-and-twentieth apart read as a smear.

**What may be drawn from** is settled at the load, by the texture
create's entry (`0x1000411c`, with esi the texture's number and ebp its
description: pixels, size, flags). The entry marks each texture as one
of three kinds. The first is a picture. The second is a picture so
nearly black that a bar of it should be black instead, which is one
with three quarters of its pixels dark: `empire.txr` and `segalogo.txr`,
black but for the logo. The third is nothing, which is a sprite, a
palette or a render target. The table holds one word per texture
number, 128 of them. The logo screens are textures, not `.bg` pictures,
so they come through here and not through `bgrow`.

The description's flags are a bitfield, not the TXR's format alone. Bit
3 means 4444; the palette and render-target bits (`0x700`, `0x1000`)
are skipped; everything else is read as 1555. By the time of the create
a format-0 texture is 1555 with bit 15 set, not 565, because the screen
DLLs' loaders (MainMode's at `0x10006b80`, the others from the same
library) expand it in place. So formats 0 and 2 read alike.

With `d3dtrace` on, every quad that reaches the bar's decision reports
it, and every texture create reports its kind. DEVELOPING.md,
*Diagnostics*, has the formats.

### The .bg screens

The `.bg` pictures go through `bgrow.asm` (NOTES.md, *Windowed*), which
is built twice, and each build serves its own screens. `Title.dll`'s
copy loop draws the title screen and nothing else; the exe's copy loop
draws the loading, game-over and course screens and nothing else. So
what a bar should hold is settled at assembly time, without looking at
the pixels.

In `Title.dll`'s build the bars carry the picture behind them: the whole
picture stretched to the surface's width, with the drawn picture over
the middle, so each bar shows the sliver past the drawn edge spread
across its width. The bars get the same motion blur and dimming as the
textured screens. Each row's sliver is box-blurred: every column is the
mean of the columns a sixty-fourth of the width either side, computed as
a running sum that stays inside the sliver, so the picture beside the
bar does not bleed into it. The result is at two fifths of the picture's
brightness.

In the exe's build the screens are pictures on a plain background, white
or `loading.bg`'s black. Their slivers reach well into the picture, so
each bar is that background - the picture's corner pixel - throughout,
and nothing more. The row's own edge would have carried the card's blur
and its red rule out as streaks.

**The composite.** Neither build stretches anything itself. Drawing the
scaled picture and its bars into the locked back buffer was some seven
million CPU pixel writes a frame at 5120x1440, the same cost that made
the lobby drag. Instead `bgrow` composes the picture at source size into
a surface `MGameD3D` keeps. The surface is 2176x600, offscreen plain in
video memory, made at the present through the same `CreateSurface` as
the lobby's. One blit then stretches the composite into the whole
screen, video memory to video memory. The composite is the picture in
the middle, with each side area beside it holding its sliver, blurred or
plain. The sliver is pre-stretched into the side area's columns by the
picture's width over the screen's, so that the one uniform stretch
afterwards makes the bar's own eightfold stretch. The bands above and
below the picture hold its first and last rows.

`bgrow` finds the surface through the exe's device object (`GAMED3D`;
`Title.dll`'s build reads it from the exe too, since the exe is at a
fixed base). The object's vtable is `MGameD3D`'s at `0xf5d4`, which
gives the DLL's base. The annex from `0x17000` is then scanned for the
block's marker `BGBLOCK`, because the blob's place in the annex depends
on which patches went in. The block holds the surface, the composite's
size and a flag. `bgrow` locks the surface, composes, unlocks and sets
the flag; it does not touch the back buffer at all.

The lock's description has to hold the composite: its width and height,
when the lock gives them, and a pitch of at least the composite's row at
the depth the lock reports. Otherwise the surface is unlocked untouched
and the picture is drawn as before. Under Proton-CachyOS 10.0 the lock
reported 32 bits over a surface whose rows were not that long, and the
bars ran off its end, as a write fault in `Title.dll`'s `stretch` at the
right bar's 351st column. 11.0 gives a surface the composite fits.

The stretch cannot happen in `bgrow`, because the game holds the back
buffer locked around the row copy. It happens at the next draw through
`MGameD3D`, or the next present, whichever comes first. That is before
any 2D the game draws over the picture, since that 2D goes through the
same draws. Without a device, a block or a surface, or with a composite
too big for the surface, `bgrow` draws as it did. Split screen comes out
of the rect scaling.

### The lobby

The multiplayer lobby is the one screen that is not a draw at all. The
exe blits its BMP strips - the background, the chat panel composed
offscreen, keyed icons - into the back buffer itself through
`IDirectDrawSurface4::Blt`, at 640x480 coordinates. A `+ddraw` trace
shows them all: `(0,0)-(640,480)`, `(126,118)-(524,405)`,
`(611,451)-(635,475)`, into the surface the present then blits to the
primary, which is `MGameD3D`'s back buffer at `0x10012554`. `BltFast`
is never used. So on a wide picture the whole screen sat in the
picture's top-left, unscaled.

`wide2d.asm`'s present hooks that `Blt` in ddraw's own vtable. The
vtable is shared by every surface, so the hook is made once, with
`VirtualProtect` around the write, and not at all if `VirtualProtect`
refuses. The first version scaled each blit into the 4:3 box, and that
made the menu drag: every blit became a stretch, and Wine stretches on
the CPU.

Now the lobby draws into a 640x480 surface of its own. The surface is
made through `IDirectDraw4::CreateSurface` (`[0x1001254c]`, offscreen
plain in video memory, in the primary's format) the first time it is
wanted, and again after a mode change has given the game a new back
buffer. Every `Blt` into the back buffer whose rect is 640x480-sized and
lies within a screen of the 640x480 has its `this` swapped for that
surface. (A panel sliding in starts off the picture, past 640 or below
480.) The rect is cut to 640x480 and the source rect is cut by the same
share, because a rect off a surface fails the blit, and the screen's
edge cut a sliding panel at 4:3 anyway. A rect with nothing left is not
drawn, and the blit answers DD_OK. So the lobby draws exactly as it did
into a 640x480 back buffer.

At each present, for eight presents after the last such blit, that
surface is stretched into the 4:3 box with one blit, video memory to
video memory, and the side areas are filled with a colour-fill blit
each. The stretch continues for eight presents because the lobby draws
only what changes, and the back buffer keeps its contents between
presents. The fill colour is the background's, read at (0, 240) from the
surface behind the one blit that is the whole 640x480. That pixel is in
the plain part of the background, left of the panel and between the
title bands. It is read under a read-only lock, at 16 or 32 bits as the
surface's format says.

Under dgVoodoo 2 that background blit came back DD_OK and black. The
game's background was a 640x480 video-memory surface (caps `0x10004040`),
which dgVoodoo blits as empty while a `Lock` of it reads the picture
whole. `surfmem` puts that surface and the lobby's other offscreen
surfaces in system memory (NOTES.md, *The lobby's panels*), where the
blit carries the picture; the copy described next stays as a fallback.
After the first background blit, the lobby surface's pixel at (0, 240)
is read back and compared with the source's. If they are the same, the
blit serves from then on. If they differ, the background is copied
through `Lock` on both surfaces, row by row, that time and every time
after, without a blit. The blit goes on serving on Windows' own
DirectDraw and under Wine.

A rect bigger than 640x480, a null one, or one into another surface
passes unchanged. So does everything when the surface cannot be made; a
refused create is not tried again until the next back buffer.
`d3dtrace` reports the create as `sr2 l hr ddraw surface`, every blit
sent to the lobby's surface as `sr2 x`, and the two surfaces as `sr2 s`
(DEVELOPING.md, *d3dtrace*). The GDI text is rasterised at 640x480 and
stretched with the rest. Two details of `DDSURFACEDESC2`: `ddsCaps` is
at `0x68`, after the 32-byte pixel format at `0x48`, so caps written
four bytes on land in `dwCaps2`; and a surface asked for with no caps is
refused.

The side areas were tried two other ways first. The background's first
column stretched across came out as streaks of the surface's dither. A
strip of the background tiled at the box's scale came out with pieces of
the title in it, since the title is composed into that surface, and
mirroring the strip to hide the seams went through Wine's CPU blitter.

### The device viewport

The exe draws the countdown digit itself, as an untransformed indexed
list (`0x42bd2f`, FVF `0x1e2`), after setting the device's viewport
itself (`0x42bcda`, MGameD3D's `+0x158` of the second interface,
`0x10006040`). It takes the viewport from its own table at `0x5b24f0`:
640x480, the split-screen halves and the 800x600 set, each with the
projection-centre fractions. The four numbers are a rect - left, top,
right and bottom - and not a corner and a size: the setter takes the
width from right minus left (`0x1000605f`). This path never goes through
MGameGL's `SetViewport`, so the digit was drawn in the picture's
top-left 640x480.

`wide2d.asm` takes that setter too. While the picture is wider, a rect
no wider than 640 and no taller than 480 is scaled through a copy into
the picture's own 4:3 box: everything by the height, and both its sides
carried past the bar, exactly as the 2D is scaled. MGameGL's rects are
in real pixels and pass.

The rect alone does not settle the digit's size. The setter makes the
clip volume from the rect's share of the *screen*: `clipW = 2 w /
(screenW · f1)` and `clipH = 2 h (screenH / screenW) / (screenH · f2)`,
where `0x10012420` and `0x10012424` hold the display size from the
device's creation, and f1, f2 are the two floats at the end of the
struct. So a rect the size of the 4:3 box on a 32:9 screen holds three
eighths of the clip width the 4:3 screen has, and what is in it is drawn
as large as a viewport the whole screen wide would draw it. The patch
therefore scales the two fractions by the box's share of the screen's
width, which brings the clip volume back to the 4:3 screen's 2.0 by 1.5.
The first version scaled the rect to the whole picture, which was worse
again by the ratio of the widths. `d3dtrace`, which reports every draw
with its caller, found this path after `gltrace` had ruled out the
renderer's paths.

## The sea

The race's backdrop below the horizon is a layer the exe builds at the
race's start (`0x448c70`). There is one layer over (0, 256, 640, 480),
or two in split screen. The `.SEA` file is loaded at `0x462b80`; the
object is made at `0x462e10` with the class at `0x49dca4`; its update is
`0x4633b0` and its draw `0x463500`. It sits on an `MGLBackground` layer
(interface `452593f2`, class vtable `0x1000b0f0`: init `0x100030a0`,
update `0x10003360`, draw `0x10003de0`).

The init lays a grid of 64-px cells over the rect widened by 96 px a
side: four rows of a 28-vertex strip. Each vertex's depth is `-h * focal
/ (y - cy)`; its z and rhw come from the renderer's `+0x40` and `+0x44`
at that depth, and its texture coordinates from the inverse projection
at that point. The update rotates the grid about a point by the camera's
roll, drops it by the pitch, and scrolls the texture. The draw is four
strips of FVF `0x1c4` through `+0xbc`, with fog off. The lake is that
plane seen through a hole in the ground mesh. `sky*.mdl` is the sky.

In split screen there is no lake, and that is the game's own doing. The
sea's draw (`0x463500`) opens with `cmp dword [game+0x38], 5; je`
(`0x463517`), and mode 5 is split screen, so the draw does nothing there
and the hole shows the backdrop. The exe still makes two layers for
split screen (the table at `0x4bc080`), but it builds them before either
half's viewport is set, both about the full screen's centre (320, 240).
A `gltrace` shows this: the six `gp` reads come right after the exe's
full-screen `vp`, and the halves' `vp` lines come fourteen lines later.
So the top layer's rows all lie above its horizon and its z is above 1,
and the bottom layer's horizon is 128 rows above its own. Presumably
that is what Sega saw, and they switched the draw off rather than fix
it.

Two things were tried and taken out: setting each half's viewport
before its layer through the exe's `SetViewport` wrapper (`0x46bfd0`),
which gave the layers the right centres, and making the `je` nops,
which would have drawn them. The Dreamcast has no lake in split screen either, so it
stays as shipped.

## The credits

The ten-year championship ends on the credits: the race state's
sub-state 8 (`0x419af0`), which replays year ten's Super S.S. in a
window at 351-607 x 222-415 while the names scroll. The window is the
race's own scene pass (`0x418f30`, mode 4 with flag `0x20`). The
countdown runs full screen; then the frame shrinks about the window's
centre in 32-px steps down to the window, through the exe's
`SetViewport` wrapper (`0x41905f`). The rest of the screen is blacked
out by untextured quads from the credits' draw (`0x48672a`, in
`0x48656c`): the bands above and below at full width, and the side
pieces from -1 to the window's left and from its right to 642. The
per-frame clear is MGameD3D's, a `Clear2` with one rect that is the
whole back buffer (`0x10012410`, `SetRect(0, 0, W, H)` at its init,
`0x10005f40`), never the viewport.

Two things went wrong on a wide picture. `widegl` scaled the window's
rect to the whole width as it does the race's, so the replay rendered
beside its black frame. And the side pieces, scaled into the 4:3 box as
2D is, left the clear showing in the side areas at the window's rows (a
`d3dtrace`: `sr2 b` why 3 for both pieces, nothing drawn). So now a
viewport rect that is narrower than the 640, or off its middle, goes
into the box, and a quad at one edge with no texture selected is drawn
out to the screen's edge. The fade at the end is the window's own: a
quad over the right half whose alpha ramps as the replay ends.

For a test without a year-ten save: the results step (`0x419830`) hands
on to the season's end step (`0x419a70`) only after a year's last stage,
at `cmp [game+0x64], 3; je` (`0x4198fc`), and that step hands on to the
ending only in year ten, at `cmp eax, 0xa; jne` (`0x419ab7`). A `jmp`
over the first and nops over the second roll the credits after any
stage. There is then no Super S.S. replay to play, so the window shows
an unlit car at 0'00"000 and fades at once. The zoom and the window's
place can be checked that way.

## The Graphic Settings page

The page (`0x10003370` exec, `0x10002f20` draw; the page object at
`Options+0x14`, rows at `+0x18`, counts at `+0x58`, cursor `+0x10`,
pulse `+0x78`) showed the RESOLUTION row's two choices side by side from
sprites (`0x1009c714`), and greyed the second without the 800x600
capability bit (`0x10003426`).

`resolution.asm` makes the row a list and adds an ASPECT RATIO row under
it. The table is grouped by aspect (`RESOLUTION_GROUPS`, five groups;
the 21:9 sizes are 64:27, 43:18 and 12:5). Row 7 holds the group, and
row 6 holds the index within it, with row 6's count set to the group's.
A change of aspect puts row 6 to the group's first entry at the next
draw.

Row 7 uses the page's own machinery: the page object has room for
sixteen rows, and left and right are generic. The page's six "7"s (the
value loop's bound and the button-row tests in the exec) are made "8"
so the cursor reaches the new row. Its plate is row 6's, drawn 27 px
lower with the loop's colours, and its label and value text go through
the stock 14-px routine. The font has no colon, so the aspect's colon
is two dots, one 6 px up. Both values start at the first choice
sprite's place, as the rows above do (`1920X1080`, `21:9`; no lowercase,
no arrows). The aspect's colon goes after its left part, at a position
measured through the routine's own character map and glyph advances. A
wide size in `SR2.CFG` that is in the table selects its group and entry
on entering the page, and DEFAULT gives 640x480 in 4:3.
