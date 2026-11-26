#!/usr/bin/env python3
r"""
Vanilla bug: combat event logs dangle after a save is loaded -> "Exception occurred during LogbookChanged event
(TAoWMapControl)" (2026-10-23).  AoWEPACK.dll only.

User report 10/23 (MP Azracs vs Highmen, reloaded after an OOS, day 19): the dialog above, game continued.  VEH log of
`X\Save\autosave bug2.asg`: AV in TCombatEventLog.GetText 0x5572906A (`[[[self+0x18]+0x10]+0x48]`, reading a freed
TCombatLogbook's final-data object) called from TEventLogbook.ListEvents 0x557FDA62 (event-list refresh 0x423304).
Seen once before on 8/14 (keeper2 notes, parked).

Mechanism (all vanilla code):
  * TCombatLogbook is ref-counted: Create sets [+8] = 1, AddRef = VMT+0x28, Release = VMT+0x2C (frees at 0).
  * DistributeCombatEvent 0x5572928C makes one TCombatEventLog per player who saw the battle and each takes a
    reference via SetCombatLogbook 0x55728F2C; TCombatEventLog.Destroy releases it.  TPlayer.UpdateLogbook 0x55752D1C
    removes every event >= 3 days old, per player.
  * TCombatEventLog.ReadWrite 0x55728F54 streams [self+0x18] as a shared object reference (stream VMT+8, type 0x14)
    WITHOUT AddRef.  After loading, a logbook shared by N players' events has count 1 -> the first player's trim
    frees it, the others' events dangle (GetText AV in the event list) and their own later trim releases freed memory
    (decrements whatever now lives there - silent per-machine heap corruption).
POISONED SAVES (found on autosave bug2 with a live read): a save written while an event dangled can store the
logbook reference as an UNRELATED object that reused the freed memory (there: a TDiplomaticAction) - every load
then rebuilds the event pointing at it.  So the cave checks the class: [obj] == TCombatLogbook VMT -> AddRef;
anything else -> the event gets a fresh empty TCombatLogbook (count 1, its own; blank battle text, no dangling,
the foreign object is never touched).
Fix: hook 0x55728F63 (6A14 8D5318 = push 0x14 / lea edx,[ebx+0x18]) -> cave: run the original object read keeping
self, then if the stream is a real object load (StorageMode = stream VMT slot 0, (mode & 0x71) == 1: plain/text read;
compare/translate streams excluded) and [self+0x18] <> nil -> AddRef.  After a load the count is 1 + events, so a
logbook outlives every event (one small object per pre-load combat is kept until exit - never dangles).
Cave AoWEPACK 0x5583C300..0x5583C380 ('CLR1').  Backup .bak_combatlogref.  Dry-run default; --apply/--revert/--dis.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from bakpath import bak_path, game_file
    DEFAULT = game_file("AoWEPACK.dll")
except Exception:
    bak_path = lambda p, s: p + s
    DEFAULT = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\AoWEPACK.dll"

DELTA = 0x55700C00
SITE, SITE_LEN = 0x55728F63, 5
ORIG = bytes.fromhex("6A148D5318")
# the original tail the cave replaces: xor ecx,ecx / mov eax,esi / mov ebx,[eax] / call [ebx+8] / pop esi / pop ebx / ret
TAIL = bytes.fromhex("33C98BC68B18FF53085E5BC3")
ZONE, ZONE_END = 0x5583C300, 0x5583C380
MAGIC = b"CLR1"
SUF = ".bak_combatlogref"
CLASSCELL = 0x55716F3C        # class-ref cell -> TCombatLogbook VMT 0x55716F7C (relocated at load, so compare live)
LOGBOOK_CREATE = 0x55728D80   # TCombatLogbook.Create (eax = class, dl = 1, ecx = 0), as vanilla 0x5572710B


def build():
    code_va = ZONE + 0x10
    src = f"""
    push ebx
    push 0x14
    lea edx, [ebx + 0x18]
    xor ecx, ecx
    mov eax, esi
    mov ebx, dword ptr [eax]
    call dword ptr [ebx + 8]
    pop ebx
    mov eax, esi
    mov edx, dword ptr [eax]
    call dword ptr [edx]
    and al, 0x71
    cmp al, 1
    jne out
    mov eax, dword ptr [ebx + 0x18]
    test eax, eax
    jz out
    call get
get:
    pop ecx
    sub ecx, get
    mov ecx, dword ptr [ecx + {CLASSCELL:#x}]
    cmp dword ptr [eax], ecx
    je addref
    mov eax, ecx
    mov dl, 1
    xor ecx, ecx
    call {LOGBOOK_CREATE:#x}
    mov dword ptr [ebx + 0x18], eax
    jmp out
addref:
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x28]
out:
    pop esi
    pop ebx
    ret
"""
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, code_va)
    code = bytes(enc)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    assert 0x10 + len(code) <= len(z), hex(len(code))
    z[0x10:0x10 + len(code)] = code
    hook = b"\xE9" + struct.pack("<i", code_va - (SITE + 5))
    return bytes(z), hook, len(code)


def relocs(path):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    base = pe.OPTIONAL_HEADER.ImageBase
    return {en.rva + base for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for en in b.entries if en.type}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, hook, clen = build()
    so, zo = SITE - DELTA, ZONE - DELTA
    site, cur = bytes(d[so:so + SITE_LEN]), bytes(d[zo:zo + len(zone)])
    tail_ok = bytes(d[so + SITE_LEN:so + SITE_LEN + len(TAIL)]) == TAIL
    applied = site == hook and cur == zone
    vanilla = site == ORIG and not any(cur)
    rl = sorted(hex(r) for r in relocs(a.dll) if SITE - 3 <= r < SITE + SITE_LEN + len(TAIL) or ZONE - 3 <= r < ZONE_END)
    print("%s\n  site %s | tail %s | zone %s | code %d B | relocs: %s"
          % (a.dll, site.hex(), "ok" if tail_ok else "CHANGED", "CLR1" if applied else ("zero" if not any(cur) else "OTHER"),
             clen, rl or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[0x10:0x10 + clen], ZONE + 0x10):
            print("   %08x  %s %s" % (i.address, i.mnemonic, i.op_str))
    if not tail_ok or rl:
        print("ABORT: unexpected bytes/relocs"); return 1
    if applied:
        if not a.revert:
            print("already applied"); return 0
        d[so:so + SITE_LEN] = ORIG
        d[zo:zo + len(zone)] = bytes(len(zone))
        msg = "reverted"
    else:
        if a.revert:
            print("not applied - nothing to revert"); return 0
        if not vanilla:
            print("ABORT: site/zone not in the expected state"); return 1
        if not a.apply:
            print("Dry run OK - rerun with --apply"); return 0
        bp = bak_path(a.dll, SUF)
        if not os.path.exists(bp):
            shutil.copy2(a.dll, bp); print("backup -> " + bp)
        d[zo:zo + len(zone)] = zone
        d[so:so + SITE_LEN] = hook
        msg = "applied: loaded combat event logs AddRef their TCombatLogbook"
    with open(a.dll, "r+b") as f:
        f.write(d)
    chk = open(a.dll, "rb").read()
    assert chk[so:so + SITE_LEN] == (ORIG if a.revert else hook)
    print("Written and verified - " + msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
