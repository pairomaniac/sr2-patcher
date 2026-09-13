; replayfree.asm - the replay gallery frees only what it allocated.
;
; The replay data lives at +0x50 of the block the exe hands every screen.
; ReplayGallery.dll's End (0x100046c0) frees it, which is right when the
; gallery loaded it from a file (its own new at 0x10003b65) and wrong
; when it came from a race: MainMode.dll keeps the race's replay in its
; own .data and the exe passes that pointer on. Windows 9x's HeapFree
; refused the address and the game went on; the heap since Windows 8
; treats it as corruption and ends the process - the crash on returning
; to the menu after saving a replay.
;
; Two thunks, in a section the patcher appends to the DLL:
;
;   +0  alloc  called instead of the new at 0x10003b65; calls it and keeps
;              the block's address
;   +5  free   called instead of `push eax; call free` at 0x1000471f, so
;              it leaves the argument for the caller's `add esp, 4`; frees
;              eax only if it is the block alloc kept
;
; The DLL is relocated on every load: the image base is this blob's
; address less its RVA, filled in by the patcher; the CRT's new and free
; are at fixed RVAs from it.

bits 32

%define MAGIC_SELFRVA   0xE7E7E7E7      ; this blob's RVA, filled at apply time
%define CRT_NEW         0xbdeb          ; RVAs in ReplayGallery.dll: operator new(size), cdecl
%define CRT_FREE        0xbde0          ; free(p), cdecl

        jmp     near alloc              ; +0
        jmp     near free               ; +5

; cdecl, as the new it stands in for: the size at [esp+4], left there.
alloc:
        call    .here
.here:  pop     ecx
        sub     ecx, .here              ; ecx = this blob
        mov     edx, ecx
        sub     edx, MAGIC_SELFRVA      ; edx = the image base
        add     edx, CRT_NEW
        push    ecx
        push    dword [esp + 8]         ; the size
        call    edx
        add     esp, 4
        pop     ecx
        mov     [ecx + D_MINE], eax
        ret

; eax = the pointer. Returns with it pushed, as the replaced push left it.
free:
        pop     edx                     ; the return address
        push    eax
        push    edx
        call    .here
.here:  pop     ecx
        sub     ecx, .here
        cmp     eax, [ecx + D_MINE]
        jne     .keep
        mov     dword [ecx + D_MINE], 0
        mov     edx, ecx
        sub     edx, MAGIC_SELFRVA
        add     edx, CRT_FREE
        push    eax
        call    edx
        add     esp, 4
.keep:
        ret

D_MINE      dd 0                        ; the block the gallery allocated, if any
