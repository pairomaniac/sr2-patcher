#!/usr/bin/env python3
"""Wrap an .iso as a MODE1/2352 bin with a cue sheet, for testing the
disc reader on the sector form real dumps use.

    python3 tools/iso2bin.py sr2.iso sr2.bin      # writes sr2.bin and sr2.cue

EDC/ECC are left zero; nothing here checks them. Make the .iso with
genisoimage or mkisofs, e.g.
    genisoimage -o sr2.iso -graft-points DATA1.CAB=data1.head
"""
import os
import sys

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'


def msf(lba):
    lba += 150
    m, rest = divmod(lba, 75 * 60)
    s, f = divmod(rest, 75)
    return bytes(int(str(x), 16) for x in (m, s, f))


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip())
        return 2
    src, dst = argv[1], argv[2]
    with open(src, 'rb') as i, open(dst, 'wb') as o:
        lba = 0
        while True:
            user = i.read(2048)
            if not user:
                break
            o.write(SYNC + msf(lba) + b'\x01' + user.ljust(2048, b'\0') + b'\0' * 288)
            lba += 1
    cue = os.path.splitext(dst)[0] + '.cue'
    with open(cue, 'w', newline='\r\n') as fh:
        fh.write('FILE "%s" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
                 % os.path.basename(dst))
    print('wrote %s and %s, %d sectors' % (dst, cue, lba))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
