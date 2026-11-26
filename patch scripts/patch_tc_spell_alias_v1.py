#!/usr/bin/env python3
r"""
AoWTCPCK.dll: let cloned combat spells inherit their donor's id-keyed tactical handling (2026-10-05).

Several tactical-combat paths in AoWTCPCK switch on the SPELL ID (not the SpellTypes class), so a clone
registered under a new id falls into the generic branch.  Sites (all start with `mov eax,[eax+0x18]`, the
TE's spell id, followed by the arithmetic that feeds the switch; 6 bytes each):
  0x40B541  TCAbRangedTE setup, class 0x0A: `sub eax,0x74` - 0x74 -> [obj+0x28]=0x15 hail frames, 0x7C Ooze
            -> 0x13, else 0x23  => Hellfire's effect ran ~70% longer.
  0x40C8D0  impact: `sub eax,0x74` - only 0x74 sends map msg 0x31006 (the "hail hits walls/terrain" message;
            its handlers fetch spell 0x74 for the damage values)  => Hellfire never damaged walls.
  0x40F0E3  TCAbRangedTE.NextStrike effect setup for Spellcasting casts: `add eax,-0x64` then a 31-entry
            table for ids 100..130 (High Prayer 102 / Mind Decay 106 / Frost Beams 120 / Sacrificial Flame 128
            -> store the CASTER in [fx+0x2C]; Solar Flare 100 -> extra effect; several -> nil).  Any other id
            leaves [fx+0x2C] nil and the kind-0x25 (High Prayer class) frame handler @0x42DD41 dereferences
            it => "Error - fxHS 52 350 / Error during NewFrame" soft-lock for Bloodbath.
Each site becomes `call cave` + nop; the cave loads the id, maps it through ALIAS (new id -> donor id), does
the site's own arithmetic and returns (flags survive `ret`, so the following je/cmp behave as vanilla).
Wall damage through 0x31006 uses the DONOR's attack/damage (Great Hail 3/8 - same as Hellfire's).

ALIAS is the table to extend for future clones; SITES for further id-keyed compares.
Caves 0x43C240.. (CODE zero tail after the AoO vcall sub), PIC (rel32 + call/pop delta for the table).
Backup <game>\backup\AoWTCPCK.dll.bak_tcalias.  Surgical --revert.  Re-apply re-syncs the zone.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")   # 2026-10-11: de-baked
BAK_SUFFIX = ".bak_tcalias"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43AD00, 0x43B100      # 2026-10-14: grown again (5 cave variants now); 0x43AF00..0x43B100 verified zero + reloc-free      # 2026-10-13: moved from 0x43C240..0x43C400 (full after the 372 keep; 0x43C400 = hail-msg caves); 0x43AD00..0x43C000 verified zero + reloc-free

ALIAS = {225: 0x7C, 226: 0x74, 218: 0x74,          # Steadfast -> Great Hail (2026-10-17, 7 strikes)
         216: 0x7C,          # Mend Walls -> Ooze (2026-10-17; 19 strikes; patch_tc_mendwalls_v1.py)
         213: 0x66,          # Crosswind -> High Prayer (2026-10-16, instant class 0x25)
         207: 0x82,          # Harvest Souls -> Animate Dead (7-hex preview @0x42827A, PROC0001 nil target @0x40F0E3; 2026-10-12)
         354: 0x74,          # Hellfire   -> Great Hail
         363: 0x74,          # Holy Starfire -> Great Hail (2026-10-13, Life/Fire)
         353: 0x71,          # Ashes to Ashes -> Death Ray (2026-10-13; 113 -> the nil-[fx+0x2C] case @0x40F0E3 like its donor)
         372: 0x7C,          # Oil Spring -> Ooze (2026-10-13; hail-class frames/impact msg; KEPT at 0x40C8D0 so the landing takes patch_oilspring_v1.py's oil path, not the mud/extinguish one)
         389: 0x74,          # Implosion -> Great Hail (2026-10-14; hail-class frames + the 0x31006 landing msg that hurts walls; KEPT at 0x40B541 (default strike count -> patch_implosion_v1.py's cnt hook) and 0x42827A (single-hex preview))
         390: 0x66,          # Frenzied Charge -> High Prayer (2026-10-14; class 37: 0x40F0E3 must store the CASTER in [fx+0x2C] or the kind-0x25 NewFrame derefs nil every frame - the Blood Pact lesson)
         300: 0x66,          # Awaken Spirit -> High Prayer (2026-10-14; class-37 clone needs the alias)
         308: 0x66,          # Heavenly Chorus -> High Prayer (2026-10-16, class 37)
         208: 0x74,          # Sanctify -> Great Hail (2026-10-16, hail class, 7 strikes; zone = patch_tc_sanctify_field_v1.py)
         309: 0x74,          # Inspiration -> Great Hail (2026-10-16, hail class, 7 strikes)
         301: 0x66,          # Blessing of the Forest -> High Prayer (2026-10-14)
         333: 0x74,          # Rot Away -> Great Hail (2026-10-14; Earth/Death small AoE, 7 strikes via patch_rotaway_v1.py)
         335: 0x74,          # Thousand Threads -> Great Hail (2026-10-14)
         366: 0x74,          # Gravity Well -> Great Hail (2026-10-14; 7 strikes via patch_rotaway_v1.py, Grounded via patch_gravitywell_v1.py)
         388: 0x74,          # Sandstorm v2 -> Great Hail (2026-10-14; hail class, 0x31006 per-landing damage; the PREVIEW site 0x42827A is overridden to Ooze 0x7C = the 19-hex glow, see SITE_ALIAS)
         350: 0x66}          # Bloodbath  -> High Prayer
# Per-site exclusions: ids that keep their OWN id at that site (site VA -> set of ids).
#   0x40F0E3 NextStrike table: Great Hail's entry (PROC0001) CLEARS the strike's unit target [fx+0x2C], so vanilla
#   hail damages units only through the per-hex 0x31006 message (no elemental hit GFX - hail is physical).  A
#   hail-class clone with elemental damage must keep its own id there (-> default entry, target kept) so units
#   on the hex are hit through the strike's direct CreateCA path, which draws the damage-type GFX (MakeDEHSList);
#   empty hexes still fall through to the class switch and the 0x31006 message for walls/terrain (2026-10-05,
#   found with the --trace build of patch_tc_hail_msg_spell_v1.py: all 21 strikes went through the message).
SITE_KEEP = {0x40F0E3: {354, 363, 353, 333, 335, 366, 309, 208, 218, 226}, 0x40C8D0: {372}, 0x40B541: {389}}   # 10/15: 365 Hurl Boulder no longer aliased (kind 2 fxComet, patch_hurlboulder_v1.py)   # 2026-10-14: 389 no longer kept at the preview 0x42827A -> Great Hail 7-hex preview (Implosion = small AoE)
SITE_ALIAS = {0x42827A: {388: 0x7C, 344: 0x7C, 309: 0x82, 208: 0x82, 218: 0x82, 226: 0x82}}   # 2026-10-15: + 344 Banshee Gale (19-hex preview; class 0x2F elsewhere). 2026-10-14: per-site overrides folded into that site's table AFTER the keep filter (388 Sandstorm previews as Ooze's 19-hex area but is Great Hail everywhere else)   # 353 Ashes (2026-10-13): Death Ray's case 1 there NILs [fx+0x2C] = the unit found on the effect path, and the generic landing @0x40C32F creates the damage CA only when [fx+0x2C] is set -> no damage; the default case keeps it
# (site VA, original 6 bytes, the load the cave redoes, the arithmetic the cave redoes after the alias)
SITES = [(0x40B541, bytes.fromhex("8b401883e874"), "mov eax, [eax+0x18]", "sub eax, 0x74"),
         (0x40C8D0, bytes.fromhex("8b401883e874"), "mov eax, [eax+0x18]", "sub eax, 0x74"),
         (0x40F0E3, bytes.fromhex("8b401883c09c"), "mov eax, [eax+0x18]", "add eax, -0x64"),
         # TRangedPathHS.Show: targeting preview after the first click - table for ids 104..130 (104/106/116/117/
         # 120/129/130 -> 7-hex glow, 124/128 -> variant, others none).  eax = selected unit HS, id at +0x38.
         (0x42827A, bytes.fromhex("8b403883c098"), "mov eax, [eax+0x38]", "add eax, -0x68")]
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def cave_key(va, load, epi):
    return (load, epi, tuple(sorted(SITE_KEEP.get(va, ()))), tuple(sorted(SITE_ALIAS.get(va, {}).items())))


def build():
    out = bytearray()
    starts = {}
    for va, _orig, load, epi in SITES:
        key = cave_key(va, load, epi)
        if key in starts: continue
        # each cave owns its table (ALIAS minus the ids this site keeps), placed right before the code
        tab = {k: v for k, v in ALIAS.items() if k not in key[2]}; tab.update(dict(key[3]))
        while len(out) % 16: out.append(0)
        tva = ZONE + len(out)
        out += b"".join(struct.pack("<II", k, v) for k, v in sorted(tab.items())) + struct.pack("<II", 0, 0)
        while len(out) % 16: out.append(0)
        cva = ZONE + len(out)
        starts[key] = cva
        out += asm("""
            push ebx
            call %#x
            pop ebx
            sub ebx, %#x
            push ecx
            %s
            lea ebx, [ebx + %#x]
        look:
            mov ecx, [ebx]
            test ecx, ecx
            jz done
            cmp ecx, eax
            jne nxt
            mov eax, [ebx+4]
            jmp done
        nxt:
            add ebx, 8
            jmp look
        done:
            pop ecx
            pop ebx
            %s
            ret
        """ % (cva + 6, cva + 6, load, tva, epi), cva)
        while len(out) % 16: out.append(0)
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), starts


def hook(site_va, orig, target):
    return b"\xe8" + struct.pack("<i", target - (site_va + 5)) + b"\x90" * (len(orig) - 5)


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
    zone, starts = build()
    hooks = [(va, orig, hook(va, orig, starts[cave_key(va, load, epi)])) for va, orig, load, epi in SITES]
    live = [bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)]) for va, orig, _h in hooks]
    zl = d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)]
    rl = reloc_set(d)
    bad = [r for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(orig) for va, orig, _h in hooks)]
    def is_ours(l, va):
        return l[0] == 0xE8 and ZONE <= va + 5 + struct.unpack_from("<i", l, 1)[0] < ZONE_END
    state = ["vanilla" if l == orig else "ours" if is_ours(l, va) else "OTHER" for (va, orig, h), l in zip(hooks, live)]
    print("sites %s | zone %s | relocs %s | caves %s | alias %s keep %s" % (state, "zero" if not any(zl) else "ours" if zl == zone else "DIFFERS",
          bad or "none", ", ".join("[%s / %s keep %s] %#x" % (k[0], k[1], k[2], v) for k, v in starts.items()), ALIAS, SITE_KEEP))
    if bad or "OTHER" in state: print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for epi, s in starts.items():
            for i in md.disasm(zone[s - ZONE:], s):
                print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
                if i.mnemonic == "ret": break
    if a.revert:
        out = bytearray(d)
        for (va, orig, _h), st in zip(hooks, state):
            if st == "ours": out[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if all(s == "ours" for s in state) and zl == zone: print("already applied"); return 0
    if "vanilla" in state and "ours" not in state and any(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]):
        print("ABORT: zone not zero on a vanilla dll"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for va, orig, h in hooks: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = h
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
