#!/usr/bin/env python3
r"""patch_vortex_v1.py -- Vortex rebalance + movement-point drain (AoWEPACK.dll, 410).

Vanilla TVortexTE.Execute @0x557A13CC (damage pass, token phase 0x50, after the whirlpool animation):
per unit of the army that was on the target hex --
  * skip if movement type has Flying / Floating / Wind Walking (bit 2 of GetMovementTypes)  [kept]
  * damage rating 7 if Swimming (ability 2), else 10 if Sailing (0x17), else 0 (no roll at all)
  * ExecuteDamageRole(attack 8, rating, physical) clamped to HP, applied via SetHitPoints

New (2026-09-13, user spec):
  * attack 10 (was 8)
  * rating: Sailing 7, Swimming 5, every other non-flying unit 2 (was 10 / 7 / 0)
  * every unit that actually took damage also loses RandInt(N) movement points, N = 9 for Sailing
    (0..8), 13 for Swimming (0..12), 7 otherwise (0..6), clamped to the unit's current points
    (GetMovePoints VMT+0xD8 -> AL, SetMovePoints VMT+0xDC dl; THero.SetMovePoints does not clamp
    negatives itself, hence the min()). Flying group still skipped, unchanged.

Four sites, three caves (rel32 only, or call/pop delta for the two globals -- rebase-safe):
  A  0x557A1605..0x557A163B  the 54-byte ability classifier -> cave_rating (jmp + nops)
  B  0x557A1645              attack immediate 8 -> 10 (one byte, in place)
  C  0x557A168C..0x557A1692  `mov byte [ebp-0xA],1; jmp` (damage-dealt tail) -> cave_drain
  D  0x557A150C..0x557A1511  start of the phase-0x50 damage pass -> cave_reseed

RandInt = VCL30 System.@RandInt thunk @0x55701080 (eax=N -> eax in 0..N-1), the same primitive
the damage roll itself draws from two instructions earlier.

  ** Why D exists (found live 2026-09-13 with vortex_probe.py). ** The whirlpool's paint routine
  (0x557A1178, called per animation frame) does `System.RandSeed := map[+0x22C]` -- a fixed
  per-game value -- so when the damage pass runs right after the animation the RAW generator
  always starts from the same seed. The first unit processed (the transporter, so every ship)
  therefore always rolled the same damage AND a drain of 0; passengers, further down the draw
  sequence, looked random. cave_reseed does BXL's reseed bridge at the top of the damage pass:
  `System.RandSeed := TAoWHSMap.Random(map, $FFFFFF)` (0x5577827C, the synced/persistent map
  RNG that also keeps multiplayer peers in lockstep), guarded exactly like Random itself guards
  (map flag 0x3C&8 -> raw path OK; else 0x55775608(map) must allow a synced draw, otherwise the
  bridge is skipped rather than tripping Random's assertion).

Cave zone 0x55815C00..0x55815D7F (zero, .reloc-free; caster-cost wallet caves end at 0x55815B8F).
Dry-run default; --apply (writes every site still vanilla, so an older install upgrades in place);
--revert (restores every site currently patched); --dll <path>; --dis.
Backup: AoWEPACK.dll.bak_vortex
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_vortex"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE, FILE_DELTA = 0x55700000, 0x55700C00

RANDINT   = 0x55701080
SITE_A    = 0x557A1605          # classifier start
SITE_A_END= 0x557A163B          # `push word [0x557a176c]` (damage-type push) - resume here
SITE_B    = 0x557A1645          # imm8 of `mov edx,8`
SITE_C    = 0x557A168C          # mov byte [ebp-0xA],1 ; jmp 0x557A1694
SITE_C_RESUME = 0x557A1694
SITE_D    = 0x557A150C          # mov ebx,[esi+0x2C]; test ebx,ebx   (first instrs of the damage pass)
SITE_D_RESUME = 0x557A1511
MAP_GLOBAL    = 0x558FA040      # [g] = TAoWHSMap                      (PIC delta needed)
RANDSEED_IAT  = 0x558FB720      # [g] = &System.RandSeed (VCL30 import)
MAP_RANDOM    = 0x5577827C      # TAoWHSMap.Random(eax=map, edx=range) -> eax
MAP_CANSYNC   = 0x55775608      # (eax=map) -> al: synced draw allowed right now
CAVE_LO, CAVE_HI = 0x55815C00, 0x55815D80

ATTACK              = 10
RATING_SAIL, RATING_SWIM, RATING_OTHER = 7, 5, 2
DRAIN_SAIL, DRAIN_SWIM, DRAIN_OTHER    = 9, 13, 7      # RandInt(N) -> 0..N-1

ORIG_A = bytes.fromhex(
    "ba02000000 8bc7 8b08 ff9148010000 84c0 7407 bb07000000 eb1c"
    "ba17000000 8bc7 8b08 ff9148010000 84c0 7407 bb0a000000 eb02 33db".replace(" ", ""))
ORIG_B = b"\x08"
ORIG_C = b"\xc6\x45\xf6\x01\xeb\x02"
ORIG_D = b"\x8b\x5e\x2c\x85\xdb"
assert len(ORIG_A) == SITE_A_END - SITE_A == 54


class Asm:
    def __init__(self, va): self.va, self.buf, self.lab, self.fix = va, bytearray(), {}, []
    def here(self): return self.va + len(self.buf)
    def db(self, *b): self.buf += bytes(b); return self
    def dd(self, v): self.buf += struct.pack("<I", v & 0xFFFFFFFF); return self
    def call(self, t): self.db(0xE8); self.buf += struct.pack("<i", t - (self.here() + 4)); return self
    def jmp(self, t): self.db(0xE9); self.buf += struct.pack("<i", t - (self.here() + 4)); return self
    def label(self, n): self.lab[n] = self.here()
    def j8(self, op, n): self.db(op); self.fix.append((len(self.buf), n)); self.db(0)
    def done(self):
        for off, n in self.fix:
            rel = self.lab[n] - (self.va + off + 1); assert -128 <= rel <= 127
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)


def abil_enabled(a, abil_id, lbl):
    """edi = unit.  al = GetAbilityEnabled(id) via item-aware VMT+0x148; jne lbl."""
    a.db(0xBA); a.dd(abil_id)                       # mov edx,id
    a.db(0x8B, 0xC7)                                # mov eax,edi
    a.db(0x8B, 0x08)                                # mov ecx,[eax]
    a.db(0xFF, 0x91); a.dd(0x148)                   # call [ecx+0x148]
    a.db(0x84, 0xC0)                                # test al,al
    a.j8(0x75, lbl)


def build_cave_rating(va):
    a = Asm(va)
    abil_enabled(a, 2, "swim")
    abil_enabled(a, 0x17, "sail")
    a.db(0xBB); a.dd(RATING_OTHER); a.j8(0xEB, "done")
    a.label("swim"); a.db(0xBB); a.dd(RATING_SWIM); a.j8(0xEB, "done")
    a.label("sail"); a.db(0xBB); a.dd(RATING_SAIL)
    a.label("done"); a.jmp(SITE_A_END)
    return a.done()


def build_cave_drain(va):
    a = Asm(va)
    a.db(0xC6, 0x45, 0xF6, 0x01)                    # mov byte [ebp-0xA],1   (replayed)
    a.db(0x53)                                      # push ebx               ; damage, read by the report
    abil_enabled(a, 2, "swim")
    abil_enabled(a, 0x17, "sail")
    a.db(0xB8); a.dd(DRAIN_OTHER); a.j8(0xEB, "roll")
    a.label("swim"); a.db(0xB8); a.dd(DRAIN_SWIM); a.j8(0xEB, "roll")
    a.label("sail"); a.db(0xB8); a.dd(DRAIN_SAIL)
    a.label("roll"); a.call(RANDINT)                # eax = 0..N-1
    a.db(0x8B, 0xD8)                                # mov ebx,eax            ; drain
    a.db(0x85, 0xDB); a.j8(0x74, "out")             # nothing to drain
    a.db(0x8B, 0xC7); a.db(0x8B, 0x10)              # mov eax,edi; mov edx,[eax]
    a.db(0xFF, 0x92); a.dd(0xD8)                    # call [edx+0xD8]        ; GetMovePoints -> al
    a.db(0x0F, 0xBE, 0xC0)                          # movsx eax,al
    a.db(0x85, 0xC0); a.j8(0x7E, "out")             # <= 0 -> nothing
    a.db(0x3B, 0xD8); a.j8(0x7E, "ok")              # cmp ebx,eax; jle ok
    a.db(0x8B, 0xD8)                                # mov ebx,eax            ; drain = current
    a.label("ok"); a.db(0x2B, 0xC3)                 # sub eax,ebx
    a.db(0x8B, 0xD0)                                # mov edx,eax            ; dl = new points
    a.db(0x8B, 0xC7); a.db(0x8B, 0x08)              # mov eax,edi; mov ecx,[eax]
    a.db(0xFF, 0x91); a.dd(0xDC)                    # call [ecx+0xDC]        ; SetMovePoints
    a.label("out"); a.db(0x5B)                      # pop ebx
    a.jmp(SITE_C_RESUME)
    return a.done()


def build_cave_reseed(va):
    """System.RandSeed := TAoWHSMap.Random(map, $FFFFFF) at the top of the damage pass, guarded."""
    a = Asm(va)
    a.db(0xE8, 0, 0, 0, 0)                          # call $+5
    anchor = a.here()
    a.db(0x59)                                      # pop ecx
    a.db(0x81, 0xE9); a.dd(anchor)                  # sub ecx,anchor      ; ecx = load delta
    a.db(0x8B, 0x81); a.dd(MAP_GLOBAL)              # mov eax,[ecx+g]     ; map
    a.db(0x85, 0xC0); a.j8(0x74, "done")
    a.db(0xF6, 0x40, 0x3C, 0x08); a.j8(0x75, "draw")   # unsynced mode -> Random takes its raw path
    a.db(0x51, 0x50)                                # push ecx; push eax
    a.call(MAP_CANSYNC)                             # al = synced draw allowed
    a.db(0x0F, 0xB6, 0xD0)                          # movzx edx,al
    a.db(0x58, 0x59)                                # pop eax; pop ecx
    a.db(0x85, 0xD2); a.j8(0x74, "done")            # not allowed -> leave the seed alone
    a.label("draw")
    a.db(0x51)                                      # push ecx
    a.db(0xBA); a.dd(0xFFFFFF)                      # mov edx,0xFFFFFF
    a.call(MAP_RANDOM)                              # eax = synced value (advances map[+0x230])
    a.db(0x59)                                      # pop ecx
    a.db(0x8B, 0x91); a.dd(RANDSEED_IAT)            # mov edx,[ecx+iat]   ; &System.RandSeed
    a.db(0x89, 0x02)                                # mov [edx],eax
    a.label("done")
    a.db(0x8B, 0x5E, 0x2C)                          # mov ebx,[esi+0x2C]  (replayed)
    a.db(0x85, 0xDB)                                # test ebx,ebx        (flags used by the je)
    a.jmp(SITE_D_RESUME)
    return a.done()


def layout():
    p = CAVE_LO
    r = build_cave_rating(p); cave_r = p; p = (p + len(r) + 3) & ~3
    d = build_cave_drain(p);  cave_d = p; p = (p + len(d) + 3) & ~3
    s = build_cave_reseed(p); cave_s = p; p = (p + len(s) + 3) & ~3
    assert p <= CAVE_HI
    def jmp(src, dst): return b"\xE9" + struct.pack("<i", dst - (src + 5))
    patches = [
        (SITE_A, ORIG_A, jmp(SITE_A, cave_r) + b"\x90" * (len(ORIG_A) - 5), "A  classifier -> cave_rating"),
        (SITE_B, ORIG_B, bytes([ATTACK]), "B  attack 8 -> %d" % ATTACK),
        (SITE_C, ORIG_C, jmp(SITE_C, cave_d) + b"\x90", "C  damage-dealt tail -> cave_drain"),
        (SITE_D, ORIG_D, jmp(SITE_D, cave_s), "D  damage-pass entry -> cave_reseed"),
        (cave_r, bytes(len(r)), r, "cave_rating"),
        (cave_d, bytes(len(d)), d, "cave_drain"),
        (cave_s, bytes(len(s)), s, "cave_reseed"),
    ]
    return patches, [(cave_r, r, "cave_rating"), (cave_d, d, "cave_drain"), (cave_s, s, "cave_reseed")], p


def relocs(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    rva, size = struct.unpack_from("<II", data, pe + 24 + 96 + 5 * 8)
    p = va2off(data, BASE + rva); end = p + size; out = set()
    while p < end:
        pg, blk = struct.unpack_from("<II", data, p)
        if blk < 8: break
        for k in range(8, blk, 2):
            e = struct.unpack_from("<H", data, p + k)[0]
            if e >> 12 == 3: out.add(BASE + pg + (e & 0xFFF))
        p += blk
    return out


def va2off(data, va):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        vsz, sva, rsz, praw = struct.unpack_from("<IIII", data, o + 8)
        if BASE + sva <= va < BASE + sva + max(vsz, rsz):
            return praw + (va - BASE - sva)
    raise ValueError("VA %08X" % va)


def disasm(code, va):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return "  (capstone not installed)"
    return "\n".join("  %08X  %-20s %-6s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str)
                     for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, va))


def write_inplace(path, data):
    assert len(data) == os.path.getsize(path)
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.flush(); os.fsync(f.fileno())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    args = ap.parse_args()
    dll = os.path.abspath(args.dll); bak = bak_path(dll, BAK_SUFFIX)
    data = bytearray(open(dll, "rb").read())
    patches, caves, end = layout()
    print("target: %s\ncaves 0x%X..0x%X (%d B)" % (dll, CAVE_LO, end, end - CAVE_LO))
    print("Vortex: attack %d; rating sail %d / swim %d / other %d; drain 0..%d / 0..%d / 0..%d"
          % (ATTACK, RATING_SAIL, RATING_SWIM, RATING_OTHER, DRAIN_SAIL - 1, DRAIN_SWIM - 1, DRAIN_OTHER - 1))
    if args.dis:
        for va, body, desc in caves:
            print("\n%s @0x%X (%d B)\n%s" % (desc, va, len(body), disasm(body, va)))
    state = []
    for va, old, new, desc in patches:
        off = va2off(data, va); cur = bytes(data[off:off + len(old)])
        state.append("patched" if cur == new else "vanilla" if cur == old else "OTHER")
    for (va, old, new, desc), s in zip(patches, state):
        print("  [%-7s] %08X  %s" % (s, va, desc))
    if any(s == "OTHER" for s in state):
        print("Aborting: a site holds bytes that are neither vanilla nor this patch."); return 1
    if args.revert:
        todo = [(p, s) for p, s in zip(patches, state) if s == "patched"]
        if not todo:
            print("Nothing applied - nothing to revert."); return 1
        for (va, old, new, desc), s in todo:
            off = va2off(data, va); data[off:off + len(old)] = old
        write_inplace(dll, data); print("Reverted %d site(s)." % len(todo)); return 0
    todo = [(p, s) for p, s in zip(patches, state) if s == "vanilla"]
    if not todo:
        print("ALL ALREADY PATCHED"); return 0
    R = relocs(data)
    hits = [r for (va, old, new, desc), s in todo for r in R if va - 3 <= r < va + len(new)]
    if hits:
        print("RELOC INTERSECT: %s" % ", ".join("%08X" % h for h in hits)); return 1
    print("no .reloc entry touches any hook window or cave byte; %d site(s) to write." % len(todo))
    if not args.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak):
        shutil.copyfile(dll, bak); print("Backup: %s" % bak)
    for (va, old, new, desc), s in todo:
        off = va2off(data, va); data[off:off + len(new)] = new
        print("Patched: %s" % desc)
    write_inplace(dll, data); print("AoWEPACK.dll patched (Vortex)."); return 0


if __name__ == "__main__":
    sys.exit(main())
