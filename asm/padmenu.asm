; padmenu.asm - the pad on the multiplayer screens, straight from MGInput's
; annex.
;
; The multiplayer controller polls the pad every frame at 0x43f8e0: the
; input wrapper's button mask packed into a level word, an edge word
; made from it and the previous level (0x43f94b: `not edx; and edx,
; ecx`), and the three stored (0x43f94f, 0x4ef7c4 / 0x4ef7e4 /
; 0x4ef7d4). Its screens test the edge word for
; up, down, left, right (bits 0-3), confirm (4), cancel (5) and Enter
; (15), and the keyboard's own word (0x4d5e08, from WM_KEYDOWN) for the
; same, for TAB (bit 13), which alone opens the team room's MENU row,
; and for any key (bit 31), which closes the room's stat card (NOTES.md,
; *The menus' directions*). In the team room the wrapper's mask carries
; nothing from an XInput pad, and the poll's own repeat of a held
; direction runs at the keyboard's rate, two frames a step.
;
; This replaces the six-byte store of the level word with a call that
; asks the annex for side 0's D-pad, left stick, A, B, Start and Back
; through the poll it publishes (PADPOLL, null without the xinput
; patch). The buttons go into the level as their bits, the wrapper's
; directions come out of it, and the pad's directions go the keyboard's
; way instead: into the keyboard word as bits 0-3, on a change and then
; every PERIOD frames after DELAY frames held, the walk WM_KEYDOWN's
; repeat gives a key. A bit there waits for the task that reads and
; clears the word, so no screen misses one, where the edge word is
; made and cleared by the frame. A press of Back sets TAB there, and
; any press its bit 31. The edge is made again against the stored
; previous level, since the level now carries the annex's bits, then
; the three stores, returning past the two that followed the site.
; With the slot empty the site's own edge in edx is stored as it is.
;
; Placeholders the patcher fills: the level, edge and previous words
; (PADLEVEL, PADEDGE, PADPREV), the keyboard word (MENUKEYS), the poll's
; slot (PADPOLL).

bits 32

%define PADLEVEL    0xB1B1B1B1          ; placeholders, EXE_MAGICS: the poll's level word
%define PADEDGE     0xCECECECE          ; its edge word
%define PADPREV     0xB2B2B2B2          ; its previous level
%define MENUKEYS    0xCFCFCFCF          ; the keyboard's menu word
%define PADPOLL     0xDFDFDFDF          ; the exe slot holding the annex's page poll
%define SOURCE      0x300               ; the annex's source ids: side 0's inputs
%define DIRS        0xf                 ; the level's direction bits
%define TAB         0x2000              ; bit 13
%define ANYKEY      0x80000000          ; bit 31
%define DELAY       30                  ; frames a direction is held before it walks
%define PERIOD      2                   ; frames a step then, the keyboard's
%define INPUTS      12                  ; the inputs asked for
%define SKIP        13                  ; the site's nop and the two six-byte stores after it, returned past

; ecx = the level packed so far, edx = the edge the site made from it
entry:  add     dword [esp], SKIP
        push    eax
        push    esi
        push    edi
        push    ebp
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob
        cmp     dword [PADPOLL], 0
        je      .store
        push    edx
        push    ecx
        xor     esi, esi                ; the annex's bits
        xor     edi, edi
.input: movzx   eax, byte [ebp + inputs + edi]
        add     eax, SOURCE
        call    paddown
        jnc     .next
        or      si, [ebp + masks + edi * 2]
.next:  inc     edi
        cmp     edi, INPUTS
        jb      .input
        pop     ecx
        pop     edx
        mov     eax, esi
        mov     edi, [ebp + down]
        mov     [ebp + down], esi       ; edi was down, esi is
        not     edi
        and     edi, esi                ; the presses
        jz      .held
        or      dword [MENUKEYS], ANYKEY
        test    edi, TAB
        jz      .held
        or      dword [MENUKEYS], TAB
.held:  and     ecx, ~DIRS              ; the directions: the pad's, the keyboard's way
        and     eax, DIRS
        cmp     eax, [ebp + dirs]
        mov     [ebp + dirs], eax
        jne     .change
        dec     dword [ebp + count]
        jg      .buttons
        mov     dword [ebp + count], PERIOD
        jmp     .pulse
.change:
        mov     dword [ebp + count], DELAY
.pulse: or      [MENUKEYS], eax
.buttons:
        and     esi, ~(DIRS | TAB)
        or      ecx, esi
        mov     edx, [PADPREV]
        not     edx
        and     edx, ecx                ; the edge again: down now, not before
.store: mov     [PADLEVEL], ecx
        mov     [PADEDGE], edx
        mov     [PADPREV], ecx
        pop     ebp
        pop     edi
        pop     esi
        pop     eax
        ret

%include "padpoll.inc"

; the inputs asked for, XINPUT_GAMEPAD order as the annex numbers them,
; and the bit each sets
inputs: db 0, 1, 2, 3, 20, 21, 18, 19, 12, 13, 4, 5
masks:  dw 1, 2, 4, 8, 1, 2, 4, 8, 0x10, 0x20, 0x8000, TAB
        align 4
down:   dd 0                            ; the bits down last frame
dirs:   dd 0                            ; the direction bits last frame
count:  dd 0                            ; frames until the held directions pulse again
