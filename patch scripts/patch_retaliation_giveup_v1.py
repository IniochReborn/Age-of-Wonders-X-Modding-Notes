#!/usr/bin/env python3
r"""
Retaliation give-up v1 (2026-10-22): a retaliating AI group abandons its chase after a FAILED attempt in which it
could not damage the marked target.  AoWEPACK.dll only.  Layers on build_defender_retaliation.py (v6.1, 5 hooks,
caves 0x55811120-0x5581168F) without touching it.

User report: an AI group retaliating against e.g. an Incarnate with physical immunity keeps attacking forever
("spamming combat"), every combat ending as fast-combat result 2 "Cannot inflict damage" (both sides alive).  The
retaliation c5 cave force-adds the marked target past the combat predictor, so the group never gives up.

Mechanism (both hooks only re-point an existing `jmp cave` rel32; each new cave keeps every register/flag and ends
by jumping to the old cave):
  A  0x55749913  TArmyCombatMoveTE.CombatExecuted common exit (currently jmp c1 0x55811120), ebx = combat,
     [esp] = TE.  If result [combat+0x14] == 2 (both sides survived; attacker army guaranteed alive) and the attacker
     army ([TE+0x28] = TArmyHS, IsClass-checked; TArmy = [hs+0x1C]) belongs to a MARKED retaliation group
     (TArmy.GetGroup(army,0xFF) -> [grp+0x24] id found in the mark table with token != 0), the slot is flagged
     "attempted" = {group id, mark token} in ATT.  Runs in TE context on every machine (lockstep).
  B  0x557D8CB8  TGuardAreaAGC.TargetFoundEvent entry (currently jmp c5 0x55811595), eax = AGC, ecx = target.
     If this group's slot is flagged attempted (id AND token still match the table entry), and the candidate target
     IS the marked unit's hex (same resolve as c5: token -> [M+0xFC] 0x5577E948 -> GetLocation 0x5577ED94), the
     vanilla combat predictor is run for it (0x55738E8C setup + 0x5572B028 TFastCombat run, exactly what vanilla's
     TargetFoundEvent does for every other target).  If the simulation leaves EVERY side-1 (target-side) object
     undamaged ([obj+0x4C] cur HP*100 >= [obj+0x10] start HP*100, [obj+0x50]&2 dead bit clear) the group could not
     inflict damage -> the table token is zeroed = the shipped "homebound" state: c5 no longer force-adds, c2 deletes
     all targets, the group walks home and c3 demotes it to its pre-retaliation behaviour.  Otherwise (some damage
     possible, e.g. the lone-leader case) nothing changes.  Either way control continues into c5.
  Only the group that actually attacked and failed gives up; other cohort members give up after their own failed
  attempt.  "Cannot damage" = the same TFastCombat simulation the engine uses for auto-combat, so after one
  failed attempt the next is predicted to fail identically.

Data (BSS page slack, verified unreferenced; the retaliation table is 0x558FA800-0x558FAA00, scratch 0x558FAA00):
  CNT 0x558FAB00: +0 attempts flagged, +4 predictor checks, +8 give-ups, +0xC damage-possible
  ATT 0x558FAB10..0x558FAC10: 32 x {group id, mark token}, slot i <-> table entry i (stride 8 vs 16)
Zone: AoWEPACK CODE 0x55837800-0x55837C00 (verified zero, no relocs, no references; Leader's Soul ends 0x55837800,
borrowtime starts 0x55838000).  Header 'RGU1' + both sites' original rel32.

Dry-run default; --apply / --revert / --dis / --read (counters from the running game) / --dll <copy>.
Backup: backup\AoWEPACK.dll.bak_retgiveup.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_retgiveup"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55837800, 0x55837C00
MAGIC = b"RGU1"
CAVE_A, CAVE_B = ZONE + 0x40, ZONE + 0x100

SITE_A, OLD_A = 0x55749913, 0x55811120          # jmp c1 (retaliation combat-end cave)
SITE_B, OLD_B = 0x557D8CB8, 0x55811595          # jmp c5 (retaliation TargetFoundEvent cave)

TABLE, TABLE_END = 0x558FA800, 0x200            # 32 x 16 B {id, marktoken, orig, ownunit}
CNT, ATT = 0x558FAB00, 0x558FAB10               # ours (BSS page slack)
MAPCELL = 0x558FA040
TARMYHS_CELL = 0x55713360
ISCLASS, GETGROUP = 0x557010C0, 0x5578C4A0
TOKEN2UNIT, GETLOC = 0x5577E948, 0x5577ED94
PRED_SETUP, PRED_RUN = 0x55738E8C, 0x5572B028


def asm(src, va):
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)
    return bytes(enc)


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
        mov eax, dword ptr [esp+0x24]
        test eax, eax
        je a_done
        mov esi, dword ptr [eax+0x28]
        test esi, esi
        je a_done
        mov eax, esi
        mov edx, dword ptr [edi+{TARMYHS_CELL:#x}]
        call {ISCLASS:#x}
        test al, al
        je a_done
        mov eax, dword ptr [esi+0x1c]
        test eax, eax
        je a_done
        mov dl, 0xff
        call {GETGROUP:#x}
        test eax, eax
        je a_done
        mov edx, dword ptr [eax+0x24]
        test edx, edx
        je a_done
        xor ecx, ecx
    a_scan:
        cmp ecx, {TABLE_END:#x}
        jge a_done
        cmp dword ptr [edi+ecx+{TABLE:#x}], edx
        je a_hit
        add ecx, 0x10
        jmp a_scan
    a_hit:
        mov eax, dword ptr [edi+ecx+{TABLE + 4:#x}]
        test eax, eax
        je a_done
        shr ecx, 1
        mov dword ptr [edi+ecx+{ATT:#x}], edx
        mov dword ptr [edi+ecx+{ATT + 4:#x}], eax
        inc dword ptr [edi+{CNT:#x}]
    a_done:
        popad
        popfd
        jmp {OLD_A:#x}
    """


def cave_b():
    return f"""
        pushfd
        pushad
        call b_pc
    b_pc:
        pop edi
        sub edi, {CAVE_B + 7:#x}
        mov ebp, dword ptr [esp+0x1c]
        mov esi, dword ptr [esp+0x18]
        mov eax, dword ptr [ebp+0xc]
        test eax, eax
        je b_done
        mov edx, dword ptr [eax+0x24]
        test edx, edx
        je b_done
        xor ecx, ecx
    b_scan:
        cmp ecx, {TABLE_END:#x}
        jge b_done
        cmp dword ptr [edi+ecx+{TABLE:#x}], edx
        je b_hit
        add ecx, 0x10
        jmp b_scan
    b_hit:
        mov eax, dword ptr [edi+ecx+{TABLE + 4:#x}]
        test eax, eax
        je b_done
        mov ebx, ecx
        shr ebx, 1
        cmp dword ptr [edi+ebx+{ATT:#x}], edx
        jne b_done
        cmp dword ptr [edi+ebx+{ATT + 4:#x}], eax
        jne b_done
        push ecx
        push ebx
        mov edx, eax
        mov eax, dword ptr [edi+{MAPCELL:#x}]
        mov eax, dword ptr [eax+0xfc]
        call {TOKEN2UNIT:#x}
        test eax, eax
        je b_pop
        sub esp, 4
        lea edx, [esp+2]
        push edx
        lea ecx, [esp+5]
        lea edx, [esp+4]
        call {GETLOC:#x}
        mov eax, dword ptr [esp]
        add esp, 4
        and eax, 0xffffff
        mov edx, dword ptr [esi+0x30]
        and edx, 0xffffff
        cmp eax, edx
        jne b_pop
        inc dword ptr [edi+{CNT + 4:#x}]
        mov eax, ebp
        mov edx, esi
        call {PRED_SETUP:#x}
        mov eax, dword ptr [ebp+0x158]
        call {PRED_RUN:#x}
        mov eax, dword ptr [ebp+0x158]
        mov eax, dword ptr [eax+0x10]
        test eax, eax
        je b_dmg
        mov ecx, dword ptr [eax+8]
        test ecx, ecx
        jle b_dmg
        mov edx, dword ptr [eax+4]
    b_obj:
        dec ecx
        js b_zero
        mov eax, dword ptr [edx+ecx*4]
        test byte ptr [eax+0x50], 2
        jne b_dmg
        mov ebx, dword ptr [eax+0x4c]
        cmp ebx, dword ptr [eax+0x10]
        jl b_dmg
        jmp b_obj
    b_zero:
        pop ebx
        pop ecx
        mov dword ptr [edi+ecx+{TABLE + 4:#x}], 0
        mov dword ptr [edi+ebx+{ATT:#x}], 0
        mov dword ptr [edi+ebx+{ATT + 4:#x}], 0
        inc dword ptr [edi+{CNT + 8:#x}]
        jmp b_done
    b_dmg:
        inc dword ptr [edi+{CNT + 0xC:#x}]
    b_pop:
        pop ebx
        pop ecx
    b_done:
        popad
        popfd
        jmp {OLD_B:#x}
    """


def build():
    a = asm(cave_a(), CAVE_A)
    b = asm(cave_b(), CAVE_B)
    assert CAVE_A + len(a) <= CAVE_B and CAVE_B + len(b) <= ZONE_END, (len(a), len(b))
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    z[4:8] = struct.pack("<i", OLD_A - (SITE_A + 5))
    z[8:12] = struct.pack("<i", OLD_B - (SITE_B + 5))
    z[CAVE_A - ZONE:CAVE_A - ZONE + len(a)] = a
    z[CAVE_B - ZONE:CAVE_B - ZONE + len(b)] = b
    return bytes(z), len(a), len(b)


def jmp_to(va, tgt): return b"\xe9" + struct.pack("<i", tgt - (va + 5))


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def read_live():
    import ctypes, ctypes.wintypes as W
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    TH32CS_SNAPPROCESS, TH32CS_SNAPMODULE, TH32CS_SNAPMODULE32 = 2, 8, 0x10
    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", W.DWORD), ("szExeFile", ctypes.c_char * 260)]
    class ME32(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("th32ModuleID", W.DWORD), ("th32ProcessID", W.DWORD), ("GlblcntUsage", W.DWORD),
                    ("ProccntUsage", W.DWORD), ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", W.DWORD), ("hModule", W.HMODULE),
                    ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * 260)]
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE32(); pe.dwSize = ctypes.sizeof(pe); pids = []
    ok = k32.Process32First(snap, ctypes.byref(pe))
    while ok:
        if pe.szExeFile.lower() == b"aowx.exe": pids.append(pe.th32ProcessID)
        ok = k32.Process32Next(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    if not pids: print("AoWx not running"); return 0
    for pid in pids:
        ms = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
        me = ME32(); me.dwSize = ctypes.sizeof(me); base = None
        ok = k32.Module32First(ms, ctypes.byref(me))
        while ok:
            if me.szModule.lower() == b"aowepack.dll": base = me.modBaseAddr
            ok = k32.Module32Next(ms, ctypes.byref(me))
        k32.CloseHandle(ms)
        if base is None: print("pid %d: AoWEPACK not found" % pid); continue
        h = k32.OpenProcess(0x0410, False, pid)
        buf = ctypes.create_string_buffer(0x110); n = ctypes.c_size_t()
        k32.ReadProcessMemory(h, ctypes.c_void_p(base - BASE + CNT), buf, 0x110, ctypes.byref(n))
        k32.CloseHandle(h)
        c = struct.unpack_from("<4I", buf.raw, 0)
        att = [struct.unpack_from("<2I", buf.raw, 0x10 + 8 * i) for i in range(32)]
        print("pid %d: attempts flagged %d | predictor checks %d | give-ups %d | damage-possible %d | attempted slots %s"
              % ((pid,) + c + ([(i, "%#x/%#x" % e) for i, e in enumerate(att) if e[0]] or "none",)))
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
    zone, la, lb = build()
    cur_a, cur_b = bytes(d[f(SITE_A):f(SITE_A) + 5]), bytes(d[f(SITE_B):f(SITE_B) + 5])
    cur_zone = bytes(d[f(ZONE):f(ZONE_END)])
    st_a = "orig" if cur_a == jmp_to(SITE_A, OLD_A) else ("ours" if cur_a == jmp_to(SITE_A, CAVE_A) else "OTHER")
    st_b = "orig" if cur_b == jmp_to(SITE_B, OLD_B) else ("ours" if cur_b == jmp_to(SITE_B, CAVE_B) else "OTHER")
    zst = "zero" if not any(cur_zone) else ("ours" if cur_zone == zone else "DIFFERS")
    rl = reloc_set(d)
    bad = sorted(hex(x) for x in rl if ZONE <= x < ZONE_END or SITE_A - 3 <= x < SITE_A + 5 or SITE_B - 3 <= x < SITE_B + 5)
    print("site A %s | site B %s | zone %s (A %d B, B %d B of %d) | relocs at sites/zone %s"
          % (st_a, st_b, zst, la, lb, ZONE_END - ZONE, bad or "none"))
    print("caves: A=%#x B=%#x | counters %#x, attempted table %#x" % (CAVE_A, CAVE_B, CNT, ATT))

    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for nm, va, n in (("A", CAVE_A, la), ("B", CAVE_B, lb)):
            print("--- cave", nm)
            for i in md.disasm(zone[va - ZONE:va - ZONE + n], va): print("  %#x  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        return 0
    if bad or "OTHER" in (st_a, st_b) or zst == "DIFFERS": print("ABORT: unexpected state"); return 1
    applied = (st_a, st_b, zst) == ("ours", "ours", "ours")
    pristine = (st_a, st_b, zst) == ("orig", "orig", "zero")

    if a.revert:
        if pristine: print("not applied - nothing to revert"); return 0
        if not applied: print("ABORT: cannot revert a partial install"); return 1
        d[f(SITE_A):f(SITE_A) + 5] = jmp_to(SITE_A, OLD_A)
        d[f(SITE_B):f(SITE_B) + 5] = jmp_to(SITE_B, OLD_B)
        d[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE)
        write_inplace(path, bytes(d)); print("reverted"); return 0
    if applied: print("already applied"); return 0
    if not pristine: print("ABORT: partial state"); return 1
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0

    bak = bak_path(path, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
    d[f(ZONE):f(ZONE_END)] = zone
    d[f(SITE_A):f(SITE_A) + 5] = jmp_to(SITE_A, CAVE_A)
    d[f(SITE_B):f(SITE_B) + 5] = jmp_to(SITE_B, CAVE_B)
    write_inplace(path, bytes(d))
    chk = open(path, "rb").read()
    assert chk[f(ZONE):f(ZONE_END)] == zone and chk[f(SITE_A):f(SITE_A) + 5] == jmp_to(SITE_A, CAVE_A) \
        and chk[f(SITE_B):f(SITE_B) + 5] == jmp_to(SITE_B, CAVE_B)
    print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
