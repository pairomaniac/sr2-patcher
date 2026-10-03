; tabmenu.asm - the team room's TAB MENU button as SEL MENU while player 1
; holds a pad.
;
; The team room's buttons are bitmaps the exe blits through MGameD3D's
; surface wrapper, not sprites, so padprompts.asm cannot switch them. Two
; things show TAB MENU. With the menu closed it is painted into the
; room's backdrop (ROOMBG, entry 0, from CHAT.BMP, loaded in the room
; object's constructor through the lobby's loader - BMPLOAD: context,
; directory, flag, name, &object, &size, 1; cdecl - and blitted whole
; onto the frame every draw) at (18, 454), 98 by 18. When TAB opens the
; menu, the exe registers a layer whose first draw loads thirty bitmaps
; from BINDATA\chat through the same loader into an array of surfaces
; (CHATOBJS), TAB_MENU_ON.BMP and TAB_MENU_ON2.BMP the fifth and sixth
; (TABOBJS), and calls each one's SetTarget (vtable +0x34) with the first
; object, then those two again with 0, the back buffer; the open menu's
; draws read the array; closing the menu frees the thirty (BMPFREE:
; object; cdecl). The room's destructor frees its surfaces without
; running that exit, so a room left with the menu open leaks the thirty.
;
; Five calls into this blob:
;
;   room (+15), in place of the constructor's call that loads the
;   backdrop: that call, then the patcher's TAB_MENU_BACK.BMP and
;   TAB_MENU_BACK_SEL.BMP, the backdrop's box as stock and as SEL, loaded
;   the same way.
;
;   init (+0), after the menu layer's two +0x34 calls on the TAB objects:
;   loads the patcher's TAB_MENU_SEL.BMP and TAB_MENU_SEL2.BMP, keeps the
;   stock pointers, and does the two +0x34 calls on the new objects. Then
;   the site's own load (ROOMFLAG).
;
;   frame (+10), in the multiplayer screens' pad poll, every frame: asks
;   MGInput's annex (PADPOLL, null without the xinput patch) whether side
;   0 holds a pad. While the menu's objects are loaded, writes the two
;   array entries as the pad's objects or the stock's. While the
;   backdrop's are, and the answer has changed, blits the matching one
;   onto the backdrop (SetTarget +0x34, Blit +0x1c: x, y, &source rect),
;   the target put back to the back buffer after. Then the site's own
;   load (POLLBASE).
;
;   free (+5), at the menu layer's release loop: puts the stock pointers
;   back in the array, frees the two objects and forgets them. Then the
;   site's own load of the array's address.
;
;   roomfree (+20), at the room destructor's release loop: the same for
;   the menu's objects if they are still loaded, then frees the
;   backdrop's two. Then the site's own load of the surface table's
;   address.
;
; Everything comes back as it was. The exe is not relocated, so the
; addresses are the build's, filled by the patcher.

bits 32

%define BMPLOAD     0xA1A1A1A1          ; placeholders, EXE_MAGICS: the chat bitmap loader (ROOMLOAD)
%define BMPFREE     0xA3A3A3A3          ; its release
%define BMPCTX      0xEDEDEDED          ; the dword holding the loader's context (HWND)
%define CHATOBJS    0xA5A5A5A5          ; the room's object array
%define TABOBJS     0xA6A6A6A6          ; its fifth entry: TAB MENU's object, TAB CHAT's after it
%define ROOMFLAG    0xA7A7A7A7          ; the init site's own load
%define POLLBASE    0xA8A8A8A8          ; the frame site's own load
%define ROOMBG      0xBBBBBBBB          ; the room's surface table, entry 0 the backdrop
%define PADPOLL     0xDFDFDFDF          ; the exe slot holding the annex's page poll
%define HELD        0x300 + 0x3e        ; the annex's source id: side 0 holds a pad
%define DIR         0xc                 ; BINDATA\chat
%define S_TARGET    0x34                ; the wrapper: SetTarget(this, surface or 0 for the back buffer)
%define S_BLIT      0x1c                ; Blit(this, x, y, &rect), the rect left, top, right, bottom
%define FILES       4                   ; the files: the two buttons, then the backdrop's box as stock and as SEL
%define ARGS        7                   ; the loader's arguments
%define BACK_X      18                  ; where the backdrop's TAB MENU sits
%define BACK_Y      454

entry:  jmp     strict near init        ; +0, five bytes each: the sites call +0, +5, +10, +15 and +20
        jmp     strict near free        ; +5
        jmp     strict near frame       ; +10
        jmp     strict near room        ; +15
        jmp     strict near roomfree    ; +20

; esi = a file's index: loaded through the exe's loader into objects[esi],
; its size into sizes[esi]. ebp = this blob. edi = &objects[esi] after.
load:   push    1
        lea     eax, [ebp + sizes + esi * 8]
        push    eax
        lea     edi, [ebp + objects + esi * 4]
        push    edi
        mov     eax, [ebp + names + esi * 4]
        add     eax, ebp                ; the name's address
        push    eax
        push    0
        push    DIR
        push    dword [BMPCTX]
        mov     eax, BMPLOAD
        call    eax
        add     esp, ARGS * 4
        ret

; esi = a file's index: its object freed and forgotten.
drop:   mov     eax, [ebp + objects + esi * 4]
        test    eax, eax
        jz      .none
        push    eax
        mov     eax, BMPFREE
        call    eax
        add     esp, 4
        mov     dword [ebp + objects + esi * 4], 0
.none:  ret

; the menu's two objects, when loaded: the stock pointers back in the array, the objects dropped.
menuoff:
        mov     eax, [ebp + stock]
        test    eax, eax
        jz      .none
        mov     ebx, TABOBJS
        mov     [ebx], eax
        mov     eax, [ebp + stock + 4]
        mov     [ebx + 4], eax
        xor     esi, esi
.one:   call    drop
        inc     esi
        cmp     esi, 2
        jb      .one
        mov     dword [ebp + stock], 0
.none:  ret

init:   pushad
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob
        mov     ebx, TABOBJS
        mov     eax, [ebx]
        mov     [ebp + stock], eax
        mov     eax, [ebx + 4]
        mov     [ebp + stock + 4], eax
        xor     esi, esi                ; the file: 0 then 1
.load:  call    load
        mov     eax, [edi]
        test    eax, eax
        jz      .next
        mov     ecx, [eax]
        push    dword [CHATOBJS]
        push    eax
        call    [ecx + S_TARGET]
        mov     eax, [edi]
        mov     ecx, [eax]
        push    0
        push    eax
        call    [ecx + S_TARGET]
.next:  inc     esi
        cmp     esi, 2
        jb      .load
        popad
        mov     edx, [ROOMFLAG]
        ret

free:   pushad
        call    .here
.here:  pop     ebp
        sub     ebp, .here
        call    menuoff
        popad
        mov     esi, CHATOBJS
        ret

; In place of the constructor's `call BMPLOAD` for the backdrop: the call again
; with the site's seven arguments, then the backdrop's two files.
room:   pushad
        call    .here
.here:  pop     ebp
        sub     ebp, .here
        mov     ecx, ARGS               ; the site's arguments, last first: each push moves the next one to the same offset
.again: push    dword [esp + 32 + 4 + (ARGS - 1) * 4]
        dec     ecx
        jnz     .again
        mov     eax, BMPLOAD
        call    eax
        add     esp, ARGS * 4
        mov     esi, 2                  ; the files: 2 then 3
.load:  call    load
        inc     esi
        cmp     esi, FILES
        jb      .load
        mov     dword [ebp + last], 0   ; the backdrop is fresh from the file: the keyboard's
        popad
        ret

roomfree:
        pushad
        call    .here
.here:  pop     ebp
        sub     ebp, .here
        call    menuoff
        mov     esi, 2
.one:   call    drop
        inc     esi
        cmp     esi, FILES
        jb      .one
        popad
        mov     esi, ROOMBG
        ret

frame:  pushad
        call    .here
.here:  pop     ebp
        sub     ebp, .here
        cmp     dword [ebp + objects], 0
        jne     .ask
        cmp     dword [ebp + objects + 8], 0
        je      .done                   ; nothing loaded: nothing to switch
.ask:   xor     edi, edi                ; the files to use: 0 the keyboard's, 1 the pad's
        cmp     dword [PADPOLL], 0
        je      .menu
        mov     eax, HELD
        call    paddown
        adc     edi, 0
.menu:  cmp     dword [ebp + objects], 0
        je      .back
        cmp     dword [ebp + objects + 4], 0
        je      .back
        lea     esi, [ebp + stock]      ; the keyboard's button objects
        test    edi, edi
        jz      .array
        lea     esi, [ebp + objects]    ; the pad's
.array: mov     ebx, TABOBJS
        mov     eax, [esi]
        mov     [ebx], eax
        mov     eax, [esi + 4]
        mov     [ebx + 4], eax
.back:  cmp     dword [ebp + objects + 8], 0
        je      .done
        cmp     dword [ebp + objects + 12], 0
        je      .done
        cmp     edi, [ebp + last]
        je      .done
        mov     ebx, [ROOMBG]           ; the backdrop (not `mov ebx, ROOMBG`: its opcode is the magic's own byte)
        test    ebx, ebx
        jz      .done
        mov     [ebp + last], edi
        mov     esi, [ebp + objects + 8 + edi * 4]  ; the backdrop's box, stock or SEL
        mov     ecx, [esi]
        push    ebx
        push    esi
        call    [ecx + S_TARGET]
        mov     ecx, [esi]
        lea     eax, [ebp + rect]
        push    eax
        push    BACK_Y
        push    BACK_X
        push    esi
        call    [ecx + S_BLIT]
        mov     ecx, [esi]
        push    0
        push    esi
        call    [ecx + S_TARGET]
.done:  popad
        mov     eax, [POLLBASE]
        ret

%include "padpoll.inc"

        align 4
names:  dd file0, file1, file2, file3   ; the files' names, offsets in this blob
objects: dd 0, 0, 0, 0                  ; the files' objects: the buttons while the menu is open, the backdrop's box while the room is up
sizes:  dd 0, 0, 0, 0, 0, 0, 0, 0       ; their sizes, as the loader writes them
stock:  dd 0, 0                         ; the stock button objects while the menu is open
last:   dd 0                            ; the backdrop's box in place: 0 stock, 1 SEL
rect:   dd 0, 0, 98, 18                 ; the box, whole
file0:  db 'TAB_MENU_SEL.BMP', 0
file1:  db 'TAB_MENU_SEL2.BMP', 0
file2:  db 'TAB_MENU_BACK.BMP', 0
file3:  db 'TAB_MENU_BACK_SEL.BMP', 0
