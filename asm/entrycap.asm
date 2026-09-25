; entrycap.asm - the lobby's text entries capped at what their fields hold.
;
; One entry widget serves the lobby: its init (0x420f10) takes the
; surface, the place, the field the text starts from and comes back to,
; and the width shown, and its character handler accepts up to 0x800
; characters (0x41fef1, and again at 0x420849) whatever the field. The
; fields are far smaller - the address slot 16 bytes, the team name's
; 36, the chat line a message - and the exe copies the text into them
; with lstrcpy, so a long entry wrote over what follows. Two entries:
;
;   +0  init   called in place of the init's first two loads: the cap
;              for this field, by the field's address (and the width
;              shown, where two fields share a buffer), is kept here,
;              and the two loads redone past the return address.
;   +5  cap    called in place of `cmp eax, 0x800`: the same compare
;              against the kept cap. Flags survive the return.
;
; The exe is never relocated, so the fields' addresses are absolute,
; filled from the build's row; the blob's own is not known until it is
; appended, so it reaches its data from a call/pop base.

bits 32

%define IPSLOT          0xB6B6B6B6      ; 0x4eacec, the address in the connection settings
%define TEAMSLOT        0xB7B7B7B7      ; 0x4ead1c, the team name there
%define LINEBUF         0xB8B8B8B8      ; 0x4d3b1c, the chat line's and the driver name's start
%define DEFAULT         0x800           ; the stock cap
%define IPMAX           47              ; the address slot and the unused modem number's after it, less the NUL (asm/ipcheck.asm)
%define TEAMMAX         35              ; the team name's 36 bytes, less the NUL
%define CHATMAX         255             ; a chat line: well within the DLL's 1024-byte message
%define NAMEMAX         20              ; the driver name: what its OK accepts
%define CHATWIDTH       0x1a            ; the chat line's width shown; the driver name's is 0x12

        jmp     near init               ; +0
        jmp     near cap                ; +5

getbase:
        call    .here
.here:  pop     ebx
        sub     ebx, .here
        ret

; [esp] the return here, [esp+4] the init's own return, then its
; arguments: [esp+8] the surface, [esp+0xc] x, [esp+0x10] y, [esp+0x14]
; the field, [esp+0x18] the width.
init:
        push    ebx
        call    getbase
        mov     edx, [esp + 0x18]       ; the field, past the pushed ebx
        mov     eax, DEFAULT
        cmp     edx, IPSLOT
        jne     .team
        mov     eax, IPMAX
        jmp     .set
.team:  cmp     edx, TEAMSLOT
        jne     .line
        mov     eax, TEAMMAX
        jmp     .set
.line:  cmp     edx, LINEBUF
        jne     .set
        mov     eax, CHATMAX
        cmp     dword [esp + 0x1c], CHATWIDTH
        je      .set
        mov     eax, NAMEMAX
.set:   mov     [ebx + limit], eax
        pop     ebx
        mov     eax, [esp + 8]          ; the two loads displaced by the call, past the return here
        mov     ecx, [esp + 0xc]
        ret

; eax = the entry's length: compared with the cap, for the `jae` after
; the call. ebx kept; the flags are the compare's.
cap:
        push    ebx
        call    getbase
        cmp     eax, [ebx + limit]
        pop     ebx
        ret

limit:  dd DEFAULT
