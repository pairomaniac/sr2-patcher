#!/usr/bin/env python3
"""The dgVoodoo 2 add-on against a made-up release, no network.

    python3 tools/dgvoodootest.py

_fetch is replaced by one that serves a release listing and an archive
laid out as dgVoodoo's are; install_dgvoodoo must take the three files
from it into a folder, edit the config's [DirectX] section as
DGVOODOO_SETTINGS says and nothing else, stamp the release, leave an
existing config alone, skip the download when the stamp and files are
there, and remove_dgvoodoo must take the DLLs back out and not the
config. parse_keys must give the add-on only where it is the default,
or when named.
"""
import io
import os
import shutil
import tempfile
import zipfile

from uctest import patcher

CONF = ('Version = 0x287\r\n\r\n[General]\r\n\r\nFullScreenMode                       = true\r\n\r\n'
        '[Glide]\r\n\r\nForceVerticalSync                   = false\r\n\r\n'
        '[DirectX]\r\n\r\n; a comment with FastVideoMemoryAccess = false in it\r\n'
        'VideoCard                           = internal3D\r\n'
        'DisableAltEnterToToggleScreenMode   = true\r\n'
        'dgVoodooWatermark                   = true\r\n'
        'ForceVerticalSync                   = false\r\n'
        'FastVideoMemoryAccess               = false\r\n\r\n'
        '[DirectXExt]\r\n\r\nFastVideoMemoryAccess               = false\r\n')
WANT = ('Version = 0x287\r\n\r\n[General]\r\n\r\nFullScreenMode                       = true\r\n\r\n'
        '[Glide]\r\n\r\nForceVerticalSync                   = false\r\n\r\n'
        '[DirectX]\r\n\r\n; a comment with FastVideoMemoryAccess = false in it\r\n'
        'VideoCard                           = internal3D\r\n'
        'DisableAltEnterToToggleScreenMode   = false\r\n'
        'dgVoodooWatermark                   = false\r\n'
        'ForceVerticalSync                   = true\r\n'
        'FastVideoMemoryAccess               = true\r\n\r\n'
        '[DirectXExt]\r\n\r\nFastVideoMemoryAccess               = false\r\n')


def archive():
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, 'w') as zf:
        zf.writestr('dgVoodoo.conf', CONF)
        zf.writestr('dgVoodooCpl.exe', b'cpl')
        zf.writestr('MS/x86/DDraw.dll', b'ddraw32')
        zf.writestr('MS/x86/D3DImm.dll', b'd3dimm32')
        zf.writestr('MS/x64/DDraw.dll', b'ddraw64')
        zf.writestr('MS/x64/D3DImm.dll', b'd3dimm64')
        zf.writestr('3Dfx/x86/Glide2x.dll', b'glide')
    return blob.getvalue()


def read(path, mode='rb'):
    with open(path, mode) as fh:
        return fh.read()


def main():
    fetched = []

    def fetch(url, limit, accept=None, progress=None):
        fetched.append(url)
        if url == patcher.DGVOODOO_RELEASE:
            return (b'{"tag_name": "v2.87.5", "html_url": "x", "assets": ['
                    b'{"name": "dgVoodoo2_87_5_dbg.zip", "browser_download_url": "dbg"},'
                    b'{"name": "dgVoodoo2_87_5.zip", "browser_download_url": "zip"},'
                    b'{"name": "dgVoodoo2_87_5_dev64.zip", "browser_download_url": "dev"}]}')
        if url == 'zip':
            return archive()
        raise SystemExit('dgvoodootest: fetched %s' % url)
    patcher._fetch = fetch

    dest = tempfile.mkdtemp()
    try:
        os.mkdir(os.path.join(dest, 'MUSASHI'))
        log = []
        tag = patcher.install_dgvoodoo(dest, log.append)
        if tag != 'v2.87.5' or fetched != [patcher.DGVOODOO_RELEASE, 'zip']:
            raise SystemExit('dgvoodootest: the install fetched %r and gave %r' % (fetched, tag))
        files = {name: read(os.path.join(dest, *name.split('\\')))
                 for _m, name in patcher.DGVOODOO_FILES}
        if files['MUSASHI\\ddraw.dll'] != b'ddraw32' or files['D3DImm.dll'] != b'd3dimm32':
            raise SystemExit('dgvoodootest: the wrong DLLs: %r' % (files,))
        if files['MUSASHI\\dgVoodoo.conf'] != WANT.encode():
            raise SystemExit('dgvoodootest: the config came out\n%s' % files['MUSASHI\\dgVoodoo.conf'].decode())
        if patcher.dgvoodoo_status(dest) != 'v2.87.5':
            raise SystemExit('dgvoodootest: the stamp reads %r' % (patcher.dgvoodoo_status(dest),))
        # again: nothing fetched, the log says so
        del fetched[:]
        if patcher.install_dgvoodoo(dest, log.append) != 'v2.87.5' or fetched:
            raise SystemExit('dgvoodootest: the second install fetched %r' % (fetched,))
        # the config kept as someone left it when the files are put back
        conf = os.path.join(dest, 'MUSASHI', 'dgVoodoo.conf')
        with open(conf, 'w') as fh:
            fh.write('mine')
        if not patcher.remove_dgvoodoo(dest, log.append) or patcher.dgvoodoo_status(dest):
            raise SystemExit('dgvoodootest: the removal did not take')
        if os.path.exists(os.path.join(dest, 'D3DImm.dll')) or os.path.exists(os.path.join(dest, 'MUSASHI', 'ddraw.dll')):
            raise SystemExit('dgvoodootest: a DLL was left behind')
        if read(conf, 'r') != 'mine':
            raise SystemExit('dgvoodootest: the removal took the config')
        if patcher.remove_dgvoodoo(dest, log.append):
            raise SystemExit('dgvoodootest: removed what was not there')
        patcher.install_dgvoodoo(dest, log.append)
        if read(conf, 'r') != 'mine':
            raise SystemExit('dgvoodootest: the install rewrote the config')
        # a stamp without the files is no install
        os.remove(os.path.join(dest, 'D3DImm.dll'))
        if patcher.dgvoodoo_status(dest):
            raise SystemExit('dgvoodootest: a stamp alone read as installed')
        # Restore's removal: everything, the config too, stamped or not
        if not patcher.remove_dgvoodoo(dest, log.append, everything=True) or os.path.exists(conf):
            raise SystemExit('dgvoodootest: the full removal left the config')
        if patcher.remove_dgvoodoo(dest, log.append, everything=True):
            raise SystemExit('dgvoodootest: the full removal found something twice')
        with open(os.path.join(dest, 'D3DImm.dll'), 'wb') as fh:
            fh.write(b'hand placed')
        if not patcher.remove_dgvoodoo(dest, log.append, everything=True) or os.path.exists(os.path.join(dest, 'D3DImm.dll')):
            raise SystemExit('dgvoodootest: the full removal left an unstamped DLL')
        # the two halves apart, as patch() uses them: the archive fetched first, unpacked after,
        # and a fetch that fails writes nothing
        del fetched[:]
        got = patcher.fetch_dgvoodoo(dest, log.append)
        if not got or got[0] != 'v2.87.5' or fetched != [patcher.DGVOODOO_RELEASE, 'zip']:
            raise SystemExit('dgvoodootest: the fetch gave %r after %r' % (got, fetched))
        if os.path.exists(os.path.join(dest, 'D3DImm.dll')):
            raise SystemExit('dgvoodootest: the fetch wrote a DLL')
        del fetched[:]
        if patcher.install_dgvoodoo(dest, log.append, fetched=got) != 'v2.87.5' or fetched:
            raise SystemExit('dgvoodootest: the unpack fetched %r' % (fetched,))
        if not os.path.exists(os.path.join(dest, 'D3DImm.dll')):
            raise SystemExit('dgvoodootest: the unpack wrote no DLL')
        patcher.remove_dgvoodoo(dest, log.append, everything=True)
        patcher._fetch = lambda *a, **k: (_ for _ in ()).throw(OSError('no network'))
        try:
            patcher.fetch_dgvoodoo(dest, log.append)
        except OSError:
            pass
        else:
            raise SystemExit('dgvoodootest: a failed fetch did not raise')
        if os.path.exists(os.path.join(dest, 'D3DImm.dll')):
            raise SystemExit('dgvoodootest: a failed fetch left a DLL')
        patcher._fetch = fetch
    finally:
        shutil.rmtree(dest)

    native = patcher.windows_native
    try:
        for default in (True, False):               # the default follows the system: on under Windows itself, off elsewhere
            patcher.windows_native = lambda: default
            if ('dgvoodoo' in patcher.default_keys()) != default:
                raise SystemExit('dgvoodootest: the default does not follow the system')
            if ('dgvoodoo' in patcher.parse_keys([])) != default or ('dgvoodoo' in patcher.parse_keys(['nodisc'])) != default:
                raise SystemExit('dgvoodootest: parse_keys does not follow the default')
    finally:
        patcher.windows_native = native
    if 'dgvoodoo' not in patcher.parse_keys(['dgvoodoo']) or 'dgvoodoo' not in patcher.parse_keys(['nodisc,dgvoodoo']):
        raise SystemExit('dgvoodootest: parse_keys drops the add-on named')
    if 'dgvoodoo' in patcher.parse_keys(['-dgvoodoo']) or 'nodisc' not in patcher.parse_keys(['-dgvoodoo']):
        raise SystemExit('dgvoodootest: -dgvoodoo does not take it out alone')
    print('dgvoodootest: the add-on\'s install, config edit, stamp and removal, and its keys OK')


if __name__ == '__main__':
    main()
