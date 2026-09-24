#!/usr/bin/env python3
"""Directory server for Sega Rally 2 internet play.

Hosts register their session once a second; guests ask for the list and
see it in the game's own team list. A join tells each side the other's
public address and port so both NATs open; when that fails within a few
seconds, the two send their game traffic through here and it is forwarded.
No state beyond the open sessions.

    python3 directory.py [port]        default 47627
    python3 directory.py status        what the journal says it did

Wire format, one UDP datagram each: the magic "SR2E", an op, a four-byte
token the client made up at start (echoed in every answer, so an answer
the client did not ask for is dropped), then the body:

    client -> server
        H <guid> <record> <cookie>  host: my session (every second; refreshes it)
        X <guid>                  host: my session is over
        L                         guest: the list
        J <guid>                  guest: I want this host
        R <guid> <data>           guest: forward <data> to the host
        R <guid> <ep> <data>      host: forward <data> to the guest at <ep>
    server -> client
        C <cookie>                to a host: the cookie its registration needs
        S <n> {<guid> <ep> <record>}...   the open sessions
        P <ep>                    the other side's endpoint
        N                         no such session
        D <ep> <data>             to a host: relayed from the guest at <ep>
        D <data>                  to a guest: relayed from the host

<guid> is 16 bytes, <ep> an IPv4 address and port, 4 + 2 bytes big-endian,
<record> the 68 bytes the game shows and one more: max players, players,
closed (a byte each), the team name, 64 bytes, and the wire version.
<cookie> is four bytes made here from the host's address and the guid:
a registration without the right one is answered with C and not listed,
so a host with a forged source address, which never sees its C, is never
listed. A session expires after EXPIRE_S without a refresh from its
host; a relayed guest is forgotten after as long without traffic.

What it refuses: an address that keeps asking for sessions that do not
exist - MISS_LIMIT different ones in MISS_WINDOW_S; asking again for one
is not counted again - has its joins ignored for a while (joins only: one
address may be a whole carrier NAT); more than PER_IP sessions from one
address; a relayed datagram larger than the game's; more than RELAY_RATE
relayed packets a second per guest each way, which a race never reaches
and a tunnel cannot exceed; more than LIST_RATE lists a second to one
address, since a list is far larger than the request and the source of a
UDP request can be forged. It forwards only between a session's host and
the guests that joined it through here. The list puts open sessions
first, the newest of them first, and stops at LIST_MAX.
"""

import hashlib
import secrets
import socket
import subprocess
import sys
import time

MAGIC = b'SR2E'
HEAD = 9                # the magic, the op, the token
GUID = 16
RECORD = 68             # max, players, closed, name[64], version
COOKIE = 4
EP = 6
EXPIRE_S = 5
MAX_SESSIONS = 5000
MAX_GUESTS = 8       # relayed guests a session may hold; the game seats 3
GUESTS_PER_IP = 4    # of them from one address
PER_IP = 8           # as Virtual-On's rendezvous.py
LIST_MAX = 16        # the game shows 15
MAX_RELAY = 1056     # the DLL's largest datagram (16 + 1024 + a margin)
RELAY_RATE = 300     # forwarded packets/s per guest each way; a race uses ~15
LIST_RATE = 10       # lists/s to one address; a searching game asks 2.5/s
LIST_BURST = 20
MISS_LIMIT = 10      # this, the window and the ban as Virtual-On's rendezvous.py
MISS_WINDOW_S = 60
BAN_S = 600
MAX_MISSES = 10000   # addresses remembered for their misses; the oldest forgotten past it

sessions = {}   # guid -> {'host': (ip, port), 'token': bytes, 'record': bytes, 'seen': t,
                #          'guests': {ep: {'seen': t, 'token': bytes, 'bucket': {}}}, 'relayed': bool}
SECRET = secrets.token_bytes(16)    # the cookies are made from it; a restart makes new ones
misses = {}     # ip -> [first_miss_t, {guids asked for that were not there}] or [until_t, None] while banned
lists = {}      # ip -> (tokens, t): the list bucket


def cookie_for(addr, guid):
    return hashlib.blake2b(SECRET + ep_bytes(addr) + guid, digest_size=COOKIE).digest()


def ep_bytes(addr):
    return socket.inet_aton(addr[0]) + addr[1].to_bytes(2, 'big')


def ep_addr(raw):
    return socket.inet_ntoa(raw[:4]), int.from_bytes(raw[4:6], 'big')


def send(sock, data, addr):
    try:
        sock.sendto(data, addr)
    except OSError as exc:
        print('send to %s:%d failed: %s' % (*addr, exc), flush=True)


def banned(ip, now):
    m = misses.get(ip)
    if not m:
        return False
    if m[1] is None:
        if now < m[0]:
            return True
        del misses[ip]
        return False
    if now - m[0] > MISS_WINDOW_S:
        del misses[ip]
    return False


def miss(ip, guid, now):
    if ip not in misses and len(misses) >= MAX_MISSES:
        del misses[next(iter(misses))]
    m = misses.setdefault(ip, [now, set()])
    if m[1] is None:
        return
    m[1].add(guid)
    if len(m[1]) >= MISS_LIMIT:
        misses[ip] = [now + BAN_S, None]
        print('%s banned for %ds: %d unknown sessions in %ds' % (ip, BAN_S, MISS_LIMIT, MISS_WINDOW_S), flush=True)


def closed(guid, why):
    e = sessions.pop(guid)
    print("'%s' by %s:%d closed: %d joined here, %s, %s" % (session_name(e), *e['host'], e['joined'],
          'relayed' if e['relayed'] else 'direct', why), flush=True)


def session_name(e):
    """The team name as the log shows it: printable, one line."""
    raw = e['record'][3:3 + 64].split(b'\0')[0].decode('latin1', 'replace')
    return ''.join(c if 32 <= ord(c) < 127 else '?' for c in raw)


def expire(now):
    for ip in [ip for ip, m in misses.items()
               if (m[1] is None and now >= m[0]) or (m[1] is not None and now - m[0] > MISS_WINDOW_S)]:
        del misses[ip]
    for ip in [ip for ip, (_, t) in lists.items() if now - t > LIST_BURST / LIST_RATE]:
        del lists[ip]                     # full again: the same as no entry
    for g in [g for g, e in sessions.items() if now - e['seen'] > EXPIRE_S]:
        closed(g, 'not refreshed')
    for e in sessions.values():
        for ep in [ep for ep, ge in e['guests'].items() if now - ge['seen'] > EXPIRE_S]:
            del e['guests'][ep]


def over_rate(bucket, side, now, rate=RELAY_RATE, burst=RELAY_RATE):
    tokens, last = bucket.get(side, (burst, now))
    tokens = min(burst, tokens + (now - last) * rate)
    if tokens < 1:
        bucket[side] = (tokens, now)
        return True
    bucket[side] = (tokens - 1, now)
    return False


def handle(sock, data, addr, now):
    """One datagram: the magic, the op, the sender's token, the body."""
    if len(data) < HEAD or data[:4] != MAGIC:
        return
    op, token, body = data[4:5], data[5:HEAD], data[HEAD:]

    def reply(op, payload=b'', token=token):
        return MAGIC + op + token + payload

    if op == b'H':
        if len(body) != GUID + RECORD + COOKIE:
            return
        guid, record = body[:GUID], body[GUID:GUID + RECORD]
        if body[GUID + RECORD:] != cookie_for(addr, guid):
            send(sock, reply(b'C', cookie_for(addr, guid)), addr)
            return
        e = sessions.get(guid)
        if e is None:
            if len(sessions) >= MAX_SESSIONS:
                return
            if sum(1 for s in sessions.values() if s['host'][0] == addr[0]) >= PER_IP:
                return
            e = sessions[guid] = {'host': addr, 'token': token, 'record': record, 'seen': now, 'guests': {},
                                  'joined': 0, 'relayed': False}
            print("'%s' opened by %s:%d (%d open)" % (session_name(e), *addr, len(sessions)), flush=True)
        elif e['host'] != addr:
            return                        # someone else's id
        e['record'] = record
        e['seen'] = now
        e['token'] = token

    elif op == b'X':
        e = sessions.get(body) if len(body) == GUID else None
        if e is not None and e['host'] == addr:
            closed(body, 'the host left')

    elif op == b'L':
        if over_rate(lists, addr[0], now, LIST_RATE, LIST_BURST):
            return
        # open and not full first, the freshest first among equals
        order = sorted(sessions.items(), key=lambda ge: (ge[1]['record'][2] != 0, -ge[1]['seen']))
        out = [guid + ep_bytes(e['host']) + e['record'] for guid, e in order[:LIST_MAX]]
        send(sock, reply(b'S', bytes([len(out)]) + b''.join(out)), addr)

    elif op == b'J':
        if len(body) != GUID or banned(addr[0], now):
            return
        e = sessions.get(body)
        if e is None:
            miss(addr[0], body, now)
            send(sock, reply(b'N'), addr)
            return
        if addr not in e['guests']:
            if len(e['guests']) >= MAX_GUESTS or sum(1 for g in e['guests'] if g[0] == addr[0]) >= GUESTS_PER_IP:
                return
            e['guests'][addr] = {'seen': now, 'bucket': {}}
            e['joined'] += 1
        e['guests'][addr]['seen'] = now
        e['guests'][addr]['token'] = token
        send(sock, reply(b'P', ep_bytes(e['host'])), addr)
        send(sock, reply(b'P', ep_bytes(addr), e['token']), e['host'])

    elif op == b'R':
        if len(body) < GUID or len(data) > HEAD + GUID + EP + MAX_RELAY:
            return
        e = sessions.get(body[:GUID])
        if e is None:
            return
        rest = body[GUID:]
        if addr == e['host']:
            if len(rest) < EP:
                return
            guest = ep_addr(rest[:EP])
            ge = e['guests'].get(guest)
            if ge is None or over_rate(ge['bucket'], 'h', now):
                return
            e['seen'] = now
            e['token'] = token
            send(sock, reply(b'D', rest[EP:], ge['token']), guest)
        else:
            ge = e['guests'].get(addr)
            if ge is None or over_rate(ge['bucket'], 'g', now):
                return
            ge['seen'] = now
            ge['token'] = token
            if not e['relayed']:
                e['relayed'] = True
                print("'%s' relaying for %s:%d" % (session_name(e), *addr), flush=True)
            send(sock, reply(b'D', ep_bytes(addr) + rest, e['token']), e['host'])


UNIT = 'sr2-directory'


def status(unit=UNIT, days=7):
    try:
        out = subprocess.run(['journalctl', '-u', unit, '--since', '%d days ago' % days, '-o', 'short-unix',
                              '--no-pager'], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        print('cannot read the journal for %s: %s' % (unit, exc))
        return 1
    if out.returncode:
        print(out.stderr.strip() or 'journalctl failed')
        return 1
    now = time.time()
    day = {'opened': 0, 'closed': 0, 'joined': 0, 'relayed': 0}
    week = dict(day)
    for line in out.stdout.splitlines():
        head = line.split(None, 1)
        try:
            ts = float(head[0])
        except (IndexError, ValueError):
            continue
        for key, mark in (('opened', ' opened by '), ('closed', ' closed: ')):
            if mark in line:
                week[key] += 1
                if now - ts <= 86400:
                    day[key] += 1
        if ' closed: ' in line:
            tail = line.split(' closed: ', 1)[1]
            n = int(tail.split()[0])
            week['joined'] += n
            week['relayed'] += tail.endswith('relayed')
            if now - ts <= 86400:
                day['joined'] += n
                day['relayed'] += tail.endswith('relayed')
    print('%-16s%12s%12s' % (unit, '24 hours', '%d days' % days))
    for key in ('opened', 'closed', 'joined', 'relayed'):
        print('  %-14s%12d%12d' % (key, day[key], week[key]))
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'status':
        sys.exit(status())
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 47627
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', port))
    sock.settimeout(1.0)
    print('listening on udp/%d' % port, flush=True)
    swept = 0
    while True:
        try:
            data, addr = sock.recvfrom(HEAD + GUID + EP + MAX_RELAY + 1)
        except (socket.timeout, ConnectionResetError):
            data = None
        now = time.monotonic()
        if data:
            handle(sock, data, addr, now)
        if now - swept >= 1:
            expire(now)
            swept = now


if __name__ == '__main__':
    main()
