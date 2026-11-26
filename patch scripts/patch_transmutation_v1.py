"""
TRANSMUTATION (spell 235, Secret tier 4) - global enchantment.  AoWEPACK.dll.

Spec (user 2026-10-18): global spell, research 300, cost 75, upkeep 25.  "Research points become gold income (halts
research)."

RE - the power split (TPlayerMagicControl = [player+0x54]; [mc+0x10] = the player; [mc+0x2C] = the research % slider):
  GetNetPower 0x5577CEC4 -> GetNetPowerToResearch 0x5577CF80 (= NetPower * [mc+0x2C] / 100) and GetNetPowerToMana
  0x5577CEE4 (= NetPower - research, x difficulty).  Research is consumed ONLY through GetNetPowerToResearch:
    TPlayerMagicControl.NewTurn: research progress ([mc+0x38] -= research; via the caster-ability cave 0x55816A90) and,
      with no spell selected, the research share is ADDED TO MANA (0x5577CE08 / 0x5577CE14);
    GetResearchTurnsLeft 0x5577CFD8 (spellbook / power window; research 0 -> 999 turns, no division);
    TResearchSpellAIPA (AI), AoWx.exe's power window (through the IAT).
  Gold income: TPlayer.UpdateIncome 0x55751F88 sums the income sources into the cached [player+0xD0] (difficulty
  multipliers last, 0x55751FC6..0x55752041); the turn payout (TTurnPlayerControl @0x5575542E -> mod cave 0x55828270)
  re-runs UpdateIncome and adds [player+0xD0] -> the income is recomputed every turn.

EFFECT: while player P (index [player+0xA6] = the enchantment caster byte [ench+0x19]) has an ACTIVE Transmutation:
  * RES - entry hook on GetNetPowerToResearch (6 B push ebx / push ecx / mov ebx,eax / mov eax,ebx): returns 0 for P,
    EXCEPT when called from GetNetPowerToMana (return address 0x5577CEF9, compared PIC) -> research is halted
    everywhere (progress, the no-research->mana path, turns-left 999, AI, power window) while the mana share stays
    exactly what it was (mana = power - the REAL research share).
  * INC - UpdateIncome tail hook at 0x55752047 (6 B cmp dword [ebx+8],0 / jne +0A): [player+0xD0] += the REAL
    research points (res_orig = the replayed vanilla body) -> the treasury line and the turn payout get them as gold.
  * PCS - TPlayerMagicControl.ExecuteChangePowerSettings 0x5577D4D0 (8 B mov [eax+0x2C],edx / call Update): after the
    slider moves, P's income is re-summed so the treasury line follows the research share immediately.
  * Activate / Deactivate (emAct/emDeact slots) re-run P's UpdateIncome (as Depths of Plenty v2 / Rite of the Seas v2).
  Deterministic, synced state only (MP-safe).

GLOBAL PLUMBING - Earth Mastery donor with marker 235 (copy of patch_riteseas_v1.py's), CHAINED IN FRONT of whatever
sits at the Earth Mastery sites / slots (live: Royal Ambition); vanilla sites get replay stubs.  CHK refuses a second
active 235; EV/PS/ID mark the map-wide particle 0xEB (= 235 & 0xFF) so slot 0 of Transmutation's OWN Spells.pfs record
is drawn.  LIFO: transmutation -> royal -> rite -> depths -> goldenage (revert this one first).

Zone 0x55881000..0x55881800 (zero, reloc-free).  Header: +0 "TRM1", +0x10 8 x 8 B saved site bytes, +0x50 3 dwords
saved slots, caves from +0x60 (PIC via call/pop delta for in-image addresses).
Dry-run default; --apply / --revert / --dis; --dll <path> = work on another copy (scratch tests).
Backup <game>\\backup\\AoWEPACK.dll.bak_transmute.
Pipeline entry (patch_dual_sphere_spells_v1.py): donor "TEarthMastery", pfs_donor 74, tc_type None, sphere 7 (Secret),
tier 4, mana 75, research 300, upkeep 25, pokes [(0x34, 4, 0xFFFFFFFF)] (AI never casts) - see
_transmutation_integration.txt.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BASE = 0x55700000
ZONE, ZONE_END = 0x55881000, 0x55881800
MAGIC, HDR_SITES, HDR_SLOTS, CAVES = b"TRM1", 0x10, 0x50, 0x60
SPELL_ID, EM_ID, FX_MARK = 235, 0x40, 0xEB

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
BASE_ACT, BASE_DEACT, BASE_CHK = 0x5577DBA0, 0x5577DC3C, 0x5577DAE8
EM_ACT, EM_DEACT, EM_CHK, EM_CHK_MSG, EM_CHK_SEH = 0x557F3370, 0x557F3410, 0x557F32AC, 0x557F3303, 0x557F335F
EM_ENCH_CREATE, EM_ENCH_CELL = 0x557F3204, 0x557EF318
MASTERY_MSG, LSTRASG, WORLD_EVENT = 0x557EF7C0, 0x55701150, 0x55779068
GET_PLAYER, UPDATE_INCOME = 0x557544D0, 0x55751F88     # TPlayerList item (eax = [map+0x140], edx = idx) / TPlayer.UpdateIncome
RES, RES_RESUME, RES_FROM_MANA = 0x5577CF80, 0x5577CF86, 0x5577CEF9   # GetNetPowerToResearch / after its 6 B prologue / ret addr in GetNetPowerToMana
INC, INC_JNE, INC_FALL = 0x55752047, 0x55752057, 0x5575204D      # UpdateIncome tail: cmp [ebx+8],0 / jne target / fall-through
PCS, MC_UPDATE = 0x5577D4D0, 0x5577D248                          # ExecuteChangePowerSettings / TPlayerMagicControl.Update
PLAYER_MC, PLAYER_IDX, PLAYER_INCOME = 0x54, 0xA6, 0xD0

SITES = [   # name, VA, vanilla bytes, hook kind, our cave
    ("CE", 0x557F373C, bytes.fromhex("33c9b201a1"), "jmp", "ce"),
    ("MM", 0x557F36D9, bytes.fromhex("e8e2c0ffff"), "call", "mm"),
    ("EV", 0x557F3712, bytes.fromhex("b209e84f59f8ff"), "call", "ev"),
    ("PS", 0x557969B5, bytes.fromhex("8bd8b80c000000"), "call", "ps"),
    ("ID", 0x557971A4, bytes.fromhex("ba40000000"), "call", "id_"),
    ("RES", RES, bytes.fromhex("53518bd88bc3"), "jmp", "res"),
    ("INC", INC, bytes.fromhex("837b0800750a"), "jmp", "inc"),
    ("PCS", PCS, bytes.fromhex("89502ce870fdffff"), "jmp", "pcs"),
]
OWN = ("RES", "INC", "PCS")                   # sites we own outright (must be vanilla before us; their bytes are replayed)
SLOTS = [   # name, slot VA, vanilla target, our cave
    ("emAct", 0x557EF3C0, EM_ACT, "ac"),
    ("emDeact", 0x557EF3B8, EM_DEACT, "de"),
    ("emChk", 0x557EF3BC, EM_CHK, "chk"),
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


def build(saved_sites, saved_slots):
    """saved_sites: name -> the site's bytes before us; saved_slots: name -> the slot's value before us.
    Returns the whole zone image (header + caves) and the cave VAs."""
    out = bytearray(CAVES); out[0:4] = MAGIC; where = {}
    for k, (nm, _va, orig, _kind, _c) in enumerate(SITES):
        out[HDR_SITES + 8 * k:HDR_SITES + 8 * k + len(orig)] = saved_sites[nm]
    for k, (nm, _sva, _orig, _c) in enumerate(SLOTS):
        struct.pack_into("<I", out, HDR_SLOTS + 4 * k, saved_slots[nm])
    C = {"id": SPELL_ID, "emid": EM_ID, "mark": FX_MARK, "map": MAP_GLOBAL, "get": LIST_GET, "bact": BASE_ACT,
         "bdeact": BASE_DEACT, "bchk": BASE_CHK, "emmsg": EM_CHK_MSG, "emseh": EM_CHK_SEH, "emcreate": EM_ENCH_CREATE,
         "emcell": EM_ENCH_CELL, "mmsg": MASTERY_MSG, "lstrasg": LSTRASG, "wev": WORLD_EVENT, "getpl": GET_PLAYER,
         "updinc": UPDATE_INCOME, "resres": RES_RESUME, "frommana": RES_FROM_MANA, "incjne": INC_JNE,
         "incfall": INC_FALL, "mcupd": MC_UPDATE, "pmc": PLAYER_MC, "pidx": PLAYER_IDX, "pinc": PLAYER_INCOME}

    def place(name, src, pic=False):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        d = dict(C, **where)
        out.extend(asm_pic(src % d, va) if pic else bytes(ks.asm(src % d, va)[0]))

    prev = {}
    for nm, va, orig, kind, _c in SITES:
        if nm in OWN: continue
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
    # res_orig: the vanilla GetNetPowerToResearch (prologue replayed) = the REAL research share; eax = mc
    place("res_orig", """
        push ebx
        push ecx
        mov ebx, eax
        mov eax, ebx
        jmp %(resres)#x
    """)
    # RES: GetNetPowerToResearch entry (jmp'ed to; eax = the TPlayerMagicControl).  Its owner [mc+0x10] has an ACTIVE
    # Transmutation and the caller is not GetNetPowerToMana -> 0 (research halted); else the vanilla body.
    place("res", """
        pushal
        mov esi, eax
        mov eax, [esi+0x10]
        test eax, eax
        jz res_pass
        call $D
        pop ebx
        sub ebx, $D
        mov ecx, [esp+0x20]
        sub ecx, ebx
        cmp ecx, %(frommana)#x
        je res_pass
        mov dl, byte ptr [eax+%(pidx)#x]
        cmp dl, 0xff
        je res_pass
        mov ecx, %(id)d
        call %(gxa)#x
        test al, al
        jz res_pass
        popal
        xor eax, eax
        ret
    res_pass:
        popal
        jmp %(res_orig)#x
    """, pic=True)
    # INC: TPlayer.UpdateIncome tail (jmp'ed to from 0x55752047; ebx = the player, [ebx+0xD0] = the summed income).
    # ACTIVE Transmutation -> [ebx+0xD0] += the REAL research share (res_orig on [player+0x54]); then the replayed
    # cmp dword [ebx+8],0 / jne 0x55752057.
    place("inc", """
        pushal
        mov dl, byte ptr [ebx+%(pidx)#x]
        cmp dl, 0xff
        je inc_out
        mov ecx, %(id)d
        call %(gxa)#x
        test al, al
        jz inc_out
        mov eax, [ebx+%(pmc)#x]
        test eax, eax
        jz inc_out
        call %(res_orig)#x
        test eax, eax
        jle inc_out
        add [ebx+%(pinc)#x], eax
    inc_out:
        popal
        cmp dword ptr [ebx+8], 0
        jne inc_jne
        jmp %(incfall)#x
    inc_jne:
        jmp %(incjne)#x
    """)
    # upd: edx = player index -> TPlayer.UpdateIncome (as Rite of the Seas v2)
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
    # PCS: ExecuteChangePowerSettings (jmp'ed to; eax = mc, edx = the new research %): the replayed body, then an
    # ACTIVE Transmutation re-sums the owner's income (the research share just changed).  Returns al = 1.
    place("pcs", """
        mov [eax+0x2c], edx
        push ebx
        mov ebx, eax
        call %(mcupd)#x
        mov eax, [ebx+0x10]
        test eax, eax
        jz pcs_out
        mov dl, byte ptr [eax+%(pidx)#x]
        cmp dl, 0xff
        je pcs_out
        mov ecx, %(id)d
        call %(gxa)#x
        test al, al
        jz pcs_out
        mov eax, [ebx+0x10]
        call %(updinc)#x
    pcs_out:
        pop ebx
        mov al, 1
        ret
    """)
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

    if zl[:4] == MAGIC:     # applied - rebuild from the saved header and compare
        saved_sites = {nm: zl[HDR_SITES + 8 * k:HDR_SITES + 8 * k + len(o)] for k, (nm, _va, o, _k, _c) in enumerate(SITES)}
        saved_slots = {nm: struct.unpack_from("<I", zl, HDR_SLOTS + 4 * k)[0] for k, (nm, *_r) in enumerate(SLOTS)}
        code, where = build(saved_sites, saved_slots)
        st = {nm: "ours" if live_sites[nm] == hook_bytes(va, o, kind, where[c]) else "OTHER" for nm, va, o, kind, c in SITES}
        st.update({nm: "ours" if live_slots[nm] == where[c] else "OTHER(%#x)" % live_slots[nm] for nm, _s, _o, c in SLOTS})
        zok = zl[:len(code)] == code and not any(zl[len(code):])
        print("state: applied | zone %s (%d B) | %s" % ("ours" if zok else "DIFFERS", len(code), st))
        if a.dis: dis(code, where)
        if not zok or any(v != "ours" for v in st.values()):
            print("ABORT (something chained in front of us or the zone changed - revert that first)"); return 1
        if not a.revert: print("already applied"); return 0
        for nm, va, o, _k, _c in SITES: d[foff(d, va):foff(d, va) + len(o)] = saved_sites[nm]
        for nm, sva, _o, _c in SLOTS: struct.pack_into("<I", d, foff(d, sva), saved_slots[nm])
        d[zo:zo + ZONE_END - ZONE] = bytes(ZONE_END - ZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted (sites/slots restored to their pre-apply bytes)"); return 0

    if any(zl): print("zone not free -> ABORT"); return 1
    if a.revert: print("not applied - nothing to revert"); return 0
    st = {}
    for nm, va, o, kind, _c in SITES:
        lv = live_sites[nm]
        if lv == o: st[nm] = "vanilla"
        elif nm not in OWN and lv[0] == (0xE9 if kind == "jmp" else 0xE8) and all(b == 0x90 for b in lv[5:]):
            st[nm] = "chain->%#x" % (va + 5 + struct.unpack_from("<i", lv, 1)[0])
        else: st[nm] = "UNKNOWN"
    for nm, _s, o, _c in SLOTS:
        st[nm] = "vanilla" if live_slots[nm] == o else "chain->%#x" % live_slots[nm]
    print("state: not applied | %s" % st)
    if "UNKNOWN" in st.values(): print("ABORT (an owned site is not vanilla / unknown hook)"); return 1
    code, where = build(live_sites, live_slots)
    assert ZONE + len(code) <= ZONE_END
    print("zone %d B; caves %s" % (len(code), ", ".join("%s=%#x" % kv for kv in where.items())))
    if a.dis: dis(code, where)
    d[zo:zo + len(code)] = code
    for nm, va, o, kind, c in SITES: d[foff(d, va):foff(d, va) + len(o)] = hook_bytes(va, o, kind, where[c])
    for nm, sva, _o, c in SLOTS: struct.pack_into("<I", d, foff(d, sva), where[c])
    if not a.apply: print("Dry run OK - rerun with --apply."); return 0
    bak = DLL + ".bak_transmute" if a.dll else bak_path(DLL, ".bak_transmute")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
