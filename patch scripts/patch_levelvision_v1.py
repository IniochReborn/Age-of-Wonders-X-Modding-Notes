#!/usr/bin/env python3
r"""patch_levelvision_v1.py  [--apply | --revert | --test]

MAP LEVEL VISION (user 2026-11-22): editor Map Settings > "Map Level Vision" lists every map level with a
"Night Vision required?" tick.  Default = the existing rule: Firmament (3) and Surface (0) off, every other level on.
This script = storage in the map + the game rules (AoWEPACK.dll).  The editor tab is aowxshot_levelvision.py.

Storage: one dword in the map object, TAoWHSMap +0x480 (InstanceSize 0x480 -> 0x484, zero-filled by NewInstance):
  bit L set = level L is TOGGLED away from the default.  0 = today's behaviour, so old maps and unpatched builds are
  unaffected.  Streamed as tag 0x10064 (4 raw bytes, written only when non-zero; unknown tags are skipped by older
  builds), chained behind the Ban List tag: the ban cave's exit `jmp 0x5577725F` @0x558BA284 -> our rw -> 0x5577725F.
NVREQ (zone+4, PIC): al = level -> ZF=1 when Night Vision is NOT required there; every register preserved.
  required = (level != 0 && level != 3) XOR bit(level) of [[0x558FA040]+0x480]; no map / level > 31 = default.
Rules now asking NVREQ instead of "level == 0 (or 3)":
  V1 TAbstractUnit.VisibilityRange 0x55780F32 (was -> engine_v1's cave 0x55851130): the halved sight without Night Vision.
     The second level test (0x55780F4C, surface-only enemy effect) and the Firmament +3 sight are untouched.
  A1 ranged attack penalty cave 0x5580F247, A2 melee 0x5580F306, A3 hero melee 0x5580F37F (the "underground without
     Night Vision" attack penalties).  Side effect of the default table: the Firmament no longer gives those penalties.
The 5-byte jumps at A1-A3 cut into the next instruction, so each stub replays it (mov al,dl / pop eax, dec al, ret /
  dec byte [esp]).
Not touched: tactical combat sight (TCombatUnit.GetVisibilityRange halves only in exploration-site battles,
  [combat+0x40] == 1, on any level - user: sites always need Night Vision).
v2 (2026-11-22, city names): a SECOND dword, map +0x484 (InstanceSize -> 0x488), tag 0x10065 = editor settings that
  travel with the map (only the editor reads them): bit 0 = "Randomly generate city names" OFF (0 = on, the default),
  bits 8..15 = city name list index (0 = Vanilla AoW).  Same stream rules as the first dword.
LIFO: revert this before patch_banlist_storage_v1 / patch_map_levels_engine_v1 / the night-vision caves are touched.
Zone AoWEPACK 0x558BAE00..0x558BB000 'LVV1'.  Backup backup\AoWEPACK.dll.bak_levelvision.  MP: every player needs it.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, V2F, BASE = game_file("AoWEPACK.dll"), 0x55700C00, 0x55700000
ZONE, ZONE_END, MAGIC = 0x558BAE00, 0x558BB000, b"LVV1"
CODE = ZONE + 4
GLOBAL_MAP, MAP_OFS, TAG = 0x558FA040, 0x480, 0x10064
MAP_OFS2, TAG2, INST_NEW = 0x484, 0x10065, 0x488
RW_BACK = 0x5577725F


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
    nvreq:
        push ecx
        push edx
        push eax
        movzx ecx, al
        xor edx, edx
        test ecx, ecx
        jz nv_m
        cmp ecx, 3
        je nv_m
        inc edx
    nv_m:
        cmp ecx, 31
        ja nv_out
        call nv_d
    nv_d:
        pop eax
        sub eax, nv_d
        mov eax, [eax + {GLOBAL_MAP:#x}]
        test eax, eax
        jz nv_out
        mov eax, [eax + {MAP_OFS:#x}]
        bt eax, ecx
        jnc nv_out
        xor edx, 1
    nv_out:
        test edx, edx
        pop eax
        pop edx
        pop ecx
        ret

    .balign 16
    vis:
        push eax
        mov al, byte ptr [esp + 6]
        call nvreq
        pop eax
        jmp 0x55780F37

    .balign 16
    rngd:
        call nvreq
        je 0x5580F25B
        mov al, dl
        jmp 0x5580F24D

    .balign 16
    melee:
        call nvreq
        je 0x5580F30E
        pop eax
        dec al
        ret

    .balign 16
    hero:
        call nvreq
        je 0x5580F386
        dec byte ptr [esp]
        jmp 0x5580F386

    .balign 16
    rw1:
        push ebp
        mov ebp, ecx
        push edx
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx]
        test al, 1
        jz rw_wr
        test al, 0x70
        jnz rw_do
        mov dword ptr [ebx + ebp], 0
        jmp rw_do
    rw_wr:
        cmp dword ptr [ebx + ebp], 0
        je rw_done
    rw_do:
        push dword ptr [esp]
        lea edx, [ebx + ebp]
        mov ecx, 4
        mov eax, edi
        mov esi, [eax]
        call dword ptr [esi + 0x1c]
    rw_done:
        pop edx
        pop ebp
        ret

    .balign 16
    rw:
        mov ecx, {MAP_OFS:#x}
        mov edx, {TAG:#x}
        call rw1
        mov ecx, {MAP_OFS2:#x}
        mov edx, {TAG2:#x}
        call rw1
        jmp {RW_BACK:#x}
    """
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code = bytes(ks.asm(src, CODE)[0])
    names = ["nvreq", "vis", "rngd", "melee", "hero", "rw"]
    tail = bytes(ks.asm(src + "\n" + "\n".join(".long %s" % n for n in names) + "\n", CODE)[0])[-4 * len(names):]
    lab = dict(zip(names, struct.unpack("<%dI" % len(names), tail)))
    assert CODE + len(code) <= ZONE_END
    return code, lab


def jmp(frm, to, pad=0):
    return b"\xE9" + struct.pack("<i", to - frm - 5) + b"\x90" * pad


def patches():
    code, lab = build()
    P = [  # site, expected old, new, label
        (0x5570E858, struct.pack("<I", 0x480), struct.pack("<I", INST_NEW), "InstanceSize"),
        (0x558BA284, jmp(0x558BA284, RW_BACK), jmp(0x558BA284, lab["rw"]), "stream (ban cave exit)"),
        (0x55780F32, jmp(0x55780F32, 0x55851130), jmp(0x55780F32, lab["vis"]), "V1 map sight"),
        (0x5580F247, bytes.fromhex("3c0074108a"), jmp(0x5580F247, lab["rngd"]), "A1 ranged penalty"),
        (0x5580F306, bytes.fromhex("3c00740458"), jmp(0x5580F306, lab["melee"]), "A2 melee penalty"),
        (0x5580F37F, bytes.fromhex("3c007403fe"), jmp(0x5580F37F, lab["hero"]), "A3 hero penalty"),
        (ZONE, bytes(ZONE_END - ZONE), (MAGIC + code).ljust(ZONE_END - ZONE, b"\0"), "zone"),
    ]
    return P, lab, code


def relocs(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; n = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(n)]
    def off(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    p, out = off(rrva), set(); end = p + rsz
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def test():
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EBX, UC_X86_REG_ESP,
                                   UC_X86_REG_EFLAGS, UC_X86_REG_ESI, UC_X86_REG_EDI)
    P, lab, code = patches()
    DELTA, MAPOBJ, STOP, STK = 0x00340000, 0x02000000, 0x00700000, 0x0010F000
    fails = 0
    def run(level, mask, havemap=True):
        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map((ZONE + DELTA) & ~0xFFF, 0x1000); uc.mem_write(CODE + DELTA, code)
        uc.mem_map((GLOBAL_MAP + DELTA) & ~0xFFF, 0x1000); uc.mem_write(GLOBAL_MAP + DELTA, struct.pack("<I", MAPOBJ if havemap else 0))
        uc.mem_map(MAPOBJ, 0x1000); uc.mem_write(MAPOBJ + MAP_OFS, struct.pack("<I", mask))
        uc.mem_map(0x00100000, 0x10000); uc.mem_map(STOP, 0x1000)
        uc.mem_write(STK, struct.pack("<I", STOP))
        regs = {UC_X86_REG_EAX: 0xAABBCC00 | level, UC_X86_REG_ECX: 0x11111111, UC_X86_REG_EDX: 0x22222222, UC_X86_REG_EBX: 0x33333333,
                UC_X86_REG_ESI: 0x44444444, UC_X86_REG_EDI: 0x55555555, UC_X86_REG_ESP: STK}
        for r, v in regs.items(): uc.reg_write(r, v)
        uc.emu_start(lab["nvreq"] + DELTA, STOP)
        regs[UC_X86_REG_ESP] = STK + 4
        same = all(uc.reg_read(r) == v for r, v in regs.items())
        return not (uc.reg_read(UC_X86_REG_EFLAGS) >> 6 & 1), same
    for mask in (0, 1, 8, 2, 0x10, 0x0000001F, 0xFFFFFFFF, 0x10000000):
        for level in list(range(0, 32)) + [0x40, 0xFF]:
            for havemap in (True, False):
                want = level not in (0, 3)
                if havemap and level < 32 and mask >> level & 1: want = not want
                got, same = run(level, mask, havemap)
                if got != want or not same:
                    fails += 1; print("FAIL level %d mask %#x map %s: required %s (want %s) regs kept %s" % (level, mask, havemap, got, want, same))
    print("nvreq: %s" % ("ALL OK (8 masks x 34 levels x map/no map, registers kept)" if not fails else "%d FAILED" % fails))
    return 1 if fails else 0


def main():
    if "--test" in sys.argv:
        return test()
    apply, revert = "--apply" in sys.argv, "--revert" in sys.argv
    P, lab, code = patches()
    d = open(DLL, "rb").read()
    rl = relocs(d)
    bad = sorted(hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, n, _ in P))
    sts = []
    for s, o, n, name in P:
        c = d[s - V2F:s - V2F + len(o)]
        st = "old" if c == o else "ours" if c == n else "OTHER"
        sts.append(st)
        if st == "OTHER": print("  OTHER %-24s %#x: %s (want %s)" % (name, s, c[:16].hex(), o[:16].hex()))
    print("%d sites %s | code %d B, nvreq %#x, rw %#x | relocs %s" % (len(P), {k: sts.count(k) for k in sorted(set(sts))}, len(code), lab["nvreq"], lab["rw"], bad or "none"))
    if bad or "OTHER" in sts or len(set(sts)) != 1:
        print("ABORT"); return 1
    want = "old" if revert else "ours"
    if sts[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not (apply or revert):
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    b = bak_path(DLL, ".bak_levelvision")
    if apply and not os.path.exists(b):
        shutil.copy2(DLL, b); print("backup ->", b)
    with open(DLL, "r+b") as f:
        for s, o, n, name in reversed(P):
            f.seek(s - V2F); f.write(o if revert else n)
    d2 = open(DLL, "rb").read()
    assert all(d2[s - V2F:s - V2F + len(o)] == (o if revert else n) for s, o, n, _ in P)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
