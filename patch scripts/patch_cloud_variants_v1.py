#!/usr/bin/env python3
r"""
Poison-cloud variants: Sandstorm / Snowstorm / Holy Cloud / Death Cloud (AoWEPACK.dll, 2026-10-30).
Data side: build_cloud_variants_hss_v1.py (4 TPoisonCloudResource records + Images\Effects ILBs).

A placed cloud (TPoisonCloud, PoisonC unit) points at its resource [cloud+8]; the variant = the resource NAME
(AnsiString ptr [res+0x30]; v1 first read it as an inline ShortString -> never matched): "Sandstorm" 1, "Snowstorm" 2, "Holy Cloud" 3, "Death Cloud" 4, anything else 0 (Poison
Cloud, vanilla).  Damage paths (both synchronous, storm kind 6):
  owner's turn start  TPoisonCloud.MsgProc @0x557CAF57 `call TriggerDamage(eax=cloud)` -> field msg 0x1150 ->
                      TArmyHS -> TArmy.IncommingStorm 0x557904B4 -> per unit ExecuteStormDamage 0x55780668
  army enters         MapFieldMsgProc @0x557CAC7D `call ArmyPlaced(eax=cloud, edx=army)` -> IncommingStorm(kind 6)
Both calls are wrapped: G_CLOUD (DATA slack byte 0x558E9BF0, unclaimed) := variant, call, := 0.
While G_CLOUD != 0 and the storm kind is 6:
  ExecuteStormDamage prologue 0x55780668 (7 B): target filter -> return 0 (no damage, no debuff):
      Sandstorm  unit race (VMT+0xA4) == 1 Azrac          Snowstorm  GetAbilityEnabled(0x4C Cold Protection)
      Holy Cloud alignment (VMT+0xFC) not in {4 Evil, 5 Pure Evil}
      Death Cloud alignment not in {0 Pure Good, 1 Good}
  kind-6 case 0x55780786 (12 B): ATK/DMG 6/1, 6/1, 5/2, 5/2 (poison 4/3)   (doubling for sailing/water kept)
  damage type 0x557807AB (11 B, `lea/mov cl,2/call SetElem`): dl = Physical 7 / Cold 1 / Holy 6 / Death 5
  debuff jump 0x557807EB (-> storm-debuff cave 0x558161C0, Poisoned for kind 6): Holy -> Vertigo 0x40, Death ->
      Cursed 0x20 via ExecuteDamageEffects 0x55781E28 (RES roll), Sand/Snow none (v1.1, 10/30)
  IncommingStorm report name 0x5579050D / 0x5579052D (`call LoadResString`): variant name instead of
      "Pestilence Storm".
Editor hover: TPoisonCloudResource VMT+0x54 ResourceEditName (slot 0x557CA834, class RStr "Poison Cloud") -> the
  resource's own name [res+0x30] (v1.1).
Movement (v1.2): TPoisonCloud.CanMoveOver 0x557CAA68 stops an army each hex when CanDoDamage says a unit can be
  hurt; vanilla exempts only flyers and poison-immune units (VMT+0xEC & 0x10).  The CanDoDamage call @0x557CAA91 is
  wrapped (G_CLOUD = variant) and the immunity test @0x557CAAD3 uses the variant rule: sand = physical immune or
  Azrac, snow = cold immune or Cold Protection, holy = holy immune or not evil, death = death immune or not good
  -> unaffected armies walk through freely, like poison-immune units through Poison Cloud.
Pestilence Storm (spell) finds its cloud by class (first match = Poison Cloud, records are appended after) and
calls TriggerDamage directly (0x557CD9E8, not wrapped) -> always poison.
Zone AoWEPACK 0x55848D00..0x55849200 ('CLV1'; moved from 0x55848800 in v1.2 - code grew).  PIC (call/pop delta).  Dry-run default; --apply / --revert.
⚠ LIFO: the debuff-jump site belongs to patch_storm_debuff_sources_v1 — revert this first.
Backup AoWEPACK.dll.bak_cloudvar.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, BASE = game_file("AoWEPACK.dll"), 0x55700000
MAGIC = b"CLV1"
ZONE, ZONE_END = 0x55848D00, 0x55849200
G_CLOUD = 0x558E9BF0
NAMES = {1: "Sandstorm", 2: "Snowstorm", 3: "Holy Cloud", 4: "Death Cloud"}
STATS = {0: (4, 3), 1: (6, 1), 2: (6, 1), 3: (5, 2), 4: (5, 2)}
DTYPE = {1: 7, 2: 1, 3: 6, 4: 5}
TRIG_SITE, TRIG_FN = 0x557CAF57, 0x557CAB88
ARMY_SITE, ARMY_FN = 0x557CAC7D, 0x557CAB08
ESD, ESD_ORIG, ESD_BACK = 0x55780668, bytes.fromhex("53565755" "83c4f4"), 0x5578066F
K6, K6_ORIG, K6_BACK = 0x55780786, bytes.fromhex("bd04000000be03000000eb04"), 0x55780796
TY, TY_ORIG, TY_BACK, SETELEM = 0x557807AB, bytes.fromhex("8d442408b102e8d208f8ff"), 0x557807B6, 0x55701088
DB, DB_TGT, DB_SKIP = 0x557807EB, 0x558161C0, 0x55780816
NM_SITES, LOADRES, LSTRASG = (0x5579050D, 0x5579052D), 0x557249FC, 0x55701150
EXEC_EFFECTS = 0x55781E28          # TAbstractUnit.ExecuteDamageEffects(eax=unit, dx=mask) (RES roll via storm-roll patch)
RES_VMT, EN_SLOT, EN_ORIG = 0x557CA7E0, 0x557CA834, 0x557CAFC4   # TPoisonCloudResource VMT, +0x54 ResourceEditName
CDD_SITE, CDD_FN = 0x557CAA91, 0x557CAAB0             # TPoisonCloud.CanMoveOver -> CanDoDamage(eax=cloud, edx=army)
IMM_SITE, IMM_ORIG = 0x557CAAD3, bytes.fromhex("ff92ec000000a8107513")   # unit immunity test (poison bit 0x10)
IMM_IMMUNE, IMM_FLY = 0x557CAAF0, 0x557CAADD
H = lambda v: "0x%X" % v  # noqa: E731

STR_BASE = ZONE + 0x10          # 4 Delphi constant strings, 0x20 each: [-8] -1, [-4] len, chars, 0
def str_va(v):
    return STR_BASE + 8 + 0x20 * (v - 1)


CODE = ZONE + 0x100
SRC = f"""
wrap:
    push eax
    call delta
    mov  ecx, eax
    pop  eax
    push ecx
    push eax
    push edx
    mov  edx, dword ptr [eax + 8]
    xor  eax, eax
    test edx, edx
    jz   w_set
    mov  edx, dword ptr [edx + 0x30]
    test edx, edx
    jz   w_set
    mov  ecx, dword ptr [edx - 4]
    cmp  ecx, 9
    jne  w_10
    cmp  byte ptr [edx], 0x53
    jne  w_set
    mov  al, 1
    cmp  byte ptr [edx + 1], 0x61
    je   w_set
    mov  al, 2
    cmp  byte ptr [edx + 1], 0x6E
    je   w_set
    xor  eax, eax
    jmp  w_set
w_10:
    cmp  ecx, 10
    jne  w_11
    cmp  byte ptr [edx], 0x48
    jne  w_set
    mov  al, 3
    jmp  w_set
w_11:
    cmp  ecx, 11
    jne  w_set
    cmp  byte ptr [edx], 0x44
    jne  w_set
    mov  al, 4
w_set:
    mov  ecx, dword ptr [esp + 8]
    mov  byte ptr [ecx + {H(G_CLOUD)}], al
    pop  edx
    pop  eax
    pop  ecx
    ret

delta:
    call d_g
d_g:
    pop  eax
    sub  eax, d_g_abs
    ret

trig:
    call wrap
    push ecx
    call {H(TRIG_FN)}
    pop  ecx
    mov  byte ptr [ecx + {H(G_CLOUD)}], 0
    ret

army:
    call wrap
    push ecx
    call {H(ARMY_FN)}
    pop  ecx
    mov  byte ptr [ecx + {H(G_CLOUD)}], 0
    ret

esd:
    cmp  dl, 6
    jne  e_orig
    push eax
    push ecx
    push edx
    call delta
    movzx ecx, byte ptr [eax + {H(G_CLOUD)}]
    mov  eax, dword ptr [esp + 8]
    test ecx, ecx
    jz   e_pass
    cmp  ecx, 1
    jne  e_2
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0xA4]
    cmp  al, 1
    je   e_skip
    jmp  e_pass
e_2:
    cmp  ecx, 2
    jne  e_34
    mov  edx, 0x4C
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x148]
    test al, al
    jnz  e_skip
    jmp  e_pass
e_34:
    push ecx
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0xFC]
    pop  ecx
    movzx eax, al
    cmp  ecx, 3
    jne  e_4
    cmp  eax, 4
    jb   e_skip
    cmp  eax, 5
    ja   e_skip
    jmp  e_pass
e_4:
    cmp  eax, 1
    ja   e_skip
e_pass:
    pop  edx
    pop  ecx
    pop  eax
e_orig:
    push ebx
    push esi
    push edi
    push ebp
    add  esp, -0xC
    jmp  {H(ESD_BACK)}
e_skip:
    pop  edx
    pop  ecx
    pop  eax
    xor  eax, eax
    ret

k6:
    call delta
    movzx eax, byte ptr [eax + {H(G_CLOUD)}]
    mov  ebp, {STATS[0][0]}
    mov  esi, {STATS[0][1]}
    cmp  eax, 1
    je   k_61
    cmp  eax, 2
    je   k_61
    cmp  eax, 3
    je   k_52
    cmp  eax, 4
    jne  k_done
k_52:
    mov  ebp, 5
    mov  esi, 2
    jmp  k_done
k_61:
    mov  ebp, 6
    mov  esi, 1
k_done:
    jmp  {H(K6_BACK)}

ty:
    cmp  byte ptr [esp], 6
    jne  t_go
    call delta
    movzx eax, byte ptr [eax + {H(G_CLOUD)}]
    cmp  eax, 1
    jne  t_2
    mov  dl, {DTYPE[1]}
t_2:
    cmp  eax, 2
    jne  t_3
    mov  dl, {DTYPE[2]}
t_3:
    cmp  eax, 3
    jne  t_4
    mov  dl, {DTYPE[3]}
t_4:
    cmp  eax, 4
    jne  t_go
    mov  dl, {DTYPE[4]}
t_go:
    lea  eax, [esp + 8]
    mov  cl, 2
    call {H(SETELEM)}
    jmp  {H(TY_BACK)}

db:
    cmp  byte ptr [esp], 6
    jne  d_go
    call delta
    movzx eax, byte ptr [eax + {H(G_CLOUD)}]
    test eax, eax
    jz   d_go
    mov  dx, 0x40
    cmp  eax, 3
    je   d_apply
    mov  dx, 0x20
    cmp  eax, 4
    je   d_apply
    jmp  {H(DB_SKIP)}
d_apply:
    mov  eax, edi
    call {H(EXEC_EFFECTS)}
    jmp  {H(DB_SKIP)}
d_go:
    jmp  {H(DB_TGT)}

cdd:
    call wrap
    push ecx
    call {H(CDD_FN)}
    pop  ecx
    mov  byte ptr [ecx + {H(G_CLOUD)}], 0
    ret

imm:
    call dword ptr [edx + 0xEC]
    mov  ecx, eax
    call delta
    movzx eax, byte ptr [eax + {H(G_CLOUD)}]
    test eax, eax
    jnz  im_var
    test cl, 0x10
    jnz  im_yes
    jmp  {H(IMM_FLY)}
im_var:
    cmp  eax, 1
    jne  im_2
    test cl, 0x80
    jnz  im_yes
    mov  eax, esi
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0xA4]
    cmp  al, 1
    je   im_yes
    jmp  {H(IMM_FLY)}
im_2:
    cmp  eax, 2
    jne  im_3
    test cl, 0x02
    jnz  im_yes
    mov  eax, esi
    mov  edx, 0x4C
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x148]
    test al, al
    jnz  im_yes
    jmp  {H(IMM_FLY)}
im_3:
    cmp  eax, 3
    jne  im_4
    test cl, 0x40
    jnz  im_yes
    mov  eax, esi
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0xFC]
    cmp  al, 4
    jb   im_yes
    cmp  al, 5
    ja   im_yes
    jmp  {H(IMM_FLY)}
im_4:
    test cl, 0x20
    jnz  im_yes
    mov  eax, esi
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0xFC]
    cmp  al, 1
    ja   im_yes
    jmp  {H(IMM_FLY)}
im_yes:
    jmp  {H(IMM_IMMUNE)}

en:
    push ebx
    push eax
    call delta
    mov  ebx, eax
    pop  eax
    test eax, eax
    jz   en_o
    lea  ecx, [ebx + {H(RES_VMT)}]
    cmp  dword ptr [eax], ecx
    jne  en_o
    mov  ecx, dword ptr [eax + 0x30]
    test ecx, ecx
    jz   en_o
    pop  ebx
    mov  eax, edx
    mov  edx, ecx
    jmp  {H(LSTRASG)}
en_o:
    pop  ebx
    jmp  {H(EN_ORIG)}

nm:
    cmp  byte ptr [ebp - 1], 6
    jne  n_go
    push eax
    call delta
    movzx ecx, byte ptr [eax + {H(G_CLOUD)}]
    test ecx, ecx
    jz   n_pop
    dec  ecx
    shl  ecx, 5
    lea  ecx, [eax + ecx + {H(str_va(1))}]
    pop  eax
    mov  eax, edx
    mov  edx, ecx
    jmp  {H(LSTRASG)}
n_pop:
    pop  eax
n_go:
    jmp  {H(LOADRES)}
"""


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    marks = ["trig", "army", "esd", "k6", "ty", "db", "nm", "en", "cdd", "imm"]
    src = SRC
    for m in marks:
        src = src.replace("\n%s:\n" % m, "\n" + "    int3\n" * (marks.index(m) + 3) + "%s:\n" % m)
    src = src.replace("\ndelta:\n", "\n    nop\n    nop\ndelta:\n")
    dg = 0x11111111
    for _ in range(4):
        code = bytes(ks.asm(src.replace("d_g_abs", H(dg)), CODE)[0])
        i = code.find(b"\x90\x90\xe8\x00\x00\x00\x00\x58")          # nop nop / call d_g / pop eax
        assert i >= 0
        new = CODE + i + 7
        if new == dg:
            break
        dg = new
    ents = {}
    for m in marks:
        n = marks.index(m) + 3
        ents[m] = CODE + code.index(b"\xcc" * n + b"\x00"[:0]) + n if False else None
    # locate entries: each mark preceded by exactly n int3s (distinct counts, search longest first)
    for m in sorted(marks, key=lambda x: -(marks.index(x) + 3)):
        n = marks.index(m) + 3
        pat = b"\xcc" * n
        pos = 0
        while True:
            k = code.find(pat, pos)
            assert k >= 0, m
            if (k == 0 or code[k - 1] != 0xCC) and code[k + n] != 0xCC:
                ents[m] = CODE + k + n
                break
            pos = k + 1
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    for v, name in NAMES.items():
        a = str_va(v) - ZONE
        struct.pack_into("<iI", z, a - 8, -1, len(name))
        z[a:a + len(name)] = name.encode()
    assert CODE + len(code) <= ZONE_END, hex(len(code))
    z[CODE - ZONE:CODE - ZONE + len(code)] = code
    return bytes(z), ents


def rel(op, at, tgt, pad=0):
    return bytes([op]) + struct.pack("<i", tgt - (at + 5)) + b"\x90" * pad


def plan():
    z, e = build()
    P = [(TRIG_SITE, rel(0xE8, TRIG_SITE, TRIG_FN), rel(0xE8, TRIG_SITE, e["trig"])),
         (ARMY_SITE, rel(0xE8, ARMY_SITE, ARMY_FN), rel(0xE8, ARMY_SITE, e["army"])),
         (ESD, ESD_ORIG, rel(0xE9, ESD, e["esd"], 2)),
         (K6, K6_ORIG, rel(0xE9, K6, e["k6"], 7)),
         (TY, TY_ORIG, rel(0xE9, TY, e["ty"], 6)),
         (DB, rel(0xE9, DB, DB_TGT), rel(0xE9, DB, e["db"]))]
    P += [(s, rel(0xE8, s, LOADRES), rel(0xE8, s, e["nm"])) for s in NM_SITES]
    P.append((EN_SLOT, struct.pack("<I", EN_ORIG), struct.pack("<I", e["en"])))   # VMT slot keeps its reloc
    P.append((CDD_SITE, rel(0xE8, CDD_SITE, CDD_FN), rel(0xE8, CDD_SITE, e["cdd"])))
    P.append((IMM_SITE, IMM_ORIG, rel(0xE9, IMM_SITE, e["imm"], 5)))
    P.append((ZONE, bytes(len(z)), z))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DLL, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    P = plan()
    rl = set()
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for en in blk.entries:
            if en.type == 3:
                rl.add(BASE + en.rva)
    bad = [hex(r) for r in rl if r != EN_SLOT and any(s - 3 <= r < s + len(o) for s, o, _ in P)]
    assert EN_SLOT in rl
    assert not any(d[off(G_CLOUD):off(G_CLOUD) + 4])
    sts = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        sts.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    print(", ".join("%#x %s" % (s, st) for (s, _, _), st in zip(P, sts)), "| relocs", bad or "none")
    if "OTHER" in sts or bad or len(set(sts)) != 1:
        print("ABORT (mixed/foreign state)"); return 1
    want = "vanilla" if revert else "ours"
    if sts[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    bak = bak_path(DLL, ".bak_cloudvar")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f:                 # in-place (house rule); zone first on apply
        for s, o, n in reversed(P):
            f.seek(off(s)); f.write(o if revert else n)
    d2 = open(DLL, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
