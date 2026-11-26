#!/usr/bin/env python3
r"""
AoWxShot.dll module: random city names in the editor + Map Settings -> "City Names" tab (2026-11-22).

User: a random city-name generator for the editor.  The name list is  Dict\xCityNamesV.mld  ("Vanilla AoW", built by
build_citynames_vanilla.py: one record per name, Original = name, ClassName = category "Human".."Undead" / "Random").
  * a city placed in the editor is a random-race city called "Noname" -> it gets a name from the Random category;
  * when its race is changed the name becomes one of the new race's names - unless the mapmaker has renamed the city;
  * Map Settings gets a tab "City Names": tick "Randomly generate city names" (default on), a "City Name List"
    drop-down (one entry for now, "Vanilla AoW"; more lists later), a button "Update Nameless" that asks
    'Update all cities named "Noname" with randomly generated names?' (Yes / No).

"Renamed by the mapmaker" is decided from the name itself, so it survives saving and reopening: a name counts as
automatic when it is "Noname" (any case) or empty, or when it is in the list under the city's CURRENT race category.
Anything else is the mapmaker's and is never replaced.

Engine facts (AoWEPACK.dll, patched IN MEMORY in the editor process only - the game never loads this DLL):
  City.TCity.Create 0x557A952C: race byte [city+0x45] := 0xFF (random), name [city+0x48] := Translate(NonameRStr) via
    `call System.@LStrAsg` @0x557A959B (e8, target thunk 0x55701150)  -> call cn_create: same call, but with a random
    "Random" name as the source when the generator is on.  (Cities created while a map LOADS get one too and the
    stream then overwrites it - harmless.)  _LStrAsg copies a source whose refcount is -1, so the DLL hands out its
    names as "literals" from one static buffer.
  City.TCity.SetRace 0x557AC990 (`53 8B D8 3A 53 45`, eax city, dl race; the city dialog's OK calls SetName first and
    then city VMT+0x244 = SetRace)  -> jmp cn_setrace: when the race really changes, the generator is on and the
    name is automatic, TCity.SetName (0x557AC92C) with a name of the new category; then the original routine.
  Race byte: 0..11 = Human, Azrac, Lizardman, Frostling, Elf, Halfling, Dwarf, Highman, Dark Elf, Orc, Goblin,
    Undead; negative (and anything else) = Random.
  Cities of the map (Update Nameless): [map+0x140] TPlayerList -> [+8] TList -> every player's structure list
    [player+0x1C] -> [+8] TList; a structure is a city when its VMT is City..TCity (RVA 0xA73F0).
v2 (user 11/22: "when i change its race, the name doesnt change accordingly"): the city dialog applies the race LIVE -
  its race combo's OnChange 0x4191AC calls city VMT+0x244 @0x4191DA (`ff 91 44 02 00 00`; ebx = form, city =
  [form+0x20C]) - so the rename happened there, but the dialog's name edit [form+0x234] kept the old text and OK
  (0x4192B0: SetName(city, edit text) first) put the old name back.  That call now goes to cn_racecb: the edit text is
  applied to the city first (so a name the mapmaker has just typed is what the "automatic?" test sees), then the
  original SetRace, and when the city's name changed the edit box is given the new name.
Settings (patch_levelvision_v1 v2): dword TAoWHSMap +0x484, bit 0 = generator OFF, bits 8..15 = list index.  Without
that storage (InstanceSize dword RVA 0xE858 != 0x488) there is no tab and the generator is simply on.
Tab controls: TCheckBox [0x432638] (SetChecked thunk 0x401AB0 eax,dl / GetChecked 0x401AA8), TComboBox [0x432640]
(items +0x118, Add VMT+0x34; SetItemIndex 0x401A98 / GetItemIndex 0x401A90; drop-down-list style through
StdCtrls.TCustomComboBox.SetStyle = VCL30 RVA 0x50760, dl = 2, first bytes verified), TButton [0x43263C] with OnClick
(+0xA4 code / +0xA8 data).  Built from the Ban List hooks: bl_fcwrap -> cn_build, bl_ok -> cn_store.
"""
import struct
import aowxshot_banlist as BL

IAT_HSMAP = 0x43289C
IAT_CHECKBOX, IAT_BUTTON, IAT_COMBO = 0x432638, 0x43263C, 0x432640
T_SETCHECKED, T_GETCHECKED, T_SETITEMINDEX, T_GETITEMINDEX = 0x401AB0, 0x401AA8, 0x401A98, 0x401A90
ON_CLICK = 0xA4
SITE_RACECB, RACECB_B0, F_NAMEEDIT, V_SETRACE = 0x4191DA, 0x024491FF, 0x234, 0x244      # ff 91 44 02 | 00 00
T_GETTEXT, T_CITY_SETNAME, T_LSTRCLR = 0x401560, 0x402930, 0x4010B0
# AoWEPACK.dll RVAs
INSTSIZE_RVA, INSTSIZE_WANT, HSMAP_RVA = 0xE858, 0x488, 0x1FA040
CREATE_CALL_RVA, LSTRASG_THUNK_RVA = 0xA959B, 0x1150
SETRACE_RVA, SETRACE_B0, SETRACE_W4, SETRACE_BACK_RVA = 0xAC990, 0x3AD88B53, 0x4553, 0xAC996
SETNAME_RVA, CITY_VMT_RVA = 0xAC92C, 0xA73F0
CITY_RACE, CITY_NAME, MAP_SET, MAP_PLAYERS, PLAYER_STRUCTS = 0x45, 0x48, 0x484, 0x140, 0x1C
# VCL30.dpl
SETSTYLE_RVA, SETSTYLE_B0 = 0x50760, 0x3AD88B53            # 53 8B D8 3A
CATS = ["Human", "Azrac", "Lizardman", "Frostling", "Elf", "Halfling", "Dwarf", "Highman", "Dark Elf", "Orc", "Goblin", "Undead", "Random"]
RANDOM_CAT = 12
LISTS = ["Vanilla AoW"]
REL_PATH = "Dict\\xCityNamesV.mld"
TAB, CHK, LBL, BTN = "City Names", "Randomly generate city names", "City Name List", "Update Nameless"
ASK = 'Update all cities named "Noname" with randomly generated names?'

IMPORTS = {"kernel32.dll": ["GetModuleFileNameA", "CreateFileA", "GetFileSize", "ReadFile", "CloseHandle"]}   # GetTickCount, VirtualAlloc,
# VirtualProtect, lstrcmpiA, MessageBoxA, GetActiveWindow are already imported by the other modules


def data(D):
    for n in ("g_cnbuf", "g_cnrecs", "g_cnend", "g_cncount", "g_cnskip", "g_cnseed", "g_cntried", "g_cnchk", "g_cncombo",
              "g_cnmap", "g_cnbase", "g_cnold", "g_cncat", "g_cnq", "g_cnqlen"):
        D.var(n)
    D.var("g_cnname", 80)
    D.var("g_cnpath", 400)
    D.add("t_cncat", b"".join((bytes([len(c)]) + c.encode("latin1")).ljust(16, b"\0") for c in CATS))
    D.s("s_cnrel", REL_PATH)
    D.s("s_cnnoname", "Noname")
    D.s("s_cnask", ASK)
    D.s("s_cncap", BTN)
    D.add("t_cntab", BL._ansi(TAB))
    D.add("t_cnchk", BL._ansi(CHK))
    D.add("t_cnlbl", BL._ansi(LBL))
    D.add("t_cnbtn", BL._ansi(BTN))
    for i, name in enumerate(LISTS):
        D.add("t_cnlist%d" % i, BL._ansi(name))


def asm(v, a, imp, GD):
    t = lambda n: "%#x" % (int(a(n), 16) + 8)          # noqa: E731
    add_lists = "".join(f"""
        mov eax, {v('g_cncombo')}
        mov eax, dword ptr [eax + {BL.LB_ITEMS:#x}]
        lea edx, [ebp + {t('t_cnlist%d' % i)}]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {BL.V_ADD:#x}]""" for i in range(len(LISTS)))
    return f"""
    cninit:
        lea eax, [ebp + {a('s_blaowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz cni_out
        mov {v('g_cnbase')}, eax
        lea edi, [eax + {CREATE_CALL_RVA:#x}]
        cmp byte ptr [edi], 0xe8
        jne cni_out
        mov ecx, dword ptr [edi + 0x1]
        lea ecx, [edi + ecx + 0x5]
        lea edx, [eax + {LSTRASG_THUNK_RVA:#x}]
        cmp ecx, edx
        jne cni_out
        lea esi, [eax + {SETRACE_RVA:#x}]
        cmp dword ptr [esi], {SETRACE_B0:#x}
        jne cni_out
        cmp word ptr [esi + 0x4], {SETRACE_W4:#x}
        jne cni_out
        lea eax, [ebp + {a('g_cnold')}]
        push eax
        push 0x40
        push 0x5
        push edi
        call {imp('VirtualProtect')}
        test eax, eax
        jz cni_out
        lea eax, [ebp + {a('g_cnold')}]
        push eax
        push 0x40
        push 0x6
        push esi
        call {imp('VirtualProtect')}
        test eax, eax
        jz cni_out
        lea eax, [ebp + cn_create]
        sub eax, edi
        sub eax, 0x5
        mov dword ptr [edi + 0x1], eax
        lea eax, [ebp + cn_setrace]
        sub eax, esi
        sub eax, 0x5
        mov byte ptr [esi], 0xe9
        mov dword ptr [esi + 0x1], eax
        mov byte ptr [esi + 0x5], 0x90
        mov edi, {SITE_RACECB:#x}
        cmp dword ptr [edi], {RACECB_B0:#x}
        jne cni_out
        cmp word ptr [edi + 0x4], 0x0
        jne cni_out
        lea eax, [ebp + {a('g_cnold')}]
        push eax
        push 0x40
        push 0x6
        push edi
        call {imp('VirtualProtect')}
        test eax, eax
        jz cni_out
        lea eax, [ebp + cn_racecb]
        sub eax, edi
        sub eax, 0x5
        mov byte ptr [edi], 0xe8
        mov dword ptr [edi + 0x1], eax
        mov byte ptr [edi + 0x5], 0x90
    cni_out:
        ret

    cn_racecb:
        push edi
        push edx
        mov edi, eax
        push 0x0
        mov eax, dword ptr [ebx + {F_NAMEEDIT:#x}]
        test eax, eax
        jz crc_ns
        mov edx, esp
        mov ecx, {T_GETTEXT:#x}
        call ecx
        mov edx, dword ptr [esp]
        mov eax, edi
        mov ecx, {T_CITY_SETNAME:#x}
        call ecx
    crc_ns:
        mov eax, esp
        mov ecx, {T_LSTRCLR:#x}
        call ecx
        add esp, 0x4
        pop edx
        push dword ptr [edi + {CITY_NAME:#x}]
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {V_SETRACE:#x}]
        pop eax
        mov edx, dword ptr [edi + {CITY_NAME:#x}]
        cmp edx, eax
        je crc_out
        mov eax, dword ptr [ebx + {F_NAMEEDIT:#x}]
        test eax, eax
        jz crc_out
        mov ecx, {BL.T_SETTEXT:#x}
        call ecx
    crc_out:
        pop edi
        ret

    cn_enabled:
        mov eax, {v('g_cnbase')}
        test eax, eax
        jz cne_no
        cmp dword ptr [eax + {INSTSIZE_RVA:#x}], {INSTSIZE_WANT:#x}
        jne cne_yes
        mov eax, dword ptr [eax + {HSMAP_RVA:#x}]
        test eax, eax
        jz cne_yes
        test byte ptr [eax + {MAP_SET:#x}], 0x1
        jnz cne_no
    cne_yes:
        mov eax, 0x1
        ret
    cne_no:
        xor eax, eax
        ret

    cn_cat:
        movsx eax, al
        cmp eax, {RANDOM_CAT - 1:#x}
        jbe cnc_out
        mov eax, {RANDOM_CAT:#x}
    cnc_out:
        ret

    cn_load:
        cmp {v('g_cnbuf')}, 0x0
        jne cnl_ok
        cmp {v('g_cntried')}, 0x0
        jne cnl_no
        mov {v('g_cntried')}, 0x1
        push esi
        push edi
        push ebx
        push 0x104
        lea eax, [ebp + {a('g_cnpath')}]
        push eax
        push 0x0
        call {imp('GetModuleFileNameA')}
        test eax, eax
        jz cnl_fail
        lea edx, [ebp + {a('g_cnpath')}]
        add eax, edx
    cnl_bs:
        cmp eax, edx
        jbe cnl_fail
        dec eax
        cmp byte ptr [eax], 0x5c
        jne cnl_bs
        inc eax
        lea edx, [ebp + {a('s_cnrel')}]
    cnl_cp:
        mov cl, byte ptr [edx]
        mov byte ptr [eax], cl
        inc eax
        inc edx
        test cl, cl
        jnz cnl_cp
        push 0x0
        push 0x80
        push 0x3
        push 0x0
        push 0x1
        push 0x80000000
        lea eax, [ebp + {a('g_cnpath')}]
        push eax
        call {imp('CreateFileA')}
        cmp eax, 0xffffffff
        je cnl_fail
        mov esi, eax
        push 0x0
        push esi
        call {imp('GetFileSize')}
        mov edi, eax
        xor ebx, ebx
        cmp edi, 0x2a
        jb cnl_close
        cmp edi, 0x400000
        ja cnl_close
        push 0x4
        push 0x3000
        lea eax, [edi + 0x10]
        push eax
        push 0x0
        call {imp('VirtualAlloc')}
        test eax, eax
        jz cnl_close
        mov ebx, eax
        push 0x0
        lea ecx, [ebp + {a('g_cnold')}]
        push ecx
        push edi
        push ebx
        push esi
        call {imp('ReadFile')}
        test eax, eax
        jnz cnl_close
        xor ebx, ebx
    cnl_close:
        push esi
        call {imp('CloseHandle')}
        test ebx, ebx
        jz cnl_fail
        cmp {v('g_cnold')}, edi
        jne cnl_fail
        cmp dword ptr [ebx], 0x03444c4d
        jne cnl_fail
        cmp byte ptr [ebx + 0x6], 0x1
        jne cnl_fail
        movzx ecx, word ptr [ebx + 0xc]
        test ecx, ecx
        jz cnl_fail
        mov {v('g_cnskip')}, ecx
        movzx ecx, word ptr [ebx + 0x12]
        mov {v('g_cncount')}, ecx
        mov ecx, dword ptr [ebx + 0x14]
        cmp ecx, edi
        jae cnl_fail
        add ecx, ebx
        mov {v('g_cnrecs')}, ecx
        lea ecx, [ebx + edi]
        mov {v('g_cnend')}, ecx
        mov {v('g_cnbuf')}, ebx
        pop ebx
        pop edi
        pop esi
    cnl_ok:
        mov eax, 0x1
        ret
    cnl_fail:
        pop ebx
        pop edi
        pop esi
    cnl_no:
        xor eax, eax
        ret

    cn_scan:
        push ebx
        push esi
        push edi
        push eax
        push edx
        xor ebx, ebx
        mov esi, {v('g_cnrecs')}
        mov edi, {v('g_cncount')}
    cns_r:
        test edi, edi
        jz cns_end
        dec edi
        mov eax, {v('g_cnend')}
        sub eax, esi
        cmp eax, 0x4
        jl cns_end
        movzx ecx, word ptr [esi]
        lea eax, [esi + 0x2]
        lea esi, [esi + ecx + 0x2]
        push eax
        push ecx
        mov eax, {v('g_cnend')}
        sub eax, esi
        cmp eax, 0x2
        jl cns_end2
        movzx ecx, word ptr [esi]
        lea edx, [esi + 0x2]
        lea esi, [esi + ecx + 0x2]
        mov eax, {v('g_cnskip')}
    cns_s:
        test eax, eax
        jz cns_sd
        push eax
        mov eax, {v('g_cnend')}
        sub eax, esi
        cmp eax, 0x2
        pop eax
        jl cns_end2
        push ecx
        movzx ecx, word ptr [esi]
        lea esi, [esi + ecx + 0x2]
        pop ecx
        dec eax
        jmp cns_s
    cns_sd:
        cmp esi, {v('g_cnend')}
        ja cns_end2
        test ecx, ecx
        jz cns_next
        mov eax, {v('g_cncat')}
        movzx eax, byte ptr [eax]
        cmp eax, ecx
        jne cns_next
        push esi
        push edi
        mov esi, edx
        mov edi, {v('g_cncat')}
        inc edi
        repe cmpsb
        pop edi
        pop esi
        jne cns_next
        mov eax, dword ptr [esp + 0xc]
        cmp eax, 0x2
        je cns_m2
        cmp eax, 0x1
        je cns_m1
        inc ebx
        jmp cns_next
    cns_m1:
        cmp ebx, dword ptr [esp + 0x8]
        je cns_take
        inc ebx
        jmp cns_next
    cns_take:
        pop ecx
        pop eax
        cmp ecx, 0x3f
        jbe cns_t1
        mov ecx, 0x3f
    cns_t1:
        lea edi, [ebp + {a('g_cnname')}]
        mov dword ptr [edi], 0xffffffff
        mov dword ptr [edi + 0x4], ecx
        add edi, 0x8
        mov esi, eax
        rep movsb
        mov byte ptr [edi], 0x0
        mov eax, 0x1
        jmp cns_out
    cns_m2:
        mov ecx, dword ptr [esp]
        cmp ecx, {v('g_cnqlen')}
        jne cns_next
        test ecx, ecx
        jz cns_hit
        push esi
        push edi
        mov esi, dword ptr [esp + 0xc]
        mov edi, {v('g_cnq')}
        repe cmpsb
        pop edi
        pop esi
        jne cns_next
    cns_hit:
        add esp, 0x8
        mov eax, 0x1
        jmp cns_out
    cns_next:
        add esp, 0x8
        jmp cns_r
    cns_end2:
        add esp, 0x8
    cns_end:
        mov eax, ebx
        cmp dword ptr [esp + 0x4], 0x0
        je cns_out
        xor eax, eax
    cns_out:
        add esp, 0x8
        pop edi
        pop esi
        pop ebx
        ret

    cn_pick:
        push ebx
        shl eax, 0x4
        lea eax, [ebp + eax + {a('t_cncat')}]
        mov {v('g_cncat')}, eax
        call cn_load
        test eax, eax
        jz cnp_no
        xor eax, eax
        call cn_scan
        test eax, eax
        jz cnp_no
        mov ebx, eax
        mov eax, {v('g_cnseed')}
        test eax, eax
        jnz cnp_s
        call {imp('GetTickCount')}
        or eax, 0x1
    cnp_s:
        imul eax, eax, 0x343fd
        add eax, 0x269ec3
        mov {v('g_cnseed')}, eax
        shr eax, 0x10
        and eax, 0x7fff
        xor edx, edx
        div ebx
        mov eax, 0x1
        call cn_scan
        test eax, eax
        jz cnp_no
        lea eax, [ebp + {int(a('g_cnname'), 16) + 8:#x}]
        pop ebx
        ret
    cnp_no:
        xor eax, eax
        pop ebx
        ret

    cn_isauto:
        push ebx
        mov ebx, eax
        mov edx, dword ptr [ebx + {CITY_NAME:#x}]
        test edx, edx
        jz cna_yes
        lea eax, [ebp + {a('s_cnnoname')}]
        push eax
        push edx
        call {imp('lstrcmpiA')}
        test eax, eax
        jz cna_yes
        mov al, byte ptr [ebx + {CITY_RACE:#x}]
        call cn_cat
        shl eax, 0x4
        lea eax, [ebp + eax + {a('t_cncat')}]
        mov {v('g_cncat')}, eax
        call cn_load
        test eax, eax
        jz cna_no
        mov edx, dword ptr [ebx + {CITY_NAME:#x}]
        mov {v('g_cnq')}, edx
        mov eax, dword ptr [edx - 0x4]
        mov {v('g_cnqlen')}, eax
        mov eax, 0x2
        call cn_scan
        pop ebx
        ret
    cna_yes:
        mov eax, 0x1
        pop ebx
        ret
    cna_no:
        xor eax, eax
        pop ebx
        ret

    cn_create:
        push ebp
        call {GD:#x}
        push eax
        push edx
        call cn_enabled
        test eax, eax
        jz cnk_plain
        mov eax, {RANDOM_CAT:#x}
        call cn_pick
        test eax, eax
        jz cnk_plain
        mov dword ptr [esp], eax
    cnk_plain:
        pop edx
        pop eax
        mov ecx, {v('g_cnbase')}
        add ecx, {LSTRASG_THUNK_RVA:#x}
        pop ebp
        jmp ecx

    cn_setrace:
        push ebp
        call {GD:#x}
        push eax
        push edx
        push ebx
        push esi
        mov ebx, eax
        movzx esi, dl
        mov ecx, esi
        cmp cl, byte ptr [ebx + {CITY_RACE:#x}]
        je cnr_go
        call cn_enabled
        test eax, eax
        jz cnr_go
        mov eax, ebx
        call cn_isauto
        test eax, eax
        jz cnr_go
        mov eax, esi
        call cn_cat
        call cn_pick
        test eax, eax
        jz cnr_go
        mov edx, eax
        mov eax, ebx
        mov ecx, {v('g_cnbase')}
        add ecx, {SETNAME_RVA:#x}
        call ecx
    cnr_go:
        pop esi
        pop ebx
        pop edx
        pop eax
        mov ecx, {v('g_cnbase')}
        add ecx, {SETRACE_BACK_RVA:#x}
        pop ebp
        push ebx
        mov ebx, eax
        cmp dl, byte ptr [ebx + {CITY_RACE:#x}]
        jmp ecx

    cn_ctl:
        push edi
        mov dl, 0x1
        mov ecx, ebx
        call dword ptr [eax + {BL.V_CREATE:#x}]
        mov edi, eax
        mov edx, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {BL.V_SETPARENT:#x}]
        mov eax, dword ptr [edi]
        mov eax, dword ptr [eax + {BL.V_SETBOUNDS:#x}]
        push eax
        push dword ptr [esp + 0x18]
        push dword ptr [esp + 0x20]
        mov edx, dword ptr [esp + 0x18]
        mov ecx, dword ptr [esp + 0x1c]
        mov eax, edi
        call dword ptr [esp + 0x8]
        add esp, 0x4
        mov edx, dword ptr [esp + 0x8]
        test edx, edx
        jz cnt_nt
        mov eax, edi
        mov ecx, {BL.T_SETTEXT:#x}
        call ecx
    cnt_nt:
        mov eax, edi
        pop edi
        ret 0x14

    cn_build:
        push esi
        push edi
        xor eax, eax
        mov {v('g_cnchk')}, eax
        mov {v('g_cncombo')}, eax
        mov {v('g_cnmap')}, eax
        mov eax, {v('g_cnbase')}
        test eax, eax
        jz cnb_out
        cmp dword ptr [eax + {INSTSIZE_RVA:#x}], {INSTSIZE_WANT:#x}
        jne cnb_out
        lea eax, [ebp + {a('s_blvcl')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz cnb_out
        mov edi, eax
        cmp dword ptr [edi + {BL.SPC_RVA:#x}], {BL.SPC_B0:#x}
        jne cnb_out
        cmp dword ptr [edi + {BL.SPC_RVA + 4:#x}], {BL.SPC_B1:#x}
        jne cnb_out
        cmp dword ptr [edi + {SETSTYLE_RVA:#x}], {SETSTYLE_B0:#x}
        jne cnb_out
        mov eax, dword ptr [{IAT_HSMAP:#x}]
        mov eax, dword ptr [eax]
        test eax, eax
        jz cnb_out
        mov {v('g_cnmap')}, eax
        mov eax, dword ptr [ebx + {BL.F_PAGECTL:#x}]
        test eax, eax
        jz cnb_out
        mov eax, dword ptr [{BL.IAT_TABSHEET:#x}]
        mov dl, 0x1
        mov ecx, ebx
        call dword ptr [eax + {BL.V_CREATE:#x}]
        mov esi, eax
        mov edx, dword ptr [ebx + {BL.F_PAGECTL:#x}]
        lea ecx, [edi + {BL.SPC_RVA:#x}]
        call ecx
        mov eax, esi
        lea edx, [ebp + {t('t_cntab')}]
        mov ecx, {BL.T_SETTEXT:#x}
        call ecx
        push 0x11
        push 0x12c
        push 0xc
        push 0xc
        lea eax, [ebp + {t('t_cnchk')}]
        push eax
        mov eax, dword ptr [{IAT_CHECKBOX:#x}]
        call cn_ctl
        mov {v('g_cnchk')}, eax
        mov ecx, {v('g_cnmap')}
        test byte ptr [ecx + {MAP_SET:#x}], 0x1
        setz dl
        mov ecx, {T_SETCHECKED:#x}
        call ecx
        push 0xc8
        mov eax, 0xc
        mov ecx, 0x30
        lea edx, [ebp + {t('t_cnlbl')}]
        call bl_label
        push 0x15
        push 0xd2
        push 0x42
        push 0xc
        push 0x0
        mov eax, dword ptr [{IAT_COMBO:#x}]
        call cn_ctl
        mov {v('g_cncombo')}, eax
        mov dl, 0x2
        lea ecx, [edi + {SETSTYLE_RVA:#x}]
        call ecx{add_lists}
        mov ecx, {v('g_cnmap')}
        movzx edx, byte ptr [ecx + {MAP_SET + 1:#x}]
        cmp edx, {len(LISTS):#x}
        jb cnb_ix
        xor edx, edx
    cnb_ix:
        mov eax, {v('g_cncombo')}
        mov ecx, {T_SETITEMINDEX:#x}
        call ecx
        push 0x19
        push 0x82
        push 0x68
        push 0xc
        lea eax, [ebp + {t('t_cnbtn')}]
        push eax
        mov eax, dword ptr [{IAT_BUTTON:#x}]
        call cn_ctl
        lea ecx, [ebp + cn_update]
        mov dword ptr [eax + {ON_CLICK:#x}], ecx
        mov dword ptr [eax + {ON_CLICK + 4:#x}], ebx
    cnb_out:
        pop edi
        pop esi
        ret

    cn_store:
        cmp {v('g_cnchk')}, 0x0
        je cno_out
        mov eax, dword ptr [{IAT_HSMAP:#x}]
        mov eax, dword ptr [eax]
        test eax, eax
        jz cno_out
        cmp eax, {v('g_cnmap')}
        jne cno_out
        push esi
        mov esi, eax
        mov eax, {v('g_cnchk')}
        mov ecx, {T_GETCHECKED:#x}
        call ecx
        xor edx, edx
        test al, al
        jnz cno_c1
        inc edx
    cno_c1:
        push edx
        mov eax, {v('g_cncombo')}
        mov ecx, {T_GETITEMINDEX:#x}
        call ecx
        pop edx
        test eax, eax
        jns cno_c2
        xor eax, eax
    cno_c2:
        and eax, 0xff
        shl eax, 0x8
        or edx, eax
        mov dword ptr [esi + {MAP_SET:#x}], edx
        pop esi
    cno_out:
        ret

    cn_update:
        push ebp
        push ebx
        push esi
        push edi
        call {GD:#x}
        call {imp('GetActiveWindow')}
        push 0x24
        lea ecx, [ebp + {a('s_cncap')}]
        push ecx
        lea ecx, [ebp + {a('s_cnask')}]
        push ecx
        push eax
        call {imp('MessageBoxA')}
        cmp eax, 0x6
        jne cnu_out
        mov eax, dword ptr [{IAT_HSMAP:#x}]
        mov eax, dword ptr [eax]
        test eax, eax
        jz cnu_out
        mov eax, dword ptr [eax + {MAP_PLAYERS:#x}]
        test eax, eax
        jz cnu_out
        mov eax, dword ptr [eax + 0x8]
        test eax, eax
        jz cnu_out
        mov esi, dword ptr [eax + 0x4]
        mov edi, dword ptr [eax + 0x8]
        test esi, esi
        jz cnu_out
    cnu_pl:
        dec edi
        js cnu_out
        mov eax, dword ptr [esi + edi*4]
        test eax, eax
        jz cnu_pl
        mov eax, dword ptr [eax + {PLAYER_STRUCTS:#x}]
        test eax, eax
        jz cnu_pl
        mov eax, dword ptr [eax + 0x8]
        test eax, eax
        jz cnu_pl
        push esi
        push edi
        mov esi, dword ptr [eax + 0x4]
        mov edi, dword ptr [eax + 0x8]
        test esi, esi
        jz cnu_sd
    cnu_st:
        dec edi
        js cnu_sd
        mov ebx, dword ptr [esi + edi*4]
        test ebx, ebx
        jz cnu_st
        mov eax, {v('g_cnbase')}
        add eax, {CITY_VMT_RVA:#x}
        cmp dword ptr [ebx], eax
        jne cnu_st
        mov edx, dword ptr [ebx + {CITY_NAME:#x}]
        test edx, edx
        jz cnu_ren
        lea eax, [ebp + {a('s_cnnoname')}]
        push eax
        push edx
        call {imp('lstrcmpiA')}
        test eax, eax
        jnz cnu_st
    cnu_ren:
        mov al, byte ptr [ebx + {CITY_RACE:#x}]
        call cn_cat
        call cn_pick
        test eax, eax
        jz cnu_st
        mov edx, eax
        mov eax, ebx
        mov ecx, {v('g_cnbase')}
        add ecx, {SETNAME_RVA:#x}
        call ecx
        jmp cnu_st
    cnu_sd:
        pop edi
        pop esi
        jmp cnu_pl
    cnu_out:
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret
    """
