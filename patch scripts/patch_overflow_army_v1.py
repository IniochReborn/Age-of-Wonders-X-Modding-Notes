#!/usr/bin/env python3
r"""
Post-combat overflow placement (2026-10-18): units that JOIN a party during combat (Dominate / Charm / any side change,
also combat-summoned units with no strategic party) no longer pile onto the hex the victorious moving party is about to
occupy when that party is full - they are placed on the nearest valid hex instead, using the engine's own summon-style
spiral (TAbstractUnit.Place = InitHNWalk/WalkToNextHN + CanPlace: in-map, field owner = player or neutral, an own army
there that can take the unit, else ValidTerrain for the unit).

RE (vanilla flow):
  * TCombat.Finalize 0x55727E38 calls every combat object's slot +0xD0 = TCombatUnit.Finalize 0x55724D44 (TCombatUnit
    AND TFastCombatUnit VMTs) three times, bl = pass 0/1/2.  Pass 0/1 put each surviving unit back into its OWN party
    (party index = [cu+0x46]>>4, set only by TCombatUnit.Setup; TCombatObject.SetCombatPlayer just rewrites [cu+0x45])
    with Place flags 2 (one hex, ignore field owner).  A unit whose party belongs to another combat player (= it changed
    sides) or that has no strategic party (party nil / party x == -1) is placed in pass 2:
      TAbstractUnit.Place(unit, x, y; flags 1, player, level) at the COMBAT TARGET hex = TCombatData [+8,+0xC,+0x10]
      (call sites 0x55724EA9 / 0x55724ED1 / 0x55724F0E; flags byte 0x55724F28 = 1 = spiral allowed).
    Place 0x557810FC: spiral from the centre, radius < 30; first hex that CanPlace (0x55781008) accepts gets the unit -
    added to the own TArmyHS there (class 0x20217) or a NEW TArmyHS.  => the joined units form a new army ON THE TARGET
    hex (it is empty: the defender died).
  * TArmyCombatMoveTE.ExecuteCombat 0x55749924 afterwards splits the moving units ([unit+0x25] & 4, set before combat)
    off the army on the attacker hex (TCombatData [+0x14,+0x18,+0x1C], from TCombat.Setup 0x55727310) into a new TArmyHS
    and PlacePrivate's it (0x55791278 -> TUnitHS.PlaceHX, no merge check) onto the target hex -> two armies on one hex
    when the moving party cannot absorb the joiners.

Fix: the three pass-2 `call Place` sites -> cave.  The cave calls vanilla Place unchanged unless ALL hold:
  flags bit0 set, player != 0xFF, (x,y) == the combat target, the TArmyHS on the attacker hex belongs to the same
  player, it has >= 1 moving unit, the target hex holds no army of another player, and
      moving units + units of the own army already on the target + 1  >  TArmy.MaxSize(moving army).
Then: walk the spiral from RADIUS 1 (InitHNWalk(.., 1)), calling Place with flags & ~1 (single hex, same CanPlace rules)
per hex until one succeeds (radius < 30, as vanilla); if none does, vanilla Place (= old behaviour).  Deterministic
(map state + walk order only, no RNG) -> MP-safe.

Zone 0x55882800..0x55882C00 (CODE zero tail, no relocs).  Header = magic + the 3 sites' ORIGINAL bytes (exact revert).
PIC: rel32 calls + call/pop delta for the map global [0x558FA040].  Sites must call vanilla Place (else ABORT) - nothing
else hooks them today.  LIFO: anything chained onto these sites later must be reverted first.
Backup <game>\backup\AoWEPACK.dll.bak_overflow.  Dry-run default; --apply / --revert / --dis / --dll <copy>.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_overflow"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55882800, 0x55882C00
MAGIC = b"OVFLOW01"
SITES = (0x55724EA9, 0x55724ED1, 0x55724F0E)          # pass-2 `call TAbstractUnit.Place` in TCombatUnit.Finalize
PLACE = 0x557810FC                                   # TAbstractUnit.Place(eax unit, edx x, ecx y; flags, player, level) ret 0xC
GETFIELD = 0x557020FC                                # TMapContainer.GetFieldXYL thunk (eax cont, edx x, ecx y; level) ret 4
GETUNIT, MAXSIZE = 0x5578309C, 0x5578DEF4            # TUnitList.GetUnit(eax, edx i) / TArmy.MaxSize(eax)
INITWALK, WALKNEXT = 0x557026D4, 0x557026DC          # HSEngine.InitHNWalk(eax walk, edx x, ecx y; radius) ret 4 / WalkToNextHN(eax)
G_MAP = 0x558FA040                                   # global TAoWHSMap; [map+0x10] = TMapContainer ([+0xC] w, [+0x10] h)
ARMYHS_CID = 0x20217
HDR = 0x20                                           # magic 8 | 3 x 5 original bytes
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def cave_src():
    return """
        push ebp
        mov ebp, esp
        sub esp, 0x40
        push ebx
        push esi
        push edi
        mov [ebp-4], eax
        mov [ebp-8], edx
        mov [ebp-0xc], ecx
        call L0
    L0: pop ebx
        sub ebx, L0
        test byte ptr [ebp+8], 1
        jz vanilla
        movzx eax, byte ptr [ebp+0xc]
        cmp al, 0xff
        je vanilla
        mov [ebp-0x10], eax
        mov eax, [esi+8]
        test eax, eax
        jz vanilla
        mov edi, [eax+0xc]
        test edi, edi
        jz vanilla
        mov eax, [ebp-8]
        cmp eax, [edi+8]
        jne vanilla
        mov eax, [ebp-0xc]
        cmp eax, [edi+0xc]
        jne vanilla
        mov edx, [edi+0x14]
        mov ecx, [edi+0x18]
        test edx, edx
        jl vanilla
        test ecx, ecx
        jl vanilla
        mov eax, [ebx+%(G)#x]
        mov eax, [eax+0x10]
        cmp edx, [eax+0xc]
        jge vanilla
        cmp ecx, [eax+0x10]
        jge vanilla
        push dword ptr [edi+0x1c]
        call %(GETFIELD)#x
        test eax, eax
        jz vanilla
        mov edx, %(CID)#x
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz vanilla
        mov eax, [eax+0x1c]
        test eax, eax
        jz vanilla
        mov [ebp-0x14], eax
        mov dl, [eax+0x12]
        cmp dl, byte ptr [ebp-0x10]
        jne vanilla
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov [ebp-0x18], eax
        xor esi, esi
        mov dword ptr [ebp-0x20], 0
    cnt:
        cmp esi, [ebp-0x18]
        jge cntdone
        mov eax, [ebp-0x14]
        mov edx, esi
        call %(GETUNIT)#x
        test eax, eax
        jz cntnext
        test byte ptr [eax+0x25], 4
        jz cntnext
        inc dword ptr [ebp-0x20]
    cntnext:
        inc esi
        jmp cnt
    cntdone:
        cmp dword ptr [ebp-0x20], 0
        je vanilla
        mov edx, [edi+8]
        mov ecx, [edi+0xc]
        push dword ptr [edi+0x10]
        mov eax, [ebx+%(G)#x]
        mov eax, [eax+0x10]
        call %(GETFIELD)#x
        test eax, eax
        jz vanilla
        mov edx, %(CID)#x
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        xor esi, esi
        test eax, eax
        jz havec2
        mov eax, [eax+0x1c]
        test eax, eax
        jz havec2
        mov dl, [eax+0x12]
        cmp dl, byte ptr [ebp-0x10]
        jne vanilla
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov esi, eax
    havec2:
        add esi, [ebp-0x20]
        inc esi
        mov eax, [ebp-0x14]
        call %(MAXSIZE)#x
        cmp esi, eax
        jle vanilla
        push 1
        lea eax, [ebp-0x40]
        mov edx, [ebp-8]
        mov ecx, [ebp-0xc]
        call %(INITWALK)#x
    walk:
        cmp dword ptr [ebp-0x34], 0x1e
        jge vanilla
        push dword ptr [ebp+0x10]
        push dword ptr [ebp+0xc]
        movzx eax, byte ptr [ebp+8]
        and al, 0xfe
        push eax
        mov eax, [ebp-4]
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x2c]
        call %(PLACE)#x
        test eax, eax
        jnz done
        lea eax, [ebp-0x40]
        call %(WALKNEXT)#x
        jmp walk
    vanilla:
        push dword ptr [ebp+0x10]
        push dword ptr [ebp+0xc]
        push dword ptr [ebp+8]
        mov eax, [ebp-4]
        mov edx, [ebp-8]
        mov ecx, [ebp-0xc]
        call %(PLACE)#x
    done:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 0xc
    """ % dict(G=G_MAP, GETFIELD=GETFIELD, CID=ARMYHS_CID, GETUNIT=GETUNIT, MAXSIZE=MAXSIZE, INITWALK=INITWALK,
               WALKNEXT=WALKNEXT, PLACE=PLACE)


def build(orig):
    out = bytearray(MAGIC + b"".join(orig))
    out += bytes(HDR - len(out))
    cave = ZONE + HDR
    out += bytes(ks.asm(cave_src(), cave)[0])
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), cave


def rel_target(b, va):
    return va + 5 + struct.unpack_from("<i", b, 1)[0]


def hook(site, cave):
    return b"\xe8" + struct.pack("<i", cave - (site + 5))


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


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
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    live = [d[s - CODE_V2F:s - CODE_V2F + 5] for s in SITES]
    if zl[:8] == MAGIC:
        orig = [zl[8 + 5 * k:13 + 5 * k] for k in range(3)]; zstate = "ours"
    elif not any(zl):
        orig = list(live); zstate = "zero"
    else:
        print("ABORT: zone %#x..%#x not free" % (ZONE, ZONE_END)); return 1
    for s, o in zip(SITES, orig):
        if o[0] != 0xE8 or rel_target(o, s) != PLACE:
            print("ABORT: site %#x original bytes %s are not `call Place`" % (s, o.hex())); return 1
    zone, cave = build(orig)
    hk = [hook(s, cave) for s in SITES]
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(s - 3 <= r < s + 5 for s in SITES)]
    states = ["ours" if l == h else ("free" if l == o else "OTHER") for l, h, o in zip(live, hk, orig)]
    print("zone %s (%d B, cave %#x) | sites %s | relocs %s" % (zstate, len(zone), cave,
          dict(zip(map(hex, SITES), states)), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[HDR:], cave):
            print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT (relocs)"); return 1
    out = bytearray(d)
    if a.revert:
        if zstate != "ours": print("already vanilla (zone not ours)"); return 0
        if any(v != "ours" for v in states):
            print("ABORT: a site no longer calls the overflow cave (revert the patch chained in front first, LIFO): %s" % states); return 1
        for s, o in zip(SITES, orig): out[s - CODE_V2F:s - CODE_V2F + 5] = o
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if "OTHER" in states: print("ABORT: a site is owned by an unknown patch: %s" % states); return 1
    if all(v == "ours" for v in states) and zl[:len(zone)] == zone and not any(zl[len(zone):]):
        print("already applied"); return 0
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for s, h in zip(SITES, hk): out[s - CODE_V2F:s - CODE_V2F + 5] = h
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL) and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
