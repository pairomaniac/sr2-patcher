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

The DLL is committed rather than carried inside the script: a whole DLL
written out as a blob in the middle of a Python file is what a scanner
calls a dropper. The patcher reads it from `net/` or from beside itself - the Windows
build from its `_internal` folder - and checks it against `MGNETWK_SHA`
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

A keep-alive goes every 500 ms. Six seconds of silence, or six seconds
with nothing acknowledged, is a dead link: a guest dropped by the host,
or the session lost for a guest.

The host owns the player list. It assigns indices - the lowest free,
unreserved slot, as the stock DLL did - and sends the roster on every
change.

A search is a `QUERY` to the LAN broadcast or to the address typed,
answered with the session record - at most 25 answers a second from one
host, so a search cannot be made a reflector. A join is `JOIN` with the
session's id, an eight-byte nonce the guest made up, the wire version
(`SR2_PROTO`) and a cookie. The host answers a join from an address it
has not seen with `CHALLENGE` carrying the cookie that address needs -
made from a secret of the host's and the address, nothing kept per
address - and seats only a join that brings it back, so a forged source
gets 20 bytes and no seat. Then `WELCOME` (the guest's index, the
host's, the reserved slots, the roster and the version) or `REFUSE`
(closed, full, not that session, or another version).

The version is in the join, the welcome and the session record, so two
patchers of different wire versions refuse each other with a reason in
`sr2-net.log` rather than misunderstand each other; a session listed
with another version is refused before a join goes out. `SR2_PROTO` in
`sr2net.h` is bumped when the wire changes.

`sr2-net.log` beside the exe, created empty, turns on a log of what the
core did.

## The directory

INTERNET goes through `net/directory.py` on UDP 47627, on Sega Online's
three servers: `segaonline.net`, `us.segaonline.net`, `jp.segaonline.net`.

Every datagram to the server carries a four-byte token the DLL made up
when the connection opened, and the server echoes it in every answer;
an answer without it - from a forged server address, say - is dropped.
The server still answers the form from before the token in kind.

A host registers its session with all three every second (`H`: the
session's id and the record the list shows, with the wire version) and
takes it down when it leaves (`X`); it expires after five seconds
without a refresh. A guest asks all three (`L`) and merges the answers,
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
per guest each way, and more than ten lists a second to one address
after a burst of twenty, since a list reply is up to 1450 bytes for a
9-byte request and a UDP source can be forged. A searching game asks 2.5
times a second. It forwards only between a session's host and the guests
that joined it there.

The DLL drops a datagram longer than a header and the largest payload,
which no sender makes, and a welcome whose index is past the player table.

## Running a directory server

```bash
sudo tools/directory-install.sh install [PORT]   # /opt/sr2-netplay, sr2-directory.service, udp/47627
sudo tools/directory-install.sh update           # after a git pull
sudo tools/directory-install.sh remove           # the unit and the files; the firewall rule is left
     tools/directory-install.sh status           # systemctl, and the last week's sessions from the journal
```
