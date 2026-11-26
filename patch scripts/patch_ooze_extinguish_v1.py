#!/usr/bin/env python3
r"""
Ooze puts out fires and clears Burning inside its mud area (AoWTCPCK.dll, 2026-09-23).  Easter egg; the AI
never values it (TCAI scores spells through GetCombatDamageValue only).

How Ooze works (CombatTE.TCAbRangedTE): the TE fires 19 "strikes" (Execute 0x40B55F sets [te+0x28]=0x13 for
spell 0x7C), one TfxHS per strike aimed at one hex of the radius-2 area (19 = 5x5 hex blob around the cursor).
When an effect has landed, Execute's per-effect loop (0x40B78E.., fx = TList [[0x469420]+0x11C][i]) runs the
spell case: [fx+0x14]==0x34 (spell), [fx+0x34]==0xA, [fx+0x18]==0x7C -> 0x40C922: field = GetField(GetMapLevel
(container,0), x=[ebp-0x28], y=[ebp-0x2C]); if the terrain allows ([field+0x14] not 0/7/9/0xF, [field+0x15]
not 2/8/0xB) a TCOozeHS mud decal is placed there.  fx position -> hex via TXYZList.GetXYZ + HPtoHX.

Patch: 5-byte hook at 0x40C922 (`mov eax,[0x469420]`, reloc at 0x40C923 -> neutralised, type 3->0) -> cave,
which for that hex (before the terrain checks, so wall/water hexes count too):
  * fire: while field.FindOwnedChild(ClassID 0x22054A TCombatFire) -> TObject.Free (THexagonSprite.Destroy
    removes it from the map; same idiom as TCombatFire.NewTurn).  Burning wood walls ARE a fire HS on the wall
    hex (TCityWall only takes msg 0x31007 damage each turn while a fire sits there) -> extinguished too.
  * unit: field.FindOwnedChild(0x220104 TTacticalCombatUnitHS) -> [hs+0x1C] TTacticalCombatUnit; if
    GetAbilityEnabled(0x7F Burning) (VMT+0xA8) then TAbstractUnit.RemoveAbility([cu+0x4C], 0x7F) in AoWEPACK
    (reached through TCPCK's import slot of TCombatUnit.SetUnit 0x46E858 + constant delta; EPACK rebases).
then replays `mov eax,[0x469420]` and resumes at 0x40C927.  PIC via call/pop delta (TCPCK is rebased).
Runs inside the TE on every client and in autocombat replays -> multiplayer-safe; fast combat: Ooze has 0
strikes there (nothing happens, as vanilla).  Cave 0x43AC40.. (zero-verified).
Backup AoWTCPCK.dll.bak_oozeext (in <game>\backup\).  Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_oozeext"
BASE = 0x400000
G_MAP = 0x469420              # ^^TAoWCombatMap (pointer to the global var) ; [[[G_MAP]]+0x10] = map container
GETMAPLEVEL = 0x401E64        # thunk HSEngine.TMapContainer.GetMapLevel(eax=container, edx=idx)
GETFIELD = 0x401E54           # thunk HSEngine.TMapLevel.GetField(eax=level, edx=x, ecx=y)
TOBJ_FREE = 0x401050          # thunk System.TObject.Free(eax)
SLOT_SETUNIT = 0x46E858       # import slot: AoWE.TCombatUnit.SetUnit (0x55725194 static)
EP_SETUNIT, EP_REMOVEABILITY = 0x55725194, 0x5577F6EC   # AoWE.TAbstractUnit.RemoveAbility(eax=unit, edx=id)
CID_FIRE, CID_UNITHS = 0x22054A, 0x220104
AB_BURNING = 0x7F
HOOK_VA = 0x40C922
HOOK_ORIG = bytes.fromhex("a120944600")   # mov eax,[0x469420]
RESUME = 0x40C927
CAVE_BASE, CAVE_END = 0x43AC40, 0x43AD40
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    src = chr(10).join(l.split(';')[0] for l in src.splitlines())
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_main(va):
    body = f"""
        mov eax, [ebx+{G_MAP:#x}]
        mov eax, [eax]                    ; 0x469420 -> ^TAoWCombatMap variable -> object
        mov eax, [eax+0x10]
        xor edx, edx
        call {GETMAPLEVEL:#x}
        test eax, eax
        jz o_done
        mov edx, [ebp-0x28]
        mov ecx, [ebp-0x2C]
        call {GETFIELD:#x}
        test eax, eax
        jz o_done
        mov esi, eax
        mov edi, 8
    o_fire:
        mov eax, esi
        mov edx, {CID_FIRE:#x}
        mov ecx, [eax]
        call [ecx+0x80]
        test eax, eax
        jz o_unit
        call {TOBJ_FREE:#x}
        dec edi
        jnz o_fire
    o_unit:
        mov eax, esi
        mov edx, {CID_UNITHS:#x}
        mov ecx, [eax]
        call [ecx+0x80]
        test eax, eax
        jz o_done
        mov eax, [eax+0x1C]
        test eax, eax
        jz o_done
        mov esi, eax
        mov edx, {AB_BURNING:#x}
        mov ecx, [eax]
        call [ecx+0xA8]
        test al, al
        jz o_done
        mov eax, [esi+0x4C]
        test eax, eax
        jz o_done
        mov edx, {AB_BURNING:#x}
        mov ecx, [ebx+{SLOT_SETUNIT:#x}]
        add ecx, {EP_REMOVEABILITY - EP_SETUNIT:#x}
        call ecx
    o_done:
        mov eax, [ebx+{G_MAP:#x}]
        mov [esp+0x1C], eax
        popad
        jmp {RESUME:#x}
    """
    p = asm("pushad", va)
    call_at = va + len(p); nxt = call_at + 5
    p += asm(f"call {nxt:#x}", call_at)
    p += asm(f"pop ebx\nsub ebx, {nxt:#x}\n" + body, nxt)
    return p


def build():
    blob = cave_main(CAVE_BASE)
    assert CAVE_BASE + len(blob) <= CAVE_END, hex(CAVE_BASE + len(blob))
    return [(CAVE_BASE, blob, "ooze-extinguish")]


def va2off(pe_bytes, va):
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    nsec = struct.unpack_from("<H", pe_bytes, e_lfanew + 6)[0]
    opt = struct.unpack_from("<H", pe_bytes, e_lfanew + 20)[0]
    sec = e_lfanew + 24 + opt
    for i in range(nsec):
        s = sec + 40 * i
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", pe_bytes, s + 8)
        if rva <= va - BASE < rva + max(vsz, rsz):
            return roff + (va - BASE - rva)
    raise ValueError(f"VA {va:#x} not in any section")


def reloc_entries(pe_bytes, ranges):
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    dd_rva, dd_sz = struct.unpack_from("<II", pe_bytes, e_lfanew + 24 + 0x88)
    if not dd_sz:
        return []
    off = va2off(pe_bytes, BASE + dd_rva); end = off + dd_sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", pe_bytes, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            eo = off + 8 + 2 * i; e = struct.unpack_from("<H", pe_bytes, eo)[0]
            va = BASE + page + (e & 0xFFF)
            if any(lo <= va < hi for lo, hi in ranges):
                hits.append((eo, va, e >> 12))
        off += bsz
    return hits


def jmp_bytes(src, dst, ln):
    return b"\xe9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (ln - 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    bak = bak_path(dll, BAK, create=a.apply)
    caves = build()
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, blob, name in caves:
            print(f"\n; ---- {name} @{va:#x} ({len(blob)} B) ----")
            for ins in md.disasm(blob, va):
                print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, dll); print(f"reverted {dll} from {bak}"); return
    data = bytearray(open(dll, "rb").read())
    ho = va2off(data, HOOK_VA); cur = bytes(data[ho:ho + len(HOOK_ORIG)])
    applied = cur[0] == 0xE9 and HOOK_VA + 5 + struct.unpack_from("<i", cur, 1)[0] == CAVE_BASE
    vanilla = cur == HOOK_ORIG
    print(f"target: {dll}\n  hook 0x{HOOK_VA:x}: {'ALREADY PATCHED' if applied else 'vanilla' if vanilla else 'UNKNOWN BYTES ' + cur.hex()}")
    for va, blob, name in caves:
        print(f"  cave {name} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_BASE), va2off(data, CAVE_END)
    zone_zero = all(v == 0 for v in data[z0:z1])
    rl_hook = reloc_entries(data, [(HOOK_VA, HOOK_VA + len(HOOK_ORIG))])
    rl_cave = reloc_entries(data, [(CAVE_BASE, CAVE_END)])
    print(f"  cave zone zero: {zone_zero}; hook relocs: {[(hex(v), t) for _, v, t in rl_hook] or 'none'} (type 3 -> neutralised on apply); cave relocs: {[hex(v) for _, v, _ in rl_cave] or 'none'}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl_cave or any(t not in (0, 3) for _, _, t in rl_hook):
        sys.exit("unexpected relocs - refusing")
    if applied:
        print("already applied - rewriting cave in place")
    elif not vanilla:
        sys.exit("hook-site bytes are neither vanilla nor ours - refusing")
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    for eo, v, t in rl_hook:
        if t == 3:
            e = struct.unpack_from("<H", data, eo)[0]; struct.pack_into("<H", data, eo, e & 0x0FFF); print(f"  reloc {v:#x} neutralised")
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    data[ho:ho + len(HOOK_ORIG)] = jmp_bytes(HOOK_VA, CAVE_BASE, len(HOOK_ORIG))
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
