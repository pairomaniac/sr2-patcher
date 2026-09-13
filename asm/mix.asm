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
;                through here: each mapped onto the range in mix.inc, so
;                -40..0 is MIX_MIN..MIX_MAX, 3.5 dB a step, 9 the old 7.
;   +N   stream  the streaming buffer's SetVolume (0x10006940) finishes
;                its value-to-dB mapping through here: the slider step
;                the value was made from, on that same curve plus STREAM_DB.
;
; The CD music in music.asm is on the same curve plus CD_DB, in the same
; units. The numbers are in mix.inc. Nothing here is absolute.

bits 32
%include "mix.inc"

%define OFFSET          STREAM_DB
%define STEP            MIX_STEP
%define BOTTOM          (MIX_BOTTOM + OFFSET)

; old -4000..0 -> MIX_MIN..MIX_MAX: new = MIX_MAX + old * (MIX_MAX - MIX_MIN) / 4000
range:                                  ; +0: replaces mov ecx,[esp+0xc]; mov edx,[esp+0x10]
        mov     ecx, [esp + 0x10]       ; min, under the return address
        mov     edx, [esp + 0x14]       ; max
        push    eax
        push    edx
        mov     eax, ecx
        call    .map
        mov     ecx, eax
        pop     eax                     ; max
        call    .map
        mov     edx, eax
        pop     eax
        ret
.map:   imul    eax, eax, (MIX_MAX - MIX_MIN)
        push    ecx
        mov     ecx, 4000
        cdq
        idiv    ecx
        pop     ecx
        add     eax, MIX_MAX
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
