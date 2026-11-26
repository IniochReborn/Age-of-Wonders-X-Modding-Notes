#!/usr/bin/env python3
r"""AoWx -- AI ignores ground items a HUMAN leader/hero could reach this turn (anti-lure, 2026-10-19).

User: "to make sure players can't exploit the AI by dropping items to lure them, make it so that any player-controlled
leader or hero within one turn of the item makes the AI not go for the item."

WHERE: the AI's item attraction is our cave_target (build_ai_itemloot.py, TItemHS VMT+0xCC @0x55814D40), the answer
to the AI target finder's field broadcast 0x1200 (only TAIGroupTargetFinder sends it, so only AI groups ask).  After
its message/mode checks it loads the answer record:
    0x55814D7F  8B 5F 0C   mov ebx,[edi+0xC]      (5 B hooked, reloc-free, inside our own cave)
    0x55814D82  85 DB      test ebx,ebx
    0x55814D84  0F 84 ..   je  _done (0x55814ED5)
  regs there: esi = TItemHS (the ground-item holder), edi = msg, frame = cave_target's (sub esp,0x20 done).
HOOK -> AL cave: if the record exists and GUARD(item HS) says "a human leader/hero is within one turn", jump to
cave_target's _done (no answer -> priority 0 -> the item never attracts any AI group); else re-test ebx and continue.
reach_v1's T/Q/R hooks are untouched (no answer written -> no G mark -> nothing to refund).

GUARD (pure game state, no RNG -> identical on every peer; reads only):
  item x/y/level = TItemHS VMT +0x74/+0x78/+0x7C (al, the HSE GetX/GetY/GetLevel thunks sites use too);
  map = [0x558E9494] (PIC), grid = 0x557020EC(eax=[map+0x10], edx=level), field = 0x557020DC(eax=grid, edx=x, ecx=y)
  with 0 <= x < [grid+0xC], 0 <= y < [grid+0x10]; army HS = 0x55771EB0(field); army = [hs+0x1C]
  (field access exactly as patch_ai_site_converge_v1 / the engine's own finder 0x557CC7D0).
  For every army in the square |dx|,|dy| <= RMAX on the item's level:
    owner = movsx byte [army+0x12] (< 0 -> skip, independents);  player = TPlayers.Get([[0x558FA040]+0x140], owner)
    human  <=> [player+0xA7] == 0  (the AI flag ai-site-leader-safety's XS gate tests);
    hero   <=> some unit IsClass THero (cell 0x55711FAC; TLeader derives from THero);
    reach  R = min over its units of GetMoves (unit VMT+0xD4, al) div HEX_MP + 1, capped at RMAX
           ("one turn" on open terrain at HEX_MP move points per hex, +1 hex slack for roads/partial terrain --
           the same reach rule patch_ai_ranged_obstacles_v1 uses for 'can reach next turn'; exact pathing per item
           query would be far too expensive);
    lured  <=> human AND hero AND max(|dx|,|dy|) <= R.
  max(|dx|,|dy|) on AoW's offset hex grid is <= the true hex distance, so the test can only over-include
  (conservative, which is the right side for an anti-exploit rule).
Pickup is NOT guarded: an AI hero already standing on the item takes it (only the long-range lure is refused).

Zone AoWEPACK 0x5581C480..0x5581C800 (header 'ALR1' + the 5 original bytes; reach_v1 ends 0x5581C479).
Order: apply AFTER build_ai_itemloot.py + patch_ai_itemloot_use_v1.py + patch_ai_itemloot_reach_v1.py;
revert this FIRST.  Backup <game>\backup\AoWEPACK.dll.bak_aiantilure.
Usage: py -3.10 patch_ai_itemloot_antilure_v1.py [--apply|--revert|--dis] [dll]   (dry run default)
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
MAGIC = b"ALR1"
ZONE_LO, ZONE_HI = 0x5581C480, 0x5581C6C0   # 10/19: 0x5581C6C0+ = patch_ai_site_converge_v2 (CNV2)
CODE = ZONE_LO + 0x10
SITE, SITE_ORIG = 0x55814D7F, bytes.fromhex("8b5f0c85db")
BACK, DONE = 0x55814D84, 0x55814ED5
RMAX = 8      # 10/19 user: one-turn reach -30..40 % (was 12)
HEX_MP = 6    # 10/19 user: one-turn reach -30..40 % (was 4)

MAPHOLD = 0x558E9494
GAME_CELL = 0x558FA040
HERO_CELL = 0x55711FAC
GETGRID, GETFIELD, ARMYHS = 0x557020EC, 0x557020DC, 0x55771EB0
GETPLAYERS = 0x557544D0
GETUNIT = 0x5578309C
ISCLASS = 0x557010C0

SRC = """
entry:
    mov  ebx, [edi+0xC]
    test ebx, ebx
    jz   e_back
    pushad
    mov  eax, esi
    call guard
    test eax, eax
    popad
    jnz  e_lured
    test ebx, ebx
e_back:
    jmp  {BACK}
e_lured:
    jmp  {DONE}

; guard(eax = TItemHS) -> eax = 1 lured / 0.  Called inside pushad: may clobber everything but esp.
; frame: [esp+0]=ix [+4]=iy [+8]=lvl [+0xC]=grid [+0x10]=dy [+0x14]=dx [+0x18]=heroref [+0x1C]=players
;        [+0x20]=army [+0x24]=unit idx [+0x28]=minMP [+0x2C]=hero flag
guard:
    push ebp
    sub  esp, 0x30
    mov  ebx, eax
    call g_p
g_p:
    pop  ebp
    mov  eax, [ebp + {KHERO}]
    mov  [esp+0x18], eax
    mov  eax, [ebp + {KGAME}]
    test eax, eax
    jz   g_no
    mov  eax, [eax+0x140]
    test eax, eax
    jz   g_no
    mov  [esp+0x1C], eax
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x74]
    movsx eax, al
    mov  [esp], eax
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x78]
    movsx eax, al
    mov  [esp+4], eax
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x7c]
    movsx eax, al
    mov  [esp+8], eax
    mov  eax, [ebp + {KMAP}]
    test eax, eax
    jz   g_no
    mov  eax, [eax]
    test eax, eax
    jz   g_no
    mov  eax, [eax+0x10]
    mov  edx, [esp+8]
    call {GETGRID}
    test eax, eax
    jz   g_no
    mov  [esp+0xC], eax
    mov  dword ptr [esp+0x10], -{RMAX}
g_ly:
    mov  dword ptr [esp+0x14], -{RMAX}
g_lx:
    mov  edx, [esp]
    add  edx, [esp+0x14]
    js   g_nx
    mov  ecx, [esp+0xC]
    cmp  edx, [ecx+0xC]
    jge  g_nx
    mov  ecx, [esp+4]
    add  ecx, [esp+0x10]
    js   g_nx
    mov  eax, [esp+0xC]
    cmp  ecx, [eax+0x10]
    jge  g_nx
    call {GETFIELD}
    test eax, eax
    jz   g_nx
    call {ARMYHS}
    test eax, eax
    jz   g_nx
    mov  eax, [eax+0x1C]
    test eax, eax
    jz   g_nx
    mov  [esp+0x20], eax
    movsx edx, byte ptr [eax+0x12]
    test edx, edx
    jl   g_nx
    mov  eax, [esp+0x1C]
    call {GETPLAYERS}
    test eax, eax
    jz   g_nx
    cmp  byte ptr [eax+0xA7], 0
    jne  g_nx
    mov  dword ptr [esp+0x24], 0
    mov  dword ptr [esp+0x28], 127
    mov  dword ptr [esp+0x2C], 0
g_ul:
    mov  eax, [esp+0x20]
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    cmp  [esp+0x24], eax
    jge  g_ud
    mov  eax, [esp+0x20]
    mov  edx, [esp+0x24]
    call {GETUNIT}
    inc  dword ptr [esp+0x24]
    test eax, eax
    jz   g_ul
    mov  ebx, eax
    mov  edx, [eax]
    call dword ptr [edx+0xD4]
    movsx eax, al
    cmp  eax, [esp+0x28]
    jge  g_mp
    mov  [esp+0x28], eax
g_mp:
    cmp  dword ptr [esp+0x2C], 0
    jne  g_ul
    mov  eax, ebx
    mov  edx, [esp+0x18]
    call {ISCLASS}
    test al, al
    jz   g_ul
    mov  dword ptr [esp+0x2C], 1
    jmp  g_ul
g_ud:
    cmp  dword ptr [esp+0x2C], 0
    je   g_nx
    mov  eax, [esp+0x28]
    test eax, eax
    jge  g_pos
    xor  eax, eax
g_pos:
    cdq
    mov  ecx, {HEX_MP}
    idiv ecx
    inc  eax
    cmp  eax, {RMAX}
    jle  g_rok
    mov  eax, {RMAX}
g_rok:
    mov  ecx, [esp+0x14]
    test ecx, ecx
    jge  g_ax
    neg  ecx
g_ax:
    cmp  ecx, eax
    jg   g_nx
    mov  ecx, [esp+0x10]
    test ecx, ecx
    jge  g_ay
    neg  ecx
g_ay:
    cmp  ecx, eax
    jg   g_nx
    mov  eax, 1
    jmp  g_out
g_nx:
    inc  dword ptr [esp+0x14]
    cmp  dword ptr [esp+0x14], {RMAX}
    jle  g_lx
    inc  dword ptr [esp+0x10]
    cmp  dword ptr [esp+0x10], {RMAX}
    jle  g_ly
g_no:
    xor  eax, eax
g_out:
    add  esp, 0x30
    pop  ebp
    ret
"""


def build():
    """Assemble at CODE; PIC deltas (target - address of g_p's pop) resolved in a second pass (disp32 forced)."""
    big = 0x7FFFFF00
    fmt = dict(BACK=BACK, DONE=DONE, RMAX=RMAX, HEX_MP=HEX_MP, GETGRID=GETGRID, GETFIELD=GETFIELD,
               ARMYHS=ARMYHS, GETPLAYERS=GETPLAYERS, GETUNIT=GETUNIT, ISCLASS=ISCLASS)
    c0 = L.asm(SRC.format(KHERO=big, KGAME=big + 4, KMAP=big + 8, **fmt), CODE)
    k = next(i for i in range(len(c0) - 5) if c0[i] == 0xE8 and c0[i + 1:i + 5] == bytes(4))
    pop_va = CODE + k + 5
    kv = lambda t: (t - pop_va) & 0xFFFFFFFF
    c1 = L.asm(SRC.format(KHERO=kv(HERO_CELL), KGAME=kv(GAME_CELL), KMAP=kv(MAPHOLD), **fmt), CODE)
    assert len(c1) == len(c0) and c1[k:k + 5] == c0[k:k + 5]
    assert CODE + len(c1) <= ZONE_HI, hex(CODE + len(c1))
    zone = bytearray(MAGIC + SITE_ORIG + bytes(CODE - ZONE_LO - len(MAGIC) - len(SITE_ORIG)) + bytes(c1))
    return bytes(zone)


def jmp(src, dst, n):
    return b"\xE9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (n - 5)


def edits():
    z = build()
    return [(ZONE_LO, bytes(len(z)), z, "AL cave (anti-lure guard)"),
            (SITE, SITE_ORIG, jmp(SITE, CODE, 5), "cave_target record load -> AL")]


def relocs(dll_bytes):
    import pefile
    pe = pefile.PE(data=dll_bytes)
    base = pe.OPTIONAL_HEADER.ImageBase
    return set(base + e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type)


def main(dll=None):
    dll = dll or DLL
    ap, rv = "--apply" in sys.argv, "--revert" in sys.argv
    d = bytearray(open(dll, "rb").read())
    E = edits()
    if "--dis" in sys.argv:
        import capstone
        z = E[0][2]
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(z[CODE - ZONE_LO:], CODE):
            print("  %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    rel = relocs(bytes(d))
    for va, ob, nb, nm in E:
        bad = [r for r in rel if va - 3 <= r < va + len(nb)]
        assert not bad, "reloc under %s: %s" % (nm, [hex(x) for x in bad])
    tail = bytes(d[ZONE_LO + len(E[0][2]) - D:ZONE_HI - D])
    st = []
    for va, ob, nb, nm in E:
        c = bytes(d[va - D:va - D + len(nb)])
        s = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        st.append(s)
        print("  %-34s @0x%08X  %s (%d B)" % (nm, va, s, len(nb)))
    print("  zone tail free: %s | RMAX %d  HEX_MP %d | relocs none" % (not any(tail), RMAX, HEX_MP))
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
    bk = bak_path(dll, ".bak_aiantilure")
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
    print("written and verified: AI ignores ground items a human leader/hero could reach this turn")
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    sys.exit(main(a[0] if a else None))
