; replaypad.asm - the pad on the replay's camera controls, from MGInput's
; annex.
;
; The race's camera manager keeps an object of its own for the replay's
; controls (made at 0x411335, updated every frame at 0x440c30). Per
; player it builds a level word: bits 0-3 up, down, left, right, 0x10
; and 0x20 the meter on and off, 0x40 the screen or car switch, 0x80 and
; 0x100 the revolving camera's zoom (the manual's smooth in and out),
; and beside it the steering's analog x, -127..127. The keyboard fills
; it from fixed scancodes (0x440d20: the arrows, Insert, Delete, TAB,
; Page Up and Page Down; S, X, Z, C, T, G and TAB for player 2), and a
; DirectInput joystick only when the player's config had one at start,
; straight from its DIJOYSTATE (0x440e20: the axes, buttons 1 to 3).
; MGInput's actions are not asked, so an XInput pad, answered by the
; annex as source ids, never reaches it.
;
; The two loads at the join of both paths (0x440cea), where the edge is
; made from the level and the previous one, become a call here. It asks
; the annex's poll (PADPOLL, null without the xinput patch) for the
; player's bumpers, left stick, triggers, Y and X and ORs their bits
; into the level - RB and LB the next and previous camera, the left
; stick left and right, RT and LT the zoom, Y the meter, X the
; switch - puts the left stick's x into the analog when the keyboard
; left it at 0, then does the two loads.
;
; esi = the player's level word (the object + 0x20 + player * 4), edi =
; the player. Everything but edx and eax, which the loads set, and the
; flags comes back as it was.

bits 32

%define PADPOLL     0xDFDFDFDF          ; placeholder, EXE_MAGICS: the exe slot holding the annex's page poll
%define SOURCE      0x300               ; the annex's source ids: 0x300 + side * 0x40 + input
%define ANALOG      0x10                ; the player's analog x, from the level word
%define PREV        8                   ; the player's previous level, from the level word
%define FULL        10000               ; a stick half's range
%define LS_LEFT     18
%define LS_RIGHT    19
%define INPUTS      8                   ; the inputs asked for

entry:  pushad
        cmp     dword [PADPOLL], 0
        je      .done
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob
        shl     edi, 6
        add     edi, SOURCE             ; the player's side
        xor     ebx, ebx                ; the pad's bits
        xor     esi, esi
.input: movzx   eax, byte [ebp + inputs + esi]
        add     eax, edi
        call    paddown
        jnc     .next
        or      bx, [ebp + masks + esi * 2]
.next:  inc     esi
        cmp     esi, INPUTS
        jb      .input
        mov     esi, [esp + 4]          ; pushad's esi: the level word
        or      [esi], ebx
        cmp     dword [esi + ANALOG], 0
        jne     .done
        lea     eax, [edi + LS_RIGHT]
        call    padvalue
        push    eax
        lea     eax, [edi + LS_LEFT]
        call    padvalue
        pop     ecx
        sub     ecx, eax                ; right less left, -FULL..FULL
        imul    eax, ecx, 127
        cdq
        mov     ecx, FULL
        idiv    ecx
        mov     [esi + ANALOG], eax
.done:  popad
        mov     edx, [esi + PREV]       ; the site's two loads
        mov     eax, [esi]
        ret

%include "padpoll.inc"

; the inputs asked for, as the annex numbers them - RB, LB, the left
; stick's left and right, RT, LT, Y, X - and the bits each sets
inputs: db 9, 8, 18, 19, 17, 16, 15, 14
masks:  dw 1, 2, 4, 8, 0x80, 0x100, 0x30, 0x40
