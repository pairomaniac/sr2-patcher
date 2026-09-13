; mix.inc - the volume curve, in one place. Included by mix.asm and, through
; the table asm/build.py derives from it (curve.inc), by music.asm.
;
; The game maps a slider step to (step+1)/10 of the effects' dB range,
; -40..0 as shipped. Everything is in hundredths of a dB.

%define MIX_MIN         -4300           ; the range the effects get instead
%define MIX_MAX         -800            ; step 9; the old 7
%define STREAM_DB       200             ; the streamed music above the effects' curve
%define CD_DB           600             ; the CD music above it; -2 dB at 9

%define MIX_STEP        ((MIX_MAX - MIX_MIN) / 10)
%define MIX_BOTTOM      (MIX_MIN + MIX_STEP)   ; step 0
