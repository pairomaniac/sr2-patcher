; devices.asm - the Device Settings page in Options.dll.
;
; Two entries in the top-level state table the patcher moves into
; .sr2d, reached with esi = the Options object as every case there is:
;
;   +0  init   state 0xc: binds the page's UV table to the loaded sheets
;              - once per load of the DLL, since the binding replaces
;              each entry's sheet index with its handle in place - starts
;              the slide-in, steps to 0xd and falls into exec.
;   +5  exec   state 0xd: draws every entry of the page's list, slid in
;              from the right by 40 px a frame as the stock pages are.
;              In place, the hint bar pops up as the frame's does and the
;              cursor moves on up and down; confirm on a row starts a
;              bind - the row pulses blue to white, the bar says to
;              press the button, cancel gives up - and confirm on BACK,
;              or cancel, drops the bar and slides
;              the page on out to the left, as the stock pages go, and
;              only then puts the menu's state back. Leaves through the
;              dispatcher's epilogue.
;
; The sprites, their quads and UV entries and the draw list are data the
; patcher builds after this code. The list is 40-byte entries: kind (1 a
; sprite, 2 a string, 0 the end), the sprite or string, x, y, z or the
; text routine's flags, alpha, red, green, blue in 256ths, and the
; cursor's hold on the entry: 0 for none, else the first and last row
; (plus one) in the low bytes and in bits 16-23 what the cursor on one of
; those rows does to it - 1 solid red, the stock's row, and during a
; bind blue pulsing to white; 2 red with a little green and blue, its
; group plate; 3 red pulsing to white, a button, with which one in bits
; 24-31, since the row after the last holds both, DEFAULT and BACK, left
; and right between them; 4 white fading, its row's value. Holds 5 to 7
; are the hint bar's, for every row: the entry rises with the bar; 6 is
; shown only outside a bind, 7 only during one. The DLL is relocated on
; every load: the blob finds its own address with a call/pop and
; subtracts its RVA to get the image base, and every DLL address here is
; an RVA from that, filled in from the build's row.

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
%define MOVE_SOUND      0xe             ; the stock's for cursor moves and leaving
%define PICK_SOUND      0xf             ; and for confirming
%define KEY_CANCEL      2
%define KEY_CONFIRM     0x41
%define KEY_UP          0x200
%define KEY_DOWN        0x400
%define KEY_LEFT        0x800
%define KEY_RIGHT       0x1000
%define SLIDE_FROM      0x44200000      ; 640.0
%define SLIDE_GONE      0xC4200000      ; -640.0
%define SLIDE_STEP      0x42200000      ; 40.0
%define ONE             0x3f800000      ; 1.0
%define BAR_STEP        0x3dcccccd      ; 0.1, the frame's hint bar a frame
%define BAR_Y           0x43e18000      ; 451.0, the bar's bottom edge, which it grows from
%define FULL            0x100
%define GROUP_TINT      0x20            ; green and blue of the group's red
%define PULSE_STEP      0x10
%define HOLD_ROW        1
%define HOLD_GROUP      2
%define HOLD_BUTTON     3
%define HOLD_VALUE      4
%define HOLD_BAR        5
%define HOLD_BAR_IDLE   6
%define HOLD_BAR_BIND   7

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
        mov     dword [edi + bar - $$], 0
        mov     dword [edi + binding - $$], 0
        mov     dword [edi + button - $$], 1
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

; ---- the list --------------------------------------------------------
.entry:
        mov     eax, [edi]
        test    eax, eax
        jz      .drawn
        mov     ecx, [edi + 12]         ; y and vertical scale as given
        mov     [ebp + y - $$], ecx
        mov     dword [ebp + sy - $$], ONE
        call    .holds
        jnc     .free
        cmp     cl, HOLD_BAR
        jb      .free
        cmp     dword [ebp + binding - $$], 0     ; the bar's strings, one or the other
        je      .idle
        cmp     cl, HOLD_BAR_IDLE
        je      .next
        jmp     .risen
.idle:
        cmp     cl, HOLD_BAR_BIND
        je      .next
.risen:                                 ; with the bar: y from its bottom edge, scaled
        mov     ecx, [ebp + bar - $$]
        mov     [ebp + sy - $$], ecx
        fld     dword [edi + 12]
        fsub    dword [ebp + bary - $$]
        fmul    dword [ebp + bar - $$]
        fadd    dword [ebp + bary - $$]
        fstp    dword [ebp + y - $$]
.free:
        cmp     eax, 2
        je      .string

        push    0                       ; the sprite call's sixteen dwords
        push    0
        push    0
        call    .holds
        jnc     .plain
        cmp     cl, HOLD_BAR
        jae     .plain
        cmp     cl, HOLD_ROW           ; 1: red, or blue pulsing to white during a bind
        jne     .notrow
        cmp     dword [ebp + binding - $$], 0
        jne     .bindpulse
        push    0
        push    0
        push    FULL
        push    FULL
        jmp     .coloured
.notrow:
        xor     edx, edx
        cmp     cl, HOLD_GROUP
        jne     .kind3
        mov     edx, GROUP_TINT
.kind3:
        cmp     cl, HOLD_BUTTON
        jne     .held
        mov     edx, [ebp + pulse - $$]
.held:
        push    edx                     ; blue, green, red, alpha
        push    edx
        push    FULL
        push    FULL
        jmp     .coloured
.bindpulse:                             ; the bind: the row blue pulsing to white
        mov     edx, [ebp + pulse - $$]
        push    FULL
        push    edx
        push    edx
        push    FULL
        jmp     .coloured
.plain:
        push    dword [edi + 32]        ; blue, green, red, alpha
        push    dword [edi + 28]
        push    dword [edi + 24]
        push    dword [edi + 20]
.coloured:
        push    dword [ebp + sy - $$]   ; scale y, x
        push    ONE
        push    0
        push    0
        push    0
        push    dword [edi + 16]        ; z
        push    dword [ebp + y - $$]    ; y
        push    eax                     ; x, slid: the entry's plus the offset
        fld     dword [edi + 8]
        fadd    dword [ebp + slide - $$]
        fstp    dword [esp]
        push    dword [edi + 4]         ; the sprite
        lea     eax, [ebx + MAGIC_DRAW]
        call    eax
        add     esp, 0x40
        jmp     .next

.string:
        push    dword [edi + 16]        ; the text routine's thirteen: flags
        lea     eax, [ebx + MAGIC_GLYPHS]
        push    eax                     ; its glyph table
        call    .holds
        jnc     .plaintext
        cmp     cl, HOLD_VALUE
        jne     .plaintext
        mov     eax, [ebp + pulse - $$] ; 4: white, alpha 0x80 to 0x100 with the pulse
        sar     eax, 1
        add     eax, 0x80
        push    FULL                    ; blue, green, red, alpha
        push    FULL
        push    FULL
        push    eax
        jmp     .colouredtext
.plaintext:
        push    dword [edi + 32]        ; blue, green, red, alpha
        push    dword [edi + 28]
        push    dword [edi + 24]
        push    dword [edi + 20]
.colouredtext:
        push    dword [ebp + sy - $$]   ; scale y, x
        push    ONE
        push    0x41200000              ; the advance of a glyph it lacks, 10.0
        push    0x41200000              ; z 10.0, the stock's text
        push    dword [ebp + y - $$]    ; y
        push    eax                     ; x, slid
        fld     dword [edi + 8]
        fadd    dword [ebp + slide - $$]
        fstp    dword [esp]
        push    dword [edi + 4]         ; the string
        lea     eax, [ebx + MAGIC_TEXT]
        call    eax
        add     esp, 0x34
.next:
        add     edi, 40
        jmp     .entry

; carry set, ecx the kind, when the cursor's row holds the entry at edi.
; eax kept.
.holds:
        push    eax
        mov     ecx, [edi + 36]
        test    ecx, ecx
        jz      .nohold
        movzx   eax, cl                 ; first row + 1 .. last row + 1
        dec     eax
        cmp     [ebp + row - $$], eax
        jl      .nohold
        movzx   eax, ch
        dec     eax
        cmp     [ebp + row - $$], eax
        jg      .nohold
        shr     ecx, 16                 ; the kind, and in ch a button's index
        cmp     cl, HOLD_BUTTON
        jne     .holding
        movzx   eax, ch
        cmp     [ebp + button - $$], eax
        jne     .nohold
.holding:
        pop     eax
        stc
        ret
.nohold:
        pop     eax
        clc
        ret

; ---- the frame ------------------------------------------------------
.drawn:
        mov     eax, [ebp + pulsedir - $$]   ; the pulse, 0 to 0x100 and back
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
        jz      .settled
        fld     dword [ebp + slide - $$]    ; sliding in
        fsub    dword [ebp + step - $$]
        fstp    dword [ebp + slide - $$]
        mov     eax, [ebp + slide - $$]
        test    eax, eax                ; to zero, or past it
        jg      .out
        mov     dword [ebp + slide - $$], 0
        jmp     .out
.settled:
        mov     eax, [ebp + bar - $$]   ; in place: the bar up, then input
        cmp     eax, ONE
        jae     .input
        fld     dword [ebp + bar - $$]
        fadd    dword [ebp + barstep - $$]
        fstp    dword [ebp + bar - $$]
        cmp     dword [ebp + bar - $$], ONE
        jb      .out
        mov     dword [ebp + bar - $$], ONE
        jmp     .out
.leave:
        mov     eax, [ebp + bar - $$]   ; the bar down, then out to the left, then the menu
        test    eax, eax
        jz      .leaving
        fld     dword [ebp + bar - $$]
        fsub    dword [ebp + barstep - $$]
        fstp    dword [ebp + bar - $$]
        mov     eax, [ebp + bar - $$]
        test    eax, eax
        jg      .out
        mov     dword [ebp + bar - $$], 0
        jmp     .out
.leaving:
        fld     dword [ebp + slide - $$]
        fsub    dword [ebp + step - $$]
        fstp    dword [ebp + slide - $$]
        cmp     dword [ebp + slide - $$], SLIDE_GONE    ; negative floats grow as unsigned
        jb      .out
        mov     dword [esi + STATE], 1  ; the menu, cursor where it was
        jmp     .out

; ---- input ----------------------------------------------------------
.input:
        mov     eax, [ebx + MAGIC_INPUT]
        mov     ecx, [eax + 8]
        test    ecx, ecx
        jz      .out
        mov     edx, [ecx]
        push    1
        call    [edx + 0x14]            ; the frame's key bits
        mov     edi, eax
        cmp     dword [ebp + binding - $$], 0
        jne     .bindkeys
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
        mov     eax, MOVE_SOUND
        call    .sound
        jmp     .out
.notup:
        test    edi, KEY_CANCEL
        jnz     .go
        mov     eax, [ebp + row - $$]
        cmp     eax, MAGIC_ROWS         ; the button row: left and right pick, confirm presses
        jne     .onrow
        test    edi, KEY_LEFT | KEY_RIGHT
        jz      .press
        xor     dword [ebp + button - $$], 1
        mov     eax, MOVE_SOUND
        call    .sound
        jmp     .out
.press:
        test    edi, KEY_CONFIRM
        jz      .out
        cmp     dword [ebp + button - $$], 1
        je      .go
        mov     eax, PICK_SOUND         ; DEFAULT: nothing to reset yet
        call    .sound
        jmp     .out
.onrow:
        test    edi, KEY_CONFIRM
        jz      .out
        mov     dword [ebp + binding - $$], 1
        mov     eax, PICK_SOUND
        call    .sound
        jmp     .out
.bindkeys:                              ; waiting for a button: cancel gives up
        test    edi, KEY_CANCEL
        jz      .out
        mov     dword [ebp + binding - $$], 0
        mov     eax, MOVE_SOUND
        call    .sound
        jmp     .out
.go:
        mov     eax, MOVE_SOUND
        call    .sound
        mov     dword [ebp + leaving - $$], 1
        jmp     .out

; plays sound eax
.sound:
        mov     ecx, [ebx + MAGIC_SOUNDOBJ]
        push    0
        push    0
        push    0
        push    eax
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
slide:  dd      0                       ; the slide's x offset, 640.0 down to 0 and on to -640
step:   dd      SLIDE_STEP
leaving: dd     0                       ; sliding out after cancel
row:    dd      0                       ; the cursor's row; ROWS is the BACK button
pulse:  dd      0                       ; the highlights' pulse, 0 to 0x100 and back
pulsedir: dd    0
bar:    dd      0                       ; the hint bar's height, 0 to 1.0
barstep: dd     BAR_STEP
bary:   dd      BAR_Y
binding: dd     0                       ; waiting for a button for the cursor's row
button: dd      0                       ; the button row's pick, 0 DEFAULT, 1 BACK
y:      dd      0                       ; the entry being drawn: its y and vertical scale
sy:     dd      0
