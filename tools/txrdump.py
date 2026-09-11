#!/usr/bin/env python3
"""Dump a .TXR texture archive to PNGs.

    python3 tools/txrdump.py OPTIONS.TXR [OUTDIR]

RTEX, a count, 16-byte entries (format, size, bytes, 0), pixels from
0x1000 back to back. Format 0 is 555 without alpha, 2 is 1555, 8 is
4444. Each texture goes to texNN.png over grey, plus a montage.png of
all of them.
"""
import os
import struct
import sys

from PIL import Image


def load(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    if data[:4] != b'RTEX':
        raise ValueError('not a TXR')
    count = struct.unpack_from('<I', data, 4)[0]
    entries = [struct.unpack_from('<4I', data, 16 + 16 * i) for i in range(count)]
    off = 0x1000
    textures = []
    for fmt, width, nbytes, _ in entries:
        height = nbytes // (width * 2)
        pixels = struct.unpack_from('<%dH' % (width * height), data, off)
        img = Image.new('RGBA', (width, height))
        if fmt == 8:
            img.putdata([((v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17, (v >> 12) * 17) for v in pixels])
        else:
            img.putdata([((v >> 10 & 31) * 8, (v >> 5 & 31) * 8, (v & 31) * 8, 255 if fmt == 0 or v & 0x8000 else 0) for v in pixels])
        textures.append((fmt, img))
        off += nbytes
    if off != len(data):
        raise ValueError('%d bytes left over' % (len(data) - off))
    return textures


def over(img, grey=(60, 60, 60)):
    bg = Image.new('RGBA', img.size, grey + (255,))
    bg.alpha_composite(img)
    return bg.convert('RGB')


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__.strip())
        return 2
    out = argv[2] if len(argv) == 3 else '.'
    os.makedirs(out, exist_ok=True)
    textures = load(argv[1])
    cell = max(img.width for _f, img in textures)
    cols = 4
    rows = (len(textures) + cols - 1) // cols
    montage = Image.new('RGB', (cell * cols, cell * rows), (255, 0, 255))
    for i, (fmt, img) in enumerate(textures):
        over(img).save(os.path.join(out, 'tex%02d.png' % i))
        montage.paste(over(img), ((i % cols) * cell, (i // cols) * cell))
        print('%2d  format %d  %dx%d' % (i, fmt, img.width, img.height))
    montage.save(os.path.join(out, 'montage.png'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
