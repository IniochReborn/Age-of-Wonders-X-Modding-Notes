"""Fix: 'Exception occurred during TArmyCombatMoveTE' + soft-lock when combat starts
with a hero carrying an ability-granting item (e.g. Leadership) in the BACKPACK.

Root cause (diagnosed live 2026-09-09, save from player report):
  The item-ability-levels fix (build_item_ability_levels.py v3, shipped 1.37.406)
  added cave_findrec @0x558124A0: when an ability GetLevel finds no own record on a
  hero, it searches THeroItems (+0x70, equipped) and THeroInventory (+0x74, backpack)
  for an item record. But VANILLA inventory legs (e.g. THeroInventory.
  GetSuperlativeAbOwner 0x557861F4 @+0x4B: cmp byte [item+0x34],6) only count
  backpack items with type byte 6; cave_findrec searched the backpack UNFILTERED.
  Result: hero with an unequipped Leadership item -> GetAbilityLevel (self-fallback
  path in THero.GetAbilityLevel 0x5578831C) returns 3, while GetAbilityOwner
  (vanilla finder 0x557881DC, bit+filter based, NO fallback) returns nil.
  TArmy.UpdateFormation 0x5578D034 then derefs the nil owner unchecked at
  0x5578D0E7 (mov ecx,[eax] / call [ecx+0x60]) -> AV -> Delphi aborts the
  TArmyCombatMoveTE token event -> TTokenExecuter wedges (events queue but never
  execute) -> units already pulled for combat vanish, game soft-locked.

Two patches (both inside the long-reserved item-ability cave region; the
407-409 laptop caves occupy 0x55812000-0x5581206E and 0x55813200-0x558155EE,
we stay clear):
  A) cave_findrec item-type filter: the 13-byte TItem-VMT check at 0x55812543 is
     re-routed through subcave @0x558125A8 which repeats the check and ADDITIONALLY
     skips backpack items (container offset ebp==0x74) whose byte [item+0x34]<>6 --
     exactly the vanilla inventory filter.
  B) hardening: TArmy.UpdateFormation's virtual GetAbilityOwner call at 0x5578D0DE
     goes through guard cave @0x558125E0: nil result -> skip this unit (jmp
     0x5578D11E next-unit) instead of dereferencing. Any future level/owner
     mismatch degrades to 'no formation bonus' instead of a wedged game.

House pattern: dry-run by default, --apply, --revert; backup AoWEPACK.dll.bak_bagability.
Default target: the 'Age of Wonders X - 409' folder's AoWEPACK.dll (pass --dll for
another copy, e.g. the main folder's). Not applicable to AoWEPACK.dev (different build).
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

BASE = 0x55700000
DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK_SUFFIX = ".bak_bagability"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)

# CODE section: RVA 0x1000 at raw 0x400  ->  file offset = VA - BASE - 0xC00
def va2fo(va):
    return va - BASE - 0xC00

# ---- patch A: cave_findrec inventory filter ----
HOOK_A_VA = 0x55812543
HOOK_A_OLD = bytes.fromhex("8B 03 2B 44 24 08 3D FC FA 70 55 75 D5".replace(" ", ""))
SUBCAVE_VA = 0x558125A8       # zeros (v2 cave region slack, ends < 0x558125FF)
CONT_OK_VA = 0x55812550       # continue: read item's record chain
CONT_SKIP_VA = 0x55812525     # skip: next item

def build_subcave():
    A = SUBCAVE_VA
    b = b""
    b += bytes.fromhex("8B03")            # mov eax,[ebx]
    b += bytes.fromhex("2B442408")        # sub eax,[esp+8]   (load delta)
    b += bytes.fromhex("3D") + struct.pack("<I", 0x5570FAFC)   # cmp eax,TItem VMT
    b += bytes.fromhex("7510")            # jne skip (next=A+0x0D, +0x10 -> A+0x1D)
    b += bytes.fromhex("83FD74")          # cmp ebp,0x74      (inventory container?)
    b += bytes.fromhex("7506")            # jne ok
    b += bytes.fromhex("807B3406")        # cmp byte [ebx+0x34],6
    b += bytes.fromhex("7505")            # jne skip
    # ok: (A+0x18)
    nxt = A + 0x18 + 5
    b += b"\xE9" + struct.pack("<i", CONT_OK_VA - nxt)
    # skip: (A+0x1D)
    nxt = A + 0x1D + 5
    b += b"\xE9" + struct.pack("<i", CONT_SKIP_VA - nxt)
    assert len(b) == 0x22
    return b

def build_hook_a():
    rel = SUBCAVE_VA - (HOOK_A_VA + 5)
    return b"\xE9" + struct.pack("<i", rel) + b"\x90" * 8

# ---- patch B: UpdateFormation nil-owner guard ----
SITE_B_VA = 0x5578D0DE
SITE_B_OLD = bytes.fromhex("FF 91 54 01 00 00".replace(" ", ""))   # call [ecx+0x154]
GUARD_VA = 0x558125E0         # zeros, ends 0x558125F3 < 0x558125FF junk
NEXT_UNIT_VA = 0x5578D11E     # UpdateFormation: dec esi / loop next unit

def build_guard():
    G = GUARD_VA
    b = b""
    b += bytes.fromhex("FF9154010000")    # call dword [ecx+0x154]  GetAbilityOwner
    b += bytes.fromhex("85C0")            # test eax,eax
    b += bytes.fromhex("7508")            # jne done (ret)
    b += bytes.fromhex("83C404")          # add esp,4  (drop return addr)
    nxt = G + 0x0D + 5
    b += b"\xE9" + struct.pack("<i", NEXT_UNIT_VA - nxt)
    b += b"\xC3"                          # done: ret
    assert len(b) == 0x13
    return b

def build_site_b():
    rel = GUARD_VA - (SITE_B_VA + 5)
    return b"\xE8" + struct.pack("<i", rel) + b"\x90"

PATCHES = [
    ("A-hook  cave_findrec item check -> subcave", HOOK_A_VA, HOOK_A_OLD, build_hook_a()),
    ("A-subcave inventory type-6 filter", SUBCAVE_VA, b"\x00" * 0x22, build_subcave()),
    ("B-site  UpdateFormation GetAbilityOwner -> guard", SITE_B_VA, SITE_B_OLD, build_site_b()),
    ("B-guard nil-owner skip cave", GUARD_VA, b"\x00" * 0x13, build_guard()),
]


def reloc_check(data, spans):
    """Ensure no base-reloc entry lands inside any patched span."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    rrva, rsz = struct.unpack_from("<II", data, pe + 0x78 + 5 * 8)  # dir[5] = basereloc
    # find .reloc raw
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 0x14)[0]
    sec0 = pe + 0x18 + opt
    raw = None
    for i in range(nsec):
        off = sec0 + i * 0x28
        vsz, va, rs, rw = struct.unpack_from("<IIII", data, off + 8)
        if va <= rrva < va + max(vsz, rs):
            raw = rw + (rrva - va)
    assert raw is not None
    bad = []
    p = raw
    end = raw + rsz
    while p < end:
        page, bsz = struct.unpack_from("<II", data, p)
        for q in range(p + 8, p + bsz, 2):
            e = struct.unpack_from("<H", data, q)[0]
            if e >> 12 == 3:
                va = BASE + page + (e & 0xFFF)
                for lo, hi in spans:
                    if lo <= va < hi or lo <= va + 3 < hi:
                        bad.append(va)
        p += bsz
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dll", default=DEFAULT_DLL)
    args = ap.parse_args()
    dll = args.dll
    bak = bak_path(dll, BAK_SUFFIX)

    data = bytearray(open(dll, "rb").read())
    print("target:", dll, "size", len(data))

    if args.revert:
        if not os.path.exists(bak):
            print("no backup found:", bak); sys.exit(1)
        b = open(bak, "rb").read()
        open(dll, "wb").write(b)
        print("reverted from", bak)
        return

    spans = [(va, va + len(new)) for _, va, _, new in PATCHES]
    bad = reloc_check(bytes(data), spans)
    if bad:
        print("FATAL: reloc entries inside patch spans:", [hex(x) for x in bad])
        sys.exit(1)
    print("reloc check clean")

    already = all(bytes(data[va2fo(va):va2fo(va) + len(new)]) == new
                  for _, va, _, new in PATCHES)
    if already:
        print("patch already applied")
        return

    ok = True
    for name, va, oldb, newb in PATCHES:
        fo = va2fo(va)
        cur = bytes(data[fo:fo + len(oldb)])
        m = "OK " if cur == oldb else "MISMATCH"
        if cur != oldb:
            ok = False
        print("%-8s %s VA %08X fo %06X" % (m, name, va, fo))
        if cur != oldb:
            print("   expected", oldb.hex())
            print("   found   ", cur.hex())
    if not ok:
        print("originals do not match -- aborting")
        sys.exit(1)

    if not args.apply:
        print("dry-run OK. run with --apply to patch.")
        return

    if not os.path.exists(bak):
        shutil.copy2(dll, bak)
        print("backup ->", bak)
    for name, va, oldb, newb in PATCHES:
        fo = va2fo(va)
        data[fo:fo + len(newb)] = newb
    open(dll, "wb").write(data)
    print("APPLIED. verify:")
    chk = open(dll, "rb").read()
    for name, va, oldb, newb in PATCHES:
        fo = va2fo(va)
        print("  %s %s" % ("OK" if chk[fo:fo + len(newb)] == newb else "FAIL", name))


if __name__ == "__main__":
    main()
