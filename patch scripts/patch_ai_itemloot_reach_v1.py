#!/usr/bin/env python3
r"""AoWx -- AI heroes travel up to 3 turns for ground items they would take (2026-10-19).

User: two helmets lay on a cleared monster lair; the AI leader had NO helmet and was 2-3 turns away; his own
leaderless stack had cleared the lair and left -> the leader never went for them.

ROOT CAUSE (static RE, AoWEPACK):
  * Group targets come from TAIGroupTargetFinder (VMT 0x5571AAC4; init 0x5573A234: flood range [finder+0x23C] = 200
    move points, so a 2-3 turn field IS scanned).  Per candidate field the finder state machine (0x55743174, state 2
    @0x557432E6) sends broadcast 0x1200 (0x55771D84; our cave_target answers for ground items: priority
    10 + min(value/2, 65) when some hero of the asking group would take the item -> a +1..+2 DEF helmet = 15..20),
    then records the PATH COST to the field (0x557452E4 -> [rec+0x28]).
  * TAIGroupTargetSelector.Score (0x5573C57C) rates every target:
        score = priority * 1.0
              + settings[+0x30] (-25) * ((cost - 1) div groupMP)      groupMP = min unit MP (0x55737418)
              + -100 if [t+0x38] <> -1, +25/+75 stickiness for the group's own current target,
              -50/-199 if another own group already heads there ...
    i.e. **-25 per turn of travel beyond the first**.  A 15-20 helmet 2-3 turns away scores -10..-35 and loses to
    anything (the group's current target alone gets +75).  Not the radius, not the listed-field skip, not the site
    structure (a cleared site no longer answers).
FIX: item answers get the travel penalty paid back for trips of up to MAXT (3) turns -> a wanted item competes at its
own priority as if it lay next door; beyond 3 turns vanilla.  Only answers our cave_target wrote (the item rule:
some hero of the asking group would take it) are touched; everything else is unchanged.
  T  0x55814ECF (cave_target tail, 6 B `cmp [ebx],eax / jge / mov [ebx],eax`) -> TC: same, and on a write remember
     G = {answer ptr, priority, asking group}.
  Q  0x55743330 (state-2 query setup, 5 B `lea eax,[esp+0xC] / push eax`) -> QC: G.ans := 0, then the original
     (no stale mark can survive into another query).
  R  0x55743380 (10 B: the two record stores after the path cost) -> RC: the original stores, then if G marks THIS
     answer (same ptr, priority unchanged, same group): turns = (cost-1) div groupMP (the selector's own formula);
     1..MAXT -> answer += PEN*turns; G cleared.  The answer is copied into the record right after (0x5574338C).
  G = 0x5590BFE0..0x5590BFEC (AoWEPACK .idata page slack, zero at load; owners nearby: tame 0x5590BF80, site-army
  0x5590BFC0, reversal 0x5590BFF0).  Caves PIC (call/pop), rel32 calls only.  Zone 0x5581C3C0..0x5581C800.
MP: runs inside every peer's identical AI target search, no RNG, deterministic.
Order: apply AFTER build_ai_itemloot.py + patch_ai_itemloot_use_v1.py; revert this BEFORE either.  Backup .bak_aireach.
Usage: py -3.10 patch_ai_itemloot_reach_v1.py [--apply|--revert] [dll]   (dry run default)
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
ZONE_LO, ZONE_HI = 0x5581C3C0, 0x5581C800
G = 0x5590BFE0
MAXT = 3
PEN = 25
GROUP_MP = 0x55737418

T_SITE, T_ORIG, T_RET = 0x55814ECF, bytes.fromhex("39037d028903"), 0x55814ED5
Q_SITE, Q_ORIG, Q_RET = 0x55743330, bytes.fromhex("8d44240c50"), 0x55743335
R_SITE, R_ORIG, R_RET = 0x55743380, bytes.fromhex("894528c7452cffffffff"), 0x5574338A


def _asm_pic(src, addr):
    """Assemble `src` (which contains one `call _p / _p: pop R / add R, DELTA`) twice: DELTA = G - address(_p)."""
    code = L.asm(src.replace("DELTA", "0"), addr)
    k = next(k for k in range(len(code) - 5) if code[k] == 0xE8 and code[k + 1:k + 5] == bytes(4))
    pop_va = addr + k + 5
    code = L.asm(src.replace("DELTA", "0x%X" % ((G - pop_va) & 0xFFFFFFFF)), addr)
    assert code[k] == 0xE8 and code[k + 1:k + 5] == bytes(4)
    return bytes(code)


def make_caves():
    TC = ZONE_LO
    tc = _asm_pic(f"""
        cmp  dword ptr [ebx], eax
        jge  _out
        mov  dword ptr [ebx], eax
        push edx
        mov  edx, [esp+0xC]
        push ecx
        call _p
    _p:
        pop  ecx
        add  ecx, DELTA
        mov  [ecx], ebx
        mov  [ecx+4], eax
        mov  [ecx+8], edx
        pop  ecx
        pop  edx
    _out:
        jmp  0x{T_RET:X}
    """, TC)
    QC = (TC + len(tc) + 0xF) & ~0xF
    qc = _asm_pic(f"""
        push ecx
        call _p
    _p:
        pop  ecx
        add  ecx, DELTA
        mov  dword ptr [ecx], 0
        pop  ecx
        lea  eax, [esp+0xC]
        push eax
        jmp  0x{Q_RET:X}
    """, QC)
    RC = (QC + len(qc) + 0xF) & ~0xF
    rc = _asm_pic(f"""
        mov  dword ptr [ebp+0x28], eax
        mov  dword ptr [ebp+0x2C], 0xFFFFFFFF
        pushad
        call _p
    _p:
        pop  esi
        add  esi, DELTA
        lea  edi, [esp+0x2C]
        cmp  [esi], edi
        jne  _clr
        mov  ecx, [edi]
        cmp  ecx, [esi+4]
        jne  _clr
        mov  eax, [ebx+0x24C]
        test eax, eax
        jz   _clr
        mov  eax, [eax+0xC]
        test eax, eax
        jz   _clr
        cmp  eax, [esi+8]
        jne  _clr
        call 0x{GROUP_MP:X}
        test eax, eax
        jle  _clr
        mov  ecx, eax
        mov  eax, [esp+0x1C]
        dec  eax
        cdq
        idiv ecx
        test eax, eax
        jle  _clr
        cmp  eax, {MAXT}
        jg   _clr
        imul eax, eax, {PEN}
        add  [edi], eax
    _clr:
        mov  dword ptr [esi], 0
        popad
        jmp  0x{R_RET:X}
    """, RC)
    assert RC + len(rc) <= ZONE_HI
    return [(TC, tc), (QC, qc), (RC, rc)]


def jmp(src, dst, n):
    return b"\xE9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (n - 5)


def edits():
    (tca, tc), (qca, qc), (rca, rc) = make_caves()
    blob_lo = tca
    blob = bytearray(rca + len(rc) - blob_lo)
    for a, c in ((tca, tc), (qca, qc), (rca, rc)):
        blob[a - blob_lo:a - blob_lo + len(c)] = c
    return [(blob_lo, bytes(len(blob)), bytes(blob), "caves TC/QC/RC"),
            (T_SITE, T_ORIG, jmp(T_SITE, tca, 6), "T cave_target tail -> TC"),
            (Q_SITE, Q_ORIG, jmp(Q_SITE, qca, 5), "Q finder state-2 query -> QC"),
            (R_SITE, R_ORIG, jmp(R_SITE, rca, 10), "R finder record cost -> RC")]


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
    for va, ob, nb, nm in E:
        bad = [r for r in rel if va - 3 <= r < va + len(nb)]
        assert not bad, "reloc under %s: %s" % (nm, [hex(x) for x in bad])
    st = []
    for va, ob, nb, nm in E:
        c = bytes(d[va - D:va - D + len(nb)])
        s = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        st.append(s)
        print("  %-34s @0x%08X  %s (%d B)" % (nm, va, s, len(nb)))
    print("  G 0x%08X (.idata page slack, runtime zero)  maxT %d  pen %d" % (G, MAXT, PEN))
    if "FOREIGN" in st:
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
    bk = bak_path(dll, ".bak_aireach")
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
    print("written and verified: AI groups travel up to %d turns for ground items a hero of theirs would take" % MAXT)
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    sys.exit(main(a[0] if a else None))
