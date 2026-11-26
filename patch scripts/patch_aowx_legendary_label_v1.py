#!/usr/bin/env python3
r"""
AoWx.exe: the unit window shows "Legendary" under "Exp (x/y)" for a Legendary-medal unit (2026-09-14).

Facts (410 build, verified):
  * TUnitWindow (VMT 0x40710C, instance 0x248, field table @0x407134 = 118 fields, class table idx 4 =
    TAOWLabel); global instance var 0x45B070.  RCDATA TUNITWINDOW 0x11AD4 B, res data entry @file
    0x73240 (RVA 0x1ED75C).  Labels Level (+0x1B8) and XP (+0x20C) live in RightFramePnl at WinTop 18
    and 30 (12 px pitch), font Age8, colour 0x171C1C, awCenter with 7 px side offsets.
  * The update routine 0x407DB8 sets the Exp text at 0x408A19/0x408A1F (`mov eax,[[esi]+0x20C]; call
    TAOWLabel.SetGText`) with esi = &UnitWindow and ebx = the unit (hero or unit) - one shared site.
  * Legendary in the dll (patch_legendary_abilities_v1.py): gold medal AND hit points at the cap; the
    medal painters gate on unit VMT+0x114 (GetUnitType != 0) and then call cave 0x5580EF60 (ebx=unit;
    CF clear = capped, which implies rank 2).  Reached from the exe rebase-safely as
    [IAT 0x45DCDC] (AoWE.THero.GetLevel, link 0x55787740) + delta.

Patch (new RWX section .xleg @VA 0x61C000):
  1. TUNITWINDOW DFM with TAOWLabel `Legend` cloned from XP (WinTop / TopOffset 42, no tooltip, no
     text) inserted after XP; resource entry repointed.  Field table +1 (Legend @+0x248, TAOWLabel),
     instance 0x248 -> 0x24C.
  2. The Exp SetGText call -> cave: original call, then Legend.SetGText("Legendary" or ""): not a THero
     (System.@IsClass against the imported THero class) and the dll's HP-cap test says capped.
Dry-run default; --apply; --revert.  Backup: AoWx.exe.bak_legendlabel
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_EXE = game_file(r"AoWx.exe")
BAK_SUFFIX = ".bak_legendlabel"; BASE = 0x400000
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
SEC_NAME, SEC_VA, SEC_VSIZE = b".xleg", 0x61C000, 0x13000
RES_ENTRY_FO, RES_RVA, RES_SIZE = 0x73240, 0x1ED75C, 0x11AD4
VMT, FT_VA, FT_LEN, FT_COUNT = 0x40710C, 0x407134, 0x6BB2 - 0x6534, 118
VMT_FT_FO, VMT_SIZE_FO = 0x64E0, 0x64F0                   # VMT-0x2C / VMT-0x1C (file = VA - 0x400C00)
OLD_INST, NEW_INST, CLS_LABEL, NEW_FIELD = 0x248, 0x24C, 4, 0x248
G_UNITWINDOW, IAT_GETLEVEL, LINK_GETLEVEL, DLL_LEGEND_CAVE = 0x45B070, 0x45DCDC, 0x55787740, 0x5580EF60
T_SETGTEXT, F_XP = 0x403254, 0x20C
HOOK, HOOK_ORIG = 0x408A1F, bytes.fromhex("e830a8ffff")   # call TAOWLabel.SetGText (Exp text)
IAT_THERO, T_ISCLASS = 0x45DFC4, 0x401070                # IAT AoWE..THero class VMT; System.@IsClass thunk (eax=obj, edx=class)
# (v1 gated on unit VMT+0x114 GetUnitType != 0 like the dll's combat medal painter; TUnit.GetUnitType is the
#  resource's type byte [res+0x30], where 0 is a valid type, so a legendary type-0 unit showed nothing.)
NEW_TOP = 42
LEGEND_CAVE_SIG = bytes.fromhex("5051528b53400fb64a2c")   # dll cave prologue: push eax/ecx/edx; mov edx,[ebx+0x40]; movzx ecx,[edx+0x2c]


def sstr(s): return bytes([len(s)]) + s


def skip_val(d, p):
    t = d[p]; p += 1
    if t in (0, 8, 9, 13): return p
    if t == 1:
        while d[p] != 0: p = skip_val(d, p)
        return p + 1
    if t == 2: return p + 1
    if t == 3: return p + 2
    if t == 4: return p + 4
    if t == 5: return p + 10
    if t in (6, 7): return p + 1 + d[p]
    if t == 10: return p + 4 + struct.unpack_from("<I", d, p)[0]
    if t == 11:
        while d[p] != 0: p += 1 + d[p]
        return p + 1
    if t == 12: return p + 4 + struct.unpack_from("<I", d, p)[0]
    raise ValueError("vtype %d @%#x" % (t, p))


def obj_span(d, o):
    p = o + 1 + d[o]; p += 1 + d[p]
    while d[p] != 0: p += 1 + d[p]; p = skip_val(d, p)
    p += 1
    while d[p] != 0: p = obj_span(d, p)
    return p + 1


def find_obj(d, name):
    key = sstr(name); i = 0
    while True:
        i = d.find(key, i); assert i >= 0, name
        for cl in range(3, 40):
            s = i - 1 - cl
            if s >= 0 and d[s] == cl and d[s + 1:s + 2] == b"T": return s, obj_span(d, s)
        i += 1


def rebuild_props(raw, new_name, drop, set_int8):
    """Clone a component node: new name, some properties dropped, some vaInt8 properties re-valued."""
    cl = raw[0]; p = 1 + cl; nl = raw[p]; p += 1 + nl
    out = bytearray(raw[:1 + cl]) + sstr(new_name)
    while raw[p] != 0:
        pn = raw[p + 1:p + 1 + raw[p]]; vs = p + 1 + raw[p]; ve = skip_val(raw, vs)
        if pn in drop:
            p = ve; continue
        if pn in set_int8:
            assert raw[vs] == 2, pn
            out += sstr(pn) + b"\x02" + struct.pack("<b", set_int8[pn])
        else:
            out += raw[p:ve]
        p = ve
    out += raw[p:]                       # end-of-props 0, children (none), end-of-object 0
    assert obj_span(bytes(out), 0) == len(out)
    return bytes(out)


def build_dfm(dfm):
    s, e = find_obj(dfm, b"XP"); raw = dfm[s:e]
    assert raw[1:1 + raw[0]] == b"TAOWLabel"
    node = rebuild_props(raw, b"Legend", {b"ToolTip", b"ToolTipText.Strings"},
                         {b"WinTop": NEW_TOP, b"Alignment.TopOffset": NEW_TOP})
    out = dfm[:e] + node + dfm[e:]
    assert obj_span(out, 4) == len(out), "extended DFM does not walk"
    return out


def build_field_table(ft):
    out = bytearray(ft); out += struct.pack("<IH", NEW_FIELD, CLS_LABEL) + sstr(b"Legend")
    struct.pack_into("<H", out, 0, struct.unpack_from("<H", ft, 0)[0] + 1); return bytes(out)


def build_code(va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    H = lambda v: "0x%X" % v  # noqa: E731  (keystone reads bare decimals as hex)
    lit = va                                     # AnsiString literal: refcount -1, length, chars
    text = b"Legendary"
    data = struct.pack("<ii", -1, len(text)) + text + b"\0"
    data += bytes((-len(data)) % 16)
    code_va = va + len(data)
    src = "\n".join([
        "call %s" % H(T_SETGTEXT),                       # the displaced call: Exp text
        "mov  eax, [%s]" % H(G_UNITWINDOW),
        "test eax, eax",
        "je   out",
        "mov  eax, [eax + %s]" % H(NEW_FIELD),           # Legend label
        "test eax, eax",
        "je   out",
        "push eax",
        "mov  eax, ebx",                                 # the unit
        "mov  edx, [%s]" % H(IAT_THERO),                 # heroes (and leaders) never carry medals
        "call %s" % H(T_ISCLASS),                        # (clobbers edx - the text is chosen AFTER the tests)
        "test al, al",
        "jne  empty",
        "mov  eax, [%s]" % H(IAT_GETLEVEL),              # AoWEPACK rebase delta
        "sub  eax, %s" % H(LINK_GETLEVEL),
        "add  eax, %s" % H(DLL_LEGEND_CAVE),
        "call eax",                                      # ebx = unit; CF clear = HP capped = Legendary
        "jb   empty",
        "mov  edx, %s" % H(lit + 8),
        "jmp  set",
        "empty:",
        "xor  edx, edx",                                 # '' (nil AnsiString; SetGText AddRef/Clr handle nil)
        "set:",
        "pop  eax",
        "call %s" % H(T_SETGTEXT),
        "out:",
        "ret",
    ])
    code = bytes(ks.asm(src, code_va)[0])
    return data + code, code_va


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    args = ap.parse_args(); exe, bak = args.exe, bak_path(args.exe, BAK_SUFFIX)
    if args.revert:
        if not os.path.exists(bak): print("no backup"); return 1
        shutil.copyfile(bak, exe); print(f"Restored {exe} from {bak}"); return 0
    import pefile
    d = bytearray(open(exe, "rb").read()); pe = pefile.PE(data=bytes(d))
    already = any(s.Name.rstrip(b"\0") == SEC_NAME for s in pe.sections)
    src = bytes(open(bak, "rb").read()) if already and os.path.exists(bak) else bytes(d); pe0 = pefile.PE(data=src)
    dfm = src[pe0.get_offset_from_rva(RES_RVA):pe0.get_offset_from_rva(RES_RVA) + RES_SIZE]; assert dfm[:4] == b"TPF0"
    ft = src[pe0.get_offset_from_rva(FT_VA - BASE):pe0.get_offset_from_rva(FT_VA - BASE) + FT_LEN]
    assert struct.unpack_from("<H", ft, 0)[0] == FT_COUNT and struct.unpack_from("<I", src, VMT_FT_FO)[0] in (FT_VA,) or already
    # the dll beside the exe must carry the legendary test cave this feature calls
    dll = os.path.join(os.path.dirname(exe), "AoWEPACK.dll")
    dd = open(dll, "rb").read()
    assert dd[DLL_LEGEND_CAVE - 0x55700C00:][:len(LEGEND_CAVE_SIG)] == LEGEND_CAVE_SIG, "AoWEPACK.dll has no legendary cave at %#x" % DLL_LEGEND_CAVE
    new_dfm, new_ft = build_dfm(dfm), build_field_table(ft)
    off_ft = (len(new_dfm) + 15) & ~15; off_code = (off_ft + len(new_ft) + 15) & ~15
    code, cave_va = build_code(SEC_VA + off_code)
    blob = bytearray(off_code + len(code)); blob[:len(new_dfm)] = new_dfm; blob[off_ft:off_ft + len(new_ft)] = new_ft; blob[off_code:] = code
    raw_size = (len(blob) + 0x1FF) & ~0x1FF; assert raw_size <= SEC_VSIZE
    print(f"target: {exe}\n{SEC_NAME.decode()} @{SEC_VA:#x}: dfm {len(new_dfm)} B (+{len(new_dfm) - RES_SIZE}), field table @+{off_ft:#x} ({len(new_ft)} B), cave @{cave_va:#x} ({len(code)} B)")
    sites = [
        (VMT_FT_FO, struct.pack("<I", FT_VA), struct.pack("<I", SEC_VA + off_ft), "TUnitWindow VMT field-table ptr"),
        (VMT_SIZE_FO, struct.pack("<I", OLD_INST), struct.pack("<I", NEW_INST), "TUnitWindow instance size 0x248 -> 0x24C"),
        (RES_ENTRY_FO, struct.pack("<II", RES_RVA, RES_SIZE), struct.pack("<II", SEC_VA - BASE, len(new_dfm)), "TUNITWINDOW resource -> extended DFM"),
        (pe.get_offset_from_rva(HOOK - BASE), HOOK_ORIG, b"\xE8" + struct.pack("<i", cave_va - (HOOK + 5)), "Exp SetGText call -> cave"),
    ]
    ok = True; applied = 0
    for off, old, new, desc in sites:
        cur = bytes(d[off:off + len(old)])
        if cur == new: applied += 1
        elif cur != old: print(f"MISMATCH @file {off:#x} ({desc}): exp {old.hex()} got {cur.hex()}"); ok = False
    if already and applied == len(sites):
        sec = next(s for s in pe.sections if s.Name.rstrip(b"\0") == SEC_NAME)
        if bytes(d[sec.PointerToRawData:sec.PointerToRawData + len(blob)]) == bytes(blob): print("ALL ALREADY PATCHED"); return 0
    if not ok or (applied and applied != len(sites)): print("Aborting."); return 1
    if not args.apply: print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak): shutil.copyfile(exe, bak); print(f"Backup: {bak}")
    e = struct.unpack_from("<I", d, 0x3C)[0]; nsec = struct.unpack_from("<H", d, e + 6)[0]; sec0 = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    if not already:
        assert sec0 + 40 * (nsec + 1) <= pe.sections[0].PointerToRawData
        assert pe.OPTIONAL_HEADER.SizeOfImage == SEC_VA - BASE, f"SizeOfImage {pe.OPTIONAL_HEADER.SizeOfImage:#x}"
        pad = (-len(d)) % 0x200; d += bytes(pad); rawoff = len(d); d += blob + bytes(raw_size - len(blob))
        hdr = SEC_NAME.ljust(8, b"\0") + struct.pack("<IIIIIIHHI", SEC_VSIZE, SEC_VA - BASE, raw_size, rawoff, 0, 0, 0, 0, 0xE0000060)
        struct.pack_into("<40s", d, sec0 + 40 * nsec, hdr); struct.pack_into("<H", d, e + 6, nsec + 1); struct.pack_into("<I", d, e + 24 + 56, SEC_VA - BASE + SEC_VSIZE)
        print(f"appended {SEC_NAME.decode()} raw @{rawoff:#x} ({raw_size:#x} B)")
    else:
        sec = next(s for s in pe.sections if s.Name.rstrip(b"\0") == SEC_NAME); assert raw_size <= sec.SizeOfRawData
        d[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData] = blob + bytes(sec.SizeOfRawData - len(blob)); print("refreshed section")
    for off, old, new, desc in sites: d[off:off + len(new)] = new; print("Patched:", desc)
    tmp = exe + ".tmp"; open(tmp, "wb").write(d); os.replace(tmp, exe)
    print("AoWx.exe patched.  UNTESTED: open the unit window on a Legendary unit (text under Exp), a gold/silver/plain unit and a hero (no text).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
