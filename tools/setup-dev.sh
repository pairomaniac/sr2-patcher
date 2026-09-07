#!/bin/sh
# Reports what the development toolchain is missing; installs nothing.
#
#     sh tools/setup-dev.sh
#
# Everything comes from the distribution, no venv: python3-pyflakes lints,
# tkinter is the window. Neither is needed to run the patcher from the
# command line.
set -e
cd "$(dirname "$0")/.."

missing=""
for mod in pyflakes tkinter; do
    python3 -c "import $mod" >/dev/null 2>&1 || missing="$missing $mod"
done

if [ -z "$missing" ]; then
    echo "toolchain complete"
else
    echo "not found:$missing"
    echo "  apt: sudo apt install python3-tk python3-pyflakes"
    echo "  dnf: sudo dnf install python3-tkinter python3-pyflakes"
fi
