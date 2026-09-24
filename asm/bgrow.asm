; bgrow.asm - a .bg picture into the back buffer, at either depth and size.
;
; The full-screen pictures (title, loading, game over, the course cards)
; are 16-bit 565 files the game copies straight into a locked back
; buffer, one row at a time, with rep movsd (0x415271). That is right for
; the 16-bit 640x480 mode it was written for. In a window on a 32-bit
; desktop the back buffer is 32-bit, and the same copy puts two pixels'
; worth of bytes into each pixel: the picture at half width, garbage.
; With a wide picture size the buffer is larger than the picture, which
; would sit in its top-left corner.
;
; This replaces the twenty-byte row copy. It reads the locked surface's
; description - the game keeps it at 0x4e6878 - and:
;
; - when the surface is the picture's size, copies the row as before, or
;   expands each 565 pixel to XRGB8888 when the surface is 32-bit,
;   replicating the high bits into the low ones as the display would;
; - when it is not, composes the whole picture on the first row, at
;   source size, into a surface MGameD3D's annex keeps (compose), for
;   one blit to stretch into the screen at the next draw: the picture
;   in the middle, scaled to fit the screen with its aspect kept, and a
;   side area each side carrying the picture behind it - the whole
;   picture stretched to the screen's width, the drawn one covering the
;   middle, so each side shows the sliver beyond the drawn edge spread
;   across it. In Title.dll's build (-DTITLE) that is the picture,
;   blurred across - each column of the sliver the box mean of the
;   columns a sixty-fourth of the width either side, so it comes out as
;   a motion blur - and at DIM of its brightness. The exe's build draws
;   the loading, game-over and course screens, which are pictures on a
;   plain background: there each side is that background, the
;   picture's corner pixel, throughout and nothing more. Without that
;   surface it draws the same thing into the back buffer itself,
;   nearest pixel (bars). Does nothing on the rows after.
;
; Registers as the copy left them: eax (the row's byte count), ebx (source
; row) and edx (destination row) untouched; ecx, esi, edi and ebp are
; scratch there, the game reloads them after. The picture's height is on
; the stack: the loop's object, whose +4 is the picture, height at +8.
;
; Title.dll has its own copy of the same loop (0x100014ba, 22 bytes, with
; the source advanced at the end), its lock description on the stack and
; the rows still to copy - the height, on the first - at [esp+0x10]:
; assembled with -DTITLE it reads those, tells the sizes apart by width
; alone, and advances ebx. Both variants hold the exe's device object
; (GAMED3D), which the patcher fills per build - the exe is never
; relocated, so Title.dll may hold its address - and the exe's the lock
; description too.

bits 32

%define SCRATCH     512                 ; columns a blurred sliver may hold, on the stack
%define GAMED3D     0xEAEAEAEA          ; the exe's MGameD3D device object, filled at apply time
%define VTABLE_RVA  0xf5d4              ; that object's vtable in MGameD3D, whose +0xb4 is the quad draw
%define QUADDRAW_RVA 0x5120             ; at this RVA - the check that the base found is MGameD3D's
%define ANNEX_RVA   0x17000             ; MGameD3D's annex, where the .bg block is
%define BGSURFW     2176                ; the .bg surface, as wide2d.asm makes it
%define BGSURFH     600
%define VT_LOCK     0x64                ; IDirectDrawSurface4::Lock and Unlock
%define VT_UNLOCK   0x80
%define DDLOCK_WAIT 0x1
%define DIM         0x66                ; the bars at this much of the picture's brightness, eight bits of
                                        ; fraction: two fifths, so they sit behind it


%ifdef TITLE
%define DESC        esp + 0x1c          ; the lock description, past the return address
%else
%define DESC        0xF1F1F1F1          ; a placeholder: the description, 0x4e6878 in the European build
%endif
%define D_HEIGHT    8                   ; DDSURFACEDESC2 fields
%define D_WIDTH     0xc
%define D_PITCH     0x10
%define D_SURFACE   0x24
%define D_BITCOUNT  0x54

%ifdef TITLE
        lea     esi, [DESC]             ; the description
%else
        mov     esi, DESC
%endif
        mov     ecx, eax
        shr     ecx, 1                  ; the picture's width
%ifdef TITLE
        mov     ebp, [esp + 4 + 0x10]   ; its height: the rows still to copy
%else
        mov     ebp, [esp + 4 + 0x18]   ; its height: the loop's object, its picture
        mov     ebp, [ebp + 4]
        mov     ebp, [ebp + 8]
%endif
        cmp     [esi + D_WIDTH], ecx
        jne     .picture
%ifndef TITLE                           ; Title.dll's count is the height on the first row only
        cmp     [esi + D_HEIGHT], ebp
        jne     .picture
%endif
        cmp     dword [esi + D_BITCOUNT], 32
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
        call    pixel32
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

; The bars each side of the drawn picture, in the mean colour of the
; picture's own edge columns: ebp = the frame, the picture drawn. Nothing
; to do when it fills the width.
; The picture into the .bg surface MGameD3D's annex keeps, at source
; size: the picture in the middle, the side areas either side as their
; slivers - the same sliver each bar shows, at one source column to
; one, since the whole is stretched once after - and the bands above
; and below as its first and last rows; the composite's size and a flag
; into the annex's block, for the next draw or present to stretch it
; into the whole screen with one blit. Carry set when that is done;
; clear, with nothing touched, when it cannot be - no MGameD3D at the
; device, no block in its annex, no surface yet, or a composite too big
; - and the picture is drawn here as before. The block is found by its
; marker: the device's vtable gives MGameD3D's base (VTABLE_RVA), and
; the annex, from 0x17000 to the image's end, is scanned for it.
compose:
        mov     eax, [GAMED3D]          ; the device: its vtable, and the base from that
        test    eax, eax
        jz      .no
        mov     eax, [eax]
        mov     ecx, [eax + 0xb4]       ; that vtable's quad draw is MGameD3D's at 0x5120, or this is
        sub     eax, VTABLE_RVA         ; not the object meant
        sub     ecx, eax
        cmp     ecx, QUADDRAW_RVA
        jne     .no
        cmp     word [eax], 'MZ'
        jne     .no
        mov     ecx, [eax + 0x3c]       ; the image's end, from its size in the header, less the marker's
        mov     ecx, [eax + ecx + 0x50] ; own eight bytes
        add     ecx, eax
        sub     ecx, 8
        lea     edx, [eax + ANNEX_RVA]
        jmp     .test
.scan:  cmp     dword [edx], 'BGBL'
        jne     .next
        cmp     dword [edx + 4], 'OCK'
        je      .found
.next:  add     edx, 4
.test:  cmp     edx, ecx                ; the bound before the read: no annex, no scan
        jbe     .scan
        jmp     .no
.found: add     edx, 8
        mov     [ebp + 0x110], edx      ; the block, and its surface
        mov     esi, [edx]
        test    esi, esi
        jz      .no
        mov     eax, [ebp + 8]          ; the side areas, in source columns: bar * src w / drawn w
        sub     eax, [ebp + 0x1c]
        shr     eax, 1
        imul    eax, [ebp + 0]
        xor     edx, edx
        div     dword [ebp + 0x1c]
        mov     [ebp + 0x114], eax
        mov     eax, [ebp + 0xc]        ; and the bands, in rows: top * src h / drawn h
        sub     eax, [ebp + 0x20]
        shr     eax, 1
        imul    eax, [ebp + 4]
        xor     edx, edx
        div     dword [ebp + 0x20]
        mov     [ebp + 0x118], eax
        mov     eax, [ebp + 8]          ; the sliver a side area shows: src w * bar / dst w columns, the
        sub     eax, [ebp + 0x1c]       ; whole picture stretched to the whole width; it goes into the
        imul    eax, [ebp + 0]          ; side area's s columns stretched by drawn w / dst w, so the one
        xor     edx, edx                ; stretch of the composite after makes the bar's own
        mov     ecx, [ebp + 8]
        shl     ecx, 1
        div     ecx
        add     eax, 2                  ; two over, so the walk's rounding never reads past it
        cmp     eax, [ebp + 0]
        jbe     .sliverfits
        mov     eax, [ebp + 0]
.sliverfits:
        mov     [ebp + 0x130], eax
        mov     eax, [ebp + 0x1c]
        shl     eax, 16
        xor     edx, edx
        div     dword [ebp + 8]
        mov     [ebp + 0x134], eax
        mov     eax, [ebp + 0]          ; the composite's size, within the surface
        add     eax, [ebp + 0x114]
        add     eax, [ebp + 0x114]
        mov     [ebp + 0x11c], eax
        cmp     eax, BGSURFW
        ja      .no
        mov     eax, [ebp + 4]
        add     eax, [ebp + 0x118]
        add     eax, [ebp + 0x118]
        mov     [ebp + 0x120], eax
        cmp     eax, BGSURFH
        ja      .no
        lea     edi, [ebp + 0x90]       ; the surface locked: its pixels, pitch and depth
        mov     ecx, 0x7c / 4
        xor     eax, eax
        rep stosd
        mov     dword [ebp + 0x90], 0x7c
        mov     eax, [esi]
        push    0
        push    DDLOCK_WAIT
        lea     edx, [ebp + 0x90]
        push    edx
        push    0
        push    esi
        call    [eax + VT_LOCK]
        test    eax, eax
        jnz     .no
        mov     eax, [ebp + 0x90 + 0x10]
        mov     [ebp + 0x124], eax
        mov     eax, [ebp + 0x90 + 0x54]
        mov     [ebp + 0x18], eax       ; the depth the pixels go in at, as stretch reads it
        ; the surface as the lock describes it must hold the composite: its size (when the lock
        ; gives one) and a pitch of at least the composite's row - the depth the lock reports at
        ; the width of the composite, else a row runs into the next and the last off the end
        mov     eax, [ebp + 0x90 + 0xc]
        test    eax, eax
        jz      .widthok
        cmp     [ebp + 0x11c], eax
        ja      .unlockno
.widthok:
        mov     eax, [ebp + 0x90 + 8]
        test    eax, eax
        jz      .heightok
        cmp     [ebp + 0x120], eax
        ja      .unlockno
.heightok:
        mov     eax, [ebp + 0x11c]
        imul    eax, [ebp + 0x18]
        shr     eax, 3
        cmp     eax, [ebp + 0x124]
        ja      .unlockno
        mov     eax, [ebp + 0x118]      ; the first picture row's place: under the top band
        imul    eax, [ebp + 0x124]
        add     eax, [ebp + 0x90 + 0x24]
        mov     [ebp + 0x128], eax
        mov     eax, [ebp + 0]          ; the blur's reach, as bars has it
        shr     eax, 6
        jnz     .reach
        mov     eax, 1
.reach: mov     [ebp + 0x4c], eax
        mov     dword [ebp + 0x12c], 0
.row:   mov     eax, [ebp + 0x12c]      ; the source row
        imul    eax, [ebp + 0]
        lea     ebx, [eax + eax]
        add     ebx, [ebp + 0x34]
        mov     edi, [ebp + 0x128]
        cmp     dword [ebp + 0x114], 0  ; the left side: the sliver from column 0, as the bar shows it
        je      .middle
        mov     ecx, [ebp + 0x130]
        xor     eax, eax
        push    edi
        lea     edi, [ebp + 0x140]
        call    sliver
        pop     edi
        push    ebx
        lea     ebx, [ebp + 0x140]
        mov     eax, [ebp + 0x134]
        mov     [ebp + 0x40], eax
        xor     eax, eax
        mov     ecx, [ebp + 0x114]
        call    stretch
        pop     ebx
.middle:
        mov     dword [ebp + 0x40], 0x10000     ; the picture's row, one column to one
        xor     eax, eax
        mov     ecx, [ebp + 0]
        call    stretch
        cmp     dword [ebp + 0x114], 0  ; the right side: the sliver ending at the last column
        je      .rowdone
        mov     ecx, [ebp + 0x130]
        mov     eax, [ebp + 0]
        sub     eax, ecx
        push    edi
        lea     edi, [ebp + 0x140]
        call    sliver
        pop     edi
        push    ebx
        lea     ebx, [ebp + 0x140]
        mov     eax, [ebp + 0x134]
        mov     [ebp + 0x40], eax
        xor     eax, eax
        mov     ecx, [ebp + 0x114]
        call    stretch
        pop     ebx
.rowdone:
        mov     eax, [ebp + 0x124]
        add     [ebp + 0x128], eax
        inc     dword [ebp + 0x12c]
        mov     eax, [ebp + 0x12c]
        cmp     eax, [ebp + 4]
        jb      .row
        mov     ecx, [ebp + 0x118]      ; the bands: the first composed row above, the last below
        test    ecx, ecx
        jz      .unlock
        mov     eax, [ebp + 0x11c]      ; a row's bytes: columns by the depth, over eight
        imul    eax, [ebp + 0x18]
        shr     eax, 3
        mov     [ebp + 0x12c], eax
        mov     esi, [ebp + 0x118]      ; the first picture row, and the band above it
        imul    esi, [ebp + 0x124]
        add     esi, [ebp + 0x90 + 0x24]
        mov     edi, [ebp + 0x90 + 0x24]
        call    band
        mov     esi, [ebp + 0x118]      ; the last, and the band below
        add     esi, [ebp + 4]
        dec     esi
        imul    esi, [ebp + 0x124]
        add     esi, [ebp + 0x90 + 0x24]
        mov     edi, esi
        add     edi, [ebp + 0x124]
        call    band
        mov     esi, [ebp + 0x110]
        mov     esi, [esi]
.unlock:
        mov     eax, [esi]
        push    0
        push    esi
        call    [eax + VT_UNLOCK]
        mov     edx, [ebp + 0x110]      ; the block: the composite's size, and the flag
        mov     eax, [ebp + 0x11c]
        mov     [edx + 0xc], eax
        mov     eax, [ebp + 0x120]
        mov     [edx + 0x10], eax
        mov     dword [edx + 8], 1
        stc
        ret
.unlockno:
        mov     eax, [esi]              ; a surface the composite does not fit: unlocked, and drawn here
        push    0
        push    esi
        call    [eax + VT_UNLOCK]
.no:    clc
        ret

; esi = a composed row, edi = the first of ecx rows to copy it to,
; [ebp+0x12c] its bytes, [ebp+0x124] the pitch. ecx, esi and edi kept.
band:   push    ecx
        push    esi
        push    edi
.copy:  push    ecx
        push    esi
        push    edi
        mov     ecx, [ebp + 0x12c]
        shr     ecx, 2
        rep movsd
        pop     edi
        pop     esi
        pop     ecx
        add     edi, [ebp + 0x124]
        dec     ecx
        jnz     .copy
        pop     edi
        pop     esi
        pop     ecx
        ret

bars:
        mov     eax, [ebp + 8]
        sub     eax, [ebp + 0x1c]
        shr     eax, 1
        mov     [ebp + 0x3c], eax       ; the bar's width
        test    eax, eax
        jz      .out
        mov     eax, [ebp + 0]          ; the source column a surface column falls on, 16.16: the whole
        shl     eax, 16                 ; picture over the whole width
        xor     edx, edx
        div     dword [ebp + 8]
        mov     [ebp + 0x40], eax
        mov     eax, [ebp + 0]          ; the blur's reach either side of a column: a sixty-fourth of the
        shr     eax, 6                  ; width, so the box is a thirty-second across, at least a column
        jnz     .reach
        mov     eax, 1
.reach: mov     [ebp + 0x4c], eax
        mov     eax, [ebp + 0x3c]       ; the slivers, in source columns: the left from 0, the right from
        add     eax, [ebp + 0x1c]       ; the first past the picture, and how far each runs
        mov     [ebp + 0x64], eax       ; (the right's first surface column, kept for the walk)
        imul    eax, [ebp + 0x40]
        mov     [ebp + 0x68], eax       ; the right's first source column, 16.16
        shr     eax, 16
        mov     ecx, [ebp + 0]
        sub     ecx, eax
        cmp     ecx, SCRATCH
        jbe     .rightfits
        mov     ecx, SCRATCH
.rightfits:
        mov     [ebp + 0x6c], ecx       ; the right's columns
        mov     eax, [ebp + 0x3c]
        imul    eax, [ebp + 0x40]
        shr     eax, 16
        inc     eax
        cmp     eax, SCRATCH
        jbe     .leftfits
        mov     eax, SCRATCH
.leftfits:
        mov     [ebp + 0x70], eax       ; the left's columns
        mov     dword [ebp + 0x48], 0   ; the same walk down the picture the drawing made
        mov     eax, [ebp + 0xc]        ; the rows above it take its first row
        sub     eax, [ebp + 0x20]
        shr     eax, 1
        mov     [ebp + 0x30], eax
        mov     esi, [ebp + 0x14]
        mov     edx, [ebp + 0xc]
.fill:  mov     eax, [ebp + 0x48]       ; this row's source row
        shr     eax, 16
        imul    eax, [ebp + 0]
        lea     ebx, [eax + eax]
        add     ebx, [ebp + 0x34]
        push    esi
        push    edx
        xor     eax, eax                ; the left sliver into the scratch row, and stretched
        mov     ecx, [ebp + 0x70]
        lea     edi, [ebp + 0x140]
        call    sliver
        lea     ebx, [ebp + 0x140]
        mov     edi, esi
        xor     eax, eax
        mov     ecx, [ebp + 0x3c]
        call    stretch
        mov     eax, [ebp + 0x48]       ; the right likewise, from its own first column
        shr     eax, 16
        imul    eax, [ebp + 0]
        lea     ebx, [eax + eax]
        add     ebx, [ebp + 0x34]
        mov     eax, [ebp + 0x68]
        shr     eax, 16
        mov     ecx, [ebp + 0x6c]
        lea     edi, [ebp + 0x140]
        call    sliver
        lea     ebx, [ebp + 0x140]
        mov     edi, [ebp + 0x64]
        cmp     dword [ebp + 0x18], 32
        jne     .right16
        shl     edi, 1
.right16:
        lea     edi, [esi + edi * 2]
        mov     eax, [ebp + 0x68]
        and     eax, 0xffff             ; the walk from the scratch row's first column: the fraction alone
        mov     ecx, [ebp + 8]
        sub     ecx, [ebp + 0x64]
        call    stretch
        pop     edx
        pop     esi
        cmp     dword [ebp + 0x30], 0   ; the picture's rows step the source, the bands above it do not
        je      .step
        dec     dword [ebp + 0x30]
        jmp     .next
.step:  mov     eax, [ebp + 0x28]
        add     [ebp + 0x48], eax
        mov     eax, [ebp + 0x48]       ; and it stops at the last row, for the bands below
        shr     eax, 16
        cmp     eax, [ebp + 4]
        jb      .next
        mov     eax, [ebp + 4]
        dec     eax
        shl     eax, 16
        mov     [ebp + 0x48], eax
.next:  add     esi, [ebp + 0x10]
        dec     edx
        jnz     .fill
.out:   ret

; ebx = a row of the picture, eax = its first column of interest, ecx =
; how many, edi = a scratch row: the sliver as its bar shows it. In
; Title.dll that is the picture, blurred and dimmed; in the exe - the
; loading, game-over and course screens, pictures on a plain background
; - it is the background, the picture's corner pixel, throughout: the
; row's own edge would carry whatever reaches it, the card's blur and
; its red rule, out as streaks. esi and edx kept.
sliver:
%ifdef TITLE
        jmp     blur
%else
        push    ecx
        mov     eax, [ebp + 0x34]       ; the picture's first pixel
        movzx   eax, word [eax]
        db      0xf3, 0x66, 0xab        ; rep stosw, its two prefixes in this order: nasm 2 puts the rep
        pop     ecx                     ; first and nasm 3 the operand size, and the blobs must assemble
        ret                             ; alike on every machine
%endif

; ebx = a row of the picture, eax = its first column of interest, ecx =
; how many, edi = a scratch row: each column's box mean, over the
; columns the reach either side of it that the sliver has, into the
; scratch as 565. A running sum: a column comes into the box as one goes
; out, the count following at the sliver's ends. esi and edx kept.
blur:
        push    esi
        push    edx
        mov     [ebp + 0x74], ecx       ; columns to do
        mov     [ebp + 0x78], eax       ; the column in hand
        mov     [ebp + 0x88], eax       ; the sliver's first and last: the box stays inside it, so the
        add     ecx, eax                ; picture beside the bar does not bleed into it
        dec     ecx
        mov     [ebp + 0x8c], ecx
        xor     ecx, ecx                ; the sums and the count, over the box around the first column
        mov     [ebp + 0x54], ecx
        mov     [ebp + 0x58], ecx
        mov     [ebp + 0x5c], ecx
        mov     [ebp + 0x50], ecx
        mov     esi, eax
        mov     edx, eax
        add     edx, [ebp + 0x4c]
        cmp     edx, [ebp + 0x8c]
        jbe     .to
        mov     edx, [ebp + 0x8c]
.to:    movzx   eax, word [ebx + esi * 2]
        call    boxin
        inc     esi
        cmp     esi, edx
        jbe     .to
.col:   mov     eax, [ebp + 0x54]       ; the mean, dimmed, back to 565
        xor     edx, edx
        div     dword [ebp + 0x50]
        imul    eax, DIM
        shr     eax, 8
        shl     eax, 11
        mov     ecx, eax
        mov     eax, [ebp + 0x58]
        xor     edx, edx
        div     dword [ebp + 0x50]
        imul    eax, DIM
        shr     eax, 8
        shl     eax, 5
        or      ecx, eax
        mov     eax, [ebp + 0x5c]
        xor     edx, edx
        div     dword [ebp + 0x50]
        imul    eax, DIM
        shr     eax, 8
        or      eax, ecx
        stosw
        mov     eax, [ebp + 0x78]       ; the box slides: the column the reach behind goes out
        sub     eax, [ebp + 0x4c]
        cmp     eax, [ebp + 0x88]
        jl      .nothingout
        movzx   eax, word [ebx + eax * 2]
        call    boxout
.nothingout:
        mov     eax, [ebp + 0x78]       ; and the one the reach ahead, plus one, comes in
        add     eax, [ebp + 0x4c]
        inc     eax
        cmp     eax, [ebp + 0x8c]
        ja      .nothingin
        movzx   eax, word [ebx + eax * 2]
        call    boxin
.nothingin:
        inc     dword [ebp + 0x78]
        dec     dword [ebp + 0x74]
        jnz     .col
        pop     edx
        pop     esi
        ret

; eax = a 565 pixel: its channels onto the box's sums, and the count up.
; ecx, edx, esi and edi kept.
boxin:
        push    edx
        mov     edx, eax
        shr     edx, 11
        add     [ebp + 0x54], edx
        mov     edx, eax
        shr     edx, 5
        and     edx, 63
        add     [ebp + 0x58], edx
        and     eax, 31
        add     [ebp + 0x5c], eax
        inc     dword [ebp + 0x50]
        pop     edx
        ret

; eax = a 565 pixel: its channels off the box's sums, and the count down.
boxout:
        push    edx
        mov     edx, eax
        shr     edx, 11
        sub     [ebp + 0x54], edx
        mov     edx, eax
        shr     edx, 5
        and     edx, 63
        sub     [ebp + 0x58], edx
        and     eax, 31
        sub     [ebp + 0x5c], eax
        dec     dword [ebp + 0x50]
        pop     edx
        ret

; ebx = a row, edi = a destination, ecx = pixels, eax = the row's column
; the first of them falls on in 16.16: the span filled with the row,
; nearest pixel, at the surface's depth. esi and edx kept.
stretch:
        push    esi
        push    edx
        mov     esi, eax
.px:    mov     eax, esi
        shr     eax, 16
        movzx   eax, word [ebx + eax * 2]
        cmp     dword [ebp + 0x18], 32
        jne     .narrow
        push    ecx
        push    edx
        push    ebx
        call    pixel32
        pop     ebx
        pop     edx
        pop     ecx
        stosd
        jmp     .on
.narrow:
        stosw
.on:    add     esi, [ebp + 0x40]
        dec     ecx
        jnz     .px
        pop     edx
        pop     esi
        ret

; eax = a 565 pixel: eax = it as XRGB8888. ebx and edx scratch.
pixel32:
        push    ebp
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
        pop     ebp
        ret

; The surface is not the picture's size: esi = the description, ebp = the
; picture's height.
; Frame: [ebp+0] src width, +4 src height, +8 dst width, +0xc dst height,
; +0x10 pitch, +0x14 surface, +0x18 bitcount, +0x1c drawn width, +0x20
; drawn height, +0x24 x step, +0x28 y step (16.16), +0x2c y accumulator,
; +0x30 rows left, +0x34 the source, +0x38 the destination row. The
; bars' own, after the picture is drawn: +0x3c the bar's width, +0x40
; the source column a surface column falls on (16.16), +0x48 the bars'
; own walk down the picture, +0x4c the blur's reach, +0x50 to +0x5c the
; box's count and sums, +0x64 to +0x70 the two slivers' first columns
; and lengths, +0x74 and +0x78 the blur's own counters, +0x88 and +0x8c
; the sliver the box stays inside. compose's: +0x90 the surface
; description it locks with (0x7c bytes), +0x110 the block, +0x114 and
; +0x118 the side areas' columns and the bands' rows, +0x11c and +0x120
; the composite's size, +0x124 the surface's pitch, +0x128 the row in
; hand and +0x12c its count (a row's bytes, for the bands), +0x130 the
; sliver's columns and +0x134 the step that stretches them into the
; side area. From +0x140 the scratch row a sliver goes into.
.picture:
        cmp     edx, [esi + D_SURFACE]
        jne     .later                  ; not the first row: drawn already
        push    eax
        push    ebx
        push    edx
        push    esi
        push    edi
        push    ebp
        mov     ecx, ebp
        sub     esp, 0x140 + SCRATCH * 2
        mov     ebp, esp
        mov     [ebp + 4], ecx
        mov     [ebp + 0x34], ebx
        mov     ecx, eax
        shr     ecx, 1
        mov     [ebp + 0], ecx
        mov     eax, [esi + D_WIDTH]
        mov     [ebp + 8], eax
        mov     eax, [esi + D_HEIGHT]
        mov     [ebp + 0xc], eax
        mov     eax, [esi + D_PITCH]
        mov     [ebp + 0x10], eax
        mov     eax, [esi + D_SURFACE]
        mov     [ebp + 0x14], eax
        mov     eax, [esi + D_BITCOUNT]
        mov     [ebp + 0x18], eax
        ; the drawn size: the largest with the picture's aspect that fits
        mov     eax, [ebp + 8]          ; dst w * src h
        imul    eax, [ebp + 4]
        mov     ecx, [ebp + 0xc]        ; dst h * src w
        imul    ecx, [ebp + 0]
        cmp     eax, ecx
        jbe     .fitwidth
        mov     eax, ecx                ; height fills: width = dst h * src w / src h
        xor     edx, edx
        div     dword [ebp + 4]
        mov     [ebp + 0x1c], eax
        mov     eax, [ebp + 0xc]
        mov     [ebp + 0x20], eax
        jmp     .steps
.fitwidth:                              ; width fills: height = dst w * src h / src w
        xor     edx, edx
        div     dword [ebp + 0]
        mov     [ebp + 0x20], eax
        mov     eax, [ebp + 8]
        mov     [ebp + 0x1c], eax
.steps: mov     eax, [ebp + 0]
        shl     eax, 16
        xor     edx, edx
        div     dword [ebp + 0x1c]
        mov     [ebp + 0x24], eax
        mov     eax, [ebp + 4]
        shl     eax, 16
        xor     edx, edx
        div     dword [ebp + 0x20]
        mov     [ebp + 0x28], eax
        mov     dword [ebp + 0x2c], 0
        call    compose                 ; into the surface MGameD3D keeps, for one blit to stretch in
        jc      .composed               ; - or, without one, drawn here
        ; clear the surface
        mov     edi, [ebp + 0x14]
        mov     edx, [ebp + 0xc]
.clear: mov     ecx, [ebp + 0x10]
        shr     ecx, 2
        xor     eax, eax
        push    edi
        rep stosd
        pop     edi
        add     edi, [ebp + 0x10]
        dec     edx
        jnz     .clear
        ; the first drawn row: (dst h - drawn h) / 2 rows down, (dst w - drawn w) / 2 pixels in
        mov     eax, [ebp + 0xc]
        sub     eax, [ebp + 0x20]
        shr     eax, 1
        imul    eax, [ebp + 0x10]
        add     eax, [ebp + 0x14]
        mov     ecx, [ebp + 8]
        sub     ecx, [ebp + 0x1c]
        shr     ecx, 1
        cmp     dword [ebp + 0x18], 32
        jne     .bpp16
        shl     ecx, 1
.bpp16: lea     eax, [eax + ecx * 2]
        mov     [ebp + 0x38], eax
        mov     eax, [ebp + 0x20]
        mov     [ebp + 0x30], eax
.row:   mov     eax, [ebp + 0x2c]
        shr     eax, 16                 ; the source row
        imul    eax, [ebp + 0]
        lea     esi, [eax + eax]
        add     esi, [ebp + 0x34]
        mov     edi, [ebp + 0x38]
        xor     edx, edx                ; the x accumulator
        mov     ecx, [ebp + 0x1c]
.px:    push    edx
        shr     edx, 16
        movzx   eax, word [esi + edx * 2]
        cmp     dword [ebp + 0x18], 32
        je      .px32
        stosw
        jmp     .pxnext
.px32:  push    ecx
        call    pixel32
        pop     ecx
        stosd
.pxnext:
        pop     edx
        add     edx, [ebp + 0x24]
        dec     ecx
        jnz     .px
        mov     eax, [ebp + 0x28]
        add     [ebp + 0x2c], eax
        mov     eax, [ebp + 0x10]
        add     [ebp + 0x38], eax
        dec     dword [ebp + 0x30]
        jnz     .row
        call    bars
.composed:
        lea     esp, [ebp + 0x140 + SCRATCH * 2]
        pop     ebp
        pop     edi
        pop     esi
        pop     edx
        pop     ebx
        pop     eax
.later:
%ifdef TITLE
        add     ebx, eax
%endif
        ret
