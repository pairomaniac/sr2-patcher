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
; picture's edge, and a picture's strip at one edge gets the picture
; itself stretched into the side area beside it (see extend, barquad).
; The race HUD - the 2D of a frame in which one of the HUD's own
; element callbacks ran, which the exe's stub in the element walker
; says (hud: wide.asm's walk entry finds the flag by its HUDFRAME
; marker and sets it, the present clears it; the HUD's text is queued
; by the callbacks and drawn as one list at the frame's end) - is
; anchored to a 16:9 frame instead of the 4:3 box: an element wholly in the left part of
; the 640 (past 268 nowhere) moves out to the frame's left edge, one
; wholly in the right part (short of 372 nowhere) to its right, the
; middle stays (see anchor).
; A list longer than the copy holds goes as it is. The first two entries replace the
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
; scaled into the picture's 4:3 box through a copy here, its fractions
; with it; MGameGL's, in real pixels, pass.
;
; The lobby - the Multiplayer menu - is the one screen that is not a
; draw: the exe blits its BMP strips into the back buffer itself,
; through IDirectDrawSurface4::Blt at 640x480 coordinates, so it lands
; in the picture's top-left. The present hooks that Blt in ddraw's own
; vtable, once, and a blit into the back buffer with a 640x480-sized
; rect goes to a 640x480 surface of the lobby's own instead; the
; present stretches that surface into the 4:3 box with one blit and
; fills the side areas (hookblt, blt, lobbypresent).
;
; The .bg pictures - the title, the loading, game-over and course
; screens - are drawn by the exe's and Title.dll's own row copies,
; which bgrow.asm takes over; bgrow composes each at source size into a
; surface kept here (bgsurf, made at the present, found by bgrow
; through its marker in the annex), and the next draw or present
; stretches it into the whole screen with one blit (bgflush).
;
; The ninth entry is in the texture create (0x1000411c, the first
; thirteen bytes after the system-memory copy is filled, esi = the
; texture's number, ebp = its description: pixels, size, format): the
; texture is marked in a table: a picture a bar can be drawn from, one
; so nearly black that the bar should be black instead, or nothing - a
; sprite, a palette, a render target.
;
; With `trace` set (the d3dtrace diagnostic) every present reports
; "sr2 p", a frame's end, and every draw through the six
; draw entries reports itself on OutputDebugStringA and to
; logs\d3dtrace.log beside the exe, the first 400000 -
; at 2 (d3dtrace2d) only the 2D that is not a quad, the lists, strips
; and fans, since the menus' quads fill the 400000 in a couple of minutes:
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
%define IAT_GETMODFN    0xf038
%define MAX_PATH        260
%define PATHBUF         MAX_PATH + 24   ; room for logs\ and the name after the directory
%define GENERIC_WRITE   0x40000000
%define FILE_SHARE_READ 1
%define CREATE_ALWAYS   2
%define FILE_ATTRIBUTE_NORMAL 0x80
%define RESUME_TEXLOAD  0x4129          ; the texture create after the thirteen bytes replaced
%define CURTEX          0x11224         ; the texture selected through +0xac, bit 31 none
%define BACKBUF         0x12554         ; the back buffer surface, and the primary before it
%define VT_BLT          0x14            ; IDirectDrawSurface4::Blt in its vtable
%define PAGE_RWX        0x40            ; PAGE_EXECUTE_READWRITE
%define VT_LOCK         0x64            ; IDirectDrawSurface4::Lock, Unlock and Release in its vtable
%define VT_UNLOCK       0x80
%define VT_RELEASE      0x8
%define DDRAW4          0x1254c         ; MGameD3D's IDirectDraw4, and CreateSurface in its vtable
%define VT_CREATESURFACE 0x18
%define DDSD_CAPS       0x1
%define DDSD_HEIGHT     0x2
%define DDSD_WIDTH      0x4
%define DDSCAPS_OFFSCREENPLAIN 0x40
%define DDSCAPS_VIDEOMEMORY    0x4000
%define LOBBYLIVE       8               ; presents the lobby's surface is stretched for after its last blit
%define BGSURFW         2176            ; the .bg pictures' surface: room for an 800x600 picture with side
%define BGSURFH         600             ; areas each as wide as a 32:9 screen's - 666 of its columns
%define DDLOCK_WAIT     0x1
%define DDLOCK_READONLY 0x10
%define DDBLT_COLORFILL 0x400
%define DDBLT_WAIT      0x1000000
%define SETTEX          0xac            ; that method, and the quad draw, in the vtable
%define DRAWQUAD        0xb4
%define SETALPHA        0xe8            ; the device's alpha blending, its state cached at ALPHACACHE
%define ALPHACACHE      0x11234
%define SETBLEND        0xec            ; its blend factors, source and destination, as D3D numbers them
%define SETFILTER       0xfc            ; and its filtering: linear with a 1, nearest with a 0
%define BLEND_ONE       2               ; the factors: both ONE adds what is drawn to what is there,
%define BLEND_SRCALPHA  5               ; and the pair the game's own blending wants back after
%define BLEND_INVSRC    6
%define PASSES          16              ; the bar drawn this many times, added, spread across kblurpx of the
%define PASSSHARE       17              ; 640's pixels, each at 17/256 of the quad's colour: sixteen of them
                                        ; make 255 for 255
%define DIM             0x66            ; the bar at this much of the quad's colour, eight bits of fraction:
                                        ; two fifths, so it sits behind the picture
%define NKINDS          128             ; textures the kind table holds
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
        call    bgflush                 ; a .bg composed since the last draw goes in first
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
        call    anchor                  ; a HUD element moved out to the 16:9 frame
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

; The HUD anchored to a 16:9 frame, for a draw from one of the HUD's
; callbacks (hud): a piece wholly in the left part of the 640 (no vertex
; past 268) moves left, one wholly in the right part (none short of
; 372) moves right, by min(bar, 2H/9) - the 4:3 box's edge to the
; edge of a 16:9 frame no wider than the picture - so at 16:9 the
; piece sits at the picture's edge, on a wider picture at a centred
; 16:9's, on a narrower one (16:10) at the picture's; 4:3 has no bar
; and moves nothing. A piece is the draw - a quad, a triangle, a strip
; or a fan - or, in a list of quads (four vertices each, the race's
; text is one list of glyphs from both sides), each run of adjacent
; quads in it: a string's glyphs, whose left ends fall within kgap of
; the run's right end so far, move together. The middle keeps its
; place. So does a quad, triangle, strip or fan touching the 640's
; edges - a tile or a fade, which extend handles - but not a list: a
; list from a HUD callback is text, and a string that reaches the edge
; (the two-digit place after POSITION, 591 to 639.5) moves out with the
; rest rather than sitting at the 4:3 box's edge until it shortens.
; A piece wholly between 224 and 256 down - the band between split
; screen's halves, where the position bar's car icons and their 1P/2P
; labels ride along a bar drawn through MGameGL and so not moved - stays
; too; the halves' own HUD lies outside it. ecx = the count, edges = the span bits; the copy at [ebx+copy], the
; originals at [esp+0x20], the count's flags at [esp+0x14]. Every
; register kept, the FPU's two values left alone.
anchor:
        cmp     dword [ebx + hud], 0
        je      .out
        test    dword [esp + 0x14], LIST
        jz      .edges
        test    dword [esp + 0x14], STRIP | FAN
        jz      .go                     ; a list of quads: text, whatever it touches
.edges: test    dword [ebx + edges], 0x30000
        jnz     .out
.go:    pushad
        mov     eax, [ebx + huddrawlo]  ; the exe's own HUD draws only, once it has said which they are
        test    eax, eax
        jz      .shift
        mov     edx, [esp + 0x20 + 0x18]        ; the draw's return address; ecx is the count
        cmp     edx, eax
        jb      .none
        cmp     edx, [ebx + huddrawhi]
        ja      .none
.shift: fild    dword [ebp + HEIGHT]
        fmul    dword [ebx + k2over9]   ; the shift: the smaller of 2H/9 and the bar
        fld     dword [ebx + bar]
        fcom    st1
        fnstsw  ax
        sahf
        jae     .least
        fxch    st1
.least: fstp    st0
        fstp    dword [ebx + hshift]
        mov     edx, ecx                ; the piece: the draw, or a quad of a list of them
        mov     eax, [esp + 0x20 + 0x14]
        test    eax, LIST
        jz      .pieces
        test    eax, STRIP | FAN
        jnz     .pieces
        test    ecx, 3
        jnz     .pieces
        mov     edx, 4
.pieces:
        mov     esi, [esp + 0x20 + 0x20]        ; the originals, and the copy alongside
        lea     edi, [ebx + copy]
.run:   xor     eax, eax                ; a run of adjacent pieces: its bits (0 a vertex past the left
        push    eax                     ; part, 1 one short of the right, 2 one out of the band), its vertices, its right end
        push    eax
.piece: push    ecx
        push    0
        mov     ecx, edx
        fld     dword [esi]             ; the piece's own bits and extent
        fld     st0
.v:     mov     eax, [esi + 4]          ; y, as an int: positive floats order as ints
        cmp     eax, 0x43600000         ; 224.0
        jb      .outband
        cmp     eax, 0x43800000         ; 256.0
        jbe     .inband
.outband:
        or      dword [esp], 4
.inband:
        fld     dword [esi]
        fcomp   dword [ebx + kthird]
        fnstsw  ax
        sahf
        jbe     .short
        or      dword [esp], 1
.short: fld     dword [esi]
        fcomp   dword [ebx + k2third]
        fnstsw  ax
        sahf
        jae     .lo
        or      dword [esp], 2
.lo:    fld     dword [esi]             ; st2 = the least x so far, st1 the greatest
        fcom    st2
        fnstsw  ax
        sahf
        jae     .hi
        fxch    st2
.hi:    fcom    st1
        fnstsw  ax
        sahf
        jbe     .nx
        fxch    st1
.nx:    fstp    st0
        add     esi, 32
        dec     ecx
        jnz     .v
        pop     eax
        pop     ecx
        push    eax                     ; the piece's bits, kept from the status word below
        ; st0 = the piece's greatest x, st1 its least; [esp+4] the run's vertices, [esp+8] its bits
        cmp     dword [esp + 4], 0
        je      .join                   ; the first piece starts the run
        fld     st1                     ; adjacent when its left end is within kgap of the run's right
        fsub    dword [ebx + runmax]
        fabs
        fcomp   dword [ebx + kgap]
        fnstsw  ax
        sahf
        jbe     .join
        fstp    st0                     ; not adjacent: the run ends before it, to be looked at again
        fstp    st0
        pop     eax
        sub     esi, 32 * 4             ; (a run is only ever of quads)
        add     ecx, 4
        jmp     .end
.join:  fstp    dword [ebx + runmax]
        fstp    st0
        pop     eax
        or      [esp + 4], eax
        add     [esp], edx
        sub     ecx, edx
        jnz     .piece
.end:   pop     edx                     ; the run's vertices and bits; the piece size is done with
        pop     eax
        test    eax, 4
        jz      .stay                   ; within the band
        and     eax, 3
        cmp     eax, 3
        je      .stay                   ; across the middle
        fld     dword [ebx + hshift]
        test    eax, 1
        jz      .move                   ; the left part: minus
        fchs                            ; the right part: plus
.move:  push    ecx
        mov     ecx, edx
.x:     fld     dword [edi]
        fsub    st0, st1
        fstp    dword [edi]
        add     edi, 32
        dec     ecx
        jnz     .x
        pop     ecx
        fstp    st0
        jmp     .done
.stay:  shl     edx, 5
        add     edi, edx
.done:  mov     edx, 4                  ; only a list of quads runs on past its first piece
        test    ecx, ecx
        jnz     .run
.none:  popad
.out:   ret

; ebx = this blob and ebp = the image base, on return.
getbase:
        call    .here
.here:  pop     ebx
        sub     ebx, .here
        mov     ebp, ebx
        sub     ebp, MAGIC_SELFRVA
        ret

; [esp] = the return, [esp+4] this, [esp+8] the rect and fractions. The
; rect is left, top, right and bottom - the setter takes the width from
; right minus left - and not a corner and a size.
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
        call    scalerect               ; a 640x480 viewport stretched to the whole picture draws what
                                        ; is in it half again too large on a 32:9 one
        fild    dword [ebp + HEIGHT]    ; the fractions: the setter makes the clip volume from the rect's
        fmul    dword [ebx + k640]      ; share of the whole screen over them, so a rect the size of the
        fdiv    dword [ebx + k480]      ; 4:3 box on a wider screen draws what is in it larger by the
        fidiv   dword [ebp + WIDTH]     ; screen's width over the box's; the box's share of the width, into
        fld     dword [edi + 0x18]      ; both, gives the clip volume the 4:3 screen has
        fmul    st0, st1
        fstp    dword [edi + 0x18]
        fld     dword [edi + 0x1c]
        fmul    st0, st1
        fstp    dword [edi + 0x1c]
        fstp    st0
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

; edi = a rect in 640x480 terms, left, top, right, bottom: scaled in
; place into the picture's 4:3 box, everything by the height and both
; sides carried past the bar, as the 2D is. ecx, esi and edi kept.
scalerect:
        push    ecx
        push    edx
        mov     eax, 640                ; the bar the picture sits behind: (W - 640 * height / 480) / 2
        imul    eax, [ebp + HEIGHT]
        xor     edx, edx
        mov     ecx, 480
        div     ecx
        mov     ecx, [ebp + WIDTH]
        sub     ecx, eax
        shr     ecx, 1
        mov     [ebx + vpbar], ecx
        xor     ecx, ecx
.side:  mov     eax, [edi + ecx * 4]
        imul    eax, [ebp + HEIGHT]
        push    ecx
        cdq
        mov     ecx, 480
        idiv    ecx
        pop     ecx
        test    ecx, 1
        jnz     .put
        add     eax, [ebx + vpbar]
.put:   mov     [edi + ecx * 4], eax
        inc     ecx
        cmp     ecx, 4
        jb      .side
        pop     edx
        pop     ecx
        ret

; The lobby is DirectDraw, not a draw: BMP strips blitted into the back
; buffer at 640x480 coordinates, through IDirectDrawSurface4::Blt, and
; it lands in the picture's top-left unscaled. Scaling each blit into
; the box is a stretch per blit, which Wine does on the CPU; instead the
; lobby draws into a 640x480 surface of its own, in video memory,
; exactly as it drew into the back buffer, and the present stretches
; that surface into the box once a frame, video memory to video memory,
; and fills the side areas with the background's colour. ddraw's vtable
; is shared by every surface, so the present hooks its Blt entry once -
; VirtualProtect around the write - and every Blt into the back buffer
; (this = [BACKBUF]) whose rect is a 640x480 one is sent to the lobby's
; surface instead, cut to it; a rect bigger than 640x480, a null one,
; or another surface's, passes. Registers as a callee must leave them.
hookblt:
        push    ebx
        push    ebp
        call    getbase
        cmp     dword [ebx + bltorig], 0
        jne     .done                   ; hooked already
        mov     eax, [ebp + BACKBUF]
        test    eax, eax
        jz      .done                   ; no back buffer yet
        push    esi
        push    edi
        mov     esi, [eax]              ; its vtable, and the Blt entry
        lea     esi, [esi + VT_BLT]
        lea     eax, [ebx + s_kernel32]
        push    eax
        call    [ebp + IAT_LOADLIB]
        lea     ecx, [ebx + s_vprotect]
        push    ecx
        push    eax
        call    [ebp + IAT_GETPROC]
        mov     edi, eax
        lea     eax, [ebx + bltold]
        push    eax
        push    PAGE_RWX
        push    4
        push    esi
        call    edi
        mov     eax, [esi]
        mov     [ebx + bltorig], eax
        lea     eax, [ebx + blt]
        mov     [esi], eax
        lea     eax, [ebx + bltold]
        push    eax
        push    dword [ebx + bltold]
        push    4
        push    esi
        call    edi
        pop     edi
        pop     esi
.done:  pop     ebp
        pop     ebx
        ret

; In ddraw's vtable in place of Blt: [esp+4] this, [esp+8] the
; destination rect, then the source, its rect, flags and fx, all left
; for the real Blt, which cleans them. A 640x480-sized rect into the
; back buffer within a screen of the 640x480 - a panel sliding in
; starts off the picture - is the lobby's: this becomes the lobby's own
; surface, the rect is cut to its 640x480 with the source rect cut to
; match (a rect off a surface fails the blit, and the screen's edge cut
; a sliding panel at 4:3), and a rect with nothing left is not drawn,
; DD_OK. The background, the one rect that is the whole 640x480, has
; its colour read for the sides.
blt:
        push    ebx
        push    ebp
        call    getbase
        cmp     dword [ebx + ownblit], 0
        jne     .pass                   ; our own, from lobbypresent or bgflush: as they are
        mov     eax, [esp + 0xc]        ; this
        cmp     eax, [ebp + BACKBUF]
        jne     .pass
        cmp     dword [ebp + WIDTH], 640
        jbe     .pass
        mov     eax, [esp + 0x10]       ; the rect
        test    eax, eax
        jz      .pass
        mov     ecx, [eax + 8]
        sub     ecx, [eax]
        cmp     ecx, 640
        jg      .pass
        mov     ecx, [eax + 0xc]
        sub     ecx, [eax + 4]
        cmp     ecx, 480
        jg      .pass
        cmp     dword [eax], -640
        jl      .pass
        cmp     dword [eax], 1280
        jge     .pass
        cmp     dword [eax + 4], -480
        jl      .pass
        cmp     dword [eax + 4], 960
        jge     .pass
        push    esi
        push    edi
        push    ecx
        call    lobbysurface            ; the lobby's surface, made when first wanted
        jz      .unchanged              ; or none to be had: the blit as it came
        mov     [esp + 0x18], eax       ; this
        mov     dword [ebx + bgblit], 0
        mov     esi, [esp + 0x1c]       ; the rect, copied and cut to the 640x480
        lea     edi, [ebx + bltrect]
        mov     ecx, 4
        rep movsd
        cmp     dword [ebx + bltrect], 0        ; the background: its colour for the sides
        jne     .cut
        cmp     dword [ebx + bltrect + 4], 0
        jne     .cut
        cmp     dword [ebx + bltrect + 8], 640
        jne     .cut
        cmp     dword [ebx + bltrect + 12], 480
        jne     .cut
        mov     dword [ebx + bgblit], 1
        call    sidecolour
.cut:   mov     esi, [esp + 0x24]       ; the source rect, if any, to cut with the destination
        test    esi, esi
        jz      .noclip
        lea     edi, [ebx + bltsrc]
        mov     ecx, 4
        rep movsd
        lea     esi, [ebx + bltsrc]
        lea     edi, [ebx + bltrect]
        call    clip
        mov     [esp + 0x24], esi
.noclip:
        lea     edi, [ebx + bltrect]
        mov     [esp + 0x1c], edi
        mov     eax, [edi + 8]          ; nothing left of it: nothing to draw, and DD_OK
        cmp     eax, [edi]
        jle     .empty
        mov     eax, [edi + 12]
        cmp     eax, [edi + 4]
        jle     .empty
        mov     dword [ebx + lobbylive], LOBBYLIVE
        pop     ecx                     ; esi and edi stay pushed: the redirected blit is called,
        lea     esi, [esp + 0x14]       ; not jumped to, for its result; esi = the arguments
        cmp     dword [ebx + bgblit], 0
        je      .real
        cmp     dword [ebx + copymode], 1
        jne     .real
        call    lobbycopy               ; the background through Lock, once found wanted
        jmp     .did
.real:  mov     ecx, 6                  ; the six arguments again, this at the top
.again: push    dword [esp + 0x28]
        loop    .again
        call    [ebx + bltorig]
        cmp     dword [ebx + bgblit], 0
        je      .did
        cmp     dword [ebx + copymode], 0
        jne     .did
        call    lobbycheck              ; the first background: did the blit carry it
.did:   mov     [ebx + blthr], eax
        call    traceblt
        pop     edi
        pop     esi
        pop     ebp
        pop     ebx
        ret     0x18
.unchanged:
        pop     ecx
        pop     edi
        pop     esi
.pass:  mov     eax, [ebx + bltorig]
        pop     ebp
        pop     ebx
        jmp     eax
.empty: pop     ecx
        pop     edi
        pop     esi
        pop     ebp
        pop     ebx
        xor     eax, eax
        ret     0x18

; esi = the background blit's arguments, eax = what Blt said of it: the
; lobby surface's pixel at (0, 240) read back and compared with the
; source's, as sidecolour read it. The same: copymode 2, the blit
; serves. Different - dgVoodoo 2 blits the game's video-memory surface
; as black while Lock reads it whole - copymode 1, and the copy made
; through Lock now and from then on. eax = the result.
lobbycheck:
        push    eax
        push    esi
        mov     esi, [esi]
        lea     edi, [ebx + cpydesc]
        call    lockro
        pop     esi
        jnz     .keep
        mov     eax, [ebx + cpydesc + 0x10]
        imul    eax, 240
        add     eax, [ebx + cpydesc + 0x24]
        cmp     dword [ebx + cpydesc + 0x54], 16
        jne     .wide
        movzx   edx, word [eax]
        jmp     .have
.wide:  mov     edx, [eax]
.have:  push    edx
        push    esi
        mov     esi, [esi]
        call    unlock
        pop     esi
        pop     edx
        cmp     edx, [ebx + bltfx + 0x50]
        je      .keep
        mov     dword [ebx + copymode], 1
        pop     eax
        jmp     lobbycopy
.keep:  mov     dword [ebx + copymode], 2
        pop     eax
        ret

; esi = the background blit's arguments: the source surface copied
; into the lobby's row by row through Lock, both 640x480 at the same
; bit count, or the blit left for next time (copymode 2) when they
; are not. eax = the result, DD_OK or the Lock's error.
lobbycopy:
        push    esi
        push    edi
        push    ebp
        mov     ebp, esi
        mov     esi, [ebp + 8]          ; the source, read-only
        lea     edi, [ebx + cpydesc]
        call    lockro
        jnz     .out
        mov     esi, [ebp]              ; the lobby's surface
        lea     edi, [ebx + bltdesc]
        call    lockrw
        jnz     .unsrc
        cmp     dword [ebx + cpydesc + 0xc], 640
        jne     .unfit
        cmp     dword [ebx + cpydesc + 8], 480
        jne     .unfit
        cmp     dword [ebx + bltdesc + 0xc], 640
        jne     .unfit
        cmp     dword [ebx + bltdesc + 8], 480
        jne     .unfit
        mov     eax, [ebx + cpydesc + 0x54]
        cmp     eax, [ebx + bltdesc + 0x54]
        jne     .unfit
        imul    eax, 640 / 32           ; dwords a row
        mov     esi, [ebx + cpydesc + 0x24]
        mov     edi, [ebx + bltdesc + 0x24]
        mov     edx, 480
.row:   mov     ecx, eax
        rep     movsd
        sub     esi, eax
        sub     esi, eax
        sub     esi, eax
        sub     esi, eax
        add     esi, [ebx + cpydesc + 0x10]
        sub     edi, eax
        sub     edi, eax
        sub     edi, eax
        sub     edi, eax
        add     edi, [ebx + bltdesc + 0x10]
        dec     edx
        jnz     .row
        xor     eax, eax
        jmp     .undst
.unfit: mov     dword [ebx + copymode], 2
        mov     eax, 0x80004005         ; E_FAIL, this once
.undst: push    eax
        mov     esi, [ebp]
        call    unlock
        pop     eax
.unsrc: push    eax
        mov     esi, [ebp + 8]
        call    unlock
        pop     eax
.out:   pop     ebp
        pop     edi
        pop     esi
        ret

; esi = a surface, edi = a DDSURFACEDESC2 to fill: Lock, read-only or
; to write, the whole surface, WAIT. eax = the result, ZF set on DD_OK.
; ecx, edx used.
lockro: mov     edx, DDLOCK_WAIT | DDLOCK_READONLY
        jmp     dolock
lockrw: mov     edx, DDLOCK_WAIT
dolock: push    edi
        push    edx
        mov     ecx, 0x7c / 4
        xor     eax, eax
        rep     stosd
        pop     edx
        pop     edi
        mov     dword [edi], 0x7c
        mov     eax, [esi]
        push    0                       ; Lock(this, no rect, &desc, flags, no event)
        push    edx
        push    edi
        push    0
        push    esi
        call    [eax + VT_LOCK]
        test    eax, eax
        ret

; esi = a surface: Unlock(this, NULL). eax, ecx, edx used.
unlock: mov     eax, [esi]
        push    0
        push    esi
        call    [eax + VT_UNLOCK]
        ret

; edi = a pair of slots, the surface and the back buffer it was made
; beside, ecx = a width, edx = a height: eax = that surface, made
; through IDirectDraw4's CreateSurface ([DDRAW4], offscreen plain in
; video memory, the primary's format) the first time, or again after a
; mode change has given the game a new back buffer, the old one
; released; zero, and ZF, when it cannot be made. ecx and edx used.
offscreen:
        mov     eax, [edi]
        test    eax, eax
        jz      .make
        push    ecx
        mov     ecx, [ebp + BACKBUF]
        cmp     ecx, [edi + 4]
        pop     ecx
        je      .have
        push    ecx                     ; a new back buffer: the old surface goes
        push    eax
        mov     ecx, [eax]
        call    [ecx + VT_RELEASE]
        pop     ecx
        mov     dword [edi], 0
.make:  push    edi
        push    ecx
        lea     edi, [ebx + bltdesc]
        mov     ecx, 0x7c / 4
        xor     eax, eax
        rep stosd
        pop     ecx
        pop     edi
        mov     dword [ebx + bltdesc], 0x7c
        mov     dword [ebx + bltdesc + 4], DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH
        mov     [ebx + bltdesc + 8], edx
        mov     [ebx + bltdesc + 0xc], ecx
        mov     dword [ebx + bltdesc + 0x68], DDSCAPS_OFFSCREENPLAIN | DDSCAPS_VIDEOMEMORY   ; ddsCaps.dwCaps, past the 0x20-byte pixel format at 0x48
        mov     eax, [ebp + DDRAW4]
        test    eax, eax
        jz      .none
        mov     ecx, [eax]
        push    0                       ; CreateSurface(this, &desc, &surface, NULL)
        push    edi
        lea     edx, [ebx + bltdesc]
        push    edx
        push    eax
        call    [ecx + VT_CREATESURFACE]
        mov     [ebx + lobbyhr], eax
        call    tracelobby
        test    eax, eax
        jnz     .none
        mov     eax, [ebp + BACKBUF]
        mov     [edi + 4], eax
        mov     eax, [edi]
        test    eax, eax
        ret
.none:  mov     dword [edi], 0
        xor     eax, eax
        ret
.have:  test    eax, eax
        ret

; The lobby's 640x480 surface.
lobbysurface:
        push    edi
        lea     edi, [ebx + lobbysurf]
        mov     ecx, 640
        mov     edx, 480
        call    offscreen
        pop     edi
        ret

; The .bg pictures' surface, BGSURFW by BGSURFH, made at the present
; and kept in the block bgrow finds by its marker: bgrow composes each
; picture into it at source size, the side areas as their slivers, and
; leaves the composite's size and a flag; the next draw or present, the
; back buffer unlocked by then, stretches it into the whole screen with
; one blit. Registers as a callee must leave them.
bgsurface:
        push    ebx
        push    ebp
        call    getbase
        cmp     dword [ebp + BACKBUF], 0
        je      .done
        push    ecx
        push    edx
        push    edi
        lea     edi, [ebx + bgsurf]
        mov     ecx, BGSURFW
        mov     edx, BGSURFH
        call    offscreen
        pop     edi
        pop     edx
        pop     ecx
.done:  pop     ebp
        pop     ebx
        ret

; ebx = this blob, ebp = the image base: a composed picture waiting is
; stretched into the whole screen, and the wait ended. Every register
; kept.
bgflush:
        cmp     dword [ebx + bgpending], 0
        je      .done
        cmp     dword [ebp + BACKBUF], 0
        je      .done
        mov     dword [ebx + bgpending], 0
        pushad
        mov     dword [ebx + ownblit], 1
        xor     eax, eax                ; the whole screen, from the composite
        mov     [ebx + bltrect], eax
        mov     [ebx + bltrect + 4], eax
        mov     [ebx + bltsrc], eax
        mov     [ebx + bltsrc + 4], eax
        mov     eax, [ebp + WIDTH]
        mov     [ebx + bltrect + 8], eax
        mov     eax, [ebp + HEIGHT]
        mov     [ebx + bltrect + 12], eax
        mov     eax, [ebx + bgcw]
        mov     [ebx + bltsrc + 8], eax
        mov     eax, [ebx + bgch]
        mov     [ebx + bltsrc + 12], eax
        mov     eax, [ebp + BACKBUF]
        mov     ecx, [eax]
        push    0                       ; Blt(back buffer, &screen, the surface, &composite, WAIT, NULL)
        push    DDBLT_WAIT
        lea     edx, [ebx + bltsrc]
        push    edx
        push    dword [ebx + bgsurf]
        lea     edx, [ebx + bltrect]
        push    edx
        push    eax
        call    [ecx + VT_BLT]
        mov     dword [ebx + ownblit], 0
        popad
.done:  ret

; The background's colour for the side areas, read from its surface at
; (0, 240) - the plain part, left of the panel and between the title
; bands - through Lock and Unlock, at 16 or 32 bits as the surface's
; format says. The blit's source is at [esp+0x24] (under the return
; here, three pushes and blt's two). eax, ecx, edx used.
sidecolour:
        mov     eax, [esp + 0x24]
        test    eax, eax
        jz      .done
        push    esi
        push    edi
        mov     esi, eax
        lea     edi, [ebx + bltdesc]
        mov     ecx, 0x7c / 4
        xor     eax, eax
        rep stosd
        mov     dword [ebx + bltdesc], 0x7c
        mov     eax, [esi]
        push    0                       ; Lock(this, no rect, &desc, WAIT | READONLY, no event)
        push    DDLOCK_WAIT | DDLOCK_READONLY
        lea     edx, [ebx + bltdesc]
        push    edx
        push    0
        push    esi
        call    [eax + VT_LOCK]
        test    eax, eax
        jnz     .out
        mov     eax, [ebx + bltdesc + 0x10]     ; the pixel at (0, 240): row 240 of the pitch
        imul    eax, 240
        add     eax, [ebx + bltdesc + 0x24]
        cmp     dword [ebx + bltdesc + 0x54], 16
        jne     .wide
        movzx   edx, word [eax]
        jmp     .have
.wide:  mov     edx, [eax]
.have:  mov     [ebx + bltfx + 0x50], edx       ; dwFillColor
        mov     eax, [esi]
        push    0
        push    esi
        call    [eax + VT_UNLOCK]
.out:   pop     edi
        pop     esi
.done:  ret

; At the present, while the lobby has drawn lately: its surface
; stretched into the 4:3 box, one blit, and the side areas filled with
; the background's colour, a colour-fill blit each, all through ddraw's
; own Blt on the back buffer. The lobby draws only what changes, and
; the back buffer keeps between presents, so the stretch goes on for
; LOBBYLIVE presents after the last blit. Registers as a callee must
; leave them.
lobbypresent:
        push    ebx
        push    ebp
        call    getbase
        cmp     dword [ebx + lobbylive], 0
        je      .done
        dec     dword [ebx + lobbylive]
        push    esi
        push    edi
        push    ecx
        mov     dword [ebx + ownblit], 1
        lea     edi, [ebx + bltrect]    ; the box: the 640x480 scaled
        xor     eax, eax
        mov     [edi], eax
        mov     [edi + 4], eax
        mov     dword [edi + 8], 640
        mov     dword [edi + 12], 480
        call    scalerect
        xor     eax, eax                ; the whole of the lobby's surface
        mov     [ebx + bltsrc], eax
        mov     [ebx + bltsrc + 4], eax
        mov     dword [ebx + bltsrc + 8], 640
        mov     dword [ebx + bltsrc + 12], 480
        push    0                       ; Blt(back buffer, &box, lobby surface, &whole, WAIT, NULL)
        push    DDBLT_WAIT
        lea     eax, [ebx + bltsrc]
        push    eax
        push    dword [ebx + lobbysurf]
        lea     eax, [ebx + bltrect]
        push    eax
        push    dword [ebp + BACKBUF]
        call    [ebx + bltorig]
        mov     dword [ebx + bltfx], 0x64       ; the sides: (0, 0, bar, H) and (W - bar, 0, W, H)
        mov     ecx, [ebx + vpbar]
        test    ecx, ecx
        jz      .filled
        xor     eax, eax
        mov     [ebx + bltside], eax
        mov     [ebx + bltside + 4], eax
        mov     [ebx + bltside + 8], ecx
        mov     eax, [ebp + HEIGHT]
        mov     [ebx + bltside + 12], eax
        call    .fill
        mov     eax, [ebp + WIDTH]
        mov     [ebx + bltside + 8], eax
        sub     eax, [ebx + vpbar]
        mov     [ebx + bltside], eax
        call    .fill
.filled:
        mov     dword [ebx + ownblit], 0
        pop     ecx
        pop     edi
        pop     esi
.done:  pop     ebp
        pop     ebx
        ret
.fill:  lea     eax, [ebx + bltfx]      ; Blt(back buffer, &side, no source, no rect, COLORFILL | WAIT, &fx)
        push    eax
        push    DDBLT_COLORFILL | DDBLT_WAIT
        push    0
        push    0
        lea     eax, [ebx + bltside]
        push    eax
        push    dword [ebp + BACKBUF]
        call    [ebx + bltorig]
        ret

; edi = a destination rect, esi = its source rect: the destination cut
; to 640x480 and the source cut to match. eax, ecx, edx used.
clip:
        xor     eax, eax
        mov     ecx, 640
        call    .axis                   ; x: [edi] and [edi+8] against 0 and 640
        add     esi, 4
        add     edi, 4
        xor     eax, eax
        mov     ecx, 480
        call    .axis                   ; y: likewise against 0 and 480
        sub     esi, 4
        sub     edi, 4
        ret
.axis:  push    ecx                     ; the limits: [esp+4] the far, [esp] the near
        push    eax
        mov     eax, [edi + 8]          ; the destination's span, and the source's
        sub     eax, [edi]
        jle     .out
        mov     edx, [esi + 8]
        sub     edx, [esi]
        push    eax
        push    edx                     ; [esp] the source span, [esp+4] the destination's
        mov     ecx, [esp + 8]
        cmp     [edi], ecx
        jge     .low
        mov     eax, ecx                ; short of the near edge: the source moves in by the same share
        sub     eax, [edi]
        imul    eax, [esp]
        cdq
        idiv    dword [esp + 4]
        add     [esi], eax
        mov     [edi], ecx
.low:   mov     ecx, [esp + 0xc]
        cmp     [edi + 8], ecx
        jle     .fits
        mov     eax, [edi + 8]          ; past the far edge: the source's end pulled in likewise
        sub     eax, ecx
        imul    eax, [esp]
        cdq
        idiv    dword [esp + 4]
        sub     [esi + 8], eax
        mov     [edi + 8], ecx
.fits:  add     esp, 8
.out:   add     esp, 8
        ret

; [esp] = the return, [esp+4] this. A frame: the widths seen since the
; last present become the table extend consults. First the hooks and
; surfaces the frame needs (hookblt, bgsurface), the lobby's stretch if
; it has drawn lately (lobbypresent) and a composed .bg waiting
; (bgflush).
present:
        call    hookblt
        call    bgsurface
        call    lobbypresent
        push    ebx
        push    ebp
        call    getbase
        call    bgflush
        call    tracepresent
        mov     dword [ebx + hud], 0    ; the frame's HUD flag, for the exe to set again
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
        cmp     dword [ebx + trace], 2
        jne     .all                            ; 2 (d3dtrace2d): the 2D that is not a quad only
        cmp     dword [ebp + FVF], 0x1c4
        jne     .done
        mov     eax, [esp + 0xc]                ; the count with its flags, under the pushed ebx and ebp
        and     eax, 0xffff
        cmp     eax, 4
        je      .done
.all:   dec     dword [ebx + left]
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
        cmp     ecx, NKINDS
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
        cmp     dword [ebx + trace], 1
        jne     .done
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

; The lobby's surface, once made or not: "sr2 l hr ddraw surface", the
; CreateSurface result, the IDirectDraw4 it was asked of and what came.
tracelobby:
        cmp     dword [ebx + trace], 0
        je      .done
        cmp     dword [ebx + left], 0
        je      .done
        dec     dword [ebx + left]
        pushad
        lea     edi, [ebx + line]
        lea     esi, [ebx + s_l]
        call    scat
        mov     eax, [ebx + lobbyhr]
        call    hex8
        mov     eax, [ebp + DDRAW4]
        call    hex8
        mov     eax, [ebx + lobbysurf]
        call    hex8
        call    report
        popad
.done:  ret

; A blit sent to the lobby's surface, as it went: "sr2 x hr this source
; flags L T R B [l t r b]", the result, the destination and source
; surfaces, the flags, the destination rect and the source rect if one,
; then the two surfaces described. esi = the blit's arguments.
traceblt:
        cmp     dword [ebx + trace], 0
        je      .done
        cmp     dword [ebx + left], 0
        je      .done
        dec     dword [ebx + left]
        pushad
        mov     edx, esi
        lea     edi, [ebx + line]
        lea     esi, [ebx + s_x]
        call    scat
        mov     eax, [ebx + blthr]
        call    hex8
        mov     eax, [edx]
        call    hex8
        mov     eax, [edx + 8]
        call    hex8
        mov     eax, [edx + 0x10]
        call    hex8
        mov     esi, [edx + 4]
        call    .rect
        mov     esi, [edx + 0xc]
        test    esi, esi
        jz      .out
        call    .rect
.out:   push    edx
        call    report
        pop     edx
        push    dword [edx]             ; then the source and the destination as surfaces
        mov     esi, [edx + 8]
        call    tracesurf
        pop     esi
        call    tracesurf
        popad
.done:  ret
.rect:  mov     ecx, 4
.r:     lodsd
        call    hex8
        loop    .r
        ret

; esi = a surface: "sr2 s surface hr flags w h pf bpp caps pixel", its
; description through Lock and Unlock and the pixel at (0, 240), as
; sidecolour reads it - 0 when the surface has no such row, since this
; describes whatever a traced blit names and the art is blitted from
; pieces a few rows tall. Registers other than eax, ecx, edx, edi kept.
tracesurf:
        test    esi, esi
        jz      .done
        lea     edi, [ebx + line]
        push    esi
        lea     esi, [ebx + s_s]
        call    scat
        pop     esi
        mov     eax, esi
        call    hex8
        push    edi
        lea     edi, [ebx + bltdesc]
        mov     ecx, 0x7c / 4
        xor     eax, eax
        rep     stosd
        pop     edi
        mov     dword [ebx + bltdesc], 0x7c
        mov     eax, [esi]
        push    0                       ; Lock(this, no rect, &desc, WAIT | READONLY, no event)
        push    DDLOCK_WAIT | DDLOCK_READONLY
        lea     edx, [ebx + bltdesc]
        push    edx
        push    0
        push    esi
        call    [eax + VT_LOCK]
        push    eax
        call    hex8
        pop     eax
        test    eax, eax
        jnz     .out
        mov     eax, [ebx + bltdesc + 4]
        call    hex8
        mov     eax, [ebx + bltdesc + 0xc]
        call    hex8
        mov     eax, [ebx + bltdesc + 8]
        call    hex8
        mov     eax, [ebx + bltdesc + 0x4c]
        call    hex8
        mov     eax, [ebx + bltdesc + 0x54]
        call    hex8
        mov     eax, [ebx + bltdesc + 0x68]
        call    hex8
        xor     eax, eax                ; the pixel at (0, 240), 0 where there is no such row:
        cmp     dword [ebx + bltdesc + 0x24], 0     ; no pointer from the lock,
        je      .pixel
        cmp     dword [ebx + bltdesc + 8], 240      ; or a surface no taller than that - a
        jbe     .pixel                              ; piece of art is 32 rows, and pitch * 240
        mov     eax, [ebx + bltdesc + 0x10]         ; ran off the end of the mapping
        imul    eax, 240
        add     eax, [ebx + bltdesc + 0x24]
        cmp     dword [ebx + bltdesc + 0x54], 16    ; as the depth the lock reports
        jne     .wide
        movzx   eax, word [eax]
        jmp     .pixel
.wide:  mov     eax, [eax]
.pixel: call    hex8
        mov     eax, [esi]
        push    0
        push    esi
        call    [eax + VT_UNLOCK]
.out:   call    report
.done:  ret

; The present, a frame's end: "sr2 p", so the draws fall into frames.
tracepresent:
        cmp     dword [ebx + trace], 0
        je      .done
        cmp     dword [ebx + left], 0
        je      .done
        dec     dword [ebx + left]
        pushad
        lea     edi, [ebx + line]
        lea     esi, [ebx + s_p]
        call    scat
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

; the line at [ebx+line], ending at edi, to OutputDebugStringA, and
; appended to logs\d3dtrace.log beside the exe, opened on the first line.
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
        call    openlog
.have:  lea     eax, [ebx + line]
        push    eax
        call    [ebx + fn_ods]
        cmp     dword [ebx + fn_log], -1
        je      .done
        mov     word [edi], 0x0a0d
        lea     ecx, [ebx + line]
        lea     eax, [edi + 2]
        sub     eax, ecx
        push    0                       ; WriteFile(log, line, length, &written, NULL)
        lea     edx, [ebx + written]
        push    edx
        push    eax
        push    ecx
        push    dword [ebx + fn_log]
        call    [ebx + fn_write]
.done:  ret

; Resolves CreateDirectoryA, CreateFileA and WriteFile, makes logs\
; beside the exe and opens d3dtrace.log in it, CREATE_ALWAYS, or leaves
; the handle -1. eax, ecx, edx used.
openlog:
        push    esi
        push    edi
        sub     esp, PATHBUF + 4        ; the path, and CreateDirectoryA above it
        mov     dword [ebx + fn_log], -1
        lea     eax, [ebx + s_kernel32]
        push    eax
        call    [ebp + IAT_LOADLIB]
        test    eax, eax
        jz      .out
        mov     esi, eax
        lea     eax, [ebx + s_writefile]
        push    eax
        push    esi
        call    [ebp + IAT_GETPROC]
        test    eax, eax
        jz      .out
        mov     [ebx + fn_write], eax
        lea     eax, [ebx + s_createfile]
        push    eax
        push    esi
        call    [ebp + IAT_GETPROC]
        test    eax, eax
        jz      .out
        mov     [ebx + fn_create], eax
        lea     eax, [ebx + s_createdir]
        push    eax
        push    esi
        call    [ebp + IAT_GETPROC]
        test    eax, eax
        jz      .out
        mov     [esp + PATHBUF], eax    ; CreateDirectoryA
        push    MAX_PATH
        lea     ecx, [esp + 4]
        push    ecx
        push    0
        call    [ebp + IAT_GETMODFN]    ; GetModuleFileNameA(NULL, path, MAX_PATH)
        test    eax, eax
        jz      .out
        lea     edi, [esp + eax]        ; after the last backslash, or the start
.back:  cmp     edi, esp
        je      .name
        dec     edi
        cmp     byte [edi], '\'
        jne     .back
        inc     edi
.name:  lea     esi, [ebx + s_logdir]
        call    scat
        mov     byte [edi], 0
        push    0
        lea     ecx, [esp + 4]
        push    ecx
        call    [esp + 8 + PATHBUF]     ; CreateDirectoryA(path, NULL); exists is fine
        mov     byte [edi], '\'
        inc     edi
        lea     esi, [ebx + s_logname]
        call    scat
        mov     byte [edi], 0
        push    0
        push    FILE_ATTRIBUTE_NORMAL
        push    CREATE_ALWAYS
        push    0
        push    FILE_SHARE_READ
        push    GENERIC_WRITE
        lea     ecx, [esp + 24]
        push    ecx
        call    [ebx + fn_create]       ; CreateFileA
        mov     [ebx + fn_log], eax
.out:   add     esp, PATHBUF + 4
        pop     edi
        pop     esi
        ret

s_d:        db 'sr2 d ', 0
s_b:        db 'sr2 b ', 0
s_t:        db 'sr2 t ', 0
s_l:        db 'sr2 l ', 0
s_x:        db 'sr2 x ', 0
s_s:        db 'sr2 s ', 0
s_p:        db 'sr2 p', 0
s_kernel32: db 'kernel32.dll', 0
s_ods:      db 'OutputDebugStringA', 0
s_vprotect: db 'VirtualProtect', 0
s_writefile: db 'WriteFile', 0
s_createfile: db 'CreateFileA', 0
s_createdir: db 'CreateDirectoryA', 0
s_logdir:   db 'logs', 0
s_logname:  db 'd3dtrace.log', 0
digits:     db '0123456789abcdef'
s_marker:   db 'D3DTRACE', 0            ; the patcher finds the flag by this
trace:      dd 0
        align 4
fn_ods:     dd 0
fn_log:     dd 0                        ; the log's handle, 0 not opened, -1 failed; WriteFile, CreateFileA
fn_write:   dd 0
fn_create:  dd 0
written:    dd 0
left:       dd 400000                   ; lines still to report: a whole race, not two minutes of one
vpbar:      dd 0                        ; the bar the picture sits behind, for scalerect
vpcopy:     times 8 dd 0                ; the viewport setter's rect and fractions, scaled
ownblit:    dd 0                        ; set around the blits this blob makes itself, which the hook passes
bltorig:    dd 0                        ; ddraw's own Blt, once hooked, the protection the entry had, a
bltold:     dd 0                        ; blit's rect scaled and its source rect cut to match, and the
bltrect:    times 4 dd 0                ; side areas' rect and the column that fills it
bltsrc:     times 4 dd 0
bltside:    times 4 dd 0
bltfx:      times 25 dd 0               ; a DDBLTFX for the side fills, and a DDSURFACEDESC2 for the read
bltdesc:    times 31 dd 0               ; and the create
lobbysurf:  dd 0                        ; the lobby's 640x480 surface, the back buffer it was made beside,
lobbyfor:   dd 0                        ; and presents left to stretch it for
lobbylive:  dd 0
lobbyhr:    dd 0                        ; what CreateSurface said, for the trace
blthr:      dd 0                        ; what the last blit sent to it said
bgblit:     dd 0                        ; the blit in hand is the background, the whole 640x480
copymode:   dd 0                        ; 0 not yet known, 1 the background copied through Lock, 2 blitted
cpydesc:    times 31 dd 0               ; a DDSURFACEDESC2 for the source of that copy
            db 'BGBLOCK', 0             ; the block bgrow finds by this, in the annex from 0x17000
bgsurf:     dd 0                        ; the .bg pictures' surface, the back buffer it was made beside,
bgfor:      dd 0                        ; a composite waiting to be stretched in, and its size
bgpending:  dd 0
bgcw:       dd 0
bgch:       dd 0
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
; picture stretched into it (barquad). One with no texture selected is
; a plain cover - the ending's black around its replay window, whose
; side pieces reach the 640's edges - and is drawn out to the screen's
; edge on that side, or the replay's own wider frame shows beside it. A clamped tile has wrap switched on
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
        mov     [ebx + covern], ecx
        call    barquad
        test    dword [ebp + CURTEX], 0x80000000
        jz      .out                    ; textured: a picture, its bar drawn or not
        mov     ecx, [ebx + covern]     ; no texture: a plain cover, out to the screen's edge on its side
        mov     esi, [esp + 0x28]       ; (the ending's black around its replay window)
        lea     edi, [ebx + copy]
.cover: fld     dword [esi]
        fcomp   dword [ebx + khalf]
        fnstsw  ax
        sahf
        jae     .notl
        mov     dword [edi], 0
        jmp     .nextc
.notl:  fld     dword [esi]
        fcomp   dword [ebx + kalmost]
        fnstsw  ax
        sahf
        jb      .nextc
        fild    dword [ebp + WIDTH]
        fstp    dword [edi]
.nextc: add     esi, 32
        add     edi, 32
        dec     ecx
        jnz     .cover
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
; place; the side area beside it gets the picture itself, stretched. A
; quad with the texture still bound and its coordinates carried past the
; quad's own edge, so the bar is the 640's own sliver - a bar's share of
; the picture's width, in from that end, and no further in than the quad
; itself reaches - spread across the side area. Drawn PASSES times,
; added, spread across kblurpx of the 640's pixels in u, each at its share
; of the quad's diffuse dimmed: a motion blur across, at two fifths. A
; texture all but black takes one black pass with no texture instead.
; ecx = the count, edges = the span bits; the copy at [ebx+copy], the
; originals at [esp+0x2c] and the device at [esp+0x28] (under the return
; here). The two values on the FPU stack are put aside for the draws.
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
        cmp     eax, NKINDS
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
        mov     eax, [esi + 16]                 ; the quad's own diffuse
        cmp     dword [ebx + barkind], KBLACK
        jne     .havediffuse
        and     eax, 0xff000000                 ; a picture that is all but black: a black bar, and no texture
.havediffuse:
        mov     [edi + 16], eax
        mov     [edi + 48], eax
        mov     [edi + 80], eax
        mov     [edi + 112], eax
        mov     eax, [ebx + vmin]               ; the quad's own texture rows
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
.draw:  mov     eax, [ebx + ubar0]              ; the texture coordinates, and the quad's own rows
        mov     [edi + 24], eax
        mov     [edi + 88], eax
        mov     eax, [ebx + ubar1]
        mov     [edi + 56], eax
        mov     [edi + 120], eax
        fld     dword [ebx + ymin]
        fmul    dword [ebx + sc]
        fst     dword [edi + 4]
        fstp    dword [edi + 36]
        fld     dword [ebx + ymax]
        fmul    dword [ebx + sc]
        fst     dword [edi + 68]
        fstp    dword [edi + 100]
        mov     eax, [ebp + CURTEX]
        mov     [ebx + savedtex], eax
        mov     dword [ebx + inbar], 1
        cmp     dword [ebx + barkind], KBLACK
        jne     .textured
        mov     ecx, [esp + 0x30]               ; the device
        mov     edx, [ecx]
        push    -1
        push    ecx
        call    [edx + SETTEX]                  ; nothing of the picture: the diffuse alone, one pass
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
.textured:                                      ; the passes add up, so the bar is their mean: a motion blur across
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
        mov     esi, [esp + 0x34]               ; each pass at its share of the quad's diffuse
        mov     eax, [esi + 16]
        call    passrgb
        mov     [edi + 16], eax
        mov     [edi + 48], eax
        mov     [edi + 80], eax
        mov     [edi + 112], eax
        fld     dword [ebx + kblurpx]           ; the blur's width in the quad's own u: so many of the 640's
        fld     dword [ebx + umax]              ; pixels, at the quad's u per pixel; a pass's step is a share of
        fsub    dword [ebx + umin]              ; it, and the first sits half of it before the others
        fmulp   st1, st0
        fld     dword [ebx + xmax]
        fsub    dword [ebx + xmin]
        fdivp   st1, st0
        fdiv    dword [ebx + kpasses1]
        fst     dword [ebx + ushift]
        fmul    dword [ebx + kfirst]
        fstp    dword [ebx + ucur]
        mov     ecx, PASSES
.pass:  push    ecx
        fld     dword [ebx + ubar0]
        fadd    dword [ebx + ucur]
        fst     dword [edi + 24]
        fstp    dword [edi + 88]
        fld     dword [ebx + ubar1]
        fadd    dword [ebx + ucur]
        fst     dword [edi + 56]
        fstp    dword [edi + 120]
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

; eax = a colour: eax = it dimmed, at a pass's share, its alpha kept.
; ecx, edx, esi and edi kept.
passrgb:
        push    ecx
        push    edx
        push    esi
        mov     esi, eax
        xor     edx, edx
        xor     ecx, ecx
.channel:
        mov     eax, esi
        shr     eax, cl
        and     eax, 0xff
        imul    eax, DIM
        shr     eax, 8
        imul    eax, PASSSHARE
        shr     eax, 8
        cmp     eax, 0xff
        jbe     .fits
        mov     eax, 0xff
.fits:  shl     eax, cl
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
; the flags). Its kind into the table: KPICTURE when every pixel is
; opaque, KBLACK when MOSTLY quarters of them are dark as well, else 0 -
; a sprite, or a format with no pixels to read. Then the thirteen bytes
; replaced, and on.
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
        cmp     esi, NKINDS
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
kblurpx:    dd 0x41A00000                   ; 20.0: a thirty-second of the 640, the motion blur's width
kpasses1:   dd 0x41700000                   ; 15.0: the steps between PASSES passes
kfirst:     dd 0xC0F00000                   ; -7.5: where the first of them starts, in steps
k640:       dd 0x44200000               ; 640.0
k480:       dd 0x43F00000               ; 480.0
khalf:      dd 0x3F000000               ; 0.5
kalmost:    dd 0x441FC000               ; 639.0
k479:       dd 0x43EF8000               ; 479.0
kone:       dd 0x3F800000               ; 1.0
kthird:     dd 0x43860000               ; 268.0: the 640's left and right parts, 0.42 of it each - the
k2third:    dd 0x43BA0000               ; 372.0   speed ends at 256 and the countdown starts at 291
k2over9:    dd 0x3E638E39               ; 2/9: a 16:9 frame's edge past the 4:3 box's, as a share of the height
hshift:     dd 0                        ; the HUD's move out to the 16:9 frame, in picture pixels
            db 'HUDFRAME'               ; the exe's walk entry finds the flag by this
hud:        dd 0                        ; set by the exe when one of the race HUD's callbacks runs, cleared at the present
huddrawlo:  dd 0                        ; and the bounds of the exe's own HUD draws, written with it: a draw
huddrawhi:  dd 0                        ; from anywhere else in a HUD frame - the results row - is not anchored
runmax:     dd 0                        ; the right end of the run of glyphs in hand, in 640 pixels
kgap:       dd 0x41800000               ; 16.0: a glyph this close to the run's end joins it
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
covern:     dd 0                        ; the count, across barquad
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
ubar1:      dd 0                        ; second; a pass's step across, and where the walk has got to
ushift:     dd 0
ucur:       dd 0
savedblend: dd 0                        ; whether the device was blending before the bar, and how it addressed
savedwrap:  dd 0
            db 'KINDTABLE', 0, 0, 0         ; the test finds the table by this
kinds:      times NKINDS dd 0           ; what each texture is: a picture, a black one, or nothing
barcopy:    times 4 * 32 db 0           ; the bar quad
sizes:      times NSIZES * 6 dd 0       ; this frame's widths: width, quads, left, right, top, bottom
nsizes:     dd 0
lastsizes:  times NSIZES * 6 dd 0       ; last frame's, and its count
nlastsizes: dd 0
        align 16
copy:       times CAPACITY * 32 db 0
