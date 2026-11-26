#!/usr/bin/env python3
r"""
Retaliation give-up v2 (2026-10-22): a retaliating AI group abandons its chase right after the FIRST failed combat
against its marked target.  AoWEPACK.dll only.  Layers on build_defender_retaliation.py (v6.1) without touching it;
--apply upgrades a v1 install in place, --revert accepts v1 or v2.

v1 problems (live LAN test 10/22):
  1. Crash "Exception occured during TArmyCombatMoveTE" / VCL30 IsClass AV, read of 6E6E612B (ASCII): v1 cave A
     dereferenced [TE+0x28] as the attacker TArmyHS.  On the TFastCombat path CombatExecuted jumps straight to the
     exit and [TE+0x28] is not a live TArmyHS there -> IsClass walked freed memory.
  2. Gave up only after the SECOND failed attempt: the first (auto-combat = TFastCombat) attempt was never flagged
     because v1's attacker lookup failed on that path, and the give-up waited for a later predictor re-check.
v2: no TE access, no predictor re-check, no "attempted" table.  At the combat-end hook, on result 2 (both sides alive =
"Cannot inflict damage" in fast combat / round limit in tactical) the attacking marked group goes homebound at once.

Hook (only the existing `jmp cave` rel32 is re-pointed; the cave ends by jumping to the old target):
  A  0x55749913  TArmyCombatMoveTE.CombatExecuted common exit (orig jmp c1 0x55811120), ebx = combat object.
     result [combat+0x14] == 2, then by class (vanilla's own test: IsClass(combat, [0x5571D77C] TFastCombat)):
     * TFastCombat (auto-combat): same object layout as the AI predictor - side lists [+0xC]/[+0x10] (items +4,
       count +8), obj [+4] strategic unit, [+0x10] start HP*100, [+0x4C] cur HP*100, [+0x50]&2 dead.  Give up only if
       EVERY side-1 (defender) object is alive and undamaged (exact "could not deal damage" for this very combat);
       then every living side-0 object's army ([unit+4], IsClass TUnitList) gets its marked group sent home.
     * TCombat (tactical): attacker army from the map at combat-data pos2 ([[combat+0xC]+0x14/18/1C] -> GetFieldXYL
       0x557020FC -> field vmt+0x80 FindChild(0x20217) -> [hs+0x1C]) - the same lookup vanilla's own result != 3 branch
       (0x55749833) performs right before our hook, valid because with result 2 the attacker never moved.  Tactical
       result 2 = the full round limit passed with both sides standing; the damage flag 0x558FAF24 is not used (AI
       predictor sims share the damage sink, so it can be polluted).
     "Send home" = mark-table entry for TArmy.GetGroup(army,0xFF) id with token != 0 -> token := 0 = the shipped
     homebound state (c5 stops force-adding, c2 deletes all targets, walk home, c3 demotes to the old behaviour).
     Runs in TE context on every machine -> the mark table stays identical everywhere.
  B  0x557D8CB8  v1's TargetFoundEvent cave is retired: v2 restores the original `jmp c5`.

Data: CNT 0x558FAB00 (BSS page slack): +0 result-2 combats seen, +4 fast: no damage, +8 groups sent home,
+0xC fast: damage dealt, +0x10 tactical result-2.  Zone 0x55837800-0x55837C00 (v1's), header 'RGU2'.
Dry-run default; --apply / --revert / --dis / --read / --dll <copy>.  Backups: .bak_retgiveup (pre-v1), .bak_retgiveup2 (pre-v2).
LIFO: revert this BEFORE build_defender_retaliation.py.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_retaliation_giveup_v1 as V1

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK1, BAK2 = ".bak_retgiveup", ".bak_retgiveup2"
BASE, CODE_V2F = V1.BASE, V1.CODE_V2F
ZONE, ZONE_END = V1.ZONE, V1.ZONE_END
MAGIC = b"RGU2"
CAVE_A = ZONE + 0x40
SITE_A, OLD_A, SITE_B, OLD_B = V1.SITE_A, V1.OLD_A, V1.SITE_B, V1.OLD_B
TABLE, TABLE_END, CNT, MAPCELL = V1.TABLE, V1.TABLE_END, V1.CNT, V1.MAPCELL
ISCLASS, GETGROUP = V1.ISCLASS, V1.GETGROUP
TFASTCOMBAT_CELL, TUNITLIST_CELL = 0x5571D77C, 0x55710E88
GETFIELDXYL = 0x557020FC


def cave_a():
    return f"""
        pushfd
        pushad
        call a_pc
    a_pc:
        pop edi
        sub edi, {CAVE_A + 7:#x}
        cmp byte ptr [ebx+0x14], 2
        jne a_done
        inc dword ptr [edi+{CNT:#x}]
        mov eax, ebx
        mov edx, dword ptr [edi+{TFASTCOMBAT_CELL:#x}]
        call {ISCLASS:#x}
        test al, al
        je a_tac
        mov eax, dword ptr [ebx+0x10]
        test eax, eax
        je a_done
        mov ecx, dword ptr [eax+8]
        test ecx, ecx
        jle a_done
        mov edx, dword ptr [eax+4]
    a_def:
        dec ecx
        js a_nodmg
        mov esi, dword ptr [edx+ecx*4]
        test byte ptr [esi+0x50], 2
        jne a_dmg
        mov ebp, dword ptr [esi+0x4c]
        cmp ebp, dword ptr [esi+0x10]
        jl a_dmg
        jmp a_def
    a_dmg:
        inc dword ptr [edi+{CNT + 0xC:#x}]
        jmp a_done
    a_nodmg:
        inc dword ptr [edi+{CNT + 4:#x}]
        mov eax, dword ptr [ebx+0xc]
        test eax, eax
        je a_done
        mov ecx, dword ptr [eax+8]
        mov edx, dword ptr [eax+4]
    a_att:
        dec ecx
        js a_done
        mov esi, dword ptr [edx+ecx*4]
        test byte ptr [esi+0x50], 2
        jne a_att
        mov eax, dword ptr [esi+4]
        test eax, eax
        je a_att
        mov eax, dword ptr [eax+4]
        test eax, eax
        je a_att
        push ecx
        push edx
        call gu
        pop edx
        pop ecx
        jmp a_att
    a_tac:
        inc dword ptr [edi+{CNT + 0x10:#x}]
        mov esi, dword ptr [ebx+0xc]
        test esi, esi
        je a_done
        push dword ptr [esi+0x1c]
        mov ecx, dword ptr [esi+0x18]
        mov edx, dword ptr [esi+0x14]
        mov eax, dword ptr [edi+{MAPCELL:#x}]
        mov eax, dword ptr [eax+0x10]
        call {GETFIELDXYL:#x}
        test eax, eax
        je a_done
        mov edx, 0x20217
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        je a_done
        mov eax, dword ptr [eax+0x1c]
        test eax, eax
        je a_done
        call gu
    a_done:
        popad
        popfd
        jmp {OLD_A:#x}

    gu:
        push ebx
        mov ebx, eax
        mov edx, dword ptr [edi+{TUNITLIST_CELL:#x}]
        call {ISCLASS:#x}
        test al, al
        je gu_out
        mov eax, ebx
        mov dl, 0xff
        call {GETGROUP:#x}
        test eax, eax
        je gu_out
        mov edx, dword ptr [eax+0x24]
        test edx, edx
        je gu_out
        xor ecx, ecx
    gu_scan:
        cmp ecx, {TABLE_END:#x}
        jge gu_out
        cmp dword ptr [edi+ecx+{TABLE:#x}], edx
        je gu_hit
        add ecx, 0x10
        jmp gu_scan
    gu_hit:
        cmp dword ptr [edi+ecx+{TABLE + 4:#x}], 0
        je gu_out
        mov dword ptr [edi+ecx+{TABLE + 4:#x}], 0
        inc dword ptr [edi+{CNT + 8:#x}]
    gu_out:
        pop ebx
        ret
    """


def build():
    a = V1.asm(cave_a(), CAVE_A)
    assert CAVE_A + len(a) <= ZONE_END, len(a)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    z[4:8] = struct.pack("<i", OLD_A - (SITE_A + 5))
    z[CAVE_A - ZONE:CAVE_A - ZONE + len(a)] = a
    return bytes(z), len(a)


def read_live():
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    import subprocess
    # reuse v1's process/module walk, then print v2 labels
    pids = []
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split(",")]
        if len(parts) > 1 and parts[0].lower() == "aowx.exe": pids.append(int(parts[1]))
    if not pids: print("AoWx not running"); return 0
    import ctypes.wintypes as W
    class ME32(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("th32ModuleID", W.DWORD), ("th32ProcessID", W.DWORD), ("GlblcntUsage", W.DWORD),
                    ("ProccntUsage", W.DWORD), ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", W.DWORD), ("hModule", W.HMODULE),
                    ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * 260)]
    for pid in pids:
        ms = k32.CreateToolhelp32Snapshot(0x18, pid)
        me = ME32(); me.dwSize = ctypes.sizeof(me); base = None
        ok = k32.Module32First(ms, ctypes.byref(me))
        while ok:
            if me.szModule.lower() == b"aowepack.dll": base = me.modBaseAddr
            ok = k32.Module32Next(ms, ctypes.byref(me))
        k32.CloseHandle(ms)
        if base is None: print("pid %d: AoWEPACK not found" % pid); continue
        h = k32.OpenProcess(0x0410, False, pid)
        buf = ctypes.create_string_buffer(0x14); n = ctypes.c_size_t()
        k32.ReadProcessMemory(h, ctypes.c_void_p(base - BASE + CNT), buf, 0x14, ctypes.byref(n))
        k32.CloseHandle(h)
        c = struct.unpack_from("<5I", buf.raw, 0)
        print("pid %d: result-2 combats %d | fast no-damage %d | groups sent home %d | fast damage-dealt %d | tactical result-2 %d"
              % ((pid,) + c))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    ap.add_argument("--read", action="store_true")
    a = ap.parse_args()
    if a.read: return read_live()

    path = a.dll
    d = bytearray(open(path, "rb").read())
    f = lambda va: va - CODE_V2F
    j = V1.jmp_to
    zone2, la = build()
    zone1, _, _ = V1.build()
    cur_a, cur_b = bytes(d[f(SITE_A):f(SITE_A) + 5]), bytes(d[f(SITE_B):f(SITE_B) + 5])
    cur_zone = bytes(d[f(ZONE):f(ZONE_END)])
    if cur_a == j(SITE_A, OLD_A) and cur_b == j(SITE_B, OLD_B) and not any(cur_zone): state = "pristine"
    elif cur_a == j(SITE_A, V1.CAVE_A) and cur_b == j(SITE_B, V1.CAVE_B) and cur_zone == zone1: state = "v1"
    elif cur_a == j(SITE_A, CAVE_A) and cur_b == j(SITE_B, OLD_B) and cur_zone == zone2: state = "v2"
    else: state = "UNKNOWN"
    rl = V1.reloc_set(d)
    bad = sorted(hex(x) for x in rl if ZONE <= x < ZONE_END or SITE_A - 3 <= x < SITE_A + 5 or SITE_B - 3 <= x < SITE_B + 5)
    print("state %s | cave A %#x (%d B of %d) | relocs at sites/zone %s | counters %#x"
          % (state, CAVE_A, la, ZONE_END - CAVE_A, bad or "none", CNT))

    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone2[CAVE_A - ZONE:CAVE_A - ZONE + la], CAVE_A): print("  %#x  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        return 0
    if bad or state == "UNKNOWN": print("ABORT: unexpected state"); return 1

    if a.revert:
        if state == "pristine": print("not applied - nothing to revert"); return 0
        d[f(SITE_A):f(SITE_A) + 5] = j(SITE_A, OLD_A)
        d[f(SITE_B):f(SITE_B) + 5] = j(SITE_B, OLD_B)
        d[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE)
        V1.write_inplace(path, bytes(d)); print("reverted (%s -> pristine)" % state); return 0
    if state == "v2": print("already applied (v2)"); return 0
    if not a.apply:
        print("Dry run OK (%s) - rerun with --apply (or --revert)." % ("upgrades v1 in place" if state == "v1" else "fresh")); return 0

    bak = bak_path(path, BAK1 if state == "pristine" else BAK2)
    if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
    d[f(ZONE):f(ZONE_END)] = zone2
    d[f(SITE_A):f(SITE_A) + 5] = j(SITE_A, CAVE_A)
    d[f(SITE_B):f(SITE_B) + 5] = j(SITE_B, OLD_B)
    V1.write_inplace(path, bytes(d))
    chk = open(path, "rb").read()
    assert chk[f(ZONE):f(ZONE_END)] == zone2 and chk[f(SITE_A):f(SITE_A) + 5] == j(SITE_A, CAVE_A) \
        and chk[f(SITE_B):f(SITE_B) + 5] == j(SITE_B, OLD_B)
    print("Written and verified (v2)"); return 0


if __name__ == "__main__":
    sys.exit(main())
