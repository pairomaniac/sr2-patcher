; devices.asm - the Device Settings page in Options.dll.
;
; Two entries in the top-level state table the patcher moves into
; .sr2d, reached with esi = the Options object as every case there is:
;
;   +0  init   state 0xc: binds the page's UV table to the loaded sheets
;              - once per load of the DLL, since the binding replaces
;              each entry's sheet index with its handle in place - fills
;              the value strings from the records, starts the slide-in,
;              steps to 0xd and falls into exec.
;   +5  exec   state 0xd: draws every entry of the page's list, slid in
;              from the right by 40 px a frame as the stock pages are.
;              The cursor moves on up and down; left, right or confirm
;              on the PLAYER row shows the other player; confirm on an
;              action row waits for a key or a pad input and binds it,
;              swapping with the row that had it, ESC or Start held
;              giving up; left and right on DEADZONE step it; DEFAULT
;              restores; BACK, or cancel, slides the page out to the
;              left and only then puts the menu's state back. Leaves
;              through the dispatcher's epilogue.
;
; The game's input objects are reached through the holder the exe fills
; (MAGIC_INPUT): its +8 is the exe's input wrapper, whose +0x14(mask) is
; a player's pressed key bits and whose +4 is MGInput's input object;
; from there GetConfig (+0x34), GetDevice (+0x20) for the keyboard and
; its GetState (+0x38, the 256 key bytes), a config's record list at
; +0x124 - a
; pointer to the head of a ring of (next, prev, record) nodes - and
; Persist (+0x30) to save; the pad through the poll the annex in
; MGInput.dll publishes at an exe slot (MAGIC_PADPOLL). A row's key
; record is the first of its action
; with a source under 0x100, its pad record the first at 0x300-0x37f
; without the menu-only bit.
;
; The sprites, their quads and UV entries, the draw list and the data
; block (MAGIC_BINDDATA: the rows' actions, the defaults, the value
; strings, the names) are built by the patcher after this code. The list
; is 40-byte entries: kind (1 a sprite, 2 a string, 0 the end), the
; sprite or string, x, y, z or the text routine's flags, alpha, red,
; green, blue in 256ths, and the cursor's hold on the entry: 0 for none,
; else the first and last row (plus one) in the low bytes and in bits
; 16-23 what the cursor on one of those rows does to it - 1 solid red,
; the stock's row, and during a bind blue pulsing to white; 3 red pulsing
; to white, a button, with which one in bits 24-31, since the row after
; the last holds both, DEFAULT and BACK, left and right between them; 4
; white fading, its row's values. Holds 5 to 7 are the hint bar's, for
; every row: the entry rises with the bar; 6 is shown only outside a
; bind, 7 only during one. The DLL is relocated on every load: the blob
; finds its own address with a call/pop and subtracts its RVA to get the
; image base, and every DLL address here is an RVA from that, filled in
; from the build's row.

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
%define MAGIC_PADPOLL   0xDFDFDFDF      ; the absolute address of the exe slot holding the annex's page poll
%define MAGIC_BINDDATA  0xDEDEDEDE      ; the page's data block, laid out by the patcher; its
                                        ; parts added in a second instruction, or the placeholder
                                        ; folds into the displacement and is never filled:
%define D_ROWACTS       0               ;   the rows' action ids
%define D_LIVE          15              ;   1 when the build's MGInput carries the annex; else the page only shows
%define D_DEFAULTS      16              ;   the shipped (key, pad) per player-row
%define D_VALUES        80              ;   the value strings, 2 a row
%define D_KEYNAMES      656             ;   a name a scancode
%define D_PADNAMES      3728            ;   a name a pad input
%define NAME            12
%define VALUE           16
%define DRIVING         8
%define ACT_DEADZONE    0xff
%define ACT_SELECTOR    0xfe            ; row 0: the player shown, left and right switch
%define VALUE_LABEL     18              ; the value string the selector's label is
%define PAD_BASE        0x300           ; pad sources: PAD_BASE + player * 0x40 + input
%define PAD_START       4
%define MENU_ONLY       0x20            ; on a pad source: the menus' own, never a row's
%define PAD_STICKS      18              ; inputs from here are stick halves, 0..10000
%define PAD_INPUTS      26
%define IN_DEADZONE     0x3f            ; reads the player's deadzone
%define STICK_ON        5000
%define KEY_ESC         1
%define HOLD_FRAMES     60
%define DEADZONE_STEP   500
%define DEADZONE_MAX    9000
%define DEADZONE_DEFAULT 1000

%define STATE           8               ; the Options object's state
%define MOVE_SOUND      0xe             ; the stock's for cursor moves
%define PICK_SOUND      0xf             ; for confirming, BACK included
%define CANCEL_SOUND    0x10            ; for backing out
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
%define PULSE_STEP      0x10
%define HOLD_ROW        1
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
        mov     dword [edi + button - $$], 0
        mov     dword [edi + shown - $$], 0
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
        lea     eax, [ebx + MAGIC_BINDDATA]
        cmp     byte [eax + D_LIVE], 0
        je      .live
        push    ebp
        mov     ebp, edi
        call    refresh                 ; the values from the records
        pop     ebp
.live:
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
        jne     .waiting
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
        jnz     .cancel
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
        mov     eax, PICK_SOUND
        call    .sound
        cmp     dword [ebp + button - $$], 1
        je      .go                     ; BACK
        lea     eax, [ebx + MAGIC_BINDDATA]
        cmp     byte [eax + D_LIVE], 0
        je      .out
        call    defaults                ; DEFAULT
        jmp     .out
.onrow:
        lea     eax, [ebx + MAGIC_BINDDATA]
        cmp     byte [eax + D_LIVE], 0
        je      .out
        call    rowof                   ; eax = the player shown, ecx = the row, edx = its action
        cmp     edx, ACT_SELECTOR
        je      .selector
        cmp     edx, ACT_DEADZONE
        je      .deadzone
        test    edi, KEY_CONFIRM
        jz      .out
        call    snapshot                ; what is held now is not a press
        mov     dword [ebp + binding - $$], 1
        mov     dword [ebp + held - $$], 0
        mov     eax, PICK_SOUND
        call    .sound
        jmp     .out
.selector:                              ; left, right or confirm: the other player
        test    edi, KEY_LEFT | KEY_RIGHT | KEY_CONFIRM
        jz      .out
        xor     dword [ebp + shown - $$], 1
        call    refresh
        mov     eax, MOVE_SOUND
        call    .sound
        jmp     .out
.deadzone:                              ; left and right, 5% a step
        test    edi, KEY_LEFT | KEY_RIGHT
        jz      .out
        push    eax
        lea     eax, [eax * 8]
        lea     eax, [eax * 8 + PAD_BASE + IN_DEADZONE]
        call    padpoll
        test    edi, KEY_LEFT
        jz      .more
        sub     eax, DEADZONE_STEP
        jns     .setdz
        xor     eax, eax
        jmp     .setdz
.more:  add     eax, DEADZONE_STEP
        cmp     eax, DEADZONE_MAX
        jbe     .setdz
        mov     eax, DEADZONE_MAX
.setdz: call    dzname                  ; edx = "DZnnnn"
        pop     eax
        call    savecfg
        call    refresh
        mov     eax, MOVE_SOUND
        call    .sound
        jmp     .out
.waiting:                               ; a wait for a key or a pad input
        call    waittick
        jmp     .out
.cancel:
        mov     eax, CANCEL_SOUND
        call    .sound
.go:
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


; ---- the bindings ---------------------------------------------------
; All of these keep ebx (the image base) and ebp (the blob) and, unless
; said, every register but eax.

; eax = the MGInput input object: the holder's wrapper, whose +4 is it.
getinput:
        mov     eax, [ebx + MAGIC_INPUT]
        mov     eax, [eax + 8]
        mov     eax, [eax + 4]
        ret

; eax = a COM object, or 0: released.
release:
        test    eax, eax
        jz      .none
        push    eax
        push    ecx
        mov     ecx, [eax]
        push    eax
        call    [ecx + 8]
        pop     ecx
        pop     eax
.none:  ret

; eax = player: eax = its config, a reference held, or 0.
getcfg:
        push    ecx
        push    edx
        push    0                       ; the out slot
        mov     ecx, eax
        mov     edx, esp
        call    getinput
        push    edx
        push    ecx
        push    eax
        mov     eax, [eax]
        call    [eax + 0x34]            ; GetConfig(player, &cfg)
        pop     eax
        pop     edx
        pop     ecx
        ret

; eax = config, ecx = action, edx = 1 for its pad record, 0 its keyboard
; one: eax = the first such record in the config's list, or 0.
findrec:
        push    esi
        push    edi
        mov     esi, [eax + 0x124]      ; the list's head node
        mov     eax, [esi]
.next:  cmp     eax, esi
        je      .none
        mov     edi, [eax + 8]          ; the record
        cmp     [edi + 0x10c], ecx
        jne     .skip
        cmp     dword [edi + 0x138], 0
        je      .skip
        push    eax
        mov     eax, [edi + 0x13c]      ; a key under 0x100, a pad input in 0x300..0x37f without the menu-only bit, else neither
        cmp     eax, 0x100
        jb      .key
        sub     eax, PAD_BASE
        cmp     eax, 0x80
        jae     .neither
        test    eax, MENU_ONLY
        jnz     .neither
        mov     eax, 1
        jmp     .kind
.key:   xor     eax, eax
.kind:  cmp     eax, edx
        pop     eax
        jne     .skip
        mov     eax, edi
        pop     edi
        pop     esi
        ret
.skip:  mov     eax, [eax]
        jmp     .next
.neither:
        pop     eax
        jmp     .skip
.none:  xor     eax, eax
        pop     edi
        pop     esi
        ret

; eax = player, ecx = row 0..7, edx = 1 pad / 0 keyboard: eax = the record, or 0.
rowrec:
        push    ecx
        push    edx
        push    esi
        mov     esi, edx
        movzx   ecx, byte [ebx + MAGIC_BINDDATA + D_ROWACTS + ecx]
        call    getcfg
        test    eax, eax
        jz      .out
        push    eax
        mov     edx, esi
        call    findrec
        mov     esi, eax
        pop     eax
        call    release
        mov     eax, esi
.out:   pop     esi
        pop     edx
        pop     ecx
        ret

; eax = player, edx = a name or 0: the config saved to the file.
savecfg:
        push    eax
        push    ecx
        push    edx
        call    getcfg
        pop     edx
        test    eax, eax
        jz      .out
        push    eax
        push    1
        push    edx
        push    eax
        mov     ecx, [eax]
        call    [ecx + 0x30]            ; Persist(name, save)
        pop     eax
        call    release
.out:   pop     ecx
        pop     eax
        ret

; eax = a pad source id: eax = its value, through the poll the annex in
; MGInput.dll publishes; 0 while there is none.
padpoll:
        push    ecx
        push    edx
        push    0                       ; the value
        mov     ecx, [MAGIC_PADPOLL]
        test    ecx, ecx
        jz      .out
        mov     edx, esp
        push    0                       ; &range
        push    edx                     ; &value
        push    eax                     ; source
        call    ecx
.out:   pop     eax
        pop     edx
        pop     ecx
        ret

; eax = the keyboard's 256 key bytes, or 0.
keyarray:
        push    ecx
        push    edx
        push    0
        push    0
        call    getinput
        lea     edx, [esp + 4]
        push    edx
        push    0
        push    3
        push    eax
        mov     ecx, [eax]
        call    [ecx + 0x20]
        mov     eax, [esp + 4]
        test    eax, eax
        jz      .out
        mov     edx, esp
        push    0
        push    edx
        push    eax
        mov     ecx, [eax]
        call    [ecx + 0x38]            ; GetState(&keys, 0)
        mov     eax, [esp + 4]
        call    release
.out:   pop     eax
        add     esp, 4
        pop     edx
        pop     ecx
        ret

; eax = the player shown, ecx = the cursor's row less the selector, edx =
; the row's action: ACT_SELECTOR on row 0.
rowof:
        mov     eax, [ebp + shown - $$]
        mov     ecx, [ebp + row - $$]
        mov     edx, ACT_SELECTOR
        test    ecx, ecx
        jz      .done
        dec     ecx
        movzx   edx, byte [ebx + MAGIC_BINDDATA + D_ROWACTS + ecx]
.done:  ret

; eax = the cursor's player, ecx = its row: the pad input eax pressed
; now. edi kept.
padpressed:
        push    ecx
        lea     ecx, [eax * 8]
        lea     eax, [ecx * 8 + PAD_BASE]
        pop     ecx
        add     eax, ecx
        call    padpoll
        cmp     ecx, PAD_STICKS
        jb      .digital
        cmp     eax, STICK_ON
        seta    al
        movzx   eax, al
        ret
.digital:
        test    eax, eax
        setne   al
        movzx   eax, al
        ret

; What is down as a wait starts, so only a fresh press binds.
snapshot:
        push    eax
        push    ecx
        push    esi
        push    edi
        call    keyarray
        lea     edi, [ebp + snapkeys - $$]
        mov     ecx, 64
        test    eax, eax
        jz      .nokeys
        mov     esi, eax
        rep movsd
        jmp     .pads
.nokeys:
        xor     eax, eax
        rep stosd
.pads:  call    rowof
        xor     ecx, ecx
.pad:   push    eax
        call    padpressed
        mov     [ebp + snappad - $$ + ecx], al
        pop     eax
        inc     ecx
        cmp     ecx, PAD_INPUTS
        jb      .pad
        pop     edi
        pop     esi
        pop     ecx
        pop     eax
        ret

; A frame of the wait: ESC or Start held gives up, a fresh key or pad
; input binds. edi is the frame's key bits, unused here.
waittick:
        push    ecx
        push    esi
        call    keyarray
        test    eax, eax
        jz      .pads
        mov     esi, eax
        test    byte [esi + KEY_ESC], 0x80
        jz      .keys
        cmp     byte [ebp + snapkeys - $$ + KEY_ESC], 0
        jne     .keys
        jmp     .giveup
.keys:  mov     ecx, 2
.key:   test    byte [esi + ecx], 0x80
        jz      .keyup
        cmp     byte [ebp + snapkeys - $$ + ecx], 0
        jne     .nextkey
        mov     eax, ecx
        call    bindkey
        jmp     .bound
.keyup: mov     byte [ebp + snapkeys - $$ + ecx], 0     ; released since the wait began: a press now is fresh
.nextkey:
        inc     ecx
        cmp     ecx, 0x100
        jb      .key
.pads:  call    rowof
        xor     ecx, ecx
.pad:   cmp     ecx, PAD_START
        je      .nextpad
        push    eax
        call    padpressed
        test    eax, eax
        pop     eax
        jz      .padup
        cmp     byte [ebp + snappad - $$ + ecx], 0
        jne     .nextpad
        mov     eax, ecx
        call    bindpad
        jmp     .bound
.padup: mov     byte [ebp + snappad - $$ + ecx], 0
.nextpad:
        inc     ecx
        cmp     ecx, PAD_INPUTS
        jb      .pad
        mov     ecx, PAD_START          ; Start held a second gives up
        call    padpressed
        test    eax, eax
        jz      .released
        inc     dword [ebp + held - $$]
        cmp     dword [ebp + held - $$], HOLD_FRAMES
        jb      .out
.giveup:
        mov     dword [ebp + binding - $$], 0
        mov     eax, CANCEL_SOUND
        call    .sound
        jmp     .out
.released:
        mov     dword [ebp + held - $$], 0
        jmp     .out
.bound: mov     dword [ebp + binding - $$], 0
        mov     eax, PICK_SOUND
        call    .sound
.out:   pop     esi
        pop     ecx
        ret
.sound: mov     ecx, [ebx + MAGIC_SOUNDOBJ]
        push    0
        push    0
        push    0
        push    eax
        lea     eax, [ebx + MAGIC_PLAYSOUND]
        call    eax
        ret

; eax = a key: the cursor's row takes it; the row that had it, either
; player's, takes the row's old key.
bindkey:
        push    ecx
        push    edx
        push    esi
        push    edi
        mov     esi, eax
        call    rowof
        xor     edx, edx
        call    rowrec
        test    eax, eax
        jz      .out
        mov     edi, eax                ; the row's record
        mov     eax, [edi + 0x13c]
        mov     [ebp + oldsrc - $$], eax
        xor     eax, eax                ; the other rows, both players
.player:
        xor     ecx, ecx
.row:   xor     edx, edx
        push    eax
        call    rowrec
        test    eax, eax
        jz      .next
        cmp     eax, edi
        je      .next
        cmp     [eax + 0x13c], esi
        jne     .next
        mov     edx, [ebp + oldsrc - $$]
        mov     [eax + 0x13c], edx
.next:  pop     eax
        inc     ecx
        cmp     ecx, DRIVING
        jb      .row
        inc     eax
        cmp     eax, 2
        jb      .player
        mov     [edi + 0x13c], esi
        xor     eax, eax
        xor     edx, edx
        call    savecfg
        inc     eax
        call    savecfg
        call    refresh
.out:   pop     edi
        pop     esi
        pop     edx
        pop     ecx
        ret

; eax = a pad input: the cursor's row takes it; the row of the same
; player that had it takes the row's old input.
bindpad:
        push    ecx
        push    edx
        push    esi
        push    edi
        mov     esi, eax
        call    rowof
        push    eax
        lea     eax, [eax * 8]
        lea     eax, [eax * 8 + PAD_BASE]
        add     esi, eax                ; the source id
        pop     eax
        mov     edx, 1
        call    rowrec
        test    eax, eax
        jz      .out
        mov     edi, eax
        mov     eax, [edi + 0x13c]
        mov     [ebp + oldsrc - $$], eax
        call    rowof
        xor     ecx, ecx
.row:   mov     edx, 1
        push    eax
        call    rowrec
        test    eax, eax
        jz      .next
        cmp     eax, edi
        je      .next
        cmp     [eax + 0x13c], esi
        jne     .next
        mov     edx, [ebp + oldsrc - $$]
        mov     [eax + 0x13c], edx
.next:  pop     eax
        inc     ecx
        cmp     ecx, DRIVING
        jb      .row
        mov     [edi + 0x13c], esi
        xor     edx, edx
        call    savecfg
        call    refresh
.out:   pop     edi
        pop     esi
        pop     edx
        pop     ecx
        ret

; DEFAULT: both players' rows back to the shipped set, the deadzones too.
defaults:
        push    eax
        push    ecx
        push    edx
        push    esi
        push    edi
        xor     eax, eax
.player:
        xor     ecx, ecx
.row:   lea     esi, [eax * 8]
        add     esi, ecx
        lea     esi, [ebx + MAGIC_BINDDATA + esi * 4]
        add     esi, D_DEFAULTS         ; the (key, pad) words
        xor     edx, edx
        push    eax
        call    rowrec
        test    eax, eax
        jz      .nokey
        movzx   edx, word [esi]
        mov     [eax + 0x13c], edx
.nokey: mov     eax, [esp]
        mov     edx, 1
        call    rowrec
        test    eax, eax
        jz      .nopad
        mov     edx, [esp]
        shl     edx, 6
        add     edx, PAD_BASE
        movzx   edi, word [esi + 2]
        add     edx, edi
        mov     [eax + 0x13c], edx
.nopad: pop     eax
        inc     ecx
        cmp     ecx, DRIVING
        jb      .row
        push    eax
        mov     eax, DEADZONE_DEFAULT
        call    dzname
        pop     eax
        call    savecfg
        inc     eax
        cmp     eax, 2
        jb      .player
        call    refresh
        pop     edi
        pop     esi
        pop     edx
        pop     ecx
        pop     eax
        ret

; eax = a deadzone, 0..10000: edx = "DZnnnn" for Persist.
dzname:
        push    eax
        push    ecx
        push    esi
        lea     esi, [ebp + dzbuf - $$]
        mov     word [esi], 'DZ'
        add     esi, 2
        mov     ecx, 1000
.next:  xor     edx, edx
        div     ecx                     ; eax the digit, edx the rest
        add     al, '0'
        mov     [esi], al
        inc     esi
        push    edx
        mov     eax, ecx
        xor     edx, edx
        mov     ecx, 10
        div     ecx
        mov     ecx, eax                ; the next divisor
        pop     eax
        test    ecx, ecx
        jnz     .next
        mov     byte [esi], 0
        lea     edx, [ebp + dzbuf - $$]
        pop     esi
        pop     ecx
        pop     eax
        ret

; Every value string from the shown player's records and deadzone, and
; the selector's label.
refresh:
        push    eax
        push    ecx
        push    edx
        push    esi
        push    edi
        mov     eax, [ebp + shown - $$]
        xor     ecx, ecx
.row:   push    eax
        push    ecx
        lea     edi, [ecx * 2]          ; the value strings: row * 2, its pad one after
        shl     edi, 4
        lea     edi, [ebx + MAGIC_BINDDATA + edi]
        add     edi, D_VALUES
        xor     edx, edx
        call    rowrec
        xor     esi, esi                ; no record: name 0
        test    eax, eax
        jz      .named
        movzx   esi, byte [eax + 0x13c]
.named: lea     esi, [esi + esi * 2]
        lea     esi, [ebx + MAGIC_BINDDATA + esi * 4]
        add     esi, D_KEYNAMES
        call    setvalue
        mov     eax, [esp + 4]
        mov     ecx, [esp]
        mov     edx, 1
        add     edi, VALUE
        call    rowrec
        mov     esi, eax
        test    eax, eax
        jz      .unnamed
        mov     esi, [esi + 0x13c]
        and     esi, 0x3f
        lea     esi, [esi + esi * 2]
        lea     esi, [ebx + MAGIC_BINDDATA + esi * 4]
        add     esi, D_PADNAMES
        jmp     .setpad
.unnamed:
        lea     esi, [ebx + MAGIC_BINDDATA]
        add     esi, D_KEYNAMES         ; scancode 0's name, a dash
.setpad:
        call    setvalue
        pop     ecx
        pop     eax
        inc     ecx
        cmp     ecx, DRIVING
        jb      .row
        ; the deadzone row, as a percentage
        lea     edi, [ebx + MAGIC_BINDDATA]
        add     edi, D_VALUES + DRIVING * 2 * VALUE
        push    eax
        lea     eax, [eax * 8]
        lea     eax, [eax * 8 + PAD_BASE + IN_DEADZONE]
        call    padpoll
        xor     edx, edx
        mov     ecx, 100
        div     ecx                     ; the percent
        mov     ecx, 10
        xor     edx, edx
        div     ecx                     ; eax tens, edx units
        test    eax, eax
        jz      .units
        add     al, '0'
        mov     [edi], al
        inc     edi
.units: add     dl, '0'
        mov     [edi], dl
        mov     byte [edi + 1], 0
        pop     eax
        ; the label: PLAYER 1 or 2
        lea     edi, [ebx + MAGIC_BINDDATA]
        add     edi, D_VALUES + VALUE_LABEL * VALUE
        lea     esi, [ebp + label - $$]
        call    setvalue
        add     al, '1'                 ; (al is the player's low byte, from eax)
        mov     [edi + 7], al
        pop     edi
        pop     esi
        pop     edx
        pop     ecx
        pop     eax
        ret

; esi = a NAME-byte name, edi = a VALUE-byte value string: copied.
setvalue:
        push    ecx
        push    esi
        push    edi
        mov     ecx, NAME / 4
        rep movsd
        mov     dword [edi], 0
        pop     edi
        pop     esi
        pop     ecx
        ret

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
held:   dd      0                       ; frames Start has been held during a wait
shown:  dd      0                       ; the player the page shows, 0 or 1
label:  db      'PLAYER 1', 0, 0, 0, 0  ; the selector's, NAME bytes, its digit set by refresh
oldsrc: dd      0                       ; the source the bound row had
dzbuf:  times 8 db 0                    ; "DZnnnn" for Persist
snapkeys: times 256 db 0                ; the keys down as the wait began
snappad: times 32 db 0                  ; the pad inputs down as it began
