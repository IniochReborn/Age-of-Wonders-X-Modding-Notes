#!/usr/bin/env python3
r"""SHIPPABLE FIX: make AoWE.TAbilityOwner.GetAbilityData fail safe instead of
crashing when it is handed an object that is not a real TAbilityOwner.

THE PROBLEM (2026-08-12, Keeper2 campaign + any siege)
    Something in the combat path calls GetAbilityData with a wrong-class
    object. Because the stock function trusts its argument, this surfaced as
    four different access violations depending on what junk happened to be in
    memory - all inside TArmyCombatMoveTE, all swallowed by the turn-event
    handler (so the game limped on with the move/combat lost):

        @0x5574F1C8  mov ebx,[eax+0x10]   owner = 0x9EEB2048 (wild)
        @0x55810C93  (heal cave)          owner = 0x9EED7388 (wild)
        @0x55810C9B  (heal cave)          chain node = 0xFFFFFFFF
        @0x5574F1D8  call [edx+0x4c]      node vtable = 0x1400

    The caller was never identified: after the wall fixes it became rare enough
    that a chain-validating probe could not be made to fire in ~10 attempts.
    Rather than leave a rare crash in players' hands, make the funnel itself
    tolerant - nil is exactly what the stock function already returns for
    "ability not found", so every caller already handles it.

WHAT THIS DOES
    Hooks GetAbilityData's first 7 bytes -> cave. The cave validates:
      * Self is a plausible pointer, and
      * every node in the [Self+0x10] chain (cap 32) is a plausible pointer
        carrying a plausible vtable
    Valid  -> replays the displaced 7 bytes and jumps back to the stock body at
              0x5574F1CB. Healthy data takes the identical original path, so
              there is NO behaviour change.
    Bogus  -> `xor eax,eax; ret` (nothing is pushed yet at that point, so this
              is a clean return of nil).

    ⚠ HONEST LIMITS: this masks the underlying wrong-class call rather than
    fixing it, and a pointer that is in-range but points at UNMAPPED memory can
    still fault when its vtable is read. It closes the four observed failures,
    not every conceivable one. If the real caller is ever identified, fix that
    and this guard can stay as belt-and-braces.

    Cave @0x55811000 (reuses the probe slot). PIC not required: only rel32
    jumps and register work. Backup: AoWEPACK.dll.bak_abdataguard.
    Dry-run default; --apply / --revert (restores the stock 7 bytes).
"""
import os, shutil, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_abdataguard"

VA2FILE = 0x55700C00
HOOK = 0x5574F1C4
RESUME = 0x5574F1CB
CAVE_BASE, CAVE_LIMIT = 0x55811000, 0x55811100
MIN_PTR, MAX_PTR = 0x10000, 0x7F000000
MAX_NODES = 32
STOCK = bytes.fromhex("53568bf28b5810")


def build_cave():
    base = CAVE_BASE
    buf = bytearray(); rel = []; labels = {}; jcc8 = []

    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def jmp(t): db(0xE9); rel.append((len(buf), t)); dd(0)
    def lab(n): labels[n] = len(buf)
    def j8(op, n): db(op); jcc8.append((len(buf), n)); db(0)

    # (a) Self plausible?
    db(0x3D); dd(MIN_PTR)
    j8(0x72, 'null')
    db(0x3D); dd(MAX_PTR)
    j8(0x73, 'null')
    # (b) whole chain plausible?
    db(0x51)                        # push ecx
    db(0x52)                        # push edx
    db(0x8B, 0x48, 0x10)            # mov ecx,[eax+0x10]
    db(0xBA); dd(MAX_NODES)         # mov edx,32
    lab('walk')
    db(0x85, 0xC9)                  # test ecx,ecx
    j8(0x74, 'okpop')               # nil terminator = healthy
    db(0x81, 0xF9); dd(MIN_PTR)
    j8(0x72, 'bogpop')
    db(0x81, 0xF9); dd(MAX_PTR)
    j8(0x73, 'bogpop')
    db(0x50)                        # push eax
    db(0x8B, 0x01)                  # mov eax,[ecx]     (node vtable)
    db(0x3D); dd(MIN_PTR)
    j8(0x72, 'bogpop2')
    db(0x3D); dd(MAX_PTR)
    j8(0x73, 'bogpop2')
    db(0x58)                        # pop eax
    db(0x8B, 0x49, 0x08)            # mov ecx,[ecx+8]   (next)
    db(0x4A)                        # dec edx
    j8(0x75, 'walk')
    lab('okpop')
    db(0x5A)                        # pop edx           (restores the ability id)
    db(0x59)                        # pop ecx
    # healthy: displaced stock bytes, then back into the stock body
    db(0x53)                        # push ebx
    db(0x56)                        # push esi
    db(0x8B, 0xF2)                  # mov esi,edx
    db(0x8B, 0x58, 0x10)            # mov ebx,[eax+0x10]
    jmp(RESUME)
    lab('bogpop2')
    db(0x58)                        # pop eax
    lab('bogpop')
    db(0x5A)                        # pop edx
    db(0x59)                        # pop ecx
    lab('null')
    db(0x33, 0xC0)                  # xor eax,eax       (stock "not found")
    db(0xC3)                        # ret

    for off, tgt in rel:
        buf[off:off+4] = (tgt - (base + off + 4)).to_bytes(4, 'little', signed=True)
    for off, n in jcc8:
        dtl = labels[n] - (off + 1)
        assert -128 <= dtl <= 127, (n, dtl)
        buf[off] = dtl & 0xFF
    assert base + len(buf) <= CAVE_LIMIT, hex(len(buf))
    return bytes(buf)


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, 'rb').read())
    h_off = HOOK - VA2FILE
    c_off = CAVE_BASE - VA2FILE
    cave = build_cave()

    if revert:
        d[h_off:h_off+7] = STOCK
        d[c_off:c_off+0x100] = bytes(0x100)
        open(DLL, 'wb').write(d)
        print("stock GetAbilityData restored; guard cave zeroed")
        return 0

    cur = bytes(d[h_off:h_off+7])
    assert cur == STOCK or cur[0] == 0xE9, "unexpected bytes at hook: " + cur.hex()

    d[c_off:c_off+0x100] = bytes(0x100)          # wipe the probe that lived here
    d[c_off:c_off+len(cave)] = cave
    d[h_off:h_off+7] = (bytes([0xE9]) +
                        (CAVE_BASE - (HOOK + 5)).to_bytes(4, 'little', signed=True) +
                        b'\x90\x90')
    print("guard cave %d B @0x%X; GetAbilityData -> guard -> stock body @0x%X"
          % (len(cave), CAVE_BASE, RESUME))
    print("bogus owner/chain now returns nil instead of crashing; healthy data unchanged")
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert).")
        return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
        print("Backup ->", os.path.basename(BAK))
    open(DLL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
