; padprompts.asm - a screen's key prompts as the pad's while a pad is the
; device last used.
;
; A screen DLL draws a prompt as a sprite of quads, each a rectangle
; over a UV entry in its .data, (texture, u0, v0, u1, v1), and the draw
; reads all of it every frame. The patcher writes the pad's lettering
; where a sheet is free; what has to change for the sprite to show it -
; the entries' boxes or which entry a quad names, and the quads' and the
; sprite's sizes where the lettering's differ - is a list of dwords.
;
; The DLL's Exec export (_RecordModeExec@4, _TitleExec@4,
; _AdvTelopExec@4, _GalleryModeExec@4, _OptionsModeExec@4) is pointed
; here. Each frame this asks MGInput's annex (PADPOLL, null without the
; xinput patch) whether a pad is the device last used, writes each dword of the
; table as the keyboard's value or the pad's, and goes on to the
; export's own routine. The table follows the code, from the patcher:
; (RVA, the keyboard's value, the pad's) a dword each, an RVA of 0 after
; the last. An RVA with bit 31 set names a dword whose two values are
; RVAs of dwords to copy: the texture handles the DLL's init wrote over
; its UV entries' sheet numbers, which the patcher cannot know.
;
; The DLL is relocated on every load: the image base is this blob's
; address less its RVA (MAGIC_SELFRVA, filled in by the patcher), the
; export's routine at MAGIC_EXEC from it. PADPOLL is an exe address,
; which does not move. Everything but eax, which a stdcall routine does
; not expect kept, comes back as it was.

bits 32

%define MAGIC_SELFRVA   0xE7E7E7E7      ; this blob's RVA, filled at apply time
%define MAGIC_EXEC      0xE6E6E6E6      ; RVA: the export's own routine
%define PADPOLL         0xDFDFDFDF      ; placeholder: the exe slot holding the annex's page poll
%define HELD            0x300 + 0x3e    ; the annex's source id: side 0 holds a pad and a pad was the device last used

entry:  pushad
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob
        mov     ebx, ebp
        sub     ebx, MAGIC_SELFRVA      ; ebx = the image base
        xor     edi, edi                ; the keyboard's column
        cmp     dword [PADPOLL], 0
        je      .set
        mov     eax, HELD
        call    paddown
        jnc     .set
        mov     edi, 4                  ; the pad's
.set:   lea     esi, [ebp + table]
.next:  lodsd                           ; a dword's RVA
        test    eax, eax
        jz      .done
        mov     edx, [esi + edi]
        jns     .store
        and     eax, 0x7fffffff         ; bit 31: the value is where to copy from
        mov     edx, [ebx + edx]
.store: mov     [ebx + eax], edx
        add     esi, 8
        jmp     .next
.done:  lea     eax, [ebx + MAGIC_EXEC]
        mov     [esp + 0x1c], eax       ; popad's eax
        popad
        jmp     eax

%include "padpoll.inc"

        align 4
table:                                  ; the patcher's rows, then a zero
