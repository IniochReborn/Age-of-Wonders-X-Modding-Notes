r"""
BRIDGE SITE LOOK (2026-10-18).  AoWEPACK.dll only.  Layer on top of patch_build_bridge_v2.py (needs it applied).

User (Build Bridge v2 "works great"): "during construction, can it NOT say it's a tower - say Bridge instead with custom
gfx?  The structure panel would also need a custom side image."

The 3-turn bridge build is carried by a TTower placed on the wet hex ("bridge site" = v2's is_site: a TTower whose hex
terrain is water/ice/lava/UG water/UG ice - a vanilla tower can never stand there).  Everything below acts ONLY for a
site; every other tower (and every other structure) runs the original code.

RE (AoWEPACK unless noted):
  * Name: TStructure.GetName (TTower VMT +0x148 = 0x5575E950, eax = self, edx = &AnsiString) -> TMapObject.EditName
    (the resource name, "Tower Fort").  Every name display goes through this slot: the exe structure panel title
    (TheMapStructureSelected -> 0x44275C: [+0x148] -> label [panel+0x64]), hover/info banners, realm lists and the
    event-log captions (12 exe call sites).  -> NM: a site answers Translate(LoadResString(AoWE.BridgeRStr 0x55706984))
    = "Bridge" (the same resourcestring Build Bridge's "Build %s" uses, localized through the game's translator).
  * Description: TStructure.GetDescription (+0x144 = 0x5575E988) returns the resource's TStrings [res+0x50]; the exe
    panel Assigns it into its memo (0x44283E).  -> DS: a site returns OUR TStringList (created once, kept for the
    process) holding "A bridge under construction. When it is finished, armies can cross the water here."
  * Side image: the exe panel (0x44275C) asks +0x140 GetBottomBorderImage (existence), then +0x138 / +0x13C / +0x140
    (top 57x2 / middle 57x50 / bottom 57x278) = TImageSequence.GetPreviewImage of slots 0x1E / 0x1F / 0x20 of the
    resource's TImageSequenceList [res+0x24] - for the tower: BORDER.ILB #42/#43/#44 ("B_WatchT").  -> BB: a site's
    BOTTOM image = TCustomImageLibrary.GetSafe(BORDER lib, 195) (the slot-0x20 sequence's own linked library
    [seq+0x10], so no library loading of our own); top/middle stay the tower's sky strips (#195 continues them).
  * Map: TStructureResource.Show 0x557605DC fetches the slot sequence at 0x55760637 (v2's SHW site: `call shw_cave`)
    and walks the chained sequences ([seq+0x0C]): per sequence frame = TImageSequence.GetFrameIndex (mode [+0x19] 0 ->
    the fixed frame [+0x20]), image = [seq+0x10].Get(frame), drawn at (x + [seq+0x24], y + [seq+0x28]).  v2 drew only
    the slot-0x19 sub-chain (the STR_BLDG crane).  -> SHW3 (the site call is repointed to it): a site draws a static
    "fake" TImageSequence in .idata page slack G_SEQ (mode 0, lib = the crane's STR_BLDG library, frame = 18 + axis*3
    + stage, offset (-24, -40)) whose next pointer is the crane chain -> the half-built bridge, then the vanilla crane
    animation on top (every construction / rebuild in the game shows that crane, so the site keeps it).
      stage = days left [+0x25]: 3 -> 0 (pilings), 2 -> 1 (first planks), 1/0 -> 2 (deck nearly done);
      axis = the first opposite-land neighbour pair (HN 1/4, 2/5, 3/6 - v2's DirectionValid order) -> 0 N-S,
      1 NE-SW, 2 NW-SE (the finished bridge picks its own orientation; on a hex with land on several axes the
      construction art may face a different axis than the result).
    Art missing (Str_bldg.ILB has <= frame images) -> the v2 look (crane only); BORDER #195 missing -> the tower image.
  Art: build_bridge_site_art_v1.py (Str_bldg.ILB ids 18..26, BORDER.ILB id 195).

Layout: zone 0x5581B600..0x5581BC00 (inside Build Bridge's reserved 0x5581B000..0x5581E000; v2 ends 0x5581B538),
  description literal at ZONE+0x500.  .idata page slack (runtime zero, beyond the raw data; no other script uses it):
  G_SEQ 0x5590BEC0..0x5590BF00 (fake sequence), G_DESC 0x5590BF00 (TStringList).  All caves PIC (call/pop delta, rel32
  calls to in-image thunks).  Sites: SHW 0x55760637 (5 B, v2's call -> ours; reloc-free), TTower VMT +0x140/+0x144/
  +0x148 (each carries a reloc -> the new in-image values rebase correctly).
Dry-run default; --apply / --revert (exact: v2's SHW call, the original VMT values, zone zeroed) / --dis / --dll <copy>.
Revert this BEFORE patch_build_bridge_v2.py (its revert would otherwise see the SHW site as FOREIGN).
Backup <game>\backup\AoWEPACK.dll.bak_bridgelook.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_build_bridge_v2 as V2

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581B600, 0x5581BC00
DESC_LIT = ZONE + 0x500
DESC_TEXT = b"A bridge under construction. When it is finished, armies can cross the water here."
ART_ID0, BORDER_ID, ART_XO, ART_YO = 18, 195, -24, -40

C = dict(
    G_SEQ=0x5590BEC0, G_DESC=0x5590BF00,
    MAPVAR=V2.C["MAPVAR"], GETMAPLEVEL=V2.C["GETMAPLEVEL"], LVL_GETFIELD=V2.C["LVL_GETFIELD"],
    CENTERHN=V2.C["CENTERHN"], LAND=V2.C["LAND"],
    GETSEQ=0x557028E4,          # ILPACK TImageSequenceList.GetImageSequence(eax=list, edx=index)
    GETSAFE=0x5570293C,         # ILPACK TCustomImageLibrary.GetSafe(eax=lib, edx=index)
    LOADRES=0x55701210, TRANSL=0x557249FC, LSTRCLR=0x55701140,
    TOBJ_CREATE=0x557010A8,     # System.TObject.Create(eax=class, dl=1)
    IMP_TSL=0x558FB944,         # IAT slot: Classes.TStringList class reference (as 0x5576049A uses it)
    SL_ADD=0x5570171C,          # Classes.TStringList.Add(eax=list, edx=str)
    RSTR_BRIDGE=0x55706984,     # AoWE.BridgeRStr
    ORIG_BOTB=0x5575EBA4, ORIG_DESC=0x5575E988, ORIG_NAME=0x5575E950,
    ART_ID0=ART_ID0, BORDER_ID=BORDER_ID, ART_XO=ART_XO, ART_YO=ART_YO, DESC_LIT=DESC_LIT,
)
TT = 0x557C31A8
VMTS = {"BB": (TT + 0x140, C["ORIG_BOTB"]), "DS": (TT + 0x144, C["ORIG_DESC"]), "NM": (TT + 0x148, C["ORIG_NAME"])}
SHW_SITE = 0x55760637

ASM = r"""
shw3:
    mov esi, dword ptr [eax + edi*4]
    test esi, esi
    jz s3_ret
    push eax
    mov eax, ebx
    call {IS_SITE}
    test al, al
    pop eax
    jz s3_t
    push ecx
    push edx
    mov ecx, dword ptr [esi + 0x0C]
    test ecx, ecx
    jz s3_pop
    mov esi, ecx
    mov edx, dword ptr [ecx + 0x10]
    test edx, edx
    jz s3_pop
    mov eax, ebx
    call site_k
    add eax, {ART_ID0}
    cmp eax, dword ptr [edx + 0x44]
    jge s3_pop
    push ebx
    call s3_d
s3_d:
    pop ebx
    sub ebx, s3_d
    lea esi, [ebx + {G_SEQ}]
    pop ebx
    mov dword ptr [esi + 0x0C], ecx
    mov dword ptr [esi + 0x10], edx
    mov byte ptr [esi + 0x19], 0
    mov dword ptr [esi + 0x20], eax
    mov dword ptr [esi + 0x24], {ART_XO}
    mov dword ptr [esi + 0x28], {ART_YO}
s3_pop:
    pop edx
    pop ecx
s3_t:
    test esi, esi
s3_ret:
    ret

site_k:
    push ebx
    push ecx
    push edx
    mov ebx, eax
    movzx ecx, byte ptr [ebx + 0x25]
    mov edx, 2
    cmp ecx, 2
    jb sk_st
    mov edx, 1
    je sk_st
    xor edx, edx
sk_st:
    push edx
    mov eax, dword ptr [ebx + 4]
    movsx ecx, byte ptr [eax + 0x12]
    movsx edx, byte ptr [eax + 0x11]
    movsx eax, byte ptr [eax + 0x10]
    call axis
    lea eax, [eax + eax*2]
    pop edx
    add eax, edx
    pop edx
    pop ecx
    pop ebx
    ret

axis:
    push ebp
    mov ebp, esp
    sub esp, 0x10
    push ebx
    push esi
    push edi
    mov dword ptr [ebp - 4], eax
    mov dword ptr [ebp - 8], edx
    call ax_d
ax_d:
    pop ebx
    sub ebx, ax_d
    mov eax, dword ptr [ebx + {MAPVAR}]
    mov eax, dword ptr [eax + 0x10]
    mov edx, ecx
    call {GETMAPLEVEL}
    mov esi, eax
    xor edi, edi
    test esi, esi
    jz ax_out
ax_lp:
    lea eax, [edi + 1]
    call ax_land
    test al, al
    jz ax_nx
    lea eax, [edi + 4]
    call ax_land
    test al, al
    jnz ax_out
ax_nx:
    inc edi
    cmp edi, 3
    jl ax_lp
    xor edi, edi
ax_out:
    mov eax, edi
    pop edi
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret
ax_land:
    lea edx, [ebp - 0x0C]
    push edx
    lea edx, [ebp - 0x10]
    push edx
    mov ecx, eax
    mov edx, dword ptr [ebp - 8]
    mov eax, dword ptr [ebp - 4]
    call {CENTERHN}
    mov eax, dword ptr [ebp - 0x0C]
    test eax, eax
    jl ax_lno
    cmp eax, dword ptr [esi + 0x0C]
    jge ax_lno
    mov ecx, dword ptr [ebp - 0x10]
    test ecx, ecx
    jl ax_lno
    cmp ecx, dword ptr [esi + 0x10]
    jge ax_lno
    mov edx, eax
    mov eax, esi
    call {LVL_GETFIELD}
    mov al, byte ptr [eax + 0x14]
    call {LAND}
    ret
ax_lno:
    xor eax, eax
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

bb_cave:
    push eax
    call {IS_SITE}
    test al, al
    jz bb_orig
    mov eax, dword ptr [esp]
    mov eax, dword ptr [eax + 8]
    test eax, eax
    jz bb_orig
    mov eax, dword ptr [eax + 0x24]
    test eax, eax
    jz bb_orig
    mov edx, 0x20
    call {GETSEQ}
    test eax, eax
    jz bb_orig
    mov eax, dword ptr [eax + 0x10]
    test eax, eax
    jz bb_orig
    mov edx, {BORDER_ID}
    cmp edx, dword ptr [eax + 0x44]
    jge bb_orig
    call {GETSAFE}
    test eax, eax
    jz bb_orig
    add esp, 4
    ret
bb_orig:
    pop eax
    jmp {ORIG_BOTB}
"""
ENTRIES = ("shw3", "nm_cave", "ds_cave", "bb_cave", "site_k", "axis")


def build():
    v2zone, v2lab = V2.build()
    fmt = dict(C, IS_SITE=v2lab["is_site"])
    src = ASM.format(**{k: hex(v) for k, v in fmt.items()})
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    enc, _ = ks.asm(src, ZONE)
    code = bytes(enc)
    # entry addresses: append `call <label>` probes after the code and decode their rel32 targets
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
    return blob, labels, v2zone, v2lab


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, lab, v2zone, v2lab = build()
    rel = V2.relocs(bytes(d), BASE)
    # v2 must be applied
    v2live = bytes(d[V2.ZONE - V2F:V2.ZONE - V2F + len(v2zone)]) == v2zone
    v2_shw = b"\xe8" + struct.pack("<i", v2lab["shw_cave"] - (SHW_SITE + 5))
    our_shw = b"\xe8" + struct.pack("<i", lab["shw3"] - (SHW_SITE + 5))
    cur = bytes(d[SHW_SITE - V2F:SHW_SITE - V2F + 5])
    st = {"SHW": "v2" if cur == v2_shw else "ours" if cur == our_shw else "FOREIGN"}
    want_vm = {"BB": lab["bb_cave"], "DS": lab["ds_cave"], "NM": lab["nm_cave"]}
    for k, (va, van) in VMTS.items():
        v = struct.unpack_from("<I", d, va - V2F)[0]
        st[k] = "vanilla" if v == van else "ours" if v == want_vm[k] else "FOREIGN"
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zst = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    bad = [hex(r) for r in rel if ZONE - 3 <= r < ZONE_END] + [hex(r) for r in rel if SHW_SITE - 3 <= r < SHW_SITE + 5]
    vmt_rel = all(va in rel for va, _ in VMTS.values())
    print("AoWEPACK bridge-site look | v2 %s | %s | zone %#x %s (%d B) | relocs %s | VMT slot relocs %s" % (
        "applied" if v2live else "NOT APPLIED", " ".join("%s %s" % kv for kv in st.items()), ZONE, zst, len(zone),
        bad or "none", "ok" if vmt_rel else "MISSING"))
    print("  entries: " + " ".join("%s=%#x" % kv for kv in lab.items()) + "  | v2 is_site=%#x shw_cave=%#x" % (v2lab["is_site"], v2lab["shw_cave"]))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[:DESC_LIT - ZONE], ZONE):
            if i.mnemonic == "int3": break
            print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if not v2live: print("ABORT (patch_build_bridge_v2.py is not applied)"); return 1
    if bad or not vmt_rel or "FOREIGN" in st.values() or zst == "DIFFERS": print("ABORT (site/reloc/zone)"); return 1
    allours = st["SHW"] == "ours" and all(st[k] == "ours" for k in VMTS) and zst == "ours"
    allvan = st["SHW"] == "v2" and all(st[k] == "vanilla" for k in VMTS) and zst == "zero"
    if not (allours or allvan): print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    if a.revert:
        n[SHW_SITE - V2F:SHW_SITE - V2F + 5] = v2_shw
        for k, (va, van) in VMTS.items(): struct.pack_into("<I", n, va - V2F, van)
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        n[SHW_SITE - V2F:SHW_SITE - V2F + 5] = our_shw
        for k, (va, _) in VMTS.items(): struct.pack_into("<I", n, va - V2F, want_vm[k])
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_bridgelook")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
