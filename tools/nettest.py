#!/usr/bin/env python3
"""Build tools/nettest.c against net/ with the system C compiler and run it.

    python3 tools/nettest.py

Skips itself, passing, when no compiler is found.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    if not cc:
        print('nettest: skipped (no C compiler)')
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, 'nettest')
        cmd = [cc, '-std=gnu99', '-O1', '-Wall', '-Wextra', '-DSR2_TEST', '-I', os.path.join(ROOT, 'net'),
               '-o', exe, os.path.join(HERE, 'nettest.c'), os.path.join(ROOT, 'net', 'sr2net.c'), '-lpthread']
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode:
            sys.stderr.write(proc.stderr)
            return 1
        if proc.stderr.strip():
            sys.stderr.write(proc.stderr)
        env = dict(os.environ)
        server = None
        port = 40000 + os.getpid() % 20000
        try:
            server = subprocess.Popen([sys.executable, os.path.join(ROOT, 'net', 'directory.py'), str(port)],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            time.sleep(0.5)
            if server.poll() is None:
                env['SR2_DIR_PORT'] = str(port)
            else:
                print('the directory did not start on port %d:\n%s' % (port, server.communicate()[0]))
                return 1
        except OSError as exc:
            print('the directory could not be started: %s' % exc)
            return 1
        try:
            proc = subprocess.run([exe], capture_output=True, text=True, timeout=120, env=env)
        finally:
            server.terminate()
            try:
                out = server.communicate(timeout=5)[0]
            except subprocess.TimeoutExpired:
                server.kill()
                out = server.communicate()[0]
            for line in out.splitlines():
                print('      [directory] ' + line)
        lines = [l for l in proc.stdout.splitlines() if not l.startswith('      [')]
        print('\n'.join(lines))
        return 0 if proc.returncode == 0 and lines and lines[-1] == 'OK' else 1


if __name__ == '__main__':
    sys.exit(main())
