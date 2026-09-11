; devices.asm - the Device Settings page in Options.dll.
;
; Two entries in the top-level state table the patcher moves into
; .sr2d, reached with esi = the Options object as every case there is:
;
;   +0  init   state 0xc: binds the page's UV table to the loaded sheets
;              - once per load of the DLL, since the binding replaces
;              each entry's sheet index with its handle in place - starts
;              the slide-in, steps to 0xd and falls into exec.
;   +5  exec   state 0xd: draws every sprite of the page's list, slid in
;              from the right by 40 px a frame as the stock pages are,
;              then, once in place, on cancel plays the back sound and
;              slides the page out the way it came, and only then puts
;              the menu's state back. Leaves through the dispatcher's
;              epilogue.
;
; The sprites, their quads and UV entries and the draw list are data the
; patcher builds after this code; the list is (sprite, x, y) with a null
; sprite at the end. The DLL is relocated on every load: the blob finds
; its own address with a call/pop and subtracts its RVA to get the image
; base, and every DLL address here is an RVA from that, filled in from
; the build's row.

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
%define MAGIC_DRAWLIST  0xDADADADA      ; the (sprite, x, y) list

%define STATE           8               ; the Options object's state
%define BACK_SOUND      0xe
%define KEY_CANCEL      2
%define SLIDE_FROM      0x44200000      ; 640.0
%define SLIDE_STEP      0x42200000      ; 40.0

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
.sprite:
        mov     eax, [edi]
        test    eax, eax
        jz      .slide
        push    0                       ; the sprite call's sixteen dwords
        push    0
        push    0
        push    0x100                   ; colour, 256 = as drawn
        push    0x100
        push    0x100
        push    0x100
        push    0x3f800000              ; scale 1.0, 1.0
        push    0x3f800000
        push    0
        push    0
        push    0
        push    0x41400000              ; z 12.0, the menu's
        push    dword [edi + 8]         ; y
        push    eax                     ; x, slid: the sprite's plus the offset
        fld     dword [edi + 4]
        fadd    dword [ebp + slide - $$]
        fstp    dword [esp]
        push    eax                     ; the sprite
        lea     eax, [ebx + MAGIC_DRAW]
        call    eax
        add     esp, 0x40
        add     edi, 12
        jmp     .sprite
.slide:
        cmp     dword [ebp + leaving - $$], 0
        jne     .leave
        mov     eax, [ebp + slide - $$]
        test    eax, eax
        jz      .input
        fld     dword [ebp + slide - $$]
        fsub    dword [ebp + step - $$]
        fstp    dword [ebp + slide - $$]
        mov     eax, [ebp + slide - $$]
        test    eax, eax                ; below zero, the sign bit
        jns     .out
        mov     dword [ebp + slide - $$], 0
        jmp     .out
.leave:                                 ; out to the right, then the menu
        fld     dword [ebp + slide - $$]
        fadd    dword [ebp + step - $$]
        fstp    dword [ebp + slide - $$]
        cmp     dword [ebp + slide - $$], SLIDE_FROM
        jb      .out
        mov     dword [esi + STATE], 1  ; the menu, cursor where it was
        jmp     .out
.input:
        mov     eax, [ebx + MAGIC_INPUT]
        mov     ecx, [eax + 8]
        test    ecx, ecx
        jz      .out
        mov     edx, [ecx]
        push    1
        call    [edx + 0x14]            ; the frame's key bits
        test    al, KEY_CANCEL
        jz      .out
        mov     ecx, [ebx + MAGIC_SOUNDOBJ]
        push    0
        push    0
        push    0
        push    BACK_SOUND
        lea     eax, [ebx + MAGIC_PLAYSOUND]
        call    eax
        mov     dword [ebp + leaving - $$], 1
.out:
        lea     eax, [ebx + MAGIC_EPILOGUE]
        pop     ebp
        pop     edi
        pop     ebx
        jmp     eax

bound:  dd      0                       ; the UV table bound this load
slide:  dd      0                       ; the slide's x offset, 640.0 down to 0 and back
step:   dd      SLIDE_STEP
leaving: dd     0                       ; sliding out after cancel
