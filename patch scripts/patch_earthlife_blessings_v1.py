"""
EARTH/LIFE BLESSINGS (2026-10-14) - AoWEPACK.dll only.  Sphere pair 9 (Life/Earth), THighPrayer clones (class 37):
  300 Awaken Spirit         -> every friendly CREATURE (non-hero, level <= 2) gains 0xB6 'Awakened'  (+1 ATK/DMG/DEF/RES)
  301 Blessing of the Forest-> every friendly unit gains 0xB7 'Barkskin' (+1 DEF/RES, Fire Weakness + Lightning Weakness)
Both abilities are COMBAT ONLY: plain TDurationAbility instances (the Oil Spring 0xB2 recipe: VMT 0x5571DD68, Create
0x55764CD4, [+0x24]=4, [+0x28]=3 = combat-only mode -> GetName appends "(combat only)", CombatDone removes them).

RE used:
  * Unit stat cache (TUnit.Changed tail 0x55782B34): [unit+0x44] ATK / +0x45 DEF / +0x46 RES / +0x47 DMG = the sums
    0x5574F624 / F674 / F6C4 / F714 over every enabled ability id (owner VMT+0x54 count, VMT+0x88 enabled, registry
    GetAbility 0x557501C0) of ability VMT+0x5C / +0x60 / +0x64 / +0x68 (eax = the registry's shared ability object,
    edx = the unit; return signed AL).  TDurationAbility's four slots are the base `xor eax,eax / ret`, so per-id caves
    there (testing [this+0xC]) give 0xB6 / 0xB7 their bonuses and keep 0 for every other plain TDurationAbility
    (subclasses like Burning have their own VMTs - untouched).
  * Creature test: TUnit VMT+0xA0 = GetLevel 0x55782B8C (byte [[unit+0x40]+0x2F] = Unitres tag 0x14 level); THero /
    TLeader override slot 0xA0, so "creature" = [vmt+0xA0] == 0x55782B8C (compared PIC) and level = call [vmt+0xA0].
  * Weakness (weakness-abilities memory): ids in WEAK_IDS BSS 0x558FA810 (index = damage-bit position: [0] Fire 0x51,
    [2] Lightning).  Damage path: cave_weakmask 0x5580FA00 -> TCombatUnit.GetAbilityEnabled 0x55725004 (Oil Spring
    hook) -> strategic VMT+0x148 (TUnit 0x5577F5E0 / THero override calls it); status-chance path: cave 0x5580FC00 ->
    strategic VMT+0x88 = TAbilityOwner.GetAbilityEnabled 0x5574FD68.  Both get a prologue hook: asked for WEAK_IDS[0]
    or WEAK_IDS[2] (fast pre-filter: ids 0x51..0x55 / 0x85..0x89 = the first candidates of the weakness registration
    table) -> answer TRUE when the owner holds 0xB7 (its own bitset test: VMT+0x4C / unit VMT+0x14C), else continue vanilla.
  * Cast: TTacticalCombatHighPrayerCA (VMT 0x557F44D0) Execute slot VMT+0x50 @0x557F4520 (sole reference, reloc'd) is
    redirected to the `exe` cave: spells 300/301 are handled here (parent 0x557F6C84, result flag [ca+0x14], unit =
    0x55728C68(level [ctx+0xC], [ca+0xD]), TUnit [cu+0x4C], grant via VMT+0x148 / VMT+0x94 ExpandAbility = Frenzied's
    path; NO High Prayer heal, NO 0x64 blessing); every other spell jumps to the original 0x557F7E98 (Frenzied's jmp
    and Blood Pact's caves stay on that path untouched).
Hooks
  reg   call-hook on the vanilla `call RegisterAbility` 0x557BCD6A (ebx = control): replay, create + register 0xB6, 0xB7.
  sa/sd/sr/sg  TDurationAbility VMT slots +0x5C/+0x60/+0x64/+0x68 -> per-id stat caves.
  exe   CA VMT slot 0x557F4520 -> exe cave.
  w1    0x5574FD68 (6 B prologue) jmp-hook; w2 0x5577F5E0 (6 B prologue) jmp-hook.
Zone 0x55854000..0x55856000 (PIC via call/pop delta; the DLL rebases).  Dry-run default; --apply (upgrades an older
build of itself in place) / --revert / --dis.  Backup <game>\\backup\\AoWEPACK.dll.bak_earthlife.
NOT covered: fast combat (TFastCombatHighPrayerCA.Generate hard-codes High Prayer) - same as Frenzied / Blood Pact.
Also needed: pipeline 300/301, ALIAS[300]=ALIAS[301]=0x66 (class-37 caster store), Ability.pfs 192/193
(patch_earthlife_ability_pfs_v1.py), ceilings LADDER += 0xB6, 0xB7 (bounds -> 0xB8).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_earthlife"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55854000, 0x55856000
SP_AWAKEN, SP_FOREST = 300, 301
AB_AWAKENED, AB_BARKSKIN = 0xB6, 0xB7
REGABIL, LSTRASG = 0x55750238, 0x55701150
DUR_VMT, DUR_CREATE = 0x5571DD68, 0x55764CD4
HPB_WORD20 = 0x557BB808                       # the word THighPrayerBlessingAbility's ctor stores at [abil+0x20] (Oil Spring recipe)
CA_PARENT_EXEC, RESOLVE_UNIT = 0x557F6C84, 0x55728C68
HP_EXEC = 0x557F7E98                          # TTacticalCombatHighPrayerCA.Execute (Frenzied's jmp lives there)
TUNIT_GETLEVEL = 0x55782B8C
WEAK_IDS = 0x558FA810
SITES = {   # name: (va, original bytes, kind, resume)
    "reg": (0x557BCD6A, bytes.fromhex("e8c934f9ff"), "call", None),
    "w1":  (0x5574FD68, bytes.fromhex("53568bf28bd8"), "jmp", 0x5574FD6E),
    "w2":  (0x5577F5E0, bytes.fromhex("53568bf28bd8"), "jmp", 0x5577F5E6),
}
SLOTS = {   # name: (slot va, original pointer)
    "sa": (DUR_VMT + 0x5C, 0x5574E990),
    "sd": (DUR_VMT + 0x60, 0x5574E994),
    "sr": (DUR_VMT + 0x64, 0x5574E998),
    "sg": (DUR_VMT + 0x68, 0x5574E99C),
    "exe": (0x557F4520, HP_EXEC),
}
NAMES = {AB_AWAKENED: b"Awakened", AB_BARKSKIN: b"Barkskin"}

ks = Ks(KS_ARCH_X86, KS_MODE_32)
REGS = {"eax": (0x58, b"\x2d"), "ecx": (0x59, b"\x81\xe9"), "ebx": (0x5B, b"\x81\xeb"), "esi": (0x5E, b"\x81\xee"), "edi": (0x5F, b"\x81\xef")}


def asm_delta(src, va):
    """`call $D / pop R / sub R, $D` (R in REGS) -> R = load delta; every anchor patched."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in REGS: s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0]); n = 0
    for r, (pop, sub) in REGS.items():
        anchor = bytes([0xE8, 0, 0, 0, 0, pop]) + sub + b"\xff\xff\xff\x7f"
        k = b.find(anchor)
        while k >= 0:
            struct.pack_into("<I", b, k + len(anchor) - 4, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D"), "delta anchors: %d of %d" % (n, src.count("call $D"))
    return bytes(b)


def build(d):
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    for aid, nm in NAMES.items():                                  # Delphi AnsiString literals (refcount -1)
        while len(out) % 4: out.append(0)
        out += struct.pack("<ii", -1, len(nm)); where["name%x" % aid] = ZONE + len(out); out += nm + b"\0"
    w20 = struct.unpack_from("<H", d, HPB_WORD20 - CODE_V2F)[0]
    newab = ""
    for aid in (AB_AWAKENED, AB_BARKSKIN):
        newab += """
        lea eax, [esi + %(vmt)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(aid)d
        mov byte ptr [eax + 0x24], 4
        mov byte ptr [eax + 0x28], 3
        mov word ptr [eax + 0x20], %(w20)d
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        """ % {"vmt": DUR_VMT, "create": DUR_CREATE, "aid": aid, "w20": w20, "name": where["name%x" % aid], "lstrasg": LSTRASG, "reg": REGABIL}
    place("reg", """
        call %(reg)#x
        push esi
        call $D
        pop esi
        sub esi, $D
        %(newab)s
        pop esi
        ret
    """ % {"reg": REGABIL, "newab": newab})
    # stat caves (eax = ability, edx = unit): signed AL
    for name, ids in (("sa", (AB_AWAKENED,)), ("sd", (AB_AWAKENED, AB_BARKSKIN)), ("sr", (AB_AWAKENED, AB_BARKSKIN)), ("sg", (AB_AWAKENED,))):
        tests = "".join("        cmp dword ptr [eax + 0xc], %d\n        je s_one\n" % i for i in ids)
        place(name, tests + """
        xor eax, eax
        ret
    s_one:
        mov eax, 1
        ret
        """)
    # exe: TTacticalCombatHighPrayerCA.Execute replacement for 300 / 301 (eax = CA, edx = ctx)
    place("exe", """
        cmp dword ptr [eax + 0x18], %(sa)d
        je ours
        cmp dword ptr [eax + 0x18], %(sf)d
        je ours
        jmp %(hp)#x
    ours:
        push ebx
        push esi
        push edi
        mov esi, edx
        mov ebx, eax
        mov edx, esi
        mov eax, ebx
        call %(parent)#x
        cmp byte ptr [ebx + 0x14], 0
        je done
        xor edx, edx
        mov dl, byte ptr [ebx + 0xd]
        mov eax, [esi + 0xc]
        call %(resolve)#x
        test eax, eax
        jz done
        mov edi, [eax + 0x4c]
        test edi, edi
        jz done
        cmp dword ptr [ebx + 0x18], %(sf)d
        jne awaken
        mov ecx, %(bark)d
        call grant
        jmp done
    awaken:
        call $D
        pop ecx
        sub ecx, $D
        mov eax, [edi]
        mov eax, [eax + 0xa0]
        lea edx, [ecx + %(getlevel)#x]
        cmp eax, edx
        jne done
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0xa0]
        cmp al, 2
        jg done
        mov ecx, %(awake)d
        call grant
    done:
        pop edi
        pop esi
        pop ebx
        ret
    grant:
        push ecx
        mov edx, ecx
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        pop edx
        test al, al
        jnz g_done
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x94]
    g_done:
        ret
    """ % {"sa": SP_AWAKEN, "sf": SP_FOREST, "hp": HP_EXEC, "parent": CA_PARENT_EXEC, "resolve": RESOLVE_UNIT,
           "bark": AB_BARKSKIN, "awake": AB_AWAKENED, "getlevel": TUNIT_GETLEVEL})
    # w1 / w2: GetAbilityEnabled prologues (eax = owner, edx = id); Barkskin => Fire + Lightning Weakness
    for name, has in (("w1", 0x4C), ("w2", 0x14C)):     # own-bitset test: TAbilityOwner VMT+0x4C / TAbstractUnit VMT+0x14C (the slot each vanilla body calls first)
        place(name, """
        lea ecx, [edx - 0x51]
        cmp ecx, 4
        jbe slow
        lea ecx, [edx - 0x85]
        cmp ecx, 4
        jbe slow
        push ebx
        push esi
        mov esi, edx
        mov ebx, eax
        jmp %(resume)#x
    slow:
        push ebx
        push esi
        mov esi, edx
        mov ebx, eax
        call $D
        pop ecx
        sub ecx, $D
        cmp esi, [ecx + %(w0)#x]
        je chk
        cmp esi, [ecx + %(w2)#x]
        jne van
    chk:
        mov eax, ebx
        mov edx, %(bark)d
        mov ecx, [eax]
        call dword ptr [ecx + %(has)#x]
        test al, al
        jz van
        mov al, 1
        pop esi
        pop ebx
        ret
    van:
        jmp %(resume)#x
        """ % {"resume": SITES[name][3], "w0": WEAK_IDS, "w2": WEAK_IDS + 8, "bark": AB_BARKSKIN, "has": has})
    zone = bytes(out)
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, where


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def hook_bytes(kind, site, target, n):
    return (b"\xe8" if kind == "call" else b"\xe9") + struct.pack("<i", target - (site + 5)) + b"\x90" * (n - 5)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, where = build(bytes(d))
    rl = reloc_set(bytes(d))
    def st_site(name):
        va, orig, kind, _r = SITES[name]; live = bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)])
        want = hook_bytes(kind, va, where[name], len(orig))
        if live == orig: return "vanilla", want
        if live == want: return "ours", want
        if live[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END: return "ours(old)", want
        return "OTHER", want
    def st_slot(name):
        va, orig = SLOTS[name]; live = struct.unpack_from("<I", d, va - CODE_V2F)[0]
        if live == orig: return "vanilla"
        if live == where[name]: return "ours"
        if ZONE <= live < ZONE_END: return "ours(old)"
        return "OTHER(%#x)" % live
    sites = {n: st_site(n) for n in SITES}; slots = {n: st_slot(n) for n in SLOTS}
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(o) for va, o, _k, _r in SITES.values())]
    noreloc = [n for n, (va, _o) in SLOTS.items() if va not in rl]
    print("sites %s | slots %s | zone %s (%d B: %s) | relocs in zone/sites %s | slots without reloc %s" % (
        {n: s for n, (s, _w) in sites.items()}, slots, zstate, len(zone), ", ".join("%s=%#x" % (k, v) for k, v in where.items() if not k.startswith("name")),
        bad or "none", noreloc or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        cav = sorted((v, k) for k, v in where.items() if not k.startswith("name")) + [(ZONE + len(zone), None)]
        for (va, nm), (nx, _n) in zip(cav, cav[1:]):
            print("  [%s]" % nm)
            for i in md.disasm(zone[va - ZONE:nx - ZONE], va):
                if i.mnemonic == "add" and i.op_str == "byte ptr [eax], al": break
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or noreloc or any(s == "OTHER" for s, _w in sites.values()) or any(s.startswith("OTHER") for s in slots.values()):
        print("ABORT"); return 1
    ours_any = any(s.startswith("ours") for s, _w in sites.values()) or any(s.startswith("ours") for s in slots.values())
    if a.revert:
        for n, (va, orig, _k, _r) in SITES.items(): d[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        for n, (va, orig) in SLOTS.items(): struct.pack_into("<I", d, va - CODE_V2F, orig)
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.write(bytes(d))
        print("reverted (all sites / slots vanilla, zone zeroed)"); return 0
    if all(s == "ours" for s, _w in sites.values()) and all(s == "ours" for s in slots.values()) and zstate == "ours":
        print("already applied"); return 0
    if zstate == "DIFFERS" and not ours_any: print("ABORT: zone not free"); return 1
    if zstate == "DIFFERS": print("older build of this patch detected -> rewriting zone + every site/slot in place")
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for n, (s, want) in sites.items():
        va = SITES[n][0]; d[va - CODE_V2F:va - CODE_V2F + len(want)] = want
    for n in SLOTS: struct.pack_into("<I", d, SLOTS[n][0] - CODE_V2F, where[n])
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(bytes(d))
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
