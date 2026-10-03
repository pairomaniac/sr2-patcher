# Gamepad

A pad binding goes in where the key it stands for enters the game, and
the keyboard is left as it was. A key the input wrapper reads as a bit
gets the pad in the wrapper, where every screen that reads the bit sees
it (`pagepad`: Page Up and Page Down, and the name entry's erase). A key that a screen takes from a
word of its own gets the pad in that word (`padmenu`: the multiplayer
screens' menu word; `replaypad`: the replay controls' word). A key the
game never reads as input gets the pad read where the key's effect is
used (`sortpad`: F6-F8 are accelerators, so the gallery reads LB and RB
itself). A prompt that names a key is drawn as the pad's while a pad is
held (`padprompts`: the Records pages' page keys and the ranking's
replay prompt; `padtitle`: the title; `padattract`: the attract screen;
`padgallery`: the Replay Gallery; `padoptions`: Options). Each of these reads
the pad through the page poll MGInput's annex publishes (`PADPOLL`,
through the shared `asm/padpoll.inc`). Each takes an input past half its
range as down, and does nothing when the poll slot is empty.

`MGInput.dll` (`0x10000000`, relocated) reads every action. The European,
American and DigiCube/MediaKite releases share one build of it; the
Australian release has an older build with the same interfaces at other
addresses. Four patches touch it: `xinput`, `dinput8`, `nogeneric` and,
in the exe, `noregistry`.

## The model

The exe's init (`0x47eff0`) makes a config per player, named `"0"` or
`"1"` at `+0xc`, attaches the keyboard device and loads the config
through `Persist` (vtable `+0x30`, `0x10007510`; flags bit 0 means save,
bit 1 means keep what is there). Player 1's config is loaded twice:
first unnamed and clearing (`0x47f094`), then named `"0"` and appending
(`0x47f0ca`).

An action is a `0x34`-byte record: an id, a repeat delay and rate in
frames, a deadzone and saturation in 0..10000, and up to eight source ids
that are ANDed, of which the first carries the value. The action's object
is `0x15c` bytes:

| Offset | Field |
| --- | --- |
| `+0x10c` | id |
| `+0x110`, `+0x114` | deadzone, saturation |
| `+0x118`, `+0x11c` | delay, rate |
| `+0x120` | the scaled value |
| `+0x124` | frames held |
| `+0x128` | the press event |
| `+0x12c`, `+0x130` | raw value and range |
| `+0x134`, `+0x138` | sources seen, their count |
| `+0x13c` | the ids |

Import and export are at `0x10008890` and `0x10008910`.

The action ids are: 0 accel, 1 brake, 2-5 up, down, left, right (the
menus, with repeat; 4 and 5 are also the steering), 6 shift up, 7 shift
down, 8 handbrake, 9 view, 10 enter, 11 escape, 12 start. Start is the
race's pause (`0x419306`) and a confirm in the menus, like 10. The
sources are: 1-0xff keyboard scancodes, 0x101-0x168 joystick, 0x201-0x20b
mouse. The device's poll answers them (`0x100056c0`,
`(this, source, &value, &range)`).

The config's update (`0x10007100`) has every record poll every attached
device, then finalises. `GetActionState` (`0x100078b0`) takes the largest
magnitude among an id's records, so a key record and a pad record for
one action coexist.

## XInput

asm/padinput.asm is hooked at the load, the save, the update and the
device's poll. The Australian build has no poll method. Its record update
(`0x10008170`) calls a static poll per device type, so there the keyboard
poll's address in that dispatch (`0x100081a8`, `0x10007e40`, five
arguments) is pointed at the annex's own entry. A third entry,
`(source, &value, &range)`, serves the Device Settings page and is published at
`PADPOLL`.

The poll answers sources `0x300 + player * 0x40 + input`. The sixteen
buttons answer `0x80`/`0x80` like a key. The triggers answer over 255,
past the usual threshold. The eight stick halves are rescaled past the
player's deadzone to 0..10000.

The update hook refreshes the config's player first. Each side keeps an
XInput slot. When a side has none, it looks for the first free slot,
every 60 frames, and it clears its state when its pad goes. Side 1 looks
only while side 0 holds a pad. So when there is one pad, at the start or
plugged back in, it is player 1's, whichever side's look falls first.
Before that rule, a pad unplugged and replugged in the menu came back as
player 2's. A `+xinput` log showed why: side 1's look, a frame ahead,
took slot 0, and side 0 then skipped that slot as held.

## Rumble

The pad shakes when the player's car hits something and when it lands
after a jump. The update hook does this after the side's pad is
refreshed, by reading the car; nothing in the exe is hooked.

The game keeps two counts in a driven car, each one up a physics step.
The first is the frames since the car last hit another car or a roadside
object (`car+0x6d8`, stepped at `0x443e0b`). The second is the frames
since it last hit a wall (`car+0x6dc`, stepped at `0x402f1f` as `+0x490`
of the physics block at `car+0x24c`). The game zeroes a count when the
hit is hard enough for its crash sound and the count is past 60
(`0x443ec1` for the first, with a push over 0.03; `0x4030ef` and the
tiers before it for the second, with a push over 0.02). So a count lower
than it was a frame ago is a hit the game itself sounded. In the
Australian build the two counts are at `car+0x6d0` and `car+0x6d4`
(`0x474d6a`, `0x407e5f`). The patcher fills in the offset (`CARHIT`).

The car's airborne flag is `car+0x270` in every build (set at
`0x402949` when all four wheel flags are set; `0x407889` in the
Australian build). The stub counts the frames the flag is up. A landing
is the flag gone after 10 frames or more, the count the game's own
landing sound waits for (`0x404691`).

The car is the side's slot of the car table (`CARS`). In a network race
(mode 6 at `+0x38` of the race block, whose pointer is at `0x50b108`,
`GAME`) it is this machine's slot, the dword `0x94c` past the car table
(`0x4d6e08`), and only side 0 has one. Side 1 has a car only in split
screen (mode 5). No side has one while bit 2 of the block's `+0x44`
flags is set, which the replays set. A car seen for the first time only
sets the stub's copies of the counts. While the game is paused the
counts and the flag stand still, so nothing fires.

The pulse is sent every frame. Its strength comes from the player's
vibration setting, 0 to 9, 5 as shipped: none at 0, and from 1 to 9
`0xffff × (setting + 3) / 12`. A hit is 48 frames at a level strength,
the left motor at the strength, doubled for the first 6 frames, and the
right at a quarter. A landing is 36 frames, the left at three eighths
and the right at a half, fading out over the last 20. A hit in the frame
of a landing takes its place. The setting is the page's
VIBRATION row, kept in `SR2.CFG` as `Vibration = 5` in the player's
controller section; a save under a name beginning `VB` sets it and input
`0x3d` reads it back, as `DZ` and `0x3f` do for the deadzone. The pulse goes through
`XInputSetState`, found beside `XInputGetState`, and the motors are
switched off when its frames run out, in or out of a race. A machine whose XInput has no
`XInputSetState` gets no rumble.

The exe has force feedback of its own for a DirectInput wheel: a constant
force made at `0x444967` and set every frame from the steering force at
`car+0x6b8` (`0x442b10`, `0x444ba0`). It is not used here. The annex's
records put a key first, so the wrapper never attaches a joystick, and
the force is a steering pull, not a shake. That account of the exe's
force feedback is read from the code, not tried.

`tools/padinputtest.py` runs the rumble under Unicorn on every build's
`MGInput.dll`. The rumble has been felt in the game. The vibration
setting has not been tried in the game yet. Whether the attract demo
sets the replay bit has not been checked.

## DirectInput 8

The DLL made its DirectInput object with `DirectInputCreateA(hinst,
0x500, &out, NULL)` (`0x1000294d`, through the thunk at `0x10008a30`,
which is the one `DINPUT.dll` import). It took `IDirectInput2` from that
object (`0x10002963`) and kept it at `+0x10` of the input object.
`EnumDevices(0, cb 0x10002300, &vector, ATTACHEDONLY)` at `0x100025e1`
collects every attached device, one `DIDEVICEINSTANCE` at a time, with
no type filter. The device init (`0x10003910`) calls `GetDeviceInfo` and
`GetCapabilities` and asks each device but the keyboard for
`IDirectInputDevice2` (`0x100039c2`).

That enumeration runs through Windows' legacy `dinput.dll`. That is where
the starts that hang on a white window with certain HID devices go
wrong; `dinput8.dll`'s enumeration does not. DirectInput 8's objects
carry the same vtables. `IDirectInput8` matches `IDirectInput2` slot for
slot, with `CreateDevice` at `+0xc` and `EnumDevices` at `+0x10` where
they were. `IDirectInputDevice8` is `IDirectInputDevice2` with three
methods appended. The enumeration flags and class values are the same
numbers, and `DIDEVICEINSTANCE`, `DIDEVCAPS` and `DIDEVICEOBJECTINSTANCE`
keep their DirectX 5 layouts. So the DLL's calls stand once the object is
DirectInput 8's.

asm/dinput8.asm makes the switch in three places:

- The create. The eighteen bytes of the call become a jump to the stub.
  The stub calls `DirectInput8Create(hinst, 0x800, IID_IDirectInput8A,
  &out, NULL)`, found once through the DLL's own `LoadLibraryA` and
  `GetProcAddress` slots, and returns the result at the site's
  continuation. A machine without `dinput8.dll` gets `E_FAIL`, as a
  failed create did before.
- The interface ids. The two in `.rdata` are rewritten to DirectInput
  8's, so the two `QueryInterface` calls succeed and hand back the same
  pointers as before.
- The device type. The one thing that changed meaning is the low byte of
  `DIDEVCAPS.dwDevType`. That is the device's kind, at `+0x260` of the
  device object. The DLL switches on it as 2 mouse, 3 keyboard, 4
  joystick (`0x10003490`, `0x10003570`, `0x10006550`), and carries it as
  the kind byte at `+0x24c` of the record the game and the Device
  Settings page see. DirectInput 8 uses 0x12, 0x13 and 0x14-0x18 for the
  controller kinds, 0x11 for a device of no kind, and 0x19-0x1c for a
  device control, screen pointer, remote or supplemental collection. The
  stub's second entry is called where the DLL first reads the byte: the
  `cmp byte [esi+0x260], 3` at `0x100039ac`, or in the Australian build
  the `mov edx, [esi+0x260]` at `0x100039f9`, that build having asked
  for `IDirectInputDevice2` before that point. The entry writes the old
  code over the new one and then does what the displaced instruction
  did, keeping the flags through the `ret`. Kinds 0x19-0x1c take the
  no-kind code, 1. The game can use such a collection no more than it
  can use a 0x11, and if they were left as joysticks they would take
  the slot the exe asks for by kind (`0x47f0a6`, joystick index 0) away
  from the pad itself. A device of no kind fails the DLL's own
  data-format and state lookups with `E_NOINTERFACE`, and its slot in
  the list stays null, which is the state a skipped instance leaves.

The instance copies in the enumeration vector keep DirectInput 8's
`dwDevType`. Nothing reads it; the loop over them (`0x100026ab`) looks
only at the instance GUID. This is what dinputto8 does for the DLL at run
time, done here once at the three sites. DirectInput wheels and pads go
on working through the same calls. `tools/dinput8test.py` drives the
DLL's own create routine under Unicorn against a stubbed `dinput8.dll`,
both with and without the DLL present, and drives the kind entry across
the type codes.

## Devices of no kind

With the list enumerated, the loop at `0x100026ab` makes a device of
every instance whose GUID is not null: it calls `CreateDevice`, runs the
init above, and makes an object of the DLL's own, which is polled every
frame. On a machine of today that is a dozen things that can never give
input: LED controllers, a stream deck, an audio device's control
collection, a receiver's spare collections. The Xidi logs from the
repack's testers list them. Each is opened, and each is a place for a
driver to stall a `CreateDevice`. DirectInput 8 does not save the game
from that.

DirectInput 8 reports those devices as `DI8DEVTYPE_DEVICE`, 0x11, a
device of no kind, and asm/nogeneric.asm leaves them out. The loop's `je
skip; mov ecx, [esi]; push edx` after the null-GUID compare becomes a
jump to the stub. The stub makes the branch on the compare's flags, looks
at `dwDevType` (eax holds `guidInstance`, so the field is at `+0x20`),
and skips a 0x11 the same way the null GUID is skipped: the list keeps a
zero in that slot, which is a state the DLL already handles. Then it does
the two displaced instructions on the way to the continuation. The four
kinds above the controllers go the same way: 0x19 `DEVICECTRL`, 0x1a
`SCREENPOINTER`, 0x1b `REMOTE` and 0x1c `SUPPLEMENTAL`. `SUPPLEMENTAL`
is what a composite pad's spare collections come up as. An 8BitDo dongle
presents a gamepad, a keyboard, a consumer collection, a mouse and a
vendor collection, and only the first is a controller. Mice (0x12),
keyboards (0x13) and every controller kind (0x14-0x18, wheels 0x16 among
them) go through as before. The patch needs `dinput8`, whose type codes
these are. `tools/nogenerictest.py` enters the site as the DLL would, for
a null GUID, for each skipped type and for each kept type.

## The store

The registry helper's load and save (`0x10008130`, `0x10008210`) become
the annex's own. The annex keeps a table of the key and pad input for
each action of each player, and the two deadzones, as text in `SR2.CFG`.
There is a section for each player and device (`[1P Controller]`,
`[1P Keyboard]`), holding `Name = value` lines for the eight driving actions
`Deadzone = 10` in percent and, in a controller section, `Vibration = 5`
(0 to 9, the rumble's strength, 0 for none). The names are the page's names with
spaces as underscores; `-` means none. The `=` is optional. An unreadable
section header closes the section. Unreadable lines keep the defaults.
The deadzone clamps to 0-90%. A file with the game's 100-byte block ahead
of the text (from before the `noregistry` patch moved the block to `SR2.DSP`) is
read past the block.

A load generates the player's records. First come each action's key
record and pad record. Then come the menus' fixed records: the arrows
(WASD for player 2) on actions 2-5, and the D-pad and stick halves twice
over, once on actions 2-5 and once on the four actions the exe's screens
read (below). The bindable records come first, because the page takes
the first record as a row's. Only unnamed loads get records; otherwise
player 1's would double. A save takes the table back out of the exported
records (the first key source and the first pad source per action). A
name beginning `DZ` gives the digits after it as the deadzone, and one
beginning `VB` the vibration strength. The save
then rewrites the text. The `[Display]` Resolution line and the
`[Network]` section (the netplay DLL's Staging and Log, 0 or 1) are
carried over as the file had them, and only when the file had them.

The menus' left and right are the steering's actions, so their fixed
sources are *menu-only*. A menu-only key is `0x400` + scancode, read from
the keyboard device's array at `+0x308` (the device whose type byte at
`+0x260` is 3). A menu-only pad input has bit 5 set. Menu-only sources
answer only while the exe's car table (`CARS`, `0x4d64bc`) has no car in
slot 0. The cars exist from a race's setup (`0x412aac`) to its teardown
(`0x412c67`), whatever the mode. Input `0x3f` reads a player's deadzone, and `0x3d` the vibration strength of 9.
Input `0x3e` reads `0x80` of `0x80` while the player's side holds a pad
and 0 while it holds none, in a race as well.

## The menus' directions

The exe's multiplayer screens (the driver select, the connection screens
and the team room) test a word of menu flags. Bits 0-3 are up, down,
left and right; bit 4 is confirm; bit 5 is cancel; bit 15 is Enter; bits
13 and 14 are back. Two such words exist. The keyboard fills one
(`0x4d5e08`) from the exe's `WM_KEYDOWN` handler (`0x41fe20`: the
arrows, CR at `0x41feb3`, TAB and ESC at `0x42018f` and `0x420172`),
never through `MGInput`. The pad fills the other (`0x4edcb4`) from the
poll at `0x43f8e0`. That poll packs the input wrapper's button mask
(`[0x50b120] + 8`, vtable `+0x1c`). The mask is built each frame at
`0x47f2d0` by a fixed table of `GetActionState` calls, with ±5000 as the
threshold: action 10 (enter) goes to bit 0, 11 (escape) to bit 1, 12
(start) to bit 6 and 2-5 (up, down, left, right) to bits 9-12. The
packing `((m & 0x40) << 5 | (m & 0x3f)) << 4 | ((m >> 9) & 0xf)` turns
those into flags 4, 5, 15 and 0-3. The screens test both words
(`0x43bef0` in the connection screen, `0x437983` in the team room's menu
row, `0x436716` in its list).

So the directions are the steering's actions 2-5, where the fixed
bindings already put the D-pad and the stick. Confirm, back and Enter
are the enter, escape and start rows, whose defaults are A, B and Start.
The fixed set carries those three as well, menu-only, so a rebound pad
still confirms and backs out of those screens. A row's fixed inputs sit
beside whatever the row is bound to. The poll has a repeat of its own:
it clears the low four bits of the previous frame's flags every
`[0x4b5638]` frames, so a held direction re-triggers. `padmenu`, below,
takes that repeat out of play.

Three things keep a pad off the team room. First, in the team room the
wrapper's mask carries nothing from an XInput pad, so the pad word stays
empty. The connection screens do take the pad through the mask, and why
the room does not is not settled. Second, the room is two tasks. The
slot list (`0x4366b0`) takes up, down and confirm from either word. But
its way to the MENU row, a task it spawns (`0x437b10`) on TAB, is bit 13
of the keyboard word alone (`0x4366c9`), and the row's way back
(`0x437983`) is bits 13 and 14 of the same word. No pad bit reaches
those. The list's confirm with no chat typed opens the player's stat
card (`0x43684d`), which any key closes through bit 31 of the keyboard
word, `WM_KEYDOWN`'s mark (`0x4366bb`). No pad bit sets that either.
Third, the poll's repeat of a held direction runs at the keyboard's
rate: `0x43f880` takes the delay and rate from `SystemParametersInfo`,
and a held stick walks the rows two frames a step once the delay is out.

The `padmenu` patch (asm/padmenu.asm) goes around all three. The poll's
six-byte store of its level word at `0x43f94f` becomes a call into the
stub. The stub asks MGInput's annex for side 0's D-pad, left stick, A, B,
Start and Back through the poll the annex publishes at `PADPOLL`. That is
the page's poll, `(source, &value, &range)`, with sources `0x300` + the
input; down is a value past half its range. A, B and Start go into the
level word as bits 4, 5 and 15, and the wrapper's directions come out of
it. The pad's directions go the keyboard's way instead: into the
keyboard word as bits 0-3, on a change and then every 2 frames once the
direction has been held for 30. That is the walk `WM_KEYDOWN`'s repeat
gives a key. A bit in the keyboard word waits for the task that reads
and clears the word (`0x43687e`, `0x437a5c`, `0x43bb99` and the rest),
so no screen misses one. The edge word, by contrast, is made and cleared
by the frame: a pulse in it reached the connection screens only now and
then, and on those screens the wrapper's level bits ran the poll's repeat without
its delay whenever anything else was held. A press of Back sets bit 13
in the keyboard word, which is TAB to the list and back to the row. Any
press sets bit 31, which closes the card as a key would. Then the stub
makes the edge word again, against the stored previous level, because
the exe made its edge at `0x43f94b`, before the site, from a level
without the annex's bits. Then it does the three stores. With the poll
slot empty, the exe's own edge is stored as it is. The poll runs only
from the multiplayer controller (`0x43fcd9`), so no other screen sees
any of this. `tools/padmenutest.py` runs the entry under Unicorn.
`tools/padbits.py` prints the action-to-flag table by running the
wrapper's update and the poll under Unicorn with `GetActionState`
stubbed (European offsets).

The name tables and defaults are data the patcher appends after the code
(`annex_tables`). `tools/uctest.py`'s `annex_records` and `annex_text`
(the patcher's `settings_text`) model that output for the tests.
`tools/padinputtest.py` runs the four entries under Unicorn against the
real DLL.

## Page Up and Page Down

The wrapper's update (`0x47f2d0`) builds each player's level word from a
fixed table, one action per bit: 10, 11, -, -, -, -, 12, -, -, 2, 3, 4, 5
for bits 0-12. A value past ±5000 sets the bit; in the Australian build,
any value does. Bits 7 and 8 have no action, so only the keyboard sets
them. They are Page Up and Page Down in the wrapper's own scancode table
(`0x47f5c0`; the keyboard's word is at `+0x44`, and the query `0x47f750`
ORs it into player 1's). Two screens read them, through the level
(`+0x1c`). The Records page turns its pages on them (`Record.dll`
`0x1000798b`, `0x10007a2c`, with a repeat of its own). The car select
takes a held Page Up as the alternative colour (`MSelect.dll`
`0x100091d3`): a confirm sets a flag and counts 40 frames, and the flag
is cleared on any frame the bit is not in player 1's level. If the flag
survives, the five cars that have an alternative colour take it. Nothing
else in the exe or the DLLs tests the two bits after a read of the
wrapper.

The `pagepad` patch (asm/pagepad.asm) gives those two bits the bumpers.
The load and test after the table loop (`0x47f506`, `mov eax, [esp+0x10];
test eax, eax`; the Australian `0x4beaf8` compares with ebp, which is 0
there) become a call into the stub. The stub asks the annex's page poll
for the player's LB, RB and X, the player being side `[esp+0x18]` of the
caller. It ORs them into the level at `[esi-0xa0]` as 0x80, 0x100 and
0x08 (X is the next section's). Then it does the load and test, so the
site's branch sees the right flags. `tools/pagepadtest.py` runs the
entry under Unicorn with each build's addresses.

## The name entry's erase

The name entry after a time attack (the exe's task at `0x433389`) and
its copy in `MSelect.dll` erase the last letter on bit 3 or 4 of the
wrapper's edge (`test al, 0x18`: exe `0x43368a` and `0x43393c`,
`MSelect.dll` `0x1001c630` and `0x1001c980`). The erase plays sound
`0x21`, takes one from the length at `+0x3c`, frees that letter's model
and clears its byte. Nothing sets either bit. The action table has none
for bits 2-5, and the wrapper's scancode table (`0x4cfe90`, one dword
per bit for bits 0-12: Return, Escape, seven -1s, then the arrows) has
-1 for both. The same entries take Start (bit 6): on END it confirms, and
anywhere else it sets state 7 (`0x433667`, `0x433919`), which spins the
carousel to END (`0x1c`) over 28 frames. Keypad Enter sets bits 0 and 6
together, and bit 0 (confirm) is tested first.

Bit 4 is not free. `MSelect.dll` sets `+0x2b0` of an object on its edge
(`0x10001c4f`, `0x100048cc`, `0x1001af8a`, `0x1001dc06`). Bit 3 is read
by the two name entries alone, in the exe and every DLL. A scan for a
test of 0x08 or 0x10 after a call to the wrapper's edge, level or
second-edge query (`+0x14`, `+0x1c`, `+0x18`) found nothing else. The
multiplayer poll packs bit 3 into bit 7 of its menu word; no read of
`0x4edcb4` or `0x4d5e08` is followed by a test of 0x80 in its low byte.

So erase is bit 3. `erasekey` writes Backspace's scancode (`0x0e`) into
bit 3's cell of the scancode table (`0x4cfe9c`). That table is read only
for player 1, while bit 0 of `+0x14c` is set (`0x47f5f8`). The keyboard's
word is ORed into player 1's by the query (`0x47f750`). `pagepad` gives
bit 3 the pad's X. The edge is made from the level at `0x47f540` (the
level against the previous one), so a held X erases once.

The Replay Gallery's sort is not input the game reads at all. F6, F7 and
F8 are accelerators in the exe's resources (VK_F6-F8, commands
40043-40045). The window procedure's `WM_COMMAND` handler (`0x428320`)
sets the mode (0 MODE, 1 CAR, 2 DATE) at `+4` of a block at `0x4e6908`,
and turns the order over (`+8`) when the mode picked is the one already
set. The gallery gets the block as its init block's `+0x6c`: the exe's
gallery screen passes `+0x28` of its own object, and the block's `+0x6c`
is that object's `+0x94`. The list's browse state (`0x1000271f`) compares
its own copy of both values every frame and sorts again when they differ.
Nothing a pad sends reaches an accelerator.

So the pad is read where the sort is used. The `sortpad` patch
(asm/sortpad.asm) makes the two instructions after the list's row update
in that state (`0x10002764`, `mov ecx, [esi+0x50]; and edi, 0xff`, the
same in every build) a call into the stub. The stub asks the annex's page
poll for side 0's LB and RB and keeps track of what was already down. On
a press of LB it steps the mode left, and on a press of RB it steps the
mode right, wrapping round at both ends. Then it does the two
instructions. The compare after them sorts the list as an F key would.
The order stays as it was; an F key pressed again still turns it over,
and the keyboard's Page Up and Page Down do nothing here, as before. The
DLL is relocated at load, so the stub finds the image base from its own
RVA and the sort block's global (`0x100be620`) from that base. The poll
slot is an exe address, filled per build.

With no replay saved the list never reaches the browse state. Its state 2
(`0x100025b7`) goes to state 3 when the list has rows and to state 6 when
it has none, and state 7 (`0x1000285c`) then shows the empty notice every
frame. The F keys still move the sort box there, so the patch has a
second site in that state: `push 0; mov edi, eax; mov edx, [ecx]`
(`0x1000286a`, file `0x1c6a`, the same in every build) becomes a call to
the stub's second entry, which steps the mode the same way and then does
the three instructions. `tools/sortpadtest.py` runs both sites on the
real DLL, relocated, under Unicorn.

## The pad's prompts

The game's prompts are lettering in its texture files, not strings. A
search of the exe and the DLLs beside it for ENTER, ESC, KEY, BUTTON and
PRESS found no prompt. These are the prompts that name a key, by file
under `BINDATA\MISC` and sheet:

| File, sheet | Lettering | Drawn by | Pad's |
| --- | --- | --- | --- |
| `TITLE.TXR` 5 | PRESS ENTER KEY | `Title.dll` | PRESS START BUTTON (`padtitle`) |
| `ADV_TXT.TXR` 0 | PRESS ENTER KEY | `AdvTelop.dll` | PRESS START BUTTON (`padattract`) |
| `Record.txr` 13 | PAGE UP KEY, PAGE DOWN KEY | `Record.dll` | LB BUTTON, RB BUTTON (`padprompts`) |
| `Rank10.txr`, `RankAC.txr`, `RankTA.txr`, `Record.txr` 9 | PRESS ENTER KEY for REPLAY | `Record.dll`, six pages | PRESS A BUTTON for REPLAY (`padprompts`) |
| `Record.txr` 14 | Use Cursor keys to change mode selections (line 1 of six) | `Record.dll`, the Records page's bar | Use the D-pad to change mode selections (`padprompts`) |
| the four `RG_` files 7 | SORT, MODE : F6, CAR : F7, DATE : F8 | `ReplayGallery.dll`, ten pages | SORT LB/RB, MODE, CAR, DATE (`padgallery`) |
| the four `RG_` files 3 | Hit the ESC key to go back to the previous screen (line 2) | `ReplayGallery.dll`, the foot's bar | Hit the B button to go back to the previous screen (`padgallery`) |
| the four `RG_` files 8 | lines 4 and 5 of six: Hit the ESC key to go back to the previous screen; Go back to the previous screen by pressing the ESC key | `ReplayGallery.dll`, two popups | the same with the B button (`padgallery`) |
| `OPTIONS.TXR` 4 | Use Cursor keys to change mode selections (line 2 of six) | `Options.dll`, the frame's bar on four pages | Use the D-pad to change mode selections (`padoptions`) |

The six lines are one sheet: `OPTIONS.TXR` 4, `Record.txr` 14 and the
`RG_` files' 8 are the same texels. The sheet's line 3 (the DELETE key)
and line 6 (the key board) are drawn by the gallery's other two popups
and stay as they are, since the pad has no delete and no letters. In the
Japanese files (Sega's Japanese and the DigiCube and MediaKite releases)
`Record.txr` 14, the `RG_` files' 3 and 8 are Japanese, with ENTER, ESC
and DELETE as keys, and the pad's lines there are Japanese too
(十字ボタン, Aボタン, Bボタン); `OPTIONS.TXR` is English in every
release. Every one of these screens' sprites was traced to its UV entry
(`_sprite_quads` in the patcher). `Options.dll` also holds fourteen
message sprites (page `0x100b3c38`) built from word-sized boxes of the
Japanese sheet 4, the Dreamcast calibration page's; on the English sheet
they read as nonsense and no page draws them.

The team room's TAB MENU button, `BINDATA\chat\tab_menu_on.BMP` (and
`_on2.BMP` with the CHAT tab up), is a bitmap the exe blits through GDI,
not a sprite, so the stub cannot switch it; the pad's Back opens that
row (`padmenu`). It has its own patch, `tabmenu` (*The team room's TAB
button*, below).

What is left of the Dreamcast's prompts is the same in every build:

- `Record.txr` 13 has L LEVER and R LEVER under PAGE UP KEY and PAGE DOWN
  KEY, and a grey plate beside them. No UV entry in `Record.dll` covers
  them.
- `MSARCADE.TXR` 13 has the Japanese hint bar in pieces: 上下で, 左右で,
  Aボタンで, Xボタンで, LRレバーで, ハンドルで, 十字ボタンで, 変更, 選択,
  決定, 実行. `MS10YEAR.TXR` 22, `MS2P.TXR` 8, `M_NETWRK.TXR` 22 and
  sheet 6 of the three `Rank` files hold the same pieces.
- `N_TIMATK.TXR` 3 has the name entry's 左右で選択、Aボタンで and
  ハンドルで 決定してください。
- `OPTIONS.TXR` 6 to 9 have the Device Settings page (*The texture*,
  below), with Aボタン and Bボタン in its calibration text.

There is no English lettering for a pad besides L LEVER and R LEVER. No
sheet has PRESS START BUTTON or a button's name in English. So the pad's
prompts are new lettering, and the Dreamcast's is not used. Each is one
line of one font, the open one that comes closest to the stock prompt it
stands in for, set and finished as that prompt is. No letter is cut from
the game's sheets or drawn by hand, so a prompt can say anything. The
lobby's SEARCH button (the `lobby` patch) and the team room's SEL are
set the same way, in the face closest to the buttons' own.

**The stub.** A screen DLL draws a prompt as a sprite of quads. A quad
is a rectangle about the sprite's centre over a UV entry, and the draws
read the sprite, the quad and the entry each time they draw (in
`Record.dll`, `lea eax, [eax+eax*4]; mov edx, [ecx+eax*4]` at
`0x1000ea2b`, `0x1000ec9e` and `0x1000ef6e`; in `Title.dll` at
`0x10001e1b`). So all of it can change while the screen is up.
asm/padprompts.asm changes it every frame. The exe finds a screen DLL's
routines by name with `GetProcAddress`, so the export table's entry for
the DLL's Exec routine becomes the stub's RVA. The stub asks the annex's
page poll for side 0's input `0x3e`, which is down while that side holds
a pad. It writes a list of dwords from a table the patcher appends after
the code, each as the stock's value or the pad's, and jumps to the
export's own routine. With the poll slot empty it writes the stock's. A
row whose RVA has bit 31 set gives, for each device, the RVA of a dword
to copy instead of a value: the entries' sheet numbers, which init
replaces with texture handles (below).

Each DLL binds its pages once, at init: it loads its TXR, copies the
file's texture handles into an array (`ReplayGallery.dll` `0x100be208`,
`Record.dll` `0x101118dc`, `Options.dll` `0x100b8bdc`) and, for each
page it draws from, walks a record `(entries, count)` and replaces each
entry's sheet number with the handle at that index, skipping -1
(`ReplayGallery.dll` `0x1000b7d0`, `Record.dll` `0x1000f170`,
`Options.dll` `0x1000ed90`). So an entry's sheet number is a handle
once the screen is up, an entry past the record's count is never bound,
and a -1 dword past the count is not a spare entry: the dword after a
page's last entry is usually its own record, then its sprites and
quads, whose white colour is also -1. `_page_count` reads the record,
and `_spares` takes spares within it alone. (An earlier version took -1
dwords past the count, which put the gallery sort box's boxes over its
quads: the plates drew pieces of other sheets, and LB crashed the game.
It was never released.)
`PROMPTS` in the patcher names each key's DLL, export and routine, and
`prompt_fields` lists what the stub switches. The patcher finds the
export's entry by name (`_export_slot`), because it is at another file
offset in the Australian `Title.dll`.

**The art.** The pad's lettering is written on a sheet of the prompt's
file at patch time: on a stock sheet where one has room, otherwise on a
sheet the patcher appends (`Record.txr` a sixteenth, each `RG_` file a
tenth, `OPTIONS.TXR` a fourteenth after the devices patch's thirteenth),
256x256 4444 and clear white like the stock gutters. Every screen DLL
copies the file's texture handles into an array of 256 (`Record.dll`
`0x101118dc`, `ReplayGallery.dll` `0x100be208`, `Options.dll`
`0x100b8bdc`), so a sheet more is room enough. `tools/prompts.py`
renders the art and bakes the texels into the patcher (`PROMPT_ART`),
each blit with its file, sheet and language. `prompt_txr` writes a
file's blits after checking each stock sheet the key touches against
its MD5; a sheet that a release has in another language names the
file's language, which picks the blits and the stub's table
(`PROMPT_VARIANT`). The file gets a `.bak` as `OPTIONS.TXR` does. The
tool draws a line eight times the size and averages it down, and takes
the face, the size, a width, a boldness across, the tracking and the
origin. Given an installed game, it also sets the stock prompt's own
words and prints how they compare with the stock texels. The faces were
chosen by fitting about 45 open fonts to each stock prompt that way:

| Stock lettering | Face | Fit |
| --- | --- | --- |
| the title | Nimbus Roman Bold (Times Bold) | below |
| the attract screen | Open Sans Bold Italic, 125% wide | 9.8% of the ink off; Noto Sans Bold Italic is as close, Nimbus Sans Bold Italic 20% |
| the replay prompt | Nimbus Sans Bold Italic (Helvetica Bold Oblique), 85% wide, two sizes, 1 px bolder | by eye: the words' widths and cap heights, the stock's straight-hooked f, and the outline's count of black and grey texels (stock 665 and 394 of the box, the render 660 and 431) |
| the frame's hint lines, 12 px caps | Liberation Sans Narrow Bold, 84% wide, 0.3125 px bolder, tracked 0.75 px, word gaps 0.25 px closer | 7.6% a word over 29 stock words, each word placed on its own; the three stock lines come out 0, 1 and 2 texels wider. The stock's caps fill rows 1 to 12 of a strip and its stems are two texels. An earlier fit at 11 px caps and 90% wide scored 9.9% on half a line and 14.1% a word: its letters were a row short and half a texel fatter, which showed in the game |
| the Records labels, 9 px caps | Liberation Sans Narrow Bold, 90% wide | about 28%: no face tried does better than about 15% a word, the stock's rasteriser being sharper than any render |
| the gallery's plates | URW Gothic Demi, 105% wide | 12% a word |
| the Japanese lines | Noto Sans CJK JP Bold, 14 px, 100% wide, 0.125 px bolder, tracked -0.25 px | the stock's own three lines come out within 4 texels of the stock's width; at 105% wide and untracked they were 11 to 32 texels wider. The letters' places still differ, the stock face setting its kana closer. The bubble behind a bar is a sprite of its own, the stock line's width, so a pad line wider than the stock's hangs out of it: the Records bar's pad line says Bボタンで戻ります, not 前画面に戻ります (372 texels against the stock's 406; the longer form is 427, and at the earlier setting's 456 was seen hanging out in the Japanese build). The popups' lines are 364 and 367 against the stock's 381 and 386, the gallery foot's 179 against 181; `tools/prompts.py` refuses a bar line past 410. The lines at this setting have not been seen in the game |
| the lobby buttons and the team room's TAB button, 10 px caps | Noto Sans Mono Regular, 13.5 px, 92.5% wide, tracked 1 px | 23.5% on SHOW TEAMS; of 46 monospaced and technical faces tried, Source Code Pro and Space Mono come next at 26% |

**The bars.** A bar line is a sprite of two quads about the bar's
centre, each a strip of 17 rows with two white texels beyond each end,
the stock's 207 wide and overlapping at the centre. The pad's line is
set the same way and cut at the word gap nearest its middle. For each
sprite the stub switches both quads' entry index and rectangle: the
page's first two spare entries (texture -1, no quad; every page has
them) are filled in at patch time as the two strips' boxes on the
appended sheet, and the rectangles put the strips end to end, centred
to a whole pixel: at half a pixel the game's filter blurs the lettering,
which made a line of odd width look smaller and bolder than the stock's
(`_bar`, `_halves_rects`). `Record.dll`'s own two quads overlap by two
pixels, (-206, -20) to (1, -3) and (-1, -20) to (206, -3), where every other
screen's meet at 0. The right half is drawn second, so its white margin
covers the last two columns of the left half, and the stock line's `a`
in `change` is cut. padprompts writes the two rectangles at `0x100c52e0` and
`0x100c5314` as (-207, -20) to (0, -3) and (0, -20) to (207, -3) for good, so
the keyboard's line is whole as well. The Records page has one such sprite, the
gallery three (its foot and the two popups), the Options frame one on
each of four pages. On the Device Settings page the two lines are the
patcher's own: `devices_page` lists each pad strip's entry right after
its keyboard strip's, and `padoptions` finds the four quads by their
rectangles and steps each entry index on by one. So `padoptions` needs
`devices`, and the patch table applies it after.

**The gallery's sort box.** Four boxes of sheet 7, 71 by 13: SORT, white
on clear, and MODE : F6, CAR : F7 and DATE : F8, black on white. Ten
pages draw them, 42 quads in all. LB and RB step the sort, so the pad's
plates read MODE, CAR and DATE and the header SORT LB/RB, in URW Gothic
Demi as the lobby's labels are. Each quad has an entry of its own, and
one page of the ten (`0x1009cf10`, 18 entries, the plates drawn over
the list) has no spare entry, so the entries are switched in place: the
box, and the sheet number through a bit-31 row, from the array's handle
for sheet 7 to its handle for the appended sheet 9. 90 rows in all.

**The team room's TAB button.** `tab_menu_on.BMP` is TAB and then MENU
on black, `tab_menu_on2.BMP` TAB on black and then CHAT, 98 by 18, the
same files in every build. Two things show TAB MENU. With the menu
closed it is painted into the room's backdrop: `CHAT.BMP` (8-bit, 640 by
480, the same file in every build) at (18, 454), 98 by 18, with TAB's
box on the same pixels as the button files'. The room object's
constructor (`0x435b90`, the class whose vtable is `0x49b82c`) loads it
first of the room's surfaces through the lobby's loader (`0x406fa0`:
context, directory `0xc`, flag, name, &object, &size, 1; the call at
`0x435c02`) into `[0x4eade0]`, and the room's first draw layer
(`0x436310`) blits the whole backdrop onto the frame every frame; the
destructor (`0x4361f0`) releases the surfaces in a loop from `0x436229`.
When TAB opens the menu, the room's key layer (`0x4366b0`) registers a
layer whose first draw is `0x437b10`: it loads thirty bitmaps from the
table at `0x4b3670` through the same loader (the loop at `0x437b3e`
pushes them from a table of `(directory, flag, name)` rows) into the
object array at `0x4eae08`, the TAB pair fifth and sixth. The objects
are MGameD3D's surfaces, the class the starting box (NOTES.md, *The starting box*) draws through: the
draw calls each one's `SetTarget` (`+0x34`) with the first object,
`MENU_BACK`, and the TAB pair's again with 0, the back buffer; the open
menu's draws read the array and call `Blit` (`+0x1c`; `0x43f301` and
about a dozen more); closing the menu frees the thirty through
`0x406f80` (the loop at `0x437aac`). The layer list is torn down
(`0x401060`) without that exit, so a room left with the menu open leaks
the thirty.

The `tabmenu` patch writes four files: `TAB_MENU_SEL.BMP` and
`TAB_MENU_SEL2.BMP`, the stock pair with TAB's letters (rows 4 to 13,
columns 10 to 33) cleared to the box's colour and SEL laid over them in
the letters' own colour; `TAB_MENU_BACK.BMP`, the backdrop's box as it
is, and `TAB_MENU_BACK_SEL.BMP`, the same with SEL. asm/tabmenu.asm has
five entries. The constructor's backdrop call goes through it: it makes
that call with the site's own seven arguments and then loads the two
backdrop files; the destructor's loop frees them, and the menu's two
objects too when the room is left with the menu open, the stock
pointers put back first. The menu layer's first draw loads the two
button files beside the stock and the menu's release loop frees them.
The multiplayer pad poll (`0x43f913`, which `padmenu` also hooks,
further on) switches the two array entries each frame while the menu's
objects are loaded and, when the pad's answer changes, blits the
matching backdrop file onto the backdrop at (18, 454) with the backdrop
as the target and the back buffer put back after; a fresh room's
backdrop counts as the keyboard's. The first version loaded the
backdrop files with the menu's, so nothing showed until the menu had
been opened once and nothing changed after it closed. `tools/tabmenutest.py`
runs the five entries under Unicorn; the patcher refuses the files when
the stock pair or `CHAT.BMP` is not the one it knows. A placeholder in a
`mov reg, imm32` whose opcode byte is the placeholder's own byte
(`mov ebx, 0xBBBBBBBB`) gets the patcher's replace on the wrong four
bytes; `asm/build.py` refuses that, and the stub loads `[ROOMBG]`
indirectly. The lobby's SHOW TEAMS button files are relettered SEARCH
from the same face: the face cleared and the mask laid over it in the
stock lettering's colour, read off the file (`lettered`). SEL in the
open and the closed menu, and the lobby's SEARCH, have been seen in the
European build under Proton.

**The replay prompt.** PRESS ENTER KEY for REPLAY is one 166 by 24 box
of sheet 9 (rows 190 to 213), the same sheet in the three `Rank` files
and `Record.txr`, drawn by six pages through six entries. Rows 214 to
236 under it hold the Dreamcast's memory-card text, which no entry
covers. The pad's PRESS A BUTTON for REPLAY goes on rows 213 to 236 of
all four files, on the same flat plate, and the stub moves the six
entries' v0 and v1 down by 23 texels. Row 213 was the stock box's last
row and is now the pad plate's first; both are plate. The words are
drawn eight times the size, the outline is the lettering spread 1.125
texels at that size, and both are averaged down; a texel is the plate
under the outline's coverage, doubled and capped at 1 for the stock's
hard black ring, with the word's colour over it by the lettering's
coverage.

**The Records pages.** Each of the five pages has a sprite of one 100
by 16 quad for PAGE UP KEY and one for PAGE DOWN KEY. The sprites' own
positions put them at (50, 225) and (50, 364). Each page has its own two
UV entries for them, `(13, 0.075, 0.075, 0.465, 0.137)` and `(13, 0.075,
0.141, 0.465, 0.204)`: the boxes (19.2, 19.2)-(119.0, 35.1) and (19.2,
36.1)-(119.0, 52.2) on sheet 13. The entries are at `0x100c46f4`,
`0x100cfadc`, `0x100d4ebc`, `0x100da1e4` and `0x100df5c4`, with PAGE
DOWN KEY's 20 bytes after each. Each box holds half of an arrow and the
lettering (rows 20-30 and 40-50). The sheet has a second arrow 34 texels
below the first, with the Dreamcast's L LEVER and R LEVER beside it. So
the pad's boxes are the keyboard's 34 texels down: v 0.208 to 0.270 and
0.274 to 0.337, in the page's three-decimal UVs. The patcher writes LB
BUTTON and RB BUTTON over L LEVER and R LEVER (texels (31, 53) to (111,
85)), on the keyboard lettering's rows 34 down, and leaves the arrow.
LB and RB turn the pages (`pagepad`).

The stock lettering is 9 px caps with 1.5 px stems. The pad's two lines
are Liberation Sans Narrow Bold with the cap height set to 9 px exactly
and the baseline on a row, so the caps' tops and feet are as sharp as
the stock's. The first letter's origin is at column 33.5, which puts its
stem on the stock P's: a full texel at column 34, then half of one.

`Record.dll` has two builds (the Australian and Sega's Japanese share
the older one). The export, the routine and the entries are at the same
places in both.

**The title.** PRESS ENTER KEY is one sprite (`0x100973a0`), 356 by 34
at (320, 330), of two quads (`0x10097338`, `0x1009736c`) over UV
entries 8 and 9 (`0x100971b0`, `0x100971c4`): the boxes (4.1, 3.1)-
(219.1, 37.1) and (112.1, 42.2)-(253.2, 76.0) on sheet 5. The image is
wider than the sheet, so the sheet holds it as two strips that overlap:
the second strip is the first 106 texels on. Rows 77 to 142 of the sheet
are free. The Exec routine (`0x100012c0`) takes bit 0 or bit 6 of the
wrapper's edge, Enter or Start.

The lettering is Times Bold, 18 px caps, with a fill that goes from
white at the top to yellow at the bottom a row at a time, over a black
glow. `tools/prompts.py` models it and prints how the model of PRESS
ENTER KEY compares with the stock texels on every run: Nimbus Roman Bold
at 26.625 px, set 2.5% wide, 0.625 px bolder across and tracked 0.8125
px, drawn at eight times the size and averaged down; the glow is the
lettering spread by a disc of radius 2.83, blurred with a sigma of
2.125 and gained 1.175. Of the 8022 texels either has, 4008 differ:
3354 by one level of 15, most of them in the glow's alpha, 375 by two
and 279 by more. PRESS START BUTTON is that model. It is 334 by 32 and goes on rows 77-108 and 110-141 as two
halves of 167. The stub switches the sprite's size, the two quads'
rectangles and the two boxes. The new boxes are inset 0.1 texel as the
stock ones are, and show a texel a pixel.

`Title.dll` has two builds too, with the sprite, quads and entries at
the same places and the export table 16 bytes on in the Australian one.

**The attract screen.** PRESS ENTER KEY is one sprite (`0x10096358`),
249 by 17 at (22, 142), of one quad (`0x10096320`) over UV entry 18 of
the page at `0x100951e0`: the box (2.0, 218.1)-(251.1, 235.0) on sheet 0
of `ADV_TXT.TXR`. Sheet 0 is full. Sheet 3 is free from row 172, and the
page has three entries with texture -1 that no quad names (111, 114 and
117). This DLL's bind adds the file's first texture number to every
entry's index (`0x10004e10`), so an entry filled in before it runs is
bound like the rest. The patcher makes entry 111 (`0x10095a8c`) the pad
lettering's box on sheet 3, and the stub switches the quad's entry index
between 18 and 111, with the quad's rectangle and the sprite's size. The
draws multiply that index by 20 each time they draw (`0x100040c0` and
three more).

`AdvTelopInit` (`0x10001000`) loads all seven sheets into texture slots
`0x5a` to `0x60` and then releases the ones its telop type does not
draw, through the texture manager's method at vtable `+0x2c`: sheets 1
and 2 (the car pictures) for types 1 and 4, sheets 3 to 6 (the names
and the makers' logos) for every other type. The exit (`0x10001240`)
releases all seven. So over the demo, sheet 3 was gone and the pad's
prompt drew as a white box, which is how the game showed it. The patcher
makes the release of sheet 3 (`push 0x5d; push eax; call [ecx+0x2c]`
at `0x112d`, 6 bytes, the same in every build) six `nop`s, so sheet 3
stays loaded for every type: 128 KB of texture memory more over the
demo. The other releases stay.

The stock lettering is white, 14.8 px caps, with greys at its edges and
an outline: every texel beside the lettering, corners included, is
`0x8842`, and no grey is fainter than 10 of 31. Spreading the stock's
lettering by one texel reproduces its outline exactly. The model is Open
Sans Bold Italic at 21 px, 125% wide, tracked -1.5 px, with that outline
rule. PRESS START BUTTON is 238 by 19 at (2, 176) on sheet 3. The box
takes the same rows of it as the stock box takes of its image, and the
quad is placed so that the lettering's middle is where the stock's is.
Both builds of `AdvTelop.dll` have the sprite, the quad and the page at
the same places.

`tools/padpromptstest.py` runs each export on the real DLL, relocated,
under Unicorn, and checks each sheet as the patcher writes it. The
`prompts` check renders the art again and compares it with the baked
texels. Every prompt here has been seen switching in the game under
Proton: the title's and the attract screen's, the Records pages' labels
and bars, the gallery's plates and lines, the replay prompt and the
Device Settings lines in the European build, the Japanese lines in the
Japanese build.

## The replay's controls

A replay's cameras do not read `MGInput`'s actions. The camera manager
(`0x411335`) keeps an input object of its own (vtable `0x49b868`, made at
`0x440b40`, `0x38` bytes) and updates it every frame (`0x440c30`, from
`0x411811`). Per player the object holds the device kind at `+8`, the
device's index at `+0x10`, the edge at `+0x18`, the level at `+0x20`, the
previous level at `+0x28` and the analog x at `+0x30`, in -127..127. `+4`
is the player count: two in 2 PLAYER BATTLE, otherwise one. The level's
bits are: 0-3 up, down, left, right; 0x10 and 0x20 the meter on and off;
0x40 the screen switch (in 2 PLAYER BATTLE, to the winner) or the watched
car (in MULTIPLAYER); 0x80 and 0x100 the revolving camera's zoom, which
is the manual's smooth in and out. Each frame the zoom is held adds or
takes 1.75/120 from `+0xd8` of the camera, clamped to ±1.75. That value
is added to the depth of the camera's offset from the car (`+0x18`, which
is copied fresh from the camera table each frame, `0x44137e`), so the
distance stays where it was left.

The keyboard fills the object from fixed scancodes (`0x440d20`). Player 1
has the arrows, Insert, Delete, TAB, Page Up and Page Down. Player 2 has
S, X, Z, C, T, G and TAB. That is the manual's table. The analog is ±127
from left and right. A joystick adds to the object only when the player's
config had one at start. The wrapper's setup (`0x47f0e9`) looks at the
first source of the config's steering record. If that source is past
`0x100`, the setup attaches joystick 0 and marks the player's kind at
`+0x14` of the player's block in the exe's input holder. The update then
reads that device's `DIJOYSTATE` directly (`0x440e20`): the axes go to
the directions and the analog, the POV is read on a kind-2 stick, and
buttons 1, 2 and 3 go to 0x30, 0xc0 and 0x100. The annex's records put a
key first on every action, so the kind is always the keyboard. An XInput
pad only answers source ids, so it never reaches this object.

The camera switch (`0x411cf0`) runs while bit 2 of the game's `+0x44`
flags is set. The replay's starts set that bit (`0x451540`, `0x4516b2`,
and the ten-year credits' `0x419b14`). The switch takes up and down from
the edge, 0x10 and 0x20 for the meter and 0x40 for the switch, and hands
the object to the camera's own input (`0x441860`). On the automatic and
side cameras, left or right on the edge turns the driver's view to the
rear, or turns the side camera to the other side. On the revolving camera
the analog turns it, or left and right from the level when the analog is
near 0, and 0x80 and 0x100 from the level zoom. The pause is the
wrapper's Start edge, as in a race.

The `replaypad` patch (asm/replaypad.asm) makes the pad a player's
whatever the kind. The two loads at the join of both paths (`0x440cea`,
`mov edx, [esi+8]; mov eax, [esi]`, where the edge is made) become a call
into the stub. The stub asks the annex's page poll (`PADPOLL`) for the
player's side (`0x300 + player * 0x40`): the bumpers, the left stick, the
triggers, Y and X. It ORs the ones past half their range into the level:
RB as up and LB as down, the next and previous camera; the left stick's
halves as left and right; RT as 0x80 and LT as 0x100, the zoom; Y as
0x30, the meter; X as 0x40, the switch. It sets the analog from the left
stick's x when the keyboard left the analog at 0. Then it does the two
loads. The D-pad, right stick, A and B are left out. The routine is the
same in every build. `tools/replaypadtest.py` runs the real update on the
patched exe under Unicorn with the input objects stubbed.

## The Options screen

The `devices` patch adds a fourth item to the Options menu and the page
behind it.

### The texture

`Options.dll` draws from `BINDATA\MISC\OPTIONS.TXR`. The file is `RTEX`,
a count, 16-byte entries `(format, size, bytes, 0)` and, from `0x1000`,
the pixels back to back. Format 0 is 565, 2 is 1555, 8 is 4444. There are
twelve textures. The Dreamcast Device Settings page survives in them
unused: both controller diagrams (8, 9), every label and the full
uppercase font (6), and the calibration bars (7). What is not there is a
steering-wheel icon. Sheet 10 holds the car, speaker and monitor icons
and a blank plate, and the blank plate is the cursor's red frame, drawn
as a nine-slice of 28-texel pieces.

### Pages and sprites

`OptionsModeInit` (`0x10003770`) loads the TXR and binds ten *pages*
through `0x1000ed90`. A page is a table of 20-byte UV entries `(texture,
u0, v0, u1, v1)`, and the loader swaps each texture index for its handle
in place. A *sprite* is 32 bytes: page, quads, count, width, height, x,
y, 0. A *quad* is 52 bytes: a UV index, a rectangle about the sprite's
centre, and four vertex colours.

`0x1000e850` draws a sprite at a given position, scale and colour;
`0x1000e5e0` draws it at its own position. Both put the quads on one
list. The flush (`0x1000e390`) sorts that list by depth (`0x1000e510`, a
stable merge on the value the device makes of z) and draws far to near.
So a sprite at z 16 goes under one at z 12, and among equals the order of
submission stands. The menu's page is `0x100ac9d8`, with 54 entries and
one `-1` between sprites. Those separators are spare, and `0xe` and
`0x11` now hold "DEVICE" from sheet 6 and the new icon.

### The menu

The menu itself (`0x10003dd0` init, `0x10003f40` exec) owns a cursor
(`0x1000ba40`) and an icon set (`0x10002330`). Both work over three-entry
tables at `0x1009c820` (frames), `0x1009c82c` (icons) and `0x1009c838`
(labels), and the menu draws the labels itself at `0x10003e10`. While
the cursor rests, it draws the frame table's entry for the item in place.
While it slides, it draws the first entry at its animated x. It draws at
z 16, with its pulse as alpha. The icons go at z 12, so the frame sits
under the plate and shows through as the plate's red holes and a 4-px
outline. The menu's state after a confirm (`0x1000421c`) draws the frame
once more at z 14 while the icon set zooms the icon.

That is five code references to the tables in all, and the patch moves
every one of them. Confirming returns the index with bit 15 set, and
`0x10003c6b` dispatches it through `0x10003dc0` to the page states. The
fourth slot was the exit state, which three items never reached. The stub
in the annex selects state 0xc. The four items sit at x 110, 250, 390 and
530.

### The item

The label is "DEVICE" over the stock "SETTINGS". The icon is on a
thirteenth sheet the patcher appends to `OPTIONS.TXR`. The patcher adds
the count and a 16-byte entry in the 4 KB header and puts the pixels at
the end. The sheet is 256x256, like the icon sheet. The loader sizes its
handle and entry arrays from the count, and the DLL's copy of the
handles has room for 256. The icon is the monitor icon's plate with the
picture's box filled back to the plate's grey, and a steering wheel cut
out of it the way the stock pictures are: holes in the plate, alpha 0
with a one-texel ramp, and the menu's dark background showing through.
The patcher draws it (`wheel_mask`); it is not copied from anywhere. It
uses the car icon's own UVs, because the page's UVs are three-decimal
values, 126.2 texels across 126 pixels, and exact fractions sample
visibly differently. The label sheet is checked by the texels of its font
and label rows. Of the twelve sheets only sheet 4, the frame's message
lettering, differs between the English and the Japanese `OPTIONS.TXR`.
So the page's hint lines are not cut from the file being patched. They
are rendered in the frame's face and carried in the patcher (*The hint
bar*).

### The states

The top-level machine (`0x10003af0`) has twelve states behind `cmp eax,
0xb` and a table at `0x10003d90`. State 1 re-inits the menu, 2 runs it,
3/5/7 init a page, 4/6/8 run a page, and 0xb leaves. The table moves to
the annex with two more entries, and the compare goes to 0xd. State 0xc
is the page's init and 0xd is its exec, both in asm/devices.asm. They are
entered as every case is, with `esi` the Options object, and they leave
through the dispatcher's epilogue (`0x10003cd6`).

Init binds the page's own UV table through `0x1000ed90` and starts the
slide-in. It binds once per load of the DLL, flagged in the blob, because
the binding writes handles over indices in place. The stock pages are
bound once, in `OptionsModeInit`, and the exe reloads the DLL for each
visit. Exec draws the list, moves the cursor, and slides the page. The
page slides in from the right, from 640 down by 40 a frame. It slides out
to the left on cancel or on a confirm over BACK, and the menu's state is
set at -640. Those are the stock pages' numbers.

### The list

The list is 40-byte entries: kind, sprite or string, x, y, z or text
flags, alpha, red, green, blue in 256ths, and the cursor's hold on the
entry. `devices_page` in the patcher builds it in the Game Settings
page's terms, and `0x100025f0` draws it. The header band, group plate and
row plate are that page's own sprites (`0x100a3128`, `0x100a3290`,
`0x100a4198`, found by their first quad). The plates are at z 14 with
alpha 0xd8, and the text is at z 10.

The text goes through the stock routine `0x1000df10` over its 14-px glyph
sprites (`0x1009c080`, one sprite per glyph, with a 256-byte character
map at `0x100fcc04` that the routine fills on first use). Its arguments
are `(string, x, y, z, advance for a missing glyph, sx, sy, alpha, r, g,
b, table, flags)`; flag 4 is proportional, 1 right-aligned, 2 centred.
The table has letters, digits, `.`, `+` and `-` only, so the colon is a
separate piece. The glyph cells carry a texel of margin around the ink
and need it: boxes cut to the ink render narrow and ragged.

The geometry is the stock's. The band and heading are at y 87, the group
plate at (48, 106), the rows of 18 from (261, 106) with 6 more between
groups, the group text at x 56, the action at 269, the colon at 397, the
value at 405, and the buttons at y 404. There are two groups, PLAYER 1
and PLAYER 2, with seven rows each.

### The cursor

The cursor is the stock's (`0x10002c30`). It moves up and down through
the rows and the button row, with DEFAULT then BACK on the button row and
left and right between them, wrapping. The sounds are the stock's: 0xe
for a move, 0xf for a confirm (BACK included), 0x10 for backing out. What
the cursor holds is drawn as Game Settings draws it: the row's plate
(0x100, 0x100, 0, 0), its group's plate (0x100, 0x100, 0x20, 0x20), the
button (0x100, 0x100, p, p) and the row's values in white with alpha
0x80 + p/2. p is the page's pulse, which goes from 0 to 0x100 and back by
0x10 a frame (`0x10002a23`). Each entry carries which rows hold it and
how.

The page shows one player at a time. A selector row comes first: the
group plate centred, with PLAYER 1 or 2 on it, and left, right or confirm
switching between them. Then come the KEY and PAD headings and the ten
rows, which are the eight driving actions, the deadzone and the
vibration strength. The rows use
Graphic Settings' own row sprite (a 123-px label plate, a 30-px fade, a
273-px value plate, three quads) at its x, and are spaced 24 px apart as
that page spaces them.

### Binding

The values are live. The page reaches the game's input objects through
the holder (`0x100b9464`, the exe's `0x50b120` block). The holder's `+8`
is the exe's input wrapper (vtable `0x4a158c`; its `+0x14(mask)` gives a
player's pressed-edge key bits). The wrapper's `+4` is `MGInput`'s input
object. From there the page reaches `GetConfig` (`+0x34`),
`GetDevice(3, 0)` (`+0x20`) for the keyboard and its `GetState` (`+0x38`, the 256 key
bytes), the config's record list at `+0x124` (a pointer to the head node
of a ring of (next, prev, record)), and `Persist` (`+0x30`) to save
(*Gamepad*). The pad comes through the poll the annex publishes at
`PADPOLL`. That is a dword in the writable room past the end of `.data`
(`0x5a1ff0`; Australian `0x60bff0`), because the Australian device has no
poll method.

A row's key record is the first record of its action with a source under
0x100. Its pad record is the first at 0x300-0x37f without the menu-only
bit. Confirm on a row snapshots what is down and waits: the row pulses
blue to white and the bar says to press the button. A key or pad input
that has been released since the wait began and is then pressed binds to
the row. The row that had that input before takes the row's old one;
for a key that may be either player's row, for a pad input the same
player's. Both configs are then saved. ESC pressed since the wait began,
or Start held for 60 frames, gives up. Left and right on the deadzone row
step it by 5% within 0 to 45%, and it is saved through a `DZnnnn` name.
On the vibration row they step the strength within 0 to 9, saved through
a `VBn` name.

Both rows are sliders drawn as the stock's volume sliders are. Sound
Settings draws a slider's ten strings, OFF and 1 to 9 (the table at
`0x1009c8c0`), with the text routine and flags 4, the set step in white
and the others in black (`0x10004a83`), each `8 × its length + 20` px
after the last. The page has ten string entries a slider in its draw
list, OFF at the values' x (271) and 1 to 9 from 311, 26 px apart, which
ends them at the value plate's far margin. `refresh` makes the set
step's entry white and gives it the row's value hold, and makes the
others black with no hold (`slider`); the data block's bytes 12 and 13
hold each slider's first entry in the list. The deadzone's step is its
percentage over 5, so a file's deadzone past 45% lights no step. DEFAULT puts the
shipped set back from the page's data block, which follows the strings
(`bind_data`). The block holds the rows' action ids and a live flag, the
defaults, the value strings the page fills, and a name per scancode and
per pad input. `tools/devicestest.py` drives the routines under Unicorn
against stubs for those objects.

### The hint bar

The hint bar under every stock page belongs to the frame object
(`0x10001cc0`). The frame pops one of fifteen lettered messages in and
out by a message number in `0x1009c784` (`0x100021b0`; the height goes
from 0 to 1 by 0.1 a frame, and the bar grows from its bottom edge at y
451). All fifteen messages are lettered, so the page leaves that number
at -1 and draws its own bar: the bar's plate and white strip copied from
message 14, grown the same way once the page is in place and dropped
before it leaves.

On the bar is one of two lines. The frame's own lettering is sheet 4:
six lines in a narrow bold grotesque with 12 px caps, dark ink on opaque
white, each in a strip of 17 rows that starts a row above its ascenders.
The page's lines are set the same way by `tools/prompts.py`, in
Liberation Sans Narrow Bold at 84% width, 0.3125 px bolder across and
tracked 0.75 px (*The pad's prompts* has the fit). A line is wider than a sheet, so each is cut in two at the word
gap nearest its middle. Each half is a strip with two texels of white
beyond each end, so the edge samples filter to white and not to the
clear gutter. The strips are baked into the patcher (`HINT_ART`), which
writes them on the appended sheet at patch time and builds the bar's
quads from their sizes. With a pad the lines say "Select an action and
hit the button to bind it" and "Hit the button to bind it, or hold
START to keep it" (*The pad's prompts*, `padoptions`).

The new data carries absolute pointers, so the annex gets a relocation
block appended to the directory in `.reloc`'s zero tail.
