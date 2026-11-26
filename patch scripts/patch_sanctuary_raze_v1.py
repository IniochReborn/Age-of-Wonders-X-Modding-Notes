#!/usr/bin/env python3
r"""
Razeable Magic Sanctuary (2026-10-31).

User: "make Sanctuary structure razeable. GFX should be easy, just remove the bubble and make a variant of the
'stone floor' that has cracks or rubble. rebuilding GFX, just add the builder animation like we've done in the past".

MagicSanctuary unit (AoWEPACK): TMagicSanctuary (VMT 0x557D41F4, ClassID 0x2089A, TStructure child, InstanceSize
0x34, +0x30 = the bubble TMagicSanctuaryOverlayHS) / TMagicSanctuaryResource (ClassID 0x2089B, ctor wrote
razeable [res+0x58] = 0).  The bubble = overlay Show (image sequence 0x13 = AMSHELL.ILB); the protection = the
MapFieldMsgProc answer to msg 0x1129 ([msg+8] = 1).  Raze framework = the TStructure one (see reflecting-pool-raze).

AoWEPACK.dll (zone 0x558E0000 'SNC1', rel32 only):
  * resource ctor 0x557D47A7 (12 B: [+44]=0 [+58]=0 [+45]=0) -> cave: [+44]=0 [+45]=0 [+58]=1 razeable,
    [+5B]=1 rebuild day (cost = framework 50 g);
  * InstanceSize 0x34 -> 0x38, razed bit = byte +0x34;  VMT +0x150 GetRazed / +0x14C SetRazed (Teleport-style:
    flip bit, recompute [self+14h] = [vmt+12Ch]([self+18h])) / +0x18 ReadWrite (TStructure.ReadWrite + byte +0x34
    as field id 0x70 - absent in old saves -> 0) / +0x12C GetTerrainTypeImage (building -> slot 13+i, razed ->
    slot 6+i, i = terrain 1..5 -> 0..4, 12 (underground) -> 5, else 0; otherwise TStructure's);
  * overlay Show 0x557D4580: owner razed -> no bubble (ret 4);
  * MapFieldMsgProc 0x557D476D: msg 0x1129 protection only while not razed.
Release.hss: both Sanctuary records (surface page 21 cell 55, underground page 23 cell 67; fields 9/10 share one
  TImageSequenceList) get slots 0x14/0x15 (raze explosion + smoke, copied from the Teleport), 6..11 (razed floor,
  STR_SANT ids 20..24) and 13..18 (razed floor + the STR_BLDG builder animation chain copied from the Teleport's
  rebuild slot 0x19).
Images\STR_SANT.ILB: ids 20..24 = cracked / rubbled versions of the floors 0..4 (sanctuary_raze_art.py).
Backups .bak_sanctraze.  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_dir, game_file  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import sanctuary_raze_art as ART  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402   (hss_rebuild, state, write_bytes, busy, asm via OV)
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_sanctraze"
DLL, BASE = game_file("AoWEPACK.dll"), 0x55700000
HSS = H.OURS
ILBP = game_file(os.path.join("Images", "STR_SANT.ILB"))

ZONE, ZONE_END, MAGIC = 0x558E0000, 0x558E0200, b"SNC1"
VMT = 0x557D41F4
INST = VMT - 0x1C
RC, RC_ORIG, RC_BACK = 0x557D47A7, bytes.fromhex("c6464400c6465800c6464500"), 0x557D47B3
SHOW, SHOW_ORIG = 0x557D4580, bytes.fromhex("558bec83c4f0")
MSG, MSG_ORIG, MSG_BACK = 0x557D476D, bytes.fromhex("c7460801000000"), 0x557D4774
SLOTS = {0x18: 0x5575E658, 0x12C: 0x5575E6A0, 0x14C: 0x5575EDE8, 0x150: 0x5575EDE4}
ST_RW, ST_GTI = 0x5575E658, 0x5575E6A0
RAZED_BIT_OFF, RW_TAG = 0x34, 0x70
REBUILD_DAYS = 1
RAZED_SLOT, BUILD_SLOT = 6, 13
SANCT_CLS, TELE_CLS = 0x2089B, 0x20105


def src():
    return f"""
    rc:
        mov byte ptr [esi + 0x44], 0
        mov byte ptr [esi + 0x45], 0
        mov byte ptr [esi + 0x58], 1
        mov byte ptr [esi + 0x5b], {REBUILD_DAYS}
        jmp {RC_BACK:#x}
    gr:
        test byte ptr [eax + {RAZED_BIT_OFF:#x}], 1
        setne al
        ret
    sr:
        push ebx
        mov ebx, eax
        test dl, dl
        je sr0
        or byte ptr [ebx + {RAZED_BIT_OFF:#x}], 1
        jmp sr1
    sr0:
        and byte ptr [ebx + {RAZED_BIT_OFF:#x}], 0xfe
    sr1:
        movsx edx, byte ptr [ebx + 0x18]
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x12c]
        mov dword ptr [ebx + 0x14], eax
        pop ebx
        ret
    rw:
        push ebx
        push esi
        push edi
        mov esi, edx
        mov ebx, eax
        call {ST_RW:#x}
        lea edx, [ebx + {RAZED_BIT_OFF:#x}]
        mov ecx, {RW_TAG:#x}
        mov eax, esi
        mov edi, dword ptr [eax]
        call dword ptr [edi + 0x30]
        pop edi
        pop esi
        pop ebx
        ret
    gti:
        mov ecx, edx
        dec ecx
        cmp ecx, 5
        jb gidx
        xor ecx, ecx
        cmp edx, 12
        jne gidx
        mov ecx, 5
    gidx:
        cmp byte ptr [eax + 0x24], 0xff
        je gnb
        lea eax, [ecx + {BUILD_SLOT}]
        ret
    gnb:
        test byte ptr [eax + {RAZED_BIT_OFF:#x}], 1
        je gorig
        lea eax, [ecx + {RAZED_SLOT}]
        ret
    gorig:
        jmp {ST_GTI:#x}
    show:
        push eax
        mov eax, dword ptr [eax + 0xc]
        test eax, eax
        je shgo
        test byte ptr [eax + {RAZED_BIT_OFF:#x}], 1
        je shgo
        pop eax
        ret 4
    shgo:
        pop eax
        push ebp
        mov ebp, esp
        add esp, -0x10
        jmp {SHOW + 6:#x}
    msg:
        test byte ptr [ebx + {RAZED_BIT_OFF:#x}], 1
        jne msk
        mov dword ptr [esi + 8], 1
    msk:
        jmp {MSG_BACK:#x}
    .long rc
    .long gr
    .long sr
    .long rw
    .long gti
    .long show
    .long msg
"""


def dll_patches():
    code = OV.asm(src(), ZONE + 0x10)
    names = ("rc", "gr", "sr", "rw", "gti", "show", "msg")
    e = dict(zip(names, struct.unpack("<%dI" % len(names), code[-4 * len(names):])))
    code = code[:-4 * len(names)]
    assert 0x10 + len(code) <= ZONE_END - ZONE
    z = MAGIC + bytes(12) + code
    jmp = lambda at, to, n: b"\xe9" + struct.pack("<i", to - (at + 5)) + b"\x90" * (n - 5)  # noqa: E731
    P = [(RC, RC_ORIG, jmp(RC, e["rc"], 12)), (SHOW, SHOW_ORIG, jmp(SHOW, e["show"], 6)),
         (MSG, MSG_ORIG, jmp(MSG, e["msg"], 7)),
         (INST, struct.pack("<I", 0x34), struct.pack("<I", 0x38)),
         (ZONE, bytes(len(z)), z)]
    new = {0x18: e["rw"], 0x12C: e["gti"], 0x14C: e["sr"], 0x150: e["gr"]}
    for slot, old in SLOTS.items():
        P.append((VMT + slot, struct.pack("<I", old), struct.pack("<I", new[slot])))
    return P


# ---- Release.hss ----------------------------------------------------------------------------------------------------
def tele_list(A):
    for c, r in sorted(A["recs"].items()):
        if struct.unpack_from("<I", r, 0)[0] == TELE_CLS:
            fo, td = H.fields(r)
            return Q.parse_list(r, td + fo[9])[0]
    raise KeyError("teleport record")


def new_list(lst, tele):
    lst = copy.deepcopy(lst)
    base = next(s for s in lst if s is not None and s["name"].upper() == "STR_SANT.ILB")
    lst[0x14] = copy.deepcopy(tele[0x14])
    lst[0x15] = copy.deepcopy(tele[0x15])
    builders = copy.deepcopy(tele[0x19]["sub"])
    assert builders["name"].upper() == "STR_BLDG.ILB"
    for i in range(6):
        frame = 20 + min(i, 4)
        razed = dict(name=base["name"], a=base["a"], b=base["b"], mode=4, frame=0, x=base["x"], y=base["y"], z=0,
                     frames=[frame], sub=None)
        lst[RAZED_SLOT + i] = razed
        rb = copy.deepcopy(razed)
        rb["sub"] = copy.deepcopy(builders)
        lst[BUILD_SLOT + i] = rb
    return lst


def rec_with_list(r, lst):
    """replace the (shared) field 9/10 image list of a record; fields after it shift"""
    te, td = H.table(r, 4)
    fo = {x[0]: x[1] for x in te}
    s = fo[9]
    assert fo[10] == s
    old, end = Q.parse_list(r, td + s)
    end -= td
    nxt = min(o for o in fo.values() if o > s)
    assert end == nxt, (end, nxt)
    blob = Q.enc_list(lst)
    assert Q.parse_list(blob, 0)[0] == lst
    delta = len(blob) - (end - s)
    for x in te:
        if x[1] > s:
            x[1] += delta
    data = bytes(r[td:td + s]) + blob + bytes(r[td + end:])
    return bytes(r[:4]) + H.enc_table(te) + data


def hss_build(b):
    A = H.parse(b)
    tele = tele_list(A)
    changed = {}
    for c, r in A["recs"].items():
        if struct.unpack_from("<I", r, 0)[0] != SANCT_CLS:
            continue
        fo, td = H.fields(r)
        lst = Q.parse_list(r, td + fo[9])[0]
        if lst[RAZED_SLOT] is not None:
            continue
        assert all(lst[i] is None for i in list(range(6, 12)) + list(range(13, 19)) + [0x14, 0x15]), c
        changed[c] = rec_with_list(r, new_list(lst, tele))
    if not changed:
        return None
    assert len(changed) == 2, sorted(changed)
    for c, v in changed.items():
        A["recs"][c] = bytearray(v)
    nb = SP.hss_rebuild(b, A)
    N = H.parse(nb)
    old = H.parse(b)["recs"]
    for c, v in N["recs"].items():
        assert bytes(v) == (changed[c] if c in changed else bytes(old[c]))
    return nb


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    files = [DLL, HSS, ILBP]
    if revert:
        if SP.busy():
            print("game/editor running - close it first"); return 1
        for f in files:
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    todo = []
    d = open(DLL, "rb").read(); pe = pefile.PE(data=d)
    P = dll_patches()
    st, bad = SP.state(d, pe, BASE, P)
    vmt_sites = {hex(VMT + s) for s in SLOTS}
    bad = [x for x in bad if x not in vmt_sites]
    print("AoWEPACK %s relocs %s" % (st, bad or "none (VMT slots are relocated pointers, expected)"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if st[0] == "vanilla":
        todo.append(("bytes", P))
    b = open(HSS, "rb").read()
    nb = hss_build(b)
    print("Release.hss", "already applied" if nb is None else "%d -> %d B (2 Sanctuary records)" % (len(b), len(nb)))
    if nb is not None:
        todo.append(("file", (HSS, nb)))
    ni = ART.build(game_dir())
    same = open(ILBP, "rb").read() == ni
    print("STR_SANT.ILB", "already applied" if same else "ids 20..24 (%d B)" % len(ni))
    if not same:
        todo.append(("file", (ILBP, ni)))
    if not todo:
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("game/editor running - close it first"); return 1
    for kind, x in todo:
        path = DLL if kind == "bytes" else x[0]
        bk = bak_path(path, TAG)
        if not os.path.exists(bk):
            shutil.copy2(path, bk)
        if kind == "bytes":
            SP.write_bytes(DLL, BASE, x, False)
        else:
            with open(path, "r+b") as fh:
                fh.write(x[1]); fh.truncate()
            assert open(path, "rb").read() == x[1]
        print("written", path)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
