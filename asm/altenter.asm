; altenter.asm - ALT+ENTER between the borderless window and a framed one.
;
; The window procedure (0x426b80) hands every message it has no case for
; to the text-input handler at 0x41fe20, cdecl (hwnd, msg, wParam,
; lParam), and takes its -1 as "not handled". That call (0x426cbc) is
; pointed here. WM_SYSKEYDOWN for ENTER with ALT held, not a repeat, is
; taken: the window is switched between WS_POPUP covering its monitor -
; how the borderless patch starts it - and a WS_OVERLAPPEDWINDOW with a
; client area the size of the picture, centred on that monitor. Every
; other message continues to the handler with the stack as it was.
;
; The picture is letterboxed into whatever client rect the window has
; (asm/fullwin.asm), so the framed window can be resized or maximised.
;
; user32's SetWindowLongA, SetWindowPos, AdjustWindowRectEx,
; MonitorFromWindow and GetMonitorInfoA are not among the exe's imports;
; they are resolved once through its LoadLibraryA and GetProcAddress and
; kept here, which is why this section is writable.
;
; The exe is never relocated, so the game's addresses are absolute; the
; section's own are not known until it is appended, so the blob takes its
; base with a call/pop and reaches its data from ebx.

bits 32

; Placeholders the patcher fills from the build's row; the European
; values are in the comments.
%define HANDLER         0xECECECEC      ; 0x41fe20
%define IAT_LOADLIB     0xE3E3E3E3      ; 0x495090
%define IAT_GETPROC     0xE4E4E4E4      ; 0x4950f0
%define HWND            0xEDEDEDED      ; 0x5088ac, the game window
%define WIDTH           0xEEEEEEEE      ; 0x4d5e1c, MGameD3D's init struct: the picture's size
%define HEIGHT          0xEFEFEFEF      ; 0x4d5e20

%define WM_SYSKEYDOWN   0x104
%define VK_RETURN       0x0d
%define GWL_STYLE       -16
%define STYLE_FRAMED    0x10cf0000      ; WS_OVERLAPPEDWINDOW | WS_VISIBLE
%define STYLE_BORDERLESS 0x90000000     ; WS_POPUP | WS_VISIBLE
%define SWP_FLAGS       0x64            ; SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW
%define MONITOR_DEFAULTTONEAREST 2
%define NFUNCS          5               ; entries in names and funcs

        mov     eax, [esp + 8]
        cmp     eax, WM_SYSKEYDOWN
        jne     .pass
        cmp     dword [esp + 12], VK_RETURN
        jne     .pass
        mov     eax, [esp + 16]
        test    eax, 1 << 29            ; ALT held
        jz      .pass
        test    eax, 1 << 30            ; a repeat
        jnz     .taken
        call    toggle
.taken:
        xor     eax, eax
        ret
.pass:
        push    HANDLER                 ; a relative jump would not survive being placed
        ret

; ebx = this blob, on return.
getbase:
        call    .here
.here:  pop     ebx
        sub     ebx, .here
        ret

; Frame: RECT [ebp-0x40], MONITORINFO [ebp-0x28] (rcMonitor at [ebp-0x24]).
toggle:
        push    ebx
        push    esi
        push    edi
        push    ebp
        mov     ebp, esp
        sub     esp, 0x40
        call    getbase
        cmp     dword [ebx + funcs], 0
        jne     .have
        lea     eax, [ebx + s_user32]
        push    eax
        call    [IAT_LOADLIB]
        test    eax, eax
        jz      .done
        mov     esi, eax
        xor     edi, edi
.resolve:
        mov     eax, [ebx + names + edi * 4]
        add     eax, ebx
        push    eax
        push    esi
        call    [IAT_GETPROC]
        test    eax, eax
        jz      .done
        mov     [ebx + funcs + edi * 4], eax
        inc     edi
        cmp     edi, NFUNCS
        jb      .resolve
.have:
        mov     edi, [HWND]
        push    MONITOR_DEFAULTTONEAREST
        push    edi
        call    [ebx + f_monitorfromwindow]
        test    eax, eax
        jz      .done
        mov     dword [ebp - 0x28], 40
        lea     ecx, [ebp - 0x28]
        push    ecx
        push    eax
        call    [ebx + f_getmonitorinfo]
        test    eax, eax
        jz      .done
        xor     byte [ebx + framed], 1
        test    byte [ebx + framed], 1
        jz      .borderless

        push    STYLE_FRAMED
        push    GWL_STYLE
        push    edi
        call    [ebx + f_setwindowlong]
        xor     eax, eax
        mov     [ebp - 0x40], eax
        mov     [ebp - 0x3c], eax
        mov     eax, [WIDTH]
        mov     [ebp - 0x38], eax
        mov     eax, [HEIGHT]
        mov     [ebp - 0x34], eax
        push    0
        push    0
        push    STYLE_FRAMED
        lea     eax, [ebp - 0x40]
        push    eax
        call    [ebx + f_adjustwindowrect]
        mov     esi, [ebp - 0x38]       ; window width
        sub     esi, [ebp - 0x40]
        mov     edx, [ebp - 0x34]       ; window height
        sub     edx, [ebp - 0x3c]
        push    SWP_FLAGS
        push    edx
        push    esi
        mov     eax, [ebp - 0x18]       ; monitor bottom
        sub     eax, [ebp - 0x20]       ; - top
        sub     eax, edx
        sar     eax, 1
        add     eax, [ebp - 0x20]
        push    eax                     ; y
        mov     eax, [ebp - 0x1c]       ; monitor right
        sub     eax, [ebp - 0x24]       ; - left
        sub     eax, esi
        sar     eax, 1
        add     eax, [ebp - 0x24]
        push    eax                     ; x
        push    0
        push    edi
        call    [ebx + f_setwindowpos]
        jmp     .done

.borderless:
        push    STYLE_BORDERLESS
        push    GWL_STYLE
        push    edi
        call    [ebx + f_setwindowlong]
        push    SWP_FLAGS
        mov     eax, [ebp - 0x18]
        sub     eax, [ebp - 0x20]
        push    eax                     ; height
        mov     eax, [ebp - 0x1c]
        sub     eax, [ebp - 0x24]
        push    eax                     ; width
        push    dword [ebp - 0x20]      ; top
        push    dword [ebp - 0x24]      ; left
        push    0
        push    edi
        call    [ebx + f_setwindowpos]
.done:
        mov     esp, ebp
        pop     ebp
        pop     edi
        pop     esi
        pop     ebx
        ret

s_user32            db 'user32.dll', 0
s_setwindowlong     db 'SetWindowLongA', 0
s_setwindowpos      db 'SetWindowPos', 0
s_adjustwindowrect  db 'AdjustWindowRectEx', 0
s_monitorfromwindow db 'MonitorFromWindow', 0
s_getmonitorinfo    db 'GetMonitorInfoA', 0

names:  dd s_setwindowlong, s_setwindowpos, s_adjustwindowrect, s_monitorfromwindow, s_getmonitorinfo

; Filled by the first toggle, in the order of names.
framed              db 0
        align 4
funcs:
f_setwindowlong     dd 0
f_setwindowpos      dd 0
f_adjustwindowrect  dd 0
f_monitorfromwindow dd 0
f_getmonitorinfo    dd 0
