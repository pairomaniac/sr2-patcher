; bgmvol.asm - the streamed music on the effects' volume curve, in MGSound.dll.
;
; Every path that sets a stream's level - the exe's, and each screen
; DLL's copy of the same client code - ends in the streaming buffer's
; SetVolume (0x10006940), with the slider step times 1111 as a 0..10000
; value, which it maps across the stream's own dB range. The effects
; and the announcer follow -36 dB + 4 dB a step; the streams did not,
; so the sliders meant different things. The mapping's last step
; becomes a call here, which puts the step on the effects' curve plus
; OFFSET, capped at 0 dB, 0 being off. The site tests the flags of the last instruction
; here; ret keeps them. ebx is the value, kept; ecx is kept too.

bits 32

%define OFFSET          400             ; hundredths of a dB above the effects' curve
%define STEP            400
%define BOTTOM          (-3600 + OFFSET)

        push    ecx
        lea     eax, [ebx + 555]        ; the step the value was made from, rounded
        xor     edx, edx
        mov     ecx, 1111
        div     ecx
        pop     ecx
        cmp     eax, 9
        jbe     .step
        mov     eax, 9
.step:
        test    eax, eax
        jz      .off
        imul    edx, eax, STEP
        add     edx, BOTTOM
        js      .out
        xor     edx, edx                ; capped at 0 dB
        jmp     .out
.off:   mov     edx, -10000
.out:   mov     esi, edx
        test    esi, esi
        ret
