#!/usr/bin/env python3
r"""
OIL SPRING (spell 372, Earth/Fire tier 1) - round 2 (2026-10-13): an OOZE-style area spell that coats 19 hexes with
black OIL; any unit standing in oil has FIRE WEAKNESS (combat only) until it moves off.  Dry-run only until applied.

Donor = Ooze (id 124 = 0x7C, CombatSpells.TOoze, SpellTypes class 0x0A = hail class, 19 strikes via the id-keyed
alias at 0x40B541): the clone is made by patch_dual_sphere_spells_v1.py (DONOR "TOoze": cell 0x557F5D94, Create
0x557F9590, site 0x557FA7AC; pfs_donor 134; tc_type 0x0A) + ALIAS 372 -> 0x7C in patch_tc_spell_alias_v1.py.

How Ooze mud works (RE 2026-10-13):
  TCAbRangedTE.Execute lands every strike; for [fx+0x14]==0x34 / [fx+0x34]==0xA the id switch @0x40C8D0 (alias cave;
  eax = alias(id)-0x74) sends 0x74 Great Hail to the 0x31006 map message and 0x7C Ooze to 0x40C922 (now the ooze-
  extinguish cave, resume 0x40C927): the hex's field is skipped for terrain [field+0x14] in {0,0xA,9,0xF,7} / overlay
  [field+0x15] in {2,0xB,8}, else `TEObject.Create([0x41275C] TCOozeHS)` + THSMap.PlaceHX(map, hs, x, y, 0).
  TCOozeHS (TSingleHS, size 0xC: +4 field) is a pure decal: ClassID 0x220109, GetOverlay 0xB, GetLevel 0x1A,
  Show 0x424190 = TImageSequenceList [AoWHSSet+0x94] seq 0x19/0x1A/0x1B (Release.hss list @0x293F00: TCOMBAT\MISC.ILB
  50-54 / 55-59 / 60-64 "OozeTile", 75x91, drawn at HXtoHP(x,y) - (16,48) - view offset, frame = self mod 5; ours: frame = (7*hx + 11*hy) mod n - v3.5 2026-10-14 (3hx+5hy made every hex of a column identical: 5hy = 0 mod 5),
  PlaceOnMap = THexagonSprite.PlaceOnMap + TMapField.UpdateTerrain.  UpdateTerrain (HSEPack 0x55607E9C) takes the
  first child whose GetOverlay >= 0 (THexagonSprite default 0xFE) -> [field+0x15] = 0xB = the mud: the MOVEMENT
  side reads [field+0x15] through the per-(terrain, overlay) passability table (AoWE.ListMovementGaps 0x5575C1B3 /
  TAIMoveControl.CalculateTransportGaps 0x5573E33C).  The decal lives until the combat map is freed.

Oil = a runtime CLONE of the TCOozeHS VMT (built once in TCPCK's BSS page slack at VMTCLONE, 0x150 bytes copied from
TCOozeHS's VMT-0x40..+0x110, self pointer fixed) with four slots replaced.  v3.2 (2026-10-14) ROOT CAUSE of the
per-strike "TCAbRangedTE" exceptions: the clone used to copy only VMT-0x40..+0xC0, but TCOozeHS has 68 slots
(+0..+0x10C; THexagonSprite's own table already ends at +0x108) - +0xC0 TSingleHS.Place, +0xC4 Remove, +0xC8 Loaded,
+0xCC MapFieldMsgProc, +0xD0/D4 CanMoveOn/Over, +0xE0/E4 Activate/Deactivate, ... +0x108 CanPlace, +0x10C PlaceHX
were NIL in the clone.  THSMap.PlaceHX -> THexagonSprite.MainPlace (VMT+0xB4, HSEPack 0x556068BC) starts with
`call [VMT+0xC0]` (0x556068D3) -> call 0 -> EAccessViolation on every landing, before the HS is on the map.
   +0x24 ClassID    -> 0x22010B (unused in TCPCK/AoWEPACK/HSEPack)
   +0x58 GetOverlay -> 0xFE (none): the field overlay is untouched -> NO movement penalty, UpdateTerrain is a no-op
   +0xA8 Show       -> draws spell 372's own image list [spell+0x2C] slot OIL_SLOT (the record's tag-0xC list, where the
                       parent paints the oil tile into DualDF.ILB) at HXtoHP(x,y) - (16,48) + (OIL_XOFF, OIL_YOFF)
   +0xAC PlaceOnMap -> THexagonSprite.PlaceOnMap, then the unit already standing on the hex gets the status
  AoWTCPCK.dll (zone 0x43D600-0x43DA00, PIC call/pop delta; VMT clone in BSS 0x46CDC0..0x46CEC0, zero-init page slack):
   land  jmp-hook 0x40C8D8 (`sub eax,8 / je 0x40C922`): id 372 (= eax 0x12C when the alias site keeps 372, see
         SITE_KEEP) takes the Ooze landing path WITHOUT the extinguish cave (replays `mov eax,[0x469420]`, jmps to
         0x40C927); 0x7C still -> 0x40C922; others -> 0x40C8DD.
   cls   call-hook 0x40CA6E (`xor ecx,ecx / mov dl,1 / mov eax,[0x41275C]`, reloc 0x40CA73 neutralised): for
         [fx+0x18]==372 returns the oil class (building the clone on first use), else TCOozeHS; redoes ecx/dl.
   cnt   call-hook 0x40B55F (Execute phase 0, the Ooze branch of the 0x40B541 alias: `mov eax,[ebp-4] / mov [eax+0x28],
         0x13`): 372 gets N_STRIKES (7 = one glob per hex of Great Hail's 7-hex pattern) instead of Ooze's 19 (v3.2).
         The pattern itself is already Great Hail's: the Repent cave 0x43CAA2 compares the RAW te id with 0x7C ->
         372 -> `[ebp-0x44] = 7` -> strike mod 7 indexes the 7-hex offset table [0x4693E0].
   sct   call-hook 0x40E300 (NextStrike hail case, right after the two Random(20)+6 landing offsets land in
         [ebp-0x2C]/[ebp-0x30]; `mov eax,[ebp-0x38] / add eax,[ebp-0x30]`): for 372 both offsets := 0x10 = the hex
         centre (what the Repent caves 0x43CAE0/0x43CB00 do for 206) so HPtoHX at the landing always resolves to the
         pattern hex - the oil area is exactly the 7 hexes (v3.2).  The add's flags survive the ret (vanilla `jno`).
   prv   call-hook 0x428280 (targeting preview 0x427EE4, after the 0x42827A alias: `cmp eax,0x1A / ja 0x42848B`):
         the alias maps 372 -> 0x7C -> index 0x14 -> Ooze's 19-hex highlight; for 372 (the fx object's [+0x38] id,
         re-fetched via 0x41D2E8) the index becomes 0x0C = Great Hail's 7-hex highlight (v3.2).
   tgt   call-hook 0x40E35D (NextStrike hail case: `mov eax,[eax+0x18] / sub eax,0x7C`, eax = te) - v3.1 2026-10-13
         ROOT CAUSE of the per-strike TE exceptions + "no effect": this te-id compare is NOT one of the alias sites,
         so a 372 strike took Great Hail's branch (0x40E372: [fx+0x2C] := the unit standing on the strike hex)
         instead of Ooze's ([fx+0x2C] := nil).  At the landing (0x40C32F) a strike with a unit target runs
         GetSpell(372).CreateCA (TOoze's slot = a mod cave into the base TCombatSpell.CreateCA with Ooze's ATK 0 /
         DMG 0 -> no usable CA -> AV at 0x40C4AA, one dialog per unit hex) and, when the unit survives, jumps to
         0x40CAF2 - skipping the kind dispatch, i.e. the oil placement.  Now 372 compares like Ooze: no target, no CA,
         every one of the 19 landings reaches the oil path (the unit on the hex is flagged by oil_place).
  AoWEPACK.dll (zone 0x55863000, PIC):
   reg   splices a vanilla `call RegisterAbility` (0x557BCD81): registers 0xB2 as a plain TDurationAbility NAMED
         "Fire Weakness", [+0x24]=4, [+0x28]=3 (combat-only mode: GetName appends "(combat only)", CombatDone removes it).
   gae   TCombatUnit.GetAbilityEnabled 0x55725004: asked for 0x51 FIRE WEAKNESS, answer yes when the unit has 0xB2 -
         the mod's damage-roll cave 0x5580FC00 asks the combat object's VMT+0x88 = this function, so the -3 applies.
   pom   AoWE.TUnitHS.PlaceOnMap 0x5578436C (every placement/move of a unit HS; MoveTo/PlaceHX both end here with
         [hs+4] = the NEW field): for ClassID 0x220104 (tactical unit HS): unit = [[hs+0x1C]+0x4C]; if the field owns a
         0x22010B oil HS -> Expand 0xB2 (unless the unit has 0xB2 or native 0x51); else if it has 0xB2 -> RemoveAbility;
         unit.Changed either way.
RANGE: the combat damage block is [spell+0x34] ATK, +0x35 DMG, +0x36 types word, +0x38 ?, +0x39 RANGE (Great Hail /
Fireball / Slow = 0x0C, Ooze = 0xFF unlimited) -> the pipeline entry 372 carries pokes=[(0x39, 1, 0x0C)] (long range).
Round-1 layout (Slow clone: AoWEPACK cca 0x557F89E0 / exec 0x557F884C, TCPCK aoe 0x40C63B) is recognised and
replaced: every site that still carries a round-1 hook into our zones is restored.  Backups *.bak_oilspring.
Dry run by default; --apply / --revert / --dis.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

SPELL_ID, ABIL_OIL, ABIL_FIREWEAK = 372, 0xB2, 0x51     # 0xB0 Martyr, 0xB1 Lionheart, 0xB2 Oil (2026-10-13)
ABIL_NAME = b"Fire Weakness"
OIL_CLASSID, UNITHS_CLASSID = 0x22010B, 0x220104
OIL_SLOT, OIL_XOFF, OIL_YOFF = 3, 0, 0                   # spell-record tag-0xC slot drawn as the tile; extra pixel offset
N_STRIKES, LAND_CENTRE = 7, 0x10                         # v3.2: one glob per hex of the 7-hex pattern, landing at the hex centre (Repent's 0xA+6)
PREVIEW_HAIL_IDX, PREVIEW_MAX, PREVIEW_DEFAULT, GETFXOBJ = 0x74 - 0x68, 0x1A, 0x42848B, 0x41D2E8   # 0x428280 switch: index = alias(id)-0x68
BAK_SUFFIX = ".bak_oilspring"
ks = Ks(KS_ARCH_X86, KS_MODE_32)

# ---------------------------------------------------------------- AoWEPACK.dll
E_DLL = game_file("AoWEPACK.dll"); E_BASE, E_CODE = 0x55700000, 0x55700C00
E_ZONE, E_ZONE_END = 0x55863000, 0x55863300
REGABIL, LSTRASG = 0x55750238, 0x55701150
DUR_CLASS, DUR_CREATE = 0x5571DD68, 0x55764CD4
REGISTRY, GETABIL, REMOVEABIL = 0x558E92E8, 0x557501C0, 0x5577F6EC
HPB_WORD20 = 0x557BB808                     # the word THighPrayerBlessingAbility's ctor stores at [abil+0x20]
E_SITES = {  # name: (va, original bytes, kind)
    "reg": (0x557BCD81, bytes.fromhex("e8b234f9ff"), "call"),        # call RegisterAbility (vanilla loop, ebx = control)
    "gae": (0x55725004, bytes.fromhex("8b484c85c9"), "jmp"),          # TCombatUnit.GetAbilityEnabled: mov ecx,[eax+0x4c] / test ecx,ecx
    "pom": (0x5578436C, bytes.fromhex("538bd88bc3"), "jmp"),          # TUnitHS.PlaceOnMap: push ebx / mov ebx,eax / mov eax,ebx
}
E_RETIRED = {  # round-1 sites (restored if they still carry a hook into our zone)
    "cca": (0x557F89E0, bytes.fromhex("8bc35f5e5b")),
    "exec": (0x557F884C, bytes.fromhex("8b474cba84000000")),
}
GAE_RESUME, POM_RESUME = 0x55725009, 0x55784371

# ---------------------------------------------------------------- AoWTCPCK.dll
T_DLL = game_file("AoWTCPCK.dll"); T_BASE, T_CODE = 0x400000, 0x400C00
T_ZONE, T_ZONE_END = 0x43D600, 0x43DA00    # 0x43D800..0x43DA00 verified zero + reloc-free 2026-10-13 (round 2 needs ~0x280)
VMTCLONE, VMT_LO, VMT_HI = 0x46CE00, 0x40, 0x110    # BSS page slack (vsize ends 0x46C0A1; AoO ring 0x46C100-0x46CD90): clone = VMT-0x40..+0x110 -> 0x46CDC0..0x46CF10 (v3.2: 68 slots, was +0xC0)
T_SITES = {
    "land": (0x40C8D8, bytes.fromhex("83e8087445"), "jmp"),           # sub eax,8 / je 0x40C922
    "cls":  (0x40CA6E, bytes.fromhex("33c9b201a15c274100"), "call"),  # xor ecx,ecx / mov dl,1 / mov eax,[0x41275C]
    "tgt":  (0x40E35D, bytes.fromhex("8b401883e87c"), "call"),        # NextStrike hail case: mov eax,[eax+0x18] / sub eax,0x7C (v3.1: 372 -> Ooze's nil-target branch)
    "cnt":  (0x40B55F, bytes.fromhex("8b45fcc7402813000000"), "call"),  # Execute phase 0 Ooze branch: mov eax,[ebp-4] / mov [eax+0x28],0x13 (v3.2: 372 -> N_STRIKES)
    "sct":  (0x40E300, bytes.fromhex("8b45c80345d0"), "call"),        # NextStrike hail case: mov eax,[ebp-0x38] / add eax,[ebp-0x30] (v3.2: centre; v3.4: the vanilla 6..25 offsets halved around the centre = 11..20 jitter)
    "prv":  (0x428280, bytes.fromhex("83f81a0f8702020000"), "call"),  # preview switch: cmp eax,0x1A / ja 0x42848B (v3.2: 372 -> Great Hail's 7-hex highlight)
    "ord":  (0x40E282, bytes.fromhex("99f77dbc6215a0f44000"), "call"),  # NextStrike hail case: cdq / idiv [ebp-0x44] / bound edx,[0x40F4A0] (reloc 0x40E288 neutralised): v3.4 372 -> scrambled pattern order
}
T_SITES["mud"] = (0x40C9B8, bytes.fromhex("0fbe40156683f80b"), "call")   # landing: movsx eax,[eax+0x15] / cmp ax,0xB (v3.7: 372 lands on ooze hexes too)
T_RETIRED = {"aoe": (0x40C63B, bytes.fromhex("8b45e08b40308b10ff522c"))}
T_RELOC_NEUTRALISE = [0x40CA73, 0x40E288]    # inside the cls hook bytes / the bound's absolute inside the ord hook bytes
LAND_OOZE, LAND_SKIP, LAND_RESUME = 0x40C922, 0x40C8DD, 0x40C927
OOZE_PRIO, PRIO_VA = 0x4242D4, 0x43D990     # TCOozeHS.GetShowPriority; our oil_prio cave (fixed: cls is assembled before it is placed)
MAPLIST, SPELLREG, OOZE_CELL, SETUNIT_SLOT, SETUNIT_VA = 0x469420, 0x46E8D0, 0x41275C, 0x46E858, 0x55725194
HXTOHP, GETSEQ, SEQFRAMES, SEQFRAMEIDX, LIBGET, HS_PLACEONMAP, GETSPELL = 0x4022BC, 0x4016E4, 0x4016CC, 0x4016DC, 0x4016F4, 0x401C5C, 0x4029B4


def asm_delta(src, va):
    """PIC delta idiom `call $D / pop R / sub R, $D` (R = eax, ebx, ebp, esi, edi): two-pass, every anchor patched."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("eax", "ebx", "ebp", "esi", "edi"): s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0]); n = 0
    for pop, sub in ((0x58, 0xE8), (0x5B, 0xEB), (0x5D, 0xED), (0x5E, 0xEE), (0x5F, 0xEF)):
        anchor = bytes([0xE8, 0, 0, 0, 0, pop]) + (b"\x2d" if pop == 0x58 else bytes([0x81, sub])) + b"\xff\xff\xff\x7f"
        k = b.find(anchor)
        while k >= 0:
            struct.pack_into("<I", b, k + len(anchor) - 4, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D"), "delta anchors: %d of %d" % (n, src.count("call $D"))
    return bytes(b)


def build_epack(d):
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = E_ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    out += struct.pack("<ii", -1, len(ABIL_NAME)); where["name"] = E_ZONE + len(out); out += ABIL_NAME + b"\0"
    word20 = struct.unpack_from("<H", d, HPB_WORD20 - E_CODE)[0]
    # reg: replay the vanilla RegisterAbility call, then register 0xB2 "Fire Weakness" = a plain TDurationAbility, mode 3
    place("reg", """
        call %(reg)#x
        push esi
        call $D
        pop esi
        sub esi, $D
        lea eax, [esi + %(cls)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(abil)d
        mov byte ptr [eax + 0x24], 4
        mov byte ptr [eax + 0x28], 3
        mov word ptr [eax + 0x20], %(w20)d
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % {"reg": REGABIL, "cls": DUR_CLASS, "create": DUR_CREATE, "abil": ABIL_OIL, "w20": word20, "name": where["name"], "lstrasg": LSTRASG})
    # gae: TCombatUnit.GetAbilityEnabled(eax = CU, edx = id): 0x51 is also true when the unit has 0xB2
    place("gae", """
        cmp edx, %(fw)d
        jne pass
        push eax
        push edx
        mov edx, %(oil)d
        call %(self)#x
        test al, al
        jz nothing
        pop edx
        pop eax
        mov al, 1
        ret
    nothing:
        pop edx
        pop eax
    pass:
        mov ecx, [eax + 0x4c]
        test ecx, ecx
        jmp %(resume)#x
    """ % {"fw": ABIL_FIREWEAK, "oil": ABIL_OIL, "self": E_SITES["gae"][0], "resume": GAE_RESUME})
    # pom: TUnitHS.PlaceOnMap(eax = hs) prologue - ebx = hs after the replay; set/clear the oil status from the new field
    place("pom", """
        push ebx
        mov ebx, eax
        mov eax, ebx
        mov edx, [eax]
        call dword ptr [edx + 0x24]
        cmp eax, %(unitcls)#x
        jne out
        mov eax, [ebx + 0x1c]
        test eax, eax
        jz out
        mov eax, [eax + 0x4c]
        test eax, eax
        jz out
        push esi
        push edi
        mov esi, eax
        mov eax, [ebx + 4]
        test eax, eax
        jz out2
        mov edx, %(oilcls)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        mov edi, eax
        mov eax, esi
        mov edx, %(oil)d
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test edi, edi
        jz leaving
        test al, al
        jnz out2
        mov eax, esi
        mov edx, %(fw)d
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jnz out2
        push ebp
        call $D
        pop ebp
        sub ebp, $D
        mov eax, [ebp + %(registry)#x]
        pop ebp
        mov eax, [eax]
        mov eax, [eax + 0x80]
        mov edx, %(oil)d
        call %(getabil)#x
        test eax, eax
        jz out2
        mov edx, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0xd0]
        jmp changed
    leaving:
        test al, al
        jz out2
        mov eax, esi
        mov edx, %(oil)d
        call %(removeabil)#x
    changed:
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x90]
    out2:
        pop edi
        pop esi
    out:
        mov eax, ebx
        jmp %(resume)#x
    """ % {"unitcls": UNITHS_CLASSID, "oilcls": OIL_CLASSID, "oil": ABIL_OIL, "fw": ABIL_FIREWEAK, "registry": REGISTRY,
           "getabil": GETABIL, "removeabil": REMOVEABIL, "resume": POM_RESUME})
    assert E_ZONE + len(out) <= E_ZONE_END, hex(E_ZONE + len(out))
    return bytes(out), where


def build_tcpck():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = T_ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    # land: eax = alias(id) - 0x74 (flags from that sub are dead here: the hail `je` already consumed them)
    place("land", """
        cmp eax, %(oilkey)#x
        je oil
        sub eax, 8
        je %(ooze)#x
        jmp %(skip)#x
    oil:
        call $D
        pop eax
        sub eax, $D
        mov eax, [eax + %(maplist)#x]
        jmp %(resume)#x
    """ % {"oilkey": SPELL_ID - 0x74, "ooze": LAND_OOZE, "skip": LAND_SKIP, "maplist": MAPLIST, "resume": LAND_RESUME})
    # classid / overlay for the clone (eax = self)
    place("oil_classid", "mov eax, %#x\n ret" % OIL_CLASSID)
    place("oil_overlay", "mov al, 0xfe\n ret")
    # PlaceOnMap(eax = self) -> al: inherited THexagonSprite.PlaceOnMap, then flag the unit already on the hex
    place("oil_place", """
        push ebx
        push esi
        push edi
        call $D
        pop ebx
        sub ebx, $D
        mov esi, eax
        call %(hsplace)#x
        mov eax, [esi + 4]
        test eax, eax
        jz out
        mov edx, %(unitcls)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz out
        mov eax, [eax + 0x1c]
        test eax, eax
        jz out
        mov edi, [eax + 0x4c]
        test edi, edi
        jz out
        mov eax, edi
        mov edx, %(oil)d
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jnz out
        mov eax, edi
        mov edx, %(fw)d
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jnz out
        mov esi, [ebx + %(setslot)#x]
        sub esi, %(setva)#x
        mov eax, [ebx + %(spellreg)#x]
        mov eax, [eax]
        mov eax, [eax + 0x80]
        mov edx, %(oil)d
        lea ecx, [esi + %(getabil)#x]
        call ecx
        test eax, eax
        jz out
        mov edx, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0xd0]
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx + 0x90]
    out:
        mov al, 1
        pop edi
        pop esi
        pop ebx
        ret
    """ % {"hsplace": HS_PLACEONMAP, "unitcls": UNITHS_CLASSID, "oil": ABIL_OIL, "fw": ABIL_FIREWEAK, "setslot": SETUNIT_SLOT,
           "setva": SETUNIT_VA, "spellreg": SPELLREG, "getabil": GETABIL})
    # Show(eax = self, edx = dx, ecx = dy, [ebp+8] = surface arg; ret 4): TCOozeHS.Show with the spell's own slot
    place("oil_show", """
        push ebp
        mov ebp, esp
        add esp, -0x1c
        push ebx
        push esi
        mov [ebp - 0xc], ecx
        mov [ebp - 8], edx
        mov [ebp - 4], eax
        call $D
        pop esi
        sub esi, $D
        lea eax, [ebp - 0x18]
        push eax
        lea ecx, [ebp - 0x14]
        mov eax, [ebp - 4]
        mov eax, [eax + 4]
        movsx edx, byte ptr [eax + 0x11]
        mov eax, [ebp - 4]
        mov eax, [eax + 4]
        movsx eax, byte ptr [eax + 0x10]
        call %(hxtohp)#x
        mov eax, [ebp - 0x14]
        sub eax, [ebp - 8]
        add eax, %(xoff)d
        mov [ebp - 8], eax
        mov eax, [ebp - 0x18]
        sub eax, [ebp - 0xc]
        add eax, %(yoff)d
        mov [ebp - 0xc], eax
        mov eax, [esi + %(spellreg)#x]
        mov eax, [eax]
        mov eax, [eax + 0x84]
        mov edx, %(id)d
        call %(getspell)#x
        test eax, eax
        jz fin
        mov eax, [eax + 0x2c]
        test eax, eax
        jz fin
        mov edx, %(slot)d
        call %(getseq)#x
        mov [ebp - 0x1c], eax
    again:
        cmp dword ptr [ebp - 0x1c], 0
        je fin
        mov eax, [ebp - 0x1c]
        call %(seqframes)#x
        test eax, eax
        jz nextseq
        mov ecx, eax
        mov eax, [ebp - 4]
        mov eax, [eax + 4]
        movsx edx, byte ptr [eax + 0x11]
        movsx eax, byte ptr [eax + 0x10]
        imul eax, eax, 7
        imul edx, edx, 11
        add eax, edx
        and eax, 0x7fffffff
        xor edx, edx
        div ecx
        mov eax, [ebp - 0x1c]
        call %(seqidx)#x
        mov [ebp - 0x10], eax
        cmp eax, -1
        je nextseq
        mov eax, [ebp + 8]
        push eax
        mov edx, [ebp - 0x10]
        mov eax, [ebp - 0x1c]
        mov eax, [eax + 0x10]
        call %(libget)#x
        mov ecx, [ebp - 0xc]
        mov edx, [ebp - 8]
        mov ebx, [eax]
        call dword ptr [ebx + 0x84]
    nextseq:
        mov eax, [ebp - 0x1c]
        mov eax, [eax + 0xc]
        mov [ebp - 0x1c], eax
        jmp again
    fin:
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 4
    """ % {"hxtohp": HXTOHP, "xoff": OIL_XOFF - 16, "yoff": OIL_YOFF - 48, "spellreg": SPELLREG, "id": SPELL_ID, "getspell": GETSPELL,
           "slot": OIL_SLOT, "getseq": GETSEQ, "seqframes": SEQFRAMES, "seqidx": SEQFRAMEIDX, "libget": LIBGET})
    # cls: called from 0x40CA6E with [ebp-0x20] = fx; returns eax = class, ecx = 0, dl = 1 (the replaced instructions)
    place("cls", """
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebp - 0x20]
        cmp dword ptr [eax + 0x18], %(id)d
        jne mud
        lea eax, [ebx + %(clone)#x]
        cmp dword ptr [eax - 0x40], 0
        jne done
        push esi
        push edi
        push ecx
        mov esi, [ebx + %(oozecell)#x]
        sub esi, %(lo)d
        lea edi, [ebx + %(clone)#x - %(lo)d]
        mov ecx, %(ndw)d
        .byte 0xf3, 0xa5
        lea eax, [ebx + %(clone)#x]
        mov [eax - 0x40], eax
        lea ecx, [ebx + %(classid)#x]
        mov [eax + 0x24], ecx
        lea ecx, [ebx + %(overlay)#x]
        mov [eax + 0x58], ecx
        lea ecx, [ebx + %(show)#x]
        mov [eax + 0xa8], ecx
        lea ecx, [ebx + %(placeon)#x]
        mov [eax + 0xac], ecx
        lea ecx, [ebx + %(prio)#x]
        mov [eax + 0x8c], ecx
        pop ecx
        pop edi
        pop esi
        jmp done
    mud:
        mov eax, [ebx + %(oozecell)#x]
    done:
        pop ebx
        xor ecx, ecx
        mov dl, 1
        ret
    """ % {"id": SPELL_ID, "clone": VMTCLONE, "oozecell": OOZE_CELL, "classid": where["oil_classid"], "overlay": where["oil_overlay"],
           "show": where["oil_show"], "placeon": where["oil_place"], "prio": PRIO_VA, "lo": VMT_LO, "ndw": (VMT_LO + VMT_HI) // 4})
    # tgt: NextStrike hail case, eax = te; replay `mov eax,[eax+0x18] / sub eax,0x7C` treating 372 as Ooze (ZF set ->
    # the strike's unit target [fx+0x2C] stays nil -> no CreateCA at the landing, the oil path always runs)
    place("tgt", """
        mov eax, [eax + 0x18]
        cmp eax, %(id)d
        je tgt_ooze
        cmp eax, 388
        je tgt_ooze
        cmp eax, 389
        jne keep
    tgt_ooze:
        mov eax, 0x7c
    keep:
        sub eax, 0x7c
        ret
    """ % {"id": SPELL_ID})
    # cnt: Execute phase 0, Ooze branch ([ebp-4] = te): replay `[te+0x28] = 0x13` (19 strikes) - N_STRIKES for 372
    place("cnt", """
        mov eax, [ebp - 4]
        cmp dword ptr [eax + 0x18], %(id)d
        je oilcnt
        mov dword ptr [eax + 0x28], 0x13
        ret
    oilcnt:
        mov dword ptr [eax + 0x28], %(n)d
        ret
    """ % {"id": SPELL_ID, "n": N_STRIKES})
    # sct: (2026-10-16) 208 Sanctify: both offsets pinned exactly to the hex centre (its rings must sit centred).
    # sct: NextStrike hail case ([ebp-4] = te): for 372 pin both landing offsets to the hex centre, then replay
    # `mov eax,[ebp-0x38] / add eax,[ebp-0x30]` (the add's flags feed the vanilla jno after the site)
    place("sct", """
        mov eax, [ebp - 4]
        cmp dword ptr [eax + 0x18], 208
        jne notsanct
        mov dword ptr [ebp - 0x2c], %(c)d
        mov dword ptr [ebp - 0x30], %(c)d
        jmp vanil
    notsanct:
        cmp dword ptr [eax + 0x18], %(id)d
        jne vanil
        mov eax, [ebp - 0x2c]
        sub eax, %(c)d
        sar eax, 1
        add eax, %(c)d
        mov [ebp - 0x2c], eax
        mov eax, [ebp - 0x30]
        sub eax, %(c)d
        sar eax, 1
        add eax, %(c)d
        mov [ebp - 0x30], eax
    vanil:
        mov eax, [ebp - 0x38]
        add eax, [ebp - 0x30]
        ret
    """ % {"id": SPELL_ID, "c": LAND_CENTRE})
    # prv: targeting preview switch, eax = alias(id) - 0x68 (0x14 for 372 -> 0x7C = Ooze's 19-hex case 1); for a 372
    # fx object (re-fetched like the vanilla code: [[ebp-4]+0x18] -> 0x41D2E8 -> obj, [obj+0x38] = spell id) use Great
    # Hail's index 0x0C (case 2 = the 7-hex highlight); then replay `cmp eax,0x1A / ja default`
    # ord (v3.4 2026-10-14, user: the glob pattern is too apparent): the hail case picks pattern hex [te+0x34] mod 7 in the
    # fixed table order; for 372 the index becomes (3*k + hx + hy) mod 7 - a permutation of 0..6 (3 is coprime with 7)
    # whose phase depends on the target hex, so the order differs from cast to cast and never repeats a hex.  The
    # vanilla `bound` range check is dropped (edx is < [ebp-0x44] by construction).  Deterministic (no RNG) -> MP-safe.
    place("ord", """
        cdq
        idiv dword ptr [ebp - 0x44]
        mov eax, [ebp - 4]
        cmp dword ptr [eax + 0x18], %(id)d
        jne odone
        movzx ecx, word ptr [eax + 0x20]
        movzx eax, word ptr [eax + 0x22]
        add ecx, eax
        lea eax, [edx + edx*2]
        add eax, ecx
        xor edx, edx
        mov ecx, 7
        div ecx
    odone:
        ret
    """ % {"id": SPELL_ID})
    # 2026-10-14 FIX: the default branch used to `ja` straight out of this CALLED cave, leaving its return address on the
    # stack -> the preview routine (TRangedPathHS.Show 0x427EE4) returned with ebx = a stack address -> crash in HSEPack's
    # draw loop 0x5560D68F (null entry) on hovering/clicking GROUND with any spell whose preview index is > 0x1A (Implosion 389)
    place("prv", """
        push eax
        mov eax, [ebp - 4]
        mov eax, [eax + 0x18]
        call %(getfx)#x
        cmp dword ptr [eax + 0x38], %(id)d
        pop eax
        jne chk
        mov eax, %(hail)d
    chk:
        cmp eax, %(max)d
        ja prv_dflt
        ret
    prv_dflt:
        add esp, 4
        jmp %(dflt)#x
    """ % {"id": SPELL_ID, "getfx": GETFXOBJ, "hail": PREVIEW_HAIL_IDX, "max": PREVIEW_MAX, "dflt": PREVIEW_DEFAULT})
    # oil_prio (v3.6 2026-11-19, user: ooze + oil on one hex flash): clone slot +0x8C TSingleHS.GetShowPriority.  TCOozeHS's
    # own override 0x4242D4 = 0x68000000 (level 0x1A << 26) + (hex y << 13) + hex x - the clone inherited it, so an ooze
    # and an oil decal on one hex had the SAME scene sort key and their order flipped.  Oil = that key + 0x1000 (above
    # every hex x of its row, below the next row): always drawn over the ooze, whatever landed first.  Draw-only.
    # Placed LAST so no older cave moves (Mend Walls chains to tgt @0x43D890).
    place("oil_prio", """
        call %(oozeprio)#x
        add eax, 0x1000
        ret
    """ % {"oozeprio": OOZE_PRIO})
    # mud (v3.7 2026-11-19, user: oil cast on an existing ooze hex did not show): the landing skips a field whose overlay
    # [field+0x15] is 0xB = Ooze's mud, so no oil decal was ever placed there.  Call-hook on `movsx eax,[eax+0x15] /
    # cmp ax,0xB` (eax = field, [ebp-0x20] = fx; the vanilla `je skip` follows): for 372 the mud test is replaced by
    # "the field already owns an oil decal" (ZF=1 = skip, so oil no longer stacks on oil either).
    place("mud", """
        mov ecx, [ebp - 0x20]
        cmp dword ptr [ecx + 0x18], %(id)d
        jne mud_van
        mov edx, %(oilcls)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jnz mud_skip
        test esp, esp
        ret
    mud_skip:
        cmp eax, eax
        ret
    mud_van:
        movsx eax, byte ptr [eax + 0x15]
        cmp ax, 0xb
        ret
    """ % {"id": SPELL_ID, "oilcls": OIL_CLASSID})
    assert where["oil_prio"] == PRIO_VA and where["tgt"] == 0x43D890, {k: hex(v) for k, v in where.items()}
    assert T_ZONE + len(out) <= T_ZONE_END, hex(T_ZONE + len(out))
    return bytes(out), where


# ---------------------------------------------------------------- PE helpers
def reloc_entries(d, base):
    """-> {va: file offset of the 16-bit entry} for every type-3 (or neutralised type-0 at a known site) entry."""
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, {}
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            out.setdefault(base + page + (e & 0xFFF), []).append((q, e >> 12))
        p += size
    return out


def hook(va, orig, kind, target):
    return (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", target - (va + 5)) + b"\x90" * (len(orig) - 5)


def site_state(live, orig, hk, zone, zone_end, va):
    if live == orig: return "vanilla"
    if live == hk: return "ours"
    if live[0] in (0xE8, 0xE9) and set(live[5:]) <= {0x90}:
        t = va + 5 + struct.unpack_from("<i", live, 1)[0]
        if zone <= t < zone_end: return "r1"
    return "OTHER"


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def plan(tag, d, code, base, zone, zone_end, blob, sites, retired, neutralise=()):
    rl = reloc_entries(d, base)
    probs = [hex(r) for r, es in rl.items() if zone <= r < zone_end and any(t == 3 for _, t in es)]
    states = {}
    for name, (va, orig, kind, target) in sites.items():
        live = d[va - code:va - code + len(orig)]
        states[name] = site_state(live, orig, hook(va, orig, kind, target), zone, zone_end, va)
        for r in range(va, va + len(orig)):
            for q, t in rl.get(r, []):
                if t == 3 and r not in neutralise: probs.append("reloc %x inside %s" % (r, name))
    for name, (va, orig) in retired.items():
        live = d[va - code:va - code + len(orig)]
        states[name] = site_state(live, orig, None, zone, zone_end, va)
    zl = d[zone - code:zone_end - code]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(blob)] == blob and not any(zl[len(blob):]) else "r1/other"
    if zstate == "r1/other" and not any(s == "r1" for s in states.values()) and not all(s in ("ours", "vanilla") for s in states.values()):
        probs.append("zone holds foreign code")
    out = bytearray(d); rev = bytearray(d)
    out[zone - code:zone_end - code] = bytes(zone_end - zone); out[zone - code:zone - code + len(blob)] = blob
    rev[zone - code:zone_end - code] = bytes(zone_end - zone)
    for name, (va, orig, kind, target) in sites.items():
        out[va - code:va - code + len(orig)] = hook(va, orig, kind, target); rev[va - code:va - code + len(orig)] = orig
    for name, (va, orig) in retired.items():                # 2026-10-15: only undo OUR round-1 hook - a retired site later
        if states[name] in ("vanilla", "OTHER"): continue   # re-used by another script (Slow's sid @0x557F884F) is left alone
        out[va - code:va - code + len(orig)] = orig; rev[va - code:va - code + len(orig)] = orig
    rstate = []
    for r in neutralise:
        es = rl.get(r, [])
        if not es: probs.append("no reloc entry at %x" % r); continue
        q, t = es[0]; rstate.append("%x:%s" % (r, {3: "type3", 0: "neutralised"}.get(t, "type%d" % t)))
        struct.pack_into("<H", out, q, (struct.unpack_from("<H", out, q)[0] & 0x0FFF))
        struct.pack_into("<H", rev, q, (struct.unpack_from("<H", rev, q)[0] & 0x0FFF) | 0x3000)
    print("%s sites %s | zone %s (%d B) | relocs %s | problems %s" % (tag, states, zstate, len(blob), rstate or "none", probs or "none"))
    applied = all(states[n] == "ours" for n in sites) and all(states[n] in ("vanilla", "OTHER") for n in retired) and zstate == "ours" and all(s.endswith("neutralised") for s in rstate)
    return applied, probs, bytes(out), bytes(rev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    de = open(E_DLL, "rb").read(); dt = open(T_DLL, "rb").read()
    eblob, ewhere = build_epack(de); tblob, twhere = build_tcpck()
    esites = {n: (va, orig, kind, ewhere[n]) for n, (va, orig, kind) in E_SITES.items()}
    tsites = {n: (va, orig, kind, twhere[n]) for n, (va, orig, kind) in T_SITES.items()}
    print("AoWEPACK caves", {k: hex(v) for k, v in ewhere.items()}); print("AoWTCPCK caves", {k: hex(v) for k, v in twhere.items()}, "VMT clone", hex(VMTCLONE))
    ea, ep, eout, erev = plan("AoWEPACK", de, E_CODE, E_BASE, E_ZONE, E_ZONE_END, eblob, esites, E_RETIRED)
    ta, tp, tout, trev = plan("AoWTCPCK", dt, T_CODE, T_BASE, T_ZONE, T_ZONE_END, tblob, tsites, T_RETIRED, T_RELOC_NEUTRALISE)
    if a.dis:
        import capstone
        cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for tag, blob, zone, start in (("AoWEPACK", eblob, E_ZONE, ewhere["reg"]), ("AoWTCPCK", tblob, T_ZONE, T_ZONE)):
            print("---", tag, "zone")
            for i in cs.disasm(blob[start - zone:], start): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if ep or tp: print("ABORT"); return 1
    if a.revert:
        write_inplace(E_DLL, erev); write_inplace(T_DLL, trev); print("reverted both (sites restored, zones zeroed, reloc restored)"); return 0
    if ea and ta: print("already applied"); return 0
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for path, data in ((E_DLL, eout), (T_DLL, tout)):
        bak = bak_path(path, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
        write_inplace(path, data); assert open(path, "rb").read() == data
    print("Written and verified (both DLLs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
