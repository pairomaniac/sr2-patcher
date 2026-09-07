; restore.asm - MGameD3D's restore-surfaces routine, redone as
; IDirectDraw4::RestoreAllSurfaces.
;
; The routine at 0x10007710 (interface slot 16) restores the primary, the
; back buffer and the Z-buffer, and nothing else. The textures are
; DirectDraw surfaces too and stay lost, so the game comes back from a
; switch away with its geometry and no textures. RestoreAllSurfaces on the
; IDirectDraw4 at 0x1001254c restores every surface the object created.
;
; Written over the original routine, so it has the same shape: stdcall
; with one argument (this), the HRESULT returned and stored at the DLL's
; last-error slot. The DLL is relocated at load, so this reads its two
; globals relative to itself and needs no relocation entries; the ten the
; original had are dropped by the patcher.

bits 32
org 0x10007710

%define DDRAW4      0x1001254c
%define LASTERR     0x10011fc4
%define RESTOREALL  0x64                ; IDirectDraw4 slot 25

        call    .here
.here:  pop     ecx
        mov     eax, [ecx + DDRAW4 - .here]
        test    eax, eax
        jz      .none
        mov     edx, [eax]
        push    ecx
        push    eax
        call    [edx + RESTOREALL]
        pop     ecx
        mov     [ecx + LASTERR - .here], eax
        ret     4
.none:
        xor     eax, eax
        mov     [ecx + LASTERR - .here], eax
        ret     4
