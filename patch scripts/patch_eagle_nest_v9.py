#!/usr/bin/env python3
r"""
Great Eagle's Nest v9 + machine Builders Guild art (2026-10-31) - on top of patch_eagle_nest_v8.

User (screenshot: Nest window/battle on grey ground, only the centre crop patch): "the crops should extend to the
rocks ... there is a second builders guild variant (the one that produces frost blower ram instead of flame
thrower ram) that reverts to default builders guild GFX on certain terrains. fix that".
  1. Crops missing: v6 made the Nest answer overlay 0 (mountain) from GetOverlay, which also turns its battles into
     mountain-terrain battles; a structure map's decor is re-mapped to the battle terrain by category (comb_res
     0x220167 field 17 = terrain group 1 GR/2 DE/3 SN/4 ST/5 WL/12 UG, field 18 = category, 9 = crops) and the
     crops had no equivalent there -> dropped.  v9 restores TBuildersGuild VMT+0x58 (TStructure.GetOverlay, the
     v6 'EGO1' cave stays as dead code) and moves the mountain rule into movement only:
     TBuildersGuild VMT+0xD0 CanMoveOn (TPlayerStructure.CanMoveOn 0x55761428; edx = {mc, field, state, slot},
     ecx = {cost, 0, stop}) -> cave 0x558E0440 'EGM1': run the original, then for the Nest (RID 0x00E16088) raise
     the cost to the army's mountain cost [mc + terrain*16 + 0x31] (overlay 0); 0xFF there (impassable) -> cost -1
     + stop, exactly like the enemy-structure block.
  2. Release.hss machine guilds (STR_BLDM / STR_BLDM2 = frames 0-2 normal, 3-5 snow, 6-8 desert, 9-11 razed):
     the frost-blower guild 694 used the default STR_BLDG art on terrains 2-5 and for razed -> slots 1-5, 12,
     22-27 copied from its twin 692 (the correct one); the Machinereum 285 and its underground guild 286 had the
     same mistakes in STR_BLDM2 (snow slot = an animation frame, razed = the snow / desert building) -> 692's slot
     layout with the ILB renamed to STR_BLDM2.
Backups .bak_eagle9 (AoWEPACK.dll, Release.hss).  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_eagle_nest_v2 as V2  # noqa: E402
import patch_eagle_nest_v6 as V6  # noqa: E402

TAG = ".bak_eagle9"
HSS = H.OURS
VMT = V6.VMT
OVL_SLOT, OVL_OLD, OVL_CAVE = 0x58, V6.OLD, V6.CAVE + 4
CMO_SLOT, CMO_OLD = 0xD0, 0x55761428
CAVE, CAVE_END, MAGIC = 0x558E0440, 0x558E04A0, b"EGM1"
TWIN = 692
FIX = {694: ("STR_BLDM.ILB", (1, 2, 3, 4, 5, 12, 22, 23, 24, 25, 26, 27)),
       285: ("STR_BLDM2.ILB", (1, 2, 3, 4, 5, 22, 23, 24, 25, 26, 27)),
       286: ("STR_BLDM2.ILB", (1, 2, 3, 4, 5, 12, 22, 23, 24, 25, 26, 27))}


def epk_patches():
    code = OV.asm(f"""
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov esi, edx
        mov edi, ecx
        call {CMO_OLD:#x}
        mov eax, dword ptr [ebx + 8]
        cmp dword ptr [eax + 0xc], {V2.RID:#x}
        jne done
        cmp dword ptr [edi], -1
        je done
        mov eax, dword ptr [esi + 4]
        movsx ecx, byte ptr [eax + 0x14]
        shl ecx, 4
        mov edx, dword ptr [esi]
        movsx eax, byte ptr [edx + ecx + 0x31]
        cmp eax, -1
        jne passable
        mov dword ptr [edi], -1
        mov byte ptr [edi + 8], 1
        jmp done
    passable:
        cmp eax, dword ptr [edi]
        jle done
        mov dword ptr [edi], eax
    done:
        pop edi
        pop esi
        pop ebx
        ret
    """, CAVE + 4)
    z = MAGIC + code
    assert len(z) <= CAVE_END - CAVE
    return [(VMT + OVL_SLOT, struct.pack("<I", OVL_CAVE), struct.pack("<I", OVL_OLD)),
            (VMT + CMO_SLOT, struct.pack("<I", CMO_OLD), struct.pack("<I", CAVE + 4)),
            (CAVE, bytes(len(z)), z)]


def renamed(seq, ilb):
    seq = copy.deepcopy(seq)
    s = seq
    while s is not None:
        if s["name"].upper().startswith("STR_BLDM"):
            s["name"] = ilb
        s = s.get("sub")
    return seq


def hss_build(b):
    A = H.parse(b)
    lists = {}
    for c in [TWIN] + list(FIX):
        r = bytes(A["recs"][c])
        fo, td = H.fields(r)
        assert struct.unpack_from("<I", r, 0)[0] == 0x2092F, c
        lists[c] = Q.parse_list(r, td + fo[9])[0]
    twin = lists[TWIN]
    assert twin[1]["name"].upper() == "STR_BLDM.ILB" and twin[22]["frame"] == 9
    changed = {}
    for c, (ilb, slots) in FIX.items():
        new = copy.deepcopy(lists[c])
        for i in slots:
            new[i] = renamed(twin[i], ilb)
        if new != lists[c]:
            changed[c] = R.rec_with_list(bytes(A["recs"][c]), new)
    if not changed:
        return None, []
    for c, v in changed.items():
        A["recs"][c] = bytearray(v)
    nb = SP.hss_rebuild(b, A)
    old = H.parse(b)["recs"]
    for c, v in H.parse(nb)["recs"].items():
        assert bytes(v) == (changed[c] if c in changed else bytes(old[c]))
    return nb, sorted(changed)


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(); st, bad = SP.state(d, pe, SP.EBASE, P)
    bad = [x for x in bad if int(x, 16) not in (VMT + OVL_SLOT, VMT + CMO_SLOT)]   # VMT slots: relocated pointers
    print("AoWEPACK %s relocs %s" % (st, bad or "none (VMT slot relocs expected)"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted AoWEPACK")
        bk = bak_path(HSS, TAG)
        if os.path.exists(bk):
            shutil.copy2(bk, HSS); print("restored", bk)
        return 0
    b = open(HSS, "rb").read(); nb, ch = hss_build(b)
    print("Release.hss", "already applied" if nb is None else "records %s" % ch)
    if nb is None and st[0] == "ours":
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if st[0] == "vanilla":
        bk = bak_path(SP.EPK, TAG)
        if not os.path.exists(bk):
            shutil.copy2(SP.EPK, bk)
        SP.write_bytes(SP.EPK, SP.EBASE, P, False)
    if nb is not None:
        bk = bak_path(HSS, TAG)
        if not os.path.exists(bk):
            shutil.copy2(HSS, bk)
        with open(HSS, "r+b") as fh:
            fh.write(nb); fh.truncate()
        assert open(HSS, "rb").read() == nb
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
