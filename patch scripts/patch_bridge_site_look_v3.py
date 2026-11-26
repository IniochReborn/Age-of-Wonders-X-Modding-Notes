r"""
BRIDGE SITE LOOK v3 (2026-10-19).  AoWEPACK.dll only.  Layer on top of patch_bridge_site_look_v2.py (needs it applied).

User on v2: "while under construction, the GFX still has the tower 'base' or shell.  Keep the animated/moving builders,
but get rid of the tower base."

ROOT CAUSE: TStructureResource.Show 0x557605DC has TWO draw paths for a resource with a sequence list:
  * 0x557605F9..0x557606B8 - taken only when the structure's VMT+0x70 test passes AND ([[0x558FA040]+0x40] & 6) == 6
    (map tick phase) - AoWEPACK's own chain loop; look v2's SHW hook (0x55760637) lives here and does skip the head.
  * 0x55760703..0x55760724 - EVERY OTHER frame: `call 0x557022C4` = HSEngine.TMapObjectResource.ShowComplexImage
    (HSEPack 0x5560A134: eax = resource, edx = x, ecx = y, [stack] pos-seed, slot, surface; ret 0xC) which walks the
    WHOLE slot chain list[slot] -> [+0x0C] ... - the STR_TOWR stub (Str_TOWR #3/#4/#5, layer 0) + the STR_BLDG crane
    (layer 1) + builders (layer 3) of the tower's under-construction slots 0x19/0x1A/0x1B (Release.hss).
  So the stub was drawn on most frames - look v2's emulation only exercised the hooked path.
FIX: SC hook at 0x55760724 (5 B rel32 call, reloc-free): `call sc_cave`.  Not a bridge site (bridge v2's
  is_site(ebx = the structure) false) -> tail-jump to the original thunk 0x557022C4 with the untouched arguments.  A site
  -> the same loop as ShowComplexImage but starting at the head's SUB sequence ([head+0x0C]): frame =
  ImageLib.TImageSequence.GetFrameIndex (thunk 0x557028BC: eax = seq, edx = tick [[[res+0x18]+0x3C]+0x40] exactly as
  ShowComplexImage reads it, ecx = pos), image = ImageLib.TCustomImageLibrary.Get (thunk 0x55702934: [seq+0x10],
  frame), drawn by the image's VMT+0x84 at (x + [seq+0x24], y + [seq+0x28]) on the surface -> crane + builders only; a
  slot without a sub-chain draws nothing (same rule as v2's SHW).  The resource's list is only read; nothing random ->
  pure drawing, MP-neutral.  The other ShowComplexImage caller (0x557A9505, slot 0x16 of another class) is untouched.
Layout: zone 0x5581C000..0x5581C100 (inside Build Bridge's reserved 0x5581B000..0x5581E000): header 'BLK3' + the
  original 5 site bytes at ZONE..ZONE+0x10, code at ZONE+0x10.  PIC: rel32 calls/jumps only.
States: look v2 (clean) / v3; --apply -> v3; --revert -> exactly the look-v2 state (site call restored, zone zeroed).
Revert BEFORE patch_bridge_site_look_v2.py.
Dry-run default; --apply / --revert / --dis / --dll <copy>.  Backup <game>\backup\AoWEPACK.dll.bak_bridgelook3.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_build_bridge_v2 as V2
import patch_bridge_site_look_v2 as L2

DLL = game_file("AoWEPACK.dll")
BASE, F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581C000, 0x5581C100
SITE = 0x55760724
THUNK = 0x557022C4                      # HSEngine.TMapObjectResource.ShowComplexImage import thunk
GETFRAME, GET = 0x557028BC, 0x55702934  # ImageLib.TImageSequence.GetFrameIndex / TCustomImageLibrary.Get thunks
HDR = b"BLK3"

ASM = r"""
sc_cave:
    push eax
    push edx
    push ecx
    mov eax, ebx
    call {IS_SITE}
    test al, al
    pop ecx
    pop edx
    pop eax
    jnz sc_site
    jmp {THUNK}
sc_site:
    push ebp
    mov ebp, esp
    push ebx
    push esi
    push edi
    sub esp, 0x0C
    mov dword ptr [ebp - 0x10], edx
    mov dword ptr [ebp - 0x14], ecx
    mov edx, dword ptr [eax + 0x18]
    mov edx, dword ptr [edx + 0x3C]
    mov edx, dword ptr [edx + 0x40]
    mov dword ptr [ebp - 0x18], edx
    mov esi, dword ptr [eax + 0x24]
    test esi, esi
    jz sc_done
    mov edi, dword ptr [ebp + 0x0C]
    cmp edi, dword ptr [esi + 8]
    jae sc_done
    mov esi, dword ptr [esi + 4]
    mov ebx, dword ptr [esi + edi*4]
    test ebx, ebx
    jz sc_done
    mov ebx, dword ptr [ebx + 0x0C]
sc_loop:
    test ebx, ebx
    jz sc_done
    mov eax, ebx
    mov edx, dword ptr [ebp - 0x18]
    mov ecx, dword ptr [ebp + 8]
    call {GETFRAME}
    cmp eax, -1
    je sc_next
    push dword ptr [ebp + 0x10]
    mov edx, eax
    mov eax, dword ptr [ebx + 0x10]
    call {GET}
    mov ecx, dword ptr [ebp - 0x14]
    add ecx, dword ptr [ebx + 0x28]
    mov edx, dword ptr [ebp - 0x10]
    add edx, dword ptr [ebx + 0x24]
    mov esi, dword ptr [eax]
    call dword ptr [esi + 0x84]
sc_next:
    mov ebx, dword ptr [ebx + 0x0C]
    jmp sc_loop
sc_done:
    lea esp, [ebp - 0x0C]
    pop edi
    pop esi
    pop ebx
    pop ebp
    ret 0x0C
"""


def build():
    _, v2lab = V2.build()
    src = ASM.format(IS_SITE=hex(v2lab["is_site"]), THUNK=hex(THUNK), GETFRAME=hex(GETFRAME), GET=hex(GET))
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, ZONE + 0x10)[0])
    orig = b"\xe8" + struct.pack("<i", THUNK - (SITE + 5))
    blob = HDR + orig + bytes(0x10 - len(HDR) - len(orig)) + code
    assert ZONE + len(blob) <= ZONE_END
    return blob, orig, ZONE + 0x10, v2lab["is_site"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    blob, orig, entry, _ = build()
    ours = b"\xe8" + struct.pack("<i", entry - (SITE + 5))
    cur = bytes(d[SITE - F:SITE - F + 5])
    sst = "vanilla" if cur == orig else "ours" if cur == ours else "FOREIGN"
    zl = bytes(d[ZONE - F:ZONE_END - F])
    zst = "zero" if not any(zl) else "ours" if zl[:len(blob)] == blob and not any(zl[len(blob):]) else "DIFFERS"
    rel = V2.relocs(bytes(d), BASE)
    bad = [hex(r) for r in rel if ZONE - 3 <= r < ZONE_END or SITE - 3 <= r < SITE + 5]
    shw = bytes(d[L2.SHW_SITE - F:L2.SHW_SITE - F + 5])                 # look v2 enters its SHW cave at its zone start
    l2 = shw == b"\xe8" + struct.pack("<i", L2.ZONE - (L2.SHW_SITE + 5)) and any(d[L2.ZONE - F:L2.ZONE - F + 16])
    print("AoWEPACK bridge-site look v3 | look v2 %s | SC site %#x %s | zone %#x %s (%d B) | relocs %s" % (
        "applied" if l2 else "NOT APPLIED", SITE, sst, ZONE, zst, len(blob), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(blob[0x10:], entry):
            print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sst == "FOREIGN" or zst == "DIFFERS": print("ABORT (site/zone/reloc)"); return 1
    if (sst == "ours") != (zst == "ours"): print("ABORT (mixed state)"); return 1
    if not l2 and not a.revert: print("ABORT (patch_bridge_site_look_v2.py is not applied)"); return 1
    n = bytearray(d)
    if a.revert:
        n[SITE - F:SITE - F + 5] = orig; n[ZONE - F:ZONE_END - F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - F:ZONE - F + len(blob)] = blob; n[SITE - F:SITE - F + 5] = ours
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_bridgelook3")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
