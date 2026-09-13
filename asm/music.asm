; music.asm - file-based CD audio for SEGA RALLY 2, inside MUSASHI\MGAudio.dll.
;
; The game's music is Redbook audio on the play disc, played over MCI by
; MGAudio.dll. This blob goes in a section the patcher appends to that DLL;
; its 11 `call [__imp__mciSendCommandA]` sites are rewritten to call the
; hook, its one `mov esi, [__imp__mciSendCommandA]` to fetch the hook's
; address instead, and the entry point is repointed at startup, which
; chains to the original.
;
;   +0   jmp hook       <- what the call sites are pointed at
;   +5   jmp startup    <- the new DllMain
;   +10  jmp hookaddr   <- esi = hook, for the one site that loads the
;                         import into esi and calls through it
;   +15  jmp setvolume  <- what the CD-volume method's entry is pointed at
;   +20  jmp getvolume  <- and the method that reads it back
;
; The DLL is relocated at load, so nothing here is absolute: the blob finds
; its own base (call/pop) and reaches everything as [ebx + offset]. The five
; MAGIC_ placeholders are offsets from the blob to things in the DLL, filled
; by the patcher; they are the same wherever the DLL lands.
;
; Tracks are <gamedir>\music\trackNN.wav, 44100/16/stereo as the ripper
; writes them; length comes from the file size. No tracks found means the
; hook forwards everything and the game reads a real CD as it always did.
;
; A track plays from a DirectSound buffer of its own, filled from the file
; on open, with the BGM slider set on that buffer in hundredths of a dB -
; the units the mix keeps every other level in, so the music sits on the
; same curve as the effects on Windows and Wine alike. winmm's volume, by
; handle or by device, is the application's session volume on Windows
; since Vista, and moves the effects with the music.
;
; MGAudio talks to MCI from several short-lived threads it also
; terminates. So every DirectSound call is made by one worker thread
; created at startup: the hook writes D_OP and D_ARG, signals D_HREQ and waits on
; D_HDONE; the worker does it, stores the result in D_RESULT and signals
; back.

bits 32
%include "mix.inc"

%define MAGIC_ORIGENTRY 0xE1E1E1E1      ; offset to the original entry point
%define MAGIC_IATMCI    0xE2E2E2E2      ; offset to the mciSendCommandA IAT slot
%define MAGIC_LOADLIB   0xE3E3E3E3      ; offset to the LoadLibraryA IAT slot
%define MAGIC_GETPROC   0xE4E4E4E4      ; offset to the GetProcAddress IAT slot
%define MAGIC_GETMODFN  0xE5E5E5E5      ; offset to the GetModuleFileNameA IAT slot

%define FAKE_ID         0xFACE

%define MCI_OPEN        0x803
%define MCI_CLOSE       0x804
%define MCI_PLAY        0x806
%define MCI_SEEK        0x807
%define MCI_STOP        0x808
%define MCI_PAUSE       0x809
%define MCI_SET         0x80D
%define MCI_STATUS      0x814
%define MCI_RESUME      0x855

%define MCI_FROM            0x004
%define MCI_TO              0x008
%define MCI_TRACK           0x010
%define MCI_STATUS_ITEM     0x100
%define MCI_OPEN_TYPE_ID    0x1000
%define MCI_OPEN_TYPE       0x2000
%define MCI_DEVTYPE_CD      0x204

%define ST_LENGTH       1
%define ST_POSITION     2
%define ST_NTRACKS      3

%define MCIERR_OUTOFRANGE 0x112
%define MCIERR_INTERNAL   0x115

; The worker's operations. D_ARG is the track for OPEN, ms for PLAY.
%define OP_OPEN         1
%define OP_PLAY         2
%define OP_STOP         3
%define OP_PAUSE        4
%define OP_RESUME       5
%define OP_CLOSE        6
%define OP_POS          7               ; D_RESULT = ms into the track
%define OP_VOL          8

%define BYTES_PER_SEC   176400          ; 44100 * 2 * 2
%define WAV_HEADER      44

; IDirectSound
%define DS_CREATEBUFFER 0x0c
%define DS_SETCOOP      0x18
%define DSSCL_NORMAL    1
; IDirectSoundBuffer
%define DSB_RELEASE     0x08
%define DSB_GETPOS      0x10
%define DSB_GETSTATUS   0x24
%define DSB_LOCK        0x2c
%define DSB_PLAY        0x30
%define DSB_SETPOS      0x34
%define DSB_SETVOLUME   0x3c
%define DSB_STOP        0x48
%define DSB_UNLOCK      0x4c
%define DSBCAPS         0x18088         ; LOCSOFTWARE | CTRLVOLUME | GLOBALFOCUS | GETCURRENTPOSITION2
%define DSBSTATUS_PLAYING 1
%define DSBVOLUME_MIN   -10000

; The buffer's state, for the position: a stopped buffer that was playing
; ran out, and is at the track's end.
%define ST_IDLE         0
%define ST_PLAYING      1
%define ST_PAUSED       2

%define MAXTRACK        99
%define PATHLEN         272

; ---------------------------------------------------------------- thunks

        jmp     near hook               ; +0
        jmp     near startup            ; +5
        jmp     near hookaddr           ; +10
        jmp     near setvolume          ; +15
        jmp     near getvolume          ; +20

; ------------------------------------------------------------- utilities

; ebx = blob base, on return.
getbase:
        call    .here
.here:  pop     ebx
        sub     ebx, .here
        ret

; esi = the hook's address. Replaces `mov esi, [slot]`; ebx kept.
hookaddr:
        push    ebx
        call    getbase
        mov     esi, ebx
        pop     ebx
        ret

; esi -> source, edi -> destination. Copies including NUL, leaves edi on it.
scat:
        lodsb
        stosb
        test    al, al
        jnz     scat
        dec     edi
        ret

; eax = value 0..99, written as two digits at edi, edi advanced.
put2:
        xor     edx, edx
        mov     ecx, 10
        div     ecx
        add     al, '0'
        stosb
        mov     al, dl
        add     al, '0'
        stosb
        ret

; Trace mode: every command the game sends, to OutputDebugStringA as
; "sr2 <id> <msg> <flags> <p1> <p2> <p3>", which WINEDEBUG=+debugstr
; shows. On when music\trace exists.
trace:
        pushad
        lea     edi, [ebx + D_TRC]
        lea     esi, [ebx + S_TRACE]
        call    scat
        mov     eax, [ebp + 8]
        call    putnum
        mov     byte [edi], ' '
        inc     edi
        mov     eax, [ebp + 12]
        call    putnum
        mov     byte [edi], ' '
        inc     edi
        mov     eax, [ebp + 16]
        call    putnum
        mov     esi, [ebp + 20]
        test    esi, esi
        jz      .send
        add     esi, 4
        push    3                       ; putnum uses ecx, so the count lives here
.param:
        mov     byte [edi], ' '
        inc     edi
        lodsd
        call    putnum
        dec     dword [esp]
        jnz     .param
        pop     eax
.send:
        lea     eax, [ebx + D_TRC]
        push    eax
        call    dword [ebx + D_ODS]
        popad
        ret

; Trace mode, the worker's side: "sr2 op <op> <arg> <result> <last HRESULT>".
optrace:
        pushad
        lea     edi, [ebx + D_TRC]
        lea     esi, [ebx + S_OPTRACE]
        call    scat
        mov     eax, [ebx + D_OP]
        call    putnum
        mov     byte [edi], ' '
        inc     edi
        mov     eax, [ebx + D_ARG]
        call    putnum
        mov     byte [edi], ' '
        inc     edi
        mov     eax, [ebx + D_RESULT]
        call    putnum
        mov     byte [edi], ' '
        inc     edi
        mov     eax, [ebx + D_LASTHR]
        call    putnum
        lea     eax, [ebx + D_TRC]
        push    eax
        call    dword [ebx + D_ODS]
        popad
        ret

; eax = value, written in decimal at edi, NUL-terminated, edi on the NUL.
putnum:
        push    ebx
        mov     ecx, 10
        xor     ebx, ebx
.digits:
        xor     edx, edx
        div     ecx
        push    edx
        inc     ebx
        test    eax, eax
        jnz     .digits
.write:
        pop     eax
        add     al, '0'
        stosb
        dec     ebx
        jnz     .write
        mov     byte [edi], 0
        pop     ebx
        ret

; Asks the worker for operation eax with argument ecx. eax = its result.
; ebx = base; the other registers kept. One caller at a time: the exe
; fades on one thread while another changes screen, and two requests
; at once left one of them unrun. A mutex rather than a critical
; section, since MGAudio terminates its threads: an abandoned mutex
; is handed on, an abandoned critical section is held for ever.
request:
        push    ecx
        push    edx
        push    eax
        push    -1
        push    dword [ebx + D_HMUTEX]
        call    dword [ebx + D_WAIT]
        pop     eax
        mov     ecx, [esp + 4]          ; the argument, as pushed; the wait keeps nothing
        mov     [ebx + D_OP], eax
        mov     [ebx + D_ARG], ecx
        push    dword [ebx + D_HREQ]
        call    dword [ebx + D_SETEVENT]
        push    -1                      ; INFINITE
        push    dword [ebx + D_HDONE]
        call    dword [ebx + D_WAIT]
        mov     eax, [ebx + D_RESULT]
        push    eax
        push    dword [ebx + D_HMUTEX]
        call    dword [ebx + D_RELMUTEX]
        pop     eax
        pop     edx
        pop     ecx
        ret

; eax = TMSF (track, min, sec, frame), returns ecx = ms into the track,
; eax = track.
tmsf_ms:
        mov     ecx, eax
        shr     ecx, 8
        movzx   edx, cl                 ; minutes
        imul    edx, 60
        shr     ecx, 8
        movzx   esi, cl                 ; seconds
        add     edx, esi
        imul    edx, 1000
        shr     ecx, 8                  ; frames
        imul    ecx, 40                 ; frames * 40 / 3 = frames * 1000 / 75
        push    eax
        push    edx
        mov     eax, ecx
        xor     edx, edx
        mov     ecx, 3
        div     ecx
        pop     edx
        add     eax, edx
        pop     ecx
        xchg    eax, ecx                ; ecx = ms
        and     eax, 0xFF               ; eax = track
        ret

; eax = ms, ecx = track. Returns eax = TMSF.
ms_tmsf:
        push    ebx
        mov     ebx, ecx                ; track
        xor     edx, edx
        mov     ecx, 1000
        div     ecx                     ; eax = seconds, edx = ms rest
        imul    edx, 75
        push    eax
        mov     eax, edx
        xor     edx, edx
        div     ecx                     ; eax = frames
        mov     ecx, eax
        pop     eax
        shl     ecx, 24                 ; frames << 24
        xor     edx, edx
        push    ecx
        mov     ecx, 60
        div     ecx                     ; eax = minutes, edx = seconds
        pop     ecx
        shl     edx, 16
        or      ecx, edx
        shl     eax, 8
        or      ecx, eax
        or      ecx, ebx
        mov     eax, ecx
        pop     ebx
        ret

; eax = frames. Returns eax = MSF (min, sec, frame), the length format.
frames_msf:
        xor     edx, edx
        mov     ecx, 75
        div     ecx                     ; eax = seconds, edx = frames
        mov     ecx, edx
        shl     ecx, 16
        xor     edx, edx
        push    ecx
        mov     ecx, 60
        div     ecx                     ; eax = minutes, edx = seconds
        pop     ecx
        shl     edx, 8
        or      eax, edx
        or      eax, ecx
        ret

; Writes NN.wav for track eax into D_PATH after the fixed prefix.
trackpath:
        lea     edi, [ebx + D_PATH]
        add     edi, [ebx + D_NNPOS]
        call    put2
        lea     esi, [ebx + S_WAV]
        call    scat
        ret

; ---------------------------------------------------------------- worker
; Waits for a request, does it, answers. Never returns. Every DirectSound
; and file call is made here.

worker:
        call    getbase
.loop:
        push    -1
        push    dword [ebx + D_HREQ]
        call    dword [ebx + D_WAIT]
        mov     eax, [ebx + D_OP]
        cmp     eax, OP_OPEN
        je      .open
        cmp     eax, OP_PLAY
        je      .play
        cmp     eax, OP_STOP
        je      .stop
        cmp     eax, OP_PAUSE
        je      .pause
        cmp     eax, OP_RESUME
        je      .resume
        cmp     eax, OP_CLOSE
        je      .close
        cmp     eax, OP_POS
        je      .pos
        cmp     eax, OP_VOL
        je      .vol
        xor     eax, eax
.answer:
        mov     [ebx + D_RESULT], eax
        cmp     dword [ebx + D_TRACE], 0
        je      .signal
        call    optrace
.signal:
        push    dword [ebx + D_HDONE]
        call    dword [ebx + D_SETEVENT]
        jmp     .loop

.open:
        call    op_close
        call    op_open
        jmp     .answer
.play:
        call    op_play
        jmp     .answer
.stop:
        call    op_stop
        xor     eax, eax
        jmp     .answer
.pause:
        call    dev_pause
        xor     eax, eax
        jmp     .answer
.resume:
        call    dev_restart
        xor     eax, eax
        jmp     .answer
.close:
        call    op_close
        xor     eax, eax
        jmp     .answer
.pos:
        call    op_pos
        jmp     .answer
.vol:
        call    op_vol
        xor     eax, eax
        jmp     .answer

; The DirectSound object, made on the first open: DirectSoundCreate and
; the cooperative level, normal, on the desktop window - the buffers are
; GLOBALFOCUS, so no window of the game's is needed. eax = 0 or
; MCIERR_INTERNAL.
dsound:
        cmp     dword [ebx + D_DS], 0
        jne     .have
        push    0
        lea     eax, [ebx + D_DS]
        push    eax
        push    0
        call    dword [ebx + D_DSCREATE]
        mov     [ebx + D_LASTHR], eax
        test    eax, eax
        jnz     .fail
        push    DSSCL_NORMAL
        call    dword [ebx + D_DESKTOP]
        push    eax
        mov     eax, [ebx + D_DS]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DS_SETCOOP]
        mov     [ebx + D_LASTHR], eax
        test    eax, eax
        jnz     .fail
.have:
        xor     eax, eax
        ret
.fail:
        mov     eax, MCIERR_INTERNAL
        ret

; Opens track D_ARG: the file read into a buffer of its size, the volume
; set. eax = 0 or MCIERR_INTERNAL, with everything released on failure.
op_open:
        call    dsound
        test    eax, eax
        jnz     .out
        mov     eax, [ebx + D_ARG]
        call    trackpath
        push    0
        push    0x80                    ; FILE_ATTRIBUTE_NORMAL
        push    3                       ; OPEN_EXISTING
        push    0
        push    1                       ; FILE_SHARE_READ
        push    0x80000000              ; GENERIC_READ
        lea     eax, [ebx + D_PATH]
        push    eax
        call    dword [ebx + D_CREATEF]
        cmp     eax, -1
        je      .fail
        mov     [ebx + D_FILE], eax
        push    0
        push    eax
        call    dword [ebx + D_GETSIZE]
        sub     eax, WAV_HEADER
        jbe     .fail
        and     eax, ~3                 ; whole frames
        mov     [ebx + D_DATASIZE], eax
        mov     [ebx + D_DESC + 8], eax ; dwBufferBytes
        push    0
        push    0
        push    0
        push    2                       ; PAGE_READONLY
        push    0
        push    dword [ebx + D_FILE]
        call    dword [ebx + D_CREATEMAP]
        test    eax, eax
        jz      .fail
        mov     [ebx + D_MAP], eax
        push    0
        push    0
        push    0
        push    4                       ; FILE_MAP_READ
        push    eax
        call    dword [ebx + D_MAPVIEW]
        test    eax, eax
        jz      .fail
        mov     [ebx + D_VIEW], eax
        lea     eax, [ebx + D_FMT]
        mov     [ebx + D_DESC + 16], eax
        push    0
        lea     eax, [ebx + D_BUF]
        push    eax
        lea     eax, [ebx + D_DESC]
        push    eax
        mov     eax, [ebx + D_DS]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DS_CREATEBUFFER]
        mov     [ebx + D_LASTHR], eax
        test    eax, eax
        jnz     .fail
        push    0
        lea     eax, [ebx + D_LOCK + 12]
        push    eax                     ; n2
        lea     eax, [ebx + D_LOCK + 8]
        push    eax                     ; p2
        lea     eax, [ebx + D_LOCK + 4]
        push    eax                     ; n1
        lea     eax, [ebx + D_LOCK]
        push    eax                     ; p1
        push    dword [ebx + D_DATASIZE]
        push    0
        mov     eax, [ebx + D_BUF]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DSB_LOCK]
        mov     [ebx + D_LASTHR], eax
        test    eax, eax
        jnz     .fail
        mov     esi, [ebx + D_VIEW]
        add     esi, WAV_HEADER
        mov     edi, [ebx + D_LOCK]
        mov     ecx, [ebx + D_LOCK + 4]
        rep movsb
        mov     edi, [ebx + D_LOCK + 8]
        mov     ecx, [ebx + D_LOCK + 12]
        rep movsb
        push    dword [ebx + D_LOCK + 12]
        push    dword [ebx + D_LOCK + 8]
        push    dword [ebx + D_LOCK + 4]
        push    dword [ebx + D_LOCK]
        mov     eax, [ebx + D_BUF]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DSB_UNLOCK]
        call    unmap
        call    op_vol
        mov     dword [ebx + D_STATE], ST_IDLE
        xor     eax, eax
.out:
        ret
.fail:
        call    op_close
        mov     eax, MCIERR_INTERNAL
        ret

; Releases the view, the mapping and the file, whichever are held.
unmap:
        mov     eax, [ebx + D_VIEW]
        test    eax, eax
        jz      .noview
        push    eax
        call    dword [ebx + D_UNMAP]
        mov     dword [ebx + D_VIEW], 0
.noview:
        mov     eax, [ebx + D_MAP]
        test    eax, eax
        jz      .nomap
        push    eax
        call    dword [ebx + D_CLOSEH]
        mov     dword [ebx + D_MAP], 0
.nomap:
        mov     eax, [ebx + D_FILE]
        test    eax, eax
        jz      .nofile
        push    eax
        call    dword [ebx + D_CLOSEH]
        mov     dword [ebx + D_FILE], 0
.nofile:
        ret

; Stops and releases the buffer, and whatever an open left half done. A
; buffer released while playing is not stopped cleanly on Windows.
op_close:
        call    unmap
        mov     eax, [ebx + D_BUF]
        test    eax, eax
        jz      .nobuf
        call    dev_stop
        mov     eax, [ebx + D_BUF]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DSB_RELEASE]
        mov     dword [ebx + D_BUF], 0
.nobuf:
        mov     dword [ebx + D_STATE], ST_IDLE
        ret

; Plays from ms D_ARG. eax = 0 or MCIERR_INTERNAL.
op_play:
        cmp     dword [ebx + D_BUF], 0
        je      .nobuf
        mov     eax, [ebx + D_ARG]
        imul    eax, BYTES_PER_SEC / 200
        xor     edx, edx
        mov     ecx, 5
        div     ecx                     ; ms * 176400 / 1000
        and     eax, ~3
        cmp     eax, [ebx + D_DATASIZE]
        jb      .inside
        mov     eax, [ebx + D_DATASIZE]
        sub     eax, 4
.inside:
        push    eax
        mov     eax, [ebx + D_BUF]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DSB_SETPOS]
        mov     [ebx + D_LASTHR], eax
        test    eax, eax
        jnz     .nobuf
        call    dev_play
        test    eax, eax
        jnz     .nobuf
        ret
.nobuf:
        mov     eax, MCIERR_INTERNAL
        ret

; Stops and goes back to the start.
op_stop:
        cmp     dword [ebx + D_BUF], 0
        je      .none
        call    dev_stop
        push    0
        mov     eax, [ebx + D_BUF]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DSB_SETPOS]
        mov     dword [ebx + D_STATE], ST_IDLE
.none:
        ret

; eax = ms into the track: the play cursor, or the end once a play has
; run out - DirectSound stops the buffer there and no longer says where.
op_pos:
        xor     eax, eax
        cmp     dword [ebx + D_BUF], 0
        je      .done
        cmp     dword [ebx + D_STATE], ST_PLAYING
        jne     .cursor
        lea     eax, [ebx + D_STATUS]
        push    eax
        mov     eax, [ebx + D_BUF]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DSB_GETSTATUS]
        test    eax, eax
        jnz     .cursor
        test    dword [ebx + D_STATUS], DSBSTATUS_PLAYING
        jnz     .cursor
        mov     eax, [ebx + D_DATASIZE]
        jmp     .ms
.cursor:
        push    0
        lea     eax, [ebx + D_STATUS]
        push    eax
        mov     eax, [ebx + D_BUF]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DSB_GETPOS]
        test    eax, eax
        jnz     .zero
        mov     eax, [ebx + D_STATUS]
.ms:
        mov     ecx, 200
        mul     ecx
        mov     ecx, BYTES_PER_SEC / 5
        div     ecx                     ; bytes * 1000 / 176400
        ret
.zero:
        xor     eax, eax
.done:
        ret

op_vol:
        cmp     dword [ebx + D_BUF], 0
        je      .none
        push    dword [ebx + D_VOL]
        call    setvol
.none:
        ret

; SetVolume(the dword pushed), stdcall.
setvol:
        push    dword [esp + 4]
        mov     eax, [ebx + D_BUF]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DSB_SETVOLUME]
        ret     4

; A pause keeps the cursor; a resume plays on from it.
dev_pause:
        cmp     dword [ebx + D_STATE], ST_PLAYING
        jne     .none
        call    dev_stop
        mov     dword [ebx + D_STATE], ST_PAUSED
.none:
        ret

dev_restart:
        cmp     dword [ebx + D_STATE], ST_PAUSED
        jne     .none
        call    dev_play
.none:
        ret

; Play(0, 0, 0), no loop, at the slider's volume. eax = its result; the
; state playing on success.
dev_play:
        call    op_vol
        push    0
        push    0
        push    0
        mov     eax, [ebx + D_BUF]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DSB_PLAY]
        mov     [ebx + D_LASTHR], eax
        test    eax, eax
        jnz     .out
        mov     dword [ebx + D_STATE], ST_PLAYING
.out:
        ret

; Silence first: Windows' mixer holds audio mixed ahead of the cursor and
; remixes it on a volume change, so the stop is clean.
dev_stop:
        push    DSBVOLUME_MIN
        call    setvol
        mov     eax, [ebx + D_BUF]
        push    eax
        mov     ecx, [eax]
        call    dword [ecx + DSB_STOP]
        ret

; ------------------------------------------------- setvolume, getvolume
; Replace the CD-volume methods: stdcall (this, values, flags), where
; values is the game's struct - +8 the channel count, +0xc and +0x10 the
; channels, 0..10000. Both return S_OK; the mixer is never touched.
;
; The exe reaches setvolume from four places, each with its own idea of
; the value, a percentage of the level getvolume gave it at startup
; (10000, so v = percent x 100):
;
;   the menu's level, the slider's step x 11.11 (0x473c5c), flags 0x40 by
;     the cdlevel patch, which the music patch requires;
;   the race's level, the step x 9 (0x473f11), flags 0x80000000;
;   the mute when a race starts, 0 (0x474210), flags 0x80000000;
;   the fade before a stop, 100 down to 10 (0x4741bc), flags 0.
;
; A level is the step on the mix's curve plus CD_DB, in hundredths of a
; dB, and is remembered; the mute is off without forgetting it. The fade
; was written for a mixer line that took amplitude, from full whatever
; the slider said: on the curve that would start up to 33 dB above the
; level, so it is taken as a percentage of the level in amplitude, the
; level plus 20 log10(v / 10000), counting from its start at 100.
;
; A fade runs on its own thread and a screen change can cut across it:
; the new screen sets the level and plays, and the fade's last steps
; land on the new track. So a fade counts from its start, 100, and ends
; at any level or mute; a step arriving outside one is dropped.
;
; The original DLL used only bit 31 of the flags, to wait for the
; previous set's thread; bit 6 is free for the mark.

setvolume:
        push    ebx
        call    getbase
        mov     eax, [esp + 12]         ; values
        test    eax, eax
        jz      .ok
        cmp     dword [eax + 8], 0
        je      .ok
        mov     eax, [eax + 12]
        cmp     eax, 10000
        jbe     .scale
        mov     eax, 10000
.scale:
        mov     edx, [esp + 16]         ; flags
        test    edx, 0x40
        jnz     .menu
        test    edx, 0x80000000
        jz      .fadeof
        test    eax, eax
        jz      .mute
        xor     edx, edx
        mov     ecx, 900
        div     ecx                     ; the race's level: step x 9 percent
        jmp     .level
.fadeof:
        cmp     eax, 10000
        je      .fadestart
        mov     ecx, eax
        jmp     .fadestep
.menu:
        xor     edx, edx
        mov     ecx, 1100
        div     ecx                     ; the menu's level: step x 11.11 percent
.level:
        cmp     eax, 9
        jbe     .step
        mov     eax, 9
.step:
        mov     ecx, DSBVOLUME_MIN      ; step 0: off
        test    eax, eax
        jz      .setlevel
        imul    eax, MIX_STEP
        lea     ecx, [eax + MIX_BOTTOM + CD_DB]   ; the mix curve plus the CD offset
.setlevel:
        mov     [ebx + D_SLIDER], ecx
        mov     dword [ebx + D_FADING], 0
        jmp     .have
.fadestart:
        mov     dword [ebx + D_FADING], 1
        mov     ecx, [ebx + D_SLIDER]
        jmp     .have
.fadestep:
        cmp     dword [ebx + D_FADING], 0
        je      .ok                     ; a step of a fade that is over
        mov     eax, ecx                ; the value
        xor     edx, edx
        mov     ecx, 100
        div     ecx                     ; eax = percent
        movsx   eax, word [ebx + S_PCTDB + eax * 2]
        mov     ecx, [ebx + D_SLIDER]
        add     ecx, eax
        cmp     ecx, DSBVOLUME_MIN
        jge     .have
        mov     ecx, DSBVOLUME_MIN
        jmp     .have
.mute:
        mov     dword [ebx + D_FADING], 0
        mov     ecx, DSBVOLUME_MIN
.have:
        mov     [ebx + D_VOL], ecx
        cmp     dword [ebx + D_NTRACKS], 0
        je      .ok                     ; no worker: nothing to set it on
        mov     eax, OP_VOL             ; ecx, the value, for the trace only
        call    request
.ok:
        xor     eax, eax
        pop     ebx
        ret     12

; Full, always: the exe reads this once at startup and scales every
; percentage it sends by it.
getvolume:
        mov     eax, [esp + 8]          ; values
        test    eax, eax
        jz      .ok
        mov     dword [eax + 8], 2
        mov     dword [eax + 12], 10000
        mov     dword [eax + 16], 10000
.ok:
        xor     eax, eax
        ret     12

; ------------------------------------------------------------------ hook
; mciSendCommandA(id, msg, flags, params), stdcall.

hook:
        push    ebp
        mov     ebp, esp
        push    ebx
        push    esi
        push    edi
        call    getbase
        cmp     dword [ebx + D_TRACE], 0
        je      .go_on
        call    trace
.go_on:
        mov     eax, [ebp + 12]         ; msg
        cmp     eax, MCI_OPEN
        jne     .notopen
        cmp     dword [ebx + D_NTRACKS], 0
        je      .forward
        mov     ecx, [ebp + 16]         ; flags
        and     ecx, MCI_OPEN_TYPE | MCI_OPEN_TYPE_ID
        cmp     ecx, MCI_OPEN_TYPE | MCI_OPEN_TYPE_ID
        jne     .forward
        mov     edx, [ebp + 20]         ; params
        cmp     dword [edx + 8], MCI_DEVTYPE_CD
        jne     .forward
        mov     dword [edx + 4], FAKE_ID
        jmp     .ok
.notopen:
        cmp     dword [ebp + 8], FAKE_ID
        jne     .forward
        cmp     eax, MCI_CLOSE
        je      .close
        cmp     eax, MCI_PLAY
        je      .play
        cmp     eax, MCI_SEEK
        je      .seek
        cmp     eax, MCI_STOP
        je      .stop
        cmp     eax, MCI_PAUSE
        je      .pause
        cmp     eax, MCI_RESUME
        je      .resume
        cmp     eax, MCI_STATUS
        je      .status
        jmp     .ok                     ; MCI_SET and anything else: fine

.close:
        mov     eax, OP_CLOSE
        call    .simple
        mov     dword [ebx + D_OPEN], 0
        jmp     .ok
.stop:
        mov     eax, OP_STOP
        call    .simple
        jmp     .ok
.pause:
        mov     eax, OP_PAUSE
        call    .simple
        jmp     .ok
.resume:
        mov     eax, OP_RESUME
        call    .simple
        jmp     .ok

.play:
        mov     ecx, [ebx + D_SEEKMS]
        mov     eax, [ebx + D_CUR]
        test    dword [ebp + 16], MCI_FROM
        jz      .playfrom
        mov     edx, [ebp + 20]
        mov     eax, [edx + 4]          ; dwFrom, TMSF
        call    tmsf_ms
.playfrom:
        mov     dword [ebx + D_SEEKMS], 0
        test    eax, eax
        jz      .range
        cmp     eax, [ebx + D_NTRACKS]
        ja      .range
        cmp     dword [ebx + D_TOC + eax * 4], 0
        je      .range
        mov     [ebx + D_CUR], eax
        mov     dword [ebx + D_OPEN], 0
        push    ecx
        mov     ecx, eax
        mov     eax, OP_OPEN
        call    request
        pop     ecx
        test    eax, eax
        jnz     .ret
        mov     dword [ebx + D_OPEN], 1
.go:
        mov     eax, OP_PLAY
        call    request
        jmp     .ret
.range:
        mov     eax, MCIERR_OUTOFRANGE
        jmp     .ret

; The exe seeks with the track its play adds one to - at "Go!" it seeks
; the course track, playing as N+1, to track N at 0:00 - so a seek to the
; open track or the one below it is a seek within the open track, and
; no play follows, so the hook plays from there.
.seek:
        test    dword [ebp + 16], MCI_TO
        jz      .ok
        mov     edx, [ebp + 20]
        mov     eax, [edx + 4]          ; dwTo, TMSF
        call    tmsf_ms
        mov     [ebx + D_SEEKMS], ecx
        cmp     dword [ebx + D_OPEN], 0
        je      .seeklater
        cmp     eax, [ebx + D_CUR]
        je      .go
        inc     eax
        cmp     eax, [ebx + D_CUR]
        je      .go
.seeklater:
        mov     [ebx + D_CUR], eax      ; the next play without FROM starts here
        jmp     .ok

.status:
        mov     edx, [ebp + 20]
        mov     dword [edx + 4], 0      ; dwReturn
        test    dword [ebp + 16], MCI_STATUS_ITEM
        jz      .ok
        mov     eax, [edx + 8]          ; dwItem
        cmp     eax, ST_NTRACKS
        je      .ntracks
        cmp     eax, ST_LENGTH
        je      .length
        cmp     eax, ST_POSITION
        je      .position
        jmp     .ok
.ntracks:
        mov     eax, [ebx + D_NTRACKS]
        mov     [edx + 4], eax
        jmp     .ok
.length:
        test    dword [ebp + 16], MCI_TRACK
        jz      .ok
        mov     eax, [edx + 12]         ; dwTrack
        cmp     eax, MAXTRACK
        ja      .ok
        mov     eax, [ebx + D_TOC + eax * 4]
        call    frames_msf
        mov     edx, [ebp + 20]
        mov     [edx + 4], eax
        jmp     .ok
.position:
        xor     eax, eax
        cmp     dword [ebx + D_OPEN], 0
        je      .posdone
        mov     eax, OP_POS
        xor     ecx, ecx
        call    request
.posdone:
        mov     ecx, [ebx + D_CUR]
        call    ms_tmsf
        mov     edx, [ebp + 20]
        mov     [edx + 4], eax
        jmp     .ok

; eax = an operation with no argument. Sends it.
.simple:
        xor     ecx, ecx
        call    request
        ret

.ok:
        xor     eax, eax
.ret:
        pop     edi
        pop     esi
        pop     ebx
        pop     ebp
        ret     16
.forward:
        mov     eax, [ebx + MAGIC_IATMCI]
        pop     edi
        pop     esi
        pop     ebx
        pop     ebp
        jmp     eax

; --------------------------------------------------------------- startup
; DllMain(hinst, reason, reserved). Builds the track table once, on process
; attach, then chains to the original entry point with the stack untouched.

startup:
        cmp     dword [esp + 8], 1      ; DLL_PROCESS_ATTACH
        jne     .chain
        pushad
        call    getbase
        cmp     dword [ebx + D_INIT], 0
        jne     .done
        mov     dword [ebx + D_INIT], 1

        ; The imports: S_MODULES names a module and then its functions, an
        ; empty name ending the list and another the whole; the addresses
        ; go to D_FN in that order. One missing and there is no music.
        lea     esi, [ebx + S_MODULES]
        lea     edi, [ebx + D_FN]
.module:
        cmp     byte [esi], 0
        je      .resolved
        push    esi
        call    dword [ebx + MAGIC_LOADLIB]
        test    eax, eax
        jz      .done
        mov     ebp, eax
.skipname:
        lodsb
        test    al, al
        jnz     .skipname
.function:
        cmp     byte [esi], 0
        je      .modend
        push    esi
        push    ebp
        call    dword [ebx + MAGIC_GETPROC]
        test    eax, eax
        jz      .done
        stosd
.skipfn:
        lodsb
        test    al, al
        jnz     .skipfn
        jmp     .function
.modend:
        inc     esi
        jmp     .module
.resolved:
        lea     eax, [ebx + S_ODS]
        push    eax
        push    ebp                     ; kernel32, the last module
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_ODS], eax      ; may be 0: then no trace

        ; the game folder, from the exe's path
        push    260
        lea     eax, [ebx + D_PATH]
        push    eax
        push    0
        call    dword [ebx + MAGIC_GETMODFN]
        test    eax, eax
        jz      .done
        lea     edi, [ebx + D_PATH]
        add     edi, eax
.back:
        dec     edi
        cmp     byte [edi], '\'
        jne     .back
        inc     edi
        push    edi
        ; music\trace beside the tracks turns the trace on
        lea     esi, [ebx + S_TRACEF]
        call    scat
        push    0
        push    0x80
        push    3
        push    0
        push    1
        push    0x80000000
        lea     eax, [ebx + D_PATH]
        push    eax
        call    dword [ebx + D_CREATEF]
        cmp     eax, -1
        je      .notrace
        push    eax
        call    dword [ebx + D_CLOSEH]
        cmp     dword [ebx + D_ODS], 0
        je      .notrace
        mov     dword [ebx + D_TRACE], 1
.notrace:
        pop     edi
        lea     esi, [ebx + S_TRACK]
        call    scat
        sub     edi, ebx
        sub     edi, D_PATH
        mov     [ebx + D_NNPOS], edi

        mov     ebp, 2                  ; track number; esi is scat's
.walk:
        mov     eax, ebp
        call    trackpath
        push    0
        push    0x80                    ; FILE_ATTRIBUTE_NORMAL
        push    3                       ; OPEN_EXISTING
        push    0
        push    1                       ; FILE_SHARE_READ
        push    0x80000000              ; GENERIC_READ
        lea     eax, [ebx + D_PATH]
        push    eax
        call    dword [ebx + D_CREATEF]
        cmp     eax, -1
        je      .next
        mov     edi, eax
        push    0
        push    edi
        call    dword [ebx + D_GETSIZE]
        push    eax
        push    edi
        call    dword [ebx + D_CLOSEH]
        pop     eax
        sub     eax, WAV_HEADER
        jbe     .next
        xor     edx, edx
        mov     ecx, 2352
        div     ecx
        mov     [ebx + D_TOC + ebp * 4], eax
        mov     [ebx + D_NTRACKS], ebp
.next:
        inc     ebp
        cmp     ebp, MAXTRACK
        jbe     .walk

        ; two auto-reset events, the callers' mutex and the worker;
        ; without them, no tracks
        push    0
        push    0
        push    0
        call    dword [ebx + D_CREATEMUT]
        mov     [ebx + D_HMUTEX], eax
        test    eax, eax
        jz      .nothread
        push    0
        push    0
        push    0
        push    0
        call    dword [ebx + D_CREATEEV]
        mov     [ebx + D_HREQ], eax
        push    0
        push    0
        push    0
        push    0
        call    dword [ebx + D_CREATEEV]
        mov     [ebx + D_HDONE], eax
        push    0
        push    0
        push    0
        lea     eax, [ebx + worker]
        push    eax
        push    0
        push    0
        call    dword [ebx + D_CREATETHR]
        test    eax, eax
        jz      .nothread
        cmp     dword [ebx + D_HREQ], 0
        je      .nothread
        cmp     dword [ebx + D_HDONE], 0
        jne     .done
.nothread:
        mov     dword [ebx + D_NTRACKS], 0
.done:
        popad
.chain:
        push    ebx
        call    getbase
        lea     eax, [ebx + MAGIC_ORIGENTRY]
        pop     ebx
        jmp     eax

; ------------------------------------------------------------------ data

align 4
D_INIT      dd 0
D_NTRACKS   dd 0                        ; highest track with a file
D_CUR       dd 0
D_OPEN      dd 0
D_SEEKMS    dd 0
D_NNPOS     dd 0                        ; where NN goes in D_PATH
D_ODS       dd 0                        ; OutputDebugStringA, or 0
D_TRACE     dd 0                        ; music\trace exists: report every command
D_TRC       times 96 db 0
D_VOL       dd 0                        ; the level, in hundredths of a dB; full until set
D_SLIDER    dd 0                        ; the slider's level, what a fade is a fraction of
D_FADING    dd 0                        ; a fade has started and no level has ended it
; 2000 log10(p / 100) for p = 0..100: an amplitude percentage in hundredths of a dB, 0 off.
S_PCTDB:
            dw -10000, -4000, -3398, -3046, -2796, -2602, -2444, -2310, -2194, -2092
            dw -2000, -1917, -1842, -1772, -1708, -1648, -1592, -1539, -1489, -1442
            dw -1398, -1356, -1315, -1277, -1240, -1204, -1170, -1137, -1106, -1075
            dw -1046, -1017, -990, -963, -937, -912, -887, -864, -840, -818
            dw -796, -774, -754, -733, -713, -694, -674, -656, -638, -620
            dw -602, -585, -568, -551, -535, -519, -504, -488, -473, -458
            dw -444, -429, -415, -401, -388, -374, -361, -348, -335, -322
            dw -310, -297, -285, -273, -262, -250, -238, -227, -216, -205
            dw -194, -183, -172, -162, -151, -141, -131, -121, -111, -101
            dw -92, -82, -72, -63, -54, -45, -35, -26, -18, -9
            dw 0
D_HREQ      dd 0
D_HDONE     dd 0
D_HMUTEX    dd 0
D_DS        dd 0                        ; IDirectSound, from the first open on
D_BUF       dd 0                        ; IDirectSoundBuffer, while a track is open
D_STATE     dd 0                        ; ST_IDLE, ST_PLAYING, ST_PAUSED
D_LASTHR    dd 0                        ; the last DirectSound result, for the trace
D_FILE      dd 0
D_MAP       dd 0
D_VIEW      dd 0
D_DATASIZE  dd 0                        ; sample bytes in the open track
D_LOCK      times 4 dd 0                ; p1, n1, p2, n2 of the lock
D_STATUS    dd 0, 0                     ; GetStatus, GetCurrentPosition's two
D_DESC      dd 36, DSBCAPS, 0, 0, 0     ; DSBUFFERDESC: size, flags, bytes, reserved, format
            times 4 dd 0                ; guid3DAlgorithm, none
D_FMT       dw 1, 2                     ; WAVEFORMATEX: PCM, stereo
            dd 44100, BYTES_PER_SEC
            dw 4, 16, 0
D_TOC       times (MAXTRACK + 1) dd 0   ; frames per track
D_PATH      times PATHLEN db 0

; The imports, in S_MODULES order.
D_FN:
D_DSCREATE  dd 0
D_DESKTOP   dd 0
D_CREATEF   dd 0
D_GETSIZE   dd 0
D_CLOSEH    dd 0
D_CREATEMAP dd 0
D_MAPVIEW   dd 0
D_UNMAP     dd 0
D_CREATETHR dd 0
D_CREATEEV  dd 0
D_SETEVENT  dd 0
D_WAIT      dd 0
D_CREATEMUT dd 0
D_RELMUTEX  dd 0

S_MODULES   db 'dsound.dll', 0
            db 'DirectSoundCreate', 0, 0
            db 'user32.dll', 0
            db 'GetDesktopWindow', 0, 0
            db 'kernel32.dll', 0
            db 'CreateFileA', 0, 'GetFileSize', 0, 'CloseHandle', 0
            db 'CreateFileMappingA', 0, 'MapViewOfFile', 0
            db 'UnmapViewOfFile', 0, 'CreateThread', 0, 'CreateEventA', 0
            db 'SetEvent', 0, 'WaitForSingleObject', 0
            db 'CreateMutexA', 0, 'ReleaseMutex', 0, 0
            db 0
S_ODS       db 'OutputDebugStringA', 0
S_TRACK     db 'music\track', 0
S_TRACEF    db 'music\trace', 0
S_TRACE     db 'sr2 ', 0
S_OPTRACE   db 'sr2 op ', 0
S_WAV       db '.wav', 0

; Last, at known offsets from the end, so the check can find them:
; D_OP at -12, D_ARG at -8, D_RESULT at -4.
align 4
D_OP        dd 0
D_ARG       dd 0
D_RESULT    dd 0
