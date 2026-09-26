# net

This directory holds the replacement `MUSASHI\MGNetWk.dll`: the stock
DLL's three COM objects over plain UDP.
[docs/NETWORK.md](../docs/NETWORK.md) describes what the exe asks of it,
and why.

## The files

| File | What it is |
| --- | --- |
| `sr2net.h`, `sr2net.c` | the core: sessions, players, reliable and unreliable messages. It has no Windows code in it |
| `sock.h` | the little of UDP the core needs, over Winsock or BSD sockets |
| `com.c` | the COM shell the game loads: the class factory and the three vtables |
| `mgnetwk.def` | the exports, as the stock DLL has them |
| `build.py` | compiles with `i686-w64-mingw32-gcc`, writes `MGNetWk.dll`, and writes its hashes into `sr2-patcher.py` |
| `MGNetWk.dll` | the compiled DLL, committed; the patcher reads it from here |
| `directory.py` | the directory server for INTERNET. It lists sessions, introduces joins, and relays them when it must |
| `directory.service` | its systemd unit; `tools/directory-install.sh` puts both in place |

## Building and testing

```bash
python3 net/build.py              # compile and write the DLL and its hashes
python3 net/build.py --check      # the `net` check: net/ and the committed DLL still agree
python3 net/build.py --out DIR    # a fresh DLL in DIR, to try by hand
```

`tools/nettest.c` is the `nettest` check. It runs a host and five guests
in one process over loopback. First it runs the joins and the roster
cleanly. Then it runs the message classes with a third of the datagrams
dropped. Then it runs a relay leg with one guest's port blackholed.

## How the patcher installs it

The patcher installs the DLL under the `netplay` key and keeps the stock
DLL as `.bak`. `lobby` and `netplay` need each other.

The DLL is committed rather than carried inside the script, because a
DLL written out as a blob in a Python file is what a scanner calls a
dropper. The patcher reads it from `net/` or from beside itself (the
Windows build reads it from `_internal`), and checks it against
`MGNETWK_SHA` before installing it.

## The wire

Every datagram is a 16-byte header and a payload. The header holds
`SR2N`, the type, the flags, from, to, a reliable sequence number, and
the last sequence number taken in order from the peer.

A guest has one link, to the host. The host has one link per guest and
forwards between them. Reliable messages are numbered per link and
acknowledged on arrival. A reliable message is sent again every 250 ms
until it is acknowledged, and delivered in order through a 64-deep
window. A receiver whose queue is full leaves the message
unacknowledged, so it comes again. A sender whose window is full drains
its socket for the acks before it gives a message up. An acknowledgement
past anything sent is ignored. Unreliable messages go as they are.

A keep-alive goes every 500 ms. Forty-five seconds of silence, or as
long with nothing acknowledged, is a dead link: the host drops that
guest, or a guest loses the session. The timeout is that long because
the game does not poll through a stage load, which can run past 12 s
under Proton, and because the exe itself waits 15 s at setup and 30 s at
the start line.

The host owns the player list. It assigns indices, giving each new
player the lowest free, unreserved slot as the stock DLL did, and sends
the roster on every change.

A search is a `QUERY` to the LAN broadcast or to the address typed. A
host that hears it answers with its session record. A host sends at
most 25 answers a second, so a search cannot be made a reflector. A join
is a `JOIN` with the session's id, an eight-byte nonce the guest made
up, the wire version (`SR2_PROTO`) and a cookie. The host answers a join
from an address it has not seen with `CHALLENGE`, which carries the
cookie that address needs. The cookie is a keyed hash (SipHash) of the
address under a secret of the host's, so the host keeps nothing per
address. The host seats only a join that brings the cookie back, so a
forged source gets 20 bytes and no seat. A seated join is answered with
`WELCOME`, which carries the guest's index, the host's, the reserved
slots, the roster and the version. Otherwise the host answers `REFUSE`:
the session is closed, full or not that session, or the join is of
another version.

The version is in the join, the welcome and the session record, and
each link keeps the version the other side gave. A later version should
add fields rather than change them, and read a peer's fields by the
peer's version, so that versions from `SR2_PROTO_MIN` up keep playing
together. A change that cannot be made that way raises `SR2_PROTO_MIN`.
A patcher from before the version sends none (0.7.0 and earlier). It is
refused, with a reason in `logs\sr2-net.log` on both sides.

`Log = 1` under `[Network]` in `SR2.CFG` turns on `logs\sr2-net.log`
beside the exe, a log of what the core did. The patcher's `netlog`
diagnostic sets it: the **Network log** box, or `--patch DIR netlog`;
`logs` includes it. The setting stays as set. The box shows the file's
value, and unticking it, or `-netlog`, sets the key back to 0. The
patcher writes the section with both keys at 0 when netplay is applied.
The DLL writes it at the game's start when the file has none. A controls
save carries it.

The game's socket is UDP 47626. When that port is taken, by a second
copy of the game on the machine, say, the DLL binds any free port and
says so in the log. INTERNET and DIRECT IP with `host:port` still work,
but a LAN search asks 47626 and will not find that machine. A join waits
up to 4 s for a direct road and 5 s more for the host's answer before it
gives up. The game's own join call holds the screen for that long.

## The directory

INTERNET goes through `net/directory.py` on UDP 47627, on Sega Online's
three servers: `segaonline.net`, `us.segaonline.net`, `jp.segaonline.net`.
The list is `SR2_DIRECTORIES` in `sr2net.h`, and the staging server is
`SR2_STAGING_DIRECTORY` beside it. That is the one place to change when
a server moves; a rebuilt DLL carries the new list. The servers' names
are looked up on a thread of the DLL's own, so a slow or absent resolver
holds the list, not the game. The search reports "connecting" until the
lookup is done.

Every datagram to the server carries a four-byte token the DLL made up
when the connection opened, and the server echoes it in every answer.
An answer without the token, from a forged server address, say, is
dropped. The form from before the token (0.7.0) is not answered.

A host registers its session with all three servers every second (`H`:
the session's id, the record the list shows with the wire version, and
a cookie), and takes it down when it leaves (`X`). A session expires
after five seconds without a refresh. The cookie is the server's. The
server makes it from the host's address and the session's id, and sends
it back (`C`) to a registration that lacks it. A registration from a
forged address never sees its cookie, so it is never listed. A guest
asks all three servers (`L`) and merges the answers, so a host anywhere
is seen from anywhere. The list puts open sessions first, and the newest
first among them.

`JOIN` names the session at the server the guest heard it from (`J`).
The server tells each side the other's public address and port. The host
sends a few packets to open its NAT, the guest's joins arrive, and the
link is direct from there. A session the server does not have is
answered `N`, and the guest stops asking.

When nothing has got through after four seconds, the guest sends its
traffic through that server (`R`). The server forwards it to the host as
`D`, with the guest's address as the token the host's replies carry
back. The host follows the guest onto the relay the moment a relayed
packet arrives. A join that reaches the host by both roads is one guest;
the nonce in it tells the host so. The relay is per guest, so a session
can have one guest direct and another relayed.

The server refuses:

- Ten different unknown sessions asked for in a minute. Joins from that
  address are then ignored for ten minutes; asking again for the same
  session counts once.
- More than eight sessions from one address.
- A relayed datagram over the game's size.
- More than 300 relayed datagrams a second per guest each way.
- More than four relayed guests of a session from one address.
- More than ten lists a second to one address, after a burst of twenty.
  A list reply is up to 1450 bytes for a 9-byte request, and a UDP
  source can be forged; a searching game asks 2.5 times a second.

It forwards only between a session's host and the guests that joined it
there.

The DLL drops a datagram longer than a header and the largest payload,
which no sender makes. It also drops a welcome whose index is past the
player table.

## Trying a new directory

A change to `directory.py`, or to the wire between it and the DLL, goes
to the staging server first: `test.segaonline.net`
(`SR2_STAGING_DIRECTORY` in `sr2net.h`). `Staging = 1` under `[Network]`
in `SR2.CFG` sends INTERNET there instead of the live three, and
`logs\sr2-net.log` says so. Run the new `directory.py` there
(`tools/directory-install.sh install`) and set the key on two machines.
Host, list, join direct and through the relay, and read both logs and
the server's journal. Then update the live servers and set the key back.
The other thing to try against the staging server is a DLL from before
the change. It should get nothing, and the journal should show nothing
odd.

## Running a directory server

```bash
sudo tools/directory-install.sh install [PORT]   # /opt/sr2-netplay, sr2-directory.service, udp/47627
sudo tools/directory-install.sh update           # after a git pull
sudo tools/directory-install.sh remove           # the unit and the files; the firewall rule is left
     tools/directory-install.sh status           # systemctl, and the last week's sessions from the journal
```
