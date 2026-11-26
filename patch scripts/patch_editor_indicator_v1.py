#!/usr/bin/env python3
r"""
Multiplayer "editor open" indicator (AoWx.exe, 2026-09-21).

Every AoWx client polls (every 3 s) whether an Age of Wonders editor is running on its own PC:
AoWEd.exe/AoWDevX.exe create the named file mapping "AOWED" at startup (their single-instance guard, kept alive
for the process lifetime), and the patched AoWDevX (patch_devx_editor_flags_v1) creates "AOWEDASG001",
"AOWEDASG002", ... (never closed) each time a saved game (.asg) is loaded, so the game can COUNT the loads by
probing the names in order (v4 2026-09-21: v3 held one flag, so re-loading the next autosave every turn was never
noticed).  Each change of the count queues an announcement; announcements are sent no earlier than 15 s after the
first poll (v3 sent at the first poll, before the chat session was up, so a save opened BEFORE the game started
was never reported) and the local echo of the line lands in the in-game chat (not the lobby memo).  Detection = CreateFileMappingA(-1,0,PAGE_READONLY,0,0x20,name) + GetLastError in
{ERROR_ALREADY_EXISTS 0xB7, ERROR_ACCESS_DENIED 5} (+CloseHandle) - no new imports needed (GetLastError via the
VCL30 IAT delta, timeGetTime via the HSEPack IAT delta).
State 0/1/2 (none / editor / editor+asg) is broadcast through the in-game chat as a hidden 3-char message
"\x01" + chr('A'+seated player index) + chr('0'+state) (DPID_ALLPLAYERS), on change and every 10 s while != 0;
receivers keep it 40 s.  For every counted .asg load the client also sends the plain chat line
"<name> has opened a saved game (.asg) in the editor", and echoes it into its own chat (DPlayChatMessage call:
memo + button flash + sound).  DPlayChatMessage (0x413F70) is hooked to swallow the hidden messages (they never
reach the memo / chat-button flash).
Display: the strategic taskbar player indicator PInd (TAoWFrame, [taskbar+0x94]) grows 17->23 px (DFM WinTop
0x1C->0x16, WinHeight 0x11->0x17, ILIndexLine 0x1D->0x35 = the 23-px tiles appended by build_tbwin_editor_lamps.py)
with a new lamp socket above each race icon; PIndDraw's y offsets move +6 (icon add ecx,2->8, ended-turn lamp
add ecx,0xB->0x11, CurP top add edx,0xB->0x11) and the ShowClipped call of the race icon (0x4576AD) is hooked to
draw the self-framed lamp 0x38 (bright) / 0x39 (dim, 8x7; rim spans the 6 px of the vanilla socket incl. the borrowed right rim, so it is centred on the turn lamp) at (x+1, y+0) for players whose state != 0, alternating
on a 32-bit pattern stepped every 256 ms (a slow green flicker); the 23-px tiles are transparent in their top 6 rows
so nothing shows for players without an editor.  TBWorldUpdate (0x457A4C, per frame while the strategic taskbar is
shown) is hooked for the poll/heartbeat/expiry and to invalidate the taskbar window + PInd ([+0x2C]=0) whenever the
flicker phase or a state changes.  Local detection runs in every game (so the own lamp can be tested single-player);
sends need a DPlay session (TGDPlay drops them otherwise).  v2 2026-09-21: v1 hooked ChatBtnUpdate (not called
unless the chat button is live), gated on MP, and drew a full-width socket row.
New RWX section .xedt @VA 0x62F000 (data + code).  The DPlayChatMessage hook covers a .reloc entry (0x413F74)
which is neutralised (type 3->0); --revert restores the backup.  Backup AoWx.exe.bak_edind (in <game>\backup\).
Requires Int\TBWin.ILB with 58 images (build_tbwin_editor_lamps.py --apply).  --apply rebuilds from the backup when present.
⚠ patch_aowx_cursor_coords.py rebuilds the live TTBWINDOW DFM from its own backup: re-run this script after it.
v5 2026-09-22 (second game instance): every AoWx claims a mapping "AOWX001".."AOWX008" at startup (hook 0x45999E
right after the game's own "AOW" mapping; first free number, handle kept for the process lifetime), the poll
counts how many exist (>= 2 -> state bit 4, lamp on) and announces "<name> has started a second copy of the
game" whenever the count rises (or is already >= 2 at the first poll), after the same 15 s startup delay.
Hidden state chars are now '0'..'7' (1 editor, 2 editor+asg, 4 second instance, combinable).
v6 2026-09-22: lamp colour by state - green (0x38/0x39) for the editor, RED (0x3A/0x3B) for a second game copy,
alternating every ~1 s when both; the announce timer and the instance baseline reset whenever the map object
changes (a second copy already running before the game started was never announced because D_FIRST dated from an
earlier game/map in the same session).
v8 2026-09-22: repaint via the toolkit's own mechanisms - flicker steps clear the frame's redraw flag [+0xA4]
(re-validating [+0x2C] made the whole strip blink), state changes push the PInd rect through
TAoWComponent.AddDrawRect + TAOWBaseWindow.InvalidateRect so the taskbar restores its background under a lamp
that went out (the old whole-window invalidate never cleared it until some later full repaint).
v7 2026-09-22: no time-based grace period any more - announcements go out as soon as the in-game chat is the
active target (the same test DPlayChatMessage uses: setup form [[0x45A30C]+0xA0]+0x75 hidden), so a second copy
or a loaded save is reported on the first poll of the game.
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_EXE = game_file(r"AoWx.exe")
BAK = ".bak_edind"
BASE = 0x400000
SEC_NAME, SEC_VA, SEC_VSIZE = b".xedt", 0x62F000, 0x1000
# exe globals / thunks
G_MAP, G_TB, G_ILBOWNER, G_SETUP = 0x45DF7C, 0x45A0CC, 0x45A4A0, 0x45A454
T_CREATEMAP, T_CLOSEHANDLE, T_GETREMOTE = 0x401270, 0x401258, 0x402F4C
T_SENDCHAT, T_LSTRCATN, T_LSTRCLR = 0x403624, 0x401128, 0x4010D8
T_ILGET, T_SHOWCLIPPED = 0x401ACC, 0x401A74
DPLAYCHATMSG = 0x413F70          # (edx=^AnsiString, one unused stack dword) - also used to echo the .asg line locally
SLOT_LSTRCATN, LINK_LSTRCATN, VCL_GETLASTERROR = 0x45D2F8, 0x41304A94, 0x413E43CC
SLOT_GETFIELD, LINK_GETFIELD, HSE_TIMEGETTIME = 0x45D9D8, 0x55608D84, 0x55630988
SLOT_SETLISTOFF, LINK_SETLISTOFF = 0x45EC94, 0x598168F4        # aowInt delta (rebase-safe)
AOWINT_ADDDRAWRECT, AOWINT_WIN_INVRECT = 0x59802AA4, 0x598075AC   # TAoWComponent.AddDrawRect(eax=win, edx=^rect, ecx=0); TAOWBaseWindow.InvalidateRect(eax=win, edx=fromIdx, ecx=^rect, [excl])
# hooks
H_UPD, H_UPD_ORIG, H_UPD_RESUME = 0x457A4C, bytes.fromhex("558bec83c4f05356"), 0x457A54   # TBWorldUpdate entry (per frame while the strategic taskbar shows)
H_RCV, H_RCV_ORIG, H_RCV_RESUME = 0x413F70, bytes.fromhex("558beca10ca34500"), 0x413F78
H_DRW, H_DRW_ORIG, H_DRW_RESUME = 0x4576AD, bytes.fromhex("e8c2a3faff"), 0x4576B2
H_INST, H_INST_ORIG, H_INST_RESUME = 0x45999E, bytes.fromhex("8bf0e8b7f4ffff"), 0x4599A5   # after CreateFileMappingA("AOW"): mov esi,eax ; call 0x458E5C
STARTUP_NEXT = 0x458E5C
IMM = [(0x4576AA, bytes.fromhex("83c102"), bytes.fromhex("83c108"), "icon y +2 -> +8"),
       (0x45776A, bytes.fromhex("83c10b"), bytes.fromhex("83c111"), "ended-turn lamp y +0xB -> +0x11"),
       (0x457706, bytes.fromhex("83c20b"), bytes.fromhex("83c211"), "CurP top +0xB -> +0x11")]
RES_ENTRY_FO = 0x731A0          # RT_RCDATA TTBWINDOW data entry (rva, size)
DFM_EDITS = [(b"\x04PInd", b"\x06WinTop\x02\x1c", b"\x06WinTop\x02\x16"),
             (b"\x04PInd", b"\x09WinHeight\x02\x11", b"\x09WinHeight\x02\x17"),
             (b"\x04PInd", b"\x0bILIndexLine\x02\x1d", b"\x0bILIndexLine\x02\x35")]
IMG_BRIGHT, IMG_DIM = 0x38, 0x39          # green; +2 = red (0x3A / 0x3B)
IMG_SWORD = 0x3C                          # 4x9 'in combat' marker, blinks in place of the race icon (2026-11-16)
PATTERN = 0b10110111011001011101101110010110   # bit set = bright, stepped every 256 ms
POLL_MS, HEARTBEAT_MS, EXPIRE_MS = 3000, 10000, 40000
ANNOUNCE_DELAY_MS, ASG_MAX = 15000, 999
ks = Ks(KS_ARCH_X86, KS_MODE_32)

# data layout
D_STATE = SEC_VA + 0x00      # 16 bytes
D_EXP = SEC_VA + 0x10        # 16 dwords
D_LOCAL = SEC_VA + 0x50
D_LASTPOLL = SEC_VA + 0x54
D_LASTSEND = SEC_VA + 0x58
D_LASTPHASE = SEC_VA + 0x5C
D_TMPSTR = SEC_VA + 0x60
D_NAME_ED = SEC_VA + 0x70    # "AOWED\0"
D_NAME_ASG = SEC_VA + 0x78   # "AOWEDASG000\0" (digits patched per probe)
D_ASGSEEN = SEC_VA + 0x64    # asg load count last seen from the editor
D_PENDING = SEC_VA + 0x68    # 1 = an .asg announcement is due
D_FIRST = SEC_VA + 0x6C      # time of the first poll (announcements wait ANNOUNCE_DELAY_MS after it)
D_ASGLINE_HDR = SEC_VA + 0x88
D_ASGLINE = SEC_VA + 0x90    # Delphi string chars
ASG_TEXT = b" has opened a saved game (.asg) in the editor"
D_HIDDEN_HDR = SEC_VA + 0xE0
D_HIDDEN = SEC_VA + 0xE8     # 3 chars + NUL
D_INSTLINE_HDR = SEC_VA + 0xF0
D_INSTLINE = SEC_VA + 0xF8   # Delphi string chars
INST_TEXT = b" has started a second copy of the game"
D_INST = SEC_VA + 0x120      # running AoWx instances seen at the last poll (0 = never polled)
D_PENDING2 = SEC_VA + 0x124  # 1 = a second-instance announcement is due
D_INSTNAME = SEC_VA + 0x128  # "AOWX000\0" (digits patched)
D_LASTMAP = SEC_VA + 0x130   # map object of the last poll: a new game resets the announce timer
D_LASTCOMBAT = SEC_VA + 0x134  # [map+0x120] at the last frame (a change repaints the indicator strip)
INST_MAX = 8
CODE_OFF = 0x140


def asm(src, addr):
    src = chr(10).join(l.split(';')[0] for l in src.splitlines())   # keystone hangs on ';' comments
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def code(va):
    return asm(f"""
    ; ---------------- helpers ----------------
    tgt:                                  ; eax = timeGetTime()  (HSEPack IAT delta)
        mov eax, [{SLOT_GETFIELD:#x}]
        sub eax, {LINK_GETFIELD:#x}
        call dword ptr [eax + {HSE_TIMEGETTIME:#x}]
        ret
    getlasterr:
        mov eax, [{SLOT_LSTRCATN:#x}]
        sub eax, {LINK_LSTRCATN:#x}
        call dword ptr [eax + {VCL_GETLASTERROR:#x}]
        ret
    detect:                               ; edx = name -> eax 1/0
        push esi
        push edi
        push edx
        push 0
        call {T_CLOSEHANDLE:#x}           ; CloseHandle(0): last error := ERROR_INVALID_HANDLE (6) - a fresh
        pop edx                           ; CreateFileMapping does not reset a stale ERROR_ALREADY_EXISTS
        push edx
        push 0x20
        push 0
        push 2
        push 0
        push -1
        call {T_CREATEMAP:#x}
        mov esi, eax
        call getlasterr
        mov edi, eax
        test esi, esi
        jz d_noh
        push esi
        call {T_CLOSEHANDLE:#x}
    d_noh:
        xor eax, eax
        cmp edi, 0xB7
        je d_yes
        cmp edi, 5
        jne d_out
    d_yes:
        inc eax
    d_out:
        pop edi
        pop esi
        ret
    gdplay:                               ; eax = TGDPlay or 0
        mov eax, [{G_SETUP:#x}]
        mov eax, [eax]
        test eax, eax
        jz g_out
        mov eax, [eax + 0x44]
    g_out:
        ret
    send_hidden:
        mov eax, [{G_MAP:#x}]
        mov eax, [eax]
        mov al, [eax + 0xA5]
        add al, 'A'
        mov [{D_HIDDEN + 1:#x}], al
        mov al, [{D_LOCAL:#x}]
        add al, '0'
        mov [{D_HIDDEN + 2:#x}], al
        call gdplay
        test eax, eax
        jz sh_out
        xor edx, edx
        mov ecx, {D_HIDDEN:#x}
        call {T_SENDCHAT:#x}
    sh_out:
        ret
    send_line:                            ; edx = Delphi string chars of the line body
        push edx
        call gdplay
        pop edx
        test eax, eax
        jz sa_out
        push eax
        push dword ptr [eax + 0x28]
        push edx
        mov eax, {D_TMPSTR:#x}
        mov edx, 2
        call {T_LSTRCATN:#x}
        pop eax
        xor edx, edx
        mov ecx, [{D_TMPSTR:#x}]
        call {T_SENDCHAT:#x}
        push 0
        mov edx, {D_TMPSTR:#x}
        xor eax, eax
        call {DPLAYCHATMSG:#x}
        mov eax, {D_TMPSTR:#x}
        call {T_LSTRCLR:#x}
    sa_out:
        ret
    instname:                             ; ecx = n -> D_INSTNAME = "AOWX" + 3 digits  (clobbers eax, edx)
        mov eax, ecx
        xor edx, edx
        push ecx
        mov ecx, 100
        div ecx
        add al, '0'
        mov [{D_INSTNAME + 4:#x}], al
        mov eax, edx
        xor edx, edx
        mov ecx, 10
        div ecx
        add al, '0'
        mov [{D_INSTNAME + 5:#x}], al
        add dl, '0'
        mov [{D_INSTNAME + 6:#x}], dl
        pop ecx
        ret
    chatready:                            ; eax = 1 when the in-game chat is the active target (setup form hidden)
        mov eax, [{0x45A30C:#x}]
        mov eax, [eax]
        test eax, eax
        jz cr_yes
        mov eax, [eax + 0xA0]
        test eax, eax
        jz cr_yes
        cmp byte ptr [eax + 0x75], 0
        jne cr_no
    cr_yes:
        mov eax, 1
        ret
    cr_no:
        xor eax, eax
        ret
    invalidate:                           ; state change: dirty-rect the PInd area (background restored) + redraw
        mov eax, [{G_TB:#x}]
        mov eax, [eax]
        test eax, eax
        jz inv_out
        mov ecx, [eax + 0x94]
        test ecx, ecx
        jz inv_out
        push ebx
        push esi
        mov esi, eax                      ; esi = taskbar window
        sub esp, 16                       ; TRect(left, top, right, bottom) in window coordinates
        mov edx, [ecx + 0x84]
        mov [esp], edx
        add edx, [ecx + 0x7C]
        mov [esp + 8], edx
        mov edx, [ecx + 0x88]
        mov [esp + 4], edx
        add edx, [ecx + 0x80]
        mov [esp + 12], edx
        mov byte ptr [ecx + 0xA4], 0
        mov ebx, [{SLOT_SETLISTOFF:#x}]
        sub ebx, {LINK_SETLISTOFF:#x}
        mov edx, esp
        xor ecx, ecx
        mov eax, esi
        lea ebx, [ebx + {AOWINT_ADDDRAWRECT:#x}]
        call ebx
        mov ebx, [{SLOT_SETLISTOFF:#x}]
        sub ebx, {LINK_SETLISTOFF:#x}
        push 0
        lea ecx, [esp + 4]
        xor edx, edx
        mov eax, esi
        lea ebx, [ebx + {AOWINT_WIN_INVRECT:#x}]
        call ebx                          ; stdcall-ish: pops its one stack arg
        add esp, 16
        pop esi
        pop ebx
        ret
    popup_player:                         ; eax = map -> eax = player holding a combat pop-up, or -1
        ; TArmyCombatMoveTE.SetupCombat (0x55748D18) locks the AI executer, sets the token executer's hold byte
        ; and activates the asked player's token control ([map+0xA4]) while the "How do you want to fight" request
        ; (or the automatic resolve) is pending - on every machine, before any TCombat exists.
        push ecx
        mov ecx, [eax + 0x128]            ; TAIExecuter
        test ecx, ecx
        jz pp_no
        cmp dword ptr [ecx + 0x30], 0     ; AI lock
        je pp_no
        mov ecx, [eax + 0x23C]            ; TTokenManager
        test ecx, ecx
        jz pp_no
        mov ecx, [ecx + 4]                ; TTokenExecuter
        test ecx, ecx
        jz pp_no
        cmp byte ptr [ecx + 0x54], 0      ; hold
        je pp_no
        movsx eax, byte ptr [eax + 0xA4]
        pop ecx
        ret
    pp_no:
        or eax, -1
        pop ecx
        ret
    invalidate_pind:                      ; flicker phase: PInd redraw flag only (no re-validate -> no blink)
        mov eax, [{G_TB:#x}]
        mov eax, [eax]
        test eax, eax
        jz inv_out
        mov eax, [eax + 0x94]
        test eax, eax
        jz inv_out
        mov byte ptr [eax + 0xA4], 0
    inv_out:
        ret
    ; ---------------- per-frame maintenance ----------------
    maint:
        mov eax, [{G_MAP:#x}]
        mov eax, [eax]
        test eax, eax
        jz m_out
        call tgt
        mov esi, eax                      ; esi = now
        mov eax, esi
        sub eax, [{D_LASTPOLL:#x}]
        cmp eax, {POLL_MS}
        jb m_flick
        mov [{D_LASTPOLL:#x}], esi
        ; expire remote entries
        xor ecx, ecx
    m_exp:
        cmp byte ptr [{D_STATE:#x} + ecx], 0
        je m_expn
        mov eax, esi
        sub eax, [{D_EXP:#x} + ecx*4]
        js m_expn
        mov byte ptr [{D_STATE:#x} + ecx], 0
        call invalidate
    m_expn:
        inc ecx
        cmp ecx, 16
        jb m_exp
        ; local detection
        mov eax, [{G_MAP:#x}]
        mov eax, [eax]
        cmp eax, [{D_LASTMAP:#x}]
        je m_det
        mov [{D_LASTMAP:#x}], eax         ; new game/map: announcements wait ANNOUNCE_DELAY_MS from now,
        mov [{D_FIRST:#x}], esi           ; and the instance baseline is re-observed
        mov dword ptr [{D_INST:#x}], 0
    m_det:
        xor edi, edi
        mov edx, {D_NAME_ED:#x}
        call detect
        test eax, eax
        jnz m_ed
        mov dword ptr [{D_ASGSEEN:#x}], 0
        jmp m_instc
    m_ed:
        inc edi
        ; count the editor's .asg loads: names AOWEDASG001.. exist while the editor lives
        xor ecx, ecx
    m_cnt:
        inc ecx
        cmp ecx, {ASG_MAX}
        ja m_cntd
        push ecx
        mov eax, ecx
        xor edx, edx
        mov ecx, 100
        div ecx
        add al, '0'
        mov [{D_NAME_ASG + 8:#x}], al
        mov eax, edx
        xor edx, edx
        mov ecx, 10
        div ecx
        add al, '0'
        mov [{D_NAME_ASG + 9:#x}], al
        add dl, '0'
        mov [{D_NAME_ASG + 10:#x}], dl
        mov edx, {D_NAME_ASG:#x}
        call detect
        pop ecx
        test eax, eax
        jnz m_cnt
    m_cntd:
        dec ecx                           ; ecx = number of .asg loads
        jz m_asgn
        inc edi                           ; state 2
        cmp ecx, [{D_ASGSEEN:#x}]
        je m_asgn
        mov dword ptr [{D_PENDING:#x}], 1
    m_asgn:
        mov [{D_ASGSEEN:#x}], ecx
    m_instc:                              ; second game instance: count AOWX001.. (one per running AoWx, incl. ourselves)
        xor ecx, ecx
        push ebx
        xor ebx, ebx
    m_icnt:
        inc ecx
        cmp ecx, {INST_MAX}
        ja m_icntd
        push ecx
        call instname
        mov edx, {D_INSTNAME:#x}
        call detect
        pop ecx
        add ebx, eax
        jmp m_icnt
    m_icntd:
        mov ecx, ebx
        pop ebx
        cmp ecx, 2
        jb m_inst1
        or edi, 4
        cmp ecx, [{D_INST:#x}]
        jbe m_inst1
        cmp dword ptr [{D_INST:#x}], 0
        jne m_instp
        cmp ecx, 2                        ; first observation: announce only if already >= 2
        jb m_inst1
    m_instp:
        mov dword ptr [{D_PENDING2:#x}], 1
    m_inst1:
        mov [{D_INST:#x}], ecx
    m_have:
        mov eax, [{G_MAP:#x}]
        mov eax, [eax]
        movzx ecx, byte ptr [eax + 0xA5]
        cmp ecx, 16
        jae m_cmp
        mov eax, edi
        mov [{D_STATE:#x} + ecx], al
        lea eax, [esi + {EXPIRE_MS}]
        mov [{D_EXP:#x} + ecx*4], eax
    m_cmp:
        cmp edi, [{D_LOCAL:#x}]
        je m_beat
        mov [{D_LOCAL:#x}], edi
        mov [{D_LASTSEND:#x}], esi
        call invalidate
        call send_hidden
        jmp m_ann
    m_beat:
        test edi, edi
        jz m_flick
        mov eax, esi
        sub eax, [{D_LASTSEND:#x}]
        cmp eax, {HEARTBEAT_MS}
        jb m_flick
        mov [{D_LASTSEND:#x}], esi
        call send_hidden
    m_ann:
        cmp dword ptr [{D_PENDING:#x}], 0
        je m_flick
        call chatready
        test eax, eax
        jz m_flick
        mov dword ptr [{D_PENDING:#x}], 0
        mov edx, {D_ASGLINE:#x}
        call send_line
    m_flick:
        cmp dword ptr [{D_PENDING2:#x}], 0
        je m_flick2
        call chatready
        test eax, eax
        jz m_flick2
        mov dword ptr [{D_PENDING2:#x}], 0
        mov edx, {D_INSTLINE:#x}
        call send_line
    m_flick2:
        mov eax, [{G_MAP:#x}]             ; combat marker: repaint when a battle starts / ends, and on every phase
        mov eax, [eax]
        xor edx, edx
        test eax, eax
        jz m_cb
        mov edx, [eax + 0x120]
        test edx, edx
        jnz m_cb
        call popup_player                 ; pop-up stage counts as "battle" for repainting (value = player + 1)
        lea edx, [eax + 1]
    m_cb:
        cmp edx, [{D_LASTCOMBAT:#x}]
        je m_cb2
        mov [{D_LASTCOMBAT:#x}], edx
        push edx
        call invalidate_pind
        pop edx
    m_cb2:
        mov eax, esi
        shr eax, 8
        cmp eax, [{D_LASTPHASE:#x}]
        je m_out
        mov [{D_LASTPHASE:#x}], eax
        test edx, edx
        jz m_st
        call invalidate_pind
        ret
    m_st:
        mov eax, [{D_STATE:#x}]
        or eax, [{D_STATE + 4:#x}]
        or eax, [{D_STATE + 8:#x}]
        or eax, [{D_STATE + 12:#x}]
        test eax, eax
        jz m_out
        call invalidate_pind
    m_out:
        ret
    ; ---------------- hook: ChatBtnUpdate entry ----------------
    cave_upd:
        pushad
        call maint
        popad
        push ebp
        mov ebp, esp
        add esp, -0x10
        push ebx
        push esi
        jmp {H_UPD_RESUME:#x}
    ; ---------------- hook: DPlayChatMessage entry ----------------
    cave_rcv:
        mov eax, [edx]
        test eax, eax
        jz r_orig
        cmp dword ptr [eax - 4], 3
        jb r_orig
        cmp byte ptr [eax], 1
        jne r_orig
        movzx ecx, byte ptr [eax + 1]
        sub ecx, 'A'
        cmp ecx, 16
        jae r_done
        movzx edx, byte ptr [eax + 2]
        sub edx, '0'
        cmp edx, 7
        ja r_done
        mov [{D_STATE:#x} + ecx], dl
        push ecx
        call tgt
        pop ecx
        add eax, {EXPIRE_MS}
        mov [{D_EXP:#x} + ecx*4], eax
        call invalidate
    r_done:
        ret 4
    r_orig:
        push ebp
        mov ebp, esp
        mov eax, [{0x45A30C:#x}]
        jmp {H_RCV_RESUME:#x}
    ; ---------------- hook: startup, after CreateFileMappingA("AOW") ----------------
    cave_inst:
        mov esi, eax
        pushad
        xor ebx, ebx                      ; counter in EBX: ECX/EDX/EAX are clobbered by the Win32 calls
    i_loop:
        inc ebx
        cmp ebx, {INST_MAX}
        ja i_done
        mov ecx, ebx
        call instname
        push 0
        call {T_CLOSEHANDLE:#x}           ; reset the last error (see detect)
        push {D_INSTNAME:#x}
        push 0x20
        push 0
        push 2
        push 0
        push -1
        call {T_CREATEMAP:#x}
        mov edi, eax
        call getlasterr
        cmp eax, 0xB7
        jne i_done                        ; created (or failed outright): keep the handle for the process lifetime
        test edi, edi
        jz i_loop
        push edi
        call {T_CLOSEHANDLE:#x}
        jmp i_loop
    i_done:
        popad
        call {STARTUP_NEXT:#x}
        jmp {H_INST_RESUME:#x}
    ; ---------------- hook: PIndDraw race-icon ShowClipped ----------------
    cave_drw:                             ; eax = race icon image, edx = x, ecx = y, clip rect on the stack, ebx = player
        push eax
        push ecx
        push edx
        cmp ebx, 16
        jae d_norm
        mov eax, [{G_MAP:#x}]
        mov eax, [eax]
        test eax, eax
        jz d_norm
        push eax
        call popup_player                 ; combat pop-up / auto-combat stage (no TCombat yet): the asked player
        cmp eax, ebx
        pop eax
        je d_hit
        mov eax, [eax + 0x120]            ; TCombat (tactical battle running: all its human participants)
        test eax, eax
        jz d_norm
        mov eax, [eax + 0xC]              ; TCombatData
        test eax, eax
        jz d_norm
        mov eax, [eax + 0x38]             ; TCombatPlayerList
        test eax, eax
        jz d_norm
        mov eax, [eax + 8]                ; its TList
        test eax, eax
        jz d_norm
        mov ecx, [eax + 8]
        mov edx, [eax + 4]
    d_lp:
        dec ecx
        js d_norm
        mov eax, [edx + ecx*4]
        test eax, eax
        jz d_lp
        cmp bl, [eax + 8]                 ; TCombatPlayer.player index
        jne d_lp
    d_hit:
        call tgt
        test eax, 0x200                   ; ~0.5 s sword / ~0.5 s race icon
        jz d_norm
        mov edx, {IMG_SWORD:#x}
        mov eax, [{G_ILBOWNER:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x88]
        call {T_ILGET:#x}
        pop edx
        pop ecx
        add esp, 4
        jmp d_show
    d_norm:
        pop edx
        pop ecx
        pop eax
    d_show:
        call {T_SHOWCLIPPED:#x}
        cmp ebx, 16
        jae w_out
        cmp byte ptr [{D_STATE:#x} + ebx], 0
        je w_out
        push ebp
        mov ebp, esp                      ; [ebp+4] = slot k, [ebp+8] = clip rect
        call tgt
        mov ecx, eax
        sub ecx, [{D_EXP:#x} + ebx*4]
        jns w_leave
        mov edx, eax                      ; edx = now
        shr eax, 8
        and eax, 31
        mov ecx, {PATTERN:#x}
        bt ecx, eax
        mov eax, {IMG_DIM:#x}
        jnc w_idx
        mov eax, {IMG_BRIGHT:#x}
    w_idx:
        movzx ecx, byte ptr [{D_STATE:#x} + ebx]
        test cl, 4
        jz w_col                          ; editor only -> green
        test cl, 3
        jz w_red                          ; second game only -> red
        shr edx, 10                       ; both: alternate green/red every ~1 s
        test edx, 1
        jz w_col
    w_red:
        add eax, 2
    w_col:
        push eax                          ; [ebp-4] image index
        mov eax, [edi + 0x94]
        mov edx, [eax + 0x84]
        add edx, 1
        mov ecx, [ebp + 4]
        lea ecx, [ecx + ecx*4]
        add edx, ecx
        push edx                          ; [ebp-8] x
        mov ecx, [eax + 0x88]
        push ecx                          ; [ebp-0xC] y (8x7 self-framed lamp)
        lea eax, [ebp + 8]
        push eax                          ; clip rect (ShowClipped stack arg)
        mov edx, [ebp - 4]
        mov eax, [{G_ILBOWNER:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x88]
        call {T_ILGET:#x}
        mov edx, [ebp - 8]
        mov ecx, [ebp - 0xC]
        call {T_SHOWCLIPPED:#x}
    w_leave:
        mov esp, ebp
        pop ebp
    w_out:
        jmp {H_DRW_RESUME:#x}
    """, va)



def build_section():
    blob = bytearray(SEC_VSIZE)
    blob[D_NAME_ED - SEC_VA:D_NAME_ED - SEC_VA + 6] = b"AOWED\0"
    blob[D_NAME_ASG - SEC_VA:D_NAME_ASG - SEC_VA + 12] = b"AOWEDASG000\0"
    struct.pack_into("<ii", blob, D_ASGLINE_HDR - SEC_VA, -1, len(ASG_TEXT))
    blob[D_ASGLINE - SEC_VA:D_ASGLINE - SEC_VA + len(ASG_TEXT) + 1] = ASG_TEXT + b"\0"
    struct.pack_into("<ii", blob, D_HIDDEN_HDR - SEC_VA, -1, 3)
    blob[D_HIDDEN - SEC_VA:D_HIDDEN - SEC_VA + 4] = b"\x01A0\0"
    struct.pack_into("<ii", blob, D_INSTLINE_HDR - SEC_VA, -1, len(INST_TEXT))
    blob[D_INSTLINE - SEC_VA:D_INSTLINE - SEC_VA + len(INST_TEXT) + 1] = INST_TEXT + b"\0"
    blob[D_INSTNAME - SEC_VA:D_INSTNAME - SEC_VA + 8] = b"AOWX000\0"
    c = code(SEC_VA + CODE_OFF)
    assert CODE_OFF + len(c) <= SEC_VSIZE, len(c)
    blob[CODE_OFF:CODE_OFF + len(c)] = c
    # locate cave entries by unique signatures
    def find(sig):
        i = c.find(sig); assert i >= 0 and c.find(sig, i + 1) < 0, sig.hex(); return SEC_VA + CODE_OFF + i
    ent = {"upd": find(b"\x60\xe8"),                                  # pushad ; call maint
           "rcv": find(bytes.fromhex("8b0285c0")),                    # mov eax,[edx] ; test eax,eax
           "drw": find(bytes.fromhex("50515283fb10")),               # push eax/ecx/edx ; cmp ebx,16 (combat marker test first)
           "inst": find(bytes.fromhex("89c660")) if c.find(bytes.fromhex("89c660")) >= 0 else find(bytes.fromhex("8bf060"))}   # mov esi,eax ; pushad
    return bytes(blob), len(c), ent


def va2off(pe_bytes, va):
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    nsec = struct.unpack_from("<H", pe_bytes, e_lfanew + 6)[0]
    opt = struct.unpack_from("<H", pe_bytes, e_lfanew + 20)[0]
    sec = e_lfanew + 24 + opt
    for i in range(nsec):
        s = sec + 40 * i
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", pe_bytes, s + 8)
        if rva <= va - BASE < rva + max(vsz, rsz):
            return roff + (va - BASE - rva)
    raise ValueError(f"VA {va:#x} not in any section")


def reloc_entries(pe_bytes, ranges):
    """[(file offset of the 16-bit entry, va, type)] for relocs inside ranges."""
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    dd_rva, dd_sz = struct.unpack_from("<II", pe_bytes, e_lfanew + 24 + 0x88)
    if not dd_sz:
        return []
    off = va2off(pe_bytes, BASE + dd_rva); end = off + dd_sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", pe_bytes, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            eo = off + 8 + 2 * i
            e = struct.unpack_from("<H", pe_bytes, eo)[0]
            va = BASE + page + (e & 0xFFF)
            if any(lo <= va < hi for lo, hi in ranges):
                hits.append((eo, va, e >> 12))
        off += bsz
    return hits


def jmp_bytes(src, dst, ln):
    return b"\xe9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (ln - 5)


def dfm_sites(data):
    rva, size = struct.unpack_from("<II", data, RES_ENTRY_FO)
    o = va2off(data, BASE + rva); dfm = bytes(data[o:o + size]); assert dfm[:4] == b"TPF0"
    sites = []
    for obj, old, new in DFM_EDITS:
        i = dfm.find(obj); assert i >= 0 and dfm.find(obj, i + 1) < 0, "PInd object not unique"
        seg = dfm[i:i + 0x300]
        jo, jn = seg.find(old), seg.find(new)
        assert (jo >= 0) != (jn >= 0), f"DFM prop {old!r}: neither/both states found"
        sites.append((o + i + (jo if jo >= 0 else jn), old, new, f"PInd DFM {old[1:1 + old[0]].decode()}"))
    return sites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    exe = a.exe; bak = bak_path(exe, BAK, create=a.apply)
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, exe); print(f"reverted {exe} from {bak}"); return
    blob, clen, ent = build_section()
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob[CODE_OFF:CODE_OFF + clen], SEC_VA + CODE_OFF):
            print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
    data = bytearray(open(exe, "rb").read())
    if a.apply and os.path.exists(bak):
        data = bytearray(open(bak, "rb").read()); print(f"  rebuilding from {bak}")
    ilb = game_file(r"Int\TBWin.ILB")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "old modding tools", "research"))
    import ilbcodec
    nimg = len(ilbcodec.read(ilb)['images'])
    e = struct.unpack_from("<I", data, 0x3C)[0]; nsec = struct.unpack_from("<H", data, e + 6)[0]
    sec0 = e + 24 + struct.unpack_from("<H", data, e + 20)[0]
    names = [bytes(data[sec0 + 40 * i:sec0 + 40 * i + 8]).rstrip(b"\0") for i in range(nsec)]
    already = SEC_NAME in names
    sites = [(va2off(data, H_UPD), H_UPD_ORIG, jmp_bytes(H_UPD, ent["upd"], len(H_UPD_ORIG)), "TBWorldUpdate -> cave_upd"),
             (va2off(data, H_RCV), H_RCV_ORIG, jmp_bytes(H_RCV, ent["rcv"], len(H_RCV_ORIG)), "DPlayChatMessage -> cave_rcv"),
             (va2off(data, H_DRW), H_DRW_ORIG, jmp_bytes(H_DRW, ent["drw"], len(H_DRW_ORIG)), "PIndDraw ShowClipped -> cave_drw"),
             (va2off(data, H_INST), H_INST_ORIG, jmp_bytes(H_INST, ent["inst"], len(H_INST_ORIG)), "startup AOW mapping -> cave_inst")]
    sites += [(va2off(data, va), old, new, desc) for va, old, new, desc in IMM]
    sites += dfm_sites(data)
    print(f"target: {exe}\n  section {SEC_NAME.decode()} @{SEC_VA:#x}: {'present' if already else 'absent'}; code {clen} B; entries "
          + ", ".join(f"{k} {v:#x}" for k, v in ent.items()) + f"\n  TBWin.ILB images: {nimg} ({'ok' if nimg >= 0x3D else 'RUN build_tbwin_editor_lamps.py --apply FIRST'})")
    states = []
    for off, old, new, desc in sites:
        cur = bytes(data[off:off + len(old)])
        st = "vanilla" if cur == old else "PATCHED" if cur == new else f"UNKNOWN {cur.hex()}"
        states.append(st); print(f"  {desc}: {st}")
    rl = reloc_entries(data, [(H_UPD, H_UPD + len(H_UPD_ORIG)), (H_RCV, H_RCV + len(H_RCV_ORIG)), (H_DRW, H_DRW + len(H_DRW_ORIG)), (H_INST, H_INST + len(H_INST_ORIG))]
                       + [(va, va + 3) for va, *_ in IMM])
    print(f"  relocs in hook ranges: {[(hex(va), t) for _, va, t in rl]} (0x413f74 type 3 is expected and gets neutralised)")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if nimg < 0x3D:
        sys.exit("TBWin.ILB lacks the lamp images - refusing")
    if any(s.startswith("UNKNOWN") for s in states):
        sys.exit("refusing: unexpected bytes")
    bad = [(hex(va), t) for _, va, t in rl if va != 0x413F74 and t != 0]
    if bad:
        sys.exit(f"refusing: unexpected relocs {bad}")
    if not os.path.exists(bak):
        shutil.copy2(exe, bak); print(f"  backup -> {bak}")
    if not already:
        assert sec0 + 40 * (nsec + 1) <= 0x400
        size_of_image = struct.unpack_from("<I", data, e + 24 + 56)[0]
        assert size_of_image == SEC_VA - BASE, f"SizeOfImage {size_of_image:#x} != expected {SEC_VA - BASE:#x}"
        pad = (-len(data)) % 0x200; data += bytes(pad); rawoff = len(data); data += blob
        hdr = SEC_NAME.ljust(8, b"\0") + struct.pack("<IIIIIIHHI", SEC_VSIZE, SEC_VA - BASE, SEC_VSIZE, rawoff, 0, 0, 0, 0, 0xE0000060)
        struct.pack_into("<40s", data, sec0 + 40 * nsec, hdr); struct.pack_into("<H", data, e + 6, nsec + 1)
        struct.pack_into("<I", data, e + 24 + 56, SEC_VA - BASE + SEC_VSIZE)
        print(f"  appended {SEC_NAME.decode()} raw @{rawoff:#x}")
    else:
        i = names.index(SEC_NAME); rawoff = struct.unpack_from("<I", data, sec0 + 40 * i + 20)[0]
        data[rawoff:rawoff + SEC_VSIZE] = blob; print("  refreshed section")
    for off, old, new, desc in sites:
        data[off:off + len(new)] = new
    for eo, va, t in rl:
        if t == 3:
            struct.pack_into("<H", data, eo, struct.unpack_from("<H", data, eo)[0] & 0x0FFF); print(f"  reloc @{va:#x} neutralised")
    with open(exe, "wb") as f:
        f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
