; activate.asm - restore the DirectDraw surfaces when the game regains focus.
;
; Switching away from an exclusive-mode DirectDraw game marks its surfaces
; lost, and every blit and flip fails until they are restored. MGameD3D has
; a routine for that - slot 16 of its interface, IsLost/Restore on the
; primary, the back buffer and the Z-buffer - and nothing in the game ever
; calls it: the window procedure's WM_ACTIVATEAPP case (0x426bc5) only
; pauses and resumes the sound object.
;
; This goes in a section the patcher appends to the exe, and the `call`
; that resumes the sound on activation (0x426bf7 -> 0x46e260) is pointed
; here instead. It restores the surfaces and then continues to the
; resume, with ecx - that routine's `this` - as it was.
;
; The exe is never relocated, so the addresses are absolute.

bits 32

%define GAMED3D     0x50b118            ; the MGameD3D interface pointer
%define RESTORE     0x40                ; its restore-surfaces slot
%define RESUME      0x46e260            ; what the call site called

        push    ecx
        mov     eax, [GAMED3D]
        test    eax, eax
        jz      .done
        mov     edx, [eax]
        push    eax
        call    [edx + RESTORE]
.done:
        pop     ecx
        push    RESUME
        ret
