#!/usr/bin/env python3
r"""
EXPERIMENT stage 2 (2026-11-16): in-place network reload with REAL network signalling + save transfer.
Replaces the marker-file rig (patch_resync_experiment_v1.py, same cave zone / hook sites / backups .bak_resyncx).
Still a test rig: the HOST is told to start by a trigger file (<game>\X\Save\resync.save, checked ~1x per second by
the DirectPlay host only); everything after that goes over the network and no longer needs a shared folder.

Protocol = raw DirectPlay user messages (TGDPlay.SendMessage, guaranteed) starting with the dword 'AXRS' + a type
byte.  They are caught by replacing the exe's import slot of NetworkE.TRemotePCC.DataReceived (0x45DA08; exe
DPlayMessage 0x4145C4 hands every packet to it while a map is active) with `dr_hook` at run time - our packets are
consumed there, everything else goes on to the real routine.
  'F'              host -> all: freeze now (token manager + AI stop; "Waiting for other players" panel)
  'C' total offset data   host -> all: the save file in 1024-byte pieces (16 per frame)
  'D'              client -> all: file complete and written to <game>\X\Save\resync.asg
  'G'              host -> all: go - reload (sent when every remote human answered 'D', or after ~60 s)
Host:  trigger -> 'F' -> freeze -> save resync.asg (engine VMT+0xAC) -> read it -> chunks -> wait for the 'D's -> 'G'
       -> reload ~2 s later -> ~4 s frozen on the new map -> run.
Client: 'F' -> freeze + panel; chunks -> buffer; complete -> write file -> 'D'; 'G' -> reload -> ~4 s -> run.
Reload itself = patch_resync_experiment_v1 v3 (keep the TRemotePCC, exe MainWin.LoadMapFile 0x454B70, cancel the
deferred DirectPlay disconnect [TGDPlay+0x1F1], restore the lobby-set map fields, ActivatePCC, exe StartGame).

Vars 0x558E9D20..0x558E9D48, path buffer 0x558E9D48..0x558E9DF0 (DATA tail).  Cave 0x55856700..0x55857000.
Dry run by default; --apply (also replaces an installed older rig build) / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP, EP_V2F = game_file("AoWEPACK.dll"), 0x55700C00
EXE, EXE_V2F = game_file("AoWx.exe"), 0x400C00
BAK = ".bak_resyncx"
CAVE, CAVE_END = 0x55856700, 0x55859000   # v2.20: grown by 0x1000 (0x55858000..0x55859000 was zero and unclaimed; grounded_melee starts at 0x55859000)
V = 0x558E9D20
V_CNT, V_INIT, V_FROZEN, V_STATE, V_TIMER, V_REALDR, V_RBUF, V_RSIZE, V_RGOT, V_DONES, V_NEED, V_FLAGS = \
    V, V + 8, V + 9, V + 10, V + 11, V + 12, V + 16, V + 20, V + 24, V + 28, V + 29, V + 30
V_ISHOST, V_SEQ, V_RSEQ = V + 31, V + 4, V + 5
# fake TSetupSettings seat record for the waiting dialog (exe reads only +0x18 race, +0x1C leader): base V+8
V_FAKE, V_FRACE, V_FLEAD = V + 8, V + 32, V + 36
X_SLOT_GETSETTINGS, X_SLOT_INDEXOFREMOTEID, GETSETTINGS, INDEXOFREMOTEID, GETPLAYERS = 0x45E8E8, 0x45E8E4, 0x557DF5F4, 0x557DF63C, 0x557544D0
BUF = 0x558E9D48
MAPG, ENGINE = 0x558FA040, 0x558FA048
FILEEXISTS, DELETEFILE, RELEASE, RELEASE_SLOT = 0x557015A4, 0x5570146C, 0x557035D4, 0x558FCAD8
CREATEFILE, READFILE, WRITEFILE, CLOSEHANDLE, SETFILEPTR, LOCALALLOC, LOCALFREE = \
    0x55701464, 0x55701494, 0x557014B4, 0x5570145C, 0x557014A4, 0x55701270, 0x55701278
SAVEGAME_VA = 0x55775884
X_MAINWIN, X_DPLAY, X_LOAD, X_START, X_CHAT1, X_CHAT2 = 0x45A420, 0x45A454, 0x454B70, 0x454D2C, 0x414424, 0x41444C
X_SLOT_SAVEGAME, X_MAPVAR, X_SLOT_DATARECEIVED, X_SENDMESSAGE = 0x45DDB0, 0x45DF7C, 0x45DA08, 0x40361C
X_PROGRESS, X_SETOVERPRI, X_SETGTEXT, X_GAUGEPOS, X_STR_PLEASEWAIT = 0x45A24C, 0x40312C, 0x403254, 0x403980, 0x414A60
# battle re-creation (v2.6): params copied from the pending TArmyCombatMoveTE ([combat+0x30], callback [combat+0x2C])
V_BATTLE = V + 6
BT0, BT1, BTN, BTIDS = 0x558E9DC0, 0x558E9DC4, 0x558E9DC8, 0x558E9DCC      # tail of the path buffer (paths < 120 chars)
COMBATEXECUTED, XYL_CLASSREF, XYL_CREATE, XYL_ADD, INTLIST_GET, TOBJ_FREE = 0x557496D4, 0x5570D9B0, 0x55701CB4, 0x55701CCC, 0x55702E94, 0x557010B8
GETFIELD, GETARMYHS, INDEXOFID, CREATEARMYMOVETE, GETTOKENCONTROL = 0x557020FC, 0x55771EB0, 0x55782FA4, 0x5574A1A0, 0x5570372C
# battle state snapshot (v2.8): blob = [0] current combat player, [1] count, [4] round, +8 records of 16 B
#   {unit id, x, y, facing, object flags +0x47, combat moves +0x5C, hit points}; sent as packet 'B'
V_PEND, V_SNAP = V + 7, 0x558E9DEC
CD_GETCOUNT, CD_GETOBJECTS, ISCLASS, CLS_COMBATUNIT, CU_GETHP, CU_SETHP, UHS_MOVETO, UHS_SETDIR =     0x55728BEC, 0x55728BF8, 0x557010C0, 0x55715A94, 0x55725064, 0x5572507C, 0x557843EC, 0x5578480C
# picture hold (v2.9): exe frame routine 0x452E50 skips draw+flip when its draw target [ebp-8] is nil (0x452F3A);
# stub2 adds "or X_HOLD set" -> the last presented picture stays on screen while we close/reload/re-open the battle.
X_HOLD, STUB2_VA, DRAW_SITE, DRAW_ORIG, DRAW_SKIP, DRAW_BACK = 0x62FF7F, 0x62FF40, 0x452F3A, bytes.fromhex("837df8000f848c010000"), 0x4530D0, 0x452F44
# v2.12: while the picture is held the minimap (Scanner.TScanner in AoWTools.dll, exe var 0x45A1C0 -> +0x5C) is not
# refreshed after the battle closes; the loading bar (exe 0x45540C) draws the whole window tree itself and the scanner
# would re-render from the map being destroyed (AV in TAoWMapField.GetExplored).  `reload` therefore clears the scanner's
# "valid" byte +0x2C (TScanner.Draw returns at once) for the duration of the load and restores it afterwards.
# v2.14: the AV actually comes from TScanner.SetSize (called in the load): the size changes (battle map -> world map, which a
# normal frame would already have done) and SetSize then runs DrawMap at once on a half-built map.  SetSize does nothing while
# [scanner+0x80] <= 0, so that dword is zeroed during the load too (the next normal frame resizes with a valid map).
X_SCANNERVAR = 0x45A1C0
SCANNER_RAD = 0x55772704     # TAbstractAoWHSMap.ScannerIconsChangedRad(eax=map, edx=x, ecx=y, push l, push radius)
# corpses + blood (v2.10): blob is 16 KB; [0x400] decor count, 0x404.. records of 28 B {type 1 corpse / 2 blood, x, y, -, 6 dwords};
# corpse dwords = unit GFX resource index, +0x14, +0x18, +0x1C, +0x20, +0x24; blood = +0x10, +0x14, +0x18.  Packets 'K' {count, records}.
# TCPCK is rebased: delta = [combat map VMT] - 0x413184 (AoWTC..TAoWCombatMap), class VMTs corpse 0x41261C / blood 0x41249C.
# v2.15 dead units: blob 32 KB.  0x400 DEAD (host order): count + 12 B {unit id, +0x45 player, +0x46 pos, +0x47 status, -, tactical dword +0x64}
#   -> packet 'X'.  0x800 KEEP (local): count + 12 B {unit id, TUnit ptr (AddRef'd before the battle is closed), new combat unit}.
#   Decor now at 0xC00, records 32 B (7th dword = id of the corpse's dead unit).  After the battle is re-created every machine
#   re-registers the dead units in host order (combat VMT+0x58 CreateCombatUnit, id = CreateUniqueCOID, free slot in the old party,
#   status destroyed, SetUnit VMT+0x134, TCombatData.AddObject, Activate VMT+0xBC) and links the corpses (+0xC) to them.
SNAP_SIZE, DEC_CNT, DEC_REC, DEC_MAX, DEC_PER = 0xA400, 0xC00, 0xC04, 900, 31
OFF_DEAD, OFF_KEEP, DEAD_MAX = 0x400, 0x800, 80
# v2.16 battle log: the re-created battle would start a new TCombatLogbook ([combat+0x18], refcount +8) -> the replay began at the
# reload.  Every machine keeps its old logbook (AddRef, ptr at blob+0x7FC) and swaps it into the new battle; so that the old
# recording still matches, every combat unit gets its OLD combat object id back (unit record +0xC, dead record +7) and the id
# counter [combat+0x10] is restored (blob header +2).  Unit record is now {id, x, y, facing, flags, moves:word, hp:word, coid, -}.
OFF_LOG = 0x7FC
# v2.17: closing the battle ran the battle-finished callback ([combat+0x2C] code / +0x30 self = TArmyCombatMoveTE.CombatExecuted,
# invoked by TCombat.UnlockExecuted 0x55728104 when word [combat+0x2E] != 0) -> an extra, truncated battle report in the event
# log (and in the host's save).  The callback is zeroed before our DestroyCombat.
LB_ADDREF, LB_RELEASE, CD_FINDID = 0x55728E80, 0x55728E88, 0x55728C68
CREATECOID, CD_FINDPOS, CD_ADDOBJECT = 0x557272D4, 0x55728CA4, 0x55728CE0
VMT_CMAP, VMT_CORPSE, VMT_BLOOD, TEOBJ_CREATE, GFX_GETINDEX, GFX_GET, RESG = 0x413184, 0x41261C, 0x41249C, 0x55703064, 0x55783BF0, 0x55783CF8, 0x558FA044
REC_SITE, REC_ORIG, REC_BACK = 0x55749924, bytes.fromhex("5356575583c4d4"), 0x5574992B   # TArmyCombatMoveTE.ExecuteCombat entry
DESTROYCOMBAT = 0x557787F8   # TAoWHSMap.DestroyCombat(eax=map): Deactivate + Finalize (tactical: restores AI PCC modes, ReleaseCombatMap -> exe view) + free
X_SYNCDLG = 0x45A550         # -> var -> TSynchronizeDlg form; +0x44 Dlg window, VMT+0x6C(dl) show/hide (OnShow fills names)
STUB_VA, STUB_FO = 0x62F7C8, 0x228600 + 0x7C8
HOOK_VA, HOOK_ORIG = 0x4530D0, bytes.fromhex("a17cdf4500")
RELOC_VA = 0x4530D1
NF_SITE, NF_ORIG, NF_BACK, NF_SKIP = 0x55777D0E, bytes.fromhex("83bb1c01000000"), 0x55777D15, 0x55777D36
MAGIC = 0x53525841          # 'AXRS'
# v2.18 real trigger (combat only): TPlayerControl.OutOfSync entry -> oos_hook.  In a battle the vanilla dialog + executer lock
# are skipped: the detecting machine freezes and raises V_OOS; a client then sends packet 'O' every poll until the host's 'F'
# arrives, the host starts the normal resync.  V_GRACE = polls after a resync during which OutOfSync calls are swallowed
# (stale sync tokens from before the reload).  Outside a battle the vanilla routine still runs (world-map dialog = next step).
V_OOS, V_GRACE, GRACE_POLLS = V + 1, V + 2, 20
# v2.19 notice: the waiting window's InfoMsg label ([TSynchronizeDlg form+0x58], TAOWLabel.SetGText thunk X_SETGTEXT(eax=label,
# edx=AnsiString)) reads OOS_TEXT while the rig shows it (restored to the vanilla text at t_run); in a battle the host waits
# NOTICE_POLLS polls (~0.5 s each) in state 5 before it closes the battle, so everybody reads it first.
OOS_TEXT, NOTICE_POLLS = "Out of Sync - restoring game", 4
# v2.20 world-map dialog.  OutOfSync outside a battle -> V_OOS 2 -> packet 'O' param 2 (every machine opens the dialog) ->
# a TPlayerConnectionEventLog (class cell CLS_CONN) with style 3 = the exe TMessageDlg's Yes/No/Cancel panel (form var MSGDLG:
# +0x44 Dlg, +0x8C YesBtn2, +0x90 NoBtn2, +0x94 CancelBtn2; live TAOWBaseButton (aowInt.dpl, NOT AoWInterface.dpl) text = AnsiString at +0x90, cache flag +0xA4).
# Captions are swapped while our dialog is up (old pointers kept at CAPS).  Click handlers = log VMT +0x80 Yes / +0x84 No /
# +0x7C Cancel: Yes -> host: V_OOS 6 (start the resync), client: V_OOS 5 (freeze + waiting window; re-opens the dialog if this
# machine becomes the DirectPlay host); No -> vanilla Yes (save prompt, exit); Cancel -> vanilla No (exit).  V_OOS 3 = open the
# dialog, 4 = dialog open.  The host's 'F' closes an open dialog on the clients.  V_DLG = our dialog is up.
V_DLG, CAPS, MSGDLG, CLS_CONN, MSGLOG_CREATE, EXITGAME = V + 3, 0x558E9DB4, 0x45B090, 0x5570CEE0, 0x557FE080, 0x557763F8
YES_SITE, YES_ORIG, YES_BACK = 0x55759B88, bytes.fromhex("53568bf033c9"), 0x55759B8E
NO_SITE, CANCEL_SITE, CANCEL_ORIG = 0x55759BF1, 0x557FE1B0, bytes.fromhex("c6402602b001c390")
DLG_TAIL = chr(13) + chr(10) + "Save - save the game and exit." + chr(13) + chr(10) + "Exit - exit without saving."
DLG_HOST = "Out of Sync"     # user 11/18: no explanations in the window, buttons only
DLG_CLI = "Out of Sync"


def astr(label, text):
    return chr(10).join(["        .align 4", "        .long 0xffffffff", "        .long %d" % len(text), "    %s:" % label, cstr(text)])


# v2.22 turn + temporary effects.
# * Turn: the re-created battle starts in the attacker's turn.  try_apply now calls combat VMT+0x78 = TCombat.NewTurn(dl=player)
#   with the snapshot's current player (header +0) when it differs, with the log flag ([combat+8] bit 4) cleared so the replay
#   gets no extra turn action; the unit moves / flags / HP are restored afterwards as before.
# * Temporary effects (unit enchantment abilities, duration modes 2/3) were stripped by TAbilityOwner.TriggerCombatDone when the
#   host closed the battle, i.e. before the save.  V_FLAGS bit 0x80 = "resync is closing / rebuilding the battle": while set,
#   TAbilityOwner.TriggerCombatDone (CDN_SITE) and TriggerNewCombatTurn (NCT_SITE; else the forced NewTurn would tick every
#   duration / regeneration / poison once more) return at once -> the effects stay on the units, travel in the save and keep
#   their remaining duration (ability data record +0xE turns left, +0xF ticking player).
# v2.23: the engine call alone left the tactical map on the attacker ([cmap+0xED] = current player is the map's own copy).
# The real hand-over is TAoWCombatMap.NewTurn(eax=cmap, dl=player) TCPCK 0x41BB30 (what TCEndTurnTE.Execute 0x407E58 calls):
# sets +0xED, round banner counter +0x134 (++ when player 0), calls combat VMT+0x78, ActivateTC, banner, AI start.
# TCPCK is rebased -> address = [cmap VMT] - VMT_CMAP + CMAP_NEWTURN.  Snapshot header +3 = low byte of [cmap+0x134].
CMAP_NEWTURN = 0x41BB30
# v2.24 walls / gates / structures: map objects on the fields (TCPCK): TCityWall VMT 0x405008, TCityWallDoor 0x4052AC (same
# SetHitPoints 0x405AE4, plain call (eax=obj, edx=hp); hp dword +0x20, damage stage +0x24, sound flag +0x2C, type +0x2D),
# TCombatStructure VMT 0x43258C (SetHitPoints 0x432930; hp +0x20, sound flag +0x24).  hp 0 = destroyed (sets the breach flag
# [combat data+0x4D] and a dust effect).  Decor records type 3 (wall/door) and 4 (structure): {type, x, y, -, hp}; apply lowers
# the hp of the same-class object on that field with the sound flag cleared.
# v2.25 fire: TCombatFire (TCPCK VMT 0x406B24, field object; Activate = VMT+0xE0 sets +0xC/+0x10 random animation phases,
# +0x14 = player whose turn it was lit in, +0x18 = 'just lit' flag).  Decor record type 5 {type, x, y, -, +0x14, +0x18}.
VMT_FIRE = 0x406B24
# v2.26 ooze / oil decals: TCOozeHS VMT 0x41279C (class cell 0x41275C, instance size 0xC = no own fields); Oil Spring's oil hex
# = runtime clone of that VMT in TCPCK BSS at 0x46CE00 (patch_oilspring_v1 VMTCLONE; built on first use, clone - 0x40 holds
# the self pointer -> nonzero once built).  Decor record type 6 (ooze) / 7 (oil): {type, x, y}.
VMT_OOZE, VMT_OIL = 0x41279C, 0x46CE00
# v2.27
# * Burning tick at the reload (user: 1-HP burning unit came back dead): the re-created battle's own first NewTurn ran the
#   abilities' new-combat-turn triggers (Burning damage, durations).  V_FLAGS bit 0x80 now stays set from the rig's
#   DestroyCombat until the battle restore has finished (cleared wherever X_HOLD is cleared), not just around single calls.
# * Explored state of the battle map (exploration sites came back blacked out): TAoWMapField +0x18 = explored bits per player
#   (GetExplored 0x55771BF4 / SetExplored 0x55771C04; +0x1A fog count).  Every machine keeps the low word of each field
#   locally in its snapshot blob at OFF_EXPL (dword count + words, blob grown to 0xA400) before its DestroyCombat and ORs it
#   back after the rebuild, then TAbstractAoWHSMap.MapChangedRad(eax=cmap, edx=x, ecx=y, push level, push radius) redraws.
OFF_EXPL, EXPL_MAX, MAPCHANGEDRAD = 0x8000, 4600, 0x55772544
VMT_WALL, VMT_DOOR, VMT_STRUCT, WALL_SETHP, STRUCT_SETHP = 0x405008, 0x4052AC, 0x43258C, 0x405AE4, 0x432930
NCT_SITE, NCT_ORIG, NCT_BACK = 0x5574FE68, bytes.fromhex("5356575583c4f8"), 0x5574FE6F
CDN_SITE, CDN_ORIG, CDN_BACK = 0x5574FEC4, bytes.fromhex("535657558bea"), 0x5574FECA
OOS_SITE, OOS_ORIG, OOS_BACK = 0x55754D14, bytes.fromhex("5356578bd8"), 0x55754D19
CHUNK, PER_FRAME = 1024, 16
# v2.30 connection lost, part A (drop while the game stays open).
# * Vanilla dialogs off: TPlayerControl.PlayerDisconnected (PD_SITE, queued the 'Connection to X lost' dialog) -> ret;
#   TPlayerControl.ConnectionLost (CL_SITE; session lost / message error) -> sets X_LOST; exe DPlayMessageTimeout (TMO_SITE) -> ret.
# * State block D = LocalAlloc'd, pointer at exe X_DPTR (our .xedt zone; exe never rebases).  drop_poll runs every poll in state 0:
#   healthy: keeps the session instance GUID (IDirectPlay GetSessionDesc), DirectPlay host sends 'H' every 8 polls (clients keep
#   the sender id = D_HOSTID), then looks for remote human seats (PCC record mode 1, player +0x44 == 0, +0x45 == 1) whose system
#   id is no longer in the TGDPlay player list ([gd+0x1C0], record +4 = DPID).
#   - host seat missing / session lost / test trigger X\Save\drop.save (non-host)  -> ROLE 2 'dropped': IDirectPlay Close, then
#     every 4 polls TGDPlay.GetSessions + JoinSession on the session with the kept GUID; joined -> all PCC records with the old id
#     get the new one, [pcc+0x10] too, ROLE 3: packet 'J' {seat, old id} every poll until the host's 'F'.
#   - otherwise ROLE 1 'stayer': frozen, dialog; the DirectPlay host clears JOINDISABLED (GetSessionDesc/SetSessionDesc) so the
#     session is joinable; 'J' re-maps the seat everywhere; host: nobody missing and Reload chosen -> re-lock, V_OOS 6 (resync).
#   - 30 polls after 'Wait'/'Reload' with the player still missing (host) or no session (dropped): second dialog.
D_ROLE, D_WAIT, D_MASK, D_TMR, D_HELLO, D_DLGK, D_HOSTID, D_GUIDOK, D_CONN, D_RETRY, D_GUID, D_OLDID = 0, 1, 2, 4, 6, 7, 8, 0xC, 0xD, 0xE, 0x10, 0x20
D_TM, D_TH, D_TI, D_DSIZE, D_DESC, D_TEXT, D_SIZE = 0x24, 0x28, 0x2C, 0x30, 0x40, 0x1D0, 0x400
X_DPTR, X_LOST, X_GETSESSIONS, X_JOINSESSION = 0x62FF60, 0x62FF64, 0x4035EC, 0x403604
GETNAME, LSTRCLR = 0x55752104, 0x55701140
# v2.31: TAoWHSMap.MouseMoved (reached from ResetSeatedPlayerView -> mouse Move during the load) took a junk field (0x446)
# from TMapContainer.GetField on the half-built map -> AV in GetExplored ("Exception occurred during UpdateFrame event",
# user 11/19 on a reconnect restore in combat).  The GetField call is wrapped: result < 0x10000 -> leave MouseMoved.
MM_SITE, MM_ORIG, MM_GETFIELD, MM_EXIT = 0x55777A95, bytes.fromhex("e862a6f8ff"), 0x557020FC, 0x55777B1C
PD_SITE, PD_ORIG = 0x55756644, bytes.fromhex("5356578bda8bf0")
CL_SITE, CL_ORIG = 0x55756670, bytes.fromhex("535633c9b201")
TMO_SITE = 0x41400C
# v2.40 connection lost, part B (the dropped player restarted the game and joins from the IPX/LAN session list).
# * After a start TSetupControl is Reset (inactive, settings empty) on every machine, so the vanilla lobby protocol cannot
#   serve a late joiner.  The joiner's lobby packages reach the host's TRemotePCC.DataReceived -> dr_pass now drops
#   non-rig packets whose sender is in no PCC record (`filt`).
# * Host (ROLE 1, seats missing): a DPID in the TGDPlay player list that is in no PCC record for 6 polls (an in-place
#   rejoiner sends 'J' at once and never gets that old) = lobby joiner -> lowest missing seat is re-mapped to it, 'M'
#   {old, new} tells the other machines.  Nobody missing -> the normal resync runs once the host chose Restore.
# * host_start sends 'S' (seat table: count, map params, per player {kind (+0xA7; 2 = no player), system id}) to all.
# * Joiner (no map): TSetupControl.DataReceived entry (SD_SITE) feeds rig packets to dr_hook; 'S' is kept (D_TAB, D_JOIN);
#   tick without a map (`lobby_tick`): file complete -> write + 'D'; 'G' -> join_start: MainWin.LoadMapFile(resync.asg),
#   map params, new TRemotePCC from the table (SendData event from the setup control), exe SetupControlStart (closes the
#   lobby, starts the map), TSetupControl.Reset, then V_STATE 2 like every other client ('P'/'L'/'R').
CAVE2, CAVE2_END = 0x558B8000, 0x558BA000
SD_SITE, SD_ORIG, SD_BACK = 0x557DFB14, bytes.fromhex("558bec6a00"), 0x557DFB19
D_NEWID, D_JOIN, D_NEWCNT, D_TAB = 0x34, 0x38, 0x39, 0x300
PCC_CLASS_SLOT, PCC_CREATE, PCC_SETUP, PCC_SETMODE, PCC_SETSYSID = 0x558FCAF8, 0x5570360C, 0x55703624, 0x55703614, 0x5570361C
SC_RESET, X_SCSTART = 0x557E1274, 0x413A64
# v2.41 turn status: player+0x2C = turn ended (TPlayer.SetEndTurn 0x55752D00, eax=player, dl); every load re-activates all AI
# players (StartLoadedMapEx) so an AI that had ended would plan again.  host_start (send_table) collects the mask of ended
# players, packet 'T' {mask}; every machine applies it in t_run (still frozen): SetEndTurn + TAIExecuter.DeactivatePlayer
# ([map+0x128], idx; 0x55734564) for AI players (kind +0xA7 != 0).  NewTurn re-activates them as usual.
D_ENDOK, D_ENDMASK, SETENDTURN, AI_DEACTIVATE = 0x3A, 0x3C, 0x55752D00, 0x55734564
X_TOOLBAR = 0x45A0CC   # exe var -> form with the End Turn button at +0x5C (click handler 0x4574AC sets +0x13C; TheMapEndTurn 0x44EE80 only clears it)
# v2.50 host crash.  The session is created with MIGRATEHOST, so DirectPlay itself moves its host flag ([gd+0x1EF], DPSYS_HOST)
# to a remaining player; the rig's authority simply follows that flag.  New rule for a machine that sees seats missing
# (`classify`): NOT alone (another player still in the TGDPlay list) -> stay (ROLE 1); alone -> the old hello-host of a
# 2-human game stays, everybody else is the dropped side (ROLE 2: Close, look for the session GUID, rejoin).  The DP host
# in ROLE 1 sends the hello every 8 polls and, when it has just become the host (D_HOSTID != own id), re-opens its dialog
# with the host captions.  ROLE 2 that finds no session for 30 polls re-hosts (`takeover`): TGDPlay.CreateSession (exe thunk
# 0x4035DC, eax=gd; needs [gd+0x1ED]), own seat re-mapped to the new id, ROLE 1 as host -> the crashed host joins from
# the session list (part B).
# Lobby rejoiner: packet M whose new id is the local id (no map) -> D_JSHOW -> lobby_tick hides the lobby window
# ([[0x45A30C]]+0xA0) and shows the loading panel (exe progress form [[0x45A24C]]: +0x44/+0x50 labels, +0x58 gauge,
# +0x54 window) with Rejoining game / Waiting for host; MainWin.LoadMapFile reuses and closes it.
X_CREATESESSION, X_SETUPFORM, D_JSHOW = 0x4035DC, 0x45A30C, 0x3B
# v2.51 no lobby for a rejoiner.  set_lock stamps the session description's dwUser1 (desc+0x40) with MAGIC = 'a game is
# running here'.  lobby_tick (every frame without a map) keeps X_RJMASK = bit i set when session-list entry i
# ([gd+0x1B8] records, desc at rec+4 -> dwUser1 rec+0x44) carries the stamp.  Exe JoinBtnClick 0x42AFA8 shows the lobby
# with `call 0x410BD8` at JOIN_SITE (esi = clicked list index): redirected to STUB3 (our .xedt zone) which skips that
# call when the bit is set.  In a session without a map lobby_tick reads the description once (D_NEWCNT as 'checked')
# and raises D_JSHOW on the stamp -> loading panel at once.  The 'M' route stays as the fallback.
X_RJMASK, STUB3_VA, JOIN_SITE, JOIN_TARGET = 0x62FF78, 0x62FF68, 0x42B033, 0x410BD8
# 2026-11-21 manual restore (host Ctrl+R, raised by AoWxLog.dll: X_MAN = MAN_MARK, then V_OOS = 6).  The 'F' packet now
# carries X_MAN in its argument byte (it was undefined before), every machine stores it and show_wait then says
# "Host initiated a manual restore" instead of the Out of Sync text; t_run clears it.  X_MAN = exe byte 0x62FF7C (free
# byte of our .xedt zone, zero in the file).
X_MAN, MAN_MARK, MAN_TEXT = 0x62FF7C, 0x4D, "Host initiated manual restore"
C2_NAMES = ["lobby_tick", "host_new", "send_table", "h_s", "h_m", "filt", "sd_hook", "h_t", "end_apply", "classify", "takeover"]
C1_NAMES = ["remap", "send_raw", "mkpath", "write_file", "dr_done", "dr_hook", "dr_pass2", "s_asg", "send_ctl", "close_dlg", "open_dlg", "drop_text", "hide_wait", "scan_seats", "get_desc"]
REJOIN_POLLS = 30


def cstr(s):
    return "        .byte " + ", ".join("0x%02x" % b for b in s.encode("latin1") + b"\0")


def build_cave(c2=None):
    if c2 is None: c2 = dict.fromkeys(C2_NAMES, CAVE2)
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
    tick:
        call td
    td:
        pop ebx
        sub ebx, td
        cmp dword ptr [ebx + {V_REALDR:#x}], 0
        jne t1
        mov eax, [{X_SLOT_DATARECEIVED:#x}]
        mov [ebx + {V_REALDR:#x}], eax
        mov eax, ebx
        add eax, dr_hook
        mov [{X_SLOT_DATARECEIVED:#x}], eax
        mov eax, ebx
        add eax, gs_hook
        mov [{X_SLOT_GETSETTINGS:#x}], eax
        mov eax, ebx
        add eax, ir_hook
        mov [{X_SLOT_INDEXOFREMOTEID:#x}], eax
    t1:
        mov esi, [ebx + {MAPG:#x}]
        test esi, esi
        jz t_nomap
        test byte ptr [ebx + {V_FLAGS:#x}], 1
        jz t2
        and byte ptr [ebx + {V_FLAGS:#x}], 0xfe
        call close_dlg
        call show_wait
    t2:
        test byte ptr [ebx + {V_FLAGS:#x}], 2
        jz t3
        and byte ptr [ebx + {V_FLAGS:#x}], 0xfd
        call write_file
    t3:
        test byte ptr [ebx + {V_FLAGS:#x}], 4
        jz t4
        and byte ptr [ebx + {V_FLAGS:#x}], 0xfb
        mov byte ptr [ebx + {V_STATE:#x}], 1
        mov byte ptr [ebx + {V_TIMER:#x}], 0
    t4:
        test byte ptr [ebx + {V_FLAGS:#x}], 8
        jz t4b
        and byte ptr [ebx + {V_FLAGS:#x}], 0xf7
        mov al, 0x4c
        mov ah, [ebx + {V_RSEQ:#x}]
        call send_ctl
    t4b:
        test byte ptr [ebx + {V_FLAGS:#x}], 0x10
        jz t4c
        and byte ptr [ebx + {V_FLAGS:#x}], 0xef
        cmp byte ptr [ebx + {V_STATE:#x}], 2
        jne t4c
        jmp t_run
    t4c:
        cmp byte ptr [ebx + {V_STATE:#x}], 3
        jne t5
        call send_chunks
        jmp t_out
    t5:
        inc byte ptr [ebx + {V_CNT:#x}]
        test byte ptr [ebx + {V_CNT:#x}], 0x0f
        jnz t_out
        mov al, [ebx + {V_STATE:#x}]
        cmp al, 1
        je t_s1
        cmp al, 2
        je t_s2
        cmp al, 4
        je t_s4
        cmp al, 5
        je t_s5
        cmp byte ptr [ebx + {V_PEND:#x}], 0
        je t5n
        call try_apply
    t5n:
        call drop_poll
        cmp byte ptr [ebx + {V_GRACE:#x}], 0
        je t5g
        dec byte ptr [ebx + {V_GRACE:#x}]
    t5g:
        cmp byte ptr [ebx + {V_OOS:#x}], 0
        je t5f
        cmp byte ptr [ebx + {V_OOS:#x}], 1
        jne t5w2
        call is_host
        test al, al
        jnz t5h
        mov ax, 0x014f
        call send_ctl
        call show_wait
        jmp t_out
    t5h:
        mov byte ptr [ebx + {V_OOS:#x}], 0
        jmp t5trig
    t5w2:
        cmp byte ptr [ebx + {V_OOS:#x}], 2
        jne t5w3
        mov ax, 0x024f
        call send_ctl
        mov byte ptr [ebx + {V_OOS:#x}], 3
        jmp t_out
    t5w3:
        cmp byte ptr [ebx + {V_OOS:#x}], 3
        jne t5w5
        call open_dlg
        mov byte ptr [ebx + {V_OOS:#x}], 4
        jmp t_out
    t5w5:
        cmp byte ptr [ebx + {V_OOS:#x}], 5
        jne t5w6
        call is_host
        test al, al
        jz t_out
        mov byte ptr [ebx + {V_FROZEN:#x}], 0
        call hide_wait
        lea edx, [ebx + s_wait]
        call wait_text
        mov byte ptr [ebx + {V_OOS:#x}], 3
        jmp t_out
    t5w6:
        cmp byte ptr [ebx + {V_OOS:#x}], 6
        jne t_out
        mov byte ptr [ebx + {V_OOS:#x}], 0
        jmp t5trig
    t5f:
        jmp t_out               ; release build (1.37.434): the resync.save test trigger is gone
    t5trig:
        mov eax, [ebx + {MAPG:#x}]
        cmp dword ptr [eax + 0x120], 0
        je t_hs
        mov byte ptr [ebx + {V_FROZEN:#x}], 1
        mov al, 0x46
        mov ah, [{X_MAN:#x}]
        call send_ctl
        call show_wait
        mov byte ptr [ebx + {V_STATE:#x}], 5
        mov byte ptr [ebx + {V_TIMER:#x}], 0
        jmp t_out
    t_s5:
        inc byte ptr [ebx + {V_TIMER:#x}]
        cmp byte ptr [ebx + {V_TIMER:#x}], {NOTICE_POLLS}
        jb t_out
        mov byte ptr [{X_HOLD:#x}], 1
    t_hs:
        call host_start
        jmp t_out
    t_s1:
        inc byte ptr [ebx + {V_TIMER:#x}]
        cmp byte ptr [ebx + {V_TIMER:#x}], 1
        jne t_s1b
        mov eax, [ebx + {MAPG:#x}]
        cmp dword ptr [eax + 0x120], 0
        je t_out
        mov byte ptr [{X_HOLD:#x}], 1
        mov edi, [ebx + {V_SNAP:#x}]
        test edi, edi
        jz t_s1k
        call keep_dead
        call snap_expl
    t_s1k:
        call hide_wait
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x120]
        mov dword ptr [eax + 0x2c], 0
        or byte ptr [ebx + {V_FLAGS:#x}], 0x80
        mov eax, [ebx + {MAPG:#x}]
        mov ecx, ebx
        add ecx, {DESTROYCOMBAT:#x}
        call ecx
        call show_wait
        jmp t_out
    t_s1b:
        cmp byte ptr [ebx + {V_TIMER:#x}], 3
        jb t_out
        mov byte ptr [ebx + {V_STATE:#x}], 2
        mov byte ptr [ebx + {V_TIMER:#x}], 0
        mov byte ptr [ebx + {V_DONES:#x}], 0
        and byte ptr [ebx + {V_FLAGS:#x}], 0xe7
        cmp byte ptr [ebx + {V_ISHOST:#x}], 0
        je t_s1c
        cmp byte ptr [ebx + {V_NEED:#x}], 0
        je t_s1c
        mov byte ptr [ebx + {V_DONES:#x}], 0xff
    t_s1c:
        mov edx, ebx
        add edx, s_asg
        call mkpath
        test eax, eax
        jz t_out
        push eax
        call hide_wait
        pop eax
        call reload
        call show_wait
        jmp t_out
    t_s2:
        inc byte ptr [ebx + {V_TIMER:#x}]
        cmp byte ptr [ebx + {V_ISHOST:#x}], 0
        jne t_s2h
        cmp byte ptr [ebx + {V_TIMER:#x}], 80
        jb t_out
        jmp t_run
    t_s2h:
        cmp byte ptr [ebx + {V_TIMER:#x}], 60
        jae t_s2r
        mov al, [ebx + {V_DONES:#x}]
        cmp al, 0xff
        je t_s2p
        cmp al, [ebx + {V_NEED:#x}]
        jae t_s2r
    t_s2p:
        inc byte ptr [ebx + {V_SEQ:#x}]
        mov byte ptr [ebx + {V_DONES:#x}], 0
        mov al, 0x50
        mov ah, [ebx + {V_SEQ:#x}]
        call send_ctl
        jmp t_out
    t_s2r:
        mov al, 0x52
        call send_ctl
    t_run:
        call {c2['end_apply']:#x}
        mov byte ptr [ebx + {V_GRACE:#x}], {GRACE_POLLS}
        mov byte ptr [ebx + {V_OOS:#x}], 0
        mov byte ptr [ebx + {V_FROZEN:#x}], 0
        mov byte ptr [ebx + {V_STATE:#x}], 0
        mov byte ptr [{X_MAN:#x}], 0
        mov eax, [{X_DPTR:#x}]
        test eax, eax
        jz t_runc
        mov byte ptr [eax + {D_CONN}], 0
    t_runc:
        call hide_wait
        lea edx, [ebx + s_wait]
        call wait_text
        cmp byte ptr [ebx + {V_PEND:#x}], 0
        jne t_runb
        mov byte ptr [{X_HOLD:#x}], 0
        and byte ptr [ebx + {V_FLAGS:#x}], 0x7f
    t_runb:
        cmp byte ptr [ebx + {V_ISHOST:#x}], 0
        je t_out
        cmp byte ptr [ebx + {V_BATTLE:#x}], 0
        je t_out
        mov byte ptr [ebx + {V_BATTLE:#x}], 0
        call restart_battle
        jmp t_out
    t_s4:
        inc byte ptr [ebx + {V_TIMER:#x}]
        mov al, [ebx + {V_DONES:#x}]
        cmp al, [ebx + {V_NEED:#x}]
        jae t_go
        cmp byte ptr [ebx + {V_TIMER:#x}], 240
        jb t_out
    t_go:
        mov al, 0x47
        call send_ctl
        mov byte ptr [ebx + {V_STATE:#x}], 1
        mov byte ptr [ebx + {V_TIMER:#x}], 0
    t_out:
        ret
    t_nomap:
        jmp {c2['lobby_tick']:#x}

    drop_poll:
        pushad
        mov ebp, [{X_DPTR:#x}]
        test ebp, ebp
        jnz dq_have
        push {D_SIZE}
        push 0x40
        call {LOCALALLOC:#x}
        test eax, eax
        jz dq_out
        mov [{X_DPTR:#x}], eax
        mov ebp, eax
    dq_have:
        mov esi, [ebx + {MAPG:#x}]
        cmp byte ptr [esi + 0x13a], 0
        je dq_out
        cmp byte ptr [esi + 0x1c0], 0
        jne dq_out
        test byte ptr [esi + 0x3c], 4
        jz dq_out
        mov eax, [esi + 0x240]
        test eax, eax
        jz dq_out
        cmp dword ptr [eax + 0x1c], 0
        je dq_out
        mov edi, [{X_DPLAY:#x}]
        mov edi, [edi]
        mov edi, [edi + 0x44]
        cmp dword ptr [edi + 0x1b0], 0
        je dq_out
        cmp word ptr [edi + 0x1f0], 0
        jne dq_out
        mov al, [ebp + {D_ROLE}]
        cmp al, 1
        je dq_stay
        cmp al, 2
        je dq_drop
        cmp al, 3
        je dq_rej
        cmp byte ptr [ebx + {V_FROZEN:#x}], 0
        jne dq_out
        cmp byte ptr [ebx + {V_OOS:#x}], 0
        jne dq_out
        cmp byte ptr [ebx + {V_DLG:#x}], 0
        jne dq_out
        cmp byte ptr [edi + 0x1ee], 0
        jne dq_h1
        cmp byte ptr [{X_LOST:#x}], 0
        je dq_out
        jmp dq_todrop
    dq_h1:
        mov byte ptr [{X_LOST:#x}], 0
        cmp byte ptr [ebp + {D_GUIDOK}], 0
        jne dq_h2
        call get_desc
        test eax, eax
        jnz dq_h2
        mov eax, [ebp + {D_DESC + 8}]
        mov [ebp + {D_GUID}], eax
        mov eax, [ebp + {D_DESC + 12}]
        mov [ebp + {D_GUID + 4}], eax
        mov eax, [ebp + {D_DESC + 16}]
        mov [ebp + {D_GUID + 8}], eax
        mov eax, [ebp + {D_DESC + 20}]
        mov [ebp + {D_GUID + 12}], eax
        mov byte ptr [ebp + {D_GUIDOK}], 1
    dq_h2:
        cmp byte ptr [edi + 0x1ef], 0
        je dq_h3
        test byte ptr [ebp + {D_HELLO}], 7
        jnz dq_h2b
        mov eax, [edi + 0x1f4]
        mov [ebp + {D_HOSTID}], eax
        mov ax, 0x0048
        call send_ctl
    dq_h2b:
        inc byte ptr [ebp + {D_HELLO}]
        jmp dq_h4
    dq_h3:                      ; release build (1.37.434): the drop.save test trigger + rejoin hold are gone
    dq_h4:
        call scan_seats
        test eax, eax
        jz dq_out
        call {c2['classify']:#x}
        test edx, edx
        jnz dq_todrop
        mov [ebp + {D_MASK}], ax
        mov byte ptr [ebp + {D_ROLE}], 1
        mov byte ptr [ebp + {D_WAIT}], 0
        mov byte ptr [ebx + {V_FROZEN:#x}], 1
        mov byte ptr [ebx + {V_OOS:#x}], 4
        xor edx, edx
        call set_lock
        mov byte ptr [ebp + {D_DLGK}], 1
        call drop_text
        call open_dlg
        jmp dq_out

    dq_stay:
        cmp byte ptr [edi + 0x1ee], 0
        je dq_todrop_s
        call scan_seats
        call {c2['classify']:#x}
        test edx, edx
        jnz dq_todrop_s
        mov [ebp + {D_MASK}], ax
        call dq_dismissed
        cmp byte ptr [edi + 0x1ef], 0
        je dq_out
        test eax, eax
        jz dq_s_all
        call {c2['host_new']:#x}
        inc byte ptr [ebp + {D_HELLO}]
        test byte ptr [ebp + {D_HELLO}], 7
        jnz dq_tmr
        xor edx, edx
        call set_lock
        jmp dq_tmr
    dq_s_all:
        cmp byte ptr [ebp + {D_WAIT}], 0
        jne dq_s_go
        cmp byte ptr [ebp + {D_DLGK}], 2
        jne dq_out
        call close_dlg
    dq_s_go:
        mov dl, 1
        call set_lock
        mov dword ptr [ebp], 0
        mov dword ptr [ebp + 4], 0
        mov byte ptr [ebp + {D_CONN}], 1
        mov byte ptr [ebx + {V_OOS:#x}], 6
        jmp dq_out
    dq_tmr:
        mov esi, [ebx + {MAPG:#x}]
        cmp byte ptr [ebp + {D_WAIT}], 0
        je dq_out
        inc word ptr [ebp + {D_TMR}]
        cmp word ptr [ebp + {D_TMR}], {REJOIN_POLLS}
        jne dq_out
        mov byte ptr [ebp + {D_WAIT}], 0
        mov byte ptr [ebp + {D_DLGK}], 2
        call hide_wait
        call drop_text
        call open_dlg
        jmp dq_out

    dq_todrop_s:
        call close_dlg
    dq_todrop:
        mov byte ptr [{X_LOST:#x}], 0
        mov byte ptr [ebp + {D_ROLE}], 2
        mov byte ptr [ebp + {D_WAIT}], 0
        mov word ptr [ebp + {D_TMR}], 0
        mov byte ptr [ebp + {D_RETRY}], 0
        mov byte ptr [ebx + {V_FROZEN:#x}], 1
        mov byte ptr [ebx + {V_OOS:#x}], 4
        mov eax, [esi + 0x240]
        mov eax, [eax + 0x1c]
        mov eax, [eax + 0x10]
        mov [ebp + {D_OLDID}], eax
        mov eax, [edi + 0x1b0]
        push eax
        mov eax, [eax]
        call dword ptr [eax + 0x10]
        mov byte ptr [edi + 0x1ee], 0
        mov byte ptr [edi + 0x1ef], 0
        mov byte ptr [edi + 0x1ed], 1
        mov byte ptr [ebp + {D_DLGK}], 1
        call hide_wait
        call drop_text
        call open_dlg
        jmp dq_out

    dq_drop:
        call dq_dismissed
        inc byte ptr [ebp + {D_RETRY}]
        call {c2['takeover']:#x}
        test al, al
        jnz dq_out
        test byte ptr [ebp + {D_RETRY}], 3
        jnz dq_tmr
        mov byte ptr [edi + 0x1ed], 1
        mov dl, 1
        mov eax, edi
        mov ecx, {X_GETSESSIONS:#x}
        call ecx
        mov ecx, [edi + 0x1b8]
        test ecx, ecx
        jz dq_tmr
        mov edx, [ecx + 8]
        mov ecx, [ecx + 4]
    dq_d_l:
        dec edx
        js dq_tmr
        cmp byte ptr [ebp + {D_GUIDOK}], 0
        je dq_d_join
        mov eax, [ecx + edx*4]
        mov esi, [eax + 0xc]
        cmp esi, [ebp + {D_GUID}]
        jne dq_d_l
        mov esi, [eax + 0x10]
        cmp esi, [ebp + {D_GUID + 4}]
        jne dq_d_l
        mov esi, [eax + 0x14]
        cmp esi, [ebp + {D_GUID + 8}]
        jne dq_d_l
        mov esi, [eax + 0x18]
        cmp esi, [ebp + {D_GUID + 12}]
        jne dq_d_l
    dq_d_join:
        mov eax, edi
        mov ecx, {X_JOINSESSION:#x}
        call ecx
        test eax, eax
        jnz dq_tmr
        cmp byte ptr [edi + 0x1ee], 1
        jne dq_tmr
        mov esi, [ebx + {MAPG:#x}]
        mov eax, [edi + 0x1f4]
        mov edx, [ebp + {D_OLDID}]
        call remap
        mov ecx, [esi + 0x240]
        mov ecx, [ecx + 0x1c]
        mov [ecx + 0x10], eax
        mov byte ptr [ebp + {D_ROLE}], 3
        mov dword ptr [ebp + {D_HOSTID}], 0
        call close_dlg
        mov byte ptr [ebp + {D_DLGK}], 0
        call show_wait
        jmp dq_out

    dq_rej:
        cmp byte ptr [edi + 0x1ee], 0
        je dq_todrop
        sub esp, 12
        mov dword ptr [esp], {MAGIC:#x}
        mov byte ptr [esp + 4], 0x4a
        mov al, [esi + 0xa5]
        mov [esp + 5], al
        mov eax, [ebp + {D_OLDID}]
        mov [esp + 6], eax
        mov edx, esp
        mov ecx, 10
        call send_raw
        add esp, 12
    dq_out:
        popad
        ret

    dq_dismissed:
        cmp byte ptr [ebx + {V_DLG:#x}], 0
        jne dqd_out
        cmp byte ptr [ebp + {D_WAIT}], 0
        jne dqd_out
        mov byte ptr [ebp + {D_WAIT}], 1
        mov word ptr [ebp + {D_TMR}], 0
        mov byte ptr [ebp + {D_DLGK}], 0
    dqd_out:
        ret

    scan_seats:
        mov dword ptr [ebp + {D_TM}], 0
        mov dword ptr [ebp + {D_TH}], 0
        mov eax, [esi + 0x240]
        mov eax, [eax + 0x1c]
        test eax, eax
        jz ss_out
        mov eax, [eax + 0xc]
        mov eax, [eax + 8]
        mov ecx, [eax + 8]
        cmp ecx, 16
        jbe ss_c
        mov ecx, 16
    ss_c:
        mov [ebp + {D_TI}], ecx
    ss_l:
        dec dword ptr [ebp + {D_TI}]
        js ss_out
        mov eax, [esi + 0x240]
        mov eax, [eax + 0x1c]
        mov eax, [eax + 0xc]
        mov eax, [eax + 8]
        mov eax, [eax + 4]
        mov ecx, [ebp + {D_TI}]
        mov eax, [eax + ecx*4]
        cmp byte ptr [eax + 8], 1
        jne ss_l
        mov ecx, [eax + 0xc]
        test ecx, ecx
        jz ss_l
        push ecx
        mov edx, [ebp + {D_TI}]
        mov eax, [esi + 0x140]
        call {GETPLAYERS:#x}
        pop ecx
        test eax, eax
        jz ss_l
        cmp byte ptr [eax + 0x44], 0
        jne ss_l
        cmp byte ptr [eax + 0x45], 1
        jne ss_l
        mov eax, [edi + 0x1c0]
        test eax, eax
        jz ss_miss
        mov edx, [eax + 8]
        mov eax, [eax + 4]
    ss_g:
        dec edx
        js ss_miss
        push eax
        mov eax, [eax + edx*4]
        cmp [eax + 4], ecx
        pop eax
        jne ss_g
        jmp ss_l
    ss_miss:
        mov eax, [ebp + {D_TI}]
        bts dword ptr [ebp + {D_TM}], eax
        cmp ecx, [ebp + {D_HOSTID}]
        jne ss_l
        mov dword ptr [ebp + {D_TH}], 1
        jmp ss_l
    ss_out:
        mov eax, [ebp + {D_TM}]
        mov edx, [ebp + {D_TH}]
        ret

    remap:
        test edx, edx
        jz rm_out
        push edi
        mov ecx, [esi + 0x240]
        test ecx, ecx
        jz rm_o2
        mov ecx, [ecx + 0x1c]
        test ecx, ecx
        jz rm_o2
        mov ecx, [ecx + 0xc]
        mov ecx, [ecx + 8]
        mov edi, [ecx + 8]
        mov ecx, [ecx + 4]
    rm_l:
        dec edi
        js rm_o2
        push ecx
        mov ecx, [ecx + edi*4]
        cmp [ecx + 0xc], edx
        jne rm_n
        mov [ecx + 0xc], eax
    rm_n:
        pop ecx
        jmp rm_l
    rm_o2:
        pop edi
    rm_out:
        ret

    get_desc:
        lea eax, [ebp + {D_DSIZE}]
        mov dword ptr [eax], 0x180
        push eax
        lea eax, [ebp + {D_DESC}]
        push eax
        mov eax, [edi + 0x1b0]
        push eax
        mov eax, [eax]
        call dword ptr [eax + 0x58]
        ret

    set_lock:
        pushad
        mov ebx, edx
        call get_desc
        test eax, eax
        jnz sl_out
        lea eax, [ebp + {D_DESC}]
        mov dword ptr [eax + 0x40], {MAGIC:#x}
        and dword ptr [eax + 4], 0xffffffdf
        test bl, bl
        jz sl_set
        or dword ptr [eax + 4], 0x20
    sl_set:
        push 0
        push eax
        mov eax, [edi + 0x1b0]
        push eax
        mov eax, [eax]
        call dword ptr [eax + 0x7c]
    sl_out:
        popad
        ret

    drop_text:
        pushad
        lea edi, [ebp + {D_TEXT}]
        cmp byte ptr [ebp + {D_ROLE}], 2
        jne dt_stay
        lea esi, [ebx + s_t_recon]
        cmp byte ptr [ebp + {D_DLGK}], 2
        jne dt_cat
        lea esi, [ebx + s_t_norecon]
        jmp dt_cat
    dt_stay:
        cmp byte ptr [ebp + {D_DLGK}], 2
        je dt_name
        lea esi, [ebx + s_t_conn]
        call tcat
    dt_name:
        movzx eax, word ptr [ebp + {D_MASK}]
        bsf edx, eax
        jz dt_noname
        mov eax, [esp + 4]
        mov eax, [eax + 0x140]
        call {GETPLAYERS:#x}
        test eax, eax
        jz dt_noname
        push 0
        mov edx, esp
        call {GETNAME:#x}
        mov esi, [esp]
        test esi, esi
        jz dt_nfree
        mov ecx, [esi - 4]
        cmp ecx, 40
        jbe dt_ncp
        mov ecx, 40
    dt_ncp:
        rep movsb
    dt_nfree:
        mov eax, esp
        call {LSTRCLR:#x}
        add esp, 4
        jmp dt_sfx
    dt_noname:
        lea esi, [ebx + s_t_player]
        call tcat
    dt_sfx:
        lea esi, [ebx + s_t_lost]
        cmp byte ptr [ebp + {D_DLGK}], 2
        jne dt_cat
        lea esi, [ebx + s_t_norejoin]
    dt_cat:
        call tcat
        mov byte ptr [edi], 0
        lea eax, [ebp + {D_TEXT}]
        sub edi, eax
        mov [eax - 4], edi
        mov dword ptr [eax - 8], 0xffffffff
        popad
        ret
    tcat:
        lodsb
        test al, al
        jz tc_out
        stosb
        jmp tcat
    tc_out:
        ret

    d_reset:
        push ecx
        mov ecx, [{X_DPTR:#x}]
        test ecx, ecx
        jz dr_x
        cmp byte ptr [ecx + {D_ROLE}], 0
        je dr_x
        mov dword ptr [ecx], 0
        mov dword ptr [ecx + 4], 0
        mov byte ptr [ecx + {D_CONN}], 1
    dr_x:
        pop ecx
        ret

    mm_hook:
        push dword ptr [esp + 4]
        call {MM_GETFIELD:#x}
        cmp eax, 0x10000
        jae mm_ok
        add esp, 8
        jmp {MM_EXIT:#x}
    mm_ok:
        ret 4
    pd_hook:
        ret
    cl_hook:
        mov byte ptr [{X_LOST:#x}], 1
        ret

    host_start:
        mov byte ptr [ebx + {V_ISHOST:#x}], 1
        mov al, 0x46
        mov ah, [{X_MAN:#x}]
        call send_ctl
        mov byte ptr [ebx + {V_FROZEN:#x}], 1
        mov eax, [ebx + {MAPG:#x}]
        mov byte ptr [ebx + {V_BATTLE:#x}], 0
        cmp dword ptr [eax + 0x120], 0
        je hs_nocombat
        cmp dword ptr [ebx + {BTN:#x}], 0
        setne byte ptr [ebx + {V_BATTLE:#x}]
        je hs_nosnap
        call snap_battle
        mov edi, [ebx + {V_SNAP:#x}]
        test edi, edi
        jz hs_nosnap
        call snap_expl
    hs_nosnap:
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x120]
        mov dword ptr [eax + 0x2c], 0
        or byte ptr [ebx + {V_FLAGS:#x}], 0x80
        mov eax, [ebx + {MAPG:#x}]
        mov ecx, ebx
        add ecx, {DESTROYCOMBAT:#x}
        call ecx
    hs_nocombat:
        call {c2['send_table']:#x}
        call show_wait
        mov edx, ebx
        add edx, s_asg
        call mkpath
        test eax, eax
        jz hs_fail
        call dosave
        mov edx, ebx
        add edx, s_asg
        call mkpath
        call read_file
        mov dword ptr [ebx + {V_RGOT:#x}], 0
        mov byte ptr [ebx + {V_DONES:#x}], 0
        call count_remote
        mov [ebx + {V_NEED:#x}], al
        cmp dword ptr [ebx + {V_RSIZE:#x}], 0
        je hs_fail
        mov byte ptr [ebx + {V_TIMER:#x}], 0
        mov byte ptr [ebx + {V_STATE:#x}], 3
        cmp byte ptr [ebx + {V_NEED:#x}], 0
        jne hs_ret
        call free_rbuf
        mov byte ptr [ebx + {V_STATE:#x}], 1
    hs_ret:
        ret
    hs_fail:
        mov byte ptr [{X_HOLD:#x}], 0
        mov byte ptr [{X_MAN:#x}], 0
        and byte ptr [ebx + {V_FLAGS:#x}], 0x7f
        mov byte ptr [ebx + {V_FROZEN:#x}], 0
        mov byte ptr [ebx + {V_STATE:#x}], 0
        call hide_wait
        ret

    rec_hook:
        pushad
        call rh_d
    rh_d:
        pop ebx
        sub ebx, rh_d
        mov esi, eax
        mov dword ptr [ebx + {BTN:#x}], 0
        cmp byte ptr [esi + 0x39], 1
        je cb_out
        cmp dword ptr [esi + 0x18], 1
        jne cb_out
        mov edx, [esi + 0x14]
        cmp dword ptr [edx + 8], 2
        jb cb_out
        mov edx, [edx + 4]
        mov ecx, [edx]
        mov [ebx + {BT0:#x}], ecx
        mov ecx, [edx + 4]
        mov [ebx + {BT1:#x}], ecx
        mov edx, [esi + 0x20]
        mov ebp, [edx + 8]
        cmp ebp, 8
        ja cb_out
        test ebp, ebp
        jz cb_out
        xor edi, edi
    cb_l:
        mov edx, edi
        mov eax, [esi + 0x20]
        call {INTLIST_GET:#x}
        mov [ebx + edi*4 + {BTIDS:#x}], eax
        inc edi
        cmp edi, ebp
        jb cb_l
        mov [ebx + {BTN:#x}], ebp
    cb_out:
        popad
        push ebx
        push esi
        push edi
        push ebp
        add esp, -0x2c
        jmp {REC_BACK:#x}

    restart_battle:
        push ebp
        mov ebp, esp
        sub esp, 8
        push esi
        push edi
        movsx eax, byte ptr [ebx + {BT1 + 2:#x}]
        push eax
        movsx ecx, byte ptr [ebx + {BT1 + 1:#x}]
        movsx edx, byte ptr [ebx + {BT1:#x}]
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x10]
        call {GETFIELD:#x}
        test eax, eax
        jz rb_out
        call {GETARMYHS:#x}
        test eax, eax
        jz rb_out
        mov [ebp - 8], eax
        xor edi, edi
        xor esi, esi
    rb_l:
        mov edx, [ebx + esi*4 + {BTIDS:#x}]
        mov eax, [ebp - 8]
        mov eax, [eax + 0x1c]
        call {INDEXOFID:#x}
        cmp eax, 7
        ja rb_n
        bts edi, eax
    rb_n:
        inc esi
        cmp esi, [ebx + {BTN:#x}]
        jb rb_l
        test edi, edi
        jz rb_out
        mov dl, 1
        mov eax, [ebx + {XYL_CLASSREF:#x}]
        call {XYL_CREATE:#x}
        mov [ebp - 4], eax
        mov edx, [ebx + {BT0:#x}]
        call {XYL_ADD:#x}
        mov edx, [ebx + {BT1:#x}]
        and edx, 0xffffff
        mov eax, [ebp - 4]
        call {XYL_ADD:#x}
        push 1
        push 0
        mov ecx, [ebp - 4]
        mov edx, edi
        mov eax, [ebp - 8]
        call {CREATEARMYMOVETE:#x}
        mov esi, eax
        test esi, esi
        jz rb_free
        mov byte ptr [esi + 0x39], 2
        mov eax, [ebx + {MAPG:#x}]
        movsx edx, byte ptr [eax + 0xa5]
        mov eax, [eax + 0x23c]
        call {GETTOKENCONTROL:#x}
        mov edx, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x10]
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x2c]
    rb_free:
        mov eax, [ebp - 4]
        call {TOBJ_FREE:#x}
    rb_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret

    free_snap:
        mov byte ptr [ebx + {V_PEND:#x}], 0
        mov eax, [ebx + {V_SNAP:#x}]
        test eax, eax
        jz fs_out
        push esi
        push edi
        mov edi, eax
        mov esi, [edi + {OFF_KEEP:#x}]
        cmp esi, {DEAD_MAX}
        ja fs_k2
    fs_k:
        dec esi
        js fs_k2
        imul eax, esi, 12
        mov eax, [edi + eax + {OFF_KEEP + 8:#x}]
        test eax, eax
        jz fs_k
        mov edx, [eax]
        call dword ptr [edx + 0x2c]
        jmp fs_k
    fs_k2:
        mov eax, [edi + {OFF_LOG:#x}]
        test eax, eax
        jz fs_k3
        call {LB_RELEASE:#x}
    fs_k3:
        mov eax, edi
        pop edi
        pop esi
        push eax
        call {LOCALFREE:#x}
        mov dword ptr [ebx + {V_SNAP:#x}], 0
    fs_out:
        ret

    snap_battle:
        pushad
        call free_snap
        push {SNAP_SIZE}
        push 0x40
        call {LOCALALLOC:#x}
        test eax, eax
        jz sn_out
        mov [ebx + {V_SNAP:#x}], eax
        mov edi, eax
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x11c]
        test eax, eax
        jz sn_nocm
        mov cl, [eax + 0x134]
        mov [edi + 3], cl
    sn_nocm:
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x120]
        mov cl, [eax + 0x10]
        mov [edi + 2], cl
        mov ebp, [eax + 0xc]
        mov al, [ebp + 0x31]
        mov [edi], al
        mov eax, [ebp + 0x44]
        mov [edi + 4], eax
        xor esi, esi
    sn_l:
        mov eax, ebp
        call {CD_GETCOUNT:#x}
        cmp esi, eax
        jae sn_done
        mov eax, ebp
        mov edx, esi
        call {CD_GETOBJECTS:#x}
        inc esi
        push eax
        lea edx, [ebx + {CLS_COMBATUNIT:#x}]
        call {ISCLASS:#x}
        pop ecx
        test al, al
        jz sn_l
        mov edx, [ecx + 0x4c]
        test edx, edx
        jz sn_l
        mov eax, [ecx + 0x60]
        test eax, eax
        jz sn_l
        mov eax, [eax + 4]
        test eax, eax
        jz sn_l
        movzx edx, byte ptr [edi + 1]
        cmp edx, 60
        jae sn_done
        shl edx, 4
        lea edx, [edi + edx + 8]
        push ecx
        mov ecx, [ecx + 0x4c]
        mov ecx, [ecx + 0x18]
        mov [edx], ecx
        pop ecx
        mov ax, [eax + 0x10]
        mov [edx + 4], ax
        mov eax, [ecx + 0x60]
        mov al, [eax + 0x14]
        mov [edx + 6], al
        mov al, [ecx + 0x47]
        mov [edx + 7], al
        mov eax, [ecx + 0x5c]
        mov [edx + 8], ax
        mov al, [ecx + 0xc]
        mov [edx + 0xc], al
        push edx
        mov eax, ecx
        call {CU_GETHP:#x}
        pop edx
        mov [edx + 0xa], ax
        inc byte ptr [edi + 1]
        jmp sn_l
    sn_done:
        call keep_dead
        call snap_decor
        movzx ecx, byte ptr [edi + 1]
        shl ecx, 4
        add ecx, 8
        sub esp, 1040
        mov dword ptr [esp], {MAGIC:#x}
        mov byte ptr [esp + 4], 0x42
        mov edx, ecx
        mov esi, edi
        lea edi, [esp + 5]
        rep movsb
        lea ecx, [edx + 5]
        mov edx, esp
        call send_raw
        mov edi, [ebx + {V_SNAP:#x}]
        mov ecx, [edi + {OFF_DEAD:#x}]
        imul ecx, ecx, 12
        add ecx, 4
        mov dword ptr [esp], {MAGIC:#x}
        mov byte ptr [esp + 4], 0x58
        lea esi, [edi + {OFF_DEAD:#x}]
        push edi
        lea edi, [esp + 9]
        mov edx, ecx
        rep movsb
        pop edi
        lea ecx, [edx + 5]
        mov edx, esp
        call send_raw
        xor ebp, ebp
    sk_l:
        mov eax, [edi + {DEC_CNT:#x}]
        sub eax, ebp
        jle sk_done
        cmp eax, {DEC_PER}
        jbe sk_n
        mov eax, {DEC_PER}
    sk_n:
        mov dword ptr [esp], {MAGIC:#x}
        mov byte ptr [esp + 4], 0x4b
        mov [esp + 5], al
        imul ecx, eax, 32
        imul esi, ebp, 32
        lea esi, [edi + esi + {DEC_REC:#x}]
        push edi
        lea edi, [esp + 10]
        mov edx, ecx
        rep movsb
        pop edi
        add ebp, eax
        lea ecx, [edx + 6]
        mov edx, esp
        call send_raw
        jmp sk_l
    sk_done:
        add esp, 1040
        mov byte ptr [ebx + {V_PEND:#x}], 1
        mov byte ptr [ebx + {V_TIMER:#x}], 0
    sn_out:
        popad
        ret

    try_apply:
        pushad
        cmp byte ptr [ebx + {V_FROZEN:#x}], 0
        jne ta_out
        mov eax, [ebx + {MAPG:#x}]
        mov ecx, [eax + 0x120]
        test ecx, ecx
        jz ta_wait
        cmp dword ptr [eax + 0x11c], 0
        je ta_wait
        mov dl, [ecx + 8]
        and dl, 3
        cmp dl, 3
        jne ta_wait
        cmp byte ptr [ebx + {V_PEND:#x}], 2
        je ta_go
        mov byte ptr [ebx + {V_PEND:#x}], 2
        jmp ta_out
    ta_go:
        mov ebp, [ecx + 0xc]
        mov edi, [ebx + {V_SNAP:#x}]
        test edi, edi
        jz ta_end
        mov al, [edi]
        cmp al, [ebp + 0x31]
        je ta_turn
        push dword ptr [ecx + 8]
        push ecx
        and byte ptr [ecx + 8], 0xfb
        or byte ptr [ebx + {V_FLAGS:#x}], 0x80
        movzx edx, al
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x11c]
        mov ecx, [eax]
        add ecx, {CMAP_NEWTURN - VMT_CMAP:#x}
        call ecx
        pop ecx
        pop eax
        and al, 4
        or [ecx + 8], al
    ta_turn:
        movzx edx, byte ptr [edi + 3]
        test edx, edx
        jz ta_rnd
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x11c]
        mov [eax + 0x134], edx
    ta_rnd:
        mov eax, [edi + 4]
        mov [ebp + 0x44], eax
        xor esi, esi
    ta_l:
        mov eax, ebp
        call {CD_GETCOUNT:#x}
        cmp esi, eax
        jae ta_end
        mov eax, ebp
        mov edx, esi
        call {CD_GETOBJECTS:#x}
        inc esi
        push eax
        lea edx, [ebx + {CLS_COMBATUNIT:#x}]
        call {ISCLASS:#x}
        pop ecx
        test al, al
        jz ta_l
        mov edx, [ecx + 0x4c]
        test edx, edx
        jz ta_l
        mov edx, [edx + 0x18]
        movzx eax, byte ptr [edi + 1]
        shl eax, 4
    ta_f:
        sub eax, 16
        js ta_l
        cmp [edi + eax + 8], edx
        jne ta_f
        lea edx, [edi + eax + 8]
        push esi
        push ebp
        mov esi, ecx
        mov ebp, edx
        mov eax, [esi + 0x60]
        test eax, eax
        jz ta_n
        mov ecx, [eax + 4]
        test ecx, ecx
        jz ta_n
        mov cx, [ecx + 0x10]
        cmp cx, [ebp + 4]
        je ta_same
        mov eax, [eax + 4]
        call scan_field
        push 0
        movsx ecx, byte ptr [ebp + 5]
        movsx edx, byte ptr [ebp + 4]
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x11c]
        mov eax, [eax + 0x10]
        call {GETFIELD:#x}
        test eax, eax
        jz ta_same
        push eax
        mov edx, eax
        mov eax, [esi + 0x60]
        call {UHS_MOVETO:#x}
        pop eax
        call scan_field
    ta_same:
        mov eax, [esi + 0x60]
        mov dl, [ebp + 6]
        call {UHS_SETDIR:#x}
        mov al, [ebp + 7]
        mov [esi + 0x47], al
        mov al, [ebp + 0xc]
        mov [esi + 0xc], al
        movzx eax, word ptr [ebp + 8]
        mov [esi + 0x5c], eax
        mov eax, esi
        call {CU_GETHP:#x}
        movzx eax, al
        movzx edx, byte ptr [ebp + 0xa]
        cmp eax, edx
        je ta_n
        mov eax, esi
        call {CU_SETHP:#x}
    ta_n:
        pop ebp
        pop esi
        jmp ta_l
    ta_wait:
        inc byte ptr [ebx + {V_TIMER:#x}]
        cmp byte ptr [ebx + {V_TIMER:#x}], 24
        jb ta_out
        jmp ta_end2
    ta_end:
        mov edi, [ebx + {V_SNAP:#x}]
        test edi, edi
        jz ta_end2
        call apply_dead
        call apply_decor
        call apply_expl
    ta_end2:
        mov byte ptr [{X_HOLD:#x}], 0
        and byte ptr [ebx + {V_FLAGS:#x}], 0x7f
        call free_snap
    ta_out:
        popad
        ret

    keep_dead:
        pushad
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x120]
        test eax, eax
        jz kd_out
        mov ebp, [eax + 0xc]
        cmp dword ptr [edi + {OFF_LOG:#x}], 0
        jne kd_nolog
        mov eax, [eax + 0x18]
        test eax, eax
        jz kd_nolog
        mov [edi + {OFF_LOG:#x}], eax
        call {LB_ADDREF:#x}
    kd_nolog:
        xor esi, esi
    kd_l:
        mov eax, ebp
        call {CD_GETCOUNT:#x}
        cmp esi, eax
        jae kd_out
        mov eax, ebp
        mov edx, esi
        call {CD_GETOBJECTS:#x}
        inc esi
        push eax
        lea edx, [ebx + {CLS_COMBATUNIT:#x}]
        call {ISCLASS:#x}
        pop ecx
        test al, al
        jz kd_l
        test byte ptr [ecx + 0x47], 1
        jz kd_l
        mov edx, [ecx + 0x4c]
        test edx, edx
        jz kd_l
        mov eax, [edi + {OFF_KEEP:#x}]
        cmp eax, {DEAD_MAX}
        jae kd_out
        inc dword ptr [edi + {OFF_KEEP:#x}]
        imul eax, eax, 12
        lea eax, [edi + eax + {OFF_KEEP + 4:#x}]
        push ecx
        mov ecx, [edx + 0x18]
        mov [eax], ecx
        mov [eax + 4], edx
        mov dword ptr [eax + 8], 0
        pop ecx
        cmp byte ptr [ebx + {V_ISHOST:#x}], 0
        je kd_ref
        mov eax, [edi + {OFF_DEAD:#x}]
        inc dword ptr [edi + {OFF_DEAD:#x}]
        imul eax, eax, 12
        lea eax, [edi + eax + {OFF_DEAD + 4:#x}]
        push edx
        mov edx, [edx + 0x18]
        mov [eax], edx
        mov dl, [ecx + 0x45]
        mov [eax + 4], dl
        mov dl, [ecx + 0x46]
        mov [eax + 5], dl
        mov dl, [ecx + 0x47]
        mov [eax + 6], dl
        mov dl, [ecx + 0xc]
        mov [eax + 7], dl
        mov edx, [ecx + 0x64]
        mov [eax + 8], edx
        pop edx
    kd_ref:
        mov eax, edx
        mov edx, [eax]
        call dword ptr [edx + 0x28]
        jmp kd_l
    kd_out:
        popad
        ret

    find_cu:
        push ecx
        push edx
        mov ecx, [edi + {OFF_KEEP:#x}]
        cmp ecx, {DEAD_MAX}
        ja fc_no
        lea edx, [edi + {OFF_KEEP + 4:#x}]
    fc_l:
        dec ecx
        js fc_no
        cmp [edx], eax
        jne fc_n
        cmp dword ptr [edx + 8], 0
        jne fc_y
    fc_n:
        add edx, 12
        jmp fc_l
    fc_y:
        mov eax, [edx + 8]
        pop edx
        pop ecx
        ret
    fc_no:
        xor eax, eax
        pop edx
        pop ecx
        ret

    apply_dead:
        push ebp
        mov ebp, esp
        sub esp, 0x10
        push esi
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x120]
        test eax, eax
        jz ap_ret
        mov [ebp - 4], eax
        mov ecx, [edi + {OFF_LOG:#x}]
        test ecx, ecx
        jz ap_nolog
        mov edx, [eax + 0x18]
        mov [eax + 0x18], ecx
        mov dword ptr [edi + {OFF_LOG:#x}], 0
        mov eax, edx
        test eax, eax
        jz ap_nolog
        call {LB_RELEASE:#x}
    ap_nolog:
        cmp dword ptr [edi + {OFF_DEAD:#x}], {DEAD_MAX}
        ja ap_out
        cmp dword ptr [edi + {OFF_KEEP:#x}], {DEAD_MAX}
        ja ap_out
        mov dword ptr [ebp - 8], 0
    ap_l:
        mov eax, [ebp - 8]
        cmp eax, [edi + {OFF_DEAD:#x}]
        jae ap_out
        inc dword ptr [ebp - 8]
        imul eax, eax, 12
        lea esi, [edi + eax + {OFF_DEAD + 4:#x}]
        movzx eax, byte ptr [esi + 7]
        mov [ebp - 0xc], eax
        mov edx, eax
        mov eax, [ebp - 4]
        mov eax, [eax + 0xc]
        call {CD_FINDID:#x}
        test eax, eax
        jnz ap_l
        mov ecx, [edi + {OFF_KEEP:#x}]
        lea edx, [edi + {OFF_KEEP + 4:#x}]
    ap_k:
        dec ecx
        js ap_l
        mov eax, [esi]
        cmp [edx], eax
        jne ap_kn
        cmp dword ptr [edx + 4], 0
        jne ap_found
    ap_kn:
        add edx, 12
        jmp ap_k
    ap_found:
        mov [ebp - 0x10], edx
        mov cl, [esi + 5]
        and cl, 0xf0
        xor ch, ch
    ap_s:
        mov dl, cl
        or dl, ch
        push ecx
        mov eax, [ebp - 4]
        mov eax, [eax + 0xc]
        call {CD_FINDPOS:#x}
        pop ecx
        test eax, eax
        jz ap_slot
        inc ch
        cmp ch, 16
        jb ap_s
        jmp ap_l
    ap_slot:
        or cl, ch
        push ecx
        mov eax, [ebp - 4]
        mov edx, [eax]
        call dword ptr [edx + 0x58]
        pop ecx
        mov [eax + 0x46], cl
        mov cl, [ebp - 0xc]
        mov [eax + 0xc], cl
        mov cl, [esi + 4]
        mov [eax + 0x45], cl
        mov byte ptr [eax + 0x47], 1
        push eax
        mov edx, [ebp - 0x10]
        mov edx, [edx + 4]
        mov ecx, [eax]
        call dword ptr [ecx + 0x134]
        pop eax
        mov ecx, [esi + 8]
        mov [eax + 0x64], ecx
        push eax
        mov edx, eax
        mov eax, [ebp - 4]
        mov eax, [eax + 0xc]
        call {CD_ADDOBJECT:#x}
        mov eax, [esp]
        mov edx, [ebp - 4]
        mov ecx, [eax]
        call dword ptr [ecx + 0xbc]
        pop eax
        mov cl, [esi + 6]
        or cl, 5
        mov [eax + 0x47], cl
        mov edx, [ebp - 0x10]
        mov [edx + 8], eax
        mov eax, [edx + 4]
        mov dword ptr [edx + 4], 0
        mov edx, [eax]
        call dword ptr [edx + 0x2c]
        jmp ap_l
    ap_out:
        mov eax, [ebp - 4]
        movzx ecx, byte ptr [edi + 2]
        cmp ecx, [eax + 0x10]
        jbe ap_ret
        mov [eax + 0x10], ecx
    ap_ret:
        pop esi
        mov esp, ebp
        pop ebp
        ret

    snap_decor:
        push ebp
        mov ebp, esp
        sub esp, 0x10
        push esi
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x11c]
        test eax, eax
        jz sd_out
        mov ecx, [eax]
        sub ecx, {VMT_CMAP:#x}
        test cx, cx
        jnz sd_out
        mov [ebp - 4], ecx
        mov eax, [eax + 0x10]
        mov eax, [eax + 8]
        mov eax, [eax + 4]
        mov eax, [eax]
        mov ecx, [eax + 0x14]
        mov [ebp - 8], ecx
        mov ecx, [eax + 0x28]
        mov [ebp - 0xc], ecx
        mov esi, [eax + 0x2c]
    sd_f:
        cmp dword ptr [ebp - 8], 0
        jle sd_out
        movzx ecx, byte ptr [esi + 0xd]
    sd_c:
        dec ecx
        js sd_nf
        mov edx, [esi + 8]
        mov edx, [edx + ecx*4]
        mov eax, [edx]
        sub eax, [ebp - 4]
        cmp eax, {VMT_CORPSE:#x}
        je sd_corpse
        cmp eax, {VMT_FIRE:#x}
        je sd_fire
        cmp eax, {VMT_OOZE:#x}
        je sd_ooze
        cmp eax, {VMT_OIL:#x}
        je sd_oil
        cmp eax, {VMT_WALL:#x}
        je sd_wall
        cmp eax, {VMT_DOOR:#x}
        je sd_wall
        cmp eax, {VMT_STRUCT:#x}
        je sd_struct
        cmp eax, {VMT_BLOOD:#x}
        jne sd_c
        call sd_rec
        test eax, eax
        jz sd_out
        mov byte ptr [eax], 2
        push ecx
        mov ecx, [edx + 0x10]
        mov [eax + 4], ecx
        mov ecx, [edx + 0x14]
        mov [eax + 8], ecx
        mov ecx, [edx + 0x18]
        mov [eax + 0xc], ecx
        pop ecx
        jmp sd_c
    sd_ooze:
        call sd_rec
        test eax, eax
        jz sd_out
        mov byte ptr [eax], 6
        jmp sd_c
    sd_oil:
        call sd_rec
        test eax, eax
        jz sd_out
        mov byte ptr [eax], 7
        jmp sd_c
    sd_fire:
        call sd_rec
        test eax, eax
        jz sd_out
        mov byte ptr [eax], 5
        push ecx
        mov ecx, [edx + 0x14]
        mov [eax + 4], ecx
        movzx ecx, byte ptr [edx + 0x18]
        mov [eax + 8], ecx
        pop ecx
        jmp sd_c
    sd_wall:
        call sd_rec
        test eax, eax
        jz sd_out
        mov byte ptr [eax], 3
        jmp sd_hp
    sd_struct:
        call sd_rec
        test eax, eax
        jz sd_out
        mov byte ptr [eax], 4
    sd_hp:
        push ecx
        mov ecx, [edx + 0x20]
        mov [eax + 4], ecx
        pop ecx
        jmp sd_c
    sd_corpse:
        call sd_rec
        test eax, eax
        jz sd_out
        mov byte ptr [eax], 1
        push ecx
        push eax
        push edx
        mov eax, [edx + 0x10]
        test eax, eax
        jnz sd_cg
        or eax, 0xffffffff
        jmp sd_ci
    sd_cg:
        call {GFX_GETINDEX:#x}
    sd_ci:
        mov ecx, eax
        pop edx
        pop eax
        mov [eax + 4], ecx
        mov ecx, [edx + 0x14]
        mov [eax + 8], ecx
        mov ecx, [edx + 0x18]
        mov [eax + 0xc], ecx
        mov ecx, [edx + 0x1c]
        mov [eax + 0x10], ecx
        mov ecx, [edx + 0x20]
        mov [eax + 0x14], ecx
        mov ecx, [edx + 0x24]
        mov [eax + 0x18], ecx
        mov ecx, [edx + 0xc]
        test ecx, ecx
        jz sd_cid
        mov ecx, [ecx + 0x4c]
        test ecx, ecx
        jz sd_cid
        mov ecx, [ecx + 0x18]
    sd_cid:
        mov [eax + 0x1c], ecx
        pop ecx
        jmp sd_c
    sd_nf:
        add esi, [ebp - 0xc]
        dec dword ptr [ebp - 8]
        jmp sd_f
    sd_out:
        pop esi
        mov esp, ebp
        pop ebp
        ret
    sd_rec:
        mov eax, [edi + {DEC_CNT:#x}]
        cmp eax, {DEC_MAX}
        jb sd_r2
        xor eax, eax
        ret
    sd_r2:
        inc dword ptr [edi + {DEC_CNT:#x}]
        imul eax, eax, 32
        lea eax, [edi + eax + {DEC_REC:#x}]
        push ecx
        mov cx, [esi + 0x10]
        mov [eax + 1], cx
        pop ecx
        ret

    apply_decor:
        push ebp
        mov ebp, esp
        sub esp, 0x10
        push esi
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x11c]
        test eax, eax
        jz ad_out
        mov ecx, [eax]
        sub ecx, {VMT_CMAP:#x}
        test cx, cx
        jnz ad_out
        mov [ebp - 4], ecx
        mov eax, [eax + 0x10]
        mov [ebp - 8], eax
        mov eax, [edi + {DEC_CNT:#x}]
        cmp eax, {DEC_MAX}
        ja ad_out
        mov [ebp - 0xc], eax
    ad_l:
        dec dword ptr [ebp - 0xc]
        js ad_out
        imul eax, [ebp - 0xc], 32
        lea eax, [edi + eax + {DEC_REC:#x}]
        mov [ebp - 0x10], eax
        push 0
        movsx ecx, byte ptr [eax + 2]
        movsx edx, byte ptr [eax + 1]
        mov eax, [ebp - 8]
        call {GETFIELD:#x}
        test eax, eax
        jz ad_l
        mov ecx, eax
        mov eax, [ebp - 0x10]
        cmp byte ptr [eax], 2
        je ad_blood
        cmp byte ptr [eax], 6
        je ad_ooze
        cmp byte ptr [eax], 7
        je ad_oil
        cmp byte ptr [eax], 5
        je ad_fire
        cmp byte ptr [eax], 3
        jae ad_wall
        cmp byte ptr [eax], 1
        jne ad_l
        push ecx
        mov edx, [eax + 4]
        cmp edx, 0xffffffff
        je ad_cskip
        mov eax, [ebx + {RESG:#x}]
        mov eax, [eax + 0x60]
        call {GFX_GET:#x}
        test eax, eax
        jz ad_cskip
        pop ecx
        push eax
        mov dl, 1
        mov eax, [ebp - 4]
        add eax, {VMT_CORPSE:#x}
        call {TEOBJ_CREATE:#x}
        mov esi, eax
        pop eax
        mov [esi + 0x10], eax
        mov edx, [ebp - 0x10]
        mov eax, [edx + 0x1c]
        test eax, eax
        jz ad_nolink
        call find_cu
    ad_nolink:
        mov [esi + 0xc], eax
        mov edx, [ebp - 0x10]
        mov eax, [edx + 8]
        mov [esi + 0x14], eax
        mov eax, [edx + 0xc]
        mov [esi + 0x18], eax
        mov eax, [edx + 0x10]
        mov [esi + 0x1c], eax
        mov eax, [edx + 0x14]
        mov [esi + 0x20], eax
        mov eax, [edx + 0x18]
        mov [esi + 0x24], eax
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0xe0]
        jmp ad_l
    ad_cskip:
        pop ecx
        jmp ad_l
    ad_oil:
        mov eax, [ebp - 4]
        cmp dword ptr [eax + {VMT_OIL - 0x40:#x}], 0
        je ad_l
        add eax, {VMT_OIL:#x}
        jmp ad_mk
    ad_ooze:
        mov eax, [ebp - 4]
        add eax, {VMT_OOZE:#x}
    ad_mk:
        mov dl, 1
        call {TEOBJ_CREATE:#x}
        mov edx, [eax]
        call dword ptr [edx + 0xe0]
        jmp ad_l
    ad_fire:
        mov dl, 1
        mov eax, [ebp - 4]
        add eax, {VMT_FIRE:#x}
        call {TEOBJ_CREATE:#x}
        mov esi, eax
        mov edx, [eax]
        call dword ptr [edx + 0xe0]
        mov edx, [ebp - 0x10]
        mov eax, [edx + 4]
        mov [esi + 0x14], eax
        mov al, [edx + 8]
        mov [esi + 0x18], al
        jmp ad_l
    ad_wall:
        movzx edx, byte ptr [ecx + 0xd]
    aw_l:
        dec edx
        js ad_l
        mov eax, [ecx + 8]
        mov eax, [eax + edx*4]
        mov esi, [eax]
        sub esi, [ebp - 4]
        push edx
        mov edx, [ebp - 0x10]
        cmp byte ptr [edx], 4
        pop edx
        je aw_s
        cmp esi, {VMT_WALL:#x}
        je aw_w
        cmp esi, {VMT_DOOR:#x}
        jne aw_l
    aw_w:
        mov edx, [ebp - 0x10]
        mov edx, [edx + 4]
        cmp edx, [eax + 0x20]
        jge ad_l
        mov byte ptr [eax + 0x2c], 0
        mov ecx, [ebp - 4]
        add ecx, {WALL_SETHP:#x}
        call ecx
        jmp ad_l
    aw_s:
        cmp esi, {VMT_STRUCT:#x}
        jne aw_l
        mov edx, [ebp - 0x10]
        mov edx, [edx + 4]
        cmp edx, [eax + 0x20]
        jge ad_l
        mov byte ptr [eax + 0x24], 0
        mov ecx, [ebp - 4]
        add ecx, {STRUCT_SETHP:#x}
        call ecx
        jmp ad_l
    ad_blood:
        mov dl, 1
        mov eax, [ebp - 4]
        add eax, {VMT_BLOOD:#x}
        call {TEOBJ_CREATE:#x}
        mov esi, eax
        mov edx, [eax]
        call dword ptr [edx + 0xe0]
        mov edx, [ebp - 0x10]
        mov eax, [edx + 4]
        mov [esi + 0x10], eax
        mov eax, [edx + 8]
        mov [esi + 0x14], eax
        mov eax, [edx + 0xc]
        mov [esi + 0x18], eax
        jmp ad_l
    ad_out:
        pop esi
        mov esp, ebp
        pop ebp
        ret

    expl_fields:
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x11c]
        test eax, eax
        jz ef_no
        mov eax, [eax + 0x10]
        mov eax, [eax + 8]
        mov eax, [eax + 4]
        mov eax, [eax]
        mov ecx, [eax + 0x14]
        mov edx, [eax + 0x28]
        mov esi, [eax + 0x2c]
        cmp ecx, {EXPL_MAX}
        ja ef_no
        test ecx, ecx
        jle ef_no
        ret
    ef_no:
        xor ecx, ecx
        ret

    snap_expl:
        pushad
        call expl_fields
        mov [edi + {OFF_EXPL:#x}], ecx
        jecxz se_out
        lea ebp, [edi + {OFF_EXPL + 4:#x}]
    se_l:
        mov ax, [esi + 0x18]
        mov [ebp], ax
        add ebp, 2
        add esi, edx
        dec ecx
        jnz se_l
    se_out:
        popad
        ret

    apply_expl:
        pushad
        call expl_fields
        jecxz ae_out
        cmp ecx, [edi + {OFF_EXPL:#x}]
        jne ae_out
        lea ebp, [edi + {OFF_EXPL + 4:#x}]
    ae_l:
        mov ax, [ebp]
        or [esi + 0x18], ax
        add ebp, 2
        add esi, edx
        dec ecx
        jnz ae_l
        push 0
        push 100
        xor ecx, ecx
        xor edx, edx
        mov eax, [ebx + {MAPG:#x}]
        mov eax, [eax + 0x11c]
        mov esi, ebx
        add esi, {MAPCHANGEDRAD:#x}
        call esi
    ae_out:
        popad
        ret

    scan_field:
        movsx edx, byte ptr [eax + 0x12]
        push edx
        push 0
        movsx ecx, byte ptr [eax + 0x11]
        movsx edx, byte ptr [eax + 0x10]
        mov eax, [eax + 4]
        mov eax, [eax + 0x1c]
        call {SCANNER_RAD:#x}
        ret

    free_rbuf:
        mov eax, [ebx + {V_RBUF:#x}]
        test eax, eax
        jz fr_out
        push eax
        call {LOCALFREE:#x}
        mov dword ptr [ebx + {V_RBUF:#x}], 0
    fr_out:
        ret

    count_remote:
        xor eax, eax
        mov ecx, [ebx + {MAPG:#x}]
        mov ecx, [ecx + 0x240]
        test ecx, ecx
        jz cr_out
        mov ecx, [ecx + 0x1c]
        test ecx, ecx
        jz cr_out
        mov ecx, [ecx + 0xc]
        mov ecx, [ecx + 8]
        mov edx, [ecx + 8]
        mov ecx, [ecx + 4]
    cr_l:
        dec edx
        js cr_out
        mov esi, [ecx + edx*4]
        cmp byte ptr [esi + 8], 1
        jne cr_l
        inc eax
        jmp cr_l
    cr_out:
        ret

    send_raw:
        push ecx
        mov ecx, edx
        xor edx, edx
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x44]
        mov esi, {X_SENDMESSAGE:#x}
        call esi
        ret

    send_ctl:
        push esi
        sub esp, 8
        mov dword ptr [esp], {MAGIC:#x}
        mov [esp + 4], ax
        mov edx, esp
        mov ecx, 6
        call send_raw
        add esp, 8
        pop esi
        ret

    send_chunks:
        push esi
        push edi
        push ebp
        sub esp, {CHUNK + 16}
        mov ebp, {PER_FRAME}
    sc_l:
        mov eax, [ebx + {V_RSIZE:#x}]
        sub eax, [ebx + {V_RGOT:#x}]
        jbe sc_done
        cmp eax, {CHUNK}
        jbe sc_len
        mov eax, {CHUNK}
    sc_len:
        mov dword ptr [esp], {MAGIC:#x}
        mov byte ptr [esp + 4], 0x43
        mov ecx, [ebx + {V_RSIZE:#x}]
        mov [esp + 5], ecx
        mov ecx, [ebx + {V_RGOT:#x}]
        mov [esp + 9], ecx
        mov esi, [ebx + {V_RBUF:#x}]
        add esi, ecx
        lea edi, [esp + 13]
        mov ecx, eax
        rep movsb
        add [ebx + {V_RGOT:#x}], eax
        lea ecx, [eax + 13]
        mov edx, esp
        call send_raw
        dec ebp
        jnz sc_l
        jmp sc_out
    sc_done:
        call free_rbuf
        mov byte ptr [ebx + {V_STATE:#x}], 4
        mov byte ptr [ebx + {V_TIMER:#x}], 0
    sc_out:
        add esp, {CHUNK + 16}
        pop ebp
        pop edi
        pop esi
        ret

    read_file:
        push esi
        push edi
        mov dword ptr [ebx + {V_RSIZE:#x}], 0
        test eax, eax
        jz rf_out
        push 0
        push 0x80
        push 3
        push 0
        push 1
        push 0x80000000
        push eax
        call {CREATEFILE:#x}
        cmp eax, -1
        je rf_out
        mov esi, eax
        push 2
        push 0
        push 0
        push esi
        call {SETFILEPTR:#x}
        mov edi, eax
        push 0
        push 0
        push 0
        push esi
        call {SETFILEPTR:#x}
        call free_rbuf
        test edi, edi
        jle rf_close
        push edi
        push 0
        call {LOCALALLOC:#x}
        test eax, eax
        jz rf_close
        mov [ebx + {V_RBUF:#x}], eax
        push 0
        mov ecx, esp
        push 0
        push ecx
        push edi
        push eax
        push esi
        call {READFILE:#x}
        pop ecx
        cmp ecx, edi
        jne rf_close
        mov [ebx + {V_RSIZE:#x}], edi
    rf_close:
        push esi
        call {CLOSEHANDLE:#x}
    rf_out:
        pop edi
        pop esi
        ret

    write_file:
        push esi
        mov edx, ebx
        add edx, s_asg
        call mkpath
        test eax, eax
        jz wf_free
        push 0
        push 0x80
        push 2
        push 0
        push 0
        push 0x40000000
        push eax
        call {CREATEFILE:#x}
        cmp eax, -1
        je wf_free
        mov esi, eax
        push 0
        mov ecx, esp
        push 0
        push ecx
        push dword ptr [ebx + {V_RSIZE:#x}]
        push dword ptr [ebx + {V_RBUF:#x}]
        push esi
        call {WRITEFILE:#x}
        pop ecx
        push esi
        call {CLOSEHANDLE:#x}
        call free_rbuf
        mov al, 0x44
        call send_ctl
        pop esi
        ret
    wf_free:
        call free_rbuf
        pop esi
        ret

    dr_hook:
        cmp ecx, 5
        jb dr_pass
        cmp dword ptr [edx], {MAGIC:#x}
        jne dr_pass
        pushad
        call dd
    dd:
        pop ebx
        sub ebx, dd
        mov esi, edx
        mov edi, ecx
        mov al, [esi + 4]
        cmp al, 0x46
        jne dr_c
        mov al, [esi + 5]
        mov [{X_MAN:#x}], al
        mov byte ptr [ebx + {V_FROZEN:#x}], 1
        mov byte ptr [ebx + {V_OOS:#x}], 0
        mov byte ptr [ebx + {V_ISHOST:#x}], 0
        or byte ptr [ebx + {V_FLAGS:#x}], 1
        call d_reset
        call free_rbuf
        mov dword ptr [ebx + {V_RGOT:#x}], 0
        mov dword ptr [ebx + {V_RSIZE:#x}], 0
        jmp dr_done
    dr_c:
        cmp al, 0x43
        jne dr_d
        cmp edi, 13
        jbe dr_done
        cmp byte ptr [ebx + {V_STATE:#x}], 3
        je dr_done
        cmp dword ptr [esi + 9], 0
        jne dr_c2
        call free_rbuf
        push dword ptr [esi + 5]
        push 0
        call {LOCALALLOC:#x}
        mov [ebx + {V_RBUF:#x}], eax
        mov eax, [esi + 5]
        mov [ebx + {V_RSIZE:#x}], eax
        mov dword ptr [ebx + {V_RGOT:#x}], 0
    dr_c2:
        mov eax, [ebx + {V_RBUF:#x}]
        test eax, eax
        jz dr_done
        mov ecx, [ebx + {V_RSIZE:#x}]
        sub ecx, [esi + 9]
        jbe dr_done
        cmp ecx, {CHUNK}
        jbe dr_c3
        mov ecx, {CHUNK}
    dr_c3:
        lea edx, [ecx + 13]
        cmp edi, edx
        jb dr_done
        add [ebx + {V_RGOT:#x}], ecx
        add eax, [esi + 9]
        mov edi, eax
        add esi, 13
        rep movsb
        mov eax, [ebx + {V_RGOT:#x}]
        cmp eax, [ebx + {V_RSIZE:#x}]
        jb dr_done
        or byte ptr [ebx + {V_FLAGS:#x}], 2
        jmp dr_done
    dr_d:
        cmp al, 0x44
        jne dr_g
        inc byte ptr [ebx + {V_DONES:#x}]
        jmp dr_done
    dr_g:
        cmp al, 0x47
        jne dr_p
        or byte ptr [ebx + {V_FLAGS:#x}], 4
        jmp dr_done
    dr_p:
        cmp al, 0x42
        jne dr_p2
        cmp edi, 13
        jb dr_done
        movzx ecx, byte ptr [esi + 6]
        cmp ecx, 60
        ja dr_done
        shl ecx, 4
        add ecx, 8
        lea edx, [ecx + 5]
        cmp edi, edx
        jb dr_done
        push ecx
        call free_snap
        push {SNAP_SIZE}
        push 0x40
        call {LOCALALLOC:#x}
        pop ecx
        test eax, eax
        jz dr_done
        mov [ebx + {V_SNAP:#x}], eax
        mov edi, eax
        add esi, 5
        rep movsb
        mov byte ptr [ebx + {V_PEND:#x}], 1
        mov byte ptr [ebx + {V_TIMER:#x}], 0
        jmp dr_done
    dr_p2:
        cmp al, 0x4b
        jne dr_p3
        cmp edi, 6
        jb dr_done
        movzx ecx, byte ptr [esi + 5]
        cmp ecx, {DEC_PER}
        ja dr_done
        imul edx, ecx, 32
        add edx, 6
        cmp edi, edx
        jb dr_done
        mov edi, [ebx + {V_SNAP:#x}]
        test edi, edi
        jz dr_done
        mov eax, [edi + {DEC_CNT:#x}]
        lea edx, [eax + ecx]
        cmp edx, {DEC_MAX}
        ja dr_done
        mov [edi + {DEC_CNT:#x}], edx
        imul eax, eax, 32
        lea edi, [edi + eax + {DEC_REC:#x}]
        imul ecx, ecx, 32
        add esi, 6
        rep movsb
        jmp dr_done
    dr_p3:
        cmp al, 0x58
        jne dr_p4
        cmp edi, 9
        jb dr_done
        mov ecx, [esi + 5]
        cmp ecx, {DEAD_MAX}
        ja dr_done
        imul ecx, ecx, 12
        add ecx, 4
        lea edx, [ecx + 5]
        cmp edi, edx
        jb dr_done
        mov edi, [ebx + {V_SNAP:#x}]
        test edi, edi
        jz dr_done
        add edi, {OFF_DEAD:#x}
        add esi, 5
        rep movsb
        jmp dr_done
    dr_p4:
        cmp al, 0x54
        je {c2['h_t']:#x}
        cmp al, 0x53
        je {c2['h_s']:#x}
        cmp al, 0x4d
        je {c2['h_m']:#x}
        cmp al, 0x4a
        je dr_j
        cmp al, 0x48
        je dr_h
        cmp al, 0x4f
        jne dr_p5
        cmp byte ptr [ebx + {V_STATE:#x}], 0
        jne dr_done
        cmp byte ptr [ebx + {V_FROZEN:#x}], 0
        jne dr_done
        cmp byte ptr [ebx + {V_GRACE:#x}], 0
        jne dr_done
        cmp byte ptr [ebx + {V_OOS:#x}], 0
        jne dr_done
        cmp edi, 6
        jb dr_done
        cmp byte ptr [esi + 5], 2
        je dr_ow
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x44]
        cmp byte ptr [eax + 0x1ef], 0
        je dr_done
        mov byte ptr [ebx + {V_OOS:#x}], 1
        mov byte ptr [ebx + {V_FROZEN:#x}], 1
        jmp dr_done
    dr_ow:
        cmp byte ptr [ebx + {V_DLG:#x}], 0
        jne dr_done
        mov byte ptr [ebx + {V_OOS:#x}], 3
        jmp dr_done
    dr_p5:
        cmp byte ptr [ebx + {V_STATE:#x}], 2
        jne dr_done
        cmp edi, 6
        jb dr_done
        mov ah, [esi + 5]
        cmp al, 0x50
        jne dr_l
        cmp byte ptr [ebx + {V_ISHOST:#x}], 0
        jne dr_done
        mov [ebx + {V_RSEQ:#x}], ah
        or byte ptr [ebx + {V_FLAGS:#x}], 8
        jmp dr_done
    dr_l:
        cmp al, 0x4c
        jne dr_r
        cmp byte ptr [ebx + {V_ISHOST:#x}], 0
        je dr_done
        cmp ah, [ebx + {V_SEQ:#x}]
        jne dr_done
        inc byte ptr [ebx + {V_DONES:#x}]
        jmp dr_done
    dr_r:
        cmp al, 0x52
        jne dr_done
        cmp byte ptr [ebx + {V_ISHOST:#x}], 0
        jne dr_done
        or byte ptr [ebx + {V_FLAGS:#x}], 0x10
    dr_done:
        popad
        ret 4
    dr_j:
        cmp edi, 10
        jb dr_done
        mov ecx, [ebx + {MAPG:#x}]
        test ecx, ecx
        jz dr_done
        mov eax, [esp + 0x24]
        mov edx, [esi + 6]
        mov esi, ecx
        mov ecx, [esi + 0x240]
        test ecx, ecx
        jz dr_done
        mov ecx, [ecx + 0x1c]
        test ecx, ecx
        jz dr_done
        cmp edx, [ecx + 0x10]
        je dr_done
        cmp eax, [ecx + 0x10]
        je dr_done
        call remap
        jmp dr_done
    dr_h:
        mov ecx, [{X_DPTR:#x}]
        test ecx, ecx
        jz dr_done
        mov eax, [esp + 0x24]
        mov [ecx + {D_HOSTID}], eax
        jmp dr_done
    dr_pass:
        jmp {c2['filt']:#x}
    dr_pass2:
        push ebx
        call dp
    dp:
        pop ebx
        sub ebx, dp
        mov ebx, [ebx + {V_REALDR:#x}]
        xchg ebx, [esp]
        ret

    oos_hook:
        push ebx
        call od
    od:
        pop ebx
        sub ebx, od
        mov ecx, [ebx + {MAPG:#x}]
        test ecx, ecx
        jz oo_pass
        mov edx, [ecx + 0x23c]
        mov edx, [edx + 4]
        mov edx, [edx + 4]
        cmp byte ptr [edx + 0x10], 0
        je oo_ret
        cmp byte ptr [ebx + {V_GRACE:#x}], 0
        jne oo_ret
        cmp byte ptr [ebx + {V_STATE:#x}], 0
        jne oo_ret
        cmp byte ptr [ebx + {V_FROZEN:#x}], 0
        jne oo_ret
        cmp byte ptr [ebx + {V_OOS:#x}], 0
        jne oo_ret
        cmp byte ptr [ebx + {V_DLG:#x}], 0
        jne oo_ret
        cmp dword ptr [ecx + 0x120], 0
        je oo_world
        mov byte ptr [ebx + {V_OOS:#x}], 1
        mov byte ptr [ebx + {V_FROZEN:#x}], 1
        jmp oo_ret
    oo_world:
        mov byte ptr [ebx + {V_OOS:#x}], 2
    oo_ret:
        pop ebx
        ret
    oo_pass:
        pop ebx
        push ebx
        push esi
        push edi
        mov ebx, eax
        jmp {OOS_BACK:#x}

    is_host:
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x44]
        mov al, [eax + 0x1ef]
        ret

    restore_caps:
        cmp dword ptr [ebx + {CAPS:#x}], 0
        je rc_out
        mov ecx, [{MSGDLG:#x}]
        test ecx, ecx
        jz rc_out
        mov eax, [ecx + 0x8c]
        mov edx, [ebx + {CAPS:#x}]
        mov [eax + 0x90], edx
        mov byte ptr [eax + 0xa4], 0
        mov eax, [ecx + 0x90]
        mov edx, [ebx + {CAPS + 4:#x}]
        mov [eax + 0x90], edx
        mov byte ptr [eax + 0xa4], 0
        mov eax, [ecx + 0x94]
        mov edx, [ebx + {CAPS + 8:#x}]
        mov [eax + 0x90], edx
        mov byte ptr [eax + 0xa4], 0
        mov dword ptr [ebx + {CAPS:#x}], 0
    rc_out:
        ret

    close_dlg:
        cmp byte ptr [ebx + {V_DLG:#x}], 0
        je cdl_out
        mov byte ptr [ebx + {V_DLG:#x}], 0
        call restore_caps
        mov eax, [{MSGDLG:#x}]
        test eax, eax
        jz cdl_out
        mov eax, [eax + 0x44]
        test eax, eax
        jz cdl_out
        xor edx, edx
        mov ecx, [eax]
        call dword ptr [ecx + 0x6c]
    cdl_out:
        ret

    open_dlg:
        push esi
        push edi
        mov eax, [ebx + {CLS_CONN:#x}]
        mov dl, 1
        xor ecx, ecx
        mov esi, ebx
        add esi, {MSGLOG_CREATE:#x}
        call esi
        mov esi, eax
        mov byte ptr [esi + 0x25], 3
        mov byte ptr [esi + 0x28], 3
        mov byte ptr [esi + 0x29], 0xff
        call is_host
        lea edx, [ebx + s_dlg_host]
        test al, al
        jnz od_t0
        lea edx, [ebx + s_dlg_cli]
    od_t0:
        mov ecx, [{X_DPTR:#x}]
        test ecx, ecx
        jz od_t
        cmp byte ptr [ecx + {D_DLGK}], 0
        je od_t
        lea edx, [ecx + {D_TEXT}]
    od_t:
        mov eax, [esi + 0x20]
        mov ecx, [eax]
        call dword ptr [ecx + 0x2c]
        mov edi, [{MSGDLG:#x}]
        test edi, edi
        jz od_show
        cmp dword ptr [ebx + {CAPS:#x}], 0
        jne od_have
        mov eax, [edi + 0x8c]
        mov eax, [eax + 0x90]
        test eax, eax
        jz od_show
        mov [ebx + {CAPS:#x}], eax
        mov eax, [edi + 0x90]
        mov eax, [eax + 0x90]
        mov [ebx + {CAPS + 4:#x}], eax
        mov eax, [edi + 0x94]
        mov eax, [eax + 0x90]
        mov [ebx + {CAPS + 8:#x}], eax
    od_have:
        call is_host
        lea edx, [ebx + s_b_reload]
        test al, al
        jnz od_c
        lea edx, [ebx + s_b_wait]
    od_c:
        mov ecx, [{X_DPTR:#x}]
        test ecx, ecx
        jz od_c1
        cmp byte ptr [ecx + {D_DLGK}], 2
        je od_cw
        cmp byte ptr [ecx + {D_ROLE}], 2
        jne od_c1
    od_cw:
        lea edx, [ebx + s_b_wait]
    od_c1:
        mov eax, [edi + 0x8c]
        mov [eax + 0x90], edx
        mov byte ptr [eax + 0xa4], 0
        mov eax, [edi + 0x90]
        lea edx, [ebx + s_b_save]
        test ecx, ecx
        jz od_c2
        cmp byte ptr [ecx + {D_DLGK}], 2
        jne od_c2
        lea edx, [ebx + s_b_saveexit]
    od_c2:
        mov [eax + 0x90], edx
        mov byte ptr [eax + 0xa4], 0
        mov eax, [edi + 0x94]
        lea edx, [ebx + s_b_exit]
        mov [eax + 0x90], edx
        mov byte ptr [eax + 0xa4], 0
    od_show:
        push 0
        push 0
        xor ecx, ecx
        mov edx, esi
        mov eax, [ebx + {MAPG:#x}]
        mov edi, [eax]
        call dword ptr [edi + 0x12c]
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x2c]
        mov byte ptr [ebx + {V_DLG:#x}], 1
        pop edi
        pop esi
        ret

    yes_hook:
        push ebx
        call yd
    yd:
        pop ebx
        sub ebx, yd
        cmp byte ptr [ebx + {V_DLG:#x}], 0
        je y_pass
        cmp byte ptr [eax + 0x25], 3
        jne y_pass
        cmp byte ptr [eax + 0x28], 3
        jne y_pass
        mov byte ptr [ebx + {V_DLG:#x}], 0
        call restore_caps
        mov ecx, [{X_DPTR:#x}]
        test ecx, ecx
        jz y_std
        cmp byte ptr [ecx + {D_ROLE}], 0
        je y_std
        mov byte ptr [ecx + {D_WAIT}], 1
        mov word ptr [ecx + {D_TMR}], 0
        mov byte ptr [ecx + {D_DLGK}], 0
        mov byte ptr [ebx + {V_FROZEN:#x}], 1
        or byte ptr [ebx + {V_FLAGS:#x}], 1
        jmp y_done
    y_std:
        call is_host
        test al, al
        jz y_cli
        mov byte ptr [ebx + {V_OOS:#x}], 6
        jmp y_done
    y_cli:
        mov byte ptr [ebx + {V_OOS:#x}], 5
        mov byte ptr [ebx + {V_FROZEN:#x}], 1
        or byte ptr [ebx + {V_FLAGS:#x}], 1
    y_done:
        pop ebx
        mov al, 1
        ret
    y_pass:
        pop ebx
    y_orig:
        push ebx
        push esi
        mov esi, eax
        xor ecx, ecx
        jmp {YES_BACK:#x}

    no_hook:
        push ebx
        call nd
    nd:
        pop ebx
        sub ebx, nd
        cmp byte ptr [ebx + {V_DLG:#x}], 0
        je n_pass
        mov byte ptr [ebx + {V_DLG:#x}], 0
        call restore_caps
        pop ebx
        add esp, 4
        xor eax, eax
        jmp y_orig
    n_pass:
        pop ebx
        jmp {EXITGAME:#x}

    cancel_hook:
        push ebx
        call cnd
    cnd:
        pop ebx
        sub ebx, cnd
        cmp byte ptr [ebx + {V_DLG:#x}], 0
        je c_pass
        mov ecx, [ebx + {CLS_CONN:#x}]
        cmp [eax], ecx
        jne c_pass
        cmp byte ptr [eax + 0x25], 3
        jne c_pass
        mov byte ptr [ebx + {V_DLG:#x}], 0
        call restore_caps
        mov eax, [ebx + {MAPG:#x}]
        pop ebx
        call {EXITGAME:#x}
        mov al, 1
        ret
    c_pass:
        pop ebx
        mov byte ptr [eax + 0x26], 2
        mov al, 1
        ret

    nct_hook:
        push eax
        call nq
    nq:
        pop eax
        sub eax, nq
        test byte ptr [eax + {V_FLAGS:#x}], 0x80
        pop eax
        jnz fx_skip
        push ebx
        push esi
        push edi
        push ebp
        add esp, -8
        jmp {NCT_BACK:#x}
    cdn_hook:
        push eax
        call cq
    cq:
        pop eax
        sub eax, cq
        test byte ptr [eax + {V_FLAGS:#x}], 0x80
        pop eax
        jnz fx_skip
        push ebx
        push esi
        push edi
        push ebp
        mov ebp, edx
        jmp {CDN_BACK:#x}
    fx_skip:
        ret

    nfgate:
        push eax
        call ng
    ng:
        pop eax
        sub eax, ng
        cmp byte ptr [eax + {V_FROZEN:#x}], 0
        pop eax
        jne ng_skip
        cmp dword ptr [ebx + 0x11c], 0
        jmp {NF_BACK:#x}
    ng_skip:
        jmp {NF_SKIP:#x}

    wait_text:
        mov eax, [{X_SYNCDLG:#x}]
        mov eax, [eax]
        test eax, eax
        jz wt_out
        mov eax, [eax + 0x58]
        test eax, eax
        jz wt_out
        mov ecx, {X_SETGTEXT:#x}
        call ecx
    wt_out:
        ret
    show_wait:
        lea edx, [ebx + s_oos]
        cmp byte ptr [{X_MAN:#x}], {MAN_MARK}
        jne sw_nm
        lea edx, [ebx + s_w_man]
    sw_nm:
        mov eax, [{X_DPTR:#x}]
        test eax, eax
        jz sw_t
        cmp byte ptr [eax + {D_CONN}], 0
        je sw_r
        lea edx, [ebx + s_w_rel]
    sw_r:
        mov cl, [eax + {D_ROLE}]
        cmp cl, 1
        jne sw_r2
        lea edx, [ebx + s_w_stay]
    sw_r2:
        cmp cl, 2
        jne sw_r3
        lea edx, [ebx + s_w_recon]
    sw_r3:
        cmp cl, 3
        jne sw_t
        lea edx, [ebx + s_w_rejoin]
    sw_t:
        call wait_text
        mov dl, 1
        jmp sw_set
    hide_wait:
        xor edx, edx
    sw_set:
        mov eax, [{X_SYNCDLG:#x}]
        mov eax, [eax]
        test eax, eax
        jz sw_out
        mov eax, [eax + 0x44]
        test eax, eax
        jz sw_out
        mov ecx, [eax]
        call dword ptr [ecx + 0x6c]
    sw_out:
        ret

    gs_hook:
        push ebx
        call gsd
    gsd:
        pop ebx
        sub ebx, gsd
        cmp byte ptr [ebx + {V_FROZEN:#x}], 0
        je gs_pass
        mov ecx, [ebx + {MAPG:#x}]
        test ecx, ecx
        jz gs_pass
        movsx edx, byte ptr [ecx + 0xa5]
        mov eax, [ecx + 0x140]
        test eax, eax
        jz gs_zero
        mov ecx, ebx
        add ecx, {GETPLAYERS:#x}
        call ecx
        test eax, eax
        jz gs_zero
        mov edx, [eax + 0xd4]
        test edx, edx
        jz gs_zero
        mov cl, [eax + 0xa5]
        mov [ebx + {V_FRACE:#x}], cl
        mov [ebx + {V_FLEAD:#x}], edx
        lea eax, [ebx + {V_FAKE:#x}]
        pop ebx
        ret
    gs_zero:
        xor eax, eax
        pop ebx
        ret
    gs_pass:
        mov ecx, ebx
        add ecx, {GETSETTINGS:#x}
        pop ebx
        jmp ecx

    ir_hook:
        push ebx
        call ird
    ird:
        pop ebx
        sub ebx, ird
        cmp byte ptr [ebx + {V_FROZEN:#x}], 0
        je ir_pass
        cmp dword ptr [ebx + {MAPG:#x}], 0
        je ir_pass
        xor eax, eax
        pop ebx
        ret
    ir_pass:
        mov ecx, ebx
        add ecx, {INDEXOFREMOTEID:#x}
        pop ebx
        jmp ecx

    dosave:
        push 0
        push 0
        mov edx, eax
        mov eax, [ebx + {ENGINE:#x}]
        mov ecx, [eax]
        call dword ptr [ecx + 0xac]
        ret

    mkpath:
        push esi
        push edi
        lea edi, [ebx + {BUF + 8:#x}]
        mov eax, [ebx + {ENGINE:#x}]
        mov esi, [eax + 0x2c]
        test esi, esi
        jz mp_sfx
        mov ecx, [esi - 4]
        cmp ecx, 0x58
        ja mp_fail
        rep movsb
    mp_sfx:
        mov esi, edx
    mp_l:
        lodsb
        stosb
        test al, al
        jnz mp_l
        lea eax, [ebx + {BUF + 8:#x}]
        dec edi
        sub edi, eax
        mov [eax - 4], edi
        mov dword ptr [eax - 8], 0xffffffff
        pop edi
        pop esi
        ret
    mp_fail:
        xor eax, eax
        pop edi
        pop esi
        ret

    reload:
        push ebp
        mov ebp, esp
        sub esp, 0x28
        mov [ebp - 4], eax
        mov esi, [ebx + {MAPG:#x}]
        mov al, [esi + 0x13a]
        mov [ebp - 8], al
        mov al, [esi + 0x239]
        mov [ebp - 7], al
        mov al, [esi + 0x14c]
        mov [ebp - 6], al
        mov al, [esi + 0x149]
        mov [ebp - 5], al
        mov al, [esi + 0x14a]
        mov [ebp - 0x1c], al
        mov eax, [esi + 0x158]
        mov [ebp - 0xc], eax
        mov eax, [esi + 0x15c]
        mov [ebp - 0x10], eax
        xor edi, edi
        mov eax, [esi + 0x240]
        test eax, eax
        jz r_nopcc
        mov edi, [eax + 0x1c]
        test edi, edi
        jz r_nopcc
        mov eax, edi
        mov ecx, [ebx + {RELEASE_SLOT:#x}]
        sub ecx, 4
        call ecx
    r_nopcc:
        mov [ebp - 0x14], edi
        mov dword ptr [ebp - 0x18], 0
        cmp byte ptr [{X_HOLD:#x}], 0
        je r_nosc
        mov eax, [{X_SCANNERVAR:#x}]
        mov eax, [eax]
        test eax, eax
        jz r_nosc
        mov eax, [eax + 0x5c]
        test eax, eax
        jz r_nosc
        mov [ebp - 0x18], eax
        mov cl, [eax + 0x2c]
        mov [ebp - 0x20], cl
        mov byte ptr [eax + 0x2c], 0
        mov cl, [eax + 0x75]
        mov [ebp - 0x1f], cl
        mov byte ptr [eax + 0x75], 0
        mov ecx, [eax + 0x80]
        mov [ebp - 0x24], ecx
        mov dword ptr [eax + 0x80], 0
    r_nosc:
        mov eax, [{X_MAINWIN:#x}]
        mov eax, [eax]
        mov edx, [ebp - 4]
        mov ecx, {X_LOAD:#x}
        call ecx
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x44]
        mov byte ptr [eax + 0x1f1], 0
        mov esi, [ebx + {MAPG:#x}]
        test esi, esi
        jz r_done
        mov al, [ebp - 8]
        mov [esi + 0x13a], al
        mov al, [ebp - 6]
        mov [esi + 0x14c], al
        mov al, [ebp - 5]
        mov [esi + 0x149], al
        mov al, [ebp - 0x1c]
        mov [esi + 0x14a], al
        mov eax, [ebp - 0xc]
        mov [esi + 0x158], eax
        mov eax, [ebp - 0x10]
        mov [esi + 0x15c], eax
        mov al, [ebp - 7]
        mov [esi + 0x239], al
        mov edi, [ebp - 0x14]
        test edi, edi
        jz r_start
        mov eax, [esi + 0x240]
        test eax, eax
        jz r_rel
        mov edx, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x4c]
    r_rel:
        mov eax, edi
        call {RELEASE:#x}
    r_start:
        mov eax, [{X_MAINWIN:#x}]
        mov eax, [eax]
        mov ecx, {X_START:#x}
        call ecx
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov edx, [eax + 0x44]
        cmp byte ptr [edx + 0x1ed], 0
        je r_done
        push eax
        mov ecx, {X_CHAT1:#x}
        call ecx
        pop eax
        mov ecx, {X_CHAT2:#x}
        call ecx
    r_done:
        mov eax, [ebp - 0x18]
        test eax, eax
        jz r_ret
        mov cl, [ebp - 0x20]
        mov [eax + 0x2c], cl
        mov cl, [ebp - 0x1f]
        mov [eax + 0x75], cl
        mov ecx, [ebp - 0x24]
        mov [eax + 0x80], ecx
    r_ret:
        mov esp, ebp
        pop ebp
        ret

        .align 4
        .long 0xffffffff
        .long 25
    s_wait:
{cstr("Waiting for other players")}
        .align 4
        .long 0xffffffff
        .long {len(OOS_TEXT)}
    s_oos:
{cstr(OOS_TEXT)}
{astr("s_dlg_host", DLG_HOST)}
{astr("s_dlg_cli", DLG_CLI)}
{astr("s_b_reload", "Restore")}
{astr("s_b_wait", "Wait")}
{astr("s_b_save", "Save")}
{astr("s_b_exit", "Exit")}
{astr("s_b_saveexit", "Save & Exit")}
{astr("s_w_rel", "Reconnected - restoring game")}
{astr("s_w_man", MAN_TEXT)}
{astr("s_w_stay", "Waiting for player to rejoin")}
{astr("s_w_recon", "Connection lost - reconnecting")}
{astr("s_w_rejoin", "Reconnected - waiting for host")}
    s_t_recon:
{cstr("Connection lost - reconnecting")}
    s_t_norecon:
{cstr("Could not reconnect." + chr(13) + chr(10) + "Keep waiting, or exit game?")}
    s_t_conn:
{cstr("Connection to ")}
    s_t_player:
{cstr("player")}
    s_t_lost:
{cstr(" lost")}
    s_t_norejoin:
{cstr(" has not rejoined." + chr(13) + chr(10) + "Keep waiting, or exit game?")}
    s_asg:
{cstr("X" + chr(92) + "Save" + chr(92) + "resync.asg")}
    """
    src = chr(10).join(l.split(";")[0].rstrip() for l in src.split(chr(10)))
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code = bytes(ks.asm(src, CAVE)[0])
    full = bytes(ks.asm(src + chr(10) + ".long mm_hook" + chr(10) + ".long pd_hook" + chr(10) + ".long cl_hook" + chr(10) + ".long nct_hook" + chr(10) + ".long cdn_hook" + chr(10) + ".long yes_hook" + chr(10) + ".long no_hook" + chr(10) + ".long cancel_hook" + chr(10) + ".long oos_hook" + chr(10) + ".long rec_hook" + chr(10) + ".long nfgate" + chr(10), CAVE)[0])
    assert len(code) <= CAVE_END - CAVE, hex(len(code))
    assert ("X" + chr(92) + "Save" + chr(92) + "resync.asg").encode() + b"\0" in code
    return code, struct.unpack("<I", full[-4:])[0], struct.unpack("<I", full[-8:-4])[0], struct.unpack("<I", full[-12:-8])[0], struct.unpack("<3I", full[-24:-12]), struct.unpack("<2I", full[-32:-24]), struct.unpack("<2I", full[-40:-32]), struct.unpack("<I", full[-44:-40])[0], \
        dict(zip(C1_NAMES, struct.unpack("<%dI" % len(C1_NAMES), bytes(ks.asm(src + chr(10) + "".join(".long " + q + chr(10) for q in C1_NAMES), CAVE)[0])[-4 * len(C1_NAMES):])))


def stub():
    b = bytes([0x60, 0xA1]) + struct.pack("<I", X_SLOT_SAVEGAME) + bytes([0x05]) + struct.pack("<i", CAVE - SAVEGAME_VA) \
        + bytes([0xFF, 0xD0, 0x61, 0xA1]) + struct.pack("<I", X_MAPVAR) + bytes([0xC3])
    assert len(b) == 20
    return b


def reloc_entry(d, va):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    for blk in pe.DIRECTORY_ENTRY_BASERELOC:
        for e in blk.entries:
            if ib + e.rva == va:
                return e.struct.get_file_offset(), e.type
    return None, None


def build_cave2(L):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
    lobby_tick:
        mov byte ptr [{X_LOST:#x}], 0
        xor edx, edx
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        test eax, eax
        jz lt_m
        mov eax, [eax + 0x44]
        test eax, eax
        jz lt_m
        mov eax, [eax + 0x1b8]
        test eax, eax
        jz lt_m
        mov ecx, [eax + 8]
        mov eax, [eax + 4]
        cmp ecx, 32
        jbe lt_ml
        mov ecx, 32
    lt_ml:
        dec ecx
        js lt_m
        mov esi, [eax + ecx*4]
        test esi, esi
        jz lt_ml
        cmp dword ptr [esi + 0x44], {MAGIC:#x}
        jne lt_ml
        bts edx, ecx
        jmp lt_ml
    lt_m:
        mov [{X_RJMASK:#x}], edx
        call d_get
        test edx, edx
        jz lt_ret
        mov edi, edx
        xor eax, eax
        mov ecx, 12
        rep stosd
        cmp byte ptr [edx + {D_JSHOW}], 1
        jne lt_j
        mov byte ptr [edx + {D_JSHOW}], 2
        mov al, 1
        call show_join
    lt_j:
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        test eax, eax
        jz lt_ret
        mov eax, [eax + 0x44]
        cmp byte ptr [eax + 0x1ee], 0
        jne lt_in
        mov byte ptr [edx + {D_JOIN}], 0
        mov byte ptr [edx + {D_NEWCNT}], 0
        and byte ptr [ebx + {V_FLAGS:#x}], 0xf9
        cmp byte ptr [edx + {D_JSHOW}], 2
        jne lt_ret
        mov byte ptr [edx + {D_JSHOW}], 0
        xor eax, eax
        call show_join
        ret
    lt_in:
        cmp byte ptr [edx + {D_NEWCNT}], 0
        jne lt_in2
        cmp byte ptr [eax + 0x1ef], 0
        jne lt_in2
        mov byte ptr [edx + {D_NEWCNT}], 1
        cmp byte ptr [edx + {D_JSHOW}], 0
        jne lt_in2
        push ebp
        push edi
        push edx
        mov ebp, edx
        mov edi, eax
        mov dword ptr [ebp + {D_DESC + 0x40}], 0
        call {L['get_desc']:#x}
        pop edx
        pop edi
        pop ebp
        test eax, eax
        jnz lt_in2
        cmp dword ptr [edx + {D_DESC + 0x40}], {MAGIC:#x}
        jne lt_in2
        mov byte ptr [edx + {D_JSHOW}], 1
    lt_in2:
        cmp byte ptr [edx + {D_JOIN}], 0
        je lt_ret
        test byte ptr [ebx + {V_FLAGS:#x}], 2
        jz lt_g
        and byte ptr [ebx + {V_FLAGS:#x}], 0xfd
        push edx
        call {L['write_file']:#x}
        pop edx
        mov byte ptr [edx + {D_JOIN}], 2
    lt_g:
        test byte ptr [ebx + {V_FLAGS:#x}], 4
        jz lt_ret
        and byte ptr [ebx + {V_FLAGS:#x}], 0xfb
        cmp byte ptr [edx + {D_JOIN}], 2
        je join_start
        mov byte ptr [edx + {D_JOIN}], 0
    lt_ret:
        ret

    show_join:
        pushad
        movzx edi, al
        test edi, edi
        jz sj_p
        mov eax, [{X_SETUPFORM:#x}]
        mov eax, [eax]
        test eax, eax
        jz sj_p
        mov eax, [eax + 0xa0]
        test eax, eax
        jz sj_p
        xor edx, edx
        mov ecx, [eax]
        call dword ptr [ecx + 0x6c]
    sj_p:
        mov esi, [{X_PROGRESS:#x}]
        mov esi, [esi]
        test esi, esi
        jz sj_x
        test edi, edi
        jz sj_w
        mov eax, [esi + 0x44]
        lea edx, [ebx + s_j1]
        mov ecx, {X_SETGTEXT:#x}
        call ecx
        mov eax, [esi + 0x50]
        lea edx, [ebx + s_j2]
        mov ecx, {X_SETGTEXT:#x}
        call ecx
        mov eax, [esi + 0x58]
        xor edx, edx
        mov ecx, {X_GAUGEPOS:#x}
        call ecx
    sj_w:
        mov eax, [esi + 0x54]
        mov edx, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x6c]
        mov eax, [{X_MAINWIN:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x44]
        imul edx, edi, 0x1388
        mov ecx, {X_SETOVERPRI:#x}
        call ecx
    sj_x:
        popad
        ret
{astr("s_j1", "Rejoining game")}
{astr("s_j2", "Waiting for host")}
{astr("s_sess", "Age of Wonders")}

    d_get:
        mov edx, [{X_DPTR:#x}]
        test edx, edx
        jnz dg_x
        push eax
        push ecx
        push {D_SIZE}
        push 0x40
        call {LOCALALLOC:#x}
        mov edx, eax
        test edx, edx
        jz dg_p
        mov [{X_DPTR:#x}], edx
    dg_p:
        pop ecx
        pop eax
    dg_x:
        ret

    classify:
        xor edx, edx
        test eax, eax
        jz cl_x
        mov ecx, [edi + 0x1c0]
        test ecx, ecx
        jz cl_alone
        cmp dword ptr [ecx + 8], 1
        ja cl_x
    cl_alone:
        mov ecx, [ebp + {D_HOSTID}]
        cmp ecx, [edi + 0x1f4]
        jne cl_drop
        lea ecx, [eax - 1]
        test ecx, eax
        jz cl_x
    cl_drop:
        inc edx
    cl_x:
        ret

    takeover:
        xor eax, eax
        cmp byte ptr [ebp + {D_RETRY}], {REJOIN_POLLS}
        jb tk_x
        pushad
        cmp dword ptr [edi + 0x24], 0
        jne tk_c
        lea eax, [ebx + s_sess]
        mov [edi + 0x24], eax
    tk_c:
        mov byte ptr [edi + 0x1ed], 1
        mov eax, edi
        mov ecx, {X_CREATESESSION:#x}
        call ecx
        test eax, eax
        jz tk_ok
        mov byte ptr [ebp + {D_RETRY}], 0
        popad
        xor eax, eax
        ret
    tk_ok:
        mov esi, [ebx + {MAPG:#x}]
        mov eax, [edi + 0x1f4]
        mov edx, [ebp + {D_OLDID}]
        mov ecx, [esi + 0x240]
        mov ecx, [ecx + 0x1c]
        mov [ecx + 0x10], eax
        call {L['remap']:#x}
        mov eax, [edi + 0x1f4]
        mov [ebp + {D_HOSTID}], eax
        mov byte ptr [ebp + {D_ROLE}], 1
        mov byte ptr [ebp + {D_WAIT}], 0
        mov word ptr [ebp + {D_TMR}], 0
        mov byte ptr [ebp + {D_GUIDOK}], 0
        call {L['scan_seats']:#x}
        mov [ebp + {D_MASK}], ax
        mov byte ptr [ebp + {D_DLGK}], 1
        call {L['close_dlg']:#x}
        call {L['hide_wait']:#x}
        mov esi, [ebx + {MAPG:#x}]
        call {L['drop_text']:#x}
        call {L['open_dlg']:#x}
        popad
        mov al, 1
    tk_x:
        ret

    join_start:
        pushad
        mov ebp, [{X_DPTR:#x}]
        mov byte ptr [ebp + {D_JOIN}], 0
        mov byte ptr [ebp + {D_JSHOW}], 0
        lea edx, [ebx + {L['s_asg']:#x}]
        call {L['mkpath']:#x}
        test eax, eax
        jz js_x
        mov edx, eax
        mov eax, [{X_MAINWIN:#x}]
        mov eax, [eax]
        mov ecx, {X_LOAD:#x}
        call ecx
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x44]
        mov byte ptr [eax + 0x1f1], 0
        mov ecx, [eax + 0x1f4]
        mov [ebp + {D_TM}], ecx
        mov esi, [ebx + {MAPG:#x}]
        test esi, esi
        jz js_x
        lea edi, [ebp + {D_TAB}]
        mov al, [edi + 6]
        mov [esi + 0x13a], al
        mov al, [edi + 7]
        mov [esi + 0x239], al
        mov al, [edi + 8]
        mov [esi + 0x14c], al
        mov al, [edi + 9]
        mov [esi + 0x149], al
        mov al, [edi + 10]
        mov [esi + 0x14a], al
        mov eax, [edi + 11]
        mov [esi + 0x158], eax
        mov eax, [edi + 15]
        mov [esi + 0x15c], eax
        mov dl, 1
        mov eax, [ebx + {PCC_CLASS_SLOT:#x}]
        call {PCC_CREATE:#x}
        mov [ebp + {D_TH}], eax
        movzx edx, byte ptr [edi + 5]
        mov ecx, [ebp + {D_TM}]
        call {PCC_SETUP:#x}
        mov dword ptr [ebp + {D_TI}], 0
    js_l:
        mov edx, [ebp + {D_TI}]
        movzx eax, byte ptr [edi + 5]
        cmp edx, eax
        jae js_inst
        lea eax, [edx + edx*4]
        lea eax, [edi + eax + 19]
        mov ecx, [eax + 1]
        cmp byte ptr [eax], 0
        jne js_ai
        cmp ecx, [ebp + {D_TM}]
        je js_me
        push ecx
        mov cl, 1
        jmp js_set
    js_me:
        push ecx
        xor ecx, ecx
        jmp js_set
    js_ai:
        push dword ptr [ebp + {D_TM}]
        mov cl, 2
    js_set:
        mov eax, [ebp + {D_TH}]
        call {PCC_SETMODE:#x}
        pop ecx
        mov edx, [ebp + {D_TI}]
        mov eax, [ebp + {D_TH}]
        call {PCC_SETSYSID:#x}
        inc dword ptr [ebp + {D_TI}]
        jmp js_l
    js_inst:
        mov eax, [esi + 0x240]
        test eax, eax
        jz js_rel
        mov edx, [ebp + {D_TH}]
        mov ecx, [eax]
        call dword ptr [ecx + 0x4c]
    js_rel:
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x48]
        mov edx, [ebp + {D_TH}]
        mov ecx, [eax + 0x88]
        mov [edx + 0x18], ecx
        mov ecx, [eax + 0x8c]
        mov [edx + 0x1c], ecx
        mov eax, edx
        call {RELEASE:#x}
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov ecx, {X_SCSTART:#x}
        call ecx
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x48]
        call {SC_RESET:#x}
        mov byte ptr [ebx + {V_STATE:#x}], 2
        mov byte ptr [ebx + {V_TIMER:#x}], 0
        mov byte ptr [ebx + {V_ISHOST:#x}], 0
        mov byte ptr [ebx + {V_FROZEN:#x}], 1
        mov byte ptr [ebx + {V_DONES:#x}], 0
        mov byte ptr [ebx + {V_OOS:#x}], 0
        and byte ptr [ebx + {V_FLAGS:#x}], 0xe7
        or byte ptr [ebx + {V_FLAGS:#x}], 1
        mov dword ptr [ebp], 0
        mov dword ptr [ebp + 4], 0
        mov byte ptr [ebp + {D_CONN}], 1
    js_x:
        popad
        ret

    in_recs:
        push eax
        push ecx
        push edi
        mov eax, [esi + 0x240]
        mov eax, [eax + 0x1c]
        mov eax, [eax + 0xc]
        mov eax, [eax + 8]
        mov ecx, [eax + 8]
        mov eax, [eax + 4]
    ir_l:
        dec ecx
        js ir_no
        mov edi, [eax + ecx*4]
        cmp [edi + 0xc], edx
        jne ir_l
        jmp ir_o
    ir_no:
        or eax, 1
    ir_o:
        pop edi
        pop ecx
        pop eax
        ret

    host_new:
        pushad
        mov esi, [ebx + {MAPG:#x}]
        mov eax, [edi + 0x1f4]
        cmp eax, [ebp + {D_HOSTID}]
        je hn_h
        mov [ebp + {D_HOSTID}], eax
        cmp byte ptr [ebp + {D_DLGK}], 1
        jne hn_h
        call {L['close_dlg']:#x}
        mov esi, [ebx + {MAPG:#x}]
        call {L['drop_text']:#x}
        call {L['open_dlg']:#x}
        mov edi, [esp]
        mov esi, [ebx + {MAPG:#x}]
        mov ebp, [esp + 8]
    hn_h:
        test byte ptr [ebp + {D_HELLO}], 7
        jnz hn_s
        mov ax, 0x0048
        call {L['send_ctl']:#x}
    hn_s:
        mov eax, [edi + 0x1c0]
        test eax, eax
        jz hn_x
        mov ecx, [eax + 8]
        mov eax, [eax + 4]
    hn_l:
        dec ecx
        js hn_none
        mov edx, [eax + ecx*4]
        mov edx, [edx + 4]
        cmp edx, [edi + 0x1f4]
        je hn_l
        call in_recs
        je hn_l
        cmp edx, [ebp + {D_NEWID}]
        je hn_same
        mov [ebp + {D_NEWID}], edx
        mov byte ptr [ebp + {D_NEWCNT}], 0
        jmp hn_x
    hn_same:
        inc byte ptr [ebp + {D_NEWCNT}]
        cmp byte ptr [ebp + {D_NEWCNT}], 6
        jb hn_x
        movzx eax, word ptr [ebp + {D_MASK}]
        bsf ecx, eax
        jz hn_x
        mov eax, [esi + 0x240]
        mov eax, [eax + 0x1c]
        mov eax, [eax + 0xc]
        mov eax, [eax + 8]
        mov eax, [eax + 4]
        mov eax, [eax + ecx*4]
        mov ecx, [eax + 0xc]
        test ecx, ecx
        jz hn_x
        sub esp, 16
        mov dword ptr [esp], {MAGIC:#x}
        mov word ptr [esp + 4], 0x004d
        mov [esp + 6], ecx
        mov [esp + 10], edx
        mov eax, edx
        mov edx, ecx
        call {L['remap']:#x}
        mov edx, esp
        mov ecx, 14
        call {L['send_raw']:#x}
        add esp, 16
    hn_none:
        mov dword ptr [ebp + {D_NEWID}], 0
    hn_x:
        popad
        ret

    send_table:
        pushad
        mov esi, [ebx + {MAPG:#x}]
        mov eax, [esi + 0x240]
        test eax, eax
        jz st_x
        mov eax, [eax + 0x1c]
        test eax, eax
        jz st_x
        mov eax, [eax + 0xc]
        mov eax, [eax + 8]
        mov ecx, [eax + 8]
        cmp ecx, 16
        jbe st_c
        mov ecx, 16
    st_c:
        mov edi, [eax + 4]
        sub esp, 0x80
        mov dword ptr [esp], {MAGIC:#x}
        mov byte ptr [esp + 4], 0x53
        mov [esp + 5], cl
        mov al, [esi + 0x13a]
        mov [esp + 6], al
        mov al, [esi + 0x239]
        mov [esp + 7], al
        mov al, [esi + 0x14c]
        mov [esp + 8], al
        mov al, [esi + 0x149]
        mov [esp + 9], al
        mov al, [esi + 0x14a]
        mov [esp + 10], al
        mov eax, [esi + 0x158]
        mov [esp + 11], eax
        mov eax, [esi + 0x15c]
        mov [esp + 15], eax
        lea ebx, [esp + 19]
        xor ebp, ebp
    st_l:
        cmp ebp, ecx
        jae st_s
        push ecx
        mov edx, ebp
        mov eax, [esi + 0x140]
        call {GETPLAYERS:#x}
        mov dl, 2
        test eax, eax
        jz st_k
        mov dl, [eax + 0xa7]
    st_k:
        pop ecx
        mov eax, [edi + ebp*4]
        mov eax, [eax + 0xc]
        mov [ebx], dl
        mov [ebx + 1], eax
        add ebx, 5
        inc ebp
        jmp st_l
    st_s:
        mov edx, esp
        lea ecx, [ecx + ecx*4 + 19]
        push esi
        call {L['send_raw']:#x}
        pop esi
        add esp, 0x80
        xor edi, edi
        xor ebp, ebp
    sm_l:
        cmp ebp, 32
        jae sm_s
        mov eax, [esi + 0x140]
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        cmp ebp, eax
        jae sm_s
        mov edx, ebp
        mov eax, [esi + 0x140]
        call {GETPLAYERS:#x}
        test eax, eax
        jz sm_n
        cmp byte ptr [eax + 0x2c], 0
        je sm_n
        bts edi, ebp
    sm_n:
        inc ebp
        jmp sm_l
    sm_s:
        mov eax, [{X_DPTR:#x}]
        test eax, eax
        jz sm_t
        mov [eax + {D_ENDMASK}], edi
        mov byte ptr [eax + {D_ENDOK}], 1
    sm_t:
        sub esp, 12
        mov dword ptr [esp], {MAGIC:#x}
        mov word ptr [esp + 4], 0x0054
        mov [esp + 6], edi
        mov edx, esp
        mov ecx, 10
        call {L['send_raw']:#x}
        add esp, 12
    st_x:
        popad
        ret

    h_s:
        cmp dword ptr [ebx + {MAPG:#x}], 0
        jne hs_done
        cmp edi, 19
        jb hs_done
        movzx ecx, byte ptr [esi + 5]
        cmp ecx, 16
        ja hs_done
        lea eax, [ecx + ecx*4 + 19]
        cmp edi, eax
        jb hs_done
        call d_get
        test edx, edx
        jz hs_done
        lea edi, [edx + {D_TAB}]
        mov ecx, eax
        rep movsb
        mov byte ptr [edx + {D_JOIN}], 1
    hs_done:
        jmp {L['dr_done']:#x}

    h_m:
        cmp edi, 14
        jb hs_done
        mov ecx, [ebx + {MAPG:#x}]
        test ecx, ecx
        jnz hm_map
        mov eax, [{X_DPLAY:#x}]
        mov eax, [eax]
        test eax, eax
        jz hs_done
        mov eax, [eax + 0x44]
        mov eax, [eax + 0x1f4]
        cmp eax, [esi + 10]
        jne hs_done
        call d_get
        test edx, edx
        jz hs_done
        cmp byte ptr [edx + {D_JSHOW}], 0
        jne hs_done
        mov byte ptr [edx + {D_JSHOW}], 1
        jmp hs_done
    hm_map:
        mov edx, [esi + 6]
        mov eax, [esi + 10]
        mov esi, ecx
        mov ecx, [esi + 0x240]
        test ecx, ecx
        jz hs_done
        mov ecx, [ecx + 0x1c]
        test ecx, ecx
        jz hs_done
        cmp edx, [ecx + 0x10]
        je hs_done
        call {L['remap']:#x}
        jmp hs_done

    h_t:
        cmp edi, 10
        jb hs_done
        mov edx, [{X_DPTR:#x}]
        test edx, edx
        jz hs_done
        mov eax, [esi + 6]
        mov [edx + {D_ENDMASK}], eax
        mov byte ptr [edx + {D_ENDOK}], 1
        jmp hs_done

    end_apply:
        pushad
        mov ebp, [{X_DPTR:#x}]
        test ebp, ebp
        jz ea_x
        cmp byte ptr [ebp + {D_ENDOK}], 0
        je ea_x
        mov byte ptr [ebp + {D_ENDOK}], 0
        mov esi, [ebx + {MAPG:#x}]
        test esi, esi
        jz ea_x
        xor edi, edi
    ea_l:
        cmp edi, 32
        jae ea_btn
        bt [ebp + {D_ENDMASK}], edi
        jnc ea_n
        mov eax, [esi + 0x140]
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        cmp edi, eax
        jae ea_btn
        mov edx, edi
        mov eax, [esi + 0x140]
        call {GETPLAYERS:#x}
        test eax, eax
        jz ea_n
        cmp byte ptr [eax + 0x45], 1
        jne ea_n
        push eax
        mov dl, 1
        call {SETENDTURN:#x}
        pop eax
        cmp byte ptr [eax + 0xa7], 0
        je ea_n
        mov eax, [esi + 0x128]
        test eax, eax
        jz ea_n
        mov edx, edi
        call {AI_DEACTIVATE:#x}
    ea_n:
        inc edi
        jmp ea_l
    ea_btn:
        movsx ecx, byte ptr [esi + 0xa5]
        cmp ecx, 32
        jae ea_x
        mov eax, [{X_TOOLBAR:#x}]
        mov eax, [eax]
        test eax, eax
        jz ea_x
        mov eax, [eax + 0x5c]
        test eax, eax
        jz ea_x
        bt [ebp + {D_ENDMASK}], ecx
        setc byte ptr [eax + 0x13c]
        mov byte ptr [eax + 0xa4], 0
    ea_x:
        popad
        ret

    filt:
        push ebx
        push esi
        push edi
        mov ebx, [esp + 0x10]
        test ebx, ebx
        jz f_pass
        mov esi, [eax + 0xc]
        test esi, esi
        jz f_pass
        mov esi, [esi + 8]
        test esi, esi
        jz f_pass
        mov edi, [esi + 8]
        mov esi, [esi + 4]
    f_l:
        dec edi
        js f_drop
        push ecx
        mov ecx, [esi + edi*4]
        cmp [ecx + 0xc], ebx
        pop ecx
        jne f_l
    f_pass:
        pop edi
        pop esi
        pop ebx
        jmp {L['dr_pass2']:#x}
    f_drop:
        pop edi
        pop esi
        pop ebx
        ret 4

    sd_hook:
        cmp ecx, 5
        jb sd_o
        cmp dword ptr [edx], {MAGIC:#x}
        jne sd_o
        jmp {L['dr_hook']:#x}
    sd_o:
        push ebp
        mov ebp, esp
        push 0
        jmp {SD_BACK:#x}
    """
    src = chr(10).join(l.split(";")[0].rstrip() for l in src.split(chr(10)))
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code = bytes(ks.asm(src, CAVE2)[0])
    full = bytes(ks.asm(src + chr(10) + "".join(".long " + q + chr(10) for q in C2_NAMES), CAVE2)[0])
    assert len(code) <= CAVE2_END - CAVE2, hex(len(code))
    return code, dict(zip(C2_NAMES, struct.unpack("<%dI" % len(C2_NAMES), full[-4 * len(C2_NAMES):])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    (cave, nfgate, rechook, ooshook, (yeshook, nohook, cancelhook), (ncthook, cdnhook), (pdhook, clhook), mmhook, lab), st = build_cave(), stub()
    cave2, c2lab = build_cave2(lab)
    r2 = build_cave(c2lab)
    assert r2[-1] == lab and len(r2[0]) == len(cave), 'cave 1 layout moved between passes'
    cave, sdhook = r2[0], c2lab['sd_hook']
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(cave, CAVE):
            print("  %08X %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    e = bytearray(open(EP, "rb").read()); x = bytearray(open(EXE, "rb").read())
    hook_new = bytes([0xE8]) + struct.pack("<i", STUB_VA - (HOOK_VA + 5))
    nf_new = bytes([0xE9]) + struct.pack("<i", nfgate - (NF_SITE + 5)) + bytes([0x90, 0x90])
    rec_new = bytes([0xE9]) + struct.pack("<i", rechook - (REC_SITE + 5)) + bytes([0x90, 0x90])
    xs_sites = [(NCT_SITE, NCT_ORIG, bytes([0xE9]) + struct.pack("<i", ncthook - (NCT_SITE + 5)) + b"\x90" * 2),
                (CDN_SITE, CDN_ORIG, bytes([0xE9]) + struct.pack("<i", cdnhook - (CDN_SITE + 5)) + b"\x90"),
                (YES_SITE, YES_ORIG, bytes([0xE9]) + struct.pack("<i", yeshook - (YES_SITE + 5)) + b"\x90"),
                (NO_SITE, bytes([0xE8]) + struct.pack("<i", EXITGAME - (NO_SITE + 5)), bytes([0xE8]) + struct.pack("<i", nohook - (NO_SITE + 5))),
                (CANCEL_SITE, CANCEL_ORIG, bytes([0xE9]) + struct.pack("<i", cancelhook - (CANCEL_SITE + 5)) + b"\x90" * 3),
                (PD_SITE, PD_ORIG, bytes([0xE9]) + struct.pack("<i", pdhook - (PD_SITE + 5)) + b"\x90" * 2),
                (CL_SITE, CL_ORIG, bytes([0xE9]) + struct.pack("<i", clhook - (CL_SITE + 5)) + b"\x90"),
                (MM_SITE, MM_ORIG, bytes([0xE8]) + struct.pack("<i", mmhook - (MM_SITE + 5)))]
    tmo = x[TMO_SITE - EXE_V2F]
    if tmo not in (0x53, 0xC3):
        print("ABORT: exe DPlayMessageTimeout entry holds a foreign byte %#x" % tmo); return 1
    xs_cur = [bytes(e[va - EP_V2F:va - EP_V2F + len(o)]) for va, o, n in xs_sites]
    for (va, o, n), c in zip(xs_sites, xs_cur):
        if c != o and not (c[0] in (0xE8, 0xE9) and CAVE <= va + 5 + struct.unpack_from("<i", c, 1)[0] < CAVE_END):
            print("ABORT: dialog hook site %#x holds foreign bytes" % va, c.hex()); return 1
    xs_van = all(c == o for (va, o, n), c in zip(xs_sites, xs_cur))
    xs_ours = all(c == n for (va, o, n), c in zip(xs_sites, xs_cur))
    oos_new = bytes([0xE9]) + struct.pack("<i", ooshook - (OOS_SITE + 5))
    ooscur = bytes(e[OOS_SITE - EP_V2F:OOS_SITE - EP_V2F + 5])
    oos_ours = ooscur[0] == 0xE9 and CAVE <= OOS_SITE + 5 + struct.unpack_from("<i", ooscur, 1)[0] < CAVE_END
    if ooscur != OOS_ORIG and not oos_ours:
        print("ABORT: OutOfSync entry holds foreign bytes", ooscur.hex()); return 1
    reccur = bytes(e[REC_SITE - EP_V2F:REC_SITE - EP_V2F + 7])
    rec_ours = reccur[0] == 0xE9 and CAVE <= REC_SITE + 5 + struct.unpack_from("<i", reccur, 1)[0] < CAVE_END
    if reccur != REC_ORIG and not rec_ours:
        print("ABORT: ExecuteCombat entry holds foreign bytes", reccur.hex()); return 1
    st2 = bytes.fromhex("803d") + struct.pack("<I", X_HOLD) + bytes([0])
    st2 += bytes([0x0F, 0x85]) + struct.pack("<i", DRAW_SKIP - (STUB2_VA + len(st2) + 6))
    st2 += bytes.fromhex("837df800")
    st2 += bytes([0x0F, 0x84]) + struct.pack("<i", DRAW_SKIP - (STUB2_VA + len(st2) + 6))
    st2 += bytes([0xE9]) + struct.pack("<i", DRAW_BACK - (STUB2_VA + len(st2) + 5))
    draw_new = bytes([0xE9]) + struct.pack("<i", STUB2_VA - (DRAW_SITE + 5)) + bytes([0x90]) * 5
    st3 = bytes.fromhex("0fa335") + struct.pack("<I", X_RJMASK) + bytes.fromhex("7205")
    st3 += bytes([0xE9]) + struct.pack("<i", JOIN_TARGET - (STUB3_VA + len(st3) + 5)) + bytes([0xC3])
    assert STUB3_VA + len(st3) <= X_RJMASK and len(st2) <= STUB3_VA - STUB2_VA
    st2b = st2 + bytes(STUB3_VA - STUB2_VA - len(st2)) + st3
    join_orig = bytes([0xE8]) + struct.pack("<i", JOIN_TARGET - (JOIN_SITE + 5))
    join_new = bytes([0xE8]) + struct.pack("<i", STUB3_VA - (JOIN_SITE + 5))
    jcur = bytes(x[JOIN_SITE - EXE_V2F:JOIN_SITE - EXE_V2F + 5])
    if jcur not in (join_orig, join_new):
        print("ABORT: exe JoinBtnClick lobby call holds foreign bytes", jcur.hex()); return 1
    s2o, dso = STUB_FO - STUB_VA + STUB2_VA, DRAW_SITE - EXE_V2F
    s2cur, dcur = bytes(x[s2o:s2o + 64]), bytes(x[dso:dso + 10])
    if not ((dcur == DRAW_ORIG and not any(s2cur)) or (dcur == draw_new and s2cur[:len(st2)] == st2)):
        print("ABORT: exe draw site / stub2 zone hold foreign bytes", dcur.hex(), s2cur[:32].hex()); return 1
    ho = HOOK_VA - EXE_V2F
    ecur = bytes(e[CAVE - EP_V2F:CAVE_END - EP_V2F])
    c2cur, sdcur = bytes(e[CAVE2 - EP_V2F:CAVE2_END - EP_V2F]), bytes(e[SD_SITE - EP_V2F:SD_SITE - EP_V2F + 5])
    sd_new = bytes([0xE9]) + struct.pack("<i", sdhook - (SD_SITE + 5))
    sd_ours = sdcur[0] == 0xE9 and CAVE2 <= SD_SITE + 5 + struct.unpack_from("<i", sdcur, 1)[0] < CAVE2_END
    if (sdcur != SD_ORIG and not sd_ours) or (any(c2cur) and not sd_ours):
        print("ABORT: cave 2 / TSetupControl.DataReceived entry hold foreign bytes", sdcur.hex()); return 1
    scur, hcur, nfcur = bytes(x[STUB_FO:STUB_FO + 20]), bytes(x[ho:ho + 5]), bytes(e[NF_SITE - EP_V2F:NF_SITE - EP_V2F + 7])
    nf_ours = nfcur[0] == 0xE9 and CAVE <= NF_SITE + 5 + struct.unpack_from("<i", nfcur, 1)[0] < CAVE_END
    if nfcur != NF_ORIG and not nf_ours:
        print("ABORT: NewFrame gate site holds foreign bytes", nfcur.hex()); return 1
    vanilla = not any(ecur) and not any(scur) and hcur == HOOK_ORIG and nfcur == NF_ORIG and reccur == REC_ORIG and dcur == DRAW_ORIG and ooscur == OOS_ORIG and xs_van and tmo == 0x53 and not any(c2cur) and sdcur == SD_ORIG and jcur == join_orig
    ours = ecur[:len(cave)] == cave and not any(ecur[len(cave):]) and scur == st and hcur == hook_new and nfcur == nf_new and reccur == rec_new and dcur == draw_new and ooscur == oos_new and xs_ours and tmo == 0xC3 and c2cur == cave2 + bytes(CAVE2_END - CAVE2 - len(cave2)) and sdcur == sd_new and jcur == join_new and s2cur[:len(st2b)] == st2b
    rig = scur == st and hcur == hook_new            # some build of the rig
    state = "vanilla" if vanilla else "ours" if ours else "older rig build" if rig else "OTHER"
    ro, rtype = reloc_entry(x, RELOC_VA)
    print("cave 2 %#x (%d B)" % (CAVE2, len(cave2)))
    print("cave %#x (%d B), exe stub %#x, hook %#x, NewFrame gate %#x: %s | reloc %#x type %s" % (
        CAVE, len(cave), STUB_VA, HOOK_VA, NF_SITE, state, RELOC_VA, rtype))
    if state == "OTHER": print("ABORT"); return 1
    if state == ("vanilla" if a.revert else "ours"):
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for p in (EP, EXE):
        b = bak_path(p, BAK)
        if not a.revert and not os.path.exists(b): shutil.copy2(p, b); print("backup ->", b)
    if a.revert:
        ew, xs, xh, rt, nfw, recw = b"", bytes(20), HOOK_ORIG, 3, NF_ORIG, REC_ORIG
    else:
        ew, xs, xh, rt, nfw, recw = cave, st, hook_new, 0, nf_new, rec_new
    with open(EP, "r+b") as f:
        f.seek(CAVE - EP_V2F); f.write(bytes(CAVE_END - CAVE)); f.seek(CAVE - EP_V2F); f.write(ew)
        f.seek(CAVE2 - EP_V2F); f.write(bytes(CAVE2_END - CAVE2))
        if not a.revert: f.seek(CAVE2 - EP_V2F); f.write(cave2)
        f.seek(SD_SITE - EP_V2F); f.write(SD_ORIG if a.revert else sd_new)
        f.seek(NF_SITE - EP_V2F); f.write(nfw)
        f.seek(REC_SITE - EP_V2F); f.write(recw)
        f.seek(OOS_SITE - EP_V2F); f.write(OOS_ORIG if a.revert else oos_new)
        for va, o, n in xs_sites:
            f.seek(va - EP_V2F); f.write(o if a.revert else n)
    with open(EXE, "r+b") as f:
        f.seek(STUB_FO); f.write(xs)
        f.seek(ho); f.write(xh)
        f.seek(s2o); f.write(bytes(64) if a.revert else st2b + bytes(64 - len(st2b)))
        f.seek(JOIN_SITE - EXE_V2F); f.write(join_orig if a.revert else join_new)
        f.seek(dso); f.write(DRAW_ORIG if a.revert else draw_new)
        f.seek(TMO_SITE - EXE_V2F); f.write(b"\x53" if a.revert else b"\xC3")
    print("reverted" if a.revert else "Written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
