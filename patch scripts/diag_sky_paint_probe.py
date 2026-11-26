#!/usr/bin/env python3
r"""
DIAGNOSTIC (2026-11-01) - why Sky <-> Clear Sky won't paint over each other in the editor.  REVERT BEFORE RELEASE.

Counters in HSEPack DATA slack 0x5562E720.. (cave 0x5561CF80 'SKD1'):
  c0 hexagon ChangeTerrain bypass entered (0x5561CA5E)        c1 ... with old == new == 0xE (Sky/Clear same terrain)
  c2 ... and the paint gate was set                            c4 MsgProc case 0 (change terrain, gated)
  c5 MsgProc case 1 (clear terrain, gated)                    c6 palette rnd-hexagon brush path (0x5561A9DF, ungated)
  last: RID of the hexagon's resource, brush Clear flag, gate (at the last c1 hit).
  --apply / --revert (backup .bak_skydiag, HSEPack.dpl); --read = print the counters from the running AoWDevX.exe
  (the editor runs elevated -> run --read from an elevated prompt, output also written to sky_probe.txt).
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402

TAG = ".bak_skydiag"
HBASE = 0x55600000
HA, HB = 0x5562E800, 0x5562EC00      # v2: histograms of the hexagon's current terrain (al) / the new terrain ([esi])
CNT = 0x5562E720                      # c0..c6 dwords, then last_rid, last_flag, last_gate
GATE, FLAG = 0x5562E5F1, 0x5562E5F0
CAVE, CAVE_END, MAGIC = 0x5561CF80, 0x5561D100, b"SKD1"
CT = 0x5561CA5E                       # 3a06 7549 3c0e   (cmp al,[esi]; jne caab; cmp al,0xe)
CT_ORIG = bytes.fromhex("3a0675493c0e")
CASE0 = 0x55612989                    # jmp pc1 (sky polish v4)
CASE1 = 0x556129AD                    # jmp SCG1 (patch_sky_clear_mode_gate_v1)
RND, RND_ORIG, RND_BACK = 0x5561A9DF, bytes.fromhex("ff97d0000000"), 0x5561A9E5


def hse_file():
    from bakpath import game_file
    return game_file("HSEPack.dpl")


def patches(d, pe):
    import sky_clouds_overlay_asm as OV
    off = lambda va: pe.get_offset_from_rva(va - HBASE)  # noqa: E731
    rel = lambda at: at + 5 + struct.unpack_from("<i", d, off(at) + 1)[0]  # noqa: E731
    assert d[off(CASE0)] == 0xE9 and d[off(CASE1)] == 0xE9, "sky polish v4 / clear-mode gate not applied"
    pc1, scg = 0x5561CAB0, 0x5561CF04                 # sky polish v4 pc1 / clear-mode gate SCG1 entries
    at = CAVE + len(MAGIC)

    def pic(lbl):
        return f"call {lbl}\n{lbl}:\n pop ecx\n sub ecx, {lbl}\n"
    src = f"""
    ctd:
        push ecx
        push edx
        {pic('p0')}
        inc dword ptr [ecx + {CNT:#x}]
        movzx edx, al
        inc dword ptr [ecx + edx*4 + {HA:#x}]
        movzx edx, byte ptr [esi]
        inc dword ptr [ecx + edx*4 + {HB:#x}]
        cmp al, byte ptr [esi]
        jne ct_x
        cmp al, 0xe
        jne ct_x
        inc dword ptr [ecx + {CNT + 4:#x}]
        movzx edx, byte ptr [ecx + {GATE:#x}]
        add dword ptr [ecx + {CNT + 8:#x}], edx
        mov dword ptr [ecx + {CNT + 0x24:#x}], edx
        movzx edx, byte ptr [ecx + {FLAG:#x}]
        mov dword ptr [ecx + {CNT + 0x20:#x}], edx
        mov edx, dword ptr [ebx + 8]
        mov edx, dword ptr [edx + 0xc]
        mov dword ptr [ecx + {CNT + 0x1c:#x}], edx
    ct_x:
        pop edx
        pop ecx
        cmp al, byte ptr [esi]
        jne {CT + 0x4D:#x}
        cmp al, 0xe
        jmp {CT + 6:#x}
    c0d:
        push ecx
        {pic('p1')}
        inc dword ptr [ecx + {CNT + 0x10:#x}]
        pop ecx
        jmp {pc1:#x}
    c1d:
        push ecx
        {pic('p2')}
        inc dword ptr [ecx + {CNT + 0x14:#x}]
        pop ecx
        jmp {scg:#x}
    rnd:
        push ecx
        {pic('p3')}
        inc dword ptr [ecx + {CNT + 0x18:#x}]
        pop ecx
        call dword ptr [edi + 0xd0]
        jmp {RND_BACK:#x}
    .long ctd
    .long c0d
    .long c1d
    .long rnd
    """
    code = OV.asm(src, at)
    e = struct.unpack("<4I", code[-16:]); code = code[:-16]
    blob = MAGIC + code
    assert CAVE + len(blob) <= CAVE_END
    assert CT + 0x4D == 0x5561CAAB
    J = lambda s, t, n: b"\xe9" + struct.pack("<i", t - (s + 5)) + b"\x90" * (n - 5)  # noqa: E731
    return [(CAVE, bytes(len(blob)), blob),
            (CT, CT_ORIG, J(CT, e[0], 6)),
            (CASE0, J(CASE0, pc1, 5), J(CASE0, e[1], 5)),
            (CASE1, J(CASE1, scg, 5), J(CASE1, e[2], 5)),
            (RND, RND_ORIG, J(RND, e[3], 6))]


def read():
    import ctypes, ctypes.wintypes as wt, subprocess
    k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    out = subprocess.check_output(["tasklist", "/FI", "IMAGENAME eq AoWDevX.exe", "/FO", "CSV", "/NH"], text=True)
    line = out.splitlines()[0]
    if "INFO:" in line:
        print("AoWDevX.exe is not running."); return 1
    pid = int([p.strip('"') for p in line.split('","')][1])
    h = k32.OpenProcess(0x410, False, pid)
    if not h:
        print("OpenProcess failed (run elevated)"); return 1
    mods = (ctypes.c_void_p * 2048)(); need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 0x03)
    nb = ctypes.create_string_buffer(260); base = None
    for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
        if mods[i]:
            psapi.GetModuleBaseNameA(h, ctypes.c_void_p(mods[i]), nb, 260)
            if nb.value.lower() == b"hsepack.dpl":
                base = mods[i]; break
    if not base:
        print("HSEPack.dpl not loaded"); return 1
    b = ctypes.create_string_buffer(0x28); g = ctypes.c_size_t()
    k32.ReadProcessMemory(h, ctypes.c_void_p(CNT - HBASE + base), b, 0x28, ctypes.byref(g))
    v = struct.unpack("<10I", b.raw)
    txt = ("bypass entered %d | same 0xE %d | with gate %d | case0 %d | case1 %d | palette path %d\n"
           "last: RID %#x flag %d gate %d   (live FLAG/GATE now: see dump)\n" % (v[0], v[1], v[2], v[4], v[5], v[6], v[7], v[8], v[9]))
    b2 = ctypes.create_string_buffer(2)
    k32.ReadProcessMemory(h, ctypes.c_void_p(FLAG - HBASE + base), b2, 2, ctypes.byref(g))
    txt += "FLAG now %d GATE now %d\n" % (b2.raw[0], b2.raw[1])
    for nm, a in (("current terrain (al)", HA), ("new terrain ([esi])", HB)):
        b3 = ctypes.create_string_buffer(1024)
        k32.ReadProcessMemory(h, ctypes.c_void_p(a - HBASE + base), b3, 1024, ctypes.byref(g))
        hv = struct.unpack("<256I", b3.raw)
        txt += nm + ": " + ", ".join("%#x:%d" % (i, n) for i, n in enumerate(hv) if n) + "\n"
    print(txt)
    open(os.path.join(HERE, "sky_probe.txt"), "w").write(txt)
    return 0


def main():
    import pefile
    import patch_sky_polish_v1 as SP
    if "--read" in sys.argv:
        return read()
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    HSE = hse_file()
    d = open(HSE, "rb").read(); pe = pefile.PE(data=d)
    P = patches(d, pe)
    st, bad = SP.state(d, pe, HBASE, P)
    print("HSEPack %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(HSE, TAG)
    if not revert and not os.path.exists(bk):
        shutil.copy2(HSE, bk)
    SP.write_bytes(HSE, HBASE, P, revert)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
