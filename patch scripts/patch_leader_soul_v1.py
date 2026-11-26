#!/usr/bin/env python3
r"""
Leader's Soul v1 (2026-10-22): a possessing LEADER passes its leader status to the body it possesses.  AoWEPACK.dll only.

Vanilla: TPossessCA.Execute 0x557696E0 kills the leader (TLeader.Killed runs during combat, so GameOver is skipped) and
re-uses its combat object for the possessed body - the player is left leaderless and can never lose.  Leader status is
the CLASS TLeader (classref cell 0x557121F8, ClassID 0x20232), so it cannot move to another object; instead a marker
ability is moved along the chain and every "is this a leader?" decision also accepts the marker.

Marker = ability 0xCE "Leader's Soul": a plain TAbility instance (VMT 0x5570F254, Create 0x5574E5F4), [+0x24] 4 like
Possessed, [+0x20] 0 (TAbility.CanExpand -> never learnable).  A bit-only ability: TCustomAbilityList.ReadWrite saves
the bit with the unit.  Ability.pfs record: patch_leader_soul_ability_pfs_v1.py (key 216).

Hooks (zone AoWEPACK 0x55836800..0x55837800, assigned by the coordinator, verified zero + reloc-free; the header keeps
every site's original bytes so --revert restores them exactly):
  reg  RegisterAbility chain call @0x557BCF6E (decoded at apply time) -> `call prev`, then create + register 0xCE.
  c1..c7  `call IsClass 0x557010C0` -> `call isl` (IsClass OR holds 0xCE) at:
       c1 TCombatUnit.DestroyObject 0x5572577B + c2 Surrender 0x557257F0   -> the chain's final death = DEFEAT
       c3 TPossessAbility.CanTouch 0x55769C90 + c4 CanTouchUnit 0x55769CDE -> the soul body cannot be possessed
       c5 TCommandAbility.CreateCommandCA 0x5577037D + c6 fcGetDamageValueEx 0x557702A9 -> immune to Seduce/Charm/
          Dominate like a leader (the marker can never change sides)
       c7 TAbstractUnit.UpdateMoraleValue 0x5577F0A5 -> skips the morale/desertion update like a leader
  pg   TPossessCA.Execute 0x557697E7 (`mov edx,0x6b`): possessor (ebx) is a leader or holds 0xCE -> the new body
       [ebp+0x4C] gets 0xCE and the old body loses it.
  ic   TPossessedAbility.CombatObjectDestroyed 0x55769A4C: dying possessed body holds 0xCE -> the new Incarnate (edi)
       gets it (combat; tactical + auto share it).
  iv   TArmy.Validate 0x5578CFF4: same for the overworld Incarnate (esi old, ebp new).
  k1/k2  TUnit.Killed 0x5578281D / THero.Killed 0x557871F6 `call TAbstractUnit.Killed` -> kd: unit holds 0xCE, is
       NOT Possessed (0x6B: it becomes an Incarnate instead), is active ([+0x25]&2) and no combat runs
       ([map+0x120]==0) -> TAoWHSMap.GameOver(owner, 2) - a mirror of TLeader.Killed.  Then the vanilla Killed.
  cr   TArmy.Leader 0x5578DFD8 (ClassID == 0x20232 test) -> also true for 0xCE: the gold crown on the party shield
       (TArmy.UpdateConcealment sets [army+0x10]&0x20) and the AI's leader-army logic.
  vmt  TUnit 0x55710CAC + THero 0x55711FEC slots +0x9C GetUpkeep (-> 0), +0x17C GetUnitMoraleValue (-> 0x5A, the
       TLeader value = High) and +0x190 CanDisband (-> 0) when the unit holds 0xCE, else the saved original pointer.
  rf1/rf2  TResurrectHero/TAnimateHero.ExecuteTE dead-hero filter `IsClass(hero,TLeader)` 0x557EC152 / 0x557EC6BA:
       a dead leader whose death owner [hero+0x5C] == the caster's owner is remembered (FOUND) - still removed from
       the random pool like every leader.
  rp1/rp2  after the filter loop 0x557EC1A7 / 0x557EC70F: FOUND -> the pool becomes exactly that leader (PICK), so
       the owner's Resurrect/Animate Hero always brings its own leader back.  Other players never can (vanilla).
  oj1/oj2  `call [vmt+0x19C] OfferToJoin` 0x557EC2CA / 0x557EC832: hero == PICK -> no join offer; the leader's army
       is given straight to the caster (TArmy.SetPlayer, like Crusade's ExecuteTE) and the soul returns: the
       player's 0xCE unit loses the marker; if it is a possessed body it also loses Possessed (normal unit), if it is
       an Incarnate it is removed (Killed - no defeat, no new Incarnate).  Returns 0 (vanilla's info-log branch).
  Scratch FOUND/PICK = AoWEPACK .idata page slack 0x5590B3C0/0x5590B3C4 (runtime-only zero memory, set and consumed
  inside one ExecuteTE).  Everything else reads synced game state only (ability bits, class, owner) -> MP-safe; the
  [map+0x120] test in kd is the same one vanilla TLeader.Killed makes.  PIC: every in-image absolute via call/pop.
Dry-run default; --apply / --revert / --dis; --dll <scratch copy>.  Backup <game>\backup\AoWEPACK.dll.bak_leadersoul.
LIFO: re-decodes the RegisterAbility chain at 0x557BCF6E - revert this BEFORE reverting/re-running any script that
chains there (patch_reversal_v1, Smokescreen, Lucky, Tame, Channeler ...).
After applying: patch_leader_soul_ability_pfs_v1.py --apply, then add 0xCE to LADDER in
patch_aowx_banner_ceilings_v1.py and patch_tcablist_ceiling_v1.py (bound -> 0xCF) and re-run both.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_leadersoul"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55836800, 0x55837800
HDR = 0x100
TABLE_OFF, RETV_OFF, NAME_OFF = 0x80, 0xA0, 0xC0
AB, POSSESSED = 0xCE, 0x6B
NAME = b"Leader's Soul"
FOUND, PICK = 0x5590B3C0, 0x5590B3C4                       # runtime-only .idata page slack
ISCLASS, GAS = 0x557010C0, 0x5577F618                      # System.IsClass; TAbstractUnit.GetAbilitySet (bit test)
TLEADER_CELL, MAPCELL = 0x557121F8, 0x558FA040
GAMEOVER, ABKILLED = 0x55776838, 0x5578087C
GETPLAYERS, GETARMY, GETUNIT, GETHERO = 0x557544D0, 0x55750808, 0x5578309C, 0x5578A208
SETPLAYER = 0x5578D690
REGABIL, LSTRASG = 0x55750238, 0x55701150
AB_VMT, AB_CREATE = 0x5570F254, 0x5574E5F4
VMTS = (0x55710CAC, 0x55711FEC)                            # TUnit, THero (TLeader keeps its own slots)
SLOTS = ((0x9C, 0), (0x17C, 0x5A), (0x190, 0))             # GetUpkeep, GetUnitMoraleValue, CanDisband -> value
PTRS = [("v%d_%x" % (v, s), VMTS[v] + s, r) for v in range(len(VMTS)) for s, r in SLOTS]

def e8(va, tgt): return b"\xe8" + struct.pack("<i", tgt - (va + 5))
# (name, va, size, original bytes | None = chained call decoded at apply time, hook kind)
SITES = [
    ("reg", 0x557BCF6E, 5, None, "call"),
    ("c1", 0x5572577B, 5, e8(0x5572577B, ISCLASS), "call"),
    ("c2", 0x557257F0, 5, e8(0x557257F0, ISCLASS), "call"),
    ("c3", 0x55769C90, 5, e8(0x55769C90, ISCLASS), "call"),
    ("c4", 0x55769CDE, 5, e8(0x55769CDE, ISCLASS), "call"),
    ("c5", 0x5577037D, 5, e8(0x5577037D, ISCLASS), "call"),
    ("c6", 0x557702A9, 5, e8(0x557702A9, ISCLASS), "call"),
    ("c7", 0x5577F0A5, 5, e8(0x5577F0A5, ISCLASS), "call"),
    ("pg", 0x557697E7, 5, bytes.fromhex("ba6b000000"), "jmp"),
    ("ic", 0x55769A4C, 8, bytes.fromhex("8b464cba6b000000"), "jmp"),
    ("iv", 0x5578CFF4, 10, bytes.fromhex("8bc68b10ff92ac010000"), "jmp"),
    ("k1", 0x5578281D, 5, e8(0x5578281D, ABKILLED), "call"),
    ("k2", 0x557871F6, 5, e8(0x557871F6, ABKILLED), "call"),
    ("cr", 0x5578DFD8, 10, bytes.fromhex("8b00ff50243d32020200"), "call"),
    ("rf1", 0x557EC152, 5, e8(0x557EC152, ISCLASS), "call"),
    ("rf2", 0x557EC6BA, 5, e8(0x557EC6BA, ISCLASS), "call"),
    ("rp1", 0x557EC1A7, 7, bytes.fromhex("8bc68b10ff5254"), "jmp"),
    ("rp2", 0x557EC70F, 7, bytes.fromhex("8bc68b10ff5254"), "jmp"),
    ("oj1", 0x557EC2CA, 6, bytes.fromhex("ff919c010000"), "call"),
    ("oj2", 0x557EC832, 6, bytes.fromhex("ff919c010000"), "call"),
]
TARGET = {"c1": "isl", "c2": "isl", "c3": "isl", "c4": "isl", "c5": "isl", "c6": "isl", "c7": "isl",
          "k1": "kd", "k2": "kd", "rf1": "rf", "rf2": "rf", "oj1": "oj", "oj2": "oj"}
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def rel(op, va, target, size):
    return bytes([op]) + struct.pack("<i", target - (va + 5)) + b"\x90" * (size - 5)


def build(prev_reg):
    out = bytearray(HDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    S = {"ab": AB, "pos": POSSESSED, "gas": GAS, "isclass": ISCLASS, "tlc": TLEADER_CELL, "map": MAPCELL,
         "go": GAMEOVER, "abk": ABKILLED, "found": FOUND, "pick": PICK, "gp": GETPLAYERS, "ga": GETARMY,
         "gu": GETUNIT, "gh": GETHERO, "sp": SETPLAYER, "table": ZONE + TABLE_OFF, "retv": ZONE + RETV_OFF}

    place("isl", """
        push ebx
        mov ebx, eax
        call %(isclass)#x
        test al, al
        jne out
        test ebx, ebx
        je out
        mov eax, ebx
        mov edx, %(ab)d
        call %(gas)#x
    out:
        pop ebx
        ret
    """ % S)
    S["isl"] = where["isl"]

    place("islv", """
        push esi
        call d
    d:
        pop esi
        sub esi, d
        mov edx, [esi + %(tlc)#x]
        pop esi
        jmp %(isl)#x
    """ % S)
    S["islv"] = where["islv"]

    place("pg", """
        mov eax, ebx
        call %(islv)#x
        test al, al
        je back
        mov eax, [ebp + 0x4c]
        mov edx, %(ab)d
        mov cl, 1
        push esi
        mov esi, [eax]
        call dword ptr [esi + 0x50]
        pop esi
        mov eax, ebx
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je back
        mov eax, ebx
        mov edx, %(ab)d
        xor ecx, ecx
        push esi
        mov esi, [eax]
        call dword ptr [esi + 0x50]
        pop esi
    back:
        mov edx, %(pos)d
        jmp 0x557697EC
    """ % S)

    place("ic", """
        mov eax, [esi + 0x4c]
        test eax, eax
        je back
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je back
        mov eax, edi
        mov edx, %(ab)d
        mov cl, 1
        push ebx
        mov ebx, [eax]
        call dword ptr [ebx + 0x50]
        pop ebx
        mov eax, [esi + 0x4c]
        mov edx, %(ab)d
        xor ecx, ecx
        push ebx
        mov ebx, [eax]
        call dword ptr [ebx + 0x50]
        pop ebx
    back:
        mov eax, [esi + 0x4c]
        mov edx, %(pos)d
        jmp 0x55769A54
    """ % S)

    place("iv", """
        mov eax, esi
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je back
        mov eax, ebp
        mov edx, %(ab)d
        mov cl, 1
        push ebx
        mov ebx, [eax]
        call dword ptr [ebx + 0x50]
        pop ebx
        mov eax, esi
        mov edx, %(ab)d
        xor ecx, ecx
        push ebx
        mov ebx, [eax]
        call dword ptr [ebx + 0x50]
        pop ebx
    back:
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x1ac]
        jmp 0x5578CFFE
    """ % S)

    place("kd", """
        push eax
        push ebx
        push esi
        mov ebx, eax
        call d
    d:
        pop esi
        sub esi, d
        mov eax, ebx
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je out
        mov eax, ebx
        mov edx, %(pos)d
        call %(gas)#x
        test al, al
        jne out
        test byte ptr [ebx + 0x25], 2
        je out
        mov eax, [esi + %(map)#x]
        test eax, eax
        je out
        cmp dword ptr [eax + 0x120], 0
        jne out
        mov dl, [ebx + 0x24]
        mov cl, 2
        call %(go)#x
    out:
        pop esi
        pop ebx
        pop eax
        jmp %(abk)#x
    """ % S)

    place("cr", """
        push eax
        mov ecx, [eax]
        call dword ptr [ecx + 0x24]
        cmp eax, 0x20232
        pop eax
        je yes
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je no
    yes:
        xor eax, eax
        ret
    no:
        or eax, 1
        ret
    """ % S)

    place("vc", """
        push ecx
        push edx
        push esi
        call d
    d:
        pop esi
        sub esi, d
        push eax
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        pop eax
        mov ecx, [esp + 12]
        jne mine
        mov ecx, [esi + ecx*4 + %(table)#x]
        add ecx, esi
        mov [esp + 12], ecx
        pop esi
        pop edx
        pop ecx
        ret
    mine:
        mov eax, [esi + ecx*4 + %(retv)#x]
        pop esi
        pop edx
        pop ecx
        add esp, 4
        ret
    """ % S)
    for i in range(len(PTRS)):
        place("t%d" % i, "push %d\njmp %#x" % (i, where["vc"]))

    place("rf", """
        push ebx
        push esi
        mov ebx, eax
        call %(isclass)#x
        test al, al
        je out
        call d
    d:
        pop esi
        sub esi, d
        cmp dword ptr [esi + %(found)#x], 0
        jne one
        mov eax, [ebp - 0xc]
        mov al, [eax + 0x24]
        cmp al, [ebx + 0x5c]
        jne one
        mov [esi + %(found)#x], ebx
    one:
        mov al, 1
    out:
        pop esi
        pop ebx
        ret
    """ % S)

    place("rpc", """
        push ebx
        push edi
        call d
    d:
        pop edi
        sub edi, d
        mov ebx, [edi + %(found)#x]
        mov dword ptr [edi + %(found)#x], 0
        mov dword ptr [edi + %(pick)#x], 0
        test ebx, ebx
        je out
        mov [edi + %(pick)#x], ebx
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        push eax
    lp:
        dec dword ptr [esp]
        js ldone
        mov edx, [esp]
        mov eax, esi
        call %(gh)#x
        test eax, eax
        je lp
        mov edx, eax
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x6c]
        jmp lp
    ldone:
        add esp, 4
        mov edx, ebx
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x70]
    out:
        pop edi
        pop ebx
        ret
    """ % S)
    S["rpc"] = where["rpc"]
    for nm, back in (("rp1", 0x557EC1AE), ("rp2", 0x557EC716)):
        place(nm, """
            call %(rpc)#x
            mov eax, esi
            mov edx, [eax]
            call dword ptr [edx + 0x54]
            jmp %(back)#x
        """ % dict(S, back=back))

    place("oj", """
        push esi
        call d
    d:
        pop esi
        sub esi, d
        test eax, eax
        je vanilla
        cmp eax, [esi + %(pick)#x]
        jne vanilla
        mov dword ptr [esi + %(pick)#x], 0
        pushad
        mov ebx, eax
        mov edi, edx
        mov eax, [ebx + 0x20]
        test eax, eax
        je soul
        mov edx, edi
        call %(sp)#x
    soul:
        mov eax, [esi + %(map)#x]
        mov eax, [eax + 0x140]
        mov edx, edi
        movsx edx, dl
        call %(gp)#x
        test eax, eax
        je done
        mov ebp, [eax + 0x28]
        mov eax, ebp
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        mov ebx, eax
    al_loop:
        dec ebx
        js done
        mov edx, ebx
        mov eax, ebp
        call %(ga)#x
        mov edi, eax
        test edi, edi
        je al_loop
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        push eax
    ul:
        dec dword ptr [esp]
        js ul_done
        mov edx, [esp]
        mov eax, edi
        call %(gu)#x
        test eax, eax
        je ul
        push eax
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        pop eax
        je ul
        push eax
        mov edx, %(ab)d
        xor ecx, ecx
        push esi
        mov esi, [eax]
        call dword ptr [esi + 0x50]
        pop esi
        pop eax
        push eax
        mov edx, %(pos)d
        call %(gas)#x
        test al, al
        pop eax
        je kill
        push eax
        mov edx, %(pos)d
        push esi
        mov esi, [eax]
        call dword ptr [esi + 0x98]
        pop esi
        pop eax
        push esi
        mov esi, [eax]
        call dword ptr [esi + 0x90]
        pop esi
        jmp found_one
    kill:
        push esi
        mov esi, [eax]
        call dword ptr [esi + 0x1ac]
        pop esi
    found_one:
        add esp, 4
        jmp done
    ul_done:
        add esp, 4
        jmp al_loop
    done:
        popad
        pop esi
        xor eax, eax
        ret
    vanilla:
        pop esi
        jmp dword ptr [ecx + 0x19c]
    """ % S)

    place("reg", """
        call %(prev)#x
        push esi
        call d
    d:
        pop esi
        sub esi, d
        lea eax, [esi + %(vmt)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(ab)d
        mov byte ptr [eax + 0x24], 4
        mov word ptr [eax + 0x20], 0
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % dict(S, prev=prev_reg, vmt=AB_VMT, create=AB_CREATE, name=ZONE + NAME_OFF + 8, lstrasg=LSTRASG, reg=REGABIL))
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    # header data (site bytes + VMT table are filled by main): return values + the name literal
    for i, (_nm, _va, r) in enumerate(PTRS): out[RETV_OFF + 4 * i:RETV_OFF + 4 * i + 4] = struct.pack("<I", r)
    lit = struct.pack("<ii", -1, len(NAME)) + NAME + b"\0"
    assert NAME_OFF + len(lit) <= HDR
    out[NAME_OFF:NAME_OFF + len(lit)] = lit
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
    applied = any(zl[HDR:])
    saved = {}; o = 0
    for name, va, n, _o, _k in SITES: saved[name] = zl[o:o + n]; o += n
    assert o <= TABLE_OFF
    for i, (name, va, _r) in enumerate(PTRS): saved[name] = zl[TABLE_OFF + 4 * i:TABLE_OFF + 4 * i + 4]
    cur = {name: g(va, n) for name, va, n, _o, _k in SITES}
    cur.update({name: g(va, 4) for name, va, _r in PTRS})
    src = saved if applied else cur
    reg_b = src["reg"]
    assert reg_b[0] == 0xE8, "RegisterAbility chain site 0x557BCF6E is not a call (%s)" % reg_b.hex()
    prev_reg = 0x557BCF6E + 5 + struct.unpack_from("<i", reg_b, 1)[0]
    if not applied:
        wrong = [(nm, cur[nm].hex()) for nm, _va, _n, orig, _k in SITES if orig is not None and cur[nm] != orig]
        if wrong: print("ABORT: sites not in the expected (vanilla) state: %s" % wrong); return 1
        for nm, _va, _r in PTRS:
            x = struct.unpack("<I", cur[nm])[0]
            assert 0x55700000 < x < 0x558E8000 and not (ZONE <= x < ZONE_END), (nm, hex(x))
    zone, where = build(prev_reg)
    hdr = bytearray(zone[:HDR]); o = 0
    for name, va, n, _o, _k in SITES: hdr[o:o + n] = src[name]; o += n
    for i, (name, va, _r) in enumerate(PTRS): hdr[TABLE_OFF + 4 * i:TABLE_OFF + 4 * i + 4] = src[name]
    zone = bytes(hdr) + zone[HDR:]
    hooked = {}
    for name, va, n, _o, kind in SITES:
        hooked[name] = rel(0xE8 if kind == "call" else 0xE9, va, where[TARGET.get(name, name)], n)
    hooked.update({name: struct.pack("<I", where["t%d" % i]) for i, (name, va, _r) in enumerate(PTRS)})
    allsites = [(nm, va, n) for nm, va, n, _o, _k in SITES] + [(nm, va, 4) for nm, va, _r in PTRS]
    st = {nm: ("ours" if cur[nm] == hooked[nm] else "orig" if (not applied or cur[nm] == saved.get(nm)) else "OTHER")
          for nm, _va, _n in allsites}
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for _nm, va, n, _o, _k in SITES)]
    ptr_reloc_ok = all(va in rl for _nm, va, _r in PTRS)
    print("sites %s | VMT slots %s | reg prev %#x | zone %s (%d B used of %d) | relocs in zone/sites %s | slot relocs %s"
          % (" ".join("%s=%s" % (k, st[k]) for k, *_ in SITES), sorted(set(st[nm] for nm, _va, _r in PTRS)), prev_reg,
             zstate, len(zone), ZONE_END - ZONE, bad or "none", "ok" if ptr_reloc_ok else "MISSING"))
    print("caves: " + ", ".join("%s=%#x" % (k, v) for k, v in where.items() if not (k.startswith("t") and k != "t0")))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        inv = {v: k for k, v in where.items()}
        for i in md.disasm(zone[HDR:], ZONE + HDR):
            if i.address in inv: print("  %s:" % inv[i.address])
            print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or not ptr_reloc_ok or "OTHER" in st.values() or zstate == "DIFFERS": print("ABORT"); return 1
    if a.revert:
        if not applied: print("already reverted"); return 0
        out = bytearray(d)
        for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = saved[nm]
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (sites + VMT slots restored from the zone header)"); return 0
    if all(v == "ours" for v in st.values()) and zstate == "ours": print("already applied"); return 0
    if applied: print("ABORT: zone holds our code but the sites do not all point at it"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = hooked[nm]
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
