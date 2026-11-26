#!/usr/bin/env python3
r"""
AoWxShot.dll module: the editor's  Options -> Map Settings -> "Map Level Vision"  tab (2026-11-22).

User: "add another new tab to Map Settings called 'Map Level Vision'.  it should display every map level, and have
toggleable 'Night Vision required?'.  the default toggle should be existing (firmament/surface = off, all underground
= on)" + "exploration sites always require night vision regardless of map level" (said on the tab's hint line; the
site rule is the game's own and is not changed).

Rides on the Ban List module's two in-memory hooks (aowxshot_banlist.py): bl_fcwrap calls `lv_build` after the dialog's
FormCreate, bl_ok calls `lv_store` after the dialog was applied to the map.  Entry state of both: ebx = the
TMapSettingsDlg form, ebp = the DLL's delta base.  Reuses bl_label / bl_box.
The tab: TTabSheet "Map Level Vision" (after Ban List), a caption, ONE check list of the map's levels in display
order (Firmament, Surface, Caverns, Depths, Abyss ...; hidden levels and levels the map does not have are left out),
a hint line.  Ticked = Night Vision required on that level.
Data (patch_levelvision_v1.py): dword TAoWHSMap +0x480, bit L = level L toggled away from the default
(default required = L not in (0, 3)).  The map is the editor's current map [[0x43289C]] (import AoWE.AoWHSMap).
The tab is only built when the storage patch is installed (AoWEPACK InstanceSize dword RVA 0xE858 == 0x488) and the
level-name function of the level UI patch is present (RVA 0x151710 starts with E8; eax = level -> AnsiString).
Level count = [[map+0x10]+0x14]; hidden-level mask = [map+0x41C].
On OK only the listed levels' bits are rewritten; nothing is written on Cancel or when the map changed meanwhile.
When the mask changed, `lv_refresh` re-runs TArmy.Update (AoWEPACK RVA 0x8D1B0: it recomputes the army's CACHED sight
byte [army+0x29] and its unfog) on the army of every registered unit ([map+0xFC] TUnitControl -> [+0x10] TList;
[unit+4] = owner, taken only when it is exactly a TArmy, VMT RVA 0x130EC) and then TAoWHSMap.UpdateVisibility (RVA
0x78408), so the editor's Fog of War view follows the new ticks at once (user 11/22).  Both routines are verified by
their first four bytes before they are called.
"""
import struct
import aowxshot_banlist as BL

IAT_HSMAP = 0x43289C                                  # AoWDevX import AoWE.AoWHSMap (address of the variable)
INSTSIZE_RVA, INSTSIZE_WANT = 0xE858, 0x488      # patch_levelvision_v1 v2 (level dword +0x480, editor settings dword +0x484)
NAMEFN_RVA = 0x151710
MAP_CONT, CONT_COUNT, MAP_HIDDEN, MAP_VISION = 0x10, 0x14, 0x41C, 0x480
MAX_LEVELS = 29
UNITCTRL, ARMY_VMT_RVA = 0xFC, 0x130EC
ARMY_UPDATE_RVA, ARMY_UPDATE_B0 = 0x8D1B0, 0x83D88B53      # 53 8B D8 83
UPDVIS_RVA, UPDVIS_B0 = 0x78408, 0xC4835653                # 53 56 83 C4
LV_LBL_TOP, LV_BOX_TOP, LV_BOX_H = 10, 30, 336        # one-line caption: list right under it, down to the hint line (y 372)
TAB = "Map Level Vision"
HEAD = "Night Vision required?"
HINT = "Exploration sites always require Night Vision."

IMPORTS = {}


def data(D):
    for n in ("g_lvbox", "g_lvcnt", "g_lvmap", "g_lvname", "g_lvn", "g_lvitems"):
        D.var(n)
    D.var("g_lvid", 32)
    D.add("t_lvtab", BL._ansi(TAB))
    D.add("t_lvhead", BL._ansi(HEAD))
    D.add("t_lvhint", BL._ansi(HINT))


def asm(v, a, imp, GD):
    t = lambda n: "%#x" % (int(a(n), 16) + 8)          # noqa: E731
    return f"""
    lv_build:
        push esi
        push edi
        xor eax, eax
        mov {v('g_lvbox')}, eax
        mov {v('g_lvcnt')}, eax
        mov {v('g_lvmap')}, eax
        lea eax, [ebp + {a('s_blaowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz lvb_out
        cmp dword ptr [eax + {INSTSIZE_RVA:#x}], {INSTSIZE_WANT:#x}
        jne lvb_out
        lea ecx, [eax + {NAMEFN_RVA:#x}]
        cmp byte ptr [ecx], 0xe8
        jne lvb_out
        mov {v('g_lvname')}, ecx
        lea eax, [ebp + {a('s_blvcl')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz lvb_out
        lea edi, [eax + {BL.SPC_RVA:#x}]
        cmp dword ptr [edi], {BL.SPC_B0:#x}
        jne lvb_out
        cmp dword ptr [edi + 0x4], {BL.SPC_B1:#x}
        jne lvb_out
        mov eax, dword ptr [{IAT_HSMAP:#x}]
        mov eax, dword ptr [eax]
        test eax, eax
        jz lvb_out
        mov ecx, dword ptr [eax + {MAP_CONT:#x}]
        test ecx, ecx
        jz lvb_out
        mov ecx, dword ptr [ecx + {CONT_COUNT:#x}]
        mov {v('g_lvn')}, ecx
        mov {v('g_lvmap')}, eax
        mov eax, dword ptr [ebx + {BL.F_PAGECTL:#x}]
        test eax, eax
        jz lvb_out
        mov eax, dword ptr [{BL.IAT_TABSHEET:#x}]
        mov dl, 0x1
        mov ecx, ebx
        call dword ptr [eax + {BL.V_CREATE:#x}]
        mov esi, eax
        mov edx, dword ptr [ebx + {BL.F_PAGECTL:#x}]
        call edi
        mov eax, esi
        lea edx, [ebp + {t('t_lvtab')}]
        mov ecx, {BL.T_SETTEXT:#x}
        call ecx
        push 0x1b2
        mov eax, {BL.COL1:#x}
        mov ecx, {LV_LBL_TOP:#x}
        lea edx, [ebp + {t('t_lvhead')}]
        call bl_label
        push 0x1b2
        mov eax, {BL.COL1:#x}
        mov ecx, {BL.HINT_TOP:#x}
        lea edx, [ebp + {t('t_lvhint')}]
        call bl_label
        mov eax, {BL.COL1:#x}
        call bl_box
        mov {v('g_lvbox')}, eax
        push {BL.BOX_W:#x}
        push {LV_BOX_H:#x}
        mov ecx, {LV_BOX_TOP:#x}
        mov edx, {BL.COL1:#x}
        mov edi, dword ptr [eax]
        call dword ptr [edi + {BL.V_SETBOUNDS:#x}]
        xor edi, edi
    lvb_l:
        cmp edi, {MAX_LEVELS:#x}
        jae lvb_out
        mov eax, edi
        test eax, eax
        jnz lvb_p1
        mov eax, 0x3
        jmp lvb_lv
    lvb_p1:
        cmp eax, 0x3
        ja lvb_lv
        dec eax
    lvb_lv:
        cmp eax, {v('g_lvn')}
        jae lvb_next
        mov ecx, {v('g_lvmap')}
        mov ecx, dword ptr [ecx + {MAP_HIDDEN:#x}]
        bt ecx, eax
        jc lvb_next
        push eax
        call {v('g_lvname')}
        test eax, eax
        jz lvb_skip
        mov edx, eax
        mov eax, {v('g_lvbox')}
        mov eax, dword ptr [eax + {BL.LB_ITEMS:#x}]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {BL.V_ADD:#x}]
        pop eax
        mov ecx, {v('g_lvcnt')}
        mov byte ptr [ebp + ecx + {a('g_lvid')}], al
        xor edx, edx
        test eax, eax
        jz lvb_d
        cmp eax, 0x3
        je lvb_d
        inc edx
    lvb_d:
        mov ecx, {v('g_lvmap')}
        mov ecx, dword ptr [ecx + {MAP_VISION:#x}]
        bt ecx, eax
        jnc lvb_e
        xor edx, 0x1
    lvb_e:
        mov cl, dl
        mov edx, {v('g_lvcnt')}
        mov eax, {v('g_lvbox')}
        call dword ptr [{BL.IAT_SETCHECKED:#x}]
        inc {v('g_lvcnt')}
        jmp lvb_next
    lvb_skip:
        pop eax
    lvb_next:
        inc edi
        jmp lvb_l
    lvb_out:
        pop edi
        pop esi
        ret

    lv_store:
        cmp {v('g_lvbox')}, 0x0
        je lvs_out
        cmp {v('g_lvcnt')}, 0x0
        je lvs_out
        mov eax, dword ptr [{IAT_HSMAP:#x}]
        mov eax, dword ptr [eax]
        test eax, eax
        jz lvs_out
        cmp eax, {v('g_lvmap')}
        jne lvs_out
        push ebx
        push esi
        push edi
        mov edi, eax
        mov esi, dword ptr [edi + {MAP_VISION:#x}]
        xor ebx, ebx
    lvs_l:
        cmp ebx, {v('g_lvcnt')}
        jae lvs_done
        mov edx, ebx
        mov eax, {v('g_lvbox')}
        call dword ptr [{BL.IAT_GETCHECKED:#x}]
        movzx ecx, byte ptr [ebp + ebx + {a('g_lvid')}]
        xor edx, edx
        test ecx, ecx
        jz lvs_d
        cmp ecx, 0x3
        je lvs_d
        inc edx
    lvs_d:
        test al, al
        setnz al
        movzx eax, al
        xor eax, edx
        btr esi, ecx
        test eax, eax
        jz lvs_n
        bts esi, ecx
    lvs_n:
        inc ebx
        jmp lvs_l
    lvs_done:
        cmp esi, dword ptr [edi + {MAP_VISION:#x}]
        je lvs_pop
        mov dword ptr [edi + {MAP_VISION:#x}], esi
        call lv_refresh
    lvs_pop:
        pop edi
        pop esi
        pop ebx
    lvs_out:
        ret

    lv_refresh:
        push ebx
        push esi
        lea eax, [ebp + {a('s_blaowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz lvr_out
        mov esi, eax
        cmp dword ptr [esi + {ARMY_UPDATE_RVA:#x}], {ARMY_UPDATE_B0:#x}
        jne lvr_out
        cmp dword ptr [esi + {UPDVIS_RVA:#x}], {UPDVIS_B0:#x}
        jne lvr_out
        mov eax, dword ptr [edi + {UNITCTRL:#x}]
        test eax, eax
        jz lvr_vis
        mov eax, dword ptr [eax + 0x10]
        test eax, eax
        jz lvr_vis
        mov ebx, dword ptr [eax + 0x8]
        mov eax, dword ptr [eax + 0x4]
        mov {v('g_lvitems')}, eax
        test eax, eax
        jz lvr_vis
    lvr_l:
        dec ebx
        js lvr_vis
        mov eax, {v('g_lvitems')}
        mov eax, dword ptr [eax + ebx*4]
        test eax, eax
        jz lvr_l
        mov eax, dword ptr [eax + 0x4]
        test eax, eax
        jz lvr_l
        lea ecx, [esi + {ARMY_VMT_RVA:#x}]
        cmp dword ptr [eax], ecx
        jne lvr_l
        lea ecx, [esi + {ARMY_UPDATE_RVA:#x}]
        call ecx
        jmp lvr_l
    lvr_vis:
        mov eax, edi
        lea ecx, [esi + {UPDVIS_RVA:#x}]
        call ecx
    lvr_out:
        pop esi
        pop ebx
        ret
    """
