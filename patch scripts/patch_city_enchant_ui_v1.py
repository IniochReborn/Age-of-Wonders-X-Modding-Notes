"""
City enchantment UI (2026-10-13; v2 10-14; v3 10-14): AoWEPACK.dll.

 1. "add the city enhancements text field" - City.TCity.ListEnhancementsInfo 0x557A9A0C (eax = city -> ebx, edx = the
    TStrings -> esi) builds the city window's enhancement lines with FOUR sequential bit tests on the city enchantment
    bitset [city+0x5C] (bit = 1 shl type: 1 Fountain Of Life (type 0), 2 Gold Rush (1), 4 type 2 (spell 54), 8 Warmonger
    (3); the bitset is recomputed from the registered TCityEnchantment list [city+0x58] by 0x557A9814); each line =
    Translate(LoadResString(name)) + ' ' + Translate(LoadResString(EnchantmentRStr 0x55706DDC "Enchantment")) via
    LStrCatN(3) -> TStrings.Add (VMT+0x34).  Arms Race = type 4 = bit 0x10 had no line.  Hook A on the function's 8-byte
    epilogue 0x557A9C27 (`xor eax,eax / pop edx / pop ecx / pop ecx / mov fs:[eax],edx`): bit 0x10 -> the same construction
    with the cave literal "Arms Race" (LStrAsg into the vanilla temporaries [ebp-0x10]/[ebp-0x18]/[ebp-0x14]/[ebp-4], which
    the vanilla finally block frees), then the replayed epilogue.

 2. City enchantment GFX - City.TCityOverlayHS.Show 0x557A91D0 (eax = hs (esi), edx = dx, ecx = dy, [ebp+8] = surface;
    [hs+0xC] = city; [ebp-4]/[ebp-8] = HXtoHP(city hex) - dx/dy = the hex origin on screen; hex = 32x32, centre =
    origin+(16,16)) draws the vanilla overlays for Warmonger (bit 8: per-size city-resource alt-list seq 0x11 = AMSHELL.ILB
    image 30, 33x32, pulsing blend, at (0,-18)/(10,-25)/(-21,-40)/(2,-47) for sizes 1..4), Gold Rush (bit 2: seq 0x12) and
    type 2 (bit 4: seq 0x13 = the AMSHELL shell, one image per city size) - nothing for Fountain Of Life (bit 1) or Arms
    Race (0x10).  Hook B on its 13-byte visibility check 0x557A920A (`mov ecx,[esi+0xC] / cmp byte [ecx+0x64],0 /
    je 0x557A950A`; [city+0x64] = visible to the seated player) draws, per bit set:
      bit 0x01 Fountain Of Life: spell 375's gfx SLOT 1 (the dedicated city sparkle the pipeline wires into Spells.pfs
               record 385; v3) on EVERY hex of the city: footprint by city size ([[city+8]+0x78] = TCity.GetSize
               0x557AA938, 1..4) from the pad resources (Release.hss TPadResource tag 7 = count + per-spiral-index
               (terrain, overlay) byte pairs, 0xFE = not part; spiral = HSEngine ring iterator 0x5560E5C8/0x5560E610,
               direction table 0x5562E250): size 1 = centre; 2 = centre + NE; 3 = centre + SW + NW; 4 = centre + N + NE +
               NW; neighbour pixel offsets are column-parity independent (N (0,-32), NE (32,-16), NW (-32,-16), SW
               (-32,16)) -> FOOT table.  Each hex gets tick + TICK_PHASE*i so they twinkle out of phase.
      bit 0x10 Arms Race: spell 375's gfx SLOT 0 (the forge-glow cog, 48x48 at xs/ys -24/-30) BELOW the Warmonger glow:
               anchor = (xs+16, ys+32+31) per size -> ARMS table (16,45) / (26,38) / (-5,23) / (18,16).
    v3 PURE DRAW (no shared state): v2 used ImageLib.TImageSequenceList.ShowLooped, whose TImageSequence.GetFrameIndex
    (ILPACK 0x552186EC) for a kind-4 sequence (jump-table case 0x55218738) advances the sequence's OWN counters
    ([seq+0x30] countdown of [seq+0x18] = f18 ticks, [seq+0x34] frame index) on EVERY call without comparing the tick
    [seq+0x2C] - so N draws per frame = N x speed, and the general-FX slot 0x46 sequence object is shared by every unit
    sparkle: our per-hex/per-city draws sped them all up.  v3 selects the frame itself - idx = (tick / CITY_PERIOD) mod
    n with n = [[seq+0x1C]+8] (frame TList count), id = [[seq+0x1C]+4][idx] - and blits it the way Show's own code does:
    TCustomImageLibrary.ImageExist/Get (thunks 0x55702944/0x55702934, eax = [seq+0x10] library, edx = id) ->
    image.VMT+0x84 Draw(edx = x + [seq+0x24], ecx = y + [seq+0x28], push surface).  Nothing is written to the sequence,
    the pace is CITY_PERIOD ticks per frame regardless of the number of hexes/cities, and f18/f20 of the slot are ignored
    (chains [seq+0xC] are ignored too: single sequences).  Both slots come from GetSpell(375) = AoWE.TSpellControl.GetSpell
    0x55779AC8(eax = [AoWHSSet 0x558FA044]+0x84, edx = id) -> [spell+0x2C] list -> TImageSequenceList.GetImageSequence
    thunk 0x557028E4 (eax = list, edx = INDEX) -> seq (nil-checked).  Map tick = [[AoWHSMap 0x558FA040]+0x40].

 3. "the glow only shows while a vanilla city enchantment is active" - the overlay HS [city+0x60] (created in TCity.Create
    0x557A95A8, never Place'd) only enters the scene through City.TCity.MakeVisible 0x557AA8F8 (VMT+0xF0, called per frame
    for every HS of every visible field by TMapField.CopyDynamic/StaticVisibleHS): `al := [city+0x5C] AND [0x557AA930];
    if al <> [0x557AA934] then overlay.MakeVisible(scene)` with the mask byte 0x557AA930 = 0x0E (bits 2|4|8) and the
    compare byte 0x557AA934 = 0.  Hook C: the mask byte 0x0E -> 0x1F (bits 1 and 0x10 included).  The scene list is rebuilt
    every frame (THSMap.ResetVisibleDynamicHS), so casting/expiry needs no extra invalidation; TCityOverlayHS.Show's own
    [city+0x64] gate and GetShowPriority (city + 0x8000000) are unchanged.  (TCity.UpdateVisibleForSeatedPlayer
    0x557AD5CC already triggers a redraw for ANY enchantment bit.)
Zone 0x55863500..0x55863800 (zero, reloc-free); PIC via the call/pop delta for every in-image address (AoWEPACK
rebases).  Backup <game>\\backup\\AoWEPACK.dll.bak_cityench (whole-file - never restore by copy; --revert un-hooks in place).
Dry-run default; --apply / --revert / --dis.  A v1/v2 zone is detected as "DIFFERS" and --apply re-syncs it in place
(hooks A/B are the same bytes; hook C is new); --revert then --apply is equivalent.
Lessons: GetImageSequence is BY INDEX; the per-size overlay art lives in the per-size TCityResource alt lists (0x10 FIRESM,
0x11 Warmonger, 0x12 Gold Rush, 0x13 shell, 0x14 DESTR, 0x15 SMOKE, 0x16 CITYn frame 6); the pad image list (13 slots) is
per TERRAIN TYPE, the footprint is tag 7; spellgfx.seq_parse asserts no trailing bytes (use _seq_parse); [city+0x64] is
"visible to the seated player", not an enchantment flag.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_cityench"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55863500, 0x55863D00          # v4: grown (0x55863800..0x55863CFF verified zero 10/15)

# hook A: ListEnhancementsInfo epilogue
HA_SITE, HA_ORIG, HA_RESUME = 0x557A9C27, bytes.fromhex("33c05a5959648910"), 0x557A9C2F
ARMS_BIT, FOUNTAIN_BIT = 0x10, 0x01
LSTR_ASG, LOAD_RES_STRING, TRANSLATE, LSTR_CATN = 0x55701150, 0x55701210, 0x557249FC, 0x55701198
SPACE_LITERAL, ENCH_RSTR_VAR = 0x557A9C60, 0x558E8F8C            # the vanilla ' ' literal; [var] = PResStringRec "Enchantment"

# hook B: TCityOverlayHS.Show visibility check
HB_SITE, HB_ORIG, HB_RESUME, HB_EXIT = 0x557A920A, bytes.fromhex("8b4e0c807964000f84f3020000"), 0x557A9217, 0x557A950A
AOWHSSET, AOWHSMAP, SPELLCONTROL_OFF, GETSPELL = 0x558FA044, 0x558FA040, 0x84, 0x55779AC8
GETIMAGESEQ, IMAGEEXIST, LIBGET = 0x557028E4, 0x55702944, 0x55702934   # ILPACK thunks: TImageSequenceList.GetImageSequence(list, idx), TCustomImageLibrary.ImageExist/Get(lib, id)
GFX_SPELL, ARMS_SLOT, CITY_SLOT = 375, 0, 1                           # Spells.pfs record 385: slot 0 = Arms Race cog, slot 1 = the city enchantment sparkle
CITY_PERIOD = 6                 # map ticks per frame for the city sparkle (the unit sparkle steps once per draw call; ~1/3 of its pace); v3.1 (2026-10-14, user: the cog slowed down): the Arms Race cog passes tick*3 -> 2 ticks/frame = its old f18=1 pace
TICK_PHASE = 7                  # tick offset between the sparkles of one city's hexes
ANCHOR_CITY = (16, 16)          # hex origin -> hex centre; the slot-1 sequence's own xs/ys (-24,-24 for 48x48) centre the frame there
FOOT = [[(0, 0)],
        [(0, 0), (32, -16)],
        [(0, 0), (-32, 16), (-32, -16)],
        [(0, 0), (0, -32), (32, -16), (-32, -16)]]
FOOT_MAX = 4
WARMONGER = [(0, -18), (10, -25), (-21, -40), (2, -47)]              # AMSHELL image 30 (33x32) offsets per city size
ARMS = [(xs + 16, ys + 32 + 31) for xs, ys in WARMONGER]              # cog (48x48 at -24/-30) anchor: centred under the glow, 1 px below it

# v4 (2026-10-15) PLAGUE (spell 341, patch_blesseddew_v1.py v4): INF_EXPORT = `jmp inf` there (esi = city -> al = 1 if the
# city is plagued; every other register preserved).  Hook A adds the 'Plague' line, hook B draws spell 341 gfx SLOT 3
# on every hex of a plagued city (the Fountain Of Life footprint, out of phase per hex), hook D makes the overlay HS visible
# for a plagued city that has no enchantment bit (vanilla only does that for bits in the mask).
INF_EXPORT = 0x5582BFF0
PLAGUE_SPELL, PLAGUE_SLOT = 341, 3
PLAGUE_LINE = "Plague (-50% income, unrest)"
HD_SITE, HD_ORIG, HD_CALLEE = 0x557AA908, bytes.fromhex("e88f78f5ff"), 0x5570219C   # TCity.MakeVisible: call TMapObject.MakeVisible (rel32, no reloc)
OVERLAY_MASK_ALL = 0x1F         # = hook C's mask (bits the vanilla test already makes visible)

# hook C: TCity.MakeVisible overlay mask byte (bits 2|4|8 -> also 1|0x10)
HC_SITE, HC_ORIG, HC_NEW = 0x557AA930, b"\x0e", b"\x1f"

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    """`call $D / pop ebx / sub ebx, $D` two-pass PIC idiom (keystone hangs on a label used as an immediate)."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    anchor = bytes.fromhex("e8000000005b81ebffffff7f")
    k = b.find(anchor); assert k >= 0, "delta anchor not found"
    while k >= 0:                                                                                  # v4: every anchor
        struct.pack_into("<I", b, k + 8, va + k + 5); k = b.find(anchor, k + 12)
    return bytes(b)


def delphi_literal(s):
    b = s.encode("latin1"); return struct.pack("<iI", -1, len(b)) + b + b"\0"


def build_a(va, lit_va, plit_va):
    src = """
        test byte ptr [ebx+0x5c], %(bit)d
        jz a_done
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        lea eax, [ebp-0x10]
        lea edx, [ebx+%(lit)#x]
        call %(asg)#x
        push dword ptr [ebp-0x10]
        lea edx, [ebx+%(space)#x]
        push edx
        mov eax, [ebx+%(rsvar)#x]
        lea edx, [ebp-0x18]
        call %(lrs)#x
        mov eax, [ebp-0x18]
        lea edx, [ebp-0x14]
        call %(trans)#x
        push dword ptr [ebp-0x14]
        lea eax, [ebp-4]
        mov edx, 3
        call %(catn)#x
        pop ebx
        mov edx, [ebp-4]
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x34]
    a_done:
        push esi
        mov esi, ebx
        call %(infx)#x
        pop esi
        test al, al
        jz p_done
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        lea eax, [ebp-4]
        lea edx, [ebx+%(plit)#x]
        call %(asg)#x
        pop ebx
        mov edx, [ebp-4]
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x34]
    p_done:
        xor eax, eax
        pop edx
        pop ecx
        pop ecx
        mov dword ptr fs:[eax], edx
        jmp %(resume)#x
    """ % {"bit": ARMS_BIT, "lit": lit_va, "asg": LSTR_ASG, "space": SPACE_LITERAL, "rsvar": ENCH_RSTR_VAR, "lrs": LOAD_RES_STRING,
           "trans": TRANSLATE, "catn": LSTR_CATN, "resume": HA_RESUME, "infx": INF_EXPORT, "plit": plit_va}
    return asm_delta(src, va)


def foot_table():
    out = b""
    for ent in FOOT:
        assert len(ent) <= FOOT_MAX
        out += struct.pack("<I", len(ent)) + b"".join(struct.pack("<ii", dx, dy) for dx, dy in ent) + bytes(8 * (FOOT_MAX - len(ent)))
    return out


def arms_table():
    return b"".join(struct.pack("<ii", dx, dy) for dx, dy in ARMS)


def build_b(va, foot_va, arms_va):
    """Entry: esi = hs, [ebp-4]/[ebp-8] = hex origin, [ebp+8] = surface.  ebx = PIC delta, edi = size index 0..3.
    pdraw(eax = seq; stack: x, y, tick, surface; ret 0x10): pure frame pick + blit (see docstring).  The slot sequences
    are fetched once into stack slots: [esp] = city seq (slot 1) or 0, [esp+4] = arms seq (slot 0) or 0."""
    src = """
        mov ecx, [esi+0xc]
        cmp byte ptr [ecx+0x64], 0
        je %(exit)#x
        test byte ptr [ecx+0x5c], %(both)d
        jnz b_go
        push esi
        mov esi, ecx
        call %(infx)#x
        pop esi
        test al, al
        jz %(resume)#x
    b_go:
        push ebx
        push edi
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ecx+8]
        movzx eax, byte ptr [eax+0x78]
        dec eax
        cmp eax, 3
        jbe size_ok
        xor eax, eax
    size_ok:
        mov edi, eax
        push 0
        push 0
        mov eax, [ebx+%(hsset)#x]
        mov eax, [eax+%(sc)#x]
        mov edx, %(spell)d
        call %(getspell)#x
        test eax, eax
        jz seqs_done
        mov eax, [eax+0x2c]
        test eax, eax
        jz seqs_done
        push eax
        mov edx, %(cslot)d
        call %(getseq)#x
        mov [esp+4], eax
        pop eax
        mov edx, %(aslot)d
        call %(getseq)#x
        mov [esp+4], eax
    seqs_done:
        mov ecx, [esi+0xc]
        test byte ptr [ecx+0x5c], %(fbit)d
        jz f_done
        cmp dword ptr [esp], 0
        je f_done
        lea edx, [edi+edi*8]
        lea edx, [ebx+edx*4+%(foot)#x]
        push edx
        push 0
    f_loop:
        mov edx, [esp+4]
        mov eax, [esp]
        cmp eax, [edx]
        jae f_end
        push dword ptr [ebp+8]
        lea ecx, [eax+eax*2]
        lea ecx, [eax+ecx*2]
        mov edx, [ebx+%(hsmap)#x]
        add ecx, [edx+0x40]
        push ecx
        mov edx, [esp+12]
        mov eax, [esp+8]
        mov ecx, [edx+eax*8+8]
        add ecx, [ebp-8]
        add ecx, %(cdy)d
        push ecx
        mov ecx, [edx+eax*8+4]
        add ecx, [ebp-4]
        add ecx, %(cdx)d
        push ecx
        mov eax, [esp+24]
        call pdraw
        inc dword ptr [esp]
        jmp f_loop
    f_end:
        add esp, 8
        mov ecx, [esi+0xc]
    f_done:
        test byte ptr [ecx+0x5c], %(abit)d
        jz a_done2
        cmp dword ptr [esp+4], 0
        je a_done2
        push dword ptr [ebp+8]
        mov edx, [ebx+%(hsmap)#x]
        mov edx, [edx+0x40]
        lea edx, [edx+edx*2]
        push edx
        mov edx, [ebx+edi*8+%(arms4)#x]
        add edx, [ebp-8]
        push edx
        mov ecx, [ebx+edi*8+%(arms)#x]
        add ecx, [ebp-4]
        push ecx
        mov eax, [esp+20]
        call pdraw
    a_done2:
        push esi
        mov esi, [esi+0xc]
        call %(infx)#x
        pop esi
        test al, al
        jz pl_done
        mov eax, [ebx+%(hsset)#x]
        mov eax, [eax+%(sc)#x]
        mov edx, %(pspell)d
        call %(getspell)#x
        test eax, eax
        jz pl_done
        mov eax, [eax+0x2c]
        test eax, eax
        jz pl_done
        mov edx, %(pslot)d
        call %(getseq)#x
        test eax, eax
        jz pl_done
        push eax
        lea edx, [edi+edi*8]
        lea edx, [ebx+edx*4+%(foot)#x]
        push edx
        push 0
    pl_loop:
        mov edx, [esp+4]
        mov eax, [esp]
        cmp eax, [edx]
        jae pl_end
        push dword ptr [ebp+8]
        lea ecx, [eax+eax*2]
        lea ecx, [eax+ecx*2]
        mov edx, [ebx+%(hsmap)#x]
        add ecx, [edx+0x40]
        push ecx
        mov edx, [esp+12]
        mov eax, [esp+8]
        mov ecx, [edx+eax*8+8]
        add ecx, [ebp-8]
        add ecx, %(cdy)d
        push ecx
        mov ecx, [edx+eax*8+4]
        add ecx, [ebp-4]
        add ecx, %(cdx)d
        push ecx
        mov eax, [esp+24]
        call pdraw
        inc dword ptr [esp]
        jmp pl_loop
    pl_end:
        add esp, 12
    pl_done:
        add esp, 8
        pop edi
        pop ebx
        mov ecx, [esi+0xc]
        jmp %(resume)#x
    pdraw:
        push ebp
        mov ebp, esp
        push ebx
        push esi
        push edi
        mov esi, eax
        mov edi, [esi+0x1c]
        mov ecx, [edi+8]
        test ecx, ecx
        jz pd_done
        mov eax, [ebp+0x10]
        xor edx, edx
        mov ebx, %(period)d
        div ebx
        xor edx, edx
        div ecx
        mov eax, [edi+4]
        mov edx, [eax+edx*4]
        mov edi, edx
        mov eax, [esi+0x10]
        call %(exist)#x
        test al, al
        jz pd_done
        push dword ptr [ebp+0x14]
        mov edx, edi
        mov eax, [esi+0x10]
        call %(get)#x
        mov ecx, [ebp+0xc]
        add ecx, [esi+0x28]
        mov edx, [ebp+8]
        add edx, [esi+0x24]
        mov ebx, [eax]
        call dword ptr [ebx+0x84]
    pd_done:
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x10
    """ % {"exit": HB_EXIT, "resume": HB_RESUME, "both": FOUNTAIN_BIT | ARMS_BIT, "fbit": FOUNTAIN_BIT, "abit": ARMS_BIT, "foot": foot_va,
           "arms": arms_va, "arms4": arms_va + 4, "cdx": ANCHOR_CITY[0], "cdy": ANCHOR_CITY[1], "hsmap": AOWHSMAP, "hsset": AOWHSSET,
           "sc": SPELLCONTROL_OFF, "spell": GFX_SPELL, "getspell": GETSPELL, "getseq": GETIMAGESEQ, "cslot": CITY_SLOT, "aslot": ARMS_SLOT,
           "period": CITY_PERIOD, "exist": IMAGEEXIST, "get": LIBGET, "infx": INF_EXPORT, "pspell": PLAGUE_SPELL, "pslot": PLAGUE_SLOT}
    return asm_delta(src, va)


def build_d(va):
    """v4 hook D (TCity.MakeVisible @0x557AA908, ebx = city, esi = scene): replay the call, then a plagued city whose
    enchantment bits are all outside the overlay mask gets its overlay HS [city+0x60] made visible (VMT+0xF0, edx =
    scene) - exactly what the vanilla mask test does for enchanted cities; the vanilla test right after skips it
    (bits & mask == 0), so the overlay is never added twice."""
    src = """
        call %(callee)#x
        test byte ptr [ebx+0x5c], %(mask)d
        jnz d_out
        push esi
        mov esi, ebx
        call %(infx)#x
        pop esi
        test al, al
        jz d_out
        mov eax, [ebx+0x60]
        test eax, eax
        jz d_out
        mov edx, esi
        mov ecx, [eax]
        call dword ptr [ecx+0xf0]
    d_out:
        ret
    """ % {"callee": HD_CALLEE, "mask": OVERLAY_MASK_ALL, "infx": INF_EXPORT}
    return bytes(ks.asm(src, va)[0])


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


def layout():
    lit = delphi_literal("Arms Race"); lit_va = ZONE + 8
    a_va = ZONE + ((len(lit) + 15) & ~15)
    plit = delphi_literal(PLAGUE_LINE); plit_va = ZONE_END - 0x80 + 8                          # v4: fixed literal slot near the zone end
    cave_a = build_a(a_va, lit_va, plit_va); b_va = a_va + ((len(cave_a) + 15) & ~15)
    foot_va = arms_va = b_va + 0x100
    b_len = len(build_b(b_va, foot_va, arms_va))
    foot_va = b_va + ((b_len + 15) & ~15); foot = foot_table()
    arms_va = foot_va + ((len(foot) + 15) & ~15); arms = arms_table()
    cave_b = build_b(b_va, foot_va, arms_va); assert len(cave_b) == b_len
    zone = (lit + bytes(a_va - ZONE - len(lit)) + cave_a + bytes(b_va - a_va - len(cave_a)) + cave_b
            + bytes(foot_va - b_va - len(cave_b)) + foot + bytes(arms_va - foot_va - len(foot)) + arms)
    d_va = ZONE + ((len(zone) + 15) & ~15); cave_d = build_d(d_va)                              # v4
    zone += bytes(d_va - ZONE - len(zone)) + cave_d
    assert ZONE + len(zone) <= plit_va - 8, hex(ZONE + len(zone))
    zone += bytes(plit_va - 8 - ZONE - len(zone)) + plit
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, a_va, b_va, foot_va, arms_va, d_va


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    zone, a_va, b_va, foot_va, arms_va, d_va = layout()
    hooks = {HA_SITE: (HA_ORIG, b"\xe9" + struct.pack("<i", a_va - (HA_SITE + 5)) + b"\x90" * (len(HA_ORIG) - 5)),
             HB_SITE: (HB_ORIG, b"\xe9" + struct.pack("<i", b_va - (HB_SITE + 5)) + b"\x90" * (len(HB_ORIG) - 5)),
             HC_SITE: (HC_ORIG, HC_NEW),
             HD_SITE: (HD_ORIG, b"\xe8" + struct.pack("<i", d_va - (HD_SITE + 5)))}
    ex = d[INF_EXPORT - CODE_V2F:INF_EXPORT - CODE_V2F + 5]                                    # v4 dependency: the Plague export
    ex_ok = ex[0] == 0xE9 and 0x5582A000 <= INF_EXPORT + 5 + struct.unpack_from("<i", ex, 1)[0] < 0x5582C000
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(st <= r < st + len(o) for st, (o, _) in hooks.items())]
    states = {}
    for st, (orig, hook) in hooks.items():
        live = d[st - CODE_V2F:st - CODE_V2F + len(orig)]
        old = (len(live) >= 5 and live[0] in (0xE8, 0xE9) and ZONE <= st + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END
               and all(x == 0x90 for x in live[5:]))                                               # v4: an older build of ours (moved cave)
        states[st] = "vanilla" if live == orig else "ours" if live == hook else "ours(old)" if old else "OTHER"
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("hook A (ListEnhancementsInfo) %s | hook B (TCityOverlayHS.Show) %s | hook C (MakeVisible mask) %s | zone %s (%d B: literal @%#x, A @%#x, B @%#x, FOOT @%#x, ARMS @%#x) | relocs %s" % (
        states[HA_SITE], states[HB_SITE], states[HC_SITE], zstate, len(zone), ZONE, a_va, b_va, foot_va, arms_va, bad or "none"))
    print("ARMS anchors per size:", ARMS, "| FOOT:", FOOT, "| period %d ticks/frame, phase %d" % (CITY_PERIOD, TICK_PHASE))
    print("v4: hook D (MakeVisible call @%#x) %s | cave D @%#x | Plague export @%#x %s" % (HD_SITE, states[HD_SITE], d_va, INF_EXPORT,
          "present" if ex_ok else "MISSING (apply patch_blesseddew_v1.py v4 first)"))
    if bad or "OTHER" in states.values(): print("ABORT"); return 1
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[a_va - ZONE:foot_va - ZONE], a_va): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        print("  -- D")
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[d_va - ZONE:], d_va):
            print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
            if i.mnemonic == "ret": break
    if a.revert:
        out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        for st, (orig, _) in hooks.items(): out[st - CODE_V2F:st - CODE_V2F + len(orig)] = orig
        write_inplace(a.dll, bytes(out)); print("reverted (hooks -> vanilla, zone zeroed)"); return 0
    if all(s == "ours" for s in states.values()) and zstate == "ours": print("already applied"); return 0
    if a.apply and not ex_ok: print("ABORT: the Plague export is missing - apply patch_blesseddew_v1.py v4 first"); return 1
    if zstate == "DIFFERS": print("zone holds an older build (v1/v2) -> --apply re-syncs it in place (hooks A/B unchanged, hook C added); --revert then --apply is equivalent")
    out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for st, (_, hook) in hooks.items(): out[st - CODE_V2F:st - CODE_V2F + len(hook)] = hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
