#!/usr/bin/env python3
r"""Item-granted Healing round 4 (FINAL display gap): make
THealingAbility.GetEnabled(owner=ITEM) resolve the item's CARRIER hero and
gate on the carrier's daily-used record.

DIAGNOSIS (live gname logger, 2026-08-21): the overland unit window builds
ability names via TAbstractUnit.ListAbilityInfo @0x5577FA50, which passes
the OWNER-FINDER's choice ([unit vmt+0x154] best-owner) straight to
ability.GetName - for item-granted Healing that owner is the TItem itself
(bypassing THero.GetAbilityName and its round-1 cave_gan hook). GetName ->
GetEnabled(item): the item's own record is eternally fresh (+0xC=1), so the
name never showed "(used)" even though the carrier's record was correctly
used=0 (the round-3 merge fix works).

NEW PRIMITIVE (found in the live dump): TItem HAS a carrier backref:
    [item+4]      -> owning container (THeroItems @0x70 / THeroInventory @0x74)
    [container+4] -> the carrying THero/TLeader
(confirmed on live server AND client copies).

FIX: cave_ghe2 replaces cave_ghe (repoint THealingAbility VMT+0x74
@file 0x20C30): if owner is a TItem whose [item+4] is a THeroItems /
THeroInventory whose [container+4] is a THero/TLeader, the EFFECTIVE owner
becomes the carrier - then the round-1 logic runs unchanged (own bit OR
merged bit for heroes, then the effective owner's record's used flag; no
record -> enabled). Uncarried items (ground/merchant: backref nil or other
class) keep exact vanilla semantics. All class compares are load-delta
normalized (the DLL rebases); every call is rel32/virtual.

This also fixes the item legs of the merged enabled query for healing at the
source (GetAbEnabled(item) -> GetEnabled(item) -> carrier-aware), making the
round-1 tail-check in cave_mge redundant but harmless.

Old cave_ghe @0x55812700 becomes unreferenced (left in place).
Cave @0x55812B80..0x55812C80 (zeros; file caves end 0x55812B49).
Dry-run default; --apply / --revert.  Backup: AoWEPACK.dll.bak_healcarrier
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_healcarrier"
V2F = 0x55700C00

FINDDATA = 0x5574F1C4
THERO_VMT    = 0x55711FEC
TLEADER_VMT  = 0x55712238
TITEM_VMT    = 0x5570FAFC
THEROITEMS_VMT = 0x55711738
THEROINV_VMT   = 0x5571162C

SLOT_FOFF = 0x20C30          # THealingAbility VMT+0x74
SLOT_OLD  = 0x55812700       # cave_ghe (round 1)
CAVE_GHE2 = 0x55812B80
CAVE_END  = 0x55812C80


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.j8 = []
    def here(self): return self.base + len(self.buf)
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += struct.pack("<I", v & 0xFFFFFFFF)
    def call(self, t):
        self.db(0xE8); self.buf += struct.pack("<i", t - (self.here() + 4))
    def lab(self, n): self.labels[n] = len(self.buf)
    def jcc8(self, op, n): self.db(op); self.j8.append((len(self.buf), n)); self.db(0)
    def fin(self, limit):
        for off, n in self.j8:
            d = self.labels[n] - (off + 1)
            assert -128 <= d <= 127, (n, d)
            self.buf[off] = d & 0xFF
        assert self.base + len(self.buf) <= limit, (hex(self.base), len(self.buf))
        return bytes(self.buf)


def build_ghe2():
    """GetEnabled(eax=self, edx=owner) -> al. Item owners resolve to their
    carrier hero via [item+4]->[container+4]; then own-or-merged bit gate and
    the effective owner's record used-flag (no record -> 1)."""
    a = Asm(CAVE_GHE2)
    a.db(0x53, 0x56, 0x57)              # push ebx/esi/edi
    a.db(0x8B, 0xD8)                    # mov ebx,eax (self)
    a.db(0x8B, 0xF2)                    # mov esi,edx (owner)
    a.db(0xE8, 0, 0, 0, 0)              # call $+5 (PIC anchor)
    popva = a.here()
    a.db(0x5F)                          # pop edi
    a.db(0x81, 0xEF); a.dd(popva)       # sub edi,popva -> edi = load delta
    # ---- item? resolve carrier
    a.db(0x8B, 0x06)                    # mov eax,[esi] (owner VMT)
    a.db(0x2B, 0xC7)                    # sub eax,edi
    a.db(0x3D); a.dd(TITEM_VMT)
    a.jcc8(0x75, 'notitem')
    a.db(0x8B, 0x46, 0x04)              # mov eax,[esi+4] (container)
    a.db(0x3D); a.dd(0x10000)           # plausible ptr?
    a.jcc8(0x72, 'notitem')
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0x2B, 0xCF)                    # sub ecx,edi
    a.db(0x81, 0xF9); a.dd(THEROITEMS_VMT)
    a.jcc8(0x74, 'cont')
    a.db(0x81, 0xF9); a.dd(THEROINV_VMT)
    a.jcc8(0x75, 'notitem')
    a.lab('cont')
    a.db(0x8B, 0x40, 0x04)              # mov eax,[eax+4] (hero)
    a.db(0x3D); a.dd(0x10000)
    a.jcc8(0x72, 'notitem')
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0x2B, 0xCF)                    # sub ecx,edi
    a.db(0x81, 0xF9); a.dd(THERO_VMT)
    a.jcc8(0x74, 'carrier')
    a.db(0x81, 0xF9); a.dd(TLEADER_VMT)
    a.jcc8(0x75, 'notitem')
    a.lab('carrier')
    a.db(0x8B, 0xF0)                    # mov esi,eax (effective owner = carrier)
    a.lab('notitem')
    # ---- own bit on effective owner
    a.db(0x8B, 0x53, 0x0C)              # mov edx,[ebx+0xC] (id)
    a.db(0x8B, 0xC6)                    # mov eax,esi
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x51, 0x4C)              # call [ecx+0x4C]  HasAbility
    a.db(0x84, 0xC0)
    a.jcc8(0x75, 'has')
    # ---- merged bit for heroes/leaders
    a.db(0x8B, 0x06)                    # mov eax,[esi]
    a.db(0x2B, 0xC7)                    # sub eax,edi
    a.db(0x3D); a.dd(THERO_VMT)
    a.jcc8(0x74, 'm')
    a.db(0x3D); a.dd(TLEADER_VMT)
    a.jcc8(0x75, 'zero')
    a.lab('m')
    a.db(0x8B, 0x53, 0x0C)              # mov edx,[ebx+0xC]
    a.db(0x8B, 0xC6)                    # mov eax,esi
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x91); a.dd(0x14C)       # call [ecx+0x14C]  merged HasAbility
    a.db(0x84, 0xC0)
    a.jcc8(0x74, 'zero')
    a.lab('has')
    a.db(0x8B, 0x53, 0x0C)              # mov edx,[ebx+0xC]
    a.db(0x8B, 0xC6)                    # mov eax,esi
    a.call(FINDDATA)                    # effective owner's record
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'one')
    a.db(0x8A, 0x40, 0x0C)              # mov al,[eax+0xC] (used flag)
    a.jcc8(0xEB, 'out')
    a.lab('one')
    a.db(0xB0, 0x01)                    # mov al,1
    a.jcc8(0xEB, 'out')
    a.lab('zero')
    a.db(0x33, 0xC0)
    a.lab('out')
    a.db(0x5F, 0x5E, 0x5B, 0xC3)        # pop edi/esi/ebx; ret
    return a.fin(CAVE_END)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1

    d = bytearray(open(DLL, "rb").read())
    cave = build_ghe2()

    c_off = CAVE_GHE2 - V2F
    cur_c = bytes(d[c_off:c_off + len(cave)])
    cur_s = struct.unpack_from("<I", d, SLOT_FOFF)[0]

    if cur_c == cave and cur_s == CAVE_GHE2:
        print("ALL ALREADY PATCHED"); return 0
    ok = True
    if cur_c != bytes(len(cave)) and cur_c != cave:
        print("MISMATCH: cave region not zero"); ok = False
    if cur_s not in (SLOT_OLD, CAVE_GHE2):
        print("MISMATCH: VMT+0x74 slot holds %#x" % cur_s); ok = False
    if not ok:
        print("Aborting."); return 1

    print("cave_ghe2 @%#x %dB; VMT+0x74 %#x -> ghe2" % (CAVE_GHE2, len(cave), cur_s))
    print("GetEnabled(item) now gates on the CARRIER hero's daily-used record")
    print("([item+4] container -> [container+4] hero backref).")
    if not apply:
        print("\nDry run OK. Re-run with --apply (or --revert)."); return 0

    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    d[c_off:c_off + len(cave)] = cave
    struct.pack_into("<I", d, SLOT_FOFF, CAVE_GHE2)
    open(DLL, "wb").write(d)
    print("AoWEPACK.dll patched successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
