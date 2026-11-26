#!/usr/bin/env python3
r"""
Suspend (214): the Air tier-3 COMBAT spell - "grants the target unit Flying and restricts its movement for 3 turns",
single target, enemy or friendly, long range (2026-10-16).  AoWEPACK.dll only (no TCPCK half needed).

Registered by patch_dual_sphere_spells_v1.py as a TRemedy instance (donor TRemedy, pfs 45 - like Second Wind 310:
a single-target unit spell; pokes: range 0x0C, target side mask [spell+0x3B] = 3 = own units + enemies).  TRemedy's
ValidTarget base check 0x5577ACAC (-> 0x557E87B8) only refuses machines (unit VMT+0x114 >= 2) - no owner test, so
enemies are valid as soon as the side mask lets the cursor through.

New ability 0xC3 'Suspended' = a plain TDurationAbility (VMT 0x5571DD68, Create 0x55764CD4) in duration MODE 2 = the
COMBAT-ROUND duration (the Second Wind / Inspired recipe but [+0x28] = 2):
  * the combat new-turn TE 0x5572A308 sets combatdata[+0x31] := the side whose turn starts and calls every combat
    object's VMT+0xF0 (TCombatUnit 0x55724B28 -> 0x5574FE68) -> each ability's VMT+0xF8: TDurationAbility 0x55764D8C
    (mode 2): if record[+0xD] == that side -> dec record[+0xC]; at 0 -> unit.RemoveAbility (VMT+0x98).
  * record = GetAbilityData(unit, id) 0x5574F1C4: +0xC remaining (Expand sets VMT+0x110 = 3), +0xD tick side.  Vanilla
    sets +0xD := combatdata[+0x31] (the current turn) at grant (0x55781FA9) - we do the same, so the countdown runs on
    the CASTER's turn starts: an enemy target stays suspended through its next 3 turns (removed at the start of the
    caster's 3rd turn after the cast); a friendly target for the rest of this turn + 2 more.
  * CombatDone (VMT+0xFC, the mod cave 0x55862130) removes modes 2 and 3 at combat end -> nothing survives the battle.

Hooks (AoWEPACK zone 0x5586C000..0x5586C800; the first 0x40 bytes hold the site bytes found at apply time, so
--revert restores them EXACTLY; every chained site is decoded at apply time):
  reg  splice of the `call` @0x557BCF6E (the 0x91 RegisterAbility site; Second Wind / Sanctify chain): `call prev`,
       then create + register 0xC3 'Suspended' (mode 2, [+0x24] 4, [+0x20] = the HighPrayerBlessing word).  Cave starts
       with `call prev` (E8) so the next script in front can decode us.
  ex   TRemedy.ExecuteSpell 0x557E736C (chained in front, 'cmp' layout): spell 214 -> ValidTarget (VMT+0x9C); only on
       the tactical path (return address == 0x558166D3, the caster-cost cave on TUnitSpell CA.Execute, where esi = the
       caster's TCombatUnit; checked [esi+0x4C] == caster): target ExpandAbility(0xC3) (VMT+0x94), record +0xC := 3,
       +0xD := combatdata[+0x31] (combat [cu+8] -> data [+0xC]), unit.Changed (VMT+0x90).  Re-cast refreshes to 3.
       Any other caller (fast combat...) -> no effect.  Recorded combat action -> replay / LAN deterministic.
  vt   TRemedy.ValidTarget 0x557E7434 (chained in front, 'cmp' layout): 214 -> the TUnitSpell base check only.
  t1   TAbilityOwner.GetAbilityEnabled 'not present' tail 0x5574FD98 (VMT+0x88; movement-type builder / immunity masks)
  t2   TAbstractUnit.GetAbilityEnabled 'not present' tail 0x5577F612 (VMT+0x148; every tactical HasAbility, the hover
       draw 0x421FFB, the can-strike rules) - both chained in front ('hdr' layout `jmp short +5 / jmp rel32 prev`):
       asked for FLYING (1) and the owner holds 0xC3 (own bitset: VMT+0x4C owner path, VMT+0x14C unit path) -> 1.
  mc   TAbstractUnit.CreateMovePointTable 0x5577FDC4 @0x5577FE13 (5 B `mov bl,[esi+0x24] / test bl,bl`; esi = unit,
       [esp] = the 13x16 per-terrain cost table, just copied from the template): unit holds 0xC3 -> fill the whole
       256-byte table with 0xFF (= impassable, the table's own 'cannot enter' value) and leave through the epilogue
       0x5577FFC5.  TCPCK rebuilds this table per unit at selection / path time (TCombatUnitSelectionControl.Update,
       CalculateMovePath, TCAI.EvalBattle) -> the unit cannot walk or fly anywhere, but keeps its move points, so
       shooting / casting (full-MP gates) and other actions are not blocked.  (The vanilla 'locked' state GetLocked
       0x55724BA4 = Webbed etc. was NOT used: it forbids ALL actions - "It cannot perform actions".)
Dry-run default; --apply / --revert / --dis; --dll <scratch copy>.  Backup <game>\backup\AoWEPACK.dll.bak_suspend.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_suspend"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5586C000, 0x5586C800
HDR = 0x40                                                # saved site bytes live in ZONE..ZONE+HDR
SPELL, AB, FLYING = 214, 0xC3, 1
NAME = b"Suspended"
CA_RET = 0x558166D3                                       # TUnitSpell CA.Execute -> ExecuteSpell return address (tactical; esi = caster CU)
BASECHECK, VT_EPI = 0x5577ACAC, 0x557E74DB
GETABILITYDATA = 0x5574F1C4
REGABIL, LSTRASG = 0x55750238, 0x55701150
DUR_VMT, DUR_CREATE = 0x5571DD68, 0x55764CD4
HPB_WORD20 = 0x557BB808
MC_BACK, MC_EPI = 0x5577FE18, 0x5577FFC5
MC_ORIG = bytes.fromhex("8a5e2484db")                     # mov bl,[esi+0x24] / test bl,bl
SITES = [  # name, va, size, kind ('call' = E8 splice, 'jmp' = chained E9 jmp, 'site' = vanilla bytes -> our jmp)
    ("reg", 0x557BCF6E, 5, "call"),
    ("ex",  0x557E736C, 6, "jmp"),
    ("vt",  0x557E7434, 6, "jmp"),
    ("t1",  0x5574FD98, 5, "jmp"),
    ("t2",  0x5577F612, 5, "jmp"),
    ("mc",  0x5577FE13, 5, "site"),
]
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def rel(op, va, target, size):
    return bytes([op]) + struct.pack("<i", target - (va + 5)) + b"\x90" * (size - 5)


def build(prev, w20):
    out = bytearray(HDR); where = {}

    def place(name, src, layout=None):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        b = asm(src, va)
        if layout == "cmp": assert b[0:3] == b"\x81\x78\x10" and b[7] == 0x74 and b[9] == 0xE9, name
        if layout == "hdr": assert b[0:2] == b"\xeb\x05" and b[2] == 0xE9, name
        if layout == "call": assert b[0] == 0xE8, name
        out.extend(b)

    out += struct.pack("<ii", -1, len(NAME)); where["name"] = ZONE + len(out); out += NAME + b"\0"

    place("ex", """
        cmp dword ptr [eax + 0x10], %(spell)d
        je mine
        jmp %(prev)#x
    mine:
        push ebp
        mov ebp, esp
        sub esp, 12
        push ebx
        push esi
        push edi
        mov [ebp - 4], edx
        mov [ebp - 8], esi
        mov edx, [ebp + 4]
        mov [ebp - 12], edx
        mov ebx, ecx
        mov esi, eax
        mov ecx, ebx
        mov edx, [ebp - 4]
        mov eax, esi
        mov edi, [eax]
        call dword ptr [edi + 0x9c]
        test al, al
        je fail
        call here
    here:
        pop eax
        sub eax, here
        add eax, %(caret)#x
        cmp eax, [ebp - 12]
        jne ok
        mov eax, [ebp - 8]
        test eax, eax
        je ok
        mov edx, [ebp - 4]
        cmp [eax + 0x4c], edx
        jne ok
        mov eax, [eax + 8]
        test eax, eax
        je ok
        mov eax, [eax + 0xc]
        test eax, eax
        je ok
        movzx edi, byte ptr [eax + 0x31]
        mov edx, %(ab)d
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x94]
        mov edx, %(ab)d
        mov eax, ebx
        call %(gad)#x
        test eax, eax
        je chg
        mov byte ptr [eax + 0xc], 3
        mov edx, edi
        mov byte ptr [eax + 0xd], dl
    chg:
        mov eax, ebx
        mov edx, [eax]
        call dword ptr [edx + 0x90]
    ok:
        mov al, 1
        jmp done
    fail:
        xor eax, eax
    done:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 8
    """ % {"spell": SPELL, "prev": prev["ex"], "caret": CA_RET, "ab": AB, "gad": GETABILITYDATA}, "cmp")

    place("vt", """
        cmp dword ptr [eax + 0x10], %(spell)d
        je mine
        jmp %(prev)#x
    mine:
        push ebx
        push esi
        mov esi, ecx
        mov ecx, esi
        call %(base)#x
        jmp %(epi)#x
    """ % {"spell": SPELL, "prev": prev["vt"], "base": BASECHECK, "epi": VT_EPI}, "cmp")

    for name, has in (("t1", 0x4C), ("t2", 0x14C)):
        place(name, """
            jmp body
            jmp %(prev)#x
        body:
            cmp esi, %(fly)d
            jne nxt
            mov eax, ebx
            mov edx, %(ab)d
            mov ecx, [eax]
            call dword ptr [ecx + %(has)#x]
            test al, al
            je nxt
            mov al, 1
            pop esi
            pop ebx
            ret
        nxt:
            jmp %(prev)#x
        """ % {"prev": prev[name], "fly": FLYING, "ab": AB, "has": has}, "hdr")

    place("mc", """
        mov eax, esi
        mov edx, %(ab)d
        mov ecx, [eax]
        call dword ptr [ecx + 0x14c]
        test al, al
        jne fill
        mov bl, byte ptr [esi + 0x24]
        test bl, bl
        jmp %(back)#x
    fill:
        mov edx, [esp]
        push edi
        mov edi, edx
        mov ecx, 0x40
        or eax, -1
        rep stosd
        pop edi
        jmp %(epi)#x
    """ % {"ab": AB, "back": MC_BACK, "epi": MC_EPI})

    place("reg", """
        call %(prev)#x
        push esi
        call rd
    rd:
        pop esi
        sub esi, rd
        lea eax, [esi + %(vmt)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(ab)d
        mov byte ptr [eax + 0x24], 4
        mov byte ptr [eax + 0x28], 2
        mov word ptr [eax + 0x20], %(w20)d
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % {"prev": prev["reg"], "vmt": DUR_VMT, "create": DUR_CREATE, "ab": AB, "w20": w20, "name": where["name"],
           "lstrasg": LSTRASG, "reg": REGABIL}, "call")
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


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
    g = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    zl = g(ZONE, ZONE_END - ZONE)
    inzone = lambda va: va is not None and ZONE <= va < ZONE_END
    tgt = lambda b, va: va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] in (0xE8, 0xE9) else None
    saved = {}; o = 0
    for name, va, n, _k in SITES: saved[name] = zl[o:o + n]; o += n
    cur = {name: g(va, n) for name, va, n, _k in SITES}
    applied = any(zl[HDR:])
    # 'prev' = what the site pointed at before us: from the saved header when we are applied, else from the live site
    src = saved if applied else cur
    prev = {name: tgt(src[name], va) for name, va, n, kind in SITES if kind != "site"}
    w20 = struct.unpack_from("<H", d, HPB_WORD20 - CODE_V2F)[0]
    if not applied:
        for name, va, n, kind in SITES:
            if kind == "site": assert cur[name] == MC_ORIG, "mc site %#x not vanilla: %s" % (va, cur[name].hex())
            elif kind == "call": assert cur[name][0] == 0xE8, "%s site %#x is not a call: %s" % (name, va, cur[name].hex())
            else: assert cur[name][0] == 0xE9, "%s site %#x is not a jmp (apply the chain below first): %s" % (name, va, cur[name].hex())
    zone, where = build(prev, w20)
    hdr = b"".join((saved if applied else cur)[name] for name, _va, _n, _k in SITES)
    zone = hdr + zone[len(hdr):]
    hooked = {name: (rel(0xE8 if kind == "call" else 0xE9, va, where[name], n)) for name, va, n, kind in SITES}
    st = {name: ("ours" if cur[name] == hooked[name] else "orig" if cur[name] == saved.get(name) or not applied else "OTHER")
          for name, _va, _n, _k in SITES}
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for _nm, va, n, _k in SITES)]
    print("sites %s | prev %s | zone %s (%d B) | relocs %s | caves %s"
          % (st, ", ".join("%s=%#x" % kv for kv in prev.items()), zstate, len(zone), bad or "none",
             ", ".join("%s=%#x" % kv for kv in where.items())))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[HDR:], ZONE + HDR): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "OTHER" in st.values() or zstate == "DIFFERS": print("ABORT"); return 1
    if a.revert:
        if not applied: print("already reverted"); return 0
        out = bytearray(d)
        for name, va, n, _k in SITES: out[va - CODE_V2F:va - CODE_V2F + n] = saved[name]
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (sites restored from the zone header)"); return 0
    if all(v == "ours" for v in st.values()) and zstate == "ours": print("already applied"); return 0
    if applied: print("ABORT: zone holds our code but the sites do not all point at it"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for name, va, n, _k in SITES: out[va - CODE_V2F:va - CODE_V2F + n] = hooked[name]
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
