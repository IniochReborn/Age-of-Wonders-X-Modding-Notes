#!/usr/bin/env python3
r"""
Tactical AI: stop focusing harmless wall crushers (rams / drills) once the wall is breached
(AoWTCPCK.dll, 2026-09-20).  RE trail: memory aowx-ai-ram-focus.

Why the AI hunts rams: a combat object's target value (TCombatUnit.GetTargetStrength, VMT+0x5C,
cached in [obj+0x40]) is the AVERAGE of its damage value against every opposing object, filled once
at combat start by TCombatObject.SetupTargets into the TQuadItemList at [obj+0x10]
(entries 16 B: +0 target object, +4 CV, +8 wall CV, +0xC unit DV).  For the attacker that list
includes the TCombatWall sections.  TWallCrushingAbility.tcGetDamageValueEx returns 0 against
TCombatUnit targets and > 0 against walls, so a ram's whole value is wall potential, frozen at
combat start.  Rams never retaliate, so hitting one scores as pure gain -- before AND after the
breach.  (Wall Crushing alone is no test: Giants, Elementals, Ents, Karagh ... carry it too.)

Patch: one 8-byte hook at 0x413673 inside TCAI.tcDVtoDEV (the value combiner every melee / ranged /
touch evaluation goes through; [ebp+8] = TARGET, [ebp+0xC] = SELF, [ebp-4] = cai), replacing
    mov eax,[ebp+8] ; mov edx,[eax] ; call [edx+0x5C]      (target value fetch)
with a PIC cave that fetches the value and then, when ALL of
    * the walls are breached  ([[[combatmap]+0xE4]+0xC]+0x4D, set by TCombatWall.DestroyObject),
    * the target is a TCombatUnit on the other side (friendly touch/heal evaluations untouched),
    * the target has Wall Crushing (0x75),
    * the target is harmless to units: no entry of its own target list whose object is a
      TCombatUnit has unit DV > 0  (the game's own numbers -- rams, drills, transports; a future
      melee unit reusing one of their ids gets a unit DV and is automatically excluded),
rewrites the value to  value * RAM_VALUE_PCT / 100.  Negative = "attack it last": phase 4 sorts
moves by value without dropping negatives, so a lone ram is still killed when nothing else is
proposed.  Before the breach nothing changes (defenders keep prioritising rams at the wall).

Coexists with build_hero_melee_courage (imm8 edits at 0x413718/0x41373B), patch_ai_melee_vs_ranged
(calls 0x413664 from its cave) and patch_heal_ai_tcpck (same) -- none of their bytes are touched.
Cave 0x43A100.. (zero-verified).  Backup AoWTCPCK.dll.bak_ramfocus (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path   # game folder = AOW_GAME_DIR or parent of patch scripts
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_ramfocus"
BASE = 0x400000

# ---- tunable --------------------------------------------------------------------------------------
RAM_VALUE_PCT = -100   # harmless crusher's value after the breach, % of vanilla (-100 = minus its value,
                       # 0 = worthless but neutral, 100 = vanilla behaviour)

# ---- engine facts ---------------------------------------------------------------------------------
ISCLASS = 0x401058        # thunk System.@IsClass(eax=obj, edx=class) -> al
GETSIDE = 0x40252C        # thunk AoWE.TCombatObject.GetSide(eax=obj) -> al (0 attacker, 1 defender, 2 none)
IAT_TCUNIT = 0x46E904     # import slot holding the TCombatUnit class pointer
G_COMBATMAP = 0x46C064    # AoWTC combat map global; +0xE4 TCombat, ->+0xC TCombatData (+0x4C walls, +0x4D breached)
WALL_CRUSHING = 0x75
HOOK_VA = 0x413673
HOOK_ORIG = bytes.fromhex("8b45088b10ff525c")   # mov eax,[ebp+8]; mov edx,[eax]; call [edx+0x5c]
RESUME_VA = 0x41367B                             # mov [ebp-0x14], eax
CAVE_BASE, CAVE_END = 0x43A100, 0x43A300

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def asm_pic(va, pre, body):
    """pre ; call next ; next: pop ebx ; sub ebx, next ; body   -> ebx = load delta (module may rebase)."""
    p = asm(pre, va) if pre.strip() else b""
    call_at = va + len(p)
    next_va = call_at + 5
    p += asm(f"call {next_va:#x}", call_at)
    p += asm(f"pop ebx\nsub ebx, {next_va:#x}\n" + body, next_va)
    return p


def cave_main(va):
    pre = """
        mov eax, [ebp+8]
        mov edx, [eax]
        call [edx+0x5C]
        push ebx
        push esi
        push edi
        push eax
    """
    body = f"""
        mov eax, [ebx+{G_COMBATMAP:#x}]
        test eax, eax
        jz r_done
        mov eax, [eax+0xE4]
        test eax, eax
        jz r_done
        mov eax, [eax+0xC]
        test eax, eax
        jz r_done
        cmp byte ptr [eax+0x4D], 0
        je r_done
        mov eax, [ebp+8]
        mov edx, [ebx+{IAT_TCUNIT:#x}]
        call {ISCLASS:#x}
        test al, al
        jz r_done
        mov eax, [ebp+8]
        call {GETSIDE:#x}
        movzx esi, al
        mov eax, [ebp+0xC]
        call {GETSIDE:#x}
        movzx eax, al
        cmp eax, esi
        je r_done
        mov edx, {WALL_CRUSHING:#x}
        mov eax, [ebp+8]
        mov ecx, [eax]
        call [ecx+0xA8]
        test al, al
        jz r_done
        mov esi, [ebp+8]
        mov esi, [esi+0x10]
        test esi, esi
        jz r_done
        mov edi, [esi+8]
        mov esi, [esi+4]
    r_loop:
        dec edi
        js r_harmless
        mov ecx, edi
        shl ecx, 4
        cmp dword ptr [esi+ecx+0xC], 0
        jle r_loop
        mov eax, [esi+ecx]
        test eax, eax
        jz r_loop
        mov edx, [ebx+{IAT_TCUNIT:#x}]
        call {ISCLASS:#x}
        test al, al
        jz r_loop
        jmp r_done
    r_harmless:
        mov eax, [esp]
        imul eax, eax, {RAM_VALUE_PCT}
        cdq
        mov ecx, 0x64
        idiv ecx
        mov [esp], eax
    r_done:
        pop eax
        pop edi
        pop esi
        pop ebx
        jmp {RESUME_VA:#x}
    """
    return asm_pic(va, pre, body)


def build():
    blob = cave_main(CAVE_BASE)
    assert CAVE_BASE + len(blob) <= CAVE_END, f"cave overflow: {CAVE_BASE + len(blob):#x}"
    return [(CAVE_BASE, blob, "ramfocus")]


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


def reloc_hits(pe_bytes, ranges):
    """VAs of base-relocation entries that fall inside any (lo, hi) range."""
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    opt = e_lfanew + 24
    dd_rva, dd_sz = struct.unpack_from("<II", pe_bytes, opt + 0x88)   # IMAGE_DIRECTORY_ENTRY_BASERELOC
    if not dd_sz:
        return []
    off = va2off(pe_bytes, BASE + dd_rva)
    end = off + dd_sz
    hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", pe_bytes, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            e = struct.unpack_from("<H", pe_bytes, off + 8 + 2 * i)[0]
            if e >> 12 == 0:
                continue
            va = BASE + page + (e & 0xFFF)
            if any(lo <= va < hi for lo, hi in ranges):
                hits.append(va)
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
        shutil.copy2(bak, dll)
        print(f"reverted {dll} from {bak}")
        return

    data = bytearray(open(dll, "rb").read())
    ho = va2off(data, HOOK_VA)
    cur = bytes(data[ho:ho + len(HOOK_ORIG)])
    applied = cur[0] == 0xE9
    vanilla = cur == HOOK_ORIG
    print(f"target: {dll}\n  hook 0x{HOOK_VA:x}: {'ALREADY PATCHED' if applied else 'vanilla' if vanilla else 'UNKNOWN BYTES ' + cur.hex()}")
    for va, blob, name in caves:
        print(f"  cave {name} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_BASE), va2off(data, CAVE_END)
    zone_zero = all(b == 0 for b in data[z0:z1])
    print(f"  cave zone zero: {zone_zero}")
    rl = reloc_hits(data, [(HOOK_VA, HOOK_VA + len(HOOK_ORIG)), (CAVE_BASE, CAVE_END)])
    print(f"  reloc entries in hook/cave ranges: {[hex(v) for v in rl] or 'none'}")
    print(f"  harmless-crusher value after breach: {RAM_VALUE_PCT} % of vanilla")
    if not a.apply:
        print("dry run - nothing written (use --apply)")
        return
    if rl:
        sys.exit("relocation entries intersect the patch - refusing")
    if applied:
        print("already applied - rewriting cave in place (hook unchanged)")
    elif not vanilla:
        sys.exit("hook-site bytes are neither vanilla nor ours - refusing")
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak)
        print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va)
        data[o:o + len(blob)] = blob
    data[ho:ho + len(HOOK_ORIG)] = jmp_bytes(HOOK_VA, CAVE_BASE, len(HOOK_ORIG))
    with open(dll, "r+b") as f:          # same-size in-place write (see aowx-project-overview: 'wb' flakes)
        f.seek(0)
        f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
