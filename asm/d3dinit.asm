; d3dinit.asm - a diagnostic: MGameD3D's bring-up, every step's HRESULT
; logged to logs\d3dinit.log in the game folder.
;
; Every step of the renderer's Init (0x10002090: the DirectDraw object,
; the cooperative level and display mode or the window, the surfaces,
; the device, the textures) ends with `mov [0x10011fc4], eax`, the
; DLL's last-HRESULT slot, and a `jl` out on a failure. The patcher
; makes each of those five-byte stores in the bring-up tree a call
; here: the store is done, and one line "<site> <hr> <w>x<h> <tw>x<th>"
; is appended - the store's RVA, the HRESULT, the picture size in the
; init struct's copy and the device's largest texture from the
; D3DDEVICEDESC the device enumeration kept (0 before it) - so the
; last line with a negative hr names the call that failed. After the
; store that follows Init's bring-up tree (FMTSITE, the second of its
; five stores, the texture formats enumerated and one picked by then)
; one more line, "fmt <slots> <chosen> <not565>": which of the
; DLL's thirteen format slots the device filled (bit n for slot n: 0
; P8, 1 X1R5G5B5, 2 R5G6B5, 3 A1R5G5B5, 4 A4R4G4B4, 5 P4, 6-10 DXT, 11
; X8R8G8B8, 12 a 16-bit RGB), the slot picked for the 16-bit textures
; and the "not 565" flag. Flags and registers are kept, since the site's
; `jl` reads the `test` before the store. On the first call the logs\
; folder is made beside the exe and the file opened in it,
; CREATE_ALWAYS, through the DLL's own kernel32 imports; if that fails
; the handle is -1 and nothing is logged. The lines stop
; at LIMIT so a texture create in a loop cannot fill a disk.
;
; The DLL is relocated on every load: the image base comes from this
; blob's own address less its RVA, filled in by the patcher.

bits 32

%define MAGIC_SELFRVA   0xE7E7E7E7      ; this blob's RVA, filled at apply time
%define LASTHR          0x11fc4         ; RVAs in MGameD3D.dll
%define WIDTH           0x123fc         ; the init struct's copy
%define HEIGHT          0x12400
%define MAXTEXW         0x124e4         ; the chosen device's D3DDEVICEDESC at 0x12430: dwMaxTextureWidth, Height
%define MAXTEXH         0x124e8
%define FMTSITE         0x20c5          ; the second of Init's five stores, after the texture formats are enumerated and one picked
%define FMTSLOTS        0x12594         ; the thirteen slots, a DDPIXELFORMAT copy each, 32 bytes; dwSize 0 when empty
%define FMTSLOTN        13
%define FMTCHOSEN       0x12740         ; the slot picked for the 16-bit textures
%define FMTNOT565       0x1273c
%define IAT_GETPROC     0xf0ac          ; kernel32 import slots
%define IAT_GETMODHANDLE 0xf0b0
%define IAT_GETMODFN    0xf038

%define MAX_PATH        260
%define PATHBUF         MAX_PATH + 24   ; room for logs\ and the name after the directory
%define LINEBUF         64
%define LIMIT           4096
%define GENERIC_WRITE   0x40000000
%define FILE_SHARE_READ 1
%define CREATE_ALWAYS   2
%define FILE_ATTRIBUTE_NORMAL 0x80

; In place of `mov [LASTHR], eax`; [esp] is the site + 5.
entry:
        pushfd
        pushad
        call    .here
.here:  pop     ebp
        sub     ebp, .here              ; ebp = this blob
        mov     ebx, ebp
        sub     ebx, MAGIC_SELFRVA      ; ebx = image base
        mov     [ebx + LASTHR], eax     ; the displaced store
        mov     esi, [esp + 36]         ; past pushad and pushfd
        sub     esi, 5
        sub     esi, ebx                ; the site's RVA
        mov     edx, eax                ; the HRESULT
        cmp     dword [ebp + handle], 0
        jne     .opened
        call    open
.opened:
        cmp     dword [ebp + handle], -1
        je      .done
        cmp     dword [ebp + count], LIMIT
        jae     .done
        inc     dword [ebp + count]
        sub     esp, LINEBUF            ; the line [esp], up to 44 bytes; written [esp+56]
        mov     edi, esp
        mov     eax, esi
        call    hex8
        mov     al, ' '
        stosb
        mov     eax, edx
        call    hex8
        mov     al, ' '
        stosb
        mov     eax, [ebx + WIDTH]
        call    decimal
        mov     al, 'x'
        stosb
        mov     eax, [ebx + HEIGHT]
        call    decimal
        mov     al, ' '
        stosb
        mov     eax, [ebx + MAXTEXW]
        call    decimal
        mov     al, 'x'
        stosb
        mov     eax, [ebx + MAXTEXH]
        call    decimal
        mov     al, 13
        stosb
        mov     al, 10
        stosb
        mov     eax, edi
        sub     eax, esp                ; the length
        push    0
        lea     ecx, [esp + 4 + 56]
        push    ecx
        push    eax
        lea     ecx, [esp + 12]
        push    ecx
        push    dword [ebp + handle]
        call    [ebp + pwrite]          ; WriteFile, stdcall
        cmp     esi, FMTSITE
        jne     .nofmt
        mov     edi, esp
        mov     eax, 'fmt '
        stosd
        xor     eax, eax                ; bit n for a filled slot n
        mov     ecx, FMTSLOTN
        lea     edx, [ebx + FMTSLOTS + (FMTSLOTN - 1) * 32]
.slot:  shl     eax, 1
        cmp     dword [edx], 0
        je      .empty
        or      eax, 1
.empty: sub     edx, 32
        dec     ecx
        jnz     .slot
        call    hex8
        mov     al, ' '
        stosb
        mov     eax, [ebx + FMTCHOSEN]
        call    hex8
        mov     al, ' '
        stosb
        mov     eax, [ebx + FMTNOT565]
        call    hex8
        mov     al, 13
        stosb
        mov     al, 10
        stosb
        mov     eax, edi
        sub     eax, esp
        push    0
        lea     ecx, [esp + 4 + 56]
        push    ecx
        push    eax
        lea     ecx, [esp + 12]
        push    ecx
        push    dword [ebp + handle]
        call    [ebp + pwrite]
.nofmt: add     esp, LINEBUF
.done:
        popad
        popfd
        ret

; eax as eight hex digits at edi.
hex8:
        push    ecx
        mov     ecx, 8
.digit: rol     eax, 4
        push    eax
        and     al, 15
        cmp     al, 10
        jb      .num
        add     al, 'a' - '0' - 10
.num:   add     al, '0'
        stosb
        pop     eax
        dec     ecx
        jnz     .digit
        pop     ecx
        ret

; eax in decimal at edi.
decimal:
        push    ecx
        push    edx
        push    ebx
        mov     ebx, 10
        xor     ecx, ecx
.div:   xor     edx, edx
        div     ebx
        push    edx
        inc     ecx
        test    eax, eax
        jnz     .div
.out:   pop     eax
        add     al, '0'
        stosb
        dec     ecx
        jnz     .out
        pop     ebx
        pop     edx
        pop     ecx
        ret

; Resolves CreateDirectoryA, CreateFileA and WriteFile, makes logs\
; beside the exe, opens the file in it and writes the header, or leaves
; the handle -1. ebp = the blob, ebx = the image base; edx is kept.
; Frame: path [esp], written [esp+PATHBUF], CreateFileA [esp+PATHBUF+4].
open:
        push    edx
        push    esi
        push    edi
        sub     esp, PATHBUF + 8
        mov     dword [ebp + handle], -1
        lea     eax, [ebp + s_k32]
        push    eax
        call    [ebx + IAT_GETMODHANDLE]
        test    eax, eax
        jz      .out
        mov     esi, eax
        lea     eax, [ebp + s_writefile]
        push    eax
        push    esi
        call    [ebx + IAT_GETPROC]
        test    eax, eax
        jz      .out
        mov     [ebp + pwrite], eax
        lea     eax, [ebp + s_createfile]
        push    eax
        push    esi
        call    [ebx + IAT_GETPROC]
        test    eax, eax
        jz      .out
        mov     [esp + PATHBUF + 4], eax
        lea     eax, [ebp + s_createdir]
        push    eax
        push    esi
        call    [ebx + IAT_GETPROC]
        test    eax, eax
        jz      .out
        mov     esi, eax                ; CreateDirectoryA
        push    MAX_PATH
        lea     ecx, [esp + 4]
        push    ecx
        push    0
        call    [ebx + IAT_GETMODFN]    ; GetModuleFileNameA(NULL, path, MAX_PATH)
        test    eax, eax
        jz      .out
        lea     edi, [esp + eax]        ; after the last backslash, or the start
.back:  cmp     edi, esp
        je      .name
        dec     edi
        cmp     byte [edi], '\'
        jne     .back
        inc     edi
.name:  lea     ecx, [ebp + s_dir]
        call    copy
        push    0
        lea     ecx, [esp + 4]
        push    ecx
        call    esi                     ; CreateDirectoryA(path, NULL); exists is fine
        mov     byte [edi - 1], '\'
        lea     ecx, [ebp + s_name]
        call    copy
        push    0
        push    FILE_ATTRIBUTE_NORMAL
        push    CREATE_ALWAYS
        push    0
        push    FILE_SHARE_READ
        push    GENERIC_WRITE
        lea     ecx, [esp + 24]
        push    ecx
        call    [esp + 28 + PATHBUF + 4]    ; CreateFileA
        cmp     eax, -1
        je      .out
        mov     [ebp + handle], eax
        push    0
        lea     ecx, [esp + 4 + PATHBUF]
        push    ecx
        push    s_head_len
        lea     ecx, [ebp + s_head]
        push    ecx
        push    eax
        call    [ebp + pwrite]
.out:
        add     esp, PATHBUF + 8
        pop     edi
        pop     esi
        pop     edx
        ret

; The string at ecx to edi, its terminator included; edi left after it.
copy:   mov     al, [ecx]
        mov     [edi], al
        inc     ecx
        inc     edi
        test    al, al
        jnz     copy
        ret

handle:         dd 0                    ; 0 not opened, -1 failed
pwrite:         dd 0
count:          dd 0
s_k32:          db 'kernel32.dll', 0
s_createdir:    db 'CreateDirectoryA', 0
s_createfile:   db 'CreateFileA', 0
s_dir:          db 'logs', 0
s_writefile:    db 'WriteFile', 0
s_name:         db 'd3dinit.log', 0
s_head:         db 'site hr WxH maxtex', 13, 10
s_head_len      equ $ - s_head
