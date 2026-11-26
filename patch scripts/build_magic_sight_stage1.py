#!/usr/bin/env python3
r"""Magic Sight — STAGE 1: register the spell so it appears with the right
name / Secret sphere / cost / level (effect still = Cosmetic Surgery's; wired
for real in stage 2).

Approach (BXL Tier-1 recipe): hook the last RegisterSpell call inside
UnitSpells.RegisterUnitSpells and, after replicating it, construct one more
spell — a TCosmeticSurgery instance (the vanilla Secret ENCHANTMENT spell,
class-ref @0x557E697C, ctor @0x557E8674) — poke its fields to Magic Sight's,
and RegisterSpell it (0x55779B40, eax=control/edx=spell). Cosmetic Surgery
already carries sphere 7 (Secret), level 1, category 1; we override ID, cast
cost, and the name (raw Delphi literal via @LStrAsg @0x55701150).

Spell ID = 0xC8 (200) — above vanilla's range, frozen. Cave is PIC (call/pop
delta) so absolutes survive AoWEPACK's rebasing: class-ref and the name
literal are read as [delta+preferredVA]; all calls are rel32 (delta-invariant).

Hook: `call RegisterSpell` @0x557E8E3A (registers TDarkGift) -> `call cave`;
the cave does that same RegisterSpell first, then adds Magic Sight, then rets
into the original tail (0x557E8E3F: pop edx; pop ebx; ret).

Backup AoWEPACK.dll.bak_magicsight1. Dry-run; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_magicsight1"

VA2FILE = 0x55700C00
CAVE_BASE  = 0x55810400
CAVE_LIMIT = 0x55810600

REGISTERSPELL = 0x55779B40
ENCHANT_CLASSREF = 0x557E575C       # ptr-> TEnchantWeapon class (VMT) — clean unit-enchant
ENCHANT_CREATE   = 0x557E6D98       #   base: short range (+0x40=0xe1), enchant cast UI, icon
LSTRASG           = 0x55701150      # System.@LStrAsg (eax=dest ptr, edx=source)

H_SITE = 0x557E8E3A                 # call RegisterSpell (TDarkGift) inside RegisterUnitSpells
H_OLD  = bytes.fromhex("E8010DF9FF")   # call 0x55779B40
H_RESUME = 0x557E8E3F                  # pop edx; pop ebx; ret

SPELL_ID = 0xC8
NAME = b"Magic Sight"


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.fix32 = []; self.rel = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, tgt): self.db(0xE8); self.rel.append((len(self.buf), tgt)); self.buf += b'\0\0\0\0'
    def lea_delta(self, reg, labelname_or_va):
        # lea reg, [edi + disp32]  (edi = delta); reg in {eax..edi}
        modrm = 0x87 | (reg << 3)   # [edi + disp32]
        self.db(0x8D, modrm)
        if isinstance(labelname_or_va, str):
            self.fix32.append((len(self.buf), labelname_or_va)); self.dd(0)
        else:
            self.dd(labelname_or_va)
    def resolve(self):
        for off, tgt in self.rel:
            self.buf[off:off+4] = (tgt - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] & 0xFFFFFFFF).to_bytes(4, 'little')


def build_cave():
    a = Asm(CAVE_BASE)
    a.label('cave')
    # entry: eax=control, edx=TDarkGift spell -> replicate the displaced RegisterSpell
    a.call(REGISTERSPELL)                     # register TDarkGift (preserves ebx/esi/edi)
    a.db(0x56)                                # push esi
    a.db(0x57)                                # push edi
    # edi = load delta
    a.call(a.here() + 5)                      # call next (pushes ret = VA of pop)
    popva = a.here()
    a.db(0x5F)                                # pop edi   (edi = runtime VA of this pop)
    a.db(0x81, 0xEF); a.dd(popva)             # sub edi, preferredVA(pop)  -> edi = delta
    # create Magic Sight spell = TCosmeticSurgery.Create(class, alloc=1)
    a.db(0x33, 0xC9)                          # xor ecx, ecx
    a.db(0xB2, 0x01)                          # mov dl, 1
    a.db(0x8B, 0x87); a.dd(ENCHANT_CLASSREF)  # mov eax, [edi + classref]  (PIC read of class ptr)
    a.call(ENCHANT_CREATE)                    # -> eax = new spell (TEnchantWeapon clone)
    a.db(0x8B, 0xF0)                          # mov esi, eax   ; esi = spell
    # poke fields
    a.db(0xC7, 0x46, 0x10); a.dd(SPELL_ID)    # mov dword [esi+0x10], ID
    a.db(0xC7, 0x46, 0x14); a.dd(5)           # mov dword [esi+0x14], 5   (cast cost)
    a.db(0xC6, 0x46, 0x20, 0x07)              # mov byte  [esi+0x20], 7   (Secret sphere)
    a.db(0xC6, 0x46, 0x21, 0x01)              # mov byte  [esi+0x21], 1   (level/tier)
    a.db(0xC6, 0x46, 0x22, 0x01)              # mov byte  [esi+0x22], 1   (category)
    # name := "Magic Sight"  (LStrAsg(dest=&[esi+8], source=literal))
    a.lea_delta(2, 'litchars')                # lea edx, [edi + litchars]  (source)
    a.db(0x8D, 0x46, 0x08)                    # lea eax, [esi+8]           (dest ptr)
    a.call(LSTRASG)
    # RegisterSpell(control, spell)
    a.db(0x8B, 0xD6)                          # mov edx, esi
    a.db(0x8B, 0xC3)                          # mov eax, ebx   (control)
    a.call(REGISTERSPELL)
    a.db(0x5F)                                # pop edi
    a.db(0x5E)                                # pop esi
    a.db(0xC3)                                # ret -> 0x557E8E3F
    # ---- literal Delphi AnsiString "Magic Sight" ----
    a.dd(0xFFFFFFFF)                          # refcount = -1 (literal, @LStrAsg won't free/refcount)
    a.dd(len(NAME))                           # length
    a.label('litchars')
    a.buf += NAME + b'\x00'
    a.resolve()
    assert CAVE_BASE + len(a.buf) <= CAVE_LIMIT, "cave overflow %d" % len(a.buf)
    return bytes(a.buf) + bytes(CAVE_LIMIT - CAVE_BASE - len(a.buf))


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
    cave = build_cave()
    print("cave %d bytes @0x%X (file 0x%X)" % (len(cave.rstrip(b'\0')), CAVE_BASE, CAVE_BASE - VA2FILE))

    # ID collision sanity: scan for another spell setting +0x10 = SPELL_ID
    idpat = bytes([0xC7, 0x46, 0x10]) + struct.pack('<I', SPELL_ID)
    idpat2 = bytes([0xC7, 0x40, 0x10]) + struct.pack('<I', SPELL_ID)
    if (idpat in data or idpat2 in data):
        print("  WARN: spell ID 0x%X may already be used — pick another." % SPELL_ID)
    else:
        print("  spell ID 0x%X looks free" % SPELL_ID)

    h_off = H_SITE - VA2FILE; c_off = CAVE_BASE - VA2FILE
    hits = reloc_scan(data, [(h_off, h_off + 5), (c_off, c_off + len(cave))])
    if hits:
        print("ABORT: reloc fixups intersect patch ranges: %s" % [hex(x) for x in hits]); return 1
    print("  reloc scan clean")

    cur = bytes(data[c_off:c_off + len(cave)])
    cnew = bytes(len(cave)) if revert else cave
    if cur == cnew: print("  cave already %s" % ("clear" if revert else "applied"))
    elif cur == bytes(len(cave)) or cur[:1] == b'\xE8':
        data[c_off:c_off+len(cnew)] = cnew; print("  cave %s" % ("clearing" if revert else "ready"))
    else: print("  cave MISMATCH %s" % cur[:8].hex()); return 1

    new = H_OLD if revert else bytes([0xE8]) + (CAVE_BASE - (H_SITE + 5)).to_bytes(4, 'little', signed=True)
    cur = bytes(data[h_off:h_off+5])
    if cur == new: print("  hook already applied")
    elif cur == H_OLD or cur[0] == 0xE8:
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
