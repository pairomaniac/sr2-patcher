; bgmvol.asm - the streamed music a few dB down, in MGSound.dll.
;
; Every path that sets a stream's level - the exe's, and each screen
; DLL's copy of the same client code - ends in the streaming buffer's
; SetVolume (0x10006940): a 0..10000 value becomes min + (max-min) *
; value / 10000 in hundredths of a dB, then goes to the DirectSound
; buffer. Streams get a narrower, higher range than the effects, so the
; same slider value lands them louder. The mapping's last step becomes
; a call here, which takes ATTEN off the result, floored at -10000. The
; site tests the flags of the last instruction here; ret keeps them.

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
