; bgmvol.asm - the streamed BGM a few dB down, in MGSound.dll.
;
; The menu loops, the settings-menu music and the replay music are
; streamed, and every path that sets a stream's level - the exe's, and
; the copy of the same client code in each screen DLL - ends in the
; streaming buffer's SetVolume in MGSound.dll (0x10006940): a value on
; the 0..10000 scale becomes min + (max-min) * value / 10000 in
; hundredths of a dB, then goes to the DirectSound buffer. At equal
; settings the streams sit above the effects and the announcer, which
; have a SetVolume of their own. The instructions that finish the
; mapping become a call here, which takes ATTEN off the result, floored
; at DirectSound's -10000. The flags the site tests are those of the
; last instruction here; ret leaves them.

bits 32

%define ATTEN           600             ; hundredths of a dB below the level given

        add     edx, esi                ; the mapping's last step, displaced
        sub     edx, ATTEN
        cmp     edx, -10000
        jge     .in
        mov     edx, -10000
.in:    mov     esi, edx
        test    esi, esi
        ret
