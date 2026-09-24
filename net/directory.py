#!/usr/bin/env python3
"""Directory server for Sega Rally 2 internet play.

Hosts register their session once a second; guests ask for the list and
see it in the game's own team list. A join tells each side the other's
public address and port so both NATs open; when that fails within a few
seconds, the two send their game traffic through here and it is forwarded.
No state beyond the open sessions.

    python3 directory.py [port]        default 47627
    python3 directory.py status        what the journal says it did

Wire format, one UDP datagram each, all starting with the magic "SR2D":

    client -> server
        H <guid> <record>         host: my session (every second; refreshes it)
        L                         guest: the list
        J <guid>                  guest: I want this host
        R <guid> <data>           guest: forward <data> to the host
        R <guid> <ep> <data>      host: forward <data> to the guest at <ep>
    server -> client
        S <n> {<guid> <ep> <record>}...   the open sessions
        P <ep>                    the other side's endpoint
        N                         no such session (the DLL does not read it yet)
        D <ep> <data>             to a host: relayed from the guest at <ep>
        D <data>                  to a guest: relayed from the host

<guid> is 16 bytes, <ep> an IPv4 address and port, 4 + 2 bytes big-endian,
<record> the 67 bytes the game shows: max players, players, closed (a byte
each) and the team name, 64 bytes. A session expires after EXPIRE_S without
a refresh from its host; a relayed guest is forgotten after as long without
traffic.

What it refuses: an address that keeps asking for sessions that do not
exist has its joins ignored for a while (joins only: one address may be a
whole carrier NAT); more than PER_IP sessions from one address; a relayed
datagram larger than the game's; more than RELAY_RATE relayed packets a
second per guest each way, which a race never reaches and a tunnel cannot
exceed; more than LIST_RATE lists a second to one address, since a list is
far larger than the request and the source of a UDP request can be forged.
It forwards only between a session's host and the guests that
joined it through here.
"""

import socket
import subprocess
import sys
import time

MAGIC = b'SR2D'
GUID = 16
RECORD = 67
EP = 6
EXPIRE_S = 5
MAX_SESSIONS = 5000
MAX_GUESTS = 8       # relayed guests a session may hold; the game seats 3
PER_IP = 8           # as Virtual-On's rendezvous.py
LIST_MAX = 16        # the game shows 15
MAX_RELAY = 1056     # the DLL's largest datagram (16 + 1024 + a margin)
RELAY_RATE = 300     # forwarded packets/s per guest each way; a race uses ~15
LIST_RATE = 10       # lists/s to one address; a searching game asks 2.5/s
LIST_BURST = 20
MISS_LIMIT = 10      # this, the window and the ban as Virtual-On's rendezvous.py
MISS_WINDOW_S = 60
BAN_S = 600

sessions = {}   # guid -> {'host': (ip, port), 'record': bytes, 'seen': t, 'guests': {ep: {'seen': t, 'bucket': {}}}, 'relayed': bool}
misses = {}     # ip -> [first_miss_t, count] or [until_t, None] while banned
lists = {}      # ip -> (tokens, t): the list bucket


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


def miss(ip, now):
    m = misses.setdefault(ip, [now, 0])
    if m[1] is None:
        return
    m[1] += 1
    if m[1] >= MISS_LIMIT:
        misses[ip] = [now + BAN_S, None]
        print('%s banned for %ds: %d unknown sessions in %ds' % (ip, BAN_S, m[1], MISS_WINDOW_S), flush=True)


def expire(now):
    for ip in [ip for ip, m in misses.items()
               if (m[1] is None and now >= m[0]) or (m[1] is not None and now - m[0] > MISS_WINDOW_S)]:
        del misses[ip]
    for ip in [ip for ip, (_, t) in lists.items() if now - t > LIST_BURST / LIST_RATE]:
        del lists[ip]                     # full again: the same as no entry
    for g in [g for g, e in sessions.items() if now - e['seen'] > EXPIRE_S]:
        e = sessions.pop(g)
        name = e['record'][3:].split(b'\0')[0].decode('latin1', 'replace')
        print("'%s' by %s:%d closed: %d joined here, %s" % (name, *e['host'], e['joined'],
              'relayed' if e['relayed'] else 'direct'), flush=True)
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
    if len(data) < 5 or data[:4] != MAGIC:
        return
    op = data[4:5]
    body = data[5:]

    if op == b'H':
        if len(body) != GUID + RECORD:
            return
        guid, record = body[:GUID], body[GUID:]
        e = sessions.get(guid)
        if e is None:
            if len(sessions) >= MAX_SESSIONS:
                return
            if sum(1 for s in sessions.values() if s['host'][0] == addr[0]) >= PER_IP:
                return
            e = sessions[guid] = {'host': addr, 'record': record, 'seen': now, 'guests': {},
                                  'joined': 0, 'relayed': False}
            name = record[3:].split(b'\0')[0].decode('latin1', 'replace')
            print("'%s' opened by %s:%d (%d open)" % (name, *addr, len(sessions)), flush=True)
        elif e['host'] != addr:
            return                        # someone else's id
        e['record'] = record
        e['seen'] = now

    elif op == b'L':
        if over_rate(lists, addr[0], now, LIST_RATE, LIST_BURST):
            return
        out = []
        for guid, e in sessions.items():
            if len(out) == LIST_MAX:
                break
            out.append(guid + ep_bytes(e['host']) + e['record'])
        send(sock, MAGIC + b'S' + bytes([len(out)]) + b''.join(out), addr)

    elif op == b'J':
        if len(body) != GUID or banned(addr[0], now):
            return
        e = sessions.get(body)
        if e is None:
            miss(addr[0], now)
            send(sock, MAGIC + b'N', addr)
            return
        if addr not in e['guests']:
            if len(e['guests']) >= MAX_GUESTS:
                return
            e['guests'][addr] = {'seen': now, 'bucket': {}}
            e['joined'] += 1
        e['guests'][addr]['seen'] = now
        send(sock, MAGIC + b'P' + ep_bytes(e['host']), addr)
        send(sock, MAGIC + b'P' + ep_bytes(addr), e['host'])

    elif op == b'R':
        if len(body) < GUID or len(data) > 5 + GUID + EP + MAX_RELAY:
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
            send(sock, MAGIC + b'D' + rest[EP:], guest)
        else:
            ge = e['guests'].get(addr)
            if ge is None or over_rate(ge['bucket'], 'g', now):
                return
            ge['seen'] = now
            if not e['relayed']:
                e['relayed'] = True
                print("'%s' relaying for %s:%d" % (e['record'][3:].split(b'\0')[0].decode('latin1', 'replace'), *addr),
                      flush=True)
            send(sock, MAGIC + b'D' + ep_bytes(addr) + rest, e['host'])


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
        now = time.monotonic()
        try:
            data, addr = sock.recvfrom(5 + GUID + EP + MAX_RELAY + 1)
        except socket.timeout:
            data = None
        except ConnectionResetError:
            continue
        if data:
            handle(sock, data, addr, now)
        if now - swept >= 1:
            expire(now)
            swept = now


if __name__ == '__main__':
    main()
