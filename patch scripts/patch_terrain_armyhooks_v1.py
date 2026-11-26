#!/usr/bin/env python3
"""patch_terrain_armyhooks_v1.py - let OUR terrain spells change terrain / place hills and mountains UNDER ARMIES
(2026-10-17; user: "it definitely seems like lava can't spawn below units.  I want mountains from Tectonic Rift to be
able to spawn under units too").  Shared infrastructure for patch_pyroclasm_v1.py (v3) and patch_tectonic_v1.py
(v3.2); independent sites, so it applies / reverts in any order relative to their chains - but both of them REQUIRE it
(their --apply refuses without it, and this --revert refuses while either of them uses it).

WHY LAVA NEVER APPEARED UNDER UNITS (RE, HSEPack + AoWEPACK):
  THSMap.ChangeTerrain (HSEPack 0x5560C688) first WRITES the new terrain into [field+0x14] of every hex, then asks every
  child TMapField.CanChangeTerrainEx (0x55607BB0) and restores the hexes a child vetoes.  TArmyHS.CanChangeTerrain
  (0x55790DAC, VMT 0x557133A0 +0x98) honours a TFrozenWaterHS / 0x2123E SOURCE only when [field+0x14] == 0 - i.e. when
  the NEW terrain is water (Freeze Water melting back).  For lava (9) it always asks TArmy.ValidTerrain (0x5578DD64) ->
  an army that cannot stand on lava VETOES the change, whatever the source.  Pyroclasm v2's "unplaced TFrozenWaterHS as
  the source" therefore never worked (its emulator modelled the veto wrongly).
WHY HILLS / MOUNTAINS NEVER APPEAR UNDER UNITS:
  * TMountainMO.CanPlace (0x557A2E54) refuses a slot whose top HS (HSEngine.TMapField.GetMaxLevelNoneTransparentHS) has
    show priority (VMT+0x64) >= 10 (`call [edx+0x64] / cmp al,0xA` @0x557A2F21); TTerrainMO.CanPlace (HSEPack
    0x5560B014, hills / trees) asks TTerrainMO VMT+0x120 = 0x5560B000, the same priority test (`call [edx+0x64]`
    @0x5560B007).  TArmyHS.GetPriority (0x557841E0) = 0x1A -> no hill or mountain can ever be placed over an army.
  * After that, the map-level placement test (HSEPack 0x5560CD00) writes the new terrain / overlay bytes and asks
    CanChangeTerrainEx too -> a mountain slot (overlay 0) over an army that cannot stand on mountains is vetoed again.

THIS PATCH (AoWEPACK.dll only; runtime switches in the .idata page slack, zero at load, written only by our engines):
  ALLOW_SRC dword @0x5590B500 - Pyroclasm v3 stores its unplaced TFrozenWaterHS source here around each of its own
            ChangeTerrain calls (and clears it after).
  PLACE_FLAG dword @0x5590B504 - Tectonic v3.2 sets it to 1 around each of its own resource CreateAndPlace calls.
  CCT  TArmyHS.CanChangeTerrain @0x55790DB9 (9 B `mov eax,[ebx+4] / cmp byte [eax+0x14],0 / jne`) -> jmp cave:
       ALLOW_SRC != 0 and the change's source == ALLOW_SRC  -> allowed;  PLACE_FLAG != 0 -> allowed;  else the vanilla
       code (the source exception for water, ValidTerrain otherwise).  The accepted change then runs the vanilla
       TMapField.TerrainChanged -> TArmyHS.TerrainChanged -> TArmy.ValidateTerrain (0x5578CF70 / Ex 0x5578CC9C): every
       unit that cannot stand there dies through the vanilla event (lava: "units burn", the Fire-Halo-lost path).
  PRIO TArmyHS VMT+0x64 slot @0x55713404 (relocated pointer, vanilla 0x557841E0) -> cave: returns 0x1A as vanilla,
       EXCEPT 9 while PLACE_FLAG != 0 and the caller is one of the two CanPlace priority tests (return address
       0x557A2F24 in AoWEPACK, or 0x5560B00A in HSEPack - HSEPack's runtime base derived from AoWEPACK's import slot
       0x558FBEE4 = HSEngine.TMapField.GetMaxLevelNoneTransparentHS, preferred 0x5560824C).  Every other priority user
       (drawing order, the priority-range child sweeps) always sees 0x1A, also during our placements.
  Visual / sync: no RNG, no state of its own; both switches are written and cleared inside the synced new-turn engines.

Zone AoWEPACK 0x5587A600..0x5587A800 (header 'TARMYHv1' + the 9 + 4 original bytes; caves) - zero and reloc free
2026-10-17 (0x5587A000..0x5587A600 stays reserved for a Sea Serpent placement fix).
Dry-run default; --apply / --revert / --dis / --dll <path> (scratch copy, no backup).  Backup .bak_armyhooks.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BAK_SUFFIX = ".bak_armyhooks"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5587A600, 0x5587A800
MAGIC = b"TARMYHv1"
ALLOW_SRC, PLACE_FLAG = 0x5590B500, 0x5590B504
CCT_SITE, CCT_VANILLA = 0x55790DB9, bytes.fromhex("8b4304807814007521")
CCT_ALLOW, CCT_VALID, CCT_SRC = 0x55790DFC, 0x55790DE3, 0x55790DC2
PRIO_SLOT, PRIO_VANILLA = 0x55713404, 0x557841E0
MTN_PRIO_RET = 0x557A2F24                           # TMountainMO.CanPlace: `call [edx+0x64]` @0x557A2F21 returns here
HSE_IMPORT, HSE_IMPORT_PREF = 0x558FBEE4, 0x5560824C  # AoWEPACK IAT slot -> HSEngine.TMapField.GetMaxLevelNoneTransparentHS
HSE_PRIO_RET = 0x5560B00A                           # HSEPack TTerrainMO VMT+0x120: `call [edx+0x64]` @0x5560B007 returns here
# users: their zones carry these addresses -> this patch refuses to revert while they are applied
USERS = (("patch_tectonic_v1.py (v3.2)", 0x55874C00, 0x55878000, PLACE_FLAG),
         ("patch_pyroclasm_v1.py (v3)", 0x5587B800, 0x5587D800, ALLOW_SRC))

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_pic(src, va):
    """Assemble; every `call $D` / `pop R` / `sub R, $D` triple gets the anchor (the VA after the call) patched in."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
        s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0])
    k = 0
    while True:
        k = b.find(b"\xe8\x00\x00\x00\x00", k)
        if k < 0: break
        if 0x58 <= b[k + 5] <= 0x5F:
            if b[k + 6] == 0x2D and b[k + 7:k + 11] == b"\xff\xff\xff\x7f":          # sub eax, imm32 (short form)
                struct.pack_into("<I", b, k + 7, va + k + 5)
            elif b[k + 6] == 0x81 and b[k + 8:k + 12] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 8, va + k + 5)
        k += 5
    assert b"\xff\xff\xff\x7f" not in b, "unpatched PIC anchor"
    return bytes(b)


def build(cct_orig, prio_orig):
    out = bytearray(MAGIC + cct_orig + struct.pack("<I", prio_orig)); where = {}
    C = dict(allow=ALLOW_SRC, pflag=PLACE_FLAG, callow=CCT_ALLOW, cvalid=CCT_VALID, csrc=CCT_SRC, mret=MTN_PRIO_RET,
             himp=HSE_IMPORT, hpref=HSE_IMPORT_PREF, hret=HSE_PRIO_RET)
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm_pic(src % C, va))
    # CCT: eax/edx free here (the vanilla paths reload them); ebx = {source, field, subhex}, esi = the TArmyHS
    place("cct", """
        call $D
        pop eax
        sub eax, $D
        mov edx, dword ptr [eax+%(allow)#x]
        test edx, edx
        jz c_flag
        cmp edx, dword ptr [ebx]
        je c_allow
    c_flag:
        cmp dword ptr [eax+%(pflag)#x], 0
        jne c_allow
        mov eax, dword ptr [ebx+4]
        cmp byte ptr [eax+0x14], 0
        jne %(cvalid)#x
        jmp %(csrc)#x
    c_allow:
        jmp %(callow)#x
    """)
    # PRIO: the TArmyHS show priority; every register but AL kept (the vanilla body is `mov al,0x1a / ret`)
    place("prio", """
        push eax
        push ecx
        push edx
        call $D
        pop ecx
        sub ecx, $D
        cmp dword ptr [ecx+%(pflag)#x], 0
        je p_def
        mov edx, dword ptr [esp+0xc]
        lea eax, [ecx+%(mret)#x]
        cmp edx, eax
        je p_low
        mov eax, dword ptr [ecx+%(himp)#x]
        sub eax, %(hpref)#x
        add eax, %(hret)#x
        cmp edx, eax
        je p_low
    p_def:
        pop edx
        pop ecx
        pop eax
        mov al, 0x1a
        ret
    p_low:
        pop edx
        pop ecx
        pop eax
        mov al, 9
        ret
    """)
    return bytes(out), where


def relocs(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def vaoff(va):
    return va - CODE_V2F


def data_off(d, va):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    rva = va - BASE
    for k in range(nsec):
        vs, sva, rs, ro = struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8)
        if sva <= rva < sva + max(vs, rs): return ro + rva - sva
    raise ValueError(hex(va))


def state_of(d):
    """-> (zone state, stored (cct, prio) or None, where or None, code or None, site states)"""
    zl = bytes(d[vaoff(ZONE):vaoff(ZONE_END)])
    live_cct = bytes(d[vaoff(CCT_SITE):vaoff(CCT_SITE) + 9])
    live_prio = struct.unpack_from("<I", d, data_off(d, PRIO_SLOT))[0]
    if zl[:8] == MAGIC:
        stored = (zl[8:17], struct.unpack_from("<I", zl, 17)[0])
    elif any(zl):
        return "FOREIGN", None, None, None, None
    else:
        stored = None
    cct_orig, prio_orig = stored if stored else (live_cct, live_prio)
    code, where = build(cct_orig, prio_orig)
    want_cct = b"\xe9" + struct.pack("<i", where["cct"] - (CCT_SITE + 5)) + b"\x90" * 4
    s_cct = "free" if stored is None else "ours" if live_cct == want_cct else "OTHER"
    s_prio = "free" if stored is None else "ours" if live_prio == where["prio"] else "OTHER"
    zs = "zero" if stored is None else "ours" if zl[:len(code)] == code and not any(zl[len(code):]) else "ours(old)"
    return zs, stored, where, code, dict(cct=s_cct, prio=s_prio, want_cct=want_cct, live_cct=live_cct, live_prio=live_prio)


def applied(d):
    """True when the hooks are live (used by patch_tectonic_v1.py / patch_pyroclasm_v1.py as a dependency check)."""
    zs, stored, where, code, st = state_of(d)
    return zs == "ours" and st["cct"] == "ours" and st["prio"] == "ours"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=None, help="patch this file instead of the live AoWEPACK.dll (scratch testing)")
    a = ap.parse_args()
    dll = a.dll or game_file("AoWEPACK.dll")
    d = bytearray(open(dll, "rb").read())
    print("target:", dll)
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or CCT_SITE - 3 < r < CCT_SITE + 9]
    if bad or PRIO_SLOT not in rl: print("ABORT: relocs in zone/site %s or the VMT slot is not relocated (%s)" % (bad, PRIO_SLOT in rl)); return 1
    zs, stored, where, code, st = state_of(d)
    if zs == "FOREIGN": print("ABORT: zone %#x..%#x is not free" % (ZONE, ZONE_END)); return 1
    if stored is None:
        if st["live_cct"] != CCT_VANILLA: print("ABORT: CanChangeTerrain site %#x is not vanilla: %s" % (CCT_SITE, st["live_cct"].hex())); return 1
        if st["live_prio"] != PRIO_VANILLA: print("ABORT: TArmyHS VMT+0x64 is not vanilla: %#x" % st["live_prio"]); return 1
    print("zone %s (%d B of %d) | CanChangeTerrain site %s | TArmyHS priority slot %s | caves %s" % (
        zs, len(code), ZONE_END - ZONE, st["cct"], st["prio"], ", ".join("%s=%#x" % kv for kv in where.items())))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); inv = {v: k for k, v in where.items()}
        st0 = where["cct"]
        for i in md.disasm(code[st0 - ZONE:], st0):
            if i.address in inv: print("  -- %s" % inv[i.address])
            print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if stored is None: print("already vanilla"); return 0
        users = [nm for nm, lo, hi, ref in USERS if struct.pack("<I", ref) in bytes(d[vaoff(lo):vaoff(hi)])]
        if users: print("ABORT: still used by %s - revert those first (they need these hooks)" % users); return 1
        if "OTHER" in (st["cct"], st["prio"]): print("ABORT: a site was taken over by someone else: %s" % st); return 1
        d[vaoff(CCT_SITE):vaoff(CCT_SITE) + 9] = stored[0]
        struct.pack_into("<I", d, data_off(d, PRIO_SLOT), stored[1])
        d[vaoff(ZONE):vaoff(ZONE_END)] = bytes(ZONE_END - ZONE)
        with open(dll, "r+b") as f: f.write(bytes(d))
        print("reverted (CanChangeTerrain site %s, priority slot %#x, zone zeroed)" % (stored[0].hex(), stored[1])); return 0
    if zs == "ours" and st["cct"] == "ours" and st["prio"] == "ours": print("already applied"); return 0
    if "OTHER" in (st["cct"], st["prio"]): print("ABORT: a site was taken over by someone else: %s" % st); return 1
    new = bytearray(d)
    new[vaoff(ZONE):vaoff(ZONE_END)] = code + bytes(ZONE_END - ZONE - len(code))
    new[vaoff(CCT_SITE):vaoff(CCT_SITE) + 9] = st["want_cct"]
    struct.pack_into("<I", new, data_off(new, PRIO_SLOT), where["prio"])
    print("%d bytes change" % sum(1 for x, y in zip(d, new) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if a.dll is None:
        bak = bak_path(dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(dll, bak); print("backup ->", bak)
    with open(dll, "r+b") as f: f.write(bytes(new))
    assert open(dll, "rb").read() == bytes(new); print("AoWEPACK: written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
