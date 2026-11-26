#!/usr/bin/env python3
r"""Magic Sight — STAGE 2 (Part B): apply the real "Magic Sight" enchantment.

Part A's shortcut (raw AddAbility 0x27/0x29 + early return) threw "exception
during TUnitSpellTE" because Night Vision / True Seeing are regular abilities,
not enchantments — the spell turn-event's enchantment bookkeeping (side image,
dispel/upkeep tracking) hit an unconfigured state.

Part B fix: cast applies a proper *enchantment ability* — our new effect-less
"Magic Sight" enchantment id 0xC9 (registered by stage 3) — through the SAME
full config path Enchant Weapon uses. TEnchantWeapon.ExecuteSpell @0x557E6E60
is that path; it hard-codes ability id 0x9a. We clone its exact bytes into the
cave and change only the two `mov edx,0x9a` immediates to 0xC9 (internal je/jmp
are relative and survive the copy; only the one external `call GetAbilityData`
rel32 is recomputed). Result: proper enchantment applied -> no exception, side
image shows, dispellable/upkeep, appears in the spell tab. The sight itself is
granted by stage 4 (Expand hook on 0xC9).

Entry hook @0x557E6E60 (eax=spell): if [eax+0x10]==0xC8 (Magic Sight) run the
0xC9 clone; else the displaced vanilla prologue + resume (real Enchant Weapon
untouched). Backup .bak_magicsight2. Requires stages 1+3+4. Dry-run; --apply/--revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_magicsight2"

VA2FILE = 0x55700C00
CAVE_BASE  = 0x55810600           # moved out of stage-1's zero-pad range (0x400..0x600)
CAVE_LIMIT = 0x55810700

H_SITE   = 0x557E6E60             # TEnchantWeapon.ExecuteSpell entry
H_OLD    = bytes.fromhex("558BEC5153")   # push ebp; mov ebp,esp; push ecx; push ebx
H_RESUME = 0x557E6E65             # after the displaced 5 bytes

BLOCK_LEN = 0x6E                  # 0x557E6E60..0x557E6ECD inclusive (ends at ret 8)
MAGIC_SIGHT_SPELL_ID = 0xC8
MS_ABILITY_ID        = 0xAA   # dense next-free ability id (registry is id-indexed)
EW_ABILITY_ID        = 0x9A
GETABILITYDATA       = 0x5574F1C4

# offsets within the copied ExecuteSpell block:
OFF_ID1  = 0x557E6E81 - H_SITE + 1   # imm of first  `mov edx,0x9a`
OFF_ID2  = 0x557E6E94 - H_SITE + 1   # imm of second `mov edx,0x9a`
OFF_CALL = 0x557E6E9B - H_SITE       # `call GetAbilityData` opcode (E8)


def build_cave(src_block):
    assert len(src_block) == BLOCK_LEN
    block = bytearray(src_block)
    # sanity: the two immediates we expect
    assert struct.unpack_from('<I', block, OFF_ID1)[0] == EW_ABILITY_ID, "id1 mismatch"
    assert struct.unpack_from('<I', block, OFF_ID2)[0] == EW_ABILITY_ID, "id2 mismatch"
    assert block[OFF_CALL] == 0xE8, "call opcode mismatch"
    # patch ability id 0x9a -> 0xC9 (both sites)
    struct.pack_into('<I', block, OFF_ID1, MS_ABILITY_ID)
    struct.pack_into('<I', block, OFF_ID2, MS_ABILITY_ID)

    buf = bytearray()
    # --- gate: is this the Magic Sight spell? ---
    buf += bytes([0x81, 0x78, 0x10]) + struct.pack('<I', MAGIC_SIGHT_SPELL_ID)  # cmp [eax+0x10],0xC8
    buf += bytes([0x75, 0x00])                 # jne vanilla  (rel8 fixed below)
    jne_pos = len(buf) - 1
    ms_off = len(buf)                          # copied block starts here
    # recompute the one external call rel32 for its new address
    call_addr = CAVE_BASE + ms_off + OFF_CALL
    struct.pack_into('<i', block, OFF_CALL + 1, GETABILITYDATA - (call_addr + 5))
    buf += block                               # the 0xC9 ExecuteSpell clone (ends in ret 8)
    # --- vanilla: displaced prologue + resume ---
    vanilla_off = len(buf)
    buf += H_OLD                               # push ebp; mov ebp,esp; push ecx; push ebx
    buf += bytes([0xE9]) + struct.pack('<i', H_RESUME - (CAVE_BASE + len(buf) + 5))
    # fix the jne rel8
    rel = vanilla_off - (jne_pos + 1)
    assert -128 <= rel <= 127, "jne out of range"
    buf[jne_pos] = rel & 0xFF

    assert CAVE_BASE + len(buf) <= CAVE_LIMIT, "cave overflow %d" % len(buf)
    return bytes(buf) + bytes(CAVE_LIMIT - CAVE_BASE - len(buf))


def reloc_scan(data, ranges):
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
    data = bytearray(open(TARGET, "rb").read())
    src_block = bytes(data[H_SITE - VA2FILE: H_SITE - VA2FILE + BLOCK_LEN])
    # if already hooked, the src at H_SITE is our jmp — read the block from backup instead
    if src_block[0] == 0xE9 and os.path.exists(BACKUP):
        bdata = open(BACKUP, "rb").read()
        src_block = bytes(bdata[H_SITE - VA2FILE: H_SITE - VA2FILE + BLOCK_LEN])
    cave = build_cave(src_block)
    print("cave %d bytes @0x%X (file 0x%X)" % (len(cave.rstrip(b'\0')), CAVE_BASE, CAVE_BASE - VA2FILE))

    h_off = H_SITE - VA2FILE; c_off = CAVE_BASE - VA2FILE
    hits = reloc_scan(data, [(h_off, h_off + 5), (c_off, c_off + len(cave))])
    if hits:
        print("ABORT: reloc fixups intersect patch ranges: %s" % [hex(x) for x in hits]); return 1
    print("  reloc scan clean")

    cur = bytes(data[c_off:c_off + len(cave)])
    cnew = bytes(len(cave)) if revert else cave
    if cur == cnew: print("  cave already %s" % ("clear" if revert else "applied"))
    elif cur == bytes(len(cave)) or cur[:3] == b'\x81\x78\x10':
        data[c_off:c_off+len(cnew)] = cnew; print("  cave %s" % ("clearing" if revert else "ready"))
    else: print("  cave MISMATCH %s" % cur[:8].hex()); return 1

    new = H_OLD if revert else bytes([0xE9]) + (CAVE_BASE - (H_SITE + 5)).to_bytes(4, 'little', signed=True)
    cur = bytes(data[h_off:h_off+5])
    if cur == new: print("  hook already applied")
    elif cur == H_OLD or cur[0] == 0xE9:
        data[h_off:h_off+5] = new; print("  hook ready @0x%X" % H_SITE)
    else: print("  hook MISMATCH @0x%X: %s" % (H_SITE, cur.hex())); return 1

    if not apply and not revert:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BACKUP):
        shutil.copy2(TARGET, BACKUP); print("Backup -> %s" % os.path.basename(BACKUP))
    open(TARGET, "wb").write(data); print("Written %s" % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
