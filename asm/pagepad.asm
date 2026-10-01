; pagepad.asm - the pad's bumpers as Page Up and Page Down, and X as the
; name entry's erase, from MGInput's annex.
;
; The input wrapper's update (0x47f2d0) builds each player's level word
; from a fixed table of actions, bit by bit; bits 7 and 8 have none, so
; only the keyboard's Page Up and Page Down (the wrapper's own scancode
; table, 0x47f5c0) set them. Two screens read them: the Records page
; turns on them (Record.dll, the level through the wrapper's +0x1c) and
; the car select takes a held Page Up as the alternative colour
; (MSelect.dll). Bit 3 has neither an action nor a key; the two name
; entries (exe 0x43368a and 0x43393c, MSelect.dll 0x1001c630 and
; 0x1001c980) take it, or bit 4, as erase.
;
; The six bytes after the table loop (0x47f506, `mov eax, [esp+0x10]` and
; a test of it; the Australian build's cmp against ebp, which is 0 there)
; become a call here. It asks the annex's poll (PADPOLL, null without
; the xinput patch) for the player's LB, RB and X, ORs them into the level
; as 0x80, 0x100 and 0x08, then does the load and the test; the flags go back
; to the site's branch.
;
; esi = the player's slot in the wrapper (+0xd4 + player * 4), its level
; at -0xa0; the player at [esp+0x18] of the caller. Everything but eax
; and the flags comes back as it was.

bits 32

%define PADPOLL     0xDFDFDFDF          ; placeholder, EXE_MAGICS: the exe slot holding the annex's page poll
%define SOURCE      0x300               ; the annex's source ids: 0x300 + side * 0x40 + input
%define LEVEL       -0xa0               ; the player's level word, from esi
%define PLAYER      0x20 + 4 + 0x18     ; the caller's player index, past pushad and the return
%define CONFIG      4 + 0x10            ; the caller's config, past the return
%define LB          8
%define RB          9
%define X           14

entry:  pushad
        cmp     dword [PADPOLL], 0
        je      .done
        mov     edi, [esp + PLAYER]
        shl     edi, 6
        add     edi, SOURCE             ; the player's side
        xor     ebx, ebx
        lea     eax, [edi + LB]
        call    paddown
        jnc     .rb
        or      ebx, 0x80
.rb:    lea     eax, [edi + RB]
        call    paddown
        jnc     .x
        or      ebx, 0x100
.x:     lea     eax, [edi + X]
        call    paddown
        jnc     .or
        or      ebx, 0x08
.or:    or      [esi + LEVEL], ebx
.done:  popad
        mov     eax, [esp + CONFIG]     ; the site's load and test
        test    eax, eax
        ret

%include "padpoll.inc"
