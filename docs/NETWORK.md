# Network

This document describes how the game's multiplayer works and what the
patcher puts in place of DirectPlay. The first half was read off the
European Pentium III exe and the `MGNetWk.dll` every release ships (one
build, MD5 `0a9f86f5…`), with pefile and capstone. The second half
describes `net/`. Addresses are VAs: the exe's base is `0x400000`, the
DLL's base `0x10000000`.

## What ships

The stock game has three layers:

1. **The exe** owns the lobby screens, the team room, the chat and its own
   message protocol above the transport (`0x435000`–`0x440400`). It also
   owns the race-time exchange of car states (`0x437ed0`–`0x4383d0`,
   `0x417bd0`). `MainMode.dll` never touches the network: the exe's race
   object calls MainMode's Exec, and polls and sends around that call
   (`0x417d87`).
2. **`MUSASHI\MGNetWk.dll`** ("MGameNetwork", Musashi SDK 0.9) is a COM
   server with CLSID `{0D5837F0-3E3C-11D2-924E-00A0C9697E45}` and one extra
   export `_CreateGameNetwork@4`. It wraps DirectPlay into three objects the
   exe uses through vtables. The DLL has no thread, no timer and no critical
   section: everything runs inside the exe's per-frame `Poll`.
3. **DirectPlay 3/4** (`DPLAYX.dll`) is created with `CoCreateInstance`;
   `DirectPlayCreate` is used once, to list modems. The service providers
   are TCP/IP, IPX, modem and serial, chosen by compound address. Sessions
   are created with `DPSESSION_MIGRATEHOST | KEEPALIVE`.

The exe also imports four WSOCK32 functions, only to print its own address
on the team room's status line (`0x436038`). With the `lobby` patch that
line comes from the DLL (*Where it stands*).

### The network object

The exe creates the network object at `0x43ff70` (`CoCreateInstance`, IID
`{0D5837F1-…}`) and keeps it at `0x4eac0c`. Its vtable is at `0x10015270`.
The exe calls these slots:

| Slot | Address | Call | Does |
| --- | --- | --- | --- |
| `+0x0c` | `0x10002550` | `SetAppGuid(struct)` | copies the 16-byte application GUID. The struct at `0x4b5338` is `{GUID 6A470280-0790-11D3-9E1B-00A0C9A0F04F, latency 5000, "157.109.86.141"}` |
| `+0x10` | `0x10002600` | `EnumModems(cb, ctx)` | lists the modem names through `DirectPlayCreate` + `EnumAddress` |
| `+0x14` | `0x10002770` | `EnumConnections(cb, ctx)` | calls `IDirectPlay3::EnumConnections`. The exe never calls this slot |
| `+0x18` | `0x10002a50` | `OpenConnection(struct)` | takes `{kind, arg1, arg2}`. Kind 1 is TCP/IP with `arg1` the IP string (empty means broadcast), 2 IPX, 3 modem (`arg1` the device, `arg2` the phone number), 4 serial (a `DPCOMPORTADDRESS` at `arg1`), 5 a raw compound address. It builds the address and calls `InitializeConnection` on a fresh `IDirectPlay3A`, kept at `0x1001c69c` |
| `+0x1c` | `0x10002af0` | `SelectConnection(index)` | picks a connection from the `EnumConnections` list. The exe never calls it |
| `+0x20` | `0x10002950` | `ConnectViaLobby(params, &session, &player)` | calls `IDirectPlayLobby3::GetConnectionSettings` and `ConnectEx`, for a game launched by a DirectPlay lobby (HEAT). The exe tries it at startup (`0x437cb0`) and on the connection screen (`0x43c198`). It fails on any machine today |
| `+0x24` | `0x10002b70` | `EnumSessions(cb, ctx)` | calls `IDirectPlay::EnumSessions(ASYNC \| AVAILABLE)`. The callback gets a 0x60-byte record per session: `+4` max players, `+8` current players, `+0xc` join disabled, `+0x10` the instance GUID, `+0x20` name[64] |
| `+0x28` | `0x10002db0` | `JoinSession(record, &session)` | calls `Open(JOIN)` and loops while it returns `DPERR_CONNECTING` |
| `+0x2c` | `0x10002ee0` | `CreateSession(record, &session)` | calls `Open(CREATE)` with flags `0x44` |
| `+0x30` | `0x10003020` | `GetCaps(caps, flags)` | calls `IDirectPlay::GetCaps`. The exe keeps `dwLatency` at `0x4b5348` (10000 for modem) and uses it as the session-search window |

### The session object

The session object is 0x1260 bytes, with its vtable at `0x10015320`. The
three calls above return it, and the exe keeps it at `0x4eac10`. Its
fields: `+8` the DirectPlay object, `+0x14` the host's player ID, `+0x18`
"I am host" (`DPCAPS_ISHOST`), `+0x24`/`+0x28` the player list and its
count, `+0x2c` a 16-byte event FIFO, `+0x54` the reserved slot table,
`+0x60` the session description, `+0x26c` a 4 KB receive buffer. The exe
calls these slots:

| Slot | Address | Call | Does |
| --- | --- | --- | --- |
| `+0x14` | `0x10004650` | `SetOpen(bool)` | clears or sets `DPSESSION_JOINDISABLED \| NEWPLAYERSDISABLED` and calls `SetSessionDesc`. The exe passes 1 on entering the team room (`0x436035`) and 0 at START (`0x4376ae`) |
| `+0x18` | `0x10003cf0` | `CreatePlayer(name, &player)` | calls `IDirectPlay::CreatePlayer` and wraps the result in a player object. The host assigns the player an index (`0x10004960`: the lowest free, unreserved slot) and broadcasts the roster. A joiner's index stays −1 until the roster arrives |
| `+0x24` | `0x10004110` | `FindPlayerByIndex(idx, &player)` | returns the object AddRef'd. An index in the table always gets an object, whether the slot is empty or not. The team room's row draw (`0x4358ce`) writes the name pointer at `[esp+0x14]` only where the call succeeded, but reads it either way. The message loop's lookup (`0x4388db`) tests the out pointer without looking at the result at all. A failure would leave both whatever the stack held. Only an index outside 0-3 is refused |
| `+0x28` | `0x100041c0` | `GetPlayerCounts(&max, &current)` | fills the two counts |
| `+0x2c` | `0x100044f0` | `Poll()` | drains `Receive(DPRECEIVE_ALL)`. The system messages (`CREATEPLAYERORGROUP`, `DESTROYPLAYERORGROUP`, `SESSIONLOST`, `HOST`) and the DLL's own control messages keep the player list and push events. Every 32nd call re-checks the list against `EnumPlayers`. Returns `DPERR_SESSIONLOST` when the session is gone |
| `+0x30` | `0x100050a0` | `PopEvent(evt)` | fills `{type, dpid, index, 0}`. Returns 0 if an event was there, 1 if none |
| `+0x38` | `0x100047b0` | `IsSlotReserved(idx, &v)` | reads the reserved slot table, for the team room's OPEN/CLOSE rows |
| `+0x3c` | `0x10004800` | `SetSlotReserved(idx, bool)` | host only. It broadcasts the table and kicks a player sitting in the slot |
| `+0x08` | `0x10003ca0` | `Release` | the destructor calls `Close` and releases DirectPlay |

The exe handles four events (`0x438c68`). Event **0** is host identified:
`+8` holds the host's index, and if that index is mine the exe sets
`0x4eac20` = 1. Event **1** is player created, with the index at `+8`.
Event **2** is player destroyed, and **3** session lost. Types 4–7 (the
DLL's lockstep layer and slot changes) are ignored.

### The player object

The player object is 0x80 bytes, with its vtable at `0x100152e0`. Its
record is 0x60 bytes: `+4` the DirectPlay ID, `+8` the index (0–3, −1
while unassigned), `+0x10` the flags (bit 0 host, bit 1 local, bit 2
ready, bit 31 destroyed), `+0x20` name[64]. The exe keeps its own player
object at `0x4eac14` and calls these slots:

| Slot | Address | Call | Does |
| --- | --- | --- | --- |
| `+0x14` | `0x10003610` | `GetName(&str)` | calls `IDirectPlay::GetPlayerName` |
| `+0x18` | `0x100036a0` | `GetInfo(record)` | copies the record |
| `+0x20` | `0x10003720` | `GetFlags(&flags)` | returns the record's flags |
| `+0x28` | `0x10003920` | `SendTo(target, data, len, guaranteed)` | calls `Send` from me to the target's ID or `DPID_ALLPLAYERS`, with `DPSEND_GUARANTEED` when guaranteed and 0 otherwise, and puts a 2-byte header `[0][?]` before the data. The exe's wrapper at `0x438050` retries on `DPERR_BUSY` when the send is guaranteed |
| `+0x2c` | `0x10003a60` | `PopUnsequenced(&tag, buf, &len)` | returns the next message for this player with the header stripped, and sets `tag` to the sender's index. It returns `DPERR_NOMESSAGES` (`0x887700be`) when there is none, and `DPERR_BUFFERTOOSMALL` with `*len` set to the size needed when the message does not fit |
| `+0x08` | `0x10003480` | `Release` | a local player's destructor calls `DestroyPlayer` |

The DLL's own wire format is one byte of type before the payload. Type 0
is a game message. Type 2 is the roster: `{dpid, index}` pairs, sent by
the host, guaranteed. Type 3 is a player removed, 4 a new host, and 0xe
the reserved-slot table. Types 1 and 5–9 belong to a sequenced lockstep
mode (`SendSequenced`, `SetReady`, `ReadCurrent`) that the exe never
uses. Nothing else is added. The DLL has no keep-alive of its own; loss
detection was DirectPlay's.

### The exe's protocol

Every message the exe sends goes through `SendTo` with the type in byte 0.
Most messages carry the sender's index in byte 1, but not all: the clock
request `0x20` carries a 0 there (`0x438f64`), and the host's `0x25`
carries the host's own 0. A received message first indexes a table by
byte 1 (`0x438902`), then dispatches by type at `0x438922` through the
table at `0x438c78`. The handlers that read byte 1 as a player index are
`0x1b`, `0x23`, `0x24`, `0x28`, `0x2a` and `0x2e`. The receive loop at
`0x438720` calls `Poll`, handles the events, then calls `PopUnsequenced`
until it returns `NOMESSAGES`. It runs every frame in the team room,
during the MSelect screens and in the race.

| Type | Size | Guaranteed | Meaning |
| --- | --- | --- | --- |
| `0x1b` | 5+text | yes | a chat line, shown as `entry>text` |
| `0x28` | 4 | yes / no | my state: 0 left, 1 in the team room, 0xa race setup begun, 0x10 setup done, 0x81 race scene loaded. The periodic resends before the start are unguaranteed |
| `0x27` | 4 | no | "what state are you in"; the answer is a `0x28` |
| `0x29` | 2 | no | sent on entering the room. The host answers with `0x31`, everyone with `0x2a` |
| `0x2a` | 0x48 | yes | my entry: status, car, variant, name, setup, spectator flag, races/wins/retired |
| `0x31` / `0x2d` | 0x134 | yes | the host's settings block: max players, host index, course, stage, laps, time-diff, boost, the four entries. `0x2d` is the same block sent at START |
| `0x2c` | 2 | no | "your block disagrees with my entry, resend" |
| `0x2e` / `0x2f` | 2 | yes | the first is a guest leaving for a select screen, the second the host's acknowledgement |
| `0x30` | 2 | yes | a slot was opened or closed |
| `0x20` / `0x21` | 2 / 12 | no | clock sync. The first is the request; the second answers with the host's base and now, and the client sets its base from them with RTT/2 |
| `0x25` / `0x26` | 8 / 2 | the first yes | the first is the race start time (host clock + 2 s), the second the request for it |
| `0x23` | 0x24 | no | **car state**: index, frame lead, position, three words the MainMode physics fills, the sender's frame counter |
| `0x24` | 8 | yes | finish time |
| `0x2b` | 8 | no | split time |

The race setup (`0x438dc0`) runs before MainMode loads. Each machine sends
state 0xa and waits up to 15 s for every racer to reach it. The clients
then sync their clock against the host's. Each machine sends state 0x10
and waits again. The waits spin without drawing, so the `starting` patch
(NOTES.md, *The starting box*) puts a box on the room and presents it
first. At the start line (`0x41c8d0`) each machine sends state 0x81. The
host sends the start time when every racer is loaded, or after 30 s, and
all count down to the same host-clock instant.

**The race is not lockstep.** Each machine simulates its own car and sends
`0x23` unguaranteed on a cycle of `[2,3,5,7,…][players]+1` frames,
staggered by index. That is every 6 frames with two players (10 Hz) and
every 11 with four. A received state is applied to a remote car
(`0x4261e0`) by re-simulating the frame gap, clamped to 24 frames, and
blending over up to 32 frames. A late or lost packet leaves the car on its
extrapolated path. A machine that finds itself 3.5 frames behind the
others steps its simulation once extra (`0x4eaca8`, consumed at
`0x42887c`). Nothing waits for anyone. A dropped player's car becomes a
passive base car (`0x417c16`). A lost session (event 3) releases
everything and restarts the multiplayer mode at the connection screens.
Host migration is accepted (event 0 at any time) but nothing is re-sent;
only the start time, the settings and slot reservation need a host.

Nothing is persisted but `MPDATA.DAT`. It holds a 0x80-byte header (the
connection type, the COM settings, the IP string, the modem name) and the
driver profiles (0x44 bytes each: name, races, wins, retired, last race
settings). `MPDATA.TMP` is the lobby's surface backup for ALT+TAB.

### The screens

Multiplayer is main mode 0xa. The lobby object (`0x439230`) runs a task
list, and a task's `+0xc` is its state function. The screens come in this
order. First the driver name or the profile list. Then the **connection
screen** at `0x43c160` (`CONNECT.BMP`), with the rows IPX / TCP-IP / MODEM
/ SERIAL; a fifth row OTHER is drawn, but the cursor wraps in 0–3 at
`0x43bf55` and `0x43bf75`. The choice goes to `0x4eace6`. Then the
**session list** at `0x43f380` (JOIN / CREATE / SHOWTEAM / CANCEL).
SHOWTEAM dispatches on the type through `0x43efd8`. IPX opens the
connection and searches at once. TCP/IP first puts up the **IP entry**
popup at `0x43cd30` (`IP_ENTRY.BMP`); the text goes verbatim to `0x4eacec`,
a 16-byte slot, and an empty text means "broadcast". The `lobby` patch
checks that text first. The search calls `EnumSessions` every frame for
30 s while it returns `DPERR_CONNECTING`, then for `latency` ms more. JOIN
calls `JoinSession` and `CreatePlayer`, then loops with no timeout until
the index is known (`0x4402a0`). CREATE goes through the team name entry,
then calls `OpenConnection`, `CreateSession` and `CreatePlayer`. Both go
on to MSelect's car select and then the **team room** at `0x435b90`. When
the type is TCP/IP, the team room's status strip prints
`IP Address : %d.%d.%d.%d` from `gethostbyname` (`0x436038`). The lobby's
art is in `BINDATA\connect\` and `BINDATA\chat\`, and a loose file there
overrides the cabinet.

## What replaces it

The build of `net/` replaces `MUSASHI\MGNetWk.dll`. It has the same
CLSID and the same three vtables, and it carries the game's bytes
unchanged over plain UDP. The exe, its lobby and its protocol are as they
were, and the manifests already point the CLSID at the file. The `lobby`
patch is the only one that touches the exe, and it changes five things.
The connection screen has three rows. The confirm that used to reach the
modem screen now opens the list, already searching, for INTERNET and LAN.
The latency is read for every type. SHOW TEAMS on row 2, relettered
SEARCH, searches at once. The IP entry checks its address.

### Three layers

1. **The game's own protocol** is untouched. The exe builds every message
   above and hands it to the DLL as bytes with two flags: *guaranteed or
   not*, and *to everyone or to one player*. A message comes back the
   same way, tagged with the sender's index. The replacement delivers
   those bytes with that meaning.
2. **What the stock DLL and DirectPlay did underneath** is the part
   replaced. DirectPlay ran a full mesh. But the stock DLL already made
   the host the authority: the host assigned the indices, sent the roster
   and the reserved slots, and kicked players. The exe's protocol is
   host-centred too, since only the host sends the settings block and the
   start time. DirectPlay itself contributed LAN discovery, guaranteed
   delivery, keep-alives and word of a vanished player.
3. **The replacement** does the same jobs in a star: guests talk to the
   host, and the host forwards. That means one NAT pair per guest instead
   of one per pair of players, which is what works without a forwarded
   port. A guest-to-guest car state takes one extra hop, which does not
   show at 10 Hz dead reckoning.

### Three ways in

The rows INTERNET, DIRECT IP and LAN are the exe's types 0, 1 and 2. They
reach the DLL as `OpenConnection` kinds 2, 1 and 3.

- **INTERNET**: SHOW TEAMS asks all three directory servers for the open
  sessions and merges the answers into the records the session list
  draws. JOIN names one session at the server it was heard from. The
  server tells each side the other's public address and port. The host
  sends a few packets to open its NAT, the guest's joins arrive, and from
  there the two talk directly. A session the server no longer has is
  answered at once. Every datagram to the server carries a token the DLL
  made up, and the server echoes it in the answers, so a forged answer is
  not taken. When nothing has got through after four seconds, the guest
  sends through the server. The host follows onto the relay when the
  first relayed packet arrives. The relay is per guest. A host registers
  with the servers every second, with a cookie each server issued it, so
  a forged registration is never listed. The host unregisters when it
  leaves, and five seconds of silence drops it too. The servers' names
  are looked up on a thread of the DLL's own. The listing is public; the
  game's own OPEN/CLOSE and START are the controls.
- **DIRECT IP**: the host forwards UDP 47626 and presses CREATE. The
  guest's SEARCH asks for the address, or `address:port`, and lists the
  host's team. The popup refuses anything that is not an address
  (NOTES.md, *The connection screen*). The exe opens the connection with
  the address box's text for CREATE too, so the DLL looks the address up
  at the first search and not at the open; hosting never waits on a
  resolver. The team room's status line shows the local and public
  address (below). This is what TCP/IP did, without DirectPlay.
- **LAN**: the search is a broadcast, and there is no popup.

**Behind CGNAT.** Under carrier-grade or symmetric NAT, the port the
directory saw is not one the other side can reach. The punch fails, and
the relay carries that guest. The host needs no inbound path at all. It
only ever sends out to the server, and the server's forwarding comes back
through the mapping those packets keep open. The cost is the detour's
latency on every packet for that guest, and about 15 packets a second
each way on the server per relayed guest during a race. One case is not
handled: a NAT that rebinds a mapping mid-session. The host sees the new
mapping as an unknown address, and the guest loses the session after
forty-five seconds. DIRECT IP is the one row CGNAT rules out, and only
when the host is behind it.

### What the DLL covers

Every slot the exe calls is implemented over the core, except four that
only have to not fail. `EnumModems` and `EnumConnections` return `S_OK`
without calling the callback. `SelectConnection` returns `S_OK`.
`ConnectViaLobby` returns `E_FAIL`. The rest of the vtable returns
`E_NOTIMPL`. The table sets each part against what the stock DLL and
DirectPlay did:

| Stock | Here |
| --- | --- |
| `EnumSessions` was DirectPlay's broadcast search, or a typed address | The search goes to the LAN broadcast, the typed address, or the directory. It returns `DPERR_CONNECTING` for up to three seconds while nothing has answered, then the list. `GetCaps` reports 1500 ms, so the exe keeps polling for that long after the first answer |
| `CreateSession`, `JoinSession` and `CreatePlayer` were DirectPlay's `Open` and `CreatePlayer`, plus the DLL's roster | The host makes a session id. A guest sends `JOIN` with that id, a nonce, the wire version and the host's cookie; a `CHALLENGE` hands the cookie to a first join. The host answers `WELCOME` with the index, the reserved slots, the roster and the version. It answers `REFUSE` when the session is closed, full or not that session, or when the join is from before the version. The guest sends its name after that, reliably. The host sends the roster on every change |
| `SendTo`, guaranteed or not, to one player or to all | Each link has a reliable class of message (numbered, acknowledged, resent every 250 ms, delivered in order through a 64-deep window) and an unreliable one. The host forwards between guests. The receiver gets the sender's index |
| `PopUnsequenced`, `DPERR_NOMESSAGES`, `DPERR_BUFFERTOOSMALL` | The same call, with the same codes |
| events 0-3: host identified, player created, player destroyed, session lost | The same events, in the order the exe wants. A guest's loop at `0x4402a0` finds its index known the moment `CreatePlayer` returns |
| DirectPlay's keep-alive and loss detection | A keep-alive goes every 500 ms. Forty-five seconds of silence, or of nothing acknowledged, ends the link: the host drops the guest and tells the others, or the guest loses the session. That is longer than a stage load, through which the game does not poll, and longer than the exe's own 15 s and 30 s waits for a racer. A leave is announced |
| `SetOpen`, the reserved slots, a player kicked from a closed slot | The same |
| chat, names in the team room, the WIN RATIO figures | These are the exe's own messages (`0x1b`, `0x2a`), carried and not interpreted, with one exception. A game message whose second byte is past the player table is dropped. So is a message of the six types that carry the sender's index there (`0x1b`, `0x23`, `0x24`, `0x28`, `0x2a`, `0x2e`) when that byte names another player. The exe indexes its tables by that byte unchecked. The clock request `0x20` carries a 0 there, so it is not held to it. `GetName` answers from the roster |
| host migration (`DPSYS_HOST`) | Not reproduced. A host leaving is *session lost* for everyone, which the exe already handles by returning to the connection screens |
| the lockstep methods (`SendSequenced`, `SetReady`, `ReadCurrent`), `EnumConnections`, `SelectConnection`, `ConnectViaLobby`, modem, serial | Not reproduced. The exe never used them, or they cannot work today |

`net/README.md` has the wire formats and the directory. `tools/nettest.c`
runs a host and guests over loopback with a third of the datagrams
dropped, against a directory started for the run.

## Where it stands

- `lobby`, `netplay` and `padmenu` are default patches. Every part runs
  under the loopback test, and the game has been played over the DLL
  between machines. `FindPlayerByIndex` must hand back a player object
  for an empty slot, because the room's row draw reads its name whether
  or not the call succeeded.
- On DIRECT IP the team room's status line comes from
  `Network_StatusLine`, the network object's added slot `+0x38`. The
  line reads `Local: a.b.c.d  Public: e.f.g.h`. The public address comes
  from a STUN server (`stun.l.google.com`, then `stun1`), asked on a
  thread when the connection opens; the line shows `?` until the server
  answers. `Port: n` is added when 47626 was taken. The exe's own
  `gethostbyname` line is the fallback when the slot answers nothing
  (asm/status.asm).

## Ports and servers

The game uses UDP 47626. A host forwards it for DIRECT IP; a guest needs
nothing. The directory is on 47627 on Sega Online's three servers,
`segaonline.net`, `us.segaonline.net` and `jp.segaonline.net`.
`Staging = 1` under `[Network]` in `SR2.CFG` sends the game to
`test.segaonline.net` instead, for trying a change. See net/README.md,
*The directory*.
