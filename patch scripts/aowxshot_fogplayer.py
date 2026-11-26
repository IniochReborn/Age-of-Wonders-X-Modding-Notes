#!/usr/bin/env python3
r"""
AoWxShot.dll module: the editor's Fog of War shows the vision of the player picked in the Players menu (2026-11-22).

User: "the Fog of War always shows the vision range of independents. i want it to show the vision range of whichever
Player is currently selected".

RE (AoWDevX.exe, fixed base):
  * fog is drawn for the map's SEATED player, byte [map+0xA5] (TAbstractAoWHSMap.DrawFog); the editor sets it to 0
    (Independents) once, when a map is opened (0x4211CE: map VMT+0xF8 with edx = 0), and never again.
  * the Players menu (DefaultPlayersMI [form+0x57C]) is rebuilt at 0x428979; its items carry the player index in Tag
    and share the OnClick 0x428944, which stores the pick in byte [map+0x190]: `mov [edx+0x190], al` @0x428964.
  * FogofWarClick 0x42BB64 ends in `call [ecx+0x100]` @0x42BB94 = map.SetFogEnabled(eax map, dl on/off), which only
    stores [map+0xC8] and invalidates the map.
Two in-memory patches made by Init -> `fpinit` (bytes verified first; both must match or nothing is touched):
  0x42BB94  ff 91 00 01 00 00 -> call fp_fog / nop : seated := fog on ? [map+0x190] : 0, then the original SetFogEnabled.
  0x428964  88 82 90 01 00 00 -> call fp_pick / nop: the original store; when fog is on, seated := the new pick and the
            map is redrawn (SetFogEnabled off + on - it invalidates only on a change).
v2 (user 11/22: "didnt work. its still showing independent vision"): the fog picture is NOT computed from the seated
byte at draw time - every hex keeps an unfog counter (field +0x1A) that armies / structures feed ONLY for the seated
player (TArmy.UpdateUnfog 0x5578E228 compares [army+0x12] with [map+0xA5], remembers its radius in [army+0x17]).  The
engine rebuilds them in TAoWHSMap.SeatedPlayerChanged (AoWEPACK RVA 0x76294: events 0x20020006 / 0x20020009 to every
map object -> TArmy / TStructure / TCity ... MsgProc redo their unfog) - what TPlayerControl.SetSeatedPlayer 0x557559C8
calls after storing the byte.  `fp_seat` does the same: store the byte, call SeatedPlayerChanged (first 4 bytes
verified; AoWEPACK base = the exe's AoWE.AoWHSMap import [0x43289C] - 0x1FA040).  ResetSeatedPlayerView (the other half
of SetSeatedPlayer) is left out on purpose: it would jump the view to that player's leader.
With fog off the seated player is 0 again, exactly the editor's own state, so nothing else in the editor changes.
"""
SITE_FOG, FOG_BYTES = 0x42BB94, bytes.fromhex("ff9100010000")
SITE_PICK, PICK_BYTES = 0x428964, bytes.fromhex("888290010000")
MAP_PICK, MAP_SEATED, MAP_FOGON, V_SETFOG = 0x190, 0xA5, 0xC8, 0x100
IAT_HSMAP, HSMAP_RVA = 0x43289C, 0x1FA040
SEATCHG_RVA, SEATCHG_B0 = 0x76294, 0xC4835653            # TAoWHSMap.SeatedPlayerChanged: 53 56 83 C4

IMPORTS = {}


def data(D):
    D.var("g_fpold")


def asm(v, a, imp, GD):
    import struct
    f0, f1 = struct.unpack("<IH", FOG_BYTES)
    p0, p1 = struct.unpack("<IH", PICK_BYTES)
    return f"""
    fpinit:
        mov edi, {SITE_FOG:#x}
        cmp dword ptr [edi], {f0:#x}
        jne fpi_out
        cmp word ptr [edi + 0x4], {f1:#x}
        jne fpi_out
        mov esi, {SITE_PICK:#x}
        cmp dword ptr [esi], {p0:#x}
        jne fpi_out
        cmp word ptr [esi + 0x4], {p1:#x}
        jne fpi_out
        lea eax, [ebp + {a('g_fpold')}]
        push eax
        push 0x40
        push 0x6
        push edi
        call {imp('VirtualProtect')}
        test eax, eax
        jz fpi_out
        lea eax, [ebp + {a('g_fpold')}]
        push eax
        push 0x40
        push 0x6
        push esi
        call {imp('VirtualProtect')}
        test eax, eax
        jz fpi_out
        lea eax, [ebp + fp_fog]
        sub eax, edi
        sub eax, 0x5
        mov byte ptr [edi], 0xe8
        mov dword ptr [edi + 0x1], eax
        mov byte ptr [edi + 0x5], 0x90
        lea eax, [ebp + fp_pick]
        sub eax, esi
        sub eax, 0x5
        mov byte ptr [esi], 0xe8
        mov dword ptr [esi + 0x1], eax
        mov byte ptr [esi + 0x5], 0x90
    fpi_out:
        ret

    fp_fog:
        push ecx
        mov cl, 0x0
        test dl, dl
        jz fpf_set
        mov cl, byte ptr [eax + {MAP_PICK:#x}]
    fpf_set:
        call fp_seat
        pop ecx
        jmp dword ptr [ecx + {V_SETFOG:#x}]

    fp_seat:
        cmp cl, byte ptr [eax + {MAP_SEATED:#x}]
        je fps_out
        mov byte ptr [eax + {MAP_SEATED:#x}], cl
        pushal
        mov edx, dword ptr [{IAT_HSMAP:#x}]
        sub edx, {HSMAP_RVA - SEATCHG_RVA:#x}
        cmp dword ptr [edx], {SEATCHG_B0:#x}
        jne fps_skip
        call edx
    fps_skip:
        popal
    fps_out:
        ret

    fp_pick:
        mov byte ptr [edx + {MAP_PICK:#x}], al
        cmp byte ptr [edx + {MAP_FOGON:#x}], 0x0
        je fpp_out
        push ebx
        mov ebx, edx
        mov cl, al
        mov eax, ebx
        call fp_seat
        mov eax, ebx
        xor edx, edx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {V_SETFOG:#x}]
        mov eax, ebx
        mov dl, 0x1
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {V_SETFOG:#x}]
        pop ebx
    fpp_out:
        ret
    """
