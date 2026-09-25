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


# What padinput.asm's annex lays out, as the tests expect it: the
# records for a player and the text it saves.
def annex_records(player, table=None):
    """The records the annex generates for a player from a table of
    (key, pad input or None) per action - the defaults when none - in the
    order it lays them out."""
    if table is None:
        keys = (patcher.KEYS_1P, patcher.KEYS_2P)[player]
        table = [(keys[a], patcher.PAD_DEFAULT[a]) for a in range(13)]

    def record(action, source):
        delay, rate = (10, 3) if 2 <= action <= 5 else (0, 0)
        return struct.pack('<13I', action, delay, rate, 0, 10000, source, 0, 0, 0, 0, 0, 0, 0)
    out = []
    for action, (key, pad) in enumerate(table):
        out.append(record(action, key))
        if pad is not None:
            out.append(record(action, patcher.PAD_BASE + player * patcher.PAD_PLAYER + pad))
    for action, key in zip(patcher.FIXED_ACTIONS, patcher.FIXED_KEYS[player]):
        out.append(record(action, patcher.MENUKEY_BASE + key))
    for action, pad in patcher.FIXED_PADS:
        out.append(record(action, patcher.PAD_BASE + player * patcher.PAD_PLAYER + pad))
    return out


def annex_text(tables=None, deadzones=None, network=('0', '0')):
    """The text the annex writes, as it lays it out: for the defaults, or
    for a (key, pad input or None) per action per player; network the
    [Network] section's Staging and Log values as the file had them."""
    deadzones = deadzones or (patcher.PAD_DEADZONE, patcher.PAD_DEADZONE)
    defaults = [[(keys[a], patcher.PAD_DEFAULT[a]) for a in range(13)] for keys in (patcher.KEYS_1P, patcher.KEYS_2P)]
    tables = [t or defaults[i] for i, t in enumerate(tables or (None, None))]
    lines = ['; SEGA RALLY 2 controls']
    for player, table in enumerate(tables):
        for device in ('Controller', 'Keyboard'):
            lines += ['', '[%dP %s]' % (player + 1, device)]
            if device == 'Controller':
                lines.append('Deadzone = %d' % (deadzones[player] // 100))
            for action in patcher.TEXT_ORDER:
                key, pad = table[action]
                name = patcher.KEY_NAMES[key] if device == 'Keyboard' else ('-' if pad is None else patcher.PAD_NAMES[pad])
                lines.append('%s = %s' % (patcher.ACTION_NAMES[action], name.replace(' ', '_')))
    lines += ['', '[Network]', 'Staging = %s' % network[0], 'Log = %s' % network[1]]
    return ''.join(line + '\n' for line in lines).encode('ascii')
