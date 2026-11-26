"""
DEPTHS OF PLENTY (spell 217, Earth tier 2) - global enchantment (2026-10-17).  AoWEPACK.dll only.

Spec (user): global spell, research 90, cost 50, upkeep 10.  Mines produce extra gold (+1 on surface, +2 underground,
+3 in depths).

v2 (2026-10-17, user: "all my mines only increased from 5 to 6 gold on every level, and my displayed gold income
didn't update"):
  * LEVEL: v1 read [mine+0x12] - not the level on a map object (always 0 -> +1 everywhere).  The level is the
    object's field's level: TMapObject.GetLhx (HSEPack 0x556095A4) = [[obj+4]+0x12]; TPlayerStructureIncomeSource.
    GetLocation 0x55761B04 reads x/y/level through VMT+0x74/+0x78/+0x7C (= GetXhx/GetYhx/GetLhx).  v2 reads
    [[mine+4]+0x12] (null field -> surface).
  * DISPLAY: the treasury income is CACHED - TPlayer.UpdateIncome 0x55751F88 sums the income sources (+0x64 list,
    vcall +0x50 = Income -> TMine.GetIncome) into [player+0xD0] and is only re-run on Register/UnregisterIncomeSource
    (mine captured/lost) and a few game events.  v2's Activate/Deactivate wrappers (marker 217 only) call it for the
    caster ([ench+0x19] -> PlayerList 0x557544D0 on [[0x558FA040]+0x140]) after the base routine, so the line updates
    the moment the spell is cast or ends.
  * Upgrade: --apply on a v1 DLL un-applies v1 in memory from the zone header (exact pre-apply bytes) and applies v2
    (backup .bak_depths2 = the v1 state); zone magic "DOP2" (v1 "DOP1"); --revert works from either version.

EFFECT - mine income:
  Every AoW mine is a TMine (VMT 0x557B4020; the only class whose slot +0x1F4 holds TMine.GetIncome 0x557B43E4).
  GetIncome = 0 when VMT+0x150() or 0x5575F008 ([mine+0x24] != 0xFF) says so, else a flat 5 gold.  It is read by
  TPlayerStructureIncomeSource.Income 0x55761AF8 (`mov eax,[eax+8] / call [vmt+0x1F4]`) = the real per-turn payout,
  so the treasury/income line sums the same value.  AoW mines only ever make gold - nothing else to handle.
  Slot 0x557B4214 (reloc'd) re-pointed to cave `mi`: call the previous target; if the result is > 0 (an owned,
  producing mine) and the owner byte [mine+0x30] (player-list index, 0xFF = none - the same byte Golden Age's city
  test uses) has an ACTIVE marker-217 global enchantment, add min([mine+0x12], 2) + 1 (THS level byte: 0 surface /
  1 underground / 2 depths, as Town Quake reads [city+0x12]) -> 6 / 7 / 8 gold.  Recomputed on every read: a cast or a
  dispel shows at once, nothing is cached.  Synced state only -> MP-safe, no RNG.

GLOBAL PLUMBING - Earth Mastery donor with marker 217, like patch_goldenage_v1.py (302/342/398), but CHAINED IN FRONT
of whatever sits at the Earth Mastery sites now (Golden Age's caves on the live DLL; vanilla sites get replay stubs).
The previous site bytes / slot values are saved in the zone header at apply time -> exact --revert.
  CE  0x557F373C (jmp): spell 217 -> call prev (creates the TEarthMasteryEnchantment, no marker for 217), then
      [ench+0x14] := 217 (marker, serialised) and [ench+0x1C] := spell name (LStrAsg); else jmp prev.
  MM  0x557F36D9 (call): spell 217 -> skip the sphere-mastery message; else jmp prev.
  AC/DE  emAct 0x557EF3C0 / emDeact 0x557EF3B8: marker 217 -> base TGlobalEnchantment Activate/Deactivate; else prev.
  CHK emChk 0x557EF3BC: marker 217 -> base check, then "already have an ACTIVE 217" (refused through Earth Mastery's
      own message branch, prologue replayed exactly as Golden Age does); else prev.
  EV  0x557F3712 (call): call prev (the TWorldFXHS type 9), spell 217 -> mark [hs+0x25] := 0xD9 (Golden Age uses
      2/3/4, Drought 1; 0xD9 = 217 & 0xFF so a parallel fork won't collide).
  PS  0x557969B5 (call): call prev, then copy the master's mark into the particle (idempotent with Golden Age's).
  ID  0x557971A4 (call): call prev (edx = spell id to draw), mark 0xD9 -> edx = 217 -> Depths of Plenty's OWN Spells.pfs
      record slot 0 (gold glints).
  Kept from the donor: sound 0 of the spell record and the event-log line.

While this is applied, patch_goldenage_v1.py sees its sites as OTHER (chain) - revert in LIFO order (this one first).

Zone 0x5586F000..0x5586F800 (zero, reloc-free).  Header: +0 "DOP1", +0x10 5 x 8 B saved site bytes (CE MM EV PS ID),
+0x38 4 dwords saved slots (emAct emDeact emChk mine), caves from +0x50 (PIC via call/pop delta for in-image reads).
Dry-run default; --apply / --revert / --dis; --dll <path> = work on another copy (scratch tests).
Backup <game>\\backup\\AoWEPACK.dll.bak_depths.
Pipeline entry (patch_dual_sphere_spells_v1.py): donor "TEarthMastery", pfs_donor 74, tc_type None, sphere 3, tier 2,
mana 50, research 90, upkeep 10, pokes [(0x34, 4, 0xFFFFFFFF)] (AI never casts - see _depths_integration.txt).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BASE = 0x55700000
ZONE, ZONE_END = 0x5586F000, 0x5586F800
MAGIC, MAGIC_V1, HDR_SITES, HDR_SLOTS, CAVES = b"DOP2", b"DOP1", 0x10, 0x38, 0x50
SPELL_ID, EM_ID, FX_MARK = 217, 0x40, 0xD9

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
BASE_ACT, BASE_DEACT, BASE_CHK = 0x5577DBA0, 0x5577DC3C, 0x5577DAE8
EM_ACT, EM_DEACT, EM_CHK, EM_CHK_MSG, EM_CHK_SEH = 0x557F3370, 0x557F3410, 0x557F32AC, 0x557F3303, 0x557F335F
EM_ENCH_CREATE, EM_ENCH_CELL = 0x557F3204, 0x557EF318
MASTERY_MSG, LSTRASG, WORLD_EVENT = 0x557EF7C0, 0x55701150, 0x55779068
MINE_GETINC = 0x557B43E4
GET_PLAYER, UPDATE_INCOME = 0x557544D0, 0x55751F88     # TPlayerList item (eax = [map+0x140], edx = idx) / TPlayer.UpdateIncome

SITES = [   # name, VA, vanilla bytes, hook kind, our cave
    ("CE", 0x557F373C, bytes.fromhex("33c9b201a1"), "jmp", "ce"),
    ("MM", 0x557F36D9, bytes.fromhex("e8e2c0ffff"), "call", "mm"),
    ("EV", 0x557F3712, bytes.fromhex("b209e84f59f8ff"), "call", "ev"),
    ("PS", 0x557969B5, bytes.fromhex("8bd8b80c000000"), "call", "ps"),
    ("ID", 0x557971A4, bytes.fromhex("ba40000000"), "call", "id_"),
]
SLOTS = [   # name, slot VA, vanilla target, our cave
    ("emAct", 0x557EF3C0, EM_ACT, "ac"),
    ("emDeact", 0x557EF3B8, EM_DEACT, "de"),
    ("emChk", 0x557EF3BC, EM_CHK, "chk"),
    ("mine", 0x557B4214, MINE_GETINC, "mi"),
]

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_pic(src, va):
    """Assemble; every `call $D` / `pop R` / `sub R, $D` triple gets the anchor (the VA after the call) patched in."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
        s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0])
    k = 0
    while True:
        k = b.find(b"\xe8\x00\x00\x00\x00", k)
        if k < 0: break
        if 0x58 <= b[k + 5] <= 0x5F:
            if b[k + 6] == 0x2D and b[k + 7:k + 11] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 7, va + k + 5)
            elif b[k + 6] == 0x81 and b[k + 8:k + 12] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 8, va + k + 5)
        k += 5
    assert b"\xff\xff\xff\x7f" not in b, "unpatched PIC anchor"
    return bytes(b)


def build(saved_sites, saved_slots, ver=2):
    """saved_sites: name -> the site's bytes before us; saved_slots: name -> the slot's value before us.
    Returns the whole zone image (header + caves) and the cave VAs."""
    out = bytearray(CAVES); out[0:4] = MAGIC if ver >= 2 else MAGIC_V1; where = {}
    for k, (nm, _va, orig, _kind, _c) in enumerate(SITES):
        out[HDR_SITES + 8 * k:HDR_SITES + 8 * k + len(orig)] = saved_sites[nm]
    for k, (nm, _sva, _orig, _c) in enumerate(SLOTS):
        struct.pack_into("<I", out, HDR_SLOTS + 4 * k, saved_slots[nm])
    C = {"id": SPELL_ID, "emid": EM_ID, "mark": FX_MARK, "map": MAP_GLOBAL, "get": LIST_GET, "bact": BASE_ACT,
         "bdeact": BASE_DEACT, "bchk": BASE_CHK, "emmsg": EM_CHK_MSG, "emseh": EM_CHK_SEH, "emcreate": EM_ENCH_CREATE,
         "emcell": EM_ENCH_CELL, "mmsg": MASTERY_MSG, "lstrasg": LSTRASG, "wev": WORLD_EVENT,
         "getpl": GET_PLAYER, "updinc": UPDATE_INCOME}

    def place(name, src, pic=False):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        d = dict(C, **where)
        out.extend(asm_pic(src % d, va) if pic else bytes(ks.asm(src % d, va)[0]))

    # previous targets: a site still vanilla gets a replay stub; otherwise decode its call/jmp
    prev = {}
    for nm, va, orig, kind, _c in SITES:
        live = saved_sites[nm]
        if live != orig:
            prev[nm] = va + 5 + struct.unpack_from("<i", live, 1)[0]; continue
        if nm == "CE":
            place("stubCE", """
                push ebx
                call $D
                pop ebx
                sub ebx, $D
                mov eax, [ebx+%(emcell)#x]
                pop ebx
                xor ecx, ecx
                mov dl, 1
                jmp %(emcreate)#x
            """, pic=True)
        elif nm == "MM":
            where["stubMM"] = MASTERY_MSG
        elif nm == "EV":
            place("stubEV", "mov dl, 9\njmp %(wev)#x")
        elif nm == "PS":
            place("stubPS", "mov ebx, eax\nmov eax, 0xc\nret")
        elif nm == "ID":
            place("stubID", "mov edx, %(emid)d\nret")
        prev[nm] = where["stub" + nm]
    for nm, _sva, _orig, _c in SLOTS:
        prev[nm] = saved_slots[nm]
    C.update({"p" + k: v for k, v in prev.items()})

    # gxa: dl = player index, ecx = marker -> al = 1 if that player has an ACTIVE global enchantment with that
    # marker; all other regs preserved (copy of Golden Age's scanner)
    place("gxa", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        push ebp
        movsx edi, dl
        mov ebp, ecx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(map)#x]
        test eax, eax
        jz gxa_no
        mov eax, [eax+0x188]
        test eax, eax
        jz gxa_no
        mov esi, [eax+0x14]
        test esi, esi
        jz gxa_no
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    gxa_lp:
        dec ecx
        js gxa_no
        push ecx
        mov eax, esi
        mov edx, ecx
        call %(get)#x
        pop ecx
        test eax, eax
        jz gxa_lp
        cmp dword ptr [eax+0x14], ebp
        jne gxa_lp
        test byte ptr [eax+0x10], 1
        jz gxa_lp
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        jne gxa_lp
        mov eax, 1
        jmp gxa_out
    gxa_no:
        xor eax, eax
    gxa_out:
        pop ebp
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """, pic=True)
    LVL = {1: "movzx edx, byte ptr [ebx+0x12]",                   # v1 bug: [mine+0x12] is not the level -> always +1
           2: "mov edx, [ebx+4]\n test edx, edx\n jz mi_add\n movzx edx, byte ptr [edx+0x12]"}   # v2: GetLhx = [[obj+4]+0x12]
    # MI: TMine.GetIncome wrapper (VMT+0x1F4; eax = mine) -> + min(level, 2) + 1 under an active 217 of the owner
    place("mi", """
        push ebx
        mov ebx, eax
        call %(pmine)#x
        test eax, eax
        jle mi_out
        mov dl, byte ptr [ebx+0x30]
        cmp dl, 0xff
        je mi_out
        push ecx
        push eax
        mov ecx, %(id)d
        call %(gxa)#x
        test al, al
        pop eax
        pop ecx
        jz mi_out
        %(lvl)s
        cmp edx, 2
        jbe mi_add
        mov edx, 2
    mi_add:
        lea eax, [eax+edx+1]
    mi_out:
        pop ebx
        ret
    """.replace("%(lvl)s", LVL[ver]))
    # CE (jmp'ed to; eax = spell): ours -> prev creates the enchantment, then marker + name
    place("ce", """
        cmp dword ptr [eax+0x10], %(id)d
        jne ce_prev
        push eax
        call %(pCE)#x
        pop edx
        mov dword ptr [eax+0x14], %(id)d
        push eax
        lea eax, [eax+0x1c]
        mov edx, [edx+8]
        call %(lstrasg)#x
        pop eax
        ret
    ce_prev:
        jmp %(pCE)#x
    """)
    place("mm", """
        cmp dword ptr [esi+0x10], %(id)d
        je mm_skip
        jmp %(pMM)#x
    mm_skip:
        ret
    """)
    if ver < 2:
        place("ac", """
            cmp dword ptr [eax+0x14], %(id)d
            je ac_ours
            jmp %(pemAct)#x
        ac_ours:
            jmp %(bact)#x
        """)
        place("de", """
            cmp dword ptr [eax+0x14], %(id)d
            je de_ours
            jmp %(pemDeact)#x
        de_ours:
            jmp %(bdeact)#x
        """)
    else:
        # upd: edx = player index -> TPlayer.UpdateIncome (re-sums the income sources into the cached [player+0xD0]
        # that the treasury line / turn payout read).  Delphi register convention: eax/ecx/edx volatile.
        place("upd", """
            push ebx
            call $D
            pop ebx
            sub ebx, $D
            mov eax, [ebx+%(map)#x]
            test eax, eax
            jz upd_out
            mov eax, [eax+0x140]
            test eax, eax
            jz upd_out
            call %(getpl)#x
            test eax, eax
            jz upd_out
            call %(updinc)#x
        upd_out:
            pop ebx
            ret
        """, pic=True)
        place("ac", """
            cmp dword ptr [eax+0x14], %(id)d
            je ac_ours
            jmp %(pemAct)#x
        ac_ours:
            push ebx
            mov ebx, eax
            call %(bact)#x
            push eax
            movsx edx, byte ptr [ebx+0x19]
            call %(upd)#x
            pop eax
            pop ebx
            ret
        """)
        place("de", """
            cmp dword ptr [eax+0x14], %(id)d
            je de_ours
            jmp %(pemDeact)#x
        de_ours:
            push ebx
            movsx ebx, byte ptr [eax+0x19]
            call %(bdeact)#x
            push eax
            mov edx, ebx
            call %(upd)#x
            pop eax
            pop ebx
            ret
        """)
    # CHK: eax = ench, dl = player, ecx = &message; returns al (1 = may cast)
    place("chk", """
        cmp dword ptr [eax+0x14], %(id)d
        je chk_ours
        jmp %(pemChk)#x
    chk_ours:
        push eax
        push ecx
        push edx
        call %(bchk)#x
        test al, al
        pop edx
        pop ecx
        pop eax
        jnz chk_base_ok
        xor eax, eax
        ret
    chk_base_ok:
        push eax
        push ecx
        mov ecx, [eax+0x14]
        call %(gxa)#x
        test al, al
        pop ecx
        pop eax
        jnz chk_refuse
        mov eax, 1
        ret
    chk_refuse:
        push ebp
        mov ebp, esp
        add esp, -0x14
        push ebx
        push esi
        push edi
        xor ebx, ebx
        mov [ebp-8], ebx
        mov [ebp-0xc], ebx
        mov edi, ecx
        mov [ebp-1], dl
        mov esi, eax
        call $D
        pop eax
        sub eax, $D
        add eax, %(emseh)#x
        push ebp
        push eax
        xor eax, eax
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        jmp %(emmsg)#x
    """, pic=True)
    # EV (called; esi = spell): prev makes the TWorldFXHS (eax), ours marks it
    place("ev", """
        call %(pEV)#x
        cmp dword ptr [esi+0x10], %(id)d
        jne ev_done
        mov byte ptr [eax+0x25], %(mark)d
    ev_done:
        ret
    """)
    # PS (called): prev (mov ebx,eax / mov eax,0xC), then the particle ebx inherits the master's mark ([ebp-4])
    place("ps", """
        call %(pPS)#x
        push ecx
        mov ecx, [ebp-4]
        mov cl, byte ptr [ecx+0x25]
        mov byte ptr [ebx+0x25], cl
        pop ecx
        ret
    """)
    # ID (called; [ebp-4] = the particle): prev picks edx, ours overrides for our mark
    place("id_", """
        call %(pID)#x
        push ecx
        mov ecx, [ebp-4]
        cmp byte ptr [ecx+0x25], %(mark)d
        jne id_done
        mov edx, %(id)d
    id_done:
        pop ecx
        ret
    """)
    return bytes(out), where


def relocs(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def foff(d, va):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    rva = va - BASE
    for k in range(nsec):
        vs, sva, rs, ro = struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8)
        if sva <= rva < sva + max(vs, rs): return ro + rva - sva
    raise ValueError(hex(va))


def hook_bytes(va, orig, kind, tgt):
    return (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", tgt - (va + 5)) + b"\x90" * (len(orig) - 5)


def dis(code, where):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    inv = {v: k for k, v in where.items()}
    for i in md.disasm(code[CAVES:], ZONE + CAVES):
        if i.address in inv: print("  -- %s" % inv[i.address])
        print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))


def main():
    ap = argparse.ArgumentParser()
    for f in ("--apply", "--revert", "--dis"): ap.add_argument(f, action="store_true")
    ap.add_argument("--dll", default=None); a = ap.parse_args()
    DLL = a.dll or game_file("AoWEPACK.dll")
    d = bytearray(open(DLL, "rb").read())
    zo = foff(d, ZONE); zl = bytes(d[zo:zo + ZONE_END - ZONE])
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(o) for _n, va, o, _k, _c in SITES)]
    noreloc = [nm for nm, sva, _o, _c in SLOTS if sva not in rl]
    if bad or noreloc: print("relocs in zone/sites %s | slots without reloc %s -> ABORT" % (bad, noreloc)); return 1
    live_sites = {nm: bytes(d[foff(d, va):foff(d, va) + len(o)]) for nm, va, o, _k, _c in SITES}
    live_slots = {nm: struct.unpack_from("<I", d, foff(d, sva))[0] for nm, sva, _o, _c in SLOTS}

    upgrade = False
    if zl[:4] in (MAGIC, MAGIC_V1):     # applied - rebuild from the saved header and compare
        ver = 2 if zl[:4] == MAGIC else 1
        saved_sites = {nm: zl[HDR_SITES + 8 * k:HDR_SITES + 8 * k + len(o)] for k, (nm, _va, o, _k, _c) in enumerate(SITES)}
        saved_slots = {nm: struct.unpack_from("<I", zl, HDR_SLOTS + 4 * k)[0] for k, (nm, *_r) in enumerate(SLOTS)}
        code, where = build(saved_sites, saved_slots, ver)
        st = {nm: "ours" if live_sites[nm] == hook_bytes(va, o, kind, where[c]) else "OTHER" for nm, va, o, kind, c in SITES}
        st.update({nm: "ours" if live_slots[nm] == where[c] else "OTHER(%#x)" % live_slots[nm] for nm, _s, _o, c in SLOTS})
        zok = zl[:len(code)] == code and not any(zl[len(code):])
        print("state: applied v%d | zone %s (%d B) | %s" % (ver, "ours" if zok else "DIFFERS", len(code), st))
        if a.dis: dis(code, where)
        if not zok or any(v != "ours" for v in st.values()):
            print("ABORT (something chained in front of us or the zone changed - revert that first)"); return 1
        # un-apply in memory (exact: the header holds the pre-apply bytes)
        for nm, va, o, _k, _c in SITES: d[foff(d, va):foff(d, va) + len(o)] = saved_sites[nm]
        for nm, sva, _o, _c in SLOTS: struct.pack_into("<I", d, foff(d, sva), saved_slots[nm])
        d[zo:zo + ZONE_END - ZONE] = bytes(ZONE_END - ZONE)
        if a.revert:
            with open(DLL, "r+b") as f: f.write(bytes(d))
            print("reverted (sites/slots restored to their pre-apply bytes)"); return 0
        if ver >= 2: print("already applied (v2)"); return 0
        print("v1 applied -> in-place upgrade to v2 (level = [[mine+4]+0x12]; Activate/Deactivate refresh the caster's income)")
        upgrade = True
        live_sites, live_slots, zl = saved_sites, saved_slots, bytes(ZONE_END - ZONE)

    if any(zl): print("zone not free -> ABORT"); return 1
    if a.revert: print("not applied - nothing to revert"); return 0
    st = {}
    for nm, va, o, kind, _c in SITES:
        lv = live_sites[nm]
        if lv == o: st[nm] = "vanilla"
        elif lv[0] == (0xE9 if kind == "jmp" else 0xE8) and all(b == 0x90 for b in lv[5:]):
            st[nm] = "chain->%#x" % (va + 5 + struct.unpack_from("<i", lv, 1)[0])
        else: st[nm] = "UNKNOWN"
    for nm, _s, o, _c in SLOTS:
        st[nm] = "vanilla" if live_slots[nm] == o else "chain->%#x" % live_slots[nm]
    print("state: %s | %s" % ("v1 un-applied in memory" if upgrade else "not applied", st))
    if "UNKNOWN" in st.values(): print("ABORT"); return 1
    code, where = build(live_sites, live_slots)
    assert ZONE + len(code) <= ZONE_END
    print("zone %d B; caves %s" % (len(code), ", ".join("%s=%#x" % kv for kv in where.items())))
    if a.dis: dis(code, where)
    d[zo:zo + len(code)] = code
    for nm, va, o, kind, c in SITES: d[foff(d, va):foff(d, va) + len(o)] = hook_bytes(va, o, kind, where[c])
    for nm, sva, _o, c in SLOTS: struct.pack_into("<I", d, foff(d, sva), where[c])
    if not a.apply: print("Dry run OK - rerun with --apply."); return 0
    suf = ".bak_depths2" if upgrade else ".bak_depths"     # .bak_depths2 = the v1 state
    bak = DLL + suf if a.dll else bak_path(DLL, suf)
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
