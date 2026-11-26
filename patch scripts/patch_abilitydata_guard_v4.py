#!/usr/bin/env python3
r"""
GetAbilityData guard v4 + duplicate-record clean-up before a save (2026-11-22).

WHY: tester saves (map 'AoWx - Shattered Peaks', 1.37.434): units vanish after a reload.  The save files have HOLES in
the army slot numbering: the unit was alive, its write raised EDoublePrioriyID (two ability-data records with one id in
TAbilityOwner.ReadWrite) and the writer dropped the whole unit.  All dropped units were Leadership-aura followers.
Suspected source of the duplicates: the v3 guard (build_abilitydata_guard_recorder.py, cave 0x55811000) returns nil for
the whole owner when a chain node lies outside 0x400000..0x40000000.  A valid heap block outside that window makes the
existing records invisible -> SetExternalSource adds another Leadership record on every formation update, a hero's
level record is not found (Marksmanship shown as I), etc.

A  guard v4 (new cave, old cave 0x55811000..0x558110BF left in place as dead code):
   hook 0x5574F1C4 `jmp guard`.  Same checks, but a node outside the usual window is no longer rejected: the OS is
   asked (VirtualQuery through VCL30's IAT, reached PIC through AoWEPACK's System.@RandInt import slot); committed and
   accessible -> accepted, otherwise nil as before.  The first rejection is still recorded at 0x558FAF40
   (build_abilitydata_guard_recorder.py --read).
B  TAbilityOwner.ReadWrite, write branch, 0x5574F40B (`cmp [esi+10],0 / je 0x5574F500`, 10 B, no relocation):
   -> cave: unlink every later record whose id equals an earlier one (the newest stays, the duplicate leaks), then the
   displaced test.  A unit with duplicates is saved whole instead of being dropped.

Dry run default; --apply; --revert (surgical: hook A back to the v3 cave, site B stock, cave zeroed); --test (unicorn).
Backup backup\AoWEPACK.dll.bak_abguard4.  Ship AoWEPACK.dll.
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP, EP_D = game_file("AoWEPACK.dll"), 0x55700C00
SUF = ".bak_abguard4"
CAVE, CAVE_END, MAGIC = 0x558BAC00, 0x558BAE00, b"ABG4"
CODE = CAVE + 4

HOOK_A, RESUME_A, OLD_CAVE = 0x5574F1C4, 0x5574F1CB, 0x55811000
SITE_B, B_STOCK = 0x5574F40B, bytes.fromhex("837E10000F84EB000000")
B_SKIP, B_CONT = 0x5574F500, 0x5574F415

SCRATCH = 0x558FAF40
SLOT_RANDINT, VCL_RANDINT, VCL_VQUERY = 0x558FB6DC, 0x41303384, 0x413E4304
MIN_PTR, MAX_PTR = 0x10000, 0x7F000000
NODE_MIN, NODE_MAX = 0x400000, 0x40000000
MAX_NODES = 32


def jmp(frm, to):
    return b"\xE9" + struct.pack("<i", to - frm - 5)


def src(n1, n2):
    return f"""
    guard:
        cmp eax, {MIN_PTR:#x}
        jb bad_self
        cmp eax, {MAX_PTR:#x}
        jae bad_self
        push ecx
        push edx
        mov ecx, dword ptr [eax + 0x10]
        mov edx, {MAX_NODES}
    walk:
        test ecx, ecx
        jz ok
        cmp ecx, {NODE_MIN:#x}
        jb slow
        cmp ecx, {NODE_MAX:#x}
        jae slow
    vt:
        push eax
        mov eax, dword ptr [ecx]
        cmp eax, {MIN_PTR:#x}
        jb bad_node2
        cmp eax, {MAX_PTR:#x}
        jae bad_node2
        pop eax
        mov ecx, dword ptr [ecx + 8]
        dec edx
        jnz walk
    ok:
        pop edx
        pop ecx
        push ebx
        push esi
        mov esi, edx
        mov ebx, dword ptr [eax + 0x10]
        jmp {RESUME_A:#x}

    slow:
        cmp ecx, {MIN_PTR:#x}
        jb bad_node
        cmp ecx, 0x7ffe0000
        jae bad_node
        push eax
        push ecx
        push edx
        sub esp, 28
        call n1
    n1:
        pop edx
        sub edx, {n1:#x}
        mov edx, dword ptr [edx + {SLOT_RANDINT:#x}]
        sub edx, {VCL_RANDINT:#x}
        mov eax, esp
        push 28
        push eax
        push ecx
        call dword ptr [edx + {VCL_VQUERY:#x}]
        test eax, eax
        jz q_bad
        cmp dword ptr [esp + 0x10], 0x1000
        jne q_bad
        mov eax, dword ptr [esp + 0x14]
        test eax, eax
        jz q_bad
        test eax, 0x101
        jnz q_bad
        add esp, 28
        pop edx
        pop ecx
        pop eax
        jmp vt
    q_bad:
        add esp, 28
        pop edx
        pop ecx
        pop eax
        jmp bad_node

    bad_node2:
        pop eax
    bad_node:
        call rec
        pop edx
        pop ecx
        xor eax, eax
        ret
    bad_self:
        push ecx
        push edx
        mov ecx, 1
        call rec
        pop edx
        pop ecx
        xor eax, eax
        ret

    rec:
        push eax
        push edx
        call n2
    n2:
        pop edx
        sub edx, {n2:#x}
        cmp dword ptr [edx + {SCRATCH:#x}], 0
        jne rec_done
        mov dword ptr [edx + {SCRATCH:#x}], 1
        mov dword ptr [edx + {SCRATCH + 8:#x}], eax
        mov dword ptr [edx + {SCRATCH + 0xC:#x}], ecx
        mov eax, dword ptr [esp + 0x14]
        mov dword ptr [edx + {SCRATCH + 4:#x}], eax
        mov eax, dword ptr [esp + 0xC]
        mov dword ptr [edx + {SCRATCH + 0x10:#x}], eax
        mov dword ptr [edx + {SCRATCH + 0x14:#x}], edx
    rec_done:
        pop edx
        pop eax
        ret

    dedupe:
        push ebx
        push edi
        push ebp
        mov ebx, dword ptr [esi + 0x10]
    d_outer:
        test ebx, ebx
        jz d_done
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x4c]
        mov ebp, eax
        mov edi, ebx
    d_inner:
        mov ecx, dword ptr [edi + 8]
        test ecx, ecx
        jz d_next
        push ecx
        mov eax, ecx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x4c]
        pop ecx
        cmp eax, ebp
        jne d_adv
        mov eax, dword ptr [ecx + 8]
        mov dword ptr [edi + 8], eax
        jmp d_inner
    d_adv:
        mov edi, ecx
        jmp d_inner
    d_next:
        mov ebx, dword ptr [ebx + 8]
        jmp d_outer
    d_done:
        pop ebp
        pop edi
        pop ebx
        cmp dword ptr [esi + 0x10], 0
        je {B_SKIP:#x}
        jmp {B_CONT:#x}
    """


def build():
    """-> (code bytes, dedupe offset).  The two `call next / pop` PIC anchors are located from the bytes."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    n1 = n2 = 0x55000000
    for _ in range(3):
        enc, _n = ks.asm(src(n1, n2), CODE)
        b = bytes(enc)
        pos = []
        i = b.find(b"\xE8\x00\x00\x00\x00\x5A")
        while i >= 0:
            pos.append(CODE + i + 5); i = b.find(b"\xE8\x00\x00\x00\x00\x5A", i + 1)
        assert len(pos) == 2, pos
        if (n1, n2) == tuple(pos):
            break
        n1, n2 = pos
    else:
        raise AssertionError("PIC anchors did not settle")
    # dedupe entry = `push ebx / push edi / push ebp / mov ebx,[esi+10]`
    dd = b.rfind(bytes.fromhex("5357558B5E10"))
    assert dd > 0
    return b, dd


def relocs(ep):
    pe = struct.unpack_from("<I", ep, 0x3C)[0]
    n = struct.unpack_from("<H", ep, pe + 6)[0]; o = pe + 0x18 + struct.unpack_from("<H", ep, pe + 0x14)[0]
    base = struct.unpack_from("<I", ep, pe + 0x34)[0]
    rrva, rsz = struct.unpack_from("<II", ep, pe + 0x78 + 5 * 8)
    out = set()
    for i in range(n):
        vs, va, rs, ro = struct.unpack_from("<IIII", ep, o + 40 * i + 8)
        if va <= rrva < va + max(vs, rs):
            p = rrva - va + ro; end = p + rsz
            while p < end:
                page, size = struct.unpack_from("<II", ep, p)
                if size < 8: break
                for k in range((size - 8) // 2):
                    e = struct.unpack_from("<H", ep, p + 8 + 2 * k)[0]
                    if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
                p += size
    return out


def test():
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_ESI,
                                   UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_EIP)
    code, dd = build()
    DELTA = 0x00230000                      # pretend AoWEPACK was rebased
    VDELTA = 0x00050000                     # ... and VCL30 too
    STOP, VQ, GETID = 0x00700000, 0x00701000, 0x00702000
    fails = []

    def run(setup, entry, eax=0, edx=0, esi=0, mapped=()):
        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        def mp(a, size=0x1000):
            try: uc.mem_map(a & ~0xFFF, size)
            except Exception: pass
        mp((CAVE + DELTA) & ~0xFFF, 0x2000); uc.mem_write(CAVE + DELTA, MAGIC + code)
        mp((SCRATCH + DELTA) & ~0xFFF); mp((SLOT_RANDINT + DELTA) & ~0xFFF)
        uc.mem_write(SLOT_RANDINT + DELTA, struct.pack("<I", VCL_RANDINT + VDELTA))
        mp((VCL_VQUERY + VDELTA) & ~0xFFF); uc.mem_write(VCL_VQUERY + VDELTA, struct.pack("<I", VQ))
        mp(0x00700000, 0x3000)
        uc.mem_write(GETID, bytes.fromhex("0FB7400EC3"))          # movzx eax, word [eax+0xE]; ret
        mp(0x00100000, 0x10000); sp = 0x0010F000
        mp(0x02000000, 0x10000)                                    # ordinary heap
        for a in mapped: mp(a)
        setup(uc)
        vq_calls = []
        def hook(uc_, addr, size, _u):
            if addr == VQ:
                esp = uc_.reg_read(UC_X86_REG_ESP)
                ret, a, buf, ln = struct.unpack("<4I", uc_.mem_read(esp, 16))
                vq_calls.append(a)
                ok = any((a & ~0xFFF) == (m & ~0xFFF) for m in mapped)
                uc_.mem_write(buf, struct.pack("<7I", a & ~0xFFF, 0, 4, 0x1000, 0x1000 if ok else 0x10000, 4 if ok else 0, 0))
                uc_.reg_write(UC_X86_REG_EAX, 28); uc_.reg_write(UC_X86_REG_ECX, 0xDEAD); uc_.reg_write(UC_X86_REG_EDX, 0xBEEF)
                uc_.reg_write(UC_X86_REG_ESP, esp + 16); uc_.reg_write(UC_X86_REG_EIP, ret)
        uc.hook_add(UC_HOOK_CODE, hook, begin=VQ, end=VQ)
        uc.mem_write(sp, struct.pack("<I", STOP))
        for r, v in ((UC_X86_REG_ESP, sp), (UC_X86_REG_EAX, eax), (UC_X86_REG_EDX, edx), (UC_X86_REG_ESI, esi),
                     (UC_X86_REG_ECX, 0x11111111), (UC_X86_REG_EBX, 0x22222222), (UC_X86_REG_EDI, 0x33333333), (UC_X86_REG_EBP, 0x44444444)):
            uc.reg_write(r, v)
        stops = (STOP, RESUME_A + DELTA, B_SKIP + DELTA, B_CONT + DELTA)
        mp((RESUME_A + DELTA) & ~0xFFF)
        end = [None]
        def stopper(uc_, addr, size, _u):
            if addr in stops: end[0] = addr; uc_.emu_stop()
        uc.hook_add(UC_HOOK_CODE, stopper)
        try:
            uc.emu_start(entry + DELTA, 0, count=20000)
        except Exception as ex:
            end[0] = "FAULT %s at %#x" % (ex, uc.reg_read(UC_X86_REG_EIP))
        return uc, end[0], vq_calls

    def node(uc, a, nxt, aid, vmt=0x02008000):
        uc.mem_write(a, struct.pack("<III", vmt, 0, nxt) + b"\0\0" + struct.pack("<H", aid))
    def chk(name, cond):
        print("  %-62s %s" % (name, "ok" if cond else "FAIL"))
        if not cond: fails.append(name)

    OWN = 0x02000100
    G = CODE
    reg = lambda uc, r: uc.reg_read(r)
    # 1 healthy chain inside the window -> falls into the stock routine with the displaced 7 bytes done
    def s1(uc):
        uc.mem_write(0x02008000 + 0x4C, struct.pack("<I", GETID))
        uc.mem_write(OWN + 0x10, struct.pack("<I", 0x02001000)); node(uc, 0x02001000, 0x02001100, 0x2E); node(uc, 0x02001100, 0, 0x20)
    uc, end, vq = run(s1, G, eax=OWN, edx=0x2E)
    chk("in-window chain -> resume, esi=id, ebx=head, no OS query", end == RESUME_A + DELTA and reg(uc, UC_X86_REG_ESI) == 0x2E and reg(uc, UC_X86_REG_EBX) == 0x02001000 and not vq
        and reg(uc, UC_X86_REG_ECX) == 0x11111111 and reg(uc, UC_X86_REG_EDX) == 0x2E and reg(uc, UC_X86_REG_EAX) == OWN)
    # 2 valid node BELOW the window (v3 returned nil here)
    def s2(uc):
        uc.mem_write(OWN + 0x10, struct.pack("<I", 0x00300040)); node(uc, 0x00300040, 0x02001100, 0x2E); node(uc, 0x02001100, 0, 0x20)
    uc, end, vq = run(s2, G, eax=OWN, edx=0x2E, mapped=(0x00300000,))
    chk("valid node below 0x400000 -> accepted after one OS query", end == RESUME_A + DELTA and vq == [0x00300040] and reg(uc, UC_X86_REG_EBX) == 0x00300040
        and reg(uc, UC_X86_REG_ECX) == 0x11111111 and reg(uc, UC_X86_REG_EDX) == 0x2E and reg(uc, UC_X86_REG_EAX) == OWN)
    # 3 valid node ABOVE the window
    def s3(uc):
        uc.mem_write(OWN + 0x10, struct.pack("<I", 0x02001100)); node(uc, 0x02001100, 0x45000040, 0x20); node(uc, 0x45000040, 0, 0x2E)
    uc, end, vq = run(s3, G, eax=OWN, edx=0x2E, mapped=(0x45000000,))
    chk("valid node above 0x40000000 -> accepted", end == RESUME_A + DELTA and vq == [0x45000040])
    # 4 wild node (unmapped) -> nil, recorded, no fault
    def s4(uc):
        uc.mem_write(OWN + 0x10, struct.pack("<I", 0x47280000))
    uc, end, vq = run(s4, G, eax=OWN, edx=0x2E)
    recd = struct.unpack("<6I", uc.mem_read(SCRATCH + DELTA, 24))
    chk("unmapped node -> nil + recorded (owner, node, id, delta)", end == STOP and reg(uc, UC_X86_REG_EAX) == 0 and recd[0] == 1 and recd[2] == OWN and recd[3] == 0x47280000
        and recd[4] == 0x2E and recd[5] == DELTA and recd[1] == STOP and reg(uc, UC_X86_REG_ESP) == 0x0010F004 and reg(uc, UC_X86_REG_ECX) == 0x11111111)
    # 5 bad Self
    uc, end, vq = run(lambda uc: None, G, eax=0x40, edx=0x2E)
    chk("bad Self -> nil", end == STOP and reg(uc, UC_X86_REG_EAX) == 0 and reg(uc, UC_X86_REG_ESP) == 0x0010F004)
    # 6 node with a garbage vtable -> nil
    def s6(uc):
        uc.mem_write(OWN + 0x10, struct.pack("<I", 0x02001000)); node(uc, 0x02001000, 0, 0x2E, vmt=0x20)
    uc, end, vq = run(s6, G, eax=OWN, edx=0x2E)
    chk("garbage vtable -> nil", end == STOP and reg(uc, UC_X86_REG_EAX) == 0 and reg(uc, UC_X86_REG_ESP) == 0x0010F004)
    # 7 nil chain
    uc, end, vq = run(lambda uc: None, G, eax=OWN, edx=0x2E)
    chk("empty chain -> resume", end == RESUME_A + DELTA and reg(uc, UC_X86_REG_EBX) == 0)

    # dedupe
    D = CODE + dd
    def chain(uc):
        out = []; p = struct.unpack("<I", uc.mem_read(OWN + 0x10, 4))[0]
        while p:
            out.append((p, struct.unpack("<H", uc.mem_read(p + 0xE, 2))[0])); p = struct.unpack("<I", uc.mem_read(p + 8, 4))[0]
        return out
    def mk(ids):
        def s(uc):
            uc.mem_write(0x02008000 + 0x4C, struct.pack("<I", GETID))
            a = [0x02001000 + 0x40 * i for i in range(len(ids))]
            uc.mem_write(OWN + 0x10, struct.pack("<I", a[0] if a else 0))
            for i, aid in enumerate(ids): node(uc, a[i], a[i + 1] if i + 1 < len(a) else 0, aid)
        return s
    for ids, want in (([0x2E, 0x2E, 0x71, 0x2E, 0x20, 0x71], [0x2E, 0x71, 0x20]), ([0x20, 0x2E], [0x20, 0x2E]), ([0x6C, 0x6C], [0x6C]), ([0x2E], [0x2E])):
        uc, end, vq = run(mk(ids), D, esi=OWN)
        got = chain(uc)
        chk("dedupe %s -> %s, first copies kept, registers kept" % (ids, want), end == B_CONT + DELTA and [i for _, i in got] == want and got[0][0] == 0x02001000
            and reg(uc, UC_X86_REG_EBX) == 0x22222222 and reg(uc, UC_X86_REG_EDI) == 0x33333333 and reg(uc, UC_X86_REG_EBP) == 0x44444444
            and reg(uc, UC_X86_REG_ESI) == OWN and reg(uc, UC_X86_REG_ESP) == 0x0010F000)
    uc, end, vq = run(mk([]), D, esi=OWN)
    chk("dedupe on an empty list -> stock skip branch", end == B_SKIP + DELTA and reg(uc, UC_X86_REG_ESP) == 0x0010F000)
    print("ALL OK" if not fails else "FAILED: %s" % fails)
    return 1 if fails else 0


def main():
    if "--test" in sys.argv:
        return test()
    apply, revert = "--apply" in sys.argv, "--revert" in sys.argv
    ep = open(EP, "rb").read()
    code, dd = build()
    blob = MAGIC + code
    assert len(blob) <= CAVE_END - CAVE, len(blob)
    GUARD, DEDUPE = CODE, CODE + dd
    o_c, o_a, o_b = CAVE - EP_D, HOOK_A - EP_D, SITE_B - EP_D
    a_old, a_new = jmp(HOOK_A, OLD_CAVE) + b"\x90\x90", jmp(HOOK_A, GUARD) + b"\x90\x90"
    b_new = jmp(SITE_B, DEDUPE) + b"\x90" * 5
    cave, a, b = ep[o_c:o_c + (CAVE_END - CAVE)], ep[o_a:o_a + 7], ep[o_b:o_b + 10]
    applied = a == a_new and b == b_new and cave.startswith(blob)
    clean = a == a_old and b == B_STOCK and not any(cave)
    print("cave %#x..%#x: %d B (guard %#x, dedupe %#x) | state: %s" % (CAVE, CAVE + len(blob), len(blob), GUARD, DEDUPE,
          "APPLIED" if applied else "clean (v3 guard)" if clean else "UNKNOWN"))
    rl = relocs(ep)
    hit = [hex(r) for r in rl if HOOK_A - 3 <= r < HOOK_A + 7 or SITE_B - 3 <= r < SITE_B + 10 or CAVE - 3 <= r < CAVE_END]
    if hit:
        print("ABORT: relocation entries inside a patched range:", hit); return 1
    if revert:
        if not applied:
            print("not applied"); return 1
        with open(EP, "r+b") as f:
            f.seek(o_a); f.write(a_old); f.seek(o_b); f.write(B_STOCK); f.seek(o_c); f.write(bytes(CAVE_END - CAVE))
        print("reverted (v3 guard active again)"); return 0
    if applied:
        print("ALREADY PATCHED"); return 0
    if not clean:
        print("ABORT: unexpected bytes  hook A %s  site B %s  cave used %d" % (a.hex(), b.hex(), sum(1 for x in cave if x))); return 1
    if not apply:
        print("Dry run OK - rerun with --apply"); return 0
    bk = bak_path(EP, SUF)
    if not os.path.exists(bk):
        shutil.copy2(EP, bk); print("backup ->", bk)
    with open(EP, "r+b") as f:
        f.seek(o_c); f.write(blob); f.seek(o_a); f.write(a_new); f.seek(o_b); f.write(b_new)
    print("applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
