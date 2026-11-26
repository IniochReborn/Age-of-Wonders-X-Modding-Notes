#!/usr/bin/env python3
r"""Magic Sight — STAGE 4 (Part B, v2): project the sight at the bitmap level.

A unit's abilities are a BITMAP (bit per ability id): HasAbility(id) tests
bit[id] ([unit+8]=bits, [unit+0xc]=count). The bitmap is (re)built from the
unit's real ability list on every recalc, and every write funnels through the
SINGLE setter TCustomAbilityList.SetAbSet @0x5574E0BC (SetAbSet(eax=list,
edx=id, cl=flag) -> bts/btr bit).

The earlier Expand approach created PERSISTENT ability-data for 0x27/0x29, so
they survived a dispel. Instead we hook the bitmap setter: when bit 0xAA (Magic
Sight enchantment) is SET, also set Night Vision 0x27 + True Seeing 0x29.

Dispel is INCREMENTAL (SetAbSet(0xAA,0), no full rebuild) — so we must also
mirror the CLEAR. To avoid stripping *innate* sight, we clear 0x27/0x29 only
when they have no backing ability-data: our projected bits set no data, so
GetAbilityData(0x27/0x29) is nil for a projected bit but non-nil for innate (or
any other real source). On clearing 0xAA we clear 0x27/0x29 iff GetAbilityData
(@0x5574F1C4) returns nil for them.

Hook overwrites the first 5 bytes (cmp edx,[eax+0xc]; jae grow) with jmp cave.
The trampoline reconstructs cmp + jae(->grow 0x5574E0D0) + jmp resume
(0x5574E0C1) so the real setter (incl. its grow path that re-enters 0x5574E0C1)
still works. Position-independent. Backup .bak_magicsight4. Dry-run; --apply/--revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_magicsight4"

VA2FILE = 0x55700C00
CAVE_BASE  = 0x55810800
CAVE_LIMIT = 0x55810900

H_SITE   = 0x5574E0BC             # TCustomAbilityList.SetAbSet entry
H_OLD    = bytes.fromhex("3b500c730f")   # cmp edx,[eax+0xc]; jae 0x5574e0d0
H_RESUME = 0x5574E0C1             # mov eax,[eax+8] (after the displaced 5 bytes)
H_GROW   = 0x5574E0D0             # grow-bitmap path (jae target)
GETABILITYDATA = 0x5574F1C4       # TAbilityOwner.GetAbilityData(eax=self, edx=id) -> eax=data|nil

MS_ABILITY_ID = 0xAA
NIGHT_VISION  = 0x27
TRUE_SEEING   = 0x29


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.rel32 = []; self.rel8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, lab): self.db(0xE8); self.rel32.append((len(self.buf), lab)); self.buf += b'\0\0\0\0'
    def call_abs(self, va): self.db(0xE8); self.rel32.append((len(self.buf), ('#', va))); self.buf += b'\0\0\0\0'
    def jmp(self, lab): self.db(0xE9); self.rel32.append((len(self.buf), lab)); self.buf += b'\0\0\0\0'
    def jmp_abs(self, va): self.db(0xE9); self.rel32.append((len(self.buf), ('#', va))); self.buf += b'\0\0\0\0'
    def jae_abs(self, va): self.db(0x0F, 0x83); self.rel32.append((len(self.buf), ('#', va))); self.buf += b'\0\0\0\0'
    def jne8(self, lab): self.db(0x75); self.rel8.append((len(self.buf), lab)); self.db(0)
    def je8(self, lab): self.db(0x74); self.rel8.append((len(self.buf), lab)); self.db(0)
    def jnz8(self, lab): self.db(0x75); self.rel8.append((len(self.buf), lab)); self.db(0)
    def set_bit(self, aid): self._bit(aid, 1)
    def clr_bit(self, aid): self._bit(aid, 0)
    def _bit(self, aid, flag):
        # SetAbSet(eax=self=ebx, edx=aid, cl=flag) via trampoline
        self.db(0x8B, 0xC3)                      # mov eax, ebx (self)
        self.db(0xBA); self.dd(aid)              # mov edx, aid
        if flag: self.db(0xB1, 0x01)             # mov cl, 1
        else:    self.db(0x32, 0xC9)             # xor cl, cl
        self.call('tramp')
    def clr_if_no_data(self, aid, skip):
        # if GetAbilityData(unit=ebx, aid)==nil: clr_bit(aid)
        self.db(0x8B, 0xC3)                      # mov eax, ebx (unit)
        self.db(0xBA); self.dd(aid)              # mov edx, aid
        self.call_abs(GETABILITYDATA)            # eax = data | nil
        self.db(0x85, 0xC0)                      # test eax, eax
        self.jnz8(skip)                          # innate/other source -> keep the bit
        self.clr_bit(aid)
        self.label(skip)
    def resolve(self):
        for off, lab in self.rel32:
            tgt = lab[1] if isinstance(lab, tuple) else self.labels[lab]
            self.buf[off:off+4] = (tgt - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.rel8:
            rel = self.labels[lab] - (self.base + off + 1)
            assert -128 <= rel <= 127, "rel8 %s" % lab
            self.buf[off] = rel & 0xFF


def build_cave():
    a = Asm(CAVE_BASE)
    # entry: eax=self(unit/list), edx=id, cl=flag
    a.db(0x81, 0xFA); a.dd(MS_ABILITY_ID)      # cmp edx, 0xAA
    a.je8('handle')                            # our id -> handle; else fall to vanilla
    # --- non-0xAA: run the real setter, returning to its caller ---
    a.label('vanilla')
    a.jmp('tramp')
    a.label('handle')
    a.db(0x84, 0xC9)                           # test cl, cl
    a.je8('clearing')                          # cl==0 -> clearing 0xAA
    # --- setting bit 0xAA: also set Night Vision + True Seeing ---
    a.db(0x53)                                  # push ebx
    a.db(0x8B, 0xD8)                            # mov ebx, eax  (self/unit)
    a.set_bit(MS_ABILITY_ID)                    # 0xAA itself (the original intent)
    a.set_bit(NIGHT_VISION)
    a.set_bit(TRUE_SEEING)
    a.db(0x5B)                                  # pop ebx
    a.db(0xC3)                                  # ret
    # --- clearing bit 0xAA: clear NV/TS too, but only if not innate/other source ---
    a.label('clearing')
    a.db(0x53)                                  # push ebx
    a.db(0x8B, 0xD8)                            # mov ebx, eax  (unit)
    a.clr_bit(MS_ABILITY_ID)                    # clear 0xAA itself
    a.clr_if_no_data(NIGHT_VISION, 'skip_nv')
    a.clr_if_no_data(TRUE_SEEING, 'skip_ts')
    a.db(0x5B)                                  # pop ebx
    a.db(0xC3)                                  # ret
    # --- trampoline: reconstruct cmp + jae(grow) + jmp resume ---
    a.label('tramp')
    a.db(0x3B, 0x50, 0x0C)                      # cmp edx, [eax+0xc]
    a.jae_abs(H_GROW)                           # jae 0x5574E0D0  (grow path)
    a.jmp_abs(H_RESUME)                         # jmp 0x5574E0C1  (mov eax,[eax+8]...)
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
    elif cur == bytes(len(cave)) or cur[:2] == b'\x81\xFA':
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
