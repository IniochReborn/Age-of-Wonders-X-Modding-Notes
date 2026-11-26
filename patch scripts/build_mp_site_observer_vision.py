#!/usr/bin/env python3
r"""MP exploration-site combat: give OBSERVERS the explorer's map vision.

PROBLEM (user, 2026-08-11): in MP the tactical/auto dialog now works for
exploration sites, and observers are correctly pulled into combat observation,
but the site's tactical map is 100% black for them.

ROOT CAUSE (RE'd 2026-08-11):
`AoWTC.TAoWCombatMap.NewTurn` @0x41BB30 decides per machine whether the local
box controls the player whose turn it is:

    0041BD0E TPlayerList.GetPlayers(pid) ; pid = [combatplayer+8]
    0041BD13 cmp byte [player+0xA7],0 / jne 0x41BED8       ; AI/eliminated
    0041BD4B TPlayerCommunicationControl.GetPlayers(pid)
    0041BD50 cmp byte [commsrec+8],1  / je  0x41BED8       ; ==1 => REMOTE
    0041BD5A <local>  SetSeatedCombatPlayer([map+0xED]) -> GetNextUnit -> select
    0041BED8 <remote> PlaySample + InitMsg + vcall [map_vmt+0x68]

On an observer every combat player is remote, so NewTurn always takes the
0x41BED8 branch and **SetSeatedCombatPlayer is never called**. That call is what
resolves the combat player to an AoW player id and hands it to
`TAbstractAoWHSMap.SetSeatedPlayer` (vcall [map_vmt+0xF8]) - i.e. it chooses
whose explored-bitmask the renderer looks through. With no seated player there
is no viewing player, so every combat tile draws unexplored => black.
(The per-tile mask is [combatfield+0x18], one bit per player; it is only ever
filled in by PARTICIPANTS' units - ExploreArea is called solely from
TCombatMoveTE.ExecuteDefaultMove and TTacticalCombatUnitHS.Activate.)

FIX (user's preference: observers see EXACTLY what the explorer sees, rather
than simply switching fog off): on the remote/observer path, seat the explorer
for VIEWING only. Control is unaffected - unit selection lives further down the
local-only path, which observers still skip.

Guards, so nothing else changes:
  * only when the local player is NOT a participant in this combat (local id
    [AoWHSMap+0xA5] is compared against every combat player's id) - so a normal
    PvP battle never seats your opponent;
  * seat the first NON-NEUTRAL combat player (a site's defenders are player 0),
    so the observer follows the explorer and not the lair;
  * skip if that player is already seated (avoids a redundant
    SeatedPlayerChanged notify every turn).

Hook: 5 bytes at 0x41BED8 (`mov eax,0x41BFA0`) -> `call cave`; the cave restores
eax before returning, so the displaced instruction still happens.
Cave @0x438500 (AoWTCPCK CODE zero region; 0x438100-0x438500 is Void Step's).
⚠ AoWTCPCK ALWAYS rebases, so the cave is position independent (call/pop delta)
and the .reloc entry for the displaced imm32 at 0x41BED9 is neutralized 3->0.

Backup AoWTCPCK.dll.bak_sitevision. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWTCPCK.dll")
BAK = DLL + ".bak_sitevision"

VA2FILE = 0x400C00
CAVE, CAVE_END = 0x438500, 0x4385C0     # 0x4385C0+ = the GetExplored nil-guard
SITE = 0x41BED8
SITE_OLD = bytes.fromhex("B8A0BF4100")          # mov eax,0x41BFA0
RESUME = SITE + 5
SAMPLE_PTR = 0x41BFA0

AOWHSMAP_PP = 0x46E8D4                          # -> -> TAoWHSMap
F_GETCOUNT = 0x430BC0                           # TTacticalCombatPlayerList.GetCount(eax)
F_GETPLAYERS = 0x430BF0                         # ...GetPlayers(eax=list, dl=idx)
F_SETSEAT = 0x41BAB8                            # TAoWCombatMap.SetSeatedCombatPlayer(eax,dl)

M_PLAYERLIST = 0xE0                             # [map+0xE0] TTacticalCombatPlayerList
M_SEATED = 0xEC                                 # [map+0xEC] seated combat player idx
P_PLAYERID = 8                                  # [combatplayer+8] AoW player id
HS_LOCALPLAYER = 0xA5                           # [AoWHSMap+0xA5] local seated player


class Asm:
    def __init__(self, org):
        self.org, self.buf, self.labels = org, bytearray(), {}
        self.f32, self.f8 = [], []

    def here(self): return self.org + len(self.buf)
    def lab(self, n): self.labels[n] = self.here()
    def db(self, *b): self.buf.extend(b)
    def dd(self, v): self.buf.extend((v & 0xFFFFFFFF).to_bytes(4, "little"))

    def rel32(self, op, t):
        self.buf.extend(op); self.f32.append((len(self.buf), t)); self.dd(0)

    def call(self, t): self.rel32(b"\xE8", t)
    def jmp(self, t): self.rel32(b"\xE9", t)

    def j8(self, op, lbl):
        self.db(op); self.f8.append((len(self.buf), lbl)); self.db(0)

    def jcc(self, cc, lbl):
        """near conditional jump (0F 8x rel32); cc = the short opcode"""
        self.rel32(bytes([0x0F, 0x80 | (cc & 0x0F)]), lbl)

    def resolve(self):
        for pos, t in self.f32:
            t = self.labels[t] if isinstance(t, str) else t
            struct.pack_into("<i", self.buf, pos, t - (self.org + pos + 4))
        for pos, lbl in self.f8:
            d = self.labels[lbl] - (self.org + pos + 1)
            assert -128 <= d < 128, "j8 out of range to %s" % lbl
            struct.pack_into("<b", self.buf, pos, d)
        return bytes(self.buf)


def build_cave():
    a = Asm(CAVE)
    a.db(0x60)                                   # pushad  (ebp = NewTurn frame, untouched)
    a.call(a.here() + 5)                         # -- PIC delta --
    pop_va = a.here()
    a.db(0x5B)                                   # pop ebx
    a.db(0x81, 0xEB); a.dd(pop_va)               # sub ebx,static  -> ebx = load delta

    a.db(0x8B, 0x75, 0xFC)                       # mov esi,[ebp-4]   (the combat map)
    a.db(0x85, 0xF6)                             # test esi,esi
    a.jcc(0x74, "done")

    a.db(0xB8); a.dd(AOWHSMAP_PP)                # mov eax,&&AoWHSMap
    a.db(0x03, 0xC3)                             # add eax,ebx
    a.db(0x8B, 0x00)                             # mov eax,[eax]
    a.db(0x85, 0xC0); a.jcc(0x74, "done")
    a.db(0x8B, 0x00)                             # mov eax,[eax]     (TAoWHSMap)
    a.db(0x85, 0xC0); a.jcc(0x74, "done")
    a.db(0x0F, 0xBE, 0xB8); a.dd(HS_LOCALPLAYER)  # movsx edi,byte [eax+0xA5] local id

    a.db(0x8B, 0x86); a.dd(M_PLAYERLIST)         # mov eax,[esi+0xE0]  player list
    a.db(0x85, 0xC0); a.jcc(0x74, "done")
    a.call(F_GETCOUNT)                           # eax = count
    a.db(0x85, 0xC0)
    a.jcc(0x7E, "done")                          # jle
    a.db(0x8B, 0xC8)                             # mov ecx,eax   (count)
    a.db(0x31, 0xD2)                             # xor edx,edx   (idx)
    a.db(0x6A, 0xFF)                             # push -1       (explorer idx slot)

    a.lab("loop")
    a.db(0x39, 0xCA)                             # cmp edx,ecx
    a.j8(0x7D, "after")                          # jge
    a.db(0x51, 0x52)                             # push ecx; push edx
    a.db(0x8B, 0x86); a.dd(M_PLAYERLIST)         # mov eax,[esi+0xE0]
    a.call(F_GETPLAYERS)                         # GetPlayers(eax=list, dl=idx)
    a.db(0x5A, 0x59)                             # pop edx; pop ecx
    a.db(0x85, 0xC0)
    a.j8(0x74, "next")
    a.db(0x0F, 0xBE, 0x40, P_PLAYERID)           # movsx eax,byte [eax+8]  AoW player id
    a.db(0x39, 0xF8)                             # cmp eax,edi   (local player?)
    a.j8(0x74, "bail")                           # -> we ARE a participant, change nothing
    a.db(0x85, 0xC0)                             # test eax,eax
    a.j8(0x74, "next")                           # id 0 = neutral/independent -> skip
    a.db(0x83, 0x3C, 0x24, 0xFF)                 # cmp dword [esp],-1
    a.j8(0x75, "next")                           # already have one
    a.db(0x89, 0x14, 0x24)                       # mov [esp],edx   (first non-neutral)
    a.lab("next")
    a.db(0x42)                                   # inc edx
    a.jmp("loop")

    a.lab("bail")
    a.db(0x83, 0xC4, 0x04)                       # add esp,4
    a.j8(0xEB, "done")

    a.lab("after")
    a.db(0x58)                                   # pop eax   (explorer idx)
    a.db(0x83, 0xF8, 0xFF)                       # cmp eax,-1
    a.j8(0x74, "done")
    a.db(0x0F, 0xBE, 0x96); a.dd(M_SEATED)       # movsx edx,byte [esi+0xEC] current seat
    a.db(0x39, 0xD0)                             # cmp eax,edx
    a.j8(0x74, "done")                           # already seated -> no redundant notify
    a.db(0x8B, 0xD0)                             # mov edx,eax   (dl = idx)
    a.db(0x8B, 0xC6)                             # mov eax,esi   (the combat map)
    a.call(F_SETSEAT)                            # SetSeatedCombatPlayer -> SetSeatedPlayer
    # ...then drop the SEAT again, keeping only the VIEW. SetSeatedCombatPlayer
    # sets [map+0xEC] (the combat seat) *and* calls SetSeatedPlayer which sets
    # [map+0xA5] (the viewing player used by GetExplored/fog) and fires the
    # SeatedPlayerChanged redraw. We want the vision + the redraw but NOT the
    # seat: while [map+0xEC] holds a player the UI treats this machine as
    # playing them - the observer could click their units ("cannot create
    # remote"), press end-turn, and saw their gold/mana. 0xFF = "nobody
    # seated", the game's own sentinel.
    a.db(0xC6, 0x86); a.dd(M_SEATED); a.db(0xFF)  # mov byte [esi+0xEC],0xFF

    a.lab("done")
    a.db(0x61)                                   # popad  (ebx/delta restored away)
    a.call(a.here() + 5)                         # -- PIC delta again, for the return value
    pop2 = a.here()
    a.db(0x58)                                   # pop eax
    a.db(0x2D); a.dd(pop2 - SAMPLE_PTR)          # sub eax,(static-0x41BFA0) -> runtime ptr
    a.db(0xC3)                                   # ret -> 0x41BEDD `call PlaySample`
    return a.resolve()


def reloc_entries(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    sec0 = pe + 24 + struct.unpack_from("<H", data, pe + 20)[0]
    raw = size = None
    for i in range(nsec):
        o = sec0 + i * 40
        if data[o:o+8].rstrip(b"\0") == b".reloc":
            size, _, _, raw = struct.unpack_from("<IIII", data, o + 8)
    assert raw, "no .reloc"
    out, p = [], raw
    while p < raw + size:
        page, bsz = struct.unpack_from("<II", data, p)
        if bsz == 0:
            break
        for q in range(p + 8, p + bsz, 2):
            e = struct.unpack_from("<H", data, q)[0]
            out.append((q, 0x400000 + page + (e & 0xFFF), e >> 12))
        p += bsz
    return out


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode == "--revert":
        if not os.path.exists(BAK):
            sys.exit("no backup")
        shutil.copyfile(BAK, DLL)
        print("reverted", DLL)
        return

    data = bytearray(open(DLL, "rb").read())
    got = data[SITE - VA2FILE: SITE - VA2FILE + 5]
    hook_now = b"\xE8" + struct.pack("<i", CAVE - (SITE + 5))
    recave = (got == hook_now)          # hook already in place: refresh the cave only
    if recave:
        print("hook already installed - rewriting the cave in place")
    else:
        assert got == SITE_OLD, "site mismatch: %s != %s" % (got.hex(), SITE_OLD.hex())
        assert not any(data[CAVE - VA2FILE: CAVE_END - VA2FILE]), "cave not empty"

    rels = reloc_entries(data)
    tgt = [(q, va, t) for q, va, t in rels if va == SITE + 1 and t == 3]
    if not recave:
        # the displaced imm32 at 0x41BED9 MUST have a HIGHLOW we neutralize
        assert len(tgt) == 1, "unexpected reloc at %#x: %s" % (SITE + 1, tgt)
    inside = [(hex(va), t) for _, va, t in rels if CAVE <= va < CAVE_END and t == 3]
    assert not inside, "relocs inside the cave: %s" % inside

    code = build_cave()
    assert len(code) <= CAVE_END - CAVE, "cave overflow %#x" % len(code)
    hook = b"\xE8" + struct.pack("<i", CAVE - (SITE + 5))

    print("cave  @ %08X  len %d bytes" % (CAVE, len(code)))
    print("hook  @ %08X  %s -> %s" % (SITE, SITE_OLD.hex(' '), hook.hex(' ')))
    print("reloc @ %s" % ("file %#x VA %08X  type 3 -> 0" % (tgt[0][0], tgt[0][1])
                          if tgt else "already neutralised"))
    if mode != "--apply":
        print("dry run OK - rerun with --apply")
        return

    if not os.path.exists(BAK):
        shutil.copyfile(DLL, BAK)
        print("backup ->", os.path.basename(BAK))
    data[CAVE - VA2FILE: CAVE - VA2FILE + len(code)] = code
    if not recave:
        data[SITE - VA2FILE: SITE - VA2FILE + 5] = hook
        q = tgt[0][0]
        e = struct.unpack_from("<H", data, q)[0]
        struct.pack_into("<H", data, q, e & 0x0FFF)      # type 3 -> 0 (absolute/no-op)
    open(DLL, "wb").write(data)
    print("APPLIED - observers now view through the exploring player.")


main()
