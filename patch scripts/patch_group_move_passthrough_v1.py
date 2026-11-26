#!/usr/bin/env python3
r"""
Tactical group move: friends that are leaving can be walked THROUGH, reserved destinations cannot
(AoWTCPCK.dll, 2026-09-21).  Companion of patch_group_move_repath_v1.py.

Diagnosis (live group probe, 3-hex advance of a two-row formation): the re-path order was right, but every
rear unit detoured around the hex of a front unit that had already been processed.  Cause, in the engine:
  * the pathfinder's transit test is TMapField.CanMoveOver 0x556081AC (HSEPack) -> each object's virtual
    CanMoveOver (VMT+0xD4); a unit's is TUnitHS.CanMoveOver 0x55784220 (AoWEPACK): passable only when the
    object's layer byte (ctx+8) is non-zero, i.e. flying -- it never looks at the TMovementHS marker;
  * the marker is only honoured by CanMoveOn (VMT+0xD0, end-of-move validity): TTacticalCombatUnitHS.CanMoveOn
    0x42079C lets a same-side mover END on the hex when a flag-1 marker sits there.  That is why "2 hexes
    forward" (rear destination = front origin) worked and "3 hexes forward" (rear must pass through) did not;
  * conversely TMovementHS inherits THexagonSprite.CanMoveOver (always 1), so a flag-0 marker (someone's
    reserved DESTINATION) blocks ending there but not passing through -- a path may cross a hex that will be
    occupied by the time the unit walks it.
Patch (two VMT slot redirects in TCPCK's own tables; their .reloc entries stay valid because the slots still
hold module-absolute pointers):
  A  TTacticalCombatUnitHS VMT+0xD4 (0x412DDC, was thunk 0x402A94 -> TUnitHS.CanMoveOver) -> cave: if the field
     (ctx+4) holds a TMovementHS (VMT 0x431140, PIC compare) on its OWN hex (field layer byte == 0; hex sprites
     register a footprint on neighbouring fields with layer 1..6) with flag [+0xC] != 0 -> passable (1); else the
     vanilla rule (layer byte ctx+8 != 0).
  B  TMovementHS VMT+0xD4 (0x431214, was thunk 0x401B5C -> THexagonSprite.CanMoveOver) -> cave: on the marker's own
     hex (ctx+8 == 0) with flag 0 (reserved destination) -> blocked (0); anything else -> passable (1).
     (v1 ignored the layer byte and walled off neighbours of every reserved destination -> detours, 2026-09-21.)
Markers exist only while the local player's group-move code computes paths, so nothing else changes.
Cave 0x43AA00.. (zero-verified).  Backup AoWTCPCK.dll.bak_grouppass (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_grouppass"
BASE = 0x400000
MARKER_VMT = 0x431140
SLOT_UNIT = (0x412DDC, 0x402A94)      # TTacticalCombatUnitHS VMT+0xD4, vanilla value
SLOT_MARKER = (0x431214, 0x401B5C)    # TMovementHS VMT+0xD4, vanilla value
CAVE_BASE, CAVE_END = 0x43AA00, 0x43AB00
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_unit(va):
    pre = """
        push ebx
        push esi
        push edi
        mov edi, edx
    """
    body = f"""
        lea ebx, [ebx+{MARKER_VMT:#x}]
        mov esi, [edi+4]
        movzx ecx, byte ptr [esi+0xD]
        movzx eax, byte ptr [esi+0xC]
        mov esi, [esi+8]
        lea eax, [esi+eax*4]
        push eax
    u_loop:
        dec ecx
        js u_vanilla
        mov edx, [esi+ecx*4]
        test edx, edx
        jz u_loop
        cmp [edx], ebx
        jne u_loop
        mov eax, [esp]
        cmp byte ptr [eax+ecx], 0
        jne u_loop
        cmp byte ptr [edx+0xC], 0
        je u_loop
        pop eax
        mov eax, 1
        jmp u_ret
    u_vanilla:
        pop eax
        xor eax, eax
        cmp byte ptr [edi+8], 0
        setne al
    u_ret:
        pop edi
        pop esi
        pop ebx
        ret
    """
    p = asm(pre, va)
    call_at = va + len(p); nxt = call_at + 5
    p += asm(f"call {nxt:#x}", call_at)
    p += asm(f"pop ebx\nsub ebx, {nxt:#x}\n" + body, nxt)
    return p


def cave_marker(va):
    return asm("""
        cmp byte ptr [edx+8], 0
        jne m_pass
        cmp byte ptr [eax+0xC], 0
        je m_block
    m_pass:
        mov eax, 1
        ret
    m_block:
        xor eax, eax
        ret
    """, va)


def build():
    caves, cur = [], CAVE_BASE
    a = cave_unit(cur); caves.append((cur, a, "unit-canmoveover")); ua = cur
    cur = (cur + len(a) + 15) & ~15
    b = cave_marker(cur); caves.append((cur, b, "marker-canmoveover")); mb = cur
    cur = (cur + len(b) + 15) & ~15
    assert cur <= CAVE_END
    return caves, ua, mb


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
            e = struct.unpack_from("<H", pe_bytes, off + 8 + 2 * i)[0]
            if e >> 12:
                va = BASE + page + (e & 0xFFF)
                if any(lo <= va < hi for lo, hi in ranges):
                    hits.append(va)
        off += bsz
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    bak = bak_path(dll, BAK, create=a.apply)
    caves, ua, mb = build()
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
    su = struct.unpack_from("<I", data, va2off(data, SLOT_UNIT[0]))[0]
    sm = struct.unpack_from("<I", data, va2off(data, SLOT_MARKER[0]))[0]
    st_u = "vanilla" if su == SLOT_UNIT[1] else "patched" if CAVE_BASE <= su < CAVE_END else f"UNKNOWN {su:#x}"
    st_m = "vanilla" if sm == SLOT_MARKER[1] else "patched" if CAVE_BASE <= sm < CAVE_END else f"UNKNOWN {sm:#x}"
    print(f"target: {dll}\n  unit slot 0x{SLOT_UNIT[0]:x}: {st_u}; marker slot 0x{SLOT_MARKER[0]:x}: {st_m}")
    for va, blob, name in caves:
        print(f"  cave {name:18} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_BASE), va2off(data, CAVE_END)
    zone_zero = all(v == 0 for v in data[z0:z1])
    slot_relocs = reloc_hits(data, [(SLOT_UNIT[0], SLOT_UNIT[0] + 4), (SLOT_MARKER[0], SLOT_MARKER[0] + 4)])
    cave_relocs = reloc_hits(data, [(CAVE_BASE, CAVE_END)])
    print(f"  cave zone zero: {zone_zero}; slot relocs (expected, kept): {[hex(v) for v in slot_relocs]}; cave relocs: {cave_relocs or 'none'}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if cave_relocs or len(slot_relocs) != 2 or "UNKNOWN" in st_u + st_m:
        sys.exit("refusing: unexpected relocs or slot values")
    fresh = st_u == "vanilla" and st_m == "vanilla"
    if fresh and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    struct.pack_into("<I", data, va2off(data, SLOT_UNIT[0]), ua)
    struct.pack_into("<I", data, va2off(data, SLOT_MARKER[0]), mb)
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
