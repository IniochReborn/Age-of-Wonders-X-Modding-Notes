#!/usr/bin/env python3
r"""
Tame Animal v2 (ability 0xC9 + new status 0xCA 'Tamed', 2026-10-18).  Supersedes patch_tame_animal_v1.py and
upgrades it IN PLACE (v1's originals are taken from v1's zone header, v1's zone is cleared).

User (on v1): "Tame Animal should set an ability called 'Tamed', not share Dominated.  It should have its own
ability gfx/sfx.  The AI should use it the same way it uses Seduce, Charm, Dominate etc.  For its displayed attack
in the preview, just put '-' to indicate it's dynamic."

Everything v1 did is kept (second TDominateAbility instance id 0xC9 'Tame Animal'; six Dominate VMT slots routed
through caves that act only for [ability+0xC] == 0xC9: ATK = 7 - target level, creature/exclusion/Fearless filter
on both CanTouch slots, target stash around the TTouchAbility roll/chance/value; AbilTypes[0xC9] = 4 touch).  New:

AoWEPACK.dll
  * 'Tamed' (0xCA): a second instance of Dominated's class (TDominatedAbility VMT 0x557206F0, class cell
    0x557206B0, Create 0x55770528 - the class every command-status uses) registered as id 0xCA, name "Tamed".
    The Tame Animal instance gets [+0x28] := 0xCA.  [+0x28] is the status the command ability grants: every reader
    is generic (TCommandAbility 0x5576FE71/0x5576FE8A/0x5576FEA4 create + register the enchantment from
    GetAbility([+0x28]), 0x5576FF13/0x5576FF24/0x5576FF5B test / remove it), so Tamed is applied, kept and removed
    exactly like Dominated.  Its description / unit overlay come from Ability.pfs record 212
    (patch_tame_ability_pfs_v2.py).
  * Combat status overlay: the TCombatUnit status draw (0x55781640..: Seduced 0x30, Dominated 0x96, Charmed 0x95,
    ... each `HasAbility(id) -> draw GetAbility(id)+0x1C`) knows only the vanilla ids.  Hook ICO @0x5578175B
    (`mov edx,0x95`, the head of the Charmed block) -> cave: the same block for 0xCA, then `mov edx,0x95` and back.
  * Preview ATK '-': Dominate VMT +0x104 GetCombatInfo (TTouchAbility 0x557680D0; record byte 1 = attack, byte 2 =
    damage 0xFF) -> cave w104: for 0xC9 call the original, then byte 1 := 0xFF.  The AoWx.exe combat ability panel
    (0x434273: `cmp byte [rec+1],0 / jle -> '-'`) then prints '-'; the AoWEPACK description builder (0x5574EBF5
    `cmp bl,0xFF / je skip`) omits its 'Attack:' line (the description itself lists 6/5/4/3).  Nothing else reads
    byte 1 (TCAI only tests byte 0's flags; the click path 0x41F58D reads byte 0).
AoWTCPCK.dll (tactical AI, TCAI)
  * SCN @0x418D1F (`cmp [ebp-0xC],0xAA / jne 0x418B3E`, 13 B): the phase-1 OFFENSIVE ability scan runs ids
    1..0xA9 only.  The cave lets it finish, then runs the loop body once more for 0xC9 (GetAbilityEnabled via the
    combat unit's VMT+0xA8 -> 0x418CAA: AbilTypes[0xC9] = 4 != 0 (bound 0..255 since BXL's relocation), combat
    info byte 0 & 2 -> added to the list), then leaves at 0x418D2C.  Ids 0xAA..0xC8 are NOT scanned (their
    AbilTypes bytes are stale SpellTypes data, e.g. 0xB4/0xBB..0xBD = 7).
  * RET @0x416F0B (`mov eax,[ebp-0x5C] / cmp eax,0x3C`, 6 B): the touch handler's "no retaliation" ladder (Web,
    Dominate, Seduce, Entangle, 0x3C, Possess 0x6A/0x6B, Charm 0x94 -> 0x416F31) gets 0xC9 too.
  Everything else in the touch handler (0x416DF4) is generic: CanTouch +0x11C (our creature filter), DV +0xEC ->
  +0xE4 TCommandAbility 0x55770274 = cur HP x 200 x chance(+0x114, our ATK via the stash), AddMove type 1, phase 5
  executes it through the normal touch flow (AbilTypes = 4).  Same evaluation as Dominate/Charm/Seduce.

PIC: AoWEPACK caves reach globals / class cells / literals via call-pop deltas; all calls/jumps rel32.  TCPCK
caves only touch the frame and rel32 targets (TCPCK is rebased at load).  MP: deterministic.
Zones: AoWEPACK 0x55818100..0x55819000 (verified zero + reloc-free at apply; 0x55818000 kept free - an old
'statdouble marker' note names it), TCPCK 0x450D00..0x450E00 (0x450C00..0x450C40 = shockwave push v2).
Header @0x55818100: 'TAM2', +4 reg original (5), +0x0C AbilTypes original, +0x10 seven slot originals
(+0x104,+0x10C..+0x120), +0x2C ICO original (5), +0x34 SCN original (13), +0x44 RET original (6), +0x50/+0x60
name literals.
States: vanilla -> apply; v1 applied -> upgrade in place (v1 zone cleared); v2 -> already applied.
--revert: back to VANILLA (pre-Tame) - re-run patch_tame_animal_v1.py --apply afterwards if v1 is wanted.
LIFO: the reg chain head @0x557BCF6E is ours (as with v1) -> revert this BEFORE patch_reversal_v1.py.
Dry-run default; --apply / --revert / --dis; --dll / --tcdll <scratch copies>.  Backups (first apply):
<game>\backup\AoWEPACK.dll.bak_tame2, AoWTCPCK.dll.bak_tame2.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
DEFAULT_TC = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_tame2"
BASE, CODE_V2F = 0x55700000, 0x55700C00
TCBASE = 0x400000
ZONE, ZONE_END = 0x55818100, 0x55819000
V1_ZONE, V1_ZONE_END = 0x5588B000, 0x5588B400
TZONE, TZONE_END = 0x450D00, 0x450E00
HDR = 0x80
MAGIC, V1_MAGIC = b"TAM2", b"TAM1"
AB, ST = 0xC9, 0xCA
NAME, ST_NAME = b"Tame Animal", b"Tamed"
STASH = 0x5590BF80
DOM_VMT, DOM_CELL, DOM_CREATE = 0x55720878, 0x55720838, 0x557705BC
DOMD_CELL, DOMD_CREATE = 0x557206B0, 0x55770528                   # TDominatedAbility (status class)
CU_CELL, UNIT_CELL = 0x55715A54, 0x55710C6C
ISCLASS, RESIDX = 0x557010C0, 0x5574D3C8
REGABIL, LSTRASG = 0x55750238, 0x55701150
GETABIL, DRAWSEQ = 0x557501C0, 0x55702914
G40, G44 = 0x558FA040, 0x558FA044
REG_SITE = 0x557BCF6E
ICO_SITE, ICO_BYTES, ICO_BACK = 0x5578175B, bytes.fromhex("ba95000000"), 0x55781760
SLOTS = (0x104, 0x10C, 0x110, 0x114, 0x118, 0x11C, 0x120)
V1_SLOTS = (0x10C, 0x110, 0x114, 0x118, 0x11C, 0x120)
VANILLA_SLOTS = {0x104: 0x557680D0, 0x10C: 0x55770664, 0x110: 0x557681B0, 0x114: 0x55768234, 0x118: 0x55768130,
                 0x11C: 0x55770008, 0x120: 0x55770068}
FEARLESS, CREATURE = 0x43, 1
EXCLUDE = {130: "Spirit Puppet", 241: "Greater Spirit Puppet", 25: "Djinn", 24: "Beholder", 41: "Yeti",
           76: "Fairy", 96: "Satyr", 98: "Centaur", 148: "Lady of Pain", 77: "Nymph", 150: "Spider Queen",
           151: "Shadow"}
TC_BYTE_VA = 0x467248 + AB
TOUCH = 4
SCN_SITE, SCN_BYTES = 0x418D1F, bytes.fromhex("817df4aa0000000f8512feffff")
RET_SITE, RET_BYTES = 0x416F0B, bytes.fromhex("8b45a483f83c")
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def lit(s):
    return struct.pack("<ii", -1, len(s)) + s + b"\0"


def build(prev_reg, orig):
    out = bytearray(HDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    L = lambda n: where[n]
    for off, s, key in ((0x50, NAME, "name"), (0x64, ST_NAME, "stname")):
        b = lit(s); out[off:off + len(b)] = b; where[key] = ZONE + off + 8
    assert 0x64 + len(lit(ST_NAME)) <= HDR

    excl = "\n".join("        cmp eax, %d\n        je fno" % k for k in sorted(EXCLUDE))
    place("getunit", """
        push ebx
        push esi
        mov ebx, eax
        test ebx, ebx
        je gzero
        call gd
    gd:
        pop esi
        sub esi, gd
        mov eax, ebx
        mov edx, dword ptr [esi + %(cucell)#x]
        call %(isclass)#x
        test al, al
        je gnotcu
        mov ebx, dword ptr [ebx + 0x4c]
        test ebx, ebx
        je gzero
    gnotcu:
        mov eax, ebx
        mov edx, dword ptr [esi + %(unitcell)#x]
        call %(isclass)#x
        test al, al
        je gzero
        mov eax, ebx
        jmp gout
    gzero:
        xor eax, eax
    gout:
        pop esi
        pop ebx
        ret
    """ % {"cucell": CU_CELL, "unitcell": UNIT_CELL, "isclass": ISCLASS})

    place("filt", """
        push ebx
        call %(getunit)#x
        test eax, eax
        je fno
        mov ebx, eax
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x114]
        cmp al, %(creature)d
        jne fno
        mov eax, dword ptr [ebx + 0x40]
        test eax, eax
        je fno
        call %(residx)#x
%(excl)s
        mov eax, ebx
        mov edx, %(fearless)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne fno
        mov al, 1
        jmp fout
    fno:
        xor eax, eax
    fout:
        pop ebx
        ret
    """ % {"getunit": L("getunit"), "creature": CREATURE, "residx": RESIDX, "excl": excl, "fearless": FEARLESS})

    place("w104", """
        cmp dword ptr [eax + 0xc], %(ab)d
        je m
        jmp %(orig)#x
    m:
        push ecx
        call %(orig)#x
        pop ecx
        mov byte ptr [ecx + 1], 0xff
        ret
    """ % {"ab": AB, "orig": orig[0x104]})

    place("w10c", """
        cmp dword ptr [eax + 0xc], %(ab)d
        je m
        jmp %(orig)#x
    m:
        push ecx
        push edx
        push esi
        call hd
    hd:
        pop esi
        sub esi, hd
        mov eax, dword ptr [esi + %(stash)#x]
        call %(getunit)#x
        test eax, eax
        je dflt
        mov eax, dword ptr [eax + 0x40]
        test eax, eax
        je dflt
        movzx eax, byte ptr [eax + 0x2f]
        cmp eax, 1
        jbe dflt
        cmp eax, 4
        jb mid
        mov eax, 3
        jmp wout
    mid:
        neg eax
        add eax, 7
        jmp wout
    dflt:
        mov eax, 6
    wout:
        pop esi
        pop edx
        pop ecx
        ret
    """ % {"ab": AB, "orig": orig[0x10C], "stash": STASH, "getunit": L("getunit")})

    for s in (0x110, 0x114, 0x118):
        place("w%x" % s, """
        cmp dword ptr [eax + 0xc], %(ab)d
        je m
        jmp %(orig)#x
    m:
        push ebx
        call hd
    hd:
        pop ebx
        sub ebx, hd
        push dword ptr [ebx + %(stash)#x]
        mov dword ptr [ebx + %(stash)#x], ecx
        call %(orig)#x
        pop dword ptr [ebx + %(stash)#x]
        pop ebx
        ret
        """ % {"ab": AB, "orig": orig[s], "stash": STASH})

    for s in (0x11C, 0x120):
        place("w%x" % s, """
        cmp dword ptr [eax + 0xc], %(ab)d
        je m
        jmp %(orig)#x
    m:
        push ecx
        call %(orig)#x
        pop ecx
        test al, al
        je wout
        mov eax, ecx
        call %(filt)#x
    wout:
        ret
        """ % {"ab": AB, "orig": orig[s], "filt": L("filt")})

    # the Tamed status overlay block (a copy of the Dominated block 0x5578170F..0x5578175A with id 0xCA)
    place("ico", """
        mov edx, %(st)d
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je idone
        push ebx
        call idl
    idl:
        pop ebx
        sub ebx, idl
        mov eax, dword ptr [ebp - 8]
        add eax, 0x28
        push eax
        mov eax, dword ptr [ebx + %(g40)#x]
        mov eax, dword ptr [eax + 0x40]
        push eax
        mov eax, dword ptr [ebp + 0xc]
        push eax
        mov eax, dword ptr [ebx + %(g44)#x]
        mov eax, dword ptr [eax + 0x80]
        mov edx, %(st)d
        call %(getabil)#x
        mov eax, dword ptr [eax + 0x1c]
        mov ecx, dword ptr [ebp - 4]
        add ecx, 0x20
        xor edx, edx
        call %(drawseq)#x
        pop ebx
    idone:
        mov edx, 0x95
        jmp %(back)#x
    """ % {"st": ST, "g40": G40, "g44": G44, "getabil": GETABIL, "drawseq": DRAWSEQ, "back": ICO_BACK})

    place("reg", """
        call %(prev)#x
        push esi
        call rd
    rd:
        pop esi
        sub esi, rd
        mov eax, dword ptr [esi + %(cell)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(ab)d
        mov dword ptr [eax + 0x28], %(st)d
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        mov eax, dword ptr [esi + %(dcell)#x]
        xor ecx, ecx
        mov dl, 1
        call %(dcreate)#x
        mov dword ptr [eax + 0xc], %(st)d
        push eax
        lea edx, [esi + %(stname)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % {"prev": prev_reg, "cell": DOM_CELL, "create": DOM_CREATE, "ab": AB, "st": ST, "name": L("name"),
           "lstrasg": LSTRASG, "reg": REGABIL, "dcell": DOMD_CELL, "dcreate": DOMD_CREATE, "stname": L("stname")})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return out, where


def build_tc():
    out = bytearray(); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = TZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    place("scn", """
        mov eax, dword ptr [ebp - 0xc]
        cmp eax, 0xaa
        jb 0x418b3e
        cmp eax, %(ab1)d
        jae 0x418d2c
        mov dword ptr [ebp - 0xc], %(ab)d
        mov edx, %(ab)d
        mov eax, dword ptr [ebp - 0x28]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        je 0x418d1c
        jmp 0x418caa
    """ % {"ab": AB, "ab1": AB + 1})
    place("ret", """
        mov eax, dword ptr [ebp - 0x5c]
        cmp eax, %(ab)d
        je 0x416f31
        cmp eax, 0x3c
        jg 0x416f24
        je 0x416f31
        jmp 0x416f15
    """ % {"ab": AB})
    assert TZONE + len(out) <= TZONE_END
    return bytes(out), where


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    return [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)], pe


def va2off(d, va, base):
    secs, _ = sections(d)
    for vs, sva, rs, ro in secs:
        if sva <= va - base < sva + max(vs, rs): return ro + va - base - sva
    raise ValueError(hex(va))


def reloc_set(d, base):
    secs, pe = sections(d)
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
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def jmp5(src, dst, total):
    b = b"\xE9" + struct.pack("<i", dst - (src + 5))
    return b + b"\x90" * (total - 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--tcdll", default=DEFAULT_TC)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read(); t = open(a.tcdll, "rb").read()
    g = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    tg = lambda va, n: bytes(t[va2off(t, va, TCBASE):va2off(t, va, TCBASE) + n])
    tco = va2off(t, TC_BYTE_VA, TCBASE)
    zl, v1z = g(ZONE, ZONE_END - ZONE), g(V1_ZONE, V1_ZONE_END - V1_ZONE)
    tzl = tg(TZONE, TZONE_END - TZONE)
    slot_va = {s: DOM_VMT + s for s in SLOTS}
    cur_reg = g(REG_SITE, 5); cur_ico = g(ICO_SITE, 5)
    cur_slot = {s: struct.unpack("<I", g(slot_va[s], 4))[0] for s in SLOTS}
    cur_tc = t[tco]; cur_scn = tg(SCN_SITE, 13); cur_ret = tg(RET_SITE, 6)
    v1 = v1z[:4] == V1_MAGIC; v2 = zl[:4] == MAGIC
    if v2:
        sav_reg = zl[4:9]; sav_tc = zl[0xC]
        sav_slot = {s: struct.unpack_from("<I", zl, 0x10 + 4 * k)[0] for k, s in enumerate(SLOTS)}
        sav_ico = zl[0x2C:0x31]; sav_scn = zl[0x34:0x41]; sav_ret = zl[0x44:0x4A]
        base_state = "v2"
    elif v1:
        sav_reg = v1z[4:9]; sav_tc = v1z[0xC]
        sav_slot = {s: struct.unpack_from("<I", v1z, 0x10 + 4 * k)[0] for k, s in enumerate(V1_SLOTS)}
        sav_slot[0x104] = cur_slot[0x104]
        sav_ico, sav_scn, sav_ret = cur_ico, cur_scn, cur_ret
        base_state = "v1"
    else:
        sav_reg, sav_tc, sav_slot = cur_reg, cur_tc, dict(cur_slot)
        sav_ico, sav_scn, sav_ret = cur_ico, cur_scn, cur_ret
        base_state = "vanilla"
        assert cur_tc == 0, "AbilTypes[0xC9] = %d (expected 0)" % cur_tc
    assert sav_reg[0] == 0xE8, "reg original is not a call (%s)" % sav_reg.hex()
    for s in SLOTS:
        assert 0x55701000 <= sav_slot[s] < 0x558E8000 and not (ZONE <= sav_slot[s] < ZONE_END) and not (V1_ZONE <= sav_slot[s] < V1_ZONE_END), (hex(s), hex(sav_slot[s]))
    assert sav_ico == ICO_BYTES, "ICO site %#x original %s (expected %s) - another patch?" % (ICO_SITE, sav_ico.hex(), ICO_BYTES.hex())
    assert sav_scn == SCN_BYTES, "SCN site original %s - another patch?" % sav_scn.hex()
    assert sav_ret == RET_BYTES, "RET site original %s - another patch?" % sav_ret.hex()
    prev_reg = REG_SITE + 5 + struct.unpack_from("<i", sav_reg, 1)[0]
    zone, where = build(prev_reg, sav_slot)
    zone[0:4] = MAGIC; zone[4:9] = sav_reg; zone[0xC] = sav_tc
    for k, s in enumerate(SLOTS): struct.pack_into("<I", zone, 0x10 + 4 * k, sav_slot[s])
    zone[0x2C:0x31] = sav_ico; zone[0x34:0x41] = sav_scn; zone[0x44:0x4A] = sav_ret
    zone = bytes(zone)
    tzone, twhere = build_tc()
    hooked_reg = b"\xE8" + struct.pack("<i", where["reg"] - (REG_SITE + 5))
    hooked_slot = {s: where["w%x" % s] for s in SLOTS}
    hooked_ico = jmp5(ICO_SITE, where["ico"], 5)
    hooked_scn = jmp5(SCN_SITE, twhere["scn"], 13)
    hooked_ret = jmp5(RET_SITE, twhere["ret"], 6)
    st = {"reg": "ours" if cur_reg == hooked_reg else ("orig" if cur_reg == sav_reg else ("v1" if v1 else "OTHER")),
          "ico": "ours" if cur_ico == hooked_ico else ("orig" if cur_ico == sav_ico else "OTHER"),
          "scn": "ours" if cur_scn == hooked_scn else ("orig" if cur_scn == sav_scn else "OTHER"),
          "ret": "ours" if cur_ret == hooked_ret else ("orig" if cur_ret == sav_ret else "OTHER"),
          "tc": "ours" if cur_tc == TOUCH else ("orig" if cur_tc == sav_tc else "OTHER")}
    for s in SLOTS:
        if cur_slot[s] == hooked_slot[s]: st["s%x" % s] = "ours"
        elif cur_slot[s] == sav_slot[s]: st["s%x" % s] = "orig"
        elif v1 and V1_ZONE <= cur_slot[s] < V1_ZONE_END: st["s%x" % s] = "v1"
        else: st["s%x" % s] = "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    tzstate = "zero" if not any(tzl) else "ours" if tzl[:len(tzone)] == tzone and not any(tzl[len(tzone):]) else "DIFFERS"
    rl = reloc_set(d, BASE); rlt = reloc_set(t, TCBASE)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or REG_SITE - 3 <= r < REG_SITE + 5 or ICO_SITE - 3 <= r < ICO_SITE + 5]
    bad += ["tc:" + hex(r) for r in rlt if TC_BYTE_VA - 3 <= r <= TC_BYTE_VA or TZONE - 3 <= r < TZONE_END
            or SCN_SITE - 3 <= r < SCN_SITE + 13 or RET_SITE - 3 <= r < RET_SITE + 6]
    slot_rel = all(slot_va[s] in rl for s in SLOTS)
    print("base %s | states %s | zone %s (%d B) tzone %s (%d B) | prev reg %#x | relocs in zones/sites %s | slot relocs %s"
          % (base_state, st, zstate, len(zone), tzstate, len(tzone), prev_reg, bad or "none", "ok" if slot_rel else "MISSING"))
    print("caves " + ", ".join("%s=%#x" % kv for kv in list(where.items()) + list(twhere.items())))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[HDR:], ZONE + HDR): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        for i in md.disasm(tzone, TZONE): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or not slot_rel or "OTHER" in st.values() or zstate == "DIFFERS" or tzstate == "DIFFERS":
        print("ABORT"); return 1
    out = bytearray(d); tout = bytearray(t)
    put = lambda va, b: out.__setitem__(slice(va - CODE_V2F, va - CODE_V2F + len(b)), b)
    tput = lambda va, b: tout.__setitem__(slice(va2off(t, va, TCBASE), va2off(t, va, TCBASE) + len(b)), b)
    if a.revert:
        if base_state == "vanilla": print("already reverted (no Tame patch present)"); return 0
        put(REG_SITE, sav_reg); put(ICO_SITE, sav_ico)
        for s in SLOTS: struct.pack_into("<I", out, slot_va[s] - CODE_V2F, sav_slot[s])
        put(ZONE, bytes(ZONE_END - ZONE)); put(V1_ZONE, bytes(V1_ZONE_END - V1_ZONE))
        tout[tco] = sav_tc; tput(SCN_SITE, sav_scn); tput(RET_SITE, sav_ret); tput(TZONE, bytes(TZONE_END - TZONE))
        write_inplace(a.tcdll, bytes(tout)); write_inplace(a.dll, bytes(out))
        print("reverted to VANILLA (reg site, 7 Dominate VMT slots, ICO, AbilTypes[0xC9], SCN, RET; zones cleared)"); return 0
    if base_state == "v2" and all(v == "ours" for v in st.values()) and zstate == "ours" and tzstate == "ours":
        print("already applied"); return 0
    if base_state == "v2": print("ABORT: v2 zone present but the sites do not all point at it"); return 1
    if base_state == "v1":
        bad1 = [k for k, v in st.items() if v not in ("v1", "orig", "ours") or (k == "tc" and v != "ours")]
        if bad1: print("ABORT: v1 marker present but site states unexpected: %s" % bad1); return 1
        put(V1_ZONE, bytes(V1_ZONE_END - V1_ZONE))
        print("upgrading v1 -> v2 in place (v1 zone cleared)")
    put(ZONE, zone); put(REG_SITE, hooked_reg); put(ICO_SITE, hooked_ico)
    for s in SLOTS: struct.pack_into("<I", out, slot_va[s] - CODE_V2F, hooked_slot[s])
    tout[tco] = TOUCH; tput(TZONE, tzone); tput(SCN_SITE, hooked_scn); tput(RET_SITE, hooked_ret)
    print("%d AoWEPACK bytes + %d AoWTCPCK bytes change" % (sum(1 for x, y in zip(d, out) if x != y), sum(1 for x, y in zip(t, tout) if x != y)))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for path in (a.dll, a.tcdll):
        if os.path.abspath(path) in (os.path.abspath(DEFAULT_DLL), os.path.abspath(DEFAULT_TC)):
            bak = bak_path(path, BAK_SUFFIX)
            if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
    write_inplace(a.tcdll, bytes(tout)); write_inplace(a.dll, bytes(out))
    assert open(a.dll, "rb").read() == bytes(out) and open(a.tcdll, "rb").read() == bytes(tout)
    print("Written and verified.  Next: patch_tame_ability_pfs_v2.py --apply, then the two ceiling scripts (LADDER += 0xCA).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
