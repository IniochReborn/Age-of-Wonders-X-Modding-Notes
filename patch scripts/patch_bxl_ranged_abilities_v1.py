#!/usr/bin/env python3
r"""
Hurl Flaming Skull (ability 0xCC) + Shoot Black Javelin (ability 0xCD) - 2026-10-19, ported from BXL's Ziggurat
(his 0xBF 'Hurl Flaming Skull' / 0xBE 'Shoot Bane Javelin', AoWEPACK.dpl/AoWTCPCK.dpl 2026-10-19; untested by him).
Data part = patch_bxl_ranged_ability_pfs_v1.py (Ability.pfs records 214 / 215).

User spec: Hurl Flaming Skull = a Hurl Boulder variant with fire + death: 3 ATK / 8 DMG (= AoWx's Hurl Boulder 0x18),
physical / fire / death / wall damage.  Shoot Black Javelin = vanilla's Shoot Black Javelin brought back (vanilla id
0x3A is Seeker Bolts in AoWx) = Shoot Javelin's ATK / DMG (AoWx 0x39: 8 / 6) + death damage.

Vanilla machinery (RE 2026-10-19, AoWEPACK.dll = vanilla .dpl build):
  * Ranged attack abilities are ONE generic class TRangedAttackAbility (VMT 0x5571E8D4, classref [0x5571E894],
    instance 0x30) registered by 0x5576F2F8 through the stdcall ctor 0x5576ED48:
        eax = id, edx = name (AnsiString), cl = ATK (+0x2A), stack (push order) DMG (+0x29), shots (+0x2D),
        range class (+0x28; 3 = long), damage mask word (+0x2B), an unused dword (vanilla 0x6E / 0x7A / 0x7B...);
        ret 0x14.  The registry put is 0x55750238 (eax = registry, edx = ability; indexed by id).
    No TRangedAttackAbility method tests ability ids; gfx / sfx come from the Ability.pfs record (id + 10).
    Damage-mask bits: 0x01 fire, 0x20 death, 0x80 physical, 0x100 walls (Hurl Boulder 0x180, vanilla Black Javelin 0xA0).
  * Id lists in AoWEPACK that name the vanilla ranged ids:
        0x5575BB26..  unit-resource AI value: Shoot Javelin 0x39 / Shoot Black Javelin 0x3A -> +100
        0x5575BBE2..  'can reach / breach walls' +100: 1 Flying, 0x24, 0x42, 0x18 Hurl Boulder, 0x2C Cannon
        0x5577ECCC    TAbstractUnit siege flags: bit B (breach walls) = 0x75 Wall Crushing / 0x18 / 0x41 / 0x2C
    (0x5576F8xx = the matching unregister list at shutdown - left alone, like Tame/Channeler.)
  * AoWTCPCK.dll (same build as BXL's .dpl):
        AbilTypes byte table 0x467248 (reads bounded 0..255 since BXL's relocation): 1 = arrow/javelin (24-direction
          kind-1 projectile), 2 = Hurl Boulder arc.  [0xCC] / [0xCD] hold stale old-SpellTypes bytes (07 07).
        three switches on the ability id:
          SA 0x40C6EA  ranged-hit TE: 0x18 -> field msg 0x31001 at the impact hex (boulder impact), 0x2C -> 0x31002...
          SB 0x4175AD  TCAI ranged evaluation: path type by id (0x16/0x19/0x2D/0x37/0x39/0x3A.. -> 0x41761F straight,
                       0x18/0x2C -> 0x41766D lobbed/wall, 0x56..0x5A breath...; any other id -> 0x4176FB = not used!)
          SC 0x4271FD  projectile path shape (0x427630 args): 0x16/0x18/0x19 high arc, 0x2C/0x2D/0x39/0x3A flat arc,
                       0x37 / breath / default straight.
        TCAI.EvalBattle ability scans run ids 1..0xA9 only: S1 0x418A73 (ranged-attack evaluation, counter
          [ebp-0x14]), S2 0x418D1F (phase-1 offensive list; Tame v2 hook 'jmp 0x450D00' adds 0xC9), S3 0x4190FA
          (byte0 & 1 abilities - not ranged, untouched), S4 0x41977F (wall-damage list: info byte 4 bit 0 = mask 0x100).

BXL's port (audited): registration ctor 0xBE 14/11 mask 0xA0, 0xBF 8/11 mask 0x1A1 (AoWEPACK 0x5589F800/0x5589FC00
spliced on two registry calls), value-list hooks at 0x5575BB37 / 0x5575BC26 and the siege flag at 0x5577ED64 (0xBF),
TCPCK SB (both) + SC (both) aliases, AbilTypes 1/2 in his relocated table, all four scans raised to 0xC1.
  Findings: (1) he did NOT alias SA, so his skull never sends the boulder-impact message 0x31001; (2) the skull's
  slot 0 (flying projectile) is the static HitIcon COMBAT.ILB #116 (no animation); (3) raising the scans wholesale is
  only safe with a clean AbilTypes table - AoWx's 0xAA..0xCB bytes are stale (0xB4/0xBB..0xBD/0xCC.. = 7), so AoWx
  must NOT raise the bounds (the AI would treat e.g. Borrow Time 0xBB as a type-7 attack).  Ids 0xBE/0xBF are taken in
  AoWx (Crosswind-era abilities) -> AoWx uses 0xCC / 0xCD.

This patch (AoWEPACK zone 0x55817400..0x55818000 'BXR1', AoWTCPCK zone 0x451D00..0x452000 'BXR1'; originals kept in
both headers for an exact --revert):
  AoWEPACK
    REG  @0x557BCF6E call -> cave: call the previous chain head (Channeler), then ctor+register
         0xCC 'Hurl Flaming Skull'  ATK 3 DMG 8 shots 1 range 3 mask 0x1A1 (unused 0x6E like Hurl Boulder)
         0xCD 'Shoot Black Javelin' ATK 8 DMG 6 shots 1 range 3 mask 0x0A0 (unused 0x7B like vanilla 0x3A)
    VAL1 @0x5575BB37 (mov edx,0x3A) -> 0x3A || 0xCD  -> +100 (javelin value)
    VAL2 @0x5575BC26 (mov edx,0x2C) -> 0x2C || 0xCC  -> +100 (wall value)
    BRCH @0x5577ED64 (mov edx,0x2C) -> 0x2C || 0xCC  -> siege 'breach walls' flag
  AoWTCPCK
    AbilTypes[0xCC] := 2 (Hurl Boulder kind), [0xCD] := 1 (javelin kind)
    SA / SB / SC: switch ids 0xCC -> 0x18, 0xCD -> 0x39 (only for the switch decision; the real id stays everywhere else)
    S1 / S4: after id 0xA9 also run the loop body for 0xCC and 0xCD (memory compares only; no register touched)
    S2: same, chained behind Tame v2's cave (0xAA..0xC9 -> previous target = Tame's 0xC9 pass; 0xCA.. -> ours)
MP: deterministic (data / id aliasing only).  Seeker Bolts 0x3A untouched (its hooks key on 0x3A / kind 1).
LIFO: becomes the AoWEPACK reg chain head and the S2 hook owner -> revert this BEFORE patch_channeler_v1.py,
patch_tame_animal_v2/v3.py, patch_reversal_v1.py.  Dry-run default; --apply / --revert / --dis; --dll / --tcdll
<scratch copies>.  Backups (first apply): <game>\backup\AoWEPACK.dll.bak_bxlranged, AoWTCPCK.dll.bak_bxlranged.
After applying: patch_bxl_ranged_ability_pfs_v1.py --apply, then LADDER += 0xCC, 0xCD in
patch_aowx_banner_ceilings_v1.py + patch_tcablist_ceiling_v1.py and re-run both (bound -> 0xCE).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
DEFAULT_TC = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_bxlranged"
EBASE, TBASE = 0x55700000, 0x400000
EZONE, EZONE_END = 0x55817400, 0x55818000
TZONE, TZONE_END = 0x451D00, 0x452000
MAGIC = b"BXR1"
EHDR, THDR = 0x80, 0x50

CTOR, REGABIL = 0x5576ED48, 0x55750238
REG_SITE = 0x557BCF6E
VAL1_SITE, VAL1_ORIG = 0x5575BB37, bytes.fromhex("ba3a000000")
VAL2_SITE, VAL2_ORIG = 0x5575BC26, bytes.fromhex("ba2c000000")
BRCH_SITE, BRCH_ORIG = 0x5577ED64, bytes.fromhex("ba2c000000")

ABILTYPES = 0x467248
SKULL, JAV = 0xCC, 0xCD
ABIL = [  # id, name, ATK, DMG, shots, range, mask, unused, AbilTypes kind, alias for the TCPCK switches
    (SKULL, b"Hurl Flaming Skull", 3, 8, 1, 3, 0x1A1, 0x6E, 2, 0x18),
    (JAV, b"Shoot Black Javelin", 8, 6, 1, 3, 0x0A0, 0x7B, 1, 0x39),
]
SA_SITE, SA_ORIG, SA_BACK = 0x40C6EA, bytes.fromhex("8b401483f82c"), 0x40C6F0
SB_SITE, SB_ORIG, SB_BACK = 0x4175AD, bytes.fromhex("8b45a483f82d"), 0x4175B3
SC_SITE, SC_ORIG, SC_BACK = 0x4271FD, bytes.fromhex("0fbf45fc83f834"), 0x427204
SCANS = {  # name: site, counter frame offset, loop top, exit, list of extra ids, vanilla 13 bytes
    "S1": (0x418A73, -0x14, 0x41870D, 0x418A80, [SKULL, JAV], bytes.fromhex("817decaa0000000f858dfcffff")),
    "S2": (0x418D1F, -0x0C, 0x418B3E, 0x418D2C, [SKULL, JAV], bytes.fromhex("817df4aa0000000f8512feffff")),
    "S4": (0x41977F, -0x0C, 0x41958C, 0x41978C, [SKULL, JAV], bytes.fromhex("817df4aa0000000f8500feffff")),
}
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def lit(s):
    return struct.pack("<ii", -1, len(s)) + s + b"\0"


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]
    return [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * i + 8) for i in range(n)], pe


def va2off(d, va, base):
    for vs, rva, rs, ro in sections(d)[0]:
        if rva <= va - base < rva + max(vs, rs):
            return ro + va - base - rva
    raise ValueError(hex(va))


def reloc_set(d, base):
    secs, pe = sections(d)
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    p = va2off(d, base + rrva, base); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def rel(op, src, dst, n):
    return bytes([op]) + struct.pack("<i", dst - (src + 5)) + b"\x90" * (n - 5)


def jmp_target(b, site):
    return site + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


# ------------------------------------------------------------------ AoWEPACK
def build_e(prev_reg):
    out = bytearray(EHDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = EZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    names = {}
    p = 0x30
    for ab in ABIL:
        b = lit(ab[1]); out[p:p + len(b)] = b; names[ab[0]] = EZONE + p + 8; p += (len(b) + 15) & ~15
    assert p <= EHDR
    regs = ""
    for (i, nm, atk, dmg, shots, rng, mask, unused, _k, _a) in ABIL:
        regs += """
        push %(dmg)d
        push %(shots)d
        push %(rng)d
        push %(mask)#x
        push %(unused)#x
        lea edx, [esi + %(name)#x]
        mov cl, %(atk)d
        mov eax, %(id)#x
        call %(ctor)#x
        mov edx, eax
        mov eax, ebx
        call %(reg)#x""" % dict(dmg=dmg, shots=shots, rng=rng, mask=mask, unused=unused, name=names[i], atk=atk, id=i,
                                 ctor=CTOR, reg=REGABIL)
    place("reg", """
        call %(prev)#x
        push esi
        call rd
    rd:
        pop esi
        sub esi, rd
        %(regs)s
        pop esi
        ret
    """ % {"prev": prev_reg, "regs": regs})
    place("val1", """
        mov edx, 0x3a
        mov eax, dword ptr [ebx + 0x38]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne 0x5575bb48
        mov edx, %(jav)#x
        mov eax, dword ptr [ebx + 0x38]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne 0x5575bb48
        jmp 0x5575bb4b
    """ % {"jav": JAV})
    place("val2", """
        mov edx, 0x2c
        mov eax, dword ptr [ebx + 0x38]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne 0x5575bc59
        mov edx, %(sk)#x
        mov eax, dword ptr [ebx + 0x38]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne 0x5575bc59
        jmp 0x5575bc37
    """ % {"sk": SKULL})
    place("brch", """
        mov edx, 0x2c
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne 0x5577ed77
        mov edx, %(sk)#x
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne 0x5577ed77
        jmp 0x5577ed80
    """ % {"sk": SKULL})
    assert EZONE + len(out) <= EZONE_END
    return out, where


# ------------------------------------------------------------------ AoWTCPCK
def alias_lines(reg="eax"):
    s = ""
    for (i, _n, _a, _d, _s, _r, _m, _u, _k, al) in ABIL:
        s += """
        cmp %(r)s, %(i)#x
        jne n%(i)x
        mov %(r)s, %(al)#x
    n%(i)x:""" % {"r": reg, "i": i, "al": al}
    return s


def build_t(prev_s2):
    out = bytearray(THDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = TZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    place("sa", """
        mov eax, dword ptr [eax + 0x14]
        %s
        cmp eax, 0x2c
        jmp %#x
    """ % (alias_lines(), SA_BACK))
    place("sb", """
        mov eax, dword ptr [ebp - 0x5c]
        %s
        cmp eax, 0x2d
        jmp %#x
    """ % (alias_lines(), SB_BACK))
    place("sc", """
        movsx eax, word ptr [ebp - 4]
        %s
        cmp eax, 0x34
        jmp %#x
    """ % (alias_lines(), SC_BACK))
    for nm, (site, ctr, top, ext, ids, _v) in SCANS.items():
        prev = prev_s2 if nm == "S2" else None
        c = "dword ptr [ebp - %#x]" % -ctr
        src = """
        cmp %(c)s, 0xaa
        jb %(top)#x""" % {"c": c, "top": top}
        if prev:
            src += """
        cmp %(c)s, 0xca
        jb %(prev)#x""" % {"c": c, "prev": prev}
        for i in sorted(ids):
            src += """
        cmp %(c)s, %(i)#x
        jbe s%(n)s%(i)x""" % {"c": c, "i": i, "n": nm}
        src += """
        jmp %#x""" % ext
        for i in sorted(ids):
            src += """
    s%(n)s%(i)x:
        mov %(c)s, %(i)#x
        jmp %(top)#x""" % {"c": c, "i": i, "n": nm, "top": top}
        place(nm, src)
    assert TZONE + len(out) <= TZONE_END
    return out, where


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--tcdll", default=DEFAULT_TC)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read(); t = open(a.tcdll, "rb").read()
    eg = lambda va, n: bytes(d[va2off(d, va, EBASE):va2off(d, va, EBASE) + n])
    tg = lambda va, n: bytes(t[va2off(t, va, TBASE):va2off(t, va, TBASE) + n])
    ezl, tzl = eg(EZONE, EZONE_END - EZONE), tg(TZONE, TZONE_END - TZONE)
    eours, tours = ezl[:4] == MAGIC, tzl[:4] == MAGIC
    if eours != tours:
        print("ABORT - half applied (AoWEPACK %s / AoWTCPCK %s)" % (eours, tours)); return 1
    cur = {"reg": eg(REG_SITE, 5), "val1": eg(VAL1_SITE, 5), "val2": eg(VAL2_SITE, 5), "brch": eg(BRCH_SITE, 5)}
    tcur = {"ab": tg(ABILTYPES + SKULL, 2), "sa": tg(SA_SITE, 6), "sb": tg(SB_SITE, 6), "sc": tg(SC_SITE, 7)}
    for nm, sc in SCANS.items(): tcur[nm] = tg(sc[0], 13)
    if eours:
        sav = {"reg": ezl[4:9], "val1": ezl[0x0C:0x11], "val2": ezl[0x14:0x19], "brch": ezl[0x1C:0x21]}
        tsav = {"ab": tzl[4:6], "sa": tzl[8:14], "sb": tzl[0x10:0x16], "sc": tzl[0x18:0x1F],
                "S1": tzl[0x20:0x2D], "S2": tzl[0x30:0x3D], "S4": tzl[0x40:0x4D]}
    else:
        sav, tsav = dict(cur), dict(tcur)
    assert sav["reg"][0] == 0xE8, "reg site original is not a call (%s)" % sav["reg"].hex()
    for k, o in (("val1", VAL1_ORIG), ("val2", VAL2_ORIG), ("brch", BRCH_ORIG)):
        assert sav[k] == o, "%s original %s (expected %s) - another patch?" % (k, sav[k].hex(), o.hex())
    for k, o in (("sa", SA_ORIG), ("sb", SB_ORIG), ("sc", SC_ORIG)):
        assert tsav[k] == o, "%s original %s (expected %s) - another patch?" % (k, tsav[k].hex(), o.hex())
    for nm in ("S1", "S4"):
        assert tsav[nm] == SCANS[nm][5], "%s original %s - another patch?" % (nm, tsav[nm].hex())
    prev_s2 = jmp_target(tsav["S2"], SCANS["S2"][0])
    assert tsav["S2"] == SCANS["S2"][5] or (prev_s2 and tsav["S2"][5:] == b"\x90" * 8), \
        "S2 original %s - neither vanilla nor a 'jmp + 8 nop' hook" % tsav["S2"].hex()
    prev_reg = REG_SITE + 5 + struct.unpack_from("<i", sav["reg"], 1)[0]
    ezone, ew = build_e(prev_reg); tzone, tw = build_t(prev_s2)
    ezone[0:4] = MAGIC; ezone[4:9] = sav["reg"]; ezone[0x0C:0x11] = sav["val1"]; ezone[0x14:0x19] = sav["val2"]
    ezone[0x1C:0x21] = sav["brch"]
    tzone[0:4] = MAGIC; tzone[4:6] = tsav["ab"]; tzone[8:14] = tsav["sa"]; tzone[0x10:0x16] = tsav["sb"]
    tzone[0x18:0x1F] = tsav["sc"]; tzone[0x20:0x2D] = tsav["S1"]; tzone[0x30:0x3D] = tsav["S2"]; tzone[0x40:0x4D] = tsav["S4"]
    ezone, tzone = bytes(ezone), bytes(tzone)
    hook = {"reg": rel(0xE8, REG_SITE, ew["reg"], 5), "val1": rel(0xE9, VAL1_SITE, ew["val1"], 5),
            "val2": rel(0xE9, VAL2_SITE, ew["val2"], 5), "brch": rel(0xE9, BRCH_SITE, ew["brch"], 5)}
    thook = {"ab": bytes(ab[8] for ab in ABIL), "sa": rel(0xE9, SA_SITE, tw["sa"], 6), "sb": rel(0xE9, SB_SITE, tw["sb"], 6),
             "sc": rel(0xE9, SC_SITE, tw["sc"], 7)}
    for nm, sc in SCANS.items(): thook[nm] = rel(0xE9, sc[0], tw[nm], 13)
    st = {k: "ours" if cur[k] == hook[k] else "orig" if cur[k] == sav[k] else "OTHER" for k in cur}
    tst = {k: "ours" if tcur[k] == thook[k] else "orig" if tcur[k] == tsav[k] else "OTHER" for k in tcur}
    zst = lambda zl, z: "zero" if not any(zl) else "ours" if zl[:len(z)] == z and not any(zl[len(z):]) else "DIFFERS"
    ezs, tzs = zst(ezl, ezone), zst(tzl, tzone)
    er, tr = reloc_set(d, EBASE), reloc_set(t, TBASE)
    ebad = [hex(r) for r in er if EZONE - 3 <= r < EZONE_END or any(s - 3 <= r < s + 5 for s in (REG_SITE, VAL1_SITE, VAL2_SITE, BRCH_SITE))]
    tsites = [(SA_SITE, 6), (SB_SITE, 6), (SC_SITE, 7), (ABILTYPES + SKULL, 2)] + [(sc[0], 13) for sc in SCANS.values()]
    tbad = [hex(r) for r in tr if TZONE - 3 <= r < TZONE_END or any(s - 3 <= r < s + n for s, n in tsites)]
    print("%s\n  AoWEPACK %s | zone %#x %s (%d B) | prev reg head %#x | relocs %s" % (a.dll, st, EZONE, ezs, len(ezone), prev_reg, ebad or "none"))
    print("%s\n  AoWTCPCK %s | zone %#x %s (%d B) | S2 prev %s | relocs %s"
          % (a.tcdll, tst, TZONE, tzs, len(tzone), hex(prev_s2) if prev_s2 else "vanilla", tbad or "none"))
    print("  caves E " + ", ".join("%s=%#x" % kv for kv in ew.items()) + " | T " + ", ".join("%s=%#x" % kv for kv in tw.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for z, va0, h in ((ezone, EZONE, EHDR), (tzone, TZONE, THDR)):
            for i in md.disasm(z[h:], va0 + h): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if ebad or tbad or "OTHER" in list(st.values()) + list(tst.values()) or "DIFFERS" in (ezs, tzs):
        print("ABORT"); return 1
    eo, to = bytearray(d), bytearray(t)
    eput = lambda va, b: eo.__setitem__(slice(va2off(d, va, EBASE), va2off(d, va, EBASE) + len(b)), b)
    tput = lambda va, b: to.__setitem__(slice(va2off(t, va, TBASE), va2off(t, va, TBASE) + len(b)), b)
    esites = {"reg": REG_SITE, "val1": VAL1_SITE, "val2": VAL2_SITE, "brch": BRCH_SITE}
    tsite = {"ab": ABILTYPES + SKULL, "sa": SA_SITE, "sb": SB_SITE, "sc": SC_SITE}
    for nm, sc in SCANS.items(): tsite[nm] = sc[0]
    if a.revert:
        if not eours: print("nothing to revert"); return 0
        for k, va in esites.items(): eput(va, sav[k])
        for k, va in tsite.items(): tput(va, tsav[k])
        eput(EZONE, bytes(EZONE_END - EZONE)); tput(TZONE, bytes(TZONE_END - TZONE))
    else:
        if all(v == "ours" for v in list(st.values()) + list(tst.values())) and ezs == tzs == "ours":
            print("already applied"); return 0
        eput(EZONE, ezone); tput(TZONE, tzone)
        for k, va in esites.items(): eput(va, hook[k])
        for k, va in tsite.items(): tput(va, thook[k])
    print("  %d AoWEPACK bytes + %d AoWTCPCK bytes change" % (sum(1 for x, y in zip(d, eo) if x != y), sum(1 for x, y in zip(t, to) if x != y)))
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for path, data, dflt in ((a.dll, eo, DEFAULT_DLL), (a.tcdll, to, DEFAULT_TC)):
        if os.path.abspath(path) == os.path.abspath(dflt) and not a.revert:
            bak = bak_path(path, BAK_SUFFIX)
            if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
        write_inplace(path, bytes(data))
        assert open(path, "rb").read() == bytes(data)
    print("reverted (all sites restored, zones zeroed)" if a.revert else
          "Written and verified.  Next: patch_bxl_ranged_ability_pfs_v1.py --apply, then LADDER += 0xCC, 0xCD in the two"
          " ceiling scripts and re-run them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
