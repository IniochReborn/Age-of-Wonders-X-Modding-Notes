#!/usr/bin/env python3
r"""DIAGNOSTIC #3 (v2, standalone): name the caller that passes a garbage owner
to AoWE.TAbilityOwner.GetAbilityData.

CONTEXT (2026-08-12)
    With the multilevel-heal patch fully disabled (GetAbilityData = stock),
    Keeper2 still dies in the STOCK function:

        Exception EAccessViolation in module AoWEPACK.dll at 0004F1C8.
        Read of address 9EEB2058

    0x5574F1C8 = `mov ebx,[eax+0x10]` -> owner eax = 0x9EEB2058-0x10 =
    0x9EEB2048. Crash #2 earlier saw owner 0x9EED7388: the same 0x9EExxxxx wild
    pattern, and it appeared BOTH with and without the heal patch - so some
    caller genuinely passes a garbage owner, and vanilla faults on it too.
    This turn-event exception is swallowed, so the game limps on.

WHAT THIS DOES (self-contained; the heal cave stays orphaned)
    Hooks GetAbilityData's first 7 bytes -> cave. The cave range-checks Self:
    OK  -> replays the displaced 7 bytes and jumps back to 0x5574F1CB (stock
           walk continues; zero behaviour change),
    bad -> deliberately faults reading (staticVA(return addr) | 0x80000000),
           so the v2 Network.dpl dialog prints
               ... at 8XXXXXXX / Read of address 8XXXXXXX
           and XXXXXXX & 0x7FFFFFFF = the static VA right after the offending
           `call GetAbilityData`.

    Cave @0x55810EA0 (reuses the orphaned probe slot; PIC via call/pop delta).
    Backup: AoWEPACK.dll.bak_abdataprobe2. Dry-run default; --apply / --revert
    (--revert restores the stock 7 bytes and zeroes the cave).

THIS IS A DIAGNOSTIC BUILD - revert it before shipping.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_abdataprobe2"

VA2FILE = 0x55700C00
HOOK = 0x5574F1C4
RESUME = 0x5574F1CB                    # after the displaced 7 bytes
CAVE_BASE, CAVE_LIMIT = 0x55811000, 0x55811100
MIN_PTR, MAX_PTR = 0x10000, 0x7F000000
STOCK = bytes.fromhex("53568bf28b5810")   # push ebx;push esi;mov esi,edx;mov ebx,[eax+0x10]


def build_cave():
    base = CAVE_BASE
    buf = bytearray(); rel = []; labels = {}; jcc8 = []

    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def jmp(t): db(0xE9); rel.append((len(buf), t)); dd(0)
    def lab(n): labels[n] = len(buf)
    def j8(op, n): db(op); jcc8.append((len(buf), n)); db(0)

    # (a) Self must be a plausible pointer
    db(0x3D); dd(MIN_PTR)           # cmp eax, 0x10000
    j8(0x72, 'bogus')
    db(0x3D); dd(MAX_PTR)           # cmp eax, 0x7F000000
    j8(0x73, 'bogus')
    # (b) VALIDATE THE WHOLE CHAIN before the stock walk touches it.
    #     Observed: owner in range, but a node's vtable was 0x1400 -> the AV
    #     landed on `call [edx+0x4c]` @0x5574F1D8 instead of in the probe.
    #     Walk up to 32 nodes; each must be a plausible pointer AND carry a
    #     plausible vtable. ECX/EDX are scratch here (the stock body reloads
    #     edx from the incoming id via esi, which we set below).
    db(0x51)                        # push ecx
    db(0x52)                        # push edx
    db(0x8B, 0x48, 0x10)            # mov ecx,[eax+0x10]      (chain head)
    db(0xBA); dd(32)                # mov edx,32              (iteration cap)
    lab('walk')
    db(0x85, 0xC9)                  # test ecx,ecx
    j8(0x74, 'okpop')               # nil terminator -> fine
    db(0x81, 0xF9); dd(MIN_PTR)     # cmp ecx,0x10000
    j8(0x72, 'bogpop')
    db(0x81, 0xF9); dd(MAX_PTR)     # cmp ecx,0x7F000000
    j8(0x73, 'bogpop')
    db(0x50)                        # push eax
    db(0x8B, 0x01)                  # mov eax,[ecx]           (node vtable)
    db(0x3D); dd(MIN_PTR)           # cmp eax,0x10000
    j8(0x72, 'bogpop2')
    db(0x3D); dd(MAX_PTR)           # cmp eax,0x7F000000
    j8(0x73, 'bogpop2')
    db(0x58)                        # pop eax
    db(0x8B, 0x49, 0x08)            # mov ecx,[ecx+8]         (next)
    db(0x4A)                        # dec edx
    j8(0x75, 'walk')
    lab('okpop')
    db(0x5A)                        # pop edx
    db(0x59)                        # pop ecx
    # normal path: displaced stock bytes, then back into the function
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
    j8(0xEB, 'bogus')
    lab('bogus')
    db(0x8B, 0x0C, 0x24)            # mov ecx,[esp]   (caller's return address)
    db(0xE8); dd(0)                 # call $+5
    popva = base + len(buf)
    db(0x5A)                        # pop edx
    db(0x81, 0xEA); dd(popva)       # sub edx, static -> delta
    db(0x29, 0xD1)                  # sub ecx, edx    -> static VA
    db(0x81, 0xC9); dd(0x80000000)  # or ecx, 0x80000000
    db(0x8B, 0x09)                  # mov ecx,[ecx]   -> AV names it
    db(0xC3)                        # ret (unreached)

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
        d[c_off:c_off+0x60] = bytes(0x60)
        open(DLL, 'wb').write(d)
        print("stock GetAbilityData restored; probe cave zeroed")
        return 0

    cur = bytes(d[h_off:h_off+7])
    assert cur == STOCK or cur[0] == 0xE9, "unexpected bytes at hook: " + cur.hex()

    d[c_off:c_off+0x60] = bytes(0x60)              # wipe the orphaned old probe
    d[c_off:c_off+len(cave)] = cave
    d[h_off:h_off+7] = (bytes([0xE9]) +
                        (CAVE_BASE - (HOOK + 5)).to_bytes(4, 'little', signed=True) +
                        b'\x90\x90')
    print("cave %d B @0x%X; GetAbilityData -> probe -> stock body @0x%X"
          % (len(cave), CAVE_BASE, RESUME))
    print("bogus owner => dialog reads '... at 8XXXXXXX'; caller VA = value & 0x7FFFFFFF")
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
