#!/usr/bin/env python3
"""Ask a Sega Rally 2 host who is hosting, the way the netplay DLL does.

    python3 tools/query.py                  # the LAN broadcast, on every interface
    python3 tools/query.py 192.168.1.20     # one host, or host:port

Sends the DLL's T_QUERY and prints every T_SESSION that comes back within
three seconds, with the address it came from. No answer to a unicast
query means the datagram did not reach a hosting game on that port (a
firewall, another program on 47626, or no team created yet); an answer
here but none in the game points at the game's own search.
"""
import socket
import struct
import sys
import time

PORT = 47626
QUERY = b'SR2N' + bytes([1, 0, 0xff, 0xff]) + b'\0' * 8      # type 1, from and to nobody
HDR = 16


def targets(arg):
    if arg:
        host, _, port = arg.partition(':')
        return [(socket.gethostbyname(host), int(port or PORT))]
    out = [('255.255.255.255', PORT)]
    try:                                        # each interface's own broadcast, for a machine with a VPN or a bridge up
        import fcntl
        with open('/proc/net/route') as fh:
            names = {line.split()[0] for line in fh.readlines()[1:]}
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for name in sorted(names):
            try:
                raw = fcntl.ioctl(s.fileno(), 0x8919, struct.pack('256s', name.encode()[:15]))   # SIOCGIFBRDADDR
                out.append((socket.inet_ntoa(raw[20:24]), PORT))
            except OSError:
                pass
    except (ImportError, OSError):
        pass
    return list(dict.fromkeys(out))


def main(argv):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind(('', 0))
    s.settimeout(0.2)
    where = targets(argv[1] if len(argv) > 1 else '')
    print('asking %s from port %d' % (', '.join('%s:%d' % t for t in where), s.getsockname()[1]))
    seen = set()
    end = time.time() + 3
    while time.time() < end:
        for t in where:
            try:
                s.sendto(QUERY, t)
            except OSError as exc:
                print('cannot send to %s:%d: %s' % (*t, exc))
        try:
            data, addr = s.recvfrom(1500)
        except socket.timeout:
            continue
        if len(data) < HDR + 84 or data[:4] != b'SR2N' or data[4] != 2 or addr in seen:
            continue
        seen.add(addr)
        maxp, players, closed = data[HDR], data[HDR + 1], data[HDR + 2]
        name = data[HDR + 19:HDR + 83].split(b'\0')[0].decode('latin1')
        print("%s:%d hosts '%s': %d of %d, %s, wire version %d"
              % (*addr, name, players, maxp, 'closed' if closed else 'open', data[HDR + 83]))
        time.sleep(0.4)
    if not seen:
        print('no answer')
    return 0 if seen else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
