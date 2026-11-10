; padpoll.inc - one input from MGInput's annex, through the page poll it
; publishes at an exe slot. The includer defines PADPOLL, the slot's
; placeholder, and checks the slot first: it is null without the xinput
; patch. Included by padmenu.asm, replaypad.asm, pagepad.asm,
; sortpad.asm and padprompts.asm.
;
; A source is 0x300 + side * 0x40 + input, the inputs numbered as the
; annex does: 0-15 the buttons in XINPUT_GAMEPAD order (D-pad up, down,
; left, right, Start, Back, LS, RS, LB, RB, -, -, A, B, X, Y), 16 and 17
; LT and RT, 18-21 the left stick's left, right, up and down, 22-25 the
; right stick's, 0x3e down while the side holds a pad and a pad was the
; device last used. The callers take
; an input as down when its value is past half its range.

; eax = a source: eax = its value, edx = its range. ebx, esi, edi and ebp
; kept.
padvalue:
        sub     esp, 8                  ; [esp] the value, [esp + 4] the range
        lea     ecx, [esp + 4]
        push    ecx                     ; &range
        lea     ecx, [esp + 4]
        push    ecx                     ; &value
        push    eax                     ; source
        call    [PADPOLL]               ; stdcall (source, &value, &range)
        pop     eax
        pop     edx
        ret

; eax = a source: carry set when it is down. ebx, esi, edi and ebp kept.
paddown:
        call    padvalue
        add     eax, eax
        cmp     edx, eax                ; below: the value past half the range
        ret
