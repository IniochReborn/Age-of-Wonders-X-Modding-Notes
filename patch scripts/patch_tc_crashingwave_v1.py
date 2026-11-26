#!/usr/bin/env python3
r"""
CRASHING WAVE (220, Water L1, 2026-10-17) - WALL DAMAGE.  AoWTCPCK.dll only.

User spec: combat spell, breath AOE, R40 C4, ATK 8 / DMG 3, Physical/Wall damage, pushes every unit in the AOE one hex away
from the caster; "basically like Gust except blue particles and it does wall damage - should NOT go through walls, should be
blocked by walls but able to damage them".  The spell = a pipeline TColdBreath clone (class 5) like Gust 212; the push, the
shake/hop animation and the forward spray come from patch_tc_gust_v1.py v7 (its caves serve the family {212, 220}).

RE (TCAbRangedTE.NextStrike 0x40D290, category 5 = breath; frame: te = [ebp-4], fx = [ebp-0x10]):
  * the strike path is walked point by point (0x40EE41..0x40F0A2); a breath (fx[+0x34] = 5) ignores units (0x40EEA5) but
    stops at the first hex holding a FindOwnedChild 0x220166 / 0x220504 (TCityWall) / 0x220506 (TCityWallDoor) object or a
    blocking terrain (0x40EF96..0x40EFEA) -> [ebp-0x54] = that object (0 = terrain), the path is TRUNCATED there (0x40EFF0),
    and 0x40F06F zeroes the strike's damage hex [fx+0x24] (= blocked: no damage at all).  So vanilla breath is already
    blocked by walls - it just never hurts them.
  * walls never see the breath message 0x31013 (TCityWall.MapFieldMsgProc 0x405D04 = VMT+0xCC handles 0x31000..0x3100E);
    hail (0x31006, case 6 @0x406087) damages them: GetSpell([msg+0xC]) (spell-id cave 0x43C420) -> spell VMT+0x7C(caster
    unit [[msg+8]+0x4C]) -> att/dmg -> roll -> TCityWall.SetHP 0x405AE4.  Msg record = Execute's hail record:
    {+0 id, +4 field, +8 caster combat unit = [te+0x10], +0xC spell id, +0x18 layer (handler skips != 0), +0x1C -1}.
Hooks (both sites vanilla & reloc-free when written; call cave + nops; the caves replay the replaced instructions):
  BLK 0x40F06F (8 B `mov eax,[ebp-0x10] / xor edx,edx / mov [eax+0x24],edx`, category-5 blocked strike): replay, then for a
      te of spell 220 whose obstacle [ebp-0x54] is a TCityWall / TCityWallDoor (VMT compare, PIC) record {fx, wall} in a
      te-tagged 24-entry table.
  LND 0x40C871 (7 B `mov eax,[ebp-0x20] / cmp dword [eax+0x24],0`, Execute's category-5 landing; fx = [ebp-0x20],
      te = [ebp-4]): for a blocked 220 strike (damage hex <= 0) found in the table -> consume the entry; if that wall was not
      hit yet by this te (te-tagged 16-entry list) deliver ONE 0x31006 hail record straight to the wall (VMT+0xCC) with
      spell 220 -> the wall takes 220's own ATK 8 / DMG 3 roll exactly like a Great Hail stone (one roll per wall section
      per cast, however many strikes it blocked).  Units standing ON the wall hex are untouched (the breath stops there).
      Replays the 2 instructions last (their flags feed the vanilla jle).
  Deterministic: inside the broadcast TE token, strike order identical on every machine; the roll is the vanilla wall
  roll (as hail).  Fast combat: breath = no strikes -> no wall damage (as Gust: damage only).
Tables: .idata page slack (vsize ends 0x479EC8, page to 0x47A000, RW, zero in the file): FXT 0x479ED0 {te, n, 24 x (fx,
wall)} .. 0x479F98; HIT 0x479FA0 {te, n, 16 walls} .. 0x479FE8 (Gust v7 latches its family id at 0x479FF0).
Zone AoWTCPCK 0x44A800..0x44B000 (zero + reloc-free when allocated): +0 magic 'CWV1', +4 BLK original (8 B), +0xC LND
original (7 B), code at +0x20.  Dry-run default; --apply / --revert / --dis / --dll <copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_cwave.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x44A800, 0x44B000
CODE = ZONE + 0x20
MAGIC = b"CWV1"
SPELL = 220
SITES = [("BLK", 0x40F06F, bytes.fromhex("8b45f033d2895024"), "blk"),
         ("LND", 0x40C871, bytes.fromhex("8b45e083782400"), "lnd")]
FXT, FXN = 0x479ED0, 24
HIT, HITN = 0x479FA0, 16
VMT_WALL, VMT_DOOR = 0x405008, 0x4052AC          # TCityWall / TCityWallDoor (VMT+0xCC = 0x405D04 for both)
K = dict(spell=SPELL, fxt=FXT, fxn=FXN, hit=HIT, hitn=HITN, vwall=VMT_WALL, vdoor=VMT_DOOR)


def caves():
    return [("blk", """
        mov eax, [ebp-0x10]
        xor edx, edx
        mov [eax+0x24], edx
        pushad
        mov esi, [ebp-4]
        cmp dword ptr [esi+0x18], %(spell)d
        jne b_out
        cmp dword ptr [esi+0x14], 0x34
        jne b_out
        mov edi, [ebp-0x54]
        test edi, edi
        jz b_out
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [edi]
        lea edx, [ebx+%(vwall)#x]
        cmp eax, edx
        je b_wall
        lea edx, [ebx+%(vdoor)#x]
        cmp eax, edx
        jne b_out
    b_wall:
        lea ecx, [ebx+%(fxt)#x]
        cmp [ecx], esi
        je b_tag
        mov [ecx], esi
        mov dword ptr [ecx+4], 0
    b_tag:
        mov eax, [ecx+4]
        cmp eax, %(fxn)d
        jae b_out
        mov edx, [ebp-0x10]
        mov [ecx+eax*8+8], edx
        mov [ecx+eax*8+12], edi
        inc dword ptr [ecx+4]
    b_out:
        popad
        ret
    """ % K), ("lnd", """
        pushad
        mov esi, [ebp-0x20]
        cmp dword ptr [esi+0x24], 0
        jg l_out
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(spell)d
        jne l_out
        call $D
        pop ebx
        sub ebx, $D
        lea ecx, [ebx+%(fxt)#x]
        cmp [ecx], eax
        jne l_out
        mov edx, [ecx+4]
        xor edi, edi
    l_find:
        cmp edi, edx
        jae l_out
        cmp [ecx+edi*8+8], esi
        je l_hit
        inc edi
        jmp l_find
    l_hit:
        mov dword ptr [ecx+edi*8+8], 0
        mov edi, [ecx+edi*8+12]
        test edi, edi
        jz l_out
        lea ecx, [ebx+%(hit)#x]
        cmp [ecx], eax
        je l_t
        mov [ecx], eax
        mov dword ptr [ecx+4], 0
    l_t:
        mov edx, [ecx+4]
        xor esi, esi
    l_dup:
        cmp esi, edx
        jae l_new
        cmp [ecx+esi*4+8], edi
        je l_out
        inc esi
        jmp l_dup
    l_new:
        cmp edx, %(hitn)d
        jae l_send
        mov [ecx+edx*4+8], edi
        inc dword ptr [ecx+4]
    l_send:
        sub esp, 0x40
        mov edx, esp
        push edi
        push eax
        mov edi, edx
        mov ecx, 0x10
        xor eax, eax
        rep stosd
        pop eax
        pop edi
        mov dword ptr [edx], 0x31006
        mov ecx, [eax+0x10]
        mov [edx+8], ecx
        mov ecx, [eax+0x18]
        mov [edx+0xc], ecx
        mov dword ptr [edx+0x1c], -1
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx+0xcc]
        add esp, 0x40
    l_out:
        popad
        mov eax, [ebp-0x20]
        cmp dword ptr [eax+0x24], 0
        ret
    """ % K)]


def build_zone():
    hdr = bytearray(MAGIC + SITES[0][2] + SITES[1][2])
    hdr += bytes(0x20 - len(hdr))
    blob = bytearray(hdr); where = {}
    for name, src in caves():
        va = ZONE + len(blob); where[name] = va; blob += asm_pic(src, va)
        while len(blob) % 4: blob += b"\x90"
    assert ZONE + len(blob) <= ZONE_END
    return bytes(blob), where


def site_bytes(site, orig, tgt):
    return b"\xE8" + struct.pack("<i", tgt - (site + 5)) + b"\x90" * (len(orig) - 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    path = a.dll; d = bytearray(open(path, "rb").read())
    R = relocs(d, BASE)
    bad = [hex(r) for r in R if ZONE <= r < ZONE_END] + [hex(r) for _, s, o, _ in SITES for r in R if s - 3 <= r < s + len(o)]
    zone = bytes(d[ZONE - V2F:ZONE_END - V2F]); stored = zone[:4] == MAGIC
    blob, where = build_zone()
    st = {}
    for tag, site, orig, cave in SITES:
        b = bytes(d[site - V2F:site - V2F + len(orig)])
        if b == orig: st[tag] = "vanilla"
        elif stored and b == site_bytes(site, orig, where[cave]): st[tag] = "ours"
        elif stored and b[0] == 0xE8 and ZONE <= site + 5 + struct.unpack_from("<i", b, 1)[0] < ZONE_END: st[tag] = "ours(old)"
        else: st[tag] = "OTHER"
    if zone == bytes(len(zone)): zst = "zero"
    elif not stored: zst = "FOREIGN"
    else: zst = "ours" if zone[:len(blob)] == blob and not any(zone[len(blob):]) else "ours(old)"
    print("AoWTCPCK crashing wave sites %s | zone %s (%d B: %s) | relocs %s" % (st, zst, len(blob), {k: hex(v) for k, v in where.items()}, bad or "none"))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob[0x20:], CODE): print("   %08X  %-8s %s" % (i.address, i.mnemonic, i.op_str))
    if bad: print("ABORT: relocations in the zone / under a site"); return 1
    if any(v == "OTHER" for v in st.values()): print("ABORT: a site holds unknown code (another patch hooked it - revert that first)"); return 1
    if zst == "FOREIGN": print("ABORT: zone %#x..%#x is not free" % (ZONE, ZONE_END)); return 1
    if a.revert:
        if not stored: print("already reverted"); return 0
        for tag, site, orig, cave in SITES:
            o = zone[4:12] if tag == "BLK" else zone[12:19]
            assert o == orig
            d[site - V2F:site - V2F + len(orig)] = o
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        open(path, "r+b").write(d); print("reverted", path); return 0
    if zst == "ours" and all(v == "ours" for v in st.values()):
        print("already applied"); return 0
    if not stored and any(v != "vanilla" for v in st.values()): print("ABORT: sites hooked but no zone"); return 1
    out = bytearray(d)
    out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); out[ZONE - V2F:ZONE - V2F + len(blob)] = blob
    for tag, site, orig, cave in SITES:
        out[site - V2F:site - V2F + len(orig)] = site_bytes(site, orig, where[cave])
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(path) == os.path.abspath(DLL):
        bak = bak_path(DLL, ".bak_cwave")
        if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    open(path, "r+b").write(out); assert open(path, "rb").read() == bytes(out); print("written and verified", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
