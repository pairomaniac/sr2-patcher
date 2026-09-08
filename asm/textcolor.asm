; textcolor.asm - SetTextColor with the Windows 95 reading of 0xffffffff.
;
; The multiplayer lobby draws its text with GDI onto DirectDraw surfaces
; and sets the colour with SetTextColor(dc, -1): ten sites in the exe push
; -1, meaning white. Windows 95 ignored the top byte of a COLORREF. NT
; and Wine read bit 24 as PALETTEINDEX, look up entry 0xffff in the DC's
; palette, fail, and fall back to entry 0 - black - which is also the
; colour key the strip is blitted with. The text is drawn and never seen.
;
; This goes in a section the patcher appends to the exe, and the ten
; sites are pointed here instead of the import slot: the eight
; `call [__imp__SetTextColor]` become `call` here, the two
; `mov esi, [__imp__SetTextColor]` become `mov esi` of this address.
; Same stdcall shape: mask the colour to its RGB bytes and continue into
; the import. Nothing else in the exe calls SetTextColor.
;
; The exe is never relocated, so the address is absolute.

bits 32

%define SETTEXTCOLOR    0x495028        ; the import slot

        and     dword [esp + 8], 0x00ffffff
        jmp     [SETTEXTCOLOR]
