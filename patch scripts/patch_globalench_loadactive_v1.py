"""
GLOBAL ENCHANTMENT 'ACTIVE' BIT AFTER A LOAD (2026-10-15).  AoWEPACK.dll only.

User (325 Bountiful Harvest test): "if i have bountiful harvest active, i cant cast it a second time. but if i reload my
save, it allows me to cast it a second time?" - and no income bonus after a reload.

ROOT CAUSE (RE 2026-10-15):
  TGlobalEnchantment (VMT 0x5570B398, size 0x24) serialises itself in ReadWrite = VMT+0x18 0x5577DA1C (the Engine
  filer reads AND writes through the same method): tag 0xA [+8] handle, 0xB [+0x18] type byte, 0xC [+0x19] caster,
  0xD [+0x1C] name, 0xE [+0x20], 0xF [+0x14] (our spell-id MARKER - it IS saved).  The flag bytes [+0x10]/[+0x11] are
  NOT saved: [+0x11] is re-set by the ctor (0x5577D8F8), but [+0x10] bit 0 = 'active' is set ONLY by Activate
  (0x5577DBA0, which also adds the enchantment to TGlobalMagicControl [[AoWHSMap 0x558FA040]+0x188] list +0x14) and
  cleared by Deactivate (0x5577DC3C, which removes it from that list).  So at run time "in the list" == "bit 0 set",
  but after a LOAD every listed enchantment has bit 0 CLEAR: TGlobalMagicControl.ReadWrite (VMT+0x18 0x5577E1D4)
  re-reads the list (tag 0xA) and then runs its rebuild pass 0x5577E46C, which only recomputes the control's own type
  bitset [gmc+0x10] from each member's [+0x18].
  Every 'is spell X active for player P' cave of ours tests marker [+0x14] AND bit 0 of [+0x10] (hva Bountiful
  Harvest, bda Blessed Dew, gaa Golden Age, spa Steam Power, Drought's two scans + drought_once, oga Overgrowth /
  World Healer) -> after a reload all of them read 'not active': no income bonus, no heal, no growth, Drought's
  markers start reverting, and the once-per-player CanActivate checks let the spell be cast again.

FIX (one place, covers every global enchantment):
  LB  0x5577E493 (5 B `mov dl,[eax+0x18] / mov eax,esp`, inside the rebuild pass's per-member loop: eax = member)
      -> `call cave`: or byte [eax+0x10], 1 (the member IS in the list = active) / replay `mov dl,[eax+0x18]` /
      `lea eax,[esp+4]` (= the caller's esp) / ret.
  The pass runs after every load, every save (members are active then anyway), every Activate (bit already set) and
  every Deactivate (after the member was removed) - so it only ever restores the run-time truth.  Vanilla readers of
  bit 0 now see after a load what they saw before the save.  No absolute addresses in the cave (no PIC needed);
  synced state only -> MP-safe (every peer loads the same list).

Zone 0x5582E000..0x5582E040 (verified zero).  Dry-run default; --apply / --revert / --dis.
Backup <game>\\backup\\AoWEPACK.dll.bak_gelactive.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP = game_file("AoWEPACK.dll")
EP_BASE, EP_V2F = 0x55700000, 0x55700C00
EZ, EZ_END = 0x5582E000, 0x5582E040
EP_SITES = [("lb", 0x5577E493, bytes.fromhex("8a50188bc4"), "call", "lb")]

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build_ep():
    src = """
        or byte ptr [eax+0x10], 1
        mov dl, byte ptr [eax+0x18]
        lea eax, [esp+4]
        ret
    """
    return bytes(ks.asm(src, EZ)[0]), {"lb": EZ}


def reloc_set(d, base):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * i + 8) for i in range(nsec)]
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    out = set()
    if not rrva: return out
    p = r2f(rrva); end = p + rsz
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def site_states(d, v2f, sites, where, zone, zend):
    st, patched = {}, {}
    for name, va, orig, kind, cave in sites:
        op = b"\xe8" if kind == "call" else b"\xe9"
        new = op + struct.pack("<i", where[cave] - (va + 5)) + b"\x90" * (len(orig) - 5); patched[name] = (va, orig, new)
        live = bytes(d[va - v2f:va - v2f + len(orig)])
        if live == orig: st[name] = "vanilla"
        elif live == new: st[name] = "ours"
        elif live[0] in (0xE8, 0xE9) and zone <= va + 5 + struct.unpack_from("<i", live, 1)[0] < zend: st[name] = "ours(old)"
        else: st[name] = "OTHER"
    return st, patched


def sanity(d):
    at = lambda va, n: bytes(d[va - EP_V2F:va - EP_V2F + n])
    assert at(0x5577E48E, 5) == bytes.fromhex("e8a9fcffff"), "rebuild loop: TList.Get call moved"
    assert at(0x5577E498, 7) == bytes.fromhex("b101e8e92bf8ff"), "rebuild loop: Include call moved"
    assert at(0x5577E215, 5) == bytes.fromhex("e852020000"), "TGlobalMagicControl.ReadWrite no longer runs the rebuild pass"
    assert at(0x5577DBAB, 6) == bytes.fromhex("0a4310884310"), "Activate's bit-0 set moved"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    ed = bytearray(open(EP, "rb").read())
    sanity(ed)
    eblob, ewhere = build_ep()
    assert EZ + len(eblob) <= EZ_END
    est, epatch = site_states(ed, EP_V2F, EP_SITES, ewhere, EZ, EZ_END)
    zl = bytes(ed[EZ - EP_V2F:EZ_END - EP_V2F])
    ez = "zero" if not any(zl) else "ours" if zl[:len(eblob)] == eblob and not any(zl[len(eblob):]) else "DIFFERS"
    erl = reloc_set(bytes(ed), EP_BASE)
    ebad = [hex(r) for r in erl if EZ - 3 <= r < EZ_END or any(va - 3 <= r < va + len(o) for _n, va, o, _k, _c in EP_SITES)]
    print("AoWEPACK: sites %s | zone %s (%d B: lb=%#x) | relocs %s" % (est, ez, len(eblob), ewhere["lb"], ebad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(eblob, EZ):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if ebad or "OTHER" in est.values(): print("ABORT (relocs or a foreign hook)"); return 1
    if ez == "DIFFERS" and not any(s.startswith("ours") for s in est.values()): print("ABORT (zone not free)"); return 1
    eo = bytearray(ed)
    if a.revert:
        for va, orig, _n in epatch.values(): eo[va - EP_V2F:va - EP_V2F + len(orig)] = orig
        eo[EZ - EP_V2F:EZ_END - EP_V2F] = bytes(EZ_END - EZ)
    else:
        eo[EZ - EP_V2F:EZ_END - EP_V2F] = bytes(EZ_END - EZ); eo[EZ - EP_V2F:EZ - EP_V2F + len(eblob)] = eblob
        for va, _o, new in epatch.values(): eo[va - EP_V2F:va - EP_V2F + len(new)] = new
    if eo == ed: print("already applied" if not a.revert else "already reverted"); return 0
    if not (a.apply or a.revert): print("%d bytes change\nDry run OK - rerun with --apply (or --revert)." % sum(1 for x, y in zip(ed, eo) if x != y)); return 0
    bak = bak_path(EP, ".bak_gelactive")
    if not os.path.exists(bak): shutil.copy2(EP, bak); print("backup ->", bak)
    with open(EP, "r+b") as f: f.write(bytes(eo))
    assert open(EP, "rb").read() == bytes(eo); print("AoWEPACK.dll: %s and verified" % ("reverted" if a.revert else "written"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
