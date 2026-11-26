#!/usr/bin/env python3
r"""
"Wall of cities": cities may touch; shared crops go to the right city (2026-10-31).

User (mapmaker request): no spacing limit between cities from their crops; cities may touch wall-to-wall but not
overlap; no duplicated crop income - the larger city gets a shared crop; ties resolved gracefully (option A: nearer
city centre, then the city placed first); a city hex on another city's crop spot is no crop / no income.
RE (AoWEPACK Crops unit, see memory city-crop-spacing):
  * TPlayerCropStructure.CanPlace 0x557A6904: after TStructure.CanPlace (pad/footprint = no overlap) it refuses if
    any crop-pattern hex ([res+0x74] offsets) or its 6 neighbours holds another TPlayerCropStructure.
    -> 0x557A6947 jumps straight to the result (keeps TStructure.CanPlace + the [vmt+0x84] test).
  * TCrop.LinkToCropOwner 0x557A5DAC took the FIRST crop structure in a radius-1 spiral around the crop.  Rewritten
    (entry -> cave 0x558E0580 'CWL1', PIC): scan the crop hex + its 6 neighbours (same spiral helpers); a crop
    structure ON the crop hex -> no owner (no income); candidates = crop structures that are not razed (vmt+0x150)
    and have this hex in their crop pattern; best = city (TCity VMT in the parent chain) over farm, then larger size
    ([res+0x78], TCity.GetSize), then smaller hex distance from the crop to the structure's x/y (axial q=x,
    r=y-x/2), then lower unique id [struct+0x1C] (= placed first) -> SetCropOwner.  Fallback: if no candidate
    qualifies, the first adjacent structure (vanilla behaviour) so income can never vanish by mistake.
    Deterministic -> MP-safe.  Income stays single-counted (GetCropCount counts crops whose owner == self).
  * Re-check on change: TPlayerCropStructure.UpdateCropSettings 0x557A636C (run by TCity / TPlayerCropStructure
    .UpdateCrops on growth, raze, capture, activation) calls TCrop.UpdateSettings for every crop in its pattern ->
    retargeted @0x557A63E6 to LinkToCropOwner (which ends in SetCropOwner -> UpdateSettings).
Backup .bak_citywall (AoWEPACK.dll).  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_citywall"
CAVE, CAVE_END, MAGIC = 0x558E0580, 0x558E0800, b"CWL1"
LINK, LINK_ORIG = 0x557A5DAC, bytes.fromhex("53565755 83c4e0".replace(" ", ""))
PLACE, PLACE_ORIG, PLACE_TGT = 0x557A6947, bytes.fromhex("0fbe55088bc6"), 0x557A6A09
RELINK, RELINK_ORIG = 0x557A63E6, bytes.fromhex("e8ddf8ffff")
SPIRAL_INIT, SPIRAL_NEXT, GETFIELD, FINDOBJ, DECODE = 0x557026D4, 0x557026DC, 0x557020DC, 0x55702004, 0x55702694
SETOWNER = 0x557A5CBC
PCS_CELL, TCITY_VMT = 0x557A55F4, 0x557A73F0


def src(ph):
    return f"""
link:
    push ebx
    push esi
    push edi
    push ebp
    sub esp, 0x48
    mov ebp, eax
    call la
la:
    pop ecx
    add ecx, {ph & 0xFFFFFFFF:#x}
    mov dword ptr [esp + 0x20], ecx
    xor edi, edi
    mov dword ptr [esp + 0x3c], 0x0
    mov dword ptr [esp + 0x40], 0x0
    mov eax, dword ptr [ebp + 0x4]
    mov ebx, dword ptr [eax + 0x4]
    movsx ecx, byte ptr [ebp + 0x11]
    movsx edx, byte ptr [ebp + 0x10]
    mov eax, ebx
    call {GETFIELD:#x}
    mov edx, dword ptr [esp + 0x20]
    mov edx, dword ptr [edx + {PCS_CELL:#x}]
    call {FINDOBJ:#x}
    test eax, eax
    jz nocentre
    mov dword ptr [esp + 0x3c], 0x1
nocentre:
    push 0x1
    movsx ecx, byte ptr [ebp + 0x11]
    movsx edx, byte ptr [ebp + 0x10]
    lea eax, [esp + 0x4]
    call {SPIRAL_INIT:#x}
lp:
    cmp dword ptr [esp + 0xc], 0x1
    jg fin
    mov esi, dword ptr [esp + 0x10]
    test esi, esi
    jl nx
    cmp esi, dword ptr [ebx + 0xc]
    jge nx
    mov ecx, dword ptr [esp + 0x14]
    test ecx, ecx
    jl nx
    cmp ecx, dword ptr [ebx + 0x10]
    jge nx
    mov edx, esi
    mov eax, ebx
    call {GETFIELD:#x}
    mov edx, dword ptr [esp + 0x20]
    mov edx, dword ptr [edx + {PCS_CELL:#x}]
    call {FINDOBJ:#x}
    test eax, eax
    jz nx
    mov esi, eax
    cmp dword ptr [esp + 0xc], 0x0
    jne notc
    mov dword ptr [esp + 0x3c], 0x1
    jmp nx
notc:
    cmp dword ptr [esp + 0x40], 0x0
    jne havefirst
    mov dword ptr [esp + 0x40], esi
havefirst:
    mov eax, esi
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x150]
    test al, al
    jnz nx
    call inpat
    test al, al
    jz nx
    xor ecx, ecx
    mov eax, dword ptr [esi]
    mov edx, dword ptr [esp + 0x20]
    add edx, {TCITY_VMT:#x}
cls_lp:
    cmp eax, edx
    je iscity
    mov eax, dword ptr [eax - 0x18]
    test eax, eax
    jz cls_done
    mov eax, dword ptr [eax]
    test eax, eax
    jz cls_done
    jmp cls_lp
iscity:
    inc ecx
cls_done:
    xor edx, edx
    test ecx, ecx
    jz sz0
    mov eax, dword ptr [esi + 0x8]
    movzx edx, byte ptr [eax + 0x78]
sz0:
    push ecx
    push edx
    call hexdist
    pop edx
    pop ecx
    test edi, edi
    jz take
    cmp ecx, dword ptr [esp + 0x24]
    jg take
    jl nx
    cmp edx, dword ptr [esp + 0x28]
    jg take
    jl nx
    cmp eax, dword ptr [esp + 0x2c]
    jl take
    jg nx
    push eax
    mov eax, dword ptr [esi + 0x1c]
    cmp eax, dword ptr [esp + 0x34]
    pop eax
    jae nx
take:
    mov edi, esi
    mov dword ptr [esp + 0x24], ecx
    mov dword ptr [esp + 0x28], edx
    mov dword ptr [esp + 0x2c], eax
    mov eax, dword ptr [esi + 0x1c]
    mov dword ptr [esp + 0x30], eax
nx:
    mov eax, esp
    call {SPIRAL_NEXT:#x}
    jmp lp
fin:
    cmp dword ptr [esp + 0x3c], 0x0
    je nob
    xor edi, edi
    jmp setown
nob:
    test edi, edi
    jnz setown
    mov edi, dword ptr [esp + 0x40]
setown:
    mov edx, edi
    mov eax, ebp
    call {SETOWNER:#x}
    add esp, 0x48
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret

inpat:
    push ebx
    push edi
    sub esp, 0x8
    mov eax, dword ptr [esi + 0x8]
    mov eax, dword ptr [eax + 0x74]
    test eax, eax
    jz ip_no
    mov edi, dword ptr [eax + 0x8]
ip_lp:
    dec edi
    js ip_no
    lea eax, [esp]
    push eax
    lea eax, [esp + 0x8]
    push eax
    mov eax, dword ptr [esi + 0x8]
    mov eax, dword ptr [eax + 0x74]
    mov eax, dword ptr [eax + 0x4]
    movzx ecx, word ptr [eax + edi*2]
    movsx edx, byte ptr [esi + 0x11]
    movsx eax, byte ptr [esi + 0x10]
    call {DECODE:#x}
    movsx eax, byte ptr [ebp + 0x10]
    cmp eax, dword ptr [esp]
    jne ip_lp
    movsx eax, byte ptr [ebp + 0x11]
    cmp eax, dword ptr [esp + 0x4]
    jne ip_lp
    mov al, 0x1
    jmp ip_out
ip_no:
    xor eax, eax
ip_out:
    add esp, 0x8
    pop edi
    pop ebx
    ret

hexdist:
    push ebx
    movsx eax, byte ptr [esi + 0x10]
    movsx ecx, byte ptr [ebp + 0x10]
    movsx edx, byte ptr [esi + 0x11]
    movsx ebx, byte ptr [ebp + 0x11]
    push eax
    sar eax, 0x1
    sub edx, eax
    pop eax
    push ecx
    sar ecx, 0x1
    sub ebx, ecx
    pop ecx
    sub eax, ecx
    sub edx, ebx
    mov ecx, eax
    add ecx, edx
    mov ebx, eax
    sar ebx, 0x1f
    xor eax, ebx
    sub eax, ebx
    mov ebx, edx
    sar ebx, 0x1f
    xor edx, ebx
    sub edx, ebx
    mov ebx, ecx
    sar ebx, 0x1f
    xor ecx, ebx
    sub ecx, ebx
    add eax, edx
    add eax, ecx
    shr eax, 0x1
    pop ebx
    ret
"""


def epk_patches():
    probe = OV.asm(src(0x11111111), CAVE + 4)
    k = [i for i in range(len(probe) - 6) if probe[i] == 0x59 and probe[i + 1:i + 3] == b"\x81\xc1"][0]
    la_va = CAVE + 4 + k
    code = OV.asm(src(-la_va), CAVE + 4)
    assert len(code) == len(probe)
    z = MAGIC + code
    assert len(z) <= CAVE_END - CAVE, hex(len(z))
    return [(LINK, LINK_ORIG, b"\xe9" + struct.pack("<i", CAVE + 4 - (LINK + 5)) + b"\x90\x90"),
            (PLACE, PLACE_ORIG, b"\xe9" + struct.pack("<i", PLACE_TGT - (PLACE + 5)) + b"\x90"),
            (RELINK, RELINK_ORIG, b"\xe8" + struct.pack("<i", LINK - (RELINK + 5))),
            (CAVE, bytes(len(z)), z)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(); st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(SP.EPK, TAG)
    if not revert and not os.path.exists(bk):
        shutil.copy2(SP.EPK, bk)
    SP.write_bytes(SP.EPK, SP.EBASE, P, revert)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
