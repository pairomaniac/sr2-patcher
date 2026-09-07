#!/usr/bin/env bash
# Run the installed game the way Faugus does, from a terminal, with the log
# kept. Reads ~/.sr2-test, which stays on this machine:
#
#   SR2_GAME     the install folder
#   SR2_PFX      its Wine prefix (Faugus keeps them under ~/Faugus/<game>)
#   SR2_UMU      umu-run, if not on PATH
#   SR2_PROTON   Proton directory; a Proton-CachyOS build is looked for
#                under ~/.steam/root/compatibilitytools.d when unset
#   SR2_WINE     plain wine instead of umu, for a normal prefix
#
#     tools/sr2-run.sh            run; the Wine log goes to logs/sr2.log
#     tools/sr2-run.sh debug      and +seh,+loaddll,+mci (edit for more)
#     tools/sr2-run.sh show       print what it would use and exit
#
# logs/ is in the repository root and gitignored. Under umu, Proton writes
# Wine's output to a file of its own rather than the terminal (PROTON_LOG);
# the terminal only shows umu's lines. The file is steam-<id>.log in
# PROTON_LOG_DIR, which is why that is pointed at logs/.
set -e

CONF=$HOME/.sr2-test
[ -f "$CONF" ] && . "$CONF"
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOGS=$HERE/../logs
LOG=$LOGS/sr2.log

die() { echo "sr2-run: $*" >&2; exit 1; }

GAME=${SR2_GAME:-}
PFX=${SR2_PFX:-}
UMU=${SR2_UMU:-$(command -v umu-run || true)}
PROTON=${SR2_PROTON:-}
WINE=${SR2_WINE:-}
EXE="SEGA RALLY 2.exe"

find_proton() {
    [ -n "$PROTON" ] && { echo "$PROTON"; return; }
    local newest
    newest=$(ls -d "$HOME"/.steam/root/compatibilitytools.d/Proton-CachyOS* 2>/dev/null | sort | tail -n 1)
    [ -n "$newest" ] || die "no Proton found; set SR2_PROTON, or SR2_WINE to use wine"
    echo "$newest"
}

[ -n "$GAME" ] || die "set SR2_GAME in $CONF"
[ -f "$GAME/$EXE" ] || die "no $EXE in $GAME"
[ -n "$PFX" ] || die "set SR2_PFX in $CONF"

mode=${1:-run}
debug=""
[ "$mode" = debug ] && debug="+seh,+loaddll,+mci"

if [ "$mode" = show ]; then
    echo "  game:   $GAME"
    echo "  prefix: $PFX"
    if [ -n "$WINE" ]; then
        echo "  wine:   $WINE"
    else
        echo "  umu:    ${UMU:-not found}"
        echo "  proton: $(find_proton)"
    fi
    exit 0
fi

mkdir -p "$LOGS"
cd "$GAME"
if [ -n "$WINE" ]; then
    WINEPREFIX="$PFX" WINEDEBUG="${debug:-err+all}" \
        "$WINE" "$GAME/$EXE" 2>&1 | tee "$LOG"
else
    [ -n "$UMU" ] || die "umu-run not found; set SR2_UMU or SR2_WINE"
    proton=$(find_proton)
    rm -f "$LOGS"/steam-*.log
    env WINEPREFIX="$PFX" GAMEID=umu-0 PROTONPATH="$proton" \
        PROTON_LOG=1 PROTON_LOG_DIR="$LOGS" ${debug:+WINEDEBUG=$debug} \
        "$UMU" "$GAME/$EXE"
    f=$(ls -t "$LOGS"/steam-*.log 2>/dev/null | head -n 1)
    [ -n "$f" ] && mv "$f" "$LOG"
fi
echo "log in $LOG" >&2
