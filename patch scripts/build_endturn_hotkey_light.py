#!/usr/bin/env python3
r"""End-turn hotkey lights up the taskbar turn button (AoWEPACK.dll).

Clicking the turn button runs TTBWindow.TurnButtonChange @0x4574AC in
AoWx.exe: it calls TAoWHSMap.EndTurn (or CancelEndTurn if the player's turn
is already ended - the button is a toggle) and stores the result in the
button's lit-state byte [TurnButton+0x13C]. The Ctrl+Enter / Ctrl+E hotkeys,
however, are handled inside AoWEPACK's TAoWHSMapKeyboard handler, which
calls TAoWHSMap.EndTurn directly - turn ends, button never lights.

    55773F50  test byte [ebp-1],4        ; Ctrl held?
    55773F5A  mov ax,[ebx] ; sub ax,0Dh  ; Ctrl+Enter -> 55773F7C
    55773F63  sub ax,38h                 ; Ctrl+E     -> fall through
    55773F6D  mov eax,[AoWHSMap] ; call TAoWHSMap.EndTurn   <- site A
    55773F7C  mov eax,[AoWHSMap] ; call TAoWHSMap.EndTurn   <- site B

This patch retargets both calls to a cave that replicates the BUTTON'S OWN
click routine (TAOWTurnButton.CheckMouseButton inner path @0x5970509D in
AOWTools.dpl) on the TurnButton instance:

    if [btn+0x120] busy (mid-animation): ignore, like a real click
    toggle the lit byte [btn+0x13C]
    [btn+0xA4] = 0                        <- dirty: THE repaint request the
                                             v1 cave missed (state changed
                                             but was never redrawn)
    fire OnChange (+0x134 code/+0x138 data) -> TurnButtonChange -> EndTurn
                                             (or CancelEndTurn - a toggle,
                                             exactly like a second click)

AoWx.exe is Delphi 3 with no .reloc, so exe addresses are constants.
Guards: TTBWindow controller global [0x45A0CC] and its TurnButton field
must be live, else fall back to the original direct EndTurn call (rel32,
so an EPACK rebase is harmless).

Backup: AoWEPACK.dll.bak_endturnlight. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_endturnlight"

VA2FILE = 0x55700C00           # CODE: file = VA - this
SITE_A  = 0x55773F72           # call EndTurn (Ctrl+E path)
SITE_B  = 0x55773F81           # call EndTurn (Ctrl+Enter path)
F_ENDTURN = 0x5577838C         # TAoWHSMap.EndTurn (eax = map)
CAVE    = 0x55860000           # CODE tail zeros (0x5581223F..0x558E7918)
# AoWx.exe (fixed base 0x400000, no .reloc)
EXE_TB_CELL       = 0x45A0CC   # -> ptr -> TTBWindow controller instance
TB_TURNBUTTON_OFF = 0x5C       # TTBWindow.TurnButton field
# TAOWTurnButton instance offsets (AOWTools.dpl, from CheckMouseButton/Draw)
BTN_BUSY   = 0x120             # nonzero while the press animation runs
BTN_LIT    = 0x13C             # lit-state byte the draw code keys off
BTN_DIRTY  = 0xA4              # 0 = needs repaint
BTN_EVT_CODE, BTN_EVT_HIWD, BTN_EVT_DATA = 0x134, 0x136, 0x138  # OnChange


# diag counters in DATA slack (file-backed, RW page; read with probe_endturn.py)
CNT_ENTER = 0x558E9A80         # cave entered (hotkey reached our sites)
CNT_CLICK = 0x558E9A84         # guards passed (click replayed on the button)


def build_cave():
    """Entered via call from a site; eax = AoWHSMap (loaded just before).
    Replays TAOWTurnButton's own click path on the TurnButton instance.
    PIC for EPACK refs (delta in ebx); exe addresses are constants."""
    a = bytearray()
    jzs = []
    def jz_fb():
        jzs.append(len(a)); a.extend(b'\x74\x00')
    a += b'\x53'                                          # push ebx
    a += b'\xE8\x00\x00\x00\x00'                          # call $+5
    popva = CAVE + len(a)
    a += b'\x5B'                                          # pop ebx
    a += b'\x81\xEB' + struct.pack('<I', popva)           # sub ebx,popva
    a += b'\xFF\x83' + struct.pack('<I', CNT_ENTER)       # inc dword [ebx+CNT]
    a += b'\x50'                                          # push eax (map)
    a += b'\xA1' + struct.pack('<I', EXE_TB_CELL)         # mov eax,[cell]
    a += b'\x85\xC0'                                      # test eax,eax
    jz_fb()
    a += b'\x8B\x00'                                      # mov eax,[eax]
    a += b'\x85\xC0'
    jz_fb()
    a += b'\x8B\x40' + bytes([TB_TURNBUTTON_OFF])         # mov eax,[eax+0x5C]
    a += b'\x85\xC0'
    jz_fb()
    a += b'\xFF\x83' + struct.pack('<I', CNT_CLICK)       # inc dword [ebx+CNT2]
    # ---- the click routine, verbatim semantics ----
    a += b'\x80\xB8' + struct.pack('<I', BTN_BUSY) + b'\x00'   # cmp byte [eax+0x120],0
    jne_busy = len(a); a += b'\x75\x00'                   # jne done (ignore, like a click)
    a += b'\x80\xB8' + struct.pack('<I', BTN_LIT) + b'\x00'    # cmp byte [eax+0x13C],0
    je_set = len(a); a += b'\x74\x00'                     # je set1
    a += b'\xC6\x80' + struct.pack('<I', BTN_LIT) + b'\x00'    # mov byte [eax+0x13C],0
    jmp_aft = len(a); a += b'\xEB\x00'                    # jmp after
    set1 = len(a)
    a += b'\xC6\x80' + struct.pack('<I', BTN_LIT) + b'\x01'    # mov byte [eax+0x13C],1
    after = len(a)
    a += b'\xC6\x80' + struct.pack('<I', BTN_DIRTY) + b'\x00'  # mov byte [eax+0xA4],0
    a += b'\x66\x83\xB8' + struct.pack('<I', BTN_EVT_HIWD) + b'\x00'  # cmp word [eax+0x136],0
    je_done = len(a); a += b'\x74\x00'                    # je done
    a += b'\x8B\xD0'                                      # mov edx,eax (Sender=btn)
    a += b'\x8B\x82' + struct.pack('<I', BTN_EVT_DATA)    # mov eax,[edx+0x138] (Self)
    a += b'\xFF\x92' + struct.pack('<I', BTN_EVT_CODE)    # call [edx+0x134] OnChange
    done = len(a)
    a += b'\x83\xC4\x04'                                  # add esp,4 (drop map)
    a += b'\x5B'                                          # pop ebx
    a += b'\xC3'                                          # ret
    fb = len(a)
    a += b'\x58'                                          # pop eax (map)
    a += b'\x5B'                                          # pop ebx
    rel = F_ENDTURN - (CAVE + len(a) + 5)
    a += b'\xE8' + struct.pack('<i', rel)                 # call EndTurn
    a += b'\xC3'                                          # ret
    for j in jzs:
        a[j+1] = fb - (j + 2)
    a[jne_busy+1] = done - (jne_busy + 2)
    a[je_set+1] = set1 - (je_set + 2)
    a[jmp_aft+1] = after - (jmp_aft + 2)
    a[je_done+1] = done - (je_done + 2)
    return bytes(a)


def reloc_hits(data, ranges):
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]; osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vs, raw, rs)); p += 40
    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs): return raw + rva - va
    off = r2o(rrva)
    if off is None or not rsz: return []
    end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        if blk < 8: break
        for i in range((blk - 8)//2):
            w = struct.unpack_from('<H', data, off + 8 + i*2)[0]
            if w >> 12 == 0: continue
            fo = r2o(page + (w & 0xFFF))
            if fo is None: continue
            for lo, hi in ranges:
                if lo <= fo + 3 and fo < hi: hits.append(fo)
        off += blk
    return hits


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1

    d = bytearray(open(DLL, 'rb').read())
    cave = build_cave()
    co = CAVE - VA2FILE
    seg = bytes(d[co:co+len(cave)])
    assert seg == bytes(len(cave)) or seg[0] in (0x50, 0x53), "cave not free: " + seg[:8].hex()
    # counters live in DATA: file = VA - (0x558E8000 - 0x1E6E00) = VA - 0x55701200
    cnto = CNT_ENTER - 0x55701200
    d[cnto:cnto+8] = bytes(8)                   # zero the counters on every apply

    sites = []
    for site in (SITE_A, SITE_B):
        o = site - VA2FILE
        assert d[o] == 0xE8, "no call at 0x%X: %02x" % (site, d[o])
        tgt = (site + 5 + struct.unpack_from('<i', d, o + 1)[0]) & 0xFFFFFFFF
        assert tgt in (F_ENDTURN, CAVE), "unexpected call target 0x%X @0x%X" % (tgt, site)
        # context check: preceded by mov eax,[AoWHSMap global]
        assert d[o-5] == 0xA1, "expected mov eax,[..] before site 0x%X" % site
        sites.append(o)
    hits = reloc_hits(bytes(d), [(co, co + len(cave)), (cnto, cnto + 8)]
                      + [(o, o + 5) for o in sites])
    assert not hits, [hex(x) for x in hits]

    d[co:co+len(cave)] = cave
    for site, o in zip((SITE_A, SITE_B), sites):
        d[o+1:o+5] = struct.pack('<i', CAVE - (site + 5))
    print("cave %dB @0x%X; sites 0x%X, 0x%X -> TurnButtonChange (with fallback)"
          % (len(cave), CAVE, SITE_A, SITE_B))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    open(DLL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
