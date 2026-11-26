#!/usr/bin/env python3
r"""AoWx -- AI heroes value ground items higher (priority boost + empty-slot bonus), busy groups untouched (2026-10-19).

User: "still instances of AI not picking up nearby items 2-3 turns away, so I think the priority needs to be
increased for picking up items or something."

RE (AoWEPACK, live after build_ai_itemloot v2.5 + use_v1 + reach_v1 + antilure_v1):
  * cave_target (0x55814D40) answers field msg 0x1200 for a ground item with
        priority = 10 + min(best/2, 65)            (best = cave_value of the best item some hero of the asking group
                                                      would take; a +2 DEF helmet ~20 -> priority 20)
    reach_v1 refunds the selector's -25/turn travel penalty for 1..3 turns, so an item competes at that priority.
  * TAIGroupTargetSelector.Score 0x5573C57C:  score = priority*[set+4](1.0) - 25*turns + (current target of the
    group: +75 in mode 2 / +25 in mode 1; [group+0x38] = target key x|y<<8|level<<16, [group+0x3C] mode set by
    SetTarget 0x55737648: 2 = feasible/committed, 1 = needs help) - 100 if [t+0x38]<>-1 - 50/-199 if another own
    group heads there (settings init 0x5573C4C0).  Competing answers: enemy city 50/100/300 (0x55790618), site
    ladder 15..100, own-city defence etc.  So a 20-priority helmet loses to nearly everything.
  * The group's current target carries no 'mission type' field (mode 1/2 = feasibility, not attack/defend), so the
    sticky +75 is NOT overridden here (overriding it globally would make groups oscillate between targets).
    Instead "busy" is read from the target itself: if the asking group's current target field holds a CITY
    (GetObjectOfType 0x20108 via field VMT+0x80; own = defence/garrison, foreign = attack) or a FOREIGN army
    (0x55771EB0, owner byte [[hs+0x1C]+0x12] <> group player [group+0x28]) -> attack / defence mission -> no item
    answer at all (garrisons and attack groups are never pulled out by loot).  Own army on the target field
    (merge / cooperation / the group's own spot) is not 'busy'.

FIX (two hooks inside our own cave_target, zone 0x5581F000..0x5581F800 'APR1'):
  E 0x55814E96 (13 B `test eax,eax / je 0x55814EA8 / call cave_value / cmp eax,[esp+0x10]`, equip-slot test) -> EC:
      the slot is EMPTY -> best := value + EMPTY_B (40 => +20 priority) and continue with the next item;
      otherwise the original value compare, back at the original `jl` 0x55814EA3.  Use items: no bonus (modest).
  P 0x55814EC0 (15 B priority formula `shr/cmp 0x41/jle/mov 0x41/add 0xA`) -> PC:
      group target key == none or its field has neither a city nor a foreign army -> priority = BASE + min(best/2, CAP)
      (35..95);  otherwise (busy) -> no answer (jump to cave_target's _done 0x55814ED5).
      PC then continues at 0x55814ECF (reach_v1's TC hook: write + refund mark), so reach/antilure stay in force.
Field access exactly as converge/antilure: holder [0x558E9494] (PIC), map=[holder], grid = 0x557020EC(eax=[map+0x10],
edx=level), field = 0x557020DC(eax=grid, edx=x, ecx=y) with 0<=x<[grid+0xC], 0<=y<[grid+0x10].
MP: runs inside every peer's identical AI target search; game state only, no RNG.
Order: apply AFTER build_ai_itemloot, use_v1, reach_v1, antilure_v1; revert this FIRST.  Backup .bak_aiprio.
Usage: py -3.10 patch_ai_itemloot_prio_v1.py [--apply|--revert] [dll]   (dry run default)
"""
import os, shutil, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts")
import build_ai_itemloot as L
try:
    from bakpath import bak_path
except Exception:
    def bak_path(p, s): return p + s

DLL = L.DLL
D = L.D
ZONE_LO, ZONE_HI = 0x5581F000, 0x5581F100   # 10/20: 0x5581F100+ = no_pair_start, host_guard, dispel, converge v3 (zeroed), hexgrid
MAGIC = b"APR1"
BASE, CAP, EMPTY_B = 35, 60, 40
MAPHOLD = 0x558E9494
GETGRID, GETFIELD, ARMYHS, CITY_T = 0x557020EC, 0x557020DC, 0x55771EB0, 0x20108
CAVE_VALUE = 0x55814840

E_SITE, E_ORIG = 0x55814E96, bytes.fromhex("85c0740ee8a1f9ffff3b442410")
E_JL, E_INEXT = 0x55814EA3, 0x55814EB0
P_SITE, P_ORIG = 0x55814EC0, bytes.fromhex("d1e883f8417e05b84100000083c00a")
P_NEXT, P_DONE = 0x55814ECF, 0x55814ED5


def make_caves():
    EC = ZONE_LO + 0x10
    ec = bytes(L.asm(f"""
        test eax, eax
        jz   _empty
        call 0x{CAVE_VALUE:X}
        cmp  eax, dword ptr [esp+0x10]
        jmp  0x{E_JL:X}
    _empty:
        mov  eax, dword ptr [esp+0x10]
        add  eax, {EMPTY_B}
        mov  dword ptr [esp+4], eax
        jmp  0x{E_INEXT:X}
    """, EC))
    PC = (EC + len(ec) + 0xF) & ~0xF
    src = f"""
        push ecx
        push edx
        push eax
        mov  ecx, dword ptr [esp+0x14]
        test ecx, ecx
        jz   _boost
        mov  edx, dword ptr [ecx+0x38]
        and  edx, 0xFFFFFF
        cmp  edx, 0xFFFFFF
        je   _boost
        push edx
        call _p
    _p:
        pop  eax
        add  eax, DELTA
        mov  eax, dword ptr [eax]
        test eax, eax
        jz   _bpop
        mov  eax, dword ptr [eax]
        test eax, eax
        jz   _bpop
        mov  eax, dword ptr [eax+0x10]
        movzx edx, byte ptr [esp+2]
        call 0x{GETGRID:X}
        test eax, eax
        jz   _bpop
        movzx edx, byte ptr [esp]
        cmp  edx, dword ptr [eax+0xC]
        jge  _bpop
        movzx ecx, byte ptr [esp+1]
        cmp  ecx, dword ptr [eax+0x10]
        jge  _bpop
        call 0x{GETFIELD:X}
        test eax, eax
        jz   _bpop
        mov  dword ptr [esp], eax
        mov  edx, {CITY_T}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jnz  _busy
        mov  eax, dword ptr [esp]
        call 0x{ARMYHS:X}
        test eax, eax
        jz   _bpop
        mov  eax, dword ptr [eax+0x1C]
        test eax, eax
        jz   _bpop
        mov  ecx, dword ptr [esp+0x18]
        mov  dl, byte ptr [eax+0x12]
        cmp  dl, byte ptr [ecx+0x28]
        jne  _busy
    _bpop:
        pop  edx
    _boost:
        pop  eax
        shr  eax, 1
        cmp  eax, {CAP}
        jle  _c
        mov  eax, {CAP}
    _c:
        add  eax, {BASE}
        pop  edx
        pop  ecx
        jmp  0x{P_NEXT:X}
    _busy:
        pop  edx
        pop  eax
        pop  edx
        pop  ecx
        jmp  0x{P_DONE:X}
    """
    code = bytes(L.asm(src.replace("DELTA", "0x7FFFFFF0"), PC))
    k = next(k for k in range(len(code) - 5) if code[k] == 0xE8 and code[k + 1:k + 5] == bytes(4))
    pop_va = PC + k + 5
    pc = bytes(L.asm(src.replace("DELTA", "0x%X" % ((MAPHOLD - pop_va) & 0xFFFFFFFF)), PC))
    assert pc[k] == 0xE8 and pc[k + 1:k + 5] == bytes(4) and len(pc) == len(code)
    assert PC + len(pc) <= ZONE_HI
    return EC, ec, PC, pc


def jmp(src, dst, n):
    return b"\xE9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (n - 5)


def edits():
    EC, ec, PC, pc = make_caves()
    blob = bytearray(PC + len(pc) - ZONE_LO)
    blob[0:4] = MAGIC
    blob[EC - ZONE_LO:EC - ZONE_LO + len(ec)] = ec
    blob[PC - ZONE_LO:PC - ZONE_LO + len(pc)] = pc
    return [(ZONE_LO, bytes(len(blob)), bytes(blob), "caves EC/PC (APR1)"),
            (E_SITE, E_ORIG, jmp(E_SITE, EC, 13), "E equip-slot test -> EC"),
            (P_SITE, P_ORIG, jmp(P_SITE, PC, 15), "P priority formula -> PC")]


def relocs(dll_bytes):
    import pefile
    pe = pefile.PE(data=dll_bytes)
    base = pe.OPTIONAL_HEADER.ImageBase
    return set(base + e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type)


def main(dll=None):
    dll = dll or DLL
    ap = "--apply" in sys.argv
    rv = "--revert" in sys.argv
    d = bytearray(open(dll, "rb").read())
    E = edits()
    rel = relocs(bytes(d))
    bad = [r for r in rel if ZONE_LO - 3 <= r < ZONE_HI]
    assert not bad, "reloc in zone: %s" % [hex(x) for x in bad]
    for va, ob, nb, nm in E:
        bad = [r for r in rel if va - 3 <= r < va + len(nb)]
        assert not bad, "reloc under %s: %s" % (nm, [hex(x) for x in bad])
    st = []
    for va, ob, nb, nm in E:
        c = bytes(d[va - D:va - D + len(nb)])
        s = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        st.append(s)
        print("  %-32s @0x%08X  %s (%d B)" % (nm, va, s, len(nb)))
    zlen = len(E[0][2])
    tail = d[ZONE_LO + zlen - D:ZONE_HI - D]
    print("  zone tail 0x%08X..0x%08X free: %s | BASE %d CAP %d EMPTY_B %d | relocs none"
          % (ZONE_LO + zlen, ZONE_HI, not any(tail), BASE, CAP, EMPTY_B))
    if "FOREIGN" in st or any(tail):
        print("FOREIGN - refusing")
        return 1
    if rv:
        if all(s == "original" for s in st):
            print("not applied")
            return 0
        for va, ob, nb, _ in E:
            d[va - D:va - D + len(nb)] = ob
        with open(dll, "r+b") as f:
            f.seek(0); f.write(bytes(d))
        print("reverted")
        return 0
    if not ap:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in st):
        print("already applied")
        return 0
    if any(s == "applied" for s in st):
        print("partially applied - refusing (revert first)")
        return 1
    bk = bak_path(dll, ".bak_aiprio")
    if not os.path.isfile(bk):
        shutil.copy2(dll, bk)
        print("backup ->", bk)
    for va, ob, nb, _ in E:
        d[va - D:va - D + len(nb)] = nb
    with open(dll, "r+b") as f:
        f.seek(0); f.write(bytes(d))
    back = open(dll, "rb").read()
    for va, ob, nb, _ in E:
        assert back[va - D:va - D + len(nb)] == nb
    print("written and verified: item priority %d..%d (+%d empty slot), busy groups (city/army target) never drawn"
          % (BASE, BASE + CAP, EMPTY_B // 2))
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    sys.exit(main(a[0] if a else None))
