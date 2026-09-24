; loadhold.asm - the stage loading screens held for a minimum time.
;
; The loading picture - a course card, or loading.bg - is an object the
; exe creates when the screen opens (0x41a6f0 picks the file by course
; and mode; the object goes to 0x4d6938) and deletes the moment the
; course has loaded, in the state step at 0x4195b0, which then advances.
; On a machine of today the load takes well under a second, and the
; card is gone before it is seen.
;
; Two entries. The first replaces the six-byte store of the new object
; at the create (0x41a7bb, `mov [0x4d6938], ecx`): it makes the store
; and notes the tick. The second replaces the six-byte load of it at the
; step (0x4195be, `mov ecx, [0x4d6938]`): it waits, ten milliseconds at
; a time, until HOLD milliseconds have passed since the note, then makes
; the load. The wait is a plain sleep - the game's loop does not run
; meanwhile, and the picture stays on screen as the last frame presented
; - and it is skipped when no note was taken, the other path that
; deletes the picture (0x419d00, an aborted load) leaving it alone.
;
; Placeholders the patcher fills: the object's global (PICTURE), the
; import slot of GetTickCount (GETTICK), and LoadLibraryA's and
; GetProcAddress's (LOADLIB, GETPROC), for Sleep.

bits 32

%define PICTURE     0xC1C1C1C1          ; placeholders, EXE_MAGICS: the loading picture object's global
%define GETTICK     0xC2C2C2C2          ; GetTickCount's import slot
%define LOADLIB     0xE3E3E3E3          ; LoadLibraryA's and GetProcAddress's
%define GETPROC     0xE4E4E4E4
%define HOLD        3000                ; milliseconds the picture stays, at least
%define NAP         10                  ; and the sleep between looks at the clock

        jmp     near shown              ; +0, the create site's entry
        jmp     near hold               ; +5, the step's

; The six bytes replaced, then the tick.
shown:  mov     [PICTURE], ecx
        push    eax
        push    ecx
        push    edx
        push    ebp
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob
        call    [GETTICK]
        or      eax, 1                  ; never 0, which is "no note"; a millisecond is neither here nor there
        mov     [ebp + when], eax
        pop     ebp
        pop     edx
        pop     ecx
        pop     eax
        ret

; Until HOLD milliseconds since the note, then the six bytes replaced.
hold:   push    eax
        push    edx
        push    ebp
        call    .here
.here:  pop     ebp
        sub     ebp, .here
        cmp     dword [ebp + when], 0
        je      .done
        cmp     dword [ebp + fn_sleep], 0
        jne     .wait
        lea     eax, [ebp + s_kernel32]
        push    eax
        call    [LOADLIB]
        lea     edx, [ebp + s_sleep]
        push    edx
        push    eax
        call    [GETPROC]
        mov     [ebp + fn_sleep], eax
        test    eax, eax
        jz      .done                   ; no Sleep to be had: no hold
.wait:  call    [GETTICK]
        sub     eax, [ebp + when]
        cmp     eax, HOLD
        jae     .done
        push    NAP
        call    [ebp + fn_sleep]
        jmp     .wait
.done:  mov     dword [ebp + when], 0
        pop     ebp
        pop     edx
        pop     eax
        mov     ecx, [PICTURE]
        ret

s_kernel32: db 'kernel32.dll', 0
s_sleep:    db 'Sleep', 0
        align 4
when:       dd 0                        ; the tick the picture was shown at, 0 for none
fn_sleep:   dd 0                        ; Sleep, once found
