"""
Magic Missile (228) - cast sound ONCE PER BOLT, at each projectile's launch (2026-10-18).  AoWTCPCK.dll.

User: "magic missile sfx sucks, improve it, and have it play once per projectile (like Magic Bolts)".
RE: the kind-6 projectile NewFrame (0x429FBB..) already has a vanilla per-projectile LAUNCH cue: on the effect's
first frame ([fx+0x10] == 0), with sound on ([map+0x129]) and param 0x34 (spellcasting), it checks
`cmp [fx+0x18], 0x7A / jne skip` (0x42A027) and plays cue 0 of spell [fx+0x18] (0x42A02D..0x42A04A).  Vanilla 0x7A
is also excluded from the caster's cast-animation cue (0x421D87), so it sounds once per projectile, never at the cast.
Fix (two parts, both exact-revertable):
  * SITE 0x42A027 (6 B `cmp dword [eax+0x18],0x7A / jne 0x42A04F`) -> `jmp CAVE / nop`; CAVE (0x44D000) =
    0x7A or 228 -> 0x42A02D (play cue 0), else -> 0x42A04F.  eax = the effect at that point; flags/regs as vanilla.
  * 228 appended to the castsnd exclusion list (TCPCK 0x43C900, patch_tc_banshee_vortex_v1 castsnd_build/parse) so
    the cast animation at strike 0 no longer plays cue 0 too (no doubling).
Cue 1 (DUALCO_MMHIT, per landing at 0x42A0A2) is unchanged.  Sound only -> MP-safe (no RNG: cue 0 must stay a SINGLE
sound, not a list - a list pick calls System.Random in SoundP, which would desync when players' sound settings differ).
LIFO: other castsnd users (banshee / hurlboulder / oil cue0) rebuild the list from the live ids, so order is free;
revert THIS before re-running anything that rewrites the bytes at 0x42A027.
v2 (10/18): strike-pacing hook 0x40CBBD -> 0x44D040 (228 waited 2x Random(3)+4).  v3 (10/18, user: "evenly spaced"):
228 waits a FIXED PACE ticks (the synced Random call still runs; only its result is replaced) -> identical gaps.
Dry-run default; --apply / --revert / --dll <copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_mmissile.
"""
import argparse, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_tc_banshee_vortex_v1 as BV
from bakpath import bak_path, game_file

SPELL_ID = 228
CODE_V2F = 0x400C00
SITE, SITE_VANILLA = 0x42A027, bytes.fromhex("8378187a7522")
PLAY, SKIP = 0x42A02D, 0x42A04F
CAVE, CAVE_END = 0x44D000, 0x44D040
SITE2, SITE2_VANILLA = 0x40CBBD, bytes.fromhex("83c0047105")     # v2: strike pacing reload (add eax,4 / jno 0x40CBC7)
SITE2_RET = 0x40CBC7
CAVE2, CAVE2_END = 0x44D040, 0x44D080
SUF = ".bak_mmissile"
SUF2 = ".bak_mmissile2"
SUF3 = ".bak_mmissile3"
PACE = 10                              # v3: fixed ticks between Magic Missile bolts (~0.29 s at ~34.5 ticks/s)


def build_cave():
    src = """
        cmp dword ptr [eax+0x18], 0x7a
        je %(play)#x
        cmp dword ptr [eax+0x18], %(id)d
        je %(play)#x
        jmp %(skip)#x
    """ % {"play": PLAY, "skip": SKIP, "id": SPELL_ID}
    return bytes(BV.ks.asm(src, CAVE)[0])


def site_bytes(): return b"\xe9" + struct.pack("<i", CAVE - (SITE + 5)) + b"\x90"


def build_cave2_v2():
    """v2 (kept only to recognise / upgrade the older build): 228 waits 2x Random(3)+4 = 8..12 ticks."""
    src = """
        add eax, 4
        mov edx, dword ptr [ebp-4]
        cmp dword ptr [edx+0x18], %(id)d
        jne c2_out
        add eax, eax
    c2_out:
        jmp %(ret)#x
    """ % {"id": SPELL_ID, "ret": SITE2_RET}
    return bytes(BV.ks.asm(src, CAVE2)[0])


def build_cave2():
    """v3 (10/18, user: "projectiles should be EVENLY spaced, the timing is weird now"): the synced Random(3) call at
    0x40CBB3..0x40CBB8 still runs (RNG sequence / MP sync unchanged) but for 228 its result is overridden with a FIXED
    PACE ticks, so every gap between bolts is identical; other spells keep vanilla Random(3)+4."""
    src = """
        mov edx, dword ptr [ebp-4]
        cmp dword ptr [edx+0x18], %(id)d
        jne c2_van
        mov eax, %(pace)d
        jmp %(ret)#x
    c2_van:
        add eax, 4
        jmp %(ret)#x
    """ % {"id": SPELL_ID, "ret": SITE2_RET, "pace": PACE}
    return bytes(BV.ks.asm(src, CAVE2)[0])


def site2_bytes(): return bytes([0xE9]) + struct.pack("<i", CAVE2 - (SITE2 + 5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dll", default=game_file("AoWTCPCK.dll")); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    f = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    cave = build_cave(); assert len(cave) <= CAVE_END - CAVE
    cave2 = build_cave2(); assert len(cave2) <= CAVE2_END - CAVE2
    s2 = f(SITE2, 5); c2 = f(CAVE2, CAVE2_END - CAVE2)
    site2 = "vanilla" if s2 == SITE2_VANILLA else "ours" if s2 == site2_bytes() else "OTHER(%s)" % s2.hex()
    cave2_v2 = build_cave2_v2()
    zone2 = ("zero" if not any(c2) else "ours" if c2[:len(cave2)] == cave2 and not any(c2[len(cave2):])
             else "ours(v2)" if c2[:len(cave2_v2)] == cave2_v2 and not any(c2[len(cave2_v2):]) else "FOREIGN")
    sb = f(SITE, 6); cb = f(CAVE, CAVE_END - CAVE)
    site = "vanilla" if sb == SITE_VANILLA else "ours" if sb == site_bytes() else "OTHER(%s)" % sb.hex()
    zone = "zero" if not any(cb) else "ours" if cb[:len(cave)] == cave and not any(cb[len(cave):]) else "FOREIGN"
    ids = BV.castsnd_parse(f(BV.CASTSND, BV.CASTSND_END - BV.CASTSND))
    rl = BV.reloc_set(bytes(d)); bad = [hex(r) for r in rl if CAVE - 3 <= r < CAVE2_END or SITE - 3 <= r < SITE + 6
                                         or SITE2 - 3 <= r < SITE2 + 5]
    print("site %s | cave %s | pacing site %s | pacing cave %s | castsnd ids %s | relocs %s" % (
        site, zone, site2, zone2, ids, bad or "none"))
    if site.startswith("OTHER") or zone == "FOREIGN" or site2.startswith("OTHER") or zone2 == "FOREIGN" or ids is None or bad:
        print("ABORT"); return 1
    if a.revert:
        if site == "vanilla" and zone == "zero" and site2 == "vanilla" and zone2 == "zero" and SPELL_ID not in ids:
            print("not applied"); return 0
        new_ids = [i for i in ids if i != SPELL_ID]
        d[SITE - CODE_V2F:SITE - CODE_V2F + 6] = SITE_VANILLA
        d[CAVE - CODE_V2F:CAVE_END - CODE_V2F] = bytes(CAVE_END - CAVE)
        d[SITE2 - CODE_V2F:SITE2 - CODE_V2F + 5] = SITE2_VANILLA
        d[CAVE2 - CODE_V2F:CAVE2_END - CODE_V2F] = bytes(CAVE2_END - CAVE2)
    else:
        if site == "ours" and zone == "ours" and site2 == "ours" and zone2 == "ours" and SPELL_ID in ids:
            print("already applied (v3)"); return 0
        if site == "ours" and site2 == "vanilla": print("in-place upgrade v1 -> v3 (adds the strike-pacing hook)")
        if zone2 == "ours(v2)": print("in-place upgrade v2 -> v3 (fixed %d-tick bolt pacing)" % PACE)
        new_ids = ids + ([SPELL_ID] if SPELL_ID not in ids else [])
        d[CAVE - CODE_V2F:CAVE - CODE_V2F + len(cave)] = cave
        d[SITE - CODE_V2F:SITE - CODE_V2F + 6] = site_bytes()
        d[CAVE2 - CODE_V2F:CAVE2_END - CODE_V2F] = bytes(CAVE2_END - CAVE2)
        d[CAVE2 - CODE_V2F:CAVE2 - CODE_V2F + len(cave2)] = cave2
        d[SITE2 - CODE_V2F:SITE2 - CODE_V2F + 5] = site2_bytes()
    cs = BV.castsnd_build(new_ids); n = BV.CASTSND_END - BV.CASTSND
    if len(cs) > n: print("ABORT (castsnd cave full: %d of %d B)" % (len(cs), n)); return 1
    d[BV.CASTSND - CODE_V2F:BV.CASTSND_END - CODE_V2F] = cs + bytes(n - len(cs))
    print("castsnd list -> %s (%d of %d B)" % (new_ids, len(cs), n))
    if not (a.apply or a.revert):
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, SUF3 if (a.apply and zone2 == "ours(v2)") else SUF2 if (a.apply and site == "ours" and site2 == "vanilla") else SUF)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    BV.write_inplace(a.dll, bytes(d))
    chk = open(a.dll, "rb").read()
    assert chk == bytes(d)
    print("written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
