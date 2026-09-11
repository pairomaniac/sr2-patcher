; devices.asm - the Device Settings page in Options.dll.
;
; Two entries in the top-level state table the patcher moves into
; .sr2d, reached with esi = the Options object as every case there is:
;
;   +0  init   state 0xc: binds the page's UV table to the loaded sheets
;              - once per load of the DLL, since the binding replaces
;              each entry's sheet index with its handle in place - starts
;              the slide-in, steps to 0xd and falls into exec.
;   +5  exec   state 0xd: draws every sprite of the page's list, slid in
;              from the right by 40 px a frame as the stock pages are,
;              then, once in place, moves the cursor on up and down, and
;              on cancel, or confirm on the BACK row, plays the back
;              sound and slides the page on out to the left, as the
;              stock pages go, and only then puts the menu's state back.
;              Leaves through the dispatcher's epilogue.
;
; The sprites, their quads and UV entries and the draw list are data the
; patcher builds after this code. The list is 40-byte entries: kind (1 a
; sprite, 2 a string, 0 the end), the sprite or string, x, y, z or the
; text routine's flags, alpha, red, green, blue in 256ths, and the
; cursor's hold on the entry: 0 for none, else the first and last row
; (plus one) in the low bytes and in bits 16-23 how it is drawn when the
; cursor is on one of those rows - 1 solid red, the stock's row; 2 red
; with a little green and blue, its group plate; 3 red pulsing to white,
; its button. The row after the last is the BACK button. The DLL
; is relocated on every load: the blob finds its own address with a
; call/pop and subtracts its RVA to get the image base, and every DLL
; address here is an RVA from that, filled in from the build's row.

bits 32

%define MAGIC_SELFRVA   0xD1D1D1D1      ; this blob's RVA
%define MAGIC_EPILOGUE  0xD2D2D2D2      ; the dispatcher's common exit
%define MAGIC_BINDPAGE  0xD3D3D3D3      ; bind a page's UV entries to sheet handles
%define MAGIC_DRAW      0xD4D4D4D4      ; queue a sprite
%define MAGIC_PLAYSOUND 0xD5D5D5D5      ; the sound manager's play
%define MAGIC_INPUT     0xD6D6D6D6      ; the input object's holder
%define MAGIC_SOUNDOBJ  0xD7D7D7D7      ; the sound manager
%define MAGIC_HANDLES   0xD8D8D8D8      ; the loaded sheets' handles
%define MAGIC_PAGEHDR   0xD9D9D9D9      ; the page's (UV table, count)
%define MAGIC_DRAWLIST  0xDADADADA      ; the draw list
%define MAGIC_TEXT      0xDBDBDBDB      ; the stock text routine: a string in the 14-px font
%define MAGIC_GLYPHS    0xDCDCDCDC      ; its glyph sprite table
%define MAGIC_ROWS      0xDDDDDDDD      ; the page's rows; the BACK row is one more

%define STATE           8               ; the Options object's state
%define BACK_SOUND      0xe             ; the stock's for cursor moves and leaving
%define KEY_CANCEL      2
%define KEY_CONFIRM     0x41
%define KEY_UP          0x200
%define KEY_DOWN        0x400
%define FULL            0x100
%define GROUP_TINT      0x20
%define PULSE_STEP      0x10
%define SLIDE_FROM      0x44200000      ; 640.0
%define SLIDE_GONE      0xC4200000      ; -640.0
%define SLIDE_STEP      0x42200000      ; 40.0

        jmp     near init               ; +0
        jmp     near exec               ; +5

; ebx = image base on return; eax clobbered.
getbase:
        call    .here
.here:  pop     ebx
        sub     ebx, .here
        sub     ebx, MAGIC_SELFRVA
        ret

init:
        push    ebx
        push    edi
        call    getbase
        lea     edi, [ebx + MAGIC_SELFRVA]  ; this blob
        mov     dword [edi + slide - $$], SLIDE_FROM
        mov     dword [edi + leaving - $$], 0
        mov     dword [edi + row - $$], 0
        mov     dword [edi + pulse - $$], 0
        mov     dword [edi + pulsedir - $$], PULSE_STEP
        cmp     dword [edi + bound - $$], 0
        jne     .ready
        mov     dword [edi + bound - $$], 1
        lea     eax, [ebx + MAGIC_HANDLES]
        push    eax
        lea     eax, [ebx + MAGIC_PAGEHDR]
        push    eax
        lea     eax, [ebx + MAGIC_BINDPAGE]
        call    eax
        add     esp, 8
.ready:
        inc     dword [esi + STATE]
        pop     edi
        pop     ebx
        ; fall through

exec:
        push    ebx
        push    edi
        push    ebp
        call    getbase
        lea     ebp, [ebx + MAGIC_SELFRVA]  ; this blob
        lea     edi, [ebx + MAGIC_DRAWLIST]
.sprite:
        mov     eax, [edi]
        test    eax, eax
        jz      .slide
        cmp     eax, 2
        je      .string
        push    0                       ; the sprite call's sixteen dwords
        push    0
        push    0
        mov     ecx, [edi + 36]         ; the cursor's hold on this entry
        test    ecx, ecx
        jz      .plain
        movzx   eax, cl                 ; first row + 1 .. last row + 1
        dec     eax
        cmp     [ebp + row - $$], eax
        jl      .plain
        movzx   eax, ch
        dec     eax
        cmp     [ebp + row - $$], eax
        jg      .plain
        shr     ecx, 16
        xor     edx, edx                ; 1: green and blue 0
        cmp     ecx, 2
        jne     .kind3
        mov     edx, GROUP_TINT
.kind3:
        cmp     ecx, 3
        jne     .held
        mov     edx, [ebp + pulse - $$]
.held:
        push    edx                     ; blue, green, red, alpha
        push    edx
        push    FULL
        push    FULL
        jmp     .coloured
.plain:
        push    dword [edi + 32]        ; blue, green, red, alpha
        push    dword [edi + 28]
        push    dword [edi + 24]
        push    dword [edi + 20]
.coloured:
        push    0x3f800000              ; scale 1.0, 1.0
        push    0x3f800000
        push    0
        push    0
        push    0
        push    dword [edi + 16]        ; z
        push    dword [edi + 12]        ; y
        push    eax                     ; x, slid: the entry's plus the offset
        fld     dword [edi + 8]
        fadd    dword [ebp + slide - $$]
        fstp    dword [esp]
        push    dword [edi + 4]         ; the sprite
        lea     eax, [ebx + MAGIC_DRAW]
        call    eax
        add     esp, 0x40
        add     edi, 40
        jmp     .sprite
.string:
        push    dword [edi + 16]        ; the text routine's thirteen: flags
        lea     eax, [ebx + MAGIC_GLYPHS]
        push    eax                     ; its glyph table
        push    dword [edi + 32]        ; blue, green, red, alpha
        push    dword [edi + 28]
        push    dword [edi + 24]
        push    dword [edi + 20]
        push    0x3f800000              ; scale 1.0, 1.0
        push    0x3f800000
        push    0x41200000              ; the advance of a glyph it lacks, 10.0
        push    0x41200000              ; z 10.0, the stock's text
        push    dword [edi + 12]        ; y
        push    eax                     ; x, slid
        fld     dword [edi + 8]
        fadd    dword [ebp + slide - $$]
        fstp    dword [esp]
        push    dword [edi + 4]         ; the string
        lea     eax, [ebx + MAGIC_TEXT]
        call    eax
        add     esp, 0x34
        add     edi, 40
        jmp     .sprite
.slide:
        mov     eax, [ebp + pulsedir - $$]   ; the button's pulse, 0 to 0x100 and back
        add     eax, [ebp + pulse - $$]
        mov     [ebp + pulse - $$], eax
        cmp     eax, FULL
        jle     .pulselow
        mov     dword [ebp + pulse - $$], FULL
        mov     dword [ebp + pulsedir - $$], -PULSE_STEP
.pulselow:
        test    eax, eax
        jns     .pulsed
        mov     dword [ebp + pulse - $$], 0
        mov     dword [ebp + pulsedir - $$], PULSE_STEP
.pulsed:
        cmp     dword [ebp + leaving - $$], 0
        jne     .leave
        mov     eax, [ebp + slide - $$]
        test    eax, eax
        jz      .input
        fld     dword [ebp + slide - $$]
        fsub    dword [ebp + step - $$]
        fstp    dword [ebp + slide - $$]
        mov     eax, [ebp + slide - $$]
        test    eax, eax                ; below zero, the sign bit
        jns     .out
        mov     dword [ebp + slide - $$], 0
        jmp     .out
.leave:                                 ; on out to the left, then the menu
        fld     dword [ebp + slide - $$]
        fsub    dword [ebp + step - $$]
        fstp    dword [ebp + slide - $$]
        cmp     dword [ebp + slide - $$], SLIDE_GONE    ; negative floats grow as unsigned
        jb      .out
        mov     dword [esi + STATE], 1  ; the menu, cursor where it was
        jmp     .out
.input:
        mov     eax, [ebx + MAGIC_INPUT]
        mov     ecx, [eax + 8]
        test    ecx, ecx
        jz      .out
        mov     edx, [ecx]
        push    1
        call    [edx + 0x14]            ; the frame's key bits
        mov     edi, eax
        test    ah, KEY_DOWN >> 8
        jz      .notdown
        mov     eax, [ebp + row - $$]   ; down: the next row, the BACK row, the first
        inc     eax
        cmp     eax, MAGIC_ROWS
        jle     .moved
        xor     eax, eax
        jmp     .moved
.notdown:
        test    ah, KEY_UP >> 8
        jz      .notup
        mov     eax, [ebp + row - $$]   ; up: the row before, or the BACK row
        dec     eax
        jns     .moved
        mov     eax, MAGIC_ROWS
.moved:
        mov     [ebp + row - $$], eax
        call    .sound
        jmp     .out
.notup:
        test    edi, KEY_CANCEL
        jnz     .go
        test    edi, KEY_CONFIRM
        jz      .out
        mov     eax, [ebp + row - $$]   ; confirm: on the BACK row, leave
        cmp     eax, MAGIC_ROWS
        jne     .out
.go:
        call    .sound
        mov     dword [ebp + leaving - $$], 1
        jmp     .out
.sound:
        mov     ecx, [ebx + MAGIC_SOUNDOBJ]
        push    0
        push    0
        push    0
        push    BACK_SOUND
        lea     eax, [ebx + MAGIC_PLAYSOUND]
        call    eax
        ret
.out:
        lea     eax, [ebx + MAGIC_EPILOGUE]
        pop     ebp
        pop     edi
        pop     ebx
        jmp     eax

bound:  dd      0                       ; the UV table bound this load
slide:  dd      0                       ; the slide's x offset, 640.0 down to 0 and back
step:   dd      SLIDE_STEP
leaving: dd     0                       ; sliding out after cancel
row:    dd      0                       ; the cursor's row; ROWS is the BACK button
pulse:  dd      0                       ; the button highlight, 0 to 0x100 and back
pulsedir: dd    0
