#!/usr/bin/env python3
r"""Engine-wide heal for old maps/saves vs multilevel-converted abilities.

PROBLEM (user-reported, reproduced on keeper2.csm): the mod converted some
abilities (e.g. Lifestealing 0x76, via the generic 3-level builder cave
@0x5580E202) from flat TAbility to TMultiLevelAbility. Old maps/saves store
such an ability ONLY as a bit in the owner's ability set — no
TMultiLevelAbilityData node (level byte) attached. The engine's invariant is
"owned multilevel ability => data node exists" (GetLevel/GetName/Expand all
read the node); a unit loaded from an old map violates it and wedges turn
processing (TurnEventTE freeze).

FIX: lazy self-heal at the single funnel, AoWE.TAbilityOwner.GetAbilityData
@0x5574F1C4 (walks the [owner+0x10] data-node chain by ability id). The
function is re-implemented in a cave; on a MISS it now heals when BOTH:
  - the owner actually owns the ability (vcall [owner+0x4C] GetAbSet, a
    bounds-checked bitset test — non-virtualized, non-recursive), and
  - the registry ability (TAbilityControl.GetAbility via [AoWHSSet+0x80]) is a
    TMultiLevelAbility (System.@IsClass vs classref [0x5571DF90])
by replicating TMultiLevelAbility.Expand's own create-branch @0x55765392:
  cls = vcall [ability+0x108] (AbilityDataClass); data = ctor vcall [cls+0x20]
  [data+0xE] = ability id (word); [data+0xC] = level 1
  link: [data+8] = [owner+0x10]; [owner+0x10] = data   (AddAbilityData)
and returns the new node. Healed nodes persist into subsequent saves, so
content self-repairs everywhere (all maps, all saves, campaign, MP — the heal
is deterministic from game state, so LAN-lockstep-safe). Non-multilevel
abilities and non-owners still get NULL exactly as before.

Hook: 7 bytes at 0x5574F1C4 -> jmp cave + 2 NOP (no reloc in either range —
asserted). Cave @0x55810C80 is PIC (globals via delta; calls rel32).
Backup: AoWEPACK.dll.bak_mlheal. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_mlheal"

VA2FILE = 0x55700C00
CAVE_BASE, CAVE_LIMIT = 0x55810C80, 0x55810D80
H_SITE = 0x5574F1C4                       # TAbilityOwner.GetAbilityData entry
H_OLD  = bytes.fromhex("53568bf28b5810") # push ebx;push esi;mov esi,edx;mov ebx,[eax+0x10]
GLOB_AOWHSSET   = 0x558FA044              # -> set; +0x80 = TAbilityControl
CLSREF_MLABILITY= 0x5571DF90              # -> TMultiLevelAbility class
F_GETABILITY    = 0x557501C0              # TAbilityControl.GetAbility
F_ISCLASS       = 0x557010C0              # System.@IsClass (eax=obj, edx=class)


def build_cave():
    base = CAVE_BASE
    buf = bytearray(); rel = []; labels = {}; jcc8 = []
    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def call(t): db(0xE8); rel.append((len(buf), t)); dd(0)
    def lab(n): labels[n] = len(buf)
    def j8(op, n): db(op); jcc8.append((len(buf), n)); db(0)

    db(0x53, 0x56, 0x57)            # push ebx; push esi; push edi
    db(0x8B, 0xF8)                  # mov edi,eax (owner)
    db(0x8B, 0xF2)                  # mov esi,edx (id)
    call(base + len(buf) + 5)       # delta trick
    popva = base + len(buf)
    db(0x5B)                        # pop ebx
    db(0x81, 0xEB); dd(popva)       # sub ebx, static -> delta
    db(0x8B, 0x47, 0x10)            # mov eax,[edi+0x10] (chain head)
    lab('walk')
    db(0x85, 0xC0)                  # test eax,eax
    j8(0x74, 'miss')                # je miss
    db(0x50)                        # push eax (node)
    db(0x8B, 0x10)                  # mov edx,[eax] (vmt)
    db(0xFF, 0x52, 0x4C)            # call [edx+0x4c] (node.GetAbilityID)
    db(0x59)                        # pop ecx (node)
    db(0x3B, 0xF0)                  # cmp esi,eax
    j8(0x74, 'hit')                 # je hit
    db(0x8B, 0x41, 0x08)            # mov eax,[ecx+8] (next)
    j8(0xEB, 'walk')                # jmp walk
    lab('hit')
    db(0x8B, 0xC1)                  # mov eax,ecx
    db(0x5F, 0x5E, 0x5B, 0xC3)      # pop edi/esi/ebx; ret
    lab('miss')
    # owner owns the ability? (GetAbSet bitset test, vcall [owner+0x4C])
    db(0x8B, 0xC7)                  # mov eax,edi
    db(0x8B, 0xD6)                  # mov edx,esi
    db(0x8B, 0x08)                  # mov ecx,[eax]
    db(0xFF, 0x51, 0x4C)            # call [ecx+0x4c] -> 0/1
    db(0x85, 0xC0)                  # test eax,eax
    j8(0x74, 'null')
    # registry ability
    db(0x8B, 0x83); dd(GLOB_AOWHSSET)  # mov eax,[ebx+set] (PIC)
    db(0x8B, 0x80); dd(0x80)           # mov eax,[eax+0x80] (ability control)
    db(0x8B, 0xD6)                  # mov edx,esi
    call(F_GETABILITY)              # -> eax = ability or 0
    db(0x85, 0xC0)                  # test eax,eax
    j8(0x74, 'null')
    # is it multilevel?
    db(0x50)                        # push eax (ability)
    db(0x8B, 0x93); dd(CLSREF_MLABILITY)  # mov edx,[ebx+clsref] (PIC)
    call(F_ISCLASS)                 # -> al
    db(0x84, 0xC0)                  # test al,al
    db(0x58)                        # pop eax (ability; flags kept)
    j8(0x74, 'null')
    # create + link the level-1 data node (Expand's own recipe)
    db(0x8B, 0x10)                  # mov edx,[eax] (vmt)
    db(0xFF, 0x92); dd(0x108)       # call [edx+0x108] (AbilityDataClass) -> eax=class
    db(0x33, 0xC9)                  # xor ecx,ecx
    db(0xB2, 0x01)                  # mov dl,1
    db(0xFF, 0x50, 0x20)            # call [eax+0x20] (construct) -> eax=data
    db(0x66, 0x89, 0x70, 0x0E)      # mov [eax+0xe],si (ability id)
    db(0xC6, 0x40, 0x0C, 0x01)      # mov byte [eax+0xc],1 (level 1)
    db(0x8B, 0x4F, 0x10)            # mov ecx,[edi+0x10]
    db(0x89, 0x48, 0x08)            # mov [eax+8],ecx
    db(0x89, 0x47, 0x10)            # mov [edi+0x10],eax (link; eax = result)
    db(0x5F, 0x5E, 0x5B, 0xC3)      # pop edi/esi/ebx; ret
    lab('null')
    db(0x33, 0xC0)                  # xor eax,eax
    db(0x5F, 0x5E, 0x5B, 0xC3)      # pop edi/esi/ebx; ret

    for off, tgt in rel:
        buf[off:off+4] = (tgt - (base + off + 4)).to_bytes(4, 'little', signed=True)
    for off, n in jcc8:
        dtl = labels[n] - (off + 1)
        assert -128 <= dtl <= 127, (n, dtl)
        buf[off] = dtl & 0xFF
    assert base + len(buf) <= CAVE_LIMIT, hex(len(buf))
    return bytes(buf)


def reloc_hits(data, ranges):
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]; osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8); secs.append((va, vs, raw, rs)); p += 40
    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs): return raw + rva - va
    off = r2o(rrva); end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        for i in range((blk - 8)//2):
            w = struct.unpack_from('<H', data, off + 8 + i*2)[0]
            if w >> 12 == 0: continue
            fo = r2o(page + (w & 0xFFF))
            if fo is None: continue
            for lo, hi in ranges:
                if lo <= fo + 3 and fo < hi: hits.append(fo)
        off += blk
    return hits


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1
    d = bytearray(open(DLL, 'rb').read())
    cave = build_cave()
    h_off = H_SITE - VA2FILE; c_off = CAVE_BASE - VA2FILE
    hits = reloc_hits(bytes(d), [(h_off, h_off+7), (c_off, c_off+len(cave))])
    assert not hits, [hex(x) for x in hits]
    cur = bytes(d[h_off:h_off+7])
    assert cur == H_OLD or cur[0] == 0xE9, cur.hex()
    curc = bytes(d[c_off:c_off+len(cave)])
    assert curc == bytes(len(cave)) or curc[:3] == cave[:3], curc[:8].hex()
    d[c_off:c_off+len(cave)] = cave
    d[h_off:h_off+7] = bytes([0xE9]) + (CAVE_BASE - (H_SITE+5)).to_bytes(4, 'little', signed=True) + b'\x90\x90'
    print("cave %dB @0x%X; GetAbilityData @0x%X -> jmp cave" % (len(cave), CAVE_BASE, H_SITE))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    open(DLL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
