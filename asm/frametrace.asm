; frametrace.asm - a diagnostic: every drawn frame logged to logs\frames.log.
;
; The frame gate (0x4287f0 in the European exe) is entered after the
; game's own work on the frame, presents, catches up with extra steps of
; the simulation if it ran late, spins out the rest of 1/60 s, and ends by
; taking the counter into eax and storing it as the frame's time; ebx
; holds the steps, 1 unless it ran late. Its first five bytes jump to
; `entry`, which takes the counter through the game's own routine and
; keeps it; its last five before `pop ebx; ret` jump to `trace`, which
; appends one line per frame, "<entry> <blit> <exit> <steps> <flags>",
; to logs\frames.log in the game folder - the folder made on the first
; frame - opened then with a header
; "budget <ticks> qpc <0|1>" from the timer object in esi: the ticks per
; 1/60 s, and whether the counter is QueryPerformanceCounter or
; timeGetTime. Blit is the counter after the borderless present's blit,
; read from fullwin.asm's data, found through the jump the borderless
; patch put at MGameD3D's present.
; The flags are the four the gate reads, as bits: 1 running, 2 paused,
; 4 the debug DLL, 8 catch-up allowed (clear on the first tick of a
; scene). tools/frames.py reads it. Applied by name only; the annex is
; writable for the handle.
;
; IAT_LOADLIB and IAT_GETPROC are the usual placeholders; the four flags
; are kept as pointers in the data. 0xE7E7E7E1 and 0xE7E7E7E2 are dwords
; after the blob the patcher fills with the counter routine's address and
; the gate's sixth byte; 0xE7E7E7E3 it replaces with the stamp's offset
; from the present. kernel32's GetModuleHandleA, GetModuleFileNameA,
; CreateDirectoryA, CreateFileA and WriteFile and user32's wsprintfA are
; resolved once. If anything fails
; the handle is -1 and nothing is logged.

bits 32

%define IAT_LOADLIB     0xE3E3E3E3
%define IAT_GETPROC     0xE4E4E4E4
%define RUNNING         0xF3F3F3F3      ; the four flags the gate reads
%define PAUSED          0xF4F4F4F4
%define DEBUGDLL        0xF5F5F5F5
%define CATCHUP         0xF6F6F6F6
%define SITE1           0xE7E7E7E1      ; the patcher's per-site placeholders (build.py's SITE_MAGICS)
%define SITE2           0xE7E7E7E2
%define SITE3           0xE7E7E7E3
%define PRESENT         0x4d7b          ; MGameD3D's windowed present, RVA

%define MAX_PATH        260
%define PATHBUF         MAX_PATH + 24   ; room for logs\ and the name after the directory
%define GENERIC_WRITE   0x40000000
%define FILE_SHARE_READ 1
%define CREATE_ALWAYS   2
%define FILE_ATTRIBUTE_NORMAL 0x80

        jmp     near trace              ; +0, from the gate's exit
        jmp     near entry              ; +5, from its first instruction

; The gate's first instruction, `mov eax, [RUNNING]`, with ecx = the timer
; object. The counter kept for the line.
entry:
        push    ecx
        push    edx
        call    dword [SITE1]      ; the game's own counter routine
        call    .here
.here:  pop     edx
        sub     edx, .here
        mov     [edx + t_entry], eax
        mov     eax, [edx + p_running]
        mov     eax, [eax]              ; the displaced `mov eax, [RUNNING]`
        pop     edx
        pop     ecx
        jmp     dword [SITE2]

; Entered with eax = the counter, ebx = the steps, esi = the timer
; object, and ebx, esi, edi pushed by the gate. Leaves as the gate did.
trace:
        pushad
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob
        mov     ecx, [ebp + handle]
        test    ecx, ecx
        jnz     .opened
        push    dword [esi + 0x28]      ; qpc
        push    dword [esi + 0x24]      ; budget
        call    open
        add     esp, 8
        mov     ecx, [ebp + handle]
.opened:
        cmp     ecx, -1
        je      .done
        xor     edx, edx                ; the flags, catch-up down to running
        mov     ecx, [ebp + p_catchup]
        cmp     dword [ecx], 0
        setne   dl
        mov     ecx, [ebp + p_debugdll]
        cmp     dword [ecx], 0
        setne   cl
        movzx   ecx, cl
        lea     edx, [edx * 2 + ecx]
        mov     ecx, [ebp + p_paused]
        cmp     dword [ecx], 0
        setne   cl
        movzx   ecx, cl
        lea     edx, [edx * 2 + ecx]
        mov     ecx, [ebp + p_running]
        cmp     dword [ecx], 0
        setne   cl
        movzx   ecx, cl
        lea     edx, [edx * 2 + ecx]
        sub     esp, 96                 ; line [esp], up to 57 bytes; written [esp+80]
        mov     edi, esp
        push    edx
        push    dword [esp + 4 + 96 + 16]   ; ebx as pushad saved it
        push    dword [esp + 8 + 96 + 28]   ; eax, the exit
        xor     ecx, ecx
        mov     edx, [ebp + p_dll]
        test    edx, edx
        jz      .stamp
        mov     ecx, [edx]              ; after the blit
.stamp:
        push    ecx
        push    dword [ebp + t_entry]
        lea     eax, [ebp + s_line]
        push    eax
        push    edi
        call    [ebp + pfmt]            ; wsprintfA, cdecl, returns the length
        add     esp, 28
        push    0
        lea     ecx, [esp + 4 + 80]
        push    ecx
        push    eax
        push    edi
        push    dword [ebp + handle]
        call    [ebp + pwrite]          ; WriteFile, stdcall
        add     esp, 96
.done:
        popad
        pop     edi
        mov     [esi + 0x1c], eax
        pop     esi
        pop     ebx
        ret

; (budget, qpc) on the stack. Resolves the four entry points, opens the
; file and writes the header, or leaves the handle -1.
; Frame: path [esp], written [esp+PATHBUF], LoadLibraryA [esp+PATHBUF+4];
; budget [esp+PATHBUF+24], qpc [esp+PATHBUF+28] past the three saved
; registers and the return. ebx = GetProcAddress, esi = kernel32.
open:
        push    ebx
        push    esi
        push    edi
        sub     esp, PATHBUF + 8
        mov     dword [ebp + handle], -1
        mov     ebx, [IAT_GETPROC]
        mov     eax, [IAT_LOADLIB]
        mov     [esp + PATHBUF + 4], eax
        lea     eax, [ebp + s_k32]
        push    eax
        call    [esp + 4 + PATHBUF + 4]
        test    eax, eax
        jz      .out
        mov     esi, eax
        lea     eax, [ebp + s_writefile]
        push    eax
        push    esi
        call    ebx
        test    eax, eax
        jz      .out
        mov     [ebp + pwrite], eax
        lea     eax, [ebp + s_user32]
        push    eax
        call    [esp + 4 + PATHBUF + 4]
        test    eax, eax
        jz      .out
        lea     ecx, [ebp + s_wsprintf]
        push    ecx
        push    eax
        call    ebx
        test    eax, eax
        jz      .out
        mov     [ebp + pfmt], eax
        lea     eax, [ebp + s_getmodhandle] ; fullwin.asm's stamp, through the present's jump
        push    eax
        push    esi
        call    ebx
        test    eax, eax
        jz      .nodll
        lea     ecx, [ebp + s_gamed3d]
        push    ecx
        call    eax
        test    eax, eax
        jz      .nodll
        cmp     byte [eax + PRESENT], 0xe9   ; the borderless present's jump into its blob
        jne     .nodll
        mov     ecx, [eax + PRESENT + 1]
        lea     eax, [eax + ecx + SITE3]  ; PRESENT + 5 + the stamp's offset in the blob
        mov     [ebp + p_dll], eax
.nodll:
        lea     eax, [ebp + s_getmodfn]
        push    eax
        push    esi
        call    ebx
        test    eax, eax
        jz      .out
        push    MAX_PATH
        lea     ecx, [esp + 4]
        push    ecx
        push    0
        call    eax                     ; GetModuleFileNameA(NULL, path, MAX_PATH)
        test    eax, eax
        jz      .out
        lea     edi, [esp + eax]        ; after the last backslash, or the start
.back:  cmp     edi, esp
        je      .name
        dec     edi
        cmp     byte [edi], '\'
        jne     .back
        inc     edi
.name:  lea     ecx, [ebp + s_dir]
        call    copy
        lea     eax, [ebp + s_createdir]
        push    eax
        push    esi
        call    ebx
        test    eax, eax
        jz      .out
        push    0
        lea     ecx, [esp + 4]
        push    ecx
        call    eax                     ; CreateDirectoryA(path, NULL); exists is fine
        mov     byte [edi - 1], '\'
        lea     ecx, [ebp + s_name]
        call    copy
        lea     eax, [ebp + s_createfile]
        push    eax
        push    esi
        call    ebx
        test    eax, eax
        jz      .out
        push    0
        push    FILE_ATTRIBUTE_NORMAL
        push    CREATE_ALWAYS
        push    0
        push    FILE_SHARE_READ
        push    GENERIC_WRITE
        lea     ecx, [esp + 24]
        push    ecx
        call    eax                     ; CreateFileA
        cmp     eax, -1
        je      .out
        mov     [ebp + handle], eax
        mov     edi, eax
        push    dword [esp + PATHBUF + 28]  ; qpc
        push    dword [esp + 4 + PATHBUF + 24]  ; budget
        lea     eax, [ebp + s_head]
        push    eax
        lea     eax, [esp + 12]         ; the path buffer, done with
        push    eax
        call    [ebp + pfmt]
        add     esp, 16
        push    0
        lea     ecx, [esp + 4 + PATHBUF]
        push    ecx
        push    eax
        lea     eax, [esp + 12]
        push    eax
        push    edi
        call    [ebp + pwrite]
.out:
        add     esp, PATHBUF + 8
        pop     edi
        pop     esi
        pop     ebx
        ret

; The string at ecx to edi, its terminator included; edi left after it.
copy:   mov     al, [ecx]
        mov     [edi], al
        inc     ecx
        inc     edi
        test    al, al
        jnz     copy
        ret

handle:         dd 0                    ; 0 not opened, -1 failed
pwrite:         dd 0
pfmt:           dd 0
t_entry:        dd 0                    ; the counter at the gate's entry
p_dll:          dd 0                    ; fullwin.asm's stamp, or 0
p_running:      dd RUNNING              ; the four flags
p_paused:       dd PAUSED
p_debugdll:     dd DEBUGDLL
p_catchup:      dd CATCHUP
s_k32:          db 'kernel32.dll', 0
s_user32:       db 'user32.dll', 0
s_getmodfn:     db 'GetModuleFileNameA', 0
s_getmodhandle: db 'GetModuleHandleA', 0
s_gamed3d:      db 'MGameD3D.dll', 0
s_createdir:    db 'CreateDirectoryA', 0
s_createfile:   db 'CreateFileA', 0
s_dir:          db 'logs', 0
s_writefile:    db 'WriteFile', 0
s_wsprintf:     db 'wsprintfA', 0
s_name:         db 'frames.log', 0
s_head:         db 'budget %u qpc %u', 13, 10, 0
s_line:         db '%u %u %u %u %u', 13, 10, 0
