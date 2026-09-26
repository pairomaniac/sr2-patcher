; starting.asm - a line on the team room while the race is set up.
;
; START calls the race setup (0x438dc0), which spins on timeGetTime -
; up to 15 s for every racer's state, a guest's stagger, the clock sync,
; the second wait - drawing nothing, so the screen holds the room's last
; frame and the game looks stuck. This is called in place of that call,
; from the host's START and the guest's on the host's word: it writes
; a line across the status strip's row of the room's background (the
; surface the strip's `IP Address :` went on, its own font, the row
; cleared to the pixel colour found there), draws the room into the back
; buffer through its own draw and presents it as the frame gate would,
; then goes on to the setup, which returns to the site. Without gdi32,
; a surface or a DC it goes straight to the setup.
;
; Placeholders the patcher fills from the build's row: the room's
; surface table (ROOMBG, entry 0 the background) and its size table
; (ROOMSIZE, entry 0 the width), the lobby's font (ROOMFONT), the room's
; draw (ROOMDRAW), the setup (RACESETUP), MGameD3D's object (GAMED3D),
; and LoadLibraryA's and GetProcAddress's import slots.

bits 32

%define ROOMBG          0xBBBBBBBB      ; placeholders, EXE_MAGICS
%define ROOMSIZE        0xBCBCBCBC
%define ROOMFONT        0xBDBDBDBD
%define ROOMDRAW        0xBEBEBEBE
%define RACESETUP       0xBFBFBFBF
%define GAMED3D         0xEAEAEAEA
%define LOADLIB         0xE3E3E3E3
%define GETPROC         0xE4E4E4E4

%define LINE_Y          456             ; the status strip's row
%define OPAQUE          2               ; SetBkMode, and ETO_OPAQUE
%define S_GETDC         0x28            ; the exe's surface wrapper: GetDC(this, &hdc), ReleaseDC(this, hdc), stdcall
%define S_RELEASEDC     0x2c
%define D_PRESENT       0x80            ; MGameD3D: the present and what the gate calls after it
%define D_AFTER         0x88
%define NFUNCS          7

; the frame, esi = its base
%define f_hdc           0
%define f_cx            4
%define f_cy            8
%define f_rect          12
%define FRAME           28

        push    ebx
        push    esi
        push    edi
        push    ebp
        sub     esp, FRAME
        mov     esi, esp
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob

        cmp     dword [ebp + funcs + (NFUNCS - 1) * 4], 0   ; the last slot: all resolved, or not yet
        jne     .ready
        lea     eax, [ebp + gdi32]
        push    eax
        call    [LOADLIB]
        test    eax, eax
        jz      .setup
        mov     ebx, eax
        xor     edi, edi
.resolve:
        mov     eax, [ebp + names + edi * 4]
        add     eax, ebp
        push    eax
        push    ebx
        call    [GETPROC]
        test    eax, eax
        jz      .setup                  ; one missing: the last slot stays 0, tried again next time
        mov     [ebp + funcs + edi * 4], eax
        inc     edi
        cmp     edi, NFUNCS
        jb      .resolve

.ready: mov     eax, [ROOMBG]
        test    eax, eax
        jz      .setup
        mov     edx, [eax]
        lea     ecx, [esi + f_hdc]
        push    ecx
        push    eax
        call    [edx + S_GETDC]
        mov     ebx, [esi + f_hdc]
        test    ebx, ebx
        jz      .setup

        push    dword [ROOMFONT]
        push    ebx
        call    [ebp + funcs + F_SELECTOBJECT * 4]
        push    -1                      ; the strip's own colour word
        push    ebx
        call    [ebp + funcs + F_SETTEXTCOLOR * 4]
        push    LINE_Y + 2              ; the row's own colour, from a pixel on it: the row cleared to it
        push    2
        push    ebx
        call    [ebp + funcs + F_GETPIXEL * 4]
        push    eax
        push    ebx
        call    [ebp + funcs + F_SETBKCOLOR * 4]
        push    OPAQUE
        push    ebx
        call    [ebp + funcs + F_SETBKMODE * 4]
        lea     eax, [esi + f_cx]
        push    eax
        push    MSGLEN
        lea     eax, [ebp + msg]
        push    eax
        push    ebx
        call    [ebp + funcs + F_GETTEXTEXTENT * 4]
        mov     eax, [ROOMSIZE]         ; the width; the line centred on it
        mov     edi, eax
        sub     eax, [esi + f_cx]
        sar     eax, 1
        mov     dword [esi + f_rect], 0         ; the row, edge to edge: whatever was there goes
        mov     dword [esi + f_rect + 4], LINE_Y
        mov     [esi + f_rect + 8], edi
        mov     ecx, [esi + f_cy]
        add     ecx, LINE_Y
        mov     [esi + f_rect + 12], ecx
        push    0                       ; lpDx
        push    MSGLEN
        lea     ecx, [ebp + msg]
        push    ecx
        lea     ecx, [esi + f_rect]
        push    ecx
        push    OPAQUE                  ; ETO_OPAQUE
        push    LINE_Y
        push    eax
        push    ebx
        call    [ebp + funcs + F_EXTTEXTOUT * 4]

        mov     eax, [ROOMBG]
        mov     edx, [eax]
        push    ebx
        push    eax
        call    [edx + S_RELEASEDC]

        mov     eax, ROOMDRAW           ; the room into the back buffer, as the frame's draw would
        call    eax
        mov     eax, [GAMED3D]
        test    eax, eax
        jz      .setup
        mov     edx, [eax]
        push    eax
        call    [edx + D_PRESENT]       ; and presented, as the gate would
        mov     eax, [GAMED3D]
        mov     edx, [eax]
        push    eax
        call    [edx + D_AFTER]

.setup: add     esp, FRAME
        pop     ebp
        pop     edi
        pop     esi
        pop     ebx
        mov     eax, RACESETUP
        jmp     eax                     ; the setup returns to the site

F_SELECTOBJECT  equ 0
F_SETTEXTCOLOR  equ 1
F_GETPIXEL      equ 2
F_SETBKCOLOR    equ 3
F_SETBKMODE     equ 4
F_GETTEXTEXTENT equ 5
F_EXTTEXTOUT    equ 6

align 4
funcs:  times NFUNCS dd 0
names:  dd n_selectobject, n_settextcolor, n_getpixel, n_setbkcolor, n_setbkmode, n_gettextextent, n_exttextout
gdi32:          db 'gdi32.dll', 0
n_selectobject: db 'SelectObject', 0
n_settextcolor: db 'SetTextColor', 0
n_getpixel:     db 'GetPixel', 0
n_setbkcolor:   db 'SetBkColor', 0
n_setbkmode:    db 'SetBkMode', 0
n_gettextextent: db 'GetTextExtentPoint32A', 0
n_exttextout:   db 'ExtTextOutA', 0
msg:            db 'STARTING - WAITING FOR THE OTHERS'
MSGLEN          equ $ - msg
                db 0
