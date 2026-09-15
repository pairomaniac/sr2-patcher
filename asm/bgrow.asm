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
; - when it is not, draws the whole picture on the first row, scaled to
;   fit the surface with its aspect kept (nearest pixel) and centred,
;   with a bar each side carrying the picture behind it: the whole
;   picture stretched to the surface's width, the drawn one covering the
;   middle, so each bar shows the sliver beyond the drawn edge spread
;   across it. Sixty-four samples wide, each the mean of a block twice as
;   wide as the step between them, over the rows a sixteenth of the
;   height either side, and the pixels between them a ramp from one
;   sample to the next. The blocks overlap both ways, so nothing of the
;   picture's own grain survives, so the stepping a row copied three
;   times would leave goes as well, and the bars sit at half the
;   picture's brightness so they stay behind it. A sliver all of a
;   colour fills flat with it, and one three quarters black, or dark
;   enough on the average, fills black outright - the loading and
;   game-over screens, and the vendor logo, whose streak is neither
;   flat nor black but sits in a sliver that is. Does nothing on the
;   rows after.
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
; alone, and advances ebx. The TITLE
; variant holds no absolute address; the other has the one placeholder
; the patcher fills.

bits 32

%define NSEG        64                  ; samples across a bar, less one
%define FLAT        2                   ; a sliver is all of a colour when its samples sit no further
                                        ; than this from the mean, five bits a channel
%define DARK        8                   ; or when the mean is this dark: that one fills black, not its mean
%define BLACK       4                   ; a sample this dark counts as black, and a sliver three quarters
%define MOSTLY      3                   ; of them fills black whatever the rest of it holds - the vendor
                                        ; logo's streak sits in one that does
%define DIM         0x4d                ; the bars at this much of the picture's brightness, eight bits of
                                        ; fraction: three tenths

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
bars:
        mov     eax, [ebp + 8]
        sub     eax, [ebp + 0x1c]
        shr     eax, 1
        mov     [ebp + 0x40], eax       ; the bar's width
        test    eax, eax
        jz      .out
        xor     edx, edx                ; and a segment of it
        mov     ecx, NSEG
        div     ecx
        mov     [ebp + 0x44], eax
        test    eax, eax
        jz      .out                    ; narrower than the segments: nothing worth drawing
        mov     eax, [ebp + 4]          ; how far the blur reaches, in the picture's rows: wide enough that
        shr     eax, 4                  ; one row more or less hardly moves it, so the bar does not step
        jnz     .reach                  ; down the picture the way a row copied three times would
        mov     eax, 1
.reach: mov     [ebp + 0x3c], eax
        ; the slivers: the picture stretched to the whole width, the drawn one covering the middle,
        ; so the left bar carries source 0 to srcw * barw / dstw and the right the far end of it
        mov     dword [ebp + 0x5c], 0
        mov     eax, [ebp + 0]
        imul    eax, [ebp + 0x40]
        xor     edx, edx
        div     dword [ebp + 8]
        mov     ecx, 0
        call    sliver
        mov     [ebp + 0x54], eax
        mov     eax, [ebp + 0x1b0]
        mov     [ebp + 0x1a8], eax
        mov     eax, [ebp + 0x40]
        add     eax, [ebp + 0x1c]
        imul    eax, [ebp + 0]
        xor     edx, edx
        div     dword [ebp + 8]
        mov     [ebp + 0x9c], eax
        shl     eax, 16
        mov     [ebp + 0x60], eax
        mov     ecx, [ebp + 0x9c]
        mov     eax, [ebp + 0]
        call    sliver
        mov     [ebp + 0x58], eax
        mov     eax, [ebp + 0x1b0]
        mov     [ebp + 0x1ac], eax
        mov     dword [ebp + 0x1b4], -1 ; no samples taken yet, either side
        mov     dword [ebp + 0x1b8], -1
        ; a sliver that is all of a colour fills flat with it, as the loading and game-over
        ; screens and the vendor logo want; one with a picture in it is stretched and blurred
        mov     dword [ebp + 0x50], 0
        mov     eax, [ebp + 0x5c]
        mov     ecx, [ebp + 0x54]
        call    flatness
        jnc     .leftdone
        mov     [ebp + 0x48], eax
        or      dword [ebp + 0x50], 1
.leftdone:
        mov     eax, [ebp + 0x60]
        mov     ecx, [ebp + 0x58]
        call    flatness
        jnc     .rightdone
        mov     [ebp + 0x4c], eax
        or      dword [ebp + 0x50], 2
.rightdone:
        mov     dword [ebp + 0x98], 0   ; the same walk down the picture the drawing made
        mov     eax, [ebp + 0xc]        ; the rows above it take its first row
        sub     eax, [ebp + 0x20]
        shr     eax, 1
        mov     [ebp + 0x30], eax
        mov     esi, [ebp + 0x14]
        mov     edx, [ebp + 0xc]
.fill:  mov     eax, [ebp + 0x98]
        shr     eax, 16
        call    setrows
        push    esi
        push    edx
        mov     edi, esi                ; the left bar
        test    dword [ebp + 0x50], 1
        jz      .leftramp
        mov     eax, [ebp + 0x48]
        mov     ecx, [ebp + 0x40]
        call    span
        jmp     .right
.leftramp:
        mov     eax, [ebp + 0x98]       ; the samples stand until the picture's row changes under them
        shr     eax, 16
        cmp     eax, [ebp + 0x1b4]
        je      .leftdraw
        mov     [ebp + 0x1b4], eax
        mov     eax, [ebp + 0x1a8]
        mov     [ebp + 0x1b0], eax
        lea     eax, [ebp + 0xa0]
        mov     [ebp + 0x1bc], eax
        mov     eax, [ebp + 0x5c]
        mov     ecx, [ebp + 0x54]
        call    samples
.leftdraw:
        lea     eax, [ebp + 0xa0]
        mov     [ebp + 0x1bc], eax
        call    rampbar
.right: mov     edi, [ebp + 0x40]
        add     edi, [ebp + 0x1c]
        cmp     dword [ebp + 0x18], 32
        jne     .right16
        shl     edi, 1
.right16:
        lea     edi, [esi + edi * 2]
        test    dword [ebp + 0x50], 2
        jz      .rightramp
        mov     eax, [ebp + 0x4c]
        mov     ecx, [ebp + 8]
        sub     ecx, [ebp + 0x40]
        sub     ecx, [ebp + 0x1c]
        call    span
        jmp     .done
.rightramp:
        mov     eax, [ebp + 0x98]
        shr     eax, 16
        cmp     eax, [ebp + 0x1b8]
        je      .rightdraw
        mov     [ebp + 0x1b8], eax
        mov     eax, [ebp + 0x1ac]
        mov     [ebp + 0x1b0], eax
        lea     eax, [ebp + 0x1c0]
        mov     [ebp + 0x1bc], eax
        mov     eax, [ebp + 0x60]
        mov     ecx, [ebp + 0x58]
        call    samples
.rightdraw:
        lea     eax, [ebp + 0x1c0]
        mov     [ebp + 0x1bc], eax
        call    rampbar
.done:  pop     edx
        pop     esi
        cmp     dword [ebp + 0x30], 0   ; the picture's rows step the source, the bands above it do not
        je      .step
        dec     dword [ebp + 0x30]
        jmp     .next
.step:  mov     eax, [ebp + 0x28]
        add     [ebp + 0x98], eax
        mov     eax, [ebp + 0x98]       ; and it stops at the last row, for the bands below
        shr     eax, 16
        cmp     eax, [ebp + 4]
        jb      .next
        mov     eax, [ebp + 4]
        dec     eax
        shl     eax, 16
        mov     [ebp + 0x98], eax
.next:  add     esi, [ebp + 0x10]
        dec     edx
        jnz     .fill
.out:   ret

; eax = a sliver's end column, ecx = its start: the block a sample covers
; into +0x1a8 and the step between samples in eax, so the last block ends
; where the sliver does. edx clobbered.
sliver:
        sub     eax, ecx
        push    eax
        xor     edx, edx
        mov     ecx, NSEG
        div     ecx
        test    eax, eax
        jnz     .have
        inc     eax
.have:  add     eax, eax                ; the blocks overlap their neighbours, which is the blur across
        mov     [ebp + 0x1b0], eax
        pop     edx
        sub     edx, eax
        jns     .span
        xor     edx, edx
.span:  mov     eax, edx
        shl     eax, 16
        xor     edx, edx
        mov     ecx, NSEG
        div     ecx
        ret

; eax = the picture's row in hand: the rows the blur reaches over into
; +0x68 and +0x6c. Every register kept.
setrows:
        push    eax
        sub     eax, [ebp + 0x3c]
        jns     .first
        xor     eax, eax
.first: mov     [ebp + 0x68], eax
        pop     eax
        add     eax, [ebp + 0x3c]
        cmp     eax, [ebp + 4]
        jb      .last
        mov     eax, [ebp + 4]
        dec     eax
.last:  mov     [ebp + 0x6c], eax
        ret

; eax = a source column in 16.16: eax = the mean of it over the rows the
; blur reaches, as a 565 pixel. ecx, edx, esi and edi kept.
colmean:
        push    ecx
        push    edx
        push    esi
        push    edi
        shr     eax, 16
        mov     [ebp + 0x90], eax
        xor     eax, eax
        mov     [ebp + 0x74], eax
        mov     [ebp + 0x78], eax
        mov     [ebp + 0x7c], eax
        mov     [ebp + 0x70], eax
        mov     edx, [ebp + 0x68]
.row:   mov     eax, edx
        imul    eax, [ebp + 0]
        add     eax, [ebp + 0x90]
        lea     esi, [eax * 2]
        add     esi, [ebp + 0x34]
        mov     ecx, [ebp + 0x1b0]      ; the block's columns
.col:   movzx   eax, word [esi]
        add     esi, 2
        lea     edi, [ebp + 0x74]
        call    addpixel
        inc     dword [ebp + 0x70]
        dec     ecx
        jnz     .col
        add     edx, 4                  ; every fourth row: the blur reaches far enough without them all
        cmp     edx, [ebp + 0x6c]
        jbe     .row
        mov     ecx, [ebp + 0x70]
        lea     edi, [ebp + 0x74]
        call    mean565
        pop     edi
        pop     esi
        pop     edx
        pop     ecx
        ret

; eax = the first source column of a sliver in 16.16, ecx = the step
; between its samples: the seventeen colours across it into +0xa0. esi,
; edx and edi kept.
samples:
        push    edi
        push    edx
        mov     [ebp + 0x94], eax
        mov     [ebp + 0x88], ecx
        mov     edi, [ebp + 0x1bc]
        mov     edx, NSEG + 1
.one:   mov     eax, [ebp + 0x94]
        call    colmean
        stosd
        mov     eax, [ebp + 0x88]
        add     [ebp + 0x94], eax
        dec     edx
        jnz     .one
        mov     dword [ebp + 0x2cc], DIM        ; the bar sits at half the picture's brightness
        push    esi
        mov     esi, [ebp + 0x1bc]
        mov     edx, NSEG + 1
.dim:   mov     eax, [esi]
        call    scale565
        mov     [esi], eax
        add     esi, 4
        dec     edx
        jnz     .dim
        pop     esi
        pop     edx
        pop     edi
        ret

; eax = a 565 pixel: eax = its three channels added up. edx clobbered.
lum:
        mov     edx, eax
        shr     edx, 11
        push    edx
        mov     edx, eax
        shr     edx, 6
        and     edx, 31
        and     eax, 31
        add     eax, edx
        pop     edx
        add     eax, edx
        ret

; eax = a 565 pixel: eax = it scaled by +0x2cc, eight bits of fraction,
; each channel held to what it can hold. ecx, edx and esi kept.
scale565:
        push    ecx
        push    esi
        mov     esi, eax
        shr     eax, 11                 ; red
        imul    eax, [ebp + 0x2cc]
        shr     eax, 8
        cmp     eax, 31
        jbe     .red
        mov     eax, 31
.red:   mov     ecx, eax
        shl     ecx, 11
        mov     eax, esi
        shr     eax, 5                  ; green
        and     eax, 63
        imul    eax, [ebp + 0x2cc]
        shr     eax, 8
        cmp     eax, 63
        jbe     .green
        mov     eax, 63
.green: shl     eax, 5
        or      ecx, eax
        mov     eax, esi                ; blue
        and     eax, 31
        imul    eax, [ebp + 0x2cc]
        shr     eax, 8
        cmp     eax, 31
        jbe     .blue
        mov     eax, 31
.blue:  or      eax, ecx
        pop     esi
        pop     ecx
        ret

; edi = a bar's first pixel: it filled from the seventeen colours at
; +0xa0, each segment a ramp from one to the next, so the sliver is
; spread across the bar without a step in it. esi and edx kept.
rampbar:
        push    esi
        push    edx
        mov     ecx, NSEG
        mov     [ebp + 0x64], ecx       ; the segments still to draw, which ramp's own slots must not touch
        mov     esi, [ebp + 0x1bc]
.seg:   mov     eax, [esi]
        mov     edx, [esi + 4]
        add     esi, 4
        mov     ecx, [ebp + 0x44]
        cmp     dword [ebp + 0x64], 1   ; the last takes the pixels the segments did not divide
        jne     .go
        mov     ecx, [ebp + 0x40]
        mov     [ebp + 0x90], edx
        mov     edx, NSEG - 1
        imul    edx, [ebp + 0x44]
        sub     ecx, edx
        mov     edx, [ebp + 0x90]
.go:    call    ramp
        dec     dword [ebp + 0x64]
        jnz     .seg
        pop     edx
        pop     esi
        ret

; edi = a destination, ecx = pixels, eax and edx = the 565 colours to run
; between: the span filled with the ramp, at the surface's depth. esi
; kept, edi left after it.
ramp:
        push    esi
        push    ebx
        mov     [ebp + 0x70], ecx
        mov     esi, eax                ; the three channels, 16.16, and their steps
        mov     ebx, edx
        xor     ecx, ecx
.channel:
        mov     eax, esi
        call    unpack
        mov     [ebp + 0x74 + ecx * 4], eax
        mov     [ebp + 0x80 + ecx * 4], eax
        mov     eax, ebx
        call    unpack
        sub     eax, [ebp + 0x74 + ecx * 4]
        shl     eax, 16
        cdq
        push    ecx
        idiv    dword [ebp + 0x70]
        pop     ecx
        mov     [ebp + 0x8c - 0 + ecx * 4], eax
        shl     dword [ebp + 0x80 + ecx * 4], 16
        inc     ecx
        cmp     ecx, 3
        jb      .channel
        mov     ecx, [ebp + 0x70]
.pixel: mov     eax, [ebp + 0x80]       ; red, green, blue back into a 565 pixel
        shr     eax, 16
        shl     eax, 11
        mov     edx, [ebp + 0x84]
        shr     edx, 16
        shl     edx, 5
        or      eax, edx
        mov     edx, [ebp + 0x88]
        shr     edx, 16
        or      eax, edx
        cmp     dword [ebp + 0x18], 32
        jne     .narrow
        push    ecx
        push    edx
        call    pixel32
        pop     edx
        pop     ecx
        stosd
        jmp     .step
.narrow:
        stosw
.step:  mov     eax, [ebp + 0x8c]
        add     [ebp + 0x80], eax
        mov     eax, [ebp + 0x90]
        add     [ebp + 0x84], eax
        mov     eax, [ebp + 0x94]
        add     [ebp + 0x88], eax
        dec     ecx
        jnz     .pixel
        pop     ebx
        pop     esi
        ret

; eax = a 565 pixel, ecx = 0, 1 or 2: eax = its red, green or blue.
unpack:
        cmp     ecx, 0
        jne     .green
        shr     eax, 11
        ret
.green: cmp     ecx, 1
        jne     .blue
        shr     eax, 5
        and     eax, 63
        ret
.blue:  and     eax, 31
        ret

; eax = the first source column of a sliver in 16.16, ecx = the step
; between its samples: carry set and eax the sliver's mean colour when it
; is all of one, clear when there is a picture in it. The test walks
; thirty-two of its rows at each of the seventeen columns and asks how
; far from the mean they sit, so one streak across an otherwise plain
; sliver - the vendor logo's - still counts as plain. edx, esi and edi
; kept.
flatness:
        push    edx
        push    esi
        push    edi
        push    ebx
        mov     [ebp + 0x94], eax
        mov     [ebp + 0x88], ecx
        mov     eax, [ebp + 4]          ; the rows it steps by
        shr     eax, 5
        jnz     .step
        mov     eax, 1
.step:  mov     [ebp + 0x8c], eax
        xor     eax, eax
        mov     [ebp + 0x74], eax
        mov     [ebp + 0x78], eax
        mov     [ebp + 0x7c], eax
        mov     [ebp + 0x70], eax
        mov     dword [ebp + 0x64], 0   ; how many of them are black
        mov     ebx, NSEG + 1           ; the sums, column by column
.column:
        mov     eax, [ebp + 0x94]
        shr     eax, 16
        mov     [ebp + 0x90], eax
        xor     edx, edx
.row:   mov     eax, edx
        imul    eax, [ebp + 0]
        add     eax, [ebp + 0x90]
        lea     esi, [eax * 2]
        add     esi, [ebp + 0x34]
        movzx   eax, word [esi]
        push    eax
        push    edx
        call    lum
        cmp     eax, BLACK
        ja      .notblack
        inc     dword [ebp + 0x64]
.notblack:
        pop     edx
        pop     eax
        lea     edi, [ebp + 0x74]
        call    addpixel
        inc     dword [ebp + 0x70]
        add     edx, [ebp + 0x8c]
        cmp     edx, [ebp + 4]
        jb      .row
        mov     eax, [ebp + 0x88]
        add     [ebp + 0x94], eax
        dec     ebx
        jnz     .column
        mov     ecx, [ebp + 0x70]
        lea     edi, [ebp + 0x74]
        call    mean565
        mov     [ebp + 0xa0], eax
        mov     eax, [ebp + 0x64]       ; mostly black: black, and no more asked of it
        imul    eax, MOSTLY + 1
        mov     ecx, [ebp + 0x70]
        imul    ecx, MOSTLY
        cmp     eax, ecx
        jb      .spread
        mov     dword [ebp + 0xa0], 0
        jmp     .flat
.spread:                                ; else how far the samples sit from the mean
        mov     eax, [ebp + 0x88]
        imul    eax, NSEG + 1
        sub     [ebp + 0x94], eax
        mov     dword [ebp + 0x7c], 0
        mov     ebx, NSEG + 1
.column2:
        mov     eax, [ebp + 0x94]
        shr     eax, 16
        mov     [ebp + 0x90], eax
        xor     edx, edx
.row2:  mov     eax, edx
        imul    eax, [ebp + 0]
        add     eax, [ebp + 0x90]
        lea     esi, [eax * 2]
        add     esi, [ebp + 0x34]
        movzx   eax, word [esi]
        call    apart
        add     [ebp + 0x7c], eax
        add     edx, [ebp + 0x8c]
        cmp     edx, [ebp + 4]
        jb      .row2
        mov     eax, [ebp + 0x88]
        add     [ebp + 0x94], eax
        dec     ebx
        jnz     .column2
        mov     eax, [ebp + 0x7c]
        xor     edx, edx
        div     dword [ebp + 0x70]
        cmp     eax, FLAT
        jbe     .flat
        mov     eax, [ebp + 0xa0]       ; or the mean is dark enough to read as black anyway
        mov     edx, eax
        shr     edx, 11
        mov     ecx, edx
        mov     edx, eax
        shr     edx, 6
        and     edx, 31
        add     ecx, edx
        mov     edx, eax
        and     edx, 31
        add     ecx, edx
        cmp     ecx, DARK
        ja      .picture
        mov     dword [ebp + 0xa0], 0   ; dark enough to read as black: black, with nothing of the picture in it
.flat:  mov     eax, [ebp + 0xa0]
        pop     ebx
        pop     edi
        pop     esi
        pop     edx
        stc
        ret
.picture:
        mov     eax, [ebp + 0xa0]
        pop     ebx
        pop     edi
        pop     esi
        pop     edx
        clc
        ret

; eax = a 565 pixel: eax = how far its channels sit from the mean at
; +0xa0, five bits each. ecx, edx, esi and edi kept.
apart:
        push    ecx
        push    edx
        push    esi
        mov     esi, [ebp + 0xa0]
        mov     ecx, eax
        shr     ecx, 11                 ; red
        mov     edx, esi
        shr     edx, 11
        sub     ecx, edx
        call    .abs
        mov     edx, ecx
        mov     ecx, eax
        shr     ecx, 6                  ; green, its top five, so it weighs as much as the others
        and     ecx, 31
        push    edx
        mov     edx, esi
        shr     edx, 6
        and     edx, 31
        sub     ecx, edx
        call    .abs
        pop     edx
        add     edx, ecx
        mov     ecx, eax
        and     ecx, 31                 ; blue
        push    edx
        mov     edx, esi
        and     edx, 31
        sub     ecx, edx
        call    .abs
        pop     edx
        lea     eax, [edx + ecx]
        pop     esi
        pop     edx
        pop     ecx
        ret
.abs:   test    ecx, ecx
        jns     .out
        neg     ecx
.out:   ret

; eax = a 565 pixel, edi = three sums: its channels onto them. ecx, edx
; and esi kept.
addpixel:
        push    edx
        mov     edx, eax
        shr     edx, 11
        add     [edi], edx              ; red, five bits
        mov     edx, eax
        shr     edx, 5
        and     edx, 63
        add     [edi + 4], edx          ; green, all six bits, so a plain colour comes back as itself
        and     eax, 31
        add     [edi + 8], eax
        pop     edx
        ret

; edi = three sums, ecx = the rows they cover: eax = their mean as a 565
; pixel. ecx, edx and esi kept.
mean565:
        push    ecx
        push    edx
        mov     eax, [edi]
        xor     edx, edx
        div     ecx
        shl     eax, 11
        push    eax
        mov     eax, [edi + 4]
        xor     edx, edx
        div     ecx
        shl     eax, 5
        pop     edx
        or      eax, edx
        push    eax
        mov     eax, [edi + 8]
        xor     edx, edx
        div     ecx
        pop     edx
        or      eax, edx
        pop     edx
        pop     ecx
        ret

; edi = a destination, ecx = pixels, eax = a 565 pixel: the span filled,
; at the surface's depth. edx and esi kept.
span:
        test    ecx, ecx
        jz      .out
        cmp     dword [ebp + 0x18], 32
        je      .wide
.narrow:
        stosw
        dec     ecx
        jnz     .narrow
        ret
.wide:  push    edx
        push    ebx
        call    pixel32
        pop     ebx
        pop     edx
.w:     stosd
        dec     ecx
        jnz     .w
.out:   ret

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
; +0x30 rows left, +0x34 the source, +0x38 the destination row, +0x3c
; and +0x40 the left and right bars' pixel for the row in hand, +0x44
; their width, +0x48 the source column the picture's last drawn one came
; from, +0x4c the blur's reach, +0x50 the row it is centred on, +0x54 and
; +0x58 the rows it runs between, +0x5c how many, +0x60 to +0x74 the six
; channel sums, +0x78 the bars' own walk down the picture.
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
        sub     esp, 0x2d0
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
        lea     esi, [eax * 2]
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
        lea     esp, [ebp + 0x2d0]
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
