#!/usr/bin/env python3
r"""patch_devx_banlist_ui_v1.py  [--apply | --revert]

Editor: Options -> Map Settings gets a 5th tab "Ban List" - two scrolling check lists (Spells / Abilities, sorted by
name, nothing ticked by default; ticked = banned).   (user 2026-11-20)

AoWDevX.exe itself is NOT changed on disk (its section table is full and every slack byte is claimed): the tab lives
in AoWxShot.dll - module aowxshot_banlist.py (read its header for the RE and the design), built by build_aowxshot.py -
and is wired when the editor starts by AoWxShot's Init(form), which patches two sites of the running exe in memory
after verifying their bytes.  So "applying" = writing the rebuilt AoWxShot.dll; this script is the house-style front
end for that:
    dry run   builds the DLL in memory, checks every precondition in the files on disk, reports the state
    --apply   backup AoWxShot.dll -> <game>\backup\AoWxShot.dll.bak_banui, write the new DLL
    --revert  put the backup back (only when the live DLL is the one this script would write)
Preconditions checked on disk (the DLL re-checks the two exe sites and VCL30 at run time and stays inert on a
mismatch):
    AoWDevX.exe   0x4226A5  dword 0x422FDC             TMapSettingsDlg method table: FormCreate entry
                  0x423730  e8 33 f5 ff ff             OKBtnClick: call 0x422C68 (apply dialog -> map)
                  IAT       TTabSheet 0x432C94, TLabel 0x432654, TCheckListBox 0x4332EC, GetChecked 0x4332E4,
                            SetChecked 0x4332E8, AoWHSSet 0x432898, TControl.SetText 0x432398 (thunk 0x401568)
    VCL30.dpl     RVA 0x66CC0  53 56 8B F2 8B D8 8B 83   ComCtrls.TTabSheet.SetPageControl
    AoWEPACK.dll  RVA 0x4E908  8B 40 14 C3               AoWE.TAbility.ExpandCost (base: [abil+0x14])
                  RVA 0x1BA200 BAN_GET (the storage patch; all zero = not installed -> the editor shows NO tab)
Other editor patches: nothing here touches TMAINFORM, .xprn or any exe byte, so the prune / palette / layout scripts
can be re-run in any order.  ⚠ Anything that rebuilds AoWxShot.dll (build_aowxshot.py) now includes this module.
Test without the editor: py -3.10 test_aowxshot_banlist_emu.py
"""
import argparse, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file
import build_aowxshot as SHOT
import aowxshot_banlist as BL

BAK_SUFFIX = ".bak_banui"


def pe_view(path):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; n = struct.unpack_from("<H", d, pe + 6)[0]
    base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(n)]
    def at(rva, ln):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs):
                o = ro + rva - va
                return d[o:o + ln] if rva - va < rs else bytes(ln)
        return None
    def imports():
        out = {}
        irva = struct.unpack_from("<I", d, pe + 24 + 0x68)[0]; k = 0
        while True:
            ilt, _a, _b, nm, iat = struct.unpack("<IIIII", at(irva + 20 * k, 20))
            if not nm: break
            i = 0
            while True:
                e = struct.unpack("<I", at((ilt or iat) + 4 * i, 4))[0]
                if not e: break
                out[base + iat + 4 * i] = at(e + 2, 96).split(b"\0")[0].decode("latin1"); i += 1
            k += 1
        return out
    return d, base, at, imports


def preconditions():
    probs, notes = [], []
    d, base, at, imports = pe_view(game_file("AoWDevX.exe"))
    if at(BL.MT_FORMCREATE - base, 4) != struct.pack("<I", BL.FORMCREATE):
        probs.append("AoWDevX %#x: FormCreate entry is %s" % (BL.MT_FORMCREATE, at(BL.MT_FORMCREATE - base, 4).hex()))
    if at(BL.OK_SITE - base, 5) != b"\xe8" + struct.pack("<I", BL.OK_SITE_REL):
        probs.append("AoWDevX %#x: OK call is %s" % (BL.OK_SITE, at(BL.OK_SITE - base, 5).hex()))
    imp = imports()
    for slot, want in ((BL.IAT_TABSHEET, "ComCtrls..TTabSheet@"), (BL.IAT_LABEL, "StdCtrls..TLabel@"), (BL.IAT_CHECKLB, "checklst..TCheckListBox@"),
                       (BL.IAT_GETCHECKED, "checklst.TCheckListBox.GetChecked@"), (BL.IAT_SETCHECKED, "checklst.TCheckListBox.SetChecked@"),
                       (BL.IAT_HSSET, "AoWE.AoWHSSet@"), (0x432398, "Controls.TControl.SetText@")):
        if not imp.get(slot, "").startswith(want): probs.append("AoWDevX IAT %#x is %r, not %s" % (slot, imp.get(slot), want))
    if at(BL.T_SETTEXT - base, 6) != b"\xff\x25" + struct.pack("<I", 0x432398): probs.append("AoWDevX SetText thunk %#x differs" % BL.T_SETTEXT)
    _d, _b, vat, _i = pe_view(game_file("VCL30.dpl"))
    if vat(BL.SPC_RVA, 8) != struct.pack("<II", BL.SPC_B0, BL.SPC_B1): probs.append("VCL30 SetPageControl bytes differ")
    _d, _b, eat, _i = pe_view(game_file("AoWEPACK.dll"))
    if eat(BL.EXPANDCOST_RVA, 4) != bytes.fromhex("8b4014c3"): probs.append("AoWEPACK TAbility.ExpandCost bytes differ")
    notes.append("BAN_GET (AoWEPACK %#x): %s" % (0x55700000 + BL.BANGET_RVA,
                 "present" if any(eat(BL.BANGET_RVA, 4)) else "NOT installed yet -> the editor will show no Ban List tab"))
    return probs, notes


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    img, info = SHOT.build(os.path.dirname(HERE))
    live = open(SHOT.OUT, "rb").read() if os.path.exists(SHOT.OUT) else b""
    marker = struct.pack("<ii", -1, 8) + b"Ban List\0"
    state = "ours" if live == img else "without the Ban List module" if marker not in live else "OTHER build of the Ban List module"
    probs, notes = preconditions()
    print("AoWxShot.dll: new build %d B (code %d B), live %d B: %s" % (len(img), info["code_len"], len(live), state))
    for n in notes: print("  " + n)
    if probs:
        for p in probs: print("  PROBLEM: " + p)
        print("ABORT"); return 1
    bak = bak_path(SHOT.OUT, BAK_SUFFIX)
    if a.revert:
        if state != "ours": print("live DLL is not this script's build - not reverting"); return 1
        if not os.path.exists(bak): print("no backup", bak); return 1
        shutil.copy2(bak, SHOT.OUT); print("reverted from", bak); return 0
    if state == "ours": print("already applied"); return 0
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if live and not os.path.exists(bak): shutil.copy2(SHOT.OUT, bak); print("backup ->", bak)
    with open(SHOT.OUT, "wb") as f: f.write(img)
    assert open(SHOT.OUT, "rb").read() == img
    print("Written", SHOT.OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
