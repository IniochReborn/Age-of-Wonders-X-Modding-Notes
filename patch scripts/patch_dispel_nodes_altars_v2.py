#!/usr/bin/env python3
r"""
Dispel Magic nodes/altars v2 (2026-10-19) - IMMEDIATE power refresh.  User: "I want the power increase to be immediate."

RE (AoWEPACK, preferred base 0x55700000):
  * Realm power is NOT cached: TPlayerMagicControl.GetPower 0x5577CA00 sums the registered power sources live
    (TPlayerStructurePowerSource.Power 0x55761B54 = structure VMT+0x1F8 -> our v1 dmlevel wrapper), and GetNetPower
    0x5577CEC4 / GetNetPowerToMana 0x5577CEE4 / ToResearch 0x5577CF80 / GetManaIncome 0x5577C95C all call it live.
    So the per-turn credit already uses whatever stands on the node when the owner's turn is processed.
  * What was missing is the CHANGE NOTIFICATION: the UI (magic window / realm power / top bar) refreshes when
    TPlayerMagicControl.Update 0x5577D248 fires (mc = [player+0x54]; Update: if [mc+0x14] BeginUpdate count == 0 ->
    UpdateEnemyEnchantments 0x5577C880 (idempotent recompute) + notify observers [mc+0x48] via 0x55702FBC).  Vanilla
    calls it when a node registers/unregisters its power source (capture, 0x557BEF08) - never when an army steps on.
  * Army enter/leave reaches the structure: TArmyHS.PlaceOnMap 0x557909F4 sends field msg 0x1102 (after the army is
    on the field) and the remove path 0x55790A5C sends 0x1103 (after removal; skipped while [game+0x3C]&8 = bulk
    clear).  TStructure msgproc 0x5575F730 dispatches 0x1102 -> VMT+0x180 ArmyPlaced, 0x1103 -> VMT+0x184
    ArmyRemoved (edx = army HS).  Node msgprocs chain there (TProductionPlace 0x557BF3D0 -> TPlayerStructure
    0x55761658 -> call 0x5575F730 @0x55761730).

Design: slots +0x180 and +0x184 of the 8 node VMTs -> per-target stub: call the PREVIOUS slot target (elemental-node
bless caves 0x55814300.. from build_elemental_nodes.py, vanilla 0x55760F24 / 0x5575F364) with eax/edx intact, then
notify(struct): owner [s+0x30] >= 0 -> player = TPlayers.Get 0x557544D0([[[0x558E9494]]+0x140], owner) -> mc =
[player+0x54] -> if mc and [mc+0x48] -> Update(mc).  Moving onto / off a node (or merging/splitting there, which
places/removes army HSs) refreshes the owner's power immediately; every step through a node also refreshes (cheap).
Not covered: a unit gaining/losing Dispel Magic while standing still (level-up / item swap on the node) - picked up
at the next refresh (any move, capture, turn).  Altars unchanged (their recharge is read live).
Deterministic (game state only, runs inside the move on every client); editor-safe (nil holder/players/mc -> skip).
Zone 0x5581F300..0x5581F800 shared with v1: v1 code 0x5581F310..0x5581F467 unchanged, v2 code from 0x5581F470;
header 'DMN2' (the v1 script then refuses).  Upgrades v1 in place; --revert = exact pre-v1 file (= v1 --revert).
LIFO: revert this before build_elemental_nodes.py (its +0x180 caves are our chained targets).
Backup <game>\backup\AoWEPACK.dll.bak_dispelnodes2.  Dry run default; --apply / --revert / --dis [dll].
"""
import os, shutil, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts")
import patch_dispel_nodes_altars_v1 as V1
from patch_dispel_nodes_altars_v1 import asm, D, ZONE_LO, ZONE_HI, NODE_VMTS, MAPHOLD

DLL = V1.DLL
MAGIC = b"DMN2"
V2CODE = 0x5581F470
GETPLAYER, MC_UPDATE = 0x557544D0, 0x5577D248
# previous (live, 2026-10-19) +0x180 / +0x184 targets per node class
PREV180 = {"TFireNode": 0x55814300, "TEarthNode": 0x55814310, "TDeathNode": 0x55814328, "TLifeNode": 0x55814320,
           "TWaterNode": 0x55814308, "TAirNode": 0x55814318, "TRandomNode": 0x55760F24, "TPowerNode": 0x55814330}
PREV184 = 0x5575F364


def prev_targets():
    return sorted(set(PREV180.values()) | {PREV184})


def v2_src(kmap):
    s = []
    for i, t in enumerate(prev_targets()):
        s += ["st%d:" % i, "    push ebx", "    mov  ebx, eax", "    call 0x%X" % t, "    mov  eax, ebx",
              "    pop  ebx", "    jmp  notify"]
    s += """
notify:
    push ebx
    push ebp
    call n_p
n_p:
    pop  ebp
    movsx edx, byte ptr [eax+0x30]
    test edx, edx
    jl   n_out
    mov  eax, dword ptr [ebp + {KMAP}]
    test eax, eax
    jz   n_out
    mov  eax, [eax]
    test eax, eax
    jz   n_out
    mov  eax, [eax+0x140]
    test eax, eax
    jz   n_out
    call {GP}
    test eax, eax
    jz   n_out
    mov  eax, [eax+0x54]
    test eax, eax
    jz   n_out
    cmp  dword ptr [eax+0x48], 0
    je   n_out
    call {UPD}
n_out:
    pop  ebp
    pop  ebx
    ret
""".format(KMAP=kmap, GP=GETPLAYER, UPD=MC_UPDATE).split("\n")
    return "\n".join(s)


def labels2():
    return ["st%d" % i for i in range(len(prev_targets()))] + ["notify", "n_p", "n_out"]


def lab_addrs(src, addr, labels):
    b = asm(src + "\n" + "\n".join(".long %s" % l for l in labels), addr)
    tbl = b[-4 * len(labels):]
    return {l: struct.unpack_from("<I", tbl, 4 * k)[0] for k, l in enumerate(labels)}


def build2():
    s0 = v2_src(0x7FFFFF00)
    lab = lab_addrs(s0, V2CODE, labels2())
    s1 = v2_src((MAPHOLD - lab["n_p"]) & 0xFFFFFFFF)
    c0, c1 = asm(s0, V2CODE), asm(s1, V2CODE)
    assert len(c0) == len(c1) and lab_addrs(s1, V2CODE, labels2()) == lab
    assert V2CODE + len(c1) <= ZONE_HI
    return c1, lab


def edits():
    z1, lab1 = V1.build()
    assert ZONE_LO + len(z1) <= V2CODE
    c2, lab2 = build2()
    zone = MAGIC + z1[4:] + bytes(V2CODE - ZONE_LO - len(z1)) + c2
    E1, _ = V1.edits()                      # E1[0] = v1 zone, E1[1:] = the 15 v1 slot edits
    E = [(ZONE_LO, bytes(len(zone)), zone, "DMN cave (v1 + v2)")] + E1[1:]
    stubs = {t: lab2["st%d" % i] for i, t in enumerate(prev_targets())}
    for v, n in NODE_VMTS.items():
        E.append((v + 0x180, struct.pack("<I", PREV180[n]), struct.pack("<I", stubs[PREV180[n]]),
                  "%s.ArmyPlaced slot" % n))
        E.append((v + 0x184, struct.pack("<I", PREV184), struct.pack("<I", stubs[PREV184]),
                  "%s.ArmyRemoved slot" % n))
    return E, lab1, lab2, z1, zone


def main(dll=None):
    dll = dll or DLL
    ap, rv = "--apply" in sys.argv, "--revert" in sys.argv
    d = bytearray(open(dll, "rb").read())
    E, lab1, lab2, z1, zone = edits()
    if "--dis" in sys.argv:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[V2CODE - ZONE_LO:], V2CODE):
            print("  %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    rel = V1.relocs(bytes(d))
    bad = [hex(r) for r in rel if ZONE_LO - 3 <= r < ZONE_HI]
    assert not bad, "reloc in zone: %s" % bad
    for va, ob, nb, nm in E[1:]:
        assert va in rel, "slot %s has no reloc?" % nm
    cur = bytes(d[ZONE_LO - D:ZONE_HI - D])
    zstate = ("zero" if not any(cur) else
              "v2" if cur[:len(zone)] == zone and not any(cur[len(zone):]) else
              "v1" if cur[:len(z1)] == z1 and not any(cur[len(z1):]) else "FOREIGN")
    st = []
    for va, ob, nb, nm in E[1:]:
        c = bytes(d[va - D:va - D + len(nb)])
        s = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        st.append(s)
        print("  %-34s @0x%08X  %s" % (nm, va, s))
    print("  zone 0x%08X..0x%08X: %s (v2 code 0x%08X..0x%08X, notify 0x%08X) | relocs none"
          % (ZONE_LO, ZONE_HI, zstate, V2CODE, ZONE_LO + len(zone), lab2["notify"]))
    if zstate == "FOREIGN" or "FOREIGN" in st:
        print("FOREIGN - refusing")
        return 1
    v1slots, newslots = st[:15], st[15:]
    if zstate == "v2" and all(s == "applied" for s in st):
        state = "v2"
    elif zstate == "v1" and all(s == "applied" for s in v1slots) and all(s == "original" for s in newslots):
        state = "v1"
    elif zstate == "zero" and all(s == "original" for s in st):
        state = "zero"
    else:
        print("inconsistent state - refusing")
        return 1
    print("  state: %s" % state)
    if rv:
        if state == "zero":
            print("not applied")
            return 0
        for va, ob, nb, _ in E:
            d[va - D:va - D + len(nb)] = ob
        with open(dll, "r+b") as f:
            f.seek(0); f.write(bytes(d))
        print("reverted (pre-v1 state)")
        return 0
    if state == "v2":
        print("already applied")
        return 0
    if not ap:
        print("dry run (--apply / --revert)%s" % ("  [upgrading v1 -> v2 in place]" if state == "v1" else ""))
        return 0
    bk = V1.bak_path(dll, ".bak_dispelnodes2")
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
    print("written and verified: node power refreshes immediately when armies enter/leave a node")
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    sys.exit(main(a[0] if a else None))
