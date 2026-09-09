; voltrace.asm - a diagnostic: every volume call the exe makes, reported.
;
; Five entry points in the sound code get a jump here at their first
; instruction; each thunk reports the call through OutputDebugStringA as
; "sr2 vN this a1 a2 a3" in hex, runs the instructions the jump
; displaced, and jumps back. WINEDEBUG=+debugstr shows the lines. Not a
; patch for players; it is applied by hand while looking for where a
; level is set.
;
;   v1  0x46f2e0  the buffer volume wrapper (sound, min, value)
;   v2  0x470630  the stream volume (value)
;   v3  0x46e160  the CD wrapper's SetVolume (pct, flags)
;   v4  0x46f370  the second per-sound call after a volume (sound, 100)
;   v5  0x46ece0  play with parameters (sound, mode, param)
;
; IAT_LOADLIB and IAT_GETPROC are the usual placeholders. Resolved on
; every call; this is a trace.

bits 32

%define IAT_LOADLIB     0xE3E3E3E3
%define IAT_GETPROC     0xE4E4E4E4
%define BUF             80

; Each thunk ends in `jmp [abs]` through a placeholder 0xE7E7E7En: the
; patcher writes the address of a dword in the section holding the
; site's VA + the displaced length.

        jmp     near t1                 ; +0
        jmp     near t2                 ; +5
        jmp     near t3                 ; +10
        jmp     near t4                 ; +15
        jmp     near t5                 ; +20

; [esp] = ret to thunk, [esp+4] = N, [esp+8] = the site's return address,
; [esp+12..] = its arguments; ecx = this.
report:
        pushad
        sub     esp, BUF
        mov     edi, esp
        call    .here
.here:  pop     ebx
        sub     ebx, .here
        lea     esi, [ebx + s_pre]
        call    scat
        mov     eax, [esp + BUF + 32 + 4]
        add     al, '0'
        stosb
        mov     al, ' '
        stosb
        mov     eax, [esp + BUF + 24]            ; ecx as pushad saved it
        call    hex8
        mov     eax, [esp + BUF + 32 + 12]
        call    hex8
        mov     eax, [esp + BUF + 32 + 16]
        call    hex8
        mov     eax, [esp + BUF + 32 + 20]
        call    hex8
        mov     byte [edi], 0
        lea     eax, [ebx + s_k32]
        push    eax
        call    dword [IAT_LOADLIB]
        lea     ecx, [ebx + s_ods]
        push    ecx
        push    eax
        call    dword [IAT_GETPROC]
        test    eax, eax
        jz      .done
        push    esp
        call    eax
.done:
        add     esp, BUF
        popad
        ret     4                       ; drops N

hex8:                                   ; eax -> 8 hex digits at edi, then a space
        mov     ecx, 8
.d:     rol     eax, 4
        mov     dl, al
        and     dl, 15
        add     dl, '0'
        cmp     dl, '9'
        jbe     .w
        add     dl, 7
.w:     mov     [edi], dl
        inc     edi
        loop    .d
        mov     byte [edi], ' '
        inc     edi
        ret

scat:   lodsb
        stosb
        test    al, al
        jnz     scat
        dec     edi
        ret

t1:     push    1
        call    report
        push    ebp
        mov     ebp, esp
        sub     esp, 0xc
        jmp     dword [0xE7E7E7E1]
t2:     push    2
        call    report
        push    ebp
        mov     ebp, esp
        sub     esp, 0x80
        jmp     dword [0xE7E7E7E2]
t3:     push    3
        call    report
        push    esi
        mov     esi, [ecx]
        test    esi, esi
        jmp     dword [0xE7E7E7E3]
t4:     push    4
        call    report
        push    ebp
        mov     ebp, esp
        sub     esp, 0x88
        jmp     dword [0xE7E7E7E4]
t5:     push    5
        call    report
        push    ebp
        mov     ebp, esp
        sub     esp, 0xc
        jmp     dword [0xE7E7E7E5]

s_pre:  db 'sr2 v', 0
s_k32:  db 'kernel32.dll', 0
s_ods:  db 'OutputDebugStringA', 0
