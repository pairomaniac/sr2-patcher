; padinput.asm - XInput gamepads and the SR2.CFG bind store, appended to
; MUSASHI\MGInput.dll.
;
; The game reads every action through MGInput: an action is a record of
; up to eight source ids (a chord, the first carrying the value), and
; each config, one per player, polls its device for each source through
; the device's vtable +0x58 (source, &value, &range). Keyboard sources
; are 1-0xff, joystick 0x101-0x168, mouse 0x201-0x20b. This annex answers
; 0x300-0x37f from XInput: 0x300 + player * 0x40 + input, the inputs
; listed at padvalue. The config's per-frame update is hooked to refresh
; that player's pad first, so a pad is read once a frame.
;
; The menus' left and right are the steering's actions, so the fixed
; sources that keep the menus navigable whatever is bound - D-pad, stick
; halves, arrows - are menu-only: a pad input with MENU_ONLY set, or a
; key as MENUKEY_BASE + scancode read from the keyboard device's array,
; answered only while the exe's car table (CARS) has no car in slot 0,
; which it has from a race's setup to its teardown.
;
; The registry helper's load and save, which the config's Persist calls
; with (this, slot "0"/"1", name, buf, count[, &got]), are replaced by
; the store below. A save whose name starts "DZ" takes the digits after
; it as that player's stick deadzone, 0-10000; input 0x3f reads it back.
;
; The entries sit at fixed offsets. Load, save and update are reached by
; a jmp from the site, whose displaced bytes the patcher copies into the
; replay slots here. The European and American build's device poll is
; hooked the same way; the Australian build, an older one, has no such
; method - its record update calls a static poll per device type - so
; there the keyboard poll's address in that dispatch is pointed at
; pollau instead. The Device Settings page polls the pad through
; pollpage, (source, &value, &range), whose address the annex writes to
; an exe slot (PUBLISH, in the writable room past .data) the page reads.
; The DLL is relocated on every load, so the blob finds its own address
; with a call/pop and every MAGIC_ but CARS and PUBLISH is an offset
; from the blob to something in the DLL, filled in by the patcher.

bits 32

%define MAGIC_LOADLIB   0xE3E3E3E3      ; offset to the LoadLibraryA IAT slot
%define MAGIC_GETPROC   0xE4E4E4E4      ; offset to the GetProcAddress IAT slot
%define MAGIC_UPDATE    0xE6E6E6E6      ; offset to the update site's continuation
%define MAGIC_POLL      0xE8E8E8E8      ; offset to the poll site's continuation
%define MAGIC_CARS      0xE9E9E9E9      ; the absolute address of the exe's car table
%define MAGIC_KBDPOLL   0xECECECEC      ; offset to the Australian build's stock keyboard poll
%define MAGIC_PUBLISH   0xEDEDEDED      ; the absolute address of the exe slot that takes pollpage's address

%define CFG_STOCK       0               ; where the text starts in the file
%define RECORD          0x34
%define PAD_BASE        0x300
%define PAD_SIDE        0x40
%define DEADZONE_DEFAULT 1000
%define DEADZONE_MAX    9000

%define GENERIC_READ    0x80000000
%define GENERIC_WRITE   0x40000000
%define OPEN_EXISTING   3
%define OPEN_ALWAYS     4
%define INVALID_HANDLE  -1
%define MAX_PATH        260

%define STATE_SIZE      16              ; XINPUT_STATE
%define PADS            4
%define RETRY_FRAMES    60              ; between looks for a pad on a side without one
%define TRIGGER_MIN     30              ; XINPUT_GAMEPAD_TRIGGER_THRESHOLD
%define FULL            10000
%define STICK_MAX       32767
%define KEY_DOWN        0x80            ; what the keyboard poll reports, value and range
%define IN_DEADZONE     0x3f            ; the virtual input that reads the deadzone
%define MENU_ONLY       0x20            ; on a pad input: answered only outside a race
%define MENUKEY_BASE    0x400           ; + a scancode: a key answered only outside a race

%define E_INVALIDARG    0x80070057

        jmp     near load               ; +0
        jmp     near save               ; +5
        jmp     near update             ; +10
        jmp     near poll               ; +15  the European build's device poll
        jmp     near pollau             ; +20  the Australian build's keyboard poll
entry_pollpage:
        jmp     near pollpage           ; +25  the Device Settings page's poll, published at PUBLISH

; ebx = the blob on return; nothing else touched.
getbase:
        call    .here
.here:  pop     ebx
        sub     ebx, .here - $$
        ret

; ---- the store ------------------------------------------------------
;
; A table of key and pad input per action per player and the two stick
; deadzones, written as text and parsed back, the names in the tables
; the patcher appends after the code:
;
;   [1P Controller]
;   Deadzone = 10
;   SteeringLeft = LS_LEFT
;   ...
;   [1P Keyboard]
;   SteeringLeft = LEFT
;   ...
;
; The text carries the eight driving actions; the menus' (up, down,
; enter, escape, start) are fixed, their defaults in T_DEFAULTS and no
; name in T_ACTNAMES. A load generates the player's records: the
; action's key record and pad record, then the menus' fixed ones - the
; bindable first, since the page takes an action's first key and pad
; records as the row's. A save takes the table back out of the records
; the config exports and rewrites the text. Lines it cannot read keep
; the defaults. An old file with the game's 100-byte block ahead of the
; text is read past it.

%define T_KEYNAMES      0               ; 256 names, NAME bytes each, spaces as _
%define T_PADNAMES      4096            ; 32 names
%define T_ACTNAMES      4608            ; 13 names
%define T_DEFAULTS      4816            ; 2 x 13 x (key word, pad word)
%define T_FIXKEYS       4920            ; 2 x 4 key words for actions 2..5
%define T_FIXPADS       4936            ; 8 x (action byte, input byte, MENU_ONLY set where it applies)
%define T_ORDER         4952            ; the actions in the text's order, 0xff after the last
%define T_FIXACTS       4965            ; the 4 actions the fixed keys are for
%define W_TABLE         4972            ; the live table, as T_DEFAULTS
%define W_DZ            5076            ; 2 dwords
%define W_TEXT          5084            ; the text, read and written here
%define W_GEN           7132            ; the records a load generates
%define W_END           9180
%define NAME            16
%define ACTIONS         13
%define TEXT_MAX        2047
%define NO_PAD          0xff
%define SECT_NONE       -1
%define SECT_KEYBOARD   0
%define SECT_CONTROLLER 1

; load(this, slot, name, buf, count, &got). The exe loads player 1's slot
; twice at start - once unnamed, clearing, then named "0" and appending -
; so a named load gets no records, or every record would be doubled.
load:
        push    ebx
        push    esi
        push    edi
        call    getbase
        call    ensure_table
        mov     esi, [esp + 0x14]       ; slot
        call    slot_of                 ; eax = the player
        jc      .bad
        xor     ecx, ecx
        cmp     dword [esp + 0x18], 0   ; name
        jne     .count
        call    generate                ; W_GEN holds the player's records, ecx of them
        mov     edi, [esp + 0x1c]       ; buf, or null for the count alone
        test    edi, edi
        jz      .count
        cmp     ecx, [esp + 0x20]
        jbe     .fits
        mov     ecx, [esp + 0x20]
.fits:  push    ecx
        imul    ecx, ecx, RECORD / 4
        lea     esi, [ebx + tables - $$ + W_GEN]
        rep movsd
        pop     ecx
.count: mov     edx, [esp + 0x24]
        test    edx, edx
        jz      .ok
        mov     [edx], ecx
.ok:    xor     eax, eax
        pop     edi
        pop     esi
        pop     ebx
        ret     0x18
.bad:   mov     eax, E_INVALIDARG
        pop     edi
        pop     esi
        pop     ebx
        ret     0x18

; save(this, slot, name, buf, count): the table from the records, a
; "DZnnnn" name into the deadzone, the text rewritten.
save:
        push    ebx
        push    esi
        push    edi
        call    getbase
        call    ensure_table
        mov     esi, [esp + 0x14]
        call    slot_of
        jc      .bad
        mov     edi, eax                ; the player
        mov     esi, [esp + 0x18]       ; name
        test    esi, esi
        jz      .named
        cmp     word [esi], 'DZ'
        jne     .named
        add     esi, 2
        call    number
        cmp     eax, FULL
        jbe     .setdz
        mov     eax, FULL
.setdz: mov     [ebx + tables - $$ + W_DZ + edi * 4], eax
.named:
        ; the table's row for this player: every key and pad forgotten,
        ; then the first of each per action from the records
        imul    eax, edi, ACTIONS * 4
        lea     edx, [ebx + tables - $$ + W_TABLE + eax]
        mov     ecx, ACTIONS
.clear: mov     word [edx], 0
        mov     word [edx + 2], NO_PAD
        add     edx, 4
        dec     ecx
        jnz     .clear
        mov     esi, [esp + 0x1c]       ; buf
        mov     ecx, [esp + 0x20]       ; count
.record:
        test    ecx, ecx
        jz      .written
        mov     eax, [esi]              ; id
        cmp     eax, ACTIONS
        jae     .next
        imul    edx, edi, ACTIONS * 4
        lea     edx, [edx + eax * 4]
        lea     edx, [ebx + tables - $$ + W_TABLE + edx]
        mov     eax, [esi + 0x14]       ; the first source
        cmp     eax, 0x100
        jae     .padsrc
        test    eax, eax
        jz      .next
        cmp     word [edx], 0
        jne     .next
        mov     [edx], ax
        jmp     .next
.padsrc:
        cmp     eax, PAD_BASE
        jb      .next
        cmp     eax, PAD_BASE + 2 * PAD_SIDE
        jae     .next
        cmp     word [edx + 2], NO_PAD
        jne     .next
        and     eax, 0x3f
        cmp     eax, IN_DEADZONE
        je      .next
        test    eax, MENU_ONLY
        jnz     .next
        mov     [edx + 2], ax
.next:  add     esi, RECORD
        dec     ecx
        jmp     .record
.written:
        call    write_text
        xor     eax, eax
        pop     edi
        pop     esi
        pop     ebx
        ret     0x14
.bad:   mov     eax, E_INVALIDARG
        pop     edi
        pop     esi
        pop     ebx
        ret     0x14

; esi = a slot name, "0" or "1": eax = the player, carry set on anything else.
slot_of:
        movzx   eax, byte [esi]
        sub     eax, '0'
        cmp     eax, 1
        ja      .bad
        clc
        ret
.bad:   stc
        ret

; eax = player: W_GEN takes its records, ecx = how many. Registers but
; eax and ecx kept.
generate:
        push    edx
        push    esi
        push    edi
        push    ebp
        mov     ebp, eax                ; the player
        lea     edi, [ebx + tables - $$ + W_GEN]
        imul    esi, eax, ACTIONS * 4
        lea     esi, [ebx + tables - $$ + W_TABLE + esi]
        xor     ecx, ecx                ; the count
        xor     edx, edx                ; the action
.action:
        push    edx
        movzx   eax, word [esi]
        push    ecx
        mov     ecx, edx
        call    record                  ; the key record, even with no key
        pop     ecx
        inc     ecx
        movzx   eax, word [esi + 2]
        cmp     eax, NO_PAD
        je      .nopad
        call    padsrc
        push    ecx
        mov     ecx, edx
        call    record
        pop     ecx
        inc     ecx
.nopad: pop     edx
        add     esi, 4
        inc     edx
        cmp     edx, ACTIONS
        jb      .action
        ; the fixed menu keys, on the actions T_FIXACTS names, menu-only
        imul    esi, ebp, 4 * 2
        lea     esi, [ebx + tables - $$ + T_FIXKEYS + esi]
        xor     edx, edx
.fixkey:
        movzx   eax, word [esi]
        add     eax, MENUKEY_BASE
        push    ecx
        movzx   ecx, byte [ebx + tables - $$ + T_FIXACTS + edx]
        call    record
        pop     ecx
        inc     ecx
        add     esi, 2
        inc     edx
        cmp     edx, 4
        jb      .fixkey
        ; the fixed menu pads, with MENU_ONLY in the table where it applies
        lea     esi, [ebx + tables - $$ + T_FIXPADS]
        mov     edx, 8
.fixpad:
        movzx   eax, byte [esi + 1]
        call    padsrc
        push    ecx
        movzx   ecx, byte [esi]
        call    record
        pop     ecx
        inc     ecx
        add     esi, 2
        dec     edx
        jnz     .fixpad
        pop     ebp
        pop     edi
        pop     esi
        pop     edx
        ret

; eax = a pad input: eax = its source id for player ebp.
padsrc:
        push    ecx
        mov     ecx, ebp
        shl     ecx, 6
        add     eax, ecx
        add     eax, PAD_BASE
        pop     ecx
        ret

; ecx = action, eax = source: a record at edi, which moves on. ecx kept.
record:
        push    ecx
        push    eax
        mov     eax, ecx
        stosd                           ; id
        xor     eax, eax
        cmp     ecx, 2
        jb      .norepeat
        cmp     ecx, 5
        ja      .norepeat
        mov     eax, 10                 ; the menus' repeat
        stosd
        mov     eax, 3
        stosd
        jmp     .rest
.norepeat:
        stosd
        stosd
.rest:  xor     eax, eax
        stosd                           ; deadzone
        mov     eax, FULL
        stosd                           ; saturation
        pop     eax
        stosd                           ; the source
        xor     eax, eax
        mov     ecx, 7
        rep stosd
        pop     ecx
        ret

; Once a session: the defaults, then whatever the file's text says.
ensure_table:
        cmp     dword [ebx + tableok - $$], 0
        jne     .done
        pushad
        call    resolve
        mov     dword [ebx + tableok - $$], 1
        lea     eax, [ebx + entry_pollpage - $$]
        mov     [MAGIC_PUBLISH], eax    ; the page's poll, for the page
        lea     esi, [ebx + tables - $$ + T_DEFAULTS]
        lea     edi, [ebx + tables - $$ + W_TABLE]
        mov     ecx, 26
        rep movsd
        mov     dword [ebx + tables - $$ + W_DZ], DEADZONE_DEFAULT
        mov     dword [ebx + tables - $$ + W_DZ + 4], DEADZONE_DEFAULT
        push    OPEN_EXISTING
        push    GENERIC_READ
        call    open_cfg
        cmp     eax, INVALID_HANDLE
        je      .out
        mov     esi, eax
        lea     eax, [ebx + tables - $$ + W_TEXT]
        push    0
        lea     ecx, [ebx + got - $$]
        push    ecx
        push    TEXT_MAX
        push    eax
        push    esi
        call    [ebx + fn_readfile - $$]
        push    esi
        call    [ebx + fn_closehandle - $$]
        mov     eax, [ebx + got - $$]
        mov     byte [ebx + tables - $$ + W_TEXT + eax], 0
        xor     eax, eax
        cmp     dword [ebx + tables - $$ + W_TEXT], 'disp'     ; an old file: the game's block first
        jne     .parse
        mov     eax, 100
.parse: call    parse
.out:   popad
.done:  ret

; The text at W_TEXT, from eax, into the table: "[nP Controller]" and "[nP Keyboard]"
; open a section, in which "Name = value" lines set an action's pad input
; or key (or "-"), and "Deadzone = nn" a controller's deadzone in percent.
; The "=" is optional.
parse:                                  ; eax = where in W_TEXT to start
        lea     esi, [ebx + tables - $$ + W_TEXT + eax]
        mov     dword [ebx + sect - $$], SECT_NONE
.line:  call    token                   ; esi = the token, ecx its length, edi past it
        jnz     .have
        cmp     byte [esi], 0           ; an empty line, or the end
        je      .end
        jmp     .skip
.have:  cmp     byte [esi], '['
        jne     .setting
        mov     dword [ebx + sect - $$], SECT_NONE      ; any section header closes the last
        movzx   eax, byte [esi + 1]     ; [1P Controller] / [2P Keyboard]
        sub     eax, '1'
        cmp     eax, 1
        ja      .skip
        cmp     byte [esi + 2], 'P'
        jne     .skip
        mov     [ebx + sectplayer - $$], eax
        mov     esi, edi
        call    token
        jz      .skip
        mov     dword [ebx + sect - $$], SECT_CONTROLLER
        cmp     byte [esi], 'C'
        je      .skip
        mov     dword [ebx + sect - $$], SECT_KEYBOARD
        cmp     byte [esi], 'K'
        je      .skip
        mov     dword [ebx + sect - $$], SECT_NONE
        jmp     .skip
.setting:
        cmp     dword [ebx + sect - $$], SECT_NONE
        je      .skip
        cmp     ecx, 8
        jne     .action
        cmp     dword [esi], 'Dead'
        jne     .action
        cmp     dword [esi + 4], 'zone'
        jne     .action
        cmp     dword [ebx + sect - $$], SECT_CONTROLLER
        jne     .skip
        mov     esi, edi
        call    value                   ; esi = the value's token
        jz      .skip
        call    number
        call    percent
        mov     edx, [ebx + sectplayer - $$]
        mov     [ebx + tables - $$ + W_DZ + edx * 4], eax
        jmp     .skip
.action:
        lea     edx, [ebx + tables - $$ + T_ACTNAMES]
        push    ACTIONS
        call    findname
        js      .skip
        push    eax                     ; the action
        mov     esi, edi
        call    value
        jz      .drop
        cmp     dword [ebx + sect - $$], SECT_CONTROLLER
        je      .padvalue
        lea     edx, [ebx + tables - $$ + T_KEYNAMES]
        push    256
        call    findname
        js      .drop
        pop     edx                     ; the action
        call    entry
        mov     [esi], ax
        jmp     .skip
.padvalue:
        mov     eax, NO_PAD
        cmp     ecx, 1                  ; "-": no pad
        jne     .padname
        cmp     byte [esi], '-'
        je      .haspad
.padname:
        lea     edx, [ebx + tables - $$ + T_PADNAMES]
        push    32
        call    findname
        js      .drop
.haspad:
        pop     edx
        call    entry
        mov     [esi + 2], ax
        jmp     .skip
.drop:  add     esp, 4
.skip:  mov     esi, edi                ; to the end of the line
.eol:   mov     al, [esi]
        test    al, al
        jz      .end
        inc     esi
        cmp     al, 10
        jne     .eol
        jmp     .line
.end:   ret

; edx = an action: esi = its table entry for the section's player. eax kept.
entry:
        push    eax
        mov     esi, [ebx + sectplayer - $$]
        imul    esi, esi, ACTIONS * 4
        lea     esi, [esi + edx * 4]
        lea     esi, [ebx + tables - $$ + W_TABLE + esi]
        pop     eax
        ret

; esi = text after a name: the value's token, past an "=" if there is
; one, as token returns it.
value:
        call    token
        jz      .done
        cmp     ecx, 1
        jne     .done
        cmp     byte [esi], '='
        jne     .done
        mov     esi, edi
        call    token
.done:  ret

; eax = a percentage: eax = it in 0..FULL, at most DEADZONE_MAX.
percent:
        imul    eax, eax, 100
        cmp     eax, DEADZONE_MAX
        jbe     .ok
        mov     eax, DEADZONE_MAX
.ok:    ret

; esi = text: skips spaces and returns esi = the token, ecx = its length
; (zero flag set when the line or text ends first), edi = just past it.
token:
        xor     ecx, ecx
.space: mov     al, [esi]
        cmp     al, ' '
        je      .next
        cmp     al, 9
        je      .next
        cmp     al, 13
        jne     .start
.next:  inc     esi
        jmp     .space
.start: mov     edi, esi
.char:  mov     al, [edi]
        test    al, al
        jz      .done
        cmp     al, ' '
        jbe     .done                   ; space, tab, CR, LF
        inc     edi
        inc     ecx
        jmp     .char
.done:  test    ecx, ecx
        ret

; esi = a token of ecx bytes, edx = a table of NAME-byte names, [esp+4]
; how many: eax = its index, or negative. The count is popped.
findname:
        push    esi
        push    edi
        push    ecx
        mov     edi, edx
        xor     eax, eax
.name:  push    esi
        push    edi
        push    ecx
.cmp:   mov     dl, [esi]
        cmp     dl, [edi]
        jne     .miss
        inc     esi
        inc     edi
        dec     ecx
        jnz     .cmp
        cmp     byte [edi], 0           ; the name ends where the token does
        jne     .miss
        pop     ecx
        pop     edi
        pop     esi
        jmp     .found
.miss:  pop     ecx
        pop     edi
        pop     esi
        add     edi, NAME
        inc     eax
        cmp     eax, [esp + 0x10]
        jb      .name
        or      eax, -1
.found: pop     ecx
        pop     edi
        pop     esi
        ret     4

; esi = text: eax = the unsigned decimal at it, esi past it; spaces skipped.
number:
        xor     eax, eax
.space: cmp     byte [esi], ' '
        jne     .digit
        inc     esi
        jmp     .space
.digit: movzx   edx, byte [esi]
        sub     edx, '0'
        cmp     edx, 9
        ja      .done
        imul    eax, eax, 10
        add     eax, edx
        inc     esi
        jmp     .digit
.done:  ret

; The table as text at W_TEXT, into the file, which is then cut there.
write_text:
        pushad
        call    resolve
        lea     edi, [ebx + tables - $$ + W_TEXT]
        lea     esi, [ebx + heading - $$]
        call    puts
        xor     ebp, ebp                ; the player
.player:
        mov     dword [ebx + sect - $$], SECT_CONTROLLER
.sect:  mov     al, 10
        stosb
        mov     al, '['
        stosb
        lea     eax, [ebp + '1']
        stosb
        mov     al, 'P'
        stosb
        mov     al, ' '
        stosb
        lea     esi, [ebx + controller - $$]
        cmp     dword [ebx + sect - $$], SECT_CONTROLLER
        je      .title
        lea     esi, [ebx + keyboard - $$]
.title: call    puts
        mov     al, ']'
        stosb
        mov     al, 10
        stosb
        cmp     dword [ebx + sect - $$], SECT_CONTROLLER
        jne     .actions
        lea     esi, [ebx + deadzone_name - $$]
        call    puts
        mov     eax, [ebx + tables - $$ + W_DZ + ebp * 4]
        call    putpercent
        mov     al, 10
        stosb
.actions:
        xor     edx, edx                ; the place in the order
.action:
        movzx   eax, byte [ebx + tables - $$ + T_ORDER + edx]
        cmp     eax, 0xff               ; the end of the order
        je      .sectend
        push    eax
        shl     eax, 4
        lea     esi, [ebx + tables - $$ + T_ACTNAMES + eax]
        call    puts
        lea     esi, [ebx + equals - $$]
        call    puts
        pop     eax
        imul    esi, ebp, ACTIONS * 4
        lea     esi, [esi + eax * 4]
        lea     esi, [ebx + tables - $$ + W_TABLE + esi]
        cmp     dword [ebx + sect - $$], SECT_CONTROLLER
        jne     .keyname
        movzx   eax, word [esi + 2]
        cmp     eax, NO_PAD
        jne     .padname
        mov     al, '-'
        stosb
        jmp     .lineend
.padname:
        shl     eax, 4
        lea     esi, [ebx + tables - $$ + T_PADNAMES + eax]
        call    puts
        jmp     .lineend
.keyname:
        movzx   eax, word [esi]
        shl     eax, 4
        lea     esi, [ebx + tables - $$ + T_KEYNAMES + eax]
        call    puts
.lineend:
        mov     al, 10
        stosb
        inc     edx
        jmp     .action
.sectend:
        dec     dword [ebx + sect - $$]      ; the keyboard section next
        jns     .sect
        inc     ebp
        cmp     ebp, 2
        jb      .player
        lea     esi, [ebx + tables - $$ + W_TEXT]
        sub     edi, esi                ; the length
        push    OPEN_ALWAYS
        push    GENERIC_READ | GENERIC_WRITE
        call    open_cfg
        cmp     eax, INVALID_HANDLE
        je      .out
        mov     ebp, eax
        push    0
        lea     ecx, [ebx + got - $$]
        push    ecx
        push    edi
        push    esi
        push    ebp
        call    [ebx + fn_writefile - $$]
        push    ebp
        call    [ebx + fn_setendoffile - $$]
        push    ebp
        call    [ebx + fn_closehandle - $$]
.out:   popad
        ret

; esi = a string: appended at edi.
puts:
        lodsb
        test    al, al
        jz      .done
        stosb
        jmp     puts
.done:  ret

; eax = 0..FULL: " nn" appended at edi.
putpercent:
        push    ecx
        push    edx
        mov     ecx, 100
        xor     edx, edx
        div     ecx
        mov     dl, ' '
        mov     [edi], dl
        inc     edi
        mov     ecx, 10
        xor     edx, edx
        div     ecx
        test    eax, eax
        jz      .units
        add     al, '0'
        stosb
.units: mov     al, dl
        add     al, '0'
        stosb
        pop     edx
        pop     ecx
        ret

heading:        db '; SEGA RALLY 2 controls', 10, 0
controller:     db 'Controller', 0
keyboard:       db 'Keyboard', 0
deadzone_name:  db 'Deadzone =', 0
equals:         db ' = ', 0

; open_cfg(access, disposition): SR2.CFG beside the exe, positioned at the
; tail. eax = the handle, or INVALID_HANDLE.
open_cfg:
        push    esi
        push    edi
        lea     edi, [ebx + path - $$]
        push    MAX_PATH
        push    edi
        push    0
        call    [ebx + fn_getmodfn - $$]
        mov     esi, edi                ; the name after the last backslash
.scan:  mov     al, [edi]
        test    al, al
        jz      .name
        inc     edi
        cmp     al, '\'
        jne     .scan
        mov     esi, edi
        jmp     .scan
.name:  mov     dword [esi], 'SR2.'
        mov     dword [esi + 4], 'CFG'
        push    0
        push    0x80                    ; FILE_ATTRIBUTE_NORMAL
        push    dword [esp + 0x18]      ; disposition
        push    0
        push    3                       ; FILE_SHARE_READ | FILE_SHARE_WRITE
        push    dword [esp + 0x20]      ; access
        lea     eax, [ebx + path - $$]
        push    eax
        call    [ebx + fn_createfile - $$]
        cmp     eax, INVALID_HANDLE
        je      .out
        push    eax
        push    0                       ; FILE_BEGIN
        push    0
        push    CFG_STOCK
        push    eax
        call    [ebx + fn_setfp - $$]
        pop     eax
.out:   pop     edi
        pop     esi
        ret     8

; ---- the pads --------------------------------------------------------

; The config's update: the player's pad is refreshed before its records
; poll, the race gate read; then the site's own first six bytes.
update:
        pushad
        call    getbase
        lea     eax, [ebx + MAGIC_UPDATE]
        mov     [esp + 0x1c], eax       ; popad's eax
        mov     eax, [esp + 0x24]       ; this, the config
        movzx   esi, byte [eax + 0xc]   ; its name, "0" or "1"
        sub     esi, '0'
        cmp     esi, 1
        ja      .skip
        test    esi, esi
        jnz     .pad
        mov     eax, [MAGIC_CARS]       ; the first car, if a race is set up; read once a frame
        mov     [ebx + inrace - $$], eax
.pad:   call    refresh
.skip:  popad
replay_update:                          ; the site's six displaced bytes, from the patcher
        times 6 db 0xc1
        jmp     eax

; esi = player: the tick's XINPUT_STATE for the pad this side holds, taking
; a free one when it holds none, one look every RETRY_FRAMES.
refresh:
        call    resolve
        mov     eax, [ebx + fn_xinput - $$]
        cmp     eax, 1
        jbe     .none                   ; no XInput on this machine
        movzx   ecx, byte [ebx + padidx - $$ + esi]
        test    ecx, ecx
        jz      .look
        dec     ecx
        call    getstate
        test    eax, eax
        jz      .done
        mov     byte [ebx + padidx - $$ + esi], 0       ; unplugged
        mov     byte [ebx + padretry - $$ + esi], RETRY_FRAMES
        jmp     .none
.look:  dec     byte [ebx + padretry - $$ + esi]
        jns     .none
        mov     byte [ebx + padretry - $$ + esi], RETRY_FRAMES
        xor     ecx, ecx
.slot:  lea     eax, [ecx + 1]
        lea     edx, [esi - 1]
        neg     edx                     ; the other side
        cmp     al, [ebx + edx + padidx - $$]
        je      .next
        call    getstate
        test    eax, eax
        jnz     .next
        lea     eax, [ecx + 1]
        mov     [ebx + padidx - $$ + esi], al
        jmp     .done
.next:  inc     ecx
        cmp     ecx, PADS
        jb      .slot
.none:  lea     edi, [ebx + state - $$ + 4]     ; nothing held: the gamepad part cleared
        imul    eax, esi, STATE_SIZE
        add     edi, eax
        xor     eax, eax
        mov     [edi], eax
        mov     [edi + 4], eax
        mov     [edi + 8], eax
.done:  ret

; XInputGetState(ecx, the side's state); eax = its result, ecx kept.
getstate:
        push    ecx
        imul    eax, esi, STATE_SIZE
        lea     eax, [ebx + state - $$ + eax]
        push    eax
        push    ecx
        call    [ebx + fn_xinput - $$]
        pop     ecx
        ret

; The European build's device poll, (this, source, &value, &range): a
; source of the annex's is answered, anything else goes back to the site
; with its displaced bytes replayed. The keyboard device's type byte is
; at +0x260 (3), its key array at +0x308.
poll:
        push    ebx
        push    esi
        push    edi
        call    getbase
        mov     eax, [esp + 0x10]       ; this
        xor     edx, edx
        cmp     byte [eax + 0x260], 3
        jne     .keys
        mov     edx, [eax + 0x308]
.keys:  mov     ecx, [esp + 0x14]       ; source
        call    answer
        jnc     .stock
        mov     ecx, [esp + 0x1c]       ; &range
        test    ecx, ecx
        jz      .norange
        mov     [ecx], edx
.norange:
        mov     ecx, [esp + 0x18]       ; &value
        test    ecx, ecx
        jz      .novalue
        mov     [ecx], eax
.novalue:
        xor     eax, eax
        pop     edi
        pop     esi
        pop     ebx
        ret     0x10
.stock: lea     edx, [ebx + MAGIC_POLL]
        pop     edi
        pop     esi
        pop     ebx
replay_poll:                            ; the site's nine displaced bytes, from the patcher; they leave edx alone
        times 9 db 0xc2
        jmp     edx

; The Australian build's keyboard poll, (descriptor, keys, source,
; &value, &range), the descriptor's type byte at +8: a source of the
; annex's is answered, anything else handed on to the stock poll, whose
; `ret 0x14` returns to the caller.
pollau:
        push    ebx
        push    esi
        push    edi
        call    getbase
        mov     eax, [esp + 0x10]       ; the descriptor
        xor     edx, edx
        cmp     byte [eax + 8], 3
        jne     .keys
        mov     edx, [esp + 0x14]       ; keys
.keys:  mov     ecx, [esp + 0x18]       ; source
        call    answer
        jnc     .stock
        mov     ecx, [esp + 0x20]       ; &range
        test    ecx, ecx
        jz      .norange
        mov     [ecx], edx
.norange:
        mov     ecx, [esp + 0x1c]       ; &value
        test    ecx, ecx
        jz      .novalue
        mov     [ecx], eax
.novalue:
        xor     eax, eax
        pop     edi
        pop     esi
        pop     ebx
        ret     0x14
.stock: lea     eax, [ebx + MAGIC_KBDPOLL]
        pop     edi
        pop     esi
        pop     ebx
        jmp     eax

; The page's poll, (source, &value, &range): the annex's sources with no
; keyboard behind them, so a menu key reads 0.
pollpage:
        push    ebx
        push    esi
        push    edi
        call    getbase
        mov     ecx, [esp + 0x10]       ; source
        xor     edx, edx
        call    answer
        jc      .ours
        xor     eax, eax
        mov     edx, KEY_DOWN
.ours:  mov     ecx, [esp + 0x18]       ; &range
        test    ecx, ecx
        jz      .norange
        mov     [ecx], edx
.norange:
        mov     ecx, [esp + 0x14]       ; &value
        test    ecx, ecx
        jz      .novalue
        mov     [ecx], eax
.novalue:
        xor     eax, eax
        pop     edi
        pop     esi
        pop     ebx
        ret     0xc

; ecx = a source id, edx = the keyboard's key array, or 0 on another
; device, ebx = the blob: carry set with eax = the value and edx = its
; range when the source is the annex's, clear otherwise. esi, edi used.
answer:
        sub     ecx, 0x300
        cmp     ecx, 0x80
        jb      .pad
        sub     ecx, MENUKEY_BASE - 0x300
        cmp     ecx, 0x100
        jb      .menukey
        clc
        ret
.menukey:                               ; ecx = the scancode: down, on the keyboard, outside a race
        xor     eax, eax
        test    edx, edx
        jz      .keyvalue
        cmp     dword [ebx + inrace - $$], 0
        jne     .keyvalue
        cmp     byte [edx + ecx], 0
        je      .keyvalue
        mov     eax, KEY_DOWN
.keyvalue:
        mov     edx, KEY_DOWN
        stc
        ret
.pad:   mov     esi, ecx
        shr     esi, 6                  ; the side
        and     ecx, 0x3f               ; the input
        cmp     ecx, IN_DEADZONE
        je      .value
        test    ecx, MENU_ONLY
        jz      .value
        and     ecx, ~MENU_ONLY
        cmp     dword [ebx + inrace - $$], 0
        je      .value
        xor     eax, eax                ; a menu-only input during a race
        mov     edx, KEY_DOWN
        stc
        ret
.value: call    padvalue
        stc
        ret

; esi = side, ecx = input: eax = its value, edx = the value's range.
;   0-15    the buttons in XINPUT_GAMEPAD order: D-pad up, down, left,
;           right, Start, Back, LS, RS, LB, RB, (two unused), A, B, X, Y
;   16, 17  LT, RT
;   18-21   left stick left, right, up, down
;   22-25   right stick likewise
;   0x3f    the side's deadzone
padvalue:
        imul    edi, esi, STATE_SIZE
        lea     edi, [ebx + state - $$ + edi]
        cmp     ecx, IN_DEADZONE
        je      .deadzone
        cmp     ecx, 16
        jae     .analog
        movzx   eax, word [edi + 4]     ; wButtons
        bt      eax, ecx
        mov     eax, 0
        jnc     .digital
        mov     eax, KEY_DOWN
.digital:
        mov     edx, KEY_DOWN
        ret
.analog:
        sub     ecx, 16
        cmp     ecx, 2
        jae     .stick
        movzx   eax, byte [edi + 6 + ecx]       ; bLeftTrigger, bRightTrigger
        cmp     eax, TRIGGER_MIN
        jae     .trigger
        xor     eax, eax
.trigger:
        mov     edx, 255
        ret
.stick: sub     ecx, 2
        cmp     ecx, 8
        jae     .nothing
        movzx   edx, byte [ebx + dirtab - $$ + ecx * 2]
        movsx   eax, word [edi + edx]
        cmp     byte [ebx + dirtab - $$ + 1 + ecx * 2], 0
        jne     .signed
        neg     eax
.signed:
        test    eax, eax
        jg      .deflected
        xor     eax, eax
        mov     edx, FULL
        ret
.deflected:                             ; scaled past the deadzone to 0..FULL
        push    eax
        mov     eax, [ebx + tables - $$ + W_DZ + esi * 4]
        imul    eax, eax, STICK_MAX
        mov     ecx, FULL
        xor     edx, edx
        div     ecx                     ; eax = the deadzone in stick units
        mov     ecx, eax
        pop     eax
        sub     eax, ecx
        jg      .past
        xor     eax, eax
        mov     edx, FULL
        ret
.past:  imul    eax, eax, FULL
        neg     ecx
        add     ecx, STICK_MAX
        xor     edx, edx
        div     ecx
        cmp     eax, FULL
        jbe     .capped
        mov     eax, FULL
.capped:
        mov     edx, FULL
        ret
.deadzone:
        mov     eax, [ebx + tables - $$ + W_DZ + esi * 4]
        mov     edx, FULL
        ret
.nothing:
        xor     eax, eax
        mov     edx, FULL
        ret

; ---- imports ---------------------------------------------------------

; Once: kernel32's file routines by name, and XInputGetState from the
; first of three DLLs present. Registers kept.
resolve:
        cmp     dword [ebx + resolved - $$], 0
        jne     .done
        pushad
        mov     dword [ebx + resolved - $$], 1
        lea     eax, [ebx + kernel32 - $$]
        push    eax
        call    [ebx + MAGIC_LOADLIB]
        mov     esi, eax
        lea     edi, [ebx + fn_createfile - $$]
        lea     ebp, [ebx + names - $$]
.name:  push    ebp
        push    esi
        call    [ebx + MAGIC_GETPROC]
        stosd
.skip:  inc     ebp
        cmp     byte [ebp - 1], 0
        jne     .skip
        cmp     byte [ebp], 0
        jne     .name
        lea     ebp, [ebx + xinputdlls - $$]
.dll:   push    ebp
        call    [ebx + MAGIC_LOADLIB]
        test    eax, eax
        jz      .nextdll
        lea     ecx, [ebx + procname - $$]
        push    ecx
        push    eax
        call    [ebx + MAGIC_GETPROC]
        test    eax, eax
        jnz     .found
.nextdll:
        inc     ebp
        cmp     byte [ebp - 1], 0
        jne     .nextdll
        cmp     byte [ebp], 0
        jne     .dll
        mov     eax, 1                  ; none: tried and failed
.found: mov     [ebx + fn_xinput - $$], eax
        popad
.done:  ret

kernel32:   db 'kernel32.dll', 0
names:      db 'CreateFileA', 0, 'ReadFile', 0, 'WriteFile', 0
            db 'SetFilePointer', 0, 'CloseHandle', 0, 'GetModuleFileNameA', 0, 'SetEndOfFile', 0, 0
xinputdlls: db 'xinput1_4.dll', 0, 'xinput1_3.dll', 0, 'xinput9_1_0.dll', 0, 0
procname:   db 'XInputGetState', 0

; stick directions: the axis's offset in XINPUT_STATE, and 1 for its
; positive half
dirtab:     db 8, 0, 8, 1, 10, 1, 10, 0, 12, 0, 12, 1, 14, 1, 14, 0

        align 4
resolved:   dd 0
fn_createfile:  dd 0                    ; in the order of names
fn_readfile:    dd 0
fn_writefile:   dd 0
fn_setfp:       dd 0
fn_closehandle: dd 0
fn_getmodfn:    dd 0
fn_setendoffile: dd 0
fn_xinput:      dd 0                    ; XInputGetState; 1 once looked for and missing
tableok:    dd 0                        ; the table read this session
inrace:     dd 0                        ; the first car as of this frame, 0 outside a race
sect:       dd 0                        ; the parser's and writer's section, SECT_*
sectplayer: dd 0                        ; its player
got:        dd 0
padidx:     db 0, 0                     ; each side's pad, XInput slot + 1; 0 none
padretry:   db 0, 0
state:      times 2 * STATE_SIZE db 0
path:       times MAX_PATH db 0


        align 4
tables:                                 ; the patcher's name tables and defaults, then the working area, W_END bytes in all
