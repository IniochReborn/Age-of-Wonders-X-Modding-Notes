r"""
BUILD BRIDGE construct option v2 (2026-10-18).  AoWEPACK.dll only.  In-place upgrade of patch_build_bridge_v1.py.

v2 FIX (user test of v1: "it consumes the builder AND the transport, turns the water hex into GRASS, and on completion
it simply builds a TOWER"): one root cause.  The site is a TILTerrainMO; its placement asks GetValidTerrainType
(HSEPack 0x55618780), which keeps the hex terrain only if TTower VMT +0x128 ValidTerrainType (TStructure 0x5575EC44)
accepts it -- a tower rejects water/ice/lava, so a land type is FORCED (ForceTerrainType / first valid resource
terrain) into [mo+0x18], and TMapField.UpdateMapField rebuilds the field terrain from its MOs -> the hex turns to
land.  TArmy.Changed (called by TConstructStructureTE.Execute right after) then validates the boat army on land and
kills it (engineer + transport), and at completion is_site (TTower on a WET hex) is false -> vanilla BuildingDone
finishes a plain tower.  (Vanilla Construct does NOT consume the builder: Execute only calls army VMT+0x1AC
TArmy.Changed.)  v2 adds VT = TTower VMT +0x128 -> vt_cave: a wet terrain (0/6/9/10/13) is VALID for a tower while
our placement flag is set or while the tower is under construction ([+0x24] builder != 0xFF, i.e. a bridge site --
also after a reload: TILTerrainMO.Loaded re-asks it after ReadWrite has restored +0x24); everything else -> the
original.  The hex keeps its water/ice/lava, the army is untouched, is_site holds and the bridge is placed.


User: new construct option "Build Bridge": 50 gold, 3 turns; only on a hex where a bridge could be placed (water or
lava - plus ICE, which becomes WATER under the bridge - with land on two opposite neighbours); the engineer will be in
a boat; on completion any unit for which the hex is no longer valid (boats) is moved to a valid hex; a "building"
animation shows on the hex while it is built.

RE (all AoWEPACK unless noted):
  Construct = ability 0x7D, TConstructAbility [+0x28] = TConstructionControlList.  Controls (VMT +0x4C GetInfo(self,
  edx=army, ecx=&name; [ebp+8]=&days, [ebp+0xC]=&cost) / +0x50 CanConstruct(self, edx=army, ecx=&err) / +0x54
  Construct / +0x58 ID / +0x5C ValidateLocation / +0x60 StructureResource): 1 Rebuild, 2 Roads, 3 Tower, 4 Shipyard.
  The exe's TConstructDlg (0x43169C) lists EVERY registered control (name/cost/turns from GetInfo) and its
  ConstructBtnClick (0x431920) calls CanConstruct -> Construct, else shows the error string -> a newly registered
  control appears in the dialog with no exe change.  TStructureConstructionControl.Construct 0x55762230 posts a
  TConstructStructureTE {+0x10 army id, +0x14 player, +0x18 control ID} (MP token); TConstructStructureTE.Execute
  0x55761E40 (all clients): control = FindID, CanConstruct again, res = StructureResource, ClearTerrain on the
  footprint, res.VMT+0x68 CreateAndPlace @0x55761FA3, GetInfo -> struct.VMT+0x1A4 ExecuteBuild(army, days)
  ([+0x25] days, [+0x24] builder), gold -= cost.  TStructure.NewTurn (via TPlayerStructure.NewTurn) decrements
  [+0x25] on the builder's turns and calls VMT+0x19C BuildingDone at 0.
  Bridges = HxBridge.THexagonBridge (road family, TAbstractRoad), one resource per wet terrain in Release.hss
  (class 0x2087B: terrain 0/6/9/10/13, overlay 5), registered in the road control [AoWHSSet+0x1C];
  TAoWHSMap.PlaceTerrain 0x55778EEC with overlay 5 places one through that control (same path the raise-terrain
  revert uses), THexagonBridge.CanPlace = road CanPlace + DirectionValid (some opposite neighbour pair is AoWE.Land:
  not 0/6/9/10/13).  TAbstractRoad.ChangeTerrain swaps the bridge resource when the hex terrain changes (ice->water).
  TArmyHS.PlaceEx 0x55791F58 (dl=x, cl=y; push level, push flags 2|4) spirals the army to the nearest empty valid
  hex (TArmy.CanPlace = all units ValidTerrain) and moves it there (VMT+0x10C MoveTo).

DESIGN - the 3-turn build is carried by a TTower placed on the wet hex as a "bridge site" (structures already save,
  count down, show the construction state and run BuildingDone; no new save data needed):
  * a 5th control "Build %s"/Bridge (ID 5, cost 50, days 3) = a runtime VMT clone of TTowerConstructionControl in
    BSS (0x558FAC50..0x558FACF4) with own GetInfo / ID / ValidateLocation and the base (non-surface-only)
    CanConstruct, registered after the tower control in Tower.RegisterTower (site REG 0x557C39F9).
  * ValidateLocation: hex terrain in {0 water, 6 ice, 9 lava, 10 UG water, 13 UG ice}, no road/bridge overlay
    (4/5), no structure (same FindNoneTransparentHS check as the vanilla one), field owner none/own, and the
    DirectionValid rule (opposite land neighbours on some axis); else "Cannot build on current location".
  * EXE 0x55761FA1: while TConstructStructureTE.Execute places the structure for OUR control, flag G_FLAG is set;
    CPL (TStructure.CanPlace entry 0x5575ECC8) answers TRUE and PHX (TStructure.PlaceHX entry 0x5575ED10) goes
    straight to TILTerrainMO.PlaceHX (no pad, no terrain-slot check) only while that flag is set -> the tower lands
    on water/ice/lava; nothing else changes (editor/other placements never see the flag).
  * "bridge site" = a TTower whose hex terrain is wet (vanilla towers can never stand on water).
  * SHW 0x55760637 (TStructureResource.Show, sequence fetch): for a site, skip the first sequence of the slot and draw
    its chained sub-sequence only = the STR_BLDG.ILB construction CRANE animation (tower slot 0x19 = stub + crane),
    i.e. the same building animation every construction/rebuild shows, without the tower stub.
  * TTower VMT +0x19C BuildingDone -> BD: a site keeps "building" with 0 days (no "Tower built" event); TTower VMT
    +0x178 NewTurn -> NT: after the vanilla NewTurn, a site with 0 days on its builder's turn is CONVERTED:
      - final terrain = water for ice (UG ice -> UG water), else unchanged; re-check DirectionValid;
      - the army on the hex, if TArmy.ValidTerrain(final terrain, overlay 5 = bridge) fails, is PlaceEx'ed to the
        nearest valid empty hex (flags 2|4); if that fails or the direction rule fails -> keep the site, retry next
        turn (nothing lost);
      - the tower is destroyed (VMT-4 Destroy(1): MainRemove/Deactivate/StructureDestroyed; the broadcast that
        delivered NewTurn iterates its child list downward, so deleting the current child is safe, and nothing
        touches self after NT returns);
      - PlaceTerrain(overlay 5, current terrain) places the bridge; for ice, ChangeTerrain(map VMT+0xD0) then turns
        the hex to water and the bridge swaps to the water bridge resource.
    All of it runs inside the MP-synchronised turn processing / TE (map.Random is used by PlaceTerrain/ChangeTerrain
    exactly as in the vanilla raise-terrain revert).
  The AI never uses construct controls (no AoWEPACK/exe AI path calls them) -> AI ignores Build Bridge.

Zone AoWEPACK 0x5581B000..0x5581E000 (zero, reloc-free).  BSS 0x558FAC50..0x558FACFC (Wall of Flames' clone ends
0x558FAC50, Sanctify's clone starts 0x558FAD00).  All caves PIC (delta via call/pop; rel32 calls).  Sites are
reloc-free; the two TTower VMT slots carry relocs (in-image values -> rebased correctly).
Dry-run default; --apply / --revert (exact: vanilla site bytes + VMT values, zone zeroed) / --dis / --dll <copy>.
Backup <game>\backup\AoWEPACK.dll.bak_bridge.  No other script hooks these sites (all vanilla on 2026-10-18).
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581B000, 0x5581E000

# ---- addresses (AoWEPACK, preferred base) ----
C = dict(
    MAPVAR=0x558FA040,                      # AoWE.AoWHSMap variable
    TOWERCTL_VMT=0x557C352C, TTOWER_VMT=0x557C31A8,
    G_CLONE=0x558FAC50, G_VMT=0x558FAC90, G_FLAG=0x558FACF8,
    RCC=0x55771408, TEOCREATE=0x55703064, SCC_CAN=0x557621EC, ILT_PLACEHX=0x55703584,
    PS_NEWTURN=0x55760A70, PS_BDONE=0x557608F4,
    ARMY_VALIDTERR=0x5578DD64, ARMYHS_PLACEEX=0x55791F58, PLACETERRAIN=0x55778EEC,
    GETLOC=0x5577ED94, GETMAPLEVEL=0x557020EC, LVL_GETFIELD=0x557020DC, CENTERHN=0x55702694, LAND=0x5575AEA4,
    FINDNTHS=0x55702004, STRUCT_CLASSREF=0x55713BD8, FIELD_OWNER=0x55771C98,
    LOADRES=0x55701210, TRANSL=0x557249FC, FORMAT=0x557015E4, LSTRASG=0x55701150, LSTRARRCLR=0x55701148,
    LSTRCLR=0x55701140,
    RSTR_BRIDGE=0x55706984, RSTR_BUILDX=0x5570772C, RSTR_CANTBUILD=0x55707744,
    CPL_RESUME=0x5575ECCD, PHX_RESUME=0x5575ED15,
    TS_VALIDTT=0x5575EC44,                  # TStructure.ValidTerrainType (v2)
)
COST, DAYS, CTRL_ID = 50, 3, 5
CLONE_DW = 0xA4 // 4                        # tower-control VMT-0x40 .. +0x64 (slots end +0x60, name follows)

SITES = {   # name: (va, vanilla bytes)
    "REG": (0x557C39F9, bytes.fromhex("e80adafaff")),          # call TConstructAbility.RegisterConstructionControl
    "EXE": (0x55761FA1, bytes.fromhex("8b30ff5668")),          # mov esi,[eax] / call [esi+68h]   (CreateAndPlace)
    "CPL": (0x5575ECC8, bytes.fromhex("558bec5156")),          # TStructure.CanPlace entry
    "PHX": (0x5575ED10, bytes.fromhex("558bec5153")),          # TStructure.PlaceHX entry
    "SHW": (0x55760637, bytes.fromhex("8b34b885f6")),          # TStructureResource.Show: mov esi,[eax+edi*4] / test esi,esi
}
VMTS = {    # name: (slot va, vanilla value)
    "NT": (0x557C31A8 + 0x178, 0x55760A70),    # TTower NewTurn      (TPlayerStructure.NewTurn)
    "BD": (0x557C31A8 + 0x19C, 0x557608F4),    # TTower BuildingDone (TPlayerStructure.BuildingDone)
    "VT": (0x557C31A8 + 0x128, 0x5575EC44),    # TTower ValidTerrainType (TStructure.ValidTerrainType)   [v2]
}

ASM = r"""
; ================= REG: register the Build Bridge control after the tower control =================
reg_cave:
    push eax                              ; ability
    call {RCC}                            ; original: RegisterConstructionControl(ability, towerctl)
    pop eax
    push ebx
    push esi
    push edi
    push eax
    call reg_d
reg_d:
    pop ebx
    sub ebx, reg_d_va
    lea esi, [ebx + {TOWERCTL_VMT} - 0x40]
    lea edi, [ebx + {G_CLONE}]
    mov ecx, {CLONE_DW}
    cld
    .byte 0xf3, 0xa5                      ; rep movsd
    lea eax, [ebx + {G_VMT}]
    mov [ebx + {G_VMT} - 0x40], eax       ; self ptr
    lea eax, [ebx + gi_cave]
    mov [ebx + {G_VMT} + 0x4C], eax       ; GetInfo
    lea eax, [ebx + {SCC_CAN}]
    mov [ebx + {G_VMT} + 0x50], eax       ; CanConstruct = TStructureConstructionControl.CanConstruct
    lea eax, [ebx + id_cave]
    mov [ebx + {G_VMT} + 0x58], eax       ; ID
    lea eax, [ebx + vl_cave]
    mov [ebx + {G_VMT} + 0x5C], eax       ; ValidateLocation
    xor ecx, ecx
    mov dl, 1
    lea eax, [ebx + {G_VMT}]
    call {TEOCREATE}                      ; TEObject.Create(our class)
    mov edx, eax
    pop eax                               ; ability
    call {RCC}
    pop edi
    pop esi
    pop ebx
    ret

; ================= EXE: flag the placement of OUR site in TConstructStructureTE.Execute =================
exe_cave:
    push ebx
    call exe_d
exe_d:
    pop ebx
    sub ebx, exe_d_va
    push eax
    mov eax, [ebp - 0x0C]                 ; Execute's control
    mov eax, [eax]
    sub eax, ebx
    cmp eax, {G_VMT}
    pop eax
    jne exe_nf
    mov byte ptr [ebx + {G_FLAG}], 1
exe_nf:
    push dword ptr [esp + 0x0C]           ; re-push the two stack args
    push dword ptr [esp + 0x0C]
    mov esi, [eax]
    call dword ptr [esi + 0x68]           ; res.CreateAndPlace
    mov byte ptr [ebx + {G_FLAG}], 0
    pop ebx
    ret 8

; ================= CPL / PHX: no pad / terrain check while our site is being placed =================
cpl_cave:
    push eax
    call cpl_d
cpl_d:
    pop eax
    sub eax, cpl_d_va
    cmp byte ptr [eax + {G_FLAG}], 0
    pop eax
    je cpl_orig
    mov al, 1
    ret 8
cpl_orig:
    push ebp
    mov ebp, esp
    push ecx
    push esi
    jmp {CPL_RESUME}

phx_cave:
    push eax
    call phx_d
phx_d:
    pop eax
    sub eax, phx_d_va
    cmp byte ptr [eax + {G_FLAG}], 0
    pop eax
    je phx_orig
    jmp {ILT_PLACEHX}
phx_orig:
    push ebp
    mov ebp, esp
    push ecx
    push ebx
    jmp {PHX_RESUME}

; ================= SHW: a site draws only the crane sub-sequence =================
shw_cave:
    mov esi, [eax + edi*4]
    test esi, esi
    jz shw_ret
    push eax
    mov eax, ebx
    call is_site
    test al, al
    pop eax
    jz shw_t
    cmp dword ptr [esi + 0x0C], 0
    je shw_t
    mov esi, [esi + 0x0C]
shw_t:
    test esi, esi
shw_ret:
    ret

; ================= BD: a site stays "building" with 0 days =================
bd_cave:
    push eax
    call is_site
    test al, al
    pop eax
    jz bd_orig
    mov byte ptr [eax + 0x25], 0
    ret
bd_orig:
    jmp {PS_BDONE}

; ================= NT: convert a finished site on its builder's turn =================
nt_cave:
    push ebx
    push esi
    mov esi, eax
    mov ebx, edx
    call {PS_NEWTURN}                     ; eax = self, dl = player
    mov eax, esi
    call is_site
    test al, al
    jz nt_done
    cmp bl, byte ptr [esi + 0x24]
    jne nt_done
    cmp byte ptr [esi + 0x25], 0
    jne nt_done
    mov eax, esi
    call convert
nt_done:
    pop esi
    pop ebx
    ret

; ----- is_site(eax = structure) -> al; preserves everything else -----
is_site:
    push ecx
    push edx
    call is_d
is_d:
    pop ecx
    sub ecx, is_d_va
    mov edx, [eax]
    sub edx, ecx
    cmp edx, {TTOWER_VMT}
    jne is_no
    mov edx, [eax + 4]
    test edx, edx
    jz is_no
    mov dl, byte ptr [edx + 0x14]
    call is_wet
    jmp is_out
is_no:
    xor eax, eax
    jmp is_out2
is_out:
    movzx eax, al
is_out2:
    pop edx
    pop ecx
    ret

; ----- is_wet(dl = terrain) -> al -----
is_wet:
    cmp dl, 0
    je wet_y
    cmp dl, 6
    je wet_y
    cmp dl, 9
    je wet_y
    cmp dl, 10
    je wet_y
    cmp dl, 13
    je wet_y
    xor eax, eax
    ret
wet_y:
    mov eax, 1
    ret

; ----- convert(eax = site tower) -----
; frame: [ebp-1] x  [ebp-2] y  [ebp-3] level  [ebp-4] terrain  [ebp-5] final terrain
convert:
    push ebp
    mov ebp, esp
    sub esp, 0x10
    push ebx
    push esi
    push edi
    mov esi, eax
    mov edi, [esi + 4]                    ; field
    mov al, byte ptr [edi + 0x10]
    mov byte ptr [ebp - 1], al
    mov al, byte ptr [edi + 0x11]
    mov byte ptr [ebp - 2], al
    mov al, byte ptr [edi + 0x12]
    mov byte ptr [ebp - 3], al
    mov al, byte ptr [edi + 0x14]
    mov byte ptr [ebp - 4], al
    cmp al, 6
    jne cv_n13
    xor al, al
cv_n13:
    cmp al, 13
    jne cv_tf
    mov al, 10
cv_tf:
    mov byte ptr [ebp - 5], al
    ; direction rule still holds?
    movsx eax, byte ptr [ebp - 1]
    movsx edx, byte ptr [ebp - 2]
    movsx ecx, byte ptr [ebp - 3]
    call dirok
    test al, al
    jz cv_out                             ; retry next turn
    ; army on the hex that cannot stay on a bridge -> push it out first
    mov eax, edi
    mov edx, 0x20217
    mov ecx, [eax]
    call dword ptr [ecx + 0x80]
    test eax, eax
    jz cv_place
    mov ebx, eax                          ; TArmyHS
    mov eax, [ebx + 0x1C]
    mov dl, byte ptr [ebp - 5]
    mov cl, 5
    call {ARMY_VALIDTERR}
    test al, al
    jnz cv_place
    movsx eax, byte ptr [ebp - 3]
    push eax                              ; level
    push 6                                ; flags: spiral beyond ring 0 + own-domain fields
    mov dl, byte ptr [ebp - 1]
    mov cl, byte ptr [ebp - 2]
    mov eax, ebx
    call {ARMYHS_PLACEEX}
    test al, al
    jz cv_out                             ; nowhere to go -> keep the site, retry next turn
cv_place:
    ; remove the site
    mov eax, esi
    mov dl, 1
    mov ecx, [eax]
    call dword ptr [ecx - 4]
    ; bridge on the current terrain
    call cv_d
cv_d:
    pop ebx
    sub ebx, cv_d_va
    movsx eax, byte ptr [ebp - 3]
    push eax                              ; level
    movsx eax, byte ptr [ebp - 4]
    push eax                              ; terrain
    push 5                                ; overlay = bridge
    mov dl, byte ptr [ebp - 1]
    mov cl, byte ptr [ebp - 2]
    mov eax, [ebx + {MAPVAR}]
    call {PLACETERRAIN}
    ; ice -> water underneath
    mov al, byte ptr [ebp - 4]
    cmp al, byte ptr [ebp - 5]
    je cv_out
    movsx eax, byte ptr [ebp - 2]
    push eax                              ; y
    movsx eax, byte ptr [ebp - 3]
    push eax                              ; level
    push 0                                ; radius
    movsx eax, byte ptr [ebp - 5]
    push eax                              ; terrain
    movsx ecx, byte ptr [ebp - 1]         ; x
    xor edx, edx
    mov eax, [ebx + {MAPVAR}]
    mov esi, [eax]
    call dword ptr [esi + 0xD0]           ; TAoWHSMap.ChangeTerrain
cv_out:
    pop edi
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret

; ----- dirok(eax = x, edx = y, ecx = level) -> al : some opposite neighbour pair is land -----
dirok:
    push ebp
    mov ebp, esp
    sub esp, 0x20
    push ebx
    push esi
    push edi
    mov [ebp - 4], eax
    mov [ebp - 8], edx
    call dk_d
dk_d:
    pop ebx
    sub ebx, dk_d_va
    mov eax, [ebx + {MAPVAR}]
    mov eax, [eax + 0x10]
    mov edx, ecx
    call {GETMAPLEVEL}
    mov esi, eax                          ; TMapLevel
    xor edi, edi
dk_lp:
    lea eax, [edi + 1]
    call dk_land
    test al, al
    jz dk_nx
    lea eax, [edi + 4]
    call dk_land
    test al, al
    jnz dk_yes
dk_nx:
    inc edi
    cmp edi, 3
    jl dk_lp
    xor eax, eax
    jmp dk_out
dk_yes:
    mov eax, 1
dk_out:
    pop edi
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret
dk_land:                                  ; eax = HN index (1..6) -> al
    lea edx, [ebp - 0x0C]
    push edx                              ; &X
    lea edx, [ebp - 0x10]
    push edx                              ; &Y
    mov ecx, eax
    mov edx, [ebp - 8]
    mov eax, [ebp - 4]
    call {CENTERHN}
    mov eax, [ebp - 0x0C]
    test eax, eax
    jl dk_lno
    cmp eax, [esi + 0x0C]
    jge dk_lno
    mov ecx, [ebp - 0x10]
    test ecx, ecx
    jl dk_lno
    cmp ecx, [esi + 0x10]
    jge dk_lno
    mov edx, eax
    mov eax, esi
    call {LVL_GETFIELD}
    mov al, byte ptr [eax + 0x14]
    call {LAND}
    ret
dk_lno:
    xor eax, eax
    ret

; ================= control methods =================
id_cave:
    mov eax, {CTRL_ID}
    ret

; GetInfo(eax=self, edx=army, ecx=&name; [ebp+8]=&days, [ebp+0xC]=&cost) -> "Build Bridge", 50, 3
gi_cave:
    push ebp
    mov ebp, esp
    sub esp, 0x20
    push ebx
    push esi
    mov esi, ecx
    xor eax, eax
    mov [ebp - 4], eax
    mov [ebp - 8], eax
    mov [ebp - 0x0C], eax
    mov [ebp - 0x10], eax
    mov [ebp - 0x1C], eax
    call gi_d
gi_d:
    pop ebx
    sub ebx, gi_d_va
    lea edx, [ebp - 4]
    lea eax, [ebx + {RSTR_BRIDGE}]
    call {LOADRES}
    mov eax, [ebp - 4]
    lea edx, [ebp - 8]
    call {TRANSL}
    mov eax, [ebp - 8]
    mov [ebp - 0x18], eax                 ; TVarRec.VAnsiString
    mov byte ptr [ebp - 0x14], 0x0B       ; vtAnsiString
    lea edx, [ebp - 0x0C]
    lea eax, [ebx + {RSTR_BUILDX}]
    call {LOADRES}
    mov eax, [ebp - 0x0C]
    lea edx, [ebp - 0x10]
    call {TRANSL}
    lea eax, [ebp - 0x1C]
    push eax                              ; &result
    lea edx, [ebp - 0x18]
    xor ecx, ecx
    mov eax, [ebp - 0x10]
    call {FORMAT}
    mov edx, [ebp - 0x1C]
    mov eax, esi
    call {LSTRASG}
    mov eax, [ebp + 0x0C]
    mov dword ptr [eax], {COST}
    mov eax, [ebp + 8]
    mov dword ptr [eax], {DAYS}
    lea eax, [ebp - 0x1C]
    call {LSTRCLR}
    lea eax, [ebp - 0x10]
    mov edx, 4
    call {LSTRARRCLR}
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret 8

; ValidateLocation(eax=self, edx=army, ecx=&err) -> al
; frame: [ebp-4] &err  [ebp-5] x  [ebp-6] y  [ebp-7] level  [ebp-0xC] TMapLevel  [ebp-0x10]/[ebp-0x14] strings
vl_cave:
    push ebp
    mov ebp, esp
    sub esp, 0x20
    push ebx
    push esi
    push edi
    mov [ebp - 4], ecx
    mov esi, edx
    lea eax, [ebp - 7]
    push eax
    lea ecx, [ebp - 6]
    lea edx, [ebp - 5]
    mov eax, esi
    call {GETLOC}
    call vl_d
vl_d:
    pop ebx
    sub ebx, vl_d_va
    mov eax, [ebx + {MAPVAR}]
    mov eax, [eax + 0x10]
    movsx edx, byte ptr [ebp - 7]
    call {GETMAPLEVEL}
    mov [ebp - 0x0C], eax
    movsx edx, byte ptr [ebp - 5]
    movsx ecx, byte ptr [ebp - 6]
    call {LVL_GETFIELD}
    mov edi, eax                          ; field
    mov dl, byte ptr [edi + 0x14]
    call is_wet
    test al, al
    jz vl_fail
    mov al, byte ptr [edi + 0x15]
    cmp al, 4
    je vl_fail
    cmp al, 5
    je vl_fail
    mov edx, [ebx + {STRUCT_CLASSREF}]
    mov eax, edi
    call {FINDNTHS}
    test eax, eax
    jnz vl_fail
    mov eax, edi
    call {FIELD_OWNER}
    cmp al, 0xFF
    je vl_own
    cmp al, byte ptr [esi + 0x24]
    jne vl_fail
vl_own:
    movsx eax, byte ptr [ebp - 5]
    movsx edx, byte ptr [ebp - 6]
    movsx ecx, byte ptr [ebp - 7]
    call dirok
    test al, al
    jz vl_fail
    mov eax, 1
    jmp vl_out
vl_fail:
    xor eax, eax
    mov [ebp - 0x10], eax
    mov [ebp - 0x14], eax
    lea edx, [ebp - 0x10]
    lea eax, [ebx + {RSTR_CANTBUILD}]
    call {LOADRES}
    mov eax, [ebp - 0x10]
    lea edx, [ebp - 0x14]
    call {TRANSL}
    mov edx, [ebp - 0x14]
    mov eax, [ebp - 4]
    call {LSTRASG}
    lea eax, [ebp - 0x14]
    mov edx, 2
    call {LSTRARRCLR}
    xor eax, eax
vl_out:
    pop edi
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret
; ================= VT (v2): a wet hex stays valid for OUR tower site =================
; ValidTerrainType(eax = self, edx = terrain) -> al
vt_cave:
    push ecx
    push eax
    call is_wet                           ; dl = terrain -> al (only eax touched)
    test al, al
    pop eax
    jz vt_orig
    call vt_d
vt_d:
    pop ecx
    sub ecx, vt_d_va
    cmp byte ptr [ecx + {G_FLAG}], 0
    jne vt_yes                            ; our TE is placing the site right now
    cmp byte ptr [eax + 0x24], 0xFF
    je vt_orig                            ; not under construction -> vanilla rule
vt_yes:
    pop ecx
    mov eax, 1
    ret
vt_orig:
    pop ecx
    jmp {TS_VALIDTT}
"""

CHUNKS = ("reg_cave", "exe_cave", "cpl_cave", "phx_cave", "shw_cave", "bd_cave", "nt_cave", "is_site", "is_wet",
          "convert", "dirok", "id_cave", "gi_cave", "vl_cave", "vt_cave")   # v2 appends vt_cave LAST (v1 layout = prefix)
ENTRIES = CHUNKS


def _asm(text, base):
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(text, base)
    return bytes(enc)


def _split():
    fmt = dict(C, CLONE_DW=CLONE_DW, COST=COST, DAYS=DAYS, CTRL_ID=CTRL_ID)
    src = ASM.format(**{k: hex(v) for k, v in fmt.items()})
    chunks, cur = {}, None
    for line in src.splitlines():
        t = line.strip()
        if t.endswith(":") and t[:-1] in CHUNKS:
            cur = t[:-1]; chunks[cur] = []; continue
        if cur and t and not t.startswith(";"):
            chunks[cur].append(line.split(";")[0].rstrip())
    return chunks


def _render(lines, addrs, anchors):
    import re
    out = []
    for l in lines:
        for nm in CHUNKS:
            l = re.sub(r"\b%s\b" % nm, hex(addrs.get(nm, 0x55555555)), l)
        l = re.sub(r"\b(\w+)_va\b", lambda m: hex(anchors.get(m.group(1), 0x55555555)), l)
        out.append(l)
    return "\n".join(out)


def build():
    """Each routine is assembled at its own base; cross-routine refs become numbers (always rel32/disp32, so sizes
    never depend on the values); the PIC anchor `call X / X: pop r / sub r, X_va` is located by its E8 00000000."""
    chunks = _split()
    addrs, anchors = {}, {}
    for _ in range(3):
        base = ZONE; code = b""; newaddrs = {}
        for nm in CHUNKS:
            newaddrs[nm] = base
            blob = _asm(_render(chunks[nm], addrs, anchors), base)
            k = blob.find(b"\xe8\x00\x00\x00\x00")
            if k >= 0:
                anchor = next(l.strip()[:-1] for l in chunks[nm] if l.strip().endswith("_d:"))
                anchors[anchor] = base + k + 5
                assert blob.find(b"\xe8\x00\x00\x00\x00", k + 1) < 0
            code += blob; base += len(blob)
            pad = (-base) % 4; code += b"\xcc" * pad; base += pad
        stable = newaddrs == addrs
        addrs = newaddrs
        if stable: break
    assert stable, "layout did not converge"
    assert len(code) <= ZONE_END - ZONE
    return code, addrs


def site_bytes(labels):
    out = {}
    def rel(op, src, dst, n=5):
        return bytes([op]) + struct.pack("<i", dst - (src + 5))
    out["REG"] = rel(0xE8, SITES["REG"][0], labels["reg_cave"])
    out["EXE"] = rel(0xE8, SITES["EXE"][0], labels["exe_cave"])
    out["CPL"] = rel(0xE9, SITES["CPL"][0], labels["cpl_cave"])
    out["PHX"] = rel(0xE9, SITES["PHX"][0], labels["phx_cave"])
    out["SHW"] = rel(0xE8, SITES["SHW"][0], labels["shw_cave"])
    vm = {"NT": labels["nt_cave"], "BD": labels["bd_cave"], "VT": labels["vt_cave"]}
    return out, vm


def relocs(d, base):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def _v1_prefix_match(zl, zone, v1len):
    """v1's zone = v2's routines before vt_cave (same addresses), padded with 0xCC to 4, then zeros."""
    v1 = zone[:v1len]
    return zl[:v1len] == v1 and not any(zl[v1len:])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, labels = build()
    sb, vm = site_bytes(labels)
    rel = relocs(bytes(d), BASE)
    states = {}
    for k, (va, van) in SITES.items():
        cur = bytes(d[va - V2F:va - V2F + 5])
        states[k] = "vanilla" if cur == van else "ours" if cur == sb[k] else "FOREIGN"
    for k, (va, van) in VMTS.items():
        cur = struct.unpack_from("<I", d, va - V2F)[0]
        states[k] = "vanilla" if cur == van else "ours" if cur == vm[k] else "FOREIGN"
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    v1len = labels["vt_cave"] - ZONE
    if not any(zl): zstate = "zero"
    elif zl[:len(zone)] == zone and not any(zl[len(zone):]): zstate = "ours"
    elif _v1_prefix_match(zl, zone, v1len): zstate = "v1"
    else: zstate = "DIFFERS"
    bad = [hex(r) for r in rel if ZONE - 3 <= r < ZONE_END] + \
          [hex(r) for k, (va, _) in SITES.items() for r in rel if va - 3 <= r < va + 5]
    vmt_rel = all(va in rel for va, _ in VMTS.values())
    print("AoWEPACK build-bridge | " + " ".join("%s %s" % (k, v) for k, v in states.items()) +
          " | zone %#x %s (%d B) | relocs %s | VMT slot relocs %s" % (ZONE, zstate, len(zone), bad or "none", "ok" if vmt_rel else "MISSING"))
    print("  entries: " + " ".join("%s=%#x" % (k, labels[k]) for k in ENTRIES))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE):
            print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or not vmt_rel or "FOREIGN" in states.values(): print("ABORT (site/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    v1state = zstate == "v1" and states["VT"] == "vanilla" and all(v == "ours" for k, v in states.items() if k != "VT")
    if v1state: print("  upgrading v1 -> v2 in place")
    allours = all(v == "ours" for v in states.values()) and zstate == "ours"
    allvan = all(v == "vanilla" for v in states.values()) and zstate == "zero"
    if not (allours or allvan or v1state): print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    if a.revert:
        for k, (va, van) in SITES.items(): n[va - V2F:va - V2F + 5] = van
        for k, (va, van) in VMTS.items(): struct.pack_into("<I", n, va - V2F, van)
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for k, (va, _) in SITES.items(): n[va - V2F:va - V2F + 5] = sb[k]
        for k, (va, _) in VMTS.items(): struct.pack_into("<I", n, va - V2F, vm[k])
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_bridge2")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
