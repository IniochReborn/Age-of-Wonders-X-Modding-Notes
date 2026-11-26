r"""
BRIDGE SITE LOOK v2 (2026-10-19).  AoWEPACK.dll only.  Layer on top of patch_build_bridge_v2.py (needs it applied);
upgrades patch_bridge_site_look_v1.py IN PLACE.  Art: build_bridge_site_art_v2.py (BORDER.ILB ids 199..204).

User on v1: "bridge construction GFX is all glitched - just keep the moving builders but get rid of the 'tower shell'
and the new stuff you added.  Side panel: remove 'the water' from the description.  Side image: the two images I posted
(surface / underground).  Add an event log entry when it completes: 'Bridge built'."

v1's glitch was the ART (build_bridge_site_art_v1 appended Str_bldg ids 18..26 = DUPLICATES of the crane frames
BuidFr08..11 -> every construction's crane flashed bridge art; fixed by build_bridge_site_art_v2.py).  v2 here:
  * SHW (0x55760637, TStructureResource.Show sequence fetch): a site draws ONLY the slot's chained sub-sequences =
    the STR_BLDG crane + builders (tower slots 0x19/0x1A/0x1B = STR_TOWR stub -> crane (layer 1) -> builders (layer
    3)); a slot without a sub-chain draws NOTHING for a site (v2's shw_cave drew the stub there).  No fake sequence /
    stage art any more (v1's G_SEQ is unused).
  * NM (TTower VMT +0x148 GetName): unchanged from v1 - "Bridge" (AoWE.BridgeRStr, translated).
  * DS (+0x144 GetDescription): "A bridge under construction. When it is finished, armies can cross here."
  * TP / MD / BB (+0x138 / +0x13C / +0x140 = the structure panel's top 57x2 / middle 57x50 / bottom 57x278 side-image
    strips): a site answers BORDER.ILB id 199 + 3*underground + part (199..201 surface, 202..204 underground;
    underground = the site's map level [[site+4]+0x12] != 0), through the slot-0x20 sequence's own BORDER library
    and TCustomImageLibrary.GetSafe (bounds-checked by id) - missing art -> the tower's own strip.
  * EV (inside patch_build_bridge_v2's convert, 0x5581B25C, 9 B `mov eax,esi / mov dl,1 / mov ecx,[eax] / call
    [ecx-4]` = the site's Destroy, reached only once the bridge WILL be placed): `call ev_cave` + 4 nop.  ev_cave posts
    the vanilla "structure built" event exactly like TStructure.BuildingDone 0x5575F010 does for a finished tower:
    TLocationTextEventLog.Create, [ev+0x10] = builder player [+0x24], text = Format(Translate(StructureBuiltRStr
    "%s built"), [GetName]) = "Bridge built" (localized), SetLocation(x, y, level from VMT +0x74/+0x78/+0x7C),
    DistributeLocationEventLog(ev, player, x, y, level, 0), ev.VMT+0x2C - then performs the original Destroy.
    Runs inside the MP-synchronised NewTurn conversion (same place vanilla BuildingDone posts its event).
Layout: zone 0x5581B600..0x5581C000 (inside Build Bridge's reserved 0x5581B000..0x5581E000), description literal at
  ZONE+0x900.  .idata slack G_DESC 0x5590BF00 (runtime TStringList, as v1).  Caves PIC (call/pop delta, rel32 calls).
States: clean (v2 bridge only) / v1 look / v2 look; --apply upgrades v1 -> v2 in place; --revert -> the exact pre-look
  state (v2's SHW call, the original 5 VMT values, v2's EV bytes, zone zeroed) from either v1 or v2.
Dry-run default; --apply / --revert / --dis / --dll <copy>.  Revert BEFORE patch_build_bridge_v2.py.
Backup <game>\backup\AoWEPACK.dll.bak_bridgelook2.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_build_bridge_v2 as V2
import patch_bridge_site_look_v1 as L1

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581B600, 0x5581C000
DESC_LIT = ZONE + 0x900
DESC_TEXT = b"A bridge under construction. When it is finished, armies can cross here."
ID0 = 199
EV_OLD = bytes.fromhex("89f0b2018b08ff51fc")       # v2 convert: mov eax,esi / mov dl,1 / mov ecx,[eax] / call [ecx-4]

C = dict(
    G_DESC=0x5590BF00,
    GETSEQ=0x557028E4, GETSAFE=0x5570293C,
    LOADRES=0x55701210, TRANSL=0x557249FC, LSTRCLR=0x55701140, LSTRASG=0x55701150,
    TOBJ_CREATE=0x557010A8, IMP_TSL=0x558FB944, SL_ADD=0x5570171C,
    RSTR_BRIDGE=0x55706984, RSTR_BUILT=0x55707714,     # AoWE.BridgeRStr / AoWE.StructureBuiltRStr ("%s built")
    FORMAT=0x5575A4B0,                                 # AoWE.Format(eax=fmt, edx=args, ecx=high, [stack]=&result)
    EV_CLASS=0x557FC624,                               # dword: TLocationTextEventLog class (as BuildingDone reads it)
    EV_CREATE=0x557FDC74, EV_SETLOC=0x557FDCFC, EV_DISTRIB=0x557FE558,
    ORIG_TOP=0x5575EB0C, ORIG_MID=0x5575EB58, ORIG_BOTB=0x5575EBA4, ORIG_DESC=0x5575E988, ORIG_NAME=0x5575E950,
    ID0=ID0, DESC_LIT=DESC_LIT,
)
TT = 0x557C31A8
VMTS = {"TP": (TT + 0x138, C["ORIG_TOP"]), "MD": (TT + 0x13C, C["ORIG_MID"]), "BB": (TT + 0x140, C["ORIG_BOTB"]),
        "DS": (TT + 0x144, C["ORIG_DESC"]), "NM": (TT + 0x148, C["ORIG_NAME"])}
SHW_SITE = 0x55760637

ASM = r"""
shw4:
    mov esi, dword ptr [eax + edi*4]
    test esi, esi
    jz s4_ret
    push eax
    mov eax, ebx
    call {IS_SITE}
    test al, al
    pop eax
    jz s4_t
    mov esi, dword ptr [esi + 0x0C]
s4_t:
    test esi, esi
s4_ret:
    ret

nm_cave:
    push eax
    call {IS_SITE}
    test al, al
    pop eax
    jz nm_orig
    push ebx
    push esi
    mov esi, edx
    push 0
    call nm_d
nm_d:
    pop ebx
    sub ebx, nm_d
    mov edx, esp
    lea eax, [ebx + {RSTR_BRIDGE}]
    call {LOADRES}
    mov eax, dword ptr [esp]
    mov edx, esi
    call {TRANSL}
    mov eax, esp
    call {LSTRCLR}
    pop eax
    pop esi
    pop ebx
    ret
nm_orig:
    jmp {ORIG_NAME}

ds_cave:
    push eax
    call {IS_SITE}
    test al, al
    pop eax
    jz ds_orig
    push ebx
    call ds_d
ds_d:
    pop ebx
    sub ebx, ds_d
    mov eax, dword ptr [ebx + {G_DESC}]
    test eax, eax
    jnz ds_out
    mov dl, 1
    mov eax, dword ptr [ebx + {IMP_TSL}]
    call {TOBJ_CREATE}
    mov dword ptr [ebx + {G_DESC}], eax
    lea edx, [ebx + {DESC_LIT} + 8]
    call {SL_ADD}
    mov eax, dword ptr [ebx + {G_DESC}]
ds_out:
    pop ebx
    ret
ds_orig:
    jmp {ORIG_DESC}

tp_cave:
    push eax
    call {IS_SITE}
    test al, al
    jz tp_o
    mov eax, dword ptr [esp]
    xor edx, edx
    call part_img
    test eax, eax
    jz tp_o
    add esp, 4
    ret
tp_o:
    pop eax
    jmp {ORIG_TOP}

md_cave:
    push eax
    call {IS_SITE}
    test al, al
    jz md_o
    mov eax, dword ptr [esp]
    mov edx, 1
    call part_img
    test eax, eax
    jz md_o
    add esp, 4
    ret
md_o:
    pop eax
    jmp {ORIG_MID}

bb_cave:
    push eax
    call {IS_SITE}
    test al, al
    jz bb_o
    mov eax, dword ptr [esp]
    mov edx, 2
    call part_img
    test eax, eax
    jz bb_o
    add esp, 4
    ret
bb_o:
    pop eax
    jmp {ORIG_BOTB}

part_img:
    push ebx
    push esi
    mov ebx, eax
    mov esi, edx
    mov ecx, dword ptr [ebx + 4]
    cmp byte ptr [ecx + 0x12], 0
    je pi_lv
    add esi, 3
pi_lv:
    add esi, {ID0}
    mov eax, dword ptr [ebx + 8]
    test eax, eax
    jz pi_no
    mov eax, dword ptr [eax + 0x24]
    test eax, eax
    jz pi_no
    mov edx, 0x20
    call {GETSEQ}
    test eax, eax
    jz pi_no
    mov eax, dword ptr [eax + 0x10]
    test eax, eax
    jz pi_no
    mov edx, esi
    call {GETSAFE}
    jmp pi_out
pi_no:
    xor eax, eax
pi_out:
    pop esi
    pop ebx
    ret

ev_cave:
    push ebp
    mov ebp, esp
    sub esp, 0x20
    push ebx
    push esi
    push edi
    mov ebx, esi
    xor eax, eax
    mov dword ptr [ebp - 4], eax
    mov dword ptr [ebp - 8], eax
    mov dword ptr [ebp - 0x0C], eax
    mov dword ptr [ebp - 0x10], eax
    call ev_d
ev_d:
    pop edi
    sub edi, ev_d
    xor ecx, ecx
    mov dl, 1
    mov eax, dword ptr [edi + {EV_CLASS}]
    call {EV_CREATE}
    mov esi, eax
    mov al, byte ptr [ebx + 0x24]
    mov byte ptr [esi + 0x10], al
    lea edx, [ebp - 8]
    mov eax, ebx
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0x148]
    mov eax, dword ptr [ebp - 8]
    mov dword ptr [ebp - 0x18], eax
    mov byte ptr [ebp - 0x14], 0x0B
    lea edx, [ebp - 0x0C]
    lea eax, [edi + {RSTR_BUILT}]
    call {LOADRES}
    mov eax, dword ptr [ebp - 0x0C]
    lea edx, [ebp - 0x10]
    call {TRANSL}
    lea eax, [ebp - 4]
    push eax
    mov eax, dword ptr [ebp - 0x10]
    lea edx, [ebp - 0x18]
    xor ecx, ecx
    call {FORMAT}
    mov edx, dword ptr [ebp - 4]
    lea eax, [esi + 0x18]
    call {LSTRASG}
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x7C]
    push eax
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x78]
    push eax
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x74]
    mov edx, eax
    mov eax, esi
    pop ecx
    call {EV_SETLOC}
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x78]
    push eax
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x7C]
    push eax
    push 0
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x74]
    mov ecx, eax
    mov dl, byte ptr [ebx + 0x24]
    mov eax, esi
    call {EV_DISTRIB}
    mov eax, esi
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x2C]
    lea eax, [ebp - 4]
    call {LSTRCLR}
    lea eax, [ebp - 8]
    call {LSTRCLR}
    lea eax, [ebp - 0x0C]
    call {LSTRCLR}
    lea eax, [ebp - 0x10]
    call {LSTRCLR}
    mov eax, ebx
    mov dl, 1
    mov ecx, dword ptr [eax]
    call dword ptr [ecx - 4]
    pop edi
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret
"""
ENTRIES = ("shw4", "nm_cave", "ds_cave", "tp_cave", "md_cave", "bb_cave", "part_img", "ev_cave")


def build():
    v2zone, v2lab = V2.build()
    ev_site = V2.ZONE + v2zone.index(EV_OLD)
    assert v2zone.count(EV_OLD) == 1
    fmt = dict(C, IS_SITE=v2lab["is_site"])
    src = ASM.format(**{k: hex(v) for k, v in fmt.items()})
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code = bytes(ks.asm(src, ZONE)[0])
    probe = src + "\n" + "\n".join("    call %s" % nm for nm in ENTRIES)
    penc = bytes(ks.asm(probe, ZONE)[0])
    assert penc[:len(code)] == code
    labels, q = {}, ZONE + len(code)
    for nm in ENTRIES:
        o = q - ZONE
        assert penc[o] == 0xE8, "probe for %s is not a rel32 call" % nm
        labels[nm] = q + 5 + struct.unpack_from("<i", penc, o + 1)[0]; q += 5
    assert ZONE + len(code) <= DESC_LIT, "code overlaps the literal"
    lit = struct.pack("<iI", -1, len(DESC_TEXT)) + DESC_TEXT + b"\0"
    blob = code + b"\xcc" * (DESC_LIT - ZONE - len(code)) + lit
    assert ZONE + len(blob) <= ZONE_END
    return blob, labels, v2zone, v2lab, ev_site


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, lab, v2zone, v2lab, ev_site = build()
    v1zone, v1lab, _, _ = L1.build()
    rel = V2.relocs(bytes(d), BASE)
    # v2 bridge must be applied (its zone except the EV bytes we may have changed)
    cur2 = bytearray(d[V2.ZONE - V2F:V2.ZONE - V2F + len(v2zone)])
    eo = ev_site - V2.ZONE
    ev_ours = b"\xe8" + struct.pack("<i", lab["ev_cave"] - (ev_site + 5)) + b"\x90" * 4
    ev_cur = bytes(cur2[eo:eo + 9])
    ev_st = "v2" if ev_cur == EV_OLD else "ours" if ev_cur == ev_ours else "FOREIGN"
    cur2[eo:eo + 9] = EV_OLD
    v2live = bytes(cur2) == v2zone
    rc = lambda t: b"\xe8" + struct.pack("<i", t - (SHW_SITE + 5))
    cur = bytes(d[SHW_SITE - V2F:SHW_SITE - V2F + 5])
    assert v1lab["shw3"] == lab["shw4"] == ZONE           # both looks enter at the zone start -> the zone state decides
    st = {"SHW": "v2" if cur == rc(v2lab["shw_cave"]) else "zone" if cur == rc(ZONE) else "FOREIGN",
          "EV": ev_st}
    want = {"TP": lab["tp_cave"], "MD": lab["md_cave"], "BB": lab["bb_cave"], "DS": lab["ds_cave"], "NM": lab["nm_cave"]}
    v1vm = {"BB": v1lab["bb_cave"], "DS": v1lab["ds_cave"], "NM": v1lab["nm_cave"]}
    for k, (va, van) in VMTS.items():
        v = struct.unpack_from("<I", d, va - V2F)[0]
        st[k] = "vanilla" if v == van else "ours" if v == want[k] else "v1" if v1vm.get(k) == v else "FOREIGN"
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    if not any(zl): zst = "zero"
    elif zl[:len(zone)] == zone and not any(zl[len(zone):]): zst = "ours"
    elif zl[:len(v1zone)] == v1zone and not any(zl[len(v1zone):]): zst = "v1"
    else: zst = "DIFFERS"
    bad = [hex(r) for r in rel if ZONE - 3 <= r < ZONE_END] + [hex(r) for r in rel if SHW_SITE - 3 <= r < SHW_SITE + 5] \
        + [hex(r) for r in rel if ev_site - 3 <= r < ev_site + 9]
    vmt_rel = all(va in rel for va, _ in VMTS.values())
    print("AoWEPACK bridge-site look v2 | bridge v2 %s | %s | zone %#x %s (%d B) | relocs %s | VMT slot relocs %s" % (
        "applied" if v2live else "NOT APPLIED", " ".join("%s %s" % kv for kv in st.items()), ZONE, zst, len(zone),
        bad or "none", "ok" if vmt_rel else "MISSING"))
    print("  entries: " + " ".join("%s=%#x" % kv for kv in lab.items()) + "  | EV site %#x" % ev_site)
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[:DESC_LIT - ZONE], ZONE):
            if i.mnemonic == "int3": break
            print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if not v2live: print("ABORT (patch_build_bridge_v2.py is not applied)"); return 1
    if bad or not vmt_rel or "FOREIGN" in st.values() or zst == "DIFFERS": print("ABORT (site/reloc/zone)"); return 1
    clean = st["SHW"] == "v2" and st["EV"] == "v2" and all(st[k] == "vanilla" for k in VMTS) and zst == "zero"
    v1 = st["SHW"] == "zone" and st["EV"] == "v2" and st["TP"] == "vanilla" and st["MD"] == "vanilla" \
        and all(st[k] == "v1" for k in ("BB", "DS", "NM")) and zst == "v1"
    ours = st["SHW"] == "zone" and st["EV"] == "ours" and all(st[k] == "ours" for k in VMTS) and zst == "ours"
    if not (clean or v1 or ours): print("ABORT (mixed state)"); return 1
    print("  state: %s" % ("clean (look not applied)" if clean else "look v1 -> upgrading in place" if v1 and not a.revert else "look v1" if v1 else "look v2"))
    n = bytearray(d)
    if a.revert:
        n[SHW_SITE - V2F:SHW_SITE - V2F + 5] = rc(v2lab["shw_cave"])
        n[ev_site - V2F:ev_site - V2F + 9] = EV_OLD
        for k, (va, van) in VMTS.items(): struct.pack_into("<I", n, va - V2F, van)
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        n[SHW_SITE - V2F:SHW_SITE - V2F + 5] = rc(lab["shw4"])
        n[ev_site - V2F:ev_site - V2F + 9] = ev_ours
        for k, (va, _) in VMTS.items(): struct.pack_into("<I", n, va - V2F, want[k])
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_bridgelook2")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
