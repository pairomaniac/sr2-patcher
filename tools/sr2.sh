#!/usr/bin/env bash
# The patcher and the game on one build, with every path taken from
# ~/.sr2-test (template: tools/sr2-test.example, which describes the
# variables). The file stays on this machine.
#
#     tools/sr2.sh BUILD install [LANG]   install from the disc and patch; English unless given
#     tools/sr2.sh BUILD rip              rip the play disc's music into the game folder
#     tools/sr2.sh BUILD patch [KEYS]     patch the installed game; KEYS a comma list to apply only those
#     tools/sr2.sh BUILD restore          put the original files back
#     tools/sr2.sh BUILD run              run under umu the way Faugus does; the Wine log goes to logs/sr2.log
#     tools/sr2.sh BUILD debug [CHANNELS] and WINEDEBUG=+seh,+loaddll,+mci, or the channels given
#     tools/sr2.sh BUILD show             print the paths it would use and exit
#
# BUILD is eu, us, au, jp (Sega's disc) or jp_mk (the DigiCube and
# MediaKite reissue), or all: every build with a game folder in
# ~/.sr2-test, one after another, for everything but run and debug. A
# variable that is empty in ~/.sr2-test shows as N/A in show; an action
# that needs it stops. logs/ is in the repository root and gitignored.
# Under umu, Proton writes Wine's output to a file of its own rather than
# the terminal (PROTON_LOG); the terminal only shows umu's lines. The file
# is steam-<id>.log in PROTON_LOG_DIR, which is why that is pointed at
# logs/.
set -e
set -o pipefail

CONF=$HOME/.sr2-test
[ -f "$CONF" ] && . "$CONF"
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOGS=$HERE/../logs
LOG=$LOGS/sr2.log

die() { echo "sr2.sh: $*" >&2; exit 1; }

if [ "${1:-}" = all ]; then
    shift
    case "${1:-run}" in run|debug) die "all: run and debug take one build" ;; esac
    failed=""
    for b in eu us au jp jp_mk; do
        v=SR2_GAME_${b^^}
        if [ -z "${!v:-}" ]; then echo "== $b: no game folder in $CONF"; continue; fi
        echo "== $b"
        "$0" "$b" "$@" || failed="$failed $b"
    done
    [ -z "$failed" ] || die "failed:$failed"
    exit 0
fi

case "${1:-}" in
    eu|us|au|jp|jp_mk) BUILD=${1^^}; shift ;;
    *) die "usage: tools/sr2.sh eu|us|au|jp|jp_mk|all install|rip|patch|restore|run|debug|show" ;;
esac
game_var=SR2_GAME_$BUILD
disc_var=SR2_DISC_$BUILD
play_var=SR2_PLAY_$BUILD
pfx_var=SR2_PFX_$BUILD
GAME=${!game_var:-}
DISC=${!disc_var:-}
PLAY=${!play_var:-}
PFX=${!pfx_var:-${SR2_PFX:-}}
PATCHER=$HERE/../sr2-patcher.py
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

need() { [ -n "${!1:-}" ] || die "$1 is empty or missing in $CONF"; }

# Empty or unset, in grey when on a terminal.
na() {
    if [ -n "$1" ]; then echo "$1"
    elif [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then printf '\033[90mN/A\033[0m\n'
    else echo N/A; fi
}

mode=${1:-run}
if [ "$mode" = show ]; then
    echo "  build:  $BUILD"
    echo "  disc:   $(na "$DISC")"
    echo "  play:   $(na "$PLAY")"
    echo "  game:   $(na "$GAME")"
    echo "  prefix: $(na "$PFX")"
    if [ -n "$WINE" ]; then
        echo "  wine:   $WINE"
    else
        echo "  umu:    $(na "$UMU")"
        echo "  proton: $(na "$(find_proton 2>/dev/null)")"
    fi
    exit 0
fi

need "$game_var"
case "$mode" in
    install)
        need "$disc_var"
        exec python3 "$PATCHER" --install "$DISC" "$GAME" "${2:-English}" ;;
    rip)
        need "$play_var"
        exec python3 "$PATCHER" --rip "$PLAY" "$GAME" ;;
    patch)   shift; exec python3 "$PATCHER" --patch "$GAME" "$@" ;;
    restore) exec python3 "$PATCHER" --restore "$GAME" ;;
    run|debug) ;;
    *) die "no such action: $mode" ;;
esac

[ -f "$GAME/$EXE" ] || die "no $EXE in $GAME; tools/sr2.sh ${BUILD,,} install first"
[ -n "$PFX" ] || die "set SR2_PFX or $pfx_var in $CONF"
debug=""
[ "$mode" = debug ] && debug="${2:-+seh,+loaddll,+mci}"

mkdir -p "$LOGS"
cd "$GAME"
if [ -n "$WINE" ]; then
    WINEPREFIX="$PFX" WINEDEBUG="${debug:-err+all}" \
        "$WINE" "$GAME/$EXE" 2>&1 | tee "$LOG" || true     # the game's own exit status is not the script's
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
