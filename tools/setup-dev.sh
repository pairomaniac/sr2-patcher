#!/bin/sh
# Reports what the development toolchain is missing; installs nothing.
#
#     sh tools/setup-dev.sh
#
# Everything comes from the distribution, no venv: python3-pyflakes lints,
# nasm rebuilds asm/, python3-unicorn runs the music hook check, tkinter is
# the window. None is needed to run the patcher from the command line.
set -e
cd "$(dirname "$0")/.."

missing=""
command -v nasm >/dev/null 2>&1 || missing="$missing nasm"
for mod in pyflakes unicorn tkinter; do
    python3 -c "import $mod" >/dev/null 2>&1 || missing="$missing $mod"
done

if [ -z "$missing" ]; then
    echo "toolchain complete"
else
    echo "not found:$missing"
    echo "  apt: sudo apt install nasm python3-tk python3-pyflakes python3-unicorn"
    echo "  dnf: sudo dnf install nasm python3-tkinter python3-pyflakes python3-unicorn"
fi
