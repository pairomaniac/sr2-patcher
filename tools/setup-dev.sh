#!/bin/sh
# Reports what the development toolchain is missing; installs nothing.
#
#     sh tools/setup-dev.sh
#
# Everything comes from the distribution, no venv: python3-pyflakes lints,
# nasm rebuilds asm/ (and the devices check reads its listing),
# python3-unicorn runs the stubs, tkinter is the window, PIL and the URW
# fonts tools/labels.py, tools/assets.py and tools/txrdump.py, those and
# Liberation Sans Narrow, Open Sans and Noto Sans CJK tools/prompts.py,
# a C compiler the
# nettest check,
# mingw net/build.py, xvfb the gui check. None is needed to run the
# patcher from the command line.
set -e

missing=""
for tool in nasm cc i686-w64-mingw32-gcc xvfb-run; do
    command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
done
for mod in pyflakes unicorn tkinter PIL; do
    python3 -c "import $mod" >/dev/null 2>&1 || missing="$missing $mod"
done
if command -v fc-list >/dev/null 2>&1; then
    fc-list | grep -qi "URWGothic-Demi\|URW Gothic" || missing="$missing fonts-urw-base35"
    fc-list | grep -qi "LiberationSansNarrow-Bold" || missing="$missing liberation-sans-narrow"
    fc-list | grep -qi "OpenSans-BoldItalic" || missing="$missing open-sans"
    fc-list | grep -qi "NotoSansCJK" || missing="$missing noto-cjk"
    fc-list | grep -qi "NotoSansMono-Regular" || missing="$missing noto-mono"
fi

if [ -z "$missing" ]; then
    echo "toolchain complete"
else
    echo "not found:$missing"
    echo "  apt: sudo apt install nasm gcc gcc-mingw-w64-i686 xvfb fonts-urw-base35 fonts-liberation-sans-narrow fonts-open-sans fonts-noto-cjk fonts-noto-mono python3-tk python3-pyflakes python3-unicorn python3-pil"
    echo "  dnf: sudo dnf install nasm gcc mingw32-gcc xorg-x11-server-Xvfb urw-base35-fonts liberation-narrow-fonts open-sans-fonts google-noto-sans-cjk-vf-fonts google-noto-sans-mono-fonts python3-tkinter python3-pyflakes python3-unicorn python3-pillow"
fi
