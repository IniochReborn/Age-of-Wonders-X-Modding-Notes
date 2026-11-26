#!/usr/bin/env python3
r"""patch_legendary_abilities_v1.py -- a "Legendary" bonus-ability set per unit, authored in the editor.

AoW1 units carry THREE ability owners in TUnitResource (+0x38 base / +0x3C silver / +0x40 gold;
Unitres.pfs tags 0x19 / 0x1E / 0x1F). When a unit gains a medal, TUnit's grant loops call
TAbilityOwner.UpdateDefaultAbilities(unit, owner[i]) for i = 0..GetRank(). The map editor's unit
dialog shows the same owners as the None / Silver / Gold tabs of AbilityRankTabs.

This mod's Legendary medal (changelog 1.37.402) is NOT a fourth rank: a unit is Legendary when
GetRank()==2 (gold) AND its HP has reached the cap (cave 0x5580EF60, CF clear = capped). So this
patch adds a 4th owner (slot +0x44, pfs tag 0x20, editor tab "Legendary") and grants it exactly
when a unit is Legendary, without touching GetRank.

AoWEPACK.dll (all rebase-safe: rel32 only):
  1. TUnitResource: allocate / free / validate 4 owners (`cmp bl,3` -> 4 in Create 0x55784C8E,
     Destroy 0x55784CEA, ReadWrite 0x55784F66).
  2. Slot 3 (+0x44) was the transport-capacity byte (pfs tag 0x18). It moves to +0x32, the dead
     +0x32..+0x37 gap (ReadWrite maps tags to +0x2C..+0x31 and +0x44/+0x48.. only; verified by
     operand scan of the whole class). Sites: GetTransportCapacity 0x55784D46, ReadWrite 0x55784ED0.
  3. ReadWrite serialises the new owner as tag 0x20 right after gold: the 15-byte gold block at
     0x55784F3B becomes `call cave_rw` which writes gold (tag 0x1F, +0x40) then legendary
     (tag 0x20, +0x44). Records without tag 0x20 simply get an empty owner.
  4. The six `call TUnit.GetRank` sites that size the grant loops -- SetExperience old/new
     (0x557828BE / 0x557828D9), SetUnitResource (0x55782C09), NewDay (0x55782CBD) and the mod's
     set-XP cave 0x5580FF20 old/new (0x5580FF2F / 0x5580FF3B; arena training, editor medals) --
     call cave_grantrank instead: GetRank + 1 when the unit is Legendary. "HP capped" is itself a
     pure function of the XP byte and the resource (cave 0x5580EF60: (XP div 10)*2 + base HP >=
     max((7-tier)*base/2, base+6)), so the Legendary transition can only happen where XP changes,
     and SetExperience's old/new pair catches it exactly (old 2 -> new 3 grants slot 3 once).
     NewDay re-grants daily (the merge is idempotent) and SetUnitResource re-templating gets it
     too. Stat tables, medal icons, arena costs and every other GetRank consumer are untouched.

AoWDevX.exe (base 0x400000, CODE file = VA - 0x400C00):
  5. the transport-capacity spin write `mov [esi+0x44],al` @VA 0x411166 -> +0x32.
  6. TUnitResourceEditForm DFM (RCDATA @file 0xDA3C4, 0x12B8 bytes, EXACTLY full, cannot grow):
     AbilityRankTabs.Tabs.Strings None/Silver/Gold -> None/Silver/Gold/Legend (+8 bytes), paid for
     by dropping the control's redundant `TabOrder = 0` (11 bytes; it is the first child of its
     group box so creation order gives it 0 anyway -- BXL's copper-medal recipe), and the strip
     widened/centred (Left 8->6, Width 185->193, Edit button Left 67->69; same-size encodings) so
     the four tabs never need comctl's scroll arrows (v1 used "Legendary" at 185 px and got them).
     The editor indexes owners as [unitres + tabIndex*4 + 0x38] (0x410F65 etc.), so tab 3 = +0x44.
     A DFM holding an earlier tuning of this script (DFM_PRIOR) is rewritten in place on --apply.

Data: no unit carries tag 0x20 until authored, so Legendary sets start empty. Old saves / maps
load unchanged (capacity is re-read from tag 0x18 into its new offset).

Dry-run default; --apply; --revert; --dll / --exe paths; --dis.   Close the game AND the editor.
Backups: AoWEPACK.dll.bak_legendary, AoWDevX.exe.bak_legendary.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dfm_edit                                                   # noqa: E402  (vendored from BXL)

GAME = game_dir()
DEFAULT_DLL = os.path.join(GAME, "AoWEPACK.dll")
DEFAULT_EXE = os.path.join(GAME, "AoWDevX.exe")
BAK = ".bak_legendary"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x55700000

GETRANK   = 0x5578294C
ISCAPPED  = 0x5580EF60          # (ebx=unit) -> CF clear when HP is at the cap; preserves eax/ecx/edx
LEG_TAG   = 0x20
CAP_OLD, CAP_NEW = 0x44, 0x32
CAVE_LO, CAVE_HI = 0x55815F00, 0x55816000

# ---- dll sites --------------------------------------------------------------------------------
CREATE_N, DESTROY_N, VALID_N = 0x55784C8E, 0x55784CEA, 0x55784F66      # imm8 of `cmp bl,3`
CAP_READ, CAP_RW = 0x55784D46, 0x55784ED0                             # disp8 bytes
RW_GOLD = 0x55784F3B
RW_GOLD_ORIG = bytes.fromhex("b91f000000 8b5740 8bc6 8b18 ff530c".replace(" ", ""))   # 15 B
GRANT_SITES = [(0x557828BE, "SetExperience: old rank"), (0x557828D9, "SetExperience: new rank"),
               (0x55782C09, "SetUnitResource: rank"), (0x55782CBD, "NewDay: rank"),
               (0x5580FF2F, "SetXP cave 0x5580FF20: old rank"), (0x5580FF3B, "SetXP cave 0x5580FF20: new rank")]

# ---- editor sites -----------------------------------------------------------------------------
ED_CODE_DELTA = 0x400C00
ED_CAP_WRITE = 0x411168          # disp8 of `mov byte ptr [esi+0x44],al`
ED_DFM_OFF, ED_DFM_SIZE = 0xDA3C4, 0x12B8
ED_TABS = "AbilityRankTabs"
ED_BTN = "AbilityBtn"
# DFM tunings: (captions, keep TabOrder, tabs Left, tabs Width, Edit-button Left).  All encodings stay
# the same size (Left/button Left vaInt8, Width vaInt16), so the resource never grows.
DFM_VANILLA = (["None", "Silver", "Gold"], True, 8, 185, 67)
# v1 (2026-09-13): "Legendary" at the vanilla width put comctl's scroll arrows on the tab strip (the
# four tabs need ~176 px of the ~181 px client at 96 dpi, and more with a scaled font).
DFM_PRIOR = [(["None", "Silver", "Gold", "Legendary"], False, 8, 185, 67)]
# v2: "Legend" (158 px) and the strip widened 185 -> 193 / centred (Left 6, button 69): no arrows.
DFM_NEW = (["None", "Silver", "Gold", "Legend"], False, 6, 193, 69)


class Asm:
    def __init__(self, va): self.va, self.buf, self.lab, self.fix = va, bytearray(), {}, []
    def here(self): return self.va + len(self.buf)
    def db(self, *b): self.buf += bytes(b); return self
    def dd(self, v): self.buf += struct.pack("<I", v & 0xFFFFFFFF); return self
    def call(self, t): self.db(0xE8); self.buf += struct.pack("<i", t - (self.here() + 4)); return self
    def label(self, n): self.lab[n] = self.here()
    def j8(self, op, n): self.db(op); self.fix.append((len(self.buf), n)); self.db(0)
    def done(self):
        for off, n in self.fix:
            rel = self.lab[n] - (self.va + off + 1); assert -128 <= rel <= 127
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)


def build_cave_grantrank(va):
    """eax=unit -> al = GetRank(unit) + (gold and HP-capped ? 1 : 0). Flags/regs as GetRank."""
    a = Asm(va)
    a.db(0x53)                                      # push ebx
    a.db(0x8B, 0xD8)                                # mov ebx,eax
    a.call(GETRANK)                                 # al = rank
    a.db(0x3C, 0x02); a.j8(0x75, "out")             # cmp al,2 ; jne out
    a.call(ISCAPPED)                                # CF = not capped   (eax preserved)
    a.j8(0x72, "out")                               # jb out
    a.db(0xFE, 0xC0)                                # inc al   -> 3 = legendary
    a.label("out"); a.db(0x5B); a.db(0xC3)          # pop ebx ; ret
    return a.done()


def build_cave_rw(va):
    """Replaces the gold-owner block of TUnitResource.ReadWrite: gold (tag 0x1F) then legendary (0x20).
    esi = the reader/writer, edi = the resource, ebx = scratch (the host reloads it)."""
    a = Asm(va)
    for tag, off in ((0x1F, 0x40), (LEG_TAG, 0x44)):
        a.db(0xB9); a.dd(tag)                       # mov ecx,tag
        a.db(0x8B, 0x57, off)                       # mov edx,[edi+off]
        a.db(0x8B, 0xC6)                            # mov eax,esi
        a.db(0x8B, 0x18)                            # mov ebx,[eax]
        a.db(0xFF, 0x53, 0x0C)                      # call [ebx+0xC]
    a.db(0xC3)
    return a.done()


def dll_layout():
    p = CAVE_LO
    g = build_cave_grantrank(p); cave_g = p; p = (p + len(g) + 3) & ~3
    r = build_cave_rw(p); cave_r = p; p = (p + len(r) + 3) & ~3
    assert p <= CAVE_HI
    def call(src, dst): return b"\xE8" + struct.pack("<i", dst - (src + 5))
    patches = [
        (CREATE_N, b"\x03", b"\x04", "TUnitResource.Create: 4 owners"),
        (DESTROY_N, b"\x03", b"\x04", "TUnitResource.Destroy: 4 owners"),
        (VALID_N, b"\x03", b"\x04", "TUnitResource.ReadWrite: validate 4 owners"),
        (CAP_READ, bytes([CAP_OLD]), bytes([CAP_NEW]), "GetTransportCapacity reads +0x32"),
        (CAP_RW, bytes([CAP_OLD]), bytes([CAP_NEW]), "ReadWrite tag 0x18 (capacity) at +0x32"),
        (RW_GOLD, RW_GOLD_ORIG, call(RW_GOLD, cave_r) + b"\x90" * 10, "ReadWrite gold block -> cave_rw (gold + legendary tag 0x20)"),
    ]
    for va, desc in GRANT_SITES:
        patches.append((va, call(va, GETRANK), call(va, cave_g), "grant loop %s -> cave_grantrank" % desc))
    patches += [(cave_g, bytes(len(g)), g, "cave_grantrank"), (cave_r, bytes(len(r)), r, "cave_rw")]
    return patches, [(cave_g, g, "cave_grantrank"), (cave_r, r, "cave_rw")]


# ---- editor -----------------------------------------------------------------------------------
def dfm_int(name, v):
    enc = bytes([dfm_edit.I8, v & 0xFF]) if -128 <= v <= 127 else bytes([dfm_edit.I16]) + struct.pack("<h", v)
    return dfm_edit.shortstr(name) + enc


def dfm_rewrite(region, tuning):
    """Normalising rewrite of the rank-tab strip (BXL's copper-medal recipe): set the captions, drop
    (or restore) the redundant TabOrder that pays for the 4th caption, and set the geometry.  Every
    tuning is produced from the same source region, so any tuning can be recognised and rewritten."""
    captions, keep_taborder, tabs_left, tabs_width, btn_left = tuning
    w = dfm_edit.walk(region)
    assert w.consumed <= len(region) and all(b == 0 for b in region[w.consumed:]), "junk after DFM"
    ti_a, ti_b = dfm_edit.find(w, ED_TABS, "TabIndex")
    tabs = [p for p in w.props if p[0].endswith(ED_TABS) and p[1] == "Tabs.Strings" and p[2] == dfm_edit.LIST]
    assert len(tabs) == 1
    ts_a, ts_b = tabs[0][3], tabs[0][4]
    mid = [p for p in w.props if p[0].endswith(ED_TABS) and ti_b <= p[3] < ts_a and p[1] != "$class"]
    assert all(p[1] == "TabOrder" for p in mid), "unexpected properties between TabIndex and Tabs"
    taborder = dfm_edit.shortstr("TabOrder") + bytes([dfm_edit.I8, 0]) if keep_taborder else b""
    newtabs = dfm_edit.shortstr("Tabs.Strings") + bytes([dfm_edit.LIST]) + dfm_edit.string_list(captions)
    edits = [(ti_b, ts_b, taborder + newtabs)]
    for suffix, name, val in ((ED_TABS, "Left", tabs_left), (ED_TABS, "Width", tabs_width), (ED_BTN, "Left", btn_left)):
        a, b = dfm_edit.find(w, suffix, name)
        edits.append((a, b, dfm_int(name, val)))
    out = bytearray(region[:w.consumed])
    for a, b, nb in sorted(edits, reverse=True):
        out[a:b] = nb
    assert len(out) <= ED_DFM_SIZE, "DFM would grow past its resource (%d > %d)" % (len(out), ED_DFM_SIZE)
    out = bytes(out) + b"\x00" * (ED_DFM_SIZE - len(out))
    w2 = dfm_edit.walk(out)
    touched = {(ED_TABS, "TabOrder"), (ED_TABS, "Tabs.Strings"), (ED_TABS, "Left"), (ED_TABS, "Width"), (ED_BTN, "Left")}
    def sig(ww):
        return [(p[0], p[1], p[2], p[5]) for p in ww.props
                if not any(p[0].endswith(s) and p[1] == n for s, n in touched)]
    assert sig(w2) == sig(w), "DFM rewrite disturbed an unrelated property"
    got = [p[5] for p in w2.props if p[0].endswith(ED_TABS) and p[1] == "Tabs.Strings" and p[2] == dfm_edit.LIST]
    assert got == [captions]
    for suffix, name, val in ((ED_TABS, "Left", tabs_left), (ED_TABS, "Width", tabs_width), (ED_BTN, "Left", btn_left)):
        assert [p[5] for p in w2.props if p[0].endswith(suffix) and p[1] == name] == [val]
    return out


def find_dfm_source(data):
    """The DFM region as it is on disk may already hold a tuning; recover the vanilla region from it
    (all tunings are same-size rewrites of the same bytes, so undoing one is another rewrite)."""
    region = bytes(data[ED_DFM_OFF:ED_DFM_OFF + ED_DFM_SIZE])
    for t in [DFM_VANILLA] + DFM_PRIOR + [DFM_NEW]:
        try:
            if dfm_rewrite(region, t) == region:
                return dfm_rewrite(region, DFM_VANILLA)
        except AssertionError:
            pass
    raise SystemExit("editor DFM at 0x%X holds no known state" % ED_DFM_OFF)


def exe_patches(data):
    vanilla = find_dfm_source(data)
    return [
        (ED_CAP_WRITE - ED_CODE_DELTA, bytes([CAP_OLD]), bytes([CAP_NEW]), "editor: capacity spin write -> +0x32"),
        (ED_DFM_OFF, vanilla, dfm_rewrite(vanilla, DFM_NEW),
         "editor: AbilityRankTabs None/Silver/Gold/%s (%d px, no scroll arrows)" % (DFM_NEW[0][-1], DFM_NEW[3]),
         [dfm_rewrite(vanilla, t) for t in DFM_PRIOR]),
    ]


# ---- helpers ------------------------------------------------------------------------------------
def va2off(data, va):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        vsz, sva, rsz, praw = struct.unpack_from("<IIII", data, o + 8)
        if BASE + sva <= va < BASE + sva + max(vsz, rsz):
            return praw + (va - BASE - sva)
    raise ValueError("VA %08X" % va)


def relocs(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    rva, size = struct.unpack_from("<II", data, pe + 24 + 96 + 5 * 8)
    p = va2off(data, BASE + rva); end = p + size; out = set()
    while p < end:
        pg, blk = struct.unpack_from("<II", data, p)
        if blk < 8: break
        for k in range(8, blk, 2):
            e = struct.unpack_from("<H", data, p + k)[0]
            if e >> 12 == 3: out.add(BASE + pg + (e & 0xFFF))
        p += blk
    return out


def disasm(code, va):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return "  (capstone not installed)"
    return "\n".join("  %08X  %-20s %-6s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str)
                     for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, va))


def write_inplace(path, data):
    assert len(data) == os.path.getsize(path)
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.flush(); os.fsync(f.fileno())


def classify(data, patches, offfn):
    """Each patch is (va, old, new, desc[, priors]); a site holding one of `priors` (an earlier tuning
    of this script) is 'prior': rewritten in place on --apply, restored to `old` on --revert."""
    out = []
    for p in patches:
        va, old, new = p[0], p[1], p[2]; priors = p[4] if len(p) > 4 else []
        off = offfn(va); cur = bytes(data[off:off + len(old)])
        out.append("patched" if cur == new else "vanilla" if cur == old else "prior" if cur in priors else "OTHER")
    return out


def run_file(path, patches, offfn, args, reloc_set=None):
    data = bytearray(open(path, "rb").read())
    state = classify(data, patches, offfn)
    for p, s in zip(patches, state):
        print("  [%-7s] %08X  %s" % (s, p[0], p[3]))
    if any(s == "OTHER" for s in state):
        print("  ABORT: a site holds bytes that are neither vanilla nor this patch."); return False
    if args.revert:
        todo = [p for p, s in zip(patches, state) if s in ("patched", "prior")]
        if not todo: print("  nothing applied here."); return True
        for va, old, new, desc in (p[:4] for p in todo):
            off = offfn(va); data[off:off + len(old)] = old
        write_inplace(path, data); print("  reverted %d site(s)." % len(todo)); return True
    todo = [p for p, s in zip(patches, state) if s in ("vanilla", "prior")]
    if not todo: print("  already fully applied."); return True
    if reloc_set is not None:
        hits = [r for va, old, new, desc in (p[:4] for p in todo) for r in reloc_set if va - 3 <= r < va + len(new)]
        if hits: print("  ABORT: .reloc entries inside a window: %s" % ", ".join("%08X" % h for h in hits)); return False
    print("  %d site(s) to write." % len(todo))
    if not args.apply: return True
    bak = bak_path(path, BAK)
    if not os.path.exists(bak): shutil.copyfile(path, bak); print("  backup: %s" % bak)
    for va, old, new, desc in (p[:4] for p in todo):
        off = offfn(va); data[off:off + len(new)] = new; print("  patched: %s" % desc)
    write_inplace(path, data); print("  written."); return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL); ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    args = ap.parse_args()
    dll, exe = os.path.abspath(args.dll), os.path.abspath(args.exe)
    dpatches, caves = dll_layout()
    if args.dis:
        for va, body, desc in caves:
            print("\n%s @0x%X (%d B)\n%s" % (desc, va, len(body), disasm(body, va)))
    print("\n== %s" % dll)
    ddata = open(dll, "rb").read()
    ok = run_file(dll, dpatches, lambda va: va2off(ddata, va), args, relocs(ddata))
    print("\n== %s" % exe)
    edata = open(exe, "rb").read()
    ok2 = run_file(exe, exe_patches(edata), lambda o: o, args)
    if not (ok and ok2): return 1
    if not args.apply and not args.revert: print("\nDry run OK. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
