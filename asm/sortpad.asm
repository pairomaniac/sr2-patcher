; sortpad.asm - the pad's LB and RB step the Replay Gallery's sort.
;
; The gallery's sort is the exe's: F6, F7 and F8 are accelerators in its
; resources (commands 40043-40045, VK_F6-F8), and the WM_COMMAND handler
; (0x428320) sets the mode - 0 MODE, 1 CAR, 2 DATE - at +4 of a block
; (0x4e6908) the gallery gets as its init block's +0x6c, turning the
; order over (+8) when the mode picked is the one already set. The list's
; browse state (0x1000271f) compares its own copy of both every frame and
; sorts again when they differ. No input the game reads is involved, so
; the pad is read here, where the sort is used.
;
; The two instructions after the list's row update (0x10002764, `mov ecx,
; [esi+0x50]; and edi, 0xff`) become a call here. It asks MGInput's annex
; (PADPOLL, null without the xinput patch) for side 0's LB and RB, keeps
; what was down, and on a press steps the mode left for LB and right for
; RB, round from DATE to MODE; the order stays as it was. Then the two
; instructions; the compare after them sees the new mode and the list
; sorts as it does for an F key.
;
; With no replay saved the list never reaches that state: it stays in the
; one that shows the empty notice (0x1000285c), where the F keys still
; move the sort box. The second entry is called from there, in place of
; `push 0; mov edi, eax; mov edx, [ecx]` (0x1000286a), and steps the mode
; the same way.
;
; The DLL is relocated on every load: the image base is this blob's
; address less its RVA (MAGIC_SELFRVA, filled in by the patcher), the
; sort block's global at a fixed RVA from it. PADPOLL is an exe address,
; which does not move. esi = the list, edi = its row update's result.
; Everything but what the site's own instructions set, and the flags,
; comes back as it was.

bits 32

%define MAGIC_SELFRVA   0xE7E7E7E7      ; this blob's RVA, filled at apply time
%define PADPOLL         0xDFDFDFDF      ; placeholder: the exe slot holding the annex's page poll
%define SORTBLOCK       0xbe620         ; RVA: the init block's +0x6c, the sort's block
%define LB              0x300 + 8       ; the annex's source ids, side 0
%define RB              0x300 + 9
%define MODES           3

        jmp     near browse             ; +0
        jmp     near empty              ; +5

browse: call    step
        mov     ecx, [esi + 0x50]       ; the site's two instructions
        and     edi, 0xff
        ret

empty:  call    step
        mov     edi, eax                ; the site's three: eax = the notice's result,
        mov     edx, [ecx]              ; ecx = the sort block
        pop     ecx                     ; the return address; the site loads ecx next
        push    0
        jmp     ecx

step:   pushad
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob
        cmp     dword [PADPOLL], 0
        je      .done
        xor     edi, edi                ; bit 0 LB, bit 1 RB
        mov     eax, LB
        call    paddown
        jnc     .rb
        or      edi, 1
.rb:    mov     eax, RB
        call    paddown
        jnc     .edge
        or      edi, 2
.edge:  mov     eax, [ebp + held]
        mov     [ebp + held], edi
        not     eax
        and     eax, edi                ; the presses
        jz      .done
        mov     ebx, ebp
        sub     ebx, MAGIC_SELFRVA      ; ebx = the image base
        mov     edx, [ebx + SORTBLOCK]
        test    edx, edx
        jz      .done
        mov     ecx, [edx + 4]          ; the mode
        test    eax, 1
        jz      .right
        dec     ecx
        jns     .store
        mov     ecx, MODES - 1
        jmp     .store
.right: inc     ecx
        cmp     ecx, MODES
        jb      .store
        xor     ecx, ecx
.store: mov     [edx + 4], ecx
.done:  popad
        ret

%include "padpoll.inc"

        align 4
held:   dd 0                            ; LB and RB down last frame
