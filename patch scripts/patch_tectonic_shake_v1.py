"""
TECTONIC SHIFT (219) MAP SHAKE (v3.5 10/17: DX/DY forced EVEN - the fog is a 1-px checkerboard stipple; odd shifts flip its phase and read as black flashes after DPI upscaling; user: "make the whole map shake like Tremors but not quite as violent").
AoWEPACK.dll + AoWx.exe.  Independent of patch_tectonic_v1.py (different sites - either can be applied/reverted first).

RE - how Tremors shakes (combat, AoWTCPCK): the Tremors effect handler (0x42BA26..0x42BC40) sends message 0x31010
with an amplitude 1, 2, 3 (then 0x31011 = stop) to every hex ring 1..0x24 around the centre; each unit HS's handler
(0x4215BD / 0x421636) sets its own image offset [hs+0x2C] / [hs+0x30] = RandInt(2a+1) - a and 0x31011 zeroes it -
i.e. a per-object random jitter of up to +-3 px.  The STRATEGIC map has no such mechanism (Town Quake only flags one
city image, [city+0x44] |= 4), so this patch shakes the whole strategic VIEW instead - a camera shake:

EXE (draw side, local / visual only - never touches game state, MP-safe):
  The strategic map is drawn by AoWx.exe 0x451268 (TMapWindow paint) through the HSEPack import thunk 0x401E84 =
  HSEngine.THSMapViewer.ShowScene (eax = viewer, edx/ecx = screen dest, [esp+4] = surface, ret 4).  Both call sites
  (0x4512C0 full-redraw path, 0x4512D7 normal path) -> cave `shk` in .xedt (0x62FD40): while a shake runs it moves
  the viewer's scene origin [viewer+0x30]/[+0x34] by (DX, DY) through the clamping setters SetSceneX/Y (thunks
  0x401E5C / 0x401E64, so the view never leaves the map), calls ShowScene, then writes the true origin back - the
  whole map (terrain, units, effects) jitters, nothing else (mouse picking, minimap logic) ever sees the offset.
  Time = KUSER_SHARED_DATA InterruptTime 0x7FFE0008 (100 ns, no import needed); a new random offset every 40 ms
  (local LCG, not the synced RNG): DX alternates sign with |DX| = 50..100 % of the amplitude, DY = +-50 %;
  amplitude = peak for the first half, then a linear fade to 0 (100 ms attack).
  Vars (.xedt 0x62FD00): +0 REQ (lo16 = ms, hi16 = peak in 1/16 px; written by AoWEPACK), +4 START, +8 DUR (packed,
  0 = idle), +0xC MAGIC 'TSHK' (AoWEPACK only writes REQ when it sees it), +0x10 LASTPH, +0x14 SEED, +0x18 DX,
  +0x1C DY, +0x20 the two sites' original 5-byte calls (exact revert).

AOWEPACK (trigger side, runs on every machine; it only REQUESTS a shake):
  CE  TAirMastery VMT slot 0x557EDF80 (CreateEnchantment; the slot's old value is 0x557F06E4 whose body Tectonic's
      own CE jmp-hooks): [spell+0x10] == 219 -> request CAST shake (1.8 s, |DX| up to 4 px); then jmp the old slot value.
  NT  0x557569DA `call 0x557553C4` in TTurnPlayerControl.NewTurn (the broadcast of msg 0x20020002 that runs every
      player's NEW TURN handlers - incl. Tectonic's per-turn shift at 0x5577D293; dl = the player index): call the
      previous target first, then if that player owns an ACTIVE Tectonic Shift (own copy of the enchantment scan:
      marker [e+0x14] == 219, bit0 [e+0x10], caster [e+0x19]) request a TURN shake (1.4 s, |DX| up to 3 px).
  `req` writes the absolute exe address 0x62FD00 only after checking: PEB ImageBase == 0x400000, SizeOfImage >=
  0x230000 (AoWDevX.exe = 0x13CC00 -> never) and the MAGIC at 0x62FD0C (no reloc entry is added - AoWx.exe has no
  ASLR flag and always sits at 0x400000).
  Zone 0x55873C00..0x55874400 (table at the head keeps the two sites' original bytes).

Dry-run default; --apply (also upgrades an older build in place) / --revert (exact) / --dll / --exe (scratch copies).
Backups <game>\\backup\\AoWEPACK.dll.bak_tshake, AoWx.exe.bak_tshake.

v3.2 (2026-10-17; user: "tectonic shift now has an issue where fog of war flickers (darker) when the spell is cast"):
  the camera shake no longer moves the MAP ENGINE's view.  v1-v3.1 shook by moving the viewer's scene origin through
  THSMapViewer.SetSceneX/Y (HSEPack 0x5560EDF0 / 0x5560EE38) before ShowScene and writing it back after: every new offset
  (25x / s) made ShowScene's THSMap.SetViewPort (0x5560D01C) see a changed view -> ClearViewPort (0x5560D158: every
  scene object SetVisible(false) via VMT+0x68, static AND dynamic scene invalidated [map+0x30]/[map+0x31] := 1), a full
  static/dynamic rebuild for the shaken origin, the map's view-changed broadcast ([map+0x70] -> the AoWE event hub,
  0x558073A8) and the window's OnSceneChanged (MapViewerSceneChanged 0x450F8C: minimap frame) - and between frames the
  map kept the SHAKEN view (+0x80/+0x84, hex range +0x94..+0xA0, which DrawFog 0x55772EB8 iterates) while the viewer
  had been restored.  v3.2 leaves the engine alone: ShowScene is called with the TRUE origin and only its screen
  DESTINATION (edx = x, ecx = y; the static-surface blit and the dynamic/fog lock rect both follow it) is offset by
  (DX, DY), clamped to [0, dest] so the shift never exceeds the 12-px map border (the window's frame is drawn after
  OnPreDrawSurface = MapWindowPreDrawSurface 0x451268, so the overdraw is covered; the far edge keeps <= 4 px of the
  previous frame for the 1.8 s shake).  AoWEPACK half unchanged.  --apply upgrades the exe cave in place (backup
  AoWx.exe.bak_tshake5 = v3.1); --revert unchanged (exact, from the stored original call bytes).
v3.1 (2026-10-17; user: "I want to see the gfx underground / in the depths too"): [map+0x88] is the VIEWED LEVEL
  (0 surface, 1 underground, 2 depths - see aowx-taskbar-coords); the vanilla Air Mastery callback skips its drift
  whenever it is != 0 (clouds only on the surface) and v2/v3's `tect` copied that gate -> 219's fissure (and its shake
  request at T_SPLIT) never drew underground.  v3.1 drops the gate from `tect` only (Air Mastery / Overgrowth / World
  Healer / Ice Age / Drought keep the vanilla surface-only drift).  In-place upgrade v3 -> v3.1; --revert unchanged.
v2 (2026-10-17; user round 3: "when I cast it but have to wait a turn due to its high casting cost, it immediately shakes
the screen despite not being cast yet" + "particles: hover map wide, then split diagonally and move away from each other,
like a fissure opening" + a gritty earthquake sound):
  WHY v1 SHOOK EARLY: TAirMastery's VMT slot +0xA0 (CreateEnchantment) is called by TUnitSpellCaster.SetSelection
  (0x5577A43C) - i.e. when the spell is SELECTED / queued, not when it is cast.  The real cast is
  TAirMastery.ExecuteTE 0x557F05F8 -> TGlobalEnchantmentSpell.ExecuteTE 0x557EF91C -> TGlobalEnchantment.Cast
  (VMT+0x70, 0x5577DCBC: CanActivate +0x6C, Activate +0x68, "... has been cast" message) and only THEN the map-wide
  TAnimation (Create 0x557FB4A8, draw callback 0x557F050C, 90 ticks) + the cast sound.  v2 drops both v1 hooks (CE slot
  and the NT call are restored exactly) and requests the shake from 219's OWN draw callback at the moment the fissure
  splits (tick T_SPLIT) - the callback only exists after a real cast.
  CB  0x557F050C (6 B, the Air Mastery draw callback's prologue `push ebp/mov ebp,esp/add esp,-0x10`; eax = the spell):
      [spell+0x10] == 219 -> `tect`, else the replayed prologue (Air Mastery, Overgrowth, World Healer, Ice Age and
      Drought's drift keep the vanilla scatter).
  tect: the vanilla callback draws Random(3) of slots 0..2 at FRAME TIME 0 (ImageLib.TImageSequenceList.Show(list,
      slot, x, y, time 0, target), so a slot never animates) at fresh positions every tick (System.RandSeed :=
      [map+0x40] - t).  219's own draw instead (own LCG seeded from the animation object, never System.RandSeed / the
      synced RNG - purely local):
      * N = 24 / 48 / 80 (detail 0 / 1 / 2, [[0x558E945C]+0x6D]) hovering green mote clusters (slots 0-2, dim twins
        11-13) at stable positions, bobbing +-3 px (48-tick cycle) and twinkling (bright 26 of every 32 ticks); they
        fade in over 10 ticks (count) and out from T_DIM (dim) / T_THIN (count -> 0 at T_END);
      * T_CRACK..: a jagged fissure (slots 4-6, 64x48 segments laid every (36,-18) px through the screen centre, so
        neighbours join end to end) grows out from the centre one segment per tick each way (CRACK_M max);
      * T_SPLIT: the shake request (1.8 s); every cluster then moves away from the line along its normal (29,57)/64,
        d = (dt+16)*dt*v >> 9 (v = 8..15 px), the side by sign((x-W/2) + 2*(y-H/2)); the crack's two EDGES part with
        the halves (+-half the mean displacement) and the open GAP glows between them (slots 7-9, 80x56);
      * T_GAPEND..T_EDGEEND: the fissure dims (slots 14-16 / 17-19) and retracts from both ends; T_END: Free (as the
        vanilla callback does at 90).
  SND 0x557F06B4 (5 B `mov edx,0x3C`): TAirMastery.ExecuteTE plays GetSpell(0x3C) = AIR MASTERY's cast sound for every
      Air clone (TWaterMastery plays its own [spell+0x28]) -> 219 now plays its own record = DUALER_TECTONIC.WAV.  Only
      219 is redirected (Overgrowth / World Healer / Ice Age still play Air Mastery's sound - same vanilla bug).
  Zone A 0x55873C00.. = MAGIC2 + the two sites' original bytes + caves (all rel32 / PIC; nothing to rebase).
  --apply on a v1 / v1.1 install = in-place upgrade (backup AoWEPACK.dll.bak_tshake2); --revert from v1 or v2 = exact.
  Gfx slots used: 0-2, 4-9, 11-19 (slot 3 deliberately left free for the terrain-change glow).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BAK_SUFFIX = ".bak_tshake"
SPELL_ID = 219
MAGIC = b"TSHAKEv1"                            # v1 / v1.1 zone tag (CE slot + NT hooks) - upgraded in place
MAGIC2 = b"TSHAKEv2"                           # v2 zone tag (draw-callback + cast-sound hooks)
# A/B diagnostic 2026-10-17 (fog-flicker hunt): TECT_SURFACE_ONLY=1 in the environment builds the v3 surface-only fissure
# (vanilla [map+0x88]==0 check restored) - apply it, test one cast, re-apply without it to go back to v3.2.
LVLCHK = ("        mov eax, dword ptr [ecx+%#x]\n        mov eax, dword ptr [eax]\n        cmp dword ptr [eax+0x88], 0\n        jne t_end\n" % 0x558E9494
          if os.environ.get("TECT_SURFACE_ONLY") == "1" else "")
# AoWEPACK
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55873C00, 0x55874400
MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
CE_SLOT, NT_SITE = 0x557EDF80, 0x557569DA        # v1 hooks (removed by v2; recognised for the in-place upgrade / revert)
CB_SITE, CB_VANILLA = 0x557F050C, bytes.fromhex("558bec83c4f0")    # v2: Air Mastery draw-callback prologue
SND_SITE, SND_VANILLA = 0x557F06B4, bytes.fromhex("ba3c000000")    # v2: TAirMastery.ExecuteTE `mov edx,0x3C` (cast sound)
MAP_CELL, DETAIL_CELL, SHOW_THUNK = 0x558E9494, 0x558E945C, 0x55702904   # [[map]] / [[options]]+0x6D detail / ImageLib.TImageSequenceList.Show
N_DETAIL = (24, 48, 80)                          # mote clusters per detail level 0 / 1 / 2 (vanilla Air Mastery: 5 / 10 / 20 big clouds)
T_END, T_CRACK, T_SPLIT, T_GAPEND, T_EDGEEND, T_DIM, T_THIN = 184, 36, 56, 108, 124, 105, 115   # ticks (~34.5 / s); vanilla lasts 90
# v3 (2026-10-17): T_GAPEND / T_EDGEEND / T_DIM / T_THIN are v2-only (no retract / dim twins / thinning any more)
T_FADE, FADE_IN = 96, 12                          # v3: eased fade-out T_FADE..T_END (smoothstep), motes fade in over FADE_IN ticks
TECT_K, TW_DIM = 10, 5                            # v3: brightness levels per image (frame = level via Show's time arg); twinkle = +5 levels
E_MAX = 64                                        # v3: final half-opening of the fissure (px, along the normal); ease-out, never retracts
CRACK_M = 30                                     # fissure segments each side of the centre (36 px apart in x)
SLOT_THIN, SLOT_GAP, SLOT_DIM = 4, 7, 11         # gfx slots: motes 0-2 (+11 dim), crack 4-6 (+10 dim), gap 7-9 (+10 dim)
# AoWx.exe
EXE_BASE, EXE_V2F = 0x400000, 0x400C00
XV = 0x62FD00                                   # vars
XCAVE = 0x62FD40
XEND = 0x62FF00
X_MAGIC = b"TSHK"
SHOW, SETX, SETY = 0x401E84, 0x401E5C, 0x401E64
EXE_SITES = (0x4512C0, 0x4512D7)
CAST_REQ = 1800 | (64 << 16)                    # 1.8 s, peak 4.0 (-> |DX| 2..4 px, |DY| <= 2 px)
# v1.1 2026-10-17 user: shake ONLY on cast, not every turn -> the NT cave just calls the previous target and returns.
TURN_REQ = 1400 | (52 << 16)                    # 1.4 s, peak 3.25 (-> |DX| 1..3 px)

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_pic(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
        s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0])
    k = 0
    while True:
        k = b.find(b"\xe8\x00\x00\x00\x00", k)
        if k < 0: break
        if 0x58 <= b[k + 5] <= 0x5F:
            if b[k + 6] == 0x2D and b[k + 7:k + 11] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 7, va + k + 5)
            elif b[k + 6] == 0x81 and b[k + 8:k + 12] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 8, va + k + 5)
        k += 5
    assert b"\xff\xff\xff\x7f" not in b, "unpatched PIC anchor"
    return bytes(b)


def lv_table():
    """v3: per tick t < T_END the fade 'level' x16 (0 = full brightness, 16*K = gone): a fade-in over FADE_IN ticks and an
    eased (smoothstep) fade-out T_FADE..T_END.  An element draws level (lv16 + its 0..15 dither) >> 4, if < K."""
    out = []
    for t in range(T_END):
        if t < FADE_IN: v = 16 * TECT_K * (1 - (t + 1) / (FADE_IN + 1.0))
        elif t >= T_FADE:
            u = (t - T_FADE) / float(T_END - T_FADE); v = 16 * TECT_K * u * u * (3 - 2 * u)
        else: v = 0
        out.append(int(round(v)))
    assert max(out) < 256
    return bytes(out)


def sep_table():
    """v3: the fissure's half-opening x16 per tick since the split (word table): an eased S-curve - a short ramp-in, then
    1 - (1 - u)^3 - so the halves keep drifting apart, slower and slower, all through the fade (v2 accelerated, then
    retracted the crack)."""
    out = []; L = T_END - T_SPLIT
    for dt in range(L):
        u = dt / float(L); base = 1 - (1 - u) ** 3; ramp = 1 - (1 - min(1.0, dt / 14.0)) ** 2
        out.append(int(round(16 * E_MAX * base * ramp)))
    assert max(out) < 65536
    return out


def build_dll(orig_cb, orig_snd):
    """v2 zone: MAGIC2 + the two sites' original bytes (CB 6 B, SND 5 B), then `req`, `snd`, `tect` (+ subs), `cb`."""
    if orig_cb != CB_VANILLA: raise ValueError("callback entry %#x: unexpected bytes %s" % (CB_SITE, orig_cb.hex()))
    if orig_snd != SND_VANILLA: raise ValueError("cast-sound site %#x: unexpected bytes %s" % (SND_SITE, orig_snd.hex()))
    out = bytearray(MAGIC2 + orig_cb + orig_snd); where = {}
    C = dict(id=SPELL_ID, xv=XV, xmagic=struct.unpack("<I", X_MAGIC)[0], cast=CAST_REQ, cbret=CB_SITE + 6, sndret=SND_SITE + 5,
             mapc=MAP_CELL, lvlchk=LVLCHK, detc=DETAIL_CELL, show=SHOW_THUNK, n0=N_DETAIL[0], n1=N_DETAIL[1], n2=N_DETAIL[2],
             END=T_END, T_CRACK=T_CRACK, T_SPLIT=T_SPLIT, T_GAPEND=T_GAPEND, T_EDGEEND=T_EDGEEND, T_DIM=T_DIM,
             T_THIN=T_THIN, THIN_LEN=T_END - T_THIN, M=CRACK_M, S_THIN=SLOT_THIN, S_GAP=SLOT_GAP, S_DIM=SLOT_DIM,
             K=TECT_K, KM1=TECT_K - 1, TW_DIM=TW_DIM)
    def place(name, src, pic=False):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        s = src % dict(C, **where)
        out.extend(asm_pic(s, va) if pic else bytes(ks.asm(s, va)[0]))
    def place_data(name, blob):
        while len(out) % 16: out.append(0)
        where[name] = ZONE + len(out); out.extend(blob)
    # req: ecx = packed request -> AoWx.exe REQ (only in our game exe); all regs preserved
    place("req", """
        pushad
        mov eax, dword ptr fs:[0x30]
        mov eax, [eax+8]
        cmp eax, 0x400000
        jne r_out
        mov edx, [eax+0x3c]
        cmp dword ptr [eax+edx+0x50], 0x230000
        jb r_out
        cmp dword ptr [%(xv)#x+0xc], %(xmagic)#x
        jne r_out
        mov dword ptr [%(xv)#x], ecx
    r_out:
        popad
        ret
    """)
    # snd (jmp'ed to from TAirMastery.ExecuteTE @0x557F06B4, edi = the spell): vanilla plays GetSpell(0x3C) = AIR
    # MASTERY's cast sound for every Air clone; v2.1 10/17 (user): EVERY clone plays its own record (219 Tectonic, 383
    # Overgrowth, 327 World Healer, 399 Ice Age; Air Mastery 0x3C itself unchanged)
    place("snd", """
        mov edx, dword ptr [edi+0x10]
        jmp %(sndret)#x
    """)
    # tect = 219's own map-wide draw (the TAnimation callback; eax = spell, edx = animation, [ebp+8] = draw target,
    # ret 8).  Frame: -4 LCG seed, -8 t, -0xC N, -0x10 W, -0x14 H, -0x18 loop var, -0x1C x / sx, -0x20 y / sy,
    # -0x24 slot / variant, -0x28 v, -0x2C ph, -0x30 dy, -0x34 x, -0x38 visible count, -0x3C PIC delta,
    # -0x40 crack reach, -0x44 / -0x48 edge offset ex / ey.
    # v3 tables (data, before the code that reads them; PIC-addressed through the [ebp-0x3C] delta)
    place_data("lvt", lv_table())
    place_data("sept", b"".join(struct.pack("<H", v) for v in sep_table()))
    place("tect", """
        push ebp
        mov ebp, esp
        sub esp, 0x60
        push ebx
        push esi
        push edi
        mov ebx, edx
        mov edi, eax
        mov esi, dword ptr [ebp+8]
        mov eax, dword ptr [ebx+0x10]
        mov dword ptr [ebp-8], eax
        call $D
        pop ecx
        sub ecx, $D
        mov dword ptr [ebp-0x3c], ecx
%(lvlchk)s        mov eax, dword ptr [ebp-8]
        cmp eax, %(END)d
        jae t_end
        cmp eax, %(T_SPLIT)d
        jne t_noshake
        mov ecx, %(cast)#x
        call %(req)#x
    t_noshake:
        mov ecx, dword ptr [ebp-0x3c]
        mov eax, dword ptr [ebp-8]
        movzx edx, byte ptr [ecx+eax+%(lvt)#x]
        mov dword ptr [ebp-0x4c], edx
        sub eax, %(T_SPLIT)d
        jg t_s1
        xor eax, eax
    t_s1:
        movzx edx, word ptr [ecx+eax*2+%(sept)#x]
        mov dword ptr [ebp-0x54], edx
        mov eax, dword ptr [ecx+%(detc)#x]
        mov eax, dword ptr [eax]
        mov al, byte ptr [eax+0x6d]
        mov edx, %(n0)d
        cmp al, 0
        je t_n
        mov edx, %(n1)d
        cmp al, 1
        je t_n
        mov edx, %(n2)d
    t_n:
        mov dword ptr [ebp-0xc], edx
        mov eax, dword ptr [ebx+0x34]
        movzx edx, ax
        mov dword ptr [ebp-0x10], edx
        shr eax, 16
        mov dword ptr [ebp-0x14], eax
        mov eax, dword ptr [ebp-8]
        sub eax, %(T_CRACK)d
        jl t_motes
        cmp eax, %(M)d
        jle t_g
        mov eax, %(M)d
    t_g:
        mov dword ptr [ebp-0x40], eax
        mov eax, dword ptr [ebp-0x54]
        sar eax, 4
        mov edx, eax
        imul edx, edx, 29
        sar edx, 6
        mov dword ptr [ebp-0x44], edx
        imul eax, eax, 57
        sar eax, 6
        mov dword ptr [ebp-0x48], eax
        mov eax, dword ptr [ebp-0x40]
        neg eax
        mov dword ptr [ebp-0x18], eax
    t_cl:
        mov eax, dword ptr [ebp-0x18]
        cmp eax, dword ptr [ebp-0x40]
        jg t_motes
        imul edx, eax, 36
        mov ecx, dword ptr [ebp-0x10]
        sar ecx, 1
        add edx, ecx
        mov dword ptr [ebp-0x1c], edx
        imul edx, eax, 18
        mov ecx, dword ptr [ebp-0x14]
        sar ecx, 1
        sub ecx, edx
        mov dword ptr [ebp-0x20], ecx
        add eax, 60
        mov ecx, eax
        imul ecx, ecx, 7
        and ecx, 15
        add ecx, dword ptr [ebp-0x4c]
        shr ecx, 4
        cmp ecx, %(K)d
        jae t_cnext
        mov dword ptr [ebp-0x50], ecx
        xor edx, edx
        mov ecx, 3
        div ecx
        mov dword ptr [ebp-0x24], edx
        cmp dword ptr [ebp-8], %(T_SPLIT)d
        jge t_cs
        add edx, %(S_THIN)d
        mov ecx, dword ptr [ebp-0x1c]
        mov eax, dword ptr [ebp-0x20]
        call t_drw
        jmp t_cnext
    t_cs:
        add edx, %(S_GAP)d
        mov ecx, dword ptr [ebp-0x1c]
        mov eax, dword ptr [ebp-0x20]
        call t_drw
        mov edx, dword ptr [ebp-0x24]
        add edx, %(S_THIN)d
        mov ecx, dword ptr [ebp-0x1c]
        sub ecx, dword ptr [ebp-0x44]
        mov eax, dword ptr [ebp-0x20]
        sub eax, dword ptr [ebp-0x48]
        call t_drw
        mov edx, dword ptr [ebp-0x24]
        add edx, %(S_THIN)d
        mov ecx, dword ptr [ebp-0x1c]
        add ecx, dword ptr [ebp-0x44]
        mov eax, dword ptr [ebp-0x20]
        add eax, dword ptr [ebp-0x48]
        call t_drw
    t_cnext:
        inc dword ptr [ebp-0x18]
        jmp t_cl
    t_motes:
        mov eax, ebx
        xor eax, 0x2545f491
        mov dword ptr [ebp-4], eax
        mov dword ptr [ebp-0x18], 0
    t_ml:
        mov eax, dword ptr [ebp-0x18]
        cmp eax, dword ptr [ebp-0xc]
        jge t_end
        mov eax, dword ptr [ebp-0x10]
        add eax, 200
        call t_rnd
        sub eax, 100
        mov dword ptr [ebp-0x1c], eax
        mov eax, dword ptr [ebp-0x14]
        add eax, 140
        call t_rnd
        sub eax, 70
        mov dword ptr [ebp-0x20], eax
        mov eax, 3
        call t_rnd
        mov dword ptr [ebp-0x24], eax
        mov eax, 8
        call t_rnd
        add eax, 8
        mov dword ptr [ebp-0x28], eax
        mov eax, 48
        call t_rnd
        mov dword ptr [ebp-0x2c], eax
        imul ecx, eax, 11
        and ecx, 15
        add ecx, dword ptr [ebp-0x4c]
        shr ecx, 4
        cmp ecx, %(K)d
        jae t_mnext
        mov edx, dword ptr [ebp-8]
        add edx, eax
        and edx, 31
        cmp edx, 26
        jl t_tw
        add ecx, %(TW_DIM)d
        cmp ecx, %(KM1)d
        jbe t_tw
        mov ecx, %(KM1)d
    t_tw:
        mov dword ptr [ebp-0x50], ecx
        mov eax, dword ptr [ebp-8]
        add eax, dword ptr [ebp-0x2c]
        xor edx, edx
        mov ecx, 48
        div ecx
        mov eax, edx
        sub eax, 24
        cdq
        xor eax, edx
        sub eax, edx
        sar eax, 2
        sub eax, 3
        mov dword ptr [ebp-0x30], eax
        mov eax, dword ptr [ebp-0x54]
        imul eax, dword ptr [ebp-0x28]
        imul eax, eax, 3
        sar eax, 8
        mov ecx, dword ptr [ebp-0x10]
        sar ecx, 1
        mov edx, dword ptr [ebp-0x1c]
        sub edx, ecx
        mov ecx, dword ptr [ebp-0x14]
        sar ecx, 1
        neg ecx
        add ecx, dword ptr [ebp-0x20]
        lea edx, [edx+ecx*2]
        test edx, edx
        jns t_mpos
        neg eax
    t_mpos:
        mov edx, eax
        imul edx, edx, 29
        sar edx, 6
        add edx, dword ptr [ebp-0x1c]
        mov dword ptr [ebp-0x34], edx
        imul eax, eax, 57
        sar eax, 6
        add eax, dword ptr [ebp-0x20]
        add eax, dword ptr [ebp-0x30]
        mov edx, dword ptr [ebp-0x24]
        mov ecx, dword ptr [ebp-0x34]
        call t_drw
    t_mnext:
        inc dword ptr [ebp-0x18]
        jmp t_ml
    t_end:
        cmp dword ptr [ebx+0x10], %(END)d
        jl t_ret
        mov dl, 1
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx-4]
    t_ret:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 8
    t_rnd:
        push ecx
        push edx
        mov ecx, eax
        mov eax, dword ptr [ebp-4]
        imul eax, eax, 0x08088405
        inc eax
        mov dword ptr [ebp-4], eax
        mul ecx
        mov eax, edx
        pop edx
        pop ecx
        ret
    t_drw:
        add ecx, dword ptr [esi+0x10]
        add eax, dword ptr [esi+0x14]
        push eax
        push dword ptr [ebp-0x50]
        push esi
        mov eax, dword ptr [edi+0x2c]
        call %(show)#x
        ret
    """, pic=True)
    # cb (jmp'ed to from the Air Mastery draw callback's entry; eax = the spell): 219 -> `tect`, else the vanilla
    # prologue and on (Air Mastery, Overgrowth, World Healer, Ice Age and Drought's drift keep the vanilla scatter)
    place("cb", """
        cmp dword ptr [eax+0x10], %(id)d
        je %(tect)#x
        push ebp
        mov ebp, esp
        add esp, -0x10
        jmp %(cbret)#x
    """)
    return bytes(out), where


def build_exe(orig_sites):
    prevs = set()
    for va, ob in zip(EXE_SITES, orig_sites):
        if ob[0] != 0xE8: raise ValueError("exe site %#x: unexpected bytes %s" % (va, ob.hex()))
        prevs.add(va + 5 + struct.unpack_from("<i", ob, 1)[0])
    if len(prevs) != 1: raise ValueError("exe sites call different targets: %s" % [hex(p) for p in prevs])
    C = dict(xv=XV, show=prevs.pop(), setx=SETX, sety=SETY)
    src = """
        push ebp
        mov ebp, esp
        push ebx
        push esi
        push edi
        mov ebx, eax
        push edx
        push ecx
        mov eax, dword ptr [%(xv)#x]
        test eax, eax
        jz s_run
        mov dword ptr [%(xv)#x], 0
        mov dword ptr [%(xv)#x+8], eax
        mov ecx, dword ptr [0x7ffe0008]
        mov dword ptr [%(xv)#x+4], ecx
        mov dword ptr [%(xv)#x+0x10], -1
    s_run:
        mov esi, dword ptr [%(xv)#x+8]
        test esi, esi
        jz s_plain
        mov eax, dword ptr [0x7ffe0008]
        sub eax, dword ptr [%(xv)#x+4]
        xor edx, edx
        mov ecx, 10000
        div ecx
        movzx ecx, si
        cmp eax, ecx
        jae s_stop
        mov edi, eax
        sub ecx, eax
        shr esi, 16
        add ecx, ecx
        mov eax, esi
        imul eax, ecx
        xor edx, edx
        movzx ecx, word ptr [%(xv)#x+8]
        div ecx
        cmp eax, esi
        jbe s_env
        mov eax, esi
    s_env:
        cmp edi, 100
        jae s_amp
        imul eax, edi
        xor edx, edx
        mov ecx, 100
        div ecx
    s_amp:
        mov esi, eax
        mov eax, edi
        xor edx, edx
        mov ecx, 40
        div ecx
        cmp eax, dword ptr [%(xv)#x+0x10]
        je s_apply
        mov dword ptr [%(xv)#x+0x10], eax
        mov edi, eax
        mov eax, dword ptr [%(xv)#x+0x14]
        imul eax, eax, 1103515245
        add eax, 12345
        mov dword ptr [%(xv)#x+0x14], eax
        shr eax, 16
        and eax, 0x3f
        add eax, 64
        imul eax, esi
        sar eax, 11
        test edi, 1
        jz s_dx
        neg eax
    s_dx:
        and eax, 0xfffffffe
        mov dword ptr [%(xv)#x+0x18], eax
        mov eax, dword ptr [%(xv)#x+0x14]
        imul eax, eax, 1103515245
        add eax, 12345
        mov dword ptr [%(xv)#x+0x14], eax
        shr eax, 16
        and eax, 0xff
        sub eax, 128
        imul eax, esi
        sar eax, 12
        and eax, 0xfffffffe
        mov dword ptr [%(xv)#x+0x1c], eax
    s_apply:
        mov eax, dword ptr [%(xv)#x+0x18]
        mov edx, dword ptr [ebp-0x10]
        cmp eax, edx
        jle s_ax
        mov eax, edx
    s_ax:
        add edx, eax
        jns s_xok
        xor edx, edx
    s_xok:
        mov eax, dword ptr [%(xv)#x+0x1c]
        mov ecx, dword ptr [ebp-0x14]
        cmp eax, ecx
        jle s_ay
        mov eax, ecx
    s_ay:
        add ecx, eax
        jns s_yok
        xor ecx, ecx
    s_yok:
        push dword ptr [ebp+8]
        mov eax, ebx
        call %(show)#x
        jmp s_done
    s_stop:
        mov dword ptr [%(xv)#x+8], 0
    s_plain:
        push dword ptr [ebp+8]
        mov ecx, dword ptr [ebp-0x14]
        mov edx, dword ptr [ebp-0x10]
        mov eax, ebx
        call %(show)#x
    s_done:
        lea esp, [ebp-0xc]
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 4
    """ % C
    code = bytes(ks.asm(src, XCAVE)[0])
    assert XCAVE + len(code) <= XEND, "exe cave overflow"
    vars_ = bytearray(0x40)
    vars_[0x0C:0x10] = X_MAGIC
    struct.pack_into("<I", vars_, 0x14, 0x2545F491)                       # LCG seed
    vars_[0x20:0x2A] = orig_sites[0] + orig_sites[1]
    return bytes(vars_) + code


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


def foff(d, base, va):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    rva = va - base
    for k in range(nsec):
        vs, sva, rs, ro = struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8)
        if sva <= rva < sva + min(max(vs, rs), rs if rs else vs): return ro + rva - sva
    raise ValueError(hex(va))


def call_to(site, tgt):
    return b"\xe8" + struct.pack("<i", tgt - (site + 5))


def jmp_to(site, tgt):
    return b"\xe9" + struct.pack("<i", tgt - (site + 5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    ap.add_argument("--dll", default=None); ap.add_argument("--exe", default=None)
    a = ap.parse_args()
    dll = a.dll or game_file("AoWEPACK.dll"); exe = a.exe or game_file("AoWx.exe")
    d = bytearray(open(dll, "rb").read()); e = bytearray(open(exe, "rb").read())
    print("targets:", dll, "|", exe)
    in_zone = lambda t: ZONE <= t < ZONE_END
    # ---- AoWEPACK state: "zero" | "v1" (CE slot + NT hooks) | "v2" (draw-callback + cast-sound hooks)
    rl = relocs(bytes(d), BASE)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or CB_SITE - 3 < r < CB_SITE + 6 or SND_SITE - 3 < r < SND_SITE + 5]
    if bad: print("ABORT: relocs in zone / hook sites %s" % bad); return 1
    zo = foff(d, BASE, ZONE); zl = bytes(d[zo:zo + ZONE_END - ZONE])
    so = foff(d, BASE, CE_SLOT); no = foff(d, BASE, NT_SITE); co = foff(d, BASE, CB_SITE); po = foff(d, BASE, SND_SITE)
    live_slot, live_nt, live_cb, live_snd = bytes(d[so:so + 4]), bytes(d[no:no + 5]), bytes(d[co:co + 6]), bytes(d[po:po + 5])
    if zl[:8] == MAGIC:
        dver = "v1"; v1_slot, v1_nt = zl[8:12], zl[12:17]
        ok_slot = in_zone(struct.unpack("<I", live_slot)[0])
        ok_nt = live_nt[0] == 0xE8 and in_zone(NT_SITE + 5 + struct.unpack_from("<i", live_nt, 1)[0])
        if not (ok_slot and ok_nt):
            print("ABORT: v1 zone present but its CE slot / NT site was taken over (slot %s, NT %s)" % (live_slot.hex(), live_nt.hex())); return 1
        orig_cb, orig_snd = live_cb, live_snd
    elif zl[:8] == MAGIC2:
        dver = "v2"; orig_cb, orig_snd = zl[8:14], zl[14:19]
    elif any(zl): print("ABORT: AoWEPACK zone %#x..%#x is not free" % (ZONE, ZONE_END)); return 1
    else: dver = "zero"; orig_cb, orig_snd = live_cb, live_snd
    # ---- exe state (unchanged since v1)
    erl = relocs(bytes(e), EXE_BASE)
    ebad = [hex(r) for r in erl if XV <= r < XEND or any(s <= r < s + 5 for s in EXE_SITES)]
    if ebad: print("ABORT: exe relocs in cave/sites %s" % ebad); return 1
    xo = foff(e, EXE_BASE, XV); xl = bytes(e[xo:xo + XEND - XV])
    live_sites = [bytes(e[foff(e, EXE_BASE, s):foff(e, EXE_BASE, s) + 5]) for s in EXE_SITES]
    if xl[0x0C:0x10] == X_MAGIC: orig_sites = [xl[0x20:0x25], xl[0x25:0x2A]]; estored = True
    elif any(xl): print("ABORT: exe area %#x..%#x is not free" % (XV, XEND)); return 1
    else: orig_sites = live_sites; estored = False
    try:
        dcode, where = build_dll(orig_cb, orig_snd)
        xcode = build_exe(orig_sites)
    except ValueError as ex:
        print("ABORT:", ex); return 1
    assert ZONE + len(dcode) <= ZONE_END, "zone overflow"
    want_cb = jmp_to(CB_SITE, where["cb"]) + b"\x90"
    want_snd = jmp_to(SND_SITE, where["snd"])
    want_sites = [call_to(s, XCAVE) for s in EXE_SITES]
    def st(live, want, stored, tgt_ok):
        if not stored: return "free"
        if live == want: return "ours"
        return "ours(old)" if tgt_ok(live) else "OTHER"
    def dst(live, want, vanilla):
        if dver != "v2": return "free" if live == vanilla else "OTHER"
        if live == want: return "ours"
        return "ours(old)" if live[0] == 0xE9 and in_zone(struct.unpack_from("<i", live, 1)[0] + (CB_SITE if len(want) == 6 else SND_SITE) + 5) else "OTHER"
    s_cb = dst(live_cb, want_cb, CB_VANILLA); s_snd = dst(live_snd, want_snd, SND_VANILLA)
    s_x = [st(l, w, estored, lambda b, s=s: b[0] == 0xE8 and XV <= s + 5 + struct.unpack_from("<i", b, 1)[0] < XEND)
           for l, w, s in zip(live_sites, want_sites, EXE_SITES)]
    print("AoWEPACK zone %s (%d B) | draw-callback entry %s | cast sound %s%s" % (dver, len(dcode), s_cb, s_snd,
          " | v1 hooks live (CE slot -> %#x, NT) - removed by the v2 upgrade on --apply" % struct.unpack("<I", live_slot)[0] if dver == "v1" else ""))
    print("AoWx.exe area %s (%d B) | sites %s" % ("ours" if estored else "zero", len(xcode), s_x))
    print("caves " + ", ".join("%s=%#x" % kv for kv in where.items()) + ", shk=%#x" % XCAVE)
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(dcode[where["req"] - ZONE:], where["req"]): print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if dver == "zero" and not estored: print("already vanilla"); return 0
        if (dver == "v2" and "OTHER" in (s_cb, s_snd)) or "OTHER" in s_x:
            print("ABORT: a site no longer points at us (revert that patch first)"); return 1
        if dver == "v1":
            d[so:so + 4] = v1_slot; d[no:no + 5] = v1_nt
        elif dver == "v2":
            d[co:co + 6] = orig_cb; d[po:po + 5] = orig_snd
        if dver != "zero":
            d[zo:zo + ZONE_END - ZONE] = bytes(ZONE_END - ZONE)
            with open(dll, "r+b") as f: f.write(bytes(d))
        if estored:
            for s, ob in zip(EXE_SITES, orig_sites):
                o = foff(e, EXE_BASE, s); e[o:o + 5] = ob
            e[xo:xo + XEND - XV] = bytes(XEND - XV)
            with open(exe, "r+b") as f: f.write(bytes(e))
        print("reverted (%s; exe sites %s)" % (dver, [b.hex() for b in orig_sites])); return 0
    if "OTHER" in (s_cb, s_snd) or "OTHER" in s_x:
        print("ABORT: a site we need was taken over by someone else (callback %s, sound %s, exe %s)" % (live_cb.hex(), live_snd.hex(), s_x)); return 1
    nd = bytearray(d); ne = bytearray(e)
    if dver == "v1":                                   # in-place upgrade: put the v1 hooks back first
        nd[so:so + 4] = v1_slot; nd[no:no + 5] = v1_nt
    nd[zo:zo + ZONE_END - ZONE] = dcode + bytes(ZONE_END - ZONE - len(dcode))
    nd[co:co + 6] = want_cb; nd[po:po + 5] = want_snd
    ne[xo:xo + XEND - XV] = xcode + bytes(XEND - XV - len(xcode))
    for s, w in zip(EXE_SITES, want_sites):
        o = foff(ne, EXE_BASE, s); ne[o:o + 5] = w
    nch = sum(1 for x, y in zip(d, nd) if x != y) + sum(1 for x, y in zip(e, ne) if x != y)
    if nd == d and ne == e: print("already applied (v3.2)"); return 0
    print("%d bytes change%s" % (nch, " (in-place upgrade v1 -> v3)" if dver == "v1" else " (in-place upgrade v2 -> v3)" if dver == "v2" else ""))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for path, old, new, given in ((dll, d, nd, a.dll), (exe, e, ne, a.exe)):
        if old == new: continue
        if given is None:
            # v3.1: a v2-tagged zone (v2 or v3) upgrades to .bak_tshake4 (keeps .bak_tshake3 = the v2 state)
            # v3.2: the exe cave change backs the v3.1 exe up to AoWx.exe.bak_tshake5 (the old .bak_tshake = vanilla stays)
            bak = bak_path(path, BAK_SUFFIX + ({"v1": "2", "v2": "4"}.get(dver, "") if path == dll else ("5" if estored else "")))
            if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
        with open(path, "r+b") as f: f.write(bytes(new))
        assert open(path, "rb").read() == bytes(new)
    print("written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
