; bgrow.asm - one row of a .bg picture into the back buffer, at either depth.
;
; The full-screen pictures (title, loading, game over, the course cards)
; are 16-bit 565 files the game copies straight into a locked back
; buffer, one row at a time, with rep movsd (0x415271). That is right for
; the 16-bit display mode it was written for. In a window on a 32-bit
; desktop the back buffer is 32-bit, and the same copy puts two pixels'
; worth of bytes into each pixel: the picture at half width, garbage.
;
; This replaces the twenty-byte row copy. It reads the locked surface's
; bit depth from the description the game keeps at 0x4e6878 and either
; copies the row as before or expands each 565 pixel to XRGB8888,
; replicating the high bits into the low ones as the display would.
;
; Registers as the copy left them: eax (the row's byte count), ebx (source
; row) and edx (destination row) untouched; ecx, esi, edi and ebp are
; scratch there, the game reloads them after.
;
; Title.dll has its own copy of the same loop (0x100014ba, 22 bytes, with
; the source advanced at the end), its lock description on the stack:
; assembled with -DTITLE it reads the depth from there and advances ebx.
; Neither variant holds an absolute address of its own.

bits 32

%ifdef TITLE
%define BITCOUNT    esp + 0x70          ; the lock description's dwRGBBitCount, past the return address
%else
%define BITCOUNT    0x4e68cc            ; ddpfPixelFormat.dwRGBBitCount of the lock
%endif

        cmp     dword [BITCOUNT], 32
        je      .expand
        mov     ecx, eax                ; the original copy
        mov     ebp, ecx
        shr     ecx, 2
        mov     esi, ebx
        mov     edi, edx
        rep movsd
        mov     ecx, ebp
        and     ecx, 3
        rep movsb
%ifdef TITLE
        add     ebx, eax
%endif
        ret

.expand:
        push    eax
        push    ebx
        push    edx
        mov     ecx, eax
        shr     ecx, 1                  ; pixels in the row
        jz      .done
        mov     esi, ebx
        mov     edi, edx
.pixel:
        movzx   eax, word [esi]
        add     esi, 2
        mov     ebx, eax
        mov     edx, eax
        and     ebx, 0xf800             ; r5 << 11
        and     edx, 0x07e0             ; g6 << 5
        and     eax, 0x001f             ; b5
        mov     ebp, ebx
        shl     ebx, 8                  ; r5 << 19
        shl     ebp, 3
        and     ebp, 0x070000           ; r5 >> 2, at bit 16
        or      ebx, ebp
        mov     ebp, edx
        shl     edx, 5                  ; g6 << 10
        shr     ebp, 1
        and     ebp, 0x000300           ; g6 >> 4, at bit 8
        or      edx, ebp
        mov     ebp, eax
        shl     eax, 3                  ; b5 << 3
        shr     ebp, 2                  ; b5 >> 2
        or      eax, ebp
        or      eax, ebx
        or      eax, edx
        stosd
        dec     ecx
        jnz     .pixel
.done:
        pop     edx
        pop     ebx
        pop     eax
%ifdef TITLE
        add     ebx, eax
%endif
        ret
