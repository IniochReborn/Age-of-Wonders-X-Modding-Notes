#!/usr/bin/env python3
r"""
dpwsockx.dll (IPXWrapper's DirectPlay IPX service provider, in the game folder): add the missing DeletePlayer
callback - fixes the client crash when the host leaves a 3+ player game (2026-11-16).

Symptom (user): 3+ player LAN game, the host is defeated (its game closes the DirectPlay session) -> one client
closes to desktop without any message, the others then see "connection lost" to that client.
Evidence (net_trace.py + X\Error Log.txt, 3 local instances): at the instant the host calls IDirectPlay::Close,
the client that does NOT become the new DirectPlay host dies on a DirectPlay worker thread:
    EXCEPTION C0000005 at 0 (call to NULL), stack dplayx.dll+0x11960 <- +0x14A4C <- +0x3EE0
dplayx.dll+0x1194C..0x1195E:  mov eax,[this+0x14] / mov esi,[eax+0x28] / call esi  = the service provider's
DPSP_SPCALLBACKS.DeletePlayer (offset 0x28), called with no NULL test while the departed host is removed during
host migration.  IPXWrapper's SPInit (0x6DE827E5) only fills EnumSessions/Reply/Send/CreatePlayer/GetCaps/Open/
+0x44/+0x48 -> DeletePlayer stays NULL.  (Microsoft's own provider implements it, so dplayx never needed a test.)
The game side is fine: the surviving client got DPSYS_HOST and played on.

Patch: SPInit's success exit `mov eax,0 / jmp` (0x6DE829D1, 5 B) -> jmp cave in the .text raw padding (RVA 0xC020):
    stub:  xor eax,eax / ret 4                          ; HRESULT DeletePlayer(LPDPSP_DELETEPLAYERDATA) = DP_OK
    hook:  mov eax,[ebp+8] / mov eax,[eax]              ; lpCB
           call $+5 / pop edx / add edx,(stub-$)        ; PIC (the DLL can be rebased)
           mov [eax+0x28],edx / mov eax,0 / jmp 0x6DE829F0
EVERY player needs the patched file.  The file is Authenticode-signed; the edit invalidates the signature (the
loader does not care).  Backup <game>\backup\dpwsockx.dll.bak_delplayer.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, BAK_SUFFIX = game_file("dpwsockx.dll"), ".bak_delplayer"
BASE = 0x6DE80000
SITE, SITE_ORIG, EXIT = 0x6DE829D1, bytes.fromhex("b800000000"), 0x6DE829F0
CTX_VA, CTX = 0x6DE829BD, bytes.fromhex("8b4508c7401814000000")       # mov eax,[ebp+8] / mov [eax+0x18],0x14
CB20_VA, CB20 = 0x6DE82986, bytes.fromhex("c74020")                    # mov [eax+0x20], CreatePlayer
CAVE = 0x6DE8C020


def rel(op, at, to): return bytes([op]) + struct.pack("<i", to - (at + 5))


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = """
    stub:
        xor eax, eax
        ret 4
        .align 8
    hook:
        mov eax, [ebp+8]
        mov eax, [eax]
        call here
    here:
        pop edx
        add edx, stub - here
        mov [eax+0x28], edx
        mov eax, 0
        jmp %#x
    """ % EXIT
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE)[0])
    return code, CAVE + 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    import pefile
    pe = pefile.PE(DLL, fast_load=True)
    if pe.OPTIONAL_HEADER.ImageBase != BASE: print("ABORT: unexpected image base"); return 1
    text = pe.sections[0]
    off = lambda va: va - BASE - text.VirtualAddress + text.PointerToRawData
    code, hook = build()
    if CAVE - BASE < text.VirtualAddress + text.Misc_VirtualSize or CAVE - BASE + len(code) > text.VirtualAddress + text.SizeOfRawData:
        print("ABORT: cave is not inside the .text raw padding"); return 1
    d = bytearray(open(DLL, "rb").read())
    g = lambda va, n: bytes(d[off(va):off(va) + n])
    if g(CTX_VA, len(CTX)) != CTX or g(CB20_VA, 3) != CB20:
        print("ABORT: this is not the expected IPXWrapper dpwsockx.dll build"); return 1
    site_new = rel(0xE9, SITE, hook)
    cur = (g(SITE, 5), g(CAVE, len(code)))
    state = "vanilla" if cur == (SITE_ORIG, bytes(len(code))) else "ours" if cur == (site_new, code) else "OTHER"
    print("site %#x: %s | cave %#x (%d B) -> %s" % (SITE, cur[0].hex(), CAVE, len(code), state))
    if state == "OTHER": print("ABORT"); return 1
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    rl = [BASE + e.rva for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in blk.entries if e.type]
    if any(SITE - 3 <= r < SITE + 5 or CAVE - 3 <= r < CAVE + len(code) for r in rl): print("ABORT: relocs in range"); return 1
    pe.close()
    if state == ("vanilla" if a.revert else "ours"):
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    ws = ((SITE, SITE_ORIG), (CAVE, bytes(len(code)))) if a.revert else ((SITE, site_new), (CAVE, code))
    with open(DLL, "r+b") as f:
        for va, b in ws:
            d[off(va):off(va) + len(b)] = b; f.seek(off(va)); f.write(b)
    assert open(DLL, "rb").read() == bytes(d)
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
