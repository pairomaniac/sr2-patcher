"""What the Unicorn tests share: the patcher module, the Unicorn import
that exits 77 when the package is missing (so tools/check.py can skip the
check), the build a game file belongs to, and a PE image mapped into an
emulator the way the loader maps it."""
import hashlib
import importlib.util
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('patcher', os.path.join(HERE, '..', 'sr2-patcher.py'))
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


SKIPPED = 77            # the exit code tools/check.py reads as a skip, not a pass


def stock(game, name):
    """The bytes of the game file `name` (as BUILDS spells it) from its
    .bak when it has been patched, so a test runs on the original."""
    path = os.path.join(game, *name.split('\\'))
    if os.path.isfile(path + '.bak'):
        path += '.bak'
    with open(path, 'rb') as fh:
        return bytearray(fh.read())


def unicorn(name):
    """The unicorn package, or exit SKIPPED with a note naming the test."""
    try:
        import unicorn
    except ImportError:
        print('%s: skipped, python3-unicorn not installed' % name)
        sys.exit(SKIPPED)
    return unicorn


def build_of(raw, name):
    """The build whose fingerprint of the game file `name` (as BUILDS
    spells it) the bytes match, or None."""
    digest = hashlib.md5(raw).hexdigest()
    return next((b for b, row in patcher.BUILDS.items() if row['files'][name][1] == digest), None)


def map_image(mu, image, base):
    """Maps a PE image at base: the headers, each section at its RVA,
    and the relocations applied as the loader applies them, which is what
    catches a relocation entry left on a byte that is no longer absolute.
    Returns the RVA of the patcher's annex, or None when there is none."""
    pe_off = struct.unpack_from('<I', image, 0x3c)[0]
    nsec = struct.unpack_from('<H', image, pe_off + 6)[0]
    opt = pe_off + 24
    size = struct.unpack_from('<I', image, opt + 56)[0]
    table = opt + struct.unpack_from('<H', image, pe_off + 20)[0]
    mu.mem_map(base, (size + 0xfff) & ~0xfff)
    mu.mem_write(base, bytes(image[:0x1000]))
    annex = None
    for i in range(nsec):
        name, _vsize, va, rsize, roff = struct.unpack_from('<8sIIII', image, table + i * 40)
        mu.mem_write(base + va, bytes(image[roff:roff + rsize]))
        if name.rstrip(b'\0') == patcher.ANNEX:
            annex = va
    delta = base - struct.unpack_from('<I', image, opt + 28)[0]
    rel_rva, rel_size = struct.unpack_from('<II', image, opt + 136)
    if delta and rel_size:
        off = patcher._rva_to_off(image, rel_rva)
        end = off + rel_size
        while off + 8 <= end:
            page, bsize = struct.unpack_from('<II', image, off)
            if not bsize:
                break
            for i in range(8, bsize, 2):
                e = struct.unpack_from('<H', image, off + i)[0]
                if e >> 12 == 3:
                    a = base + page + (e & 0xfff)
                    v = struct.unpack('<I', mu.mem_read(a, 4))[0]
                    mu.mem_write(a, struct.pack('<I', (v + delta) & 0xffffffff))
            off += bsize
    return annex
