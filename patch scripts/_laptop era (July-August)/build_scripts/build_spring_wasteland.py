#!/usr/bin/env python3
"""Spring of Life: undead/wasteland conditional effect (AoWEPACK.dll).

Design (see ../Spring_Of_Life_Wasteland_Design.md):

  terrain under the spring   | living (non-undead) unit      | undead unit
  ---------------------------+-------------------------------+------------------
  anything except wasteland  | heal + Nature's Blessing      | NOTHING (new)
  Wasteland (5) / CaveW (0xB)| poison-cloud effect (new)     | heal + Nature's
                             |                               | Blessing (new)

"Undead" = the engine's own Turn Undead test (TTurnUndeadAbility.CanTouchUnit
@0x5576ADC8): race == 0x0B (Undead) OR GetAbilityEnabled(0x81 Animated).

"Poison-cloud effect" = TAbstractUnit.ExecuteStormDamage(unit, 6=Pestilence,
nil) @0x55780668 - the exact per-unit routine TPoisonCloud drives through
TArmy.IncommingStorm: poison damage roll (immunity blocks / protection
halves, wasteland is Pestilence's on-type terrain so the x4 strength bonus
applies) plus the Poisoned (0x60) debuff when damage lands.  The magic
shield check from TPoisonCloud.ArmyPlaced (field GetMagicShieldActive) is
kept.  Skipped vs a real poison cloud: the army event-log toast + its
ValidateGameOver call (cosmetic; deaths themselves are handled).

Hook: Spring.TSpringOfLife.ExecuteNaturesBlessing @0x557A3DE4 - its per-unit
loop (0x557A3DEF..0x557A3E21, 0x33 bytes) blindly ExpandAbility(0x63)s every
unit in the placed army.  Replaced with a call into cave_spring which:

  1. reads the terrain byte of the field the army was placed on
     ([argMO+4] = TAoWMapField, +0x14 = terrain; wasteland = 5 or 0xB)
  2. on wasteland: reseeds System.RandSeed from the synced map RNG and
     BeginUpdates the army - byte-for-byte what TArmy.IncommingStorm does at
     entry, so MP stays deterministic and change notifications batch
  3. loops the army: bless iff (undead == wasteland); poison living units on
     wasteland (unless the field has an active magic shield)
  4. on wasteland: gated APest PlaySample (v5, see below), then TArmy.Validate
     (reap poison deaths) + EndUpdate
  5. returns AL=0 on wasteland (sound already handled in-cave) or on a
     no-blessing placement - the hook then skips the vanilla blessing
     sound+animation block (jz 0x557A3F0F epilogue); AL=1 only for a normal
     blessed placement, which runs the vanilla block untouched

Cave @0x55810000 (file 0x10F400) - inside the big verified-zeros run
0x10F370..0x1E6E10, clear of every earlier cave (all < 0x5580F000).
Position-independent: rel32 calls only; the two data globals (AoWHSMap
@0x558FA040, RandSeed IAT slot @0x558FB720) are read via the call/pop
rebase-delta trick (the DLL rebases at runtime; caves get no .reloc).

v5 (2026-08-07): wasteland SFX moved INSIDE the cave.  v4 patched two 5-byte
sites in the vanilla sound/anim block (sfx_pick @0x557A3E67, anim_gate
@0x557A3E94); those site patches empirically caused "Exception occured during
TArmyDefaultMoveTE" + army corruption on spring placements (static analysis
never found the defect - sites reverted -> stable; do NOT re-add them).  v5
keeps both sites byte-for-byte vanilla and instead, on wasteland with any
effect applied, the cave replicates the vanilla sound gate (play if army
owner == local player [[0x558E9494]]+0xA5, else if TAoWHSMap.Watching(spring
x/y/lvl via esi virtuals +0x74/78/7C)) and calls PlaySample with the cave's
APest literal, then returns AL=0 so the hook jumps straight to the epilogue -
no chime, no sparkle on wasteland; normal springs run the vanilla block
untouched.

v2 (2026-08-06): v1 read the terrain as [argMO+4]+0x14 - WRONG.  [argMO+4]
is the *message-hub* HSEngine.TMapField (the thing SendMapFieldMsg /
GetMagicShieldActive want); its +0x14 is not terrain, so the wasteland flag
never set (in-game: undead no longer blessed anywhere, but no wasteland
behavior).  The terrain cell is a different object: ExecuteStormDamage's own
terrain-bonus code does TAbstractUnit.GetLocation(unit,&x,&y,&lvl) ->
TMapContainer.GetField([AoWHSMap+0x10], x, y, lvl) -> terrain = [cell+0x14].
v2 mirrors that byte-for-byte using unit 0 of the placed army (all units
share the hex; empty army -> no-op).  Location x == 0xFF (not on map) ->
treated as non-wasteland.

Dry-run by default, --apply to write.  Idempotent; verifies bytes before
writing; backs up to AoWEPACK.dll.bak_spring_wasteland on first apply.
"""
import os
import shutil
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_spring_wasteland"

VA2FILE = 0x55700C00                 # file offset = VA - VA2FILE (CODE section)

# ---- engine symbols (AoWEPACK.dll preferred-base VAs, all verified) --------
GETUNIT      = 0x5578309C            # AoWE.TUnitList.GetUnit(eax=list, edx=i)
STORMDMG     = 0x55780668            # AoWE.TAbstractUnit.ExecuteStormDamage(eax=unit, dl=idx, ecx=caster)
VALIDATE     = 0x5578CF7C            # AoWE.TArmy.Validate(eax=army)
BEGINUPD     = 0x55703284            # thunk EngineP!TEChangeNotifyNode.BeginUpdate(eax)
ENDUPD       = 0x5570328C            # thunk EngineP!TEChangeNotifyNode.EndUpdate(eax)
MAGICSHIELD  = 0x55771D38            # AoWE.TAoWMapField.GetMagicShieldActive(eax=hub-field)
HSMAP_RANDOM = 0x5577827C            # AoWE.TAoWHSMap.Random(eax=map, edx=range)
GETLOCATION  = 0x5577ED94            # AoWE.TAbstractUnit.GetLocation(eax=unit, edx=&x, ecx=&y, [&lvl])
GETFIELD     = 0x557020FC            # thunk HSEPack!TMapContainer.GetField(eax=cont, edx=x, ecx=y, [lvl])
AOWHSMAP     = 0x558FA040            # global: TAoWHSMap ptr (PIC access only!)
RANDSEED_IAT = 0x558FB720            # IAT slot -> VCL30!System.RandSeed
# event-log machinery (all straight out of TArmy.IncommingStorm @0x557904B4)
LOGCLASSREF  = 0x557135E8            # slot holding TArmyEventLog class (VMT) ptr
LOGCREATE    = 0x5578BB6C            # AoWE.TArmyEventLog.Create(eax=class, dl=1, ecx=0)
STORMRSTR6   = 0x558E8264 + 6*4      # AoWE.TStormTypeRStr[6] = "Pestilence" RStr ptr
TRANSLATE    = 0x557249FC            # AoWE.TranslateRStr(eax=rstr, edx=&outstr)
LSTRASG      = 0x55701150            # thunk VCL30!System.@LStrAsg(eax=&dest, edx=src)
LSTRCLR      = 0x55701140            # thunk VCL30!System.@LStrClr(eax=&str)
BYTEADD      = 0x55702EFC            # thunk EngineP!Engine.TByteList.Add(eax=list, edx=val)
STORMDMGT6   = 0x558E8330 + 6        # AoWE.StormDamageType[6] = 0x10 (poison bit)
VALIDGO      = 0x5578BDDC            # AoWE.TArmyEventLog.ValidateGameOver(eax=log)
DISTLOG      = 0x557FE558            # EventLog.DistributeLocationEventLog(eax=log, dl, cl, [1],[y],[x])
VISIBLE      = 0x557759F8            # AoWE.TAoWHSMap.Visible (vanilla callee at ANIM site)
WATCHING     = 0x55775B88            # AoWE.TAoWHSMap.Watching (sound gate, v5 in-cave sound)
PLAYSAMPLE   = 0x55702D04            # thunk SoundP!Sound.PlaySample(eax=str)
GAMEGLOBAL   = 0x558E9494            # global: ptr -> obj whose byte +0xA5 = local player
                                     # (vanilla sound gate @0x557A3E2B: owner==local -> play)
SCRATCH      = 0x558FA8F0            # BSS page slack (combatlog uses 0x558FA810-38)
                                     #   +0: bit0 = wasteland (SFX pick), bit1 = blessed (anim gate)
                                     #   +1: breadcrumb stage (post-mortem diagnostics, v4.2):
                                     #       10 entry, 20 count-ok, 30 terrain-read, 40 reseeded,
                                     #       50 log-created, 58 log-filled, 60 snapshot, 70 loop,
                                     #       80 loop-done, 90 gameover-checked, A0 distributed,
                                     #       B0 log-freed, C0 validated, FF returned
                                     #   +2: unused since v5 (cleared each run)
                                     #   +3: v5 sound result (0=no sound path, 2=APest
                                     #       played in-cave, 3=gated off: not watching)
                                     #   +4: terrain byte read   +5: unused since v5
ENCHP02_TXT  = 0x557A3F20            # vanilla 'SFX\ATTACK\ENCHP02.WAV' literal text

# ---- hook site -------------------------------------------------------------
HOOK      = 0x557A3DEF               # ExecuteNaturesBlessing loop start
HOOK_END  = 0x557A3E22               # L557A3E22 (sound/anim part, kept)
EPILOGUE  = 0x557A3F0F               # add esp,14h; pop edi/esi/ebx; ret

# ---- vanilla terrain gate in TSpringOfLife.ArmyPlaced ----------------------
# mov eax,[ebx+4]; mov al,[eax+0x14]  = terrain under the spring, then:
#   sub al,3; je skip   -> Snow(3): spring inactive      (KEPT - vanilla)
#   sub al,2; je skip   -> Wasteland(5): spring inactive (OPENED - v3)
# This gate is why v1/v2 did nothing on wasteland: ExecuteNaturesBlessing was
# never called there.  NOP the second je so wasteland springs run the cave.
# (CaveWasteland 0xB was never gated.)
GATE      = 0x557A3F51               # file 0xA3351
GATE_OLD  = bytes.fromhex("2C027409")   # sub al,2 ; je 0x557A3F5E
GATE_NEW  = bytes.fromhex("2C029090")   # sub al,2 ; nop nop

# ---- SFX + animation sites: PERMANENTLY VANILLA since v5 -------------------
# v4 redirected these two 5-byte sites into the cave (sfx_pick / anim_gate);
# that caused TArmyDefaultMoveTE exceptions + army corruption.  v5 keeps both
# sites vanilla forever (and restores them if a prior version's call is found).
SFX_SITE  = 0x557A3E67               # mov eax, ENCHP02_TXT (vanilla)
SFX_OLD   = bytes.fromhex("B8203F7A55")
ANIM_SITE = 0x557A3E94               # call TAoWHSMap.Visible (vanilla)
ANIM_OLD  = bytes.fromhex("E85F1BFDFF")

OLD_HOOK = bytes.fromhex(
    "8B0424"            # mov eax,[esp]          ; argMO
    "8B401C"            # mov eax,[eax+1Ch]      ; army
    "8B10"              # mov edx,[eax]
    "FF5254"            # call [edx+54h]         ; Count
    "8BD8"              # mov ebx,eax
    "4B"                # dec ebx
    "85DB"              # test ebx,ebx
    "7C21"              # jl  L557A3E22
    "43"                # inc ebx
    "33FF"              # xor edi,edi
    "8B0424"            # mov eax,[esp]
    "8B401C"            # mov eax,[eax+1Ch]
    "8BD7"              # mov edx,edi
    "E88BF2FDFF"        # call TUnitList.GetUnit
    "BA63000000"        # mov edx,63h            ; Nature's Blessing
    "8B08"              # mov ecx,[eax]
    "FF9194000000"      # call [ecx+94h]         ; ExpandAbility
    "47"                # inc edi
    "4B"                # dec ebx
    "75E2")             # jnz loop
assert len(OLD_HOOK) == HOOK_END - HOOK == 0x33

CAVE_BASE  = 0x55810000              # file 0x10F400, verified zeros
CAVE_LIMIT = 0x55810500              # claimed range; zero-padded on write

WASTELAND, CAVE_WASTELAND = 0x05, 0x0B
RACE_UNDEAD  = 0x0B
AB_ANIMATED  = 0x81
AB_BLESSING  = 0x63
STORM_PESTILENCE = 6


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.fix32 = []; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, name): self.labels[name] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += v.to_bytes(4, 'little')
    def call(self, target): self.db(0xE8); self._rel32(target)
    def jmp32(self, target): self.db(0xE9); self._rel32(target)
    def _rel32(self, target):
        if isinstance(target, str):
            self.fix32.append((len(self.buf), target)); self.buf += b'\0\0\0\0'
        else:
            self.buf += (target - (self.here() + 4)).to_bytes(4, 'little', signed=True)
    def j8(self, opcode, label):
        self.db(opcode); self.fix8.append((len(self.buf), label)); self.db(0x00)
    def resolve(self):
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.fix8:
            rel = self.labels[lab] - (self.base + off + 1)
            assert -128 <= rel <= 127, "rel8 out of range for %s: %d" % (lab, rel)
            self.buf[off] = rel & 0xFF


def build_cave():
    a = Asm(CAVE_BASE)

    def crumb(n):
        # breadcrumb: [SCRATCH+1] = stage n (clobbers ecx only; esp must be at
        # the locals base so [esp+4] = PIC delta)
        a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]
        a.db(0xC6, 0x81); a.dd(SCRATCH + 1); a.db(n)  # mov byte [ecx+SCRATCH+1], n
    # in: [esp+4]=argMO (outer [esp]); esi=spring (untouched)
    # out: AL = bh flags (bit0 blessed, bit1 poisoned) on normal terrain,
    #      forced 0 on wasteland (v5: sound handled in-cave; hook enters the
    #      vanilla sound/anim block only when AL != 0)
    # ebx: bl = wasteland flag, bh = out-flags; edi = loop index
    # (ebx/edi are dead in the caller after the loop - verified)
    # locals after sub esp,16:
    #   [esp]=x [esp+1]=y [esp+2]=lvl [esp+3]=anydmg
    #   [esp+4]=PIC delta  [esp+8]=event log (0=none)  [esp+12]=temp AnsiString
    a.label('cave_spring')
    a.db(0x55)                          # push ebp
    a.db(0x8B, 0x6C, 0x24, 0x08)        # mov ebp, [esp+8]       ; argMO
    a.db(0x83, 0xEC, 0x10)              # sub esp, 16            ; locals
    a.call(a.here() + 5)                # call $+5 (PIC delta)
    popva = a.here()
    a.db(0x58)                          # pop eax                ; runtime VA of pop
    a.db(0x2D); a.dd(popva)             # sub eax, preferred-VA  ; eax = rebase delta
    a.db(0x89, 0x44, 0x24, 0x04)        # mov [esp+4], eax       ; save delta
    a.db(0x33, 0xC0)                    # xor eax, eax
    a.db(0x89, 0x04, 0x24)              # mov [esp], eax         ; x/y/lvl/anydmg = 0
    a.db(0x89, 0x44, 0x24, 0x08)        # mov [esp+8], eax       ; log = nil
    a.db(0x89, 0x44, 0x24, 0x0C)        # mov [esp+12], eax      ; temp str = nil
    a.db(0x33, 0xDB)                    # xor ebx, ebx           ; bl=waste bh=flags
    crumb(0x10)                         # entry
    a.db(0xC7, 0x81); a.dd(SCRATCH + 2); a.dd(0)  # mov dword [ecx+SCRATCH+2], 0 (clear diag)
    # --- empty army? nothing to do (also guards unit-0 fetch) ---
    a.db(0x8B, 0x45, 0x1C)              # mov eax, [ebp+0x1C]    ; army
    a.db(0x8B, 0x10)                    # mov edx, [eax]
    a.db(0xFF, 0x52, 0x54)              # call [edx+0x54]        ; Count
    a.db(0x85, 0xC0)                    # test eax, eax
    a.db(0x0F, 0x8E)                    # jle rel32 done         ; (bl=0 -> plain exit)
    a.fix32.append((len(a.buf), 'done')); a.buf += b'\0\0\0\0'
    crumb(0x20)                         # count ok
    # --- terrain of the hex the army was placed on (ExecuteStormDamage pattern:
    #     GetLocation(unit0) -> TMapContainer.GetField -> [cell+0x14]) ---
    a.db(0x8B, 0x45, 0x1C)              # mov eax, [ebp+0x1C]
    a.db(0x33, 0xD2)                    # xor edx, edx
    a.call(GETUNIT)                     # -> eax = unit 0
    a.db(0x8D, 0x54, 0x24, 0x02)        # lea edx, [esp+2]       ; &lvl
    a.db(0x52)                          # push edx               ; stack arg
    a.db(0x8D, 0x54, 0x24, 0x04)        # lea edx, [esp+4]       ; &x (esp shifted)
    a.db(0x8D, 0x4C, 0x24, 0x05)        # lea ecx, [esp+5]       ; &y
    a.call(GETLOCATION)                 # GetLocation(unit,&x,&y,[&lvl])
    a.db(0x80, 0x3C, 0x24, 0xFF)        # cmp byte [esp], 0xFF   ; off-map?
    a.j8(0x74, 'terr_done')             # je  terr_done          ; -> not wasteland
    a.db(0x0F, 0xBE, 0x44, 0x24, 0x02)  # movsx eax, byte [esp+2]; level
    a.db(0x50)                          # push eax               ; stack arg
    a.db(0x8B, 0x54, 0x24, 0x08)        # mov edx, [esp+8]       ; delta (esp shifted)
    a.db(0x8B, 0x82); a.dd(AOWHSMAP)    # mov eax, [edx+AoWHSMap]
    a.db(0x8B, 0x40, 0x10)              # mov eax, [eax+0x10]    ; TMapContainer
    a.db(0x0F, 0xBE, 0x54, 0x24, 0x04)  # movsx edx, byte [esp+4]; x
    a.db(0x0F, 0xBE, 0x4C, 0x24, 0x05)  # movsx ecx, byte [esp+5]; y
    a.call(GETFIELD)                    # -> eax = terrain cell
    a.db(0x8A, 0x40, 0x14)              # mov al, [eax+0x14]     ; terrain byte
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0x88, 0x81); a.dd(SCRATCH + 4) # mov [ecx+SCRATCH+4], al  (record terrain)
    a.db(0x3C, WASTELAND)               # cmp al, 5
    a.j8(0x74, 'waste')                 # je  waste
    a.db(0x3C, CAVE_WASTELAND)          # cmp al, 0x0B
    a.j8(0x75, 'terr_done')             # jne terr_done
    a.label('waste')
    a.db(0xB3, 0x01)                    # mov bl, 1
    a.label('terr_done')
    crumb(0x30)                         # terrain determined
    a.db(0x84, 0xDB)                    # test bl, bl
    a.db(0x0F, 0x84)                    # jz rel32 no_seed
    a.fix32.append((len(a.buf), 'no_seed')); a.buf += b'\0\0\0\0'
    # --- wasteland prep: reseed synced RNG + BeginUpdate (IncommingStorm parity)
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0x8B, 0x81); a.dd(AOWHSMAP)    # mov eax, [ecx+AoWHSMap]
    a.db(0xBA); a.dd(0x00FFFFFF)        # mov edx, 0xFFFFFF
    a.call(HSMAP_RANDOM)                # -> eax = synced roll
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0x8B, 0x91); a.dd(RANDSEED_IAT)  # mov edx, [ecx+IATslot] ; &System.RandSeed
    a.db(0x89, 0x02)                    # mov [edx], eax
    a.db(0x8B, 0x45, 0x1C)              # mov eax, [ebp+0x1C]    ; army
    a.call(BEGINUPD)                    # TEChangeNotifyNode.BeginUpdate
    crumb(0x40)                         # reseeded + BeginUpdate done
    # --- create the Pestilence army event log (IncommingStorm parity) --------
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0x8B, 0x81); a.dd(LOGCLASSREF) # mov eax, [ecx+classref]; TArmyEventLog class
    a.db(0x33, 0xC9)                    # xor ecx, ecx
    a.db(0xB2, 0x01)                    # mov dl, 1
    a.call(LOGCREATE)                   # -> eax = log
    a.db(0x89, 0x44, 0x24, 0x08)        # mov [esp+8], eax       ; save log
    crumb(0x50)                         # log created
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0x8B, 0x81); a.dd(STORMRSTR6)  # mov eax, [ecx+RStr[6]] ; "Pestilence"
    a.db(0x8D, 0x54, 0x24, 0x0C)        # lea edx, [esp+12]      ; &temp
    a.call(TRANSLATE)                   # TranslateRStr
    a.db(0x8B, 0x54, 0x24, 0x0C)        # mov edx, [esp+12]      ; temp
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax, [esp+8]
    a.db(0x83, 0xC0, 0x1C)              # add eax, 0x1C          ; &log.Name
    a.call(LSTRASG)                     # log.Name := "Pestilence"
    a.db(0x8B, 0x45, 0x1C)              # mov eax, [ebp+0x1C]
    a.db(0x8A, 0x50, 0x12)              # mov dl, [eax+0x12]     ; army owner
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax, [esp+8]
    a.db(0x88, 0x50, 0x10)              # mov [eax+0x10], dl     ; log owner
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0x8B, 0x81); a.dd(STORMRSTR6)  # mov eax, [ecx+RStr[6]]
    a.db(0x8D, 0x54, 0x24, 0x0C)        # lea edx, [esp+12]      ; &temp
    a.call(TRANSLATE)                   # TranslateRStr (again, for the text body)
    a.db(0x8B, 0x54, 0x24, 0x0C)        # mov edx, [esp+12]
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax, [esp+8]
    a.db(0x8B, 0x40, 0x20)              # mov eax, [eax+0x20]    ; log strings obj
    a.db(0x8B, 0x08)                    # mov ecx, [eax]
    a.db(0xFF, 0x51, 0x34)              # call [ecx+0x34]        ; .Add(text)
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax, [esp+8]
    a.db(0xC7, 0x40, 0x24, 0x02, 0x00, 0x00, 0x00)  # mov dword [eax+0x24], 2
    crumb(0x58)                         # log strings/owner/type set
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax, [esp+8]
    a.db(0x8B, 0x40, 0x18)              # mov eax, [eax+0x18]    ; log unit snapshot obj
    a.db(0x8B, 0x55, 0x1C)              # mov edx, [ebp+0x1C]    ; army
    a.db(0xB1, 0xFF)                    # mov cl, 0xFF
    a.db(0x8B, 0x38)                    # mov edi, [eax]
    a.db(0xFF, 0x97); a.dd(0xC0)        # call [edi+0xC0]        ; snapshot army units
    crumb(0x60)                         # snapshot done
    a.label('no_seed')
    a.db(0x33, 0xFF)                    # xor edi, edi           ; unit index
    a.label('loop')
    crumb(0x70)                         # in unit loop
    a.db(0x8B, 0x45, 0x1C)              # mov eax, [ebp+0x1C]
    a.db(0x8B, 0x10)                    # mov edx, [eax]
    a.db(0xFF, 0x52, 0x54)              # call [edx+0x54]        ; Count
    a.db(0x3B, 0xF8)                    # cmp edi, eax
    a.db(0x0F, 0x8D)                    # jge rel32 done
    a.fix32.append((len(a.buf), 'done')); a.buf += b'\0\0\0\0'
    a.db(0x8B, 0x45, 0x1C)              # mov eax, [ebp+0x1C]
    a.db(0x8B, 0xD7)                    # mov edx, edi
    a.call(GETUNIT)                     # -> eax = TAbstractUnit
    a.db(0x50)                          # push eax               ; save unit
    a.db(0x8B, 0x10)                    # mov edx, [eax]
    a.db(0xFF, 0x92); a.dd(0xA4)        # call [edx+0xA4]        ; GetRace
    a.db(0x3C, RACE_UNDEAD)             # cmp al, 0x0B
    a.j8(0x74, 'undead')                # je  undead
    a.db(0x8B, 0x04, 0x24)              # mov eax, [esp]         ; unit
    a.db(0xBA); a.dd(AB_ANIMATED)       # mov edx, 0x81          ; Animated
    a.db(0x8B, 0x08)                    # mov ecx, [eax]
    a.db(0xFF, 0x91); a.dd(0x148)       # call [ecx+0x148]       ; GetAbilityEnabled
    a.db(0x84, 0xC0)                    # test al, al
    a.j8(0x75, 'undead')                # jnz undead
    a.db(0x84, 0xDB)                    # test bl, bl            ; living unit:
    a.j8(0x75, 'poison')                # jnz poison             ; wasteland -> poison
    a.label('bless')
    a.db(0x58)                          # pop eax                ; unit
    a.db(0xBA); a.dd(AB_BLESSING)       # mov edx, 0x63          ; Nature's Blessing
    a.db(0x8B, 0x08)                    # mov ecx, [eax]
    a.db(0xFF, 0x91); a.dd(0x94)        # call [ecx+0x94]        ; ExpandAbility (heal+bless)
    a.db(0x80, 0xCF, 0x01)              # or  bh, 1              ; blessed-any
    a.db(0x33, 0xC0)                    # xor eax, eax           ; dmg = 0 for the log
    a.j8(0xEB, 'log_dmg')               # jmp log_dmg
    a.label('undead')
    a.db(0x84, 0xDB)                    # test bl, bl            ; undead unit:
    a.j8(0x75, 'bless')                 # jnz bless              ; wasteland -> bless
    a.label('drop')
    a.db(0x58)                          # pop eax                ; discard unit
    a.db(0x33, 0xC0)                    # xor eax, eax           ; dmg = 0 for the log
    a.j8(0xEB, 'log_dmg')               # jmp log_dmg
    a.label('poison')
    a.db(0x8B, 0x45, 0x04)              # mov eax, [ebp+4]       ; field
    a.call(MAGICSHIELD)                 # GetMagicShieldActive
    a.db(0x84, 0xC0)                    # test al, al
    a.j8(0x75, 'drop')                  # jnz drop               ; shielded -> spare
    a.db(0x58)                          # pop eax                ; unit
    a.db(0xB2, STORM_PESTILENCE)        # mov dl, 6              ; Pestilence
    a.db(0x33, 0xC9)                    # xor ecx, ecx           ; caster = nil
    a.call(STORMDMG)                    # ExecuteStormDamage -> eax = damage
    a.db(0x80, 0xCF, 0x02)              # or  bh, 2              ; poison applied (SFX)
    a.db(0x85, 0xC0)                    # test eax, eax
    a.j8(0x74, 'log_dmg')               # jz  log_dmg
    a.db(0xC6, 0x44, 0x24, 0x03, 0x01)  # mov byte [esp+3], 1    ; anydmg
    a.label('log_dmg')
    # append (damage, damage-type) to the log's byte lists, army order
    a.db(0x8B, 0x54, 0x24, 0x08)        # mov edx, [esp+8]       ; log
    a.db(0x85, 0xD2)                    # test edx, edx
    a.j8(0x74, 'next')                  # jz  next               ; no log (non-wasteland)
    a.db(0x8B, 0xD0)                    # mov edx, eax           ; damage
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax, [esp+8]
    a.db(0x8B, 0x40, 0x28)              # mov eax, [eax+0x28]    ; dmg TByteList
    a.call(BYTEADD)                     # .Add(damage)
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0x8A, 0x91); a.dd(STORMDMGT6)  # mov dl, [ecx+DmgType[6]] ; 0x10 poison
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax, [esp+8]
    a.db(0x8B, 0x40, 0x2C)              # mov eax, [eax+0x2C]    ; type TByteList
    a.call(BYTEADD)                     # .Add(0x10)
    a.label('next')
    a.db(0x47)                          # inc edi
    a.db(0xE9)                          # jmp rel32 loop
    a.fix32.append((len(a.buf), 'loop')); a.buf += b'\0\0\0\0'
    a.label('done')
    crumb(0x80)                         # loop done
    # log wrap-up (wasteland only): popup if any damage, then free the log
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax, [esp+8]       ; log
    a.db(0x85, 0xC0)                    # test eax, eax
    a.j8(0x74, 'no_log')                # jz  no_log
    a.db(0x80, 0x7C, 0x24, 0x03, 0x00)  # cmp byte [esp+3], 0    ; anydmg?
    a.j8(0x74, 'free_log')              # jz  free_log
    a.call(VALIDGO)                     # ValidateGameOver(log)  (eax = log)
    crumb(0x90)                         # game-over checked
    a.db(0x8B, 0x4D, 0x1C)              # mov ecx, [ebp+0x1C]    ; army
    a.db(0x8A, 0x41, 0x14)              # mov al, [ecx+0x14]
    a.db(0x50)                          # push eax
    a.db(0x8A, 0x41, 0x15)              # mov al, [ecx+0x15]
    a.db(0x50)                          # push eax
    a.db(0x6A, 0x01)                    # push 1
    a.db(0x8A, 0x51, 0x12)              # mov dl, [ecx+0x12]
    a.db(0x8A, 0x49, 0x13)              # mov cl, [ecx+0x13]
    a.db(0x8B, 0x44, 0x24, 0x14)        # mov eax, [esp+0x14]    ; log (esp -12)
    a.call(DISTLOG)                     # DistributeLocationEventLog (popup)
    crumb(0xA0)                         # distributed
    a.label('free_log')
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax, [esp+8]       ; log
    a.db(0x8B, 0x10)                    # mov edx, [eax]
    a.db(0xFF, 0x52, 0x2C)              # call [edx+0x2C]        ; log.Free
    a.db(0x8D, 0x44, 0x24, 0x0C)        # lea eax, [esp+12]
    a.call(LSTRCLR)                     # release temp string
    crumb(0xB0)                         # log freed
    a.label('no_log')
    a.db(0x84, 0xDB)                    # test bl, bl
    a.db(0x0F, 0x84)                    # jz rel32 ret           ; non-wasteland: done
    a.fix32.append((len(a.buf), 'ret')); a.buf += b'\0\0\0\0'
    # --- v5: play APest from inside the cave (wasteland + any effect landed).
    #     Byte-for-byte replica of the vanilla sound gate @0x557A3E28..65:
    #     play if army owner == local player, else if the local player is
    #     Watching the spring's hex.  Before Validate so the army is intact.
    a.db(0x84, 0xFF)                    # test bh, bh            ; blessed or poisoned?
    a.db(0x0F, 0x84)                    # jz rel32 no_snd        ; all-shielded -> silent
    a.fix32.append((len(a.buf), 'no_snd')); a.buf += b'\0\0\0\0'
    a.db(0x8B, 0x45, 0x1C)              # mov eax, [ebp+0x1C]    ; army
    a.db(0x8A, 0x40, 0x12)              # mov al, [eax+0x12]     ; army owner
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0x8B, 0x91); a.dd(GAMEGLOBAL)  # mov edx, [ecx+GAMEGLOBAL]
    a.db(0x8B, 0x12)                    # mov edx, [edx]
    a.db(0x3A, 0x82); a.dd(0xA5)        # cmp al, [edx+0xA5]     ; == local player?
    a.j8(0x74, 'snd_play')              # je  snd_play
    a.db(0x8B, 0xC6)                    # mov eax, esi           ; spring
    a.db(0x8B, 0x10)                    # mov edx, [eax]
    a.db(0xFF, 0x52, 0x7C)              # call [edx+0x7C]        ; level
    a.db(0x50)                          # push eax
    a.db(0x6A, 0x00)                    # push 0
    a.db(0x8B, 0xC6)                    # mov eax, esi
    a.db(0x8B, 0x10)                    # mov edx, [eax]
    a.db(0xFF, 0x52, 0x78)              # call [edx+0x78]        ; y
    a.db(0x50)                          # push eax
    a.db(0x8B, 0xC6)                    # mov eax, esi
    a.db(0x8B, 0x10)                    # mov edx, [eax]
    a.db(0xFF, 0x52, 0x74)              # call [edx+0x74]        ; x
    a.db(0x8B, 0xD0)                    # mov edx, eax
    a.db(0x8B, 0x4C, 0x24, 0x10)        # mov ecx, [esp+0x10]    ; delta (esp -12)
    a.db(0x8B, 0x81); a.dd(GAMEGLOBAL)  # mov eax, [ecx+GAMEGLOBAL]
    a.db(0x8B, 0x00)                    # mov eax, [eax]
    a.db(0x59)                          # pop ecx                ; y
    a.call(WATCHING)                    # TAoWHSMap.Watching (ret 8, eats 0+level)
    a.db(0x84, 0xC0)                    # test al, al
    a.j8(0x74, 'snd_off')               # jz  snd_off
    a.label('snd_play')
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0xC6, 0x81); a.dd(SCRATCH + 3); a.db(0x02)  # diag: APest played
    a.db(0x8D, 0x81)                    # lea eax, [ecx+apest_txt] ; runtime addr
    a.fixabs = getattr(a, 'fixabs', []); a.fixabs.append((len(a.buf), 'apest_txt')); a.dd(0)
    a.call(PLAYSAMPLE)                  # Sound.PlaySample(eax=str)
    a.j8(0xEB, 'no_snd')                # jmp no_snd
    a.label('snd_off')
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0xC6, 0x81); a.dd(SCRATCH + 3); a.db(0x03)  # diag: gated off (not watching)
    a.label('no_snd')
    a.db(0x8B, 0x45, 0x1C)              # mov eax, [ebp+0x1C]
    a.call(VALIDATE)                    # TArmy.Validate (reap deaths)
    a.db(0x8B, 0x45, 0x1C)              # mov eax, [ebp+0x1C]
    a.call(ENDUPD)                      # TEChangeNotifyNode.EndUpdate
    crumb(0xC0)                         # validated + EndUpdate
    a.label('ret')
    # scratch := bit0 wasteland (SFX pick) | bit1 blessed (anim gate)
    a.db(0x8A, 0xC3)                    # mov al, bl
    a.db(0xF6, 0xC7, 0x01)              # test bh, 1
    a.j8(0x74, 'noscr')                 # jz  noscr
    a.db(0x0C, 0x02)                    # or  al, 2
    a.label('noscr')
    a.db(0x8B, 0x4C, 0x24, 0x04)        # mov ecx, [esp+4]       ; delta
    a.db(0x88, 0x81); a.dd(SCRATCH)     # mov [ecx+SCRATCH], al
    a.db(0xC6, 0x81); a.dd(SCRATCH + 1); a.db(0xFF)  # mov byte [ecx+SCRATCH+1], 0xFF (returned)
    a.db(0x8A, 0xC7)                    # mov al, bh             ; out-flags
    a.db(0x84, 0xDB)                    # test bl, bl            ; v5: wasteland ->
    a.j8(0x74, 'keep_al')               # jz  keep_al            ;   AL=0 skips the
    a.db(0x33, 0xC0)                    # xor eax, eax           ;   vanilla sound/anim
    a.label('keep_al')
    a.db(0x83, 0xC4, 0x10)              # add esp, 16            ; drop locals
    a.db(0x5D)                          # pop ebp
    a.db(0xC3)                          # ret
    # ---- APest AnsiString literal (Delphi const-string layout) --------------
    # (v5: referenced only by the in-cave snd_play; sfx_pick/anim_gate removed)
    a.dd(0xFFFFFFFF)                    # refcount -1 (constant)
    txt = b'SFX\\PLACES\\APEST.WAV'
    a.dd(len(txt))                      # length
    a.label('apest_txt')
    a.buf += txt + b'\x00'
    a.resolve()
    # absolute-displacement fixups (VA of a cave label, used in lea [reg+disp])
    for off, lab in getattr(a, 'fixabs', []):
        a.buf[off:off+4] = a.labels[lab].to_bytes(4, 'little')
    assert CAVE_BASE + len(a.buf) <= CAVE_LIMIT, "cave overflow: %d" % len(a.buf)
    return bytes(a.buf) + bytes(CAVE_LIMIT - CAVE_BASE - len(a.buf)), a.labels


def build_cave_bytes():
    return build_cave()[0]


def build_hook():
    a = Asm(HOOK)
    a.call('cave'); a.labels['cave'] = CAVE_BASE; a.resolve()
    buf = bytearray(a.buf)
    buf += bytes([0x84, 0xC0])                          # test al, al
    nxt = HOOK + len(buf) + 6
    buf += bytes([0x0F, 0x84]) + (EPILOGUE - nxt).to_bytes(4, 'little')   # jz epilogue
    nxt = HOOK + len(buf) + 2
    buf += bytes([0xEB, (HOOK_END - nxt) & 0xFF])       # jmp short L557A3E22
    buf += bytes([0x90]) * (HOOK_END - HOOK - len(buf)) # NOP fill
    assert len(buf) == len(OLD_HOOK)
    return bytes(buf)


def main():
    apply = "--apply" in sys.argv
    data = bytearray(open(TARGET, "rb").read())
    dirty = False
    ok = True

    cave, labels = build_cave()
    hook = build_hook()
    print("cave: %d bytes @0x%X (file 0x%X)" % (len(cave), CAVE_BASE, CAVE_BASE - VA2FILE))

    # cave range: acceptable prior states = untouched zeros, or an earlier
    # version of OUR cave (starts with push ebp; mov ebp,[esp+8] - only this
    # patch has ever written in the claimed range)
    off = CAVE_BASE - VA2FILE
    cur = bytes(data[off:off+len(cave)])
    prior_ours = cur[:5] == bytes.fromhex("558B6C2408")
    if cur == cave:
        print("  %-30s already applied" % "cave_spring")
    elif cur == bytes(len(cave)) or prior_ours:
        print("  %-30s ready @0x%X (%s)" % ("cave_spring", CAVE_BASE,
              "over prior version" if prior_ours else "fresh"))
        data[off:off+len(cave)] = cave
        dirty = True
    else:
        print("  %-30s MISMATCH @0x%X: %s..." % ("cave_spring", CAVE_BASE, cur[:16].hex()))
        ok = False

    def calls_our_cave(site_va, cur):
        # an earlier version of this patch: E8 rel32 targeting our claimed range
        if cur[0] != 0xE8:
            return False
        tgt = site_va + 5 + int.from_bytes(cur[1:5], 'little', signed=True)
        return CAVE_BASE <= tgt < CAVE_LIMIT

    for name, va, old, new in (
            ("hook ExecuteNaturesBlessing", HOOK, OLD_HOOK, hook),
            ("gate ArmyPlaced wasteland", GATE, GATE_OLD, GATE_NEW),
            ("sfx site (vanilla, v5)", SFX_SITE, SFX_OLD, SFX_OLD),
            ("anim site (vanilla, v5)", ANIM_SITE, ANIM_OLD, ANIM_OLD)):
        off = va - VA2FILE
        cur = bytes(data[off:off+len(old)])
        if cur == new:
            print("  %-30s already applied" % name)
        elif cur == old or calls_our_cave(va, cur):
            print("  %-30s ready @0x%X (%d bytes)" % (name, va, len(new)))
            data[off:off+len(new)] = new
            dirty = True
        else:
            print("  %-30s MISMATCH @0x%X: %s..." % (name, va, cur[:16].hex()))
            ok = False

    if not ok:
        print("ABORT: unexpected bytes, nothing written.")
        return 1
    if not dirty:
        print("All patches already applied; nothing to do.")
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply to write.")
        return 0

    if not os.path.exists(BACKUP):
        shutil.copy2(TARGET, BACKUP)
        print("Backup -> %s" % os.path.basename(BACKUP))
    with open(TARGET, "wb") as f:
        f.write(data)
    print("Written %s" % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
