"""
Oil Spring (372) - play the cast sound (cue 0) when the gush RISE starts (2026-10-17).  AoWTCPCK.dll.

User: "oil spring sfx doesn't match gfx anymore".  Cause: a hail-class spell's cue 0 is played by the caster's cast
animation (castsnd site 0x421D91), which NextStrike only starts when STRIKE 0 launches.  The smooth gate v2
(patch_tc_oilgush_smooth_v1.py) now holds strike 0 until the rise's tick 48 (v1: 24), so DUALEF_OILSPRING.WAV began
~1.4 s after the fountain burst out of the ground (it was already 0.7 s late before).  Fix = the banshee/Flashfreeze
recipe:
  * the smooth gate's first-pass `jmp refuse` (0x447855, right after it spawns the RISE driver) -> jmp CUE (cave
    0x449E00): GetSpell(registry, 372).[+0x28] -> TSFXLibrary play, cue 0 ([map+0x129] sound flag honoured, as
    vanilla), then the original jmp.  ebx = the gate's PIC delta at that point; eax/ecx/edx are dead (refuse pops).
  * 372 added to the castsnd exclusion list (TCPCK 0x43C900, patch_tc_hellfire_portal_v1.py's cave, rebuilt with
    patch_tc_banshee_vortex_v1's castsnd_build/parse) so the cast animation at strike 0 doesn't play it again.
Pairs with DUALEF_OILSPRING.WAV v3 (timed from the rise start; _oilsfx3_integration.txt).
While applied: revert THIS before re-running / reverting patch_tc_oilgush_smooth_v1.py (it rebuilds the gate zone).
Dry-run default; --apply / --revert / --dll <copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_oilcue0.
"""
import argparse, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_tc_banshee_vortex_v1 as BV
from bakpath import bak_path, game_file

SPELL_ID = 372
CODE_V2F = 0x400C00
SITE, SITE_ORIG_TGT = 0x447855, 0x447907                  # smooth gate v2: first pass `jmp refuse`
CAVE, CAVE_END = 0x449E00, 0x449E40
SUF = ".bak_oilcue0"


def build_cave():
    src = """
        mov eax, [ebx+%(map)#x]
        cmp byte ptr [eax+0x129], 0
        je out
        mov eax, [ebx+%(reg)#x]
        mov eax, [eax]
        mov eax, [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        mov eax, [eax+0x28]
        xor edx, edx
        call %(play)#x
    out:
        jmp %(back)#x
    """ % {"map": BV.MAP_GLOBAL, "reg": BV.SPELLREG_GLOBAL, "id": SPELL_ID, "getspell": BV.GETSPELL, "play": BV.SFXPLAY, "back": SITE_ORIG_TGT}
    return bytes(BV.ks.asm(src, CAVE)[0])


def jmp(frm, to): return b"\xe9" + struct.pack("<i", to - (frm + 5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dll", default=game_file("AoWTCPCK.dll")); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    f = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    cave = build_cave(); assert len(cave) <= CAVE_END - CAVE
    sb = f(SITE, 5); cb = f(CAVE, CAVE_END - CAVE)
    site = "vanilla" if sb == jmp(SITE, SITE_ORIG_TGT) else "ours" if sb == jmp(SITE, CAVE) else "OTHER(%s)" % sb.hex()
    zone = "zero" if not any(cb) else "ours" if cb[:len(cave)] == cave and not any(cb[len(cave):]) else "FOREIGN"
    gate_ok = f(SITE - 0x11, 7) == bytes.fromhex("c7402807000000")     # mov [eax+0x28], 7 (smooth gate v2 layout)
    ids = BV.castsnd_parse(f(BV.CASTSND, BV.CASTSND_END - BV.CASTSND))
    rl = BV.reloc_set(bytes(d)); bad = [hex(r) for r in rl if CAVE <= r < CAVE_END or SITE <= r < SITE + 5]
    print("site %s | cave %s | gate layout %s | castsnd ids %s | relocs %s" % (site, zone, "ok" if gate_ok else "UNEXPECTED", ids, bad or "none"))
    if site.startswith("OTHER") or zone == "FOREIGN" or ids is None or bad or not gate_ok:
        print("ABORT"); return 1
    if a.revert:
        if site == "vanilla" and zone == "zero" and SPELL_ID not in ids: print("not applied"); return 0
        new_ids = [i for i in ids if i != SPELL_ID]
        out = d
        out[SITE - CODE_V2F:SITE - CODE_V2F + 5] = jmp(SITE, SITE_ORIG_TGT)
        out[CAVE - CODE_V2F:CAVE_END - CODE_V2F] = bytes(CAVE_END - CAVE)
    else:
        if site == "ours" and zone == "ours" and SPELL_ID in ids: print("already applied"); return 0
        new_ids = ids + ([SPELL_ID] if SPELL_ID not in ids else [])
        out = d
        out[CAVE - CODE_V2F:CAVE - CODE_V2F + len(cave)] = cave
        out[SITE - CODE_V2F:SITE - CODE_V2F + 5] = jmp(SITE, CAVE)
    cs = BV.castsnd_build(new_ids); n = BV.CASTSND_END - BV.CASTSND; assert len(cs) <= n
    out[BV.CASTSND - CODE_V2F:BV.CASTSND_END - CODE_V2F] = cs + bytes(n - len(cs))
    print("castsnd ids -> %s (%d B)" % (new_ids, len(cs)))
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bp = bak_path(a.dll, SUF)
    if a.apply and not os.path.exists(bp): shutil.copy2(a.dll, bp); print("backup ->", bp)
    BV.write_inplace(a.dll, bytes(out))
    chk = open(a.dll, "rb").read()
    assert chk == bytes(out); print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
