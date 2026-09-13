; texrange.asm - the texture release with its index checked.
;
; MGameD3D releases texture N at 0x10004430: the pointer at [table + N*4],
; its Release, the slot cleared. Nothing checks N, and VendorLogo's End
; releases texture -128 (0x100014e0), which is the dword 512 bytes before
; the table: the tail of whatever the heap put there. Zero and nothing
; happens; a pointer and the game calls through it - which is what the
; heap's layout of the day decides, and why the stock crashed on Windows
; after the vendor logo with the borderless window and not without.
;
; The function's first ten bytes jump here; this does what they did after
; checking the index against the count at 0x10012590, as the create at
; 0x10003fa5 does, and returns for one out of range.
;
; The DLL is relocated on every load: the image base comes from this
; blob's own address less its RVA, filled in by the patcher.

bits 32

%define MAGIC_SELFRVA   0xE7E7E7E7      ; this blob's RVA, filled at apply time
%define TABLE           0x12580         ; RVAs in MGameD3D.dll
%define COUNT           0x12590
%define RESUME          0x443a          ; after the ten bytes replaced

        call    .here
.here:  pop     edx
        sub     edx, .here
        sub     edx, MAGIC_SELFRVA      ; edx = image base
        mov     ecx, [esp + 4]          ; the index
        cmp     ecx, [edx + COUNT]
        jae     .out
        mov     eax, [edx + TABLE]      ; the ten bytes: mov eax, [table]
        push    esi                     ;                push esi
        mov     esi, [esp + 8]          ;                mov esi, [esp+8]
        add     edx, RESUME
        jmp     edx
.out:
        xor     eax, eax
        ret     4
