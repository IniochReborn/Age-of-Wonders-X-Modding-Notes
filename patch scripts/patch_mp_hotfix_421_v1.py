r"""
1.37.421 MP HOTFIX v1 (2026-10-21).  AoWEPACK.dll only.

User: LAN OOS in a clean 1.37.420 shortly after the turn starts (AI players + many roaming independents); every machine
went OOS, and a full relaunch on all machines did not help.  User rule: no reverts, fix forward.

FIX A - superstack must not read machine-local timing
  patch_ai_superstack_v1 merges armies with AoWE.MoveArmyXYL 0x5574A490, the HUMAN click path (no vanilla AoWEPACK code
  calls it).  XYL hands its [ebp+8] flag to MoveArmyEx 0x5574A318, which with flag 0 refuses the move when
  TPlayer.GetBusy 0x557516D0 says busy.  GetBusy reads [map+0x120] = the combat in progress (set by
  TAoWHSMap.CreateCombat +23, cleared by DestroyCombat), which starts and ends at a different moment on each machine.
  A refusal makes the cave end the day (count := MAXMOVES), so the AIs diverge.  Every vanilla MoveArmyEx caller with
  flag 0 is human UI (TSelectedArmy.ExecuteMove, GlobalTargetSpells, TCave.EnterEx).
  -> the two `push 0` (flag) before the XYL calls @0x55819781 / 0x558197D3 become `push 1`: MoveArmyEx skips GetBusy
  and goes straight to the path check, so a refusal now depends on game state only (no path) and is identical on every
  peer; ending the day on refusal stays (prevents an endless retry of the same refused move).  The cave only runs while
  the AI's TE queue is idle (TAIPlayerControl), and the TE is queued on that player's queue as before.

FIX B - per-game AI state reset
  The 410/420 AI caves keep day/site-keyed state in AoWEPACK .idata page slack (beyond raw data 0x5590B200 -> zero only
  at process start; never saved, never reset), so a second game or a reload in the same session starts with stale
  entries on some machines.  Chained onto build_defender_retaliation's TAoWHSMap.Create cave (entry hook 0x557748A4 ->
  0x5581165F, which already clears its own table): its tail `jmp 0x557748AA` @0x5581168A -> this cave, which zeroes
      0x5590B420..0x5590B4A0  site-loot-for-leaders table C          (patch_ai_siteloot_leader_v1)
      0x5590B510..0x5590B5E0  leader-safety/converge table B + superstack day counter
      0x5590BC80..0x5590BD00  converge wait table A
      0x5590BD20..0x5590BE24  site-recruit tag cache
      0x5590BE50..0x5590BEC0  end-turn enchant per-player state
      0x5590BF40..0x5590BF80  diplomacy deferred actions (PEND)
  and then jumps on to 0x557748AA.  Untouched on purpose: the smokescreen VMT clone 0x5590B200..B350, ALLOW_SRC/
  PLACE_FLAG B500/B504, smokescreen W B600..BB60, band buffer BB80, essence/diag BD00/BD10, globals BE40 (TStringList),
  G_SEQ/G_DESC BEC0..BF00, tame STASH BF80, and the per-call slots BFC0/BFE0/BFF0.
  eax/ecx/edx (Create's self / alloc flag) are preserved; data reached via call/pop delta (rebase-safe).

Zone AoWEPACK 0x55833000..0x55833100 ('MPH1' header; verified zero, reloc-free, unclaimed by any script).
Dry-run default; --apply / --revert / --dis.  Backup <game>\backup\AoWEPACK.dll.bak_mphotfix421.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55833000, 0x55833100
CODE = ZONE + 0x10
MAGIC = b"MPH1"

FLAG_SITES = (0x55819781, 0x558197D3)                 # superstack `push 0` before MoveArmyXYL
FLAG_OLD, FLAG_NEW = bytes.fromhex("6a00"), bytes.fromhex("6a01")
CHAIN = 0x5581168A                                    # defender-retaliation Create cave tail jmp
CREATE_CONT = 0x557748AA
RANGES = ((0x5590B420, 0x5590B4A0), (0x5590B510, 0x5590B5E0), (0x5590BC80, 0x5590BD00),
          (0x5590BD20, 0x5590BE24), (0x5590BE50, 0x5590BEC0), (0x5590BF40, 0x5590BF80))


def rel_jmp(src, dst):
    return b"\xe9" + struct.pack("<i", dst - (src + 5))


def build():
    lines = ["push eax", "push ecx", "push edx", "push edi",
             "call here", "here:", "pop edx", "sub edx, %#x" % (CODE + 9)]   # 4 pushes (4 B) + call (5 B)
    for i, (lo, hi) in enumerate(RANGES):
        assert (hi - lo) % 4 == 0
        lines += ["lea edi, [edx+%#x]" % lo, "mov ecx, %d" % ((hi - lo) // 4), "xor eax, eax",
                  "z%d:" % i, "mov dword ptr [edi], eax", "add edi, 4", "dec ecx", "jnz z%d" % i]
    lines += ["pop edi", "pop edx", "pop ecx", "pop eax", "jmp %#x" % CREATE_CONT]
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm("\n".join(lines), CODE)
    code = bytes(code)
    # the delta base must be the address right after the call
    off = code.find(b"\xe8\x00\x00\x00\x00")
    assert off == 4 and CODE + off + 5 == CODE + 9, off
    zone = MAGIC + bytes(12) + code
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return zone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    rd = lambda lo, hi: bytes(d[lo - V2F:hi - V2F])
    zone = build()
    jmp_old, jmp_new = rel_jmp(CHAIN, CREATE_CONT), rel_jmp(CHAIN, CODE)

    flags = [rd(s, s + 2) for s in FLAG_SITES]
    fst = "v1" if all(f == FLAG_NEW for f in flags) else "vanilla" if all(f == FLAG_OLD for f in flags) else "OTHER %s" % flags
    ch = rd(CHAIN, CHAIN + 5)
    cst = "v1" if ch == jmp_new else "vanilla" if ch == jmp_old else "OTHER " + ch.hex()
    zl = rd(ZONE, ZONE_END)
    zst = "v1" if zl[:len(zone)] == zone else "zero" if not any(zl) else "OTHER"
    rl = relocs(bytes(d), BASE)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(s - 3 <= r < s + 2 for s in FLAG_SITES)
           or CHAIN - 3 <= r < CHAIN + 5]
    print("superstack flags %s | Create chain @%#x %s | zone %#x %s (%d B) | relocs at sites %s"
          % (fst, CHAIN, cst, ZONE, zst, len(zone), bad or "none"))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(zone[0x10:], CODE):
            print("  %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad:
        print("ABORT: relocation entries under patched bytes"); return 1
    if a.revert:
        if (fst, cst) == ("vanilla", "vanilla"):
            print("already reverted"); return 0
        if fst != "v1" or cst != "v1" or zst != "v1":
            print("ABORT: not in the v1 state - refusing a partial revert"); return 1
        for s in FLAG_SITES: d[s - V2F:s - V2F + 2] = FLAG_OLD
        d[CHAIN - V2F:CHAIN - V2F + 5] = jmp_old
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        if (fst, cst, zst) == ("v1", "v1", "v1"):
            print("already applied"); return 0
        if fst != "vanilla" or cst != "vanilla" or zst != "zero":
            print("ABORT: unexpected state (needs superstack v1 + defender-retaliation Create cave, zone zero)"); return 1
        for s in FLAG_SITES: d[s - V2F:s - V2F + 2] = FLAG_NEW
        d[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        d[CHAIN - V2F:CHAIN - V2F + 5] = jmp_new
    if not (a.apply or a.revert):
        print("Dry run OK - rerun with --apply."); return 0
    bak = bak_path(a.dll, ".bak_mphotfix421")
    if a.apply and not os.path.exists(bak):
        shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f:
        f.seek(0); f.write(d)
    print("reverted" if a.revert else "applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
