#!/usr/bin/env python3
r"""Magic Sight — STAGE 3 (Part B): register the enchantment ability 0xC9.

Casting Magic Sight (stage 2) applies enchantment ability id 0xC9. That id must
exist as a real, registered TUnitEnchantmentAbility so the enchantment machinery
(dispel, upkeep, spell-tab name) works. We register a BASE TUnitEnchantmentAbility
(classref 0x5572237C) — deliberately the base class, which has NO GetAttack/
GetDamage override, so it adds no combat stats (unlike Enchant Weapon's subclass).
Its only behaviour is the base Expand, which stage 4 hooks to grant the actual
sight abilities (Night Vision 0x27 + True Seeing 0x29).

Abilities register in RegisterUnitAbilities as: `mov eax,[classref]; mov dl,1;
call Ability.Create; mov edx,eax; mov eax,ebx(control); call RegisterAbility
(0x55750238)`. We hook the `call RegisterAbility` @0x557BCC11 that registers
Enchanted Weapon: our cave first replays that RegisterAbility, then builds our
base ability (base Create @0x55765518 with eax=classref, dl=1), pokes id=0xC9 and
name="Magic Sight", and registers it too. control stays in ebx (callee-saved).

PIC delta trick (edi=delta) so the rebased classref + name literal resolve; all
calls are rel32 (delta-invariant). Backup .bak_magicsight3. Dry-run; --apply/--revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_magicsight3"

VA2FILE = 0x55700C00
CAVE_BASE  = 0x55810700
CAVE_LIMIT = 0x55810800

REGISTERABILITY = 0x55750238      # TAbilityControl.RegisterAbility(eax=control, edx=ability)
# TUnitEnchantmentAbility class-ref (effect-less base). CONFIRMED via vmtSelfPtr
# @0x55722324 -> 0x55722364 and slot alignment vs Enchanted Weapon (Create @+0x20
# =0x55765518, Expand @+0xD0=0x55765894; 63 inherited slots match, 0 bad). NOTE: an
# earlier value 0x5572237C (derived from a wrong Delphi vmtClassName offset) was
# 0x18 too high -> every high virtual call read into the class-name string -> GPF 216.
BASE_CLASSREF   = 0x55722364
BASE_CREATE     = 0x55765518      # TUnitEnchantmentAbility.Create(eax=classref, dl=1)
LSTRASG         = 0x55701150      # System.@LStrAsg(eax=dest ptr, edx=source)

H_SITE   = 0x557BCC11             # `call RegisterAbility` (registers Enchanted Weapon)
H_OLD    = bytes([0xE8]) + struct.pack('<i', REGISTERABILITY - (H_SITE + 5))

# The ability registry is a TList indexed BY id, padded with nils up to the id
# (while id>=Count: Add(nil)). A sparse/high id leaves nil gaps that crash the
# startup ability-enumeration (runtime error 216). Max vanilla+mod ability id is
# 0xA9, so Count==0xAA — registering at 0xAA appends densely (no gaps).
MS_ABILITY_ID = 0xAA
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
    def lea_delta(self, reg, va_or_label):
        self.db(0x8D, 0x87 | (reg << 3))          # lea reg, [edi + disp32]
        if isinstance(va_or_label, str):
            self.fix32.append((len(self.buf), va_or_label)); self.dd(0)
        else:
            self.dd(va_or_label)
    def resolve(self):
        for off, tgt in self.rel:
            self.buf[off:off+4] = (tgt - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] & 0xFFFFFFFF).to_bytes(4, 'little')


def build_cave():
    a = Asm(CAVE_BASE)
    # entry: eax=control, edx=Enchanted-Weapon ability (original RegisterAbility args)
    a.call(REGISTERABILITY)                    # replay original RegisterAbility(control, EnchW)
    a.db(0x56)                                 # push esi
    a.db(0x57)                                 # push edi
    # edi = load delta
    a.call(a.here() + 5)                       # call next (pushes ret = VA of pop)
    popva = a.here()
    a.db(0x5F)                                 # pop edi
    a.db(0x81, 0xEF); a.dd(popva)              # sub edi, preferredVA(pop) -> edi = delta
    # build base enchantment ability: base Create(eax=classref, dl=1, ecx=0)
    a.db(0x33, 0xC9)                           # xor ecx, ecx
    a.lea_delta(0, BASE_CLASSREF)              # lea eax, [edi + classref]
    a.db(0xBA); a.dd(1)                        # mov edx, 1   (dl=1 alloc)
    a.call(BASE_CREATE)                        # -> eax = new ability
    a.db(0x8B, 0xF0)                           # mov esi, eax
    a.db(0xC7, 0x46, 0x0C); a.dd(MS_ABILITY_ID)  # mov dword [esi+0xc], 0xC9  (ability id)
    # name := "Magic Sight"
    a.lea_delta(2, 'litchars')                 # lea edx, [edi + litchars]  (source)
    a.db(0x8D, 0x46, 0x08)                     # lea eax, [esi+8]           (dest ptr)
    a.call(LSTRASG)
    # RegisterAbility(control=ebx, ability=esi)
    a.db(0x8B, 0xD6)                           # mov edx, esi
    a.db(0x8B, 0xC3)                           # mov eax, ebx
    a.call(REGISTERABILITY)
    a.db(0x5F)                                 # pop edi
    a.db(0x5E)                                 # pop esi
    a.db(0xC3)                                 # ret -> 0x557BCC16
    # ---- literal Delphi AnsiString "Magic Sight" ----
    a.dd(0xFFFFFFFF)                           # refcount = -1 (literal)
    a.dd(len(NAME))                            # length
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
