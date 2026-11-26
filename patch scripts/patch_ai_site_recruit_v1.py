r"""
AI SITE RAIDS - GATHER A STRONG ENOUGH FORCE (engine-native recruitment / cooperation), 2026-10-19.  AoWEPACK.dll only.

User: "AI is still too passive about exploration sites.  If the AI has enough units within ~3 turns of a site that
it could form a single 8-stack of sufficient power to explore, it should rearrange its nearby units into the most
powerful stack possible and do so."

RE - the strategic AI already HAS this machinery; sites just never fed it:
  TAIGroupTargetFinder (0x5573A120..) floods 200 MP around a group, queries each field with msg 0x1200 (answer rec,
  6 dwords, zeroed by TAoWMapField.GetAITarget 0x55771D84) and turns every answer into a TAIGroupControlTarget in
  TargetFoundEvent 0x5573A18C: answer -> target +0x18..+0x2F (+0x18 priority, +0x1C kind byte), +0x30 x/y/level,
  +0x34 path cost, and (finder setup sets bit 1 of [finder+0x24]) +0x40 = 0x5575C224 = enemy strength along the path.
  TAIGroupTargetSelector.Process 0x5573D2C0 (state 0, per target):
      req = GetRequiredStrength 0x5573CBB8 = max(GetRequiredTargetStrength (battle-field scan at the target),
                                                GetRequiredBattleFieldStrength 0x5573CAC4 >= [t+0x40] x [sel+0x70|74]
                                                (superiority, default 1.0 / 0.8 current target, plugins 0.75..1.5))
      if req > group strength [gc+0x50] (= sum TAbstractUnit.GetStrength(unit, [0x558E8044]) - the all-kinds metric)
      -> TAIGroupCooperationControl ([sel+0x2C], mode bit 2: other groups join the attack),
         TAIGroupRecruitControl ([sel+0x24], bit 4: pull units from other groups, recruit finder floods 75 MP),
         TAIGroupProductionControl ([sel+0x28], bit 8: build units);  a target that cannot be made feasible never
         gets flag 2 in [t+0x3C] and state 10 skips it (no suicide runs).
  A site's defenders are a TUnitList on the site ([site+0x34]), not a map army, so BOTH required-strength terms are 0
  for site targets: the selector thinks any group can take any site alone, and our cave_msgproc (build_ai_sitesearch
  v2 ladder) had to refuse weak groups outright -> passive AI, no gathering.

FIX (3 hooks, zone 0x5581D000..0x5581E000 'SRC1'):
  M  cave_msgproc weak-group gate @0x55814AC2 (11 B: lea ecx,[ebp*3] / lea edx,[eax*2] / cmp / jl skip):
       every site answer records (site x/y/level -> roster strength x TAGK/10) in a small per-search table;
       group >= 1.5 x roster (by the leader-safety v4 grp_eff value) -> original ladder (unchanged);
       weaker group WITHOUT the leader -> answer priority P_WEAK (15) instead of refusing, so the selector runs its
       own requirement / cooperation / recruitment logic on the site;  weaker group WITH the leader -> refused as
       before (leader safety untouched; the leader rules in leader-safety v4 / XS gate stay authoritative).
  T  TargetFoundEvent @0x5573A20C (6 B: mov eax,[edi+0x2C] / cmp eax,-1): if the target's x/y/level is in the table,
       [t+0x40] = max([t+0x40], tagged strength)  ->  required strength = roster x 1.5 x superiority.
  A  TAIGroupTargetFinder.Activate @0x5573A30C (5 B prologue): clears the table at the start of every target search,
       so tags only ever come from this search's own answers (identical on every MP peer, nothing stale after a load).
Table: 32 x {key = x | y<<8 | level<<16 | 0x01000000, strength} + index dword at AoWEPACK .idata page slack
  0x5590BD20..0x5590BE24 (beyond raw data = zero at load; essence uses BD00/BD10, mimic BE40).
All addresses reached PIC (call/pop delta) or rel32 -> rebase-safe.  No RNG; only synced game state -> MP-identical.
Recruited/cooperating units then move and merge through the engine's own group / move executers; the existing
gates still decide the actual search (cave_execai mint >= 2/3 x roster with converge v2 waiting <= 1 turn, leader
rules, XS choke gate).

Dry-run default; --apply / --revert / --dis / --dll <scratch>.  Backup <game>\backup\AoWEPACK.dll.bak_aisiterecruit.
LIFO: hook M sits inside build_ai_sitesearch's cave_msgproc (next to leader-safety's hook B @0x55814ABD, no overlap):
revert this before build_ai_sitesearch.py.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581D000, 0x5581D400   # 10/19: 0x5581D400+ = patch_ai_end_enchant_v1
CODE = ZONE + 0x20
H_LCLS, H_TABLE = CODE, CODE + 0x10            # PIC helpers
M_ENTRY, T_ENTRY, A_ENTRY, SUBS = CODE + 0x20, CODE + 0x100, CODE + 0x180, CODE + 0x200
MAGIC = b"SRC1"

SITE_M, ORIG_M = 0x55814AC2, bytes.fromhex("8d4c6d008d140039ca7c4c")
SITE_T, ORIG_T = 0x5573A20C, bytes.fromhex("8b472c83f8ff")
SITE_A, ORIG_A = 0x5573A30C, bytes.fromhex("5356578bf2")
M_STRONG, M_SKIP, M_ANSWER = 0x55814ACD, 0x55814B19, 0x55814B13
T_BACK, A_BACK = 0x5573A212, 0x5573A311

TABLE, NENT = 0x5590BD20, 32
TAGK, P_WEAK = 15, 15                           # tag = roster x 1.5 ; weak-group answer priority
GETUNIT, ISCLASS, CLS_LEADER = 0x5578309C, 0x557010C0, 0x557121F8

SRC_M = """
    push eax
    call {TAG}
    pop  eax
    lea  ecx, [ebp+ebp*2]
    lea  edx, [eax+eax]
    cmp  edx, ecx
    jl   weak
    jmp  {STRONG}
weak:
    mov  eax, [edi+0x10]
    mov  eax, [eax+0xc]
    call {HASL}
    test eax, eax
    jnz  skip
    mov  eax, {PW}
    jmp  {ANSWER}
skip:
    jmp  {SKIP}
"""

SRC_T = """
    push ecx
    push edx
    push esi
    call {HT}
    mov  esi, eax
    mov  edx, [ebx+0x30]
    and  edx, 0xffffff
    or   edx, 0x1000000
    xor  ecx, ecx
tl:
    cmp  ecx, {N}
    jge  tdone
    cmp  [esi+ecx*8+4], edx
    je   tfound
    inc  ecx
    jmp  tl
tfound:
    mov  eax, [esi+ecx*8+8]
    cmp  eax, [ebx+0x40]
    jle  tdone
    mov  [ebx+0x40], eax
tdone:
    pop  esi
    pop  edx
    pop  ecx
    mov  eax, [edi+0x2c]
    cmp  eax, -1
    jmp  {BACK}
"""

SRC_A = """
    push eax
    push ecx
    push edi
    call {HT}
    mov  edi, eax
    xor  eax, eax
    mov  ecx, {DW}
    cld
    rep  stosd
    pop  edi
    pop  ecx
    pop  eax
    push ebx
    push esi
    push edi
    mov  esi, edx
    jmp  {BACK}
"""

# subs: tag_site (esi = site, ebp = roster S > 0; keeps ebx/esi/edi/ebp) / has_leader (eax = TUnitList -> eax 0/1)
SRC_S = """
tag:
    push ebx
    push esi
    push edi
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x74]
    movzx edi, al
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x78]
    movzx ebx, al
    shl  ebx, 8
    or   edi, ebx
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x7c]
    movzx ebx, al
    shl  ebx, 16
    or   edi, ebx
    or   edi, 0x1000000
    mov  eax, ebp
    imul eax, eax, {K}
    cdq
    mov  ecx, 10
    idiv ecx
    mov  ebx, eax
    call {HT}
    mov  esi, eax
    xor  ecx, ecx
ts_lp:
    cmp  ecx, {N}
    jge  ts_new
    cmp  [esi+ecx*8+4], edi
    je   ts_set
    inc  ecx
    jmp  ts_lp
ts_new:
    mov  ecx, [esi]
    and  ecx, {NM}
    lea  edx, [ecx+1]
    and  edx, {NM}
    mov  [esi], edx
ts_set:
    mov  [esi+ecx*8+4], edi
    mov  [esi+ecx*8+8], ebx
    pop  edi
    pop  esi
    pop  ebx
    ret
hasl:
    push ebx
    push esi
    push edi
    push ebp
    mov  esi, eax
    xor  eax, eax
    test esi, esi
    jz   hl_out
    call {HL}
    mov  ebp, eax
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  edi, eax
    xor  ebx, ebx
hl_lp:
    cmp  ebx, edi
    jge  hl_none
    mov  edx, ebx
    mov  eax, esi
    call {GU}
    test eax, eax
    jz   hl_nx
    mov  edx, ebp
    call {IC}
    test al, al
    jnz  hl_yes
hl_nx:
    inc  ebx
    jmp  hl_lp
hl_yes:
    mov  eax, 1
    jmp  hl_out
hl_none:
    xor  eax, eax
hl_out:
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""


def asm(src, at):
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def build():
    # helpers: H_LCLS -> eax = [CLS_LEADER] (TLeader class) ; H_TABLE -> eax = &table
    h1 = b"\xe8\x00\x00\x00\x00\x58\x05" + struct.pack("<i", CLS_LEADER - (H_LCLS + 5)) + b"\x8b\x00\xc3"
    h2 = b"\xe8\x00\x00\x00\x00\x58\x05" + struct.pack("<i", TABLE - (H_TABLE + 5)) + b"\xc3"
    subs = asm(SRC_S.format(K=TAGK, N=NENT, NM=NENT - 1, HT=H_TABLE, HL=H_LCLS, GU=GETUNIT, IC=ISCLASS), SUBS)
    # sub entry points: tag = SUBS, hasl = first "push ebx" after the tag's ret
    import capstone
    ins = list(capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(subs, SUBS))
    hasl = next(ins[k + 1].address for k in range(len(ins) - 1) if ins[k].mnemonic == "ret")
    m = asm(SRC_M.format(TAG=SUBS, STRONG=M_STRONG, HASL=hasl, PW=P_WEAK, ANSWER=M_ANSWER, SKIP=M_SKIP), M_ENTRY)
    t = asm(SRC_T.format(HT=H_TABLE, N=NENT, BACK=T_BACK), T_ENTRY)
    a = asm(SRC_A.format(HT=H_TABLE, DW=1 + 2 * NENT, BACK=A_BACK), A_ENTRY)
    assert len(m) <= T_ENTRY - M_ENTRY and len(t) <= A_ENTRY - T_ENTRY and len(a) <= SUBS - A_ENTRY
    zone = bytearray(0x20 + 0x200 + len(subs))
    zone[0:4] = MAGIC
    zone[4:4 + 22] = ORIG_M + ORIG_T + ORIG_A
    for addr, blob in ((H_LCLS, h1), (H_TABLE, h2), (M_ENTRY, m), (T_ENTRY, t), (A_ENTRY, a), (SUBS, subs)):
        zone[addr - ZONE:addr - ZONE + len(blob)] = blob
    assert len(zone) <= ZONE_END - ZONE
    sm = b"\xe9" + struct.pack("<i", M_ENTRY - (SITE_M + 5)) + b"\x90" * 6
    st = b"\xe9" + struct.pack("<i", T_ENTRY - (SITE_T + 5)) + b"\x90"
    sa = b"\xe9" + struct.pack("<i", A_ENTRY - (SITE_A + 5))
    return bytes(zone), {SITE_M: (ORIG_M, sm), SITE_T: (ORIG_T, st), SITE_A: (ORIG_A, sa)}, hasl


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, sites, hasl = build()
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    states = {}
    for s, (o, n) in sites.items():
        b = bytes(d[s - V2F:s - V2F + len(o)])
        states[s] = "vanilla" if b == o else "ours" if b == n else "FOREIGN"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END
           or any(s - 3 <= r < s + len(o) for s, (o, n) in sites.items())]
    for s in sites: print("  site %#x %s" % (s, states[s]))
    print("  zone %#x..%#x %s (%d B; hasl %#x) | table %#x x%d | relocs %s"
          % (ZONE, ZONE_END, zstate, len(zone), hasl, TABLE, NENT, bad or "none"))
    if a.dis:
        import capstone
        for lo, hi in ((H_LCLS, M_ENTRY), (M_ENTRY, T_ENTRY), (T_ENTRY, A_ENTRY), (A_ENTRY, SUBS), (SUBS, ZONE + len(zone))):
            print("  --")
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[lo - ZONE:hi - ZONE].rstrip(b"\0") or b"\x90", lo):
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    st = set(states.values())
    if bad or "FOREIGN" in st: print("ABORT (site/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if len(st | {zstate.replace("zero", "vanilla")}) > 1: print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    if a.revert:
        for s, (o, _) in sites.items(): n[s - V2F:s - V2F + len(o)] = o
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for s, (_, p) in sites.items(): n[s - V2F:s - V2F + len(p)] = p
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aisiterecruit")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
