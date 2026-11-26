#!/usr/bin/env python3
r"""
AoWDevX: Abilities tab re-layout so the skill-point cost is always visible (2026-10-31).

User: "when i have AoWDevX open, the skillpoint cost of abilities isnt visible unless i change my desktop
resolution ... (when i edit abilities)".  TMAINFORM > Settings > PageControl3 > AbilitySheet > Panel3 stacks one
209-px column of group boxes down to y = 565, with 'Skill Points:' (AbilityLevelPointBox) LAST at y 512..565 -
below the visible part of the side panel on shorter screens.
New column (Top / Height): Skill Points 4/53 (moved to the top) | Ability Info 60/130 (memo 88/96) |
Ability Description 194/112 (memo 70, Edit button 82) | SFX + GFX 310/60 (buttons 22) | Selection 374/118
(check list 90) -> ends at y 492 instead of 565, nothing hidden behind anything.
Only integer Top/Height values change; the DFM is rewritten in place at the end of .xprn (grows/shrinks with the
encodings; .xprn raw/virtual size + resource entry size updated like patch_devx_terrain_palette_v1).
⚠ re-run after patch_devx_terrain_palette_v1 / patch_sky_polish (they rebuild TMAINFORM from their own inputs).
Backup .bak_ablayout.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_devx_terrain_palette_v1 as PAL  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402

EXE = game_file("AoWDevX.exe")
SHEET = "AbilitySheet"
LAYOUT = {   # component: {prop: (old, new)}
    "AbilityLevelPointBox": {"Top": (512, 4)},
    "AbilityInfoGroup": {"Top": (4, 60), "Height": (153, 130)},
    "AbilityInfoMemo": {"Top": (32, 88), "Height": (109, 96)},
    "GroupBox1": {"Top": (164, 194), "Height": (137, 112)},
    "AbilityDescription": {"Height": (73, 70)},
    "EditAbilityText": {"Top": (104, 82)},
    "SFXBox": {"Top": (304, 310), "Height": (65, 60)},
    "EditAbilitySFXBtn": {"Top": (24, 22)},
    "AbGFXBox": {"Top": (304, 310), "Height": (65, 60)},
    "AbGFXEdit": {"Top": (24, 22)},
    "AbilitySelectionGroup": {"Top": (372, 374), "Height": (137, 118)},
    "AbilitySelectionCLB": {"Height": (105, 90)},
}
PARENTS = {"AbilityLevelPointBox": "Panel3", "AbilityInfoGroup": "Panel3", "AbilityInfoMemo": "Panel3",
           "GroupBox1": "Panel3", "SFXBox": "Panel3", "AbGFXBox": "Panel3", "AbilitySelectionGroup": "Panel3"}


def enc_int(v):
    return b"\x02" + struct.pack("<b", v) if -128 <= v <= 127 else b"\x03" + struct.pack("<h", v)


def prop_spans(raw, c):
    D = PAL.DFM(raw)
    D.p = c["start"]
    if raw[D.p] & 0xF0 == 0xF0:
        D.p += 1
    D.rs(); D.rs()
    out = {}
    while raw[D.p]:
        k = D.rs().decode(); st = D.p; D.val()
        out[k] = (st, D.p)
    return out


def int_at(raw, s):
    t = raw[s]
    return struct.unpack_from("<b" if t == 2 else "<h", raw, s + 1)[0] if t in (2, 3) else None


def new_dfm(dfm):
    D = PAL.DFM(dfm)
    sheet = [c for c in D.comps if c["name"] == SHEET]
    assert len(sheet) == 1
    under = set()

    def walk(c):
        under.add(c["name"])
        for k in c["kids"]:
            walk(k)
    walk(sheet[0])
    edits = []
    state = set()
    for name, props in LAYOUT.items():
        assert name in under, name
        c = [x for x in D.comps if x["name"] == name and x["name"] in under]
        c = [x for x in c if x["parent"] == PARENTS.get(name, x["parent"])]
        assert len(c) == 1, name
        sp = prop_spans(dfm, c[0])
        for k, (old, new) in props.items():
            s, e = sp[k]
            v = int_at(dfm, s)
            state.add("vanilla" if v == old else "ours" if v == new else "OTHER %s.%s=%s" % (name, k, v))
            edits.append((s, e, enc_int(new)))
    if state == {"ours"}:
        return None, "ours"
    assert state == {"vanilla"}, state
    out = bytearray(); pos = 0
    for s, e, b in sorted(edits):
        out += dfm[pos:s] + b; pos = e
    out += dfm[pos:]
    N = PAL.DFM(bytes(out))
    for name, props in LAYOUT.items():
        c = [x for x in N.comps if x["name"] == name and x["parent"] == PARENTS.get(name, x["parent"])]
        sp = prop_spans(bytes(out), c[0])
        for k, (old, new) in props.items():
            assert int_at(bytes(out), sp[k][0]) == new
    return bytes(out), "vanilla"


def build(d):
    import pefile
    pe = pefile.PE(data=d)
    rva, dfm = PAL.mainform_dfm(pe)
    nd, st = new_dfm(dfm)
    if nd is None:
        return None, "already applied"
    secs = pe.sections
    last = max(secs, key=lambda s: s.PointerToRawData)
    assert last.Name.rstrip(b"\0") == b".xprn" and last.PointerToRawData + last.SizeOfRawData == len(d)
    dfm_fo = pe.get_offset_from_rva(rva)
    assert not any(d[dfm_fo + len(dfm):]), "data after the DFM in .xprn"
    end = dfm_fo + len(nd)
    new_raw = max(((end - last.PointerToRawData) + PAL.ALIGN - 1) // PAL.ALIGN * PAL.ALIGN, last.SizeOfRawData)
    out = bytearray(d[:dfm_fo]) + nd
    out += bytes(last.PointerToRawData + new_raw - len(out))
    sh = last.get_file_offset()
    struct.pack_into("<I", out, sh + 8, max(new_raw, last.Misc_VirtualSize))
    struct.pack_into("<I", out, sh + 16, new_raw)
    sa = pe.OPTIONAL_HEADER.SectionAlignment
    soi = max(pe.OPTIONAL_HEADER.SizeOfImage, (last.VirtualAddress + max(new_raw, last.Misc_VirtualSize) + sa - 1) // sa * sa)
    struct.pack_into("<I", out, pe.OPTIONAL_HEADER.get_file_offset() + 56, soi)
    assert struct.unpack_from("<I", out, PAL.RES_ENTRY_FO)[0] == rva
    struct.pack_into("<I", out, PAL.RES_ENTRY_FO + 4, len(nd))
    return bytes(out), "DFM %d -> %d B" % (len(dfm), len(nd))


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    bk = bak_path(EXE, ".bak_ablayout")
    if revert:
        if SP.busy():
            print("editor running - close it first"); return 1
        if os.path.exists(bk):
            shutil.copy2(bk, EXE); print("restored", bk)
        return 0
    d = open(EXE, "rb").read()
    out, info = build(d)
    print("AoWDevX TMAINFORM Abilities tab:", info)
    if out is None:
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("editor running - close it first"); return 1
    if not os.path.exists(bk):
        shutil.copy2(EXE, bk)
    with open(EXE, "r+b") as f:
        f.write(out); f.truncate()
    assert open(EXE, "rb").read() == out
    import pefile
    _, chk = PAL.mainform_dfm(pefile.PE(EXE))
    PAL.DFM(chk)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
