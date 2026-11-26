"""
PLAGUE POISON (2026-10-15).  AoWEPACK.dll only.  341 Plague's infected cities poison the units standing in them each
turn, exactly as a Poison Plant does (user: "similar to poison plants - rolls for damage/poison each turn on any
units standing in city").

Vanilla Poison Plant (PoisonP.TPoisonPlant, VMT 0x557C3A78):
  * MsgProc 0x557C44C8: on the player new-turn broadcast 0x20020002 ([msg+0x18] = player) -> 0x557C42F0: if the plant
    is active (0x557C3F90: not on snow / wasteland), find the TArmy on its hex (field VMT+0x80 FindOwnedChild 0x20217)
    and, if the army's owner ([[army+0x1C]+0x12]) is the player whose turn starts, TriggerArmyDamage.  (Field msg 0x1142
    = an army entering the hex triggers it at once too, 0x557C428C.)
  * TriggerArmyDamage 0x557C4044 (eax self, edx army): seeds [0x558FB720] from map.Random (SYNCED stream), builds the
    damage report, then per unit of [army+0x1C]: skip if VMT+0xEC & 0x10 or Flying (HasAbility 1); damage =
    ExecuteDamageRole 0x55781AC4(unit, strength 4, 3, mask word [0x557C4288] = 0x10 POISON) (immunity / RES as vanilla),
    capped at HP, HP -= dmg (VMT+0xE4), alive -> ExecuteDamageEffects 0x55781E28(mask) = Poisoned roll (our
    patch_storm_effect_roll makes it roll vs RES); report rows; afterwards, if any unit was hurt, the map FX/report at
    self's position (self VMT+0x74/+0x78/+0x7C) and 0x5578CF7C (dead-unit cleanup) on the unit list.

Plague: TCity.NewTurn 0x557AB814 (eax city, dl player whose turn starts) runs on every player's new turn; its first
call `call 0x557A6200` @0x557AB81E (5 B rel32, reloc-free) -> cave `pt`: replays that call, then if the city is plagued
(patch_blesseddew_v1.py v4's INF_EXPORT 0x5582BFF0: esi = city -> al) collects the armies in the city exactly as
ExecuteFountainOfLife 0x557A9CB8 does (TList class [0x557134EC] ctor 0x557032D4, city VMT+0x1D8 fills it, item i =
0x5579229C, Free 0x557010B8) and calls TriggerArmyDamage(eax = army, edx = army) for each army owned by that player.
self = the ARMY (its own VMT+0x74/+0x78/+0x7C = its map position, which Fountain of Life also uses) - the city's
TStructure position getters differ from TILTerrainMO's.  Same damage, same poison roll, same report as a plant; once
per army per its owner's turn.  Deterministic (synced map RNG inside TriggerArmyDamage), MP-safe.
PIC: the one in-image absolute ([0x557134EC]) is read through a call/pop delta.

v2 (2026-10-15; user: "should apply at the same time as poison plants would - when a unit moves onto it at any time, or
at the beginning of turn if standing on it"): ON-ENTRY trigger.  The army move step (0x55791189) sends field message
0x1142 ([msg+8] = the moving TArmy, [msg+0x18] = the field) via TMapField.SendMapFieldMsg to the objects on the hex it
enters; a plant's MapFieldMsgProc (its VMT slot 0x557C3B84) checks the field is its own ([[self+8]+0x28].IndexOf) and calls
0x557C428C -> TriggerArmyDamage(plant, army) unless [[0x558E9494]]+0x3C has bit 2.  TCity has its OWN MapFieldMsgProc
0x557AD614 (VMT slot 0x557A74BC = TCity vmt +0xCC; the plant's slot is at a +0x40 shifted vmt base - aligned via the
shared ControlMode slot).  v2 redirects that slot (relocated, only reference) to cave `ent`: calls 0x557AD614 first,
then for msg 0x1142 on one of the city's own fields, in a plagued city (INF_EXPORT), with the same global guard as the
plant: TriggerArmyDamage(eax = army, edx = army) - same damage/poison roll/report, any owner's army.  Like a plant it
fires on EVERY entry into a city hex (moving between two hexes of the same city triggers again, exactly as between two
plant hexes); it is a different event from the turn-start trigger, so no double-fire.

Zone 0x55832000..0x55832200 (zero, reloc-free).  Requires patch_blesseddew_v1.py v4 (INF_EXPORT) - --apply refuses
otherwise; revert THIS script before reverting Plague.  Dry-run default; --apply / --revert / --dis.
Backup <game>\\backup\\AoWEPACK.dll.bak_plaguepoison.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55832000, 0x55832200
SLOT, SLOT_ORIG = 0x557A74BC, 0x557AD614   # TCity VMT +0xCC = MapFieldMsgProc (v2 on-entry trigger)
INDEXOF, GLOBAL_STATE = 0x55701C8C, 0x558E9494
SITE, SITE_ORIG = 0x557AB81E, bytes.fromhex("e8dda9ffff")      # TCity.NewTurn: call 0x557A6200 (crop new turn)
CROP_NT = 0x557A6200
INF_EXPORT = 0x5582BFF0            # patch_blesseddew_v1.py v4: jmp inf (esi = city -> al = plagued, regs preserved)
TLIST_CLS, TLIST_CTOR, LIST_GET, TOBJ_FREE = 0x557134EC, 0x557032D4, 0x5579229C, 0x557010B8
TRIGGER = 0x557C4044               # TPoisonPlant.TriggerArmyDamage (eax self, edx army)
BAK = "bak_plaguepoison"
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build():
    va = ZONE; pd = va + 5
    src = """
        call pd
    pd:
        pop ecx
        sub ecx, %(pd)#x
        push ecx
        push eax
        push edx
        call %(crop)#x
        pop edx
        pop eax
        pop ecx
        pushad
        mov ebp, ecx
        mov esi, eax
        mov ebx, edx
        call %(inf)#x
        test al, al
        jz pt_done
        xor ecx, ecx
        mov dl, 1
        mov eax, dword ptr [ebp + %(cls)#x]
        call %(ctor)#x
        mov edi, eax
        mov edx, edi
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x1d8]
        mov eax, edi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov ebp, eax
    pt_loop:
        dec ebp
        js pt_fin
        mov edx, ebp
        mov eax, edi
        call %(get)#x
        test eax, eax
        jz pt_loop
        mov edx, dword ptr [eax + 0x1c]
        test edx, edx
        jz pt_loop
        cmp bl, byte ptr [edx + 0x12]
        jne pt_loop
        mov edx, eax
        call %(trig)#x
        jmp pt_loop
    pt_fin:
        mov eax, edi
        call %(free)#x
    pt_done:
        popad
        ret
    """ % {"pd": pd, "crop": CROP_NT, "inf": INF_EXPORT, "cls": TLIST_CLS, "ctor": TLIST_CTOR, "get": LIST_GET,
           "trig": TRIGGER, "free": TOBJ_FREE}
    code = bytes(ks.asm(src, va)[0])
    ev = (va + len(code) + 15) & ~15; epd = ev + 0x40       # placeholder, re-solved below
    def ent_src(epd):
        return """
        push ebx
        push esi
        push edi
        mov esi, eax
        mov ebx, edx
        call %(orig)#x
        cmp dword ptr [ebx], 0x1142
        jne e_done
        mov edx, dword ptr [ebx + 0x18]
        mov eax, dword ptr [esi + 8]
        mov eax, dword ptr [eax + 0x28]
        call %(idx)#x
        test al, al
        jl e_done
        call %(inf)#x
        test al, al
        jz e_done
        call %(epd)#x
        pop edi
        sub edi, %(epd)#x
        mov eax, dword ptr [edi + %(glob)#x]
        mov eax, dword ptr [eax]
        test byte ptr [eax + 0x3c], 2
        jne e_done
        mov edx, dword ptr [ebx + 8]
        test edx, edx
        jz e_done
        mov eax, edx
        call %(trig)#x
    e_done:
        pop edi
        pop esi
        pop ebx
        ret
        """ % {"orig": SLOT_ORIG, "idx": INDEXOF, "inf": INF_EXPORT, "epd": epd, "glob": GLOBAL_STATE, "trig": TRIGGER}
    # solve the call/pop label address: assemble once to find the offset of the `pop edi` after `call epd`
    probe = bytes(ks.asm(ent_src(ev + 0x100), ev)[0])
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    ins = list(md.disasm(probe, ev))
    k = next(n for n, i in enumerate(ins) if i.mnemonic == "pop" and i.op_str == "edi" and n > 0 and ins[n - 1].mnemonic == "call")
    epd = ins[k].address
    ent = bytes(ks.asm(ent_src(epd), ev)[0])
    assert list(md.disasm(ent, ev))[k].address == epd
    code = code + bytes(ev - va - len(code)) + ent
    return code, {"pt": va, "ent": ev}


def hook(target):
    return b"\xe8" + struct.pack("<i", target - (SITE + 5))


def relocs(d):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    zone, where = build(); assert ZONE + len(zone) <= ZONE_END
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or SITE <= r < SITE + 5]
    live = bytes(d[SITE - CODE_V2F:SITE - CODE_V2F + 5]); h = hook(where["pt"])
    tgt = SITE + 5 + struct.unpack_from("<i", live, 1)[0] if live[0] == 0xE8 else None
    sstate = "vanilla" if live == SITE_ORIG else "ours" if live == h else ("ours(old)" if tgt and ZONE <= tgt < ZONE_END else "OTHER")
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    exp = bytes(d[INF_EXPORT - CODE_V2F:INF_EXPORT - CODE_V2F + 5])
    exp_ok = exp[0] == 0xE9 and 0x5582A000 <= INF_EXPORT + 5 + struct.unpack_from("<i", exp, 1)[0] < 0x5582C000
    slot_live = struct.unpack_from("<I", d, SLOT - CODE_V2F)[0]
    lstate = "vanilla" if slot_live == SLOT_ORIG else "ours" if slot_live == where["ent"] else ("ours(old)" if ZONE <= slot_live < ZONE_END else "OTHER")
    slot_reloc = SLOT in rl
    print("site %s | slot %s (reloc %s) | zone %s (%d B: pt=%#x ent=%#x) | relocs %s | Plague INF_EXPORT %s" % (
        sstate, lstate, "ok" if slot_reloc else "MISSING", zstate, len(zone), where["pt"], where["ent"], bad or "none",
        "ok" if exp_ok else "MISSING (apply patch_blesseddew_v1.py v4 first)"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone, ZONE):
            if i.bytes == bytes(2): continue
            print("   %08X %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate == "OTHER" or lstate == "OTHER" or not slot_reloc: print("ABORT"); return 1
    if a.revert:
        if sstate == "vanilla" and zstate == "zero" and lstate == "vanilla": print("not applied"); return 0
        d[SITE - CODE_V2F:SITE - CODE_V2F + 5] = SITE_ORIG
        struct.pack_into("<I", d, SLOT - CODE_V2F, SLOT_ORIG)
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        open(DLL, "r+b").write(bytes(d)); print("reverted"); return 0
    if sstate == "ours" and zstate == "ours" and lstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and sstate == "vanilla": print("ABORT (zone not free)"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    out[SITE - CODE_V2F:SITE - CODE_V2F + 5] = h
    struct.pack_into("<I", out, SLOT - CODE_V2F, where["ent"])
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not exp_ok: print("ABORT: Plague INF_EXPORT missing - apply patch_blesseddew_v1.py v4 first"); return 1
    bak = bak_path(DLL, BAK)
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    open(DLL, "r+b").write(bytes(out))
    assert open(DLL, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
