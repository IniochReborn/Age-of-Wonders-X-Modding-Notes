#!/usr/bin/env python3
r"""Warp Self — STAGE 2: replace the placeholder Call Flames effect with the
actual teleport.

Stage 1 (build_warp_self_stage1.py, user-confirmed) registered spell 0xCA
"Warp Self" as a TCallFlames clone; casting it in tactical combat runs the
spell-as-ranged-action token TCAbRangedTE with [token+0x14]=0x34 (spell
marker), [token+0x18]=spell id, [token+0x1c/0x1e]=caster hex (words),
[token+0x20/0x22]=target hex (words). Phase 0 of TCAbRangedTE.Execute
resolves the caster into [token+0x10], runs TSpell.CombatSpellCast (mana
bookkeeping), then computes strikes/sound; phase 1 applies the per-spell-id
effect (Call Flames = id 0x75, hardcoded).

This patch hooks phase 0 at 0x40B452 (AoWTCPCK.dll), immediately AFTER the
CombatSpellCast block, replacing `mov eax,[0x469420]` (5 bytes).

Cave logic for our id (v4: summon-style DESTINATION SEARCH using the ENGINE's
own per-unit validity — a fake ctx (v3) couldn't express the terrain-cost
matrix, so rocks/UG dirt walls passed; walls ignored abilities):
    settings = TCombatMoveControlSettings.Create   ; classref [0x4129A8]
    SetSourcePos(settings, casterX, casterY, 0)    ; mirrors TCAI.EvalBattle's
    [settings+0x9C]=casterHS; [settings+0x1AC]=0x1A; [settings+0x65]=0
    CreateMovePointTable([caster+0x4C], &settings+0xAC)  ; terrain matrix from
                                                   ; the unit's OWN resource
                                                   ; (walking/flying/wallclimb)
    [settings+0x6C]=GetPlayer(caster); [settings+0x98]=0xC8
    control = [[0x46C064]+0xFC]                    ; the live combat TMoveControl
    Activate(control, settings) or bail            ; TMoveControl.Activate
    level = TMapContainer.GetMapLevel(map, 0)
    for HN in 0..6:                                ; spiral: 0=target, 1..6=ring
        (cx,cy) = CenterHNtoHX(tx, ty, HN)
        bounds-check cx<[level+0xC], cy<[level+0x10]  (GetField has NO check!)
        skip if FindOwnedChild(field, 0x220104)    ; unit there (engine check
                                                   ; allows friendly pass-through)
        found if ValidLocation(control, cx, cy, 0) ; base terrain matrix +
                                                   ; every object CanMoveOn —
                                                   ; rocks/dirt walls/water/walls
                                                   ; per the caster's abilities
    Deactivate(control); Release(settings)
    none valid -> fizzle (MP still consumed)
Activate/ValidLocation/Deactivate live in AoWEPACK with no AoWTCPCK thunk —
called cross-module rebase-proof via delta from the GetPlayer IAT slot
(0x46E7CC): delta = [slot] - 0x557268E4; fn = static VA + delta.

Teleport = drive the game's own synced combat mover ONE step:
    path    = TXYLList[ dest, src ]             ; cost bytes 0 => affordable at 0 MP
    te      = CreateCombatMoveTE(caster, path)  ; ctor+Setup (MovePointsToPos->0)
    Validate(te)                                ; resolves [te+0x1c]=caster from src
    [te+0x18]=1; ExecuteDefaultMove(te)         ; entry vcall TMoveTE.Move pre-
                                                ; decrements the step -> path[0]=dest:
                                                ; TUnitHS.MoveTo + AddHS + MovedTo
                                                ; + ExploreArea/MapChangedRad/redraw
    Free(te); Free(path)                        ; TMoveTE created unqueued (edx=0),
                                                ; Destroy is registration-free
then zero caster MP (mirror of the normal tail at 0x40B6F6), set the Execute
result byte [ebp-9]=1 (token done) and exit through the in-function epilogue
0x40B70F — same path the engine uses when the caster is dead. Phase 1 (flames)
never runs; the token completes on every machine identically (executed inside
the broadcast token => deterministic => LAN-safe; no new token is queued).

REBASE SAFETY: AoWTCPCK.dll's preferred base collides with AoWx.exe, so it
ALWAYS rebases. All cave data refs use the PIC delta trick (delta from the
hook's return address); calls/jmps are rel32. The .reloc HIGHLOW entry that
covers the hooked instruction's abs32 operand (RVA 0xB453) is neutralized
(type 3->0) so the loader can't corrupt our rel32.

Backup: AoWTCPCK.dll.bak_warpself2. Dry-run by default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TC = os.path.join(GAME, "AoWTCPCK.dll")
BAK = TC + ".bak_warpself2"

VA2FILE = 0x400C00                 # AoWTCPCK: VA = file_off + 0x400C00
CAVE_VA, CAVE_LIMIT = 0x438100, 0x438500
HOOK_VA, RET_VA = 0x40B452, 0x40B457
H_OLD = bytes.fromhex("a120944600")  # mov eax,[0x469420]
EPILOGUE_VA = 0x40B70F             # phase-0 "token done" exit (inner-frame unwind)

MAP_SINGLETON   = 0x469420         # ptr -> ptr -> map (+0x10 = TMapContainer)
XYL_CLASSREF    = 0x46E940         # TXYLList classref (as used by MoveCombatUnit)
SET_CLASSREF    = 0x4129A8         # TCombatMoveControlSettings classref (AI donor)
TC_GLOBALS      = 0x46C064         # TC globals; +0xFC = the combat TMoveControl
T_GETMAPLEVEL   = 0x401E64         # thunk HSEngine.TMapContainer.GetMapLevel
T_GETFIELD_LVL  = 0x401E54         # thunk HSEngine.TMapLevel.GetField (no bounds!)
T_XYL_CREATE    = 0x401AFC         # thunk HSEngine.TXYLList.Create
T_XYL_ADD       = 0x401B04         # thunk HSEngine.TXYLList.Add
T_OBJ_FREE      = 0x401050         # thunk System.TObject.Free
T_CENTERHNTOHX  = 0x4022AC         # thunk HSEngine.CenterHNtoHX (spiral idx->hex)
T_SET_CREATE    = 0x40263C         # thunk AoWE.TMoveControlSettings.Create
T_SET_SRCPOS    = 0x40266C         # thunk AoWE.TMoveControlSettings.SetSourcePos
T_SET_RELEASE   = 0x40265C         # thunk AoWE.TMoveControlSettings.Release
T_CMPTABLE      = 0x4029BC         # thunk AoWE.TAbstractUnit.CreateMovePointTable
T_GETPLAYER     = 0x402544         # thunk AoWE.TCombatObject.GetPlayer
F_CREATEMOVETE  = 0x40F548         # CombatTE.CreateCombatMoveTE
F_VALIDATE      = 0x4081EC         # CombatTE.TCombatMoveTE.Validate
F_EXECDEFMOVE   = 0x408278         # CombatTE.TCombatMoveTE.ExecuteDefaultMove
IAT_GETPLAYER   = 0x46E7CC         # AoWTCPCK IAT slot of TCombatObject.GetPlayer
EP_GETPLAYER_S  = 0x557268E4       # its static VA -> AoWEPACK rebase delta
EP_ACTIVATE     = 0x5574646C       # AoWE.TMoveControl.Activate (static VA)
EP_VALIDLOC     = 0x557458E8       # AoWE.TMoveControl.ValidLocation (static VA)
EP_DEACTIVATE   = 0x557466B4       # AoWE.TMoveControl.Deactivate (static VA)
# v5 presentation:
SPELLCTRL_ROOT  = 0x46E8D0         # ptr -> obj; +0x84 = TSpellControl
XYZPT_CLASSREF  = 0x46EB24         # TXYZ point classref (fx position records)
F_ADDEFFECT     = 0x41C6EC         # AoWTC.TAoWCombatMap.AddEffect(map, dl=type)
T_GETSPELL      = 0x4029B4         # thunk AoWE.TSpellControl.GetSpell
T_PLAYEX        = 0x4022FC         # thunk Sound.TSFXLibrary.PlayEx
T_XYZ_ADD       = 0x402DE4         # thunk aowFX.TXYZList.Add
T_OBJ_CREATE    = 0x401040         # thunk System.TObject.Create
T_HXTOHP        = 0x4022BC         # thunk HSEngine.HXtoHP (hex -> pixel)
FX_CLOUDPUFF    = 0x22             # TfxType: the engine's unit-materialize puff
SPELL_ID = 0xCA
UNIT_CLASSID = 0x220104
# scratch block layout (esp-relative, 0x20 bytes)
CTRL  = 0x00                       # the combat TMoveControl instance
SETT  = 0x04                       # our TCombatMoveControlSettings instance
CANDX = 0x08                       # candidate hex X (written by CenterHNtoHX)
CANDY = 0x0C                       # candidate hex Y
HN    = 0x10                       # spiral index 0..6
FNVAL = 0x14                       # runtime addr of ValidLocation
LVL   = 0x18                       # TMapLevel ptr ( +0xC width / +0x10 height )
DELTA = 0x1C                       # AoWEPACK rebase delta
BLK   = 0x20


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.rel = []; self.jcc = []; self.jcc32s = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, tgt): self.db(0xE8); self.rel.append((len(self.buf), tgt)); self.buf += b'\0\0\0\0'
    def jmp(self, tgt):  self.db(0xE9); self.rel.append((len(self.buf), tgt)); self.buf += b'\0\0\0\0'
    def jcc8(self, op, lab):  # short conditional to a forward label
        self.db(op); self.jcc.append((len(self.buf), lab)); self.db(0)
    def jcc32(self, op, lab):  # near conditional (0F xx rel32) to a label
        self.db(0x0F, op); self.jcc32s.append((len(self.buf), lab)); self.buf += b'\0\0\0\0'
    def jmp32(self, lab):      # near unconditional jmp to a label
        self.db(0xE9); self.jcc32s.append((len(self.buf), lab)); self.buf += b'\0\0\0\0'
    def call_lab(self, lab):   # near call to an in-cave label
        self.db(0xE8); self.jcc32s.append((len(self.buf), lab)); self.buf += b'\0\0\0\0'
    def esp(self, *op_then_disp):  # opcode bytes with [esp+disp32] operand
        *op, disp = op_then_disp
        self.db(*op, 0x24); self.dd(disp)
    def resolve(self):
        for off, tgt in self.rel:
            self.buf[off:off+4] = (tgt - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.jcc:
            d = self.labels[lab] - (self.base + off + 1)
            assert -128 <= d <= 127, (hex(off), lab, d)
            self.buf[off] = d & 0xFF
        for off, lab in self.jcc32s:
            self.buf[off:off+4] = (self.labels[lab] - (self.base + off + 4)).to_bytes(4, 'little', signed=True)


def build_cave():
    a = Asm(CAVE_VA)
    a.db(0x53)                                  # push ebx
    a.db(0x8B, 0x5C, 0x24, 0x04)                # mov ebx,[esp+4] (runtime ret addr)
    a.db(0x81, 0xEB); a.dd(RET_VA)              # sub ebx, RET_VA  -> ebx = rebase delta
    a.db(0x8B, 0x45, 0xFC)                      # mov eax,[ebp-4]  (token)
    a.db(0x81, 0x78, 0x14); a.dd(0x34)          # cmp dword [eax+0x14],0x34 (spell marker)
    a.jcc32(0x85, 'normal')                     # jne normal
    a.db(0x81, 0x78, 0x18); a.dd(SPELL_ID)      # cmp dword [eax+0x18],0xCA
    a.jcc32(0x85, 'normal')                     # jne normal
    a.db(0x56, 0x57)                            # push esi; push edi
    a.db(0x8B, 0xF0)                            # mov esi,eax (token)
    a.db(0x81, 0xEC); a.dd(BLK)                 # sub esp,BLK (locals)
    # -- AoWEPACK rebase delta + ValidLocation runtime addr --
    a.db(0x8B, 0x83); a.dd(IAT_GETPLAYER)       # mov eax,[ebx+IAT slot] (PIC)
    a.db(0x2D); a.dd(EP_GETPLAYER_S)            # sub eax, static GetPlayer
    a.esp(0x89, 0x84, DELTA)                    # mov [esp+DELTA],eax
    a.db(0x8B, 0xD0)                            # mov edx,eax
    a.db(0x81, 0xC2); a.dd(EP_VALIDLOC)         # add edx, static ValidLocation
    a.esp(0x89, 0x94, FNVAL)                    # mov [esp+FNVAL],edx
    # -- level ptr (width/height + field lookup base) --
    a.db(0x8B, 0x83); a.dd(MAP_SINGLETON)       # mov eax,[ebx+MAP] (PIC)
    a.db(0x8B, 0x00)                            # mov eax,[eax]
    a.db(0x8B, 0x40, 0x10)                      # mov eax,[eax+0x10] (TMapContainer)
    a.db(0x33, 0xD2)                            # xor edx,edx
    a.call(T_GETMAPLEVEL)                       # -> eax = TMapLevel
    a.esp(0x89, 0x84, LVL)                      # mov [esp+LVL],eax
    # -- build a real settings object for the caster (mirrors TCAI.EvalBattle) --
    a.db(0x33, 0xC9)                            # xor ecx,ecx
    a.db(0xB2, 0x01)                            # mov dl,1
    a.db(0x8B, 0x83); a.dd(SET_CLASSREF)        # mov eax,[ebx+SET_CLASSREF] (PIC)
    a.call(T_SET_CREATE)                        # -> eax = TCombatMoveControlSettings
    a.esp(0x89, 0x84, SETT)                     # mov [esp+SETT],eax
    a.db(0x8B, 0xF8)                            # mov edi,eax (settings)
    a.db(0x6A, 0x00)                            # push 0 (level)
    a.db(0x0F, 0xBF, 0x4E, 0x1E)                # movsx ecx,word [esi+0x1e] (caster y)
    a.db(0x0F, 0xBF, 0x56, 0x1C)                # movsx edx,word [esi+0x1c] (caster x)
    a.db(0x8B, 0xC7)                            # mov eax,edi
    a.call(T_SET_SRCPOS)                        # SetSourcePos (ret 4)
    a.db(0x8B, 0x46, 0x10)                      # mov eax,[esi+0x10] (caster)
    a.db(0x8B, 0x50, 0x60)                      # mov edx,[eax+0x60] (casterHS)
    a.db(0x89, 0x97); a.dd(0x9C)                # mov [edi+0x9c],edx
    a.db(0xC6, 0x87); a.dd(0x1AC); a.db(0x1A)   # mov byte [edi+0x1ac],0x1A
    a.db(0xC6, 0x47, 0x65, 0x00)                # mov byte [edi+0x65],0 (ResetState)
    a.db(0x8D, 0x97); a.dd(0xAC)                # lea edx,[edi+0xac] (matrix dest)
    a.db(0x8B, 0x46, 0x10)                      # mov eax,[esi+0x10]
    a.db(0x8B, 0x40, 0x4C)                      # mov eax,[eax+0x4c] (unit resource)
    a.call(T_CMPTABLE)                          # CreateMovePointTable(res, &table)
    a.db(0x8B, 0x46, 0x10)                      # mov eax,[esi+0x10]
    a.call(T_GETPLAYER)                         # -> al
    a.db(0x88, 0x47, 0x6C)                      # mov [edi+0x6c],al
    a.db(0xC7, 0x87); a.dd(0x98); a.dd(0xC8)    # mov dword [edi+0x98],0xC8
    # -- Activate the live combat move control with our settings --
    a.db(0x8B, 0x83); a.dd(TC_GLOBALS)          # mov eax,[ebx+TC_GLOBALS] (PIC)
    a.db(0x8B, 0x80); a.dd(0xFC)                # mov eax,[eax+0xfc] (control)
    a.esp(0x89, 0x84, CTRL)                     # mov [esp+CTRL],eax
    a.db(0x8B, 0xD7)                            # mov edx,edi (settings)
    a.esp(0x8B, 0x8C, DELTA)                    # mov ecx,[esp+DELTA]
    a.db(0x81, 0xC1); a.dd(EP_ACTIVATE)         # add ecx, static Activate
    a.db(0xFF, 0xD1)                            # call ecx -> al
    a.db(0x84, 0xC0)                            # test al,al
    a.jcc32(0x84, 'relfizzle')                  # je relfizzle (no Deactivate on fail)
    # base Activate does NOT set the ctx unit fields — the TC override
    # TCombatMoveControl.ProcessMove @0x41D038 copies them from settings
    # before calling the base. Without this the control carries a NULL
    # (turn 1: crash in object CanMoveOn) or STALE unit (wrong abilities).
    a.esp(0x8B, 0x84, CTRL)                     # mov eax,[esp+CTRL]
    a.esp(0x8B, 0x94, SETT)                     # mov edx,[esp+SETT]
    a.db(0x8B, 0x8A); a.dd(0x9C)                # mov ecx,[edx+0x9c] (casterHS)
    a.db(0x89, 0x88); a.dd(0x1E0)               # mov [eax+0x1e0],ecx
    a.db(0x8A, 0x8A); a.dd(0x1AC)               # mov cl,[edx+0x1ac]
    a.db(0x88, 0x88); a.dd(0x1E4)               # mov [eax+0x1e4],cl
    a.esp(0xC7, 0x84, HN); a.dd(0)              # mov dword [esp+HN],0
    a.label('loop')
    # -- candidate hex = spiral(HN) around target --
    a.esp(0x8D, 0x84, CANDX)                    # lea eax,[esp+CANDX]
    a.db(0x50)                                  # push eax (&outX)
    a.esp(0x8D, 0x84, 4 + CANDY)                # lea eax,[esp+4+CANDY]
    a.db(0x50)                                  # push eax (&outY)
    a.esp(0x8B, 0x8C, 8 + HN)                   # mov ecx,[esp+8+HN]
    a.db(0x0F, 0xBF, 0x56, 0x22)                # movsx edx,word [esi+0x22] (ty)
    a.db(0x0F, 0xBF, 0x46, 0x20)                # movsx eax,word [esi+0x20] (tx)
    a.call(T_CENTERHNTOHX)                      # ret 8; HN 0 = target itself
    # -- bounds (TMapLevel.GetField has NO check; off-map => garbage ptr) --
    a.esp(0x8B, 0x84, CANDX)                    # mov eax,[esp+CANDX]
    a.db(0x85, 0xC0)                            # test eax,eax
    a.jcc32(0x8C, 'next')                       # jl next
    a.esp(0x8B, 0x94, LVL)                      # mov edx,[esp+LVL]
    a.db(0x3B, 0x42, 0x0C)                      # cmp eax,[edx+0xC] (width)
    a.jcc32(0x8D, 'next')                       # jge next
    a.esp(0x8B, 0x84, CANDY)                    # mov eax,[esp+CANDY]
    a.db(0x85, 0xC0)                            # test eax,eax
    a.jcc32(0x8C, 'next')                       # jl next
    a.db(0x3B, 0x42, 0x10)                      # cmp eax,[edx+0x10] (height)
    a.jcc32(0x8D, 'next')                       # jge next
    # -- field + occupied guard --
    a.esp(0x8B, 0x94, CANDX)                    # mov edx,[esp+CANDX]
    a.esp(0x8B, 0x8C, CANDY)                    # mov ecx,[esp+CANDY]
    a.esp(0x8B, 0x84, LVL)                      # mov eax,[esp+LVL]
    a.call(T_GETFIELD_LVL)                      # -> eax = TMapField
    a.db(0x8B, 0xF8)                            # mov edi,eax
    a.db(0xBA); a.dd(UNIT_CLASSID)              # mov edx,0x220104
    a.db(0x8B, 0x08)                            # mov ecx,[eax]
    a.db(0xFF, 0x91); a.dd(0x80)                # call [ecx+0x80] (FindOwnedChild)
    a.db(0x85, 0xC0)                            # test eax,eax
    a.jcc32(0x85, 'next')                       # jne next (unit there; the engine
                                                # check allows friendly pass-through)
    # -- engine verdict: TMoveControl.ValidLocation(control, x, y, 0) --
    a.esp(0x8B, 0xBC, FNVAL)                    # mov edi,[esp+FNVAL]
    a.esp(0x8B, 0x84, CTRL)                     # mov eax,[esp+CTRL]
    a.esp(0x8B, 0x94, CANDX)                    # mov edx,[esp+CANDX]
    a.esp(0x8B, 0x8C, CANDY)                    # mov ecx,[esp+CANDY]
    a.db(0x6A, 0x00)                            # push 0 (level; ret 4)
    a.db(0xFF, 0xD7)                            # call edi -> al (1 = may stand here)
    a.db(0x84, 0xC0)                            # test al,al
    a.jcc32(0x85, 'found')                      # jne found
    a.label('next')
    a.esp(0xFF, 0x84, HN)                       # inc dword [esp+HN]
    a.esp(0x83, 0xBC, HN); a.db(0x06)           # cmp dword [esp+HN],6
    a.jcc32(0x8E, 'loop')                       # jle loop
    # none valid: Deactivate, release settings, fizzle
    a.esp(0x8B, 0x84, CTRL)                     # mov eax,[esp+CTRL]
    a.esp(0x8B, 0x8C, DELTA)                    # mov ecx,[esp+DELTA]
    a.db(0x81, 0xC1); a.dd(EP_DEACTIVATE)       # add ecx, static Deactivate
    a.db(0xFF, 0xD1)                            # call ecx
    a.label('relfizzle')
    a.esp(0x8B, 0x84, SETT)                     # mov eax,[esp+SETT]
    a.call(T_SET_RELEASE)                       # Release(settings) -> frees
    a.db(0x81, 0xC4); a.dd(BLK)                 # add esp,BLK
    a.jmp32('fizzle')
    a.label('found')
    # Deactivate the control before driving the move TE
    a.esp(0x8B, 0x84, CTRL)                     # mov eax,[esp+CTRL]
    a.esp(0x8B, 0x8C, DELTA)                    # mov ecx,[esp+DELTA]
    a.db(0x81, 0xC1); a.dd(EP_DEACTIVATE)       # add ecx, static Deactivate
    a.db(0xFF, 0xD1)                            # call ecx
    # -- v5: spell sound (mirrors the skipped phase-0 PlayEx block) --
    a.db(0xBA); a.dd(SPELL_ID)                  # mov edx,0xCA
    a.db(0x8B, 0x83); a.dd(SPELLCTRL_ROOT)      # mov eax,[ebx+SPELLCTRL_ROOT] (PIC)
    a.db(0x8B, 0x00)                            # mov eax,[eax]
    a.db(0x8B, 0x80); a.dd(0x84)                # mov eax,[eax+0x84] (spell control)
    a.call(T_GETSPELL)                          # -> eax = spell
    a.db(0x85, 0xC0)                            # test eax,eax
    a.jcc8(0x74, 'nosnd')                       # je nosnd
    a.db(0x8B, 0x40, 0x28)                      # mov eax,[eax+0x28] (sfx object)
    a.db(0x85, 0xC0)                            # test eax,eax
    a.jcc8(0x74, 'nosnd')                       # je nosnd
    a.db(0x6A, 0x00, 0x6A, 0x00, 0x6A, 0x01)    # push 0(LOOP OFF); push 0; push 1
    a.db(0x6A, 0x00, 0x6A, 0x00)                # push 0; push 0
    # (vanilla passes loop=1 and stops via the handle freed at token end
    #  [epilogue 0x40CC55 frees [token+0x2c]]; our token ends instantly,
    #  so the sound must be one-shot)
    a.db(0xB9); a.dd(0x40)                      # mov ecx,0x40
    a.db(0x33, 0xD2)                            # xor edx,edx
    a.call(T_PLAYEX)                            # PlayEx (callee-clean)
    a.label('nosnd')
    # -- v5: materialize puffs at source and destination --
    a.db(0x0F, 0xBF, 0x46, 0x1C)                # movsx eax,word [esi+0x1c] (src x)
    a.db(0x0F, 0xBF, 0x56, 0x1E)                # movsx edx,word [esi+0x1e] (src y)
    a.call_lab('makefx')
    a.esp(0x8B, 0x84, CANDX)                    # mov eax,[esp+CANDX]
    a.esp(0x8B, 0x94, CANDY)                    # mov edx,[esp+CANDY]
    a.call_lab('makefx')
    # -- path list [dest, src], zero cost/level --
    a.db(0xB2, 0x01)                            # mov dl,1
    a.db(0x8B, 0x83); a.dd(XYL_CLASSREF)        # mov eax,[ebx+XYL_CLASSREF] (PIC)
    a.call(T_XYL_CREATE)                        # -> eax = list
    a.db(0x8B, 0xF8)                            # mov edi,eax
    a.esp(0x8B, 0x94, CANDY)                    # mov edx,[esp+CANDY]
    a.db(0xC1, 0xE2, 0x08)                      # shl edx,8
    a.esp(0x0B, 0x94, CANDX)                    # or edx,[esp+CANDX] (= cx | cy<<8)
    a.db(0x8B, 0xC7)                            # mov eax,edi
    a.call(T_XYL_ADD)                           # Add(list, dest)
    a.db(0x0F, 0xB7, 0x56, 0x1E)                # movzx edx,word [esi+0x1e]
    a.db(0xC1, 0xE2, 0x08)                      # shl edx,8
    a.db(0x0F, 0xB7, 0x46, 0x1C)                # movzx eax,word [esi+0x1c]
    a.db(0x0B, 0xD0)                            # or edx,eax   (src = x | y<<8)
    a.db(0x8B, 0xC7)                            # mov eax,edi
    a.call(T_XYL_ADD)                           # Add(list, src)
    a.esp(0x8B, 0x84, SETT)                     # mov eax,[esp+SETT]
    a.call(T_SET_RELEASE)                       # Release(settings) -> frees
    a.db(0x81, 0xC4); a.dd(BLK)                 # add esp,BLK (release scratch)
    # -- create + drive the move TE one step (src -> dest) --
    a.db(0x8B, 0xD7)                            # mov edx,edi (path)
    a.db(0x8B, 0x46, 0x10)                      # mov eax,[esi+0x10] (caster)
    a.call(F_CREATEMOVETE)                      # -> eax = TE (or 0)
    a.db(0x85, 0xC0)                            # test eax,eax
    a.jcc8(0x74, 'freepath')
    a.db(0x50)                                  # push eax (TE)
    a.call(F_VALIDATE)                          # Validate(eax=TE) -> al
    a.db(0x84, 0xC0)                            # test al,al
    a.db(0x58)                                  # pop eax (TE; flags kept)
    a.jcc8(0x74, 'freete')
    a.db(0x50)                                  # push eax
    a.db(0xC7, 0x40, 0x18); a.dd(1)             # mov dword [eax+0x18],1 (step; the
                                                # entry vcall TMoveTE.Move PRE-DECREMENTS
                                                # it -> 0 = dest entry, like InitializeMove
                                                # (count-1) does in the engine's own flow)
    a.call(F_EXECDEFMOVE)                       # ExecuteDefaultMove(eax=TE)
    a.db(0x58)                                  # pop eax (TE)
    a.label('freete')
    a.call(T_OBJ_FREE)                          # Free(TE)
    a.label('freepath')
    a.db(0x8B, 0xC7)                            # mov eax,edi
    a.call(T_OBJ_FREE)                          # Free(path)
    a.label('fizzle')
    # -- mirror normal tail: cast zeroes caster MP; then end the token --
    a.db(0x8B, 0x46, 0x10)                      # mov eax,[esi+0x10]
    a.db(0x33, 0xD2)                            # xor edx,edx
    a.db(0x89, 0x50, 0x5C)                      # mov [eax+0x5c],edx
    a.db(0x5F, 0x5E, 0x5B)                      # pop edi; pop esi; pop ebx
    a.db(0xC6, 0x45, 0xF7, 0x01)                # mov byte [ebp-9],1 (result: done)
    a.db(0x83, 0xC4, 0x04)                      # add esp,4 (drop return addr)
    a.jmp(EPILOGUE_VA)                          # unwind inner frame, exit Execute
    a.label('normal')
    a.db(0x8B, 0x83); a.dd(MAP_SINGLETON)       # displaced instr, PIC form
    a.db(0x5B)                                  # pop ebx
    a.db(0xC3)                                  # ret -> 0x40B457
    # ---- makefx(eax=hexX, edx=hexY): cloud puff centered on the hex ----
    # (recipe = MakeHitBlood/PrayerGlow donors; clobbers eax/ecx/edx/edi)
    a.label('makefx')
    a.db(0x56)                                  # push esi
    a.db(0x55)                                  # push ebp
    a.db(0x8B, 0xEC)                            # mov ebp,esp
    a.db(0x83, 0xEC, 0x08)                      # sub esp,8
    a.db(0x89, 0x45, 0xFC)                      # mov [ebp-4],eax (hexX)
    a.db(0x89, 0x55, 0xF8)                      # mov [ebp-8],edx (hexY)
    a.db(0x8B, 0x83); a.dd(TC_GLOBALS)          # mov eax,[ebx+TC_GLOBALS] (combat map)
    a.db(0xB2, FX_CLOUDPUFF)                    # mov dl,0x22
    a.call(F_ADDEFFECT)                         # -> eax = fx
    a.db(0x8B, 0xF8)                            # mov edi,eax
    # tag the fx as OUR spell's: the type-0x22 NewFrame handler @0x42DB6D
    # resolves its frames via GetSpell([fx+0x18])->[spell+0x2C] image
    # sequence when [fx+0x14]==0x34; untagged fx have no frames = invisible.
    a.db(0xC7, 0x47, 0x14); a.dd(0x34)          # mov dword [edi+0x14],0x34
    a.db(0xC7, 0x47, 0x18); a.dd(SPELL_ID)      # mov dword [edi+0x18],0xCA
    a.db(0xB2, 0x01)                            # mov dl,1
    a.db(0x8B, 0x83); a.dd(XYZPT_CLASSREF)      # mov eax,[ebx+XYZPT_CLASSREF] (PIC)
    a.call(T_OBJ_CREATE)                        # -> eax = point
    a.db(0x8B, 0xF0)                            # mov esi,eax
    a.db(0x8B, 0xD0)                            # mov edx,eax
    a.db(0x8B, 0x47, 0x1C)                      # mov eax,[edi+0x1c] (fx point list)
    a.call(T_XYZ_ADD)                           # Add(list, pt)
    a.db(0x8D, 0x46, 0x08)                      # lea eax,[esi+8]
    a.db(0x50)                                  # push eax (&pixelY)
    a.db(0x8D, 0x4E, 0x04)                      # lea ecx,[esi+4] (&pixelX)
    a.db(0x8B, 0x55, 0xF8)                      # mov edx,[ebp-8] (hexY)
    a.db(0x8B, 0x45, 0xFC)                      # mov eax,[ebp-4] (hexX)
    a.call(T_HXTOHP)                            # hex -> pixel (ret 4)
    a.db(0x83, 0x46, 0x04, 0x10)                # add dword [esi+4],0x10 (center)
    a.db(0x83, 0x46, 0x08, 0x10)                # add dword [esi+8],0x10
    a.db(0x8B, 0xE5)                            # mov esp,ebp
    a.db(0x5D)                                  # pop ebp
    a.db(0x5E)                                  # pop esi
    a.db(0xC3)                                  # ret
    a.resolve()
    assert CAVE_VA + len(a.buf) <= CAVE_LIMIT, hex(len(a.buf))
    return bytes(a.buf)


def reloc_entries(data):
    """Yield (entry_file_off, type, target_file_off) for every .reloc entry."""
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]
    osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vs, raw, rs)); p += 40
    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs): return raw + rva - va
    off = r2o(rrva); end = off + rsz
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        if blk < 8: break
        for i in range((blk - 8)//2):
            wo = off + 8 + i*2
            w = struct.unpack_from('<H', data, wo)[0]
            t = w >> 12
            if t == 0: continue
            fo = r2o(page + (w & 0xFFF))
            if fo is not None: yield wo, t, fo
        off += blk


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, TC); print("restored AoWTCPCK.dll from", os.path.basename(BAK))
        else:
            print("no backup found"); return 1
        return 0
    d = bytearray(open(TC, 'rb').read())
    cave = build_cave()
    h_off = HOOK_VA - VA2FILE
    c_off = CAVE_VA - VA2FILE
    # hook site: original bytes (or already-applied hook for idempotent rerun)
    cur = bytes(d[h_off:h_off+5])
    assert cur == H_OLD or cur[0] == 0xE8, cur.hex()
    # cave area: zeros (or a previous application)
    curc = bytes(d[c_off:c_off+len(cave)])
    assert curc == bytes(len(cave)) or curc[0] == 0x53, curc[:8].hex()
    # relocs: exactly one HIGHLOW entry covering the hook's abs32 operand; none in cave
    hook_hits, cave_hits = [], []
    for wo, t, fo in reloc_entries(bytes(d)):
        if h_off <= fo + 3 and fo < h_off + 5: hook_hits.append((wo, t, fo))
        if c_off <= fo + 3 and fo < c_off + len(cave): cave_hits.append((wo, t, fo))
    assert not cave_hits, [hex(x[2]) for x in cave_hits]
    assert len(hook_hits) == 1 and hook_hits[0][2] == h_off + 1, hook_hits
    wo, t, fo = hook_hits[0]
    assert t in (3, 0), t   # 0 if already neutralized by a previous run
    # patch
    d[c_off:c_off+len(cave)] = cave
    d[h_off:h_off+5] = bytes([0xE8]) + (CAVE_VA - (HOOK_VA+5)).to_bytes(4, 'little', signed=True)
    w = struct.unpack_from('<H', d, wo)[0]
    struct.pack_into('<H', d, wo, w & 0x0FFF)   # type 3 -> 0 (skip)
    print("cave %dB @VA 0x%X (file 0x%X); hook @0x%X -> call cave; reloc word @file 0x%X neutralized"
          % (len(cave), CAVE_VA, c_off, HOOK_VA, wo))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(TC, BAK); print("Backup ->", os.path.basename(BAK))
    open(TC, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
