; fullwin.asm - the windowed mode filling the monitor.
;
; MGameD3D's windowed path sizes the window to the 640x480 it draws
; (MoveWindow at 0x100026be) and presents by blitting the back buffer to
; the window's client rect (0x10004d7b). Two thunks, in a section the
; patcher appends to the DLL:
;
;   +0  present     the client rect, letterboxed to the back buffer's
;                   aspect; the bars filled black, the picture blitted
;                   into the middle. Jumped to from 0x10004d7b, which had
;                   already made its 16-byte frame; leaves through that
;                   frame's `ret 4`.
;   +5  sizewindow  MoveWindow's stdcall shape: the window is moved to
;                   cover the monitor under the cursor, or where the game
;                   asked if user32 will not say. Called from 0x100026be.
;
; The window class is WS_POPUP, so a window the size of its monitor is
; what Wine and Windows treat as fullscreen, with no display mode change
; behind it.
;
; The DLL is relocated on every load. The blob finds its own address with
; a call/pop and subtracts its RVA, filled in by the patcher, to get the
; image base; the DLL's globals and import slots are RVAs from there.

bits 32

%define MAGIC_SELFRVA   0xE7E7E7E7      ; this blob's RVA, filled at apply time

; RVAs in MGameD3D.dll
%define HWND            0x123f8
%define PRIMARY         0x12550         ; IDirectDrawSurface4*
%define BACK            0x12554
%define SRCRECT         0x12410         ; 0, 0, width, height
%define LASTHR          0x11fc4
%define IAT_GETCLIENTRECT   0xf140
%define IAT_CLIENTTOSCREEN  0xf13c
%define IAT_MOVEWINDOW      0xf12c
%define IAT_LOADLIB         0xf114
%define IAT_GETPROC         0xf0ac

%define BLT             0x14            ; IDirectDrawSurface4::Blt
%define DDBLT_COLORFILL 0x400
%define DDBLT_WAIT      0x1000000
%define MONITOR_DEFAULTTONEAREST 2

        jmp     near present            ; +0
        jmp     near sizewindow         ; +5

; ebx = image base, esi = this blob, on return.
getbase:
        call    .here
.here:  pop     ebx
        sub     ebx, .here
        mov     esi, ebx
        sub     ebx, MAGIC_SELFRVA
        ret

; ------------------------------------------------------------- present
; Frame: rc [ebp-0x10], dest [ebp-0x20], bar [ebp-0x30], sw/sh/dw/dh
; [ebp-0x40..-0x4c], DDBLTFX (100 bytes) [ebp-0xb0].
present:
        push    ebp
        mov     ebp, esp
        sub     esp, 0xb0
        push    ebx
        push    esi
        push    edi
        call    getbase
        lea     eax, [ebp - 0x10]
        push    eax
        push    dword [ebx + HWND]
        call    [ebx + IAT_GETCLIENTRECT]
        lea     eax, [ebp - 0x10]
        push    eax
        push    dword [ebx + HWND]
        call    [ebx + IAT_CLIENTTOSCREEN]
        lea     eax, [ebp - 0x08]
        push    eax
        push    dword [ebx + HWND]
        call    [ebx + IAT_CLIENTTOSCREEN]
        mov     esi, [ebp - 0x08]       ; cw
        sub     esi, [ebp - 0x10]
        mov     edi, [ebp - 0x04]       ; ch
        sub     edi, [ebp - 0x0c]
        mov     ecx, [ebx + SRCRECT + 8]
        sub     ecx, [ebx + SRCRECT]
        mov     [ebp - 0x40], ecx       ; sw
        mov     edx, [ebx + SRCRECT + 12]
        sub     edx, [ebx + SRCRECT + 4]
        mov     [ebp - 0x44], edx       ; sh
        mov     eax, esi
        imul    eax, edx                ; cw * sh
        mov     ecx, edi
        imul    ecx, [ebp - 0x40]       ; ch * sw
        cmp     eax, ecx
        jb      .bywidth
        mov     [ebp - 0x4c], edi       ; dh = ch
        mov     eax, ecx
        xor     edx, edx
        div     dword [ebp - 0x44]
        mov     [ebp - 0x48], eax       ; dw = ch * sw / sh
        jmp     .fit
.bywidth:
        mov     [ebp - 0x48], esi       ; dw = cw
        xor     edx, edx
        div     dword [ebp - 0x40]
        mov     [ebp - 0x4c], eax       ; dh = cw * sh / sw
.fit:
        mov     eax, esi
        sub     eax, [ebp - 0x48]
        shr     eax, 1
        add     eax, [ebp - 0x10]
        mov     [ebp - 0x20], eax       ; dest.left
        add     eax, [ebp - 0x48]
        mov     [ebp - 0x18], eax       ; dest.right
        mov     eax, edi
        sub     eax, [ebp - 0x4c]
        shr     eax, 1
        add     eax, [ebp - 0x0c]
        mov     [ebp - 0x1c], eax       ; dest.top
        add     eax, [ebp - 0x4c]
        mov     [ebp - 0x14], eax       ; dest.bottom

        lea     edi, [ebp - 0xb0]       ; DDBLTFX, fill colour 0
        xor     eax, eax
        mov     ecx, 25
        rep stosd
        mov     dword [ebp - 0xb0], 100

        mov     eax, [ebp - 0x10]       ; top bar: l, t, r, dest.top
        mov     [ebp - 0x30], eax
        mov     eax, [ebp - 0x0c]
        mov     [ebp - 0x2c], eax
        mov     eax, [ebp - 0x08]
        mov     [ebp - 0x28], eax
        mov     eax, [ebp - 0x1c]
        mov     [ebp - 0x24], eax
        call    fillbar
        mov     eax, [ebp - 0x14]       ; bottom bar: l, dest.bottom, r, b
        mov     [ebp - 0x2c], eax
        mov     eax, [ebp - 0x04]
        mov     [ebp - 0x24], eax
        call    fillbar
        mov     eax, [ebp - 0x1c]       ; left bar: l, dest.top, dest.left, dest.bottom
        mov     [ebp - 0x2c], eax
        mov     eax, [ebp - 0x20]
        mov     [ebp - 0x28], eax
        mov     eax, [ebp - 0x14]
        mov     [ebp - 0x24], eax
        call    fillbar
        mov     eax, [ebp - 0x18]       ; right bar: dest.right, dest.top, r, dest.bottom
        mov     [ebp - 0x30], eax
        mov     eax, [ebp - 0x08]
        mov     [ebp - 0x28], eax
        call    fillbar

        mov     eax, [ebx + PRIMARY]
        mov     ecx, [eax]
        push    0
        push    DDBLT_WAIT
        lea     edx, [ebx + SRCRECT]
        push    edx
        push    dword [ebx + BACK]
        lea     edx, [ebp - 0x20]
        push    edx
        push    eax
        call    [ecx + BLT]
        mov     [ebx + LASTHR], eax
        pop     edi
        pop     esi
        pop     ebx
        mov     esp, ebp
        pop     ebp
        add     esp, 0x10               ; the frame 0x10004d55 made
        ret     4

; The bar at [ebp-0x30] filled black on the primary, if it has any area.
fillbar:
        mov     eax, [ebp - 0x28]
        cmp     eax, [ebp - 0x30]
        jle     .skip
        mov     eax, [ebp - 0x24]
        cmp     eax, [ebp - 0x2c]
        jle     .skip
        mov     eax, [ebx + PRIMARY]
        mov     ecx, [eax]
        lea     edx, [ebp - 0xb0]
        push    edx
        push    DDBLT_COLORFILL | DDBLT_WAIT
        push    0
        push    0
        lea     edx, [ebp - 0x30]
        push    edx
        push    eax
        call    [ecx + BLT]
.skip:
        ret

; ---------------------------------------------------------- sizewindow
; stdcall (hwnd, x, y, w, h, repaint).
; Frame: hmonitor [ebp-0x34], POINT [ebp-0x30], MONITORINFO [ebp-0x28]
; (rcMonitor at [ebp-0x24]).
sizewindow:
        push    ebp
        mov     ebp, esp
        sub     esp, 0x40
        push    ebx
        push    esi
        push    edi
        call    getbase
        lea     eax, [esi + s_user32]
        push    eax
        call    [ebx + IAT_LOADLIB]
        test    eax, eax
        jz      .asasked
        mov     edi, eax
        lea     eax, [esi + s_getcursorpos]
        push    eax
        push    edi
        call    [ebx + IAT_GETPROC]
        test    eax, eax
        jz      .asasked
        lea     ecx, [ebp - 0x30]
        push    ecx
        call    eax
        test    eax, eax
        jz      .asasked
        lea     eax, [esi + s_monitorfrompoint]
        push    eax
        push    edi
        call    [ebx + IAT_GETPROC]
        test    eax, eax
        jz      .asasked
        push    MONITOR_DEFAULTTONEAREST
        push    dword [ebp - 0x2c]
        push    dword [ebp - 0x30]
        call    eax
        test    eax, eax
        jz      .asasked
        mov     [ebp - 0x34], eax
        lea     eax, [esi + s_getmonitorinfo]
        push    eax
        push    edi
        call    [ebx + IAT_GETPROC]
        test    eax, eax
        jz      .asasked
        mov     dword [ebp - 0x28], 40
        lea     ecx, [ebp - 0x28]
        push    ecx
        push    dword [ebp - 0x34]
        call    eax
        test    eax, eax
        jz      .asasked
        push    1
        mov     eax, [ebp - 0x18]
        sub     eax, [ebp - 0x20]
        push    eax                     ; height
        mov     eax, [ebp - 0x1c]
        sub     eax, [ebp - 0x24]
        push    eax                     ; width
        push    dword [ebp - 0x20]      ; top
        push    dword [ebp - 0x24]      ; left
        push    dword [ebp + 8]
        call    [ebx + IAT_MOVEWINDOW]
        jmp     .done
.asasked:
        push    dword [ebp + 0x1c]
        push    dword [ebp + 0x18]
        push    dword [ebp + 0x14]
        push    dword [ebp + 0x10]
        push    dword [ebp + 0x0c]
        push    dword [ebp + 0x08]
        call    [ebx + IAT_MOVEWINDOW]
.done:
        pop     edi
        pop     esi
        pop     ebx
        mov     esp, ebp
        pop     ebp
        ret     0x18

s_user32            db 'user32.dll', 0
s_getcursorpos      db 'GetCursorPos', 0
s_monitorfrompoint  db 'MonitorFromPoint', 0
s_getmonitorinfo    db 'GetMonitorInfoA', 0
