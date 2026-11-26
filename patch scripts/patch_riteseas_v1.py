"""
RITE OF THE SEAS (spell 221, Water tier 2) - global enchantment (2026-10-17).  AoWEPACK.dll only.

Spec (user): global spell, research 90, cost 50, upkeep 10.  "Shipyard productions spawn with Silver Medal."

v2 (2026-10-17, user: "make it so that it reduces base income of shipyards by 1 while active. make sure income updates
correctly like our other spells"):
  * INCOME: every TProductionPlace reports its per-turn gold through VMT+0x1F4 = 0x557BE500 (Steam Power's x2 cave
    0x5585C160 sits in that slot for shipyards + guilds), which starts from the BASE income VMT+0x22C = 0x557BE4E0
    (5 gold, 0 when razed/inactive: [obj+0x48] == 1 or 0x5575F008), then x1.5 in one case.  v2 re-points the TShipyard
    slot only (0x557C715C + 0x22C = 0x557C7388, reloc'd; the Builders' Guild has its own slot 0x557CA308, untouched)
    to cave `si`: call the previous target; if > 0 and the owner [place+0x30] (0xFF = none) has an ACTIVE marker-221
    enchantment -> -1 (never below 0, since only a positive base is reduced).  The x1.5 / Steam Power x2 then apply to
    the reduced base (5 -> 4 -> 8 with Steam Power).  Recomputed on every read (payout + treasury line).
  * DISPLAY: TPlayer.UpdateIncome 0x55751F88 caches the sum in [player+0xD0]; as in Depths of Plenty v2 the Activate /
    Deactivate wrappers (marker 221 only) re-run it for the caster ([ench+0x19]) after the base routine, so the income
    line changes the moment the spell is cast or ends.
  * Upgrade: --apply on a v1 DLL un-applies v1 in memory from the zone header (exact pre-apply bytes) and applies v2
    (backup .bak_riteseas2 = the v1 state); zone magic "RTS2" (v1 "RTS1"); --revert works from either version.

RE - production:
  Units are produced by TProductionControl (VMT 0x5570A784) descendants: TCityProductionControl (VMT 0x557A6D34,
  cities) and TProductionPlaceControl (VMT 0x557BD4D0, the map production places = TProductionPlace subclasses
  TShipyard VMT 0x557C715C and TBuildersGuild VMT 0x557CA0DC).  "Shipyard production" = a unit produced by a
  TProductionPlaceControl whose place [ctl+0x28] is a TShipyard (GetOwner VMT+0x7C = [[ctl+0x28]+0x30]).
  The production START (0x5575D118, item type 1) calls VMT+0x9C CreateUnit(ctl, item index) and keeps the TUnit in
  the running production [[ctl+0x24]+0x24] until it is delivered; base CreateUnit 0x5575D588 = Create TUnit +
  SetResource.  TCityProductionControl overrides +0x9C (0x557A8DA0) and applies Warmonger's rank right there
  (cave_warmonger 0x5580FF60 -> cave_arenaxp 0x5580FF20) - Rite of the Seas uses the same point and XP writer.
  Medals are pure XP: TUnit.GetRank 0x5578294C, XP byte [unit+0x3C] >= 10 Silver, >= 20 Gold.  cave_arenaxp
  (eax = unit, dl = target XP) writes the XP and applies the crossed ranks' ability owners ([res+0x38+rank*4]);
  then TUnit.Changed (VMT+0x90) - exactly what Warmonger does for Gold.
EFFECT: slot 0x557BD56C (TProductionPlaceControl +0x9C, reloc'd, vanilla = 0x5575D588) -> cave `pr`: call prev; if
  the place is a TShipyard (VMT compare, PIC) owned by a player with an ACTIVE marker-221 enchantment and the new unit
  has < 10 XP -> 10 XP (Silver).  A unit whose production started before the cast stays unranked (it was created
  then); the medal shows in the production panel from the start.  Builders' Guild / city production unchanged.

GLOBAL PLUMBING - Earth Mastery donor with marker 221, a copy of patch_depthsofplenty_v1.py's (itself chained in
front of Golden Age), CHAINED IN FRONT of whatever sits at the Earth Mastery sites now (Depths of Plenty's caves on
the live DLL; vanilla sites get replay stubs).  Sites CE/MM/EV/PS/ID + slots emAct/emDeact/emChk as Depths (see that
script); Activate/Deactivate = the base TGlobalEnchantment routines; CHK refuses a second active 221; EV/PS/ID mark the
map-wide particle 0xDD (= 221 & 0xFF) so slot 0 of Rite of the Seas' OWN Spells.pfs record is drawn.

While this is applied, patch_depthsofplenty_v1.py (and through it Golden Age) sees its sites as OTHER -> revert in
LIFO order: this one first.

Zone 0x55878800..0x55879000 (zero, reloc-free).  Header: +0 "RTS1", +0x10 5 x 8 B saved site bytes, +0x38 4 dwords
saved slots (emAct emDeact emChk prod), caves from +0x50 (PIC via call/pop delta for in-image addresses).
Dry-run default; --apply / --revert / --dis; --dll <path> = work on another copy (scratch tests).
Backup <game>\\backup\\AoWEPACK.dll.bak_riteseas.
Pipeline entry (patch_dual_sphere_spells_v1.py): donor "TEarthMastery", pfs_donor 74, tc_type None, sphere 6 (Water),
tier 2, mana 50, research 90, upkeep 10, pokes [(0x34, 4, 0xFFFFFFFF)] (AI never casts) - see _riteseas_integration.txt.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BASE = 0x55700000
ZONE, ZONE_END = 0x55878800, 0x55879000
MAGIC, MAGIC_V1, HDR_SITES, HDR_SLOTS, CAVES = b"RTS2", b"RTS1", 0x10, 0x38, 0x50
SPELL_ID, EM_ID, FX_MARK = 221, 0x40, 0xDD

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
BASE_ACT, BASE_DEACT, BASE_CHK = 0x5577DBA0, 0x5577DC3C, 0x5577DAE8
EM_ACT, EM_DEACT, EM_CHK, EM_CHK_MSG, EM_CHK_SEH = 0x557F3370, 0x557F3410, 0x557F32AC, 0x557F3303, 0x557F335F
EM_ENCH_CREATE, EM_ENCH_CELL = 0x557F3204, 0x557EF318
MASTERY_MSG, LSTRASG, WORLD_EVENT = 0x557EF7C0, 0x55701150, 0x55779068
PROD_CREATE = 0x5575D588          # TProductionControl.CreateUnit (VMT+0x9C; eax = control, edx = production item index)
SHIPYARD_VMT = 0x557C715C         # TShipyard (TProductionPlace subclass; TBuildersGuild = 0x557CA0DC)
ARENA_XP = 0x5580FF20             # cave_arenaxp (patch_arena_xp_v1.py): eax = unit, dl = target XP -> [unit+0x3C] + rank-up abilities
SILVER_XP = 10                    # TUnit.GetRank: XP >= 10 silver, >= 20 gold
PLACE_BASE_INC = 0x557BE4E0       # TProductionPlace base income (VMT+0x22C): 5 gold, 0 when razed / inactive
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
    ("prod", 0x557BD56C, PROD_CREATE, "pr"),      # TProductionPlaceControl VMT 0x557BD4D0 + 0x9C (inherited base CreateUnit)
    ("shipinc", 0x557C7388, PLACE_BASE_INC, "si"),  # v2: TShipyard VMT 0x557C715C + 0x22C (base income)
]
SLOTS_V1 = SLOTS[:4]

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
    Returns the whole zone image (header + caves) and the cave VAs.  ver 1 rebuilds the v1 image (upgrade check)."""
    slots = SLOTS if ver >= 2 else SLOTS_V1
    out = bytearray(CAVES); out[0:4] = MAGIC if ver >= 2 else MAGIC_V1; where = {}
    for k, (nm, _va, orig, _kind, _c) in enumerate(SITES):
        out[HDR_SITES + 8 * k:HDR_SITES + 8 * k + len(orig)] = saved_sites[nm]
    for k, (nm, _sva, _orig, _c) in enumerate(slots):
        struct.pack_into("<I", out, HDR_SLOTS + 4 * k, saved_slots[nm])
    C = {"id": SPELL_ID, "emid": EM_ID, "mark": FX_MARK, "map": MAP_GLOBAL, "get": LIST_GET, "bact": BASE_ACT,
         "bdeact": BASE_DEACT, "bchk": BASE_CHK, "emmsg": EM_CHK_MSG, "emseh": EM_CHK_SEH, "emcreate": EM_ENCH_CREATE,
         "emcell": EM_ENCH_CELL, "mmsg": MASTERY_MSG, "lstrasg": LSTRASG, "wev": WORLD_EVENT,
         "shipvmt": SHIPYARD_VMT, "arenaxp": ARENA_XP, "silver": SILVER_XP, "getpl": GET_PLAYER,
         "updinc": UPDATE_INCOME}

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
    for nm, _sva, _orig, _c in slots:
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
    # PR: TProductionPlaceControl.CreateUnit wrapper (VMT+0x9C; eax = control, edx = item index) -> call the previous
    # target (creates the TUnit of the production that is starting; the same object is delivered when it completes -
    # the City override 0x557A8DA0 applies Warmonger's rank at exactly this point too).  If the place [ctl+0x28] is a
    # TShipyard owned ([place+0x30] != 0xFF) by a player with an ACTIVE marker-221 enchantment and the unit has < 10 XP,
    # set it to 10 XP = Silver through cave_arenaxp (writes [unit+0x3C] + applies the Silver ability owner) and call
    # TUnit.Changed (VMT+0x90).  Synced state only -> MP-safe.
    place("pr", """
        push ebx
        push esi
        push edi
        mov edi, eax
        call %(pprod)#x
        mov esi, eax
        test esi, esi
        jz pr_out
        mov ecx, [edi+0x28]
        test ecx, ecx
        jz pr_out
        call $D
        pop ebx
        sub ebx, $D
        lea edx, [ebx+%(shipvmt)#x]
        cmp dword ptr [ecx], edx
        jne pr_out
        mov dl, byte ptr [ecx+0x30]
        cmp dl, 0xff
        je pr_out
        mov ecx, %(id)d
        call %(gxa)#x
        test al, al
        jz pr_out
        cmp byte ptr [esi+0x3c], %(silver)d
        jae pr_out
        mov eax, esi
        mov dl, %(silver)d
        call %(arenaxp)#x
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x90]
    pr_out:
        mov eax, esi
        pop edi
        pop esi
        pop ebx
        ret
    """, pic=True)
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
        # that the treasury line / turn payout read) - as Depths of Plenty v2.  eax/ecx/edx volatile.
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
        # SI: TShipyard base income (VMT+0x22C; eax = the shipyard) -> previous target; a positive base of a
        # shipyard owned ([obj+0x30] != 0xFF) by a player with an ACTIVE marker-221 enchantment loses 1 gold.
        place("si", """
            push ebx
            mov ebx, eax
            call %(pshipinc)#x
            test eax, eax
            jle si_out
            cmp byte ptr [ebx+0x30], 0xff
            je si_out
            push eax
            mov dl, byte ptr [ebx+0x30]
            mov ecx, %(id)d
            call %(gxa)#x
            test al, al
            pop eax
            jz si_out
            dec eax
        si_out:
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
        slots_v = SLOTS if ver >= 2 else SLOTS_V1
        saved_sites = {nm: zl[HDR_SITES + 8 * k:HDR_SITES + 8 * k + len(o)] for k, (nm, _va, o, _k, _c) in enumerate(SITES)}
        saved_slots = {nm: struct.unpack_from("<I", zl, HDR_SLOTS + 4 * k)[0] for k, (nm, *_r) in enumerate(slots_v)}
        code, where = build(saved_sites, saved_slots, ver)
        st = {nm: "ours" if live_sites[nm] == hook_bytes(va, o, kind, where[c]) else "OTHER" for nm, va, o, kind, c in SITES}
        st.update({nm: "ours" if live_slots[nm] == where[c] else "OTHER(%#x)" % live_slots[nm] for nm, _s, _o, c in slots_v})
        zok = zl[:len(code)] == code and not any(zl[len(code):])
        print("state: applied v%d | zone %s (%d B) | %s" % (ver, "ours" if zok else "DIFFERS", len(code), st))
        if a.dis: dis(code, where)
        if not zok or any(v != "ours" for v in st.values()):
            print("ABORT (something chained in front of us or the zone changed - revert that first)"); return 1
        # un-apply in memory (exact: the header holds the pre-apply bytes)
        for nm, va, o, _k, _c in SITES: d[foff(d, va):foff(d, va) + len(o)] = saved_sites[nm]
        for nm, sva, _o, _c in slots_v: struct.pack_into("<I", d, foff(d, sva), saved_slots[nm])
        d[zo:zo + ZONE_END - ZONE] = bytes(ZONE_END - ZONE)
        if a.revert:
            with open(DLL, "r+b") as f: f.write(bytes(d))
            print("reverted (sites/slots restored to their pre-apply bytes)"); return 0
        if ver >= 2: print("already applied (v2)"); return 0
        print("v1 applied -> in-place upgrade to v2 (shipyard base income -1 while active; Activate/Deactivate refresh the caster's income)")
        upgrade = True
        saved_slots["shipinc"] = live_slots["shipinc"]
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
    suf = ".bak_riteseas2" if upgrade else ".bak_riteseas"     # .bak_riteseas2 = the v1 state
    bak = DLL + suf if a.dll else bak_path(DLL, suf)
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
