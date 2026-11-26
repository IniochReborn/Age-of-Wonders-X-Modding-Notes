#!/usr/bin/env python3
r"""
Sky code: only read a field object as a hexagon when it IS a hexagon (2026-11-14).

User: editor crashes "when i try putting an elf swordsman on a spring of life".  VEH log: AV at AoWEPACK 0x558DB1EF
(read 0x1B000B28), sky overlay extension 'kindof' (sky_overlay_ext_asm), called for a Sky (0xE) field.  kindof walks
the field's object list ([fld+8], count byte [fld+0xD]) and reads [[obj+8]+0xC] as the hexagon resource RID
(Clear Sky = RID>>16 == 0x5A1B) for EVERY object.  A unit standing on a Sky hex has other data at +8 (0x1B000B1C)
-> crash as soon as the hex is drawn.  Nothing to do with the spring itself.
The same blind walk exists in 4 places; each `mov r,[list+ecx*4] / cmp r,0x10000 / jb loop` now calls a small cave
that also requires obj.ClassID (virtual slot 0x24) == 0x20152 (THexagon; TAoWHexagon inherits it), else skips:
  AoWEPACK 0x558DB1DB (overlay ext kindof) + 0x558E126B (second copy)   cave 0x558DBF40
  AoWTools 0x5970A05F (minimap Clear Sky test, patch_minimap_sky_v1)     cave 0x5970A0C0
  AoWTCPCK 0x45B8C3   (battle set-up Clear Sky flag, patch_sky_fld_guard_v1) cave 0x454520
Caves are position independent.  Backups .bak_skycls1.  Dry-run default; --apply; --revert.
Revert this before rebuilding / reverting the overlay ext, the minimap patch or the fld guard.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_skycls1"
HEX_CLASS = 0x20152
PAD = 0x30


def cave_src(reg, lst):
    if reg == "eax":
        return f"""
            mov eax, dword ptr [{lst} + ecx*4]
            cmp eax, 0x10000
            jb zero
            push ecx
            push edx
            push eax
            mov edx, dword ptr [eax]
            call dword ptr [edx + 0x24]
            cmp eax, {HEX_CLASS:#x}
            pop eax
            pop edx
            pop ecx
            je ok
        zero:
            xor eax, eax
        ok:
            ret
        """
    return f"""
        mov ebx, dword ptr [{lst} + ecx*4]
        cmp ebx, 0x10000
        jb zero
        push eax
        push ecx
        push edx
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x24]
        cmp eax, {HEX_CLASS:#x}
        pop edx
        pop ecx
        pop eax
        je ok
    zero:
        xor ebx, ebx
    ok:
        ret
    """


# file, VA - file offset, cave VA, reg, list reg, [(site VA, original bytes)]
JOBS = [
    ("AoWEPACK.dll", 0x55700C00, 0x558DBF40, "eax", "esi",
     [(0x558DB1DB, bytes.fromhex("8b048e3d0000010072f3")), (0x558E126B, bytes.fromhex("8b048e3d0000010072f3"))]),
    ("AoWTools.dll", 0x59700C00, 0x5970A0C0, "eax", "edx",
     [(0x5970A05F, bytes.fromhex("8b048a3d0000010072f3"))]),
    ("AoWTCPCK.dll", 0x400C00, 0x454520, "ebx", "edx",
     [(0x45B8C3, bytes.fromhex("8b1c8a81fb0000010072f0"))]),
]


def new_site(site, orig, cave, reg):
    n = len(orig)
    target = site + n + struct.unpack("b", orig[-1:])[0]          # the loop head the jb went to
    b = b"\xE8" + struct.pack("<i", cave - (site + 5)) + (b"\x85\xC0" if reg == "eax" else b"\x85\xDB")
    b += b"\x74" + struct.pack("b", target - (site + 9))
    return b + b"\x90" * (n - len(b))


def main():
    ap, rv = "--apply" in sys.argv, "--revert" in sys.argv
    plan = []
    for fn, delta, cave, reg, lst, sites in JOBS:
        path = game_file(fn)
        d = open(path, "rb").read()
        code = OV.asm(cave_src(reg, lst), cave)
        assert len(code) <= PAD
        code += bytes(PAD - len(code))
        cur_c = d[cave - delta:cave - delta + PAD]
        st = set()
        for site, orig in sites:
            cur = d[site - delta:site - delta + len(orig)]
            new = new_site(site, orig, cave, reg)
            st.add("vanilla" if cur == orig and cur_c == bytes(PAD) else
                   "ours" if cur == new and cur_c == code else "OTHER")
        st = st.pop() if len(st) == 1 else "OTHER"
        print("%-13s sites %s, cave %#x: %s" % (fn, ", ".join("%#x" % s for s, _ in sites), cave, st))
        plan.append((path, delta, cave, code, reg, sites, st))
    if not (ap or rv):
        return 0
    assert all(p[-1] != "OTHER" for p in plan), "unexpected bytes - not touching anything"
    assert not SP.busy(), "close the game / editor first"
    for path, delta, cave, code, reg, sites, st in plan:
        if (st == "ours") == ap:
            print("  %s: nothing to do" % os.path.basename(path)); continue
        bk = bak_path(path, TAG)
        if not os.path.exists(bk):
            shutil.copy2(path, bk)
        with open(path, "r+b") as f:
            f.seek(cave - delta); f.write(code if ap else bytes(PAD))
            for site, orig in sites:
                f.seek(site - delta); f.write(new_site(site, orig, cave, reg) if ap else orig)
        print("  %s: written" % os.path.basename(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
