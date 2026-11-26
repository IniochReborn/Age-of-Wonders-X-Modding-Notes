r"""
Realm window Heroes tab: "Turn Met" + "Experience" columns (2026-10-22, for 1.37.422).  AoWx.exe only.
Needs patch_hero_turnmet_v1.py (AoWEPACK) for the Turn Met value (word THero+0x9A; without it the column shows "1").

Columns (panel T5LBFr, 354 px):  Hero Name 0..132 | Turn Met 131..177 | Health 176..238 | Experience 237..301 | Level
  Turn Met:   word [hero+0x9A]: 0xFFFF -> "-" (pre-422 save), 0 -> "1" (map hero), N -> "N"
  Experience: "cur/next" from the hero vcalls +0x15C GetExperience / +0x164 GetNextLevelExperience; "Max" at the level
              cap (vanilla returns next <= cur there)

1. DFM  RCDATA "TREALMWIN" is copied to .xtut 0x63A000 and its resource data entry (file 0x730C0) repointed:
   T5Name/T5SName narrowed (RightOffset 124 -> 222), T5Health/T5SHealth moved (RightOffset 53 -> 116, width 62);
   new T5Turn / T5Exp listboxes (clones of T5Health) and T5STurn ("Turn Met", OnClick T5STurnClick) / T5SExp
   ("Experience", OnClick T5SLevelClick = sort by level) header buttons (clones of T5SHealth).
2. CLASS  TRealmWin VMT 0x4484F0: InstanceSize 0x19C -> 0x1AC; new field table (+T5Turn +0x19C, T5Exp +0x1A0,
   T5STurn +0x1A4, T5SExp +0x1A8) and method table (+T5STurnClick) in .xtut (VMT-0x2C / VMT-0x28 repointed).
3. CODE (jmp hooks, all reloc-free):
   0x4498E4  fill: clear Items of the two new lists after the vanilla 3
   0x449A84  fill: per hero, after the Level Add -> add the Turn Met + Experience strings
   0x44B128  HeroListChange: SetIndex on the new lists too
   0x44B14B  HeroVSBChange VANILLA BUG: scrolled [self+0xC8] (= T3Name, the Places list) instead of T5Name -> +0x110
   0x44B179  HeroVSBChange: SetListOff on the new lists too
   0x44B2F5 / 0x44B355 / 0x44B3B5  Name / Health / Level sort: the new lists are permuted along
   T5STurnClick: sort [Turn, Name, Health, Level, Exp] numerically (mode 2, like Level)
.xtut: raw 0x4400 -> RAW_NEW / VS 0x5000 -> VS_NEW (code zone 0x639000..0x63A000 'RHC1', DFM from 0x63A000);
the previous VS tail 0x638400..0x639000 (intro-egg runtime data) becomes file-backed zeros = same initial state.
Revert = exact (sites, VMT, resource entry, sizes restored, file truncated).  LIFO: revert this before any later
script that grows .xtut.  Dry-run default; --apply / --revert / --dis.  Backup <game>\backup\AoWx.exe.bak_realmhero.
"""
import argparse, os, shutil, struct, sys

import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import dfmbin
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

EXE = game_file("AoWx.exe")
BASE, CODE2F = 0x400000, 0x400C00
SEC_VA, SEC_FILE = 0x634000, 0x22D000
RAW_OLD, VS_OLD = 0x4400, 0x5000
ZONE, ZONE_END = 0x639000, 0x63A000
DFM_VA = 0x63A000
MAGIC = b"RHC1"

VMT = 0x4484F0
FT_PTR, MT_PTR, IS_PTR = VMT - 0x2C, VMT - 0x28, VMT - 0x1C
FT_OLD, MT_OLD, IS_OLD, IS_NEW = 0x448518, 0x4489F5, 0x19C, 0x1AC
CLASSNAME_VA = 0x448E51                        # method table ends here
RES_ENTRY_FILE = 0x730C0                       # IMAGE_RESOURCE_DATA_ENTRY of TREALMWIN
RES_OLD = (0x163C74, 57682)

F_TURN, F_EXP, F_STURN, F_SEXP = 0x19C, 0x1A0, 0x1A4, 0x1A8
NEW_FIELDS = ((F_TURN, 6, "T5Turn"), (F_EXP, 6, "T5Exp"), (F_STURN, 5, "T5STurn"), (F_SEXP, 5, "T5SExp"))

INTTOSTR, LSTRCATN, TLIST_ADD, TOBJ_CREATE = 0x4013AC, 0x401128, 0x4014B4, 0x401058
SETINDEX, SETLISTOFF, SORT, SORTPREP = 0x40365C, 0x403664, 0x455744, 0x455DFC
SLASH = 0x449B28                               # vanilla const AnsiString '/'

SITES = {   # va: (original bytes, return address)
    0x4498E4: (bytes.fromhex("8b80180100008b80140100008b10ff5240"), 0x4498F5),
    0x449A84: (bytes.fromhex("8b80180100008b8014010000"), 0x449A95),
    0x44B128: (bytes.fromhex("8b96200100008b8318010000e82385fbff"), 0x44B139),
    0x44B179: (bytes.fromhex("8b8318010000e8e084fbff"), 0x44B184),
    0x44B2F5: (bytes.fromhex("8b93180100008b0424e8b161fbff"), 0x44B303),
    0x44B355: (bytes.fromhex("8b93180100008b0424e85161fbff"), 0x44B363),
    0x44B3B5: (bytes.fromhex("8b93140100008b0424e8f160fbff"), 0x44B3C3),
}
VSB_FIX = (0x44B14B, bytes.fromhex("8b83c8000000"), bytes.fromhex("8b8310010000"))

# geometry inside T5LBFr (354 px): x = 354 - RightOffset - width for awRight boxes
GEO = {"Name": (0, 132, 222), "Turn": (131, 46, 177), "Health": (176, 62, 116), "Exp": (237, 64, 53)}


def lit(s):
    """Delphi constant AnsiString (refcount -1): returns bytes; the string pointer is +8"""
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\x00" * (4 - len(b) % 4)


def build_code(ks, at, lits):
    blocks = []
    ret = {va: r for va, (_, r) in SITES.items()}

    def add_new(field, call_ofs, pre=""):
        return """
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+{f:#x}]
        test eax, eax
        je {lbl}
        mov eax, dword ptr [eax+0x114]
        mov edx, dword ptr [eax]
        call dword ptr [edx+{c:#x}]
    {lbl}:""".format(f=field, c=call_ofs, lbl="cl_%x" % field)

    blocks.append(("clear", """
        mov eax, dword ptr [eax+0x118]
        mov eax, dword ptr [eax+0x114]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x40]
        {a}
        {b}
        jmp {r:#x}
    """.format(a=add_new(F_TURN, 0x40), b=add_new(F_EXP, 0x40), r=ret[0x4498E4])))

    blocks.append(("fill", """
        mov eax, dword ptr [eax+0x118]
        mov eax, dword ptr [eax+0x114]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x34]
        movzx eax, word ptr [ebx+0x9a]
        cmp eax, 0xffff
        je f_dash
        test eax, eax
        jne f_num
        inc eax
    f_num:
        lea edx, [ebp-0x14]
        call {its:#x}
        mov edx, dword ptr [ebp-0x14]
        jmp f_addt
    f_dash:
        mov edx, {dash:#x}
    f_addt:
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+{ft:#x}]
        test eax, eax
        je f_exp
        mov eax, dword ptr [eax+0x114]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x34]
    f_exp:
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x164]
        mov edi, eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x15c]
        cmp edi, eax
        jg f_frac
        mov edx, {mx:#x}
        jmp f_adde
    f_frac:
        push edi
        lea edx, [ebp-0x18]
        call {its:#x}
        pop eax
        lea edx, [ebp-0x1c]
        call {its:#x}
        push dword ptr [ebp-0x18]
        push {slash:#x}
        push dword ptr [ebp-0x1c]
        lea eax, [ebp-0x14]
        mov edx, 3
        call {cat:#x}
        mov edx, dword ptr [ebp-0x14]
    f_adde:
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+{fe:#x}]
        test eax, eax
        je f_done
        mov eax, dword ptr [eax+0x114]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x34]
    f_done:
        jmp {r:#x}
    """.format(its=INTTOSTR, dash=lits["-"], mx=lits["Max"], ft=F_TURN, fe=F_EXP, slash=SLASH, cat=LSTRCATN,
               r=ret[0x449A84])))

    sel_new = "".join("""
        mov eax, dword ptr [ebx+{f:#x}]
        test eax, eax
        je s_{f:x}
        mov edx, dword ptr [esi+0x120]
        call {si:#x}
    s_{f:x}:""".format(f=f, si=SETINDEX) for f in (F_TURN, F_EXP))
    blocks.append(("sel", """
        mov edx, dword ptr [esi+0x120]
        mov eax, dword ptr [ebx+0x118]
        call {si:#x}
        {n}
        jmp {r:#x}
    """.format(si=SETINDEX, n=sel_new, r=ret[0x44B128])))

    vsb_new = "".join("""
        mov eax, dword ptr [ebx+{f:#x}]
        test eax, eax
        je v_{f:x}
        mov edx, dword ptr [ebx+0x134]
        mov edx, dword ptr [edx+0x148]
        call {so:#x}
    v_{f:x}:""".format(f=f, so=SETLISTOFF) for f in (F_TURN, F_EXP))
    blocks.append(("vsb", """
        mov eax, dword ptr [ebx+0x118]
        call {so:#x}
        {n}
        jmp {r:#x}
    """.format(so=SETLISTOFF, n=vsb_new, r=ret[0x44B179])))

    for site, fld in ((0x44B2F5, 0x118), (0x44B355, 0x118), (0x44B3B5, 0x114)):
        add = "".join("""
        mov edx, dword ptr [ebx+{f:#x}]
        test edx, edx
        je t_{f:x}
        mov eax, dword ptr [esp]
        call {ad:#x}
    t_{f:x}:""".format(f=f, ad=TLIST_ADD) for f in (F_TURN, F_EXP))
        blocks.append(("sort_%x" % site, """
        mov edx, dword ptr [ebx+{x:#x}]
        mov eax, dword ptr [esp]
        call {ad:#x}
        {n}
        jmp {r:#x}
        """.format(x=fld, ad=TLIST_ADD, n=add, r=ret[site])))

    adds = "".join("""
        mov edx, dword ptr [ebx+{f:#x}]
        mov eax, dword ptr [esp]
        call {ad:#x}""".format(f=f, ad=TLIST_ADD) for f in (F_TURN, 0x110, 0x114, 0x118, F_EXP))
    blocks.append(("turnclick", """
        push ebx
        push ecx
        mov ebx, eax
        mov eax, dword ptr [0x45a420]
        mov eax, dword ptr [eax]
        xor edx, edx
        call {prep:#x}
        mov dl, 1
        mov eax, dword ptr [0x45d4e8]
        call {cr:#x}
        mov dword ptr [esp], eax
        {adds}
        mov edx, esp
        mov eax, dword ptr [0x45a420]
        mov eax, dword ptr [eax]
        mov cl, 2
        call {sort:#x}
        pop edx
        pop ebx
        ret
    """.format(prep=SORTPREP, cr=TOBJ_CREATE, adds=adds, sort=SORT)))

    code = b""; ent = {}
    for name, src in blocks:
        a = at + len(code)
        ent[name] = a
        enc, _ = ks.asm(src, a)
        code += bytes(enc)
        code += b"\xcc" * (-len(code) % 4)
    return code, ent


def build_tables(d, at, turnclick):
    """new field + method tables (copies of the originals + our entries)"""
    va = lambda v: d[v - CODE2F:]
    nfields = struct.unpack_from("<H", d, FT_OLD - CODE2F)[0]
    classtab = struct.unpack_from("<I", d, FT_OLD + 2 - CODE2F)[0]
    fbody = bytes(d[FT_OLD + 6 - CODE2F:MT_OLD - CODE2F])
    ft = struct.pack("<HI", nfields + len(NEW_FIELDS), classtab) + fbody
    for off, idx, nm in NEW_FIELDS:
        ft += struct.pack("<IH", off, idx) + bytes([len(nm)]) + nm.encode()
    ft += b"\x00" * (-len(ft) % 4)
    nmeth = struct.unpack_from("<H", d, MT_OLD - CODE2F)[0]
    mbody = bytes(d[MT_OLD + 2 - CODE2F:CLASSNAME_VA - CODE2F])
    nm = b"T5STurnClick"
    mt = struct.pack("<H", nmeth + 1) + mbody + struct.pack("<HI", 2 + 4 + 1 + len(nm), turnclick) + bytes([len(nm)]) + nm
    mt += b"\x00" * (-len(mt) % 4)
    return ft, mt, at, at + len(ft)


def build_dfm(orig):
    root = dfmbin.parse(orig)
    kids = root.children
    names = [c.name for c in kids]

    def geo(c, key):
        x, w, ro = GEO[key]
        c.set("WinLeft", dfmbin.v_int(x)); c.set("WinWidth", dfmbin.v_int(w))
        c.set("Alignment.RightOffset", dfmbin.v_int(ro))

    for n, key in (("T5Name", "Name"), ("T5SName", "Name"), ("T5Health", "Health"), ("T5SHealth", "Health")):
        geo(root.find(n), key)
    health, shealth = root.find("T5Health"), root.find("T5SHealth")
    turn, exp = health.clone(), health.clone()
    turn.name, exp.name = "T5Turn", "T5Exp"
    geo(turn, "Turn"); geo(exp, "Exp")
    sturn, sexp = shealth.clone(), shealth.clone()
    sturn.name, sexp.name = "T5STurn", "T5SExp"
    geo(sturn, "Turn"); geo(sexp, "Exp")
    sturn.set("Text", dfmbin.v_str("Turn Met")); sexp.set("Text", dfmbin.v_str("Experience"))
    sturn.set("ToolTipText.Strings", dfmbin.v_strlist(["Sort Heroes by Turn Met."]))
    sexp.set("ToolTipText.Strings", dfmbin.v_strlist(["Sort Heroes by Level."]))
    sturn.set("OnClick", dfmbin.v_ident("T5STurnClick")); sexp.set("OnClick", dfmbin.v_ident("T5SLevelClick"))
    i = names.index("T5Level") + 1
    kids[i:i] = [turn, exp]
    names = [c.name for c in kids]
    i = names.index("T5SLevel") + 1
    kids[i:i] = [sturn, sexp]
    out = dfmbin.serialize(root)
    chk = dfmbin.parse(out)
    assert [c.name for c in chk.children].count("T5Turn") == 1
    return out


def sec_hdr(pe):
    s = pe.sections[-1]
    assert s.Name.rstrip(b"\0") == b".xtut" and s.VirtualAddress == SEC_VA - BASE, ".xtut must be the last section"
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--exe", default=EXE)
    a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    pe = pefile.PE(data=bytes(d), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    s = sec_hdr(pe)
    shoff = s.get_file_offset()
    soi_off = pe.OPTIONAL_HEADER.get_file_offset() + 56
    raw, vs = s.SizeOfRawData, s.Misc_VirtualSize
    soi = pe.OPTIONAL_HEADER.SizeOfImage
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    # ---- build
    lits_blob = b""; lits = {}
    lit_at = ZONE + 0x10
    for t in ("-", "Max"):
        lits[t] = lit_at + len(lits_blob) + 8
        lits_blob += lit(t)
    code_at = lit_at + len(lits_blob)
    code, ent = build_code(ks, code_at, lits)
    tab_at = code_at + len(code)
    ft, mt, ft_va, mt_va = build_tables(d, tab_at, ent["turnclick"])
    zone = MAGIC + bytes(12) + lits_blob + code + ft + mt
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    rsrc = [x for x in pe.sections if x.Name.rstrip(b"\0") == b".rsrc"][0]
    dfm_file = rsrc.PointerToRawData + RES_OLD[0] - rsrc.VirtualAddress
    orig_dfm = bytes(d[dfm_file:dfm_file + RES_OLD[1]])
    dfm = build_dfm(orig_dfm)
    vs_new = (DFM_VA + len(dfm) - SEC_VA + 0xFFF) & ~0xFFF
    raw_new = vs_new
    soi_new = SEC_VA - BASE + vs_new
    hooks = {va: (b"\xe9" + struct.pack("<i", ent[n] - (va + 5))).ljust(len(SITES[va][0]), b"\x90")
             for va, n in ((0x4498E4, "clear"), (0x449A84, "fill"), (0x44B128, "sel"), (0x44B179, "vsb"),
                           (0x44B2F5, "sort_44b2f5"), (0x44B355, "sort_44b355"), (0x44B3B5, "sort_44b3b5"))}

    # ---- state
    rd = lambda va, n: bytes(d[va - CODE2F:va - CODE2F + n])
    st = {}
    for va, (old, _) in SITES.items():
        cur = rd(va, len(old)); st[va] = "v1" if cur == hooks[va] else "vanilla" if cur == old else "OTHER " + cur.hex()
    cur = rd(VSB_FIX[0], 6); st[VSB_FIX[0]] = "v1" if cur == VSB_FIX[2] else "vanilla" if cur == VSB_FIX[1] else "OTHER"
    ftp, mtp, isz = (struct.unpack_from("<I", d, p - CODE2F)[0] for p in (FT_PTR, MT_PTR, IS_PTR))
    res = struct.unpack_from("<II", d, RES_ENTRY_FILE)
    vmt_st = "v1" if (ftp, mtp, isz) == (ft_va, mt_va, IS_NEW) else "vanilla" if (ftp, mtp, isz) == (FT_OLD, MT_OLD, IS_OLD) else "OTHER"
    res_st = "v1" if res == (DFM_VA - BASE, len(dfm)) else "vanilla" if res == RES_OLD else "OTHER %r" % (res,)
    size_st = "v1" if (raw, vs, soi, len(d)) == (raw_new, vs_new, soi_new, SEC_FILE + raw_new) else \
        "vanilla" if (raw, vs, soi, len(d)) == (RAW_OLD, VS_OLD, SEC_VA - BASE + VS_OLD, SEC_FILE + RAW_OLD) else "OTHER"
    zone_st = "-"
    if size_st == "v1":
        zl = bytes(d[SEC_FILE + ZONE - SEC_VA:SEC_FILE + ZONE_END - SEC_VA])
        dl = bytes(d[SEC_FILE + DFM_VA - SEC_VA:SEC_FILE + DFM_VA - SEC_VA + len(dfm)])
        zone_st = "v1" if zl[:len(zone)] == zone and dl == dfm else "OTHER"
    relocs = set()
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type: relocs.add(BASE + e.rva)
    bad = [hex(r) for r in relocs if any(va - 3 <= r < va + len(SITES[va][0]) for va in SITES)
           or VSB_FIX[0] - 3 <= r < VSB_FIX[0] + 6 or IS_PTR - 3 <= r < IS_PTR + 4]
    print("sites: " + ", ".join("%#x %s" % (k, st[k]) for k in sorted(st)))
    print("VMT tables/size %s | resource entry %s | .xtut raw %#x VS %#x SOI %#x file %#x -> %s | zone+DFM %s"
          % (vmt_st, res_st, raw, vs, soi, len(d), size_st, zone_st))
    print("zone %#x: %d B (code %d, field table %#x, method table %#x) | DFM %d -> %d B @%#x | new raw/VS %#x SOI %#x"
          % (ZONE, len(zone), len(code), ft_va, mt_va, len(orig_dfm), len(dfm), DFM_VA, raw_new, soi_new))
    print("entries: " + ", ".join("%s %#x" % kv for kv in ent.items()))
    print("relocs at hook sites: %s (the VMT table pointers 0x4484C4/C8 are relocated dwords; their new values are"
          " in-image addresses too, and AoWx.exe has no DYNAMIC_BASE)" % (bad or "none"))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, code_at):
            print("  %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad:
        print("ABORT: relocation entries under patched bytes"); return 1
    states = set(st.values()) | {vmt_st, res_st, size_st}
    if a.revert:
        if states == {"vanilla"}:
            print("already reverted"); return 0
        if states != {"v1"} or zone_st != "v1":
            print("ABORT: not in the v1 state (or .xtut grown by a later script) - refusing a partial revert"); return 1
        for va, (old, _) in SITES.items(): d[va - CODE2F:va - CODE2F + len(old)] = old
        d[VSB_FIX[0] - CODE2F:VSB_FIX[0] - CODE2F + 6] = VSB_FIX[1]
        struct.pack_into("<I", d, FT_PTR - CODE2F, FT_OLD); struct.pack_into("<I", d, MT_PTR - CODE2F, MT_OLD)
        struct.pack_into("<I", d, IS_PTR - CODE2F, IS_OLD)
        struct.pack_into("<II", d, RES_ENTRY_FILE, *RES_OLD)
        struct.pack_into("<I", d, shoff + 8, VS_OLD); struct.pack_into("<I", d, shoff + 16, RAW_OLD)
        struct.pack_into("<I", d, soi_off, SEC_VA - BASE + VS_OLD)
        del d[SEC_FILE + RAW_OLD:]
    else:
        if states == {"v1"} and zone_st == "v1":
            print("already applied"); return 0
        if states != {"vanilla"}:
            print("ABORT: unexpected state (needs vanilla sites, VMT, resource entry and .xtut raw %#x / VS %#x, no overlay)"
                  % (RAW_OLD, VS_OLD)); return 1
        d += bytes(SEC_FILE + raw_new - len(d))
        zf = SEC_FILE + ZONE - SEC_VA
        d[zf:zf + len(zone)] = zone
        df = SEC_FILE + DFM_VA - SEC_VA
        d[df:df + len(dfm)] = dfm
        for va, h in hooks.items(): d[va - CODE2F:va - CODE2F + len(h)] = h
        d[VSB_FIX[0] - CODE2F:VSB_FIX[0] - CODE2F + 6] = VSB_FIX[2]
        struct.pack_into("<I", d, FT_PTR - CODE2F, ft_va); struct.pack_into("<I", d, MT_PTR - CODE2F, mt_va)
        struct.pack_into("<I", d, IS_PTR - CODE2F, IS_NEW)
        struct.pack_into("<II", d, RES_ENTRY_FILE, DFM_VA - BASE, len(dfm))
        struct.pack_into("<I", d, shoff + 8, vs_new); struct.pack_into("<I", d, shoff + 16, raw_new)
        struct.pack_into("<I", d, soi_off, soi_new)
        chk = pefile.PE(data=bytes(d), fast_load=True)
        assert chk.sections[-1].SizeOfRawData == raw_new and chk.OPTIONAL_HEADER.SizeOfImage == soi_new
        assert dfmbin.parse(bytes(chk.get_data(DFM_VA - BASE, len(dfm)))).find("T5STurn")
    if not (a.apply or a.revert):
        print("Dry run OK - rerun with --apply."); return 0
    bak = bak_path(a.exe, ".bak_realmhero")
    if a.apply and not os.path.exists(bak):
        shutil.copy2(a.exe, bak); print("backup ->", bak)
    with open(a.exe, "r+b") as f:
        f.seek(0); f.write(d); f.truncate()
    print("reverted" if a.revert else "applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
