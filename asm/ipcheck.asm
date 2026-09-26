; ipcheck.asm - the IP entry popup's OK refused for a blank or malformed
; address.
;
; The popup (0x43ca20) takes OK by comparing the entry's length with
; zero (0x43cb4e: blank meant a broadcast search) and copying the text
; to the connection settings with lstrcpy - into a 16-byte slot, from
; an entry that holds 2048. That compare becomes a call here. The text
; has to be an address the DLL will take - a dotted quad or a name,
; with an optional :port, of at most MAXLEN characters, which fill the
; slot and the unused modem number's after it - or the press is
; refused with the cancel sound
; and the popup stays: the stack is unwound to what the popup's own
; refusals push, and the sound call continued into.
;
; The exe is never relocated, so the addresses are absolute, filled
; from the build's row.

bits 32

%define EDITBUF         0xB3B3B3B3      ; 0x4d3d1c, the entry's text
%define EDITLEN         0xB4B4B4B4      ; 0x4d454c, its length
%define DENY            0xB5B5B5B5      ; 0x43cbac, the popup's sound call, its four arguments pushed
%define SOUND_CANCEL    0x1c
%define MAXLEN          47              ; the address slot's 16 bytes and the modem number's 32, less the NUL

        push    ebx
        push    esi
        push    edi
        push    ecx
        push    edx
        mov     esi, EDITBUF
        call    check
        pop     edx
        pop     ecx
        pop     edi
        pop     esi
        pop     ebx
        test    eax, eax
        jz      .deny
        cmp     dword [EDITLEN], 0      ; the displaced compare; esi is 0 at the site
        ret
.deny:  pop     eax                     ; the return: not going back
        push    0
        push    0
        push    0
        push    SOUND_CANCEL
        push    DENY
        ret

; esi = the text. eax = 1 for an address, 0 otherwise. ebx, ecx, edx,
; edi used.
check:
        xor     ecx, ecx                ; the length
        or      edx, -1                 ; the last colon, or none
.scan:  mov     al, [esi + ecx]
        test    al, al
        jz      .scanned
        cmp     al, ':'
        jne     .next
        mov     edx, ecx
.next:  inc     ecx
        jmp     .scan
.scanned:
        test    ecx, ecx
        jz      .bad
        cmp     ecx, MAXLEN
        ja      .bad
        mov     edi, ecx                ; the host's length
        cmp     edx, -1
        je      .host
        mov     edi, edx
        lea     ebx, [edx + 1]          ; the port: digits after the colon, 1 to 65535
        cmp     ebx, ecx
        jae     .bad
        xor     edx, edx
.port:  movzx   eax, byte [esi + ebx]
        sub     eax, '0'
        cmp     eax, 9
        ja      .bad
        imul    edx, 10
        add     edx, eax
        cmp     edx, 65535
        ja      .bad
        inc     ebx
        cmp     ebx, ecx
        jb      .port
        test    edx, edx
        jz      .bad
.host:  test    edi, edi                ; the host: letters, digits, dots and hyphens
        jz      .bad
        xor     ebx, ebx
        xor     edx, edx                ; a letter seen
.class: movzx   eax, byte [esi + ebx]
        cmp     al, '.'
        je      .ok
        cmp     al, '-'
        je      .ok
        sub     eax, '0'
        cmp     eax, 9
        jbe     .ok
        mov     al, [esi + ebx]
        or      al, 0x20
        sub     al, 'a'
        cmp     al, 'z' - 'a'
        ja      .bad
        inc     edx
.ok:    inc     ebx
        cmp     ebx, edi
        jb      .class
        test    edx, edx
        jnz     .good                   ; a name: the DLL looks it up
        xor     ebx, ebx                ; digits and dots only: a dotted quad
        xor     ecx, ecx                ; the groups ended
        or      edx, -1                 ; the group so far, or none
.quad:  movzx   eax, byte [esi + ebx]
        cmp     al, '.'
        jne     .digit
        cmp     edx, -1
        je      .bad                    ; an empty group
        inc     ecx
        or      edx, -1
        jmp     .more
.digit: sub     eax, '0'                ; a digit, or the hyphen the class pass let through
        cmp     eax, 9
        ja      .bad
        cmp     edx, -1
        jne     .accum
        xor     edx, edx
.accum: imul    edx, 10
        add     edx, eax
        cmp     edx, 255
        ja      .bad
.more:  inc     ebx
        cmp     ebx, edi
        jb      .quad
        cmp     edx, -1
        je      .bad                    ; a trailing dot
        cmp     ecx, 3
        jne     .bad
.good:  mov     eax, 1
        ret
.bad:   xor     eax, eax
        ret
