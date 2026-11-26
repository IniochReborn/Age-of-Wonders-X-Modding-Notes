r"""
Army battles on exploration sites use the SITE combat map (2026-10-18) - AoWEPACK.dll.

User spec: when a party attacks another party that stands on an exploration site, the battle is fought on the
site's own combat map (lair / dungeon / crypt / ruin / pyramid / item site); the attacker starts near the ENTRANCE
(where an explorer starts) and the defender INSIDE (where the site's defenders start); explored or not, PvAI and
PvP; unexplored -> the site's item bags spawn as they would when exploring; adjacent stacks do NOT join.

Vanilla facts (RE 2026-10-18):
  * Army attack: TArmyCombatMoveTE (combat creation @0x55749A70): CreateObject 0x220110 (tactical) / 0x202B0 (auto)
    -> TCombat.Setup vcall +0x60 (location = the DEFENDED hex, defender = its owner) -> field message 0x1107 sent to
    the defended field ([msg+8] = combat, [msg+0xC] = attacker TArmyHS, [msg+0x1C] = handled).  If nothing handles
    it, TCombat.AddArmies 0x55727BCC runs (attacker + defender + EVERY adjacent stack via AddAdjacentArmies
    0x5572760C).  Only TCity handles 0x1107 in vanilla (0x557AD6F9 -> 0x557ACD58, sets [msg+0x1C] = 1).
    The same 0x1107 is also sent to the pre-dialog probe combat (0x5574920E) - same handling, harmless.
  * Site exploration: TExplorationSite.SetupCombat (VMT+0x1F4; base 0x557C1960, item sites 0x557C29C8, dungeons
    0x557C5ABC): attacker AddArmy 0x55727804 (side 0) with the SITE location, defenders = roster via 0x557279D0
    (side 1, slot 1), [combat+0x40] := 1 (site combat), item sites/dungeons [combat+0x44] := loot list
    ([site+0x3C] / dungeon [site+0x38]).
  * [combat+0x40] == 1 is what makes AoWTCPCK's map builder (0x4245EC, reads it @0x42462F) pick the structure's
    cave map (the structure is looked up on the combat location) and hand [combat+0x44] to the bag placer; TCPCK
    0x41CD14 puts unpicked bags back into [combat+0x44] after the battle; AoWEPACK 0x55724AFD applies the site
    movement rule (Cave Crawling).  The battle's post-combat callback [combat+0x2C]/[+0x30] stays the ARMY TE's.
  * Start placement: each combat army entry has a SLOT (TCombat 0x55728684 cl; units get slot<<4|n in +0x46);
    AddArmy 0x55727804 derives it from the army's location via 0x55727764 (same hex / neighbour direction / 7).
    An explorer gets the "same hex" slot (it is added with the site location), the site defenders slot 1.

This patch (zone 0x55819200..0x55819400, header 'SCB1' + originals):
  MSG  the 7 exploration-site VMTs' MapFieldMsgProc slot +0xCC (currently build_ai_sitesearch v2's cave
       0x55814A40, chained first) -> cave msg: on 0x1107 not yet handled, with an army on the site's field ([site+4]
       GetObjectOfType 0x20217) that is not the attacker and a site class that owns a loot list (item sites /
       lairs / crypts / ruins / pyramids [site+0x3C], dungeons [site+0x38]; the bare base class is left alone):
         [combat+0x40] := 1, [combat+0x44] := loot list,
         attacker AddArmy(side 0, its real location) with the slot forced to the explorer's (0x55727764 of the
         combat location itself),
         defender AddArmy(side 1, its real location) with the slot forced to 1 (= the site defenders' slot),
         [msg+0x1C] := 1 (-> no AddAdjacentArmies: adjacent stacks stay out).
  SLOT @0x55727855 (AddArmy's `call 0x55727764`) -> cave slot: the original call, then if the override dword
       G = 0x5590BFC0 (AoWEPACK .idata page slack, runtime-only zero memory) is non-zero, al := G-1.  G is only
       set by cave msg around its two AddArmy calls and cleared right after -> every other AddArmy is untouched.
  NOT DONE: the unexplored site's own roster defenders are NOT added - AoW combat is strictly two-sided (attacker /
       defender side bytes [data+0x24]/[+0x25]); a third side hostile to both does not exist.  Adding them to the
       defender's side would make them allies of the defending army and their losses would bypass the site's
       post-combat callback.  The roster, explored state and loot stay the site's: unpicked bags go back to the
       site list (vanilla TCPCK 0x41CD14), picked ones are kept by the picker; a site whose loot list empties this
       way counts as cleared (vanilla rule: TExplorationSite VMT+0x1F0 = loot list empty), otherwise it stays
       unexplored with its roster intact.
PIC: G and the class compare go through a call-pop delta; everything else is rel32 or virtual.  The VMT slots keep
their relocs (in-image VAs).  MP: deterministic (inside the army TE on every machine, no RNG).

LIFO: revert this BEFORE build_ai_sitesearch.py (its cave 0x55814A40 is our chain target).
Dry-run default; --apply / --revert / --dis; --dll <scratch copy>.  Backup <game>\backup\AoWEPACK.dll.bak_sitearmy.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_sitearmy"
BASE = 0x55700000
ZONE, ZONE_END = 0x55819200, 0x55819400
HDR = 0x40
MAGIC = b"SCB1"
G = 0x5590BFC0                       # slot override (0 = none, else slot + 1); .idata page slack, zero at load
SITE_VMTS = (0x557C1440, 0x557C23BC, 0x557C2D24, 0x557C557C, 0x557C64D0, 0x557C68FC, 0x557C6D20)
MSG_SLOT = 0xCC
SETUP_ITEM, SETUP_DUNGEON = 0x557C29C8, 0x557C5ABC          # VMT+0x1F4 SetupCombat variants -> loot list field
SLOT_SITE = 0x55727855
SLOT_ORIG = bytes.fromhex("e80affffff")                       # call 0x55727764
POSCODE, ADDARMY = 0x55727764, 0x55727804
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]
    out = []
    for i in range(n):
        s = pe + 24 + opt + 40 * i
        vs, va, rs, ro = struct.unpack_from("<IIII", d, s + 8)
        out.append((vs, va, rs, ro))
    return out, pe


def va2off(d, va):
    for vs, rva, rs, ro in sections(d)[0]:
        if rva <= va - BASE < rva + rs:
            return ro + va - BASE - rva
    raise ValueError(hex(va))


def reloc_set(d):
    secs, pe = sections(d)
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    p = va2off(d, BASE + rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def push_xyz(reg):
    """push x, y, level of the TArmyHS in `reg` (vcalls +0x74/+0x78/+0x7C, signed bytes) - AddArmy's stack args."""
    return "".join("""
        mov eax, %s
        mov edx, dword ptr [eax]
        call dword ptr [edx + %#x]
        movsx eax, al
        push eax""" % (reg, s) for s in (0x74, 0x78, 0x7C))


def build(prev):
    out = bytearray(HDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    place("msg", """
        push ebx
        push esi
        push edi
        push ebp
        mov esi, eax
        mov edi, edx
        call %(prev)#x
        cmp dword ptr [edi], 0x1107
        jne done
        cmp dword ptr [edi + 0x1c], 0
        jne done
        mov ebx, dword ptr [edi + 8]
        test ebx, ebx
        je done
        cmp dword ptr [edi + 0xc], 0
        je done
        mov eax, dword ptr [esi + 4]
        test eax, eax
        je done
        mov edx, 0x20217
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        je done
        cmp eax, dword ptr [edi + 0xc]
        je done
        mov ebp, eax
        call md
    md:
        pop ecx
        sub ecx, md
        mov eax, dword ptr [esi]
        mov eax, dword ptr [eax + 0x1f4]
        sub eax, ecx
        cmp eax, %(sitem)#x
        jne nitem
        mov eax, dword ptr [esi + 0x3c]
        jmp gotl
    nitem:
        cmp eax, %(sdung)#x
        jne done
        mov eax, dword ptr [esi + 0x38]
    gotl:
        test eax, eax
        je done
        mov byte ptr [ebx + 0x40], 1
        mov dword ptr [ebx + 0x44], eax
        mov eax, dword ptr [ebx + 0xc]
        push dword ptr [eax + 0x10]
        mov ecx, dword ptr [eax + 0xc]
        mov edx, dword ptr [eax + 8]
        mov eax, ebx
        call %(pos)#x
        movzx eax, al
        inc eax
        call mg1
    mg1:
        pop ecx
        sub ecx, mg1
        mov dword ptr [ecx + %(g)#x], eax
        %(patt)s
        mov eax, dword ptr [edi + 0xc]
        mov edx, dword ptr [eax + 0x1c]
        xor ecx, ecx
        mov eax, ebx
        call %(add)#x
        call mg2
    mg2:
        pop ecx
        sub ecx, mg2
        mov dword ptr [ecx + %(g)#x], 2
        %(pdef)s
        mov edx, dword ptr [ebp + 0x1c]
        mov cl, 1
        mov eax, ebx
        call %(add)#x
        call mg3
    mg3:
        pop ecx
        sub ecx, mg3
        mov dword ptr [ecx + %(g)#x], 0
        mov dword ptr [edi + 0x1c], 1
    done:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """ % {"prev": prev, "sitem": SETUP_ITEM, "sdung": SETUP_DUNGEON, "pos": POSCODE, "g": G, "add": ADDARMY,
           "patt": push_xyz("dword ptr [edi + 0xc]"), "pdef": push_xyz("ebp")})
    place("slot", """
        push dword ptr [esp + 4]
        call %(pos)#x
        push edx
        call sd
    sd:
        pop edx
        sub edx, sd
        mov edx, dword ptr [edx + %(g)#x]
        test edx, edx
        je sno
        lea eax, [edx - 1]
    sno:
        pop edx
        ret 4
    """ % {"pos": POSCODE, "g": G})
    assert ZONE + len(out) <= ZONE_END
    return out, where


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    g = lambda va, n: bytes(d[va2off(d, va):va2off(d, va) + n])
    u32 = lambda va: struct.unpack("<I", g(va, 4))[0]
    zl = g(ZONE, ZONE_END - ZONE)
    ours = zl[:4] == MAGIC
    cur_slots = [u32(v + MSG_SLOT) for v in SITE_VMTS]
    cur_slot_site = g(SLOT_SITE, 5)
    if ours:
        sav_prev = struct.unpack_from("<I", zl, 4)[0]; sav_site = zl[8:13]
    else:
        assert len(set(cur_slots)) == 1, "site VMT +0xCC slots differ: %s" % [hex(x) for x in cur_slots]
        sav_prev = cur_slots[0]; sav_site = cur_slot_site
    assert sav_site == SLOT_ORIG, "AddArmy slot call @%#x is %s (expected %s)" % (SLOT_SITE, sav_site.hex(), SLOT_ORIG.hex())
    zone, where = build(sav_prev)
    zone[0:4] = MAGIC; struct.pack_into("<I", zone, 4, sav_prev); zone[8:13] = sav_site
    zone = bytes(zone)
    hooked_site = b"\xE8" + struct.pack("<i", where["slot"] - (SLOT_SITE + 5))
    st_vmt = "ours" if all(s == where["msg"] for s in cur_slots) else "orig" if all(s == sav_prev for s in cur_slots) else "OTHER"
    st_site = "ours" if cur_slot_site == hooked_site else "orig" if cur_slot_site == sav_site else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d)
    vmt_rel = all(v + MSG_SLOT in rl for v in SITE_VMTS)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or SLOT_SITE - 3 <= r < SLOT_SITE + 5]
    try:
        gz = u32(G)                  # inside the raw data -> must be zero
    except ValueError:
        gz = 0                       # past the raw data = runtime-only zero memory (expected)
    print("%s\n  site VMT +0xCC: %s (chain %#x, relocs %s) | slot call %#x: %s | zone %#x: %s (%d B) | G %#x | relocs %s"
          % (a.dll, st_vmt, sav_prev, "ok" if vmt_rel else "MISSING", SLOT_SITE, st_site, ZONE, zstate, len(zone), G,
             bad or "none"))
    print("  caves " + ", ".join("%s=%#x" % kv for kv in where.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[HDR:], ZONE + HDR): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or not vmt_rel or "OTHER" in (st_vmt, st_site) or zstate == "DIFFERS" or gz:
        print("ABORT"); return 1
    out = bytearray(d)
    put = lambda va, b: out.__setitem__(slice(va2off(d, va), va2off(d, va) + len(b)), b)
    if a.revert:
        if not ours and st_vmt == st_site == "orig": print("nothing to revert"); return 0
        for v in SITE_VMTS: put(v + MSG_SLOT, struct.pack("<I", sav_prev))
        put(SLOT_SITE, sav_site); put(ZONE, bytes(ZONE_END - ZONE))
        write_inplace(a.dll, bytes(out)); print("reverted (7 site VMT slots, AddArmy slot call, zone cleared)"); return 0
    if ours and st_vmt == st_site == zstate == "ours": print("already applied"); return 0
    put(ZONE, zone); put(SLOT_SITE, hooked_site)
    for v in SITE_VMTS: put(v + MSG_SLOT, struct.pack("<I", where["msg"]))
    print("  %d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out))
    assert open(a.dll, "rb").read() == bytes(out)
    print("Written and verified.  Test: attack an enemy stack standing on an exploration site.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
