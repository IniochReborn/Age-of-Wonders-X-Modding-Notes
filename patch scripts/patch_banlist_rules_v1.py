"""patch_banlist_rules_v1.py  [--apply | --revert | --dis]

BAN LIST - game rules (user 2026-11-19).  The map carries a ban list (editor: Options > Map Settings > Ban List):
  * a banned SPELL can not be researched and is never an automatic starting spell (wizard towers, scrolls, map-maker
    spell lists and scripted grants still give it; once known it casts normally);
  * a banned ABILITY is not offered in leader customisation nor on hero/leader level-up, for humans and the AI
    (items, units, spells and map-defined heroes still have/grant it).

Interface (storage patch, another script): BAN_GET = AoWEPACK 0x558BA200 -> eax = 96-byte buffer, bytes 0..63 spell
bitset (ids 0..511), bytes 64..95 ability bitset (ids 0..255); preserves every other register.  This script refuses
to --apply while 0x558BA200 is still zero.

AoWEPACK.dll (cave zone 0x558BA600; only rel32 calls/jumps inside the module -> no PIC delta needed, no absolutes):
  S1 TPlayerMagicControl.ValidResearchSpell 0x5577CFF0 (entry, 6 B; eax pmc, edx spell, id [spell+0x10]) -> false
     for a banned spell.  The ONLY research-eligibility test: ListResearchSpells (the exe's research page, the
     new-turn "pick research" prompt, TResearchSpellAIPA.Process = the AI) all go through it.
  S2 TPlayerMagicControl.ExecuteResearchSpell 0x5577D538 (entry, 6 B; eax pmc, edx id, 0 = cancel) -> refuses a
     banned id (defence: the token event of ResearchSpell and the AI both end here).
  S3 TPlayerMagicControl.NewTurn day-1 starting spells: `call TIntegerList.IndexOf` @0x5577CCC6 (known-list test,
     edx = spell id) -> wrapper answering "already known" for a banned id, so it never enters the candidate lists
     (the three synced Random(count) picks then draw from shorter lists / are skipped when a list is empty - the
     same on every machine).
  S4 campaign catch-up grant (TAoWCampaign 0x5573217C): same IndexOf call @0x55732290 -> same wrapper.
  S5 TPlayerMagicControl.NewTurn @0x5577CD4A (`mov ebx,[esi+0x34] / test ebx,ebx`, 5 B): a banned spell that is
     somehow the current research (old save, edited map) is dropped ([+0x34] := 0, [+0x38] := 0) - the power of
     that turn goes to mana and the player is asked for a new research like after any finished research.
  A1 AI level-up chooser (THero.ExecuteUpgradeHeroAI eligibility cave 0x5580FD40, mod July 2026): its
     `call TAbilityControl.GetAbility` @0x5580FD6D -> wrapper returning nil for a banned id = the cave's own
     "ability does not exist" skip.  The weighted pick (one synced draw per upgrade) simply has fewer entries.
AoWx.exe (stub in the .xedt zone 0x62FFA0; the exe never rebases; BAN_GET is reached through the exe's IAT slot of
TAbilityControl.GetAbility 0x45DE78 + constant distance, so an AoWEPACK rebase is harmless):
  E1 TLeaderSetupWin list builder 0x4161CF, E2 TLeaderSetupWin "can take" 0x41650C (fn 0x4164EC),
  E3 THeroUpgradeDlg list builder 0x4469DD, E4 THeroUpgradeDlg "can take" 0x447084 (fn 0x447064):
     each `mov ecx,[eax] / call [ecx+0xC4]` (ability.CanExpand(owner), 8 B) -> `call stub`: false for a banned id.
  CanExpand itself is NOT gated: spells use it too (Holy/Unholy Champion ValidTargetUnit), as does the editor.

In-place apply/revert, every site state-checked (expected / ours / OTHER), .reloc scanned on every hooked range.
"""
import argparse, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLL, EXE = os.path.join(ROOT, "AoWEPACK.dll"), os.path.join(ROOT, "AoWx.exe")
SUFFIX = ".bak_banrules"
E_BASE, E_V2F = 0x55700000, 0x55700C00
BAN_GET = 0x558BA200
ZONE, ZONE_END = 0x558BA600, 0x558BAC00
INDEXOF, GETABILITY = 0x55702EA4, 0x557501C0
N_SPELLS, N_ABIL, ABIL_OFF = 0x200, 0x100, 0x40
# name: (va, expected bytes, kind, resume)       kind: "jmp" = E9 to the cave (+nops), "call" = retargeted E8
E_SITES = {
    "S1": (0x5577CFF0, "53565783c4ec", "jmp"),          # ValidResearchSpell prologue
    "S2": (0x5577D538, "53568bf28bd8", "jmp"),          # ExecuteResearchSpell prologue
    "S3": (0x5577CCC6, "e8d961f8ff", "call"),           # day-1 grant: call IndexOf
    "S4": (0x55732290, "e80f0cfdff", "call"),           # campaign grant: call IndexOf
    "S5": (0x5577CD4A, "8b5e3485db", "jmp"),            # NewTurn: current research
    "A1": (0x5580FD6D, "e84e04f4ff", "call"),           # AI level-up cave: call GetAbility
}
S1_BACK, S2_BACK, S5_BACK = 0x5577CFF6, 0x5577D53E, 0x5577CD4F

X_V2F, X_XEDT_VA, X_XEDT_FO = 0x400C00, 0x62F000, 0x228600
X_STUB, X_STUB_END = 0x62FFA0, 0x630000
X_IAT_GETABILITY = 0x45DE78
X_ORIG = bytes.fromhex("8b08ff91c4000000")
X_SITES = {"E1": 0x4161CF, "E2": 0x41650C, "E3": 0x4469DD, "E4": 0x447084}


def build_epack():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
    chk_spell:
        push eax
        push ecx
        mov ecx, eax
        call {BAN_GET:#x}
        cmp ecx, {N_SPELLS:#x}
        jae cs_r
        bt dword ptr [eax], ecx
    cs_r:
        pop ecx
        pop eax
        ret
    chk_abil:
        push eax
        push ecx
        mov ecx, eax
        call {BAN_GET:#x}
        cmp ecx, {N_ABIL:#x}
        jae ca_r
        bt dword ptr [eax + {ABIL_OFF:#x}], ecx
    ca_r:
        pop ecx
        pop eax
        ret

    s1:
        push eax
        mov eax, dword ptr [edx + 0x10]
        call chk_spell
        pop eax
        jc s1_no
        push ebx
        push esi
        push edi
        add esp, -0x14
        jmp {S1_BACK:#x}
    s1_no:
        xor eax, eax
        ret

    s2:
        test edx, edx
        jz s2_go
        push eax
        mov eax, edx
        call chk_spell
        pop eax
        jc s2_no
    s2_go:
        push ebx
        push esi
        mov esi, edx
        mov ebx, eax
        jmp {S2_BACK:#x}
    s2_no:
        xor eax, eax
        ret

    idx:
        push eax
        mov eax, edx
        call chk_spell
        pop eax
        jc idx_b
        jmp {INDEXOF:#x}
    idx_b:
        xor eax, eax
        ret

    s5:
        mov ebx, dword ptr [esi + 0x34]
        test ebx, ebx
        jz s5_r
        mov eax, ebx
        call chk_spell
        jnc s5_r
        xor ebx, ebx
        mov dword ptr [esi + 0x34], ebx
        mov dword ptr [esi + 0x38], ebx
    s5_r:
        test ebx, ebx
        jmp {S5_BACK:#x}

    ga:
        push eax
        mov eax, edx
        call chk_abil
        pop eax
        jc ga_b
        jmp {GETABILITY:#x}
    ga_b:
        xor eax, eax
        ret
    """
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code = bytes(ks.asm(src, ZONE)[0])
    lab = {}
    for name in ("s1", "s2", "idx", "s5", "ga"):
        lab[name] = struct.unpack("<I", bytes(ks.asm(src + "\n.long %s\n" % name, ZONE)[0])[-4:])[0]
    assert ZONE + len(code) <= ZONE_END
    return code, lab


def build_stub():
    """eax = ability, edx = owner (kept): replay `mov ecx,[eax]`, then CanExpand unless the ability id is banned."""
    b = bytes.fromhex("8b08" "50" "51" "8b480c")                 # mov ecx,[eax] / push eax / push ecx / mov ecx,[eax+0xC]
    b += b"\xa1" + struct.pack("<I", X_IAT_GETABILITY)           # mov eax,[IAT GetAbility]
    b += b"\x05" + struct.pack("<i", BAN_GET - GETABILITY)       # add eax, BAN_GET - GetAbility
    b += bytes.fromhex("ffd0")                                   # call eax            -> eax = ban buffer
    b += b"\x81\xf9" + struct.pack("<I", N_ABIL)                 # cmp ecx, 0x100
    b += bytes.fromhex("7304")                                   # jae +4 (CF = 0)
    b += bytes.fromhex("0fa34840")                               # bt [eax+0x40], ecx
    b += bytes.fromhex("59" "58")                                # pop ecx / pop eax
    b += bytes.fromhex("7206")                                   # jc banned
    b += bytes.fromhex("ffa1c4000000")                           # jmp [ecx+0xC4]
    b += bytes.fromhex("31c0" "c3")                              # banned: xor eax,eax / ret
    assert ABIL_OFF == 0x40 and X_STUB + len(b) <= X_STUB_END
    return b


def relocs(d, base):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; n = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(n)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    out = set()
    if not rrva: return out
    def off(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = off(rrva); end = p + rsz
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def reloc_hits(rl, va, n):
    return [hex(r) for r in rl if va - 3 <= r < va + n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    cave, lab = build_epack(); stub = build_stub()
    d = open(DLL, "rb").read(); x = open(EXE, "rb").read()
    rl_d, rl_x = relocs(d, E_BASE), relocs(x, 0x400000)
    target = {"S1": lab["s1"], "S2": lab["s2"], "S3": lab["idx"], "S4": lab["idx"], "S5": lab["s5"], "A1": lab["ga"]}
    plan, states, probs = [], {}, []
    for name, (va, exp, kind) in E_SITES.items():
        exp = bytes.fromhex(exp)
        new = (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", target[name] - (va + 5)) + b"\x90" * (len(exp) - 5)
        cur = d[va - E_V2F:va - E_V2F + len(exp)]
        states[name] = "expected" if cur == exp else "ours" if cur == new else "OTHER " + cur.hex()
        h = reloc_hits(rl_d, va, len(exp))
        if h: probs.append("%s: reloc inside the hooked bytes %s" % (name, h))
        plan.append(("dll", va - E_V2F, exp, new))
    zcur = d[ZONE - E_V2F:ZONE_END - E_V2F]
    zstate = "zero" if not any(zcur) else "ours" if zcur[:len(cave)] == cave and not any(zcur[len(cave):]) else "older build" if all(s == "ours" or s.startswith("OTHER") for s in states.values()) and any(zcur) else "FOREIGN"
    h = reloc_hits(rl_d, ZONE, ZONE_END - ZONE)
    if h: probs.append("relocs inside the cave zone %s" % h[:4])
    for name, va in X_SITES.items():
        new = b"\xe8" + struct.pack("<i", X_STUB - (va + 5)) + b"\x90\x90\x90"
        cur = x[va - X_V2F:va - X_V2F + 8]
        states[name] = "expected" if cur == X_ORIG else "ours" if cur == new else "OTHER " + cur.hex()
        h = reloc_hits(rl_x, va, 8)
        if h: probs.append("%s: reloc inside the hooked bytes %s" % (name, h))
        plan.append(("exe", va - X_V2F, X_ORIG, new))
    so = X_XEDT_FO + X_STUB - X_XEDT_VA
    scur = x[so:so + X_STUB_END - X_STUB]
    sstate = "zero" if not any(scur) else "ours" if scur[:len(stub)] == stub and not any(scur[len(stub):]) else "FOREIGN"
    ban_ready = any(d[BAN_GET - E_V2F:BAN_GET - E_V2F + 8])
    print("AoWEPACK cave %#x..%#x (%d B): %s | exe stub %#x..%#x (%d B): %s" % (ZONE, ZONE + len(cave), len(cave), zstate, X_STUB, X_STUB + len(stub), len(stub), sstate))
    print("sites:", states)
    print("BAN_GET %#x: %s" % (BAN_GET, "present" if ban_ready else "NOT PRESENT (storage patch not applied) - --apply will refuse"))
    if a.dis:
        import capstone
        cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for blob, va in ((cave, ZONE), (stub, X_STUB)):
            for i in cs.disasm(blob, va): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
            print()
    if any(s.startswith("OTHER") for s in states.values()) and not a.revert: probs.append("a site holds foreign bytes")
    if zstate == "FOREIGN" or sstate == "FOREIGN": probs.append("a cave zone holds foreign bytes")
    if probs: print("ABORT:", "; ".join(probs)); return 1
    allours = all(s == "ours" for s in states.values()) and zstate == "ours" and sstate == "ours"
    allvan = all(s == "expected" for s in states.values()) and zstate == "zero" and sstate == "zero"
    if a.revert and allvan: print("already reverted"); return 0
    if not a.revert and allours: print("already applied"); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if a.apply and not ban_ready: print("ABORT: BAN_GET %#x is empty - apply the ban-list storage patch first" % BAN_GET); return 1
    if a.apply:
        for path in (DLL, EXE):
            b = bak_path(path, SUFFIX)
            if not os.path.exists(b): shutil.copy2(path, b); print("backup ->", b)
    with open(DLL, "r+b") as f, open(EXE, "r+b") as g:
        f.seek(ZONE - E_V2F); f.write(bytes(ZONE_END - ZONE))
        g.seek(so); g.write(bytes(X_STUB_END - X_STUB))
        if a.apply:
            f.seek(ZONE - E_V2F); f.write(cave)
            g.seek(so); g.write(stub)
        for which, off, exp, new in plan:
            fh = f if which == "dll" else g
            cur = (d if which == "dll" else x)[off:off + len(exp)]
            if a.revert and cur != new: continue          # only undo our own hook
            fh.seek(off); fh.write(new if a.apply else exp)
    print("Written" if a.apply else "reverted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
