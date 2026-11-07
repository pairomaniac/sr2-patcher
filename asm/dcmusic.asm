; dcmusic.asm - the Dreamcast's extra music, from music\track15.wav onward.
;
; The Dreamcast release has music the PC one dropped: a replay set and an
; ending of its own. This blob plays such tracks where the PC one plays a
; track of the disc's; for now the ten-year championship's ending, which
; plays track 11 and plays track 18 when there is one.
;
; The tracks go through the exe's own music. Its sound bank (the object
; at [0x50b134] in the European build) plays a scene by its slot
; (0x473d80, thiscall: slot, loop, two more): the slot list (0x5a2514)
; names a descriptor, and a CD descriptor holds its track less one,
; which the CD object hands to MGAudio. The bank copies each slot's
; descriptor into a record of its own, 0x28 bytes a slot, when it is
; built. Slot 14's descriptor (id 0x0d) is a CD track no scene plays:
; track 15, which the PC's disc does not have. So an extra track is
; played by writing its number less one into slot 14's record and
; playing slot 14. The bank's bookkeeping - what is playing, the fades,
; the stop at the next scene - is the bank's own, and the CD object
; starts any track that is not the one already going.
;
; A track plays only when its file is there: music\trackNN.wav beside
; the exe, looked for once, at the first call. Without it the slot the
; game asked for is played, as before. The music patch plays the files;
; on the disc there is no track past 14.
;
; One entry, at +0: it replaces the `call` of the ending's play, with
; ecx the bank and the slot at [esp+4], and leaves through the play
; itself.
;
; Placeholders the patcher fills: the play (PLAY), and the import slots
; of LoadLibraryA, GetProcAddress and GetModuleFileNameA.

bits 32

%define PLAY        0xB3B3B3B3          ; placeholders, EXE_MAGICS: the sound bank's play
%define LOADLIB     0xE3E3E3E3          ; LoadLibraryA's import slot
%define GETPROC     0xE4E4E4E4          ; GetProcAddress's
%define GETMODFN    0xF9F9F9F9          ; GetModuleFileNameA's

%define EXTRA       14                  ; the slot of the CD track no scene plays
%define RECORD      0x28                ; a bank's record of a slot; +0 the CD track less one
%define FIRST       15                  ; the extra tracks
%define LAST        18
%define ENDING      18                  ; the ten-year ending's
%define PATHLEN     272
%define DIRECTORY   0x10                ; FILE_ATTRIBUTE_DIRECTORY
%define DIGITS      11                  ; the track's digits in name, after music\track

%if LAST > 19
%error the file names are written as 1 and one digit
%endif

        jmp     near ending             ; +0, the ten-year ending's play

; The ending's track 11 (slot 9), or track 18 in slot 14 when its file
; is there. ecx, the slot and the return are the play's.
ending: push    ecx
        push    ENDING
        call    present
        pop     ecx
        test    eax, eax
        jz      .play
        mov     eax, [ecx]              ; the bank's records
        mov     dword [eax + EXTRA * RECORD], ENDING - 1
        mov     dword [esp + 4], EXTRA
.play:  mov     eax, PLAY
        jmp     eax

; 1 if music\trackNN.wav is there for the track pushed, else 0. stdcall;
; keeps ebx, esi, edi and ebp.
present:
        push    ebp
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob
        cmp     byte [ebp + looked], 0
        jne     .known
        call    look
.known: mov     ecx, [esp + 8]
        sub     ecx, FIRST
        mov     eax, [ebp + found]
        shr     eax, cl
        and     eax, 1
        pop     ebp
        ret     4

; The tracks FIRST to LAST whose files are there, as bits of found. ebp
; is the blob. Asked once: a file put in place later is seen at the
; next start.
look:   push    ebx
        push    esi
        push    edi
        mov     byte [ebp + looked], 1
        lea     eax, [ebp + kernel32]
        push    eax
        call    [LOADLIB]
        test    eax, eax
        jz      .out
        lea     ecx, [ebp + getattr]
        push    ecx
        push    eax
        call    [GETPROC]
        test    eax, eax
        jz      .out
        mov     ebx, eax                ; GetFileAttributesA
        push    PATHLEN - 24            ; room after it for the file's name
        lea     edi, [ebp + path]
        push    edi
        push    0
        call    [GETMODFN]
        test    eax, eax
        jz      .out
        lea     esi, [edi + eax]
.back:  cmp     esi, edi                ; back to the last backslash
        je      .out
        dec     esi
        cmp     byte [esi], '\'
        jne     .back
        inc     esi
        mov     edx, esi
        lea     ecx, [ebp + name]
.copy:  mov     al, [ecx]               ; the exe's name becomes music\track15.wav
        mov     [edx], al
        inc     ecx
        inc     edx
        test    al, al
        jnz     .copy
        add     esi, DIGITS             ; the two digits
        mov     edi, FIRST
.each:  mov     eax, edi
        aam                             ; ah the tens, al the units
        add     ax, '00'
        mov     [esi], ah
        mov     [esi + 1], al
        lea     eax, [ebp + path]
        push    eax
        call    ebx
        cmp     eax, -1
        je      .next
        test    al, DIRECTORY
        jnz     .next
        lea     ecx, [edi - FIRST]
        mov     eax, 1
        shl     eax, cl
        or      [ebp + found], eax
.next:  inc     edi
        cmp     edi, LAST
        jbe     .each
.out:   pop     edi
        pop     esi
        pop     ebx
        ret

looked:     db 0                        ; look has run
            align 4
found:      dd 0                        ; bit n: track FIRST + n is there
kernel32:   db 'kernel32.dll', 0
getattr:    db 'GetFileAttributesA', 0
name:       db 'music\track15.wav', 0
path:       times PATHLEN db 0
