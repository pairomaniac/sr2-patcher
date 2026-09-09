; mix.asm - one volume curve for everything, in MGSound.dll.
;
; The game's sound manager - in the exe and, as a copy of the same code,
; in every screen DLL - gives each effect a dB range of -40..0 and sets
; its ceiling at (step+1)/10 of it from the slider: 4 dB a step, 0 dB at
; 9. The streamed music went across a range of its own and the CD music
; was linear in amplitude, so a step meant three things. Two routines,
; both in the streaming and buffer code every client ends in:
;
;   +0   range   the buffer's SetRange (0x10004380) loads min and max
;                through here: each becomes 7/8 of itself less 8 dB, so
;                -40..0 is -43..-8 and a step is 3.5 dB, 9 being the old 7.
;   +N   stream  the streaming buffer's SetVolume (0x10006940) finishes
;                its value-to-dB mapping through here: the slider step
;                the value was made from, on that same curve plus OFFSET.
;
; The CD music's table in music.asm is the same curve plus 8 dB, as
; waveOut amplitudes. Nothing here is absolute.

bits 32

%define OFFSET          200             ; hundredths of a dB above the effects' curve
%define STEP            350             ; (max - min) / 10 of the remapped range
%define BOTTOM          (-3950 + OFFSET) ; step 0 on it

range:                                  ; +0: replaces mov ecx,[esp+0xc]; mov edx,[esp+0x10]
        mov     ecx, [esp + 0x10]       ; min, under the return address
        mov     edx, [esp + 0x14]       ; max
        imul    ecx, ecx, 7
        sar     ecx, 3
        sub     ecx, 800
        imul    edx, edx, 7
        sar     edx, 3
        sub     edx, 800
        ret

stream:                                 ; +N: replaces add edx,esi; mov esi,edx; test esi,esi
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
        jmp     .out
.off:   mov     edx, -10000
.out:   mov     esi, edx
        test    esi, esi                ; the site's branch reads these flags
        ret
