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
; Playback is not implemented here: a CD command becomes an MCI string
; command against waveaudio, and the same MCI subsystem does the work.
;
; The BGM slider used to set the mixer's CD line, through a method that
; gives up without a mixer handle; its sibling reads the line back, and
; the exe divides that by 100 for the scale it sends the slider on. Both
; entries are pointed here: getvolume answers with the volume the blob
; holds, on the 0..10000 scale, and setvolume keeps what the game sends as
; a waveOut volume, scaled by GAIN so full slider sits where a CD line
; used to against the effects. mciwave opens the wave device on play, on
; its own thread, a moment after play returns, so after sending a play the
; worker retries the volume every few milliseconds until a handle takes
; it. Windows takes a device id for that, 0; Wine takes only the handles
; it made, built from indices - 0xFF00 for the first mapper stream,
; 0xC000 for the first on device 0 - so those are tried too, and a handle
; not in use fails.
;
; MGAudio talks to MCI from several short-lived threads, and Wine's winmm
; keeps an MCI device private to the thread that opened it. So every string
; command is issued by one worker thread created at startup: the hook
; writes D_CMD, signals D_HREQ and waits on D_HDONE; the worker sends the
; command, stores the result in D_RESULT and signals back.

bits 32

%define MAGIC_ORIGENTRY 0xE1E1E1E1      ; offset to the original entry point
%define MAGIC_IATMCI    0xE2E2E2E2      ; offset to the mciSendCommandA IAT slot
%define MAGIC_LOADLIB   0xE3E3E3E3      ; offset to the LoadLibraryA IAT slot
%define MAGIC_GETPROC   0xE4E4E4E4      ; offset to the GetProcAddress IAT slot
%define MAGIC_GETMODFN  0xE5E5E5E5      ; offset to the GetModuleFileNameA IAT slot

%define FAKE_ID         0xFACE
%define GAIN            32768           ; 0.5 of 65535: the level at full slider

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

%define MAXTRACK        99
%define PATHLEN         272
%define CMDLEN          512
%define RETLEN          32

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

; esi -> decimal text, eax = value.
getnum:
        xor     eax, eax
        xor     ecx, ecx
.next:
        mov     cl, [esi]
        sub     cl, '0'
        cmp     cl, 9
        ja      .done
        imul    eax, 10
        add     eax, ecx
        inc     esi
        jmp     .next
.done:
        ret

; Sends D_CMD as an MCI string command through the worker. eax = MCIERROR.
; ebx = base. The answer, if any, is in D_RET.
mcistr:
        push    dword [ebx + D_HREQ]
        call    dword [ebx + D_SETEVENT]
        push    -1                      ; INFINITE
        push    dword [ebx + D_HDONE]
        call    dword [ebx + D_WAIT]
        mov     eax, [ebx + D_RESULT]
        ret

; The worker thread: waits for a request, sends it, answers. Never returns.
worker:
        call    getbase
.loop:
        push    -1
        push    dword [ebx + D_HREQ]
        call    dword [ebx + D_WAIT]
        push    0
        push    RETLEN
        lea     eax, [ebx + D_RET]
        push    eax
        lea     eax, [ebx + D_CMD]
        push    eax
        call    dword [ebx + D_MCISTR]
        mov     [ebx + D_RESULT], eax
        push    dword [ebx + D_HDONE]
        call    dword [ebx + D_SETEVENT]
        cmp     dword [ebx + D_PLAYED], 0
        je      .loop
        mov     dword [ebx + D_PLAYED], 0
        cmp     dword [ebx + D_SLEEP], 0
        je      .loop
        mov     ecx, 100                ; up to 400 ms for the stream to appear
.settle:
        call    applyvol
        test    eax, eax
        jz      .loop
        push    ecx
        push    4
        call    dword [ebx + D_SLEEP]
        pop     ecx
        dec     ecx
        jnz     .settle
        jmp     .loop

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

; Opens track eax as sr2bgm. eax = 0 or MCIERROR.
opentrack:
        mov     [ebx + D_CUR], eax
        push    eax
        lea     edi, [ebx + D_CMD]
        lea     esi, [ebx + S_CLOSE]
        call    scat
        call    mcistr
        mov     dword [ebx + D_OPEN], 0
        pop     eax
        call    trackpath
        lea     edi, [ebx + D_CMD]
        lea     esi, [ebx + S_OPEN]
        call    scat
        lea     esi, [ebx + D_PATH]
        call    scat
        lea     esi, [ebx + S_OPEN2]
        call    scat
        call    mcistr
        test    eax, eax
        jnz     .out
        lea     edi, [ebx + D_CMD]
        lea     esi, [ebx + S_SETMS]
        call    scat
        call    mcistr
        mov     dword [ebx + D_OPEN], 1
        xor     eax, eax
.out:
        ret

; waveOutSetVolume(h, D_VOL) for every h in S_HANDLES. eax = 0 if any
; took it; other registers kept.
applyvol:
        mov     eax, -1
        cmp     dword [ebx + D_SETVOL], 0
        je      .none
        push    ecx
        push    edx
        push    esi
        push    edi
        mov     edi, -1
        lea     esi, [ebx + S_HANDLES]
.each:
        push    dword [ebx + D_VOL]
        push    dword [esi]
        call    dword [ebx + D_SETVOL]
        test    eax, eax
        jnz     .next
        xor     edi, edi
.next:
        add     esi, 4
        cmp     dword [esi], -1
        jne     .each
        mov     eax, edi
        pop     edi
        pop     esi
        pop     edx
        pop     ecx
.none:
        ret

; ------------------------------------------------- setvolume, getvolume
; Replace the CD-volume methods: stdcall (this, values, flags), where
; values is the game's struct - +8 the channel count, +0xc and +0x10 the
; channels, 0..10000. Both return S_OK; the mixer is never touched.

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
        mov     [ebx + D_VOL10K], eax
        imul    eax, eax, GAIN
        xor     edx, edx
        mov     ecx, 10000
        div     ecx
        mov     edx, eax
        shl     edx, 16
        or      eax, edx                ; both channels
        mov     [ebx + D_VOL], eax
        call    applyvol
.ok:
        xor     eax, eax
        pop     ebx
        ret     12

getvolume:
        push    ebx
        call    getbase
        mov     eax, [esp + 12]         ; values
        test    eax, eax
        jz      .ok
        mov     ecx, [ebx + D_VOL10K]
        mov     dword [eax + 8], 2
        mov     [eax + 12], ecx
        mov     [eax + 16], ecx
.ok:
        xor     eax, eax
        pop     ebx
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
        lea     esi, [ebx + S_CLOSE]
        call    .simple
        mov     dword [ebx + D_OPEN], 0
        jmp     .ok
.stop:
        lea     esi, [ebx + S_STOP]
        call    .simple
        jmp     .ok
.pause:
        lea     esi, [ebx + S_PAUSE]
        call    .simple
        jmp     .ok
.resume:
        lea     esi, [ebx + S_RESUME]
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
        push    ecx
        call    opentrack
        pop     ecx
        test    eax, eax
        jnz     .ret
        lea     edi, [ebx + D_CMD]
        lea     esi, [ebx + S_PLAY]
        call    scat
        test    ecx, ecx
        jz      .go
        lea     esi, [ebx + S_FROM]
        call    scat
        mov     eax, ecx
        call    putnum
.go:
        mov     dword [ebx + D_PLAYED], 1  ; the worker settles the volume after this one
        call    mcistr
        jmp     .ret
.range:
        mov     eax, MCIERR_OUTOFRANGE
        jmp     .ret

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
        jne     .seeklater
        lea     edi, [ebx + D_CMD]
        lea     esi, [ebx + S_SEEK]
        call    scat
        mov     eax, ecx
        call    putnum
        call    mcistr
        jmp     .ok
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
        mov     ecx, [ebx + D_CUR]
        xor     eax, eax
        cmp     dword [ebx + D_OPEN], 0
        je      .posdone
        lea     edi, [ebx + D_CMD]
        lea     esi, [ebx + S_POS]
        call    scat
        call    mcistr
        lea     esi, [ebx + D_RET]
        call    getnum
        mov     ecx, [ebx + D_CUR]
.posdone:
        call    ms_tmsf
        mov     edx, [ebp + 20]
        mov     [edx + 4], eax
        jmp     .ok

; esi -> a complete command. Sends it.
.simple:
        lea     edi, [ebx + D_CMD]
        call    scat
        call    mcistr
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

        lea     eax, [ebx + S_WINMM]
        push    eax
        call    dword [ebx + MAGIC_LOADLIB]
        test    eax, eax
        jz      .done
        mov     esi, eax
        lea     ecx, [ebx + S_MCISTR]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        test    eax, eax
        jz      .done
        mov     [ebx + D_MCISTR], eax
        lea     ecx, [ebx + S_SETVOL]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_SETVOL], eax   ; may be 0: then the slider does nothing

        lea     eax, [ebx + S_KERNEL]
        push    eax
        call    dword [ebx + MAGIC_LOADLIB]
        test    eax, eax
        jz      .done
        mov     esi, eax
        lea     ecx, [ebx + S_CREATEF]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_CREATEF], eax
        lea     ecx, [ebx + S_GETSIZE]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_GETSIZE], eax
        lea     ecx, [ebx + S_CLOSEH]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_CLOSEH], eax
        lea     ecx, [ebx + S_CREATETHR]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_CREATETHR], eax
        lea     ecx, [ebx + S_CREATEEV]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_CREATEEV], eax
        lea     ecx, [ebx + S_SETEVENT]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_SETEVENT], eax
        lea     ecx, [ebx + S_WAIT]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_WAIT], eax
        lea     ecx, [ebx + S_SLEEP]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_SLEEP], eax
        lea     ecx, [ebx + S_ODS]
        push    ecx
        push    esi
        call    dword [ebx + MAGIC_GETPROC]
        mov     [ebx + D_ODS], eax
        lea     esi, [ebx + D_CREATEF]  ; the seven resolved above, in a row
        mov     ecx, 7
.resolved:
        cmp     dword [esi], 0
        je      .done
        add     esi, 4
        dec     ecx
        jnz     .resolved

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
        sub     eax, 44
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

        ; two auto-reset events and the worker; without them, no tracks
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
D_MCISTR    dd 0
D_CREATEF   dd 0                        ; these seven are checked in a row
D_GETSIZE   dd 0
D_CLOSEH    dd 0
D_CREATETHR dd 0
D_CREATEEV  dd 0
D_SETEVENT  dd 0
D_WAIT      dd 0
D_HREQ      dd 0
D_HDONE     dd 0
D_SETVOL    dd 0                        ; waveOutSetVolume, or 0
D_SLEEP     dd 0                        ; Sleep
D_ODS       dd 0                        ; OutputDebugStringA
D_PLAYED    dd 0                        ; a play was just sent: settle the volume
D_TRACE     dd 0                        ; music\trace exists: report every command
D_TRC       times 96 db 0
D_VOL       dd GAIN | GAIN << 16        ; the slider, as a waveOut volume; full until set
D_VOL10K    dd 10000                    ; the same on the game's scale, for getvolume
S_HANDLES   dd 0                        ; Windows: device 0
            dd 0xFF00, 0xFF01           ; Wine: mapper streams 0 and 1
            dd 0xC000                   ; Wine: device 0 stream 0
            dd -1
D_TOC       times (MAXTRACK + 1) dd 0   ; frames per track
D_PATH      times PATHLEN db 0

S_WINMM     db 'winmm.dll', 0
S_MCISTR    db 'mciSendStringA', 0
S_SETVOL    db 'waveOutSetVolume', 0
S_KERNEL    db 'kernel32.dll', 0
S_CREATEF   db 'CreateFileA', 0
S_GETSIZE   db 'GetFileSize', 0
S_CLOSEH    db 'CloseHandle', 0
S_CREATETHR db 'CreateThread', 0
S_CREATEEV  db 'CreateEventA', 0
S_SETEVENT  db 'SetEvent', 0
S_WAIT      db 'WaitForSingleObject', 0
S_SLEEP     db 'Sleep', 0
S_ODS       db 'OutputDebugStringA', 0
S_TRACK     db 'music\track', 0
S_TRACEF    db 'music\trace', 0
S_TRACE     db 'sr2 ', 0
S_WAV       db '.wav', 0
S_CLOSE     db 'close sr2bgm', 0
S_OPEN      db 'open "', 0
S_OPEN2     db '" type waveaudio alias sr2bgm', 0
S_SETMS     db 'set sr2bgm time format milliseconds', 0
S_PLAY      db 'play sr2bgm', 0
S_FROM      db ' from ', 0
S_SEEK      db 'seek sr2bgm to ', 0
S_STOP      db 'stop sr2bgm', 0
S_PAUSE     db 'pause sr2bgm', 0
S_RESUME    db 'resume sr2bgm', 0
S_POS       db 'status sr2bgm position', 0

; Last, at known offsets from the end, so the check can find them:
; D_CMD at -(CMDLEN+RETLEN+4), D_RET at -(RETLEN+4), D_RESULT at -4.
align 4
D_CMD       times CMDLEN db 0
D_RET       times RETLEN db 0
D_RESULT    dd 0
