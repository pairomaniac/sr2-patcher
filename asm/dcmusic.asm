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
;   a course's music          OPTION's seven choices and four more, the
;                             replay set: 7 track 15, 8 track 11, 9 track
;                             16, 10 track 17
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
; the course's music, track 11 included. A course choice of 7 to 10
; whose file is not there plays track 11. The music patch plays the
; files; on the disc there is no track past 14.
;
; A course's choice is read as slot = choice + 1 wherever the game plays,
; fades or restarts the course's music; for 7 to 10 that slot (8 to 11)
; is another scene's, so every such call comes here and gets slot 14 (or
; 9 for track 11) instead.
;
; Exe entries, each in place of a `call` of the bank, with ecx the bank
; and the slot at [esp+4], leaving through the routine called:
;
;   +0   the ten-year ending's play of slot 9
;   +5   a championship replay's first race (race index 0)
;   +10  its later races, a call shared with a slot-7 branch for race
;        index 0, which is left alone
;   +15  the other modes' scene music: their replays, and in modes 5 and
;        6 the race; a call shared with the arcade ending and mode 10's
;        scene, which are left alone
;   +20  the race's play of the course's music
;   +25  a fade of it (FADE)
;   +30  its restart (RESTART)
;   +35  the ten-year ending's DRIVER line: in place of the load and
;        compare of its step count with 780 (8 bytes), not a call; the
;        line is held, while track 18 plays, until GetTickCount reaches
;        the music's start plus its length less the 3 s the screen
;        takes to fade (the length from the file's size)
;
; The race block ([STATE]): +0x38 the mode (1 arcade, 4 ten-year; 2, 3,
; 5 and 6 the single-race modes), +0x44 the state bits (4 a replay), +0x64
; the race of the championship, from 0.
;
; Placeholders the patcher fills: the bank's play (PLAY), fade and restart,
; the pointer to the race block (STATE), and the import slots of
; LoadLibraryA, GetProcAddress and GetModuleFileNameA.
;
; With OPTIONS defined, the same for Options.dll's BGM page and its sound
; page's BGM TEST, the extra tracks there after the stock 13. The DLL has a
; copy of the bank of its own (the object at [0x100b8bd8], its play
; 0x1000b610) and another slot list: slot 12 is track 11, slot 13 the CD
; track no scene plays. Entries:
;
;   +0   the page's init, in place of `mov ebx, 7`: the seven rows' count
;        of choices, 11 when one of tracks 15 to 17 is there
;   +5   the rows' name draw, in place of the call of the text routine:
;        a choice of 7 to 10 drawn with its own name
;   +10  the preview, in place of the call of the play: choices 7 to 10
;        as in the exe
;   +15  the sound page's init, in place of `mov dword [esi+0x68], 13`:
;        BGM TEST's count of tracks, 13 and one more for each of tracks
;        15 to 18 there is a file for
;   +20  BGM TEST's name draw, in place of the call of the text routine:
;        past the 13th, the extra track's name
;   +25  BGM TEST's play, in place of the call of the play: past the
;        13th, the extra track in slot 13
;
; There the placeholders are RVAs: the blob's own (SELFRVA), the text
; routine's, the play's and the three import slots'. A saved choice of 7
; to 10 with none of the files there still draws, previews and plays (as
; track 11); left or right brings it back into the seven.

bits 32

%ifdef OPTIONS
%define SELFRVA     0xE7E7E7E7          ; placeholders, DCOPTIONS_MAGICS: this blob's RVA
%define TEXT        0xDBDBDBDB          ; the text routine
%define PLAY        0xD5D5D5D5          ; the page bank's play
%define LOADLIB     0xE3E3E3E3          ; LoadLibraryA's import slot
%define GETPROC     0xE4E4E4E4          ; GetProcAddress's
%define GETMODFN    0xE5E5E5E5          ; GetModuleFileNameA's
%define EXTRA       13                  ; the slot of the CD track no scene plays
%define ELEVEN      12                  ; the slot of track 11
%define ROWS        0x18                ; the page: each row's choice
%define STOCK       7                   ; the choices a row has
%define MORE        11                  ; and with the replay set
%define TESTVAL     0x3c                ; the sound page: BGM TEST's track
%define TESTMAX     0x68                ;   and its count
%define TESTSTOCK   13                  ;   which is the stock tracks'
%define SELECT      8                   ;   its car select's track, track 12
%else
%define PLAY        0x9A9A9A9A          ; placeholders, EXE_MAGICS: the sound bank's play
%define FADE        0x9C9C9C9C          ; its fade
%define RESTART     0x9D9D9D9D          ; its restart of a slot's CD track
%define STATE       0x9B9B9B9B          ; RACEBLOCK: the pointer to the race block
%define LOADLIB     0xE3E3E3E3          ; LoadLibraryA's import slot
%define GETPROC     0xE4E4E4E4          ; GetProcAddress's
%define GETMODFN    0xF9F9F9F9          ; GetModuleFileNameA's
%define GETTICK     0xC2C2C2C2          ; GetTickCount's
%define DRIVERCOUNT 0x14                ; the ten-year ending's step count in its DRIVER line
%define DRIVERSTEPS 780                 ;   which it shows for 780 steps, 13 s at 60 Hz
%define FADEMS      3000                ;   then fades the screen for 178 steps
%define WAVHEAD     44                  ; a WAV's header, before the samples
%define BYTESPER10MS 1764               ; 44.1 kHz, 16-bit stereo
%define EXTRA       14                  ; the slot of the CD track no scene plays
%define ELEVEN      9                   ; the slot of track 11
%endif

%define RECORD      0x28                ; a bank's record of a slot; +0 the CD track less one
%define FIRST       15                  ; the extra tracks
%define LAST        18
%define ENDING      18                  ; the ten-year ending's
%define REPLAYS     7                   ; found's bits of tracks 15, 16 and 17
%define CHOICE      8                   ; the slot of course choice 7, the first of the replay set's
%define MODE        0x38                ; the race block's
%define BITS        0x44
%define REPLAY      4                   ;   a replay
%define RACE        0x64
%define PATHLEN     272
%define DIRECTORY   0x10                ; FILE_ATTRIBUTE_DIRECTORY
%define SIZELOW     0x20                ; WIN32_FILE_ATTRIBUTE_DATA's nFileSizeLow
%define DIGITS      11                  ; the track's digits in name, after music\track

%if LAST > 99
%error the file names have two digits
%endif

; call through an import slot; the arguments are pushed, eax is free
%macro IMPORT 1
%ifdef OPTIONS
        mov     eax, ebp
        sub     eax, SELFRVA
        call    [eax + %1]
%else
        call    [%1]
%endif
%endmacro

%ifdef OPTIONS

        jmp     near init               ; +0, the count of choices
        jmp     near name               ; +5, a row's name
        jmp     near preview            ; +10, the preview's play
        jmp     near count              ; +15, BGM TEST's count of tracks
        jmp     near title              ; +20, its track's name
        jmp     near listen             ; +25, its play

; The sound page's BGM TEST: [esi+TESTVAL] the track shown, [esi+TESTMAX]
; how many. Past the stock 13 come the extra tracks there are files for,
; in order. In place of `mov dword [esi+TESTMAX], 13`; keeps every register.
count:  push    eax
        push    ecx
        call    tracks
        mov     ecx, TESTSTOCK
.bit:   shr     eax, 1
        adc     ecx, 0
        test    eax, eax
        jnz     .bit
        mov     [esi + TESTMAX], ecx
        pop     ecx
        pop     eax
        ret

; eax = the extra track BGM TEST's value eax names, or 0 for a stock one.
; Keeps the other registers.
pick:   sub     eax, TESTSTOCK
        jb      .stock
        push    ecx
        push    edx
        mov     edx, eax                ; which of those there
        call    tracks
        xor     ecx, ecx
.find:  bt      eax, ecx
        jnc     .next
        dec     edx
        js      .got
.next:  inc     ecx
        cmp     ecx, LAST - FIRST
        jbe     .find
        xor     eax, eax
        jmp     .out
.got:   lea     eax, [ecx + FIRST]
.out:   pop     edx
        pop     ecx
        ret
.stock: xor     eax, eax
        ret

; The text routine with BGM TEST's track name at [esp+4], page esi.
title:  mov     eax, [esi + TESTVAL]
        call    pick
        push    ebp
        call    .here
.here:  pop     ebp
        sub     ebp, .here
        test    eax, eax
        jz      .stock
        mov     eax, [ebp + titles - FIRST * 4 + eax * 4]
.put:   add     eax, ebp
        mov     [esp + 8], eax
        jmp     text
.stock: cmp     dword [esi + TESTVAL], SELECT
        jne     text
        mov     eax, select             ; the stock's name for it is the
        jmp     .put                    ; replay's, IGNITION'98

; The page bank's play of BGM TEST's value at [esp+4], ecx the bank: an
; extra track goes into slot 13's record and slot 13 plays.
listen: mov     eax, [esp + 4]
        call    pick
        test    eax, eax
        jz      tail
        dec     eax
        push    edx
        mov     edx, [ecx]              ; the bank's records
        mov     [edx + EXTRA * RECORD], eax
        pop     edx
        mov     dword [esp + 4], EXTRA
        jmp     tail

; ebx = 11 when one of tracks 15 to 17 is there, else 7. Keeps the rest.
init:   push    eax
        call    tracks
        mov     ebx, STOCK
        test    al, REPLAYS
        jz      .out
        mov     ebx, MORE
.out:   pop     eax
        ret

; The text routine with the row's name: row edi of the page esi, the
; string at [esp+4]. Choices 7 to 10 name the replay set's tracks.
name:   push    ebp
        call    .here
.here:  pop     ebp
        sub     ebp, .here
        mov     eax, [esi + ROWS + edi * 4]
        sub     eax, STOCK
        cmp     eax, 3
        ja      .go
        mov     eax, [ebp + names + eax * 4]
        add     eax, ebp
        mov     [esp + 8], eax
.go:    ; fall into text

; Leave through the text routine, ebp the blob, pushed.
text:   mov     eax, ebp
        sub     eax, SELFRVA
        add     eax, TEXT
        pop     ebp
        jmp     eax

; The page bank's play of slot [esp+4], ecx the bank: slots 8 to 11 are
; choices 7 to 10.
preview:
        call    map
        ; fall into tail

; Leave through the page bank's play.
tail:   push    ebp
        call    .here
.here:  pop     ebp
        sub     ebp, .here
        mov     eax, ebp
        sub     eax, SELFRVA
        add     eax, PLAY
        pop     ebp
        jmp     eax

%else

        jmp     near ending             ; +0, the ten-year ending's play
        jmp     near first              ; +5, a championship replay's race 1
        jmp     near later              ; +10, its races 2 to 4
        jmp     near single             ; +15, the other modes' scene music
        jmp     near course             ; +20, the race's play of the course's music
        jmp     near fade               ; +25, its fade
        jmp     near restart            ; +30, its restart
        jmp     near driver             ; +35, the ten-year ending's DRIVER line, held

; The ending's track 11 (slot 9), or track 18 in slot 14 when its file
; is there. ecx, the slot and the return are the play's.
ending: call    tracks
        push    ebp
        call    .here
.here:  pop     ebp
        sub     ebp, .here
        bt      eax, ENDING - FIRST
        setc    byte [ebp + holding]
        jnc     .go
        push    ecx
        call    [GETTICK]               ; the music's start
        mov     ecx, eax
        mov     eax, [ebp + sizes + (ENDING - FIRST) * 4]
        sub     eax, WAVHEAD
        jbe     .now
        imul    eax, eax, 10            ; bytes / 176.4 = ms
        xor     edx, edx
        push    BYTESPER10MS
        div     dword [esp]
        add     esp, 4
        sub     eax, FADEMS             ; the screen's fade takes the last of it
        jbe     .now
        add     ecx, eax
.now:   mov     [ebp + until], ecx
        pop     ecx
.go:    pop     ebp
        call    tracks
        mov     edx, ENDING
        jmp     extra

; In place of `mov eax, [obj+0x14]; cmp eax, 0x30c` in the ten-year
; ending's DRIVER line (ebx the ending): the count runs to the stock 780
; steps, and then, while track 18 plays, on until its music is all but
; over. Returns the flags of a compare the `jle` after it reads; keeps
; every register but eax.
driver: mov     eax, [ebx + DRIVERCOUNT]
        cmp     eax, DRIVERSTEPS
        jle     .out                    ; the stock count still running
        push    ebp
        call    .here
.here:  pop     ebp
        sub     ebp, .here
        cmp     byte [ebp + holding], 0
        je      .stock
        push    ecx
        push    edx
        call    [GETTICK]
        pop     edx
        pop     ecx
        sub     eax, [ebp + until]
        js      .hold                   ; not yet: wraps with GetTickCount
        mov     byte [ebp + holding], 0
.stock: pop     ebp
        mov     eax, [ebx + DRIVERCOUNT]
        cmp     eax, DRIVERSTEPS
        ret
.hold:  pop     ebp
        mov     eax, [ebx + DRIVERCOUNT]
        cmp     eax, 0x7fffffff         ; less: the jle holds the line
.out:   ret

first:  xor     eax, eax
        jmp     replay

later:  mov     eax, [STATE]
        mov     eax, [eax + RACE]
        test    eax, eax
        jz      play                    ; race index 0 here is the slot-7 branch
        and     eax, 3                  ; the ten-year championship's races past 4 go round
        jmp     replay

; A single-race mode's scene: in a replay one of the four, at random,
; among those there are files for (track 11 always); else the course's
; music. The call's other scenes are left alone.
single: mov     eax, [STATE]
        mov     edx, [eax + MODE]
        cmp     edx, 2
        je      .mode
        cmp     edx, 3
        je      .mode
        cmp     edx, 5
        je      .mode
        cmp     edx, 6
        jne     play
.mode:  test    byte [eax + BITS], REPLAY
        jz      course
        call    tracks
        test    al, REPLAYS
        jz      course
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
        jz      course                  ; no replay set: the course's music
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
; the course's music in the slot asked for.
extra:  sub     edx, FIRST
        bt      eax, edx
        jnc     course
        add     edx, FIRST - 1
        mov     eax, [ecx]              ; the bank's records
        mov     [eax + EXTRA * RECORD], edx
        mov     dword [esp + 4], EXTRA
play:   mov     eax, PLAY
        jmp     eax

; The course's music: its slot, choice + 1, at [esp+4].
course: call    map
        jmp     play
fade:   call    map
        mov     eax, FADE
        jmp     eax
restart:
        call    map
        mov     eax, RESTART
        jmp     eax

%endif

; A course choice's slot at [esp+8], with ecx its bank: slots 8 to 11,
; choices 7 to 10, become slot 14 with the track in its record, or slot
; 9 (track 11) for choice 8 and for a track whose file is not there.
; Keeps every register but eax.
map:    mov     eax, [esp + 8]
        sub     eax, CHOICE
        cmp     eax, 3
        ja      .out
        push    ecx
        push    edx
        mov     edx, eax
        call    tracks
        cmp     edx, 1
        je      .eleven
        jb      .have                   ; 0, track 15: bit 0
        dec     edx                     ; 2 and 3, tracks 16 and 17: bits 1 and 2
.have:  bt      eax, edx
        jnc     .eleven
        add     edx, FIRST - 1
        mov     eax, [ecx]              ; the bank's records
        mov     [eax + EXTRA * RECORD], edx
        mov     eax, EXTRA
        jmp     .set
.eleven:
        mov     eax, ELEVEN
.set:   mov     [esp + 16], eax
        pop     edx
        pop     ecx
.out:   ret

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
        IMPORT  LOADLIB
        test    eax, eax
        jz      .out
        lea     ecx, [ebp + getattr]
        push    ecx
        push    eax
        IMPORT  GETPROC
        test    eax, eax
        jz      .out
        mov     ebx, eax                ; GetFileAttributesExA
        push    PATHLEN - 24            ; room after it for the file's name
        lea     edi, [ebp + path]
        push    edi
        push    0
        IMPORT  GETMODFN
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
        lea     ecx, [ebp + file]
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
        lea     eax, [ebp + attrs]
        push    eax
        push    0                       ; GetFileExInfoStandard
        lea     eax, [ebp + path]
        push    eax
        call    ebx
        test    eax, eax
        jz      .next
        test    byte [ebp + attrs], DIRECTORY
        jnz     .next
        mov     eax, [ebp + attrs + SIZELOW]
        mov     [ebp + sizes + edi * 4 - FIRST * 4], eax
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
sizes:      times LAST - FIRST + 1 dd 0 ; each one's file size
attrs:      times 9 dd 0                ; WIN32_FILE_ATTRIBUTE_DATA
%ifndef OPTIONS
until:      dd 0                        ; GetTickCount when the DRIVER line may end
holding:    db 0                        ; track 18 plays the ten-year ending
%endif
%ifdef OPTIONS
names:      dd  replay1, replay2, replay3, replay4  ; choices 7 to 10, from the blob
; The Dreamcast's titles for the four replay tracks, races 1 to 4.
replay1:    db  "IGNITION'98", 0                ; track 15
replay2:    db  "NIGHT GROOVIN'", 0             ; track 11
replay3:    db  'ESTRADA NOVA', 0               ; track 16
replay4:    db  'M N F ?', 0                    ; track 17
titles:     dd  replay1, replay3, replay4, dawn ; BGM TEST: tracks 15 to 18
dawn:       db  'TILL YOU SEE THE DAWN', 0      ; track 18, the ten-year ending's
select:     db  'IGNITION 98 SELECT', 0         ; BGM TEST 9, track 12, the car select's
%endif
kernel32:   db 'kernel32.dll', 0
getattr:    db 'GetFileAttributesExA', 0
file:       db 'music\track15.wav', 0
path:       times PATHLEN db 0
