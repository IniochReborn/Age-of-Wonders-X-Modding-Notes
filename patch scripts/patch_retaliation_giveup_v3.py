#!/usr/bin/env python3
r"""
Retaliation give-up v3 (2026-10-22): a retaliating AI group abandons its chase right after the FIRST combat against
its marked target that ends with both sides standing (result 2, "Cannot inflict damage").  AoWEPACK.dll only.
Layers on build_defender_retaliation.py (v6.1) without touching it.  --apply upgrades v1 or v2 in place; --revert
accepts v1/v2/v3.

v2 BUG (live 10/22: "Exception occured during TArmyCombatMoveTE" on the first retaliation attack, then every later
attack "Combat already created" from 0x557787A9 because the aborted TE never tore the combat down):
v2 treated the real auto-combat object (class TFastCombat, cell 0x5571D77C, VMT 0x5571D7BC) as if it had the AI
PREDICTOR's layout and walked [combat+0x10] as a side list.  It does not: TFastCombat INHERITS TCombat (VMT-24 ->
cell 0x557170D4 = TCombat) and shares its layout ([+0xC] TCombatData, [+0x14] result, [+0x1C]/[+0x20] side wrappers,
combat objects with [+8] combat / [+0x4C] strategic unit).  The predictor ([agc+0x158]) is a different class whose
objects are TCombatPredictorUnit (cell 0x5571563C) - only THOSE have the [+4] unit / [+0x10] / [+0x4C] HP*100 layout.
(v1's crash was [TE+0x28], not a live TArmyHS on the fast path.)

v3 - one path for both combat classes, no TE access, no object walking:
  A  0x55749913  TArmyCombatMoveTE.CombatExecuted common exit (orig jmp c1 0x55811120), ebx = combat.
     result [combat+0x14] == 2 and IsClass(combat, TCombat) (true for TCombat and TFastCombat) ->
     attacker army from the map at combat-data pos2 ([[combat+0xC]+0x14/18/1C] -> GetFieldXYL 0x557020FC -> field
     vmt+0x80 FindChild(0x20217) -> [hs+0x1C]) - the exact lookup vanilla's own result != 3 branch (0x55749833) does,
     valid because with result 2 the attacker never moved.  Guards: IsClass(combat, TCombat); IsClass([combat+0xC],
     TCombatData self-ptr 0x55716E6C); pos2 x,y <= 0xFF, level <= 3 (unsigned); FindChild result IsClass TArmyHS
     (0x55713360) -> army -> IsClass TUnitList -> TArmy.GetGroup(army,0xFF) -> mark
     table entry with token != 0 -> token := 0 (the shipped homebound state: c5 stops force-adding, c2 deletes all
     targets, walk home, c3 demotes).  TE context, every machine -> table identical everywhere.
     No damage test: result 2 already means the attack failed (both sides alive); the per-combat damage flag
     0x558FAF24 is not trusted (shared damage sink).
  B  0x557D8CB8  stays the original `jmp c5` (v1's cave B retired in v2).

Data (BSS page slack 0x558FAAE0; was 0x558FAB00 until 10/23 - Wall of Flames collision): +0 result-2 combats, +4 TFastCombat among them, +8 groups sent home,
+0xC TCombat-check failures, +0x10 plain TCombat among them, +0x14 STAGE breadcrumb, +0x18 last combat object.
STAGE: 1 entered (any result) . 2 result 2 . 3 is a TCombat . 4 field found . 5 army HS found . 6 army ok .
       7 gu: TUnitList ok . 8 gu: group found . 9 gu: token zeroed; bit 0x10 OR-ed in on clean cave exit
       (e.g. 0x19 = sent home and left the cave; a value without 0x10 = died inside the cave at that step).
Zone 0x55837800-0x55837C00 (v1/v2's), header 'RGU3'.  Dry-run default; --apply / --revert / --dis / --read / --dll.
Backups: .bak_retgiveup (pre-v1), .bak_retgiveup3 (pre-v3).  LIFO: revert BEFORE build_defender_retaliation.py.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_retaliation_giveup_v1 as V1
import patch_retaliation_giveup_v2 as V2

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK1, BAK3 = ".bak_retgiveup", ".bak_retgiveup3"
CODE_V2F = V1.CODE_V2F
ZONE, ZONE_END = V1.ZONE, V1.ZONE_END
MAGIC = b"RGU3"
CAVE_A = ZONE + 0x40
SITE_A, OLD_A, SITE_B, OLD_B = V1.SITE_A, V1.OLD_A, V1.SITE_B, V1.OLD_B
TABLE, TABLE_END, MAPCELL = V1.TABLE, V1.TABLE_END, V1.MAPCELL
CNT = 0x558FAAE0   # 10/23: v1/v2 used 0x558FAB00 = ON TOP of Wall of Flames' TCombatFire clone header (built-flag [VMT-0x40] = 0x558FAB00); moved into the free span 0x558FAA42..0x558FAB00
ISCLASS, GETGROUP, GETFIELDXYL = V1.ISCLASS, V1.GETGROUP, V2.GETFIELDXYL
TCOMBAT_CELL, TFASTCOMBAT_CELL, TUNITLIST_CELL = 0x557170D4, V2.TFASTCOMBAT_CELL, V2.TUNITLIST_CELL
TCOMBATDATA_CELL = 0x55716E6C      # TCombatData VMT self-pointer (VMT-0x40; content = VMT 0x55716EAC, relocated)
TARMYHS_CELL = V1.TARMYHS_CELL     # 0x55713360 -> TArmyHS VMT
STAGE, LASTC = CNT + 0x14, CNT + 0x18


def st(n): return f"mov dword ptr [edi+{STAGE:#x}], {n:#x}"


def cave_a():
    return f"""
        pushfd
        pushad
        call a_pc
    a_pc:
        pop edi
        sub edi, {CAVE_A + 7:#x}
        {st(1)}
        cmp byte ptr [ebx+0x14], 2
        jne a_done
        {st(2)}
        mov dword ptr [edi+{LASTC:#x}], ebx
        inc dword ptr [edi+{CNT:#x}]
        mov eax, ebx
        mov edx, dword ptr [edi+{TCOMBAT_CELL:#x}]
        call {ISCLASS:#x}
        test al, al
        jne a_isc
        inc dword ptr [edi+{CNT + 0xC:#x}]
        jmp a_done
    a_isc:
        {st(3)}
        mov eax, ebx
        mov edx, dword ptr [edi+{TFASTCOMBAT_CELL:#x}]
        call {ISCLASS:#x}
        test al, al
        je a_plain
        inc dword ptr [edi+{CNT + 4:#x}]
        jmp a_look
    a_plain:
        inc dword ptr [edi+{CNT + 0x10:#x}]
    a_look:
        mov esi, dword ptr [ebx+0xc]
        test esi, esi
        je a_done
        mov eax, esi
        mov edx, dword ptr [edi+{TCOMBATDATA_CELL:#x}]
        call {ISCLASS:#x}
        test al, al
        je a_done
        cmp dword ptr [esi+0x14], 0xff
        ja a_done
        cmp dword ptr [esi+0x18], 0xff
        ja a_done
        cmp dword ptr [esi+0x1c], 3
        ja a_done
        push dword ptr [esi+0x1c]
        mov ecx, dword ptr [esi+0x18]
        mov edx, dword ptr [esi+0x14]
        mov eax, dword ptr [edi+{MAPCELL:#x}]
        mov eax, dword ptr [eax+0x10]
        call {GETFIELDXYL:#x}
        test eax, eax
        je a_done
        {st(4)}
        mov edx, 0x20217
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        je a_done
        mov esi, eax
        mov edx, dword ptr [edi+{TARMYHS_CELL:#x}]
        call {ISCLASS:#x}
        test al, al
        je a_done
        {st(5)}
        mov eax, dword ptr [esi+0x1c]
        test eax, eax
        je a_done
        {st(6)}
        call gu
    a_done:
        or dword ptr [edi+{STAGE:#x}], 0x10
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
        {st(7)}
        mov eax, ebx
        mov dl, 0xff
        call {GETGROUP:#x}
        test eax, eax
        je gu_out
        {st(8)}
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
        {st(9)}
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
    import ctypes, ctypes.wintypes as W, subprocess
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    pids = [int(p[1]) for p in ([x.strip('"') for x in l.split(",")] for l in out.splitlines()) if len(p) > 1 and p[0].lower() == "aowx.exe"]
    if not pids: print("AoWx not running"); return 0
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
        buf = ctypes.create_string_buffer(0x1C); n = ctypes.c_size_t()
        k32.ReadProcessMemory(h, ctypes.c_void_p(base - V1.BASE + CNT), buf, 0x1C, ctypes.byref(n))
        k32.CloseHandle(h)
        c = struct.unpack_from("<7I", buf.raw, 0)
        print("pid %d: result-2 combats %d (TFastCombat %d, TCombat %d, not-a-TCombat %d) | groups sent home %d | "
              "STAGE %#x | last combat %#010x" % (pid, c[0], c[1], c[4], c[3], c[2], c[5], c[6]))
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
    zone3, la = build()
    zone1, _, _ = V1.build()
    zone2, _ = V2.build()
    cur_a, cur_b = bytes(d[f(SITE_A):f(SITE_A) + 5]), bytes(d[f(SITE_B):f(SITE_B) + 5])
    cur_zone = bytes(d[f(ZONE):f(ZONE_END)])
    if cur_a == j(SITE_A, OLD_A) and cur_b == j(SITE_B, OLD_B) and not any(cur_zone): state = "pristine"
    elif cur_a == j(SITE_A, V1.CAVE_A) and cur_b == j(SITE_B, V1.CAVE_B) and cur_zone == zone1: state = "v1"
    elif cur_a == j(SITE_A, V2.CAVE_A) and cur_b == j(SITE_B, OLD_B) and cur_zone == zone2: state = "v2"
    elif cur_a == j(SITE_A, CAVE_A) and cur_b == j(SITE_B, OLD_B) and cur_zone == zone3: state = "v3"
    else: state = "UNKNOWN"
    rl = V1.reloc_set(d)
    bad = sorted(hex(x) for x in rl if ZONE <= x < ZONE_END or SITE_A - 3 <= x < SITE_A + 5 or SITE_B - 3 <= x < SITE_B + 5)
    print("state %s | cave A %#x (%d B of %d) | relocs at sites/zone %s | counters %#x"
          % (state, CAVE_A, la, ZONE_END - CAVE_A, bad or "none", CNT))

    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone3[CAVE_A - ZONE:CAVE_A - ZONE + la], CAVE_A): print("  %#x  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        return 0
    if bad or state == "UNKNOWN": print("ABORT: unexpected state"); return 1

    if a.revert:
        if state == "pristine": print("not applied - nothing to revert"); return 0
        d[f(SITE_A):f(SITE_A) + 5] = j(SITE_A, OLD_A)
        d[f(SITE_B):f(SITE_B) + 5] = j(SITE_B, OLD_B)
        d[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE)
        V1.write_inplace(path, bytes(d)); print("reverted (%s -> pristine)" % state); return 0
    if state == "v3": print("already applied (v3)"); return 0
    if not a.apply:
        print("Dry run OK (%s) - rerun with --apply (or --revert)." % ("fresh" if state == "pristine" else "upgrades %s in place" % state)); return 0

    bak = bak_path(path, BAK1 if state == "pristine" else BAK3)
    if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
    d[f(ZONE):f(ZONE_END)] = zone3
    d[f(SITE_A):f(SITE_A) + 5] = j(SITE_A, CAVE_A)
    d[f(SITE_B):f(SITE_B) + 5] = j(SITE_B, OLD_B)
    V1.write_inplace(path, bytes(d))
    chk = open(path, "rb").read()
    assert chk[f(ZONE):f(ZONE_END)] == zone3 and chk[f(SITE_A):f(SITE_A) + 5] == j(SITE_A, CAVE_A) \
        and chk[f(SITE_B):f(SITE_B) + 5] == j(SITE_B, OLD_B)
    print("Written and verified (v3)"); return 0


if __name__ == "__main__":
    sys.exit(main())
