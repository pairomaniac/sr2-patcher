; starting.asm - a box on the team room while the race is set up.
;
; START calls the race setup (0x438dc0), which spins on timeGetTime -
; up to 15 s for every racer's state, a guest's stagger, the clock sync,
; the second wait - drawing nothing, so the screen holds the room's last
; frame and the game looks stuck. This is called in place of that call,
; from the host's START and the guest's on the host's word. It draws a
; box with two lines in the middle of the room's background surface
; (the one the strip's `IP Address :` went on, MGameD3D's wrapper: GetDC
; +0x28, ReleaseDC +0x2c, the target +0x34, the blit +0x1c; the surface
; is loaded afresh on every entry to the room, so the box stays in it
; harmlessly), blits that box alone onto the back buffer - through the
; widescreen patch's hook when it is there, so it lands on the room's
; last frame and not over it - presents as the frame gate would, then
; goes on to the setup, which returns to the site. Without gdi32, a
; surface or a DC it goes straight to the setup.
;
; Placeholders the patcher fills from the build's row: the room's
; surface table (ROOMBG, entry 0 the background) and its size table
; (ROOMSIZE, entry 0 width and height), the lobby's font (ROOMFONT),
; the setup (RACESETUP), MGameD3D's object (GAMED3D), and LoadLibraryA's
; and GetProcAddress's import slots.

bits 32

%define ROOMBG          0xBBBBBBBB      ; placeholders, EXE_MAGICS
%define ROOMSIZE        0xBCBCBCBC
%define ROOMFONT        0xBDBDBDBD
%define RACESETUP       0xBFBFBFBF
%define GAMED3D         0xEAEAEAEA
%define LOADLIB         0xE3E3E3E3
%define GETPROC         0xE4E4E4E4

%define OPAQUE          2               ; SetBkMode, and ETO_OPAQUE
%define TRANSPARENT     1
%define TEXT            0x00ffffff      ; COLORREFs: the lines, the border, the box
%define BORDER          0x00c8c8c8
%define BOX             0x00462814      ; a dark blue; never black, which a keyed blit would drop
%define PAD_X           28              ; the box around the wider line
%define PAD_Y           14
%define GAP             6               ; between the lines
%define EDGE            2               ; the border
%define S_BLIT          0x1c            ; the wrapper: Blit(this, x, y, &rect), stdcall
%define S_GETDC         0x28            ; GetDC(this, &hdc), ReleaseDC(this, hdc)
%define S_RELEASEDC     0x2c
%define S_TARGET        0x34            ; SetTarget(this, surface or 0 for the back buffer)
%define D_PRESENT       0x80            ; MGameD3D: the present and what the gate calls after it
%define D_AFTER         0x88
%define NFUNCS          6

; the frame, esi = its base
%define f_hdc           0
%define f_cx1           4
%define f_cy1           8
%define f_cx2           12
%define f_cy2           16
%define f_outer         20              ; left, top, right, bottom
%define f_inner         36
%define FRAME           52

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
        lea     eax, [esi + f_cx1]      ; the two lines' extents
        push    eax
        push    LEN1
        lea     eax, [ebp + line1]
        push    eax
        push    ebx
        call    [ebp + funcs + F_GETTEXTEXTENT * 4]
        lea     eax, [esi + f_cx2]
        push    eax
        push    LEN2
        lea     eax, [ebp + line2]
        push    eax
        push    ebx
        call    [ebp + funcs + F_GETTEXTEXTENT * 4]

        ; the box: the wider line plus the padding, centred on the surface
        mov     eax, [esi + f_cx1]
        cmp     eax, [esi + f_cx2]
        jae     .wide
        mov     eax, [esi + f_cx2]
.wide:  add     eax, PAD_X * 2          ; the width
        mov     ecx, [esi + f_cy1]
        add     ecx, [esi + f_cy2]
        add     ecx, GAP + PAD_Y * 2    ; the height
        mov     edx, ROOMSIZE
        mov     edi, [edx + 4]          ; the surface's height
        mov     edx, [edx]              ; and width: left = (width - w) / 2
        sub     edx, eax
        sar     edx, 1
        mov     [esi + f_outer], edx
        add     edx, eax
        mov     [esi + f_outer + 8], edx
        mov     edx, edi                ; top = (height - h) / 2
        sub     edx, ecx
        sar     edx, 1
        mov     [esi + f_outer + 4], edx
        add     edx, ecx
        mov     [esi + f_outer + 12], edx
        mov     eax, [esi + f_outer]    ; the inner rect, EDGE in from the outer
        add     eax, EDGE
        mov     [esi + f_inner], eax
        mov     eax, [esi + f_outer + 4]
        add     eax, EDGE
        mov     [esi + f_inner + 4], eax
        mov     eax, [esi + f_outer + 8]
        sub     eax, EDGE
        mov     [esi + f_inner + 8], eax
        mov     eax, [esi + f_outer + 12]
        sub     eax, EDGE
        mov     [esi + f_inner + 12], eax

        push    OPAQUE
        push    ebx
        call    [ebp + funcs + F_SETBKMODE * 4]
        push    BORDER                  ; the border: the outer rect filled
        push    ebx
        call    [ebp + funcs + F_SETBKCOLOR * 4]
        lea     eax, [esi + f_outer]
        call    fill
        push    BOX                     ; the box: the inner rect filled
        push    ebx
        call    [ebp + funcs + F_SETBKCOLOR * 4]
        lea     eax, [esi + f_inner]
        call    fill
        push    TRANSPARENT
        push    ebx
        call    [ebp + funcs + F_SETBKMODE * 4]
        push    TEXT
        push    ebx
        call    [ebp + funcs + F_SETTEXTCOLOR * 4]
        mov     edi, [esi + f_outer + 4]
        add     edi, PAD_Y              ; the first line's top
        lea     eax, [ebp + line1]
        mov     ecx, LEN1
        mov     edx, [esi + f_cx1]
        call    line
        add     edi, [esi + f_cy1]
        add     edi, GAP                ; the second's
        lea     eax, [ebp + line2]
        mov     ecx, LEN2
        mov     edx, [esi + f_cx2]
        call    line

        mov     eax, [ROOMBG]
        mov     edx, [eax]
        push    ebx
        push    eax
        call    [edx + S_RELEASEDC]

        mov     eax, [ROOMBG]           ; the box alone onto the back buffer, at its place
        mov     edx, [eax]
        push    0
        push    eax
        call    [edx + S_TARGET]
        mov     eax, [ROOMBG]
        mov     edx, [eax]
        lea     ecx, [esi + f_outer]
        push    ecx
        push    dword [esi + f_outer + 4]
        push    dword [esi + f_outer]
        push    eax
        call    [edx + S_BLIT]
        mov     eax, [GAMED3D]
        test    eax, eax
        jz      .setup
        mov     edx, [eax]
        push    eax
        call    [edx + D_PRESENT]       ; presented, as the gate would
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

; eax = a rect: filled with the background colour (ExtTextOut of nothing, opaque).
fill:   push    0
        push    0
        push    eax                     ; the text: none, so eax will do for its address
        push    eax
        push    OPAQUE
        push    0
        push    0
        push    ebx
        call    [ebp + funcs + F_EXTTEXTOUT * 4]
        ret

; eax = the text, ecx = its length, edx = its width, edi = its top: written centred.
line:   push    0
        push    ecx
        push    eax
        push    0
        push    0
        push    edi
        mov     eax, ROOMSIZE
        mov     eax, [eax]
        sub     eax, edx
        sar     eax, 1
        push    eax
        push    ebx
        call    [ebp + funcs + F_EXTTEXTOUT * 4]
        ret

F_SELECTOBJECT  equ 0
F_SETTEXTCOLOR  equ 1
F_SETBKCOLOR    equ 2
F_SETBKMODE     equ 3
F_GETTEXTEXTENT equ 4
F_EXTTEXTOUT    equ 5

align 4
funcs:  times NFUNCS dd 0
names:  dd n_selectobject, n_settextcolor, n_setbkcolor, n_setbkmode, n_gettextextent, n_exttextout
gdi32:          db 'gdi32.dll', 0
n_selectobject: db 'SelectObject', 0
n_settextcolor: db 'SetTextColor', 0
n_setbkcolor:   db 'SetBkColor', 0
n_setbkmode:    db 'SetBkMode', 0
n_gettextextent: db 'GetTextExtentPoint32A', 0
n_exttextout:   db 'ExtTextOutA', 0
line1:          db 'STARTING THE RACE'
LEN1            equ $ - line1
line2:          db 'WAITING FOR THE OTHER PLAYERS'
LEN2            equ $ - line2
                db 0
