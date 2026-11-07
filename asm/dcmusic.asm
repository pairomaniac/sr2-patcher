; dcmusic.asm - the Dreamcast's extra music, from music\track15.wav onward.
;
; The Dreamcast release has music the PC one dropped: a replay set and an
; ending of its own. This blob plays such tracks where the PC one plays a
; track of the disc's:
;
;   the ten-year ending       track 18 in place of track 11
;   a championship's replay   race 1 track 15, race 2 track 11, race 3
;                             track 16, race 4 track 17, in place of the
;                             course's music
;   any other replay          one of those four at random
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
; game asked for is played, as before. The replays change only when at
; least one of tracks 15 to 17 is there: without any, the replays keep
; the course's music, track 11 included. The music patch plays the
; files; on the disc there is no track past 14.
;
; Entries, each in place of a `call` of the bank's play, with ecx the
; bank and the slot at [esp+4], leaving through the play itself:
;
;   +0   the ten-year ending's play of slot 9
;   +5   a championship replay's first race (race index 0)
;   +10  its later races, a call shared with a slot-7 branch for race
;        index 0, which is left alone
;   +15  the other modes' replays, a call shared with the arcade ending
;        and mode 10's scene, which are left alone
;
; The race block ([STATE]): +0x38 the mode (1 arcade, 4 ten-year; 2, 3,
; 5 and 6 the single-race modes), +0x44 the state bits (4 a replay), +0x64
; the race of the championship, from 0.
;
; Placeholders the patcher fills: the play (PLAY), the pointer to the race
; block (STATE), and the import slots of LoadLibraryA, GetProcAddress and
; GetModuleFileNameA.

bits 32

%define PLAY        0xB3B3B3B3          ; placeholders, EXE_MAGICS: the sound bank's play
%define STATE       0xB4B4B4B4          ; RACEBLOCK: the pointer to the race block
%define LOADLIB     0xE3E3E3E3          ; LoadLibraryA's import slot
%define GETPROC     0xE4E4E4E4          ; GetProcAddress's
%define GETMODFN    0xF9F9F9F9          ; GetModuleFileNameA's

%define EXTRA       14                  ; the slot of the CD track no scene plays
%define RECORD      0x28                ; a bank's record of a slot; +0 the CD track less one
%define ELEVEN      9                   ; the slot of track 11
%define FIRST       15                  ; the extra tracks
%define LAST        18
%define ENDING      18                  ; the ten-year ending's
%define REPLAYS     7                   ; found's bits of tracks 15, 16 and 17
%define MODE        0x38                ; the race block's
%define BITS        0x44
%define REPLAY      4                   ;   a replay
%define RACE        0x64
%define PATHLEN     272
%define DIRECTORY   0x10                ; FILE_ATTRIBUTE_DIRECTORY
%define DIGITS      11                  ; the track's digits in name, after music\track

%if LAST > 99
%error the file names have two digits
%endif

        jmp     near ending             ; +0, the ten-year ending's play
        jmp     near first              ; +5, a championship replay's race 1
        jmp     near later              ; +10, its races 2 to 4
        jmp     near single             ; +15, the other modes' replays

; The ending's track 11 (slot 9), or track 18 in slot 14 when its file
; is there. ecx, the slot and the return are the play's.
ending: call    tracks
        mov     edx, ENDING
        jmp     extra

first:  xor     eax, eax
        jmp     replay

later:  mov     eax, [STATE]
        mov     eax, [eax + RACE]
        test    eax, eax
        jz      play                    ; race index 0 here is the slot-7 branch
        and     eax, 3                  ; the ten-year championship's races past 4 go round
        jmp     replay

; A replay in a single-race mode: one of the four, at random, among those
; there are files for (track 11 always).
single: mov     eax, [STATE]
        test    byte [eax + BITS], REPLAY
        jz      play
        mov     eax, [eax + MODE]
        cmp     eax, 2
        je      .mode
        cmp     eax, 3
        je      .mode
        cmp     eax, 5
        je      .mode
        cmp     eax, 6
        jne     play
.mode:  call    tracks
        test    al, REPLAYS
        jz      play
        push    ecx
        push    ebx
        mov     ebx, eax                ; the replay's choices: bit n, choice n is there
        and     eax, 1                  ;   0, track 15
        and     ebx, 6                  ;   2 and 3, tracks 16 and 17
        shl     ebx, 1
        or      ebx, eax
        or      ebx, 2                  ;   1, track 11
        xor     ecx, ecx                ; how many
        mov     edx, ebx
.count: shr     edx, 1
        adc     ecx, 0
        test    edx, edx
        jnz     .count
        rdtsc
        xor     edx, edx
        div     ecx                     ; edx: which of them
        mov     eax, -1
.find:  inc     eax
        bt      ebx, eax
        jnc     .find
        dec     edx
        jns     .find
        pop     ebx
        pop     ecx
        ; fall into replay

; Choice eax of the replay set, in the Dreamcast's order: 0 track 15,
; 1 track 11, 2 track 16, 3 track 17. ecx, the slot and the return are
; the play's.
replay: mov     edx, eax
        call    tracks
        test    al, REPLAYS
        jz      play                    ; no replay set: the course's music
        cmp     edx, 1
        jne     .extra
        mov     dword [esp + 4], ELEVEN
        jmp     play
.extra: jb      .one
        add     edx, FIRST - 1          ; 2 and 3: tracks 16 and 17
        jmp     extra
.one:   mov     edx, FIRST
        ; fall into extra

; Track edx in slot 14 when its file is there (eax the found bits), else
; the slot asked for.
extra:  sub     edx, FIRST
        bt      eax, edx
        jnc     play
        add     edx, FIRST - 1
        mov     eax, [ecx]              ; the bank's records
        mov     [eax + EXTRA * RECORD], edx
        mov     dword [esp + 4], EXTRA
play:   mov     eax, PLAY
        jmp     eax

; eax = the tracks FIRST to LAST whose files are there, bit n track
; FIRST + n. Keeps the other registers.
tracks: push    ebp
        push    ecx
        push    edx
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob
        cmp     byte [ebp + looked], 0
        jne     .known
        call    look
.known: mov     eax, [ebp + found]
        pop     edx
        pop     ecx
        pop     ebp
        ret

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
