#!/usr/bin/env python3
r"""
AoW1 LAN out-of-sync fix  --  portable, pattern-based patcher for AoWEPACK.dll
=============================================================================

WHAT THIS FIXES
    Multiplayer / LAN "Out of Sync" that fires when a player moves onto and
    recruits a neutral/independent stack (the classic repro: the underground
    dwarf moles on "Towers of Khazlkound").

THE BUG (one sentence)
    TMoveTE.Execute draws a synced Random(0xFFFFF) once per move token's first
    execution and immediately DISCARDS the result (eax is overwritten by the
    next instruction, `mov eax,[ebx+14h]`).  That throwaway draw still advances
    the shared synced RNG seed.  When a human move executes at a slightly
    different stream position than the peer (which happens when it is injected
    into a burst of concurrently-generated AI move tokens, e.g. recruiting an
    independent that wakes a nearby AI), the draw lands on one machine and not
    the other at the sync-check point -> the seeds differ -> OUT OF SYNC.

THE FIX
    NOP the 5-byte `call Random` so a move token consumes ZERO synced draws.
    The value was discarded anyway, so gameplay is unchanged; the synced RNG
    stream simply advances one-fewer-per-move UNIFORMLY on every client (they
    all run the same patched DLL), so determinism is preserved and the move's
    execution timing can no longer perturb the seed.

WHY PATTERN-BASED (not a fixed offset)
    Every mod build lays AoWEPACK.dll out differently.  This script does NOT
    trust an address; it searches for the exact instruction signature:

        BA FF FF 0F 00    mov edx, 0x000FFFFF      ; Random range arg
        A1 ?? ?? ?? ??    mov eax, [AoWHSMap]       ; 'self' (wildcarded)
        E8 ?? ?? ?? ??    call TAoWHSMap.Random     ; <-- the draw (wildcarded)
        8B 43 14          mov eax, [ebx+14h]        ; RESULT DISCARDED HERE

    The trailing `8B 43 14` is the proof the result is thrown away -- that is
    what makes NOPing the call safe.  The script REQUIRES exactly one match; if
    it finds zero or several, it refuses to touch anything.  If your build has
    its own hook sitting on these bytes it simply won't match (safe no-op).

USAGE
    py -3 patch_lan_desync_fix.py                 # dry-run on ./AoWEPACK.dll
    py -3 patch_lan_desync_fix.py --apply         # patch it (makes a backup)
    py -3 patch_lan_desync_fix.py --revert        # restore the original bytes
    py -3 patch_lan_desync_fix.py PATH\AoWEPACK.dll --apply

    A one-time backup "<file>.bak_lan_desync" is written on first --apply and
    is what --revert restores from.

    Ships as plain stdlib Python 3 -- no dependencies.  Idempotent.  Every
    client in a game must run the SAME patched DLL (as with any sync fix).
"""
import os
import struct
import sys

# ---- signature ---------------------------------------------------------------
# (byte, is_wildcard) pairs.
PATTERN = [
    (0xBA, False), (0xFF, False), (0xFF, False), (0x0F, False), (0x00, False),  # mov edx,0xFFFFF
    (0xA1, False), (0x00, True),  (0x00, True),  (0x00, True),  (0x00, True),   # mov eax,[abs]
    (0xE8, False), (0x00, True),  (0x00, True),  (0x00, True),  (0x00, True),   # call rel32
    (0x8B, False), (0x43, False), (0x14, False),                                # mov eax,[ebx+14h]
]
CALL_OFF = 10          # offset of the E8 within the pattern
CALL_LEN = 5           # E8 + rel32
NOP5 = b"\x90" * 5
# Patched form of the same window (call replaced by 5 NOPs) -- for idempotence.


def find_matches(data, pattern):
    hits = []
    n = len(pattern)
    first = pattern[0][0]
    i = data.find(first)
    while i != -1 and i + n <= len(data):
        ok = True
        for k, (b, wild) in enumerate(pattern):
            if not wild and data[i + k] != b:
                ok = False
                break
        if ok:
            hits.append(i)
        i = data.find(first, i + 1)
    return hits


def is_already_patched(data, off):
    """True if the window at off matches the pattern but with the call NOPed."""
    for k, (b, wild) in enumerate(PATTERN):
        if CALL_OFF <= k < CALL_OFF + CALL_LEN:
            if data[off + k] != 0x90:
                return False
        elif not wild and data[off + k] != b:
            return False
    return True


def find_patched(data):
    """Locate an already-applied patch: same fixed bytes, call region = NOPs."""
    hits = []
    i = data.find(0xBA)
    n = len(PATTERN)
    while i != -1 and i + n <= len(data):
        if is_already_patched(data, i):
            hits.append(i)
        i = data.find(0xBA, i + 1)
    return hits


def file_off_to_va(data, off):
    """Best-effort VA for reporting (uses PE section table + image base)."""
    try:
        e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
        nsec = struct.unpack_from('<H', data, e_lfanew + 6)[0]
        opt_size = struct.unpack_from('<H', data, e_lfanew + 20)[0]
        image_base = struct.unpack_from('<I', data, e_lfanew + 24 + 28)[0]
        p = e_lfanew + 24 + opt_size
        for _ in range(nsec):
            vsz, va, rsz, raw = struct.unpack_from('<IIII', data, p + 8)
            if raw <= off < raw + rsz:
                return image_base + va + (off - raw)
            p += 40
    except Exception:
        pass
    return None


def reloc_hits(data, lo, hi):
    """Any base-reloc fixups intersecting [lo, hi)?  (Should be none for a call.)"""
    try:
        e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
        opt = e_lfanew + 24
        nsec = struct.unpack_from('<H', data, e_lfanew + 6)[0]
        opt_size = struct.unpack_from('<H', data, e_lfanew + 20)[0]
        reloc_rva, reloc_sz = struct.unpack_from('<II', data, opt + 96 + 5 * 8)
        secs = []
        p = opt + opt_size
        for _ in range(nsec):
            vsz, va, rsz, raw = struct.unpack_from('<IIII', data, p + 8)
            secs.append((va, vsz, raw, rsz)); p += 40
        def r2o(rva):
            for va, vsz, raw, rsz in secs:
                if va <= rva < va + max(vsz, rsz):
                    return raw + rva - va
        off = r2o(reloc_rva)
        if off is None:
            return []
        end = off + reloc_sz
        out = []
        while off < end:
            page, blk = struct.unpack_from('<II', data, off)
            for i in range((blk - 8) // 2):
                w = struct.unpack_from('<H', data, off + 8 + i * 2)[0]
                if (w >> 12) == 0:
                    continue
                fo = r2o(page + (w & 0xFFF))
                if fo is not None and lo <= fo + 3 and fo < hi:
                    out.append(fo)
            off += blk
        return out
    except Exception:
        return []


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    target = args[0] if args else os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "AoWEPACK.dll")
    if not os.path.isfile(target):
        print("ERROR: AoWEPACK.dll not found: %s" % target)
        print("       Pass the path explicitly, e.g.:  py patch_lan_desync_fix.py "
              "\"C:\\path\\AoWEPACK.dll\" --apply")
        return 2
    backup = target + ".bak_lan_desync"
    data = bytearray(open(target, "rb").read())

    matches = find_matches(data, PATTERN)
    patched = find_patched(data)

    print("Target : %s" % target)
    print("Found  : %d unpatched site(s), %d already-patched site(s)"
          % (len(matches), len(patched)))

    # ---- REVERT ----
    if revert:
        if not patched:
            print("Nothing to revert (no applied patch found).")
            return 0
        if len(patched) != 1:
            print("ABORT: %d patched sites -- refusing to guess." % len(patched))
            return 1
        if not os.path.isfile(backup):
            print("ABORT: no backup file to restore from (%s)." % os.path.basename(backup))
            print("       (The patch is reversible only via the backup made on --apply.)")
            return 1
        import shutil
        shutil.copy2(backup, target)
        print("Reverted: restored original from %s" % os.path.basename(backup))
        return 0

    # ---- already done? ----
    if patched and not matches:
        print("Already patched -- nothing to do.  (Use --revert to undo.)")
        return 0

    # ---- must be exactly one clean site ----
    if len(matches) == 0:
        print("ABORT: signature not found.  This build may differ, already be")
        print("       patched by other means, or have a hook on these bytes.")
        print("       Nothing was changed.")
        return 1
    if len(matches) > 1:
        print("ABORT: signature matched %d times -- too ambiguous to patch safely."
              % len(matches))
        for off in matches:
            va = file_off_to_va(data, off)
            print("         file 0x%X%s" % (off, "  (VA 0x%08X)" % va if va else ""))
        return 1

    off = matches[0]
    call_off = off + CALL_OFF
    va = file_off_to_va(data, off)
    print("Site   : file 0x%X%s" % (off, "  (VA 0x%08X)" % (va + CALL_OFF) if va else ""))
    print("         window: %s" % data[off:off + len(PATTERN)].hex())
    print("         (trailing 8B 43 14 confirms the Random result is discarded)")

    rh = reloc_hits(data, call_off, call_off + CALL_LEN)
    if rh:
        print("ABORT: a base relocation intersects the call bytes (%s) -- unexpected;"
              " not patching." % rh)
        return 1

    if not apply:
        print("\nDRY RUN ok.  Would NOP the 5 call bytes at file 0x%X:" % call_off)
        print("    %s  ->  90 90 90 90 90" % data[call_off:call_off + CALL_LEN].hex())
        print("Re-run with --apply to write the patch (a backup will be made).")
        return 0

    if not os.path.isfile(backup):
        import shutil
        shutil.copy2(target, backup)
        print("Backup : %s" % os.path.basename(backup))
    data[call_off:call_off + CALL_LEN] = NOP5
    open(target, "wb").write(data)
    print("APPLIED: NOPed call at file 0x%X.  LAN recruit desync fixed." % call_off)
    print("         Every player must run this same patched DLL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
