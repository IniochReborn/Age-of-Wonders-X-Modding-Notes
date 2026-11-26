#!/usr/bin/env python3
r"""
DIAGNOSTIC: trace every tactical-AI ranged-ability evaluation (AoWTCPCK.dll, 2026-09-20).
Revert before any release cut.  Memory: aowx-ai-hero-idle.

Two hooks inside TCAI.CheckUnit's ranged handler (0x417420..):
  A 0x417458  right after the damage value is stored ([ebp-0x28], 6-byte `jle 0x417FE8`): opens a record
              with self, target, ability id, distance [ebp-0x1C], DV, self moves [+0x5C], move-list count.
  B 0x417FE8  the handler's common exit (5 bytes `xor eax,eax; pop edx; pop ecx; pop ecx`): closes the
              record with DEV [ebp-0x64], [ebp-0x58] (obstruction/search value), [ebp-0x28] (DEV0 or DV),
              band [ebp-0x24], reach distance [ebp-0x34], chosen path index [ebp-0x2C], move-list count.
Ring buffer (header 0x10 + 3000 x 40 B) is LocalAlloc'ed on first use (kernel32!LocalAlloc IAT 0x46DC2C);
the pointer lives in .idata page slack at 0x479EC8 (writable, zero in the file).  `--read` dumps it from
the running game.  Caves 0x43A300.. (zero-verified).  Backup AoWTCPCK.dll.bak_rtrace.
Dry-run default; --apply; --revert; --dis; --read.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_rtrace"
BASE = 0x400000
PTR_SLOT = 0x479EC8          # .idata page slack: heap pointer of the ring
IAT_LOCALALLOC = 0x46DC2C
REC_N, REC_SZ, HDR = 3000, 40, 0x10   # 3000 x 40 B = 120 KB heap ring (was 100)
BUF_SZ = HDR + REC_N * REC_SZ
HA = ("dv", 0x417458, bytes.fromhex("0f8e8a0b0000"), 0x41745E, 0x417FE8)   # jle 0x417FE8
HB = ("exit", 0x417FE8, bytes.fromhex("33c05a5959"), 0x417FED)
CAVE_BASE, CAVE_END = 0x43A300, 0x43A500

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def asm_pic(va, pre, body):
    p = asm(pre, va) if pre.strip() else b""
    call_at = va + len(p); nxt = call_at + 5
    p += asm(f"call {nxt:#x}", call_at)
    p += asm(f"pop ebx\nsub ebx, {nxt:#x}\n" + body, nxt)
    return p


def cave_a(va):
    pre = """
        pushfd
        push eax
        push ecx
        push edx
        push ebx
        push esi
        push edi
    """
    body = f"""
        mov esi, [ebx+{PTR_SLOT:#x}]
        test esi, esi
        jnz a_have
        push {BUF_SZ:#x}
        push 0x40
        call [ebx+{IAT_LOCALALLOC:#x}]
        test eax, eax
        jz a_done
        mov [ebx+{PTR_SLOT:#x}], eax
        mov esi, eax
    a_have:
        mov eax, [esi]
        inc dword ptr [esi]
        xor edx, edx
        mov ecx, {REC_N}
        div ecx
        imul edx, edx, {REC_SZ}
        lea edi, [esi+edx+{HDR:#x}]
        mov [esi+4], edi
        mov eax, [ebp+0x14]
        mov [edi], eax
        mov eax, [ebp+0x10]
        mov [edi+4], eax
        mov eax, [ebp-0x5C]
        mov [edi+8], al
        mov byte ptr [edi+9], 0xFF
        mov eax, [ebp-0x1C]
        mov [edi+0xA], al
        mov byte ptr [edi+0xB], 0xFF
        mov eax, [ebp-0x28]
        mov [edi+0xC], eax
        mov eax, [ebp+0x14]
        mov eax, [eax+0x5C]
        mov [edi+0x10], eax
        mov eax, [ebp-4]
        mov eax, [eax+0x14]
        mov eax, [eax+8]
        mov [edi+0x14], ax
        mov word ptr [edi+0x16], 0xFFFF
        xor eax, eax
        mov [edi+0x18], eax
        mov [edi+0x1C], eax
        mov [edi+0x20], eax
        mov [edi+0x24], eax
    a_done:
        pop edi
        pop esi
        pop ebx
        pop edx
        pop ecx
        pop eax
        popfd
        jle {HA[4]:#x}
        jmp {HA[3]:#x}
    """
    return asm_pic(va, pre, body)


def cave_b(va):
    pre = """
        push eax
        push ebx
        push esi
        push edi
    """
    body = f"""
        mov esi, [ebx+{PTR_SLOT:#x}]
        test esi, esi
        jz b_done
        mov edi, [esi+4]
        test edi, edi
        jz b_done
        mov eax, [ebp+0x14]
        cmp eax, [edi]
        jne b_done
        mov eax, [ebp+0x10]
        cmp eax, [edi+4]
        jne b_done
        mov eax, [ebp-0x24]
        mov [edi+9], al
        mov eax, [ebp-0x34]
        mov [edi+0xB], al
        mov eax, [ebp-0x64]
        mov [edi+0x18], eax
        mov eax, [ebp-0x58]
        mov [edi+0x1C], eax
        mov eax, [ebp-0x28]
        mov [edi+0x20], eax
        mov eax, [ebp-4]
        mov eax, [eax+0x14]
        mov eax, [eax+8]
        mov [edi+0x16], ax
        mov eax, [ebp-0x2C]
        mov [edi+0x24], eax
        mov dword ptr [esi+4], 0
    b_done:
        pop edi
        pop esi
        pop ebx
        pop eax
        xor eax, eax
        pop edx
        pop ecx
        pop ecx
        jmp {HB[3]:#x}
    """
    return asm_pic(va, pre, body)


def build():
    caves, cur = [], CAVE_BASE
    tgt = {}
    for name, fn in (("dv", cave_a), ("exit", cave_b)):
        blob = fn(cur); caves.append((cur, blob, name)); tgt[name] = cur
        cur = (cur + len(blob) + 15) & ~15
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


def read_trace(only_unit=None, only_heroes=False, last=400, ringn=REC_N):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ai_state_probe as P
    pid, mods = P.find_game(); tc = mods.get("aowtcpck.dll")
    if tc is None:
        sys.exit("AoWTCPCK.dll not in process")
    mem = P.Mem(pid)
    buf = mem.u32(tc - BASE + PTR_SLOT)
    print(f"TCPCK base {tc:#x}; ring buffer {buf:#x}")
    if not buf:
        print("no evaluations logged yet"); return
    b = mem.read(buf, HDR + ringn * REC_SZ)
    if b is None:
        sys.exit("could not read the ring (wrong --ringn for the running build?)")
    count = struct.unpack_from("<I", b, 0)[0]; n = min(count, ringn)
    print(f"ranged evaluations logged: {count} (ring keeps {n}; filter unit={only_unit and hex(only_unit)} heroes={only_heroes} last={last})")
    shown = 0
    for r in range(count - n, count):
        o = HDR + (r % ringn) * REC_SZ
        self_, tgt = struct.unpack_from("<II", b, o)
        if only_unit and self_ != only_unit:
            continue
        if only_heroes:
            u = mem.u32(self_ + 0x4C) if self_ else 0
            if not u or mem.classname(u) not in ("THero", "TLeader"):
                continue
        shown += 1
        if shown > last:
            print("  ... (more, raise --last)"); break
        abil, band, dist, reach = b[o + 8], b[o + 9], b[o + 10], b[o + 11]
        dv, devin, cb, ca, devout, v58, dev0, idx = struct.unpack_from("<iiHHiiii", b, o + 0xC)
        closed = ca != 0xFFFF
        print(f"  [{r:3}] {P.describe(mem, self_)} -> {P.describe(mem, tgt)} abil {abil:#x} dist {dist} band {band if band != 255 else '?'} "
              f"DV {dv} moves {devin} | DEV {devout} v58 {v58} dev0 {dev0} reach {reach if reach != 255 else '?'} idx {idx} "
              f"moves-list {cb}->{ca if closed else '?'}{'' if closed else '  (exited before B)'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    ap.add_argument("--read", action="store_true")
    ap.add_argument("--unit", default=None, help="--read: only records whose SELF object is this hex address")
    ap.add_argument("--heroes", action="store_true", help="--read: only THero/TLeader shooters")
    ap.add_argument("--last", type=int, default=400, help="--read: how many of the newest records to show")
    ap.add_argument("--ringn", type=int, default=REC_N, help="--read: ring size of the RUNNING build (100 for the first build)")
    a = ap.parse_args()
    if a.read:
        return read_trace(int(a.unit, 16) if a.unit else None, a.heroes, a.last, a.ringn)
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
    applied = all(data[va2off(data, h[1])] == 0xE9 for h in hooks)
    vanilla = all(bytes(data[va2off(data, h[1]):va2off(data, h[1]) + len(h[2])]) == h[2] for h in hooks)
    print(f"target: {dll}\n  hook sites: {'ALREADY PATCHED' if applied else 'vanilla' if vanilla else 'UNKNOWN BYTES'}")
    for va, blob, name in caves:
        print(f"  cave {name:6} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_BASE), va2off(data, CAVE_END)
    zone_zero = all(v == 0 for v in data[z0:z1])
    po = va2off(data, PTR_SLOT); slot_zero = all(v == 0 for v in data[po:po + 4])
    rl = reloc_hits(data, [(h[1], h[1] + len(h[2])) for h in hooks] + [(CAVE_BASE, CAVE_END), (PTR_SLOT, PTR_SLOT + 4)])
    print(f"  cave zone zero: {zone_zero}; pointer slot zero: {slot_zero}; relocs in patch ranges: {[hex(v) for v in rl] or 'none'}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl or not slot_zero:
        sys.exit("refusing: relocs or pointer slot not free")
    if applied:
        print("already applied - rewriting caves in place")
    elif not vanilla:
        sys.exit("hook-site bytes are neither vanilla nor ours - refusing")
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    for name, va, orig, *_ in hooks:
        o = va2off(data, va); data[o:o + len(orig)] = jmp_bytes(va, tgt[name], len(orig))
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
