#!/usr/bin/env python3
r"""AoWx -- AI leader (and heroes) go and collect the loot of an exploration site their own army just cleared
(2026-10-20).  AoWEPACK.dll only.

User: "the orcs cleared their site with a leaderless party, then never picked up the items with their nearby
leader ... if a leaderless party clears an exploration site, that leader will prioritize picking up the items."

WHY THE LEADER IGNORED THE BAGS (static RE + probe log 10/20):
  * The AI leader's group is usually committed to its OWN CITY (probe: orc leader group, target prio 120, score
    120+75 = 195).  patch_ai_itemloot_prio_v1's 'busy group' rule (PC 0x5581F040) gives NO item answer at all to a
    group whose current target field holds a city -> the bags never even competed.
  * Even with an answer, an item scores 35..95 (+travel refund <= 3 turns) vs the 195 commitment.
  * TAIGroupTargetSelector.Score 0x5573C57C also subtracts -50/-199 ([settings+0x14]/[+0x10]) when another own group
    in mode 2 targets a field within 1 hex (0x5573C264) - i.e. the clearing party still committed to the site hex.
  (Anti-lure was NOT involved: its predicate is already 'human player ([player+0xA7]==0, the flag 83 vanilla sites
   test) AND the army holds a THero/TLeader within one turn'.)

FIX (zone 0x55835000..0x55835400 'SLL1'; table C = 16 x {key, day} at .idata slack 0x5590B420..0x5590B4A0,
MATCH dword 0x5590B4A0 - both runtime-zero, free between Wall-of-Flames diag 0x5590B400..B414 and armyhooks B500):
  REC  0x557C2A8E (5 B `mov eax,[ebx+0x3C] / mov edx,[eax]`) in TItemExplorationSite drop-loot 0x557C29E0, after
       the event object [ebp-4] got owner ([+0x10] = clearing army's owner) and site x/y/level ([+0x24..+0x26]):
       record key = x | y<<8 | level<<16 | owner<<24, day = [[0x558E9494]]+0x174 in slot (x+3y+5*level)&15.
  PRE  0x55814D7F (cave_target entry; was `jmp 0x5581C490` = antilure) -> PRE: MATCH := 0; if the bag's hex
       (TItemHS VMT +0x74/+0x78/+0x7C) + the asking group's player ([group+0x28], group = [[msg+0x10]+0xC]) hit a
       table entry no older than LIFE days -> MATCH := PRIO_LEADER if the group holds that player's leader
       ([player+0xD4]) else PRIO_HERO.  Then the antilure cave as before (human leader/hero near -> no answer).
  LP   0x55814EC0 (priority step; was `jmp 0x5581F040` = prio_v1 PC) -> LP: MATCH <> 0 -> priority := MATCH and on
       to 0x55814ECF (reach_v1 TC: write + travel refund up to 3 turns), SKIPPING prio_v1's busy rule; else PC.
       (LP is only reached when some hero of the group would take an item from the bag - cave_target's own rule.)
  SC   0x5573C60E (Score's `call 0x5573C264`, other-own-group-heads-there test) -> SC: a matching site-loot target
       for the scoring group's player -> 'no' (no -50/-199), else the original test.
  PRIO_LEADER 230 beats a committed own-city / 120-target (195) and a committed boosted site (200), stays below
  enemy-city answers (300); with reach's 3-turn refund a 4-turn trip still scores 205.  PRIO_HERO 160.
Pure synced game state + day, no RNG -> identical on every MP peer.  Human players never ask (AI target finder only).

Order: apply AFTER build_ai_itemloot + use_v1 + reach_v1 + antilure_v1 + prio_v1; revert THIS first
(antilure/prio dry runs report their entry jumps as FOREIGN while this is applied).
Dry-run default; --apply / --revert / --dis / --dll.  Backup <game>\backup\AoWEPACK.dll.bak_siteloot.
"""
import argparse, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts")
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55835000, 0x55835400   # undeclared + zero + reloc-free (mistystep 0x55834000..0x55834040 below)
MAGIC = b"SLL1"
TAB, MATCH = 0x5590B420, 0x5590B4A0
MAPHOLD, GAME_CELL = 0x558E9494, 0x558FA040
GETPLAYERS, GETUNIT = 0x557544D0, 0x5578309C
LIFE = 10
PRIO_LEADER, PRIO_HERO = 230, 160

REC_SITE, REC_ORIG, REC_BACK = 0x557C2A8E, bytes.fromhex("8b433c8b10"), 0x557C2A93
PRE_SITE, PRE_PREV = 0x55814D7F, 0x5581C490          # antilure AL cave
LP_SITE, LP_PREV, LP_NEXT = 0x55814EC0, 0x5581F040, 0x55814ECF   # prio_v1 PC / reach TC
SC_SITE, SC_PREV = 0x5573C60E, 0x5573C264

SRC = r"""
rec:
    pushad
    mov  eax, [ebp-4]
    test eax, eax
    jz   r_out
    movsx edx, byte ptr [eax+0x10]
    test edx, edx
    jl   r_out
    shl  edx, 24
    movzx ecx, byte ptr [eax+0x26]
    shl  ecx, 16
    or   edx, ecx
    movzx ecx, byte ptr [eax+0x25]
    shl  ecx, 8
    or   edx, ecx
    movzx ecx, byte ptr [eax+0x24]
    or   edx, ecx
    call today
    mov  esi, eax
    call slot_of
    call r_p
r_p:
    pop  ebp
    lea  ebp, [ebp + {P1}]
    mov  [ebp+eax*8], edx
    mov  [ebp+eax*8+4], esi
r_out:
    popad
    mov  eax, [ebx+0x3C]
    mov  edx, [eax]
    jmp  {REC_BACK}

; slot_of(edx = key) -> eax = (x + 3y + 5*level) & 15 ; keeps edx
slot_of:
    movzx eax, dl
    movzx ecx, dh
    lea  ecx, [ecx+ecx*2]
    add  eax, ecx
    mov  ecx, edx
    shr  ecx, 16
    and  ecx, 0xFF
    lea  ecx, [ecx+ecx*4]
    add  eax, ecx
    and  eax, 15
    ret

; hit(edx = key) -> eax = 1 if table C holds key with 0 <= today - day <= LIFE ; saves ebx/esi/edi/ebp
hit:
    push ebx
    push esi
    call slot_of
    call h_p
h_p:
    pop  ebx
    lea  esi, [ebx + {P2}]
    cmp  [esi+eax*8], edx
    jne  h_no
    test edx, edx
    jz   h_no
    mov  ecx, [esi+eax*8+4]
    call today
    sub  eax, ecx
    mov  ebx, eax
    jl   h_no
    cmp  ebx, {LIFE}
    jg   h_no
    mov  eax, 1
    jmp  h_out
h_no:
    xor  eax, eax
h_out:
    pop  esi
    pop  ebx
    ret

; today() -> eax = map day (0 if no map) ; clobbers eax only
today:
    call t_p
t_p:
    pop  eax
    mov  eax, dword ptr [eax + {P0}]
    test eax, eax
    jz   t_out
    mov  eax, [eax]
    test eax, eax
    jz   t_out
    mov  eax, [eax+0x174]
t_out:
    ret

pre:
    pushad
    sub  esp, 0x10
    call p_p
p_p:
    pop  ebp
    lea  ebp, [ebp + {P4}]
    mov  dword ptr [ebp], 0
    mov  eax, [edi+0x10]
    test eax, eax
    jz   p_out
    mov  ebx, [eax+0xC]
    test ebx, ebx
    jz   p_out
    movsx eax, byte ptr [ebx+0x28]
    test eax, eax
    jl   p_out
    mov  [esp], eax
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x74]
    movzx eax, al
    mov  [esp+4], eax
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x78]
    movzx eax, al
    mov  [esp+8], eax
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x7c]
    movzx edx, al
    shl  edx, 16
    mov  eax, [esp+8]
    shl  eax, 8
    or   edx, eax
    or   edx, [esp+4]
    mov  eax, [esp]
    shl  eax, 24
    or   edx, eax
    call hit
    test eax, eax
    jz   p_out
    mov  dword ptr [esp+0xC], {PRIO_HERO}
    call p_q
p_q:
    pop  eax
    mov  eax, dword ptr [eax + {P5}]
    test eax, eax
    jz   p_set
    mov  eax, [eax+0x140]
    test eax, eax
    jz   p_set
    mov  edx, [esp]
    call {GETPLAYERS}
    test eax, eax
    jz   p_set
    mov  edi, [eax+0xD4]
    test edi, edi
    jz   p_set
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  esi, eax
p_lp:
    dec  esi
    jl   p_set
    mov  eax, ebx
    mov  edx, esi
    call {GETUNIT}
    cmp  eax, edi
    jne  p_lp
    mov  dword ptr [esp+0xC], {PRIO_LEADER}
p_set:
    mov  eax, [esp+0xC]
    mov  [ebp], eax
p_out:
    add  esp, 0x10
    popad
    jmp  {PRE_PREV}

lp:
    push ecx
    call l_p
l_p:
    pop  ecx
    lea  ecx, [ecx + {P6}]
    cmp  dword ptr [ecx], 0
    je   l_norm
    mov  eax, [ecx]
    mov  dword ptr [ecx], 0
    pop  ecx
    jmp  {LP_NEXT}
l_norm:
    pop  ecx
    jmp  {LP_PREV}

; sc(eax = selector, edx = target record, ecx = group) -> al  (replaces `call 0x5573C264`)
sc:
    push eax
    push ecx
    push edx
    movsx eax, byte ptr [ecx+0x28]
    test eax, eax
    jl   s_orig
    shl  eax, 24
    mov  ecx, [edx+0x30]
    and  ecx, 0xFFFFFF
    or   eax, ecx
    mov  edx, eax
    call hit
    test eax, eax
    jz   s_orig
    pop  edx
    pop  ecx
    pop  eax
    xor  eax, eax
    ret
s_orig:
    pop  edx
    pop  ecx
    pop  eax
    jmp  {SC_PREV}
"""

PIC = {"P0": MAPHOLD, "P1": TAB, "P2": TAB, "P4": MATCH, "P5": GAME_CELL, "P6": MATCH}
ORDER = ["P0", "P1", "P2", "P4", "P5", "P6"]   # order of the call/pop pairs that serve them
POPS = {"P0": "t_p", "P1": "r_p", "P2": "h_p", "P4": "p_p", "P5": "p_q", "P6": "l_p"}
CODE = ZONE + 4


def _asm(src, addr):
    src = chr(10).join(l.split(";")[0] for l in src.splitlines())
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, addr)
    return bytes(enc)


def build():
    fmt = dict(REC_BACK="0x%X" % REC_BACK, PRE_PREV="0x%X" % PRE_PREV, LP_NEXT="0x%X" % LP_NEXT,
               LP_PREV="0x%X" % LP_PREV, SC_PREV="0x%X" % SC_PREV, GETPLAYERS="0x%X" % GETPLAYERS,
               GETUNIT="0x%X" % GETUNIT, LIFE=LIFE, PRIO_LEADER=PRIO_LEADER, PRIO_HERO=PRIO_HERO)
    dummy = dict(fmt, **{k: "0x7FFFFF00" for k in PIC})
    # label addresses: assemble with a unique marker after each label, find the pop opcodes in order
    labels = {}
    for lab in ("rec", "pre", "lp", "sc", "t_p", "r_p", "h_p", "p_p", "p_q", "l_p"):
        src = SRC.format(**dummy)
        assert src.count("\n" + lab + ":\n") == 1, lab        # exact label line (e.g. 'lp:' must not hit 'p_lp:')
        s = src.replace("\n" + lab + ":\n", "\n" + lab + ":\n    int3\n    int3\n    int3\n    int3\n", 1)
        c = _asm(s, CODE)
        labels[lab] = CODE + c.index(b"\xCC\xCC\xCC\xCC")
    real = dict(fmt, **{k: "0x%X" % ((PIC[k] - labels[POPS[k]]) & 0xFFFFFFFF) for k in PIC})
    code = _asm(SRC.format(**real), CODE)
    c0 = _asm(SRC.format(**dummy), CODE)
    assert len(code) == len(c0), "PIC displacement width changed"
    zone = MAGIC + bytes(CODE - ZONE - 4) + code
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return zone, labels


def jmp(src, dst):
    return b"\xE9" + struct.pack("<i", dst - (src + 5))


def call(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def sites(labels):
    return [(REC_SITE, REC_ORIG, jmp(REC_SITE, labels["rec"]), "REC site drop-loot record"),
            (PRE_SITE, jmp(PRE_SITE, PRE_PREV), jmp(PRE_SITE, labels["pre"]), "PRE cave_target entry"),
            (LP_SITE, jmp(LP_SITE, LP_PREV), jmp(LP_SITE, labels["lp"]), "LP priority step"),
            (SC_SITE, call(SC_SITE, SC_PREV), call(SC_SITE, labels["sc"]), "SC Score other-group test")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, labels = build()
    rd = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    zl = rd(ZONE, ZONE_END - ZONE)
    zstate = "zero" if not any(zl) else ("ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS")
    S = sites(labels)
    sst = []
    for va, ob, nb, nm in S:
        c = rd(va, len(nb))
        s = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        sst.append(s)
        print("  %-28s @%#x  %s" % (nm, va, s))
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + 5 for va, *_ in S)]
    print("  zone %#x..%#x %s (%d B; rec %#x pre %#x lp %#x sc %#x) | table %#x match %#x | relocs %s"
          % (ZONE, ZONE_END, zstate, len(zone), labels["rec"], labels["pre"], labels["lp"], labels["sc"],
             TAB, MATCH, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[CODE - ZONE:], CODE):
            print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad:
        print("ABORT (reloc under a site or the zone)"); return 1
    if zstate == "DIFFERS" or "FOREIGN" in sst:
        print("ABORT (zone not free / a site is foreign - apply order: itemloot, use_v1, reach_v1, antilure_v1, prio_v1)")
        return 1
    applied = zstate == "ours" and all(s == "applied" for s in sst)
    pristine = zstate == "zero" and all(s == "original" for s in sst)
    if not (applied or pristine):
        print("ABORT (mixed state)"); return 1
    if a.revert:
        if pristine:
            print("not applied"); return 0
        n = bytearray(d)
        for va, ob, nb, nm in S:
            n[va - V2F:va - V2F + len(ob)] = ob
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    elif a.apply:
        if applied:
            print("already applied"); return 0
        n = bytearray(d)
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for va, ob, nb, nm in S:
            n[va - V2F:va - V2F + len(nb)] = nb
    else:
        print("already applied" if applied else "Dry run OK - rerun with --apply (or --revert).")
        return 0
    if a.dll == DLL:
        bak = bak_path(a.dll, ".bak_siteloot")
        if a.apply and not os.path.exists(bak):
            shutil.copyfile(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f:
        f.seek(0); f.write(n)
    print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
