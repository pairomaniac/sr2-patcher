# net

The replacement `MUSASHI\MGNetWk.dll`: the stock DLL's three COM objects
over plain UDP. What the exe asks of it, and why, is in
[docs/NETWORK.md](../docs/NETWORK.md).

## The files

| File | What it is |
| --- | --- |
| `sr2net.h`, `sr2net.c` | the core: sessions, players, reliable and unreliable messages. No Windows in it |
| `sock.h` | the little of UDP it needs, Winsock or BSD |
| `com.c` | the COM shell the game loads: the class factory and the three vtables |
| `mgnetwk.def` | the exports, as the stock DLL has them |
| `build.py` | compiles with `i686-w64-mingw32-gcc`, writes `MGNetWk.dll` and its hashes into `sr2-patcher.py` |
| `MGNetWk.dll` | the compiled DLL, committed: the patcher reads it from here |
| `directory.py` | the directory server for INTERNET: sessions listed, joins introduced, relayed when they must be |
| `directory.service` | its systemd unit; `tools/directory-install.sh` puts both in place |

## Building and testing

```bash
python3 net/build.py              # compile and write the DLL and its hashes
python3 net/build.py --check      # the `net` check: net/ and the committed DLL still agree
python3 net/build.py --out DIR    # a fresh DLL in DIR, to try by hand
```

`tools/nettest.c` is the `nettest` check. It runs a host and five guests
in one process over loopback: first the joins and the roster cleanly,
then the message classes with a third of the datagrams dropped, then a
relay leg with one guest's port blackholed.

## How the patcher installs it

Under the `netplay` key, with the stock DLL kept as `.bak`. `lobby` and
`netplay` need each other.

The DLL is committed rather than carried inside the script, since a DLL
written out as a blob in a Python file is what a scanner calls a
dropper. The patcher reads it from `net/` or from beside itself (the
Windows build from `_internal`) and checks it against `MGNETWK_SHA`
before installing it.

## The wire

Every datagram is a 16-byte header and a payload. The header is `SR2N`,
the type, flags, from, to, a reliable sequence number and the last one
taken in order from the peer.

Guests have one link, to the host; the host has one per guest and
forwards between them. Reliable messages are numbered per link,
acknowledged on arrival, sent again every 250 ms until they are, and
delivered in order through a 64-deep window; a receiver whose queue is
full leaves one unacknowledged, so it comes again, and a sender whose
window is full drains its socket for the acks before giving one up. An
acknowledgement past anything sent is ignored. The others go as they
are.

A keep-alive goes every 500 ms. Forty-five seconds of silence, or as
long with nothing acknowledged, is a dead link: a guest dropped by the
host, or the session lost for a guest. The game does not poll through a
stage load, which can run past 12 s under Proton, and the exe itself
waits up to 45 s for a racer.

The host owns the player list. It assigns indices - the lowest free,
unreserved slot, as the stock DLL did - and sends the roster on every
change.

A search is a `QUERY` to the LAN broadcast or to the address typed,
answered with the session record - at most 25 answers a second from one
host, so a search cannot be made a reflector. A join is `JOIN` with the
session's id, an eight-byte nonce the guest made up, the wire version
(`SR2_PROTO`) and a cookie. The host answers a join from an address it
has not seen with `CHALLENGE` carrying the cookie that address needs -
a keyed hash (SipHash) of the address under a secret of the host's,
nothing kept per address - and seats only a join that brings it back, so a forged source
gets 20 bytes and no seat. Then `WELCOME` (the guest's index, the
host's, the reserved slots, the roster and the version) or `REFUSE`
(closed, full, not that session, or another version).

The version is in the join, the welcome and the session record, and
each link keeps the one the other side gave. A later version should add
fields rather than change them and read a peer's by its version, so
versions from `SR2_PROTO_MIN` up keep playing together; a change that
cannot be made that way raises `SR2_PROTO_MIN`. A patcher from before
the version, which sends none (0.7.0 and earlier), is refused with a
reason in `logs\sr2-net.log` on both sides.

`Log = 1` under `[Network]` in `SR2.CFG` turns on `logs\sr2-net.log` beside
the exe, a log of what the core did: the patcher's `netlog` diagnostic
(the **Network log** box, or `--patch DIR netlog`; `logs` includes it),
and a plain Apply sets it back to 0. The patcher writes the section
with both keys at 0 when netplay is applied, the DLL writes it at the
game's start when the file has none, and a controls save carries it.

The game's socket is UDP 47626. When that port is taken - a second copy
of the game on the machine, say - the DLL binds any free port and says
so in the log; INTERNET and DIRECT IP with `host:port` still work, but
a LAN search, which asks 47626, will not find that machine. A join
waits up to 4 s for a direct road and 5 s more for the host's answer
before giving up, and the game's own join call holds the screen for
that long.

## The directory

INTERNET goes through `net/directory.py` on UDP 47627, on Sega Online's
three servers: `segaonline.net`, `us.segaonline.net`, `jp.segaonline.net`.
The list is `SR2_DIRECTORIES` in `sr2net.h`, the staging server
`SR2_STAGING_DIRECTORY` beside it: the one place to change when a
server moves; a rebuilt DLL carries the new list.
Their names are looked up on a thread of the DLL's own, so a slow or
absent resolver holds the list, not the game; the search reports
"connecting" until the lookup is done.

Every datagram to the server carries a four-byte token the DLL made up
when the connection opened, and the server echoes it in every answer;
an answer without it - from a forged server address, say - is dropped.
The form from before the token (0.7.0) is not answered.

A host registers its session with all three every second (`H`: the
session's id, the record the list shows with the wire version, and a
cookie) and takes it down when it leaves (`X`); it expires after five
seconds without a refresh. The cookie is the server's, made from the
host's address and the session's id and sent back (`C`) to a
registration without it: a registration from a forged address never
sees its cookie, so it is never listed. A guest asks all three (`L`)
and merges the answers,
so a host anywhere is seen from anywhere; the list puts open sessions
first and the newest first among them.

`JOIN` names the session at the server the guest heard it from (`J`).
The server tells each side the other's public address and port, the host
sends a few packets to open its NAT, the guest's joins arrive, and the
link is direct from there. A session the server does not have is
answered `N`, and the guest stops asking.

When nothing has got through after four seconds the guest sends its
traffic through that server (`R`), which forwards it to the host as `D`
with the guest's address as the token the host's replies carry back. The
host follows the guest onto the relay the moment a relayed packet
arrives. A join that reaches the host by both roads is one guest, told
apart by the nonce in it. The relay is per guest, so a session can have
one guest direct and another relayed.

What the server refuses: ten different unknown sessions asked for in a
minute (joins from that address ignored for ten minutes; asking again
for the same one counts once), more than eight sessions from one
address, relayed datagrams over the game's size, more than 300 a second
per guest each way, more than four relayed guests of a session from one
address, and more than ten lists a second to one address after a burst
of twenty (a list reply is up to 1450 bytes for a 9-byte request and a
UDP source can be forged; a searching game asks 2.5 times a second). It
forwards only between a session's host and the guests that joined it
there.

The DLL drops a datagram longer than a header and the largest payload,
which no sender makes, and a welcome whose index is past the player table.

## Trying a new directory

A change to `directory.py` or to the wire between it and the DLL goes to
the staging server first: `test.segaonline.net` (`SR2_STAGING_DIRECTORY`
in `sr2net.h`). `Staging = 1` under `[Network]` in `SR2.CFG` sends
INTERNET there instead of the live three; `logs\sr2-net.log` says so. Run
the new `directory.py` there (`tools/directory-install.sh install`),
set it on two machines, host, list, join direct and through the relay,
and read both logs and the server's journal. Then update the live
servers and set it back. A DLL from before the change is the other
thing to try against it: it should get nothing, and the journal should
show nothing odd.

## Running a directory server

```bash
sudo tools/directory-install.sh install [PORT]   # /opt/sr2-netplay, sr2-directory.service, udp/47627
sudo tools/directory-install.sh update           # after a git pull
sudo tools/directory-install.sh remove           # the unit and the files; the firewall rule is left
     tools/directory-install.sh status           # systemctl, and the last week's sessions from the journal
```
