; wide2d.asm - the 2D drawn in 640x480 terms, scaled to the back buffer,
; and the device's viewport with it.
;
; Every screen DLL, MainMode and the exe draw their menus, text and HUD
; as pre-transformed geometry, FVF 0x1c4, in 640x480 pixels whatever
; the buffer's size, through MGameD3D's draws: quads (vtable +0xb4,
; 0x10005120), triangles (+0xb0, 0x100050d0), triangle lists plain
; (+0xb8, 0x10004fe0) and indexed (+0xc4, 0x10005170), strips (+0xbc,
; 0x10005030) and fans (+0xc0, 0x10005080). MGameGL's 3D is
; untransformed (FVF 0x1e2 and 0x112, the device transforms it), so
; every draw with the FVF the game set (0x1001121c) at 0x1c4 is 2D.
; With that FVF and a buffer that is not 640x480, the vertices are
; scaled into a copy here and the copy is drawn: uniformly by height,
; centred, so the 4:3 layout keeps its shape in the middle of a wide
; picture; a quad that spans the whole width (a fade, a background) is
; stretched across instead; a tile at one edge is drawn out to the
; picture's edge, and a strip of a one-hue picture at one edge gets a
; bar of that hue beside it (see extend, texload). A list longer than
; the copy holds goes as it is. The first two entries replace the
; six-byte `mov edx, [0x10011220]` each draw begins with, the next four
; the list, indexed-list, strip and fan draws' first ten bytes, and
; each continues after them.
;
; What is a tile is settled by the frame before: each quad's width
; goes into a table (sizes, 16 widths, each with how many quads had
; it and the extent they covered); the present (+0x80, 0x10004d50,
; the eighth entry, its first eight bytes) starts a new table and
; keeps the last, and only a width that covered the whole 640x480
; last frame with at least six quads is a background's tile. A sprite
; sliding through the frame's edge, a button or a car, has no such
; width behind it and keeps its place.
;
; Vertex: x, y, z, rhw, diffuse, specular, u, v - 32 bytes.
;
; The device's viewport setter (vtable +0x158 of the second interface,
; 0x10006040: this, &{left, top, right, bottom, four fractions}) is the
; seventh entry: the exe sets the countdown's viewport on the device
; itself from its own table (0x5b24f0: 640x480, the split halves, the
; 800x600 set), a path MGameGL's SetViewport never sees, so a rect no
; wider than 640 and no taller than 480 while the picture is wider is
; scaled to the picture through a copy here; MGameGL's, in real pixels,
; pass.
;
; The ninth entry is in the texture create (0x1000411c, the first
; thirteen bytes after the system-memory copy is filled, esi = the
; texture's number, ebp = its description: pixels, size, format): the
; texture is marked in a table: a picture a bar can be drawn from, one
; so nearly black that the bar should be black instead, or nothing - a
; sprite, a palette, a render target.
;
; With `trace` set (the d3dtrace diagnostic) every draw through the six
; draw entries reports itself on OutputDebugStringA, the first 60000:
; "sr2 d e fvf count ret x0 y0 z0 tex kind", e the entry (q, t, l, i, s,
; f), ret the draw's return address (the loaddll lines say whose), the
; first vertex in hex before any scaling, the texture selected and what
; texload made of it. A quad that reaches barquad reports there too.

bits 32

%define MAGIC_SELFRVA   0xE7E7E7E7      ; this blob's RVA, filled at apply time
%define FVF             0x1121c         ; RVAs in MGameD3D.dll
%define FLAGS           0x11220         ; the draw flags the replaced mov loads
%define WIDTH           0x123fc         ; the back buffer's size
%define HEIGHT          0x12400
%define RESUME_QUAD     0x5126          ; after the bytes replaced
%define RESUME_TRI      0x50d6
%define RESUME_LIST     0x4fea
%define RESUME_INDEXED  0x517a
%define RESUME_STRIP    0x503a
%define RESUME_FAN      0x508a
%define STRIP           0x10000000      ; flags the count of a strip on the stack
%define FAN             0x08000000      ; and of a fan
%define TRIANGLES       0x12764         ; the count the list draws' second instruction loads
%define WRAP            0x11240         ; the texture addressing as last set through +0xf8: nonzero wraps
%define SETWRAP         0xf8            ; that method, in the vtable
%define TILE            0x43000000      ; 128.0: a clamped quad no wider than this is a tile
%define LIST            0x40000000      ; flags the count of a list on the stack
%define INDEXED         0x20000000      ; and of an indexed one
%define CAPACITY        2048            ; vertices the copy holds
%define RESUME_VIEWPORT 0x6049          ; the viewport setter after its first nine bytes
%define RESUME_PRESENT  0x4d58          ; the present after its first eight
%define FULLSCREEN      0x1240c         ; the present's first instruction loads it
%define NSIZES          16              ; widths the table holds, 24 bytes each
%define MINTILES        6               ; quads of a width, at least, for a background
%define IAT_LOADLIB     0xf114          ; MGameD3D's import slots
%define IAT_GETPROC     0xf0ac
%define RESUME_TEXLOAD  0x4129          ; the texture create after the thirteen bytes replaced
%define CURTEX          0x11224         ; the texture selected through +0xac, bit 31 none
%define SETTEX          0xac            ; that method, and the quad draw, in the vtable
%define DRAWQUAD        0xb4
%define NFILLS          128             ; textures the kind table holds
%define SETALPHA        0xe8            ; the device's alpha blending, its state cached at ALPHACACHE
%define ALPHACACHE      0x11234
%define SETBLEND        0xec            ; its blend factors, source and destination, as D3D numbers them
%define SETFILTER        0xfc            ; and its filtering: linear with a 1, nearest with a 0
%define BLEND_ONE       2               ; the factors: both ONE adds what is drawn to what is there,
%define BLEND_SRCALPHA  5               ; and the pair the game's own blending wants back after
%define BLEND_INVSRC    6
%define PASSES          8               ; the bar drawn this many times, added, each shifted a little down the
%define PASSDIM         10              ; picture, and at this much of the quad's colour, so they make 30 per
                                        ; cent between them. Each sits four of the picture's rows below the
                                        ; last, the step bgrow's own blur takes: an even number, so every pass
                                        ; lands on the same side of the picture's scanlines and they carry
                                        ; into the bar instead of averaging away (kblurstep).
%define KPICTURE        1               ; what a texture is, as texload leaves it: a picture a bar can be
%define KBLACK          2               ; drawn from, or one so nearly black that the bar should just be black
%define DARKPIX         6               ; a pixel whose channels add up to no more than this is black, and a
%define MOSTLY          3               ; texture this many quarters of them gets the second kind
%define PALETTED        0x700           ; the description's flags: a palette of one size or another
%define RENDERTGT       0x1000          ; and a render target
%define STRIPTALL       0x43200000      ; 160.0: a quad at least this tall gets a bar, not a plate sliding through

        jmp     near quad               ; +0
        jmp     near tri                ; +5
        jmp     near list               ; +10
        jmp     near indexed            ; +15
        jmp     near strip              ; +20
        jmp     near fan                ; +25
        jmp     near viewport           ; +30
        jmp     near present            ; +35
        jmp     near texload            ; +40

quad:   push    4
        jmp     draw
tri:    push    3
        jmp     draw
list:   push    dword [esp + 0xc]       ; the count, the third argument
        or      dword [esp], LIST
        jmp     draw
indexed:
        push    dword [esp + 0xc]       ; the vertex count, the third argument
        or      dword [esp], LIST | INDEXED
        jmp     draw
strip:  push    dword [esp + 0xc]       ; the count, the third argument
        or      dword [esp], LIST | STRIP
        jmp     draw
fan:    push    dword [esp + 0xc]
        or      dword [esp], LIST | FAN

; [esp] = the vertex count, [esp+4] the draw's return address, [esp+8]
; its `this`, [esp+0xc] the vertices. eax, ecx and edx are free at both
; sites. ebx = this blob, ebp = the image base.
draw:
        push    ebp
        push    ebx
        call    getbase
        cmp     dword [ebx + inbar], 0
        jne     .out                    ; the bar's own draw, in picture pixels already
        call    tracedraw
        cmp     dword [ebp + FVF], 0x1c4
        jne     .out
        mov     ecx, [esp + 8]          ; the count
        and     ecx, ~(LIST | INDEXED | STRIP | FAN)
        cmp     ecx, CAPACITY
        ja      .out
        cmp     dword [ebp + WIDTH], 640
        jne     .scale
        cmp     dword [ebp + HEIGHT], 480
        je      .out
.scale: push    esi
        push    edi
        mov     esi, [esp + 0x1c]       ; the vertices
        cmp     ecx, 4
        jne     .noquad
        call    tally
.noquad:
        lea     edi, [ebx + copy]
        push    ecx
        shl     ecx, 3
        rep movsd                       ; the copy
        pop     ecx
        lea     edi, [ebx + copy]
        mov     esi, edi
        fild    dword [ebp + HEIGHT]
        fdiv    dword [ebx + k480]      ; the scale, by height
        fild    dword [ebp + WIDTH]
        fld     st1
        fmul    dword [ebx + k640]
        fsubp   st1, st0
        fmul    dword [ebx + khalf]     ; the bar: (W - 640 * scale) / 2
        ; st0 = the bar, st1 = the scale
        fst     dword [ebx + bar]
        fld     st1
        fstp    dword [ebx + sc]
        push    ecx                     ; bit 16 set for an x at the left edge, 17 the right
.span:  fld     dword [esi]
        fcomp   dword [ebx + khalf]
        fnstsw  ax
        sahf
        jae     .right
        or      dword [esp], 0x10000
.right: fld     dword [esi]
        fcomp   dword [ebx + kalmost]
        fnstsw  ax
        sahf
        jb      .next
        or      dword [esp], 0x20000
.next:  add     esi, 32
        dec     ecx
        jnz     .span
        pop     ecx
        test    ecx, 0x10000
        jz      .centred
        test    ecx, 0x20000
        jz      .centred
        and     ecx, 0xffff             ; spans the width: x * W / 640, y * scale
        fstp    st0                     ; the bar goes
        fild    dword [ebp + WIDTH]
        fdiv    dword [ebx + k640]      ; st0 = the x scale, st1 = the y scale
.stretch:
        fld     dword [edi]
        fmul    st0, st1
        fstp    dword [edi]
        fld     dword [edi + 4]
        fmul    st0, st2
        fstp    dword [edi + 4]
        add     edi, 32
        dec     ecx
        jnz     .stretch
        jmp     .done
.centred:
        mov     [ebx + edges], ecx
        and     ecx, 0xffff             ; x * scale + the bar, y * scale
        push    ecx
.c:     fld     dword [edi]
        fmul    st0, st2
        fadd    st0, st1
        fstp    dword [edi]
        fld     dword [edi + 4]
        fmul    st0, st2
        fstp    dword [edi + 4]
        add     edi, 32
        dec     ecx
        jnz     .c
        pop     ecx
        call    extend
.done:  fstp    st0
        fstp    st0
        lea     eax, [ebx + copy]
        mov     [esp + 0x1c], eax       ; the draw takes the copy
        pop     edi
        pop     esi
.out:   mov     eax, [esp + 8]          ; the count
        test    eax, LIST
        jnz     .list
        mov     edx, [ebp + FLAGS]      ; the six bytes replaced
        cmp     eax, 4
        je      .quad
        add     ebp, RESUME_TRI
        jmp     .go
.quad:  add     ebp, RESUME_QUAD
        jmp     .go
.list:  mov     ecx, [ebp + TRIANGLES]  ; the ten bytes replaced: mov eax, [esp+0xc] (the indexed draw's [esp+0x14]); mov ecx, [triangles]
        test    eax, INDEXED
        jnz     .indexed
        test    eax, STRIP
        jnz     .strip
        test    eax, FAN
        jnz     .fan
        mov     eax, [esp + 0x18]
        add     ebp, RESUME_LIST
        jmp     .go
.strip: mov     eax, [esp + 0x18]
        add     ebp, RESUME_STRIP
        jmp     .go
.fan:   mov     eax, [esp + 0x18]
        add     ebp, RESUME_FAN
        jmp     .go
.indexed:
        mov     eax, [esp + 0x20]
        add     ebp, RESUME_INDEXED
.go:    mov     [esp + 8], ebp          ; the resume address over the count
        pop     ebx
        pop     ebp
        ret

; ebx = this blob and ebp = the image base, on return.
getbase:
        call    .here
.here:  pop     ebx
        sub     ebx, .here
        mov     ebp, ebx
        sub     ebp, MAGIC_SELFRVA
        ret

; [esp] = the return, [esp+4] this, [esp+8] the rect and fractions.
viewport:
        push    ebx
        push    ebp
        call    getbase
        cmp     dword [ebp + WIDTH], 640
        jbe     .out                    ; 640 wide or less: nothing to scale to
        mov     eax, [esp + 0x10]       ; the rect
        cmp     dword [eax + 8], 640
        jg      .out
        cmp     dword [eax + 0xc], 480
        jg      .out
        push    esi
        push    edi
        push    ecx
        mov     esi, eax
        lea     edi, [ebx + vpcopy]
        mov     ecx, 8
        rep movsd                       ; the copy, its fractions as they are
        lea     edi, [ebx + vpcopy]
        xor     ecx, ecx
.side:  mov     eax, [edi + ecx * 4]
        test    ecx, 1
        jnz     .y
        imul    eax, [ebp + WIDTH]
        push    edx
        cdq
        push    ecx
        mov     ecx, 640
        idiv    ecx
        pop     ecx
        pop     edx
        jmp     .put
.y:     imul    eax, [ebp + HEIGHT]
        push    edx
        cdq
        push    ecx
        mov     ecx, 480
        idiv    ecx
        pop     ecx
        pop     edx
.put:   mov     [edi + ecx * 4], eax
        inc     ecx
        cmp     ecx, 4
        jb      .side
        mov     [esp + 0x1c], edi       ; the rect argument, on the stack
        pop     ecx
        pop     edi
        pop     esi
.out:   lea     eax, [ebp + RESUME_VIEWPORT]
        pop     ebp
        pop     ebx
        sub     esp, 8                  ; the nine bytes replaced
        push    esi
        mov     esi, [esp + 0x14]
        push    edi
        jmp     eax

; [esp] = the return, [esp+4] this. A frame: the widths seen since the
; last present become the table extend consults.
present:
        push    ebx
        push    ebp
        call    getbase
        push    esi
        push    edi
        push    ecx
        lea     esi, [ebx + sizes]
        lea     edi, [ebx + lastsizes]
        mov     ecx, NSIZES * 6 + 1     ; the entries and the count
        rep movsd
        mov     dword [ebx + nsizes], 0
        pop     ecx
        pop     edi
        pop     esi
        mov     eax, [ebp + FULLSCREEN] ; the eight bytes replaced: mov eax, [fullscreen]; sub esp, 0x10
        lea     edx, [ebp + RESUME_PRESENT]
        pop     ebp
        pop     ebx
        sub     esp, 0x10
        jmp     edx

; The scan also keeps the texture coordinates at those four extremes, so
; a bar can follow the picture down its own edge.
;
; esi = a quad's vertices, in 640 terms: its width into the frame's
; table, with the extent quads of that width have covered. ecx kept.
tally:
        push    ecx
        push    edi
        mov     ecx, 4
        call    bbox
        fld     dword [ebx + bx1]
        fsub    dword [ebx + bx0]
        fstp    dword [ebx + bw]
        lea     edi, [ebx + sizes]
        mov     edx, [ebx + nsizes]
        call    find
        jnc     .have
        cmp     edx, NSIZES
        jae     .out                    ; the table is full: not counted
        mov     eax, [ebx + bw]
        mov     [edi], eax
        mov     dword [edi + 4], 0
        mov     eax, [ebx + bx0]
        mov     [edi + 8], eax
        mov     eax, [ebx + bx1]
        mov     [edi + 12], eax
        mov     eax, [ebx + by0]
        mov     [edi + 16], eax
        mov     eax, [ebx + by1]
        mov     [edi + 20], eax
        inc     dword [ebx + nsizes]
.have:  inc     dword [edi + 4]
        fld     dword [ebx + bx0]
        fcomp   dword [edi + 8]
        fnstsw  ax
        sahf
        jae     .x1
        mov     eax, [ebx + bx0]
        mov     [edi + 8], eax
.x1:    fld     dword [ebx + bx1]
        fcomp   dword [edi + 12]
        fnstsw  ax
        sahf
        jbe     .y0
        mov     eax, [ebx + bx1]
        mov     [edi + 12], eax
.y0:    fld     dword [ebx + by0]
        fcomp   dword [edi + 16]
        fnstsw  ax
        sahf
        jae     .y1
        mov     eax, [ebx + by0]
        mov     [edi + 16], eax
.y1:    fld     dword [ebx + by1]
        fcomp   dword [edi + 20]
        fnstsw  ax
        sahf
        jbe     .out
        mov     eax, [ebx + by1]
        mov     [edi + 20], eax
.out:   pop     edi
        pop     ecx
        ret

; esi = vertices, ecx = how many: their extent into bx0, bx1, by0, by1.
; esi and ecx kept.
bbox:
        push    esi
        push    ecx
        mov     eax, [esi]
        mov     [ebx + bx0], eax
        mov     [ebx + bx1], eax
        mov     eax, [esi + 4]
        mov     [ebx + by0], eax
        mov     [ebx + by1], eax
.v:     fld     dword [esi]
        fcomp   dword [ebx + bx0]
        fnstsw  ax
        sahf
        jae     .x1
        mov     eax, [esi]
        mov     [ebx + bx0], eax
.x1:    fld     dword [esi]
        fcomp   dword [ebx + bx1]
        fnstsw  ax
        sahf
        jbe     .y0
        mov     eax, [esi]
        mov     [ebx + bx1], eax
.y0:    fld     dword [esi + 4]
        fcomp   dword [ebx + by0]
        fnstsw  ax
        sahf
        jae     .y1
        mov     eax, [esi + 4]
        mov     [ebx + by0], eax
.y1:    fld     dword [esi + 4]
        fcomp   dword [ebx + by1]
        fnstsw  ax
        sahf
        jbe     .next
        mov     eax, [esi + 4]
        mov     [ebx + by1], eax
.next:  add     esi, 32
        dec     ecx
        jnz     .v
        pop     ecx
        pop     esi
        ret

; edi = a table, edx = its entries, [ebx+bw] = a width: edi at the entry
; within a pixel of it, or carry and edi at the free slot after them.
find:
        push    ecx
        mov     ecx, edx
        jecxz   .none
.e:     fld     dword [ebx + bw]
        fsub    dword [edi]
        fabs
        fcomp   dword [ebx + kone]
        fnstsw  ax
        sahf
        jb      .found
        add     edi, 24
        loop    .e
.none:  stc
        pop     ecx
        ret
.found: clc
        pop     ecx
        ret

; [ebx+bw] = a width: carry unless it was a background's tile last
; frame - at least MINTILES quads of it, covering the 640x480.
tiled:
        push    edi
        push    edx
        lea     edi, [ebx + lastsizes]
        mov     edx, [ebx + nlastsizes]
        call    find
        jc      .out
        cmp     dword [edi + 4], MINTILES
        jb      .no
        fld     dword [edi + 8]
        fcomp   dword [ebx + khalf]
        fnstsw  ax
        sahf
        ja      .no                     ; not from the left edge
        fld     dword [edi + 12]
        fcomp   dword [ebx + kalmost]
        fnstsw  ax
        sahf
        jb      .no                     ; nor to the right
        fld     dword [edi + 16]
        fcomp   dword [ebx + khalf]
        fnstsw  ax
        sahf
        ja      .no
        fld     dword [edi + 20]
        fcomp   dword [ebx + k479]
        fnstsw  ax
        sahf
        jb      .no
        clc
        jmp     .out
.no:    stc
.out:   pop     edx
        pop     edi
        ret

; ---- the trace ----------------------------------------------------------

; [esp+4] = the pushed ebx, then ebp, the count with its flags, the
; return, this, the vertices.
tracedraw:
        cmp     dword [ebx + trace], 0
        je      .done
        cmp     dword [ebx + left], 0
        je      .done
        dec     dword [ebx + left]
        pushad
        lea     edi, [ebx + line]
        lea     esi, [ebx + s_d]
        call    scat
        mov     eax, [esp + 0x20 + 0xc]         ; the entry, from the count's flags
        mov     ecx, eax
        and     ecx, 0xffff
        mov     dl, 'q'
        cmp     ecx, 4
        je      .kind
        mov     dl, 't'
        test    eax, LIST
        jz      .kind
        mov     dl, 'l'
        test    eax, INDEXED
        jz      .notidx
        mov     dl, 'i'
.notidx:
        test    eax, STRIP
        jz      .notstrip
        mov     dl, 's'
.notstrip:
        test    eax, FAN
        jz      .kind
        mov     dl, 'f'
.kind:  mov     al, dl
        stosb
        mov     al, ' '
        stosb
        mov     eax, [ebp + FVF]
        call    hex8
        mov     eax, ecx
        call    hex8
        mov     eax, [esp + 0x20 + 0x10]        ; the return
        call    hex8
        mov     esi, [esp + 0x20 + 0x18]        ; the vertices
        mov     eax, [esi]
        call    hex8
        mov     eax, [esi + 4]
        call    hex8
        mov     eax, [esi + 8]
        call    hex8
        mov     eax, [ebp + CURTEX]             ; the texture selected, and what texload made of it
        call    hex8
        xor     eax, eax
        mov     ecx, [ebp + CURTEX]
        cmp     ecx, NFILLS
        jae     .nokind
        mov     eax, [ebx + kinds + ecx * 4]
.nokind:
        call    hex8
        call    report
        popad
.done:  ret

; What barquad made of the quad in hand: "sr2 b why tex kind xmin xmax
; ymin ymax", why as barquad sets it, the extents in 640x480 terms.
tracebar:
        cmp     dword [ebx + trace], 0
        je      .done
        cmp     dword [ebx + left], 0
        je      .done
        dec     dword [ebx + left]
        pushad
        lea     edi, [ebx + line]
        lea     esi, [ebx + s_b]
        call    scat
        mov     eax, [ebx + barwhy]
        call    hex8
        mov     eax, [ebp + CURTEX]
        call    hex8
        mov     eax, [ebx + barkind]
        call    hex8
        mov     eax, [ebx + xmin]
        call    hex8
        mov     eax, [ebx + xmax]
        call    hex8
        mov     eax, [ebx + ymin]
        call    hex8
        mov     eax, [ebx + ymax]
        call    hex8
        call    report
        popad
.done:  ret

; What texload made of the texture: "sr2 t why slot flags size first bad
; left kind", why 1 past the table, 2 paletted or a render target, 3 no
; pixels, 4 a transparent pixel (a sprite), 5 the kind kept; first and
; bad the first pixel and the one that ended it, left the pixels still
; to go then.
tracetex:
        cmp     dword [ebx + trace], 0
        je      .done
        cmp     dword [ebx + left], 0
        je      .done
        dec     dword [ebx + left]
        pushad
        lea     edi, [ebx + line]
        lea     esi, [ebx + s_t]
        call    scat
        lea     esi, [ebx + texwhy]
        mov     ecx, 8
.field: mov     eax, [esi]
        push    ecx
        push    esi
        call    hex8
        pop     esi
        pop     ecx
        add     esi, 4
        loop    .field
        call    report
        popad
.done:  ret

; eax -> 8 hex digits at edi, then a space.
hex8:
        push    ecx
        mov     ecx, 8
.d:     rol     eax, 4
        push    eax
        and     eax, 0xf
        mov     al, [ebx + digits + eax]
        stosb
        pop     eax
        loop    .d
        mov     al, ' '
        stosb
        pop     ecx
        ret

scat:   lodsb
        test    al, al
        jz      .done
        stosb
        jmp     scat
.done:  ret

; the line at [ebx+line], ending at edi, to OutputDebugStringA.
report:
        mov     byte [edi], 0
        cmp     dword [ebx + fn_ods], 0
        jne     .have
        lea     eax, [ebx + s_kernel32]
        push    eax
        call    [ebp + IAT_LOADLIB]
        lea     ecx, [ebx + s_ods]
        push    ecx
        push    eax
        call    [ebp + IAT_GETPROC]
        mov     [ebx + fn_ods], eax
.have:  lea     eax, [ebx + line]
        push    eax
        call    [ebx + fn_ods]
        ret

s_d:        db 'sr2 d ', 0
s_b:        db 'sr2 b ', 0
s_t:        db 'sr2 t ', 0
s_kernel32: db 'kernel32.dll', 0
s_ods:      db 'OutputDebugStringA', 0
digits:     db '0123456789abcdef'
s_marker:   db 'D3DTRACE', 0            ; the patcher finds the flag by this
trace:      dd 0
        align 4
fn_ods:     dd 0
left:       dd 60000                    ; lines still to report
vpcopy:     times 8 dd 0                ; the viewport setter's rect and fractions, scaled
line:       times 128 db 0

; A quad or triangle with a vertex at or past one edge of the 640 - the
; left edge of a tiled background, say - is drawn out to the picture's
; edge on that side, its texture coordinate shifted at the same rate as
; across the rest of it for the distance that vertex moves, so a tiling
; texture goes on, scrolling or not. Only a tile-sized quad, no more
; than 128 by 128, of a width that tiled the whole frame last frame
; (tiled); a sprite passing through the edge has no such width behind
; it and keeps its 4:3 place. A wider or taller quad at the edge is a
; picture or a strip of one - the mode select's collage - and keeps its
; place too, but when it is tall the side area beside it gets the
; picture stretched into it (barquad). A clamped tile has wrap switched on
; for its draw through the device's own method; its cache then has the
; next clamp request applied again. ecx = the count, edges = the span
; bits; the copy at [ebx+copy], the originals at [esp+0x20] and the
; device at [esp+0x1c] (under the return here).
extend:
        mov     eax, [ebx + edges]
        and     eax, 0x30000
        jz      .none
        cmp     eax, 0x30000
        je      .none                   ; both edges: stretched already
        cmp     ecx, 4
        ja      .none                   ; a list is text, not a background
        push    esi
        push    edi
        mov     esi, [esp + 0x28]       ; the originals
        ; the leftmost and rightmost vertex, their x and u; the top and bottom
        fld     dword [esi]
        fst     dword [ebx + xmin]
        fstp    dword [ebx + xmax]
        fld     dword [esi + 4]
        fst     dword [ebx + ymin]
        fstp    dword [ebx + ymax]
        mov     eax, [esi + 24]
        mov     [ebx + umin], eax
        mov     [ebx + umax], eax
        mov     eax, [esi + 28]
        mov     [ebx + vmin], eax
        mov     [ebx + vmax], eax
        push    ecx
.scan:  fld     dword [esi + 4]
        fcomp   dword [ebx + ymin]
        fnstsw  ax
        sahf
        jae     .nottop
        mov     eax, [esi + 4]
        mov     [ebx + ymin], eax
        mov     eax, [esi + 28]
        mov     [ebx + vmin], eax
.nottop:
        fld     dword [esi + 4]
        fcomp   dword [ebx + ymax]
        fnstsw  ax
        sahf
        jbe     .notbottom
        mov     eax, [esi + 4]
        mov     [ebx + ymax], eax
        mov     eax, [esi + 28]
        mov     [ebx + vmax], eax
.notbottom:
        fld     dword [esi]
        fcomp   dword [ebx + xmin]
        fnstsw  ax
        sahf
        jae     .notmin
        mov     eax, [esi]
        mov     [ebx + xmin], eax
        mov     eax, [esi + 24]
        mov     [ebx + umin], eax
.notmin:
        fld     dword [esi]
        fcomp   dword [ebx + xmax]
        fnstsw  ax
        sahf
        jbe     .notmax
        mov     eax, [esi]
        mov     [ebx + xmax], eax
        mov     eax, [esi + 24]
        mov     [ebx + umax], eax
.notmax:
        add     esi, 32
        dec     ecx
        jnz     .scan
        pop     ecx
        ; shift = (umax - umin) * (bar / scale) / (xmax - xmin)
        fld     dword [ebx + xmax]
        fsub    dword [ebx + xmin]      ; dx
        fst     dword [ebx + bw]
        fld     st0
        fcomp   dword [ebx + ktile]
        fnstsw  ax
        sahf
        ja      .strip                  ; wider than a tile: a picture
        fld     dword [ebx + ymax]
        fsub    dword [ebx + ymin]
        fcomp   dword [ebx + ktile]
        fnstsw  ax
        sahf
        ja      .strip                  ; taller than a tile: a strip of one
        call    tiled
        jc      .thin                   ; not a background's tile
        fld     st0
        fcomp   dword [ebx + khalf]
        fnstsw  ax
        sahf
        jb      .thin                   ; no width to speak of
        cmp     dword [ebp + WRAP], 0
        jne     .shift                  ; wrapping already
        push    ecx                     ; a clamped tile: wrap for this draw
        push    edx
        mov     ecx, [esp + 0x24 + 8]   ; the device
        mov     edx, [ecx]
        push    1
        push    ecx
        call    [edx + SETWRAP]
        pop     edx
        pop     ecx
.shift:
        fld     dword [ebx + umax]
        fsub    dword [ebx + umin]      ; du
        fdivrp  st1, st0                ; du / dx, the rate
        fstp    dword [ebx + rate]
        fld     dword [ebx + bar]
        fdiv    dword [ebx + sc]
        fstp    dword [ebx + barpx]     ; the bar in 640 pixels
        jmp     .apply
.thin:  fstp    st0
        jmp     .out
.strip: fstp    st0
        call    barquad
        jmp     .out
.apply: mov     esi, [esp + 0x28]       ; the originals
        lea     edi, [ebx + copy]
.v:     fld     dword [esi]
        fcomp   dword [ebx + khalf]
        fnstsw  ax
        sahf
        jae     .notleft
        mov     dword [edi], 0          ; to the left edge: moved by x + bar
        fld     dword [esi]
        fadd    dword [ebx + barpx]
        fmul    dword [ebx + rate]
        fsubr   dword [edi + 24]
        fstp    dword [edi + 24]
        jmp     .next
.notleft:
        fld     dword [esi]
        fcomp   dword [ebx + kalmost]
        fnstsw  ax
        sahf
        jb      .next
        fild    dword [ebp + WIDTH]     ; to the right edge: moved by 640 + bar - x
        fstp    dword [edi]
        fld     dword [ebx + k640]
        fadd    dword [ebx + barpx]
        fsub    dword [esi]
        fmul    dword [ebx + rate]
        fadd    dword [edi + 24]
        fstp    dword [edi + 24]
.next:  add     esi, 32
        add     edi, 32
        dec     ecx
        jnz     .v
.out:   pop     edi
        pop     esi
.none:  ret

; A strip's bar. A quad at one edge, wider or taller than a tile and at
; least STRIPTALL tall, is a picture or a strip of one, and keeps its 4:3
; place; the side area beside it gets the picture itself, stretched. One
; quad, the texture still bound and its coordinates carried past the
; quad's own edge, so the bar is the 640's own sliver - a bar's share of
; the picture's width, in from that end - spread across the side area,
; sharp down the rows and soft across, which is what stretching a picture
; eight times over does. Its diffuse is the quad's halved, so it sits
; behind the picture; a texture all but black takes a black bar with no
; texture at all instead. ecx = the count, edges = the span bits; the
; copy at [ebx+copy], the originals at [esp+0x2c] and the device at
; [esp+0x28] (under the return here).
barquad:
        mov     dword [ebx + barkind], 0
        mov     dword [ebx + barwhy], 1         ; not a quad
        cmp     ecx, 4
        jne     .report
        mov     dword [ebx + barwhy], 2         ; not tall enough
        fld     dword [ebx + ymax]
        fsub    dword [ebx + ymin]
        fcomp   dword [ebx + kstrip]
        fnstsw  ax
        sahf
        jb      .report
        mov     dword [ebx + barwhy], 3         ; none selected, or past the table
        mov     eax, [ebp + CURTEX]
        cmp     eax, NFILLS
        jae     .report
        mov     eax, [ebx + kinds + eax * 4]
        mov     [ebx + barkind], eax
        mov     dword [ebx + barwhy], 4         ; a sprite, not a picture
        test    eax, eax
        jz      .report
        mov     dword [ebx + barwhy], 5         ; drawn
        push    esi
        push    edi
        fstp    dword [ebx + fpu1]              ; the bar and the scale, aside: the rest is the stack's
        fstp    dword [ebx + fpu0]
        mov     esi, [esp + 0x34]               ; the originals
        lea     edi, [ebx + barcopy]
        mov     ecx, 4
.vertex:
        mov     edx, [esi + 8]                  ; z and rhw as the quad's, no specular
        mov     [edi + 8], edx
        mov     edx, [esi + 12]
        mov     [edi + 12], edx
        xor     edx, edx
        mov     [edi + 20], edx
        add     edi, 32
        dec     ecx
        jnz     .vertex
        lea     edi, [ebx + barcopy]
        mov     eax, [esi + 16]                 ; the quad's diffuse, at a pass's share of the bar's brightness
        cmp     dword [ebx + barkind], KBLACK
        je      .black
        call    dimrgb
        jmp     .havediffuse
.black: and     eax, 0xff000000                 ; a picture that is all but black: a black bar, and no texture
.havediffuse:
        mov     [edi + 16], eax
        mov     [edi + 48], eax
        mov     [edi + 80], eax
        mov     [edi + 112], eax
        fld     dword [ebx + ymin]              ; the bar covers the quad's own rows, and takes their texture ones
        fmul    dword [ebx + sc]
        fst     dword [edi + 4]
        fstp    dword [edi + 36]
        fld     dword [ebx + ymax]
        fmul    dword [ebx + sc]
        fst     dword [edi + 68]
        fstp    dword [edi + 100]
        mov     eax, [ebx + vmin]
        mov     [edi + 28], eax
        mov     [edi + 60], eax
        mov     eax, [ebx + vmax]
        mov     [edi + 92], eax
        mov     [edi + 124], eax
        test    dword [ebx + edges], 0x10000
        jz      .right
        xor     eax, eax                        ; the left bar: the picture's own left, stretched from the
        mov     [edi], eax                      ; screen's edge to where the picture starts
        mov     [edi + 64], eax
        fldz
        call    uat
        fstp    dword [ebx + ubar0]
        fld     dword [ebx + xmin]
        fmul    dword [ebx + sc]
        fadd    dword [ebx + bar]
        fst     dword [edi + 32]
        fstp    dword [edi + 96]
        call    sliverx                 ; no further in than the quad itself reaches
        fld     dword [ebx + xmax]
        fcom    st1
        fnstsw  ax
        sahf
        jae     .haveleft
        fstp    st1
        jmp     .leftu
.haveleft:
        fstp    st0
.leftu: call    uat
        fstp    dword [ebx + ubar1]
        jmp     .draw
.right: fild    dword [ebp + WIDTH]             ; the right bar: the picture's own right, likewise
        fst     dword [edi + 32]
        fstp    dword [edi + 96]
        fld     dword [ebx + k640]
        call    uat
        fstp    dword [ebx + ubar1]
        fld     dword [ebx + k640]              ; its inner side sits at the picture's edge, or at the 640's
        fld     dword [ebx + xmax]              ; own where the quad runs past it
        fcom    st1
        fnstsw  ax
        sahf
        jbe     .haveright
        fstp    st0
        fld     dword [ebx + k640]
.haveright:
        fmul    dword [ebx + sc]
        fadd    dword [ebx + bar]
        fst     dword [edi]
        fstp    dword [edi + 64]
        fstp    st0
        fld     dword [ebx + k640]
        call    sliverx
        fsubp   st1, st0
        fld     dword [ebx + xmin]      ; no further in than the quad itself reaches
        fcom    st1
        fnstsw  ax
        sahf
        jbe     .haveright2
        fstp    st1
        jmp     .rightu
.haveright2:
        fstp    st0
.rightu:
        call    uat
        fstp    dword [ebx + ubar0]
.draw:  mov     eax, [ebp + CURTEX]
        mov     [ebx + savedtex], eax
        mov     dword [ebx + inbar], 1
        cmp     dword [ebx + barkind], KBLACK
        jne     .textured
        mov     ecx, [esp + 0x30]               ; the device
        mov     edx, [ecx]
        push    -1
        push    ecx
        call    [edx + SETTEX]                  ; nothing of the picture: the diffuse alone
        mov     eax, [ebx + ubar0]             ; and one pass of it, with nothing to blur
        mov     [edi + 24], eax
        mov     [edi + 88], eax
        mov     eax, [ebx + ubar1]
        mov     [edi + 56], eax
        mov     [edi + 120], eax
        mov     ecx, [esp + 0x30]
        mov     edx, [ecx]
        push    edi
        push    ecx
        call    [edx + DRAWQUAD]
        mov     ecx, [esp + 0x30]
        mov     edx, [ecx]
        push    dword [ebx + savedtex]
        push    ecx
        call    [edx + SETTEX]
        jmp     .done
.textured:                                      ; the passes add up, so the bar is their mean: a blur across
        mov     eax, [ebp + ALPHACACHE]
        mov     [ebx + savedblend], eax
        mov     ecx, [esp + 0x30]
        mov     edx, [ecx]
        push    1
        push    ecx
        call    [edx + SETFILTER]               ; linear, so the stretch does not come out in texels
        mov     ecx, [esp + 0x30]
        mov     edx, [ecx]
        push    BLEND_ONE                       ; both factors ONE: what is drawn is added to what is there
        push    BLEND_ONE
        push    ecx
        call    [edx + SETBLEND]
        mov     eax, [ebp + WRAP]               ; and clamped, so a pass shifted past the texture's edge
        mov     [ebx + savedwrap], eax          ; carries its last column out rather than starting again
        test    eax, eax
        jz      .clamped
        mov     ecx, [esp + 0x30]
        mov     edx, [ecx]
        push    0
        push    ecx
        call    [edx + SETWRAP]
.clamped:
        mov     ecx, [esp + 0x30]
        mov     edx, [ecx]
        push    1
        push    ecx
        call    [edx + SETALPHA]
        mov     eax, [ebx + ubar0]              ; across the bar the stretch itself does the smoothing, so the
        mov     [edi + 24], eax                 ; passes stay where they are and walk down the picture instead
        mov     [edi + 88], eax
        mov     eax, [ebx + ubar1]
        mov     [edi + 56], eax
        mov     [edi + 120], eax
        fld     dword [ebx + vmax]              ; a pass's step, in the quad's own texture rows
        fsub    dword [ebx + vmin]
        fmul    dword [ebx + kblurstep]
        fld     dword [ebx + ymax]
        fsub    dword [ebx + ymin]
        fdivp   st1, st0
        fst     dword [ebx + ushift]
        fmul    dword [ebx + kfirst]            ; the first sits half of it above the others
        fstp    dword [ebx + ucur]
        mov     ecx, PASSES
.pass:  push    ecx
        fld     dword [ebx + vmin]
        fadd    dword [ebx + ucur]
        fst     dword [edi + 28]
        fstp    dword [edi + 60]
        fld     dword [ebx + vmax]
        fadd    dword [ebx + ucur]
        fst     dword [edi + 92]
        fstp    dword [edi + 124]
        fld     dword [ebx + ucur]
        fadd    dword [ebx + ushift]
        fstp    dword [ebx + ucur]
        mov     ecx, [esp + 0x34]
        mov     edx, [ecx]
        push    edi
        push    ecx
        call    [edx + DRAWQUAD]
        pop     ecx
        dec     ecx
        jnz     .pass
        mov     ecx, [esp + 0x30]               ; blending back as it was, and the factors the game's own wants
        mov     edx, [ecx]
        push    dword [ebx + savedblend]
        push    ecx
        call    [edx + SETALPHA]
        mov     ecx, [esp + 0x30]
        mov     edx, [ecx]
        push    BLEND_INVSRC
        push    BLEND_SRCALPHA
        push    ecx
        call    [edx + SETBLEND]
        cmp     dword [ebx + savedwrap], 0
        je      .done
        mov     ecx, [esp + 0x30]
        mov     edx, [ecx]
        push    dword [ebx + savedwrap]
        push    ecx
        call    [edx + SETWRAP]
.done:  mov     dword [ebx + inbar], 0
        fld     dword [ebx + fpu0]
        fld     dword [ebx + fpu1]
        pop     edi
        pop     esi
.report:
        call    tracebar
        ret

; eax = a colour: eax = it at a pass's share of the bar's brightness,
; its alpha kept. ecx, edx, esi and edi kept.
dimrgb:
        push    ecx
        push    edx
        push    esi
        mov     esi, eax
        xor     edx, edx
        mov     ecx, 0
.channel:
        mov     eax, esi
        shr     eax, cl
        and     eax, 0xff
        imul    eax, PASSDIM
        shr     eax, 8
        shl     eax, cl
        or      edx, eax
        add     ecx, 8
        cmp     ecx, 24
        jb      .channel
        mov     eax, esi
        and     eax, 0xff000000
        or      eax, edx
        pop     esi
        pop     edx
        pop     ecx
        ret

; st0 = an x in the 640's terms: st0 = the quad's texture coordinate
; there, its own u carried on past its edges. Every register kept.
uat:
        fsub    dword [ebx + xmin]
        fld     dword [ebx + umax]
        fsub    dword [ebx + umin]
        fmulp   st1, st0
        fld     dword [ebx + xmax]
        fsub    dword [ebx + xmin]
        fdivp   st1, st0
        fadd    dword [ebx + umin]
        ret

; st0 = the 640's own sliver: as much of it as a bar covers, were the
; whole picture stretched to the picture's width behind it, which is what
; the .bg screens do. Every register kept.
sliverx:
        fld     dword [ebx + k640]
        fmul    dword [ebx + bar]
        fidiv   dword [ebp + WIDTH]
        ret

; The ninth entry, in the texture create: esi = the texture's number,
; ebp = its description (pixels, size, format - 0 and 2 are 1555 by
; now, the screen DLLs' loaders having expanded a 565 texture in place
; with bit 15 set, 8 is 4444, a palette or a render target elsewhere in
; the flags). Its fill into the table: 0xff000000 with the mean colour
; when every pixel is opaque, else 0. Then the thirteen bytes replaced,
; and on.
texload:
        push    ebp                     ; the description
        push    ebx
        call    getbase
        xor     eax, eax
        mov     [ebx + texkind], eax
        mov     [ebx + texflags], eax
        mov     [ebx + texsize], eax
        mov     [ebx + texfirst], eax
        mov     [ebx + texbad], eax
        mov     [ebx + texslot], esi
        mov     dword [ebx + texwhy], 1 ; past the table
        cmp     esi, NFILLS
        jae     .out
        mov     dword [ebx + kinds + esi * 4], 0
        push    esi
        push    edi
        mov     edi, [esp + 0xc]        ; the description
        mov     eax, [edi + 8]
        mov     [ebx + texflags], eax
        mov     dword [ebx + texwhy], 2 ; paletted or a render target: not a picture
        test    eax, PALETTED | RENDERTGT
        jnz     .done
        and     eax, 8                  ; 4444, else the 16-bit format, which is 1555 by here
        mov     [ebx + fmt], eax
        mov     eax, [edi + 4]
        mov     [ebx + texsize], eax
        imul    eax, eax
        test    eax, eax
        mov     dword [ebx + texwhy], 3 ; no pixels
        jz      .done
        mov     [ebx + npix], eax
        mov     dword [ebx + nblack], 0
        mov     esi, [edi]              ; the pixels
        movzx   eax, word [esi]
        mov     [ebx + texfirst], eax
        mov     ecx, [ebx + npix]
.pixel: movzx   eax, word [esi]
        add     esi, 2
        call    texel                   ; eax, edx, edi = red, green and blue
        jc      .clear                  ; a clear pixel: a sprite, and no bar drawn from it
        add     eax, edx
        add     eax, edi
        cmp     eax, DARKPIX
        ja      .notdark
        inc     dword [ebx + nblack]
.notdark:
        dec     ecx
        jnz     .pixel
        mov     edx, [ebx + nblack]     ; a picture, or one so nearly black that a bar of it should be black
        shl     edx, 2
        mov     ecx, [ebx + npix]
        imul    ecx, MOSTLY
        mov     eax, KPICTURE
        cmp     edx, ecx
        jb      .kind
        mov     eax, KBLACK
.kind:  mov     [ebx + texkind], eax
        mov     ecx, [esp + 4]          ; the texture's number
        mov     [ebx + kinds + ecx * 4], eax
        mov     dword [ebx + texwhy], 5 ; kept
        jmp     .done
.clear: movzx   eax, word [esi - 2]     ; the pixel that ended it, and how many were left
        mov     [ebx + texbad], eax
        mov     [ebx + texleft], ecx
        mov     dword [ebx + texwhy], 4
.done:  pop     edi
        pop     esi
.out:   xor     eax, eax                ; the thirteen bytes replaced: xor eax, eax; mov ecx, 0x1f; lea edi, [esp+0x20]; rep stosd
        mov     ecx, 0x1f
        lea     edi, [esp + 0x28]       ; [esp+0x20] under the two pushed here
        rep     stosd
        call    tracetex
        lea     edx, [ebp + RESUME_TEXLOAD]
        pop     ebx
        pop     ebp
        jmp     edx

; eax = a pixel of the format at [ebx+fmt]: eax, edx, edi = its red,
; green and blue in 5 bits, or carry when it is not opaque. ecx kept.
texel:
        cmp     dword [ebx + fmt], 8
        je      .t4444
        test    eax, 0x8000             ; 1555
        jz      .clear
        mov     edx, eax
        shr     edx, 5
        and     edx, 31
        mov     edi, eax
        and     edi, 31
        shr     eax, 10
        and     eax, 31
        clc
        ret
.t4444: mov     edx, eax
        shr     edx, 12
        cmp     edx, 15
        jne     .clear
        mov     edx, eax
        shr     edx, 4
        and     edx, 15
        mov     edi, eax
        and     edi, 15
        shr     eax, 8
        and     eax, 15
        call    .widen
        xchg    eax, edx
        call    .widen
        xchg    eax, edx
        xchg    eax, edi
        call    .widen
        xchg    eax, edi
        clc
        ret
.widen: push    edx                     ; eax = 4 bits -> 5: v * 2 + v / 8
        mov     edx, eax
        shr     edx, 3
        lea     eax, [eax + eax + edx]
        pop     edx
        ret
.clear: stc
        ret

ktile:      dd TILE
kstrip:     dd STRIPTALL
kblurstep:  dd 0x40800000                   ; 4.0: the picture's rows between one pass and the next
kfirst:     dd 0xC0600000                   ; -3.5: where the first of them starts
k640:       dd 0x44200000               ; 640.0
k480:       dd 0x43F00000               ; 480.0
khalf:      dd 0x3F000000               ; 0.5
kalmost:    dd 0x441FC000               ; 639.0
k479:       dd 0x43EF8000               ; 479.0
kone:       dd 0x3F800000               ; 1.0
        align 4
bar:        dd 0                        ; the scaling in force: the bar, the scale
sc:         dd 0
edges:      dd 0                        ; the span bits of the vertices in hand
xmin:       dd 0                        ; extend's leftmost and rightmost x and their u, top and bottom y
ymin:       dd 0
ymax:       dd 0
xmax:       dd 0
umin:       dd 0
umax:       dd 0
vmin:       dd 0                        ; the texture rows the top and bottom fall on
vmax:       dd 0
rate:       dd 0                        ; du / dx across the quad, and the bar in 640 pixels
barpx:      dd 0
bx0:        dd 0                        ; bbox's extent; bw the width in hand
bx1:        dd 0
by0:        dd 0
by1:        dd 0
bw:         dd 0
            db 'BARFLAG', 0             ; the test finds the flag by this
inbar:      dd 0                        ; set while the bar's own draw goes through the quad entry
savedtex:   dd 0                        ; the texture selected before the bar's draw
barwhy:     dd 0                        ; what barquad made of the quad in hand, for the trace
barkind:    dd 0
texwhy:     dd 0                        ; what texload made of the texture, for the trace: these eight in order
texslot:    dd 0
texflags:   dd 0
texsize:    dd 0
texfirst:   dd 0
texbad:     dd 0
texleft:    dd 0
texkind:    dd 0
fpu0:       dd 0                        ; the FPU stack's two values, aside for the bar's draw
fpu1:       dd 0
fmt:        dd 0                        ; texload's: the pixels' format, how many there are, and how
npix:       dd 0                        ; many of them are black
nblack:     dd 0
ubar0:      dd 0                        ; the bar's two texture coordinates, at its first vertex and its
ubar1:      dd 0                        ; second; a pass's step down the picture, and where it has got to
ushift:     dd 0
ucur:       dd 0
savedblend: dd 0                        ; whether the device was blending before the bar, and how it addressed
savedwrap:  dd 0
            db 'FILLTABLE', 0, 0, 0         ; the test finds the table by this
kinds:      times NFILLS dd 0           ; what each texture is: a picture, a black one, or nothing
barcopy:    times 4 * 32 db 0           ; the bar quad
sizes:      times NSIZES * 6 dd 0       ; this frame's widths: width, quads, left, right, top, bottom
nsizes:     dd 0
lastsizes:  times NSIZES * 6 dd 0       ; last frame's, and its count
nlastsizes: dd 0
        align 16
copy:       times CAPACITY * 32 db 0
