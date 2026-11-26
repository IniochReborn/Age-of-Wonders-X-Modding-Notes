#!/usr/bin/env python3
r"""
AoWTCPCK.dll: network battles - drop the stale local events of the seats a battle turns REMOTE (2026-11-21).

User 11/21 (Wrath of the Three, 2 instances, simultaneous turns): independents attack the Orc hero + two allied AI
heroes; the Orc machine freezes in the battle with no error.  Ctrl+F report: executer waits at executed 426 on seat
11, whose queue starts with a TNegotiateTE that has NO token counter ([ev+0xC] = -1), the real remote events
(TSyncTE 0x1AA ...) behind it.

Cause (vanilla): AoWTC.TTacticalCombat.Initialize 0x429088
  1. controlling human [combat+0x4C] = first human player of the MAP,
  2. every non-human combat player gets that human's PCC connection mode + system id
     -> on all other machines those seats are REMOTE from here on,
  3. loop 0x4292FF: `if tc.Local or tc.Global then tc.ClearEvents`.
Step 3 runs after step 2, so on the non-controlling machines the AI seats are skipped and keep the events their
world-map AI had queued while the seat was still global.  A remote control only hands over events whose counter is
executed+i (TTokenControl.GetPrefetchableTokenEvents, Network 0x5580398C), so an uncounted event at the head blocks
that seat for ever.  The controlling machine cleared the same events in step 3, so dropping them is consistent.

Patch: the `call TTokenControl.Global` at 0x429332 -> cave 0x43E820:
    Global(tc) true  -> return 1 (vanilla: ClearEvents follows)
    otherwise        -> delete every event of [tc+4] with [ev+0xC] == -1, return 0
Counted events are kept (the controlling machine may already have sent battle events for the seat).
Network.dpl routines (TTokenEventList.GetCount / GetEvent / Delete) are reached from the run-time address in the
import slot of TTokenControl.ClearEvents (0x46EA1C) + fixed distances, the slot through the PIC delta trick
(TCPCK and Network both rebase).  No relocs in the cave or at the site.
EVERY machine in a network game should have the patch (it only changes what a machine does with its own stale
events, so mixed versions cannot desync, the unpatched machine can just still freeze).
Backup <game>\backup\AoWTCPCK.dll.bak_tcpurge.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
NETWORK = game_file("Network.dpl")
BAK_SUFFIX = ".bak_tcpurge"
V2F = 0x400C00
SITE_VA = 0x429332                       # call TTokenControl.Global (thunk 0x402CD4)
GLOBAL_THUNK, CLEAR_THUNK = 0x402CD4, 0x402CC4
CLEAR_SLOT = 0x46EA1C                    # import slot NetworkE.TTokenControl.ClearEvents
CTX_VA, CTX = 0x429337, bytes.fromhex("84c0741a")           # test al,al / je 0x429355
CAVE_VA, CAVE_ROOM = 0x43E820, 0xE0
NET = {"ClearEvents": "NetworkE.TTokenControl.ClearEvents", "GetCount": "NetworkE.TTokenEventList.GetCount",
       "GetEvent": "NetworkE.TTokenEventList.GetEvent", "Delete": "NetworkE.TTokenEventList.Delete"}
NET_EXPECT = {"ClearEvents": 0x38C8, "GetCount": 0x339C, "GetEvent": 0x338C, "Delete": 0x3414}   # RVAs


def rel(op, at, to): return bytes([op]) + struct.pack("<i", to - (at + 5))


def net_rvas():
    import pefile
    pe = pefile.PE(NETWORK, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    out = {}
    for s in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        n = (s.name or b"").decode().split("@")[0]
        for k, v in NET.items():
            if n == v: out[k] = s.address
    return out


def build_cave(r):
    d = lambda k: struct.pack("<i", r[k] - r["ClearEvents"])
    c = bytearray()
    c += bytes.fromhex("535657" "89c3")                      # push ebx/esi/edi ; mov ebx,eax (tc)
    c += rel(0xE8, CAVE_VA + len(c), GLOBAL_THUNK)           # call TTokenControl.Global
    c += bytes.fromhex("84c0")                               # test al,al
    jne_out = len(c); c += b"\x75\x00"                       # jne out
    c += bytes.fromhex("e800000000" "5f")                    # call $+5 ; pop edi
    here = CAVE_VA + len(c) - 1
    c += b"\x81\xef" + struct.pack("<I", here)               # sub edi, here  (delta)
    c += b"\x8b\xbf" + struct.pack("<I", CLEAR_SLOT)         # mov edi,[edi+slot] = ClearEvents (run time)
    c += bytes.fromhex("8b4304") + b"\x8d\x8f" + d("GetCount") + bytes.fromhex("ffd1")   # count of [tc+4]
    c += bytes.fromhex("89c6")                               # mov esi,eax
    loop = len(c)
    c += b"\x4e"                                             # dec esi
    js_done = len(c); c += b"\x78\x00"                       # js done
    c += bytes.fromhex("8b4304" "89f2") + b"\x8d\x8f" + d("GetEvent") + bytes.fromhex("ffd1")
    c += bytes.fromhex("83780cff")                           # cmp dword [eax+0xC], -1
    c += b"\x75" + struct.pack("<b", loop - (len(c) + 2))    # jne loop
    c += bytes.fromhex("8b4304" "89f2") + b"\x8d\x8f" + d("Delete") + bytes.fromhex("ffd1")
    c += b"\xeb" + struct.pack("<b", loop - (len(c) + 2))    # jmp loop
    done = len(c)
    c += bytes.fromhex("31c0")                               # xor eax,eax
    out = len(c)
    c += bytes.fromhex("5f5e5bc3")
    c[jne_out + 1] = out - (jne_out + 2)
    c[js_done + 1] = done - (js_done + 2)
    return bytes(c)


def reloc_hits(path, ranges):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    out = []
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type and any(lo - 3 <= ib + e.rva < hi for lo, hi in ranges): out.append(hex(ib + e.rva))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--show", action="store_true", help="disassemble the cave")
    a = ap.parse_args()
    r = net_rvas()
    if r != NET_EXPECT: print("ABORT: Network.dpl exports differ:", {k: hex(v) for k, v in r.items()}); return 1
    cave_new = build_cave(r)
    cave_orig = bytes(len(cave_new))
    site_orig, site_new = rel(0xE8, SITE_VA, GLOBAL_THUNK), rel(0xE8, SITE_VA, CAVE_VA)
    if a.show:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(cave_new, CAVE_VA):
            print("  %08X  %-6s %s" % (i.address, i.mnemonic, i.op_str))
    d = bytearray(open(a.dll, "rb").read())
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    if g(CTX_VA, len(CTX)) != CTX or g(GLOBAL_THUNK, 2) != b"\xff\x25" or g(CLEAR_THUNK, 6) != b"\xff\x25" + struct.pack("<I", CLEAR_SLOT):
        print("ABORT: Initialize loop / thunks not as expected"); return 1
    site, cave = g(SITE_VA, 5), g(CAVE_VA, len(cave_new))
    state = ("vanilla" if (site, cave) == (site_orig, cave_orig) else
             "ours" if (site, cave) == (site_new, cave_new) else "OTHER")
    print("site %#x: %s | cave %#x (%d B) -> %s" % (SITE_VA, site.hex(), CAVE_VA, len(cave_new), state))
    if state == "OTHER": print("ABORT"); return 1
    if state == "vanilla" and any(g(CAVE_VA, CAVE_ROOM)): print("ABORT: cave zone not empty"); return 1
    bad = reloc_hits(a.dll, [(SITE_VA, SITE_VA + 5), (CAVE_VA, CAVE_VA + len(cave_new))])
    if bad: print("ABORT: relocs in range", bad); return 1
    if state == ("vanilla" if a.revert else "ours"):
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    sw, cw = (site_orig, cave_orig) if a.revert else (site_new, cave_new)
    d[SITE_VA - V2F:SITE_VA - V2F + 5] = sw
    d[CAVE_VA - V2F:CAVE_VA - V2F + len(cw)] = cw
    if not a.apply and not a.revert:
        print("%d byte change. Dry run OK - rerun with --apply (or --revert)." % (5 + len(cw))); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f:                    # in-place (house rule: "wb" is refused on the live DLLs)
        for va, b in ((SITE_VA, sw), (CAVE_VA, cw)): f.seek(va - V2F); f.write(b)
    assert open(a.dll, "rb").read() == bytes(d)
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
