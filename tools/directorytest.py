#!/usr/bin/env python3
"""The directory server's list limit, without a network.

    python3 tools/directorytest.py

net/directory.py's handler called with a socket that records what it
sends and a clock set by hand. Checked: a list for every request up to
the burst, then LIST_RATE a second; each address its own bucket; an
idle address's bucket forgotten; a full list of 16 sessions still one
datagram under 1472 bytes, open sessions first and the newest of those
first; the token echoed and the old form answered in its own; a join to
no session answered N and counted once however often it is asked; the
host's X taking the session down.
"""
import contextlib
import importlib.util
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location('directory', os.path.join(ROOT, 'net', 'directory.py'))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class Sock:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))


TOKEN = b'\x11\x22\x33\x44'
HEAD = d.MAGIC + b'%s' + TOKEN


def head(op):
    return d.MAGIC + op + TOKEN


def lists(sock, addr, n, now):
    before = len(sock.sent)
    for _ in range(n):
        d.handle(sock, head(b'L'), addr, now)
    return sum(1 for data, to in sock.sent[before:] if to == addr and data[4:5] == b'S')


def main():
    sock = Sock()
    a, b = ('198.51.100.7', 5000), ('203.0.113.9', 5000)
    t = 1000.0
    assert lists(sock, a, 100, t) == d.LIST_BURST, 'the burst'
    assert lists(sock, a, 1, t) == 0, 'past the burst'
    assert lists(sock, b, 5, t) == 5, 'another address held by the first'
    assert lists(sock, a, 100, t + 1) == d.LIST_RATE, 'the rate'
    for k in range(40):                           # a game searching: every 400 ms
        assert lists(sock, a, 1, t + 2 + k * 0.4) == 1, 'a searching game refused'
    d.expire(t + 100)
    assert not d.lists, 'idle buckets kept'
    with contextlib.redirect_stdout(io.StringIO()):     # the server's own log lines
        for k in range(18):
            guid = bytes([k + 1]) * 16
            record = bytes([4, 1, 1 if k == 3 else 0]) + (b'T%d' % k).ljust(64, b'\0') + bytes([1])
            d.handle(sock, head(b'H') + guid + record, ('192.0.2.%d' % (k + 1), 6000), t + 100 + k)
    sock.sent.clear()
    assert lists(sock, a, 1, t + 120) == 1
    data = sock.sent[-1][0]
    assert data[:9] == head(b'S'), 'the token echoed'
    assert data[9] == d.LIST_MAX and len(data) <= 1472, 'the full list'
    most = len(data)
    entries = [data[10 + i * 90:10 + (i + 1) * 90] for i in range(d.LIST_MAX)]
    assert entries[0][:16] == bytes([18]) * 16 and entries[1][:16] == bytes([17]) * 16, 'the newest first'
    assert all(e[:16] != bytes([4]) * 16 for e in entries), 'the closed one is not among sixteen open'
    assert all(e[-1] == 1 for e in entries), 'the version in each record'
    with contextlib.redirect_stdout(io.StringIO()):
        d.handle(sock, d.MAGIC_OLD + b'L', b_old := ('203.0.113.10', 5000), t + 120)
    data = sock.sent[-1][0]
    assert data[:5] == d.MAGIC_OLD + b'S' and data[5] == d.LIST_MAX and len(data) == 6 + 89 * d.LIST_MAX, 'the old form answered in kind'
    assert sock.sent[-1][1] == b_old
    # a join to a session that is not there: N, and one miss however often it is asked
    sock.sent.clear()
    for k in range(20):
        d.handle(sock, head(b'J') + bytes([0xee]) * 16, a, t + 121 + k * 0.3)
    assert [data[4:5] for data, to in sock.sent] == [b'N'] * 20, 'N for each'
    assert not d.banned(a[0], t + 130), 'one unknown session asked for twenty times is one miss'
    with contextlib.redirect_stdout(io.StringIO()):
        for k in range(d.MISS_LIMIT):
            d.handle(sock, head(b'J') + bytes([0xe0 + k]) * 16, a, t + 130)
    assert d.banned(a[0], t + 131) and not d.banned(b[0], t + 131), 'ten different ones is a ban, of that address'
    # the host takes its session down
    sock.sent.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        d.handle(sock, head(b'X') + bytes([18]) * 16, ('192.0.2.99', 6000), t + 140)
        assert bytes([18]) * 16 in d.sessions, 'X from another address ignored'
        d.handle(sock, head(b'X') + bytes([18]) * 16, ('192.0.2.18', 6000), t + 140)
    assert bytes([18]) * 16 not in d.sessions, 'X from the host closes it'
    print('directory: lists held to %d/s per address after %d, %d bytes at the most; the token, N, X'
          % (d.LIST_RATE, d.LIST_BURST, most))
    return 0


if __name__ == '__main__':
    sys.exit(main())
