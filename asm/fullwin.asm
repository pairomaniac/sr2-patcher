; fullwin.asm - the windowed mode filling the monitor.
;
; MGameD3D's windowed path sizes the window to the 640x480 it draws
; (MoveWindow at 0x100026be) and presents by blitting the back buffer to
; the window's client rect (0x10004d7b). Two thunks, in the annex the
; patcher appends to the DLL:
;
;   +0  present     the client rect, letterboxed to the back buffer's
;                   aspect; the bars filled black, the picture blitted
;                   into the middle. Jumped to from 0x10004d7b, which had
;                   already made its 16-byte frame; leaves through that
;                   frame's `ret 4`.
;   +5  sizewindow  MoveWindow's stdcall shape: a WS_POPUP window is moved
;                   to cover the monitor under the cursor the first time,
;                   the monitor it is on after that (ALT+ENTER may have
;                   taken it elsewhere), or where the game asked if user32
;                   will not say; a framed one (asm/altenter.asm) is left
;                   as the player has it. Called from 0x100026be - on every
;                   screen change, since the game brings the renderer up
;                   again for each screen.
;
; The window class is WS_POPUP, so a window the size of its monitor is
; what Wine and Windows treat as fullscreen, with no display mode change
; behind it.
;
; The primary surface is the primary monitor: DirectDraw's default device
; reaches no other, on Windows or Wine. A client rect that leaves it is
; presented through GDI instead - the back buffer's DC stretched into the
; window's, the bars filled with PatBlt - which reaches any monitor. The
; six user32 and gdi32 entry points are resolved with the counter below
; and kept here; if any is missing the DirectDraw blit is kept.
;
; The counter after the blit is kept in t_blt for the frametrace
; diagnostic, which finds it through the jump the patcher puts at the
; present; QueryPerformanceCounter is resolved on the first present.
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
%define IAT_GETWINDOWLONG   0xf138
%define IAT_LOADLIB         0xf114
%define IAT_GETPROC         0xf0ac

%define BLT             0x14            ; IDirectDrawSurface4::Blt
%define GETDC           0x44            ; IDirectDrawSurface4::GetDC
%define RELEASEDC       0x68            ; IDirectDrawSurface4::ReleaseDC
%define DDBLT_COLORFILL 0x400
%define DDBLT_WAIT      0x1000000
%define MONITOR_DEFAULTTONEAREST 2
%define GWL_STYLE       -16
%define WS_POPUP        0x80000000
%define SM_CXSCREEN     0
%define SM_CYSCREEN     1
%define COLORONCOLOR    3
%define BLACKNESS       0x42
%define SRCCOPY         0xcc0020
%define NUSER           3               ; user32 entries at the head of names
%define NFUNCS          6

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
; [ebp-0x40..-0x4c], cw/ch [ebp-0x50/-0x54], the surface's and the
; window's DC [ebp-0x58/-0x5c], dx/dy [ebp-0x60/-0x64], DDBLTFX (100
; bytes) [ebp-0xc8]. rc and dest are screen coordinates, dx/dy and the
; bars of the GDI path client ones.
present:
        push    ebp
        mov     ebp, esp
        sub     esp, 0xc8
        push    ebx
        push    esi
        push    edi
        call    getbase
        cmp     dword [esi + pqpc], 0
        jne     .resolved
        call    resolve
.resolved:
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
        mov     eax, [ebp - 0x08]
        sub     eax, [ebp - 0x10]
        mov     [ebp - 0x50], eax       ; cw
        mov     eax, [ebp - 0x04]
        sub     eax, [ebp - 0x0c]
        mov     [ebp - 0x54], eax       ; ch
        mov     ecx, [ebx + SRCRECT + 8]
        sub     ecx, [ebx + SRCRECT]
        mov     [ebp - 0x40], ecx       ; sw
        mov     edx, [ebx + SRCRECT + 12]
        sub     edx, [ebx + SRCRECT + 4]
        mov     [ebp - 0x44], edx       ; sh
        test    ecx, ecx                ; an empty source rect: nothing to fit, nothing to divide by
        jz      .none
        test    edx, edx
        jz      .none
        mov     eax, [ebp - 0x50]
        imul    eax, edx                ; cw * sh
        mov     ecx, [ebp - 0x54]
        imul    ecx, [ebp - 0x40]       ; ch * sw
        cmp     eax, ecx
        jb      .bywidth
        mov     eax, [ebp - 0x54]
        mov     [ebp - 0x4c], eax       ; dh = ch
        mov     eax, ecx
        xor     edx, edx
        div     dword [ebp - 0x44]
        mov     [ebp - 0x48], eax       ; dw = ch * sw / sh
        jmp     .fit
.bywidth:
        mov     ecx, [ebp - 0x50]
        mov     [ebp - 0x48], ecx       ; dw = cw
        xor     edx, edx
        div     dword [ebp - 0x40]
        mov     [ebp - 0x4c], eax       ; dh = cw * sh / sw
.fit:
        mov     eax, [ebp - 0x50]
        sub     eax, [ebp - 0x48]
        shr     eax, 1
        mov     [ebp - 0x60], eax       ; dx
        add     eax, [ebp - 0x10]
        mov     [ebp - 0x20], eax       ; dest.left
        add     eax, [ebp - 0x48]
        mov     [ebp - 0x18], eax       ; dest.right
        mov     eax, [ebp - 0x54]
        sub     eax, [ebp - 0x4c]
        shr     eax, 1
        mov     [ebp - 0x64], eax       ; dy
        add     eax, [ebp - 0x0c]
        mov     [ebp - 0x1c], eax       ; dest.top
        add     eax, [ebp - 0x4c]
        mov     [ebp - 0x14], eax       ; dest.bottom

        cmp     dword [esi + f_patblt], 0    ; the last resolved: all six are
        je      .ddraw
        mov     eax, [ebp - 0x10]
        or      eax, [ebp - 0x0c]
        js      .gdi                    ; left of or above the primary monitor
        push    SM_CXSCREEN
        call    [esi + f_getsystemmetrics]
        cmp     [ebp - 0x08], eax
        jg      .gdi                    ; past its right edge
        push    SM_CYSCREEN
        call    [esi + f_getsystemmetrics]
        cmp     [ebp - 0x04], eax
        jg      .gdi                    ; below it

.ddraw:
        lea     edi, [ebp - 0xc8]       ; DDBLTFX, fill colour 0
        xor     eax, eax
        mov     ecx, 25
        rep stosd
        mov     dword [ebp - 0xc8], 100

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
        jmp     .stamp

.gdi:
        mov     eax, [ebx + BACK]
        mov     ecx, [eax]
        lea     edx, [ebp - 0x58]
        push    edx
        push    eax
        call    [ecx + GETDC]
        test    eax, eax
        jnz     .ddraw                  ; no DC to read: the blit, for what it reaches
        push    dword [ebx + HWND]
        call    [esi + f_getdc]
        test    eax, eax
        jz      .release
        mov     [ebp - 0x5c], eax
        push    COLORONCOLOR
        push    eax
        call    [esi + f_setstretchbltmode]

        xor     eax, eax                ; top bar: 0, 0, cw, dy
        mov     [ebp - 0x30], eax
        mov     [ebp - 0x2c], eax
        mov     eax, [ebp - 0x50]
        mov     [ebp - 0x28], eax
        mov     eax, [ebp - 0x64]
        mov     [ebp - 0x24], eax
        call    patbar
        mov     eax, [ebp - 0x64]       ; bottom bar: 0, dy + dh, cw, ch - dy - dh
        add     eax, [ebp - 0x4c]
        mov     [ebp - 0x2c], eax
        mov     ecx, [ebp - 0x54]
        sub     ecx, eax
        mov     [ebp - 0x24], ecx
        call    patbar
        mov     eax, [ebp - 0x64]       ; left bar: 0, dy, dx, dh
        mov     [ebp - 0x2c], eax
        mov     eax, [ebp - 0x60]
        mov     [ebp - 0x28], eax
        mov     eax, [ebp - 0x4c]
        mov     [ebp - 0x24], eax
        call    patbar
        mov     eax, [ebp - 0x60]       ; right bar: dx + dw, dy, cw - dx - dw, dh
        add     eax, [ebp - 0x48]
        mov     [ebp - 0x30], eax
        mov     ecx, [ebp - 0x50]
        sub     ecx, eax
        mov     [ebp - 0x28], ecx
        call    patbar

        push    SRCCOPY
        push    dword [ebp - 0x44]      ; sh
        push    dword [ebp - 0x40]      ; sw
        push    dword [ebx + SRCRECT + 4]
        push    dword [ebx + SRCRECT]
        push    dword [ebp - 0x58]
        push    dword [ebp - 0x4c]      ; dh
        push    dword [ebp - 0x48]      ; dw
        push    dword [ebp - 0x64]      ; dy
        push    dword [ebp - 0x60]      ; dx
        push    dword [ebp - 0x5c]
        call    [esi + f_stretchblt]
        push    dword [ebp - 0x5c]
        push    dword [ebx + HWND]
        call    [esi + f_releasedc]
.release:
        mov     eax, [ebx + BACK]
        mov     ecx, [eax]
        push    dword [ebp - 0x58]
        push    eax
        call    [ecx + RELEASEDC]
        xor     eax, eax                ; DD_OK
        mov     [ebx + LASTHR], eax

.stamp:
        call    stamp
        mov     [esi + t_blt], eax
        mov     eax, [ebx + LASTHR]     ; the blit's result, as the original returned it
.out:   pop     edi
        pop     esi
        pop     ebx
        mov     esp, ebp
        pop     ebp
        add     esp, 0x10               ; the frame 0x10004d55 made
        ret     4
.none:  xor     eax, eax                ; nothing to present: DD_OK
        jmp     .out

; eax = the counter's low dword, 0 without QueryPerformanceCounter.
stamp:
        mov     eax, [esi + pqpc]
        cmp     eax, -1
        je      .none
        test    eax, eax
        jz      .done
        sub     esp, 8
        push    esp
        call    eax
        pop     eax
        add     esp, 4
.done:  ret
.none:  xor     eax, eax
        ret

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
        lea     edx, [ebp - 0xc8]
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

; The bar at [ebp-0x30] - x, y, w, h - filled black in the window's DC,
; if it has any area.
patbar:
        cmp     dword [ebp - 0x28], 0
        jle     .skip
        cmp     dword [ebp - 0x24], 0
        jle     .skip
        push    BLACKNESS
        push    dword [ebp - 0x24]
        push    dword [ebp - 0x28]
        push    dword [ebp - 0x2c]
        push    dword [ebp - 0x30]
        push    dword [ebp - 0x5c]
        call    [esi + f_patblt]
.skip:
        ret

; Resolves QueryPerformanceCounter into pqpc, -1 when kernel32 will not
; say, so it is asked once; then the GDI present's six into funcs, in
; the order of names, stopping at the first missing.
resolve:
        mov     dword [esi + pqpc], -1
        lea     eax, [esi + s_kernel32]
        push    eax
        call    [ebx + IAT_LOADLIB]
        test    eax, eax
        jz      .user32
        lea     ecx, [esi + s_qpc]
        push    ecx
        push    eax
        call    [ebx + IAT_GETPROC]
        test    eax, eax
        jz      .user32
        mov     [esi + pqpc], eax
.user32:
        lea     eax, [esi + s_user32]
        push    eax
        call    [ebx + IAT_LOADLIB]
        test    eax, eax
        jz      .done
        mov     edi, eax
        xor     ecx, ecx
.user:  call    getone
        jz      .done
        inc     ecx
        cmp     ecx, NUSER
        jb      .user
        lea     eax, [esi + s_gdi32]
        push    eax
        call    [ebx + IAT_LOADLIB]
        test    eax, eax
        jz      .done
        mov     edi, eax
        mov     ecx, NUSER              ; the call kept no ecx
.gdi:   call    getone
        jz      .done
        inc     ecx
        cmp     ecx, NFUNCS
        jb      .gdi
.done:  ret

; funcs[ecx] = GetProcAddress(edi, names[ecx]); ecx kept, ZF set on a miss.
getone:
        push    ecx
        mov     eax, [esi + names + ecx * 4]
        add     eax, esi
        push    eax
        push    edi
        call    [ebx + IAT_GETPROC]
        pop     ecx
        mov     [esi + funcs + ecx * 4], eax
        test    eax, eax
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
        push    GWL_STYLE
        push    dword [ebp + 8]
        call    [ebx + IAT_GETWINDOWLONG]
        test    eax, WS_POPUP
        jz      .done                   ; framed: the player's window, left alone
        lea     eax, [esi + s_user32]
        push    eax
        call    [ebx + IAT_LOADLIB]
        test    eax, eax
        jz      .asasked
        mov     edi, eax
        cmp     byte [esi + placed], 0
        jne     .bywindow
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
        jmp     .monitor
.bywindow:
        lea     eax, [esi + s_monitorfromwindow]
        push    eax
        push    edi
        call    [ebx + IAT_GETPROC]
        test    eax, eax
        jz      .asasked
        push    MONITOR_DEFAULTTONEAREST
        push    dword [ebp + 8]
        call    eax
.monitor:
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
        mov     byte [esi + placed], 1
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
s_gdi32             db 'gdi32.dll', 0
s_getcursorpos      db 'GetCursorPos', 0
s_monitorfrompoint  db 'MonitorFromPoint', 0
s_monitorfromwindow db 'MonitorFromWindow', 0
s_getmonitorinfo    db 'GetMonitorInfoA', 0
s_kernel32          db 'kernel32.dll', 0
s_qpc               db 'QueryPerformanceCounter', 0
s_getsystemmetrics  db 'GetSystemMetrics', 0
s_getdc             db 'GetDC', 0
s_releasedc         db 'ReleaseDC', 0
s_setstretchbltmode db 'SetStretchBltMode', 0
s_stretchblt        db 'StretchBlt', 0
s_patblt            db 'PatBlt', 0

names:  dd s_getsystemmetrics, s_getdc, s_releasedc, s_setstretchbltmode, s_stretchblt, s_patblt

placed              db 0                ; sizewindow has placed the window
        align 4
pqpc                dd 0                ; 0 not asked, -1 none
t_blt               dd 0                ; the counter after the blit
; Filled with pqpc, in the order of names.
funcs:
f_getsystemmetrics  dd 0
f_getdc             dd 0
f_releasedc         dd 0
f_setstretchbltmode dd 0
f_stretchblt        dd 0
f_patblt            dd 0
