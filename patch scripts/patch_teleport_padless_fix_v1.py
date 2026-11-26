#!/usr/bin/env python3
r"""
Teleporters work again after the padless change (2026-11-04).

Bug (mapmaker report, The Groll 1f: teleporter 19/104/5 -> 31/98/5 "does nothing"): every teleporter has been dead
since patch_teleport_water_v2 (10/31) made TTeleportResource padless (res+0x44 = 0) so water teleporters stay on
water.  HSEngine calls each structure on a map field with the structure's footprint PART byte:
  * TMapField.UpdateMapField (HSE 0x55608028) -> struct VMT+0xEC, record {field, part}
  * TMapField.MoveExclusive  (HSE 0x55608204) -> struct VMT+0xD8, record {ctx, field, part}
TTeleport's handlers (0x557A4E1C: field flag 0x8000 "has exclusive move"; 0x557A4E2C: pathfinder edge to the
destination via 0x55745928) only act for part 0.  Pad placement always registered part 0; generic (padless)
placement registers the structure's footprint part (editor status "HS:3"), so no teleport edge is ever added.
Fix: both handlers act when the field IS the teleporter's own hex (field +0x10/+0x11/+0x12 == GetXhx/GetYhx/GetLhx =
VMT +0x74/+0x78/+0x7C), whatever the part byte.  Divine Gates share TTeleport -> fixed too.
Cave AoWEPACK 0x558E0A80..0x558E0B00 'TPF1'.  Backup .bak_telepadfix.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_telepadfix"
CAVE, CAVE_END, MAGIC = 0x558E0A80, 0x558E0B00, b"TPF1"
EC_SITE, EC_ORIG = 0x557A4E1C, bytes.fromhex("807a040075098b0281481800800000c3")
D8_SITE, D8_ORIG = 0x557A4E32, bytes.fromhex("807e08007530")
D8_OK, D8_SKIP = 0x557A4E38, 0x557A4E68


def epk_patches():
    at = CAVE + len(MAGIC)
    # ismine: ebx = teleporter, edi = field -> ZF set when the field is the teleporter's own hex
    src = f"""
    ec:
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov edi, dword ptr [edx]
        call ismine
        jne ec_out
        or dword ptr [edi + 0x18], 0x8000
    ec_out:
        pop edi
        pop esi
        pop ebx
        ret
    d8:
        push edi
        mov edi, dword ptr [esi + 0x4]
        call ismine
        pop edi
        jne {D8_SKIP:#x}
        jmp {D8_OK:#x}
    ismine:
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x74]
        cmp al, byte ptr [edi + 0x10]
        jne im_out
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x78]
        cmp al, byte ptr [edi + 0x11]
        jne im_out
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x7c]
        cmp al, byte ptr [edi + 0x12]
    im_out:
        ret
    """
    code = OV.asm(src, at)
    # entry offsets: ec at 0; d8 after the ec block (fixed layout, measured)
    sig = bytes.fromhex("578b7e04")               # d8: push edi / mov edi,[esi+4]
    assert code.count(sig) == 1
    d8_at = at + code.index(sig)
    z = MAGIC + code
    assert CAVE + len(z) <= CAVE_END, len(z)
    jec = b"\xe9" + struct.pack("<i", at - (EC_SITE + 5))
    jd8 = b"\xe9" + struct.pack("<i", d8_at - (D8_SITE + 5))
    return [(EC_SITE, EC_ORIG, jec + b"\x90" * (len(EC_ORIG) - 5)),
            (D8_SITE, D8_ORIG, jd8 + b"\x90" * (len(D8_ORIG) - 5)),
            (CAVE, bytes(len(z)), z)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches()
    st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted")
        return 0
    if st[0] == "ours":
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(SP.EPK, TAG)
    if not os.path.exists(bk):
        shutil.copy2(SP.EPK, bk)
    SP.write_bytes(SP.EPK, SP.EBASE, P, False)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
