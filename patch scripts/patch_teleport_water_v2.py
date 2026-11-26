#!/usr/bin/env python3
r"""
Water teleporters v2 (2026-10-31) - on top of patch_teleport_water_v1 (art / hss / BORDER stay as v1 made them).

User: "water teleporter turns into land teleporter when placed on water, fix it".
Cause: TTeleportResource keeps res+0x44 = 1 (set by TStructureResource.Create) = pad-based structure; the pad turns
the hex under it into land, so the teleporter shows its land image.  TCaveResource.Create clears +0x44 (no pad,
generic placement) - that is why the water tunnels stay on water.
  * TTeleportResource.Create 0x557A550B (`mov dword [esi+60h],0C8h`) -> cave: same + `mov byte [esi+44h],0`.
    (Divine Gates share TTeleportResource -> also padless.)
  * The side-image getters (v1 caves read the terrain byte [self+0x18], which only the pad path stores) are re-done
    in cave 0x558E0900 'TWB2' reading the current image slot [self+0x14] (TerrainChanged writes
    GetTerrainTypeImage(terrain) there in both paths): slot 0 / 10 (water / cave water) -> tags 40/41/42.  The v1
    caves stay as dead code; the TTeleport VMT slots +0x138/+0x13C/+0x140 move from them to TWB2.
Backup .bak_telewater2 (AoWEPACK.dll).  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_teleport_water_v1 as V1  # noqa: E402

TAG = ".bak_telewater2"
CAVE, CAVE_END, MAGIC = 0x558E0900, 0x558E0A00, b"TWB2"
CREATE, CREATE_ORIG, CREATE_BACK = 0x557A550B, bytes.fromhex("c74660c8000000"), 0x557A5512


def v1_entries():
    P = V1.epk_patches()
    return {struct.unpack("<I", o)[0]: struct.unpack("<I", n)[0] for (a, o, n) in P[:3]}   # orig getter -> v1 cave


def epk_patches():
    v1 = v1_entries()
    P, at = [], CAVE + len(MAGIC)
    blob = bytearray(MAGIC)
    for slot, orig, tag in V1.GETTERS:
        c = OV.asm(f"""
            mov ecx, dword ptr [eax + 0x14]
            test ecx, ecx
            je w
            cmp ecx, 0xa
            jne o
        w:
            push ebx
            mov ebx, eax
            mov eax, dword ptr [ebx + 0x8]
            mov eax, dword ptr [eax + 0x24]
            test eax, eax
            jz f
            mov edx, {tag:#x}
            call {V1.LIST_FIND:#x}
            test eax, eax
            jz f
            mov eax, dword ptr [ebx + 0x8]
            mov eax, dword ptr [eax + 0x24]
            mov edx, {tag:#x}
            call {V1.LIST_FIND:#x}
            call {V1.LIST_IMG:#x}
            pop ebx
            ret
        f:
            mov eax, ebx
            pop ebx
        o:
            jmp {orig:#x}
        """, at)
        P.append((V1.VMT + slot, struct.pack("<I", v1[orig]), struct.pack("<I", at)))
        blob += c; at += len(c)
    cc = OV.asm(f"""
        mov dword ptr [esi + 0x60], 0xc8
        mov byte ptr [esi + 0x44], 0x0
        jmp {CREATE_BACK:#x}
    """, at)
    P.append((CREATE, CREATE_ORIG, b"\xe9" + struct.pack("<i", at - (CREATE + 5)) + b"\x90\x90"))
    blob += cc
    assert CAVE + len(blob) <= CAVE_END
    P.append((CAVE, bytes(len(blob)), bytes(blob)))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(); st, bad = SP.state(d, pe, SP.EBASE, P)
    bad = [x for x in bad if int(x, 16) not in [V1.VMT + s for s, _, _ in V1.GETTERS]]
    print("AoWEPACK %s relocs %s" % (st, bad or "none (VMT slot relocs expected)"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT (patch_teleport_water_v1 must be applied)"); return 1
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
