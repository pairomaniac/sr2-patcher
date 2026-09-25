; status.asm - the team room's status line from the netplay DLL.
;
; On DIRECT IP the team room's init prints "IP Address : a.b.c.d" from
; gethostbyname (0x43604b to 0x43611c): the machine's own address,
; right on a LAN, nothing to a guest across a router. The DLL's network
; object has a slot of its own for the line (+0x38, Network_StatusLine:
; the local addresses and the public one a STUN server saw), and this
; puts it in front of the exe's: called in place of the `lea` that
; starts the exe's lookup, it asks the DLL for the line into the same
; buffer and, given one, continues at the draw; without a network
; object, an error, or an empty line, it redoes the `lea` and returns
; to the exe's own code.
;
; The exe is never relocated, so the addresses are absolute, filled
; from the build's row.

bits 32

%define NETOBJ          0xB9B9B9B9      ; 0x4eac0c, the exe's network object
%define DRAW            0xBABABABA      ; 0x43611c, the strip's draw, the line in the buffer
%define STATUSLINE      0x38            ; the network object's added slot
%define BUF             0x20            ; the line's buffer in the init's frame, 0x100 bytes
%define BUFLEN          0x100
%define WSADATA         0x220           ; what the displaced `lea eax, [esp + 0x220]` took

        mov     eax, [NETOBJ]
        test    eax, eax
        jz      .own
        lea     ecx, [esp + 4 + BUF]    ; past the return here
        push    BUFLEN
        push    ecx
        push    eax
        mov     edx, [eax]
        call    [edx + STATUSLINE]      ; stdcall: (this, buf, len)
        test    eax, eax
        jnz     .own
        cmp     byte [esp + 4 + BUF], 0
        je      .own
        pop     eax                     ; the return: on to the draw instead
        push    DRAW
        ret
.own:   lea     eax, [esp + 4 + WSADATA]
        ret
