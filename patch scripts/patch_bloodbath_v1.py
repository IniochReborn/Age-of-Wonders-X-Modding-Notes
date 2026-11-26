#!/usr/bin/env python3
r"""
Bloodbath (dual-sphere spell id 350, Death/Fire tier 2): High Prayer clone that grants BLOODLUST (2026-10-04).

The spell object is registered by patch_dual_sphere_spells_v1.py as a THighPrayer instance with id 350.  High
Prayer's combat actions hard-code the ability they grant, so this patch makes the grant depend on the spell id:

  tactical combat  TTacticalCombatHighPrayerCA.Execute 0x557F7E98: ebx = CA at entry ([ca+0x18] = spell id,
                   stamped by THighPrayer.CreateCA), but ebx is reused for the target unit before the grant.
     H1 0x557F7EA7  `cmp byte [ebx+0x14],0 / je 0x557F7EF7` (6 B) -> jmp cave: stash [ca+0x18] in DATA slack
                   STASH, replay the compare, branch as vanilla.
     H2 0x557F7EE2  `mov edx,0x64` (THighPrayerBlessing ability id) -> call cave: edx = STASH==350 ? 0xA8 : 0x64.
     H5 0x557F7ECF  `call [ecx+0x8C]` SetHitPoints(hp+5) -> call cave: skipped when STASH==350 (Bloodbath does
                   not heal - 2026-10-05).
     H7 0x557F7EF1  `call [ecx+0xD0]` ability.Expand(unit) -> call cave: Expand, then unit.Changed (VMT+0x90).
  fast combat      TFastCombatHighPrayerCA.Generate 0x557F7E20 hard-codes [ca+0x1C] = 0x66 (High Prayer's own id)
     H3 0x557F80F3  `call Generate` inside THighPrayer.fcExecuteCombatCommand (edi = spell, ebx = CA) -> call cave:
                   call Generate, then [ca+0x1C] = [spell+0x10].
     H4 0x557F7DFF  `mov edx,0x64` in TFastCombatHighPrayerCA.Execute (edi = CA) -> call cave: edx by [ca+0x1C].
     H6 0x557F7DEC  `call [ecx+0x8C]` SetHitPoints(hp+5) -> call cave: skipped when [ca+0x1C]==350.
     H8 0x557F7E0E  `call [ecx+0xD0]` ability.Expand(unit) -> same cave as H7.
  Why the Changed call (H7/H8): TUnit caches its ability stat bonuses in bytes +0x44..+0x47 and only TUnit.Changed
  (GetAbAttackAll & co) refreshes them; THero sums enabled abilities live.  Vanilla High Prayer / Blood Shrine call
  ability.Expand directly (TAbilityOwner.ExpandAbility = Expand + Changed is NOT used), so plain units showed the
  ability but not its +1 att / +2 dmg / -1 def until some later Changed.  Also fixes vanilla High Prayer's +2 def /
  +2 res on non-hero units in the same battle.
  Bloodlust = ability 0xA8 (TBloodlustAbility), the same one the Blood Shrine grants; it is a world-day duration
  ability (GetTotalDuration VMT+0x110 = 5 days), so unlike High Prayer's blessing it outlives the battle.
  v3 (2026-10-09) COMBAT-ONLY: TDurationAbility instances carry a mode byte +0x28 (0 permanent, 1 days, 2 combat
  turns, 3 combat only; THighPrayerBlessingAbility ctor sets 3 @0x557BB7C2, TBloodlustAbility ctor sets 1
  @0x557B9D74) and TDurationAbility.CombatDone 0x55764E00 (reached from TCombatUnit.CombatDone 0x55724B54 ->
  TAbilityOwner.TriggerCombatDone 0x5574FEC4 -> ability VMT+0xFC, tactical and fast combat alike) removes modes 2/3
  via owner.RemoveAbility.  Per-unit state is a TDurationAbilityData record (chain at [owner+0x10]; +0xC turns
  left, +0xD player byte, +0xE id, +0x10 unused dword, streamed with the save) found by
  TAbilityOwner.GetAbilityData 0x5574F1C4 (eax=owner, edx=id); TDurationAbility.Expand 0x55765054 creates the
  record or just refreshes the turns of an existing one.  So: c7 stamps [rec+0x10] = 350 only when no record
  existed before Expand (a Blood Shrine Bloodlust already there stays unflagged = keeps its days), and
     H9 0x55764E06  `mov al,[ebx+0x28] / add al,-2 / sub al,2 / jae keep` (9 B) -> jmp cave: also take the remove
                   path for mode 1 when GetAbilityData(cu.GetUnit (VMT+0xB8), id)+0x10 == 350.
     H10 0x55764E5A `mov al,[ebx+0x28] / dec al / je days` (7 B) in TDurationAbility.GetName 0x55764E28 -> jmp
                   cave: a mode-1 ability with a Bloodbath-flagged record takes the "(combat only)" branch
                   @0x55764FAF (resstr 0x55706DB4), so the unit window reads "Bloodlust (combat only)".

Caves 0x55862000.. (CODE zero tail), STASH = DATA slack dword 0x558E9B60 (after the dual-sphere name table).
All PIC (rel32 + call/pop delta).  Backup <game>\backup\AoWEPACK.dll.bak_bloodbath.  Surgical --revert.
Re-apply re-syncs the zone (new caves are added to an already-patched dll).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")   # 2026-10-11: de-baked
BAK_SUFFIX = ".bak_bloodbath"
BASE, CODE_V2F = 0x55700000, 0x55700C00
SPELL_ID = 350
ABIL_BLESSING, ABIL_BLOODLUST = 0x64, 0xA8
GENERATE = 0x557F7E20
STASH = 0x558E9B60
GETABDATA = 0x5574F1C4                  # TAbilityOwner.GetAbilityData(eax=owner, edx=ability id) -> record or nil
CD_REMOVE, CD_KEEP = 0x55764E0F, 0x55764E24   # TDurationAbility.CombatDone: remove path / keep path
GN_DAYS, GN_NEXT, GN_COMBAT = 0x55764E76, 0x55764E61, 0x55764FAF   # TDurationAbility.GetName: days branch / rest of the switch / "(combat only)" branch
ZONE, ZONE_END = 0x55862000, 0x55862200       # v3 grew past 0x55862100 (next free AoWEPACK cave 0x55862200)

# (site VA, original bytes, hook kind, cave name)
HOOKS = [(0x557F7EA7, bytes.fromhex("807b1400744a"), "jmp", "c1"),
         (0x557F7EE2, bytes.fromhex("ba64000000"), "call", "c2"),
         (0x557F80F3, bytes.fromhex("e828fdffff"), "call", "c3"),
         (0x557F7DFF, bytes.fromhex("ba64000000"), "call", "c4"),
         (0x557F7ECF, bytes.fromhex("ff918c000000"), "call", "c5"),
         (0x557F7DEC, bytes.fromhex("ff918c000000"), "call", "c6"),
         (0x557F7EF1, bytes.fromhex("ff91d0000000"), "call", "c7"),
         (0x557F7E0E, bytes.fromhex("ff91d0000000"), "call", "c7"),
         (0x55764E06, bytes.fromhex("8a432804fe2c027315"), "jmp", "c9"),   # TDurationAbility.CombatDone mode test
         (0x55764E5A, bytes.fromhex("8a4328fec87415"), "jmp", "c10")]      # TDurationAbility.GetName mode switch
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out)
        where[name] = va; out.extend(asm(src % {"va6": va + 6, "va7": va + 7, "stash": STASH, "id": SPELL_ID,
                                               "bless": ABIL_BLESSING, "blood": ABIL_BLOODLUST, "gen": GENERATE,
                                               "abdata": GETABDATA, "rem": CD_REMOVE, "keep": CD_KEEP,
                                               "gn_days": GN_DAYS, "gn_next": GN_NEXT, "gn_combat": GN_COMBAT}, va))
    place("c1", """
        push eax
        push ecx
        call %(va7)#x
        pop ecx
        sub ecx, %(va7)#x
        mov eax, [ebx+0x18]
        mov [ecx+%(stash)#x], eax
        pop ecx
        pop eax
        cmp byte ptr [ebx+0x14], 0
        je 0x557F7EF7
        jmp 0x557F7EAD
    """)
    place("c2", """
        push ecx
        call %(va6)#x
        pop ecx
        sub ecx, %(va6)#x
        mov edx, %(bless)d
        cmp dword ptr [ecx+%(stash)#x], %(id)d
        jne done
        mov edx, %(blood)d
    done:
        pop ecx
        ret
    """)
    place("c3", """
        call %(gen)#x
        mov eax, [edi+0x10]
        mov [ebx+0x1c], eax
        ret
    """)
    place("c4", """
        mov edx, %(bless)d
        cmp dword ptr [edi+0x1c], %(id)d
        jne done
        mov edx, %(blood)d
    done:
        ret
    """)
    place("c5", """
        push ecx
        call %(va6)#x
        pop ecx
        sub ecx, %(va6)#x
        cmp dword ptr [ecx+%(stash)#x], %(id)d
        pop ecx
        je skip
        call [ecx+0x8c]
    skip:
        ret
    """)
    place("c6", """
        cmp dword ptr [edi+0x1c], %(id)d
        je skip
        call [ecx+0x8c]
    skip:
        ret
    """)
    # c7 (v3 2026-10-09): Expand + Changed as before, and when the grant CREATED the unit's Bloodlust record (no
    # TDurationAbilityData existed before Expand) stamp its unused dword +0x10 with the spell id = "combat only".
    # A record that already existed (Blood Shrine's 5-day Bloodlust) is merely refreshed by Expand and stays unflagged.
    # Entry: eax = ability, ecx = [eax], edx = strategic unit, ebx = TCombatUnit; eax is not used by the callers.
    place("c7", """
        push ebx
        push esi
        push edi
        mov esi, eax
        mov edi, edx
        mov eax, edi
        mov edx, [esi+0xc]
        call %(abdata)#x
        push eax
        mov eax, esi
        mov edx, edi
        mov ecx, [esi]
        call [ecx+0xd0]
        pop ecx
        test ecx, ecx
        jnz done
        cmp dword ptr [esi+0xc], %(blood)d
        jne done
        mov eax, edi
        mov edx, %(blood)d
        call %(abdata)#x
        test eax, eax
        jz done
        mov dword ptr [eax+0x10], %(id)d
    done:
        mov eax, edi
        mov edx, [eax]
        call [edx+0x90]
        pop edi
        pop esi
        pop ebx
        ret
    """)
    # c9: TDurationAbility.CombatDone's mode test.  Vanilla drops modes 2 (combat turns) and 3 (combat only); we also
    # drop a mode-1 (days) ability whose record carries the Bloodbath flag.  Entry: ebx = ability, esi = TCombatUnit.
    place("c9", """
        movzx eax, byte ptr [ebx+0x28]
        cmp eax, 2
        je rem
        cmp eax, 3
        je rem
        cmp eax, 1
        jne keep
        mov eax, esi
        mov edx, [esi]
        call [edx+0xb8]
        test eax, eax
        jz keep
        mov edx, [ebx+0xc]
        call %(abdata)#x
        test eax, eax
        jz keep
        cmp dword ptr [eax+0x10], %(id)d
        jne keep
    rem:
        jmp %(rem)#x
    keep:
        jmp %(keep)#x
    """)
    # c10: TDurationAbility.GetName 0x55764E28 (eax=ability -> ebx, edx=owner -> esi, ecx=&result -> edi) switches on
    # the mode byte: 1 -> "(n/m days)" @0x55764E76, 2 -> turns @0x55764F1D, 3 -> "(combat only)" @0x55764FAF.  A
    # mode-1 ability whose record is Bloodbath-flagged takes the mode-3 branch, so the unit window reads
    # "Bloodlust (combat only)" like High Prayer's blessing.  Hook replaces `mov al,[ebx+0x28] / dec al / je days`.
    place("c10", """
        cmp byte ptr [ebx+0x28], 1
        jne plain
        mov eax, esi
        mov edx, [ebx+0xc]
        call %(abdata)#x
        test eax, eax
        jz plain
        cmp dword ptr [eax+0x10], %(id)d
        jne plain
        jmp %(gn_combat)#x
    plain:
        mov al, [ebx+0x28]
        dec al
        je %(gn_days)#x
        jmp %(gn_next)#x
    """)
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def hook(va, orig, kind, target):
    b = (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", target - (va + 5))
    return b + b"\x90" * (len(orig) - 5)


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
    zone, where = build()
    hooks = [(va, orig, hook(va, orig, kind, where[cave])) for va, orig, kind, cave in HOOKS]
    live = [bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)]) for va, orig, _h in hooks]
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    rl = reloc_set(d)
    bad = [r for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(orig) for va, orig, _h in hooks)]
    def is_ours(l, va):
        return l[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", l, 1)[0] < ZONE_END and all(b == 0x90 for b in l[5:])
    state = ["vanilla" if l == orig else "ours" if is_ours(l, va) else "OTHER" for (va, orig, _h), l in zip(hooks, live)]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("sites %s | zone %s | relocs %s | caves %s" % (state, zstate, bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if bad or "OTHER" in state: print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for name, s in where.items():
            print("  --", name)
            for i in md.disasm(zone[s - ZONE:], s):
                print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
                if i.mnemonic in ("ret",) or (i.mnemonic == "jmp" and name == "c1") or (name == "c9" and i.mnemonic == "jmp" and int(i.op_str, 16) == CD_KEEP) or (name == "c10" and i.mnemonic == "jmp" and int(i.op_str, 16) == GN_NEXT): break
    if a.revert:
        out = bytearray(d)
        for (va, orig, _h), st in zip(hooks, state):
            if st == "ours": out[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if all(s == "ours" for s in state) and zstate == "ours" and all(l == h for (va, orig, h), l in zip(hooks, live)):
        print("already applied"); return 0
    if "ours" not in state and zstate != "zero": print("ABORT: zone not zero on a vanilla dll"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for va, orig, h in hooks: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = h
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
