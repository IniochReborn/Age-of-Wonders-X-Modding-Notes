#!/usr/bin/env python3
r"""patch_leadership_others_v1.py -- Leadership buffs every OTHER unit in the party, never itself.

Vanilla model (AoWEPACK.dll, ability id 0x2E). Each unit's TLeadershipAbilityData record holds
  [+0x0C] own (inherent) level      [+0x10] borrowed (aura) level      [+0x14] source name
TArmy.UpdateFormation @0x5578D034 (every stack change and combat start):
  pass 1  ResetExternalSource on every unit (borrowed := 0; a record with own==0 is deleted) and
          find max1 = highest GetAbilityLevel(0x2E) in the army (+ that unit's name)
  pass 2  SetExternalSource(max1) on every unit whose level < max1
TLeadershipAbility.GetLevel @0x557661C4 = max(own, borrowed) (item-aware via cave_findrec);
the attack/defence bonus getters (+0x5C @0x557661FC, +0x60 @0x55766210) index the bonus tables
with GetLevel -- so a leader always buffs ITSELF with its own level, and the strongest leader in a
stack never gets anything from a weaker one.

New rule (user, 2026-09-13): a unit's Leadership bonus = the highest OWN Leadership level among the
OTHER units in its party. Never its own level. Two leaders buff each other.

  A  the two bonus getters call cave_blevel instead of GetLevel: bonus level = the unit's own
     record's BORROWED field only ([+0x10]); no record -> 0.  (`mov ecx,[eax]; call [ecx+0x70]`,
     5 bytes each -> `call cave_blevel`.)
  B  pass 2 of UpdateFormation is replaced by cave_pass2 (hook on its first 6 bytes @0x5578D128,
     resume at the function's shared exit 0x5578D186; the vanilla pass-2 bytes stay in place, dead,
     because 0x5578D162 carries a .reloc entry that must not be displaced):
        loop 1: count = #units whose own level == max1, max2 = highest own level below max1
        loop 2: target(u) = max2 if (own(u)==max1 and count==1) else max1
                if target > 0: SetExternalSource(ability, u, target, name)   (creates the record,
                sets the bit, writes borrowed only when own < target) and then, so the top leader
                also receives max2, write [record+0x10] := target directly.
     Own levels are read through the unit's GetAbilityLevel (VMT+0x144), the same call pass 1
     uses, so item-granted Leadership (Crown of Kings) projects an aura like before.

  C  GetLevel (0x55812440 cave tail @0x55812464, 18 bytes in place): returns the OWN level only,
     never the borrowed one. Card text, hero level-up, the map editor and the pre-game customise
     screen therefore see what the unit really has; a follower under an aura lists plain
     "Leadership" (level 0) plus the bonus it receives.

Untouched: hero level-up CanExpand (own < cap), aura garbage collection, the 4-level tables at
0x5580E0C0/0x5580E0C8, and pass 1.

Cave zone 0x55815D00..0x55815DFF (zero, .reloc-free). Rebase-safe: rel32 calls, one call/pop delta
for the AoWHSSet global.  Dry-run default; --apply; --revert; --dll; --dis.
Backup: AoWEPACK.dll.bak_leadership_others
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_leadership_others"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x55700000

LEADERSHIP   = 0x2E
GET_ABDATA   = 0x5574F1C4          # (eax=owner, edx=id) -> record | nil
GET_ABILITY  = 0x557501C0          # (eax=TAbilityControl, edx=id) -> ability
SET_EXTSRC   = 0x55766224          # (eax=ability, edx=unit, cl=level, [stack]=name)  ret 4
AOWHSSET_G   = 0x558FA044          # [g]+0x80 = TAbilityControl        (PIC delta)
SITE_ATK, SITE_DEF = 0x557661FC, 0x55766210     # `mov ecx,[eax]; call [ecx+0x70]`
ORIG_GET     = b"\x8b\x08\xff\x51\x70"
SITE_P2      = 0x5578D128          # cmp dword [ebp-8],0 ; jle 0x5578D186
ORIG_P2      = b"\x83\x7d\xf8\x00\x7e\x58"
P2_EXIT      = 0x5578D186
# C: TLeadershipAbility.GetLevel lives in the item-ability-levels cave (0x55812440, GetLevel is
#    `jmp`-routed there); its record tail returned max(own [+0xC], borrowed [+0x10]). The borrowed
#    level leaked into everything that asks "what level does this unit HAVE" -- the map editor showed
#    a Leadership-I leader as IV while a Frost Queen stood in its party, offered V, and deleting "IV"
#    left a bare bit with no record ("Leadership, cost -5" in the pre-game customise screen).
#    Now: own level only. The aura reaches stats through cave_blevel, nothing else needs it.
# D: name display. TMultiLevelAbility.GetName @0x55765298 (eax=abil, edx=owner, ecx=@result) renders
#    GetLevelName(GetLevel(owner)); Leadership's GetLevelName is the project cave @0x5580E020 (" I".." IV").
#    TLeadershipAbility VMT+0x58 (slot @0x55722060, carries a .reloc entry -- repointing it keeps it
#    rebase-correct) -> cave_lname: original name of the OWN level + " (+<roman> received)" when the
#    unit's record holds a borrowed level. Follower with no own level: "Leadership (+IV received)".
ML_GETNAME   = 0x55765298
SITE_NAME    = 0x55722060                        # TLeadershipAbility VMT+0x58
ORIG_NAME    = struct.pack("<I", ML_GETNAME)
LSTR_CAT3    = 0x55701190                        # _LStrCat3(eax=@dest, edx=s1, ecx=s2)
LSTR_ASG     = 0x55701150                        # _LStrAsg(eax=@dest, edx=src)
LSTR_CLR     = 0x55701140                        # _LStrClr(eax=@s)
SUFFIXES     = [" (+I received)", " (+II received)", " (+III received)", " (+IV received)", " (+V received)"]   # 2026-10-12: V added (user: a Leadership-V aura showed "+IV received")
SITE_GL      = 0x55812464
ORIG_GL      = bytes.fromhex("0fb6480c 0fb65010 3bca 7303 8bc2c3 8bc1c3".replace(" ", ""))   # 18 B
NEW_GL       = b"\x0f\xb6\x40\x0c\xc3" + b"\x90" * 13                     # movzx eax,[eax+0xC]; ret
# E/F (2026-09-17, found live with leadership_probe.py + a hardware watchpoint): C made pass 1 blind to
#    followers.  Pass 1 only resets/removes a unit's record when it has the bit OR GetAbilityLevel > 0;
#    a plain unit whose record survived without its bit (records stream/copy bit-independently, e.g.
#    through save/load) has own = 0 -> skipped, so its record is never removed; pass 2 then finds the
#    record, skips SetExternalSource's create-and-SETBIT path, and only rewrites borrowed.  Result: record
#    with the right borrowed level, bit clear, bonus sum (bit-gated) = 0 -> swordsmen got nothing while
#    units with an own level (bit inherent) did.  Vanilla's max(own,borrowed) GetLevel hid this.
#    E  pass-1 gate call @0x5578D096 (`mov ecx,[eax]; call [ecx+0x144]`, 8 B) -> cave_p1gate: level =
#       max(own, borrowed) from the unit's own record, else the original item-aware GetAbilityLevel.
#       (max1 at 0x5578D0C5 keeps the own-only call.)
#    F  cave_pass2 sets the bit itself ([unit vmt+0x50](0x2E, 1)) after SetExternalSource, so a
#       follower with a pre-existing record still ends up with the bit.
SITE_P1      = 0x5578D096
ORIG_P1      = bytes.fromhex("8b08ff9144010000")
CAVE_LO, CAVE_HI = 0x55815D00, 0x55815F00          # zone 1: cave_blevel, cave_pass2
CAVE2_LO, CAVE2_HI = 0x55862200, 0x55862400        # zone 2 MOVED 2026-10-12 (was 0x558162E0-0x55816400, too small for the 5th suffix and 0x55816400+ belongs to patch_caster_levels_v1.py): cave_lname, cave_p1gate
OLD_ZONE2 = (0x558162E0, 0x55816400)                  # zeroed by hand after the move
ZONES = [(CAVE_LO, CAVE_HI), (CAVE2_LO, CAVE2_HI)]


class Asm:
    def __init__(self, va): self.va, self.buf, self.lab, self.fix = va, bytearray(), {}, []
    def here(self): return self.va + len(self.buf)
    def db(self, *b): self.buf += bytes(b); return self
    def dd(self, v): self.buf += struct.pack("<I", v & 0xFFFFFFFF); return self
    def call(self, t): self.db(0xE8); self.buf += struct.pack("<i", t - (self.here() + 4)); return self
    def jmp(self, t): self.db(0xE9); self.buf += struct.pack("<i", t - (self.here() + 4)); return self
    def label(self, n): self.lab[n] = self.here()
    def j8(self, op, n): self.db(op); self.fix.append((len(self.buf), n, 1)); self.db(0)
    def jmp32(self, n): self.db(0xE9); self.fix.append((len(self.buf), n, 4)); self.dd(0)   # near jmp to label
    def done(self):
        for off, n, size in self.fix:
            rel = self.lab[n] - (self.va + off + size)
            if size == 1:
                assert -128 <= rel <= 127, n
                self.buf[off] = rel & 0xFF
            else:
                struct.pack_into("<i", self.buf, off, rel)
        return bytes(self.buf)


def build_cave_blevel(va):
    """eax=ability, edx=owner -> eax = owner's borrowed Leadership level (0 if no record)."""
    a = Asm(va)
    a.db(0x85, 0xD2); a.j8(0x74, "zero")            # test edx,edx
    a.db(0x8B, 0x48, 0x0C)                          # mov ecx,[eax+0xC]     ; ability id
    a.db(0x8B, 0xC2)                                # mov eax,edx           ; owner
    a.db(0x8B, 0xD1)                                # mov edx,ecx
    a.call(GET_ABDATA)
    a.db(0x85, 0xC0); a.j8(0x74, "zero")
    a.db(0x0F, 0xB6, 0x40, 0x10)                    # movzx eax,byte [eax+0x10]
    a.db(0xC3)
    a.label("zero"); a.db(0x33, 0xC0, 0xC3)         # xor eax,eax; ret
    return a.done()


def build_cave_pass2(va):
    a = Asm(va)
    # frame: [ebp-4]=army [ebp-8]=max1 [ebp-0xC]=name ; ebx/esi are saved by the host, edi is not
    a.db(0x83, 0x7D, 0xF8, 0x00); a.j8(0x7F, "start")       # cmp dword [ebp-8],0 ; jg start
    a.jmp(P2_EXIT)                                          # max1 <= 0 -> nothing to do
    a.label("start")
    a.db(0x57)                                              # push edi
    a.db(0xE8, 0, 0, 0, 0); anchor = a.here()               # call $+5
    a.db(0x5F)                                              # pop edi
    a.db(0x81, 0xEF); a.dd(anchor)                          # sub edi,anchor      ; edi = delta
    a.db(0x6A, 0x00)                                        # push 0              ; [esp+4] = max2
    a.db(0x6A, 0x00)                                        # push 0              ; [esp]   = count

    def unit_count():                                       # esi = [[army+8]+8]
        a.db(0x8B, 0x45, 0xFC); a.db(0x8B, 0x40, 0x08); a.db(0x8B, 0x70, 0x08)
    def unit_i():                                           # ebx = [[army+8]+4][esi]
        a.db(0x8B, 0x45, 0xFC); a.db(0x8B, 0x40, 0x08); a.db(0x8B, 0x40, 0x04); a.db(0x8B, 0x1C, 0xB0)
    def own_level():                                        # eax = ebx.GetAbilityLevel(0x2E)
        a.db(0xBA); a.dd(LEADERSHIP); a.db(0x8B, 0xC3); a.db(0x8B, 0x08); a.db(0xFF, 0x91); a.dd(0x144)

    # ---- loop 1: count of max1 holders, max2
    unit_count()
    a.label("l1"); a.db(0x4E); a.j8(0x78, "l1end")          # dec esi ; js
    unit_i(); own_level()
    a.db(0x3B, 0x45, 0xF8); a.j8(0x75, "notmax")            # cmp eax,[ebp-8]
    a.db(0xFF, 0x04, 0x24); a.j8(0xEB, "l1")                # inc dword [esp]
    a.label("notmax")
    a.db(0x3B, 0x44, 0x24, 0x04); a.j8(0x7E, "l1")          # cmp eax,[esp+4] ; jle
    a.db(0x89, 0x44, 0x24, 0x04); a.j8(0xEB, "l1")          # mov [esp+4],eax
    a.label("l1end")
    # ---- loop 2: apply
    unit_count()
    a.label("l2"); a.db(0x4E); a.j8(0x79, "l2go"); a.jmp32("l2end")   # dec esi ; jns l2go ; jmp l2end (body > 127 B)
    a.label("l2go")
    unit_i(); own_level()
    a.db(0x8B, 0x4D, 0xF8)                                  # mov ecx,[ebp-8]      ; target = max1
    a.db(0x3B, 0xC1); a.j8(0x75, "tgt")                     # own != max1 -> max1
    a.db(0x83, 0x3C, 0x24, 0x01); a.j8(0x75, "tgt")         # count != 1  -> max1 (co-leaders)
    a.db(0x8B, 0x4C, 0x24, 0x04)                            # mov ecx,[esp+4]      ; sole top leader -> max2
    a.label("tgt")
    a.db(0x85, 0xC9); a.j8(0x7E, "l2next")                  # nothing to give
    a.db(0x51)                                              # push ecx             ; keep target
    a.db(0x8B, 0x87); a.dd(AOWHSSET_G)                      # mov eax,[edi+g]
    a.db(0x8B, 0x80); a.dd(0x80)                            # mov eax,[eax+0x80]   ; TAbilityControl
    a.db(0xBA); a.dd(LEADERSHIP); a.call(GET_ABILITY)       # eax = TLeadershipAbility
    a.db(0x8B, 0x0C, 0x24)                                  # mov ecx,[esp]        ; cl = target
    a.db(0xFF, 0x75, 0xF4)                                  # push dword [ebp-0xC] ; name
    a.db(0x8B, 0xD3)                                        # mov edx,ebx
    a.call(SET_EXTSRC)                                      # (pops name)
    # F: force the ability bit - SetExternalSource only sets it when it has to CREATE the record
    a.db(0x56)                                              # push esi
    a.db(0x8B, 0x33)                                        # mov esi,[ebx]        ; vmt
    a.db(0x8B, 0xC3)                                        # mov eax,ebx
    a.db(0xBA); a.dd(LEADERSHIP)                            # mov edx,0x2E
    a.db(0xB9); a.dd(1)                                     # mov ecx,1            ; cl = set
    a.db(0xFF, 0x56, 0x50)                                  # call [esi+0x50]      ; SetAb
    a.db(0x5E)                                              # pop esi
    a.db(0x8B, 0xC3); a.db(0xBA); a.dd(LEADERSHIP); a.call(GET_ABDATA)   # record of ebx
    a.db(0x59)                                              # pop ecx              ; target
    a.db(0x85, 0xC0); a.j8(0x74, "l2next")
    a.db(0x88, 0x48, 0x10)                                  # mov [eax+0x10],cl    ; borrowed := target
    # TUnit caches its ability bonuses ([+0x44..+0x47]) in VMT+0x90 "AbilitiesChanged"; SetExternalSource
    # fired it BEFORE the write above, so re-fire it or a non-hero top leader never sees the bonus.
    a.db(0x8B, 0xC3); a.db(0x8B, 0x10); a.db(0xFF, 0x92); a.dd(0x90)   # mov eax,ebx; mov edx,[eax]; call [edx+0x90]
    a.label("l2next"); a.jmp32("l2")
    a.label("l2end")
    a.db(0x83, 0xC4, 0x08)                                  # add esp,8
    a.db(0x5F)                                              # pop edi
    a.label("done"); a.jmp(P2_EXIT)
    return a.done()


def build_cave_p1gate(va):
    """pass-1 gate: eax=unit, edx=0x2E -> eax = max(own, borrowed) of the unit's own record,
    else the original virtual GetAbilityLevel (item-aware)."""
    a = Asm(va)
    a.db(0x53)                                              # push ebx
    a.db(0x8B, 0xD8)                                        # mov ebx,eax
    a.call(GET_ABDATA)                                      # (eax=owner, edx=id) -> rec | nil
    a.db(0x85, 0xC0); a.j8(0x74, "fallback")
    a.db(0x0F, 0xB6, 0x48, 0x0C)                            # movzx ecx,byte [rec+0xC]   own
    a.db(0x0F, 0xB6, 0x40, 0x10)                            # movzx eax,byte [rec+0x10]  borrowed
    a.db(0x3B, 0xC1); a.j8(0x73, "done")                    # cmp eax,ecx ; jae
    a.db(0x8B, 0xC1)                                        # mov eax,ecx
    a.label("done"); a.db(0x5B, 0xC3)                       # pop ebx ; ret
    a.label("fallback")
    a.db(0x8B, 0xC3)                                        # mov eax,ebx
    a.db(0xBA); a.dd(LEADERSHIP)                            # mov edx,0x2E
    a.db(0x8B, 0x08)                                        # mov ecx,[eax]
    a.db(0xFF, 0x91); a.dd(0x144)                           # call [ecx+0x144]
    a.db(0x5B, 0xC3)                                        # pop ebx ; ret
    return a.done()


def build_cave_lname(va):
    """TLeadershipAbility.GetName(eax=abil, edx=owner, ecx=@result): own-level name + received suffix."""
    a = Asm(va)
    a.db(0x53, 0x56, 0x57, 0x55)                            # push ebx/esi/edi/ebp
    a.db(0x8B, 0xF9); a.db(0x8B, 0xF2); a.db(0x8B, 0xD8)    # edi=@result esi=owner ebx=abil
    a.db(0xE8, 0, 0, 0, 0); anchor = a.here()               # call $+5
    a.db(0x5D)                                              # pop ebp
    a.db(0x81, 0xED); a.dd(anchor)                          # sub ebp,anchor       ; ebp = delta
    a.db(0x6A, 0x00)                                        # push 0               ; temp string at [esp]
    a.db(0x8B, 0xCC); a.db(0x8B, 0xD6); a.db(0x8B, 0xC3)    # ecx=esp edx=owner eax=abil
    a.call(ML_GETNAME)                                      # temp := "Leadership <own>"
    a.db(0x85, 0xF6); a.j8(0x74, "plain")                   # no owner
    a.db(0x8B, 0xC6); a.db(0x8B, 0x53, 0x0C); a.call(GET_ABDATA)   # record of owner
    a.db(0x85, 0xC0); a.j8(0x74, "plain")
    a.db(0x0F, 0xB6, 0x40, 0x10)                            # movzx eax,[rec+0x10] ; borrowed
    a.db(0x85, 0xC0); a.j8(0x74, "plain")
    a.db(0x83, 0xF8, len(SUFFIXES)); a.j8(0x7E, "ok"); a.db(0xB8); a.dd(len(SUFFIXES))   # clamp to the table size (5 since 2026-10-12)
    a.label("ok")
    a.db(0x48)                                              # dec eax             ; 0..4
    a.db(0x8B, 0x8C, 0x85); tbl_ref = len(a.buf); a.dd(0)   # mov ecx,[ebp+eax*4+TABLE]  (patched below)
    a.db(0x03, 0xCD)                                        # add ecx,ebp          ; string bytes (runtime)
    a.db(0x8B, 0x14, 0x24)                                  # mov edx,[esp]        ; temp
    a.db(0x8B, 0xC7)                                        # mov eax,edi          ; @result
    a.call(LSTR_CAT3)                                       # result := temp + suffix
    a.j8(0xEB, "fin")
    a.label("plain")
    a.db(0x8B, 0xC7); a.db(0x8B, 0x14, 0x24); a.call(LSTR_ASG)   # result := temp
    a.label("fin")
    a.db(0x8B, 0xC4); a.call(LSTR_CLR)                      # LStrClr(temp)
    a.db(0x83, 0xC4, 0x04)                                  # add esp,4
    a.db(0x5D, 0x5F, 0x5E, 0x5B)                            # pop ebp/edi/esi/ebx
    a.db(0xC3)
    # ---- data: pointer table (link-time VAs of the string bytes) + AnsiString literals
    while len(a.buf) % 4: a.db(0x90)
    table = a.here()
    struct.pack_into("<I", a.buf, tbl_ref, table)
    for _ in SUFFIXES: a.dd(0)
    for i, s in enumerate(SUFFIXES):
        while len(a.buf) % 4: a.db(0)
        a.dd(0xFFFFFFFF); a.dd(len(s))                      # refcount -1 (never freed), length
        struct.pack_into("<I", a.buf, table - va + i * 4, a.here())
        a.db(*s.encode("ascii")); a.db(0)
    body = a.done()
    for i, s in enumerate(SUFFIXES):                        # self-check: every table slot -> its bytes
        p = struct.unpack_from("<I", body, table - va + i * 4)[0] - va
        assert body[p:p + len(s)] == s.encode("ascii") and body[p - 4] == len(s)
    return body


def layout():
    p = CAVE_LO
    b = build_cave_blevel(p); cave_b = p; p = (p + len(b) + 3) & ~3
    s = build_cave_pass2(p);  cave_s = p; p = (p + len(s) + 3) & ~3
    assert p <= CAVE_HI, "zone 1 cave overflow"
    q = CAVE2_LO
    n = build_cave_lname(q);  cave_n = q; q = (q + len(n) + 3) & ~3
    g = build_cave_p1gate(q); cave_g = q; q = (q + len(g) + 3) & ~3
    assert q <= CAVE2_HI, "zone 2 cave overflow"
    def call(src, dst): return b"\xE8" + struct.pack("<i", dst - (src + 5))
    def jmp(src, dst): return b"\xE9" + struct.pack("<i", dst - (src + 5))
    patches = [
        (SITE_ATK, ORIG_GET, call(SITE_ATK, cave_b), "A  attack-bonus getter: GetLevel -> cave_blevel"),
        (SITE_DEF, ORIG_GET, call(SITE_DEF, cave_b), "A  defence-bonus getter: GetLevel -> cave_blevel"),
        (SITE_P2, ORIG_P2, jmp(SITE_P2, cave_s) + b"\x90", "B  UpdateFormation pass 2 -> cave_pass2"),
        (SITE_GL, ORIG_GL, NEW_GL, "C  GetLevel record tail: max(own,borrowed) -> own only"),
        (SITE_NAME, ORIG_NAME, struct.pack("<I", cave_n), "D  TLeadershipAbility VMT+0x58 GetName -> cave_lname"),
        (SITE_P1, ORIG_P1, call(SITE_P1, cave_g) + b"\x90" * 3, "E  UpdateFormation pass-1 gate -> cave_p1gate (own|borrowed)"),
        (cave_b, bytes(len(b)), b, "cave_blevel"),
        (cave_s, bytes(len(s)), s, "cave_pass2 (+F force bit)"),
        (cave_n, bytes(len(n)), n, "cave_lname"),
        (cave_g, bytes(len(g)), g, "cave_p1gate"),
    ]
    caves = [(cave_b, b, "cave_blevel"), (cave_s, s, "cave_pass2"), (cave_n, n, "cave_lname"), (cave_g, g, "cave_p1gate")]
    return patches, caves, max(p, q)


def in_zone(va):
    return any(lo <= va < hi for lo, hi in ZONES)


def is_stale(va, cur):
    """bytes left by an OLDER build of this script: a cave slot inside our zones, or a hook/pointer
    whose target lies inside our zones."""
    if in_zone(va):
        return True
    if va == SITE_NAME:
        return in_zone(struct.unpack("<I", cur)[0])
    if cur[0] in (0xE8, 0xE9):
        return in_zone(va + 5 + struct.unpack_from("<i", cur, 1)[0])
    return False


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
    return "\n".join("  %08X  %-22s %-6s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str)
                     for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, va))


def write_inplace(path, data):
    assert len(data) == os.path.getsize(path)
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.flush(); os.fsync(f.fileno())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    args = ap.parse_args()
    dll = os.path.abspath(args.dll); bak = bak_path(dll, BAK_SUFFIX)
    data = bytearray(open(dll, "rb").read())
    patches, caves, end = layout()
    print("target: %s\ncaves 0x%X..0x%X (%d B)" % (dll, CAVE_LO, end, end - CAVE_LO))
    if args.dis:
        for va, body, desc in caves:
            print("\n%s @0x%X (%d B)\n%s" % (desc, va, len(body), disasm(body, va)))
    state = []
    for va, old, new, desc in patches:
        off = va2off(data, va); cur = bytes(data[off:off + len(old)])
        state.append("patched" if cur == new else "vanilla" if cur == old else
                     "stale" if is_stale(va, cur) else "OTHER")
    for (va, old, new, desc), s in zip(patches, state):
        print("  [%-7s] %08X  %s" % (s, va, desc))
    if any(s == "OTHER" for s in state):
        print("Aborting: a site holds bytes that are neither vanilla nor this patch."); return 1
    def zero_zones():
        for lo, hi in ZONES:
            o = va2off(data, lo); data[o:o + (hi - lo)] = bytes(hi - lo)
    if args.revert:
        todo = [p for p, s in zip(patches, state) if s in ("patched", "stale")]
        if not todo: print("Nothing applied."); return 1
        zero_zones()
        for va, old, new, desc in todo:
            if not in_zone(va):
                off = va2off(data, va); data[off:off + len(old)] = old
        write_inplace(dll, data); print("Reverted %d site(s); cave zones zeroed." % len(todo)); return 0
    todo = [p for p, s in zip(patches, state) if s in ("vanilla", "stale")]
    if not todo: print("ALL ALREADY PATCHED"); return 0
    if any(s == "stale" for s in state):
        print("stale bytes from an older build detected: upgrading in place (zones rewritten).")
    # 2026-10-12 FIX: zero_zones() below wipes BOTH cave zones, so every site must be rewritten whenever anything is
    # written - the old "only vanilla/stale sites" list left already-[patched] caves zeroed (bit us when zone 2 moved).
    todo = patches
    R = relocs(data)
    hits = [r for va, old, new, desc in todo for r in R if va - 3 <= r < va + len(new) and va != SITE_NAME]
    assert SITE_NAME in R, "VMT slot 0x55722060 should carry a .reloc entry"
    if hits: print("RELOC INTERSECT: %s" % ", ".join("%08X" % h for h in hits)); return 1
    print("no .reloc entry touches any hook window or cave byte; %d site(s) to write." % len(todo))
    if not args.apply: print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak): shutil.copyfile(dll, bak); print("Backup: %s" % bak)
    zero_zones()
    for va, old, new, desc in todo:
        off = va2off(data, va); data[off:off + len(new)] = new; print("Patched: %s" % desc)
    write_inplace(dll, data); print("AoWEPACK.dll patched (Leadership: others only)."); return 0


if __name__ == "__main__":
    sys.exit(main())
