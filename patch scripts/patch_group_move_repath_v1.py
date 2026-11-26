#!/usr/bin/env python3
r"""
Tactical group move (box-select + click): re-path every unit in execution order (AoWTCPCK.dll, 2026-09-21).
v2: the hover PREVIEW uses the same re-path (without reordering the list), so what you see is what executes.

Vanilla (TCombatUnitSelectionControl / CombatTE.SetupMultiTCUnitMove / AoWE.TMultiMoveTE):
  * while hovering, each selected unit's path is computed by CalculateMovePath (VMT+8 of the selection
    control) with temporary TMovementHS markers: BLOCKING on the destination of every other selected unit
    that already has a path, PASSABLE on their origin (paths are stored destination-first: node 0 = dest,
    last node = origin; a passable marker makes a same-side unit's hex walkable);
  * on the click, SetupMultiTCUnitMove validates the stored paths (CalculateMovePositions), bubble-sorts
    the units by path length, creates one TMoveTE per unit WITH THE FROZEN PATH and TMultiMoveTE executes
    them one after another -- nothing is re-pathed.
So the paths only know about units that happened to be computed earlier, the execution order is a
different one, and units walk into group members that have not moved yet, detour around ones that are
about to leave, and whole moves are refused because frozen paths collide with each other.

Core (cave sub, eax = selection control, edx = 1 reorder the list / 0 leave it):
  1. read every unit's hover destination (path node 0) and hover path length;
  2. choose the execution order: repeatedly take the unit with the FEWEST waiting units standing on a
     shortest line between its origin and its destination (dist(o_i,o_j)+dist(o_j,d_i) == dist(o_i,d_i),
     dHXtoRad), ties broken by hover path length (v3, 2026-09-21: v2's "destination is someone's origin"
     rule only covered moves of exactly one row depth);
  3. clear all paths, then call the vanilla CalculateMovePath for each unit IN THAT ORDER with its saved
     destination, so the marker logic sees exactly the units that will already have moved (destination
     blocked, origin free) and the units still standing (real obstacles).  With edx = 1 the settings
     list is physically reordered as it goes (TList.Exchange on [wrapper+8]) so the token order matches.
Hooks:
  A 0x41E7F7  ExecuteMoveSelection, `jmp exit` right after the hover formation loop -> core(0) -> exit.
  B 0x41E2B0  MoveUnits `call SetupMultiTCUnitMove` -> core(1) -> SetupMultiTCUnitMove.  Its bubble sort
              is neutralised (0x40F81C `jle` -> `jmp`).
Paths are fixed before the tokens are created and travel inside them -> multiplayer-safe.
Groups larger than 64 units fall back to vanilla.  PIC (call/pop delta for the combat-map global).
Cave 0x43A600.. (zero-verified).  Backup AoWTCPCK.dll.bak_grouprepath (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_grouprepath"
BASE = 0x400000
MAXN = 64

G_COMBATMAP = 0x46C064          # [map+0x88] = current level (as the hover code passes it)
GETMS = 0x40275C                # thunk AoWE.TMoveSettingsList.GetMoveSettings(eax=wrapper, edx=idx) -> ms
LIST_EXCHANGE = 0x401534        # thunk Classes.TList.Exchange(eax=TList, edx=i, ecx=j); the TList is [wrapper+8]
XYL_GET = 0x401B1C              # thunk HSEngine.TXYLList.Get(eax=list, edx=idx) -> x | y<<8 | ...
XYL_CLEAR = 0x401B0C            # thunk HSEngine.TXYLList.Clear(eax=list)
SETUP_MULTI = 0x40F788          # CombatTE.SetupMultiTCUnitMove(eax=wrapper) -> al
DHX = 0x4022A4                  # thunk HSEngine.dHXtoRad(eax=x1, edx=y1, ecx=x2, push y2) -> hex distance (ret 4)
HA = ("preview", 0x41E7F7, bytes.fromhex("e9dd050000"), 0x41EDD9)   # jmp 0x41EDD9 (routine exit)
HB = ("click", 0x41E2B0, bytes.fromhex("e8d314ffff"), 0x41E2B5)     # call 0x40F788
SORT_VA = 0x40F81C
SORT_ORIG, SORT_NEW = bytes.fromhex("7e6b"), bytes.fromhex("eb6b")
CAVE_BASE, CAVE_END = 0x43A600, 0x43AC00
TAKEN = -2

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_core(va):
    # frame (own ebp): -4 n, -8 k, -0xC i, -0x10 best, -0x14 bestlen, -0x18 j, -0x1C flag, -0x20 level,
    # -0x24 sel, -0x28 wrapper, -0x2C unused, -0x30 p, -0x34 D, -0x38 inway, -0x3C oi, -0x40 di, -0x44 lenkey, -0x48 oj, -0x4C t ; arrays of 64 dwords:
    # DEST -0x150, LEN -0x250, ORDER -0x350, CUR -0x450 (locals end at -0x4C)
    FR = 0x450
    DEST, LEN, ORDER, CUR = "-0x150", "-0x250", "-0x350", "-0x450"
    pre = f"""
        push ebp
        mov ebp, esp
        sub esp, {FR:#x}
        push ebx
        push esi
        push edi
        mov esi, eax
        mov [ebp-0x24], eax
        mov [ebp-0x1C], edx
        mov edi, [eax+8]
        mov [ebp-0x28], edi
    """
    body = f"""
        mov eax, edi
        mov edx, [eax]
        call [edx+0x54]
        mov [ebp-4], eax
        cmp eax, 2
        jl c_done
        cmp eax, {MAXN}
        jg c_done
        mov eax, [ebx+{G_COMBATMAP:#x}]
        mov eax, [eax+0x88]
        mov [ebp-0x20], eax
        mov dword ptr [ebp-0xC], 0
    c_fill:
        mov eax, [ebp-0xC]
        cmp eax, [ebp-4]
        jge c_fill_end
        mov [ebp+eax*4{CUR}], eax
        mov edx, eax
        mov eax, edi
        call {GETMS:#x}
        mov eax, [eax+8]
        mov ecx, [eax+8]
        mov edx, [ebp-0xC]
        mov [ebp+edx*4{LEN}], ecx
        mov dword ptr [ebp+edx*4{DEST}], -1
        test ecx, ecx
        jle c_fill_next
        xor edx, edx
        call {XYL_GET:#x}
        and eax, 0xFFFF
        mov edx, [ebp-0xC]
        mov [ebp+edx*4{DEST}], eax
    c_fill_next:
        inc dword ptr [ebp-0xC]
        jmp c_fill
    c_fill_end:
        mov dword ptr [ebp-8], 0
    c_order:
        mov eax, [ebp-8]
        cmp eax, [ebp-4]
        jge c_order_end
        mov dword ptr [ebp-0x10], -1
        mov dword ptr [ebp-0x14], 0x7FFFFFFF
        mov dword ptr [ebp-0xC], 0
    c_cand:
        mov eax, [ebp-0xC]
        cmp eax, [ebp-4]
        jge c_cand_end
        mov ecx, [ebp+eax*4{LEN}]
        cmp ecx, {TAKEN}
        je c_cand_next
        test ecx, ecx
        jg c_len_ok
        mov ecx, 0xFFF
    c_len_ok:
        cmp ecx, 0xFFF
        jle c_len_capped
        mov ecx, 0xFFF
    c_len_capped:
        mov [ebp-0x44], ecx
        mov ecx, [ebp+eax*4{DEST}]
        cmp ecx, -1
        jne c_has_dest
        mov ecx, 0x7FFFFFFE
        jmp c_key_ready
    c_has_dest:
        mov [ebp-0x40], ecx
        mov edx, eax
        call c_origin
        mov [ebp-0x3C], eax
        mov edx, [ebp-0x40]
        call c_dist
        mov [ebp-0x34], eax
        mov dword ptr [ebp-0x38], 0
        mov dword ptr [ebp-0x18], 0
    c_way:
        mov eax, [ebp-0x18]
        cmp eax, [ebp-4]
        jge c_way_end
        cmp eax, [ebp-0xC]
        je c_way_next
        cmp dword ptr [ebp+eax*4{LEN}], {TAKEN}
        je c_way_next
        mov edx, eax
        call c_origin
        mov [ebp-0x48], eax
        mov edx, eax
        mov eax, [ebp-0x3C]
        call c_dist
        mov [ebp-0x4C], eax
        mov eax, [ebp-0x48]
        mov edx, [ebp-0x40]
        call c_dist
        add eax, [ebp-0x4C]
        cmp eax, [ebp-0x34]
        jne c_way_next
        inc dword ptr [ebp-0x38]
    c_way_next:
        inc dword ptr [ebp-0x18]
        jmp c_way
    c_way_end:
        mov ecx, [ebp-0x38]
        shl ecx, 12
        or ecx, [ebp-0x44]
    c_key_ready:
        cmp ecx, [ebp-0x14]
        jge c_cand_next
        mov eax, [ebp-0xC]
        mov [ebp-0x10], eax
        mov [ebp-0x14], ecx
    c_cand_next:
        inc dword ptr [ebp-0xC]
        jmp c_cand
    c_cand_end:
        cmp dword ptr [ebp-0x10], -1
        je c_order_end
        mov ecx, [ebp-0x10]
        mov edx, [ebp-8]
        mov [ebp+edx*4{ORDER}], ecx
        mov dword ptr [ebp+ecx*4{LEN}], {TAKEN}
        inc dword ptr [ebp-8]
        jmp c_order
    c_order_end:
        mov dword ptr [ebp-0xC], 0
    c_clear:
        mov eax, [ebp-0xC]
        cmp eax, [ebp-4]
        jge c_clear_end
        mov edx, eax
        mov eax, edi
        call {GETMS:#x}
        mov eax, [eax+8]
        call {XYL_CLEAR:#x}
        inc dword ptr [ebp-0xC]
        jmp c_clear
    c_clear_end:
        mov dword ptr [ebp-8], 0
    c_repath:
        mov eax, [ebp-8]
        cmp eax, [ebp-4]
        jge c_done
        mov ecx, [ebp+eax*4{ORDER}]
        mov [ebp-0x30], ecx
        cmp dword ptr [ebp-0x1C], 0
        je c_pos_ready
        mov dword ptr [ebp-0xC], 0
    c_findpos:
        mov eax, [ebp-0xC]
        cmp eax, [ebp-4]
        jge c_pos_ready
        mov edx, [ebp+eax*4{CUR}]
        cmp edx, [ebp-0x30]
        je c_found
        inc dword ptr [ebp-0xC]
        jmp c_findpos
    c_found:
        mov ecx, [ebp-8]
        cmp eax, ecx
        je c_swapped
        mov edx, [ebp+ecx*4{CUR}]
        mov [ebp+eax*4{CUR}], edx
        mov edx, [ebp-0x30]
        mov [ebp+ecx*4{CUR}], edx
        mov edx, ecx
        mov ecx, eax
        mov eax, [edi+8]
        call {LIST_EXCHANGE:#x}
    c_swapped:
        mov eax, [ebp-8]
        mov [ebp-0x30], eax
    c_pos_ready:
        mov eax, [ebp-8]
        mov ecx, [ebp+eax*4{ORDER}]
        mov ecx, [ebp+ecx*4{DEST}]
        cmp ecx, -1
        je c_repath_next
        mov edx, ecx
        shr edx, 8
        and edx, 0xFF
        push edx
        push dword ptr [ebp-0x20]
        and ecx, 0xFF
        mov edx, [ebp-0x30]
        mov eax, esi
        mov ebx, [eax]
        call [ebx+8]
    c_repath_next:
        inc dword ptr [ebp-8]
        jmp c_repath
    c_done:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    c_origin:
        mov eax, edi
        call {GETMS:#x}
        mov eax, [eax+0x10]
        mov eax, [eax+4]
        movzx edx, byte ptr [eax+0x11]
        shl edx, 8
        movzx eax, byte ptr [eax+0x10]
        or eax, edx
        ret
    c_dist:
        push ebx
        mov ebx, edx
        movzx ecx, bh
        push ecx
        movzx ecx, bl
        movzx edx, ah
        movzx eax, al
        call {DHX:#x}
        pop ebx
        ret
    """
    p = asm(pre, va)
    call_at = va + len(p); nxt = call_at + 5
    p += asm(f"call {nxt:#x}", call_at)
    p += asm(f"pop ebx\nsub ebx, {nxt:#x}\n" + body, nxt)
    return p


def cave_hook_preview(va, core):
    return asm(f"""
        mov eax, [ebp-4]
        xor edx, edx
        call {core:#x}
        jmp {HA[3]:#x}
    """, va)


def cave_hook_click(va, core):
    return asm(f"""
        mov eax, [ebp-4]
        mov edx, 1
        call {core:#x}
        mov eax, [ebp-4]
        mov eax, [eax+8]
        call {SETUP_MULTI:#x}
        jmp {HB[3]:#x}
    """, va)


def build():
    caves, cur = [], CAVE_BASE
    core = cave_core(cur); caves.append((cur, core, "core")); core_va = cur
    cur = (cur + len(core) + 15) & ~15
    a = cave_hook_preview(cur, core_va); caves.append((cur, a, "preview")); tgt = {"preview": cur}
    cur = (cur + len(a) + 15) & ~15
    b = cave_hook_click(cur, core_va); caves.append((cur, b, "click")); tgt["click"] = cur
    cur = (cur + len(b) + 15) & ~15
    assert cur <= CAVE_END, hex(cur)
    return caves, tgt


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
    caves, tgt = build()
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
    hooks = [HA, HB]
    state = []
    for name, va, orig, _ in hooks:
        cur = bytes(data[va2off(data, va):va2off(data, va) + len(orig)])
        state.append("patched" if cur[0] == 0xE9 and cur != orig else "vanilla" if cur == orig else f"UNKNOWN {cur.hex()}")
    so = va2off(data, SORT_VA); cur_s = bytes(data[so:so + 2])
    state.append("patched" if cur_s == SORT_NEW else "vanilla" if cur_s == SORT_ORIG else f"UNKNOWN {cur_s.hex()}")
    print(f"target: {dll}\n  preview hook {state[0]}, click hook {state[1]}, sort {state[2]}")
    for va, blob, name in caves:
        print(f"  cave {name:8} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_BASE), va2off(data, CAVE_END)
    zone_zero = all(v == 0 for v in data[z0:z1])
    rl = reloc_hits(data, [(h[1], h[1] + len(h[2])) for h in hooks] + [(SORT_VA, SORT_VA + 2), (CAVE_BASE, CAVE_END)])
    print(f"  cave zone zero: {zone_zero}; relocs: {[hex(v) for v in rl] or 'none'}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl or any(s.startswith("UNKNOWN") for s in state):
        sys.exit("refusing: relocs or unexpected bytes")
    fresh = all(s == "vanilla" for s in state)
    if not fresh:
        print("rewriting caves in place (earlier build present)")
    if fresh and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    data[z0:z1] = b"\0" * (z1 - z0)
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    for name, va, orig, _ in hooks:
        o = va2off(data, va); data[o:o + len(orig)] = jmp_bytes(va, tgt[name], len(orig))
    data[so:so + 2] = SORT_NEW
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
