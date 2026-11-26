r"""
AI SITE EXPLORING - LEADER SAFETY (2026-10-19).  AoWEPACK.dll only.  Layer on build_ai_sitesearch.py v2.

User: "AI explores sites but they're dying early game sometimes, being too aggressive.  I thought they would only
attack if they calculated they were stronger?  I don't want to neuter them / stop them exploring.  Improve so the
AI still explores sites aggressively but doesn't get its LEADER killed so often."

AUDIT of the live v2 logic (build_ai_sitesearch.py):
  strength metric  TUnitList.GetStrength 0x55783300 = sum over units of TAbstractUnit.GetStrength 0x5577F8F4 =
                   (band[kind]+10) * [unit+0x34], [unit+0x34] = (vmt+0xC4 + 10 + vmt+0xCC) * (vmt+0xE0 + 10)
                   (cached, recomputed by the HP setter -> vmt+0xE0 is CURRENT hp: wounded units count less).
                   So the estimate is sane and HP-aware - the problem is the MARGINS:
  attraction       (cave_msgproc 0x55814A40)  group >= 1.5x roster -> priority 15..100.
  search mint      (cave_execai 0x55814780)   on-site army >= 2/3 (!) of the roster -> search (auto-combat).
                   The 2/3 bar was deliberately lax ("a group may split") - it is what sends a leader that has
                   marched up with a couple of escorts into an even-or-worse fight, and an AI that loses its leader
                   loses the game.  Nothing distinguishes the leader's stack.
FIX - leader-aware margins only; groups WITHOUT the leader keep exactly the v2 behaviour (aggressive):
  The two strength calls are re-targeted (same-length rel32) to wrappers that return an "effective" strength:
    hook A 0x558147D7 (cave_execai, `call GetStrength(army)`)      -> army_eff
    hook B 0x55814ABD (cave_msgproc, `call GetStrengthMax(group)`) -> grp_eff
  If the army/group contains the player's LEADER (IsClass TLeader, classref cell 0x557121F8, PIC):
    leader hp < 60 % of max (vmt+0xE0 / vmt+0xD0)        -> effective strength 0  (no raid at all)
    escorts (total - leader) >= 25 % of the total strength:
        mint needs   army  >= 2   x roster   (eff = ceil(S/3) vs the 2/3 bar)
        attraction   group >= 3   x roster   (eff = S/2   vs the 1.5x bar; ladder steps scale the same way)
    lone / token-escort leader:
        mint needs   army  >= 3   x roster   (eff = ceil(2S/9))
        attraction   group >= 4.5 x roster   (eff = ceil(S/3))
  Attraction is always stricter than the mint bar -> no "parked next to the site but never searches".
  Undefended (roster strength 0) sites stay free loot for everyone (v2: priority 100, always minted).
  Pure function of synced game state, no RNG -> identical on every MP peer (AIPAs run on all machines).
Zone AoWEPACK 0x5581E400..0x5581E800 (zero, reloc-free).  Dry-run default; --apply / --revert / --dis / --dll.
LIFO: revert THIS before reverting/re-running build_ai_sitesearch.py (its dry run reports the two caves FOREIGN
while this is on).  Backup <game>\backup\AoWEPACK.dll.bak_aileadsafe.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581E400, 0x5581E800
LIST_STRENGTH = 0x55783300      # TUnitList.GetStrength(eax=list, dl=kind)
UNIT_STRENGTH = 0x5577F8F4      # TAbstractUnit.GetStrength(eax=unit, dl=kind)
GC_STRENGTHMAX = 0x557389D4     # TAIGroupControl.GetStrengthMax(eax=gc, dx=mask)
GETUNIT = 0x5578309C            # TUnitList.GetUnit(eax=list, edx=idx)
ISCLASS = 0x557010C0            # System.@IsClass thunk (eax=obj, edx=class) -> al
CLS_LEADER = 0x557121F8         # TLeader classref cell (in-image -> PIC)
HOOK_A, HOOK_B = 0x558147D7, 0x55814ABD
HP_PCT, ESC_PCT = 60, 25
MAGIC = b"ALS1"

SRC = f"""
army_eff:                       ; eax = army (TUnitList), edx = kind  -> eax = effective strength
    push ebx
    push esi
    push edi
    push ebp
    mov  esi, eax
    call 0x{LIST_STRENGTH:X}
    mov  edi, eax
    mov  eax, esi
    call find_leader
    test eax, eax
    jz   a_plain
    mov  ebx, eax
    call leader_ok
    test al, al
    jz   ret_zero
    call escort_ok              ; ebx = leader, edi = total -> al
    test al, al
    jz   a_lone
    lea  eax, [edi+2]           ; escorted: ceil(S/3)  (mint at army >= 2x roster)
    xor  edx, edx
    mov  ecx, 3
    div  ecx
    jmp  fin
a_lone:
    lea  eax, [edi+edi+8]       ; lone: ceil(2S/9)  (mint at army >= 3x roster)
    xor  edx, edx
    mov  ecx, 9
    div  ecx
    jmp  fin
a_plain:
    mov  eax, edi
    jmp  fin
ret_zero:
    xor  eax, eax
fin:
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret

grp_eff:                        ; eax = TAIGroupControl, dx = kind mask -> eax = effective strength
    push ebx
    push esi
    push edi
    push ebp
    mov  esi, eax
    call 0x{GC_STRENGTHMAX:X}
    mov  edi, eax
    mov  eax, [esi+0xC]
    test eax, eax
    jz   g_plain
    call find_leader
    test eax, eax
    jz   g_plain
    mov  ebx, eax
    call leader_ok
    test al, al
    jz   ret_zero
    call escort_ok
    test al, al
    jz   g_lone
    mov  eax, edi               ; escorted: S/2  (attraction at group >= 3x roster)
    shr  eax, 1
    jmp  fin
g_lone:
    lea  eax, [edi+2]           ; lone: ceil(S/3)  (attraction at group >= 4.5x roster)
    xor  edx, edx
    mov  ecx, 3
    div  ecx
    jmp  fin
g_plain:
    mov  eax, edi
    jmp  fin

find_leader:                    ; eax = TUnitList -> eax = first TLeader in it, or 0.  saves ebx/esi/edi/ebp
    push ebx
    push esi
    push edi
    push ebp
    mov  esi, eax
    test esi, esi
    jz   fl_none
    call fl_a
fl_a:
    pop  ebp
    mov  ebp, dword ptr [ebp + 0x11111111]
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x54]   ; count
    mov  edi, eax
    xor  ebx, ebx
fl_lp:
    cmp  ebx, edi
    jge  fl_none
    mov  edx, ebx
    mov  eax, esi
    call 0x{GETUNIT:X}
    test eax, eax
    jz   fl_nx
    push eax
    mov  edx, ebp
    call 0x{ISCLASS:X}
    test al, al
    pop  eax
    jnz  fl_out
fl_nx:
    inc  ebx
    jmp  fl_lp
fl_none:
    xor  eax, eax
fl_out:
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret

leader_ok:                      ; ebx = leader -> al = 1 when hp*100 >= max*{HP_PCT}
    push esi
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0xE0]   ; current hp
    movsx esi, al
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0xD0]   ; max hp
    movsx eax, al
    imul eax, eax, {HP_PCT}
    imul esi, esi, 100
    cmp  esi, eax
    setge al
    pop  esi
    ret

escort_ok:                      ; ebx = leader, edi = total strength -> al = 1 when (total-leader)*100 >= total*{ESC_PCT}
    mov  eax, ebx
    xor  edx, edx
    call 0x{UNIT_STRENGTH:X}
    mov  edx, edi
    sub  edx, eax
    jge  eo_1
    xor  edx, edx
eo_1:
    imul edx, edx, 100
    imul eax, edi, {ESC_PCT}
    cmp  edx, eax
    setge al
    ret
"""


def build():
    src = "\n".join(ln.split(";")[0] for ln in SRC.splitlines())
    code = bytearray(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, ZONE + 4)[0])
    pic = b"\xe8\x00\x00\x00\x00\x5d"                              # call $+5 / pop ebp  (find_leader anchor)
    i = code.find(pic)
    assert i > 0 and code.count(pic) == 1
    anchor = ZONE + 4 + i + 5
    j = code.find(struct.pack("<I", 0x11111111)); assert j > 0
    code[j:j + 4] = struct.pack("<i", CLS_LEADER - anchor)
    labs = {}
    for k in range(len(code) - 11):                              # entries: push ebx/esi/edi/ebp; mov esi,eax; call X
        if bytes(code[k:k + 7]) == b"\x53\x56\x57\x55\x89\xc6\xe8":
            tgt = ZONE + 4 + k + 11 + struct.unpack_from("<i", code, k + 7)[0]
            labs[{LIST_STRENGTH: "army_eff", GC_STRENGTHMAX: "grp_eff"}[tgt]] = ZONE + 4 + k
    assert set(labs) == {"army_eff", "grp_eff"}, labs
    code = MAGIC + bytes(code)
    assert len(code) <= ZONE_END - ZONE
    return code, labs


def call_to(site, tgt):
    return b"\xe8" + struct.pack("<i", tgt - (site + 5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, labs = build()
    hooks = [(HOOK_A, call_to(HOOK_A, LIST_STRENGTH), call_to(HOOK_A, labs["army_eff"]), "cave_execai army strength"),
             (HOOK_B, call_to(HOOK_B, GC_STRENGTHMAX), call_to(HOOK_B, labs["grp_eff"]), "cave_msgproc group strength")]
    states = []
    for va, ob, nb, nm in hooks:
        c = bytes(d[va - V2F:va - V2F + 5])
        st = "v2" if c == ob else "ours" if c == nb else "FOREIGN"
        states.append(st); print("  %-30s @%#x  %s" % (nm, va, st))
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + 5 for va, *_ in hooks)]
    print("  zone %#x..%#x %s (%d B; army_eff %#x, grp_eff %#x) | relocs %s" % (ZONE, ZONE_END, zstate, len(zone), labs["army_eff"], labs["grp_eff"], bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[4:], ZONE + 4):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "FOREIGN" in states: print("ABORT (site/reloc) - is build_ai_sitesearch.py v2 applied?"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    applied = all(s == "ours" for s in states) and zstate == "ours"
    clean = all(s == "v2" for s in states) and zstate == "zero"
    if not (applied or clean): print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    if a.revert:
        for va, ob, nb, _ in hooks: n[va - V2F:va - V2F + 5] = ob
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for va, ob, nb, _ in hooks: n[va - V2F:va - V2F + 5] = nb
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aileadsafe")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
